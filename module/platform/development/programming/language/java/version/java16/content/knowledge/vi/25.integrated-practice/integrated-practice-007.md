# Xây dịch vụ IPC cục bộ truyền thông điệp qua Unix-domain socket

**Module:** JAVA_VERSION_JAVA16  
**Chương:** Thực hành tổng hợp  
**Áp dụng:** Java 16 trở lên. Unix-domain socket channels được chuẩn hóa trong Java 16 qua JEP 380; API này tiếp tục dùng được trong các JDK hiện đại.

Trong bài thực hành này, bạn sẽ xây một dịch vụ IPC (inter-process communication) cục bộ bằng Java. Một tiến trình server lắng nghe trên Unix-domain socket; một tiến trình client kết nối, gửi thông điệp và nhận phản hồi. Hai tiến trình chạy độc lập nhưng trao đổi dữ liệu qua một socket file trên cùng máy.

Bài tập kết hợp các API NIO được bổ sung trong Java 16:

- `UnixDomainSocketAddress` biểu diễn địa chỉ Unix-domain socket từ một `Path`.
- `StandardProtocolFamily.UNIX` chọn họ giao thức Unix-domain.
- `ServerSocketChannel` lắng nghe kết nối cục bộ.
- `SocketChannel` chấp nhận kết nối và truyền dữ liệu hai chiều.

Các API này là tính năng chuẩn, không cần bật preview hoặc dùng thư viện bên ngoài. Hãy chạy trên hệ điều hành và JDK có hỗ trợ Unix-domain sockets; nếu provider không hỗ trợ, thao tác mở channel có thể ném `UnsupportedOperationException`.

## 1. Kiến trúc bài thực hành

Ta xây một server nhỏ cung cấp ba lệnh:

| Request | Response |
| --- | --- |
| `PING` | `PONG` |
| `ECHO hello Java` | `hello Java` |
| `UPPER hello Java` | `HELLO JAVA` |

Mỗi client mở một kết nối, gửi một request, đọc một response rồi đóng kết nối. Server chấp nhận nhiều client và xử lý bằng một worker pool có hàng đợi giới hạn.

Luồng xử lý:

```text
Process A: LocalIpcClient                 Process B: LocalIpcServer
        |                                          |
        | SocketChannel.open(UNIX)                 |
        |----------------------------------------->|
        | connect(socketPath)                     | ServerSocketChannel
        |                                          | bind(socketPath)
        |  4-byte length + UTF-8 request           |
        |=========================================>|
        |                                          | read frame
        |                                          | dispatch command
        |  4-byte length + UTF-8 response          |
        |<=========================================|
        | decode response                          |
        | close                                    | close client channel
```

Unix-domain socket là kênh IPC trên cùng máy. Nó không phải TCP socket lắng nghe trên địa chỉ IP và không cần chọn port. Hai tiến trình phải dùng cùng đường dẫn socket.

## 2. Chọn giao thức truyền thông điệp

Socket là luồng byte. Một lần gọi `write()` ở client không đảm bảo tương ứng với một lần gọi `read()` ở server. Một frame có thể được đọc thành nhiều phần; nhiều lần ghi cũng có thể được nhận trong một lần đọc.

Vì vậy, bài tập dùng giao thức **length-prefixed**:

```text
+----------------------+------------------------------+
| 4 bytes              | N bytes                      |
+----------------------+------------------------------+
| Payload length       | UTF-8 payload                 |
| signed int, big-endian| N <= 64 KiB                   |
+----------------------+------------------------------+
```

Quy ước:

1. Header là số nguyên 32-bit big-endian biểu diễn số byte của payload.
2. Payload là chuỗi UTF-8.
3. Payload không vượt quá 64 KiB.
4. Mỗi kết nối trong lab truyền đúng một request và một response.
5. Client đóng kết nối sau khi nhận response.

Độ dài phải tính theo byte UTF-8, không phải số ký tự Java. Ví dụ, một ký tự tiếng Việt có dấu có thể chiếm nhiều byte.

Length prefix giúp payload có thể chứa dấu cách hoặc ký tự xuống dòng mà không làm mất ranh giới thông điệp. Giới hạn frame ngăn client gửi một length quá lớn khiến server cấp phát bộ nhớ ngoài dự kiến.

## 3. Tạo lớp FrameProtocol

Lớp này đóng gói việc đọc và ghi một frame. Nó xử lý partial read/write bằng vòng lặp cho đến khi buffer được lấp đầy hoặc gửi hết.

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SocketChannel;

final class FrameProtocol {
    static final int MAX_FRAME_BYTES = 64 * 1024;

    private FrameProtocol() {}

    static byte[] readFrame(SocketChannel channel) throws IOException {
        ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);

        int firstRead = channel.read(header);
        if (firstRead == -1) {
            return null; // Peer đóng kết nối trước khi gửi frame.
        }

        readFully(channel, header, "header");
        header.flip();

        int length = header.getInt();
        if (length < 0 || length > MAX_FRAME_BYTES) {
            throw new IOException("Frame length không hợp lệ: " + length);
        }

        ByteBuffer payload = ByteBuffer.allocate(length);
        readFully(channel, payload, "payload");
        return payload.array();
    }

    static void writeFrame(SocketChannel channel, byte[] payload)
            throws IOException {
        if (payload.length > MAX_FRAME_BYTES) {
            throw new IOException("Payload vượt giới hạn 64 KiB");
        }

        ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);
        header.putInt(payload.length);
        header.flip();

        writeFully(channel, header);
        writeFully(channel, ByteBuffer.wrap(payload));
    }

    private static void readFully(
            SocketChannel channel,
            ByteBuffer buffer,
            String part
    ) throws IOException {
        while (buffer.hasRemaining()) {
            int count = channel.read(buffer);
            if (count == -1) {
                throw new EOFException("Peer đóng giữa frame " + part);
            }
        }
    }

    private static void writeFully(
            SocketChannel channel,
            ByteBuffer buffer
    ) throws IOException {
        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }
}
```

Các channel được mở ở chế độ blocking mặc định. Vòng lặp vẫn cần thiết vì `SocketChannel.write()` có thể ghi ít byte hơn số byte còn lại trong buffer; protocol không được giả định một lần ghi luôn gửi hết dữ liệu.

`readFrame()` trả về `null` nếu peer đóng kết nối trước khi có byte header nào. Nếu peer đóng sau khi đã bắt đầu header hoặc payload, phương thức ném `EOFException` vì frame chưa hoàn chỉnh.

## 4. Xây server bằng ServerSocketChannel

Server bind vào một đường dẫn socket, nhận client và chuyển từng kết nối cho worker pool. Hàng đợi có giới hạn để số kết nối chờ xử lý không tăng vô hạn.

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.AsynchronousCloseException;
import java.nio.channels.Channel;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class LocalIpcServer {
    private LocalIpcServer() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                "Usage: java LocalIpcServer <socket-path>"
            );
            return;
        }

        Path socketPath = Path.of(args[0]).toAbsolutePath().normalize();
        Path parent = socketPath.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        // Không xóa một socket có thể đang được server khác sử dụng.
        if (Files.exists(socketPath, LinkOption.NOFOLLOW_LINKS)) {
            throw new FileAlreadyExistsException(
                "Socket path đã tồn tại: " + socketPath
            );
        }

        Set<SocketChannel> activeClients =
            ConcurrentHashMap.newKeySet();

        try (ServerSocketChannel server =
                ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
            server.bind(UnixDomainSocketAddress.of(socketPath));

            try {
                try {
                    Files.setPosixFilePermissions(
                        socketPath,
                        PosixFilePermissions.fromString("rw-------")
                    );
                } catch (UnsupportedOperationException ignored) {
                    // File system không cung cấp POSIX permissions.
                    // Khi đó cần dùng ACL/quyền của hệ điều hành.
                }

                Thread shutdownHook = new Thread(() -> {
                    closeQuietly(server);
                    for (SocketChannel client : activeClients) {
                        closeQuietly(client);
                    }
                    try {
                        Files.deleteIfExists(socketPath);
                    } catch (IOException ignored) {
                        // Main thread cũng thử xóa socket khi kết thúc.
                    }
                }, "local-ipc-shutdown");
                Runtime.getRuntime().addShutdownHook(shutdownHook);

                ThreadPoolExecutor workers = new ThreadPoolExecutor(
                    4,
                    4,
                    0L,
                    TimeUnit.MILLISECONDS,
                    new ArrayBlockingQueue<>(32),
                    new ThreadPoolExecutor.AbortPolicy()
                );

                try {
                    System.out.println("IPC server listening at " + socketPath);

                    while (true) {
                        SocketChannel client = server.accept();
                        activeClients.add(client);

                        try {
                            workers.execute(() -> {
                                try {
                                    serve(client);
                                } finally {
                                    activeClients.remove(client);
                                }
                            });
                        } catch (RejectedExecutionException overloaded) {
                            activeClients.remove(client);
                            closeQuietly(client);
                            System.err.println(
                                "Server quá tải; đã từ chối một kết nối."
                            );
                        }
                    }
                } catch (AsynchronousCloseException stopping) {
                    // Shutdown hook đóng server channel để thoát accept().
                    System.out.println("IPC server đang dừng.");
                } finally {
                    for (SocketChannel client : activeClients) {
                        closeQuietly(client);
                    }

                    workers.shutdown();
                    try {
                        if (!workers.awaitTermination(5, TimeUnit.SECONDS)) {
                            workers.shutdownNow();
                        }
                    } catch (InterruptedException interrupted) {
                        workers.shutdownNow();
                        Thread.currentThread().interrupt();
                    }
                }
            } finally {
                Files.deleteIfExists(socketPath);
            }
        }
    }

    private static void serve(SocketChannel client) {
        try (client) {
            byte[] requestBytes = FrameProtocol.readFrame(client);
            if (requestBytes == null) {
                return;
            }

            String request = new String(
                requestBytes,
                StandardCharsets.UTF_8
            );
            String response = dispatch(request);

            FrameProtocol.writeFrame(
                client,
                response.getBytes(StandardCharsets.UTF_8)
            );
        } catch (IOException failure) {
            System.err.println("IPC client error: " + failure.getMessage());
        }
    }

    private static String dispatch(String request) {
        if ("PING".equals(request)) {
            return "PONG";
        }
        if (request.startsWith("ECHO ")) {
            return request.substring("ECHO ".length());
        }
        if (request.startsWith("UPPER ")) {
            return request.substring("UPPER ".length())
                .toUpperCase(Locale.ROOT);
        }
        return "ERROR unsupported command";
    }

    private static void closeQuietly(Channel channel) {
        try {
            channel.close();
        } catch (IOException ignored) {
            // Đang dọn dẹp khi server dừng.
        }
    }
}
```

Một số điểm đáng chú ý:

- `ServerSocketChannel.open(StandardProtocolFamily.UNIX)` tạo server channel cho Unix-domain socket.
- `bind(UnixDomainSocketAddress.of(socketPath))` gắn server với đường dẫn socket.
- `accept()` chờ kết nối mới và trả về một `SocketChannel`.
- Worker pool xử lý nhiều client mà không để một client chiếm vòng lặp accept.
- Hàng đợi có giới hạn 32 kết nối đang chờ; khi đầy, server đóng kết nối mới thay vì giữ một lượng công việc không giới hạn.
- Server không xóa path có sẵn lúc khởi động vì path đó có thể thuộc một server còn hoạt động.

Server xử lý một frame cho mỗi kết nối trong bài lab. Một dịch vụ production có thể giữ kết nối lâu hơn và lặp đọc nhiều frame, nhưng khi đó cần thiết kế thêm giới hạn số frame, thời gian chờ, backpressure và lifecycle của connection.

## 5. Xây client bằng SocketChannel

Client mở channel cùng protocol family, kết nối tới đúng socket path, gửi frame rồi đọc phản hồi:

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Arrays;

public final class LocalIpcClient {
    private LocalIpcClient() {}

    public static void main(String[] args) throws IOException {
        if (args.length < 2) {
            System.err.println(
                "Usage: java LocalIpcClient <socket-path> <command...>"
            );
            return;
        }

        Path socketPath = Path.of(args[0]).toAbsolutePath().normalize();
        String request = String.join(
            " ",
            Arrays.copyOfRange(args, 1, args.length)
        );

        try (SocketChannel channel =
                SocketChannel.open(StandardProtocolFamily.UNIX)) {
            channel.connect(UnixDomainSocketAddress.of(socketPath));

            FrameProtocol.writeFrame(
                channel,
                request.getBytes(StandardCharsets.UTF_8)
            );

            byte[] response = FrameProtocol.readFrame(channel);
            if (response == null) {
                throw new EOFException(
                    "Server đóng kết nối trước khi gửi response"
                );
            }

            System.out.println(
                new String(response, StandardCharsets.UTF_8)
            );
        }
    }
}
```

Client dùng try-with-resources để luôn đóng channel khi gửi thành công hoặc gặp lỗi. Đường dẫn client truyền vào phải trùng với path mà server bind.

## 6. Biên dịch và chạy hai tiến trình

Đặt ba file Java trong cùng thư mục:

```text
ipc-lab/
  FrameProtocol.java
  LocalIpcServer.java
  LocalIpcClient.java
```

Biên dịch bằng JDK 16 hoặc mới hơn:

```sh
javac --release 16 FrameProtocol.java LocalIpcServer.java LocalIpcClient.java
```

Mở terminal thứ nhất và chạy server:

```sh
java LocalIpcServer /tmp/acme-ipc.sock
```

Server hiển thị đường dẫn đang lắng nghe. Mở terminal thứ hai và gửi request:

```sh
java LocalIpcClient /tmp/acme-ipc.sock PING
java LocalIpcClient /tmp/acme-ipc.sock ECHO xin chao Java
java LocalIpcClient /tmp/acme-ipc.sock UPPER java 16
```

Kết quả mong đợi:

```text
PONG
xin chao Java
JAVA 16
```

Dừng server bằng Ctrl+C. Server đóng các client đang hoạt động và xóa socket path do chính nó tạo.

Các lệnh trên dùng đường dẫn kiểu POSIX. Trên hệ điều hành khác, chọn một path hợp lệ trên file system của máy đó và xác minh JDK/provider hỗ trợ Unix-domain socket channels.

## 7. Thử payload có dấu cách, Unicode và giới hạn frame

Thử gửi tiếng Việt:

```sh
java LocalIpcClient /tmp/acme-ipc.sock ECHO Xin chào từ Java 16
```

UTF-8 giúp client và server trao đổi văn bản có dấu. Length prefix tính theo số byte UTF-8 nên không bị sai khi payload chứa ký tự nhiều byte.

Thử gửi payload vượt quá 64 KiB bằng cách điều chỉnh client hoặc tạo một test harness. Server phải từ chối frame có length âm hoặc lớn hơn `MAX_FRAME_BYTES` trước khi cấp phát payload buffer.

Trong production, giới hạn frame cần được chọn theo nhu cầu nghiệp vụ và memory budget. Không nhận một length tùy ý từ peer rồi gọi `ByteBuffer.allocate(length)` mà không kiểm tra.

## 8. Vì sao phải xử lý partial read và partial write?

Socket channel truyền byte stream. Ranh giới của lần gọi API không phải ranh giới message:

```text
Client ghi:
  [HEADER + PAYLOAD] -------------------->

Server có thể đọc:
  lần 1: [2 byte đầu header]
  lần 2: [2 byte còn lại + một phần payload]
  lần 3: [phần payload còn lại]
```

Nếu code chỉ gọi `channel.read(buffer)` một lần rồi giả định buffer đã đầy, có thể giải mã length sai hoặc xử lý payload bị thiếu.

Hai helper trong `FrameProtocol` giải quyết điều đó:

- `readFully()` lặp cho đến khi buffer đầy; EOF giữa frame là lỗi protocol.
- `writeFully()` lặp cho đến khi buffer được gửi hết.

Các helper trên phù hợp với channel blocking trong bài lab. Nếu chuyển sang non-blocking mode, một thao tác có thể trả về 0 khi chưa có tiến triển; khi đó phải dùng selector và state machine để tiếp tục thao tác sau, không spin-loop chờ dữ liệu.

## 9. Quản lý socket path và quyền truy cập

Unix-domain socket dùng một path trong file system để hai tiến trình tìm thấy endpoint. Path này là tài nguyên cần quản lý:

- Tạo socket trong thư mục riêng của user/service.
- Giới hạn quyền truy cập thư mục cha; trên POSIX có thể dùng mode `rwx------`.
- Server đặt quyền socket thành `rw-------` khi file system hỗ trợ POSIX permissions.
- Khi dừng bình thường, xóa socket path do server tạo.
- Nếu server bị kill đột ngột và để lại path, kiểm tra process trước khi xóa file socket cũ.
- Giữ path ngắn vì giới hạn độ dài Unix socket path phụ thuộc hệ điều hành.

Ví dụ chuẩn bị thư mục riêng trên Linux/macOS:

```sh
mkdir -p "$HOME/.acme-ipc"
chmod 700 "$HOME/.acme-ipc"
java LocalIpcServer "$HOME/.acme-ipc/service.sock"
```

Chạy client với đúng path:

```sh
java LocalIpcClient "$HOME/.acme-ipc/service.sock" PING
```

Quyền file và directory là một phần của kiểm soát truy cập trên hệ điều hành hỗ trợ POSIX. Trên nền tảng dùng ACL hoặc cơ chế khác, cấu hình quyền tương ứng của OS; không giả định `setPosixFilePermissions()` hoạt động trên mọi provider.

Unix-domain socket giới hạn giao tiếp ở máy cục bộ nhưng không tự xác thực danh tính nghiệp vụ của client. Hãy giới hạn quyền path, xác thực/ủy quyền nếu cần và kiểm tra mọi message như dữ liệu đầu vào không tin cậy.

## 10. Vòng đời và xử lý lỗi

Một dịch vụ IPC cần có quy tắc rõ ràng khi kết nối thất bại:

| Tình huống | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `UnsupportedOperationException` khi mở channel | JDK/provider hoặc OS không hỗ trợ Unix-domain socket | Xác minh nền tảng và provider; không tự chuyển sang API preview |
| `ConnectException` hoặc lỗi connect | Server chưa chạy, path sai hoặc socket không còn listener | Kiểm tra server và dùng cùng socket path |
| `FileAlreadyExistsException` lúc server bind | Path đã tồn tại, có thể là server khác hoặc socket stale | Xác minh process đang giữ socket trước khi dọn path |
| `AccessDeniedException` | Quyền thư mục hoặc socket không cho phép truy cập | Kiểm tra owner, permissions và ACL |
| `EOFException` giữa frame | Peer đóng kết nối trước khi gửi đủ header/payload | Xem đây là request không hoàn chỉnh và đóng connection |
| Frame length không hợp lệ | Client gửi dữ liệu sai protocol hoặc cố tình gây áp lực bộ nhớ | Từ chối frame và đóng connection |
| Server từ chối kết nối khi tải cao | Worker pool và queue đã đầy | Điều chỉnh capacity dựa trên tải và memory budget; áp dụng backpressure |

Server không nên để một request lỗi làm sập accept loop. Ví dụ đã giới hạn lỗi đọc/ghi ở worker của từng client; accept loop chỉ dừng khi server channel đóng hoặc gặp lỗi server-level.

## 11. Kiểm tra nhiều client đồng thời

Mở nhiều terminal client và gửi lệnh cùng lúc. Server nhận từng connection rồi giao cho worker pool. Bài lab dùng bốn worker và queue 32 phần tử để giới hạn công việc chờ.

Đây là cấu hình minh họa. Khi thiết kế thật:

- Chọn số worker theo CPU, latency và thời gian xử lý request.
- Giới hạn số connection đang hoạt động và số request chờ.
- Không giữ connection nhàn rỗi vô thời hạn.
- Có timeout/lifecycle policy ở tầng ứng dụng nếu client không gửi đủ frame.
- Theo dõi số kết nối bị từ chối và thời gian xử lý.

Unix-domain socket không làm mất nhu cầu backpressure. Một client cục bộ vẫn có thể gửi dữ liệu chậm, mở nhiều kết nối hoặc gửi frame không hợp lệ.

## 12. Phân biệt Unix-domain socket với TCP socket

| Tiêu chí | Unix-domain socket | TCP socket |
| --- | --- | --- |
| Phạm vi | IPC trên cùng máy | Giao tiếp qua IP, local hoặc network |
| Địa chỉ | File-system path (`UnixDomainSocketAddress`) | IP address và port |
| Protocol family | `StandardProtocolFamily.UNIX` | `StandardProtocolFamily.INET` hoặc `INET6` |
| Thiết lập endpoint server | `ServerSocketChannel.open(UNIX)` và bind path | `ServerSocketChannel.open()` và bind IP/port |
| Kiểm soát truy cập | Quyền path/directory và cơ chế OS | Firewall, network policy và xác thực ứng dụng |
| Dùng khi | Service local, agent, database local, daemon | Client/server qua mạng hoặc cần tương tác host khác |

Unix-domain socket có thể tránh một số chi phí của đường truyền IP và cung cấp quyền truy cập theo file system trên nền tảng phù hợp. Tuy nhiên, không nên khẳng định nó luôn nhanh hơn TCP trong mọi workload; hãy benchmark trên hệ thống mục tiêu.

## 13. Mở rộng giao thức cho ứng dụng thực tế

Sau khi lab hoạt động, có thể mở rộng giao thức theo nhu cầu:

1. Thêm version field để client và server phát hiện khác phiên bản protocol.
2. Thêm request ID để ghép response với request khi một connection truyền nhiều message.
3. Thêm status code và error payload có cấu trúc.
4. Thêm giới hạn số frame và tổng byte cho mỗi connection.
5. Thêm timeout và chính sách đóng client gửi chậm.
6. Thêm xác thực/ủy quyền theo mô hình threat của máy cục bộ.
7. Dùng structured payload như JSON/CBOR/Protocol Buffers nếu cần schema; giữ length prefix bên ngoài để phân định frame.
8. Có thể chuyển sang non-blocking channel và `Selector` nếu số lượng kết nối đồng thời lớn, nhưng cần state machine cho từng connection.

Giữ framing độc lập với định dạng payload. Khi thay UTF-8 text bằng JSON hoặc binary payload, server vẫn đọc length prefix trước rồi mới giải mã nội dung.

## 14. Câu hỏi tự kiểm tra

1. Vì sao `UnixDomainSocketAddress` nhận `Path` thay vì host và port?
2. `StandardProtocolFamily.UNIX` được dùng khi mở channel nào ở phía server và client?
3. Vì sao một lần `SocketChannel.read()` không đảm bảo đã nhận toàn bộ frame?
4. Tại sao length prefix cần giới hạn tối đa trước khi cấp phát buffer?
5. Vì sao độ dài payload UTF-8 phải tính theo byte thay vì số ký tự?
6. `URL` hoặc TCP port có cần thiết cho Unix-domain socket không?
7. Khi nào server nên xóa socket path và vì sao không xóa path tùy tiện lúc startup?
8. Queue giới hạn của worker pool giúp bảo vệ tài nguyên như thế nào?
9. Vì sao quyền thư mục cha quan trọng đối với socket file?
10. Khi nào nên dùng Unix-domain socket thay vì TCP?

## 15. Checklist hoàn thành lab

- [ ] Biên dịch ba file bằng JDK 16 hoặc mới hơn.
- [ ] Server bind được vào một Unix-domain socket path.
- [ ] Client kết nối bằng `SocketChannel` với protocol family `UNIX`.
- [ ] Client gửi request có length prefix và UTF-8 payload.
- [ ] Server đọc đủ header và payload, kể cả khi dữ liệu đến theo nhiều phần.
- [ ] Server từ chối length âm hoặc vượt 64 KiB.
- [ ] `PING`, `ECHO` và `UPPER` trả đúng response.
- [ ] Nhiều client có thể kết nối đồng thời.
- [ ] Queue đầy không làm accept loop sập.
- [ ] Server đóng client channel và xóa socket path khi shutdown.
- [ ] Thư mục socket có quyền phù hợp với user/service.
- [ ] Đã thử trường hợp path sai, server chưa chạy và quyền truy cập bị từ chối.

**Ghi nhớ:** Java 16 cung cấp Unix-domain socket channels chuẩn qua JEP 380. Dùng `ServerSocketChannel` để bind và accept, `SocketChannel` để trao đổi byte, `UnixDomainSocketAddress` để định vị endpoint. Vì socket là byte stream, hãy tự định nghĩa framing, xử lý partial read/write và giới hạn payload. Quản lý socket path, quyền truy cập, worker queue và shutdown lifecycle như các tài nguyên thực sự của dịch vụ.

## Tài liệu chính thức

- [JEP 380 — Unix-Domain Socket Channels](https://openjdk.org/jeps/380).
- [Java SE 26 API — `UnixDomainSocketAddress`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/UnixDomainSocketAddress.html).
- [Java SE 26 API — `StandardProtocolFamily`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardProtocolFamily.html).
- [Java SE 26 API — `SocketChannel`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html).
- [Java SE 26 API — `ServerSocketChannel`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html).
