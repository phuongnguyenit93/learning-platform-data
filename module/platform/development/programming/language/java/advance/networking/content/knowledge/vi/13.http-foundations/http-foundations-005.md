# Content-Type, charset, Content-Length và biểu diễn dữ liệu trong HTTP

## 1. Vì sao phải phân biệt nội dung, cách mã hóa và số byte?

Một bản tin HTTP mang **representation data** (dữ liệu biểu diễn tài nguyên/thông điệp) cùng các metadata giúp phía nhận hiểu dữ liệu đó. Ba trường hay bị nhầm:

- **`Content-Type`** cho biết loại media của biểu diễn, ví dụ `text/plain`, `application/json`, `image/png`; một số media type có tham số `charset` chỉ cách chuyển byte thành ký tự.
- **`charset`** không phải header độc lập bắt buộc; thường là **tham số** của `Content-Type`, ví dụ `Content-Type: text/plain; charset=UTF-8`. Nó nói cách **giải mã ký tự**, không nói cách chia frame TCP.
- **`Content-Length`** là **số octet (byte)** được khai báo theo ngữ nghĩa HTTP. Khi gửi nội dung với HTTP/1.1 và không có `Transfer-Encoding`, nó được dùng để xác định số byte content trong message; **không phải số ký tự, số dòng, kích thước object Java hay số byte của cả HTTP message gồm headers**.

Với dữ liệu đã nén, còn một tầng quan trọng: **`Content-Encoding`** như `gzip` nói rằng bytes của representation đã qua content coding. Khi ấy `Content-Length` (nếu áp dụng cho nội dung truyền) đếm **bytes đã mã hóa/nén** trong HTTP content, không phải bytes UTF-8 trước nén.

Sơ đồ thao tác ở client/server:

```text
  Dữ liệu logic
       |
       v
  Serialization theo media type
  (text, JSON, XML, form, PNG, protobuf, ...)
       |
       v
  Character encoding nếu là dữ liệu văn bản
  ("Xin chào" --> UTF-8 bytes)
       |
       v
  Optional Content-Encoding, ví dụ gzip
       |
       v
  HTTP content bytes
       |
       +---- Content-Type: mô tả media type gốc
       +---- charset: cách giải mã văn bản nếu media type định nghĩa
       +---- Content-Encoding: phép biến đổi content coding
       +---- Content-Length: byte count theo quy tắc HTTP
       |
       v
  HTTP/1.1 framing hoặc HTTP/2/3 framing
       |
       v
  Transport (TCP/TLS/QUIC tương ứng)
```

Ở phía nhận làm ngược lại: xác định ranh giới HTTP content → giải content coding (nếu có) → giải mã bytes theo media type và charset hợp lệ → parse ra JSON/text/binary → validate dữ liệu nghiệp vụ. **Không thể suy ra toàn bộ quá trình chỉ từ một header**.

## 2. Đọc một HTTP/1.1 message đúng cách

Ví dụ body là chuỗi `Xin chào` dưới dạng UTF-8:

```http
POST /notes HTTP/1.1
Host: example.test
Content-Type: text/plain; charset=UTF-8
Content-Length: 9

Xin chào
```

Đoạn nhìn bằng mắt ở trên là biểu diễn dễ đọc của message; theo HTTP/1.1, dòng header được phân tách bằng **CRLF** và có một dòng trống CRLF giữa header section và body. Body thực chất là **chín byte UTF-8**, không phải tám byte:

```text
Ký tự: X   i   n  [ ]  c   h    à      o
Hex:   58  69  6E  20   63  68  C3 A0   6F

String "Xin chào":
  8 UTF-16 code units (và 8 Unicode code points trong ví dụ)
  9 bytes khi mã hóa UTF-8
```

Do `à` được mã hóa thành hai byte `C3 A0`, nếu lấy `"Xin chào".length()` rồi đặt `Content-Length: 8`, receiver HTTP/1.1 có thể coi thông điệp kết thúc **trước byte cuối**. Trong hệ thống HTTP keep-alive, dữ liệu thừa còn có thể làm lệch việc phân tách message tiếp theo. Không tự sửa vấn đề bằng cách tăng timeout hoặc dựa vào một lần `socket.write()`: đây là lỗi **framing**.

**Header field names không phân biệt hoa thường**: `content-type`, `Content-Type` hoặc `CONTENT-TYPE` là tên cùng một trường. Ngược lại, giá trị tham số và media type phải được diễn giải theo quy tắc riêng (media type và tên tham số nhìn chung không phân biệt case; nội dung bytes không tự đổi). Khi học cấu trúc HTTP/1.1, không được coi dòng trống hay `\n` của bài minh họa là giao thức message framing có thể tự thay thế CRLF tùy ý.

## 3. `Content-Type` mô tả loại biểu diễn

Cú pháp phổ biến:

```text
Content-Type: <type>/<subtype>; parameter=value

Ví dụ:
Content-Type: text/plain; charset=UTF-8
Content-Type: text/html; charset=utf-8
Content-Type: application/json
Content-Type: application/octet-stream
Content-Type: multipart/form-data; boundary=----demo-boundary
```

**Media type** nói receiver cần sử dụng parser/handler nào:

| Media type | Nội dung thường gặp | Điều cần chú ý |
| --- | --- | --- |
| `text/plain` | Văn bản thuần | Phải thống nhất charset khi dùng ký tự ngoài ASCII |
| `text/html` | HTML | Charset có thể khai qua HTTP header và/hoặc metadata của tài liệu; các quy tắc ưu tiên phụ thuộc HTML |
| `application/json` | JSON | JSON trao đổi ngoài closed ecosystem phải dùng UTF-8 theo RFC 8259 |
| `application/xml` hoặc `text/xml` | XML | Có quy tắc encoding riêng của XML/media type; không mặc định giống JSON |
| `application/octet-stream` | Byte nhị phân | Không ép decode sang `String` |
| `image/png` | Ảnh PNG | Parse theo định dạng PNG, không giải mã chữ |
| `application/x-www-form-urlencoded` | Form key/value URL-encoded | Percent-encoding và charset của form ảnh hưởng bytes |
| `multipart/form-data; boundary=...` | Nhiều part (file, field...) | Byte body gồm cả boundary, part headers và CRLF, không chỉ nội dung file |

**Không suy ra kiểu thực sự chỉ từ đuôi file**. `file.json` có thể được gửi sai `Content-Type`; client phải xử lý theo hợp đồng API, kiểm tra response media type và validate payload. `Content-Type` không phải bằng chứng nội dung an toàn: không tin arbitrary upload chỉ vì nó tuyên bố `image/png` hay `application/json`.

**`Accept` khác `Content-Type`:**

- Client gửi `Accept: application/json` là **sở thích/khả năng nhận response**.
- Client gửi `Content-Type: application/json` là **mô tả body của request hiện tại**.
- Server gửi `Content-Type: application/json` mô tả **response đã chọn**.
- Nếu server không hỗ trợ media type request, có thể trả `415 Unsupported Media Type`; nếu không thể đáp ứng lựa chọn trong `Accept`, có thể trả `406 Not Acceptable`. Phản ứng thực tế tùy API contract.

Không phải response nào cũng có body; khi không có body, `Content-Type` có thể vắng mặt. Nếu có response bytes cần xử lý, điều quan trọng là xác định media type trước khi parse.

## 4. `charset`: từ byte thành ký tự và ngược lại

Với `Content-Type: text/plain; charset=UTF-8`, phía gửi làm:

```java
String text = "Xin chào";
byte[] body = text.getBytes(StandardCharsets.UTF_8);
int contentLength = body.length; // 9, không phải text.length() == 8
```

Phía nhận làm ngược lại:

```java
String decoded = new String(body, StandardCharsets.UTF_8);
```

Hai mảnh code trên giả định có `import java.nio.charset.StandardCharsets;` và biến `body` đúng dữ liệu UTF-8 đã nhận. Khi dùng API Java trả về raw `byte[]`, **caller chịu trách nhiệm** chọn charset đúng và kiểm tra dữ liệu hợp lệ.

Những khái niệm cần tách rõ:

- `String.length()` của Java đếm **UTF-16 code units**, không đếm byte UTF-8. Ký tự supplementary code point như một số emoji có thể chiếm **hai UTF-16 code units**.
- `String.codePointCount(...)` đếm Unicode code points của đoạn chuỗi, vẫn không phải độ dài bytes.
- `text.getBytes(StandardCharsets.UTF_8).length` là số bytes sau mã hóa UTF-8; đây là đại lượng cần dùng khi tính kích thước **byte body**.
- `byte[].length` là dung lượng của mảng cụ thể. Nếu body có prefix/header/trailer riêng của media type, còn phải tính **toàn bộ bytes thực gửi**, không chỉ bytes chữ.
- `CharsetDecoder` với `CodingErrorAction.REPORT` hữu ích khi cần **từ chối byte sequence không hợp lệ** thay vì âm thầm thay bằng ký tự thay thế.

**Không tồn tại một charset mặc định duy nhất áp dụng cho mọi media type HTTP.** Khi gửi text do bạn kiểm soát, cách an toàn và dễ tương tác là chọn UTF-8 **rõ ràng** ở cả header (với các media type dùng tham số charset) và khi chuyển đổi Java `String`↔bytes. Đối với text thiếu charset, quy tắc fallback phụ thuộc media type, giao thức và ứng dụng; không nên ngẫu nhiên dùng platform default encoding.

### Trường hợp `application/json`

RFC 8259 quy định **JSON text trao đổi giữa các hệ thống không thuộc một hệ sinh thái đóng phải mã hóa UTF-8**. Media type `application/json` trong đăng ký IANA **không định nghĩa tham số `charset`**; thêm `charset=UTF-8` không làm thay đổi cách xử lý của receiver tuân thủ RFC. Nên gửi:

```http
Content-Type: application/json
```

và mã hóa body theo UTF-8. Ví dụ `{"message":"Chào"}` có **19 byte UTF-8**; đoạn mã chạy trong mục 9 xác nhận điều này. Dù nội dung là JSON text, `Content-Length` vẫn là **19** khi gửi không nén, không phải số ký tự trong chuỗi JSON.

Nếu code làm `json.getBytes()` mà không chỉ định charset, hành vi gắn với cấu hình JVM/JDK và môi trường; đối với protocol, hãy dùng `json.getBytes(StandardCharsets.UTF_8)` để không lệ thuộc giả định ngầm.

### UTF-8 và BOM

Với JSON truyền trên mạng, RFC 8259 nói generator **không được thêm BOM** ở đầu JSON text. Một số parser có thể bỏ qua BOM để tăng interoperability, nhưng không được dựa vào hành vi đó. Với HTML/XML, quy tắc về BOM, encoding declaration hoặc HTTP charset có thể khác; cần theo media type tương ứng thay vì áp dụng nguyên xi từ JSON.

## 5. `Content-Length` thực sự đếm gì?

Theo HTTP Semantics (RFC 9110), `Content-Length` có dạng **số thập phân nguyên không âm**, đơn vị **octet** (byte). Khi message có body content và không dùng HTTP/1.1 transfer coding, giá trị là **độ dài bytes của HTTP content** để recipient biết kết thúc message ở đâu.

```text
String original: "Xin chào"         -> length() = 8
UTF-8 encoded: 58 69 6E 20 63 68 C3 A0 6F
HTTP content bytes: 9             -> Content-Length: 9
```

Không tính:

- Header lines của HTTP (ví dụ `Host`, `Content-Type` và CRLF phân cách).
- TCP header, TLS record header, IP packet header.
- Ký tự trong Java `String` hay số code points.
- Số đối tượng JSON, số dòng hoặc số file trong form.
- Số bytes trước gzip nếu HTTP content đang gửi **bytes gzip**.

**Người gửi chịu trách nhiệm cung cấp chính xác kích thước khi tự xử lý framing.** Trong Java `HttpClient`, body publisher chuẩn đã biết số bytes có thể cho transport tính Content-Length; **không tự đặt Content-Length bằng số ký tự**. Với stream không biết trước kích thước, để HTTP stack sử dụng framing hợp lệ tương ứng.

### Ngoại lệ quan trọng

Đừng khẳng định mọi giá trị `Content-Length` xuất hiện đều có nghĩa "body chắc chắn có từng ấy byte". RFC 9110 cho phép/giới hạn các trường hợp riêng:

- Response cho `HEAD` **không có response body**; nếu gửi `Content-Length` thì giá trị phải bằng số bytes **sẽ được gửi** trong content của response tương ứng với `GET`.
- Response `304 Not Modified` **không có body**; nếu chứa `Content-Length` thì nó phải diễn tả số bytes **sẽ có** trong response `200 OK` tương ứng.
- Không gửi `Content-Length` trong response `1xx` hoặc `204 No Content`; cũng không gửi trong response `2xx` của `CONNECT`.
- Trong HTTP/1.1, sự hiện diện và độ dài message body phải tuân theo **thứ tự ưu tiên framing** của RFC 9112, chứ không được chỉ nhìn vào trường header một cách tách biệt.

Với body nhỏ, `Content-Length: 0` nghĩa là zero content bytes. Nhưng **request không có body** không nhất thiết luôn cần trường này; cách ứng dụng/tầng HTTP tạo message phụ thuộc method và contract.

## 6. Phân biệt `Content-Encoding` với `Transfer-Encoding`

Đây là hai tầng khác nhau:

| Header | Đối tượng mô tả | Ví dụ | Thứ tự giải mã |
| --- | --- | --- | --- |
| `Content-Type` | Media type của representation | `application/json` | Chọn parser sau khi có decoded representation bytes |
| `charset` parameter | Encoding ký tự nếu media type định nghĩa | `UTF-8` | Chuyển byte văn bản thành ký tự |
| `Content-Encoding` | **Content coding** áp dụng lên representation | `gzip` | Giải nén/decode content coding trước khi parse JSON/text |
| `Transfer-Encoding` | Transfer coding/framing ở **HTTP/1.1** | `chunked` | HTTP stack bỏ framing khi đọc message |
| `Content-Length` | Số octet liên quan đến representation/message content theo quy tắc RFC | `39` | Framing khi được phép và không có transfer coding |

Ví dụ gửi JSON `{"message":"Chào"}` đã được gzip:

```http
POST /inspect HTTP/1.1
Host: localhost
Content-Type: application/json
Content-Encoding: gzip
Content-Length: 39

<39 byte gzip - nội dung nhị phân, không thể biểu diễn là JSON text thô>
```

Trong ví dụ Java đã chạy:

- JSON UTF-8 **trước nén** dài **19 byte**.
- Dùng `GZIPOutputStream` của JDK tạo dữ liệu nén **39 byte** trong lần test.
- HTTP body gửi **39 byte gzip** → `Content-Length: 39`.
- Server đọc đúng 39 byte, giải nén thành 19 byte UTF-8 rồi mới đọc JSON text.

**Không gọi `new String(compressedBytes, UTF_8)` để parse JSON.** Bước giải `Content-Encoding: gzip` phải đi trước giải charset và parse. Một client HTTP cấp cao có thể hỗ trợ tự giải content coding theo cấu hình; mã dùng raw body bytes hoặc server HTTP primitive cần kiểm tra thực tế thư viện có xử lý tự động hay không.

**`Transfer-Encoding: chunked` không phải gzip.** Ở HTTP/1.1, chunked mô tả cách truyền message body theo các chunk có kích thước và dấu kết thúc. Sau khi HTTP decoder bỏ chunk framing, ứng dụng nhận content bytes. Sender **không được đồng thời gửi `Transfer-Encoding` và `Content-Length`** trong cùng một HTTP/1.1 message. Kết hợp sai hai trường có nguy cơ tạo cách hiểu ranh giới khác nhau giữa proxy và backend.

## 7. HTTP/1.1 chunked, HTTP/2 và HTTP/3

Khi biết kích thước content trước lúc gửi HTTP/1.1 response, có thể dùng một `Content-Length` hợp lệ. Với streaming response không biết kích thước, HTTP/1.1 có thể dùng **`Transfer-Encoding: chunked`**, chẳng hạn:

```http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Transfer-Encoding: chunked

5
Hello
0

```

Đây là ví dụ trực quan các dòng chunk (trên wire phải dùng CRLF chuẩn); `5` là **số byte ở hệ hex**, không phải Content-Length. Chunk terminator `0` đánh dấu kết thúc data. Với dữ liệu UTF-8 nhiều byte, chunk size vẫn đếm bytes và một ký tự UTF-8 có thể bị chia giữa các chunk mà stream decoder cuối vẫn tái tạo được khi ghép đúng bytes.

Trong HTTP/2 và HTTP/3, framing dùng **các frame DATA của giao thức tương ứng**; không dùng `Transfer-Encoding: chunked` kiểu HTTP/1.1. `Content-Length` có thể tồn tại như metadata kiểm tra kích thước nội dung, nhưng không phải delimiter TCP byte stream kiểu HTTP/1.1. Đừng tự parse HTTP/2 trên `InputStream` như raw HTTP/1.1 lines.

**Bài học thực hành:** dùng `HttpClient`, server framework hoặc thư viện HTTP chuẩn để xử lý framing, thay vì tự tính chunked/HTTP2 frames bằng tay. Ứng dụng nên chọn media type/charset/bytes chính xác; transport layer chịu trách nhiệm đóng khung theo phiên bản HTTP.

## 8. Ví dụ lỗi điển hình khi tính Content-Length

Đoạn code này minh họa sai:

```java
String body = "Xin chào";
int wrong = body.length(); // 8, KHÔNG phải độ dài UTF-8.
```

Đúng:

```java
byte[] utf8 = body.getBytes(StandardCharsets.UTF_8);
int correct = utf8.length;  // 9 bytes
```

Với API thực sự quản lý transfer, thường **không tự gắn Content-Length**: đưa đúng bytes cho body publisher và để thư viện tính:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "text/plain; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofByteArray(utf8))
        .build();
```

*Đây là đoạn nằm trong chương trình có biến `uri`, `utf8` và import `java.net.http.HttpRequest`.* Một số header do Java HTTP client kiểm soát (bao gồm `Content-Length`) bị hạn chế đặt thủ công theo chính sách triển khai. Không tìm cách ép chúng qua tùy chọn nội bộ; nếu body có kích thước cố định, dùng publisher cho byte array/string/file phù hợp.

### `HttpURLConnection` / raw stream

Nếu API yêu cầu bạn cung cấp kích thước streaming **trước khi gửi**, phải chuyển sang bytes trước:

```java
// Mảnh code: đã có HttpURLConnection conn.
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
conn.setDoOutput(true);
conn.setRequestProperty("Content-Type", "application/json");
conn.setFixedLengthStreamingMode(bytes.length);
try (OutputStream out = conn.getOutputStream()) {
    out.write(bytes);
}
```

*Đoạn này không phải chương trình standalone; giả định `conn` là HTTP URL connection chưa bắt đầu gửi, `json` là chuỗi JSON hợp lệ, và caller xử lý `IOException`. Cần import `OutputStream` và `StandardCharsets`.* Gọi `setFixedLengthStreamingMode` sau khi đã mở connection/stream có thể quá muộn; dùng khi đã biết số bytes chính xác. Tránh vừa mở `Writer` với charset khác vừa tính length bằng UTF-8.

## 9. Chương trình Java 17+ hoàn chỉnh: HTTP client/server loopback

Ví dụ chạy không cần Internet: `com.sun.net.httpserver.HttpServer` phục vụ endpoint `/inspect` trên loopback, `java.net.http.HttpClient` gửi hai request HTTP/1.1.

- **Request 1:** `text/plain; charset=UTF-8`, payload `Xin chào`. Server đọc bytes, xác minh `Content-Length` so với số bytes nhận rồi decode UTF-8.
- **Request 2:** `application/json` + `Content-Encoding: gzip`. Client mã hóa JSON thành UTF-8 rồi nén, gửi **compressed bytes**; server giải nén trước khi decode.
- Hai response của server là `text/plain; charset=UTF-8` và được gửi bằng bytes UTF-8 với kích thước đúng.
- Client dùng `BodyPublishers.ofByteArray(...)` nên số bytes truyền **được xác định trước** và HTTP client đặt framing tương ứng. Phần code **không tự điền Content-Length header**.

**Tệp `HttpRepresentationDemo.java`:**

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public final class HttpRepresentationDemo {
    private static byte[] gzip(byte[] bytes) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (GZIPOutputStream zipper = new GZIPOutputStream(output)) {
            zipper.write(bytes);
        }
        return output.toByteArray();
    }

    private static void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
            if (!"POST".equals(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(405, -1);
                return;
            }

            String mediaType = exchange.getRequestHeaders()
                    .getFirst("Content-Type");
            String encoding = exchange.getRequestHeaders()
                    .getFirst("Content-Encoding");
            String declared = exchange.getRequestHeaders()
                    .getFirst("Content-Length");
            byte[] received = exchange.getRequestBody().readAllBytes();

            byte[] decoded = received;
            if ("gzip".equalsIgnoreCase(encoding)) {
                try (GZIPInputStream unzip = new GZIPInputStream(
                        new ByteArrayInputStream(received))) {
                    decoded = unzip.readAllBytes();
                }
            }
            String text = new String(decoded, StandardCharsets.UTF_8);
            boolean correctLength = declared != null
                    && Long.parseLong(declared) == received.length;
            String response = "type=" + mediaType
                    + "; lengthMatches=" + correctLength
                    + "; content=" + text;
            byte[] responseBytes =
                    response.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type",
                    "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, responseBytes.length);
            exchange.getResponseBody().write(responseBytes);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext("/inspect", HttpRepresentationDemo::handle);
        server.start();
        try {
            URI uri = URI.create("http://" +
                    (loopback.getHostAddress().contains(":")
                        ? "[" + loopback.getHostAddress() + "]"
                        : loopback.getHostAddress())
                    + ":" + server.getAddress().getPort() + "/inspect");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();

            String message = "Xin chào";
            byte[] utf8 = message.getBytes(StandardCharsets.UTF_8);
            HttpRequest plain = HttpRequest.newBuilder(uri)
                    .header("Content-Type", "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(utf8))
                    .build();
            HttpResponse<String> plainResponse = client.send(plain,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("text UTF-16 units=" + message.length()
                    + ", UTF-8 bytes=" + utf8.length);
            System.out.println("text reply: " + plainResponse.body());

            String json = "{\"message\":\"Chào\"}";
            byte[] jsonBytes = json.getBytes(StandardCharsets.UTF_8);
            byte[] compressed = gzip(jsonBytes);
            HttpRequest zipped = HttpRequest.newBuilder(uri)
                    .header("Content-Type", "application/json")
                    .header("Content-Encoding", "gzip")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(compressed))
                    .build();
            HttpResponse<String> zippedResponse = client.send(zipped,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("JSON UTF-8 bytes=" + jsonBytes.length
                    + ", gzip bytes=" + compressed.length);
            System.out.println("gzip reply: " + zippedResponse.body());
        } finally {
            server.stop(0);
        }
    }
}
```

**Biên dịch và chạy với JDK 17** (server HTTP nằm trong module JDK `jdk.httpserver`):

```bash
javac --release 17 --add-modules jdk.httpserver HttpRepresentationDemo.java
java --add-modules jdk.httpserver HttpRepresentationDemo
```

**Stdout thực tế đã kiểm thử:**

```text
text UTF-16 units=8, UTF-8 bytes=9
text reply: type=text/plain; charset=UTF-8; lengthMatches=true; content=Xin chào
JSON UTF-8 bytes=19, gzip bytes=39
gzip reply: type=application/json; lengthMatches=true; content={"message":"Chào"}
```

### Giải thích kết quả

**Dòng 1:** Java `String.length()` đếm 8 UTF-16 code units; payload UTF-8 có 9 byte. `Content-Length` của HTTP request được tạo theo đúng bytes vì dùng byte-array publisher.

**Dòng 2:** Server đọc `Content-Type` và nhận đúng body 9 byte. Cờ `lengthMatches=true` nghĩa là trường `Content-Length` (trong request HTTP/1.1 đã thử) là số thập phân khớp `received.length`. Server giải mã bytes thành `Xin chào` bằng UTF-8.

**Dòng 3:** JSON text ban đầu mã hóa ra 19 byte UTF-8; sau `GZIPOutputStream` là 39 byte. Độ dài đã nén phụ thuộc nội dung và thuật toán/triển khai, nên bài học đúng ở đây là **lấy `compressed.length` thực tế**, không ước lượng theo số ký tự. Kết quả 39 là đầu ra của ví dụ thử trên JDK dùng trong bài.

**Dòng 4:** Server thấy `Content-Type: application/json`, giải `Content-Encoding: gzip` để có JSON text, và `Content-Length` khớp số **byte nén** đã nhận. Nếu server đem 39 byte nén vào `new String(..., UTF_8)` ngay lập tức, sẽ không được JSON hợp lệ.

**Giới hạn demo:** đây là server test, không phải production API. `readAllBytes()` và `GZIPInputStream.readAllBytes()` **không có giới hạn kích thước**; đầu vào không tin cậy có thể gây tiêu thụ nhiều bộ nhớ hoặc decompression bomb. Code cũng giả định mọi request text đều là UTF-8 và chỉ xử lý content encoding `gzip`/không encoding; production phải kiểm tra media type, charset, content coding, giới hạn bytes/trailer và error response trước khi parse. Request mẫu dùng HTTP/1.1 có content-length xác định, vì thế phép so sánh header có ý nghĩa trong thử nghiệm; **không yêu cầu mọi HTTP request hợp lệ phải có Content-Length**.

## 10. Dùng Java `HttpClient` đúng tầng dữ liệu

Một số thao tác thường gặp:

| Mục đích | Java 17 API | Lưu ý |
| --- | --- | --- |
| Gửi text UTF-8 | `BodyPublishers.ofString(text, StandardCharsets.UTF_8)` | Cần đặt `Content-Type` phù hợp; thư viện không thể biết chính sách media type ứng dụng từ chuỗi |
| Gửi bytes đã serialized/nén | `BodyPublishers.ofByteArray(bytes)` | Kích thước publisher xác định theo bytes thực |
| Gửi file | `BodyPublishers.ofFile(path)` | Media type dựa vào hợp đồng/tệp, không tự suy chắc từ tên file |
| Nhận response dưới dạng bytes | `BodyHandlers.ofByteArray()` | Giữ nguyên bytes để tự xử lý content coding/format |
| Nhận text theo charset xác định | `BodyHandlers.ofString(StandardCharsets.UTF_8)` | Dùng khi protocol/API xác định UTF-8 |
| Xem response media type | `response.headers().firstValue("Content-Type")` | Validate trước khi parse ngoài ví dụ ngắn |
| Xem HTTP status | `response.statusCode()` | Không mặc định một 200 đồng nghĩa payload hợp lệ |

Đối với response có `Content-Encoding: gzip`, nếu thư viện bạn dùng **không** tự giải nén, cần đọc bytes, giải gzip rồi parse theo media type. Không thể cho `BodyHandlers.ofString(UTF_8)` tự nhiên giải nén mọi content coding chỉ vì bạn chọn charset UTF-8.

**Thứ tự an toàn phía client:** kiểm tra status → giới hạn kích thước bytes → kiểm tra `Content-Type` → đọc đúng body bằng API có hạn mức → giải `Content-Encoding` nếu cần → giải charset → parse/validate. Với `application/json`, dùng thư viện JSON có kiểm soát thay vì xử lý JSON phức tạp bằng cắt chuỗi thủ công.

Lưu ý: đối với nguồn dữ liệu **không tin cậy**, header tự khai `Content-Length` có thể thiếu/sai. Không cho phép header đó quyết định vô điều kiện lượng bộ nhớ cấp phát; áp dụng trần theo application contract và kiểm tra bytes nhận.

## 11. Multipart và form encoding: body không chỉ có text thuần

Hai form phổ biến cũng dùng `Content-Type` nhưng cách tính bytes khác:

### 11.1. `application/x-www-form-urlencoded`

Nội dung có cấu trúc key/value được percent-encode. Ví dụ khoảng trắng có thể trở thành `+`, ký tự phi ASCII thường được biểu diễn bằng các percent-encoded UTF-8 bytes theo charset form. Vì vậy số byte HTTP body **không bằng** số ký tự trong giá trị input ban đầu.

Cần mã hóa từng giá trị bằng API phù hợp, ví dụ `URLEncoder.encode(value, StandardCharsets.UTF_8)` khi dùng đúng quy tắc form encoding; không lấy chuỗi raw thay cho body đã mã hóa để tính `Content-Length`.

### 11.2. `multipart/form-data`

Body gồm nhiều part, mỗi part có header riêng và ranh giới (boundary). Ví dụ:

```http
Content-Type: multipart/form-data; boundary=BOUNDARY

--BOUNDARY
Content-Disposition: form-data; name="note"

Xin chào
--BOUNDARY--
```

Đây là minh họa dễ đọc; trên wire cần CRLF đúng, thường còn có Content-Type per-part và các bytes file nhị phân. **`Content-Length`, nếu có, phải tính toàn bộ multipart body bytes**, bao gồm marker boundary, CRLF, part headers, payload mỗi part và dấu kết thúc; không chỉ bytes của file hoặc một field text.

Nếu dùng thư viện multipart client, hãy để thư viện tạo boundary, header và body. Tự ghép chuỗi rồi ước lượng bằng `String.length()` rất dễ sai khi có UTF-8 hoặc file nhị phân.

## 12. Server nhận dữ liệu và bảo vệ tài nguyên

Không chỉ kiểm tra Content-Length cho đúng; một server cần đặt **giới hạn tin cậy** cho body:

1. Chỉ hỗ trợ những media type endpoint định nghĩa. Ví dụ API JSON yêu cầu `application/json`, từ chối `text/plain` nếu không có quy tắc parse tương ứng.
2. Chọn charset theo media type. JSON dùng UTF-8; `text/plain` có thể cần đọc tham số charset và chỉ hỗ trợ tập charset được cho phép.
3. Áp giới hạn **encoded bytes** trước khi đọc hoặc lưu body. Khi Content-Length quá lớn, có thể reject sớm; khi header không có, vẫn phải giới hạn số bytes stream thực đọc.
4. Nếu `Content-Encoding: gzip`, áp thêm giới hạn **decoded bytes**, tỷ lệ giải nén và thời gian CPU để phòng decompression bomb.
5. Phân biệt lỗi HTTP framing (được HTTP server stack xử lý) với lỗi parse representation (ứng dụng trả 400/415/422 tùy contract).
6. Kiểm soát charset decoder và parser. Kiểm tra JSON syntax/schema, độ sâu lồng nhau, kích thước string/array, không chỉ Content-Type.
7. Tránh tin `Content-Length` như một chứng cứ integrity; nó chỉ cung cấp byte count theo quy tắc framing, không phải chữ ký hay checksum.

Một hàm helper có thể đọc InputStream tối đa `maxBytes` mà không gọi `readAllBytes()` vô hạn:

```java
// Mảnh code minh họa, cần import java.io.*, byte[].
static byte[] readAtMost(InputStream in, int maxBytes) throws IOException {
    if (maxBytes < 0) throw new IllegalArgumentException();
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    byte[] chunk = new byte[8192];
    int read;
    while ((read = in.read(chunk)) != -1) {
        if (read > maxBytes - output.size()) {
            throw new IOException("HTTP content exceeds limit");
        }
        output.write(chunk, 0, read);
    }
    return output.toByteArray();
}
```

Đây là fragment riêng, không phải tệp runnable đầy đủ. Nó minh họa giới hạn số bytes trước khi cấp phát vô hạn; **không tự giải `Content-Encoding`** và cũng không thay thế HTTP framing của server. Trong request processing thực tế cần xử lý timeout, abort/close, cách trả status code và giải phóng connection theo framework.

## 13. `Content-Length` sai và rủi ro HTTP request smuggling

HTTP/1.1 dùng ranh giới message để phân biệt request trên kết nối keep-alive. Nếu reverse proxy và backend **không thống nhất độ dài**, một chuỗi byte có thể bị hiểu thành hai cách phân chia request khác nhau; đây là gốc của một số kiểu **request smuggling**.

Những đầu vào cần xử lý nghiêm ngặt:

- `Content-Length` chứa ký tự không phải số hoặc giá trị âm.
- Giá trị quá lớn gây overflow khi parse sang `int`/`long`.
- Nhiều Content-Length mâu thuẫn; phải tuân theo quy tắc RFC và chính sách của HTTP stack, không tự tùy tiện chọn bản đầu/cuối.
- Message có cả `Transfer-Encoding` và `Content-Length`. RFC 9112 đặt `Transfer-Encoding` lên trên khi nhận, nhưng đây là tình huống đáng nghi; sender **không được gửi cả hai** và intermediary phải xử lý theo tiêu chuẩn để tránh parser disagreement.
- Header content-length được biết là không đúng nhưng vẫn được forward tới downstream.

**Đừng tự viết HTTP/1.1 parser bằng `readLine()` và `parseInt(Content-Length)` cho traffic không tin cậy** nếu có sẵn stack được kiểm thử. Chọn version/server/proxy framework được cập nhật, giới hạn kích thước header/body và nhất quán về cách xử lý framing tại mọi hop.

Ngay cả khi Content-Length đúng, dữ liệu bên trong vẫn có thể sai JSON, sai schema, sai charset hoặc chứa mã độc; **độ dài hợp lệ không tương đương dữ liệu hợp lệ**.

## 14. Khác biệt giữa Content-Length, transfer progress và integrity

Người học đôi khi dùng Content-Length để quyết định:

- **Progress bar:** khi body size được biết, byte count giúp ước tính tiến độ. Với streaming/chunked, tổng kích thước có thể không biết trước.
- **Memory allocation:** không cấp phát thẳng mảng theo untrusted Content-Length. Luôn có upper bound ứng dụng.
- **Download integrity:** file có đúng số byte chỉ là kiểm tra độ dài. Muốn xác nhận toàn vẹn/nội dung/nguồn, dùng transport security (TLS), digest/signature/checksum theo threat model và metadata tin cậy.
- **Compression:** tỉ lệ nén lớn nghĩa encoded bytes nhỏ nhưng decoded bytes có thể rất lớn. Content-Length chỉ phản ánh bytes encoded được gửi, không tự tiết lộ decoded size.
- **Response caching:** Content-Type/Content-Encoding và Vary/negotiation ảnh hưởng việc diễn giải representation. Cache không được trộn lẫn các biến thể gzip/plain hay media type khác nhau theo cách làm sai ứng dụng.

Tóm lại: Content-Length trả lời câu hỏi **bao nhiêu octet** theo quy tắc HTTP; Content-Type trả lời **đây là loại biểu diễn nào**; charset trả lời **các byte văn bản được giải mã thế nào**; Content-Encoding trả lời **bytes đã qua phép biến đổi nào**. Chúng bổ sung cho nhau, không thể thay thế nhau.

## 15. Một số tình huống chẩn đoán thực tế

| Dấu hiệu | Nguyên nhân cần kiểm tra | Bước xử lý |
| --- | --- | --- |
| Tiếng Việt bị `Ã `/mojibake | Sender và receiver không thống nhất charset | Kiểm tra bytes gốc, Content-Type charset, decoder UTF-8 |
| Server đọc body thiếu byte cuối | Lấy `String.length()` làm Content-Length | Mã hóa bytes trước và dùng byte count |
| Server thấy JSON thành ký tự lạ | Đang parse bytes gzip như UTF-8 | Kiểm tra `Content-Encoding`, giải nén trước |
| HTTP 415 Unsupported Media Type | Media type request khác loại API nhận | Đặt đúng Content-Type theo contract |
| HTTP 406 Not Acceptable | Server không trả được variant theo Accept | Kiểm tra Accept và khả năng content negotiation |
| Client treo khi đọc body | Framing sai, stream không kết thúc, timeout | Dùng HTTP library, deadline và đo số bytes thực |
| Response không có Content-Length | Có thể là streaming/chunked/HTTP2; không nhất thiết lỗi | Để HTTP stack xử lý framing, đặt streaming limit |
| JSON UTF-8 đúng nhưng header có `charset` lạ | Media type JSON không định nghĩa charset parameter | Tuân thủ JSON UTF-8 và API contract |
| Content-Length đúng mà file bị hỏng | Byte count không xác nhận integrity | Kiểm tra media format, digest/signature |
| Response HEAD có Content-Length nhưng không body | Header có thể chỉ kích thước GET tương ứng | Không cố đọc body theo header trong HEAD |
| Proxy/backend bất đồng Content-Length / Transfer-Encoding | Nguy cơ desynchronization/request smuggling | Harden server/proxy và reject framing sai |
| Body binary bị biến thành String rồi gửi lại | Dữ liệu có thể bị sửa hoặc mất byte | Truyền `byte[]`/InputStream trực tiếp |

## 16. Bài tập vận dụng

**Bài 1 — UTF-8.** Đoạn Java `String s = "Xin chào";`. Vì sao `s.length()==8` nhưng request chứa UTF-8 có Content-Length 9? Tính bytes bằng API nào?

**Bài 2 — Gzip.** JSON trước nén dài 19 byte và sau nén dài 39 byte. HTTP request gửi 39 byte nén có `Content-Type: application/json` và `Content-Encoding: gzip`. `Content-Length` trong HTTP/1.1 nên là bao nhiêu? Receiver phải làm gì trước khi parse JSON?

**Bài 3 — Media type.** Client gửi JSON nhưng đặt `Content-Type: text/plain`, còn `Accept: application/json`. Hai header đang mô tả hai hướng nào? Server có thể phản hồi 415 khi nào?

**Bài 4 — HTTP/1.1 framing.** Nếu request có đồng thời `Content-Length: 8` và `Transfer-Encoding: chunked`, cần làm gì? Sender có được chủ động phát cả hai không?

**Bài 5 — HEAD.** Server phản hồi HEAD với `Content-Length: 3200`. Có được đọc 3200 byte body trong response HEAD không? Con số 3200 được phép đại diện điều gì?

**Bài 6 — Multipart.** Một file upload chứa 1000 byte, body multipart còn có boundary/part headers/CRLF. Content-Length có bằng 1000 không? Nếu dùng library tạo multipart, nên tự tính hay để library quản lý?

**Bài 7 — Charset.** Client nhận `application/octet-stream` chứa PNG. Có nên gọi `new String(bodyBytes, UTF_8)` trước khi lưu không? Vì sao?

**Bài 8 — Streaming.** Server phát nội dung dần mà không biết tổng số byte trước khi gửi headers. HTTP/1.1 có thể dùng cách nào thay Content-Length? HTTP/2 có dùng đúng `Transfer-Encoding: chunked` không?

**Đáp án gợi ý:**

1. `String.length()` đếm UTF-16 code units; `à` cần hai UTF-8 bytes. Dùng `s.getBytes(StandardCharsets.UTF_8).length`.
2. `Content-Length: 39` vì HTTP content đã gzip. Receiver phải đọc body, giải gzip để có 19 byte UTF-8 rồi parse JSON.
3. `Content-Type` mô tả request body hiện tại; `Accept` mô tả response muốn nhận. Server có thể trả `415` nếu không chấp nhận request media type.
4. Sender không được gửi cả hai theo RFC 9112. Receiver/proxy phải xử lý framing theo chuẩn và chính sách an toàn, không chọn tùy tiện một giá trị.
5. Không có body đối với response HEAD; nếu trường được gửi, giá trị phải phù hợp số byte sẽ được gửi bởi response GET tương ứng.
6. Không: Content-Length nếu có phải gồm toàn bộ bytes multipart body. Để thư viện HTTP/multipart quản lý framing.
7. Không. PNG là binary; String decoding có thể đổi/làm mất bytes. Giữ raw bytes và đưa cho decoder PNG.
8. HTTP/1.1 thường dùng chunked transfer coding khi phù hợp; HTTP/2 dùng DATA frames riêng, không dùng HTTP/1.1 chunked.

## Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html), đặc biệt các mục `Content-Type`, `Content-Encoding` và `Content-Length`.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html), message framing, `Transfer-Encoding: chunked` và quy tắc tránh framing ambiguity.
- [RFC 8259 — JSON Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259.html), JSON UTF-8 và media type `application/json`.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html), lựa chọn HTTP version và xử lý request.
- [Java SE 17 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html), gửi string/byte array/file/stream.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html), nhận bytes hoặc string theo charset.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html), server HTTP cục bộ dùng trong ví dụ.
- [Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html), request/response headers, body stream và `sendResponseHeaders`.
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html), mã hóa UTF-8 minh bạch giữa các máy.
