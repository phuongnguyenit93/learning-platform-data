# HttpHandler và HttpExchange trong một yêu cầu — HTTP server của JDK (Java 17+)

## 1. Từ một HTTP request đến một HTTP response: ai chịu trách nhiệm?

Trong module `jdk.httpserver`, JDK cung cấp một HTTP server nhúng tương đối gọn, dùng được cho công cụ nội bộ, thử nghiệm, ví dụ học mạng và một số nhu cầu phục vụ HTTP đơn giản. Các thành phần chính là:

- `HttpServer`: bind địa chỉ/cổng, lắng nghe kết nối TCP, tìm `HttpContext` phù hợp rồi phân phối request.
- `HttpContext`: liên kết một đường dẫn gốc (ví dụ `/api/`) với một `HttpHandler`, có thể bổ sung `Filter` hoặc `Authenticator`.
- `HttpHandler`: **hợp đồng xử lý** một yêu cầu HTTP, với duy nhất method cần implement là `handle(HttpExchange exchange)`.
- `HttpExchange`: **đối tượng đại diện một lượt trao đổi** gồm một HTTP request đã nhận và response mà handler sẽ tạo; chứa request metadata, request body stream, response headers, response status/body stream và thông tin kết nối.

Chữ ký cơ bản:

~~~java
@FunctionalInterface
public interface HttpHandler {
    void handle(HttpExchange exchange) throws IOException;
}
~~~

Đây là **chữ ký API đã rút gọn để minh họa** (không cần tự khai báo interface này khi import `com.sun.net.httpserver.HttpHandler`). `HttpHandler` quyết định **phải làm gì** cho một request. `HttpExchange` cho biết **request nào đang được xử lý**, và cung cấp **cách phát sinh response**.

Điều quan trọng nhất: **mỗi lần gọi `handle(exchange)` đại diện cho một exchange riêng**. Bạn không nên dùng một `HttpExchange` sau khi trao đổi đã hoàn tất, cũng không tự giả định mỗi exchange luôn tương ứng một TCP connection mới: HTTP/1.1 persistent connections có thể phục vụ nhiều exchanges tuần tự trên cùng một kết nối.

Bài thuộc module **Java Advance - networking**, mục cha **HTTP server của JDK**, đề bài trực tiếp **“HttpHandler và HttpExchange trong một yêu cầu”**. Nội dung giải thích vòng đời chuẩn, các method cần hiểu, hai ví dụ Java 17+ độc lập đã kiểm thử và những lỗi thường gặp khi tự xây server nhỏ.

## 2. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Mô tả quan hệ `HttpServer → HttpContext → HttpHandler.handle(HttpExchange)`.
2. Phân biệt **handler dùng lại** với **exchange gắn với request/response cụ thể**, tránh để trạng thái request vào field dùng chung.
3. Dùng `getRequestMethod()`, `getRequestURI()`, `getRequestHeaders()`, `getRequestBody()` để đọc request; hiểu kiểu dữ liệu và giới hạn của từng API.
4. Dùng `getResponseHeaders()`, `sendResponseHeaders(status, length)`, `getResponseBody()` để trả response đúng thứ tự.
5. Hiểu ba chế độ response-length đặc trưng của JDK server: **dương = fixed byte count**, **0 = chunked transfer encoding**, **-1 = không có response body**.
6. Biết vì sao **response body length là byte UTF-8**, không phải số ký tự Java `String.length()`.
7. Đảm bảo **đóng exchange**, tiêu thụ/đóng request body và đóng response output, kể cả khi xảy ra lỗi.
8. Phân loại 200, 204, 404, 405, 413, 415 và dùng response headers như `Content-Type`/`Allow` phù hợp.
9. Biết context mapping là **prefix path selection**, không phải router REST tự động theo method/route đầy đủ.
10. Thiết kế giới hạn body, timeout, concurrency, authentication, error response và logging an toàn.
11. Chạy hai chương trình Java 17+: **vòng đời handler/exchange** và **fixed/chunked/no-body/HEAD**.
12. Phân biệt phương thức HTTP server nhúng trong JDK với `java.net.http.HttpClient` ở phía client và các framework production.

## 3. Sơ đồ vòng đời: một request đi qua những gì?

~~~text
HTTP client                         JDK HttpServer
    |                                     |
    | TCP connect + HTTP request         |
    |------------------------------------>|
    |                             accept / parse HTTP/1.1
    |                                     |
    |                         tìm HttpContext theo URI path
    |                                     |
    |                           HttpHandler.handle(exchange)
    |                                     |
    |                           +---------+-----------+
    |                           | request metadata    |
    |                           | request body stream |
    |                           +---------+-----------+
    |                                     |
    |                           business logic/validation
    |                                     |
    |                           +---------+-----------+
    |                           | response headers    |
    |                           | sendResponseHeaders |
    |                           | response body bytes |
    |                           +---------+-----------+
    |                                     |
    |<------------------------------------|
    | HTTP status + headers + body        |
    |                                     |
    |                      close streams / close exchange
    |                                     |
    |                         connection reuse nếu thích hợp
~~~

**Một `HttpExchange` có hai phía:**

~~~text
                  HttpExchange
             +---------------------+
  REQUEST    | getRequestMethod    |     GET /api/hello
             | getRequestURI       |     /api/hello?lang=vi
             | getRequestHeaders   |     Accept: text/plain
             | getRequestBody      |     InputStream
             +---------------------+
  RESPONSE   | getResponseHeaders  |     Content-Type: text/plain
             | sendResponseHeaders |     HTTP status 200, length N
             | getResponseBody     |     OutputStream
             +---------------------+
                  close()
~~~

Dữ liệu từ `getRequestHeaders()` là **read-only** theo API, còn `getResponseHeaders()` cho phép handler thêm/sửa response header **trước khi commit**. `sendResponseHeaders(...)` khởi phát việc gửi status/header và quy tắc framing của response; sau thời điểm đó không thể coi headers như chưa gửi.

## 4. Trách nhiệm của bốn đối tượng

| Thành phần | Vòng đời | API tiêu biểu | Trách nhiệm |
| --- | --- | --- | --- |
| `HttpServer` | Từ lúc tạo/bind tới `stop(delay)` | `create`, `createContext`, `setExecutor`, `start`, `stop` | Listener, routing context, dispatch, executor |
| `HttpContext` | Cấu hình context của server | `getPath`, `getHandler`, `getFilters`, `setAuthenticator` | Gắn path prefix với handler, filters, auth |
| `HttpHandler` | Thường được tạo/đăng ký **một lần**, dùng cho nhiều exchanges | `handle(HttpExchange)` | Chạy logic xử lý mỗi exchange |
| `HttpExchange` | Gắn với **một** HTTP request và response | `getRequest*`, `sendResponseHeaders`, `getResponseBody`, `close` | Metadata, streams, response status/body |

### 4.1. Một handler có thể xử lý nhiều exchanges

~~~java
HttpHandler handler = exchange -> {
    try (exchange) {
        byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, body.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body);
        }
    }
};

server.createContext("/health", handler);
~~~

Đây là **mảnh code** bên trong một method có `server`, imports `HttpHandler`, `StandardCharsets` và `OutputStream`; không phải chương trình độc lập. `handler` có thể được JDK gọi nhiều lần cho các exchanges khác nhau.

**Sai thiết kế:** lưu request hiện tại vào một field của handler rồi dùng nó trong thread khác:

~~~java
// SAI: request-specific mutable state không được để dùng chung
private HttpExchange currentExchange;
public void handle(HttpExchange exchange) {
    currentExchange = exchange;
}
~~~

Nếu executor chạy concurrent, exchange B có thể ghi đè exchange A; dù không concurrent, giữ exchange quá vòng đời gây leak/cố dùng stream đã đóng. Dữ liệu request nên là **local variables** trong `handle` hoặc immutable request context được truyền rõ ràng. Shared counters/caches chỉ dùng khi có thread-safety thích hợp.

### 4.2. `HttpContext` chọn handler theo path, không phải theo method

~~~java
server.createContext("/api/", new ApiHandler());
~~~

Handler có thể được gọi cho `/api/hello`, `/api/echo`, `/api/missing`. Java server chọn context theo **đường dẫn URI** (cơ chế prefix, longest matching prefix), **không** tự hiểu rằng `GET /api/hello` và `POST /api/hello` là hai REST endpoints có phương thức hợp lệ khác nhau.

Bạn vẫn phải viết logic kiểm tra:

~~~java
String method = exchange.getRequestMethod();
String path = exchange.getRequestURI().getPath();

if (path.equals("/api/hello") && method.equals("GET")) {
    // Xử lý GET /api/hello.
} else {
    // Gửi 404 hoặc 405 tùy path/method.
}
~~~

Mảnh code trên không standalone. Một context prefix dài hơn có thể được chọn trước prefix ngắn hơn, chẳng hạn `/api/admin/` trước `/api/`, nếu cả hai đã được đăng ký. Context matching **case-sensitive**, không tự decode/normalize URL/path theo policy nghiệp vụ của bạn.

Đừng dựa vào `createContext("/api", ...)` để giả định mọi đường dẫn được phân cách rành mạch theo segment; prefix `/api` cũng có thể khớp `/apix`. Dùng prefix với dấu `/` hợp lý rồi tự kiểm tra route đầy đủ trong handler.

## 5. Đọc một request qua HttpExchange

### 5.1. Method: `getRequestMethod()`

~~~java
String method = exchange.getRequestMethod();
~~~

Giá trị ví dụ `GET`, `POST`, `PUT`, `HEAD`, `DELETE`. TCP không tự hiểu những chuỗi này; đây là thông tin được HTTP server parse và đưa cho handler.

- Xác định resource trước, sau đó quyết định **method nào được hỗ trợ**.
- Với resource đã tồn tại nhưng method không được hỗ trợ, trả **405 Method Not Allowed** và header **`Allow`**.
- Với resource không tồn tại, trả **404 Not Found**.
- Khi cần áp chính sách quyền, phải kiểm tra **authentication/authorization** ở mức ứng dụng, không chỉ nhìn method.
- **GET không được mặc nhiên có quyền đọc mọi thứ**, POST không bảo đảm đã ghi database.

### 5.2. URI: `getRequestURI()`

~~~java
URI target = exchange.getRequestURI();
String path = target.getPath();
String rawPath = target.getRawPath();
String query = target.getRawQuery();
~~~

Đây là mảnh code bên trong handler, cần import `java.net.URI`. Ví dụ request:

~~~http
GET /api/hello?lang=vi HTTP/1.1
Host: localhost

~~~

Tương ứng:

~~~text
getPath()     -> /api/hello
getRawPath()  -> /api/hello
getRawQuery() -> lang=vi
~~~

**Cẩn thận với percent-encoding:** `getPath()` trả path dạng được giải mã theo URI semantics, `getRawPath()` giữ escaped characters; `getRawQuery()` **không** tự biến query thành map. Đừng lấy `getRawQuery()` rồi split bằng mọi dấu `&`/`=` để làm URL parser production nếu chưa xử lý percent encoding, duplicate parameters và character encoding.

Không dùng `URI.getPath()` trực tiếp làm đường dẫn filesystem để đọc file tùy ý (nguy cơ traversal/normalization, encoded separators). Tên route là **application resource**, không nhất thiết liên quan file vật lý.

### 5.3. Request headers: `getRequestHeaders()`

~~~java
Headers requestHeaders = exchange.getRequestHeaders();
String contentType = requestHeaders.getFirst("Content-Type");
String accept = requestHeaders.getFirst("Accept");
~~~

Mảnh code với import `com.sun.net.httpserver.Headers`. Keys **không phân biệt hoa thường** theo HTTP semantics, nhưng header field values có thể xuất hiện **nhiều lần**. `getFirst(...)` thuận tiện khi policy chấp nhận một giá trị đơn; với `Cookie`, `Set-Cookie` hoặc nhiều header lines, cần hiểu quy tắc của từng field.

- **Đọc-only:** request headers không phải map để bạn sửa giá trị client gửi.
- **Không tin input:** `Content-Type` chỉ là lời khai của client; vẫn validate bytes/body schema.
- **`Content-Length` không phải giới hạn an toàn**: có thể thiếu do transfer chunked hoặc malformed; phải giới hạn số bytes **thực đọc**.
- **`Host`** không phải bằng chứng resource đáng tin; nếu tạo absolute redirects/links dựa Host, cần allowlist authority.
- **`Authorization`** là dữ liệu nhạy cảm; không log raw token/basic credentials.

### 5.4. Request body: `getRequestBody()`

~~~java
try (InputStream input = exchange.getRequestBody()) {
    byte[] requestBytes = input.readNBytes(65);
    // Ví dụ này chỉ giữ tối đa 65 bytes vào mảng.
}
~~~

Đây là mảnh code, imports `java.io.InputStream`. Với body limit 64 bytes trong demo, đọc tối đa **65 bytes** cho phép phát hiện body vượt hạn, không đọc toàn bộ vào heap vô giới hạn.

**Vòng đời request body:**

- `getRequestBody()` trả `InputStream` của request **đang xử lý**, không phải stream của toàn bộ TCP connection.
- Bạn nên **đọc hết request body** khi thích hợp rồi đóng stream. Đóng sớm có thể khiến underlying TCP connection không thể reuse; JDK chỉ có thể tự drain số byte còn lại **đến một giới hạn phụ thuộc implementation**.
- `getRequestBody()` gọi nhiều lần vẫn trả **cùng stream**, không tự rewind về đầu.
- Không gọi `readAllBytes()` trên input đến từ Internet khi không có giới hạn body; attacker có thể gửi content rất lớn hoặc chậm.
- Khi endpoint từ chối sớm vì 413/415, có thể quyết định đóng connection thay vì drain body lớn, sau khi response/cleanup đúng policy.
- Nếu đã tiêu thụ body cho logging, parser business không thể tự đọc lại trừ khi bạn buffer có giới hạn hoặc tái tạo stream qua filter.
- Đừng đọc body nếu business không cần nó rồi tự động giữ connection như chắc chắn được reuse; tùy JDK/cách đóng và kích thước còn lại.

**Ví dụ giới hạn nhận payload:**

~~~java
int maxBytes = 64 * 1024;
byte[] bounded = exchange.getRequestBody().readNBytes(maxBytes + 1);
if (bounded.length > maxBytes) {
    exchange.sendResponseHeaders(413, -1);
    return; // try(exchange) bên ngoài sẽ cleanup.
}
~~~

Đây là mảnh code minh họa, không standalone, nhưng thể hiện rõ **đếm bytes thực** thay vì chỉ kiểm tra Content-Length. Production có thể cần streaming parser/sink, tổng deadline và giới hạn sau decompression nữa.

## 6. Tạo response theo đúng thứ tự: headers → sendResponseHeaders → body

Vòng đời điển hình theo API:

~~~text
(1) getRequestMethod() / getRequestURI() / getRequestHeaders()
(2) getRequestBody() -> consume & close (nếu phù hợp)
(3) getResponseHeaders() -> set Content-Type, Cache-Control, Allow...
(4) sendResponseHeaders(status, responseLength)
(5) getResponseBody() -> write bytes -> close
(6) close HttpExchange (try-with-resources)
~~~

Phần lõi:

~~~java
byte[] bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);

exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(200, bytes.length);

try (OutputStream out = exchange.getResponseBody()) {
    out.write(bytes);
}
~~~

Mảnh code này cần `exchange` đang còn mở, imports `StandardCharsets` và `OutputStream`. Gọi `sendResponseHeaders` **trước** `getResponseBody` là bắt buộc; nếu cố gọi body stream trước, bạn đi ngược lifecycle.

**Response headers nên được cấu hình trước khi gửi:** sau `sendResponseHeaders`, response headers đã được gửi, không nên tiếp tục thêm `Content-Type`/`Allow` với hy vọng client sẽ thấy.

### 6.1. Tại sao tính số byte, không lấy String.length()?

`"café"` là 4 ký tự Java nhưng **5 bytes** ở UTF-8 (`c` `a` `f` = 3, `é` = 2). Vì vậy:

~~~java
String text = "café";
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
System.out.println(text.length());  // 4
System.out.println(bytes.length);   // 5
~~~

Đây là mảnh code trong method. Với `sendResponseHeaders(200, 5)`, handler phải ghi **đúng 5 bytes**. Dùng `String.length()==4` làm fixed length sẽ làm response body sai framing, có thể khiến `OutputStream.write(...)` ném `IOException` và exchange bị abort.

### 6.2. Ba chế độ của `sendResponseHeaders(status, length)`

| `responseLength` | Ý nghĩa theo JDK HTTP server | Cách kết thúc |
| --- | --- | --- |
| **dương** (ví dụ `5`) | Fixed response body length, phải gửi **đúng N bytes** | Ghi N bytes rồi close `OutputStream` |
| **0** | Bật **chunked transfer encoding** (HTTP/1.1), số bytes tùy ý | Ghi 0..N bytes rồi close để phát chunk cuối |
| **-1** (hoặc nhỏ hơn) | **Không có response body** | Không ghi body; đóng exchange/output đúng lifecycle |

**Cú pháp quan trọng:** `sendResponseHeaders(200, 0)` **không** có nghĩa “trả response rỗng với độ dài cố định 0”. Nó chọn **chunked**. Muốn không có body, dùng `-1`, đặc biệt với `204 No Content`, `304 Not Modified` và HEAD phù hợp.

**Fixed-length chính xác:** nếu ghi quá N bytes, `OutputStream.write()` ném `IOException`; nếu ghi ít hơn N bytes, `OutputStream.close()` ném `IOException`. JDK abort exchange và đóng underlying TCP connection trong các tình huống này.

**Không set Content-Length bằng tay cho mọi response:** khi dùng `sendResponseHeaders(status, bytes.length)`, JDK quản lý framing/length tương ứng. Với HEAD có thể cung cấp header độ dài **giả định của GET** để client hiểu metadata, dù không gửi body; xem demo thứ hai.

### 6.3. Response không có body

~~~java
exchange.sendResponseHeaders(204, -1);
~~~

Đây là mảnh code trong handler. Không cần viết `"null"`, `"{}"` hoặc newline làm body của 204. Khi client nhận `204`, `HttpResponse.BodyHandlers.ofByteArray()` cho mảng rỗng.

Một response `404`, `400`, `405` có thể chứa body mô tả lỗi nhỏ, có Content-Type phù hợp. `HttpClient.send(...)` không tự ném exception chỉ vì HTTP status lỗi; client có thể đọc status và body thông thường.

### 6.4. Response headers và `Allow`

Ví dụ method không hỗ trợ:

~~~java
exchange.getResponseHeaders().set("Allow", "GET");
byte[] message = "method not allowed".getBytes(StandardCharsets.UTF_8);
exchange.sendResponseHeaders(405, message.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(message);
}
~~~

Nếu resource tồn tại nhưng method không được hỗ trợ, header `Allow` theo HTTP semantics nên liệt kê các methods hiện có. Không nhầm `405` với `404`: một cái nói **resource có thể tồn tại nhưng method bị từ chối**, cái kia nói **target không tìm thấy hoặc không thể tiết lộ**.

## 7. Đóng streams và đóng exchange: quy tắc không thể bỏ qua

`HttpExchange` implements `AutoCloseable` nên dùng:

~~~java
@Override
public void handle(HttpExchange exchange) throws IOException {
    try (exchange) {
        // Đọc request, xử lý, gửi response.
    }
}
~~~

Đây là mảnh method trong một `HttpHandler`, cần import `IOException`. JDK `HttpExchange.close()` sẽ cố đóng request `InputStream` rồi response `OutputStream`. Theo Oracle Java 17:

- Exchange kết thúc khi cả request input stream và response output stream được đóng.
- Đóng response output stream cũng **ngầm đóng** request input nếu nó chưa đóng.
- Nên tiêu thụ đầy đủ request body trước khi close nếu muốn connection có thể tái sử dụng.
- Không đóng exchange có thể làm rò tài nguyên/không tái sử dụng được connection.
- Việc gọi `getRequestBody()`/`getResponseBody()` nhiều lần trả cùng stream, không tạo stream mới độc lập.
- Nếu bạn tự đóng output stream trong try-with-resources và sau đó `exchange.close()` được gọi, cách đóng lặp đó tương thích với mô hình cleanup, nhưng **không** được dùng exchange sau khi close.

### 7.1. Vì sao close cực kỳ quan trọng với HTTP keep-alive?

~~~text
Client TCP connection
   |
   +-- HTTP request A → HttpExchange A → body/close
   |
   +-- HTTP request B → HttpExchange B → body/close
   |
   +-- HTTP request C → HttpExchange C → body/close
~~~

JDK server có thể tái sử dụng connection cho nhiều HTTP/1.1 requests, tùy framing, trạng thái streams, networking và headers. Nếu handler A không consume/close response output, B có thể bị cản trở hoặc connection không được reuse.

**Không tuyên bố** “`try(exchange)` luôn tái sử dụng connection”: khi handler bỏ unread request body lớn, JDK không thể lúc nào cũng drain hết; nó có thể đóng connection để tránh lẫn framing. Response header `Connection: close` cũng có thể buộc đóng connection sau exchange theo implementation.

### 7.2. Xử lý exception đúng thời điểm

~~~text
Trước sendResponseHeaders:
  Còn khả năng chọn status 4xx/5xx phù hợp.

Sau sendResponseHeaders:
  Status/headers đã commit → không thể tự gửi response 500 thứ hai
  cùng một exchange khi write body lỗi.
~~~

Một số lỗi:

- `IOException` khi client disconnect hoặc TCP write fail.
- Body decoder/validator báo dữ liệu không hợp lệ: nếu chưa commit response, trả `400 Bad Request`.
- File/database lỗi: trả `500 Internal Server Error` nếu response chưa commit và vẫn có khả năng ghi.
- Response stream ghi thiếu/ghi thừa fixed length: `IOException` và exchange có thể bị abort.
- Thread interrupted/cancellation: không cố gửi tiếp response với streams đã hỏng.

**Anti-pattern:**

~~~java
try {
    exchange.sendResponseHeaders(200, declaredLength);
    exchange.getResponseBody().write(data);
} catch (Exception ex) {
    // SAI: headers 200 có thể đã gửi. Không thể gửi thêm 500 chuẩn.
    exchange.sendResponseHeaders(500, -1);
}
~~~

Mảnh code cố ý **sai**, không phải ví dụ nên chạy. Hãy validate/chuẩn bị response trước khi commit; nếu đã commit rồi write fail, log/cancel/close chứ không tự viết một HTTP response mới chen vào body cũ.

## 8. Demo #1 chạy độc lập: handler định tuyến method và quản lý một exchange

### 8.1. Hợp đồng ví dụ

Chương trình có một HTTP server **chỉ bind loopback `127.0.0.1`** và tạo context prefix `/api/`. `ApiHandler.handle(...)` thực thi:

| Request | Kết quả |
| --- | --- |
| `GET /api/hello?lang=vi` | `200`, body `Xin chào` UTF-8 |
| `POST /api/echo` với `text/plain` và body `abc` | `200`, body `echo:abc`; header `X-Handled-Method: POST` |
| `DELETE /api/hello` | `405`, header `Allow: GET` |
| `GET /api/empty` | `204`, không có body |
| `POST /api/echo` với `application/json` | `415 Unsupported Media Type` |
| `POST /api/echo` với 65 bytes text | `413 Content Too Large` do giới hạn demo 64 bytes |
| `GET /api/missing` | `404 Not Found` |

Đây là một **API tối giản có kiểm soát**, không phải server production. Trường hợp POST thiếu Content-Type bị trả 415; ở ví dụ Java chỉ dùng `startsWith("text/plain")` để minh họa header check, **không** phải parser media type hoàn chỉnh (ví dụ `text/plain-malicious` cũng khớp prefix; production phải parse theo chuẩn).

### 8.2. Tệp `HandlerExchangeLifecycleDemo.java`

~~~java
import com.sun.net.httpserver.*;
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
import java.util.Locale;

public class HandlerExchangeLifecycleDemo {
    static final int MAX_BODY = 64;

    static class ApiHandler implements HttpHandler {
        @Override public void handle(HttpExchange exchange) throws IOException {
            try (exchange) {
                String path = exchange.getRequestURI().getPath();
                String method = exchange.getRequestMethod();
                if (path.equals("/api/hello")) {
                    if (!method.equals("GET")) {
                        exchange.getResponseHeaders().set("Allow", "GET");
                        send(exchange, 405, "method not allowed");
                        return;
                    }
                    String rawQuery = exchange.getRequestURI().getRawQuery();
                    send(exchange, 200, rawQuery != null &&
                            rawQuery.equals("lang=en") ? "Hello" : "Xin chào");
                    return;
                }
                if (path.equals("/api/echo")) {
                    if (!method.equals("POST")) {
                        exchange.getResponseHeaders().set("Allow", "POST");
                        send(exchange, 405, "method not allowed");
                        return;
                    }
                    String type = exchange.getRequestHeaders()
                            .getFirst("Content-Type");
                    if (type == null || !type.toLowerCase(Locale.ROOT)
                            .startsWith("text/plain")) {
                        send(exchange, 415, "unsupported media type");
                        return;
                    }
                    byte[] body;
                    try (InputStream input = exchange.getRequestBody()) {
                        body = input.readNBytes(MAX_BODY + 1);
                    }
                    if (body.length > MAX_BODY) {
                        send(exchange, 413, "too large");
                        return;
                    }
                    exchange.getResponseHeaders().set("X-Handled-Method", method);
                    send(exchange, 200, "echo:" +
                            new String(body, StandardCharsets.UTF_8));
                    return;
                }
                if (path.equals("/api/empty")) {
                    if (!method.equals("GET")) {
                        exchange.getResponseHeaders().set("Allow", "GET");
                        send(exchange, 405, "method not allowed");
                        return;
                    }
                    exchange.sendResponseHeaders(204, -1);
                    return;
                }
                send(exchange, 404, "not found");
            }
        }

        static void send(HttpExchange exchange, int status, String text)
                throws IOException {
            byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status,
                    bytes.length == 0 ? -1 : bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext("/api/", new ApiHandler());
        server.start();
        try {
            URI root = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();

            HttpResponse<String> greeting = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/hello?lang=vi"))
                            .timeout(Duration.ofSeconds(5)).GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("GET hello: " + greeting.statusCode()
                    + " | " + greeting.body());
            System.out.println("GET media: " + greeting.headers()
                    .firstValue("Content-Type").orElse("missing"));

            HttpResponse<String> echo = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/echo"))
                            .header("Content-Type", "text/plain; charset=UTF-8")
                            .timeout(Duration.ofSeconds(5))
                            .POST(HttpRequest.BodyPublishers.ofString("abc"))
                            .build(),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("POST echo: " + echo.statusCode()
                    + " | " + echo.body());
            System.out.println("POST method observed: " + echo.headers()
                    .firstValue("X-Handled-Method").orElse("missing"));

            HttpResponse<String> badMethod = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/hello"))
                            .timeout(Duration.ofSeconds(5))
                            .method("DELETE", HttpRequest.BodyPublishers.noBody())
                            .build(), HttpResponse.BodyHandlers.ofString());
            System.out.println("DELETE: " + badMethod.statusCode()
                    + " | Allow=" + badMethod.headers()
                    .firstValue("Allow").orElse("missing"));

            HttpResponse<byte[]> empty = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/empty"))
                            .timeout(Duration.ofSeconds(5)).GET().build(),
                    HttpResponse.BodyHandlers.ofByteArray());
            System.out.println("No content: " + empty.statusCode()
                    + " | bytes=" + empty.body().length);

            HttpResponse<String> wrong = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/echo"))
                            .header("Content-Type", "application/json")
                            .timeout(Duration.ofSeconds(5))
                            .POST(HttpRequest.BodyPublishers.ofString("{}"))
                            .build(), HttpResponse.BodyHandlers.ofString());
            System.out.println("Wrong media: " + wrong.statusCode());

            HttpResponse<String> huge = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/echo"))
                            .header("Content-Type", "text/plain")
                            .timeout(Duration.ofSeconds(5))
                            .POST(HttpRequest.BodyPublishers.ofString("x".repeat(65)))
                            .build(), HttpResponse.BodyHandlers.ofString());
            System.out.println("Oversized: " + huge.statusCode());

            HttpResponse<String> unknown = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/missing"))
                            .timeout(Duration.ofSeconds(5)).GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("Unknown route: " + unknown.statusCode());
        } finally {
            server.stop(0);
        }
    }
}
~~~

### 8.3. Biên dịch, chạy, stdout đã kiểm chứng

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver HandlerExchangeLifecycleDemo.java
java --add-modules jdk.httpserver HandlerExchangeLifecycleDemo
~~~

**Stdout từ bài test thực tế trên OpenJDK 24 khi compile `--release 17`:**

~~~text
GET hello: 200 | Xin chào
GET media: text/plain; charset=UTF-8
POST echo: 200 | echo:abc
POST method observed: POST
DELETE: 405 | Allow=GET
No content: 204 | bytes=0
Wrong media: 415
Oversized: 413
Unknown route: 404
~~~

### 8.4. Giải thích thứ tự hành động trong một request

**GET `/api/hello?lang=vi`:**

1. `HttpServer` chọn context prefix `/api/`.
2. `ApiHandler.handle(exchange)` được gọi với exchange riêng.
3. Handler đọc `getRequestURI().getPath()` và `getRequestMethod()`.
4. Nó kiểm tra method GET; đọc `getRawQuery()` nhưng chỉ so đúng giá trị demo `lang=en`, trường hợp khác trả chuỗi UTF-8 `Xin chào`.
5. `send(...)` mã hóa `String` thành `byte[]` theo UTF-8, set `Content-Type`.
6. `sendResponseHeaders(200, bytes.length)` commit status/headers và fixed byte length.
7. `getResponseBody()` trả output stream; handler ghi đúng bytes.
8. `OutputStream.close()` và `HttpExchange.close()` kết thúc exchange.
9. Client `HttpClient.send(...)` nhận status 200 và body đúng.

**POST `/api/echo`:**

1. Handler xác nhận path, method POST và header Content-Type.
2. Đọc tối đa 65 bytes từ request body; payload `abc` có 3 bytes nên không vượt 64.
3. Đặt response header `X-Handled-Method: POST` để demo chứng minh handler đã đọc method.
4. Trả `echo:abc` với HTTP 200 và fixed byte length.
5. Client đọc status, body, header — **cùng một exchange** chứa input của POST và output phản hồi tương ứng.

**DELETE `/api/hello`:**

1. Resource path hợp lệ nhưng method DELETE không hỗ trợ.
2. Handler đặt `Allow: GET` rồi gửi 405.
3. Client nhận status 405 bình thường. Nó không phải TCP error hay exception vì client cho phép nhận HTTP error response.

**GET `/api/empty`:** gửi 204 với length -1, client nhận mảng byte length 0.

**POST quá 64 bytes:** handler phát hiện request body vượt policy và trả 413. Việc đóng request body khi còn unread dữ liệu có thể làm server **không tái sử dụng connection**; demo không cố chứng minh keepalive luôn hoạt động trong nhánh này.

### 8.5. Vì sao code demo chưa phù hợp production?

- `Content-Type` được kiểm tra bằng prefix; có thể nhầm `text/plain-malicious`. Cần media type parser/allowlist chuẩn.
- Query `lang=vi` chưa qua URL query decoder hoàn chỉnh; trong production phải xử lý percent-encoding, duplicate keys, invalid characters.
- Đọc 65 bytes chỉ minh họa hard cap cho payload nhỏ; API upload thực cần streaming quotas, deadlines và content validation.
- Không có authentication/authorization, rate limiting, CSRF/cookie policy, security headers, access logs hoặc HTTP/TLS termination.
- Server chỉ bind loopback và không có security checks cần thiết nếu mở Internet; không nên đơn giản thay `127.0.0.1` bằng `0.0.0.0` rồi coi là an toàn.
- `HttpServer` built-in không phải full framework; nếu cần production endpoint, phải đánh giá server/platform và security/observability requirements.
- Một handler dùng `getRequestURI().getPath()` làm path để route; không tự giải quyết canonicalization, encoded separators, path traversal nếu route liên quan filesystem.
- `server.stop(0)` trong lab dừng server ngay khi client test xong; production thường muốn graceful drain và worker shutdown policy.
- Mọi response dùng `text/plain`; một ứng dụng REST thật có thể chọn `application/json` hoặc problem details theo contract.

## 9. Demo #2 chạy độc lập: fixed-length, chunked, 204 và HEAD

Trong API JDK, **số thứ hai của `sendResponseHeaders` quan trọng không kém status**. Ví dụ này kiểm tra bốn exchange do cùng một handler instance xử lý:

1. GET `/fixed`: trả `200`, body `café` UTF-8 = **5 bytes**, fixed length.
2. GET `/chunked`: gọi `sendResponseHeaders(200, 0)` và ghi `part-` + `two`, trả **8 bytes** với `Transfer-Encoding: chunked`.
3. GET `/none`: gọi `sendResponseHeaders(204, -1)`, trả **0 bytes** và không có chunked body.
4. HEAD `/head`: chỉ trả headers; `Content-Length: 5` biểu diễn hypothetical GET payload `hello`, nhưng body **0 bytes**.
5. Handler dùng `AtomicInteger` để đếm tổng số `handle(exchange)` được gọi: **4 lần**.

Khác ví dụ trước, server đặt một `ExecutorService` rõ ràng qua `server.setExecutor(workers)`. Việc một handler instance được dùng nhiều lần minh họa chuyện xử lý state dùng chung phải thread-safe: `AtomicInteger` an toàn hơn field `int count++` khi server chạy nhiều request đồng thời.

### 9.1. Tệp `HttpExchangeResponseModesDemo.java`

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
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
import java.util.concurrent.atomic.AtomicInteger;

public class HttpExchangeResponseModesDemo {
    static final class ModeHandler implements HttpHandler {
        final AtomicInteger exchangeCount = new AtomicInteger();

        @Override public void handle(HttpExchange exchange) throws IOException {
            try (exchange) {
                exchangeCount.incrementAndGet();
                String path = exchange.getRequestURI().getPath();
                String method = exchange.getRequestMethod();
                if (path.equals("/fixed") && method.equals("GET")) {
                    byte[] body = "café".getBytes(StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().set("Content-Type",
                            "text/plain; charset=UTF-8");
                    exchange.getResponseHeaders().set("X-Mode", "fixed");
                    exchange.sendResponseHeaders(200, body.length);
                    try (OutputStream out = exchange.getResponseBody()) {
                        out.write(body);
                    }
                    return;
                }
                if (path.equals("/chunked") && method.equals("GET")) {
                    exchange.getResponseHeaders().set("X-Mode", "chunked");
                    exchange.sendResponseHeaders(200, 0);
                    try (OutputStream out = exchange.getResponseBody()) {
                        out.write("part-".getBytes(StandardCharsets.US_ASCII));
                        out.write("two".getBytes(StandardCharsets.US_ASCII));
                    }
                    return;
                }
                if (path.equals("/none") && method.equals("GET")) {
                    exchange.sendResponseHeaders(204, -1);
                    return;
                }
                if (path.equals("/head") && method.equals("HEAD")) {
                    byte[] hypothetical = "hello".getBytes(StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().set(
                            "Content-Length", Integer.toString(hypothetical.length));
                    exchange.getResponseHeaders().set("X-Mode", "head");
                    exchange.sendResponseHeaders(200, -1);
                    return;
                }
                byte[] error = "not found".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(404, error.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(error);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        ModeHandler handler = new ModeHandler();
        server.createContext("/", handler);
        server.setExecutor(workers);
        server.start();
        try {
            URI root = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            for (String path : new String[]{"/fixed","/chunked","/none"}) {
                HttpRequest request = HttpRequest.newBuilder(root.resolve(path))
                        .timeout(Duration.ofSeconds(5)).GET().build();
                HttpResponse<byte[]> response = client.send(
                        request, HttpResponse.BodyHandlers.ofByteArray());
                System.out.println(path + " -> " + response.statusCode()
                        + " | bytes=" + response.body().length
                        + " | transfer=" + response.headers()
                                .firstValue("Transfer-Encoding").orElse("none"));
            }

            HttpRequest head = HttpRequest.newBuilder(root.resolve("/head"))
                    .timeout(Duration.ofSeconds(5))
                    .method("HEAD", HttpRequest.BodyPublishers.noBody())
                    .build();
            HttpResponse<byte[]> response = client.send(
                    head, HttpResponse.BodyHandlers.ofByteArray());
            System.out.println("/head -> " + response.statusCode()
                    + " | bytes=" + response.body().length
                    + " | Content-Length=" + response.headers()
                        .firstValue("Content-Length").orElse("missing"));
            System.out.println("Handler invocations: " +
                    handler.exchangeCount.get());
        } finally {
            server.stop(0);
            workers.shutdown();
            if (!workers.awaitTermination(2, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch với API Java 17:

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver HttpExchangeResponseModesDemo.java
java --add-modules jdk.httpserver HttpExchangeResponseModesDemo
~~~

**Stdout được kiểm chứng thực tế:**

~~~text
/fixed -> 200 | bytes=5 | transfer=none
/chunked -> 200 | bytes=8 | transfer=chunked
/none -> 204 | bytes=0 | transfer=none
/head -> 200 | bytes=0 | Content-Length=5
Handler invocations: 4
~~~

### 9.2. Vì sao fixed và chunked cùng status 200 nhưng khác wire framing?

Cả hai đều có response status 200:

~~~text
/fixed:
  sendResponseHeaders(200, 5) → đúng 5 bytes UTF-8
  Content-Length: 5
  body: café

/chunked:
  sendResponseHeaders(200, 0) → Transfer-Encoding: chunked
  body logic: part-two (8 bytes)
  wire message gồm chunk sizes và chunk terminator

/none:
  sendResponseHeaders(204, -1) → không có body

/head:
  HEAD request
  Content-Length: 5 (độ dài giả định representation GET)
  sendResponseHeaders(200, -1) → không gửi body
~~~

**Cẩn thận:** `HttpResponse<byte[]>.body().length` của client là độ dài **payload đã được HTTP client giải framing**, không tính các byte chunk-size markers trên wire. Vì vậy `/chunked` in 8, không có nghĩa toàn bộ HTTP/1.1 message dài đúng 8 bytes.

### 9.3. Mỗi request có exchange riêng nhưng dùng cùng handler object

Bốn client requests gọi `handle(exchange)` bốn lần. Một object `ModeHandler` dùng chung có thể phục vụ nhiều requests. Field `AtomicInteger exchangeCount` là ví dụ state dùng chung đã được bảo vệ; request-specific `path`, `method` và `exchange` đều là local variables, tránh races giữa requests.

Vì chương trình gửi tuần tự, stdout count=4 là deterministic. Cách test concurrency thực nên gửi `sendAsync` tới cùng endpoint nhiều lần và đồng bộ CountDownLatch/barrier nếu muốn xác minh interleaving; không coi ví dụ tuần tự đã chứng minh thread-safety của mọi app logic.

### 9.4. Tránh hiểu sai HEAD

**HEAD response không có content**, nhưng headers có thể mô tả representation tương ứng với GET. Ở ví dụ này handler đặt `Content-Length: 5` cho payload hypothetical `hello`, sau đó `sendResponseHeaders(200,-1)`, client nhận zero-byte body. Điều này **không** vi phạm length framing của response GET, vì HEAD có semantics “headers như GET, không có content”.

Nếu muốn một endpoint phục vụ cả GET và HEAD, cần bảo đảm headers của HEAD nhất quán với GET khi thích hợp, và không write body đối với HEAD. Không xử lý HEAD bằng cách viết một body rồi tin client sẽ tự bỏ qua.

## 10. Thứ tự gọi API: bảng đúng/sai

| Tình huống | Đúng | Sai dễ mắc |
| --- | --- | --- |
| Đọc request method | `exchange.getRequestMethod()` | Đoán method từ tên URI hoặc TCP port |
| Lấy request path | `exchange.getRequestURI().getPath()` | Đọc nguyên chuỗi request line tự chế |
| Đọc header | `exchange.getRequestHeaders().getFirst(...)` | Cố sửa immutable request headers |
| Đọc body nhỏ | `readNBytes(limit+1)` và validate | `readAllBytes()` vô hạn trên Internet |
| Set response media type | `getResponseHeaders().set(...)` trước send | Set sau `sendResponseHeaders` rồi mong client thấy |
| Send status + fixed length | `sendResponseHeaders(200, bytes.length)` | `sendResponseHeaders(200, text.length())` |
| Không có body | `sendResponseHeaders(204,-1)` | Dùng `0` rồi nghĩ là fixed zero |
| Chunked | `sendResponseHeaders(200,0)` | Tự viết chunk length thủ công vào OutputStream |
| Ghi response | `getResponseBody().write(bytes)` sau send | Gọi getResponseBody trước khi send headers |
| Cleanup | `try(exchange)` và đóng output | Quên close, khiến connection/resources treo |
| Lỗi sau commit | Close/abort và log theo policy | Gửi thêm `sendResponseHeaders(500,...)` |
| Lỗi method | 405 + Allow cho resource tồn tại | Mặc định trả 200 hay 404 cho mọi method |
| Không có context | JDK server có thể tự trả 404 | Tưởng handler luôn được gọi |
| State dùng chung | Atomic/lock/thread-safe executor policy | Field `HttpExchange current` toàn cục |

## 11. HttpServer executor và luồng xử lý: một handler có concurrent không?

`HttpServer.setExecutor(Executor executor)` dùng để quyết định **thread execution context** cho exchanges. Phải gọi trước `start()`; có thể truyền `null` để dùng default executor. Nếu dùng `Executors.newFixedThreadPool(n)`, nhiều exchanges có thể được xử lý đồng thời, nên handler **phải thread-safe**.

~~~java
ExecutorService workers = Executors.newFixedThreadPool(4);
HttpServer server = HttpServer.create(new InetSocketAddress(
        InetAddress.getByName("127.0.0.1"), 8080), 0);

server.createContext("/api/", new ApiHandler());
server.setExecutor(workers);
server.start();

try {
    // Server lắng nghe; phần lifecycle thực tế do ứng dụng quản lý.
} finally {
    server.stop(1);
    workers.shutdown();
}
~~~

Đây là **mảnh code kiến trúc**, không phải chương trình độc lập: cần imports `ExecutorService`/`Executors`, `HttpServer`, `InetAddress`/`InetSocketAddress`, và class `ApiHandler` đã định nghĩa. Nó minh họa thứ tự `setExecutor` trước `start` và ownership của executor, không phải pattern start-then-stop tức thời để copy vào production.

**Lưu ý:**

- Một `HttpHandler` object thường dùng chung giữa nhiều requests; không đặt request body/response stream vào instance fields.
- Không thực hiện business I/O quá lâu trên một số lượng threads hữu hạn; dùng deadlines và backpressure.
- Không tạo một new unbounded thread pool per request, vì dễ tạo resource exhaustion.
- Nếu định nghĩa `setExecutor(customExecutor)`, ứng dụng phải quản lý executor lifecycle theo ownership của nó; `server.stop(...)` không nên được hiểu là tự shutdown mọi custom executor.
- `HttpServer.stop(delay)` chặn request mới, chờ exchanges hiện có hoàn thành hoặc đến khoảng delay tính theo giây, rồi đóng TCP connections; server đã stop **không thể reuse/start lại**.
- Đừng tự giả định default executor của JDK đáp ứng load cao; đọc docs và định cấu hình rõ theo workload.
- Ghi metrics queue length, active handlers, request latency và rejection policy, không log dữ liệu nhạy cảm.

### 11.1. Exchange không phải transaction độc quyền

Có nhiều requests concurrent, mỗi request có `HttpExchange` riêng; đồng thời nhiều exchanges có thể chia sẻ database, cache, cùng một handler, cùng backend. Việc đóng `HttpExchange` **không tự rollback database** hoặc cancel tất cả asynchronous tasks của ứng dụng. Nếu tạo background job, transaction/context phải được quản lý riêng; không giữ reference đến exchange để viết response **sau khi exchange đã close**.

## 12. HttpContext, Filter và Authenticator trong một exchange

`HttpContext` là điểm gắn **middleware**:

~~~text
HttpServer
  |
  +--- HttpContext("/api/")
             |
             +--- Filter #1: request ID/metrics
             +--- Filter #2: request limits
             +--- Authenticator (nếu cấu hình)
             |
             v
          ApiHandler.handle(exchange)
~~~

Một filter có thể **gắn attribute** vào `HttpExchange`:

~~~java
exchange.setAttribute("trace-id", "req-123");
Object trace = exchange.getAttribute("trace-id");
~~~

Đây là mảnh code. Attributes phục vụ chia sẻ dữ liệu nội bộ giữa filters và handler **trên cùng exchange**, không phải HTTP headers được client tự gửi. Không tin `trace-id` như quyền truy cập, và không biến nó thành global mutable state ngoài vòng đời exchange.

Các API liên quan:

- `exchange.getHttpContext()`: context được chọn cho exchange.
- `exchange.getPrincipal()`: `HttpPrincipal` nếu context có authenticator và request đã được xác thực phù hợp, còn không có thể **null**.
- `exchange.getRemoteAddress()`: remote peer socket address; đằng sau reverse proxy có thể là **IP proxy**, không phải IP user thật.
- `exchange.getLocalAddress()`: địa chỉ local mà request tới.
- `exchange.getProtocol()`: protocol string của request, ví dụ `HTTP/1.1`.
- `exchange.getAttribute(name)` / `setAttribute(name,value)`: gắn dữ liệu giữa filters/handler; không nên lạm dụng để lưu persistent session state.

**Không dùng `getRemoteAddress()` thay authentication.** Nếu server nằm sau reverse proxy, dữ liệu từ `Forwarded`/`X-Forwarded-For` cũng phải được xác minh chỉ nhận từ proxy được tin cậy; không lấy IP header bất kỳ của client làm quyền truy cập.

## 13. HTTP/HTTPS và giới hạn của JDK built-in server

`com.sun.net.httpserver` có cả `HttpServer` và `HttpsServer`:

- `HttpServer` phục vụ HTTP thông thường; nếu bind local port để test, client dùng `http://127.0.0.1:port`.
- `HttpsServer` kế thừa các khả năng xử lý exchange của server và cấu hình TLS qua `HttpsConfigurator`; `HttpsExchange` mở rộng `HttpExchange` và có `getSSLSession()`.
- Các API này là **HTTP server nhẹ do JDK cung cấp**, không thay cho container server/framework lớn nếu cần nhiều middleware, protocol upgrades, HTTP/2/3, distributed tracing, auth và production hardening.
- Cả hai ví dụ ở trên dùng HTTP/1.1 trên loopback **không mã hóa** để tách biệt bài học về `HttpHandler`/`HttpExchange`. Đừng gửi credentials thật qua `http://` trên mạng công khai.
- Khi triển khai production-facing API, cần TLS termination, certificate validation, reverse proxy, request limits, timeouts, security headers, auth/authorization và quan sát phù hợp.
- Đừng đoán HttpsExchange tự authenticate một user business chỉ vì TLS thành công; client certificate/mTLS và application identity cần được thiết kế tách biệt.

### 13.1. Không nhầm client `HttpResponse` với server `HttpExchange`

| Phía client | Phía server |
| --- | --- |
| `java.net.http.HttpClient` | `com.sun.net.httpserver.HttpServer` |
| `HttpRequest` | `HttpExchange.getRequestMethod/getRequestURI/...` |
| `HttpResponse<T>` | `HttpExchange.getResponseHeaders/sendResponseHeaders/getResponseBody` |
| `BodyPublisher` gửi request body | `HttpExchange.getRequestBody()` đọc body |
| `BodyHandler<T>` tiêu thụ response body | `HttpExchange.getResponseBody()` ghi response body |
| `client.send(...)` khởi tạo HTTP exchange | `HttpHandler.handle(exchange)` xử lý exchange được dispatch |

**Hai package khác nhau:** client Java 11+ ở `java.net.http`; server nhúng ở `com.sun.net.httpserver` thuộc module `jdk.httpserver`. Không có API chuẩn “server.listen()” trong `HttpClient` và không có `HttpResponse.BodyHandlers` trong `HttpExchange`.

## 14. Status code cho một handler thực tế

| Tình huống | HTTP status phù hợp | Lưu ý |
| --- | --- | --- |
| GET thành công, trả representation | `200 OK` | Content-Type/charset/length đúng |
| POST tạo resource | `201 Created` | Có thể set `Location` |
| POST chấp nhận xử lý async | `202 Accepted` | Không có nghĩa background job đã hoàn tất |
| Xóa thành công, không có content | `204 No Content` | `sendResponseHeaders(204,-1)` |
| Request sai JSON/query | `400 Bad Request` | Không log raw bí mật |
| Chưa xác thực | `401 Unauthorized` | Thường cần `WWW-Authenticate` theo auth scheme |
| Xác thực có nhưng thiếu quyền | `403 Forbidden` | Không dựa vào IP của peer một mình |
| Không tìm thấy resource | `404 Not Found` | Không tự lộ resource riêng tư |
| Method không được hỗ trợ cho resource | `405 Method Not Allowed` | Set `Allow` |
| Conflicting update | `409 Conflict` | Application semantics |
| Body lớn hơn limit | `413 Content Too Large` | Dừng đọc/đóng connection có kiểm soát |
| Content-Type không được hỗ trợ | `415 Unsupported Media Type` | Validate media type thật |
| Quá nhiều requests | `429 Too Many Requests` | Rate limit, có thể `Retry-After` |
| Lỗi server chưa commit response | `500 Internal Server Error` | Tránh lộ stack trace |
| Server tạm không sẵn sàng | `503 Service Unavailable` | Có thể `Retry-After` |

**Một HTTP response không đồng nghĩa business operation chắc chắn commit.** Handler trả 200 có thể vẫn có background tasks; nếu thao tác quan trọng, hợp đồng API phải phân biệt accepted, committed và idempotency đúng.

## 15. Request body và rủi ro bảo mật

### 15.1. Tránh body memory exhaustion

~~~java
// KHÔNG nên dùng trên input không giới hạn từ Internet:
byte[] bytes = exchange.getRequestBody().readAllBytes();
~~~

Cách minh họa an toàn hơn:

~~~java
int limit = 1024 * 1024; // 1 MiB
byte[] bytes = exchange.getRequestBody().readNBytes(limit + 1);
if (bytes.length > limit) {
    exchange.sendResponseHeaders(413, -1);
    return;
}
~~~

Đây là mảnh code; response body/close phải được quản lý ở phạm vi ngoài. **Không** hiểu giới hạn này là chống mọi loại DoS: malicious client có thể mở nhiều connections, giữ request chậm, gửi headers lớn, gửi compressed payload có decoded-size lớn hoặc gây quá tải CPU.

### 15.2. Cần deadline và quota toàn hệ thống

- HTTP request header size và header count: cân nhắc giới hạn cấu hình JDK/server/proxy.
- Request body size: đếm bytes thực, không chỉ tin `Content-Length`.
- Time-to-first-header, body receive timeout, total request duration và response write timeout.
- Connection count, pending requests, executor queue length và active handler quota.
- JSON depth/nesting, decompression ratio, uploaded file scanning và MIME/content validation.
- Authorization theo resource, không chỉ method.
- Trusted proxy network và forwarded headers.
- Resource cleanup khi client disconnect/cancel.
- Rate limiting và circuit breakers cho downstream dependencies.

JDK networking có một số system properties cho built-in HTTP server (ví dụ `sun.net.httpserver.maxReqHeaderSize`, `sun.net.httpserver.maxReqTime` và `sun.net.httpserver.maxRspTime` trong các tài liệu liên quan); **không nên coi những property này là hợp đồng Java SE portable giữa mọi vendor/runtime**. Kiểm tra theo JDK đang triển khai, thêm security ở reverse proxy khi cần, và test thực tế.

### 15.3. Kiểm tra body và charset

`getRequestBody()` trả bytes. Chỉ dùng `new String(bytes, StandardCharsets.UTF_8)` khi contract cho phép UTF-8. Với JSON, parse theo chuẩn và validate schema; với binary, đừng biến thành text. Nếu request chứa `Content-Type: text/plain; charset=ISO-8859-1` thì demo ép UTF-8 có thể không đúng kỳ vọng; production cần định nghĩa charset policy.

Cũng vậy, nếu response gửi UTF-8 thì phải set `Content-Type` với charset phù hợp, tính `bytes.length` và không viết thiếu byte.

## 16. Một request kết thúc lúc nào?

Đây là câu hỏi dễ sai khi mới học `HttpExchange`:

~~~text
Handler handle(...) return
    KHÔNG tự động đồng nghĩa exchange cleanup đúng nếu streams chưa đóng.

OutputStream.close()
    làm response body kết thúc, đồng thời đóng request InputStream nếu còn.

HttpExchange.close()
    đóng request InputStream, rồi response OutputStream;
    nên dùng try-with-resources.

TCP connection close
    không nhất thiết là kết thúc mỗi exchange;
    HTTP/1.1 có thể dùng persistent connection qua nhiều exchanges.
~~~

Trong code demo, `try(exchange)` đảm bảo cleanup trên mọi đường `return` bình thường hoặc exception. `try(OutputStream ...)` làm rõ đúng byte length và thời điểm kết thúc response body.

**Một handler không nên gọi `Thread.sleep(...)` lâu sau khi đã gửi response mà chưa close exchange**, vì giữ tài nguyên không cần thiết. Cũng không nên giữ `exchange` trong background task đã vượt vòng đời request; tách task kết quả và trạng thái business khỏi response stream.

### 16.1. Client disconnect giữa lúc handler đang viết

Hành vi có thể là:

1. Client gửi GET.
2. Server gọi `sendResponseHeaders(200, n)`.
3. Client đóng TCP connection.
4. Handler gọi `getResponseBody().write(bytes)`, nhận `IOException`.
5. Handler đóng exchange trong `finally/try-with-resources`, log gọn và dọn resources.

**Không** cố gửi status 500 sau IOException đó, bởi response 200 đã commit hoặc connection không còn dùng được. Với business side effects, phải dùng transaction/idempotency riêng nếu client cancel giữa chừng.

## 17. Các lỗi thường gặp với HttpHandler/HttpExchange

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `String.length()` làm fixed length | Đếm UTF-16 units, không phải bytes | `String.getBytes(UTF_8).length` |
| Dùng `sendResponseHeaders(200,0)` để trả body rỗng | `0` nghĩa là chunked | `-1` khi thực sự không có body |
| Set Content-Type sau `sendResponseHeaders` | Headers đã commit | Set trước khi send |
| Gọi `getResponseBody()` trước send headers | Sai API lifecycle | `sendResponseHeaders` trước |
| Không đóng output/exchange | Resource leak, connection kẹt | `try(exchange)` và close response |
| Đọc không hết request body nhưng mong keepalive | Input còn bytes, JDK drain giới hạn | Consume thích hợp hoặc đóng connection |
| Dùng `readAllBytes()` với upload lớn | Heap exhaustion | Bounded streaming/byte budget |
| Chỉ kiểm `Content-Length` | Header có thể thiếu/sai | Enforce bytes thực nhận |
| Lưu `HttpExchange` vào field shared | Race, lifetime leak | Request-local variables |
| Coi context path là router REST đầy đủ | Chỉ prefix dispatch, không tự method routing | Route theo method/path trong handler |
| Chọn `createContext("/api")` rồi mong không match `/apix` | Prefix không nhất thiết segment-boundary | Dùng `/api/` và route exact |
| Trả 404 khi resource có nhưng method sai | Bỏ ý nghĩa 405 | Trả 405 và `Allow` |
| Trả response 204 có body JSON | Vi phạm no-content semantics | `sendResponseHeaders(204,-1)` |
| Write fewer/more fixed bytes | JDK ném IOException/abort exchange | Tính byte length, ghi đúng N |
| Gửi 500 sau khi gửi 200 headers | Không thể commit hai responses | Validation trước commit, close khi write fail |
| Không xử lý client disconnect | Exception làm leak resources | Try-with-resources, bounded logging |
| Dùng global counter `int++` với fixedThreadPool | Race lost updates | `AtomicInteger`/lock |
| Dùng field `currentUser` của handler | Shared request state | Local variable/context auth |
| Tin `getRemoteAddress()` là user thật | Reverse proxy biến remote thành proxy IP | Trusted auth/forwarding policy |
| Coi `getPrincipal()` luôn có giá trị | Chỉ có khi context auth hợp lệ | Null check + auth design |
| Cho `HttpServer` public internet không bảo vệ | Thiếu TLS/rate limiting/hardening | Thêm gateway/security hoặc chọn server phù hợp |
| Không shutdown custom ExecutorService | Thread leak | `shutdown`/`awaitTermination` |
| Cố `server.start()` lại sau `stop` | Server không reusable | Tạo HttpServer instance mới |
| Tự đọc HTTP request line từ raw Socket trong handler | JDK đã parse HTTP | Dùng `HttpExchange` APIs |
| Ngầm nghĩ `java.net.http.HttpClient` là server | Phía client khác server module | Phân biệt packages và roles |

## 18. Bộ kiểm thử cần có cho một handler

| Nhóm | Case | Kỳ vọng |
| --- | --- | --- |
| Routing | Path đúng, method đúng | Handler được gọi, response status hợp lệ |
| Routing | Context không khớp | Server trả 404 |
| Routing | Prefix tương tự nhưng resource khác | Router chính xác không cho lộ endpoint |
| Method | DELETE vào endpoint chỉ GET | 405 và Allow |
| Body | POST text hợp lệ | Đọc bounded bytes, response echo |
| Body | POST thiếu/sai Content-Type | 415 hoặc policy đã định |
| Body | Body vượt giới hạn | 413, không OOM |
| Body | Content-Length thiếu | Streaming bounded vẫn đúng nếu protocol cho phép |
| Body | Client gửi body chậm | Deadline, không giữ thread vô hạn |
| Response | Fixed UTF-8 có ký tự đa byte | Exact Content-Length bytes |
| Response | Chunked streaming | Client giải framing, nhận đủ bytes |
| Response | 204 | Zero bytes, không gửi body |
| Response | HEAD | Headers hợp lệ, zero response body |
| Response | Client abort giữa write | IOException được cleanup |
| Response | Handler ném trước commit | Error response thích hợp nếu còn khả năng |
| Response | Handler ném sau commit | Không gửi headers lần hai |
| Concurrency | N requests đồng thời | Shared state thread-safe |
| Shutdown | Stop khi đang xử lý | Bounded stop và executor shutdown |
| Security | Unauthorized resource | 401/403, không lộ dữ liệu |
| Security | Malformed query/URL/path | Reject/normalize theo policy |
| Security | Header oversized và upload lớn | Bound memory/CPU/connections |
| Security | Input chứa credential | Không log raw secrets |

### 18.1. Ưu tiên test deterministic

Hai demos dùng port 0 để OS chọn port trống, bind loopback để không expose Internet, và `HttpClient` local để có stdout tin cậy. `HttpExchangeResponseModesDemo` dùng `AtomicInteger` cho counter và gọi tuần tự, nên output predictable.

Với test chạy đồng thời, đừng dùng `Thread.sleep(100)` rồi giả định tất cả handlers chắc đã chạy. Dùng `CountDownLatch`, `CompletableFuture`, executor có giới hạn, deadline rõ ràng và đảm bảo shutdown.

## 19. Bài tập kèm đáp án

### Bài 1 — Ai gọi handle?

Bạn tạo `HttpServer`, đăng ký `createContext("/hello", handler)` rồi gọi `server.start()`. Ai gọi `handler.handle(exchange)`?

**Đáp án:** JDK `HttpServer` nhận và parse HTTP request, chọn `HttpContext` phù hợp, rồi dispatch đến `HttpHandler.handle(exchange)`. Ứng dụng **không cần tự gọi handle** cho request bình thường.

### Bài 2 — Exchange và TCP connection

Hai GET HTTP/1.1 đi cùng một persistent TCP connection. Có phải cùng một `HttpExchange`?

**Đáp án:** **Không.** Mỗi HTTP request/response exchange có `HttpExchange` riêng; TCP connection có thể được tái sử dụng cho nhiều exchanges.

### Bài 3 — Đọc path và query

Client gửi `GET /api/hello?lang=en`. Handler dùng API nào để lấy method, path và raw query?

**Đáp án:** `getRequestMethod()`, `getRequestURI().getPath()` và `getRequestURI().getRawQuery()`. `getRawQuery()` không phải query map đã decode tự động.

### Bài 4 — Có nên sửa request headers?

**Đáp án:** Không. `getRequestHeaders()` trả read-only headers của request. `getResponseHeaders()` cho phép chuẩn bị headers của **response** trước `sendResponseHeaders`.

### Bài 5 — Fixed length sai vì Unicode

`String text="café"` có `length()==4`, nhưng bytes UTF-8 dài 5. Dùng `sendResponseHeaders(200,4)` rồi ghi 5 bytes thì sao?

**Đáp án:** Với fixed response length=4 mà ghi 5 bytes, JDK có thể ném `IOException` và abort exchange; phải dùng `bytes.length==5`.

### Bài 6 — 0 và -1

`sendResponseHeaders(200,0)` và `sendResponseHeaders(204,-1)` khác nhau ra sao?

**Đáp án:** 0 chọn **chunked transfer encoding** với arbitrary response length, còn -1 báo **không có response body**. Với 204 dùng -1.

### Bài 7 — Quên đóng stream

Handler trả body xong nhưng không đóng `OutputStream` hoặc `HttpExchange`. Điều gì có thể xảy ra?

**Đáp án:** Exchange chưa kết thúc đúng, kết nối/tài nguyên có thể bị giữ hoặc không tái sử dụng. Dùng try-with-resources/close đúng vòng đời.

### Bài 8 — Client không đọc toàn bộ POST body

Handler đọc 100 bytes đầu rồi đóng exchange dù còn 10 MB chưa đọc. Có chắc connection reuse được không?

**Đáp án:** Không. JDK chỉ cố drain unread bytes tới một giới hạn phụ thuộc implementation; TCP connection có thể phải đóng để tránh lẫn framing.

### Bài 9 — Route matching

`server.createContext("/api", handler)` tự đảm bảo request `/apix` không vào handler chưa?

**Đáp án:** Chưa. Context matching dựa prefix, không phải router segment-aware. Dùng context prefix hợp lý và kiểm tra path đầy đủ.

### Bài 10 — Error status sau commit

Handler đã gọi `sendResponseHeaders(200,...)` rồi lúc ghi body phát sinh IOException. Có thể gọi tiếp `sendResponseHeaders(500,...)` không?

**Đáp án:** Không. Response headers/status đã commit; cần cleanup, log và đóng/cancel exchange.

### Bài 11 — POST wrong media type

Resource `/api/echo` chỉ nhận text/plain, client gửi application/json. Status nào phù hợp?

**Đáp án:** `415 Unsupported Media Type` theo contract demo; phải check media type đúng chuẩn và không tin header là bằng chứng payload hợp lệ.

### Bài 12 — Method không hỗ trợ

Resource `/api/hello` có, nhưng client gửi DELETE. Trả gì?

**Đáp án:** `405 Method Not Allowed` với header `Allow: GET`; không coi đây là TCP exception.

### Bài 13 — Shared state

Một `ApiHandler` phục vụ 100 requests concurrent và dùng field `int count++`. Có chắc count=100?

**Đáp án:** Không, `count++` không atomic. Dùng `AtomicInteger.incrementAndGet()`, lock hoặc thiết kế state immutable phù hợp.

### Bài 14 — HEAD trả body

Client gửi HEAD, handler trả 200 kèm 5 bytes body `hello`. Điều gì sai?

**Đáp án:** HEAD không được có response content; headers có thể mang Content-Length của GET hypothetical, nhưng **không ghi body**.

### Bài 15 — Client thấy 404

Khi `HttpClient.send` trả `HttpResponse` có status 404, `HttpServer` handler có chắc đã được gọi không?

**Đáp án:** Không nhất thiết. JDK có thể trả 404 khi **không tìm được HttpContext**; nếu có context prefix nhưng handler không nhận diện resource, handler tự trả 404.

### Bài 16 — `getPrincipal()` null

Nếu context chưa cấu hình `Authenticator`, `exchange.getPrincipal()` chắc chắn là user hiện tại?

**Đáp án:** Không. Có thể **null**. Auth phải được cấu hình/validate theo policy, không tự coi địa chỉ peer là authenticated principal.

### Bài 17 — Stop server

`HttpServer.stop(0)` xong có gọi lại `start()` được không?

**Đáp án:** Không. Theo API, server đã stop không tái sử dụng; cần tạo server mới.

### Bài 18 — Response stream có phải TCP socket stream thuần?

**Đáp án:** Không. `exchange.getResponseBody()` là stream được HTTP server gắn với **response framing**. Bạn gửi representation bytes, không tự viết `HTTP/1.1 200 OK\r\n...` vào stream đó.

## 20. Checklist trước khi hoàn thành bài

- [ ] Tôi hiểu `HttpServer` bind/listen/dispatch qua `HttpContext`.
- [ ] Tôi hiểu `HttpHandler.handle(HttpExchange)` được gọi cho **mỗi HTTP exchange**.
- [ ] Tôi không giữ `HttpExchange` của request trước trong shared fields.
- [ ] Tôi biết `getRequestMethod()`, `getRequestURI()`, `getRequestHeaders()` và `getRequestBody()`.
- [ ] Tôi biết `getRequestHeaders()` read-only, `getResponseHeaders()` mutable.
- [ ] Tôi định tuyến path và method chính xác, không phụ thuộc prefix mặc định.
- [ ] Tôi giới hạn body bằng **bytes thực nhận**, không chỉ `Content-Length`.
- [ ] Tôi hiểu UTF-8 bytes có thể khác `String.length()`.
- [ ] Tôi set headers trước `sendResponseHeaders`.
- [ ] Tôi biết `length > 0` = fixed exact bytes.
- [ ] Tôi biết `length == 0` = chunked, không phải fixed empty.
- [ ] Tôi biết `length == -1` = no response body.
- [ ] Tôi đóng response stream và exchange kể cả khi exception xảy ra.
- [ ] Tôi đọc/đóng request body phù hợp để tránh làm hỏng reuse.
- [ ] Tôi không gửi status 500 thứ hai sau khi status 200 đã commit.
- [ ] Tôi phân biệt 404 vs 405, 413 vs 415, 204 vs 200.
- [ ] Tôi hiểu HEAD trả headers nhưng không gửi body.
- [ ] Tôi biết handler shared state cần thread-safe khi dùng custom executor.
- [ ] Tôi shutdown executor do mình sở hữu và gọi `server.stop(delay)` đúng lifecycle.
- [ ] Tôi không dùng `getRemoteAddress` thay authentication.
- [ ] Tôi không đưa built-in test server ra Internet nếu chưa có TLS/rate limit/hardening.
- [ ] Tôi có test fixed/chunked/no-body/HEAD và Unicode multi-byte response length.
- [ ] Tôi đã biên dịch ví dụ với `javac --release 17` và chạy trong môi trường kiểm soát.

## 21. Tài liệu chính thức để tra cứu

- [Java SE 17 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): module định nghĩa JDK-specific HTTP server API.
- [Java SE 17 — Package com.sun.net.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/package-summary.html): HttpServer, HttpContext, HttpHandler, HttpExchange, Filter và Authenticator.
- [Java SE 17 — HttpHandler](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): `handle(HttpExchange)`.
- [Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): lifecycle chính thức, input/output streams, status/response length/close.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): `create`, `createContext`, `setExecutor`, `start` và `stop`.
- [Java SE 17 — HttpContext](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): path mapping, filter chain, authentication.
- [Java SE 17 — Headers](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): case-insensitive HTTP headers, `getFirst`, `set`.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client được dùng trong hai bài test.
- [Java SE 17 — HttpsExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsExchange.html): extension cho HTTPS và SSL session.
- [Java SE 17 — Java Networking](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): networking/server options và system properties.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): methods, status 204/404/405/413/415, HEAD và content semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): message framing và response body length trên wire.

**Kết luận:** `HttpHandler` quyết định **cách xử lý một request**, còn `HttpExchange` cho bạn **đầy đủ ngữ cảnh của request và công cụ tạo response tương ứng**. Vòng đời đúng luôn là **đọc method/URI/headers/body → validate/route → set response headers → gửi status + đúng body framing → đóng streams và exchange**. Khi hiểu được fixed length, chunked, no-body, error timing và shared handler concurrency, bạn có nền tảng tốt để viết và kiểm thử HTTP endpoints với JDK Java 17+.
