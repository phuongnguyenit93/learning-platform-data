# Executable permissions, core.filemode, and the limits of Git metadata

When a project is developed across Windows, Linux, and macOS, the same file can appear with different system permissions on each machine. For instance, a shell script may have executable permissions on Linux, yet when checked out on a filesystem that does not represent executable bits in the way Git expects, Git may fail to detect that change. To collaborate reliably, you need to understand at what level Git stores file permissions, how `core.filemode` affects behavior, and which metadata sits outside Git's storage model.

Git does record a portion of information about file types and executable permissions. For regular files, Git distinguishes between executable and non-executable states. Git does not store full POSIX permissions, Windows ACLs, ownership, modification timestamps, or all filesystem attributes. Thus, a repository stores the state needed for collaboration, but it is not a complete copy of operating system metadata.

## 1. At what level does Git store file permissions?

In a Git tree, a regular file typically has one of two modes:

| Mode | Meaning |
|---|---|
| `100644` | Regular non-executable file |
| `100755` | Regular executable file |

These two modes are octal representations inside Git's tree/index structures. The `100` prefix denotes the object type as a regular file; the trailing digits distinguish whether the file has executable permission or not. Git does not record individual read/write bits separately for owner, group, and others like a POSIX filesystem does.

Git also represents several other entry types in a tree:

| Mode | Entry type | Meaning |
|---|---|---|
| `120000` | Symbolic link | A symlink; the blob contains the target path of the link |
| `160000` | Gitlink | A reference to a submodule's commit |
| `040000` | Tree | A directory represented by a subtree; empty directories are not stored as standalone entries |

For a regular file, what Git needs to know for collaboration is whether the file is marked executable. For example, a deployment script meant to be run directly can be stored with mode `100755`; configuration files or regular source code are typically `100644`.

## 2. Git does not store full filesystem permissions and metadata

Git focuses on content, paths, tree structure, entry types, and certain attributes needed to reconstruct the repository. The following items are generally not stored in commits as file metadata:

| Operating system metadata | Stored by Git in commit? | Notes |
|---|---|---|
| File contents | Yes | Stored as blob objects |
| Paths and directory structure | Yes | Represented via tree objects |
| Executable bit of regular files | Yes | Distinguishes modes `100644` and `100755` |
| Symbolic link type | Yes | Mode `120000`, blob contains target path |
| Submodule reference | Yes | Gitlink mode `160000` pointing to submodule commit |
| Granular read/write bits for owner, group, others | No | Git does not store full POSIX permission bits |
| Owner and group ownership | No | Not restored from commit on checkout |
| NTFS ACLs or POSIX ACLs | No | Must be managed by deployment systems or server configuration |
| Creation, access, and modification timestamps | No | Checkout creates new filesystem timestamps on the current machine |
| Windows hidden, system, archive, read-only attributes | No | Not standard metadata stored in Git commits |
| Extended attributes and filesystem-specific metadata | No | Requires separate tools or processes if the project depends on them |
| Hard links between paths | No | Git stores paths and contents, not hard-link relationships |

This means checking out the same commit on two machines does not guarantee identical filesystem permissions and metadata details. Git restores the state managed by its model; the operating system and filesystem determine the remaining details.

If your deployment process requires specific users/groups, ACLs, granular read/write permissions, or file ownership, configure them in your deployment tools, images/containers, packages, or installation scripts. You cannot rely on Git commits to recreate those permissions.

## 3. `core.filemode` controls executable change detection

`core.filemode` is a setting indicating whether Git should trust changes to the executable bit in the working tree when comparing against the index.

```bash
# View configured value and configuration source
git config --show-origin --get core.filemode

# Enable executable change detection in the current repository
git config --local core.filemode true

# Disable executable change detection in the current repository
git config --local core.filemode false
```

If `git config --get core.filemode` returns no value, it means no value has been explicitly configured in the scopes being read. Git uses default behavior appropriate to the platform and filesystem capabilities; during a clone, Git may set this configuration based on whether the filesystem reliably supports the executable bit.

### When `core.filemode=true`

Git checks executable changes in the working tree. If a tracked file changes from non-executable to executable, `git status` and `git diff` can report a mode change even though file contents are unchanged.

On filesystems that reliably support executable permissions, this is the right setting so Git automatically recognizes changes from `chmod`.

### When `core.filemode=false`

Git ignores executable bit differences observed in the working tree when comparing with the index. This setting is useful on filesystems that do not preserve or reliably report the executable bit, such as certain Windows environments or shared filesystems.

`core.filemode=false` only affects detecting mode changes from the working tree. It does not remove modes already stored in commits, nor does it prevent you from explicitly setting the mode in the index using `git update-index --chmod`.

### Choosing the right configuration scope

| Command | Scope |
|---|---|
| `git config --local core.filemode false` | Current repository only |
| `git config --global core.filemode false` | Repositories for the current user, unless overridden by a higher-precedence configuration |
| `git config --system core.filemode false` | System-wide Git, usually requiring administrator privileges |

Do not set `core.filemode=false` globally just to hide an unexpected permission change in one repository. Identify each project's filesystem and needs before choosing a scope. If only one repository has the issue, `--local` configuration is usually easier to control.

## 4. Changing executable permissions on Linux and macOS

On POSIX filesystems supporting the executable bit, you can use `chmod`:

```bash
# Enable executable permission for a script
chmod +x scripts/deploy.sh

# Check if Git detects the mode change
git status --short
git diff --summary
```

If Git is tracking mode changes, the output may look like:

```text
 mode change 100644 => 100755 scripts/deploy.sh
```

Then stage and inspect the staged change:

```bash
git add scripts/deploy.sh
git diff --cached --summary
git ls-files --stage -- scripts/deploy.sh
```

If the file needs to revert to non-executable:

```bash
chmod -x scripts/deploy.sh
git add scripts/deploy.sh
git diff --cached --summary
```

When contents do not change, the diff may show only the mode change. Verify the exact path before committing to avoid accidentally changing permissions on many files.

## 5. Setting the mode in the index with `git update-index --chmod`

In environments where `chmod` cannot change or Git cannot detect the executable bit, you can set the mode directly in the index:

```bash
# Mark a tracked file as executable in the index
git update-index --chmod=+x scripts/deploy.sh

# View current mode in the index
git ls-files --stage -- scripts/deploy.sh

# View staged differences against the current commit
git diff --cached --summary
```

`git update-index --chmod=+x` instructs Git to record the file in executable mode in the index. `--chmod=-x` sets it back to non-executable mode:

```bash
git update-index --chmod=-x scripts/deploy.sh
git diff --cached --summary
```

For a new file not yet in the index, add the file first and then set the mode:

```bash
git add scripts/deploy.sh
git update-index --chmod=+x scripts/deploy.sh
git diff --cached --summary
```

This command adjusts the mode in the index so the next commit saves the correct state. It is not a tool for changing full ACLs or actual filesystem permissions. On a Windows machine, the file still may not have a Linux-style executable concept, yet the commit can still record mode `100755` so POSIX environments check out the proper executable permission.

## 6. Inspecting modes in the index and commits

There are three states to distinguish:

- **Working tree:** permissions currently exposed by the filesystem for the file.
- **Index:** mode that will be written to the next commit.
- **Commit:** mode already stored in the commit's tree.

The following commands inspect each place:

```bash
# View permissions displayed by the OS (on Unix-like systems)
ls -l scripts/deploy.sh

# View staged mode in the index
git ls-files --stage -- scripts/deploy.sh

# View committed mode in HEAD
git ls-tree HEAD -- scripts/deploy.sh

# View summary of unstaged mode changes
git diff --summary

# View summary of staged mode changes
git diff --cached --summary
```

For example, `git ls-files --stage` may return:

```text
100755 2f7c... 0    scripts/deploy.sh
```

The number `100755` is the mode currently in the index. If `git ls-tree HEAD -- scripts/deploy.sh` still shows `100644`, it indicates the executable mode has not yet been recorded in the current commit, even though the index has been updated.

After committing:

```bash
git commit -m "Mark deployment script executable"
git ls-tree HEAD -- scripts/deploy.sh
git show --summary --format=short HEAD
```

Confirm the commit shows the desired mode. When cloned or checked out on Linux/macOS with a supporting filesystem, Git can restore the executable bit from the stored mode.

## 7. Working across multiple operating systems

A repository can be checked out on Windows, Linux, and macOS. Different operating systems and filesystems do not represent permissions identically:

| Environment | Typical capability | How to collaborate |
|---|---|---|
| Linux | POSIX filesystems usually support the executable bit | Use `chmod` and let Git detect it when `core.filemode=true` |
| macOS | Filesystems usually support the executable bit | Use `chmod`; verify mode before committing |
| Windows with NTFS | Permission and attribute model differs from POSIX; Git may not detect executable bits like on Unix | Check `core.filemode`; use `git update-index --chmod` when explicitly recording modes |
| Shared filesystems or special mounts | May map or strip permission differences | Check actual behavior; configure `core.filemode` appropriately for the repository |

For example, suppose a team has `scripts/deploy.sh` that must be executable on Linux. A Windows team member edits the script's content but cannot set the executable bit in the usual way. That member can stage the content and then set the mode in the index:

```bash
git add scripts/deploy.sh
git update-index --chmod=+x scripts/deploy.sh
git diff --cached --summary
git commit -m "Update deployment script and executable mode"
```

When a Linux team member fetches and checks out this commit, Git can set the executable bit per mode `100755`, provided the filesystem and local configuration support it. Windows users should not conclude the mode in the repository is wrong simply because File Explorer does not show Linux-style execute permissions.

If a team member frequently sees unexpected mode changes when checking out or copying files across filesystems that do not preserve permissions, inspect `core.filemode` in that repository. Disabling mode detection can reduce noise, but intentional executable changes must then be staged explicitly.

## 8. Symbolic links and platform limitations

Git can store a symbolic link as a mode `120000` entry. Its blob contains the link's target path, not the target file's contents. On checkout, Git needs a filesystem and user privileges that support creating symbolic links.

In environments lacking support or permission to create symlinks, setting `core.symlinks=false` can cause Git to check out symlinks as regular files containing the target path. This is separate from `core.filemode`:

| Setting | Controls |
|---|---|
| `core.filemode` | Whether to trust executable bit changes on regular files in the working tree |
| `core.symlinks` | Whether to create actual symbolic links on checkout or use a regular-file representation |

Do not use `core.filemode` to fix symlink errors, and do not use `core.symlinks` to handle executable permissions. When a project relies on symlinks, check OS policies, user permissions, and each team member's clone configuration.

## 9. Metadata that must be managed outside Git

Because Git does not store full OS permissions, several requirements must be handled elsewhere in your workflow:

- **Owner and group:** create appropriate users/groups in the server, container, or deployment step.
- **ACLs and read/write permissions:** configure with OS tools, Ansible, provisioning scripts, or infrastructure policies.
- **File timestamps:** do not use mtime or ctime to identify versions; use commits, tags, and object IDs.
- **Windows attributes:** set hidden/read-only/system via scripts or deployment tools if the application needs them.
- **Extended attributes:** back up and restore with filesystem-aware tools if data requires these attributes.
- **Executable permissions:** store the executable bit in Git if required by the repository; verify actual permissions after deployment as well.

For example, an application may require a configuration file readable only by its owner. Git can store sample configuration content, while mode `0600` must be applied during deployment:

```bash
install -m 600 config/production.example /etc/sample-app/production.conf
chown sample-app:sample-app /etc/sample-app/production.conf
```

These are operations on the target machine. Git commits do not store owner, group, or mode `0600` to automatically restore them on every machine.

## 10. Diagnostic workflow when modes change unexpectedly

When `git status` reports a mode change or a script fails to run after checkout, check in this order:

```bash
# 1. Check filemode setting and configuration source
git config --show-origin --get core.filemode

# 2. Check changes Git is detecting
git status --short
git diff --summary

# 3. Compare mode in the index and commit
git ls-files --stage -- scripts/deploy.sh
git ls-tree HEAD -- scripts/deploy.sh

# 4. If the filesystem supports it, check actual permissions
ls -l scripts/deploy.sh
```

After identifying the cause:

- If the file truly needs to be executable and the filesystem supports it, use `chmod +x` and stage it.
- If Git does not detect the mode because `core.filemode=false` or the filesystem cannot represent permissions, use `git update-index --chmod=+x`.
- If the file should not be executable, reset the mode with `chmod -x` or `git update-index --chmod=-x`.
- If read/write permissions, owner, or ACLs are wrong, fix them on the filesystem or in the deployment process; Git has no corresponding metadata to restore them.

Then re-check `git diff --cached --summary` and `git ls-files --stage`, and commit once the index reflects your intent.

## 11. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Git stores all POSIX file permissions | Git mainly distinguishes executable and non-executable regular files; it does not store full owner/group or read/write bits. |
| `core.filemode=false` removes the executable bit from commits | No. It only makes Git ignore executable changes detected from the working tree. |
| `chmod +x` is always detected by Git on every OS | Only when the filesystem and configuration allow Git to observe that change. |
| `git update-index --chmod=+x` changes machine ACLs | No. It sets the executable mode in the index so the commit records it. |
| Checkout restores previous owner and modification time | No. The filesystem creates ownership and timestamps according to the current environment. |
| `core.filemode` and `core.symlinks` are the same setting | No. One controls executable bit detection; the other controls checking out symbolic links. |
| Mode `100755` means Git stores exact `rwxr-xr-x` permissions across all OSes | It is an executable marker for a regular file in Git's model, not a complete backup of filesystem permission bits. |

## 12. Self-check

1. **Which mode represents an executable regular file in Git?**
   - `100755`.
2. **What does `core.filemode=false` affect?**
   - Git ignores executable bit changes detected from the working tree when comparing against the index.
3. **Which command sets the executable mode directly in the index?**
   - `git update-index --chmod=+x <path>`.
4. **Does Git store file owner, group, and ACLs?**
   - No. Those metadata items must be managed outside Git.
5. **Which entry type does mode `120000` represent?**
   - Symbolic link.
6. **Why should you inspect both `git ls-files --stage` and `git ls-tree HEAD`?**
   - The first shows the mode in the index; the second shows the mode already stored in the current commit.

## Conclusion

Git stores content, path structure, entry types, and the executable state of regular files via mode `100644` or `100755`. `core.filemode` determines whether Git detects executable changes from the working tree; `git update-index --chmod` allows explicitly setting the mode in the index when the filesystem lacks good support. Owner, group, ACLs, timestamps, and many other OS attributes sit outside commit metadata, so they must be configured in the deployment environment. Properly distinguishing what Git stores from what the filesystem manages keeps repositories working consistently across Windows, Linux, and macOS.
