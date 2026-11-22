# Resource Closing Responsibility Table by API in Java I/O

## 1. How to Read This Table: Who Opens, Who Closes?

In Java, **resource ownership** determines which component is responsible for calling **close()**. An object having a close() method is not enough to conclude that the code currently using it is allowed to close it: the object may have been created locally, borrowed from an external caller, or had ownership transferred under an API contract.

| Scenario | Who must close? | Principle |
|---|---|---|
| A method opens a file, socket, channel, directory stream, etc. itself | The method that opened it | Use try-with-resources to close along every path, including when an exception occurs. |
| A method **receives** an InputStream, OutputStream, Reader, Writer, etc. passed in by the caller | Usually the caller | The callee uses it and returns; close only when the API explicitly documents taking ownership. |
| A method returns an object holding an open resource | The caller receiving the result | Document clearly in the contract that the caller must close it; avoid returning hidden, hard-to-track resources. |
| Wrapping a stream/channel in a wrapper | The owner of the wrapper **and** underlying resource per contract | Closing a wrapper usually closes the underlying resource as well. If the underlying resource is borrowed, do not close the wrapper unilaterally. |
| An API performs the full read/write in a single call and returns only data/Path/result | The API itself | No resource object remains for the caller to close; deleting files or cleaning up data is a separate responsibility. |

**Default rule for quick lookup:** if your own code creates a resource with an open/close lifecycle, put it in try-with-resources; if an existing resource is merely passed in, **do not close it** unless a transfer-of-ownership contract exists. Specific exceptions should be checked per API below.

## 2. java.io Reference Table: Streams, Readers, Writers, and Wrappers

| API or creation form | Typical owner | What to do when done? | Impact and notes |
|---|---|---|---|
| **new FileInputStream(file)**, **new FileOutputStream(file)** | Code calling the constructor | **close()** | Releases the file descriptor; OutputStream.close() closes the write stream and does not replace mechanisms that ensure data is durable on disk. |
| **new FileReader(file, charset)**, **new FileWriter(file, charset)** | Code opening the file | **close()** | Closes the reader/writer and file resource; specify the charset explicitly if content must be reproduced consistently. |
| **new BufferedInputStream(input)**, **new BufferedOutputStream(output)** | Code owning the wrapper per contract | **close() the wrapper** | Closing the wrapper closes the underlying stream; for output streams, close() also flushes buffered data. |
| **new BufferedReader(reader)**, **new BufferedWriter(writer)** | Code owning the wrapper | **close() the wrapper** | Closing the wrapper cascades to closing the underlying reader/writer; for writers, close or flush is needed to push out buffered data. |
| **new InputStreamReader(input, charset)**, **new OutputStreamWriter(output, charset)** | Code owning the wrapper | **close() the wrapper** | Closes the byte ↔ character conversion layer and closes the underlying stream. |
| **new DataInputStream(input)**, **new DataOutputStream(output)** | Code owning the wrapper | **close() the wrapper** | Closes the underlying stream; DataOutputStream's close() also finishes the write path. |
| **new ObjectInputStream(input)**, **new ObjectOutputStream(output)** | Code owning the wrapper | **close() the wrapper** | Closes the underlying stream; the written object stream must be completed/flushed before ending. Do not use ObjectOutputStream on untrusted Java Serialization data. |
| **new PrintStream(output)**, **new PrintWriter(writer/output)** | Code owning the wrapper | **close() if owning the output** | Closing the wrapper closes the write target. Both classes may record errors rather than throwing IOException on several operations; check **checkError()** when write error detection is needed. |
| **new RandomAccessFile(file, mode)** | Code opening the file | **close()** | Releases the file; **getChannel()** returns a channel bound to the same file, so closing one side can affect the other. |
| **new ByteArrayInputStream(bytes)**, **new ByteArrayOutputStream()** | Code creating the object | No OS handle requiring closure | close() has no effect on these two classes; distinguish them from wrappers backed by real system resources. |
| **new StringReader(text)**, **new StringWriter()** | Code creating the object | No file/socket to release | StringReader.close() marks it closed so subsequent reads fail; StringWriter.close() has no effect. Do not generalize these two classes to all Readers/Writers. |

For example, closing a BufferedReader created from a FileReader propagates down to FileReader; there is no need to close each layer manually. Conversely, a BufferedWriter wrapping **System.out** must not be closed unilaterally, because doing so would close the standard stream shared by other components.

## 3. java.nio.file.Files Reference Table

Distinguish **methods that return an open resource** from **methods that perform all I/O internally and return data**.

| API | Return value | Closing responsibility |
|---|---|---|
| **Files.newInputStream(path)**, **Files.newOutputStream(path)** | Open InputStream/OutputStream | **Caller closes** the returned stream. |
| **Files.newBufferedReader(path, charset)**, **Files.newBufferedWriter(path, charset, options…)** | Open BufferedReader/BufferedWriter | **Caller closes** the returned reader/writer. |
| **Files.newByteChannel(path, options…)** | Open SeekableByteChannel | **Caller closes** the channel. |
| **Files.newDirectoryStream(dir)**, glob/filter variants | Open DirectoryStream | **Caller closes** after iteration; even if iteration stops early or an error occurs. |
| **Files.lines(path, charset)** | Stream&lt;String&gt; backed by an open file | **Caller closes the Stream** via try-with-resources. count(), forEach(), findFirst(), etc. **do not close** the underlying source automatically. |
| **Files.list(dir)** | Stream&lt;Path&gt; that may hold a directory resource | **Caller closes the Stream**. |
| **Files.walk(start, …)**, **Files.find(start, …)** | Stream&lt;Path&gt; traversing a directory tree | **Caller closes the Stream**; the source may hold directory handles during traversal. |
| **Files.readAllBytes(path)**, **Files.readAllLines(path, charset)**, **Files.readString(path, charset)** | byte[], List&lt;String&gt;, String | The API manages I/O internally; **caller has no stream to close**. Consider memory usage if the file is large. |
| **Files.write(path, bytes/lines, …)**, **Files.writeString(path, text, charset, …)** | Path | The API opens/closes resources internally; **caller does not close the Path**. |
| **Files.copy(sourcePath, targetPath, …)**, **Files.move(source, target, …)** | Path | The API manages internal handles; no stream is returned to close. |
| **Files.copy(inputStream, targetPath, …)** | long (byte count) | The API **does not close the inputStream** passed in by the caller; caller retains responsibility. |
| **Files.copy(sourcePath, outputStream)** | long (byte count) | The API **does not close the outputStream** passed in by the caller; caller retains responsibility. |
| **Files.walkFileTree(start, visitor)** | Path | The API manages opening/closing directories during traversal; however, any resource opened by the visitor itself must still be closed by the visitor. |
| **Files.exists/isRegularFile/size/delete/deleteIfExists/createTempFile** | Value/Path, no stream returned | No handle for the caller to close; **temporary files must still be deleted if the application is responsible for cleanup**. |

**Common mistake:** writing Files.lines(path).filter(...).count() without placing the returned Stream in try-with-resources. A terminal operation only ends the Stream pipeline evaluation; it does not equal close(). For a Stream created from an in-memory collection like list.stream(), there is normally no external resource to release.

## 4. Channels, Filesystems, and Other NIO Objects Reference Table

| API | Who closes? | Important notes |
|---|---|---|
| **FileChannel.open(path, options…)** | Caller closes FileChannel | Closing the channel releases the file descriptor. |
| **AsynchronousFileChannel.open(path, options…)** | Caller closes AsynchronousFileChannel | Close the channel after asynchronous operations are processed/synchronized by design; avoid use after close. |
| **Files.newByteChannel(path)** | Caller closes SeekableByteChannel | Even when going through an abstraction layer, ownership follows the returned object. |
| **Channels.newInputStream(channel)** / **Channels.newOutputStream(channel)** | Component owning the wrapper | Closing the adapter stream closes the underlying channel; do not do this if the channel is borrowed. |
| **FileLock** from FileChannel.lock()/tryLock() | Holder of the lock releases it | Use release() or AutoCloseable.close(); closing the channel also releases associated locks, though it should not replace an explicit lock lifecycle. |
| **FileChannel.map(…) → MappedByteBuffer** | No public close() method on the buffer | Closing FileChannel **does not guarantee** immediate unmapping of the memory-mapped region; unmapping usually depends on buffer lifetime/GC. Do not assume delete/truncate succeeds immediately on all OSes. |
| **FileSystems.newFileSystem(…)** (e.g., ZIP filesystem) | Code creating the FileSystem | Close the FileSystem when finished to release the provider's resources. |
| **FileSystems.getDefault()** | JVM runtime | **Do not close** the default filesystem. |
| **FileSystems.getFileSystem(uri)** | Depends on origin contract | This returns an existing filesystem; do not close if borrowed or shared. |
| **FileSystems.getDefault().newWatchService()** | Code creating the WatchService | Close the WatchService to release the directory monitoring system resources. |
| **Path**, **Files.readAttributes(…)**, **BasicFileAttributes** | Not applicable | Path and attribute snapshots are not open handles; there is no close() to call. |

Channels and streams created over the same underlying source may **share a lifecycle**. Do not open multiple wrappers concurrently and assume closing one wrapper leaves the others working.

## 5. Common I/O APIs Outside java.io/nio Reference Table

| API | Responsibility | Edge cases to avoid |
|---|---|---|
| **new Scanner(path, charset)**, **new Scanner(inputStream/reader)** | Close Scanner if it owns the input; Scanner.close() closes the source if the source is Closeable | Scanner(System.in).close() will also close **System.in**; normally do not close shared standard input. |
| **new ZipInputStream(input)**, **new GZIPInputStream(input)** | Owner of the wrapper closes the wrapper | Closing propagates to the underlying input; each entry in ZipInputStream ends with closeEntry() to advance entries, but **closeEntry() does not replace close() on the entire stream**. |
| **new ZipOutputStream(output)**, **new GZIPOutputStream(output)** | Owner of the wrapper closes the wrapper | You can call finish() to complete the compression format while keeping the underlying stream open per the API design; wrapper's **close()** also closes the underlying output. |
| **new ZipFile(path)**, **new JarFile(path)** | Code opening the archive file | Close ZipFile/JarFile; InputStreams obtained via getInputStream(entry) should also be closed within their usage scope before closing the archive. |
| **Socket**, **ServerSocket** created/accepted by the application | Code owning the socket closes the socket | Closing a socket or one of its streams typically closes the connection; do not close a socket's stream when the connection must be reused. |
| **URL.openStream()** | Calling code | Close the returned InputStream; specialized HTTP connection management should follow the contract of the library in use. |
| **Process.getInputStream/getErrorStream/getOutputStream** | Code managing the Process and its streams | Close streams when no longer used, consume stdout/stderr to avoid deadlocks, and manage Process lifecycle separately; closing streams alone does not terminate the process. |

For resources borrowed from frameworks, containers, libraries, or callbacks, **the specific API contract can override default ownership**. For instance, a framework might invoke a callback with an OutputStream that the framework itself closes after the callback returns.

## 6. Right/Wrong Patterns by Scenario

### 6.1. Self-opened: self-closed

~~~java
try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String firstLine = reader.readLine();
    // Use firstLine here.
} // reader.close() runs even if readLine() throws IOException.
~~~

When wrapping FileInputStream in BufferedInputStream, the object managed at the application layer is usually the **outermost wrapper**: closing the wrapper closes the underlying stream. If building multi-layer wrappers can fail midway, structure each acquisition step in appropriate try-with-resources scopes so already-opened sources do not leak.

### 6.2. Borrowed OutputStream: write without closing

~~~java
static void copyToCallerOwnedDestination(Path source, OutputStream destination)
        throws IOException {
    Files.copy(source, destination);
    destination.flush(); // Only when the contract requires flushing data now.
    // Do not close destination: the caller owns it.
}
~~~

This example illustrates a **caller-owned contract**; document this clearly in the real method's JavaDoc. flush() is not close(), and it does not guarantee data has been durably synced to the storage device. Wrapping destination in a try-with-resources BufferedOutputStream and closing the wrapper here would unintentionally close the caller-owned destination as well.

### 6.3. Returned Stream: recipient must close

~~~java
static long countLines(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
        return lines.count();
    }
}
~~~

Wrong resource lifecycle:

~~~java
long count = Files.lines(file).count(); // The Stream holding the file resource is never closed.
~~~

When designing an API that returns a file-backed Stream, document the caller's close responsibility. If the data is small and lazy evaluation is unnecessary, consider returning a fully read List inside a try-with-resources scope to simplify ownership.

### 6.4. Standard streams and shared resources

- **System.in, System.out, System.err** are generally shared application/JVM resources; avoid closing them inside a helper or exercise. Only flush standard output when needed.
- **Wrappers propagate close to the source:** Scanner(System.in), BufferedWriter(new OutputStreamWriter(System.out, …)), and PrintWriter(System.out) can all close the standard stream when the wrapper is closed.
- **Shared or pooled resources:** do not close a borrowed source unless the library/owner transfers ownership. A non-closing adapter must be designed explicitly; merely skipping close() on a BufferedWriter can leave buffered data unwritten.

## 7. Runnable Java 17+ Program

This is a standalone example demonstrating the difference between APIs that manage resources themselves (**readAllLines**, **writeString**), APIs that return a handle (**newBufferedReader**, **newDirectoryStream**), and Streams that must be closed (**Files.lines**). The temporary file is deleted in finally; deletion is independent of close().

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

            // Files opens/closes the source internally; the resulting List needs no close().
            List<String> all = Files.readAllLines(file, StandardCharsets.UTF_8);
            System.out.println("readAllLines=" + all.size());

            // The caller owns BufferedReader, so use try-with-resources.
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

Explanation: Files.writeString() and Files.readAllLines() close their internal resources; Files.newBufferedReader(), Files.lines(), and Files.newDirectoryStream() return objects that the caller must close. try-with-resources closes the resources before finally deletes the temporary file, avoiding deletion while a handle is still open.

## 8. Exceptions, close(), and Release Order

~~~java
try (InputStream input = Files.newInputStream(path);
     BufferedInputStream buffered = new BufferedInputStream(input)) {
    // Read data from buffered.
}
~~~

This example demonstrates **closing in reverse order of declaration**: buffered.close() first, input.close() second. Since closing BufferedInputStream already closes the underlying InputStream, the source may be closed again in this example; this pattern is useful when ensuring an opened InputStream is still closed if wrapper construction fails. When choosing a design, verify idempotency of closing multiple times on the specific API; if wrapper initialization failure does not need separate handling, managing only the outermost wrapper in try-with-resources is usually sufficient.

If the try body throws an exception and close() also throws, try-with-resources keeps the body's exception as the **primary exception** and attaches the close exception as a **suppressed exception** (see Throwable.getSuppressed()). When closing multiple resources, Java attempts to close them in reverse order even if one close fails. Avoid hand-written finally blocks where a close error masks the original error or silently swallows errors unintentionally.

**Do not rely on GC or finalize() to close files/sockets/channels.** Collection timing is non-deterministic. Likewise, deleteIfExists() removes the filename in the file system; it does not replace closing a stream/channel holding the file.

## 9. Pre-Close Lookup Checklist

1. **Origin:** Was the resource created here, passed in by a caller, or supplied by a framework/connection pool?
2. **Return value:** Does the API return plain data (byte[], String, List, Path) or an open object (Stream, Reader, Writer, Channel, DirectoryStream, Socket…)?
3. **Wrapper:** Does close() propagate to the underlying stream/channel? If so, do you actually own the right to close that underlying source?
4. **Laziness:** Is a Stream from Files.lines/list/walk/find closed inside try-with-resources, even if iteration stops early?
5. **Errors and write completion:** Will resources close when exceptions occur? Is buffered/ZIP/object output finalized according to the API contract? Is checkError() needed for PrintStream/PrintWriter?
6. **Transfer scope:** If returning an open resource to the caller, is the close responsibility documented in the contract? If receiving a borrowed resource, does the method leave its open/closed state intact?
7. **Cleanup beyond close:** Are temp file deletion, lock release, process management, or durable data sync handled separately when required?

When verifying an API not listed in the tables, check its return type, the **close/ownership** section in JavaDoc, and the wrapper's behavior toward its underlying source. The deciding principle is the **lifecycle contract**, not merely the method name or whether the object implements AutoCloseable.
