# Resource Closing Responsibility Table by API in Java I/O

## 1. How to Read the Table: Who Opens, Who Closes?

In Java, **resource ownership** determines which component is responsible for calling **close()**. Simply having a close() method on an object is not enough to conclude that the code currently using it is allowed to close it: the object may have been created here, borrowed from outside, or transferred ownership under an API contract.

| Scenario | Who must close? | Principle |
|---|---|---|
| Method opens a file, socket, channel, directory stream, etc. itself | The method that opened it | Use try-with-resources to close on every path, including when an exception occurs. |
| Method **receives** an InputStream, OutputStream, Reader, Writer, etc. passed by the caller | Normally the caller | The callee uses it and returns; close only when the API explicitly states it takes ownership. |
| Method returns an object that still holds an open resource | The caller receiving the result | Document clearly in the contract that the caller must close; avoid returning hidden, hard-to-track resources. |
| Placing a wrapper around a stream/channel | The party owning the wrapper **and** underlying resource per contract | Closing a wrapper usually closes the underlying resource as well. If the underlying resource is borrowed, do not close the wrapper arbitrarily. |
| API reads/writes completely in a single call and only returns data/Path/result | The API itself | No resource object remains for the caller to close; deleting files or cleaning up data is a separate responsibility. |

**Default quick-lookup rule:** if your code creates a resource with an open/close lifecycle itself, put it in try-with-resources; if an existing resource is merely passed in, **do not close it** unless there is a transfer-of-ownership contract. Specific exceptions should be checked per API below.

## 2. java.io Lookup Table: Stream, Reader, Writer, and Wrapper

| API or creation method | Typical owner | What to do when done? | Effects and notes |
|---|---|---|---|
| **new FileInputStream(file)**, **new FileOutputStream(file)** | Code calling the constructor | **close()** | Releases the file descriptor; OutputStream.close() closes the write stream and does not replace mechanisms ensuring data is durable on disk. |
| **new FileReader(file, charset)**, **new FileWriter(file, charset)** | Code opening the file | **close()** | Closes the reader/writer and file resource; specify charset explicitly if content must be reproduced consistently. |
| **new BufferedInputStream(input)**, **new BufferedOutputStream(output)** | Code owning the wrapper per contract | **close() the wrapper** | Closing the wrapper closes the underlying stream; for write streams, close() also flushes buffered data. |
| **new BufferedReader(reader)**, **new BufferedWriter(writer)** | Code owning the wrapper | **close() the wrapper** | Closing the wrapper cascades to close the underlying reader/writer; for writers, close or flush is needed to push buffered data out. |
| **new InputStreamReader(input, charset)**, **new OutputStreamWriter(output, charset)** | Code owning the wrapper | **close() the wrapper** | Closes the byte ↔ character conversion layer and closes the underlying stream. |
| **new DataInputStream(input)**, **new DataOutputStream(output)** | Code owning the wrapper | **close() the wrapper** | Closes the underlying stream; DataOutputStream's close() also terminates the write path. |
| **new ObjectInputStream(input)**, **new ObjectOutputStream(output)** | Code owning the wrapper | **close() the wrapper** | Closes the underlying stream; must finish/flush the serialized object sequence before ending. Do not use ObjectOutputStream for untrusted Java Serialization data. |
| **new PrintStream(output)**, **new PrintWriter(writer/output)** | Code owning the wrapper | **close() if owning the output** | Closing the wrapper closes the write target. These two classes may record errors instead of throwing IOException in some operations; check **checkError()** when write error detection is needed. |
| **new RandomAccessFile(file, mode)** | Code opening the file | **close()** | Releases the file; **getChannel()** returns a channel linked to the same file, so closing one side may affect the other. |
| **new ByteArrayInputStream(bytes)**, **new ByteArrayOutputStream()** | Code creating the object | No OS handle that must be closed | close() has no effect on these two classes; distinguish them from wrappers backed by real underlying resources. |
| **new StringReader(text)**, **new StringWriter()** | Code creating the object | No file/socket to release | StringReader.close() marks it closed so subsequent reads are invalid; StringWriter.close() has no effect. Do not generalize from these two classes to all Readers/Writers. |

For example, closing a BufferedReader created from a FileReader propagates down to FileReader; there is no need to close each layer manually. Conversely, a BufferedWriter wrapping **System.out** must not be closed arbitrarily, because doing so would also close the standard stream used by other components.

## 3. java.nio.file.Files Lookup Table

Distinguish **methods returning an open resource** from **methods performing all I/O internally and returning data**.

| API | Result | Closing responsibility |
|---|---|---|
| **Files.newInputStream(path)**, **Files.newOutputStream(path)** | Open InputStream/OutputStream | **Caller closes** the returned stream. |
| **Files.newBufferedReader(path, charset)**, **Files.newBufferedWriter(path, charset, options…)** | Open BufferedReader/BufferedWriter | **Caller closes** the returned reader/writer. |
| **Files.newByteChannel(path, options…)** | Open SeekableByteChannel | **Caller closes** the channel. |
| **Files.newDirectoryStream(dir)**, variants with glob/filter | Open DirectoryStream | **Caller closes** after iterating; even when stopping iteration early or if an error occurs. |
| **Files.lines(path, charset)** | Stream&lt;String&gt; backed by an open file | **Caller closes the Stream** via try-with-resources. count(), forEach(), findFirst(), etc. **do not close** the source automatically. |
| **Files.list(dir)** | Stream&lt;Path&gt; that may hold a directory resource | **Caller closes the Stream**. |
| **Files.walk(start, …)**, **Files.find(start, …)** | Stream&lt;Path&gt; walking a directory tree | **Caller closes the Stream**; the source may hold directory handles while traversing. |
| **Files.readAllBytes(path)**, **Files.readAllLines(path, charset)**, **Files.readString(path, charset)** | byte[], List&lt;String&gt;, String | API manages I/O internally; **caller has no stream to close**. Consider memory usage if the file is large. |
| **Files.write(path, bytes/lines, …)**, **Files.writeString(path, text, charset, …)** | Path | API opens/closes internal resources; **caller does not close Path**. |
| **Files.copy(sourcePath, targetPath, …)**, **Files.move(source, target, …)** | Path | API manages internal handles; no stream is returned to close. |
| **Files.copy(inputStream, targetPath, …)** | long (byte count) | API **does not close inputStream** passed by caller; caller retains responsibility. |
| **Files.copy(sourcePath, outputStream)** | long (byte count) | API **does not close outputStream** passed by caller; caller retains responsibility. |
| **Files.walkFileTree(start, visitor)** | Path | API manages opening/closing directories during traversal; however, any resource opened by the visitor itself must still be closed by the visitor. |
| **Files.exists/isRegularFile/size/delete/deleteIfExists/createTempFile** | Value/Path, no stream returned | No handle for caller to close; **temp files must still be deleted if the application is responsible for cleanup**. |

**Common mistake:** writing Files.lines(path).filter(...).count() without placing the returned Stream in try-with-resources. A terminal operation only ends the Stream computation; it does not mean close(). For a Stream obtained from an in-memory collection such as list.stream(), there is no external resource to release in typical cases.

## 4. Lookup Table for Channels, FileSystems, and Other NIO Objects

| API | Who closes? | Important notes |
|---|---|---|
| **FileChannel.open(path, options…)** | Caller closes FileChannel | Closing the channel releases the file descriptor. |
| **AsynchronousFileChannel.open(path, options…)** | Caller closes AsynchronousFileChannel | Close the channel after handling/synchronizing asynchronous tasks per design; avoid using after close. |
| **Files.newByteChannel(path)** | Caller closes SeekableByteChannel | Across abstraction layers, ownership still follows the returned object. |
| **Channels.newInputStream(channel)** / **Channels.newOutputStream(channel)** | Party owning the wrapper | Closing the adapter stream closes the underlying channel; do not do so if the channel is borrowed. |
| **FileLock** from FileChannel.lock()/tryLock() | Party acquiring the lock releases it | Use release() or AutoCloseable.close(); closing the channel also releases associated locks, but should not substitute for an explicit lock lifecycle. |
| **FileChannel.map(…) → MappedByteBuffer** | No public close() method on the buffer | Closing FileChannel **does not guarantee** the mapped memory region is unmapped immediately; unmapping typically depends on buffer lifecycle/GC. Do not assume delete/truncate succeeds immediately on all OSes. |
| **FileSystems.newFileSystem(…)** (e.g., ZIP filesystem) | Code creating the FileSystem | Close the FileSystem when done to release provider resources. |
| **FileSystems.getDefault()** | JVM runtime | **Do not close** the default filesystem. |
| **FileSystems.getFileSystem(uri)** | Depends on origin contract | This is an existing filesystem; do not close if borrowed or shared. |
| **FileSystems.getDefault().newWatchService()** | Code creating the WatchService | Close WatchService to release the directory watching system. |
| **Path**, **Files.readAttributes(…)**, **BasicFileAttributes** | Not applicable | Path and attribute snapshots are not open handles; there is no close() to call. |

Channels and streams created over the same underlying source may **share a lifecycle**. Do not open multiple wrappers simultaneously and assume closing one wrapper leaves the others working.

## 5. Lookup Table for Common I/O APIs Outside java.io/nio

| API | Responsibility | Edge cases to avoid |
|---|---|---|
| **new Scanner(path, charset)**, **new Scanner(inputStream/reader)** | Close Scanner if it owns the input; Scanner.close() closes the source if it is Closeable | Scanner(System.in).close() will also close **System.in**; normally do not close shared standard input. |
| **new ZipInputStream(input)**, **new GZIPInputStream(input)** | Wrapper owner closes the wrapper | Closing cascades to underlying input; each entry in ZipInputStream ends with closeEntry() to advance to the next entry, but **closeEntry() does not replace close() of the entire stream**. |
| **new ZipOutputStream(output)**, **new GZIPOutputStream(output)** | Wrapper owner closes the wrapper | finish() can be used to complete the compressed format while keeping the underlying stream open per API design; wrapper **close()** also closes the underlying output. |
| **new ZipFile(path)**, **new JarFile(path)** | Code opening the archive file | Close ZipFile/JarFile; InputStreams obtained via getInputStream(entry) should also be closed within their scope of use before closing the archive. |
| **Socket**, **ServerSocket** created/accepted by application | Code receiving socket ownership closes socket | Closing a socket or one of its streams typically closes the connection; do not close a socket stream when the connection needs to be reused. |
| **URL.openStream()** | Calling code | Close the received InputStream; specialized HTTP connection management should follow the library's contract. |
| **Process.getInputStream/getErrorStream/getOutputStream** | Code managing Process and its streams | Close streams when no longer needed, consume stdout/stderr to avoid blocking, and manage Process lifecycle separately; closing streams alone does not terminate the process. |

For resources borrowed from a framework, container, library, or callback, **the specific API contract may override default ownership**. For instance, a framework may invoke a callback with an OutputStream that the framework itself closes after the callback returns.

## 6. Right/Wrong Patterns by Scenario

### 6.1. Self-Opened: Self-Closed

~~~java
try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String firstLine = reader.readLine();
    // Use firstLine here.
} // reader.close() runs even if readLine() throws IOException.
~~~

With FileInputStream wrapped by BufferedInputStream, the object managed at the application layer is usually the **outermost wrapper**: closing the wrapper closes the underlying stream. If constructing nested layers can fail partway through, design each acquisition step in appropriate try-with-resources scopes so already-opened sources do not leak.

### 6.2. Borrowed OutputStream: Write Without Closing

~~~java
static void copyToCallerOwnedDestination(Path source, OutputStream destination)
        throws IOException {
    Files.copy(source, destination);
    destination.flush(); // Only when the contract requires data to be pushed out now.
    // Do not close destination: the caller owns it.
}
~~~

This example illustrates a **caller-owned contract**; this must be documented clearly in the JavaDoc of a real method. flush() is not close(), and does not guarantee data has been durably synchronized to the storage device. Wrapping destination in try-with-resources with a BufferedOutputStream and closing the wrapper here would accidentally close the caller-owned destination as well.

### 6.3. Returned Stream: Receiver Must Close

~~~java
static long countLines(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
        return lines.count();
    }
}
~~~

Wrong resource lifecycle:

~~~java
long count = Files.lines(file).count(); // Stream holding the file resource is not closed.
~~~

When designing an API that returns a file-backed Stream, document the caller's close responsibility. If the data is small and lazy evaluation is unnecessary, consider returning a List already read inside a try-with-resources scope to simplify ownership.

### 6.4. Standard System and Shared Resources

- **System.in, System.out, System.err** are typically shared application/JVM resources; avoid closing them in a helper or exercise. Flush standard output only when needed.
- **Wrappers cascade close to the source:** Scanner(System.in), BufferedWriter(new OutputStreamWriter(System.out, …)), and PrintWriter(System.out) can all close the standard stream when the wrapper's close() is called.
- **Shared or pooled resources:** do not close a borrowed source if the library/owner has not transferred ownership. A non-closing adapter must be designed explicitly; merely omitting close() on a BufferedWriter can leave buffered data unwritten.

## 7. Runnable Java 17+ Program

This is a standalone example demonstrating the difference between self-managing resource APIs (**readAllLines**, **writeString**), handle-returning APIs (**newBufferedReader**, **newDirectoryStream**), and Streams requiring close (**Files.lines**). The temporary file is deleted in finally; deletion is independent of close().

**File: ResourceCloseTableDemo.java**

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class ResourceCloseTableDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("close-table-", ".txt");

        try {
            Files.writeString(file, "alpha\nbeta\n", StandardCharsets.UTF_8);

            // Files opens/closes the source internally; the List result needs no close().
            List<String> all = Files.readAllLines(file, StandardCharsets.UTF_8);
            System.out.println("readAllLines=" + all.size());

            // Caller owns BufferedReader, so use try-with-resources.
            try (BufferedReader reader =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                System.out.println("first=" + reader.readLine());
            }

            // count() does not close the Stream: try-with-resources closes it.
            try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
                long count = lines.filter(s -> s.startsWith("b")).count();
                System.out.println("b-lines=" + count);
            }

            // DirectoryStream holds a handle that must be closed after iteration.
            try (DirectoryStream<Path> entries =
                    Files.newDirectoryStream(
                            file.getParent(), file.getFileName().toString())) {
                int matches = 0;
                for (Path entry : entries) {
                    if (entry.equals(file)) {
                        matches++;
                    }
                }
                System.out.println("matching-files=" + matches);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac ResourceCloseTableDemo.java
java ResourceCloseTableDemo
~~~

**Expected stdout:**

~~~text
readAllLines=2
first=alpha
b-lines=1
matching-files=1
~~~

Explanation: Files.writeString() and Files.readAllLines() close their internal resources; Files.newBufferedReader(), Files.lines(), and Files.newDirectoryStream() return objects that the caller must close. try-with-resources closes the resources before finally deletes the temp file, avoiding deletion while handles are still open.

## 8. Exceptions, close(), and Release Order

~~~java
try (InputStream input = Files.newInputStream(path);
     BufferedInputStream buffered = new BufferedInputStream(input)) {
    // Read data from buffered.
}
~~~

This example shows **closing in reverse order of declaration**: buffered.close() first, input.close() second. Since closing BufferedInputStream already closes the underlying InputStream, the source may be closed again in this example; this pattern is useful when ensuring an opened InputStream is still closed if wrapper construction fails. When choosing a design, check the idempotency/safety of calling close multiple times on the specific API; if wrapper initialization failure does not need special handling, usually only the outermost wrapper needs to be managed in try-with-resources.

If the try body throws an exception and close() also throws, try-with-resources keeps the body's exception as the **primary exception** and attaches the close exception as a **suppressed exception** (see Throwable.getSuppressed()). When multiple resources are closed, Java attempts to close them in reverse order even if one close fails. Avoid writing manual finally blocks where close errors mask the original error or errors are silently swallowed unintentionally.

**Do not rely on GC or finalize() to close files/sockets/channels.** Collection timing is non-deterministic. Likewise, deleteIfExists() removes the filename in the file system; it does not replace closing streams/channels holding the file.

## 9. Quick Lookup Checklist Before Calling close()

1. **Origin:** Was the resource created here, passed in by the caller, or provided by a framework/connection pool?
2. **Return value:** Does the API return plain data (byte[], String, List, Path) or an open object (Stream, Reader, Writer, Channel, DirectoryStream, Socket…)?
3. **Wrapper:** Does close() propagate to the underlying stream/channel? If so, do I actually have authority to close that underlying source?
4. **Laziness:** Are Streams from Files.lines/list/walk/find closed in try-with-resources, even when iteration stops early?
5. **Errors and write completion:** Is the resource closed on exceptions? Is buffered/ZIP/object output finalized per the API contract? Is checkError() needed for PrintStream/PrintWriter?
6. **Transfer scope:** If returning an open resource to the caller, is the close responsibility documented in the contract? If receiving a borrowed resource, does the method preserve its open/closed state?
7. **Cleanup beyond close:** Are temp file deletion, lock release, process management, or durable data sync handled separately when needed?

When verifying an API not listed in the tables, inspect its return type, the **close/ownership** section in JavaDoc, and the wrapper's underlying-source closing behavior. The deciding principle is the **lifecycle contract**, not merely the method name or whether an object implements AutoCloseable.
