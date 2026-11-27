# Repacking objects with repack and space-vs-time tradeoffs

Git stores repository contents as objects such as blobs, trees, commits, and tags. When newly created, many objects may exist individually in the object database as **loose objects**. As a repository grows, Git consolidates objects into **packfiles** to reduce storage overhead and transfer data more efficiently. The `git repack` command performs this repacking and can also reorganize how objects are compressed and share data.

Repacking changes how Git stores objects on disk; it does not rewrite commit contents or alter commit OIDs. Choosing repack settings involves tradeoffs: searching harder for deltas generally saves more space but consumes more CPU, memory, and time; deeper delta chains can reduce size but require extra work when reconstructing objects.

## 1. Loose objects and packfiles

When Git creates an object, it is stored in the object database. In a repository using the traditional file backend, new objects typically start as loose objects in the `objects` directory, compressed individually. When there are many objects, Git can pack them into packfiles.

| Storage format | Organization | Characteristics |
|---|---|---|
| Loose object | Each object has its own file named by OID | Easy to write new objects, but file counts can grow very large |
| Packfile | Many objects written sequentially into one `.pack` file | Reduces file overhead and supports delta compression between similar objects |
| Pack index | `.idx` file paired with a pack | Maps OIDs to object offsets inside the pack for fast lookup |
| Reverse index | Optional `.rev` file | Maps pack offset order back to object order, useful for certain pack traversal operations |
| Bitmap index | Optional `.bitmap` file | Stores reachability information to speed up operations such as clone and fetch |

The object database path can vary, especially in linked worktrees or repositories using a common directory. Use Git commands to locate it rather than assuming `.git` is always a directory:

```bash
git rev-parse --git-path objects
git rev-parse --git-path objects/pack
```

A packfile is not a standalone backup. Git still needs refs and the object database to determine which objects are in use. The `.idx` file enables locating objects inside `.pack`; if the index is missing, Git can rebuild it in some situations, but you should not manually delete or edit pack files.

## 2. How does delta compression save space?

Many objects in a repository have nearly identical content. For example, a source file edited over many commits may keep most of its old lines and change only a few sections. A packfile can store an object as a **delta** against a base object instead of storing the full content again.

Simple illustration:

```text
Blob A: [header][old logic][footer]
Blob B: [header][new logic][footer]
                     |
                     +-- delta: replace old logic with new logic
```

When Git needs to read Blob B, it retrieves the base and applies the delta to reconstruct the full content. A delta can reference its base object by offset within the same pack (`OFS_DELTA`) or by OID (`REF_DELTA`). Users work with the reconstructed objects; delta details are an underlying pack storage mechanism.

Delta compression can dramatically reduce pack size, especially in repositories with many versions of the same file or many similar files. However, Git must search for suitable base objects and may need to apply multiple delta layers when reading an object.

## 3. What does `git repack` do?

`git repack` reads objects from the object database, selects the set of objects to pack, creates a new packfile, and optionally deletes old packs that have become redundant. The command can:

- Consolidate loose objects into a packfile.
- Combine multiple small packs into a larger pack.
- Re-evaluate delta bases to improve compression.
- Generate a bitmap index for workloads that need fast reachability computation.
- Pack unreachable objects separately into a cruft pack to manage their lifecycle.

A common example to pack all objects reachable from refs into a pack and delete old packs that have been superseded:

```bash
git repack -a -d
```

Where:

- `-a` instructs Git to pack referenced (reachable) objects into a new pack.
- `-d` deletes old packs once their objects are superseded by the new pack, and cleans up loose objects already contained in the pack.

This command does not mean deleting all unreachable objects. If old packs still contain unreachable objects, Git handles them according to the applicable rules; you can use `--cruft` or `-A` depending on your goal. Do not manually delete old packs to try to free disk space.

Repacking does not alter commit history in Git's model: commit, tree, and blob OIDs remain unchanged. It changes the location and encoding of objects on disk. The working tree and current branch are not changed merely by running repack.

## 4. Measuring object database state before repacking

Before optimizing, record loose object counts, pack counts, and current disk usage:

```bash
git count-objects -vH
```

Common fields:

| Field | Meaning |
|---|---|
| `count` | Number of loose objects |
| `size` | Size of loose objects |
| `in-pack` | Number of objects inside packs |
| `packs` | Number of existing packfiles |
| `size-pack` | Size of packfiles |
| `prune-packable` | Number of loose objects that already exist in a pack and can be cleaned up |
| `garbage` / `size-garbage` | Files not recognized as valid objects and their corresponding size |

The output serves as a baseline for comparison after repacking. The reported size is the object database size recognized by Git; it excludes the full working tree, application logs, build artifacts, or external backups.

Inspect existing packs:

```bash
git verify-pack -v <pack-index-path>
```

Replace `<pack-index-path>` with the actual `.idx` file path in the pack directory. Detailed output can show OIDs, object types, unpacked object sizes, packed data sizes, offsets, and delta depths. The summary line reports object counts and pack size statistics.

If you need to check object database integrity, run:

```bash
git fsck --full
```

`git fsck` verifies object links and validity. It is a diagnostic step separate from repacking; repacking does not repair corrupted object contents or replace backups.

## 5. Packing for different goals

### Packing all reachable objects

```bash
git repack -a -d
```

Use this when you want to consolidate reachable objects into a new pack and remove redundant old packs. On large repositories, the operation can read and write substantial data and requires temporary free disk space while creating the new pack.

### Packing new objects incrementally

```bash
git repack -d
```

Without `-a`, Git can pack loose objects not yet in a pack and clean up redundant packs within the selected scope. This approach generally fits incremental maintenance, avoiding rewriting a single pack from the entire history.

### Keeping unreachable objects as loose objects

```bash
git repack -A -d
```

`-A` behaves similarly to `-a`, except unreachable objects in old packs are unpacked into loose objects instead of being removed with the old pack. This option is useful when you want to replace packs while retaining unreachable objects to leave time for inspection or recovery. It does not mean unreachable objects are kept forever; they can still be cleaned later according to prune policies and retention periods.

### Packing unreachable objects using a cruft pack

```bash
git repack -d --cruft
```

A cruft pack is a pack dedicated to unreachable objects. It manages these objects separately from packs holding reachable objects while storing metadata needed for Git to apply expiration policies. When using `--cruft-expiration=<date>`, Git can drop unreachable objects older than the chosen cutoff; use this only when you understand its effect on recoverability.

Unreachable objects may still be needed after a reset or rebase. Before setting short expiration cutoffs or cleaning cruft, check reflogs, backups, and commits you need to preserve.

## 6. Delta window and delta depth

Two important parameters directly affecting compression are `--window` and `--depth`.

| Parameter | Meaning | When increasing the value |
|---|---|---|
| `--window=<n>` | Number of candidate objects Git examines in the delta base search window | Greater chance of finding a closer base; typically uses more CPU and memory |
| `--depth=<n>` | Maximum depth of a delta chain | Allows longer delta chains; can reduce size but increases object reconstruction cost |

Example requesting a wider search window and allowing deeper delta chains:

```bash
git repack -a -d --window=100 --depth=50
```

Larger values are not always better. If objects lack similar bases, a larger window can spend extra time without shrinking the pack significantly. Overly deep delta chains can cause object reads or history traversal to consume more CPU.

### Example recomputing compression from scratch

```bash
git repack -a -d -f --window=100 --depth=50
```

`-f` tells Git not to reuse existing deltas when building the pack, so Git computes fresh deltas using the current parameters. This can improve compression if old packs were built with a small window, though it usually takes significantly longer. Do not run it routinely unless metrics show the current packs need optimization.

## 7. CPU, memory, and thread count

Repacking can use significant CPU during delta search and object compression. The `--threads=<n>` parameter controls the number of compression threads in multi-threaded phases:

```bash
git repack -a -d --threads=4
```

More threads can shorten runtime on machines with spare CPU cores, but also increase CPU and memory usage. If the machine is running an IDE, builds, or local databases, multi-threaded repacking can slow down interactive tasks.

`--window-memory=<n>` limits the memory used for the delta search window as supported by Git. Window size, window memory, and thread count should be balanced together; increasing all of them at once can raise RAM consumption substantially.

Start with defaults or a moderate thread count, measure runtime and post-repack size, and only then tune parameters upward. If a repository is large and the machine has limited RAM, a slower but stable repack may be preferable to an overloaded run.

## 8. Limiting pack size and pack count

`--max-pack-size=<n>` sets a size cap on generated packs. With a smaller cap, Git can produce multiple packs instead of one large pack:

```bash
git repack -a -d --max-pack-size=2g
```

Splitting packs can be helpful in environments with file size limits or when managing data in batches. However, too many packs increase the number of indexes to search and can add overhead to object operations. When a repository retains multiple packs, the Multi-Pack Index (MIDX) enables OID lookup across multiple packs without opening each index independently.

Inspect or build a multi-pack-index:

```bash
git multi-pack-index write
git multi-pack-index verify
```

MIDX does not merge packs into a single pack; it creates a shared index so Git can locate objects across the existing set of packs. When optimizing pack counts, look at Git's incremental repack and automated maintenance tasks rather than deleting packs arbitrarily.

## 9. Bitmap indexes and clone/fetch speed

A pack can be accompanied by a bitmap index so Git can determine the set of objects reachable from refs faster during certain data transfer operations. Bitmaps are especially helpful on server repositories handling many clones or fetches.

You can request bitmap generation during a repack:

```bash
git repack -a -d --write-bitmap-index
```

Bitmaps require additional storage space and computation time to generate. Not every repository configuration or pack layout supports bitmaps the same way; Git imposes conditions and limits depending on version, object types, and configuration. Inspect the results and measure actual fetch/clone performance.

Bitmaps speed up reachability calculations when generating packs for transfer; they do not automatically make working tree operations or regular file reads faster.

## 10. Geometric repacking and incremental maintenance

A repository with many packs does not necessarily need to merge all of them into a single pack during every maintenance run. Geometric repacking selects a subset of small packs to consolidate so that pack sizes follow an exponential progression, avoiding repeatedly rewriting the largest pack.

Example:

```bash
git repack --geometric=2 -d
```

A larger geometric factor keeps more small packs and reduces the amount of data repacked each run, at the cost of Git managing more packs. A smaller factor merges more packs, reducing pack count while requiring more I/O per maintenance run.

For large repositories, Git also supports incremental maintenance and Multi-Pack Index. Depending on version, you can run the incremental repack task via:

```bash
git maintenance run --task=incremental-repack
```

This task commonly works alongside MIDX to merge small packs in batches. It reduces the cost of a long full repack, especially when a repository receives objects continuously.

## 11. Space-vs-time tradeoff table

| Choice | Pack size | Repack time | Read / transfer cost |
|---|---|---|---|
| Small window | Likely larger due to fewer base candidates | Usually faster | Fewer optimized deltas; larger packs may increase data transferred |
| Large window | Potentially smaller if good bases are found | Uses more CPU | May reduce transfer size; effectiveness depends on object structure |
| Low depth | Likely larger due to shorter delta chains | Usually easier to generate | Fewer layers to reconstruct objects |
| High depth | Potentially smaller | May spend more time finding and building deltas | May use more CPU when reconstructing objects |
| Many threads | Does not directly guarantee smaller packs | Can be faster on multi-core CPUs | Increases CPU/RAM contention if running alongside other tasks |
| Many small packs | Typically adds index/pack overhead | Partial repacks can be lighter | MIDX aids lookup; without MIDX, many packs increase object lookup cost |
| One large pack | Can reduce overhead and optimize global deltas better | Full repack can be slow and I/O-heavy | Convenient for transfers, though updating a large pack is resource-intensive |
| Bitmap index | Slightly increases metadata size | Adds bitmap generation time | Can accelerate reachability checks during clone/fetch |

No single configuration is optimal for every repository. Repositories storing many similar text files can benefit from a larger window; repositories containing many already-compressed binary files usually gain little from delta compression. Measure real data rather than increasing parameters by guesswork.

## 12. Controlled repack workflow

A safe workflow before and after repacking:

```bash
# 1. Check working status
git status --short

# 2. Record size and object counts before repacking
git count-objects -vH

# 3. Check the object database if diagnosing anomalies
git fsck --full

# 4. Pack reachable objects and remove redundant packs
git repack -a -d

# 5. Re-measure after repacking
git count-objects -vH

# 6. Verify the new pack if needed
git verify-pack -v <pack-index-path>
```

Compare `size-pack`, `packs`, `in-pack`, and runtime before and after. If the goal is faster clone/fetch, measure the transfer operations too; if the goal is saving disk space, compare object database sizes on the same repository and identical ref state.

Repacking can require free disk space to keep old packs while writing the new pack. On large repositories, schedule it during low-activity periods, ensure sufficient disk space, and avoid running competing maintenance processes simultaneously. Git uses locks to protect many internal operations, but you should not rely on locks to justify manually deleting or editing pack files.

## 13. When to use `git gc` instead of invoking repack directly?

`git gc` is a high-level maintenance command that can run repacking alongside other cleanup tasks such as pruning expired objects, updating metadata, and optimizing the repository. Git also provides auto-maintenance mechanisms when certain thresholds are reached.

```bash
# Run general maintenance according to Git policy
git gc

# Request automatic maintenance if needed
git gc --auto

# View related maintenance configuration
git config --show-origin --get gc.auto
git config --show-origin --get maintenance.auto
```

`git gc` is not merely an alias for `git repack -a -d`: it can perform additional object and metadata management steps. If you specifically need to tune compression or delta behavior, use `git repack` with explicit parameters. For routine maintenance, prefer Git's default mechanisms or a team-agreed `git maintenance` schedule.

Do not use `git gc --prune=now` as a routine disk-cleanup command. This parameter can remove unreachable objects immediately, eliminating the chance to recover commits just reset or rebased. Only prune when you have confirmed objects are no longer needed and no active operations in the repository rely on them.

## 14. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Repack recreates commits and changes OIDs | Repack changes how objects are stored on disk; commit/tree/blob OIDs do not change. |
| `git repack -a -d` deletes all unreachable objects | It packs reachable objects and deletes redundant packs; unreachable objects must be handled under their own policy. |
| Larger window is always better | A larger window checks more bases but uses more CPU/RAM and does not guarantee a smaller pack. |
| Higher depth always makes Git faster | Deep delta chains can save space but increase object reconstruction cost. |
| More threads always reduce total runtime | Effectiveness depends on CPU, RAM, I/O, and concurrent workloads. |
| `.idx` contains object contents | `.idx` maps OIDs to offsets in `.pack`; object data lives in the packfile. |
| Bitmaps make every Git command faster | Bitmaps primarily assist reachability calculations and pack generation for transfer operations. |
| Old packs can be deleted manually after repacking | Use `-d` and Git tools to manage packs; manual deletion can lose still-referenced objects. |
| Missing reflog entries mean objects are definitely gone | Objects may still exist in packs or cruft packs; recoverability depends on whether objects remain and whether a ref retains them. |

## 15. Self-check

1. **How do loose objects differ from packfiles?**
   - Loose objects are stored individually as separate files; packfiles consolidate many objects into one file and can use delta compression.
2. **What is the role of the `.idx` file?**
   - Maps OIDs to object offsets inside the packfile.
3. **What is `git repack -a -d` commonly used for?**
   - Packing reachable objects into a new pack and removing old packs that have become redundant.
4. **What is the tradeoff of increasing `--window`?**
   - Git examines more delta base candidates, potentially achieving better compression at the cost of more CPU and memory.
5. **What does `--depth` control?**
   - Maximum depth of a delta chain; deeper chains can save disk space while increasing object reconstruction cost.
6. **When are bitmap indexes most useful?**
   - Speeding up reachability computations and pack generation for clone/fetch operations.
7. **Why should you avoid running prune immediately after noticing a lost commit?**
   - Unreachable objects may be the data needed for recovery; pruning can remove those objects from the object database.

## Conclusion

`git repack` consolidates loose objects and existing packs into new packfiles, optionally using delta compression to reduce size. `--window` controls the base search scope, `--depth` caps delta chains, while thread counts and pack size limits affect CPU, RAM, I/O, and pack management overhead. Measure with `git count-objects -vH`, inspect packs with `git verify-pack -v`, and choose optimization settings based on your actual workload. For routine maintenance, consider `git gc` or incremental maintenance; always exercise caution with unreachable objects and prune operations since they can eliminate history recovery opportunities.
