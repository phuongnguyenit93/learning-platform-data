# Speeding up change detection with untracked cache and FSMonitor

In repositories with tens or hundreds of thousands of files, `git status` can take a long time to identify modified tracked files and find new untracked files. Two Git mechanisms that reduce repeated scanning work are the **untracked cache** and **FSMonitor**. The untracked cache remembers information about already-inspected directories; FSMonitor notifies Git of paths that have changed since the last check. When supported well by the filesystem and Git version, combining both mechanisms can make status checks substantially faster.

## 1. Why can `git status` be slow?

To determine repository status, Git must reconcile several data sources:

- **HEAD:** snapshot of the current commit.
- **Index:** list of staged files along with modes, object IDs, and necessary metadata.
- **Working tree:** files and directories currently on disk.
- **Untracked files:** files not tracked by Git that reside within the repository scope and are not ignored.

In small repositories, checking files and directories is usually fast. In large projects, file counts can grow due to dependencies, generated code, build outputs, caches, or automatically generated workspaces. Git must determine which paths have changed and which directories contain untracked files.

For example, a repository may have:

- 80,000 tracked source and asset files.
- 30,000 ignored build output files.
- 12,000 new untracked files.
- Thousands of subdirectories in the workspace.

If Git has to re-check metadata across vast numbers of directories on every `git status`, a seemingly simple operation can become a bottleneck when working in an IDE, terminal, or automation tool.

## 2. Distinguishing untracked cache and FSMonitor

The two features reduce work in two different ways:

| Mechanism | What it remembers or receives | Work reduced |
|---|---|---|
| Untracked cache | Directory metadata and information about detected untracked files | Avoids re-listing contents of unchanged directories |
| FSMonitor | List of paths changed since a monitoring checkpoint | Avoids inspecting every path when the monitor can pinpoint regions to check |

The untracked cache is cached data stored inside Git's index. FSMonitor is a mechanism for receiving change notifications from a filesystem monitor, via either Git's built-in daemon or an external monitor program. The two mechanisms complement each other: FSMonitor narrows the set of paths to inspect, while the untracked cache lets Git skip re-scanning unchanged untracked directories.

Neither mechanism replaces the index or the object database. They only help Git determine working tree state more efficiently; commit contents and version-control semantics remain unchanged.

## 3. How does the untracked cache work?

The untracked cache stores information about directories Git has already inspected for untracked files. On the next `git status`, Git can compare directory metadata—such as modification timestamps and relevant filesystem attributes—to determine whether a directory needs to be re-scanned.

If a directory has not changed according to the filesystem metadata Git relies on, Git can reuse the cached result instead of re-listing every file inside it. If a directory shows signs of change, Git re-scans that directory and updates the cache.

The untracked cache is typically helpful when:

- The repository has very many subdirectories.
- The number of untracked files to scan is large.
- Directory structure changes infrequently between `git status` runs.
- The filesystem provides reliable directory metadata.

This cache does not store file contents and does not replace checking tracked files. Git still verifies tracked files using index and stat data; the untracked cache focuses on the cost of discovering untracked files.

## 4. Filesystem requirements for the untracked cache

The untracked cache relies on the reliability of directory metadata, especially the ability to detect that a directory has changed. Some filesystems, network mounts, folder-sync tools, or external utilities may update metadata in ways Git does not expect.

If directory metadata fails to accurately reflect changes, the cache can become stale and Git risks missing new untracked files. Therefore, test support before enabling it.

Git provides the command:

```bash
git update-index --test-untracked-cache
```

This command tests whether the current filesystem meets the untracked cache's requirements. If Git reports that the filesystem is unsuitable, do not force-enable the cache merely to try speeding things up. Consider FSMonitor or reducing the scope of untracked files that need scanning.

Test results reflect only the current filesystem and environment. If the repository is moved to a different drive, mount, or CI environment, test again.

## 5. Enabling the untracked cache

After the filesystem test passes, enable the cache for the current repository:

```bash
git config --local core.untrackedCache true
```

Git will use the untracked cache when updating the index and checking status. You can verify the configuration value:

```bash
git config --show-origin --get core.untrackedCache
```

Another option is to instruct Git to enable the extension in the index:

```bash
git update-index --untracked-cache
```

This command enables the untracked cache for the current index. In normal workflows, setting `core.untrackedCache` expresses the policy more clearly and applies whenever Git updates the index.

The first run may not be noticeably faster because Git must scan and populate the cache. Run `git status` a few more times on the same repository state to evaluate the benefit.

## 6. Disabling the untracked cache when needed

If the filesystem behaves unreliably or you suspect the cache is producing inaccurate untracked results, disable it at repository scope:

```bash
git config --local core.untrackedCache false
```

You can strip the extension from the index with:

```bash
git update-index --no-untracked-cache
```

After disabling it, re-run status and verify untracked files appear properly:

```bash
git status --short --untracked-files=all
```

Do not confuse disabling the untracked cache with skipping untracked file detection. They are different: the cache changes how Git performs the check, whereas `--untracked-files=no` tells `git status` not to list untracked files for that run.

## 7. What is FSMonitor?

FSMonitor is an interface for Git to receive notifications about paths that have changed in the working tree since a previous monitoring checkpoint. Instead of inspecting every file and directory itself, Git queries the monitor for changes that occurred and focuses inspection on the relevant paths.

Notification sources can be:

- **Built-in FSMonitor daemon:** a daemon provided by Git on supported platforms and versions.
- **External FSMonitor hook:** an external program, such as a filesystem watcher configured by an organization or developer tooling.

FSMonitor does not decide on its own how file contents changed. It tells Git which paths to check; Git still compares metadata and contents as needed to determine the exact status.

FSMonitor is particularly useful in large repositories where most files do not change between `git status` runs, yet the total number of tracked paths is very high.

## 8. Enabling the built-in FSMonitor daemon

On Git versions and platforms supporting built-in FSMonitor, enable it via repository configuration:

```bash
git config --local core.fsmonitor true
```

Check daemon status:

```bash
git fsmonitor--daemon status
```

You can start the daemon explicitly:

```bash
git fsmonitor--daemon start
```

On supported environments, Git can auto-start the daemon when needed; the `start` subcommand lets you proactively inspect and launch it. Verify status after enabling:

```bash
git fsmonitor--daemon status
git status --short
```

Built-in daemon support depends on Git version, operating system, and filesystem type. If the daemon command is unsupported in your current environment, upgrade Git according to organizational policy or use a verified external monitor.

## 9. Using an external FSMonitor hook

`core.fsmonitor` can also take a path or command for an external monitor program. Git invokes that program using the FSMonitor protocol to receive information about changed paths.

In configuration, the boolean value `true` requests the built-in monitor if supported; a command/path value specifies an external monitor. General configuration example:

```bash
git config --local core.fsmonitor /path/to/fsmonitor-hook
```

Do not copy this example path literally. Use the setup command provided by your official monitoring tool and inspect the script contents before enabling it. An external monitor is a program executed by Git, so treat it as an executable running with the privileges of the active user account.

Avoid configuring both the built-in daemon and an external hook with conflicting values across scopes. Inspect configuration origin:

```bash
git config --show-origin --show-scope --get core.fsmonitor
```

If multiple values come from global and local scopes, determine the final effective value before making adjustments.

## 10. Disabling FSMonitor

To disable FSMonitor configuration in the current repository:

```bash
git config --local --unset core.fsmonitor
```

If the configuration was set globally or system-wide, the command above only removes the local value; check configuration origin before modifying other scopes. For the built-in daemon, you can stop the process:

```bash
git fsmonitor--daemon stop
```

Then verify Git is no longer using an unintended monitor:

```bash
git config --show-origin --show-scope --get core.fsmonitor
git status --short
```

Note that `--unset` returns a non-zero exit code if the key does not exist at the specified scope. That does not necessarily indicate a repository error; check the actual configuration.

## 11. Combining untracked cache and FSMonitor

Both mechanisms can work together. A typical workflow on a supported filesystem:

```bash
git update-index --test-untracked-cache
git config --local core.untrackedCache true
git config --local core.fsmonitor true
git status
```

When running `git status`, Git can use FSMonitor to learn which paths changed, and then use the index and untracked cache to avoid re-scanning directories without relevant changes.

Results are usually clearest in repositories with many files where only a small fraction change between checks. For small repositories, the overhead of starting or maintaining a monitor may yield no noticeable difference.

You do not need to enable both in every project. Measure performance first, enable one mechanism at a time, verify correctness, and only then combine them to see where gains come from.

## 12. Measuring effectiveness before and after enabling

Do not rely on gut feeling alone. Measure the same command on the same repository and identical working state.

In Bash or Git Bash:

```bash
time git status --short --untracked-files=all
```

In PowerShell:

```powershell
Measure-Command { git status --short --untracked-files=all | Out-Host }
```

Measurement procedure:

1. Choose a repository with a representative workload, especially untracked file count and subdirectories.
2. Run the command several times with features disabled and record the timings.
3. Enable the untracked cache, run several times so the cache populates, and record timings.
4. Disable or keep the untracked cache, enable FSMonitor, and re-measure.
5. Enable both and take a final measurement.
6. Compare median timings rather than picking only the fastest run.

Keep the working tree in the exact same state across measurement runs. If many files are added or deleted between runs, results are no longer directly comparable. The first run after enabling a monitor may be slower while the daemon starts or the cache builds.

Example measurement table:

| Configuration | Run 1 | Run 2 | Run 3 | Notes |
|---|---:|---:|---:|---|
| Default | 2.8 s | 2.6 s | 2.7 s | Baseline |
| Untracked cache | 1.7 s | 1.1 s | 1.0 s | Subsequent runs cut directory scan time |
| FSMonitor | 1.0 s | 0.8 s | 0.8 s | Only inspects paths reported changed by monitor |
| Both | 0.6 s | 0.5 s | 0.5 s | Can further reduce repeated work |

The numbers above illustrate how to record results, not guaranteed numbers for every machine or repository.

## 13. The `--untracked-files` option and its impact on results

`git status` can alter the scope of untracked file scanning via an option:

| Option | Meaning |
|---|---|
| `--untracked-files=no` or `-uno` | Do not list untracked files |
| `--untracked-files=normal` or `-unormal` | List directories containing untracked files rather than every file inside; this is the common default |
| `--untracked-files=all` or `-uall` | List every untracked file individually |

Examples:

```bash
git status --short --untracked-files=no
git status --short --untracked-files=normal
git status --short --untracked-files=all
```

`-uno` can make the command return faster because Git does not have to report untracked files, but you will not see new untracked files. This option alters displayed information rather than providing cache optimization equivalent to the untracked cache or FSMonitor.

When testing untracked cache performance, keep the same `--untracked-files` value across runs. If one run uses `no` and another uses `all`, results cannot be compared fairly.

## 14. Limitations and cases requiring caution

### Untracked cache

- Depends on directory metadata and filesystem behavior; some filesystems or mounts do not meet the requirements.
- The cache takes time to populate, so the initial run may not be faster.
- If the repository is moved across different filesystems or environments, re-verify suitability.
- Does not replace checking tracked files and does not reduce repository disk size.

### FSMonitor

- Requires a daemon or external monitor compatible with Git and the filesystem.
- The monitor may be unavailable in certain environments, network filesystems, or special workspaces.
- When the monitor stops, loses state, or cannot supply reliable information, Git must fall back or trigger a re-scan to guarantee accurate results.
- An external hook is an executable program; use tools only from trusted sources.
- Some CI environments use short-lived workspaces created and destroyed continuously; monitor startup overhead may not pay off over job runtime.

If you suspect Git missed a change, disable each feature and re-run `git status` to compare. Do not proceed with commits or decisions based on inaccurate status.

## 15. Troubleshooting unexpected results

Check configuration and daemon status:

```bash
git config --show-origin --show-scope --get core.untrackedCache
git config --show-origin --show-scope --get core.fsmonitor
git fsmonitor--daemon status
```

If a new untracked file does not appear:

1. Verify the file is not ignored using `git check-ignore -v path/to/file`.
2. Run `git status --short --untracked-files=all`.
3. Temporarily disable untracked cache and FSMonitor at repository scope and re-run.
4. If status is accurate only after disabling the cache, inspect filesystem behavior and file-sync utilities.
5. If using an external monitor, check that tool's logs and protocol responses.

If a recently edited tracked file is not detected by `git status`, inspect monitor and stat behavior. Try disabling FSMonitor first to isolate whether the issue involves the monitor. On filesystems with coarse timestamp resolution or tools that update metadata unusually, evaluate appropriate Git settings rather than assuming caches are always accurate.

To disable both in the current repository while investigating:

```bash
git config --local core.untrackedCache false
git config --local --unset core.fsmonitor
git update-index --no-untracked-cache
git status --short --untracked-files=all
```

Once normal output is confirmed, you can re-enable each feature individually if supported by the environment. Do not delete the index or `.git` directory to troubleshoot cache issues.

## 16. Recommended workflow for large repositories

1. Time `git status --short --untracked-files=all` in the default state.
2. Run `git update-index --test-untracked-cache` to verify the filesystem.
3. If it passes, enable `core.untrackedCache` at local scope.
4. Enable built-in FSMonitor if supported by your Git version and platform; if using an external monitor, verify its source and command configuration.
5. Re-measure the same workload, record medians, and verify both tracked and untracked status detection.
6. Test common operations such as `git status`, `git add`, checkout/switch, and file edits inside the IDE.
7. If results are inconsistent, disable the relevant feature and investigate the filesystem/monitor before continuing.
8. Include settings in team guidelines only after validating them across the operating systems and filesystems the team actually uses.

## 17. Key takeaways

The untracked cache avoids re-listing unchanged directories by storing directory information in the index; FSMonitor notifies Git of changed paths to narrow the inspection scope. The two mechanisms can work together, though they depend on compatible filesystems, daemons, or monitors. Run `git update-index --test-untracked-cache`, enable settings at an appropriate scope, benchmark identical workloads before and after, and verify `git status` accuracy. Whenever you suspect a cache or monitor is missing changes, disable it to cross-check before continuing work.
