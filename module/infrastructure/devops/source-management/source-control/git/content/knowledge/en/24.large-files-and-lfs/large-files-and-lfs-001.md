# Why Large Binary Files Cause Repository History to Grow Rapidly

A Git repository can start out very small and grow to gigabytes after a period of development. The cause is usually not just the current number of files, but also the versions of large files that have been recorded in commit history. A video file, design image, build output, dataset, or machine learning model can be modified many times; each committed version can significantly expand the object database.

Git is designed to manage source code history efficiently. For text files, versions typically share many identical lines, allowing Git to compress and store deltas effectively. For many binary formats, even a small semantic change can alter a large portion of the bytes in the file. When that happens, delta compression may not save much space. Replacing or deleting the file in a new commit also does not automatically remove old versions from history.

This lesson belongs to the **Large Files and LFS** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from working tree, staging area, commit, and history to branch, merge, rebase, remote, and tag; it also builds skills in collaborating through branches, resolving conflicts, tracking down changes, and recovering from mistakes while preserving important history. Understanding why a repository grows rapidly helps teams decide which data should be versioned directly and which data should be stored in an artifact management system or Git LFS.

## 1. How Do Binary Files and Text Files Differ?

Text files are typically organized into human-readable lines of characters, such as source code, YAML, JSON, Markdown, or configuration files. When a few lines are edited, most of the remaining content stays the same. This gives Git the opportunity to represent differences between versions as small change hunks.

Binary files store data in formats that cannot be processed simply as plain text. For example:

- PNG, JPEG, TIFF images and graphic design files.
- Video, audio, and media files.
- Large PDFs, slide decks, and binary documents.
- 3D models, CAD files, and engineering drawings.
- Machine learning datasets, checkpoints, and models.
- Archives, packages, installers, and build binaries.

Some binary formats have internal structures or built-in compression. When saved again after an edit, headers, index tables, metadata, or data offsets may shift, causing many bytes to differ even if the user only adjusted a small element. As a result, Git may not find a small delta corresponding to the actual change.

Not all binary files are equally hard to delta-compress. Some formats have stable structures or closely related versions that still produce good deltas. The key point is that efficiency depends on the format, how the tool generates the file, and the extent of changes between versions.

## 2. How Does Git Store Content in History?

Git manages content using objects. For a regular file, the content is stored in a blob. A tree describes file names, directories, and their corresponding blobs. A commit points to a tree representing the repository snapshot at the time of the commit.

For example:

~~~text
Commit A
  |
  +-- Tree A
       |
       +-- src/app.java
       +-- assets/design.bin  --> Blob X

Commit B
  |
  +-- Tree B
       |
       +-- src/app.java
       +-- assets/design.bin  --> Blob Y
~~~

If the content of <code>assets/design.bin</code> changes, the new snapshot will reference the blob representing the new content. The old commit still references the old snapshot. This is how Git preserves the ability to check out and compare history.

Git uses content hashes to identify objects. If two paths or two commits use the same file content, Git can reuse the same blob instead of storing another identical copy. However, if the content changes, the hash typically changes and Git must store the object corresponding to the new version.

This explains why a large file committed repeatedly can make a repository grow quickly: each distinct version of the content must be retained as long as the commit containing that version remains part of the history to be preserved.

## 3. Does Git Store Every Version of a File Uncompressed?

At the history model level, each commit points to its own snapshot and every content version must be recoverable. However, when Git packs objects into packfiles, Git can use compression and delta compression to store objects more efficiently.

Delta compression stores an object as the difference relative to another object instead of keeping the entire content independently. If two file versions are close, the delta can be small. This usually works well for many text changes because most lines remain unchanged.

For binary files:

- Pre-compressed files such as JPEG, MP4, or ZIP may have little room for additional compression.
- A small edit can change many byte regions due to internal encoding or compression algorithms.
- Export tools may rewrite metadata, chunk ordering, or index structures, making the content differ substantially.
- Some files have high entropy or scattered data, so two versions are semantically close but not close at the byte level.

Therefore, Git may have to store a large delta or store the object almost in full. You should not assume every commit always adds a full uncompressed copy, nor should you assume Git will compress every binary version down to a tiny change.

### Growth Illustration

Suppose a team manages a 120 MB design file and keeps 15 different versions. If the versions cannot be delta-compressed effectively, the data stored in history can approach the combined size of the retained versions, roughly 1.8 GB before accounting for overhead and other data.

If the versions share many identical byte regions and Git delta-compresses well, actual growth can be significantly lower. But with compressed files or files re-exported wholesale by a tool, growth can be close to the sum of all versions.

<escape>Illustrative example, not an exact prediction for every format:</escape>

| Retained versions | Size per version | Near-zero delta scenario |
|---:|---:|---:|
| 1 | 120 MB | 120 MB |
| 3 | 120 MB | 360 MB |
| 8 | 120 MB | 960 MB |
| 15 | 120 MB | 1,800 MB |

Actual packfile size depends on similarity between versions, compression, Git configuration, and object history. The table simply shows why a large file committed repeatedly can become a long-term storage cost.

## 4. Why Does Deleting a File Not Shrink the Repository Immediately?

Suppose you commit <code>assets/video-demo.mp4</code> in commit A, then delete that file in commit B:

~~~text
A: add assets/video-demo.mp4
|
B: delete assets/video-demo.mp4
~~~

In commit B's snapshot, the file path no longer exists. However, commit A still holds the snapshot containing that file. As long as commit A remains in history reachable from a branch, tag, or other ref, Git must keep the blob so that commit A can still be checked out.

Running:

~~~bash
git rm assets/video-demo.mp4
git commit -m "chore: remove demo video"
~~~

only removes the file from the current snapshot and subsequent commits. It does not remove the blob from earlier commits.

Similarly, adding a large file to <code>.gitignore</code> only prevents untracked files matching the pattern from being suggested in the future. It does not remove already-committed files and does not make existing history smaller.

### Does git gc Automatically Delete Old Large Files?

Garbage collection can clean up unreferenced objects once the appropriate expiration conditions are met. However, if a commit containing a large file is still reachable from a branch, tag, or other ref, the blob must still be kept.

Therefore, running:

~~~bash
git gc
~~~

is not a solution for removing a large file from still-referenced history. To eliminate the blob from the entire history, the team must rewrite history with an appropriate tool and coordinate updating all related clones.

## 5. Consequences of a Repository Containing Many Large Files

A large repository affects more than just the working directory size.

### Slow Clones and Fetches

When cloning a repository, Git must download the required objects according to the history scope and clone options. If the packfile is large, data transfer, decompression, and object writing take longer. Fetches may also have to download additional large objects whenever new history contains new file versions.

### Slow and Resource-Heavy CI/CD

Pipelines frequently check out the repository across many jobs or environments. A large repository increases job startup time, bandwidth usage, cache size, and storage costs. When runners create fresh clones frequently, the cumulative impact becomes much more pronounced.

### High Storage Needs for Every Team Member

Clones can contain a large object history. Users need disk space for the object database, working tree, build files, and caches. On laptops or constrained development environments, cloning a large repository can become a bottleneck.

### Heavier Backups, Mirrors, and Repository Transfers

Backup or mirror systems need to retain the object database and refs. As history bloats, backup duration, mirror transfer times, and repository restoration times also increase.

### Deleting Files in New Versions Does Not Solve History Cost

Even when the current working tree only contains small source code files, the object database can still be huge because old commits hold binary files. Current directory size and Git history size are two distinct measurements.

## 6. Distinguishing Working Tree Size from Object Database Size

The project folder size shown in File Explorer does not reveal the full cost of storing history. Two situations can occur:

- The current working tree is large because it holds datasets or outputs needed for the current run.
- The working tree is small, but the Git directory is large because history contains many versions of files already deleted from the current snapshot.

For a quick check:

~~~bash
# Object database size in human-readable form
git count-objects -vH

# Size of files in the current snapshot
git ls-tree -r -l HEAD

# Working directory size reported by the OS
# Use the operating system's disk usage tool in the project directory
~~~

<code>git count-objects -vH</code> reports the number of loose objects, loose object size, number of packs, and pack size. This gives an overview of the object database without directly identifying which files contribute the most.

<code>git ls-tree -r -l HEAD</code> lists the blobs in the current snapshot along with each blob's logical content size, not its actual packfile size. This command cannot find large files that were deleted in earlier history. To inspect history, you need to traverse objects reachable from refs.

## 7. Finding Large Blobs in History

One diagnostic approach is to list objects reachable from refs and retrieve blob sizes. For example, in Bash:

~~~bash
git rev-list --objects --all |
  git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' |
  awk '$1 == "blob" { print $3, $2, $4 }' |
  sort -nr |
  head -20
~~~

The output shows large blobs by object size, along with their hash and path if Git can provide it. A single blob may be referenced by multiple commits or paths; this list identifies candidates to review rather than automatically deciding what can be deleted.

In Windows PowerShell, you can retrieve and sort similar data:

~~~powershell
git rev-list --objects --all |
  git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' |
  ForEach-Object {
    $parts = $_ -split ' ', 4
    if ($parts.Count -ge 3 -and $parts[0] -eq 'blob') {
      [PSCustomObject]@{
        Bytes = [int64]$parts[2]
        Object = $parts[1]
        Path = if ($parts.Count -eq 4) { $parts[3] } else { '' }
      }
    }
  } |
  Sort-Object Bytes -Descending |
  Select-Object -First 20
~~~

To inspect details of a specific blob:

~~~bash
git cat-file -s <object-hash>
git cat-file -t <object-hash>
~~~

The first command prints the object size in bytes; the second confirms the object type. If you want to inspect binary content, avoid printing it directly to the terminal because the data may be unreadable. You can extract it to a temporary file in a suitable inspection environment.

### Checking Packfile Size

In a repository using packfiles, you can inspect:

~~~bash
git count-objects -vH
~~~

Common fields:

- <code>count</code>: number of loose objects.
- <code>size</code>: size of loose objects; with the <code>-H</code> option, Git displays human-readable units.
- <code>in-pack</code>: number of packed objects.
- <code>packs</code>: number of packfiles.
- <code>size-pack</code>: total packfile size; with the <code>-H</code> option, Git displays human-readable units.
- <code>prune-packable</code>: loose objects that already exist in a pack.
- <code>garbage</code> and <code>size-garbage</code>: invalid files recognized by Git in the object directory.

If deep packfile analysis is needed, you can run <code>git verify-pack -v</code> against a pack index file. Path conventions and wildcards differ between Bash and PowerShell; locate the pack index inside the repository's object directory before running it.

## 8. Deciding Which File Types Belong in Git

Not every large file has to be excluded from Git. Some small binaries or rarely changing assets are still appropriate to version directly. The decision should be based on size, change frequency, review needs, reproducibility, and history access requirements.

| Data type | Typically suitable storage | Reason |
|---|---|---|
| Source code and text configs | Standard Git | Clear diffs, easy-to-review history |
| Small icons, rarely changed graphics | Standard Git | Size and version count remain manageable |
| Large design files, frequently changed | Consider Git LFS | Keeps pointers in Git, stores large content via LFS |
| Large video, audio, or models | Git LFS or artifact storage | Avoids bloating the object database with every version |
| Large datasets, reproducible or re-downloadable | Object storage / data platform | Does not necessarily belong in source history |
| Build outputs, generated packages | Artifact registry or CI artifacts | Can be reproduced from source and pipeline |
| Temp files, caches, local logs | <code>.gitignore</code> | Not inputs that need versioning |

A helpful question is: if a team member checks out a commit from two years ago, do they genuinely need this exact file version to reproduce the project state? If yes, choose a reliable versioning mechanism. If no, artifact or dedicated storage may be more appropriate.

## 9. What Does Git LFS Solve?

Git Large File Storage (Git LFS) is an extension that manages large files by storing a small pointer file in Git while keeping the actual content on an LFS server. On checkout, Git LFS downloads the corresponding content if the environment has the proper configuration and access permissions.

Instead of storing the entire binary in a regular blob for each version, Git stores a pointer containing the LFS object identifier and size. This keeps the repository's object database lighter and reduces the volume of binary data transferred during routine Git operations.

Illustrative example of pointer content:

~~~text
version https://git-lfs.github.com/spec/v1
oid sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
size 104857600
~~~

The pointer is not the actual file content. It specifies which LFS object to fetch by identifier and size. If a machine cloning the repository cannot download LFS objects, the working tree may contain only the pointer instead of the full binary file.

### Switching to LFS Does Not Automatically Remove Old History

If large files were already committed before the team enabled LFS, merely adding tracking rules and re-committing the files will not automatically remove old blobs from history. Earlier commits still reference the regular binaries.

To eliminate old blobs from history, you need a migration workflow that rewrites history, verifies the result, updates the remote, and coordinates with everyone who has a clone. This affects commit hashes and any branches based on the old history. Specific migration work should be planned separately with backups and instructions for re-syncing clones.

## 10. Preventing Repository Bloat from the Start

The most effective preventive measures are usually applied before large files are committed:

1. Agree on file size limits and data types allowed in the repository.
2. Add <code>.gitignore</code> rules for build files, caches, logs, and reproducible outputs.
3. Use Git LFS for large file types that require versioning and receive frequent updates.
4. Move datasets or generated artifacts to an appropriate storage system.
5. Check file sizes before staging or committing.
6. Integrate size checks into code review or pre-commit hooks if the team needs them.
7. Document how team members install Git LFS and fetch LFS objects after cloning.

For example, to find large files in the working tree with Bash:

~~~bash
find . -type f -size +50M -not -path './.git/*' -print
~~~

In PowerShell:

~~~powershell
Get-ChildItem -File -Recurse |
  Where-Object { $_.Length -gt 50MB -and $_.FullName -notmatch '[\\/]\.git[\\/]' } |
  Sort-Object Length -Descending |
  Select-Object -First 30 FullName, Length
~~~

This only checks the current working tree. It does not find large files already deleted from the current snapshot that still exist in history; use the blob inspection approach from the previous section for that case.

## 11. Handling Large Files That Have Already Been Committed

When you catch a large file that was just committed but not yet pushed, you can fix the commit before sharing it:

~~~bash
# Remove file from the index while keeping its content in the working tree
git rm --cached -- assets/large-model.bin

# Add an appropriate rule to avoid staging it accidentally next time
# For example: assets/generated/

# Edit .gitignore and then verify
git status
git diff --staged
git diff
~~~

If the file is in the most recent commit and that commit has not been shared, you can amend the commit after verifying the index:

~~~bash
git add .gitignore
git commit --amend
~~~

This operation creates a new commit replacing the old one on the current branch. Only use it when others have not built on the commit or when the team has agreed to rewrite history.

If the large file has already been pushed or is on a shared branch, evaluate the impact before rewriting. You can create a new commit to remove the file from the current snapshot, though that does not shrink old history. To purge the blob from the entire history, you must rewrite history with a dedicated tool and coordinate updating the remote along with all affected clones.

### Why Should You Not Rewrite History Carelessly?

Rewriting history changes the hashes of affected commits and all recreated descendant commits. After force-pushing the rewritten history:

- Other team members' local branches may still be based on the old commits.
- Pull requests, tags, releases, and pipelines may reference the previous history.
- Existing clones may continue holding old blobs until cleaned up.
- Synchronization requires clear instructions, typically fetching and resetting or re-cloning according to a plan.

If the file contained secrets or credentials, in addition to cleaning history, you must revoke or rotate those secrets. Removing a blob from Git does not invalidate an exposed token.

## 12. A Pre-Commit File Evaluation Workflow

Before adding large assets to a repository, a team can apply a checklist:

- Does the file need to exist in every historical snapshot, or only be stored as an artifact?
- What is the file size and expected update frequency?
- Does the format delta-compress well, or is it typically pre-compressed?
- Do reviewers need to inspect content diffs, or only know the version and origin?
- Is it necessary to check out old versions of the file to reproduce a release?
- If using LFS or object storage, do all build environments have permission to download the data?
- Are there file size limit policies or storage quotas?
- Has the file been tracked previously, or is this its first time entering Git?

For example: a small SVG icon edited a few times is usually a good fit for standard Git because it is text-based and its diff is easy to review. An 800 MB video file re-exported every week is generally not suitable for storing directly in standard Git history. If individual versions need to be retained, LFS or artifact storage is the option to evaluate.

## 13. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| Git always stores a full uncompressed copy for every version | Git can use delta compression in packfiles; savings depend on the content |
| A small binary change always produces a small delta | Compressed files or binary structures where many bytes shift can produce large deltas |
| Deleting a file in a new commit shrinks the repository immediately | Old commits still reference the blob; history still needs to retain that content |
| Adding a file to <code>.gitignore</code> deletes the committed copy | Ignore does not untrack already-tracked files and does not modify history |
| Running <code>git gc</code> deletes all old binaries | Objects still reachable from refs must be preserved |
| Git LFS automatically migrates old commits | LFS requires a migration if you want to replace old blobs in history with pointers |
| Project folder size equals history size | The working tree and the object database are two separate things |
| Shallow clones solve all large-file problems | Shallow clones limit downloaded history, but do not replace a long-term binary management strategy |

## 14. Self-Check Exercises

Practice in a test repository:

1. Create a text file and a large binary file, then commit both.
2. Change a few lines in the text file and commit a new version.
3. Modify the binary file with an appropriate tool, commit again, and compare the object database growth.
4. Run <code>git count-objects -vH</code> before and after creating the commits.
5. Delete the binary file in a new commit, then check why the object database does not shrink immediately.
6. Use <code>git rev-list --objects --all</code> combined with <code>git cat-file --batch-check</code> to find large blobs in history.
7. Add an ignore rule for a new file and confirm that an already-tracked file does not automatically stop being tracked.
8. Create another test repository to observe Git LFS pointers and distinguish pointers from binary content.
9. Explain why migrating to LFS requires processing old history if the goal is to reduce the size of an existing repository.

Once you understand how snapshots, blobs, and packfiles work together, you can explain why a repository grows in size even when the current working tree is small. Evaluate file size and change frequency before committing binaries, use ignore rules for files that do not need versioning, and choose LFS or artifact storage when large data requires long-term management.
