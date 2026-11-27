# HTTPS Authentication with Tokens and Credential Managers

When working with a remote repository over HTTPS, Git needs to authenticate the user before performing operations such as `clone`, `fetch`, or `push` on private repositories. Many Git services no longer accept account passwords for Git operations over HTTPS; instead, users must use a personal access token (PAT), OAuth, or a provider-supported authentication mechanism.

A token can be entered whenever Git prompts for credentials, but you should not have to re-enter it on every operation. A credential manager helps store and supply credentials through the operating system's secure vault. When configured properly, a team can use HTTPS conveniently while still controlling token expiration, permissions, and lifecycle.

In Git source code hosting services, protecting credentials is part of repository security. A token with write permissions can allow someone else to modify source code, create releases, or access private data. Therefore, grant least privilege, store tokens in the right place, avoid putting tokens in URLs or configuration files, and revoke them immediately if exposure is suspected.

## 1. How does HTTPS authentication work in Git?

When a remote uses an HTTPS URL, Git communicates with the Git service over HTTPS. If the repository requires authentication, the server requests credentials. Depending on the service, credentials may consist of a username and PAT, an OAuth token, or another compatible authentication mechanism.

Example HTTPS remote:

```bash
git remote -v
git remote add origin https://github.com/example-team/payment-service.git
```

When running `git fetch origin` or `git push origin main`, Git may prompt for login credentials. For services that use a PAT over HTTPS:

- The username is typically the account name on the Git service.
- The password entered is the PAT, not the account login password.

Some providers use OAuth via a browser and credential manager; in that case, the user signs in through the provider's authentication page and does not need to manually create a PAT. Follow the mechanism supported by your organization's Git service.

### Why not use the account password?

Tokens allow assigning separate permissions and expiration dates specifically for Git activity. If a token is compromised, you can revoke that token without changing your account password. One PAT might only be allowed to read certain repositories, while another token has write access for a project group. This permission model limits the blast radius when credentials are exposed.

Not every service has the same token policy. Some use fine-grained PATs, some use group tokens or deploy tokens, and some prefer OAuth. Read your provider's and organization's policies before creating a token.

## 2. What is a personal access token?

A personal access token (PAT) is a secret string representing a user or application identity when accessing a Git service. A PAT is typically configured with the following attributes:

- **Scope/permissions:** permissions to read repositories, write repositories, manage workflows, packages, or other resources.
- **Repository access:** all repositories or only selected repositories, depending on the provider.
- **Expiration:** an expiration date or lifetime defined by organizational policy.
- **Owner:** the user account, group, or service identity that issued the token.
- **Status:** active, expired, revoked, or restricted by security policy.

A PAT is a secret equivalent to a login credential. Anyone possessing the token and appropriate permissions can perform actions within the token's granted scope. Never share tokens via chat, email, issues, pull requests, screenshots, or documentation.

### Choosing least privilege

Before creating a PAT, determine the operations you need to perform:

| Need | Permissions to consider |
| --- | --- |
| Clone or fetch a private repository | Required repository read permission |
| Push commits to a repository | Repository content read and write permissions |
| Download private packages | Corresponding package read permission |
| Publish packages | Corresponding package write permission |
| Run or manage workflows | Grant workflow permissions only if genuinely required |

Exact permission names differ across GitHub, GitLab, Azure DevOps, and internal Git servers. Do not select all permissions just to avoid authentication errors. If a push fails due to missing permissions, identify the exact permission to add rather than granting broad administrative privileges.

### Token expiration and rotation

Prefer tokens with an expiration matching your needs and organizational policy. A token used for a short-lived task should have a short lifetime; long-lived tokens need a clear owner, rotation schedule, and revocation procedure.

When creating a new token to replace an old one:

1. Create the new token with least-privilege permissions and an appropriate expiration.
2. Update the credential manager or secret store for the relevant environment.
3. Verify `fetch`/`push` or CI tasks with the new token.
4. Revoke the old token after confirming all consumers have switched over.

Do not let an unexpected token expiration disrupt pipelines or team workflows. Track expiration dates and communicate rotations following internal procedures.

## 3. What is a credential manager?

Git supports credential helpers to exchange authentication information with an external program. When a service requests login, Git asks the helper whether a matching credential is already available. If not, Git may prompt the user; after successful authentication, the helper can store the credential for future reuse.

Credential helpers can be configured in several forms:

| Helper | How it stores | Notes |
| --- | --- | --- |
| Git Credential Manager (`manager`) | Integrates with the OS secure vault and supported provider OAuth flows | Convenient choice for many desktop environments and popular Git services |
| `osxkeychain` | macOS Keychain | Uses the macOS credential vault |
| `libsecret` | Secret Service on Linux | Requires a compatible secret environment/vault |
| `cache` | Temporary in-memory storage for a set duration | Does not persist long-term; prompts again once expired |
| `store` | Plain text file on disk | Can store credentials in plaintext; unsuitable for sensitive PATs |

Do not confuse a credential helper with storing a token inside a remote URL or configuration file. A helper is designed to supply credentials on demand, whereas a token embedded in a URL can surface in `.git/config`, logs, shell history, or diagnostic output.

## 4. Git Credential Manager (GCM)

Git Credential Manager is a cross-platform credential helper for Git. GCM can integrate with Git providers to perform browser/OAuth sign-in or handle credentials via supported mechanisms, then store them in the operating system's secure vault.

Common storage backends:

- Windows: Windows Credential Manager.
- macOS: Keychain.
- Linux: Secret Service/libsecret or a security backend appropriate for the environment.

The exact backend depends on the GCM version, operating system, and configuration. If a Linux environment lacks an available secret service, set up a supported backend or use an organization-approved authentication method; avoid falling back to plaintext PAT storage as a quick fix.

### Checking GCM

```bash
git credential-manager --version
```

If the command is not found, GCM may not be installed or may not be on PATH. Some older versions use the command name `git-credential-manager-core`; the command name depends on the installed version.

### Configuring GCM as the credential helper

On modern GCM versions:

```bash
git credential-manager configure
```

This command configures Git to integrate with GCM. In some environments where GCM is already installed, you can set the helper directly:

```bash
git config --global credential.helper manager
```

Verify the configuration:

```bash
git config --show-origin --get-all credential.helper
```

Do not configure multiple helpers haphazardly. Git may invoke declared helpers in sequence; an older helper might keep returning the wrong credential or save credentials in an unintended location. Inspect all configured values and sources before making changes.

### First-time login

After configuring GCM, use the HTTPS remote normally:

```bash
git remote set-url origin https://github.com/example-team/payment-service.git
git fetch origin
```

If the provider supports OAuth via GCM, a browser window may open for the user to sign in and authorize access. If the provider requires a PAT, enter the username as instructed and paste the PAT into the password field when prompted. Do not put the PAT into commands or URLs.

After successful authentication, GCM saves the credential in the corresponding secure vault. Subsequent `fetch` or `push` operations typically do not prompt again until the credential expires, is revoked, or policy requires re-authentication.

## 5. Using a PAT with an HTTPS remote

General workflow example when a provider requires a PAT:

### Step 1: Create a PAT on the Git service

Open the provider's token management page and create a token following your organization's guidelines. Select:

- The repository or group of repositories needing access.
- Minimum read/write permissions for the job.
- A reasonable expiration period.
- SSO or organization approval if required by the provider.

Many services display the full token only once at creation time. Copy the token directly into the secure input prompt or let the credential manager handle the authentication flow; do not save it temporarily in a text file or shared clipboard.

### Step 2: Confirm the remote does not contain a token

```bash
git remote -v
```

The URL should look like:

```text
https://github.com/example-team/payment-service.git
```

Do not use forms that embed secrets such as:

```text
https://USERNAME:TOKEN@github.com/example-team/payment-service.git
```

A URL containing a token can be written into repository configuration, CI logs, shell history, or diagnostic output. If a token was ever embedded in a URL, remove it from the configuration and revoke that token because it may already have been saved elsewhere.

### Step 3: Perform an operation requiring authentication

```bash
git fetch origin
```

If Git asks for a username and password, enter the account username and use the PAT in the password field. If GCM opens a browser, complete the provider's login flow. Never pass a PAT in command-line arguments.

### Step 4: Verify the operation

```bash
git status -sb
git fetch origin
```

If write access is needed, verify with a push operation permitted by your team's workflow, such as pushing a committed feature branch. Do not create dummy commits or test pushes to a protected branch just to check credentials.

## 6. Other credential helpers

GCM is usually a good choice for developer machines with a supported secure backend. Some environments may use other helpers.

### macOS Keychain

```bash
git config --global credential.helper osxkeychain
```

Git uses Keychain to store and retrieve credentials. Users can manage or delete related entries in the Keychain Access app according to machine policy.

### Linux Secret Service/libsecret

If Git is installed with the `libsecret` helper, you can configure:

```bash
git config --global credential.helper /usr/lib/git-core/git-credential-libsecret
```

The actual path varies by distribution and how Git was installed. Check which helper is present on the machine and use the exact path provided by the installation package. This backend typically requires an available Secret Service, such as a desktop environment keyring.

### Credential cache

```bash
git config --global credential.helper 'cache --timeout=3600'
```

Cache keeps credentials in memory for 3,600 seconds. After that period, Git may prompt again. This is a temporary option, not long-term storage. Do not set an overly long timeout if security policy requires a short lifetime.

### Credential store

```bash
git config --global credential.helper store
```

The `store` helper can write credentials to a file such as `~/.git-credentials` in plaintext. Any process or user with read access to that file can obtain the token. Do not use `store` to save sensitive PATs on shared machines or unprotected environments. If a token has already been stored this way, switch to a secure helper and revoke/rotate the token per organizational policy.

## 7. Distinguishing credential helpers from username configuration

Git can store a default username separately from the credential helper:

```bash
git config --global credential.username developer
```

This setting only hints at the username; it does not store a PAT and does not grant access permissions. You can scope a username to a specific host using URL-specific configuration when working with multiple accounts. Check the exact URL and configuration syntax in Git documentation before applying it.

When you have multiple accounts on the same host, Git may reuse a credential already saved for that host. You can instruct Git to distinguish credentials by repository path:

```bash
git config --global credential.useHttpPath true
```

When `useHttpPath` is enabled, Git includes the path in the credential context instead of using only the protocol and host. This can be helpful when the same host serves multiple repositories or multiple identities, though storage behavior still depends on the credential helper and provider policy. Do not enable this option merely to mask the fact that the wrong account is being used; inspect the stored credential first and sign in again with the right identity.

## 8. Managing and revoking credentials

When a credential expires, is revoked, or uses the wrong account, Git may repeatedly prompt or return an authentication error. You must remove the old credential from the helper and re-authenticate.

Git provides a protocol to ask the helper to forget credentials by context. For example, in a POSIX shell, you can pass the host to remove without putting any token in the command:

```bash
printf "protocol=https\nhost=github.com\n\n" | git credential reject
```

This asks the helper to delete the credential matching that host; the outcome depends on the helper and credential context. If using GCM, you can also delete the host account/credential in the account management UI or the OS security vault. On Windows, check Windows Credential Manager; on macOS, check Keychain Access; on Linux, check Secret Service/keyring or the configured backend.

After removing the old credential, run again:

```bash
git fetch origin
```

Git will prompt for re-authentication or launch the login flow. Ensure the new token has the right repository access, scope, and expiration.

### When must a token be revoked immediately?

Revoke a token immediately if:

- The token appears in a commit, issue, pull request, log, or remote URL.
- The token was accidentally sent via chat/email or shared with an unauthorized person.
- A device holding the token is lost or the account shows signs of compromise.
- It is no longer clear where the token is being used or who manages it.

After revoking:

1. Check the Git service's activity logs for unusual access.
2. Create a replacement token with least privilege if the work still needs it.
3. Update credential managers and CI secret stores.
4. Remove the token from any storage you control and clean Git history if the token was ever committed.
5. Check forks, clones, caches, logs, and artifacts that may have contained the token.

Removing a token from a new commit does not invalidate the old token. The first step is always to revoke the token at the provider; rewriting history is only a follow-up step to clean up remaining traces.

## 9. Never embed tokens in URLs, scripts, or configuration

Do not use patterns like the following:

```bash
# Don't do this: the token appears in the URL and may be written to config/logs
git remote set-url origin https://user:token@example.com/team/repo.git

# Don't do this: the token sits directly in the command or script
git clone https://TOKEN@example.com/team/repo.git
```

Do not place tokens in:

- `.git/config`, `.gitmodules`, `.git-credentials`, or committed configuration files.
- Shell history, build scripts, Dockerfiles, or manifest files.
- CI logs, debug output, error messages, or printed URLs.
- Unprotected environment variables or publicly downloadable artifacts.

For pipelines, use the CI/CD secret store and short-lived credential issuance if supported by the provider. Avoid printing secret variables to logs. Grant permissions only to the required repositories and actions; separate read-only tokens used for checkout from write-capable publish tokens if the pipeline has both stages.

## 10. Using HTTPS tokens in CI/CD

CI runners typically execute without an interactive user to type a token. Therefore, credentials must be supplied via a secret store or provider-supported identity federation.

General workflow:

1. Create a secret or connect a service identity in the CI system.
2. Restrict permissions by repository and operation.
3. Inject the secret into the step requiring Git access via the CI's secure mechanism.
4. Use an HTTPS remote that contains no token.
5. Run fetch/clone/push according to the granted permissions.
6. Do not echo secrets, do not enable debug modes that print auth headers, and do not persist credentials in long-lived workspaces.
7. Revoke or rotate credentials on schedule and when the pipeline no longer needs them.

Illustrative remote configuration example:

```bash
git remote set-url origin https://github.com/example-team/payment-service.git
git fetch origin
```

The token is supplied by the secret store to the helper or runner's authentication mechanism rather than concatenated directly into the URL. How a secret is mapped to Git depends on the CI platform; use official actions/plugins or provider documentation to avoid leaking tokens into logs.

If CI only needs to clone/fetch, use a read-only credential. If a release step needs to push tags or update the repository, separate the write-capable credential and grant it only to trusted jobs. Never use a developer's long-lived personal PAT as the default credential for pipelines.

## 11. Comparing HTTPS tokens and SSH keys

Git can access remotes over HTTPS or SSH. The two methods have different authentication models:

| Criterion | HTTPS + token/OAuth | SSH key |
| --- | --- | --- |
| Credentials | PAT, OAuth, or provider-supported credential | Private and public key pair |
| Management | Credential manager or secret store | SSH agent, keychain, or secret store |
| Revocation | Revoke token per account/application | Delete/revoke registered public key or rotate key |
| Permission scope | Can be restricted by scope/repository depending on provider | Usually tied to an identity/key; repository permissions determined by the Git service |
| Automation | Easy to integrate with secret stores and OAuth flows | Well-suited for deploy keys or managed SSH identities |

HTTPS tokens are convenient when an organization standardizes on OAuth/GCM or needs tokens with fine-grained scopes and expirations. SSH works well when a team has a clear key management process. Neither method is safe if secrets are stored inside the repository or granted overly broad permissions.

## 12. Common authentication errors

| Error | Possible cause | Resolution |
| --- | --- | --- |
| `Authentication failed` | Wrong, expired, or revoked PAT, or wrong username | Check token status, clear old credentials, and re-authenticate |
| `Repository not found` even with correct URL | Account/token lacks read access to the private repository | Check repository access, organization membership, and SSO authorization |
| Fetch works but push is rejected | Token is read-only or branch is protected | Check write permissions and the team's pull request workflow |
| Git prompts for credentials on every operation | Helper is not configured, cannot save, or backend is unavailable | Check `credential.helper`, install/configure GCM or a secure backend |
| GCM does not open a browser | Missing browser, headless environment, or unsupported provider flow | Use an authentication method supported for that environment; do not switch to plaintext token storage |
| Logged into the wrong account | Helper is returning a cached credential for the same host | Clear the old credential in the helper/OS vault and sign in with the right account |
| CI clones successfully but push fails | Secret lacks write access or job is not granted the secret | Grant appropriate permissions to trusted jobs and check branch protection rules |
| Token exposed in URL/logs | Credential was embedded directly in a command or configuration | Revoke the token, audit logs/history, and issue a new token safely |

Useful commands to inspect configuration without revealing token values:

```bash
git remote -v
git config --show-origin --get-all credential.helper
git config --show-origin --get credential.useHttpPath
git credential-manager --version
```

Do not run commands or debug modes that could print full credentials to the terminal or logs. If diagnostics are needed, mask all secret values before sharing output.

## 13. Secure setup workflow for a developer machine

Perform these steps on a test repository or a repository your account is authorized to access:

1. Install Git and a version of Git Credential Manager compatible with your OS.
2. Run `git credential-manager configure` or configure the `manager` helper according to your installed version.
3. Run `git config --show-origin --get-all credential.helper`.
4. Confirm the HTTPS remote contains no username/token.
5. Run `git fetch origin` to trigger the login flow.
6. If the service requires a PAT, create one with least-privilege permissions and an appropriate expiration; enter it at the secure prompt.
7. Verify that a subsequent fetch does not prompt for credentials while the token remains valid.
8. Check where the credential is stored using the OS security vault.
9. Practice removing the host credential in a test environment and re-authenticating.
10. Document token rotation and revocation procedures per team policy.

## 14. Token and credential manager security checklist

Before using a token:

- The token has only the required scopes and repository access.
- The token has a clear expiration date and owner.
- Organization approval or SSO authorization is completed if required.
- The remote URL contains no secret information.

When storing credentials:

- Use GCM or an organization-approved secure vault.
- Avoid `credential.helper store` for sensitive PATs.
- Never commit files containing tokens or personal credentials.
- Never print credentials to terminals, logs, or bug reports.

When a token is no longer needed or may be exposed:

- Revoke it on the Git service.
- Remove the credential from the helper/OS vault.
- Update relevant secret stores and pipelines.
- Audit activity logs and clean Git history if the token was ever committed.

## 15. Hands-on practice

Practice using a test account and test repository:

1. Check Git and GCM versions using `git --version` and `git credential-manager --version`.
2. Configure GCM with `git credential-manager configure`.
3. Create a test PAT with read-only access to one repository and an appropriately short expiration.
4. Set the remote using an HTTPS URL without any token.
5. Run `git fetch` and complete authentication via GCM or the provider prompt.
6. Inspect `git remote -v` to confirm the URL contains no token.
7. Run fetch again to confirm the helper supplies the saved credential.
8. Remove the test host credential using the management UI or `git credential reject`, then re-authenticate.
9. Revoke the test PAT at the provider and confirm the token can no longer be used.
10. Discuss how CI retrieves read-only secrets and write-capable credentials without printing values to logs.

Never use active production tokens to practice deletion or revocation. Never copy tokens into exercise files, scripts, issues, or commit contents.

## 16. Self-check questions

1. Why do many Git services require a PAT or OAuth instead of an account password when using HTTPS?
2. How does a PAT differ from an account password in terms of permission scoping and revocation?
3. When does Git invoke a credential helper?
4. Where does Git Credential Manager store credentials on common operating systems?
5. Why is `credential.helper store` unsuitable for storing sensitive PATs?
6. Why should tokens never be embedded in remote URLs?
7. What scenario does `credential.useHttpPath` help resolve?
8. When a token is exposed, why must it be revoked before rewriting Git history?
9. What kind of credential should CI use when it only needs to clone/fetch?
10. When should you consider HTTPS tokens instead of SSH keys?

## Conclusion

HTTPS authentication with tokens lets you restrict permissions and lifetimes for repository access. A credential manager like Git Credential Manager helps Git supply credentials through the operating system's secure vault and provider-supported login flows. Grant least privilege, keep remote URLs clean, avoid plaintext token storage, verify helper configuration, and maintain a rotation/revocation process. For CI/CD, retrieve credentials from a secret store or short-lived identity, separate read and write permissions, and ensure logs never expose secrets.
