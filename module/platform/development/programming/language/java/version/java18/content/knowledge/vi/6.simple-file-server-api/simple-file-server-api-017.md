# Dùng `HttpClient` kiểm tra header, status và byte phản hồi mà không phụ thuộc trình duyệt

## 1. Vì sao kiểm chứng HTTP bằng Java thay vì chỉ mở trình duyệt?

Khi dùng **Simple Web Server** từ JDK 18 để chia sẻ file HTML, CSS, văn bản hoặc dữ liệu mẫu, mở URL trong trình duyệt là cách quan sát nhanh. Tuy nhiên, trình duyệt thường tự hiển thị HTML, tải ảnh, diễn giải charset, xử lý chuyển hướng và che bớt các chi tiết của phản hồi. Một trang hiện ra đúng **không chứng minh** server đã gửi đúng byte, status hoặc header mà ứng dụng khác cần.

Với `java.net.http.HttpClient`, chương trình kiểm thử có thể kiểm tra riêng:

- **Status:** server thực sự trả mã nào, ví dụ `200`, `404`, `405` hoặc `501`?
- **Header:** `Content-Type`, `Content-Length`, `Location` hoặc header khác có đúng hợp đồng không?
- **Body byte:** mảng `byte[]` có khớp file gốc hoặc chuỗi byte mong đợi không?
- **Phương thức:** `GET` trả nội dung, còn `HEAD` trả thông tin phản hồi mà không có response body?
- **Tình huống lỗi:** tài nguyên không tồn tại hoặc request method không được hỗ trợ được phản hồi ra sao?

Bài nằm trong chương **API SimpleFileServer** của mô-đun `JAVA_VERSION_JAVA18`. Simple Web Server được giới thiệu bằng **JEP 408 trong JDK 18**; API HTTP Client đã có từ Java 11 và tiếp tục được hỗ trợ trên các JDK hiện đại. Bài tập trung vào bộ kiểm tra có thể chạy lại bằng Java mà không lệ thuộc cách trình duyệt hiển thị kết quả.

## 2. Bối cảnh: Simple Web Server phục vụ nội dung gì?

`jwebserver` thuộc module `jdk.httpserver`. Nó là server HTTP/1.1 tối giản để **thử nghiệm, phát triển và gỡ lỗi**, phục vụ file tĩnh trong một cây thư mục. Nó không cung cấp một hệ thống ứng dụng web production hoàn chỉnh.

Các hành vi cốt lõi vẫn áp dụng trên JDK hiện đại:

| Request | Hành vi thông thường của Simple Web Server |
| --- | --- |
| `GET /xin-chao.txt`, file tồn tại | Trả nội dung file, thường `200 OK` |
| `HEAD /xin-chao.txt`, file tồn tại | Trả header/status tương ứng; **không có body** |
| `GET /khong-ton-tai.txt` | Trả lỗi tài nguyên không tồn tại, thường `404 Not Found` |
| `POST` tới file handler | Không hỗ trợ; `jwebserver` có thể trả `405` hoặc `501` theo trường hợp |
| `GET /subdir/` | Nếu có index file phù hợp thì phục vụ index; nếu không thì trả danh sách thư mục |
| `GET` tới file như `.html`, `.txt` | Server chọn `Content-Type` bằng bảng MIME có sẵn, dựa trên suy đoán loại file |

`SimpleFileServer.createFileHandler(rootDirectory)` trong JDK 24 hỗ trợ **GET và HEAD**; tài liệu API của file handler quy định phản hồi **405** cho phương thức khác. Tài liệu của lệnh `jwebserver` mô tả phương thức không được hỗ trợ có thể nhận **405 hoặc 501**. Vì vậy, khi kiểm tra command-line server, đừng khẳng định mọi method không hỗ trợ đều trả duy nhất một mã.

Server không phải trình duyệt: nó trả status, headers và byte theo HTTP. Client có trách nhiệm hiểu kết quả.

## 3. Chuẩn bị một file mẫu có byte kiểm chứng được

Giả sử muốn phục vụ file `public/xin-chao.txt` bằng UTF-8. Nên tạo dữ liệu thử nghiệm bằng API chỉ định charset rõ ràng, tránh dùng công cụ ghi file tự chọn encoding theo shell.

Có thể dùng `jshell` của JDK để chuẩn bị fixture trong thư mục làm việc của người học:

```java
import java.nio.file.*;
import java.nio.charset.StandardCharsets;

Files.createDirectories(Path.of("public"));

Files.writeString(
        Path.of("public", "xin-chao.txt"),
        "Xin chào Việt Nam 🌿\n",
        StandardCharsets.UTF_8);
```

Đây là các lệnh nhập trong `jshell`; sau khi tạo file, dùng `/exit` để trở về shell. `Files.writeString` với `StandardCharsets.UTF_8` ghi byte UTF-8; dữ liệu mẫu gồm chữ tiếng Việt có dấu, một emoji và ký tự LF ở cuối.

Khởi động Simple Web Server từ thư mục chứa `public`:

```shell
jwebserver -b 127.0.0.1 -p 8000 -d public
```

Server chạy ở foreground. Mở một terminal khác để chạy client kiểm thử. Đường dẫn dự kiến là:

```text
http://127.0.0.1:8000/xin-chao.txt
```

Dùng `127.0.0.1` giúp giữ bài thử trong phạm vi máy cục bộ. Chỉ phục vụ một thư mục fixture riêng, không chọn thư mục chứa khóa bí mật hoặc dữ liệu cá nhân. `jwebserver` không phải lựa chọn để triển khai public production.

### 3.1. Vì sao fixture UTF-8 vẫn cần kiểm tra?

JEP 400 làm UTF-8 trở thành default charset thông thường của các API Java SE phụ thuộc default charset từ JDK 18, nhưng điều đó **không tự chuyển đổi byte file cũ**. Khi file đã được viết bằng charset khác, HTTP file server vẫn phục vụ byte file mà nó đọc được. Dùng `Files.writeString(..., UTF_8)` trong ví dụ giúp hợp đồng fixture rõ ràng.

Không mặc định server sẽ tự thêm `charset=UTF-8` vào `Content-Type` chỉ vì file là UTF-8. Loại MIME và charset thực tế là hai vấn đề cần kiểm chứng riêng.

## 4. Bộ API `HttpClient` cần dùng

| API | Công dụng |
| --- | --- |
| `HttpClient.newBuilder()` | Tạo HTTP client với cấu hình chung |
| `HttpClient.Redirect.NEVER` | Giữ nguyên phản hồi 3xx để kiểm tra thay vì tự theo redirect |
| `HttpClient.Version.HTTP_1_1` | Yêu cầu HTTP/1.1, phù hợp `jwebserver` |
| `HttpRequest.newBuilder(uri)` | Tạo request tới URI cụ thể |
| `GET()` hoặc `method("HEAD", BodyPublishers.noBody())` | Chọn phương thức request |
| `timeout(Duration)` | Đặt giới hạn thời gian cho request |
| `client.send(request, handler)` | Gửi đồng bộ, nhận `HttpResponse` |
| `response.statusCode()` | Lấy mã trạng thái HTTP |
| `response.headers()` | Lấy `HttpHeaders` |
| `response.body()` | Lấy body theo kiểu mà `BodyHandler` quyết định |
| `BodyHandlers.ofByteArray()` | Nhận body thành `byte[]` để so sánh chính xác |

Ví dụ một request GET cơ bản:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(5))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("http://127.0.0.1:8000/xin-chao.txt"))
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();

HttpResponse<byte[]> response = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());

System.out.println("Status = " + response.statusCode());
System.out.println("HTTP version = " + response.version());
System.out.println("Body bytes = " + response.body().length);
```

`HttpClient` mặc định không tự theo redirect, nhưng đặt `Redirect.NEVER` tường minh giúp mục đích kiểm thử rõ ràng. Đặt `HTTP_1_1` cũng hữu ích vì `jwebserver` chỉ phục vụ HTTP/1.1.

Một `HttpClient` có thể được tái sử dụng cho nhiều request; không cần tạo client mới mỗi lần kiểm tra file.

## 5. Kiểm tra status trước khi diễn giải body

Mã trạng thái HTTP cho biết cách server xử lý request. Trình duyệt có thể render cả trang báo lỗi; chương trình kiểm thử nên kiểm tra status riêng.

```java
int status = response.statusCode();

if (status != 200) {
    throw new AssertionError(
            "Expected HTTP 200, got " + status);
}
```

Đừng chỉ kiểm tra `response.body().length > 0`. Trang lỗi 404 cũng có thể chứa HTML với nhiều byte. Ngược lại, một response thành công có thể có body rỗng tùy endpoint.

Một số nhóm status cần biết:

| Mã / nhóm | Ý nghĩa trong bài kiểm tra |
| --- | --- |
| `200` | Tài nguyên GET được phục vụ thành công |
| `3xx` | Redirect; kiểm tra `Location`, request URL và chính sách theo redirect |
| `404` | Tài nguyên không tồn tại |
| `405` | Method không được cho phép với tài nguyên/handler |
| `501` | Server không hỗ trợ phương thức hoặc khả năng được yêu cầu |
| `5xx` | Lỗi phía server; không coi nội dung body là file mong đợi |

`client.send(...)` thông thường trả `HttpResponse` cho cả 404 hay 500; đây không phải là `IOException` chỉ vì status khác 200. Lỗi mạng, DNS, kết nối bị từ chối hoặc timeout mới được báo qua exception tương ứng.

### 5.1. Kiểm tra status của tài nguyên thiếu

```java
HttpRequest missingRequest = HttpRequest.newBuilder()
        .uri(URI.create(
                "http://127.0.0.1:8000/khong-ton-tai-kiem-thu.txt"))
        .GET()
        .build();

HttpResponse<byte[]> missingResponse = client.send(
        missingRequest, HttpResponse.BodyHandlers.ofByteArray());

if (missingResponse.statusCode() != 404) {
    throw new AssertionError(
            "Expected 404, got " + missingResponse.statusCode());
}
```

Trước khi dùng ví dụ, bảo đảm fixture có chủ đích **không chứa** file cùng tên. Đừng kiểm tra theo giá trị status mà không kiểm soát tài nguyên thử nghiệm.

### 5.2. Phân biệt redirect với nội dung thành công

Nếu server trả `301`, `302`, `307` hoặc `308`, `HttpClient.Redirect.NEVER` giúp giữ status ban đầu. Khi đó:

```java
int status = response.statusCode();

if (status >= 300 && status < 400) {
    String location = response.headers()
            .firstValue("Location")
            .orElse("<không có Location>");
    System.out.println("Redirect to: " + location);
}
```

Khi bật `Redirect.NORMAL`, client có thể tự theo chuyển hướng; `response.uri()` có thể là URL đích cuối, và status có thể là 200 dù request ban đầu gặp redirect. Muốn xác minh server gốc trả gì, chọn `NEVER` trong bài kiểm thử.

## 6. Đọc `HttpHeaders` đúng cách

`HttpHeaders` cung cấp cái nhìn read-only về headers. Tên header HTTP không phân biệt hoa/thường khi tra cứu bằng API:

```java
String type = response.headers()
        .firstValue("Content-Type")
        .orElse("<không có>");

String lowerCaseLookup = response.headers()
        .firstValue("content-type")
        .orElse("<không có>");

System.out.println(type);
System.out.println(lowerCaseLookup);
```

Hai lời gọi tra cứu cùng tên header theo quy tắc HTTP. Những phương thức thường dùng:

- `firstValue("Content-Type")` trả `Optional<String>`, có thể rỗng nếu header không có.
- `allValues("Set-Cookie")` trả mọi giá trị cùng tên, không tự ghép hoặc tách dấu phẩy.
- `firstValueAsLong("Content-Length")` trả `OptionalLong`, có thể rỗng nếu không có header; nếu giá trị không phải số hợp lệ thì có thể ném `NumberFormatException`.
- `map()` trả view nhiều giá trị để log và gỡ lỗi; không nên dựa vào thứ tự entry trong map.

Header thiếu và header có giá trị rỗng là hai tình huống khác nhau. Khi một header là bắt buộc theo hợp đồng API, test phải thất bại rõ ràng nếu không có nó.

### 6.1. `Content-Type` của SimpleFileServer là giá trị suy đoán

`SimpleFileServer.createFileHandler(...)` chọn `Content-Type` của file dựa trên bảng MIME có sẵn. Ví dụ `.html` thường được phục vụ dưới `text/html`, còn `.txt` thường là `text/plain`.

Điều đó không chứng minh file có encoding nào. `Content-Type: text/plain` thiếu parameter `charset` không biến file thành UTF-8; ứng dụng có thể chọn UTF-8 **vì hợp đồng của fixture** đã quy định như vậy.

Khi viết test:

```java
String type = response.headers()
        .firstValue("Content-Type")
        .orElseThrow(() -> new AssertionError(
                "GET response thiếu Content-Type"));

if (!type.toLowerCase(java.util.Locale.ROOT)
        .startsWith("text/plain")) {
    throw new AssertionError("Unexpected Content-Type: " + type);
}
```

Trong ví dụ chỉ phục vụ file `.txt` do bài học kiểm soát. Với file nhị phân hoặc một media type khác, không dùng cùng assertion. Nếu hệ thống yêu cầu chính xác `charset=UTF-8`, cần cấu hình server/handler phù hợp và kiểm tra parameter đó riêng.

## 7. So sánh `Content-Length` với số byte nhận được

`Content-Length` trong HTTP là độ dài tính theo **octet (byte)**. `String.length()` đếm UTF-16 code unit, không phải số byte UTF-8.

```java
String text = "Cà phê 🌿";

int units = text.length();
int byteLength = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8).length;

System.out.println("UTF-16 units = " + units);
System.out.println("UTF-8 bytes = " + byteLength);
```

Sau một GET thành công với fixture tĩnh không áp dụng content coding, có thể kiểm tra header khi server cung cấp:

```java
byte[] bytes = response.body();

var declaredLength = response.headers()
        .firstValueAsLong("Content-Length");

if (declaredLength.isPresent()) {
    long advertised = declaredLength.getAsLong();
    if (advertised != bytes.length) {
        throw new AssertionError(
                "Content-Length=" + advertised
                + " but received " + bytes.length + " bytes");
    }
}
```

**Không mặc định `Content-Length` luôn tồn tại.** HTTP/1.1 có thể truyền body với cơ chế framing khác, ví dụ chunked transfer coding, nên header có thể vắng. Khi đó, `response.body().length` vẫn cho biết số byte mà `BodyHandler` đã thu thập.

Đừng dùng đoạn so sánh này một cách máy móc cho response có `Content-Encoding` như gzip: cần hiểu độ dài đang mô tả representation đã được mã hóa như thế nào và cách client xử lý content coding. Với fixture tĩnh chưa nén, việc so sánh byte là trực tiếp hơn.

## 8. Kiểm tra byte gốc bằng `ofByteArray()`, `Arrays.equals` và SHA-256

Đây là phần quan trọng nhất khi cần biết file server thực sự gửi đúng file.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

byte[] expected = Files.readAllBytes(
        Path.of("public", "xin-chao.txt"));

byte[] actual = response.body();

if (!Arrays.equals(expected, actual)) {
    throw new AssertionError(
            "HTTP body không khớp byte của file nguồn");
}
```

Kiểm tra byte bắt được những sai lệch mà trình duyệt có thể không bộc lộ:

- File bị cắt ngắn hoặc thêm byte.
- Dấu xuống dòng CRLF/LF bị thay đổi.
- Có hoặc thiếu BOM UTF-8.
- Charset bị chuyển đổi ngoài ý muốn.
- File không phải file đã dự kiến dù chữ hiển thị giống.
- Byte của ảnh, PDF hoặc nội dung nhị phân bị thay đổi.

Để log một bản tóm tắt byte mà không in toàn bộ file, dùng `MessageDigest` và `HexFormat`:

```java
import java.security.MessageDigest;
import java.util.HexFormat;

byte[] digest = MessageDigest.getInstance("SHA-256")
        .digest(actual);

System.out.println("SHA-256 = "
        + HexFormat.of().formatHex(digest));

System.out.println("First bytes = "
        + HexFormat.of()
                .withUpperCase()
                .formatHex(actual, 0, Math.min(actual.length, 24)));
```

Chỉ tính hash không đủ nếu không biết hash kỳ vọng; với fixture cục bộ, có thể tính hash cả file nguồn lẫn body. `Arrays.equals` giúp khẳng định toàn bộ byte bằng nhau khi có hai mảng trong bộ nhớ.

### 8.1. Kiểm chứng UTF-8 nghiêm ngặt khi fixture là văn bản

Giả sử fixture được tạo bằng UTF-8. Dùng `CharsetDecoder` để phát hiện byte không hợp lệ:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

String decoded = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(actual))
        .toString();

System.out.println(decoded);
```

`REPORT` giúp phát hiện malformed UTF-8 thay vì thay thế âm thầm bằng ký tự `U+FFFD`. Tuy nhiên, một dãy byte hợp lệ theo UTF-8 không chứng minh nguồn vốn được tạo bằng UTF-8; hợp đồng fixture/file vẫn cần xác định charset.

Với ảnh hoặc file nhị phân, không giải mã body thành `String`. Hãy so byte hoặc so hash, rồi dùng parser/decoder phù hợp loại file nếu cần.

## 9. `BodyHandlers.ofString()` dùng charset nào?

Đây là điểm dễ nhầm khi so sánh client tự động với bộ kiểm tra byte.

Theo API `HttpResponse.BodyHandlers` của **Java SE 24**:

| BodyHandler | Hành vi |
| --- | --- |
| `ofString()` | Giải mã body theo charset ghi trong `Content-Type` nếu có và được hỗ trợ; fallback UTF-8 khi thiếu header hoặc charset không được hỗ trợ |
| `ofString(StandardCharsets.UTF_8)` | Giải mã theo UTF-8 **được chỉ định**, không cần suy từ header |
| `ofByteArray()` | Giữ body thành `byte[]`, chưa chuyển byte thành `String` |
| `discarding()` | Bỏ body, phù hợp khi chỉ quan tâm status/header |
| `ofInputStream()` | Đọc body theo luồng; caller phải đóng/đọc hết stream để giải phóng tài nguyên |

Ví dụ:

```java
HttpResponse<String> textResponse = client.send(
        request, HttpResponse.BodyHandlers.ofString());

HttpResponse<String> forcedUtf8 = client.send(
        request, HttpResponse.BodyHandlers.ofString(
                java.nio.charset.StandardCharsets.UTF_8));
```

Hai cách trên có thể cho kết quả khác nếu header khai báo charset khác UTF-8. Cả hai đều đã chuyển byte thành `String`, nên không còn phù hợp để xác định byte nguyên bản có bị sai, thêm BOM hoặc bị đổi newline hay không.

**Đối với bài kiểm chứng này, ưu tiên `ofByteArray()`.** Nó tách bước nhận byte khỏi bước diễn giải charset, giúp so sánh nội dung gửi qua HTTP với file nguồn.

Đây là hợp đồng của API hiện hành, không được suy rằng `ofString()` luôn dùng UTF-8 bất kể `Content-Type`.

## 10. Kiểm chứng `HEAD` mà không tải nội dung file

`HEAD` yêu cầu server trả metadata của tài nguyên theo ngữ nghĩa tương ứng với `GET` nhưng **không gửi response body**. Đây là cách kiểm tra status và header mà không tải file lớn về.

```java
HttpRequest headRequest = HttpRequest.newBuilder()
        .uri(URI.create(
                "http://127.0.0.1:8000/xin-chao.txt"))
        .method("HEAD", HttpRequest.BodyPublishers.noBody())
        .build();

HttpResponse<byte[]> headResponse = client.send(
        headRequest, HttpResponse.BodyHandlers.ofByteArray());

System.out.println("HEAD status = " + headResponse.statusCode());
System.out.println("HEAD Content-Type = "
        + headResponse.headers()
                .firstValue("Content-Type")
                .orElse("<absent>"));
System.out.println("HEAD body bytes = "
        + headResponse.body().length);
```

Với tài nguyên có thể truy cập, kỳ vọng status thành công và `headResponse.body().length == 0`. Một số header như `Content-Length` có thể mô tả độ dài body **sẽ được gửi nếu là GET**, do đó **không yêu cầu Content-Length của HEAD bằng 0**.

Server có thể không gửi tất cả metadata của GET trong HEAD, nên test các header được hợp đồng yêu cầu thay vì khẳng định mọi header HEAD phải giống hệt GET. Muốn kiểm chứng byte thực sự của file, vẫn phải gửi GET.

## 11. Ví dụ hoàn chỉnh: kiểm thử GET và HEAD với file nguồn

Tạo file `VerifySimpleFile.java` theo ví dụ sau. Chương trình nhận hai đối số: URL file đang được phục vụ và đường dẫn đến file nguồn cục bộ. File nguồn được giả định là UTF-8 như fixture ở phần 3.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Locale;

public class VerifySimpleFile {
    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java VerifySimpleFile.java <url> <local-file>");
            System.exit(2);
        }

        URI uri = URI.create(args[0]);
        Path file = Path.of(args[1]);
        byte[] expected = Files.readAllBytes(file);

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .followRedirects(HttpClient.Redirect.NEVER)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest get = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<byte[]> response = client.send(
                get, HttpResponse.BodyHandlers.ofByteArray());

        require(response.statusCode() == 200,
                "GET status = " + response.statusCode());

        String contentType = response.headers()
                .firstValue("Content-Type")
                .orElseThrow(() -> new AssertionError(
                        "GET thiếu Content-Type"));

        require(contentType.toLowerCase(Locale.ROOT)
                        .startsWith("text/plain"),
                "Unexpected Content-Type: " + contentType);

        require(response.headers()
                        .firstValue("Content-Encoding").isEmpty(),
                "Fixture không mong đợi Content-Encoding");

        byte[] actual = response.body();
        require(Arrays.equals(expected, actual),
                "GET body khác byte file nguồn");

        var declared = response.headers()
                .firstValueAsLong("Content-Length");

        if (declared.isPresent()) {
            require(declared.getAsLong() == actual.length,
                    "GET Content-Length không khớp số byte");
        }

        String decoded = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(actual))
                .toString();

        System.out.println("GET status: " + response.statusCode());
        System.out.println("Content-Type: " + contentType);
        System.out.println("Body bytes: " + actual.length);
        System.out.println("Text: " + decoded);

        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(actual);
        System.out.println("SHA-256: "
                + HexFormat.of().formatHex(hash));

        HttpRequest head = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .method("HEAD", HttpRequest.BodyPublishers.noBody())
                .build();

        HttpResponse<byte[]> headResponse = client.send(
                head, HttpResponse.BodyHandlers.ofByteArray());

        require(headResponse.statusCode() == 200,
                "HEAD status = " + headResponse.statusCode());
        require(headResponse.body().length == 0,
                "HEAD không được có response body");

        System.out.println("HEAD status: "
                + headResponse.statusCode());
        System.out.println("PASS: headers, status and bytes verified");
    }
}
```

Chạy client trong terminal khác với terminal đang chạy `jwebserver`:

```shell
java VerifySimpleFile.java http://127.0.0.1:8000/xin-chao.txt public/xin-chao.txt
```

Chương trình sẽ thất bại rõ ràng nếu GET/HEAD không trả `200`, `Content-Type` không phù hợp file `.txt`, có content coding ngoài hợp đồng, byte response khác byte file nguồn, `Content-Length` có nhưng không khớp, hoặc byte không hợp lệ theo UTF-8.

### 11.1. Kết quả kiểm tra thành công có ý nghĩa gì?

Khi chương trình in `PASS`, nó chứng minh **trong lần request này**:

- GET và HEAD trả status mong đợi.
- Media type của fixture phù hợp.
- Body GET trùng chính xác từng byte với file được chọn làm chuẩn.
- Byte có thể giải mã UTF-8 nghiêm ngặt.
- HEAD không có body.

Đó là kiểm chứng HTTP lặp lại được, độc lập cách trình duyệt render HTML hay thay đổi font/charset hiển thị. Kết quả không thay thế các bài kiểm thử bảo mật, tải hoặc tính ổn định của server.

### 11.2. Vì sao không tự đóng `HttpClient` trong ví dụ?

Ví dụ sử dụng các API có sẵn từ Java 18 và kết thúc tiến trình sau khi kiểm thử. Trên các JDK mới hơn, `HttpClient` có API quản lý vòng đời bổ sung; trong ứng dụng chạy lâu, nên tái sử dụng client và giải phóng tài nguyên theo API của JDK đang dùng. Bản thân ví dụ không mở body streaming cần đóng, vì `ofByteArray()` đọc hết response body trước khi `send` trả về.

## 12. Kiểm thử request không hợp lệ hoặc method không được hỗ trợ

Một bộ test tốt có cả tình huống âm tính. Với `jwebserver`, file handler chỉ phục vụ GET và HEAD.

```java
HttpRequest post = HttpRequest.newBuilder()
        .uri(URI.create(
                "http://127.0.0.1:8000/xin-chao.txt"))
        .POST(HttpRequest.BodyPublishers.noBody())
        .build();

HttpResponse<byte[]> rejected = client.send(
        post, HttpResponse.BodyHandlers.ofByteArray());

int status = rejected.statusCode();

if (status != 405 && status != 501) {
    throw new AssertionError(
            "Unexpected status for unsupported method: " + status);
}
```

Tài liệu lệnh `jwebserver` cho phép cả hai mã 405/501 với các request không được hỗ trợ. Nếu kiểm thử trực tiếp `SimpleFileServer.createFileHandler(...)` theo hợp đồng API, có thể xác định riêng kết quả 405.

Đừng dùng `HttpClient` để giả định một server production bất kỳ cũng sẽ cho đúng kết quả này. Kỳ vọng status phải được lấy từ hợp đồng của hệ thống đang kiểm tra.

## 13. Khi response là file lớn hoặc nhị phân

`BodyHandlers.ofByteArray()` giữ toàn bộ response trong bộ nhớ. Đây là lựa chọn tốt cho fixture nhỏ và vừa, nhưng không phù hợp khi tải file nhiều gigabyte.

Các lựa chọn khác:

- `BodyHandlers.ofFile(path)` để ghi body ra file rồi so byte hoặc tính hash khi cần.
- `BodyHandlers.ofInputStream()` để đọc theo luồng, kết hợp `MessageDigest` và so sánh byte theo chunk.
- `BodyHandlers.discarding()` khi chỉ cần status và headers, không kiểm chứng body.
- `HEAD` khi chỉ cần metadata server sẵn sàng công bố.

Với `ofInputStream()`, phải đọc hết hoặc đóng `InputStream` để giải phóng tài nguyên HTTP. Với `ofFile(path)`, cần xác định rõ đường dẫn đích, quyền ghi và cách xử lý file chưa hoàn chỉnh nếu request lỗi.

Dữ liệu ảnh, font, ZIP hoặc PDF phải được kiểm tra như byte. Không cố gọi `ofString()` hoặc giải mã UTF-8 chỉ vì muốn in body trong terminal.

### 13.1. Hash không thay thế kiểm tra hợp đồng HTTP

SHA-256 giúp biết byte response có trùng với một bản chuẩn hay không; nhưng hai file có cùng nội dung vẫn có thể được server gửi với metadata khác nhau. Vì vậy, bộ kiểm thử cần xác minh cả **status**, **headers** và **body bytes** theo yêu cầu của tài nguyên.

## 14. Các tình huống dễ làm kiểm thử sai

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Browser mở file đúng nhưng test byte thất bại | Có BOM, newline, encoding hoặc file nguồn khác dự kiến | So sánh `Arrays.equals` và hex để tìm byte khác |
| GET trả 404 | Sai URL, sai thư mục `-d` hoặc fixture chưa được tạo | Kiểm tra địa chỉ server và đường dẫn tương đối tới root |
| `ConnectException` | Server chưa chạy hoặc sai địa chỉ/port | Kiểm tra `jwebserver` và URL `127.0.0.1:8000` |
| GET trả 200 nhưng `Content-Type` lạ | MIME được suy đoán theo phần mở rộng | Xác minh extension hoặc cấu hình handler theo hợp đồng |
| `Content-Length` không có | Response có cách framing khác hoặc server không gửi header | Chỉ kiểm tra header khi xuất hiện; dùng `body.length` để đếm byte đã nhận |
| HEAD có `Content-Length` dương | Header phản ánh kích thước body của GET tương ứng | Không yêu cầu Content-Length của HEAD bằng 0 |
| GET lỗi khi in `String` | Body không phải UTF-8 hoặc là dữ liệu nhị phân | Giữ `byte[]`, xác định charset/media type trước |
| 3xx bị tự chuyển thành 200 | Client được cấu hình theo redirect | Dùng `Redirect.NEVER` để kiểm tra phản hồi ban đầu |
| HTML lỗi bị coi là file đúng | Chỉ kiểm tra body không rỗng | Kiểm tra status và so byte với file chuẩn |
| BodyHandler nhận 404 vẫn có dữ liệu | Body handler không tự từ chối mã status | Kiểm tra `statusCode()` trước khi dùng dữ liệu |

## 15. Checklist tự động hóa một bài kiểm chứng HTTP

Trước khi đánh dấu bài kiểm thử thành công, xác minh:

1. Đã dùng đúng JDK và server đang chạy trên loopback.
2. `jwebserver` phục vụ đúng thư mục fixture.
3. URL file được encode đúng; tài nguyên có tồn tại.
4. HTTP status đúng theo từng request GET, HEAD hoặc request âm tính.
5. `Content-Type` phù hợp media type mong đợi; không suy đoán charset từ phần mở rộng.
6. `Content-Encoding` có được sử dụng hay không; xử lý nếu có.
7. `Content-Length` được hiểu là số byte và có thể không xuất hiện.
8. GET body được nhận bằng `ofByteArray()` nếu cần so byte.
9. Byte được so với nguồn chuẩn bằng `Arrays.equals` hoặc hash.
10. Với fixture văn bản, decoder sử dụng đúng charset và báo lỗi khi byte không hợp lệ.
11. HEAD không có body, nhưng metadata không nhất thiết bằng 0.
12. Redirect và các tình huống 404, 405/501 được kiểm tra rõ.
13. Kết quả có thể chạy lặp lại mà không cần mở trình duyệt.

## 16. Bài tập tự kiểm tra

**Bài 1.** Trình duyệt hiển thị đúng nội dung `xin-chao.txt`. Điều đó có chứng minh server đã gửi đúng byte UTF-8 không?

*Đáp án:* Không. Trình duyệt đã giải mã và render nội dung. Dùng `BodyHandlers.ofByteArray()`, so byte với file nguồn và dùng decoder UTF-8 nghiêm ngặt để kiểm tra.

**Bài 2.** Muốn biết một file tồn tại và xem metadata mà không tải body, nên dùng GET hay HEAD?

*Đáp án:* Dùng HEAD. HEAD trả status và header theo ngữ nghĩa của tài nguyên mà không có response body. Nếu cần xác minh byte, phải dùng GET.

**Bài 3.** HEAD trả `Content-Length: 100` và body dài 0. Có phải server sai không?

*Đáp án:* Không nhất thiết. Với HEAD, Content-Length có thể mô tả kích thước representation của GET tương ứng. Response body của HEAD vẫn không được gửi.

**Bài 4.** `BodyHandlers.ofString()` có luôn giải mã UTF-8 dù header `Content-Type` ghi charset khác không?

*Đáp án:* Không. Theo Java SE 24, overload không truyền charset dùng charset từ `Content-Type` nếu có và được hỗ trợ; nếu thiếu hoặc không được hỗ trợ thì fallback UTF-8. `ofString(StandardCharsets.UTF_8)` mới chọn UTF-8 tường minh.

**Bài 5.** Khi `GET` trả 404 nhưng body có HTML, tại sao không được coi là file tải thành công?

*Đáp án:* Body có thể chứa nội dung trang lỗi. Phải xác minh `statusCode()` trước khi dùng body và so byte với file kỳ vọng.

**Bài 6.** Một file `.txt` có `Content-Type: text/plain` nhưng không có `charset`. Có thể kết luận server đã tự chuyển nội dung sang UTF-8 không?

*Đáp án:* Không. SimpleFileServer chọn media type theo bảng MIME; nó không tự chuyển đổi byte file. Charset phải được xác định từ hợp đồng fixture hoặc metadata đáng tin cậy.

**Bài 7.** Vì sao `Content-Length` có thể không xuất hiện dù GET nhận body thành công?

*Đáp án:* HTTP có các cách framing khác ngoài Content-Length, ví dụ chunked transfer coding. Có thể dùng `response.body().length` để kiểm tra số byte đã nhận khi body được đưa vào `byte[]`.

**Bài 8.** Khi cần kiểm tra file lớn, nên dùng gì thay cho `ofByteArray()`?

*Đáp án:* Dùng `ofInputStream()` để đọc theo chunk hoặc `ofFile(path)` để lưu body, sau đó tính hash/so sánh. Với InputStream phải đóng hoặc đọc hết để giải phóng tài nguyên.

## 17. Ghi nhớ

`HttpClient` giúp kiểm chứng Simple Web Server mà không phụ thuộc trình duyệt. Cần tách biệt ba bằng chứng: **status** cho biết kết quả xử lý HTTP, **headers** mô tả representation và **byte body** xác nhận dữ liệu thực sự được gửi.

Với file tĩnh, kết hợp GET + `ofByteArray()` + so byte với file nguồn; dùng HEAD để kiểm tra metadata mà không tải body. Dùng `HttpHeaders.firstValue`, `firstValueAsLong` và `statusCode()` để kiểm tra chính xác hợp đồng. Hiểu rằng `ofString()` có thể giải mã theo charset trong `Content-Type`, trong khi `ofString(Charset)` dùng charset chỉ định; chúng không thay thế kiểm tra byte nguyên bản.

Simple Web Server từ JDK 18 vẫn hữu ích trên các JDK hiện đại cho bài thử cục bộ, nhưng chỉ dành cho phát triển, thử nghiệm và gỡ lỗi. Một bộ kiểm thử tốt cần chạy lại được và phát hiện sai status, header, charset hoặc byte mà trình duyệt có thể che khuất.

### Tài liệu tham khảo chính thức

- [Oracle JDK 24 — jwebserver Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jwebserver.html).
- [Oracle Java SE 24 — SimpleFileServer](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html).
- [Oracle Java SE 24 — HttpClient](https://docs.oracle.com/en/java/javase/24/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Oracle Java SE 24 — HttpRequest](https://docs.oracle.com/en/java/javase/24/docs/api/java.net.http/java/net/http/HttpRequest.html).
- [Oracle Java SE 24 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/24/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html).
- [Oracle Java SE 24 — HttpHeaders](https://docs.oracle.com/en/java/javase/24/docs/api/java.net.http/java/net/http/HttpHeaders.html).
- [OpenJDK — JEP 408: Simple Web Server](https://openjdk.org/jeps/408).
