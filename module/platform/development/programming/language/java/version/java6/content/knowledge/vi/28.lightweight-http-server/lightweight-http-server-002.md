# HttpHandler, HttpExchange và context định tuyến trong Java HTTP Server

**`com.sun.net.httpserver.HttpServer`** là HTTP server gọn được JDK cung cấp trong module **`jdk.httpserver`**. Nó thích hợp để tạo endpoint nội bộ, webhook demo, health check, ứng dụng nhúng, tiện ích phát triển và integration test mà không cần Spring, Servlet container hay một web framework bên ngoài.

Để sử dụng đúng, cần hiểu ba đối tượng cốt lõi:

- **`HttpServer`** mở socket, nhận kết nối, quản lý các **`HttpContext`** và chuyển HTTP request cho handler tương ứng. Nó có các API như `create(...)`, `createContext(...)`, `setExecutor(...)`, `start()` và `stop(...)`.
- **`HttpHandler`** là functional interface chỉ có method `handle(HttpExchange exchange)`. Nó viết logic xử lý một request đã được định tuyến, ví dụ kiểm tra method, đọc input và gửi kết quả.
- **`HttpExchange`** là một phiên xử lý **request/response**: có HTTP method, URI, request headers/body, response headers/body và trạng thái phản hồi. Handler phải gửi response đúng thứ tự, **đóng streams/exchange** để giải phóng tài nguyên.

**`HttpContext`** nối **đường dẫn đăng ký** với `HttpHandler`, đồng thời chứa cấu hình `Filter`, `Authenticator` và context attributes. Khi có nhiều contexts, server **chọn context có đường dẫn là tiền tố dài nhất khớp với request path**. Trong API mặc định JDK 17–26, việc khớp là **literal, phân biệt chữ hoa/thường, không tự chuẩn hóa/URL-decode**, và **không tự xét HTTP method hay query string**. Vì vậy, thêm route `"/api"` có thể vô tình bắt cả `"/api2"`; nhiều trường hợp nên đăng ký `"/api/"` và tự kiểm tra path chính xác khi cần.

Bài thuộc nhóm **HTTP server gọn**. Các API và kỹ thuật được trình bày vẫn còn áp dụng trong **Java 17+ và JDK 26**; không dùng kiến thức đã lỗi thời làm khuyến nghị. Có **hai chương trình Java 17+ độc lập**: một server với sáu contexts và 16 kiểm tra HTTP thật qua `HttpClient` trên **loopback**, một chương trình kiểm tra **filter, chunked/no-body responses và removeContext** với 6 assertions. Cả hai được biên dịch `javac --release 17` và chạy trên JDK 24, không cần thư viện bên ngoài.

## 1. Phạm vi của jdk.httpserver

`jdk.httpserver` là module **đặc thù JDK**, nhưng package `com.sun.net.httpserver` là API **được xuất công khai** từ module, **không phải** package nội bộ `sun.*` mà ứng dụng phải dùng `--add-exports` để truy cập. Tên package bắt đầu bằng `com.sun` **không tự đồng nghĩa** với “internal unsupported API”.

Các class/interface chính:

| API | Vai trò | Điểm dùng thực tế |
| --- | --- | --- |
| `HttpServer` | HTTP server và context router. | Tạo server, bind, start, stop, thêm/xóa context. |
| `HttpHandler` | Xử lý một request. | `handle(HttpExchange)` là lambda/method reference. |
| `HttpExchange` | Request + response cho một lượt gọi. | Method, URI, headers, body, status và stream lifecycle. |
| `HttpContext` | Ánh xạ path → handler và cấu hình route. | `getPath()`, `getHandler()`, `getFilters()`, `setAuthenticator()`. |
| `Headers` | Tập header names không phân biệt hoa/thường. | Request headers read-only; response headers writable. |
| `Filter` | Xử lý trước/sau handler. | Request logging/metadata/thẩm định đầu vào theo chính sách. |
| `Authenticator` | Cơ chế xác thực theo context. | Phải cấu hình riêng; **không tự có authentication**. |
| `HttpsServer` | Server hỗ trợ HTTPS. | Cần `HttpsConfigurator` và TLS config đáng tin. |

**Giới hạn rõ ràng:** Oracle mô tả server này là **minimal HTTP server**, chủ yếu dành cho phát triển, testing, debugging và use case đơn giản. Nó **không tự thay thế** đầy đủ các tính năng bảo mật, bảo vệ lưu lượng, TLS termination, quotas, metrics, reverse proxy và vận hành của một production web stack. Đừng phơi một demo HTTP localhost trực tiếp ra Internet.

## 2. Tạo HttpServer và đăng ký HttpContext

Cú pháp cơ bản:

```java
HttpServer server = HttpServer.create(
        new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);

server.createContext("/health", exchange -> {
    // Xử lý HTTP exchange ở đây.
});

server.start();
```

Đây là **mảnh code minh họa**; một ứng dụng hoàn chỉnh phải xử lý `IOException`, đóng exchange và gọi `stop` khi kết thúc. Chương trình runnable ở mục 8 làm đầy đủ.

### 2.1. InetSocketAddress và port 0

- `InetAddress.getLoopbackAddress()` bind vào loopback, giới hạn kết nối đến từ máy cục bộ; phù hợp test.
- Port `0` yêu cầu hệ điều hành chọn một cổng trống, tránh hardcode `8080` đang bận trong CI.
- `server.getAddress().getPort()` trả cổng thực tế đã bind.
- Nếu muốn người khác trong LAN kết nối, phải chủ động chọn interface/địa chỉ phù hợp và thêm security/network policy; đừng chọn wildcard bind theo thói quen trong demo.
- `HttpServer.create(InetSocketAddress addr, int backlog)` bind ngay; overload `create()` tạo server chưa bind, sau đó phải gọi `bind(...)` trước start.

Trong test bài này, client dùng `http://localhost:<port>` với port do OS cấp, không có external network request. Server được dừng trong `finally`.

### 2.2. Backlog không phải thread count

Tham số `backlog` liên quan số TCP connections đang chờ được accept ở kernel/socket. Nó **không** phải số lượng HTTP handlers có thể chạy đồng thời, số requests tối đa, cũng không phải kích thước request-body giới hạn.

`backlog <= 0` để provider/JDK dùng system default phù hợp. Concurrency thực tế còn phụ thuộc `Executor` và resource limits. Một server không giới hạn request size/connection count có thể cạn tài nguyên ngay cả khi backlog đặt nhỏ.

### 2.3. createContext trả về HttpContext

```java
HttpContext context = server.createContext(
        "/api/items/", new ItemHandler());
```

Mảnh code chỉ hợp lệ khi `ItemHandler` implements `HttpHandler` và `server` tồn tại. `HttpContext` là registration của route; bạn có thể gọi `context.getPath()`, `getHandler()`, `getFilters()`, `setAuthenticator(...)` hoặc gắn các context-level configuration attributes.

Không tạo hai contexts cùng **path string** trên một server: `createContext` có thể ném `IllegalArgumentException` nếu path đã được đăng ký. Các context path phải bắt đầu bằng `"/"`; không dùng query string như một phần đường dẫn registration.

## 3. Quy tắc chọn context: tiền tố dài nhất, literal

Đây là điểm quan trọng nhất của định tuyến built-in trong JDK 17–26.

Giả sử server đăng ký:

```java
server.createContext("/", rootHandler);
server.createContext("/api/", apiHandler);
server.createContext("/api/items/", itemsHandler);
server.createContext("/hello", helloHandler);
```

**Mỗi request chỉ được chuyển tới context có path dài nhất là tiền tố literal khớp với request URI path.** Với các path trên:

| Request path | Context được chọn | Giải thích |
| --- | --- | --- |
| `/api/items/42` | `/api/items/` | Dài hơn `/api/` và `/`. |
| `/api/items/` | `/api/items/` | Path match chính xác. |
| `/api/items` | `/api/` | Thiếu dấu `/` cuối nên không match `/api/items/`. |
| `/api/ping` | `/api/` | Path bắt đầu bằng `/api/`. |
| `/api2` | `/` | `/api/` không match `/api2`. |
| `/hello` | `/hello` | Path match chính xác. |
| `/helloworld` | `/hello` | **Đây là prefix text match**, dù không phải segment `hello`. |
| `/HELLO` | `/` | Context matching phân biệt chữ hoa/thường. |
| `/unknown` | `/` | Catch-all root context. |

**Quan trọng:** `"/hello"` match `"/helloworld"` bởi đó là so sánh tiền tố **chuỗi**, không phải “path segment match”. Nếu bạn muốn chỉ xử lý `/hello`, **handler phải kiểm tra path chính xác**, rồi trả 404 cho `/helloworld`.

Tương tự, `createContext("/api")` có thể khớp `/api2` và `/apix`. Khi muốn một nhánh có delimiter, hãy dùng `"/api/"`, hoặc kiểm tra chính xác root `"/api"` bên trong handler.

### 3.1. Query string không phải một phần context path

Request:

```text
GET /api/items/42?lang=vi HTTP/1.1
```

được router chọn theo **`/api/items/42`**; query `lang=vi` không ảnh hưởng context matching. Trong handler:

```java
URI uri = exchange.getRequestURI();
String path = uri.getRawPath();
String query = uri.getRawQuery();
```

Cần import `java.net.URI` và có biến `exchange`. `getRawQuery()` có thể trả `null` nếu không có `?`.

**Không lấy `URI.toString()` rồi dùng `startsWith("/api/")`**, vì URI string có thể chứa scheme/authority/query hoặc encoded data.

### 3.2. Context router không chọn HTTP method

Cùng một context `"/api/items/"` có thể nhận `GET`, `POST`, `PUT`, `DELETE`, `HEAD` v.v. Router built-in **không tạo method-based endpoints** tự động. Trong handler bạn phải dùng:

```java
if (!"GET".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "GET");
    // Gửi status 405 và đóng response.
}
```

`405 Method Not Allowed` phù hợp khi resource/route tồn tại nhưng method không được hỗ trợ. Header `Allow` nên liệt kê những method cho phép. Cần phân biệt `404 Not Found` (route không hợp lệ), `400 Bad Request` (input sai) và `413 Content Too Large` (request payload vượt chính sách).

Với `HEAD`, `OPTIONS` và `204 No Content`, ứng dụng phải xử lý HTTP semantics cụ thể; `HttpServer` không tự biến một GET handler thành một REST framework đầy đủ.

### 3.3. Encoded path và decoded path

`HttpServer` theo Javadoc so khớp path **literal, không tự chuyển đổi sang/từ encoded forms**. `URI` từ `exchange.getRequestURI()` có:

- `getRawPath()`: giữ percent-encoded representation, ví dụ `"/api/items/%34%32"`.
- `getPath()`: decoded path, ví dụ `"/api/items/42"`.
- `getRawQuery()` và `getQuery()`: tương ứng với phần query.

Chương trình test đã xác minh `GET /api/items/%34%32` trả phần suffix **`%34%32`** khi handler dùng `getRawPath()`. Nếu ứng dụng cần decode route parameters, phải quy định chính xác encoding và **kiểm tra lại input sau decode**; tránh double-decoding, encoded slash/dot-segments, path traversal hoặc nhận nhầm tên file.

**Đừng dùng `getPath()` để tự tái dựng security identity của resource nếu proxy/router/handler đang so raw paths theo các quy tắc khác nhau.** Một đường dẫn có thể có nhiều dạng encoded tương đương hoặc bất tương đương tùy tầng; canonicalization policy phải thống nhất.

### 3.4. "/" có nghĩa catch-all

Nếu đăng ký `server.createContext("/", fallback)`, mọi path không match context chuyên biệt sẽ đến fallback handler; nó không còn nhận built-in 404 của server khi hoàn toàn không có match.

Nếu **không có** root catch-all và request không khớp bất kỳ context nào, `HttpServer` tự trả HTTP 404. Chương trình thứ hai ở mục 9 kiểm tra điều này sau khi xóa context duy nhất cho `/stream`.

## 4. HttpHandler.handle(HttpExchange): một request, một response

`HttpHandler` là functional interface:

```java
@FunctionalInterface
public interface HttpHandler {
    void handle(HttpExchange exchange) throws IOException;
}
```

Đây là chữ ký **minh họa**, không phải một Java file độc lập. Có thể triển khai bằng:

```java
server.createContext("/health", exchange -> {
    try (exchange) {
        byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(200, body.length);
        try (var out = exchange.getResponseBody()) {
            out.write(body);
        }
    }
});
```

Đây là mảnh code cần `server`, imports và xử lý checked exception tại ngữ cảnh method chứa nó. `HttpExchange` implements `AutoCloseable`, vì thế dùng `try(exchange)` (Java 9+ syntax) giúp chắc chắn exchange được kết thúc.

### 4.1. Một handler nên thực hiện những bước nào?

Thông thường:

1. Đọc `exchange.getRequestMethod()` và `exchange.getRequestURI()`.
2. Kiểm tra route/method và xác thực/ủy quyền phù hợp.
3. Đọc `exchange.getRequestHeaders()` khi cần; chỉ tin content-type, credentials, host/IP sau khi validate theo policy.
4. Đọc `exchange.getRequestBody()` nếu route chấp nhận body, với **size limit** và charset/format rõ ràng.
5. Chọn status code, tạo response body bytes.
6. Đặt headers trong `exchange.getResponseHeaders()` **trước** gửi status.
7. Gọi `sendResponseHeaders(status, responseLength)` **đúng một lần**.
8. Viết số bytes thích hợp vào `getResponseBody()`.
9. Đóng output stream, input stream và exchange kể cả khi gặp lỗi.

Nếu handler ném exception mà không gửi response/không đóng exchange, phía client có thể gặp connection reset hoặc request treo; không nên coi `HttpHandler` có error handler chung tự trả JSON/500 an toàn như một framework.

### 4.2. Headers case-insensitive nhưng không tự đáng tin

`exchange.getRequestHeaders()` trả header collection **read-only**, còn `exchange.getResponseHeaders()` mutable. `Headers` xử lý **header names không phân biệt hoa/thường**. Các key có thể có nhiều values, do đó không nên giả định một header luôn chỉ có một giá trị hay luôn hợp lệ.

Ví dụ:

```java
String contentType =
        exchange.getRequestHeaders().getFirst("Content-Type");
String userAgent =
        exchange.getRequestHeaders().getFirst("User-Agent");
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.getResponseHeaders().set("X-Content-Type-Options", "nosniff");
```

Đây là mảnh code. `getFirst` trả `null` nếu header không có; không parse nguyên header thành trusted state. Không nên trả giá trị raw của header người dùng vào HTML page mà thiếu output encoding.

## 5. HttpExchange: request data và response lifecycle

Một `HttpExchange` sở hữu **một HTTP request và một HTTP response**. Các method:

| Method | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `getRequestMethod()` | HTTP method string. | Handler phải kiểm tra method. |
| `getRequestURI()` | `java.net.URI`. | Phân biệt raw/decoded path, query. |
| `getRequestHeaders()` | Headers request, read-only. | Không tin user input. |
| `getRequestBody()` | `InputStream` body. | Đọc có giới hạn; đóng phù hợp. |
| `getResponseHeaders()` | Headers response, writable. | Đặt trước `sendResponseHeaders`. |
| `sendResponseHeaders(int,long)` | Gửi HTTP status + headers, định dạng body. | Phải gọi trước `getResponseBody`. |
| `getResponseBody()` | `OutputStream` để gửi body. | Đóng stream để kết thúc exchange. |
| `getResponseCode()` | Status đã thiết lập, hoặc -1 trước khi có. | Hữu ích trong filter/logger. |
| `getHttpContext()` | Context được chọn. | Có `getPath`, `getAttributes`. |
| `getLocalAddress()` | Địa chỉ local server của request. | Không thay thế route/host validation. |
| `getRemoteAddress()` | Địa chỉ peer socket. | Qua proxy có thể là proxy, không phải user thực. |
| `getProtocol()` | HTTP protocol string. | Không giả định HTTP/2. |
| `getAttribute(name)` / `setAttribute` | Metadata liên quan exchange. | JDK 26 thay đổi attribute scoping; xem mục 11. |
| `getPrincipal()` | Principal nếu context có Authenticator. | Có thể null nếu chưa xác thực. |
| `close()` | Kết thúc cả request/response streams. | Gọi khi hết lifetime. |

### 5.1. Response headers phải đi trước body

Sai thứ tự:

```java
// SAI: chưa gọi sendResponseHeaders.
exchange.getResponseBody().write(bytes);
exchange.sendResponseHeaders(200, bytes.length);
```

Đúng:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.sendResponseHeaders(200, bytes.length);
try (var output = exchange.getResponseBody()) {
    output.write(bytes);
}
```

Chỉ sử dụng đoạn này nếu `bytes.length > 0`, bởi **độ dài 0 có nghĩa chunked**, không phải “response body rỗng” trên `HttpExchange`. Với body rỗng, dùng `-1`. Xem mục 6 và chương trình thứ hai.

### 5.2. Không dùng String.length() thay số bytes

Với văn bản `"Xin chào 😀"`, số Java UTF-16 code units và số bytes UTF-8 **khác nhau**. Khi sử dụng fixed length:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
exchange.sendResponseHeaders(200, bytes.length);
output.write(bytes);
```

Nếu `sendResponseHeaders` nhận `text.length()` trong khi output ghi `text.getBytes(UTF_8)`, bạn có thể gửi **nhiều bytes hơn khai báo**, gây `IOException` và đóng connection.

### 5.3. Request input streams cũng phải được xử lý

`getRequestBody()` trả `InputStream`; đọc input lớn mà không có giới hạn dễ dẫn đến memory exhaustion:

```java
// Đây là fragment; MAX_BYTES do application quy định.
byte[] data;
try (var input = exchange.getRequestBody()) {
    data = input.readNBytes(MAX_BYTES + 1);
}
if (data.length > MAX_BYTES) {
    // Trả 413, không parse/echo payload lớn.
}
```

`readNBytes(MAX+1)` là một kỹ thuật giới hạn đọc cho body nhỏ. Trong sản phẩm thực cần thêm max header/body bytes, timeouts, rate limit và streaming parser cho body lớn. Đóng stream trước khi đọc hết request có thể làm kết nối HTTP keep-alive không tái sử dụng được; điều này phù hợp hơn việc đọc không giới hạn trong một demo.

## 6. sendResponseHeaders: >0, 0, -1 không giống nhau

Đây là **quy tắc rất dễ viết sai** của `HttpExchange`:

| `responseLength` | Ý nghĩa trên Java 17+ | Ứng dụng phải làm |
| --- | --- | --- |
| `> 0` | **Fixed length**, chính xác từng byte. | Ghi **đúng** số bytes đã khai báo. |
| `0` | **Chunked transfer encoding**, độ dài chưa xác định. | Có thể viết nhiều chunks; đóng output để kết thúc. |
| `-1` hoặc nhỏ hơn | **Không gửi response body**. | Không write bytes, vẫn đóng exchange. |

**JDK 26** còn bổ sung các constants `HttpExchange.RSPBODY_CHUNKED` và `HttpExchange.RSPBODY_EMPTY` nhằm làm rõ hai trạng thái 0/-1. Nhưng vì demo dùng `javac --release 17`, chương trình **dùng giá trị số 0 và -1**, không dùng constants mới chưa có trong API Java 17.

### 6.1. Fixed-length

```java
byte[] data = "Chào 😀".getBytes(StandardCharsets.UTF_8);
exchange.sendResponseHeaders(200, data.length);
try (var out = exchange.getResponseBody()) {
    out.write(data);
}
```

Phải ghi **đúng** số bytes. Ghi thiếu sẽ khiến `close` có thể ném `IOException`; ghi quá sẽ khiến `write` ném `IOException`. Cả hai trường hợp có thể abort exchange.

### 6.2. Chunked

```java
exchange.sendResponseHeaders(200, 0);
try (var out = exchange.getResponseBody()) {
    out.write("part-1".getBytes(StandardCharsets.UTF_8));
    out.write("+part-2".getBytes(StandardCharsets.UTF_8));
}
```

Ở HTTP/1.1 JDK server, client sẽ thấy body `part-1+part-2`, có thể được truyền bằng header `Transfer-Encoding: chunked`. **Không** dùng responseLength `0` để giả định “không có body”.

### 6.3. Không có body

```java
exchange.sendResponseHeaders(204, -1);
exchange.getResponseBody().close();
```

`204 No Content` không có response body; chọn `-1` rõ ràng. `HEAD` và `304 Not Modified` cũng có các quy tắc HTTP body riêng; với các status này, áp dụng đúng semantics chứ không cố ghi payload rồi nghĩ client sẽ tự bỏ qua.

## 7. Bộ định tuyến tối giản đầy đủ trên localhost

Chương trình đầu tiên tạo một server và đăng ký sáu contexts:

| Context path | Handler | Mục tiêu |
| --- | --- | --- |
| `/health` | `health` | GET health status, query không đổi route. |
| `/hello` | `hello` | GET với UTF-8, kiểm tra exact path. |
| `/api/` | `api` | GET với nhánh API chung. |
| `/api/items/` | `items` | GET danh sách/ID giả lập, lấy raw path và raw query. |
| `/api/echo` | `echo` | POST nhận body tối đa 64 bytes và phản hồi text. |
| `/` | `fallback` | 404 cho mọi route khác. |

`HttpServerRoutesDemo` còn dùng `java.net.http.HttpClient` để **tự gửi HTTP request thật** lên chính server vừa tạo. Nó không đòi hỏi bạn phải mở hai terminals, không dùng cổng hardcode và không gọi Internet.

### 7.1. Source: HttpServerRoutesDemo.java

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class HttpServerRoutesDemo {
    private static final int MAX_ECHO_BYTES = 64;

    private static void respond(HttpExchange exchange, int code, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type",
                "text/plain; charset=utf-8");
        exchange.getResponseHeaders().set("X-Content-Type-Options", "nosniff");
        exchange.sendResponseHeaders(code, bytes.length == 0 ? -1 : bytes.length);
        try (var out = exchange.getResponseBody()) {
            if (bytes.length != 0) out.write(bytes);
        }
    }

    private static boolean requireMethod(HttpExchange exchange, String method)
            throws IOException {
        if (method.equals(exchange.getRequestMethod())) return true;
        exchange.getResponseHeaders().set("Allow", method);
        respond(exchange, 405, "method-not-allowed");
        return false;
    }

    private static void health(HttpExchange exchange) throws IOException {
        try (exchange) {
            if (!"/health".equals(exchange.getRequestURI().getRawPath())) {
                respond(exchange, 404, "not-found");
            } else if (requireMethod(exchange, "GET")) {
                respond(exchange, 200, "ok");
            }
        }
    }

    private static void hello(HttpExchange exchange) throws IOException {
        try (exchange) {
            if (!"/hello".equals(exchange.getRequestURI().getRawPath())) {
                respond(exchange, 404, "hello-prefix-rejected");
            } else if (requireMethod(exchange, "GET")) {
                respond(exchange, 200, "xin-chào");
            }
        }
    }

    private static void api(HttpExchange exchange) throws IOException {
        try (exchange) {
            if (requireMethod(exchange, "GET")) {
                respond(exchange, 200,
                        "api:" + exchange.getRequestURI().getRawPath());
            }
        }
    }

    private static void items(HttpExchange exchange) throws IOException {
        try (exchange) {
            if (!requireMethod(exchange, "GET")) return;
            String path = exchange.getRequestURI().getRawPath();
            String prefix = "/api/items/";
            String item = path.substring(prefix.length());
            String query = exchange.getRequestURI().getRawQuery();
            respond(exchange, 200,
                    "items:" + (item.isEmpty() ? "index" : item)
                    + (query == null ? "" : ";query=" + query));
        }
    }

    private static void echo(HttpExchange exchange) throws IOException {
        try (exchange) {
            if (!"/api/echo".equals(exchange.getRequestURI().getRawPath())) {
                respond(exchange, 404, "echo-prefix-rejected");
                return;
            }
            if (!requireMethod(exchange, "POST")) return;
            byte[] data;
            try (var body = exchange.getRequestBody()) {
                data = body.readNBytes(MAX_ECHO_BYTES + 1);
            }
            if (data.length > MAX_ECHO_BYTES) {
                respond(exchange, 413, "payload-too-large");
                return;
            }
            respond(exchange, 200,
                    "echo:" + new String(data, StandardCharsets.UTF_8));
        }
    }

    private static void fallback(HttpExchange exchange) throws IOException {
        try (exchange) {
            respond(exchange, 404,
                    "not-found:" + exchange.getRequestURI().getRawPath());
        }
    }

    private static HttpResponse<String> get(
            HttpClient client, String base, String path) throws Exception {
        return client.send(HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(5)).GET().build(),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }

    private static HttpResponse<String> post(
            HttpClient client, String base, String path, String content)
            throws Exception {
        return client.send(HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "text/plain; charset=utf-8")
                .POST(HttpRequest.BodyPublishers.ofString(
                        content, StandardCharsets.UTF_8)).build(),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }

    private static void check(String label, int expectedCode,
                              String expectedText,
                              HttpResponse<String> response) {
        if (response.statusCode() != expectedCode
                || !expectedText.equals(response.body())) {
            throw new AssertionError(label + " expected " + expectedCode + " "
                    + expectedText + ", got " + response.statusCode() + " "
                    + response.body());
        }
        System.out.println(label + "=" + response.statusCode()
                + "|" + response.body());
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        server.setExecutor(pool);
        server.createContext("/health", HttpServerRoutesDemo::health);
        server.createContext("/hello", HttpServerRoutesDemo::hello);
        server.createContext("/api/", HttpServerRoutesDemo::api);
        server.createContext("/api/items/", HttpServerRoutesDemo::items);
        server.createContext("/api/echo", HttpServerRoutesDemo::echo);
        server.createContext("/", HttpServerRoutesDemo::fallback);
        try {
            server.start();
            String base = "http://localhost:" + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(5)).build();
            check("health", 200, "ok",
                    get(client, base, "/health"));
            check("queryIgnoredForContext", 200, "ok",
                    get(client, base, "/health?x=1"));
            check("helloUtf8", 200, "xin-chào",
                    get(client, base, "/hello"));
            check("literalPrefixCaught", 404, "hello-prefix-rejected",
                    get(client, base, "/helloworld"));
            check("caseSensitive", 404, "not-found:/HELLO",
                    get(client, base, "/HELLO"));
            check("longestItems", 200, "items:42;query=lang=vi",
                    get(client, base, "/api/items/42?lang=vi"));
            check("itemsIndex", 200, "items:index",
                    get(client, base, "/api/items/"));
            check("itemsWithoutTrailingSlash", 200, "api:/api/items",
                    get(client, base, "/api/items"));
            check("apiGeneric", 200, "api:/api/ping",
                    get(client, base, "/api/ping"));
            check("encodedRawPath", 200, "items:%34%32",
                    get(client, base, "/api/items/%34%32"));
            check("notFound", 404, "not-found:/api2",
                    get(client, base, "/api2"));
            check("postEcho", 200, "echo:Xin chào 😀",
                    post(client, base, "/api/echo", "Xin chào 😀"));
            check("postTooLarge", 413, "payload-too-large",
                    post(client, base, "/api/echo", "x".repeat(65)));
            check("echoPrefixCaught", 404, "echo-prefix-rejected",
                    post(client, base, "/api/echoBad", "x"));
            check("wrongMethod", 405, "method-not-allowed",
                    get(client, base, "/api/echo"));
            HttpResponse<String> method = get(client, base, "/api/echo");
            if (!method.headers().firstValue("Allow")
                    .orElse("").equals("POST")) {
                throw new AssertionError("Expected Allow: POST");
            }
            System.out.println("allowHeader=PASS");
        } finally {
            server.stop(0);
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

### 7.2. Biên dịch và chạy

Với JDK 17 trở lên, lưu file UTF-8 cùng tên class rồi chạy:

```bash
javac --release 17 -encoding UTF-8 HttpServerRoutesDemo.java
java HttpServerRoutesDemo
```

`HttpServer` ở module `jdk.httpserver`, `HttpClient` ở module `java.net.http`. Trong môi trường JDK thông thường, source classpath trên đây biên dịch được như đã kiểm thử, không cần external dependencies hoặc `--add-exports`. Nếu bạn sử dụng **named JPMS module** với `module-info.java`, phải khai báo `requires jdk.httpserver;` và `requires java.net.http;` khi code dùng cả hai.

### 7.3. Stdout chính xác đã kiểm chứng

```text
health=200|ok
queryIgnoredForContext=200|ok
helloUtf8=200|xin-chào
literalPrefixCaught=404|hello-prefix-rejected
caseSensitive=404|not-found:/HELLO
longestItems=200|items:42;query=lang=vi
itemsIndex=200|items:index
itemsWithoutTrailingSlash=200|api:/api/items
apiGeneric=200|api:/api/ping
encodedRawPath=200|items:%34%32
notFound=404|not-found:/api2
postEcho=200|echo:Xin chào 😀
postTooLarge=413|payload-too-large
echoPrefixCaught=404|echo-prefix-rejected
wrongMethod=405|method-not-allowed
allowHeader=PASS
```

**16 dòng stdout**, tất cả conditions đều được xác minh trên **JDK 24** khi biên dịch với `--release 17`. Mỗi dòng test có status/body được so sánh chính xác; `allowHeader=PASS` còn xác nhận response 405 có header `Allow: POST`.

### 7.4. Phân tích các test định tuyến

**`health=200`**: server chọn context `/health` và handler kiểm tra exact raw path.

**`queryIgnoredForContext=200`**: `/health?x=1` vẫn vào cùng context; query không đổi route.

**`helloUtf8=200`**: body chứa tiếng Việt, `getBytes(UTF_8)` giúp khai báo fixed response byte length chính xác.

**`literalPrefixCaught=404`**: server thực sự chuyển `/helloworld` vào context `/hello` vì raw text prefix, nhưng handler từ chối do path không đúng `"/hello"`.

**`caseSensitive=404`**: `/HELLO` không match `/hello`; route fallback `/` nhận.

**`longestItems=200`**: `/api/items/42` có cả hai tiền tố `/api/` và `/api/items/`, nhưng context dài hơn được chọn. `getRawQuery()` trả `lang=vi` và được đưa vào output để minh họa; demo không decode query thành business parameter.

**`itemsIndex=200`**: `/api/items/` match chính context items; suffix rỗng được mô tả là `index`.

**`itemsWithoutTrailingSlash=200`**: `/api/items` thiếu slash cuối nên **không** match `/api/items/`; nó match `/api/` chung, trả output `api:/api/items`.

**`apiGeneric=200`**: `/api/ping` đi vào context `/api/`.

**`encodedRawPath=200`**: `%34%32` được giữ raw trong handler, không tự chuyển thành `42` trước khi hiển thị.

**`notFound=404`**: `/api2` không match `/api/` nên fallback trả 404.

**`postEcho=200`**: POST body có tiếng Việt/emoji, đọc tối đa 65 bytes và phản hồi UTF-8.

**`postTooLarge=413`**: input 65 bytes vượt chính sách 64 bytes, handler từ chối, không đọc/phân tích không giới hạn.

**`echoPrefixCaught=404`**: context `/api/echo` cũng có thể bắt `/api/echoBad`, nhưng handler từ chối bởi exact-path check.

**`wrongMethod=405`**: một GET tới route chỉ cho POST được trả 405 thay vì vô tình xử lý body. 

**`allowHeader=PASS`**: HTTP 405 phản hồi danh sách method được phép theo header Allow.

### 7.5. Điều chương trình KHÔNG làm

- Không phục vụ Internet: chỉ bind loopback, client tự gọi localhost.
- Không tự thêm authentication/authorization/TLS.
- Không giải mã JSON, multipart uploads, cookies hoặc quản lý sessions.
- Không ghi file, không truy cập database.
- Không dùng một web framework; route/method policies được viết thủ công.
- Không giới thiệu `readNBytes(MAX+1)` là một giải pháp production toàn diện cho upload lớn; size limits ở proxy/server tầng khác vẫn cần thiết.
- Không bảo đảm an toàn chống tất cả path traversal/SSRF chỉ vì dùng `getRawPath`.
- Không dùng một exception handler chung; đây là demo được cố ý giới hạn phạm vi và input test.

## 8. HttpContext: filters, authenticator và removeContext

`HttpContext` biểu diễn mapping của một handler. Bạn nhận nó từ `server.createContext(...)`.

```java
HttpContext context = server.createContext("/stream", handler);
String registered = context.getPath();
HttpHandler registeredHandler = context.getHandler();
```

Đây là mảnh code yêu cầu `handler`/`server` phù hợp. `HttpContext` còn có:

- `context.getFilters()`: danh sách filters áp dụng vào requests của context; thứ tự filters có ý nghĩa.
- `context.setAuthenticator(authenticator)` và `getAuthenticator()`: xác thực trước handler nếu có cấu hình.
- `context.getAttributes()`: map cấu hình **chia sẻ theo context**.
- `context.setHandler(...)`: đặt handler nếu context được tạo mà chưa có handler.
- `server.removeContext(context)` hoặc `removeContext(path)`: bỏ mapping để các request mới không còn vào handler đó.

### 8.1. Filter trước handler

Từ Java 17, có tiện ích `Filter.beforeHandler`:

```java
HttpContext ctx = server.createContext("/stream", handler);
ctx.getFilters().add(Filter.beforeHandler(
        "count", e -> counter.incrementAndGet()));
```

Mảnh code yêu cầu `counter` và các imports phù hợp. Filter có thể ghi metadata, xác thực cơ bản theo policy hay đo thời gian, nhưng không nên biến nó thành logic tùy ý truy cập/ghi dữ liệu nguy hiểm trước khi route/method được kiểm tra.

Có cả `Filter.afterHandler` (quan sát response sau khi handler hoàn thành), và interface `Filter.doFilter(HttpExchange, Filter.Chain)` để tự điều khiển chain. Nếu một custom filter không gọi `chain.doFilter(exchange)`, nó **phải chịu trách nhiệm gửi response thích hợp**.

### 8.2. Authenticator không tự tồn tại

`HttpContext.setAuthenticator(...)` gắn cơ chế xác thực vào context. Nếu không thiết lập, `getPrincipal()` thường `null` và request tới handler không tự được xác thực.

**Đừng đưa endpoint nhạy cảm ra Internet** chỉ vì có context routing. Với hệ thống thật, cần xác thực danh tính, phân quyền theo resource/tenant, TLS, rate limiting và chính sách reverse proxy phù hợp. Dữ liệu như `X-Forwarded-For` là header do client có thể giả mạo nếu không có trusted-proxy policy.

### 8.3. removeContext không giết exchange đang chạy

`server.removeContext(context)` ngăn requests mới được phân phối tới context đã xóa; những exchanges đang xử lý **không bị hủy tức thời bởi hành động removeContext**. Bài test ở mục 9 xóa context `/stream` rồi gửi request mới, xác minh server tự trả 404 khi không có root catch-all và không còn context phù hợp.

## 9. Chương trình 2: chunked, no-body, filter và xóa context

File `HttpContextAndResponseDemo.java` kiểm chứng sáu hành vi độc lập:

1. Dùng `sendResponseHeaders(200, 0)` và viết hai chunks; client nhận body gộp.
2. Client nhìn thấy `Transfer-Encoding: chunked`.
3. `Filter.beforeHandler` tăng bộ đếm trước handler.
4. HTTP 204 với `sendResponseHeaders(204, -1)` không có body.
5. Fixed-length UTF-8 gửi text `Chào 😀` đúng.
6. Sau `removeContext`, request mới `/stream` không có handler nên nhận 404.

### 9.1. Source: HttpContextAndResponseDemo.java

```java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

public final class HttpContextAndResponseDemo {
    private static void text(HttpExchange e, int code, String value)
            throws IOException {
        byte[] b = value.getBytes(StandardCharsets.UTF_8);
        e.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
        e.sendResponseHeaders(code, b.length == 0 ? -1 : b.length);
        try (var out = e.getResponseBody()) {
            out.write(b);
        }
    }
    private static HttpResponse<String> get(HttpClient c, String base, String path)
            throws Exception {
        return c.send(HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(5)).GET().build(),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }
    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println(name + "=PASS");
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        AtomicInteger hits = new AtomicInteger();
        HttpContext context = server.createContext("/stream", e -> {
            try (e) {
                e.getResponseHeaders().set("Content-Type",
                        "text/plain; charset=utf-8");
                e.sendResponseHeaders(200, 0); // 0 => chunked, not empty
                try (var out = e.getResponseBody()) {
                    out.write("part-1".getBytes(StandardCharsets.UTF_8));
                    out.write("+part-2".getBytes(StandardCharsets.UTF_8));
                }
            }
        });
        context.getFilters().add(Filter.beforeHandler(
                "count", e -> hits.incrementAndGet()));
        server.createContext("/empty", e -> {
            try (e) {
                e.sendResponseHeaders(204, -1); // -1 => no body
                e.getResponseBody().close();
            }
        });
        server.createContext("/fixed", e -> {
            try (e) {
                text(e, 200, "Chào 😀");
            }
        });
        try {
            server.start();
            String base = "http://localhost:" + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(5)).build();
            HttpResponse<String> chunked = get(client, base, "/stream");
            check("chunkedBody", chunked.statusCode() == 200
                    && chunked.body().equals("part-1+part-2"));
            check("chunkedHeader",
                    chunked.headers().firstValue("Transfer-Encoding")
                    .orElse("").equalsIgnoreCase("chunked"));
            check("filterHit", hits.get() == 1);
            HttpResponse<String> empty = get(client, base, "/empty");
            check("noBody204", empty.statusCode() == 204
                    && empty.body().isEmpty());
            HttpResponse<String> fixed = get(client, base, "/fixed");
            check("fixedUtf8", fixed.statusCode() == 200
                    && fixed.body().equals("Chào 😀"));
            server.removeContext(context);
            HttpResponse<String> missing = get(client, base, "/stream");
            check("removedContext404", missing.statusCode() == 404);
        } finally {
            server.stop(0);
        }
    }
}
```

### 9.2. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 HttpContextAndResponseDemo.java
java HttpContextAndResponseDemo
```

**Stdout chính xác, 6/6 PASS trên JDK 24:**

```text
chunkedBody=PASS
chunkedHeader=PASS
filterHit=PASS
noBody204=PASS
fixedUtf8=PASS
removedContext404=PASS
```

Trong Java 17–26, chương trình dùng `-1` và `0` theo `sendResponseHeaders`. `Filter.beforeHandler` đã được bổ sung từ Java 17. Không có requirements về database hoặc external network.

### 9.3. Những kết luận từ chương trình thứ hai

- `chunkedBody=PASS` cho thấy chunked encoding không bắt client nhận từng chunk thành nhiều messages; HTTP client có thể ghép thành một response body.
- `chunkedHeader=PASS` cho thấy JDK HTTP server đã gửi HTTP/1.1 chunked transfer encoding trong test.
- `filterHit=PASS` cho thấy pre-handler filter chạy đúng một lần cho một request vào context.
- `noBody204=PASS` xác nhận status 204 và body rỗng dùng responseLength `-1`.
- `fixedUtf8=PASS` chứng minh fixed length phải tính bằng số bytes UTF-8.
- `removedContext404=PASS` khẳng định request mới không còn match context `/stream` sau khi remove. Server **không có `/` fallback** trong chương trình này.

## 10. Executor, concurrency và vòng đời server

`HttpServer.start()` tạo một background thread tiếp nhận connections. `server.setExecutor(executor)` cho phép server dispatch HTTP exchanges vào một `Executor` của ứng dụng. **Gọi `setExecutor` trước `start`**, nếu không có thể ném `IllegalStateException`.

Ví dụ của bài:

```java
ExecutorService pool = Executors.newFixedThreadPool(4);
server.setExecutor(pool);
try {
    server.start();
    // Gửi requests; handlers chạy qua executor.
} finally {
    server.stop(0);
    pool.shutdownNow();
    pool.awaitTermination(5, TimeUnit.SECONDS);
}
```

Nếu không `setExecutor`, JDK dùng default executor của server, **không phải** một phép màu tự tạo hệ thống request scheduling mạnh mẽ. Với ứng dụng có concurrent I/O, nên cân nhắc executor/queue sizes, timeouts, rate limits và giới hạn concurrent requests.

### 10.1. start, stop, restart

- `start()` bắt đầu phục vụ requests.
- `stop(delay)` đóng listening socket và ngừng nhận exchanges mới; có thể đợi handlers hiện tại tối đa khoảng `delay` giây.
- `stop(0)` dùng để dừng ngay trong test; công việc còn đang chạy có thể bị ngắt khi connections bị đóng.
- **Không thể khởi động lại cùng instance `HttpServer` sau khi đã stop**. Muốn server mới phải tạo instance mới.
- `removeContext(...)` khác `stop(...)`: remove một route, không dừng toàn server.
- Executor được ứng dụng cung cấp phải được dọn dẹp theo ownership của ứng dụng; demo tự `shutdownNow()` nó sau `stop`.

### 10.2. Không giữ handler quá lâu

Nếu một handler chiếm thread vì đọc body vô hạn, chờ database quá lâu hoặc stream response mà không có timeout, thread pool bị cạn. Với use case cần high concurrency/HTTP features hoàn chỉnh, cân nhắc một server/framework phù hợp hơn, có metrics và các lớp bảo vệ vận hành.

### 10.3. Backlog, connection limits và timeouts

JDK default server có các system properties về idle connections, request/response timeouts và header limits; chúng phụ thuộc provider/JDK version. Kiểm tra [module jdk.httpserver JDK 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/module-summary.html) trước khi thiết lập production test.

Những settings provider-specific không thay thế:

- Deadline/timeouts của application-level downstream calls.
- Kích thước request body.
- Quotas theo client/tenant/token.
- Rate limiting.
- Connection pool/worker limits.
- Logging/health metrics và alerting.
- TLS/authentication/authorization.

## 11. Điểm cần cập nhật cho JDK 26: exchange attributes

Đây là một thay đổi hiện hành đáng chú ý, đặc biệt khi đọc blog cũ.

Oracle JDK 26 module docs ghi: **trước JDK 26**, trong default implementation, map cho `HttpExchange` attributes được dùng chung với `HttpContext`. **Từ JDK 26**, mặc định attributes của `HttpExchange` là **riêng từng exchange**; khi muốn configuration dùng chung cho context, truy cập:

```java
Map<String, Object> shared =
        exchange.getHttpContext().getAttributes();
```

Còn khi muốn metadata cho request hiện tại:

```java
exchange.setAttribute("requestId", requestId);
Object stored = exchange.getAttribute("requestId");
```

Hai mảnh code này chỉ là minh họa API; `requestId` do ứng dụng tạo. Đừng dựa vào `exchange.setAttribute` để truyền trạng thái xuyên request vì semantics khác nhau theo version. Dùng `HttpContext.getAttributes()` cho config chia sẻ, và đồng bộ nếu có nhiều threads cùng sửa cấu trúc mutable.

### 11.1. Compatibility property

JDK 26 có system property `jdk.httpserver.attributes=context` để phục hồi hành vi exchange attributes cũ trong default implementation. Đây là cơ chế tương thích, **không phải lựa chọn kiến trúc khuyên dùng cho code mới**. Nên sửa code để không lệ thuộc vào shared exchange attributes, vì request-scoped state an toàn/rõ ràng hơn.

**Lưu ý:** property và details trên thuộc **default JDK provider**, không phải ràng buộc bắt buộc cho mọi HttpServer provider bên ngoài. Đối với hệ thống cần kiểm soát concurrency, kiểm tra behavior thật trên runtime dự kiến.

## 12. Bảo mật HTTP server tối giản

HTTP server nhận data không tin cậy. Một vài biện pháp tối thiểu trước khi dùng ngoài môi trường test:

### 12.1. Bind loopback theo mặc định

Trong demo dùng:

```java
new InetSocketAddress(InetAddress.getLoopbackAddress(), 0)
```

Điều này giới hạn socket ở loopback. Nếu server phục vụ nội bộ LAN hoặc Internet, phải chủ động có reverse proxy, TLS, auth và firewall/network ACL; tránh `new InetSocketAddress(0)` một cách vô ý vì có thể bind rộng hơn ý định.

### 12.2. Không có authentication/authorization mặc định

`HttpContext.setAuthenticator` là công cụ nhưng không tự bảo đảm:

- User identity đúng và token/session được xác thực.
- User có quyền truy cập đúng resource/tenant.
- Không bị CSRF nếu dùng cookie authentication trong web browser.
- Không bị rate abuse hoặc brute force.
- Không leak dữ liệu giữa các tenants.
- Thông tin principal/trace được kiểm soát.

Cho dữ liệu nhạy cảm, TLS qua `HttpsServer` (được cấu hình cẩn thận) hoặc reverse proxy trusted là cần thiết. HTTP thuần trên loopback phù hợp demo; không gửi credentials thật qua plain HTTP trên mạng không tin cậy.

### 12.3. Validate method, path, query và body

- **Method:** allowlist `GET`/`POST`…, trả 405 cùng `Allow` cho unsupported methods.
- **Raw path:** xác định chính xác path/prefix, không nhầm `/hello` với `/helloworld`.
- **Encoded path:** nhất quán về percent decoding; cẩn trọng encoded separators, `..`, Unicode normalization và double decoding.
- **Query:** đọc bằng `getRawQuery()` và parse với quy tắc phù hợp; không dùng substring/naive split nếu có percent-encoded `&`/`=`.
- **Body:** kiểm tra Content-Type, Content-Length khi có nhưng không tin nó hoàn toàn; thực tế vẫn giới hạn bytes đọc.
- **Charset:** dùng UTF-8 rõ ràng cả khi đọc/gửi văn bản.
- **Headers:** đặt `Content-Type` và `X-Content-Type-Options: nosniff` phù hợp.
- **Output:** escape/serialize theo định dạng trả về; đừng lấy raw input rồi render như HTML, SQL, shell command hoặc log mà thiếu kiểm soát.

### 12.4. Đừng lấy remote address làm danh tính

`getRemoteAddress()` là **peer socket address**. Qua reverse proxy, peer có thể là proxy, không phải người dùng cuối. Header `X-Forwarded-For` hoặc `Forwarded` cũng có thể bị client giả mạo nếu proxy không xác định/strip/ghi đè đúng. Dùng explicit trusted-proxy chain và authenticators.

### 12.5. Quản lý lỗi

Handler nên phân biệt:

| Tình huống | HTTP status phù hợp trong ví dụ |
| --- | --- |
| Path không tồn tại | `404 Not Found`. |
| Method không hỗ trợ | `405 Method Not Allowed` + `Allow`. |
| Body vượt giới hạn | `413 Content Too Large`. |
| Dữ liệu đầu vào sai | `400 Bad Request` (thay vì lỗi Java chưa bắt). |
| Chưa xác thực | `401 Unauthorized` + challenge phù hợp, nếu có auth. |
| Có danh tính nhưng không được phép | `403 Forbidden`. |
| Server internal failure | `500 Internal Server Error`, phản hồi an toàn, log riêng. |
| Hệ thống tạm không phục vụ | `503 Service Unavailable` nếu đúng tình huống. |

**Không hứa có thể đổi status sau khi `sendResponseHeaders` đã gửi.** Nếu lỗi xảy ra khi đang stream body, status có thể đã đi tới client, và giải pháp thường là hủy stream/đóng connection + ghi diagnostic, không phải cố gửi một response 500 thứ hai.

## 13. HttpServer vs HttpsServer và web framework

`HttpServer` giúp nắm HTTP request/response lifecycle nhưng không tự cung cấp đầy đủ:

| Chức năng | Server gọn trong JDK | Khi cần ứng dụng production |
| --- | --- | --- |
| HTTP endpoint | `HttpServer` và contexts. | Có thể đủ cho health check/embedded service đơn giản. |
| HTTPS | `HttpsServer` + TLS configuration. | Cần certificates/trust, rotation, TLS policy và monitoring. |
| Router HTTP method + variables | Tự viết trên `HttpHandler`. | Framework router nếu nhiều endpoints. |
| Body validation | Tự đọc/giới hạn/parse. | Schema/validation layer riêng. |
| Sessions/auth | Có `Authenticator` cấp context nhưng không đầy đủ policy. | AuthN/AuthZ, identity provider, tenant binding. |
| Rate limit/timeout | Một phần cấu hình provider + application logic. | Network gateway/filters, quotas và observability. |
| Structured logging/metrics | Tự thêm `Filter`/instrumentation. | Telemetry/health/alerts đầy đủ. |
| HTTP/2/WebSocket | Không giả định có từ API tối giản này. | Chọn server/framework hỗ trợ rõ tính năng nếu bắt buộc. |

**Không gọi `com.sun.net.httpserver` là “legacy và phải bỏ”**: API vẫn hiện hành, được JDK hỗ trợ. Nhưng cũng **không đánh đồng** nó với một stack server enterprise có đầy đủ protections mặc định.

## 14. Checklist triển khai

- [ ] Đã sử dụng public API `com.sun.net.httpserver` trong module `jdk.httpserver`?
- [ ] Có chọn binding address/port phù hợp, ưu tiên loopback trong test?
- [ ] Có đăng ký context path bắt đầu bằng `/`, tránh duplicate?
- [ ] Hiểu longest **literal** prefix matching và case sensitivity?
- [ ] Có tránh `"/api"` bắt `"/api2"` không chủ ý?
- [ ] Với endpoint exact-path, đã kiểm tra `getRawPath()` trong handler?
- [ ] Query string được xử lý riêng, không dùng làm context path?
- [ ] HTTP method được allowlist, có 405/Allow khi cần?
- [ ] Có kiểm tra headers/body và áp giới hạn byte/timeouts?
- [ ] Có dùng UTF-8 byte length cho fixed response?
- [ ] Có phân biệt `sendResponseHeaders(len>0)`, `(0)` và `(-1)`?
- [ ] Có gọi `sendResponseHeaders` trước `getResponseBody`?
- [ ] Có đóng input/output streams/exchange cả khi lỗi?
- [ ] Với filter, có gọi `chain.doFilter` hoặc tự tạo response nếu chặn?
- [ ] Có cấu hình `setExecutor` trước `start` và dọn pool khi stop?
- [ ] Có hiểu `removeContext` khác `stop` và stop không restart?
- [ ] Có áp authN/authZ/TLS nếu endpoint có dữ liệu nhạy cảm?
- [ ] Không tin raw query, encoded path, `Forwarded`/`X-Forwarded-For`?
- [ ] Có kiểm tra JDK26 attribute scoping nếu dùng `getAttribute`/`setAttribute`?
- [ ] Có kiểm thử 404/405/413, percent encoding, Unicode, path prefix và resource cleanup?
- [ ] Có quan sát behavior thật trên runtime/provider mà ứng dụng triển khai?

## 15. Những lỗi phổ biến

| Sai lầm | Tác động | Cách sửa |
| --- | --- | --- |
| Gọi `createContext("/api")` rồi nghĩ chỉ match `/api/...`. | Có thể match cả `/api2`. | `/api/` + exact root path policy. |
| Giả định router hiểu REST methods. | POST có thể vào GET handler. | Check `getRequestMethod`. |
| Không kiểm tra exact path trong `/hello`. | `/helloworld` vào cùng handler. | So `getRawPath()` với `"/hello"`. |
| Coi query là path. | Route sai logic. | Tách `getRawPath` và `getRawQuery`. |
| Decode path nhiều lần. | Path traversal/route confusion. | Định nghĩa và test một decoding policy. |
| Gọi `sendResponseHeaders(200, text.length())`. | Sai byte length với Unicode. | `text.getBytes(UTF_8).length`. |
| Gửi `0` để biểu diễn body rỗng. | Gửi chunked response. | `-1` cho no-body. |
| Ghi response quá số bytes fixed-length. | `IOException`, connection abort. | Ghi đúng count. |
| Không đóng response output stream. | Exchange không kết thúc, leak. | Try-with-resources hoặc `exchange.close`. |
| Đọc body bằng `readAllBytes()` vô giới hạn. | Heap/DoS. | Limit/streaming. |
| Đặt header sau `sendResponseHeaders`. | Header có thể không đến client. | Set trước. |
| Gọi `setExecutor` sau `start`. | `IllegalStateException`. | Set executor trước start. |
| Không dọn thread pool. | JVM/test có thể không thoát. | Shutdown pool trong finally. |
| Stop rồi start lại cùng server. | Không được hỗ trợ. | Tạo instance mới. |
| Cho rằng removeContext chặn request đang xử lý. | In-flight exchange vẫn chạy. | Phân biệt remove route và cancellation. |
| Giả định `getAttribute` luôn là shared context state. | Khác biệt từ JDK26. | `getHttpContext().getAttributes()` cho shared config. |
| Cho rằng Headers request writable. | API chỉ đọc. | Chỉ sửa response headers. |
| Log body/headers chứa tokens. | Lộ dữ liệu. | Sanitize/redact. |
| Bind wildcard trong demo. | Phơi endpoint cho máy khác. | Bind loopback. |
| Dùng server tối giản làm internet gateway không có auth. | Thiếu các lớp bảo vệ. | Reverse proxy/TLS/auth/rate limits. |

## 16. Bài tập thực hành

**A — Prefix trap.** Đổi context `"/api/"` thành `"/api"`, gọi `GET /api2`. Phân tích handler nào nhận và vì sao. Sau đó khôi phục slash cuối để chặn match ngoài ý muốn.

**B — Longest prefix.** Thêm context `"/api/items/special/"` và gọi `/api/items/special/42`. So sánh với `/api/items/` và `/api/`.

**C — Case sensitivity.** Gọi `/HELLO`, `/Hello`, `/hello`; mô tả kết quả. Nếu yêu cầu case-insensitive application route, thiết kế riêng policy và negative tests.

**D — Query vs path.** Gọi `GET /api/items/42?lang=vi&debug=1`. Xây parser query an toàn có percent decoding một lần, không tự chấp nhận duplicate parameter không kiểm soát.

**E — UTF-8 length.** Gửi response `"Chào 😀"` với fixed-length; so `String.length()` và `getBytes(UTF_8).length`. Tại sao phải dùng số bytes?

**F — Method policy.** Thêm `PUT /api/items/42` với validation; nếu chưa hỗ trợ, trả 405 và `Allow: GET` thay vì 500.

**G — Request limit.** Thay `MAX_ECHO_BYTES` thành 32; thử 31, 32 và 33 bytes (không phải 31/32/33 ký tự Unicode). Xác minh status 200/413.

**H — Chunked.** Gửi ba chunks bằng `sendResponseHeaders(200,0)`. Quan sát `HttpClient` trả một body đã được ghép như thế nào.

**I — No body.** Trả `204` với `-1`, thử dùng `0` trong sandbox và xem khác biệt headers/connection lifecycle.

**J — Filters.** Thêm `Filter.beforeHandler` để gắn một correlationId vào exchange. Đừng lưu per-request state trên context map shared.

**K — Context removal.** Xóa `HttpContext /health`, gọi lại /health khi có `/` fallback; giải thích vì sao fallback (không phải built-in 404) nhận request.

**L — Concurrency.** Gửi 20 HTTP requests song song trên localhost và dùng fixed thread pool 4 threads. Đo throughput/latency, không khẳng định pool size 4 nghĩa tối đa 4 TCP connections.

**M — Binding.** So sánh loopback với wildcard bind trong môi trường được phép. Giải thích vì sao demo không nên tự mở trên 0.0.0.0.

**N — JDK26 attributes.** Lưu config `getHttpContext().getAttributes()` và per-request data `exchange.setAttribute`; test hành vi theo phiên bản JDK đang triển khai, tránh dựa vào semantics cũ.

## 17. Câu hỏi tự kiểm tra

**1. `HttpHandler` là gì?** — Interface có `handle(HttpExchange)` xử lý một request được chuyển đến bởi HttpServer.

**2. `HttpContext` dùng để làm gì?** — Ánh xạ context path đến handler, có thể thêm filters và authenticator.

**3. HttpServer chọn context nào khi có nhiều đường dẫn khớp?** — Context có **literal prefix dài nhất**, theo JDK 17–26 mặc định.

**4. `/hello` có match `/helloworld` không?** — Có theo literal prefix; handler phải kiểm tra exact path nếu chỉ muốn /hello.

**5. Router tự phân biệt GET và POST không?** — Không. Method được kiểm tra trong handler/filter.

**6. Query `?x=1` có tham gia so context path không?** — Không. Context matching xét path.

**7. `getRawPath()` khác `getPath()`?** — Raw giữ percent-encoded characters; decoded path chuyển encoding thành ký tự tương ứng.

**8. `sendResponseHeaders(200, 0)` nghĩa không có body?** — Không; `0` nghĩa chunked, `-1` mới là no-body.

**9. Khi response fixed-length có Unicode, dùng length nào?** — Số bytes UTF-8 của mảng gửi, không phải `String.length()`.

**10. Nếu handler không đóng response output stream?** — Exchange có thể không kết thúc, làm cạn resources/treo client.

**11. Vì sao dùng port 0 trong test?** — Cho OS chọn port trống, tránh xung đột; đọc qua `server.getAddress().getPort()`.

**12. `setExecutor` nên gọi trước hay sau `start`?** — Trước; sau start có thể ném IllegalStateException.

**13. `removeContext` có dừng toàn server không?** — Không, chỉ bỏ registration của context; server tiếp tục phục vụ routes khác.

**14. Có thể restart cùng HttpServer sau `stop` không?** — Không; phải tạo server mới.

**15. JDK26 có thay đổi gì về `HttpExchange` attributes?** — Mặc định per-exchange; cấu hình dùng chung nên dùng `HttpContext.getAttributes`.

**16. Hai chương trình ví dụ cần internet hay Maven?** — Không. Chỉ dùng JDK và localhost, biên dịch Java 17 target, chạy trên JDK 24 đã kiểm chứng.

## 18. Tài liệu chính thức hiện hành

- [HttpServer — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): create/bind/start/stop/createContext/removeContext, longest literal prefix matching, backlog và executor.
- [HttpExchange — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request/response lifecycle, headers, streams, `sendResponseHeaders` và constants mới từ JDK26.
- [HttpHandler — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): `handle(HttpExchange)`.
- [HttpContext — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): context path/handler/filter/authenticator/attributes.
- [Filter — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html): `beforeHandler`, `afterHandler`, `doFilter`.
- [Headers — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): case-insensitive names, multiple values và getFirst.
- [jdk.httpserver module summary — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/module-summary.html): phạm vi server tối giản, config/limits và **thay đổi exchange attributes JDK26**.
- [HttpServer — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): API tương thích với `javac --release 17`.
- [HttpExchange — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): rõ `0` chunked, `-1` no-body, streams/headers lifecycle.
- [HttpClient — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client chuẩn JDK được dùng để gửi integration requests đến loopback.

**Ghi nhớ:** `HttpServer` định tuyến theo **context path tiền tố literal dài nhất**, không tự chọn method/route parameters; `HttpHandler` xử lý và `HttpExchange` nắm toàn bộ request-response lifecycle. Gọi `sendResponseHeaders` trước khi ghi body, tính **đúng số bytes UTF-8**, phân biệt **0 = chunked** và **-1 = no body**, và luôn đóng exchange. Trong hệ thống thật, bổ sung validation, auth, TLS, rate limits và tài nguyên giới hạn; với JDK26, tránh dựa vào hành vi shared `HttpExchange` attributes cũ.
