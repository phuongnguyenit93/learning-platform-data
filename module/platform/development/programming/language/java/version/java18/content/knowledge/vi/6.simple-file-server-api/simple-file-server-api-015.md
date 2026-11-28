# stop(delay): dừng máy chủ có kiểm soát và dọn tài nguyên khi kiểm thử kết thúc

> **Chương:** API SimpleFileServer  
> **Module học:** JAVA_VERSION_JAVA18 — SimpleFileServer được bổ sung từ Java 18; vòng đời HttpServer, xử lý exchange và dọn tài nguyên kiểm thử vẫn áp dụng trên JDK hiện đại.  
> **Mục tiêu:** Hiểu chính xác HttpServer.stop(delay) chờ những gì, chọn delay phù hợp, phân biệt dừng server với shutdown ExecutorService và bảo đảm thư mục/file tạm được dọn sau khi exchange kết thúc.

## 1. Vì sao cần dừng HttpServer có kiểm soát?

Một test tích hợp có thể tạo HttpServer cục bộ, đăng ký file handler, gửi HTTP request rồi kiểm tra status và response body. Khi assertion hoàn tất, test phải dừng server và giải phóng tài nguyên. Nếu chỉ kết thúc phương thức test mà bỏ quên server hoặc thread pool, tiến trình test có thể còn thread nền, cổng vẫn bị chiếm hoặc file tạm chưa thể xóa.

Một vòng đời test điển hình:

~~~text
Tạo thư mục/file tạm
        |
        v
Tạo và cấu hình HttpServer
        |
        v
Đăng ký context / handler / filter
        |
        v
server.start()
        |
        v
Gửi HTTP request và kiểm tra response
        |
        v
server.stop(delay)
        |
        v
Shutdown ExecutorService do test sở hữu
        |
        v
Xóa thư mục và file tạm
~~~

HttpServer.stop(int delay) là điểm kết thúc nhận request và chờ các exchange đang chạy trong một khoảng thời gian hữu hạn. Đây là API của module jdk.httpserver, đã có từ trước Java 18 và vẫn dùng được trên JDK hiện đại.

## 2. Hợp đồng chính xác của stop(delay)

Chữ ký:

~~~java
public abstract void stop(int delay)
~~~

Tham số delay là số giây chờ các exchange hiện tại kết thúc. Khi gọi phương thức, server thực hiện theo thứ tự:

1. Đóng listening socket, không nhận exchange mới.
2. Chờ các exchange hiện tại hoàn tất hoặc chờ đến khi khoảng delay giây hết — điều kiện nào đến trước.
3. Đóng các TCP connection còn mở.
4. Trả quyền điều khiển về caller.

| Giá trị delay | Hành vi |
| --- | --- |
| Số nguyên dương | Chờ exchange hiện tại hoàn tất, tối đa khoảng số giây đã chỉ định. |
| 0 | Trả về ngay, không chờ handler hoàn tất. Các TCP connection còn mở sẽ bị đóng. |
| Số âm | Ném IllegalArgumentException. |

Thời gian chờ được tính bằng **giây**, không phải milliseconds. API không nhận Duration.

Điểm quan trọng: stop(delay) không đảm bảo mọi handler luôn hoàn tất. Nếu handler hoàn tất trước thời hạn, server có thể trả về sớm. Nếu hết thời hạn mà exchange còn mở, server đóng các connection đang mở và trả về. Client có thể nhận response bị ngắt hoặc lỗi I/O.

Sau khi đã dừng, một HttpServer không thể khởi động lại. Nếu cần chạy test khác, hãy tạo instance server mới.

## 3. Graceful stop và immediate stop

### 3.1. Dừng có thời gian chờ

~~~java
server.stop(3);
~~~

Server ngừng nhận request mới và dành tối đa khoảng ba giây cho exchange hiện tại hoàn tất. Nếu các handler kết thúc sau 200 ms, caller không cần chờ đủ ba giây. Nếu một handler vẫn chạy khi hết thời gian, connection của exchange đó có thể bị đóng.

Đây là lựa chọn thường dùng trong finally của test tích hợp có handler ngắn và cần cho response hoàn tất trước khi dọn thư mục tạm.

### 3.2. Dừng ngay

~~~java
server.stop(0);
~~~

stop(0) không chờ handler hoàn tất. Dùng khi test cần kết thúc nhanh và chấp nhận các exchange đang chạy bị ngắt. Không dùng nó nếu ngay sau đó test cần bảo đảm response của request đang chạy đã được ghi đầy đủ.

### 3.3. Chọn delay theo thời gian xử lý

| Loại handler | Cách chọn delay |
| --- | --- |
| File handler đọc file nhỏ trong thư mục tạm | Một khoảng ngắn, ví dụ 1–2 giây, thường đủ cho test cục bộ. |
| Handler trả JSON/text nhỏ | Chọn theo thời gian xử lý tối đa của test. |
| Handler streaming hoặc tạo response lớn | Chọn theo thời gian stream có thể hoàn tất; nếu không cần kiểm thử stream, hãy đóng/giới hạn test trước khi stop. |
| Handler gọi dịch vụ ngoài | Đặt timeout cho I/O bên ngoài; không dựa vào stop delay để thay thế timeout. |
| Handler có thể treo | Sửa handler hoặc dùng timeout/cancellation riêng; tăng delay mãi không giải quyết được nguyên nhân. |

Các giá trị 1–2 giây chỉ là gợi ý cho ví dụ cục bộ, không phải cấu hình chung cho production. Thời gian thực tế phụ thuộc workload, hệ điều hành và handler.

## 4. stop(delay) không phải shutdown ExecutorService

Hai thao tác quản lý hai tài nguyên khác nhau:

| Thao tác | Quản lý | Tác dụng |
| --- | --- | --- |
| server.stop(delay) | HttpServer, listening socket và TCP connections | Ngừng nhận exchange mới, chờ exchange hiện tại trong giới hạn delay rồi đóng connection còn mở. |
| executor.shutdown() | ExecutorService do ứng dụng sở hữu | Ngừng nhận task mới, để task đã submit tiếp tục chạy. |
| executor.shutdownNow() | ExecutorService do ứng dụng sở hữu | Cố gắng interrupt task đang chạy và trả về task chưa bắt đầu. |
| executor.awaitTermination(...) | ExecutorService do ứng dụng sở hữu | Chờ executor kết thúc trong giới hạn thời gian. |

stop(delay) không thay thế ExecutorService.shutdown(). Nếu test đã tạo thread pool và truyền nó qua server.setExecutor(executor), test vẫn phải quản lý pool đó.

Thứ tự thông thường:

~~~text
server.stop(delay)
        |
        v
executor.shutdown()
        |
        v
executor.awaitTermination(timeout)
        |
        +---- kết thúc ----> dọn file tạm
        |
        +---- hết timeout --> executor.shutdownNow()
                                  |
                                  v
                             chờ thêm có giới hạn
~~~

Không shutdown executor trước server. Trong khoảng thời gian server vẫn nhận request, nó có thể cần submit task mới cho executor. Nếu executor đã từ chối task, exchange mới có thể không được xử lý như mong muốn.

Nếu dùng executor mặc định vì không gọi setExecutor, test không sở hữu một ExecutorService cụ thể để shutdown. Chỉ shutdown executor mà test đã tạo hoặc được giao quyền quản lý; không tự ý dừng executor dùng chung của thành phần khác.

## 5. Handler còn chạy sau khi stop hết delay

stop(delay) giới hạn thời gian server chờ exchange, không phải một cơ chế interrupt tổng quát cho mọi handler. Khi hết delay, server đóng các TCP connection còn mở. API không cam kết rằng code handler đang chạy sẽ tự dừng ngay tại thời điểm đó.

Nếu handler đang chạy trên ExecutorService do ứng dụng quản lý:

- Sau khi server.stop(delay) trả về, gọi executor.shutdown() để ngừng nhận task mới.
- Dùng awaitTermination(...) để chờ task đã submit kết thúc.
- Nếu quá hạn, shutdownNow() yêu cầu interrupt task đang chạy.
- Handler phải hợp tác với interrupt và các thao tác I/O cần có timeout.

Nếu handler bỏ qua interrupt hoặc mắc kẹt trong thao tác không có timeout, executor có thể không kết thúc đúng hạn. Không có một lời gọi stop(delay) nào có thể bảo đảm dừng an toàn code Java tùy ý đang chạy.

**Không gọi server.stop(delay) từ chính handler của exchange đang được server chờ hoàn tất.** Nếu handler gọi stop, phương thức có thể chờ chính exchange đó đến hết delay rồi đóng connection; handler chỉ có thể tiếp tục sau khi stop trả về. Hãy để thread điều phối/test gọi stop sau khi điều kiện test hoàn tất.

## 6. Dùng try/finally để cleanup luôn chạy

Test cần dọn tài nguyên ngay cả khi request lỗi hoặc assertion thất bại. Mẫu cơ bản:

~~~java
HttpServer server = HttpServer.create(address, 0);
boolean started = false;

try {
    server.createContext("/", handler);
    server.start();
    started = true;

    // Gửi request và assert response.
} finally {
    if (started) {
        server.stop(2);
    }
}
~~~

finally được chạy khi:

- Request thành công.
- Client ném IOException.
- Assertion ném AssertionError.
- Một thao tác trong phần test ném exception.

Nếu server chưa start thành công thì không cần gọi stop trong ví dụ này. Nếu đã start, gọi stop trước khi xóa root directory để file handler không còn đọc file trong lúc cleanup.

Khi test còn sở hữu executor và thư mục tạm, dùng finally lồng nhau để bảo đảm lỗi ở một bước cleanup không bỏ qua các bước sau:

~~~java
finally {
    try {
        if (started) {
            server.stop(2);
        }
    } finally {
        try {
            if (executor != null) {
                shutdownExecutor(executor);
            }
        } finally {
            deleteTree(root);
        }
    }
}
~~~

Trong ứng dụng thật, có thể ghi nhận exception cleanup để không che mất exception gốc từ test. Mục tiêu của cấu trúc lồng nhau là vẫn thử giải phóng executor và file tạm khi một bước trước đó thất bại.

## 7. Chọn cổng và thư mục tạm để test độc lập

### 7.1. Dùng cổng 0

~~~java
HttpServer server = HttpServer.create(
        new InetSocketAddress(InetAddress.getLoopbackAddress(), 0),
        0);
~~~

Cổng 0 yêu cầu hệ điều hành cấp một cổng khả dụng. Sau khi bind, đọc cổng thực tế bằng:

~~~java
int port = server.getAddress().getPort();
~~~

Không hard-code cổng như 8080 trong test. Hai test chạy song song có thể tranh cùng một cổng; cổng 0 giúp mỗi server có địa chỉ riêng.

Bind vào loopback nếu test chỉ chạy trên máy hiện tại. Điều này tránh mở server demo ra các giao diện mạng khác.

### 7.2. Tạo root riêng cho mỗi test

~~~java
Path root = Files.createTempDirectory("simple-file-server-test-");
~~~

Mỗi test có thư mục riêng, không đọc hoặc ghi đè file của test khác. Sau khi server dừng và executor kết thúc, xóa cây thư mục:

~~~java
static void deleteTree(Path root) throws IOException {
    if (!Files.exists(root)) {
        return;
    }
    try (var paths = Files.walk(root)) {
        for (Path path : paths
                .sorted(Comparator.reverseOrder()).toList()) {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Sắp xếp đường dẫn đảo ngược để xóa file con trước rồi mới xóa thư mục cha. Trên Windows, việc xóa file đang được mở có thể thất bại; vì vậy phải stop server và chờ handler/executor kết thúc trước khi xóa.

## 8. Ví dụ hoàn chỉnh: test file handler và cleanup có kiểm soát

Ví dụ sau tạo một file server cục bộ, dùng fixed thread pool do test sở hữu, gửi request bằng HttpClient, kiểm tra response, sau đó dừng server, shutdown executor và xóa thư mục tạm.

Lưu thành StopServerAfterTest.java:

~~~java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;

import java.io.IOException;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class StopServerAfterTest {
    private static URI uri(InetSocketAddress address, String path) {
        InetAddress ip = address.getAddress();
        String host = ip.getHostAddress();
        if (ip instanceof Inet6Address) {
            host = "[" + host + "]";
        }
        return URI.create(
                "http://" + host + ":" + address.getPort() + path);
    }

    private static void shutdownExecutor(ExecutorService executor) {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.err.println("Executor chưa kết thúc sau timeout");
                }
            }
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    private static void deleteTree(Path root) throws IOException {
        if (!Files.exists(root)) {
            return;
        }
        try (var paths = Files.walk(root)) {
            for (Path path : paths
                    .sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("simple-file-server-test-");
        ExecutorService executor = null;
        HttpServer server = null;
        boolean started = false;

        try {
            Files.writeString(
                    root.resolve("hello.txt"),
                    "Hello from a temporary root",
                    StandardCharsets.UTF_8);

            executor = Executors.newFixedThreadPool(2);
            server = HttpServer.create(
                    new InetSocketAddress(InetAddress.getLoopbackAddress(), 0),
                    0);

            server.setExecutor(executor);
            server.createContext(
                    "/", SimpleFileServer.createFileHandler(root));
            server.start();
            started = true;

            URI fileUri = uri(server.getAddress(), "/hello.txt");
            HttpResponse<String> response = HttpClient.newHttpClient().send(
                    HttpRequest.newBuilder(fileUri).GET().build(),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            if (response.statusCode() != 200) {
                throw new AssertionError(
                        "Expected 200 but got " + response.statusCode());
            }
            if (!response.body().equals("Hello from a temporary root")) {
                throw new AssertionError("Unexpected response body");
            }

            System.out.println("URL: " + fileUri);
            System.out.println("HTTP " + response.statusCode());
            System.out.println(response.body());
        } finally {
            try {
                if (started) {
                    // Chờ tối đa hai giây cho exchange hiện tại hoàn tất.
                    server.stop(2);
                }
            } finally {
                try {
                    if (executor != null) {
                        shutdownExecutor(executor);
                    }
                } finally {
                    // Chỉ xóa file sau khi server và worker đã dừng.
                    deleteTree(root);
                }
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 18 trở lên:

~~~bash
javac StopServerAfterTest.java
java StopServerAfterTest
~~~

Kết quả có dạng:

~~~text
URL: http://127.0.0.1:54321/hello.txt
HTTP 200
Hello from a temporary root
~~~

Cổng thực tế thay đổi theo lần chạy. Nếu hệ thống chọn loopback IPv6, hàm uri(...) đặt địa chỉ trong dấu ngoặc vuông.

## 9. Test delay có chủ đích

Có thể kiểm tra khác biệt giữa stop có chờ và stop ngay bằng handler có thời gian xử lý xác định. Ví dụ handler chờ một khoảng ngắn có giới hạn:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

HttpHandler slowHandler = exchange -> {
    try {
        Thread.sleep(800);
        byte[] body = "done".getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, body.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body);
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IOException("Handler bị interrupt", e);
    }
};
~~~

Nếu test gửi request đến handler này rồi gọi server.stop(2) từ thread điều phối, khoảng chờ hai giây đủ để handler 800 ms hoàn tất trong điều kiện test bình thường. Nếu gọi server.stop(0) ngay sau khi gửi request bất đồng bộ, connection có thể bị đóng trước khi response hoàn tất.

Không dùng Thread.sleep() để đo chính xác thời gian stop trong test ổn định. Scheduling của hệ điều hành và tải máy có thể làm thời gian dao động. Dùng CountDownLatch, Future hoặc điều kiện đồng bộ để biết handler đã vào/ra khỏi đoạn cần kiểm thử.

Ví dụ trên chỉ minh họa handler có thời gian hữu hạn. Handler thực tế nên có timeout cho I/O và không phụ thuộc vào việc stop delay sẽ interrupt nó.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test kết thúc nhưng JVM không thoát | ExecutorService do test tạo vẫn còn worker. | Stop server, shutdown executor và chờ termination. |
| Test sau không bind được cổng | Server trước chưa được stop hoặc test hard-code cổng dùng chung. | Dùng cổng 0 và cleanup trong finally. |
| Response đang tải bị cắt | stop(0) hoặc delay hết trước khi exchange hoàn tất. | Chọn delay đủ cho handler/test và đọc response đến hết trước khi stop. |
| File tạm không xóa được trên Windows | File handler hoặc worker vẫn đang sử dụng file. | Stop server, chờ executor kết thúc rồi mới xóa root. |
| Handler vẫn chạy sau stop | Stop đóng connection nhưng không bảo đảm dừng code handler. | Shutdown executor có timeout; thiết kế handler phản hồi interrupt và timeout I/O. |
| Gọi stop từ handler làm chậm response | Stop chờ exchange hiện tại, bao gồm exchange đang gọi nó. | Gọi stop từ thread điều phối sau khi handler/test hoàn tất. |
| Gọi stop với delay âm | Tham số không hợp lệ. | Chỉ truyền số giây không âm. |
| Cố start lại server đã stop | HttpServer đã dừng không thể tái sử dụng. | Tạo instance mới cho test/lifecycle tiếp theo. |
| Shutdown executor dùng chung quá sớm | Executor còn được server/thành phần khác sử dụng. | Chỉ shutdown tại nơi sở hữu lifecycle hoặc sau khi mọi consumer kết thúc. |
| Dùng delay rất dài để che handler treo | Handler không có timeout hoặc không hoàn tất. | Sửa handler, thêm timeout và cancellation hợp tác. |

## 11. Checklist cleanup cho test tích hợp

Trước khi kết thúc test, kiểm tra thứ tự:

1. Response body của client đã được đọc hết nếu test cần xác minh nội dung.
2. Không còn request mới cần gửi đến server.
3. Gọi server.stop(delay) để ngừng nhận request và chờ exchange hiện tại trong giới hạn.
4. Nếu test tạo ExecutorService, gọi shutdown().
5. Chờ awaitTermination() trong thời gian hữu hạn; dùng shutdownNow() khi quá hạn.
6. Chỉ xóa root directory sau khi server và worker đã ngừng sử dụng nó.
7. Nếu dùng executor chia sẻ, để chủ sở hữu của executor quyết định thời điểm shutdown.
8. Tạo server và thư mục mới cho test tiếp theo; không tái sử dụng HttpServer đã stop.

Với test framework, đặt logic này trong @AfterEach, @AfterAll hoặc một fixture có close() tùy phạm vi tài nguyên. Bảo đảm cleanup được đăng ký ngay sau khi tài nguyên được tạo để test thất bại giữa chừng vẫn có thể dọn phần đã tạo.

## 12. Câu hỏi tự kiểm tra

1. HttpServer.stop(delay) đóng những tài nguyên nào?
2. delay được tính theo đơn vị nào?
3. Điều gì khác nhau giữa stop(0) và stop(2)?
4. Khi hết delay mà exchange vẫn chưa hoàn tất, điều gì xảy ra?
5. Vì sao stop không thay thế ExecutorService.shutdown()?
6. Vì sao nên gọi stop trước khi shutdown executor?
7. Vì sao không nên gọi stop từ chính handler đang xử lý exchange?
8. Tại sao test nên dùng cổng 0 và địa chỉ loopback?
9. Vì sao cần dừng server và chờ worker trước khi xóa thư mục tạm?
10. HttpServer có thể start lại sau khi stop không?
11. Nếu executor được chia sẻ với thành phần khác, ai nên shutdown nó?
12. Vì sao tăng delay không giải quyết được handler bị treo vô hạn?

**Bài thực hành:** chạy StopServerAfterTest, quan sát response hoàn tất trước khi chương trình dọn thư mục tạm. Thử thay server.stop(2) bằng server.stop(0) trong một test gửi request chậm; quan sát khả năng response bị ngắt. Thử gọi setExecutor và start trên một server mới, rồi kiểm tra không thể tái sử dụng instance đã stop. Khôi phục delay hữu hạn phù hợp và giữ cleanup trong finally.

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — HttpServer.stop(int)](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): đóng listening socket, chờ exchange hiện tại tối đa delay giây và đóng TCP connections.
- [Oracle JDK 18 — HttpServer.stop(int)](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): hợp đồng stop(delay) có từ Java 18.
- [Oracle JDK 27 — ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown, shutdownNow và awaitTermination.
- [Oracle JDK 27 — HttpExchange](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): kết thúc exchange và đóng request/response streams.
- [Oracle JDK 27 — Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html): tạo thư mục tạm, duyệt và xóa file trong test.
- [Oracle JDK 27 — HttpClient](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html): gửi request và nhận response khi kiểm thử server.
