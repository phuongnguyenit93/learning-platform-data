# Reading History with git log and Branch Graphs

Git stores history as a directed acyclic graph (DAG). Each commit records a snapshot and references its parent commits; branches and tags are refs pointing to specific commits. The `git log` command reads commits across a range you select, while the `--graph` option visualizes parent-child relationships so you can see how branches diverge and merge.

When reading history, do not look only at dates or message lines. Identify which commit is the parent of which, where each branch/ref is pointing, which commits exist only on one branch, and which commits are merge points. Combining `git log`, `git branch`, `git merge-base`, and appropriate filters helps you understand development progress, prepare for merges/rebases, and investigate changes.

## 1. Commits and History as a Graph

A commit contains the OID of a tree representing the snapshot, author/committer metadata, a message, and one or more parent commits. A regular commit has one parent; the repository's initial commit has no parent; a merge commit typically has two or more parents.

Example of a linear history:

```text
A---B---C---D  main
```

Each new commit points back to the previous commit. If you create the `feature` branch from B and continue committing in parallel:

```text
      C1---C2  feature
     /
A---B---D---E  main
```

A branch is not a directory copy or a separate sequence of commits. A branch is a named ref pointing to the tip commit of that branch. Two branches can point to commits that share a common ancestor and then evolve in different directions.

When merging `feature` into `main`, Git can create a merge commit with two parents:

```text
      C1---C2------+
     /             \
A---B---D---E-------M  main
```

The commit graph helps answer questions such as: where each branch was created from, which commits have already been integrated, which branch still has commits not yet brought into the main branch, and which histories a merge commit connects.

## 2. Viewing Basic History with git log

Basic command:

```bash
git log
```

By default, Git displays history reachable from `HEAD`, usually the current branch. Each entry includes the commit hash, author, author date, commit metadata, and message. Press `q` to exit the pager when Git opens the output in the terminal.

For a compact view:

```bash
git log --oneline
```

Each commit is displayed on a single line with an abbreviated hash and subject. This is useful when you need to quickly scan recent history.

To also see branch/tag names pointing to commits:

```bash
git log --oneline --decorate
```

`--decorate` displays refs such as `HEAD -> main`, `origin/main`, or tags. These labels help identify which commit is a branch tip, a release tag, or the position of a remote-tracking branch.

Limit the number of most recent commits:

```bash
git log -5 --oneline --decorate
```

The number `5` only limits how many commits are displayed; it does not alter history.

## 3. Drawing Branch Graphs with --graph

A commonly used command to view the full branch graph in a clone:

```bash
git log --graph --oneline --decorate --all
```

Meaning of the options:

- `--graph`: draws connecting lines between commits and parent commits using ASCII characters.
- `--oneline`: condenses each commit onto a single line.
- `--decorate`: attaches branch, tag, and ref names to their corresponding commits.
- `--all`: traverses history reachable from all local refs known to Git, instead of only from `HEAD`.

Illustrative output example:

```text
*   8ac31e2 (HEAD -> main) Merge feature/payment
|\
| * 71c09ad (feature/payment) Add payment retry
| * 52d7a11 Add payment gateway client
* | 3a4b2f0 Fix checkout validation
|/
* 2f91c44 (tag: v1.2.0) Add checkout flow
* 0d8b6e1 Initial commit
```

Reading from top to bottom generally goes from newer commits to older commits. Each `*` represents a commit; the `|`, `/`, and `\` lines show paths through the graph back to parent commits. In the example, `main` contains the merge commit `8ac31e2`, while `feature/payment` points to commit `71c09ad` on the merged branch.

The graph is a representation of history, not an exact timeline of when each person worked. One commit may have an earlier or later author date than another due to cherry-picks, rebases, edited metadata, or unsynchronized machine clocks.

### Viewing Only Selected Branches or Ref Groups

`--all` is useful for inspecting many refs, though sometimes the graph becomes too dense. You can specify particular revisions:

```bash
git log --graph --oneline --decorate main feature/payment
```

Or view only local branches:

```bash
git log --graph --oneline --decorate --branches
```

View only remote-tracking refs:

```bash
git log --graph --oneline --decorate --remotes
```

View only tags:

```bash
git log --graph --oneline --decorate --tags
```

`--all` does not mean Git accesses every branch on the server. It only uses the refs currently present in the local clone. If the remote has new or recently updated branches, you need to fetch to update remote-tracking refs before analyzing the latest state.

## 4. Understanding Ref Labels in the Graph

When using `--decorate`, you may encounter the following labels:

| Common Label | Meaning |
|---|---|
| `HEAD -> main` | `HEAD` is pointing via the `main` branch; this commit is the current branch tip |
| `feature/search` | Local branch named `feature/search` points to this commit |
| `origin/main` | Remote-tracking ref recording the position of `main` at the last fetch from remote `origin` |
| `tag: v2.0.0` | Tag `v2.0.0` points to this commit or corresponding tag object |
| `HEAD` without a branch arrow | You may be in detached HEAD state at that commit |

A remote-tracking ref such as `origin/main` is local information about the remote's state as of the last fetch; it does not update automatically when activity occurs on the server. View remotes and URLs:

```bash
git remote -v
git branch -vv
```

`git branch -vv` displays local branches along with their upstream and ahead/behind status based on current tracking data. To update information from the remote before comparing:

```bash
git fetch --all --prune
```

Fetch updates objects and remote-tracking refs; `--prune` cleans up remote-tracking refs corresponding to branches deleted on the remote. This command does not automatically merge or rebase your working branch.

## 5. Choosing Commit Display Order

A branching graph can be displayed in different orders. Two common options:

```bash
git log --graph --oneline --all --topo-order
git log --graph --oneline --all --date-order
```

- `--topo-order` prioritizes topological order: child commits are shown before parent commits and parallel lines of development are kept from interleaving prematurely.
- `--date-order` also preserves the rule of not showing a parent before its child, while prioritizing commit date order where possible.

`--graph` implies topological order by default if you do not specify another ordering. With multi-branch histories, `--topo-order` usually makes each line of development clearer. `--date-order` is helpful when you want an order closer to commit timestamps while still preserving parent-child constraints.

Commit dates do not always reflect integration order. Rebasing creates new commits with new committer dates; cherry-picking also creates new commits; commits may also be created on machines with skewed clocks. When determining historical relationships, prioritize the parent graph and refs rather than relying solely on timestamps.

## 6. Viewing History by Branch or Commit

`git log` accepts revisions as arguments. For example:

```bash
git log --oneline main
git log --oneline feature/payment
git log --oneline v2.0.0
```

Each command displays commits reachable from that revision. Compare two branches with a graph:

```bash
git log --graph --oneline --decorate main feature/payment
```

If you only want to know which commits are on one branch and not yet on the other, use a revision range.

### Range A..B

```bash
git log --oneline main..feature/payment
```

`A..B` shows commits reachable from B but not reachable from A. In this example, the command lists commits present on `feature/payment` that are not yet in `main`.

In the opposite direction:

```bash
git log --oneline feature/payment..main
```

This command shows commits present on `main` that are not yet in `feature/payment`.

This is a quick way to check which branch has unique commits before merging or rebasing. Results depend on the ancestry graph, not merely on comparing names or commit dates.

### Range A...B

```bash
git log --oneline --left-right main...feature/payment
```

`A...B` selects commits reachable from either side but not from both; that is, the diverging commits of the two histories after excluding their common ancestors. `--left-right` marks commits on the left side with `<` and on the right side with `>`.

Example:

```text
< 2a1b3c4 Fix checkout timeout
< 7d8e9f0 Update deployment config
> 4c5d6e7 Add payment retry
> 8f9a0b1 Add gateway metrics
```

These markers help identify commits unique to each branch. You can combine `--graph` to see branch relationships:

```bash
git log --graph --oneline --left-right main...feature/payment
```

### Finding the Common Ancestor

To find the merge base of two branches:

```bash
git merge-base main feature/payment
```

The merge base is the best common ancestor that Git uses as a reference point for many three-way merge operations. Combining it with the log helps clarify where two branches started diverging.

## 7. Viewing the Graph Focused on the Main Branch

When a repository uses merge commits to integrate features, history can contain many commits inside side branches. If you only want to read the main integration line, use `--first-parent`:

```bash
git log --first-parent --graph --oneline --decorate main
```

This option follows only the first parent of each merge commit. It creates a more linear view of commits brought into the main branch, which is often useful in merge-commit workflows.

Compare:

```bash
git log --graph --oneline main
git log --first-parent --graph --oneline main
```

The first command may display commits from side branches. The second focuses on the main integration chain and omits the internal history of secondary parents. Therefore, `--first-parent` is suited for reviewing release or mainline progress, though not suited when you need to inspect every commit inside a feature branch.

Filter merge commits:

```bash
git log --merges --oneline main
```

View only non-merge commits:

```bash
git log --no-merges --oneline main
```

You can combine this with `--first-parent` to view merges brought into the mainline:

```bash
git log --first-parent --merges --oneline main
```

## 8. Reading Change Contents in History

By default, `git log` focuses on commit metadata. To inspect changed file contents, use `-p`:

```bash
git log -p -3 -- src/payment.js
```

This command displays the patch of the three most recent commits affecting the path `src/payment.js` in the traversed history.

If you only need a summary of changed files:

```bash
git log --stat --oneline -5
git log --name-status --oneline -5
```

- `--stat` displays added/deleted line counts per file.
- `--name-status` lists filenames along with statuses such as added (`A`), modified (`M`), deleted (`D`), or renamed (`R`).
- `--summary` displays summary information such as create/delete modes or detected renames.

Example:

```bash
git log --summary --find-renames -5
```

These options help you pick the right level of detail: use `--oneline` for quick scanning, `--stat` to scope changes, and then `-p` to read line-by-line diffs.

## 9. Filtering History by Author, Time, and Message

When a repository has many commits, you can combine filters to narrow down results.

### By Author or Committer

```bash
git log --author="An Nguyen" --oneline
git log --committer="Build Bot" --oneline
```

`--author` filters by the author field; `--committer` filters by the committer field. The two fields can differ, for example when one person creates a commit and another cherry-picks or applies the change.

### By Time

```bash
git log --since="2026-01-01" --oneline
git log --after="2 weeks ago" --oneline
git log --until="2026-03-31" --oneline
```

`--since`/`--after` sets the earliest bound; `--until`/`--before` sets the latest bound. Both can be combined to inspect a time window. Time filters rely on commit timestamps according to Git's rules; if a commit was recreated via rebase/cherry-pick, its date may not match when the change was originally authored.

### By Commit Message

```bash
git log --grep="payment" --oneline
git log --grep="fix.*timeout" --regexp-ignore-case --oneline
```

`--grep` searches within commit messages. You can use `--all-match` when specifying multiple patterns and wanting a commit to match all grep conditions rather than just one.

Combined example:

```bash
git log --author="An Nguyen" --since="1 month ago" --grep="payment" --oneline
```

## 10. Finding Commits That Changed a Value or Code Snippet

Sometimes you do not know the commit message or exact file, but you know a string was added, removed, or changed.

### Finding When String Occurrences Changed with -S

```bash
git log -S"calculateTotal" --oneline -- src/
```

`-S<string>` finds commits where the exact number of occurrences of the string changed in the diff. This is a good choice when you want to find when a function name or literal was introduced or removed.

### Searching by Regular Expression with -G

```bash
git log -G"return .*total" --oneline -- src/payment.js
```

`-G<regex>` finds commits with added or removed lines matching a regular expression. The main difference is that `-S` tracks changes in the occurrence count of a string, whereas `-G` looks for lines in the patch matching a regex.

Once you find a candidate commit, inspect its patch:

```bash
git show <COMMIT_ID>
```

Do not conclude a commit caused a bug just because it contains the search string. Verify the change against a reproduction test or actual behavior.

## 11. Tracking a File's History Across Renames

View commits affecting a path:

```bash
git log --oneline -- src/payment.js
```

If the file was previously renamed, use `--follow` so Git attempts to trace history back across detected renames:

```bash
git log --follow --oneline -- src/payment.js
```

`--follow` is designed for a single file path and has limitations, especially in complex merge histories. Git detects renames based on content similarity when computing diffs; commits do not store standalone rename records.

View file contents at a specific commit:

```bash
git show <COMMIT_ID>:src/payment.js
```

Find the commit that deleted a file:

```bash
git log --all --diff-filter=D --summary -- src/legacy-payment.js
```

If a path was renamed multiple times, combine `--follow`, `--name-status`, and `git show` to identify the old and new names.

## 12. Customizing Log Format

`--pretty` or `--format` lets you choose which fields to display:

```bash
git log --pretty=format:"%h %ad %an <%ae> %s" --date=short -10
```

Common placeholders:

| Placeholder | Content |
|---|---|
| `%H` | Full commit OID |
| `%h` | Abbreviated OID |
| `%T` / `%t` | Full / abbreviated tree OID |
| `%P` / `%p` | Full / abbreviated parent OIDs |
| `%an` / `%ae` | Author name / email |
| `%cn` / `%ce` | Committer name / email |
| `%ad` / `%cd` | Author / committer date in the chosen format |
| `%s` | Commit message subject |
| `%b` | Commit message body |
| `%d` | Decorations such as branches/tags |

Example showing both author date and committer date:

```bash
git log --pretty=format:"%h | author %ad | committer %cd | %s" --date=iso-strict -10
```

Some built-in presets:

```bash
git log --pretty=short
git log --pretty=fuller
git log --pretty=oneline
```

`--pretty=fuller` clearly displays both author and committer along with timestamps. This is useful when investigating commits that were cherry-picked, rebased, or recreated by someone else.

## 13. Reading the Graph When Preparing to Merge or Rebase

Before integrating the `feature/payment` branch into `main`, inspect both branch tips and their unique commits:

```bash
git fetch origin
git log --graph --oneline --decorate --all
git log --oneline main..feature/payment
git log --oneline feature/payment..main
git merge-base main feature/payment
```

These commands help answer:

1. Which commits are `main` and `feature/payment` currently pointing to?
2. Which commits does the feature branch have that main does not?
3. Which commits does main have that the feature branch does not?
4. What is the nearest common ancestor of the two branches?

If `main..feature/payment` returns no results, the feature branch has no unique commits not already in main by ancestry. If both directions return results, the two branches have diverged. The graph helps you decide whether to merge, rebase, or update the branch according to your team's workflow.

Do not rely solely on visual inspection of the graph to decide whether a fast-forward is possible. Check explicitly:

```bash
git merge-base --is-ancestor main feature/payment
```

An exit code of `0` means `main` is an ancestor of `feature/payment`; in that case `main` can fast-forward to `feature` if there are no other constraints. A non-zero exit code means that ancestry relationship does not hold.

## 14. Options for Simplifying the Graph

In long-lived repositories, an `--all` graph can be very long. You can display only commits attached to refs or tags:

```bash
git log --graph --oneline --decorate --all --simplify-by-decoration
```

`--simplify-by-decoration` omits many undecorated commits to highlight branch/tag milestones. It is helpful for an overview, though it does not replace the full graph when investigating a specific change.

Limit display depth:

```bash
git log --graph --oneline --decorate --all -30
```

View only commits along the ancestry path between two milestones:

```bash
git log --ancestry-path base..feature/payment --oneline
```

`--ancestry-path` restricts results to commits lying on the ancestry path within the range, which is helpful when a branch has many side branches and you only care about the chain connecting to a specific milestone.

## 15. Limitations to Keep in Mind When Reading History

- **`--all` only sees existing local refs.** Unfetched branches or refs hidden by the server will not appear.
- **Remote-tracking branches can be stale.** Run fetch before concluding whether a remote has or has not received a commit.
- **Commit dates are not parent-child order.** Use graph/topological order to understand historical relationships.
- **Rebase and cherry-pick create new commits.** Patch contents may be identical while OIDs and parents differ.
- **Renames are inferred from content.** Similarity thresholds and merge history can change how renames are displayed.
- **Shallow clones have limited history.** The graph only reflects the commits present in the clone.
- **Reflog differs from git log.** `git log` inspects commits reachable from selected revisions/refs; `git reflog` records movements of local refs and can help find commits no longer reachable from any branch.
- **A graph does not prove commit quality.** It describes historical relationships, not whether tests passed or changes are correct.

If you need to find a commit dropped from a branch after a reset, try:

```bash
git reflog --all --date=local
```

Once you find the commit to keep, create a rescue branch so it remains reachable:

```bash
git branch rescue/important-commit <COMMIT_ID>
```

## 16. Daily History-Reading Workflow

When picking up a new branch or preparing to review a pull request, you can follow this sequence:

**Step 1: Determine current status**

```bash
git status --short
git branch -vv
git remote -v
```

**Step 2: Update remote information if needed**

```bash
git fetch --all --prune
```

**Step 3: View the overview graph**

```bash
git log --graph --oneline --decorate --all --topo-order -40
```

**Step 4: Compare branches**

```bash
git log --left-right --oneline main...feature/payment
git merge-base main feature/payment
```

**Step 5: Read relevant commits and patches**

```bash
git log --stat --oneline main..feature/payment
git log -p main..feature/payment -- src/payment.js
```

**Step 6: Record conclusions**

Clearly note which commits exist only on feature, which exist only on main, what the merge base is, and whether merge commits are present. During review, reference specific OIDs rather than just describing "the latest commit".

## 17. Hands-On Exercise

In a test repository, create a history with a `main` branch, a `feature/search` branch, at least three commits on each branch, and one merge commit.

1. Run `git log` and `git log --oneline --decorate` to compare the level of detail.
2. Run `git log --graph --oneline --decorate --all` and identify the branch point commit, the feature branch tip commit, and the merge commit.
3. Use `git branch -vv` to compare local branches with their upstream if the repository has a remote.
4. Compare `git log main..feature/search` with `git log feature/search..main`.
5. Run `git log --left-right --graph --oneline main...feature/search` and explain the `<` and `>` markers.
6. Use `git log --first-parent --graph --oneline main` to compare the mainline view against the full graph.
7. Filter history using `--author`, `--since`, `--grep`, and `-S` or `-G`.
8. Rename a file in the repository, commit, and then use `git log --follow --oneline -- <path>` to view history across the rename.
9. Create a new commit on a branch, fetch from the remote, and explain why `origin/main` only updates after fetching.

You have completed the exercise when you can read the commit graph, determine relationships between branches and merges, distinguish commits unique to each branch, and choose the right `git log` filters for an investigation question.
