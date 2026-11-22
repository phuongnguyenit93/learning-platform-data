# Content-Type, charset và ý nghĩa dữ liệu truyền trong HTTP Request (Java 11+)

## 1. Mục tiêu: hiểu đúng những byte được gửi qua HTTP

Trong HTTP, một request có thể chứa **body**: văn bản, JSON, dữ liệu form, ảnh, PDF hoặc các byte nhị phân khác. Để server hiểu body đúng, hai bên cần thống nhất **dữ liệu thuộc loại nào** và, nếu là văn bản, **các byte biểu diễn ký tự theo bảng mã nào**.

Hai khái niệm cốt lõi:

- **`Content-Type`** mô tả *media type* của representation (định dạng/ý nghĩa của nội dung được gửi), ví dụ `text/plain`, `application/json`, `application/x-www-form-urlencoded` hay `application/octet-stream`.
- **`charset`** là một tham số của **những media type có định nghĩa tham số ấy**, thường dùng để cho biết cách diễn giải byte thành ký tự, ví dụ `text/plain; charset=utf-8`.

Tuy vậy, **header không tự chuyển đổi dữ liệu**. Nếu bạn phát byte UTF-8 nhưng khai báo ISO-8859-1, server có thể đọc sai tiếng Việt. Ngược lại, ghi `charset=utf-8` không làm một mảng byte tùy ý tự trở thành UTF-8 hợp lệ.

Trong Java 11+, module `java.net.http` cung cấp `HttpClient`, `HttpRequest` và `HttpResponse` để gửi/nhận HTTP, cùng `BodyPublishers` để tạo request body và `BodyHandlers` để xử lý response body.

**Mục tiêu học tập:**

1. Đọc và đặt `Content-Type` đúng theo body.
2. Tạo byte từ `String` với charset tường minh, nhất là UTF-8.
3. Phân biệt request `Content-Type`, `Accept`, response `Content-Type` và `Content-Encoding`.
4. Biết khi nào dùng JSON, form, multipart hoặc binary.
5. Kiểm thử được cả header lẫn byte thực tế; tránh nhầm *byte length* với độ dài `String`.
6. Hiểu những ngoại lệ và vấn đề bảo mật khi nhận đầu vào không tin cậy.

## 2. Cú pháp của Content-Type

Ví dụ HTTP request gửi văn bản:

```http
POST /notes HTTP/1.1
Host: example.com
Content-Type: text/plain; charset=utf-8
Accept: application/json

Xin chào
```

Đây là ví dụ **mô tả thông điệp HTTP**, không phải một chương trình Java hoàn chỉnh. Khi truyền thật, body là **byte**, không phải trực tiếp các chữ cái trong đoạn trình bày trên.

Cấu trúc thường gặp:

```text
Content-Type: type/subtype; parameter=value
```

Trong đó:
- `type/subtype` xác định định dạng nội dung, chẳng hạn `text/plain` hoặc `application/json`.
- Phần `; charset=utf-8` là tham số dành cho media type hỗ trợ nó.
- Media type, tên tham số và tên charset được so sánh theo quy tắc không phân biệt chữ hoa/chữ thường tương ứng. Ví dụ `Text/Plain; Charset="UTF-8"` cùng ý nghĩa cơ bản với `text/plain; charset=utf-8`.
- Không phải mọi media type đều dùng `charset`. Các tham số khác có thể mang ý nghĩa riêng, như `boundary` của `multipart/form-data`.

Một số dạng thường dùng:

| `Content-Type` | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `text/plain; charset=utf-8` | Văn bản thuần, mã hóa UTF-8. | Phù hợp khi gửi một đoạn text và server mong text. |
| `text/html; charset=utf-8` | Tài liệu HTML mã hóa UTF-8. | Không giống text thuần; việc hiển thị HTML cần xử lý an toàn. |
| `application/json` | Dữ liệu cú pháp JSON. | JSON trao đổi giữa hệ thống mở cần UTF-8 theo RFC 8259. |
| `application/x-www-form-urlencoded` | Các cặp trường được mã hóa theo quy tắc form. | Không giống JSON; dấu `+` thường đại diện khoảng trắng trong giá trị form. |
| `multipart/form-data; boundary=...` | Nội dung có nhiều phần, phân cách bằng boundary. | Header và cấu trúc byte thực tế bắt buộc khớp nhau. |
| `application/octet-stream` | Byte nhị phân không có định dạng cụ thể hơn. | Không áp dụng charset cho byte tùy ý. |
| `image/png` | Dữ liệu ảnh PNG. | Không dùng charset để “giải mã” file PNG. |
| `application/pdf` | Dữ liệu PDF. | Phải là byte PDF hợp lệ; chỉ đổi header không tạo ra PDF. |

**Lưu ý quan trọng với JSON:** trong đăng ký media type `application/json` theo RFC 8259, **không định nghĩa tham số `charset`**; vì vậy `application/json; charset=utf-8` không tạo hiệu lực bổ sung đối với bên nhận tuân thủ chuẩn. Cách phù hợp để trao đổi JSON hiện đại là gửi **byte UTF-8** và `Content-Type: application/json`. Một số API có thể chấp nhận hoặc yêu cầu tham số charset vì quy ước riêng; hãy tuân theo hợp đồng API nhưng đừng suy ra đây là yêu cầu chung của chuẩn JSON.

## 3. Charset: đường đi từ String đến byte và ngược lại

### 3.1. Chuỗi Java không trực tiếp là byte HTTP

`String` của Java biểu diễn văn bản ở mức ký tự, không phải một mảng byte UTF-8. Muốn gửi văn bản qua mạng, phải **mã hóa ký tự thành byte**:

```text
String Java
    |
    | encode(StandardCharsets.UTF_8)
    v
byte[] -- HTTP request body --> server
                                |
                                | decode bằng charset đúng
                                v
                             văn bản
```

Trong Java 11:

```java
String text = "Xin chào";
byte[] utf8Bytes = text.getBytes(StandardCharsets.UTF_8);

System.out.println(text.length());       // 8 đơn vị char UTF-16
System.out.println(utf8Bytes.length);     // 9 byte UTF-8
```

Đây là **mảnh mã minh họa trong phương thức**, cần import `java.nio.charset.StandardCharsets`. Chữ `à` chiếm một đơn vị `char` UTF-16 nhưng **hai byte** trong UTF-8, nên `8` đơn vị `char` tạo `9` byte.

Với ký tự ngoài BMP, một Unicode code point còn có thể chiếm **hai `char` Java** (surrogate pair), và nhiều byte UTF-8. Vì thế:

- `String.length()` đếm **đơn vị UTF-16**, không phải byte.
- `text.getBytes(UTF_8).length` đếm **byte của bản mã hóa UTF-8**.
- `Content-Length` (khi được dùng) được tính theo **byte của thông điệp body**, không phải số ký tự của `String`.
- Với `Content-Encoding: gzip`, số byte vận chuyển có thể khác cả số byte văn bản UTF-8 trước khi nén.

### 3.2. Phải khớp charset đã dùng và charset công bố

Ví dụ đúng:

```java
String text = "Xin chào";
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "text/plain; charset=utf-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                text, StandardCharsets.UTF_8))
        .build();
```

Đây là đoạn minh họa, giả định đã có `URI uri`, các import cần thiết và một client để gửi request.

Ở đây có **hai quyết định riêng biệt**:
1. `BodyPublishers.ofString(text, UTF_8)` thực sự tạo byte UTF-8.
2. Header `Content-Type` công bố cho server rằng body là văn bản thuần mã hóa UTF-8.

**Không coi việc đặt `Content-Type` là thao tác encode.** `HttpClient` không đọc tên charset trong header rồi tự chuyển một `byte[]` bất kỳ sang encoding đó. Hãy chọn charset tường minh trong publisher hay encoder. `BodyPublishers.ofString(String)` cũng có overload dùng UTF-8, nhưng ghi rõ `StandardCharsets.UTF_8` giúp hợp đồng dễ thấy.

### 3.3. Nếu charset không khớp thì sao?

Giả sử client mã hóa `"café"` thành UTF-8 (chữ `é` là hai byte) nhưng server **giải mã nhầm theo ISO-8859-1**. Kết quả có thể bị lỗi hiển thị kiểu `"cafÃ©"`. Đây là *mojibake*: byte không nhất thiết sai, **cách đọc byte sai**.

Một số decoder có thể thay chuỗi byte không hợp lệ bằng ký tự thay thế `�`, thay vì báo lỗi, nên không nên mặc định “decode không ném exception = văn bản hợp lệ”. Với dữ liệu nhạy cảm, có thể dùng `CharsetDecoder` và `CodingErrorAction.REPORT` để từ chối chuỗi byte không hợp lệ theo chính sách xử lý.

**Chọn UTF-8 tường minh** là mặc định tốt để giao tiếp văn bản giữa hệ thống hiện đại, trừ khi giao thức/media type hoặc API đã quy định một encoding khác.

## 4. Phân biệt những header dễ bị nhầm

| Header | Ai sử dụng? | Nó mô tả điều gì? |
| --- | --- | --- |
| Request `Content-Type` | Server nhận request | Body mà **client đang gửi** là loại dữ liệu gì. |
| Request `Accept` | Server tạo response | Loại media type mà **client muốn nhận** trong response. |
| Response `Content-Type` | Client nhận response | Body mà **server trả về** là loại dữ liệu gì. |
| `Content-Encoding` | Bên nhận representation | Dữ liệu đã áp dụng content coding như `gzip`, cần xử lý trước khi diễn giải theo media type. |
| `Accept-Encoding` | Server khi chọn response | Những content coding như `gzip` mà client chấp nhận. |
| `Content-Length` | Bên nhận và tầng HTTP | Chiều dài body theo **byte** trong trường hợp được gửi. |
| `Transfer-Encoding` | Tầng framing HTTP/1.1 | Cách truyền/framing thông điệp như `chunked`; **không** quy định charset. |

Ví dụ một request có thể đồng thời dùng:

```http
Content-Type: application/json
Accept: application/json
Accept-Encoding: gzip
```

Điều này có nghĩa: client **gửi JSON**, muốn nhận **JSON**, và cho biết có thể chấp nhận một số cách mã hóa nội dung phản hồi (ở đây là gzip). Ba header không thay thế nhau.

**`Content-Type` không cho biết HTTP status.** Body chứa JSON có thể đi kèm status 200, 400, 404 hoặc 500. Ở chiều nhận, phải kiểm tra riêng `response.statusCode()` và loại dữ liệu nhận được.

**`Content-Encoding: gzip` không phải `charset=gzip`.** Gzip là phép biến đổi byte của representation; charset, nếu có ý nghĩa với media type, mới nói cách giải nghĩa byte văn bản sau khi xử lý content coding.

Đối với HTTP/2, chi tiết framing khác HTTP/1.1. Không tự gán thủ công `Transfer-Encoding: chunked` vào một request HTTP/2; để thư viện HTTP xử lý lớp giao thức truyền tải.

## 5. Gửi Content-Type trong java.net.http của Java 11

Những kiểu API thường dùng:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

HttpClient client = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/submit"))
        .header("Content-Type", "text/plain; charset=utf-8")
        .header("Accept", "text/plain")
        .POST(HttpRequest.BodyPublishers.ofString(
                "Xin chào", StandardCharsets.UTF_8))
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
```

Đây là **mã minh họa**, cần đặt trong phương thức có xử lý/khai báo `IOException` và `InterruptedException`. Endpoint `example.com/submit` chỉ là địa chỉ ví dụ, không cam kết dịch vụ sẽ xử lý POST thật.

Quy trình:

1. `HttpClient` điều phối kết nối, gửi request và nhận response; nên **tái sử dụng** client cho nhiều request.
2. `HttpRequest.newBuilder(URI)` tạo cấu hình request. `header("Content-Type", ...)` gắn metadata của body.
3. `BodyPublishers.ofString(..., UTF_8)` chuyển text thành byte UTF-8. Header không tự thêm hoặc xác nhận nội dung là JSON, form hay XML.
4. `build()` tạo request bất biến; **chưa gửi gì**.
5. `client.send(...)` mới thực hiện I/O.
6. `BodyHandlers.ofString(UTF_8)` giải mã **response** theo UTF-8; nó không ảnh hưởng việc encode request.
7. `response.statusCode()` và `response.headers()` giúp kiểm tra kết quả ở tầng HTTP.

### Đặt header đúng số lượng

`header(name, value)` **thêm** một giá trị header. Khi cần chắc chắn thay các giá trị đã thêm trước đó, có thể dùng `setHeader(name, value)` trong builder. Không cố tình tạo nhiều `Content-Type` không nhất quán cho một representation.

Không cần tự đặt `Content-Length` từ `text.length()`. Với `BodyPublisher`, Java HTTP Client xử lý việc tính/truyền độ dài/framing phù hợp. Nếu body có độ dài UTF-8 9 byte mà header bạn tự gán là 8, thông điệp có thể sai hoặc bị thư viện/protocol từ chối.

## 6. Ví dụ Java hoàn chỉnh: kiểm tra header, byte, response charset và dữ liệu form

Ví dụ này tạo HTTP server **chỉ trên loopback `127.0.0.1`** để kiểm chứng request/response tại máy học mà không dùng Internet. Phía gửi request vẫn dùng **HTTP Client chuẩn `java.net.http`**. Server fixture dùng `com.sun.net.httpserver.HttpServer` của module `jdk.httpserver` có trong JDK; ứng dụng chỉ cần HTTP client **không phải** triển khai server như vậy.

Lưu chương trình vào **`ContentTypeDemo.java`**:

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
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class ContentTypeDemo {
    private static void respond(HttpExchange exchange, String contentType,
                                byte[] bytes) throws IOException {
        try {
            exchange.getResponseHeaders().set("Content-Type", contentType);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream body = exchange.getResponseBody()) {
                body.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/inspect", exchange -> {
            String type = exchange.getRequestHeaders().getFirst("Content-Type");
            byte[] bytes = exchange.getRequestBody().readAllBytes();
            String text = new String(bytes, StandardCharsets.UTF_8);
            String result = "type=" + type + "\n"
                    + "bytes=" + bytes.length + "\n"
                    + "text=" + text + "\n";
            respond(exchange, "text/plain; charset=utf-8",
                    result.getBytes(StandardCharsets.UTF_8));
        });
        server.createContext("/latin", exchange ->
                respond(exchange, "text/plain; charset=ISO-8859-1",
                        "café".getBytes(StandardCharsets.ISO_8859_1)));
        server.start();

        try {
            URI base = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            String message = "Xin chào";
            HttpRequest post = HttpRequest.newBuilder(base.resolve("/inspect"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type", "text/plain; charset=utf-8")
                    .header("Accept", "text/plain")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            message, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> response = client.send(
                    post, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            System.out.println("post.status=" + response.statusCode());
            System.out.print(response.body());

            HttpRequest get = HttpRequest.newBuilder(base.resolve("/latin"))
                    .GET().build();
            HttpResponse<String> latin = client.send(
                    get, HttpResponse.BodyHandlers.ofString());
            System.out.println("response.type=" + latin.headers()
                    .firstValue("Content-Type").orElse("(missing)"));
            System.out.println("response.text=" + latin.body());

            String form = "name=" + URLEncoder.encode(
                    "Lan Anh", StandardCharsets.UTF_8)
                    + "&city=" + URLEncoder.encode("Hà Nội", StandardCharsets.UTF_8);
            System.out.println("form=" + form);
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch và chạy trên JDK còn hỗ trợ Java 11:

```bash
javac -encoding UTF-8 --release 11 ContentTypeDemo.java
java ContentTypeDemo
```

**Đầu ra đã kiểm chứng trên JDK 24 khi biên dịch với `--release 11`:**

```text
post.status=200
type=text/plain; charset=utf-8
bytes=9
text=Xin chào
response.type=text/plain; charset=ISO-8859-1
response.text=café
form=name=Lan+Anh&city=H%C3%A0+N%E1%BB%99i
```

Đọc kết quả:

- `post.status=200`: server đã nhận request và trả response; status không tự chứng minh mọi API khác cũng nhận cùng media type.
- `type=text/plain; charset=utf-8`: server nhận đúng header request được client đặt.
- `bytes=9`: chuỗi `"Xin chào"` được encode thành **9 byte UTF-8**, dù `message.length()` chỉ là **8**.
- `text=Xin chào`: server đã dùng cùng UTF-8 để diễn giải request body, nên văn bản đọc được chính xác.
- `response.type=text/plain; charset=ISO-8859-1`: **response có header của riêng nó**, khác header request.
- `response.text=café`: `BodyHandlers.ofString()` (không truyền charset) sử dụng charset từ **response Content-Type**. Ở ví dụ này body chứa byte ISO-8859-1 nên được giải mã đúng.
- `form=...`: `URLEncoder` dùng quy tắc `application/x-www-form-urlencoded`: khoảng trắng trở thành `+`, chữ có dấu được encode thành byte UTF-8 rồi thành dạng `%HH`.

**Giới hạn của fixture:** handler `/inspect` sử dụng `readAllBytes()` vì ví dụ chỉ gửi chuỗi ngắn do chính test tạo. Không sao chép nguyên cách đọc không giới hạn này vào dịch vụ nhận request lớn/không tin cậy; phải giới hạn kích thước input và tài nguyên trước khi lưu/parse.

Nếu dùng `module-info.java`, module chứa HTTP client cần `requires java.net.http;`. Chương trình server fixture còn cần `requires jdk.httpserver;`. Ví dụ trên sử dụng **classpath** để chạy đơn giản với các lệnh đã nêu.

## 7. Request JSON: định dạng và charset

Giả sử server nhận JSON:

```json
{"name":"Linh","active":true}
```

Trong Java 11, có thể tạo body từ `String` JSON **đã hợp lệ**:

```java
String json = "{\"name\":\"Linh\",\"active\":true}";
HttpRequest request = HttpRequest.newBuilder(apiUri)
        .header("Content-Type", "application/json")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
```

Đây là **mảnh mã minh họa**, cần có `apiUri`, các import và client phù hợp để gửi. `BodyPublishers.ofString` không kiểm tra cú pháp JSON và **không serialize Java object thành JSON**. Với dữ liệu động hoặc cấu trúc phức tạp, hãy sử dụng thư viện JSON đúng tiêu chuẩn để tránh lỗi dấu nháy, dấu gạch chéo ngược, ký tự điều khiển hoặc lỗi injection.

**RFC 8259 yêu cầu JSON trao đổi giữa những hệ thống không thuộc cùng một hệ sinh thái đóng phải sử dụng UTF-8.** Vì media type `application/json` không định nghĩa tham số `charset`, đặt `charset=utf-8` trong header không thay thế việc thực sự gửi byte UTF-8.

Nếu server trả JSON, `HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)` giúp đọc văn bản; sau đó vẫn cần **parse JSON**, kiểm tra schema/kiểu trường và xử lý status code. Một HTTP 200 không tự bảo đảm body là JSON hợp lệ.

## 8. Form URL-encoded: Content-Type không phải JSON

Một form đơn giản có thể gửi:

```text
name=Lan+Anh&city=H%C3%A0+N%E1%BB%99i
```

Đây là **form body đã encode**, không phải JSON object hay một đường dẫn URI đầy đủ.

Cách xây dựng các **giá trị trường** theo UTF-8:

```java
String form = "name=" + URLEncoder.encode(
        "Lan Anh", StandardCharsets.UTF_8)
        + "&city=" + URLEncoder.encode(
                "Hà Nội", StandardCharsets.UTF_8);

HttpRequest request = HttpRequest.newBuilder(apiUri)
        .header("Content-Type", "application/x-www-form-urlencoded")
        .POST(HttpRequest.BodyPublishers.ofString(
                form, StandardCharsets.UTF_8))
        .build();
```

Đây là mảnh mã trong phương thức, không phải chương trình độc lập. Server phải có endpoint hiểu form và decode theo quy tắc form; trong một số API charset có thể được thống nhất riêng.

**Chi tiết quan trọng:**
- Trong các **giá trị form**, khoảng trắng thường được biểu diễn thành `+`.
- Dấu cộng **thật** trong dữ liệu sẽ được encode thành `%2B` để không bị hiểu thành khoảng trắng.
- Dấu `&` trong giá trị phải được encode thành `%26`; nếu nối thẳng vào body nó có thể bị hiểu thành ký hiệu ngăn cách giữa các trường.
- `URLEncoder` được thiết kế cho `application/x-www-form-urlencoded`, **không phải trình tạo URL tổng quát** cho toàn bộ đường dẫn URI.
- Khai báo `application/json` nhưng gửi `name=Lan+Anh` là sai ý nghĩa dữ liệu; đổi header không biến form thành JSON.

## 9. Multipart và dữ liệu nhị phân

### 9.1. Multipart/form-data

Khi một request chứa nhiều phần (ví dụ trường văn bản và tệp upload), thường gặp:

```http
Content-Type: multipart/form-data; boundary=demoBoundary
```

Body tương ứng chứa những phần được phân tách bằng dấu `--demoBoundary`, mỗi phần có metadata riêng như `Content-Disposition`; có thể có `Content-Type` riêng cho phần tệp.

**Header và body phải đồng bộ boundary.** Không chỉ đặt `multipart/form-data` (hoặc tự chọn một boundary) rồi gửi byte JSON/chuỗi thường và cho rằng server sẽ tự tạo các phần. `HttpClient` Java 11 không cung cấp tiện ích multipart builder chuyên biệt ngang mức `BodyPublishers.ofString`; khi cần multipart đầy đủ, phải tự tạo body đúng tiêu chuẩn hoặc chọn thư viện hỗ trợ phù hợp.

### 9.2. Byte nhị phân không dùng charset văn bản

Nếu payload là byte ảnh hoặc tệp nhị phân:

```java
byte[] payload = getBinaryData();
HttpRequest upload = HttpRequest.newBuilder(apiUri)
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofByteArray(payload))
        .build();
```

Đây là đoạn minh họa trong chương trình; `getBinaryData()` và `apiUri` do ứng dụng cung cấp. Khi API biết loại file chính xác, dùng media type chuyên biệt như `image/png` hay `application/pdf` thay cho loại chung `application/octet-stream` nếu phù hợp.

Không giải mã byte nhị phân thành `String`, rồi encode lại tùy ý: thao tác đó có thể **làm hỏng byte** vì nhiều chuỗi byte không phải văn bản hợp lệ. Với file lớn, dùng `BodyPublishers.ofFile(path)` khi phù hợp và quản lý giới hạn, đường dẫn, quyền đọc.

## 10. Response Content-Type và cách BodyHandler giải mã

`Content-Type` của **response** có thể độc lập với request. Ví dụ server trả:

```http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=ISO-8859-1
```

Với Java 11:

```java
HttpResponse<String> automatic = client.send(
        request, HttpResponse.BodyHandlers.ofString());

HttpResponse<String> forcedUtf8 = client.send(
        request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
```

Đây là **mảnh mã minh họa** hai request riêng (nếu gửi cả hai), cần import và xử lý exception. Hai cách có ý nghĩa khác nhau:

- **`BodyHandlers.ofString()`** chọn charset theo **`Content-Type` trong response**. Nếu không có header đó hoặc charset không được hỗ trợ, API Java 11 dùng **UTF-8** làm fallback.
- **`BodyHandlers.ofString(StandardCharsets.UTF_8)`** luôn chọn **UTF-8 do caller chỉ định** để decode body, ngay cả khi header khai báo một charset khác.

Ví dụ chương trình mục 6 cho thấy `ofString()` đọc đúng `"café"` từ byte ISO-8859-1. Nếu bạn ép UTF-8 cho những byte ISO-8859-1 không hợp lệ, kết quả có thể chứa ký tự thay thế. Không ép một charset tùy tiện rồi coi dữ liệu bị lỗi là lỗi của HTTP client.

Khi xử lý nội dung không tin cậy hoặc kích thước lớn, `BodyHandlers.ofString` có thể giữ nhiều dữ liệu trong RAM. Lựa chọn khác:
- `BodyHandlers.ofByteArray()` lấy byte gốc để tự kiểm tra/giải mã, nhưng vẫn giữ toàn bộ byte trong bộ nhớ.
- `BodyHandlers.ofInputStream()` cho phép stream và giới hạn byte; cần **đóng stream** khi xong.
- `BodyHandlers.ofFile(path)` ghi ra file, cần kiểm soát quyền và xử lý file tạm/an toàn.
- `BodyHandlers.discarding()` bỏ body khi chắc chắn không cần đọc nội dung.

**Không tự giả định HttpClient đã giải nén mọi `Content-Encoding`.** Khi server trả response nén, cần làm rõ khả năng tự xử lý của môi trường và thiết kế body handler/giải nén phù hợp; `Content-Type` mô tả nội dung **sau khi** các content coding đã được gỡ theo đúng thứ tự.

## 11. Điều gì xảy ra khi Content-Type bị thiếu hoặc sai?

### 11.1. Thiếu Content-Type

HTTP cho phép có thông điệp thiếu header `Content-Type` trong một số tình huống. Bên nhận có thể không biết định dạng; không có đảm bảo mọi server/client sẽ “đoán” giống nhau. **Đối với API mà bạn kiểm soát, hãy gửi `Content-Type` đúng khi có body** thay vì phụ thuộc vào suy đoán hoặc tự nhận dạng dữ liệu.

Không khẳng định rằng nếu thiếu `Content-Type` thì request luôn bị từ chối. Tùy endpoint, server có thể chấp nhận, áp dụng mặc định hoặc trả lỗi.

### 11.2. Header sai media type

Ví dụ gửi JSON byte nhưng ghi `Content-Type: text/plain`. Server mong JSON có thể từ chối với **415 Unsupported Media Type** hoặc xử lý khác theo hợp đồng. Trường hợp khai báo đúng media type nhưng body sai cú pháp có thể bị từ chối với **400 Bad Request**, nhưng **mã trạng thái cụ thể do server quyết định**.

Không coi `Content-Type: application/json` là bằng chứng body thực sự là JSON. Phải parse và validate theo schema.

### 11.3. Header đúng loại nhưng charset sai

Có thể gặp text méo dạng, ký tự `�` hoặc lỗi parse. Khi debug, hãy kiểm tra:
1. Body được **encode thành byte** bằng charset nào?
2. Header `Content-Type` của request hoặc response thực tế là gì?
3. Server/client decode bằng charset nào?
4. Có lớp nén (`Content-Encoding`), proxy hay biến đổi dữ liệu nào xen vào không?
5. Có phải dữ liệu đã bị encode/decode **hai lần** không?

Dùng byte hex hoặc so sánh `byte[]` trên môi trường test để xác định lỗi thay vì thay header liên tục mà không kiểm tra byte thực.

## 12. Kiểm thử, bảo mật và giới hạn dữ liệu

### 12.1. Bộ ca kiểm thử nên có

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Text ASCII | Header đúng và byte body trùng mã hóa dự kiến. |
| Tiếng Việt có dấu | Đếm đúng byte UTF-8; nhận lại đúng ký tự. |
| Emoji/Unicode ngoài BMP | Không nhầm độ dài `String` với byte hay code point. |
| Sai charset | Hệ thống phát hiện hoặc xử lý lỗi theo chính sách, không âm thầm ghi dữ liệu méo. |
| Thiếu/sai `Content-Type` | Ứng dụng phản hồi theo hợp đồng rõ ràng; không giả định status cố định. |
| JSON sai cú pháp | Parser/validator từ chối, không chỉ dựa vào header. |
| Form có dấu `+`, `&`, dấu cách | Encode/decode đúng quy tắc `application/x-www-form-urlencoded`. |
| File nhị phân | Byte được giữ nguyên; không đổi thành `String` tùy ý. |
| Body lớn | Có giới hạn byte, bộ nhớ, thời gian và khả năng hủy xử lý. |
| Content coding | Nếu `gzip`, thao tác giải nén đúng lớp, không nhầm `Content-Type`. |

### 12.2. Không tin Content-Type do phía không tin cậy khai báo

Trong một server nhận upload, `Content-Type: image/png` chỉ là **lời khai metadata** từ client. Nó **không chứng minh** byte body là ảnh PNG hợp lệ và không chứng minh file an toàn. Nếu nghiệp vụ cần kiểm tra loại file, phải xác minh chữ ký/định dạng thực tế, giới hạn dung lượng và dùng parser đáng tin cậy; không dùng duy nhất phần mở rộng tên tệp hoặc header.

Khi hiển thị nội dung người dùng cung cấp trên web, `text/html` có thể mang mã script; cần áp dụng output encoding/sanitization và các header/chính sách bảo vệ phù hợp. Đừng biến dữ liệu chưa tin cậy thành HTML chỉ bằng cách đặt header. Nếu server muốn trình duyệt không tự đoán MIME type, có thể cân nhắc `X-Content-Type-Options: nosniff` trong ngữ cảnh response browser phù hợp.

### 12.3. Giới hạn bộ nhớ và không log bí mật

`BodyHandlers.ofString()` và `ofByteArray()` có thể đọc toàn bộ body vào bộ nhớ; với endpoint không tin cậy, hãy áp dụng timeout và giới hạn byte, cân nhắc xử lý stream có kiểm soát.

Không ghi log nguyên body chứa mật khẩu, token, cookie, thông tin nhận dạng hoặc dữ liệu riêng tư. Khi kiểm thử cần xem body, dùng payload giả lập không nhạy cảm như ví dụ localhost.

### 12.4. Một lưu ý về charset và bảo mật

Nếu một lớp bảo vệ kiểm tra text đã decode bằng charset A nhưng thành phần khác lại decode cùng byte theo charset B, hai bên có thể hiểu **khác nội dung**. Thống nhất media type/charset tại ranh giới tin cậy, từ chối input sai encoding khi cần, và luôn kiểm tra cú pháp, giới hạn tài nguyên, quyền truy cập độc lập với header.

## 13. Lỗi thường gặp và cách sửa

| Hiểu nhầm / lỗi | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Chỉ đặt `Content-Type: text/plain; charset=utf-8` là đã gửi UTF-8 | Header không encode body. | Tạo byte bằng `StandardCharsets.UTF_8` trong publisher/encoder. |
| Nghĩ `String.length()` bằng `Content-Length` | UTF-16 code units khác byte sau mã hóa. | Đếm `getBytes(UTF_8).length` khi cần biết byte. |
| Gửi JSON nhưng `Content-Type` là form hoặc text | Media type không khớp representation. | Chọn `application/json` và body JSON hợp lệ UTF-8. |
| Cho rằng JSON phải luôn ghi `charset=utf-8` | RFC 8259 không định nghĩa tham số charset cho `application/json`. | Dùng `application/json`, encode byte UTF-8; tuân hợp đồng đặc thù nếu có. |
| Gửi form với các dấu `&`/`+` chưa encode | Server có thể hiểu sai cặp trường. | `URLEncoder` cho **từng giá trị form**, không cho toàn bộ URI. |
| Gửi multipart chỉ bằng cách gắn header | Chưa có boundary và byte body đúng cấu trúc. | Tạo multipart body đúng chuẩn, khớp boundary. |
| Đọc file nhị phân bằng `new String(bytes)` | Byte không nhất thiết là văn bản. | Dùng `byte[]`, `InputStream` hoặc file API. |
| Nghĩ `Accept` nói loại body đang gửi | `Accept` mô tả response mong muốn. | Dùng request `Content-Type` cho body gửi. |
| Nghĩ `Content-Encoding: gzip` là charset | Compression là lớp mã hóa nội dung khác charset. | Xử lý gzip/encoding rồi mới diễn giải định dạng nội dung. |
| Dùng `BodyHandlers.ofString(UTF_8)` bất chấp response header Latin-1 | Có thể decode sai ký tự. | Theo đặc tả endpoint; dùng `ofString()` nếu muốn theo charset từ response. |
| Dựa vào status 200 để kết luận body hợp lệ | Status và cú pháp/nội dung là hai lớp kiểm tra. | Kiểm tra status, media type, parse và schema. |
| Tin vào `Content-Type` của file upload | Header do client khai báo có thể sai/cố ý giả. | Xác minh nội dung thực, kiểm soát loại và kích thước. |

## 14. Tự luyện và đáp án

**Câu 1.** Gửi chuỗi `"Xin chào"` qua UTF-8 nhưng lấy `text.length()` làm chiều dài body có đúng không?

**Đáp án:** Không. Đó là 8 đơn vị `char` UTF-16 nhưng **9 byte UTF-8**. Không tự đặt Content-Length theo `String.length()`.

**Câu 2.** Gửi body JSON `{"ok":true}` với `Content-Type: text/plain` có khớp ý nghĩa dữ liệu không?

**Đáp án:** Không nếu endpoint yêu cầu JSON. Dùng `Content-Type: application/json`, body đúng cú pháp JSON và byte UTF-8.

**Câu 3.** `Accept: application/json` có làm `BodyPublishers.ofString(...)` tạo JSON không?

**Đáp án:** Không. `Accept` là sở thích response. Request body vẫn phải tự được serialize và mô tả bằng `Content-Type` đúng.

**Câu 4.** Response khai báo `text/plain; charset=ISO-8859-1`. `BodyHandlers.ofString()` và `BodyHandlers.ofString(UTF_8)` có luôn giống nhau không?

**Đáp án:** Không. Overload không tham số chọn charset từ response `Content-Type` (fallback UTF-8 theo API); overload truyền UTF-8 ép decode theo UTF-8.

**Câu 5.** Muốn gửi form với giá trị `"a+b & c"`, có thể nối thẳng vào chuỗi `"q="+value` không?

**Đáp án:** Không. Dấu cộng, dấu cách và `&` có ý nghĩa đặc biệt trong form. Encode từng giá trị bằng `URLEncoder.encode(value, UTF_8)`.

**Câu 6.** Với file ảnh PNG, có nên dùng `Content-Type: image/png; charset=utf-8` không?

**Đáp án:** Không. PNG là dữ liệu nhị phân; `charset` không diễn giải PNG. Gửi byte thật và media type `image/png` nếu đúng định dạng.

**Câu 7.** Chỉ thay header thành `multipart/form-data` có khiến body text thành multipart hợp lệ không?

**Đáp án:** Không. Body phải có cấu trúc nhiều phần và boundary khớp header.

**Câu 8.** Nhận upload có `Content-Type: application/pdf` thì có thể bỏ qua kiểm tra byte/size/filename không?

**Đáp án:** Không. Header không chứng minh nội dung hợp lệ/an toàn. Kiểm tra định dạng, kích thước, đường dẫn và chính sách lưu trữ.

**Câu 9.** `Content-Encoding: gzip` và `Content-Type: application/json` có mâu thuẫn không?

**Đáp án:** Không. Dữ liệu được nén gzip nhưng sau giải nén biểu diễn JSON. Đây là hai lớp metadata khác nhau.

## 15. Tổng kết và tài liệu chuẩn

- **`Content-Type` mô tả định dạng/ý nghĩa của body, không tự chuyển đổi dữ liệu.**
- **`charset` nói về cách diễn giải byte thành văn bản** khi media type hỗ trợ tham số đó; chọn charset nhất quán ở cả encode và decode.
- Dùng **UTF-8** tường minh cho văn bản và JSON trao đổi giữa hệ thống; với `application/json`, RFC 8259 **không định nghĩa tham số charset**.
- `String.length()` không đo số byte HTTP. Chọn `BodyPublishers.ofString(text, UTF_8)` hoặc `getBytes(UTF_8)` để biết byte truyền thực tế.
- `Content-Type` của request khác `Accept`; `Content-Type` của response lại thuộc body do server gửi. `Content-Encoding` không phải charset.
- Form dùng quy tắc `application/x-www-form-urlencoded`; multipart cần boundary/body khớp; binary giữ byte nguyên trạng.
- Trong Java 11, `BodyHandlers.ofString()` giải mã theo charset từ response Content-Type, với fallback UTF-8 khi không có hoặc charset không hỗ trợ; overload có `Charset` dùng charset chỉ định.
- Khi nhận dữ liệu không tin cậy, **không tin header một cách mù quáng**: kiểm tra status, cấu trúc, encoding, dung lượng và bảo mật.

Nguồn tham khảo chính thức và còn áp dụng:

- [Oracle Java SE 11 — HttpRequest và BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html).
- [Oracle Java SE 11 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html).
- [Oracle Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html).
- [Oracle Java SE 11 — StandardCharsets](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/StandardCharsets.html).
- [RFC 9110 — HTTP Semantics: Content-Type, Content-Encoding, Accept](https://www.rfc-editor.org/rfc/rfc9110.html).
- [RFC 8259 — JSON encoding và media type application/json](https://www.rfc-editor.org/rfc/rfc8259.html).