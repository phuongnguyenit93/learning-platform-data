# Tạo HTTP server cục bộ trả mã lỗi, chuyển hướng và nội dung dạng luồng

## 1. Tại sao nên tự dựng một HTTP server để thực nghiệm mạng?

Khi học hoặc kiểm thử Java Networking, ta thường cần mô phỏng những phản hồi ít gặp nhưng rất quan trọng: lỗi `400/404/429/503`, chuyển hướng `302/307`, response truyền theo luồng (streaming), mất kết nối giữa body và header `Content-Length` không khớp thực tế. Phụ thuộc vào một API công khai cho các tình huống này khiến bài test không ổn định, khó tái hiện và có thể vi phạm giới hạn dịch vụ.

**HTTP server cục bộ** cho phép chủ động quyết định HTTP status, header, thời điểm gửi bytes và khi nào đóng kết nối. Client Java chạy ngay trong cùng máy để kiểm tra đúng hành vi cần học, không phụ thuộc Internet.

```text
                Một chương trình Java 17
  +------------------------------------------------+
  |                                                |
  |  HttpClient                                    |
  |      |                                         |
  |      | GET http://127.0.0.1:<ephemeral-port>    |
  |      v                                         |
  |  HttpServer (JDK jdk.httpserver)                |
  |      |                                         |
  |      +-- /fixed         -> 200, body có length  |
  |      +-- /bad-request   -> 400 JSON            |
  |      +-- /not-found     -> 404 JSON            |
  |      +-- /limited       -> 429 Retry-After      |
  |      +-- /unavailable   -> 503 Retry-After      |
  |      +-- /redirect      -> 302 Location        |
  |      +-- /redirect-307  -> 307 Location        |
  |      +-- /stream        -> 200 chunked         |
  |      +-- /stream-large  -> body vượt quota     |
  |      +-- /truncated     -> đóng trước length   |
  +------------------------------------------------+
```

Bài này tập trung **tự tạo một server test điều khiển được** và quan sát từ HTTP client. Nó không xây web framework sản phẩm, không dựng server công khai, không cần database, TLS certificate hay dịch vụ bên ngoài. Các ví dụ dùng **Java 17+**; mã hoàn chỉnh được biên dịch và chạy thật ở mục 9.

Mục tiêu học tập:

1. Tạo và dừng `com.sun.net.httpserver.HttpServer`, bind `127.0.0.1` và cổng `0`.
2. Dùng `HttpExchange` để đọc request method/URI, thiết lập status, header và response body.
3. Chọn đúng `sendResponseHeaders(status, responseLength)` cho body có độ dài cố định, streaming/chunked hoặc không body.
4. Trả các mã lỗi HTTP với body/headers phù hợp; hiểu lỗi giao thức khác lỗi nghiệp vụ.
5. Tạo chuyển hướng tương đối `Location` và so sánh client `Redirect.NEVER` với `Redirect.NORMAL`.
6. Dựng kịch bản luồng vượt giới hạn hoặc body bị cắt, test client phản ứng fail-closed.
7. Dọn mọi socket/server trong `finally` để kiểm thử lặp lại được.

## 2. Chọn đúng công cụ trong JDK

### 2.1. Các API có sẵn

| API | Vai trò | Nơi sử dụng |
| --- | --- | --- |
| `com.sun.net.httpserver.HttpServer` | Tạo HTTP listener và ánh xạ request tới handler | Phía server |
| `HttpHandler` | Giao diện xử lý từng HTTP exchange | Phía server |
| `HttpExchange` | Request method/URI/headers/body và response headers/body | Phía server |
| `HttpContext` | Ánh xạ một path prefix với handler và filters | Phía server |
| `Headers` | Map headers không phân biệt chữ hoa/thường của tên trường | Phía server |
| `java.net.InetSocketAddress` | Địa chỉ IP/port mà server bind | Cấu hình |
| `java.net.http.HttpClient` | Client gửi GET/HEAD/POST tới loopback | Kiểm thử |
| `HttpRequest` | URI/method/timeout của request | Kiểm thử |
| `HttpResponse` | Status/headers/body và final URI | Kiểm thử |
| `InputStream`/`OutputStream` | Đọc và ghi body từng phần | Client và server |

`HttpServer` thuộc **module `jdk.httpserver`** có trong JDK 17; không cần Maven/Gradle dependency để chạy mẫu. Có thể đặt module tường minh:

```bash
javac --release 17 --add-modules jdk.httpserver LocalHttpLab.java
java --add-modules jdk.httpserver LocalHttpLab
```

Một số IDE tự resolve module từ classpath project, nhưng lệnh trên cố ý khai rõ dependency để dễ tái hiện. Lưu ý Java 17 đã có `HttpServer`, **không cần** `SimpleFileServer` hoặc `jwebserver` (những thành phần mới được bổ sung từ JDK 18 cho nhu cầu static file).

### 2.2. Vì sao dùng HttpServer thay vì tự parse HTTP bằng Socket?

Nếu dùng `ServerSocket` thuần, bạn phải tự xử lý request line, headers, message framing, chunked encoding, keep-alive, protocol errors và nhiều trường hợp bảo mật. Bài học ở đây muốn kiểm thử **status, redirect và body streaming**, nên `HttpServer` giúp giảm phần parser lặp lại.

Tuy nhiên, server JDK này là công cụ nhẹ cho kiểm thử/prototyping. Nó **không tự cấp authentication, authorization, business validation, rate limiting, production-grade observability hay HTTPS**. Nếu ứng dụng thực cần HTTPS, Java có `HttpsServer` và SSLContext, nhưng việc cấu hình TLS an toàn là chủ đề khác; không nên đưa server HTTP thử nghiệm ra Internet.

## 3. Bind loopback và chọn cổng 0 để tránh xung đột

Tạo server:

```java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 0), 0);

server.createContext("/hello", exchange -> {
    byte[] bytes = "Hello".getBytes(StandardCharsets.UTF_8);
    try (exchange) {
        exchange.getResponseHeaders().set("Content-Type", "text/plain");
        exchange.sendResponseHeaders(200, bytes.length);
        exchange.getResponseBody().write(bytes);
    }
});

server.start();
try {
    int actualPort = server.getAddress().getPort();
    // Dùng URI http://127.0.0.1:<actualPort>/hello trong test.
} finally {
    server.stop(0);
}
```

*Đây là mảnh mã đặt trong method có `throws Exception` và các import `HttpServer`, `InetSocketAddress`, `StandardCharsets`. Ví dụ hoàn chỉnh ở mục 9.*

Giải thích:

- **`127.0.0.1`** là loopback IPv4. Chỉ các tiến trình có quyền truy cập loopback trong network namespace tương ứng mới kết nối được; đó **không phải authentication**.
- **Port `0`** yêu cầu hệ điều hành chọn cổng trống. Với test tự động/chạy song song, tốt hơn hard-code port `8080` hoặc `8000` vì tránh collision.
- Tham số thứ hai trong `HttpServer.create(address, backlog)` là **TCP accept backlog**. Giá trị `0` cho phép implementation chọn giá trị mặc định, **không có nghĩa server chỉ nhận 0 request**.
- `createContext("/hello", handler)` đăng ký route trước khi server phục vụ. Context mapping dùng **so khớp tiền tố path**; đừng xem nó như router có kiểm tra HTTP method hay authorization tự động.
- `start()` bắt đầu nhận request. `getAddress().getPort()` lấy **cổng thực tế** sau khi bind.
- `stop(0)` ngừng phục vụ và đóng các kết nối đang mở theo cơ chế của API, không phải lệnh hủy một request bằng status 0. Tham số là **giây chờ tối đa** cho các handlers đang xử lý; đối tượng server đã stop không thể start lại.

Không dùng `new InetSocketAddress("0.0.0.0", 0)` trong bài test đơn giản nếu không cần truy cập từ thiết bị khác. Bind all interfaces có thể khiến service bị truy cập ngoài dự định. Bài này **chỉ phục vụ fixture test không có secret**.

## 4. Vòng đời của một HttpExchange

Một lần request/response có trình tự:

```text
HTTP request tới listener
    |
    v
HttpServer chọn HttpContext và gọi HttpHandler.handle(exchange)
    |
    +--> exchange.getRequestMethod()
    +--> exchange.getRequestURI()
    +--> exchange.getRequestHeaders()
    +--> nếu có request body: xử lý InputStream có quota
    |
    v
exchange.getResponseHeaders().set(...)
    |
    v
exchange.sendResponseHeaders(statusCode, responseLength)
    |
    v
exchange.getResponseBody().write(...)
    |
    v
đóng response body / HttpExchange
    |
    v
HTTP response kết thúc hoặc connection bị abort
```

**Thứ tự rất quan trọng:** phải thiết lập các header muốn gửi **trước** khi gọi `sendResponseHeaders`. Sau lệnh đó, header response đã bắt đầu được gửi; không kỳ vọng chỉnh header sau khi đã ghi body sẽ có tác dụng.

`HttpExchange` là `AutoCloseable` ở Java 17; dùng:

```java
try (exchange) {
    // Set headers, send status, write body.
}
```

Khi exchange được đóng, request/response streams cũng được đóng. Nếu có body từ client, nên tiêu thụ hoặc xử lý/đóng có chủ đích; đóng exchange khi chưa đọc hết request body có thể ảnh hưởng khả năng tái sử dụng connection theo API JDK.

**Không nên** giữ một `HttpExchange` trong global variable để xử lý sau khi handler đã đóng. Với streaming bất đồng bộ, lifecycle và thread ownership cần được thiết kế riêng; ví dụ dưới dùng ghi đồng bộ có giới hạn nên dễ hiểu.

## 5. Ba chế độ responseLength của sendResponseHeaders

Đây là điểm kỹ thuật **quan trọng nhất** để tạo phản hồi đúng trên JDK 17:

| Lời gọi | Semantics của JDK HttpExchange | Sử dụng |
| --- | --- | --- |
| `sendResponseHeaders(200, N)` với **N > 0** | Body cố định **chính xác N byte** | Text/JSON/file nhỏ đã biết size |
| `sendResponseHeaders(200, 0)` | Sử dụng **chunked transfer encoding**; ghi số byte tùy ý, kết thúc bằng đóng stream | Streaming HTTP/1.1 |
| `sendResponseHeaders(status, -1)` | **Không có response body** | HEAD, 204, 304, redirect không body trong demo |

**Không nhầm `0` là "body rỗng".** Trong API `HttpExchange`, `0` là tín hiệu **chunked**. Nếu muốn response không có body, dùng `-1`. Tài liệu Java SE 17 của `HttpExchange.sendResponseHeaders` xác định rõ ba trường hợp này.

### 5.1. Fixed Content-Length

```java
byte[] bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(200, bytes.length);
exchange.getResponseBody().write(bytes);
```

*Fragment trong handler, phải đóng `exchange` sau khi hoàn tất.*

`"Xin chào"` có **8 UTF-16 code units** nhưng **9 bytes UTF-8**. Nếu viết:

```java
// PHẢN VÍ DỤ: body.length() không phải byte count trên mạng.
exchange.sendResponseHeaders(200, "Xin chào".length());
exchange.getResponseBody().write(
        "Xin chào".getBytes(StandardCharsets.UTF_8));
```

thì khai 8 byte nhưng cố ghi 9 byte: fixed-length response **vượt số byte khai báo**. JDK sẽ ném `IOException`, exchange bị abort. Cần **tính byte[] trước**, sau đó dùng `bytes.length`.

Nếu khai N byte nhưng chỉ ghi M byte với **M nhỏ hơn N**, thao tác đóng response body có thể ném `IOException` và kết nối bị đóng. Đây là cách cố tình tạo lỗi truncated-body để kiểm thử client (mục 9), **không phải hành vi server bình thường**.

### 5.2. Chunked body (streaming)

```java
try (exchange) {
    exchange.getResponseHeaders().set("Content-Type", "text/plain");
    exchange.sendResponseHeaders(200, 0);
    OutputStream out = exchange.getResponseBody();
    out.write("one|".getBytes(StandardCharsets.UTF_8));
    out.flush();
    out.write("two".getBytes(StandardCharsets.UTF_8));
    out.flush();
}
```

Khi server đóng stream thành công, HTTP stack kết thúc chunked body đúng giao thức; client nhận **logical body** `one|two`. Trong bài test HTTP/1.1, header `Transfer-Encoding: chunked` được xác minh bằng `HttpClient`.

**Lưu ý:** mỗi lần `out.write/flush` **không bảo đảm client thấy một `InputStream.read()` tương ứng**. TCP/HTTP buffers, chunk encoding, proxy và HTTP client có thể gộp hoặc chia bytes. Kiểm thử phải dựa trên **nội dung và trạng thái giao thức**, không giả định "server flush một lần = client read một lần".

### 5.3. Không body

```java
try (exchange) {
    exchange.getResponseHeaders().set("Location", "/fixed");
    exchange.sendResponseHeaders(302, -1);
}
```

Đây là một response redirect hợp lệ theo lựa chọn demo: `Location` ở header, không có response body. `-1` cũng phù hợp cho `204 No Content` và một HEAD response. Khi dùng HEAD, có thể cung cấp các header metadata như Content-Type và Content-Length **của representation GET tương ứng** mà không gửi bytes body.

Không dùng `sendResponseHeaders(204, 0)` rồi cố stream một body. Status 204 theo HTTP semantics không có message content.

## 6. Tạo mã lỗi 4xx/5xx có thể kiểm thử

HTTP error không phải lúc nào cũng tương đương Java exception. Server có thể xử lý request thành công ở tầng TCP nhưng **cố ý trả 400/404/429/503** để client thực hành nhánh lỗi.

| Status | Trường hợp thí nghiệm | Client cần làm |
| --- | --- | --- |
| `400 Bad Request` | Input/schema không hợp lệ | Không retry nguyên request; sửa input |
| `401 Unauthorized` | Chưa xác thực hoặc credentials sai | Xác thực lại theo policy |
| `403 Forbidden` | Có danh tính nhưng thiếu quyền | Không tự retry vô hạn |
| `404 Not Found` | Không tìm thấy resource | Báo không tồn tại, không parse như tài liệu thành công |
| `405 Method Not Allowed` | POST tới endpoint chỉ cho GET/HEAD | Đọc `Allow`; dùng đúng method |
| `409 Conflict` | Trạng thái hiện tại không cho thao tác | Xử lý business conflict |
| `413 Content Too Large` | Request upload vượt quota | Giảm payload theo contract |
| `415 Unsupported Media Type` | Header/body không đúng media type hỗ trợ | Chọn Content-Type hợp lệ |
| `422 Unprocessable Content` | Syntax hợp lệ nhưng nội dung nghiệp vụ không đạt | Sửa dữ liệu |
| `429 Too Many Requests` | Vượt rate limit | Tôn trọng `Retry-After`/backoff |
| `500 Internal Server Error` | Server lỗi không mong đợi | Không suy nguyên nhân từ client; log server an toàn |
| `503 Service Unavailable` | Bảo trì/quá tải/tạm thời không sẵn sàng | Retry có giới hạn và backoff khi phù hợp |
| `504 Gateway Timeout` | Gateway/upstream không phản hồi kịp | Phân biệt timeout upstream với client timeout |

**Không coi mọi 4xx là lỗi Java exception cần bắt lại**, cũng không coi mọi 5xx đều an toàn để retry. Với request có side effect như POST tạo đơn hàng, server có thể đã commit rồi mới mất response; cần idempotency key/server-side dedup trước khi resend.

### 6.1. Body lỗi JSON nhỏ và rõ ràng

```java
static void sendJsonError(HttpExchange ex, int status, String errorCode)
        throws IOException {
    String json = "{\"error\":\"" + errorCode + "\"}";
    byte[] body = json.getBytes(StandardCharsets.UTF_8);
    try (ex) {
        ex.getResponseHeaders().set(
                "Content-Type", "application/json; charset=UTF-8");
        ex.sendResponseHeaders(status, body.length);
        ex.getResponseBody().write(body);
    }
}
```

*Fragment này giả định `errorCode` là **hằng số server kiểm soát** như `"invalid_input"`, không phải chuỗi user tùy ý; nếu dữ liệu động, dùng JSON serializer chuẩn để escape đúng. Các import cần thiết: `HttpExchange`, `IOException`, `StandardCharsets`.*

Không trả stack trace, filesystem path, database credentials hay thông tin nội bộ vào lỗi HTTP. Với môi trường test, body có schema cố định như `{"error":"invalid_input"}` giúp assert nhanh và tránh phụ thuộc thông điệp exception thay đổi.

### 6.2. Retry-After trên 429 và 503

Một handler mô phỏng rate limit:

```java
server.createContext("/limited", ex -> {
    ex.getResponseHeaders().set("Retry-After", "2");
    text(ex, 429, "text/plain", "slow down");
});
```

Mảnh code giả định helper `text(...)` của ví dụ mục 9 và `server` đã khởi tạo. `Retry-After: 2` nghĩa là **gợi ý chờ 2 giây** theo HTTP semantics (header cũng có thể là HTTP-date); không phải lệnh Java tự ngủ. Client Java `HttpClient` **không mặc định đảm bảo tuân thủ retry/backoff ứng dụng** cho tất cả lỗi 429/503. Test client nên đọc header, phân loại status và thực hiện policy retry có giới hạn.

Đừng triển khai retry vô hạn; bổ sung jitter, tổng deadline, giới hạn số lần và điều kiện idempotency.

## 7. Chuyển hướng: mã 301/302/303/307/308 và Location

Một server test redirect có thể đơn giản:

```java
server.createContext("/redirect", ex -> {
    try (ex) {
        ex.getResponseHeaders().set("Location", "/fixed");
        ex.sendResponseHeaders(302, -1);
    }
});
```

**Location** có thể là URI tương đối `/fixed`. Client dùng URI hiện tại để giải ra URL tuyệt đối. Các status liên quan:

| Status | Ý nghĩa cơ bản | Lưu ý khi test |
| --- | --- | --- |
| `301 Moved Permanently` | Chuyển vĩnh viễn | Cache/client có thể nhớ redirect tùy semantics |
| `302 Found` | Chuyển tạm thời | POST có lịch sử được đổi sang GET ở một số client |
| `303 See Other` | Chuyển tới URI khác, thường dùng GET | Phù hợp "POST rồi xem kết quả" theo contract |
| `307 Temporary Redirect` | Chuyển tạm, **giữ method/body semantics** | Cẩn trọng khi body không replay được |
| `308 Permanent Redirect` | Chuyển vĩnh viễn, giữ method/body | Không tự resend non-idempotent request |

Demo dùng **GET** nên đường chuyển hướng `307 -> 302 -> 200` được kiểm chứng mà không có side effects.

### 7.1. Cấu hình client NEVER so với NORMAL

```java
HttpClient never = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpClient normal = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
```

Với `NEVER`, GET `/redirect` trả trực tiếp **302 và header `Location: /fixed`**; client không tự đi tới destination.

Với `NORMAL` và redirect **cùng loopback origin** trong demo, GET `/redirect-307` qua `/redirect` rồi đến `/fixed`; kết quả cuối **200**, `HttpResponse.uri().getPath()` là `/fixed`.

**Cảnh báo:** `Redirect.NORMAL` không phải chính sách chống SSRF đầy đủ. Nó ngăn một số scheme downgrade (HTTPS→HTTP), nhưng **không áp allowlist host/port/path của ứng dụng**. Với URL do người dùng kiểm soát, nên dùng `NEVER` và **xác thực từng Location trước request mới**, kiểm tra DNS/IP/egress, giới hạn hop/vòng lặp và không chuyển Authorization/cookie sang origin không được phép.

### 7.2. Redirect an toàn cho GET

```text
GET /initial --302--> Location: /next
    |
    v
URI.resolve(Location)
    |
    +-- validate scheme, host, port, path, userinfo
    +-- reject off-origin / forbidden destination
    +-- maxRedirects / seen URI / total deadline
    |
    v
GET /next
```

Không dùng `response.headers().firstValue("Location")` rồi blind-follow để gửi secret ngoài origin. Demo dùng redirect local an toàn, còn SSRF defenses production cần cả network policy và validation tại điểm kết nối thực (DNS rebinding có thể vượt một DNS lookup trước khi connect).

## 8. Streaming responses: chunked HTTP/1.1 khác Content-Length cố định

### 8.1. Fixed-length và streaming khác nhau ở đâu?

**Fixed-length:** server đã biết số bytes trước khi gửi, có thể khai `Content-Length: N` và bắt buộc ghi đúng N bytes.

**Chunked:** server bắt đầu gửi khi chưa biết tổng bytes, ví dụ tiến trình tạo log, file được sinh từng đoạn hoặc API đưa kết quả thành các phần. Trong API JDK 17 dùng:

```java
ex.sendResponseHeaders(200, 0); // chunked response
OutputStream out = ex.getResponseBody();
out.write("first".getBytes(StandardCharsets.UTF_8));
out.flush();
out.write("second".getBytes(StandardCharsets.UTF_8));
out.flush();
```

Mảnh code yêu cầu exchange được đóng sau khi ghi. Dữ liệu **logic** khách hàng đọc là `firstsecond`; framing chunked do HTTP stack mã hóa/giải mã.

### 8.2. Chunked wire framing và body mà client nhìn thấy

HTTP/1.1 chunked sử dụng các chunk sizes trên wire (sơ đồ minh họa, **không cam kết đây là cách JDK chia chunk trong từng lần flush**):

```http
HTTP/1.1 200 OK
Transfer-Encoding: chunked
Content-Type: text/plain

4
one|
3
two
0

```

Client HTTP library xử lý framing để application chỉ thấy bytes `one|two`. Vì thế:

- Không tự parse chuỗi `4\r\none|\r\n...` từ `BodyHandlers.ofInputStream()`: HttpClient **đã xử lý** HTTP chunked framing.
- Không giả định `InputStream.read()` trả đúng một server write hoặc một HTTP chunk.
- Không coi `flush()` là application ACK hoặc cam kết byte đã đến consumer ở thời điểm đó.
- Nếu peer đóng TCP trước terminating zero-size chunk, HTTP client có thể báo lỗi framing; không đánh dấu stream thành công chỉ vì đã đọc một phần.
- HTTP/2/HTTP/3 dùng stream framing riêng; **HTTP/1.1 chunked không phải mô hình payload framing của WebSocket/SSE**.

### 8.3. Client đọc body dưới dạng InputStream

```java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] buffer = new byte[8192];
    long count = 0;
    int n;
    while ((n = body.read(buffer)) != -1) {
        if (n > MAX_BYTES - count) {
            throw new IOException("Body exceeds limit");
        }
        count += n;
        // Xử lý những bytes đang có; đừng giữ tất cả trong RAM.
    }
}
```

*Fragment trong method có `client`, `request` và `MAX_BYTES`; cần import `HttpResponse`, `InputStream`, `IOException`.*

Lưu ý quan trọng: với `BodyHandlers.ofInputStream()`, `client.send(...)` có thể trả về sau khi nhận headers **trước khi body được đọc hết**. Phải xử lý exception khi đọc stream, đóng body kể cả lỗi, đặt quota bytes và deadline/cancellation cho tác vụ hoàn chỉnh.

### 8.4. Streaming log/SSE là trường hợp ứng dụng

Nếu muốn stream event đơn giản, server có thể set `Content-Type: text/event-stream; charset=UTF-8` và gửi các dòng theo định dạng **Server-Sent Events (SSE)**:

```text
event: progress
data: {"percent":25}

event: progress
data: {"percent":50}

```

**Đây là ví dụ payload SSE, không phải kết quả demo mục 9.** SSE dùng HTTP response stream một chiều; khác **WebSocket** là kênh full-duplex sau handshake. Server cần kiểm soát hủy request, heartbeat, timeouts, backpressure và quyền truy cập nếu muốn dùng SSE thực. Chunked HTTP giúp vận chuyển streaming trên HTTP/1.1, nhưng ranh giới chunk **không** đồng nghĩa một SSE event; event kết thúc theo các dòng trống của định dạng SSE.

## 9. Chương trình Java 17 hoàn chỉnh — server + client + các nhánh lỗi

Đây là chương trình **độc lập, chạy trong một JVM, không dùng Internet**. Nó tạo server localhost ở port 0, cấu hình các route, rồi dùng hai HttpClient để đối chiếu response.

Các tình huống:

- Fixed body 200 và HEAD không body (nhưng Content-Length của representation là 5).
- HTTP 400/404 với JSON error, HTTP 429/503 với `Retry-After`.
- POST bị từ chối bằng 405, có `Allow: GET, HEAD`.
- GET redirect `302` không tự follow với NEVER, so với chuỗi `307→302→200` được NORMAL follow.
- Streaming chunked trả `one|two`, client quan sát Transfer-Encoding.
- Chunked stream lớn hơn byte quota 10 và fixed response bị cắt trước declared length 20; client từ chối hai trường hợp.

**Tên tệp: `LocalHttpLab.java`**

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class LocalHttpLab {
    static void text(HttpExchange ex, int status, String media, String value)
            throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        try (ex) {
            ex.getResponseHeaders().set("Content-Type", media);
            ex.sendResponseHeaders(status, bytes.length);
            ex.getResponseBody().write(bytes);
        }
    }

    static void redirect(HttpExchange ex, int status, String location)
            throws IOException {
        try (ex) {
            ex.getResponseHeaders().set("Location", location);
            ex.sendResponseHeaders(status, -1);
        }
    }

    static HttpClient newClient(HttpClient.Redirect redirects) {
        return HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .followRedirects(redirects)
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    static HttpRequest request(URI base, String method, String path) {
        return HttpRequest.newBuilder(base.resolve(path))
                .timeout(Duration.ofSeconds(5))
                .method(method, HttpRequest.BodyPublishers.noBody())
                .build();
    }

    static HttpResponse<String> stringReply(HttpClient client, URI base,
            String method, String path) throws Exception {
        return client.send(request(base, method, path),
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    static long consumeBounded(InputStream body, long max)
            throws IOException {
        byte[] bytes = new byte[8];
        long count = 0;
        int n;
        while ((n = body.read(bytes)) != -1) {
            if (n > max - count)
                throw new IOException("Body exceeds limit");
            count += n;
        }
        return count;
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/fixed", ex -> {
            if ("HEAD".equals(ex.getRequestMethod())) {
                try (ex) {
                    ex.getResponseHeaders().set("Content-Type", "text/plain");
                    ex.getResponseHeaders().set("Content-Length", "5");
                    ex.sendResponseHeaders(200, -1);
                }
            } else if ("GET".equals(ex.getRequestMethod())) {
                text(ex, 200, "text/plain; charset=UTF-8", "hello");
            } else {
                ex.getResponseHeaders().set("Allow", "GET, HEAD");
                text(ex, 405, "text/plain", "method not allowed");
            }
        });
        server.createContext("/bad-request", ex ->
                text(ex, 400, "application/json",
                        "{\"error\":\"invalid_input\"}"));
        server.createContext("/not-found", ex ->
                text(ex, 404, "application/json",
                        "{\"error\":\"not_found\"}"));
        server.createContext("/limited", ex -> {
            ex.getResponseHeaders().set("Retry-After", "2");
            text(ex, 429, "text/plain", "slow down");
        });
        server.createContext("/unavailable", ex -> {
            ex.getResponseHeaders().set("Retry-After", "3");
            text(ex, 503, "text/plain", "maintenance");
        });
        server.createContext("/redirect", ex ->
                redirect(ex, 302, "/fixed"));
        server.createContext("/redirect-307", ex ->
                redirect(ex, 307, "/redirect"));
        server.createContext("/stream", ex -> {
            try (ex) {
                ex.getResponseHeaders().set("Content-Type", "text/plain");
                ex.sendResponseHeaders(200, 0); // Chunked HTTP/1.1
                OutputStream out = ex.getResponseBody();
                out.write("one|".getBytes(StandardCharsets.UTF_8));
                out.flush();
                out.write("two".getBytes(StandardCharsets.UTF_8));
                out.flush();
            }
        });
        server.createContext("/stream-large", ex -> {
            try (ex) {
                ex.getResponseHeaders().set("Content-Type", "text/plain");
                ex.sendResponseHeaders(200, 0);
                OutputStream out = ex.getResponseBody();
                for (int i = 0; i < 4; i++) {
                    out.write("123456".getBytes(StandardCharsets.US_ASCII));
                    out.flush();
                }
            } catch (IOException earlyClose) {
                // A bounded client may stop reading before completion.
            }
        });
        server.createContext("/truncated", ex -> {
            try (ex) {
                ex.getResponseHeaders().set("Content-Type", "text/plain");
                ex.sendResponseHeaders(200, 20);
                ex.getResponseBody().write(
                        "cut".getBytes(StandardCharsets.US_ASCII));
            } catch (IOException expected) {
                // Intentionally close before the declared 20 bytes.
            }
        });
        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient never = newClient(HttpClient.Redirect.NEVER);
            HttpClient normal = newClient(HttpClient.Redirect.NORMAL);

            HttpResponse<String> fixed =
                    stringReply(never, base, "GET", "/fixed");
            System.out.println("GET: " + fixed.statusCode()
                    + " body=" + fixed.body());

            HttpResponse<String> head =
                    stringReply(never, base, "HEAD", "/fixed");
            System.out.println("HEAD: " + head.statusCode()
                    + " bodyLength=" + head.body().length()
                    + " declared=" + head.headers()
                            .firstValue("Content-Length").orElse("none"));

            for (String path : new String[]{"/bad-request", "/not-found",
                    "/limited", "/unavailable"}) {
                HttpResponse<String> r =
                        stringReply(never, base, "GET", path);
                System.out.println(path + ": " + r.statusCode()
                        + " retryAfter=" + r.headers()
                                .firstValue("Retry-After").orElse("none"));
            }
            HttpResponse<String> badMethod =
                    stringReply(never, base, "POST", "/fixed");
            System.out.println("POST: " + badMethod.statusCode()
                    + " allow=" + badMethod.headers()
                            .firstValue("Allow").orElse("none"));

            HttpResponse<String> redirect =
                    stringReply(never, base, "GET", "/redirect");
            System.out.println("redirect NEVER: " + redirect.statusCode()
                    + " location=" + redirect.headers()
                            .firstValue("Location").orElse("none"));

            HttpResponse<String> followed =
                    stringReply(normal, base, "GET", "/redirect-307");
            System.out.println("redirect NORMAL: " + followed.statusCode()
                    + " path=" + followed.uri().getPath()
                    + " body=" + followed.body());

            HttpResponse<String> stream =
                    stringReply(never, base, "GET", "/stream");
            System.out.println("stream: " + stream.statusCode()
                    + " transfer=" + stream.headers()
                            .firstValue("Transfer-Encoding").orElse("none")
                    + " body=" + stream.body());

            HttpResponse<InputStream> large = never.send(
                    request(base, "GET", "/stream-large"),
                    HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream in = large.body()) {
                consumeBounded(in, 10);
                throw new AssertionError("size limit not enforced");
            } catch (IOException expected) {
                System.out.println("stream-limit: rejected");
            }

            try {
                HttpResponse<InputStream> truncated = never.send(
                        request(base, "GET", "/truncated"),
                        HttpResponse.BodyHandlers.ofInputStream());
                try (InputStream in = truncated.body()) {
                    long count = consumeBounded(in, 100);
                    if (count != 20)
                        throw new IOException("Content-Length mismatch");
                    throw new AssertionError("truncation not rejected");
                }
            } catch (IOException expected) {
                System.out.println("truncated: rejected");
            }
        } finally {
            server.stop(0);
        }
    }
}
```

**Biên dịch và chạy Java 17** (module `jdk.httpserver` cung cấp server cục bộ):

```bash
javac --release 17 --add-modules jdk.httpserver LocalHttpLab.java
java --add-modules jdk.httpserver LocalHttpLab
```

**Stdout đã biên dịch và chạy thực tế:**

```text
GET: 200 body=hello
HEAD: 200 bodyLength=0 declared=5
/bad-request: 400 retryAfter=none
/not-found: 404 retryAfter=none
/limited: 429 retryAfter=2
/unavailable: 503 retryAfter=3
POST: 405 allow=GET, HEAD
redirect NEVER: 302 location=/fixed
redirect NORMAL: 200 path=/fixed body=hello
stream: 200 transfer=chunked body=one|two
stream-limit: rejected
truncated: rejected
```

### 9.1. Những gì từng dòng chứng minh

- **GET 200:** server trả đúng 5 byte `hello` bằng fixed-length body.
- **HEAD 200:** response body rỗng nhưng header Content-Length được ghi tường minh là `5`, tương ứng body GET.
- **400/404:** handler chủ động phát mã lỗi, không cần làm hỏng TCP connection.
- **429/503:** client nhận header Retry-After dưới dạng text `2` và `3`. Nó **chưa tự retry**; quyết định retry thuộc ứng dụng.
- **POST 405:** endpoint `/fixed` chỉ cho GET/HEAD và trả header `Allow: GET, HEAD`.
- **Redirect NEVER:** nhận nguyên response 302 và Location `/fixed`.
- **Redirect NORMAL:** client đi theo chuỗi `307→302→200` đến `/fixed`, quan sát URI cuối và body.
- **Stream chunked:** mặc dù server gọi hai lần write/flush, client nhận một logical body `one|two` sau khi HttpClient giải HTTP framing.
- **Stream limit rejected:** server phát tổng 24 byte bằng chunked; client đặt limit 10 byte, đọc có kiểm tra và ném IOException; không chấp nhận phần dữ liệu vượt quota.
- **Truncated rejected:** server tuyên bố 20 byte nhưng cố ý ghi 3 byte. Khi ghi/đóng body, trao đổi bị abort; client đọc phát sinh IOException hoặc kiểm tra count thất bại nên không coi response là hoàn tất.

**Lưu ý độ tin cậy của test:** output của chính chương trình được quan sát trong môi trường Java 17-compatible với `javac --release 17`. Demo không đo thời gian network và không assert số lượt callback read, vì những thứ đó phụ thuộc scheduler/buffering. Bài test này không chứng minh server an toàn để public hoặc mọi trường hợp HTTP/2/TLS.

### 9.2. Vì sao chương trình không dùng sleep để chứng minh streaming?

Một stream vẫn là **stream** nếu server gọi `sendResponseHeaders(200, 0)`, ghi theo các đợt và đóng OutputStream đúng cách. Thêm `Thread.sleep(...)` chỉ giúp làm chậm tiến trình để quan sát; nó không thay đổi semantics của HTTP transfer.

Nếu bài test cần chứng minh client xử lý **ngay khi chunk đầu tiên đến**, hãy dùng synchronization như `CountDownLatch`/futures (có deadline) hoặc đo các event ứng dụng có kiểm soát, không viết assertion "sau 50 ms chắc chắn client đã nhận phần 1" — timing dựa vào môi trường và thường gây test flaky.

## 10. Thử thủ công bằng curl sau khi khởi động server riêng

Chương trình `LocalHttpLab` chạy server và tự kiểm thử rồi dừng ngay. Để thử bằng `curl`, có thể viết một phiên bản server giữ process đang chạy đến khi người dùng nhấn Enter hoặc Ctrl+C. **Không chạy curl sau khi chương trình mục 9 đã hoàn tất**, vì port ngẫu nhiên đã được giải phóng.

Với một server local đang chạy ở `http://127.0.0.1:8000` theo cùng route logic, dùng:

```bash
curl -i http://127.0.0.1:8000/fixed
curl -I http://127.0.0.1:8000/fixed

# Hiện response lỗi và Retry-After:
curl -i http://127.0.0.1:8000/bad-request
curl -i http://127.0.0.1:8000/limited
curl -i http://127.0.0.1:8000/unavailable

# Không theo redirect: quan sát 302 và Location:
curl -i http://127.0.0.1:8000/redirect

# Cho curl đi theo redirect trong môi trường loopback tin cậy:
curl -iL http://127.0.0.1:8000/redirect-307

# Streaming: -N giảm buffering phía curl:
curl -iN http://127.0.0.1:8000/stream
```

Các lệnh `curl` minh họa cần server còn sống và port đã biết. Khi dùng PowerShell Windows, `curl` có thể là alias khác tùy phiên bản shell; dùng `curl.exe` nếu muốn CLI curl thật.

**Quan trọng:** `curl -L` là lựa chọn auto-follow redirects, **không an toàn để mù quáng dùng với URI không tin cậy trong sản phẩm**. Chỉ áp dụng với server test loopback trong ví dụ; phần mềm production cần revalidate từng Location.

## 11. Kiểm thử lỗi không phải làm hỏng server mãi mãi

Một **mã lỗi HTTP hợp lệ** và một **lỗi transport** khác nhau:

```text
Nhánh A: Server chủ động xử lý request và trả 404
   -> Client nhận status 404 + body lỗi (giao thức hoàn chỉnh)

Nhánh B: Server trả header 200/Content-Length:20
         nhưng đóng khi mới ghi 3 byte
   -> Client thấy body incomplete/IOException
   -> Không có artifact hợp lệ để dùng

Nhánh C: Server không listen / TCP reset trước response
   -> Client send/connect có thể ném IOException
   -> Có thể chưa nhận bất kỳ HTTP status nào
```

Tránh gộp ba trường hợp vào một loại exception; client nên phân loại rõ **HTTP response status**, **network/transport failure** và **application-level payload invalid**.

### 11.1. Kịch bản Content-Length sai

Javadoc của `HttpExchange.getResponseBody()` quy định khi dùng fixed length, server phải ghi đúng số byte đã khai. Nếu ghi nhiều hơn thì `write(...)` ném `IOException`; nếu ít hơn thì `close()` có thể ném `IOException` và trao đổi bị abort.

Có thể tận dụng hành vi này để tạo fault injection (như route `/truncated`), nhưng phải **bắt lỗi có chủ đích** trong handler để test server không in stack trace ồn ào hoặc nuốt mọi lỗi thật mà không kiểm soát.

**Không dùng kiểu "server gửi 200 rồi kết thúc sớm" để mô tả một lỗi nghiệp vụ như thiếu quyền**; nếu có thể phát hiện lỗi trước khi gửi headers, hãy trả **4xx/5xx thích hợp trước khi bắt đầu body**.

### 11.2. Không đổi HTTP status khi đã bắt đầu streaming

Một khi đã gọi `sendResponseHeaders(200, 0)`, server **không thể đổi thành 500** nếu lỗi xảy ra giữa streaming. Khi exception xuất hiện:

- Đóng/abort response theo chính sách, log lỗi phía server không chứa secret.
- Client phải phát hiện stream không complete hoặc lỗi ở tầng application protocol.
- Nếu cần stream events với khả năng báo lỗi có cấu trúc, định nghĩa event type `error` và end marker/sequence trong payload trước khi đóng, nhưng vẫn cần hiểu **HTTP status ban đầu có thể là 200**.
- Với dữ liệu quan trọng, dùng expected checksum, count, end marker hoặc manifest từ nguồn tin cậy để xác nhận hoàn tất ở tầng ứng dụng.
- Không commit artifact chỉ vì header status 200 đã được nhận.

Đây là lý do hệ thống tải file lớn thường ghi **file tạm** rồi publish sau khi đọc đủ body và xác minh integrity.

## 12. Bổ sung route mô phỏng độ trễ, timeout và đóng kết nối

Để test timeout của client, có thể tạo handler giả lập độ trễ **trong môi trường cục bộ**:

```java
server.createContext("/slow", ex -> {
    try (ex) {
        Thread.sleep(250); // Demo: giả lập xử lý chậm.
        byte[] body = "late".getBytes(StandardCharsets.UTF_8);
        ex.sendResponseHeaders(200, body.length);
        ex.getResponseBody().write(body);
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
    }
});
```

*Mảnh code không thuộc chương trình hoàn chỉnh ở mục 9; nó cần import tương ứng và bảo đảm xử lý exception/lifecycle. Đây là một kịch bản mô phỏng latency, không dùng sleep để áp policy bảo mật.*

Nếu cấu hình client request timeout ngắn hơn thời gian server tạo response, có thể quan sát `HttpTimeoutException` theo API. Tuy vậy, không viết test giả định scheduler luôn chính xác tới millisecond; đặt biên độ thời gian đủ rõ và dùng đồng bộ có deadline.

**Cảnh báo với streaming:** `HttpClient.send(..., BodyHandlers.ofInputStream())` có thể trả về khi headers đã sẵn sàng, trước khi body được tiêu thụ. Thời hạn của `HttpRequest.timeout(...)` không nên bị hiểu nhầm là **deadline chắc chắn cho toàn bộ vòng InputStream.read()** trong mọi cách triển khai. Một test client đáng tin cần deadline tổng, idle-read timeout/cancel, byte cap và đóng stream.

Khi giả lập connection reset, đôi khi cần một HTTP test framework chuyên dụng hoặc kiểm soát socket thấp hơn vì `HttpServer` chủ động quản lý framing và lifecycle. Không tự viết raw HTTP server cho traffic public chỉ để tạo lỗi framing.

## 13. Kiểm soát request input và giới hạn tài nguyên phía server

Server test có thể tạo route độc hại/hỏng theo kịch bản, nhưng bản thân nó cũng phải tránh cho một test làm treo toàn bộ JVM:

- **Chỉ cho những HTTP methods cần thiết.** Ví dụ `/fixed` cho GET/HEAD, từ chối POST bằng 405 + `Allow`. Nếu dùng mọi method mà không check, test sẽ không đại diện cho API thật.
- **Giới hạn request body** ngay khi đọc stream nếu server nhận POST/PUT. `Content-Length` là metadata cần kiểm tra sớm nhưng không thay được quota bytes thực.
- **Giới hạn URL, query và headers** theo yêu cầu test; không log raw Authorization/cookie nếu có.
- **Tách root/context test:** `HttpServer.createContext("/api",...)` dùng prefix matching; có thể match ngoài route dự kiến nếu không xác thực path bên trong. Đừng dùng context prefix thay authorization.
- **Giới hạn concurrency:** nếu phục vụ nhiều request, dùng executor có số threads/queue giới hạn; tránh unbounded thread per request.
- **Giới hạn tốc độ streaming và tổng bytes:** một route gửi data vô hạn có thể khiến client/test treo; dùng finite fixture, cancellable task, deadline.
- **Dừng server trong finally** dù assertion test ném exception; tránh port/threads tồn tại sau test.

Ví dụ bounded request body reader:

```java
static long discardUpTo(InputStream body, long limit)
        throws IOException {
    byte[] buffer = new byte[4096];
    long total = 0;
    int n;
    while ((n = body.read(buffer)) != -1) {
        if (n > limit - total)
            throw new IOException("Request body too large");
        total += n;
    }
    return total;
}
```

*Mảnh code cần import InputStream và IOException; đây không phải HTTP handler hoàn chỉnh.* Khi quá quota, phải quyết định trả 413/đóng connection theo trạng thái đã gửi headers. Lỗi sau khi bắt đầu gửi response không thể đổi status.

## 14. Executor, threads và giới hạn thực nghiệm

Nếu không gọi `server.setExecutor(...)`, JDK `HttpServer` dùng executor mặc định của implementation. Tài liệu Java 17 nói default xử lý tasks trên thread được server `start()` tạo. Đối với demo ngắn, điều đó đủ và làm output dễ lặp lại.

Nếu cần thử concurrency hoặc streaming dài, có thể tạo executor riêng **trước** `start()`:

```java
ExecutorService pool = Executors.newFixedThreadPool(4);
server.setExecutor(pool);
server.start();
try {
    // Test concurrent requests.
} finally {
    server.stop(0);
    pool.shutdownNow();
}
```

*Mảnh code cần import `ExecutorService`/`Executors`. Lưu ý `newFixedThreadPool` có queue không bị giới hạn mặc định; đây chỉ là cấu hình nhỏ cho fixture **có tải vào được kiểm soát**. Đối với server tiếp nhận request untrusted, phải dùng bounded queue/rejection policy + ingress quotas.*

Không tạo thread mới cho mỗi request không giới hạn. Không dùng một `Thread.sleep(10000)` trong mọi request nếu muốn test nhận nhiều kết nối trên executor mặc định. Để tạo test có timing, dùng executor và synchronization rõ ràng, timeouts và cleanup.

Mỗi test nên biết server còn sống và port thật. Không dùng `Thread.sleep(200)` như kiểm tra chắc chắn rằng server khởi động; sau `server.start()` và lấy address có thể gửi client request, và test nên bắt/report lỗi rõ.

## 15. Chọn status/headers/body đúng với mục tiêu test

Một số endpoint chỉ dùng status:

```text
GET /health    -> 200 OK
GET /missing   -> 404 Not Found
GET /limited   -> 429 Too Many Requests + Retry-After
GET /shutdown  -> KHÔNG nên tự tạo ngoài phạm vi test
```

Nhưng phần response còn có contract:

| Mục tiêu | Status | Headers | Body |
| --- | --- | --- | --- |
| Success text | 200 | Content-Type text/plain, Content-Length | Bytes đúng UTF-8 |
| Success no content | 204 | Không body | Rỗng |
| HEAD metadata | 200 | Content-Type, Content-Length của GET | Rỗng |
| Input error | 400 | Content-Type application/json | JSON error code ổn định |
| Missing resource | 404 | Content-Type application/json | JSON error code |
| Unsupported method | 405 | Allow: GET, HEAD | Error body tùy hợp đồng |
| Redirect | 302/307 | Location: /path | Có thể không body |
| Rate limit | 429 | Retry-After nếu phù hợp | Error body không lộ secret |
| Temporary unavailable | 503 | Retry-After nếu phù hợp | Error body ngắn |
| Streaming text | 200 | Content-Type text/plain; Transfer-Encoding chunked | Nhiều bytes được gửi theo luồng |
| Forced truncation | 200, header khai length lớn | Content-Length vượt body thực | Body lỗi, connection có thể abort |

### Về HEAD và 204

HTTP semantics yêu cầu `HEAD` **không chứa response content**. Nó có thể mang `Content-Length` của response GET tương ứng, không có nghĩa HEAD client phải đọc số bytes đó. `204 No Content` cũng không có body. Trong `HttpExchange`, dùng `sendResponseHeaders(status,-1)` khi không gửi body; có thể set trước header metadata hợp lệ theo status.

Không tạo `Content-Length: 0` bừa bãi cho mọi status rồi viết content. Client và proxy có thể từ chối response có framing mâu thuẫn.

## 16. Chọn media type, charset và JSON chính xác

**Cấu hình server:**

```java
ex.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=UTF-8");
```

Sau đó body thực phải được mã hóa UTF-8. Với JSON:

```java
ex.getResponseHeaders().set(
        "Content-Type", "application/json; charset=UTF-8");
```

Đừng đặt Content-Type JSON nhưng trả HTML stack trace. Đừng dùng `String.length()` thay `getBytes(UTF_8).length` để khai fixed length.

Nếu test chỉ cần error code tĩnh, có thể viết literal JSON cố định như chương trình. Nhưng **khi tạo JSON từ input động**, phải dùng JSON serializer để escape dấu ngoặc kép, xuống dòng và các ký tự đặc biệt; nối string tùy ý có thể tạo JSON sai hoặc injection.

Khi client nhận response error, `HttpClient.send(...)` bình thường **trả một `HttpResponse` với `statusCode()==400/404`**; nó không tự biến mọi HTTP status lỗi thành IOException. Application phải đọc status và xử lý theo policy. IOException thường biểu diễn lỗi network/framing/I/O, không đồng nhất với 404.

## 17. Test streaming bằng kỹ thuật nào để kết quả ổn định?

Một bài test tốt ưu tiên **observable contract** hơn lịch trình threads:

1. **Kiểm tra body đầy đủ:** `/stream` trả chính xác `one|two`, không thừa/thiếu byte.
2. **Kiểm tra status/headers:** 200 và, trong HTTP/1.1 demo, Transfer-Encoding chunked.
3. **Kiểm tra byte quota ở client:** `/stream-large` phát 24 bytes, client limit 10 phải reject.
4. **Kiểm tra truncation:** `/truncated` khai 20, gửi 3 rồi close; client phải fail, không commit artifact.
5. **Đóng InputStream trong mọi nhánh:** success, invalid status, over-limit, cancellation.
6. **Kiểm tra timeout/cancellation riêng:** tạo kịch bản delay có kiểm soát và deadline, tránh dựa vào một sleep ngắn mang tính ngẫu nhiên.
7. **Không assert số lần `read()`:** HTTP client có thể trả data được gộp/chia theo nội bộ.
8. **Không assert port cố định:** dùng ephemeral port do server cấp.
9. **Không phụ thuộc Internet:** chạy server và client trên loopback, fixture tự tạo.
10. **Lặp test nhiều lần:** đảm bảo stop và cleanup mọi lần, kể cả khi một assertion fail.

Một trong những lỗi test phổ biến là dùng `BodyHandlers.ofString()` cho stream quá lớn rồi đợi đến khi hoàn tất: cách này **thu toàn bộ body vào bộ nhớ** trước khi trả String. Để test stream/quota thực tế, dùng `BodyHandlers.ofInputStream()` và đọc từng buffer.

## 18. Mở rộng test: SSE, file download, multipart và lỗi đặc thù

Một HTTP server cục bộ có thể phục vụ nhiều kiểu thí nghiệm khác nhau mà không cần dữ liệu Internet:

### 18.1. SSE progress

Server set `Content-Type: text/event-stream; charset=UTF-8`, dùng streaming/chunked, gửi `event: progress` và `data: ...` kèm dòng trống. Client SSE đọc từng event, xử lý reconnect theo application protocol (ví dụ Last-Event-ID). Đây là **protocol tầng ứng dụng trên HTTP**, không phải một HTTP chunk = một SSE event.

### 18.2. File download

Route `/file` có thể mở file fixture qua `Files.newInputStream` và copy theo buffer tới response. Nếu biết size, dùng fixed `sendResponseHeaders(200,size)`; nếu file được tạo khi đang gửi, dùng streaming có giới hạn. Với dữ liệu lớn không dùng `Files.readAllBytes` tùy tiện, và không cho user chọn path ngoài document root.

### 18.3. Range và resume

Nếu cần kiểm thử `Range: bytes=...`, server phải cố ý trả `206 Partial Content` kèm `Content-Range` khớp byte offset, hoặc `416 Range Not Satisfiable` khi sai. Ví dụ chính **không triển khai Range**, không được dùng status 206 bừa bãi rồi cho rằng resume đúng. Dữ liệu test cần validator/ETag nếu kiểm tra If-Range.

### 18.4. Multipart upload

HTTP server nhận multipart phải parse boundary và giới hạn request body, số parts, filename, tổng bytes và tốc độ. `HttpServer` không tự tạo một servlet/multipart parser hoàn chỉnh; cần parser phù hợp hoặc custom fixture handler. Không mở upload endpoint nhận file tùy ý chỉ để học về GET streaming.

### 18.5. Lỗi TLS/HTTP proxy

Server demo là HTTP plaintext loopback; để test certificate chain, hostname verification, mutual TLS hoặc proxy CONNECT, dùng một `HttpsServer`/mock proxy được cấu hình đúng và kiểm tra riêng. Không tắt certificate verification để "làm chạy test".

## 19. Debug bằng status line, headers, body, cuối cùng mới tới business logic

Khi một bài thực nghiệm không ra kết quả như ý, hãy kiểm tra theo thứ tự:

```text
(1) Port đang listen? bind đúng 127.0.0.1?
    |
(2) URI path/method gửi có khớp HttpContext?
    |
(3) Handler có set header trước sendResponseHeaders?
    |
(4) ResponseLength = N, 0 hay -1?
    |
(5) Body có ghi đúng N bytes và đóng stream?
    |
(6) Client có auto-follow redirect hay không?
    |
(7) Client đang đọc String hay streaming InputStream?
    |
(8) Lỗi là HTTP status, IOException hay parser error?
    |
(9) Cleanup đã stop server và đóng body chưa?
```

Dùng `curl -i` để xem status+headers+body hoặc `curl -I` để gửi HEAD. Nếu dùng Windows PowerShell, gọi `curl.exe` khi cần tránh alias. Không dùng server log ghi nguyên credentials, Cookie/Authorization headers hoặc dữ liệu riêng tư.

**Lỗi rất thường thấy:** HTTP server trả fixed-length response 9 bytes nhưng code khai length 8 vì dùng `String.length()`. Khi client báo lỗi incomplete/connection closed, kiểm tra byte count trước khi nghi ngờ network.

## 20. Bảng lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng port 8000 cố định ở mọi integration test | Dễ conflict khi chạy song song | Dùng `InetSocketAddress("127.0.0.1",0)` |
| Bind `0.0.0.0` cho fixture local | Bất ngờ mở ra network | Bind loopback |
| Không gọi `server.stop(0)` trong finally | Leak port/threads | Cleanup lifecycle |
| `sendResponseHeaders(200,0)` tưởng body rỗng | Tạo chunked semantics ngoài ý muốn | Dùng `-1` khi không body |
| `sendResponseHeaders(200,"Xin chào".length())` | Byte count UTF-8 lệch | Dùng `getBytes(UTF_8).length` |
| Khai N nhưng ghi ít/hơn N bytes | Connection abort/truncation | Ghi chính xác N |
| Thay header sau khi gửi response | Header đã được commit | Set trước `sendResponseHeaders` |
| Không đóng OutputStream/HttpExchange | Exchange/connection leak | try-with-resources |
| Gọi `GET` route nhưng quên validate method | Route nhận POST ngoài ý muốn | Switch method, trả 405/Allow |
| `createContext("/api",...)` coi là exact match | Prefix matching nhận path khác | Xác thực URI path trong handler |
| Giả định `write/flush` tương đương `read()` của client | Test timing không ổn định | Kiểm tra logical body/order |
| Dùng `ofString()` cho payload unbounded | OOM | `ofInputStream()` + size quota |
| Gọi `send()` rồi không kiểm tra status | 404/429 bị coi thành công | Phân loại `statusCode()` |
| Tưởng `Retry-After` làm HttpClient tự retry | Rate limit bị xử lý sai | Client policy riêng |
| Dùng `Redirect.NORMAL` cho URL user kiểm soát | Có thể follow host cấm | NEVER + validate từng hop |
| Copy Authorization qua redirect | Rò token | Origin-scoped credential handling |
| Tạo response 200 rồi muốn đổi thành 500 giữa stream | Status đã gửi | Application error event/abort + client validation |
| Không giới hạn request body | Test server bị treo/hết RAM | Bounded reader và timeout |
| Dùng thread pool vô hạn cho test nhiều client | Quá tải/cạn resources | Executor có bounded work |
| Đọc response không đóng InputStream | Leak HTTP connection | try-with-resources |
| Coi HEAD Content-Length là bytes body của HEAD | Chờ body không có | HEAD chỉ metadata |
| Tưởng localhost server là production-ready | Thiếu auth/TLS/observability | Chỉ dùng test/prototyping |

## 21. Ma trận test mở rộng

| Tình huống | Đầu vào/handler | Điều client cần xác nhận |
| --- | --- | --- |
| GET 200 | `/fixed` | Status 200, body `hello` đúng 5 bytes |
| HEAD | `HEAD /fixed` | Status 200, no body, Content-Length=5 |
| 400 | `/bad-request` | Nhận JSON error, không coi success |
| 404 | `/not-found` | Not found rõ ràng |
| 429 | `/limited` | Retry-After=2, không retry mù |
| 503 | `/unavailable` | Retry-After=3, classify overload |
| 405 | `POST /fixed` | Allow=GET,HEAD |
| 302 NEVER | `/redirect` | Status 302 + Location |
| 307→302 NORMAL | `/redirect-307` | Status cuối 200, URI cuối /fixed |
| Streaming chunked | `/stream` | Status 200, body one|two, Transfer-Encoding |
| Body vượt quota | `/stream-large` | Client reject khi vượt 10 bytes |
| Body truncated | `/truncated` | Client fail, không publish |
| Empty response | 204/-1 | No body, không chờ bytes |
| Request body quá lớn | POST với Content-Length/no length | Server reject/413 theo policy |
| Content-Type sai | Server trả HTML thay JSON | Client reject trước parse |
| Disconnect trước headers | Server/socket đóng sớm | IOException, không có HTTP status |
| Slow headers | Handler trì hoãn sendResponseHeaders | Client timeout/cancel |
| Slow body | Chunked mỗi phút một byte | Idle-read/total deadline |
| Concurrent clients | Nhiều HttpClient request | Executor và queue trong giới hạn |
| Path prefix ambiguity | /api vs /api-secret | Handler không cấp quyền dựa trên context prefix |
| Redirect out-of-origin | Location host khác | Client policy từ chối |
| Resume Range | 206/Content-Range hợp lệ | Chỉ append đúng offset/version |
| SSE | text/event-stream | Parse event theo dòng/trống, không theo chunk |
| Cleanup | Assertion fail giữa chừng | Server stop, stream close |
| Parallel CI | Hai bài chạy cùng máy | Port 0 tránh va chạm |

Đây là **ma trận đề xuất**, không phải tất cả các trường hợp đã được chương trình mục 9 thực thi. Chỉ những dòng được in trong stdout của chương trình mới là những quan sát trực tiếp đã kiểm thử; những hàng còn lại cần thêm handlers/tests nếu sản phẩm của bạn yêu cầu.

## 22. Bài tập thực hành

**Bài 1.** Tại sao `sendResponseHeaders(200, 0)` không có nghĩa "gửi body trống"? Nếu muốn trả `204 No Content` thì nên chọn tham số thứ hai nào?

**Bài 2.** Server trả text `Xin chào`; nếu dùng `"Xin chào".length()` làm responseLength, điều gì có thể xảy ra? Vì sao?

**Bài 3.** Khi HTTP status là 404, `HttpClient.send(...)` nhất thiết có ném `IOException` hay không? Cần kiểm tra thuộc tính nào của response?

**Bài 4.** Với `GET /redirect` server trả `302 Location: /fixed`. Sự khác nhau giữa client `Redirect.NEVER` và `Redirect.NORMAL` trong server loopback cùng origin là gì?

**Bài 5.** Server gọi `out.write("one|")`, `flush()`, rồi `out.write("two")`. Có thể chắc chắn client đọc đúng hai lần với hai mảng byte tương ứng không?

**Bài 6.** Server khai fixed length 20 bytes, chỉ gửi 3 bytes rồi đóng connection. Client có thể coi HTTP 200 là tải xong không? Kiểu lỗi nào cần xử lý?

**Bài 7.** Vì sao server dùng `127.0.0.1:0` tốt hơn `0.0.0.0:8080` trong integration tests chạy trên CI?

**Bài 8.** Handler trả 429 với `Retry-After: 2`. Điều này có làm HttpClient tự chờ 2 giây và retry không? Nếu muốn retry an toàn cần gì?

**Bài 9.** Vì sao sau khi đã gọi `sendResponseHeaders(200,0)`, server không thể đổi status thành 500 nếu streaming parser/producer gặp lỗi?

**Bài 10.** Khi dùng `BodyHandlers.ofString()` để test stream rất lớn, rủi ro chính là gì? Đổi sang API nào nếu cần limit bytes theo từng lần đọc?

**Bài 11.** Server có context `/api`. Có nên dùng sự kiện context được gọi như bằng chứng request path đúng chính xác và đã được phân quyền không?

**Bài 12.** Lệnh `curl -L` làm gì? Vì sao chỉ nên dùng với redirect chain đã tin cậy trong bài thực nghiệm này?

**Bài 13.** `HEAD /fixed` có Content-Length=5 và bodyBytes=0. Đây có phải response sai không?

**Bài 14.** Khi gửi một lỗi JSON tự xây từ input do user nhập, vì sao không nên nối String trực tiếp để tạo JSON?

**Bài 15.** Để test HTTP client phát hiện body vượt quota 10 bytes, nên viết server stream như thế nào và client cần kiểm tra điều gì?

### Đáp án gợi ý

1. Trong JDK HttpExchange, 0 tạo chunked body; không body dùng -1.
2. Chuỗi dài 8 UTF-16 code units nhưng 9 UTF-8 bytes; fixed length lệch và server có thể ném IOException/abort.
3. Không. HTTP 404 vẫn là response hợp lệ; kiểm tra `response.statusCode()` rồi xử lý body lỗi theo contract.
4. NEVER trả 302/Location trực tiếp; NORMAL follow redirect hợp lệ trong môi trường test và có thể trả 200 từ /fixed.
5. Không. Buffers/chunked/TCP/HTTP client có thể gộp/chia; kiểm tra logical content và thứ tự.
6. Không. Body incomplete; cần xử lý IOException hoặc declared/actual length mismatch, không commit.
7. Loopback giảm phạm vi mạng; port 0 tránh tranh chấp khi tests chạy song song.
8. Không. Retry-After là gợi ý HTTP, cần policy retry có deadline, backoff và idempotency.
9. HTTP response status/headers đã commit; chỉ có thể báo lỗi bằng application protocol hoặc abort, không thay status cũ.
10. Có thể tích dữ liệu lớn trong RAM; dùng ofInputStream, đọc từng buffer với byte cap.
11. Không. Context dùng prefix matching; cần validate exact request path và authorization.
12. `-L` follow redirects; có thể đến host khác nếu không kiểm soát nên chỉ dùng trên fixture loopback.
13. Không. HEAD không có body; Content-Length có thể mô tả GET representation tương ứng.
14. Escape/serialization sai dẫn đến JSON không hợp lệ/injection; dùng JSON serializer.
15. Gửi chunked body lớn hơn 10 bytes; client đọc stream, cộng bytes và reject trước khi vượt max.

## 23. Tài liệu tham khảo

- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): tạo/bind listener, createContext, start, stop, executor.
- [Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): thứ tự response, sendResponseHeaders và ý nghĩa N/0/-1, đóng exchange.
- [Java SE 17 — HttpHandler](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): handler nhận và xử lý exchange.
- [Java SE 17 — HttpContext](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): context mapping và filters.
- [Java SE 17 — Headers](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): response/request headers.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): gửi HTTP requests, redirect policies.
- [Java SE 17 — HttpClient.Redirect](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html): NEVER, NORMAL và ALWAYS.
- [Java SE 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request method và timeout.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): ofString và ofInputStream.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): status codes, redirect, Retry-After, HEAD.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html): chunked framing và truncated messages.
- [MDN — Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): định dạng SSE và các sự kiện trên response stream.
