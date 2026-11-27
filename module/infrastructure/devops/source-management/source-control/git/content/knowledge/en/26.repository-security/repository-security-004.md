# Never Put Passwords, Tokens, and Private Keys in URLs or Repository Configuration

Git needs authentication when connecting to private remotes, fetching submodules, or pushing data to a server. There are several ways to supply credentials, such as HTTPS with a credential helper, an SSH key, or a token issued by a CI system. A common mistake is embedding a password or token directly in a remote URL, writing a private key into a configuration file, or committing secret files into the repository.

These practices can cause secrets to appear in `.git/config`, shell history, CI logs, backups, clones, or commit history. Deleting the secret string from the current file does not erase it from places where it was previously stored.

This lesson explains how to identify leak-prone locations, configure HTTPS and SSH authentication safely, manage secrets in CI, prevent accidental commits, and respond when credentials have been exposed.

## 1. Separating remote URLs from credentials

### 1.1. Remote URLs should only identify the repository

A remote typically has a name such as `origin` or `upstream`. Its URL identifies the server and repository to connect to.

Example HTTPS URL without credentials:

~~~bash
git remote add origin https://github.com/ORG/PROJECT.git
~~~

Or updating an existing URL:

~~~bash
git remote set-url origin https://github.com/ORG/PROJECT.git
~~~

When connecting, Git will request or retrieve credentials from the configured credential helper. Users do not need to put tokens in the URL.

An SSH URL does not need to contain a private key either:

~~~bash
git remote set-url origin git@github.com:ORG/PROJECT.git
~~~

In this example, `git@github.com` is the SSH account and host; the SSH client selects the right key via ssh-agent or SSH configuration.

### 1.2. Why avoid embedding tokens in URLs?

Do not use URLs such as:

~~~text
https://USERNAME:TOKEN@github.com/ORG/PROJECT.git
~~~

Nor should you attach a token to a query string:

~~~text
https://github.com/ORG/PROJECT.git?access_token=TOKEN
~~~

These strings can be saved in:

- `.git/config` if set as a repository-level remote URL.
- Global or system configuration if set at those scopes.
- Shell command history.
- Script, CI, or GUI tool logs.
- Process listings or diagnostic data when commands are invoked with arguments containing secrets.
- Backups, archives, or shared repository copies.

A URL containing a token can also be displayed by `git remote -v`, administration tools, or debug logs. Therefore, a remote URL should contain only the repository address.

### 1.3. .git/config is not a secret store

Local repository configuration usually lives in `.git/config`. This file is not committed like normal source files, yet it can still hold sensitive data if you manually write tokens or passwords into it.

For example, a remote configuration may be stored as:

~~~ini
[remote "origin"]
    url = https://github.com/ORG/PROJECT.git
    fetch = +refs/heads/*:refs/remotes/origin/*
~~~

This is an appropriate form because the URL contains no credentials.

Even though `.git/config` is not committed, it can still be exposed when:

- Zipping the entire repository folder to send for support.
- Backing up the working directory to an unprotected service.
- Sharing a machine or operating system account.
- Diagnostic tools collect the Git directory.
- A script accidentally prints the entire configuration to logs.

Do not treat local configuration as a secret store. It is simply a plain-text configuration file.

## 2. Common places where passwords, tokens, and private keys leak

### 2.1. Remote URLs and Git config

Inspect remote URLs:

~~~bash
git remote -v
~~~

This command helps confirm fetch/push remotes, but if an older URL embedded a token, the output may display that token. When sharing output, mask the secret portion first.

You can inspect the URL value in config:

~~~bash
git config --show-origin --get remote.origin.url
~~~

This command can also print credentials if the URL currently contains them. Run and view the output only in a private environment; never paste raw output into tickets, chats, or public logs.

Besides remote URLs, configuration keys such as `http.<url>.extraheader` can hold authentication headers. These headers often contain Base64-encoded values, yet Base64 is not security encryption and can be decoded back. Never store an Authorization header containing a long-lived token in a configuration file.

### 2.2. Committed configuration files

Some configuration files live in the working tree and are tracked by Git, such as:

- `.env`
- `config/local.yml`
- `application-prod.properties`
- `settings.json`
- `.npmrc`, `.pypirc`, or other tool configuration files
- `.gitmodules` if a submodule URL was written with credentials attached

Not every file named config contains secrets. Distinguish public configuration from per-machine or per-environment credentials.

For example, a repository can provide `.env.example` containing only variable names and dummy values:

~~~dotenv
API_BASE_URL=https://api.example.test
API_TOKEN=
DATABASE_URL=
~~~

The actual `.env` file holding tokens or passwords should stay outside Git and be supplied via a secret manager or environment configuration.

### 2.3. Commit history

If a token was ever committed, removing it from the file in a newer commit does not remove the content from older commits. Anyone with read access to the repository can still check out an older commit or search for the secret string in history.

For example:

~~~text
A --- B --- C
      |
      +-- B contains the committed token
~~~

A new commit D removes the token from the file:

~~~text
A --- B --- C --- D
~~~

The token still remains in B and C. Therefore, once a secret has been committed or pushed, treat it as a credential incident rather than merely editing the current file content.

### 2.4. Shell history, logs, and automation tools

Avoid passing tokens directly inside commands whenever possible:

~~~bash
git clone https://USERNAME:TOKEN@github.com/ORG/PROJECT.git
~~~

Even if the command runs only once, the string can remain in history, runner logs, or diagnostic data. Similarly, avoid:

- Printing secret environment variables with `echo`, `set`, or `env`.
- Enabling HTTP debugging without knowing what the logs will capture.
- Passing tokens in process command-line arguments.
- Storing credentials in committed scripts.
- Sending raw log files without reviewing them for sensitive information.

Base64 encoding, URL encoding, or renaming variables does not turn a token into safe data to expose publicly.

## 3. HTTPS authentication with credential helpers

### 3.1. What does a credential helper do?

A credential helper is a mechanism for Git to retrieve and store credentials without embedding them in remote URLs. When a server requires authentication, Git calls the configured helper; the helper can prompt the user to log in or retrieve credentials from a secure vault.

Check configured helpers:

~~~bash
git config --show-origin --get-all credential.helper
~~~

There may be multiple helpers or helpers across multiple configuration scopes. Inspect their origins to understand which mechanism Git is using.

### 3.2. Prefer the operating system's credential vault

Git Credential Manager (GCM) is a popular choice on Windows, macOS, and Linux. GCM supports modern authentication flows and integrates with the OS or provider credential vault.

Once GCM is installed, you can configure the helper:

~~~bash
git config --global credential.helper manager
~~~

The helper name may vary by version or installation package. Check the documentation for your installed GCM version if Git cannot find the helper.

Some systems also provide dedicated helpers:

- macOS: `osxkeychain`.
- Linux: helpers integrating with libsecret or a desktop secret keyring.
- Windows: Git Credential Manager typically integrates with Windows Credential Manager.

Use a helper appropriate for your environment and organizational policy. There is no need to write passwords or tokens directly into `.gitconfig`.

### 3.3. Distinguishing cache and store

Git includes simple helpers with different levels of protection:

- `cache` keeps credentials temporarily in memory for a set period of time.
- `store` saves credentials long-term in a plaintext file, typically `~/.git-credentials`.

Do not choose `store` for sensitive tokens or passwords on shared machines or environments with file access risk. A file protected only by OS file permissions is still plaintext readable by any authorized account.

If long-term persistence is needed, prefer a helper integrated with the OS secret vault or a provider-supported SSO/OAuth mechanism.

### 3.4. Using HTTPS without embedding tokens in URLs

Set a remote URL that contains no credentials:

~~~bash
git remote set-url origin https://github.com/ORG/PROJECT.git
~~~

Then run the operation requiring authentication:

~~~bash
git fetch origin
~~~

Git Credential Manager or the configured helper will handle the login flow. If the provider requires a personal access token (PAT), enter the token via the prompt or helper-supported authentication flow, without attaching it to the URL.

Some platforms no longer accept account passwords for Git over HTTPS. In that case, use a least-privilege PAT or OAuth/SSO per provider policy.

## 4. Using tokens safely

### 4.1. Choosing the right token

A token should have:

- The minimum permissions required for the task.
- Specific repository scope if supported by the platform.
- An appropriate expiration date.
- A clear owner or purpose.
- A revocation and replacement procedure.

Do not use a single full-access personal token across every script, server, and repository. For automation, prefer dedicated workload tokens or machine identities if supported by the platform.

### 4.2. Never put tokens in URLs or configuration files

Avoid patterns such as:

~~~bash
git remote set-url origin https://USER:TOKEN@github.com/ORG/PROJECT.git
git config --global remote.origin.url https://USER:TOKEN@github.com/ORG/PROJECT.git
~~~

Both can store the token in plaintext inside configuration. Instead, use clean URLs and a credential helper.

If a tool requires a token for an API, use that tool's official secret input mechanism or credential provider. Do not pass tokens as arbitrary arguments just to make a command run non-interactively.

### 4.3. Never share tokens in chat or tickets

When requesting help with an authentication error, share only:

- Error messages with any tokens stripped out.
- The provider and authentication type in use.
- The timestamp of the error and the operation performed.
- The remote name after verifying the URL is clean.
- Request IDs or correlation IDs if non-sensitive.

Never send tokens, passwords, private keys, recovery codes, or credential files to teammates so they can "help test". Grant separate permissions to the account or workload of whoever needs access.

## 5. Using SSH keys without exposing private keys

### 5.1. Distinguishing private keys and public keys

SSH typically uses a key pair:

- **Private key:** kept secret on your machine or in a key management system. Never commit, send over chat, or upload to a repository.
- **Public key:** can be registered with a Git hosting provider or SSH server to grant access.

Example filenames:

~~~text
~/.ssh/id_ed25519_work       # private key
~/.ssh/id_ed25519_work.pub   # public key
~~~

Only the `.pub` file is uploaded to the Git hosting service. Never place a private key in a repository.

### 5.2. Generating a private key for work

You can generate an Ed25519 key:

~~~bash
ssh-keygen -t ed25519 -C "work Git access" -f ~/.ssh/id_ed25519_work
~~~

When prompted, set a strong passphrase on the private key. A passphrase helps protect the key if the file is copied.

On Windows, macOS, and Linux, home paths and SSH agent management differ. Choose a location suited to your user account and ensure restricted file permissions.

### 5.3. Loading the key into the SSH agent

After generating the key, load it into the agent:

~~~bash
ssh-add ~/.ssh/id_ed25519_work
~~~

The SSH agent holds the unlocked key in your session so you do not have to enter the passphrase on every connection. The agent is not a place to commit keys; the private key still needs protection on disk.

If the command reports it cannot connect to the agent, check your OS ssh-agent service and current terminal session.

### 5.4. Configuring SSH per host

You can define an alias in `~/.ssh/config`:

~~~sshconfig
Host github-work
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_work
    IdentitiesOnly yes
~~~

Then use the alias in the remote:

~~~bash
git remote set-url origin git@github-work:ORG/PROJECT.git
~~~

This configuration only tells the SSH client which key to use when connecting. The private key is not in the URL and is not written into Git config.

Test the connection:

~~~bash
ssh -T git@github-work
~~~

A success message may state that the server authenticated you but does not provide interactive shell access. This is normal behavior for many Git hosting providers.

### 5.5. Checking the host key

SSH also needs to authenticate the server. On first connection, SSH may ask to confirm the host key. Compare the fingerprint against your provider's official documentation or your organization's trusted source.

Do not blindly accept a new host key when warned that the key has changed. That could indicate a legitimate infrastructure change, or it could signal connecting to a different server or a man-in-the-middle risk. Verify the fingerprint before updating `known_hosts`.

## 6. Protecting configuration and secret files in a repository

### 6.1. Using .gitignore for local files

A `.gitignore` file can exclude secret files from untracked listings:

~~~gitignore
.env
.env.*
!.env.example
*.pem
*.key
secrets/
credentials/
~~~

These patterns are examples only; adjust them to match your project structure. Not every `.pem` or `.key` file is a private key, and if the project has legitimate files using those extensions, write more specific rules to avoid missing secrets or ignoring valid files.

### 6.2. .gitignore does not untrack already-tracked files

If `.env` has already been committed, adding it to `.gitignore` does not make Git stop tracking that file.

To remove the file from the index while keeping it on disk:

~~~bash
git rm --cached -- .env
git add .gitignore
git commit -m "Stop tracking local environment file"
~~~

Afterward, developer machines can keep their local copy while the repository stops tracking it.

However, if the file ever contained tokens or passwords, the secrets still exist in older commits. You must revoke the credentials and evaluate removing them from history as a separate incident.

### 6.3. Providing template files without secrets

You can commit `.env.example` with placeholders:

~~~dotenv
DATABASE_URL=
API_TOKEN=
PAYMENT_PROVIDER=
~~~

Onboarding docs instruct each member to create a local `.env` or pull values from a secret manager. Never put production values, real tokens, or shared passwords in template files.

### 6.4. Checking before committing

Before committing, review the staged file list and contents:

~~~bash
git status --short
git diff --cached --name-only
git diff --cached
~~~

The last command can display secrets directly if they have been staged. Review it in a private environment and never copy unreviewed output into chats or tickets.

You can use secret scanners in pre-commit hooks, CI, or your Git hosting platform's push protection. Scanners help catch pattern-matched tokens and keys, though they do not guarantee detecting every secret, especially encrypted data or secrets inside binary files.

## 7. Managing secrets in CI/CD

### 7.1. Storing secrets in the platform's secret store

CI needs tokens to clone private dependencies, push artifacts, or deploy. Store them in the CI platform's protected secrets/variables feature or a dedicated secret manager.

Never store tokens in:

- Committed workflow YAML files.
- Build or deploy scripts.
- Dockerfiles and image layers.
- Configuration files packaged into artifacts.
- Job logs or outputs.

Workflows should reference only the secret name, for example:

~~~yaml
steps:
  - name: Publish package
    env:
      PACKAGE_TOKEN: ${{ secrets.PACKAGE_TOKEN }}
    run: ./scripts/publish.sh
~~~

This is an example of GitHub Actions syntax. On other CI platforms, use the corresponding secret injection mechanism.

### 7.2. Limiting permissions and lifetimes

CI tokens should have permissions scoped strictly to the job. For example, a job that only needs to read the repository should not receive write permissions. A release job should only have permission to publish to the required resources.

When supported by the platform, prefer:

- Short-lived tokens.
- OIDC or workload identity instead of long-lived secrets.
- Dedicated tokens per repository or environment.
- Read-only permissions for dependency download steps.
- Environment approvals before supplying production secrets.

Never reuse an employee's personal token for long-running pipelines.

### 7.3. Never print secrets to logs

Avoid commands such as:

~~~bash
echo "$PACKAGE_TOKEN"
env
printenv
set
~~~

Some CI systems automatically mask registered secret values, but masking is not an absolute guarantee. A secret may be transformed, encoded, truncated, or printed in an error message in an unrecognized form.

Do not enable shell tracing or full command debugging in steps that handle credentials if there is any risk of printing values. Log only sanitized results, such as status codes or step names.

### 7.4. Pull requests from forks and secrets

Many platforms restrict supplying secrets to workflows triggered by pull requests from forks. This is a protective measure because externally proposed code could modify scripts to read and exfiltrate secrets.

Do not attempt to bypass this restriction by embedding tokens in workflow files or URLs. Separate checks that do not need secrets from privileged deployment steps, and supply secrets only after code has passed review/approval per project policy.

## 8. Inspecting Git configuration without exposing secrets

### 8.1. Selectively inspecting configuration sources

Git can read configuration from system, global, local, and worktree scopes. When investigating, query specific keys:

~~~bash
git config --show-origin --get-all credential.helper
git config --show-origin --get core.hooksPath
~~~

Never share raw `git config --list` output externally without reviewing it first. Configuration may contain remote URLs, headers, or internal paths with sensitive details.

### 8.2. Cleaning a remote URL if credentials were previously embedded

If a remote URL currently contains a token, replace it with a clean URL:

~~~bash
git remote set-url origin https://github.com/ORG/PROJECT.git
~~~

Verify again:

~~~bash
git remote -v
~~~

Before sharing output, confirm the URL no longer contains credentials. If a token was ever in the URL, treat that token as compromised and revoke/replace it. Changing the URL only fixes the current configuration; it does not remove the token from shell history, logs, or older copies.

### 8.3. Avoiding Authorization headers in configuration

Do not use persistent configuration to store a header containing a token, such as `http.<url>.extraheader` with a static Authorization value. The header may be written into `.git/config` or global configuration files and exposed when collecting configs.

Use a credential helper or the tool's official authentication mechanism instead. If an organization has a temporary header workflow, supply it from a secret manager at runtime, restrict logging, and never persist it in long-term configuration files.

## 9. Responding when a token, password, or private key is exposed

Treat any exposed credential as untrusted. Deleting the string from a file or a new commit is not enough to protect the account.

### Step 1 — Revoke or rotate immediately

Prioritize invalidating the credential at the issuer:

- Revoke the PAT or API token.
- Change the password if a password was exposed.
- Remove the corresponding SSH public key from the account or deploy key list if a private key was exposed.
- Rotate service account and workload credentials.
- Revoke sessions or refresh tokens if supported by the provider.

Create new credentials with least privilege and an appropriate expiration. If the secret could access production, assess blast radius and rotate dependent credentials as well.

### Step 2 — Identify where the secret appeared

Audit relevant locations:

- Current files and commits in history.
- Remote URLs and Git config.
- `.git-credentials` or the OS credential vault.
- Shell history, terminal logs, and scripts.
- CI logs, artifacts, caches, and build outputs.
- Pull requests, issues, chats, or tickets.
- Clones, forks, and backups.
- Submodule or dependency configuration files.

Do not include secret values in investigation reports. Record only the credential type, owner, timestamp, permission scope, and revocation status.

### Step 3 — Remove the secret from current code

Replace the secret with an environment variable or secret manager. If the file is meant only for local use, add an ignore rule and provide a template file containing no real values.

Example removing `.env` from the index while keeping the local copy:

~~~bash
git rm --cached -- .env
git add .gitignore
git commit -m "Remove local environment file from tracking"
~~~

This only cleans the current version. If the secret was ever committed, history still needs to be evaluated.

### Step 4 — Consider cleaning history

If policy requires purging the secret from Git history, a history-rewriting tool such as `git filter-repo` can be used following organizational procedure. This requires identifying all affected refs accurately: branches, tags, and other references.

Do not put the token value directly into commands or committed files. If a replacement file containing secret strings is needed, protect that file like a secret, restrict access, and securely delete it when finished.

Rewriting history may require force-pushing and coordinating with everyone using the repository. Existing clones, forks, pull requests, caches, artifacts, and logs may still retain old content. No filtering operation guarantees erasing every copy outside your control.

### Step 5 — Verify and notify

After revoking credentials and cleaning the repository:

- Run a secret scanner across current branches and history per policy scope.
- Confirm the old credential no longer works.
- Verify CI, deploy keys, and automation have switched to the new credential.
- Review access logs for unusual activity.
- Notify repository maintainers and team members who need to synchronize with the new history.

Never delay revoking a token while waiting for a history rewrite to finish. Revoking the credential is the first risk-reduction step.

## 10. Common mistakes

- **Embedding tokens in remote URLs:** tokens can surface in Git config, shell history, and logs. Use clean URLs together with a credential helper.
- **Assuming .git/config is safe because it is uncommitted:** local files can still be backed up, archived, or shared. Never store secrets there.
- **Using credential.helper store for sensitive tokens:** this helper saves plaintext. Prefer the OS secret vault or GCM.
- **Committing a private SSH key:** a private key grants access and must stay outside the repository. Only register the public key.
- **Assuming .gitignore removes secrets from Git:** ignoring only prevents untracked files from being added automatically; it does not remove already-committed files.
- **Only removing a token in a new commit:** older commits and clones can still contain the token. Revoke first, then clean history.
- **Using one full-access PAT across all pipelines:** if leaked, the blast radius is large. Create separate tokens with least privilege.
- **Printing environment variables to debug CI:** logs can retain secrets long-term. Log sanitized status instead.
- **Believing Base64 hides credentials:** Base64 is only a representation encoding, not secret protection.
- **Force-pushing rewritten history without notifying the team:** this can drop teammates' new commits or diverge clones. Plan synchronization and guide members on updating.

## 11. Credential protection checklist

Before pushing or sharing a repository, confirm:

- [ ] Remote URLs contain no username/password/token.
- [ ] Git config contains no tokens or long-lived Authorization headers.
- [ ] Private SSH keys stay outside the repository and have an appropriate passphrase.
- [ ] Local `.env`, credential, and secret files are ignored if they must not be committed.
- [ ] Template files contain only placeholders.
- [ ] Credential helper uses storage appropriate for the operating system.
- [ ] CI pulls secrets from a secret manager and does not print values to logs.
- [ ] Tokens have least privilege and a clear expiration.
- [ ] Secret scanning or push protection is enabled when supported by the platform.
- [ ] If a secret was ever leaked, the old credential was revoked before considering a history rewrite.

## 12. Quick reference table

| Need | Command or practice |
| --- | --- |
| View remote URLs | `git remote -v` — inspect and mask credentials if present |
| Set a clean HTTPS URL | `git remote set-url origin https://github.com/ORG/PROJECT.git` |
| Set an SSH URL | `git remote set-url origin git@github.com:ORG/PROJECT.git` |
| View credential helper | `git config --show-origin --get-all credential.helper` |
| Configure Git Credential Manager | `git config --global credential.helper manager` |
| Generate an SSH key | `ssh-keygen -t ed25519 -C "work Git access"` |
| Load private key into agent | `ssh-add ~/.ssh/id_ed25519_work` |
| Test SSH connection | `ssh -T git@github-work` |
| Untrack a local file from index | `git rm --cached -- .env` |
| View staged files | `git diff --cached --name-only` |
| Replace URL containing credentials with clean URL | `git remote set-url origin https://github.com/ORG/PROJECT.git` |
| Handle an exposed secret | Revoke/rotate first, then clean files and history per procedure |

## 13. Summary

Passwords, tokens, private keys, and Authorization headers are sensitive credentials. Never put them into remote URLs, Git config, committed files, scripts, or logs. A remote URL should only identify the repository; Git Credential Manager, an appropriate credential helper, or an SSH agent handles authentication separately.

For the repository, use `.gitignore` for local files, provide template files without secrets, and inspect staged content before committing. For CI, pull credentials from a secret manager, grant least privilege, and avoid printing values to logs.

If a credential has been exposed, revoke or rotate it immediately. Only afterward should you remove it from current code, evaluate rewriting history, and address remaining clones, forks, artifacts, or logs. This approach protects both access control and the critical history of the repository.

## References

- [Git credentials — Git documentation](https://git-scm.com/docs/gitcredentials)
- [git-credential — Git documentation](https://git-scm.com/docs/git-credential)
- [Git Credential Manager](https://github.com/git-ecosystem/git-credential-manager)
- [GitHub: About remote repositories](https://docs.github.com/en/get-started/git-basics/about-remote-repositories)
- [GitHub: Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
