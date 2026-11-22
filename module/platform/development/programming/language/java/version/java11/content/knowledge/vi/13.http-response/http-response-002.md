# statusCode, headers, uri, request và version trong HTTP Response (Java 11+)

## 1. HttpResponse cho biết những gì ngoài nội dung trả về?

Khi gọi một HTTP API, ứng dụng cần biết nhiều hơn chuỗi JSON hoặc nội dung tệp mà server trả về. Một phản hồi HTTP có **mã trạng thái**, **header**, **URI cuối cùng**, **request gắn với phản hồi**, **phiên bản giao thức HTTP thực tế** và **body**.

Từ **Java 11**, HTTP Client chuẩn nằm trong module `java.net.http`. Khi gửi request bằng `HttpClient.send(...)` hoặc `sendAsync(...)`, kết quả là một đối tượng `HttpResponse<T>`:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
```

Đây là **mảnh mã minh họa** đặt trong phương thức đã khai báo/xử lý `IOException` và `InterruptedException`, với `client`, `request` và các import tương ứng đã có. Phương thức `BodyHandlers.ofString(UTF_8)` chọn cách đọc **body** thành `String`. Nó **không** quyết định status, header hoặc version mà server trả về.

Năm accessor cần nắm vững:

| API | Kiểu kết quả | Ý nghĩa |
| --- | --- | --- |
| `response.statusCode()` | `int` | Mã trạng thái HTTP của phản hồi, ví dụ 200, 302, 404 hoặc 500. |
| `response.headers()` | `HttpHeaders` | Tập header của phản hồi, tra cứu theo tên và nhận giá trị. |
| `response.uri()` | `URI` | URI của request mà phản hồi này ứng với; **có thể là URI cuối sau redirect**. |
| `response.request()` | `HttpRequest` | Request liên kết với phản hồi; **có thể khác request đầu tiên** nếu đã redirect. |
| `response.version()` | `HttpClient.Version` | Phiên bản HTTP được dùng cho phản hồi đó, như `HTTP_1_1` hoặc `HTTP_2`. |

Ngoài năm accessor chính, `body()` trả kiểu `T` theo `BodyHandler`; `previousResponse()` cung cấp metadata của phản hồi trước nếu có chuỗi chuyển hướng; `sslSession()` có thể cung cấp thông tin TLS khi phù hợp.

**Điểm cần nhớ:** `HttpResponse<T>` là kết quả của **giao dịch HTTP đã được nhận**, không phải bảo đảm rằng nghiệp vụ thành công. Status 404/500 vẫn có thể trả `HttpResponse` bình thường. Trong khi đó, lỗi DNS, TLS, timeout hoặc I/O có thể làm `send` ném ngoại lệ thay vì trả một response.

## 2. statusCode(): phân biệt phản hồi HTTP và lỗi truyền tải

### 2.1. Các nhóm mã trạng thái

`response.statusCode()` trả về số nguyên mà server dùng để mô tả kết quả giao thức HTTP. Các nhóm thường gặp:

| Nhóm | Ví dụ | Ý nghĩa và xử lý thông thường |
| --- | --- | --- |
| `1xx` | 100 Continue | Thông tin tạm thời trong quá trình xử lý HTTP; không xem là kết quả nghiệp vụ hoàn tất. |
| `2xx` | 200 OK, 201 Created, 204 No Content | Request được xử lý thành công theo ngữ nghĩa mã cụ thể. |
| `3xx` | 301, 302, 303, 307, 308 | Chuyển hướng hoặc trạng thái liên quan định vị/cache. Có thể được client tự theo tùy cấu hình. |
| `4xx` | 400, 401, 403, 404, 409, 429 | Có vấn đề ở request/quyền truy cập/tài nguyên/giới hạn tốc độ; cần đọc hợp đồng API. |
| `5xx` | 500, 502, 503, 504 | Server hoặc thành phần trung gian không hoàn thành yêu cầu theo mong đợi. |

Không phải mọi `2xx` đều có body: `204 No Content` thường được dùng khi **không có nội dung phản hồi**. `201` có thể biểu thị một tài nguyên vừa tạo và có header `Location`. Đừng giả định cứ mã `200` là JSON hợp lệ hoặc cứ `204` là phải có `String` chứa nội dung.

Với API mà thành công được định nghĩa theo nhóm `2xx`:

```java
int status = response.statusCode();
if (status >= 200 && status < 300) {
    // Xử lý các trường hợp thành công phù hợp hợp đồng endpoint.
} else if (status == 404) {
    // Không tìm thấy tài nguyên.
} else if (status == 429) {
    // Giới hạn tốc độ: áp dụng chính sách retry/backoff của API.
} else {
    // Xử lý mã trạng thái còn lại.
}
```

Đây là đoạn minh họa trong phương thức đã có `response`. Phân loại theo dải là bước đầu; **ý nghĩa nghiệp vụ** phải dựa trên tài liệu endpoint: 202 có thể là xử lý chưa hoàn tất, 206 là nội dung một phần, 304 không phải response có body đầy đủ.

### 2.2. Status 404/500 không tự ném IOException

Giả sử server phản hồi hợp lệ:

```http
HTTP/1.1 404 Not Found
Content-Type: text/plain; charset=utf-8

not found
```

Khi `client.send(...)` nhận response này và body handler xử lý được nội dung, lời gọi có thể hoàn tất bình thường:

```java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

System.out.println(response.statusCode()); // 404
System.out.println(response.body());       // not found
```

Ngược lại, mất kết nối, lỗi chứng chỉ TLS, timeout hoặc hủy/gián đoạn thao tác có thể khiến không có `HttpResponse` hoàn chỉnh để kiểm tra status. Vì vậy **không dùng `catch(IOException)` thay cho kiểm tra mã HTTP**.

Một số framework HTTP khác có thể tự ném exception đối với 4xx/5xx, nhưng đó không phải hành vi mặc định của **`java.net.http.HttpClient`** khi dùng các body handler thông thường.

### 2.3. Redirect có thể làm status cuối khác status trung gian

Nếu client được cấu hình theo chuyển hướng:

```text
GET /start
     |
     v
HTTP 302  Location: /final
     |
     v
GET /final
     |
     v
HTTP 200
```

`response.statusCode()` của lần gửi ban đầu có thể là **200** (phản hồi cuối), không phải 302. Muốn kiểm tra các phản hồi trước do redirect, dùng `response.previousResponse()` và duyệt chuỗi previous-response khi cần.

Ngược lại, nếu client **không theo redirect** (ví dụ `followRedirects(HttpClient.Redirect.NEVER)`), phản hồi 302 có thể được trả thẳng cho caller. Đây là quyết định cấu hình client, không phải lỗi đọc status.

## 3. headers(): đọc metadata HTTP đúng cách

`response.headers()` trả về `HttpHeaders`. Đối tượng này hỗ trợ các API phổ biến:

```java
HttpHeaders headers = response.headers();

Optional<String> contentType = headers.firstValue("Content-Type");
List<String> tags = headers.allValues("X-Tag");
OptionalLong contentLength = headers.firstValueAsLong("Content-Length");
Map<String, List<String>> all = headers.map();
```

Đây là **mảnh mã minh họa** trong phương thức và cần import `java.net.http.HttpHeaders`, `java.util.Optional`, `OptionalLong`, `List` và `Map`. `HttpHeaders` là một cái nhìn **không cho phép sửa** các header phản hồi; muốn thay đổi hành vi gửi request thì phải cấu hình `HttpRequest`, không chỉnh map từ `response.headers()`.

### 3.1. Tra cứu không phân biệt chữ hoa/thường ở tên header

Tên header HTTP không phân biệt chữ hoa/thường. Vì vậy:

```java
response.headers().firstValue("content-type");
response.headers().firstValue("Content-Type");
response.headers().firstValue("CONTENT-TYPE");
```

đều tra cứu cùng tên header về mặt ngữ nghĩa. Điều này khác với **giá trị** của nhiều header, vốn cần được phân tích theo quy tắc riêng của từng header.

Đừng viết code yêu cầu tên được trả về từ `headers.map()` phải giữ đúng kiểu chữ server đã gửi. Khi cần một header cụ thể, `firstValue("...")` hoặc `allValues("...")` rõ ràng hơn việc tự duyệt map và so sánh key bằng `String.equals` có phân biệt hoa/thường.

### 3.2. Header có thể vắng mặt hoặc có nhiều giá trị

`firstValue(name)` trả `Optional<String>`; nếu header không có, kết quả là `Optional.empty()`. Sử dụng an toàn:

```java
String type = response.headers()
        .firstValue("Content-Type")
        .orElse("(missing)");

List<String> values = response.headers()
        .allValues("Set-Cookie");
```

Đoạn này minh họa cho `response` đã có. Với các header có nhiều giá trị, **`firstValue` chỉ lấy một giá trị**, không phải phép kiểm tra toàn bộ header. `allValues` trả danh sách những giá trị được API thể hiện; tùy quy tắc header, một giá trị có thể chứa danh sách phân tách bằng dấu phẩy. **Không tách mọi header theo dấu phẩy một cách máy móc**, đặc biệt header như `Set-Cookie` có cú pháp riêng.

`firstValueAsLong(name)` phù hợp khi giá trị header cần được hiểu là một số nguyên (ví dụ `Content-Length` nếu server thực sự cung cấp). Đừng mặc định `Content-Length` luôn có: HTTP có thể truyền body bằng các cơ chế không khai báo trước chiều dài; với nội dung đã nén, `Content-Length` cũng không tự nói kích thước dữ liệu sau giải nén.

### 3.3. Headers cần diễn giải theo hợp đồng API

Các trường thường hữu ích:

| Header | Ví dụ | Cách hiểu |
| --- | --- | --- |
| `Content-Type` | `application/json` | Media type của **body response**; không chứng minh JSON hợp lệ. |
| `Content-Type` | `text/plain; charset=utf-8` | Văn bản cùng thông tin charset nếu media type định nghĩa tham số đó. |
| `Location` | `/items/42` | Có thể chỉ vị trí mới/chuyển hướng tùy status (201, 3xx...). |
| `Retry-After` | `120` | Gợi ý thời gian chờ theo định dạng cho phép; có thể xuất hiện với 429/503. |
| `ETag` | `"v12"` | Giá trị phục vụ kiểm tra điều kiện/cache; không phải chữ ký bảo mật. |
| `Content-Length` | `15` | Độ dài representation theo byte trong điều kiện header được sử dụng. |
| `Cache-Control` | `max-age=60` | Chỉ dẫn về caching, cần giải thích theo hợp đồng HTTP. |
| `Content-Encoding` | `gzip` | Biểu thị content coding áp dụng cho representation, khác charset. |

**Content-Type của response** không đồng nghĩa request đã gửi cùng loại. Ví dụ request có `Content-Type: application/json` nhưng response trả `text/plain` để mô tả lỗi. `Accept` của request nói client mong muốn nhận gì; response vẫn phải được kiểm tra thực tế.

Với dữ liệu bí mật như `Set-Cookie` hoặc header chứa thông tin xác thực, **không in/log tùy tiện**; nếu cần quan sát lỗi, ghi tên header và thông tin đã lược bỏ bí mật.

## 4. uri(): URI liên kết với phản hồi, đặc biệt sau redirect

`response.uri()` trả một đối tượng `java.net.URI`. Trong trường hợp không chuyển hướng, nó thường là URI trong request đã gửi. Nếu client **tự theo chuyển hướng**, URI này phản ánh **URI cuối cùng gắn với phản hồi nhận được**.

Ví dụ:

```java
URI original = URI.create("https://example.com/start");
HttpRequest request = HttpRequest.newBuilder(original).GET().build();

// Nếu server chuyển hướng /start -> /final
// và chính sách redirect cho phép theo:
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

URI effective = response.uri(); // có thể là https://example.com/final
```

Đây là **đoạn mã minh họa**, giả định endpoint và redirect thực sự tồn tại; không phải chương trình tự chạy. Không dùng `response.uri()` để kết luận nội dung là an toàn hay URI được phép truy cập: **đích sau redirect có thể khác đích ban đầu**.

Khi cần so sánh:

- `request.uri()` là URI của **đối tượng request đầu tiên mà code đã tạo**.
- `response.uri()` là URI của **response đã nhận** (có thể là đích cuối sau chuyển hướng).
- `response.request().uri()` là URI của **request đi kèm response**, nên có thể giống URI cuối thay vì request ban đầu.

URI không phải địa chỉ mạng đã giải DNS, không chứng minh danh tính server và không đồng nhất với tên host trong chứng chỉ TLS. Với môi trường có giới hạn truy cập đích, phải kết hợp kiểm tra URL/redirect và chính sách mạng phù hợp.

## 5. request(): request tương ứng với response

`response.request()` trả lại `HttpRequest` liên kết với response; có thể truy cập các thuộc tính:

```java
HttpRequest returnedRequest = response.request();
String method = returnedRequest.method();
URI sentTo = returnedRequest.uri();
Optional<Duration> timeout = returnedRequest.timeout();
HttpHeaders requestHeaders = returnedRequest.headers();
```

Đây là đoạn minh họa trong phương thức; cần import các kiểu tương ứng.

**Không nhất thiết cùng đối tượng với `request` ban đầu.** Nếu có redirect, HTTP client có thể tạo các request trung gian hoặc cuối; `response.request()` tương ứng với response cuối. Hơn nữa, redirect của những HTTP method như POST có các quy tắc đặc thù theo mã 301/302/303/307/308 và chính sách client; **không mặc định method/body bất biến sau mọi redirect**.

Một ứng dụng muốn kiểm soát redirect chặt có thể tắt theo tự động:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

Khi đó caller tự kiểm tra status 3xx và `Location`, đồng thời đánh giá đích mới trước khi phát tiếp request. Với redirect được tự theo, dùng `previousResponse()` khi cần truy nguyên chuỗi chuyển hướng.

**Không coi `response.request().headers()` là bản chụp byte HTTP thực tế đi trên mạng.** Các header do thư viện/hạ tầng thêm vào hoặc các chi tiết truyền tải cấp thấp không nhất thiết được thể hiện như trong gói tin. Thuộc tính request dùng để kiểm tra cấu hình/lôgic của request gắn với response.

## 6. version(): giao thức thực tế được dùng

`response.version()` trả giá trị `HttpClient.Version`:

- `HttpClient.Version.HTTP_1_1`.
- `HttpClient.Version.HTTP_2`.

Đọc trực tiếp:

```java
System.out.println(response.version());
```

Điểm hay nhầm:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

`version(HTTP_2)` là phiên bản **ưu tiên** cho client, không đảm bảo mỗi server, proxy hoặc kết nối sẽ thực sự dùng HTTP/2. Với server chỉ hỗ trợ HTTP/1.1, thư viện có thể dùng HTTP/1.1 tùy điều kiện. Kiểm tra `response.version()` khi cần biết chính xác phản hồi được xử lý bằng giao thức gì.

Phiên bản HTTP thực tế có thể ảnh hưởng đến đặc tính multiplexing, cách đóng khung (framing), header và thông tin quan sát hiệu năng. Nhưng **không được suy ra chất lượng, bảo mật hoặc tính đúng đắn của dữ liệu chỉ từ `HTTP_2`**. HTTPS/TLS, xác thực và ngữ nghĩa response là các vấn đề riêng.

Khi chạy ví dụ ở mục 8, chương trình cấu hình `HTTP_1_1` để kết quả minh họa **ổn định**, không phụ thuộc việc thương lượng HTTP/2 với các endpoint công khai.

## 7. previousResponse(): kiểm tra chuỗi redirect

Ngoài năm thành phần chính của đề bài, `previousResponse()` là API bổ trợ quan trọng để hiểu vì sao `statusCode()`, `uri()` và `request()` khác kỳ vọng:

```java
Optional<HttpResponse<String>> previous = response.previousResponse();

previous.ifPresent(prev -> {
    System.out.println(prev.statusCode());
    System.out.println(prev.uri());
});
```

Đây là đoạn minh họa cho `HttpResponse<String> response` đã có; cần import `java.util.Optional`. Nếu có chuỗi redirect, mỗi previous response có thể có tiếp `previousResponse()` của nó. Nếu không có, `Optional` rỗng.

**Body của previous response trong chuỗi này là `null` theo hợp đồng của `HttpResponse.previousResponse()`.** Đừng dùng `previousResponse().get().body()` để lấy trang HTML/thông điệp của lần redirect trước. Phản hồi cuối dùng `response.body()` được tạo theo body handler của request hiện tại.

Mọi response trong chuỗi có thể mang status, header, URI, request và version riêng. Tuy nhiên, không mặc định chúng đại diện cho mọi lần thử mạng, lần retry hoặc một trace đầy đủ của proxy: đây là API response HTTP và chuỗi phản hồi trước đó theo Java HTTP Client.

## 8. Chương trình Java 11+ đầy đủ: status, header, redirect, request và version

Chương trình dùng **`java.net.http.HttpClient` làm client** và một HTTP server cục bộ tại `127.0.0.1` để tạo dữ liệu kiểm thử xác định. Server fixture dùng `com.sun.net.httpserver.HttpServer` (module `jdk.httpserver` có trong JDK), không phải API client của bài học.

Luồng chạy:

1. `GET /start` được trả `302 Location: /final`.
2. `HttpClient` đã cấu hình `Redirect.NORMAL` theo chuyển hướng đến `/final`.
3. `/final` trả status `200`, hai giá trị header `X-Tag` và body `"Xin chao Java 11"`.
4. Chương trình in metadata response, request ban đầu, request cuối và previous response `302`.
5. Gửi thêm `GET /missing` để chứng minh status `404` được nhận bằng `HttpResponse` thay vì tự ném ngoại lệ.

Lưu thành tệp **`HttpResponseMetadataDemo.java`**:

```java
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
import java.time.Duration;

public class HttpResponseMetadataDemo {
    private static void reply(HttpExchange exchange, int status, String body)
            throws IOException {
        try {
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/start", exchange -> {
            try {
                exchange.getResponseHeaders().set("Location", "/final");
                exchange.sendResponseHeaders(302, -1);
            } finally {
                exchange.close();
            }
        });
        server.createContext("/final", exchange -> {
            exchange.getResponseHeaders().set("X-Demo", "from-final");
            exchange.getResponseHeaders().add("X-Tag", "one");
            exchange.getResponseHeaders().add("X-Tag", "two");
            reply(exchange, 200, "Xin chao Java 11");
        });
        server.createContext("/missing",
                exchange -> reply(exchange, 404, "not found"));
        server.start();

        try {
            URI base = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .build();

            HttpRequest initial = HttpRequest.newBuilder(base.resolve("/start"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
            HttpResponse<String> response = client.send(
                    initial, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println("status=" + response.statusCode());
            System.out.println("contentType=" + response.headers()
                    .firstValue("content-type").orElse("(missing)"));
            System.out.println("xDemo=" + response.headers()
                    .firstValue("X-DEMO").orElse("(missing)"));
            System.out.println("tagCount=" + response.headers()
                    .allValues("x-tag").size());
            System.out.println("initialPath=" + initial.uri().getPath());
            System.out.println("responsePath=" + response.uri().getPath());
            System.out.println("requestPath=" + response.request().uri().getPath());
            System.out.println("method=" + response.request().method());
            System.out.println("version=" + response.version());
            System.out.println("redirectStatus=" + response.previousResponse()
                    .map(HttpResponse::statusCode).orElse(-1));
            System.out.println("previousBodyNull=" + response.previousResponse()
                    .map(previous -> previous.body() == null).orElse(false));
            System.out.println("body=" + response.body());

            HttpRequest missing = HttpRequest.newBuilder(
                    base.resolve("/missing")).GET().build();
            HttpResponse<String> absent = client.send(
                    missing, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("missingStatus=" + absent.statusCode());
            System.out.println("missingBody=" + absent.body());
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch và chạy với JDK có compiler còn hỗ trợ Java 11:

```bash
javac -encoding UTF-8 --release 11 HttpResponseMetadataDemo.java
java HttpResponseMetadataDemo
```

**Kết quả thực tế đã kiểm chứng khi chạy trên JDK 24, biên dịch bằng `--release 11`:**

```text
status=200
contentType=text/plain; charset=utf-8
xDemo=from-final
tagCount=2
initialPath=/start
responsePath=/final
requestPath=/final
method=GET
version=HTTP_1_1
redirectStatus=302
previousBodyNull=true
body=Xin chao Java 11
missingStatus=404
missingBody=not found
```

### Diễn giải từng điểm quan trọng

- `status=200` là mã phản hồi **cuối** sau redirect; `redirectStatus=302` ghi nhận phản hồi trước.
- `contentType=...` được tìm bằng tên `content-type` viết thường; kết quả vẫn đúng vì tên header không phân biệt chữ hoa/thường.
- `xDemo=from-final` truy xuất bằng tên `X-DEMO` khác cách viết hoa của server; cùng một tên header về ngữ nghĩa.
- `tagCount=2` chứng minh `allValues("x-tag")` có thể thu nhiều giá trị cho một header.
- `initialPath=/start` là request ban đầu; `responsePath=/final` và `requestPath=/final` cho thấy URI/request của **response cuối**.
- `method=GET` đọc phương thức từ `response.request()`, không phải tự suy đoán từ kiểu body.
- `version=HTTP_1_1` phản ánh giao thức thực tế của response trong fixture này.
- `previousBodyNull=true` minh họa hợp đồng previous response: body trước không được lưu trong cây response này.
- `missingStatus=404` nhưng lệnh `client.send` không tự ném `IOException` cho phản hồi HTTP 404; `missingBody` vẫn đọc được.

Bởi server chạy trên **loopback** và dùng cổng hệ điều hành cấp tự động, ví dụ không cần kết nối Internet. Nó không phải mẫu server production. Một dự án chỉ làm HTTP client không cần import `com.sun.net.httpserver`; với dự án module hóa, client cần `requires java.net.http;` và fixture này cần thêm `requires jdk.httpserver;`. Ví dụ dùng **classpath**, nên có thể chạy bằng đúng hai lệnh phía trên.

## 9. Sử dụng cùng metadata khi gửi bất đồng bộ

`HttpClient.sendAsync(...)` trả về `CompletableFuture<HttpResponse<T>>`. Khi request hoàn thành thành công, **cùng những accessor** được dùng:

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

future.thenAccept(res -> {
    System.out.println(res.statusCode());
    System.out.println(res.headers().firstValue("Content-Type"));
    System.out.println(res.uri());
    System.out.println(res.request().method());
    System.out.println(res.version());
});
```

Đoạn này là **mảnh mã minh họa** trong phương thức, cần import `java.util.concurrent.CompletableFuture` và có `client`, `request`. `sendAsync` không đảm bảo một callback `thenAccept` đã hoàn tất trước khi code tiếp tục; ứng dụng phải điều phối `CompletableFuture` phù hợp với vòng đời tác vụ.

Lỗi network, timeout hoặc TLS có thể khiến future **hoàn thành thất bại**. Nếu gọi `join()`, ngoại lệ nguyên nhân có thể nằm trong `CompletionException`; nếu gọi `get()`, nó có thể được bao trong `ExecutionException`. **HTTP status 404/500 vẫn có thể là future hoàn thành bình thường**, vì đã nhận response hợp lệ.

Không bắt một exception bất kỳ rồi thay thành status `500` do client tự tạo: điều đó làm mất khả năng phân biệt **server đã gửi response** với **không nhận được response hợp lệ**.

## 10. Kiểm soát timeout, lỗi và tài nguyên khi đọc HTTP response

Một request đồng bộ thường cần phân biệt:

```java
try {
    HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    int status = response.statusCode();
    // Phân tích status/headers/body theo hợp đồng ứng dụng.
} catch (java.net.http.HttpConnectTimeoutException e) {
    // Hết thời gian tạo kết nối mới.
} catch (java.net.http.HttpTimeoutException e) {
    // Hết thời gian chờ phản hồi của request.
} catch (IOException e) {
    // Các lỗi I/O hoặc TLS/kết nối khác.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Dừng hoặc báo lên tầng điều phối.
}
```

Đây là **mảnh mã minh họa** trong phương thức có `client` và `request`. `HttpConnectTimeoutException` là subtype của `HttpTimeoutException`, phải catch trước; đồng thời cấu hình `client.connectTimeout(...)` và `request.timeout(...)` khi cần.

**Đừng trộn lẫn mã trạng thái với timeout**. `504 Gateway Timeout` là status do một server/proxy trả về, còn `HttpTimeoutException` là lỗi cục bộ trong quá trình thực hiện request.

Với body lớn, `BodyHandlers.ofString()` hoặc `ofByteArray()` có thể giữ toàn bộ body trong RAM. Nếu ứng dụng chỉ cần metadata, hãy chọn body handler phù hợp:

- `BodyHandlers.discarding()` khi muốn **tiêu thụ và bỏ** body.
- `BodyHandlers.ofInputStream()` khi cần đọc streaming, kiểm tra tổng byte và **đóng stream** sau khi dùng.
- `BodyHandlers.ofFile(path)` khi tải nội dung xuống file, cần chính sách giới hạn tài nguyên và xử lý file ghi dở.

Đừng cố đánh giá “file đã tải đầy đủ” chỉ vì response headers đã về. Với `ofInputStream`, body được xử lý tiếp qua stream, và lỗi có thể phát sinh lúc đọc stream. Khi cần an toàn về bộ nhớ, đếm byte trong vòng lặp và giới hạn kích thước trước khi lưu/parse.

## 11. An toàn khi dùng URI, header và redirect

### 11.1. Không tin URI đầu vào và chuỗi redirect

Với ứng dụng server-side nhận URL từ người dùng rồi gọi `HttpClient`, nguy cơ **SSRF** không được giải quyết chỉ bằng `response.uri()`. Cần ràng buộc protocol, host, cổng, địa chỉ IP/DNS và chuyển hướng, bao gồm đích sau mỗi bước. Khi phải giới hạn đích rất chặt, có thể dùng `Redirect.NEVER` và đánh giá `Location` trước khi gửi request kế tiếp.

Không coi việc nhận `HTTP_2` hoặc một `Content-Type` có vẻ hợp lệ là chứng chỉ bảo mật. Kiểm tra TLS/hostname, policy mạng và dữ liệu thực tế vẫn cần thiết.

### 11.2. Không làm lộ header riêng tư

`headers.map()` có thể chứa `Set-Cookie` và thông tin liên quan phiên đăng nhập. Không in nguyên bộ header/URI query vào log nếu có thể chứa token hoặc dữ liệu cá nhân. `response.request()` cũng có thể chứa các header do ứng dụng gửi; ghi log phải che `Authorization`, cookie và khóa API.

### 11.3. Không dựa duy nhất vào Content-Type để xử lý nội dung

Response chứa `Content-Type: application/json` không chứng minh body là JSON hợp lệ. Muốn xử lý đúng phải:
1. Đọc `statusCode()`.
2. Xem `headers()` để biết media type, charset/content encoding thực tế.
3. Giới hạn kích thước và đọc body đúng loại.
4. Parse/validate nội dung theo schema nghiệp vụ.
5. Xử lý lỗi rõ ràng, không công bố dữ liệu chưa được kiểm tra.

Không tự phân tích HTML hoặc file upload dựa trên tên hay header đơn thuần. Đối với JSON và văn bản, hãy chọn charset phù hợp với định dạng/giao thức và tránh giải mã byte nhị phân thành `String` tùy ý.

## 12. Lỗi thường gặp và hướng sửa

| Hiểu nhầm | Hậu quả | Cách dùng đúng |
| --- | --- | --- |
| `statusCode() == 200` nên mọi nghiệp vụ chắc chắn thành công | Body có thể sai schema hoặc thiếu dữ liệu mong đợi. | Kiểm tra status **và** nội dung theo hợp đồng API. |
| `404` sẽ ném `IOException` | Không vào catch, code coi body lỗi là kết quả thành công. | Kiểm tra `response.statusCode()`. |
| Luôn dùng `response.headers().firstValue(...).get()` | Header thiếu gây `NoSuchElementException`. | Dùng `orElse`/`ifPresent` hoặc nhánh xử lý Optional rỗng. |
| Tra header bằng `equals` phân biệt chữ hoa/thường | Có thể bỏ sót header cùng tên. | Dùng accessor của `HttpHeaders`, tên không phân biệt hoa/thường. |
| Lấy `firstValue("Set-Cookie")` để coi là toàn bộ cookie | Header có thể có nhiều giá trị. | Dùng `allValues`/cơ chế cookie phù hợp. |
| Mặc định `Content-Length` luôn tồn tại | Request/response có thể dùng framing khác hoặc không gửi header này. | Dùng Optional và đo byte thật khi cần. |
| `response.uri()` luôn bằng request ban đầu | Redirect có thể đổi URI. | So sánh `initial.uri()` với `response.uri()`, kiểm tra previous response. |
| `response.request() == initial` luôn đúng | Client có thể tạo request mới khi redirect. | Dùng `response.request()` để lấy request tương ứng phản hồi. |
| `response.version()` luôn đúng bằng `client.version()` | Phiên bản client chọn chỉ là ưu tiên. | Dùng `response.version()` để biết protocol đã dùng. |
| `previousResponse().get().body()` đọc được body redirect | Body của previous response là `null` theo hợp đồng API. | Dùng metadata previous response; body cuối qua `response.body()`. |
| `sendAsync` lỗi mạng sẽ tự trả status 500 | Future có thể hoàn thành thất bại không kèm response. | Phân biệt exception với response.statusCode. |
| Ghi log `headers.map()` không lọc | Có thể lộ cookie, token, dữ liệu riêng tư. | Chỉ log field được phép và redaction. |
| Dùng `ofString` cho nội dung không giới hạn | Có thể tiêu tốn RAM. | Streaming, giới hạn byte, timeout và đóng nguồn. |

## 13. Tự luyện có đáp án

**Câu 1.** `statusCode()` trả 404, còn `client.send(...)` không ném exception. Có mâu thuẫn không?

**Đáp án:** Không. 404 là một phản hồi HTTP hợp lệ mang trạng thái lỗi của tài nguyên. `IOException` mô tả lỗi I/O/transport, không tự đại diện mọi status 4xx/5xx.

**Câu 2.** Trong ví dụ redirect từ `/start` sang `/final`, vì sao `response.uri().getPath()` là `"/final"`?

**Đáp án:** Vì client đã theo redirect và `response` là phản hồi **cuối**. Request đầu tiên vẫn có `initial.uri().getPath() == "/start"`.

**Câu 3.** `response.request()` dùng để làm gì? Có luôn là cùng reference với `initial` không?

**Đáp án:** Nó trả request liên kết với phản hồi. Khi redirect, client có thể tạo request khác, nên không mặc định hai reference hoặc URI giống nhau.

**Câu 4.** Header `Content-Type` có thể tra bằng `"content-type"` và `"CONTENT-TYPE"` không?

**Đáp án:** Có, tra bằng `HttpHeaders` không phân biệt hoa/thường ở **tên header**. Tuy nhiên, giá trị media type cần diễn giải theo cú pháp riêng.

**Câu 5.** Nếu header `X-Tag` có hai giá trị, `firstValue("X-Tag")` có cung cấp toàn bộ không?

**Đáp án:** Không. Dùng `allValues("X-Tag")` để lấy những giá trị header mà HTTP Client thể hiện.

**Câu 6.** Cấu hình `client.version(HTTP_2)` đã bảo đảm `response.version() == HTTP_2` chưa?

**Đáp án:** Chưa. Phiên bản thực tế còn phụ thuộc khả năng của server/proxy/kết nối; phải đọc `response.version()`.

**Câu 7.** Có thể dùng `previousResponse()` để đọc body của phản hồi 302 trước đó không?

**Đáp án:** Không. API previous response lưu metadata liên quan, nhưng body của previous response là `null`.

**Câu 8.** Khi `BodyHandlers.ofInputStream()` trả stream, đã có response nghĩa là body chắc chắn tải xong chưa?

**Đáp án:** Chưa. Caller phải đọc/giới hạn/đóng stream. Lỗi I/O vẫn có thể xảy ra khi đọc.

**Câu 9.** Làm sao phân biệt status 504 và `HttpTimeoutException`?

**Đáp án:** 504 là status trong `HttpResponse` nếu gateway/server trả về; `HttpTimeoutException` xảy ra trong client khi hết thời gian chờ, có thể không nhận được response hoàn chỉnh.

**Câu 10.** Nếu cần bảo vệ hệ thống khỏi redirect tới đích không tin cậy, có nên dựa duy nhất vào `response.uri()` sau khi request đã gửi không?

**Đáp án:** Không. Khi tự theo redirect, request đến đích mới **đã diễn ra**. Cần kiểm soát địa chỉ và redirect **trước mỗi lần gửi**, ví dụ tắt auto-follow và áp dụng chính sách xác thực đích.

## 14. Tổng kết và nguồn tham khảo

- **`statusCode()`** cho mã HTTP: 2xx, 3xx, 4xx, 5xx không đồng nghĩa với exception từ HTTP client.
- **`headers()`** cho `HttpHeaders` để đọc metadata; tên header không phân biệt chữ hoa/thường, header có thể thiếu hoặc có nhiều giá trị.
- **`uri()`** thể hiện URI ứng với phản hồi; nếu đã redirect, nó có thể là **URI cuối**, không phải URI ban đầu.
- **`request()`** trả `HttpRequest` liên kết với phản hồi; redirect có thể dẫn đến request cuối khác request gốc.
- **`version()`** cho phiên bản HTTP thực tế của response, không phải cam kết từ phiên bản ưu tiên của client.
- **`previousResponse()`** giúp lần theo phản hồi redirect trước đó; body previous response là `null` theo hợp đồng.
- **`body()`** trả nội dung theo `BodyHandler`; xử lý status, media type, kích thước và tính hợp lệ dữ liệu là những bước riêng.
- Dùng đúng các API **`java.net.http` của Java 11+**, kiểm thử với server cục bộ và tránh giả định những tính năng chỉ được thêm vào JDK sau.

Tài liệu API chính thức, vẫn áp dụng:

- [Java SE 11 — HttpResponse](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html).
- [Java SE 11 — HttpHeaders](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpHeaders.html).
- [Java SE 11 — HttpRequest](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html).
- [Java SE 11 — HttpClient và phiên bản giao thức](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).