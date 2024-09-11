import os
import re
import subprocess
import sys
import tempfile
import pathlib
import shutil


artifacts_dir = "/srv/www.python.org/ftp/python"
github_oidc_issuer = "https://github.com/login/oauth"
google_oidc_issuer = "https://accounts.google.com"
expected_issuers_and_identities = {
    "3.7": (github_oidc_issuer, "nad@python.org"),
    "3.8": (github_oidc_issuer, "lukasz@langa.pl"),
    "3.9": (github_oidc_issuer, "lukasz@langa.pl"),
    "3.10": (google_oidc_issuer, "pablogsal@python.org"),
    "3.11": (google_oidc_issuer, "pablogsal@python.org"),
    "3.12": (google_oidc_issuer, "thomas@python.org"),
    "3.13": (google_oidc_issuer, "thomas@python.org"),
}
python_with_version_re = re.compile(r"-(3\.[0-9]{,2})\.[0-9]{,2}")


def confirm_before_continue(statement: str):
    assert input(
        f"{statement} (Submit 'y' and Enter to confirm and continue)"
    ).startswith("y")


def main():

    # Discover all Sigstore bundles
    orig_sigstore_bundles: list[pathlib.Path] = []
    for root, _, filenames in os.walk(artifacts_dir):
        for filename in filenames:
            if not filename.endswith(".sigstore") or not python_with_version_re.search(filename):
                continue
            orig_sigstore_bundles.append(pathlib.Path(root) / filename)

    assert orig_sigstore_bundles
    print("\n".join(sorted(map(str, orig_sigstore_bundles))))
    confirm_before_continue("Discovered Sigstore bundles, does this look correct?")

    # Saves all Sigstore bundles and their original locations to a temporary directory
    # along with creating a "restoration" script.
    backup_dir = pathlib.Path(tempfile.mkdtemp(prefix="backup-sigstore-"))
    print(
        f"Sigstore bundles being backed up to {backup_dir}, run ./restore-backup.sh to restore from backup"
    )
    with (backup_dir / "restore-backup.sh").open(mode="w") as restore_sh:
        restore_sh.truncate()

        for orig_sigstore_bundle in orig_sigstore_bundles:

            # Save the original Sigstore bundle to a temporary directory.
            restore_sigstore_bundle = backup_dir / orig_sigstore_bundle.name
            assert not restore_sigstore_bundle.exists()
            shutil.copyfile(orig_sigstore_bundle, restore_sigstore_bundle)

            # Write the restoration command to the restore.sh file.
            restore_sh.write(f"cp {restore_sigstore_bundle} {orig_sigstore_bundle}\n")

    confirm_before_continue(
        f"Confirm that the backup directory and script exists at {backup_dir}"
    )

    # Create a temporary working directory for files and the 'apply-changes.sh' script.
    working_dir = pathlib.Path(tempfile.mkdtemp(prefix="working-sigstore-"))
    print(f"Sigstore bundles being copied to {working_dir}")
    working_sigstore_bundles_to_orig_bundles: dict[pathlib.Path, pathlib.Path] = {}

    apply_sh_filepath = working_dir / "apply-changes.sh"
    with apply_sh_filepath.open(mode="w") as apply_sh:
        apply_sh.truncate()

        # Copy the original Sigstore file to the working directory
        for orig_sigstore_bundle in orig_sigstore_bundles:
            working_sigstore_bundle = working_dir / orig_sigstore_bundle.name
            assert not working_sigstore_bundle.exists()
            shutil.copyfile(orig_sigstore_bundle, working_sigstore_bundle)
            working_sigstore_bundles_to_orig_bundles[working_sigstore_bundle] = (
                orig_sigstore_bundle
            )

            apply_sh.write(f"cp {working_sigstore_bundle} {orig_sigstore_bundle}\n")

    # Add the Sigstore checkpoint fix to each bundle
    print("Sigstore bundles being fixed")
    for working_sigstore_bundle in working_sigstore_bundles_to_orig_bundles.keys():
        sigstore_fix_bundle_argv = [
            sys.executable,
            "-m",
            "sigstore",
            "plumbing",
            "fix-bundle",
            "--in-place",
            "--bundle",
            str(working_sigstore_bundle),
        ]
        print(" ".join(sigstore_fix_bundle_argv))
        subprocess.check_call(sigstore_fix_bundle_argv)

    # Check that every fixed bundle now verifies correctly.
    print("Verifying fixed Sigstore bundles")
    for (
        working_sigstore_bundle,
        orig_sigstore_bundle,
    ) in working_sigstore_bundles_to_orig_bundles.items():
        # Use the original artifact path to verify the new bundle.
        orig_artifact = (
            orig_sigstore_bundle.parent
            / orig_sigstore_bundle.name.removesuffix(".sigstore")
        )
        assert orig_artifact.is_file()

        # Pull the Python version from the artifact
        if not (match := python_with_version_re.search(orig_artifact.name)):
            print(
                f"Couldn't find Python major and minor version for {orig_artifact.name}"
            )
            exit(1)
        python_major_minor = match.group(1)

        # Mapping between Python release and expected issuer and identity
        cert_oidc_issuer, cert_identity = expected_issuers_and_identities[
            python_major_minor
        ]

        # Create the verification command
        sigstore_verify_argv = [
            sys.executable,
            "-m",
            "sigstore",
            "verify",
            "identity",
            "--cert-oidc-issuer",
            cert_oidc_issuer,
            "--cert-identity",
            cert_identity,
            "--bundle",
            str(working_sigstore_bundle),
            str(orig_artifact),
        ]

        print(" ".join(sigstore_verify_argv))
        subprocess.check_call(sigstore_verify_argv)

    print(
        f">>> All updated bundles have been verified, run {apply_sh_filepath} to apply changes to Sigstore bundles"
    )


if __name__ == "__main__":
    main()
