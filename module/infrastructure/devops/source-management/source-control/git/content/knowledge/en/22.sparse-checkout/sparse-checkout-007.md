# Configuring cone mode and sparse index

In a large repository, developers often work on only part of the codebase, such as one backend service, one frontend app, or a documentation group. Checking out the entire file tree can take time, consume disk space, and force IDEs to index unrelated directories.

Git sparse-checkout lets you limit which paths are present in the working tree. Within it, **cone mode** defines how directories are selected according to tree structure; **sparse index** optimizes how Git represents portions outside the checked-out area inside the index. The two features are often used together, yet they solve two different problems.

This lesson walks through enabling cone mode, selecting and updating the working scope, enabling sparse index, checking state, and handling limitations when working with large repositories or across different environments.

## 1. What problem does sparse-checkout solve?

A normal Git clone creates a working tree containing most or all tracked files in the current commit. In a monorepo with hundreds of thousands of files, you may only need a few directories to develop a service.

Sparse-checkout allows Git to materialize (place into the working tree) only the paths in the selected set. Tracked files outside that region remain part of history and the commit tree, but generally do not appear in the working tree.

Example repository:

~~~text
platform/
├── apps/
│   ├── web/
│   └── mobile/
├── services/
│   ├── billing/
│   ├── identity/
│   └── notification/
├── libraries/
├── docs/
├── scripts/
└── README.md
~~~

If you only work on the billing service and documentation, you can select:

- `services/billing/`
- `docs/`

Git retains the necessary files according to sparse-checkout rules, reducing the number of files appearing in the working tree.

Sparse-checkout primarily controls the working tree and index. It does not automatically mean the repository downloaded less history or fewer objects. A regular clone may still download most of the repository's objects while displaying only a subset of files.

## 2. What is cone mode?

### 2.1. Selecting directories by tree structure

Cone mode is the recommended sparse-checkout mode for most workflows. Instead of allowing arbitrary glob patterns, cone mode selects directories and applies consistent rules based on directory hierarchy.

Enable sparse-checkout in cone mode:

~~~bash
git sparse-checkout init --cone
~~~

Select directories to work on:

~~~bash
git sparse-checkout set services/billing docs
~~~

The paths passed to `set` are directories relative to the repository root. `set` replaces the currently selected set of directories with the new list.

### 2.2. What does cone mode include?

Cone mode keeps:

- Files at the repository root.
- Files located directly inside parent directories leading to the selected directories.
- All contents inside the selected directories, including subdirectories.

With the command:

~~~bash
git sparse-checkout set services/billing docs
~~~

The working tree may contain:

~~~text
platform/
├── README.md
├── .gitignore
├── services/
│   ├── README.md
│   └── billing/
│       ├── pom.xml
│       └── src/
│           └── ...
└── docs/
    ├── architecture.md
    └── ...
~~~

Files directly inside `services/` are kept so the path can lead to the `services/billing/` subdirectory; sibling directories such as `services/identity/` are not expanded in full. The `docs/` directory is selected, so its contents are checked out recursively.

This rule helps Git build the path set efficiently while preserving the required parent structure.

### 2.3. Cone mode selects directories, not arbitrary files

Cone mode fits when the unit of work is a directory. For example:

~~~bash
git sparse-checkout set apps/web services/identity
~~~

If you want to select a specific file nested deep inside a directory or use complex patterns like `src/**/test-*.java`, cone mode is not the right expression mechanism. In that case, you can use non-cone mode with gitignore-like patterns, though the rules are harder to understand and can incur higher processing cost on large repositories.

For most monorepos, organize the directory structure so teams can select by directory and use cone mode.

## 3. Setting up and managing the sparse-checkout scope

### 3.1. Initializing cone mode

From any subdirectory inside the repository, confirm the current repository:

~~~bash
git rev-parse --show-toplevel
git status --short --branch
~~~

Then enable cone mode:

~~~bash
git sparse-checkout init --cone
~~~

This command initializes sparse-checkout and configures cone mode. Check status before running it if the working tree has uncommitted changes.

### 3.2. Selecting the working scope with set

For example, working only with the frontend and documentation directory:

~~~bash
git sparse-checkout set apps/web docs
~~~

The `set` command replaces the selected directory set. If you previously selected `services/billing`, after this command that directory may be removed from the working tree because it is no longer in the sparse region.

View the current list:

~~~bash
git sparse-checkout list
~~~

This command displays the directories selected in cone mode.

### 3.3. Adding directories with add

If you want to expand the working scope while keeping existing directories, use:

~~~bash
git sparse-checkout add services/identity
~~~

After the command, the selected region includes the previous directories plus `services/identity`.

Verify:

~~~bash
git sparse-checkout list
git status --short
~~~

Distinction:

- `set`: replaces the current selection set.
- `add`: appends directories to the selection set.

This is an important distinction to avoid accidentally removing a directory you still need from the working tree.

### 3.4. Viewing and checking configuration

You can inspect the relevant settings:

~~~bash
git config --show-origin --get core.sparseCheckout
git config --show-origin --get core.sparseCheckoutCone
git config --show-origin --get index.sparse
~~~

Meaning:

| Setting | Role |
| --- | --- |
| `core.sparseCheckout` | Indicates whether sparse-checkout is enabled |
| `core.sparseCheckoutCone` | Indicates whether cone mode is in use |
| `index.sparse` | Indicates whether Git uses a sparse index |

Not every key is written explicitly in the same configuration file; if a command prints no output, the key may not be set at the queried config levels.

You can view the list of tracked paths:

~~~bash
git ls-files
~~~

This list can be large depending on how Git represents the index and display options. The next section explains how to inspect a sparse index.

## 4. What is a sparse index?

### 4.1. Regular index and its cost on monorepos

The index (staging area) stores information about contents prepared for commits. In a large repository, a regular index can hold one entry for every tracked file, including many files outside the sparse-checkout area.

When the file count is very high, reading and updating the index can consume significant time and memory even though the working tree displays only part of the repository.

Sparse index optimizes this by letting the index represent a directory tree outside the sparse area as a single **sparse-directory entry**, instead of expanding into individual entries for every file inside it.

As a result, the index can be considerably smaller in monorepos with many unchecked-out directories.

### 4.2. Sparse index is not cone mode

The two concepts have different roles:

| Component | What does it decide? | Benefit |
| --- | --- | --- |
| Cone mode | Which directories and files are present in the working tree | Simple, efficient path selection rules |
| Sparse index | How Git represents areas outside the sparse region in the index | Reduces index size and processing overhead |

You can enable cone mode without enabling sparse index. Sparse index requires cone mode; it is not an independent path selection mode.

A common workflow is to start with cone mode, confirm the working scope is right, and then enable sparse index if the repository is large enough and team tooling is compatible.

### 4.3. Enabling sparse index

You can initialize both at the same time:

~~~bash
git sparse-checkout init --cone --sparse-index
~~~

If sparse-checkout is already enabled in cone mode, you can reapply the configuration with sparse index:

~~~bash
git sparse-checkout reapply --sparse-index
~~~

Then verify the configuration:

~~~bash
git config --get core.sparseCheckoutCone
git config --get index.sparse
~~~

Sparse index was introduced in Git 2.32. Its level of support depends on the Git version and the commands used. For older environments or incompatible tooling, use cone mode with the regular index.

### 4.4. Inspecting sparse-directory entries

You can inspect the index in sparse form:

~~~bash
git ls-files --sparse
~~~

When sparse index is in use, Git can display some directories outside the checkout area as directory entries rather than listing every nested file. Exact output depends on repository structure and the selected directory set.

To view full entries and modes:

~~~bash
git ls-files --stage --sparse
~~~

A sparse-directory entry typically has mode `040000`, representing a directory tree. Do not confuse this entry with a regular directory file created by a user; it is the index's compressed representation of part of the repository tree.

Do not edit the index directly to create or remove these entries. Use `sparse-checkout` commands so Git manages them consistently.

## 5. Using cone mode and sparse index in a workflow

Suppose the team develops a monorepo with these directories:

~~~text
repo/
├── apps/
│   ├── web/
│   └── mobile/
├── services/
│   ├── billing/
│   ├── identity/
│   └── notification/
├── shared/
├── docs/
└── tools/
~~~

You are responsible for the billing service and need the shared library and documentation.

### Step 1 — Check version and repository

~~~bash
git --version
git rev-parse --show-toplevel
git status --short --branch
~~~

Sparse-checkout has been available since Git 2.25. Sparse index requires Git 2.32 or newer. If a command is unsupported, check the help output of the version you are running:

~~~bash
git sparse-checkout -h
git sparse-checkout init -h
~~~

### Step 2 — Enable cone mode and select directories

~~~bash
git sparse-checkout init --cone
git sparse-checkout set services/billing shared docs
~~~

The working tree will contain root files, direct files in required parent directories, and all contents of the selected directories.

### Step 3 — Verify the selected region

~~~bash
git sparse-checkout list
git status --short
git ls-files
~~~

Open a few needed paths and confirm that the IDE, build scripts, or project tools can access the expected files.

### Step 4 — Enable sparse index if appropriate

~~~bash
git sparse-checkout reapply --sparse-index
git config --get index.sparse
git ls-files --sparse
~~~

If tools or commands in your environment encounter issues with sparse index, you can switch back to the full index while keeping cone mode:

~~~bash
git sparse-checkout reapply --no-sparse-index
~~~

This does not disable sparse-checkout; it only changes how the index is represented.

### Step 5 — Expand the working scope when needed

If you also need to modify the identity service:

~~~bash
git sparse-checkout add services/identity
git sparse-checkout list
~~~

If you want to switch to working on frontend and docs instead of billing:

~~~bash
git sparse-checkout set apps/web docs
~~~

The `set` command replaces the previous list. Re-verify the working scope after each change.

## 6. Switching branches and syncing remotes in sparse checkout

Sparse-checkout does not create a special kind of branch. You still use normal Git commands to switch branches, fetch, pull, merge, rebase, and commit.

However, the new branch may have a different file structure than the current branch. Git applies the sparse-checkout rules to decide which files are materialized. After branch operations or integrations, if the working tree no longer matches the selected region, you can reapply:

~~~bash
git sparse-checkout reapply
~~~

Example:

~~~bash
git fetch origin
git switch feature/billing-v2
git sparse-checkout reapply
git status --short --branch
~~~

If conflicts occur, resolve the affected files following normal merge/rebase procedures. Do not manually delete files hidden from the sparse view to "clean up" conflicts; inspect `git status` and the unmerged list first.

Merge, rebase, or external tools may temporarily materialize some files outside the sparse region. `reapply` helps Git bring the working tree back to the configured selection set once the operation finishes.

### 6.1. Commits only include staged changes

Sparse-checkout does not alter commit rules. Commits still read contents from the index:

~~~bash
git status
git diff
git diff --cached
git commit -m "Update billing validation"
~~~

Before committing, inspect the index to be sure only intended changes are included. Files outside the sparse region generally do not appear in the working tree, yet remain part of the current commit tree.

Do not run `git add -A` blindly across an overly broad scope without checking its impact. Stage by relevant path or directory and inspect `git diff --cached`.

## 7. How does sparse-checkout differ from partial clone?

The two features are often combined, but they are not the same.

- **Sparse-checkout:** limits which files are materialized in the working tree.
- **Partial clone:** limits which objects are downloaded from the remote, typically via an object filter.

A sparse checkout on a normal clone may still download all or most blobs even though only a subset of files is shown. If the goal is to reduce both the number of files in the working tree and the initial data downloaded, you can combine partial clone:

~~~bash
git clone --filter=blob:none --sparse <repository-url>
cd <repository-folder>
git sparse-checkout set services/billing shared docs
~~~

With `--filter=blob:none`, blobs are downloaded on demand via the partial clone mechanism. When checking out or opening a file that requires a blob not yet local, Git can fetch the object from the remote if the promisor remote and connection are working.

Partial clone requires server filter support and may require network access when accessing unfetched content. Sparse-checkout remains the mechanism that decides which paths appear in the working tree.

Do not treat clone's `--sparse` flag as synonymous with partial clone. It initializes sparse-checkout up front; the filter is what defers downloading certain objects.

## 8. Limitations and considerations when using sparse index

### 8.1. Not every tool understands sparse index

Some external tools, IDEs, scripts, or older Git versions may assume the index always contains one entry per file. Sparse index uses sparse-directory entries, so those tools may misread or fail to support it.

Modern Git commands can often expand the sparse index on the fly when needed for compatibility, though expanding it can forfeit performance gains for that run. If errors occur, check your Git version and active tooling before concluding the repository is corrupted.

You can temporarily disable sparse index:

~~~bash
git sparse-checkout reapply --no-sparse-index
~~~

Cone mode and the sparse working tree remain intact.

### 8.2. Do not manipulate files outside the sparse region directly

A path not appearing in the working tree does not mean it was deleted from the repository. It still exists in commits and is tracked by Git.

Do not manually recreate files outside the sparse region by copying them from elsewhere, as that can create confusing states between the index and working tree. If you need another directory, add it to the selection set:

~~~bash
git sparse-checkout add path/to/directory
~~~

After finishing your work, you can remove that directory from the selection set by running `set` with a new list containing only the directories you want to keep.

### 8.3. Untracked and ignored files

Sparse-checkout primarily manages tracked paths. Untracked or ignored files follow their own rules and may remain on disk even when the corresponding tracked directory is no longer in the sparse set.

Before changing the selection scope or disabling sparse-checkout, check:

~~~bash
git status --short
git status --ignored --short
~~~

Do not confuse an untracked or ignored file with content managed by sparse-checkout.

### 8.4. Disabling sparse-checkout

When you need to return to a full working tree:

~~~bash
git sparse-checkout disable
~~~

This command turns off sparse-checkout and restores tracked paths into the working tree. With partial clone, Git may need to download additional objects from the remote to materialize all contents.

Then check:

~~~bash
git sparse-checkout list
git status --short --branch
~~~

If sparse-checkout has been disabled, the list command may report that sparse mode is inactive or has no corresponding configuration. Verify the working tree and repository status.

## 9. Common troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `git sparse-checkout` does not exist | Git is too old or another executable is being invoked | Check `git --version` and executable path; sparse-checkout requires Git 2.25 or newer |
| `--sparse-index` is unsupported | Older Git or the command lacks that option | Check help output; use cone mode with a regular index |
| A directory disappears after `set` | `set` replaces the previous selection set | Use `add` to append or include the directory in the new `set` list |
| Working tree has files outside the sparse region after merge | The operation may temporarily materialize files | Check status and run `git sparse-checkout reapply` |
| IDE or script reports errors when sparse index is enabled | Tool does not yet support sparse-directory entries | Update the tool or use `reapply --no-sparse-index` |
| Cannot open file contents in a partial clone | Blob has not been downloaded and remote is unreachable | Check network, promisor remote, and access permissions |
| `disable` takes a long time | Repository has many files or needs to fetch missing objects | Wait for completion and check remote connectivity if using partial clone |

When errors occur, check in order:

~~~bash
git --version
git status --short --branch
git sparse-checkout list
git config --show-origin --get core.sparseCheckout
git config --show-origin --get core.sparseCheckoutCone
git config --show-origin --get index.sparse
~~~

These commands help identify the version, sparse scope, and how the index is configured.

## 10. Quick reference table

| Need | Command |
| --- | --- |
| Initialize cone mode | `git sparse-checkout init --cone` |
| Initialize cone mode and sparse index | `git sparse-checkout init --cone --sparse-index` |
| Select or replace directories | `git sparse-checkout set services/billing docs` |
| Add a directory | `git sparse-checkout add services/identity` |
| View selected directories | `git sparse-checkout list` |
| Reapply sparse rules | `git sparse-checkout reapply` |
| Enable sparse index when cone mode is active | `git sparse-checkout reapply --sparse-index` |
| Disable sparse index while keeping cone mode | `git sparse-checkout reapply --no-sparse-index` |
| View index in sparse form | `git ls-files --sparse` |
| View sparse checkout config | `git config --get core.sparseCheckout` |
| View cone mode config | `git config --get core.sparseCheckoutCone` |
| View sparse index config | `git config --get index.sparse` |
| Disable sparse-checkout | `git sparse-checkout disable` |

## 11. Summary

Cone mode and sparse index complement each other when working with large repositories. Cone mode selects directories by tree structure and keeps path sets easy to understand and maintain. Sparse index reduces the number of entries stored in the index by representing directories outside the checkout area as sparse-directory entries.

Start with cone mode, pick the right directories with `set`, expand with `add`, and confirm with `list`. Enable sparse index only when your Git version and team tools support it. After switching branches or integrating changes, use `reapply` if the working tree needs to be brought back to the selected scope. When you need to work with the entire repository, use `disable`.

Finally, remember that sparse-checkout only determines which part of the working tree is materialized; it does not replace partial clone or delete history. Distinguishing these features properly helps you choose a configuration suited to your repository scale, reduce operational overhead, and avoid mistakes when syncing or committing.
