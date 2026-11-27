# Reading Objects with `git cat-file` and `git ls-tree`

Git stores history as linked objects. Commits point to trees, trees list the names and modes of directory entries, and blobs contain file content bytes. Annotated tags create an additional object describing a labeled milestone. The two commands `git cat-file` and `git ls-tree` let you inspect this structure directly without checking out a version into the working tree. Knowing how to use them enables you to check exactly what a commit contains, what content a path once held, and what type of object a tag points to.

## 1. The object model observed by these two commands

Git has four basic object types:

| Object type | Primary contents | Role |
|---|---|---|
| Blob | File content bytes | Stores file contents; does not store name or path |
| Tree | Child entries with mode, name, and object ID | Describes a directory in a snapshot |
| Commit | Tree ID, parent IDs, author, committer, timestamps, and message | Records a snapshot along with historical relationships |
| Tag | Target object, target type, tag name, tagger, timestamp, and message | Records metadata for a milestone, usually a release |

A commit does not contain all file contents inside itself. A commit points to a root tree; trees can point to subtrees and blobs. Thus, the snapshot structure can be pictured as:

```text
commit
  |
  v
root tree
  |--------------------|
  v                    v
tree: src/          blob: README.md
  |
  |--------------------|
  v                    v
blob: App.java      tree: config/
                       |
                       v
                    blob: app.yml
```

`git ls-tree` lets you inspect the entries referenced by a tree. `git cat-file` lets you determine the type, size, and content of each object.

## 2. Specifying the object to read

Object commands generally accept an object name. You can pass:

- A full object ID or a uniquely unambiguous prefix.
- A ref name such as `HEAD`, `main`, or `v1.2.0`.
- A commit expression such as `HEAD~2`, `main^{tree}`, or `v1.2.0^{}`.
- A path expression within a tree-ish such as `HEAD:README.md`.

Example:

```bash
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git rev-parse 'HEAD:README.md'
```

`git rev-parse` resolves expressions to object IDs. With `HEAD^{tree}`, Git retrieves the root tree of the `HEAD` commit. With `HEAD:README.md`, Git finds the object referenced by the `README.md` path in `HEAD`'s tree.

Object IDs are shown as SHA-1 (40 hex characters) in many repositories, though Git also supports SHA-256 repositories (64 hex characters). Never write scripts assuming every object ID is always 40 characters long.

## 3. Using `git cat-file -t` to check object type

The `-t` option prints the type of object that the given name resolves to:

```bash
git cat-file -t HEAD
git cat-file -t 'HEAD^{tree}'
git cat-file -t 'HEAD:README.md'
```

The outputs are typically, in order:

```text
commit
tree
blob
```

This lets you verify whether an expression points to a commit, tree, or blob before reading its content. For an annotated tag, `git cat-file -t v1.2.0` returns `tag` because the ref points to a tag object. For a lightweight tag, the result is normally `commit` because the ref points directly to a commit.

You can check whether an object exists without printing its content:

```bash
git cat-file -e 'HEAD:README.md'
```

This command prints nothing if the object exists and exits with a non-zero status if the object cannot be resolved. This is useful in scripts to validate existence before reading.

## 4. Using `git cat-file -s` to check object size

The `-s` option prints the object's payload size in bytes:

```bash
git cat-file -s 'HEAD:README.md'
git cat-file -s HEAD
```

For a blob, the size is the number of bytes in the file's content. For a commit, tree, or tag, the size is the byte count of the serialized data stored in that object.

This is the logical object content size, not the disk space the object occupies inside a packfile. Git may compress objects or store deltas in packfiles, so those two numbers do not necessarily match.

To view blob sizes within a tree listing, you can use `git ls-tree -l` as shown later.

## 5. Using `git cat-file -p` to read object content

The `-p` option tells Git to pretty-print the object content in a human-readable format:

```bash
git cat-file -p HEAD
```

For a commit, the output typically looks like:

```text
tree 6f3a...
parent 8c21...
author Linh Nguyen <linh@example.invalid> 1760000000 +0700
committer Linh Nguyen <linh@example.invalid> 1760000100 +0700

Add report endpoint
```

- `tree` is the object ID of the root snapshot recorded by the commit.
- Each `parent` line is a parent commit; merge commits typically have two or more parents.
- `author` records the person who made the change and the author timestamp.
- `committer` records the person who created the commit object and the commit creation timestamp.
- After the blank line comes the commit message.

Commits can include extra headers such as `encoding`, `gpgsig`, or other metadata. Do not assume every commit has only the exact lines shown in the example.

Read the blob of a file:

```bash
git cat-file -p 'HEAD:README.md'
```

For text blobs, Git prints the file contents. For binary blobs, the terminal may display unreadable characters or control bytes. Avoid printing binary files directly to a terminal; you can redirect the object to a file so an appropriate tool can open it:

```bash
git cat-file blob 'HEAD:assets/logo.png' > logo-from-commit.png
```

This command writes the blob bytes to the target file. Choose an output file name that does not overwrite existing data.

## 6. Reading a tree object with `git cat-file -p`

Retrieve the root tree from a commit and display it:

```bash
git cat-file -p 'HEAD^{tree}'
```

A tree is displayed as lines containing mode, object type, object ID, and entry name. Example:

```text
100644 blob 2f8a...    README.md
040000 tree 9b31...    src
100755 blob 6c20...    scripts/build.sh
```

A tree stores only its direct child entries. The `src` line points to another tree; to see what is inside it, you must read that subtree or use `git ls-tree -r` to recurse.

`git cat-file -p` is useful for inspecting object contents, whereas `git ls-tree` is more convenient when filtering, listing, or processing tree entries.

## 7. Reading an annotated tag object

An annotated tag creates a separate object containing metadata about the tagged milestone. Inspect its type and content:

```bash
git cat-file -t v1.2.0
git cat-file -p v1.2.0
```

Example output:

```text
object 7ab3...
type commit
tag v1.2.0
tagger Linh Nguyen <linh@example.invalid> 1760000200 +0700

Release version 1.2.0
```

- `object` is the object ID the tag points to.
- `type` indicates the target object type, usually `commit`.
- `tag` is the tag name.
- `tagger` and the message describe who created the tag and the purpose of the milestone.

To peel an annotated tag down to its final target object, use the `^{}` suffix:

```bash
git cat-file -t 'v1.2.0^{}'
git cat-file -p 'v1.2.0^{}'
```

If the tag points to a commit, the first command returns `commit` and the second displays the commit object. For a lightweight tag, the ref already points straight to the commit, so `^{}` does not need to unwrap a separate tag object.

## 8. Using `git ls-tree` to inspect tree contents

Basic command:

```bash
git ls-tree HEAD
```

This lists the direct entries at the root tree of the `HEAD` commit. Output typically looks like:

```text
100644 blob 2f8a...    README.md
040000 tree 9b31...    src
100644 blob 7c12...    pom.xml
```

Each line contains these fields:

1. **Mode:** permissions or entry kind in the tree.
2. **Object type:** `blob`, `tree`, or `commit`.
3. **Object ID:** the object referenced by that entry.
4. **Path:** path name relative to the tree being listed.

`git ls-tree` reads snapshots already stored in the object database. It does not list untracked files and does not reflect uncommitted edits in the working tree.

## 9. Understanding entry modes in a tree

Modes let Git distinguish regular files, executable files, symbolic links, directories, and gitlinks:

| Mode | Object type | Meaning |
|---|---|---|
| `100644` | `blob` | Regular file without the executable bit |
| `100755` | `blob` | Regular file with the executable bit |
| `120000` | `blob` | Symbolic link; the blob stores the link's target path |
| `040000` | `tree` | Subdirectory |
| `160000` | `commit` | Gitlink pointing to a submodule commit |

For a symbolic link, the blob does not hold the target file's content; it holds the target path string that the link points to. For a gitlink, the superproject records the commit of the child repository rather than storing files inside the submodule as regular blobs.

When you see mode `160000`, recognize it as a submodule. The referenced commit belongs to the child repository; that object may not exist in the superproject's object database, so running `git cat-file` in the superproject may not be able to read that commit if the object is not present there.

## 10. Traversing trees recursively with `-r`

By default, `git ls-tree` shows only direct entries of the specified tree. Use `-r` to descend into subdirectories:

```bash
git ls-tree -r HEAD
```

The output lists files at all depths with paths relative to the root tree. If you also want intermediate tree entries displayed during recursive traversal, combine with `-t`:

```bash
git ls-tree -r -t HEAD
```

Some useful options:

| Option | Effect |
|---|---|
| `-r` | Recurse into subtrees |
| `-t` | Show tree entries even when `-r` is used |
| `-d` | Show only tree entries |
| `-l` | Also show object sizes, useful for blobs |
| `--name-only` | Print only paths |
| `--object-only` | Print only object IDs |
| `--full-tree` | List from the root tree, not restricted by the current working directory |
| `-z` | Terminate entries with NUL, suitable for scripts handling special characters in file names |

Example printing only file names:

```bash
git ls-tree -r --name-only HEAD
```

Example viewing blob sizes:

```bash
git ls-tree -r -l HEAD
```

The displayed size is the object payload size, not the number of bytes the object occupies in a packfile.

## 11. Inspecting a specific directory or path

You can specify paths to filter the output:

```bash
git ls-tree HEAD src
git ls-tree -r HEAD -- src/
```

The first command shows the `src` entry in the tree; the second lists entries inside `src/`. To read that directory's tree with `cat-file`, you can use a path expression:

```bash
git cat-file -t 'HEAD:src'
git cat-file -p 'HEAD:src'
```

`HEAD:src` resolves to the tree object of the `src` directory in the `HEAD` commit. If the path is a file, the corresponding expression resolves to a blob.

If you are inside a subdirectory of the working tree and want to list from the repository root, use `--full-tree`:

```bash
git ls-tree --full-tree -r HEAD
```

The specified path must match the snapshot in the tree, not an arbitrary path outside the repository.

## 12. Comparing trees between two commits

`git ls-tree` can read the tree of any reachable commit in the repository. This helps check whether a file existed in an older version and how its object ID changed.

Example:

```bash
git ls-tree HEAD~1
git ls-tree HEAD
```

If you want to compare two snapshots at the path-change level, `git diff-tree` is usually more suitable:

```bash
git diff-tree --no-commit-id --name-status -r HEAD~1 HEAD
```

You can then retrieve the object ID of a path at each commit with:

```bash
git rev-parse 'HEAD~1:src/App.java'
git rev-parse 'HEAD:src/App.java'
```

If the two object IDs are identical, the referenced blob content is identical. If they differ, inspect each version:

```bash
git cat-file -p 'HEAD~1:src/App.java'
git cat-file -p 'HEAD:src/App.java'
```

For binary files, avoid printing contents directly to the terminal; use `git cat-file blob` to write to temporary files or use an appropriate comparison tool.

## 13. Using `git cat-file --batch` when reading many objects

When you need to inspect many objects in scripts or repository analysis, batch mode avoids spawning a separate Git process for each object.

To retrieve metadata for multiple objects:

```bash
printf '%s\n' HEAD 'HEAD^{tree}' 'HEAD:README.md' |
  git cat-file --batch-check='%(objectname) %(objecttype) %(objectsize)'
```

The output gives the object ID, type, and size for each requested object. Common format placeholders include:

- `%(objectname)`: object ID.
- `%(objecttype)`: object type.
- `%(objectsize)`: object payload size.
- `%(rest)`: remaining part of the input line in suitable batch workflows.

To read the contents of multiple objects, use:

```bash
printf '%s\n' HEAD 'HEAD^{tree}' 'HEAD:README.md' | git cat-file --batch
```

`--batch` prints an object header followed by the exact number of content bytes reported in that header. For binary blobs, output may include non-text bytes. Scripts parsing `--batch` should read the exact byte count specified in the header rather than splitting on newlines or assuming all objects are text.

`--batch-check` returns only metadata, making it safer and more convenient for statistics. You can pair `--batch-all-objects` with the appropriate batch mode to iterate over every object in the object database, including objects no longer pointed to by normal refs; consider data volume and runtime on large repositories.

The examples above use shell `printf` syntax; in PowerShell, you can pipe lines through the pipeline by generating text lines and passing them to `git cat-file --batch-check`.

## 14. Distinguishing tree objects, the index, and the working tree

`git ls-tree` only reads trees stored in commits or tree objects. It is not a tool for inspecting the staging area or current files on disk.

| Data location | Appropriate command | Reflected content |
|---|---|---|
| Committed commit/tree | `git ls-tree <tree-ish>` | Snapshot of a commit or tree object |
| Index (staging area) | `git ls-files --stage` | Staged entries, including mode, object ID, and stage number |
| Working tree | `git status`, `git diff`, and filesystem tools | Current files on disk and unstaged changes |

Example of a file edited but not yet committed:

```bash
git ls-tree HEAD -- src/App.java
git ls-files --stage -- src/App.java
git diff -- src/App.java
```

The three commands can yield different results because they inspect three distinct states. If `git ls-tree` still shows the old blob while `git diff` shows new content, that is expected: the commit has not changed yet.

## 15. Practical walkthrough: tracing from commit to file content

Suppose you want to find which version of `src/main/App.java` is stored in commit `HEAD`.

1. Inspect the commit object:

   ```bash
   git cat-file -p HEAD
   ```

2. Get the tree ID referenced by the commit:

   ```bash
   git rev-parse 'HEAD^{tree}'
   ```

3. List entries in the root tree:

   ```bash
   git ls-tree HEAD
   ```

4. List files under `src/main`:

   ```bash
   git ls-tree -r HEAD -- src/main/
   ```

5. Check the file's object type and size:

   ```bash
   git cat-file -t 'HEAD:src/main/App.java'
   git cat-file -s 'HEAD:src/main/App.java'
   ```

6. Read the blob content:

   ```bash
   git cat-file -p 'HEAD:src/main/App.java'
   ```

This workflow traces from commit to tree, from tree to path, and finally to blob. You can do the same with older commits, tags, or other branches without checking them out.

## 16. Common mistakes

- **Running `cat-file -p HEAD` and expecting file contents.** `HEAD` is normally a commit object; use `HEAD:path` for a blob or `HEAD^{tree}` for a tree.
- **Confusing annotated tags with lightweight tags.** `cat-file -t` may return `tag` or `commit`; use `^{}` to peel a tag to its target object.
- **Assuming blobs store file names.** A blob only stores content bytes; names and modes live in trees.
- **Expecting `ls-tree` to show currently modified files.** The command reads snapshots in the object database, not the working tree or index.
- **Running default `ls-tree` and concluding a repository has no nested files.** By default it shows only direct entries; use `-r` to recurse.
- **Confusing object size with packfile disk size.** `cat-file -s` and `ls-tree -l` report payload size, not compressed storage size.
- **Printing binary blobs straight to the terminal.** Redirect to a file or use a tool built for that format.
- **Treating a gitlink as a submodule blob.** Mode `160000` is a commit referenced by the superproject; the child repository's contents live in its own repository.
- **Assuming object IDs are always 40 characters.** Repositories can use SHA-256; handle length according to the hash algorithm.

## 17. Key takeaways

`git cat-file` reads an object's type, size, and content; `git ls-tree` shows how a tree maps path names, modes, and object IDs. Starting from a commit, get the root tree with `^{tree}`, traverse paths with `ls-tree`, and read blobs with `cat-file`. Remember that blobs do not store file names, trees list only direct entries unless `-r` is passed, and these commands read stored snapshots rather than uncommitted index or working tree changes.
