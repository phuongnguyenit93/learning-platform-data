# Signed tags and verification with git tag -v

When marking a release version, a team often wants to know whether the tag was genuinely created by an authorized releaser and whether it points to the exact approved commit. Git supports **signed tags**: tags carrying a cryptographic signature bound to the tagged object and the tag's metadata.

You create a signed tag with `git tag -s` and verify its signature with `git tag -v`. Verification confirms that the signature is valid against a public key present in your environment. To conclude that the tag is trustworthy, you must also verify the signer's identity and whether that person is authorized to release the version.

## 1. Distinguishing lightweight, annotated, and signed tags

Git has two basic tag types:

- **Lightweight tag** is a simple reference pointing directly to a Git object, typically a commit. It does not create a separate tag object, does not store a tagger message like an annotated tag, and has nowhere to attach a tag signature.
- **Annotated tag** creates a dedicated tag object storing the tag name, tagger, timestamp, message, and target object. It is suitable for marking release versions.

A signed tag is an annotated tag with an added cryptographic signature. Common creation commands:

```bash
# Lightweight tag
git tag v2.4.0

# Annotated tag, unsigned
git tag -a v2.4.0 -m "Release v2.4.0"

# Signed annotated tag
git tag -s v2.4.0 -m "Release v2.4.0"
```

In practice, do not create all three tags with the same name in one repository. The example is solely for comparing syntax. For release versions requiring signer verification, use a signed tag. `-s` creates an annotated tag and signs the tag object; `-a` only creates an unsigned annotated tag.

The signature is attached to the tag object, covering the target object and the tag's metadata. Because a commit has its own hash and the tag stores the target object's hash, the tag signature also binds to the marked commit. A tag signature differs from a commit signature: `git tag -v` verifies tags, while `git verify-commit` verifies commit signatures.

## 2. Preparing an OpenPGP signing key

Git commonly uses GPG/OpenPGP to sign tags. The machine creating the tag needs GPG installed along with the corresponding private key. The private key must be kept secure; others only need the public key to verify the signature.

List available secret keys:

```bash
gpg --list-secret-keys --keyid-format=long
```

The output may include a `sec` line with a key ID. Select the release key approved by your organization, then configure Git to use it:

```bash
git config --global user.signingkey <KEY_ID>
```

If the machine has multiple keys, explicitly choose the right key instead of relying on a default. You can verify the configuration:

```bash
git config --show-origin --get user.signingkey
```

Git invokes GPG to sign; depending on the environment, you will need to unlock the key with a passphrase or confirm via pinentry. If the signing command reports that GPG cannot be found, verify GPG is installed and available in `PATH`.

For others to verify, export the public key:

```bash
gpg --armor --export <KEY_ID> > release-public-key.asc
```

Share only the public key. Never send the private key file, never commit private keys to a repository, and never store passphrases in scripts or project configuration files.

## 3. Creating a signed tag

Before creating a tag, identify the commit to release and inspect the working tree:

```bash
git status
git log -1 --oneline
```

If you need to attach the tag to the current commit:

```bash
git tag -s v2.4.0 -m "Release v2.4.0"
```

If you want to specify the target commit explicitly:

```bash
git tag -s v2.4.0 <COMMIT_ID> -m "Release v2.4.0"
```

Git creates the tag object and signs it with the configured key. If you need to use a specific key just for this tag creation, specify it with `-u`:

```bash
git tag -s -u <KEY_ID> v2.4.0 -m "Release v2.4.0"
```

A tag name must be unique in the repository. If `v2.4.0` already exists, Git normally refuses to recreate it. Do not use `-f` merely to bypass this error; first inspect the existing tag and check your team's tag correction procedure. Published release tags should generally be kept immutable.

Inspect the newly created tag:

```bash
git show --no-patch --decorate v2.4.0
git cat-file -p refs/tags/v2.4.0
```

For an annotated tag, `git cat-file -p` displays the tag object, including the target object, tagger, message, and signature block if signed. The `git show` command displays the commit contents the tag points to.

## 4. Verifying signatures with git tag -v

Verification command:

```bash
git tag -v v2.4.0
```

Git reads the tag object, extracts the signature, and invokes the corresponding verification tool. With OpenPGP, that tool is usually GPG. When the signature is valid and the public key is available, the output typically indicates a good signature along with the signer's identity or key ID.

You can also use the dedicated plumbing command:

```bash
git verify-tag v2.4.0
```

`git verify-tag` checks a tag's signature; `git tag -v` is the standard way to verify a specific tag. Neither replaces confirming that the key belongs to the authorized releaser.

### Common outcomes

| Result | Meaning | Action required |
|---|---|---|
| Good signature | Signature matches the tag object and the public key used for verification | Verify the fingerprint and the key owner's release authorization |
| Public key not found | The machine lacks the key needed to verify | Obtain the public key from a trusted source, import it, and verify its fingerprint |
| BAD signature | Tag data or signature does not match | Do not trust the tag; check the tag source and data integrity |
| Tag has no signature or is not a signed annotated tag | No tag signature exists to verify | Confirm whether the tag is the right type per release policy |
| Signing tool failed to run | Git could not invoke GPG or the configured verification program | Check the installed program, path, and Git configuration |

A `Good signature` message proves the signature is valid for the key used, but it does not by itself prove the signer is an employee authorized to release. A public key can be imported into a keyring without identity verification; therefore, never skip the fingerprint verification step.

## 5. Receiving and verifying public keys

When receiving a releaser's public key, verify its fingerprint through an independent channel, such as an internal key directory or direct confirmation from the key custodian. Do not extract the fingerprint from the key file itself and treat it as independent proof.

Import the public key after confirming the source:

```bash
gpg --import release-public-key.asc
```

Inspect the fingerprint:

```bash
gpg --fingerprint <KEY_ID>
```

Compare the full fingerprint against information published by your organization. Then verify the tag:

```bash
git tag -v v2.4.0
```

If GPG reports a valid signature while the key's trust status is not yet established, follow your team's identity verification policy. GPG's trust mechanism and organizational release authorization are related, but they are not identical.

## 6. Using SSH keys to sign tags

Modern versions of Git also support signing with SSH. This is a practical choice when an organization already manages SSH keys for developers. Example configuration:

```bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519
```

Create the tag as usual:

```bash
git tag -s v2.4.0 -m "Release v2.4.0"
```

To verify SSH signatures, Git needs a list of allowed signers via `gpg.ssh.allowedSignersFile`. This file uses OpenSSH's allowed signers format, where each line associates a principal (typically an email address) with a public key permitted to sign. Example single-line format:

```text
release@example.com namespaces="git" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... release-key
```

Configure the path to that file:

```bash
git config --global gpg.ssh.allowedSignersFile ~/.config/git/allowed_signers
```

After configuring the list of allowed keys, run:

```bash
git tag -v v2.4.0
```

Do not copy the illustrative key string verbatim into a real configuration. Use an SSH public key confirmed by an administrator and a principal matching the tagger's identity. If your team uses OpenPGP, SSH signing configuration is not needed; if using SSH, prepare the allowed signers file on every verifying machine.

## 7. Publishing and verifying tags via a remote

Tags are created in the local repository. After verifying the tag on the creating machine, push it explicitly to the remote:

```bash
git push origin v2.4.0
```

Check that the remote advertises the tag:

```bash
git ls-remote --tags origin v2.4.0
```

`ls-remote` only displays references on the server; it does not verify the tag signature. In another clone, fetch the tag and verify it independently:

```bash
git fetch origin tag v2.4.0
git tag -v v2.4.0
git show --no-patch --decorate v2.4.0
```

The verifying clone needs the releaser's public key and corresponding verification tool configuration. If the tag uses an SSH signature, the verifying machine needs an appropriate allowed signers file. A successful push also does not mean the server automatically verified the signature; that depends on Git server policies and hooks.

## 8. Limitations and principles for protecting release tags

- **A signature does not replace release policy.** Always check that the signer is authorized to release that version.
- **A signature does not make a tag immutable.** Someone with write access on the remote can still delete or replace the tag ref if the server allows it; a tag signature only detects whether the tag object content differs from the signature.
- **Do not silently modify published release tags.** If a mistake is discovered, issue a new version tag or publish a clear revocation/replacement procedure.
- **Never share private keys.** Distribute only public keys and verified fingerprints.
- **Verify after fetching.** A tag received from a remote should not be assumed trustworthy simply because it resides on a familiar server.
- **Distinguish tag signatures from commit signatures.** If policy requires both tags and commits to be signed, verify each signature type separately.

## 9. Release workflow with signed tags

A basic workflow may include the following steps:

1. Confirm the commit has passed review and testing.
2. Select the organization-approved signing key; verify the `user.signingkey` setting.
3. Create a signed annotated tag with `git tag -s` and include the version message.
4. Run `git tag -v` on the creating machine to check the signature and confirm the target commit.
5. Push the specific tag with `git push origin <tag>`.
6. In an independent clone, fetch the tag and run `git tag -v`; verify the fingerprint and release authorization.
7. Record the version details, target commit, and signer per the team's release process.

Shortened command example:

```bash
git status
git log -1 --oneline
git tag -s v2.4.0 -m "Release v2.4.0"
git tag -v v2.4.0
git push origin v2.4.0
```

## 10. Hands-on exercise

In a test repository, prepare an OpenPGP key meant for a learning environment or use a pre-provisioned test key. Never use an organization's private key in personal exercises.

1. Use `gpg --list-secret-keys --keyid-format=long` to identify the signing key.
2. Configure `user.signingkey` to point to that key.
3. Create a signed annotated tag `v0.1.0` with `git tag -s`.
4. Run `git tag -v v0.1.0` and read the verification output.
5. Export the public key, import it into the keyring of another test environment, and verify its fingerprint over an independent channel.
6. Fetch the tag in a second clone, run `git tag -v`, and compare results.
7. Try verifying a lightweight tag to observe why it has no tag object signature.

You have completed the exercise when you can create a signed tag, verify its signature with `git tag -v`, distinguish cryptographic verification from identity verification, and explain why private keys must be protected.
