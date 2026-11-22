# Tạo GET, POST, PUT và method tùy chọn với header đúng bằng Java HttpClient

Java 11 trở lên cung cấp HTTP client chuẩn trong module `java.net.http`, tiếp tục được hỗ trợ trên **Java 17+**. Với `HttpClient` và `HttpRequest.Builder`, ứng dụng có thể tạo request `GET`, `POST`, `PUT`, `DELETE` hoặc một HTTP method tùy chọn như `PATCH`, gửi request đồng bộ/bất đồng bộ, và đọc status, headers, body của response.

Phần dễ sai nhất không phải gọi đúng tên method, mà là **phối hợp chính xác HTTP method, URI, request body và headers** theo hợp đồng của API phía server. Ví dụ: `Content-Type` mô tả **body đang gửi**, `Accept` mô tả **kiểu response muốn nhận**; `BodyPublishers.ofString(...)` không tự biến Java object thành JSON và không tự chọn `Content-Type: application/json`; `Content-Length` thường do HttpClient/body publisher tự quản lý. Một request hợp lệ ở phía Java vẫn có thể sai về ngữ nghĩa HTTP hoặc bị server từ chối.

Bài học đi từ cách tạo request tới cấu hình headers, xử lý response và lỗi thực tế, rồi cung cấp chương trình **Java 17+ chạy độc lập trên loopback**, dùng một HTTP server trong bộ nhớ để kiểm chứng cả bốn phương thức **GET, POST, PUT, PATCH** mà không cần gọi API Internet.

## 1. Các thành phần và quy trình

Một HTTP exchange cơ bản:

~~~text
          HttpClient (tái sử dụng cho nhiều request)
                         |
HttpRequest.Builder     |     HttpResponse.BodyHandler<T>
  URI                   |              |
  method                |              v
  headers               |        giải mã/tiêu thụ
  BodyPublisher         |        response body
        |                |
        +--- build() ----+
                 |
          HttpRequest bất biến
                 |
         client.send(request, handler)
                  hoặc
         client.sendAsync(request, handler)
                 |
                 v
       HTTP request trên TCP/TLS
                 |
             HTTP server
                 |
                 v
       status + headers + body
                 |
                 v
           HttpResponse<T>
~~~

Các lớp liên quan:

| Thành phần | Vai trò |
| --- | --- |
| `java.net.http.HttpClient` | Client dùng chung: kết nối, proxy, HTTP version, redirect, connect timeout, TLS… |
| `HttpRequest` | Request đã dựng: URI, method, headers, body publisher, request timeout |
| `HttpRequest.Builder` | Builder mutable để thiết lập request; `build()` trả request bất biến |
| `HttpRequest.BodyPublishers` | Nguồn byte gửi đi: `ofString`, `ofByteArray`, `ofFile`, `noBody`… |
| `HttpResponse.BodyHandlers` | Cách nhận response: `ofString`, `ofByteArray`, `ofFile`, `discarding`… |
| `HttpResponse<T>` | Thông tin kết quả: `statusCode()`, `headers()`, `body()`, `uri()`, `version()` |

**Builder khác request:** `HttpRequest.Builder` không được bảo đảm an toàn cho nhiều thread chỉnh sửa đồng thời; `HttpRequest` sau `build()` là bất biến. Có thể dùng chung một `HttpClient` cho nhiều request; không cần khởi tạo client mới cho từng GET/POST.

Tạo HTTP client:

~~~java
// Fragment Java 17+; cần import java.net.http.*, java.time.Duration.
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NEVER)
        .version(HttpClient.Version.HTTP_1_1)
        .build();
~~~

Chọn HTTP/1.1 ở đây để kết nối với server minh họa. Trong dịch vụ thật có thể dùng HTTP/2, kiểm tra `response.version()` để biết phiên bản thực tế; cấu hình version là **preference**, không nhất thiết là phiên bản cuối cùng trong mọi môi trường. `followRedirects(NEVER)` hữu ích khi cần kiểm soát redirect và ngăn vô tình chuyển credentials sang host khác.

## 2. GET — đọc tài nguyên, thường không có request body

GET thường dùng để đọc danh sách/chi tiết tài nguyên. `HttpRequest.Builder.GET()` đặt method GET; nếu bạn không chỉ định method nào, builder cũng mặc định là GET. Trong API REST phổ biến, GET không dùng body, tham số truy vấn thuộc URI.

~~~java
// Fragment Java 17+, cần import URI, HttpRequest, Duration.
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/items?limit=10"))
        .timeout(Duration.ofSeconds(5))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

**Giải thích header:** `Accept: application/json` nói client mong **response JSON**. Đây không phải khai báo request body là JSON. Với GET không có body, thường **không cần đặt `Content-Type`**. Nếu server chỉ hỗ trợ loại khác, nó có thể trả lỗi (ví dụ 406 Not Acceptable), hoặc phản hồi theo chính sách của API.

### Encode query parameter đúng

Không ghép trực tiếp chuỗi nhập từ người dùng vào URI, đặc biệt khi có khoảng trắng, ký tự `&`, `=`, dấu tiếng Việt hoặc ký tự dành riêng:

~~~java
// Fragment dùng quy ước form-encoding cho GIÁ TRỊ query parameter.
String keyword = "Cà phê & sách";
String encoded = java.net.URLEncoder.encode(
        keyword, java.nio.charset.StandardCharsets.UTF_8);
URI uri = URI.create("https://example.com/items?q=" + encoded);
~~~

`URLEncoder` là encoder cho `application/x-www-form-urlencoded`, phù hợp với **giá trị query khi server giải mã theo quy ước này**: khoảng trắng có thể được viết thành `+`. Nó **không phải encoder chung để biến một URL bất kỳ thành URL hợp lệ**, và không nên dùng để encode toàn bộ path/URI. Với path segment chứa dữ liệu động, dùng cách xây URI/percent-encoding dành riêng cho path và làm rõ hợp đồng với server.

GET được định nghĩa là **safe** trong ngữ nghĩa HTTP: client yêu cầu xem dữ liệu, không chủ đích tạo side effect. Vì vậy, API không nên dùng GET để cập nhật trạng thái nghiệp vụ, thanh toán hoặc xóa dữ liệu. GET cũng là method **idempotent** theo ngữ nghĩa HTTP; không có nghĩa mọi lần đọc đều trả cùng một nội dung vì tài nguyên có thể thay đổi.

## 3. POST — gửi nội dung, thường tạo tài nguyên hoặc kích hoạt hành động

POST có thể tạo một item, gửi một lệnh nghiệp vụ, đăng nhập hoặc thực hiện một thao tác không có ngữ nghĩa idempotent mặc định. `POST(...)` nhận một **BodyPublisher**. Nếu gửi JSON, phải tạo JSON hợp lệ và khai báo media type phù hợp.

~~~java
// Fragment Java 17+; JSON ở đây được tạo thủ công chỉ để minh họa.
String json = "{\"name\":\"An\"}";

HttpRequest post = HttpRequest.newBuilder(
        URI.create("https://example.com/items"))
        .timeout(Duration.ofSeconds(5))
        .header("Accept", "application/json")
        .header("Content-Type", "application/json; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, java.nio.charset.StandardCharsets.UTF_8))
        .build();
~~~

Các điểm phải phân biệt:

- `BodyPublishers.ofString(json, UTF_8)` chuyển **chuỗi đã là JSON** thành bytes UTF-8. Nó **không** biến một Java POJO thành JSON. Khi có object Java phức tạp, dùng thư viện JSON serialization phù hợp để xử lý escaping, null, arrays, dates, v.v.
- `Content-Type: application/json; charset=UTF-8` mô tả body đang gửi. Với JSON, UTF-8 là cách mã hóa tương thích phổ biến; một số API yêu cầu chính xác `application/json`, không có parameter, nên **theo hợp đồng server**.
- `Accept: application/json` mô tả body response muốn nhận; khác hoàn toàn `Content-Type`.
- `POST` thông thường **không được giả định idempotent**. Khi request bị timeout, server có thể đã xử lý thành công trước khi client thấy kết quả. Retry tự động có thể tạo dữ liệu trùng; cần idempotency key hoặc giao thức dedup khi phù hợp.

HTTP POST có thể trả `201 Created` cùng `Location` khi tạo tài nguyên, nhưng còn phụ thuộc API. Không mặc định rằng POST thành công chỉ khi status 200; hãy đọc tài liệu cụ thể.

### Không phải POST nào cũng là JSON

Nếu server yêu cầu form body:

~~~java
// Fragment Java 17+.
String form = "name=" + java.net.URLEncoder.encode(
        "Nguyễn An", java.nio.charset.StandardCharsets.UTF_8)
        + "&active=true";

HttpRequest formPost = HttpRequest.newBuilder(
        URI.create("https://example.com/forms"))
        .header("Content-Type",
                "application/x-www-form-urlencoded; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                form, java.nio.charset.StandardCharsets.UTF_8))
        .build();
~~~

Nếu server yêu cầu raw bytes hoặc tệp, dùng `BodyPublishers.ofByteArray(...)` hoặc `ofFile(path)` với media type chính xác. **Multipart/form-data** đòi cấu trúc nhiều part và boundary trùng với body; không chỉ đặt header `multipart/form-data` rồi gửi một chuỗi JSON. Với `ofInputStream(...)`/publisher dạng stream, cần nghĩ tới khả năng đọc lại body khi retry, redirect hoặc xác thực; không mặc định một nguồn stream có thể phát lại.

## 4. PUT — gửi representation để tạo/thay thế trạng thái tài nguyên

PUT thường nhắm tới **URI cụ thể của tài nguyên** và yêu cầu server tạo hoặc thay thế representation tại URI đó (tùy chính sách). Trong thiết kế REST phổ biến, PUT thường gửi **toàn bộ representation cần được thay thế**, khác với PATCH chỉ áp một thay đổi từng phần.

~~~java
// Fragment Java 17+.
String fullItem = "{\"id\":7,\"name\":\"Binh\",\"active\":true}";

HttpRequest put = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/items/7"))
        .header("Accept", "application/json")
        .header("Content-Type", "application/json; charset=UTF-8")
        .PUT(HttpRequest.BodyPublishers.ofString(
                fullItem, java.nio.charset.StandardCharsets.UTF_8))
        .build();
~~~

PUT là **idempotent theo ý nghĩa HTTP**: gửi lại cùng yêu cầu với cùng URI/body dự kiến có cùng tác động mục tiêu lên tài nguyên như gửi một lần (bỏ qua các hiệu ứng phụ như log/timestamps được mô tả riêng). Điều đó **không có nghĩa** mạng bảo đảm đúng một request đến server, response luôn giống hệt, hoặc tự động retry luôn an toàn với mọi API custom.

Nếu nhiều client cùng cập nhật một item, dùng **conditional request** khi server hỗ trợ, ví dụ `If-Match: "etag-value"` để chống ghi đè thay đổi của người khác:

~~~java
// Fragment: ETag phải được lấy từ response trước đó của chính tài nguyên.
// Không bịa một ETag; giá trị nhận từ server có thể có dấu ngoặc kép.
HttpRequest conditionalPut = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/items/7"))
        .header("If-Match", "\"revision-7\"")
        .header("Content-Type", "application/json")
        .PUT(HttpRequest.BodyPublishers.ofString(
                "{\"id\":7,\"name\":\"Binh\"}"))
        .build();
~~~

Đây chỉ là mẫu cấu hình header: `revision-7` không phải ETag thực được một server xác nhận. Server hỗ trợ precondition có thể trả `412 Precondition Failed` nếu representation không còn khớp. Một endpoint không hỗ trợ ETag/If-Match có thể có hành vi khác; cần xem contract.

## 5. Method tùy chọn: PATCH, OPTIONS, REPORT và các động từ khác

`HttpRequest.Builder` có các phương thức tiện ích `GET()`, `POST(publisher)`, `PUT(publisher)` và `DELETE()`. Khi API cần một method khác (phổ biến nhất là **PATCH**), dùng:

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/items/7"))
        .header("Content-Type", "application/merge-patch+json")
        .header("Accept", "application/json")
        .method("PATCH", HttpRequest.BodyPublishers.ofString(
                "{\"name\":\"Chi\"}",
                java.nio.charset.StandardCharsets.UTF_8))
        .build();
~~~

`method(String method, BodyPublisher bodyPublisher)` đặt **cả tên method lẫn nguồn body**. Tên method phải là token HTTP hợp lệ; Java không tự sáng tạo ngữ nghĩa cho method và **server/proxy phải hỗ trợ nó**. Chẳng hạn, một gateway có thể từ chối PATCH hoặc REPORT dù Java tạo request hợp lệ.

Dùng `BodyPublishers.noBody()` khi method không có request body:

~~~java
// Fragment — server phải hỗ trợ OPTIONS ở endpoint này.
HttpRequest options = HttpRequest.newBuilder(
        URI.create("https://example.com/items"))
        .method("OPTIONS", HttpRequest.BodyPublishers.noBody())
        .build();
~~~

`PATCH` khác PUT ở ý nghĩa: nó áp dụng **một tài liệu mô tả thay đổi**, chứ không nhất thiết thay thế toàn bộ representation. `application/merge-patch+json` dành cho **JSON Merge Patch** (RFC 7396); `application/json-patch+json` dành cho **JSON Patch** (RFC 6902), có cấu trúc khác. Không thể đổi hai media type mà vẫn dùng cùng body nếu server phân biệt đúng chuẩn. PATCH **không tự động idempotent**; tính chất retry phụ thuộc patch document và hợp đồng API.

Với DELETE không body thông thường, dùng `DELETE()`. Nếu một API đặc thù thật sự yêu cầu DELETE có body, có thể dùng `method("DELETE", BodyPublishers.ofString(...))`, nhưng không xem đó là quy tắc phổ quát: nhiều server/proxy không hỗ trợ body theo cách mong muốn.

### Bảng chọn method theo intent

| Method | Intent thường gặp | Body gửi | Tính chất HTTP cần nhớ |
| --- | --- | --- | --- |
| `GET` | Đọc resource/list | Thường không | Safe, idempotent theo ngữ nghĩa |
| `POST` | Tạo, gửi lệnh, xử lý | Thường có | Không mặc định idempotent |
| `PUT` | Thay thế trạng thái tại URI xác định | Thường có | Idempotent theo ngữ nghĩa |
| `PATCH` | Cập nhật một phần theo patch format | Thường có | Không mặc định idempotent |
| `DELETE` | Yêu cầu xóa tài nguyên | Thường không | Idempotent theo ngữ nghĩa, response có thể khác |
| `OPTIONS` | Hỏi khả năng giao tiếp/các method | Thường không | Server phải hỗ trợ; response có thể chứa `Allow` |
| Method riêng | Do server và client thỏa thuận | Tùy hợp đồng | Không có ngữ nghĩa chung nếu không được đặc tả |

**Không dùng “method tùy chọn” để né kiểm tra quyền.** API server vẫn phải xác thực, phân quyền theo method/resource và xử lý payload theo schema. CORS của browser cũng là chủ đề riêng: Java HttpClient **không phải browser** và không bị chính sách CORS của trình duyệt chặn như JavaScript chạy từ website.

## 6. Gửi header đúng: Content-Type, Accept, Authorization và các trường khác

Một HTTP header gồm **tên** và **giá trị**; tên header không phân biệt hoa/thường về ngữ nghĩa. Trong Java:

~~~java
// Fragment — các lời gọi builder.
HttpRequest.Builder builder = HttpRequest.newBuilder()
        .header("Accept", "application/json")
        .header("Content-Type", "application/json")
        .header("X-Request-ID", "req-42");
~~~

### Header quan trọng nhất

| Header | Ai dùng và để làm gì? | Lưu ý |
| --- | --- | --- |
| `Accept` | Request: mô tả media type phản hồi mà client mong muốn | Chọn theo **response** API trả, ví dụ `application/json` hoặc `text/plain` |
| `Content-Type` | Request: mô tả **body gửi đi** | Khớp JSON/form/binary/patch, charset nếu đúng contract; GET không body thường không cần |
| `Authorization` | Request: credentials như `Bearer <token>` theo cơ chế API | Không hard-code, không log/reveal token, không gửi tới host lạ |
| `If-Match` | Request: điều kiện update dựa trên ETag | Giúp tránh lost update nếu server hỗ trợ precondition |
| `If-None-Match` | Request: conditional retrieval/cache với ETag | Server có thể trả `304 Not Modified` không có body |
| `Accept-Language` | Request: ngôn ngữ response ưu tiên | Không bảo đảm server có translation |
| `User-Agent` | Request: nhận diện client khi được phép | Tùy server; không phải bằng chứng xác thực |
| `X-Request-ID` / `traceparent` | Correlation/tracing theo hợp đồng giữa hệ thống | Không tự động tồn tại; nên tạo ID an toàn và log đối chiếu |
| `Content-Length` | Số bytes request body trên wire | Thường do HttpClient/BodyPublisher tính, **không tự đặt** |
| `Host`, `Connection`, HTTP/2 pseudo-headers | Header và metadata transport/protocol | Để HttpClient quản lý, có thể thuộc danh sách restricted |
| `Content-Encoding` | Cách body được content-encoded, ví dụ gzip | Chỉ đặt khi body **thực sự** đã mã hóa theo cách đó; không nhầm với charset |
| `Accept-Encoding` | Biểu thị mã hóa response client chấp nhận | Chỉ quảng cáo khi có handler/logic giải nén phù hợp; theo contract/client |

**Đặc biệt:** `Content-Type` không phải định dạng mà **client muốn nhận**; `Accept` không phải định dạng mà **client đang gửi**. Có thể gửi JSON nhưng yêu cầu nhận `text/plain`: điều này hoàn toàn hợp lệ nếu server cung cấp response text. Ví dụ kiểm thử sau sử dụng chính cặp header đó.

### Tránh header sai/hạn chế

Một số header được HttpClient quản lý hoặc hạn chế vì lý do giao thức/bảo mật. Tài liệu `HttpRequest.Builder.header/setHeader` nêu việc implementation có thể ném `IllegalArgumentException` với **tên/giá trị không hợp lệ hoặc restricted**; `Content-Length` là ví dụ Javadoc nhắc rõ.

Đừng cố tự set `Content-Length` bằng `json.length()`: đó là số **ký tự UTF-16 của String**, không nhất thiết bằng số byte UTF-8. BodyPublisher quản lý byte count/publishing; với body stream chưa biết chiều dài, framing có thể khác. Tự set sai `Content-Length` có thể làm server đọc thiếu/thừa body hoặc gặp protocol error.

Không đưa CR/LF hay dữ liệu header chưa validate từ người dùng vào tên/giá trị. Header splitting/injection và newline không hợp lệ sẽ gây rủi ro; builder có kiểm tra cú pháp nhưng code vẫn phải kiểm soát giá trị nghiệp vụ (ví dụ không cho người dùng ghi đè Authorization).

### `header()`, `headers()`, `setHeader()` khác nhau thế nào?

- `header(name, value)`: **thêm** một giá trị cho header. Nếu đã có cùng tên, các giá trị được giữ thành nhiều giá trị.
- `headers(name1, value1, name2, value2, ...)`: thêm theo từng **cặp name-value**; số chuỗi phải chẵn và tên/giá trị hợp lệ.
- `setHeader(name, value)`: **thay thế tất cả giá trị trước đó** của header cùng tên trong builder bằng một giá trị mới.

~~~java
HttpRequest.Builder b = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/items"))
        .header("X-Trace", "temporary")
        .setHeader("X-Trace", "request-42")
        .GET();

HttpRequest request = b.build();
// Request khai báo X-Trace: request-42, không còn temporary.
~~~

Với header đơn trị như `Authorization` hoặc `Content-Type`, dùng `setHeader` khi cần cập nhật để không vô tình tạo nhiều giá trị trái contract. Một số header hợp lệ nhiều giá trị (như `Accept` trong nhiều cách biểu diễn), nhưng không nên tự append trùng nếu không chủ đích. `HttpRequest.headers().firstValue("X-Trace")` có thể kiểm tra cấu hình header **đã đặt trong request**; những header được HttpClient tự sinh trên wire có thể không xuất hiện như value do user khai báo.

**Quan trọng với redirect:** nếu request chứa Authorization hoặc API key, không tự động forward credentials sang host khác khi server chuyển hướng. `followRedirects(NEVER)` là lựa chọn dễ audit; nếu bật redirect, cần hiểu quy tắc cross-origin, scheme downgrade và phạm vi trust.

## 7. Authentication và cấu hình bí mật

Có thể đặt header Bearer khi API yêu cầu:

~~~java
// Fragment Java 17+: chỉ dành cho host HTTPS tin cậy, được cấu hình.
String token = System.getenv("API_TOKEN");
if (token == null || token.isBlank()) {
    throw new IllegalStateException("Missing API_TOKEN");
}

HttpRequest secure = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/private/items"))
        .setHeader("Authorization", "Bearer " + token)
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

Đây là **fragment**, không phải chương trình có thể chạy với endpoint minh họa: cần tài khoản/API thật, URI đúng, và token được cấp. Không ghi token vào mã nguồn, console, log HTTP request hoặc file chia sẻ. Chỉ gửi token qua HTTPS tới host đã xác minh và cân nhắc chuyển tiếp proxy/redirect. Các API còn có thể dùng cookie, Basic authentication, OAuth, HMAC signing hoặc mTLS theo hợp đồng; không tự giả định mọi API dùng Bearer.

Lưu ý `Authorization` trong ví dụ là **request header**, không phải header chứng minh HTTP server đã xác thực thành công. Phải kiểm tra status và response. Với HTTP 401, server có thể trả `WWW-Authenticate`; với 403, tài khoản có thể đã xác thực nhưng thiếu quyền. Không quy hết mọi 401/403 cho lỗi mạng hoặc retry vô hạn.

## 8. Ví dụ chạy được: GET, POST, PUT, PATCH và kiểm tra header trên Java 17+

Phần này tạo một **HTTP server loopback** bằng module JDK `jdk.httpserver` để **chỉ echo request**. Nó không lưu database, không thật sự tạo/sửa item; response code được chọn để minh họa cách nhận status. Nhờ vậy, kết quả **không phụ thuộc API ngoài, DNS, credentials hay Internet**. Client được ép sử dụng HTTP/1.1 để tương thích server mẫu.

Tệp duy nhất **`HttpMethodsDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
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
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpMethodsDemo {

    private static final Charset UTF8 = StandardCharsets.UTF_8;

    private static String show(String value) {
        return value == null ? "-" : value;
    }

    // Endpoint local chỉ echo; không sửa dữ liệu ứng dụng.
    private static void handle(HttpExchange ex) throws IOException {
        String requestBody;
        try (InputStream in = ex.getRequestBody()) {
            byte[] bytes = in.readAllBytes();
            requestBody = bytes.length == 0
                    ? "-" : new String(bytes, UTF8);
        }

        String result = ex.getRequestMethod()
                + " " + ex.getRequestURI()
                + " | Accept="
                + show(ex.getRequestHeaders().getFirst("Accept"))
                + " | Content-Type="
                + show(ex.getRequestHeaders().getFirst("Content-Type"))
                + " | X-Trace="
                + show(ex.getRequestHeaders().getFirst("X-Trace"))
                + " | body=" + requestBody;

        byte[] response = result.getBytes(UTF8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");

        // Chỉ minh họa HTTP status, không tạo record thật.
        int status = "POST".equals(ex.getRequestMethod())
                ? 201 : 200;
        ex.sendResponseHeaders(status, response.length);

        try (OutputStream out = ex.getResponseBody()) {
            out.write(response);
        }
    }

    private static void send(
            HttpClient client, HttpRequest request) throws Exception {
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString(UTF8));

        System.out.println(
                request.method() + " -> "
                + response.statusCode()
                + " | " + response.body());
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext("/items", HttpMethodsDemo::handle);
        server.start();

        try {
            String root = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            // GET: chỉ yêu cầu text response, không có body.
            // setHeader thay thế giá trị X-Trace đặt trước đó.
            HttpRequest get = HttpRequest.newBuilder(
                    URI.create(root + "/items?limit=2"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Accept", "text/plain")
                    .header("X-Trace", "temporary")
                    .setHeader("X-Trace", "get-1")
                    .GET()
                    .build();

            // POST: gửi JSON request, nhận text/plain response.
            HttpRequest post = HttpRequest.newBuilder(
                    URI.create(root + "/items"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Accept", "text/plain")
                    .header("Content-Type",
                            "application/json; charset=UTF-8")
                    .header("X-Trace", "post-1")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "{\"name\":\"An\"}", UTF8))
                    .build();

            // PUT: representation gửi tới URI của item cụ thể.
            HttpRequest put = HttpRequest.newBuilder(
                    URI.create(root + "/items/7"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Accept", "text/plain")
                    .header("Content-Type",
                            "application/json; charset=UTF-8")
                    .header("X-Trace", "put-1")
                    .PUT(HttpRequest.BodyPublishers.ofString(
                            "{\"name\":\"Binh\"}", UTF8))
                    .build();

            // PATCH: method() với body format dành cho Merge Patch.
            HttpRequest patch = HttpRequest.newBuilder(
                    URI.create(root + "/items/7"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Accept", "text/plain")
                    .header("Content-Type",
                            "application/merge-patch+json")
                    .header("X-Trace", "patch-1")
                    .method("PATCH",
                            HttpRequest.BodyPublishers.ofString(
                                    "{\"name\":\"Chi\"}", UTF8))
                    .build();

            send(client, get);
            send(client, post);
            send(client, put);
            send(client, patch);
        } finally {
            server.stop(0);
        }
    }
}
~~~

**Biên dịch và chạy trên JDK 17+:**

~~~bash
javac HttpMethodsDemo.java
java HttpMethodsDemo
~~~

Trên một số cấu hình module-path tường minh có thể cần thêm `--add-modules jdk.httpserver` khi biên dịch/chạy vì demo sử dụng API `com.sun.net.httpserver`. Với JDK chuẩn chạy trên classpath/unnamed module, module này thường được resolve tự động. **Không** dùng dependency hoặc server HTTP ngoài JDK.

**Đầu ra đã kiểm tra trên JDK 24 qua JShell, với localhost HTTP/1.1:**

~~~text
GET -> 200 | GET /items?limit=2 | Accept=text/plain | Content-Type=- | X-Trace=get-1 | body=-
POST -> 201 | POST /items | Accept=text/plain | Content-Type=application/json; charset=UTF-8 | X-Trace=post-1 | body={"name":"An"}
PUT -> 200 | PUT /items/7 | Accept=text/plain | Content-Type=application/json; charset=UTF-8 | X-Trace=put-1 | body={"name":"Binh"}
PATCH -> 200 | PATCH /items/7 | Accept=text/plain | Content-Type=application/merge-patch+json | X-Trace=patch-1 | body={"name":"Chi"}
~~~

**Ý nghĩa từng dòng:**

1. **GET:** endpoint nhận `GET /items?limit=2`. Body `-` nghĩa là **không có body**; không có request `Content-Type`. `X-Trace=get-1` chứng minh `setHeader` đã thay `temporary`. Query được giữ trong request-target.
2. **POST:** publisher gửi JSON UTF-8 `{"name":"An"}`, server nhận `Content-Type: application/json; charset=UTF-8` và `Accept: text/plain`. Status 201 là lựa chọn của **server demo**, không phải cam kết đã tạo item thật.
3. **PUT:** gửi body JSON tới `/items/7`, status 200. Server chỉ echo chứ không chứng minh PUT đã thay representation.
4. **PATCH:** `method("PATCH", ...)` tạo đúng method và body, đồng thời header `application/merge-patch+json` tới server local. Demo không áp dụng JSON Merge Patch thực tế; nó chỉ kiểm tra việc tạo/gửi HTTP request đúng.

**Vì sao mã không cần mạng ngoài?** `HttpServer` lắng nghe tại `127.0.0.1` và cổng `0`; OS chọn một cổng còn trống. Client lấy cổng thực qua `server.getAddress().getPort()`, không hard-code port. `server.stop(0)` dừng server ở `finally`, kể cả khi request ném lỗi. Trong môi trường bị cấm mở socket loopback, bài thử có thể thất bại vì policy dù code Java hợp lệ.

**Giới hạn an toàn của demo:** server đọc toàn bộ body vào RAM và echo trực tiếp input. Chỉ nên chạy với những request nhỏ, tin cậy trên loopback. Server production phải giới hạn kích thước request, validate schema/method, xác thực, authorization, content negotiation, tránh phản chiếu dữ liệu nhạy cảm và quản lý HTTP error responses. Không mở public port hoặc dùng echo handler này như một service Internet.

## 9. Đọc response đúng: không chỉ lấy `body()`

API:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

int status = response.statusCode();
String body = response.body();
String contentType = response.headers()
        .firstValue("Content-Type").orElse("-");
System.out.println(status + " " + contentType);
~~~

**Phải kiểm tra status**, vì `send()` thường **không ném exception chỉ vì HTTP 4xx hoặc 5xx**: đây vẫn là response HTTP hợp lệ. `BodyHandlers.ofString(...)` chuyển body thành String; nó không parse JSON, cũng không tự từ chối status lỗi.

| Nhóm status | Ý nghĩa thường gặp | Xử lý ứng dụng |
| --- | --- | --- |
| 2xx | Thành công ở tầng HTTP | Kiểm tra schema/body/side effects phù hợp endpoint |
| 3xx | Điều hướng/cache/conditional | Xem `Location`, `ETag`, `304`; đừng mù quáng follow redirect có token |
| 400 | Request không hợp lệ | Kiểm tra URI, method, body, validation và Content-Type |
| 401 / 403 | Unauthorized / Forbidden | Kiểm tra cơ chế xác thực/quyền, không log bí mật |
| 404 | Không có resource/route | Kiểm tra URI, path, resource id |
| 405 | Method Not Allowed | Server không hỗ trợ method ở endpoint; xem header `Allow` nếu có |
| 406 / 415 | Accept không được đáp ứng / Content-Type không hỗ trợ | Kiểm tra media type/contract |
| 409 / 412 | Conflict / precondition không còn đúng | Phải reconcile version/ETag, không ghi đè mù quáng |
| 429 | Rate limited | Backoff dựa trên policy và `Retry-After` nếu có |
| 5xx | Server-side error hoặc gateway lỗi | Retry chỉ khi phù hợp idempotency và retry budget |

**Một POST tạo resource** thường trả 201, có thể chứa header `Location` chỉ URI resource mới. Một DELETE thành công có thể trả 204 No Content, vì vậy đừng ép mọi response phải chứa JSON. Với 204/304, không nên cố parse body rỗng.

Tài liệu `HttpResponse.BodyHandlers.ofString(Charset)` dùng charset bạn chỉ định. `ofString()` không tham số dùng charset từ response `Content-Type` nếu có và được hỗ trợ, nếu không thì UTF-8. Với API có encoding cố định, chọn charset tường minh để dễ kiểm soát. Với JSON, **String response không phải object JSON**; vẫn cần parse/validate response trước khi dùng.

Ví dụ kiểm tra status hợp đồng:

~~~java
// Fragment helper trong một class Java 17+.
static String requireSuccess(HttpResponse<String> response)
        throws java.io.IOException {
    int status = response.statusCode();
    if (status < 200 || status >= 300) {
        throw new java.io.IOException(
                "HTTP status " + status
                + ", response length="
                + response.body().length());
    }
    return response.body();
}
~~~

Ví dụ chỉ nêu status và độ dài response thay vì log toàn bộ body lỗi — body có thể chứa dữ liệu nhạy cảm. Hệ thống thật cần phân loại lỗi API chi tiết hơn và giới hạn kích thước body đọc vào bộ nhớ.

## 10. Timeout, exception và retry cho từng method

Cần phân biệt:

- `HttpClient.Builder.connectTimeout(Duration)`: giới hạn thời gian **thiết lập một kết nối mới** khi cần. Nếu client sử dụng lại kết nối đã tồn tại, không nhất thiết có bước connect mới.
- `HttpRequest.Builder.timeout(Duration)`: cấu hình timeout của **request/response exchange** theo API; nếu không nhận response đúng hạn, request có thể ném `HttpTimeoutException`.
- `client.send(...)`: đồng bộ, chặn luồng gọi tới khi nhận response theo `BodyHandler` hoặc thất bại.
- `client.sendAsync(...)`: trả `CompletableFuture<HttpResponse<T>>`; hoàn thành bình thường hoặc exceptionally, không tự làm mọi thao tác server có idempotency.
- Timeout **không chứng minh** server chưa nhận/thi hành request. Đặc biệt với POST, tình trạng “server đã commit, client không thấy reply” rất quan trọng.

Bắt lỗi với synchronous send:

~~~java
// Fragment Java 17+; request và client đã được tạo.
try {
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));
    System.out.println("HTTP status " + response.statusCode());
} catch (java.net.http.HttpTimeoutException timeout) {
    // Request timeout; server có thể vẫn đã xử lý.
} catch (java.io.IOException networkOrTlsError) {
    // DNS/connection/reset/TLS/framing/transport... cần phân loại.
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Trả quyền điều khiển và xử lý cleanup phù hợp.
}
~~~

Khi dùng `sendAsync`:

~~~java
// Fragment: trả future ngay, không bắt buộc đợi bằng join().
java.util.concurrent.CompletableFuture<HttpResponse<String>> pending =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

pending.thenAccept(response -> {
    System.out.println("HTTP status " + response.statusCode());
}).exceptionally(error -> {
    // Log nguyên nhân có kiểm soát, không log credentials.
    return null;
});
~~~

Nếu code gọi `pending.join()` ngay trên thread hiện tại, bạn lại chặn thread đó, chỉ đổi cú pháp chờ. Các exception từ asynchronous stage có thể được bọc trong `CompletionException`; cần quan sát cause. Khi hủy `CompletableFuture` của HTTP exchange, Java cố hủy để giải phóng tài nguyên nhưng không bảo đảm thời điểm hủy có hiệu lực: server có thể đã nhận và xử lý request.

### Retry: khác nhau theo method

| Method | Có thể retry ngay khi timeout không? |
| --- | --- |
| `GET` | Thường có thể retry với giới hạn/throttling, nhưng phải lưu ý dữ liệu thay đổi và side effect từ API triển khai sai |
| `PUT` | Theo ngữ nghĩa idempotent, retry **có thể** hợp lý; kiểm tra precondition, version và custom business logic |
| `POST` | **Không retry mù quáng**: có thể tạo 2 order/charge nếu request đầu đã thành công |
| `PATCH` | Tùy patch format/thao tác; không mặc định idempotent |
| `DELETE` | Idempotent về trạng thái dự kiến, nhưng retry có thể nhận 404 sau lần xóa thành công; xử lý theo contract |

Một retry policy tốt có số lần thử giới hạn, backoff + jitter, deadline tổng, xét 429/503 cùng `Retry-After` và phát hiện lỗi không thể phục hồi. Nếu nghiệp vụ cần exactly-once effect, phải có cơ chế phía server như idempotency key, conditional update hoặc deduplication; HTTP method/idempotency chỉ là một phần của bài toán.

## 11. Headers và dữ liệu nhạy cảm: bảo mật và đúng phạm vi

Đặt header đúng còn liên quan bảo mật, không chỉ giao thức:

1. **Không lưu Bearer/API key trong source hoặc log.** Dùng cấu hình bảo mật, secret manager hoặc biến môi trường trong demo nội bộ. Nếu cần chia sẻ log, xóa giá trị `Authorization`, `Cookie` và token trong query.
2. **HTTPS ở môi trường thật.** Demo dùng HTTP loopback vì muốn kiểm tra API không phụ thuộc cert; không gửi Bearer token qua HTTP plain-text ngoài môi trường được kiểm soát.
3. **Không nhận URI tùy ý từ input để forward request với credentials.** Validate scheme, host allowlist, port, redirects và đường dẫn để phòng SSRF/exfiltration.
4. **Không giả định 2xx nghĩa là body đã đúng kiểu.** Server có thể trả HTML/error page dù client gửi Accept JSON; kiểm tra Content-Type và parse/validate response.
5. **Không tự cho phép Host, Content-Length, Connection hoặc HTTP/2 pseudo headers qua data user.** Đó là lớp transport do HttpClient quản lý; có thể bị từ chối hoặc gây protocol mismatch.
6. **Không gộp nhầm header và body.** Với `application/json` body phải là JSON hợp lệ; với form body phải được encode đúng; với multipart cần boundary và format part.
7. **Không lạm dụng `Expect: 100-continue`.** Nếu có nhu cầu tối ưu gửi body lớn, dùng `expectContinue(true)` khi server/proxy hỗ trợ và hiểu vòng interim response; không tự kết luận server đã xử lý request chỉ từ status 100.
8. **Không chia sẻ mutable request builder giữa thread.** Tạo builder theo request hoặc phối hợp an toàn; `HttpRequest` đã build mới là immutable.

Môi trường proxy, load balancer, CDN hoặc API gateway cũng có thể áp giới hạn header size, loại header hop-by-hop, chặn phương thức tùy chọn và biến đổi URI. Khi 405/415 xảy ra, phải kiểm tra cả endpoint ở upstream lẫn API gateway, không chỉ code client.

## 12. Những lỗi thường gặp khi tạo GET/POST/PUT/PATCH

**Lỗi A — POST JSON nhưng server nói body sai format.**  
Kiểm tra body có JSON hợp lệ không, serializer đã escape đúng ký tự Unicode và dấu ngoặc kép chưa, `Content-Type` có đúng `application/json` theo contract không, charset của bytes có khớp không. `BodyPublishers.ofString` không parse hay validate JSON.

**Lỗi B — Chỉ đặt Accept mà quên Content-Type.**  
`Accept` mô tả **response**, không dạy server cách parse request. Với POST/PUT/PATCH có body, khai báo media type của request body khi API yêu cầu.

**Lỗi C — GET gửi body không cần thiết.**  
GET thông thường nên mang query trong URI; server/proxy/cache không thống nhất ý nghĩa request GET có body. Không dùng `method("GET", ofString(...))` như giải pháp mặc định chỉ để tránh encode query.

**Lỗi D — Gặp 415 Unsupported Media Type.**  
Server không hỗ trợ request `Content-Type` hoặc format payload đang gửi. Phân biệt body Merge Patch và JSON Patch; kiểm tra chính xác media type của endpoint, không tự đổi tùy tiện.

**Lỗi E — Gặp 406 Not Acceptable.**  
Client yêu cầu response media type không được server cung cấp. Nếu chỉ muốn `text/plain`, đặt `Accept: text/plain`; nếu server chỉ trả JSON, đặt media type đúng và dùng JSON parser.

**Lỗi F — Gặp 405 Method Not Allowed khi dùng PATCH/custom method.**  
Java có thể gửi method, nhưng server/resource/gateway không hỗ trợ. Kiểm tra `Allow` khi có, API contract và cấu hình proxy. Không lén đổi PATCH thành POST nếu API không cho phép.

**Lỗi G — Header lặp ngoài ý muốn.**  
`header` thêm giá trị; gọi hai lần với `Authorization` hoặc `Content-Type` có thể tạo request mơ hồ. Nếu chỉ cần một giá trị, dùng `setHeader` và kiểm tra `request.headers()` trước khi gửi.

**Lỗi H — Tự set Content-Length rồi bị exception.**  
HttpClient quản lý độ dài dựa trên BodyPublisher và có thể cấm tên header. Ngoài ra `String.length()` không phải byte count UTF-8. Bỏ header đó; gửi body publisher đúng.

**Lỗi I — GET query có ký tự tiếng Việt/`&` và request bị cắt thành hai tham số.**  
Encode **giá trị** query theo chuẩn server, không nối input raw. Đừng dùng `URLEncoder` để encode nguyên URI hoặc path segment.

**Lỗi J — `client.send` trả response 401/500 nhưng không ném IOException.**  
HTTP status code lỗi vẫn là HTTP response hợp lệ. Kiểm tra `response.statusCode()`, header và body schema rồi xử lý theo nghiệp vụ.

**Lỗi K — POST bị gửi hai lần vì retry sau timeout.**  
Timeout có thể xảy ra sau khi server đã ghi DB. Cần idempotency key, correlation ID, dedup hoặc query trạng thái request thay vì retry ngay.

**Lỗi L — PUT cập nhật đè thay đổi của người khác.**  
Dùng ETag/`If-Match` khi backend hỗ trợ, xử lý 412/409; không chỉ vì PUT idempotent mà coi nó an toàn với race đồng thời.

**Lỗi M — Response có ký tự lỗi do encoding.**  
Kiểm tra Content-Type charset và dữ liệu bytes; `BodyHandlers.ofString(UTF_8)` giả định UTF-8. Nếu API trả charset khác, chọn handler/decoder tương ứng theo contract.

**Lỗi N — Dùng một HttpClient cho mỗi request và bị chậm.**  
HttpClient được thiết kế tái sử dụng các kết nối và nguồn lực. Có thể dùng một client theo cấu hình trust/proxy/timeout chung; tạo mới chỉ khi có lý do về isolation hoặc cấu hình.

**Lỗi O — Test HTTP request vào public API nhưng response không như demo.**  
Server loopback ở đây **chỉ echo** và tự gán status, không có persistence/authorization. API thật phải có URI, quyền, schema và status code riêng; đừng lấy output demo làm lời hứa về mọi server.

## 13. Hướng dẫn chẩn đoán có hệ thống

Khi HTTP call không thành công, kiểm tra theo thứ tự:

~~~text
1. URL/URI
   - Scheme là http hay https?
   - Host/path/query đúng? Query values đã encode?
   - Đúng resource id và environment (dev/staging/prod)?

2. Method
   - GET / POST / PUT / PATCH đúng contract?
   - Custom method được server/gateway hỗ trợ?
   - Body có phù hợp với method và endpoint?

3. Headers
   - Accept là media type response mong đợi?
   - Content-Type là media type BODY GỬI thực tế?
   - Authorization/token đúng và không bị lộ?
   - Có lặp header() ngoài ý muốn?
   - Có cố set header restricted?

4. Transport
   - TLS certificate/hostname, DNS, proxy, firewall?
   - Connect timeout khác request timeout?
   - Có redirect sang host/scheme khác?

5. Response
   - HTTP status?
   - Content-Type response?
   - Location / Allow / ETag / Retry-After / WWW-Authenticate?
   - Body lỗi có cấu trúc gì? Có được phép log không?

6. Retry / tác dụng phụ
   - Server có thể đã xử lý request trước timeout?
   - Method idempotent theo contract?
   - Có idempotency key hoặc If-Match?
~~~

Ghi log an toàn các trường như correlation ID, method, route template, status, latency, response Content-Type, retry count và error category. **Không** log raw Authorization, cookies, password hoặc toàn bộ body cá nhân. Để so sánh request thực sự được server nhận, một echo endpoint như demo là công cụ học tốt; không để echo không kiểm soát trên public network.

## 14. Bài tập thực hành và đáp án

**Câu 1:** Client gửi `POST` body `{"name":"An"}` và muốn nhận JSON, cần headers nào?  
**Đáp án:** Thường dùng `Content-Type: application/json` cho body gửi và `Accept: application/json` cho body response. Charset và yêu cầu cụ thể theo API contract; BodyPublisher gửi bytes, không tự set Content-Type.

**Câu 2:** Client gọi `GET()` không body. Có cần `Content-Type: application/json` không?  
**Đáp án:** Thường không. Dùng `Accept: application/json` nếu muốn response JSON; query đặt trong URI.

**Câu 3:** Builder gọi `header("X-Trace","a")` rồi `header("X-Trace","b")`; có giữ cả hai không?  
**Đáp án:** Có, builder thêm nhiều giá trị. Nếu muốn thay bằng một giá trị, dùng `setHeader("X-Trace","b")`.

**Câu 4:** Vì sao không tự gán `Content-Length=json.length()`?  
**Đáp án:** Giá trị là số byte trên wire, không phải ký tự Java; còn do BodyPublisher/HttpClient quản lý và có thể là restricted header.

**Câu 5:** Java 17 muốn gửi PATCH body JSON Merge Patch, dùng API nào?  
**Đáp án:** `.method("PATCH", BodyPublishers.ofString(patchJson, UTF_8))` với `Content-Type: application/merge-patch+json` khi server yêu cầu. Kiểm tra hỗ trợ PATCH ở backend.

**Câu 6:** POST trả `201 Created` mà `client.send` không ném exception. Đã có item thật chưa?  
**Đáp án:** Chỉ biết server trả 201. Kiểm tra tài liệu API, response body/Location và trạng thái nghiệp vụ. Demo local gán 201 nhưng không lưu item.

**Câu 7:** `client.send` trả `415 Unsupported Media Type`. Nên sửa gì trước?  
**Đáp án:** Kiểm tra request `Content-Type` và format bytes thực sự gửi; phân biệt JSON, form, Merge Patch và JSON Patch.

**Câu 8:** PUT cùng URI/body được gửi lại hai lần có phải luôn tạo 2 resource?  
**Đáp án:** Theo ngữ nghĩa HTTP, PUT idempotent về tác động mục tiêu, nhưng server custom có thể có side effects/điều kiện khác. Không suy luận mọi request được thi hành đúng một lần; kiểm tra contract và concurrency control.

**Câu 9:** HTTP 401 có khiến `client.send` tự ném `IOException` không?  
**Đáp án:** Không chỉ vì status 401. Thường bạn vẫn nhận `HttpResponse` và phải kiểm tra `statusCode()`, headers, body.

**Câu 10:** `GET /items?q=Cà phê & sách` được ghép trực tiếp từ input; nguy cơ gì?  
**Đáp án:** URI không hợp lệ hoặc `&` bị phân tích thành query parameter mới. Encode giá trị query theo quy ước của server; không encode nguyên URI một lần.

**Câu 11:** Sau timeout POST, nên retry ngay khi gặp mọi `IOException` không?  
**Đáp án:** Không. Server có thể đã xử lý tạo đơn hàng hoặc thanh toán. Cần idempotency key/dedup, retry policy có giới hạn và xem lỗi có thể phục hồi.

**Câu 12:** Java HttpClient có bị CORS browser hạn chế như JavaScript trong trang web không?  
**Đáp án:** Không theo cùng cơ chế bảo mật của browser. Tuy nhiên server vẫn có thể kiểm soát quyền, origin hoặc policy riêng.

**Câu 13:** Muốn gửi request có body từ file lớn nên dùng gì?  
**Đáp án:** `BodyPublishers.ofFile(path)` nếu hợp đồng cho phép, và `Content-Type` đúng định dạng; cân nhắc nguồn có thể replay, timeout, limits và không load file lớn vào String.

**Câu 14:** Demo gửi `Accept: text/plain` nhưng `Content-Type: application/json` cho POST có mâu thuẫn không?  
**Đáp án:** Không. Request body là JSON; response mong muốn là text. Echo server trong demo trả `text/plain` nên cặp header này hợp lệ.

## 15. Tài liệu chính thức

- Java SE 17 — `HttpClient`, `send()`, `sendAsync()`, cấu hình client: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17 — `HttpRequest`, request bất biến và builder: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html
- Java SE 17 — `HttpRequest.Builder`: `GET/POST/PUT/DELETE/method/header/setHeader/timeout`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html
- Java SE 17 — `HttpRequest.BodyPublishers`, string, file, byte[], noBody: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html
- Java SE 17 — `HttpResponse`, status, headers, body, version: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Java SE 17 — `HttpResponse.BodyHandlers`, `ofString/byteArray/ofFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- Java SE 17 — `HttpTimeoutException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html
- Java SE 17 — `com.sun.net.httpserver.HttpServer` cho bài test loopback: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- HTTP Semantics (IETF RFC 9110) — method, safe/idempotent, status codes: https://www.rfc-editor.org/rfc/rfc9110
- HTTP PATCH (IETF RFC 5789): https://www.rfc-editor.org/rfc/rfc5789
- JSON Merge Patch (IETF RFC 7396): https://www.rfc-editor.org/rfc/rfc7396
