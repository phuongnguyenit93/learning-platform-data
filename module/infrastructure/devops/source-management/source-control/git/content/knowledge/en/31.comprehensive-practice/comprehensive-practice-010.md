# Practicing Worktrees, Sparse Checkout, and Submodule Repositories

Git can manage multiple working trees from a single repository, check out only part of a directory tree, and embed external repositories as submodules. These three capabilities address distinct needs: worktrees let you work on multiple branches simultaneously without cloning the repository again; sparse checkout restricts which files appear in a working tree; submodules let a superproject pin a specific commit of a child repository.

This lab combines all three capabilities in an isolated sandbox. You will create a local Git library, add it to an application as a submodule, create a linked worktree for a feature branch, enable sparse checkout to materialize only needed areas, update the submodule, and verify state across working trees.

## 1. Goals and Prerequisites

After this lab, you will be able to:

- Create a linked worktree with git worktree add and inspect the worktree list.
- Understand how branches and the object database are shared while HEAD, index, and working tree are separated per worktree.
- Enable sparse checkout in cone mode and specify which directories to work with.
- Recognize that sparse checkout alters the working tree without automatically making the repository fetch only partial objects.
- Add, initialize, and verify a submodule pinned via a gitlink.
- Coordinate worktrees, sparse checkout, and submodules in a verifiable workflow.
- Clean up a worktree safely without accidentally deleting branches or uncommitted data.

Requirements: a modern Git version supporting git switch, git worktree, and git sparse-checkout; Bash, Git Bash, or WSL terminal; enough disk space for a few lab directories. The lab uses local repositories so it does not depend on external Git hosting.

## 2. Distinguishing the Three Concepts

| Feature | What does it manage? | Use case |
|---|---|---|
| Worktree | Multiple working trees linked to the same repository | Open a hotfix branch in a separate directory while keeping an active feature branch untouched |
| Sparse checkout | The subset of paths checked out into the working tree | Large repository where your work only needs src/api and docs |
| Submodule | An independent Git repository referenced at a path in the superproject | Consuming a library or component with its own history and release lifecycle |

A worktree is not an independent clone: linked worktrees share the main repository's object database and refs, while each worktree maintains its own HEAD, index, and working tree. Sparse checkout controls which portion of the tree is materialized inside a working tree. A submodule has its own repository; the superproject records the submodule's specific commit via a gitlink.

## 3. Creating the Lab Directory and Library Repository

Create a dedicated lab directory. The LAB_ROOT variable in the examples holds the absolute path to the practice directory:

~~~bash
LAB_ROOT="$(pwd)/git-worktree-sparse-lab"
mkdir -p "$LAB_ROOT"
~~~

Create a bare repository to act as the local remote for the library:

~~~bash
git init --bare --initial-branch=main "$LAB_ROOT/math-core.git"
~~~

Create a working repository to develop the library:

~~~bash
git init --initial-branch=main "$LAB_ROOT/math-core-work"
git -C "$LAB_ROOT/math-core-work" config user.name "Git Learner"
git -C "$LAB_ROOT/math-core-work" config user.email "learner@example.test"

printf '# Math Core\n\nLocal library for the Git lab.\n' > "$LAB_ROOT/math-core-work/README.md"
printf 'def add(a, b):\n    return a + b\n' > "$LAB_ROOT/math-core-work/math_core.py"

git -C "$LAB_ROOT/math-core-work" add README.md math_core.py
git -C "$LAB_ROOT/math-core-work" commit -m "Create math core library"
git -C "$LAB_ROOT/math-core-work" remote add origin "$LAB_ROOT/math-core.git"
git -C "$LAB_ROOT/math-core-work" push -u origin main
~~~

Verify the bare remote received the main branch:

~~~bash
git --git-dir="$LAB_ROOT/math-core.git" show-ref
~~~

A bare repository contains only Git data, with no working tree. In this lab, it serves as a local remote so the submodule can fetch pushed commits.

## 4. Creating the Application Repository and Baseline Commit

Initialize the application:

~~~bash
git init --initial-branch=main "$LAB_ROOT/sample-app"
git -C "$LAB_ROOT/sample-app" config user.name "Git Learner"
git -C "$LAB_ROOT/sample-app" config user.email "learner@example.test"

mkdir -p "$LAB_ROOT/sample-app/src/api"
mkdir -p "$LAB_ROOT/sample-app/src/web"
mkdir -p "$LAB_ROOT/sample-app/docs"
mkdir -p "$LAB_ROOT/sample-app/tools"

printf '# Sample App\n' > "$LAB_ROOT/sample-app/README.md"
printf 'route=/api/v1\n' > "$LAB_ROOT/sample-app/src/api/routes.conf"
printf 'page=home\n' > "$LAB_ROOT/sample-app/src/web/page.conf"
printf '# Architecture\n' > "$LAB_ROOT/sample-app/docs/architecture.md"
printf '#!/bin/sh\necho build\n' > "$LAB_ROOT/sample-app/tools/build.sh"

git -C "$LAB_ROOT/sample-app" add README.md src docs tools
git -C "$LAB_ROOT/sample-app" commit -m "Create sample application"
~~~

Verify the repository is clean:

~~~bash
git -C "$LAB_ROOT/sample-app" status --short
git -C "$LAB_ROOT/sample-app" log --oneline --decorate -1
~~~

This is the baseline commit for main. Creating a commit before adding the submodule gives the lab a clear parent history.

## 5. Adding the Library as a Submodule

In real projects, a submodule URL should be a stable HTTPS or SSH address accessible to all team members. This lab uses an absolute local path to the bare repository created above:

~~~bash
# Local lab only: allow file protocol in this repository's config
git -C "$LAB_ROOT/sample-app" config protocol.file.allow always

git -C "$LAB_ROOT/sample-app" submodule add "$LAB_ROOT/math-core.git" libs/math-core
~~~

The submodule add command clones the library repository into libs/math-core and updates two entries in the superproject:

- The .gitmodules file storing the submodule's name, path, and URL.
- A gitlink entry with mode 160000 storing the commit OID that the superproject expects the submodule to check out.

Inspect:

~~~bash
git -C "$LAB_ROOT/sample-app" status
git -C "$LAB_ROOT/sample-app" diff --cached --submodule=log
git -C "$LAB_ROOT/sample-app" ls-files --stage -- libs/math-core
cat "$LAB_ROOT/sample-app/.gitmodules"
~~~

The gitlink's stage should be 0 and its mode should be 160000. Commit the added submodule:

~~~bash
git -C "$LAB_ROOT/sample-app" commit -m "Add math-core submodule"
git -C "$LAB_ROOT/sample-app" ls-tree HEAD -- libs/math-core
git -C "$LAB_ROOT/sample-app" submodule status --recursive
~~~

The absolute path in .gitmodules only works on the machine where this lab was created. Never use absolute local URLs like this in a team repository. In real work, replace it with a stable remote URL and ensure the commit referenced by the gitlink is already pushed to the submodule's remote.

## 6. Creating a Linked Worktree for a Feature Branch

The sample-app repository currently has main checked out in the sample-app directory. Create a second worktree in a sibling directory while creating the feature/api-v2 branch from main:

~~~bash
git -C "$LAB_ROOT/sample-app" worktree add -b feature/api-v2 "$LAB_ROOT/sample-app-api" main
~~~

Check the worktree list:

~~~bash
git -C "$LAB_ROOT/sample-app" worktree list
git -C "$LAB_ROOT/sample-app" worktree list --porcelain
~~~

You will see two working trees:

| Working tree | Branch |
|---|---|
| sample-app | main |
| sample-app-api | feature/api-v2 |

Both directories can be opened in separate terminals or IDEs. Committing in the feature/api-v2 worktree updates the shared branch in the repository; the main working tree retains its own state.

### Checking the Git Directory of a Linked Worktree

In a standard repository, .git is normally a directory. In a linked worktree, .git at the working directory root is normally a file pointing to that worktree's dedicated Git directory:

~~~bash
git -C "$LAB_ROOT/sample-app-api" rev-parse --show-toplevel
git -C "$LAB_ROOT/sample-app-api" rev-parse --absolute-git-dir
git -C "$LAB_ROOT/sample-app-api" rev-parse --git-common-dir
~~~

The per-worktree Git directory stores data such as the worktree's HEAD and index; the common Git directory holds shared data such as the object database and refs. Use rev-parse commands to find actual paths rather than assuming every worktree has its own .git directory at the root.

### A Branch Cannot Be Checked Out in Two Worktrees Simultaneously

Git prevents the same branch from being checked out in two linked worktrees at once. For example, main is checked out in sample-app, so you cannot create another worktree that also checks out main normally. Create a new branch with -b or use detached HEAD when you only want to inspect a commit without attaching to a branch:

~~~bash
git -C "$LAB_ROOT/sample-app" worktree add --detach "$LAB_ROOT/sample-app-review" main
~~~

A detached worktree suits reviews or temporary experiments. If you create commits and want to keep them, create a branch before removing the worktree.

This is an optional example; if you ran it, remove the review worktree once done inspecting:

~~~
git -C "$LAB_ROOT/sample-app" worktree remove "$LAB_ROOT/sample-app-review"
~~~

## 7. Enabling Sparse Checkout in the Feature Worktree

Switch to the linked worktree sample-app-api and enable cone mode:

~~~bash
git -C "$LAB_ROOT/sample-app-api" sparse-checkout init --cone
~~~

Check out only the areas needed for API work, documentation, and the library:

~~~bash
git -C "$LAB_ROOT/sample-app-api" sparse-checkout set src/api docs libs/math-core
~~~

List the currently selected directories:

~~~bash
git -C "$LAB_ROOT/sample-app-api" sparse-checkout list
~~~

In cone mode, Git keeps files at the repository root, files in parent directories along selected paths, and all contents inside the selected directories. With the path set above, src/api, docs, and libs/math-core appear; src/web is not checked out. This rule makes directory selection intuitive and performs better than arbitrary path patterns in non-cone mode.

Inspect the file tree:

~~~bash
find "$LAB_ROOT/sample-app-api" -maxdepth 3 -type f
git -C "$LAB_ROOT/sample-app-api" status --short
~~~

On Windows PowerShell, you can list files using Get-ChildItem instead of find.

### Adding or Changing Sparse Checkout Scope

To add a directory while keeping existing selections:

~~~bash
git -C "$LAB_ROOT/sample-app-api" sparse-checkout add tools
~~~

To replace the entire directory list, use sparse-checkout set with the new list. To reapply patterns after a special checkout or update operation:

~~~bash
git -C "$LAB_ROOT/sample-app-api" sparse-checkout reapply
~~~

To return to a full working tree:

~~~bash
git -C "$LAB_ROOT/sample-app-api" sparse-checkout disable
~~~

Disable turns off sparse checkout and restores missing tracked files into the working tree. It does not delete repository history or objects.

### Sparse Checkout Is Not the Same as Partial Clone

Sparse checkout limits which paths are checked out into the working tree. With a standard clone, the object database still holds all cloned objects, including objects for directories currently hidden from the working tree.

If your goal is to reduce the volume of objects downloaded from the remote as well, combine sparse checkout with partial clone—for example, cloning with a blob:none filter and then selecting the required directories. This is an advanced setup requiring server support for filtering; sparse checkout alone does not shrink the object database proportionally to the visible files.

## 8. Initializing the Submodule in the Linked Worktree

Submodules are pinned by the superproject at a specific commit. In a new working tree, the submodule may need to be initialized and checked out to the gitlink commit. Because the lab included libs/math-core in sparse checkout, the submodule path is within the checked-out scope.

Run:

~~~bash
git -C "$LAB_ROOT/sample-app-api" submodule update --init --recursive
~~~

Inspect:

~~~bash
git -C "$LAB_ROOT/sample-app-api" submodule status --recursive
git -C "$LAB_ROOT/sample-app-api" status --short
git -C "$LAB_ROOT/sample-app-api" ls-tree HEAD -- libs/math-core
~~~

Submodules normally sit in detached HEAD at the OID specified by the gitlink. This is expected behavior because the superproject pins a specific commit rather than tracking the latest branch tip automatically.

If a submodule is omitted from sparse checkout, its directory may be absent or uninitialized in the working tree. Add the submodule path to the sparse checkout set first, then run submodule update. In real repositories, ensure submodule URLs and access permissions are valid.

When cloning a fresh superproject, you can fetch submodules recursively upfront:

~~~bash
git clone --recurse-submodules <superproject-url> sample-app
~~~

If you already cloned without initializing submodules:

~~~bash
git submodule update --init --recursive
~~~

## 9. Making Changes Inside the Feature Worktree

In the sample-app-api worktree, modify a file within the sparse checkout scope:

~~~bash
printf 'route=/api/v2\n' > "$LAB_ROOT/sample-app-api/src/api/routes.conf"
printf 'endpoint=/users\n' > "$LAB_ROOT/sample-app-api/src/api/users.conf"

git -C "$LAB_ROOT/sample-app-api" status --short
git -C "$LAB_ROOT/sample-app-api" diff
~~~

Stage and commit:

~~~bash
git -C "$LAB_ROOT/sample-app-api" add src/api/routes.conf src/api/users.conf
git -C "$LAB_ROOT/sample-app-api" diff --cached
git -C "$LAB_ROOT/sample-app-api" commit -m "Add API v2 routes"
~~~

Confirm the feature/api-v2 branch advanced:

~~~bash
git -C "$LAB_ROOT/sample-app-api" log --oneline --decorate -3
git -C "$LAB_ROOT/sample-app" branch --list
git -C "$LAB_ROOT/sample-app" worktree list
~~~

Switch back to checking the main worktree:

~~~bash
cat "$LAB_ROOT/sample-app/src/api/routes.conf"
git -C "$LAB_ROOT/sample-app" status --short
~~~

The main worktree still shows the contents of the commit on main and does not automatically pull in changes from feature/api-v2. Both worktrees share the repository and refs, while each directory maintains its own checkout state.

## 10. Updating Code Inside the Submodule

The submodule is checked out in detached HEAD at the gitlink commit. For this lab, update the library inside the separate working repository math-core-work, push the commit to the bare remote, and then update the submodule inside the feature worktree. This clearly separates the two steps: developing the child repository and advancing the pointer in the superproject.

Create a branch and new commit in the library repository:

~~~bash
git -C "$LAB_ROOT/math-core-work" switch -c feature/math-multiply
printf 'def multiply(a, b):\n    return a * b\n' >> "$LAB_ROOT/math-core-work/math_core.py"

git -C "$LAB_ROOT/math-core-work" add math_core.py
git -C "$LAB_ROOT/math-core-work" commit -m "Add multiply helper"
git -C "$LAB_ROOT/math-core-work" push -u origin feature/math-multiply
~~~

Inside the feature worktree's submodule, fetch the pushed branch and check out the new commit. Checking out the OID via FETCH_HEAD keeps the submodule in detached HEAD:

~~~bash
git -C "$LAB_ROOT/sample-app-api/libs/math-core" fetch origin feature/math-multiply
git -C "$LAB_ROOT/sample-app-api/libs/math-core" checkout FETCH_HEAD
git -C "$LAB_ROOT/sample-app-api/libs/math-core" log --oneline -1
~~~

Committing in the submodule only changes the child repository's history. The superproject still records the old gitlink OID. To update the pointer in the superproject:

~~~bash
git -C "$LAB_ROOT/sample-app-api" status --short
git -C "$LAB_ROOT/sample-app-api" diff --submodule=log
git -C "$LAB_ROOT/sample-app-api" add libs/math-core
git -C "$LAB_ROOT/sample-app-api" diff --cached --submodule=log
git -C "$LAB_ROOT/sample-app-api" commit -m "Advance math-core submodule"
~~~

The sharing order in a real workflow is to push the child repository commit first, and only then push the superproject commit containing the updated gitlink. If the superproject points to a submodule commit not yet pushed to its remote, teammates will fail to fetch that version.

In this lab, the library's remote is the local bare repository. The feature/math-multiply branch was pushed there so the new OID can be fetched. The absolute local URL in .gitmodules remains suitable only for this lab machine; never share such a config with a team.

## 11. Verifying the State of All Three Components

Before finishing, inspect each layer separately:

~~~bash
# Superproject in the feature worktree
git -C "$LAB_ROOT/sample-app-api" status
git -C "$LAB_ROOT/sample-app-api" branch --show-current
git -C "$LAB_ROOT/sample-app-api" sparse-checkout list

# List of linked worktrees of the superproject
git -C "$LAB_ROOT/sample-app" worktree list --porcelain

# Submodule and pinned commit
git -C "$LAB_ROOT/sample-app-api" submodule status --recursive
git -C "$LAB_ROOT/sample-app-api" ls-tree HEAD -- libs/math-core

# Superproject in the main worktree
git -C "$LAB_ROOT/sample-app" status
git -C "$LAB_ROOT/sample-app" branch --show-current
~~~

Outcomes to verify:

- sample-app is on main; sample-app-api is on feature/api-v2.
- Each worktree has its own working tree and index.
- Sparse checkout in sample-app-api shows only the selected directories; if you ran the extension step in section 7, tools is also visible.
- The submodule is initialized and checked out at the exact gitlink OID from the superproject commit.
- API changes are committed on feature/api-v2; main does not have those commits yet.
- No unintended changes remain in either working tree.

## 12. Cleaning Up the Worktree After Practice

Before deleting a linked worktree, ensure any changes you want to keep are committed or backed up. Then remove the worktree:

~~~bash
git -C "$LAB_ROOT/sample-app" worktree remove "$LAB_ROOT/sample-app-api"
git -C "$LAB_ROOT/sample-app" worktree list
~~~

The remove command deletes the specified working tree and its linked metadata. It does not delete the feature/api-v2 branch. The branch still exists in the shared repository and can be merged or retained:

~~~bash
git -C "$LAB_ROOT/sample-app" branch --list feature/api-v2
~~~

If you want to delete the branch, do so only after confirming it is merged or has no commits you still need:

~~~bash
git -C "$LAB_ROOT/sample-app" branch -d feature/api-v2
~~~

Do not use -D to force-delete without verifying. If you deleted a worktree directory manually via the OS, Git may retain stale metadata; after confirming the path is truly gone, run:

~~~bash
git -C "$LAB_ROOT/sample-app" worktree prune
~~~

Prune cleans up metadata for missing worktrees; it does not delete active branches. Never run prune as a substitute for worktree remove when the working tree still holds data you need.

## 13. Common Errors and How to Handle Them

| Situation | Common cause | How to resolve |
|---|---|---|
| Cannot check out branch in new worktree | Branch is already checked out in another worktree | Create a new branch with -b or use --detach |
| Worktree reported dirty on remove | Uncommitted or unsaved changes remain | Check status, commit or back up, then remove again |
| Expected files missing in sparse worktree | Path is not in the sparse checkout set | Use sparse-checkout add or set to include the directory |
| Submodule directory is empty | Not initialized/updated or path excluded from sparse selection | Add submodule path to sparse checkout, then run submodule update --init --recursive |
| Submodule is in detached HEAD | Superproject checks out a specific gitlink | Normal when only consuming; create a child branch if you need to edit and commit |
| New child commit does not update superproject | Gitlink change not staged in superproject | Run git add <submodule-path> and commit in the superproject |
| Teammates cannot fetch submodule commit | Gitlink points to an unpushed commit or unreachable URL | Push child repository first; verify URL and permissions |
| Sparse checkout does not shrink clone size as expected | Sparse checkout restricts working tree, not necessarily downloaded objects | Consider partial clone if supported by the remote |

## 14. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| Each worktree is an independent clone | Linked worktrees share the main repository's object database and refs, while maintaining separate HEAD, index, and working tree. |
| You can check out the same branch in multiple worktrees | Git normally locks a branch already checked out in another worktree to prevent two places from advancing the same branch independently. |
| Removing a worktree deletes its branch | Worktree remove only deletes the working tree and linked metadata; the branch remains. |
| Sparse checkout deletes files from the repository | It controls which files are materialized in the working tree; it does not remove commits or objects from history. |
| Sparse checkout automatically reduces downloaded objects | Not necessarily; reducing downloaded object data requires combining with partial clone where supported. |
| Cone mode accepts arbitrary file patterns | Cone mode is designed around directory prefixes; use non-cone mode if arbitrary patterns are needed and understand its cost. |
| A submodule is a directory committed in full into the superproject | The superproject stores .gitmodules and a mode 160000 gitlink pointing to the child repository commit. |
| Committing inside a submodule auto-updates the superproject | You must stage the submodule path and commit the gitlink update in the superproject. |
| Submodule detached HEAD is an error | This is the normal state when checking out the commit pinned by the superproject. |

## 15. Self-Check Questions

1. **Which command creates a linked worktree and a new branch from main?**
   - git worktree add -b <branch> <path> main.
2. **Which command lists all worktrees?**
   - git worktree list.
3. **Which command enables sparse checkout in cone mode?**
   - git sparse-checkout init --cone.
4. **Which command selects directories to check out?**
   - git sparse-checkout set <directory...>.
5. **Does sparse checkout automatically remove objects outside selected areas from the object database?**
   - No. It primarily limits the working tree; partial clone is the mechanism for reducing fetched objects when supported by the server.
6. **How does the superproject record the pinned submodule version?**
   - A mode 160000 gitlink containing the child repository's commit OID.
7. **After committing in a submodule, what must you do so the superproject records the new commit?**
   - Stage the submodule path and commit the gitlink change in the superproject.
8. **Which command removes a linked worktree cleanly?**
   - git worktree remove <path>, after safeguarding any needed changes.

## Conclusion

Worktrees create multiple working trees sharing a single repository for parallel work across branches. Sparse checkout limits which directories appear in a working tree, while submodules keep child repositories pinned at the commit specified by the superproject. In a combined workflow, create a separate worktree, enable sparse checkout including needed submodule paths, initialize submodules, and verify branches, path sets, and gitlinks. Before cleaning up, confirm all changes are committed or saved; removing a worktree does not delete its branch, and sparse checkout does not delete objects from the repository.
