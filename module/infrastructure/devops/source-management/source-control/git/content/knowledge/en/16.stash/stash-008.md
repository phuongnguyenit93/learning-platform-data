# Viewing, Deleting, and Recovering Lost Stashes Before Objects Are Pruned

Git stash helps temporarily shelve changes in the working tree so you can switch branches or handle another task. Each stash is stored as Git objects and managed via the `refs/stash` reference and its reflog. You can inspect, apply, pop a stash from the list, or delete a stash when it is no longer needed.

If a stash is deleted by mistake, the data sometimes still remains in the object database as an unreferenced commit. When these objects have not yet been pruned by Git, you can locate them using `git fsck`, identify the right stash commit, and recreate a reference to recover it. Because the retention window for unreferenced objects is limited and depends on cleanup configuration, stop prune operations and secure the object as soon as possible.

## 1. How are stashes stored and numbered?

Git stores the stash list through the `refs/stash` ref. Each time a new stash is created, Git updates this ref and records an entry in the reflog. Names like `stash@{0}` and `stash@{1}` access entries by position in the reflog:

- `stash@{0}` is usually the newest stash.
- `stash@{1}` is the stash immediately before it.
- Indices shift when you add or delete stashes.

Because indices can shift, check `git stash list` before using `stash@{n}`. If you need to identify a specific stash across multiple operations, you can retrieve the OID of the stash commit and note it down:

```bash
git stash list
git rev-parse 'stash@{0}'
```

Structurally, a stash is typically a commit whose first parent points to the `HEAD` commit at the time of shelving, second parent saves the index state, and which may have a third parent containing untracked files if the stash was created with `-u` or `-a`. The `-a` option also includes ignored files. The tree of the stash commit describes the shelved working tree state.

Understanding this structure helps when recovering a lost stash: `git fsck` can find the stash commit even when it no longer appears in `git stash list`.

## 2. Listing and viewing stash contents

List existing stashes:

```bash
git stash list
```

Example:

```text
stash@{0}: On feature/payment: save payment validation
stash@{1}: WIP on main: 4c2a1b7 update documentation
stash@{2}: On feature/search: add unfinished search flow
```

The message after the colon is generated from the branch and base commit information or from the `-m` content you provided. Set a specific message when creating a stash for easy identification.

View change statistics of a stash:

```bash
git stash show --stat 'stash@{0}'
```

View detailed diff:

```bash
git stash show -p 'stash@{0}'
```

If the stash contains untracked files, add `--include-untracked` to view that part too:

```bash
git stash show --stat --include-untracked 'stash@{0}'
git stash show -p --include-untracked 'stash@{0}'
```

The `--only-untracked` option restricts the output to untracked files included in the stash. These viewing options do not alter the stash contents.

By default, `git stash push` does not shelve untracked files. Use `-u` (`--include-untracked`) to shelve those files too; use `-a` (`--all`) if you also need to shelve ignored files. When inspecting an old stash, remember that files not included in the stash from the start cannot appear during recovery.

## 3. Applying, recovering, and deleting stashes

### Apply: apply while keeping the stash in the list

```bash
git stash apply 'stash@{0}'
```

`apply` brings changes from the stash into the current working tree while keeping the stash entry intact. This is usually a good choice when you want to verify the result before deciding to delete the stash.

If you want to restore the staged state saved in the stash as well, use `--index`:

```bash
git stash apply --index 'stash@{0}'
```

Git will attempt to restore the index state too. If applying the index fails due to conflicts or state differences, you may need to resolve manually and re-check the staging area.

### Pop: apply and remove from the list on success

```bash
git stash pop 'stash@{0}'
```

`pop` is similar to `apply`, except Git removes the stash from the list if application succeeds. If conflicts prevent application from completing, the stash is typically kept so you can resolve and retry. For important work, use `apply` first, verify the result, and only `drop` when certain the stash is no longer needed.

### Branch: create a branch from the stash's base commit

When a stash was created on another branch or applying onto the current branch would easily cause conflicts, you can use:

```bash
git stash branch recover/payment-work 'stash@{0}'
```

Git creates and switches to a new branch at the commit where the stash was originally created, then applies the stash's changes. If application succeeds, the stash entry is removed from the list. This approach is often helpful when you want to continue working in the exact original context.

### Drop: delete one stash entry

```bash
git stash drop 'stash@{1}'
```

This command deletes the specified entry from the stash list. Check `git stash list` right before dropping because `stash@{n}` indices may have shifted after other operations.

### Clear: delete the entire stash list

```bash
git stash clear
```

`clear` deletes all stash entries. Commit objects may become unreachable and eventually get pruned from the object database. Do not use `clear` as a routine cleanup unless you have confirmed every stash is no longer needed.

## 4. Understanding lost stashes and unreachable objects

While a stash is in the list, the `refs/stash` ref and reflog let Git locate the stash commit. When you drop an entry or clear the list, some stash commits may no longer have any ref pointing to them. They become objects unreachable from current refs, commonly called **unreachable** or **dangling** depending on how they are inspected.

Unreachable does not mean the data was deleted immediately. Object contents may still reside in `.git/objects` or the packed object database. Git can prune them during subsequent garbage collection/prune runs once they expire according to configuration.

Therefore, if you just deleted a stash by mistake:

1. Immediately stop cleanup operations such as `git gc --prune=now`, `git prune`, or commands that expire the reflog.
2. Avoid running automated object database cleanup tools while searching for the stash.
3. Find the remaining stash commit and create a ref to preserve it before continuing other tasks.

There is no fixed recovery window for all repositories. Object age, reflogs, `gc.pruneExpire` and `gc.reflogExpire` settings, maintenance jobs, and Git version can all affect whether the object still exists.

## 5. Checking the reflog before searching for lost objects

If the stash ref still exists, view its reflog:

```bash
git reflog show refs/stash
```

The reflog records changes to a ref. If the entry you are looking for is still in the reflog, you can take its OID and recreate the stash entry or apply it directly. However, `drop` and especially `clear` can remove the entry or related reflog; in that case, you need to search for unreachable objects.

Check other refs and reflogs if you ever created a branch or tag pointing to the stash commit. Such a backup ref can still keep the commit alive and make recovery easier.

## 6. Finding dropped or cleared stashes with git fsck

`git fsck` verifies the integrity of the object database and can list objects that are no longer referenced. Use:

```bash
git fsck --full --no-reflogs --unreachable
```

This command tells Git to perform a full check and list unreachable objects without treating reflogs as reference roots. In the output, look for lines of the form:

```text
unreachable commit 7a91d2f...
unreachable tree  1b52e30...
```

Listed commits could be lost stashes, old commits after a rebase, abandoned commits, or other data. Not every unreachable commit is a stash, so each candidate must be inspected.

If you want Git to write dangling objects into `.git/lost-found` for easier inspection, you can run:

```bash
git fsck --full --no-reflogs --lost-found
```

`--lost-found` creates reference files inside Git's internal directory; it does not automatically restore stashes into the list and does not apply changes to the working tree.

## 7. Identifying stash commits among candidates

For each OID of type `commit`, inspect its metadata and parents:

```bash
git cat-file -p <stash-oid>
```

A stash commit typically has a message like `WIP on ...` or `On ...`, has its first parent as the base commit, and its second parent as the commit storing the index. If the stash included untracked files, there may be a third parent. This structure helps distinguish stash candidates from regular commits.

View summary info and diff against the base commit:

```bash
git show --stat --oneline <stash-oid>
git diff <stash-oid>^1 <stash-oid>
```

In the second command, `^1` is the first parent of the stash commit. The diff between the first parent and the stash commit shows the saved working tree state compared to the base commit. To inspect the index part separately, you can compare the first parent with the second parent:

```bash
git diff <stash-oid>^1 <stash-oid>^2
```

If there is a third parent, it is typically a snapshot of untracked files saved with the stash. You can list the files in that tree:

```bash
git ls-tree -r <stash-oid>^3
```

Replace the illustrative OID with the full hash returned by `git fsck`. Check filenames, message, base commit, and diff contents to confirm this is indeed the stash you are looking for. Do not select based solely on a `WIP` message, as regular commits can use similar messages too.

## 8. Recreating a reference and recovering the stash

Once you have confirmed the OID is the right stash commit, save it back to the stash stack with `git stash store`:

```bash
git stash store -m "Recovered payment work" <stash-oid>
```

This command records the stash commit in `refs/stash` and the reflog, allowing Git to manage it as a stash again. Re-check:

```bash
git stash list
git stash show --stat 'stash@{0}'
```

If you want to preserve the commit with a dedicated ref for easy lookup, you can create a recovery ref first:

```bash
git update-ref refs/recovery/stash-payment <stash-oid>
```

A ref under `refs/recovery/` prevents the object from being treated as unreachable. You do not need to check out this ref. Even if you created a separate ref, still run `git stash store` as above to put the commit onto the stash stack; the separate ref serves as extra safekeeping, while `stash@{0}` is the entry just restored to the list.

After the commit is back on the stash stack, apply it to an appropriate working tree:

```bash
git stash apply --index 'stash@{0}'
```

Prefer `apply` during recovery because it keeps the stash so you can retry if conflicts occur. Check the working tree and index:

```bash
git status
git diff
git diff --cached
```

If the contents have been restored and fully verified, you can commit the work or continue editing. Only delete the recovered stash once you are sure the backup copy is no longer needed.

## 9. Handling conflicts when applying a recovered stash

The stash was created from an earlier repository state. If files have changed significantly since then, `apply` may produce conflicts.

When encountering conflicts:

```bash
git status
```

Open each file marked unmerged, combine content according to the intent of the changes, remove conflict markers, and verify the result. After resolving:

```bash
git add src/payment/PaymentService.java
```

Check both staged and unstaged parts before committing. The stash is preserved when using `apply`; if the operation does not succeed completely, do not rush to drop it. If the current state is too complex, create a separate branch or worktree to test recovery, keeping the rescue ref intact until verification is complete.

If you need to recover in the exact original commit context, you can use `git stash branch` after the stash has been restored to the list:

```bash
git stash branch recover/payment-work 'stash@{0}'
```

The command creates a branch at the original base commit, applies the stash, and deletes the stash entry if successful. If the operation hits conflicts, resolve them on the new branch and keep the rescue refs until the content is verified.

## 10. When can a stash not be recovered with git fsck?

`git fsck` can only find objects still present in the object database. If Git has already pruned the stash object and no copy remains in the reflog or another ref, the old OID cannot reconstruct the lost contents.

When the stash cannot be found:

- Check other clones of the same repository; the object might still exist on a teammate's machine.
- Check backups of the `.git` directory, disk snapshots, or machine backup systems.
- Check the IDE's local history, exported patches, temporary files, or editor buffer copies.
- If part of the changes was committed on another branch, use `git log`, `git reflog`, or search for the corresponding commit to retrieve that part.

Do not keep running prune or garbage collection hoping Git will recover more data. Cleanup commands can only remove additional unprotected objects.

## 11. Safe workflow for viewing and cleaning up stashes

A short workflow helps avoid accidental stash loss:

```bash
# 1. List and inspect stashes
git stash list
git stash show --stat 'stash@{0}'
git stash show -p 'stash@{0}'

# 2. Test-apply while keeping the stash
git stash apply --index 'stash@{0}'

# 3. Inspect the result
git status
git diff
git diff --cached

# 4. Only delete a specific stash once confirmed no longer needed
git stash drop 'stash@{0}'
```

If you need to delete multiple stashes, inspect each entry, record important OIDs, or create a backup ref beforehand. `git stash clear` wipes the entire list; use it only when you have confirmed no work remains that needs recovery.

## 12. Common confusions

| Confusion | Accurate understanding |
|---|---|
| `git stash drop` deletes the object immediately | It removes the entry from the stash reflog; the object can remain in the object database until pruned. |
| `git stash clear` can be undone with one simple command | Clear removes the stash list and related reflog; you must search for unreachable objects if the data has not been pruned yet. |
| `stash@{0}` is a permanent identifier | It is a position in the reflog and can change after adding or deleting stashes. |
| `git stash apply` deletes the stash | Apply keeps the stash; pop deletes the entry when application succeeds. |
| `git fsck` automatically recovers stashes | Fsck only finds and reports objects; you must identify the commit, create a ref or use `git stash store`, and then apply it yourself. |
| Every unreachable commit is a stash | It could be an old commit from rebase, reset, or other operations; you must check parents, message, and diff. |
| Once a stash is dropped, data is definitely lost | Objects may still exist until Git prunes them; recovery depends on whether the object still exists and is identified correctly. |

## 13. Self-check

1. **Which command lists existing stashes?**
   - `git stash list`.
2. **What is the difference between `apply` and `pop`?**
   - Apply keeps the stash in the list; pop applies and deletes the entry if application succeeds.
3. **After dropping a stash, why can recovery still be possible?**
   - The stash commit may still exist as an unreachable object until removed by garbage collection/prune.
4. **Which command searches for unreachable objects in the repository?**
   - `git fsck --full --no-reflogs --unreachable`.
5. **After identifying the right stash commit, which command puts it back onto the stash stack?**
   - `git stash store -m "Recovered stash" <oid>`.
6. **Why should you keep a rescue ref before applying a recovered stash?**
   - The ref keeps the object from being treated as unreachable, giving you a fallback point if applying or resolving conflicts runs into issues.

## Conclusion

Use `git stash list` and `git stash show` to inspect contents, `apply` or `branch` to restore, and `drop` or `clear` to clean up entries no longer needed. If a stash is deleted by mistake, check the reflog and then search for unreachable commits with `git fsck --full --no-reflogs --unreachable`. Once you identify the right stash commit, use `git stash store` or create a rescue ref to preserve the object, then apply and verify the changes. Recovery is only possible while the object has not been pruned, so avoid prune and garbage collection while searching.
