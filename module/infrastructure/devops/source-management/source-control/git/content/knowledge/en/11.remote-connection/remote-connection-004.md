# HTTPS, SSH Protocols, and Local Repository Paths

When working with Git, you can pull and send changes to a repository via HTTPS, SSH, or a filesystem path. These three methods differ only in how Git locates the repository and authenticates access. Git objects such as commits, branches, and tags still have the exact same meaning regardless of which protocol you use.

## 1. What Is a Remote in Git?

A **remote** is a memorable alias used by Git to store the address of another repository. A remote typically points to a repository on a hosting service such as GitHub, GitLab, or an organization's Git server, though it can also point to a repository directory on your computer or a shared drive.

A remote usually has two components:

- **Remote name**: an alias used in commands, such as `origin` or `upstream`.
- **URL**: the Git address used to access the repository, such as an HTTPS URL, an SSH URL, or a local path.

`origin` is the default name usually created when you clone a repository. This is merely a naming convention, not a mandatory keyword. In a project with an original repository and a fork, teams commonly use `origin` for their fork and `upstream` for the original repository.

View configured remotes:

```bash
git remote -v
```

Sample output:

```text
origin  https://git.example.com/team/app.git (fetch)
origin  https://git.example.com/team/app.git (push)
```

A remote can have different fetch and push addresses. Therefore, inspect both lines when checking configuration. To view more information about a remote and tracking branches:

```bash
git remote show origin
```

Git stores remote configuration in `.git/config` inside the current repository. A remote is not a live synchronized copy; references like `origin/main` reflect the data Git most recently downloaded and are updated when you fetch.

## 2. Three Ways to Specify a Repository Address

### 2.1. HTTPS

An HTTPS URL typically has the form:

```text
https://<host>/<group-or-user>/<repo-name>.git
```

Example:

```bash
git clone https://git.example.com/platform/payment-service.git
```

When using HTTPS, Git connects over HTTP secured with TLS. The server authenticates the user through a sign-in mechanism supported by the provider, usually a personal access token or credentials managed by Git Credential Manager. Many services no longer accept regular account passwords for Git operations over HTTPS.

HTTPS is suitable when:

- Your organization's network allows HTTPS but restricts SSH connections.
- You are new to Git and want to use the login mechanism provided by the hosting service.
- Your computer already has Git Credential Manager to store and use credentials securely.

Do not embed tokens or passwords directly into the URL, such as `https://user:token@host/...`. URLs can get saved in configuration files, command history, or logs. Let your credential manager handle authentication.

### 2.2. SSH

An SSH URL typically takes one of two forms:

```text
git@<host>:<repo-path>.git
ssh://<user>@<host>:<port>/<repo-path>.git
```

Common SCP-like syntax example:

```bash
git clone git@git.example.com:platform/payment-service.git
```

URI syntax example with an explicit port:

```bash
git clone ssh://git@git.example.com:22/platform/payment-service.git
```

In the first form, a colon separates the host and the repository path. In the `ssh://` form, the port is written after the hostname and before the path.

SSH typically authenticates using an asymmetric key pair:

- **Private key** stays on your machine and must be protected.
- **Public key** is registered with your Git account or server.
- `ssh-agent` can keep the unlocked key in your session so you do not have to enter the passphrase repeatedly.

On a machine with OpenSSH, you can generate an Ed25519 key with:

```bash
ssh-keygen -t ed25519 -C "machine-name-or-email"
```

Then add the public key to your Git account or server according to your provider's instructions. If using `ssh-agent`, load the private key with:

```bash
ssh-add ~/.ssh/id_ed25519
```

The key filename and location may differ if you chose a different path when generating the key. On Windows, OpenSSH commands can be run in PowerShell or Git Bash depending on your installation.

Test the SSH connection to the server:

```bash
ssh -T git@git.example.com
```

Replace `git.example.com` with the actual server. Some services return a welcome message or notify you that authentication succeeded without granting an interactive shell; that can still indicate that the key was accepted. Follow the provider's specific verification syntax if they require one.

On the first connection, SSH may ask whether you trust the server's host key. Compare the fingerprint against official information from your administrator or provider before accepting. Never blindly ignore host key change warnings.

SSH is suitable when you fetch and push frequently, want key-based authentication, or your organization has standardized SSH key provisioning. Connections may require extra configuration if your network blocks the default SSH port.

### 2.3. Local Repository Path

Git can also access a repository via a path on the same machine or a mounted filesystem. Examples:

```bash
git clone ../shared/payment-service.git
git clone /srv/git/payment-service.git
```

Paths can be:

- **Relative**, such as `../shared/payment-service.git`, resolved relative to the working directory where the command is run.
- **Absolute**, such as `/srv/git/payment-service.git` or `D:/git/payment-service.git`.
- **File URI**, such as `file:///srv/git/payment-service.git`.

Local paths are useful for learning Git, backups, exchanging data in offline environments, or working with repositories on a shared drive. When multiple clones need to push to the same repository, use a **bare repository** as the receiving repository. A bare repository contains Git data without a working tree for users to edit directly.

Create a bare repository:

```bash
git init --bare /srv/git/payment-service.git
```

Clone from that repository:

```bash
git clone /srv/git/payment-service.git payment-service
```

You can also add this path as a remote to an existing repository:

```bash
git remote add local-backup ../shared/payment-service.git
git remote -v
```

You should not use a regular repository with a checked-out working tree as a target for pushes from multiple people. Git normally rejects updating a branch that is currently checked out to prevent the receiving working tree from falling into an inconsistent state. A bare repository is the better choice for receiving pushes.

## 3. Comparing and Choosing a Protocol

| Criterion | HTTPS | SSH | Local Path |
|---|---|---|---|
| Typical address | `https://host/group/repo.git` | `git@host:group/repo.git` | `../repo.git`, `/srv/git/repo.git` |
| Authentication | Token or credentials via credential manager | SSH key pair | Filesystem permissions |
| Network | Usually uses HTTPS port 443 | Usually uses SSH port 22, configurable | No Internet required; path must be reachable |
| Best suited for | Networks allowing only HTTPS, service-based login | Frequent work, organization-managed keys | Learning, backups, file servers, or internal environments |
| Key considerations | Protect tokens and credentials | Protect private key, verify host key | Read/write permissions and how the receiving repo is structured |

No protocol changes how Git stores commits. Choose based on authentication policies, network connectivity, and how your team manages access permissions. The same repository can be accessed via HTTPS on one machine and SSH on another; what matters is that those addresses actually point to the same repository.

## 4. Connecting a Remote to an Existing Repository

If you cloned from a URL, Git usually creates the `origin` remote automatically. If you already have a local repository and want to connect it to a repository on a server, add the remote:

```bash
git remote add origin https://git.example.com/platform/payment-service.git
git remote -v
```

Download branch and commit information from the remote:

```bash
git fetch origin
```

`fetch` updates remote-tracking branches such as `origin/main`, but does not automatically integrate changes into the current local branch. You can inspect branches and tracking status with:

```bash
git branch -vv
git branch -r
```

When you want to push the current branch to the remote and set up the tracking branch for the first time, use:

```bash
git push -u origin main
```

Replace `main` with the actual branch name in your repository. The `-u` (or `--set-upstream`) option sets up the upstream so subsequent commands can use shorter `git push` or `git pull`.

If the remote already exists but the address changed, update the URL instead of adding a duplicate remote:

```bash
git remote set-url origin git@git.example.com:platform/payment-service.git
git remote -v
```

You can retrieve the URL currently used for a remote with:

```bash
git remote get-url origin
```

If a project works with a fork and an original repository, you can declare two remotes:

```bash
git remote add origin git@git.example.com:my-account/payment-service.git
git remote add upstream https://git.example.com/platform/payment-service.git
git remote -v
```

In this example, `origin` points to the fork and `upstream` points to the original repository. Remote names only carry meaning based on the project's configuration; agree on a convention with your team.

## 5. Testing Connectivity Before Operating

After configuring a remote, you can check the address and read access with:

```bash
git remote -v
git ls-remote origin
```

`git ls-remote` asks Git to contact the server and list references that the account has permission to view. This command helps detect wrong URLs, network errors, or read authentication errors. It does not prove that you have push permissions.

To see whether Git can perform a push without updating branches on the remote, you can run a dry run:

```bash
git push --dry-run origin HEAD
```

A dry run is useful for checking basic configuration and push permissions, though actual push results can still differ due to hooks, server policies, or changes in remote state.

In daily work, commonly used commands include:

```bash
git fetch origin
git pull --ff-only origin main
git push origin main
```

`git pull` performs a fetch and then integrates changes into the current branch according to your pull configuration. The example above uses `--ff-only` to allow only fast-forward updates; if history has diverged, Git stops so you can inspect and choose how to handle it. Replace `main` with the branch you need to work on.

## 6. Switching Between HTTPS and SSH

You do not need to re-clone a repository just to switch protocols. Update the remote's URL:

```bash
git remote set-url origin git@git.example.com:platform/payment-service.git
git remote -v
git ls-remote origin
```

If you want to switch back to HTTPS:

```bash
git remote set-url origin https://git.example.com/platform/payment-service.git
```

Changing the URL does not alter existing commits, branches, or the working tree. However, after switching, ensure your machine has valid credentials configured for the new protocol. If your team uses separate fetch and push URLs, check both lines from `git remote -v` before concluding the switch is complete.

## 7. Common Errors and Troubleshooting

| Message or Symptom | Possible Cause | How to Check and Resolve |
|---|---|---|
| `Repository not found` | Wrong URL, private repository, or account has not been granted access | Verify host, group, repository name, and account access permissions |
| `Authentication failed` when using HTTPS | Expired token, wrong credentials, or stale cached credential | Sign in again via credential manager; regenerate/reissue token per provider policy |
| `Permission denied (publickey)` | SSH cannot find a matching key or the public key is not registered | Check keys, `ssh-agent`, `ssh-add -l`, and whether the account has the public key |
| `Host key verification failed` | Server host key is untrusted or has changed | Verify fingerprint through an official channel before updating `known_hosts` |
| Connection timed out or refused | Wrong host/port, firewall, VPN, or proxy | Check network, proxy configuration, and ports supported by the server |
| `non-fast-forward` when pushing | Remote has commits that the local branch has not integrated | Fetch, inspect both branch histories, then merge or rebase per team convention |
| Push to local path rejected | Target is a repository with a working tree and checked-out branch | Use a bare repository as the push target or choose an appropriate sharing method |

A short troubleshooting sequence when unable to connect:

```bash
git remote -v
git remote get-url origin
git ls-remote origin
```

Then determine whether the error belongs to the address, network, or authentication. Avoid changing multiple settings at once, as it becomes harder to know which change solved the issue.

## 8. Protecting Credentials and Repositories

- Never commit tokens, passwords, or private keys into a repository.
- Never put tokens into remote URLs or share URLs containing credentials.
- Grant only necessary permissions to accounts and SSH keys; revoke keys when a device is no longer in use.
- Protect private keys with appropriate file permissions and a passphrase when required by policy.
- Verify the server host key fingerprint when setting up SSH for the first time or when receiving a key-change warning.
- For local repositories on shared drives, control read/write permissions and use a bare repository as the push target.

## 9. Hands-On Exercise

Suppose you have a local repository named `payment-service` and your team provides both an HTTPS URL and an SSH URL for the same repository.

1. Add a remote named `origin` using the HTTPS URL and confirm with `git remote -v`.
2. Run `git ls-remote origin` to verify read access to the repository.
3. Switch `origin` to the SSH URL using `git remote set-url`.
4. Check your SSH key and run `git ls-remote origin` again.
5. Create a bare repository in another directory, add it under the name `local-backup`, and inspect both remotes.

You have completed the exercise when you can explain where each remote points, which authentication mechanism Git uses for each, and how to test connectivity without modifying history on the remote.
