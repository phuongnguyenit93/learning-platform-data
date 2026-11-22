# HttpServer và module jdk.httpserver hiện hành trong Java

## 1. Mục tiêu và phạm vi

Khi cần một HTTP endpoint nhỏ cho công cụ nội bộ, health check, bài thực hành, môi trường tích hợp hay ứng dụng embedded, JDK cung cấp một HTTP server nhẹ mà không cần cài thêm servlet container. API này nằm trong **module `jdk.httpserver`**, package **`com.sun.net.httpserver`**. Dù tên package có `com.sun`, đây là **API public được tài liệu hóa trong module JDK**, khác với việc truy cập các internal classes như `sun.net.httpserver.*`.

Bài **“HttpServer và module jdk.httpserver hiện hành”** thuộc chủ đề **HTTP server gọn**. Nội dung trình bày:

1. Khi nào chọn `HttpServer` và giới hạn của implementation mặc định.
2. Vai trò module `jdk.httpserver` trong Java Platform Module System.
3. `HttpServer`, `HttpContext`, `HttpHandler`, `HttpExchange`, `Filter` và `Headers`.
4. Cách bind vào loopback, port động, đăng ký route và thiết lập executor.
5. Đọc request, trả response có UTF-8, status code, `Content-Type` và length chính xác.
6. Phân biệt response **fixed-length**, **chunked** và **không có body**.
7. Context matching theo **longest literal prefix** và các cạm bẫy path.
8. Cách đặt attributes đúng với **thay đổi JDK 26**.
9. Authentication cơ bản, HTTPS, giới hạn request và lưu ý đưa dịch vụ ra mạng.
10. `SimpleFileServer` / `jwebserver` để chia sẻ file **cho development/test**, không phải giải pháp host web production.
11. Một chương trình **Java 17+ thực sự mở server trên loopback**, dùng `java.net.http.HttpClient` gọi endpoint, tự kiểm tra **38/38 tình huống** rồi dừng server.
12. Checklist khi chuyển từ demo sang dịch vụ có yêu cầu bảo mật và vận hành.

**Special Note hiện hành:** Bài dùng API còn có trong Java SE 26. Không khuyên sử dụng internal `sun.net.httpserver.*`, applet hay các giải pháp legacy. Ví dụ tương thích Java 17, nhưng các thay đổi riêng JDK 26 được ghi rõ, không giả định JDK 17 đã có những API/constants mới hơn.

## 2. `jdk.httpserver` là module gì?

Trang module Java SE 26 mô tả `jdk.httpserver` là module **JDK-specific** cung cấp high-level HTTP server API và công cụ `jwebserver`.

```text
Java runtime (JDK)
|
+-- java.base
|     +-- java.net, java.io, java.util...
|
+-- java.net.http
|     +-- java.net.http.HttpClient  (HTTP CLIENT)
|
+-- jdk.httpserver
      +-- com.sun.net.httpserver.HttpServer
      +-- com.sun.net.httpserver.HttpsServer
      +-- com.sun.net.httpserver.HttpExchange
      +-- com.sun.net.httpserver.HttpHandler
      +-- com.sun.net.httpserver.HttpContext
      +-- com.sun.net.httpserver.Filter
      +-- com.sun.net.httpserver.BasicAuthenticator
      +-- com.sun.net.httpserver.SimpleFileServer
      +-- com.sun.net.httpserver.HttpHandlers
      +-- com.sun.net.httpserver.spi.HttpServerProvider
      +-- jwebserver CLI
```

Hai module cần phân biệt:

| Module | Vai trò | Các type tiêu biểu |
| --- | --- | --- |
| `jdk.httpserver` | **Nhận** TCP/HTTP requests và tạo server-side responses | `HttpServer`, `HttpExchange` |
| `java.net.http` | **Gửi** HTTP requests dưới dạng client | `HttpClient`, `HttpRequest`, `HttpResponse` |

Trong chương trình kiểm thử, một tiến trình dùng **cả hai**: `HttpServer` nhận requests tại localhost, còn `HttpClient` gửi requests tự động. Đó là lý do code có imports từ hai package khác nhau.

### 2.1. Module được cung cấp từ JDK nào?

Module `jdk.httpserver` được khai báo từ **Java 9**, bao bọc HTTP Server API từng có từ Java 6. Nó vẫn được tài liệu hóa trên Java SE 26.

Các tiện ích khác có version riêng:
- `HttpServer` / `HttpsServer`: API HTTP/HTTPS server được hỗ trợ lâu nay.
- `SimpleFileServer`, `HttpHandlers` và `jwebserver`: được giới thiệu trong **JDK 18**.
- `HttpExchange.RSPBODY_EMPTY` và `HttpExchange.RSPBODY_CHUNKED`: **symbolic constants giới thiệu trong JDK 26**. Với source target Java 17, dùng giá trị `-1` và `0` như contract đã quy định.
- Từ **JDK 26**, attribute maps của `HttpExchange` mặc định **theo từng exchange**, không còn chia sẻ trực tiếp với `HttpContext` như implementation trước đó. Đây là thay đổi cần chủ động nắm nếu nâng cấp JDK.

**Không nên trộn API mới với target 17** rồi kỳ vọng biên dịch. Ví dụ trong bài dùng các method có thể biên dịch `--release 17`; phần mô tả JDK 26 phản ánh API/docs hiện hành.

### 2.2. Dùng trên classpath

Với file `HttpServerModuleDemo.java` trong bài:

```bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 HttpServerModuleDemo.java
java --add-modules jdk.httpserver HttpServerModuleDemo
```

`--add-modules jdk.httpserver` là cách khai báo module có mặt trong graph khi biên dịch/chạy ở classpath. Trong nhiều cách chạy classpath với JDK đầy đủ module có thể đã tự resolve, nhưng dùng flag tường minh giúp môi trường test, build script và `jlink` dễ hiểu hơn.

### 2.3. Dùng trong named module (JPMS)

Nếu ứng dụng của bạn có `module-info.java`:

```java
module example.web {
    requires jdk.httpserver;
}
```

Đây là **snippet khai báo module**, không phải file chạy độc lập. Nếu chính named module cũng dùng `HttpClient`, thêm:

```java
module example.web {
    requires jdk.httpserver;
    requires java.net.http;
}
```

Trong một project modular, source classes phải nằm trong package có tên, không phải unnamed/default package như fixture học tập. Ví dụ có thể dùng package `example.web`, compile theo cấu trúc module và run bằng `java --module-path ... -m example.web/example.web.Main` sau khi build đúng source layout.

**Đừng viết `requires java.httpserver`** (module đó không tồn tại) hay `requires java.net.http` rồi kỳ vọng import `com.sun.net.httpserver.HttpServer` chạy được. Đúng module server là `jdk.httpserver`.

## 3. Khi nào nên và không nên dùng HttpServer?

### 3.1. Phù hợp

`HttpServer` phù hợp với:
- Local health/diagnostics endpoint được bảo vệ.
- Local integration test cho HTTP clients.
- Small embedded controls trong môi trường khép kín.
- Demo HTTP request/response và concurrency.
- Prototyping một API nhỏ không cần frameworks.
- Test harness tạo fake HTTP service nội bộ.

### 3.2. Không phải production reverse proxy / high-performance web server

Javadoc module Java SE 26 nói rõ implementation mặc định **dành cho những nhu cầu đơn giản như local test, development và debugging**, không phải full-featured high-performance HTTP server. Nó không tự cung cấp toàn bộ:
- Load balancing, sophisticated routing, rate limiting, request tracing.
- Service mesh/security policies.
- HTTP/2, HTTP/3 hay WebSocket server chuyên dụng.
- Servlet/Jakarta EE runtime.
- Full authentication/authorization/CSRF protections.
- TLS certificate lifecycle, automatic renewal, mTLS policy orchestration.
- Request body size/deadline limits theo business semantics.
- Production metrics, graceful rolling deployments, dynamic configuration.

**HttpServer có class `HttpsServer` riêng**, nhưng điều đó **không biến** `jwebserver` thành công cụ HTTPS. Công cụ `jwebserver` chỉ phục vụ file bằng **HTTP/1.1**, không hỗ trợ HTTPS hoặc HTTP/2 theo tài liệu chính thức.

Nếu server phải expose cho internet hoặc cần scale, chọn HTTP server/container/framework phù hợp; hoặc đặt sau gateway/reverse proxy có TLS, authentication, rate limiting và security controls, sau khi đánh giá cả ứng dụng.

## 4. Mô hình thành phần của `HttpServer`

```text
HTTP client
     |
     v
TCP listening socket (host:port)
     |
     v
HttpServer
     |
     +-- HttpContext "/health"
     |       |
     |       v
     |   HttpHandler -> HttpExchange
     |
     +-- HttpContext "/api/"
     |       |
     |       +-- Filter(s)
     |       |
     |       v
     |   HttpHandler -> HttpExchange
     |
     +-- HttpContext "/api/health"
     |       |
     |       v
     |   HttpHandler (more specific prefix)
     |
     +-- HttpContext "/private/"
             |
             +-- Authenticator
             |
             v
         HttpHandler
```

| Type | Công việc |
| --- | --- |
| `HttpServer` | Bind, listen, register contexts, set executor, start/stop |
| `HttpContext` | Mapping path prefix → handler, giữ filters/authenticator/context attributes |
| `HttpHandler` | Functional interface xử lý một `HttpExchange` |
| `HttpExchange` | Một chu kỳ request/response và request/response streams |
| `Headers` | Request/response headers (multi-valued map) |
| `Filter` | Xử lý trước/sau handler, gọi `chain.doFilter(exchange)` |
| `Authenticator` | Xác thực request trước khi vào handler |
| `BasicAuthenticator` | HTTP Basic auth tiện lợi (chỉ phù hợp trên TLS hoặc loopback demo) |
| `HttpsServer` | HTTP server có HTTPS/TLS, cần `HttpsConfigurator` |
| `HttpServerProvider` | SPI dùng để thay thế implementation mặc định |

Cần phân biệt **context path** với **HTTP method**. `createContext("/health", handler)` không tự giới hạn GET/POST; code handler phải kiểm tra method hoặc dùng conditional handler/filter/auth.

## 5. Tạo server, bind loopback và port động

### 5.1. Tạo server

```java
HttpServer server = HttpServer.create(
        new InetSocketAddress(
                InetAddress.getLoopbackAddress(), 0),
        16);
```

- `InetAddress.getLoopbackAddress()`: chỉ bind interface loopback, tránh vô tình expose test server trên LAN.
- `port = 0`: hệ điều hành chọn port còn trống; lấy port thật bằng `server.getAddress().getPort()`.
- `backlog = 16`: số kết nối đang chờ trong TCP accept backlog, **không** phải số request đồng thời mà ứng dụng được phép xử lý.
- `HttpServer.create()` không tham số tạo server chưa bind; sau đó có thể gọi `bind(...)`.
- `HttpServer.create(address, backlog)` bind lúc tạo, **chưa start**.

Dùng `new InetSocketAddress(8080)` thường bind mọi interface, không thích hợp cho demo chứa dữ liệu nhạy cảm. Nếu muốn an toàn mặc định, **bind cụ thể địa chỉ loopback** như trong fixture.

### 5.2. Lifecycle

```text
CREATE (unbound or bound)
    |
    +-- createContext(...)
    +-- context.getFilters().add(...)
    +-- setAuthenticator(...) if needed
    +-- setExecutor(...) before start
    |
    v
start()
    |
    v
Accept and handle exchanges
    |
    v
stop(delay)
    |
    v
STOPPED (cannot restart same HttpServer object)
```

`server.start()` tạo thread để nhận kết nối. `server.stop(delay)` ngừng nhận exchanges mới, chờ exchanges hiện tại hoàn tất hoặc khoảng delay seconds, rồi đóng các TCP connections. **Sau `stop` không thể khởi động lại cùng server instance**. Nếu muốn restart, tạo một `HttpServer` mới.

Nếu bạn tạo `ExecutorService` để cấp cho server thì phải chủ động `shutdown()`/`shutdownNow()` cho executor sau khi stop. `HttpServer.stop()` không phải API quản lý mọi resource do ứng dụng tự tạo.

## 6. Cấu hình executor và xử lý đồng thời

```java
ExecutorService workers = Executors.newFixedThreadPool(4);
server.setExecutor(workers);
server.start();
```

`HttpServer.setExecutor(Executor)` phải gọi **trước `start()`**. Nếu không chỉ định, implementation mặc định dùng thread do `start()` tạo để xử lý requests. Không nên mặc định giả định nó có một thread pool lớn.

### 6.1. Tại sao không dùng unlimited threads?

Mỗi request có thể chờ I/O (đọc body, database, service ngoài). Nếu hệ thống cho phép số requests/threads tăng vô hạn, sẽ dễ bị resource exhaustion.

Đối với một HTTP server nhỏ:
- Dùng executor có capacity phù hợp.
- Đặt số kết nối đồng thời ở ingress/gateway.
- Giới hạn request body.
- Hạn chế thời gian xử lý và các downstream calls.
- Dùng queue/rejection policy có kiểm soát.
- Xử lý shutdown/drain requests.

`Executors.newFixedThreadPool(4)` trong fixture chỉ đơn giản để bảo đảm test dùng executor riêng, không phải cấu hình production tối ưu. Factory này có task queue không giới hạn số phần tử một cách logic; khi có tải lớn cần hiểu backpressure và có thể dùng bounded executor/gateway.

### 6.2. Về virtual threads

Virtual threads là một lựa chọn hiện hành trên Java 21+ cho workloads blocking I/O, nhưng không nên bảo đảm `HttpServer` tự dùng virtual threads. Có thể truyền một `Executor` phù hợp trên runtime hỗ trợ, cần tự đánh giá giới hạn requests, shared-state concurrency và lifecycle. Ví dụ target Java 17 chọn fixed thread pool để biên dịch và chạy được.

## 7. Context matching: longest literal prefix

Theo Javadoc, `HttpServer` chọn context có **prefix dài nhất** so với request URI path. So khớp **literal**, phân biệt chữ hoa/thường, không tự decode/encode path khi chọn context.

Ví dụ đăng ký:

```java
server.createContext("/api/", apiHandler);
server.createContext("/api/health", specialHandler);
```

Kết quả:

| Request path | Handler được chọn | Vì sao |
| --- | --- | --- |
| `/api/items` | `/api/` | Prefix tồn tại |
| `/api/health` | `/api/health` | Prefix dài hơn |
| `/api/HEALTH` | `/api/` | Case-sensitive, không khớp `health` |
| `/unknown` | Không có context | Server tự trả 404 |
| `/api2` | Không có `/api/` prefix | Không khớp |
| `/api/health/extra` | `/api/health` | Prefix literal vẫn khớp |

**Cạm bẫy:** Context `"/admin"` cũng có thể khớp `"/administrator"` vì cùng prefix. Nếu muốn route dạng thư mục, thường nên đăng ký `"/admin/"` và xử lý chính xác `"/admin"` (redirect/reject) tùy protocol. Đừng coi context matching như route syntax của các web frameworks.

Do path matching literal, nếu xử lý file paths hoặc authorization theo URI, còn phải cẩn thận encoded slash, dot segments, normalized paths, case và decoded values. Không tạo file path từ request URL bằng string concatenation không kiểm tra.

## 8. `HttpExchange`: đúng thứ tự request/response

`HttpExchange` đại diện cho một lượt xử lý HTTP.

```text
HttpHandler.handle(exchange)
    |
    +-- exchange.getRequestMethod()
    +-- exchange.getRequestURI()
    +-- exchange.getRequestHeaders()
    +-- exchange.getRequestBody()   (nếu cần)
    |
    +-- validate method/headers/body/authorization
    |
    +-- exchange.getResponseHeaders().set(...)
    +-- exchange.sendResponseHeaders(status, length)
    +-- exchange.getResponseBody().write(...)
    |
    +-- close request/response streams or exchange
```

### 8.1. Các getter quan trọng

| Method | Ý nghĩa |
| --- | --- |
| `getRequestMethod()` | `GET`, `HEAD`, `POST`... |
| `getRequestURI()` | Path/query của request |
| `getRequestHeaders()` | Các request headers |
| `getRequestBody()` | `InputStream` chứa body |
| `getResponseHeaders()` | Mutable headers cho response |
| `sendResponseHeaders(status, length)` | Gửi status/headers và quy định body mode |
| `getResponseBody()` | `OutputStream` để ghi body |
| `getLocalAddress()` | Địa chỉ endpoint local |
| `getRemoteAddress()` | Địa chỉ client được thấy ở kết nối |
| `getProtocol()` | Ví dụ `HTTP/1.1` |
| `getHttpContext()` | Context đã chọn |
| `getAttribute()/setAttribute()` | Giao tiếp thuộc tính qua filters/handler |
| `close()` | Kết thúc exchange, giải phóng streams |

**Không gọi `getResponseBody()` và ghi dữ liệu trước khi `sendResponseHeaders()`**. Không để exchanges mở vô hạn; body stream cần được đóng để server kết thúc response và tái sử dụng tài nguyên.

### 8.2. Request headers và response headers

`getRequestHeaders()` trả headers nhận được từ client và không dành cho việc chỉnh sửa request tùy tiện. `getResponseHeaders()` trả đối tượng có thể thay đổi trước khi gửi:

```java
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.getResponseHeaders().set(
        "X-Content-Type-Options", "nosniff");
```

Sử dụng `Headers.set` cho giá trị đơn, `add` khi header cho phép nhiều values. Header names case-insensitive theo HTTP semantics. Không ghi sensitive tokens vào response/logs.

Nếu ứng dụng trả JSON, sử dụng `application/json; charset=utf-8`, **escape/serialize JSON đúng cách** bằng thư viện phù hợp; không nối string trực tiếp với dữ liệu không đáng tin rồi coi là JSON an toàn.

### 8.3. UTF-8 và byte length

Khi trả string Unicode, phải đo **số bytes UTF-8**, không phải `String.length()`:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
exchange.sendResponseHeaders(200, bytes.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(bytes);
}
```

`String.length()` đếm UTF-16 code units. Với tiếng Việt/emoji, khác số bytes UTF-8. Ghi không đủ hoặc vượt fixed response length có thể làm connection bị abort và ném `IOException`.

## 9. Quy tắc dễ nhầm: responseLength >0, =0, =-1

Đây là một trong những phần quan trọng nhất của `HttpExchange`.

| Giá trị `responseLength` | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| `> 0` | Fixed length: phải ghi **đúng số bytes** | Text/JSON/bytes đã có sẵn |
| `0` | **Chunked transfer encoding**, độ dài không xác định | Streaming response |
| `-1` (hoặc âm khác) | **Không có response body** | `204`, `HEAD` hoặc response empty |
| `HttpExchange.RSPBODY_CHUNKED` | Symbolic name cho `0`, từ **JDK 26** | Mã target 26+ |
| `HttpExchange.RSPBODY_EMPTY` | Symbolic name cho `-1`, từ **JDK 26** | Mã target 26+ |

**Không truyền `bytes.length` nếu `bytes.length==0` mà tưởng “body rỗng”**: số 0 có nghĩa *chunked response*. Với response không có body, dùng `-1` trong code Java17.

Ví dụ fixed body:

```java
byte[] body = "ready".getBytes(StandardCharsets.UTF_8);
exchange.sendResponseHeaders(200, body.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(body);
}
```

Ví dụ chunked:

```java
exchange.sendResponseHeaders(200, 0);
try (OutputStream out = exchange.getResponseBody()) {
    out.write("part-A|".getBytes(StandardCharsets.UTF_8));
    out.write("part-B".getBytes(StandardCharsets.UTF_8));
}
```

Ví dụ no content:

```java
exchange.sendResponseHeaders(204, -1);
```

Ba đoạn là snippets đặt bên trong một handler có `exchange`. `HttpExchange.close()` hoặc đóng output stream kết thúc request/response. Với chunked response, output stream **phải đóng** để gửi kết thúc chunks.

## 10. Xử lý phương thức HTTP: GET, HEAD, POST, 405, 413

`HttpServer` không tự giới hạn method chỉ vì handler tên là `/health`. Ứng dụng tự định nghĩa:

```java
if (!"GET".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "GET");
    // send 405 Method Not Allowed
}
```

Các lưu ý:
- `GET`: nên không làm thay đổi dữ liệu server theo cách bất ngờ.
- `HEAD`: giống GET ở mục đích lấy metadata, **không trả response body**. Cần xử lý đúng header/body contract.
- `POST`: có thể có body; **giới hạn kích thước từ lúc đọc**.
- `405 Method Not Allowed`: nên có header `Allow` chỉ rõ methods hỗ trợ.
- `404 Not Found`: server tự trả nếu không context nào match; handler cũng cần trả 404 nếu resource trong context không tồn tại.
- `413 Content Too Large`: từ chối body vượt giới hạn; không materialize toàn bộ body rồi mới check.

Ví dụ đọc giới hạn 64 bytes:

```java
try (InputStream input = exchange.getRequestBody()) {
    byte[] bytes = input.readNBytes(65);
    if (bytes.length > 64) {
        // Send HTTP 413; do not process the request.
        return;
    }
    // Decode as UTF-8 and validate content.
}
```

Đây là snippet **chỉ minh họa cách kiểm tra vượt ngưỡng**; caller phải gửi status 413 trước khi return (fixture đầy đủ có làm). Với production, không chỉ dựa vào `Content-Length` header có thể thiếu/sai; cần giới hạn bytes được đọc thực tế, và đặt ingress/timeouts.

Nếu server từ chối request trước khi đọc hết body, connection có thể không được tái sử dụng. JDK implementation có thể drain một số bytes và đóng connection tùy configuration; đừng giả định keep-alive luôn còn.

## 11. `Filter`: xử lý trước và sau handler

`HttpContext.getFilters()` cho phép thêm filters. Một filter có hai điểm cơ bản:
- `description()` mô tả chức năng.
- `doFilter(HttpExchange exchange, Filter.Chain chain)` thực thi trước/sau handler.

Ví dụ:

```java
HttpContext ctx = server.createContext("/api/", handler);
ctx.getFilters().add(new Filter() {
    @Override
    public String description() {
        return "Add request-local marker";
    }

    @Override
    public void doFilter(
            HttpExchange ex, Chain chain) throws IOException {
        ex.setAttribute("trace", "filter-ok");
        chain.doFilter(ex);
    }
});
```

Đây là snippet cần `server`/`handler` và imports `HttpContext, Filter, HttpExchange, IOException`. `chain.doFilter(ex)` chuyển tiếp exchange qua các filters còn lại và handler. Không gọi nhiều lần hoặc bỏ qua tùy tiện.

### 11.1. Filter dùng để làm gì?

- Gắn correlation ID/trace marker.
- Ghi latency/metrics.
- Kiểm tra đơn giản về request method hoặc headers.
- Bọc streams qua `setStreams` nếu thật sự cần.
- Chặn request ở một điều kiện với response phù hợp.
- Chuẩn hóa logging không ghi secrets.

Không coi một filter đơn giản là thay thế đầy đủ cho security middleware/framework. Authorization và quota cần được thiết kế theo trust boundary.

### 11.2. `HttpHandlers` từ JDK 18

Java SE 26 có tiện ích:
- `HttpHandlers.of(int statusCode, Headers headers, String body)`: tạo static response handler.
- `HttpHandlers.handleOrElse(Predicate<Request>, handler, fallbackHandler)`: chọn handler theo điều kiện.

Ví dụ **cho source target JDK 18+**:

```java
HttpHandler allowGet = HttpHandlers.handleOrElse(
        req -> "GET".equals(req.getRequestMethod()),
        HttpHandlers.of(
                200,
                Headers.of("Content-Type", "text/plain; charset=utf-8"),
                "ready"),
        HttpHandlers.of(
                405,
                Headers.of("Allow", "GET"),
                "method not allowed"));
```

Đây là snippet cần imports `HttpHandler, HttpHandlers, Headers`. **Không** đưa nó vào fixture `--release 17` vì `HttpHandlers` được giới thiệu trong JDK 18. Nó là một cách tổ hợp handlers gọn, không thay thế những validation/security khác.

## 12. Thay đổi quan trọng trong JDK 26: attributes theo exchange

**Đây là kiến thức hiện hành dễ bị bỏ qua nhất khi đọc các ví dụ HttpServer cũ.**

Trước JDK 26, trong implementation `jdk.httpserver` mặc định của JDK, `HttpExchange` attributes **dùng chung một attribute map** với enclosing `HttpContext`. Điều này tạo khả năng dữ liệu exchange vô tình dùng chung giữa requests.

**Từ JDK 26**, mặc định:
- `exchange.setAttribute("trace", value)` lưu attribute **theo từng HttpExchange**.
- `exchange.getAttribute("trace")` đọc attribute của exchange đó.
- Context attributes phải được truy cập qua **`exchange.getHttpContext().getAttributes()`**.
- System property `jdk.httpserver.attributes=context` có thể khôi phục behavior trước JDK 26 cho mục đích tương thích, **không nên dùng làm mô hình thiết kế mới**.

Nguồn: Oracle JDK 26 Release Notes và `jdk.httpserver` module summary.

### 12.1. Code nên viết để đúng cả JDK 17 và 26

Muốn lưu cấu hình **context-scoped**:

```java
HttpContext api = server.createContext("/api/", handler);
api.getAttributes().put("service", "demo-service");
```

Trong handler đọc trực tiếp:

```java
Object service = exchange.getHttpContext()
        .getAttributes().get("service");
```

Để lưu metadata **request/exchange-scoped** trong filter:

```java
exchange.setAttribute("trace", "filter-ok");
```

Trong handler tương ứng:

```java
Object trace = exchange.getAttribute("trace");
```

**Tránh** dùng `exchange.getAttribute("service")` để đọc context configuration. Trên JDK trước 26 có thể vô tình hoạt động do shared map, nhưng trên JDK 26 default sẽ không còn làm vậy.

### 12.2. Đừng chia sẻ state request qua context

Đặt `requestId` hoặc user identity vào `HttpContext.getAttributes()` là một thiết kế nguy hiểm vì context được chia sẻ giữa nhiều requests và threads. Dữ liệu dùng chung phải immutable/thread-safe; metadata request nên nằm trong exchange-specific scope.

Code fixture chỉ set marker tĩnh `"filter-ok"`; vì test chạy trên JDK 24, nó **không** tuyên bố đã thử new JDK 26 behavior. Phần chênh lệch version được kiểm chứng từ tài liệu JDK 26, còn code cố ý đọc context attribute qua explicit context API để tương thích.

## 13. Xác thực: `BasicAuthenticator` chỉ là bước đầu

`BasicAuthenticator` hỗ trợ HTTP Basic authentication:

```java
HttpContext restricted =
        server.createContext("/private/", handler);

restricted.setAuthenticator(
        new BasicAuthenticator("demo-only") {
            @Override
            public boolean checkCredentials(
                    String username, String password) {
                return "student".equals(username)
                        && "local-test-password".equals(password);
            }
        });
```

Đây là snippet **chỉ phù hợp môi trường học/test trên loopback**. Mật khẩu hardcoded **không được đưa vào ứng dụng thật**. Với production:
- Không gửi Basic credentials qua **HTTP plaintext**; ít nhất phải có TLS end-to-end.
- Lưu secrets bằng secret store và hash credential với cơ chế phù hợp.
- Chống brute-force, rate limit, audit và session management.
- Kiểm tra authorization **sau authentication**.
- Không dùng demo credentials hay `Base64` như cơ chế mã hóa bảo mật: Base64 chỉ là encoding.
- Cân nhắc mTLS/token validation/gateway policy nếu thích hợp.

Không có header `Authorization`, `BasicAuthenticator` có thể trả HTTP 401 và `WWW-Authenticate` challenge. Trong fixture, authenticated GET trên localhost trả 200.

### 13.1. `HttpsServer` là API khác

`HttpsServer` mở HTTPS listener. Để dùng nó, cần:
- `HttpsServer.create(...)`.
- `HttpsConfigurator` với `SSLContext` đã cấu hình certificate/private key.
- TLS versions, ciphers, certificate lifecycle, client-auth policy nếu cần.
- Validation và vận hành security boundary.

Không chỉ thay `HttpServer` bằng `HttpsServer` rồi kỳ vọng mã tự có certificate đáng tin. Đừng đưa ví dụ self-signed certificate vào production mà không triển khai trust policy.

### 13.2. Network exposure

Đoạn học tập bind loopback. Để expose ra LAN/Internet, bạn phải **chủ động** đánh giá threat model, firewall/gateway, TLS, authentication/authorization, rate limiting và observability. Không bind `0.0.0.0` chỉ để “curl từ máy khác thử” khi service có endpoints nhạy cảm.

## 14. Ví dụ chạy thật: server và client cùng một JVM

Một chương trình hoàn chỉnh sẽ:
- Mở server tại loopback với port do OS chọn.
- Tạo fixed executor có 4 threads trước khi start.
- Đăng ký `/health` xử lý GET, HEAD và 405.
- Đăng ký `/api/` với một `Filter` và context-scoped `service` setting.
- Đăng ký `/api/health` để xác minh longest-prefix match.
- Đăng ký `/echo` nhận POST UTF-8, giới hạn body 64 bytes, trả 413 nếu vượt.
- Đăng ký `/empty` trả HTTP 204, không body.
- Đăng ký `/chunk` trả body với chunked encoding.
- Đăng ký `/private/` với `BasicAuthenticator` chỉ để kiểm chứng loopback.
- Dùng `java.net.http.HttpClient` thực hiện GET/HEAD/POST và đọc status/body/headers.
- Đối chiếu **38 assertions**, dừng server, shutdown executor trong finally.

**Mức độ kiểm thử:** Có HTTP connection thật qua TCP loopback, không mock `HttpExchange` hoặc gửi những kết quả giả lập. Trình biên dịch `javac --release 17` và OpenJDK 24 đã chạy thành công **38/38 PASS**.

### 14.1. File `HttpServerModuleDemo.java`

Lưu nguyên nội dung sau thành **`HttpServerModuleDemo.java`**:

```java
import com.sun.net.httpserver.BasicAuthenticator;
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.atomic.AtomicInteger;

public final class HttpServerModuleDemo {
    private static int passed;

    private static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + label);
        System.out.println("PASS " + label);
        passed++;
    }

    private static void reply(
            HttpExchange ex, int status, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        ex.getResponseHeaders().set(
                "X-Content-Type-Options", "nosniff");

        if (bytes.length == 0) {
            ex.sendResponseHeaders(status, -1);
        } else {
            ex.sendResponseHeaders(status, bytes.length);
            try (OutputStream body = ex.getResponseBody()) {
                body.write(bytes);
            }
        }
    }

    private static boolean require(
            HttpExchange ex, String method)
            throws IOException {
        if (method.equals(ex.getRequestMethod())) {
            return true;
        }
        ex.getResponseHeaders().set("Allow", method);
        reply(ex, 405, "method not allowed");
        return false;
    }

    private static HttpRequest req(
            URI uri, String method, String body) {
        HttpRequest.Builder builder =
                HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(5));

        if ("GET".equals(method)) {
            return builder.GET().build();
        }
        if ("HEAD".equals(method)) {
            return builder.method(
                    "HEAD",
                    HttpRequest.BodyPublishers.noBody())
                    .build();
        }
        if ("POST".equals(method)) {
            return builder.POST(
                    HttpRequest.BodyPublishers.ofString(
                            body, StandardCharsets.UTF_8))
                    .build();
        }
        throw new IllegalArgumentException(method);
    }

    private static HttpResponse<String> send(
            HttpClient client,
            URI uri,
            String method,
            String body) throws Exception {
        return client.send(
                req(uri, method, body),
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        ExecutorService workers =
                Executors.newFixedThreadPool(4);

        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getLoopbackAddress(), 0),
                16);

        AtomicInteger filterCalls = new AtomicInteger();
        AtomicInteger echoCalls = new AtomicInteger();

        server.createContext("/health", ex -> {
            try (ex) {
                if ("HEAD".equals(ex.getRequestMethod())) {
                    ex.getResponseHeaders().set(
                            "Content-Type",
                            "text/plain; charset=utf-8");
                    ex.sendResponseHeaders(200, -1);
                    return;
                }

                if (!require(ex, "GET")) return;
                reply(ex, 200, "ready");
            }
        });

        HttpContext api =
                server.createContext("/api/", ex -> {
            try (ex) {
                if (!require(ex, "GET")) return;

                String service = String.valueOf(
                        ex.getHttpContext()
                                .getAttributes()
                                .get("service"));

                String marker = String.valueOf(
                        ex.getAttribute("trace"));

                reply(ex, 200,
                        "api;service=" + service
                        + ";trace=" + marker);
            }
        });

        api.getAttributes().put("service", "demo-service");
        api.getFilters().add(new Filter() {
            @Override
            public String description() {
                return "Adds request-local marker";
            }

            @Override
            public void doFilter(
                    HttpExchange ex, Chain chain)
                    throws IOException {
                filterCalls.incrementAndGet();
                ex.setAttribute("trace", "filter-ok");
                chain.doFilter(ex);
            }
        });

        server.createContext("/api/health", ex -> {
            try (ex) {
                if (!require(ex, "GET")) return;
                reply(ex, 200, "api-ready");
            }
        });

        server.createContext("/echo", ex -> {
            try (ex) {
                if (!require(ex, "POST")) return;
                echoCalls.incrementAndGet();

                byte[] bytes;
                try (InputStream in = ex.getRequestBody()) {
                    bytes = in.readNBytes(65);
                }
                if (bytes.length > 64) {
                    reply(ex, 413, "payload too large");
                    return;
                }
                reply(ex, 200, "echo:"
                        + new String(bytes,
                                StandardCharsets.UTF_8));
            }
        });

        server.createContext("/empty", ex -> {
            try (ex) {
                if (!require(ex, "GET")) return;
                ex.sendResponseHeaders(204, -1);
            }
        });

        server.createContext("/chunk", ex -> {
            try (ex) {
                if (!require(ex, "GET")) return;

                ex.getResponseHeaders().set(
                        "Content-Type",
                        "text/plain; charset=utf-8");

                // 0 means chunked, NOT empty response.
                ex.sendResponseHeaders(200, 0);

                try (OutputStream out =
                        ex.getResponseBody()) {
                    out.write("part-A|".getBytes(
                            StandardCharsets.UTF_8));
                    out.write("part-B".getBytes(
                            StandardCharsets.UTF_8));
                }
            }
        });

        HttpContext restricted =
                server.createContext("/private/", ex -> {
            try (ex) {
                if (!require(ex, "GET")) return;
                reply(ex, 200, "secret-demo");
            }
        });

        // Demo credentials for loopback tests ONLY.
        restricted.setAuthenticator(
                new BasicAuthenticator("demo-only") {
            @Override
            public boolean checkCredentials(
                    String username,
                    String password) {
                return "student".equals(username)
                        && "local-test-password".equals(password);
            }
        });

        server.setExecutor(workers);
        server.start();

        try {
            int port = server.getAddress().getPort();
            URI base = URI.create(
                    "http://127.0.0.1:" + port);

            HttpClient client = HttpClient.newBuilder()
                    .version(
                            HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(5))
                    .build();

            check("module-is-present",
                    ModuleLayer.boot()
                            .findModule("jdk.httpserver")
                            .isPresent());
            check("loopback-ephemeral-address",
                    port > 0
                    && server.getAddress().getAddress()
                            .isLoopbackAddress());
            check("executor-configured",
                    server.getExecutor() == workers);

            HttpResponse<String> health = send(
                    client, base.resolve("/health"),
                    "GET", "");
            check("get-health-200",
                    health.statusCode() == 200);
            check("health-body",
                    health.body().equals("ready"));
            check("health-utf8-contenttype",
                    health.headers().firstValue(
                            "content-type").orElse("")
                            .contains("utf-8"));
            check("health-http11",
                    health.version()
                            == HttpClient.Version.HTTP_1_1);

            HttpResponse<String> head = send(
                    client, base.resolve("/health"),
                    "HEAD", "");
            check("head-200",
                    head.statusCode() == 200);
            check("head-without-body",
                    head.body().isEmpty());

            HttpResponse<String> wrong = send(
                    client, base.resolve("/health"),
                    "POST", "");
            check("method-405",
                    wrong.statusCode() == 405);
            check("method-allow-header",
                    wrong.headers().firstValue("allow")
                            .orElse("").equals("GET"));

            HttpResponse<String> apiParent = send(
                    client, base.resolve("/api/items"),
                    "GET", "");
            check("prefix-context-matches",
                    apiParent.statusCode() == 200);
            check("context-attributes-read-directly",
                    apiParent.body().contains(
                            "service=demo-service"));
            check("filter-populates-exchange-attribute",
                    apiParent.body().contains(
                            "trace=filter-ok"));
            check("api-filter-called",
                    filterCalls.get() == 1);

            HttpResponse<String> child = send(
                    client, base.resolve("/api/health"),
                    "GET", "");
            check("longest-prefix-context",
                    child.body().equals("api-ready"));
            check("child-no-parent-filter",
                    filterCalls.get() == 1);

            HttpResponse<String> caseVariant = send(
                    client, base.resolve("/api/HEALTH"),
                    "GET", "");
            check("context-case-sensitive",
                    caseVariant.body().contains(
                            "service=demo-service"));
            check("parent-filter-on-case-variant",
                    filterCalls.get() == 2);

            HttpResponse<String> notFound = send(
                    client, base.resolve("/unknown"),
                    "GET", "");
            check("missing-context-404",
                    notFound.statusCode() == 404);

            String unicode = "Xin chào 🌿";
            HttpResponse<String> echo = send(
                    client, base.resolve("/echo"),
                    "POST", unicode);
            check("post-echo-200",
                    echo.statusCode() == 200);
            check("post-utf8-body",
                    echo.body().equals(
                            "echo:" + unicode));
            check("post-handler-called",
                    echoCalls.get() == 1);

            HttpResponse<String> tooLarge = send(
                    client, base.resolve("/echo"),
                    "POST", "x".repeat(65));
            check("post-overlimit-413",
                    tooLarge.statusCode() == 413);
            check("post-overlimit-message",
                    tooLarge.body().equals(
                            "payload too large"));

            HttpResponse<String> echoWrong = send(
                    client, base.resolve("/echo"),
                    "GET", "");
            check("echo-get-405",
                    echoWrong.statusCode() == 405);
            check("echo-handler-not-called-on-get",
                    echoCalls.get() == 2);

            HttpResponse<String> empty = send(
                    client, base.resolve("/empty"),
                    "GET", "");
            check("no-content-204",
                    empty.statusCode() == 204);
            check("no-content-empty-body",
                    empty.body().isEmpty());

            HttpResponse<String> chunk = send(
                    client, base.resolve("/chunk"),
                    "GET", "");
            check("chunked-200",
                    chunk.statusCode() == 200);
            check("chunked-body",
                    chunk.body().equals("part-A|part-B"));
            check("chunked-transfer-encoding",
                    chunk.headers().firstValue(
                            "transfer-encoding")
                            .orElse("")
                            .equalsIgnoreCase("chunked"));

            HttpResponse<String> unauthorized = send(
                    client, base.resolve("/private/"),
                    "GET", "");
            check("basic-auth-401",
                    unauthorized.statusCode() == 401);
            check("basic-auth-challenge",
                    unauthorized.headers()
                            .firstValue("www-authenticate")
                            .orElse("").startsWith("Basic"));

            String credentials =
                    Base64.getEncoder().encodeToString(
                            "student:local-test-password"
                                    .getBytes(
                                            StandardCharsets.UTF_8));

            HttpRequest authed = HttpRequest.newBuilder(
                    base.resolve("/private/"))
                    .timeout(Duration.ofSeconds(5))
                    .header(
                            "Authorization",
                            "Basic " + credentials)
                    .GET()
                    .build();

            HttpResponse<String> privateOk = client.send(
                    authed,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            check("basic-auth-200-on-loopback",
                    privateOk.statusCode() == 200);
            check("basic-auth-returned-demo-response",
                    privateOk.body().equals("secret-demo"));

            check("filter-count-is-context-local",
                    filterCalls.get() == 2);
            check("module-name",
                    HttpServer.class.getModule().getName()
                            .equals("jdk.httpserver"));

            System.out.println("passed=" + passed);
        } finally {
            server.stop(1);
            workers.shutdownNow();
        }
    }
}
```

### 14.2. Biên dịch và chạy

```bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 HttpServerModuleDemo.java
java --add-modules jdk.httpserver HttpServerModuleDemo
```

Các lệnh dùng được trong PowerShell, Linux hay macOS với JDK 17+. Port do OS chọn nên không cần sửa source. Server chỉ bind loopback, không nhận kết nối trực tiếp từ mạng bên ngoài. Client dùng HTTP/1.1; không có yêu cầu certificate/TLS vì **chỉ demo trong cùng máy**.

### 14.3. Stdout chính xác đã xác minh

```text
PASS module-is-present
PASS loopback-ephemeral-address
PASS executor-configured
PASS get-health-200
PASS health-body
PASS health-utf8-contenttype
PASS health-http11
PASS head-200
PASS head-without-body
PASS method-405
PASS method-allow-header
PASS prefix-context-matches
PASS context-attributes-read-directly
PASS filter-populates-exchange-attribute
PASS api-filter-called
PASS longest-prefix-context
PASS child-no-parent-filter
PASS context-case-sensitive
PASS parent-filter-on-case-variant
PASS missing-context-404
PASS post-echo-200
PASS post-utf8-body
PASS post-handler-called
PASS post-overlimit-413
PASS post-overlimit-message
PASS echo-get-405
PASS echo-handler-not-called-on-get
PASS no-content-204
PASS no-content-empty-body
PASS chunked-200
PASS chunked-body
PASS chunked-transfer-encoding
PASS basic-auth-401
PASS basic-auth-challenge
PASS basic-auth-200-on-loopback
PASS basic-auth-returned-demo-response
PASS filter-count-is-context-local
PASS module-name
passed=38
```

**Content QA:** Chương trình đã được biên dịch bằng `javac --release 17` và chạy trên OpenJDK 24, **38/38 assertions PASS**, bao gồm HTTP thật, dữ liệu Unicode và các endpoints được mô tả. Không in port/timing cụ thể để tránh các giá trị nondeterministic.

### 14.4. Giải thích kết quả chính

| Nhóm | Test | Điều được xác minh |
| --- | --- | --- |
| Module | `module-is-present`, `module-name` | Class nằm trong `jdk.httpserver` |
| Port | `loopback-ephemeral-address` | Không expose LAN, OS chọn port |
| Executor | `executor-configured` | Server dùng executor được cấp |
| GET | `get-health-200` | HTTP response 200 |
| UTF-8 | `health-utf8-contenttype`, `post-utf8-body` | Body/headers chứa encoding đúng |
| HEAD | `head-200`, `head-without-body` | Không trả response body |
| Method | `method-405`, `method-allow-header` | Từ chối method, có `Allow` |
| Context routing | `longest-prefix-context` | Context cụ thể thắng prefix chung |
| Case | `context-case-sensitive` | `/api/HEALTH` khác `/api/health` |
| 404 | `missing-context-404` | Không có context phù hợp |
| Filter | `filter-populates-exchange-attribute` | Metadata filter có thể tới handler |
| Context attrs | `context-attributes-read-directly` | Đọc cấu hình qua `getHttpContext().getAttributes()` |
| POST | `post-echo-200` | Body UTF-8 được đọc/trả |
| Size limit | `post-overlimit-413` | Không nhận body vượt 64 bytes |
| 204 | `no-content-204` | Empty body với `-1` |
| Chunked | `chunked-transfer-encoding` | `responseLength=0` sinh chunked |
| Basic auth | `basic-auth-401`, `basic-auth-200-on-loopback` | Authorization challenge và demo credentials |
| Cleanup | `passed=38` trong flow finally | Server stop, executor shutdown sau test |

### 14.5. Những gì fixture không chứng minh

- Không benchmark throughput hoặc latency trên tải lớn.
- Không chứng minh `HttpServer` là production-grade API gateway.
- Không test HTTPS certificate/mTLS hay HTTP/2; chỉ HTTP/1.1 loopback.
- Không test security của Basic authentication qua public network; **không dùng demo credentials ngoài localhost**.
- Không đo timeout/slowloris, queue overload và rate limiting; cần config và integration test riêng.
- Không chạy trên JDK 26; thay đổi attribute map JDK 26 được kiểm tra bằng **tài liệu chính thức**, không gắn sai nhãn là kết quả runtime fixture JDK 24.

## 15. `jwebserver`: phục vụ file cục bộ nhanh từ JDK 18+

`jwebserver` là tool CLI cho **Java Simple Web Server**. Theo JDK 26 tool guide:
- Chỉ serve **static files/directory listings**.
- Chỉ xử lý **GET** và **HEAD**.
- Chỉ hỗ trợ **HTTP/1.1**; **không HTTPS và không HTTP/2**.
- Mặc định bind **loopback**, port **8000**, directory hiện tại.
- Phục vụ một directory hierarchy do bạn chọn; các hành vi ẩn/symlink theo implementation docs.
- Chỉ dành cho prototyping/testing/debugging; không expose files chứa dữ liệu nhạy cảm.

Ví dụ trong một folder do bạn kiểm soát:

```bash
jwebserver -b 127.0.0.1 -p 8000 -d ./public -o info
```

Nếu folder `./public` không tồn tại, cần tạo trước. Dừng tool bằng `Ctrl+C`. Để xem help:

```bash
jwebserver --help
```

Hoặc chạy module main:

```bash
java -m jdk.httpserver
```

**Không** bind `0.0.0.0` chỉ để chia sẻ nhanh cả thư mục project chứa secrets. Tool có thể trả directory listing; mặc định là directory hiện tại nếu không truyền `-d`.

### 15.1. Phân biệt `jwebserver` và `HttpServer`

| Nội dung | `jwebserver` | `HttpServer` tự lập trình |
| --- | --- | --- |
| Chạy bằng | CLI | Java source |
| Tạo custom endpoints | Không | Có, qua HttpHandler |
| GET/HEAD | Có | Tùy code handler |
| POST/PUT | Không dành cho handling động | Có thể lập trình |
| Serve static files | Có | Tự viết hoặc dùng SimpleFileServer |
| HTTPS | Không | Qua `HttpsServer` |
| Module | `jdk.httpserver` | `jdk.httpserver` |
| Mục tiêu | Development/test | Embedded/test/small HTTP service |

### 15.2. `SimpleFileServer` từ JDK 18+

Với Java 18+:

```java
HttpServer files = SimpleFileServer.createFileServer(
        new InetSocketAddress(
                InetAddress.getLoopbackAddress(), 8080),
        Path.of("public").toAbsolutePath().normalize(),
        SimpleFileServer.OutputLevel.INFO);
files.start();
```

Đây là snippet phải được đặt trong method có imports `HttpServer`, `SimpleFileServer`, `InetAddress`, `InetSocketAddress` và `Path`. Nó phục vụ file trong folder đã chỉ định và **chỉ dùng cho development/testing**, không phải một production file CDN.

`SimpleFileServer.createFileHandler(root)` trả `HttpHandler`; `createOutputFilter(output, level)` tạo logging filter. Với JDK 18+, có thể kết hợp cùng `HttpHandlers.handleOrElse` để thêm handling method riêng, nhưng phải kiểm tra authorization/path security nếu cho client ghi file.

## 16. Những giới hạn tài nguyên liên quan đến HTTP server mặc định

Module documentation Java SE 26 liệt kê một số **JDK-specific system properties** của implementation mặc định. Ví dụ:

| Property | Ý nghĩa | Mặc định được công bố trong JDK 26 docs |
| --- | --- | --- |
| `jdk.httpserver.maxConnections` | Số TCP connections đang mở (active+idle) | `-1` (không giới hạn ở property này) |
| `sun.net.httpserver.maxIdleConnections` | Số keep-alive idle connections | `200` |
| `sun.net.httpserver.idleInterval` | Khoảng idle connection được giữ | `30s` |
| `sun.net.httpserver.drainAmount` | Số bytes request body còn lại tối đa được auto-discard để xem xét reuse connection | `65536` |
| `sun.net.httpserver.maxReqHeaders` | Số header fields tối đa | `200` |
| `sun.net.httpserver.maxReqHeaderSize` | Tổng kích thước header section | `393216` bytes |
| `sun.net.httpserver.maxReqTime` | Thời gian tối đa đọc request headers/body, milliseconds | `-1` (không giới hạn ở property này) |
| `sun.net.httpserver.maxRspTime` | Thời gian tối đa truyền response headers/body, milliseconds | `-1` (không giới hạn ở property này) |
| `sun.net.httpserver.nodelay` | Cấu hình TCP_NODELAY | `false` |

**Đây là implementation-specific settings của JDK default provider**, không phải constants/contract portable cho mọi `HttpServerProvider`. Values/defaults có thể thay đổi giữa JDK versions. Chúng có thể được đặt bằng `-Dname=value` khi khởi chạy JVM; đọc module docs tương ứng runtime của bạn trước khi deploy.

Các limits này **không thay thế**:
- POST max body byte count theo endpoint.
- Authentication và authorization.
- Request processing deadline của business logic.
- Downstream/database timeout.
- Rate limiting và total memory/threads/backpressure.
- Payload format/schema validation.
- Reverse proxy limits.

Đặc biệt `sun.net.httpserver.maxReqTime` và `maxRspTime` mặc định âm (không áp limit tương ứng) trong JDK26 docs. Nếu expose dịch vụ có client không tin cậy, phải chủ động có network/security policy. Không trông chờ mọi limits đã bật sẵn.

## 17. Exception handling trong HttpHandler

Một handler có thể gặp:
- `IOException` khi client ngắt kết nối, đọc/ghi socket thất bại.
- `IllegalArgumentException` khi tham số/route/headers không hợp lệ.
- Lỗi parse JSON/data do business code.
- Timeout từ downstream services.
- RuntimeException do bug.

### 17.1. Trả status có chủ đích

Trước khi gọi `sendResponseHeaders()`, server có thể quyết định trả HTTP 400/401/403/404/405/413/500 phù hợp. Sau khi headers đã gửi, **không** cố gửi một response thứ hai trên cùng exchange.

Pattern:

```java
try (exchange) {
    // Validate and process; send response only once.
} catch (IOException socketFailure) {
    // Client disconnected or I/O failed; log safely and finish.
}
```

Đây là snippet. Không catch `Exception` rồi đưa `exception.toString()`/stack trace ra HTTP response, vì có thể lộ secrets và chi tiết hệ thống. Dùng correlation ID, error code và logging đã redact.

### 17.2. Đóng exchange để tránh rò resources

`HttpExchange` implements `AutoCloseable`. Sử dụng `try (exchange) { ... }` giúp close cả request/response streams khi handler kết thúc. Nếu đã viết body và đóng `OutputStream`, việc close exchange thêm là an toàn theo lifecycle của API.

Nếu chưa đọc hết request body mà close exchange, TCP connection có thể không tái sử dụng được, nhưng đó là lựa chọn chấp nhận được khi ứng dụng cố ý từ chối một body quá lớn.

### 17.3. Đừng block vô hạn trong handler

Server nhỏ cũng có thể chết vì cạn threads:
- Gọi service ngoài không timeout.
- Đọc body chưa giới hạn và client gửi vô hạn.
- Thao tác synchronized/global lock quá lâu.
- Chờ task trong cùng executor gây deadlock.
- Không xử lý client abort.

Gắn timeout trong `HttpClient` (outbound), database query timeout, ingress request time/size budgets và bounded executor cho môi trường vận hành thật.

## 18. Những sai lầm thường gặp

**1. Nghĩ module server là `java.net.http`.**  
`java.net.http` là HTTP **client**; server là `jdk.httpserver`.

**2. Dùng `sun.net.httpserver.*` internal classes.**  
Không. Dùng public API `com.sun.net.httpserver.*` của module.

**3. Bỏ `requires jdk.httpserver` trong named module.**  
Ứng dụng modular cần khai báo dependency đúng.

**4. Coi `HttpServer.create(...)` đã bắt đầu nghe.**  
Cần gọi `server.start()`.

**5. Gọi `setExecutor` sau khi đã `start()`.**  
API ném `IllegalStateException`. Cấu hình executor trước start.

**6. Không shutdown executor do mình tạo sau `server.stop()`.**  
Có thể để các worker threads còn sống khiến JVM không thoát.

**7. Cố start lại HttpServer đã stop.**  
Sau stop không thể reuse instance; tạo mới.

**8. Cho rằng `backlog=16` nghĩa là chỉ có tối đa 16 requests đồng thời.**  
Backlog liên quan TCP accept queue, không phải HTTP request concurrency cap.

**9. Bind all interfaces vô tình.**  
Dùng explicit loopback cho local tests, trừ khi có yêu cầu/biện pháp bảo vệ network rõ.

**10. Chỉ đăng ký path rồi nghĩ HTTP method tự được bảo vệ.**  
Phải check GET/HEAD/POST hoặc dùng conditional handler.

**11. Dùng `"/admin"` mà nghĩ không match `"/administrator"`.**  
Context matching là literal prefix; dùng `"/admin/"` nếu muốn directory-style path.

**12. Không hiểu longest-prefix matching.**  
`/api/health` thắng `/api/` khi request đúng lowercase path.

**13. Giả định request URI path luôn normalized/decoded.**  
Không. Validate raw/decoded paths theo security policy trước file access.

**14. Dùng `String.length()` làm HTTP fixed response length.**  
Sai với UTF-8 Unicode; dùng `bytes.length`.

**15. Truyền `0` vào `sendResponseHeaders` để trả body rỗng.**  
`0` nghĩa chunked, dùng `-1` cho no-body trong Java 17.

**16. Gọi `getResponseBody().write(...)` trước `sendResponseHeaders(...)`.**  
Không đúng lifecycle của API.

**17. Không đóng output stream khi dùng chunked.**  
Client có thể chờ không có điểm kết thúc response.

**18. Không đọc/đóng request body.**  
Dễ giảm khả năng reuse connection hoặc rò tài nguyên.

**19. Đọc toàn bộ POST body rồi mới kiểm tra độ lớn.**  
Dễ memory exhaustion; dùng bounded reads/ingress limits.

**20. Coi Basic Auth qua HTTP plaintext là bảo mật.**  
Basic credentials chỉ Base64-encoded; cần TLS hoặc chỉ local demo.

**21. Coi xác thực người dùng là đủ cho mọi endpoint.**  
Cần authorization theo user/role/resource.

**22. Không đặt `Allow` khi trả 405.**  
HTTP client khó biết methods được hỗ trợ.

**23. Đưa stacktrace/exception nội bộ vào response.**  
Có thể lộ secrets, đường dẫn, cấu hình, service tokens.

**24. Dùng `exchange.getAttribute("service")` để đọc context attribute trên JDK26.**  
JDK 26 per-exchange map default; đọc qua `exchange.getHttpContext().getAttributes()`.

**25. Đặt request ID/user identity vào `context.getAttributes()`.**  
Context shared giữa requests; dễ lộ/cross-request data race.

**26. Bật `jdk.httpserver.attributes=context` rồi coi đó là cách viết mới nên dùng.**  
Đó là compatibility switch để khôi phục behavior cũ, không nên thiết kế phụ thuộc nó.

**27. Dùng `HttpExchange.RSPBODY_EMPTY` trong source target Java17.**  
Constant được thêm ở JDK 26; code Java17 dùng `-1`.

**28. Dùng `HttpHandlers` / `SimpleFileServer` rồi biên dịch target Java17.**  
Hai tiện ích này từ JDK 18; phải nâng target/runtime hoặc dùng API cơ bản.

**29. Coi `jwebserver` là public HTTPS/HTTP2 production server.**  
Theo JDK26 tool docs, nó là HTTP/1.1 static file server cho test/dev, chỉ GET/HEAD.

**30. Tưởng `HttpServer` mặc định có bounded request rates và timeouts đầy đủ.**  
Phải cấu hình ingress/threads/body/timeouts.

**31. Giữ các mutable maps/lists dùng chung giữa handlers mà không đồng bộ.**  
Executor có nhiều threads; cần thread-safe state.

**32. Test chỉ handler trực tiếp, không gửi HTTP request thật.**  
Có thể bỏ sót status/header/protocol/transfer encoding; dùng HttpClient loopback integration tests.

**33. Không test 404, 405, 413, HEAD và empty/chunked.**  
Dễ có endpoint xử lý sai HTTP semantics dù GET thành công.

**34. Không giới hạn file serving root và quyền filesystem nếu dùng SimpleFileServer.**  
Không bao giờ serve toàn bộ thư mục chứa secrets.

**35. Dùng HttpsServer nhưng chưa cấu hình chứng thư/TLS chính xác.**  
HTTPS cần `SSLContext` và certificate lifecycle; không tự phát sinh bảo mật.

## 19. Checklist khi triển khai và nâng cấp JDK

- [ ] Chọn `jdk.httpserver` vì nhu cầu thực sự nhỏ/embedded/test.
- [ ] Dùng public `com.sun.net.httpserver` API, không đụng internals.
- [ ] `module-info.java` có `requires jdk.httpserver` nếu là named module.
- [ ] Bind loopback trong tests; quyết định interface network có chủ đích.
- [ ] Khởi tạo contexts/filters/authenticator/executor **trước start**.
- [ ] Hiểu longest literal prefix và case-sensitive path matching.
- [ ] Kiểm tra methods và status codes đúng; gửi `Allow` cho 405.
- [ ] Dùng UTF-8 và **byte length** khi gửi fixed body.
- [ ] Phân biệt `responseLength: >0` fixed, `0` chunked, `-1` no body.
- [ ] Đóng request/response streams và exchange.
- [ ] Giới hạn request bytes/headers/time/depth và concurrency.
- [ ] Không hardcode secrets hoặc để Basic auth trên HTTP public.
- [ ] Dùng context attrs cho dữ liệu shared config, exchange attrs cho request metadata.
- [ ] Khi lên JDK26, kiểm tra thay đổi per-exchange attribute map.
- [ ] Không dựa vào compatibility property `jdk.httpserver.attributes=context` lâu dài.
- [ ] Ghi log an toàn và đủ correlation ID; không log credentials/raw body.
- [ ] Chọn HTTPS/reverse proxy nếu có network external.
- [ ] Dừng server và shutdown executor, tạo instance mới khi restart.
- [ ] Đánh giá integration test với JDK/provider đúng môi trường triển khai.
- [ ] Không coi `jwebserver`/`SimpleFileServer` là hardened production web server.

## 20. Câu hỏi ôn tập

**1. `HttpServer` thuộc module nào?**  
`jdk.httpserver`.

**2. `java.net.http.HttpClient` là server API không?**  
Không. Nó là client; server-side API ở `com.sun.net.httpserver`.

**3. Named module cần directive gì?**  
`requires jdk.httpserver;`.

**4. Có thể khởi động server mà không gọi `start()` không?**  
Không. `create`/`bind` chưa đồng nghĩa start.

**5. Làm thế nào dùng port không xung đột khi test?**  
Bind `port=0`, lấy port thật từ `server.getAddress().getPort()`.

**6. Vì sao bind loopback trong demo?**  
Không vô tình mở service qua mạng.

**7. `HttpContext` chọn handler thế nào?**  
Theo **longest literal matching path prefix**, case-sensitive.

**8. Context `"/api"` có thể khớp `"/apiX"` không?**  
Có, vì prefix literal; nên cân nhắc `"/api/"`.

**9. Method POST tới GET-only handler sẽ tự bị server chặn không?**  
Không. Handler/conditional policy phải tự trả 405.

**10. `sendResponseHeaders(200, 0)` có nghĩa body rỗng?**  
Không. Nó chọn chunked transfer encoding.

**11. Dùng gì để trả 204 no body với Java17?**  
`sendResponseHeaders(204, -1)`.

**12. Tại sao dùng `bytes.length` thay `text.length()`?**  
Vì HTTP fixed body length tính **bytes**, UTF-8 có thể nhiều bytes cho một ký tự.

**13. Khi nào thiết lập executor?**  
Trước `start()`.

**14. `stop(delay)` có thể restart cùng HttpServer không?**  
Không. Tạo server instance mới.

**15. Request data qua `HttpExchange.getAttribute` có thể lấy từ context mặc định trên JDK 26 không?**  
Không nên dựa vào đó. JDK26 mặc định per-exchange; shared context attributes đọc qua `exchange.getHttpContext().getAttributes()`.

**16. Dùng `jdk.httpserver.attributes=context` để làm gì?**  
Khôi phục behavior shared attributes của JDK trước 26; đây là compatibility switch.

**17. `HttpHandlers` và `SimpleFileServer` có từ phiên bản nào?**  
JDK 18.

**18. Các symbolic constants `RSPBODY_EMPTY/CHUNKED` có từ khi nào?**  
JDK 26.

**19. `jwebserver` hỗ trợ HTTPS và HTTP/2 không?**  
Không. Nó phục vụ static files bằng HTTP/1.1, chủ yếu cho development/testing.

**20. Tại sao BasicAuthenticator demo chỉ chạy loopback?**  
Basic auth qua HTTP plaintext không bảo vệ credentials trên mạng; demo không phải policy production.

**21. Khi POST body quá lớn nên làm gì?**  
Đọc có giới hạn, trả 413, đóng exchange phù hợp và áp ingress limits.

**22. `HttpServer` có sẵn rate limiter/tổng giới hạn business requests đầy đủ không?**  
Không. Cần gateway/limits/executor/backpressure và monitoring riêng.

**23. 38/38 PASS chứng minh gì?**  
Java17 HTTP server fixture đã hoạt động trên OpenJDK24 với các request/responses đã test. Không chứng minh throughput/security production.

## 21. Tài liệu hiện hành Java SE 26

- [Java SE 26 — `jdk.httpserver` module summary](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/module-summary.html): mục đích module, system properties và thay đổi JDK26 attribute maps.
- [Java SE 26 — `HttpServer`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): create/bind, contexts, longest-prefix matching, executor, start/stop và backlog.
- [Java SE 26 — `HttpExchange`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): lifecycle, status, streams và `RSPBODY_EMPTY/CHUNKED`.
- [Java SE 26 — `HttpContext`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): filters, authenticator và context attributes.
- [Java SE 26 — `HttpHandler`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): request handlers.
- [Java SE 26 — `Filter`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html): request pre/post processing.
- [Java SE 26 — `Headers`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): multi-value HTTP headers.
- [Java SE 26 — `BasicAuthenticator`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/BasicAuthenticator.html): basic auth mechanism.
- [Java SE 26 — `HttpsServer`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): TLS-enabled HTTP server.
- [Java SE 26 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): file server cho test/development.
- [Java SE 26 — `HttpHandlers`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandlers.html): static/conditional handler factories.
- [Java SE 26 — `jwebserver` tool guide](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jwebserver.html): flags, mặc định loopback, chỉ static GET/HEAD và HTTP/1.1.
- [Oracle JDK 26 Release Notes — HttpContext Attributes No Longer Shared with HttpExchange by Default](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): thay đổi JDK 26 `jdk.httpserver.attributes`.
- [Java SE 26 — `java.net.http.HttpClient`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): client để kiểm thử HTTP server.

**Tổng kết:** `HttpServer` của `jdk.httpserver` vẫn là một API JDK public, hữu ích cho **HTTP server gọn và local integration tests**. Cần khai báo đúng module, thiết lập contexts/executor trước start, giới hạn và đóng streams, phân biệt response length modes, hiểu longest-prefix routing và chú ý **JDK 26 mặc định tách exchange attributes khỏi context attributes**. `SimpleFileServer`/`jwebserver` hỗ trợ nhanh việc chia sẻ static files khi phát triển, nhưng không phải lựa chọn production web gateway bảo mật/hiệu năng cao.
