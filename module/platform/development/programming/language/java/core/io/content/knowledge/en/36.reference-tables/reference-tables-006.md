# Common I/O Errors and Diagnostic Information Table in Java

## Purpose and How to Use

This document is a **quick-lookup table with explanations** for Java Core I/O errors: reading/writing files with java.io and java.nio.file, handling byte/character streams, charsets, channels, sockets, ZIP compression, and Java object serialization. When you encounter an error, identify the operation just performed, locate the closest exception name or message in the table, verify the minimum evidence, and choose the fix matching the confirmed root cause.

**Key principle:** the exception name indicates the problem category, not proof of the root cause. The same file-reading operation may raise IOException, a more specific subclass, or a RuntimeException depending on the API, operating system, file-system provider, permissions, and the stage at which the error occurs. Messages such as "Permission denied", "The process cannot access the file", and "Too many open files" are typically supplied by the environment; never assume they always map to the same exception class on every system.

### What Information Should Be Collected First?

For an incident, record in a controlled manner:

1. **Operation and API:** Files.readString, Files.newInputStream, Files.move, FileInputStream, BufferedReader, Socket.connect, ZipInputStream, ObjectInputStream.readObject…; read or write; synchronous or asynchronous execution.
2. **Full exception:** exact exception type, message, nested cause, suppressed exceptions if any, and stack trace at the first throw point relevant to the application.
3. **Target object:** syntactically normalized absolute path, path kind (file/directory/link), host:port endpoint, or data format. Mask sensitive information in logs; do not log tokens, passwords, or private file contents.
4. **Environment:** OS, JDK, working directory, container/mount, encoding/charset, disk status, quota, file descriptors/handles, and permissions of the **running account**.
5. **Timing and scope:** occurred during open, read, write, flush, or close; once or repeatedly; one file or all files; before/after deploy; whether concurrent processes modify/delete/rename data.
6. **Outcome to clarify:** whether the error is recoverable by fixing path/permissions/schema, whether retry is needed, whether retry is safe or risks duplicate writes, and whether data was partially written.

Do not funnel all errors into a single catch(IOException) block just to print "I/O failed": that discards context. Preserve the original exception and add the operation name and masked path/endpoint.

## 1. File System Error Lookup Table: java.nio.file and java.io

This group is commonly encountered when using Files, Path, InputStream, OutputStream, FileChannel, and directory operations. Specific NIO error classes mostly extend IOException (especially FileSystemException), though not every error is a checked exception.

| Error/symptom | Meaning and common causes | Information to check | Resolution |
| --- | --- | --- | --- |
| NoSuchFileException | File or a path component does not exist at operation time; may have been deleted/moved after a prior check | Effective path, working directory, case sensitivity, parent path, mount, actions by other processes | Confirm exact file and lifecycle; create file if contract allows; handle absence as a business state when appropriate |
| FileNotFoundException | Legacy java.io API failed to open the file; could be missing file, permission denied, or path pointing to a directory | API called, getMessage(), file existence and type, open permissions, relative/absolute path | Inspect the OS-level cause; do not infer with certainty that the file does not exist from the exception name alone |
| AccessDeniedException | Access to file/directory was denied; usually from an NIO provider | Execution account, ACL/permissions on file and parent directory, read-only mount, security policy state | Grant required permissions or change storage location; do not run the application as administrator just to hide the error |
| SecurityException | Runtime or environment security policy denied the action; this is an unchecked exception | Stack trace, security policy/runtime, sandbox, whether the application has permission to call the API | Adjust allowed configuration/scope per policy; distinguish from AccessDeniedException |
| FileAlreadyExistsException | Attempted to create an object that already exists, commonly with CREATE_NEW or Files.createFile/createDirectory | Current path and entry type, whether another process claimed the name, whether uniqueness is required | Use unique names or handle conflicts explicitly; CREATE_NEW provides atomic check/create on supporting providers |
| DirectoryNotEmptyException | Directory delete/move failed because contents inside prevent completion | Entries inside (including hidden files), which program is using them, recursive-delete policy | Delete recursively only when that is a confirmed business requirement; avoid accidental data loss |
| NotDirectoryException | A component expected to be a directory is actually not a directory | Each path segment, parent path attributes, symbolic links | Fix the path or directory structure; do not proceed by arbitrarily appending path segments |
| FileSystemLoopException | Traversing links caused a cycle while following symbolic links, e.g. via Files.walkFileTree | Symbolic link structure, FOLLOW_LINKS mode, path forming the cycle | Do not follow links if unnecessary; detect and skip cycles or report a clear error |
| FileSystemException | File-system error without a more specific subclass, e.g. cannot rename/move, file locked/in use, device error | getFile(), getOtherFile(), getReason(), OS/provider and permissions, disk/lock status | Use reason/cause to diagnose; do not treat FileSystemException as one single specific cause |
| IOException: "No space left on device" / "Disk full" | Storage volume is out of space or over quota; exact exception class may vary | Disk space, inodes/quota (if applicable), actual file location, temp directory, logs/backups | Free space/increase quota, reserve capacity, check for partial writes and corresponding transactions |
| IOException: "Too many open files" | Exhausted file descriptors/handles or OS limits; often caused by unclosed streams/channels/sockets | Open file count of process, system limits, growth trend, code paths missing close | Use try-with-resources, fix leaks, consider bounding concurrent I/O; increase OS limits only with justification |
| IOException: "Read-only file system" | Environment disallows writes on the current mount or file system | Mount flags, container volumes, output location, deployment environment | Switch to a configured writable volume or adjust mount properly |
| IOException: "Broken pipe" / "Connection reset" | Data transmission connection was closed/reset while writing/reading; message comes from network/pipe | Did peer close? timeout? proxy/load balancer? bytes already transferred? | Do not automatically retry non-idempotent writes; investigate connection lifecycle and acknowledgment mechanism |
| InvalidPathException | Path string is invalid for the current system/provider, e.g. forbidden characters; this is an unchecked exception | Input data, OS, path syntax, Path.of(...) | Validate input structure, convert format properly per OS; do not arbitrarily strip characters and alter identifiers |
| ClosedFileSystemException | Accessing a closed FileSystem, e.g. a ZIP filesystem mounted via FileSystems; unchecked | Close timing, code retaining Path, FileSystem provider lifecycle | Ensure required operations complete before closing and do not reuse Paths after the provider has closed |

**Notes on checked/unchecked:** NoSuchFileException, AccessDeniedException, FileAlreadyExistsException, and FileSystemException extend IOException; InvalidPathException, ClosedFileSystemException, and SecurityException extend RuntimeException. Therefore catch(IOException) does not catch every failure listed.

**Notes on existence and permissions:** Files.exists(path) returns false even when existence cannot be determined in some cases; Files.notExists(path) can also return false when status is unknown. Do not turn false into definitive proof that a file does not exist. The actual operation can still fail due to concurrent changes, even if a check succeeded immediately before.

## 2. Error Lookup Table for Streams, Buffers, and Channels

| Error/symptom | When it typically occurs | Information to check | Resolution |
| --- | --- | --- | --- |
| EOFException | API requires reading a complete structure but data ends before completion, e.g. DataInputStream.readInt | Actual data length, read-write format/order, whether header/version/checksum exists, whether source finished writing | Check framing and truncated data; distinguish valid EOF in a byte-read loop from unexpected EOF when reading a record |
| IOException: "Stream closed" | Reading/writing after stream was closed; sometimes another wrapper closed the underlying stream | Which try-with-resources owns the resource, who closed first, usage flow | Identify ownership, do not share closed streams; avoid closing resources in a layer that does not own them |
| ClosedChannelException | Operating on a channel after it has been closed | Close order, multithreaded handling, shutdown/cancel, channel lifecycle | Coordinate lifecycle, do not reuse a closed channel |
| AsynchronousCloseException | Another thread closed a channel currently blocked in an I/O operation | Which thread closed it, whether stop/cancel/shutdown occurred, task stack trace | Treat as operation cancellation on intentional shutdown; fix premature close races if unexpected |
| ClosedByInterruptException | Thread was interrupted while blocked on an interruptible channel; the channel is also closed | Thread interruption, executor shutdownNow, cancellation, channel state | Distinguish task cancellation from network/disk failure; honor interrupt policy and do not retry blindly |
| NonReadableChannelException / NonWritableChannelException | Using channel in a mode that disallows reading or writing; unchecked | Channel open mode, OpenOption.READ/WRITE/APPEND, buffer and logic branches | Open channel in the right mode and perform only supported operations |
| OverlappingFileLockException | A lock on the same file region overlaps a lock already held in the same JVM, or an overlapping lock is pending; unchecked | Locks already held by the JVM, start/size region, FileLock lifecycle management | Coordinate locks within the same process, avoid duplicate locks; always release locks properly |
| FileLockInterruptionException | Thread was interrupted while waiting for a FileChannel lock | Interrupt policy, lock history, worker/task state | Investigate lock contention or cancellation request; handle cancellation properly |
| InterruptedIOException | An I/O operation was interrupted and may have transferred partial data; has a bytesTransferred field | bytesTransferred, stream type, current operation, thread state | Do not assume the entire operation did nothing; decide resume/retry per protocol |
| IOException during flush/close | Buffered data was not fully flushed or resource close failed, potentially occurring after write calls returned | Whether flush/close actually ran, primary and suppressed exceptions, whether FS/link is still alive | Do not declare a transaction successful just because write returned; check close errors and sync/commit when needed |
| BufferOverflowException / BufferUnderflowException | Application writes/reads past the remaining limit of a ByteBuffer; unchecked | position/limit/capacity, flip/clear/compact, record size | Check remaining() and byte protocol; fix buffer lifecycle rather than arbitrarily increasing buffer size |
| ReadOnlyBufferException | Writing to a read-only ByteBuffer; unchecked | Whether buffer was created via asReadOnlyBuffer, READ_ONLY map, or sharing mechanism | Use a writable buffer when writing is needed or separate memory regions appropriately |

### Three Common Points of Confusion

- InputStream.read() returns **-1** on normal EOF. This is a valid result; there is not necessarily an EOFException. Conversely, DataInputStream.readFully/readInt throws EOFException if there are not enough bytes for the requested structure.
- For InputStream.read(byte[]), the returned byte count may be smaller than the buffer length even when EOF has **not** been reached. You must loop until enough data is read according to your framing/record, or use readNBytes/readFully appropriately.
- OutputStream.close() may flush buffered data, but should not be assumed by default to guarantee data is durably persisted on disk. If the application requires durability, you must establish specific sync/transaction mechanisms, such as FileChannel.force(...) and the environment's guarantee limits.

## 3. Error Lookup Table for Charsets, Text, and Binary Data

| Error/symptom | Common cause | What to check? | Resolution |
| --- | --- | --- | --- |
| MalformedInputException | Byte sequence is invalid for the chosen charset, such as UTF-8 with an invalid continuation byte | Byte source, BOM, write/read charset, error position, whether file is truncated | Choose the right charset per data contract; replace erroneous characters only if business logic accepts data loss |
| UnmappableCharacterException | Unicode character cannot be represented in the target charset or transcoding sequence cannot be mapped | Encoder/decoder, target charset, source data, coding-error action | Use UTF-8/appropriate Unicode, or handle transcoding errors transparently |
| CharacterCodingException | Checked exception group for character encoding/decoding errors | IOException cause, decoder/encoder, sample bytes with sensitive data masked | Preserve original data for diagnosis; determine charset before decoding |
| UTFDataFormatException | Reading/writing DataInput/DataOutput modified UTF-8 format (e.g., readUTF/writeUTF) that is invalid or violates format limits | Matching writeUTF/readUTF pair, format/bytes written, whether data is truncated | Do not use readUTF to read arbitrary UTF-8 text; follow the DataInput/DataOutput protocol strictly |
| Characters turn into "�" (replacement character) without throwing | Decoder uses replacement error action or data was already mis-encoded earlier | Each encode/decode step, CharsetDecoder.onMalformedInput, stored source data | Choose REPORT policy to detect early when data fidelity must be preserved |
| "Mojibake" characters (e.g. "Ã©") | Bytes encoded with one charset but decoded with another | Source/target charset, BOM, default charset, and transport metadata | Specify charset explicitly on both ends; do not re-encode an already mis-decoded string as a hack |
| File appears empty or missing lines | Buffer not flushed, Reader/Writer not closed, read logic drops last element | flush/close, while loop, line separators, size on disk vs in RAM | Close streams properly, check EOF reading loop, and handle trailing data |

**Distinction:** Standard UTF-8 is used with Files.readString(path, StandardCharsets.UTF_8), InputStreamReader(..., UTF_8), OutputStreamWriter(..., UTF_8). DataInputStream.readUTF and DataOutputStream.writeUTF use **length-prefixed modified UTF-8**, which is not equivalent to reading/writing ordinary UTF-8 text.

## 4. Network Error Lookup Table: Socket, Timeout, and TLS

This group belongs to java.net and javax.net.ssl; several errors are subclasses of IOException. When diagnosing, identify whether the failure occurred at **DNS, TCP connect, TLS handshake, read, write, or close**.

| Error | Common symptom/meaning | Practical checks | Approach |
| --- | --- | --- | --- |
| UnknownHostException | Cannot resolve hostname or hostname has no suitable address | Hostname, DNS from runtime environment, search domain, container/proxy config, DNS stability | Fix DNS/host; perform bounded retries only when the error is genuinely transient |
| ConnectException | TCP connection refused or failed at connect step, e.g. "Connection refused" | Host:port, service listening, firewall, routing, IPv4/IPv6, proxy | Verify endpoint and service status; do not confuse with read timeout |
| SocketTimeoutException | Exceeded timeout during socket connect or read (per configured operation) | Connect timeout or SO_TIMEOUT? Network reachable? Server responding slowly? | Set deliberate timeouts, measure latency, retry with idempotency/backoff |
| SocketException | General socket error, such as reset, broken pipe, socket closed | Did peer close? Local close? Idle timeout, HTTP proxy, keepalive | Identify lifecycle and potentially transferred data; do not treat every reset as a safely retryable network glitch |
| BindException | Cannot bind address/port, usually port already in use or invalid address | Socket local address/port, process holding it, bind config, OS permissions | Choose valid port/address, stop conflicting process if permitted |
| SSLHandshakeException | TLS handshake did not complete (certificate, protocol, cipher, hostname, trust) | Cause chain, certificate chain/truststore, hostname, expiry, TLS version, system clock | Fix trust/identity/protocol; do not disable certificate verification to bypass the error |
| SSLException | General TLS error during handshake or data transfer | Stack/cause, handshake vs application data phase, connection close | Find root cause, check protocol and configuration on both ends |

Key points to remember:

- Connect timeout and read timeout are two distinct phases. A successful connect does not prove the server will return data on time.
- Retrying a state-reading operation differs from retrying a write/payment command: if the request reached the server and the response was lost, the client may not know whether the operation completed. Use request-id, idempotency keys, or application-level verification flows.
- Never log payloads, credentials, private keys, access tokens, or sensitive certificate contents when collecting traces. Log only the technical information needed for diagnosis.

## 5. Error Lookup Table for ZIP and Object Serialization

| Error/symptom | Location and meaning | Information to check | Resolution |
| --- | --- | --- | --- |
| ZipException | java.util.zip encountered invalid or unprocessable ZIP/GZIP/DEFLATE data | Actual format, header/magic, whether file downloaded completely, CRC/entry, compression method | Verify source and integrity, ensure decompression matches format; limit decompressed size to prevent zip bombs |
| EOFException during decompression | Compressed stream was truncated or structure is incomplete | Bytes downloaded/received vs expected, checksum, source close | Re-transfer/re-download in a controlled way, verify completeness before processing |
| StreamCorruptedException | ObjectInputStream detected an invalid header, token, or Java serialized stream structure | Did writer use ObjectOutputStream? Read/write order, inserted/truncated bytes, protocol mismatch | Align format and order, avoid mixing text/raw data into object streams |
| InvalidClassException | Class incompatible with stream (serialVersionUID, type/class descriptor), or rejected by ObjectInputFilter | Full message/cause, serialVersionUID, class changes, filter policy, binary class name | Fix compatibility/schema or proper allowlist; do not disable the filter just to get past the error |
| NotSerializableException | Writing a non-Serializable class in the object graph | Type named in message, fields holding resources/other non-serializable objects | Use serializable DTOs, mark non-serialized state transient when semantically appropriate |
| OptionalDataException | ObjectInputStream read a type mismatching primitive/object data in stream, or reached end of custom data | Order of writeObject/writeInt/readObject/readInt, custom readObject/writeObject | Match format and order, manage versioning explicitly |
| InvalidObjectException | Object data invalid in validation/readResolve or restoration logic | Cause, class invariants, raw data, validation code in custom deserialization | Validate and reject invalid data, fix source or apply verified migration |
| ClassNotFoundException | Reader cannot find the class described in the stream; checked exception, does not extend IOException | Classpath/module path, package/class name, deployed version, custom class loader | Ensure the matching class is present or switch to an explicit schema-based data exchange format |

**Serialization security limits:** ObjectInputFilter can restrict classes, depth, reference count, bytes, and array sizes during deserialization. The filter must be installed **before readObject()**, preferring an allowlist for trusted sources while still bounding external input sizes. A filter does not authenticate the sender, replace encryption/signatures, or prevent every risk inside custom readObject. For untrusted input, consider an exchange format with an explicit schema and validation.

## 6. Standalone Java 17+ Example: Triggering and Distinguishing Three I/O Errors

This example creates a temporary directory, demonstrates three specific exceptions in sequence, and then cleans up the temporary files. Each error is caught with the appropriate exception type to show how to read the cause. No sensitive paths or external resources are used.

Create file **IoErrorLookupDemo.java**:

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

            // 2. CREATE_NEW only creates the file when the path does not exist yet.
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

Expected output in an environment where temporary directories can be created/read/written/deleted:

~~~text
NoSuchFileException: missing.txt
FileAlreadyExistsException: existing.txt
MalformedInputException: invalid UTF-8
~~~

**Why does this example work?**

1. Files.readString(missing, UTF_8) encounters a non-existent file and therefore throws NoSuchFileException on common default file-system providers. There is no prior exists check, because the read operation itself is where the true state is determined.
2. Files.writeString(existing, ..., CREATE_NEW) creates the file the first time. The second time, the CREATE_NEW option itself requires not overwriting an existing path, so it throws FileAlreadyExistsException. This is usually the right choice to avoid accidental overwrites.
3. Byte 0xC3 is the leading byte of a two-byte UTF-8 sequence, but the next byte 0x28 is not a valid continuation byte. Files.readString(..., UTF_8) reports MalformedInputException, showing the error is in **decoding bytes to characters**, not a missing file or denied permission.
4. finally cleans up the paths created in the exercise. If cleanup itself fails, IOException may be thrown from finally; in larger applications, preserve the original exception and attach cleanup errors as suppressed/separate logs rather than accidentally masking the primary cause.

**Limitations of the example:** If the temporary directory is not writable, runs out of space, or another process interferes, the program may fail with a different exception before printing all three lines. That is real I/O behavior to diagnose, not a reason to catch all exceptions and print fake results.

## 7. Error Diagnosis and Contextual Logging Patterns

You do not need to log full customer data to debug I/O. Log enough information to identify **which operation**, **which target**, and **what reason the OS/provider reported**.

Illustrative method snippet in an application that already has a logger and path:

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
        // Check service account, ACLs, and parent directory permissions.
        throw new IOException("Cannot read config: access denied", ex);
    } catch (FileSystemException ex) {
        // getReason() may be null; content may depend on OS/provider.
        throw new IOException("Cannot read config: " + ex.getReason(), ex);
    }
}
~~~

This is an **illustrative method snippet**, not a standalone program since it lacks a class and main. In a real environment:

- Log stack traces/causes to an internal log channel with appropriate access controls; return only safe messages to users. Do not automatically print absolute paths containing account names, secrets, or infrastructure layout in public APIs.
- Preserve the cause when wrapping errors. Do not turn a permission error into "file not found" in operational logs; the HTTP layer may return a different status message, but the original evidence must be kept.
- For FileSystemException, use getFile(), getOtherFile(), getReason() if helpful; some values may be null and the exception message may carry information that should not be exposed publicly.
- Do not catch SecurityException with IOException. If runtime policy errors need handling, catch them under a separate contract and avoid obscuring policy violation signals.
- When using try-with-resources, errors from closing resources may reside in getSuppressed() of the primary exception. Read suppressed exceptions as well when an operation chain involves multiple resources.

### I/O Incident Recording Template

~~~text
Operation      : READ_TEXT / WRITE_BYTES / MOVE / SOCKET_CONNECT / DESERIALIZE
API            : Files.readString(Path, UTF_8)
Resource       : <path alias or endpoint with sensitive info masked>
Environment    : JDK version, OS, container/mount, service account
Exception      : <fully-qualified exception class>
Message/Reason : <concise message, sensitive info removed>
Cause          : <cause chain, internal stack trace>
Suppressed     : <cleanup/close errors if any>
Input format   : UTF-8 / binary protocol / serialized object / ZIP / ...
Timing         : Time of occurrence, open/read/write/flush/close phase
Observed state : Exists? Directory? Permissions? Free space? Host:port reachable?
Concurrency    : Concurrent writer/deleter/closer? Any prior retry?
Next action    : Fix path / permissions / schema / storage / connectivity / code
~~~

Information from exists/isDirectory/isReadable is only a point-in-time snapshot and may change immediately afterward. Do not use them as a guarantee that open/read/write will succeed; you still need to handle errors from the actual operation.

## 8. Low-Risk Investigation Workflow in Order

1. **Pinpoint the failure point:** read the top 1–3 stack frames belonging to your code along with the exception class, cause, and suppressed exceptions. Do not start by changing charsets or granting broader permissions before knowing the failure phase.
2. **Cross-reference the API type:** FileInputStream may report a broad FileNotFoundException; Files may provide a more specific NoSuchFileException or AccessDeniedException. For networking, identify connect/read/write/TLS before tuning timeouts.
3. **Inspect non-mutating facts:** JDK/OS version, actual path, working directory, isRegularFile/isDirectory, permission/mount info if allowed; do not run delete commands, recursive chmod, or kill processes to test theories.
4. **Check resources:** is there remaining space/quota, are streams/channels/sockets leaking, are file handles/locks held, is pool usage or concurrent I/O task count abnormal?
5. **Check the data contract:** do writer and reader agree on charset, record framing, field order, version/schema, checksum/length? For ZIP and serialized streams, is the format valid?
6. **Reproduce in a controlled way:** use temporary files and non-sensitive data; test success + missing input + permission denied + truncated data + concurrently modified file when those scenarios are genuinely relevant.
7. **Fix root cause, test negative cases:** fix path/permissions/resource lifecycle/charset/framing; verify specific exceptions are handled properly. For write operations, check state before retrying to avoid duplicate or corrupted data.
8. **Add observability:** if the issue has not reproduced, log additional operation metadata, expected/read byte counts (without logging content), connect/read/write durations, path alias, exception cause, and correlation id.

### Quick Decision Questions

| Question | If the answer is "Yes" | What to check next |
| --- | --- | --- |
| Does the error happen immediately when opening the file? | Likely related to path, type, permissions, or resources | Path resolution, working directory, service account permissions |
| Opens fine but fails after multiple reads? | Truncated data, wrong framing, connection error, or changing source | Length/record boundary, EOF, bytes read, writer/peer |
| Fails only with Vietnamese/special characters? | Mismatched charset or transcoding | UTF-8, BOM, decoder policy, raw bytes |
| Fails only under high load/concurrency? | Leak, lock, contention, or race condition | try-with-resources, file handles, channel close, pool size |
| Fails only upon deploy/in container? | Working directory, mount, account, DNS, or permissions changed | Environment diff, volume, path, service user, network route |
| Fails only with data saved by an older version? | Format/schema/serialVersionUID changed | Version, migration, classpath, backward compatibility |
| Fails only after socket idle time? | Idle timeout, peer/proxy close, or connection reset | Configured timeouts, keepalive, lifecycle, request replay safety |

## 9. Preventing Errors at Design Time

### Resource Lifecycle Management

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

This is an illustrative method. try-with-resources closes BufferedReader even when reading fails and helps prevent leaks. Do not open a stream outside try and forget to close it on a return or catch branch.

### Choosing Open/Write Strategy by Contract

- **Read-only:** Files.newInputStream(path, READ) or Files.newBufferedReader(path, UTF_8); handle missing files, permissions, and data errors as intended.
- **Create new file, strictly never overwrite:** Files.write(..., CREATE_NEW) or Files.createFile(path), catching FileAlreadyExistsException to handle conflicts.
- **Controlled overwrite:** Write complete data to a temporary file on the same file system, check flush/close, then move to replace if the contract allows. ATOMIC_MOVE is not supported by all providers; handle AtomicMoveNotSupportedException and decide fallback based on atomicity requirements, without silently pretending to be atomic.
- **Reading large data:** Use streams/channels and bounded buffers; avoid Files.readAllBytes for unbounded files because it can cause memory pressure.
- **Reading text:** Specify UTF-8 or the documented charset; do not rely on the default charset when exchanging data with other systems.
- **Network I/O:** Configure per-phase timeouts, bound payload sizes, and use conditional/idempotent retries; record partial results when required by the protocol.
- **Serialization:** Set an appropriate ObjectInputFilter before calling ObjectInputStream.readObject; validate data after restoration; bound input bytes upfront.

### When Should You Retry?

| Situation type | Automatic retry? | Reason |
| --- | --- | --- |
| Missing file due to mistyped path | Usually no | Retrying does not fix the path |
| AccessDeniedException due to static ACL | Usually no | Permissions or policy must be fixed |
| FileAlreadyExistsException with CREATE_NEW | No with the same name and request | Retrying will keep colliding |
| SocketTimeoutException on idempotent query | Possible, with limit and backoff | Sometimes a transient network glitch, but still needs bounds |
| Write command with side effects already sent, response timed out | Only with guarantee protocol/idempotency key | Risk of executing twice |
| Out of disk space or out of file handles | Do not retry aggressively in a loop | Resources must recover and partial writes must be handled |
| MalformedInputException due to fixed wrong-charset file | No | Format/charset must be fixed; retrying does not alter bytes |
| Unexpected EOF on partially downloaded data | Can re-download if source/contract allows | Must verify checksum/length and avoid splicing mismatched sessions |

## 10. Knowledge Check

1. Why is FileNotFoundException insufficient to conclude a file does not exist?
2. Files.exists(path) just returned true, yet immediately afterward Files.readString(path) still throws NoSuchFileException. How can this happen?
3. When DataInputStream.readInt throws EOFException, why does handling differ from a while(InputStream.read() != -1) loop?
4. How do you distinguish a charset error from a truncated byte stream error?
5. When Files.move fails, which details of FileSystemException help locate the cause?
6. Why is setting CREATE_NEW generally safer than a "check exists then create" sequence when multiple writers exist?
7. How does SocketTimeoutException during connect differ from during read? Why should you not retry every send unconditionally?
8. How does an IOException from close affect a "write succeeded" claim?
9. Which exceptions in the tables are unchecked, and why does catch(IOException) not cover them?
10. What two very different situations can InvalidClassException indicate in Java serialization?

**Passing criteria:** You can identify the failing operation, exception, and verifiable cause; pick specific APIs/checks to distinguish hypotheses; handle resources and errors properly while avoiding dangerous retries; and avoid leaking sensitive information in logs.

## Java SE 17 Reference Documentation

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
