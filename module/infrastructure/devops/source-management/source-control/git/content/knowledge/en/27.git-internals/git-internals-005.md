# Loose Objects, Packfiles, Delta Compression, and Pack Index Files

Git stores history using immutable content-addressed objects. When a new object is created, Git may store it as a loose object. As a repository grows, multiple objects are bundled into packfiles to reduce disk usage and improve storage efficiency. Packfiles can use delta compression to store differences between similar objects, while pack index files help Git locate objects quickly without scanning the entire pack.

Understanding these components helps explain why `.git/objects` contains files with unreadable names, why `.pack` and `.idx` files appear after a fetch or garbage collection, and how to inspect the size and integrity of the object database.

After this lesson, you will be able to:

- Explain loose objects and how Git names objects by content.
- Identify the `commit`, `tree`, `blob`, and `tag` object types.
- Describe the basic structure of a packfile.
- Explain delta compression and the two ways of referencing a base object.
- Distinguish the pack index `.idx` from the staging index `.git/index`.
- Use `cat-file`, `count-objects`, `verify-pack`, and `fsck` to inspect data.
- Understand the role of `repack` and garbage collection.

## 1. What does the Git object database store?

Git does not store history merely as sequential text patches. The repository stores objects describing content and relationships between versions. The four fundamental object types are:

| Object type | Contents |
| --- | --- |
| blob | Content of a single file; does not store the file name or path. |
| tree | List of names, modes, types, and object IDs for entries in a directory. |
| commit | Root snapshot of a version, author/committer metadata, message, and parent commits. |
| tag | Annotated tag object pointing to an object and storing metadata such as tagger, timestamp, message, and optionally a signature. |

A commit normally points to a tree representing the root directory of the snapshot. A tree can point to subtrees or blobs. A commit also points to parent commits to form history. An annotated tag is a standalone object; a lightweight tag is simply a ref pointing to an object.

Git objects are identified by an object ID (OID), computed from the canonical representation of the object consisting of a header and content. Conceptually, the header has the form:

~~~text
<type> <size> NUL <content>
~~~

For example, a blob object has a header containing the `blob` type, the content byte count, and a NUL byte separating it from the actual content. Git hashes this entire canonical representation to produce the OID. The same type and same content yield the same OID under the same repository hash format.

Traditional Git repositories use SHA-1 with 40-hex-character OIDs. Git also supports repositories using SHA-256, where OIDs are 64 hex characters long. You can check the hash format of the current repository:

~~~bash
git rev-parse --show-object-format
~~~

Do not assume every repository uses 40-character OIDs. Git commands generally accept either a full OID or an abbreviated prefix unique within the repository.

## 2. How are loose objects stored?

When Git writes an unpacked object, it is typically stored in the object database at the path:

~~~text
.git/objects/aa/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
~~~

The first two hex characters of the OID become the directory name; the remaining characters become the file name. This split avoids creating a single directory with too many files.

Example OID:

~~~text
e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
~~~

Corresponding loose object path:

~~~text
.git/objects/e6/9de29bb2d1d6434b8b29ae775ad8c2e48c5391
~~~

The loose object file is compressed with zlib. Therefore, if you open the file in a text editor, you will not see the header and original file content in human-readable form. Git decompresses and parses the object when needed.

A loose object is a standalone storage unit. Git can create them when writing new objects, such as when adding content to the index or creating a commit. When the repository undergoes maintenance or receives substantial data, Git can bundle loose objects into packfiles.

## 3. Creating and reading objects for inspection

You can use `git hash-object` to compute a file's OID without writing the object to the database:

~~~bash
git hash-object README.md
~~~

Add the `-w` option to write the object into the object database:

~~~bash
git hash-object -w README.md
~~~

The command returns the blob's OID. Writing an object does not automatically create a commit or stage the file.

Assuming the command returns OID `abc123...`, you can check the object type:

~~~bash
git cat-file -t abc123
~~~

Check the content size:

~~~bash
git cat-file -s abc123
~~~

Print the object content:

~~~bash
git cat-file -p abc123
~~~

For a blob, `-p` prints the file content. For a tree, it displays the entries and OIDs. For a commit, it displays metadata along with the tree and parents. For a tag, it displays the tag object's contents.

You can retrieve the OID of a file at a given commit:

~~~bash
git rev-parse HEAD:README.md
~~~

Then use `cat-file` to inspect the object referenced by the commit's tree. This demonstrates that the file name does not reside in the blob; names and paths are stored in trees, while blobs hold only content bytes.

## 4. Why does Git need packfiles?

If a repository kept every object as a loose file forever, the file count inside `.git/objects` could grow enormous. Having one file per object increases filesystem metadata overhead and slows down traversing or copying many small objects.

A packfile bundles many objects into a single larger file. Git can compress objects and represent some objects as deltas relative to similar base objects. Bundling in this way helps:

- Reduce the number of files in the object database.
- Save disk space when many objects share similar content.
- Transfer groups of objects more efficiently during fetch, clone, or push.
- Organize data so Git can look up and read sequentially with better performance.

Packfiles typically reside in:

~~~text
.git/objects/pack/
|-- pack-<hash>.pack
|-- pack-<hash>.idx
+-- pack-<hash>.rev
~~~

The `.rev` file is a reverse index that may also be generated in certain Git versions and maintenance workflows; not every pack is required to have this file. The essential files to recognize are `.pack` and `.idx`.

You can query the object database and pack directory paths via Git rather than concatenating `.git` manually, especially when working with linked worktrees or custom repository layouts:

~~~bash
git rev-parse --git-path objects
git rev-parse --git-path objects/pack
~~~

## 5. Basic structure of a packfile

A packfile uses a binary format. Conceptually, a pack consists of:

1. A header identifying the pack, format version, and number of packed objects.
2. Entries describing objects; an entry can store either a full object or a delta against a base object.
3. A checksum at the end of the pack to verify pack data integrity.

The header starts with the ASCII bytes `PACK`. Next come the pack version number and the entry count. Common pack versions are 2 and 3. Each entry has a header encoding the object type and data size as a variable-length integer, followed by compressed data.

For an entry storing a full object, the decompressed data corresponds directly to the object's content. For a delta entry, the decompressed data consists of instructions to reconstruct the target object from a base object.

A packfile can store `commit`, `tree`, `blob`, and `tag` objects. It can also store delta entries, typically represented by the `OFS_DELTA` or `REF_DELTA` types. These two types specify how to locate the base object needed to reconstruct the target object.

Never edit a `.pack` file in an editor or delete individual files manually. A packfile is structured binary data paired with its corresponding index.

## 6. What is delta compression?

Across Git history, many blobs can be highly similar. For example, a source code file may have only a few lines changed across dozens of commits. Storing every version in full inside a pack can significantly increase disk usage.

Delta compression stores a target object as instructions to reconstruct it from a base object. Instead of repeating the entire content, a delta can:

- Copy a range of bytes from the base object.
- Insert a new sequence of bytes.
- Combine multiple copy and insert operations to produce the complete content.

Illustrative example:

~~~text
Base object:
    public class Search {
        return query;
    }

Target object:
    public class Search {
        return normalize(query);
    }

Conceptual delta:
    COPY initial segment from base object
    INSERT "normalize("
    COPY remaining matching segment
    INSERT ")"
~~~

This is only an illustrative model, not the actual binary delta syntax of a packfile. Real deltas are binary data encoding copy/insert instructions and lengths.

When Git needs the target object, it locates the base object, applies the delta instructions, and reconstructs the complete byte content. Once reconstructed, the object has the exact same OID as when stored as a loose object or full object in a pack.

Important point: delta compression is a storage optimization. It does not alter logical history, logical content, or an object's OID. Displaying a diff between two commits via `git diff` is a separate operation; deltas inside a pack are simply the physical on-disk representation of objects.

## 7. OFS_DELTA and REF_DELTA

The pack format has two common ways to specify a delta's base object:

| Delta type | How it references the base | Characteristics |
| --- | --- | --- |
| OFS_DELTA | Uses a byte offset to an earlier base entry in the same pack. | Avoids storing the full base OID; suitable when the base lives in the same pack. |
| REF_DELTA | Uses the OID of the base object. | Can locate the base by OID in the object database; does not depend on the base's byte offset in the current pack. |

`OFS_DELTA` identifies the base via a relative offset inside the pack. `REF_DELTA` uses an OID to identify the base, allowing Git to look up the base among existing objects through standard object database lookup.

A delta can itself depend on another delta. In that case, Git must reconstruct the chain starting from the original base through each delta layer until reaching the requested object. Overly deep chains increase decompression cost, so during repacking Git balances chain depth against compression ratio.

Not every object in a pack is stored as a delta. Commits and trees are usually small, and some blobs do not benefit from delta encoding. Git chooses how to store each object based on size, similarity, and packing heuristics.

## 8. What does the pack index file (.idx) do?

A packfile can hold thousands or millions of objects. To look up an object by OID, Git should not have to sequentially scan the entire packfile for the matching entry. The pack index file `.idx` provides a mapping from OID to the entry's position in the pack.

A pack index typically contains:

- A 256-entry fanout table narrowing the search range by the OID's first byte.
- A sorted list of OIDs.
- CRC32 checksums for pack entry data in index format version 2.
- Offsets to entries in the pack.
- An additional 64-bit offset table when offsets exceed a 32-bit field.
- The pack checksum and the index file's own checksum.

Using the sorted OID list and fanout table, Git can locate an object rapidly and then use its offset to read the corresponding entry from the `.pack` file.

The index file normally shares the same basename as its pack:

~~~text
pack-abc123.pack
pack-abc123.idx
~~~

The two files belong together as a pair. Deleting or replacing one without updating the other can prevent the object database from reading the pack as expected. Let Git manage them through fetch, repack, and garbage collection.

## 9. Distinguishing the pack index from the staging index

The shared word "index" can cause confusion:

| Component | Typical path | Role |
| --- | --- | --- |
| Staging index | `.git/index` | Stores the staged temporary snapshot prepared for creating the next commit. |
| Pack index | `.git/objects/pack/pack-<hash>.idx` | Looks up OIDs and offsets of objects inside a packfile. |

The staging index participates in the working tree → staging area → commit workflow. The pack index belongs to the object database and serves lookups for packed data. They never replace or update one another.

Example:

~~~bash
# Inspect changes in the staging area
git diff --cached

# Show the repository's staging index file path
git rev-parse --git-path index

# Show the pack directory containing .pack and .idx
git rev-parse --git-path objects/pack
~~~

Never delete `.git/index` to fix a packfile, and never delete a pack `.idx` file to unstage a change from the staging area. These are two completely different indexes serving different purposes.

## 10. Observing loose objects and packfiles in a repository

A useful overview command:

~~~bash
git count-objects -vH
~~~

Sample output:

~~~text
count: 42
size: 180.00 KiB
in-pack: 1250
packs: 3
size-pack: 8.40 MiB
prune-packable: 12
garbage: 0
size-garbage: 0 bytes
~~~

Key field meanings:

| Field | Meaning |
| --- | --- |
| count | Number of loose objects in the object database. |
| size | Total size of loose objects, in human-readable form when `-H` is used. |
| in-pack | Number of objects stored in packfiles. |
| packs | Number of recognized packfiles. |
| size-pack | Total size of packfiles. |
| prune-packable | Loose objects that already have a copy in a pack and can be pruned during maintenance. |
| garbage | Number of files in the object database that are not valid objects. |
| size-garbage | Total size of detected garbage files. |

These numbers vary depending on the repository and recent activity. Having many loose objects is not necessarily an error; Git may keep them until appropriate maintenance runs.

To locate existing packs:

~~~bash
git rev-parse --git-path objects/pack
~~~

Then list the files in the returned directory using filesystem tools. Do not assume the path is always `.git/objects/pack`, as the Git directory layout can differ in linked worktrees or specially configured repositories.

## 11. Inspecting pack contents with git verify-pack

`git verify-pack` checks the consistency of a pack index and its corresponding packfile, and can display per-object details:

~~~bash
git verify-pack -v .git/objects/pack/pack-<hash>.idx
~~~

The path above is an example; replace `<hash>` with the actual pack basename. On Windows or in linked worktrees, use the path resolved from `git rev-parse --git-path objects/pack`.

Output typically includes these columns:

| Field | Meaning |
| --- | --- |
| OID | Object ID after reconstructing the object. |
| Type | Object type such as `commit`, `tree`, `blob`, or `tag`. |
| Size | Uncompressed object size. |
| Packed size | Size of the entry data stored in the pack. |
| Offset | Byte offset of the entry inside the packfile. |
| Depth | Delta chain depth, if the object is stored as a delta. |
| Base OID | OID of the base object when the output includes this field. |

Non-delta objects normally have no depth/base fields. Delta objects can show a packed size much smaller than the uncompressed object size.

You can use the output to identify large objects or deep delta chains. However, do not look solely at packed size and assume an object is unimportant; every entry may be referenced by commits, trees, tags, or other objects.

## 12. Checking integrity with git fsck

`git fsck` checks the integrity of the object database and reference relationships between objects:

~~~bash
git fsck --full
~~~

This command detects missing objects, corrupted objects, or objects unreachable from current refs. Depending on repository state, the output may also list dangling or unreachable objects.

A dangling object is not necessarily an error. For example, after resetting a branch or deleting a ref, an old commit may no longer be referenced by any branch or tag while still remaining in the object database for a while. Git can retain that object to assist recovery before garbage collection becomes eligible to prune it.

If `fsck` reports missing or corrupt objects, preserve the exact output and identify the affected objects. Do not run cleanup commands or manually delete packs before understanding the scope of the incident. For important repositories, make a safe backup copy before attempting repairs.

## 13. Repack and garbage collection

When many loose objects or many small packs accumulate, Git can consolidate and reorganize the object database. Two key commands to know:

~~~bash
git repack -ad
git gc
~~~

`git repack` builds a new pack from the selected set of objects and can remove redundant packs when given the appropriate options. For example, `-a` packs reachable objects in the repository; `-d` removes redundant packs after creating the new pack.

`git gc` runs maintenance tasks such as repacking and handling obsolete objects according to expiration policies. Git may trigger automatic maintenance during certain commands if the repository crosses configured thresholds.

Before running manual maintenance on a repository accessed concurrently by multiple processes, ensure no other Git operations are actively writing to the object database. Never delete `.pack` or `.idx` files by hand to free disk space; doing so can lose objects and break pack lookups.

Repacking changes how objects are stored on disk without changing object OIDs, commit contents, or where branches point. If an object moves from loose to packed storage, `cat-file` still reads it with the exact same OID.

### Why aren't all loose objects packed immediately?

Git may keep newly created loose objects for a period of time or until maintenance runs. This reduces the overhead of constant repacking and avoids immediately deleting objects that recently became unreachable but might still be needed for recovery. Thresholds and expiration periods depend on configuration and Git version.

## 14. Delta compression is a physical optimization, not commit history

A common misconception is thinking Git stores commits as sequential patches on top of previous commits. In reality, a commit references a tree describing a snapshot. Trees reference blobs and subtrees. A packfile may choose to store a blob as a delta to save space, but that storage representation does not alter Git's snapshot model.

For example, two commits can share references to many identical blobs. If one file changes slightly, a pack may store the new blob as a delta against the old blob. Yet when checking out the new commit, Git reconstructs the complete blob and writes its full content into the working tree.

This also explains why:

- An object can exist in loose or packed form without its OID changing.
- An object can be delta-encoded yet `cat-file` still returns its full content.
- Repacking can change repository disk size without creating any new commits.
- `git diff` is not a direct dump of delta instructions inside a packfile.

## 15. Diagnostic workflow when the object database is large or abnormal

When `.git/objects` consumes excessive disk space or Git reports object errors, inspect in order:

~~~bash
# 1. Locate the object database and pack directory
git rev-parse --git-path objects
git rev-parse --git-path objects/pack

# 2. Count loose objects and packfiles
git count-objects -vH

# 3. Verify integrity
git fsck --full

# 4. Inspect a specific pack if needed
git verify-pack -v .git/objects/pack/pack-<hash>.idx

# 5. Run maintenance only after understanding the state
git gc
~~~

If storage growth is caused by large blobs or history containing many versions of binary files, delta compression may yield minimal savings because those files share little similarity. In that case, review large-file management policies, Git LFS, or appropriate artifact storage instead of repeatedly repacking.

If a packfile is missing or corrupted, do not fabricate an `.idx` file by renaming or copying one from another pack. Restore the objects from a remote, another clone, or a trusted backup, and then run integrity checks.

## 16. Common pitfalls

### Opening a loose object file and seeing unreadable data

Loose objects are zlib-compressed and include a binary header. Use `git cat-file -t`, `-s`, or `-p` so Git decodes and displays the object.

### Deleting `.idx` files to free disk space

Do not do this. The pack index is the lookup table for the packfile. Deleting it can prevent Git from accessing the pack normally. Use `git gc` or `git repack` for maintenance.

### Confusing the pack index with the staging index

`.git/index` stores staged content; `pack-<hash>.idx` sits alongside a packfile and maps OIDs to offsets. The two files are functionally unrelated.

### Thinking delta compression changes OIDs

Incorrect. An OID is computed from the canonical uncompressed object content, not from how the object is compressed or delta-encoded inside a pack.

### Assuming dangling objects are always errors

Incorrect. Objects can become unreachable after a ref is moved or deleted while still remaining available for recovery. Inspect `fsck` output and understand your refs before pruning.

### Deleting packs manually to free space

Very risky. A single pack can hold objects needed by many commits and refs. Use Git's maintenance tools rather than deleting `.pack` or `.idx` files individually.

## 17. Key takeaways

- Git stores blobs, trees, commits, and annotated tags as immutable objects identified by OID.
- A loose object is typically canonical content compressed with zlib and placed in a subdirectory named after the first two characters of its OID.
- A packfile bundles many objects into a single file and may store some objects as deltas.
- Delta compression reconstructs an object from a base using copy/insert instructions; it is a storage optimization and does not alter logical history or OIDs.
- `OFS_DELTA` references the base by offset within the same pack; `REF_DELTA` references the base by OID.
- The pack index `.idx` maps OIDs to offsets in `.pack`; it is distinct from the staging index `.git/index`.
- `git count-objects -vH`, `git verify-pack -v`, and `git fsck --full` let you observe and verify the object database.
- `git repack` and `git gc` are maintenance tools; never delete packs or indexes by hand.
- Repacking can change how objects are stored on disk without altering OIDs, commits, or working tree contents.

Loose objects let Git write data simply one object at a time; packfiles bundle and compress data for more efficient repository storage. Delta compression cuts down repeated content, while pack indexes make object lookups fast. Understanding these three layers allows you to read the object database layout, diagnose storage growth, and maintain repositories without confusing storage internals with history or the staging area.
