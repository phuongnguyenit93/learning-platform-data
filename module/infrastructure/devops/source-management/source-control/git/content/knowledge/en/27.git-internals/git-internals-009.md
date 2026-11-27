# Resolving Objects and References with git rev-parse

Git commonly lets you use memorable names such as `HEAD`, `main`, `origin/main`, or `v1.0.0` instead of long object IDs. Before a command operates on history, Git must resolve that name or expression to a concrete object. The **git rev-parse** command helps verify and normalize revisions, refs, object IDs, metadata paths, and repository information.

In the **Internals** chapter of the **SOURCE_CONTROL_GIT** module, this lesson focuses on how Git interprets commit and object names. You will learn how to resolve refs, read revision syntax such as `HEAD~2` or `tag^{commit}`, verify object types, handle hash prefixes, and use `rev-parse` safely in scripts. The goal is to know precisely where a name points before using it for reset, checkout, merge, release, or automation.

After this lesson, you will be able to:

- Explain the difference between a ref, a revision expression, and an object ID.
- Use `git rev-parse` to resolve `HEAD`, branches, remote-tracking branches, and tags.
- Use `^`, `~`, `^{type}`, `@{upstream}`, and path expressions in revisions.
- Verify that a revision exists and resolves to the expected object type.
- Recognize ambiguous short refs and use full ref names to avoid mistakes.
- Understand hash abbreviation, object formats, and how to handle non-unique prefixes.
- Use `--show-toplevel`, `--git-dir`, `--git-path`, and repository options in scripts.
- Protect scripts against invalid revision inputs or inputs starting with a hyphen.

## 1. Refs, revisions, and object IDs

Git stores commits, trees, blobs, and tags as objects. Each object has an object ID computed from its content and metadata. In daily workflows, you rarely need to type a full object ID; instead, Git allows reference names or revision expressions.

| Concept | Meaning | Example |
| --- | --- | --- |
| Object ID (OID) | Identifier of an object in the object database | `a1b2c3...` |
| Ref | Name referencing an object | `refs/heads/main`, `refs/tags/v1.0.0` |
| Revision expression | Expression Git resolves to an object or revision range | `HEAD~2`, `main^{commit}` |
| Symbolic ref | Ref pointing to another ref | `HEAD` usually points to `refs/heads/main` |

A branch is a ref that can move when new commits are created. A tag is typically used as a fixed milestone. `HEAD` indicates the current checkout position: normally a symbolic ref pointing to a branch, though it can also point directly to a commit in detached HEAD state.

Example:

~~~text
HEAD
  |
  v
refs/heads/main
  |
  v
commit C (OID: a1b2c3...)
  |
  v
tree -> blob / subtree
~~~

When you run `git rev-parse HEAD`, Git resolves `HEAD` through the current branch to the commit's object ID. When you run `git rev-parse refs/heads/main`, Git reads the `main` branch ref directly. Both results match if `HEAD` has `main` checked out and the branch has not changed between calls.

## 2. What is git rev-parse used for?

`rev-parse` is a tool for parsing and normalizing Git arguments. It can:

- Convert a ref name or revision expression into an object ID.
- Check whether a revision resolves to a commit, tree, or blob.
- Return the full name of a ref or the abbreviated name of a branch.
- Display repository paths, the Git directory, the common directory, or metadata paths.
- Report the object format used by the repository.
- Parse certain revision syntaxes and arguments that scripts pass to Git.

Basic examples:

~~~bash
git rev-parse HEAD
git rev-parse main
git rev-parse origin/main
git rev-parse v1.0.0
~~~

Each command prints the object ID that the corresponding name resolves to. For an annotated tag, the initial object ID may be the tag object rather than the commit the tag points to. When you need the underlying commit, use peel syntax such as `v1.0.0^{commit}`.

`rev-parse` does not replace `git show` or `git log`. It answers "which object or ref does this name resolve to?"; `git show` reads object contents, while `git log` traverses commit history.

## 3. Resolving short refs and full refs

A full ref normally resides under a namespace:

| Ref kind | Full form | Example |
| --- | --- | --- |
| Local branch | `refs/heads/name` | `refs/heads/main` |
| Tag | `refs/tags/name` | `refs/tags/v1.0.0` |
| Remote-tracking branch | `refs/remotes/remote/branch` | `refs/remotes/origin/main` |
| Other ref | `refs/namespace/name` | `refs/notes/commits` |

Git supports shorthand names like `main`, `v1.0.0`, or `origin/main`. It applies ref lookup rules to infer the matching full name. This DWIM (do what I mean) convenience can cause confusion when multiple refs share the same short name.

For example, in a repository that has both a branch and a tag named `release`:

~~~bash
git show-ref --heads --tags
git rev-parse release
git rev-parse refs/heads/release
git rev-parse refs/tags/release
~~~

The short name is resolved according to Git's ref lookup rules; if multiple interpretations exist, Git may warn that the name is ambiguous. Use full names such as `refs/heads/release` or `refs/tags/release` when precision is required, especially in scripts and release workflows.

### Viewing the full ref a name resolves to

~~~bash
git rev-parse --symbolic-full-name main
git rev-parse --symbolic-full-name v1.0.0
~~~

The `--symbolic-full-name` option asks Git to print the full ref name when an argument resolves to a ref. It is useful for checking which namespace a short name points to.

To view the current branch name:

~~~bash
git rev-parse --abbrev-ref HEAD
~~~

If `HEAD` is detached, the output is normally `HEAD` rather than a branch name. You can test for detached state using:

~~~bash
git symbolic-ref --quiet --short HEAD
~~~

`symbolic-ref` fails when `HEAD` is not a symbolic ref; in scripts, check the exit code rather than relying solely on output.

## 4. Verifying a revision exists and has the right object type

A revision can resolve to a commit, tree, blob, or tag object. If a script expects a commit, checking merely that "an object exists" is not enough.

### Using --verify

~~~bash
git rev-parse --verify HEAD
git rev-parse --verify main
~~~

`--verify` requires Git to resolve a single argument to exactly one object ID. If it cannot be resolved, the command returns a non-zero exit code. Use `--quiet` to suppress error messages when a script only needs to check success or failure:

~~~bash
git rev-parse --verify --quiet HEAD
~~~

### Requiring the object to be a commit

~~~bash
git rev-parse --verify 'HEAD^{commit}'
git rev-parse --verify 'refs/tags/v1.0.0^{commit}'
~~~

The `^{commit}` expression asks Git to peel the object down to a commit. If a tag points to a tree or blob instead of a commit, this check fails.

Common type assertions:

| Expression | Condition |
| --- | --- |
| `^{object}` | Object exists, without requiring a specific type |
| `^{commit}` | Resolves to a commit |
| `^{tree}` | Resolves to a tree |
| `^{blob}` | Resolves to a blob |
| `^{tag}` | Object is an annotated tag object |
| `^{}` | Peels tag layers until reaching a non-tag object |

Example checking a tag:

~~~bash
git rev-parse --verify 'v1.0.0^{tag}'
git rev-parse --verify 'v1.0.0^{commit}'
~~~

The first command requires `v1.0.0` to point to a tag object. The second requires the tag to ultimately resolve to a commit. A lightweight tag pointing straight to a commit passes the `^{commit}` check but fails the `^{tag}` check.

### Using cat-file when deeper inspection is needed

~~~bash
git cat-file -t <object-id>
git cat-file -e 'HEAD^{commit}'
git show --no-patch --oneline HEAD
~~~

`rev-parse` is suited for resolving names and checking types via revision syntax. `cat-file -t` prints the actual object type; `cat-file -e` tests whether an object exists and is readable; `git show` displays human-meaningful content.

## 5. Parent selection syntax: ^ and ~

Revision syntax lets you traverse from a commit to its parents.

### ^ selects a parent

- `HEAD^` or `HEAD^1`: first parent.
- `HEAD^2`: second parent.
- `HEAD^3`: third parent if the commit has enough parents.

A normal commit has one parent; a merge commit has two or more parents. Thus `HEAD^` and `HEAD^1` are normally identical, while `HEAD^2` selects the branch that was merged into the merge commit according to parent order.

### ~ follows first-parents

- `HEAD~1`: first parent of `HEAD`.
- `HEAD~2`: first parent of the first parent.
- `HEAD~3`: continue following the first-parent chain three times.

Example:

~~~text
          M (HEAD)
         / \
        A   B
       /
      P
~~~

For merge commit `M`:

- `HEAD^1` is `A`.
- `HEAD^2` is `B`.
- `HEAD~2` is the first parent of `A`, which is `P` in the diagram.

Therefore, `HEAD~2` does not mean "the second most recent commit across all branches." It follows first-parents. Use `^n` when you need a specific parent of a merge commit.

Verify the results:

~~~bash
git rev-parse HEAD^
git rev-parse HEAD^2
git rev-parse HEAD~3
git show --no-patch --oneline 'HEAD^2'
~~~

## 6. Peeling tags and selecting objects inside a tree

An annotated tag points to a tag object; the tag object in turn points to a commit or another object. Peel syntax retrieves the final object or requires a specific object type.

Example:

~~~bash
git rev-parse 'v2.0.0^{tag}'
git rev-parse 'v2.0.0^{}'
git rev-parse 'v2.0.0^{commit}'
git rev-parse 'v2.0.0^{tree}'
~~~

These commands return the object ID of the tag object, the peeled target object, the commit, or the tree respectively. Not every expression succeeds: if the tag does not ultimately point to the requested object type, Git reports an error.

### Selecting a file at a revision

A revision can be combined with a path inside a tree:

~~~bash
git rev-parse 'HEAD:src/app.js'
git rev-parse 'HEAD^{tree}'
~~~

`HEAD:src/app.js` resolves to the file's blob at the `HEAD` commit. `HEAD^{tree}` resolves to the root tree of that commit.

To get a blob from the current index:

~~~bash
git rev-parse ':src/app.js'
~~~

If the index currently has conflicts, you can select each stage:

~~~bash
git rev-parse ':1:src/app.js'
git rev-parse ':2:src/app.js'
git rev-parse ':3:src/app.js'
~~~

In a normal merge conflict, the stages mean:

- Stage 1: common base version.
- Stage 2: ours version.
- Stage 3: theirs version.

Stage expressions are only valid when the index contains those entries, typically while resolving a merge conflict. With rebase, the `ours`/`theirs` interpretation can be counterintuitive because the roles of the rebased branch and base branch differ from a normal merge; identify the active operation and inspect each stage's content before choosing. For non-conflicted files, stage 0 is the normal entry; `:0:path` can be used to explicitly specify stage 0.

To inspect the blob content:

~~~bash
git cat-file -p 'HEAD:src/app.js'
~~~

Do not confuse a blob ID with a file path. A blob contains only content; file names and locations are stored in trees.

## 7. Reflog and time-based selectors

The reflog records updates to local refs. Revision syntax allows selecting past states of `HEAD` or a branch.

Example:

~~~bash
git rev-parse 'HEAD@{0}'
git rev-parse 'HEAD@{1}'
git rev-parse 'main@{yesterday}'
~~~

- `HEAD@{0}`: current value of `HEAD` according to the reflog.
- `HEAD@{1}`: previous value of `HEAD` in the reflog.
- `main@{yesterday}`: state of the `main` ref at the time interpreted as yesterday, if the reflog still holds matching data.

Reflog selectors depend on local data and reflog retention periods. They are not stable refs suitable for sharing with teammates.

### Upstream and push destination

When a branch has an upstream configured:

~~~bash
git rev-parse --symbolic-full-name '@{upstream}'
git rev-parse '@{upstream}^{commit}'
~~~

`@{upstream}` resolves to the current branch's upstream, usually a remote-tracking branch like `refs/remotes/origin/main`.

In workflows that push to a different remote or triangular workflows, the push destination may differ from upstream:

~~~bash
git rev-parse --symbolic-full-name '@{push}'
~~~

If no upstream or push destination is configured, these expressions fail to resolve. Inspect with:

~~~bash
git branch -vv
git config --get-regexp '^branch\..*\.(remote|merge|pushRemote)$'
~~~

### Previously checked-out branch

The expression:

~~~bash
git rev-parse '@{-1}'
~~~

selects the previously checked-out branch/position based on checkout history. It is handy for toggling back and forth between two branches, but depends on local checkout state and is unsuitable as a stable ref name in shared scripts.

## 8. Handling ambiguous ref names and object ID prefixes

### Short refs can be ambiguous

If a branch, tag, or remote-tracking branch share the same name, use full names:

~~~bash
git rev-parse refs/heads/release
git rev-parse refs/tags/release
git rev-parse refs/remotes/origin/release
~~~

You can list refs:

~~~bash
git show-ref
git for-each-ref --format='%(refname) %(objectname)'
~~~

In scripts, avoid relying on short-name guessing rules when refs could collide. Use full refs or verify names before acting.

### Hash prefixes

You can use a prefix of an object ID if it is long enough and unique in the repository:

~~~bash
git rev-parse a1b2c3d
~~~

If the prefix matches multiple objects, Git cannot uniquely identify one and reports it as ambiguous. Never assume hashes are always 40 characters long; repositories may use SHA-1 or SHA-256.

Check the object format:

~~~bash
git rev-parse --show-object-format
~~~

The output is normally `sha1` or `sha256`. Full OID lengths differ accordingly. When storing IDs in automation systems, capture the actual output rather than truncating strings to a fixed length.

### Listing objects matching a prefix

~~~bash
git rev-parse --disambiguate=a1b2
~~~

`--disambiguate` lists object IDs starting with the provided prefix. The prefix must be at least four hex characters. Use this command when investigating an ambiguous prefix; it can return multiple object types, not only commits.

## 9. --short and --abbrev-ref

To display a shorter OID:

~~~bash
git rev-parse --short HEAD
git rev-parse --short=12 HEAD
~~~

Git chooses a length unique within the repository; even when a specific length is requested, it may increase the length if needed to avoid collisions.

To display an abbreviated branch name:

~~~bash
git rev-parse --abbrev-ref HEAD
git rev-parse --abbrev-ref=strict HEAD
~~~

`--abbrev-ref` converts a ref into a human-readable short form. `strict` mode enforces stricter abbreviation rules; if a ref name is ambiguous under DWIM rules, Git may decline to shorten it as expected.

Avoid using short hashes as long-term identifiers in release records or storage systems when the full OID can be stored. Short hashes are primarily for display and interactive typing.

## 10. Using --verify and --end-of-options safely in scripts

Scripts often receive revisions from arguments, environment variables, configuration files, or user input. Input might be empty, invalid, or start with a hyphen. If passed directly to a Git command, Git might interpret it as an option flag rather than a revision.

Use `--verify` to require exactly one object and `--end-of-options` to mark subsequent arguments as revision data:

~~~bash
candidate=$1

if ! oid=$(git rev-parse --verify --quiet --end-of-options "$candidate^{commit}")
then
    echo "Invalid commit revision" >&2
    exit 1
fi

printf 'Resolved commit: %s\n' "$oid"
~~~

The `^{commit}` expression requires the result to be a commit. `--end-of-options` prevents an input string starting with a hyphen from being parsed as an option to `rev-parse`. `--quiet` lets the script handle errors via exit code without printing default resolution error messages.

In PowerShell:

~~~powershell
$candidate = 'main'
$resolved = git rev-parse --verify --quiet --end-of-options "$candidate^{commit}"
if ($LASTEXITCODE -ne 0) {
    throw 'Invalid commit revision'
}
$resolved
~~~

For production scripts, still validate input according to business rules and check Git's exit status. Never use `eval` or concatenate shell command strings from user-supplied revisions.

### Why verify the object type?

If a script invokes `git reset --hard` with a tag name that happens to point to a tree or blob, the operation may fail or behave unexpectedly. Confirming `^{commit}` before passing a revision to a command expecting a commit catches type mismatches early.

Example:

~~~bash
target=$(git rev-parse --verify --quiet --end-of-options 'v1.0.0^{commit}') || exit 1
git show --no-patch --oneline "$target"
~~~

## 11. Options for inspecting repository locations

`rev-parse` is also useful in scripts that need to locate the current repository or its metadata paths.

| Command | Output |
| --- | --- |
| `git rev-parse --show-toplevel` | Absolute path to the working tree root |
| `git rev-parse --show-prefix` | Relative path from the root to the current directory |
| `git rev-parse --show-cdup` | Number of directory levels up to reach the root |
| `git rev-parse --git-dir` | The Git directory currently in use |
| `git rev-parse --git-common-dir` | Shared common Git directory, useful with linked worktrees |
| `git rev-parse --git-path path` | Path to a file or directory inside the Git directory |
| `git rev-parse --is-inside-work-tree` | `true` if the current directory is inside a working tree |
| `git rev-parse --is-inside-git-dir` | `true` if the current directory is inside a Git directory |
| `git rev-parse --is-bare-repository` | `true` if the repository is bare |

Example:

~~~bash
git rev-parse --show-toplevel
git rev-parse --show-prefix
git rev-parse --git-dir
git rev-parse --git-common-dir
git rev-parse --git-path hooks
~~~

### Why use --git-path instead of hardcoding .git?

In a standard repository, users normally see a `.git` directory. However, in linked worktrees, submodules, or repositories using a separate `git-dir`, metadata may reside elsewhere or a file may point to the actual Git directory.

Example getting the index path:

~~~bash
git rev-parse --git-path index
~~~

Example getting the default hooks directory inside the Git directory:

~~~bash
git rev-parse --git-path hooks
~~~

Git computes the path based on the repository layout and relevant environment variables. Scripts should ask Git instead of assuming the index always lives at `.git/index`.

Note: `--git-path hooks` returns the default hooks location inside the Git directory. If the repository configures `core.hooksPath`, Git uses that configured directory instead of the default location. Check separately:

~~~bash
git config --show-origin --get core.hooksPath
~~~

Do not interpret `--git-path hooks` as the active hooks directory in every repository.

### Checking repository and bare repository status

~~~bash
git rev-parse --is-inside-work-tree
git rev-parse --is-inside-git-dir
git rev-parse --is-bare-repository
~~~

These commands output `true` or `false`. In scripts, inspect both the exit code and output to decide whether commands requiring a working tree can run. A bare repository has no normal working tree; many server-side hooks execute inside bare repositories.

## 12. Resolving revision ranges

`rev-parse` can parse range expressions and turn them into revision arguments understood by other commands.

### A..B

The expression `A..B` represents commits reachable from `B` but not reachable from `A`. When parsed with `rev-parse`:

~~~bash
git rev-parse 'main..feature/login'
~~~

Git represents this range with one negated input excluding `A` and one input including `B`, equivalent to:

~~~text
^<OID-of-main>
<OID-of-feature-login>
~~~

To list the actual commits in the range, use:

~~~bash
git log --oneline main..feature/login
~~~

### A...B

The expression `A...B` represents the symmetric difference: commits reachable from `A` or `B` but not from both, based on their merge base. This is useful for comparing two diverged branches:

~~~bash
git log --oneline main...feature/login
~~~

`rev-parse` can normalize revision ranges for other Git commands, but it is not a history display tool. When the goal is to read commits, use `git log`; when you need OIDs or to validate revisions, use `rev-parse`.

## 13. Distinguishing rev-parse from similar commands

| Command | Primary role | When to use |
| --- | --- | --- |
| `git rev-parse` | Resolve revisions/refs, verify types, display repository metadata | Scripts needing OIDs, full refs, or Git paths |
| `git show-ref` | List refs and the object IDs they point to | Checking ref existence and avoiding duplicate names |
| `git cat-file` | Inspect object type, size, and content | Investigating the object database |
| `git show` | Display commit, tag, tree, or blob content in readable form | Reviewing an object |
| `git log` | Traverse commit history | Viewing commit progression and relationships |
| `git symbolic-ref` | Read or update symbolic refs | Checking which branch `HEAD` is attached to |
| `git merge-base` | Find common ancestors between commit histories | Checking ancestry or the merge base of two branches |

Do not use `rev-parse` as a substitute for every other Git command. Use the right tool for the question you are asking.

## 14. Practical workflow: verifying a target before acting

Suppose a script accepts a revision name to create a release tag. Before creating the tag, the script must confirm the target exists and is a commit.

### Step 1: resolve the commit

~~~bash
target=$(git rev-parse --verify --quiet --end-of-options "$1^{commit}") || {
    echo "Target must resolve to a commit" >&2
    exit 1
}
~~~

### Step 2: inspect commit metadata

~~~bash
git show --no-patch --format=fuller "$target"
~~~

Cross-check the commit against the approved pull request, build artifact, or release record.

### Step 3: confirm the tag does not already exist

~~~bash
git show-ref --verify --quiet refs/tags/v4.0.0
~~~

If the command returns exit code `0`, the tag already exists. The script should abort or handle it according to policy rather than overwriting it blindly.

### Step 4: create the tag at the verified commit

~~~bash
git tag -a v4.0.0 "$target" -m "Release v4.0.0"
git rev-parse --verify 'refs/tags/v4.0.0^{commit}'
~~~

Compare the resolved OID against `target` to confirm the tag points to the right commit. For signed tags, use `git tag -s` and verify with `git verify-tag`.

## 15. Common misconceptions

### Is HEAD always a branch name?

No. `HEAD` is normally a symbolic ref pointing to a branch, but when checking out a commit directly, `HEAD` is in a detached state and points directly to a commit.

### Does git rev-parse v1.0.0 always return a commit?

No. If `v1.0.0` is an annotated tag, the command returns the tag object's OID. Use `v1.0.0^{commit}` to request the underlying commit after peeling.

### Are HEAD~2 and HEAD^2 the same?

No. `HEAD~2` follows first-parents twice; `HEAD^2` selects the second parent of the `HEAD` commit, commonly used on merge commits.

### Is a short hash always unique?

No. A prefix can be ambiguous if multiple objects start with the same characters. Git may require additional characters. Store full OIDs in important metadata.

### Is @{-1} the previous commit?

Not necessarily. It selects the previously checked-out branch/position according to checkout history. Use `HEAD@{1}` if the goal is the previous `HEAD` state in the reflog.

### Does --verify only check commits?

No. It checks that an object can be resolved. Use `^{commit}`, `^{tree}`, or `^{blob}` to require a specific object type.

### Does --symbolic-full-name always return an OID?

No. This option displays the full ref name if the argument is a ref. If you need an OID, run normal `rev-parse` or combine it with appropriate options.

## 16. Self-check

A repository has branch `main`, branch `feature/api`, remote-tracking branch `origin/main`, and annotated tag `v2.0.0`. `HEAD` currently has `feature/api` checked out.

Answer the following:

1. Which command gets the commit OID that `HEAD` points to?
2. Which command verifies that `v2.0.0` resolves to a commit?
3. Which command tells you whether `v2.0.0` is a tag object or another object type?
4. What does `HEAD^2` mean if `HEAD` is a merge commit?
5. How does `HEAD~2` differ from `HEAD^2`?
6. Which command inspects the upstream of the current branch?
7. Why should a script use `--verify --end-of-options` and `^{commit}`?
8. Which command gets the hooks path according to the current repository layout?

**Hints:** Use `git rev-parse HEAD` to get the OID. Use `git rev-parse --verify 'v2.0.0^{commit}'` to require a commit. Use `git cat-file -t v2.0.0` to inspect the object type directly. `HEAD^2` is the second parent; `HEAD~2` follows first-parents twice. Use `git rev-parse --symbolic-full-name '@{upstream}'` to inspect the upstream. `--verify` checks for a single valid object, `--end-of-options` protects input from being parsed as options, and `^{commit}` enforces the right type. Use `git rev-parse --git-path hooks` to retrieve the hooks path.

## Conclusion

`git rev-parse` turns ref names and revision expressions into concrete object IDs, verifies object types, and locates repository metadata. Distinguish refs from objects, use `^` and `~` appropriately, peel annotated tags with `^{commit}`, check whether short names are ambiguous, and never assume fixed-length hashes. In scripts, combine `--verify`, `--end-of-options`, and object-type filters to validate targets before acting. When you need Git paths or worktree information, ask Git using `--git-path`, `--git-dir`, and `--git-common-dir` instead of guessing directory layouts.
