# Checking Remote Repository Connectivity and Access Permissions

A Git repository can work normally on your machine and still fail to pull code from or push changes to a server. The cause may lie in the remote URL, the network, the authentication mechanism, account permissions, or branch protection policies. Knowing how to check each layer helps you pinpoint the exact issue before changing configuration or asking an administrator for permissions.

## 1. Distinguishing Remote, Connectivity, Authentication, and Access Permissions

In Git, a **remote** is an alias representing a repository at another location. The name `origin` is usually created when cloning, but it is just a convention; it is not a server name and does not prove that connectivity is working.

It is important to distinguish four concepts:

| Concept | Meaning | Example Issue |
|---|---|---|
| Remote configuration | Remote name and Git URL used to contact it | Wrong URL, remote not yet declared |
| Network connectivity | Machine can reach the server over DNS, network, proxy, and the required port | Unable to resolve hostname, timeout, blocked by firewall |
| Authentication | The server identifies which account or identity you are | Expired token, SSH key not registered |
| Authorization | Which operations the account is allowed to perform on the repository or branch | Read access works but cannot push, branch is protected |

A successful `fetch` shows that you can access the required read data on that remote. It does not prove that you have write permissions. Similarly, successfully signing in to a Git platform does not mean the account has access to every repository on that platform.

## 2. Checking Local Remote Configuration

First, view the declared remotes:

```bash
git remote -v
```

Sample output:

```text
origin  https://git.example.com/team/service.git (fetch)
origin  https://git.example.com/team/service.git (push)
```

Each remote can have a URL used for fetch and a URL used for push. These two URLs can differ—for instance, an organization may allow reads via a mirror server while requiring writes to the primary server. Therefore, inspect both lines and compare them against the repository URL provided by your team.

To view the URL resolved by Git after `insteadOf` shorthand rules, you can use:

```bash
git remote get-url --all origin
git remote get-url --push --all origin
```

Replace `origin` with the actual remote name. If no remotes exist yet, `git remote -v` prints nothing; that simply means the local repository has not declared any remote.

Some commonly used configuration edits:

```bash
git remote add origin https://git.example.com/team/service.git
git remote set-url origin https://git.example.com/team/service.git
git remote set-url --push origin https://git-write.example.com/team/service.git
```

`remote add` adds a new remote; `set-url` changes the default fetch URL; `set-url --push` sets a separate push URL. Perform these only after confirming the exact URL. If the remote already exists, do not add another remote with the same name.

Security note: remote URLs sometimes contain sensitive information if someone embedded a token in the URL. Do not post raw URLs containing tokens into tickets, logs, screenshots, or messages. Use a credential manager or the authentication mechanism recommended by your organization instead of storing tokens directly in the URL.

## 3. Checking Whether the Remote Responds

`git remote -v` only reads local configuration and sends no requests to the server. To verify that the remote is actually reachable, use:

```bash
git remote show origin
```

This command contacts the remote to retrieve information such as fetch/push URLs, the default branch, and branch tracking relationships. If the command fails, read the message to identify network, authentication, permission, or URL errors.

A direct way to inspect the list of refs published by the remote is:

```bash
git ls-remote --symref origin HEAD
git ls-remote --heads origin
```

The first command queries `HEAD` and the branch it points to if the server advertises symbolic refs. The second command lists remote branches. `git ls-remote` does not update remote-tracking branches in the local repository; it only queries existing refs on the server.

If a repository is newly created and has no commits yet, the command may succeed without printing any branches. Therefore, empty output does not automatically mean a connection failure; check the exit code and the repository state on the server.

To test fetch capability without updating local refs yet, you can run:

```bash
git fetch --dry-run origin
```

The `--dry-run` option shows what Git would do without performing the fetch update. When you actually need to download data and update remote-tracking branches, use `git fetch origin`; this updates local Git data without modifying the current working branch.

## 4. Checking Read and Write Permissions

Read permissions and write permissions are usually granted separately. Test according to the exact operation you need to perform.

### 4.1. Read Permissions

Operations such as `git ls-remote` and `git fetch` require repository read permissions. If `git ls-remote origin` lists refs, that is strong evidence that the current identity can read the repository via that URL.

If your team requires pulling code to your machine, after checking you can run:

```bash
git fetch origin
```

`fetch` downloads objects and updates remote-tracking refs per configuration. It does not automatically merge changes into the current branch. `git pull` typically performs a fetch followed by integrating changes into the active branch, so do not use `pull` merely as a connectivity test when you do not yet want to integrate code.

### 4.2. Write Permissions

Successful read access does not imply push permissions. If you need to test the ability to update a branch without actually updating refs, you can try simulation mode:

```bash
git push --dry-run origin HEAD:refs/heads/<branch>
```

Replace `<branch>` with a target branch you are permitted to update. `--dry-run` instructs Git to simulate the push operation without updating refs on the remote. The result helps uncover certain authentication or write-permission issues, but it is not a guarantee that an actual push will succeed: the server may enforce branch protection, hook checks, fast-forward rules, or other policies upon receiving an actual update. A non-fast-forward error also does not necessarily mean the account lacks write permissions.

If you need to confirm write permissions definitively, check the repository's policies or ask an administrator to verify your account's permissions and target branch rules. Do not push a test branch or delete a remote branch without your team's approval.

## 5. Authenticating with HTTPS and SSH

Git typically uses HTTPS or SSH to connect to servers. Use the method supported by your team or Git provider.

### 5.1. HTTPS

With HTTPS, servers typically authenticate using an account combined with an access token or an organization-managed login mechanism. Account passwords may not be accepted for Git operations; this depends on the platform and organization policy.

When encountering authentication errors, check the following:

- Does the URL have the correct protocol, hostname, group, and repository name?
- Is the credential manager using credentials from an old account?
- Is the token still valid, equipped with the required scopes/permissions, and authorized for SSO if required by the organization?
- Has the account been invited to the group or repository?

Do not paste tokens into commands, committed configuration files, or public error reports. If you suspect a token has been exposed, revoke it and issue new credentials according to your organization's process.

### 5.2. SSH

With SSH, the local machine uses a private key to prove identity; the Git server usually stores the corresponding public key on the account. Check the list of keys currently managed by the SSH agent:

```bash
ssh-add -l
```

If no matching key is listed, check the SSH agent, `~/.ssh/config`, the account where the public key is registered, and the hostname/port required by the provider. Never send your private key to others; only the public key is registered on the Git service.

You can test the SSH handshake with the server following your provider's guide, for example:

```bash
ssh -T git@git.example.com
```

Replace the hostname and SSH username with the values provided by the service. Some platforms use dedicated SSH ports or usernames. A successful authentication message at this step only confirms that the server recognized your key/account; you still need to check permissions on a specific repository using `git ls-remote` or the corresponding operation.

When SSH reports an unknown server host key or a changed fingerprint, verify the fingerprint against the provider's official documentation or with an administrator through a trusted channel. Never accept an unfamiliar fingerprint just to bypass the warning.

## 6. Reading and Isolating Common Errors

Error messages usually indicate which layer the problem lies in. However, some servers intentionally return generic messages so they do not reveal whether a private repository exists.

| Symptom | Possible Cause | Troubleshooting Direction |
|---|---|---|
| `Could not resolve host` | Wrong DNS or hostname | Check hostname spelling, DNS, VPN, and network configuration |
| `Connection timed out` or `Connection refused` | Firewall, proxy, VPN, port, or server service | Check allowed network access, proxy, port, and service status |
| `SSL certificate problem` | Untrusted certificate or CA chain, TLS-inspecting proxy | Check system clock, CA certificates, and organization proxy guidance |
| `Permission denied (publickey)` | Server rejects the SSH key being used | Check agent, loaded keys, registered public key, and SSH config |
| `Authentication failed` or HTTP `401` | Incorrect, expired, or revoked credentials | Check credential manager and regenerate token per policy |
| HTTP `403` or access denied message | Account recognized but lacks permissions or token lacks scope | Check repository permissions, token scopes, and SSO requirements |
| `Repository not found` or HTTP `404` | Wrong URL, repository does not exist, or server hides unreadable private repos | Cross-check URL and request access from repository owner |
| Push rejected due to protected branch or hook | Branch policy or server-side check disallows the update | Read the server message, use a pull request, or follow team workflow |
| `non-fast-forward` | Remote branch has commits not yet integrated by local branch | Fetch, inspect history, and integrate per team workflow before pushing |

Do not work around certificate errors by disabling TLS verification (`http.sslVerify=false`) or handle SSH warnings by arbitrarily deleting host keys. Those approaches weaken server verification and can cause credentials to be sent to a spoofed server.

## 7. Distinguishing Remote-Tracking Branches from Access Permissions

A remote-tracking branch like `origin/main` is a local reference recording the state of the remote branch as of the most recent fetch. View them with:

```bash
git branch -r
git branch -vv
```

Those commands do not query the server at runtime. Therefore, seeing `origin/main` does not prove that the remote is currently reachable or that the current account still has read access. To check the latest state, you need to query the remote, such as with `git ls-remote origin` or `git fetch origin`.

A local branch can be configured to track a remote branch. The upstream configuration tells Git the default target/source for operations like pull and push, but by itself it does not grant permissions to the account. Access permissions are governed by the server and organization policies.

## 8. Recommended Diagnostic Workflow

When clone, fetch, or push fails, proceed step by step:

1. **Confirm repository and remote.** Run `git status` and `git remote -v`; compare fetch/push URLs against your team's official addresses.
2. **Test reachability.** Run `git remote show origin` or `git ls-remote origin` to see if the server responds via that URL.
3. **Verify authentication method.** Check the credential manager for HTTPS or the SSH agent and key configuration for SSH. Ensure the right account is being used.
4. **Test the required permission.** Use `git ls-remote`/`git fetch` for read access. For write access, review branch policies and optionally use `git push --dry-run` as a preliminary check.
5. **Categorize the error message.** Separate network, certificate, authentication, authorization, branch protection, and non-fast-forward errors before changing configuration.
6. **Record sufficient diagnostic details for support.** Provide the command run, protocol type, hostname, repository name, timestamp, and the error message with sensitive data masked. Never send tokens, passwords, private keys, or URLs containing credentials.

Example of a read-only diagnostic sequence:

```bash
git status
git remote -v
git remote show origin
git ls-remote --symref origin HEAD
```

If read commands succeed while push is rejected, shift your investigation toward write permissions, the target branch, and branch protection policies. There is no need to replace SSH keys or tokens when evidence shows read authentication works and the error occurs only on write operations.

## 9. Key Takeaways

A remote is a configuration pointing to another repository; network connectivity, identity authentication, and operation authorization are separate layers. Verify the URL first, query the remote to confirm read access, and then check write policies for the specific branch and operation. Protect tokens, private keys, and server verification details throughout the troubleshooting process.
