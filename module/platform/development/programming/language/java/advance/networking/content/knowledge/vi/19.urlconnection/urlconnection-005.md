# Fixed-length, chunked streaming và giới hạn gửi lại nội dung với HttpURLConnection (Java 17+)

Khi gửi một HTTP request body bằng `HttpURLConnection`, **hai chế độ streaming** giải quyết hai bài toán khác nhau: `setFixedLengthStreamingMode(long)` dành cho body có **độ dài byte đã biết chính xác**; `setChunkedStreamingMode(int)` dành cho body **chưa biết tổng độ dài** khi bắt đầu gửi. Cả hai cho phép gửi body qua `OutputStream` mà **không cần `HttpURLConnection` đệm toàn bộ body trước khi truyền**.

Sự đánh đổi rất quan trọng: **khi bật output streaming, `HttpURLConnection` không tự động xử lý được tình huống HTTP authentication hoặc redirect cần gửi lại request body** như khi còn có bản đệm nội bộ. Nếu server yêu cầu gửi lại, việc đọc phản hồi có thể ném `java.net.HttpRetryException`. Client phải quyết định theo chính sách ứng dụng: có được retry không, còn nguồn dữ liệu để mở lại không, redirect target có an toàn không, operation có idempotent không và server đã thực hiện side effect hay chưa.

Bài thuộc nhóm **URLConnection** trong **Java Advance - networking**, sử dụng API Java SE 17. Nội dung bao gồm cơ chế framing, cấu hình đúng thứ tự, khác biệt giữa UTF-8 character count và byte count, kiểm soát OutputStream, giới hạn replay, redirect 307/308, xác thực 401/407, response cleanup và hai chương trình Java 17+ dùng HTTP server loopback để kiểm chứng hành vi thực tế.

## 1. Cần phân biệt URLConnection và HttpURLConnection

`java.net.URLConnection` là API trừu tượng cho kết nối tài nguyên theo URL. `java.net.HttpURLConnection` kế thừa từ nó và bổ sung HTTP-specific operations như `setRequestMethod`, `getResponseCode`, `setFixedLengthStreamingMode` và `setChunkedStreamingMode`. Với `https://`, đối tượng thường là `HttpsURLConnection`, vốn kế thừa `HttpURLConnection` và thêm TLS.

```text
java.net.URLConnection
          |
          v
java.net.HttpURLConnection
          |
          v
javax.net.ssl.HttpsURLConnection

URI -> URL -> openConnection() -> per-request HttpURLConnection
                                      |
                            configure BEFORE connect
                                      |
                   getOutputStream() / getInputStream()
```

Ví dụ ứng dụng chỉ làm việc với HTTP(S):

```java
// Snippet minh họa, cần import URI, URL và HttpURLConnection.
HttpURLConnection conn = (HttpURLConnection)
        URI.create("https://api.example.test/upload")
                .toURL().openConnection();
```

**Không cast vô điều kiện** một kết nối `file:`, `jar:` hoặc protocol tùy chỉnh sang `HttpURLConnection`. Chỉ áp các phương thức HTTP này khi nguồn thực sự có HTTP URL connection thích hợp.

Một instance `HttpURLConnection` được dùng cho **một HTTP request**. Đừng tái sử dụng chính đối tượng ấy để gửi request khác sau khi đã đọc response. Các socket keep-alive nền có thể được Java chia sẻ ngầm giữa những instances khác nhau, nhưng **một `HttpURLConnection` không tương đương một socket vĩnh viễn**.

## 2. Ba chiến lược gửi request body và cái giá của buffering

| Cách cấu hình | Khi nào dùng | Framing HTTP/1.1 thường gặp | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- | --- |
| Không chọn streaming mode | Body nhỏ, muốn giữ logic tự động của client khi được hỗ trợ | Implementation xác định khi đã có body | Dễ dùng; implementation có thể đệm nội dung và xử lý replay | Có thể phải giữ cả body trong memory, nhất là upload lớn |
| `setFixedLengthStreamingMode(length)` | Biết **chính xác số byte** sẽ ghi | `Content-Length: length` | Không cần đệm nguyên body; server biết độ dài từ đầu | Sai byte count gây IOException; không auto replay auth/redirect |
| `setChunkedStreamingMode(chunklen)` | Chưa biết tổng byte count | `Transfer-Encoding: chunked` | Có thể tạo/gửi body dần | Server/proxy cần hỗ trợ chunked; không auto replay auth/redirect |

**“Không đệm toàn bộ body” không có nghĩa “không dùng bất kỳ buffer nào”.** Implementation vẫn có thể dùng buffer I/O, encoder TLS, TCP send buffer hoặc chunk buffer; khác biệt là không bắt buộc giữ **toàn bộ nội dung** để biết Content-Length trước khi gửi.

Không suy ra ngay lựa chọn nào “nhanh hơn X%”: throughput/latency phụ thuộc đường truyền, TLS, server, proxy, chunk size, kích thước body, garbage collection và backpressure. Mục tiêu đầu tiên là **correctness và memory bound**.

## 3. Fixed-length mode: contract chính xác theo số byte

API Java 17:

```java
void setFixedLengthStreamingMode(int contentLength);
void setFixedLengthStreamingMode(long contentLength);
```

Đây là chữ ký API để đọc, không phải một class Java độc lập. Theo `HttpURLConnection` Javadoc, fixed-length streaming cho phép gửi body mà không cần đệm toàn bộ khi đã biết độ dài. Gọi `setFixedLengthStreamingMode(long)` thường rõ ràng hơn và hỗ trợ độ dài vượt phạm vi `int`.

Với HTTP/1.1, ứng dụng hứa sẽ ghi đúng **`contentLength` byte**. Nếu ghi **nhiều hơn**, thao tác ghi có thể ném IOException; nếu **đóng OutputStream khi chưa ghi đủ**, việc đóng có thể ném IOException. Không được cho rằng Java sẽ tự thêm bytes bằng không hoặc âm thầm đổi Content-Length.

Ví dụ minh họa:

```java
// Snippet: conn chưa kết nối, body là byte[] đã chuẩn bị.
conn.setDoOutput(true);
conn.setRequestMethod("POST");
conn.setFixedLengthStreamingMode((long) body.length);
try (OutputStream output = conn.getOutputStream()) {
    output.write(body);
}
```

**`body.length` ở đây là số byte**. Không dùng số ký tự `text.length()` khi dữ liệu được mã hóa UTF-8. Nếu dữ liệu có ký tự nhiều byte, Character count và byte count khác nhau.

## 4. UTF-8: “Xin chào” là 8 ký tự nhưng 9 byte

Một lỗi rất thực tế:

```java
String text = "Xin chào";
int chars = text.length();                      // 8 UTF-16 code units
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
int contentLength = bytes.length;                // 9 byte
```

Snippet yêu cầu import `StandardCharsets`. Chữ `à` dùng nhiều byte trong UTF-8; `String.length()` đếm UTF-16 code units, không đếm bytes được gửi. Với emoji, chênh lệch có thể lớn hơn vì UTF-16 surrogate pair.

**Sai:**

```java
conn.setFixedLengthStreamingMode(text.length());
out.write(text.getBytes(StandardCharsets.UTF_8));
```

Ở ví dụ, client khai Content-Length = 8 rồi cố viết 9 byte; contract fixed-length sẽ không được đáp ứng. Không sửa bằng cách tự cắt bỏ byte thứ 9: đó có thể là một phần của ký tự Unicode, làm payload hỏng.

**Đúng:** encode ra bytes *một lần* khi body đủ nhỏ, lấy `bytes.length`. Nếu stream từ file, biết độ dài bằng `Files.size(path)` **chỉ khi file bytes được gửi nguyên trạng**; nếu còn gzip/chuyển mã/biến đổi trước khi gửi, kích thước input file có thể **không** phải kích thước output cuối.

## 5. Long-length và file lớn: tránh kiểu int tràn

`setFixedLengthStreamingMode(long)` tồn tại vì số byte upload có thể vượt giới hạn `Integer.MAX_VALUE`. Trong Java 17:

```java
// Snippet minh họa, path là Path chứa file ổn định.
long length = Files.size(path);
HttpURLConnection conn = (HttpURLConnection)
        uri.toURL().openConnection();
conn.setRequestMethod("PUT");
conn.setDoOutput(true);
conn.setFixedLengthStreamingMode(length);

try (InputStream input = Files.newInputStream(path);
     OutputStream output = conn.getOutputStream()) {
    input.transferTo(output);
}
```

Đây **không phải chương trình độc lập**: cần imports, khởi tạo `path/uri`, timeout, status/error handling và `disconnect()` trong `finally`. Ví dụ còn giả định **file không đổi trong lúc upload**. Nếu file bị cắt giữa chừng, có thể đóng output thiếu bytes; nếu file tăng, có thể ghi vượt Content-Length.

Chọn `long` không bảo đảm server chấp nhận file kích thước bất kỳ: reverse proxy, API, load balancer, storage và security policy vẫn có giới hạn upload. Đừng cố upload hàng chục GiB chỉ vì Java API nhận `long`.

## 6. Chunked mode: không cần biết tổng byte count trước

API:

```java
void setChunkedStreamingMode(int chunklen);
```

Bật chế độ này khi tổng kích thước body chưa biết, ví dụ tạo dữ liệu từ pipeline, đọc stream từ nguồn chưa có kích thước hoặc phải gửi các phần khi đang được sản xuất. Với HTTP/1.1, client dùng **chunked transfer coding** để phân tách body ở tầng giao thức thay vì gửi Content-Length của toàn request.

Ví dụ:

```java
// Snippet: conn còn chưa connected, source cung cấp dữ liệu dần.
conn.setRequestMethod("POST");
conn.setDoOutput(true);
conn.setChunkedStreamingMode(8192);

try (InputStream input = source;
     OutputStream output = conn.getOutputStream()) {
    input.transferTo(output);
}
```

**`source` và `conn` cần được khai báo**; snippet không chạy độc lập.

- Giá trị `chunklen` là **cấu hình kích thước chunk buffer/transfer**, không phải số chunks hoặc độ dài toàn body.
- `setChunkedStreamingMode(0)` dùng mặc định của implementation; không cần biết và không nên hardcode “mặc định luôn bằng 4.096 byte” vào business logic.
- Gọi `write(100)` lần này và `write(100)` lần sau **không bắt buộc** khiến server quan sát hai chunks chứa đúng 100 byte. Framing/chunk boundaries do transport handler quyết định.
- **Không tự đặt Content-Length** như thể cả fixed-length và chunked đang cùng có hiệu lực; chúng là hai mô hình framing thay thế nhau.
- Một số HTTP servers/proxies không hỗ trợ chunked upload, có thể từ chối hoặc yêu cầu `Content-Length`. Khi gặp lỗi phải điều tra capability trước khi chọn chiến lược.

## 7. Chunked transfer coding khác application message framing

Minh họa HTTP/1.1 trên wire:

```http
POST /upload HTTP/1.1
Host: api.example.test
Transfer-Encoding: chunked
Content-Type: text/plain

5
hello
6
 world
0
```

Khối trên **chỉ minh họa** cách chunk size dạng hexadecimal và end marker vận hành, không phải chuỗi raw có đầy đủ CRLF cần thiết để gửi thực tế. Server HTTP framework thường **giải mã chunked transfer coding** trước khi application handler nhận `InputStream` body.

Do đó:

- Một server-side `read(byte[])` không tương ứng “một HTTP chunk” theo wire.
- Chia `out.write` trong Java thành 2 lần **không** tự tạo 2 business records.
- Nếu nội dung là JSON/CSV/binary stream, vẫn phải dùng parser/framing của chính nội dung; chunked không tự phân định đối tượng.
- Chunked cũng **không phải** `WebSocket` fragment, `TCP` packet, HTTP/2 stream hay backpressure API.
- HTTP/2 có cơ chế DATA frames và kết thúc stream riêng, không dùng `Transfer-Encoding: chunked` theo HTTP/1.1. Đừng áp thông tin một HTTP/1.1 `HttpURLConnection` request vào mọi HTTP version/client API.

Trong chương trình chạy thật dưới đây, server đọc body thành chuỗi byte hoàn chỉnh. Nó chỉ xác minh transfer encoding và tổng số bytes, **không** giả định số chunk hay kích thước từng lần read.

## 8. Cấu hình đúng thứ tự trước khi kết nối

Trình tự phổ biến:

```text
1. new URL / URI.toURL + openConnection()
2. setRequestMethod("POST"/"PUT")
3. setDoOutput(true)
4. setConnectTimeout(...), setReadTimeout(...)
5. setRequestProperty("Content-Type", ...)
6. Chọn ĐÚNG MỘT mode:
      fixed-length nếu biết byte count
      chunked nếu chưa biết
7. getOutputStream()  -> kết nối có thể bắt đầu
8. write tất cả request body bytes
9. close OutputStream
10. getResponseCode(), getInputStream() hoặc getErrorStream()
11. close response stream
12. disconnect() trong finally
```

`setFixedLengthStreamingMode`/`setChunkedStreamingMode` **phải được gọi trước khi connected**. Các hành động như `connect()`, `getOutputStream()`, `getInputStream()` hoặc `getResponseCode()` có thể kích hoạt kết nối, nên không thay mode ở thời điểm ấy.

Gọi fixed rồi gọi chunked (hoặc ngược lại) trên cùng connection sẽ gây `IllegalStateException`. Gọi setter sau khi connected cũng có thể gây `IllegalStateException`. Cần kiểm tra điều kiện ngay tại nơi cấu hình, không dựa vào exception để quyết định streaming mode trong runtime.

Một `HttpURLConnection` chỉ dùng cho một request. Muốn gửi request mới/ retry, phải `openConnection()` để tạo instance mới với cấu hình và body source phù hợp.

## 9. Vì sao không thể tự động gửi lại khi đang streaming?

Với mode không streaming, implementation có thể có **buffer đầy đủ của request body** nên có khả năng phát lại trong một số flow authentication/redirect được hỗ trợ. Khi bạn bật streaming, body có thể đã được gửi thẳng ra mạng và **không còn bản sao trong client**.

```text
WITHOUT streaming:
  Application --> [possible full request-body buffer] --> server
                           |
                           +--> implementation may replay where allowed

WITH streaming:
  Application InputStream --> HttpURLConnection OutputStream --> server
             [one-shot?]      [no full body buffer in client]
                                   |
                 server returns 307 / 401 / 407
                                   |
                 client does NOT know how to recreate body
                                   |
                 HttpRetryException when reading response
```

**Không được đánh đồng “streaming mode” với “body không bao giờ phát lại được”.** Một nguồn `byte[]` hay file ổn định có thể mở lại và gửi một lần nữa **nếu ứng dụng có chủ đích**. Ngược lại, luồng nhận từ camera, pipe, sinh nội dung có side effect, stream đã đọc hết hoặc file bị thay đổi có thể **không replayable**.

API không thể tùy ý quyết định upload lại POST có side effect, đổi URI theo redirect, mang credential sang domain khác hoặc mở lại stream do bạn sở hữu. Đó là **quyết định của tầng ứng dụng**, không phải missing feature cần workaround bằng cách tắt exception.

## 10. Giới hạn quan trọng: HTTP 307/308 redirect

Một redirect thường dùng:

```http
HTTP/1.1 307 Temporary Redirect
Location: /target
```

Với **307** hoặc **308**, HTTP semantics yêu cầu giữ **HTTP method và request content** nếu thực sự tự động follow. Đối với POST đang streaming, client sẽ cần tạo lại body bytes để gửi tới target mới. `HttpURLConnection` Java 17 không tự làm điều này khi đã bật streaming; việc đọc response có thể ném `HttpRetryException` dù `setInstanceFollowRedirects(true)`.

**Đừng chỉ nhìn status 307 rồi lập tức POST lại**. Một quy trình có kiểm soát phải xét:

1. `Location` có hợp lệ, có nằm trong allowlist origin/path hay không?
2. Redirect từ HTTPS sang HTTP có bị policy cấm không?
3. Server gốc đã thực hiện side effect trước khi trả redirect chưa?
4. Body source có thể mở lại để gửi **đúng cùng bytes** không?
5. Có idempotency key, operation ID, retry budget và deadline tổng không?
6. Header Authorization, cookies, client certificate hoặc data nhạy cảm có được phép chuyển sang origin mới không?
7. Có vòng lặp redirect hoặc chain quá dài không?

Trên hệ thống nhạy cảm, có thể chọn **không tự follow** bất kỳ POST redirect nào; trả lỗi có cấu trúc hoặc yêu cầu application protocol rõ hơn.

## 11. HTTP 301/302/303 có semantics khác 307/308

| HTTP status | Điểm cần hiểu khi redirect | Vấn đề với streaming body |
| --- | --- | --- |
| 301 Moved Permanently | Có lịch sử và quy tắc chuyển hướng method trong các client implementations; cần xem RFC/contract | Không giả định POST body được giữ nguyên ở mọi client |
| 302 Found | Một số client có thể chuyển POST thành GET theo semantics/history | Không gửi nội dung tạo giao dịch tới URI mới nếu chưa có policy |
| 303 See Other | Cho phép client lấy resource khác, thường bằng GET, theo protocol | Không đồng nghĩa “replay POST body” |
| 307 Temporary Redirect | **Không đổi method** khi follow redirect | Muốn POST lại phải tái tạo body |
| 308 Permanent Redirect | **Không đổi method** khi follow redirect | Cần quyết định retry và bảo vệ nguồn body |

**Với streaming mode, nguyên tắc chung của `HttpURLConnection` vẫn là authentication và redirection không được xử lý tự động như khi có buffered body.** Không thiết kế ứng dụng dựa vào một tình cờ của một status/phiên bản Java mà chưa test.

Nếu server muốn một thao tác tạo job chỉ tại một endpoint chuẩn, giảm redirect path cho POST stream thường đơn giản và an toàn hơn cố thực hiện mọi loại redirect phía client.

## 12. HTTP 401/407 authentication challenge cũng cần replay

Khi client gửi một POST streaming đến endpoint yêu cầu xác thực, server hoặc proxy có thể trả:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="private-api"
```

Hoặc proxy trả `407 Proxy Authentication Required`. Một HTTP client có body buffer có thể có cơ hội làm authentication challenge/response rồi tự gửi lại request theo policy và credential provider. Nhưng **với streaming mode**, `HttpURLConnection` không thể tự gửi lại body nếu cần retry và có thể ném `HttpRetryException` khi đọc response.

Ứng dụng cần lựa chọn:

- Nếu hợp đồng hỗ trợ, **xác thực ngay từ đầu** bằng một mechanism an toàn, không đợi 401 rồi upload body dài mới xác thực; không để token bị log.
- Khi đã có 401/407, xác định đó là lỗi credential, proxy configuration hay permissions; **không retry vô hạn cùng credential sai**.
- Khi muốn retry, phải tạo **connection mới**, cung cấp nguồn body mới và policy phù hợp; không tái sử dụng `HttpURLConnection` đã connected.
- Không gửi Authorization header của origin A sang origin B chỉ vì redirect. Cần chặn credential leakage và SSRF.
- Với HTTPS, vẫn phải xác minh TLS certificate và hostname; không dùng trust-all manager để “sửa” authentication.

Có thể đọc HTTP error stream khi server gửi hữu ích, nhưng `getErrorStream()` **có thể null**; hạn chế số bytes đọc/log và bảo vệ dữ liệu nhạy cảm.

## 13. HttpRetryException: tín hiệu “cần xử lý”, không phải lệnh tự retry

`java.net.HttpRetryException` kế thừa `IOException`. Khi gặp, ứng dụng có thể truy cập:

```java
// Snippet minh họa trong nhánh catch.
catch (HttpRetryException ex) {
    int status = ex.responseCode();
    String reason = ex.getReason();
    String location = ex.getLocation(); // có thể null
    // Log metadata an toàn; quyết định theo policy, không blind retry.
}
```

Trong code thực cần mở đúng cấu trúc try/catch, xử lý checked exceptions và không rò full URL chứa secrets. `getLocation()` cung cấp thông tin redirect **nếu có**, không có nghĩa location hợp lệ để tự động truy cập.

Cần phân biệt:

- `HttpRetryException`: HTTP response đòi thêm hành động authentication/redirect mà client streaming không tự replay được.
- `SocketTimeoutException`: hết thời gian chờ kết nối/đọc theo timeout, chưa chắc server chưa xử lý.
- `ProtocolException`: method, state hoặc protocol API sử dụng không phù hợp.
- `IOException` khác: network/stream failure, trạng thái remote có thể mơ hồ.

Một `HttpRetryException` không phải “Java đã thử lại rồi thất bại lần hai” theo nghĩa business. Nó nói rằng **không thể tiếp tục quy trình tự động cần replay** trong mode này.

## 14. Java 17+ demo số 1: fixed-length và chunked trên HTTP server loopback

Tệp **`HttpStreamingModesDemo.java`** tự tạo một `HttpServer` từ module chuẩn `jdk.httpserver`, bind **chỉ** IPv4 loopback `127.0.0.1` và cổng tự cấp. Nó nhận hai POST:

- `/upload/fixed`: client gửi `"Xin chào"` theo UTF-8, tính đúng 9 byte, gọi `setFixedLengthStreamingMode((long) fixed.length)` và ghi payload thành **hai lần `write`**.
- `/upload/chunked`: client gửi chuỗi 20 byte `"part-A|part-B|part-C"` bằng `setChunkedStreamingMode(1024)`, cũng ghi bằng **hai lần `write`**.
- Server giải mã body theo HTTP framework, ghi nhận header `Content-Length` hoặc `Transfer-Encoding`, và trả `200 OK` với body `OK`. Client đọc response/đóng streams và `disconnect()`.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class HttpStreamingModesDemo {
    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        AtomicInteger requests = new AtomicInteger();
        AtomicInteger fixedBytes = new AtomicInteger();
        AtomicInteger chunkedBytes = new AtomicInteger();
        AtomicReference<String> fixedLengthHeader =
                new AtomicReference<>();
        AtomicReference<String> fixedText = new AtomicReference<>();
        AtomicReference<String> transferEncoding =
                new AtomicReference<>();

        server.createContext("/upload", exchange -> {
            try {
                byte[] body;
                try (InputStream in = exchange.getRequestBody()) {
                    body = in.readAllBytes();
                }
                requests.incrementAndGet();
                if (exchange.getRequestURI().getPath()
                        .endsWith("/fixed")) {
                    fixedBytes.set(body.length);
                    fixedLengthHeader.set(exchange.getRequestHeaders()
                            .getFirst("Content-Length"));
                    fixedText.set(new String(
                            body, StandardCharsets.UTF_8));
                } else {
                    chunkedBytes.set(body.length);
                    transferEncoding.set(exchange.getRequestHeaders()
                            .getFirst("Transfer-Encoding"));
                }
                byte[] ok = "OK".getBytes(StandardCharsets.US_ASCII);
                exchange.sendResponseHeaders(200, ok.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(ok);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(workers);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            String text = "Xin chào";
            byte[] fixed = text.getBytes(StandardCharsets.UTF_8);
            byte[] chunked = "part-A|part-B|part-C".getBytes(
                    StandardCharsets.UTF_8);

            HttpURLConnection one = (HttpURLConnection)
                    URI.create(base + "/upload/fixed")
                            .toURL().openConnection();
            boolean fixedOk;
            try {
                one.setRequestMethod("POST");
                one.setDoOutput(true);
                one.setConnectTimeout(3000);
                one.setReadTimeout(3000);
                one.setRequestProperty("Content-Type",
                        "text/plain; charset=UTF-8");
                one.setFixedLengthStreamingMode((long) fixed.length);
                try (OutputStream out = one.getOutputStream()) {
                    out.write(fixed, 0, 3);
                    out.write(fixed, 3, fixed.length - 3);
                }
                fixedOk = one.getResponseCode() == 200;
                try (InputStream in = one.getInputStream()) {
                    fixedOk &= "OK".equals(new String(
                            in.readAllBytes(), StandardCharsets.US_ASCII));
                }
            } finally {
                one.disconnect();
            }

            HttpURLConnection two = (HttpURLConnection)
                    URI.create(base + "/upload/chunked")
                            .toURL().openConnection();
            boolean chunkedOk;
            try {
                two.setRequestMethod("POST");
                two.setDoOutput(true);
                two.setConnectTimeout(3000);
                two.setReadTimeout(3000);
                two.setChunkedStreamingMode(1024);
                try (OutputStream out = two.getOutputStream()) {
                    out.write(chunked, 0, 6);
                    out.write(chunked, 6, chunked.length - 6);
                }
                chunkedOk = two.getResponseCode() == 200;
                try (InputStream in = two.getInputStream()) {
                    chunkedOk &= "OK".equals(new String(
                            in.readAllBytes(), StandardCharsets.US_ASCII));
                }
            } finally {
                two.disconnect();
            }

            System.out.println("Fixed body bytes: " + fixedBytes.get());
            System.out.println("Fixed Content-Length correct: "
                    + String.valueOf(fixed.length).equals(
                            fixedLengthHeader.get()));
            System.out.println("UTF-8 bytes exceed char count: "
                    + (fixed.length > text.length()));
            System.out.println("Fixed body matches: "
                    + text.equals(fixedText.get()));
            System.out.println("Chunked Transfer-Encoding: "
                    + "chunked".equalsIgnoreCase(
                            transferEncoding.get()));
            System.out.println("Chunked body bytes: "
                    + chunkedBytes.get());
            System.out.println("Responses OK: " + (fixedOk && chunkedOk));
            System.out.println("Requests served: " + requests.get());
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Biên dịch/chạy với JDK 17+:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 HttpStreamingModesDemo.java
java --add-modules jdk.httpserver HttpStreamingModesDemo
```

Stdout đã kiểm thử:

```text
Fixed body bytes: 9
Fixed Content-Length correct: true
UTF-8 bytes exceed char count: true
Fixed body matches: true
Chunked Transfer-Encoding: true
Chunked body bytes: 20
Responses OK: true
Requests served: 2
```

**Giải thích từng khẳng định:**

1. `Fixed body bytes: 9` đến từ số bytes server **đã đọc**, không phải số chars của Java String.
2. `Fixed Content-Length correct: true` xác nhận **header do HTTP client gửi** có độ dài đúng. Client không tự chỉnh header `Content-Length` bằng tay.
3. `UTF-8 bytes exceed char count` cho thấy chênh lệch giữa UTF-8 và UTF-16 char count trong văn bản tiếng Việt.
4. `Fixed body matches` xác nhận payload đến server không bị cắt/mất bytes khi client ghi hai lần.
5. `Chunked Transfer-Encoding: true` xác nhận server nhận header transfer coding `chunked`. Demo **không đếm chunk frames** và không coi hai lần `write` tương ứng hai chunks.
6. `Chunked body bytes: 20` cho thấy HTTP server nhận body đã giải mã thành bytes liên tục, có tổng kích thước kỳ vọng.
7. `Responses OK` buộc cả hai requests có HTTP 200 và body response `OK`, chứ không chỉ dừng ở `getOutputStream().close()`.
8. `HttpURLConnection` là request-specific; demo dùng **hai instances riêng**, không tự reuse một object để đổi upload mode.

Đây là test của **Java API framing**, không phải benchmark throughput, không kiểm chứng bao nhiêu TCP sockets được reuse và không đại diện cho proxy/server từ Internet. Giao thức không bảo đảm chunk boundaries quan sát ở phía server giống ranh giới write calls.

## 15. Java 17+ demo số 2: redirect 307 bị từ chối replay tự động

Tệp **`StreamingRedirectDemo.java`** tạo server loopback có hai endpoints:

1. `POST /redirect` đọc request body, đếm request, trả `307 Temporary Redirect` với `Location: /target`.
2. `/target` đếm số request thực sự đến.

Client tạo một `HttpURLConnection` cho `/redirect`, bật `setInstanceFollowRedirects(true)` **nhưng đồng thời** bật `setFixedLengthStreamingMode(...)`, gửi POST body một lần rồi gọi `getInputStream()`.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpRetryException;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class StreamingRedirectDemo {
    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        AtomicInteger redirectHits = new AtomicInteger();
        AtomicInteger targetHits = new AtomicInteger();

        server.createContext("/redirect", exchange -> {
            try {
                try (InputStream in = exchange.getRequestBody()) {
                    in.transferTo(OutputStream.nullOutputStream());
                }
                redirectHits.incrementAndGet();
                exchange.getResponseHeaders().set("Location", "/target");
                exchange.sendResponseHeaders(307, -1);
            } finally {
                exchange.close();
            }
        });
        server.createContext("/target", exchange -> {
            try {
                targetHits.incrementAndGet();
                byte[] ok = "TARGET".getBytes(
                        StandardCharsets.US_ASCII);
                exchange.sendResponseHeaders(200, ok.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(ok);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(workers);
        server.start();

        try {
            URL url = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort()
                    + "/redirect").toURL();
            byte[] body = "change=1".getBytes(
                    StandardCharsets.UTF_8);
            HttpURLConnection conn = (HttpURLConnection)
                    url.openConnection();
            boolean retryNeeded = false;
            int code = -1;
            try {
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setInstanceFollowRedirects(true);
                conn.setConnectTimeout(3000);
                conn.setReadTimeout(3000);
                conn.setFixedLengthStreamingMode((long) body.length);
                try (OutputStream out = conn.getOutputStream()) {
                    out.write(body);
                }
                try (InputStream in = conn.getInputStream()) {
                    in.transferTo(OutputStream.nullOutputStream());
                } catch (HttpRetryException ex) {
                    retryNeeded = true;
                    code = ex.responseCode();
                }
            } finally {
                conn.disconnect();
            }
            System.out.println("Redirect needs caller handling: "
                    + retryNeeded);
            System.out.println("Redirect status: " + code);
            System.out.println("Redirect requests: "
                    + redirectHits.get());
            System.out.println("Target requests: " + targetHits.get());
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Biên dịch/chạy:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 StreamingRedirectDemo.java
java --add-modules jdk.httpserver StreamingRedirectDemo
```

Stdout đã kiểm thử:

```text
Redirect needs caller handling: true
Redirect status: 307
Redirect requests: 1
Target requests: 0
```

**Điểm quan trọng nhất:** mặc dù `setInstanceFollowRedirects(true)` đã bật, server trả redirect và Java vẫn báo `HttpRetryException` vì đang **streaming**. Counter `Target requests: 0` chứng minh client **không tự gửi lại body** sang `/target`. Ở đây ứng dụng **chủ động không retry** vì chỉ muốn minh họa giới hạn và tránh hành vi không kiểm soát.

Code có redirect 307 *relative location* nhưng không dùng `getLocation()` để tự mở URL mới. Nếu một ứng dụng thật quyết định manual retry, nó phải resolve URI theo base, kiểm tra scheme/host/port/path allowlist, có nguồn body có thể replay và biết semantics request; **không truy cập bất kỳ URL nào từ header Location theo mặc định**.

## 16. Lỗi gửi thiếu hoặc dư byte trong fixed-length mode

Khả năng phát hiện sai byte count là **một phần của API contract**, không phải tùy chọn:

```java
// Snippet minh họa sai: body được cam kết 10 bytes,
// nhưng caller chỉ ghi 9 bytes rồi đóng output.
conn.setFixedLengthStreamingMode(10L);
try (OutputStream output = conn.getOutputStream()) {
    output.write(new byte[9]);
} // IOException do không đáp ứng đủ bytes đã khai báo.
```

Với ghi **dư**, `write` có thể ném IOException ngay khi vượt số byte còn được phép. Với ghi **thiếu**, `close` có thể ném IOException. Vì vậy không chỉ đặt `try` quanh `getResponseCode()`; phải bắt/cleanup exception trong **đường ghi body**.

Những nguồn gây mismatch:

- Tính `text.length()` thay vì `text.getBytes(UTF_8).length`.
- Dùng `Files.size` trước khi file bị thay đổi trong lúc upload.
- Tính kích thước dữ liệu **trước** khi gzip/base64/transcode nhưng gửi dữ liệu **sau** biến đổi.
- Một producer thất bại giữa đường rồi đóng stream như thể đã gửi đủ.
- Sử dụng offset/length sai hoặc bỏ qua partial reads của nguồn.
- Phép cộng/truyền kiểu dữ liệu dẫn đến tràn `int` cho file lớn.

**Không tự retry ngay** khi thiếu bytes: server có thể đã nhận một phần và trạng thái xử lý không rõ, đặc biệt nếu server streaming parse/upload theo từng phần. Cần API upload session/operation ID để biết server giữ phần nào.

## 17. Chunked có tránh được upload “một lần đọc hết” không?

Có thể giảm nhu cầu đệm cả nội dung, nhưng upload vẫn cần một **nguồn phát dữ liệu** đúng lifetime:

```java
// Snippet, nguồn input và conn đã cấu hình.
try (InputStream input = source;
     OutputStream output = conn.getOutputStream()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = input.read(buffer)) != -1) {
        output.write(buffer, 0, n);
    }
}
```

Ở đây `buffer` chỉ giữ tối đa 8192 bytes mỗi vòng. Nhưng:

1. `InputStream.read` có thể trả bất kỳ số byte dương đến chiều dài buffer, không bảo đảm “đúng một chunk”.
2. `OutputStream.write` có thể block nếu network/server chậm; *streaming* không tự tạo async nonblocking producer.
3. Với nguồn không replayable, khi 401/307 xảy ra, không có cách tự “rewind” InputStream đã consume.
4. Close OutputStream báo body kết thúc đúng theo framing; không quên close khi producer đến EOF.
5. Cần cancellation/deadline/byte cap để không đọc vô hạn từ nguồn không đáng tin.
6. Nội dung có thể bị nén/mã hóa hoặc thay đổi trong pipeline; chunked framing không tự định nghĩa JSON record boundary hay checksum.

**Streaming upload không đồng nghĩa streaming response**: gửi qua `getOutputStream`, còn đọc phản hồi qua `getInputStream/getErrorStream` là một lượt I/O khác và phải cleanup riêng.

## 18. Thông tin response và xử lý HTTP status/errors

Một routine HTTP an toàn cần quan sát status:

```java
// Snippet minh họa: request body đã gửi xong, conn đang active.
int status = conn.getResponseCode();
InputStream responseStream = status >= 400
        ? conn.getErrorStream()
        : conn.getInputStream();
if (responseStream != null) {
    try (InputStream in = responseStream) {
        // Đọc với kích thước tối đa và charset đúng.
    }
}
```

Trong thực tế, `getResponseCode()`/`getInputStream()` có thể ném exception liên quan streaming redirect/auth, nên phải có catch riêng `HttpRetryException`, `IOException`. Với error stream, **có thể là null** nếu server không gửi body hoặc lỗi xảy ra trước response; đừng gọi `read` trên null.

`HttpURLConnection.getInputStream()` có thể ném IOException cho HTTP status lỗi, nhưng response headers/status vẫn có thể hữu ích. Đừng bỏ không đọc/đóng response; backend có thể giữ connection resources lâu nếu stream bị bỏ quên.

Giới hạn kích thước **cả error body**: server lỗi có thể trả HTML rất lớn hoặc dữ liệu chứa secret. Không log raw response vô hạn; parse/redact theo Content-Type/encoding và policy.

Trong hai chương trình loopback, response body chỉ vài bytes nên dùng `InputStream.readAllBytes()` là hợp lý. Với production, không dùng `readAllBytes()` cho nội dung Internet không có kích thước trần.

## 19. connectTimeout, readTimeout và upload deadline

Một số timeouts:

- `setConnectTimeout(ms)` giới hạn thời gian thiết lập kết nối network, **không** là toàn bộ upload deadline.
- `setReadTimeout(ms)` giới hạn thời gian chờ đọc dữ liệu từ InputStream theo hợp đồng API, **không** là ngân sách tổng thời gian cho một body lớn.
- `OutputStream.write(...)` có thể block theo network backpressure, TLS buffering và hành vi provider; không tự cho rằng `readTimeout` kiểm soát toàn bộ thời gian ghi.
- Một file lớn có thể gửi được mỗi chunk trong vài giây nhưng **toàn bộ upload** kéo dài hàng phút/giờ. Cần deadline ở tầng application hoặc cấu trúc async/cancel có kiểm soát khi SLA yêu cầu.
- Nếu timeout xảy ra **sau khi server đã nhận toàn bộ hoặc một phần request**, không suy từ exception rằng server chưa xử lý gì.

Với operation quan trọng, hãy dùng idempotency key hoặc upload session ID ở API để hỏi tình trạng. Nếu người dùng hủy upload, cần cơ chế server-side cleanup/cancel session riêng; đóng TCP không tự xóa mọi temporary chunks hoặc database records.

## 20. Bảo mật khi manual redirect và authentication

Khi đang streaming, ứng dụng có thể bị cám dỗ viết:

```java
// Anti-pattern: KHÔNG tự động gửi lại mọi POST theo Location.
String location = ex.getLocation();
HttpURLConnection another = (HttpURLConnection)
        URI.create(location).toURL().openConnection();
// ... resend original body + Authorization (SAI nếu chưa kiểm tra).
```

Đây là **snippet cảnh báo**, không phải code nên sử dụng. Một Location do server/proxy kiểm soát có thể trỏ đến địa chỉ nội bộ, metadata endpoint, file scheme không mong muốn, domain khác hoặc HTTP không TLS. Nếu client mang Authorization/cookies/PII theo, có rủi ro **SSRF và credential leakage**.

Manual follow phải có chính sách rõ:

1. Kiểm tra scheme chỉ HTTP(S) được phép, host/port/đường dẫn thuộc allowlist.
2. Chặn downgrade HTTPS → HTTP khi có dữ liệu nhạy cảm.
3. Quy định redirect method semantics: 307/308 giữ method/body; 301/302/303 cần xử lý theo API contract.
4. Không đưa credential hoặc cookie của origin cũ cho origin mới nếu chưa được phép.
5. Hạn chế số redirects và phát hiện vòng lặp.
6. Chỉ replay nếu body có thể được tạo lại chính xác, operation được phép retry và có idempotency key/operation ID.
7. Giới hạn tổng thời gian, dung lượng và số attempts; có logs/tracing nhưng không log secrets.
8. Không giải quyết 401/407 bằng tắt TLS verification/trust-all.

**Một HTTP redirect không chứng minh endpoint mới an toàn hoặc business operation cũ chưa được xử lý.**

## 21. “Có thể replay” là thuộc tính của nguồn nội dung và nghiệp vụ

| Body source | Có thể phát lại nội dung giống hệt không? | Hướng xử lý |
| --- | --- | --- |
| `byte[]` bất biến trong operation | Thường có | Tạo connection mới, ghi lại bytes nếu method/policy cho phép |
| File ổn định, checksum được khóa | Có thể | Mở stream mới, kiểm tra độ dài/hash/version trước retry |
| File bị người dùng sửa trong lúc upload | Không bảo đảm | Version/locking/snapshot, không dùng byte count cũ |
| `InputStream` từ pipe/network chỉ đọc một lần | Thường không | Không blind retry; dùng spool có giới hạn hoặc resumable protocol |
| Producer nén/chuyển mã nondeterministic | Không bảo đảm byte-for-byte | Snapshot output hoặc thiết kế semantic idempotency thay vì byte equality |
| Request sinh mã giao dịch mới mỗi lần gọi | Body có thể replay, **operation không cùng identity** | Giữ idempotency key/operation ID ổn định |
| POST payment/order đã commit trước khi response mất | Replay bytes **không tự an toàn** | Tra trạng thái, dùng idempotency server-side |

Ba câu hỏi độc lập:

1. **Kỹ thuật:** Có tái tạo được cùng bytes không?
2. **HTTP semantics:** Method và redirect/auth có cho phép retry không?
3. **Nghiệp vụ:** Gửi lại request có gây thêm một side effect không?

Chỉ câu 1 đúng **không đủ** để quyết định retry. Một file hoàn toàn replayable vẫn có thể được POST vào endpoint tạo job **hai lần**. Cần cơ chế dedup server và confirmation/reconciliation.

## 22. Retry an toàn hơn với idempotency và resumable upload

Một server nhận upload lớn thường có API upload-session:

```text
POST /uploads                   -> 201, uploadId=U123
PUT  /uploads/U123/parts/1      -> upload segment with checksum
PUT  /uploads/U123/parts/2      -> upload segment with checksum
GET  /uploads/U123              -> current committed segments/status
POST /uploads/U123/complete     -> finalized artifact
DELETE /uploads/U123            -> cancel, theo policy
```

Đây là **ví dụ giao thức**, không phải endpoint có sẵn trong Java. Kết hợp:

- **Idempotency key** định danh logical create/complete operation; server lưu durable state cùng side effect.
- **Part number/offset + checksum** giúp server biết segment nào đã nhận, không cần gửi lại toàn bộ file.
- **Conditional update/ETag/version** tránh ghi đè sai.
- **Status endpoint** cho phép reconcile sau timeout, auth challenge hoặc connection reset.
- **TTL và quota** cho upload sessions chưa hoàn tất.
- **Authorization** cho owner, tenant, size, content type, mime sniffing và virus scanning khi cần.
- **Retry budget/backoff** để tránh quá tải server khi hàng nghìn clients cùng retry.

Chọn fixed-length khi biết chính xác segment byte count, chunked khi không; nhưng **khả năng retry an toàn chủ yếu đến từ thiết kế protocol/server**, không từ một setter của `HttpURLConnection`.

## 23. Mối quan hệ với HttpClient Java 17 hiện đại

Bài này tập trung vào `HttpURLConnection` vì đó là nguồn của các setter streaming mode cụ thể. Java 17 còn có `java.net.http.HttpClient` và `HttpRequest.BodyPublisher`:

| API | Cách gửi body | Cách cung cấp độ dài |
| --- | --- | --- |
| `HttpURLConnection` | `getOutputStream()` + chọn fixed/chunked mode | `setFixedLengthStreamingMode` / `setChunkedStreamingMode` |
| `java.net.http.HttpClient` | `HttpRequest.BodyPublishers.ofString/ofByteArray/ofFile/ofInputStream/fromPublisher` | `BodyPublisher.contentLength()` và publisher semantics |
| `HttpsURLConnection` | API `HttpURLConnection` kết hợp TLS | Tương tự fixed/chunked ở URLConnection family |

Không chuyển nguyên API `setChunkedStreamingMode` sang `java.net.http.HttpClient.Builder`: đó là **hai API khác nhau**. Với modern client, `BodyPublisher` có thể cho content length biết trước hoặc unknown length; protocol implementation quyết định HTTP/1.1 framing/HTTP/2. Vẫn cần hiểu body replayability, redirect/auth behavior, timeout và idempotency theo **hợp đồng riêng của API đang dùng**.

Đừng mặc định hiện đại hơn nghĩa có thể “tự retry mọi POST streaming” an toàn. Một request body không replayable và business side effect vẫn là vấn đề ở bất kỳ HTTP stack nào.

## 24. Sự thật cần phân biệt về connection pooling

`HttpURLConnection` Javadoc nói mỗi object dùng để thực hiện một request, nhưng underlying network connection có thể được các object khác **chia sẻ ngầm**. `disconnect()` cho biết không kỳ vọng dùng connection này nữa; nó **có thể** đóng socket nền nếu socket đang idle. Việc đóng response streams giải phóng nguồn lực exchange, **không hứa một socket mới hay một socket reused**.

Những suy luận không an toàn:

- “Dùng fixed-length thì TCP luôn keep-alive”: không đúng; server/proxy/timeout có thể đóng.
- “Dùng chunked thì chắc chắn tách thành nhiều TCP packets”: TCP segmentation có thể gộp/chia dữ liệu tùy điều kiện.
- “Đã gọi `disconnect()` nghĩa server chưa đọc phần body chưa gửi”: không chắc; network và server có thể đang xử lý.
- “Mỗi lần `openConnection()` tức là tạo một TCP socket mới”: không bắt buộc; keep-alive có thể được tái sử dụng.
- “Hai calls `out.write` là hai HTTP chunks”: không có contract như vậy.
- “Một HTTP chunk là một business upload part”: không; upload parts phải có application-level IDs/framing.

Để đo reuse, cần server metrics/TCP tracing/connection IDs, không đo số `HttpURLConnection` objects hay số `OutputStream.write` calls.

## 25. Chẩn đoán lỗi thường gặp

| Triệu chứng | Khả năng chính | Cách kiểm tra |
| --- | --- | --- |
| `IOException: too many bytes written` | Body dài hơn fixed declared length | Đếm bytes sau encode/transform; dùng long length đúng |
| `IOException: insufficient data written` | Đóng trước khi ghi đủ fixed length | Kiểm tra producer EOF/exception, file bị thay đổi |
| `IllegalStateException: Already connected` | Chọn streaming mode sau `connect/getOutputStream` | Di chuyển setter trước kết nối |
| `IllegalStateException` khi gọi cả fixed và chunked | Hai modes loại trừ nhau | Chọn một mode theo biết/không biết byte count |
| `HttpRetryException` sau response 307/308 | Redirect cần replay body nhưng streaming không auto replay | Kiểm tra location, method, byte source, idempotency, security |
| `HttpRetryException` sau 401/407 | Auth challenge cần replay request body | Xác thực trước, không retry mù với credential sai |
| HTTP 411 Length Required | Server/proxy yêu cầu Content-Length | Đổi fixed-length khi byte length biết được; liên hệ server policy |
| HTTP 400/501 với chunked | Server/proxy không hỗ trợ transfer coding | Xác minh từng hop, tránh tự bóp méo chunked |
| Server body parser nhận sai UTF-8 | Dùng char length hoặc decode per chunk | Encode UTF-8 một lần/decoder có trạng thái |
| Client chờ mãi ở `getOutputStream/write` | Backpressure, peer chậm, network | Deadline/cancellation policy, observability |
| HTTP 413 Payload Too Large | Server/proxy quota | Giới hạn dung lượng từ trước, không retry cùng body vô hạn |
| `getErrorStream() == null` | Không có error body hoặc I/O lỗi sớm | Null-check, lấy status/header có thể |
| Response body bị bỏ mở | Quên close/consume InputStream | Try-with-resources, cleanup finally |

Một exception ở **client khi đọc phản hồi** không chứng minh server chưa xử lý POST. Bản ghi business cần operation ID/status endpoint thay vì suy luận từ transport failure.

## 26. Hai mươi lỗi thiết kế phổ biến

1. **Tính Content-Length bằng `String.length()`.** Sai với UTF-8/non-BMP; tính bytes.
2. **Gọi fixed-length mode rồi ghi dư bytes.** Sẽ gặp IOException, không phải auto resize Content-Length.
3. **Gọi fixed-length mode rồi đóng thiếu bytes.** Contract bị vi phạm, không tự pad.
4. **Gọi cả fixed và chunked trên một connection.** Không hợp lệ.
5. **Cài streaming mode sau `getOutputStream()`.** Quá muộn, kết nối có thể đã bắt đầu.
6. **Nghĩ chunklen là tổng body length.** Nó là cấu hình chunking, body có thể dài không biết trước.
7. **Nghĩ `setChunkedStreamingMode(0)` nghĩa zero-byte body.** Không, nó chọn chunk size mặc định.
8. **Coi hai lần `write` là hai chunks hiện trên server.** Không bảo đảm chunk boundaries.
9. **Bắt buộc server hiểu chunked khi chưa kiểm tra.** Một số server/proxy không hỗ trợ.
10. **Tự thêm Content-Length đồng thời với Transfer-Encoding chunked.** Framing mâu thuẫn.
11. **Nghĩ streaming luôn nhanh hơn buffering trong mọi workload.** Cần benchmark đúng dữ liệu.
12. **Nghĩ streaming bảo đảm không có buffering nào.** Vẫn có buffers I/O/TLS/TCP hữu hạn.
13. **Bật followRedirects rồi nghĩ body streaming được replay tự động.** Có thể có `HttpRetryException`.
14. **Nhận 307/308 và POST lại vào URI không kiểm tra.** SSRF, leak credential, duplicate side effects.
15. **Nhận 401/407 và gửi lại liên tục cùng credential.** Vô ích và gây tải.
16. **Dùng lại `HttpURLConnection` instance cho request lần hai.** Instance dùng cho một request, cần open mới.
17. **Retry với InputStream đã đọc hết.** Không có dữ liệu để replay; cần source mới.
18. **Dựa vào file size cũ khi file bị mutate.** Fixed byte contract có thể sai.
19. **Gọi `readAllBytes()` trên response/upload không giới hạn.** OOM; dùng bounded streaming.
20. **Coi timeout/IOException là “server chắc chắn chưa tạo đơn”.** Không chắc, cần status/idempotency.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** Body `"Xin chào"` dùng UTF-8 nên khai `setFixedLengthStreamingMode(text.length())` được không? **Không**; dùng số bytes của UTF-8 encoding, ví dụ 9 byte.

**Câu 2.** Kích thước output chưa biết nhưng server hỗ trợ chunked upload, nên chọn gì? **`setChunkedStreamingMode(...)`** trước khi mở output stream.

**Câu 3.** `setChunkedStreamingMode(0)` có gửi một body rỗng không? **Không**; chọn chunk size mặc định.

**Câu 4.** Gọi fixed trước rồi chunked có được không? **Không**; hai mode loại trừ nhau.

**Câu 5.** Đã bật `setInstanceFollowRedirects(true)` và streaming POST, server trả 307. Vì sao có `HttpRetryException`? **Client không có body buffer để tự replay**, nên ứng dụng phải xử lý an toàn.

**Câu 6.** `HttpRetryException` chứng minh server chưa xử lý request? **Không**. Kết quả side effect cần bằng chứng từ server ledger.

**Câu 7.** Một file có thể mở lại từ đầu thì retry POST đã chắc an toàn chưa? **Chưa**. Phải xét HTTP semantics, idempotency và redirect target.

**Câu 8.** Server đọc `InputStream.read` một lần ra 8192 bytes; có nghĩa HTTP wire chunk là 8192 bytes? **Không**. Chunk transfer coding đã được parser HTTP xử lý, boundaries không trùng.

**Câu 9.** Một `HttpURLConnection` dùng để gửi hai request khác nhau được không? **Không**. Mỗi object cho một request; mở connection object mới cho retry/operation mới.

**Câu 10.** Đóng `InputStream` response có bảo đảm socket bị đóng hoàn toàn không? **Không**. Keep-alive sharing và `disconnect()` có semantics riêng.

**Câu 11.** Server trả HTTP 411 sau chunked upload. Nên làm gì? **Xác minh server policy; nếu biết byte count thật, có thể chọn fixed-length trên request mới theo contract**, không tự đưa Content-Length giả.

**Câu 12.** Content source là một pipe chỉ đọc một lần. Server trả 401 và yêu cầu replay. Có thể `getOutputStream` lại trên connection cũ không? **Không**. Cần nguồn có thể tạo lại hoặc protocol khác; xử lý auth trước khi gửi.

## 28. Checklist triển khai production

1. **Đúng API:** request là HTTP(S) `HttpURLConnection/HttpsURLConnection`, không lẫn `java.net.http.HttpClient`.
2. **Chọn fixed hoặc chunked theo độ dài byte thật:** biết chính xác thì fixed; không biết thì chunked nếu server/proxy hỗ trợ.
3. **Cấu hình mọi mode trước khi connected:** method, doOutput, headers, timeouts, streaming mode.
4. **Đếm UTF-8 bytes, không dùng char count**; chú ý gzip/transcode/changing files.
5. **Giới hạn upload bytes, memory, time và concurrency**; truyền dần không có nghĩa nguồn vô hạn an toàn.
6. **Có đầy đủ try-with-resources/finally:** đóng request output, đọc/đóng response body hoặc error stream và `disconnect()`.
7. **Đọc HTTP status và xử lý HTTP errors có quota:** `getErrorStream` có thể null.
8. **Đã kiểm chứng server/proxy support chunked uploads chưa?** Bao gồm HTTP 411/413 và proxies trung gian.
9. **Có policy redirect 301/302/303/307/308 chưa?** Không follow mọi URI hoặc POST side effect mù quáng.
10. **Có giải pháp auth 401/407 không cần replay body lớn?** Credential đúng trước khi gửi, không leak secrets.
11. **Nguồn body có replayable không?** byte[], snapshot file, input stream one-shot, generator state.
12. **Retry có idempotency key/server-side dedup không?** Đặc biệt POST orders/payment/jobs.
13. **Có operation ID/status reconciliation cho ambiguous outcomes không?**
14. **Không lộ Authorization/cookies khi chuyển origin:** chống SSRF, HTTPS downgrade, redirect loop.
15. **Có deadline end-to-end, cancellation và backoff?** Connect/read timeout không thay toàn operation SLA.
16. **Có test thực trên Java 17 và server thật?** Fixed byte count, chunked framing, 307/401, upload lớn, file mutate, body error, pool reuse.

**Kết luận:** `setFixedLengthStreamingMode(long)` dùng khi biết **đúng số byte body**, `setChunkedStreamingMode(int)` khi **chưa biết số byte**. Hai chế độ tránh việc client phải giữ toàn bộ request body để gửi nhưng đổi lại **không thể tự replay an toàn** khi server yêu cầu redirect/authentication. `HttpRetryException` là dấu hiệu để ứng dụng quyết định, **không phải giấy phép tự gửi lại POST**. Tính đúng của upload phụ thuộc byte count/framing, và tính an toàn của retry phụ thuộc nguồn dữ liệu có thể phát lại, HTTP semantics, đích nhận hợp lệ và idempotency từ server.

### Tài liệu tham khảo chính thống

- [Java SE 17 — HttpURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): `setFixedLengthStreamingMode`, `setChunkedStreamingMode`, `getErrorStream`, `disconnect`.
- [Java SE 17 — HttpRetryException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpRetryException.html): `responseCode`, `getReason`, `getLocation`.
- [Java SE 17 — URLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): connection state, timeouts và input/output configuration.
- [Java SE 17 — HttpsURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): TLS-protected HTTP connection.
- [Java SE 17 — HttpClient / BodyPublisher](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html): sự khác nhau của API HTTP hiện đại.
- [RFC 9112 — HTTP/1.1 transfer coding](https://www.rfc-editor.org/rfc/rfc9112.html).
- [RFC 9110 — HTTP Semantics / Redirects and Idempotence](https://www.rfc-editor.org/rfc/rfc9110.html).