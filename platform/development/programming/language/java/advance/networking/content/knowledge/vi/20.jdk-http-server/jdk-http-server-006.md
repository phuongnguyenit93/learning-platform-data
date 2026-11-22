# Gửi mã trạng thái, header, độ dài và response body

*Java Advance – networking · Nhóm: HTTP server của JDK · Java 17+*

## 1. Bốn thành phần của một HTTP response

Với HTTP server có sẵn trong JDK (`com.sun.net.httpserver.HttpServer`), người viết handler phải quyết định **trả mã trạng thái nào, đặt các header gì, body dài bao nhiêu byte và ghi body theo cách nào**. Bốn việc này liên quan chặt chẽ nhưng không thể thay thế cho nhau:

1. **Status code** (`200`, `201`, `204`, `302`, `404`, `500`…) thông báo kết quả xử lý theo semantics HTTP.
2. **Response headers** (`Content-Type`, `Cache-Control`, `Location`, `ETag`, các custom headers…) cung cấp metadata và hướng dẫn client.
3. **Response body length** trong `sendResponseHeaders(status, responseLength)` điều khiển **cách server gửi và đóng khung body**: fixed-length, chunked hay không có body.
4. **Response body** được ghi tới `OutputStream` từ `exchange.getResponseBody()`; ghi đủ, đóng stream và giải phóng exchange là trách nhiệm của handler.

**Lưu ý quan trọng nhất của Java 17 `HttpExchange`:** tham số `responseLength = 0` **không có nghĩa “body rỗng”**. Nó yêu cầu **chunked transfer encoding**, tức body có độ dài không xác định trước. Muốn trả response **không có body**, dùng `responseLength = -1`.

~~~text
Client                        JDK HttpServer / HttpExchange
  |                                     |
  | ---- HTTP request ----------------> |  getRequestMethod(), getRequestURI()
  |                                     |  getRequestHeaders(), getRequestBody()
  |                                     |
  |                           Xử lý nghiệp vụ / chọn status
  |                                     |
  |                          getResponseHeaders().set/add(...)
  |                                     |
  |                          sendResponseHeaders(status, length)
  | <--- status line + headers -------- |
  |                                     |
  |                             getResponseBody()
  | <--- body bytes (nếu có) ----------- |  OutputStream.write(...)
  |                                     |
  |                    OutputStream.close() / exchange.close()
  | <--- body kết thúc theo framing ---- |
~~~

Trong handler, **phải đặt header trước khi gửi status/headers**, và **gọi `sendResponseHeaders` trước `getResponseBody`**. Sau khi response headers đã phát đi, không có cách an toàn để đổi status từ `200` thành `500` cho cùng response.

## 2. Các lớp cần biết trong module jdk.httpserver

| Lớp / API | Vai trò |
|---|---|
| `HttpServer` | Tạo HTTP server lắng nghe một địa chỉ/cổng; đăng ký context/handler |
| `HttpHandler` | Nhận một `HttpExchange` và viết response cho request đó |
| `HttpExchange` | Chứa request metadata, request body, response headers, status/body output |
| `Headers` | Multimap tên header sang danh sách giá trị; dùng `set` hoặc `add` |
| `getResponseHeaders()` | Lấy headers **sắp được gửi** tới client để bổ sung trước commit |
| `sendResponseHeaders(int,long)` | Gửi status + response headers và chọn framing body |
| `getResponseBody()` | OutputStream để ghi body; cần close khi hoàn tất |
| `close()` | Kết thúc exchange/đóng request và response streams theo contract |
| `HttpsServer` | Biến thể HTTPS của lightweight server, cần cấu hình TLS riêng |

Đối với source dùng trong ví dụ:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.Headers;
~~~

Module trong JDK là **`jdk.httpserver`**, khác với các thư viện web framework. Đây là server nhỏ, hữu ích cho ví dụ, kiểm thử nội bộ hoặc service HTTP đơn giản; **không tự mang đầy đủ features của một production framework** (routing cao cấp, authentication, security filters, observability, request quotas…). Các lớp `com.sun.net.httpserver` là API được xuất bởi module `jdk.httpserver`, không nên nhầm với các package `sun.*` nội bộ.

## 3. Trình tự đúng trong một HttpHandler

Quy trình cơ bản:

~~~text
handle(HttpExchange exchange)
          |
          v
Đọc method, URI, request headers/body (nếu cần)
          |
          v
Xử lý logic và chọn status/representation
          |
          v
exchange.getResponseHeaders().set(...)
          |
          v
exchange.sendResponseHeaders(status, responseLength)
          |
          v
try (OutputStream out = exchange.getResponseBody()) {
    out.write(payload);
}
          |
          v
OutputStream được đóng -> exchange kết thúc
~~~

**Không đảo thứ tự** giữa gửi headers và viết body. `HttpExchange.sendResponseHeaders(...)` có thể ném `IOException` nếu headers đã được gửi hoặc có lỗi I/O; `getResponseBody()` theo Javadoc phải được gọi **sau** `sendResponseHeaders(...)`.

### 3.1. Skeleton handler cố định độ dài

~~~java
// Đây là trích đoạn dùng bên trong HttpHandler.
byte[] payload = "Hello".getBytes(StandardCharsets.UTF_8);

exchange.getResponseHeaders()
        .set("Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(200, payload.length);

try (OutputStream output = exchange.getResponseBody()) {
    output.write(payload);
}
~~~

Ý nghĩa:

- Chọn `200 OK`.
- Đặt `Content-Type` trước khi commit.
- Đặt length bằng **số byte thực sự** sẽ ghi.
- Dùng try-with-resources đảm bảo đóng output stream cả khi xử lý có lỗi; đây là bước giúp hoàn tất HTTP exchange.

Các import `StandardCharsets` và `OutputStream` cần có ở chương trình hoàn chỉnh. **Không coi đoạn trích này là file Java có thể chạy độc lập**; ví dụ đầy đủ ở phần dưới.

### 3.2. Không gửi status code lần thứ hai

`sendResponseHeaders(...)` chỉ thuộc **một lần phản hồi** của một `HttpExchange`. Nếu đã gọi và đang ghi body mà gặp lỗi, không thể làm:

~~~java
// Sai về lifecycle: response headers đã gửi rồi.
// exchange.sendResponseHeaders(200, ...);
// write(...) ném IOException ...
exchange.sendResponseHeaders(500, -1); // Không thể gửi một status line mới.
~~~

Khi lỗi xảy ra **trước khi commit**, handler có thể quyết định trả response lỗi đúng cấu trúc. Khi lỗi xảy ra **sau commit**, hãy log và đóng/huỷ exchange; client có thể thấy body bị cắt ngắn hoặc connection lỗi. Việc client đã thấy 200 không đảm bảo server gửi xong toàn body.

## 4. Chọn mã trạng thái HTTP đúng semantics

`sendResponseHeaders(rCode, responseLength)` nhận **mã số nguyên**. Không cần tự viết `HTTP/1.1 200 OK` vào response body: JDK server gửi HTTP status line/headers theo protocol. Chọn mã dựa trên kết quả xử lý, không dựa trên việc “body có nội dung”.

| Status | Ý nghĩa điển hình | Có thể trả body? |
|---|---|---|
| **200 OK** | GET/operation thành công | Có, tùy method/representation |
| **201 Created** | Tài nguyên mới được tạo | Có thể có body; cân nhắc `Location` |
| **202 Accepted** | Request được chấp nhận xử lý bất đồng bộ | Có thể có mô tả/trạng thái; **không** tự có nghĩa xử lý xong |
| **204 No Content** | Thành công nhưng không có response content | **Không có body** |
| **301/302** | Redirect thường trú/tạm thời | Thường có `Location`; follow là quyết định client |
| **303 See Other** | Xem tài nguyên/result qua URI khác | Có thể có metadata; có `Location` |
| **304 Not Modified** | Conditional cache | **Không có response content** |
| **400 Bad Request** | Request sai cấu trúc/validation | Có thể trả error JSON |
| **401 Unauthorized** | Cần xác thực hợp lệ | Có thể trả error body và `WWW-Authenticate` khi phù hợp |
| **403 Forbidden** | Không được phép thực hiện | Có thể trả error body, không làm lộ tài nguyên |
| **404 Not Found** | Không thấy tài nguyên | Có thể trả JSON/HTML giải thích ngắn |
| **405 Method Not Allowed** | Method không hỗ trợ cho resource | Cần `Allow` nêu các method hỗ trợ |
| **409 Conflict** | Mâu thuẫn trạng thái resource | Có thể có error JSON |
| **422 Unprocessable Content** | Body có cấu trúc hợp lệ nhưng không xử lý theo semantics | Có thể có validation details đã lọc |
| **429 Too Many Requests** | Rate limit | Có thể có `Retry-After` |
| **500 Internal Server Error** | Lỗi server không mong đợi | Có thể có error body chung, **không** lộ stack trace |
| **503 Service Unavailable** | Tạm quá tải/bảo trì | Có thể có `Retry-After` |

**Không nhầm HTTP status với Java exception.** Một handler có thể hoàn thành I/O về mặt kỹ thuật nhưng phải trả `404` vì tài nguyên không tồn tại. Trả `200` với body `{"error":"missing"}` chỉ để “không lỗi trên client” thường gây hiểu lầm cho monitoring, cache, retry policy và API consumers.

### 4.1. Status code và response body là hai quyết định độc lập

~~~text
200 + body JSON              -> thành công, có representation
201 + Location + body JSON   -> tạo resource mới
204 + không body             -> thành công, không có content
302 + Location               -> client có thể điều hướng
404 + error JSON             -> HTTP error có body giải thích
500 + error JSON an toàn     -> HTTP error, không lộ thông tin nội bộ
~~~

Không dùng `-1` làm status code. `-1` là giá trị **độ dài body** trong tham số thứ hai của `sendResponseHeaders` để báo không có body. Status code vẫn phải là mã HTTP hợp lệ như `204` hay `304`.

## 5. Thiết lập response headers đúng cách

`exchange.getResponseHeaders()` trả một `Headers` cho **response**, khác với `exchange.getRequestHeaders()` (request headers của client).

~~~java
Headers h = exchange.getResponseHeaders();
h.set("Content-Type", "application/json; charset=UTF-8");
h.set("Cache-Control", "no-store");
h.set("X-Request-Id", "demo-1");

// Với header thực sự có thể lặp nhiều lần, dùng add:
h.add("Set-Cookie", "session=abc; HttpOnly; Secure; SameSite=Lax");
h.add("Set-Cookie", "theme=dark; Secure; SameSite=Lax");
~~~

Đây là **trích đoạn**, cookie string chỉ minh họa; demo HTTP loopback phía dưới không đặt cookie thực hoặc làm flow đăng nhập. Không hardcode session ID như `abc` trong sản phẩm. `Secure` chỉ có ý nghĩa đúng khi dùng HTTPS theo quy tắc client.

### 5.1. set khác add

| API | Hành vi |
|---|---|
| `headers.set(name, value)` | Thay danh sách giá trị hiện có của header bằng một giá trị mới |
| `headers.add(name, value)` | Bổ sung một giá trị vào danh sách sẵn có |
| `headers.getFirst(name)` | Đọc giá trị đầu tiên cho header nếu có |
| `headers.get(name)` | Đọc danh sách giá trị cho tên header |
| `headers.remove(name)` | Loại bỏ header khỏi tập chuẩn bị gửi |

Tên header HTTP **không phân biệt chữ hoa/thường** theo protocol. Với một số headers có thể lặp như `Set-Cookie`, cần bảo toàn từng field/value phù hợp; không mặc định dùng dấu phẩy để gộp mọi header lại.

**Tất cả header cần được thiết lập trước `sendResponseHeaders`.** Sau khi headers đã gửi, sửa `Headers` không làm status/header cũ thay đổi trên wire.

### 5.2. Những headers thường quan trọng

| Header | Vai trò | Lưu ý |
|---|---|---|
| `Content-Type` | Loại representation và charset | `application/json; charset=UTF-8`, `text/plain; charset=UTF-8` |
| `Content-Length` | Số byte body theo framing phù hợp | Với fixed-length thường để `sendResponseHeaders` tự đặt |
| `Transfer-Encoding` | Cách mã hóa/framing đường truyền, ví dụ `chunked` | Với JDK HttpServer để `responseLength=0` điều khiển, không tự set mâu thuẫn |
| `Cache-Control` | Quy tắc cache client/proxy | `no-store` thích hợp cho dữ liệu nhạy cảm |
| `Location` | Địa chỉ resource mới/redirect | Dùng với 201 hoặc redirect theo semantics |
| `ETag` / `Last-Modified` | Metadata cho conditional requests | `304` có quy tắc riêng |
| `Retry-After` | Hướng dẫn retry khi thích hợp | Không thay thế retry policy phía client |
| `Allow` | Methods hỗ trợ cho resource | Quan trọng với `405 Method Not Allowed` |
| `Vary` | Chỉ các request header ảnh hưởng chọn representation | Tránh cache sai biến thể |
| `Content-Disposition` | Cách trình bày/tải file | Cẩn thận tên file do user cung cấp |
| `X-Content-Type-Options: nosniff` | Hạn chế MIME sniffing của browser theo ngữ cảnh | Không thay thế xác thực/phân quyền |
| `Access-Control-Allow-Origin` | Chính sách browser CORS theo origin được phép | CORS không phải server authentication |

### 5.3. Không đưa dữ liệu không tin cậy trực tiếp vào headers

Tên và giá trị header cần tuân thủ cú pháp HTTP. Nếu lấy `Location`, filename hay custom header từ input người dùng, **validate và encode theo ngữ cảnh**. Đừng cho input chứa CR/LF tạo HTTP response splitting hoặc lỗi protocol. Không chèn exception message, token, password, session cookie hay stack trace vào headers.

**CORS không phải cơ chế xác thực**: server vẫn phải kiểm tra credentials và quyền. Với `Access-Control-Allow-Origin`, chọn policy origin hợp lệ; không phản chiếu tất cả giá trị Origin mù quáng, nhất là khi dùng credentials.

## 6. sendResponseHeaders(int status, long responseLength): ba chế độ

Đây là trọng tâm của bài. Java 17 Javadoc quy định:

| responseLength | Cách server gửi body | Nghĩa của handler |
|---|---|---|
| **`> 0`** | **Fixed-length** | Phải ghi **đúng bằng** số byte khai báo; thừa/thiếu đều lỗi |
| **`0`** | **Chunked transfer encoding** trên HTTP/1.1 | Không biết trước length; có thể ghi lượng byte tùy ý, **phải close output stream để kết thúc** |
| **`-1`** (hoặc âm khác theo Javadoc parameters) | **Không gửi response body** | Không ghi body; kết thúc exchange, phù hợp HEAD/204/304… |

**`0` không phải body rỗng.** Nếu một `byte[]` có độ dài `0` và bạn gọi `sendResponseHeaders(200, bytes.length)`, Java 17 sẽ chọn **chunked** thay vì “no body”; nó vẫn có thể truyền một chunked body rỗng về mặt dữ liệu, nhưng framing khác với response không có body.

### 6.1. Khi chọn fixed-length

~~~java
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders()
        .set("Content-Type", "application/json; charset=UTF-8");
exchange.sendResponseHeaders(200, bytes.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(bytes); // Chính xác bytes.length byte.
}
~~~

`bytes.length` là số byte, **không phải `json.length()`**. Khi dùng UTF-8, ký tự có dấu/emoji có số byte khác số Java UTF-16 code units. Ví dụ:

~~~text
Text:                  Xin chào
Java String.length():  8
UTF-8 byte[].length:   9
~~~

Nếu gọi `sendResponseHeaders(200, 8)` nhưng ghi cả 9 byte UTF-8, `OutputStream.write` có thể ném `IOException` do **ghi nhiều hơn số byte khai báo**. Nếu khai báo 10 mà chỉ ghi 9, `OutputStream.close` có thể ném `IOException` do **ghi thiếu byte**. Theo Javadoc, trong cả hai trường hợp exchange bị abort và underlying TCP connection bị đóng.

### 6.2. Những điều fixed-length đảm bảo và không đảm bảo

Fixed-length giúp server/client có framing rõ ràng và phát hiện sai lệch lượng byte. Tuy nhiên:

- Không tự chứng minh bytes là JSON hợp lệ hoặc nội dung đã được client parse.
- Không chứng minh client đã nhận/xử lý thành công nếu connection rơi sau khi server viết.
- Nếu có compression như gzip, cần tính **số byte representation sau khi nén**, không dùng length của text gốc.
- Nếu body rỗng, cân nhắc **`-1`** thay vì truyền `0` với suy nghĩ đây là Content-Length 0.
- Tránh tự đặt `Content-Length` mâu thuẫn với tham số `responseLength`. Để server implementer chọn header/framing dựa trên API, trừ các trường hợp đặc biệt như HEAD cần metadata.

## 7. Chunked: responseLength = 0

Khi chưa biết tổng số byte hoặc muốn xuất dữ liệu incremental, có thể gọi:

~~~java
exchange.getResponseHeaders()
        .set("Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(200, 0); // 0 nghĩa chunked!

try (OutputStream out = exchange.getResponseBody()) {
    out.write("alpha-".getBytes(StandardCharsets.UTF_8));
    out.write("beta".getBytes(StandardCharsets.UTF_8));
}
~~~

Trong HTTP/1.1, JDK server sử dụng `Transfer-Encoding: chunked` cho trường hợp này; client nhận body nội dung `alpha-beta` mà không cần có `Content-Length` cố định. **Đóng output stream** là thao tác kết thúc chunked response. Nếu không đóng, client có thể đợi mãi chunk cuối / EOF logic.

### 7.1. Chunked không có nghĩa mỗi write thành một chunk wire

Hai lời gọi `out.write(...)` trong Java không bắt buộc tương ứng **đúng hai chunks HTTP** trên wire. Buffering, `flush`, networking và implementation có thể chia/gộp dữ liệu. Application protocol không được dùng ranh giới `write` của server làm ranh giới message bên client. Nếu cần nhiều record, hãy dùng JSON Lines/SSE/protocol framing rõ ràng.

### 7.2. Flush không phải close

`out.flush()` có thể thúc đẩy dữ liệu đi xuống tầng dưới, nhưng **không đánh dấu response đã hoàn tất**. Chunked body thường kết thúc khi đóng stream (server phát chunk terminator phù hợp). Với client streaming, việc đã đọc được vài byte không có nghĩa response đã hết.

**Không manually gắn `Transfer-Encoding: chunked` rồi vẫn gọi `sendResponseHeaders(status, fixedLength)`.** Hai cơ chế framing cạnh tranh gây hành vi không được bảo đảm hoặc response malformed; hãy để API quản lý.

### 7.3. HTTP/1.0 và framing không biết trước

Khái niệm `chunked` là của HTTP/1.1. Các HTTP protocol/version khác không nhất thiết dùng cùng wire framing; đừng xây ứng dụng dựa trên việc `Transfer-Encoding` luôn đúng trên mọi client/proxy. Bài kiểm thử bên dưới sử dụng `HttpURLConnection` với HTTP/1.1 để quan sát `Transfer-Encoding: chunked`, nhưng **dữ liệu nghiệp vụ vẫn là body sau khi HTTP framing được giải mã**.

## 8. Không gửi body: responseLength = -1

Khi response không nên/cần có body:

~~~java
exchange.getResponseHeaders()
        .set("Cache-Control", "no-store");
exchange.sendResponseHeaders(204, -1); // No Content, không gửi body.
exchange.close();
~~~

`-1` biểu thị **no response body**. `exchange.close()` giải phóng exchange, bao gồm các streams liên quan. Javadoc nhấn mạnh kể cả khi không gửi body, response stream/exchange vẫn phải được đóng để hoàn tất. Sử dụng `exchange.close()` là cách đơn giản cho nhánh không ghi body.

Các tình huống điển hình:

| Trường hợp | Body HTTP có được gửi? | Cách thiết lập trong JDK |
|---|---|---|
| `204 No Content` | Không | `sendResponseHeaders(204, -1)` |
| `304 Not Modified` | Không | `sendResponseHeaders(304, -1)` |
| `HEAD` | Không, dù metadata mô tả representation GET | Đặt headers cần thiết rồi `sendResponseHeaders(200, -1)` |
| `205 Reset Content` | Theo RFC không được có content | Dùng no-body và kiểm tra semantics |
| `1xx` informational | Không có response content theo semantics | Không coi 1xx như final body response |
| `200` với nhu cầu không gửi representation | Có thể không có body | `sendResponseHeaders(200, -1)`, nhưng cân nhắc status phù hợp |

**Không cố gắng ghi body sau `sendResponseHeaders(status, -1)`.** Không có response body nào để ghi; hãy đóng exchange.

### 8.1. HEAD: Content-Length biểu thị body của GET tương ứng

Theo HTTP, response cho `HEAD` **không được chứa body**, nhưng có thể chứa `Content-Length` biểu thị **số byte sẽ được gửi nếu request tương ứng là GET** trong những điều kiện tương tự.

~~~java
byte[] wouldBeGetBody = "Xin chào".getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=UTF-8");
exchange.getResponseHeaders().set(
        "Content-Length", String.valueOf(wouldBeGetBody.length));
exchange.sendResponseHeaders(200, -1); // HEAD: không ghi body.
exchange.close();
~~~

Trong demo, `Content-Length: 9` là **metadata GET tương ứng**, không có 9 byte thực sự được gửi trong HEAD response. Đừng gọi `sendResponseHeaders(200, 9)` rồi cố ghi 9 byte trên một HEAD request: trái với semantics HEAD, và implementation có thể cảnh báo.

### 8.2. 204 và 304 không giống nhau

`204 No Content` là response thành công không có nội dung. `304 Not Modified` là phản hồi cho conditional request để client/cache sử dụng lại representation đã lưu; **không phải một tài liệu mới được gửi**. Hai status đều không có body, nhưng metadata/semantics khác nhau. Với `304`, các validator như `ETag` và `Last-Modified` cần nhất quán với tài nguyên khi áp dụng caching.

### 8.3. Vì sao không dùng 0 để nói no-body?

Hãy nhớ **tham số của Java API** chứ đừng suy từ toán học:

~~~text
sendResponseHeaders(200, 9)    -> fixed-length, viết đúng 9 byte
sendResponseHeaders(200, 0)    -> chunked, viết tùy số byte rồi close
sendResponseHeaders(204, -1)   -> không gửi response body
sendResponseHeaders(304, -1)   -> không gửi response body
sendResponseHeaders(200, -1)   -> không gửi response body
~~~

Với các status không cho body như 204/304, JDK có thể điều chỉnh/framing để tuân semantics thay vì dùng chunked kể cả khi bạn truyền 0, nhưng không dựa vào điều chỉnh ngầm ấy. Hãy **chọn -1 rõ ràng** từ handler.

## 9. Response lỗi cũng có body hữu ích

**HTTP error không phải lỗi kết nối bắt buộc.** Nếu resource không tồn tại, handler có thể trả status `404` và body JSON:

~~~java
byte[] error = "{\"error\":\"missing\"}"
        .getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "application/json; charset=UTF-8");
exchange.sendResponseHeaders(404, error.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(error);
}
~~~

Client đọc:

~~~text
HTTP/1.1 404 Not Found
Content-Type: application/json; charset=UTF-8
Content-Length: 19

{"error":"missing"}
~~~

Các header/line kết xuất ở trên minh họa; `HttpServer` có thể thêm header như `Date` và thứ tự/header casing có thể khác. **Client không nên phân nhánh bằng reason phrase** hay dựa vào thứ tự headers.

Phía Java client:

- `java.net.http.HttpClient` với `BodyHandlers.ofString()` thường trả `HttpResponse<String>` có status 404 **và body JSON**; HTTP 4xx không tự thành IOException.
- Legacy `HttpURLConnection` có `getResponseCode()` cho status; `getInputStream()` với 404 có thể ném IOException, còn `getErrorStream()` có thể trả error body và **có thể null** nếu không có error data.

**An toàn:** error JSON nên dùng mã lỗi ổn định và thông tin tối thiểu; không nhúng stack trace, SQL query, session/token, đường dẫn filesystem nhạy cảm hoặc thông tin nội bộ vào response body.

### 9.1. 201 Created với Location

Khi handler tạo tài nguyên thành công, response có thể đặt `Location`:

~~~java
exchange.getResponseHeaders().set("Location", "/items/42");
byte[] body = "{\"id\":42}".getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "application/json; charset=UTF-8");
exchange.sendResponseHeaders(201, body.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(body);
}
~~~

URI trong `Location` có thể relative tùy protocol/use case. Hãy kiểm tra input trước khi xây URI/Location để không tạo open redirect hoặc header injection.

### 9.2. 405 Method Not Allowed với Allow

Nếu endpoint chỉ nhận GET/HEAD nhưng client gửi DELETE:

~~~java
exchange.getResponseHeaders().set("Allow", "GET, HEAD");
exchange.sendResponseHeaders(405, -1);
exchange.close();
~~~

`Allow` là header quan trọng theo HTTP semantics cho 405. **Không nhận một method không được hỗ trợ rồi vẫn trả 200** chỉ vì code handler không kiểm tra method.

## 10. Chương trình Java 17+ hoàn chỉnh: sáu kiểu response

Ví dụ dùng **`HttpServer` trên loopback `127.0.0.1` và cổng động**. Không có request ra Internet, không đòi chứng chỉ TLS hoặc thư viện ngoài JDK.

Các endpoint:

1. **`GET /fixed`:** status 200, `Content-Type` và custom `X-Lesson-Mode`, body UTF-8 `Xin chào` có **9 byte** nhưng Java String có 8 code units; gửi fixed-length.
2. **`GET /chunked`:** status 200, responseLength `0`, body hai lần `write` ghép thành `alpha-beta`; client thấy `Transfer-Encoding: chunked` trên HTTP/1.1.
3. **`GET /empty`:** status 204, responseLength `-1`, không body.
4. **`HEAD /head`:** status 200, set `Content-Length: 9` như GET tương ứng nhưng không gửi body.
5. **`GET /not-modified`:** status 304, không body.
6. **`GET /error`:** status 404, JSON error fixed-length; client đọc qua `HttpURLConnection.getErrorStream()`.

Client kiểm tra status, headers, body và in stdout có thể tái lập. Demo này dùng legacy `HttpURLConnection` chỉ để quan sát wire response; server được viết hoàn toàn bằng JDK `HttpServer`.

Tạo file **`HttpResponseWriteDemo.java`**:

~~~java
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;

public class HttpResponseWriteDemo {
    static final byte[] HELLO = "Xin chào".getBytes(StandardCharsets.UTF_8);

    private static void common(HttpExchange ex, String mode, String contentType) {
        Headers h = ex.getResponseHeaders();
        h.set("Content-Type", contentType);
        h.set("X-Lesson-Mode", mode);
        h.set("Cache-Control", "no-store");
    }

    private static void fixed(HttpExchange ex) throws IOException {
        common(ex, "fixed", "text/plain; charset=UTF-8");
        ex.sendResponseHeaders(200, HELLO.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(HELLO);
        }
    }

    private static void chunked(HttpExchange ex) throws IOException {
        common(ex, "chunked", "text/plain; charset=UTF-8");
        ex.sendResponseHeaders(200, 0);
        try (OutputStream out = ex.getResponseBody()) {
            out.write("alpha-".getBytes(StandardCharsets.UTF_8));
            out.write("beta".getBytes(StandardCharsets.UTF_8));
        }
    }

    private static void empty(HttpExchange ex) throws IOException {
        common(ex, "empty", "text/plain; charset=UTF-8");
        ex.sendResponseHeaders(204, -1);
        ex.close();
    }

    private static void head(HttpExchange ex) throws IOException {
        common(ex, "head", "text/plain; charset=UTF-8");
        ex.getResponseHeaders().set("Content-Length", String.valueOf(HELLO.length));
        ex.sendResponseHeaders(200, -1);
        ex.close();
    }

    private static void notModified(HttpExchange ex) throws IOException {
        common(ex, "not-modified", "text/plain; charset=UTF-8");
        ex.sendResponseHeaders(304, -1);
        ex.close();
    }

    private static void error(HttpExchange ex) throws IOException {
        byte[] payload = "{\"error\":\"missing\"}".getBytes(StandardCharsets.UTF_8);
        common(ex, "error", "application/json; charset=UTF-8");
        ex.sendResponseHeaders(404, payload.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(payload);
        }
    }

    private static void check(URI base, String path, String method)
            throws IOException {
        HttpURLConnection conn = (HttpURLConnection)
                base.resolve(path).toURL().openConnection();
        conn.setConnectTimeout(3000);
        conn.setReadTimeout(3000);
        conn.setInstanceFollowRedirects(false);
        conn.setRequestMethod(method);
        try {
            int status = conn.getResponseCode();
            InputStream source = status >= 400
                    ? conn.getErrorStream() : conn.getInputStream();
            byte[] body;
            if (source == null) {
                body = new byte[0];
            } else {
                try (InputStream in = source) {
                    body = in.readAllBytes();
                }
            }
            switch (path) {
                case "fixed" -> System.out.println(
                        "fixed status=" + status
                        + " len=" + conn.getContentLengthLong()
                        + " mode=" + conn.getHeaderField("X-Lesson-Mode")
                        + " body=" + new String(body, StandardCharsets.UTF_8));
                case "chunked" -> System.out.println(
                        "chunked status=" + status
                        + " transfer=" + conn.getHeaderField("Transfer-Encoding")
                        + " len=" + conn.getContentLengthLong()
                        + " body=" + new String(body, StandardCharsets.UTF_8));
                case "empty" -> System.out.println(
                        "empty status=" + status + " bodyBytes=" + body.length);
                case "head" -> System.out.println(
                        "head status=" + status
                        + " advertised=" + conn.getContentLengthLong()
                        + " bodyBytes=" + body.length);
                case "not-modified" -> System.out.println(
                        "notModified status=" + status
                        + " bodyBytes=" + body.length);
                case "error" -> System.out.println(
                        "error status=" + status
                        + " type=" + conn.getHeaderField("Content-Type")
                        + " body=" + new String(body, StandardCharsets.UTF_8));
                default -> throw new IOException("Unexpected path");
            }
        } finally {
            conn.disconnect();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/fixed", HttpResponseWriteDemo::fixed);
        server.createContext("/chunked", HttpResponseWriteDemo::chunked);
        server.createContext("/empty", HttpResponseWriteDemo::empty);
        server.createContext("/head", HttpResponseWriteDemo::head);
        server.createContext("/not-modified", HttpResponseWriteDemo::notModified);
        server.createContext("/error", HttpResponseWriteDemo::error);
        server.start();
        try {
            URI base = new URI("http", null, "127.0.0.1",
                    server.getAddress().getPort(), "/", null, null);
            check(base, "fixed", "GET");
            check(base, "chunked", "GET");
            check(base, "empty", "GET");
            check(base, "head", "HEAD");
            check(base, "not-modified", "GET");
            check(base, "error", "GET");
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac --release 17 --add-modules jdk.httpserver HttpResponseWriteDemo.java
java --add-modules jdk.httpserver HttpResponseWriteDemo
~~~

**Stdout chính xác đã kiểm chứng khi biên dịch `--release 17` và chạy trên OpenJDK 24:**

~~~text
fixed status=200 len=9 mode=fixed body=Xin chào
chunked status=200 transfer=chunked len=-1 body=alpha-beta
empty status=204 bodyBytes=0
head status=200 advertised=9 bodyBytes=0
notModified status=304 bodyBytes=0
error status=404 type=application/json; charset=UTF-8 body={"error":"missing"}
~~~

### 10.1. Giải thích từng kết quả

| Stdout | Ý nghĩa |
|---|---|
| `fixed status=200 len=9 mode=fixed body=Xin chào` | Server gửi mã 200, custom header và 9 byte UTF-8 theo fixed-length |
| `chunked status=200 transfer=chunked len=-1 body=alpha-beta` | Client thấy header `Transfer-Encoding`, không có `Content-Length` cố định; body đã được giải chunk |
| `empty status=204 bodyBytes=0` | 204 không có response body |
| `head status=200 advertised=9 bodyBytes=0` | HEAD công bố độ dài representation GET nhưng **không gửi body** |
| `notModified status=304 bodyBytes=0` | 304 là response không có content |
| `error status=404 type=application/json; charset=UTF-8 body={"error":"missing"}` | 404 vẫn có error JSON đã được client đọc |

**Phạm vi ví dụ:** chỉ sử dụng HTTP/1.1 loopback JDK implementation; không thử TLS, HTTP/2, proxy, concurrent stress test hoặc streaming vô hạn. Kết quả `Transfer-Encoding: chunked` phản ánh implementation/trường hợp thử; application không được dựa vào đó để xác định dữ liệu nghiệp vụ hợp lệ, mà phải tuân HTTP semantics và reader API.

### 10.2. Vì sao byte[] UTF-8 được tạo trước khi sendResponseHeaders?

Ở nhánh fixed-length, server tạo `byte[]` một lần rồi **sử dụng chính `bytes.length` cho metadata và write**. Nhờ vậy không nhầm `String.length()`, không thay đổi charset giữa lúc tính length và lúc ghi. Nếu dùng gzip, phải tạo/đếm length của compressed bytes hoặc chọn streaming chunked để không cần biết trước độ dài.

### 10.3. Tại sao dùng -1 cho no-body và vẫn đóng exchange?

`sendResponseHeaders(204,-1)`/`(304,-1)`/`HEAD -1` cho biết không phát body. `ex.close()` giải phóng tài nguyên và kết thúc exchange. Việc không ghi body không đồng nghĩa không cần hoàn tất exchange. Trường hợp có body, try-with-resources đóng `OutputStream` giúp hoàn tất response và giải phóng resources.

### 10.4. Tại sao client có getErrorStream riêng?

Server gửi một response HTTP 404 **hoàn toàn hợp lệ** với body JSON. Legacy `HttpURLConnection.getInputStream()` có thể ném IOException trên HTTP 4xx/5xx; vì vậy code client demo chọn `getErrorStream()` khi `status >= 400`. Đây là đặc điểm **client-side API**, không có nghĩa server phải dùng một stream khác để viết lỗi: server vẫn dùng **cùng `HttpExchange.getResponseBody()`** cho mọi HTTP status có body.

## 11. Lỗi fixed-length: ghi thiếu hoặc ghi thừa

Javadoc Java 17 rất cụ thể:

- `responseLength > 0` nghĩa handler phải viết **đúng** số byte.
- Nếu viết **thừa**, `OutputStream.write` ném `IOException`.
- Nếu viết **thiếu**, `OutputStream.close()` ném `IOException`.
- Trong cả hai trường hợp, exchange bị abort và underlying TCP connection bị đóng.

~~~java
// Ví dụ KHÔNG CHẠY trong demo chính: cố ý sai số byte.
byte[] body = "abc".getBytes(StandardCharsets.US_ASCII);
exchange.sendResponseHeaders(200, 4); // Khai báo 4 byte.
try (OutputStream out = exchange.getResponseBody()) {
    out.write(body);                    // Chỉ viết 3 byte.
} // close() có thể ném IOException vì thiếu 1 byte.
~~~

Đây là **phản ví dụ** về lỗi giao thức, không phải snippet khuyến nghị chạy. Khi response đã commit mà lỗi ghi xảy ra, không thể sửa lại Content-Length/status trên wire. Client có thể nhận truncated response/EOF bất thường. Trong production nên log exception và kiểm tra trạng thái client download thay vì ghi nhận success chỉ vì status 200 đã rời server.

### 11.1. Tránh dùng số ký tự làm Content-Length

~~~text
String s = "Xin chào";
s.length()                 = 8 Java UTF-16 code units
s.getBytes(UTF_8).length   = 9 UTF-8 bytes

sendResponseHeaders(200, 8)  + write(9 UTF-8 bytes) => sai
sendResponseHeaders(200, 9)  + write(9 UTF-8 bytes) => đúng
~~~

Nếu response có emoji, Java `String.length()` có thể đếm **hai UTF-16 code units** cho một Unicode supplementary code point; còn UTF-8 có thể dùng bốn byte. **Độ dài truyền HTTP luôn phải xét byte**, không phải `String.length()` hoặc số chữ nhìn thấy trên màn hình.

## 12. Body lớn hoặc sinh dữ liệu dần: chọn mô hình phù hợp

| Tình huống | Chế độ response | Vì sao |
|---|---|---|
| JSON nhỏ đã encode xong thành `byte[]` | Fixed-length, `bytes.length` | Đơn giản, chính xác và biết đủ dung lượng |
| File đã biết kích thước bytes | Fixed-length nếu có thể viết chính xác | Client có metadata độ dài và phát hiện truncated |
| Nội dung tạo dần/không biết trước kích thước | Chunked, length `0` | Không cần buffer toàn bộ trước khi viết |
| SSE/log streaming lâu dài | Chunked + flush theo protocol có kiểm soát | Phải thiết kế deadline, heartbeat và cancellation |
| Response `204`/`304`/`HEAD` | No-body, length `-1` | Tuân HTTP semantics |
| Error JSON nhỏ đã biết | Fixed-length với status 4xx/5xx đúng | Client có thể parse error body có giới hạn |

**Chunked không tự làm code bất đồng bộ.** Nếu handler gọi một hàm tạo dữ liệu chậm rồi `write`, thread handler vẫn bị chiếm theo executor mà `HttpServer` sử dụng. Muốn phục vụ nhiều streaming exchanges đồng thời, cần cấu hình executor, hạn chế concurrency và giải quyết backpressure, timeout, client disconnect và số byte gửi.

**Không lưu mọi chunk vô hạn trong RAM** trước khi gọi `write`. Ưu điểm của chunked là gửi bytes incremental; nếu đã xây xong body nhỏ thành byte[] thì fixed-length đơn giản hơn.

### 12.1. Streaming, flush và kết thúc body

~~~java
exchange.sendResponseHeaders(200, 0);
try (OutputStream out = exchange.getResponseBody()) {
    for (byte[] chunk : chunks) {
        out.write(chunk);
        out.flush(); // Có thể giúp client nhận dần; không kết thúc body.
    }
} // close() mới đánh dấu kết thúc response.
~~~

Đây là **trích đoạn**: `chunks` là nguồn byte[] do application cung cấp; cần giới hạn kích thước/tiến độ, không biến ví dụ thành stream vô hạn. `flush()` không có bảo đảm mỗi call tạo đúng một HTTP chunk mà client đọc theo một record. Dùng framing nội dung như newline-delimited JSON nếu cần phân biệt logical messages.

### 12.2. Compression thay đổi độ dài

Nếu muốn `Content-Encoding: gzip`:

- Body trên wire phải là **bytes đã gzip**, không phải String trước khi gzip.
- Khi fixed-length, dùng **số byte của compressed representation**, không dùng số byte source.
- Nếu nén streaming và không biết trước tổng byte, có thể chọn chunked, nhưng phải **đóng đúng cả gzip wrapper và response stream**, xử lý thứ tự close và buffering cẩn thận.
- Thêm/kiểm soát `Vary: Accept-Encoding` khi response representation phụ thuộc request header; không dùng gzip với mọi client nếu không đàm phán đúng.
- Đặt `Content-Type` cho media type gốc; `Content-Encoding` mô tả content coding áp lên representation.

**Không tự set `Content-Length` thủ công bằng độ dài dữ liệu chưa nén rồi bật gzip**: client sẽ gặp mismatch về framing hoặc parse.

## 13. Quản lý tài nguyên của HttpExchange

Javadoc `HttpExchange` nói exchange được kết thúc khi request input stream và response output stream được đóng. Đóng response output cũng đóng request input nếu nó còn mở; tuy vậy để reuse TCP connection đáng tin hơn, nên **tiêu thụ request body hợp lệ trước khi đóng**. Đóng khi còn request body chưa đọc có thể khiến connection không còn sử dụng được cho exchange tiếp theo.

### 13.1. Request body dài cũng có hậu quả

Một handler xử lý POST có thể đọc `exchange.getRequestBody()`. Nếu server chỉ đọc vài byte rồi trả response, việc `close()` có thể phải discard một lượng byte giới hạn hoặc khiến persistent connection không còn reuse. Đừng giả định connection reuse sẽ luôn xảy ra.

Nên áp giới hạn bytes/time cho request body, tránh chấp nhận dữ liệu quá lớn, và chọn policy **reject early vs drain remaining body** phù hợp service. Không đọc mọi request body bằng `readAllBytes()` không có quota.

### 13.2. OutputStream phải được đóng

- Với fixed-length/chunked: `try (OutputStream out = exchange.getResponseBody()) { ... }`.
- Với no-body: `sendResponseHeaders(..., -1)` rồi `exchange.close()`.
- Trong handler thực tế cần `try/finally` để dọn tài nguyên cả khi exception xảy ra, nhưng **không gửi một response mới sau khi response cũ đã commit**.

Một response kết thúc bất thường có thể khiến client biết status 200 nhưng đọc body thất bại. **Application-level success phải tính sau khi ghi body hoàn tất và xử lý downstream phù hợp**, không chỉ sau `sendResponseHeaders`.

### 13.3. Request handlers và exception

`HttpHandler.handle` có thể ném `IOException`. Hệ thống cần cơ chế log/sanitize exception và không để error response chứa stack trace hoặc credentials. Nếu lỗi xảy ra **trước khi gửi headers**, có thể gửi status 500 phù hợp; nếu lỗi xảy ra **sau headers**, phải kết thúc exchange và ghi nhận partial response, không cố thay status.

## 14. Những vấn đề về header framing

### 14.1. Content-Length và Transfer-Encoding không được mâu thuẫn

HTTP/1.1 có những quy tắc rõ về message framing. **Không vừa tự đặt `Content-Length` cố định, vừa tự gắn `Transfer-Encoding: chunked` cho cùng body rồi giả định mọi proxy/client sẽ suy luận giống nhau**. Cách ít lỗi với JDK HttpServer:

- Fixed body: `sendResponseHeaders(status, bytes.length)`, **để server tự xử lý Content-Length**.
- Unknown length: `sendResponseHeaders(status, 0)`, **để server tự xử lý chunked framing**.
- No body: `sendResponseHeaders(status, -1)`, không write body.
- HEAD: có thể đặt `Content-Length` để mô tả GET tương ứng nhưng vẫn **không gửi body**.

### 14.2. Chunked là HTTP message framing, không phải application framing

Wire representation có chunk sizes, delimiters và terminating chunk. `HttpURLConnection` hay `java.net.http.HttpClient` sẽ xử lý HTTP framing; dữ liệu ứng dụng chỉ thấy **body bytes đã được giải mã theo HTTP transfer framing**. Nếu server viết `alpha-` và `beta`, client có thể đọc `alpha-beta` trong một lần read hoặc nhiều lần. Không gắn protocol meaning cho số lần Java write hoặc network packets.

### 14.3. Cache, 304 và body rules

`304` không gửi body mới. Khi trả 304, các metadata như `ETag`, `Cache-Control`, `Last-Modified` hoặc `Vary` phải tuân conditional request semantics; không phải cứ mọi GET đều có thể trả 304 mà không kiểm tra request conditional headers.

`204` cũng không gửi body, nhưng không phải thông báo cache “Not Modified”. Đừng dùng 204 như thay thế cho 304 hoặc ngược lại.

## 15. Client quan sát status/headers/body như thế nào?

Có thể dùng client hiện đại Java 17:

~~~java
// Trích đoạn: client và URI đã được tạo hợp lệ.
HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

System.out.println(response.statusCode());
System.out.println(response.headers()
        .firstValue("Content-Type").orElse("unknown"));
System.out.println(response.body());
~~~

Khi `BodyHandlers.ofString()` hoàn tất thành công, String đã được body subscriber đọc và decode, nhưng **không tự chứng minh business JSON hợp lệ**. Body của HTTP 404/500 cũng có thể được đọc thành String theo handler, không tự ném exception chỉ vì status >=400.

Với `BodyHandlers.ofInputStream()`, `HttpResponse<InputStream>` có thể có sau headers **trước khi toàn bộ body truyền xong**; caller còn phải đọc stream tới EOF/close. Phía server, `sendResponseHeaders` đã gửi headers không có nghĩa client đã nhận/tiêu thụ hết body.

Legacy `HttpURLConnection` cho phép `getResponseCode()`, `getHeaderField(...)`, `getInputStream()` và `getErrorStream()`; demo dùng nó để in byte[] và metadata, nhưng **đường HTTP error body** phải xử lý nullable error stream. Đừng xem `getErrorStream() == null` là bằng chứng 404 không thể có body trong mọi trường hợp.

## 16. Bảo mật khi trả status và headers

| Rủi ro | Cách phòng tránh |
|---|---|
| Lộ chi tiết nội bộ qua response 500 | Trả error code ổn định, thông điệp ngắn; log stack trace phía server với kiểm soát |
| Header injection / response splitting | Validate/encode dữ liệu đưa vào `Location` và custom headers; từ chối CR/LF |
| Lộ token/PII qua body lỗi | Redact, chỉ trả trường được API contract cho phép |
| Cache nhầm dữ liệu nhạy cảm | Xét `Cache-Control: no-store` và cache key đúng |
| CORS bị coi là authentication | Không; vẫn phải kiểm tra session/token/authorization phía server |
| Body quá lớn | Hạn chế request/response size, concurrency, latency, buffer size |
| Stream không close | try-with-resources và finally; thiết kế cancellation |
| Ghi Content-Length sai | Tính byte[] thực, không dựa trên ký tự/JSON size ước lượng |
| Nội dung browser bị sniff MIME | Đặt `Content-Type` đúng và `X-Content-Type-Options: nosniff` khi phù hợp |
| Open redirect | Validate `Location` và target URI trước khi trả redirect do input điều khiển |

**`HttpServer` trong JDK là lightweight**; dùng trong production cần bổ sung authentication, access control, rate limiting, TLS config, observability, graceful shutdown, thread pool policies và reverse proxy/ingress security phù hợp. Bài tập minh họa chỉ chạy HTTP trên loopback.

## 17. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| Gọi `sendResponseHeaders(200, 0)` mà tưởng Content-Length 0 | `0` là chunked | Với no-body dùng `-1` |
| Fixed-length request body trả client lỗi/truncated | Đếm `String.length()` thay vì bytes UTF-8 | Tính `byte[].length` |
| `OutputStream.close()` ném IOException | Viết **thiếu** số byte fixed-length | Đảm bảo số byte đúng trước khi close |
| `OutputStream.write()` ném IOException | Viết **thừa** số byte fixed-length | Ghi đúng length hoặc dùng chunked |
| Client đợi mãi response chunked | Không close response body stream | try-with-resources |
| Gửi 204 mà vẫn cố write JSON | 204 không có response body | `sendResponseHeaders(204, -1)` |
| HEAD trả về body | Hiểu nhầm metadata là representation body | Chỉ gửi headers; `-1` |
| 304 bị dùng như status success có JSON | 304 là conditional cache, không có content | Đặt validator/headers phù hợp |
| Client nhận body `{"error":"..."}` nhưng status 200 | Server không phân loại error | Trả status 4xx/5xx phù hợp |
| Tự gắn Content-Length và chunked cùng lúc | Framing mâu thuẫn | Để `sendResponseHeaders` quản lý |
| Sửa header sau `sendResponseHeaders` mà client không thấy | Headers đã được commit | Đặt tất cả trước khi gọi |
| Cố gửi status 500 sau khi response 200 đã bắt đầu | Không thể gửi hai status lines cùng exchange | Log partial response/close, sửa flow |
| `getResponseBody()` trước `sendResponseHeaders` | Sai thứ tự API | Gửi headers trước rồi mới lấy stream |
| GET /error có status 404 nhưng client không thấy body | Client legacy chỉ gọi `getInputStream` | Dùng `getErrorStream` khi có body lỗi |
| Không log được byte cuối cùng | Stream lỗi hoặc client disconnect | Bắt IOException, ghi status body_failed |
| Gửi response rất lớn làm OOM | Buffer toàn bộ body trong heap | Stream chunked hoặc fixed từ file có quota |
| Compression khiến body lỗi | Độ dài tính trước nén | Tính compressed bytes hoặc chunked |
| GET body với 204 nhưng parser vỡ | 204 không có payload | Không parse body với 204 |
| Header chứa CR/LF từ input | Header injection hoặc syntax invalid | Validate dữ liệu và từ chối ký tự cấm |

## 18. Checklist thiết kế HttpHandler

**Trước khi gửi headers:** method/URI đã validate? Có body request cần đọc hay giới hạn? Status code đúng semantics? `Content-Type`, encoding, cache headers, `Location`/`Allow`/`ETag` nếu cần đã sẵn? Có dùng input không đáng tin trong headers hay error JSON không?

**Chọn framing:** body có byte[] với độ dài đã biết không? Nếu fixed-length, `responseLength = bytes.length > 0` và phải ghi đúng số byte. Nếu body stream không biết length, dùng `0` chunked. Nếu không gửi body, dùng `-1`. Với HEAD/204/304, tuân quy tắc không body. Không tự tạo header Content-Length cạnh tranh với API.

**Trong lúc ghi:** `sendResponseHeaders` được gọi một lần trước `getResponseBody`? Có try-with-resources? Chương trình có thể báo lỗi trước khi commit không? Nếu lỗi sau commit, có cleanup và log partial response không?

**Sau khi ghi:** stream đã close, exchange đã được kết thúc? Có leak request input hay output? Monitoring có phân biệt status code, byte count, I/O failure và client disconnect không? Client có kiểm tra status/body thật sau khi nhận không?

## 19. Câu hỏi tự kiểm tra

**1. `sendResponseHeaders(200, 0)` nghĩa response body dài 0 byte?** Không. `0` chọn chunked transfer encoding.

**2. Muốn response 204 không gửi body thì dùng responseLength nào?** `-1`.

**3. `sendResponseHeaders(200, 12)` nhưng chỉ viết 10 byte thì sao?** Khi đóng output stream có thể ném IOException; exchange bị abort.

**4. `sendResponseHeaders(200, 12)` nhưng ghi 13 byte?** `write` có thể ném IOException và abort exchange.

**5. Vì sao phải dùng `bytes.length` thay `String.length()`?** HTTP length tính theo byte của representation được gửi; Unicode UTF-8 khác UTF-16 code units.

**6. Có nên tự set `Transfer-Encoding: chunked` khi responseLength đã là 0?** Không; để HTTP server quản lý framing.

**7. `out.flush()` có phải tín hiệu kết thúc chunked body?** Không. Phải close response body output stream.

**8. `HEAD` response có thể có Content-Length nhưng không body?** Có. Length mô tả GET tương ứng khi phù hợp.

**9. `304 Not Modified` có body JSON mới không?** Không. Đây là conditional cache response, không gửi content.

**10. Gặp lỗi sau khi đã gọi `sendResponseHeaders(200, ...)` có thể đổi status thành 500?** Không. Headers đã commit.

**11. Nếu server trả 404 kèm JSON, có phải Java server dùng `getErrorStream` để viết body?** Không. Server vẫn dùng `getResponseBody`; `getErrorStream` là API client legacy.

**12. Chọn status 201 khi nào?** Khi resource đã được tạo thành công theo semantics; có thể thêm `Location`.

**13. Với 405 Method Not Allowed nên thêm header gì?** `Allow` liệt kê các methods được resource hỗ trợ.

**14. Response chunked có đảm bảo một `write` thành một chunk mạng không?** Không. HTTP/TCP có thể chia/gộp dữ liệu.

**15. Chạy ví dụ có cần Internet hoặc thư viện bên ngoài không?** Không. Dùng loopback `127.0.0.1` và JDK module `jdk.httpserver`.

**16. `HttpServer` đã tự có production authentication/rate limit chưa?** Không theo cách framework đầy đủ; application phải thiết kế các policy bổ sung.

**17. Chunked có nghĩa mọi client phải thấy `Content-Length`?** Không. HTTP/1.1 chunked thường có `Transfer-Encoding` thay cho length cố định.

**18. Nếu không cần gửi response body, có cần đóng exchange không?** Có; kết thúc exchange giúp giải phóng resources.

## 20. Tài liệu chính thức

- [Java SE 17 – HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): lifecycle, `getResponseHeaders`, `sendResponseHeaders`, `getResponseBody`, error khi ghi sai fixed length, close/connection reuse.
- [Java SE 17 – Headers](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): `set`, `add`, `getFirst` và tên header case-insensitive.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): tạo server, bind port, context, start/stop, executor.
- [Java SE 17 – HttpHandler](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): xử lý một HTTP exchange.
- [Java SE 17 – HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): HTTPS variant của lightweight JDK HTTP server.
- [Java SE 17 – HttpURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): quan sát status, header, input/error stream từ client.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client hiện đại.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status, representation, HEAD, 204/304 và request/response semantics.
- [RFC 9112 – HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): Content-Length, chunked transfer encoding và framing.

**Kết luận:** Trong JDK `HttpServer`, trước tiên chọn **status code đúng**, đặt **response headers** trên `getResponseHeaders()`, sau đó gọi **`sendResponseHeaders(status, length)` đúng một lần** và ghi/đóng body. Nhớ quy ước bắt buộc: **length dương = đúng từng byte; 0 = chunked; -1 = không có response body**. Tuân HTTP semantics của HEAD/204/304, không nhầm Unicode character count với byte count, và luôn close stream/exchange để response thật sự kết thúc.
