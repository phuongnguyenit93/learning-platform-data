# Directory Ownership, safe.directory, and Overly Broad Trust Risks

Git checks repository ownership before trusting configuration and performing certain actions that could execute code from the repository. If the working directory or Git directory belongs to another user, Git may stop and report:

~~~text
fatal: detected dubious ownership in repository at '/path/to/repository'
To add an exception for this directory, call:

    git config --global --add safe.directory /path/to/repository
~~~

This message does not necessarily mean you lack file read or write permissions. Git is warning that the repository is owned by a different identity than the user running Git. You must determine the cause before marking the repository as trusted.

This lesson belongs to the **Repository Security** chapter of the SOURCE_CONTROL_GIT module. The module covers the working tree, staging area, commit, history, branch, merge, rebase, remote, and tag; understanding ownership and trust boundaries helps you use Git safely on personal machines, shared hosts, containers, and CI.

## 1. Why does Git check ownership?

A repository can contain configuration and components that alter how Git behaves. Certain configurations can invoke external programs, change how files are processed, or specify where hooks live. Hooks can run commands during commit, checkout, merge, push, or other operations.

If Git automatically trusted every repository accessible to a user, a repository controlled by someone else could inject unwanted configuration or executable code into your workflow.

Therefore, Git checks ownership to distinguish repositories owned by the current user from repositories owned by another identity. When detecting a repository with dubious ownership, Git can refuse to read repository configuration or execute behaviors that depend on that configuration.

The **detected dubious ownership** message is a security boundary. Treat it as a prompt to verify the repository's origin, not an error to silence blindly with a fixed command.

## 2. Ownership vs. file permissions

Distinguish three concepts:

| Concept | Question answered | Example |
| --- | --- | --- |
| Ownership | Which account or UID owns the directory/file? | Repository folder belongs to root while Git runs under the dev account |
| Filesystem permissions/ACL | Is the current user permitted to read, write, or execute the file? | User has read access but lacks write access to .git/index |
| Git trust (safe.directory) | Does Git accept a repository owned by another user as trusted to process? | Allows a specific repository path even when owner differs from current user |

safe.directory only resolves Git's ownership trust check. It does not change owners, grant filesystem permissions, or repair ACLs.

If you lack write permission to a repository, adding safe.directory will not make git add, git commit, or other write operations succeed. In that case, fix operating system permissions per machine policy or ask an administrator.

## 3. Common situations that trigger dubious ownership

Common causes include:

- Cloning or extracting a repository under an administrator account, then running Git under a regular user account.
- Running sudo git clone or sudo git inside a project folder and continuing to work as another user.
- Using Docker/CI with a volume mount whose UID/GID inside the container differs from the host owner.
- Sharing a common working directory across multiple accounts on a build machine.
- Moving a repository over from another machine or account.
- Using network drives, NFS, WSL, or mounted folders with different ownership mappings.
- A linked worktree whose working directory or Git directory resides in a location with a different owner.

For example, you clone as root:

~~~bash
sudo git clone https://example.com/team/app.git /work/app
~~~

Then log in with a developer account and run:

~~~bash
cd /work/app
git status
~~~

If the folder belongs to root, Git may refuse because the current process runs under the developer identity.

A better approach is usually to clone and run Git using the same account that will work with the repository. Avoid running sudo for routine Git commands without a clear administrative reason.

## 4. Identifying the owner and the identity running Git

Before adding an exception, identify who is running Git and who owns the repository.

### Linux

Check the current identity:

~~~bash
id
id -u
id -un
~~~

Check the owner and permissions of the repository directory:

~~~bash
stat -c '%U:%G (%u:%g) %A %n' .
stat -c '%U:%G (%u:%g) %A %n' .git
~~~

The second command applies when .git is a directory. With a linked worktree, .git may be a file pointing to another Git directory; inspect the owner of both the working directory and the actual Git directory.

### macOS

~~~bash
id
stat -f '%Su:%Sg (%u:%g) %Sp %N' .
stat -f '%Su:%Sg (%u:%g) %Sp %N' .git
~~~

stat formatting on macOS differs from GNU/Linux; use the syntax matching your OS.

### Windows PowerShell

Check the current account:

~~~powershell
whoami
~~~

Check the owner of the working directory and .git:

~~~powershell
Get-Acl -LiteralPath . | Select-Object Owner
Get-Acl -LiteralPath .git | Select-Object Owner
~~~

If .git is a pointer file in a linked worktree, the command above shows the owner of the pointer file; the actual Git directory may live elsewhere and should be checked separately.

Do not inspect only a single source file's owner. Git may evaluate the working directory or the associated Git directory. When worktree or submodule layouts are complex, identify the exact path triggering the warning before changing configuration.

## 5. Identifying the exact repository path

safe.directory accepts trusted repository paths. Use an exact, absolute path pointing to the specific worktree or repository.

If Git operates normally, obtain the root path of the working tree:

~~~bash
git rev-parse --show-toplevel
~~~

For a bare repository without a working tree, the path to trust is the bare repository directory itself.

When Git is already blocking the repository due to dubious ownership, Git commands inside that repository may also be blocked. In that case, obtain the path via the shell or File Explorer first:

~~~bash
pwd -P
~~~

In PowerShell:

~~~powershell
(Get-Location).Path
~~~

Navigate to the repository root before capturing the path. If you are in a subdirectory, the current path is not necessarily the path that should be added to safe.directory.

Once the path is verified, you can apply a temporary command-line exception to inspect:

~~~bash
git -c safe.directory=/absolute/path/to/repository -C /absolute/path/to/repository status
~~~

-c applies the setting only for that single invocation. Use this only after confirming the repository is trustworthy; never use it to mask a repository of unknown origin.

## 6. How does safe.directory work?

safe.directory is a multi-valued configuration key. Each entry declares a repository path that Git may trust even when its owner differs from the current user.

Add a specific repository to global configuration:

~~~bash
git config --global --add safe.directory /absolute/path/to/repository
~~~

In Windows PowerShell, if the terminal is at the repository root:

~~~powershell
$repoPath = (Get-Location).Path
git config --global --add safe.directory $repoPath
~~~

Verify afterward:

~~~bash
git config --global --get-all safe.directory
git status
~~~

Global configuration applies to the current user across their repositories. This is usually the right scope when you need to trust a specific repository on a personal machine.

### Why must it reside in protected configuration?

Git only honors safe.directory when values come from protected configuration, such as system, global, or command scope. Values inside a repository's own local configuration are ignored for marking that repository safe.

This is crucial: if an untrusted repository could add safe.directory into .git/config itself, it could bypass the very check protecting the user.

Therefore, the following is not a valid solution:

~~~bash
git config --local safe.directory /path/to/repository
~~~

Use global for current-user exceptions or system when administrators must establish machine-wide policy.

### Inspecting configuration sources and scopes

~~~bash
git config --show-origin --show-scope --get-all safe.directory
~~~

The output shows which file and configuration scope each value comes from. This is how you locate previously added exceptions, especially when a repository is being trusted by a wildcard in system or global config.

## 7. Wildcards and overly broad trust scopes

Git supports several wildcard forms for safe.directory.

| Value | Trust scope |
| --- | --- |
| /work/team-a/app | Only the repository at that exact path |
| /work/team-a/* | Repositories directly under /work/team-a |
| * | Every repository, bypassing ownership checks |

Example wildcard for a workspace area:

~~~bash
git config --global --add safe.directory '/work/team-a/*'
~~~

The * value has the broadest impact:

~~~bash
git config --global --add safe.directory '*'
~~~

This configuration makes Git trust all repositories regardless of owner. It removes the ownership protection boundary and can cause Git to read configs or invoke hooks from repositories you do not truly trust.

Never use safe.directory '*' as a default fix on personal machines, shared hosts, or CI. If only one repository needs access, declare that exact path.

Directory wildcards must also be restricted to areas you control. Do not add a broad shared parent directory just to get one project working.

## 8. Removing or narrowing previously added exceptions

Check current values and their origins:

~~~bash
git config --show-origin --show-scope --get-all safe.directory
~~~

To remove one specific path from global config:

~~~bash
git config --global --fixed-value --unset-all safe.directory '/absolute/path/to/repository'
~~~

If you want to remove all safe.directory entries in global config:

~~~bash
git config --global --unset-all safe.directory
~~~

Note: the command above removes values only from the global file. If system config still contains a wildcard, that value can remain in effect.

To reset values inherited from lower-precedence configs and add only selected paths, add an empty value first:

~~~bash
git config --global --add safe.directory ''
git config --global --add safe.directory '/work/team-a/app'
~~~

An empty value resets the accumulated safe.directory list at the point Git parses configuration; entries declared afterward start a fresh list. Re-check origins and effective values after making changes.

Never remove administrator-managed system configuration if you do not have machine administration responsibilities. If a wildcard is applied from system config, coordinate with administrators to narrow the scope per policy.

## 9. Fixing ownership instead of adding an exception

If the repository ought to belong to the current account and ownership changed due to an earlier operation, the right fix may be restoring ownership at the OS level.

On Linux, an administrator can adjust ownership according to directory policy. The following example changes ownership recursively—use it only when the entire repository genuinely belongs to the current user and group:

~~~bash
sudo chown -R "$(id -u):$(id -g)" /absolute/path/to/repository
~~~

This operates across the whole directory tree; do not run it if the repository is shared or contains files requiring other owners. With linked worktrees, the Git directory may sit outside the working directory, so identify both locations before fixing.

On Windows, inspect the owner and ACLs via Security > Advanced in Properties or ask an administrator to adjust ownership per organizational policy. safe.directory does not replace fixing owners or ACLs.

If a repository is shared across multiple accounts, design appropriate group/ACL permissions and write access. A trust exception is not a collaboration permissions mechanism.

## 10. Containers, CI, and shared directories

Container environments frequently hit ownership errors when a host directory is mounted into a container with a different UID/GID. For example, the host creates files with UID 1000 while processes inside the container run as UID 1001.

Before adding safe.directory, check:

~~~bash
id
stat -c '%u:%g %n' /workspace /workspace/project
git config --show-origin --show-scope --get-all safe.directory
~~~

Remediation options to consider in order:

1. Run Git processes with a UID/GID matching the workspace owner.
2. Configure volume mounts and ownership properly during runner preparation.
3. If the workspace is a trusted source and differing ownership is intentional, add the exact workspace path to the job's protected config.
4. Use wildcards only if that directory area is tightly controlled and the trust scope has been evaluated.

In CI, avoid baking safe.directory=* into shared base images or global runner configuration merely to silence warnings. A job might process repositories supplied by untrusted pull requests or branches; overly broad trust increases risk when Git parses configs or runs hooks.

## 11. Running Git as root via sudo

On Linux, when Git runs as root inside a sudo environment, Git may inspect the SUDO_UID environment variable and also trust repositories owned by the UID that invoked sudo. This behavior allows certain administrative commands to still operate on the original user's repository.

Check the variable:

~~~bash
printf '%s' "$SUDO_UID"
~~~

If there is a clear reason for Git to trust only root-owned repositories during that invocation, you can unset SUDO_UID from the environment:

~~~bash
sudo env -u SUDO_UID git -C /path/to/repository status
~~~

This is specific to sudo environments, not a way to fix ownership. In normal development work, run Git under the account that owns the repository instead of running as root.

## 12. Workflow for handling a dubious ownership message

When encountering the error, follow this sequence:

1. Read the exact path in the message.
2. Verify the repository's origin and who created the directory.
3. Check the current user/UID along with the owner of the working tree and Git directory.
4. Determine whether this is an ownership issue or a filesystem permissions issue.
5. If ownership is wrong unintentionally, fix ownership per OS policy.
6. If the repository belongs to another owner but you have verified its origin and need to trust it, add that exact path to protected config.
7. Re-verify safe.directory along with its config origin and test with a read-only Git command.
8. Review repository configs and hooks before running operations that may execute code.

PowerShell example, after confirming the exact repository directory and trusted origin:

~~~powershell
Set-Location 'C:/work/team-app'
$repoPath = (Get-Location).Path
Get-Acl -LiteralPath . | Select-Object Owner
git config --global --add safe.directory $repoPath
git config --show-origin --show-scope --get-all safe.directory
git status
~~~

Linux example:

~~~bash
cd /work/team-app
id
stat -c '%U:%G (%u:%g) %A %n' .
git config --global --add safe.directory "$(pwd -P)"
git config --show-origin --show-scope --get-all safe.directory
git status
~~~

Add an exception only after confirming the repository is trustworthy. If you cannot verify the origin or owner, stop and ask an administrator to investigate.

## 13. Common mistakes and misconceptions

- **Adding safe.directory to fix missing write permissions:** this setting does not alter ACLs or filesystem permissions.
- **Putting safe.directory in .git/config:** Git ignores this value because it comes from the very repository being checked.
- **Using safe.directory=* to silence warnings:** this disables ownership checks broadly and removes the protection boundary.
- **Trusting an overly broad parent directory:** directory wildcards also expand trust scope; choose the narrowest directory possible.
- **Confusing author/committer with directory owner:** commit metadata does not determine filesystem repository ownership.
- **Running every Git command with sudo:** easily creates root-owned files and causes errors when returning to a regular user.
- **Recursively changing owners on a shared repository:** can break ownership and ACLs that the team relies on.
- **Ignoring system configuration:** a wildcard from system config can remain active after deleting global entries.
- **Assuming safe.directory proves repository contents are safe:** it only permits Git to process the repository per trust policy; you still must review provenance, configuration, and hooks.

## 14. Decision flow diagram

~~~mermaid
flowchart TD
    A[Git reports detected dubious ownership] --> B[Identify exact repository path]
    B --> C[Check current user and owner]
    C --> D{Is owner wrong unintentionally?}
    D -- Yes --> E[Fix ownership or ACLs per policy]
    D -- No --> F{Does repository have a trusted origin?}
    F -- No --> G[Stop and ask administrator to verify]
    F -- Yes --> H[Add exact path to protected safe.directory]
    E --> I[Verify permissions and Git status]
    H --> J[Verify config origin and Git status]
    I --> K[Review config and hooks]
    J --> K
    K --> L[Continue work]
~~~

Before finishing, verify for yourself:

1. Have I verified the repository's origin and actual owner?
2. Is the issue ownership or filesystem permissions?
3. Have I identified the exact worktree/Git directory path?
4. Was safe.directory added in global/system/command config rather than local config?
5. Does the exception cover only the repository or directory scope actually needed?
6. Have I checked for wildcards and values inherited from system config?
7. Do I trust the repository's configuration and hooks before letting Git process it?

Directory ownership is part of the security boundary when Git processes a repository. safe.directory is an intentional exception list, not a file-permission repair tool or a way to suppress warnings globally. Verify ownership and origin first, fix ownership when it is an environment mistake, and add only specific paths when you genuinely trust the repository.

## References

- [Git documentation: git-config — safe.directory](https://git-scm.com/docs/git-config#Documentation/git-config.txt-safedirectory) — protected configuration, multi-valued entries, wildcards, and empty values.
- [Git documentation: git-config — protected configuration](https://git-scm.com/docs/git-config#SCOPES) — configuration scopes treated as protected.
- [Git documentation: git](https://git-scm.com/docs/git) — -c and -C options and general Git command behavior.
- [Git security advisory CVE-2022-24765](https://github.blog/2022-04-12-git-security-vulnerability-announced/) — security context regarding repository ownership and Git handling untrusted repositories.
