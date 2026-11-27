# Commit-graph, bitmap, and multi-pack-index

When a repository has a long history, hundreds of thousands of commits, or a large number of packfiles, some Git operations can take noticeable time because they must traverse the commit graph or look up objects across many packs. Git provides metadata structures to accelerate these operations without altering commit contents or source code.

Three commonly used structures are **commit-graph**, **reachability bitmap**, and **multi-pack-index (MIDX)**. They address three distinct bottlenecks:

- Commit-graph enables Git to traverse relationships between commits faster.
- Bitmaps enable faster computation of the set of objects reachable from commits, especially when building packs for fetch, clone, or push.
- Multi-pack-index speeds up object lookup when a repository has many packfiles.

These structures can coexist in the same repository. Understanding the role of each structure helps you choose the right maintenance approach, verify effectiveness, and avoid running unnecessary repack or garbage collection commands.

## 1. Why do large repositories need accelerating metadata?

Git stores content as objects: commits, trees, blobs, and tags. As a repository grows, the number of objects and commits increases. Git must perform several tasks when processing history and exchanging data:

- Follow parent commits to find a common ancestor.
- Determine which commits lie between two refs.
- Identify which objects are reachable from a branch or tag.
- Look up objects by OID across multiple packfiles.
- Build a pack containing only objects the receiving side does not yet have.

For small repositories, this cost is usually negligible. For monorepos or repositories with deep histories, repeated traversals can slow down fetch, clone, push, log, or maintenance operations.

Git uses auxiliary metadata to avoid recomputing everything from scratch. This metadata is built from existing objects and refs, so it can be regenerated if missing or corrupted. It does not replace the original commits, trees, or blobs.

## 2. Three structures solving three different problems

| Structure | Primary problem | Indexed information |
|---|---|---|
| Commit-graph | Traversing commit history and ancestry relationships | Commit OID, tree, parents, generation number, and data accelerating path queries |
| Reachability bitmap | Computing the set of objects reachable from commits | Bitsets representing objects reachable from specific commits |
| Multi-pack-index | Locating objects when many packfiles exist | Mapping from object OID to pack and offset within the pack |

You can remember them by question:

- **Commit-graph:** which commit is the parent or ancestor of which commit?
- **Bitmap:** which objects are reachable from this commit?
- **MIDX:** which packfile contains this object?

A repository can use all three. MIDX does not replace bitmaps; MIDX locates objects across multiple packs, whereas bitmaps compute reachable object sets. Meanwhile, commit-graph focuses on the commit DAG and does not index the pack location of every blob.

## 3. What does commit-graph store?

The commit-graph is a metadata file containing information about commits in the repository. Git can store commit OIDs, tree OIDs, parent commits, generation numbers, and additional data used to accelerate history traversal.

Key pieces of information include:

- **Commit OID:** commit identifier.
- **Tree OID:** root tree of the snapshot in the commit.
- **Parent list:** parent/child relationships, including multiple parents of merge commits.
- **Generation number:** topological generation order used to prune ancestry traversals.
- **Commit date:** commit timestamp stored in metadata.
- **Changed-path Bloom filter:** probabilistic filter indicating whether a path may have changed in a commit, if written.

Commit-graph does not store file contents. Nor is it a source of truth replacing commit objects. Git still reads commit objects when needed; commit-graph supplies precomputed data to reduce traversal overhead.

Conceptual layout:

~~~text
Commit objects
  A <- B <- C <- E
        \       /
         D ----
           merge

Commit-graph
  OID A: parent []
  OID B: parent [A]
  OID C: parent [B]
  OID D: parent [B]
  OID E: parent [C, D]
  generation / tree / optional Bloom filters
~~~

When Git needs to find a common ancestor or walk commits in order, it can use graph metadata instead of repeatedly opening and parsing every commit object.

## 4. Generation numbers speed up ancestry traversal

A generation number represents an ordering level in the commit graph. It helps Git determine that one commit cannot be an ancestor of another if its generation does not satisfy the required condition.

In a linear graph, generations increase step by step with each commit. For merge commits, the generation is computed from parents so it still reflects the commit's position in the DAG (directed acyclic graph).

A generation number is not a repository-wide commit sequence number and should not be used as a timestamp. It is metadata serving graph traversal algorithms.

Git can use generation numbers in operations such as:

- Finding a merge base.
- Comparing ancestry between two commits.
- Walking commits within a revision range.
- History queries that need to determine which commits can be ancestors of another commit.

If the commit-graph is absent or invalid, Git can still compute these results from commit objects, though it may need to read more data.

## 5. Changed-path Bloom filters accelerate path-filtered logs

When running:

~~~bash
git log -- src/payment
~~~

Git needs to determine which commits modified the path <code>src/payment</code>. In large repositories, inspecting file trees across many commits can be expensive.

Commit-graph can store a **Bloom filter** of changed paths for each commit. A Bloom filter is a probabilistic structure:

- If the filter says the path definitely does not appear, Git can skip more expensive tree checks.
- If the filter says the path might appear, Git must perform an exact check.
- False positives can occur, meaning the filter reports a possible match when the path did not actually change.
- By design, false negatives are not permitted, ensuring real changes are never skipped.

To write a commit-graph with changed-path Bloom filters:

~~~bash
git commit-graph write --reachable --changed-paths
~~~

The <code>--changed-paths</code> option instructs Git to record Bloom filters for path queries. This feature helps when frequently running <code>git log -- &lt;path&gt;</code>, <code>git log --follow</code>, or file-level history analysis tools.

Bloom filters do not make every log command faster. Benefits depend on query type, commit count, tree structure, and Git version.

## 6. Creating and verifying commit-graph

Create a commit-graph from commits reachable via refs:

~~~bash
git commit-graph write --reachable
~~~

Also generate changed-path Bloom filters:

~~~bash
git commit-graph write --reachable --changed-paths
~~~

Verify consistency:

~~~bash
git commit-graph verify
~~~

You can enable progress output for large repositories:

~~~bash
git commit-graph verify --progress
~~~

<code>--reachable</code> tells Git to build the graph for commits reachable from refs known to the repository. This generally fits standard working repositories.

If you only want to build a graph for commits supplied via stdin, you can use <code>--stdin-commits</code>; ensure the input set and ref scope match your maintenance goal.

Commit-graph resides in Git's internal metadata, does not appear as files in the working tree, and is not committed to the source repository.

## 7. Split commit-graph for continuously updated repositories

If every fetch rewrote a large commit-graph from scratch, graph generation cost could scale with repository history. Git supports a **split commit-graph chain** to write incremental graph layers instead of always rebuilding a single monolithic file.

Create or update a split graph:

~~~bash
git commit-graph write --reachable --split
~~~

You can combine this with Bloom filters:

~~~bash
git commit-graph write --reachable --split --changed-paths
~~~

Graph layers are linked into a chain. Git reads them as a unified structure. When the chain accumulates many layers or needs consolidation, Git can perform compaction according to the write command's policy.

Advantages:

- Reduces the amount of data rewritten during incremental updates.
- Fits repositories that frequently fetch new commits.
- Allows updating the graph in batches.

Limitations:

- The chain introduces extra metadata and more files.
- Requires maintenance and merging when appropriate.
- Split graphs are not always faster than a single graph; observe real workloads.

Do not manually delete files inside the commit-graphs directory. Use <code>git commit-graph write</code> and <code>git commit-graph verify</code> so Git manages the chain.

## 8. Automatically updating commit-graph

You can instruct Git to write the commit-graph during fetch:

~~~bash
git config fetch.writeCommitGraph true
~~~

Or specify it for a single fetch:

~~~bash
git fetch --write-commit-graph origin
~~~

This setting and option keep the graph updated as the repository receives new commits. If the system already uses Git maintenance, you can let the scheduled maintenance task manage the commit-graph.

Run the task individually:

~~~bash
git maintenance run --task=commit-graph
~~~

Check related settings:

~~~bash
git config --show-origin --get fetch.writeCommitGraph
git config --show-origin --get core.commitGraph
~~~

You do not need to force identical settings across all repositories. For small repositories or short-lived workflows, graph overhead may be negligible. For large repositories, commit-graph is usually beneficial, especially when history queries occur frequently.

## 9. What is a reachability bitmap?

A reachability bitmap is a bitset structure that helps Git determine the set of objects reachable from a commit. Instead of traversing the entire graph and collecting objects every time a pack is built, Git can combine bitmaps to compute the object set faster.

For example, a commit reaches:

- Commit objects in history.
- Tree objects of snapshots.
- Blob objects of files.

A bitmap records that object set as bits. Bitmaps of different commits can be combined using bitwise operations to compute which objects need to be sent or which objects the receiver is missing.

Bitmaps are especially useful when a server handles many clones/fetches or must build packs for large repositories.

### Bitmaps are not content copies

Bitmaps do not store blob or commit objects. They only store metadata about object reachability. If a packfile is replaced, removed, or rebuilt with a different object set, the corresponding bitmap must be updated or regenerated.

Bitmaps speed up object-set computation; they replace neither the pack index nor the commit-graph.

## 10. How do bitmaps speed up fetch, clone, and push?

When a client requests a clone or fetch, the server must determine which objects to send. If a repository has many commits and objects, walking the entire history to build the list can take substantial time.

With reachability bitmaps, Git can:

1. Select the bitmap corresponding to the requested tip commit.
2. Combine bitmaps of sender and receiver refs when applicable.
3. Compute the set of objects to send via bitwise operations.
4. Build a pack from the identified object set.

Bitmaps reduce object-traversal cost, though they do not eliminate network transfer time, pack compression overhead, or disk writes on the receiving machine.

Effectiveness depends on:

- Number of commits and objects.
- Number of refs and how they share history.
- Whether bitmaps cover the required commits.
- Object types and pack layout.
- Git version and server configuration.

## 11. Generating bitmaps for packfiles with git repack

A common way to generate a bitmap is to repack reachable objects into a pack and write a bitmap index:

~~~bash
git repack -adb
~~~

Main options:

- <code>-a</code>: pack reachable objects into a new pack.
- <code>-d</code>: delete redundant packs after repacking.
- <code>-b</code>: write a bitmap index if supporting conditions are met.

This command can read and write a lot of data, produce a large pack, and consume significant CPU/IO. Do not run it casually on a heavily loaded server. For large repositories, choose a maintenance window and ensure sufficient temporary disk space.

To check options for your installed version, view <code>git repack -h</code> or local documentation before putting the command into maintenance scripts.

### Which pack does a bitmap belong to?

A traditional bitmap is tied to a specific packfile. When repack creates a new pack, Git can generate the corresponding bitmap index. If that pack is later replaced or deleted, the bitmap is no longer valid metadata for the old pack layout.

Therefore, packfile bitmaps must be regenerated when the pack structure changes significantly. Do not copy standalone <code>.bitmap</code> files from another repository or rename them manually.

## 12. Bitmaps and Multi-pack-index bitmaps

In repositories with multiple packfiles, a bitmap attached to a single pack may not conveniently cover the entire object set. Git supports **MIDX bitmaps** to build reachability bitmaps over the object set indexed by a multi-pack-index.

Generate or update a MIDX bitmap:

~~~bash
git multi-pack-index write --bitmap
~~~

The <code>--bitmap</code> option instructs Git to write a bitmap associated with the MIDX. Availability depends on the Git version; inspect <code>git multi-pack-index -h</code> or documentation for your deployed version.

MIDX bitmaps allow Git to use bitmaps while keeping objects distributed across multiple packfiles. This is a key component of incremental repack workflows for large repositories.

Do not assume a MIDX bitmap is always generated automatically just because a MIDX exists. Verify the command, configuration, and behavior of the running Git version.

## 13. What is a Multi-pack-index (MIDX)?

When a repository has multiple packfiles, each pack normally has its own <code>.idx</code> index file. Git may need to search across multiple indexes to find an object by OID.

Multi-pack-index creates a unified index spanning multiple packs. It maps object OIDs to the pack containing the object and its corresponding offset, enabling faster lookups without merging all packs into a single pack.

Example:

~~~text
objects/pack/
  pack-a.pack
  pack-a.idx
  pack-b.pack
  pack-b.idx
  pack-c.pack
  pack-c.idx
  multi-pack-index
~~~

MIDX tells Git which pack holds an object. The original packs remain in place; MIDX does not merge their contents into a new pack.

The benefit is clearest when a repository has many packfiles from frequent fetches, incremental repacks, or multi-batch object ingestion.

## 14. Creating and verifying multi-pack-index

Create or update MIDX:

~~~bash
git multi-pack-index write
~~~

Verify MIDX:

~~~bash
git multi-pack-index verify
~~~

You can enable progress output:

~~~bash
git multi-pack-index verify --progress
~~~

MIDX is stored in the pack directory of the object database. Git uses it automatically when a valid MIDX file exists; users do not need to specify it in log, fetch, or checkout commands.

MIDX does not store object contents. If a packfile is corrupted or manually deleted, the index may point to missing data. Use verify commands and maintenance workflows to update it; do not edit MIDX files by hand.

## 15. Expiring and repacking packfiles via MIDX

MIDX supports pack maintenance operations:

~~~bash
git multi-pack-index expire
git multi-pack-index repack
~~~

**Expire** handles packfiles that no longer need to be retained in the set managed by MIDX, based on index state and Git rules.

**Repack** selects objects from eligible packs to repack, reducing fragmentation and small-pack counts. You can adjust batch size in supported versions:

~~~bash
git multi-pack-index repack --batch-size=2g
~~~

Batch size caps the repack batch according to units accepted by Git. Check <code>git multi-pack-index repack -h</code> for syntax and options in your installed version.

An incremental repack workflow can update MIDX, repack a subset of objects, and then expire old packs that are no longer needed. Do not delete packs manually without understanding how MIDX references them.

## 16. Comparing pack index, MIDX, and bitmap

| Component | Scope | Role |
|---|---|---|
| Pack index <code>.idx</code> | Single packfile | Look up OIDs and object offsets in that pack |
| Multi-pack-index | Multiple packfiles | Look up objects across the entire indexed set of packs |
| Pack bitmap | Supported single pack | Compute reachable objects from bitmapped commits |
| MIDX bitmap | Pack set in MIDX | Compute reachable objects across multiple packs |
| Commit-graph | Commit graph | Speed up ancestry and history queries |

A repository can have multiple <code>.idx</code> files, one MIDX, and bitmaps. These are not mutually exclusive formats; Git coordinates them to optimize different stages.

## 17. Incremental repack and Git maintenance

In a long-lived repository, each fetch can add a new packfile. If pack counts grow unchecked, object lookup and pack management can slow down.

Git includes the <code>incremental-repack</code> maintenance task to manage packs in batches rather than always producing one giant pack. This task coordinates MIDX, repack, and expire according to Git's strategy.

Run the task:

~~~bash
git maintenance run --task=incremental-repack
~~~

Run the commit-graph task:

~~~bash
git maintenance run --task=commit-graph
~~~

Run default maintenance tasks:

~~~bash
git maintenance run
~~~

You can enable the background maintenance schedule:

~~~bash
git maintenance start
~~~

Exact execution schedules depend on operating system, scheduler, and Git configuration. Before enabling it on shared repositories or servers, understand which tasks will run and when they execute. Never allow two independent repack/gc processes to run concurrently on the same object database.

## 18. Settings related to commit-graph, bitmap, and MIDX

Several configuration settings affect how Git uses accelerating metadata:

~~~bash
git config --show-origin --get core.commitGraph
git config --show-origin --get fetch.writeCommitGraph
git config --show-origin --get pack.useBitmaps
git config --show-origin --get maintenance.incremental-repack.auto
~~~

General meaning:

| Configuration | Purpose |
|---|---|
| <code>core.commitGraph</code> | Controls reading the commit-graph |
| <code>fetch.writeCommitGraph</code> | Enables updating the commit-graph during fetch |
| <code>pack.useBitmaps</code> | Controls using bitmaps in eligible packing operations |
| <code>maintenance.incremental-repack.auto</code> | Controls the threshold/auto-trigger for incremental repack during maintenance |

Not every Git version has identical settings or defaults. If <code>git config --get</code> returns no value, the setting may not be explicitly configured; Git can still apply default behavior.

Check configuration origin to see whether a value comes from system, global, local, or command scope. Avoid copying configuration from a large server to a small development machine without measuring results.

## 19. Measuring effectiveness before and after maintenance

Do not evaluate effectiveness merely by whether commands succeeded. Measure real workloads before and after building metadata.

Metrics to track:

- Runtime of <code>git log -- &lt;path&gt;</code>.
- Runtime of <code>git merge-base</code> across two long branches.
- Fetch/clone time from a test server.
- Push time when packs must be generated.
- Number of packfiles.
- Pack and object database size.
- Runtime and CPU/IO usage of maintenance runs.

Check overall object and pack summary:

~~~bash
git count-objects -vH
~~~

The command shows loose object count, loose size, pack count, pack size, and related metrics. Use the same repository and identical ref state when comparing before and after.

To time a specific command in a Unix-like environment, you can use <code>time</code>:

~~~bash
time git log --oneline -- src/payment
time git merge-base main feature/payment
~~~

On Windows, use equivalent timing tools in PowerShell or CI. Repeat runs under comparable conditions to avoid drawing conclusions from differences between cold and warm caches.

## 20. Diagnosing missing or corrupted metadata

If Git operations are abnormally slow or verify reports an error, identify which structure has an issue.

### Commit-graph

Check:

~~~bash
git commit-graph verify
~~~

If the graph is missing, you can regenerate it:

~~~bash
git commit-graph write --reachable --split --changed-paths
~~~

If the graph is corrupted, preserve error logs and consider rebuilding using Git commands. Do not manually delete graph files without understanding the current split chain.

### Multi-pack-index

Check:

~~~bash
git multi-pack-index verify
~~~

If MIDX is missing or needs updating:

~~~bash
git multi-pack-index write
~~~

After packs are repacked or expired, update MIDX according to the maintenance workflow.

### Bitmap

Bitmaps are usually verified indirectly via repack/pack operations and version-appropriate inspection tools. If you suspect a bitmap is no longer compatible with packs, regenerate it using a repack with bitmaps or MIDX bitmap workflow.

Do not delete a bitmap currently in use by Git while the repository has concurrent read/write operations.

## 21. Things you should not do

- Do not edit commit-graph, bitmap, or MIDX files with a hex editor.
- Do not copy metadata files from another repository.
- Do not delete packfiles simply because there are many <code>.pack</code> files.
- Do not run repack, gc, and maintenance concurrently on the same object database.
- Do not run <code>git repack -adb</code> on a heavily loaded server without measuring the cost.
- Do not assume MIDX reduces total object size; it primarily accelerates lookup across multiple packs.
- Do not assume bitmaps speed up every Git command; benefits focus on object traversal and pack generation.
- Do not treat commit-graph as the primary source of commit data; commit objects remain the source of truth.

Metadata files can be regenerated, whereas packfiles holding original objects cannot always be recovered if deleted by mistake. Distinguish auxiliary index files from data-bearing packs.

## 22. Sample workflow for a large repository

Suppose a repository has a long commit history and many packfiles from continuous fetches.

**Step 1 — Record baseline state**

~~~bash
git count-objects -vH
git show-ref
git commit-graph verify
git multi-pack-index verify
~~~

If commit-graph or MIDX does not exist yet, verify may report no structure to check; note this state rather than treating it as commit data corruption.

**Step 2 — Update commit-graph**

~~~bash
git commit-graph write --reachable --split --changed-paths
git commit-graph verify
~~~

**Step 3 — Update MIDX**

~~~bash
git multi-pack-index write
git multi-pack-index verify
~~~

**Step 4 — Generate bitmaps when workload requires**

If the server frequently builds packs for clone/fetch:

~~~bash
git multi-pack-index write --bitmap
~~~

If using a single-pack bitmap, consider repacking with bitmaps during a maintenance window:

~~~bash
git repack -adb
~~~

You do not necessarily need to run both approaches. Choose pack bitmap or MIDX bitmap based on pack layout, Git version, and server workflow.

**Step 5 — Run incremental repack maintenance if appropriate**

~~~bash
git maintenance run --task=incremental-repack
~~~

**Step 6 — Re-measure**

~~~bash
git count-objects -vH
git commit-graph verify
git multi-pack-index verify
~~~

Compare task runtimes and sizes against baseline metrics. If there is no improvement, re-examine the actual bottleneck instead of repeatedly running repack.

## 23. Operations checklist

- [ ] Identified whether the slow operation is commit traversal, reachable object computation, or object lookup across many packs.
- [ ] Verified that the installed Git version supports the required options.
- [ ] Generated/verified commit-graph if the repository has a large history.
- [ ] Considered changed-path Bloom filters for path-based history queries.
- [ ] Checked packfile count and MIDX status.
- [ ] Considered bitmaps when the server frequently builds packs.
- [ ] Selected pack bitmap or MIDX bitmap according to repository layout.
- [ ] Scheduled repack/maintenance for an appropriate time window.
- [ ] Confirmed no other gc/repack processes are running concurrently.
- [ ] Measured runtime and disk usage before and after.
- [ ] Saved verification logs and operational results.
- [ ] Ensured appropriate backups exist before large repack operations on critical servers.

## 24. Key takeaways

- Commit-graph accelerates commit and ancestry traversal; changed-path Bloom filters assist path-based history queries.
- Reachability bitmaps accelerate computing objects to send or process when building packs.
- Multi-pack-index maps object OIDs to packs and offsets, useful when a repository has many packfiles.
- Pack bitmaps attach to a pack; MIDX bitmaps can describe reachability across multiple packs.
- Use <code>git commit-graph write</code> and <code>git commit-graph verify</code> to build/verify the graph.
- Use <code>git multi-pack-index write</code> and <code>git multi-pack-index verify</code> to build/verify MIDX.
- <code>git repack -adb</code> can generate packs and bitmaps but carries significant IO/CPU cost.
- <code>git maintenance run --task=incremental-repack</code> and <code>--task=commit-graph</code> help automate task-based maintenance.
- This metadata does not replace original objects and does not alter commit hashes.
- Measure workloads before and after, and avoid running multiple repack/gc operations concurrently.

Commit-graph, bitmap, and multi-pack-index are three complementary layers of metadata. When you identify the true bottleneck, build and verify the appropriate structures, and re-measure on real workloads, large repositories can traverse history and exchange objects more efficiently while keeping Git data intact.
