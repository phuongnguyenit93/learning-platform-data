# Creating a Stash with a Description and Listing Stashes

When working on an unfinished task and needing to switch to something else, you can temporarily shelve your changes using **Git stash**. Each stash saves a snapshot of your working state at the time of creation. You can add a description to identify the purpose of that shelve, then view the list of existing stashes to find the right piece of work again.

The most commonly used command is `git stash push -m "description"`. Afterward, `git stash list` displays stash entries in newest-first order. This lesson focuses on creating a stash with a description, specifying its contents, and reading the stash list.

## 1. What is stash used for?

Stash helps temporarily shelve uncommitted changes so the working tree returns to a cleaner state, making it convenient to switch branches, pull updates, or handle an urgent request.

For example, you are editing two files for a payment feature but do not want to create a commit yet. An urgent bug appears on another branch. You can shelve your current changes, switch branches to fix the bug, and then return to retrieve the shelved work.

Stashes are data stored in the local repository. They are not automatically pushed to a remote like branches and are not a long-term backup. If you need to share work or preserve durable history, create an appropriate branch and commit.

## 2. Creating a stash with a description

Modern syntax:

```bash
git stash push -m "short-description"
```

Or use the full option name:

```bash
git stash push --message "short-description"
```

Example in a project:

```bash
git status
git stash push -m "Pause payment processing"
git status
```

The message is stored with the stash entry and displayed in the list. Describe the purpose or scope of the changes, for example:

```bash
git stash push -m "WIP: validate payment request"
git stash push -m "Temporarily shelve login page UI"
git stash push -m "Save changes before updating main"
```

A good description helps you recognize a stash after several days, when the list already has many entries. You can use a ticket ID, feature name, or reason for shelving; avoid generic descriptions like `test`, `tmp`, or `fix`.

If there are no eligible changes to shelve, Git reports that there are no local changes to save and does not create a new stash. Therefore, check `git status` before creating one.

### Stashing selected files

You can restrict a stash to specific paths using a pathspec placed after `--`:

```bash
git stash push -m "Temporarily shelve config file" -- src/config.yml
```

This command only shelves changes matching `src/config.yml`; other files remain in the working tree. The `--` separator distinguishes Git options from file paths, which is especially useful when a filename could be misinterpreted as a revision or an option.

You can specify multiple paths:

```bash
git stash push -m "Temporarily shelve API layer" -- src/api/PaymentController.java src/api/PaymentService.java
```

Before using a pathspec, check `git status` to know exactly which files will be shelved and which will remain.

## 3. Which types of changes are included in a stash?

By default, `git stash push` saves changes to files tracked by Git, including both staged and unstaged changes. Untracked and ignored files are not included in a stash by default.

| Change type | Default | Option |
|---|---|---|
| Modified tracked file, unstaged | Shelved | No extra option needed |
| Staged tracked file | Shelved | No extra option needed |
| New file not yet tracked by Git (untracked) | Not shelved | `-u` or `--include-untracked` |
| Ignored file | Not shelved | `-a` or `--all` |

Include untracked files in the stash:

```bash
git stash push -u -m "Save new unadded files too"
```

Include ignored files in the stash:

```bash
git stash push -a -m "Save ignored files too"
```

`-a` includes both untracked and ignored files. Be cautious with this option because build directories, log files, auto-generated files, or local data can take up large amounts of space. You should not shelve files containing secrets or sensitive data in a stash if repository policy prohibits it.

### Shelving only unstaged changes

If you want to keep staged content in the index and shelve only unstaged edits, use `--keep-index`:

```bash
git stash push --keep-index -m "Temporarily shelve unstaged part"
```

This option is useful when you have staged part of your changes to prepare a commit, but need to temporarily shelve the rest. Staged changes are kept in the index and working tree as intended by the option. Check `git status` afterward to confirm the resulting state.

If you only want to shelve staged changes, Git provides the `--staged` option in supported versions:

```bash
git stash push --staged -m "Temporarily shelve staged part"
```

This option puts only staged changes into the stash. If your Git version does not support it yet, check `git stash push -h` to see available options.

## 4. Inspecting the newly created stash

After stashing, check the working tree state:

```bash
git status
```

If there are no tracked changes left to keep, the working tree returns to a clean state with respect to the shelved changes. If untracked files remain, you may not have used `-u`; if ignored files remain, you may need `-a` depending on your goal.

View the latest stash entry:

```bash
git stash list
```

Example output:

```text
stash@{0}: On feature/payment: WIP: validate payment request
stash@{1}: On main: Temporarily shelve login page UI
stash@{2}: On feature/report: Save changes before updating main
```

Each line typically contains:

- `stash@{n}`: the selector referencing the stash entry in the reflog.
- The branch name at the time of creation, if recorded by Git.
- The descriptive message passed via `-m`/`--message`.

`stash@{0}` is the newest entry. When adding a new stash or deleting an entry, the index `n` can shift. Therefore, re-check `git stash list` right before using an index, especially if multiple stash operations occur consecutively.

## 5. Filtering how the stash list is displayed

`git stash list` accepts `git log` formatting options. For example, displaying the selector, timestamp, and message:

```bash
git stash list --date=local --format="%gd | %cd | %gs"
```

Commonly useful placeholders:

- `%gd`: selector name in the form `stash@{0}`.
- `%cd`: commit creation date in the chosen date format.
- `%gs`: reflog entry message, typically containing the branch and stash description.
- `%H`: full hash of the stash commit.

If the list is long, you can limit the number of lines:

```bash
git stash list -n 5
```

Or display only concise information:

```bash
git stash list --format="%gd %gs"
```

The message is text for human identification; Git does not enforce naming rules or guarantee that the description accurately reflects the files inside. Inspect the diff before applying a stash.

## 6. Viewing the contents of a stash in the list

To view a summary of changes in the latest stash:

```bash
git stash show 'stash@{0}'
```

Display per-file statistics:

```bash
git stash show --stat 'stash@{0}'
```

View the full patch:

```bash
git stash show -p 'stash@{0}'
```

Replace `stash@{0}` with the selector you want to inspect. If the stash was created with `-u` or `-a` and you want to see untracked files too, use the `--include-untracked` option on supported Git versions:

```bash
git stash show --include-untracked --stat 'stash@{0}'
git stash show --include-untracked -p 'stash@{0}'
```

Check `git stash show -h` if your current version does not accept this option.

You can also inspect the stash commit with:

```bash
git show --stat 'stash@{0}'
git log -1 --oneline 'stash@{0}'
```

A stash is typically represented by a special commit, which can contain information about the working tree and index states at the time of shelving. For stashes with untracked files, Git stores additional data needed to restore them. When using stash, there is no need to manipulate this commit structure directly; the `git stash` commands provide a more suitable interface.

## 7. Example workflow for creating and finding a stash

Suppose you are editing a payment API, have changes in tracked files, and added a new test file not yet tracked by Git. You need to temporarily switch to the `hotfix/login` branch.

Check the status before shelving:

```bash
git status --short
```

Create a stash with a description and include untracked files:

```bash
git stash push -u -m "WIP: payment API and new tests"
```

Check the working tree and list:

```bash
git status
git stash list
```

Find the newly created entry and inspect its contents:

```bash
git stash show --stat 'stash@{0}'
git stash show --include-untracked -p 'stash@{0}'
```

Now you can switch to the branch you need to work on:

```bash
git switch hotfix/login
```

When returning to the feature branch, check the stash list once more to confirm the right selector before applying. Applying and deleting stashes are covered in subsequent operations; creating a stash and viewing the list do not automatically restore changes.

## 8. Notes on managing multiple stashes

- Use contextual descriptions: feature name, ticket, or reason for shelving.
- Run `git stash list` before referencing `stash@{n}` because indices shift over time.
- View `git stash show -p` before applying an old stash if you do not remember its exact contents.
- Use `-u` when you need to keep untracked files; only use `-a` when you truly need to save ignored files too.
- Stashes reside in the local repository and can be deleted; do not use them as a substitute for commits or backups.
- If there are multiple independent changes or a need to share with teammates, creating separate branches and committing is easier to manage.

## 9. Practice exercise

In a test repository, modify a tracked file, create an additional untracked file, and leave an ignored file if the project has an appropriate ignore configuration.

1. Run `git status --short` to identify the three types of states.
2. Create a stash with only tracked changes using `git stash push -m "WIP: tracked files"`.
3. Check `git stash list` and view the contents with `git stash show -p 'stash@{0}'`.
4. Create another stash including untracked files using `git stash push -u -m "WIP: include new test"`.
5. Run `git stash list --format="%gd | %cd | %gs" --date=local` to view the selector, date, and description.
6. Compare the list and contents after creating the two stashes; explain why the newest entry has selector `stash@{0}`.

You have completed the exercise when you can create stashes with recognizable descriptions, select the exact scope of files to shelve, and locate the right stash in the list.
