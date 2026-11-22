# Common I/O Errors and Diagnostic Information Checklist in Java

## Purpose and How to Use

This document is a **quick-reference yet explanatory** table for Java Core I/O errors: reading/writing files with java.io and java.nio.file, handling byte/character streams, charsets, channels, sockets, ZIP compression, and Java object serialization. When an error appears, identify the operation just performed, find the closest exception name or message in the table, verify the minimal evidence, and choose a fix based on the confirmed root cause.

**Key principle:** the exception name indicates the problem category, not proof of the root cause. The same file-reading operation may throw IOException, a more specific subclass, or a RuntimeException depending on the API, operating system, file-system provider, permissions, and timing of the failure. Messages such as "Permission denied", "The process cannot access the file", and "Too many open files" are usually supplied by the environment; do not assume they always map to the same exception class across all systems.

### What information should be collected first?

For an incident, record in a controlled manner:

1. **Operation and API:** Files.readString, Files.newInputStream, Files.move, FileInputStream, BufferedReader, Socket.connect, ZipInputStream, ObjectInputStream.readObject…; read or write; synchronous or asynchronous execution.
2. **Full exception:** exact exception type, message, nested cause, any suppressed exceptions, and stack trace at the first application-relevant throw site.
3. **Target resource:** syntactically normalized absolute path, path type (file/directory/link), endpoint host:port, or data format. Mask sensitive details in logs; do not log tokens, passwords, or private file contents.
4. **Environment:** OS, JDK, working directory, container/mount, encoding/charset, disk status, quota, file descriptors/handles, and permissions of the **running account**.
5. **Timing and scope:** occurred during open, read, write, flush, or close; one-off or recurring; one file or all files; before/after deployment; whether concurrent processes modify/delete/rename the data.
6. **Outcome to clarify:** whether the error is recoverable by fixing path/permissions/schema, whether a retry is needed, whether retrying is safe or risks duplicate writes, and whether data has been partially written.

Do not force every error into a single catch(IOException) block just to print "I/O failed": that destroys context. Preserve the original exception and add the operation name and masked path/endpoint.

## 1. File System Error Reference Table: java.nio.file and java.io

This group frequently occurs when using Files, Path, InputStream, OutputStream, FileChannel, and directory operations. Most specific NIO error classes extend IOException (especially FileSystemException), though not every failure is a checked exception.

| Error/symptom | Meaning and common causes | Information to inspect | How to handle |
| --- | --- | --- | --- |
| NoSuchFileException | File or path component does not exist at operation time; may have been deleted/moved after a prior check | Effective path, working directory, name/case sensitivity, parent directory, mount, actions of other processes | Verify the right file and lifecycle; create the file if allowed by the contract; treat absence as a business state when appropriate |
| FileNotFoundException | Legacy java.io API could not open the file; may be missing file, permission denied, or path pointing to a directory | API called, getMessage(), existence and file type, open permissions, relative/absolute path | Check the OS-level cause; do not conclude with certainty that the file is absent from the exception name alone |
| AccessDeniedException | Access permission to file/directory denied; usually from NIO provider | Service account, ACL/permissions on file and parent directory, read-only mount, security policy status | Grant required permissions or change storage location; do not run the application as administrator just to hide the error |
| SecurityException | Runtime or environment security policy rejects the action; an unchecked exception | Stack trace, security policy/runtime, sandbox, whether the app is allowed to call the API | Adjust allowed configuration/scope per policy; distinguish from AccessDeniedException |
| FileAlreadyExistsException | Attempted to create an object that already exists, commonly with CREATE_NEW or Files.createFile/createDirectory | Path and existing entry type, whether another process claimed the name, whether uniqueness is required | Generate unique names or handle conflict explicitly; CREATE_NEW provides atomic check-and-create on supporting providers |
| DirectoryNotEmptyException | Deleting/moving a directory when its contents prevent the operation from completing | Entries inside (including hidden files), which program is using them, recursive-delete policy | Delete recursively only when it is a confirmed business requirement; avoid accidental data loss |
| NotDirectoryException | A component expected to be a directory is actually not a directory | Each path segment, parent path attributes, symbolic links | Fix the path or directory structure; do not proceed by concatenating paths blindly |
| FileSystemLoopException | Following symbolic links caused a cycle, e.g., via Files.walkFileTree | Symbolic link structure, FOLLOW_LINKS mode, path forming the cycle | Avoid following links if unnecessary; detect and skip cycles or report a clear error |
| FileSystemException | File-system error without a more specific subclass, e.g., cannot rename/move, file locked, device error | getFile(), getOtherFile(), getReason(), OS/provider and permissions, disk/lock status | Use reason/cause to diagnose; do not treat FileSystemException as a single specific cause |
| IOException: "No space left on device" / "Disk full" | Storage volume has no remaining space or exceeded quota; exact exception class may vary | Free space, inodes/quota (if applicable), actual file location, temp directory, logs/backups | Free space/raise quota, reserve headroom, check partial writes and corresponding transactions |
| IOException: "Too many open files" | Exhausted file descriptors/handles or OS limit; often caused by unclosed streams/channels/sockets | Open file count of the process, system limits, growth trend, unclosed code paths | Use try-with-resources, fix leaks, consider bounding concurrent I/O; raise OS limits only with justification |
| IOException: "Read-only file system" | Environment disallows writes on the current mount or file system | Mount flags, container volume, output path, deployment environment | Switch to a configured writable volume or adjust mount configuration validly |
| IOException: "Broken pipe" / "Connection reset" | Data transport connection was closed/reset while writing/reading; message comes from network/pipe | Did the peer close? timeout? proxy/load balancer? how many bytes were sent? | Do not blindly retry non-idempotent writes; investigate connection lifecycle and acknowledgment |
| InvalidPathException | Path string invalid for current system/provider, e.g., forbidden characters; unchecked exception | Input data, OS, path syntax, Path.of(...) | Validate input structure, normalize format per OS; do not arbitrarily replace characters and corrupt identifiers |
| ClosedFileSystemException | Accessing a closed FileSystem, e.g., a ZIP filesystem mounted via FileSystems; unchecked | Close timing, code holding Path, FileSystem provider lifecycle | Ensure required operations finish before closing and do not reuse Path after the provider is closed |

**Note on checked/unchecked:** NoSuchFileException, AccessDeniedException, FileAlreadyExistsException, and FileSystemException extend IOException; InvalidPathException, ClosedFileSystemException, and SecurityException extend RuntimeException. Therefore, catch(IOException) will not catch every failure listed above.

**Note on existence and permissions:** Files.exists(path) returns false even when existence cannot be determined in some cases; Files.notExists(path) can also return false when the state is unknown. Do not turn false into proof that a file does not exist. The real operation can still fail due to concurrent changes, even if a check succeeded immediately prior.

## 2. Error Reference Table When Reading/Writing Streams, Buffers, and Channels

| Error/symptom | When it commonly appears | Information to inspect | How to handle |
| --- | --- | --- | --- |
| EOFException | API requires reading a complete structure but runs out of data before finishing, e.g., DataInputStream.readInt | Actual data length, read/write format and order, header/version/checksum presence, whether producer finished writing | Check framing and truncated data; distinguish normal EOF in a byte-read loop from unexpected EOF when reading a record |
| IOException: "Stream closed" | Reading/writing after the stream was closed; sometimes another wrapper closed the underlying stream | Which try-with-resources owns the resource, who closed first, execution flow | Establish ownership, do not share a closed stream; avoid closing resources in a non-owning layer |
| ClosedChannelException | Channel operation attempted after the channel was closed | Close order, multithreaded handling, shutdown/cancel, channel lifecycle | Coordinate lifecycle, do not reuse a closed channel |
| AsynchronousCloseException | Another thread closed a channel currently blocked in an I/O operation | Which thread closed it, whether stop/cancel/shutdown occurred, task stack trace | Treat as operation cancellation on intentional shutdown; fix premature close races if unexpected |
| ClosedByInterruptException | Thread was interrupted while blocked on an interruptible channel; the channel is also closed | Thread interruption, executor shutdownNow, cancellation, channel state | Distinguish task cancellation from network/disk errors; respect interrupt policy and avoid blind retries |
| NonReadableChannelException / NonWritableChannelException | Using a channel in a mode that disallows reading or writing; unchecked | Channel open mode, OpenOption.READ/WRITE/APPEND, buffer and logic branches | Open the channel in the right mode and perform only supported operations |
| OverlappingFileLockException | A lock on the same file region overlaps a lock already held in the same JVM, or is waiting on an overlapping lock; unchecked | Locks already held by the JVM, start/size region, FileLock lifecycle management | Coordinate locking within the process, avoid duplicate locks; always release locks properly |
| FileLockInterruptionException | Thread was interrupted while waiting for a FileChannel lock | Interrupt policy, lock history, worker/task state | Investigate lock contention or cancellation request; handle cancellation properly |
| InterruptedIOException | An I/O operation was interrupted and may have transferred partial data; has bytesTransferred field | bytesTransferred, stream type, current operation, thread state | Do not assume nothing was transferred; decide resume/retry per protocol |
| IOException on flush/close | Buffered data not fully flushed or error closing resource, possibly occurring after successful write calls | Did flush/close actually run, root and suppressed exceptions, is FS/connection still alive? | Do not declare a transaction successful merely because write returned; inspect close errors and sync/commit when required |
| BufferOverflowException / BufferUnderflowException | Application writes/reads past remaining capacity/data of ByteBuffer; unchecked | position/limit/capacity, flip/clear/compact, record size | Check remaining() and byte protocol; fix buffer lifecycle rather than resizing buffers arbitrarily |
| ReadOnlyBufferException | Writing to a read-only ByteBuffer; unchecked | Buffer created by asReadOnlyBuffer, READ_ONLY map, or sharing mechanism | Use a writable buffer when writing is needed or separate memory regions appropriately |

### Three common points of confusion

- InputStream.read() returns **-1** on normal EOF. That is a valid result; EOFException is not thrown there. Conversely, DataInputStream.readFully/readInt can throw EOFException if fewer bytes remain than the requested structure requires.
- For InputStream.read(byte[]), the returned byte count may be smaller than the buffer length even **before** reaching EOF. Loop until enough data is read for the framing/record, or use readNBytes/readFully as appropriate.
- OutputStream.close() may flush buffered bytes, but you should not assume it guarantees data is durably persisted to disk. If the application needs durability, define explicit sync/transaction mechanisms, such as FileChannel.force(...) and the environment's guarantee boundaries.

## 3. Charset, Text, and Binary Data Error Reference Table

| Error/symptom | Common causes | What to inspect? | How to handle |
| --- | --- | --- | --- |
| MalformedInputException | Byte sequence invalid for the chosen charset, such as UTF-8 with bad continuation bytes | Byte source, BOM, write/read charset, error offset, whether the file was truncated | Choose the right charset per data contract; replace invalid characters only if business rules tolerate data loss |
| UnmappableCharacterException | Unicode character cannot be represented in target charset or transcoding sequence cannot be mapped | Encoder/decoder, target charset, original data, coding-error action | Use UTF-8/Unicode appropriately, or handle transcoding errors transparently |
| CharacterCodingException | Checked exception hierarchy for character encoding/decoding errors | IOException cause, decoder/encoder, sample bytes with sensitive data masked | Preserve original bytes for diagnosis; determine charset before decoding |
| UTFDataFormatException | Invalid DataInput/DataOutput modified UTF-8 format (e.g., readUTF/writeUTF) or format limit violated | Was a matching writeUTF/readUTF pair used, format/written byte count, was data truncated? | Do not use readUTF to read arbitrary UTF-8 text; follow the DataInput/DataOutput protocol strictly |
| Characters turn into "�" (replacement character) without throwing | Decoder uses error-replacement behavior or data was previously mis-encoded | Each encode/decode step, CharsetDecoder.onMalformedInput, stored source data | Choose the REPORT policy for early detection when data fidelity must be preserved |
| "Mojibake" characters (e.g., "Ã©") | Bytes written with one charset but decoded with another | Source/target charset, BOM, default charset, and transport metadata | Specify charset explicitly on both sides; do not re-encode a mis-decoded string as a workaround |
| File appears empty or missing trailing lines | Buffer not flushed, Reader/Writer not closed, reading logic drops the last element | flush/close, while loop, line separators, size on disk vs. in RAM | Close streams properly, verify code reads until EOF and handles the final chunk |

**Distinction:** Standard UTF-8 is used with Files.readString(path, StandardCharsets.UTF_8), InputStreamReader(..., UTF_8), and OutputStreamWriter(..., UTF_8). DataInputStream.readUTF and DataOutputStream.writeUTF use **length-prefixed modified UTF-8**, which is not equivalent to ordinary UTF-8 text reading/writing.

## 4. Network Error Reference Table: Sockets, Timeouts, and TLS

This group belongs to java.net and javax.net.ssl; several errors are subclasses of IOException. When diagnosing, identify whether the failure happened during **DNS, TCP connect, TLS handshake, read, write, or close**.

| Error | Common signs/meaning | What to verify in practice | Approach |
| --- | --- | --- | --- |
| UnknownHostException | Cannot resolve hostname or hostname has no matching address | Hostname, DNS from runtime environment, search domain, container/proxy config, DNS stability | Fix DNS/host; perform bounded retries only when the failure is genuinely transient |
| ConnectException | TCP connection refused or failed at connect step, e.g., "Connection refused" | Host:port, listening service, firewall, routing, IPv4/IPv6, proxy | Verify endpoint and service status; do not confuse with read timeout |
| SocketTimeoutException | Timeout exceeded during socket connect or read (depending on configured operation) | Connect timeout or SO_TIMEOUT? Network connected yet? Server responding slowly? | Set intentional timeouts, measure latency, retry per idempotency/backoff |
| SocketException | General socket error, such as reset, broken pipe, socket closed | Did peer close, local close, idle timeout, HTTP proxy, keepalive | Determine lifecycle and partially transferred data; do not treat every reset as safely retryable |
| BindException | Cannot bind address/port, usually port already in use or invalid address | Socket local address/port, process holding it, bind config, OS permissions | Choose a valid port/address, stop conflicting process if permitted |
| SSLHandshakeException | TLS handshake failed to complete (certificate, protocol, cipher, hostname, trust) | Cause chain, certificate chain/truststore, hostname, expiry, TLS version, system clock | Fix trust/identity/protocol; do not disable certificate validation to bypass errors |
| SSLException | General TLS error during handshake or data transfer | Stack/cause, handshake vs. application data stage, connection close | Find root cause, check protocol and configuration on both ends |

Key points to remember:

- Connect timeout and read timeout are two separate phases. A successful connect does not prove the server will return data on time.
- Retrying a status read usually differs from retrying a write/payment command: if a request reached the server and the response was lost, the client may not know whether the operation completed. Use request-ids, idempotency keys, or application-level confirmation workflows.
- Never log sensitive payloads, credentials, private keys, access tokens, or certificate internals when collecting traces. Log only the technical metadata needed for diagnosis.

## 5. ZIP and Object Serialization Error Reference Table

| Error/symptom | Location and meaning | Information to inspect | How to handle |
| --- | --- | --- | --- |
| ZipException | java.util.zip encountered invalid or unprocessable ZIP/GZIP/DEFLATE data | Actual format, header/magic, whether full file downloaded, CRC/entry, compression method | Verify source and integrity, ensure decompression matches format; bound decompressed size against zip bombs |
| EOFException during decompression | Compressed stream truncated or incomplete structure | Bytes downloaded/received vs. expected, checksum, source close | Re-transfer/re-download in a controlled way, verify completeness before processing |
| StreamCorruptedException | ObjectInputStream saw invalid header, token, or Java serialized stream structure | Did writer use ObjectOutputStream, read/write order, injected/truncated bytes, protocol mismatch | Align format and order, avoid mixing text/raw data into an object stream |
| InvalidClassException | Class incompatible with stream (serialVersionUID, type/class descriptor), or rejected by ObjectInputFilter | Full message/cause, serialVersionUID, class changes, filter policy, binary class name | Fix compatibility/schema or proper allowlist; do not disable the filter just to get past errors |
| NotSerializableException | Writing a non-Serializable class in the object graph | Type named in message, fields holding resources/other non-serializable objects | Use serializable DTOs, mark non-serializable state transient when semantically appropriate |
| OptionalDataException | ObjectInputStream reading a type mismatch against primitive/object data in the stream, or reaching end of custom data | Order of writeObject/writeInt/readObject/readInt, custom readObject/writeObject | Match format and ordering, manage versions explicitly |
| InvalidObjectException | Object data failed validation/readResolve or restoration logic | Cause, class invariants, source data, validation checks in custom deserialization | Validate and reject invalid data, fix source or use a verified migration |
| ClassNotFoundException | Reader cannot locate a class described in the stream; checked exception, does not extend IOException | Classpath/module path, package/class name, deployment version, custom class loader | Ensure matching class is present or switch to a schema-explicit data exchange format |

**Serialization security limits:** ObjectInputFilter can restrict classes, depth, reference count, bytes, and array sizes during deserialization. Configure the filter **before calling readObject()**, prefer an allowlist for trusted sources, and still bound external input size. A filter does not authenticate the sender, replace encryption/signatures, or stop every risk inside custom readObject. For untrusted input, prefer exchange formats with explicit schemas and validation.

## 6. Standalone Java 17+ Example: Producing and Distinguishing Three I/O Errors

This example creates a temporary directory, demonstrates three specific exceptions in sequence, and cleans up the temporary files. Each error is caught with the appropriate exception type so learners can see how to read the cause. No sensitive paths or external resources are used.

Create the file **IoErrorLookupDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class IoErrorLookupDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("io-error-lookup-");
        Path missing = dir.resolve("missing.txt");
        Path existing = dir.resolve("existing.txt");
        Path invalidUtf8 = dir.resolve("invalid-utf8.txt");

        try {
            // 1. Cannot read a file that does not exist yet.
            try {
                Files.readString(missing, StandardCharsets.UTF_8);
            } catch (NoSuchFileException ex) {
                System.out.println("NoSuchFileException: missing.txt");
            }

            // 2. CREATE_NEW creates the file only when the path does not yet exist.
            Files.writeString(existing, "Hello", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW);
            try {
                Files.writeString(existing, "Again", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("FileAlreadyExistsException: existing.txt");
            }

            // 3. The two bytes below do not form a valid UTF-8 sequence.
            Files.write(invalidUtf8, new byte[] {(byte) 0xC3, (byte) 0x28});
            try {
                Files.readString(invalidUtf8, StandardCharsets.UTF_8);
            } catch (MalformedInputException ex) {
                System.out.println("MalformedInputException: invalid UTF-8");
            }
        } finally {
            Files.deleteIfExists(invalidUtf8);
            Files.deleteIfExists(existing);
            Files.deleteIfExists(missing);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac IoErrorLookupDemo.java
java IoErrorLookupDemo
~~~

Expected output in an environment that can create/read/write/delete a temporary directory:

~~~text
NoSuchFileException: missing.txt
FileAlreadyExistsException: existing.txt
MalformedInputException: invalid UTF-8
~~~

**Why does this example work?**

1. Files.readString(missing, UTF_8) encounters a non-existent file, so on common default file-system providers it throws NoSuchFileException. There is no prior exists check because the read operation itself determines the real state.
2. Files.writeString(existing, ..., CREATE_NEW) creates the file the first time. The second time, the CREATE_NEW option itself forbids overwriting an existing path, so it throws FileAlreadyExistsException. This is typically the right choice to prevent accidental overwrites.
3. Byte 0xC3 is the leading byte of a two-byte UTF-8 sequence, but the next byte 0x28 is not a valid continuation byte. Files.readString(..., UTF_8) reports MalformedInputException, indicating an error in **decoding bytes into characters**, not a missing file or denied permission.
4. finally cleans up the paths created in the demo. If cleanup itself fails, an IOException may be thrown from finally; in larger applications, preserve the original exception and attach cleanup errors as suppressed or log them separately rather than accidentally masking the primary cause.

**Limitation of the example:** If the temporary directory is not writable, runs out of space, or another process interferes, the program may fail with another exception before printing all three lines. That reflects real I/O behavior to diagnose, not a reason to catch all exceptions and print fake results.

## 7. Error Diagnosis and Contextual Logging Patterns

You do not need to log entire customer payloads to debug I/O. Log enough details to identify **which operation**, **which target**, and **what reason the OS/provider reported**.

Illustrative example of a method in an application that already has a logger and path:

~~~java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.FileSystemException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

static String loadConfig(Path path) throws IOException {
    try {
        return Files.readString(path, StandardCharsets.UTF_8);
    } catch (NoSuchFileException ex) {
        // Requested file does not exist; policy might be to return 404.
        throw new IOException("Config is missing: " + path.getFileName(), ex);
    } catch (AccessDeniedException ex) {
        // Check service account, ACLs, and permissions on parent directory.
        throw new IOException("Cannot read config: access denied", ex);
    } catch (FileSystemException ex) {
        // getReason() may be null; content may depend on OS/provider.
        throw new IOException("Cannot read config: " + ex.getReason(), ex);
    }
}
~~~

This is an **illustrative method snippet**, not a standalone program because it has no enclosing class or main method. In a real environment:

- Write stack traces/causes to an internal log channel with appropriate access control; return only safe messages to users. Do not automatically expose absolute paths containing account names, secrets, or infrastructure layout in public APIs.
- Preserve the original cause when wrapping errors. Do not turn a permission error into "file not found" in operational logs; the HTTP layer can return a different status message while preserving original evidence.
- For FileSystemException, use getFile(), getOtherFile(), and getReason() when helpful; some values may be null and the exception message may contain details that should not be exposed publicly.
- Do not catch SecurityException with IOException. If runtime policy failures must be handled, catch them under a separate contract and do not obscure policy violations.
- When using try-with-resources, errors from closing a resource may appear in getSuppressed() on the primary exception. Inspect suppressed exceptions as well when an operation involves multiple resources.

### I/O incident record template

~~~text
Operation      : READ_TEXT / WRITE_BYTES / MOVE / SOCKET_CONNECT / DESERIALIZE
API            : Files.readString(Path, UTF_8)
Resource       : <masked path alias or endpoint>
Environment    : JDK version, OS, container/mount, service account
Exception      : <fully-qualified exception class>
Message/Reason : <concise message, sensitive info removed>
Cause          : <cause chain, internal stack trace>
Suppressed     : <cleanup/close errors if any>
Input format   : UTF-8 / binary protocol / serialized object / ZIP / ...
Timing         : Timestamp, phase open/read/write/flush/close
Observed state : Exists? Directory? Permissions? Free space? Host:port reachable?
Concurrency    : Concurrent writer/deleter/closer? Previous retry?
Next action    : Fix path / permissions / schema / storage / connectivity / code
~~~

exists/isDirectory/isReadable values are only point-in-time snapshots and can change immediately afterward. Do not rely on them as guarantees that open/read/write will succeed; still handle errors from the actual operation.

## 8. Low-Risk Investigation Sequence

1. **Pinpoint the failure site:** read the first 1–3 stack frames belonging to your code along with the exception class, cause, and suppressed exceptions. Do not start by changing charsets or adding permissions before knowing which phase failed.
2. **Match the API type:** FileInputStream may report a broad FileNotFoundException; Files can provide more specific NoSuchFileException or AccessDeniedException. For networking, distinguish connect/read/write/TLS before tuning timeouts.
3. **Inspect non-destructive facts:** JDK/OS version, effective path, working directory, isRegularFile/isDirectory, permission/mount info if permitted; do not run delete commands, recursive chmod, or kill processes to guess.
4. **Check resources:** is disk space/quota available, are streams/channels/sockets leaking, are file handles/locks held, are thread pools and concurrent I/O counts abnormal?
5. **Verify the data contract:** do writer and reader agree on charset, record framing, field order, version/schema, and checksum/length; for ZIP and serialized streams, is the format valid?
6. **Reproduce safely:** use temporary files and non-sensitive data; test success + missing input + denied permission + truncated data + concurrently modified file when those scenarios are genuinely relevant.
7. **Fix root cause, add negative tests:** fix path/permissions/resource lifecycle/charset/framing; verify the specific exception is handled properly. For writes, check state before retrying to avoid duplicates or corruption.
8. **Improve observability:** if the issue is not yet reproducible, log the operation, expected/read byte counts (never log sensitive content), connect/read/write duration, path alias, exception cause, and correlation id.

### Quick decision questions

| Question | If the answer is "Yes" | Check next |
| --- | --- | --- |
| Error occurs immediately on file open? | Likely related to path, type, permission, or resource | Path resolution, working directory, service account permissions |
| Opens fine but fails after several reads? | Truncated data, wrong framing, connection drop, or source modified | Length/record boundary, EOF, bytes read, writer/peer |
| Fails only with Vietnamese/special characters? | Charset or inconsistent transcoding | UTF-8, BOM, decoder policy, original bytes |
| Fails only under high load/concurrency? | Leak, lock, contention, or race condition | try-with-resources, file handles, channel close, pool size |
| Fails only when deployed/containerized? | Working directory, mount, account, DNS, or permission changed | Environment diff, volume, path, service user, network route |
| Fails only with data saved by an older version? | Format/schema/serialVersionUID changed | Version, migration, classpath, backward compatibility |
| Fails only after socket idle time? | Idle timeout, peer/proxy close, or connection reset | Configured timeouts, keepalive, lifecycle, request replay safety |

## 9. Preventing Errors During Program Design

### Managing resource lifecycle

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static void printNonEmptyLines(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(
            path, StandardCharsets.UTF_8)) {
        String line;
        while ((line = reader.readLine()) != null) {
            if (!line.isBlank()) {
                System.out.println(line);
            }
        }
    }
}
~~~

This is an illustrative method. try-with-resources closes BufferedReader even if reading fails and prevents leaks. Do not open streams outside try and forget to close them on a return or catch branch.

### Choosing open/write strategies per contract

- **Read-only:** Files.newInputStream(path, READ) or Files.newBufferedReader(path, UTF_8); handle missing files, permissions, and data errors per requirements.
- **Create new file, never overwrite:** Files.write(..., CREATE_NEW) or Files.createFile(path), catch FileAlreadyExistsException to handle conflicts.
- **Controlled replacement write:** Write full data to a temporary file on the same file system, check flush/close, then move to replace if allowed by the contract. ATOMIC_MOVE is not supported by all providers; handle AtomicMoveNotSupportedException and decide fallback behavior according to atomicity requirements rather than silently pretending it is atomic.
- **Reading large data:** Use streams/channels and bounded buffers; avoid Files.readAllBytes for unbounded files to prevent memory pressure.
- **Reading text:** Specify UTF-8 or the documented charset explicitly; do not rely on the default charset when exchanging data with other systems.
- **Network I/O:** Configure per-phase timeouts, bound payload sizes, and use conditional/idempotent retries; record partial results when required by the protocol.
- **Serialization:** Set an appropriate ObjectInputFilter before calling ObjectInputStream.readObject; validate data after deserialization; bound input bytes upfront.

### When should you retry?

| Scenario type | Retry automatically? | Reason |
| --- | --- | --- |
| Missing file due to typo in path | Usually no | Retrying will not fix the path |
| AccessDeniedException due to static ACL | Usually no | Permissions or policy must be fixed |
| FileAlreadyExistsException with CREATE_NEW | No with the same name and request | Retrying will keep colliding |
| SocketTimeoutException on an idempotent query | Possible, bounded with backoff | Network glitches can be transient, though limits are still required |
| Side-effecting write sent, response timed out | Only with protocol guarantees/idempotency key | Risk of executing twice |
| Out of disk space or out of file handles | Do not retry tightly or indefinitely | Resources must be recovered and partial writes handled |
| MalformedInputException from a file with wrong fixed charset | No | Format/charset must be fixed; retrying does not alter bytes |
| Unexpected EOF on partially downloaded data | Can re-download if source/contract allows | Must verify checksum/length and avoid stitching mismatched sessions |

## 10. Knowledge Check

1. Why is FileNotFoundException insufficient to conclude a file does not exist?
2. Files.exists(path) just returned true, yet immediately afterward Files.readString(path) throws NoSuchFileException. How can this happen?
3. When DataInputStream.readInt throws EOFException, why does handling it differ from a while(InputStream.read() != -1) loop?
4. How do you distinguish a charset error from a truncated byte stream error?
5. When a Files.move operation fails, which details of FileSystemException help find the cause?
6. Why is using CREATE_NEW generally safer than a "check exists then create" sequence with multiple writers?
7. How does SocketTimeoutException during connect differ from during read? Why must you not retry every send unconditionally?
8. How does an IOException from close affect the claim that "writing succeeded"?
9. Which exceptions in the tables are unchecked, and why does catch(IOException) not cover them?
10. What two very different situations can InvalidClassException indicate in Java serialization?

**Passing criteria:** You can pinpoint the failing operation, exception, and verifiable cause; pick concrete APIs/checks to separate hypotheses; handle resources and errors properly while avoiding unsafe retries; and avoid leaking sensitive information in logs.

## Java SE 17 Reference Links

- java.io.IOException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html
- java.io.EOFException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/EOFException.html
- java.io.FileNotFoundException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html
- java.nio.file.Files: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- java.nio.file.FileSystemException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemException.html
- java.nio.charset.MalformedInputException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/MalformedInputException.html
- java.nio.channels.ClosedChannelException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedChannelException.html
- java.net.SocketTimeoutException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html
- java.io.ObjectInputFilter: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html
- Java tutorials — Basic I/O: https://docs.oracle.com/javase/tutorial/essential/io/
