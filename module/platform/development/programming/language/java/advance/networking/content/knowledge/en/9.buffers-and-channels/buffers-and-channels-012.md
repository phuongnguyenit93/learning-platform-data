# Local socket paths, access permissions, and file cleanup after close — Java NIO

A **Unix-domain socket** (often called a *local socket* or `AF_UNIX` socket) allows **two processes on the same machine** to exchange a byte stream without requiring an IP address and TCP port. In Java 17+, it is represented by `UnixDomainSocketAddress` and NIO channels such as `ServerSocketChannel` and `SocketChannel`. A server can bind to a **filesystem path**, for example `/run/myapp/service.sock`; the client connects to that path.

The most common mistake is that **the socket file has a different lifecycle from the channel**:

~~~text
ServerSocketChannel.open(UNIX)
       |
       | bind(UnixDomainSocketAddress.of(socketPath))
       v
Listening socket endpoint + node at socketPath
       |
       | accept() -> SocketChannel for each client
       |
       | server.close() / end of try-with-resources
       v
Kernel socket is closed; file at socketPath MAY STILL REMAIN
       |
       | Files.deleteIfExists(socketPath) (proper ownership/timing)
       v
Pathname is freed for the next bind
~~~

Do not confuse **closing the connection**, **deleting the socket name on the filesystem**, and **user permissions to access the socket**. They are three distinct responsibilities. Deleting the file too early can prevent new clients from finding the service; blindly deleting the file can delete another process's socket; leaving the file behind after closing can prevent the next startup from binding. This lesson focuses on these three issues in the **Buffers and channels** module of Java Networking.

## 1. Objectives

After this lesson, you will be able to:

- Explain `StandardProtocolFamily.UNIX`, `UnixDomainSocketAddress.of(Path)`, `ServerSocketChannel.bind()`, and `SocketChannel.connect()`.
- Distinguish a **path serving as an IPC endpoint name** from a **regular file containing data**, an IP/port address, and an unnamed Unix-domain socket address.
- Choose paths that are **short, absolute, on the default filesystem**, access-controlled, and have a clear lifecycle.
- Understand permissions on the **parent directory** and **socket node** in Linux/POSIX, Windows ACL differences, and portability limits.
- Explain why `close()` or `try-with-resources` **does not automatically unlink** a bound socket file, even when the server uses `bind(null)`.
- Write `try/finally` blocks to close channels and then clean up **only the path owned by the process**, without blindly deleting unverified paths.
- Identify stale socket files after a crash, duplicate startups, path length limits, `Address already in use`, `Access denied`, and symlink/race risks.
- Run a standalone Java 17+ program demonstrating local connection, byte exchange, observing that the file remains after close, and safely cleaning up the file in a dedicated temporary directory.

## 2. Comparing Unix-domain sockets with TCP loopback

| Aspect | TCP loopback | Unix-domain stream socket |
| --- | --- | --- |
| Endpoint | IP/hostname + port, e.g. `127.0.0.1:8080` | Filesystem path, e.g. `/run/myapp/service.sock` |
| Protocol family | `INET`/`INET6` | `UNIX` |
| Usage in Java NIO | `ServerSocketChannel` / `SocketChannel` | Same two classes, but opened with `UNIX` |
| Connection address | `InetSocketAddress` | `UnixDomainSocketAddress` |
| Communication | TCP/IP (via loopback) | Host-internal IPC stream, no IP routing |
| Protection | Firewall, bind address, OS, protocol | Parent-directory permissions, socket-node permissions/ACL, peer identity, protocol |
| Scope | Depends on bind address; loopback is current host only | Local machine supporting AF_UNIX only; a path may work across a shared filesystem namespace/container if the OS allows |
| Data handling | Byte stream, requires custom framing | Also a byte stream, requires custom framing |
| Closing server endpoint | Releases listener/socket via API | Closing the channel **does not automatically delete the filesystem name** |
| Java support | Available for a long time | NIO `UNIX` since **Java 16** (JEP 380); works reliably with Java 17+ if the OS supports it |

A Unix-domain socket can reduce overhead for internal IPC, but it is not an automatic drop-in replacement for all TCP communication: the two processes must have a way to see the same path in an appropriate **filesystem namespace**, and require permission policies as well as supporting Java/OS versions.

**Important API limitation in Java 17:** Unix-domain **streams** are supported via `ServerSocketChannel` and `SocketChannel`; do not use regular `new ServerSocket()` or `new Socket()` to request `UNIX`, and do not confuse them with `DatagramChannel` Unix-domain datagrams. If you need AF_UNIX datagrams or Linux abstract namespaces, you must check the specific capabilities of the system/library; JEP 380 does not provide those features through this standard API.

## 3. Creating a Unix-domain socket with Java 17+

### 3.1. Core APIs

~~~java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

Path socketPath = Path.of("/run/myapp/service.sock");
UnixDomainSocketAddress address = UnixDomainSocketAddress.of(socketPath);

try (ServerSocketChannel server =
        ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
    server.bind(address);
    try (SocketChannel accepted = server.accept()) {
        // Read/write on the accepted channel.
    }
} // ServerSocketChannel is closed, but the path needs separate cleanup.
~~~

This is an **illustrative code snippet inside a method** (requiring `throws IOException` or `catch`); the path `/run/myapp/service.sock` must be created in an existing directory with appropriate permissions. Do not copy this example verbatim to run on Windows because the Unix path format does not apply to Windows. A complete program that automatically creates an OS-appropriate path is in section 9.

- `ServerSocketChannel.open(StandardProtocolFamily.UNIX)` creates a listener channel for **Unix-domain stream sockets**.
- `UnixDomainSocketAddress.of(Path)` uses a `Path` from the **default file system** as the address. Not every `Path` from a ZIP filesystem or third-party provider is valid; the JDK may reject it.
- `server.bind(address)` associates the filesystem name with the listening endpoint, **creating a socket node at that path**.
- `server.accept()` returns a **separate connected** `SocketChannel` for the incoming client; the server continues listening unless closed.
- `SocketChannel.open(StandardProtocolFamily.UNIX)` creates a client channel; `client.connect(address)` connects to the bound path. `SocketChannel.open(address)` can also infer the protocol family from the address type.
- `server.close()` stops the listener; `accepted.close()` terminates only the accepted connection; the two resources do not share the same lifecycle.

The `try-with-resources` construct closes the channel even if the code throws an exception, but **it only calls the channel's `close()`**, not `Files.delete(...)` on the path.

### 3.2. No IP/port on a Unix-domain address

~~~java
UnixDomainSocketAddress address =
        UnixDomainSocketAddress.of("/run/myapp/service.sock");
Path path = address.getPath();
~~~

`UnixDomainSocketAddress` extends `SocketAddress` but is **not** an `InetSocketAddress`. There is no `getHost()` or `getPort()` to call. The socket's address is identified by a name in the filesystem namespace. A file with a `.sock` extension is **just a naming convention**; `service.ipc` also works if valid, while a regular file named with `.sock` **does not automatically turn into a socket**.

Avoid thinking "since `/tmp/app.sock` exists, I can just open it with `Files.newInputStream()` to read messages." A socket file is **not a data file read/written via Files I/O**. It is a special node serving OS `bind/connect` operations; communication payloads flow through `SocketChannel.read()/write()`.

### 3.3. Empty name (unnamed) and `bind(null)`

For a client using `SocketChannel.open(UNIX)` and then `connect(address)` without calling `bind` first, the **client's local endpoint is usually unnamed**, has an empty path, and has **no separate socket file to clean up**. That behavior differs from a server bound to a public path.

For a server:

~~~java
try (ServerSocketChannel server =
        ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
    server.bind(null); // OS/JDK chooses a dedicated temporary name for the server
    UnixDomainSocketAddress bound =
        (UnixDomainSocketAddress) server.getLocalAddress();
    Path autoPath = bound.getPath();
    // Provide autoPath to the client via a trusted IPC/discovery mechanism.
    // Ensure autoPath is cleaned up AFTER the server stops.
}
~~~

This is a **code snippet**. With `ServerSocketChannel.bind(null)` and the `UNIX` family, the JDK selects a **unique temporary path** in the configured directory. **This auto-generated file also persists after the server channel closes**, so cleanup is still required. Do not confuse a **server's `bind(null)`** with an **implicit client bind**: they do not produce the same pathname artifact.

The JDK has options such as `jdk.net.unixdomain.tmpdir` and `java.io.tmpdir`/OS environment settings to choose where to create automatic paths, depending on the operating system. Automatic naming reduces the chance of name collisions, but **does not replace access permission policies, discovery, or file cleanup**.

## 4. Socket paths: important operational rules

### 4.1. The directory must exist and have the right owner

Suppose a product uses `/run/myapp/service.sock`:

~~~text
/run/
  myapp/             <-- parent directory (owner / mode / ACL)
    service.sock      <-- Unix-domain socket node created by bind
~~~

A socket address needs a **valid path in the OS**, and the parent directory must exist. `bind` does not automatically create missing parent directories. When a service runs under a low-privilege user, do not assume that user can create files in `/run` or `/var/run`. The proper approach is to have the service manager or installation step create the runtime directory with the right owner/group and permissions.

Classification of common locations:

- `/run/<service>/...` on Linux: suitable for a daemon's runtime socket, if a properly permissioned directory already exists. It may not exist or be writable during personal tests.
- `/tmp/<service>.sock`: easy for quick experiments, but **dangerous if using a fixed name in a shared directory**; it is vulnerable to contention/races or accidental deletion by cleanup jobs. Only use it when policies are clearly understood and protections are in place.
- A **newly created private** temp directory: good for tests; code can create a folder with `Files.createTempDirectory("uds-")`, place the path inside, and delete the folder when the test finishes.
- On Windows: use Windows `Path`s and corresponding ACLs; do not assume POSIX modes, `/run/...` paths, or `chmod` commands work.

**Recommendation:** use a short, absolute path with a clear namespace, inside a directory controlled by the process. Paths specified in configuration should have a defined owner, collision risk assessment, and restart procedure; do not blindly "normalize and delete any file" on unvalidated input.

### 4.2. Path length limit in bytes

A Unix-domain pathname is stored in a buffer inside the socket address structure. The name has an OS/JDK-dependent limit; Java documentation describes it as **typically around 100 bytes**. Linux commonly has `sun_path[108]` in `sockaddr_un`, with null-termination details; other operating systems may have shorter limits.

Therefore:

- `/home/username/very/long/project/path/build/tmp/.../server.sock` can easily exceed the limit even though it is a completely valid regular file path.
- Unicode characters can occupy **multiple UTF-8 bytes**, so "100 Unicode characters" is not equivalent to "100 bytes for a socket name."
- Temp directories generated from `java.io.tmpdir` can also sit under long paths, especially on Windows CI or user home directories.
- When `bind` or `connect` fails with an error like "Unix domain path too long," switch to a **shorter path you own**. Do not delete files or tweak permissions thinking a length error is a permission error.
- Do not assume a string-normalized path is an absolute unique identifier when the filesystem has symlinks, mount namespaces, or case-folding.

To estimate the byte count on an OS using UTF-8, you can check `socketPath.toString().getBytes(StandardCharsets.UTF_8).length`; that does **not** replace the native contract/counter on every platform. The reliable approach is to keep the path short and test `bind` in the target environment.

### 4.3. Relative paths and filesystem providers

`UnixDomainSocketAddress.of(Path)` requires a `Path` from the **default file system**. A `Path` obtained from `FileSystems.newFileSystem(zipPath)` cannot be used as a normal Unix-domain socket address.

Relative paths make behavior depend on the working directory and how the API/OS resolves paths. Normalize configuration to a controlled absolute path, for example:

~~~java
Path socketPath = configuredDirectory
        .toAbsolutePath()
        .normalize()
        .resolve("service.sock");
~~~

This snippet is **code inside a method**, where `configuredDirectory` is an authorized/verified `Path`. `normalize()` only processes path syntax; it **does not** prevent symlinks, prove the path stays inside the intended directory, or replace permission checks. If an attacker controls the parent directory, a race can occur between checking the path and `bind/delete`.

## 5. Access permissions: the parent directory is as important as the socket node

A Unix-domain path is an access point in the filesystem, so **OS identity/permissions** govern who can create or connect to it.

### 5.1. On Linux/POSIX

According to Linux `unix(7)`:

- To create a socket node in a directory, the process needs **write** and **search/execute** permissions on the parent directory (and traversal across ancestor directories per OS rules).
- On Linux, connecting to a pathname **stream socket** requires **write** permission on the socket node; however, POSIX **does not guarantee all OSes apply socket permission bits identically to Linux**. You cannot rely solely on the socket node's mode for a portable security design.
- The node's mode can be affected by the process **umask** at creation time. If a service runs with an overly broad umask in a shared directory, the node may be exposed to unwanted clients.
- If the parent directory only allows the owner to traverse it, other users cannot easily access the node even if the socket-node mode is relatively permissive.
- Owner/group and ACL details should be inspected with appropriate OS tools, such as `ls -ld` on the directory and `ls -l` on the socket on Linux.

Example Linux deployment following the principle of least privilege:

~~~text
/run/myapp/             owner=myapp, mode=0700
/run/myapp/service.sock owner=myapp, mode created according to umask / policy
~~~

`0700` on the directory means the owner has read/write/execute permissions while other users/groups have none via mode bits; a private directory prevents strangers from easily creating, replacing, or accessing the socket name. If another service group needs to connect, use an explicitly configured group/ACL instead of opening up to `0777`.

**Do not claim `chmod 600 service.sock` is always sufficient.** On Linux, it applies to the pathname socket's permissions, but other OSes may handle it differently; in addition, there are ACLs, groups, mount namespaces, SELinux/AppArmor, process identity, service policies, and application-level authentication.

### 5.2. Creating a private directory with Java NIO on POSIX

In a Linux/POSIX application, you can create a new directory with the desired initial mode:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

Path parent = Path.of("/run/myapp");
Path privateDir = Files.createTempDirectory(
        parent,
        "uds-",
        PosixFilePermissions.asFileAttribute("rwx------"));
~~~

This is a **POSIX-dependent snippet**: `/run/myapp` must already exist and be writable by the service; the filesystem/provider must support POSIX attributes. When the provider does not support them, the operation can throw `UnsupportedOperationException`. It does not replace service manager configuration and parent directory ownership/ACLs, especially if the folder is reused across restarts.

If you want to change permissions after creation:

~~~java
Files.setPosixFilePermissions(privateDir,
        PosixFilePermissions.fromString("rwx------"));
~~~

This is also just a snippet; on Windows or providers without a POSIX view, it may not run. **Adjusting permissions after a file has already been created can expose a time window (race)**; for production protection, set appropriate permissions/umask **before binding**, and use a dedicated parent directory that cannot be modified by untrusted users.

### 5.3. On Windows

Windows supports Unix-domain sockets in compatible versions, and Java NIO `UNIX` can run if the OS/JDK supports it, but:

- Permissions are managed under the **Windows security model/ACL**, not POSIX `0700`/`0600` modes.
- Do not use `Files.setPosixFilePermissions(...)` as a portable way to grant permissions.
- Do not assume a `C:\...` path has the same limits/features as Linux or that socket-node permissions are enforced identically.
- Only work with directories and paths owned by the process/service; verify ACLs on the actual OS, and test connecting from an unauthorized account before declaring isolation effective.

In container systems, you also need to check the **mount namespace**: two containers can only connect via a path if the socket path is exposed/placed in an appropriate shared volume and policy allows it. Having the same filename string without sharing a namespace does not guarantee the same endpoint.

### 5.4. File permissions do not replace authentication

Unix-domain sockets only allow **local communication**, eliminating exposure of a TCP port to a remote network, but they **do not automatically prove client identity**. Depending on the environment:

- Apply least-privilege user/group and directory/socket permissions.
- Check peer credentials using **platform-specific** capabilities when available and required by the threat model. Some systems/JDKs offer extended options; do not assume every platform supports them.
- For sensitive operations, the application protocol still needs operation authorization, input validation, message size limits, DoS protection, and secret-safe logging.
- Do not use an uncontrolled shared directory to host an endpoint privileged to perform system administration tasks.

## 6. `close()` and `Files.deleteIfExists()` are two independent steps

### 6.1. Closing the channel does not remove the file from the filesystem

When binding a Unix-domain server socket to `/run/myapp/service.sock`, the OS creates a **socket node** on the filesystem. After closing the channel:

~~~java
server.close();
// Do not assume Files.exists(socketPath) will be false.
~~~

The JDK's `ServerSocketChannel.bind` documentation explicitly states that the socket node **persists after the channel is closed**, and must be deleted before rebinding the same pathname. This also holds true for server paths automatically allocated by the JDK via `bind(null)`. On Linux, this behavior corresponds to unlinking the pathname; it is **distinct** from closing the file descriptor.

Consequences:

- A **stopped** service still leaves `service.sock` on disk (a stale socket file).
- When the service restarts using the same path, `bind` may fail with "Address already in use" or an equivalent error.
- Simply using `try (ServerSocketChannel ... )` is not enough to ensure a clean next startup.
- Deleting the socket file **does not mean** kernel connections have been closed (if accepted channels remain), nor does it wait for clients to finish. Those steps belong to lifecycle management.

### 6.2. Why not call `Files.deleteIfExists(path)` before every startup?

Suppose instance A is running and owns `/run/myapp/service.sock`. Instance B starts up and sees the file exists. If B deletes the path **without checking**, B may delete A's active endpoint name. New clients can no longer connect via that path even though A's established connections may still be alive; B may take over the name and cause split-brain.

Therefore, **an existing file is not synonymous with a stale file**. Before cleaning up an existing path, you must know:

- Am I the **owner** of this endpoint/path?
- Is the old instance still running? Who holds the lock or service manager instance ownership?
- Is the path inside a **private directory** that cannot be replaced by someone else?
- Is there a race between checking existence/process/file type and the moment of deletion?

A safe approach for practice exercises is to create **a new exclusive temporary directory**, place the socket inside it, prevent other processes from writing to the folder, and clean up only the path created by the program itself. In production with a fixed path, use a service manager, singleton/locking, and a recovery procedure—never call unconditional deletion in a shared directory.

### 6.3. Cleaning up at the right time

Preferred lifecycle:

~~~text
1. Choose a private directory and a socket path that does not yet exist.
2. Open ServerSocketChannel(UNIX), bind the path.
3. Accept/complete in-flight requests.
4. Stop accepting new connections, close the listener and accepted channels according to ownership.
5. Once sure this instance owns the path, delete the socket node.
6. Delete the temporary directory created by this instance (if empty).
~~~

For a real server:

- To stop accepting new clients, close the listener and ensure the accept loop terminates.
- Accepted `SocketChannel`s are separate connections; for graceful shutdown, you can allow handlers to finish within a deadline or forcibly close them according to policy.
- Upon termination, clean up only the pathname belonging to the service itself. Do not delete another service's path just because it has the same name.
- Make sure exceptions are handled when closing and deleting files; if cleanup fails, log and alert operations rather than silencing it.

In Java, `Files.deleteIfExists(socketPath)` can throw `IOException` (permissions, file in use, or other OS issues). If you are certain the file belongs to you, **do not swallow exceptions** and pretend cleanup succeeded. `Files.deleteIfExists` does not automatically verify ownership or file type; that is the application's responsibility before calling it.

### 6.4. Handling symlinks and TOCTOU

`Files.exists(path)` followed by `Files.deleteIfExists(path)` are **two separate operations**, not an atomic transaction. If another process can replace the path between the two operations, the application may delete the wrong target. `LinkOption.NOFOLLOW_LINKS` helps inspect the node itself rather than following a symlink in a single query, **but does not eliminate the race by itself**.

Do not write "defensive" code like:

~~~java
// Dangerous on a path not under your control:
if (Files.exists(socketPath)) {
    Files.delete(socketPath);
}
listener.bind(UnixDomainSocketAddress.of(socketPath));
~~~

If the path is currently a live socket of another instance or the file is replaced, the code above causes disruption/insecurity. A more robust solution uses exclusive directory permissions, per-instance naming, socket/service ownership, lifecycle checks, and platform-appropriate lock/atomic coordination mechanisms when needed.

### 6.5. Deleting the file does not close the listener

On Unix-like OSes, unlinking a pathname while the socket is open **does not necessarily close already established connections immediately**. However, new clients will not be able to find the old endpoint to connect by name. Therefore, **deleting the path is not an API for tearing down connections or safely stopping a server**.

On Windows, there may be different constraints on deleting an open socket node. The portable approach at the Java layer: close the channels you own first, then delete the path in `finally` after the lifecycle has stopped.

## 7. Relationship with buffers and channels

A Unix-domain socket via `SocketChannel` is still **stream-oriented**. NIO buffer/channel fundamentals still apply:

- `SocketChannel.read(ByteBuffer)` returns the actual number of bytes read, **which may be fewer than the remaining space in the buffer**, and `-1` when the peer has ended its send side; do not assume one `read` = one message.
- `SocketChannel.write(ByteBuffer)` may also write **fewer** than `buffer.remaining()`. A `while (buffer.hasRemaining())` loop is usually needed in blocking code to send the full payload.
- When using a non-blocking channel, `read`/`write` can return `0` because it is not ready; non-blocking code must integrate with `Selector`/readiness, not busy-spin.
- `ByteBuffer.flip()` switches from writing into the buffer to reading from it; `clear()` or `compact()` prepares for subsequent receive cycles.
- **Framing** is required to know where a message ends: fixed-length, length prefix, delimiter, or a specific protocol. AF_UNIX does **not** turn a byte stream into datagram message boundaries.
- When the peer closes, EOF is a state of the **stream**, not a sign that every request was processed successfully.

Snippet illustrating two helper methods to send/receive exactly **4 ASCII bytes**:

~~~java
private static void writeText(SocketChannel ch, String text)
        throws IOException {
    ByteBuffer data = StandardCharsets.US_ASCII.encode(text);
    while (data.hasRemaining()) {
        ch.write(data);
    }
}

private static String readFour(SocketChannel ch) throws IOException {
    ByteBuffer data = ByteBuffer.allocate(4);
    while (data.hasRemaining()) {
        int n = ch.read(data);
        if (n == -1) {
            throw new EOFException("Expected 4 bytes");
        }
    }
    return new String(data.array(), StandardCharsets.US_ASCII);
}
~~~

These are **methods used inside the complete example class in section 9**, not a standalone program if copied by themselves. The code assumes the channel is in **blocking mode**; in non-blocking mode, `0`/readiness must be handled instead of just spinning in a loop without waiting.

### Do the accepted socket and listener share the same path?

The listener `ServerSocketChannel` is bound to the bound path. Each `accept()` returns a separate `SocketChannel` to communicate with that client. Accepted connections **do not each get a separate `service-1.sock`, `service-2.sock`, ... file**. The path is the name of the **listening endpoint**, not a per-request data file. A client does not bind its own name when using an implicit unnamed connection.

Therefore, during cleanup:

- Do **not** delete the socket path after *each request* finishes if the listener still needs to accept other clients.
- Do **not** call path deletion inside `try (SocketChannel accepted = ...)` of each handler.
- You **may** clean up the path after the **listener/server instance** lifecycle ends, when the server has truly stopped and the endpoint belongs to it.

## 8. API and lifecycle matrix

| Purpose | Java 17+ API | Behavior and notes |
| --- | --- | --- |
| Create UDS listener | `ServerSocketChannel.open(StandardProtocolFamily.UNIX)` | Does not bind immediately |
| Create endpoint name | `UnixDomainSocketAddress.of(Path)` | Path from default file system; path length depends on platform |
| Bind server | `server.bind(address)` | Creates socket node; requires valid path/permissions, unclaimed name |
| Auto-bind | `server.bind(null)` | Creates a temp name chosen by JDK; file still needs cleanup |
| Get bound server name | `(UnixDomainSocketAddress) server.getLocalAddress()` | Useful with bind(null) and when needing discovery/cleanup |
| Accept client | `SocketChannel ch = server.accept()` | Creates a new connected channel each time |
| Create UDS client | `SocketChannel.open(StandardProtocolFamily.UNIX)` | Not yet connected |
| Connect client | `client.connect(address)` | Client is usually implicitly unnamed, creates no separate pathname |
| Send/receive | `ch.write(ByteBuffer)` / `ch.read(ByteBuffer)` | Byte stream; handle partial I/O/framing manually |
| Close connected channel | `ch.close()` | Does not close the listener |
| Close listener | `server.close()` | Stops accepting, **does not unlink the socket file** |
| Check filesystem node | `Files.exists(path, NOFOLLOW_LINKS)` | Observation only, does not prove staleness or ownership |
| Clean up owned node | `Files.deleteIfExists(path)` | Only after closing, avoiding accidental deletion/races |
| Clean up temp directory | `Files.deleteIfExists(dir)` | Only a folder you created, must be empty |

## 9. Complete runnable Java 17+ program

This program fully demonstrates:

1. Using `Files.createTempDirectory("uds-")` to create a fresh private directory for the run, avoiding contention on a fixed socket path.
2. Creating `server.sock` in that folder; binding with `ServerSocketChannel.open(UNIX)`.
3. Creating a server worker that accepts a client via `accept()`, reads `PING`, and replies `PONG`.
4. The client connecting to the exact `UnixDomainSocketAddress` and checking the response content.
5. Closing the connected channels and listener with `try-with-resources`.
6. **Verifying the file still exists after the listener closes** using `Files.exists(..., NOFOLLOW_LINKS)`.
7. **Cleaning up the exact path** in `finally`, then deleting the newly created private directory.

Create the file **`UnixDomainPathDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class UnixDomainPathDemo {
    private static void writeText(SocketChannel channel, String text)
            throws IOException {
        ByteBuffer data = StandardCharsets.US_ASCII.encode(text);
        while (data.hasRemaining()) {
            channel.write(data);
        }
    }

    private static String readFour(SocketChannel channel) throws IOException {
        ByteBuffer data = ByteBuffer.allocate(4);
        while (data.hasRemaining()) {
            int n = channel.read(data);
            if (n == -1) {
                throw new EOFException("Expected 4 bytes");
            }
        }
        return new String(data.array(), StandardCharsets.US_ASCII);
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("uds-");
        Path path = directory.resolve("server.sock");
        ExecutorService workers = Executors.newSingleThreadExecutor();
        try {
            UnixDomainSocketAddress address = UnixDomainSocketAddress.of(path);
            try (ServerSocketChannel listener =
                    ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
                listener.bind(address);
                Future<String> server = workers.submit(() -> {
                    try (SocketChannel accepted = listener.accept()) {
                        String request = readFour(accepted);
                        writeText(accepted, "PONG");
                        return request;
                    }
                });
                try (SocketChannel client =
                        SocketChannel.open(StandardProtocolFamily.UNIX)) {
                    client.connect(address);
                    writeText(client, "PING");
                    System.out.println("Client received: " + readFour(client));
                }
                System.out.println("Server received: " +
                        server.get(5, TimeUnit.SECONDS));
            }
            System.out.println("Socket path remains after close: " +
                    Files.exists(path, LinkOption.NOFOLLOW_LINKS));
        } finally {
            workers.shutdownNow();
            Files.deleteIfExists(path);
            Files.deleteIfExists(directory);
        }
        System.out.println("Socket path deleted: " +
                !Files.exists(path, LinkOption.NOFOLLOW_LINKS));
    }
}
~~~

How to compile and run on JDK 17+ with an OS supporting pathname-based Unix-domain sockets:

~~~bash
javac -encoding UTF-8 UnixDomainPathDemo.java
java UnixDomainPathDemo
~~~

**Verified stdout with OpenJDK 24 on Windows with AF_UNIX:**

~~~text
Client received: PONG
Server received: PING
Socket path remains after close: true
Socket path deleted: true
~~~

How to read the output:

1. Client and server meet through a **filesystem path**, without using TCP/IP, DNS, or ports.
2. `writeText` and `readFour` use loops so they do not assume a single I/O call handles all four bytes.
3. The server worker reads `PING` and returns `PONG`; `Future.get(5, TimeUnit.SECONDS)` waits for the task to finish and propagates worker errors to main.
4. `try (SocketChannel accepted...)` closes the accepted connection, `try (SocketChannel client...)` closes the client, and `try (ServerSocketChannel listener...)` closes the listener.
5. After the **listener has closed**, `Files.exists(path, NOFOLLOW_LINKS)` still returns `true` because the socket node remains.
6. `Files.deleteIfExists(path)` cleans up the exact node in the directory **just created exclusively by the program**; then `Files.deleteIfExists(directory)` cleans up the empty folder. Thus the final line confirms `true`.

**Limitations and notes about the demo:**

- Although `Files.createTempDirectory` reduces name-collision risk, a secure deployment needs an ACL/mode policy **before binding**. Do not assume every OS's default temp directory meets the security requirements of a sensitive service.
- Some OS/JDK combinations do not support `StandardProtocolFamily.UNIX` or restrict socket creation; in that case you may encounter `UnsupportedOperationException` or I/O errors. Do not silently fall back to TCP without redesigning the permission model.
- If the temp path is too long for the OS's Unix-domain socket limit, bind may fail; configure a **short, reliable** runtime directory for that environment.
- `ExecutorService.shutdownNow()` in the demo only cleans up the task executor after `Future.get` has confirmed the happy path. In a long-running server, you must close the listener, coordinate worker completion/cancellation with timeouts, and manage accepted connections before deleting the path.
- `readFour` only reads exactly four bytes for demo purposes; a real protocol must define framing, data limits, and proper EOF/timeout handling. A Unix-domain byte stream does not frame messages automatically.
- If cleanup fails, `Files.deleteIfExists` throws an exception; this is a signal to handle, not to blindly overwrite or delete an entire directory tree out of scope.
- `Files.exists` returning `true` when the server closes is the documented Java behavior for pathname sockets; do not write production code that depends on automatic cleanup by default.

## 10. Variation: `bind(null)` still requires path cleanup

Some servers do not need a fixed path and want the OS/JDK to choose a unique name automatically:

~~~java
Path autoPath;
try (ServerSocketChannel server =
        ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
    server.bind(null);
    autoPath = ((UnixDomainSocketAddress) server.getLocalAddress()).getPath();
    System.out.println("Has named server address: " +
            !autoPath.toString().isEmpty());
    System.out.println("Socket file while open: " +
            Files.exists(autoPath, LinkOption.NOFOLLOW_LINKS));
}
try {
    System.out.println("Socket file after close: " +
            Files.exists(autoPath, LinkOption.NOFOLLOW_LINKS));
} finally {
    Files.deleteIfExists(autoPath);
}
~~~

**This is a code snippet** placed inside a `throws Exception` method, requiring imports `java.net.*`, `java.nio.channels.*`, `java.nio.file.*`. The path auto-bound by the server must be sent to the client via a reliable discovery mechanism. Do not scan the temp directory for the first file prefixed with `socket_`: that could be another process's file.

This snippet was tested on a UDS-capable JDK with three output lines:

~~~text
Has named server address: true
Socket file while open: true
Socket file after close: true
~~~

The third line proves that **an auto-named socket file still exists after close**. If you want to try it as a standalone program, wrap the snippet in a class with `public static void main(String[] args) throws Exception` and valid imports. Even when the server allocates the name automatically, the rule of cleaning up the file you own does not change.

## 11. Real-world symptoms and diagnostic steps

### 11.1. `Address already in use` or bind failure

Possibilities:

- The path already has a socket node owned by an **active** instance.
- A previous instance died and left behind a **stale socket file**.
- The path is a different file (regular file, symlink, directory) with the same name.
- Another process bound that name between two check steps.
- The path exceeds the OS limit or the filesystem does not support Unix-domain nodes.

How to handle:

1. Inspect the path, owner, type, and process/server status with OS tools within authorized scope.
2. Check the service manager/lock to see whether a real instance is running.
3. If the path is verified to be stale and owned by the same service, clean it up under the lifecycle manager's authority; **do not delete blindly**.
4. Prefer a private runtime directory and single-owner design to avoid split-brain.
5. Retry binding after the underlying issue is resolved.

**Do not put an unconditional `Files.deleteIfExists(socketPath)` in startup logic** before binding. That code can disrupt an existing running service.

### 11.2. `Access denied` / `Permission denied`

Check:

- Does the parent directory exist? Can the service user search/traverse it and create nodes?
- Does the socket file have the right owner/group/ACL? On Linux, a connecting client needs write permission on the socket node.
- Are there additional ACLs, SELinux/AppArmor, container policies, mount namespaces, or Windows ACLs?
- Does the process have permission in the temp directory chosen by the JDK? `bind(null)` still needs write access in the target directory.
- Does the path pass through a directory controlled by untrusted users or through a symlink?

Do not fix this by running `chmod 777` on the whole directory, especially for services with sensitive privileges. Identify the **principal that needs to connect** and grant least-privilege access to that principal, from the parent directory down to the socket.

### 11.3. `No such file or directory` / `Connection refused`

- `No such file or directory`: the pathname/server file may not exist, the mount namespace may be wrong, the path may have changed, or the parent directory may be missing.
- `Connection refused` or equivalent connection error: the file/socket node may exist, but there is no active listener, the server has closed, or it is not ready.
- Do not draw definitive conclusions from a single error message; wording and native error mapping to `IOException` differ across OSes.
- An existing path does not prove the server is alive. Inspect the service process and run a connect/health protocol within authorized permissions.

### 11.4. Commonly useful Linux tools

~~~bash
ls -ld /run/myapp
ls -l /run/myapp/service.sock
stat /run/myapp/service.sock
ss -xl
~~~

The commands above are Linux illustrations only and should be run on systems you own or are authorized to diagnose. `ls -l` typically shows type `s` for a socket node; it is not a file storing payloads. `ss -xl` helps observe some listening Unix-domain sockets; output depends on permissions, namespaces, and the OS. Do not treat figures from these command examples as actual output of the Java program.

## 12. Design mistakes to avoid

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| Using `new ServerSocket()` with `UnixDomainSocketAddress` | Legacy TCP/IP API is not how you select the `UNIX` family | `ServerSocketChannel.open(UNIX)` |
| Using `InetSocketAddress("localhost", port)` | That is TCP/IP, not pathname IPC | `UnixDomainSocketAddress.of(Path)` |
| Thinking `.sock` is a normal payload file | A socket file is a special node for connect/bind | Read/write via `SocketChannel` |
| Closing the channel and assuming the path disappears | The JDK does not automatically unlink bound pathnames | Separate cleanup after closing |
| Putting `Files.deleteIfExists(path)` inside each client's handler | New clients lose the listening server's name | Cleanup at the server/instance lifecycle |
| Immediately deleting an existing path when seen | It might be another running server's endpoint | Check owner/instance/liveness and coordinate shutdown |
| Placing a fixed socket in a world-writable directory | Prone to collisions, symlink/race attacks, unwanted access | Private directory + ownership + permissions |
| Only checking `Files.exists` and then deleting | Subject to time-of-check/time-of-use race | Protected directory, locking, and instance management |
| Treating socket permission modes as portable | POSIX does not guarantee identical behavior across all OSes | Private directory, ACLs, and peer auth when needed |
| Using `setPosixFilePermissions` on Windows | POSIX attribute view is not available | Configure appropriate Windows ACLs |
| Using Unicode / very long paths | Native sockaddr path is measured in bytes and has a limit | Short paths, test on target OS |
| Using a Path from a ZIP filesystem | Not a default filesystem Path | Use `Path.of(...)` or the default provider |
| Thinking `bind(null)` creates no file | Auto-bind server creates a temporary name and still leaves a node | Retrieve `getLocalAddress().getPath()` and clean up |
| Identifying clients by port or IP | Unix-domain sockets have no TCP endpoint | Use local user/peer policies and application protocols |
| Thinking Unix-domain sockets auto-close all accepted connections when the listener closes | Connection channels are independent | Manage handlers/accepted sockets separately |
| Reading once into a buffer and treating it as a complete message | Stream I/O can be partial | Proper framing and read/write loops |
| Unlinking while the listener is still running | New clients cannot find the endpoint; hard-to-debug races | Stop listener/handlers, then clean up |
| Recursively deleting a shared runtime directory | Can wipe out other data/sockets | Only delete the node and directory you created/own |
| Ignoring cleanup errors | Subsequent restarts easily fail to bind | Log/report errors; handle stale files safely |

## 13. Recommended test cases

| Scenario | Check |
| --- | --- |
| Bind to a new path in a private directory | Succeeds and creates socket node |
| Client connects to the exact path | Can exchange bytes via `SocketChannel` |
| Close client while listener stays open | Server can still accept another client |
| Close listener while an accepted channel exists | Accepted connection is not closed solely by the listener |
| Close listener and then inspect path | File still exists per Java contract |
| Cleanup after listener stops | Node is deleted, empty directory can be removed |
| Rebind same path **while stale file is undeleted** | May fail; do not auto-delete before verifying ownership |
| Rebind path after proper cleanup | Can succeed if OS and permissions allow |
| Path too long | Bind/connect throws contextual error; solution is a shorter path |
| Insufficient parent directory permissions | Server bind is rejected per OS policy |
| Unauthorized client attempts to connect | Rejected per actual OS/ACL policy |
| Symlink or other file at path | Does not overwrite/delete a file not owned by you |
| Two instances compete for the same name | Only one owner can bind; second instance does not unlink the first |
| Crash between bind and cleanup | Next startup detects stale file safely without deleting live socket |
| Containers with different mount namespaces | Do not rely on identical names to assume the same endpoint |
| Error in handler and cleanup | Accepted channel, listener, and file are handled by ownership; exceptions are reported |

You do not need to write all tests in a single `main()`; permission, race, and crash cases require a controlled test environment, sometimes running multiple processes/OS accounts. The demo in section 9 mainly proves the fundamental behavior **channel close != pathname delete**.

## 14. Practice exercises and answers

### Exercise 1 — Why did restart fail?

A server uses `/run/myapp/service.sock`. The previous run exited `try (ServerSocketChannel server = ...)`, yet the next `bind` reports the name is already in use. Why?

**Answer:** A bound Unix-domain socket creates a socket node; `close()` closes the channel but **does not automatically unlink** the pathname. The remaining stale file prevents rebinding the same name. After verifying the old instance is not running and you own the path, clean up the node via a safe procedure rather than deleting blindly.

### Exercise 2 — Role of chmod 0700

Why is a `/run/myapp` directory with mode `0700` owned by the service itself more useful than putting the socket in `/tmp/service.sock` and only running chmod on the socket file?

**Answer:** A private directory prevents unauthorized users from **traversing or replacing the name** of the endpoint; on Linux a client needs to traverse the directory and have appropriate permissions. Socket-node mode also depends on the OS and can be altered in a race after binding. When another user group needs to connect, use properly designed permissions/ACLs rather than opening the entire directory.

### Exercise 3 — Automatic binding

Does `ServerSocketChannel.open(UNIX).bind(null)` automatically release the file after `close()`? How do you know the path to clean up?

**Answer:** No. Retrieve `(UnixDomainSocketAddress) server.getLocalAddress()` and call `getPath()` after binding, track that path under the instance's ownership, and clean it up once the server has stopped.

### Exercise 4 — Does the client have its own file?

A client creates `SocketChannel.open(UNIX)` and calls `connect(address)` without binding a local address. Does `client.sock` need to be deleted?

**Answer:** No separate pathname socket file is created for such an **implicitly bound** client; its local endpoint is considered unnamed. Only clean up paths that the program actually owns/created.

### Exercise 5 — Deleting the path prematurely

Instance A is listening at `/tmp/app.sock`. Instance B sees the path exists and calls `Files.deleteIfExists("/tmp/app.sock")` before binding. What is the danger?

**Answer:** B can unlink A's active endpoint name, preventing new clients from connecting via the old name and causing split-brain while old connections may still remain. You must have owner/instance coordination, a private directory, and safe verification before handling a stale path.

### Exercise 6 — Partial read/write

A server calls `SocketChannel.read(buffer)` once and assumes it has received a full 200-byte request. Why can this be wrong?

**Answer:** A Unix-domain stream socket **has no message boundaries**. A single read may return only part of the bytes; you must define framing, loop until all bytes are received, and handle EOF/timeouts.

### Exercise 7 — Operating system differences

A group of developers sees that Linux allows `chmod 600 service.sock` and concludes that Windows, macOS, and BSD all apply the same permission checks on socket nodes. Is that conclusion right?

**Answer:** No. POSIX does not mandate identical semantics for pathname socket permissions across every OS; Windows uses ACLs and its own policies. You must test on the target OS; start with a private directory, proper ownership, and application authorization when needed.

### Exercise 8 — Path length limit

A 160-byte path can still create a text file on the filesystem. Is it guaranteed to bind as a `UnixDomainSocketAddress`?

**Answer:** No. Unix-domain sockaddr paths have their own native limit (JDK describes it as typically ~100 bytes). Choose a shorter path and do not assume that a valid filesystem path is automatically valid as a socket address.

## 15. Pre-deployment checklist

- [ ] Use `StandardProtocolFamily.UNIX` and `UnixDomainSocketAddress`, not confusing them with TCP loopback.
- [ ] The path is a **short, absolute path** on the default filesystem, with an existing parent directory.
- [ ] There is an **owner** rule: the server/service manager is responsible for the path, listener, and accepted channels.
- [ ] The parent directory has appropriate permissions; on Linux distinguish directory execute/search and socket write; on Windows verify ACLs.
- [ ] Do not place sensitive sockets in a shared directory vulnerable to renaming/symlinks without protection.
- [ ] Have a mechanism to prevent two server instances from claiming the same endpoint name.
- [ ] Do not treat `Files.exists(path)` as proof that an endpoint is stale or that a client/server is alive.
- [ ] Do not delete an existing file before startup without verifying ownership and the previous instance's state.
- [ ] `try-with-resources` closes channels; a separate `finally` cleans up the pathname **after** stopping the listener/handlers.
- [ ] With `bind(null)`, save the path returned by `getLocalAddress()` and clean it up upon exit.
- [ ] Do not forget to clean up accepted sockets/workers/executors during graceful shutdown.
- [ ] Implement framing and handle partial read/write, EOF, oversized data, timeouts, and auth as needed.
- [ ] Deploy and test on the specific OS/JDK, including path length, permissions, and crash/restart.
- [ ] If cleanup fails, log operational errors; never recursively delete directories you do not own.

## 16. Official references for verification

- [Java SE 17 — UnixDomainSocketAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/UnixDomainSocketAddress.html): `of(Path)`, `getPath()`, paths from the default file system, unnamed addresses.
- [Java SE 17 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): `open(UNIX)`, `bind`, `accept`, and **the rule that the socket file remains after close**.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): client `connect`, stream I/O, implicit unnamed bind, channel lifecycle.
- [Java SE 17 — NIO channel package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/package-summary.html): protocol families and Unix-domain stream socket support.
- [Java SE 17 — Networking Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html): `jdk.net.unixdomain.tmpdir` and socket paths allocated by `bind(null)`.
- [Inside Java — JEP 380 Unix-domain socket channels](https://inside.java/2021/02/03/jep380-unix-domain-sockets-channels/): API design, differences between TCP vs local pathnames, security, and cleanup.
- [Linux man-pages — unix(7)](https://man7.org/linux/man-pages/man7/unix.7.html): pathname sockets, `sun_path` length, parent directory/socket node permissions, and portability differences.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `createTempDirectory`, `exists`, `deleteIfExists`, `LinkOption.NOFOLLOW_LINKS`, and filesystem operations.
- [Java SE 17 — PosixFilePermissions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html): creating/interpreting POSIX permissions, not a portable ACL API.

**Core takeaway:** A Unix-domain socket uses a **pathname as its IPC address**, but the pathname is **not the channel's lifecycle**. Place the path in a controlled directory, grant proper permissions to authorized processes, close the listener and accepted channels in their proper scopes, and **delete the socket node only after the instance owning the endpoint has stopped**. That is the key to avoiding restart failures, leaked socket files, and accidentally deleting a running endpoint.
