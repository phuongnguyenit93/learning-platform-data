# Distinguishing Commit Identity from Remote Access Authentication

When using Git, you may see a name and email appear in commit history, while Git may also prompt you to log in when pushing to or fetching from a server. Both involve identity, yet they serve different purposes. The name and email in a commit describe who is recorded as creating the change; remote authentication helps the server identify the client, after which authorization decides whether the client is permitted to access the repository.

If you confuse these two concepts, you might configure the right email yet still fail to push, or log in successfully only for commits to display the wrong author name. This lesson belongs to the **Repository Security** chapter of the SOURCE_CONTROL_GIT module. The module covers the working tree, staging area, commit, history, branch, merge, rebase, remote, and tag; understanding identity and authentication properly keeps history informative and remote operations protected.

## 1. Two different questions

When working with Git, separate two questions:

- **Who is recorded on the commit?** Git stores the author and committer name/email in the commit's metadata.
- **How is the client authenticated and what permissions are granted?** The server identifies the user or client via HTTPS token/OAuth, SSH key, or a provider mechanism, then checks the corresponding read/write permissions.

| Concept | Where is it stored or checked? | Purpose |
| --- | --- | --- |
| Author name/email | Commit metadata | Records the person who originally wrote the change |
| Committer name/email | Commit metadata | Records the person who created the current commit |
| Commit signature | Signature attached to the commit object | Verifies whether the commit was signed by the corresponding key and whether its content was altered |
| HTTPS credential | Credential helper, token/OAuth, or login mechanism | Authenticates when accessing a remote over HTTPS |
| SSH key | Private key on the client machine and public key registered on the service | Authenticates the client when accessing a remote over SSH |
| Server identity | TLS certificate or SSH host key | Helps the client verify it is connecting to the right server |

Configuring an author/email does not grant push permissions. Conversely, successful remote authentication does not automatically change a commit's author/email.

## 2. Author and committer in a commit

A Git commit stores two sets of identity information:

- **Author**: the person recorded as having originally written the change.
- **Committer**: the person who created the current commit object.

In typical workflows, the same person is both author and committer. However, during a cherry-pick, rebase, patch application, or committing on someone else's behalf, the two identities can differ.

Inspect commit details:

~~~bash
git log -1 --format=fuller
~~~

The output may look similar to:

~~~text
commit 8ac41d2...
Author:     Nguyen An <an@example.com>
AuthorDate: Tue Nov 17 09:30:00 2026 +0700
Commit:     Tran Binh <binh@example.com>
CommitDate: Tue Nov 17 10:15:00 2026 +0700

    Fix invoice calculation
~~~

Author shows who wrote the fix; Commit shows who created the current commit. The two timestamps can also differ.

### Configuring the default identity

Set a name and email for all of a user's repositories:

~~~bash
git config --global user.name "Nguyen An"
git config --global user.email "an@example.com"
~~~

Set them specifically for the current repository:

~~~bash
git config --local user.name "Nguyen An"
git config --local user.email "an@company.example"
~~~

Local configuration takes higher precedence than global configuration within that repository. This is useful when you use one machine for multiple projects or need a separate work email.

Check the active values currently in use:

~~~bash
git config --get user.name
git config --get user.email
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

The command with --show-origin reveals which configuration file each value comes from. You can list all configuration entries along with their sources:

~~~bash
git config --list --show-origin
~~~

This list may contain URLs or sensitive configuration details; review it carefully and mask private data before sharing the output.

### Confirming the effective identity before committing

Git can display the exact identity it will use for the author and committer:

~~~bash
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
~~~

This is a useful check before creating a commit in repositories with multiple configurations or environment variables.

### Preventing Git from guessing your identity

If you want Git to require explicit configuration rather than inferring a name/email from your operating system account:

~~~bash
git config --global user.useConfigOnly true
~~~

When no suitable user.name or user.email is configured, creating a commit fails and prompts you to configure one. This option helps prevent commits with an unintended identity.

## 3. Configuration sources and identity overrides

Git reads configuration from multiple scopes, such as system, global, local, and worktree. More specific scopes typically override general values. Command-line flags and environment variables can also supply values for a single invocation.

Several environment variables directly affect commit metadata:

| Variable | Effect |
| --- | --- |
| GIT_AUTHOR_NAME | Author name |
| GIT_AUTHOR_EMAIL | Author email |
| GIT_AUTHOR_DATE | Author date |
| GIT_COMMITTER_NAME | Committer name |
| GIT_COMMITTER_EMAIL | Committer email |
| GIT_COMMITTER_DATE | Committer date |

For example, a script can set a custom identity for a single commit in a POSIX shell:

~~~bash
GIT_AUTHOR_NAME="Release Bot" GIT_AUTHOR_EMAIL="release-bot@example.com" GIT_COMMITTER_NAME="Release Bot" GIT_COMMITTER_EMAIL="release-bot@example.com" git commit -m "Prepare release metadata"
~~~

In PowerShell, set the environment variables before the command and remove them afterward:

~~~powershell
$env:GIT_AUTHOR_NAME = "Release Bot"
$env:GIT_AUTHOR_EMAIL = "release-bot@example.com"
$env:GIT_COMMITTER_NAME = "Release Bot"
$env:GIT_COMMITTER_EMAIL = "release-bot@example.com"
git commit -m "Prepare release metadata"
Remove-Item Env:GIT_AUTHOR_NAME
Remove-Item Env:GIT_AUTHOR_EMAIL
Remove-Item Env:GIT_COMMITTER_NAME
Remove-Item Env:GIT_COMMITTER_EMAIL
~~~

If a commit shows an unexpected name or email, inspect both the configuration and the environment of your terminal, IDE, script, or CI. Do not look solely at the global config file and assume it is the only source.

## 4. Author, committer, and commit signatures are not the same

Author/committer metadata consists of plain text strings recorded in the commit. Git does not automatically verify that the person declaring a name or email actually owns that identity.

A commit signature is an additional mechanism. The commit creator uses a signing key to sign the commit object; others can verify the signature using a public key or a trusted key list.

A signature verifies that the commit was signed by the corresponding key and that the signed commit content has not been altered after signing. A signing key can be tied to a person or account according to an organization's policy.

A signature does not replace remote authentication. You still need remote access permissions to push, and a validly signed commit does not automatically grant write access to a repository.

### Signing commits with GPG

After installing and configuring a GPG key, specify the signing key:

~~~bash
git config --global user.signingkey <GPG-KEY-ID>
git config --global commit.gpgsign true
~~~

Create a signed commit:

~~~bash
git commit -S -m "Add invoice validation"
~~~

If commit.gpgsign is enabled, new commits are signed by default.

### Signing commits with SSH

Git versions that support SSH signing can use an SSH key to sign commits:

~~~bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global commit.gpgsign true
git commit -S -m "Add invoice validation"
~~~

In PowerShell, replace the key path with the actual public key path:

~~~powershell
git config --global user.signingkey "$env:USERPROFILE/.ssh/id_ed25519.pub"
~~~

A key used for commit signing plays a different role from using a private key for SSH authentication to a remote. Some services allow registering the same key for multiple purposes, but you should follow your organization's security policy and key management workflow.

### Verifying signatures

View a commit and its signature status:

~~~bash
git log -1 --show-signature
~~~

Verify a specific commit:

~~~bash
git verify-commit <commit>
~~~

Verification results depend on the public key, trust configuration, and installed signing tools. Simply seeing Author/Committer metadata does not mean a commit has been signed.

## 5. Authentication when accessing a remote

A remote is a repository on a server or another repository address. View configured remotes:

~~~bash
git remote -v
~~~

A remote can use an HTTPS or SSH URL. The protocol in the URL determines which authentication mechanism is typically used.

### HTTPS: token, OAuth, or credential manager

An HTTPS URL typically looks like:

~~~text
https://git.example.com/team/project.git
~~~

When fetching or pushing, the server may require authentication via a personal access token (PAT), OAuth, or a provider-supported login flow. Git commonly integrates a credential helper to store or retrieve credentials without prompting every time.

Check the configured credential helpers:

~~~bash
git config --show-origin --get-all credential.helper
~~~

On Windows, Git Credential Manager is commonly used to launch the login flow and store credentials in the operating system's secure vault. Setup details depend on your Git version and organization.

When working with tokens, you should:

- Choose the minimum permissions required, such as read-only access if you only fetch.
- Set an expiration and rotate tokens according to your organization's policy.
- Store them using an approved credential manager or secret store.
- Never embed tokens directly in remote URLs, scripts, logs, or shell history.
- Never include tokens in screenshots or support outputs.

Avoid using a regular account password when the provider requires a token or OAuth. Specific policies depend on the Git platform in use.

### SSH: public key and private key

An SSH URL typically looks like:

~~~text
git@git.example.com:team/project.git
~~~

SSH uses a key pair:

- **Private key** on the client machine, which must be kept secret.
- **Public key** registered in your account or permission management system on the Git service.

When connecting, the client proves ownership of the private key without sending the private key to the server. An SSH agent can hold unlocked keys in memory to reduce repeated passphrase prompts.

List keys currently loaded into the agent:

~~~bash
ssh-add -l
~~~

Add a private key to the agent if needed:

~~~bash
ssh-add ~/.ssh/id_ed25519
~~~

In Windows PowerShell, the path typically looks like:

~~~powershell
ssh-add "$env:USERPROFILE/.ssh/id_ed25519"
~~~

Test the SSH connection using the command appropriate for your organization's hostname and Git service. A general example:

~~~bash
ssh -T git@git.example.com
~~~

A success message typically indicates that the account was recognized; some servers do not grant an interactive shell, so the command not opening a shell does not mean authentication failed.

### Verifying the server is a separate step

With HTTPS, a TLS certificate helps the client verify the server. With SSH, the host key and the known_hosts file help the client verify the server endpoint.

This is **server identity** verification, which is different from the server authenticating **client identity** using a token or public key. Never bypass host key warnings or disable TLS checks just to make a command work; verify the fingerprint or certificate through a trusted channel.

## 6. Successful authentication does not mean write permission

Someone can log in successfully and still be unable to push. Authentication answers the question "who are you?"; authorization answers the question "what are you allowed to do?".

For example:

- The credential is valid, but the account only has read access.
- The account has repository write access, but the target branch is protected.
- The token has expired or lacks a required scope.
- The SSH key is valid, but has not been granted access to the repository.
- Review rules require a pull request instead of pushing directly to the main branch.
- The server rejects the update because the branch already has newer commits or due to a hook policy.

When a push fails, read the message carefully to distinguish between authentication errors, authorization errors, branch protection, and non-fast-forward rejections. Do not change user.name/email to fix a remote permission error when the root cause lies in a token, SSH key, or policy.

## 7. Checking configuration before committing and pushing

A useful verification workflow:

~~~bash
git status
git branch --show-current
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
git config --show-origin --get user.name
git config --show-origin --get user.email
git remote -v
~~~

Before sharing output, check whether the remote URL embeds a username/token or internal information. Mask sensitive details if you send logs to others.

After creating a commit, verify the actual metadata:

~~~bash
git log -1 --format=fuller
~~~

When signature verification is needed:

~~~bash
git log -1 --show-signature
git verify-commit HEAD
~~~

When you need to test access permissions, perform a read operation such as fetch or ls-remote against the project remote. A test push can mutate state on the server, so use a test branch or a workflow approved by your team.

## 8. Fixing the identity of an existing commit

Configuring user.name and user.email only affects commits created afterward. It does not alter the metadata of older commits.

If the latest commit has not been shared and you want to fix its author, you can run:

~~~bash
git commit --amend --reset-author
~~~

This command recreates the current commit, sets the author to the current configured identity, and updates the committer metadata. If you only want to replace the author with a specific value, you can use:

~~~bash
git commit --amend --author="Nguyen An <an@example.com>"
~~~

Verify the result afterward:

~~~bash
git log -1 --format=fuller
~~~

Amending changes the commit hash. If the commit has already been pushed or others have based work on it, rewriting history requires coordinating with your team and may require a force-push according to policy. Do not arbitrarily rewrite shared branch history.

If you need to fix multiple older commits, that is a history-rewriting operation (such as an interactive rebase or a history-filtering tool). Back up first, agree on the scope, and prepare a plan to update existing clones before proceeding.

## 9. Email identity and hosting platforms

Many Git platforms use the email in a commit to link activity to a user account. If the commit email is unverified or has not been added to your account, the web UI may not attribute the commit to the right profile even though the commit itself is valid.

You can use a private email address or a platform-provided no-reply address if your account policy supports it. In that case, the commit still stores the configured email, and the platform can map that email to your account.

Key distinctions to keep in mind:

- Git stores the email as metadata; Git does not send emails to verify remote access permissions.
- Hosting platforms may use the email to display attribution.
- Push authentication still uses a token/OAuth or an SSH key.
- A commit signature is an additional verification layer, not a replacement for an email or credential.

If the author name displays incorrectly in the web UI, check the metadata with git log first, then check your verified emails on the platform. Do not generate a new token if the issue is only email attribution.

## 10. Troubleshooting common issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Commit displays the wrong name or email | user.name/email, config scope, or environment variable override | Use git var, git config --show-origin, and inspect environment variables |
| Push over HTTPS repeatedly prompts for login | Expired credential, unconfigured helper, or wrong token | Re-authenticate via credential manager, check token permissions and expiration |
| Push over SSH reports Permission denied (publickey) | Private key not loaded, public key not registered, or SSH using the wrong key | Check ssh-add -l, ssh config, and account permissions |
| Login succeeds but push is rejected | Account has read-only access or branch protection is enabled | Check role, branch policy, and pull request workflow |
| Commit has the right author but a different committer | Cherry-pick, rebase, or another person created the new commit | Inspect git log --format=fuller and confirm how the commit was created |
| Platform does not link commit to account | Commit email is unverified or not associated with the account | Check email attribution settings on the hosting service |
| Commit signature cannot be verified | Missing public key, trust configuration, or wrong signing format | Check signing key, allowed signers/keyring, and git verify-commit |
| SSH warns that the host key has changed | Server rotated its key or connected to the wrong endpoint | Verify the fingerprint with an administrator before updating known_hosts |

## 11. Identity and authentication flow diagram

~~~mermaid
flowchart TD
    A[Prepare commit] --> B[Git reads user.name and user.email]
    B --> C[Author and committer are recorded in the commit]
    C --> D{Is commit signing enabled?}
    D -- Yes --> E[Sign commit with GPG or SSH signing key]
    D -- No --> F[Commit has no signature]
    E --> G[Commit resides in local history]
    F --> G
    G --> H[Push or fetch over remote]
    H --> I{Transport}
    I -- HTTPS --> J[Token or OAuth via credential helper]
    I -- SSH --> K[Private key proves ownership]
    J --> L[Server authenticates client]
    K --> L
    L --> M[Server checks repository permissions and branch policy]
    M --> N[Allow or reject operation]
~~~

Before finishing, verify for yourself:

1. Are the author and committer set to the right person and email per project policy?
2. Is any local configuration or environment variable overriding the global setting?
3. Does the remote use HTTPS or SSH, and is the corresponding credential configured?
4. Have you distinguished between client authentication, server verification, and repository authorization?
5. If commit signatures are required, are the signing key and verification workflow configured?
6. Has the commit already been shared before you amend or rewrite history?

Commit identity shows in history who wrote and who created a commit. Remote authentication controls which credentials allow a client to connect; authorization determines whether the client can read or write. Commit signatures provide additional cryptographic proof of origin and integrity. By keeping these three layers distinct, you can configure Git accurately, diagnose push errors at their root cause, and maintain trustworthy collaboration history.

## References

- [Git documentation: git-config](https://git-scm.com/docs/git-config) — configuring user.name, user.email, and configuration scopes.
- [Git documentation: git-var](https://git-scm.com/docs/git-var) — inspecting effective author and committer identities.
- [Git documentation: git-commit](https://git-scm.com/docs/git-commit) — author, amend, and commit signing.
- [Git documentation: gitcredentials](https://git-scm.com/docs/gitcredentials) — credential helpers and transport authentication.
- [Git documentation: git-push](https://git-scm.com/docs/git-push) — updating remote refs.
- [Git documentation: git-verify-commit](https://git-scm.com/docs/git-verify-commit) — verifying commit signatures.
