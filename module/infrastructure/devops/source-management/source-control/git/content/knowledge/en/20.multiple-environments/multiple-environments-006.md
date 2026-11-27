# Symbolic links and support differences across operating systems

A symbolic link (commonly called a **symlink**) is a filesystem entry that points to another path. Symlinks allow multiple locations to reference the same file or directory without duplicating data. In Git projects, symlinks are often used to share configuration, assets, or common directories.

Git can store symlinks in a repository, but how a symlink appears in the working tree depends on the operating system, filesystem, and user permissions. Linux and macOS typically support symlinks directly; Windows also supports them, though Developer Mode or symbolic link creation privileges may be required. If an environment cannot create symlinks, Git can check them out as plain text files containing the target path.

Understanding how Git stores symlinks and these differences helps avoid situations where one team member sees a working link while another sees only a text file or encounters checkout errors.

## 1. What is a symlink?

A symlink is a filesystem entry containing a path to another target. When a program accesses a symlink, the OS generally resolves the path and redirects the operation to the link's target.

For example, suppose a project has the structure:

~~~text
project/
├── config/
│   └── app.yml
└── deploy/
    └── app.yml -> ../config/app.yml
~~~

The file deploy/app.yml is a symlink pointing to config/app.yml. When the application reads deploy/app.yml, the OS redirects the read to the target file.

A symlink can point to:

- A file.
- A directory.
- A relative or absolute path.
- A non-existent target (a dangling symlink).

A symlink can be structurally valid even if the target does not yet exist, though an application accessing the link will not be able to read target content until that path exists.

### Distinguishing symlinks, hard links, and shortcuts

| Link type | How it works | Characteristics |
|---|---|---|
| Symbolic link | Stores a path to a target | Can point to a file or directory, even a non-existent target; can cross filesystems |
| Hard link | Creates an additional name for the same file object/inode | Generally not used for directories; constrained to the same filesystem and volume |
| Windows shortcut (.lnk) | A shortcut file handled by Windows Shell | Not a symlink that Git stores under symlink mode |

A .lnk file is typically treated by Git as a regular file. Applications reading paths directly may not understand that shortcut. If a project needs links recognized consistently by CLI tools and Git, use an actual symlink.

## 2. How does Git store symlinks?

Git does not copy the target file's contents into the repository when adding a symlink. Git stores:

1. A blob containing the exact target path string of the symlink.
2. A special file mode in the tree/index to mark that entry as a symlink.

The mode of a symlink is **120000**. When Git checks out in a supporting environment, Git uses this information to create a symlink in the working tree.

Example:

~~~text
Index / Git tree
100644  blob   -> regular file
100755  blob   -> file with executable bit
120000  blob   -> symbolic link
~~~

For the symlink deploy/app.yml pointing to ../config/app.yml, the symlink's blob contains the string:

~~~text
../config/app.yml
~~~

Git stores the target path, not the contents of config/app.yml, inside the symlink blob. The target file is tracked separately if it also resides in the repository.

You can visualize this as:

~~~text
Git tree
  deploy/app.yml
    mode: 120000
    blob: "../config/app.yml"

Working tree on a supporting OS
  deploy/app.yml  --symlink-->  config/app.yml

Working tree when core.symlinks=false
  deploy/app.yml  --regular file containing text-->  "../config/app.yml"
~~~

Key takeaway: the entry type recorded in the Git index/tree remains a symlink. Whether it checks out as a real symlink or a text file depends on configuration and environment capabilities.

## 3. Creating symlinks on Linux and macOS

On Linux and macOS, the standard command to create a symlink is **ln -s**.

Create a symlink to a file:

~~~bash
ln -s ../config/app.yml deploy/app.yml
~~~

Create a symlink to a directory:

~~~bash
ln -s ../shared-assets deploy/assets
~~~

A relative target path is resolved from the directory containing the symlink. In the first example, deploy/app.yml points to ../config/app.yml, meaning go up one level from deploy and then into config.

Inspect the link:

~~~bash
ls -l deploy
readlink deploy/app.yml
~~~

ls -l typically displays an arrow and the link target. readlink prints the path string stored inside the symlink.

If the target is a directory, the link is still created with ln -s. No separate directory flag is needed on Linux/macOS.

## 4. Creating symlinks on Windows

Windows supports symbolic links, though creating them can depend on the Windows version, Developer Mode, account privileges, and machine policies.

There are three common ways.

### Using PowerShell

Create a symlink to a file:

~~~powershell
New-Item -ItemType SymbolicLink -Path .\deploy\app.yml -Target ..\config\app.yml
~~~

Create a symlink to a directory:

~~~powershell
New-Item -ItemType SymbolicLink -Path .\deploy\assets -Target ..\shared-assets
~~~

### Using Command Prompt

In Command Prompt (cmd.exe), use mklink:

~~~cmd
mklink deploy\app.yml ..\config\app.yml
mklink /D deploy\assets ..\shared-assets
~~~

The /D option creates a directory symbolic link. mklink is a cmd.exe command; if you are in PowerShell, you can run cmd /c mklink or use New-Item.

### Using Git Bash

Git Bash provides the ln command:

~~~bash
ln -s ../config/app.yml deploy/app.yml
~~~

This is convenient when a team uses the same command across documentation for Linux, macOS, and Git Bash. However, Git Bash still requires Windows to allow creating real symbolic links. If privileges or system capabilities are missing, the operation may fail or Git may be configured to check out symlinks as regular files.

### Permissions to create symlinks on Windows

On Windows, creating a symbolic link may require the "Create symbolic links" privilege or having Developer Mode enabled. In some enterprise environments, machine policies may restrict this feature.

If a command reports errors such as "privilege not held" or "access denied":

1. Confirm you are creating the right type of symbolic link.
2. Check Developer Mode or account privileges.
3. Check machine policies and the filesystem.
4. Check Git's core.symlinks configuration.
5. Only change configuration after confirming the environment can create real symlinks.

Do not run every terminal as Administrator solely to bypass errors without understanding machine policies. Use the privilege mechanisms approved by your organization.

## 5. Adding symlinks to Git

After creating a symlink, add it to the staging area like a normal file:

~~~bash
git add deploy/app.yml
git status --short
git diff --cached --summary
~~~

To confirm Git recognizes it properly as a symlink, check the mode in the index:

~~~bash
git ls-files --stage -- deploy/app.yml
~~~

Sample output:

~~~text
120000 4b825dc642cb6eb9a060e54bf8d69288fbee4904 0 deploy/app.yml
~~~

The hash in this example is illustrative only. The key detail is mode 120000. If Git displays 100644, the entry is staged as a regular file rather than a symlink.

View the target string stored in the index:

~~~bash
git show :deploy/app.yml
~~~

View the committed content:

~~~bash
git show HEAD:deploy/app.yml
~~~

These two commands display the blob containing the symlink's target path. They do not open the target file's contents the way an application does when following the link in the filesystem.

After verifying:

~~~bash
git commit -m "Add shared app config symlink"
~~~

## 6. How does core.symlinks affect checkout?

Git provides the **core.symlinks** setting to control how symlinks are handled in the working tree.

Check the configuration:

~~~bash
git config --show-origin --get core.symlinks
~~~

If the command prints no output, the setting may not be explicitly configured. Git generally defaults to supporting symlinks, though when cloning in an environment unable to create symlinks, Git may set core.symlinks=false for that repository.

### core.symlinks=true

When enabled, Git attempts to check out mode 120000 entries as real symlinks on the filesystem.

~~~bash
git config --local core.symlinks true
~~~

Set true only when the environment can create symlinks. If Windows lacks the necessary privileges or the filesystem does not support them, checkout may fail.

### core.symlinks=false

When disabled, Git checks out symlinks as regular files whose contents are the target path string:

~~~bash
git config --local core.symlinks false
~~~

For example, deploy/app.yml may become a text file containing only:

~~~text
../config/app.yml
~~~

In the repository, the index still records mode 120000. This is a compatibility mechanism for working with repositories containing symlinks in environments that cannot create real symlinks. It does not convert symlinks in Git history into regular files.

If you enable core.symlinks after checkout, the existing working tree does not necessarily convert immediately. Check first and re-checkout the relevant entry after safeguarding any edits:

~~~bash
git status
git config --local core.symlinks true
git restore --source=HEAD --worktree -- deploy/app.yml
~~~

The restore command above tells Git to re-checkout the entry from HEAD. Use it only when you have no local edits to keep at that path. Afterward, verify with OS tools and git ls-files --stage.

For a fresh clone, ensure symlink creation capability is ready beforehand so Git detects the environment accurately from the start.

## 7. Symlink support differences across operating systems

| Environment | Typical support | Things to watch out for |
|---|---|---|
| Linux | Filesystem-level symlink support | Target access permissions, mount options, and filesystem can affect behavior |
| macOS | Filesystem-level symlink support | APFS/HFS+ and access permissions; volumes may have different settings |
| Windows 10/11 | Supports symlinks | May require Developer Mode or symlink creation privileges; Git may set core.symlinks=false |
| WSL | Supports symlinks in Linux filesystem | Interoperability depends on whether the symlink resides on Linux or Windows filesystems and how mounts are configured |
| Network share, removable drive, or restricted filesystem | Depends on filesystem and policy | May not create, follow, or resolve symlinks like a local filesystem |

Do not infer solely from the OS name that all drives share identical support. For example, a Linux machine may access a restricted filesystem or mount; a Windows machine may support symlinks on an NTFS drive but not on another volume.

When a team works across multiple operating systems, verify actual filesystem capabilities and Git configuration in each environment.

## 8. Relative and absolute paths

A symlink can store a relative or absolute path.

Relative path example:

~~~bash
ln -s ../config/app.yml deploy/app.yml
~~~

Absolute path example:

~~~bash
ln -s /home/alex/project/config/app.yml deploy/app.yml
~~~

Absolute paths typically depend on a specific machine. On another machine, the username, drive letter, or checkout location may differ, breaking the link.

For shared repositories, prefer relative paths within the project structure:

- Do not point symlinks into a personal home directory.
- Do not use machine-specific drive paths like D:/workspace/... if the repository is shared by multiple people.
- Verify relative paths from the symlink's location, not from the repository root.
- If a target must reside outside the repository, clearly document the environment requirement and setup instructions.

Relative symlinks are much more portable with the repository. However, if the directory structure changes, the target path will also need updating.

## 9. Path separators and portability

Git stores path names in trees using forward slashes (/). The path inside a symlink is blob content, so the target string is stored exactly as created.

On Linux and macOS, backslashes are not interpreted as directory separators in Unix paths. On Windows, both / and \ are accepted in many path contexts, though how tools process them can vary.

To improve portability:

- Prefer relative symlinks.
- Use / in targets when creating symlinks via Git Bash or tools that support this syntax.
- Avoid committing absolute Windows paths into a cross-platform repository.
- Verify targets after cloning on each supported operating system.
- Do not assume all build tools resolve symlinks identically.

A symlink with a target using backslashes may work on Windows yet be interpreted as a filename containing literal backslash characters on Unix. Writing portable targets is therefore critical.

## 10. Differences in case sensitivity

Git stores filenames with exact capitalization, while filesystems may handle them differently.

- Linux usually distinguishes App.yml and app.yml as two distinct names.
- Windows usually does not distinguish case in filenames.
- macOS usually uses a case-insensitive filesystem by default, though case-sensitive volumes can be created.

This affects both symlinks and target files. For example, a symlink pointing to Config/App.yml may work on Windows or case-insensitive macOS, yet break on Linux if the actual repository path is config/app.yml. The discrepancy may only surface when another teammate checks out on a case-sensitive filesystem.

Git provides core.ignorecase to adapt to case-insensitive filesystems. Check:

~~~bash
git config --show-origin --get core.ignorecase
~~~

Git normally auto-detects and sets the appropriate value during init or clone. Do not change core.ignorecase merely to hide filename discrepancy bugs.

When performing a case-only rename, you can use an intermediate name:

~~~bash
git mv config.yml config.tmp
git mv config.tmp Config.yml
git status
~~~

Then inspect the diff and commit. This helps Git recognize the rename on filesystems that do not support two names differing only by casing.

## 11. Differences in executable bits and core.filemode

In addition to symlinks, Git tracks certain file modes, including the executable bit. On Linux and macOS, execute permission is typically represented via mode 100755; regular files are typically 100644.

Windows does not use Unix executable bits in the same way. Git for Windows commonly sets core.filemode=false when the filesystem does not accurately reflect execute permissions.

Check:

~~~bash
git config --show-origin --get core.filemode
git ls-files --stage -- scripts/deploy.sh
~~~

Common modes:

| Mode | Meaning |
|---|---|
| 100644 | Regular file, without executable bit |
| 100755 | Regular file with executable bit |
| 120000 | Symlink |

core.filemode controls whether Git treats permission bit changes as file modifications. It is not a symlink setting; core.symlinks is the setting related to checking out symlinks.

If a script must run on Linux/macOS, check its mode in the index rather than looking only at file properties on Windows. You can update the executable bit in Git using:

~~~bash
git update-index --chmod=+x scripts/deploy.sh
~~~

This command updates the mode in the index. Verify with git ls-files --stage before committing.

## 12. Changing a symlink's target

To change the target, recreate the symlink with the new path. On Linux/macOS or Git Bash:

~~~bash
rm deploy/app.yml
ln -s ../config/app-v2.yml deploy/app.yml
~~~

The rm command here deletes the symlink itself, not the target file. Do not run recursive delete commands unless you understand where the path points.

In PowerShell, you can remove and recreate the link with:

~~~powershell
Remove-Item -LiteralPath .\deploy\app.yml
New-Item -ItemType SymbolicLink -Path .\deploy\app.yml -Target ..\config\app-v2.yml
~~~

Then verify Git detects the change:

~~~bash
git status --short
git diff --summary
git diff
~~~

Because the target is stored as blob content, changing the target string causes Git to show a diff for the symlink. The mode remains 120000 as long as the entry is still a symlink.

If you accidentally replace a symlink with a regular file, the mode can change from 120000 to 100644. Check the staged mode with git ls-files --stage and restore it as a symlink before committing.

## 13. Inspecting symlinks in the working tree

On Linux/macOS/Git Bash:

~~~bash
ls -l deploy/app.yml
readlink deploy/app.yml
test -L deploy/app.yml && echo "is symlink"
~~~

In modern PowerShell:

~~~powershell
$item = Get-Item -LiteralPath .\deploy\app.yml
$item | Format-List FullName,Attributes,LinkType,Target
~~~

If Git checked out a symlink as a regular file due to core.symlinks=false, filesystem checks will report a regular file. The file's content will usually be the target string. Do not open the file, see a path string, and assume Git stored it wrong; check the mode in the index.

Check the Git index:

~~~bash
git ls-files --stage -- deploy/app.yml
~~~

Check the committed target blob:

~~~bash
git show HEAD:deploy/app.yml
~~~

Cross-check all three views: filesystem, index, and commit. They answer three distinct questions: what the working tree currently holds, what entry type Git is about to commit, and what target history stores.

## 14. Common errors

| Symptom | Possible cause | How to check or resolve |
|---|---|---|
| Creating symlink on Windows reports Access denied | Missing privilege or Developer Mode not enabled | Check machine policies and symbolic link creation privileges |
| After cloning, symlink is a text file | core.symlinks=false or environment cannot create symlinks | Inspect mode 120000 and core.symlinks configuration |
| Git reports a symlink, but the app cannot read it | Wrong target, missing target, or incompatible path | Use readlink/Get-Item and verify the target from the symlink's location |
| Works on Linux but fails on Windows | Windows lacks privileges, paths differ, or filesystem lacks support | Check privileges, filesystem, target, and Git configuration |
| Works on Windows but fails on Linux | Target contains backslashes or depends on Windows paths | Use a relative target with forward slashes (/) |
| Git shows mode 100644 instead of 120000 | Entry is a regular file or Windows .lnk shortcut, not a staged symlink | Check entry type on filesystem and create a real symlink before staging; stub files created by core.symlinks=false still keep mode 120000 in the index |
| Target file was modified unexpectedly | A tool followed the symlink and wrote to the target | Identify the target and inspect build tools/scripts |
| Case-only rename goes unrecognized | Case-insensitive filesystem | Rename via an intermediate name and verify with git status |

When encountering an error, do not rush to delete files or change global settings. Determine which mode Git stores, what entry type exists in the working tree, and what the actual target is.

## 15. Symlinks and repository safety

A symlink can point outside the repository directory. Git stores the target path, without guaranteeing the target lies inside the repository or exists on every machine.

For example, a symlink could point to a parent directory:

~~~bash
ln -s ../../private-config deploy/private
~~~

When a build tool, script, or editor opens deploy/private, it can access data outside the repository depending on the user's permissions.

When receiving a repository from an untrusted source:

- Inspect symlinks in the diff before running scripts or builds.
- Check targets with readlink or an equivalent tool.
- Be cautious of symlinks pointing to configuration, credential, or personal directories.
- Do not run automated scripts until you understand which links they follow.
- Avoid placing symlinks pointing outside the repository unless the project has an explicit reason.

A symlink itself does not grant extra access privileges; a program following the link still runs with the current user's permissions. The risk lies in a tool reading or writing a path outside the scope the user expects to operate on.

## 16. Cross-OS collaboration workflow

Suppose a team has members using Linux, macOS, and Windows. The repository uses the symlink deploy/app.yml pointing to config/app.yml.

A consistent workflow can include:

**Step 1 — Agree on a relative target**

~~~text
deploy/app.yml -> ../config/app.yml
~~~

Do not use absolute paths tied to a specific machine.

**Step 2 — Verify the environment**

On Windows, check symlink creation privileges and core.symlinks. On Linux/macOS, confirm filesystem and target access permissions.

**Step 3 — Create the symlink and stage it**

~~~bash
ln -s ../config/app.yml deploy/app.yml
git add deploy/app.yml
~~~

On Windows, use Git Bash if capable of creating symlinks, or New-Item/mklink according to machine policy.

**Step 4 — Verify mode and target**

~~~bash
git ls-files --stage -- deploy/app.yml
git show :deploy/app.yml
~~~

The expected result is mode 120000 and the correct relative target.

**Step 5 — Commit and push**

~~~bash
git commit -m "Add portable config symlink"
git push
~~~

**Step 6 — Verify after cloning on another OS**

Each team member verifies the Git index and working tree. If Windows checks it out as a regular file, inspect core.symlinks and symlink creation privileges before concluding the repository is broken.

The team should document environment requirements in project docs, such as needing Developer Mode enabled on Windows or a filesystem supporting symlinks. This helps newcomers understand why the same repository may be checked out differently.

## 17. Pre-commit checklist for symlinks

- [ ] Is the target accurate and present in the required environments?
- [ ] Is the target relative to avoid machine-specific dependencies?
- [ ] Does the path use separators compatible with the target operating systems?
- [ ] Does the symlink point outside the repository?
- [ ] Does the Git index show mode 120000?
- [ ] Does the blob in the index contain the exact target string?
- [ ] Do Windows team members have symlink creation privileges or understand core.symlinks limitations?
- [ ] Are any filenames differing only by case?
- [ ] Do scripts/build tools handle symlinks accurately and safely?

## 18. Key takeaways

- A symlink is a filesystem entry pointing to another path; it differs from hard links and Windows shortcuts.
- Git stores symlinks using mode 120000 and a blob containing the target string.
- Linux and macOS generally support symlinks directly; Windows supports them but may require Developer Mode or appropriate privileges.
- core.symlinks=true instructs Git to create real symlinks; core.symlinks=false checks them out as regular files containing the target.
- The Git index can still preserve mode 120000 even when the working tree shows a text file due to compatibility settings.
- Prefer relative targets and avoid absolute paths tied to individual machines.
- Git stores case-sensitive path names, while default Windows/macOS filesystems are usually case-insensitive.
- core.filemode relates to the executable bit; core.symlinks relates to symlinks.
- Inspect the filesystem, index, and commit separately when diagnosing issues.
- Review symlinks from untrusted repositories because tools may follow links to data outside the repository.

Symlinks let repositories reference shared resources without duplicating data. When you understand mode 120000, the core.symlinks configuration, and each operating system's capabilities, a team can design links that are portable, inspectable, and reliable across multi-platform environments.
