# Gửi status, header và body đúng thứ tự với HTTP server gọn trong Java 17+

## 1. Vấn đề cốt lõi: phản hồi HTTP có trình tự, không phải ba lời gọi tùy ý

Với HTTP server tích hợp trong JDK, API `com.sun.net.httpserver.HttpServer` và `HttpExchange` giúp tạo một dịch vụ HTTP nhỏ mà không cần thư viện web ngoài. Điểm dễ sai nhất khi bắt đầu là **gửi status, response headers và response body không đúng thứ tự**, hoặc nhầm độ dài ký tự Java với số byte được gửi.

**Quy tắc chính:**
1. Đọc/kiểm tra request method, path và request headers; nếu có request body thì đọc, validate và giới hạn nó.
2. **Xác định status và chuẩn bị toàn bộ response headers** bằng `exchange.getResponseHeaders()`.
3. Gọi **`exchange.sendResponseHeaders(statusCode, responseLength)` đúng một lần**. Đây là mốc bắt đầu gửi status/headers đến client.
4. **Sau đó** mới lấy `exchange.getResponseBody()` và ghi **đúng số byte** (nếu có body).
5. Đóng response output stream và kết thúc exchange; nếu có input body, bảo đảm nó được xử lý/đóng đúng vòng đời.

```text
HTTP request
     |
getRequestMethod / getRequestHeaders
     |
read/validate request body nếu có
     |
quyết định status + MIME type + representation
     |
getResponseHeaders().set(...)
     |
sendResponseHeaders(status, responseLength)     <-- COMMIT
     |
getResponseBody()
     |
write bytes / finish streaming nếu có
     |
close output stream + close exchange
     |
HTTP client nhận status, headers, body
```

**Không** có phương thức `setStatus(200)` riêng trong `HttpExchange`. Status và cách đóng khung body được quyết định ở `sendResponseHeaders(int,long)`. Các headers được đặt trước khi gọi phương thức này. Sau khi bắt đầu gửi phản hồi, bạn không thể tin rằng sửa `Headers` sẽ thay đổi những bytes header đã truyền qua mạng.

Theo tài liệu `HttpExchange` trên Java 17/25, **`sendResponseHeaders` phải được gọi trước `getResponseBody()`**. Nếu response body có độ dài cố định khác 0, **số byte ghi phải khớp hoàn toàn**; ghi quá/thiếu có thể tạo `IOException` và làm hủy exchange. Đây là một **contract I/O**, không chỉ một lời khuyên định dạng.

Bài này thuộc nhóm **HTTP server gọn**, tập trung cách gửi status/headers/body, xử lý fixed/chunked/no-body, UTF-8, các HTTP status thường gặp, HEAD, resource cleanup, lỗi trước/sau commit, security và kiểm thử client. Chỉ sử dụng API vẫn còn hỗ trợ trên Java 17 trở lên, đúng yêu cầu Special Note.

## 2. HTTP server gọn trong JDK 17+ gồm những gì?

Java cung cấp module **`jdk.httpserver`**, package **`com.sun.net.httpserver`**, với:
- `HttpServer`: tạo listener, bind địa chỉ/port, đăng ký đường dẫn, start/stop.
- `HttpHandler`: callback xử lý từng request; method `handle(HttpExchange)`.
- `HttpExchange`: một cặp request/response, cung cấp method, URI, request/response headers, input/output streams.
- `Headers`: map header names (không phân biệt hoa/thường), hỗ trợ `set`/`add`/`getFirst`.
- `HttpContext`: ánh xạ đường dẫn sang handler.
- `HttpsServer`: biến thể server có TLS khi được cấu hình HTTPS đúng cách.

```java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8080), 0);
server.createContext("/hello", exchange -> {
    try (exchange) {
        byte[] bytes =
                "Xin chào".getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }
});
server.start();
```

Đây là **snippet minh họa**, không phải file độc lập; cần imports `HttpServer`, `InetSocketAddress`, `StandardCharsets`, `OutputStream` và mã quản lý shutdown của server. Chỉ nên bind localhost trong môi trường học tập. Chương trình hoàn chỉnh có stop, executor và integration client ở mục 10.

`HttpServer` là API HTTP server đơn giản vẫn được hỗ trợ trong JDK hiện hành, **không bị coi là legacy chỉ vì package có `com.sun`**. Tuy nhiên, nó không tự là một giải pháp production gateway đầy đủ: TLS, authentication, rate limits, request size/timeouts, metrics, routing phức tạp và các HTTP edge cases cần thiết kế/cấu hình riêng. Với hệ thống public-facing, đánh giá framework/gateway đã được vận hành và bảo vệ thích hợp.

### 2.1. Module và classpath

Ở JDK tiêu chuẩn, các class trên nằm trong module `jdk.httpserver`. Với chương trình classpath đơn giản, ví dụ Java 17 ở mục 10 đã biên dịch bằng:

```bash
javac --release 17 -encoding UTF-8 HttpResponseOrderDemo.java
java HttpResponseOrderDemo
```

Không cần `--enable-preview` hoặc JAR ngoài JDK. Với dự án dùng `module-info.java`, khai báo:

```java
module example.http {
    requires jdk.httpserver;
}
```

Đây là snippet của `module-info.java`. Nó không đồng nghĩa Java `HttpClient` nằm trong cùng module: client chuẩn thuộc **`java.net.http`**, nên khi dùng module-info cho chương trình có cả server và client, bổ sung `requires java.net.http;`. Nếu dựng runtime image qua `jlink`, phải bao gồm các module cần thiết.

### 2.2. Một exchange là một request-response

Mỗi lần handler được gọi, `HttpExchange` đại diện **một lần trao đổi**. Nó không phải stream dùng chung giữa các requests; không lưu `HttpExchange` vào singleton/global map và cho nhiều threads cùng ghi. Mỗi handler phải kết thúc exchange và giải phóng resources trên mọi đường xử lý, kể cả 4xx/5xx.

`HttpExchange` **implements `AutoCloseable` trên Java 17**, nên `try (exchange) { ... }` là hợp lệ và giúp dọn request/response streams. Có thể đồng thời dùng `try (OutputStream out = exchange.getResponseBody())` để đóng stream đầu ra sớm/rõ ràng khi ghi xong. Tránh vô tình đóng stream trước khi đã gửi đủ số byte fixed-length.

## 3. Thứ tự đúng của status, headers và body

### 3.1. Chuẩn bị trước khi gửi

Trước khi `sendResponseHeaders`, quyết định:
- **Status**: `200 OK`, `201 Created`, `204 No Content`, `400 Bad Request`, `404 Not Found`, `405 Method Not Allowed`, `500 Internal Server Error`…
- **Content-Type**: loại body thực tế, thường kèm charset nếu là text.
- **Location**: khi tạo resource mới, redirect hoặc tình huống HTTP cần vị trí.
- **Allow**: khi từ chối HTTP method bằng 405.
- **Cache-Control`/`ETag`**: nếu có chính sách cache.
- **Content-Encoding** nếu thực sự nén body (không được khai “gzip” cho plain bytes).
- **Security headers** phù hợp nội dung/site, nhưng không tự thêm headers không đúng ngữ nghĩa.

Ví dụ:

```java
Headers headers = exchange.getResponseHeaders();
headers.set("Content-Type", "application/json; charset=utf-8");
headers.set("Cache-Control", "no-store");

byte[] response = "{\"ok\":true}".getBytes(
        StandardCharsets.UTF_8);

exchange.sendResponseHeaders(200, response.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(response);
}
```

Đây là **snippet** trong một handler, với `HttpExchange exchange` đã tồn tại; cần import `Headers`, `StandardCharsets`, `OutputStream`. Nó thể hiện **headers → sendResponseHeaders → response stream**. Phải đóng exchange trong scope bao ngoài.

### 3.2. Vì sao không gọi getResponseBody() trước?

`getResponseBody()` có precondition trong Javadoc: `sendResponseHeaders(int,long)` phải được gọi trước. Trình tự sai có thể gây lỗi từ server implementation hoặc dẫn tới response chưa được khởi tạo đúng; không thử workaround bằng cách gọi `getResponseBody()` rồi “để server tự thêm status”.

```java
// SAI: gọi lấy body trước khi gửi status/headers.
OutputStream out = exchange.getResponseBody();
exchange.sendResponseHeaders(200, 100);
out.write(data);
```

Đây là snippet **sai có chủ ý**, các biến `exchange` và `data` không được định nghĩa trong đây. Không dùng trong production.

### 3.3. Headers sau commit sẽ không tự cập nhật trên dây

`sendResponseHeaders` gửi status line và response headers đang có. Vì vậy:
- Đặt `Content-Type`, `Location`, `Allow` trước.
- Không gửi body trước khi xác định status/headers.
- Không coi `getResponseHeaders().set("X-...", "...")` sau `sendResponseHeaders` là một header client sẽ nhận được.
- Không gọi lại `sendResponseHeaders` để “đổi 200 thành 500”; gọi lần thứ hai sẽ vi phạm contract và có thể ném `IOException`.
- Nếu cần biết đã đặt response code hay chưa, `getResponseCode()` có thể trả `-1` trước khi code được đặt, nhưng **đó không phải một cơ chế khôi phục chắc chắn** nếu I/O đã thất bại giữa chừng.

**Điểm commit:** sau khi status/headers đã bắt đầu đi ra network, lỗi của code tạo body không thể biến thành một response HTTP mới với status khác. Phải log/cancel/close và để client biết response bị lỗi hoặc thiếu dữ liệu; chuẩn bị trước body khi kích thước nhỏ, hoặc thiết kế streaming/error protocol rõ ràng.

## 4. Hiểu đúng responseLength của sendResponseHeaders

`sendResponseHeaders(int rCode, long responseLength)` có **ba chế độ** cực kỳ quan trọng, khác với ý nghĩa của `Content-Length` trong HTTP:

| `responseLength` | Ý nghĩa trong `HttpExchange` | Khi sử dụng |
| --- | --- | --- |
| **`> 0`** | Body có **độ dài cố định đúng bằng N bytes**; ghi đúng N bytes. | Payload đã biết, ví dụ JSON/text đã encode thành byte[]. |
| **`0`** | Dùng **chunked transfer encoding** cho HTTP/1.1, body có độ dài tùy ý, kết thúc bằng đóng OutputStream. | Streaming khi chưa biết body length trước. |
| **`-1`** (hoặc ≤ -1 theo API) | **Không gửi response body**. | `204`, `304`, `HEAD`, hoặc response không có body. |

**Bẫy số 0:** trong `HttpExchange`, **`sendResponseHeaders(200, 0)` không có nghĩa “Content-Length: 0”**. Nó chọn chế độ chunked (với HTTP/1.1). Nếu bạn muốn **không gửi body**, dùng `-1` thay vì `0`.

**Bẫy fixed length:** `sendResponseHeaders(200, 100)` cần đúng **100 bytes**, không phải 100 Java `char`, 100 Unicode codepoints hay “khoảng 100”. Viết 101 bytes có thể làm `write` ném `IOException`; viết chỉ 99 bytes có thể khiến `OutputStream.close()` ném `IOException`, abort exchange và đóng TCP connection. Đây là hành vi được nêu rõ trong Javadoc Java 17/25.

### 4.1. Body cố định: encode trước, đo bytes, ghi đúng

```java
String text = "Xin chào 🌏";
byte[] payload = text.getBytes(StandardCharsets.UTF_8);

exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.sendResponseHeaders(200, payload.length);

try (OutputStream out = exchange.getResponseBody()) {
    out.write(payload);
}
```

Đây là snippet. `String.length()` cho một chuỗi Unicode là số **UTF-16 code units**, còn `payload.length` là số **UTF-8 bytes**. Trên chuỗi `"Xin chào 🌏"`, ví dụ đã kiểm chứng **`payload.length == 14`**; không dùng `text.length()` làm `responseLength`.

**Đừng tự đặt `Content-Length` thủ công** khi trả fixed-length body bình thường bằng `sendResponseHeaders`. API đã biết byte count và quản lý header phù hợp. Việc tự đặt một header Content-Length mâu thuẫn với số bytes thực tế có thể làm client gặp lỗi/framing mismatch. Ngoại lệ cần cân nhắc riêng: `HEAD` có thể gửi Content-Length mô tả **GET representation** nhưng tuyệt đối không gửi body.

### 4.2. Streaming/chunked: chưa biết trước tổng số bytes

```java
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.sendResponseHeaders(200, 0);

try (OutputStream out = exchange.getResponseBody()) {
    out.write("A\n".getBytes(StandardCharsets.UTF_8));
    out.write("B\n".getBytes(StandardCharsets.UTF_8));
}
```

Đây là snippet được thể hiện trong chương trình đầy đủ mục 10. Nó gửi status/headers **trước**, sau đó từng đoạn body. Đóng `OutputStream` báo hết body. Trên HTTP/1.1, client nhận một stream được framed bằng chunked transfer encoding.

**Chunked không đồng nghĩa mỗi `write()` là một HTTP chunk.** Chunk boundaries là chi tiết transport/implementation; app và client không được dựa vào “1 lần write = 1 chunk”. Một `BodyHandler` thường lắp ráp lại body cho client. Muốn xác định ranh giới bản ghi business trong stream, dùng giao thức payload có framing riêng (ví dụ newline-delimited JSON) chứ không dựa vào HTTP chunks.

**Đừng hứa chunked trên mọi HTTP version.** Java `HttpServer` triển khai HTTP/1.1 trong test; khi dùng HTTP/2 ở gateway, cách đóng khung body khác. Mục tiêu ở đây là hiểu contract của `HttpExchange`, không thiết kế một HTTP/2 framing protocol.

### 4.3. Không có response body: -1

```java
exchange.sendResponseHeaders(204, -1);
```

Đây là snippet trong handler với exchange được đóng trong scope phù hợp. `204 No Content` không gửi representation body. **Không gọi `out.write(...)` sau đó**. Trả status/headers đúng và close exchange.

Một số status/method cấm gửi content:
- `1xx`: thông tin trung gian, không phải representation response thông thường.
- `204 No Content`: không có body.
- `205 Reset Content`: theo HTTP semantics không phát sinh content; áp dụng contract/no-body phù hợp.
- `304 Not Modified`: không gửi representation body.
- `HEAD`: client nhận status/headers mô tả response GET tương ứng nhưng **không** có body.

Với `HttpExchange`, dùng `-1` cho những trường hợp no-body, và chỉ đặt headers được HTTP semantics cho phép.

### 4.4. 200 rỗng và -1 so với 0

Nếu handler cần trả `200` nhưng thực sự không có body:
- `sendResponseHeaders(200, -1)` biểu diễn không gửi body.
- `sendResponseHeaders(200, 0)` chọn response stream chunked; đóng stream ngay sẽ kết thúc một body rỗng theo framing chunked.

Cả hai có thể khiến client đọc chuỗi rỗng, **nhưng wire framing/headers khác nhau**. Không tự viết code khẳng định `0` tạo Content-Length 0.

### 4.5. Content-Length và Transfer-Encoding không được trộn tùy ý

Với cố định `N>0`, để `HttpExchange` tạo framing/Content-Length. Với `0`, để implementation chọn chunked framing. Đừng tự đặt `Transfer-Encoding: chunked` trong `Headers` khi bạn cũng truyền fixed byte count; đừng tự phát bytes của các chunk vào `getResponseBody()` vì framework đang xử lý framing.

**HTTP response splitting:** không đưa untrusted CR/LF hoặc tên header tùy ý từ input vào `Headers`. Validate values, giới hạn length/size và dùng các header names/values được định nghĩa rõ. Không phản chiếu raw query parameters vào response headers nếu chưa kiểm soát.

## 5. Dùng Headers.set, Headers.add và getFirst

`getResponseHeaders()` trả `Headers` mutable; `getRequestHeaders()` trả headers của request để đọc. Names của headers **case-insensitive**. Các thao tác phổ biến:

```java
Headers h = exchange.getResponseHeaders();
h.set("Content-Type", "application/json; charset=utf-8");
h.set("Cache-Control", "no-store");
h.add("Vary", "Accept-Encoding");
h.add("Vary", "Accept-Language");
```

Đây là snippet; `exchange` đã có. Theo Javadoc:
- `set(name,value)` thay thế tập giá trị của header đó bằng **một** value.
- `add(name,value)` thêm **một** value nữa, tạo trường lặp nếu thích hợp.
- `getFirst(name)` trả value đầu tiên (hoặc null) nếu có.
- Với header single-valued như `Content-Type`, thường dùng `set`.
- Với header đa giá trị, cần hiểu semantic cụ thể trước khi dùng `add`; không phải header nào cũng an toàn để phát thành nhiều dòng độc lập.
- Với `Set-Cookie` (nếu có), các dòng riêng thường quan trọng; cần chú ý nhiều cookies, SameSite/Secure/HttpOnly và framework/session policy.

**Không nhầm request và response headers:** 
- `exchange.getRequestHeaders()` là metadata mà client đã gửi; không sửa nó để cố “thêm header response”.
- `exchange.getResponseHeaders()` là bộ header do server tạo, phải chỉnh **trước** `sendResponseHeaders`.

### 5.1. Content-Type và charset

Các ví dụ hợp lệ:
- Plain text: `text/plain; charset=utf-8`.
- HTML UTF-8: `text/html; charset=utf-8`.
- JSON: `application/json` (UTF-8 mặc định theo các JSON interoperability rules hiện hành; có thể dùng `application/json; charset=utf-8` nếu đối tác yêu cầu, như demo).
- Binary: MIME type tương ứng như `application/octet-stream` hoặc media type chính xác.

`Content-Type` phải **khớp với bytes thực sự gửi**. Không khai UTF-8 nhưng lại tạo bytes bằng platform-default encoding. Dùng `StandardCharsets.UTF_8` ở boundary.

**Không tính Content-Length từ `String.length()`.** Với non-ASCII tiếng Việt và emoji, ký tự/UTF-16 units không bằng bytes, và fixed-length stream có thể bị abort vì ghi thừa so với khai báo.

### 5.2. Location, Allow, caching và security

- `201 Created` có thể kèm `Location` trỏ đến resource vừa tạo nếu operation tạo ra resource.
- `405 Method Not Allowed` cần `Allow` liệt kê methods có thể dùng cho target resource; demo dùng `GET, HEAD`.
- `304 Not Modified` dùng metadata/cache validators (`ETag` hoặc `Last-Modified`) phù hợp conditional request; không gửi body.
- `Cache-Control: no-store` với responses chứa thông tin nhạy cảm, khi phù hợp nghiệp vụ.
- `X-Content-Type-Options: nosniff` và `Content-Security-Policy` cho các bối cảnh web phù hợp; không chèn chính sách ngẫu nhiên mà chưa hiểu target.
- CORS headers không tự động làm endpoint được authenticate; chỉ định origin/method/headers theo chính sách.
- Không cho phép client quyết định arbitrary `Location` để tránh open redirect.

## 6. Chọn status code theo kết quả thực, trước commit

| Status | Ý nghĩa thường dùng | Body | Headers cần cân nhắc |
| --- | --- | --- | --- |
| `200 OK` | Truy vấn thành công. | Có thể có body; nếu body fixed N>0, truyền N. | `Content-Type`, cache policy. |
| `201 Created` | Tạo resource thành công. | Có thể có JSON xác nhận. | `Location` khi có URI mới. |
| `202 Accepted` | Yêu cầu được nhận để xử lý sau. | Có thể có trạng thái/job ID. | Retry/polling contract theo ứng dụng. |
| `204 No Content` | Thành công nhưng không có representation body. | **Không có body**, dùng -1. | ETag nếu phù hợp, không Content-Length của body. |
| `301/302/303/307/308` | Redirect theo semantics từng mã. | Có thể có hoặc không. | `Location`. |
| `304 Not Modified` | Conditional request trùng cache validator. | **Không có body**, dùng -1. | ETag, Cache-Control/Last-Modified phù hợp. |
| `400 Bad Request` | Request không hợp lệ. | Thường trả error JSON/text nhỏ. | `Content-Type`, bảo vệ dữ liệu nhạy cảm. |
| `401 Unauthorized` | Cần authentication hợp lệ. | Có thể trả error body. | `WWW-Authenticate` khi cần theo HTTP semantics. |
| `403 Forbidden` | Không được phép. | Có thể trả error body. | Không lộ phân quyền nội bộ. |
| `404 Not Found` | Không tìm thấy route/resource. | Có thể trả error body. | `Content-Type`. |
| `405 Method Not Allowed` | Method không được hỗ trợ cho target. | Có thể trả error body. | **`Allow`**. |
| `413 Content Too Large` | Payload vượt size policy. | Có thể trả error body. | Connection/stream cleanup. |
| `415 Unsupported Media Type` | Body media type không hỗ trợ. | Có thể trả error body. | Media type trong message. |
| `429 Too Many Requests` | Quota/rate limit. | Có thể trả error body. | `Retry-After` nếu có giá trị phù hợp. |
| `500 Internal Server Error` | Lỗi xử lý server **trước khi commit**. | Error body chung, không stack trace nội bộ. | `Content-Type`, no-store theo policy. |
| `503 Service Unavailable` | Service không sẵn sàng. | Có thể trả error body. | `Retry-After` nếu biết khoảng thời gian. |

**Phân biệt HTTP status và Java exception:** Không có quy tắc “mọi `IOException` sẽ tự trả 500”. Nếu response đã commit 200 rồi output stream lỗi, Java không thể thu hồi status đã gửi trên wire. Log/metrics, đóng connection, và để client nhận biết incomplete response.

**Không trả 200 rồi nhét `{"error":...}` vào body cho một request đã thất bại**, trừ khi đó là contract application-specific có chủ đích. HTTP status phải phản ánh outcome theo API semantics. Cố gắng xác định lỗi có thể biết trước khi gọi `sendResponseHeaders`.

## 7. Xử lý HEAD, 204, 304, 205 đúng cách

### 7.1. HEAD: metadata giống GET, không ghi body

Theo HTTP semantics, HEAD cho phép client lấy metadata của representation mà không tải nội dung. Java demo ở mục 10 có nhánh:

```java
if ("HEAD".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=utf-8");
    exchange.getResponseHeaders().set(
            "Content-Length",
            Integer.toString(
                "Xin chào 🌏".getBytes(StandardCharsets.UTF_8).length));

    exchange.sendResponseHeaders(200, -1);
    // Không ghi body cho HEAD.
}
```

Đây là snippet; trong handler hoàn chỉnh có `try (exchange)`. `Content-Length=14` là **metadata về body GET tương ứng**, không phải dữ liệu HEAD thực sự được gửi. Đây là một trường hợp HTTP cho phép đặt Content-Length thủ công **trước** `sendResponseHeaders(200,-1)`; JDK demo đã kiểm chứng client nhận `headContentLength=14` và body rỗng.

**Không gọi `sendResponseHeaders(200, bytes.length)` rồi không ghi bytes cho HEAD** — fixed-length contract có thể gây warning/stream mismatch. Sử dụng -1 để diễn đạt no-body. Khi body GET được tạo động, hãy thận trọng trước khi gắn Content-Length cho HEAD nếu không biết chắc GET representation length.

### 7.2. 204 No Content

```java
exchange.sendResponseHeaders(204, -1);
```

Không có body. HTTP `204` không được chứa response content; không đặt Content-Type/Content-Length không cần thiết. Trong demo, client nhận `204` và body là chuỗi rỗng.

### 7.3. 304 Not Modified

Khi conditional request dùng cache validator và phía server xác định client đã có phiên bản phù hợp:

```java
exchange.getResponseHeaders().set("ETag", "\"revision-7\"");
exchange.sendResponseHeaders(304, -1);
// Không gửi representation body.
```

Đây là snippet với `exchange` đã có, không phải chương trình độc lập. `304` phải tuân semantics HTTP cache, không trả như một 200 response với body rỗng mặc dù cả hai có thể khiến client thấy không có bytes. Việc so khớp `If-None-Match`/`If-Modified-Since` và phát các headers cache cần đúng chuẩn/ứng dụng; snippet chỉ thể hiện **thứ tự gửi**.

### 7.4. 205 Reset Content và các 1xx

`205 Reset Content` yêu cầu server không gửi content. Trong `HttpExchange`, no-body mode `-1` là cách đơn giản để tránh ghi payload; các response framing constraints của HTTP semantics vẫn phải được tôn trọng. Với `1xx`, không dùng đoạn handler đơn giản làm cơ chế trao đổi nhiều informational responses; `HttpServer` là server gọn, không tự biến việc gọi nhiều lần `sendResponseHeaders` thành chuỗi 100 Continue + 200 như một HTTP stack đầy đủ.

**Ghi nhớ:** có những status không được gửi body theo HTTP specification, **không phải vì body.length==0**, mà do semantics của status/method.

## 8. Lỗi xảy ra trước và sau khi gửi response headers

### 8.1. Trước commit: còn có thể chọn status phù hợp

Một pattern đúng:
1. Parse và validate input có **size limit**.
2. Kiểm tra authentication/authorization.
3. Thực hiện hoặc chuẩn bị kết quả nghiệp vụ.
4. Xác định success/error status, content type, payload.
5. Sau cùng mới `sendResponseHeaders` + write.

Nếu code có thể gây lỗi trước commit, bắt lỗi dự kiến và tạo error response có kiểm soát. Ví dụ:

```java
try {
    Result result = performBusinessAction();
    byte[] bytes = result.toJson()
            .getBytes(StandardCharsets.UTF_8);
    exchange.getResponseHeaders().set(
            "Content-Type", "application/json; charset=utf-8");
    exchange.sendResponseHeaders(200, bytes.length);
    try (OutputStream out = exchange.getResponseBody()) {
        out.write(bytes);
    }
} catch (BadInputException ex) {
    // Chỉ có thể gửi 400 nếu response chưa bắt đầu commit.
    // Viết hàm chuẩn hóa lỗi khi biết chắc headers chưa gửi.
}
```

Đây là **pseudocode**; `Result`, `BadInputException` và `performBusinessAction()` không được định nghĩa, không phải chương trình Java runnable. Nó nhấn mạnh **phân tách chuẩn bị response khỏi commit**. Trong implementation thật, tránh catch `IOException` sau khi đã commit rồi cố gửi thêm một 500 response; lúc này chỉ có thể đóng/abort exchange và ghi nhận lỗi.

### 8.2. Sau commit: không thể đổi 200 thành 500

Ví dụ sai có chủ ý:

```java
exchange.sendResponseHeaders(200, 0);
try (OutputStream out = exchange.getResponseBody()) {
    streamPotentiallyFailingData(out);
} catch (IOException problem) {
    // SAI: status 200 đã gửi, không gửi lại headers:
    exchange.sendResponseHeaders(500, -1);
}
```

Đây là **pseudocode anti-pattern**, method `streamPotentiallyFailingData` chưa được định nghĩa. Gọi `sendResponseHeaders` lần hai sẽ vi phạm contract. Nếu stream lỗi sau khi 200 đã bắt đầu, log metric theo correlation ID và đóng exchange; với giao thức streaming, có thể có cơ chế báo lỗi ở **payload protocol** nếu nó được thiết kế từ đầu, nhưng không thể đổi HTTP status đã truyền.

### 8.3. Fixed length mismatch

Giả sử `byte[] payload` có 14 bytes nhưng:
- `sendResponseHeaders(200, 10)` → `write(payload)` cố ghi thừa bytes, có thể ném `IOException`.
- `sendResponseHeaders(200, 20)` → chỉ ghi 14 bytes rồi đóng, `close()` có thể ném `IOException` vì chưa gửi đủ N.
- `sendResponseHeaders(200, payload.length)` → đúng 14 bytes, body đầy đủ.
- `sendResponseHeaders(200, 0)` → chuyển sang chunked mode, không phải một cách “sửa số 14” nếu thực ra bạn đã biết độ dài chính xác.

Không ghi test chủ động phá kết nối vào production để thử mismatched lengths. Unit/integration test trên loopback có thể kiểm tra success cases, còn failure behavior dựa trên Javadoc và fault-injection test có kiểm soát.

### 8.4. Ưu tiên tính nhất quán hơn việc bắt mọi lỗi

Một error handler gom `catch (Exception e)` rồi luôn gửi `500` không đúng nếu:
- Client gửi data sai → có thể là `400`.
- Request method bị cấm → `405` và `Allow`.
- Không tìm thấy resource → `404`.
- Đã gửi headers → không thể tạo một HTTP response mới.
- Connection bị đóng trước khi hoàn tất → có thể chỉ là client disconnect.
- Source đã đọc một phần hoặc downstream đã commit DB transaction → cần rollback/idempotency.

Xử lý lỗi dựa trên **giai đoạn của exchange** và semantics nghiệp vụ. Không log raw tokens, passwords hoặc PII trong request/body để debug.

## 9. Kết thúc exchange, đọc request body và quản lý executor

### 9.1. Close response body là phần của protocol

Theo Javadoc `HttpExchange`, exchange kết thúc khi request `InputStream` và response `OutputStream` đều được đóng. `OutputStream.close()` gián tiếp đóng request input nếu chưa đóng; `HttpExchange.close()` cũng đóng cả hai theo thứ tự. Không dừng ở `out.flush()` rồi quên `close()`, đặc biệt với chunked body, vì client có thể đợi dấu kết thúc stream.

Ví dụ:
```java
try (exchange) {
    exchange.sendResponseHeaders(204, -1);
}
```

Đây là snippet; `HttpExchange` implements AutoCloseable ở Java17. Với response có body, dùng try-with-resources cho `OutputStream` như mã đầy đủ. Nếu request có body, đọc và validate có giới hạn rồi đóng trước khi trả response khi phù hợp.

### 9.2. Không đọc request body vô hạn

Một handler xử lý POST:
- Giới hạn bytes trước và trong khi đọc body, không dựa duy nhất vào `Content-Length`.
- Đặt request timeout và authentication/authorization.
- Kiểm tra method/content type, CSRF/CORS theo kiến trúc web.
- Không gọi `exchange.getRequestBody().readAllBytes()` với nguồn không tin cậy mà không có budget.
- Nếu body không được tiêu thụ hết trước khi đóng, keep-alive/TCP reuse có thể bị ảnh hưởng; cân nhắc drain có giới hạn hoặc đóng kết nối theo policy.
- Không phản chiếu raw request headers/body vào response error.

Demo sử dụng `HttpRequest.BodyPublishers.noBody()` cho POST tạo resource giả định, nên không cần parse request body và không hướng dẫn đọc vô hạn.

### 9.3. Executor, stop và shutdown

`HttpServer.setExecutor(Executor)` cho phép điều khiển threads xử lý requests. Với `ExecutorService` tự tạo, chương trình phải quản lý vòng đời:
1. Tạo server và executor.
2. Đăng ký contexts trước khi `start()`.
3. Start server, nhận requests.
4. Khi hoàn tất, `server.stop(delaySeconds)` theo ngữ nghĩa API.
5. `executor.shutdown()` hoặc `shutdownNow()` theo policy và xử lý tasks đang chạy.

Demo dùng fixed thread pool 2 threads và `shutdownNow()` khi kết thúc kiểm thử, phù hợp môi trường local. Trong production, shutdown cần graceful draining/in-flight semantics và thời hạn hợp lý; không dùng `shutdownNow()` như mặc định cho yêu cầu đang xử lý tài chính.

### 9.4. Route matching là prefix matching

Một `HttpContext` đăng ký `"/fixed"` có thể match cả path bắt đầu bằng `"/fixed"`, chẳng hạn `"/fixed-extra"`, vì `HttpServer` chọn context theo cơ chế longest matching prefix (có phân biệt chữ hoa/thường theo đường dẫn). Không giả định `createContext("/users", ...)` tự triển khai exact route pattern `/users/{id}` an toàn.

Nếu các tuyến có yêu cầu authorization khác nhau, kiểm tra `exchange.getRequestURI().getPath()` và route semantics rõ ràng trước khi thao tác. Đừng coi một đường dẫn bị match ngoài dự kiến là được phép. Tài liệu `HttpServer` JDK17 nêu ví dụ `/foo` có thể match `/foobar`.

## 10. Chương trình Java 17+ đầy đủ và kiểm thử HTTP client tại chỗ

Chương trình **`HttpResponseOrderDemo.java`** tạo HTTP server trên **127.0.0.1 với cổng ngẫu nhiên**. Nó gửi các responses với status/headers/body đúng thứ tự, rồi dùng `java.net.http.HttpClient` (đang được hỗ trợ trên Java17+) để kiểm tra thực tế.

Các endpoints:
- `GET /fixed`: status `200`, `Content-Type` UTF-8, custom header và body tiếng Việt/emoji fixed-length.
- `GET /stream`: status `200`, `responseLength=0`, chunked body gồm hai đoạn.
- `POST /created`: status `201`, `Location` và JSON body nhỏ. **Demo tạo phản hồi tĩnh**, không thực sự ghi database.
- `GET /empty`: status `204`, không body.
- `HEAD /fixed`: status `200`, Content-Length metadata `14`, không body.
- `PUT /fixed`: status `405`, `Allow: GET, HEAD`.
- `GET /missing`: status `404`, text tiếng Việt.

Mọi response được xác thực bằng `expect/require` theo status, headers và body; nếu sai, chương trình ném `AssertionError` thay vì in kết quả success giả.

### 10.1. Toàn bộ file HttpResponseOrderDemo.java

```java
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class HttpResponseOrderDemo {
    private static final String TYPE = "text/plain; charset=utf-8";
    private static final String GREETING = "Xin chào 🌏";

    private static void sendText(HttpExchange ex,
                                 int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", TYPE);
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static void fixed(HttpExchange ex) throws IOException {
        try (ex) {
            Headers headers = ex.getResponseHeaders();
            if ("HEAD".equals(ex.getRequestMethod())) {
                headers.set("Content-Type", TYPE);
                headers.set("Content-Length", Integer.toString(
                        GREETING.getBytes(StandardCharsets.UTF_8).length));
                ex.sendResponseHeaders(200, -1);
            } else if ("GET".equals(ex.getRequestMethod())) {
                headers.set("X-Demo", "fixed");
                sendText(ex, 200, GREETING);
            } else {
                headers.set("Allow", "GET, HEAD");
                sendText(ex, 405, "Method Not Allowed");
            }
        }
    }

    private static void stream(HttpExchange ex) throws IOException {
        try (ex) {
            ex.getResponseHeaders().set("Content-Type", TYPE);
            ex.sendResponseHeaders(200, 0);
            try (OutputStream out = ex.getResponseBody()) {
                out.write("A\n".getBytes(StandardCharsets.UTF_8));
                out.write("B\n".getBytes(StandardCharsets.UTF_8));
            }
        }
    }

    private static void created(HttpExchange ex) throws IOException {
        try (ex) {
            if (!"POST".equals(ex.getRequestMethod())) {
                ex.getResponseHeaders().set("Allow", "POST");
                sendText(ex, 405, "Method Not Allowed");
                return;
            }
            byte[] bytes = "{\"id\":7}".getBytes(StandardCharsets.UTF_8);
            ex.getResponseHeaders().set(
                    "Content-Type", "application/json; charset=utf-8");
            ex.getResponseHeaders().set("Location", "/created/7");
            ex.sendResponseHeaders(201, bytes.length);
            try (OutputStream out = ex.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    private static void empty(HttpExchange ex) throws IOException {
        try (ex) {
            ex.sendResponseHeaders(204, -1);
        }
    }

    private static void notFound(HttpExchange ex) throws IOException {
        try (ex) {
            sendText(ex, 404, "Không tìm thấy");
        }
    }

    private static void require(boolean good, String label) {
        if (!good) throw new AssertionError(label);
    }

    private static HttpRequest get(URI uri) {
        return HttpRequest.newBuilder(uri).GET().build();
    }

    private static HttpResponse<String> call(
            HttpClient client, HttpRequest request) throws Exception {
        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        server.setExecutor(pool);
        server.createContext("/fixed", HttpResponseOrderDemo::fixed);
        server.createContext("/stream", HttpResponseOrderDemo::stream);
        server.createContext("/created", HttpResponseOrderDemo::created);
        server.createContext("/empty", HttpResponseOrderDemo::empty);
        server.createContext("/", HttpResponseOrderDemo::notFound);
        server.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            URI base = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort());

            HttpResponse<String> fixed =
                    call(client, get(base.resolve("/fixed")));
            require(fixed.statusCode() == 200, "fixed status");
            require(GREETING.equals(fixed.body()), "fixed UTF-8 body");
            require(TYPE.equals(fixed.headers()
                    .firstValue("content-type").orElse("")), "fixed type");
            require("fixed".equals(fixed.headers()
                    .firstValue("x-demo").orElse("")), "fixed header");
            System.out.println("fixedStatus=" + fixed.statusCode());
            System.out.println("fixedBody=" + fixed.body());
            System.out.println("fixedByteLength="
                    + GREETING.getBytes(StandardCharsets.UTF_8).length);

            HttpResponse<String> stream =
                    call(client, get(base.resolve("/stream")));
            require(stream.statusCode() == 200, "stream status");
            require("A\nB\n".equals(stream.body()), "stream body");
            require("chunked".equalsIgnoreCase(stream.headers()
                    .firstValue("transfer-encoding").orElse("")),
                    "chunked HTTP 1.1");
            System.out.println("streamStatus=" + stream.statusCode());
            System.out.println("streamChunked=true");
            System.out.println("streamBody=" + stream.body().replace('\n', '|'));

            HttpRequest post = HttpRequest.newBuilder(
                    base.resolve("/created"))
                    .POST(HttpRequest.BodyPublishers.noBody()).build();
            HttpResponse<String> created = call(client, post);
            require(created.statusCode() == 201, "201");
            require("/created/7".equals(created.headers()
                    .firstValue("location").orElse("")), "location");
            require("{\"id\":7}".equals(created.body()), "json");
            System.out.println("createdStatus=" + created.statusCode());
            System.out.println("createdLocation="
                    + created.headers().firstValue("location").orElse(""));
            System.out.println("createdBody=" + created.body());

            HttpResponse<String> empty =
                    call(client, get(base.resolve("/empty")));
            require(empty.statusCode() == 204 && empty.body().isEmpty(),
                    "204 no body");
            System.out.println("emptyStatus=" + empty.statusCode());
            System.out.println("emptyBodyEmpty=" + empty.body().isEmpty());

            HttpRequest headRequest = HttpRequest.newBuilder(
                    base.resolve("/fixed"))
                    .method("HEAD", HttpRequest.BodyPublishers.noBody()).build();
            HttpResponse<String> head = call(client, headRequest);
            require(head.statusCode() == 200 && head.body().isEmpty(),
                    "HEAD no body");
            require(Integer.toString(
                    GREETING.getBytes(StandardCharsets.UTF_8).length)
                    .equals(head.headers()
                            .firstValue("content-length").orElse("")),
                    "HEAD Content-Length");
            System.out.println("headStatus=" + head.statusCode());
            System.out.println("headContentLength=" + head.headers()
                    .firstValue("content-length").orElse(""));
            System.out.println("headBodyEmpty=" + head.body().isEmpty());

            HttpRequest put = HttpRequest.newBuilder(base.resolve("/fixed"))
                    .PUT(HttpRequest.BodyPublishers.noBody()).build();
            HttpResponse<String> method = call(client, put);
            require(method.statusCode() == 405, "405");
            require("GET, HEAD".equals(method.headers()
                    .firstValue("allow").orElse("")), "Allow");
            System.out.println("methodStatus=" + method.statusCode());
            System.out.println("methodAllow="
                    + method.headers().firstValue("allow").orElse(""));

            HttpResponse<String> missing =
                    call(client, get(base.resolve("/missing")));
            require(missing.statusCode() == 404, "404");
            require("Không tìm thấy".equals(missing.body()), "404 text");
            System.out.println("missingStatus=" + missing.statusCode());
            System.out.println("missingBody=" + missing.body());
        } finally {
            server.stop(0);
            pool.shutdownNow();
        }
    }
}
```

**Giải thích thiết kế:**
- `sendText()` chuẩn bị bytes và Content-Type trước khi gửi `sendResponseHeaders`; helper chỉ được gọi trong demo với **body không rỗng**. Nếu bạn mở rộng để body có thể rỗng, hãy chọn `-1` hoặc chunked `0` theo chủ đích thay vì xem `bytes.length=0` là fixed zero.
- `fixed()` phân biệt HEAD/GET/other; HEAD có metadata Content-Length nhưng không body; method không được phép trả 405 cùng Allow.
- `stream()` chọn chunked bằng `responseLength=0`, đóng output để kết thúc.
- `created()` trả 201 + Location trước body, nhưng không lưu entity thật; chỉ minh họa response protocol.
- `empty()` gửi 204 + -1, không có payload.
- `notFound()` trả 404 với text UTF-8.
- `try (ex)` hợp lệ Java 17 vì `HttpExchange` implements `AutoCloseable`.
- `HttpClient` trong Java 17 **không dùng trực tiếp trong try-with-resources** vì phiên bản API đó chưa implements `AutoCloseable`; code giữ client trong scope `try/finally` phục vụ test loopback. API mới hơn có lifecycle methods khác, nhưng ví dụ giữ compatibility từ Java17.
- `HttpClient.Version.HTTP_1_1` được chọn rõ ràng để kiểm tra `Transfer-Encoding: chunked` trong môi trường loopback. Client ẩn đi framing khi trả body; `streamBody=A|B|` chỉ là format hiển thị các dấu xuống dòng.
- `server.stop(0)` và `pool.shutdownNow()` ở finally bảo đảm test không giữ listening port và threads mãi sau khi xong.

### 10.2. Lệnh biên dịch và chạy

Yêu cầu JDK **17 trở lên**; trên môi trường thử nghiệm đã biên dịch bằng `--release 17`:

```bash
javac --release 17 -encoding UTF-8 HttpResponseOrderDemo.java
java HttpResponseOrderDemo
```

Không cần Maven, Gradle, Spring hoặc thư viện bên thứ ba; chỉ dùng `jdk.httpserver` và `java.net.http`. Chương trình tự mở cổng ngẫu nhiên trên loopback, chạy client tests và dừng server; không yêu cầu mở port public.

### 10.3. Stdout chính xác đã kiểm chứng

```text
fixedStatus=200
fixedBody=Xin chào 🌏
fixedByteLength=14
streamStatus=200
streamChunked=true
streamBody=A|B|
createdStatus=201
createdLocation=/created/7
createdBody={"id":7}
emptyStatus=204
emptyBodyEmpty=true
headStatus=200
headContentLength=14
headBodyEmpty=true
methodStatus=405
methodAllow=GET, HEAD
missingStatus=404
missingBody=Không tìm thấy
```

**Đã biên dịch bằng `javac --release 17` và chạy kiểm chứng trên OpenJDK 24.** Stdout là 18 dòng như trên. Thời gian, cổng TCP ngẫu nhiên và HTTP header tự động như `Date` không được in nên kết quả không phụ thuộc chúng.

**Ý nghĩa các assertions:**
1. `fixedStatus=200` và `fixedBody=...` chứng minh status, content type và body UTF-8 được đọc đúng.
2. `fixedByteLength=14` chứng minh cần lấy byte[] length, không đếm Java char.
3. `streamChunked=true` xác nhận HTTP/1.1 server trả chunked khi dùng `sendResponseHeaders(200,0)`.
4. `createdStatus=201`, `createdLocation=/created/7`, `createdBody={"id":7}` chứng minh server gửi metadata của resource mới trước JSON bytes.
5. `emptyStatus=204` và `emptyBodyEmpty=true` xác minh no-body response.
6. `headStatus=200`, `headContentLength=14`, `headBodyEmpty=true` xác minh HEAD giữ metadata về GET nhưng không gửi content.
7. `methodStatus=405`, `methodAllow=GET, HEAD` xác minh method failure có Allow.
8. `missingStatus=404` và `missingBody=Không tìm thấy` xác minh negative response chứa UTF-8 text hợp lệ.

**Giới hạn của demo:** đây là HTTP server cho học tập, không có user authentication, TLS, request-body quota, session management, logging/metrics production hoặc persistence. Nó xử lý requests không có body và tạo resource giả định. Để expose trên mạng, cần cơ chế vận hành/gateway đầy đủ, request limits và xác thực phù hợp.

## 11. Kiểm thử qua curl và công cụ HTTP

Chương trình ở mục 10 tự mở port ngẫu nhiên rồi đóng, vì vậy **không thể chạy curl thủ công vào port đó sau khi chương trình đã kết thúc**. Nếu muốn xem response trên curl, tạo server riêng chạy lâu hơn/giữ process và bind localhost tại port cố định được cấp. Các lệnh dưới đây là **mẫu** khi một server tương ứng đang chạy tại `http://127.0.0.1:8080`, không phải output đã thực thi của demo:

```bash
curl -i http://127.0.0.1:8080/fixed
curl -i http://127.0.0.1:8080/stream
curl -i -X POST http://127.0.0.1:8080/created
curl -i http://127.0.0.1:8080/empty
curl -I http://127.0.0.1:8080/fixed
curl -i -X PUT http://127.0.0.1:8080/fixed
curl -i http://127.0.0.1:8080/missing
```

`curl -i` hiển thị response headers cùng body, còn `curl -I` gửi HEAD và chỉ yêu cầu headers. `-X POST` đặt method POST; với API thực tế có body, dùng `--data` và Content-Type phù hợp. Để xem framing mà không decode, dùng công cụ packet capture trên môi trường test đã được phép, không dựa vào output của `HttpClient.BodyHandlers.ofString` vì nó đã xử lý transfer encoding.

### 11.1. Test matrix tối thiểu

| Trường hợp | Assert quan trọng |
| --- | --- |
| GET fixed UTF-8 | Status 200, Content-Type đúng, body Unicode đúng, fixed byte length. |
| GET chunked | Status 200, Transfer-Encoding chunked ở HTTP/1.1, body hoàn chỉnh khi close. |
| POST Created | Status 201, Location đúng, Content-Type JSON, body đúng. |
| GET No Content | Status 204 và body rỗng. |
| HEAD | Status/headers phù hợp GET, không body, Content-Length metadata nếu biết. |
| Unsupported method | Status 405, Allow liệt kê methods hợp lệ. |
| Unknown route | Status 404 và error representation nhất quán. |
| Fixed-length body thiếu bytes | Exchange báo lỗi/abort, không treo indefinitely; kiểm tra trong fault-injection test. |
| Fixed-length body thừa bytes | Write gây lỗi và connection bị abort theo contract. |
| sendResponseHeaders hai lần | IOException/vi phạm contract; handler không cố gửi 500 mới sau 200. |
| Header sửa sau commit | Client không nhận headers được thêm trễ. |
| Empty body 200 | Kiểm tra lựa chọn -1 vs 0 có framing/headers đúng như thiết kế. |
| Request body quá dài | 413 và dọn nguồn, không dùng readAllBytes vô hạn. |
| Client disconnect | IOException được dọn/log, không leak threads. |
| Input malformed | 400 trước commit, không 200 với error JSON trá hình. |
| Multiple requests | Exchange của mỗi request đóng, executor ổn định, keep-alive hoạt động nếu hợp lệ. |
| Concurrent requests | Không chia sẻ HttpExchange, tránh race condition response state. |
| Retry/idempotency | POST không tự double-create chỉ vì client retry; cần idempotency keys nếu nghiệp vụ đòi hỏi. |

Đây là **test plan**, không nói đã thực thi tất cả failure injections. Những trường hợp fixed/chunked/201/204/HEAD/405/404 được chương trình kiểm thử tự động trong mục 10.

## 12. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Gọi `getResponseBody()` trước `sendResponseHeaders`. | Vi phạm thứ tự HttpExchange. | Gửi status/headers trước, rồi mới lấy stream. |
| Chỉnh `Content-Type` sau `sendResponseHeaders`. | Header client thấy có thể không đổi. | Đặt toàn bộ headers trước commit. |
| Gọi `sendResponseHeaders` hai lần. | IOException, không thể đổi status đã gửi. | Một exchange chỉ commit phản hồi một lần. |
| Truyền `text.length()` làm fixed byte length. | Sai khi UTF-8 có tiếng Việt/emoji, có thể abort connection. | Dùng `text.getBytes(UTF_8).length`. |
| Gửi `sendResponseHeaders(200,0)` và tưởng body rỗng. | JDK chọn chunked mode. | Không body dùng -1; 0 chỉ khi muốn chunked. |
| Gửi N bytes khai báo nhưng thực tế ghi N-1. | Close stream IOException, response bị abort. | Precompute bytes hoặc streaming 0. |
| Tự đặt Content-Length mâu thuẫn với responseLength. | Mismatch/framing lỗi. | Với fixed body thường để API quyết định header. |
| Quên `OutputStream.close()`. | Client có thể chờ chunk kết thúc, leak resource. | Try-with-resources cho output và close exchange. |
| Gửi body cho 204/304/HEAD. | Sai HTTP semantics. | Sử dụng -1 và không write. |
| HEAD truyền fixed length >0 mà không ghi body. | Không đúng contract, warning/abort tùy implementation. | Đặt Content-Length metadata và send -1. |
| Return 405 mà quên Allow. | Phản hồi thiếu thông tin method hỗ trợ. | `headers.set("Allow", "...")` trước 405. |
| Gửi 201 Location sau khi đã gửi body. | Client không nhận Location. | Set Location trước sendResponseHeaders. |
| Chỉ log stack trace sau khi 200 đã commit. | Không thu hồi được partial success signal. | Protocol streaming có error semantics, close/log và giám sát. |
| Dùng `HttpServer.createContext("/api")` như exact-match router. | `/apiSomething` có thể match sai. | Xác thực path/URI, dùng routing rõ. |
| Đọc request input bằng `readAllBytes()` không giới hạn. | DoS, heap exhaustion. | Bounded reading, timeout và quotas. |
| Dùng `HttpClient` trong try-with-resources khi compile Java 17. | Compile fail vì HttpClient chưa AutoCloseable ở API Java17. | Dùng compatible lifecycle, kiểm tra API theo target JDK. |
| Chạy bind `0.0.0.0` cho demo. | Mở endpoint trên mạng ngoài ý muốn. | Bind `127.0.0.1` trong test. |
| Quên stop server/shutdown executor. | Process/threads giữ lại. | Shutdown trong finally/managed lifecycle. |
| Tin “server trong JDK” tự bảo vệ public traffic. | Thiếu TLS, authentication, quotas và metrics. | Dùng gateway/framework phù hợp deployment. |

## 13. Trường hợp nâng cao

### 13.1. Streaming file lớn

Nếu body là một file lớn đã biết kích thước `N`:
- Kiểm tra file hiện tại, quyền truy cập và kích thước.
- Nếu dùng fixed-length `N>0`, phải bảo đảm ghi **đúng N bytes**; nếu file đổi trong lúc truyền, dễ vi phạm contract.
- Nếu không chắc độ dài hoặc tạo dữ liệu theo luồng, cân nhắc `sendResponseHeaders(200,0)` và ghi chunks có bounded memory.
- Với file zero bytes, chọn no-body semantics hoặc content framing đúng policy.
- Kiểm soát path traversal, MIME type, download filename và header value injection.
- Đóng file input/output trên mọi đường lỗi và xử lý client disconnect.

**Không giải quyết file streaming bằng cách đọc toàn file vào RAM chỉ để tính `Content-Length`** nếu file rất lớn. Dùng file size từ nguồn đáng tin/stable hoặc chunked transfer, đồng thời quản lý file lifetime.

### 13.2. Streaming JSON/NDJSON

Với một danh sách records rất lớn:
- Chuẩn bị `Content-Type` phù hợp (`application/x-ndjson` nếu hợp đồng dùng NDJSON).
- Gọi `sendResponseHeaders(200,0)`.
- Ghi từng record dạng JSON hoàn chỉnh và ký tự newline.
- Không giữ toàn bộ records trong List.
- Đảm bảo mỗi line JSON encode UTF-8 đúng, không tự nối raw input không escape.
- Nếu lỗi giữa stream, client có thể đã thấy một số records; cần contract về **partial result**, transaction/idempotency và cách client phân biệt stream hoàn tất (ví dụ end sentinel ứng dụng) nếu yêu cầu.
- Không đòi đổi status giữa chừng sau khi gửi record đầu tiên.

**Chunked transfer encoding là cơ chế HTTP framing**, còn newline của NDJSON là application framing; hai lớp hoàn toàn khác nhau.

### 13.3. Compression và Content-Encoding

Nếu body được nén:
- `Content-Encoding: gzip` chỉ đúng khi **bytes thực sự đã gzip**.
- `Content-Length` (nếu dùng fixed) phải đo **bytes sau nén**.
- Nếu gzip được tạo on-the-fly và chưa biết tổng bytes, có thể dùng chunked mode cho HTTP/1.1, đóng `GZIPOutputStream` để ghi trailer trước khi kết thúc body.
- `Vary: Accept-Encoding` cần phù hợp nếu server chọn nội dung nén theo request headers.
- Không double-compress hoặc gửi `Content-Length` của plaintext cho compressed bytes.

Đây là thiết kế mở rộng; chương trình runnable không nén body để giữ trọng tâm thứ tự response.

### 13.4. Conditional GET / ETag

Trước commit:
1. Kiểm tra `If-None-Match`/`If-Modified-Since` và cache policy.
2. Nếu representation chưa đổi, trả `304` với validators phù hợp và **không body**.
3. Nếu dữ liệu đã đổi, gửi `200` kèm `ETag`/`Content-Type` và body.
4. Đảm bảo `ETag` được tính trên representation theo contract của application (nếu nội dung phụ thuộc compression, language và parameters, cần xử lý Vary đúng).
5. Không coi `304` là 200 với JSON `null`.

### 13.5. Custom headers, Content-Disposition và redirects

Khi người dùng cung cấp filename/redirect target:
- Không đưa trực tiếp CR/LF vào headers.
- Với `Content-Disposition`, encode/escape filename theo HTTP header syntax (đặc biệt UTF-8/non-ASCII) và có allowlist.
- Với `Location`, tránh arbitrary open redirect hoặc URLs chứa credentials.
- Nếu nhiều headers có cùng tên, dùng `Headers.add` chỉ khi header semantics cho phép.
- Đặt security/cache headers trước commit, không chỉnh late.

### 13.6. HTTP client bên ngoài và reverse proxy

Server có thể nằm sau reverse proxy:
- Proxy có thể buffer/chunk/recompress body hoặc chuyển HTTP/1.1 ↔ HTTP/2.
- Client có thể nhận Transfer-Encoding khác nội bộ dù application stream đúng.
- Không dùng chunk boundaries làm business records.
- Response code/headers có thể bị gateway áp policy; integration test phải chạy cả đường proxy thật.
- Nếu proxy xử lý TLS, xác thực forwarded headers đúng trust boundary; đừng tin `X-Forwarded-*` từ client bất kỳ.

## 14. Hỏi đáp ôn tập

**Câu 1. Thứ tự ba bước cốt lõi của HttpExchange là gì?**

**Đáp án:** `getResponseHeaders().set(...)` → `sendResponseHeaders(status,length)` → `getResponseBody()` và `write(...)`; sau đó đóng output/exchange.

**Câu 2. Có thể gửi body rồi mới quyết định status không?**

**Đáp án:** Không. `getResponseBody()` yêu cầu đã gọi `sendResponseHeaders`. Status/headers phải được quyết định trước khi ghi body.

**Câu 3. `sendResponseHeaders(200,0)` có nghĩa Content-Length 0 không?**

**Đáp án:** Không. Với `HttpExchange` nó chọn chunked transfer encoding cho HTTP/1.1. Không body thì dùng `-1`.

**Câu 4. Nếu body UTF-8 chứa emoji thì dùng String.length() cho responseLength được không?**

**Đáp án:** Không. `responseLength` là số bytes. Dùng `byte[] payload = text.getBytes(StandardCharsets.UTF_8)` rồi `payload.length`. Ví dụ `"Xin chào 🌏"` có 14 UTF-8 bytes.

**Câu 5. Điều gì xảy ra nếu khai body 20 bytes nhưng chỉ ghi 14 bytes?**

**Đáp án:** Theo Javadoc fixed-length output, khi đóng stream có thể ném `IOException`, exchange bị abort và TCP connection đóng.

**Câu 6. Có thể đổi Content-Type sau khi sendResponseHeaders không?**

**Đáp án:** Không thể tin nó sẽ được gửi; headers đã commit. Đặt Content-Type trước khi gửi.

**Câu 7. HEAD nên gửi body không?**

**Đáp án:** Không. Có thể gửi Content-Length metadata tương ứng representation của GET, nhưng dùng `sendResponseHeaders(200,-1)` và không ghi body.

**Câu 8. 204 và 304 có gửi body không?**

**Đáp án:** Không. Dùng no-body mode; 304 dùng cùng cache validators phù hợp conditional request.

**Câu 9. Gửi 405 có cần header gì?**

**Đáp án:** `Allow` liệt kê methods được hỗ trợ cho target resource, đặt trước `sendResponseHeaders(405, ...)`.

**Câu 10. Vì sao cần đóng OutputStream sau chunked?**

**Đáp án:** Đóng stream kết thúc response body, nếu không client có thể chờ data tiếp và resources chưa được giải phóng.

**Câu 11. Một Java HttpServer handler có cần tự tạo TCP protocol headers thô không?**

**Đáp án:** Không. API quản lý status line, HTTP headers, Content-Length/chunk framing. App cung cấp status/headers/bytes qua đúng methods, không ghi raw `HTTP/1.1 200 OK` vào body.

**Câu 12. `Headers.set` và `Headers.add` khác gì?**

**Đáp án:** `set` thay tất cả values cùng tên bằng một value, `add` thêm một value. Header semantics quyết định cách dùng.

**Câu 13. Khi stream đã commit 200 và backend phát sinh IOException, có thể gửi lại 500 không?**

**Đáp án:** Không. Không thể thu hồi status/headers đã gửi. Cần close/abort, log/monitor và định nghĩa streaming error contract nếu cần.

**Câu 14. `HttpExchange.close()` có hợp lệ trong try-with-resources trên Java 17 không?**

**Đáp án:** Có. `HttpExchange` implements AutoCloseable từ API JDK17. Đóng exchange sẽ đóng request input và response output.

**Câu 15. `HttpClient` Java17 có thể dùng try-with-resources giống HttpExchange không?**

**Đáp án:** Không ở API Java17: `HttpClient` chưa implements AutoCloseable theo target đó; tránh viết `try (HttpClient client = ...)` khi compile `--release 17`. Trên các JDK mới hơn có lifecycle API riêng.

**Câu 16. `createContext("/foo",handler)` chỉ match đúng `/foo` không?**

**Đáp án:** Không chắc. `HttpServer` dùng prefix matching, `/foobar` có thể được match. Xác nhận/giới hạn path trong handler.

**Câu 17. Cần test gì để tin response 201 đúng?**

**Đáp án:** Status 201, `Location` chính xác theo resource thật, Content-Type và body nếu có, đồng thời side effect nghiệp vụ tương ứng; demo chỉ dùng 201 tĩnh.

**Câu 18. Tại sao server học tập không nên bind `0.0.0.0`?**

**Đáp án:** Nó có thể lắng nghe từ interfaces bên ngoài, mở endpoint không có authentication/TLS/limits. Loopback 127.0.0.1 phù hợp test tại máy.

## 15. Checklist triển khai đúng thứ tự

1. Kiểm tra HTTP method/URI, request headers và body có giới hạn, validate/authenticate trước commit.
2. Quyết định status code từ kết quả nghiệp vụ trước khi gửi.
3. Chuẩn bị `Content-Type`, cache/redirect/Allow và security headers thích hợp trong `getResponseHeaders()`.
4. Nếu body cố định, chuyển text sang bytes với charset xác định, dùng `byte[].length`.
5. Gọi **một lần** `sendResponseHeaders(status,length)` trước `getResponseBody()`.
6. Dùng `length>0` cho fixed N bytes; `length=0` cho chunked streaming; `length=-1` khi không gửi body.
7. Không tự đặt Content-Length mâu thuẫn với API; chỉ dùng metadata Content-Length ở những trường hợp được HTTP semantics cho phép như HEAD.
8. Không gửi body cho HEAD, 204, 304, 205 và các trường hợp status/method no-body khác.
9. Ghi đúng N bytes fixed-length hoặc đóng output để kết thúc chunked.
10. Đóng `OutputStream` và `HttpExchange` trong finally/try-with-resources; xử lý request input đúng vòng đời.
11. Nếu lỗi trước commit, chọn error status/payload phù hợp; nếu lỗi sau commit, không gửi status/headers lần hai.
12. Không log secrets/raw request body và không phản chiếu untrusted header values.
13. Hạn chế body bytes, thời gian, concurrency và queue; không dùng readAllBytes vô hạn cho input từ client.
14. Kiểm tra `HttpContext` prefix routing, tránh tạo đường dẫn nhạy cảm match ngoài ý muốn.
15. Với public traffic, cấu hình TLS, authn/authz, rate limiting, metrics, graceful shutdown và gateway protection.
16. Test GET fixed/chunked, 201, 204, HEAD, 405, 404, UTF-8 byte length và error cases.
17. Với proxy hoặc HTTP/2, test framing/headers ở end-to-end path thật; không coi chunk boundaries là records.
18. Dùng Java 17+ `jdk.httpserver` và `java.net.http` APIs hiện hành, không sử dụng HTTP parser/response-writing legacy.

## 16. Nguồn chính thức và chuẩn

- [Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): thứ tự request/response, `sendResponseHeaders`, fixed/chunked/no-body, đóng exchange, lỗi byte count.
- [Java SE 25 — HttpExchange](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): xác nhận contract phản hồi còn áp dụng trên JDK mới.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): tạo server, contexts/prefix match, executor, start/stop.
- [Java SE 17 — HttpHandler](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): xử lý một HttpExchange.
- [Java SE 17 — Headers](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): `set`, `add`, `getFirst` và tên header case-insensitive.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client integration tests trên Java 17.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): đọc status, response headers, body.
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): `UTF_8` để xác định bytes.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): phương thức HEAD, status 201/204/304/405, Allow/Location/Content-Length semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html): message framing, Content-Length và chunked transfer encoding.
