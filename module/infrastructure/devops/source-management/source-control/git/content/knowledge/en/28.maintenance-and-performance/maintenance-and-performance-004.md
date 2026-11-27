# Scheduled maintenance with `git maintenance`

When a repository operates for a long time, Git can accumulate many loose objects, small pack files, refs, and history data that need optimization. This can slow down operations such as reading logs, finding merge bases, fetching, or inspecting objects. Git provides **`git maintenance`** to run maintenance work as discrete tasks, either manually or on a background schedule.

`git maintenance` helps organize updating the commit-graph, prefetching data from remotes, packing loose objects, and organizing pack files. It can also run the `gc` task according to configuration. Understanding each task helps you select the right work to run, monitor its impact, and avoid accidentally deleting objects needed for recovery.

In the SOURCE_CONTROL_GIT module, periodic maintenance is part of keeping a repository healthy during long-term collaboration. This lesson focuses on how to use `git maintenance`, distinguish it from `git gc`, verify results, and configure an appropriate schedule.

## 1. Why does a repository need maintenance?

Git stores data in the object database. During commits, fetches, merges, or other operations, Git creates additional objects and updates refs. Over time, a repository can develop:

- Many **loose objects** stored individually in the object database.
- Many small **pack files** resulting from fetches, repacks, or separate updates.
- A commit graph that needs updating to speed up history traversal.
- Loose refs that need to be packed.
- Data from remotes not yet downloaded locally even though it will soon be needed for work.
- Objects no longer reachable after resets, rebases, or branch deletions; some objects are retained for a period before they can be pruned.

These factors do not necessarily corrupt the repository. They may simply increase disk usage or degrade performance. Maintenance reorganizes data so Git can access it more efficiently.

### 1.1. Loose objects and pack files

When Git creates objects, they may initially be stored as loose objects. Many loose objects can be consolidated into a pack file to reduce file counts and take advantage of delta compression.

Pack files typically include a `.idx` index file that helps Git locate objects inside the pack. A repository with many small packs can incur extra overhead when searching and managing them. Maintenance tasks can consolidate and reorganize them.

### 1.2. Commit graph and multi-pack-index

The commit graph is auxiliary data that speeds up traversing commit relationships such as ancestry and history. The multi-pack-index (MIDX) is an index that helps locate objects across multiple pack files without inefficiently scanning each pack index individually.

These are performance-accelerating structures. The underlying commits and objects remain in the object database; generating or updating these indexes does not alter commit contents.

### 1.3. Maintenance is not a substitute for backup

Maintenance is the work of optimizing and cleaning up a repository. It is not a backup tool and does not guarantee recovery of uncommitted changes. Before operating on a repository experiencing an issue, protect the working tree, index, refs, and necessary Git metadata.

If you are investigating lost commits or unreachable objects, do not rush to run tasks that might prune objects. Locate commits via the reflog/fsck and create rescue refs before cleaning up.

## 2. How does `git maintenance` work?

`git maintenance` divides maintenance work into small tasks. You can run a specific task, run configured tasks, or let a scheduler run them periodically.

Commonly used commands:

```bash
# Run configured tasks
git maintenance run

# Run when Git determines maintenance thresholds are met
git maintenance run --auto

# Run a single specific task
git maintenance run --task=commit-graph

# View help and options for the current Git version
git maintenance run --help
```

`git maintenance run` does not mean every possible task always runs. The task set depends on `maintenance.strategy`, `maintenance.<task>.enabled` settings, schedules, and passed options. If `--task=<task>` is specified, Git runs the listed tasks in order without relying on enabled flags to select them. Use `git config --show-origin --get-regexp '^maintenance\.'` to inspect the actual configuration.

In modern Git, the default strategy for manual maintenance can be `geometric`, while background schedules without a configured strategy typically run no tasks. When registering a repository with `register` or `start`, Git sets `incremental` if no strategy is already set. Because defaults and strategies can vary across versions, check the actual `maintenance.strategy` value.

### 2.1. `--auto` and maintenance thresholds

```bash
git maintenance run --auto
```

The `--auto` option tells Git to perform maintenance only when the corresponding automatic conditions/thresholds are met. This mechanism is suitable for invoking from scripts or after certain Git operations without forcing full maintenance every time.

Specific thresholds can depend on the task and Git configuration. Do not treat `--auto` as a background schedule or a guarantee that every task will run. If you need an explicit schedule, configure the schedule and use a scheduler.

### 2.2. Running tasks by schedule

Git supports `hourly`, `daily`, and `weekly` frequencies for tasks configured on those schedules:

```bash
git maintenance run --schedule=hourly
git maintenance run --schedule=daily
git maintenance run --schedule=weekly
```

The command only runs tasks configured for the selected frequency. Valid values for `maintenance.<task>.schedule` are `hourly`, `daily`, or `weekly`; if a task has no schedule configured, calling `--schedule` does not automatically assign every task to that schedule. `--auto` and `--schedule` are not used together.

## 3. Common maintenance tasks

Git includes several specialized tasks. Exact names and support may depend on the Git version; inspect `git maintenance run --help` and the `git-maintenance` documentation on the machine in use.

| Task | Primary work | Benefit |
|---|---|---|
| `commit-graph` | Writes/updates the commit-graph from reachable commits. | Speeds up certain history and ancestry traversal operations. |
| `prefetch` | Fetches data from remotes into the prefetch namespace. | Prepares remote commits/objects before the user needs them. |
| `loose-objects` | Packs loose objects into packs and cleans duplicate loose copies when appropriate. | Reduces the number of individual object files. |
| `incremental-repack` | Reorganizes pack files using an incremental repack strategy, often combined with MIDX. | Reduces small pack counts and improves object access. |
| `pack-refs` | Packs eligible refs into `packed-refs`. | Reduces the number of individual ref files. |
| `reflog-expire` | Removes reflog entries past expiration thresholds. | Reduces old reflog data; may remove an expired recovery trail. |
| `rerere-gc` | Cleans old entries in the `rerere` cache storing recorded conflict resolutions. | Reduces cache data that is no longer needed. |
| `worktree-prune` | Removes metadata for linked worktrees that are stale or corrupted. | Cleans up worktree registrations that are no longer valid. |
| `gc` | Runs garbage collection according to Git configuration. | Performs composite tasks such as repacking and pruning objects past retention limits. |

Not every version or strategy enables all tasks on the same schedule. Inspect the current configuration rather than assuming which tasks will run.

### 3.1. The `commit-graph` task

```bash
git maintenance run --task=commit-graph
```

This task updates the commit-graph for reachable commits. The commit graph helps Git avoid reading and parsing many commit objects merely to determine parent relationships or compute ancestry.

You can verify commit-graph data:

```bash
git commit-graph verify
```

The commit graph is accelerating data, not an independent history. If it is missing or needs rebuilding, Git can still read the original commit objects, though operations may be slower.

### 3.2. The `prefetch` task

```bash
git maintenance run --task=prefetch
```

Prefetch downloads info/objects from configured remotes and stores refs under the `refs/prefetch/` namespace. It helps prepare remote data for subsequent work.

Prefetch does not mean merging or pulling changes into the current working branch. It does not modify the working tree and should not be interpreted as having integrated new code into local branches.

This task requires network access and credentials for the remote. Prefetch writes refs into `refs/prefetch/`; it does not update standard remote-tracking branches or tags. In offline environments, prefetch may fail or have no new data to download. If a repository has many remotes or branches, prefetch can also consume bandwidth and disk space. You can exclude a remote from prefetch with `remote.<name>.skipFetchAll`.

### 3.3. The `loose-objects` task

```bash
git maintenance run --task=loose-objects
```

This task consolidates loose objects into a pack file and removes duplicate loose copies when appropriate. The goal is to reduce the number of individual files in the object database.

Packing does not change object OIDs. Commits and blobs retain the same logical content; only their physical storage layout is reorganized.

### 3.4. The `incremental-repack` task

```bash
git maintenance run --task=incremental-repack
```

This task reorganizes pack files incrementally instead of always repacking the entire object database into a single large pack. Git can use the multi-pack-index and a geometric strategy to reduce the number of small packs in stages.

For large repositories, incremental repacking spreads maintenance cost across multiple runs. It does not mean every object is rewritten in a single pass.

Essentially, this task uses MIDX to identify packs that can be excluded from the index, then repacks a group of smaller packs into a larger pack and updates the MIDX. Steps are split across multiple runs to reduce the duration of each batch.

### 3.5. The `pack-refs` task

```bash
git maintenance run --task=pack-refs
```

Git can store refs as individual files or consolidate many refs into `packed-refs`. This task helps reduce the number of scattered ref files. Branches and tags are still accessed by name as before; the change is mainly in how refs are stored on disk.

### 3.6. The `gc` task

```bash
git maintenance run --task=gc
```

The `gc` task invokes Git's garbage collection process according to configuration. `git gc` can repack objects, update auxiliary data, and remove unreachable objects past their retention period.

This is a task that requires greater caution when the repository is being used for data investigation or recovery. A commit reset off a branch may remain in the reflog/object database for a period; once the retention period expires and it is pruned, recovery can become difficult or impossible.

The `gc` task can combine all objects into a single large pack and take considerable time on large repositories. Do not enable the `gc` and `loose-objects` tasks simultaneously: the GC process can leave behind unreachable loose objects for a subsequent `loose-objects` pass to clean up, so running both tasks together is not recommended.

Each `git maintenance run` acquires a lock on the object database to prevent two maintenance processes from running concurrently on the same repository. However, invoking `git gc` directly does not use the same locking mechanism as `git maintenance run`. Avoid running `git gc` in parallel with maintenance; if GC is needed, prefer `git maintenance run --task=gc` so it participates in maintenance locking.

### 3.7. Auxiliary cleanup tasks

```bash
git maintenance run --task=reflog-expire
git maintenance run --task=rerere-gc
git maintenance run --task=worktree-prune
```

- `reflog-expire` removes reflog entries past expiration thresholds. If you are recovering commits, create a rescue branch/tag before letting reflogs expire.
- `rerere-gc` cleans old cache entries of the `rerere` (reuse recorded resolution) mechanism, where Git remembers conflict resolutions.
- `worktree-prune` cleans metadata for linked worktrees that no longer exist or are no longer valid. Before running, check which worktrees the team still needs.

These tasks may not be present or may behave differently in older Git versions. Check `git maintenance run --help` to confirm supported tasks.

## 4. Running maintenance manually

### 4.1. Pre-run checks

Before maintaining a repository, inspect its status and configuration:

```bash
git status --short --branch
git count-objects -vH
git config --show-origin --get-regexp '^maintenance\.'
```

- `git status` helps detect in-progress changes and merge/rebase states.
- `git count-objects -vH` reports loose object counts, pack counts, and estimated sizes.
- `git config` shows where tasks, schedules, or strategies are configured.

Maintenance normally does not modify working tree contents, but if you are handling an incident, have unreachable objects, or have other write operations on the repository, back up and understand the state before running cleanup tasks.

### 4.2. Running the needed tasks

For example, a repository with many loose objects and an outdated commit graph:

```bash
git maintenance run --task=loose-objects
git maintenance run --task=commit-graph
```

If there are many small packs, you can run incremental repack:

```bash
git maintenance run --task=incremental-repack
```

There is no need to run every task routinely after every commit. Choose tasks based on repository condition and team configuration.

### 4.3. Post-maintenance verification

```bash
git count-objects -vH
git commit-graph verify
git multi-pack-index verify
git fsck --full
git status --short --branch
```

Some verify commands are only meaningful if the repository has the corresponding commit-graph or multi-pack-index. If those index files do not yet exist, Git may report no data found to verify; that alone does not prove object database corruption.

Compare `git count-objects -vH` before and after to observe loose objects, pack count, and sizes. Do not expect every number to drop: prefetch may download more objects; repacks may temporarily use extra space; commit-graph/MIDX create additional index files.

## 5. Setting up background maintenance

For frequently used repositories, you can register the repository so Git manages periodic maintenance.

### 5.1. Registering the repository

```bash
git maintenance register
```

This command registers the current repository in the user's list of background-maintained repositories. The registration list is typically stored in global configuration under the multi-valued key `maintenance.repo`.

If `maintenance.strategy` is not yet set, `register` sets it to `incremental`. This strategy favors small, background-safe jobs: `prefetch` and `commit-graph` hourly; `loose-objects` and `incremental-repack` daily; `pack-refs` weekly; and does not schedule the `gc` task. `register` also sets `maintenance.auto=false` in local configuration to disable foreground auto-maintenance for the repository. This setting remains after `unregister`, so inspect it before changing maintenance behavior.

`maintenance.auto` controls whether certain Git commands automatically invoke `git maintenance run --auto` after writing data; the default is `true`. Therefore, after `unregister`, if you want to restore the previous auto-maintenance behavior, inspect and explicitly reset this value, for example:

```bash
git config --local maintenance.auto true
```

Check the list:

```bash
git config --global --get-all maintenance.repo
```

A user can register multiple repositories. Review the list if the scheduler is maintaining repositories that are no longer used.

### 5.2. Starting the scheduler

```bash
git maintenance start
```

This command sets up background maintenance execution using a scheduler supported by Git on the current operating system. Depending on platform and Git version, the scheduler may be based on cron, systemd, launchd, or Windows Task Scheduler.

`start` performs the same configuration updates as `register`, then creates or updates the scheduler to invoke `git maintenance run --scheduled` on schedule. Thus, you can run `git maintenance start` directly without calling `register` first; calling `register` separately is useful when you only want to add the repository to the list first.

The scheduler runs check jobs hourly; `daily` tasks run during the midnight pass and `weekly` tasks run during the corresponding pass at the start of the week. Git selects tasks based on the schedule configured for each repository. Starting the scheduler does not mean all tasks execute immediately at the moment the command is run.

You can specify a scheduler if needed:

```bash
git maintenance start --scheduler=auto
```

Modern choices include `auto`, `crontab`, `systemd-timer`, `launchctl`, and `schtasks`; supported options depend on Git version and operating system. `auto` selects the appropriate mechanism on the machine.

If you need to check scheduler choices or behavior on a specific version:

```bash
git maintenance start --help
git maintenance run --help
```

Do not manually create duplicate cron jobs or scheduled tasks if Git has already installed a user scheduler; overlapping schedules can run maintenance concurrently and waste resources unnecessarily.

### 5.3. Stopping the scheduler

```bash
git maintenance stop
```

This command stops the background maintenance mechanism set up by Git. Stopping the scheduler is different from unregistering a repository; if you want a repository removed from the maintained list, use `unregister`.

`stop` halts the background schedule Git set up for the user, so other repositories in the list will also not run on that schedule until the scheduler is restarted. It does not delete `maintenance.repo` entries.

### 5.4. Unregistering the repository

```bash
git maintenance unregister
```

This command removes the current repository from the maintenance repository list. It does not delete the repository, commits, branches, or objects. It only changes whether the scheduler maintains the repository according to the registration list.

`unregister` does not stop the scheduler and does not abort a currently running maintenance process. The scheduler continues operating for the remaining repositories in the list. If you want to stop the user's background schedule, use `git maintenance stop`; if you only want to remove one repository, use `unregister`.

### 5.5. Checking configuration status

```bash
git config --show-origin --show-scope --get-regexp '^maintenance\.'
```

The output helps inspect `maintenance.repo`, enabled tasks, schedules, and strategy if those keys are configured. Settings may come from global or local scope depending on the key; use `--show-origin` to identify the exact source.

## 6. Configuring tasks and schedules

Git lets you configure which tasks are enabled and how often they run. Keys take the form `maintenance.<task>.enabled` and `maintenance.<task>.schedule`.

### 6.1. Choosing a maintenance strategy

`maintenance.strategy` is a composite setting that determines which group of tasks is used when `--task` is not passed. Common strategies in modern Git:

| Strategy | Goal |
|---|---|
| `none` | Run no scheduled tasks; typically the default for scheduled maintenance when no strategy is configured. |
| `gc` | Run the composite garbage collection task. |
| `geometric` | Optimize packs using a geometric strategy, update auxiliary structures, and clean certain expired data; suitable for large repositories. |
| `incremental` | Run small tasks on schedule to reduce per-run cost and avoid running the `gc` task in the background schedule. |

`register` sets the strategy to `incremental` if unset. An existing configuration is preserved. Depending on the strategy and run mode (manual, auto, or scheduled), selected tasks can differ; `maintenance.<task>.enabled` and `maintenance.<task>.schedule` keys can customize selection.

With `incremental`, the recommended schedule is `prefetch` and `commit-graph` hourly; `loose-objects` and `incremental-repack` daily; `pack-refs` weekly; and the `gc` task is not scheduled. When running manual maintenance with this strategy, Git uses the `gc` task. With `geometric`, Git optimizes packs exponentially, updates auxiliary structures, and may expire reflogs or prune stale worktrees; this strategy is designed for large repositories and requires understanding its cleanup impact before use.

View the current strategy:

```bash
git config --show-origin --get maintenance.strategy
```

Do not change the strategy merely to force a single task to run. Use `--task=<task>` for specific needs; change the strategy when you want to alter the long-term maintenance policy.

### 6.2. `is-needed`: checking before running

```bash
git maintenance is-needed --auto
```

This command checks whether automatic thresholds require maintenance without running tasks yet. Exit status `0` means maintenance is needed; `1` means it is not currently needed. It is suitable for scripts deciding whether to invoke maintenance without running the full workload.

`is-needed` also understands tasks specified with `--task`. Check `git maintenance is-needed --help` if you want to combine specific tasks or use it on different Git versions.

### 6.3. Configuring tasks and schedules

Example enabling the commit-graph task at global scope:

```bash
git config --global maintenance.commit-graph.enabled true
```

Setting the schedule for the task:

```bash
git config --global maintenance.commit-graph.schedule daily
```

Valid task names and schedule values depend on the Git version. Check the `git-maintenance` documentation before configuring rarely used tasks.

You can view all related settings:

```bash
git config --show-origin --show-scope --get-regexp '^maintenance\.'
```

Do not mechanically enable every task at high frequency. For example, hourly prefetch may suit an actively developed repository on a stable network, but is unnecessary for a rarely updated repository or remotes with strict bandwidth quotas.

## 7. Distinguishing `git maintenance` from `git gc`

The two commands are related but organize work differently:

| Criterion | `git maintenance` | `git gc` |
|---|---|---|
| Goal | Coordinates multiple discrete maintenance tasks, runnable incrementally or on schedule. | Runs the composite garbage collection process. |
| Scope | Can run an individual task such as prefetch, commit-graph, loose-objects, incremental-repack, or gc. | Focuses on packing, cleaning, and optimizing the object database. |
| Background schedule | Provides register/start/stop commands for scheduler integration. | Can be invoked manually or automatically via `gc.auto` thresholds; does not set up background schedules like `maintenance start`. |
| Unreachable objects | The `gc` task can prune objects past configured retention periods. | Can prune unreachable objects past retention periods. |
| Best suited for | Periodic maintenance, spreading cost, and specialized tasks. | Comprehensive cleanup or targeted GC runs with clear understanding. |

`git gc --auto` is an automatic GC mechanism based on configured thresholds; it is not equivalent to starting a background maintenance scheduler.

## 8. Caution with unreachable objects and pruning

### 8.1. Why can GC affect recovery?

When a branch is reset or deleted, old commits may no longer be reachable from current branches/refs. However, objects may still be retained by the reflog or the grace period before pruning.

If you need to locate commits:

```bash
git reflog --all --date=iso
git fsck --full --no-reflogs --unreachable
```

Once you identify a commit to keep, create a rescue branch:

```bash
git branch rescue/recovered <commit-id>
```

Only afterward consider maintenance or pruning under policy.

### 8.2. Do not use `--prune=now` as a speedup

The command:

```bash
git gc --prune=now
```

can remove unreachable objects immediately, bypassing the normal grace period. If another Git process is creating objects and has not yet updated a ref, immediate pruning increases the risk of data loss or repository corruption.

Do not run `git gc --prune=now` or `git prune` out of habit. Use them only when you thoroughly understand the repository state, have backups, and have ensured no other process is writing to the repository.

### 8.3. Maintenance is not a tool to delete all old data immediately

Git intentionally retains certain unreachable objects for a period to support recent history-rewriting operations. Therefore, after deleting a branch or resetting, repository size may not drop immediately. This is not necessarily an error.

## 9. Monitoring size and performance

### 9.1. Counting objects and packs

```bash
git count-objects -vH
```

Common fields include:

- `count`: number of loose objects.
- `size`: size of loose objects.
- `in-pack`: number of objects in packs.
- `packs`: number of pack files.
- `size-pack`: size of packs.
- `prune-packable`: loose objects that already have corresponding copies in a pack.
- `garbage`: data not recognized as valid objects.
- `size-garbage`: size of garbage data.

These metrics help identify trends, not a single threshold proving a repository needs GC.

### 9.2. Checking packs and multi-pack-index

```bash
git multi-pack-index verify
git verify-pack -v .git/objects/pack/*.idx
```

`git multi-pack-index verify` checks the MIDX if the repository uses one. `git verify-pack` verifies the contents of the specified pack index; the `.git/objects/pack/*.idx` glob example applies to a repository with a standard `.git` directory. For linked worktrees or relocated Git directories, determine the actual path.

PowerShell does not automatically expand wildcards for native programs the way some Unix shells do. When running on PowerShell, you can list `.idx` files and invoke the command on each file:

```powershell
$packDir = git rev-parse --git-path objects/pack
Get-ChildItem -LiteralPath $packDir -Filter '*.idx' | ForEach-Object {
    git verify-pack -v $_.FullName
}
```

### 9.3. Checking the commit graph

```bash
git commit-graph verify
```

If no commit-graph exists yet, there may be no data to verify. You can generate it using the corresponding task:

```bash
git maintenance run --task=commit-graph
```

## 10. Impact on remotes, LFS, and special repositories

### 10.1. Prefetch does not replace user fetch/pull

Prefetch prepares data from remotes in a separate namespace. It does not update the checked-out branch, merge changes, or replace the review/pull workflow. Before integrating code, users still need to fetch/merge/rebase according to team workflow.

### 10.2. Git maintenance does not manage LFS server quota

Git LFS stores large contents on the LFS server. `git maintenance` optimizes the local Git object database and refs; it does not delete LFS objects on the server, does not reduce LFS storage quota, and does not replace `git lfs prune` for the local LFS cache.

Do not confuse `git gc` or `git maintenance run` with your LFS provider's retention policy.

### 10.3. Linked worktrees and submodules

Linked worktrees can share the object database with the main repository. Understand the Git directory and common directory before performing manual maintenance on physical paths.

Submodules are separate repositories. Maintaining the parent repository does not mean every submodule's object database is maintained. If a submodule is large or long-lived, inspect and maintain it separately according to project policy.

### 10.4. Shared repositories on servers

For bare repositories or repositories on servers, maintenance schedules should be managed by administrators or operations systems. Do not set up a scheduler from a personal machine if the repository is accessed by multiple processes or users over shared storage without understanding locking mechanisms and operational policies.

## 11. Sample periodic maintenance workflow

For a regularly used personal repository:

**Step 1: Check status and configuration**

```bash
git status -sb
git count-objects -vH
git config --show-origin --show-scope --get-regexp '^maintenance\.'
```

**Step 2: Register the repository**

```bash
git maintenance register
```

**Step 3: Start the scheduler**

```bash
git maintenance start
```

You can skip the separate `register` step and run `git maintenance start` directly, as `start` performs the same configuration updates as `register` before creating the background schedule.

**Step 4: When needed, run specific tasks to inspect**

```bash
git maintenance run --task=commit-graph
git maintenance run --task=loose-objects
```

**Step 5: Verify data and status**

```bash
git count-objects -vH
git commit-graph verify
git status -sb
```

**Step 6: When you no longer want the scheduler to maintain this repository**

```bash
git maintenance unregister
```

If you want to stop the user's background scheduler, use `git maintenance stop`. Distinguish stopping the scheduler from unregistering a single repository.

For large repositories or repositories with data needing recovery, back up, inspect reflogs/objects first, and choose non-pruning tasks first. Run GC only once you understand the impact and no longer need to retain unreachable objects for investigation.

## 12. Common issues

### 12.1. `git maintenance start` does not create the expected schedule

Check the Git version, supported schedulers on the OS, permissions to create background tasks, and maintenance configuration. View help with `git maintenance start --help`. Some container environments, CI runners, or machines without a suitable system scheduler may not be appropriate places for background schedules.

On Windows, Git uses Task Scheduler (`schtasks`), and tasks may briefly open a console window when running. You can inspect tasks in Task Scheduler; names typically look like `Git Maintenance (hourly)`, `Git Maintenance (daily)`, and `Git Maintenance (weekly)`. If tasks need to run when the user is logged out, the corresponding Task Scheduler option may require Windows credentials.

### 12.2. `git maintenance run` does not run the desired task

Check `maintenance.<task>.enabled`, the schedule, and the invocation. `--schedule=hourly` selects only tasks configured to run hourly; `--task=<task>` requests a specific task.

### 12.3. Prefetch does not update local branches

This is normal behavior. Prefetch only prepares data from remotes; use `git fetch` to update remote-tracking refs under standard refspecs and merge/rebase to integrate.

### 12.4. Disk usage does not decrease after maintenance

A task may create new packs or indexes, prefetch may download additional objects, and GC may keep unreachable objects during the grace period. Compare `git count-objects -vH` and inspect which data types grew rather than looking only at total size.

### 12.5. Objects disappear while recovering a repository

A prune/GC task may have removed unreachable objects. Before running maintenance on a repository under investigation, create rescue refs for commits to preserve and make a backup. If objects have been pruned from all local copies, look for backups or other clones.

## 13. Key takeaways

- `git maintenance` breaks maintenance into small tasks and supports manual or scheduled execution.
- `git maintenance run --task=<task>` runs a specific task; `--auto` runs only when automatic conditions are met.
- `commit-graph` speeds up history traversal; `prefetch` prepares remote data; `loose-objects` and `incremental-repack` organize objects/packs; `pack-refs` packs refs; `gc` performs garbage collection.
- `register` registers a repository; `start` sets up the scheduler; `stop` stops the scheduler; `unregister` removes a repository from the list.
- `git maintenance` and `git gc` are related but do not share the exact same interface or single purpose.
- Unreachable objects may be needed for recovery; create rescue branches/tags before pruning.
- Do not use `git gc --prune=now` or `git prune` out of habit, especially while other processes are writing to the repository.
- `git count-objects -vH`, `git commit-graph verify`, and `git multi-pack-index verify` help monitor and verify maintenance data.
- Prefetch does not merge code; Git maintenance does not manage LFS server quotas.
- Linked worktrees, submodules, and shared repositories must be evaluated according to their actual object database layout.

Treat `git maintenance` as a repository care schedule: select tasks based on real indicators, run them at appropriate intervals, and verify afterward. In particular, safeguarding objects needed for recovery before running GC ensures optimization never accidentally destroys data the team still needs.

## 14. References

- [Git `maintenance`](https://git-scm.com/docs/git-maintenance)
- [Git `config`](https://git-scm.com/docs/git-config)
- [Git `gc`](https://git-scm.com/docs/git-gc)
