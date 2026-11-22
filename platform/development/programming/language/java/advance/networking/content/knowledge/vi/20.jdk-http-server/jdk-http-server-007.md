# JDK HttpServer: đóng HttpExchange, xử lý lỗi và không để client chờ phản hồi mãi

## 1. Vấn đề: handler nhận request nhưng client vẫn quay vòng chờ

Bạn đang dùng `com.sun.net.httpserver.HttpServer` để dựng một HTTP server Java 17+. Server đã nhận `GET /api`, nhưng phía `HttpClient`, `curl` hoặc trình duyệt vẫn chờ rất lâu. Có những lý do khác nhau:

- Handler chạy đến cuối mà **không gọi `sendResponseHeaders(...)`**: không có HTTP status/headers hoàn chỉnh được gửi.
- Đã gửi headers nhưng **quên viết đủ byte** theo `Content-Length` hoặc **quên đóng response stream**: client có thể chưa biết response body kết thúc, hoặc nhận truncated response / lỗi I/O.
- Exception xuất hiện trong handler và thoát ra mà **không tạo response lỗi có kiểm soát**, nên client có thể chỉ thấy đóng kết nối, lỗi mạng hoặc đợi đến timeout.
- Handler **bị kẹt khi đọc request body**, gọi database/API ngoài, chờ lock hoặc `Thread.sleep` lâu; chưa đi tới bước gửi phản hồi.
- Thread xử lý của server bị **chiếm hết**, hàng đợi executor dài hoặc upstream proxy/LB giữ kết nối lâu; request chưa được xử lý kịp.
- Code chọn sai `responseLength`: dùng `0` với ý định “không có body” trong khi JDK `HttpExchange` hiểu `0` là **chunked response**, cần đóng stream để kết thúc.
- Client không cấu hình timeout; nếu server không phản hồi/không đóng đúng, caller có thể chờ lâu hơn mức ứng dụng chấp nhận.

Đây là bài học về **vòng đời một request/response trong HTTP server nhỏ đi kèm JDK**, không phải hướng dẫn xây một ứng dụng web server framework hoàn chỉnh. Mục tiêu là làm đúng `HttpExchange`, **có phản hồi có chủ đích trên mọi đường xử lý hợp lệ và lỗi có thể dự đoán**, biết khi nào không còn được sửa HTTP status, đóng đúng tài nguyên, thiết kế deadline và tránh để client chờ vô hạn.

### 1.1. Sơ đồ một exchange

~~~text
Client                JDK HttpServer / HttpHandler
  |                              |
  | -------- request ----------> |  accept/dispatch exchange
  |                              |  đọc method, URI, headers
  |                              |  (đọc request body nếu cần)
  |                              |  validate -> service logic
  | <--- status + headers ------ |  sendResponseHeaders(...)
  | <------- body bytes -------- |  getResponseBody().write(...)
  | <------ kết thúc body -------|  close response stream / exchange
  |                              |  release resources
  |                              |
  |  Trạng thái lỗi nếu chưa có response:
  | <---- 4xx/5xx + body ------- |  error response và close
  |
  |  Nếu lỗi xảy ra SAU headers:
  | <--- có thể truncated -------|  không thể đổi status thành 500
~~~

**Quy tắc nền tảng:** một `HttpExchange` biểu diễn **một giao dịch HTTP**, gồm một request và một response; bạn cần đảm bảo nó **được kết thúc đúng cách**. `HttpExchange.close()` đóng request body stream và response body stream nếu chưa đóng. Nó không phải một lệnh “tự động sinh HTTP 200/500”, vì vậy **đừng chỉ gọi `close()` mà quên gửi response hợp lệ**.

## 2. Các lớp và vai trò trong module `jdk.httpserver`

JDK 17 cung cấp module `jdk.httpserver`, package `com.sun.net.httpserver`. Những thành phần chính:

| Thành phần | Nhiệm vụ |
| --- | --- |
| `HttpServer` | Bind địa chỉ/cổng, tạo URL contexts, dùng executor để xử lý HTTP requests, start/stop |
| `HttpHandler` | Callback `handle(HttpExchange)` xử lý **một exchange** |
| `HttpExchange` | Chứa method, URI, request headers/body và response headers/body |
| `HttpContext` | Ánh xạ đường dẫn URL vào handler và cấu hình filters |
| `Headers` | Map của HTTP headers, có `getFirst`/`set` |
| `Filter` | Can thiệp request/response theo chuỗi filter, cũng phải tuân thủ response lifecycle |
| `HttpsServer` | HTTP server sử dụng TLS, cần `HttpsConfigurator` và cấu hình certificate/trust phù hợp |

Đây là API HTTP server **nhẹ** để học, test, service nhỏ hoặc môi trường được kiểm soát. Nó **không tự mang theo** routing framework đầy đủ, authentication/authorization, multipart handling, body size quotas, rate limiting, distributed tracing, JSON serialization, transactional persistence hay endpoint security production-grade.

Ví dụ dựng server:

~~~java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8080), 0);

server.createContext("/api", exchange -> {
    // Xử lý một request, gửi đúng response, luôn kết thúc exchange.
});

server.start();
~~~

Đây là **đoạn minh họa**, cần imports `com.sun.net.httpserver.*` và `java.net.*`; chạy trên máy có port 8080 khả dụng. `start()` mở thread nền để xử lý connections. Không có chuyện mỗi handler được tự gắn một timeout chỉ nhờ dòng `createContext`.

### 2.1. Một exchange ≠ một TCP connection

HTTP/1.1 có thể **reuse connection** cho nhiều request theo cơ chế keep-alive. Nhưng mỗi request/response riêng có một `HttpExchange`. Handler phải hoàn thành exchange hiện tại trước khi client có thể tiếp tục đọc response và sử dụng lại connection an toàn.

Nếu request body chưa đọc hết, JDK có thể cố đọc/bỏ một lượng dữ liệu khi đóng stream, nhưng theo tài liệu chính thức việc **không tiêu thụ hết request body có thể khiến TCP connection không dùng lại được**. Không có bảo đảm đóng exchange sẽ giữ keep-alive sau mọi tình huống.

## 3. Vòng đời chuẩn của `HttpExchange`

Tài liệu JDK 17 mô tả luồng thông thường:

1. `exchange.getRequestMethod()`: xác định phương thức HTTP.
2. `exchange.getRequestURI()`, `getRequestHeaders()`: đọc đường dẫn và metadata.
3. `exchange.getRequestBody()`: đọc body nếu cần; **quản lý giới hạn kích thước/thời gian** và đóng.
4. `exchange.getResponseHeaders()`: thiết lập các header phù hợp **trước khi commit response**.
5. `exchange.sendResponseHeaders(statusCode, responseLength)`: **bắt đầu gửi** status và headers; khi đã gửi không thể thay status theo ý.
6. `exchange.getResponseBody()`: ghi đúng byte nếu có response body.
7. **Đóng response stream và exchange** (try-with-resources hoặc `finally`); cleanup các tài nguyên ngoài exchange.

~~~java
static void hello(HttpExchange exchange) throws IOException {
    try (exchange) {
        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);

        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(200, bytes.length);

        try (OutputStream body = exchange.getResponseBody()) {
            body.write(bytes);
        }
    }
}
~~~

Đoạn trên là **phương thức bên trong class**, cần imports `HttpExchange`, `IOException`, `OutputStream`, `StandardCharsets`. Đối với `GET` không có request body đáng kể, đây là mẫu nhỏ đúng: set headers, commit status/length, ghi **đúng số bytes**, đóng stream và exchange.

**Không cần tự gọi `close()` thêm lần nữa** sau `try (exchange)`; Java sẽ gọi khi rời block kể cả do `return` hoặc exception. Khi response stream đã đóng riêng bên trong `try`, `exchange.close()` cũng kiểm tra và đóng các stream còn lại. Nếu tự quản lý `close()` bằng `finally` thay vì try-with-resources, cũng phải bảo đảm đường thành công và thất bại đều đi qua cleanup.

### 3.1. Trình tự nào là sai?

~~~java
// SAI: body trước khi gửi status/header.
OutputStream body = exchange.getResponseBody();
body.write("hello".getBytes(StandardCharsets.UTF_8));
exchange.sendResponseHeaders(200, 5);
~~~

`getResponseBody()` phải được dùng **sau** `sendResponseHeaders(...)` theo API. Nếu đảo thứ tự, bạn có thể gặp lỗi/trạng thái không hợp lệ; tránh phụ thuộc implementation details.

~~~java
// SAI: return khi chưa có HTTP response.
if (invalidInput) {
    return;
}
~~~

Một `HttpHandler` tự kết thúc mà không gửi response hợp lệ có thể khiến client nhận lỗi connection hoặc đợi tới timeout, chứ **không tự có `400 Bad Request`**. Nếu `invalidInput` có thể được xác định, hãy **gửi 400 đúng cách** rồi đóng exchange.

~~~java
// SAI: gửi headers hai lần trên cùng exchange.
exchange.sendResponseHeaders(200, 5);
exchange.sendResponseHeaders(500, 0);
~~~

Không thể “sửa” response đã bắt đầu như vậy; `sendResponseHeaders` sau lần commit có thể ném `IOException`. Chỉ có **một response status/header commit** trên một exchange.

## 4. Tham số `responseLength`: ba trường hợp phải nhớ chính xác

Đây là một trong những điểm quan trọng nhất của `HttpExchange`:

| Gọi | Ý nghĩa theo JDK 17 | Việc cần làm |
| --- | --- | --- |
| `sendResponseHeaders(200, n)`, **n > 0** | Fixed-length response body, đúng **n bytes** | Viết **chính xác n byte**, đóng output |
| `sendResponseHeaders(200, 0)` | **Chunked transfer coding** cho response body với kích thước không khai báo trước | Có thể viết số byte tùy ý; phải **đóng output** để kết thúc chunked body |
| `sendResponseHeaders(204, -1)` | **Không có response body** | Không viết body; vẫn kết thúc exchange/streams |

**Sai lầm rất thường gặp:** “0 nghĩa là trả body rỗng” — **không đúng** trong API này. Với `HttpExchange.sendResponseHeaders`, **0 kích hoạt chunked response**, chứ không phải một response không có body đã được kết thúc. Muốn **không gửi body**, dùng `-1`; các status như **204 No Content** và **304 Not Modified**, cũng như phản hồi HEAD, phải tôn trọng semantics no-body của HTTP.

### 4.1. Fixed-length: đếm **byte**, không đếm ký tự Java

~~~java
String message = "Xin chào";
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);

exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.sendResponseHeaders(200, bytes.length);

try (OutputStream out = exchange.getResponseBody()) {
    out.write(bytes);
}
~~~

`"Xin chào"` có **8 UTF-16 code units** nhưng **9 byte UTF-8**. Vì `responseLength` là số **byte trên wire**, không được dùng `message.length()` để khai báo độ dài. Nếu khai ít byte hơn rồi gửi nhiều, `write` có thể ném `IOException`; nếu khai nhiều hơn số thật rồi đóng, `close` có thể ném `IOException`. Trong cả hai trường hợp, JDK có thể **abort exchange và đóng TCP connection**, khiến client báo truncated response chứ không tự có 500.

### 4.2. Chunked: dùng 0 khi không biết kích thước trước

~~~java
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.sendResponseHeaders(200, 0);

try (OutputStream out = exchange.getResponseBody()) {
    out.write("part-1\n".getBytes(StandardCharsets.UTF_8));
    out.write("part-2\n".getBytes(StandardCharsets.UTF_8));
} // Đóng output để gửi điểm kết thúc chunked response.
~~~

Đây là **đoạn minh họa** trong handler. `sendResponseHeaders(..., 0)` cho phép body có kích thước chưa biết trước trong HTTP/1.1, phù hợp một số response streaming. Nhưng nếu stream bị bỏ quên hoặc generator không kết thúc, **client có thể tiếp tục chờ body**. Với stream dài hạn được thiết kế có chủ đích như SSE, cần protocol/timeout/cancel riêng; đừng dùng chunked để che giấu việc handler không có đường hoàn tất.

### 4.3. Không có body: dùng -1

~~~java
try (exchange) {
    exchange.sendResponseHeaders(204, -1);
}
~~~

Response `204 No Content` **không gửi representation body**. `-1` là lựa chọn phù hợp. Đừng gửi `Content-Type: application/json` và body `{}` với 204 rồi mong client nhận nội dung; 204 là status không mang body. `304 Not Modified` cũng là no-body response. Với `HEAD`, server phải thực hiện semantics HTTP HEAD (metadata tương ứng với GET, **không gửi message body**); hãy dùng lựa chọn length/headers phù hợp với JDK và test trực tiếp.

### 4.4. “Đã gọi sendResponseHeaders” vẫn có thể thất bại

`sendResponseHeaders` có thể ném `IOException` khi header đã gửi hoặc lỗi I/O xảy ra. Để bảo vệ chống gửi hai phản hồi, một `Reply` wrapper có thể đánh dấu **đã bắt đầu commit trước khi gọi API**. Cách này **bảo thủ**: ngay cả khi header write thất bại giữa chừng, code sẽ không thử phát một `500` thứ hai lên cùng socket không rõ trạng thái.

## 5. Vì sao phải đóng response body và toàn bộ exchange?

### 5.1. Đóng stream là một phần protocol, không chỉ tiết kiệm RAM

Khi chọn fixed-length, server cần gửi đủ số byte. Khi chọn chunked, điểm kết thúc body thường phụ thuộc việc **đóng response stream**, bởi đó là lúc implementation kết thúc framing. Nếu quên đóng output, client có thể chưa biết body đã xong; connection không được tái sử dụng an toàn và tài nguyên server có thể bị giữ lâu.

Theo JDK 17, `HttpExchange.close()` đóng **request InputStream trước, rồi response OutputStream** nếu chúng chưa đóng. Đó là cơ chế chấm dứt exchange trong mọi đường thoát. Kể cả response không có body, exchange vẫn phải được đóng đúng.

### 5.2. `try (exchange)` là guard quan trọng

~~~java
static void handler(HttpExchange exchange) {
    try (exchange) {
        // Mọi normal path phải commit response trước khi ra khỏi block.
        // Nếu xử lý lỗi trước commit: gửi response 4xx/5xx.
    }
}
~~~

Đây là **đoạn skeleton**, không phải một handler đầy đủ: nếu block không gửi status/headers thì vẫn có vấn đề ở tầng HTTP. `try-with-resources` bảo đảm cleanup khi method `return` hoặc ném exception, nhưng **không quyết định** mã HTTP phù hợp thay bạn.

### 5.3. Đóng request body khi chưa đọc hết ảnh hưởng keep-alive

`exchange.getRequestBody()` là `InputStream` có thể chứa request body. Với POST/PUT, nên đọc đúng số lượng mà giao thức và API cho phép, giới hạn size/time rồi đóng. Nếu client gửi request body lớn mà handler trả lỗi sớm (ví dụ 413) mà không tiêu thụ body, JDK có thể discard một phần khi close, **không có bảo đảm giữ kết nối để reuse**. Điều này không đồng nghĩa handler bị lỗi HTTP; nó là tradeoff quản lý kết nối.

Đừng vì muốn keep-alive mà **đọc/bỏ vô hạn** dữ liệu không đáng tin: người gửi có thể stream rất lâu, buộc thread server chờ mãi. Chấp nhận đóng connection khi body quá lớn/có dấu hiệu abuse, kèm chính sách timeouts và quotas của hạ tầng.

### 5.4. Không có “finally thần kỳ”

~~~java
try {
    doWork();
} finally {
    exchange.close();
}
~~~

Block trên đảm bảo đóng tài nguyên, **nhưng không gửi HTTP status** nếu `doWork()` ném trước khi commit. Client có thể thấy connection close/network error, không có `500`. Hãy **xử lý lỗi trước commit** và sau đó cleanup trong `finally`.

## 6. Xử lý lỗi đúng thời điểm: trước commit và sau commit

Một response có hai giai đoạn thiết yếu:

~~~text
[PRE-COMMIT]                [COMMITTED]                    [DONE]
validate -> service work -> sendResponseHeaders -> body.write -> body.close()
      |                             |
      |                             +-- Lỗi sau commit:
      |                                 không thể đổi status 200 -> 500;
      |                                 đóng stream/socket và log.
      |
      +-- Lỗi trước commit:
          có thể chọn 400/404/405/413/500/503,
          đặt headers + status + body một lần.
~~~

### 6.1. Lỗi **trước** khi gửi headers

Ví dụ database lookup ném `IllegalStateException` trước khi có response. Handler có thể catch exception, log nội bộ và gửi:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: text/plain; charset=utf-8
Cache-Control: no-store

internal-error
~~~

Không trả stack trace, SQL, API token hoặc đường dẫn filesystem cho client. **500 là lỗi phía server**, khác 400 do request không hợp lệ. Với lỗi upstream tạm thời có chủ đích, 503 có thể phù hợp và có thể kèm `Retry-After` theo policy; không tự đổi mọi runtime exception thành 503.

### 6.2. Lỗi **sau** khi gửi headers

Giả sử server đã gửi:

~~~http
HTTP/1.1 200 OK
Content-Length: 1000
~~~

Sau đó ghi được 200 byte, file I/O lỗi. **Không thể sửa status** của response đang đi thành 500, không thể gửi một response 500 thứ hai trong cùng exchange. Các lựa chọn thực tế:

- Log nguyên nhân, correlation ID, bytes đã gửi và trạng thái committed.
- Đóng stream/exchange hoặc để implementation abort connection khi fixed-length bị thiếu.
- Client nhận incomplete body, EOF, IOException hoặc mismatch length tùy transport; không bảo đảm nhận 500.
- Nếu cần không lộ partial success, phải **tính toán/kiểm tra toàn bộ output trước commit** (khi kích thước hợp lý), hoặc thiết kế protocol hỗ trợ chunk-level checksum/trailer/abort mà client hiểu.
- Nếu streaming rất dài, status có thể đã commit từ lâu; yêu cầu xử lý lỗi **ở tầng application stream** thay vì giả vờ có thể đổi HTTP status.

### 6.3. Đánh dấu commit bảo thủ

Trong helper response, đặt `committed=true` **ngay trước** `sendResponseHeaders(...)`; nếu call gặp lỗi I/O giữa chừng, ta **không thử gửi status khác** vì không biết đã có bao nhiêu byte header ra mạng.

~~~java
void send(int status, byte[] bytes) throws IOException {
    if (committed) {
        throw new IllegalStateException("Already committed");
    }
    committed = true;
    exchange.sendResponseHeaders(status, bytes.length);
    try (OutputStream out = exchange.getResponseBody()) {
        out.write(bytes);
    }
}
~~~

Đây là đoạn minh họa (chỉ đúng khi `bytes.length > 0`); class runnable đầy đủ bên dưới phân biệt no-body `-1`. Nếu `write` hoặc `close` ném lỗi, trạng thái committed vẫn đúng. **Không gọi `sendResponseHeaders(500, ...)` lần nữa**.

### 6.4. Xử lý `IOException` khi client đã rời đi

Nếu client timeout, đóng tab, mất Wi-Fi hoặc hủy request, `OutputStream.write()` có thể ném `IOException`. Lúc đó không nhất thiết có client nào còn đọc được `500`; điều hợp lý là **đóng tài nguyên, ghi log mức phù hợp và cập nhật metrics**. Không tạo vòng lặp vô hạn cố “gửi lỗi về cho client” đã bỏ đi.

## 7. Mã trạng thái nên chọn khi xử lý request

| Tình huống | Status thường phù hợp | Ghi chú |
| --- | --- | --- |
| GET thành công, có body | **200 OK** | Gửi Content-Type và đúng bytes |
| Request có dữ liệu đầu vào sai | **400 Bad Request** | Không phải mọi lỗi Java đều là 400 |
| Resource không tồn tại | **404 Not Found** | Có thể thêm error representation |
| Method không được hỗ trợ tại endpoint | **405 Method Not Allowed** | Gửi `Allow` header với method được phép |
| Request body vượt quota | **413 Content Too Large** | Giới hạn bytes thực đọc, có thể phải đóng connection |
| Xảy ra lỗi logic/server ngoài dự đoán trước commit | **500 Internal Server Error** | Log nội bộ; message lỗi ngắn/generic |
| Dịch vụ tạm không thể phục vụ | **503 Service Unavailable** | Có thể có `Retry-After`, tránh dùng cho mọi lỗi |
| Thành công và không có response body | **204 No Content** | Dùng no-body `-1` |
| Client gửi request quá chậm hoặc không hoàn chỉnh | **408 Request Timeout** *nếu server có thể trả status này* | Không đồng nghĩa mọi timeout Java |
| Gateway/proxy chờ upstream quá hạn | **504 Gateway Timeout** | Thường từ intermediary/proxy, không phải mặc định JDK handler |

**Phân biệt hai loại “timeout”:** `HttpTimeoutException` phía Java client là **exception**, có thể xảy ra khi **không nhận HTTP response** nào. Nó **không phải HTTP status 408/504**. Đừng bịa một response code chỉ vì client đã hủy chờ.

### 7.1. `400` khác `500`

Nếu query `limit=abc` không parse thành số, trả 400 với giải thích an toàn là hợp lý. Nếu database driver ném exception không dự kiến, nên coi là lỗi server (500/503 tùy bản chất), không trả 400 để đổ lỗi cho client. Phân loại exception theo **nguồn và ý nghĩa**, không catch tất cả rồi dùng một status.

### 7.2. `405` cần Allow

~~~java
if (!"GET".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "GET");
    // Gửi 405 + body phù hợp và kết thúc exchange.
}
~~~

Tài liệu HTTP quy định response 405 phải có `Allow` liệt kê những methods hiện hỗ trợ. Khi chỉ hỗ trợ GET, lưu ý HTTP HEAD semantics là một vấn đề riêng; demo dưới đây cố ý giới hạn GET và trả 405 cho mọi method khác, không phải một REST framework hỗ trợ HEAD mặc định.

## 8. Ví dụ Java 17+ tự chạy: mọi đường chuẩn có phản hồi, lỗi có 500, client có timeout

Ví dụ này dùng **HttpServer** và **HttpClient** đều thuộc JDK. Server chạy trên loopback IPv4 `127.0.0.1` với cổng ngẫu nhiên (port 0), không truy cập Internet. Các routes:

- `GET /ok`: `200` với body `ok`.
- `GET /bad`: `400` với body `bad-request`.
- `GET /fail`: cố tình ném `IllegalStateException` **trước commit**, wrapper trả `500` + `internal-error`.
- `GET /missing`: `404` + `not-found`.
- `GET /empty`: `204` **không body**, dùng `-1`.
- `POST /ok`: `405` + `method-not-allowed`, header `Allow: GET`.
- `GET /slow`: cố tình chậm 1,5 giây; client đặt timeout 150 ms và nhận `HttpTimeoutException`. **Timeout này do client quyết định**, không phải server đã tự sinh status 408/504.

Handler dùng `try (exchange)`, helper `Reply` ghi response **chỉ một lần** và theo dõi flag `committed`. Server có executor riêng và dọn nó khi kết thúc chương trình. Đây là ví dụ giáo dục: response bodies rất nhỏ, routes cố định; `Executors.newFixedThreadPool` dùng queue mặc định **không giới hạn**, chưa phải cấu hình chịu tải production.

Lưu vào file **ExchangeLifecycleDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ExchangeLifecycleDemo {
    static final class Reply {
        final HttpExchange exchange;
        boolean committed;

        Reply(HttpExchange exchange) {
            this.exchange = exchange;
        }

        void text(int code, String text) throws IOException {
            if (committed) {
                throw new IllegalStateException(
                        "Response already committed");
            }

            byte[] data = text.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.getResponseHeaders().set(
                    "Cache-Control", "no-store");

            // Đặt true TRƯỚC khi thử commit để không ghi status lần 2.
            committed = true;
            exchange.sendResponseHeaders(code, data.length);

            try (OutputStream out = exchange.getResponseBody()) {
                out.write(data);
            }
        }

        void empty(int code) throws IOException {
            if (committed) {
                throw new IllegalStateException(
                        "Response already committed");
            }
            committed = true;
            exchange.sendResponseHeaders(code, -1);
        }
    }

    static void handle(HttpExchange exchange) {
        try (exchange) {
            Reply reply = new Reply(exchange);

            try {
                if (!"GET".equals(exchange.getRequestMethod())) {
                    exchange.getResponseHeaders().set(
                            "Allow", "GET");
                    reply.text(405, "method-not-allowed");
                    return;
                }

                String path = exchange.getRequestURI().getPath();
                switch (path) {
                    case "/ok" ->
                            reply.text(200, "ok");

                    case "/bad" ->
                            reply.text(400, "bad-request");

                    case "/empty" ->
                            reply.empty(204);

                    case "/fail" ->
                            throw new IllegalStateException(
                                    "simulated service failure");

                    case "/slow" -> {
                        // Chỉ dành cho test client timeout.
                        Thread.sleep(1500);
                        reply.text(200, "late");
                    }

                    default ->
                            reply.text(404, "not-found");
                }
            } catch (Exception problem) {
                // Production: ghi log an toàn problem + request ID.
                // Không gửi stack trace / secrets cho client.
                if (problem instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }

                if (!reply.committed) {
                    int status =
                            problem instanceof InterruptedException
                                    ? 503 : 500;
                    String message = status == 503
                            ? "unavailable" : "internal-error";

                    try {
                        reply.text(status, message);
                    } catch (IOException sendFailed) {
                        // Socket có thể đã bị client đóng.
                        // Không cố gửi phản hồi lần nữa.
                    }
                }

                // Sau commit: chỉ cleanup/log, không đổi status.
            }
        }
    }

    static String get(
            HttpClient client, URI base, String path) throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                    base.resolve(path))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        return response.statusCode() + " " + response.body();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        ExecutorService pool = Executors.newFixedThreadPool(4);
        server.createContext("/", ExchangeLifecycleDemo::handle);
        server.setExecutor(pool); // Bắt buộc trước start().
        server.start();

        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            System.out.println("OK: "
                    + get(client, base, "ok"));
            System.out.println("Bad: "
                    + get(client, base, "bad"));
            System.out.println("Fail: "
                    + get(client, base, "fail"));
            System.out.println("Missing: "
                    + get(client, base, "missing"));

            HttpResponse<String> empty = client.send(
                    HttpRequest.newBuilder(
                            base.resolve("empty")).GET().build(),
                    HttpResponse.BodyHandlers.ofString());

            System.out.println("Empty: " + empty.statusCode()
                    + " body-length=" + empty.body().length());

            HttpResponse<String> method = client.send(
                    HttpRequest.newBuilder(
                            base.resolve("ok"))
                            .POST(HttpRequest.BodyPublishers.noBody())
                            .build(),
                    HttpResponse.BodyHandlers.ofString());

            System.out.println("Method: "
                    + method.statusCode() + " " + method.body());

            try {
                client.send(
                        HttpRequest.newBuilder(base.resolve("slow"))
                                .timeout(Duration.ofMillis(150))
                                .GET()
                                .build(),
                        HttpResponse.BodyHandlers.ofString());

                System.out.println("Timeout: unexpected-success");
            } catch (HttpTimeoutException expected) {
                System.out.println("Timeout: HttpTimeoutException");
            }
        } finally {
            server.stop(0);
            pool.shutdownNow();
            pool.awaitTermination(3, TimeUnit.SECONDS);
        }
    }
}
~~~

Biên dịch/chạy với **JDK 17+** có module `jdk.httpserver`:

~~~bash
javac -encoding UTF-8 ExchangeLifecycleDemo.java
java ExchangeLifecycleDemo
~~~

Nếu môi trường chạy với module graph tùy chỉnh không tự resolve `jdk.httpserver`, thêm `--add-modules jdk.httpserver` vào `javac` và `java`. Trên JDK 17 thông thường, chương trình demo đã chạy được mà không cần dependency ngoài.

**Stdout đã kiểm tra trực tiếp trên JDK 17 bằng JShell:**

~~~text
OK: 200 ok
Bad: 400 bad-request
Fail: 500 internal-error
Missing: 404 not-found
Empty: 204 body-length=0
Method: 405 method-not-allowed
Timeout: HttpTimeoutException
~~~

### 8.1. Vì sao những dòng này đúng?

1. **`OK: 200 ok`**: route gửi status 200, length chính xác 2 bytes của `ok`; stream được đóng.
2. **`Bad: 400 bad-request`**: dữ liệu đầu vào được mô phỏng là không hợp lệ, handler **chủ động** gửi 400 thay vì `return` im lặng.
3. **`Fail: 500 internal-error`**: exception ở route `/fail` được bắt trước khi response bắt đầu; helper gửi 500 và nội dung chung. Đây là ví dụ quan trọng nhất cho **tránh client treo chỉ vì handler exception**.
4. **`Missing: 404 not-found`**: đường dẫn không được định nghĩa vẫn có phản hồi kết thúc rõ ràng.
5. **`Empty: 204 body-length=0`**: dùng `sendResponseHeaders(204,-1)`, không có body. Đây là **no-body**, không phải chunked stream bỏ trống.
6. **`Method: 405 method-not-allowed`**: POST bị từ chối và server gửi `Allow: GET`; vẫn có response, không để client chờ vô hạn.
7. **`Timeout: HttpTimeoutException`**: `/slow` cố tình ngủ 1,5 giây, trong khi client chỉ đợi 150 ms. Client chấm dứt lượt chờ qua HTTP request timeout; **không có mã HTTP 408 hay 504 được server trả về**.

### 8.2. Giới hạn của demo cần hiểu rõ

- Mã `/slow` cố tình **block** một handler thread để minh họa timeout; **không** áp dụng `Thread.sleep(1500)` làm thiết kế dịch vụ thật.
- `HttpRequest.timeout(...)` ngăn client chờ không giới hạn, nhưng **không bảo đảm tác vụ server đã bị hủy**. Nếu server đang ghi database, nó có thể tiếp tục dù client đã timeout.
- Demo dùng `FixedThreadPool(4)` để minh họa lifecycle; queue mặc định của `Executors.newFixedThreadPool` **không giới hạn** và có thể tích tụ request khi tải lớn. Production cần giới hạn queue/concurrency và có overload policy.
- Demo chỉ đọc URI/method của GET; các endpoint đọc body lớn cần **giới hạn bytes**, deadline và parser an toàn.
- Khi `Reply.text(...)` đã set `committed=true` và I/O thất bại, handler **không cố sửa lỗi thành response thứ hai**. Nó đóng exchange; client có thể nhận IOException/truncated body.
- Phần `catch (Exception)` trong demo không phải framework exception mapper đầy đủ. Production cần phân loại lỗi (400/404/409/413/429/500/503), log/metrics và không nuốt sự cố nghiêm trọng.
- Kết quả timeout phụ thuộc timing/JDK/network scheduler; đường loopback với delay 1,5 giây và deadline 150 ms được kiểm tra thành công, nhưng không nên hard-code timing output cho các môi trường tải cực nặng mà không kiểm soát test clock/scheduling.

## 9. Đừng để server mắc kẹt khi đọc request body

### 9.1. `Content-Length` không phải dữ liệu có thể tin tuyệt đối

Một client ác ý hoặc bị lỗi có thể khai body lớn hơn khả năng server, gửi body chậm, bỏ dở giữa chừng hoặc không kết thúc. Nếu handler gọi:

~~~java
byte[] body = exchange.getRequestBody().readAllBytes();
~~~

mà không giới hạn byte/time, server có thể tốn rất nhiều RAM và **chờ đến khi stream kết thúc**. Với file upload hoặc request body lớn, nguy cơ cạn heap còn rõ hơn.

Một giới hạn kích thước tối thiểu:

~~~java
static byte[] readSmallBody(InputStream in, int maxBytes)
        throws IOException {
    byte[] data = in.readNBytes(maxBytes + 1);
    if (data.length > maxBytes) {
        throw new RequestTooLargeException();
    }
    return data;
}
~~~

Đây là **đoạn minh họa**, class `RequestTooLargeException` là exception ứng dụng cần định nghĩa, và `maxBytes` phải được kiểm tra để tránh overflow/tràn RAM. Khi gặp quá giới hạn, trả **413 Content Too Large** nếu chưa commit, sau đó xử lý việc đóng/drain connection theo chính sách. **`readNBytes` chỉ giới hạn số byte**, không tự áp đặt deadline: người gửi có thể gửi 1 byte/phút. Cần thêm request read timeout, proxy policies và resource quotas ở các tầng thích hợp.

### 9.2. Server đọc body tới EOF vì client không đóng

Với HTTP request chuẩn, framing/chunked/content-length do parser quản lý. Nhưng client có thể **gửi không đủ body**, khiến handler chờ hoặc I/O trả lỗi. Đừng tự tạo protocol dựa trên “client sẽ đóng TCP socket thì tôi mới biết body kết thúc” nếu HTTP framing của request đã cung cấp thông tin kích thước/điểm kết thúc.

### 9.3. Trả lỗi sớm và keep-alive

Nếu request có `Content-Length: 1000000000` vượt mức cho phép, không nên cố đọc/bỏ hết 1 GB chỉ để tái sử dụng TCP connection. Sau khi trả 413 (nếu có thể), có thể yêu cầu đóng connection bằng `Connection: close` trước commit tùy môi trường. Theo tài liệu JDK, closing exchange khi chưa đọc hết body **có thể khiến connection không reuse được**; đây có thể là kết quả chấp nhận được.

### 9.4. Streaming thay vì nạp trọn body vào RAM

Với upload thật, đọc body theo buffer giới hạn và ghi ra đích có quota; giữ bộ đếm tổng byte, deadline, checksum nếu cần và cleanup file tạm khi lỗi. Tránh giữ một mảng `byte[]` kích thước theo input tùy ý. Với multipart, dùng parser đã kiểm thử thay vì tự tìm boundary bằng `String.split(...)` trên binary payload.

## 10. Ngăn handler bị block bởi database, HTTP upstream hoặc lock

### 10.1. Mọi I/O phụ thuộc bên ngoài cần deadline

Handler có thể chờ:

- Database connection acquisition/query/transaction.
- HTTP client gọi một API khác.
- Hàng đợi nội bộ, thread pool, lock hoặc `Future.get()`.
- File I/O/network file share.
- Người dùng gửi request body rất chậm.

Chỉ đóng exchange trong `finally` **không giúp tiến trình đi tới finally** nếu thread đang block vô hạn. Phải cấu hình **timeout ở chính thao tác có thể block**, kèm total request deadline và giới hạn concurrency.

Ví dụ khi handler gọi HTTP upstream bằng JDK client:

~~~java
HttpClient upstream = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest req = HttpRequest.newBuilder(upstreamUri)
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
~~~

Đây là **mã minh họa**, cần imports `HttpClient`/`HttpRequest`, `Duration`, `URI` và biến `upstreamUri`. `connectTimeout` giới hạn giai đoạn kết nối, request timeout giới hạn request theo API; nhưng còn cần deadline chung cho xử lý/response, kiểm soát blocking body và policy retry.

### 10.2. `CompletableFuture.orTimeout` không tự hủy I/O

~~~java
CompletableFuture<String> timed =
        computeAsync()
                .orTimeout(2, TimeUnit.SECONDS);
~~~

Đây là fragment có `computeAsync` giả định. Nếu quá thời gian, future có thể kết thúc exceptionally với `TimeoutException`, **nhưng underlying blocking operation có thể vẫn tiếp tục**. Không nên giải phóng tài nguyên mà backend đang dùng hoặc ném status 503 rồi để hàng ngàn work items chạy nền vô hạn. Cần cancellation hợp lệ, bounded executor, per-operation timeouts và observability.

### 10.3. Cẩn thận với `Future.get(timeout)`

~~~java
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException timedOut) {
    future.cancel(true);
    throw timedOut;
}
~~~

Đây là **mã minh họa** trong phương thức có return type phù hợp; cancellation chỉ là yêu cầu hủy theo contract task/implementation, không bảo đảm query hoặc I/O đã dừng ngay. Nếu handler bắt timeout **trước khi commit**, nó có thể gửi 503 hoặc lỗi tương ứng. Nếu đã commit, không được đổi HTTP status.

### 10.4. Đọc request body và thời gian truyền response là hai deadline khác nhau

- **Header/read timeout:** bảo vệ thời gian client gửi request headers/body.
- **Application deadline:** bảo vệ logic phụ thuộc DB/API.
- **Response write timeout:** bảo vệ trường hợp client đọc rất chậm; JDK API không cho một công tắc tổng quát “set per-exchange write timeout” cấp cao.
- **Client request timeout:** bảo vệ người gọi HTTP; không thay thế ba deadline server.

Không có một lệnh `exchange.setTimeout(...)` chuẩn trong JDK 17 `HttpExchange` giải quyết mọi trường hợp. Các thuộc tính hệ thống dành riêng cho implementation có thể tồn tại, nhưng **không coi chúng là public per-exchange API ổn định**; dùng reverse proxy, hệ điều hành, provider/runtime phù hợp và timeout ở từng dependency.

## 11. Executor: để hàng đợi quá lớn cũng khiến client chờ

### 11.1. `HttpServer.setExecutor` trước `start`

Theo JDK 17, gọi `server.setExecutor(executor)` **trước** `server.start()`. Nếu không đặt executor, implementation mặc định sử dụng thread do `start()` tạo để chạy tasks. Một handler block lâu có thể khiến request khác bị trì hoãn.

Ví dụ:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(8);
server.setExecutor(pool);
server.start();
~~~

Mã minh họa cần imports `ExecutorService`/`Executors`. **Đừng dừng ở đây trong production**: `Executors.newFixedThreadPool` có work queue không giới hạn theo thiết kế, nên khi nhiều requests đổ vào hơn tốc độ xử lý, các tasks có thể chờ rất lâu và dùng nhiều RAM. Cần **bounded queue**, admission control, backpressure/overload response và metrics.

### 11.2. Bounded executor cần chính sách từ chối rõ ràng

Có thể dùng `ThreadPoolExecutor` với queue hữu hạn, kích thước pool định trước và `RejectedExecutionHandler` phù hợp. Nhưng từ chối task ở executor **không tự đảm bảo một HTTP 503 sẽ được gửi** nếu handler chưa được dispatch hoặc exchange không đến được application code. Cần test implementation, reverse proxy và overload architecture.

Không chọn `CallerRunsPolicy` một cách máy móc nếu nó khiến thread nhận kết nối bị chiếm bởi một handler chậm. Tùy kiến trúc, backpressure từ reverse proxy, connection limits và load shedding cấp trước handler có thể cần thiết.

### 11.3. Shutdown cũng cần biết exchange đang chạy

`server.stop(delay)` dừng listener, không nhận exchanges mới và đợi các handlers hiện tại hoàn thành trong giới hạn delay giây; sau đó đóng TCP connections. Khi `stop` đã gọi, **server object không thể khởi động lại**. Executor do bạn tạo có lifecycle riêng, cần shutdown/await termination.

Demo dùng:

~~~java
finally {
    server.stop(0);
    pool.shutdownNow();
    pool.awaitTermination(3, TimeUnit.SECONDS);
}
~~~

Đây là **thủ tục dọn demo**, không phải mẫu graceful shutdown an toàn cho mọi workload. `stop(0)` có thể cắt exchange đang hoạt động; với production, cần drain/deadline, ngừng nhận request mới trước, thông báo overload nếu cần, rồi release worker resources.

### 11.4. Thread interruption không phải HTTP status

Nếu handler bị interrupt khi đang `Thread.sleep`, Java ném `InterruptedException`. Trong ví dụ, callback khôi phục cờ interrupt rồi thử gửi 503 **nếu chưa commit và socket còn dùng được**. Trong production, nguyên nhân interrupt có thể là shutdown/cancel, cần tránh tạo side effects và dọn tài nguyên. Không cố gửi 500 sau khi server đã đóng socket.

## 12. Tổ chức một response writer giúp không quên close

Khi có nhiều handlers, nên dùng một helper tập trung:

- Nhận `status` và bytes (hoặc một nguồn streaming).
- Đặt `Content-Type` và headers **trước commit**.
- Phân biệt no-body/fixed/chunked.
- Đánh dấu `committed` trước `sendResponseHeaders`.
- Dùng `try-with-resources` khi viết output.
- Không tạo **hai responses** trên một exchange.
- Không nuốt `IOException` không có log và metrics.

Với body nhỏ biết trước, cách đơn giản nhất thường là `getBytes(UTF_8)` rồi gửi fixed length. Với body lớn hoặc chưa biết, chunked giúp stream nhưng cần deadline/close/flow control. Với response rỗng, `-1` và no-body semantics hợp lệ.

### 12.1. Tránh response writer lồng nhau

Một pattern rủi ro:

~~~java
try {
    sendJson(exchange, 200, compute());
} catch (Exception ex) {
    sendJson(exchange, 500, errorObject);
}
~~~

Nếu `sendJson(...,200,...)` **đã gọi `sendResponseHeaders`** rồi thất bại khi write, catch sẽ cố gửi 500 lần hai và gặp lỗi. Nên tách:

~~~text
validate/compute (trước commit)
      |
      +-- fail -> send error một lần
      |
      +-- success -> begin response một lần
                        |
                        +-- write fail -> cleanup/log only
~~~

Nếu cần streamed body, đôi khi không thể tính xong trước commit; khi ấy **không cố phát status mới** sau lỗi.

### 12.2. Ghi lỗi khi serialization bị ném

Với JSON object nhỏ, serialize/validate trước khi commit để nếu lỗi vẫn có thể gửi `500`. Đừng viết nửa JSON rồi mới gọi những getter/serializer có thể throw không dự đoán; client có thể nhận JSON thiếu ký tự trong một response 200.

Với response stream lớn, có thể dùng format message có checksum/sequence hoặc cung cấp endpoint lấy lại từ offset theo application contract, thay vì tuyên bố “gửi 200 có nghĩa mọi byte chắc chắn đã tới client”.

## 13. Filter chain và ngoại lệ trước handler

`HttpServer` hỗ trợ `Filter` cho logging/auth/metrics. Nếu filter ném exception **trước khi gọi handler**, phần `try(exchange)` trong handler có thể **chưa từng được thực thi**. Vì vậy chính sách response/cleanup cần được thiết kế cho **toàn bộ chain**, không chỉ nội dung của một route.

Một error-boundary filter có thể bắt các lỗi chưa commit và gửi response generic, nhưng phải biết liệu downstream đã commit hay chưa. Không được giả định filter biết chính xác trạng thái commit khi nhiều component tự gọi `sendResponseHeaders`. Dùng một response abstraction chung hoặc chuẩn hóa error policy trong framework.

Filter có thể giúp ghi elapsed time và requestId, nhưng **không log Authorization, cookies hay toàn bộ body**. Đừng để logging callback ném lỗi mới rồi che mất exception ban đầu.

## 14. Keep-alive, chunked và body length: ba điểm gắn chặt nhau

### 14.1. Không đọc hết request body

Khi handler trả response mà request body còn dư, implementation có thể phải đọc/bỏ một phần để giữ TCP connection có thể phục vụ request kế tiếp. Nếu còn rất nhiều bytes chưa tiêu thụ, connection có thể không reuse. Đừng cố giữ keep-alive bằng cách block đọc một input vô hạn.

### 14.2. Không kết thúc chunked response

Khi `sendResponseHeaders(status, 0)`, output stream phải đóng để đánh dấu **kết thúc body**. Nếu handler trở về không close stream/exchange, client có thể chờ chunk tiếp theo hoặc timeout. `try (exchange)` giúp dọn ngay cả khi callback return.

### 14.3. Fixed Content-Length không khớp

Nếu báo length N mà chỉ ghi ít hơn N và đóng, JDK có thể abort connection; client có thể ném IOException do premature end of fixed-length body. Đây **không phải** một response 500 mới; status 200 đã có thể nằm trên wire.

Không tự đặt `Content-Length` bằng `String.length()` hoặc kích thước buffer, đừng thêm header thủ công rồi để `sendResponseHeaders` dùng length khác. **Đặt bytes trước, lấy byte length từ payload thực**, hoặc dùng chiến lược streaming đúng contract.

### 14.4. Cần gửi body rỗng thật sự

Đừng lẫn:

~~~java
exchange.sendResponseHeaders(200, 0);  // chunked response, có thể gửi 0+ bytes
exchange.sendResponseHeaders(204, -1); // no-body response
~~~

Nếu API contract yêu cầu `200` với body rỗng, có thể dùng no-body length `-1` (và metadata phù hợp) hoặc cách truyền chunked được kết thúc chính xác, theo semantics. Điều quan trọng là **không dùng 0 với suy nghĩ nó tự kết thúc và không cần đóng stream**.

## 15. Đo và chẩn đoán “client chờ mãi” như thế nào?

### 15.1. Phân đoạn thời gian request

Một request nên có những mốc quan sát được:

~~~text
t0: socket/request accepted
t1: handler dispatched
t2: request body consumed/validated
t3: business work completed
t4: response headers committed
t5: response body finished/closed
t6: exchange closed

queue_wait    = t1 - t0
request_read  = t2 - t1
business_work = t3 - t2
response_send = t5 - t4
total         = t6 - t0
~~~

Nếu không đo được t0 ở ứng dụng, dùng timestamps từ reverse proxy hoặc server instrumentation. Phân biệt chờ ở **executor queue**, **body read**, **service work**, **response write** và **network/client** thay vì chỉ nói “Java HttpServer chậm”.

### 15.2. Bảng tìm nguyên nhân

| Triệu chứng phía client | Chỗ cần kiểm tra | Biện pháp |
| --- | --- | --- |
| Không có HTTP status, client timeout | Handler chưa `sendResponseHeaders` / bị block | Log entry/exit, deadline và bounded dependencies |
| Nhận 200 nhưng body bị thiếu/EOF | Fixed-length sai hoặc I/O lỗi sau commit | Byte length chính xác, close, log bytes sent |
| Response chunked không kết thúc | Không đóng response stream | `try-with-resources` và close exchange |
| Một request chậm kéo tất cả request khác | Executor mặc định hoặc thiếu concurrency | Đặt executor hợp lý, đo queue wait |
| Nhiều request chờ rất lâu rồi timeout | Unbounded queue/overload | Bounded queue, admission control, load shedding |
| Client POST lớn khiến handler kẹt | `readAllBytes` / chờ EOF / slow client | Body size/time limits, quota, proxy |
| Handler ném lỗi, client không thấy 500 | Không có error boundary trước commit | Catch/format error response + cleanup |
| Handler cố gửi 500 sau 200 | Response đã committed | Không retry headers; close/log |
| Sau vài request, connection không reuse | Request body chưa tiêu thụ hết | Đọc trong giới hạn hoặc đóng connection có chủ đích |
| Client timeout nhưng DB vẫn ghi | Client deadline không hủy server work | Idempotency/cancellation/transaction policy |
| Shutdown làm mất response | `stop(0)` cắt exchanges | Graceful drain và deadline |
| Response header/metadata chưa đúng | Set header sau commit | Đặt headers trước `sendResponseHeaders` |

### 15.3. Log đủ để điều tra nhưng không lộ dữ liệu

Một record an toàn có thể ghi `requestId`, method/path đã sanitize, status code (nếu đã commit), elapsed time, source error type, bytes intended/sent, client-disconnected flag. Trong trường hợp lỗi trước commit, log root cause/stack trace trên server. Không in API key, cookie, bearer token, request body cá nhân hoặc query chứa secret nguyên vẹn.

Cần phân biệt metric **status đã gửi**, **body completed**, **exchange aborted**, **client timed out**. Đừng tăng “200 success” chỉ vì `sendResponseHeaders(200, N)` đã trả về nếu body sau đó bị đứt giữa chừng.

## 16. Kiểm thử tự động những đường hoàn tất và lỗi

Ngoài demo ở mục 8, khi làm sản phẩm nên kiểm thử:

1. **GET success:** nhận đúng status/headers/body, request kết thúc.
2. **400/404/405:** status rõ ràng, response body hữu hạn, `Allow` phù hợp với 405.
3. **500 trước commit:** callback ném `RuntimeException`, client nhận 500 generic, server log nguyên nhân.
4. **Lỗi sau commit:** write partial rồi nguồn bị lỗi; verify client thấy truncated/IOException theo framing và server **không gửi 500 lần hai**.
5. **204/HEAD/304:** không có body, framing đúng, response không treo.
6. **Chunked:** biết đóng output để client nhận end-of-body.
7. **Fixed-length mismatch:** test một handler cố ý ghi thiếu/nhiều byte; client không được giả định đó là body hợp lệ.
8. **Slow request reader/writer:** test server body limits, proxy timeouts và upload quotas.
9. **Slow application dependency:** DB/API mock block rồi timeout; handler có deadline/response hoặc intentional abort.
10. **Executor saturated:** test queue limits và overload policy; không có thread/process resource leak.
11. **Client canceled:** bỏ kết nối giữa chừng, server dọn resources và không lặp vô hạn gửi error.
12. **Shutdown:** nhiều exchanges đang chạy, drain/stop theo policy và metrics.
13. **Keep-alive:** nhiều requests trên cùng TCP connection, kiểm tra không để body cũ làm hỏng exchange sau.

### 16.1. Kiểm thử với curl

Với server demo lắng nghe cổng ngẫu nhiên, URL thay đổi mỗi lần chạy; bạn có thể sửa sang một port ổn định phù hợp rồi dùng:

~~~bash
curl -i http://127.0.0.1:8080/ok
curl -i http://127.0.0.1:8080/bad
curl -i http://127.0.0.1:8080/fail
curl -i -X POST http://127.0.0.1:8080/ok
curl --max-time 1 -i http://127.0.0.1:8080/slow
~~~

Các lệnh trên là **minh họa**, chỉ chạy nếu bạn thực sự đã đổi chương trình để bind đúng port 8080 và giữ server chạy. Với server code ở mục 8, chương trình tự tạo và dừng server trên port động sau khi hoàn tất tests, nên không có một endpoint `localhost:8080` sẵn để curl gọi.

`curl --max-time` giới hạn tổng thời gian ở phía client; kết quả timeout **không chứng minh server đã cancel công việc**. Có thể đo verbose và server logs để thấy thời điểm headers được gửi.

## 17. Bài tập tình huống và đáp án

### Bài A — `return` ngay khi thiếu tham số

Handler kiểm tra `id` và phát hiện thiếu. Nó `return` mà không gọi `sendResponseHeaders`.

**Đáp án:** sai. Nếu có thể xử lý trước commit, trả `400 Bad Request` (hoặc lỗi domain phù hợp), đóng stream/exchange trong `finally`/`try`. `close` không tự thay thế việc gửi status.

### Bài B — Số byte Unicode

Server gửi `"Xin chào"` UTF-8 nhưng khai `responseLength=8` vì `String.length()==8`.

**Đáp án:** sai; dữ liệu dài **9 byte UTF-8**. Phải gọi `getBytes(StandardCharsets.UTF_8)` rồi lấy `bytes.length`. Fixed-length mismatch có thể abort exchange.

### Bài C — 0 có phải empty body?

Handler gọi `sendResponseHeaders(200, 0)`, không ghi gì và không đóng stream.

**Đáp án:** trong JDK `HttpExchange`, `0` nghĩa là chunked transfer coding, và stream cần đóng để chấm dứt body. Nếu muốn **no-body**, dùng `-1` và status semantics tương ứng; nếu dùng chunked, vẫn phải close.

### Bài D — Lỗi xảy ra sau 200 headers

Handler gửi `200` với length 1000, ghi 200 bytes rồi I/O file lỗi. Catch block gọi `sendResponseHeaders(500,...)`.

**Đáp án:** không thể đổi status đã committed. Phải cleanup/log, để stream/connection abort khi không hoàn tất đúng fixed-length; client có thể gặp truncated body, không có 500 thứ hai.

### Bài E — Client hết hạn 150 ms

Client gửi GET tới `/slow`, `HttpRequest.timeout(150 ms)`, server ngủ 1,5 giây. Client nhận `HttpTimeoutException`. Server có trả 504 không?

**Đáp án:** không. HTTP client timeout là **exception local**, không phải một status HTTP từ server. Server có thể vẫn đang xử lý request; muốn dừng backend work cần cơ chế deadline/cancellation riêng.

### Bài F — Executor hàng đợi không giới hạn

Đội dùng `newFixedThreadPool(2)`, mỗi handler block 5 giây, một phút nhận 100.000 requests.

**Đáp án:** dù chỉ có 2 threads, queue có thể phình rất lớn, khiến người gọi chờ và tốn RAM. Dùng bounded executor/admission control, per-route limits, timeouts và overload policy. Cần test cách hệ thống trả/đóng connections khi quá tải.

### Bài G — POST body không được đọc

Handler thấy `Content-Length: 500MB`, gửi 413 rồi đóng exchange. TCP connection không được reuse.

**Đáp án:** đó có thể là tradeoff đúng khi từ chối body quá lớn; không nên cố đọc/bỏ vô hạn chỉ để giữ keep-alive. Cần size/time limits, header/response phù hợp và kiểm thử proxy behavior.

### Bài H — 204 nhưng cố gửi JSON

Handler dùng `sendResponseHeaders(204, -1)` rồi ghi `{"ok":true}` vào response body.

**Đáp án:** sai semantics. 204 không có response body; nếu muốn trả JSON, dùng status có body phù hợp như 200. Với 204 phải dừng ở headers và close exchange.

### Bài I — Exception khi đóng OutputStream

Handler khai fixed length 10 bytes, nhưng chỉ ghi 3. `out.close()` ném `IOException`. Có nên catch và gửi 500?

**Đáp án:** không vì headers đã committed, không thể gửi lại status. Log partial-write error, cleanup; client có thể thấy connection aborted/incomplete response.

### Bài J — Database query không có timeout

Handler có `try (exchange)` nhưng `queryDatabase()` chờ vĩnh viễn. Có đủ bảo vệ không?

**Đáp án:** không. `try-with-resources` chỉ đóng khi **thoát block**. Cần timeout/deadline cho database và bounded concurrency. Khi lỗi xảy ra trước commit, trả 503/500 theo phân loại; nếu không thể tạo response do connection đã mất, cleanup/log.

### Bài K — Cố gắng “sửa” lỗi bằng cách đóng socket ngay

Một handler xử lý 404 bằng cách `exchange.close()`, không gửi 404 headers. Client nên hiểu đây là response 404?

**Đáp án:** không. Không có status 404 trên wire. Client có thể thấy EOF/reset/timeout. Gửi `sendResponseHeaders(404, length)` + body thích hợp rồi đóng.

### Bài L — Server stop trong khi client đang tải

`server.stop(0)` được gọi khi một exchange còn đang ghi file lớn.

**Đáp án:** stop có thể đóng connection ngay, làm client nhận incomplete body. Với production, dùng drain/deadline phù hợp và có kế hoạch retry/resume cho tải quan trọng.

### Bài M — Lỗi trong filter trước handler

Một authentication filter ném `IllegalStateException` trước khi gọi `chain.doFilter`; handler có `try(exchange)` nhưng chưa chạy.

**Đáp án:** error boundary của handler không bắt được lỗi trước nó. Filters cũng phải có cleanup/response policy hoặc dùng một abstraction/error boundary ở tầng chung, tránh để client không nhận status.

### Bài N — Viết 1 triệu logs vào response stream

Handler dùng chunked và ghi từng log line mãi mãi. Client dùng `BodyHandlers.ofString()` và chờ xong.

**Đáp án:** nếu đây là **stream có chủ ý**, client cần một streaming `BodyHandler`/protocol (ví dụ SSE) và cancellation; `ofString()` muốn tổng hợp response hoàn chỉnh nên có thể chờ mãi. Nếu không phải stream có chủ ý, phải có điểm dừng, limit và đóng output.

## 18. Checklist xử lý HTTP exchange an toàn

- [ ] Handler nào cũng **xác định rõ response status** trên đường thành công và lỗi dự đoán được?
- [ ] Tất cả nhánh trả về trước commit đều gửi 4xx/5xx phù hợp thay vì `return` im lặng?
- [ ] Đã đặt headers trước `sendResponseHeaders` và **chỉ commit một lần**?
- [ ] Phân biệt `responseLength>0` fixed byte count, `0` chunked, `-1` no-body?
- [ ] Với fixed length, có tính **UTF-8 byte length** chứ không lấy `String.length()`?
- [ ] OutputStream luôn được đóng, kể cả khi write/copy/serialization lỗi?
- [ ] `HttpExchange` được đóng bằng `try-with-resources` hoặc `finally` ở mọi đường?
- [ ] Không gửi một response status thứ hai sau khi đã committed?
- [ ] Nếu lỗi sau commit, có log partial body/abort thay vì cố gửi 500 lần nữa?
- [ ] Request body có max size, giới hạn thời gian và close/drain policy?
- [ ] Có nhận thức unread request body có thể làm TCP keep-alive không reuse?
- [ ] I/O phụ thuộc bên ngoài (DB, HTTP, disk, lock) có deadline/cancel policy?
- [ ] Client có request timeout để không chờ vô hạn, đồng thời không coi nó là server status?
- [ ] Executor được cấu hình trước `start`, queue/concurrency có giới hạn trong production?
- [ ] Có overload response/policy ở proxy và server phù hợp?
- [ ] `server.stop(delay)` và shutdown executor có kế hoạch graceful/forced đúng?
- [ ] Lỗi từ filter/auth/serialization cũng có error boundary và cleanup?
- [ ] Log requestId, status/commit state, bytes intended/sent, latency và nguyên nhân đúng, không lộ secrets?
- [ ] Đã test 200, 400, 404, 405, 413, 500, 503, 204, client timeout và partial response?
- [ ] Không dùng demo HTTP server này thay thế đầy đủ hardening của web server framework?

**Kết luận:** Với `com.sun.net.httpserver.HttpServer`, tránh client chờ mãi đòi **ba kỷ luật khác nhau**: (1) trên mỗi đường handler có thể xử lý, **commit một HTTP response đúng một lần**; (2) ghi đúng response bytes và **đóng stream/exchange** để framing kết thúc; (3) giới hạn thời gian/nguồn lực của body read, business operations, executor queue và client wait. `try(exchange)` ngăn quên đóng tài nguyên nhưng **không tự gửi status**; `sendResponseHeaders(200, 0)` không có nghĩa no-body; lỗi sau commit không thể đổi thành 500. Viết code theo ranh giới này sẽ giúp phân biệt lỗi HTTP thật, lỗi mạng và timeout, đồng thời giảm treo request và rò rỉ tài nguyên.

## 19. Tài liệu gốc nên đối chiếu

- **Oracle Java 17 — HttpExchange:** vòng đời, `getRequestBody`/`getResponseBody`, `sendResponseHeaders` (0 = chunked, -1 = no body), `close`. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- **Oracle Java 17 — HttpServer:** `setExecutor`, `start`, `stop(delay)`, contexts. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- **Oracle Java 17 — HttpHandler:** interface nhận một exchange. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html
- **Oracle Java 17 — Headers:** get/set request/response headers. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html
- **Oracle Java 17 — HttpClient và HttpRequest:** request timeout, response handling. https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **RFC 9110 — HTTP Semantics:** HTTP status codes, method semantics, body constraints. https://www.rfc-editor.org/rfc/rfc9110
- **RFC 9112 — HTTP/1.1:** framing, message body length, connections. https://www.rfc-editor.org/rfc/rfc9112

Tài liệu API JDK xác định chính xác ý nghĩa của `sendResponseHeaders` và `close`; tài liệu RFC giải thích semantics HTTP trên wire. Khi triển khai ở môi trường có proxy, TLS, nhiều clients và tải lớn, phải kiểm thử cả **server, client, reverse proxy, queue và backend dependencies** thay vì chỉ quan sát handler chạy hết một lần.