# Installing Git LFS and Declaring File Patterns with git lfs track

Git stores source code history efficiently for text files and many common file types. However, large binary files such as videos, design images, builds, 3D models, or test datasets can cause a repository to grow rapidly in size. Each time the content of a large file changes, standard Git may have to store another blob version in history.

**Git LFS (Large File Storage)** is a Git extension that manages large file content through LFS storage objects. Inside the Git repository, a large file is replaced with a small *pointer file* containing the identifier and size of the actual content. The actual content is stored on an LFS server and downloaded when needed. To use it, install Git LFS, initialize integration with Git using `git lfs install`, and then declare the file patterns to manage using `git lfs track`.

## 1. What Problem Does Git LFS Solve?

Suppose a project contains these files:

```text
project/
├── src/
├── docs/
└── assets/
    ├── product-demo.mp4
    ├── logo-source.psd
    └── model-final.blend
```

Video, design, and model files can be large and also change frequently. If stored directly as regular blobs, the repository can grow rapidly, and cloning or fetching history becomes costly in time, network bandwidth, and disk space.

Git LFS separates large content from the standard Git object database:

- Git commits store a small pointer file instead of the large binary content.
- The pointer contains an OID (typically SHA-256) and the size of the actual content.
- The Git LFS client downloads or uploads actual content to the LFS server through a dedicated mechanism.
- Git still manages history, branches, merges, and commits of the pointers like other files.

Git LFS is well suited for large binary assets that a team needs to version alongside source code. It does not automatically compress every file, does not eliminate the Git repository, and does not replace deciding carefully which data should be committed.

## 2. Git LFS Operates via Pointer Files

When a file is configured to be tracked by LFS and added with `git add`, the Git LFS clean filter converts the file content into a pointer in the index. On checkout, the Git LFS smudge filter or the corresponding checkout mechanism replaces the pointer with the actual content if the LFS object can be downloaded.

An illustrative pointer file looks like:

```text
version https://git-lfs.github.com/spec/v1
oid sha256:4cac196befb372e4a4e1c1f2f9c0c3b5d7e9a1b3c5d7e9f1029384756abcdef0
size 12345678
```

Field meanings:

| Field | Meaning |
|---|---|
| `version` | Git LFS pointer specification version |
| `oid sha256:...` | LFS content identifier based on SHA-256 |
| `size` | Size of the actual content in bytes |

On commit, Git writes the pointer file into the tree. On push, Git LFS typically uses a pre-push hook to upload required LFS objects to the server before or alongside pushing refs. On clone or checkout, the client uses the OID in the pointer to retrieve the exact content from the LFS server.

This keeps Git history containing small metadata while large content is transferred through the LFS service. The repository still depends on the LFS server to retrieve the real files when working with them.

## 3. Installing Git LFS on Windows

Git LFS is a separate program to install even if Git for Windows is already installed. First, verify Git is working:

```powershell
git --version
```

### Using the Official Installer

1. Open the official site <https://git-lfs.com/> or the releases page <https://github.com/git-lfs/git-lfs/releases>.
2. Download the installer matching your Windows architecture.
3. Run the installer and complete the setup wizard.
4. Close and reopen PowerShell, Windows Terminal, or Git Bash to load the updated PATH.

### Verifying the Installation

```powershell
git lfs version
where.exe git-lfs
```

If `git lfs version` prints a version number, Git has located the Git LFS executable. `where.exe git-lfs` helps confirm which executable is invoked via PATH.

## 4. Installing Git LFS on macOS

If Homebrew is installed, run:

```bash
brew install git-lfs
```

Verify the program:

```bash
git lfs version
command -v git-lfs
```

If you do not use Homebrew, download the appropriate package from <https://github.com/git-lfs/git-lfs/releases> and follow the release instructions. If your machine has multiple Git installations or multiple LFS sources, check the path to ensure your terminal uses the intended executable.

## 5. Installing Git LFS on Linux

Many Linux distributions provide a `git-lfs` package. Use the package manager appropriate for your system:

### Ubuntu and Debian

```bash
sudo apt update
sudo apt install git-lfs
```

### Fedora and DNF-Based Compatible Distributions

```bash
sudo dnf install git-lfs
```

### Arch Linux

```bash
sudo pacman -S git-lfs
```

### openSUSE

```bash
sudo zypper install git-lfs
```

If the package is unavailable in your configured repositories or too old for project requirements, refer to the official installation guide and packages at <https://github.com/git-lfs/git-lfs>. On corporate machines, prefer package sources approved by your organization.

Verify after installation:

```bash
git lfs version
command -v git-lfs
```

## 6. Initializing Git LFS Integration with git lfs install

Installing the executable only completes installation. You need to run `git lfs install` to configure the Git filters and hooks required by Git LFS.

Typically, run once per user account:

```bash
git lfs install
```

This command configures `lfs` filters in Git configuration and installs the pre-push hook for the current repository if run inside a repository. The hook enables Git LFS to upload required large content when you push commits containing pointers.

If you only want to configure the current repository:

```bash
git lfs install --local
```

`--local` limits the Git LFS configuration to the current repository instead of applying it at the user scope. This is useful on shared machines or when a project has specific configuration requirements.

Inspect environment details:

```bash
git lfs env
```

This displays Git paths, the LFS object storage directory, endpoints, and related settings. Review output before sharing because environment details can reveal internal paths or private server URLs.

## 7. Declaring File Patterns with git lfs track

Once Git LFS is installed and initialized, navigate to the repository root and choose the file patterns to manage with LFS.

For example, track all Photoshop files:

```bash
git lfs track "*.psd"
```

Track videos inside the `assets/video/` directory:

```bash
git lfs track "assets/video/*.mp4"
```

Track a group of design and archive files:

```bash
git lfs track "*.blend" "*.zip" "*.7z"
```

`git lfs track` writes patterns into the repository's `.gitattributes` file. This file tells Git which paths use the LFS filter, diff/merge drivers, and how content should be handled. It is a repository configuration file, so it must be committed for other team members to receive the same rules.

A generated `.gitattributes` may contain lines such as:

```gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
*.blend filter=lfs diff=lfs merge=lfs -text
*.zip filter=lfs diff=lfs merge=lfs -text
```

Meaning of the attributes:

- `filter=lfs`: uses the Git LFS clean/smudge filters during staging and checkout.
- `diff=lfs`: uses the Git LFS diff driver.
- `merge=lfs`: uses the Git LFS merge driver according to supported configuration.
- `-text`: disables text-based line-ending conversion for binary files.

Do not modify or remove these attributes arbitrarily. If editing `.gitattributes` manually, preserve valid syntax and verify the result with `git check-attr`.

## 8. Choosing Appropriate Patterns

`.gitattributes` patterns use syntax similar to `.gitignore` but not completely identical. Some practical guidelines:

- `*.psd` works well when targeting files with the `.psd` extension across multiple locations in the repository.
- `assets/video/*.mp4` restricts tracking to videos under the specified path.
- `models/**` can be used to cover a model directory tree as required by the project.
- Quote patterns when passing them in a shell to prevent the shell from expanding `*` before Git receives the argument.

Track by explicit extensions or directories with clear intent. Avoid overly broad patterns like `*` or an entire repository directory unless intentional, as that can route text files, configs, and scripts into LFS as well.

List currently declared LFS patterns:

```bash
git lfs track
```

This displays patterns configured in the repository's `.gitattributes`. To inspect changes created by the command:

```bash
git status --short
git diff -- .gitattributes
```

## 9. Checking Whether a Path Is Configured to Use LFS

`git check-attr` shows the effective attributes for a path. For example:

```bash
git check-attr filter diff merge text -- assets/design/logo-source.psd
```

If an LFS pattern matches, the output typically looks like:

```text
assets/design/logo-source.psd: filter: lfs
assets/design/logo-source.psd: diff: lfs
assets/design/logo-source.psd: merge: lfs
assets/design/logo-source.psd: text: unset
```

This indicates Git will apply the LFS filter to that path and the `text` attribute is unset. If `filter` is not `lfs`, check the pattern in `.gitattributes`, the file's location, and rules in parent directories.

You can also inspect files already recorded by LFS:

```bash
git lfs ls-files
```

This lists LFS files in the current repository state along with abbreviated OIDs and filenames. If no LFS files have been staged or committed yet, the list may be empty even when `.gitattributes` already contains patterns.

## 10. Adding New Files After Declaring Track Rules

Typical workflow for a new file:

```bash
# 1. Declare pattern.
git lfs track "*.psd"

# 2. Inspect the rule written to .gitattributes.
git diff -- .gitattributes

# 3. Stage the config file and the large file.
git add .gitattributes
git add assets/design/logo-source.psd

# 4. Check status and LFS file list.
git status
git lfs ls-files

# 5. Commit both configuration and file.
git commit -m "chore: track design assets with Git LFS"
```

Commit `.gitattributes` together with changes using LFS. That way, other team members receive the rules before or at the same time as the large files, allowing Git to apply the appropriate filter during checkout.

## 11. When a File Was Already Tracked by Git Before Running git lfs track

`git lfs track` creates or updates rules for subsequent staging operations. It does not automatically rewrite existing history. If a large file was already committed as a standard Git blob, older commits still retain that blob.

Two scenarios must be distinguished:

- **Only want modified versions from now on to use LFS:** after declaring the pattern, stage the new version of the file under the LFS rule and verify with `git lfs ls-files`. Older versions in history remain regular Git blobs.
- **Want to convert old history to LFS as well:** a migration tool such as `git lfs migrate import` is required. This rewrites commits and changes commit hashes within the selected scope; it requires planning, backups, and coordination with all repository users before execution.

Do not run migrations on a shared repository merely for experimentation. If the goal is to remove large blobs from all history, agree on target branches/refs, how force-pushing will occur, and instructions for team members to re-clone or re-sync after history changes.

## 12. Pushing and Retrieving LFS Content from a Remote

When a repository is configured with Git LFS, pushing a branch works like standard Git:

```bash
git push origin feature/design-assets
```

The Git LFS pre-push hook finds required LFS objects and uploads them to the LFS server. Git then pushes commits and refs. The remote host must support Git LFS, and the account needs access to both the repository and LFS storage.

When cloning a repository with LFS files, Git LFS normally downloads actual content during checkout. To fetch LFS content after cloning or fetching:

```bash
git lfs pull
```

`git lfs fetch` downloads LFS objects to local storage without necessarily checking them out into the working tree; `git lfs pull` combines fetching and checking out the matching content for the current ref.

If you want to clone without downloading LFS content immediately, use:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://example.com/team/project.git
```

In PowerShell, setting an environment variable for a command uses different syntax; for example:

```powershell
$env:GIT_LFS_SKIP_SMUDGE = "1"
git clone https://example.com/team/project.git
```

When you want to download the actual content later, run `git lfs pull`. This is useful when cloning quickly to inspect source code first, but keep in mind LFS files in the working tree may remain pointers until content is pulled.

## 13. Common Errors

### git lfs Command Not Recognized

If `git lfs version` reports command not found, Git LFS may not be installed or its executable may not be in PATH. Verify installation for your OS, open a new terminal, and run again:

```bash
git lfs version
```

### Git LFS Installed but File Still Committed as a Normal Blob

Check whether `git lfs install` was run, whether the pattern matches the path, and whether `git check-attr filter -- <path>` returns `lfs`. If the file was staged before adding the pattern, re-stage it after configuring properly and verify with `git lfs ls-files`.

### File Does Not Appear in git lfs ls-files

`git lfs track` only declares patterns; it does not automatically add files to the index. Run `git add <path>` after tracking and check status. For files committed previously, determine whether you only need new versions in LFS or need a history migration.

### Push Reports Missing LFS Objects or Authentication Error

Verify the remote supports LFS, the account has access to the LFS endpoint, and the pre-push hook is installed. Inspect configuration with:

```bash
git lfs env
git config --show-origin --get-regexp '^lfs\.'
```

Do not share tokens, passwords, or credentials in support output. If the hook was skipped or failed to run, resolve the cause before pushing again so pointers on the remote have corresponding content on the LFS server.

### Clone Succeeds but Files Only Contain Pointer Text

This can happen if smudge was skipped, LFS objects have not been downloaded, or the client cannot reach the LFS server. Run:

```bash
git lfs pull
```

If it still fails, inspect `git lfs env`, access permissions, and connectivity to the LFS endpoint.

## 14. LFS Setup Workflow for a New Repository

A concise workflow can be followed like this:

```bash
# 1. Confirm Git and Git LFS are installed.
git --version
git lfs version

# 2. Initialize LFS integration.
git lfs install

# 3. Inside the repository, declare patterns.
git lfs track "*.psd" "*.mp4" "*.blend"

# 4. Inspect .gitattributes.
git diff -- .gitattributes

# 5. Test a sample path.
git check-attr filter diff merge text -- assets/design/logo-source.psd

# 6. Stage configuration and large files.
git add .gitattributes
git add assets/design/logo-source.psd

# 7. Verify the file is recognized by LFS.
git lfs ls-files

# 8. Commit and push.
git commit -m "chore: configure Git LFS for binary assets"
git push origin main
```

Replace branch names and paths with your repository's actual structure. Before pushing, verify the hosting server has Git LFS enabled and your user has permission to upload LFS content.

## 15. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| Installing Git includes Git LFS | Git LFS is a separate extension that must be installed and initialized independently |
| `git lfs track` uploads files to the server | That command declares patterns in `.gitattributes`; pushing transfers LFS objects to the remote |
| `.gitattributes` does not need to be committed | It is repository configuration and must be shared so all members apply the same rules |
| Tracking an extension automatically converts old history | Old commits do not change automatically; migrating history requires a separate operation |
| Pointer files are corrupted file content | A pointer is standard metadata used by Git LFS to locate and download actual content |
| Git LFS eliminates the need for a remote | Pointers live in Git, while actual content relies on LFS storage when downloading |
| LFS works without server support | The remote must provide an LFS endpoint and corresponding access permissions |

## 16. Key Takeaways

To start using Git LFS, install the program for your OS, verify with `git lfs version`, and run `git lfs install`. Inside a repository, use `git lfs track "<pattern>"` to write rules to `.gitattributes`; verify with `git check-attr` and `git lfs ls-files`.

Commit `.gitattributes` together with LFS-managed files so every team member receives the same configuration. When pushing, Git LFS transfers large content to the LFS server; when cloning or checking out, clients retrieve actual content using pointers. If files already exist in Git history before being tracked, distinguish switching new versions to LFS from migrating full history, since migration rewrites commits and requires team coordination.
