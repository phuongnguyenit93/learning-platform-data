# Module `jdk.httpserver` và các API công khai trong `com.sun.net.httpserver`

> **Chương:** API SimpleFileServer  
> **Phạm vi:** Java 18 trở lên, tập trung vào những API vẫn có trong JDK hiện đại. `SimpleFileServer`, `HttpHandlers` và công cụ `jwebserver` được bổ sung từ Java 18; module `jdk.httpserver` và các thành phần HTTP server nền tảng đã tồn tại trước đó.

## 1. Vì sao cần hiểu module `jdk.httpserver`?

Khi phát triển ứng dụng Java, đôi khi ta chỉ cần phục vụ một thư mục HTML/CSS/JavaScript để thử giao diện, chia sẻ tệp trong máy phát triển, hoặc tạo một HTTP endpoint nhỏ để kiểm tra tích hợp. Java 18 cung cấp `SimpleFileServer` để thực hiện các tình huống này với ít mã hơn, dựa trên những API HTTP server sẵn có trong JDK.

Các thành phần đó nằm trong **module `jdk.httpserver`**:

- `com.sun.net.httpserver`: các kiểu công khai để nhận yêu cầu HTTP/HTTPS, định tuyến, xử lý request/response, tạo file server, ghép handler và thêm filter.
- `com.sun.net.httpserver.spi`: **Service Provider Interface (SPI)**, chủ yếu dùng khi cần cung cấp một triển khai HTTP server tùy biến thông qua `HttpServerProvider`.

Đây là **API đặc thù của JDK**, không phải một phần của tập API Java SE tiêu chuẩn. Dù tên package bắt đầu bằng `com.sun`, hai package trên được module `jdk.httpserver` **export công khai**. Với chúng, ứng dụng không cần sử dụng `--add-exports` để vượt qua cơ chế đóng gói module. Không nên đánh đồng các API được export này với những lớp nội bộ `sun.*` hoặc `jdk.internal.*`.

> **Chọn đúng công cụ:** `SimpleFileServer` và `jwebserver` được thiết kế cho **thử nghiệm, phát triển và gỡ lỗi**. Chúng không thay thế máy chủ ứng dụng hoặc giải pháp phục vụ nội dung có kiểm soát truy cập, bảo mật và vận hành đầy đủ cho production.

## 2. Khai báo phụ thuộc và cách tra cứu API

Nếu ứng dụng là **named module** (có `module-info.java`), khai báo:

```java
module demo.fileserver {
    requires jdk.httpserver;
}
```

Các class trong named module phải thuộc package có tên; đây chỉ là ví dụ về module descriptor. Trong ứng dụng chạy trên classpath truyền thống, có thể import trực tiếp các API từ `com.sun.net.httpserver` khi dùng JDK có module này.

Có thể kiểm tra JDK đang sử dụng:

```bash
java --list-modules
javap --module jdk.httpserver com.sun.net.httpserver.SimpleFileServer
```

Lệnh thứ nhất liệt kê các module khả dụng; tìm `jdk.httpserver`. Lệnh thứ hai hiển thị chữ ký API của `SimpleFileServer` trên đúng JDK đang chạy. Các bản runtime tự đóng gói bằng `jlink` có thể không chứa module này nếu nhà phát triển không đưa nó vào image.

## 3. Bản đồ các API công khai

Để đọc Javadoc dễ hơn, hãy phân biệt **server** (nhận kết nối), **context** (ghép đường dẫn), **handler** (xử lý yêu cầu), **exchange** (một lượt request/response) và **filter** (xử lý trước/sau handler).

| Thành phần | Vai trò và trường hợp sử dụng |
| --- | --- |
| `HttpServer` | Tạo và quản lý máy chủ HTTP; cấu hình địa chỉ, `HttpContext`, `Executor`; gọi `start()`/`stop(int)`. |
| `HttpsServer`, `HttpsConfigurator`, `HttpsParameters`, `HttpsExchange` | Các phần mở rộng cho HTTPS/TLS; phải cấu hình TLS phù hợp. `SimpleFileServer` **không** tự tạo HTTPS server. |
| `HttpContext` | Gắn một URI path với `HttpHandler`, danh sách filter và cấu hình cho context. |
| `HttpHandler` | Functional interface thực hiện `handle(HttpExchange)` để xử lý một lượt trao đổi HTTP. |
| `HttpExchange` | Đọc phương thức, URI, header, request body; đặt response header, status code và ghi response body. |
| `Headers` | Tập header HTTP; `getFirst`, `set`, `add` thuận tiện khi đọc/ghi header. |
| `Request` | Giao diện quan sát trạng thái request; dùng trong các predicate của `HttpHandlers` và `Filter.adaptRequest`. |
| `HttpHandlers` | Ghép các handler bằng `handleOrElse(...)`; tạo phản hồi tĩnh bằng `of(...)`. |
| `Filter` | Thêm thao tác trước/sau handler, ví dụ ghi log hoặc gắn response header; có `beforeHandler`, `afterHandler`, `adaptRequest`. |
| `Authenticator`, `BasicAuthenticator`, `HttpPrincipal` | Các thành phần xác thực của HTTP server API; cần chủ động cấu hình nếu ứng dụng cần xác thực. |
| `SimpleFileServer` | Tạo file server hoàn chỉnh, file handler hoặc logging filter từ các API sẵn có. |
| `SimpleFileServer.OutputLevel` | Điều khiển mức log: `NONE`, `INFO`, `VERBOSE`. |

`com.sun.net.httpserver.spi.HttpServerProvider` nằm ở package SPI được export riêng. Ứng dụng thông thường dùng provider mặc định thông qua `HttpServer.create(...)`, không cần tự triển khai SPI.

Luồng xử lý tổng quát:

```text
HTTP client
    │ request
    ▼
HttpServer ── tìm HttpContext khớp URI path
    │
    ▼
Các Filter gắn với context (trước handler)
    │
    ▼
HttpHandler.handle(HttpExchange)
    │       └─ đọc request, gửi status/header/body
    ▼
Các Filter sau handler (nếu có)
    │
    ▼
HTTP response về client
```

Lưu ý `HttpServer` chọn context có **tiền tố path khớp dài nhất**, so khớp phân biệt chữ hoa/chữ thường. Chẳng hạn `/health` được ưu tiên hơn `/`, nhưng context `/api` cũng khớp đường dẫn `/apix`; nếu cần phạm vi `/api/`, hãy chọn path và kiểm tra đường dẫn cho phù hợp.

## 4. Ba factory method của `SimpleFileServer`

`SimpleFileServer` là `final class` cung cấp ba **static factory method** thay vì bắt buộc ứng dụng tự triển khai từng lớp:

| Phương thức | Kết quả | Khi dùng |
| --- | --- | --- |
| `createFileServer(InetSocketAddress, Path, OutputLevel)` | `HttpServer` | Muốn có máy chủ tệp dùng được ngay, có context `/` và log theo mức đã chọn. |
| `createFileHandler(Path)` | `HttpHandler` | Muốn tích hợp chức năng phục vụ tệp vào `HttpServer` và hệ thống route hiện có. |
| `createOutputFilter(OutputStream, OutputLevel)` | `Filter` | Muốn gắn log trao đổi HTTP cho một context cụ thể. |

Đối với cả `createFileServer` và `createFileHandler`, **`rootDirectory` phải là đường dẫn tuyệt đối, tồn tại, là thư mục và đọc được**. Nếu không, API ném `IllegalArgumentException`. Có thể chuyển một đường dẫn tương đối thành tuyệt đối bằng `Path.of("public").toAbsolutePath().normalize()`, nhưng vẫn phải tạo thư mục `public` trước.

### 4.1. Tạo file server trực tiếp

Tạo thư mục `public` cạnh nơi chạy chương trình và đặt file `index.html` vào đó. Lưu đoạn dưới đây trong `FileServerDemo.java`:

```java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import com.sun.net.httpserver.SimpleFileServer.OutputLevel;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.file.Path;

public class FileServerDemo {
    public static void main(String[] args) {
        Path root = Path.of("public").toAbsolutePath().normalize();
        InetSocketAddress address =
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 8000);

        HttpServer server =
                SimpleFileServer.createFileServer(address, root, OutputLevel.INFO);

        server.start(); // Factory trả về server CHƯA được khởi động.
        System.out.println("File server đã chạy trên cổng 8000");
    }
}
```

Biên dịch và chạy bằng **JDK 18 trở lên**:

```bash
javac FileServerDemo.java
java FileServerDemo
```

Từ một terminal khác, kiểm tra:

```bash
curl -i http://localhost:8000/index.html
curl -I http://localhost:8000/index.html
curl -i -X POST http://localhost:8000/index.html
```

Hai yêu cầu đầu dùng `GET` và `HEAD`. Yêu cầu cuối dùng `POST` nên file handler trả về **405 Method Not Allowed**. Nếu file không tồn tại, handler trả về lỗi phù hợp (thường là `404`). Khi URL trỏ đến thư mục, file handler có thể trả về **danh sách thư mục dạng HTML**: không nên mặc định rằng nó sẽ tự phục vụ `index.html` như một web server có cơ chế directory index riêng.

`OutputLevel.INFO` tạo log thông tin. `OutputLevel.VERBOSE` bổ sung request/response headers và đường dẫn tuyệt đối của tài nguyên; tránh bật verbose nếu header chứa dữ liệu nhạy cảm. `OutputLevel.NONE` làm `createFileServer` không tạo log. Lưu ý `createOutputFilter(...)` **không chấp nhận `OutputLevel.NONE`**; nếu không muốn log, đừng gắn filter.

### 4.2. Ghép file handler vào một server có endpoint riêng

Giả sử ta muốn đồng thời có đường dẫn `/` để duyệt tệp và `/health` để hệ thống kiểm tra trạng thái. Thay vì để factory tạo cả server, có thể tạo `HttpServer` rồi gắn các handler:

```java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpHandlers;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.file.Path;

public class ComposedServerDemo {
    public static void main(String[] args) throws IOException {
        Path root = Path.of("public").toAbsolutePath().normalize();
        var address = new InetSocketAddress(InetAddress.getLoopbackAddress(), 8000);
        HttpServer server = HttpServer.create(address, 0);

        HttpContext files = server.createContext(
                "/", SimpleFileServer.createFileHandler(root));
        files.getFilters().add(SimpleFileServer.createOutputFilter(
                System.out, SimpleFileServer.OutputLevel.INFO));
        files.getFilters().add(Filter.beforeHandler(
                "Add nosniff header",
                exchange -> exchange.getResponseHeaders()
                        .set("X-Content-Type-Options", "nosniff")));

        server.createContext("/health", HttpHandlers.of(
                200,
                Headers.of("Content-Type", "text/plain; charset=utf-8"),
                "OK"));

        server.start();
        System.out.println("Server đã chạy trên cổng 8000");
    }
}
```

Trong ví dụ này:

1. `HttpServer.create(address, 0)` khởi tạo server; `backlog = 0` để hệ thống dùng giá trị mặc định. Vẫn phải gọi `start()`.
2. `createContext("/", ...)` ghép một `HttpHandler` phục vụ thư mục vào path gốc.
3. `getFilters().add(...)` thêm **filter cho context `/`**. Filter log do `SimpleFileServer` cung cấp và filter tùy biến `beforeHandler` cùng chạy trong chuỗi của context đó.
4. `createContext("/health", ...)` tạo endpoint tĩnh trả về `200`, header `Content-Type` và nội dung `OK`. Context `/health` khớp cụ thể hơn `/` nên được chọn cho request có path `/health`.

Nếu muốn cùng một filter áp dụng cho nhiều context, phải gắn nó vào từng context tương ứng. Ví dụ trên chỉ gắn vào context phục vụ tệp, vì vậy log filter ấy không ghi request được xử lý bởi `/health`.

## 5. Tạo handler động và hiểu `HttpExchange`

Với endpoint cần tính toán phản hồi, có thể tự viết `HttpHandler` dưới dạng lambda. Đây là thành phần nền tảng dùng chung với `SimpleFileServer`:

```java
server.createContext("/time", exchange -> {
    if (!exchange.getRequestMethod().equals("GET")) {
        exchange.getResponseHeaders().set("Allow", "GET");
        exchange.sendResponseHeaders(405, -1);
        exchange.close();
        return;
    }

    byte[] body = java.time.Instant.now().toString()
            .getBytes(java.nio.charset.StandardCharsets.UTF_8);
    exchange.getResponseHeaders()
            .set("Content-Type", "text/plain; charset=utf-8");
    exchange.sendResponseHeaders(200, body.length);
    try (var out = exchange.getResponseBody()) {
        out.write(body);
    }
});
```

Đây là **đoạn mở rộng** để chèn vào `main` của ví dụ thứ hai, trước khi gọi `server.start()`. `HttpExchange` cho phép lấy request method, URI, headers, body và tạo HTTP response. Cần gửi status/response headers **trước** khi ghi response body; sau khi xử lý, đóng response stream hoặc exchange để giải phóng tài nguyên. Trong ví dụ, trả `405` có header `Allow` nếu phương thức khác `GET`.

Với `sendResponseHeaders(int status, long responseLength)`, độ dài dương xác định số byte phản hồi; `0` có ý nghĩa phản hồi truyền theo chunked encoding; `-1` nghĩa là không gửi response body. Do đó không sử dụng `0` với ý định gửi một body trống.

### `HttpHandlers` và `Request`

`HttpHandlers.of(status, headers, body)` tạo handler trả nội dung cố định; đây là lựa chọn ngắn gọn cho health check hoặc mock response. Nếu cần điều hướng theo điều kiện, `HttpHandlers.handleOrElse(predicate, a, b)` chọn handler `a` khi predicate trên `Request` trả `true`, ngược lại chọn `b`:

```java
var getOnly = HttpHandlers.handleOrElse(
        request -> request.getRequestMethod().equals("GET"),
        HttpHandlers.of(200, Headers.of("Content-Type", "text/plain"), "ready"),
        HttpHandlers.of(405, Headers.of("Allow", "GET"), ""));

server.createContext("/ready", getOnly);
```

`Request` mô tả trạng thái request để bộ lọc hoặc handler kiểm tra. `Headers.of(...)` trả về bộ headers **bất biến** để truyền vào `HttpHandlers.of`; ngược lại `exchange.getResponseHeaders()` trả về headers có thể chỉnh sửa **trước khi gửi response**.

## 6. Filter, logging và lifecycle

Các factory của `Filter` giúp bổ sung chức năng vào chuỗi xử lý mà không phải viết một subclass:

| API | Vị trí chạy | Công dụng điển hình |
| --- | --- | --- |
| `Filter.beforeHandler(description, operation)` | Trước handler hoặc filter tiếp theo | Thêm response header, kiểm tra thông tin request. |
| `Filter.afterHandler(description, operation)` | Sau khi handler/filter tiếp theo xử lý | Quan sát mã trạng thái để log, thống kê. |
| `Filter.adaptRequest(description, operator)` | Trước handler/filter tiếp theo | Tạo một góc nhìn request đã điều chỉnh, ví dụ bổ sung request header. |
| `SimpleFileServer.createOutputFilter(out, level)` | Sau handler | Ghi thông tin exchange ra `OutputStream` ở mức `INFO` hoặc `VERBOSE`. |

`Filter.afterHandler` thường phù hợp để **quan sát** trạng thái sau xử lý. Không nên sửa header hoặc cố gửi phản hồi mới tại đây, vì handler có thể đã gửi response. Với filter tự viết, việc gọi `chain.doFilter(exchange)` quyết định có tiếp tục chuỗi xử lý hay không; nếu chủ động dừng chuỗi, filter phải gửi phản hồi thích hợp cho client.

`HttpServer` có vòng đời rõ ràng: tạo server → đăng ký context/filter → (tùy chọn) đặt `Executor` → `start()` → `stop(delay)`. Nếu muốn server xử lý request song song, có thể cấu hình `Executor` **trước** khi `start()`; nếu không, server dùng executor mặc định. `stop(delay)` dừng nhận kết nối mới và chờ các exchange đang xử lý tối đa khoảng `delay` giây; server đã dừng **không thể khởi động lại**.

Một chi tiết cần chú ý khi đọc ví dụ cũ: kể từ **JDK 26**, các attribute của `HttpExchange` trong triển khai mặc định là riêng cho mỗi exchange, thay vì chia sẻ mặc định với `HttpContext` như trước. Muốn lưu dữ liệu dùng chung cho context, truy cập `exchange.getHttpContext().getAttributes()`; không dựa vào `exchange.setAttribute(...)` để truyền dữ liệu giữa các request khác nhau. Đây là hành vi phù hợp khi xây ứng dụng trên JDK hiện đại.

## 7. `jwebserver`: sử dụng file server không cần viết Java

Khi mục tiêu chỉ là thử một thư mục tệp tĩnh, CLI `jwebserver` trong module `jdk.httpserver` còn gọn hơn việc viết chương trình:

```bash
jwebserver -b 127.0.0.1 -p 8000 -d ./public -o info
```

Các tham số chính:

| Tham số | Ý nghĩa |
| --- | --- |
| `-b`, `--bind-address` | Địa chỉ lắng nghe; mặc định là loopback, phù hợp cho thử nghiệm cục bộ. |
| `-p`, `--port` | Cổng; mặc định `8000`. |
| `-d`, `--directory` | Thư mục phục vụ; mặc định thư mục làm việc hiện tại. |
| `-o`, `--output` | Mức log `none`, `info` hoặc `verbose`; mặc định `info`. |

Cũng có thể khởi chạy qua `java -m jdk.httpserver` với các tùy chọn tương ứng. Dừng server bằng `Ctrl+C`. CLI này sử dụng file server của JDK, không cung cấp API endpoint động hoặc cấu hình HTTP server phức tạp; dùng API Java khi cần ghép thêm `HttpContext`, `HttpHandler`, `Filter`.

## 8. Giới hạn và cách dùng an toàn

1. **Chỉ phục vụ nội dung nên công khai:** `SimpleFileServer` có thể hiển thị danh sách thư mục và phục vụ các tệp con. Hãy trỏ `rootDirectory` đến thư mục dành riêng cho nội dung thử nghiệm; đừng chọn thư mục chứa mã nguồn bí mật, khóa, token, tài liệu riêng hay toàn bộ thư mục người dùng.
2. **Giữ phạm vi truy cập cục bộ khi không cần chia sẻ:** dùng `InetAddress.getLoopbackAddress()` hoặc bind `127.0.0.1`. Bind `0.0.0.0` khiến service có thể được truy cập từ các giao diện mạng khác nếu mạng/tường lửa cho phép.
3. **Không mặc định có HTTPS hoặc xác thực:** `SimpleFileServer` là HTTP-only. Với dịch vụ cần TLS, dùng `HttpsServer` và cấu hình SSL/TLS đúng cách; với truy cập nhạy cảm, chọn kiến trúc máy chủ phù hợp cho môi trường triển khai.
4. **File handler hỗ trợ `GET` và `HEAD`:** các phương thức khác nhận `405`. Không dùng `SimpleFileServer` để kỳ vọng xử lý upload (`POST`/`PUT`), chỉnh sửa hoặc xóa tệp. Việc tạo handler tùy biến để xử lý phương thức khác phải kèm kiểm tra hợp lệ, phân quyền và giới hạn dữ liệu.
5. **Bảo vệ thông tin trong log:** `VERBOSE` có thể ghi request/response headers và đường dẫn tuyệt đối; kiểm tra kỹ dữ liệu được log. Không ghi log chi tiết vào nơi chia sẻ rộng.
6. **Phân biệt thử nghiệm với vận hành lâu dài:** API server của module được thiết kế tối giản, không nhắm tới các tính năng đầy đủ hoặc hiệu năng của web server production.

## 9. Câu hỏi tự kiểm tra

1. Vì sao package `com.sun.net.httpserver` có thể được sử dụng qua `requires jdk.httpserver` mà không cần `--add-exports`?
2. Phân biệt `HttpServer`, `HttpContext`, `HttpHandler` và `HttpExchange` bằng vai trò trong một request tới `/health`.
3. Khi nào nên dùng `SimpleFileServer.createFileServer(...)`, khi nào nên dùng `createFileHandler(...)`?
4. Tại sao `createOutputFilter(System.out, OutputLevel.NONE)` không phải cách tắt log hợp lệ?
5. Một server có hai context `/` và `/health`. Context nào nhận `GET /health`? Nếu cần chặn chính xác `/healthcheck`, cần lưu ý gì về khớp tiền tố?
6. Vì sao nên giới hạn bind address và thư mục gốc khi thử nghiệm `jwebserver`?

**Bài thực hành:** tạo một thư mục `public` chứa `hello.txt`; chạy `ComposedServerDemo`; dùng `curl` để quan sát `GET /hello.txt`, `HEAD /hello.txt`, `POST /hello.txt` và `GET /health`. Kiểm tra status code, header, response body và log; sau đó đổi `OutputLevel.INFO` thành `VERBOSE` để thấy mức chi tiết khác nhau (chỉ sử dụng dữ liệu thử nghiệm không nhạy cảm).

## Tài liệu chính thức

- [JDK 27 — Module `jdk.httpserver`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): danh sách package export, mục đích module và thay đổi hành vi attribute kể từ JDK 26.
- [JDK 27 — Package `com.sun.net.httpserver`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/package-summary.html): các API HTTP/HTTPS công khai.
- [JDK 27 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): ba factory method, hợp đồng đường dẫn, giới hạn phương thức HTTP.
- [JDK 27 — `HttpHandlers`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandlers.html): ghép handler và tạo phản hồi tĩnh.
- [JDK 27 — `HttpServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): lifecycle và quy tắc khớp path.
- [JDK 24 — tài liệu lệnh `jwebserver`](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jwebserver.html): tham số CLI được duy trì trên các bản JDK hiện đại.
