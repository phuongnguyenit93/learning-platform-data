# `ATOMIC_MOVE` and When It May Not Be Supported in Java NIO.2

## 1. The Problem to Solve

When renaming, publishing, or replacing a file, an application often wants readers **not to observe a half-completed move state**. Java NIO.2 provides the `StandardCopyOption.ATOMIC_MOVE` option for `Files.move(source, target, options...)` to request that the file system perform the move as **a single atomic operation**.

For example: a tool generates a new configuration file in a temporary file and then moves it to `config.json`. The goal is to prevent a reader opening the target at the exact moment of transfer from seeing a destination file containing only half the content.

However, `ATOMIC_MOVE` **is not a guarantee of always succeeding**:

- The operating system, `FileSystemProvider`, file store, mount configuration, permissions, and object type can all affect it.
- If an atomic move cannot be performed, the API throws `AtomicMoveNotSupportedException`.
- If the target path already exists, Java **does not guarantee** that an `ATOMIC_MOVE` will replace the target: the provider may replace it or throw `IOException`, depending on the implementation.
- An atomic move with respect to name/visibility **does not mean** the content is durably persisted to the storage device across power loss; these are two distinct requirements.

This lesson belongs to **Java Core I/O → File Locking and Durability**. After this lesson, you will accurately understand the `ATOMIC_MOVE` contract, cases where it is impossible, the meaning of its exceptions, permission-aware file publication strategies, and how to distinguish **atomicity**, **visibility**, **durability**, and **consistency**.

## 2. How `Files.move` and `ATOMIC_MOVE` Work

API signature:

```java
Path result = Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
```

This is an illustrative snippet placed inside a method that can throw `IOException`; `source` and `target` are appropriate `Path` instances.

`Files.move` moves or renames a file entry. With the `ATOMIC_MOVE` option, Java requests the operation to execute as an **atomic file-system operation**: another application observing the rename/move does not see a sequence of intermediate states of the move operation itself.

Typical model when the target file does not yet exist:

```text
Before:
  work/new.tmp    -> contains complete data
  work/result.dat -> does not exist yet

Files.move(new.tmp, result.dat, ATOMIC_MOVE)

After success:
  work/new.tmp    -> no longer exists
  work/result.dat -> appears with complete data
```

This illustrates an operation changing a single filename, **not a multi-file transaction**. If you need to update `data.bin` and `index.json` simultaneously, a single `ATOMIC_MOVE` does not turn those two changes into one unified transaction.

### 2.1. Exact Contract of `ATOMIC_MOVE`

According to the Java SE 17/21 documentation for `Files.move`:

1. `ATOMIC_MOVE` requests moving as an atomic file-system operation.
2. **All other move options are ignored** when `ATOMIC_MOVE` is present.
3. If the target already exists, the provider **decides** whether to replace the target or throw `IOException`. There is no cross-platform promise for replacement.
4. If an atomic move cannot be performed, `AtomicMoveNotSupportedException` is thrown—for instance, when copying across two different file stores would be required or when the paths belong to different providers.
5. Even when both paths reside on the same file store, the operation can still fail due to provider policy/mechanisms or other I/O errors.

Key phrase to remember: `ATOMIC_MOVE` is a **requirement for atomicity**, not "try atomic, and if unsupported let Java silently fall back to copy then delete".

## 3. Comparing Standard Move, Replace, and Atomic Move

| Call | Intent | When Target Already Exists | Atomicity Guaranteed? |
| --- | --- | --- | --- |
| `Files.move(src, dst)` | Default move/rename | Usually fails, except same-file or provider rules | No |
| `Files.move(src, dst, REPLACE_EXISTING)` | Permits replacing target if supported | Replaces within API limits; non-empty directories cannot be replaced this way | No |
| `Files.move(src, dst, ATOMIC_MOVE)` | Requests atomic move | May replace or fail depending on provider | Yes, if **completed successfully under provider contract** |
| `Files.move(src, dst, ATOMIC_MOVE, REPLACE_EXISTING)` | Still an atomic move request | **`REPLACE_EXISTING` is ignored**; same as row above | Yes, if the atomic operation completes properly |

The values above are `StandardCopyOption.ATOMIC_MOVE` and `StandardCopyOption.REPLACE_EXISTING`. In abbreviated tables/examples, the two enum constants are written without the class name when context is clear.

The easiest mistake to make:

```java
Files.move(staging, finalPath,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
```

Never comment this line as "guaranteed atomic overwrite". Java's contract states that `ATOMIC_MOVE` causes **all other options to be ignored**, while existing-target replacement behavior is implementation-dependent. Writing it this way cannot turn a platform that lacks atomic replacement support into one that supports it.

## 4. What Exception Is `AtomicMoveNotSupportedException`?

Full exception name:

```java
java.nio.file.AtomicMoveNotSupportedException
```

It extends `FileSystemException`, which extends `IOException`. It is a **checked exception**. When calling `Files.move`, the program must handle or declare `IOException` or its relevant subclasses.

Example:

```java
try {
    Files.move(source, destination, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException e) {
    // Atomicity is not supported for this move.
    // Decide per business rules: fail or use a non-atomic approach.
}
```

This snippet must be placed in a method handling remaining `IOException` cases with appropriate `java.nio.file.*` imports. Do not catch every `IOException` and assume "ATOMIC_MOVE is not supported".

| Exception | Possible Meaning | Response |
| --- | --- | --- |
| `AtomicMoveNotSupportedException` | Atomic move cannot be performed in this context | Do not assume the move occurred; apply fallback policy or fail |
| `FileAlreadyExistsException` | Target already exists and provider cannot/refuses to replace in that situation | Check conflict policy; do not blindly overwrite |
| `AccessDeniedException` | Insufficient permissions to modify entry/directory or access restriction | Check permissions and whether the file is in use |
| `NoSuchFileException` | Source or a required path component is missing | Review path construction and concurrent changes |
| `DirectoryNotEmptyException` | Cannot replace a non-empty target directory under API rules | Do not turn this into an unintended recursive delete |
| Other `IOException` | I/O, file system, lock, network, or provider error | Inspect type and cause; make no assumptions about post-error state |

For non-atomic moves, the Javadoc notes that if an `IOException` occurs, **the state of source/target is unspecified**: both may exist or target may be partially copied. Thus, a non-atomic fallback requires a **recovery policy**, not merely a single API call.

## 5. Why Might Atomic Move Not Be Supported?

### 5.1. Moving Between Two File Stores

Renaming a file within the same file store can usually be executed by the provider using an OS rename primitive. However, when source and target belong to different file stores, moving may require:

```text
Source filesystem A                  Destination filesystem B
          |                                     ^
          +---- copy bytes / metadata ----------+
          |
          +---- delete old file when finished
```

A copy-then-delete sequence involves multiple steps; an observer may see the target mid-copy, or the system may fail midway. Java cannot promise this entire sequence as a universal atomic file-system operation.

Examples include Windows moving from one volume to another; Unix/Linux moving across two different mounts; or data inside a ZIP file-system provider moving to the default file system.

**Note:** "same physical disk" does not equal "same `FileStore`". Mount points, partitions, network filesystems, and providers can have separate rules. And **being on the same `FileStore` is only a favorable precondition**, not a certificate that atomic move will definitely succeed.

### 5.2. Different Providers and File Systems

A `Path` in Java belongs to a `FileSystem`; a `FileSystem` is created by a `FileSystemProvider`. File systems such as ZIP/JAR or virtual providers may not support atomic renames like the default file system.

`Files.move` can work across providers per API design, but when `ATOMIC_MOVE` is requested, cross-provider data transfer may have no common atomic primitive.

### 5.3. Other Practical Limitations

Even within the same file store, the operation can fail due to permissions, file locks, provider capabilities, entry types (directory/file/symlink), Windows sharing rules, network FS limits, or races with other processes. Do not assume all failures appear as `AtomicMoveNotSupportedException`: many surface as other `IOException` subclasses.

## 6. Runnable Java 17+ Example: Require Atomic, Explicitly Labeled Fallback

This example creates a staging file in the same directory as the target, writes full content, and attempts `ATOMIC_MOVE`. The target intentionally **does not yet exist** to avoid depending on the provider's replace-target rules. If atomic move is unsupported, the demo chooses a regular move fallback to illustrate the failure branch; this is printed explicitly.

Create the file `AtomicMoveDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class AtomicMoveDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("atomic-move-");
        Path staging = Files.createTempFile(directory, "stage-", ".tmp");
        Path target = directory.resolve("published.txt");

        try {
            Files.writeString(staging, "version-2", StandardCharsets.UTF_8);

            try {
                Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE);
                System.out.println("mode: atomic");
            } catch (AtomicMoveNotSupportedException ex) {
                // Only this demo accepts downgraded guarantees to still produce output.
                // Real applications must choose this policy deliberately.
                Files.move(staging, target);
                System.out.println("mode: non-atomic fallback");
            }

            System.out.println("content: "
                    + Files.readString(target, StandardCharsets.UTF_8));
            System.out.println("staging exists: " + Files.exists(staging));
        } finally {
            Files.deleteIfExists(staging);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
```

Execution commands:

```bash
javac AtomicMoveDemo.java
java AtomicMoveDemo
```

When the provider supports `ATOMIC_MOVE`, stdout:

```text
mode: atomic
content: version-2
staging exists: false
```

If the provider refuses atomic move but allows a standard move, stdout instead:

```text
mode: non-atomic fallback
content: version-2
staging exists: false
```

Both outcomes are valid under their respective conditions. If another error occurs (permissions, file in use, I/O error), the program may terminate with an exception instead of printing those lines. This demo does not prove that every machine supports atomic moves.

**Explanation:** `Files.createTempFile(directory,...)` places staging in the same parent directory as target, increasing the chance an atomic rename is allowed; the program does not promise it. When the move succeeds, the staging name disappears and target holds `version-2`. In the fallback branch, atomicity **is not guaranteed**, even though post-completion inspection looks identical. A single run's result reflects only that environment and operation, not proof that a provider supports atomic moves in all situations.

Note that temporary paths depend on the OS; the demo avoids printing random path names so stdout stays comparable.

## 7. File Publication Design: Complete Staging First, Move After

An application updating configuration or data commonly uses this workflow:

```text
[1] Create staging in target directory
          |
[2] Write full content, validate data
          |
[3] If durability required: force staging data
          |
[4] Close write handle
          |
[5] Files.move(staging, target, ATOMIC_MOVE)
          |
[6] On success: target is published
    On unsupported/error: follow policy, log, and clean up staging carefully
```

This is the **staging + publish** model:

- Readers never use staging as their primary data source.
- Only once content is fully prepared is it renamed to the official path.
- The goal of an atomic move is that no intermediate state of the rename itself is observable.
- Clearly define what happens if target already exists; Java does not promise atomic replacement on every provider.
- If the application stores multiple related files, use versioning/manifests or another publication protocol rather than assuming independent moves form a whole transaction.

### 7.1. Strict Pattern: Require Atomic, Fail If Missing

When atomicity is a **mandatory** requirement, treat `ATOMIC_MOVE` as a precondition:

```java
import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

static void publishStrict(Path staging, Path target) throws IOException {
    try {
        Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE);
    } catch (AtomicMoveNotSupportedException e) {
        throw new IOException(
                "Cannot publish atomically: " + staging + " -> " + target, e);
    }
}
```

This is an **illustrative method** placed inside a Java class with corresponding imports. It handles only that specific exception branch; other `IOException`s propagate. The caller is responsible for managing staging, errors, and existing targets. Never switch to a regular `Files.move` after an atomic request fails, as that weakens the publication function's contract.

### 7.2. Downgraded-Guarantee Pattern: Intentional Fallback

When business requirements tolerate a non-atomic move phase, you may catch `AtomicMoveNotSupportedException` specifically and then use `Files.move(source,target)` or `REPLACE_EXISTING` per policy.

However, document clearly:

1. Fallback **forfeits the atomicity guarantee**.
2. In the non-atomic branch, if an `IOException` occurs, source/target state **may be incomplete or indeterminate**.
3. Does policy allow an existing target to be replaced? If so, is losing the old version acceptable if the program crashes midway?
4. Is recovery needed from a staging/backup copy, hash verification, state markers, or reconciliation on the next run?
5. If the system has multiple parallel writers, who is authorized to publish the final version?

Do not catch all `IOException`s and always retry non-atomically: permission or disk-full errors will not be solved by changing options and may further corrupt state.

## 8. `ATOMIC_MOVE` with an Existing Target: A Major Pitfall

Suppose source holds the new version and target holds the old version:

```text
source: new.tmp     = "version-2"
target: config.txt  = "version-1"
```

With code:

```java
Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
```

Outcomes vary by provider:

- Provider supports atomic replacement: the operation succeeds and target resolves to the new file.
- Provider rejects because target already exists and throws `IOException`.
- If atomic move is unsupported in this context, `AtomicMoveNotSupportedException` may be thrown.

Adding `REPLACE_EXISTING` **does not alter the `ATOMIC_MOVE` contract** because other options are ignored. Even after testing on OS A, do not assume OS B or ZIP/SMB/NFS will handle an existing target identically.

**One thing never to do to dodge the conflict:** delete `target` first, then atomically move source into place. Two operations—`delete` and `move`—do not fuse into one atomic transaction. In the gap between them, target does not exist, breaking uninterrupted updates.

If "atomically replace existing" is mandatory, state it explicitly in the application contract and test the target deployment's provider/file store/OS. When unsupported, fail clearly or use a snapshot/versioned-file architecture; never silently downgrade guarantees.

## 9. Atomicity Is Not Durability: A Successful Move Is Not Automatically Power-Loss Safe

Two frequently conflated concepts:

| Concept | Question | Does `ATOMIC_MOVE` Fully Solve It? |
| --- | --- | --- |
| **Atomicity/visibility** | Does a reader observe the move as a single operation or see intermediate states? | Aims for this if the atomic move succeeds |
| **Durability** | On power loss, are file contents and name durably persisted on storage? | **Not** guaranteed by `ATOMIC_MOVE` alone |
| **Consistency** | Does the file have valid format, checksum, and logical links with other data? | No; the application must verify |
| **Isolation** | Do multiple writers contend on versions or read/write concurrently? | Does not create a multi-operation transaction |
| **Crash recovery** | After a crash, how does the program know which data is valid and how to recover? | Requires dedicated design |

Before publishing critical data, you typically need to push staging contents down to the device:

```java
try (FileChannel channel = FileChannel.open(
        staging, StandardOpenOption.WRITE)) {
    channel.force(true);
}
Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE);
```

This is an illustrative snippet inside a method declaring `throws IOException`, with `staging`/`target` existing and requiring imports for `java.nio.channels.FileChannel`, `java.nio.file.StandardOpenOption`, `java.nio.file.Files`, and `java.nio.file.StandardCopyOption`. `force(true)` on `FileChannel` requests pushing content **and file metadata** updates to the device within the API's promise, but **does not itself guarantee** that metadata of the **directory containing the filename after rename** is durable.

To achieve strong crash consistency on some OSes, flushing/fsyncing the **directory** after rename is also commonly required. Java NIO provides no universal portable contract guaranteeing that opening and `force`-ing a directory works across every OS/provider; never write generic Java code and claim "100% crash-safe on every filesystem". Some systems use a transaction/journal at another layer or a versioned publish + checkpoint protocol.

Also distinguish: `Files.move` does not automatically make the new file's content valid. If staging was under-written, contains invalid JSON, or fails a checksum, a successful atomic move simply publishes **that broken content atomically**.

## 10. Creating Staging in the Target Directory and Remaining Limitations

Usually a good choice:

```java
Path dir = target.toAbsolutePath().getParent();
Path staging = Files.createTempFile(dir, ".publish-", ".tmp");
```

This is an illustrative snippet inside a `throws IOException` method; verify `target` has a parent directory, creation permissions, and a valid destination. Creating staging in the target's parent directory increases the probability that both paths share the same file store and can be atomically renamed.

Yet limitations remain:

- `Files.getFileStore(staging)` or `Files.getFileStore(dir)` reports the file store at check time, **not proof that atomic move is guaranteed**.
- If target is a symlink, replace-target behavior and symlink interaction policies can affect the outcome. `Files.move` moves **the symlink itself** if source is a symlink, not the target content.
- The parent path could be swapped with a link or have permissions altered by another process between operations; untrusted environments need proper path/directory security policies.
- If staging carries wrong permissions/ownership/attributes, an atomic rename does not automatically give it the right attributes. Prepare attributes before publishing when required.
- Atomically **renaming** does not mean every process holding an open file descriptor to the old file immediately sees new contents. Readers holding open handles may continue seeing the old file per OS semantics; reopen the path or use an application-level version protocol.

## 11. Do Not Use `ATOMIC_MOVE` as a "Silver Bullet"

Common misconceptions:

| Misconception | Why It Is Wrong | Fix |
| --- | --- | --- |
| `ATOMIC_MOVE` is always supported on Java 17+ | Support depends on provider, file store, OS, and operation | Catch `AtomicMoveNotSupportedException`; verify environment |
| With `ATOMIC_MOVE`, Java auto-falls back to copy/delete | API requires atomic move or throws an appropriate error | Choose an explicit fallback policy |
| `ATOMIC_MOVE, REPLACE_EXISTING` forces atomic overwrite | Other options are ignored; existing target behavior is implementation-specific | Design and test replacement per provider |
| Two paths on the same drive are guaranteed atomic | A file store/OS may still impose other constraints | Execute the operation and handle errors |
| `FileAlreadyExistsException` means atomic move is unsupported | May be a conflict with an existing target | Distinguish error types |
| Atomic rename guarantees data durability after power loss | Visibility and durability are different | Flush file contents and plan metadata/recovery strategy |
| Deleting target first then atomic-moving staging is still atomic replace | Two steps leave a window where target is missing | Keep target intact until the publish step if needed |
| `Files.copy` then `Files.delete` is atomic | Copy/delete is a multi-step sequence | Use atomic move where supported or acknowledge downgraded guarantees |
| Checking `Files.exists(target)` beforehand prevents races | Check-then-act suffers from TOCTOU | Use permissions, ownership, and proper concurrency control |
| Catching all `IOException`s and retrying non-atomically fixes errors | Permission/device/disk errors are unrelated to missing atomicity | Classify exceptions and preserve error context |
| Atomic move is a multi-file transaction | API applies to a single move operation | Use manifest/version/checkpoint or another transaction layer |

## 12. Concurrency: What If Two Writers Publish Together?

Suppose writers A and B both prepare separate staging files for `config.json`. Even if each rename is atomic, **there is no guarantee** which writer wins or that the newer data ends up last. `ATOMIC_MOVE` provides no version-based compare-and-swap, distributed lock, or transaction ordering.

Mitigations depend on business needs:

1. Allow only one process to publish at a time.
2. Use file locks or an appropriate locking system when supported by the environment, while understanding lock scope and process cooperation.
3. Assign monotonically increasing versions, enforce conditional updates at a coordination layer, or publish files under immutable versioned names.
4. When multiple files must be read consistently, switch a single manifest/current-version pointer last after all data files for that version are ready.
5. Design recovery for process death at any point, including controlled cleanup of leftover staging files.

An atomic move guarantees the property of **that move itself if the provider succeeds**; it does not replace versioning or concurrency protocols.

## 13. Testing Support Properly

A meaningful test should run in the **real target environment** with:

- Source file located on the exact intended file store.
- Target located at the exact real path and conditions.
- If replacement is needed, target **already exists**, to exercise the harder case.
- Permissions and ownership matching the real runtime process.
- Error scenarios (disk full, permissions, concurrent reader/writer, target being a directory/symlink) tested under control where relevant.

For instance, the demo in Section 6 demonstrates the **target does not exist** case on the demo machine's file store. It **does not prove** replace-existing support and does not measure crash durability.

If you need a runtime probe:

```java
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
    // Succeeded for this source/target at this moment.
} catch (AtomicMoveNotSupportedException ex) {
    // Atomicity is missing in the current context.
} catch (IOException ex) {
    // Other I/O error; preserve details for analysis.
}
```

This code is an illustrative snippet inside a method; it does not yet handle existing-target policy or source cleanup. A successful `Files.move` call cannot be generalized to mean other file stores, other directories, and existing targets will also succeed.

## 14. Real-World Scenarios and Appropriate Choices

### A. Writing Configuration Where Only Complete Versions Must Be Seen

Write to a staging file in the same directory, validate content, flush data if durability is needed, and try `ATOMIC_MOVE`. If replacing an existing target is mandatory but the provider does not support it, **fail and keep the old version** per policy. Never proactively `delete(target)` before publishing.

### B. Moving a File to Another Disk

When source is on volume A and destination is on volume B, an atomic move may be infeasible. If data transfer is required, you can copy into a **staging file at the destination**, verify checksum/length, then atomically rename from staging to the final name **within the destination file store**, and only after publication succeeds consider deleting the source. This is a multi-step workflow that **does not make the cross-volume move atomic**, though it avoids exposing a half-copied file at the destination name.

### C. Deploying Large Artifacts

A program produces `download.part`/a staging file. Once download + checksum succeed, it publishes via atomic rename if supported. Even if the rename is atomic, you must still design handling for incomplete files, timeouts, and flush failures.

### D. File Locks and Durability

If the system uses `FileLock`, do not assume a lock on the old inode/file protects the target name after a rename or that every provider enforces locks identically. `FileLock` and `ATOMIC_MOVE` solve different problems: locks control concurrent access within OS/provider scope, whereas atomic move controls the atomicity of a single move operation. Survival across crashes requires yet another policy.

## 15. Self-Check Questions

**1.** Can `Files.move(a,b,ATOMIC_MOVE)` return successfully if target `b` already exists?

**Answer:** It can, depending on the provider; Java does not guarantee this across all file systems.

**2.** Does adding `REPLACE_EXISTING` alongside `ATOMIC_MOVE` guarantee replacing an existing target?

**Answer:** No. When `ATOMIC_MOVE` is present, all other move options are ignored; target replacement remains implementation-specific.

**3.** If source/target reside on two different file stores, will Java automatically copy then delete atomically?

**Answer:** No. An atomic move may be infeasible; Java throws `AtomicMoveNotSupportedException` when an atomic file-system move cannot be performed.

**4.** When `AtomicMoveNotSupportedException` occurs, should you always fall back to a regular `Files.move`?

**Answer:** Only if business requirements **accept losing the atomicity guarantee** and have a recovery plan when fallback fails midway. If atomicity is mandatory, you must fail with an error.

**5.** Does a successful atomic move mean the data is definitely durable across power loss?

**Answer:** No. That guarantees the atomicity of the move operation; content and directory metadata durability must be handled separately and depend on the OS/provider.

**6.** Can you call `Files.delete(target)` followed by `Files.move(staging,target,ATOMIC_MOVE)` to construct an atomic replacement yourself?

**Answer:** No. Between the two operations there is a window where target has been deleted while staging is not yet published.

**7.** If two writers concurrently atomic-move to `config.json`, are they automatically ordered by latest version?

**Answer:** No. Atomic rename provides no version ordering, CAS, or isolation for multi-writer systems.

**8.** Why should staging be created in the target's parent directory?

**Answer:** It increases the likelihood that source and target share the same file store and provider, avoiding cross-volume copies. You still must handle exceptions when the provider lacks support or other errors occur.

## 16. Key Takeaways and Deployment Checklist

```text
ATOMIC_MOVE:
  - Requests an atomic move
  - If impossible -> AtomicMoveNotSupportedException
  - Other move options are ignored
  - Target exists -> replace or IOException depends on provider
  - Does not automatically mean durable / crash-safe / multi-file transaction
```

Before deploying to production:

1. Clarify the exact goal: atomic rename, atomic replacement, or crash durability.
2. Create staging in the target directory, write complete data, and validate payload.
3. If durability is required, consider `FileChannel.force(true)` and OS-appropriate metadata flushing mechanisms.
4. Publish only after preparation completes; never delete the old target before moving.
5. Use `Files.move(..., ATOMIC_MOVE)` and distinguish `AtomicMoveNotSupportedException` from other I/O errors.
6. If business logic demands atomicity, **fail explicitly** when unsupported.
7. If fallback is accepted, document the downgraded guarantee and handle post-error source/target states.
8. Test on the exact file store, provider, OS, permissions, and target-existing conditions of the deployment environment.
9. Coordinate writers and add versioning/manifest mechanisms if the system updates multiple files.
10. Record metadata and staging state to aid recovery, avoiding accidental deletion of valid data.

## References

- Oracle Java SE 17 — `Files.move(Path,Path,CopyOption...)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Oracle Java SE 21 — `StandardCopyOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardCopyOption.html
- Oracle Java SE 21 — `AtomicMoveNotSupportedException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/AtomicMoveNotSupportedException.html
- Oracle Java SE 21 — `FileChannel.force(boolean)`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html