# Sparse checkout: limiting paths in the working directory

A large repository may contain many applications, libraries, docs, and build tools within the same Git history. If you only work on a few directories, checking out the entire repository can make the working directory heavy and hard to navigate. **Sparse checkout** lets Git place only selected paths into the working tree while still operating on the same repository and commit history.

For example, a repository has directories `services/`, `libraries/`, `docs/`, and `tools/`, but you only develop `services/payment/`. Sparse checkout can restrict the working tree to the needed directory plus certain parent-level files that Git retains under sparse checkout rules.

## 1. What problem does sparse checkout solve?

In a normal repository, when checking out a commit, Git populates the working tree from the tracked files in that commit. In a monorepo or multi-component repository, the number of files can be huge even when a contributor works on only a small slice.

Sparse checkout helps:

- Reduce the number of files materialized in the working tree.
- Keep IDEs, search tools, and build tools focused on the active part of the project.
- Reduce working tree disk usage and filesystem operation time.
- Let a contributor pick different directories per task without splitting each component into an independent repository.

Sparse checkout controls **which paths are checked out in the working tree**. It does not create a new repository, does not delete commit history, and does not alter the contents of commits on branches.

## 2. How does sparse checkout work?

Git stores path states in the index. When sparse checkout is enabled, Git uses patterns to determine which files should appear in the working tree. Files outside the selected scope are typically marked with the `skip-worktree` bit in the index, letting Git know they are intentionally omitted from the working tree according to the sparse configuration.

You can picture the repository like this:

```text
company-platform/
├── services/
│   ├── payment/
│   ├── identity/
│   └── notification/
├── libraries/
│   ├── common/
│   └── security/
├── docs/
└── tools/
```

If you only select `services/payment/`, the working tree focuses on that area along with root files and direct parent files required by cone mode rules. Unselected directories such as `services/identity/`, `libraries/`, or `tools/` are not checked out in full.

Sparse checkout is not an access control mechanism. Users are still working in the same repository; restricting the working tree does not prevent them from accessing commits or objects already in the repository using appropriate Git commands.

## 3. Cone mode and non-cone mode

Git supports two ways of expressing sparse checkout scope.

### Cone mode

Cone mode selects scope by directory. This is the preferred approach in most projects because patterns are easy to understand, easy to manage, and Git can process them more efficiently on large repositories.

Example:

```bash
git sparse-checkout init --cone
git sparse-checkout set services/payment docs
```

With the two directories above, cone mode keeps:

- Files in the repository root directory.
- Direct files inside parent directories along the path to the selected directories—for example, files located directly inside `services/`.
- All contents inside `services/payment/` and `docs/`, including subdirectories.

Cone mode does not mean only the exact two named directories appear. Root files and direct files in parent directories are part of the cone rules to support project structure.

### Non-cone mode

Non-cone mode uses more flexible patterns that can describe file scopes with syntax similar to `.gitignore`, such as including or excluding by name or location. This approach is useful when selecting a group of files that cannot be expressed cleanly by directories, but patterns are more complex and can be less efficient on large repositories.

For new repositories or typical needs, use cone mode. Only use non-cone mode when you genuinely need pattern-based selection and have carefully verified the outcome.

## 4. Enabling sparse checkout for an existing repository

Open a terminal in the repository to configure. Before enabling, check the working state:

```bash
git status --short --branch
```

If there are uncommitted changes, commit or save them per your team's workflow before changing the checkout scope. Narrowing the working tree can alter which files are present in directories; do not start without knowing the current state.

Enable sparse checkout in cone mode:

```bash
git sparse-checkout init --cone
```

This command initializes sparse checkout configuration and applies cone mode. When no directory list has been specified yet, the initial scope may include only files at the repository root.

Then select the directories to work on:

```bash
git sparse-checkout set services/payment
```

Git updates the sparse patterns list and adjusts the working tree to match the new selection. If multiple directories are needed, pass all of them in the same command:

```bash
git sparse-checkout set services/payment libraries/common docs
```

The `set` command replaces the currently configured directory/pattern list with the new list. Therefore, if you want to keep previously selected directories, list them again alongside the new directory in the `set` command.

## 5. Creating a clone that checks out only part of the repo from the start

If you do not yet have a local repository, you can clone in sparse mode:

```bash
git clone --sparse https://example.com/company/platform.git
```

`--sparse` creates a clone with sparse checkout enabled and an initial working tree containing only root-level files. Then enter the cloned directory and choose the scope:

```bash
cd platform
git sparse-checkout set services/payment docs
```

This clone command still creates a normal Git repository with a configured remote. Sparse checkout limits what is checked out to the working tree; it does not automatically mean Git only downloads objects for the selected directories.

If you also want to reduce downloaded object data, you can combine partial clone when the server supports it:

```bash
git clone --filter=blob:none --sparse https://example.com/company/platform.git
```

`--filter=blob:none` asks the server not to send blobs initially; Git can download needed blobs later when they are accessed. This is a separate mechanism from sparse checkout and depends on remote server support.

## 6. Viewing and updating the selected path list

### Viewing the sparse patterns list

```bash
git sparse-checkout list
```

In cone mode, the output typically lists the selected directories, for example:

```text
docs
services/payment
```

This list reflects the configured sparse checkout scope, not necessarily every actual subdirectory appearing in the working tree.

### Replacing the list with set

Suppose you initially selected:

```bash
git sparse-checkout set services/payment docs
```

Later you switch to a task in `services/identity/` while still wanting to keep docs:

```bash
git sparse-checkout set services/identity docs
```

After this command, `services/payment` is no longer in the selected list unless covered by another pattern.

### Adding directories with add

If you only want to expand the scope while keeping current selections, use:

```bash
git sparse-checkout add libraries/security
```

`add` appends a directory/pattern to the existing configuration. This is a convenient option when expanding the working tree step by step.

### Verifying after changes

```bash
git sparse-checkout list
git status --short --branch
```

Check both the sparse list and repository status after every scope change to be sure you are working on the right part of the project.

## 7. Updating scope after switching branches or pulling

Sparse checkout continues to apply when you switch branches or update history. However, the new branch may contain different directories or files than the previous branch. Git applies the current sparse patterns to the contents of the new commit.

Example:

```bash
git switch feature/payment-v2
git pull --ff-only
```

After switching branches or pulling, check:

```bash
git status
git sparse-checkout list
```

If you need to expand the scope to edit a new directory present on that branch:

```bash
git sparse-checkout add services/payment-migration
```

If changing branches creates a situation where the working tree does not match the sparse patterns, you can reapply the configuration:

```bash
git sparse-checkout reapply
```

`reapply` tells Git to reapply sparse checkout patterns to the working tree and index. Before using it, check `git status` and preserve local changes; do not use this command as an arbitrary way to discard modified files.

## 8. Restoring the full working tree with disable

When you no longer need sparse checkout and want to bring all tracked contents of the current commit back into the working tree, run:

```bash
git sparse-checkout disable
```

This command turns off sparse checkout and expands the working tree back to a full checkout state. Then check:

```bash
git sparse-checkout list
git status --short --branch
```

When sparse checkout is disabled, `git sparse-checkout list` may report that the configuration is inactive or that there is no active pattern list, depending on the Git version. The key point is that tracked files of the current commit have been restored to the working tree.

If the repository uses partial clone and some blobs have not been downloaded yet, expanding the working tree may cause Git to contact the remote to fetch missing objects. Ensure proper connectivity and access permissions.

## 9. Non-cone mode and file-based patterns

When you need to select files by pattern rather than by directory, you can initialize non-cone mode:

```bash
git sparse-checkout init --no-cone
```

Then configure the patterns. The example below illustrates the idea of keeping root contents and a specific set of paths using pattern syntax:

```bash
git sparse-checkout set --no-cone '/*' '!/*/' '/services/payment/' '/docs/'
```

Non-cone mode uses highly expressive pattern rules, but patterns can be hard to read and can easily produce an unintended scope. In particular, patterns starting with `!` can exclude paths already matched by another pattern; ordering and how Git matches patterns should be tested on an actual repository.

After configuring, inspect the list:

```bash
git sparse-checkout list
```

If your goal is simply working by directory, cone mode is simpler and easier to maintain. Avoid switching back and forth between cone and non-cone just to test a pattern without saving the list and understanding its effect on the working tree.

## 10. How do sparse checkout and partial clone differ?

These two features are often used together, but they solve two different problems:

| Feature | What does it control? | Primary effect |
|---|---|---|
| Sparse checkout | Which paths are checked out in the working tree | Reduces the number of files appearing in the working directory |
| Partial clone | Which Git objects are downloaded from the remote | Can reduce initial downloaded data, e.g., deferring blobs with `--filter=blob:none` |

Using sparse checkout alone does not guarantee a corresponding reduction in object database size or downloaded history. Conversely, partial clone does not automatically limit directories appearing in the working tree unless combined with sparse checkout.

For very large repositories, you can combine them:

```bash
git clone --filter=blob:none --sparse https://example.com/company/platform.git
cd platform
git sparse-checkout set services/payment
```

Check your Git server's filter support and your organization's access policies before choosing this clone approach.

## 11. Limitations and considerations when using sparse checkout

- **Not a security mechanism:** sparse checkout does not stop users from accessing history or objects already downloaded in the repository.
- **Does not automatically skip all untracked files:** sparse patterns primarily control checked-out tracked paths; untracked and ignored files must be managed separately.
- **Mind uncommitted changes:** before narrowing or widening the scope, check and preserve local changes.
- **Some tools assume a full repository:** IDEs, scripts, or build tools may need directories outside the sparse set. Expand the scope if your work requires them.
- **Cone mode selects by directory:** it also keeps root files and direct files in parent directories along selected paths.
- **Non-cone mode is more complex:** patterns are flexible, but harder to maintain and can make operations less efficient.
- **Partial clone needs the remote:** if blobs have not been downloaded yet, Git may need network access to fetch them when contents are requested.

If a Git command or build tool reports missing files, first check the sparse patterns with `git sparse-checkout list`. Do not assume the file was deleted from the repository; it may simply lie outside the current checkout scope.

## 12. Sample workflow in a monorepo

Suppose you need to develop the payment service in a repository containing multiple applications and libraries.

```bash
# 1. Clone the repository in sparse mode.
git clone --sparse https://example.com/company/platform.git
cd platform

# 2. Select directories needed for your work.
git sparse-checkout set services/payment libraries/common docs

# 3. Verify the selected scope.
git sparse-checkout list
git status --short --branch

# 4. Create a branch for the change.
git switch -c feature/payment-retry

# 5. After working, inspect diff and commit as usual.
git status
git diff
git add services/payment
git commit -m "feat: add payment retry handling"

# 6. If you also need a shared test directory.
git sparse-checkout add tools/test-fixtures

# 7. When you need to work with the full repository.
git sparse-checkout disable
```

Branch, diff, add, and commit commands continue to work under the familiar Git model. The difference is that the working tree displays only the scope selected by sparse checkout.

## 13. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Sparse checkout creates a small standalone repository | It preserves the repository and history, limiting only the paths checked out in the working tree |
| A missing directory means it was deleted from Git | The path may simply lie outside the sparse patterns |
| `git sparse-checkout set` appends to the old list | `set` replaces the list; use `add` to append |
| Cone mode keeps only the exact selected directory | Cone mode also keeps root files and direct files in required parent directories |
| Sparse checkout automatically shrinks all downloaded data | It controls the working tree; partial clone controls object downloading |
| Sparse checkout is a way to restrict access permissions | It is not a security or authorization mechanism |
| `git sparse-checkout disable` deletes the repository | The command turns off sparse mode and restores the full working tree for the current commit |

## 14. Key takeaways

Sparse checkout fits when a repository has many directories but your work needs only a subset. In most cases, use cone mode:

```bash
git sparse-checkout init --cone
git sparse-checkout set services/payment docs
git sparse-checkout list
```

Use `add` to expand scope, `reapply` to reapply patterns, and `disable` to restore the full working tree. Before changing scope, inspect `git status` and safeguard local work. If you also need to reduce downloaded objects, consider combining with partial clone such as `--filter=blob:none`.

Remember that sparse checkout limits only what is checked out to the working tree. The repository, history, and Git access permissions still follow the existing repository configuration and remote permissions.
