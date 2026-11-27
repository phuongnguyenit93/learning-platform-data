# Measuring size and object counts with git count-objects

As a Git repository grows, you need to know how much disk space the data occupies and how it is stored before deciding on maintenance. Git can store objects individually (*loose objects*) or group multiple objects into packfiles (*packed objects*). The `git count-objects` command reports the counts and sizes of these object groups, helping you observe the state of the object database without modifying the repository.

The most commonly used command is `git count-objects -vH`. The `-v` option displays detailed counters, while `-H` formats sizes in human-readable units. The output helps identify whether a repository has many loose objects, many packfiles, loose objects duplicated in packfiles, or garbage data that requires investigation.

## 1. What does the Git object database store?

Git stores content and history using objects. The four basic object types are:

- **Blob:** the contents of a file.
- **Tree:** directory structure, path names, and references to blobs or subtrees.
- **Commit:** tree snapshot, parent commits, author, committer, and commit message.
- **Tag object:** metadata and signature of an annotated tag.

These objects are stored in the object database, typically located at `.git/objects` for a standard repository. Git can store objects in two primary ways:

### Loose objects

A loose object is an object stored as an individual file in a directory structure based on the first two characters of its OID. For example, an object whose OID starts with `ab` is placed in the `objects/ab/` directory with the remaining characters of the OID as its filename. Object content is compressed to save space.

Loose objects typically appear after creating commits, adding content, or receiving data from a remote. Git can keep many loose objects until a repack or garbage collection process consolidates them.

### Packed objects

When there are many objects, Git can group them into a packfile to save space and reduce the number of filesystem files. A packfile typically consists of a `.pack` data file and a `.idx` index file for fast object lookup. Git can use delta compression to store differences between related object versions.

A repository can simultaneously contain loose objects and multiple packfiles. This is a normal state; having loose objects does not mean the repository is broken or needs immediate cleanup.

## 2. Basic syntax of git count-objects

Run the command from any directory inside the repository:

```bash
git count-objects
```

The command reports the number of loose objects and the size of loose objects in KiB. To view additional information about packfiles, duplicate objects that can be pruned, and garbage data:

```bash
git count-objects -v
```

To display sizes in human-readable units:

```bash
git count-objects -vH
```

`-H` is the short form of `--human-readable`. The output may use `KiB`, `MiB`, `GiB`, or another appropriate unit. If you need to compare values via a script, use the numeric output without `-H` to avoid parsing unit strings.

## 3. Reading fields in verbose output

Example output:

```text
count: 125
size: 812
in-pack: 15230
packs: 3
size-pack: 46120
prune-packable: 12
garbage: 0
size-garbage: 0
```

When run with `-H`, size fields are displayed in human-readable form, such as `812.00 KiB` or `45.04 MiB`. Meaning of the fields:

| Field | Meaning |
|---|---|
| `count` | Number of loose objects in the object directory being inspected |
| `size` | Size of loose objects, in KiB if `-H` is not used |
| `in-pack` | Number of objects stored in packfiles |
| `packs` | Number of existing packfiles |
| `size-pack` | Size of packfiles, in KiB if `-H` is not used |
| `prune-packable` | Number of loose objects that already have a corresponding copy in a packfile and can be removed from loose storage during appropriate cleanup |
| `garbage` | Number of files in the object directory that are neither valid loose objects nor valid packfiles |
| `size-garbage` | Size of files classified as garbage, in KiB if `-H` is not used |

The values are point-in-time metrics at the moment the command runs. The repository can change immediately afterward due to commits, fetches, repacks, maintenance, or other operations.

## 4. Distinguishing object counts and sizes

`count` and `in-pack` are two counters for two different storage formats. You should not mechanically add them together to conclude how many unique objects exist or how many objects are still referenced by current history.

An object can exist as a loose object while simultaneously having a copy in a packfile. The `prune-packable` field indicates the number of loose objects that have a corresponding copy in a pack, meaning the loose copies can be cleaned up once the pack is confirmed to hold those objects. Therefore, if you see `count` is 125 and `prune-packable` is 12, 12 of the loose objects already have corresponding packed copies.

`in-pack` is also not the number of objects reachable from the current branch. A packfile can contain objects no longer referenced by current branches or tags, such as objects left behind after rewriting history or deleting branches. `git count-objects` focuses on measuring object storage, not fully analyzing the reachability of every object.

If you need to determine which objects are still referenced or unreachable, combine other commands such as `git rev-list`, `git fsck`, and reflog checks. Do not rely solely on totals from `count-objects` to conclude that a repository has redundant data.

## 5. Is an increase in loose objects a problem?

Loose objects are a normal part of Git operations. After creating commits, Git typically writes new objects in loose form. When the repository accumulates many objects or reaches a maintenance point, Git can group them into packfiles.

Signs worth observing:

- `count` increases continuously after many commit or fetch operations.
- `size` grows rapidly compared to the expected source code size.
- `prune-packable` is large, indicating many loose objects already have copies in packfiles.
- Many small packfiles exist after repeated fetches or updates.

These signs do not automatically mean the repository is broken. Compare them over time and in context. For example, fetching a large branch can significantly increase object counts; a repack can reduce loose objects while changing pack size or pack count in other ways.

To track trends, run the same command before and after fetch, merge, or maintenance:

```bash
git count-objects -vH
```

Record the results along with the timestamp and the operation just performed. Consistent comparison is more useful than a single number.

## 6. Understanding the prune-packable field

`prune-packable` is an important field when evaluating object storage status. It counts loose objects that already have a corresponding copy in a packfile. If an object is already in a pack, the individual loose copy is generally no longer needed for reading that object.

Example:

```text
count: 500
in-pack: 12000
prune-packable: 430
```

There are 500 loose objects, of which 430 already have copies in a packfile. This can happen after Git repacks objects while the duplicate loose copies have not yet been cleaned up.

Git provides `git prune-packed` to delete loose objects that already exist in a pack. However, regular users do not need to run this command manually after every measurement. Maintenance processes and `git gc` can perform appropriate cleanup. If you want to run it, make sure you know whether another Git process is actively using the repository and follow your project's maintenance policy.

Do not confuse `prune-packable` with the number of unreachable objects. These are objects that have duplicate copies in a pack, not a conclusion about whether an object is still used by a commit or ref.

## 7. Understanding the garbage and size-garbage fields

`garbage` counts files in the object directory that are not recognized as valid loose objects or valid packfiles. `size-garbage` reports the size of those files.

Example:

```text
garbage: 2
size-garbage: 4096
```

This indicates there are two files classified as garbage with a total size of 4096 KiB. They could be leftover temporary files, corrupted files, malformed files, or data created by an interrupted process.

Do not manually delete files simply because `garbage` is non-zero. First, identify the specific files and what created them. Some Git operations might be in progress or recently interrupted; deleting the wrong file in the object directory can corrupt repository data.

To investigate further, locate the object directory:

```bash
git rev-parse --git-path objects
```

Then inspect the file listing using an appropriate filesystem tool. Do not manually edit object contents, packfiles, or index files. If you suspect the object database is inconsistent, use `git fsck --full` to check integrity and back up the repository before taking corrective action.

## 8. Using metrics to evaluate packfiles

The `packs` and `size-pack` fields help observe the number of packfiles along with packed data size. Many small packfiles can appear after repeated fetches, pushes, or before maintenance consolidates them. However, a large pack count is not automatically an error; Git can manage multiple packs by design, including cruft packs and specialized packs depending on version and configuration.

Example:

```text
in-pack: 250000
packs: 18
size-pack: 840.00 MiB
```

The repository has 250,000 objects in packfiles and 18 packfiles with a packed size of about 840 MiB. If Git operations remain fast and disk usage is acceptable, no intervention may be needed. If the pack count grows excessively, fetches become slow, or size increases abnormally, inspect more details from `git maintenance`, `git gc`, or packfile analysis before deciding.

`size-pack` is the pack size reported by Git; it is not the total size of the entire `.git` directory. Components such as pack indexes, commit-graph, multi-pack-index, reflogs, config, refs, hooks, and LFS data may fall outside this figure.

## 9. Measurement workflow before and after maintenance

`git count-objects` is an observation command. It does not repack, prune, delete files, or alter commits. You can use it as a baseline measurement before and after a maintenance operation.

Example workflow:

```bash
# 1. Check repository status.
git status --short --branch

# 2. Measure object storage before maintenance.
git count-objects -vH

# 3. Check Git version and maintenance status if needed.
git --version
git maintenance run --auto

# 4. Measure again after the operation.
git count-objects -vH
```

`git maintenance run --auto` may decide to execute certain maintenance tasks depending on configuration and thresholds. It is included in the example to illustrate before/after measurement; there is no need to run it just because `count` is large. In production environments or shared repositories, follow the maintenance schedule and operational policies.

If you need to run manual garbage collection, `git gc` can consolidate objects and clean up data according to Git's rules. Read the command documentation and evaluate the impact before running it; `git count-objects` does not require running `git gc` after every measurement.

## 10. What git count-objects does not measure

The output of `git count-objects` is not the total size of the working directory or the entire repository on disk. It focuses on the object database and the object file groups the command recognizes.

Components that cannot be fully inferred from this output alone include:

- **Working tree:** files currently checked out in the project directory.
- **Index:** staging area data.
- **Refs and reflogs:** branch/tag names and ref update history.
- **Other metadata:** commit-graph, multi-pack-index, configuration, hooks, and auxiliary files.
- **Git LFS:** LFS content is stored in a separate store, usually under `.git/lfs/objects`, rather than as regular blobs in the Git object database.
- **Submodules:** each submodule is a separate repository with its own object database.
- **Alternate object database:** a repository may use objects from another store; you must understand the alternate configuration when interpreting metrics for the current object directory.

If your goal is to measure the total size of `.git` or the repository directory, use filesystem tools to measure the corresponding directory. If you need to measure LFS separately, use `git lfs` commands and inspect LFS storage. Do not add metrics from different sources together without clearly determining whether they overlap.

## 11. Combining with other inspection commands

`git count-objects` answers high-level questions about object counts and sizes. When detailed investigation is needed, combine the following commands:

| Need | Command | Role |
|---|---|---|
| Check object database format | `git count-objects -vH` | Measure loose/packed objects and sizes |
| Check object integrity | `git fsck --full` | Detect corrupted, missing, or unreachable objects within the check scope |
| View commit history | `git log --oneline --all --decorate` | Understand which branches/refs hold which history |
| View object database path | `git rev-parse --git-path objects` | Identify where Git stores objects |
| View object type and content | `git cat-file -t <oid>` / `git cat-file -p <oid>` | Inspect a specific object |
| Analyze packfile | `git verify-pack -v <pack-index>` | View objects in a pack along with size/delta info |

For example, when pack size spikes unexpectedly, you can start with:

```bash
git count-objects -vH
git log --oneline --all --decorate -20
git fsck --full
```

If you need to find the largest blobs, you must analyze the object list and their sizes; `git count-objects` does not tell you which files take up the most space. An analysis workflow can use `git rev-list --objects --all` combined with `git cat-file --batch-check` or specialized tools to rank blobs.

## 12. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| `git count-objects` reports total repository size | The command measures object groups in the object database; it excludes the full working tree, LFS, and other metadata |
| `count + in-pack` is always the unique object count | Loose objects can already exist in a pack; `prune-packable` reflects this overlap |
| Many loose objects mean the repository is corrupted | Loose objects are a normal storage state and can be packed during maintenance |
| `prune-packable` is the number of unreachable objects | It is the number of loose objects with corresponding copies in a pack, not a reachability measurement |
| Non-zero `garbage` means files can be deleted immediately | Identify the file source and inspect the object database before cleaning up |
| `-H` makes measurements more accurate | `-H` only changes size formatting to human-readable units |
| Running `git count-objects` cleans the repository | It is a measurement command and does not automatically repack or prune objects |
| Pack size is the total size of `.git` | Packs are one part of repository metadata; many other directories and files exist |

## 13. Key takeaways

To quickly inspect object storage, use:

```bash
git count-objects -vH
```

Read `count` and `size` for loose objects; `in-pack`, `packs`, and `size-pack` for packed data; `prune-packable` for loose objects that already have copies in a pack; and `garbage` and `size-garbage` for files not recognized as valid objects or packs.

Use these metrics as indicators to track trends rather than treating an isolated value as proof that the repository needs cleanup. `git count-objects` does not delete data and does not measure the total size of the working tree, Git LFS, or all metadata. When deciding on maintenance, combine the results with repository status, history, `git fsck`, and appropriate analysis tools.
