# Kiểm tra dữ liệu tiếng Việt qua HTTP bằng `Content-Type`, charset và nội dung byte

## 1. Vì sao phải kiểm tra cả header lẫn byte?

HTTP vận chuyển nội dung dưới dạng byte. Khi gửi hoặc nhận văn bản tiếng Việt, cần xác minh ba điều độc lập: media type của body, charset dùng để chuyển byte thành ký tự, và byte thực tế có hợp lệ theo charset được công bố hay không.

`Content-Type` mô tả representation trong body và các tham số của media type. Đây là metadata; nó không chuyển đổi byte. Nếu server gửi byte Windows-1258 nhưng khai báo `charset=UTF-8`, client tin header sẽ giải mã sai.

**Nguyên tắc kiểm chứng:** đọc header, giữ byte gốc, chọn charset theo hợp đồng media type, giải mã nghiêm ngặt khi cần toàn vẹn, rồi so sánh nội dung. Không chỉ nhìn chữ trong browser hoặc log rồi kết luận encoding đúng.

Bài thuộc chương **Kiểm chứng mã hóa** của mô-đun `JAVA_VERSION_JAVA18`. Nội dung dùng Java HTTP Client hiện đại và tập trung vào `Content-Type`, UTF-8 cùng kiểm tra byte thực tế.

## 2. Phân biệt các header HTTP

### 2.1. `Content-Type` mô tả representation hiện tại

Ví dụ:

```http
Content-Type: text/plain; charset=UTF-8
```

`text/plain` là media type; `charset=UTF-8` là parameter mô tả cách mã hóa văn bản thành byte. Header request mô tả body client gửi; header response mô tả body server trả về.

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Type/subtype | `text/plain` | Văn bản thuần |
| Type/subtype | `application/json` | Nội dung JSON |
| Parameter | `charset=UTF-8` | Charset khi media type định nghĩa parameter này |
| Parameter | `boundary=...` | Ranh giới các phần multipart |

Tên type, subtype, parameter name và charset không phân biệt chữ hoa/chữ thường. `UTF-8` và `utf-8` là cùng charset trong Java.

### 2.2. `Accept` không thay thế `Content-Type`

`Accept` cho biết client muốn nhận loại representation nào. `Content-Type` mô tả loại body thực sự được gửi.

```http
GET /greeting HTTP/1.1
Accept: text/plain
```

Client yêu cầu response dạng `text/plain`. Server vẫn cần mô tả response thực tế bằng `Content-Type`. Không dùng `Accept` để suy ra charset response nếu hợp đồng API không quy định.

### 2.3. `Content-Encoding` không phải charset

`Content-Encoding` mô tả content coding, thường dùng để nén như gzip. Nó không nói cách chuyển byte thành ký tự.

```http
Content-Type: text/plain; charset=UTF-8
Content-Encoding: gzip
```

Thứ tự xử lý là giải nén content coding trước, sau đó giải mã byte representation theo charset. Không giải mã UTF-8 trực tiếp trên byte gzip còn nén.

## 3. Chọn charset theo media type

Không phải media type nào cũng định nghĩa parameter `charset`. Hãy theo đặc tả định dạng, không tự áp dụng một quy tắc cho mọi response.

### 3.1. `text/plain`

Với văn bản thuần, nên công bố charset tường minh nếu API cho phép:

```http
Content-Type: text/plain; charset=UTF-8
```

Client có thể dùng parameter để giải mã body. Nếu header thiếu charset, đừng tự suy ra UTF-8 chỉ vì server chạy JDK 18+. Default charset của JVM server không phải metadata được truyền qua HTTP. Hai bên cần hợp đồng rõ về charset mặc định hoặc server cần khai báo charset.

### 3.2. `application/json`

JSON trao đổi giữa các hệ thống ngoài một closed ecosystem phải dùng UTF-8 theo RFC 8259. Đặc tả JSON không định nghĩa parameter `charset` cho `application/json`; nếu header có `charset=UTF-8` thì parameter đó không làm thay đổi quy tắc giải mã JSON.

Ví dụ response:

```http
Content-Type: application/json
```

Client không nên yêu cầu phải có `charset=UTF-8` mới chấp nhận JSON. RFC 8259 cũng quy định generator không được thêm BOM vào đầu JSON text truyền qua mạng. Parser có thể được phép bỏ qua BOM nếu nhận được, nhưng ứng dụng không nên dựa vào điều đó.

### 3.3. Media type khác

- `text/html`: tuân theo quy tắc charset của HTML và metadata tài liệu.
- `application/xml` hoặc `text/xml`: tuân theo quy tắc encoding của XML và media type cụ thể.
- `application/octet-stream`: dữ liệu nhị phân; không tự giải mã thành văn bản nếu chưa có hợp đồng.
- `multipart/form-data`: mỗi phần có header và quy tắc riêng; không giả định toàn bộ body dùng một charset.

## 4. Gửi tiếng Việt bằng Java HTTP Client

Java HTTP Client thuộc module `java.net.http` từ Java 11 và vẫn được hỗ trợ trên JDK hiện đại. Hãy mã hóa body rõ ràng và đặt `Content-Type` tương ứng.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

String json = """
        {"message":"Xin chào Việt Nam 🙂"}
        """;

byte[] requestBytes = json.getBytes(StandardCharsets.UTF_8);

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.test/messages"))
        .header("Content-Type", "application/json")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofByteArray(requestBytes))
        .build();

HttpClient client = HttpClient.newHttpClient();

HttpResponse<byte[]> response = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());

System.out.println("HTTP status = " + response.statusCode());
System.out.println("Response bytes = " + response.body().length);
```

Trong ví dụ:

- `getBytes(StandardCharsets.UTF_8)` tạo byte UTF-8.
- `Content-Type: application/json` mô tả request body.
- `Accept: application/json` cho biết loại response mong muốn.
- `BodyPublishers.ofByteArray` gửi chính mảng byte đã tạo.
- `BodyHandlers.ofByteArray` giữ byte response để ứng dụng tự kiểm chứng.

`HttpRequest.BodyPublishers.ofString(json)` cũng mã hóa body bằng UTF-8 theo hợp đồng API, nhưng vẫn cần tự đặt `Content-Type`; body publisher không tự suy ra media type.

### 4.1. Không dùng số ký tự làm Content-Length

HTTP đếm octet (byte), không đếm ký tự Java. Tiếng Việt có dấu và emoji có thể dùng nhiều byte UTF-8.

```java
String text = "Xin chào 🙂";

int utf16Units = text.length();
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;

System.out.println("String.length = " + utf16Units);
System.out.println("UTF-8 bytes = " + utf8Bytes);
```

Không tự đặt `Content-Length` bằng `text.length()`. `BodyPublishers.ofByteArray` biết độ dài mảng byte. Nếu cần ghi log độ dài payload, dùng `requestBytes.length`.

## 5. Nhận response: giữ byte trước khi giải mã

### 5.1. Vì sao `BodyHandlers.ofByteArray()` hữu ích?

`HttpResponse.BodyHandlers.ofByteArray()` giữ body dưới dạng `byte[]`. Cách này phù hợp khi cần kiểm tra header, byte malformed, charset legacy hoặc lưu payload gốc.

`BodyHandlers.ofString()` tạo `String` bằng UTF-8 theo hợp đồng Java HTTP Client. Nó không tự đọc `Content-Type` rồi chọn charset parameter tùy ý. Nếu server trả `text/plain; charset=windows-1258`, `ofString()` không tự giải mã theo Windows-1258. Khi cần tuân thủ charset header, nhận byte trước rồi tự giải mã.

### 5.2. Đọc header và byte body

```java
import java.util.HexFormat;

String contentType = response.headers()
        .firstValue("Content-Type")
        .orElse("");

byte[] body = response.body();

System.out.println("Content-Type = " + contentType);
System.out.println("Body length = " + body.length);
System.out.println("First bytes = " + HexFormat.of()
        .withUpperCase()
        .formatHex(body, 0, Math.min(body.length, 32)));
```

Đây là header của response. Không lấy header request do client tự đặt để kết luận server đã trả đúng media type.

### 5.3. Kiểm tra media type trước khi decode

Client nên kiểm tra status code và media type trước khi giải mã. Nếu API dự kiến JSON nhưng server trả HTML trang lỗi hoặc `text/plain`, không nên cố parse body như JSON.

Java SE không cung cấp parser tổng quát cho mọi cú pháp media type. Trong production, dùng parser MIME/media type từ thư viện HTTP hoặc framework của dự án. Không dùng phép kiểm tra chuỗi đơn giản như `contains("json")` vì có thể chấp nhận nhầm media type.

## 6. Giải mã `text/plain` theo charset được công bố

Ví dụ minh họa response `text/plain; charset=UTF-8`. Hàm parse dưới đây chỉ dành cho header đơn giản; nó không xử lý mọi dạng quoted parameter phức tạp. Ứng dụng production nên dùng parser media type chuẩn.

```java
import java.nio.ByteBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;

static Charset parseSimpleTextCharset(String contentType) {
    String[] parts = contentType.split(";");

    if (!parts[0].trim().equalsIgnoreCase("text/plain")) {
        throw new IllegalArgumentException(
                "Expected text/plain, got: " + parts[0]);
    }

    for (int i = 1; i < parts.length; i++) {
        String part = parts[i].trim();
        int equals = part.indexOf('=');

        if (equals > 0
                && part.substring(0, equals).trim()
                        .equalsIgnoreCase("charset")) {
            String name = part.substring(equals + 1).trim();

            if (name.startsWith("\"") && name.endsWith("\"")
                    && name.length() >= 2) {
                name = name.substring(1, name.length() - 1);
            }

            return Charset.forName(name);
        }
    }

    throw new IllegalArgumentException(
            "text/plain response must declare charset by API contract");
}

static String decodeStrict(byte[] bytes, Charset charset)
        throws java.nio.charset.CharacterCodingException {
    var decoder = charset.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);

    return decoder.decode(ByteBuffer.wrap(bytes)).toString();
}
```

Sử dụng:

```java
String contentType = response.headers()
        .firstValue("Content-Type")
        .orElseThrow();

Charset charset = parseSimpleTextCharset(contentType);
String text = decodeStrict(response.body(), charset);

System.out.println(text);
```

Nếu parameter không có, ví dụ từ chối response theo chính sách API để tránh đoán charset. Media type khác có thể có quy tắc encoding mặc định riêng. Nếu tên charset không hợp lệ hoặc runtime không hỗ trợ, `Charset.forName` có thể ném `IllegalCharsetNameException` hoặc `UnsupportedCharsetException`. Hãy xử lý đây là lỗi metadata/hợp đồng response, không fallback âm thầm sang `Charset.defaultCharset()`.

## 7. Giải mã JSON theo hợp đồng UTF-8

Với JSON trao đổi qua HTTP giữa các hệ thống, dùng UTF-8 theo RFC 8259:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeJsonUtf8(byte[] bytes)
        throws java.nio.charset.CharacterCodingException {
    var decoder = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);

    return decoder.decode(ByteBuffer.wrap(bytes)).toString();
}
```

Trước khi parse, xác minh response có media type JSON mà API chấp nhận, ví dụ `application/json` hoặc vendor media type hậu tố `+json` nếu hợp đồng hỗ trợ. Sau đó giải mã UTF-8 nghiêm ngặt và chuyển chuỗi cho JSON parser.

Không dùng `Content-Type: application/json; charset=windows-1258` để thay đổi quy tắc JSON trên mạng. RFC 8259 yêu cầu JSON trao đổi giữa các hệ thống dùng UTF-8 và không định nghĩa charset parameter cho `application/json`.

## 8. Kiểm tra byte UTF-8 mong đợi

Hãy chọn chuỗi có dấu tiếng Việt và ký tự ngoài BMP để test nhiều dạng code point.

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String expected = "Xin chào Việt Nam 🙂";
byte[] expectedBytes = expected.getBytes(StandardCharsets.UTF_8);

System.out.println(HexFormat.of()
        .withUpperCase()
        .formatHex(expectedBytes));
```

Nếu endpoint phải trả đúng representation byte này:

```java
byte[] actualBytes = response.body();

if (!java.util.Arrays.equals(expectedBytes, actualBytes)) {
    throw new AssertionError(
            "HTTP payload bytes không khớp UTF-8 mong đợi");
}
```

So sánh byte chỉ phù hợp khi endpoint được kỳ vọng trả đúng representation byte giống hệt, không có newline, JSON formatting hoặc biến đổi hợp lệ khác. Với JSON, nếu server có thể thay đổi whitespace hoặc thứ tự property, hãy parse JSON rồi so sánh cấu trúc và giá trị thay vì so sánh toàn bộ byte.

### 8.1. Kiểm tra riêng một ký tự

Ký tự `à` trong UTF-8 có byte `C3 A0`:

```java
byte[] bytes = "à".getBytes(StandardCharsets.UTF_8);

String hex = HexFormat.of()
        .withUpperCase()
        .formatHex(bytes);

if (!"C3A0".equals(hex)) {
    throw new AssertionError("Unexpected UTF-8 bytes: " + hex);
}
```

Nếu server gửi byte `E0` nhưng header công bố UTF-8, decoder UTF-8 nghiêm ngặt sẽ báo malformed input. Đừng đổi charset theo phỏng đoán; cần xác minh producer và hợp đồng dữ liệu.

## 9. Ví dụ server: header phải khớp byte được ghi

Với JDK có module `jdk.httpserver`, `com.sun.net.httpserver.HttpServer` có thể tạo endpoint thử nghiệm nhỏ. Đây là API của module JDK, không phải framework HTTP đầy đủ.

```java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8080), 0);

server.createContext("/vietnamese", exchange -> {
    byte[] body = "Xin chào Việt Nam 🙂"
            .getBytes(StandardCharsets.UTF_8);

    exchange.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=UTF-8");

    exchange.sendResponseHeaders(200, body.length);

    try (var output = exchange.getResponseBody()) {
        output.write(body);
    }
});

server.start();
```

Điểm cần chú ý:

- Body được mã hóa UTF-8 trước khi gửi.
- `Content-Type` khai báo đúng UTF-8.
- Độ dài response dùng `body.length`, tức byte count, không phải `String.length()`.
- Server ghi đúng mảng byte đã dùng để tính độ dài.

Ví dụ chỉ phục vụ kiểm thử phát triển. Production cần quản lý vòng đời server, executor, port, timeout, xác thực, TLS và giới hạn request.

## 10. Dùng `curl` và công cụ hex để kiểm tra endpoint

### 10.1. Xem response headers

```bash
curl -i https://example.test/greeting
```

`-i` hiển thị response headers cùng body. Kiểm tra status code, `Content-Type` và các header liên quan. Header đúng chưa chứng minh byte đúng; cần kiểm tra body.

### 10.2. Lưu body để kiểm tra byte

Linux/macOS:

```bash
curl -sS https://example.test/greeting -o response.bin
xxd -g 1 response.bin
```

Windows PowerShell:

```powershell
curl.exe -sS https://example.test/greeting -o response.bin
Format-Hex .\response.bin
```

Dùng `curl.exe` trên Windows để gọi chương trình curl thực tế, tránh nhầm alias PowerShell ở các phiên bản cũ. Tùy chọn `-o` lưu body vào file để kiểm tra byte độc lập với cách terminal hiển thị.

### 10.3. Gửi request với media type rõ ràng

Ví dụ Windows Command Prompt:

```cmd
curl -i https://example.test/messages ^
  -H "Content-Type: application/json" ^
  -H "Accept: application/json" ^
  --data-binary "@request.json"
```

Dấu `^` là ký tự nối dòng của Windows Command Prompt. Trên PowerShell hoặc Linux/macOS, dùng cú pháp nối dòng của shell hoặc viết lệnh trên một dòng. `--data-binary` gửi byte file mà không áp dụng chuyển đổi newline của chế độ text form thông thường. File `request.json` phải được tạo bằng UTF-8 theo hợp đồng JSON.

## 11. Các lỗi thường gặp khi xác minh HTTP tiếng Việt

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Header nói UTF-8 nhưng tiếng Việt lỗi | Body byte không phải UTF-8 hoặc byte malformed | Lưu body, xem hex, decode UTF-8 `REPORT` |
| `BodyHandlers.ofString()` đọc sai response legacy | Handler dùng UTF-8, không tự chọn charset từ header | Dùng `ofByteArray()` rồi decode theo charset được công bố |
| JSON bị từ chối vì thiếu `charset=UTF-8` | Client yêu cầu parameter không được JSON định nghĩa | Tuân RFC 8259: JSON network UTF-8, `application/json` không cần charset |
| Server gửi UTF-8 nhưng khai báo charset khác | Header không khớp representation | Sửa producer hoặc header theo byte thực tế |
| `Content-Length` không khớp | Dùng số ký tự thay số byte | Dùng byte array và `body.length` |
| Chữ chỉ sai trong browser | Browser decode theo metadata hoặc quy tắc media type khác kỳ vọng | Kiểm tra header và byte bằng curl/hex |
| Response là HTML lỗi nhưng client parse JSON | Không kiểm tra status/media type | Kiểm tra status và `Content-Type` |
| Body gzip bị decode trực tiếp thành UTF-8 | Chưa xử lý `Content-Encoding` | Giải nén trước khi decode charset |
| Có `U+FFFD` trong nội dung | Byte đã bị decoder thay thế hoặc dữ liệu thực có replacement character | Giữ byte gốc và dùng decoder `REPORT` |

## 12. Checklist kiểm chứng endpoint

Khi xác minh endpoint tiếng Việt, thực hiện lần lượt:

1. Ghi lại HTTP status code và URL.
2. Đọc `Content-Type` của đúng response.
3. Xác nhận type/subtype phù hợp với API mong đợi.
4. Xác định charset theo parameter hoặc quy tắc media type.
5. Kiểm tra `Content-Encoding`; giải nén trước khi decode nếu cần.
6. Nhận body dạng `byte[]` để giữ byte gốc.
7. Kiểm tra byte bằng hex với chuỗi mẫu đã biết.
8. Dùng decoder `REPORT` nếu cần từ chối byte không hợp lệ.
9. Parse JSON/XML/HTML bằng parser tương ứng.
10. So sánh giá trị sau parse, không chỉ dựa vào cách browser/console hiển thị.
11. Kiểm tra request body và response body riêng biệt.
12. Ghi lại header và byte mẫu trong regression test.

### Các nguyên tắc không được nhầm

- `Content-Type` mô tả representation; nó không chuyển đổi body.
- `Accept` mô tả response client muốn nhận; nó không khai báo charset của request body.
- `Content-Encoding` mô tả content coding; nó không phải charset.
- `Content-Length` tính byte, không tính ký tự.
- JDK 18+ default UTF-8 không tự ép mọi HTTP body thành UTF-8.
- `application/json` dùng UTF-8 trên mạng theo RFC 8259; không cần charset parameter.
- `BodyHandlers.ofString()` dùng UTF-8 theo API; muốn tuân charset khác, nhận byte trước.
- Decoder `REPORT` xác nhận byte hợp lệ theo charset đã chọn; nó không tự phát hiện charset nguồn.

## 13. Bài tập tự kiểm tra

**Bài 1.** Server trả `Content-Type: text/plain; charset=UTF-8` nhưng body chứa byte `E0` đứng riêng. Cần làm gì?

*Đáp án:* Giữ byte gốc và giải mã UTF-8 với `CodingErrorAction.REPORT`. Byte `E0` đứng riêng không phải UTF-8 hợp lệ; cần điều tra producer hoặc header, không đổi charset theo phỏng đoán.

**Bài 2.** Vì sao `Accept: application/json` không thay thế `Content-Type: application/json` trong request POST?

*Đáp án:* `Accept` mô tả loại response client muốn nhận; `Content-Type` mô tả loại body request đang gửi.

**Bài 3.** Response `application/json` không có `charset=UTF-8`. Client có thể giải mã JSON bằng UTF-8 không?

*Đáp án:* Có. RFC 8259 quy định JSON trao đổi giữa các hệ thống phải dùng UTF-8 và không định nghĩa charset parameter cho `application/json`.

**Bài 4.** `BodyHandlers.ofString()` có tự đọc `charset=windows-1258` trong response header không?

*Đáp án:* Không. Handler tạo String bằng UTF-8 theo hợp đồng Java HTTP Client. Muốn xử lý charset khác, dùng `ofByteArray()` rồi decode theo media type/hợp đồng.

**Bài 5.** Vì sao `Content-Length` không được tính bằng `String.length()`?

*Đáp án:* HTTP đếm octet. Một ký tự tiếng Việt hoặc emoji có thể được mã hóa thành nhiều byte; phải tính độ dài mảng byte sau khi encode.

**Bài 6.** Nếu có `Content-Encoding: gzip` và `Content-Type: text/plain; charset=UTF-8`, thứ tự xử lý là gì?

*Đáp án:* Giải nén gzip trước, sau đó giải mã byte representation thành ký tự bằng UTF-8.

## 14. Ghi nhớ

Muốn xác minh dữ liệu tiếng Việt qua HTTP, hãy đối chiếu `Content-Type`, quy tắc charset của media type và byte thực tế. Với `text/plain`, công bố charset tường minh theo hợp đồng API. Với JSON trao đổi qua mạng, dùng UTF-8 theo RFC 8259; `application/json` không cần charset parameter. Phân biệt `Content-Encoding` với charset và tính độ dài theo byte.

Trong Java HTTP Client, gửi byte đã mã hóa bằng charset rõ ràng và đặt header phù hợp. Khi nhận response cần kiểm tra encoding, dùng `BodyHandlers.ofByteArray()` để giữ byte, đọc header, giải mã theo hợp đồng và dùng decoder `REPORT` khi cần toàn vẹn. Chỉ khi header, byte và nội dung sau giải mã nhất quán mới có thể kết luận đường đi HTTP của văn bản tiếng Việt đang đúng.

### Tài liệu tham khảo chính thức

- [RFC 9110 — HTTP Semantics: Content-Type, Accept and Content-Encoding](https://www.rfc-editor.org/rfc/rfc9110).
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259).
- [RFC 3629 — UTF-8, a transformation format of ISO 10646](https://www.rfc-editor.org/rfc/rfc3629).
- [Oracle Java SE 24 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/24/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html).
- [Oracle Java SE 24 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/24/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html).
- [Oracle Java SE 24 — HttpHeaders](https://docs.oracle.com/en/java/javase/24/docs/api/java.net.http/java/net/http/HttpHeaders.html).
- [Oracle Java SE 24 — CharsetDecoder](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
