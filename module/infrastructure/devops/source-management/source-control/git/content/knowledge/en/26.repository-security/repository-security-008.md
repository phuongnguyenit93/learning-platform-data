# Verifying Signatures, Trust Sources, and Signature Limitations

In a shared repository, commits and tags can be signed with cryptographic keys so recipients can check whether content was signed by the corresponding key. Signatures help detect tampering with commit/tag content after signing and provide evidence of which key created the signature. However, a valid signature does not automatically prove that the keyholder is the right person, that they are authorized to modify a branch, or that the code is safe.

When verifying Git signatures, separate three questions: **is the signature cryptographically valid**, **does the signing key or identity come from a trusted source**, and **is the signer authorized to sign this kind of change under project policy**. Commands like `git verify-commit`, `git verify-tag`, and `git log --show-signature` verify the signature itself; confirming key trust and enforcing policy require additional trusted sources.

## 1. Which objects can Git sign?

Git supports signatures on commits and annotated tags. The signature is stored inside the Git object and verified against the signed content and corresponding public key.

- **Signed commit:** a commit containing a signature in its metadata. The signature covers the commit content, including tree, parents, author, committer, and commit message.
- **Signed annotated tag:** a tag object containing tagger metadata, message, target object, and signature. This is the common way to sign a release milestone.
- **Lightweight tag:** merely a ref pointing to an object, with no separate tag object, so it cannot carry a tag signature like `git tag -s` produces.

A signed commit can be verified independently of whichever branch points to it. A signed annotated tag confirms the keyholder signed the tag content and the object the tag points to. That does not mean every preceding commit in history was signed.

## 2. Distinguishing a valid signature, identity, and authorization

Signature verification results should be interpreted layer by layer:

| Question | What to check | What cannot be concluded from the signature alone |
|---|---|---|
| Is the signature valid? | The signature matches the object content and public key | Who holds the key in real life or inside the organization |
| Is the key trusted? | Fingerprint/principal/certificate matches a trusted source and is not revoked per policy | Whether that person is authorized to review, merge, or release |
| Is the signer authorized? | Allowed signers list, scope of responsibility, timing, and approval workflow | Whether the code has vulnerabilities or malicious behavior |

For example, `git verify-commit` may confirm a valid signature against an OpenPGP key. Yet if you obtained that public key from an unverified page, an attacker could supply their own key and sign commits themselves. The signature remains cryptographically valid while the identity attributed to the key is false.

Therefore, verify keys by fingerprint or identity from an independent trusted source, then check against project policy. Never rely solely on the display name or email inside a commit as proof of identity: those fields are commit metadata and can be arbitrarily set by whoever created the commit.

## 3. Signature formats supported by Git

Git supports multiple signing and verification backends. The format is selected via the `gpg.format` setting.

| `gpg.format` value | Mechanism | Common tools |
|---|---|---|
| `openpgp` | OpenPGP signatures | GnuPG (`gpg`) |
| `ssh` | SSH signatures | `ssh-keygen` and SSH keys |
| `x509` | X.509 signatures | `gpgsm` with appropriate certificate infrastructure |

If unconfigured, Git defaults to `openpgp`. Configuration and verification tools must align between the signing machine and the verifying machine. A machine may be able to verify OpenPGP commits while lacking configuration to verify SSH or X.509.

Check current configuration:

```bash
git config --show-origin --get gpg.format
git config --show-origin --get gpg.program
git config --show-origin --get user.signingkey
```

Not every key or certificate works with every format. Confirm which signature type the project requires before configuring.

## 4. Verifying a commit with git verify-commit

To check a commit's signature:

```bash
git verify-commit <commit>
```

Examples:

```bash
git verify-commit HEAD
git verify-commit a1b2c3d
```

If the commit is signed and verification is properly configured, Git invokes the corresponding verifier program. When valid, the output reports a good signature along with key or signer details. If the commit is unsigned, the signature is invalid, the key cannot be found, or the verifier is misconfigured, verification will fail.

To view more output from the verifier:

```bash
git verify-commit --verbose HEAD
```

With OpenPGP, output from GnuPG distinguishes a valid signature from the trust level your keyring assigns to the key. Read the full output; a "Good signature" line only confirms the signature matches the public key used for checking. It does not replace verifying the fingerprint and signer authorization.

## 5. Verifying a tag signature with git verify-tag

To check an annotated tag:

```bash
git verify-tag v2.4.0
```

You can pass `--verbose` to view additional verifier output:

```bash
git verify-tag --verbose v2.4.0
```

This command verifies the tag object's signature. Lightweight tags have no tag object or dedicated signature, so they cannot be verified this way.

You can inspect tag contents together with its signature via:

```bash
git show --show-signature v2.4.0
```

A validly signed tag proves the key signed the tag object pointing to the target object. If the tag points to a release commit, also inspect that commit and any release criteria required by your team. A tag signature does not retroactively sign earlier commits.

## 6. Viewing signatures in history with git log --show-signature

When reviewing a commit range, you can display signature details alongside history:

```bash
git log --show-signature --oneline --decorate -10
```

Or inspect a specific branch:

```bash
git log --show-signature --format=fuller origin/main
```

`--show-signature` instructs Git to show signature verification details for signed commits in the viewed history. Unsigned commits simply have no signature details to display. Displaying output does not mean project policy is satisfied; you must check the signer, commit range, and mandatory rules.

To verify a set of commits explicitly in an automated pipeline, loop over selected commit hashes and invoke `git verify-commit` on each commit. Define the exact history range to check, such as new commits on a feature branch relative to the base branch; never assume checking only the branch tip is enough.

## 7. Confirming OpenPGP keys by fingerprint

With OpenPGP, never compare only the name or email shown in the output. Retrieve the public key's full fingerprint and verify it through an independent channel.

List keys with fingerprints:

```bash
gpg --list-keys --fingerprint
```

View the fingerprint of a specific key:

```bash
gpg --fingerprint <key-id-or-email>
```

Then compare the fingerprint against a source published by your organization, such as an internal signing key directory, authenticated security documentation, or the release owner over a verified communication channel. Short key IDs can collide or fail to uniquely identify a key; the full fingerprint is what you must compare.

GnuPG maintains its own trust model representing confidence in keys and identity bindings. A valid signature may appear alongside a warning that the key is uncertified or untrusted. Never disable trust checks just to silence warnings; confirm the key owner and apply your organization's trust procedures.

## 8. Verifying SSH signatures with allowed signers

Git supports using SSH keys to sign commits and tags. An SSH key used for signature verification must be associated with an authorized principal (identity) via an `allowedSignersFile`.

Example `~/.ssh/allowed_signers` file:

```text
dev@example.com namespaces="git" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExamplePublicKeyMaterial
release@example.com namespaces="git" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAnotherPublicKeyMaterial
```

The key strings above are illustrative only, not usable keys. Each line includes a principal, optional settings, key type, and public key. The principal must match the signer identity defined by the project; `namespaces="git"` restricts the key to the Git signing namespace.

Configure the file for the repository or user:

```bash
git config --global gpg.format ssh
git config --global gpg.ssh.allowedSignersFile ~/.ssh/allowed_signers
```

Once configured, verify the commit:

```bash
git verify-commit HEAD
```

The allowed signers file is a list of keys accepted for verification under local configuration. If a key is revoked or no longer permitted, update your policy and revocation configuration accordingly; do not leave old keys in the allowed list merely because historical commits used them.

With SSH, "key is in allowed signers" is a trust decision made by whoever manages that file. It does not by itself prove which employee owns the principal or whether they are authorized to approve a release. The key source and management of this file must be protected, reviewed, and kept current.

## 9. Verifying X.509 certificates

Git also supports X.509 signatures via the `x509` format, typically using `gpgsm` for signing and verification. In this model, trust depends on certificates, certificate chains, CAs, and the trust store configured on the system.

Check the format:

```bash
git config --get gpg.format
```

If the project uses X.509, appropriate tools and certificate/CA configurations must be set up per organizational policy. A signature may validate against the key inside the certificate while still requiring verification of the certificate chain, expiration, revocation status, and subject identity. Never add unfamiliar CAs or certificates to your trust store just to make a commit pass verification.

## 10. Checking the signer's trust source

A trustworthy verification workflow requires a clear provenance for keys or certificates. Usable sources include:

- A signing key or fingerprint directory published by security/release teams in an authenticated internal system.
- Official project documentation accessed over verified domains and distribution channels.
- Certificates issued by an internal CA or trusted public CA with a valid certificate chain.
- A centrally managed SSH allowed signers file with code review and change history.
- Fingerprint confirmation via a channel independent of where you fetched the commits or public key.

Do not trust a key merely because:

- The key was attached to the same pull request containing the commit to verify.
- The signer's email or name resembles a teammate's name.
- A short key ID matches entries in an unauthenticated log.
- A mirror site or unverified attachment supplied the public key.

If an attacker controls both the commit and the key source you use for confirmation, the check is not independent. Obtain fingerprints or principals from a pre-authenticated source.

## 11. Signatures do not replace access controls and code review

A signature answers the question "which key signed this content?" within the verification mechanism's scope. It does not automatically answer:

- Whether the signer has permission to push to `main`.
- Whether the commit was reviewed or passed CI.
- Whether the signer is authorized to create a release or sign a version tag.
- Whether files in the commit contain malware, secrets, or vulnerabilities.
- Whether an artifact built from this commit is the exact artifact deployed.

Those conditions require separate controls such as repository permissions, branch protection, pull request reviews, CI, release approvals, and build provenance/attestation. For instance, a contributor may validly sign commits with their key and still lack permission to merge into a protected branch.

For releases, a team may require signed commits/tags, signers belonging to an approved release managers list, passing pipelines, and valid artifact provenance. Each condition must be verified individually per policy.

## 12. Commit/tag signatures vs. push signatures

Git also provides a mechanism to sign push requests. For example:

```bash
git push --signed origin main
```

A push signature generates a certificate for the ref update request in that push. It differs from signatures embedded inside commits or annotated tags:

| Signature type | What does it verify? | Where is it stored? |
|---|---|---|
| Commit signature | Commit content was signed by a key | Inside the commit object |
| Tag signature | Annotated tag content and target object were signed | Inside the tag object |
| Push certificate | Ref update request of the push was signed | Sent in the push protocol to a supporting server |

The server must support and be configured to receive push certificates for push signatures to be enforced per policy. Push signatures do not replace commit/tag signatures; conversely, signed commits do not prove that the push request to the server was signed.

## 13. Example workflow for checking a release

Suppose a team receives tag `v3.2.0` and must verify it before deployment.

```bash
# 1. Inspect tag details and signature.
git show --show-signature v3.2.0

# 2. Verify the tag object signature.
git verify-tag --verbose v3.2.0

# 3. Resolve the commit the tag points to.
git rev-parse 'v3.2.0^{commit}'

# 4. Verify the target commit signature if required by policy.
git verify-commit 'v3.2.0^{commit}'

# 5. Inspect history and signatures of related commits.
git log --show-signature --oneline -20 'v3.2.0^{commit}'
```

After these technical steps, cross-check the signer's fingerprint or principal against the trusted release list. Confirm the tag points to the expected commit, the branch/release passed review, and CI succeeded. If the project requires every commit in a range to be signed, verify each commit in that range rather than only checking the target commit.

If a signature fails verification, halt the release workflow and investigate the root cause: missing public key, wrong `gpg.format`, missing verifier tool, expired/revoked key, or altered content. Never ignore warnings just to proceed with deployment.

## 14. Common errors and warnings

| Symptom | Possible cause | Resolution |
|---|---|---|
| Commit has no signature | Commit was created without signing | Check whether signing is mandatory under policy; a nonexistent signature cannot be verified |
| Public key not found | Verifier machine lacks the corresponding key | Fetch the key from a trusted source, verify fingerprint, then import/configure |
| Invalid signature | Content altered, corrupted signature, or wrong verifier | Inspect commit/tag, signature format, and verification tool |
| Good signature with trust warning | Signature is valid but keyring does not yet trust the identity | Verify fingerprint via an independent source and configure trust per policy |
| SSH signature fails to verify | Missing or wrong `gpg.ssh.allowedSignersFile`, mismatched principal, or unauthorized key | Check allowed signers and principals published by the project |
| X.509 chain untrusted | Missing CA, trust store issue, or certificate problem | Verify certificate chain and certificate status per organizational policy |
| Tag verification fails on lightweight tag | Lightweight tag has no tag object/signature | Use a signed annotated tag when release verification is required |
| Signature valid but rejected by policy | Signer is not on the authorized list or lacks review/CI | Check permissions and separate policy criteria |

## 15. Takeaways

To verify a commit, use `git verify-commit`; to verify an annotated tag, use `git verify-tag`; to inspect signatures alongside history, use `git log --show-signature`. Git supports OpenPGP, SSH, and X.509, but the verifying machine must be configured with the right format and key/certificate sources.

A valid signature proves the content matches the key used to sign it. To trust the identity, verify the fingerprint, principal, or certificate from an independent source. To confirm authorization to make the change, you still need repository permissions, reviews, CI, and release policies. Signatures are an important layer of protection for Git history, not standalone proof that a signer is authorized or that code is safe.
