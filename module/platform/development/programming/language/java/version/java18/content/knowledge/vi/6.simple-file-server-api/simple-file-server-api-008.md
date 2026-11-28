# `createFileHandler()`: tái sử dụng trình phục vụ tệp trong một `HttpServer` tự cấu hình

> **Chương:** API SimpleFileServer  
> **Module học:** `JAVA_VERSION_JAVA18` — `SimpleFileServer` được bổ sung từ Java 18; các API HTTP server nền tảng được dùng cùng vẫn còn áp dụng trên JDK hiện đại.  
> **Mục tiêu:** Tạo một file handler độc lập, gắn nó vào `HttpContext` của `HttpServer` do ứng dụng quản lý, kết hợp endpoint khác và filter, đồng thời hiểu rõ giới hạn của handler có sẵn.

## 1. `createFileHandler()` trả về gì?

`SimpleFileServer.createFileHandler(Path rootDirectory)` là static factory method trả về một đối tượng kiểu **`HttpHandler`**:

```java
HttpHandler fileHandler =
        SimpleFileServer.createFileHandler(rootDirectory);
```

Handler này phục vụ tệp và danh sách thư mục từ `rootDirectory`. Khi xử lý request, nó phân giải URI của request đối với thư mục gốc để xác định tài nguyên cần phục vụ:

- Nếu tài nguyên là **tệp**, response có header `Content-Type` được suy đoán từ MIME table của hệ thống và body chứa nội dung tệp.
- Nếu tài nguyên là **thư mục**, response body chứa danh sách thư mục được định dạng HTML.
- Handler chỉ hỗ trợ hai phương thức **`GET`** và **`HEAD`**. Phương thức khác nhận status **`405 Method Not Allowed`**.

Điều quan trọng là factory này chỉ tạo **handler**. Nó không tạo socket, không bind địa chỉ/cổng, không đăng ký `HttpContext`, không chọn executor và không gọi `start()`. Các việc đó thuộc về ứng dụng dùng handler.

Nếu ứng dụng dùng named module, khai báo phụ thuộc:

```java
module demo.files {
    requires jdk.httpserver;
}
```

`HttpHandler` là functional interface với phương thức `handle(HttpExchange)`. Khi gắn vào context, server gọi handler này cho từng exchange được định tuyến đến context đó.

## 2. Hợp đồng đầu vào và ngoại lệ

Chữ ký API:

```java
public static HttpHandler createFileHandler(Path rootDirectory)
```

`rootDirectory` phải đồng thời:

1. Là đường dẫn tuyệt đối.
2. Tồn tại.
3. Là một thư mục.
4. Đọc được bởi tiến trình JVM.

Nếu vi phạm một trong các điều kiện trên, factory ném `IllegalArgumentException`. Nếu đối số là `null`, factory ném `NullPointerException`.

Ví dụ chuẩn bị:

```java
Path root = Path.of("public").toAbsolutePath().normalize();
if (!Files.isDirectory(root) || !Files.isReadable(root)) {
    throw new IllegalArgumentException("Thư mục public không hợp lệ: " + root);
}

HttpHandler fileHandler = SimpleFileServer.createFileHandler(root);
```

`toAbsolutePath().normalize()` giúp chuyển đường dẫn tương đối thành tuyệt đối và chuẩn hóa các thành phần đường dẫn. Nó không tạo thư mục. Nếu `public` chưa tồn tại, cần tạo thư mục thử nghiệm trước hoặc sửa cấu hình. Kiểm tra trước giúp thông báo dễ hiểu, nhưng factory vẫn kiểm tra hợp đồng của chính nó khi tạo handler.

## 3. Ghép file handler vào `HttpServer` tự cấu hình

Luồng kết hợp:

```text
Ứng dụng chọn rootDirectory
          │
          ▼
SimpleFileServer.createFileHandler(root)
          │ trả về HttpHandler
          ▼
HttpServer.create(address, backlog)
          │
          ▼
server.createContext(path, fileHandler)
          │ trả về HttpContext
          ├── thêm Filter nếu cần
          ├── cấu hình Executor nếu cần
          ▼
server.start()
          │
          ▼
HTTP request ──► HttpContext ──► Filter chain ──► fileHandler
          │
          ▼
HTTP response
          │
          ▼
server.stop(delay) khi kết thúc
```

Ví dụ tối thiểu:

```java
Path root = Path.of("public").toAbsolutePath().normalize();
HttpHandler fileHandler = SimpleFileServer.createFileHandler(root);

HttpServer server = HttpServer.create(
        new InetSocketAddress(InetAddress.getLoopbackAddress(), 8080), 0);
HttpContext files = server.createContext("/", fileHandler);

server.start();
```

`HttpServer.create(address, 0)` tạo và bind server vào địa chỉ được chọn; giá trị backlog `0` yêu cầu dùng giá trị mặc định của hệ thống. Context `/` nhận các request mà không có context cụ thể hơn. Server chưa phục vụ request cho đến khi gọi `start()`.

Khác với `SimpleFileServer.createFileServer(...)`, đoạn mã trên cho ứng dụng quyền quyết định:

- Địa chỉ IP và cổng bind.
- Context path mà file handler được gắn vào.
- Các context khác như `/health/` hoặc `/api/`.
- Filter áp dụng cho từng context.
- Executor dùng để xử lý request.
- Thời điểm dừng server.

## 4. Ví dụ hoàn chỉnh: file handler, health endpoint và filter

Ví dụ sau tạo server HTTP tùy chỉnh với hai context:

- `/`: phục vụ nội dung tĩnh từ thư mục `public`.
- `/health/`: trả về `200 OK` và nội dung `OK`.

File context có một filter thêm response header và một output filter ghi log. Filter của context file không tự động áp dụng lên health context.

Lưu thành `CustomFileHandlerServer.java`:

```java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import com.sun.net.httpserver.SimpleFileServer.OutputLevel;

import java.io.IOException;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CustomFileHandlerServer {
    public static void main(String[] args) throws IOException {
        Path root = Path.of("public").toAbsolutePath().normalize();
        if (!Files.isDirectory(root) || !Files.isReadable(root)) {
            throw new IllegalArgumentException(
                    "Thư mục public không tồn tại hoặc không đọc được: " + root);
        }

        // Chỉ nghe trên loopback; cổng 0 để hệ điều hành cấp cổng khả dụng.
        InetSocketAddress address = new InetSocketAddress(
                InetAddress.getLoopbackAddress(), 0);
        HttpServer server = HttpServer.create(address, 0);

        // Handler do SimpleFileServer tạo, được gắn vào context do ứng dụng chọn.
        HttpContext files = server.createContext(
                "/", SimpleFileServer.createFileHandler(root));

        // Filter trước handler: thêm header cho response từ file context.
        files.getFilters().add(Filter.beforeHandler(
                "Add nosniff header",
                exchange -> exchange.getResponseHeaders()
                        .set("X-Content-Type-Options", "nosniff")));

        // Filter hậu xử lý: ghi log các exchange của context này.
        files.getFilters().add(SimpleFileServer.createOutputFilter(
                System.out, OutputLevel.INFO));

        // Endpoint riêng, không dùng file handler.
        server.createContext("/health/", exchange -> {
            byte[] body = "OK".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        try {
            server.start();
            InetSocketAddress bound = server.getAddress();
            InetAddress boundIp = bound.getAddress();
            String host = boundIp.getHostAddress();
            if (boundIp instanceof Inet6Address) {
                host = "[" + host + "]";
            }
            System.out.println("File root: " + root);
            System.out.println("Server URL: http://" + host + ":"
                    + bound.getPort() + "/");
            System.out.println("Nhấn Enter để dừng...");
            System.in.read();
        } finally {
            server.stop(1);
        }
    }
}
```

Tạo thư mục `public` và đặt `hello.txt` vào đó. Biên dịch và chạy bằng JDK 18 trở lên:

```bash
javac CustomFileHandlerServer.java
java CustomFileHandlerServer
```

Chương trình in ra URL dựa trên địa chỉ thực tế. Trong terminal khác, thay `<host>` và `<port>` bằng các giá trị trong URL được in:

```bash
curl -i "http://<host>:<port>/hello.txt"
curl -I "http://<host>:<port>/hello.txt"
curl -i -X POST "http://<host>:<port>/hello.txt"
curl -i "http://<host>:<port>/health/"
```

Nếu host là IPv6, giá trị được in đã có dấu ngoặc vuông, ví dụ `[0:0:0:0:0:0:0:1]`; giữ nguyên dấu ngoặc vuông khi thay vào URL.

Kết quả cần quan sát:

| Request | Context/handler | Kết quả |
| --- | --- | --- |
| `GET /hello.txt` | `/` → file handler | `200` nếu tệp tồn tại; body là nội dung tệp; có header `X-Content-Type-Options`. |
| `HEAD /hello.txt` | `/` → file handler | Trả headers tương ứng, không gửi response body. |
| `POST /hello.txt` | `/` → file handler | `405 Method Not Allowed`. |
| `GET /health/` | `/health/` → health handler | `200 OK`, body `OK`; không đi qua filter của file context. |

Nhấn Enter ở terminal chạy Java để gọi `server.stop(1)`. Nếu dùng PowerShell 5.1, gọi `curl.exe` thay cho `curl` nếu tên `curl` đang là alias.

## 5. Context path và cách định tuyến

`HttpContext` liên kết một URI path với một `HttpHandler`. Khi nhận request, `HttpServer` chọn context có path khớp dài nhất với request URI path. Việc so khớp phân biệt chữ hoa/chữ thường.

Trong ví dụ:

- Context `/` là fallback phục vụ tệp.
- Context `/health/` cụ thể hơn nên nhận `GET /health/` và các request con thuộc path đó.

Nên chọn context path có dấu `/` cuối khi muốn thể hiện một ranh giới thư mục, ví dụ `/static/`, `/assets/`, `/health/`. Điều này làm ý định định tuyến rõ ràng và tránh nhập nhằng với những path chỉ bắt đầu bằng cùng chuỗi ký tự.

Một `HttpServer` có thể có nhiều context và mỗi context có handler/filter riêng. Nếu không có context nào khớp, server trả `404`. Khi đặt file handler ở `/`, hầu hết request sẽ được xử lý bởi nó trừ khi có context cụ thể hơn.

## 6. Kết hợp file handler với handler khác

File handler có sẵn chỉ xử lý `GET` và `HEAD`. Nếu ứng dụng cần xử lý một phương thức khác, có thể tạo một handler kết hợp bằng `HttpHandlers.handleOrElse(...)`: predicate chọn handler tùy chỉnh, còn request khác được chuyển cho file handler.

Ví dụ, xử lý `OPTIONS` để công bố các method được hỗ trợ, còn lại dùng file handler:

```java
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpHandlers;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;

// Giả sử root và address đã được khai báo như trong ví dụ ở phần 4.
HttpHandler fileHandler = SimpleFileServer.createFileHandler(root);

HttpHandler combined = HttpHandlers.handleOrElse(
        request -> request.getRequestMethod().equals("OPTIONS"),
        exchange -> {
            exchange.getResponseHeaders().set("Allow", "GET, HEAD, OPTIONS");
            exchange.sendResponseHeaders(204, -1);
            exchange.close();
        },
        fileHandler);

HttpServer server = HttpServer.create(address, 0);
server.createContext("/", combined);
server.start();
```

Trong đoạn này:

- Request `OPTIONS` được xử lý bởi handler đầu tiên.
- Request `GET` hoặc `HEAD` đi qua `fileHandler`.
- Request `POST`, `PUT`, `DELETE` không khớp predicate sẽ đến file handler và nhận `405`.

`HttpHandlers.handleOrElse` không tự triển khai upload hoặc thay đổi tệp. Nếu cần `PUT`/ `POST`, ứng dụng phải tự kiểm tra đường dẫn, nội dung, kích thước, quyền ghi và các quy tắc nghiệp vụ trước khi lưu dữ liệu. Không nên ghép một handler ghi tệp tùy ý vào file server thử nghiệm mà không có các kiểm soát đó.

## 7. Thêm filter và executor theo nhu cầu

### Filter thuộc về context

Một filter được gắn vào danh sách `context.getFilters()` sẽ chạy với các exchange của context đó. Có thể dùng:

- `Filter.beforeHandler(...)`: xử lý trước handler, ví dụ thêm response header.
- `Filter.afterHandler(...)`: quan sát exchange sau khi handler xử lý, ví dụ ghi nhận status code.
- `SimpleFileServer.createOutputFilter(...)`: ghi log hậu xử lý của các exchange đi qua context.

Filter `afterHandler` phù hợp để quan sát trạng thái. Không nên gửi response mới hoặc thay response headers tại thời điểm đó, vì handler có thể đã gửi response. Filter log được thêm vào file context không tự động log health context.

### Executor do ứng dụng quản lý

Nếu muốn chủ động chọn cách thực thi request, cấu hình `Executor` trước khi gọi `start()`:

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
server.setExecutor(executor); // Trước server.start()
server.start();

try {
    System.in.read();
} finally {
    server.stop(1);
    executor.shutdown();
}
```

Đây là phần bổ sung cho ví dụ server; cần import `java.util.concurrent.ExecutorService` và `java.util.concurrent.Executors`. Không cần đặt executor riêng nếu cơ chế mặc định của `HttpServer` đáp ứng nhu cầu thử nghiệm. Nếu ứng dụng tự tạo executor, phải đóng nó trong lifecycle khi server dừng.

## 8. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Handler được tạo nhưng không nhận request | Chưa gắn handler vào `HttpContext` hoặc server chưa `start()`. | Gọi `server.createContext(path, fileHandler)`, sau đó `server.start()`. |
| `IllegalArgumentException` tại `createFileHandler` | Root không tuyệt đối, không tồn tại, không phải thư mục hoặc không đọc được. | Chuẩn hóa path và kiểm tra `Files.isDirectory`/`Files.isReadable`. |
| `NullPointerException` tại factory | Truyền `null` làm root. | Truyền `Path` hợp lệ. |
| Request file trả `404` | Tệp không tồn tại dưới root, URI không đúng hoặc context không được chọn như dự định. | Kiểm tra root, URL và context path. |
| `POST`/`PUT` trả `405` | File handler chỉ hỗ trợ `GET`/`HEAD`. | Dùng handler tùy chỉnh hoặc kết hợp qua `HttpHandlers.handleOrElse`. |
| Không thấy filter log ở endpoint khác | Filter chỉ được gắn cho một context. | Gắn filter vào context cần quan sát. |
| Executor không hoạt động như dự kiến | Cấu hình sau khi server đã start hoặc executor đã shutdown. | Gọi `setExecutor` trước `start()`; quản lý vòng đời executor. |
| Log/tệp nhạy cảm bị tải qua HTTP | Đặt log hoặc dữ liệu riêng trong root được phục vụ. | Chỉ phục vụ thư mục public riêng; lưu log bên ngoài root. |

## 9. Ranh giới sử dụng an toàn

`SimpleFileServer` được JDK mô tả là công cụ cho **testing, development và debugging**. `createFileHandler` giúp tái sử dụng chức năng phục vụ tệp, nhưng không tự cung cấp toàn bộ yêu cầu của một dịch vụ web production:

- Không có upload hoặc sửa/xóa tệp qua các method `POST`/`PUT`/`DELETE`.
- Không tự thêm cơ chế xác thực/phân quyền nghiệp vụ cho các tài nguyên.
- Không biến HTTP thành HTTPS; nếu cần TLS phải cấu hình HTTPS server riêng.
- Directory listing có thể để lộ tên tệp và cấu trúc thư mục; chỉ phục vụ root được chủ động chọn.
- Filter có thể ghi URL, headers hoặc đường dẫn tuyệt đối; tránh log credential và dữ liệu riêng.

Ưu tiên bind loopback khi thử nghiệm trên máy cá nhân. Không dùng thư mục home, source code, thư mục chứa secret hoặc dữ liệu khách hàng làm root. Nếu cần phục vụ tài nguyên trong production, hãy chọn web server/framework phù hợp và thiết kế xác thực, phân quyền, TLS, giới hạn request và logging theo yêu cầu ứng dụng.

## 10. Câu hỏi tự kiểm tra

1. `createFileHandler(root)` trả về kiểu gì? Vì sao gọi factory không làm server bắt đầu lắng nghe?
2. Bốn điều kiện của `rootDirectory` là gì? Ngoại lệ nào xảy ra khi root không hợp lệ hoặc null?
3. Khác biệt giữa `createFileServer(...)` và `createFileHandler(...)` trong cách ứng dụng quản lý server/context?
4. Vì sao file handler trả directory listing HTML khi URI tương ứng với thư mục?
5. File handler xử lý những method nào? Làm thế nào kết hợp một handler tùy chỉnh cho `OPTIONS`?
6. Vì sao filter thêm vào `files.getFilters()` không tự động áp dụng cho context `/health/`?
7. `HttpServer` chọn context nào khi nhiều path cùng khớp request?
8. Vì sao chỉ nên chọn một thư mục public riêng để phục vụ qua HTTP?

**Bài thực hành:** chạy `CustomFileHandlerServer`; gửi `GET`, `HEAD`, `POST` tới `/hello.txt` và `GET /health/`. Quan sát status, headers, body và log. Sau đó bỏ output filter, thêm lại filter vào health context và so sánh log. Cuối cùng thử `HttpHandlers.handleOrElse` để tự xử lý `OPTIONS`, giữ file handler làm fallback.

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — `SimpleFileServer.createFileHandler`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): hợp đồng file handler, ánh xạ request URI, directory listing, MIME type, method `GET`/`HEAD` và ngoại lệ.
- [Oracle JDK 27 — `HttpServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): tạo server, `createContext`, định tuyến path, executor, `start()` và `stop()`.
- [Oracle JDK 27 — `HttpContext`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): mối liên hệ handler/filter/context và danh sách filter.
- [Oracle JDK 27 — `HttpHandlers`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandlers.html): ghép handler theo điều kiện bằng `handleOrElse`.
- [Oracle JDK 18 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): API gốc được giới thiệu từ Java 18 và ví dụ tái sử dụng handler.
