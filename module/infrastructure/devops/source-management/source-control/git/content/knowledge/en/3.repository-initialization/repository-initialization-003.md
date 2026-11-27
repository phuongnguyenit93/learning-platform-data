# The Role of .git, the Working Tree, and Bare Repositories

A Git repository typically has three closely connected parts: the **working tree**, which contains the files you read and edit; the **index**, which stores staged content in preparation for a commit; and the **Git directory**, which stores objects and metadata so Git can manage history. In a standard repository, the Git directory usually resides in the hidden `.git` folder at the project root.

A **bare repository** still has an object database, refs, and Git configuration, but it has no working tree for checking out and editing files. Bare repositories are commonly used as central remotes or storage copies of a repository. Understanding the role of each part helps you know where Git commands read or update data, and helps you choose the right repository type when initializing a project or setting up a Git server.

## 1. The three parts of a standard repository

When you run `git init` inside a project directory, Git creates the metadata needed to manage the repository. Overview model:

```text
storefront/                 <- working tree
|-- .git/                   <- Git directory
|   |-- HEAD
|   |-- config
|   |-- index               <- staging area (stored in the index file)
|   |-- objects/            <- object database
|   |-- refs/               <- branches, tags, and other refs
|   |-- hooks/              <- sample hooks or repository hooks
|   `-- logs/               <- reflog, if enabled/created
|-- src/
|-- README.md
`-- .gitignore
```

The three main parts serve different roles:

| Component | What does it store? | When do you use it? |
|---|---|---|
| Working tree | Files and directories you can open, edit, create, or delete | Writing code, editing documentation, running builds and tests |
| Index (staging area) | A snapshot of content selected for the next commit | Choosing exactly which changes will go into a commit |
| Git directory | Object database, refs, `HEAD`, configuration, and other metadata | Storing history, tracking branches/commits, managing the repository |

A change in the working tree does not automatically become historical data. You typically add the content to be committed into the index with `git add`, then create a commit with `git commit`. The commit records the index snapshot and history metadata in the Git directory.

## 2. Working tree: where you work with files

The working tree is the directory containing the versions of files you are actively working on. When you check out a branch or commit, Git updates the working tree to reflect the selected snapshot. You can edit files with an IDE, terminal, or any tool; Git detects differences when you run commands such as `git status` and `git diff`.

Example:

```bash
git status
git diff
```

- `git status` shows which files are modified, staged, untracked, or deleted.
- `git diff` compares the working tree against the index, displaying unstaged changes.

The working tree can contain tracked, untracked, and ignored files. Git does not automatically save every file present in the directory. Untracked files are only added to the index when you explicitly add them; ignored files are normally skipped according to `.gitignore` rules unless you explicitly specify how to add them.

You can check the current working tree root:

```bash
git rev-parse --show-toplevel
```

This command is useful when you are in a subdirectory and want to find the repository root. In a bare repository, there is no working tree, so this command does not return a standard working tree root.

## 3. Index: the staging area between working tree and commit

The index (also called the staging area) is where Git stores the state of content selected for the next commit. In a standard repository, the index is normally stored in `.git/index`. This file is internal Git data; you should not edit it manually with a text editor.

Example workflow:

```bash
# Edit README.md and src/app.js in the working tree
git status

# Select two files to add to the index
git add README.md src/app.js

# View staged changes
git diff --cached

# Create a commit from the index
git commit -m "Update application setup"
```

The key point is that commits are created from the index, not directly from the entire working tree. As a result, you can split changes into small, well-scoped commits even if a file still has unfinished sections.

Inspect the state of the index:

```bash
git ls-files --stage
```

This command displays staged entries along with their file mode, object ID, and stage number. During a merge conflict, the index can hold multiple stages for the same path until you resolve the conflict and stage the result.

## 4. The Git directory and the role of .git

The Git directory is where Git stores repository management data. In a standard repository created with `git init`, the Git directory is normally the `.git` directory at the root of the working tree.

Common important components:

| Path in the Git directory | Role |
|---|---|
| `HEAD` | Indicates the current commit or symbolic ref of the checked-out branch |
| `config` | Local repository configuration such as remotes, user name, merge settings, and other options |
| `index` | Contents and state of the staging area |
| `objects/` | Object database containing blobs, trees, commits, tags, and related objects |
| `refs/` | References such as branches and tags; some refs may reside in `packed-refs` |
| `hooks/` | Hooks executed at specific Git lifecycle events, if configured |
| `logs/` | Reflogs recording changes to refs, if reflog is enabled and data exists |
| `info/` | Local metadata such as `exclude` and `attributes` applied specifically to this clone |

Not every repository has all the files and directories listed above from the start. Git creates certain components when needed; some refs may be packed rather than stored as individual files. This is an internal structure, so use Git commands to read and modify it rather than manipulating files directly inside `.git`.

### HEAD and branches

In a standard repository, `HEAD` is usually a symbolic ref pointing to the current branch, for example:

```text
ref: refs/heads/main
```

The `main` branch then points to a commit. When you create a new commit, Git updates the branch ref to point to the new commit; older commit objects remain as long as they are still referenced or have not been garbage-collected.

Check:

```bash
git symbolic-ref -q HEAD
git rev-parse HEAD
git branch --show-current
```

If you are in a detached `HEAD` state, `git branch --show-current` prints no branch name and `HEAD` directly contains a commit OID instead of a symbolic ref.

### Objects and history

The `objects/` directory stores content by content address. Git uses four primary object types:

- **Blob:** file contents.
- **Tree:** directory structure and links to blobs/subtrees.
- **Commit:** tree snapshot, parent commit(s), and metadata.
- **Tag object:** annotated tag metadata, optionally signed.

Git may store objects in loose form or pack them into packfiles. You should not manually delete or edit files inside `objects/`; doing so can render commits or files unreadable.

## 5. .git is not always a directory

In a simple standard repository, `.git` is a directory. However, in certain Git layouts, `.git` can be a **text file** pointing to a Git directory located elsewhere.

Common cases:

- **Linked worktree:** each secondary worktree has a `.git` file pointing to that worktree's own metadata; most objects and refs are shared with the common Git directory.
- **Submodule:** a submodule directory typically has a `.git` file pointing to metadata managed inside the superproject's Git directory.
- **Separate Git directory:** when initializing or cloning with the option to separate the Git directory, the working tree and metadata can reside in two different locations.

Therefore, do not assume you can find all metadata by opening `<project>/.git/`. Ask Git for the actual locations:

```bash
git rev-parse --git-dir
git rev-parse --git-common-dir
git rev-parse --show-toplevel
```

- `--git-dir` reports the Git directory currently in use for the repository/worktree.
- `--git-common-dir` reports the common Git directory, especially useful with linked worktrees.
- `--show-toplevel` reports the working tree root, if one exists.

Printed paths may be relative or absolute depending on the environment and where the command is run. Using `git rev-parse` is more reliable than guessing from directory names.

### Separating the Git directory from the working tree

You can create a repository with a separately located Git directory:

```bash
git init --separate-git-dir=/srv/git-metadata/storefront.git ./storefront
```

In this case, the working tree is at `./storefront`, while metadata resides at `/srv/git-metadata/storefront.git`; Git creates a `.git` file in the working tree pointing to the metadata location. This option is useful when you need to place metadata on a separate disk or storage volume, provided you preserve the path and access permissions so the repository continues to work.

## 6. What is a bare repository?

A bare repository is a repository with no working tree. Its Git directory sits directly at the repository directory itself, conventionally named with a `.git` suffix:

```text
storefront.git/
|-- HEAD
|-- config
|-- objects/
|-- refs/
|-- hooks/
`-- ...
```

There is no nested `.git` folder inside and no checked-out project files. A bare repository still has an object database, branch refs, tags, `HEAD`, configuration, and hooks. In a bare repository, `core.bare` is typically set to `true`.

Having a `.git` suffix in the name is just a common convention, not a strict requirement. A directory named `storefront` can still be a bare repository if it was initialized in bare mode.

Inspect the current repository:

```bash
git rev-parse --is-bare-repository
git rev-parse --is-inside-work-tree
```

In a bare repository, the first command returns `true`; the second does not confirm a normal working tree. Commands that require a working tree, such as editing files or viewing a working tree diff, have nowhere to operate.

## 7. Creating a standard repository and a bare repository

### Initializing a repository with a working tree

Create a project directory and initialize Git:

```bash
mkdir storefront
cd storefront
git init
```

Git creates the Git directory (usually `.git`) inside the working tree. You can add files and commit:

```bash
echo "# Storefront" > README.md
git add README.md
git commit -m "Initial commit"
```

If you want to choose the initial branch name during initialization:

```bash
git init --initial-branch=main
```

On Git versions that do not yet support `--initial-branch`, you can configure `init.defaultBranch` before initializing or rename the branch after creation.

### Initializing a bare repository

To create a repository without a working tree:

```bash
git init --bare storefront.git
```

Or specify the default branch on supported versions:

```bash
git init --bare --initial-branch=main storefront.git
```

Bare repositories are commonly used as central remotes. Developers work in standard clones and push commits to the bare remote. The bare repository receives objects and updates refs without having to check out files into a shared working tree.

### Quick comparison

| Criterion | Standard repository | Bare repository |
|---|---|---|
| Working tree | Yes | No |
| Index for staging | Yes | No standard working-tree index |
| Git directory | Usually `.git/` inside the project | The repository directory itself |
| Has object database and refs | Yes | Yes |
| Uses `git status` to inspect modified files | Yes | No working tree to inspect |
| Used as a central target for receiving pushes | Not the suitable default choice | Suitable |
| Used for directly editing and building the project | Yes | Needs to be cloned into a separate working tree |

## 8. Why are central remotes usually bare repositories?

If multiple people push into a repository that has a checked-out working tree, the updated ref may fall out of sync with the files sitting in the working tree. This creates the risk of confusion or leaving the working tree in a state that does not reflect the new branch.

A bare repository avoids that problem because there is no checked-out working tree. When receiving a push, Git only updates objects and refs. Other team members fetch or pull to update their own clones.

Example workflow:

```text
Developer A (standard clone) --+
                               |
                               v
                         Bare remote
                               ^
                               |
Developer B (standard clone) --+
```

Create a bare remote on the server:

```bash
git init --bare --initial-branch=main /srv/git/storefront.git
```

In a developer's clone:

```bash
git remote add origin ssh://git@git.example.com/srv/git/storefront.git
git push -u origin main
```

Another developer clones from the remote:

```bash
git clone ssh://git@git.example.com/srv/git/storefront.git
```

A bare repository is just a Git repository on the server. To operate over the network, it must be served over SSH, the Git protocol, HTTP(S), or a hosting platform, and protected with authentication, authorization, backups, and push policies.

## 9. How does a bare repository differ from a mirror clone?

Bare describes a repository without a working tree. Mirror describes a cloning/configuration method for duplicating the refs advertised by a remote.

```bash
git clone --bare https://git.example.com/platform/storefront.git storefront-bare.git
git clone --mirror https://git.example.com/platform/storefront.git storefront-mirror.git
```

`--bare` creates a bare repository, typically fetching branch heads according to bare clone rules. `--mirror` also creates a bare repository, but configures a broad refspec `+refs/*:refs/*` to map every ref advertised by the source within the same namespace. A mirror clone is suited for replicating refs; a bare clone may be appropriate when you only need a bare repository with standard branches.

Not all data on a hosting service lives inside Git refs and objects. Pull requests, issues, comments, access permissions, branch protections, artifacts, Git LFS objects, and submodule repositories may need to be backed up separately. A mirror clone also cannot fetch refs that the server hides or restricts access to.

## 10. Identifying repository locations while working

When encountering a project directory with an unfamiliar layout, use the following commands:

```bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git rev-parse --git-common-dir
git rev-parse --is-inside-work-tree
git rev-parse --is-bare-repository
```

They respectively report the working tree root, the Git directory, the common Git directory, whether you are inside a working tree, and whether the repository is bare. Some commands may not return expected values if run outside a repository or inside a bare repository; read the errors and status output to determine your current context.

You can also inspect local configuration:

```bash
git config --local --list
```

In a standard repository, local configuration typically lives in `.git/config`; with linked worktrees or a separated Git directory layout, the actual location may differ. Use `git rev-parse --git-dir` to determine which Git directory is being used.

## 11. Operations you should not perform directly inside .git

The `.git` directory holds critical data Git relies on to understand history. You should not:

- Arbitrarily delete or rename `objects/`, `refs/`, `HEAD`, or `index`.
- Edit compressed object files inside `objects/` with a text editor.
- Delete `index.lock` without confirming no Git process is currently using it.
- Copy `.git` alone as a substitute for a verified backup procedure, especially when the repository uses worktrees, alternate object stores, LFS, or submodules.
- Treat `.gitignore` as a history store; this file only specifies which untracked paths should be ignored.

If you need to back up a repository, use an appropriate strategy such as a mirror clone, a bundle, or a full backup of the repository and its associated components. If you need to modify refs or configuration, use Git commands such as `git branch`, `git update-ref`, and `git config` as appropriate.

## 12. Hands-on exercises

Practice in a test directory to observe repository structure without affecting real projects.

1. Create a directory `repo-normal`, run `git init`, and list hidden contents to locate the `.git` directory.
2. Create `README.md`, stage the file with `git add`, then use `git status`, `git diff --cached`, and `git ls-files --stage` to observe the working tree and index.
3. Commit the file, then inspect `HEAD`, `config`, `refs`, and `objects` using appropriate Git commands; do not edit metadata directly.
4. Run `git rev-parse --show-toplevel`, `--git-dir`, `--is-inside-work-tree`, and `--is-bare-repository` to identify a standard repository.
5. Create a bare repository using `git init --bare repo-remote.git`, then inspect `--is-bare-repository`, `show-ref`, and `symbolic-ref HEAD`.
6. Push a branch from the standard repository to the bare repository, then clone the bare remote into a new working tree.
7. Compare the directory layout of a standard repository and a bare repository; explain why a bare remote has no checked-out project files.
8. If your environment supports it, create a linked worktree and verify that `.git` in the secondary worktree is a file pointing to metadata rather than a directory.

You have completed the exercises when you can explain how the working tree, index, and Git directory differ; locate where `.git` actually lives; and choose appropriately between a standard repository and a bare repository for active development or remote storage.
