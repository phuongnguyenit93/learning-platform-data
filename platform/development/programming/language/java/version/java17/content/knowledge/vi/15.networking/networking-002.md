# Tạo HttpRequest và chọn BodyPublisher, BodyHandler trong Java 17

Java 17 có HTTP Client API trong package `java.net.http`. Khi gửi HTTP request, hai quyết định quan trọng là:

- **`HttpRequest.BodyPublisher`:** mô tả cách cung cấp phần body gửi lên server.
- **`HttpResponse.BodyHandler<T>`:** quyết định cách nhận và xử lý body trả về, đồng thời xác định kiểu dữ liệu `T` của response.

Chọn publisher và handler phù hợp giúp tránh nạp file lớn vào bộ nhớ, giữ đúng charset, quản lý luồng I/O và làm rõ kiểu dữ liệu ở phía gọi. Bài này dùng HTTP Client API chính thức, được chuẩn hóa từ Java 11 và tiếp tục sử dụng trong Java 17; không cần thư viện HTTP bên ngoài hoặc preview feature.

## 1. Vị trí của HttpRequest trong HTTP Client API

Một lần gọi HTTP thường gồm các thành phần:

1. `HttpClient` quản lý kết nối, cấu hình TLS, proxy, redirect và cách gửi request.
2. `HttpRequest` mô tả URI đích, method, header, timeout và body publisher.
3. `HttpClient.send(...)` hoặc `sendAsync(...)` thực hiện request.
4. `HttpResponse<T>` chứa status code, headers, URI cuối cùng, HTTP version và body kiểu `T`.
5. `BodyHandler<T>` chọn cách nhận body; handler tạo body subscriber để tiêu thụ dữ liệu phản hồi.

Sơ đồ:

~~~text
HttpClient
   |
   | send(request, BodyHandler<T>)
   v
HttpRequest --------------------> Server
   |                                |
   | BodyPublisher                  | response status + headers + body
   | (request body)                 v
   |                           BodyHandler<T>
   |                                |
   +-------------------------- HttpResponse<T>
~~~

`BodyPublisher` xử lý **chiều gửi**; `BodyHandler` xử lý **chiều nhận**. Hai kiểu này có mục đích khác nhau dù đều liên quan đến body.

## 2. Tạo HttpClient và HttpRequest

`HttpClient` nên được tái sử dụng cho nhiều request cùng cấu hình. Client có thể quản lý và tái sử dụng connection nội bộ; không cần tạo một client mới cho từng request nhỏ.

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
~~~

Các cấu hình thường dùng:

- `connectTimeout` giới hạn thời gian thiết lập kết nối.
- `followRedirects` chọn chính sách xử lý redirect: `NEVER`, `NORMAL` hoặc `ALWAYS`.
- `version` đặt phiên bản HTTP mong muốn, chẳng hạn HTTP/1.1 hoặc HTTP/2. Phiên bản thực tế còn phụ thuộc khả năng server và kết nối.
- `proxy` cấu hình proxy khi môi trường yêu cầu.
- `authenticator` cấu hình cơ chế xác thực ở tầng client khi phù hợp.

`HttpRequest` được tạo qua builder:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/api/items"))
        .timeout(Duration.ofSeconds(10))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

Một request thường xác định:

| Thành phần | API | Ý nghĩa |
| --- | --- | --- |
| URI | `uri(URI)` | Địa chỉ tài nguyên |
| HTTP method | `GET()`, `POST(...)`, `PUT(...)`, `DELETE()`, `method(...)` | Hành động yêu cầu |
| Header | `header(name, value)`, `setHeader(name, value)` | Metadata của request |
| Timeout | `timeout(Duration)` | Giới hạn thời gian cho request |
| Body | `GET()`, `POST(BodyPublisher)`, `PUT(BodyPublisher)`, `method(...)` | Cách gửi nội dung |

Builder tạo ra `HttpRequest` bất biến sau khi gọi `build()`. Muốn tạo request khác, dùng builder mới hoặc `request.newBuilder()` để bắt đầu từ request hiện có.

### 2.1. GET và request không có body

`GET()` tạo request GET không có body:

~~~java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/status"))
        .GET()
        .build();
~~~

Có thể biểu diễn request không có body một cách tường minh bằng `BodyPublishers.noBody()` khi dùng `method`:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .method("GET", HttpRequest.BodyPublishers.noBody())
        .build();
~~~

Thông thường nên dùng `GET()` cho GET và `DELETE()` cho DELETE khi không có body. Không cần tạo một chuỗi rỗng chỉ để biểu diễn request không có nội dung.

### 2.2. POST, PUT và method tùy chỉnh

`POST` và `PUT` nhận một `BodyPublisher`:

~~~java
HttpRequest post = HttpRequest.newBuilder(uri)
        .POST(HttpRequest.BodyPublishers.noBody())
        .build();

HttpRequest put = HttpRequest.newBuilder(uri)
        .PUT(HttpRequest.BodyPublishers.ofString("content"))
        .build();
~~~

Với method không có convenience method riêng, dùng `method(name, publisher)`:

~~~java
HttpRequest patch = HttpRequest.newBuilder(uri)
        .method(
                "PATCH",
                HttpRequest.BodyPublishers.ofString("{\"active\":true}"))
        .header("Content-Type", "application/json")
        .build();
~~~

Tên method phải tuân theo quy tắc của HTTP và server phải hỗ trợ method đó. Không nên giả định mọi server đều hỗ trợ PATCH hoặc các method mở rộng.

### 2.3. header và setHeader

`header(name, value)` thêm một giá trị header; gọi nhiều lần có thể tạo nhiều giá trị cùng tên. `setHeader(name, value)` thay thế các giá trị trước đó của header đó.

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Accept", "application/json")
        .header("Accept", "text/plain")
        .setHeader("X-Request-Source", "java17-demo")
        .GET()
        .build();
~~~

Header HTTP không phân biệt chữ hoa/chữ thường theo tên. Việc có nhiều giá trị hay thay thế giá trị phải theo ý nghĩa của header và hợp đồng API.

Không tự đặt `Content-Length`. HTTP Client xác định độ dài từ `BodyPublisher` khi có thể và quản lý framing của request. Một số header bị client hạn chế vì chúng phải được quản lý theo giao thức hoặc cấu hình riêng.

## 3. BodyPublisher là gì?

`HttpRequest.BodyPublisher` là một `Flow.Publisher<ByteBuffer>` cung cấp dữ liệu body cho HTTP Client. Nó mô tả cách phát các phần dữ liệu để gửi, cùng thông tin độ dài nội dung nếu biết.

Các publisher dựng sẵn nằm trong `HttpRequest.BodyPublishers`:

| Factory | Dùng khi |
| --- | --- |
| `noBody()` | Request không có nội dung |
| `ofString(String)` | Gửi văn bản |
| `ofString(String, Charset)` | Gửi văn bản với charset xác định |
| `ofByteArray(byte[])` | Gửi dữ liệu nhị phân đang có trong bộ nhớ |
| `ofByteArray(byte[], offset, length)` | Gửi một vùng của mảng byte |
| `ofFile(Path)` | Gửi nội dung file |
| `ofInputStream(Supplier<InputStream>)` | Cung cấp dữ liệu qua InputStream được tạo khi publisher cần đọc |

Chọn publisher theo nguồn dữ liệu thực tế. Không nên chuyển file lớn thành `byte[]` chỉ để dùng `ofByteArray` nếu có thể gửi trực tiếp bằng `ofFile`.

## 4. Gửi văn bản bằng ofString

Với JSON, XML, form text hoặc nội dung văn bản nhỏ, `ofString` là lựa chọn đơn giản:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

String json = """
        {
          "name": "An",
          "active": true
        }
        """;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/api/users"))
        .header("Content-Type", "application/json; charset=UTF-8")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
~~~

`ofString(String)` sử dụng UTF-8. Overload có `Charset` giúp thể hiện rõ encoding của body và tránh phụ thuộc vào giả định ngầm khi đọc code.

`Content-Type` mô tả kiểu nội dung đang gửi; `Accept` mô tả kiểu phản hồi client mong muốn. Hai header này không thay thế nhau.

Không nối dữ liệu người dùng vào JSON bằng cách ghép chuỗi tùy tiện. Trong ứng dụng thực tế, dùng JSON serializer để escape đúng ký tự và xử lý kiểu dữ liệu.

## 5. Gửi byte array bằng ofByteArray

Nếu nội dung đã nằm trong bộ nhớ dưới dạng byte, dùng `ofByteArray`:

~~~java
byte[] payload = {
        0x01, 0x02, 0x03, (byte) 0xFE
};

HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofByteArray(payload))
        .build();
~~~

Để gửi một vùng của mảng:

~~~java
byte[] buffer = new byte[1024];
// Giả sử dữ liệu hợp lệ nằm trong buffer từ offset đến offset + length.
int offset = 100;
int length = 200;

HttpRequest request = HttpRequest.newBuilder(uri)
        .POST(HttpRequest.BodyPublishers.ofByteArray(
                buffer, offset, length))
        .build();
~~~

Overload này giúp tránh tạo mảng con chỉ để gửi một vùng dữ liệu. Hãy bảo đảm offset và length nằm trong giới hạn mảng.

`ofByteArray` phù hợp với payload có kích thước vừa phải đã có sẵn trong bộ nhớ. Nếu đọc file lớn, nên dùng `ofFile` để tránh tự nạp toàn bộ file vào một mảng.

## 6. Gửi file bằng ofFile

`BodyPublishers.ofFile(Path)` tạo publisher đọc nội dung từ file:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.file.Path;

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/api/upload"))
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofFile(
                Path.of("data/archive.bin")))
        .build();
~~~

Factory `ofFile` có thể ném `IOException` khi không thể mở file. File phải tồn tại và có thể đọc được khi publisher thực hiện việc gửi.

Lợi ích:

- Không cần tự đọc toàn bộ file thành `byte[]`.
- Phù hợp hơn với file lớn.
- HTTP Client có thể lấy độ dài nội dung từ file.
- Code thể hiện rõ nguồn body là một file.

Đây là gửi **raw file body**. Nếu server yêu cầu multipart/form-data với boundary và các trường form, cần tạo đúng cấu trúc multipart theo giao thức; chỉ đặt `Content-Type: multipart/form-data` rồi gửi raw file sẽ không tạo ra multipart hợp lệ.

## 7. Gửi dữ liệu qua ofInputStream

`BodyPublishers.ofInputStream(Supplier<? extends InputStream>)` phù hợp khi nguồn dữ liệu được cung cấp qua `InputStream`, chẳng hạn dữ liệu sinh theo yêu cầu hoặc được mở từ một nguồn tùy chỉnh.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.net.http.HttpRequest;

HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofInputStream(() -> {
            try {
                return Files.newInputStream(Path.of("data.bin"));
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        }))
        .build();
~~~

Supplier được gọi khi publisher cần một stream để phát body. Vì việc đọc là lazy, đừng mở stream trước rồi đóng nó ngay sau khi dựng request.

Một supplier tốt cần có khả năng cung cấp stream mới khi được gọi lại, nếu publisher cần subscription mới. Không trả lại cùng một `InputStream` đã bị đọc hoặc đóng. Với nguồn file thông thường, `ofFile` đơn giản hơn và thường là lựa chọn rõ ràng hơn.

Vòng đời của stream do publisher quản lý theo hợp đồng của implementation; không giữ một stream bên ngoài rồi vừa gửi vừa đọc/sửa nó ở nơi khác. Nếu tự quản lý một nguồn đặc biệt, hãy đọc rõ hợp đồng publisher và supplier.

## 8. BodyPublisher tùy chỉnh và Flow API

Trong tình huống nâng cao, có thể tạo publisher từ `Flow.Publisher<ByteBuffer>`:

~~~java
Flow.Publisher<ByteBuffer> publisher = obtainPublisher();

HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.fromPublisher(
                publisher,
                knownContentLength);
~~~

Overload có `contentLength` yêu cầu độ dài được cung cấp chính xác. Nếu không biết trước độ dài, có thể dùng overload chỉ nhận publisher:

~~~java
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.fromPublisher(publisher);
~~~

Không khai báo sai content length: dữ liệu thực tế và độ dài đã khai báo phải nhất quán. Nếu nguồn không thể bảo đảm độ dài, dùng overload không có độ dài để HTTP Client xử lý theo cơ chế truyền phù hợp.

Tự triển khai `Flow.Publisher` đòi hỏi tuân thủ backpressure, subscription, tín hiệu kết thúc và quy tắc lỗi của Reactive Streams/Flow. Với phần lớn ứng dụng, publisher dựng sẵn như `ofString`, `ofByteArray`, `ofFile` hoặc `ofInputStream` dễ dùng và ít rủi ro hơn.

## 9. BodyHandler quyết định cách nhận response

`HttpResponse.BodyHandler<T>` nhận thông tin response (status và headers) và cung cấp `BodySubscriber<T>` để xử lý body. Kiểu `T` trở thành kiểu body trong `HttpResponse<T>`.

Ví dụ:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString());
~~~

Ở đây handler trả body dưới dạng `String` nên kiểu response là `HttpResponse<String>`.

Các handler dựng sẵn trong `HttpResponse.BodyHandlers`:

| Handler | Kiểu body | Dùng khi |
| --- | --- | --- |
| `ofString()` | `String` | Response văn bản nhỏ/vừa |
| `ofString(Charset)` | `String` | Văn bản cần charset cụ thể |
| `ofByteArray()` | `byte[]` | Payload nhị phân nhỏ/vừa |
| `ofFile(Path)` | `Path` | Ghi response body trực tiếp ra file |
| `ofInputStream()` | `InputStream` | Muốn đọc body theo luồng |
| `ofLines(Charset)` | `Stream<String>` | Response văn bản theo dòng |
| `discarding()` | `Void` | Không cần body |
| `replacing(value)` | Kiểu của value | Bỏ body và trả một giá trị thay thế |

Lựa chọn handler ảnh hưởng trực tiếp đến bộ nhớ và vòng đời tài nguyên. Nếu body lớn, tránh `ofByteArray` hoặc `ofString` khi không cần giữ toàn bộ nội dung trong heap.

## 10. Nhận văn bản bằng ofString

Đây là lựa chọn phù hợp với JSON response, thông báo lỗi hoặc nội dung text có kích thước vừa phải:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

System.out.println(response.statusCode());
System.out.println(response.headers().firstValue("Content-Type"));
System.out.println(response.body());
~~~

`ofString()` mặc định dùng UTF-8; overload nhận charset giúp hợp đồng encoding rõ ràng.

Response body chỉ có thể được đọc theo handler đã chọn. Nếu body là JSON, `String` vẫn chỉ là văn bản; cần JSON parser/serializer để ánh xạ sang object.

### 10.1. Đừng mặc định mọi response đều là JSON

Server có thể trả:

- JSON cho API thành công.
- HTML cho trang lỗi hoặc proxy.
- Plain text cho thông báo.
- Binary cho file hoặc ảnh.
- Body rỗng cho một số response.

Dùng `Content-Type` và hợp đồng endpoint để chọn cách parse. Không nên parse mọi body thành JSON chỉ vì request đã gửi header `Accept: application/json`; server vẫn có thể trả lỗi hoặc loại nội dung khác.

## 11. Nhận dữ liệu nhị phân bằng ofByteArray

~~~java
HttpResponse<byte[]> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofByteArray());

byte[] body = response.body();
System.out.println("bytes = " + body.length);
~~~

Dùng khi response nhỏ hoặc cần toàn bộ dữ liệu trong bộ nhớ, ví dụ một ảnh thumbnail hoặc một payload binary giới hạn kích thước.

Với file lớn, `ofByteArray` có thể tiêu tốn nhiều heap. Nên cân nhắc `ofFile` hoặc `ofInputStream` để xử lý theo luồng.

## 12. Ghi response trực tiếp ra file bằng ofFile

`BodyHandlers.ofFile(Path)` ghi response body vào file và trả về đường dẫn:

~~~java
import java.net.http.HttpResponse;
import java.nio.file.Path;

HttpResponse<Path> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofFile(
                Path.of("downloads/report.pdf")));

System.out.println("status = " + response.statusCode());
System.out.println("saved = " + response.body());
~~~

Handler quản lý việc ghi body ra file trong quá trình nhận response. Khi `send` hoàn tất, body đã được xử lý theo handler.

Lưu ý: handler ghi body bất kể status code là thành công hay lỗi, trừ khi dùng handler tùy chỉnh để chọn cách xử lý theo status. Một server có thể trả HTML lỗi với status 404; nếu dùng `ofFile` trực tiếp, nội dung lỗi cũng có thể được lưu vào file đích.

Nếu cần bảo vệ file đích khỏi response lỗi, hãy thiết kế body handler dựa trên `ResponseInfo.statusCode()` hoặc nhận response theo cách cho phép kiểm tra status trước khi quyết định lưu. Đừng chỉ kiểm tra status sau đó rồi cho rằng file đích chắc chắn chứa tài liệu thành công.

## 13. Nhận InputStream và đóng đúng vòng đời

`BodyHandlers.ofInputStream()` trả về `InputStream` thay vì đợi đọc toàn bộ body thành mảng hoặc chuỗi:

~~~java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] prefix = body.readNBytes(128);
    System.out.println("read bytes = " + prefix.length);
}
~~~

Handler này hữu ích khi response lớn hoặc ứng dụng muốn đọc từng phần. Nhưng nó chuyển trách nhiệm đóng body stream sang phía gọi. Phải đóng `InputStream`, tốt nhất bằng try-with-resources.

`send` với `ofInputStream` có thể trả về sau khi headers đã nhận và stream body được cung cấp; body chưa nhất thiết đã được đọc hết. Vì vậy cần giữ stream mở trong lúc xử lý, và đóng sau khi đọc xong hoặc khi quyết định bỏ phần còn lại.

Không đọc body stream sau khi đã đóng. Cũng không bỏ qua close khi chỉ đọc một phần; việc đóng giúp HTTP Client giải phóng hoặc kết thúc xử lý tài nguyên phản hồi đúng cách.

## 14. Nhận nội dung theo dòng bằng ofLines

Nếu response là văn bản nhiều dòng và muốn xử lý lazy, dùng `BodyHandlers.ofLines(Charset)`:

~~~java
HttpResponse<Stream<String>> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofLines(StandardCharsets.UTF_8));

try (Stream<String> lines = response.body()) {
    lines.filter(line -> !line.isBlank())
            .forEach(System.out::println);
}
~~~

Body có kiểu `Stream<String>`, vì vậy caller cần đóng stream sau khi tiêu thụ. Đây là một ví dụ resource-backed stream: terminal operation không tự đóng nguồn response.

Dùng `ofLines` khi nội dung lớn theo dòng và không cần giữ toàn bộ body trong một `String`. Nếu chỉ cần parse một JSON object nhỏ, `ofString` thường đơn giản hơn.

## 15. Bỏ qua response body

Nếu chỉ cần status và headers, có thể dùng `BodyHandlers.discarding()`:

~~~java
HttpResponse<Void> response = client.send(
        request,
        HttpResponse.BodyHandlers.discarding());

System.out.println(response.statusCode());
System.out.println(response.headers().map());
~~~

Body bị bỏ qua; kiểu body của response là `Void`. Cách này hữu ích khi gọi endpoint mà nội dung phản hồi không cần sử dụng, hoặc khi thực hiện thao tác chỉ quan tâm kết quả trạng thái.

`BodyHandlers.replacing(value)` cũng bỏ qua body nhưng trả một giá trị thay thế:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.replacing("body ignored"));

System.out.println(response.body()); // body ignored
~~~

Giá trị thay thế không phải dữ liệu server gửi về; nó do ứng dụng chỉ định.

## 16. Chọn BodyHandler theo status và headers

`BodyHandler<T>` được gọi khi thông tin response headers đã có. Vì thế có thể lựa chọn cách tiêu thụ body dựa trên status code hoặc header.

Ví dụ dưới đây dùng một kiểu kết quả chung là `byte[]`: response 2xx được đọc thành bytes; response khác 2xx cũng đọc thành bytes để caller có thể xem error body:

~~~java
HttpResponse.BodyHandler<byte[]> handler = info -> {
    String contentType = info.headers()
            .firstValue("Content-Type")
            .orElse("unknown");

    System.out.println("status = " + info.statusCode());
    System.out.println("content-type = " + contentType);

    return HttpResponse.BodySubscribers.ofByteArray();
};
~~~

Vì cả hai nhánh đều phải trả `BodySubscriber<byte[]>`, kiểu response không thay đổi. Sau đó caller kiểm tra status:

~~~java
HttpResponse<byte[]> response = client.send(request, handler);

if (response.statusCode() >= 200 && response.statusCode() < 300) {
    // Xử lý body thành công.
} else {
    // Phân tích error body hoặc chuyển thành lỗi nghiệp vụ.
}
~~~

Ví dụ này vẫn giữ toàn bộ body trong bộ nhớ. Với response lớn, có thể thiết kế subscriber/handler chuyên biệt để ghi ra file hoặc giới hạn dữ liệu; cần bảo đảm mọi nhánh vẫn trả subscriber có cùng kiểu kết quả `T`.

`BodyHandler` không tự quyết định response là thành công hay thất bại. Nó chọn cách đọc body. Việc diễn giải status code thuộc logic ứng dụng.

## 17. Gửi request đồng bộ bằng send

`HttpClient.send(request, handler)` thực hiện request đồng bộ và trả về `HttpResponse<T>`:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

Phương thức có thể ném:

- `IOException` khi lỗi I/O xảy ra trong quá trình gửi/nhận.
- `InterruptedException` nếu thread đang chờ bị interrupt.

Ví dụ hoàn chỉnh:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class GetTextDemo {
    public static void main(String[] args)
            throws IOException, InterruptedException {

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(15))
                .header("Accept", "text/html")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        System.out.println("status = " + response.statusCode());
        System.out.println("version = " + response.version());
        System.out.println("final URI = " + response.uri());
        System.out.println("body length = " + response.body().length());
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -encoding UTF-8 GetTextDemo.java
java GetTextDemo
~~~

Ví dụ phụ thuộc kết nối mạng và endpoint bên ngoài. Status code có thể thay đổi theo thời điểm hoặc chính sách server; điều quan trọng là cách request và handler được kết hợp.

## 18. Gửi request bất đồng bộ bằng sendAsync

`sendAsync` trả về `CompletableFuture<HttpResponse<T>>`, cho phép xử lý tiếp khi response hoàn tất mà không chặn thread gọi trong lúc chờ I/O:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

future.thenApply(HttpResponse::statusCode)
        .thenAccept(System.out::println);
~~~

Hoặc chờ kết quả trong ví dụ đơn giản:

~~~java
HttpResponse<String> response = client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
        .join();
~~~

`join()` chờ kết quả và có thể ném `CompletionException` nếu tác vụ hoàn tất bất thường. Nếu dùng `get()`, cần xử lý `InterruptedException` và `ExecutionException`.

`sendAsync` không thay đổi vai trò của BodyPublisher hoặc BodyHandler: request vẫn cần publisher cho body gửi, response vẫn cần handler cho body nhận. Nếu handler trả `InputStream` hoặc `Stream<String>`, caller vẫn phải đóng tài nguyên đó sau khi future hoàn tất và body được sử dụng.

## 19. Timeout, status code và lỗi HTTP

Có hai loại timeout thường được cấu hình:

- `HttpClient.Builder.connectTimeout` giới hạn thời gian thiết lập kết nối.
- `HttpRequest.Builder.timeout` giới hạn thời gian cho request.

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
~~~

Timeout request không có nghĩa server trả một status code đặc biệt; request có thể thất bại bằng exception khi thời gian chờ vượt giới hạn.

### 19.1. HTTP 404 hoặc 500 không tự động thành exception

`HttpClient.send` thường vẫn trả `HttpResponse<T>` khi server gửi status 404, 500 hoặc status không thuộc 2xx. Ứng dụng phải kiểm tra:

~~~java
int status = response.statusCode();

if (status >= 200 && status < 300) {
    System.out.println("Request thành công");
} else {
    System.out.println("HTTP error: " + status);
}
~~~

Đây là khác biệt giữa **lỗi giao thức/transport** (không kết nối được, timeout, I/O lỗi) và **response HTTP có status báo lỗi**. Một response 404 vẫn là một response hợp lệ ở tầng HTTP.

### 19.2. Phân biệt các nhóm lỗi

| Tình huống | Cách nhận biết thường gặp |
| --- | --- |
| DNS, socket, TLS hoặc I/O lỗi | `IOException` hoặc subtype |
| Thread chờ bị interrupt | `InterruptedException` |
| Request timeout | `HttpTimeoutException` (subclass của `IOException`) |
| Server trả 4xx/5xx | `HttpResponse.statusCode()` |
| Body không đúng định dạng mong đợi | Lỗi parse ở tầng ứng dụng |
| Future async hoàn tất bất thường | `CompletionException` hoặc exception khi lấy kết quả |

Không nên coi mọi status khác 200 là thất bại: nhiều API dùng 201, 202 hoặc 204 cho kết quả thành công. Hãy kiểm tra dải status phù hợp với hợp đồng endpoint.

## 20. Content-Type, charset và Accept

Ba khái niệm dễ nhầm:

- `Content-Type` của request: loại dữ liệu đang gửi lên.
- `Accept` của request: loại dữ liệu client muốn nhận.
- `Content-Type` của response: loại dữ liệu server thực sự trả về.

Ví dụ JSON:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/json; charset=UTF-8")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
~~~

Khi nhận response, kiểm tra header trước khi parse:

~~~java
String contentType = response.headers()
        .firstValue("Content-Type")
        .orElse("");

if (contentType.toLowerCase(Locale.ROOT)
        .contains("application/json")) {
    // Parse JSON.
} else {
    // Xử lý theo loại nội dung khác hoặc báo lỗi hợp đồng.
}
~~~

Ví dụ trên minh họa kiểm tra loại nội dung cơ bản; ứng dụng có yêu cầu chặt hơn nên parse media type theo quy tắc đầy đủ thay vì chỉ dùng phép chứa chuỗi.

Không mặc định charset của mọi response là UTF-8 nếu server không tuân hợp đồng. Với API hiện đại, UTF-8 thường là lựa chọn phổ biến; vẫn nên thống nhất encoding ở hai phía.

## 21. Chọn cặp BodyPublisher và BodyHandler theo tình huống

| Nhu cầu | BodyPublisher | BodyHandler | Ghi chú |
| --- | --- | --- | --- |
| GET dữ liệu JSON nhỏ | `noBody()` hoặc `GET()` | `ofString(UTF_8)` | Parse JSON sau khi nhận |
| POST JSON | `ofString(json, UTF_8)` | `ofString(UTF_8)` | Đặt Content-Type/Accept phù hợp |
| Gửi ảnh hoặc payload bytes nhỏ | `ofByteArray(bytes)` | `ofString` hoặc `ofByteArray` tùy response | Phù hợp dữ liệu đã nằm trong bộ nhớ |
| Upload file lớn | `ofFile(path)` | Theo response, thường `ofString` hoặc `discarding` | Tránh nạp toàn file vào heap |
| Gửi nguồn InputStream | `ofInputStream(supplier)` | Theo response | Supplier phải cung cấp stream có vòng đời hợp lệ |
| Download file | `noBody()` hoặc GET | `ofFile(path)` | Xem xét status trước khi coi file là hợp lệ |
| Download/đọc body từng phần | `noBody()` hoặc GET | `ofInputStream()` | Caller phải đóng InputStream |
| Xử lý response text theo dòng | `noBody()` hoặc GET | `ofLines(UTF_8)` | Đóng Stream<String> |
| Chỉ cần status/header | Theo request | `discarding()` | Body bị bỏ qua |

Lựa chọn đúng phụ thuộc cả kích thước dữ liệu, định dạng, cách tiêu thụ và trách nhiệm đóng tài nguyên.

## 22. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Body tiếng Việt lỗi ký tự | Không thống nhất charset | Dùng `ofString(text, UTF_8)` và handler có charset rõ |
| Gửi file lớn làm tăng heap | Đọc toàn file vào `byte[]` | Dùng `BodyPublishers.ofFile` |
| Response lớn làm tăng heap | Dùng `ofByteArray` hoặc `ofString` không giới hạn | Cân nhắc `ofFile` hoặc `ofInputStream` |
| Response stream bị rò rỉ | Không đóng `InputStream` hoặc `Stream<String>` | Dùng try-with-resources |
| POST không có body như mong muốn | Dùng nhầm `noBody` hoặc publisher rỗng | Chọn publisher phù hợp và kiểm tra Content-Type |
| Server báo sai Content-Length | Tự đặt header hoặc khai báo độ dài custom publisher không đúng | Để client quản lý hoặc cung cấp length chính xác |
| Server trả 404 nhưng code không vào catch | HTTP status không tự động là exception | Kiểm tra `statusCode()` |
| Download file lỗi nhưng file vẫn tồn tại | `ofFile` đã ghi body của response lỗi | Kiểm tra status và thiết kế handler phù hợp |
| Async task lỗi nhưng không thấy trong callback | Exception nằm trong `CompletableFuture` | Xử lý `exceptionally`, `handle` hoặc khi lấy kết quả |
| Dùng cùng InputStream nhiều lần | Supplier trả lại stream đã đọc/đóng | Tạo stream mới cho mỗi lần được yêu cầu |
| Đặt Accept nhưng server vẫn trả loại khác | Accept là yêu cầu thương lượng, không phải bảo đảm | Kiểm tra Content-Type thực tế |
| Mỗi request tạo một HttpClient | Không tái sử dụng client | Dùng client dùng chung theo cấu hình phù hợp |

## 23. Bài tập thực hành

### Bài 1 — GET văn bản

Tạo `HttpClient` và `HttpRequest` GET tới một endpoint văn bản. Dùng `BodyHandlers.ofString(UTF_8)`, in status, Content-Type và độ dài body.

### Bài 2 — POST JSON

Tạo JSON có hai trường, dùng `BodyPublishers.ofString`, đặt `Content-Type` và `Accept`. Gửi request tới endpoint thử nghiệm mà bạn kiểm soát; kiểm tra status và response body.

### Bài 3 — Upload file

Dùng `BodyPublishers.ofFile` gửi một file nhị phân. Quan sát cách request được tạo mà không cần tự đọc toàn file vào mảng byte.

### Bài 4 — Download file

Dùng `BodyHandlers.ofFile` để ghi response vào một đường dẫn. Kiểm tra status trước khi ứng dụng coi file là kết quả tải thành công.

### Bài 5 — Đọc InputStream

Dùng `BodyHandlers.ofInputStream`, đọc từng block byte và đóng stream bằng try-with-resources. So sánh với `ofByteArray`.

### Bài 6 — Body theo dòng

Dùng `BodyHandlers.ofLines(StandardCharsets.UTF_8)` để lọc các dòng chứa từ khóa. Đảm bảo stream được đóng sau khi terminal operation hoàn tất.

### Bài 7 — Đồng bộ và bất đồng bộ

Gửi cùng một request bằng `send` và `sendAsync`. So sánh cách xử lý exception, kết quả và thread chờ.

### Bài 8 — Status và lỗi

Thử endpoint trả về 2xx, 404 và 500. Giải thích vì sao phải kiểm tra `statusCode()` ngay cả khi `send` không ném exception.

## 24. Nguyên tắc thiết kế

Khi làm việc với HTTP Client trong Java 17:

- Dùng `HttpClient` dùng chung cho các request có cấu hình tương tự.
- Tạo `HttpRequest` bất biến bằng builder; khai báo rõ URI, method, header và timeout.
- Chọn `BodyPublisher` theo nguồn dữ liệu: text, byte array, file hoặc InputStream.
- Chọn `BodyHandler<T>` theo cách ứng dụng cần tiêu thụ response: String, bytes, file, stream hoặc bỏ qua.
- Dùng charset tường minh khi gửi/nhận văn bản.
- Không tự đặt Content-Length khi HTTP Client có thể quản lý; custom publisher phải khai báo độ dài chính xác nếu cung cấp.
- Kiểm tra status code và Content-Type; HTTP 4xx/5xx vẫn là response, không tự động thành exception.
- Đóng body resource như `InputStream` và `Stream<String>` khi handler trả về các kiểu đó.
- Với dữ liệu lớn, ưu tiên cách truyền/nhận theo file hoặc stream để tránh giữ toàn bộ body trong bộ nhớ.
- Phân biệt lỗi I/O, timeout, interrupt, status HTTP và lỗi parse ở tầng ứng dụng.

`BodyPublisher` và `BodyHandler` tạo thành hai đầu của hợp đồng truyền dữ liệu. Khi chọn đúng theo kích thước, định dạng và vòng đời tài nguyên, code Java 17 có thể gửi request rõ ràng, nhận response hiệu quả và quản lý body một cách an toàn.
