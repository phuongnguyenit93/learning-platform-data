# Distinguishing Submodules, Subtrees, and Regular Source Directories

When a project needs to use source code developed in another repository, you can integrate that code in several ways. Git submodules keep the external repository independent and have the parent repository record a specific commit. Git subtrees place the external repository's contents into a directory inside the parent repository and can synchronize changes with upstream. A regular source directory consists simply of files managed directly by the current repository.

All three choices can produce directory structures that look quite similar, yet they differ in how history is stored, how projects are cloned, how versions are updated, and how teams collaborate. Choosing the right model clarifies who maintains the source code, how updates are received, and what happens when someone clones the project fresh.

## 1. The Three Models from a Repository Perspective

Suppose the `storefront` application needs to use the `payment-core` library.

### Submodule: Separate Repository, Superproject Pins a Commit

```text
storefront/                  # superproject
|-- src/
|-- .gitmodules
|-- .git/
`-- libs/payment-core/       # working tree of the child repository
```

The `libs/payment-core` directory is a separate Git repository. The superproject stores a mode `160000` gitlink pointing to a commit SHA of the submodule. The `.gitmodules` file publishes the path and URL so other clones know how to fetch the child repository. The library's history, branches, and remotes are managed inside the submodule repository.

### Subtree: External Repository Contents Live in Parent Repository History

```text
storefront/                  # a single Git repository
|-- src/
|-- vendor/payment-core/     # files stored in the parent repository
`-- .git/
```

With subtree integration, the files of `payment-core` reside directly in the tree of `storefront` under the prefix `vendor/payment-core`. You can use the `git subtree` tool to import history and synchronize with the source repository. Cloning the superproject fetches this directory's contents directly; there is no need to initialize a separate child repository.

### Regular Directory: Source Code Belongs Entirely to the Current Repository

```text
storefront/
|-- src/
|-- libs/payment-utils/      # ordinary files of storefront
`-- .git/
```

Files in `libs/payment-utils` are staged and committed like any other file in `storefront`. There is no gitlink, no child repository, and no automatic upstream mechanism. If the code was originally copied from another project, the team manually manages pulling subsequent updates.

## 2. Comparing How Git Stores Data

| Criterion | Submodule | Subtree | Regular Directory |
|---|---|---|---|
| Contents in parent repository | Gitlink pointing to child commit | Files and trees of external code | Regular files and trees |
| Independent repository | Yes | Source repository may still exist separately, though the integrated copy lives inside the parent repository | No |
| External code history | Lives in the submodule repository | Can import upstream history or use squashed imports | History is created and managed in the parent repository |
| Version pinning | Commit SHA of the submodule | Commit/tree in superproject history | Commit of the superproject |
| Cloning the project | Requires initializing/fetching submodules | Cloning the superproject fetches subtree contents directly | Cloning the superproject fetches files directly |
| Upstream synchronization | Fetch and check out submodule commit | Use `git subtree pull`/`push` or equivalent workflow | Manually obtain and integrate source code |
| Dedicated configuration | `.gitmodules` and local configuration | Usually no `.gitmodules` needed; subtree tool uses prefix and remote/ref | No integration configuration needed |
| Best suited for | Components with independent lifecycle and governance | Vendoring while still exchanging changes with upstream | Code belonging to the same project, review, and release cycle |

The most important distinction: submodules have the parent repository reference another repository; subtrees import external code contents into the parent repository's history; regular directories are purely internal file structure with no Git-managed upstream sync relationship.

## 3. When Should You Choose a Submodule?

Submodules fit well when the external component has an independent lifecycle from the main project:

- A library is used by multiple repositories and maintained by its own team.
- The project needs to pin an exact commit of the library without copying its entire history into the parent repository.
- The team wants releases, reviews, access permissions, and issue tracking for the library in its own repository.
- Multiple applications consume different versions of the same component.

Example adding a submodule:

```bash
git submodule add https://git.example.com/platform/payment-core.git libs/payment-core
git status
git diff --cached
git commit -m "Add payment-core submodule"
```

Git creates or updates `.gitmodules` and adds the gitlink to the index. After committing, the superproject records the commit SHA currently checked out in the submodule.

Cloning the project and initializing submodules:

```bash
git clone --recurse-submodules https://git.example.com/platform/storefront.git
```

If already cloned earlier:

```bash
git submodule update --init --recursive
```

To update the submodule to the commit pinned by the superproject, run:

```bash
git submodule update --init --recursive
```

This command checks out the commit recorded in the gitlink, usually in detached `HEAD`. When you want to advance to a new commit, work inside the child repository, push that commit to the submodule remote, then stage the gitlink and commit the superproject. The team must ensure the child commit is reachable before sharing the new gitlink.

Drawbacks to consider are that clone workflows and CI must handle submodules, users need access permissions for both the parent and child repositories, and a gitlink pointing to an unpushed commit will prevent other clones from fetching the required version.

## 4. When Should You Choose a Subtree?

Subtrees fit well when you want external code to appear directly in the main repository so cloning, building, and developing happen in a single working tree, while still retaining the ability to sync with the source repository.

Common scenarios:

- Vendoring a library or tool into an application repository.
- CI environments need the complete source code via a single superproject clone.
- Team members prefer not to run extra submodule init/update steps.
- The team wants to receive upstream updates in batches and review them as changes in the main repository.
- You may occasionally need to send modifications back to the source repository.

`git subtree` is a helper script supporting subtree operations; it is commonly distributed with Git source code under the `contrib` directory, though not every Git build installs it by default. Check `git subtree -h`; if the command is unavailable on your machine, install the script according to your environment's instructions before using it.

### Adding a Subtree for the First Time

Example importing the `main` branch from `payment-core` into `vendor/payment-core`:

```bash
git subtree add --prefix=vendor/payment-core https://git.example.com/platform/payment-core.git main --squash
```

- `--prefix=vendor/payment-core`: directory in the superproject that will hold the external code.
- URL: source repository of the subtree.
- `main`: source branch to import.
- `--squash`: collapses the imported history into a single combined commit instead of adding the full upstream commit chain into superproject history.

Without `--squash`, `git subtree add` imports the source repository's commit history and creates a merge commit connecting the two histories. Choose between squashing or keeping full history based on traceability requirements and repository policy.

### Updating a Subtree from Upstream

When the source repository has new changes:

```bash
git subtree pull --prefix=vendor/payment-core https://git.example.com/platform/payment-core.git main --squash
```

This command fetches and integrates changes from the source branch into the prefix directory. If conflicts occur, resolve them as superproject conflicts, inspect the contents in `vendor/payment-core`, and complete the merge as prompted by Git.

### Sending Changes from a Subtree Back to Upstream

If the team edits the library in `vendor/payment-core` and wants to send changes back to the source repository:

```bash
git subtree push --prefix=vendor/payment-core https://git.example.com/platform/payment-core.git main
```

`git subtree push` extracts history split from the prefix and pushes it to the source branch as supported by the subtree tool. Your account needs push permission to the source repository. If the project only wants one-way vendoring, the team can use `add` and `pull` without `push`.

With a subtree, the library's contents already live inside the superproject's commits. Thus, when cloning the application, those files are immediately present without fetching a separate external repository. In return, superproject history can grow longer if full upstream history is imported; choosing `--squash` keeps history compact at the cost of less upstream commit granularity in the parent repository.

## 5. When Is a Regular Source Directory Enough?

Not every subdirectory needs a submodule or subtree. If the source code belongs to the same product, the same owning team, and the same release cycle, manage it as a normal part of the repository.

For example:

```bash
mkdir -p libs/payment-utils
# Add source files into libs/payment-utils
git add libs/payment-utils
git diff --cached
git commit -m "Add payment utility module"
```

Files are committed directly alongside the application. Branches, tags, reviews, permissions, and releases all follow the parent repository. This is straightforward for developers and CI; no additional remotes or component-syncing tools are required.

If the directory contains code copied from upstream, Git has no knowledge of its origin or how to update it. When a new version is needed, the team must manually download, diff, cherry-pick, copy, or apply patches according to an agreed process. If synchronization becomes frequent or the component has a separate owner, reconsider a subtree or submodule.

## 6. Comparing Clone and CI Workflows

The clone workflow is the most visible difference for newcomers joining the project.

| Task | Submodule | Subtree | Regular Directory |
|---|---|---|---|
| Clone superproject | May require `--recurse-submodules` | Regular clone | Regular clone |
| Update external content | `git submodule update` or branch workflow | `git subtree pull` | Manual update |
| Access permissions | Requires access to child repository | Only needs read access to superproject for imported content | Only needs read access to superproject |
| Build in CI | Must initialize submodules before building | Contents available immediately after clone | Contents available immediately after clone |
| Version locking | Gitlink records commit SHA | Superproject commit records subtree contents | Superproject commit records directory contents |

Example CI preparation step when using submodules:

```bash
git submodule update --init --recursive
```

If the pipeline clones fresh, you can configure the clone with `--recurse-submodules`. With subtrees or regular directories, this extra step is unnecessary because the files already live in the superproject's tree.

Do not compare clone time alone. Factor in history size, the number of repositories requiring authentication, dependency caching, network reachability, and trust in the external code source.

## 7. History and Reviewing Changes

### With Submodules

The superproject typically shows submodule updates as gitlink changes:

```bash
git diff --submodule
git ls-tree HEAD libs/payment-core
```

Reviewers need to see the old and new commit SHAs, and may open the child repository to read commit details. The superproject diff does not automatically show every individual file change inside the submodule.

### With Subtrees

Files under the prefix are direct contents of the superproject. They can be reviewed with regular diffs:

```bash
git diff -- vendor/payment-core
git log --oneline -- vendor/payment-core
```

If full history was imported, upstream history can be inspected in the commit graph. With `--squash`, each sync produces a summary commit representing the imported state; detailed upstream commits remain in the source repository.

### With Regular Directories

Review like any other change in the repository:

```bash
git diff -- libs/payment-utils
git log --oneline -- libs/payment-utils
```

Git has no built-in way to distinguish which changes originated from upstream unless the team records that via commit messages, metadata, or a dedicated process.

## 8. Ownership, Versioning, and Maintenance

Choose a model based on ownership boundaries:

- If the library has its own maintainers, releases, and access controls, submodules maintain clear repository boundaries.
- If the application wants to carry external code inside the same repository while still pulling periodic upstream updates, subtrees may be a good fit.
- If the code is simply part of the application and does not need syncing from another repository, a regular directory is the simplest option.

Submodules pin specific commits for reproducible external versions, though the team must ensure those commits continue to be served by the remote. Subtrees also capture content state in the parent commit, so checking out an older superproject commit restores the exact integrated version. Regular directories are likewise pinned in the parent commit, without Git-managed upstream links.

Across all three approaches, verify licenses, provenance, security patching workflows, and who is responsible for version upgrades. Pulling code into a subtree or regular directory does not alter that source code's license obligations.

## 9. Quick Selection Table

| Question | Usually Appropriate Choice |
|---|---|
| Does the component have its own repository, releases, and owning team? | Submodule |
| Want one-step cloning with external code included while still syncing upstream? | Subtree |
| Is the code simply part of the same product with no independent upstream? | Regular directory |
| Need multiple projects referencing the same library commits while picking versions independently? | Submodule |
| Want to review library updates as file diffs in application pull requests? | Subtree or regular directory |
| Want to avoid adding child-repository initialization steps in CI? | Subtree or regular directory |

There is no single best choice for every project. Prefer the model that accurately reflects how your team owns and releases that component, then standardize your clone, update, and review workflows accordingly.

## 10. Hands-on Exercise

In a test environment, prepare a `storefront` application repository and a `payment-core` library repository with at least two commits.

1. Add `payment-core` as a submodule, commit the superproject, and inspect the gitlink using `git ls-tree HEAD`.
2. Clone the superproject into a new directory without `--recurse-submodules`, observe its state, and then run `git submodule update --init`.
3. Create another test repository and import `payment-core` using `git subtree add --prefix=vendor/payment-core ... --squash`.
4. Create a new commit in `payment-core`, then update the subtree with `git subtree pull`.
5. Compare `git diff --submodule` with `git diff -- vendor/payment-core` to observe how reviews differ between the two models.
6. Create a regular source directory in `storefront`, stage and commit it; explain why Git has no awareness of a separate upstream for that directory.
7. Write a short decision note for a hypothetical project: which model fits if the library has an independent release team, and which model fits if the library is purely vendored into the application.

You have completed the exercise when you can explain what the superproject stores in each model, how clones fetch external code, and how versions are updated from the source repository.
