# HTTP server gọn trong Java: Đọc method, URI, header và body

## Mục tiêu bài học

Khi viết một HTTP server nhỏ bằng Java, một request không chỉ là “đường dẫn URL” và “chuỗi dữ liệu”. Nó bao gồm **HTTP method**, **request-target URI**, **các header có thể lặp và không phân biệt chữ hoa/thường ở tên**, cùng **request body dạng luồng byte**. Mỗi phần có API, cú pháp, quy tắc giải mã và yêu cầu bảo mật khác nhau. Java Development Kit cung cấp một HTTP server nhỏ là `com.sun.net.httpserver.HttpServer`, thuộc module **`jdk.httpserver`**, cùng `HttpHandler` và `HttpExchange` để đọc request và trả response.

Đây là **JDK-specific module** còn được tài liệu Oracle Java SE 26 & JDK 26 mô tả, không phải một phần của đặc tả Java SE độc lập với mọi JDK vendor. Nó phù hợp với ví dụ học tập, kiểm thử tích hợp, công cụ nội bộ hoặc endpoint đơn giản; không đồng nghĩa có đầy đủ tính năng của một web framework hay HTTP reverse proxy production.

Sau khi học, bạn có thể:

1. Khởi tạo server qua `HttpServer.create`, đăng ký `createContext`, gắn handler và đóng server đúng vòng đời.
2. Đọc HTTP method qua `exchange.getRequestMethod()`; phân biệt `GET`, `POST`, `PUT`, `DELETE` và trả `405 Method Not Allowed` đúng ngữ nghĩa khi endpoint không hỗ trợ method.
3. Đọc URI qua `exchange.getRequestURI()`; phân biệt `getRawPath` với `getPath`, `getRawQuery` với `getQuery`, và không nhầm raw percent-encoding với ký tự sau giải mã.
4. Lấy header bằng `exchange.getRequestHeaders()` và `Headers.getFirst` hoặc `get`, biết tên header không phân biệt hoa/thường, một tên có thể có nhiều giá trị, request headers không được sửa.
5. Đọc request body qua `exchange.getRequestBody()` như một `InputStream`, không tự giả định nó là `String`, JSON object hoặc có giới hạn sẵn.
6. Giới hạn dung lượng body **trước khi materialize**, kiểm tra content type và giải mã UTF-8 bằng `CharsetDecoder` cấu hình **REPORT** để từ chối byte sai.
7. Hiểu `Content-Length`/`Transfer-Encoding`/chunked framing có ý nghĩa gì và vì sao không chỉ tin mỗi `Content-Length` để áp hạn mức.
8. Trả response đúng thứ tự: response headers → `sendResponseHeaders` → ghi output stream → đóng exchange/streams.
9. Xử lý 200/400/404/405/413/415 một cách có kiểm thử và đóng tài nguyên khi có lỗi.
10. Biết các giới hạn bảo mật: URL decoding, path normalization, header trust, request smuggling ở tầng proxy, timeouts, concurrency, body upload, logging và không tự biến API demo thành web service public.
11. Chạy một chương trình **Java 17+ độc lập** dùng chính HTTP server JDK và `java.net.http.HttpClient` gọi request qua loopback `127.0.0.1`, xác nhận **31 phép kiểm tra tự động** đã được chạy thật trên OpenJDK 24.

**Special Note:** Chỉ sử dụng kiến thức **còn áp dụng hiện nay**; không khuyến nghị thư viện hoặc API đã lỗi thời/legacy. `jdk.httpserver` và `java.net.http` vẫn hiện hành. Ví dụ biên dịch với `javac --release 17` để chạy trên các JDK 17+ có hai modules này; không yêu cầu Spring, servlet container hay dependency bên ngoài.

## 1. Tổng quan luồng request/response

Một HTTP request dạng minh họa:

```http
POST /api/echo/%C4%91?name=Mai%20Anh&flag=a%2Bb HTTP/1.1
Host: 127.0.0.1
Content-Type: text/plain; charset=UTF-8
X-Trace: alpha
X-Trace: beta
Content-Length: 26

Xin chào
Java 🌏 & bạn
```

Đây là bản **minh họa cấu trúc**, không phải byte dump thực tế: port, request framing, số bytes Content-Length và các headers bổ sung phụ thuộc client và encoding. **Không dùng số Content-Length trong sơ đồ này để tự thiết lập header thật.** Trong ví dụ chạy đầy đủ, `HttpClient` quản lý request framing.

Server cần hiểu từng phần:

| Phần | Ý nghĩa | API phía `HttpExchange` |
| --- | --- | --- |
| `POST` | Method chỉ loại thao tác HTTP | `getRequestMethod()` |
| `/api/echo/%C4%91?...` | Request URI có path/query | `getRequestURI()` |
| `Content-Type`, `X-Trace` | Metadata, có thể nhiều values | `getRequestHeaders()` |
| Dữ liệu sau header | Request body dưới dạng bytes stream | `getRequestBody()` |
| Status response | Kết quả request (200/4xx/5xx) | `sendResponseHeaders(status,length)` |
| Response headers | Content-Type, cache, policy... | `getResponseHeaders()` |
| Response body | Bytes ghi ra client | `getResponseBody()` |

### 1.1. HTTP method không phải URI

`POST /api/echo/item` và `GET /api/echo/item` có cùng request path nhưng **khác method**. Router/handler thường cần xét cả hai. Không quyết định một request “chỉ đọc” dựa vào path hoặc header; method có ý nghĩa riêng trong HTTP semantics.

### 1.2. URI không phải query map đã được parse

`getRequestURI()` trả `java.net.URI`. `URI.getRawQuery()` trả raw query string, **không** tự biến thành `Map<String,String>`, không tự biết parameter nào là array hoặc cách xử lý khóa trùng nhau. Nếu cần query parameters, parser của ứng dụng phải xác định decoding/form conventions, duplicate-key policy và giới hạn kích thước.

### 1.3. Body không nhất thiết tồn tại, và không nhất thiết là text

Với `GET` thông thường, body có thể rỗng. `POST` có thể chứa JSON, form, multipart, protobuf hoặc bytes tùy media type. `getRequestBody()` chỉ trả một `InputStream`; method/URI/header không làm phép giải mã tự động thành object nghiệp vụ.

## 2. Server JDK hiện hành: module `jdk.httpserver`

Các classes quan trọng:

```java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.Headers;
```

`HttpServer` là một simple HTTP server trong JDK, API được giới thiệu từ JDK 6 và tiếp tục hiện diện trong JDK 26. `com.sun.net.httpserver` được JDK công bố chính thức trong module `jdk.httpserver`; **đừng nhầm** nó với các classes `sun.*` không được hỗ trợ.

Từ góc nhìn Java modules:

```java
module my.demo {
    requires jdk.httpserver;
}
```

Đây là **nội dung file `module-info.java` minh họa** cho một named module. Nếu cùng module còn dùng `java.net.http.HttpClient` để kiểm thử, cần thêm `requires java.net.http;`. Với source chạy trên class path thông thường, lệnh `javac --release 17 MiniHttpRequestDemo.java` và `java MiniHttpRequestDemo` được kiểm thử thành công trên JDK 24.

### 2.1. Khởi tạo server chỉ trên loopback

```java
InetSocketAddress address =
        new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0);
HttpServer server = HttpServer.create(address, 0);
server.createContext("/api/echo/", exchange -> {
    // Xử lý request trong HttpExchange.
});
server.start();
```

Đây là **snippet**, cần imports và quản lý shutdown/error handling. Port `0` yêu cầu hệ điều hành cấp một port còn trống; đọc port thật bằng `server.getAddress().getPort()` **sau khi bind**.

**Tại sao bind `127.0.0.1`?** Ví dụ không cần public inbound traffic, nên tránh vô tình mở service cho các máy khác trong mạng. Để cung cấp API public, cần hạ tầng HTTPS, authentication, rate limits, network policy và monitoring phù hợp — không chỉ đổi host thành `0.0.0.0` rồi xem như đủ bảo mật.

### 2.2. Context path là prefix matching

Theo Javadoc `HttpServer.createContext`, context path là root URI path dùng để chọn handler. Matching là **prefix matching** chứ không phải tự tạo một REST router kiểm tra ranh giới từng segment. Ví dụ context `"/foo"` cũng có thể match `"/foobar"`.

Vì vậy dùng `"/api/echo/"` để tránh một số trường hợp match tên prefix ngoài ý muốn, nhưng nếu endpoint chỉ cho đúng một path thì **handler vẫn phải tự kiểm tra path/segments**. Đừng dựa vào prefix context như access-control boundary.

### 2.3. Executor và shutdown

`setExecutor` phải được gọi **trước** `start`. Ví dụ tích hợp dùng `Executors.newFixedThreadPool(4)` và trong `finally` gọi `server.stop(0)` cùng `workers.shutdownNow()`. Mẫu này đủ cho một bài test ngắn, không phải lời khuyên “luôn dùng 4 threads” cho production.

Chọn thread pool phải xét thời gian xử lý, body upload chậm, timeout và backpressure. Nếu một handler blocking quá lâu khi đọc body, thread tương ứng vẫn có thể bị giữ. JDK server nhỏ không tự cung cấp mọi chính sách giới hạn tài nguyên mà một ứng dụng public cần.

## 3. Đọc method bằng `getRequestMethod()`

```java
String method = exchange.getRequestMethod();
if (!"POST".equals(method)) {
    exchange.getResponseHeaders().set("Allow", "POST");
    sendText(exchange, 405, "Method Not Allowed");
    return;
}
```

Đây là **snippet** cần helper `sendText` của ứng dụng. Với endpoint chỉ nhận `POST`, trả `405` và header `Allow: POST` là hành vi có ý nghĩa hơn việc chấp nhận mọi method hoặc trả `200` khi không xử lý.

### 3.1. `GET` và `POST` không quyết định body type

Method phản ánh semantic của request. Content type xác định **biểu diễn** được client gửi trong body. `POST` không mặc nhiên là JSON; `GET` không mặc nhiên có body, và server cũng không nên tự suy diễn từ method rằng body đã được giải mã.

### 3.2. Không gọi mọi lỗi method là 404

- `404 Not Found`: server không có tài nguyên/router phù hợp, ví dụ `/unknown`.
- `405 Method Not Allowed`: endpoint tồn tại nhưng **method không được hỗ trợ**; kèm `Allow` mô tả những methods chấp nhận.
- `415 Unsupported Media Type`: body media type không được endpoint hỗ trợ.
- `400 Bad Request`: dữ liệu request sai quy tắc đầu vào, ví dụ UTF-8 không hợp lệ trong endpoint yêu cầu UTF-8.
- `413 Content Too Large`: body vượt hạn mức byte do endpoint đặt.
- `200 OK`: request hợp lệ và xử lý thành công.

Không trả HTTP 200 cùng một JSON error object để che mọi trường hợp thất bại. Client và monitoring cần status phản ánh đúng kết quả.

### 3.3. HEAD, OPTIONS và các method khác

Ví dụ học tập giới hạn `GET` cho `/health` và `POST` cho `/api/echo/`; nó **không** tự hỗ trợ HEAD/OPTIONS/CORS. Nếu sản phẩm cần HEAD/OPTIONS, hãy triển khai riêng theo HTTP semantics, đặc biệt response body và Allow/CORS headers. Đừng xem mọi request khác POST đều là một trường hợp tương đương về tác động bảo mật.

## 4. Đọc URI bằng `getRequestURI()`

```java
URI uri = exchange.getRequestURI();
String rawPath = uri.getRawPath();
String path = uri.getPath();
String rawQuery = uri.getRawQuery();
String decodedQuery = uri.getQuery();
```

Đây là snippet đầy đủ về API accessor nhưng chưa phải HTTP server hoàn chỉnh. `java.net.URI` là immutable. Các phương thức `getRaw...` giữ nguyên percent-encoded representation; các phương thức không có Raw trả component đã được decode theo URI rules.

### 4.1. Ví dụ raw và decoded

Input:

```text
/api/echo/%C4%91?name=Mai%20Anh&flag=a%2Bb
```

Giá trị Java trong fixture:

| Phương thức | Kết quả |
| --- | --- |
| `uri.getRawPath()` | `/api/echo/%C4%91` |
| `uri.getPath()` | `/api/echo/đ` |
| `uri.getRawQuery()` | `name=Mai%20Anh&flag=a%2Bb` |
| `uri.getQuery()` | `name=Mai Anh&flag=a+b` |

**Khác biệt quan trọng:** `getQuery()` decode `%2B` thành dấu `+`, nhưng Java URI **không tự áp dụng quy tắc form-url-encoded chuyển dấu + thành dấu cách**. Nếu input là `x=a+b`, `getQuery()` có thể vẫn chứa `a+b`.

### 4.2. `URLDecoder` có phạm vi riêng

`java.net.URLDecoder` được thiết kế cho dữ liệu `application/x-www-form-urlencoded`, trong đó ký tự `+` biểu thị khoảng trắng. Nó **không phải** bộ parser URI path tổng quát. Không tự lấy `uri.getPath()` (đã decode) rồi `URLDecoder.decode` lần nữa: **double decoding** có thể biến `%252F` thành dấu `/` ở lần decode thứ hai, gây sai boundary của path.

Nếu cần query form data, xác định rõ:
- Lấy **raw query** từ `uri.getRawQuery()`.
- Chia tên/giá trị theo rules phù hợp, sau đó decode từng thành phần **đúng một lần** bằng charset thống nhất.
- Xử lý khóa trùng, tham số rỗng, invalid percent escape, dấu `=` trong giá trị và độ dài tối đa.
- Giữ nguyên tham số chưa hiểu hoặc từ chối theo contract; không dùng decoder lần hai.

### 4.3. Không gán URI path trực tiếp thành file path

Một API kiểu `GET /files/...` không được tự nối `uri.getPath()` với thư mục chứa file rồi mở `Files.readAllBytes(...)`. Cần xét encoded slash `%2F`, `..`, dot-segments, symbolic links, Unicode normalization, separator khác platform và path containment sau normalization.

Đặc biệt, `getPath()` là decoded component, không tự thực thi **authorization** hoặc chặn path traversal. Route matching và file-system access phải có validation/canonical filesystem resolution riêng.

### 4.4. Absolute URI, Host header và proxy

`exchange.getRequestURI()` biểu thị request target mà server nhận được, không phải một “địa chỉ public đã xác thực” của hệ thống. Nếu app xây redirect hoặc absolute URL, không nên tin tùy tiện `Host`/`Forwarded`/`X-Forwarded-*` từ mọi client. Cấu hình trusted reverse proxies và canonical origin rõ ràng; nếu không có, attacker có thể cố điều khiển domain trong link/redirect do server sinh.

### 4.5. Query không phải nơi tốt để đặt secrets

Query thường xuất hiện trong logs, history, analytics và proxy tracing. Đừng đặt tokens, password hoặc thông tin nhạy cảm vào query nếu có lựa chọn truyền thông tin phù hợp hơn. Trong demo, query chỉ chứa tên ví dụ và ký tự đặc biệt phục vụ kiểm thử decoding.

## 5. Đọc headers bằng `getRequestHeaders()`

`HttpExchange.getRequestHeaders()` trả `com.sun.net.httpserver.Headers` **immutable**, biểu diễn `Map<String, List<String>>`. Tên header là **case-insensitive**. Một tên header có thể xuất hiện lặp và `Headers` giữ danh sách các giá trị.

```java
Headers headers = exchange.getRequestHeaders();

String firstTrace = headers.getFirst("x-TrAcE");
List<String> traces = headers.get("X-TRACE");
String contentType = headers.getFirst("Content-Type");
String missing = headers.getFirst("X-Missing"); // null nếu không có
```

Đoạn này là snippet; cần imports `com.sun.net.httpserver.Headers` và `java.util.List`.

### 5.1. `getFirst` và `get` không tương đương

- `getFirst(name)` lấy **giá trị đầu tiên** trong danh sách hoặc `null`.
- `get(name)` trả `List<String>` (hoặc `null`) chứa các occurrence values.
- `Headers.add` bổ sung một giá trị, `Headers.set` thay danh sách bằng một giá trị; các mutators chỉ dùng trên **mutable headers**, ví dụ `exchange.getResponseHeaders()`.
- `exchange.getRequestHeaders()` là **immutable**; không cố sửa request headers để “chỉnh cho đúng”.

Ví dụ request có:

```http
X-Trace: alpha
x-trace: beta
```

Một code đọc `getFirst("X-TRACE")` thường nhận `alpha`; `get("x-trace")` có **hai giá trị** trong fixture. Header names không phân biệt hoa thường, nhưng không nên biến mọi header nhiều giá trị thành chuỗi gộp bằng dấu phẩy — một số header có rules khác, và các security-sensitive headers cần xử lý chặt.

### 5.2. Header name case-insensitive, value semantics tùy header

`Content-Type`, `Accept`, `Authorization`, `Cookie` và `Set-Cookie` có quy tắc cấu trúc khác nhau. Đừng xử lý tất cả bằng một cách “split comma rồi chọn phần tử cuối”. Với `Authorization`, người dùng thường mong **một scheme token** có policy riêng. Không dùng `getFirst` để lờ các duplicate header bất thường trong những field quan trọng cho routing/authorization/request framing.

### 5.3. Trường hợp không có header

`headers.getFirst("X-Missing")` trả `null`, **không phải empty string**. Hãy kiểm tra null thay vì gọi `.equals` trên nó. Ví dụ:

```java
String trace = headers.getFirst("X-Trace");
if (trace == null) {
    // Header không được gửi.
}
```

Đây là snippet. Không ép các headers tùy chọn phải có giá trị trừ khi API contract yêu cầu.

### 5.4. Request headers là dữ liệu client cung cấp

Một số header là gợi ý/metadata do client tự gửi và **không đáng tin tự thân**. Đừng dùng `X-User-Id` hay `X-Role=admin` làm bằng chứng xác thực. Nếu ứng dụng sau trusted proxy, định nghĩa rõ header nào do proxy ghi đè và proxy nào được tin; không chấp nhận direct untrusted traffic giả mạo forwarded headers.

### 5.5. Content-Length và Transfer-Encoding cần xử lý ở tầng HTTP

Server HTTP framework/parser xác định framing cho request body. `getRequestBody()` cung cấp stream các bytes sau framing. Đừng tự parser raw HTTP từ TCP khi đã dùng `HttpExchange`. Đồng thời **không chỉ tin `Content-Length`** để kiểm tra body size: client có thể gửi chunked body, Content-Length có thể thiếu, hoặc proxy/server có policy khác.

Giới hạn **số bytes thực tế được đọc**, đồng thời có giới hạn HTTP header size, timeouts và front-proxy agreement ở tầng deploy. Request smuggling/desynchronization khi các HTTP intermediaries parse framing khác nhau phải được giải quyết ở HTTP stack/proxy, không chỉ bằng `if(contentLength<MAX)` trong handler.

## 6. Đọc body: `getRequestBody()` trả InputStream

```java
InputStream input = exchange.getRequestBody();
```

Javadoc xác nhận gọi `getRequestBody()` nhiều lần trên cùng exchange trả **cùng stream object**. Nó không “đọc lại từ đầu” sau mỗi lần gọi và không cung cấp JSON parser tự động.

### 6.1. Vì sao `readAllBytes()` không an toàn cho untrusted input?

`InputStream.readAllBytes()` có thể cấp phát lớn nếu client gửi body không giới hạn. Một `POST` hàng GB có thể dùng quá nhiều heap. Với endpoint biết giới hạn nhỏ, đọc tối đa `MAX+1`:

```java
private static final int MAX_BODY_BYTES = 4096;

byte[] payload;
try (InputStream input = exchange.getRequestBody()) {
    payload = input.readNBytes(MAX_BODY_BYTES + 1);
}
if (payload.length > MAX_BODY_BYTES) {
    // Trả HTTP 413 thay vì xử lý tiếp.
}
```

Đây là snippet; cần imports `InputStream`, `HttpExchange`, và phần trả HTTP status. `readNBytes` có trong Java 17. Kỹ thuật `MAX+1` giúp phân biệt body **đúng giới hạn** với body **lớn hơn giới hạn**, **không** đọc toàn bộ body quá lớn vào memory.

**Quan trọng:** khi từ chối body quá lớn và đóng request stream trước khi tiêu thụ hết, underlying connection có thể không được tái sử dụng. Javadoc nói đóng input sớm có thể drain/discard một lượng data tùy implementation; đó là chi phí tài nguyên phải tính đến, không phải lý do để đọc hết body GB vào RAM.

### 6.2. Content-Length không quyết định body bytes thực đọc

`Content-Length` là metadata của HTTP framing khi có, nhưng **không được dùng làm bộ giới hạn duy nhất**. Ví dụ `Transfer-Encoding: chunked` hoặc cấu hình intermediary khác có thể không có độ dài cố định. Trong handler, sau khi HTTP stack giải quyết framing, đếm bytes **từ InputStream**.

Có thể dùng Content-Length làm tín hiệu từ chối sớm một request rõ ràng quá lớn, nhưng vẫn phải giới hạn streaming reads và thiết lập server/proxy max body size.

### 6.3. Byte length khác character length

`"đ"` thường chiếm nhiều UTF-8 bytes dù là một Unicode character. Emoji như `🌏` chiếm 4 UTF-8 bytes. `String.length()` trong Java đếm UTF-16 code units, **không phải** HTTP body bytes. Vì vậy hạn mức upload luôn cần đơn vị rõ: bytes, characters, JSON nodes hay tổng tài nguyên.

Fixture dùng:

```java
TEXT.getBytes(StandardCharsets.UTF_8).length
```

để kiểm tra **số bytes** được đọc tương ứng với ký tự Unicode ban đầu.

## 7. Content-Type và chọn cách decode body

Trước khi diễn giải payload thành text, đọc `Content-Type`:

```java
String contentType = exchange.getRequestHeaders()
        .getFirst("Content-Type");
```

Một endpoint `POST /api/echo/` trong ví dụ chỉ chấp nhận:

- `text/plain` (quy ước của **endpoint này** là UTF-8).
- `text/plain; charset=UTF-8` (có thể khác chữ hoa/thường và khoảng trắng đơn giản).

Những media types khác hoặc thiếu Content-Type được trả `415`. Đây là **API contract do ví dụ định nghĩa**; không có nghĩa HTTP chuẩn bắt buộc mọi `POST` phải chứa Content-Type hay body. Bài cố tình giới hạn để dễ kiểm tra, không phải một media type parser đầy đủ.

### 7.1. Vì sao không áp `new String(bytes, UTF_8)` khi cần từ chối data sai?

Một số convenience decoders có thể **thay bytes sai bằng replacement character** thay vì báo lỗi. Nếu API yêu cầu UTF-8 hợp lệ, dùng:

```java
String text;
try {
    text = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(payload))
            .toString();
} catch (CharacterCodingException e) {
    // HTTP 400 Invalid UTF-8
    return;
}
```

Đây là snippet dùng `java.nio.ByteBuffer`, `java.nio.charset`; biến `payload` là `byte[]` đã giới hạn kích thước. `REPORT` ngăn việc âm thầm coi một byte sequence lỗi là input hợp lệ.

### 7.2. Content-Type có nhiều tham số hơn ví dụ

Một Content-Type thực tế có thể chứa quoted parameters, whitespace và các tham số bổ sung. Demo dùng **so khớp hẹp** để chấp nhận đúng hai dạng dễ hiểu, không cố tự viết một general HTTP media type parser bằng `split(";")` tùy tiện. Với production, dùng parser có test đầy đủ theo HTTP standards và cấu hình charset policy rõ ràng.

### 7.3. JSON, form, multipart, binary cần parser khác

- `application/json`: dùng JSON parser đã được lựa chọn, bảo vệ depth, số token và input size. JDK `java.xml` không phải JSON parser.
- `application/x-www-form-urlencoded`: decode theo form conventions; `+` có thể là khoảng trắng. Không dùng cách đó để decode URI path.
- `multipart/form-data`: parsing boundary, file quotas, filename policy, file scanning và storage isolation là chủ đề riêng; không biến raw body thành String rồi tách ngẫu nhiên.
- `application/octet-stream`: giữ bytes, xử lý binary stream, không tự decode UTF-8.
- `Content-Encoding: gzip`: nếu hỗ trợ giải nén, cần giới hạn **bytes sau giải nén** và tỷ lệ nén để tránh zip bombs; demo không hỗ trợ request compression.

Trọng tâm bài là **đọc method, URI, header và body** một cách đúng, trước khi lựa chọn parser nghiệp vụ.

## 8. Phản hồi HTTP: status, headers và output stream

Sau khi đọc/validate request, handler cần gửi response. Trình tự Javadoc:

1. `getResponseHeaders()` để đặt `Content-Type` và các headers khác.
2. `sendResponseHeaders(status, responseLength)`.
3. `getResponseBody()`, ghi bytes.
4. Đóng response stream và exchange.

Helper đầy đủ về response (snippet trong class đã import):

```java
private static void respond(HttpExchange exchange, int status, String message)
        throws IOException {
    byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
    Headers out = exchange.getResponseHeaders();
    out.set("Content-Type", "text/plain; charset=UTF-8");
    out.set("X-Content-Type-Options", "nosniff");
    exchange.sendResponseHeaders(status, bytes.length);
    try (OutputStream body = exchange.getResponseBody()) {
        body.write(bytes);
    }
}
```

Helper dùng body **không rỗng** trong fixture. Nếu muốn trả response không có body, đặc biệt `204 No Content`, `304 Not Modified` hoặc `HEAD`, hãy theo đúng contract của `sendResponseHeaders` và HTTP semantics; **đừng coi `responseLength=0` là luôn “no body”**. Trong `HttpExchange`, length 0 có nghĩa xử lý transfer-encoded/chunked response với khả năng có body, còn negative length cho trường hợp không có response body. Với fixed-length body phải ghi **đúng số bytes** đã khai báo; thiếu/thừa bytes có thể abort exchange.

### 8.1. Response Content-Type phải phù hợp bytes

Ví dụ ghi UTF-8 bytes và đặt `text/plain; charset=UTF-8` nhất quán. Không nhận request Content-Type là `application/json` nhưng gửi chuỗi plain text tự xưng JSON.

### 8.2. `getRequestHeaders()` và `getResponseHeaders()` khác tính mutable

Request headers từ `exchange.getRequestHeaders()` **immutable**, response headers từ `exchange.getResponseHeaders()` **mutable**. Muốn đặt `Allow` khi `405` hoặc `Content-Type` thì sửa response headers **trước `sendResponseHeaders`**.

### 8.3. Đóng streams/exchange

Theo Java SE 26, `HttpExchange` implements `AutoCloseable`, nên có thể viết:

```java
@Override
public void handle(HttpExchange exchange) throws IOException {
    try (exchange) {
        // Đọc method/URI/headers/body và gửi response...
    }
}
```

Đây là snippet cần nằm trong một `HttpHandler`. `close()` kết thúc exchange; Javadoc lưu ý nên tiêu thụ request body khi cần tái sử dụng connection. Demo cũng đóng request `InputStream` và response `OutputStream` riêng với try-with-resources, rồi đóng exchange nhằm không bỏ tài nguyên khi có exception.

**Một HTTP handler phải gửi response thành công hoặc kết thúc exchange**, không bỏ mặc stream mở. Khi đã bắt đầu gửi response thì không thể đơn giản đổi status từ 200 sang 500 sau khi bytes đã được gửi; xử lý lỗi và validation **trước** khi gọi `sendResponseHeaders` càng nhiều càng tốt.

## 9. Thiết kế endpoint đọc request trong ví dụ

Fixture sử dụng hai contexts:

| Context | Method cho phép | Mục đích |
| --- | --- | --- |
| `/api/echo/` | `POST` | Đọc method, URI, request headers, body; trả lại dữ liệu quan sát được bằng text |
| `/health` | `GET` | Kiểm tra server và minh họa method/query |
| `/unknown` | Không đăng ký | JDK server trả 404 |

Mọi traffic chạy qua `127.0.0.1` với port do hệ điều hành cấp. Bản thân server không được cung cấp API public. Tests kiểm tra status từ các HTTP requests thực bằng `java.net.http.HttpClient`, không chỉ gọi handler như một hàm Java với mock data.

### 9.1. Contract của `POST /api/echo/`

- Method phải là POST, nếu không trả **405** và `Allow: POST`.
- Content-Type phải là `text/plain` hoặc `text/plain; charset=UTF-8` theo policy demo; nếu không trả **415**.
- Body tối đa **4096 bytes**; đọc tối đa 4097 bytes để xác định vượt giới hạn, trả **413** nếu cần.
- UTF-8 phải hợp lệ; nếu không trả **400**.
- Trả response text chứa method, raw/decoded path, raw/decoded query, header `X-Trace` đầu tiên, số giá trị header đó, tình trạng missing header, số bytes body và text sau decode.
- Không render text input của người dùng dưới dạng HTML hoặc SQL; response là `text/plain` cùng `nosniff` nhằm giữ rõ context.

**Giới hạn minh họa:** Endpoint echo cố tình phản hồi dữ liệu nhận được để dạy API; không nên log/echo toàn bộ headers hoặc body của request thật trong production, vì có thể chứa credentials, personal data hoặc secrets.

### 9.2. Lý do kiểm tra số bytes thật

Một client gửi `Content-Length` không cần xuất hiện trong application code mới đọc được `getRequestBody`. HTTP stack làm việc với request framing. Limit cần bảo vệ process heap **kể cả khi Content-Length vắng mặt**. 4096 chỉ là giá trị cho fixture; production phải định nghĩa theo use case, memory budget và API contract.

### 9.3. Quy tắc fail-fast và leak-safe

Handler kiểm tra method/media type trước khi materialize body, sau đó giới hạn bytes, rồi decode chặt. Mọi nhánh lỗi đều gọi helper phản hồi và kết thúc trong scope `try (exchange)`. Vì lỗi method/media type có thể không đọc hết body, connection đó có thể không được tái sử dụng; đây là trade-off được Javadoc mô tả.

## 10. Chương trình Java 17+ chạy độc lập, có integration tests thật

Tạo một file tên **`MiniHttpRequestDemo.java`** và sao chép chính xác mã sau. Chương trình dùng hai modules có sẵn trong JDK:

- `jdk.httpserver` cho `HttpServer`/`HttpExchange`.
- `java.net.http` cho `HttpClient`/`HttpRequest`/`HttpResponse`.

Không cần Maven, Spring Boot, servlet, database hay Internet. Server chỉ bind local loopback và được dừng sau khi kiểm thử. Các assertions in kết quả ổn định, không hardcode port ngẫu nhiên.

### 10.1. Toàn bộ mã nguồn `MiniHttpRequestDemo.java`

```java
import com.sun.net.httpserver.Headers;
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
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MiniHttpRequestDemo {
    private static final int MAX_BODY_BYTES = 4096;
    private static final String TEXT = "Xin chào\nJava 🌏 & bạn";

    private static void respond(HttpExchange exchange, int status, String message)
            throws IOException {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        Headers out = exchange.getResponseHeaders();
        out.set("Content-Type", "text/plain; charset=UTF-8");
        out.set("X-Content-Type-Options", "nosniff");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream body = exchange.getResponseBody()) {
            body.write(bytes);
        }
    }

    private static boolean acceptsUtf8Text(String contentType) {
        if (contentType == null) return false;
        String compact = contentType.toLowerCase(Locale.ROOT)
                .replace(" ", "").replace("\t", "");
        return compact.equals("text/plain")
                || compact.equals("text/plain;charset=utf-8");
    }

    private static final class EchoHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            try (exchange) {
                String method = exchange.getRequestMethod();
                if (!method.equals("POST")) {
                    exchange.getResponseHeaders().set("Allow", "POST");
                    respond(exchange, 405, "Method Not Allowed");
                    return;
                }
                URI uri = exchange.getRequestURI();
                Headers headers = exchange.getRequestHeaders();
                String contentType = headers.getFirst("Content-Type");
                if (!acceptsUtf8Text(contentType)) {
                    respond(exchange, 415, "Use text/plain; charset=UTF-8");
                    return;
                }
                byte[] bytes;
                boolean sameBody;
                try (InputStream requestBody = exchange.getRequestBody()) {
                    sameBody = requestBody == exchange.getRequestBody();
                    bytes = requestBody.readNBytes(MAX_BODY_BYTES + 1);
                }
                if (bytes.length > MAX_BODY_BYTES) {
                    respond(exchange, 413, "Body too large");
                    return;
                }
                final String decodedBody;
                try {
                    decodedBody = StandardCharsets.UTF_8.newDecoder()
                            .onMalformedInput(CodingErrorAction.REPORT)
                            .onUnmappableCharacter(CodingErrorAction.REPORT)
                            .decode(ByteBuffer.wrap(bytes)).toString();
                } catch (CharacterCodingException invalid) {
                    respond(exchange, 400, "Invalid UTF-8");
                    return;
                }
                String trace = headers.getFirst("x-TrAcE");
                List<String> traces = headers.get("X-TRACE");
                String reply = String.join("\n",
                        "method=" + method,
                        "rawPath=" + uri.getRawPath(),
                        "path=" + uri.getPath(),
                        "rawQuery=" + uri.getRawQuery(),
                        "query=" + uri.getQuery(),
                        "traceFirst=" + trace,
                        "traceCount=" + (traces == null ? 0 : traces.size()),
                        "missingHeader=" + (headers.getFirst("X-Missing") == null),
                        "sameBodyStream=" + sameBody,
                        "bodyBytes=" + bytes.length,
                        "body=" + decodedBody);
                respond(exchange, 200, reply);
            }
        }
    }

    private static final class HealthHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            try (exchange) {
                if (!exchange.getRequestMethod().equals("GET")) {
                    exchange.getResponseHeaders().set("Allow", "GET");
                    respond(exchange, 405, "Method Not Allowed");
                    return;
                }
                respond(exchange, 200, "health=" + exchange.getRequestMethod()
                        + "\nrawQuery=" + exchange.getRequestURI().getRawQuery());
            }
        }
    }

    private static HttpResponse<String> send(HttpClient client, HttpRequest request)
            throws Exception {
        return client.send(request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
    }

    private static void check(String name, boolean value) {
        if (!value) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) throws Exception {
        InetSocketAddress address =
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0);
        HttpServer server = HttpServer.create(address, 0);
        ExecutorService workers = Executors.newFixedThreadPool(4);
        try {
            server.createContext("/api/echo/", new EchoHandler());
            server.createContext("/health", new HealthHandler());
            server.setExecutor(workers);
            server.start();
            int port = server.getAddress().getPort();
            String base = "http://127.0.0.1:" + port;
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            check("ephemeralPortAssigned", port > 0);
            HttpRequest post = HttpRequest.newBuilder(
                    URI.create(base + "/api/echo/%C4%91?name=Mai%20Anh&flag=a%2Bb"))
                    .timeout(Duration.ofSeconds(6))
                    .header("Content-Type", "text/plain; charset=UTF-8")
                    .header("X-Trace", "alpha")
                    .header("x-trace", "beta")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            TEXT, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> result = send(client, post);
            String response = result.body();
            check("postStatus200", result.statusCode() == 200);
            check("methodRead", response.contains("method=POST\n"));
            check("rawPathPreserved",
                    response.contains("rawPath=/api/echo/%C4%91\n"));
            check("decodedPath",
                    response.contains("path=/api/echo/đ\n"));
            check("rawQueryPreserved",
                    response.contains("rawQuery=name=Mai%20Anh&flag=a%2Bb\n"));
            check("decodedQuery",
                    response.contains("query=name=Mai Anh&flag=a+b\n"));
            check("headerCaseInsensitive",
                    response.contains("traceFirst=alpha\n"));
            check("duplicateHeaderValues",
                    response.contains("traceCount=2\n"));
            check("missingHeaderNull",
                    response.contains("missingHeader=true\n"));
            check("getRequestBodySameStream",
                    response.contains("sameBodyStream=true\n"));
            check("unicodeBodyRoundTrip",
                    response.contains("body=" + TEXT));
            check("bodyBytesUtf8NotChars",
                    response.contains("bodyBytes="
                            + TEXT.getBytes(StandardCharsets.UTF_8).length
                            + "\n"));
            check("responseUtf8ContentType",
                    result.headers().firstValue("Content-Type")
                            .orElse("").equalsIgnoreCase("text/plain; charset=UTF-8"));
            check("responseNoSniff",
                    result.headers().firstValue("X-Content-Type-Options")
                            .orElse("").equals("nosniff"));

            HttpResponse<String> health = send(client, HttpRequest
                    .newBuilder(URI.create(base + "/health?probe=true"))
                    .GET().build());
            check("healthStatus200", health.statusCode() == 200);
            check("healthGetMethod", health.body().contains("health=GET\n"));
            check("healthRawQuery",
                    health.body().contains("rawQuery=probe=true"));

            HttpResponse<String> wrongMethod = send(client, HttpRequest
                    .newBuilder(URI.create(base + "/api/echo/item"))
                    .GET().build());
            check("wrongMethod405", wrongMethod.statusCode() == 405);
            check("allowPost", wrongMethod.headers()
                    .firstValue("Allow").orElse("").equals("POST"));

            HttpResponse<String> healthPost = send(client, HttpRequest
                    .newBuilder(URI.create(base + "/health"))
                    .POST(HttpRequest.BodyPublishers.noBody()).build());
            check("healthPost405", healthPost.statusCode() == 405);
            check("healthAllowsGet", healthPost.headers()
                    .firstValue("Allow").orElse("").equals("GET"));

            HttpResponse<String> notFound = send(client, HttpRequest
                    .newBuilder(URI.create(base + "/unknown"))
                    .GET().build());
            check("unknownPath404", notFound.statusCode() == 404);

            HttpResponse<String> badType = send(client, HttpRequest.newBuilder(
                            URI.create(base + "/api/echo/item"))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString("{}"))
                    .build());
            check("unsupportedMedia415", badType.statusCode() == 415);

            HttpResponse<String> noType = send(client, HttpRequest.newBuilder(
                            URI.create(base + "/api/echo/item"))
                    .POST(HttpRequest.BodyPublishers.ofString("ABC"))
                    .build());
            check("missingMedia415", noType.statusCode() == 415);

            byte[] invalidUtf8 = {(byte) 0xc3, (byte) 0x28};
            HttpResponse<String> invalid = send(client, HttpRequest.newBuilder(
                            URI.create(base + "/api/echo/item"))
                    .header("Content-Type", "text/plain")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(invalidUtf8))
                    .build());
            check("invalidUtf8Rejected400", invalid.statusCode() == 400);

            String big = "x".repeat(MAX_BODY_BYTES + 1);
            HttpResponse<String> huge = send(client, HttpRequest.newBuilder(
                            URI.create(base + "/api/echo/item"))
                    .header("Content-Type", "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofString(big))
                    .build());
            check("oversizedBody413", huge.statusCode() == 413);

            String exact = "y".repeat(MAX_BODY_BYTES);
            HttpResponse<String> boundary = send(client, HttpRequest.newBuilder(
                            URI.create(base + "/api/echo/item"))
                    .header("Content-Type", "text/plain")
                    .POST(HttpRequest.BodyPublishers.ofString(exact))
                    .build());
            check("exactLimitAccepted", boundary.statusCode() == 200);
            check("exactLimitByteCount",
                    boundary.body().contains("bodyBytes=4096\n"));

            HttpResponse<String> empty = send(client, HttpRequest.newBuilder(
                            URI.create(base + "/api/echo/item"))
                    .header("Content-Type", "text/plain")
                    .POST(HttpRequest.BodyPublishers.noBody())
                    .build());
            check("emptyBodyAccepted", empty.statusCode() == 200);
            check("emptyBodyCountZero", empty.body().contains("bodyBytes=0\n"));
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

### 10.2. Biên dịch và chạy

Tại thư mục chứa file `MiniHttpRequestDemo.java`:

```bash
javac --release 17 MiniHttpRequestDemo.java
java MiniHttpRequestDemo
```

Không cần thêm `--add-exports`, không dùng class `sun.*`. Trên JDK 17+ tiêu chuẩn có module `jdk.httpserver`, ví dụ trên class path biên dịch và chạy thành công. Nếu ứng dụng dùng named modules, khai báo `requires jdk.httpserver;` và `requires java.net.http;`. Nếu môi trường CI hạn chế loopback socket, integration test có thể bị chặn bởi sandbox, không phải lỗi cú pháp Java.

### 10.3. Stdout chính xác đã chạy trên OpenJDK 24

```text
ephemeralPortAssigned=true
postStatus200=true
methodRead=true
rawPathPreserved=true
decodedPath=true
rawQueryPreserved=true
decodedQuery=true
headerCaseInsensitive=true
duplicateHeaderValues=true
missingHeaderNull=true
getRequestBodySameStream=true
unicodeBodyRoundTrip=true
bodyBytesUtf8NotChars=true
responseUtf8ContentType=true
responseNoSniff=true
healthStatus200=true
healthGetMethod=true
healthRawQuery=true
wrongMethod405=true
allowPost=true
healthPost405=true
healthAllowsGet=true
unknownPath404=true
unsupportedMedia415=true
missingMedia415=true
invalidUtf8Rejected400=true
oversizedBody413=true
exactLimitAccepted=true
exactLimitByteCount=true
emptyBodyAccepted=true
emptyBodyCountZero=true
```

**31/31 assertions PASS.** Mỗi dòng chỉ in khi điều kiện đúng; method `check` ném `AssertionError` nếu có test sai. Chương trình đã được biên dịch bằng `javac --release 17` và thực thi thật trên **OpenJDK 24** qua loopback socket, không phải stdout giả lập hay số liệu được tự suy đoán. Port do OS cấp là ngẫu nhiên nên cố tình không in số port để stdout ổn định.

### 10.4. Giải thích nhóm kiểm thử

| Assertion | Kiểm chứng |
| --- | --- |
| `ephemeralPortAssigned` | Server thật được bind đến một port lớn hơn 0 |
| `postStatus200` | POST hợp lệ được xử lý thành công |
| `methodRead` | Handler nhận đúng `POST` |
| `rawPathPreserved` | URI raw path vẫn chứa `%C4%91` |
| `decodedPath` | `getPath` trả ký tự Unicode `đ` |
| `rawQueryPreserved` | Query raw giữ `%20` và `%2B` |
| `decodedQuery` | URI query decode thành `Mai Anh` và `a+b` |
| `headerCaseInsensitive` | `getFirst` tìm được `X-Trace` dù dùng mixed-case key |
| `duplicateHeaderValues` | `Headers.get` có hai values cho X-Trace |
| `missingHeaderNull` | Header vắng mặt trả null |
| `getRequestBodySameStream` | Hai lần gọi getRequestBody trả đúng cùng stream object |
| `unicodeBodyRoundTrip` | Body tiếng Việt/emoji được đọc và trả đúng nguyên văn |
| `bodyBytesUtf8NotChars` | Đếm **bytes UTF-8**, không dùng `String.length` |
| `responseUtf8ContentType` | Response body UTF-8 có Content-Type nhất quán |
| `responseNoSniff` | Response đặt X-Content-Type-Options |
| `healthStatus200`, `healthGetMethod` | GET /health hoạt động |
| `healthRawQuery` | Health handler đọc raw query |
| `wrongMethod405`, `allowPost` | GET tới POST endpoint bị từ chối với Allow: POST |
| `healthPost405`, `healthAllowsGet` | POST tới health bị từ chối với Allow: GET |
| `unknownPath404` | Context không tồn tại nhận HTTP 404 |
| `unsupportedMedia415` | application/json bị endpoint text/plain từ chối |
| `missingMedia415` | Endpoint buộc Content-Type, không có trả 415 |
| `invalidUtf8Rejected400` | CharsetDecoder REPORT từ chối byte UTF-8 sai |
| `oversizedBody413` | Body 4097 bytes vượt limit 4096 |
| `exactLimitAccepted`, `exactLimitByteCount` | Body đúng 4096 bytes vẫn được chấp nhận |
| `emptyBodyAccepted`, `emptyBodyCountZero` | POST text/plain có body rỗng vẫn xử lý hợp lệ |

**Không suy rộng:** 31 tests chứng minh behavior trong môi trường Java/HTTP client/server được kiểm thử. Chúng không kiểm tra TLS, authentication, proxy traversal, max concurrent connections, header count limits, multipart parser, JSON validation hoặc deployment Internet public. Đó là các chính sách riêng bắt buộc với hệ thống thật.

## 11. Đọc request body đúng trách nhiệm tài nguyên

### 11.1. Stream có lifecycle gắn với exchange

`HttpExchange.getRequestBody()` cung cấp InputStream của **một request**. Đọc/đóng stream theo exchange, không lưu lại sang worker khác sau khi handler kết thúc. Javadoc khuyến nghị tiêu thụ toàn bộ request body trước khi đóng để connection có cơ hội được tái sử dụng, nhưng nếu body quá lớn hoặc client bất thường, app cần **từ chối sớm và giải phóng tài nguyên** thay vì đọc vô hạn.

### 11.2. Chunked requests

HTTP/1.1 có framing với `Transfer-Encoding: chunked`. Handler không phải tự đọc các dòng kích thước chunk từ InputStream; HTTP server implementation đã xử lý framing. Dữ liệu mà app nhận qua `getRequestBody()` là body content stream. Phần mềm cũng phải kiểm soát end-of-body, timeouts và lỗi client ngắt kết nối.

**Đừng** đọc từ socket TCP trực tiếp ở tầng ứng dụng nếu đã dùng `HttpExchange`, vì sẽ dễ tạo hai HTTP parsers có logic mâu thuẫn.

### 11.3. Request stream có thể lỗi giữa chừng

`readNBytes` có thể ném `IOException` nếu client reset connection, timeout hoặc transport lỗi. Sau khi response đã bắt đầu, việc trả một status khác có thể không còn khả thi. Do đó phân tách nhận/validate body với xuất response và xử lý I/O exceptions ở tầng server/monitoring.

### 11.4. Không đọc lần thứ hai như một stream mới

`getRequestBody()` nhiều lần trả cùng object. Nếu bạn đã tiêu thụ 100 bytes rồi gọi lại, đó **không** reset offset. Nếu cần xử lý nhiều lượt và body nhỏ, có thể lưu `byte[]` sau khi đã giới hạn bytes; nếu body lớn, thiết kế streaming parser với một pass thay vì cache tùy tiện.

## 12. Bảo mật khi đọc method, URI, header và body

| Ranh giới | Nguy cơ | Hướng xử lý |
| --- | --- | --- |
| Method | Endpoint nhận method ngoài ý muốn | Allowlist method theo route, trả 405 + Allow |
| URI raw/decoded path | Encoded slash, traversal, double decode | Decode đúng một lần, validate segments, canonical containment |
| Query | Duplicate params, encoded values, secrets trong logs | Parser/size limit, privacy policy |
| Headers | Spoofed roles/forwarded host, nhiều giá trị | Trust proxy đúng scope, validate duplicates |
| Content-Length | Thiếu/sai/khác với proxy framing | Giới hạn bytes thật, reverse-proxy hardening |
| Content-Type | Nhầm binary/JSON thành UTF-8 plain text | Media type allowlist, charset policy |
| Body | Memory exhaustion, slow uploads | Body byte limit, timeouts, concurrency quotas |
| Text decoding | Invalid UTF-8 silently replaced | CharsetDecoder REPORT |
| Response | Data leak, MIME sniff, reflection | Giới hạn echo/log, Content-Type, nosniff |
| Network | Exposed test server ngoài mạng | Bind loopback cho demo; HTTPS/auth/ACL cho public |
| Thread pool | Blocking reads giữ threads | Bounded concurrency, timeouts, metrics |
| Request logging | Tokens/personal info trong path/headers/body | Redaction, structured logging, retention policy |

### 12.1. Không tin `X-Forwarded-*` vô điều kiện

Client có thể tự gửi `X-Forwarded-For`, `X-Forwarded-Host` hoặc `Forwarded`. Nếu ứng dụng deploy sau proxy, phải xác định proxy đáng tin và cho phép proxy **ghi đè/xóa** các headers do client cung cấp. Không dùng các giá trị đó để quyết định quyền hoặc redirect khi không có trust boundary.

### 12.2. Không tin `Host` để xác định quyền

Host header có thể bị gửi theo ý client, và server behind load balancer có routing riêng. Nếu backend dùng Host để xác định tenant, phải có validation với danh sách domains/tenants đã cấu hình và bảo đảm gateway kiểm soát header. Không dùng raw Host cho reset-password links hoặc absolute redirects.

### 12.3. Hạn chế query/body logs

Request có thể chứa email, token, auth credentials, số tài khoản, file nhạy cảm. Đừng log toàn bộ URI hoặc body một cách mặc định ở production. Nếu cần debugging, có thể log method, **route template**, status code, duration và correlation ID không nhạy cảm.

### 12.4. HTTP request smuggling không được sửa bằng string parsing đơn giản

Khi client, reverse proxy và backend không thống nhất cách xử lý `Content-Length` và `Transfer-Encoding`, có thể xảy ra HTTP desynchronization. Handler JDK được cung cấp **parsed request**; ứng dụng không nên tự tái diễn giải framing bằng vài phép tách chuỗi. Cần chọn HTTP server/proxy stacks đã được cập nhật, cấu hình chúng nhất quán, chặn request framing ambiguous và kiểm thử hạ tầng.

### 12.5. Content-type sniffing và injection

Nếu phản hồi echo chứa text người dùng, hãy dùng đúng `text/plain; charset=UTF-8` và `X-Content-Type-Options: nosniff`. Nếu render HTML, cần **output encoding phù hợp HTML context**, CSP và những kiểm soát khác — không chỉ thêm `nosniff` rồi nghĩ đã chặn mọi XSS.

### 12.6. Simple server không phải production platform

`HttpServer` có giá trị cho công cụ nhỏ và học API, nhưng một dịch vụ Internet public cần TLS và rotation, authentication, authorization, request size/time limits ở nhiều tầng, proxy/load balancer policy, observability, graceful shutdown, overload handling, HTTP protocol/security updates, và integration/regression testing. Không mặc định những tính năng đó đã có chỉ vì `HttpServer` chạy được.

## 13. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Điều chỉnh |
| --- | --- | --- |
| Chỉ đọc URI mà bỏ method | GET và POST khác semantics | `getRequestMethod` trước dispatch |
| Trả HTTP 200 cho mọi lỗi | Client không biết request đã fail | Trả status phù hợp |
| Trả 404 thay vì 405 cho method không được phép | Endpoint có tồn tại | `405` và header `Allow` |
| `getRequestURI().toString()` rồi tự cắt mọi thành phần | Có encoding/query/authority nuances | Dùng `URI.getRawPath/getPath/getRawQuery` |
| Decode URI path hai lần | Có thể tạo traversal và segment confusion | Decode đúng một lần, validate path |
| Dùng URLDecoder cho mọi URL path | `+` semantics của form khác URI path | Chỉ dùng đúng form context |
| Cho rằng query đã là map | `URI` không parse key/value | Parser query với duplicate policy |
| Dùng Host/X-Forwarded-* làm auth bằng chứng | Client có thể giả mạo | Trusted proxy + allowlist |
| Cho rằng header names case-sensitive | HTTP fields không như vậy | `Headers` hỗ trợ case-insensitive |
| Dùng getFirst cho security header có duplicates mơ hồ | Có thể bỏ qua giá trị khác | Validate count/value theo header semantics |
| Sửa request Headers | Immutable | Sửa response Headers nếu cần |
| Coi body là Java String sẵn có | InputStream chứa bytes | Xác định Content-Type/charset trước |
| `readAllBytes()` với untrusted input | OOM với payload lớn | Bounded reads hoặc streaming parser |
| Dựa duy nhất vào Content-Length | Có request framing khác/không có length | Đếm bytes thực |
| Dùng String.length để áp byte limit | UTF-8 bytes khác UTF-16 code units | Byte-size limit trên InputStream |
| `new String(bytes, UTF_8)` khi phải reject sai bytes | Có thể replace malformed input | CharsetDecoder REPORT |
| Decode JSON như text rồi coi là object validated | JSON có schema/parser riêng | JSON parser + size/depth limit |
| Nhầm text/plain với multipart/binary | Sai media type | Chọn parser theo Content-Type |
| Chỉ gửi body, không sendResponseHeaders | Sai vòng đời HttpExchange | Headers → sendResponseHeaders → body |
| Quên đóng OutputStream/exchange | Leak resources, connection không kết thúc | try-with-resources |
| Cho rằng responseLength=0 luôn nghĩa empty | HTTP server dùng chunked behavior | Đọc contract response length |
| Gửi data người dùng như HTML | Rủi ro XSS/context injection | Đúng Content-Type + encoding |
| Mở server demo trên mọi interface | Lộ endpoint không auth | Bind loopback |
| Không shutdown ExecutorService | App có thể giữ threads sau server.stop | Shutdown thread pool do app sở hữu |
| Không test malformed UTF-8/body lớn | Dễ bỏ qua lỗi thực tế | Integration test HTTP 400/413 |

## 14. Ma trận kiểm thử bổ sung cho hệ thống thật

| Test | Kỳ vọng |
| --- | --- |
| Method đúng và sai | 200, 405 + Allow chính xác |
| Unknown route | 404 |
| URI có percent-encoded Unicode | getRawPath/getPath đúng |
| URI có `%2B` và `+` | Không nhầm URI decode với form decode |
| URI dot-segments/encoded slash | Không traversal/authorization bypass |
| Query trùng keys hoặc dài | Parser policy có giới hạn |
| Header key khác hoa/thường | Lookup như nhau |
| Header lặp | Đúng multi-value policy |
| Thiếu optional header | getFirst trả null |
| Header bảo mật bị lặp/mâu thuẫn | Reject hoặc xử lý theo spec, không tùy tiện first/last |
| Content-Type thiếu/sai | 415 theo contract endpoint |
| UTF-8 hợp lệ chứa tiếng Việt/emoji | Body round-trip đúng |
| UTF-8 malformed hoặc truncated sequence | 400 |
| Body rỗng | Theo contract endpoint |
| Body đúng byte limit | Được chấp nhận |
| Body >byte limit | 413, không materialize toàn bộ |
| Chunked request | Giới hạn actual body bytes hoạt động |
| Client upload cực chậm | Timeouts/resource policy hoạt động |
| Client disconnect giữa body | IOException được quản lý |
| Không có Content-Length | Không bỏ qua limit |
| HTTP framing ambiguous | Backend/proxy không desync |
| Response byte length | Ghi chính xác fixed-length |
| HEAD/OPTIONS nếu được hỗ trợ | Tuân thủ semantics, không body sai |
| Request logging | Không lộ Authorization/cookies/body |
| TLS, auth, reverse proxy | Security boundaries đúng |
| Concurrent requests | Không data races/leak/executor starvation |
| Shutdown | Server và executor dừng, ports giải phóng |

Bộ fixture 31 checks chỉ kiểm tra các trường hợp đã triển khai; những hàng khác trong ma trận là đề xuất integration tests khi triển khai production, **không phải kết quả đã kiểm thử**.

## 15. Bài tập thực hành

### Bài 1 — Thêm method PUT

Cho `/api/echo/` chấp nhận `PUT` bên cạnh `POST`. Sửa method allowlist và header `Allow: POST, PUT`. Thêm một `HttpClient` request `PUT` với body UTF-8 và test status 200; đừng đổi tên method theo query parameter.

### Bài 2 — Trả raw query khi vắng mặt

Gửi `POST /api/echo/item` không có `?`. Quan sát `uri.getRawQuery() == null`. Sửa response để dùng biểu diễn riêng cho null nếu cần, nhưng không đánh đồng “không có query” với “query rỗng” nếu contract phân biệt.

### Bài 3 — Tách query form parameters

Nhận `?x=a%2Bb&y=Mai+Anh` trong một API định nghĩa dữ liệu là `application/x-www-form-urlencoded`. Viết parser giữ raw query, split theo `&`, tách first `=`, decode từng component **một lần** với UTF-8. Test duplicate keys `x=1&x=2` và invalid escapes.

### Bài 4 — Security-sensitive duplicate header

Gửi hai header custom `X-Role` khác nhau và nhận biết `getFirst` sẽ bỏ phần còn lại. Thêm rule từ chối duplicates với headers app dùng để quyết định chính sách; không bao giờ coi client-supplied X-Role là sự xác thực.

### Bài 5 — Unicode body limit

Gửi `"đ".repeat(4096)` thay vì `"y".repeat(4096)`. Đếm **bytes UTF-8** và so với limit. Tại sao `String.length()==4096` không cho biết request body được chấp nhận?

### Bài 6 — Lỗi UTF-8 truncated

Thử payload byte `0xE2 0x82` (thiếu byte cuối của một code point UTF-8) với `Content-Type: text/plain; charset=UTF-8`; kỳ vọng `400` trong fixture strict decoder.

### Bài 7 — Stream vượt hạn mức

Thay `MAX_BODY_BYTES` thành 1024. Gửi lần lượt body 1023, 1024 và 1025 bytes. Xác minh status phù hợp và app không gọi `readAllBytes` để đọc hết một request lớn.

### Bài 8 — Content-Type parameters

Mở rộng endpoint để chấp nhận quoted charset parameters theo một media type parser được kiểm thử. Không tiếp tục sử dụng `replace(" ", "")` như thể đó là parser RFC tổng quát.

### Bài 9 — Path normalization

Viết endpoint `GET /files/...` giả lập nhưng **không mở file thật**. Test `..`, `%2e%2e`, `%2F`, `%252F` và double decoding. Xác định canonical path containment policy trước khi cho truy cập file.

### Bài 10 — Streaming large body

Tạo parser xử lý các chunks qua `InputStream.read(buffer)`, đếm bytes bằng `long`, giới hạn total bytes và không giữ toàn bộ body trong memory. Test khi client ngắt truyền giữa chừng.

### Bài 11 — Response body rỗng

Thêm `HEAD /health` hoặc một endpoint trả `204`. Đọc contract `sendResponseHeaders`, phân biệt zero-length **chunked** với chế độ **không có response body**, rồi test bằng HttpClient. Không áp dụng helper `respond` hiện tại cho mọi status/method.

### Bài 12 — Concurrent requests

Gửi nhiều requests cùng lúc bằng `HttpClient.sendAsync` và đo kết quả. Chọn executor size dựa vào workload, timeouts và resource budget; nếu tăng thread count, cần đo chứ không suy đoán.

## 16. Câu hỏi tự kiểm tra

**1. Java API nào nhận một HTTP request trong server gọn?**

`com.sun.net.httpserver.HttpExchange`. Nó có `getRequestMethod`, `getRequestURI`, `getRequestHeaders` và `getRequestBody`.

**2. `HttpServer` thuộc Java module nào?**

`jdk.httpserver`, là JDK-specific module được hỗ trợ hiện nay, không phải API portable Java SE độc lập.

**3. Tại sao dùng `HttpServer.create(...,0)` với local loopback?**

Port 0 cho OS chọn ephemeral port; loopback tránh mở service demo cho máy khác.

**4. Method POST có đồng nghĩa body JSON không?**

Không. Method và media type có ý nghĩa khác nhau.

**5. `getRequestURI` trả gì?**

Một `java.net.URI`. Dùng `getRawPath/getPath/getRawQuery/getQuery` để lấy các components phù hợp.

**6. `getRawPath` và `getPath` khác gì?**

Raw path giữ percent encoding; decoded path chuyển mã URI escapes thành ký tự, ví dụ `%C4%91` thành `đ`.

**7. `URI.getQuery` có tự chuyển dấu `+` thành dấu cách không?**

Không theo quy tắc `application/x-www-form-urlencoded`. `URI` decoding và `URLDecoder` form decoding là hai ngữ cảnh khác nhau.

**8. `getRequestHeaders` có sửa được không?**

Request Headers trả immutable trong Java SE 26. Response headers thì mutable.

**9. Tên HTTP header có phân biệt hoa/thường không?**

Không. `Headers` dùng case-insensitive keys.

**10. `getFirst("X-Trace")` có cho biết tất cả giá trị không?**

Không. Nó trả giá trị đầu tiên; `get` trả danh sách values.

**11. Khi header vắng mặt `getFirst` trả gì?**

`null`.

**12. `getRequestBody` có trả String không?**

Không, nó trả `InputStream`.

**13. Vì sao gọi `getRequestBody` lần nữa không đọc lại body?**

Javadoc nói các lần gọi trả cùng InputStream. Đã tiêu thụ bytes thì stream không tự rewind.

**14. Vì sao không chỉ tin Content-Length để áp hạn mức body?**

Vì Content-Length có thể vắng mặt hoặc body có framing khác; phải giới hạn actual bytes được đọc.

**15. Cách đơn giản để biết body có lớn hơn `MAX` không?**

Đọc tối đa `MAX+1` bytes rồi kiểm tra `bytes.length>MAX`, không cần materialize toàn bộ body lớn.

**16. Java String.length có phải số HTTP body bytes không?**

Không. Java String là UTF-16 code units; UTF-8 bytes có độ dài khác.

**17. Khi bắt buộc UTF-8 hợp lệ, vì sao dùng CharsetDecoder REPORT?**

Để từ chối malformed byte sequences thay vì âm thầm thay bằng replacement characters.

**18. `415` khác `400` trong fixture ra sao?**

`415` là media type thiếu/không hỗ trợ theo contract; `400` là body UTF-8 không hợp lệ.

**19. `405` nên gửi thêm header nào?**

`Allow` với danh sách methods endpoint hỗ trợ.

**20. Khi nào `sendResponseHeaders` phải được gọi?**

Trước khi lấy/ghi response body stream, sau khi đặt response headers cần thiết.

**21. Response length 0 luôn là không body?**

Không. Với `HttpExchange`, zero-length response có ngữ nghĩa chunked; khi không có body phải dùng chế độ phù hợp theo API/HTTP status.

**22. Đóng HttpExchange có thay việc quản lý server executor không?**

Không. Exchange lifecycle và server/executor lifecycle là hai việc khác nhau.

**23. Có thể đưa Content-Type request thẳng thành response Content-Type không?**

Không nên. Response bytes phải có media type đúng với dữ liệu thật mà server ghi ra.

**24. Có thể dùng raw Host/X-Forwarded-Host làm canonical origin không?**

Không nếu không có chính sách trusted proxy và domain allowlist.

**25. `createContext("/foo")` có match `/foobar` không?**

Có thể theo prefix matching được Javadoc mô tả; cần routing/path validation phù hợp.

**26. `HttpServer` có đủ bảo mật cho Internet public không?**

Không nên suy ra vậy. Nó là server gọn; public deployment cần TLS, auth, limits, proxy, logging, monitoring và integration tests.

## Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — HttpServer](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): tạo/bind server, createContext, prefix path matching, executor, start và stop.
- [Oracle Java SE 26 — HttpExchange](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): method, URI, headers, request body, response stream, sendResponseHeaders và đóng exchange.
- [Oracle Java SE 26 — Headers](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): case-insensitive multi-valued headers, getFirst/get, immutable request headers và mutable response headers.
- [Oracle Java SE 26 — HttpHandler](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): `handle(HttpExchange)` và trách nhiệm xử lý request.
- [Oracle Java SE 26 — jdk.httpserver module](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/module-summary.html): module và các packages public của JDK HTTP server.
- [Oracle Java SE 26 — URI](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URI.html): raw vs decoded components, URI percent encoding, path/query.
- [Oracle Java SE 26 — URLDecoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLDecoder.html): form-url-encoded decoding và dấu `+`.
- [Oracle Java SE 26 — InputStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStream.html): `readNBytes`, stream lifecycle, bounded reads.
- [Oracle Java SE 26 — CharsetDecoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html): malformed input handling và `CodingErrorAction.REPORT`.
- [Oracle Java SE 26 — HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): Java HTTP client dùng trong integration tests.
- [IETF RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP methods, status codes, field semantics, media types và request/response behavior.
- [IETF RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): HTTP/1.1 message framing và các lưu ý về Content-Length/Transfer-Encoding.

**Ghi nhớ:** Với `HttpExchange`, hãy đọc **`getRequestMethod()` → `getRequestURI()` → `getRequestHeaders()` → `getRequestBody()`**, nhưng phải phân biệt từng lớp dữ liệu. Method được allowlist; URI có raw/decoded components; Headers là case-insensitive và có thể nhiều giá trị; Body là InputStream phải được **giới hạn bytes** rồi decode/parse theo Content-Type. Không double decode path, không tin security-sensitive headers tự khai, không dùng `Content-Length` làm giới hạn duy nhất. Sau validation, đặt response headers, gọi `sendResponseHeaders`, ghi/đóng response stream, đóng exchange và quản lý riêng vòng đời server. Bài học dùng API Java 17+ còn hiệu lực, không áp dụng mẹo HTTP parsing legacy.
