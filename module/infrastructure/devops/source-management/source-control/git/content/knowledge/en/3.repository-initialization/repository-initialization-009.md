# Identifying Unintended Nested Repositories and Submodule Boundaries

A project directory can contain multiple subdirectories, yet not every subdirectory belongs to the same Git repository. If you run <code>git init</code> or clone a repository inside a repository you are already working in, Git recognizes a nested repository. From that point onward, commands executed inside the subdirectory can operate on a different repository from the parent repository.

Nested repositories are sometimes intentional, such as a submodule or a linked worktree. However, when one appears unintentionally, it can cause Git to skip the subdirectory's contents, stage a gitlink instead of files, or leave teammates cloning an empty directory path.

This lesson shows how to determine the repository root, distinguish between standalone repositories, submodules, and worktrees, understand the boundaries Git creates, and choose a safe resolution.

## 1. What is a nested repository?

A nested repository occurs when a directory inside a parent repository's working tree contains its own Git metadata.

Example:

~~~text
workspace/
├── .git/
├── README.md
├── src/
└── tools/
    └── converter/
        ├── .git/
        ├── README.md
        └── src/
~~~

Here:

- <code>workspace</code> is the parent repository.
- <code>tools/converter</code> is the child repository.
- Each repository has its own history, refs, index, and configuration.
- Git commands run inside <code>tools/converter</code> typically select the nearest child repository.
- Git commands run from the <code>workspace</code> root treat the subdirectory as a repository boundary.

A nested repository can be created by:

- Accidentally running <code>git init</code> inside a subdirectory.
- Cloning another project into a directory belonging to the current repository.
- Extracting source code that already contains a <code>.git</code> directory.
- Adding an independent project into a monorepo without deciding how to manage it.
- Creating a worktree or submodule without realizing they use separate metadata.

Not every subdirectory entry named <code>.git</code> is a completely standalone repository. In submodules and linked worktrees, <code>.git</code> is typically a file pointing to metadata stored elsewhere. Always inspect before moving or deleting it.

## 2. Why does Git create boundaries between repositories?

When Git searches for a repository from the current directory, it looks for Git metadata in that directory and walks up parent directories. Upon encountering the nearest repository, Git uses that repository for subsequent commands.

Suppose the layout is:

~~~text
project/
├── .git/
└── vendor/
    └── library/
        └── .git/
~~~

If the terminal is in <code>project/vendor/library</code>, Git finds the child repository first and uses it. If the terminal is in <code>project</code>, Git uses the parent repository.

This explains why two commands can return two different roots:

~~~bash
git -C . rev-parse --show-toplevel
git -C vendor/library rev-parse --show-toplevel
~~~

The first command returns the parent repository's root. The second returns the child repository's root if that directory is indeed a separate repository.

Git does not automatically merge the two histories. The parent repository does not automatically track every file inside the child repository as regular files.

## 3. Finding the current repository root

The most basic command:

~~~bash
git rev-parse --show-toplevel
~~~

This command prints the absolute path to the working tree root of the repository Git is currently using. Running it from a deeply nested directory inside the project still reports the corresponding root.

Other useful commands:

~~~bash
git rev-parse --show-prefix
git rev-parse --show-cdup
git rev-parse --git-dir
git rev-parse --git-common-dir
~~~

| Command | Meaning |
|---|---|
| <code>--show-toplevel</code> | Path to the working tree root |
| <code>--show-prefix</code> | Relative path from the root to the current directory |
| <code>--show-cdup</code> | Relative path needed to traverse up to the root |
| <code>--git-dir</code> | Path to the Git metadata currently in use |
| <code>--git-common-dir</code> | Path to the shared metadata, useful with worktrees and certain linked repository layouts |

If <code>--show-prefix</code> returns an empty string, the terminal is at that repository's root. If <code>--show-cdup</code> returns <code>../../</code>, you are two levels deep below the root.

Note: these commands describe whichever repository Git selected from the current location. They do not by themselves tell you whether that repository is a parent repository, a submodule, or a worktree. Combine them with the checks in the following sections.

## 4. Comparing roots of parent and child directories

When suspecting a nested repository, query Git for each specific path:

~~~bash
git -C . rev-parse --show-toplevel
git -C tools/converter rev-parse --show-toplevel
git -C tools/converter rev-parse --git-dir
git -C tools/converter rev-parse --git-common-dir
~~~

If the two <code>--show-toplevel</code> commands return different paths, the subdirectory belongs to a separate working tree.

You can check status further:

~~~bash
git status --short
git -C tools/converter status --short
git -C tools/converter remote -v
~~~

The parent and child repositories can have completely different branches, remotes, and uncommitted changes. Do not run commands that rewrite history or delete metadata until you know clearly which repository the terminal is operating on.

## 5. Detecting .git entries inside the working tree

A standard repository normally has a <code>.git</code> directory at the root. Inside the working tree, there may be additional directories or files named <code>.git</code> belonging to submodules, worktrees, or standalone repositories.

On Linux/macOS/Git Bash, you can list items named .git beneath the current directory:

~~~bash
find . -path './.git' -prune -o -mindepth 2 -name .git -print -prune
~~~

This command skips <code>./.git</code> at the root and stops descending once an item named <code>.git</code> is found. If the project is very large or contains generated directories, narrow the search scope to avoid scanning excessive data.

You can inspect a specific path:

~~~bash
ls -ld tools/converter/.git
file tools/converter/.git
~~~

The output indicates whether <code>.git</code> is a directory or a file on Unix-like systems. On Windows, use PowerShell:

~~~powershell
Get-Item -Force .\tools\converter\.git | Format-List FullName,Attributes,LinkType,Target
~~~

If <code>.git</code> is a file, read its contents to see which Git directory it points to. Do not delete this file before determining whether it belongs to a submodule, a worktree, or a separate git dir configuration.

## 6. Distinguishing standalone repositories, submodules, and linked worktrees

All three structures can appear as a subdirectory containing Git metadata, yet their meanings differ.

| Type | Typical metadata | Relationship with parent repository |
|---|---|---|
| Nested standalone repository | Usually has its own <code>.git</code> directory | No formal management link to the parent |
| Submodule | Usually has a <code>.git</code> file pointing to submodule metadata inside the parent repository | Parent repository records a gitlink and configuration in <code>.gitmodules</code> |
| Linked worktree | Has a <code>.git</code> file pointing to per-worktree metadata | Shares object database and common metadata with the main repository |

A <code>.git</code> entry being a directory does not prove it is a standalone repository in every single case. A <code>.git</code> file alone is also not enough to conclude it is a submodule. Use Git commands to verify the relationship.

### Checking for a submodule

Run inside the suspected directory:

~~~bash
git rev-parse --show-superproject-working-tree
~~~

If the command prints the parent repository's path, the current directory is inside a submodule of that superproject. If the output is empty, Git does not recognize it as a submodule of a superproject at the time of inspection.

From the parent repository, view the list:

~~~bash
git submodule status --recursive
~~~

### Checking for a worktree

From the main repository or a linked worktree belonging to the same repository:

~~~bash
git worktree list --porcelain
~~~

The listing shows the working trees linked to the shared repository. Compare paths to see whether the subdirectory is a worktree created via <code>git worktree add</code>.

### Checking for a standalone repository

If it is neither a submodule nor a worktree, inspect root and remotes:

~~~bash
git -C tools/converter rev-parse --show-toplevel
git -C tools/converter remote -v
git -C tools/converter branch --show-current
~~~

A standalone repository typically has its own remotes, branches, and history. However, a remote may not have been configured yet, so do not rely solely on <code>remote -v</code> output to draw conclusions.

## 7. How does Git see a nested repository in status?

Suppose <code>tools/converter</code> is a child repository newly cloned inside the parent repository but not yet added to the index. The parent repository might display:

~~~bash
git status --short
~~~

Illustrative output:

~~~text
?? tools/converter/
~~~

Git normally does not list every file inside the child repository as individual untracked files. The subdirectory acts as a repository boundary.

If you run:

~~~bash
git add tools/converter
~~~

Git may warn that you are adding an embedded Git repository. Instead of adding all the source code, Git usually stages a gitlink pointing to the child repository's current commit.

This behavior is easy to misunderstand: a successful <code>git add</code> command does not mean all child files were added to the parent repository.

## 8. What is gitlink mode 160000?

Git represents a submodule in the parent repository's tree using a special entry called a **gitlink**, with mode <code>160000</code>.

Example in the index:

~~~bash
git ls-files --stage -- tools/converter
~~~

Illustrative output:

~~~text
160000 7c4a... 0 tools/converter
~~~

Or after committing:

~~~bash
git ls-tree HEAD -- tools/converter
~~~

Output:

~~~text
160000 commit 7c4a...    tools/converter
~~~

Mode <code>160000</code> means the parent repository stores the OID of the commit the child repository currently points to. It does not store all the files inside the child repository as regular blobs.

This OID must correspond to a commit in the child repository. The parent repository does not contain the submodule's full history or object database. When cloning the superproject, Git needs the URL to download the child repository.

## 9. An embedded repository is not necessarily a properly configured submodule

If you only run <code>git add</code> on a child repository, Git can create a gitlink without standard submodule configuration.

A proper submodule normally has two components:

1. A gitlink with mode <code>160000</code> in the superproject's tree/index.
2. A <code>.gitmodules</code> file recording the path and URL so Git knows how to initialize the submodule.

Example .gitmodules:

~~~ini
[submodule "tools/converter"]
    path = tools/converter
    url = https://example.com/team/converter.git
~~~

This file is configuration committed in the parent repository. It does not contain the submodule's source code. The gitlink records the specific commit the superproject wants to use.

If <code>.gitmodules</code> is missing, anyone cloning the parent repository may see a gitlink without knowing the canonical URL to fetch the child content. Git warns when adding an embedded repository so you can decide whether you truly intend to use a submodule.

## 10. Submodules are intentional management boundaries

Submodules are suitable when a project needs to reference another repository as an independently managed dependency.

Example:

~~~text
game/
├── .git/
├── .gitmodules
├── src/
└── vendor/
    └── physics/
        └── .git
~~~

The parent repository manages:

- The submodule path.
- The URL to clone the submodule.
- The specific submodule commit used by that version of the project.

The child repository manages:

- Its own source code and history.
- Its own branches, tags, and remotes.
- The commit referenced by the superproject.

Submodules do not automatically track the latest branch tip. The superproject normally pins a specific commit, ensuring everyone clones the exact same version of the dependency.

## 11. Adding a submodule properly

Use the <code>git submodule add</code> command to register a child repository:

~~~bash
git submodule add https://example.com/team/converter.git tools/converter
~~~

This command clones the child repository into the target directory, updates the .gitmodules file, and stages the gitlink in the parent repository. If the path already exists and contains data or Git metadata, inspect its status first; do not delete or overwrite that directory just to make the command run.

Verify:

~~~bash
git status
git diff -- .gitmodules
git ls-files --stage -- tools/converter
~~~

Then commit the configuration and gitlink:

~~~bash
git add .gitmodules tools/converter
git commit -m "Add converter as a submodule"
~~~

When adding a submodule, verify the URL is accessible from teammates' machines and CI. If the child repository is private, anyone cloning the superproject also needs read access to the child repository.

Do not use plain <code>git add</code> as a substitute for <code>git submodule add</code> when your goal is creating a submodule with explicit shared configuration.

## 12. Cloning a repository with submodules

A standard clone retrieves the superproject without initializing submodule contents.

To clone and fetch all submodules from the start:

~~~bash
git clone --recurse-submodules https://example.com/team/game.git
~~~

If already cloned earlier:

~~~bash
git submodule update --init --recursive
~~~

Meaning:

- <code>--init</code>: initializes local configuration for submodules.
- <code>--recursive</code>: applies recursively to submodules nested inside submodules.
- <code>update</code>: checks out the commit recorded by the superproject in the gitlink.

If a submodule has not been initialized, its directory may appear empty or lack expected content. This does not necessarily mean the repository is broken; the submodule may simply not have been fetched and checked out yet.

## 13. Submodules usually check out in detached HEAD

When you run:

~~~bash
git submodule update --init --recursive
~~~

Git checks out the specific commit referenced by the superproject. Submodules are typically in a detached HEAD state because the superproject stores a commit OID, not a branch name.

Inspect:

~~~bash
git -C tools/converter status
git -C tools/converter log -1 --oneline
git -C tools/converter branch --show-current
~~~

If you want to develop inside the submodule, switch to the appropriate branch:

~~~bash
git -C tools/converter switch main
~~~

Then edit, commit, and push in the child repository following its own workflow. Once the child commit is on the remote, return to the superproject and stage the gitlink update:

~~~bash
git add tools/converter
git commit -m "Update converter submodule revision"
~~~

The superproject commit only updates which commit it references. It does not automatically push new commits inside the submodule.

## 14. Updating a submodule to the commit recorded by the superproject

To re-checkout the exact commit recorded in the superproject:

~~~bash
git submodule update --init --recursive
~~~

This is the appropriate approach when you want your working environment to match the dependency version pinned by the team.

If you want to update according to the remote branch configured for the submodule, you can use:

~~~bash
git submodule update --remote --recursive
~~~

The <code>--remote</code> option fetches the latest version according to the configured or default remote-tracking branch. After updating, the superproject may show the submodule at a different commit from the committed gitlink. You need to verify, stage the gitlink, and commit the change in the superproject if you want to share the new version.

Do not use <code>--remote</code> blindly in reproducible builds, because a remote branch can move over time. For builds requiring deterministic results, use the commit pinned in the superproject.

## 15. Checking submodule status

From the parent repository:

~~~bash
git submodule status --recursive
git status --short
~~~

The leading character on each line of <code>git submodule status</code> typically means:

| Symbol | Meaning |
|---|---|
| Space | Submodule is at the commit recorded by the superproject |
| <code>-</code> | Submodule has not been initialized |
| <code>+</code> | Submodule has a different commit checked out from the gitlink |
| <code>U</code> | Gitlink has a merge conflict |

Inspect changes inside the submodule:

~~~bash
git -C tools/converter status --short
~~~

The status of the superproject and the submodule are two separate layers. The superproject may report that the submodule has modified contents or a new commit, but to see which files were edited, run <code>git status</code> inside the submodule.

## 16. Distinguishing submodules from directly vendored source directories

Not every dependency requires a submodule.

| Management approach | What does the parent repository store? | Suitable when |
|---|---|---|
| Copy/vendor source | Regular files and directories | The project wants to manage the source as part of itself |
| Submodule | Gitlink to a commit and URL in <code>.gitmodules</code> | The dependency has an independent history and lifecycle |
| Linked worktree | Working tree linked to the same repository | Multiple simultaneous checkouts/branches are needed |
| Nested standalone repository | Subdirectory with its own Git metadata but not formally registered | Only suitable when intentionally managing independently and understanding the limits |

If copying source from another project into a monorepo, make sure unwanted Git metadata is removed. If you want to preserve the dependency's history, consider a submodule or a history integration method such as subtree. Do not leave a child repository lying around accidentally and expect the parent Git repository to manage every file.

## 17. A linked worktree is not a submodule

A linked worktree creates an additional working tree for the same repository, commonly used to work on multiple branches simultaneously.

Example:

~~~bash
git worktree add ../project-hotfix hotfix/login
git worktree list
~~~

The two working trees share the object database and common metadata, while each worktree has its own index and HEAD. A secondary worktree directory typically has a .git file pointing to metadata dedicated to that worktree.

Differences from a submodule:

- A worktree is another checkout of the same repository.
- A submodule is a different repository referenced by the superproject via a gitlink.
- A submodule has its own URL and commit recorded in .gitmodules/gitlink.
- Worktrees are managed with <code>git worktree list</code>, <code>add</code>, <code>remove</code>, and <code>prune</code>.

If a worktree is placed inside the working tree of another repository, the parent repository may see it as a nested repository. Do not delete the worktree's .git file to "merge" it into the parent repository; use the appropriate worktree commands.

## 18. Handling an accidental clone inside a parent repository

Suppose you accidentally ran:

~~~bash
git clone https://example.com/team/converter.git tools/converter
~~~

while <code>tools</code> belongs to the parent repository.

Before fixing it, determine your intent:

- Should the converter directory be regular source code in the parent repository?
- Should it be an intentional submodule?
- Should it be a standalone repository ignored by the parent repository?
- Or was it cloned into the wrong location and should be moved outside the working tree?

If unsure, stop and inspect commits, remotes, and local changes in the child repository. Never delete metadata merely to make a Git warning disappear.

### Case A — The child repository belongs outside the parent repository

Move the subdirectory to a sibling location outside the parent repository's root. Check the destination path before moving and ensure you do not overwrite an existing directory.

Then verify:

~~~bash
git status --short
git -C ../converter rev-parse --show-toplevel
~~~

The parent repository will no longer see that directory in its working tree.

### Case B — The child repository is an independent dependency not tracked by the parent

If the directory needs to stay in place without belonging to the parent project, add its path to the parent repository's .gitignore:

~~~gitignore
/tools/converter/
~~~

Verify the rule:

~~~bash
git check-ignore -v tools/converter/
~~~

If the path was already staged as a gitlink or tracked in the index, .gitignore will not automatically remove it from the index. Check <code>git ls-files --stage -- tools/converter</code> and handle the staged entry appropriately before committing.

### Case C — Converting the directory into a formal submodule

Identify the canonical URL, commit to pin, and access permissions. Use <code>git submodule add</code> to create the .gitmodules configuration and gitlink. If the current directory already contains a repository, verify whether Git can reuse the existing repository or whether it should be moved/re-cloned into a clean path.

Then verify:

~~~bash
git diff -- .gitmodules
git ls-files --stage -- tools/converter
git submodule status
~~~

Only commit once the URL and referenced commit are correct.

## 19. Handling an accidental git init inside a subdirectory

Suppose you are in <code>project/tools/converter</code> and run:

~~~bash
git init
~~~

This creates Git metadata inside the subdirectory. From that point on, Git commands executed there will use the new repository.

First, verify the root:

~~~bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git status
~~~

If this is a newly created mistake with no history or changes to preserve, still inspect carefully before discarding metadata. If commits were already made or uncommitted changes exist, preserve them.

### Preserving child repository history

If you need to keep commits already created, you can create a bundle from the child repository:

~~~bash
git bundle create /safe/location/converter-backup.bundle --all
~~~

A bundle stores objects reachable from the included refs. It does not contain uncommitted changes or untracked files. Back up the working tree and uncommitted files separately as appropriate.

If the child repository has remotes, check:

~~~bash
git remote -v
git branch -avv
git log --all --oneline --decorate
~~~

Do not delete .git until you have determined which history needs to be preserved and confirmed the backup is readable.

### Converting files into regular content of the parent repository

If you decide the subdirectory is simply regular source code of the parent, remove the child repository boundary after backing up and confirming the metadata type.

- If .git is a separate metadata directory, you can move the metadata directory to a backup location outside the working tree and then stage the source files via the parent repository.
- If .git is a file, do not delete it following directory instructions; it may point to a submodule, worktree, or separate git dir.
- If this is a formal submodule, use the proper submodule removal procedure; do not treat it like an anonymous nested repository.
- If the child history must be preserved inside the parent's history, plan a dedicated history integration, such as subtree or rewriting history into a subdirectory. Simply copying files and removing metadata will not transfer older commits into the parent repository.

Once you have confirmed the directory is regular source code, check the parent root and stage the files:

~~~bash
git -C /path/to/project status --short
git -C /path/to/project add tools/converter
~~~

Replace the example path with the actual root. Inspect the index to ensure Git added regular files rather than a gitlink:

~~~bash
git -C /path/to/project ls-files --stage -- tools/converter
~~~

Regular files have modes such as <code>100644</code> or <code>100755</code>; if you still see <code>160000</code>, the index is storing a gitlink.

## 20. If the parent repository already tracked files before the child repository appeared

A confusing scenario occurs when a subdirectory already had source files tracked by the parent repository, and someone later ran <code>git init</code> or cloned another repository inside it.

In this situation, the parent's Git index may still contain the previously tracked files. The presence of .git metadata does not automatically convert the entire directory into a gitlink.

Check:

~~~bash
git ls-files --stage -- tools/converter
git status --short
git -C tools/converter status --short
~~~

If multiple files with regular modes appear in the index, the parent repository is still managing those files. If mode <code>160000</code> appears, Git is storing a gitlink. Transitional states or unstaged files may exist; proceed according to the actual output.

Do not mechanically run <code>git rm -r</code>, <code>git clean</code>, or delete metadata. Those commands can remove files or alter the index more broadly than intended. Back up, determine tracked/untracked status, and perform a controlled transition.

## 21. Removing a submodule properly

If a submodule is no longer needed, unlink it from the superproject in verified steps.

First, confirm the path and status:

~~~bash
git submodule status
git status --short
git -C tools/converter status --short
~~~

After preserving any changes you need to keep, remove the gitlink from the index and .gitmodules configuration following the workflow for your Git version. For example, for a verified submodule:

~~~bash
git rm tools/converter
~~~

This command stages removing the submodule from the superproject and updates .gitmodules where applicable. Inspect the diff before committing:

~~~bash
git diff --cached -- .gitmodules
git diff --cached --summary
~~~

Submodule metadata may remain in .git/modules/ for recovery or cleanup purposes. Only clean up remaining metadata once you are certain the child repository does not need to be kept and you understand the path. Never manually delete another submodule's .git/modules directory.

If you want to keep the source code as regular files instead of deleting the contents, back up/copy the source to a safe location first, remove the gitlink, and then add the source into the parent repository's index as a separate planned step.

## 22. Quick diagnostic commands

| Goal | Command |
|---|---|
| Find the current root | <code>git rev-parse --show-toplevel</code> |
| Find the Git directory | <code>git rev-parse --git-dir</code> |
| Find the Git common directory | <code>git rev-parse --git-common-dir</code> |
| Check a submodule's superproject | <code>git rev-parse --show-superproject-working-tree</code> |
| List submodules | <code>git submodule status --recursive</code> |
| List linked worktrees | <code>git worktree list --porcelain</code> |
| Check mode in the index | <code>git ls-files --stage -- &lt;path&gt;</code> |
| Check committed gitlink | <code>git ls-tree HEAD -- &lt;path&gt;</code> |
| Check child repository remotes | <code>git -C &lt;path&gt; remote -v</code> |
| Check child repository status | <code>git -C &lt;path&gt; status --short</code> |

Run commands from the proper repository root or use <code>git -C</code> to specify the path explicitly. This reduces the risk of accidentally operating on a child repository when you intend to modify the parent repository.

## 23. Common mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| <code>git status</code> in parent shows only a single untracked directory | Subdirectory has its own repository | Check the subdirectory's root and determine whether it is a submodule |
| <code>git add</code> warns about an embedded Git repository | Adding a child repository without registering a submodule | Choose to convert to regular files, ignore, move outside, or create a formal submodule |
| Parent clone leaves subdirectory empty | Gitlink has not been initialized or submodule URL is missing | Check .gitmodules and run <code>git submodule update --init --recursive</code> |
| Superproject reports submodule has new commits | Submodule HEAD differs from committed gitlink | Verify child commit, stage gitlink, and commit change in parent if intentional |
| Git command operates on the wrong repository | Terminal is inside a child repository | Check <code>git rev-parse --show-toplevel</code> or use <code>git -C</code> |
| Cannot delete .git like a directory | .git is a file pointing to external metadata | Read the file and check submodule/worktree/separate git dir before acting |
| .gitignore does not remove a staged entry | Path is already in the index | Check <code>git ls-files</code> and remove from index intentionally |
| Removed submodule, yet metadata remains | Submodule metadata is stored separately in .git/modules | Inspect and clean up according to procedure, avoiding deleting other submodules |

## 24. Decision workflow when a nested repository is detected

You can use the following sequence before making edits:

~~~text
Detect subdirectory containing .git
             |
             v
Compare roots with git rev-parse
             |
             v
Is it a submodule?
       /             \
     Yes              No
     |                 |
Check .gitmodules     In git worktree list?
and gitlink mode      /              \
                   Yes                No
                   |                  |
              Linked worktree    Nested standalone repo
                   |                  |
             Use git worktree    Clarify intent:
             to manage           move / ignore / convert
                                     / submodule
~~~

After identifying the repository type, preserve any changes and history you need to keep before moving or removing metadata.

## 25. Checklist before fixing a nested repository

- [ ] Identified the roots of both the parent and child repositories.
- [ ] Checked whether .git is a directory or a file.
- [ ] Checked submodule status using <code>--show-superproject-working-tree</code>.
- [ ] Checked linked worktree status using <code>git worktree list</code>.
- [ ] Inspected .gitmodules and gitlink mode <code>160000</code>.
- [ ] Determined whether the child repository has commits or local changes to keep.
- [ ] Backed up refs and working tree if needed.
- [ ] Decided whether to move, ignore, convert to regular files, or register as a submodule.
- [ ] Verified the index after handling.
- [ ] Tested cloning or reinitializing a copy to confirm teammates receive the intended layout.

## 26. Key points to remember

- Git selects the nearest repository when searching upward for metadata from the current directory.
- <code>git rev-parse --show-toplevel</code> identifies the root that the current command is using.
- Nested repositories have their own history and index; the parent Git repository does not automatically manage all files inside.
- When adding an embedded repository, Git may stage gitlink mode <code>160000</code> rather than the full source tree.
- A formal submodule combines a gitlink in the tree with URL/path configuration in .gitmodules.
- Submodules pin a specific commit; clones require <code>--recurse-submodules</code> or <code>git submodule update --init --recursive</code>.
- Linked worktrees share the common repository and are managed with <code>git worktree</code>.
- .git can be a directory or a file pointing to metadata elsewhere; never delete it before identifying its type.
- If converting a child repository into regular files, preserve history and local changes before removing the boundary.
- Always inspect root, index mode, .gitmodules, submodule status, and worktree list before making changes.

Properly identifying repository boundaries prevents accidentally committing gitlinks, omitting source code, or losing child project history. When a child repository is intentional, register and update it as a submodule or worktree using the right mechanism; when it appears unintentionally, verify its state and preserve data before converting it.
