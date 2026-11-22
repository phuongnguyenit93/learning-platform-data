# Rename Atomicity Is Not Power-Loss Durability

## 1. The Problem: "Rename Succeeded" Does Not Mean "Durably Saved"

In Java NIO.2, an application commonly updates a configuration or state file using the **write temporary file, then rename** pattern:

```text
Before:     config.json = old data
Prepare:    .config-123.tmp = new data
Publish:    rename .config-123.tmp to config.json
After:      another application opening config.json sees new data
```

This pattern reduces the chance that a reader sees the destination file **half-written**. Yet the question "do readers see an intact update while the system is running?" is fundamentally different from "after the machine loses power and reboots, does the update still exist?".

There are at least three distinct properties to distinguish:

1. **Rename atomicity:** for supported file operations, moving/renaming is a single atomic operation in the file system's namespace. Observers do not see a *half-renamed* state produced by that operation itself.
2. **Durability:** necessary bytes and metadata have been pushed down to storage per contract so they can be recovered after a crash or power loss.
3. **Application consistency:** published data is a complete version valid with respect to schema/checksum; related files satisfy invariants. An atomic rename does not validate content or create a multi-file transaction.

**Core conclusion:** `Files.move(source, target, StandardCopyOption.ATOMIC_MOVE)` can provide an **atomic rename** when supported by the provider; by itself, it is **not an `fsync` call**, nor does it promise that the new version survives a power-loss event.

Lesson goals: understand `ATOMIC_MOVE` and its interaction with `REPLACE_EXISTING`, distinguish `FileChannel.force(...)` from directory durability, design the "write → sync file → rename → sync directory" sequence according to platform rules, interpret demo outputs accurately, and avoid flawed crash-consistency assumptions.

## 2. Three Moments That Must Be Modeled Separately

Suppose `state.dat` currently contains `OLD` and the program wants to replace it with `NEW`.

```text
T0: target = OLD
             │
             ▼
T1: create temp file, write NEW (may still sit in cache)
             │
             ▼
T2: synchronize temp file data (if durability is required)
             │
             ▼
T3: atomic rename temp file → target
             │
             ▼
T4: synchronize directory/namespace metadata (if platform supports it)
             │
             ▼
T5: complete the application's durable-update policy
```

Question at **T3**: once the rename completes, how is the published target path observed?  
Question at **T5**: if a crash occurs immediately after the API returns, does the platform provide enough guarantees to recover the filename pointing to valid data?

These are two separate problems. A name change can become visible immediately in the running namespace, whereas changes to directory entries or file bytes still require synchronization for crash durability. Conversely, flushing the temp file **before** renaming cannot guarantee the final name has been durably persisted.

### 2.1. Distinguishing Application Crashes from Power Loss

- **Process crash**: the Java process stops, while the OS keeps running. Data in the page cache may continue being written to disk by the OS.
- **OS crash/kernel panic**: the operating system halts abnormally; unwritten page-cache contents may be lost.
- **Power loss**: sudden power failure; beyond the page cache, you must account for device write caches, firmware, controllers, file systems, journals, and actual storage drive guarantees.

Never test with `kill -9` on a process and read the file back as proof that the program is safe against *power loss*. That is a different failure mode from an abrupt OS or power shutdown.

## 3. `Files.move` and `StandardCopyOption.ATOMIC_MOVE`

Java NIO.2 provides:

```java
Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
```

Here `source` and `target` are resolved `Path` instances; illustrative examples must sit inside a method handling `IOException` with imports for `java.nio.file.Files`, `java.nio.file.Path`, and `java.nio.file.StandardCopyOption`.

Per Java SE 21:

- `ATOMIC_MOVE` requests that the move occur as **an atomic file-system operation**.
- If an atomic operation is unsupported for the source/target pair, the API throws `AtomicMoveNotSupportedException`; a typical cause is moving across different `FileStore` instances or different providers.
- When `ATOMIC_MOVE` is specified, **all other options are ignored**. Do not deduce that `ATOMIC_MOVE` plus `REPLACE_EXISTING` will always replace an existing target file.
- **If the target already exists**, whether an atomic move replaces the target or throws `IOException` is **implementation-specific**. Verify the contract/provider/runtime environment before using it to overwrite an existing file.
- When `ATOMIC_MOVE` is omitted, `Files.move` does not promise atomicity; if a move requires copy/delete, post-failure state can be complex and the target file may be incomplete.

**Important:** `Files.move` returning successfully does not mean Java invoked or completed `fsync` for the file and its associated directory entries. `ATOMIC_MOVE` is an *atomicity* request, not a *durability* option.

### 3.1. `REPLACE_EXISTING` Does Not Replace `ATOMIC_MOVE`

```java
Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
```

`REPLACE_EXISTING` only requests replacing an existing target within its contract and exceptions. It **does not guarantee** an atomic rename. With both options:

```java
Files.move(source, target,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
```

`ATOMIC_MOVE` causes the remaining options to be ignored per API specification. Do not describe this call as "guaranteed atomic overwrite on every OS". When the target already exists, replacement policy and related limits must be verified for the specific file system.

### 3.2. Why Place the Temp File Next to the Target?

`Files.createTempFile(target.getParent(), ...)` creates the temp file in the **same directory** as the target. This avoids having the default temp file land on a different drive where atomic rename is impossible.

However, "same directory" is **not absolute proof** that the provider supports `ATOMIC_MOVE`. Permissions, file system type, mounts, target state, and provider behavior still govern success. Use the API properly and handle `AtomicMoveNotSupportedException`.

## 4. What Does Atomicity Guarantee to Running Readers?

Suppose the rename is atomic and the file system executes it successfully. Readers that opened the target path **before** the rename may hold handles to the old version, whereas readers opening **after** the rename may obtain the new version, depending on OS/provider and application semantics.

What is protected is that **the name-change step** is not implemented as a sequence of operations exposing a half-renamed state. However:

- It does not guarantee that all readers holding old file handles immediately see new contents.
- It does not stop another program from directly modifying the target file or temp file at the same time.
- It does not make writes to **the same open file** atomic; write complete data to the temp file before publishing.
- It does not guarantee atomicity if an update spans multiple files or multiple distinct paths.
- It does not validate JSON syntax, checksums, or business rules.
- It says nothing by itself about survival across power loss.

**Comparison:** overwriting the target directly with `TRUNCATE_EXISTING` and writing in chunks can expose an empty or partial file to readers. Writing completely to a temp file and then using a supported atomic move avoids the *publishing partial contents* problem for path-based observations under suitable conditions.

## 5. `FileChannel.force(boolean)` and File Content Durability

Java provides a way to request flushing file data down to the device:

```java
try (FileChannel channel = FileChannel.open(
        temp,
        StandardOpenOption.WRITE)) {

    // After writing bytes via channel...
    channel.force(true);
}
```

This is an illustrative snippet with `temp` as a valid `Path`; import `FileChannel` and `StandardOpenOption`, in a method handling `IOException`. Passing `true` requests flushing **content together with relevant metadata** of the file within contract scope; `false` requests content only, not necessarily metadata.

Key conditions and limits in Java SE:

- When the file resides on a **local storage device**, `force(...)` provides guarantees for changes made to the file per the `FileChannel` contract.
- For files on **non-local** devices such as some network filesystems, Java **does not make the same guarantee**.
- Java's `FileChannel.force` guarantees only changes made through the channel's methods and API-specified paths. Do not assume it flushes everything written elsewhere by other code/providers.
- If the file is modified through a `MappedByteBuffer`, `channel.force(...)` may **not** flush changes made through the mapping; use `mapped.force()` per the buffer's contract.
- `force(true)` can incur expensive I/O. Use it deliberately at commit points rather than after every byte unless required.
- Success of `force(true)` **on the file** does not mean the `target` name entry after renaming is already durable on storage.

### 5.1. Common Mistake: Calling `force` Before Rename Without Distinguishing Scope

Suppose you write completely to `temp`, call `channel.force(true)`, and then rename. At the time of `force`, Java requests synchronizing the **temp file**; the **rename happens afterward**, modifying the directory entry. Thus, forcing before the rename cannot "pre-sync" a namespace change that has not happened yet.

Even if you reopen `target` and call `force(true)`, `FileChannel.force`'s contract covers changes to the **file managed by the channel**; it **does not provide a portable synchronization API for the renamed directory entry**. Do not assume `FileChannel.force(true)` on the final file suffices to guarantee the parent directory is durably persisted.

## 6. The Parent Directory Also Holds Metadata That Must Be Persisted

In a file system, the association between the **name** `state.dat` and the underlying file object lives in directory metadata. Renaming modifies directory entries.

On Linux/POSIX, the `fsync(2)` manual explicitly states: calling `fsync` on a **file** does not necessarily ensure the entry in the **directory containing the file** has reached disk; for that guarantee, `fsync` must also be called on a file descriptor for the directory.

Therefore, a strong update sequence on a supporting system typically looks like:

```text
1. Create temp file in the same directory as target.
2. Write all new data to the temp file.
3. fsync/force temp file to persist content (+ necessary metadata).
4. Atomically rename temp file to target name.
5. fsync parent directory to persist the name change in the namespace.
6. Only then confirm the durable update per platform policy.
```

This is an **OS-level procedure**, not a promise that Java `Files.move` performs steps 3 and 5 automatically. If a rename crosses **two different directories**, the durability policy may need to sync both source and destination directories. Keeping temp in the same directory makes the workflow easier to control.

### 6.1. Can You Open a Directory with `FileChannel` and Call `force(true)` on Every OS?

**There is no such portable guarantee in Java SE 17/21.** Opening a directory as a `FileChannel` depends on the OS, provider, and permissions. Nor is `FileChannel.force` a universally defined Java API for syncing directory-entry changes made by `Files.move`.

An example you might encounter in Linux-specific code:

```java
// Platform-specific illustration; not a portable Java solution.
try (FileChannel dir = FileChannel.open(
        directory, StandardOpenOption.READ)) {
    dir.force(true);
}
```

The snippet above **must not** be used to claim "guaranteed rename durability on Windows/macOS/Linux with Java NIO.2". A system with strict power-loss requirements should use a verified OS/platform adapter for directory `fsync`, or a storage protocol/engine offering an appropriate durability contract, while testing on real hardware, file systems, and deployment configurations.

### 6.2. Even a Journaled Filesystem Does Not Eliminate the Problem

A journal can help recover metadata after a crash, but journaling policies differ: data/metadata ordering, mount modes, device cache flushing, barriers, snapshots, network servers, and crash-recovery semantics all vary.

You cannot infer "journaled filesystem" ⇒ every `Files.move(ATOMIC_MOVE)` is durable across power loss. When designing for critical data, inspect the platform/filesystem contract, including the possibility that hardware reports a successful flush without actually persisting data as expected.

## 7. Runnable Java 17+ Example: Write Temp, Force, Request Atomic Rename

This example demonstrates supported Java NIO operations and marks **the boundaries of their guarantees**. To avoid depending on existing-target replacement behavior (which is implementation-specific), the program targets a **nonexistent target path** inside a dedicated temporary directory.

**File:** `AtomicRenameDemo.java`

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;

public class AtomicRenameDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("atomic-rename-");
        Path target = directory.resolve("state.txt");
        Path staging = null;

        try {
            staging = Files.createTempFile(directory, ".state-", ".tmp");

            byte[] payload = "READY".getBytes(StandardCharsets.UTF_8);
            try (FileChannel channel = FileChannel.open(
                    staging, StandardOpenOption.WRITE)) {

                ByteBuffer buffer = ByteBuffer.wrap(payload);
                while (buffer.hasRemaining()) {
                    channel.write(buffer);
                }

                channel.force(true); // Flush staging file content and metadata.
            }

            System.out.println("before move exists: "
                    + Files.exists(target));

            try {
                Files.move(staging, target,
                        StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException ex) {
                System.out.println("atomic move: unsupported");
                return; // Do not silently fall back to a regular move.
            }

            System.out.println("after move: "
                    + Files.readString(target, StandardCharsets.UTF_8));
            System.out.println("staging exists: "
                    + Files.exists(staging));

            // This demonstrates atomic move + force(file) only.
            // Java SE does not guarantee portable parent-directory fsync.
        } finally {
            // Clean up only files created by the demo.
            if (staging != null) {
                Files.deleteIfExists(staging);
            }
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile and run in the directory containing the source file:

```bash
javac AtomicRenameDemo.java
java AtomicRenameDemo
```

**Expected stdout when the filesystem supports `ATOMIC_MOVE`:**

```text
before move exists: false
after move: READY
staging exists: false
```

**If the provider does not support atomic move**, output follows the other branch:

```text
before move exists: false
atomic move: unsupported
```

Explanation:

1. `createTempDirectory` creates an isolated directory, and `createTempFile(directory, ...)` places the staging file in the **same directory** as target.
2. `"READY"` is UTF-8 encoded and written in a `while (buffer.hasRemaining())` loop because a single `channel.write` is not guaranteed to write everything.
3. `channel.force(true)` is called while the channel is still open, after bytes were written through that exact channel.
4. `Files.move(..., ATOMIC_MOVE)` requests an atomic rename. If impossible, the example reports `unsupported` and **does not silently downgrade**.
5. On the success branch, target contains the full string `READY` and the staging path no longer exists.
6. Finally, the program cleans up temporary files. Successfully opening/reading the file proves the content is currently visible, **not** that the directory entry is durably synced across power loss.

**Note:** even on a filesystem supporting `ATOMIC_MOVE`, I/O can still fail for other reasons (permissions, disk full, device error, failure deleting temp files...). The program lets `IOException` propagate rather than promising fixed stdout for every environment error.

### 7.1. Why Doesn't the Demo Call `Files.move(..., REPLACE_EXISTING)` When `ATOMIC_MOVE` Fails?

Because the example's requirement is **never to publish an update via an operation lacking atomicity guarantees**. Falling back to a normal move breaks the `ATOMIC_MOVE` guarantee that "readers only see a complete version".

In a real application, you might permit a weaker fallback, but that must be an **explicit business decision** with distinct status reporting, error behavior, and recovery procedures; it cannot carry the same "atomic commit" label.

## 8. Overwriting an Existing Target: Complexities to Handle

The "initial write" case (target does not exist yet) is simpler than "replacing an active version". To replace an existing `settings.json` with a new version:

```text
T0: target = version A
T1: staging = valid version B
T2: sync staging
T3: atomic rename staging → target (if platform supports overwrite)
T4: sync parent directory per platform
```

**Do not assume** `Files.move(staging, target, ATOMIC_MOVE, REPLACE_EXISTING)` always replaces A with B. Because `ATOMIC_MOVE` causes other options to be ignored, when target already exists, **whether it replaces or fails is implementation-specific**.

A production design needs to:

- Clearly verify the OS, filesystem, provider, and atomic-replace support on existing targets.
- Check permissions, symlink policy, hard links, and races with other processes.
- Write a complete temp file and validate content before publishing.
- Check the results of `force` and rename; never report "committed/durable" if a required step failed.
- Ensure post-crash recovery can distinguish valid versions, old versions, temp files, or missing states.
- When strong durability is required, implement platform-appropriate directory synchronization.

**Consistency principle:** atomically renaming a single target **does not** switch a group of files (such as `config.json` and `index.json`) together in one transaction. When multiple files must be published consistently, consider writing immutable versioned files and then atomically updating **a single manifest/pointer file**, paired with suitable durability/recovery policies.

## 9. Table: "What Was Done?" vs. "What Is Guaranteed?"

| Operation | What Property Improves? | What Is Not Automatically Guaranteed? |
|---|---|---|
| `Files.write(...)` to target | Writes file contents | Neither atomic publish nor guaranteed durable |
| Writing a complete temp file | Produces an isolated version B for validation | Target not yet published; not necessarily durable |
| `channel.force(false)` | Flushes content per `FileChannel` | May not flush metadata; does not sync rename entry |
| `channel.force(true)` | Flushes content and file metadata per contract | Does not sync directory entry of a subsequent rename |
| `Files.move(temp,target,ATOMIC_MOVE)` | Requests atomic namespace move when supported | Does not `fsync` file/directory; does not always replace existing target |
| `Files.move(temp,target,REPLACE_EXISTING)` | Requests replacing target when supported | Does not promise atomicity without `ATOMIC_MOVE` |
| Platform-specific native `fsync(parentDir)` | Can make directory-entry update durable per OS contract | Does not fix unsynced payloads or hardware faults |
| `FileLock` | Coordinates cooperating concurrent accesses per file-lock semantics | Neither atomic rename nor a durability mechanism |
| `close()` channel | Releases resources; may flush related layers per their contracts | Not equivalent to a guaranteed `force(true)` in all cases |

### 9.1. Why Can't `close()` Replace an `fsync` Policy?

Closing a `Writer`/`OutputStream` may push in-process buffers down to the I/O channel, but Java does not claim every `close` equals `FileChannel.force(true)` for data and metadata durability. Call the proper sync API explicitly when durability is required. Even then, directory entries must still be handled if business requirements demand renames survive power loss.

### 9.2. `StandardOpenOption.SYNC` and `DSYNC`

When opening a file for writing, Java supports:

- `SYNC`: requires every update to content **or metadata** to be written synchronously to the underlying storage device.
- `DSYNC`: requires updates to **content** to be written synchronously to the underlying storage device; metadata does not necessarily follow unless needed to retrieve the data.

These are **file-open options**, not `Files.move` options:

```java
try (FileChannel ch = FileChannel.open(
        staging,
        StandardOpenOption.WRITE,
        StandardOpenOption.SYNC)) {
    // Write content under SYNC policy.
}
```

Illustrative example with an existing `staging` file; options depend on the provider and sync overhead can be high. `SYNC` or `DSYNC` **does not automatically sync the directory entry of a subsequent rename**. On network filesystems, ultimate durability still depends on the underlying system's contract.

## 10. Post-Crash Outcomes: Never Infer from a Single API Call Alone

We must analyze by failure point and OS/file-system assumptions.

| Failure Moment | What Was Observed While Running? | What to Account for During Recovery |
|---|---|---|
| Before staging is fully written | Old target has not published new version | Staging may lack data; accept only validated files |
| After writing staging, before file sync | Staging B may be readable | Bytes of B may not be durable yet |
| After syncing staging, before rename | Staging B requested durable write | B is not yet at target name; needs recovery cleanup/resume |
| After atomic rename, before directory sync | Target B may be visible immediately | Never assume directory entry B survives power loss |
| After file sync + rename + directory sync per contract | Durable commit steps executed per platform | Still subject to device/OS limits and app-level data recovery |

This table is a **risk analysis model**, not a deterministic prediction that "after power loss only A or B can exist" on every file system. Java SE does not specify crash-recovery semantics for individual devices/providers. Never claim the old or new target is certain to exist when required sync steps are missing.

### 10.1. Does One Target Name Equal One Transaction?

If the new file holds multiple records, atomic rename switches only **the name pointer** from the old version to the new version at an observable point in the filesystem. File validity still requires checksums, versions, lengths, schemas, and structural checks. If the application also updates a database, message queue, or multiple files, rename does not guarantee atomicity across those resources.

For example: writing `state.json` and then sending a message "version 2 is ready" before ensuring durability. After a power loss, the message may have reached the consumer while the file namespace change was lost, creating inconsistency. Design commit ordering and recovery properly.

## 11. Testing and Error Handling in Real Applications

### 11.1. Never Swallow `AtomicMoveNotSupportedException`

```java
try {
    Files.move(staging, target,
            StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException ex) {
    // Policy: return an explicit error, or
    // execute a fallback with separately documented weaker guarantees.
    throw ex;
}
```

This is an illustrative snippet inside a method handling `IOException`. Never switch to `Files.move(..., REPLACE_EXISTING)` and still log "atomic update succeeded". If the product chooses a fallback, emit distinct signals in logs/metrics as well as API documentation.

### 11.2. Be Careful About Cleanup on Error

If writing staging fails, an incomplete file may remain. If rename has not occurred, clean up staging per policy and keep the old target. If rename succeeded, never assume staging still exists at its old path. Example pattern:

```java
Path staging = Files.createTempFile(parent, ".update-", ".tmp");
try {
    // Write all bytes, force, validate, atomic rename ...
} finally {
    Files.deleteIfExists(staging);
}
```

This is an illustrative snippet inside a method handling `IOException`. `finally` runs while the process can still execute Java bytecode, not if the machine loses power. Cleanup must touch only files created by the program and never delete target after publication.

### 11.3. Testing Failure Modes Without Destroying Real Data

- Unit tests with temporary directories can verify successful rename branches, permissions, exception handling, final content, and cleanup.
- Integration tests on the real filesystem can verify atomic move support and existing-target replacement behavior.
- Concurrent-reader tests can uncover publication protocol bugs, but **do not prove** power-loss durability.
- Crash/power-loss tests require dedicated test environments, recovery logic, and real measurement. Never pull the plug on production servers to speculate.
- If the provider lacks atomic move or reliable directory sync, the system must downgrade its advertised guarantees or adopt a different storage design.

## 12. Common Mistakes

1. **"`ATOMIC_MOVE` means the data is durable."** False: namespace atomicity and storage durability are two separate properties.
2. **"`FileChannel.force(true)` before rename suffices to persist the final name."** False: rename updates the directory entry **after** the file force.
3. **"Closing a file automatically equals file `fsync` and directory `fsync`."** `close` offers no such portable guarantee.
4. **"`ATOMIC_MOVE + REPLACE_EXISTING` always atomically overwrites."** Java specifies other options are ignored; existing targets behave per implementation.
5. **"Same directory guarantees atomic rename."** It only increases compatibility; the provider can still refuse.
6. **"Moving without `ATOMIC_MOVE` is still atomic on every OS."** Not promised by contract.
7. **"If `Files.move` returns success, power-loss recovery is guaranteed to keep the new version."** Insufficient; scoped sync steps and platform contracts are needed.
8. **"File `fsync` = parent directory `fsync`."** On Linux, they are distinct; the directory entry requires its own sync for appropriate guarantees.
9. **"`FileChannel.open(dir).force(true)` is portable directory `fsync`."** Java SE provides no such universal contract.
10. **"Every device honors flushes faithfully."** Real durability depends on OS, firmware, controller, filesystem, and hardware.
11. **"Rename maintains transactions across multiple files."** A single rename does not atomically commit a group of files or a database.
12. **"Killing the process and seeing the file intact proves power-loss safety."** A process crash is not equivalent to an OS crash or power loss.
13. **"Temp files in `java.io.tmpdir` can still atomically move to the destination."** Default temp may reside on a different file store.
14. **"A single `channel.write` call is enough."** NIO writes can be partial; loop until `ByteBuffer` is exhausted.
15. **"Using `FileLock` instead of sync."** Locks coordinate access; they do not create durability.
16. **"'Staging B is readable' means 'B is durable'."** Bytes may only be in the page cache.
17. **"Journaling guarantees applications never see corrupted files."** Depends on filesystem mode and data-write policies, plus application-level framing.
18. **"No recovery needed because atomic rename was used."** Version/checksum checks and cleanup/recovery for temp/old files are still required.
19. **"`force(false)` always covers all needed metadata."** `false` does not require flushing all metadata; check actual requirements.
20. **"No I/O errors means maximum guarantees were achieved."** APIs promise only within defined scopes; unspecified parts must be evaluated separately.

## 13. Self-Check Questions

**Question 1.** `Files.move(temp,target,ATOMIC_MOVE)` succeeds. Does that guarantee the new target survives power loss?  
**Answer:** No. It requests an atomic namespace move; it does not ensure file contents and the directory entry were durably persisted.

**Question 2.** If target exists, must `ATOMIC_MOVE` replace it?  
**Answer:** No. Java's contract leaves replacement or failure to the implementation; other options like `REPLACE_EXISTING` are ignored when `ATOMIC_MOVE` is set.

**Question 3.** Why is writing temp in the same directory helpful?  
**Answer:** It avoids one cause of non-atomic moves: source and target residing on different file stores. You still must verify provider support.

**Question 4.** What does `FileChannel.force(true)` on temp before rename accomplish?  
**Answer:** Under the local-storage and channel-write contract, it requests flushing file content and metadata. It does not sync the rename that occurs afterward.

**Question 5.** On Linux, why consider `fsync` on the parent directory after renaming?  
**Answer:** Because `fsync` on a file does not automatically persist its name entry in the directory; renaming modifies the directory's namespace metadata.

**Question 6.** Does Java SE 17/21 provide a portable directory `fsync` API guaranteed across all OSes?  
**Answer:** No such guarantee exists from `Files.move` or `FileChannel.force`; evaluate a platform-specific solution if that guarantee level is required.

**Question 7.** If `ATOMIC_MOVE` is unsupported, can we call `REPLACE_EXISTING` and report "atomic update" success?  
**No.** That mode provides weaker guarantees; if falling back, revise the published contract accordingly.

**Question 8.** Is calling `channel.force(true)` after editing through `MappedByteBuffer` sufficient?  
**Answer:** `FileChannel.force` may not flush modifications made through a mapped buffer; see `MappedByteBuffer.force()`.

**Question 9.** How do you distinguish a process-crash test from a power-loss test?  
**Answer:** A process crash leaves the OS running to continue flushing caches; power loss cuts off cache flushing too, leading to different conclusions.

**Question 10.** When updating multiple files to the same version concurrently, do per-file atomic renames form one transaction?  
**No.** You need a dedicated protocol such as immutable snapshots + manifest/pointer commit, or a verified transactional storage engine.

## 14. Key Takeaways and Official Documentation

**One sentence to remember:** *Rename atomicity is a property of name publication; durability is a property of data/metadata surviving crashes. To achieve both, you must design the full chain of file writing, file syncing, atomic renaming, and directory syncing per platform contracts.*

References:

- Java SE 21 — `Files.move`, `ATOMIC_MOVE`, and `REPLACE_EXISTING`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html
- Java SE 21 — `StandardCopyOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardCopyOption.html
- Java SE 21 — `FileChannel.force(boolean)`, `SYNC`, and `DSYNC`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 21 — `StandardOpenOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html
- Linux man-pages — `fsync(2)`, especially notes on synchronizing the directory containing a file: https://man7.org/linux/man-pages/man2/fsync.2.html