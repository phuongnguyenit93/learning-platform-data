# Kiểm thử khởi động lại, client song song và peer bị dừng đột ngột

Unix-domain socket là kênh giao tiếp giữa các tiến trình trên cùng máy. Khi vận hành dịch vụ thật, các ca lỗi quan trọng thường không xuất hiện trong một lần request đơn giản: server có thể phải khởi động lại trên cùng pathname, nhiều client có thể kết nối cùng lúc, hoặc một peer có thể bị kết thúc mà không gửi thông điệp đóng ứng dụng.

Các bài kiểm thử cho những tình huống này cần xác nhận cả dữ liệu giao thức lẫn vòng đời socket. Hãy kiểm tra rằng server có thể bind lại pathname sau khi cleanup, request của các client không trộn lẫn, và phía còn sống nhận biết peer đã đóng kết nối. Bài học sử dụng API Unix-domain socket được chuẩn hóa từ Java 16 và các công cụ kiểm thử vẫn phù hợp trên JDK hiện đại.

## 1. Những hành vi cần kiểm thử

| Kịch bản | Điều cần xác nhận | Lỗi thường gặp |
|---|---|---|
| Server khởi động lại | Server mới bind được cùng pathname sau khi instance cũ đóng và xóa socket file | Chỉ đóng channel nhưng quên xóa pathname |
| Client đang kết nối khi server dừng | Client cũ nhận biết kết nối đã kết thúc; server mới phục vụ kết nối mới | Tái sử dụng channel cũ hoặc giữ connection state từ instance trước |
| Nhiều client đồng thời | Mỗi client nhận đúng response tương ứng với request của mình | Chia sẻ ByteBuffer, ghi lẫn dữ liệu hoặc xử lý client tuần tự ngoài ý muốn |
| Peer đóng kết nối | Server nhận EOF hoặc lỗi I/O phù hợp và giải phóng client channel | Vòng lặp đọc vô hạn, không xóa SelectionKey hoặc không đóng channel |
| Peer process bị kill | Tiến trình còn sống phát hiện peer đã biến mất dù không có thông điệp ứng dụng báo trước | Chờ một thông điệp shutdown không bao giờ đến |
| Server crash | Socket pathname cũ được xử lý theo chính sách recovery có kiểm soát | Xóa pathname đang được server khác sở hữu |

Nên tách test đơn vị cho parser/giao thức khỏi test tích hợp mở socket thật. Test tích hợp xác nhận hành vi của operating system, channel và selector; test đơn vị xác nhận cách ứng dụng xử lý frame thiếu, dữ liệu sai hoặc trạng thái kết nối.

## 2. Chuẩn bị môi trường kiểm thử

Unix-domain socket channel được thêm vào Java 16. Test cần chạy bằng JDK 16 trở lên và trên hệ điều hành/JDK provider hỗ trợ protocol family UNIX. Nếu môi trường không hỗ trợ, hãy đánh dấu test tích hợp là skipped bằng assumption của JUnit thay vì giả lập thành công.

Ví dụ kiểm tra khả năng mở channel:

~~~java
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

final class UnixSocketTestSupport {
    static void requireUnixDomainSocketSupport() {
        try (ServerSocketChannel ignored =
                     ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
            // Provider hỗ trợ mở Unix-domain server channel.
        } catch (UnsupportedOperationException | IOException e) {
            assumeTrue(false,
                    "Unix-domain socket channels are not available: " + e);
        }
    }
}
~~~

Một số hệ điều hành giới hạn độ dài pathname của Unix-domain socket. Giới hạn phụ thuộc nền tảng và thường xấp xỉ 100 byte. Khi dùng JUnit TempDir, hãy giữ tên file và thư mục con ngắn; nếu bind thất bại vì pathname quá dài, rút ngắn đường dẫn test thay vì tăng giới hạn trong code.

Mỗi test nên dùng một pathname riêng trong thư mục tạm. Không dùng một socket path cố định chung cho toàn bộ test suite vì test song song có thể bind trùng nhau.

## 3. Giao thức test đơn giản: client gửi rồi half-close output

Để test echo server dễ dự đoán, có thể dùng giao thức nhỏ:

1. Client kết nối.
2. Client ghi toàn bộ payload.
3. Client gọi shutdownOutput() để báo rằng không gửi thêm byte nào.
4. Server đọc đến EOF, sau đó phản hồi payload đã nhận.
5. Client đọc response đến EOF.

shutdownOutput() đóng nửa chiều gửi của client nhưng vẫn cho phép client đọc response. Đây là cách tạo ranh giới request rõ ràng cho ví dụ kiểm thử; ứng dụng thực tế thường dùng length prefix, delimiter hoặc framing theo giao thức riêng.

Phương thức exchange sau được đặt trong cùng lớp UnixSocketTestSupport:

~~~java
static String exchange(Path socketPath, String message)
        throws IOException {
    try (SocketChannel client =
                 SocketChannel.open(StandardProtocolFamily.UNIX)) {
        client.connect(UnixDomainSocketAddress.of(socketPath));

        ByteBuffer request = StandardCharsets.UTF_8.encode(message);
        while (request.hasRemaining()) {
            client.write(request);
        }
        client.shutdownOutput();

        ByteBuffer response = ByteBuffer.allocate(8193);
        while (true) {
            int count = client.read(response);
            if (count < 0) {
                break;
            }
            if (!response.hasRemaining()) {
                throw new IOException("Response exceeds test buffer");
            }
        }

        response.flip();
        return StandardCharsets.UTF_8.decode(response).toString();
    }
}
~~~

Client channel được đóng bởi try-with-resources kể cả khi connect, write hoặc read thất bại. Vòng lặp write xử lý partial write; vòng lặp read không giả định một lần read nhận đủ response.

Trong ví dụ, response bị giới hạn ở 8192 byte để test không phải cấp phát bộ nhớ không giới hạn. Giao thức production cần có giới hạn kích thước frame, chính sách từ chối payload quá lớn và xử lý dữ liệu UTF-8 bị chia giữa các lần đọc.

## 4. Server fixture xử lý nhiều client

Để kiểm thử nhiều client đồng thời, server fixture cần một accept loop và khả năng xử lý mỗi client độc lập. Ví dụ sau dùng một executor cho accept loop và một executor cho các handler. Đây là fixture cho test, không phải cấu hình thread pool production.

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

final class EchoServer implements AutoCloseable {
    private static final int MAX_REQUEST_BYTES = 8192;

    private final Path socketPath;
    private final ServerSocketChannel listener;
    private final ExecutorService acceptor =
            Executors.newSingleThreadExecutor();
    private final ExecutorService handlers =
            Executors.newCachedThreadPool();
    private final Set<SocketChannel> clients =
            ConcurrentHashMap.newKeySet();
    private final AtomicBoolean running = new AtomicBoolean(true);
    private final AtomicReference<IOException> acceptFailure =
            new AtomicReference<>();
    private final CountDownLatch firstClientAccepted =
            new CountDownLatch(1);

    static EchoServer start(Path socketPath) throws IOException {
        ServerSocketChannel listener =
                ServerSocketChannel.open(StandardProtocolFamily.UNIX);
        try {
            listener.bind(UnixDomainSocketAddress.of(socketPath));
            return new EchoServer(socketPath, listener);
        } catch (IOException | RuntimeException e) {
            try {
                listener.close();
            } catch (IOException closeFailure) {
                e.addSuppressed(closeFailure);
            }
            throw e;
        }
    }

    private EchoServer(Path socketPath, ServerSocketChannel listener) {
        this.socketPath = socketPath;
        this.listener = listener;
        acceptor.execute(this::acceptLoop);
    }

    private void acceptLoop() {
        while (running.get()) {
            try {
                SocketChannel client = listener.accept();
                clients.add(client);
                firstClientAccepted.countDown();
                handlers.execute(() -> echo(client));
            } catch (IOException e) {
                if (running.get()) {
                    acceptFailure.compareAndSet(null, e);
                }
                return;
            } catch (RuntimeException e) {
                if (running.get()) {
                    acceptFailure.compareAndSet(
                            null, new IOException("Accept handler failed", e));
                }
                return;
            }
        }
    }

    private void echo(SocketChannel client) {
        try (client) {
            ByteBuffer request = ByteBuffer.allocate(
                    MAX_REQUEST_BYTES + 1);

            while (true) {
                int count = client.read(request);
                if (count < 0) {
                    break;
                }
                if (request.position() > MAX_REQUEST_BYTES) {
                    throw new IOException("Request exceeds test limit");
                }
            }

            request.flip();
            while (request.hasRemaining()) {
                client.write(request);
            }
        } catch (IOException ignored) {
            // Client có thể đã ngắt kết nối hoặc server đang shutdown.
        } finally {
            clients.remove(client);
        }
    }

    void awaitFirstClient() throws InterruptedException {
        if (!firstClientAccepted.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Server did not accept a client in time");
        }
    }

    @Override
    public void close() throws IOException {
        running.set(false);
        IOException failure = null;

        try {
            listener.close();
        } catch (IOException e) {
            failure = e;
        }

        acceptor.shutdownNow();
        try {
            awaitTermination(acceptor, "acceptor");
        } catch (IOException e) {
            failure = append(failure, e);
        }

        for (SocketChannel client : List.copyOf(clients)) {
            try {
                client.close();
            } catch (IOException e) {
                failure = append(failure, e);
            }
        }

        handlers.shutdownNow();
        try {
            awaitTermination(handlers, "client handlers");
        } catch (IOException e) {
            failure = append(failure, e);
        }

        try {
            Files.deleteIfExists(socketPath);
        } catch (IOException e) {
            failure = append(failure, e);
        }

        IOException acceptProblem = acceptFailure.get();
        if (acceptProblem != null) {
            failure = append(failure, acceptProblem);
        }

        if (failure != null) {
            throw failure;
        }
    }

    private static IOException append(
            IOException failure, IOException next) {
        if (failure == null) {
            return next;
        }
        failure.addSuppressed(next);
        return failure;
    }

    private static void awaitTermination(
            ExecutorService executor, String name) throws IOException {
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IOException(name + " did not terminate");
                }
            }
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
            throw new IOException("Interrupted while stopping " + name, e);
        }
    }
}
~~~

Fixture này giữ một tập client channel đang mở để có thể đóng chúng khi server dừng. Accept loop được dừng bằng cách đóng listening channel, nhờ đó lời gọi accept() đang block được đánh thức. Sau khi acceptor dừng, fixture đóng các client còn lại, dừng handler executor và xóa pathname đã bind.

Trong production, không nên dùng cached thread pool không giới hạn nếu số client có thể tăng lớn. Hãy đặt giới hạn tài nguyên, queue policy, timeout, giới hạn kết nối và chiến lược backpressure phù hợp. Một selector event loop hoặc kiến trúc xử lý kết nối khác có thể phù hợp hơn tùy tải.

## 5. Kiểm thử server khởi động lại trên cùng pathname

Khi bind một Unix-domain server socket vào pathname, hệ điều hành tạo một socket file. Socket file vẫn tồn tại sau khi channel đóng và phải được xóa trước khi một server khác bind cùng tên. Đây là khác biệt quan trọng so với suy nghĩ rằng đóng ServerSocketChannel tự giải phóng cả tên pathname.

Test restart cơ bản:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class UnixSocketRestartTest {
    @TempDir
    Path tempDir;

    @Test
    void restartsServerOnTheSameSocketPath() throws Exception {
        UnixSocketTestSupport.requireUnixDomainSocketSupport();
        Path socketPath = tempDir.resolve("svc.sock");

        try (EchoServer first = EchoServer.start(socketPath)) {
            assertEquals("first",
                    UnixSocketTestSupport.exchange(socketPath, "first"));
        }

        assertFalse(Files.exists(socketPath));

        try (EchoServer second = EchoServer.start(socketPath)) {
            assertEquals("second",
                    UnixSocketTestSupport.exchange(socketPath, "second"));
        }

        assertFalse(Files.exists(socketPath));
    }
}
~~~

Test này xác nhận ba điều: server đầu tiên phục vụ request, fixture đóng listener và xóa socket file, server thứ hai bind lại cùng pathname và phục vụ request mới. Mỗi instance có channel và executor riêng.

Nếu server đóng channel nhưng không xóa socket file, lần bind thứ hai thường thất bại vì tên đã tồn tại. Vì vậy, test nên kiểm tra Files.exists(socketPath) sau shutdown thay vì chỉ kiểm tra isOpen() của channel.

## 6. Kiểm thử client cũ khi server restart

Một client đã kết nối với server cũ không tự chuyển sang server mới khi pathname được bind lại. SocketChannel đang giữ kết nối tới endpoint cũ; ứng dụng cần nhận biết disconnect và chủ động tạo kết nối mới.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SocketChannel;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class UnixSocketClientRestartTest {
    @TempDir
    Path tempDir;

    @Test
    void oldConnectionEndsAndNewClientConnectsAfterRestart()
            throws Exception {
        UnixSocketTestSupport.requireUnixDomainSocketSupport();
        Path socketPath = tempDir.resolve("svc.sock");
        EchoServer first = EchoServer.start(socketPath);
        SocketChannel oldClient =
                SocketChannel.open(StandardProtocolFamily.UNIX);

        try {
            oldClient.connect(UnixDomainSocketAddress.of(socketPath));
            first.awaitFirstClient();

            first.close();
            assertFalse(Files.exists(socketPath));

            ByteBuffer oneByte = ByteBuffer.allocate(1);
            try {
                int count = oldClient.read(oneByte);
                assertEquals(-1, count);
            } catch (IOException disconnected) {
                // Provider có thể báo lỗi I/O khi peer đã bị đóng.
            }
        } finally {
            oldClient.close();
            first.close();
        }

        try (EchoServer second = EchoServer.start(socketPath)) {
            assertEquals("new-connection",
                    UnixSocketTestSupport.exchange(
                            socketPath, "new-connection"));
        }
    }
}
~~~

Test xác nhận client cũ không được xem là đã kết nối với server mới. Sau khi server đầu tiên đóng accepted channel và dọn pathname, client mới tạo SocketChannel mới để kết nối tới instance thứ hai.

Trong ứng dụng, logic reconnect cần có deadline, backoff có giới hạn, xử lý hủy request và quy tắc retry theo tính idempotent của operation. Không retry vô hạn hoặc tự gửi lại lệnh ghi dữ liệu có thể đã được server cũ xử lý nhưng client chưa nhận response.

## 7. Kiểm thử nhiều client kết nối đồng thời

Để test thực sự tạo cạnh tranh, dùng CountDownLatch cho các client chờ ở vạch xuất phát rồi cùng bắt đầu. Không dùng Thread.sleep() để cố tạo đồng thời vì thời điểm chạy phụ thuộc scheduler và tải máy.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class UnixSocketConcurrentClientTest {
    @TempDir
    Path tempDir;

    @Test
    void servesConcurrentClientsWithoutMixingResponses() throws Exception {
        UnixSocketTestSupport.requireUnixDomainSocketSupport();
        Path socketPath = tempDir.resolve("parallel.sock");
        int clientCount = 12;

        try (EchoServer server = EchoServer.start(socketPath)) {
            ExecutorService pool =
                    Executors.newFixedThreadPool(clientCount);
            CountDownLatch ready = new CountDownLatch(clientCount);
            CountDownLatch start = new CountDownLatch(1);
            List<Future<String>> results = new ArrayList<>();

            try {
                for (int i = 0; i < clientCount; i++) {
                    String request = "client-" + i;
                    results.add(pool.submit(() -> {
                        ready.countDown();
                        if (!start.await(5, TimeUnit.SECONDS)) {
                            throw new IllegalStateException(
                                    "Start signal timed out");
                        }
                        return UnixSocketTestSupport.exchange(
                                socketPath, request);
                    }));
                }

                assertTrue(ready.await(5, TimeUnit.SECONDS),
                        "Not all client tasks became ready");
                start.countDown();

                for (int i = 0; i < clientCount; i++) {
                    assertEquals("client-" + i,
                            results.get(i).get(10, TimeUnit.SECONDS));
                }
            } finally {
                start.countDown();
                pool.shutdownNow();
                assertTrue(pool.awaitTermination(5, TimeUnit.SECONDS),
                        "Client executor did not terminate");
            }
        }
    }
}
~~~

Mỗi task tạo SocketChannel riêng và gửi một chuỗi có ID riêng. Test kiểm tra response của từng Future theo đúng ID. Nếu server dùng chung một buffer mutable cho nhiều client hoặc gắn nhầm state giữa các connection, test có thể phát hiện response bị trộn.

Trong fixture, mỗi client được xử lý bởi một handler độc lập. Nếu server production dùng Selector, mỗi SelectionKey nên có attachment hoặc connection state riêng. Không chia sẻ ByteBuffer đang được đọc/ghi giữa các client nếu không có đồng bộ hóa và ownership rõ ràng.

## 8. Kiểm thử peer đóng channel bình thường

Khi peer gọi close() hoặc shutdownOutput(), phía còn lại sẽ đọc dữ liệu đã được gửi trước đó rồi nhận EOF. Với SocketChannel dạng stream, read() trả về -1 khi đầu vào đã kết thúc sau khi dữ liệu đệm được tiêu thụ.

Ví dụ ở phía server:

~~~java
try (SocketChannel client = server.accept()) {
    ByteBuffer buffer = ByteBuffer.allocate(1024);

    while (true) {
        int count = client.read(buffer);
        if (count < 0) {
            break;
        }
    }

    buffer.flip();
    // Xử lý phần dữ liệu đã nhận trước EOF.
}
~~~

Nếu channel ở non-blocking mode, read() có thể trả 0 khi hiện tại chưa có dữ liệu; 0 không có nghĩa peer đã đóng. Chỉ -1 mới biểu thị EOF. Vì vậy, không được viết điều kiện kiểu count <= 0 rồi đóng client ngay trong non-blocking event loop.

Khi nhận EOF, server cần:

1. Hoàn tất xử lý dữ liệu đã nhận nếu giao thức cho phép.
2. Hủy SelectionKey hoặc bỏ interest operation không còn cần.
3. Đóng SocketChannel.
4. Xóa connection khỏi registry.
5. Giải phóng buffer và trạng thái ứng dụng gắn với connection.

Nếu giao thức yêu cầu frame hoàn chỉnh nhưng peer đóng giữa chừng, hãy phân biệt EOF tại ranh giới frame với EOF khi frame chưa đủ byte. Trường hợp thứ hai là truncated request và thường phải bị từ chối hoặc ghi log như một protocol error.

## 9. Kiểm thử tiến trình peer bị kill đột ngột

Đóng SocketChannel trong cùng JVM kiểm tra đường xử lý disconnect ở cấp channel. Để kiểm tra trường hợp peer process biến mất, có thể khởi chạy một JVM con, cho nó kết nối và chờ, sau đó gọi destroyForcibly() từ test process.

Tiến trình con:

~~~java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

public final class PeerProcessMain {
    public static void main(String[] args) throws Exception {
        Path socketPath = Path.of(args[0]);

        try (SocketChannel peer =
                     SocketChannel.open(StandardProtocolFamily.UNIX)) {
            peer.connect(UnixDomainSocketAddress.of(socketPath));

            System.out.println("CONNECTED");
            System.out.flush();

            // Chờ server; test process sẽ kết thúc JVM này cưỡng bức.
            peer.read(ByteBuffer.allocate(1));
        }
    }
}
~~~

Lưu lớp này trong file PeerProcessMain.java thuộc test source set. Đặt nó cùng package với test class để JVM con có thể tải class này từ test runtime classpath.

Test process:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class UnixSocketPeerProcessTest {
    @TempDir
    Path tempDir;

    @Test
    void detectsEofWhenPeerProcessIsKilled() throws Exception {
        UnixSocketTestSupport.requireUnixDomainSocketSupport();
        Path socketPath = tempDir.resolve("peer.sock");
        ExecutorService outputReader = Executors.newSingleThreadExecutor();
        Process child = null;

        try (ServerSocketChannel server =
                     ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
            server.bind(UnixDomainSocketAddress.of(socketPath));

            Path javaExecutable = Path.of(
                    System.getProperty("java.home"),
                    "bin",
                    isWindows() ? "java.exe" : "java");

            child = new ProcessBuilder(
                    javaExecutable.toString(),
                    "-cp",
                    System.getProperty("java.class.path"),
                    PeerProcessMain.class.getName(),
                    socketPath.toString())
                    .redirectErrorStream(true)
                    .start();

            Process peerProcess = child;
            Future<String> readyLine = outputReader.submit(() -> {
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(
                                peerProcess.getInputStream(),
                                StandardCharsets.UTF_8))) {
                    return reader.readLine();
                }
            });

            assertEquals("CONNECTED",
                    readyLine.get(10, TimeUnit.SECONDS));

            try (SocketChannel accepted = server.accept()) {
                child.destroyForcibly();
                assertTrue(child.waitFor(10, TimeUnit.SECONDS),
                        "Peer process did not terminate");

                Future<Integer> readResult = outputReader.submit(
                        () -> accepted.read(ByteBuffer.allocate(1)));

                try {
                    assertEquals(-1, readResult.get(5, TimeUnit.SECONDS));
                } catch (ExecutionException e) {
                    assertTrue(e.getCause() instanceof IOException,
                            "Expected EOF or an I/O disconnect");
                }
            }
        } finally {
            if (child != null && child.isAlive()) {
                child.destroyForcibly();
                child.waitFor(5, TimeUnit.SECONDS);
            }
            outputReader.shutdownNow();
            outputReader.awaitTermination(5, TimeUnit.SECONDS);
            Files.deleteIfExists(socketPath);
        }
    }

    private static boolean isWindows() {
        return System.getProperty("os.name")
                .toLowerCase(java.util.Locale.ROOT)
                .contains("win");
    }
}
~~~

Test này dùng một tiến trình Java độc lập để tạo peer thật. Dòng CONNECTED trên stdout xác nhận child đã connect trước khi parent chấp nhận và kill process. Sau khi process bị kết thúc, server-side channel phải nhận biết kết nối đã đóng; thông thường read() trả -1, một số tình huống/provider có thể biểu diễn disconnect bằng IOException.

Đoạn test là mẫu tích hợp: classpath của tiến trình con phải chứa test class và dependency cần thiết. Một số build runner dùng classpath launcher riêng; khi đó hãy truyền test runtime classpath do build tool cung cấp thay cho java.class.path của JVM cha.

Không nên khẳng định mọi peer crash luôn tạo ra cùng một exception. Dữ liệu đã được kernel buffer trước khi peer chết có thể vẫn được đọc trước EOF. Với lỗi kết nối khi ghi, ứng dụng có thể nhận IOException. Code production nên xử lý EOF và IOException như các tín hiệu connection termination, đồng thời ghi nhận nguyên nhân phù hợp.

## 10. Server crash và socket pathname còn sót lại

Khi server bind một pathname, socket file được tạo trên filesystem. File này vẫn tồn tại sau khi ServerSocketChannel đóng và cũng có thể còn lại nếu process bị kill trước khi chạy cleanup. Vì vậy, restart sau crash cần một chính sách xử lý stale socket path.

Không được xóa pathname chỉ vì lần bind mới nhận lỗi "đã tồn tại". Có thể một server instance khác vẫn đang chạy và sở hữu endpoint đó. Một chiến lược an toàn hơn:

1. Dùng process supervisor hoặc lock file để xác định instance sở hữu endpoint.
2. Khi khởi động, kiểm tra owner/lease metadata mà ứng dụng quản lý.
3. Nếu xác nhận instance cũ đã kết thúc, thử kết nối hoặc kiểm tra trạng thái endpoint theo chính sách của hệ thống.
4. Chỉ xóa socket file khi đã xác định đó là pathname stale thuộc dịch vụ này.
5. Bind server mới và ghi nhận owner/instance mới.

Thử connect thất bại một mình chưa đủ chứng minh socket file stale: lỗi có thể do quyền truy cập, giới hạn hệ điều hành hoặc server đang trong quá trình khởi động. Không xóa file của tiến trình khác.

Với server shutdown bình thường, hãy đóng listener trước rồi gọi Files.deleteIfExists(path). Đưa cleanup vào finally hoặc resource quản lý pathname để nó chạy khi có exception. Với process crash hoặc máy mất điện, finally không chạy; cần startup recovery có kiểm soát.

## 11. Kiểm thử retry và reconnect có giới hạn

Client có thể cần kết nối lại khi server restart. Retry nên có giới hạn thời gian và backoff thay vì vòng lặp vô hạn:

~~~java
static SocketChannel connectWithRetry(
        Path socketPath,
        int maxAttempts,
        long delayMillis) throws IOException, InterruptedException {

    if (maxAttempts < 1 || delayMillis < 0) {
        throw new IllegalArgumentException(
                "maxAttempts must be positive and delayMillis non-negative");
    }

    IOException lastFailure = null;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        SocketChannel channel =
                SocketChannel.open(StandardProtocolFamily.UNIX);
        try {
            channel.connect(UnixDomainSocketAddress.of(socketPath));
            return channel;
        } catch (IOException e) {
            lastFailure = e;
            channel.close();
        }

        if (attempt < maxAttempts) {
            try {
                Thread.sleep(delayMillis);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw e;
            }
        }
    }

    throw new IOException(
            "Could not connect after " + maxAttempts + " attempts",
            lastFailure);
}
~~~

Đây là ví dụ đơn giản chỉ giới hạn số lần thử; một blocking connect vẫn có thể mất thời gian theo hành vi của hệ điều hành. Production cần deadline thực sự cho toàn bộ quá trình, chẳng hạn dùng non-blocking connect với Selector và đo bằng System.nanoTime(), kết hợp exponential backoff có jitter và cancellation. Không dùng thời gian wall-clock để đo timeout vì đồng hồ hệ thống có thể thay đổi.

Chỉ retry operation an toàn. Với request ghi dữ liệu, nếu client mất kết nối trước khi nhận response thì không biết server đã xử lý request hay chưa. Giao thức cần request ID/idempotency key hoặc cơ chế tra cứu kết quả để tránh thực hiện trùng.

## 12. Kiểm thử server xử lý nhiều client nhưng một peer bị mất

Một tình huống quan trọng là nhiều client đang hoạt động, một client bị kill, các client còn lại vẫn phải nhận đúng response. Test nên xác minh server cô lập lỗi theo connection:

- Mỗi client có SocketChannel và buffer riêng.
- EOF hoặc IOException ở một client chỉ đóng connection đó.
- Selector tiếp tục phục vụ các key hợp lệ khác.
- Registry loại bỏ đúng client đã kết thúc.
- Server không dừng toàn bộ event loop chỉ vì một peer bị mất, trừ khi đó là chính sách đã chọn.

Có thể kiểm tra isolation ngay trong cùng JVM bằng cách đóng một client đang mở rồi gửi request từ client khác:

~~~java
@Test
void oneDisconnectedClientDoesNotAffectAnotherClient()
        throws Exception {
    UnixSocketTestSupport.requireUnixDomainSocketSupport();
    Path socketPath = tempDir.resolve("isolation.sock");

    try (EchoServer server = EchoServer.start(socketPath);
         java.nio.channels.SocketChannel abandoned =
                 java.nio.channels.SocketChannel.open(
                         java.net.StandardProtocolFamily.UNIX)) {

        abandoned.connect(
                java.net.UnixDomainSocketAddress.of(socketPath));
        server.awaitFirstClient();

        abandoned.close();

        assertEquals("survivor",
                UnixSocketTestSupport.exchange(socketPath, "survivor"));
    }
}
~~~

Test này xác nhận server vẫn nhận và phản hồi request mới sau khi một connection bị đóng. Có thể đặt method trong một test class có field TempDir như các ví dụ trước.

Trong selector loop, tránh catch IOException ở phạm vi toàn bộ server rồi đóng listener ngay lập tức nếu lỗi chỉ thuộc một client. Hãy xử lý lỗi theo key:

~~~java
try {
    readClient(key);
} catch (IOException clientFailure) {
    closeClient(key);
    // Ghi log theo connection; tiếp tục vòng selector nếu server còn chạy.
}
~~~

Các thao tác đóng connection thường gồm cancel key, close channel và xóa attachment/registry entry. Nếu Selector bị đóng hoặc listener gặp lỗi nghiêm trọng, đó mới là trạng thái cần shutdown server.

## 13. Không dựa vào sleep để đồng bộ test

Các cách sau thường tạo test chập chờn:

- Khởi động server rồi Thread.sleep(500) để đoán rằng server đã bind.
- Cho client chạy rồi sleep để đoán rằng request đã đến server.
- Kill child process rồi sleep để đoán rằng EOF đã xuất hiện.
- Khởi động nhiều client bằng các sleep khác nhau để tạo tải đồng thời.

Hãy đồng bộ theo sự kiện:

| Nhu cầu | Công cụ phù hợp |
|---|---|
| Server đã bind | Constructor/start method chỉ trả về sau khi bind thành công |
| Server đã accept client | CountDownLatch hoặc Future |
| Tất cả client đã sẵn sàng | CountDownLatch |
| Bắt đầu đồng thời | CountDownLatch hoặc CyclicBarrier |
| Child process đã connect | Marker qua stdout/pipe hoặc handshake trên socket |
| Child process đã chết | Process.waitFor(timeout, unit) |
| Peer đã đóng | read() EOF hoặc Future có timeout |
| Server đã dừng | Future.get(timeout) hoặc awaitTermination |

Mọi wait trong test nên có timeout. Timeout giúp test thất bại rõ ràng thay vì treo toàn bộ build. Khi test thất bại, finally phải đóng socket, dừng executor và kết thúc child process.

## 14. Ma trận kiểm thử đề xuất

| Nhóm | Trường hợp | Kỳ vọng |
|---|---|---|
| Startup | Bind pathname chưa tồn tại | Server start thành công |
| Restart graceful | Đóng server, xóa path, bind lại | Instance mới start thành công |
| Restart cleanup | Server đóng nhưng path còn | Test phát hiện cleanup thiếu |
| Existing connection | Client đang nối khi server đóng | Client nhận EOF hoặc IOException |
| New connection | Client mới sau restart | Kết nối vào instance mới |
| Concurrent clients | Nhiều client gửi ID riêng cùng lúc | Response khớp ID từng client |
| Partial write | Client ghi payload qua nhiều lần write | Server nhận đủ frame |
| Partial read | Server đọc response qua nhiều lần read | Client ghép đủ response |
| Peer close | Client close hoặc shutdownOutput | Server nhận EOF và dọn connection |
| Peer crash | Child process bị destroyForcibly | Server nhận biết connection termination |
| Truncated frame | Peer dừng giữa frame | Parser từ chối request chưa hoàn chỉnh |
| One peer fails | Một client bị mất trong khi client khác hoạt động | Các connection còn lại tiếp tục |
| Server crash | Process chết và socket file còn lại | Recovery chỉ xóa path khi xác nhận stale |
| Retry | Server tạm thời chưa sẵn sàng | Client retry trong deadline, không lặp vô hạn |

Không phải test nào cũng cần chạy trong mọi commit. Có thể chạy test unit nhanh thường xuyên và giữ child-process/crash integration test trong profile CI phù hợp, nhưng các kịch bản restart và concurrent client nên có coverage ổn định.

## 15. Checklist review

- [ ] Mỗi test dùng pathname riêng và ngắn.
- [ ] Test chỉ chạy khi provider hỗ trợ StandardProtocolFamily.UNIX.
- [ ] Server chỉ báo ready sau khi bind thành công.
- [ ] Socket file được xóa sau shutdown bình thường.
- [ ] Test restart bind lại cùng pathname sau cleanup.
- [ ] Không xóa pathname cũ nếu chưa xác định ownership.
- [ ] Client cũ được xem là disconnected sau khi server instance cũ dừng.
- [ ] Mỗi client đồng thời có channel, buffer và connection state riêng.
- [ ] Test concurrency dùng latch/barrier thay vì sleep.
- [ ] Partial read/write được xử lý bằng vòng lặp.
- [ ] EOF được phân biệt với read() trả 0 trong non-blocking mode.
- [ ] Một peer lỗi không làm dừng các client khác ngoài chính sách đã định.
- [ ] Child process test có timeout và cleanup trong finally.
- [ ] Test chấp nhận EOF hoặc IOException phù hợp khi peer biến mất.
- [ ] Retry có deadline/backoff và chỉ áp dụng cho operation an toàn.
- [ ] Truncated frame được phân biệt với request hoàn chỉnh.

## 16. Ghi nhớ

- Java 16 bổ sung Unix-domain socket channel qua StandardProtocolFamily.UNIX và UnixDomainSocketAddress.
- Socket pathname tồn tại sau khi channel đóng; xóa nó trước khi bind lại cùng tên.
- Client cũ không tự chuyển sang server mới sau restart; phải tạo SocketChannel mới.
- Dùng request ID riêng để phát hiện response bị trộn giữa các client đồng thời.
- Mỗi connection cần sở hữu channel, buffer và trạng thái giao thức riêng.
- Với stream socket, đọc đến EOF; trong non-blocking mode, read() trả 0 chỉ có nghĩa hiện chưa có dữ liệu.
- Khi peer process chết, dữ liệu đã được kernel buffer có thể vẫn đến trước EOF; write có thể thất bại bằng IOException.
- Không giả định một exception cụ thể cho mọi kiểu peer termination.
- Test đồng bộ bằng latch, barrier, Future và timeout thay vì Thread.sleep().
- Process crash có thể để lại socket file; recovery phải xác nhận ownership trước khi xóa.
- Retry cần deadline, backoff và idempotency phù hợp.

Kiểm thử restart, concurrency và peer termination giúp xác nhận hệ thống xử lý được những thay đổi vòng đời thường gặp của IPC. Khi test pathname cleanup, dữ liệu từng client, EOF và process death bằng đồng bộ có timeout, ứng dụng Unix-domain socket sẽ dễ vận hành và phục hồi hơn trên các JDK hiện đại.

## Tài liệu tham khảo

- [JEP 380: Unix-Domain Socket Channels](https://openjdk.org/jeps/380) — chuẩn hóa Unix-domain socket channels trong Java 16.
- [Java SE 26 ServerSocketChannel API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html) — bind pathname, backlog và socket file tồn tại sau khi channel đóng.
- [Java SE 26 SocketChannel API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html) — connect, shutdownOutput, read, write và EOF.
- [Java SE 26 Selector API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/Selector.html) — readiness, selected keys và wakeup.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — TempDir, assumptions, assertions và test lifecycle.
