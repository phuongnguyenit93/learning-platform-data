# Locating Commits with Short Hashes, HEAD~, HEAD^, and Reference Names

When inspecting Git history, you often need to pinpoint a specific commit to view its contents, compare changes, create a branch, or restore state. Git lets you locate commits by object ID (OID), a partial hash prefix, a branch/tag name, special reference names such as HEAD, or parent-relationship expressions like <code>HEAD~2</code> and <code>HEAD^</code>.

All of these notations resolve to an object or commit, but their meanings differ. Short hashes identify an object by hash prefix; reference names identify a named position in the repository; <code>~</code> and <code>^</code> follow parent links in the commit graph.

This article explains how to read and combine revision selectors to pinpoint the exact commit in both linear histories and histories with merges.

## 1. Commits Are Identified by Object ID

Every Git object has an identifier computed from the object's content and type. This identifier is commonly called an object ID (OID) or hash.

A commit object contains the following key information:

- The tree OID of the snapshot.
- Parent OIDs (one or more parents).
- Author and committer.
- Commit creation timestamps.
- Commit message.

Example output:

~~~bash
git log -1 --format=fuller
~~~

~~~text
commit 4f2c9a7d8e1b...
Author: Developer <dev@example.com>
Date:   Tue Nov 17 10:30:00 2026 +0700

    Add payment validation
~~~

The line starting with <code>commit</code> is the commit's OID. When passing an OID to commands like <code>git show</code>, <code>git log</code>, or <code>git branch</code>, Git can locate the corresponding object.

An OID is a content-addressed identifier. If a commit's content changes, its OID changes too. Therefore, a commit recreated after a rebase normally has a different OID from the original commit, even if the source code diff looks similar.

## 2. SHA-1, SHA-256, and OID Length

Traditional Git repositories use the SHA-1 object format, with a full OID of 40 hexadecimal characters. Git also supports repositories using the SHA-256 format, with a full OID of 64 hexadecimal characters.

Check a repository's object format:

~~~bash
git rev-parse --show-object-format
~~~

The output is typically:

~~~text
sha1
~~~

or:

~~~text
sha256
~~~

Do not assume every OID is always 40 characters long. When writing documentation, scripts, or integration tools, let Git supply the OID rather than truncating strings to a fixed length.

The <code>--show-object-format</code> option is available in Git 2.29 and later. The SHA-256 format still has some compatibility limitations with tools or services that only support SHA-1 repositories; when using this format, verify that your entire toolchain supports it.

Retrieve the full OID of the current commit:

~~~bash
git rev-parse HEAD
~~~

Retrieve the full OID of a specific commit:

~~~bash
git rev-parse main
~~~

## 3. What Is an Abbreviated Hash?

Git allows using a prefix of an OID instead of the full OID, provided the prefix is long enough to uniquely identify a single object in the current repository.

For example, if the full OID is:

~~~text
4f2c9a7d8e1b63c5...
~~~

then <code>4f2c9a7</code> works as long as no other object starts with that same prefix. If another object shares that prefix, Git reports an ambiguous short object ID and asks for more characters.

Key points to remember:

- A short hash is a prefix of the OID, not a separate identifier.
- The minimum required length depends on the number of objects and colliding prefixes.
- As a repository gains more objects, a previously unique prefix can become ambiguous.
- Full OIDs are more stable for storing in operational runbooks or exchanging exact references across repositories with the same object format.

## 4. Getting Abbreviated Hashes with git rev-parse

Use <code>--short</code> to ask Git to print an abbreviated OID:

~~~bash
git rev-parse --short HEAD
~~~

You can request a specific minimum length:

~~~bash
git rev-parse --short=12 HEAD
~~~

The number <code>12</code> is the desired minimum length. If more characters are required for uniqueness, Git can print a longer string.

Get the abbreviated OID of a branch:

~~~bash
git rev-parse --short=12 main
~~~

Get the abbreviated OID of a tag:

~~~bash
git rev-parse --short=12 v2.4.0
~~~

Use this command instead of manually slicing the first few characters from <code>git log</code> output, because Git guarantees the prefix is long enough to be unique in the repository.

## 5. Viewing OIDs and Abbreviated Hashes in git log

To view commits with abbreviated hashes:

~~~bash
git log --oneline
~~~

Example:

~~~text
4f2c9a7 Add payment validation
19ab3d2 Add payment endpoint
a6e8c10 Initial project
~~~

The <code>--oneline</code> option corresponds to a compact commit display, usually showing the abbreviated OID and commit message subject.

To explicitly display full OIDs:

~~~bash
git log -5 --format="%H %s"
~~~

Where:

- <code>%H</code> is the full OID.
- <code>%h</code> is the abbreviated OID.
- <code>%s</code> is the commit message subject.
- <code>%an</code> is the author name.
- <code>%ad</code> is the author date, formatted according to the date option.

Example:

~~~bash
git log -5 --format="%h %ad %an %s" --date=short
~~~

## 6. Why You Should Not Hardcode Hash Lengths

A 7-character short hash may be unique in a small repository, but it is not guaranteed in a larger repository. As object count grows, prefix collision probability increases.

Do not write scripts assuming every commit has an exact 7-character short hash. Use:

~~~bash
git rev-parse --short HEAD
~~~

or if you want a readable format with a minimum length:

~~~bash
git rev-parse --short=12 HEAD
~~~

If you need an identifier for long-term storage, use the full OID:

~~~bash
git rev-parse HEAD
~~~

Short hashes are great for quick log reading and internal communication. Full OIDs are better suited for integration systems, audit logs, or documentation where ambiguity must be avoided.

## 7. What Is a Reference Name (ref)?

A ref is a name Git uses to point to an object, usually a commit. Instead of memorizing hashes, you can use branch names, tags, or special refs.

Common refs:

| Type | Example | Typical Location |
|---|---|---|
| Local branch | <code>main</code> | <code>refs/heads/main</code> |
| Tag | <code>v2.4.0</code> | <code>refs/tags/v2.4.0</code> |
| Remote-tracking branch | <code>origin/main</code> | <code>refs/remotes/origin/main</code> |
| HEAD | <code>HEAD</code> | Special ref for the current checkout position |
| Remote fetch result | <code>FETCH_HEAD</code> | Ref/commit info received from the most recent fetch |
| Previous operation tip | <code>ORIG_HEAD</code> | Temporary ref updated by certain operations |

Short names like <code>main</code> or <code>v2.4.0</code> are convenient. If there is a name collision or you need absolute clarity, use the full ref name such as <code>refs/heads/main</code> or <code>refs/tags/v2.4.0</code>.

## 8. Local Branches vs. Remote-Tracking Branches

A local branch is a branch you work on directly, for example:

~~~bash
git switch main
~~~

Its full ref name is:

~~~text
refs/heads/main
~~~

A remote-tracking branch is a local record of a branch on a remote, for example:

~~~text
refs/remotes/origin/main
~~~

Its common shorthand is <code>origin/main</code>. This ref is updated during fetch or corresponding remote operations that update tracking refs. It does not automatically change with new commits on the server until you fetch.

Inspect branches:

~~~bash
git branch
git branch -r
git branch -avv
~~~

If you want to know how many commits the current branch differs from its remote-tracking branch, fetch first to update local tracking info before comparing:

~~~bash
git fetch origin
git log --oneline main..origin/main
~~~

Do not treat <code>origin/main</code> as a live pointer to the server's real-time state at every moment. It is a local ref reflecting the last synchronization.

## 9. Tags and Annotated Tags When Locating Commits

A tag is a ref commonly used to mark versions or release milestones.

List tags:

~~~bash
git tag --list
~~~

View the commit a tag points to:

~~~bash
git show v2.4.0
~~~

A lightweight tag points directly to an object, usually a commit. An annotated tag has its own tag object containing the tagger, creation date, message, and optional signature; that tag object in turn points to the tagged object.

When you need the commit represented by a tag, use the peel syntax shown later or ask Git to verify the commit type.

Example:

~~~bash
git rev-parse --verify 'v2.4.0^{commit}'
~~~

This is helpful when a tag might be an annotated tag and you need the underlying commit rather than the tag object.

## 10. HEAD as a Special Reference Name

<code>HEAD</code> represents the current location checked out in the repository.

Normally, HEAD is a symbolic ref pointing to the current branch. For example:

~~~text
HEAD -> refs/heads/main
~~~

When working on the main branch, <code>HEAD</code> and <code>main</code> normally point to the same commit.

Check this:

~~~bash
git status -sb
git branch --show-current
git symbolic-ref --short HEAD
~~~

If you are in detached HEAD state, HEAD points directly to a commit instead of a branch. In that case, <code>git branch --show-current</code> prints an empty line and <code>git symbolic-ref --short HEAD</code> fails because HEAD is no longer a symbolic ref.

Check the OID that HEAD currently points to:

~~~bash
git rev-parse HEAD
~~~

## 11. What Do HEAD~ and HEAD~n Mean?

The <code>~</code> operator walks backward along a commit's **first parent**.

- <code>HEAD~0</code> is the current HEAD.
- <code>HEAD~1</code> is the first parent of HEAD.
- <code>HEAD~2</code> is the first parent of the first parent.
- <code>HEAD~3</code> steps back three times along the first-parent chain.

Linear history example:

~~~text
A---B---C---D---E  main
                ^
               HEAD
~~~

When HEAD is at E:

| Expression | Selected Commit |
|---|---|
| <code>HEAD</code> | E |
| <code>HEAD~1</code> | D |
| <code>HEAD~2</code> | C |
| <code>HEAD~3</code> | B |
| <code>HEAD~4</code> | A |

You can omit the number 1:

~~~bash
git show HEAD~
~~~

Equivalent to:

~~~bash
git show HEAD~1
~~~

<code>HEAD~</code> is also equivalent to <code>HEAD^</code> in the first-parent case.

## 12. What Do HEAD^ and HEAD^n Mean?

The <code>^</code> operator selects a specific parent of a commit.

- <code>HEAD^</code> is equivalent to <code>HEAD^1</code>, i.e., the first parent.
- <code>HEAD^2</code> selects the second parent.
- <code>HEAD^3</code> selects the third parent if the commit has at least three parents.

In linear history, each regular commit has only one parent, so <code>HEAD^</code> and <code>HEAD~1</code> produce the same result.

The difference becomes clear at a merge commit, because a merge commit typically has two parents.

Example:

~~~text
        D---E
       /     \
A---B---C-----M  main
              ^
             HEAD
~~~

In this example:

- The first parent of M is C (the branch checked out when merging).
- The second parent of M is E (the tip of the merged-in branch).

Therefore:

~~~bash
git show HEAD^1
git show HEAD^2
~~~

The first command inspects C; the second inspects E.

## 13. Distinguishing HEAD~2, HEAD^^, and HEAD^2

This is where newcomers to Git often get confused.

In linear history:

~~~text
A---B---C  main
        ^
       HEAD
~~~

All of the following expressions point to A:

- <code>HEAD~2</code>
- <code>HEAD^^</code>
- <code>HEAD~1~1</code>
- <code>HEAD^1^1</code>

But at a merge commit:

~~~text
        D---E
       /     \
A---B---C-----M
              ^
             HEAD
~~~

The meanings differ:

| Expression | Path |
|---|---|
| <code>HEAD~2</code> | M → parent 1 is C → parent 1 is B |
| <code>HEAD^^</code> | M → parent 1 is C → parent 1 is B |
| <code>HEAD^2</code> | M → parent 2 is E |
| <code>HEAD^1</code> | M → parent 1 is C |

Remember: the number after <code>~</code> is the number of steps along the first parent; the number after <code>^</code> is the index of the parent selected at a single commit.

## 14. Using ~ and ^ to Navigate History with Merges

At a merge commit, choosing which parent to follow determines which branch history you traverse.

Example:

~~~bash
git log --oneline --graph --decorate --all
~~~

Suppose HEAD is merge commit M:

~~~bash
git show HEAD^1
git show HEAD^2
git log --oneline HEAD~3
git log --oneline HEAD^2
~~~

Common use cases:

- View the main branch right before the merge: usually <code>HEAD^1</code>.
- View the tip of the branch that was merged in: usually <code>HEAD^2</code>.
- Step back multiple commits along the first-parent line: use <code>HEAD~n</code>.
- Follow a specific parent of a merge: use <code>HEAD^n</code>.

Not every merge commit has exactly two parents. An octopus merge can have three or more parents. If you select a parent index that does not exist, Git reports an error.

## 15. ^0: Resolving the Current Commit of a Revision

The <code>^0</code> syntax confirms that a revision points to a commit and returns that commit itself, without stepping to any parent.

Example:

~~~bash
git rev-parse 'HEAD^0'
git rev-parse 'main^0'
git rev-parse 'v2.4.0^0'
~~~

This syntax is useful when a revision might be a tag name pointing to an annotated tag object. <code>^{commit}</code> is even clearer when the goal is to peel a tag and verify the final object is of type commit.

A root commit has no parent. Thus, <code>HEAD^</code> fails at a root commit, whereas <code>HEAD^0</code> still returns the root commit itself.

## 16. Peeling Tags with ^{} and ^{commit}

Git supports peel syntax to dereference a tag object down to the underlying tagged object.

- <code>v2.4.0^{}</code> tells Git to recursively peel the tag until an object that is no longer a tag is reached.
- <code>v2.4.0^{commit}</code> tells Git to peel and verify that the target object is a commit.
- <code>v2.4.0^{tree}</code> requires the target object to be a tree.

Example:

~~~bash
git rev-parse 'v2.4.0^{}'
git rev-parse 'v2.4.0^{commit}'
git cat-file -t 'v2.4.0^{commit}'
~~~

The last command prints the object type, in this case <code>commit</code>.

Wrap revision expressions in single quotes so the shell does not interpret special characters. This is especially helpful in Bash, PowerShell, and cross-platform scripts.

## 17. Other Special Reference Names

Besides HEAD, Git has several useful special reference names:

| Name | Common Meaning |
|---|---|
| <code>HEAD</code> | Currently checked-out commit or branch |
| <code>ORIG_HEAD</code> | HEAD position prior to certain major operations like reset/merge |
| <code>FETCH_HEAD</code> | Info on refs/commits received from the most recent fetch |
| <code>MERGE_HEAD</code> | Commit being merged into HEAD while a merge is in progress |
| <code>CHERRY_PICK_HEAD</code> | Commit being cherry-picked while the operation is in progress |

These names are not regular branches. Some exist only while an operation is in progress or are updated by specific commands.

Example checking ORIG_HEAD:

~~~bash
git show --no-patch --oneline ORIG_HEAD
~~~

Checking FETCH_HEAD:

~~~bash
git show --no-patch --oneline FETCH_HEAD
~~~

If the ref does not exist in the current state, Git reports that it cannot resolve the revision. Do not use these as stable substitutes for branches or tags.

## 18. Upstream Selectors: @{upstream} and @{u}

A branch can have a configured upstream branch, typically the remote-tracking branch that the local branch tracks.

For example, local branch <code>feature/payment</code> tracks <code>origin/feature/payment</code>. You can run:

~~~bash
git rev-parse --abbrev-ref '@{upstream}'
~~~

Or the shorthand form:

~~~bash
git rev-parse --abbrev-ref '@{u}'
~~~

Inspect the upstream commit:

~~~bash
git log -1 --oneline '@{upstream}'
~~~

The <code>@{upstream}</code> and <code>@{u}</code> expressions depend on the current branch's upstream configuration. If no upstream is set for the branch, Git cannot resolve this expression.

Inspect tracking configuration:

~~~bash
git branch -vv
~~~

## 19. Reflog Selector ref@{n} vs. HEAD~n

Git has two syntaxes that are easy to confuse because both use special punctuation or braces:

- <code>HEAD~2</code> steps back two generations along first parents in the commit graph.
- <code>HEAD@{2}</code> selects the third entry in HEAD's reflog, i.e., a previously recorded state of HEAD.

Example:

~~~bash
git reflog show HEAD
git show 'HEAD@{2}'
git show HEAD~2
~~~

The two <code>git show</code> commands can display completely different commits.

Reflog selectors can be used with other ref names:

~~~bash
git show 'main@{1}'
git show 'origin/main@{1}'
~~~

Reflog entries are local and can expire or be deleted. <code>~</code> and <code>^</code> are based on parent relationships in the commit graph, not on local operation sequence numbers.

## 20. Using Revision Selectors with git show

<code>git show</code> is a quick way to inspect the selected commit and its changes.

Example:

~~~bash
git show HEAD
git show HEAD~1
git show HEAD^2
git show 4f2c9a7
git show main
git show v2.4.0
~~~

View commit metadata only, without the patch:

~~~bash
git show --no-patch --format=fuller HEAD~2
~~~

View only the changed file list and statistics:

~~~bash
git show --stat HEAD^
~~~

If the revision is an annotated tag, <code>git show</code> can display both tag info and the tagged object. Use <code>^{commit}</code> when you want to verify the exact commit object.

## 21. Using Revision Selectors with git log

<code>git log</code> accepts one or more revisions to scope the history to display.

Example:

~~~bash
git log --oneline HEAD~5..HEAD
~~~

This command lists commits reachable from HEAD that are not part of the history reachable from HEAD~5. In a linear history, this typically prints the five most recent commits after that baseline.

View history from a branch:

~~~bash
git log --oneline main
~~~

View history from a remote-tracking branch:

~~~bash
git log --oneline origin/main
~~~

View the graph across multiple refs:

~~~bash
git log --graph --decorate --oneline --all
~~~

Note that the <code>..</code> operator in a <code>git log</code> revision range means commits reachable on the right side that are not reachable on the left side. It is not a parent-stepping operator like <code>~</code>.

## 22. Using Revision Selectors with git diff

<code>git diff</code> compares the snapshots of two revisions:

~~~bash
git diff HEAD~1 HEAD
~~~

Compare the first parent of a merge with the merge commit:

~~~bash
git diff HEAD^1 HEAD
~~~

Compare the second parent of a merge with the merge commit:

~~~bash
git diff HEAD^2 HEAD
~~~

Compare branches:

~~~bash
git diff main feature/payment
~~~

In <code>git diff A B</code>, Git compares the tree of A against the tree of B. Pay attention to comparison direction: additions/deletions are expressed going from A to B.

The three-dot form in <code>git diff A...B</code> compares the merge-base of A and B against B. This is commonly useful when viewing changes on branch B since the common branch point.

## 23. Using Revision Selectors with branch and checkout

You can create a new branch from any revision:

~~~bash
git branch feature/restore HEAD~2
~~~

This creates a new branch pointing to the commit two first-parent steps before HEAD, without switching the working tree to the new branch.

Create and switch to the new branch:

~~~bash
git switch -c feature/restore HEAD~2
~~~

If you only want to inspect a commit without creating a branch:

~~~bash
git switch --detach HEAD~2
~~~

The repository is now in detached HEAD state. You can inspect or test things, though if you create new commits you should create a branch to keep them before leaving this state.

Do not use <code>git checkout</code> with an ambiguous name when intending to switch branches. <code>git switch</code> makes branch switching explicit; <code>git restore</code> is for restoring files.

## 24. Verifying Revisions Before Using Them in Scripts

When a revision comes from user input or external data, verify it before passing it to commands that modify the repository.

Check that a revision exists and resolves to a commit:

~~~bash
git rev-parse --verify --end-of-options 'main^{commit}'
~~~

If valid, the command prints the commit OID. If invalid or unable to peel to a commit, the command exits with an error.

You can check the object type:

~~~bash
git cat-file -t 'main^{commit}'
~~~

Expected output:

~~~text
commit
~~~

Using <code>--end-of-options</code> prevents Git from interpreting an input string starting with a hyphen as a command option. In scripts, still handle exit codes and validate inputs according to context.

## 25. Distinguishing Revisions and Pathspecs

Some Git commands accept both revisions and file paths. The <code>--</code> delimiter marks the end of revisions/options and the start of pathspecs.

Example:

~~~bash
git log main -- src/payment
git show HEAD~1 -- src/payment/service.java
git diff HEAD~2 HEAD -- src/payment
~~~

In the commands above:

- <code>main</code>, <code>HEAD~1</code>, and <code>HEAD~2</code> are revisions.
- <code>src/payment</code> or file paths are pathspecs.
- <code>--</code> ensures Git treats subsequent arguments as paths, even if a filename happens to match a ref name.

When you need to verify an exact revision, use <code>git rev-parse --verify</code>. When filtering history by file, place the pathspec after <code>--</code>.

## 26. Quick Reference Table of Revision Expressions

| Expression | Meaning |
|---|---|
| <code>HEAD</code> | Current commit |
| <code>HEAD~</code> | First parent of HEAD |
| <code>HEAD~1</code> | First parent of HEAD |
| <code>HEAD~2</code> | Step along first parent twice |
| <code>HEAD^</code> | First parent of HEAD |
| <code>HEAD^1</code> | First parent of HEAD |
| <code>HEAD^2</code> | Second parent of HEAD |
| <code>HEAD^^</code> | Step along first parent twice |
| <code>HEAD^0</code> | HEAD commit itself after verifying commit type |
| <code>main</code> | Local branch main |
| <code>origin/main</code> | Remote-tracking branch origin/main |
| <code>refs/heads/main</code> | Full ref name of local branch main |
| <code>refs/tags/v2.4.0</code> | Full ref name of tag |
| <code>v2.4.0^{commit}</code> | Commit that the tag peels to |
| <code>HEAD@{1}</code> | HEAD position at the previous reflog entry |
| <code>@{u}</code> | Upstream of the current branch |

## 27. Common Errors When Locating Commits

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Git reports ambiguous short object ID | Abbreviated hash is no longer unique | Use the full OID or a longer prefix from Git |
| <code>HEAD^</code> fails to resolve | HEAD is at a root commit with no parent | Use <code>HEAD^0</code> to get the commit itself |
| <code>HEAD^2</code> returns an error | Commit does not have a second parent | Check whether the commit is a merge commit |
| <code>HEAD~2</code> fails to resolve | First-parent history does not go back two steps | Inspect <code>git log --graph</code> and pick a valid revision |
| <code>origin/main</code> is behind server | Remote has not been fetched | Run <code>git fetch origin</code> and re-check |
| <code>@{u}</code> is invalid | Branch has no configured upstream | Check <code>git branch -vv</code> and set upstream if needed |
| Tag does not return commit directly | Annotated tag points to a tag object | Use <code>tag^{commit}</code> to peel and verify |
| Revision name mistaken for path | Ambiguous revision/pathspec | Use full ref name or place <code>--</code> before pathspec |

## 28. Workflow for Selecting the Right Revision

When locating a commit, you can follow this order:

1. Determine whether you want the current commit, a commit by branch/tag name, or an ancestor commit.
2. If you know the OID, use the full OID or a uniquely resolving short hash.
3. If using a branch/tag, verify the ref exists and check what object type it points to.
4. If stepping back in history, pick <code>~n</code> for the first-parent chain or <code>^n</code> for a specific parent.
5. If merge commits are nearby, inspect the graph with <code>git log --graph --oneline --decorate --all</code> before choosing a parent.
6. Verify the revision with <code>git show</code> or <code>git rev-parse --verify</code>.
7. Only pass verified revisions to commands that modify branches, reset state, or push.

For example, to create a branch from the second parent of the current merge commit:

~~~bash
git show --no-patch --oneline HEAD^2
git branch feature/from-merged-side HEAD^2
~~~

To create a branch from the commit two steps before HEAD along the first parent:

~~~bash
git switch -c feature/previous-point HEAD~2
~~~

These two examples pick two different paths in the commit graph. Confirm with <code>git show</code> before creating a branch when merges are present.

## 29. Hands-On Exercises

Create a test repository or use a demo repository where you can experiment safely.

### Exercise A — Retrieving Full and Abbreviated Hashes

Run:

~~~bash
git rev-parse --show-object-format
git rev-parse HEAD
git rev-parse --short HEAD
git rev-parse --short=12 HEAD
git log --oneline -5
~~~

Note the difference between the full OID and the short hash. Try adding more commits or cloning a larger repository to observe abbreviation lengths.

### Exercise B — Stepping Back Along the First Parent

Run:

~~~bash
git log --graph --oneline --decorate -10
git show HEAD~
git show HEAD~2
git show HEAD^^
~~~

Compare the commits selected by each expression. If the current history is linear, <code>HEAD~2</code> and <code>HEAD^^</code> will point to the same commit.

### Exercise C — Distinguishing Parents of a Merge

In a repository containing a merge commit, locate the merge commit and run:

~~~bash
git show --no-patch --format=raw HEAD
git show HEAD^1
git show HEAD^2
git show HEAD~2
~~~

Read the parent lines of the merge commit and identify the first and second parents. Compare against the graph:

~~~bash
git log --graph --oneline --decorate --all
~~~

If HEAD is not a merge commit, switch to an existing merge commit in history or create a merge in your lab repository.

### Exercise D — Resolving Ref Names

Run:

~~~bash
git branch -avv
git tag --list
git show-ref --heads --tags
git rev-parse --verify 'HEAD^{commit}'
git rev-parse --verify 'main^{commit}'
~~~

Try using the full ref <code>refs/heads/main</code> and compare it with the short name <code>main</code>.

### Exercise E — Distinguishing Reflog Selectors

Run:

~~~bash
git reflog show HEAD
git show 'HEAD@{1}'
git show HEAD~1
~~~

Explain why the two commits can differ: one expression selects a ref state in the reflog, while the other follows a commit parent.

## 30. Checklist Before Using a Revision in Important Commands

- [ ] Identified which repository and branch you are currently in.
- [ ] Distinguished full OID from abbreviated OID.
- [ ] Let Git determine a uniquely resolving abbreviation.
- [ ] Identified whether a ref name is a local branch, remote-tracking branch, or tag.
- [ ] Fetched if fresh remote state is needed.
- [ ] Understood that <code>~n</code> follows the first parent.
- [ ] Understood that <code>^n</code> selects the nth parent.
- [ ] Checked the parent graph when the revision is near a merge commit.
- [ ] Distinguished <code>HEAD~n</code> from <code>HEAD@{n}</code>.
- [ ] Verified the revision with <code>git show</code> or <code>git rev-parse --verify</code>.
- [ ] Used <code>--</code> to separate revisions from pathspecs when needed.
- [ ] Recorded the full OID before performing history-rewriting operations.

## 31. Key Takeaways

- Commits are identified by OID; the common format is SHA-1, while SHA-256 repositories use longer OIDs.
- Short hashes must be unique within the repository; use <code>git rev-parse --short</code> instead of manually slicing strings.
- Branches, tags, and remote-tracking branches are reference names pointing to objects.
- <code>HEAD</code> represents the current checkout location; in detached HEAD state, it points directly to a commit.
- <code>HEAD~n</code> steps back n times along the first parent.
- <code>HEAD^n</code> selects the nth parent of a commit; <code>HEAD^</code> is equivalent to <code>HEAD^1</code>.
- In a merge commit, <code>HEAD^1</code> and <code>HEAD^2</code> typically point to two different parent branches.
- <code>HEAD^0</code> confirms the current commit itself; <code>tag^{commit}</code> peels a tag down to a commit.
- <code>HEAD@{n}</code> is a reflog selector, distinct from <code>HEAD~n</code>.
- Use <code>git show</code> and <code>git rev-parse --verify</code> to confirm a revision before modifying history.
- Use <code>--</code> to separate revisions from pathspecs in commands that accept both argument types.

Once you understand OIDs, ref names, and parent traversal, you can locate the exact commit you need to inspect or operate on. Read the graph before picking a parent on a merge commit, use Git-generated abbreviations, and verify revisions prior to commands that affect branches or history.
