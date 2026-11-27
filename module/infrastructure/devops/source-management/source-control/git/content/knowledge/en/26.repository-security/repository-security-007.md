# Signing Commits and Tags with GPG and SSH

Digital signatures allow recipients to verify whether a commit or tag was signed by the corresponding key and whether the signed content was modified afterward. Git supports signing with OpenPGP via GPG and with SSH keys. Both approaches use different key mechanisms, yet both can attach a signature to a commit or annotated tag for others to verify.

In the **Repository Security** chapter of the **SOURCE_CONTROL_GIT** module, this lesson covers setting up, creating, and verifying commit and tag signatures with GPG and SSH. You will distinguish signatures on Git objects from signatures on a push, understand how public keys are distributed, and learn why a cryptographically valid signature still needs to be matched against a trusted identity.

After this lesson, you will be able to:

- Explain how signatures are stored in commits and annotated tags.
- Distinguish signing with GPG/OpenPGP from SSH signing.
- Generate or select a signing key, configure Git, and sign commits/tags.
- Verify signatures using Git commands.
- Configure allowed signers for SSH and understand the role of trust in GPG.
- Automatically sign commits or tags according to personal or project policy.
- Distinguish signed commits, signed tags, and signed pushes.
- Troubleshoot invalid signatures, missing keys, or mismatched identity metadata.

## 1. What do digital signatures solve in Git?

A Git commit contains a snapshot, parent commit(s), author metadata, committer metadata, timestamps, and a message. When signing a commit, Git creates a cryptographic signature bound to the commit content. An annotated tag can also contain a signature bound to the tag object.

A signature lets a verifier check:

- Whether the commit or tag content matches the signature.
- Whether the signature was created by the corresponding key.
- Whether that key is associated with an identity trusted by the organization.

Signing does not encrypt source code and does not hide commit contents. Anyone with read access to the repository can still read files and history. Signatures provide proof of authenticity and integrity; they do not replace repository access controls, code review, testing, or branch policies.

Git can sign using:

- **OpenPGP/GPG**: uses an OpenPGP key pair and GPG's key and trust database.
- **SSH**: uses an SSH key to create signatures; for verification, Git requires a list of allowed public keys and their corresponding principals.

Choose a method that fits your team's existing infrastructure. Team members can even use different methods if the verification systems are configured to accept both.

## 2. How do commit signatures and tag signatures differ?

### Signed commit

A commit signature is stored inside the commit object itself. When verifying, Git checks the signature on that commit.

Create a signed commit:

~~~bash
git commit -S -m "feat: add signed release metadata"
~~~

The -S option instructs Git to sign the commit using the configured format and key. You can specify a particular key if your environment has multiple keys:

~~~bash
git commit -S<key-id> -m "fix: validate signed request"
~~~

There is no space between -S and the key ID in the attached form; alternative option forms are available depending on your Git version. If user.signingKey is already set, -S alone is usually sufficient.

### Signed tag

A signed tag must be an annotated tag because the signature is stored inside the tag object. A lightweight tag is merely a ref pointing directly to an object and has no tag object to hold a signature.

Create a signed annotated tag:

~~~bash
git tag -s v1.2.0 -m "Release v1.2.0"
~~~

Attach a tag to a specific commit:

~~~bash
git tag -s v1.2.0 <commit> -m "Release v1.2.0"
~~~

This command creates a tag object containing tagger metadata, a message, and a signature. The tag points to the specified commit even if HEAD currently points to another commit.

### Signatures are not added automatically to every operation

The -S option signs the object created by that command. Unless auto-signing is configured, new commits or tags may not be signed. A signed tag does not turn earlier commits into signed commits; conversely, signing commits does not automatically create a signed tag.

## 3. Common Git configuration for signing

Git uses several configuration keys to select the signing format, program, and key.

| Key | Role |
| --- | --- |
| gpg.format | Selects the signature format: openpgp, ssh, or x509 |
| user.signingKey | Key or key identifier used for signing |
| gpg.program | Program used to sign/verify OpenPGP or another configured format |
| gpg.ssh.program | SSH program used to create/verify SSH signatures |
| gpg.ssh.allowedSignersFile | File mapping principals to public keys allowed for verifying SSH signatures |
| gpg.ssh.revocationFile | File containing revoked SSH key information checked during verification |
| commit.gpgsign | Automatically sign commits when creating commits |
| tag.gpgSign | Automatically sign annotated tags when creating tags |

Inspect related configuration:

~~~bash
git config --show-origin --show-scope --get-regexp '^(gpg|user\.signingkey|commit\.gpgsign|tag\.gpgsign)'
~~~

Set configuration at global scope to apply across all repositories for the user; set it at local scope to apply only to the current project. Local configuration can override global settings.

Never store private keys or passphrases in Git config. Git config should only hold paths, fingerprints, or key identifiers; private keys must be protected with proper key tools and authentication mechanisms.

## 4. Signing with GPG/OpenPGP

### Step 1: check GPG

Confirm GPG is in PATH:

~~~bash
gpg --version
~~~

If Git cannot find the GPG program, install GPG for your OS or set the executable path via gpg.program:

~~~bash
git config --global gpg.program gpg
~~~

The value above assumes the executable is named gpg on PATH. If using a specific path, supply the exact path on your machine.

### Step 2: create or choose a secret key

If you do not yet have an OpenPGP key, generate one:

~~~bash
gpg --full-generate-key
~~~

Follow the prompts to choose the key type, length or algorithm, expiration, and identity. Use an email matching your commit identity or organizational policy. Set a strong passphrase to protect the private key.

List secret keys:

~~~bash
gpg --list-secret-keys --keyid-format=long
~~~

View the fingerprint:

~~~bash
gpg --fingerprint <key-id>
~~~

Prefer using the full fingerprint to identify a key so you avoid collisions between short key IDs. If your organization already issued a key, use that key per instructions instead of creating an unapproved one.

### Step 3: configure Git to use GPG

Select OpenPGP format and your signing key:

~~~bash
git config --global gpg.format openpgp
git config --global user.signingKey <fingerprint>
~~~

If you want Git to automatically sign all new commits and annotated tags:

~~~bash
git config --global commit.gpgsign true
git config --global tag.gpgSign true
~~~

If you only want to sign selected commits/tags, leave both auto-sign settings off and pass -S on the commands you want signed.

### Step 4: sign a commit

~~~bash
git commit -S -m "feat: add account recovery"
~~~

If commit.gpgsign is enabled, a regular git commit command will also sign. GPG may prompt for a passphrase or display an authentication dialog depending on agent configuration and environment.

### Step 5: sign an annotated tag

~~~bash
git tag -s v2.0.0 -m "Release v2.0.0"
~~~

If tag.gpgSign is enabled, creating an annotated tag per configuration may sign automatically. To make intent explicit in release documentation, teams should still use -s in release examples.

## 5. Distributing and verifying GPG keys

Recipients need the corresponding public key to verify signatures. Export the public key:

~~~bash
gpg --armor --export <fingerprint> > signing-public-key.asc
~~~

Share the public key file through an accepted team channel. Recipients import the key:

~~~bash
gpg --import signing-public-key.asc
~~~

After importing, verify the fingerprint via an independent trusted channel, such as an internal key directory or direct confirmation with the key owner. Do not rely solely on the name and email displayed in the key; those fields are self-declared.

GPG has its own trust model. A valid signature message means the signature matches the public key, yet confidence that the key belongs to the right person depends on how your organization verifies and marks trust. Distinguish:

- **Signature validity**: signed data has not been altered and the signature matches the key.
- **Key identity/trust**: whether the key genuinely belongs to a person or organization you trust.

Never treat importing an arbitrary public key as having verified the signer's identity.

## 6. Verifying signed commits and signed tags with GPG

Verify the current commit:

~~~bash
git verify-commit HEAD
~~~

Verify a specific commit:

~~~bash
git verify-commit <commit>
~~~

View signatures while reading history:

~~~bash
git log --show-signature --format=fuller -1
~~~

Verify a tag:

~~~bash
git verify-tag v2.0.0
~~~

Or view tag details together with its signature:

~~~bash
git tag -v v2.0.0
~~~

If a signature fails to verify, check:

- Has the corresponding public key been imported?
- Does the fingerprint match a trusted source?
- Was the commit signed with the configured private key?
- Are the GPG executable and agent available in the environment?
- Is the key expired, revoked, or no longer accepted?

A trust warning does not necessarily mean the cryptographic signature is invalid. Read the full output and check the key status against organizational policy.

## 7. Signing with SSH

Git can use an SSH key to sign commits and annotated tags. This is convenient if the team already manages SSH keys for repository access and wants to share the same key infrastructure.

SSH signing differs from using an SSH key to authenticate during git fetch or git push. A key used for server login is not automatically treated by Git as a signing key; you must configure gpg.format and the signing key.

### Step 1: create or choose an SSH key

If you do not have a suitable key yet, generate an Ed25519 key:

~~~bash
ssh-keygen -t ed25519 -C "developer@example.com" -f ~/.ssh/id_ed25519
~~~

Set a passphrase on the private key. If your organization issued a dedicated signing key, use that key and follow storage policies.

The public key has the .pub extension; the private key is the other file. Share only the public key. Never send or commit the private key to a repository.

### Step 2: load the private key into the SSH agent

On Unix-like environments:

~~~bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
~~~

On Windows with OpenSSH Agent, start the service per machine policy and load the key:

~~~powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
~~~

Confirm the key is loaded:

~~~bash
ssh-add -l
~~~

If Git cannot locate ssh-keygen, configure gpg.ssh.program to point to the appropriate executable in your environment. Executable paths can differ across Windows, macOS, and Linux.

### Step 3: configure Git for SSH signing

Select SSH as the format:

~~~bash
git config --global gpg.format ssh
git config --global user.signingKey ~/.ssh/id_ed25519.pub
~~~

This example specifies the public key path and assumes the corresponding private key is already loaded in the SSH agent. Git invokes the SSH signing program to create signatures; the private key must be accessible via your agent or key mechanism.

If you only want automatic commit signing:

~~~bash
git config --global commit.gpgsign true
~~~

If you want automatic annotated tag signing:

~~~bash
git config --global tag.gpgSign true
~~~

### Step 4: create a commit or tag with an SSH signature

~~~bash
git commit -S -m "fix: validate signed payload"
git tag -s v2.1.0 -m "Release v2.1.0"
~~~

Git uses SSH signing because gpg.format is set to ssh. The -S flag is used for both GPG and SSH; configuration selects the format.

## 8. Setting up allowed signers to verify SSH signatures

To verify an SSH signature, Git needs to know which public keys are permitted and which principals are associated with each key. The allowed signers file lists principals alongside public keys.

Example entry:

~~~text
developer@example.com namespaces="git" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExamplePublicKeyMaterial
~~~

Replace the email, key type, and public key body with real values. The example string above illustrates format only and is not a usable key.

Create the allowed signers file in your personal configuration directory, then set:

~~~bash
git config --global gpg.ssh.allowedSignersFile ~/.ssh/allowed_signers
~~~

The principal is usually tied to the commit identity email accepted by the organization. The namespaces="git" option restricts this key entry to the Git signing namespace. Without a matching allowed signers file, Git may be unable to verify SSH signatures even if the public key exists on the machine.

The allowed signers file is a verifier's trust policy. It is not a private key and does not need to live inside the repository. Teams can distribute this file through administrative configuration or a controlled trusted source.

### Checking SSH signatures

~~~bash
git verify-commit HEAD
git verify-tag v2.1.0
git log --show-signature -1
~~~

If verification fails, check:

- Is gpg.format set to ssh?
- Does gpg.ssh.allowedSignersFile point to an existing, readable file?
- Does the principal in the file match the checked identity?
- Does the public key in the file match the key that signed the object?
- Does the entry include the right namespace?
- Has the key been revoked according to verification config?

## 9. Revoking SSH and GPG keys

When a private key is exposed, lost, or its owner leaves the organization, trust for that key must be revoked.

### For SSH

Git supports an SSH revocation file via gpg.ssh.revocationFile. This file can use OpenSSH's Key Revocation List (KRL) format.

Example creating a KRL from a revoked public key:

~~~bash
ssh-keygen -k -f ~/.ssh/revoked_keys.krl ~/.ssh/compromised_key.pub
~~~

Configure Git to use the file:

~~~bash
git config --global gpg.ssh.revocationFile ~/.ssh/revoked_keys.krl
~~~

During verification, Git can check signatures against revoked keys and flag them invalid per the revocation data. The revocation file must be kept updated and distributed to verifying machines.

### For GPG

GPG provides OpenPGP key/certificate revocation mechanisms. The key owner can generate a revocation certificate using the GPG workflow and publish it through an appropriate key distribution channel. Verifiers must refresh their keyrings to receive the updated revocation status.

Revoking a key does not automatically erase previously signed commits or tags. It changes the trust status of the key during verification. Organizations must define the cutoff time after which signatures from a key are no longer accepted and how to handle previously signed releases.

## 10. Automatically signing commits and tags

If policy requires all new commits by a user to be signed:

~~~bash
git config --global commit.gpgsign true
~~~

If new annotated tags should be signed automatically:

~~~bash
git config --global tag.gpgSign true
~~~

These two settings are independent. You can auto-sign commits while only signing release tags, or require both.

Set them locally if only the current repository requires them:

~~~bash
git config --local commit.gpgsign true
git config --local tag.gpgSign true
~~~

Inspect configuration sources:

~~~bash
git config --show-origin --show-scope --get commit.gpgsign
git config --show-origin --show-scope --get tag.gpgSign
git config --show-origin --show-scope --get gpg.format
git config --show-origin --show-scope --get user.signingKey
~~~

If a CI environment creates commits or tags, supply the signing key to the runner via a secret store or centralized signing service. Never place private keys into the source tree, public artifacts, or pipeline logs.

## 11. Verifying signatures before review or release

Signatures are only useful if workflows actually check them. Reviewers can verify a commit:

~~~bash
git verify-commit <commit>
~~~

Verify a release tag:

~~~bash
git verify-tag v2.1.0
~~~

View history along with signature status:

~~~bash
git log --show-signature --oneline --decorate -10
~~~

A release workflow might require:

1. Release commits are signed by a key belonging to an authorized member or bot.
2. Tags are annotated and signed.
3. Verifiers possess the corresponding public keys or allowed signers file.
4. Fingerprints or principals are confirmed via a trusted source.
5. CI checks signatures before building artifacts or deploying.
6. Artifact metadata records the commit hash, tag, and verification outcome.

A valid signature does not prove code is secure or reviewed. It only verifies the signing source and object integrity. Security checks, code reviews, tests, and release approvals remain necessary.

## 12. Commit/tag signatures vs. signed push

Git also has a mechanism to sign a push operation:

~~~bash
git push --signed origin main
~~~

This creates a signed push certificate. It signs the ref update request sent to the server, allowing the server to record information about the sender and updated refs if the server supports this feature.

Comparison:

| Mechanism | Signed object | Purpose |
| --- | --- | --- |
| Signed commit | Commit object | Verifies the commit was signed and content is unaltered |
| Signed tag | Annotated tag object | Verifies release milestone and tag metadata |
| Signed push | Push certificate for ref update | Verifies details of the push request |

A push may contain signed commits, signed tags, or both; that does not automatically mean the push certificate itself is signed. Conversely, a signed push does not automatically sign commits in history.

## 13. What happens when commits are rewritten?

A signature is bound to the content and metadata of the commit object. If you use amend, rebase, or another operation that creates new commits, commit hashes change and the old signature no longer applies to the new commit.

For example:

~~~bash
git commit --amend
~~~

The amended commit is a new object. To re-sign it:

~~~bash
git commit --amend -S
~~~

Rebasing also recreates commits onto a new base; if policy requires signed commits, configure commit.gpgsign or re-sign the newly created commits. When a branch has been shared, rewriting history requires coordination and may require safe update mechanisms per team convention.

Signed tags should likewise be treated as immutable release milestones. If a tag is moved to another commit, the tag object and signature must be recreated; never arbitrarily overwrite published tags because users may already have fetched and verified the earlier version.

## 14. Common errors when signing and verifying

### Git cannot find GPG

Check:

~~~bash
gpg --version
git config --show-origin --get gpg.program
~~~

Ensure GPG is on PATH or gpg.program points to the right executable. If Git runs inside an IDE or CI, check the PATH of that specific process.

### Signing key not found

For GPG:

~~~bash
gpg --list-secret-keys --keyid-format=long
git config --show-origin --get user.signingKey
~~~

For SSH:

~~~bash
ssh-add -l
git config --show-origin --get user.signingKey
~~~

Confirm the corresponding private key is available in the GPG agent or SSH agent and the key is configured properly.

### SSH signature fails to verify

Check the allowed signers file:

~~~bash
git config --show-origin --get gpg.ssh.allowedSignersFile
~~~

Ensure the file exists, has the right format, and contains the matching principal and public key. Adding a public key to a Git hosting account for access does not automatically make it an allowed signer in local Git verification.

### Commit shows invalid signature after rebase

Rebase creates new commits with new hashes and either new signatures or no signatures depending on configuration. Verify the new commits; never use verification output from an old commit to claim the new commit is valid.

### Another machine reports a missing public key

Recipients need to import the GPG public key or have the SSH entry in allowedSignersFile. Share public keys and fingerprints through a trusted source; never share private keys.

## 15. Sample workflow for a signed release

Suppose a team prepares to release v3.0.0 using GPG:

### Step 1: confirm configuration and keys

~~~bash
git config --show-origin --get gpg.format
git config --show-origin --get user.signingKey
gpg --list-secret-keys --keyid-format=long
~~~

Confirm the key and fingerprint match organizational standards.

### Step 2: create a signed release commit

~~~bash
git commit -S -m "chore: prepare v3.0.0"
git verify-commit HEAD
~~~

### Step 3: create a signed annotated tag

~~~bash
git tag -s v3.0.0 -m "Release v3.0.0"
git verify-tag v3.0.0
~~~

### Step 4: push branch and tag

~~~bash
git push origin main
git push origin v3.0.0
~~~

### Step 5: verify after sharing

~~~bash
git fetch origin --tags
git verify-commit origin/main
git verify-tag v3.0.0
~~~

In production workflows, verify the release commit using a specific hash or confirmed release ref; origin/main may have advanced after the push. CI should verify the exact commit and tag from which artifacts are built.

## 16. Common misconceptions

### Do signed commits encrypt content?

No. Signatures protect integrity and help authenticate the signing origin. Commit contents remain readable as usual.

### Does seeing Good signature guarantee the right person?

Not by itself. You must verify the GPG fingerprint or SSH principal and public key via a trusted source. A cryptographically valid signature and a trusted identity are two separate checks.

### Can a lightweight tag be signed?

Not with Git's signed tag mechanism. Create an annotated tag with -a or a signed annotated tag with -s.

### Does an SSH key used to clone over SSH automatically sign commits?

No. You must set gpg.format to ssh, configure user.signingKey, and ensure the private key is available for SSH signing.

### Does pushing signed commits automatically sign the push?

No. Signed commits and signed pushes are separate mechanisms. To sign a push certificate, pass --signed if the remote supports it.

### Does rebase preserve old signatures?

Recreated commits get new hashes and need new signatures if policy requires them. Old signatures remain attached to the old commits.

## 17. Self-check

A team requires commits on main and release tags to be signed. One member uses GPG, while another uses SSH. CI must verify both signature types before building artifacts.

Answer the following:

1. Which setting chooses OpenPGP or SSH?
2. Which commands create a signed commit and a signed annotated tag?
3. Why cannot a lightweight tag carry a tag signature?
4. What must a verifier do to trust a GPG public key?
5. Which file does SSH signing require to map principals to public keys?
6. Why can a rebase cause an old commit signature to no longer apply to the new commit?
7. Does a signed push replace signed commits?

**Hint:** Use gpg.format to choose openpgp or ssh. Use git commit -S and git tag -s to sign. Signed tags require an annotated tag object. For GPG, import the public key and verify its fingerprint through a trusted channel. For SSH, configure gpg.ssh.allowedSignersFile. Rebase creates new commit objects, so the old signature does not sign the new object. A signed push signs the ref update request, not commit contents.

## Conclusion

Git supports signing commits and annotated tags with OpenPGP/GPG or SSH. Configure the format and key properly, protect private keys, sign the required objects, and verify them with verify-commit or verify-tag. Recipients must verify GPG fingerprints or SSH principals/public keys via a trusted source; a cryptographically valid signature alone does not prove identity. Commit signatures, tag signatures, and signed pushes protect different objects. When commits or tags are rewritten, create and verify new signatures before republishing the milestone.
