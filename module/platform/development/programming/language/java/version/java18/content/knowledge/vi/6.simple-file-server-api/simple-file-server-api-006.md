# Dùng cổng 0 rồi đọc địa chỉ thực tế để tránh xung đột trong kiểm thử

> **Chương:** API SimpleFileServer  
> **Module học:** `JAVA_VERSION_JAVA18` — tập trung vào `SimpleFileServer` được bổ sung từ Java 18 và cách dùng các API mạng nền tảng còn áp dụng trên JDK hiện đại.  
> **Mục tiêu:** Dùng cổng `0` để hệ điều hành cấp một cổng khả dụng, lấy cổng thực tế từ `HttpServer.getAddress()`, xây URL cho client và quản lý vòng đời server trong kiểm thử tự động.

## 1. Vì sao không nên cố định cổng trong kiểm thử?

Một ví dụ đơn giản thường bind vào cổng cố định:

```java
InetSocketAddress address = new InetSocketAddress(
        InetAddress.getLoopbackAddress(), 8080);
HttpServer server = SimpleFileServer.createFileServer(
        address, rootDirectory, OutputLevel.INFO);
server.start();
```

Điều này dễ hiểu khi chạy thủ công, nhưng tạo ra một phụ thuộc môi trường trong kiểm thử:

- Cổng `8080` có thể đã được ứng dụng khác sử dụng.
- Nhiều test chạy song song có thể cùng cố bind vào một cổng.
- Một tiến trình cũ chưa dừng đúng cách có thể giữ cổng.
- Máy CI, máy lập trình viên và container có thể có dịch vụ nền khác nhau.

Khi cổng đã được sử dụng hoặc không thể bind, thao tác tạo server có thể thất bại do lỗi I/O (được bọc trong `UncheckedIOException` bởi factory của `SimpleFileServer`). Kết quả test khi đó phụ thuộc trạng thái máy chạy, dù mã xử lý request không có lỗi.

Giải pháp phù hợp cho server thử nghiệm là truyền **cổng `0`** vào `InetSocketAddress`. Đây là yêu cầu hệ điều hành chọn một cổng khả dụng khi socket bind. Sau khi factory tạo server, đọc cổng được cấp qua `server.getAddress().getPort()`.

## 2. Cổng 0 có nghĩa là gì?

Trong API socket của Java, cổng hợp lệ nằm trong khoảng từ `0` đến `65535`. Riêng **cổng `0` khi bind** có ý nghĩa đặc biệt: ứng dụng yêu cầu hệ điều hành tự chọn một cổng khả dụng. Server sau đó được gắn với cổng thực tế mà hệ điều hành cấp.

```java
InetAddress loopback = InetAddress.getLoopbackAddress();
InetSocketAddress address = new InetSocketAddress(loopback, 0);

HttpServer server = SimpleFileServer.createFileServer(
        address, rootDirectory, OutputLevel.NONE);

int actualPort = server.getAddress().getPort();
System.out.println("Cổng thực tế: " + actualPort);
```

Không được hiểu rằng server tiếp tục lắng nghe ở cổng `0`. Số `0` chỉ là yêu cầu cấp phát trong bước bind. **Cổng thực tế** có giá trị khác `0` và phải được lấy từ địa chỉ đã bind.

### Thời điểm đọc cổng thực tế

Với `SimpleFileServer.createFileServer(addr, rootDirectory, outputLevel)`, factory tạo và bind server, đăng ký context `/`, rồi trả về một `HttpServer` **chưa start**. Vì vậy có thể đọc địa chỉ ngay sau khi gọi factory, trước `server.start()`:

```java
HttpServer server = SimpleFileServer.createFileServer(
        address, root, OutputLevel.NONE);

InetSocketAddress boundAddress = server.getAddress();
int actualPort = boundAddress.getPort(); // Đã là cổng hệ điều hành cấp.

server.start(); // Chỉ sau bước này server mới bắt đầu phục vụ HTTP.
```

Đây là khác biệt quan trọng giữa **bind** và **start**:

1. Factory bind socket vào địa chỉ và cổng.
2. `getAddress()` cho biết địa chỉ socket server đang bind.
3. `start()` khởi động việc nhận và xử lý các HTTP exchange.

Nếu quên `start()`, việc đã nhận được một cổng thực tế không có nghĩa client đã có thể sử dụng file server.

## 3. Chọn loopback cùng cổng 0

Khi chỉ kiểm thử trên máy hiện tại, nên kết hợp cổng `0` với loopback tường minh:

```java
InetSocketAddress address = new InetSocketAddress(
        InetAddress.getLoopbackAddress(), 0);
```

Không nên rút gọn thành:

```java
new InetSocketAddress(0);
```

Constructor chỉ nhận cổng tạo địa chỉ **wildcard/any-local**. Nó có thể khiến server lắng nghe trên các giao diện mạng cục bộ phù hợp. Cổng `0` chỉ giải quyết xung đột số cổng; nó **không** giới hạn phạm vi truy cập mạng. Chọn loopback nếu nhu cầu là local-only.

`InetAddress.getLoopbackAddress()` có thể trả về IPv4 loopback hoặc IPv6 loopback. Nếu tạo URL từ địa chỉ đã bind, phải đặt địa chỉ IPv6 trong dấu ngoặc vuông:

| Địa chỉ được bind | Host trong URL |
| --- | --- |
| IPv4 loopback `127.0.0.1` | `127.0.0.1` |
| IPv6 loopback `::1` | `[::1]` |

Ví dụ URL:

```text
http://127.0.0.1:54321/hello.txt
http://[::1]:54321/hello.txt
```

Trong ví dụ, `54321` chỉ là số minh họa; không nên hard-code giá trị này. Dùng cổng và địa chỉ được server báo lại.

## 4. Ví dụ hoàn chỉnh: khởi chạy file server trên cổng do hệ điều hành cấp

Ví dụ sau tạo một thư mục tạm, ghi tệp thử nghiệm, tạo file server trên loopback với cổng `0`, lấy cổng thực tế, rồi gửi HTTP request bằng `java.net.http.HttpClient`. Phần cuối luôn dừng server và xóa thư mục tạm.

Lưu thành `EphemeralPortFileServerTest.java`:

```java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import com.sun.net.httpserver.SimpleFileServer.OutputLevel;

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

public class EphemeralPortFileServerTest {
    public static void main(String[] args) throws IOException, InterruptedException {
        Path root = Files.createTempDirectory("simple-file-server-")
                .toAbsolutePath().normalize();
        Files.writeString(root.resolve("hello.txt"), "Hello from test",
                StandardCharsets.UTF_8);

        InetAddress loopback = InetAddress.getLoopbackAddress();
        InetSocketAddress requestedAddress =
                new InetSocketAddress(loopback, 0);
        HttpServer server = null;

        try {
            // Factory bind socket ngay lúc tạo; server chưa start.
            server = SimpleFileServer.createFileServer(
                    requestedAddress, root, OutputLevel.NONE);

            // Đọc địa chỉ và cổng hệ điều hành đã cấp.
            InetSocketAddress bound = server.getAddress();
            InetAddress boundIp = bound.getAddress();
            int actualPort = bound.getPort();

            if (actualPort == 0 || boundIp == null
                    || !boundIp.isLoopbackAddress()) {
                throw new IllegalStateException(
                        "Địa chỉ bind không như mong đợi: " + bound);
            }

            // start() mới bắt đầu nhận request.
            server.start();

            // Tạo host đúng cú pháp cho IPv4 hoặc IPv6.
            String host = boundIp.getHostAddress();
            if (boundIp instanceof Inet6Address) {
                host = "[" + host + "]";
            }
            URI uri = URI.create(
                    "http://" + host + ":" + actualPort + "/hello.txt");

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .GET()
                    .build();
            HttpResponse<String> response = HttpClient.newHttpClient().send(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

            if (response.statusCode() != 200
                    || !response.body().equals("Hello from test")) {
                throw new AssertionError(
                        "HTTP response không đúng: " + response.statusCode()
                                + ", body=" + response.body());
            }

            System.out.println("Địa chỉ đã bind: " + bound);
            System.out.println("URL kiểm thử: " + uri);
            System.out.println("HTTP " + response.statusCode()
                    + " - " + response.body());
        } finally {
            // Giải phóng socket trước khi xóa dữ liệu trên đĩa.
            if (server != null) {
                server.stop(0);
            }
            try (var paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Biên dịch và chạy trên JDK 18 trở lên:

```bash
javac EphemeralPortFileServerTest.java
java EphemeralPortFileServerTest
```

Kết quả có dạng:

```text
Địa chỉ đã bind: localhost/127.0.0.1:54321
URL kiểm thử: http://127.0.0.1:54321/hello.txt
HTTP 200 - Hello from test
```

Địa chỉ và cổng trong kết quả phụ thuộc hệ điều hành, không cố định. Nếu JDK chọn IPv6, URL sẽ có dạng `http://[...]:<port>/hello.txt`. Ví dụ kiểm tra đồng thời ba điều:

- `actualPort != 0`: hệ điều hành đã cấp một cổng cụ thể.
- `boundIp.isLoopbackAddress()`: server được giới hạn ở loopback.
- HTTP response có status `200` và body đúng: server thực sự phục vụ được nội dung.

## 5. Vì sao cách dò cổng rảnh trước đó không an toàn?

Một số test cũ thử tìm cổng trống bằng cách tạo một socket tạm:

```java
// Anti-pattern: minh họa cách làm có race condition.
int port;
try (java.net.ServerSocket probe = new java.net.ServerSocket(0)) {
    port = probe.getLocalPort();
}

// Sau khi probe đóng, cổng có thể bị tiến trình khác chiếm
// trước khi HttpServer bind vào port vừa lấy.
HttpServer server = SimpleFileServer.createFileServer(
        new InetSocketAddress(InetAddress.getLoopbackAddress(), port),
        root, OutputLevel.NONE);
```

Vấn đề nằm ở khoảng thời gian giữa **đóng socket dò cổng** và **bind server thật**:

1. Test A mở socket tạm, hệ điều hành cấp cổng `54321`.
2. Test A đọc cổng rồi đóng socket tạm.
3. Một tiến trình khác có thể bind `54321`.
4. Test A tạo HTTP server với cổng `54321` và gặp lỗi bind.

Đây là một dạng **time-of-check to time-of-use (TOCTOU)**. Việc dò cổng cho biết cổng rảnh tại thời điểm kiểm tra, nhưng không giữ quyền sở hữu cổng sau khi socket dò đã đóng.

Với `SimpleFileServer`, cách trực tiếp hơn là để chính server bind với port `0`, sau đó đọc `server.getAddress().getPort()`. Socket thật đã chiếm cổng được cấp và tiếp tục giữ nó trong thời gian server tồn tại. Không có khoảng hở giữa một socket dò và socket server cần kiểm thử.

## 6. Dùng port 0 trong kiểm thử song song

Giả sử có nhiều test cùng cần một file server:

| Test | Cổng cố định | Cổng `0` |
| --- | --- | --- |
| Test A | Cố bind `8080` | OS cấp cổng A |
| Test B | Cũng cố bind `8080`, có thể thất bại | OS cấp cổng B khác khi A vẫn đang bind |
| Test C | Có thể xung đột với A/B hoặc dịch vụ khác | OS tiếp tục cấp cổng khả dụng |

Khi từng server giữ socket của mình, các bind cùng địa chỉ loopback không thể đồng thời chiếm cùng một cặp IP/cổng. Vì thế port `0` rất phù hợp với test chạy song song, test lặp lại và môi trường CI.

Một số quy tắc để test ổn định:

1. **Tạo server thật với port 0** thay vì tự dò cổng rồi đóng socket.
2. Đọc cổng qua `server.getAddress().getPort()` sau factory và trước hoặc sau `start()`; không lưu một cổng minh họa trong cấu hình test.
3. Gọi `server.start()` trước khi gửi request.
4. Dùng đúng host cùng họ IP với địa chỉ bind; với IPv6 cần dấu ngoặc vuông trong URL.
5. Luôn gọi `server.stop(delay)` trong `finally` hoặc hook teardown để giải phóng socket, kể cả khi assertion thất bại.
6. Dọn thư mục tạm sau khi server dừng để test không để lại tệp rác.

Port `0` không loại bỏ mọi lỗi hệ thống: hệ điều hành vẫn có thể hết tài nguyên/cổng khả dụng, hoặc thao tác bind vẫn bị từ chối. Nếu factory ném `UncheckedIOException`, hãy kiểm tra nguyên nhân gốc. Tuy nhiên, port `0` loại bỏ phần lớn xung đột do nhiều test cùng chọn một số cổng cố định.

### Đoạn teardown tối thiểu

Nếu framework test tự quản lý thư mục tạm, phần quan trọng vẫn là dừng server:

```java
HttpServer server = SimpleFileServer.createFileServer(
        new InetSocketAddress(InetAddress.getLoopbackAddress(), 0),
        root, OutputLevel.NONE);
try {
    int port = server.getAddress().getPort();
    server.start();
    // Gửi request và assert tại đây.
} finally {
    server.stop(0);
}
```

Trong JUnit hoặc framework tương tự, đặt đoạn tạo server ở setup và `server.stop(0)` ở teardown/`@AfterEach`. Nếu test dùng thư mục tạm, để framework quản lý vòng đời thư mục nhưng bảo đảm server đã dừng trước khi framework xóa nội dung.

## 7. Các lỗi thường gặp khi dùng port 0

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| URL được tạo vẫn chứa `:0` | Dùng cổng yêu cầu ban đầu thay vì địa chỉ sau bind. | Đọc `server.getAddress().getPort()`. |
| Server tạo thành công nhưng client không kết nối được | Chưa gọi `server.start()`, hoặc client dùng sai host/port. | Gọi start; dùng host loopback và cổng thực tế. |
| Dùng `0.0.0.0` hoặc `::` làm host URL | Nhầm wildcard bind address với địa chỉ đích client. | Dùng loopback/IP cụ thể làm host client. |
| Client IPv4 không kết nối được server chỉ bind IPv6 loopback | Hai họ địa chỉ khác nhau. | Dùng host IPv6 có ngoặc vuông hoặc bind IPv4 loopback. |
| Test vẫn thất bại do lỗi bind | Hết tài nguyên, quyền bind hoặc lỗi môi trường socket. | Kiểm tra nguyên nhân của `UncheckedIOException`; port 0 không đảm bảo mọi bind đều thành công. |
| Cổng vẫn bị chiếm sau test | Không dừng server ở nhánh lỗi/assertion. | Đặt `server.stop(0)` trong `finally`/teardown. |
| Cổng thay đổi mỗi lần chạy | Đây là hành vi mong đợi của port 0. | Không assert số cổng cụ thể; chỉ kiểm tra cổng khác 0 và request thành công. |

## 8. Những giới hạn cần nhớ

- **Port 0 không phải cổng dịch vụ cố định:** phù hợp cho kiểm thử và server tạm thời; nếu một client bên ngoài cần biết trước cổng, hãy dùng cấu hình cổng cố định phù hợp với môi trường triển khai.
- **Port 0 không giới hạn địa chỉ mạng:** luôn chọn loopback nếu chỉ cần local-only. Cổng ngẫu nhiên không phải cơ chế bảo mật.
- **Port 0 không tự start server:** vẫn cần gọi `start()` sau khi tạo và cấu hình.
- **Không nên giả định cổng cụ thể hoặc dải cổng cụ thể:** hệ điều hành quản lý việc cấp phát. Chỉ dùng giá trị được đọc từ server.
- **Server phải được dừng:** port chỉ được giải phóng khi socket server đóng. Dùng `stop(delay)` trong `finally` hoặc hook teardown.
- **SimpleFileServer vẫn phục vụ nội dung thư mục đã chọn:** dùng thư mục thử nghiệm riêng, không trỏ tới dữ liệu nhạy cảm. Đây là công cụ testing/development/debugging, không phải web server production đầy đủ.

## 9. Câu hỏi tự kiểm tra

1. Khi truyền port `0` vào `InetSocketAddress`, hệ điều hành được yêu cầu làm gì?
2. Vì sao có thể đọc `server.getAddress().getPort()` ngay sau `createFileServer(...)` mà chưa cần gọi `start()`?
3. Vì sao URL client không được chứa cổng `0`?
4. Sự khác nhau giữa `new InetSocketAddress(0)` và `new InetSocketAddress(InetAddress.getLoopbackAddress(), 0)` là gì?
5. Tại sao cách tạo `ServerSocket(0)`, đọc cổng, đóng socket rồi bind HTTP server vào cổng đó vẫn có race condition?
6. Vì sao nhiều test song song có thể dùng port 0 mà không cần cấu hình mỗi test một cổng cố định?
7. Nếu server bind IPv6 loopback, URL HTTP cần biểu diễn host như thế nào?
8. Vì sao phải gọi `server.stop(0)` trong `finally`, kể cả khi test assertion thất bại?

**Bài thực hành:** chạy `EphemeralPortFileServerTest` nhiều lần liên tiếp và quan sát cổng thay đổi. Sau đó chạy hai instance đồng thời, xác minh mỗi instance có cổng riêng, request đến đúng nội dung, và cả hai đều giải phóng socket khi dừng. Cuối cùng thay loopback bằng wildcard để quan sát khác biệt của `getAddress()`; khôi phục loopback sau khi thử.

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — `InetSocketAddress`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/InetSocketAddress.html): constructor, phạm vi cổng và cách biểu diễn cổng được yêu cầu.
- [Oracle JDK 27 — `HttpServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): `getAddress()`, bind, `start()`, `stop(delay)`.
- [Oracle JDK 27 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): factory tạo file server, địa chỉ bind và trạng thái chưa start.
- [Oracle JDK 27 — `InetAddress`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/InetAddress.html): loopback, any-local, địa chỉ IPv4/IPv6.
- [Oracle JDK 27 — `HttpClient`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html): gửi request HTTP trong ví dụ kiểm thử tích hợp.
