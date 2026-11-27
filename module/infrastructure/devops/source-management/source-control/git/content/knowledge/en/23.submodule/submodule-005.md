# Initializing and Updating with git submodule update --init --recursive

## What Is a Submodule and Why Must It Be Initialized?

Git submodules allow a repository to manage another Git repository as a component inside its directory tree. The repository containing the submodule is called the **superproject**. Submodules have their own history, commits, and remotes; the superproject stores the specific commit ID that each submodule must use.

For example, an application has the following structure:

~~~text
inventory-app/
├── src/
├── config/
├── libs/
│   ├── ui-kit/       # submodule
│   └── data-client/  # submodule
├── .gitmodules
└── README.md
~~~

When cloning the superproject, Git retrieves the source code and history of the main repository. The contents of the submodules may not yet be downloaded and checked out. Submodule directories may appear without containing an initialized working tree.

To initialize and check out the submodules at the exact commits required by the superproject, use:

~~~bash
git submodule update --init --recursive
~~~

This is the command typically needed after cloning a repository with submodules or after switching to a commit where a gitlink changed.

What the options mean:

- **update:** synchronizes the submodule working tree with the commit recorded in the superproject.
- **--init:** initializes configuration for submodules not yet registered in the local configuration.
- **--recursive:** continues initializing and updating submodules nested inside other submodules.

This command brings submodules to the pinned commit recorded by the superproject. By default, it does not fetch the latest commit on each submodule's remote branch.

## How Does the Superproject Record Submodules?

The superproject does not store all file contents of a submodule inside its own commits. Instead, it stores a **gitlink**: the submodule's path together with the commit ID that the superproject wants to use.

The .gitmodules file is committed in the superproject and contains information such as the submodule name, path, and URL:

~~~ini
[submodule "ui-kit"]
    path = libs/ui-kit
    url = https://example.com/team/ui-kit.git

[submodule "data-client"]
    path = libs/data-client
    url = https://example.com/team/data-client.git
~~~

In the example:

- ui-kit and data-client are the submodule names.
- path is the checkout location in the superproject.
- url is the repository address of the submodule.

The submodule name is a configuration name; it often matches the path, though it is not required to match. The superproject stores the gitlink corresponding to the path, while .gitmodules provides the information Git needs to know which repository to fetch.

You can inspect gitlinks in the current commit:

~~~bash
git ls-tree HEAD
git ls-tree HEAD libs/ui-kit
~~~

A gitlink typically has mode 160000, for example:

~~~text
160000 commit 8a7b6c5d...    libs/ui-kit
~~~

The commit ID after it is the commit the superproject requires the submodule to check out. This is why two people cloning the same superproject commit will use the same submodule version, provided that commit is reachable in the submodule repository.

You can check the gitlink state in the index:

~~~bash
git ls-files --stage -- libs/ui-kit
~~~

If a submodule is updated to a different commit, the superproject will see the submodule path change as a gitlink modification. To share the new version, you must commit in the submodule repository, then stage the submodule path in the superproject and commit the gitlink change.

## Differences Between .gitmodules and Local Configuration

The two configuration locations serve different roles:

| Storage Location | Role |
|---|---|
| .gitmodules | Metadata version-controlled and shared with the superproject, typically including path and URL |
| Superproject's .git/config | Local configuration of submodules already initialized in the current clone |
| Configuration inside the submodule repository | Settings specific to the child repository, such as remotes and commit identity |

When running git submodule init, Git reads the URL information from .gitmodules and writes the corresponding configuration into the superproject's .git/config. The init command does not itself clone and check out submodule contents.

If local configuration already exists, init does not overwrite existing URL customizations. When a URL in .gitmodules changes and you need to resynchronize local configuration, use git submodule sync.

Read the .gitmodules file:

~~~bash
git config --file .gitmodules --list
~~~

View local submodule configuration:

~~~bash
git config --local --get-regexp '^submodule\.'
~~~

A repository may contain a relative URL, for example:

~~~ini
[submodule "ui-kit"]
    path = libs/ui-kit
    url = ../ui-kit.git
~~~

Git resolves relative URLs against the superproject's remote URL. This is useful when multiple repositories belong to the same organization or server. If you clone the superproject from a mirror or a source with a different layout, verify that the resolved URL points to the correct submodule repository.

## Workflow for Initializing Submodules After Cloning

### Step 1: Clone the Superproject

Clone the main repository as usual:

~~~bash
git clone https://example.com/team/inventory-app.git
cd inventory-app
~~~

At this point, the submodule directories may not be initialized yet. Check:

~~~bash
git submodule status
~~~

Example:

~~~text
-8a7b6c5d... libs/ui-kit
-1f2e3d4c... libs/data-client
~~~

The leading - indicates the submodule has not been initialized. The commit ID next to it is the commit required by the superproject.

### Step 2: Initialize and Update All Submodules

Run:

~~~bash
git submodule update --init --recursive
~~~

Git will:

1. Read submodule declarations from .gitmodules.
2. Initialize local configuration for unregistered submodules.
3. Clone the submodule repository if the needed clone does not yet exist.
4. Fetch necessary data from the submodule remote.
5. Check out the commit recorded in the superproject's gitlink.
6. Continue performing the corresponding steps for nested submodules.

If the repository has many submodules, this process may take time and require access to multiple remotes.

### Step 3: Verify the Status

After the command finishes:

~~~bash
git submodule status --recursive
git status
~~~

Example output:

~~~text
 8a7b6c5d... libs/ui-kit (v2.4.0-3-g8a7b6c5)
 1f2e3d4c... libs/data-client
~~~

The absence of -, +, or U at the beginning of a line generally indicates that the submodule is initialized and at the commit recorded by the superproject. The text in parentheses may describe a branch, tag, or commit distance, depending on repository state.

If a submodule is in detached HEAD, that is usually the normal state when Git checks out a commit pinned by the superproject. This helps guarantee every team member uses the exact dependency version.

## Initializing Submodules Right During Cloning

If you want to clone the superproject and download all submodules from the start, you can use:

~~~bash
git clone --recurse-submodules https://example.com/team/inventory-app.git
~~~

The --recurse-submodules option instructs Git to initialize and update submodules during the clone operation. For repositories with nested submodules, this operation also handles recursion.

The command above is generally equivalent to the sequence:

~~~bash
git clone https://example.com/team/inventory-app.git
cd inventory-app
git submodule update --init --recursive
~~~

If you already cloned without --recurse-submodules, there is no need to re-clone. Simply run git submodule update --init --recursive from the superproject root directory.

## Updating Submodules After Switching Branches or Pulling

A new commit in the superproject can change a submodule's gitlink. For example, the main branch may be updated to use a new version of libs/ui-kit.

After fetching the new superproject commits:

~~~bash
git switch main
git pull --ff-only
~~~

Check the submodule status:

~~~bash
git submodule status --recursive
~~~

If a submodule is not yet at the commit required by the superproject, update:

~~~bash
git submodule update --init --recursive
~~~

This command brings each submodule to the commit recorded in the current superproject commit. It can clone newly added submodules, check out new commits for existing submodules, and initialize nested submodules.

**Fetching or pulling the superproject does not guarantee that every submodule is initialized and checked out recursively.** Certain configurations or recurse options may instruct Git to fetch submodules during a pull; to explicitly initialize and check out according to the superproject commit's gitlink, run submodule update --init --recursive.

### When the Superproject Changes the Submodule Version

Suppose the superproject previously pinned libs/ui-kit at commit A. A new commit on main changes the gitlink to commit B.

~~~text
Superproject before:
main -> commit P1 -> libs/ui-kit @ A

Superproject after:
main -> commit P2 -> libs/ui-kit @ B
~~~

After updating the superproject to P2, run:

~~~bash
git submodule update --init --recursive
~~~

Git checks out libs/ui-kit at B. If the submodule currently has local changes that could be overwritten, Git may refuse the update. Inspect and preserve those changes before continuing.

### Updating a Specific Submodule

If you only need to initialize or update one path:

~~~bash
git submodule update --init --recursive -- libs/ui-kit
~~~

This is useful in large repositories when you only need to work with a subset of dependencies. However, if the selected submodule has nested submodules, the --recursive option still requires updating its child levels.

## How Do --init and --recursive Work Together?

The following three invocations have different scopes:

~~~bash
# Update only already-initialized submodules
git submodule update

# Initialize and update submodules at the current level
git submodule update --init

# Initialize and update nested submodules as well
git submodule update --init --recursive
~~~

| Option | Effect |
|---|---|
| Without --init | Updates submodules that are already initialized |
| --init | Registers configuration for uninitialized submodules, then updates |
| --recursive | Continues processing submodules nested inside |
| --init --recursive | Initializes and updates the entire submodule tree to the commits required by the superproject |

If a project has nested submodules and you omit --recursive, deeper child repositories may remain uninitialized. Therefore, when preparing a development or CI environment, using --init --recursive generally ensures the full dependency tree is checked out.

## Understanding Which Commit Is Updated: Pinned Commit vs. Remote Branch

A common misconception is assuming that:

~~~bash
git submodule update --init --recursive
~~~

will fetch the latest commit of the main branch in each submodule. In reality, the default command checks out the commit recorded in the superproject's gitlink.

For example, .gitmodules declares the URL of libs/ui-kit, while the gitlink in the superproject commit points to commit 8a7b6c5. Even if the submodule's remote already has newer commits, the default update command still checks out 8a7b6c5.

This approach makes builds reproducible: the superproject commit determines the exact version of each submodule.

If the goal is to update a submodule to the latest commit on a remote branch, that is a separate workflow, usually using --remote:

~~~bash
git submodule update --remote --recursive
~~~

The --remote option fetches the latest state from the submodule's configured remote-tracking branch instead of simply checking out the current gitlink. The branch can be specified with the submodule.<name>.branch key in .gitmodules or local config; if unspecified, Git uses the remote HEAD branch. As a result, the gitlink in the superproject may change; that change must be reviewed and committed as an intentional dependency update.

Do not use --remote in place of the standard init/update command when you need to reproduce the exact version pinned by a superproject commit.

## Updating the Submodule URL When the Repository Address Changes

If a team moves a submodule repository to a new URL, a maintainer updates .gitmodules and commits the change in the superproject.

Example URL change:

~~~ini
[submodule "ui-kit"]
    path = libs/ui-kit
    url = https://git.example.com/platform/ui-kit.git
~~~

On an existing clone, local configuration may still hold the old URL. Synchronize the URL from .gitmodules:

~~~bash
git submodule sync --recursive
~~~

Then initialize or update:

~~~bash
git submodule update --init --recursive
~~~

Inspect the submodule's URL:

~~~bash
git -C libs/ui-kit remote -v
~~~

sync updates the URL registered in local configuration according to the declaration in .gitmodules; it does not modify the URL in .gitmodules itself and does not commit changes for the superproject.

If the new URL requires different access permissions, verify your SSH key, credential helper, or read access to the submodule repository. Do not embed tokens or passwords in committed URLs.

## Checking Submodule Status with git submodule status

The command:

~~~bash
git submodule status --recursive
~~~

displays the current commit of each submodule and a status indicator at the beginning of each line.

| Leading Character | Meaning |
|---|---|
| Space | Submodule is initialized and at the commit recorded by the superproject |
| - | Submodule has not been initialized |
| + | Submodule is checked out at a commit different from the superproject's gitlink |
| U | Gitlink has an unresolved conflict |

Example:

~~~text
-8a7b6c5... libs/ui-kit
+1f2e3d4... libs/data-client
U3a4b5c6... libs/legacy-client
~~~

How to read it:

- libs/ui-kit has not been initialized.
- libs/data-client has a working tree, but it is at a different commit than required by the superproject.
- libs/legacy-client has a gitlink conflict that needs resolution.

After running update and resolving any necessary conflicts, run status again to verify.

You can check the status inside individual submodules:

~~~bash
git -C libs/ui-kit status
git -C libs/data-client log -1 --oneline --decorate
~~~

Or iterate across initialized submodules:

~~~bash
git submodule foreach --recursive 'git status --short'
~~~

The foreach command runs a command inside each submodule. The --recursive option continues into nested submodules.

## Detached HEAD in a Submodule Is Normal

After git submodule update, a submodule is usually in detached HEAD because Git directly checks out the commit recorded in the gitlink. For example:

~~~bash
git -C libs/ui-kit status
~~~

May output:

~~~text
HEAD detached at 8a7b6c5
nothing to commit, working tree clean
~~~

This does not mean the submodule is broken or missing its branches. The superproject is requesting a specific commit rather than a development branch.

If you need to develop inside the submodule, switch to an appropriate branch in the child repository:

~~~bash
git -C libs/ui-kit switch -c feature/button-accessibility
~~~

After committing and pushing changes in the submodule, return to the superproject and stage the submodule path to update the gitlink:

~~~bash
git add libs/ui-kit
git commit -m "Update ui-kit submodule"
~~~

Before sharing the superproject commit, ensure the new submodule commit has been pushed to a remote accessible by other team members. If the superproject pins an unshared commit, others will be unable to fetch the submodule when cloning or updating.

## Common Errors During Initialization and Updating

### Submodule Not Initialized

A - in git submodule status indicates the submodule has not been initialized.

Run:

~~~bash
git submodule update --init --recursive
~~~

If you only need one path:

~~~bash
git submodule update --init --recursive -- libs/ui-kit
~~~

### Cannot Access Submodule Repository

The error may be caused by an incorrect URL, a moved repository, missing permissions, or unconfigured credentials.

Check:

~~~bash
git config --file .gitmodules --list
git submodule sync --recursive
git -C libs/ui-kit remote -v
~~~

After confirming the URL is correct, try updating again:

~~~bash
git submodule update --init --recursive
~~~

If using SSH, verify keys and access permissions. If using HTTPS, check your credential manager or authentication mechanism supported by your organization. Do not place credentials in .gitmodules.

### URL Changed, but the Clone Still Uses the Old Address

The .gitmodules file may be updated while .git/config on the machine still holds the old URL. Synchronize:

~~~bash
git submodule sync --recursive
git submodule update --init --recursive
~~~

Then verify with git -C <path> remote -v.

### Submodule Is on the Wrong Commit

If status shows +, the submodule is checked out at a commit different from the gitlink. To return to the commit required by the superproject:

~~~bash
git submodule update --init --recursive
~~~

If the command refuses because of local changes, inspect inside the submodule first:

~~~bash
git -C libs/ui-kit status
git -C libs/ui-kit diff
git -C libs/ui-kit diff --cached
~~~

Commit, stash, or back up changes you need to keep according to your team's workflow. Only after preserving data should you update the submodule. Do not use force options to overwrite uninspected changes.

### Nested Submodules Are Still Not Downloaded

If an outer submodule is checked out but contains uninitialized subdirectories inside, check:

~~~bash
git submodule status --recursive
~~~

Then run:

~~~bash
git submodule update --init --recursive
~~~

Ensure the URLs and access permissions at every submodule level are valid.

### Git Reports Local Files Would Be Overwritten

The submodule may have tracked modifications or untracked files at paths colliding with the checkout contents.

Inspect:

~~~bash
git -C libs/ui-kit status --short
git -C libs/ui-kit diff
git -C libs/ui-kit ls-files --others --exclude-standard
~~~

Move or save files you need to keep, commit/stash appropriate changes, and run update again. Do not delete the submodule directory manually before determining whether local data needs to be preserved.

### Superproject Reports a Gitlink Conflict

When two branches change the commit referenced by the same submodule, the superproject can report a conflict at the gitlink path.

Check:

~~~bash
git status
git ls-files -u -- libs/ui-kit
~~~

Inspect the commits held by the index at each stage if present:

~~~bash
git ls-files --stage -- libs/ui-kit
~~~

Determine the submodule version to use based on the merge goal, ensure that commit is reachable, and check out that exact commit inside the submodule. Re-stage the path in the superproject:

~~~bash
git add libs/ui-kit
git status
~~~

Once no conflicts remain, complete the merge according to the repository's workflow. git submodule update --init --recursive does not decide for the team which side's gitlink to choose when a conflict occurs.

## Sample Workflow for New Team Members

A new team member clones the project and needs to prepare all submodules:

~~~bash
# Clone the superproject
git clone https://example.com/team/inventory-app.git
cd inventory-app

# Initialize and update all submodules, including nested submodules
git submodule update --init --recursive

# Check the commit and status of each submodule
git submodule status --recursive

# Confirm the main repository status
git status
~~~

If the project recommends a one-step clone:

~~~bash
git clone --recurse-submodules https://example.com/team/inventory-app.git
cd inventory-app
git submodule status --recursive
~~~

After switching to another branch or pulling new commits:

~~~bash
git switch feature/report
git pull --ff-only
git submodule update --init --recursive
git submodule status --recursive
~~~

Use the branch and pull method defined by your team's conventions. The goal is to ensure submodules are checked out according to the gitlinks of the active superproject commit.

## Sample Workflow in CI

CI normally clones a repository from scratch, so it needs to initialize submodules explicitly. A checkout step might run:

~~~bash
git clone <repository-url> project
cd project
git submodule update --init --recursive
~~~

Or configure the CI platform's action/checkout task to enable the recursive submodule option. Specific configuration depends on the CI system.

In a pipeline, verify:

- The superproject commit matches the revision the pipeline is building.
- All required submodules are initialized.
- Submodules are at the commits required by the gitlinks.
- Nested submodules have been updated.
- The runner has read permissions for all submodule repositories.
- Referenced submodule commits exist on the remote.

Do not run --remote updates arbitrarily in CI if the goal is a reproducible build from a superproject commit. Standard CI should use the exact gitlink commits that were reviewed and committed.

## Checklist After Running update --init --recursive

- [ ] Running the command from the root directory of the superproject.
- [ ] .gitmodules declares the right paths and URLs.
- [ ] Local configuration has been initialized or synchronized if URLs changed.
- [ ] The git submodule update --init --recursive command completed successfully.
- [ ] git submodule status --recursive shows no unexpected -, +, or U prefixes.
- [ ] Each submodule is at the commit required by the gitlink.
- [ ] Nested submodules have been initialized.
- [ ] No local changes or untracked files were overwritten.
- [ ] Submodule commits are reachable from the team's remotes.
- [ ] The superproject build/tests run with the checked-out dependencies.

## Key Takeaways

The superproject stores the path and specific commit of each submodule as a gitlink; .gitmodules provides URLs and metadata so Git can initialize child repositories. After cloning, switching branches, or updating the superproject, use git submodule update --init --recursive to initialize missing submodules, check out pinned commits, and handle nested submodules. The default command does not fetch the latest version of a remote branch. Always check git submodule status --recursive, preserve local changes, and confirm all submodule commits are reachable before building or sharing changes.
