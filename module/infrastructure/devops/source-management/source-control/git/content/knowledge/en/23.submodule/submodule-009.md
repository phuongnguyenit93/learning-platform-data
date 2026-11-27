# Changing URLs, Syncing Configuration, and Removing a Submodule Safely

Submodules allow a superproject repository to record another Git repository as a dependent component. When the child repository's address changes, existing clones must update their URL configuration to continue fetching and updating the submodule. When a submodule is no longer needed, the team must unlink it from the superproject, handle local data, and decide whether to keep or delete the submodule's cached repository.

These operations touch multiple storage locations: the committed and shared .gitmodules file, local configuration in .git/config, the gitlink in the superproject's index, the submodule's working directory, and the Git repository stored in .git/modules. Confusing those components can result in changing a URL without other machines picking it up, deleting a directory while leaving stale metadata behind, or losing local commits inside the submodule.

After this lesson, you will be able to:

- Distinguish the URL in .gitmodules from the local URL in .git/config.
- Change a submodule URL using git submodule set-url.
- Synchronize URL configuration using git submodule sync.
- Update submodules to the commits recorded by the superproject.
- Inspect status and local commits in the child repository before removal.
- Temporarily uninitialize a submodule with deinit.
- Remove a submodule from the superproject and commit the change properly.
- Understand when to keep or delete the cached repository in .git/modules.

## 1. Submodules Are Stored Across Multiple Layers

A submodule is not just a directory containing source code. The superproject manages a submodule using several components:

| Component | Role | Shared via Commits? |
| --- | --- | --- |
| .gitmodules | Declares the submodule's name, path, and URL; may include branch or update settings. | Yes. |
| Gitlink in index/tree | Records the child repository commit ID required by the superproject. | Yes. |
| .git/config | Stores local configuration, including the submodule's URL and initialization state. | No. |
| Submodule working directory | Holds the source files checked out at the specified commit. | Contents belong to the child repository. |
| .git/modules/ | Stores the separate Git repository of each submodule in the current clone. | Not committed as superproject content. |

Example layout:

~~~text
product/
|-- .git/
|   +-- modules/
|       +-- shared-lib/       <- Git repository of the submodule
|-- .gitmodules
|-- src/
+-- vendor/
    +-- shared-lib/           <- working tree of the submodule
        |-- .git              <- file pointing to .git/modules/shared-lib
        +-- library files
~~~

The submodule's working directory typically contains a .git file pointing to the child repository stored in .git/modules/NAME inside the superproject. As a result, the child repository maintains its own Git metadata while still being neatly managed inside the superproject's data area.

In the superproject, the path vendor/shared-lib is stored as a gitlink with mode 160000. The gitlink points to a specific commit in the child repository. It does not store all files of the submodule inside the superproject's tree.

The .gitmodules file is configuration shared with teammates. The corresponding configuration in .git/config belongs to the current clone. Therefore, editing the URL in .gitmodules and syncing the local URL are related actions, not identical ones.

## 2. Inspecting Submodules and Current URLs

Before changing a URL or removing a submodule, check the status:

~~~bash
git submodule status --recursive
git status --short --branch
git config -f .gitmodules --get-regexp '^submodule\..*\.'
~~~

git submodule status --recursive lists the commit each submodule currently has checked out and its state. The leading character generally means:

| Character | Meaning |
| --- | --- |
| Space | Submodule has the exact commit recorded by the superproject checked out. |
| - | Submodule has not been initialized. |
| + | Submodule has a different commit checked out from the gitlink recorded by the superproject. |
| U | Gitlink is in a conflict state. |

Inspect .gitmodules contents:

~~~bash
git config -f .gitmodules --list
~~~

Example:

~~~text
submodule.shared-lib.path=vendor/shared-lib
submodule.shared-lib.url=https://git.example.com/team/shared-lib.git
~~~

The name in the section submodule.shared-lib is the submodule name; the path value is the directory path inside the superproject. The two values often match, though they do not have to. When locating the cached repository in .git/modules, use the section name rather than assuming it always equals the path.

Inspect locally configured URLs:

~~~bash
git config --get-regexp '^submodule\..*\.url$'
~~~

The URL in .gitmodules shows the shared address declared by the repository. The URL in .git/config shows the address the current clone is actually using. The two values can differ if the URL changed upstream while the local clone has not run sync yet.

## 3. Changing URLs with git submodule set-url

Suppose the submodule vendor/shared-lib moved from an old server to a new server. Use:

~~~bash
git submodule set-url vendor/shared-lib https://git.example.com/platform/shared-lib.git
~~~

This command updates the submodule's URL in .gitmodules and the corresponding local configuration. It informs the current clone of the new address while producing a .gitmodules change that can be committed so other clones receive it too.

Inspect the change:

~~~bash
git diff -- .gitmodules
git config -f .gitmodules --get-regexp '^submodule\..*\.url$'
git config --get-regexp '^submodule\..*\.url$'
~~~

If you prefer editing .gitmodules manually, update the url value in the right submodule section, then synchronize local configuration with git submodule sync. Using set-url is usually less prone to picking the wrong section.

### Changing the URL Does Not Mean Changing the Submodule Commit

The URL only tells Git where to fetch the child repository. The superproject still records the submodule's commit ID in the gitlink. If the new repository contains the recorded commit, the submodule can continue checking out the exact same content from the new address.

If the new repository lacks the commit requested by the gitlink, git submodule update may fail. In that case, verify whether the new repository holds the matching history, or update the submodule to a new commit and commit the gitlink in the superproject.

### Using Relative URLs

.gitmodules can use relative URLs, for example:

~~~ini
[submodule "shared-lib"]
    path = vendor/shared-lib
    url = ../shared-lib.git
~~~

Git resolves relative URLs against the superproject's default remote URL. This is useful when multiple repositories sit side by side on the same server and are mirrored together. For superproject repository team/product.git, the URL ../shared-lib.git typically points to team/shared-lib.git.

Do not arbitrarily replace ../shared-lib.git with ./shared-lib.git; single-dot and double-dot prefixes have different path meanings. If the repository moves to another host or namespace, verify that the relative URL resolves to the intended address.

## 4. Synchronizing URLs with git submodule sync

When a new commit changes a URL in .gitmodules, clones that have already initialized the submodule may still retain the old URL in .git/config. Run:

~~~bash
git submodule sync
~~~

This command reads URLs in .gitmodules and syncs them into the local configuration of already-initialized submodules. To apply recursively to nested submodules:

~~~bash
git submodule sync --recursive
~~~

Or sync only one submodule:

~~~bash
git submodule sync -- vendor/shared-lib
~~~

Sync only updates URL configuration. It does not fetch objects, check out new commits, or modify gitlinks in the superproject.

A typical sequence when receiving a URL change from a teammate:

~~~bash
# Fetch new superproject commits
git pull

# Update local URLs according to the new .gitmodules
git submodule sync --recursive

# Initialize or check out submodules per gitlinks
git submodule update --init --recursive
~~~

If the superproject was updated via merge or rebase, inspect .gitmodules after integration before running sync. For a submodule that had a custom local URL override, sync will reset the URL setting back to the value declared in .gitmodules; only run it if that is what you intend.

## 5. Initializing and Updating Submodules to Recorded Commits

Once the URL is correct, use:

~~~bash
git submodule update --init --recursive
~~~

- --init registers and initializes uninitialized submodules.
- update fetches necessary objects and checks out the commit recorded by the superproject in the gitlink.
- --recursive continues processing submodules nested inside other submodules.

By default, submodules are usually checked out in detached HEAD at the commit required by the superproject. This is normal: the superproject pins a specific commit so all clones reproduce the exact same dependency version.

Verify the result:

~~~bash
git submodule status --recursive
git diff --submodule
~~~

If a submodule line starts with +, the checked-out commit does not match the gitlink. You can update again with git submodule update --init --recursive, but confirm beforehand that no local changes inside the submodule need to be kept.

### When You Want to Track the Latest Branch Instead of the Pinned Commit

git submodule update --remote is a different operation from standard update:

~~~bash
git submodule update --remote -- vendor/shared-lib
~~~

This command fetches and updates the submodule to the configured remote branch (or the default remote branch if unspecified). It may move the submodule to a commit newer than the current gitlink. When the superproject needs to record that new version, stage the submodule path and commit the gitlink:

~~~bash
git add vendor/shared-lib
git diff --cached --submodule
git commit -m "Update shared library revision"
~~~

Do not use --remote as a default replacement for git submodule update. In reproducible build workflows, checking out the pinned commit is usually the right choice; use update --remote only when the team actively intends to upgrade the dependency along a branch.

## 6. Checking Local Work Before Removing a Submodule

Before deinitializing or removing, inspect the child repository. Check inside the submodule directory:

~~~bash
git -C vendor/shared-lib status --short --branch
git -C vendor/shared-lib branch -vv
git -C vendor/shared-lib log --oneline --decorate -n 12
~~~

Determine:

- Are there uncommitted changes in the submodule's working tree?
- Are there local commits not yet pushed to remote?
- Is the submodule in detached HEAD or on a branch?
- Are there untracked or ignored files containing data that must be preserved?
- Do local commits need to be shared, moved to another branch, or saved as patches?

Commits in a child repository do not automatically become commits in the superproject. The superproject only records one commit ID via a gitlink. If the submodule has new commits you want teammates to receive, first make sure those commits are reachable from the submodule's remote, then update the gitlink and commit in the superproject.

For example, if the submodule has local commits to preserve:

~~~bash
git -C vendor/shared-lib switch -c backup/shared-lib-work
git -C vendor/shared-lib push -u origin backup/shared-lib-work
~~~

Adjust branch and remote names to match your environment. If commits are not ready to push, back them up or export patches according to your team's workflow. Never delete the cached repository before confirming all important commits and changes have been saved.

## 7. Deinit: Uninitializing While Keeping the Submodule Declaration

git submodule deinit is used when you want to remove a submodule's working tree from the current clone while keeping the submodule in the superproject.

~~~bash
git submodule deinit -- vendor/shared-lib
~~~

This command unregisters the submodule from local configuration and deletes its working tree. The declaration in .gitmodules and the gitlink in superproject commits remain intact. The local Git repository is normally preserved in .git/modules, so it can be reinitialized later:

~~~bash
git submodule update --init -- vendor/shared-lib
~~~

To deinitialize all submodules:

~~~bash
git submodule deinit --all
~~~

This operation is useful when a clone only needs part of the repository temporarily, or when you want to clean up the working tree while preserving the project's dependency structure.

### Deinit with Force

If the submodule still has local changes or cannot be safely deinitialized, Git may refuse. The -f option forces deinit:

~~~bash
git submodule deinit -f -- vendor/shared-lib
~~~

Force can discard a working tree containing unsaved changes. Before using it, commit, push, stash, or back up any data you need to keep. Deinit is not the way to permanently remove a submodule from superproject history.

## 8. Permanently Removing a Submodule from the Superproject

If the project no longer depends on a submodule, remove its gitlink and corresponding declaration from the superproject. First inspect status and save work in the child repository as shown in the previous section.

A clear sequence is:

~~~bash
# 1. Unregister local config and working tree of the submodule
git submodule deinit -- vendor/shared-lib

# 2. Remove the gitlink from the superproject's index and working tree
git rm -- vendor/shared-lib

# 3. Inspect changes
git status --short
git diff -- .gitmodules
git diff --cached --submodule

# 4. Commit the submodule removal
git commit -m "Remove shared library submodule"
~~~

git rm stages the removal of the gitlink from the superproject and typically removes the corresponding section from .gitmodules as well. Inspect both .gitmodules and the staged diff before committing. If Git does not automatically remove the right section due to structure or prior edits, edit the exact section in .gitmodules, stage the file, and re-verify.

After committing, other clones receive the submodule removal when they pull or check out the new commit. Their working trees will reflect that the submodule path is no longer part of the superproject.

### When git rm Refuses

If the submodule has local changes, Git may refuse in order to protect data. Do not rush to add -f. Inspect first:

~~~bash
git -C vendor/shared-lib status --short --branch
git submodule status --recursive
~~~

Save necessary commits and files first. Once you have confirmed all changes can be discarded, you may run:

~~~bash
git rm -f -- vendor/shared-lib
~~~

-f bypasses certain safety checks in git rm and can lose local contents inside the submodule working tree. Use it only after verifying the exact path and accepting the consequences.

## 9. Should the Cached Repository in .git/modules Be Deleted?

After deinitializing or removing a submodule, its separate Git repository may remain inside .git/modules. This makes it possible to reinitialize the submodule or recover local commits if needed.

Check the submodule's administrative directory:

~~~bash
git rev-parse --git-path modules/shared-lib
~~~

The name shared-lib in the example is the submodule section name. If the name in .gitmodules differs from the path vendor/shared-lib, use the actual section name. You can look up the mapping with:

~~~bash
git config -f .gitmodules --get-regexp '^submodule\..*\.path$'
~~~

Do not delete the cache merely because the working tree directory disappeared. The cache may hold unpushed local commits, backup branches, or data needed for recovery. Only consider deleting it when:

1. The submodule has been removed from the superproject and the change is committed.
2. No worktree or process is still using the child repository.
3. All commits and local data worth keeping have been pushed or backed up.
4. You have identified the exact cache directory of the exact submodule.

If you truly want to delete the cached repository, use filesystem tools on the exact path returned by git rev-parse --git-path. This is a local data deletion operation that Git cannot automatically undo. Do not delete the entire .git/modules directory because it may hold other submodules.

For many teams, keeping the cache around for a period after removal is a prudent choice. It does not affect superproject commits and aids recovery if you discover data is still needed.

## 10. Changing URLs and Removing Nested Submodules

A submodule can contain other submodules. In that case, use recursive options when syncing or initializing:

~~~bash
git submodule sync --recursive
git submodule update --init --recursive
~~~

If changing only the URL of a deeply nested submodule, identify its exact relative path within the superproject or parent submodule. Run the command in the repository containing the .gitmodules file that declares that submodule.

When removing a parent submodule, inspect any inner submodules and their local data first. Removing the parent working tree can make the entire nested subdirectory tree disappear from the working tree; cached repositories for nested submodules may remain in the administrative area. Do not delete caches by guessing path names; identify each section name and its corresponding storage location before cleaning up.

## 11. Inspecting Submodule Changes in the Superproject

The superproject records a submodule's commit as a gitlink. Some useful commands:

~~~bash
# View status of all submodules
git submodule status --recursive

# View gitlink changes compared to current commit
git diff --submodule

# View the gitlink stored in a commit
git ls-tree HEAD vendor/shared-lib

# View staged changes
git diff --cached --submodule
~~~

git ls-tree displays mode 160000, type commit, and the commit ID of the child repository. This proves the superproject stores a commit pointer rather than storing submodule file contents as regular files.

If only the URL changed, the staged diff primarily shows changes to .gitmodules. If the submodule version was updated, the staged diff shows the gitlink moving from the old commit to the new commit. If the submodule was removed, the staged diff shows the gitlink deleted and .gitmodules updated.

## 12. Hands-on Workflow: Moving a Submodule to a New URL

Suppose vendor/shared-lib moves from an old server to a new server, while the superproject still needs the exact current commit:

~~~bash
# 1. Confirm initial status
git status --short --branch
git submodule status --recursive

# 2. Change the declared URL
git submodule set-url vendor/shared-lib https://git.example.com/platform/shared-lib.git

# 3. Inspect configuration change
git diff -- .gitmodules

# 4. Sync local URLs, including nested submodules if any
git submodule sync --recursive

# 5. Fetch and check out the commit recorded by the superproject
git submodule update --init --recursive

# 6. Verify
git submodule status --recursive
git status --short

# 7. Commit the URL change in the superproject
git add .gitmodules
git diff --cached
git commit -m "Update shared library submodule URL"
~~~

If the new URL does not have the commit required by the gitlink, stop and verify the repository's history. Do not arbitrarily update the gitlink to a new commit without team approval.

## 13. Hands-on Workflow: Removing an Unneeded Submodule

Suppose the project replaced vendor/shared-lib with another library:

~~~bash
# 1. Inspect superproject and submodule status
git status --short --branch
git submodule status --recursive
git -C vendor/shared-lib status --short --branch
git -C vendor/shared-lib log --oneline -n 10

# 2. Save any local commits or files worth keeping

# 3. Deinit to remove local configuration and working tree
git submodule deinit -- vendor/shared-lib

# 4. Remove the gitlink from the superproject
git rm -- vendor/shared-lib

# 5. Verify .gitmodules and index
git status --short
git diff -- .gitmodules
git diff --cached --submodule

# 6. Commit the submodule removal
git commit -m "Remove shared library submodule"

# 7. Check the remaining submodule list
git submodule status --recursive
~~~

After committing, decide whether to keep the cached repository in .git/modules. Delete the cache only after confirming no commits or local data remain that need to be preserved.

## 14. Common Errors

### Edited .gitmodules, but Fetch Still Uses the Old URL

The current clone may still have the old URL configured in .git/config. Run git submodule sync or git submodule sync --recursive, then check local configuration. If you just changed the URL with set-url, verify both .gitmodules and .git/config.

### Sync Finished, Yet Submodule Contents Did Not Change

This is normal behavior. Sync only synchronizes URLs; it does not fetch or check out commits. Use git submodule update --init --recursive to retrieve the commit recorded by the superproject.

### Submodule Update Reports Commit Not Found

The repository at the new URL may not contain the commit referenced by the gitlink. Check permissions, URL, history, and repository mirroring. Update the gitlink to another commit only after confirming the new dependency version.

### Deinit Completed, Yet Submodule Still Appears in .gitmodules

This is expected behavior. Deinit only uninitializes locally; it leaves the declaration and gitlink in the superproject. To remove permanently, use git rm and commit.

### Deleted Directory, Yet Data Remains in .git/modules

The cached repository is retained so it can be reinitialized. This is not necessarily an error. Clean up the cache only after removing the submodule from the superproject and confirming no data needs to be kept.

### Superproject Reports Submodule Has a Different Commit

A + in git submodule status indicates the checked-out commit differs from the gitlink. Inspect changes inside the submodule; if the new commit is intentional, stage the submodule path and commit the gitlink. Otherwise, run update to return to the recorded commit after preserving local work.

## 15. Key Takeaways

- .gitmodules is the shared submodule configuration; .git/config holds the clone's local configuration.
- git submodule set-url updates the declared URL; git submodule sync syncs URLs from .gitmodules into local configuration.
- Sync does not fetch, check out, or change gitlinks.
- git submodule update --init --recursive fetches and checks out commits pinned by the superproject.
- A gitlink has mode 160000 and points to a commit in the child repository.
- deinit removes the working tree and local registration while keeping the submodule declaration in the superproject.
- git rm removes the gitlink and updates .gitmodules; commit the change so teammates receive it.
- The cached repository in .git/modules can hold local commits; delete it only after inspecting and backing up necessary data.
- Changing a URL, updating a submodule commit, and removing a submodule are three distinct types of changes; inspect staged diffs before committing.

When you clearly understand shared URLs, local configuration, gitlinks, and cached repositories, you can move a submodule to a new server or remove it from a project while keeping full control over history and local data.
