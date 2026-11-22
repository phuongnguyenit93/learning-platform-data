# `expectContinue` và tải nội dung lớn bằng HTTP Request (Java 11+)

## Mục tiêu

Gửi một request HTTP mang **body lớn** khác với gửi một JSON nhỏ: ứng dụng có thể phải đọc tệp từ ổ đĩa, truyền hàng trăm MB hoặc nhiều GB, và server có thể từ chối request chỉ dựa trên **headers** (chẳng hạn thiếu quyền, sai loại dữ liệu hoặc vượt giới hạn). Nếu client cứ tải toàn bộ body trước khi nhận ra server đã từ chối, nó có thể tốn băng thông và thời gian không cần thiết.

Từ Java 11, `java.net.http.HttpRequest.Builder.expectContinue(true)` cho phép yêu cầu cơ chế **HTTP `100 Continue`**, nhằm nhận sự chấp thuận ban đầu của server trước khi bắt đầu phát request body. Kết hợp với `HttpRequest.BodyPublishers.ofFile(...)` hoặc `ofInputStream(...)`, ứng dụng có thể gửi nội dung lớn mà không buộc phải giữ toàn bộ dữ liệu trong heap.

Sau bài này bạn sẽ:

- Hiểu hai bước **gửi headers → chờ phản hồi ban đầu → gửi body** khi bật `expectContinue`, và phân biệt `100 Continue` với HTTP status cuối cùng.
- Dùng đúng `.expectContinue(true)`, `.POST(BodyPublishers.ofFile(path))` và `BodyPublishers.ofInputStream(supplier)`.
- Nhận biết khi nào `expectContinue` giúp hạn chế việc upload không cần thiết, và khi nào có thể làm tăng độ trễ.
- Thiết kế tải tệp lớn theo hướng **streaming, có timeout, có xử lý lỗi và có chính sách retry/idempotency**.
- Chạy chương trình Java 11 tự dựng HTTP server nội bộ để kiểm tra request với body 256 KiB.

**Phiên bản:** các API chính nêu trong bài có từ Java 11 và vẫn được hỗ trợ trong các phiên bản Java hiện đại. Không dùng API thử nghiệm hoặc cách làm phụ thuộc vào thư viện HTTP đã bị thay thế.

## 1. HTTP `100 Continue` giải quyết việc gì?

Một HTTP request có thể gồm **request line, headers và body**. Với upload lớn, phía server đôi khi xác định được ngay từ headers rằng nó không muốn chấp nhận body.

Ví dụ:

- Header xác thực không hợp lệ: server có thể trả HTTP `401 Unauthorized` hoặc `403 Forbidden`.
- Body theo khai báo quá lớn: server có thể trả HTTP `413 Content Too Large`.
- Cơ chế `Expect` không được server hỗ trợ: có thể gặp HTTP `417 Expectation Failed`.
- Server chấp nhận để client tiếp tục gửi: server trả **phản hồi thông tin `100 Continue`**.

Một trao đổi HTTP/1.1 lý tưởng khi bật `expectContinue`:

```text
Client                               Server
  | POST /upload HTTP/1.1              |
  | Expect: 100-continue               |
  | Content-Type: application/octet-stream
  | Content-Length: ...                 |
  |----------------------------------->|
  |             100 Continue           |
  |<-----------------------------------|
  |        Request body (stream)       |
  |===================================>|
  |             200 OK                 |
  |<-----------------------------------|
```

Server cũng có thể trả **phản hồi cuối cùng** ngay từ giai đoạn headers:

```text
Client                               Server
  | POST /upload + headers             |
  | Expect: 100-continue               |
  |----------------------------------->|
  |       413 Content Too Large        |
  |<-----------------------------------|
  |   (không cần chuyển toàn bộ body)  |
```

Hai sơ đồ mô tả **khả năng của giao thức**, không phải bảo đảm rằng mọi server/proxy đều phản hồi như thế. Ứng dụng chỉ có thể yêu cầu cơ chế; nó **không ép** server từ chối sớm, không bảo đảm không có byte body nào đã được truyền ở mọi hoàn cảnh và không phải là một cơ chế xác thực.

### `100` là phản hồi trung gian

- **`100 Continue`** thuộc nhóm HTTP **1xx (informational)**. Nó cho biết phía nhận có thể tiếp tục nhận body, **không xác nhận upload hoàn tất**.
- Server vẫn có thể trả **4xx/5xx** sau khi đã nhận body; ví dụ dữ liệu không hợp lệ theo nghiệp vụ.
- `HttpClient.send(...)` và `sendAsync(...)` cung cấp `HttpResponse` đại diện cho **phản hồi cuối cùng**, không phải giá trị `100` chỉ vì request bật `expectContinue`.
- Chỉ coi upload thành công khi **status cuối cùng, response body và hợp đồng API phía server** xác nhận điều đó. Với hệ thống quan trọng, cân nhắc checksum, upload ID và xác minh nội dung đã lưu.

## 2. Cấu hình `expectContinue` trong Java 11

Lệnh đúng qua `HttpRequest.Builder`:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(30))
        .expectContinue(true)
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofFile(file))
        .build();
```

Đây là **đoạn code minh họa**, cần có `URI uri`, `Path file` và import `java.net.http.HttpRequest`, `java.time.Duration`; `ofFile` có thể phát sinh `FileNotFoundException` trong quá trình tạo publisher và thao tác gửi có thể lỗi I/O.

Các điểm chính:

- `expectContinue(true)` **mặc định tắt** nếu không cấu hình. Bật `false` hoặc bỏ lời gọi sẽ không yêu cầu trình tự `100 Continue`.
- Theo Javadoc Java 11, khi bật, client **đề nghị** server gửi **phản hồi lỗi cuối cùng hoặc `100 Continue` trước body**. Publisher của request **không được kích hoạt trước khi nhận được phản hồi trung gian/khởi đầu phù hợp** theo hợp đồng này.
- Dùng API builder để bật `Expect: 100-continue`; không cần tự thêm header `Expect` thủ công. Một số header HTTP còn được client quản lý và không cho phép ứng dụng đặt tùy ý.
- `timeout(...)` trong ví dụ là timeout ở mức **request**; `HttpClient.Builder.connectTimeout(...)` xử lý riêng giai đoạn kết nối mới. Đặt timeout hợp lý, song không tưởng rằng cấu hình này thay thế mọi giới hạn thời gian xử lý phía server.
- `BodyPublisher` tạo luồng byte gửi đi. Bật `expectContinue` **không tự làm body nhỏ hơn** và không tự nén dữ liệu.

Có thể đọc cấu hình đã đóng gói trong request bằng:

```java
boolean enabled = request.expectContinue(); // true
```

Phương thức trên trả trạng thái được yêu cầu trong `HttpRequest`; **nó không chứng minh server thực sự đã gửi `100 Continue` hoặc connection nào đã được dùng**.

## 3. Chọn BodyPublisher cho tải nội dung lớn

`HttpRequest.BodyPublishers` cung cấp nhiều cách tạo request body. Lựa chọn này quan trọng **không kém** cờ `expectContinue`.

| Publisher | Nguồn dữ liệu | Đặc điểm bộ nhớ / độ dài |
| --- | --- | --- |
| `BodyPublishers.ofString(text)` | Chuỗi đã tồn tại trong RAM | Hữu ích cho body nhỏ; không phù hợp để cố dựng cả file hàng GB thành một String |
| `BodyPublishers.ofByteArray(bytes)` | Mảng byte đã nằm trong RAM | Dễ dùng nhưng dung lượng mảng tăng theo toàn body |
| `BodyPublishers.ofFile(path)` | File có đường dẫn `Path` | Publisher đọc file khi gửi, tránh tự nạp toàn bộ file thành mảng byte; độ dài có thể xác định từ file |
| `BodyPublishers.ofInputStream(supplier)` | Stream được mở theo yêu cầu | Đọc dần từ stream; hỗ trợ trường hợp nguồn không phải file; độ dài thường không biết trước |
| `BodyPublishers.fromPublisher(publisher, length)` | `Flow.Publisher<ByteBuffer>` tự xây dựng | Khi thật sự cần kiểm soát dữ liệu phát/Flow và biết chính xác độ dài; phát triển phức tạp hơn |

Các API trong bảng đều có mặt ở Java 11 theo tài liệu chính thức. Chọn phương thức phù hợp với nơi dữ liệu đang nằm, thay vì tạo trung gian một `byte[]` hoặc `String` rất lớn chỉ để gửi.

### `ofFile(path)`: lựa chọn mặc định hợp lý cho tệp lớn

```java
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofFile(file);
```

Đây là đoạn minh họa có `Path file` đã tồn tại; yêu cầu import `HttpRequest` và xử lý lỗi mở file. Nó giúp client **đọc và gửi từ tệp** theo luồng, nhưng không mang nghĩa “không dùng RAM” — vẫn có buffer nội bộ, state của client, TLS, response và các tác vụ đồng thời.

Đặc biệt:

1. File phải tồn tại và đọc được. Lỗi file không tìm thấy hoặc lỗi I/O vẫn có thể xảy ra.
2. **Đừng sửa/xóa file trong lúc request đang gửi.** Nếu thay đổi dữ liệu giữa lúc publisher xác định độ dài và lúc phát body, kết quả có thể sai, bị cắt, hoặc request thất bại.
3. Với file rất lớn, hãy kiểm soát số upload đồng thời. Chỉ dùng body publisher dạng streaming không tự bảo đảm tổng heap, socket, disk I/O và băng thông luôn nhỏ.
4. Không tự đặt `Content-Length` hoặc `Transfer-Encoding` theo phỏng đoán; để client/publisher quản lý framing theo giao thức và độ dài đã biết.
5. `ofFile` truyền **byte của file**, không tự gói `multipart/form-data`. Nếu endpoint yêu cầu multipart với boundary và các trường form, phải xây publisher đúng định dạng đó.

### `ofInputStream(supplier)`: khi nguồn là luồng dữ liệu

Nếu nguồn có thể mở lại theo yêu cầu:

```java
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofInputStream(() -> {
            try {
                return Files.newInputStream(file);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        });
```

Đây là **đoạn minh họa**, cần `Path file` cùng import `java.nio.file.Files`, `java.io.IOException`, `java.io.UncheckedIOException`, `java.net.http.HttpRequest`. Supplier không khai báo checked exception nên ví dụ bọc trong `UncheckedIOException`.

**Tại sao là Supplier chứ không nhận sẵn một InputStream?**

- Publisher có thể chỉ được yêu cầu bắt đầu phát body **sau giai đoạn `100 Continue`**.
- Một HTTP request đôi khi cần **phát lại body** do redirect, authentication challenge hoặc quy trình retry thích hợp. Theo hợp đồng `BodyPublisher`, một lần gửi lại có thể tạo subscription mới.
- Supplier nên có khả năng trả một **InputStream mới, đọc được từ đầu và cho cùng dữ liệu**, cho các lần yêu cầu phát lại nếu điều kiện nghiệp vụ cho phép. Không chia sẻ một stream đã bị tiêu thụ hết giữa các lần gọi.
- Với nguồn **không thể phát lại** (camera/live stream/một hàng đợi đã lấy dữ liệu), phải thiết kế rõ chính sách redirect, authentication và retry. Không giả định `HttpClient` sẽ luôn phát lại được body hoặc sẽ retry thành công.

`ofInputStream` thường báo **content length không biết trước**, nên cách framing sẽ phụ thuộc phiên bản HTTP/transport. Trên HTTP/1.1 có thể dùng cơ chế chunked transfer encoding; trên HTTP/2 dùng các DATA frames. Không tự ép `Content-Length` thiếu căn cứ.

## 4. Chương trình Java 11 chạy được: upload 256 KiB qua `100-continue`

Ví dụ tự khởi động một HTTP server tại `127.0.0.1` trên cổng ngẫu nhiên; tạo tệp thử nghiệm 256 KiB theo **32 khối, mỗi khối 8 KiB**; gửi tệp với `expectContinue(true)` và `BodyPublishers.ofFile(...)`. Server đọc theo khối và trả số byte thực sự nhận được.

Không cần Internet, token hay API bên ngoài. Đây là **bài thử hành vi client và truyền body**, không phải hệ thống upload production có xác thực hoặc lưu trữ bền vững.

**Tệp: `ExpectContinueUploadDemo.java`** — Java 11+

```java
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;

public class ExpectContinueUploadDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("upload-demo-", ".bin");
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/upload", exchange -> {
            long received = 0;

            try (InputStream in = exchange.getRequestBody()) {
                byte[] buffer = new byte[8192];
                int size;
                while ((size = in.read(buffer)) != -1) {
                    received += size;
                }
            }

            byte[] reply = ("received=" + received)
                    .getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, reply.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(reply);
            }
        });

        try {
            byte[] block = new byte[8192];
            Arrays.fill(block, (byte) 'A');

            try (OutputStream out = Files.newOutputStream(file)) {
                for (int i = 0; i < 32; i++) {
                    out.write(block);
                }
            }

            server.start();

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/upload");

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(20))
                    .expectContinue(true)
                    .header("Content-Type",
                            "application/octet-stream")
                    .POST(HttpRequest.BodyPublishers.ofFile(file))
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println(
                    "expectContinue=" + request.expectContinue());
            System.out.println("status=" + response.statusCode());
            System.out.println("body=" + response.body());
        } finally {
            server.stop(0);
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy trong thư mục chứa tệp với JDK 11 trở lên:

```bash
javac -encoding UTF-8 ExpectContinueUploadDemo.java
java ExpectContinueUploadDemo
```

Nếu dùng JDK mới hơn và muốn kiểm tra mức tương thích Java 11:

```bash
javac --release 11 -encoding UTF-8 ExpectContinueUploadDemo.java
java ExpectContinueUploadDemo
```

**Stdout đã kiểm tra thực tế:**

```text
expectContinue=true
status=200
body=received=262144
```

Trong thử nghiệm đã xác nhận biên dịch thành công bằng `javac --release 11` và chạy với JDK hiện đại, nhận đúng **262.144 byte** (32 × 8.192). `HttpServer` là lớp thuộc module JDK `jdk.httpserver`, không phải thư viện Maven. Cần có module đó trong bản JDK/môi trường đang sử dụng.

### Giải thích từng phần

1. `Files.createTempFile(...)` tạo tệp riêng; vòng lặp ghi nhiều khối 8 KiB, không cần dựng một mảng 256 KiB để tải lên.
2. Server tự tạo `HttpServer` trên loopback, đọc request body bằng `InputStream.read(byte[])` và đếm số byte đã nhận, rồi trả một chuỗi ngắn.
3. `HttpClient.Version.HTTP_1_1` giúp demo tập trung vào cách hoạt động với HTTP/1.1. Nó không mô phỏng một server TLS/public có proxy, redirect hoặc auth.
4. Request bật `expectContinue(true)` và dùng `ofFile(file)`. Client có thể tiến hành cơ chế chờ phản hồi tiếp tục trước khi phát body.
5. `client.send(...)` đợi phản hồi cuối cùng được tiêu thụ theo `BodyHandlers.ofString(...)`. Kết quả `status=200` là **phản hồi cuối**, không phải `100 Continue`.
6. `request.expectContinue()` chỉ hiển thị cấu hình đã được đặt. **Ví dụ không tự chứng minh bằng stdout rằng server đã gửi đúng gói `100 Continue` trên wire**; muốn kiểm tra chi tiết đó cần log giao thức, tracing hoặc công cụ giám sát phù hợp.
7. `finally` dừng server và xóa tệp tạm; trong mã Java 11 không gọi `client.close()` vì API quản lý vòng đời kiểu đó được bổ sung từ Java 21, không tồn tại trong target Java 11.

**Lưu ý:** server demo chấp nhận mọi body để có đầu ra ổn định. Bài kiểm thử server từ chối sớm, lỗi xác thực hoặc quá kích thước là trường hợp riêng; không suy ra từ stdout này rằng client đã tiết kiệm băng thông.

## 5. Khi nào bật `expectContinue` có ích?

### Có ích hơn khi

- Body lớn và **khả năng bị từ chối từ headers là đáng kể**: kiểm tra token, quyền, loại content, quota, khai báo dung lượng.
- Endpoint được xác nhận có **hỗ trợ xử lý `Expect: 100-continue`** hoặc có chính sách phản hồi lỗi sớm rõ ràng.
- Đường truyền có băng thông hạn chế hoặc chi phí truyền một payload lớn đáng kể.
- Phần lớn nội dung đã nằm ở file/stream và có thể phát muộn, không cần đọc trước.

Khi client gửi headers trước, server có cơ hội từ chối sớm **trước khi** publisher tạo/đọc body. Điều này có thể giảm upload không cần thiết, nhưng không bảo đảm hoàn toàn tránh truyền mọi byte hoặc tránh mọi chi phí.

### Không phải luôn tốt khi

- Request rất nhỏ; thêm bước chờ có thể làm tăng latency mà chẳng tiết kiệm đáng kể.
- Server/proxy xử lý `Expect` không nhất quán, trì hoãn hoặc không gửi phản hồi mong đợi.
- Backend đã chấp nhận body gần như luôn luôn, khiến cơ chế xác nhận ban đầu hiếm khi tiết kiệm băng thông.
- Ứng dụng cần protocol đặc biệt, streaming live hoặc có server không hỗ trợ handshake tương ứng.

Hãy **đo trên đường đi thực tế** gồm HTTP client, proxy/CDN/load balancer và server, thay vì tự khẳng định một mức hiệu năng tốt hơn.

## 6. Server cần xử lý gì để hỗ trợ từ chối sớm?

Phía nhận HTTP request nên phân biệt **đánh giá từ headers** và **xử lý body**:

1. Đọc request line và headers.
2. Kiểm tra những điều có thể biết ngay: credential, permission, `Content-Type`, `Content-Length` nếu có, quota/size policy.
3. Nếu không phù hợp, gửi status cuối cùng thích hợp (**401/403/413/415/417**, tùy tình huống) theo đúng giao thức/server framework, thay vì đọc body lớn trước khi từ chối.
4. Nếu có thể tiếp tục, trả `100 Continue` khi giao thức/framework yêu cầu, rồi đọc body bằng streaming.
5. Trong lúc đọc, **vẫn kiểm tra số byte thực nhận**, checksum và định dạng; khai báo `Content-Length` không phải bằng chứng an toàn rằng client trung thực.
6. Hoàn thành xử lý và trả status **cuối cùng**, kèm upload ID/checksum khi API có hợp đồng đó.

Lưu ý `413` là **Content Too Large** trong thuật ngữ HTTP hiện đại (trước đây thường gặp tên **Payload Too Large**). Việc chọn response code phải đúng với nguyên nhân lỗi, không thể dùng một code chung cho mọi trường hợp.

**Server phải tự bảo vệ nguồn lực**: giới hạn kích thước thực nhận, tốc độ, timeout, số upload đồng thời, kiểu MIME và nơi lưu file; phòng chống upload quá quota và không tin hoàn toàn filename/path do client đưa. `expectContinue` là tối ưu trao đổi, **không phải hàng rào an toàn** thay cho validation.

## 7. Phân biệt upload và download: hai phía của BodyHandler

Trong mã Java HTTP Client, tên API dễ gây nhầm:

- **Request upload:** `HttpRequest.BodyPublisher` tạo **nội dung sẽ gửi đi**.
- **Response download:** `HttpResponse.BodyHandler` quyết định **cách tiêu thụ nội dung server trả về**.

Với một file upload lớn và response JSON nhỏ:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .expectContinue(true)
        .POST(HttpRequest.BodyPublishers.ofFile(file))
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
```

Đoạn này **minh họa** với `uri`, `file`, `client` hợp lệ và xử lý `IOException`/`InterruptedException`; không phải chương trình độc lập. `BodyHandlers.ofString(...)` chỉ áp dụng cho **response** nhỏ, không có nghĩa upload đã nạp cả file thành String.

Nếu server trả về **response lớn**, cân nhắc `BodyHandlers.ofFile(path)` hoặc `ofInputStream()` cho tải xuống. Với `ofInputStream()`, caller phải đọc hết hoặc đóng stream để giải phóng tài nguyên HTTP; nếu đóng sớm, kết nối có thể không được tái sử dụng. Đây là bài toán chiều **download**, không thay thế cách thiết kế BodyPublisher cho upload.

## 8. Timeout, lỗi và hủy request

Khi gửi body lớn cần tính cả thời gian **kết nối, chờ phản hồi ban đầu, đọc file, truyền body, xử lý server và nhận response**. Có thể cấu hình:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofMinutes(3))
        .expectContinue(true)
        .PUT(HttpRequest.BodyPublishers.ofFile(file))
        .build();
```

Đây là **mã minh họa**, giả định có `URI uri`, `Path file` và import cần thiết; trong production, thời gian timeout phải được chọn theo payload, băng thông và hợp đồng API.

- `connectTimeout` áp dụng khi cần thiết lập connection mới; nó không phải timeout bao trùm upload trên connection đã có.
- `HttpRequest.Builder.timeout` đặt timeout ở mức request theo hợp đồng HTTP Client; với pipeline nhiều bước hoặc response streaming, vẫn cần deadline nghiệp vụ/kiểm soát tài nguyên phù hợp.
- `send(...)` có thể ném `IOException` và `InterruptedException`. Với async, lỗi thường nằm trong `CompletableFuture` và được bọc khi gọi `join()`.
- Nếu luồng bị interrupt khi `send`, phải giữ/cân nhắc trạng thái interrupt theo quy ước ứng dụng; không nuốt ngoại lệ rồi âm thầm retry upload.
- Khi request bị cancel/timeout, server **có thể đã nhận hoặc xử lý một phần hay toàn bộ body**. Không thể tự suy rằng “không có gì xảy ra” chỉ từ việc client không thấy status thành công.

Tải lớn cần **giới hạn số upload đồng thời** và backpressure; chỉ sử dụng `sendAsync()` không tự quản lý số lượng socket, số future hoặc tổng I/O.

## 9. Retry, redirect và body có thể phát lại

**Đây là rủi ro nghiệp vụ quan trọng nhất với upload lớn.** Đôi khi client gặp timeout sau khi server đã lưu thành công tệp nhưng response bị mất. Nếu upload lại một cách mù quáng, hệ thống có thể tạo hai bản ghi hoặc ghi đè ngoài ý muốn.

- Với `POST` có tác dụng phụ, không tự động retry vô hạn. Cân nhắc **idempotency key** hoặc upload session do server hỗ trợ.
- Với `PUT` vào một tài nguyên định danh ổn định, tính idempotent theo ngữ nghĩa HTTP hữu ích, nhưng vẫn phải hiểu ràng buộc API, versioning, permission và lỗi giữa chừng.
- Với `BodyPublishers.ofInputStream(supplier)`, mỗi lần yêu cầu phát lại có thể gọi Supplier để mở luồng từ đầu; nếu dữ liệu nguồn chỉ đọc được một lần, phát lại có thể thất bại.
- Với `BodyPublishers.ofFile(path)`, file phải giữ nguyên và truy cập được khi có lần đọc/phát lại. Đừng sửa file giữa hai lần thử.
- Redirect có thể đổi method/URI và làm phát sinh chính sách chuyển body phức tạp; xác thực thông qua challenge cũng có thể cần gửi lại. Đừng cho phép redirect sang host khác một cách thiếu kiểm soát khi có token hoặc dữ liệu nhạy cảm.
- Nếu server hỗ trợ **resumable upload** bằng upload ID, offset, chunk checksum và xác nhận phần đã lưu, hãy dùng giao thức đó cho file đặc biệt lớn hoặc mạng thường mất kết nối. `expectContinue` **không** tự hỗ trợ tiếp tục upload từ byte đã gửi.

### Tải lên theo chunk ở mức ứng dụng khác với HTTP transfer chunked

Hai khái niệm không giống nhau:

1. **Chunked transfer encoding (HTTP/1.1):** một cách đóng khung **một request body** khi không biết trước chiều dài; không tự tạo giao thức resume.
2. **Multipart/resumable upload ứng dụng:** server/client phối hợp gửi nhiều phần/phiên, theo dõi ID, offset, xác minh và cho phép thử lại từng phần theo hợp đồng riêng.

Với HTTP/2, truyền dữ liệu qua frames; không nên lấy các chi tiết `Transfer-Encoding: chunked` của HTTP/1.1 áp cho HTTP/2.

## 10. Những lỗi phổ biến

| Sai lầm | Vấn đề | Cách giải quyết |
| --- | --- | --- |
| Nghĩ bật `expectContinue(true)` nghĩa là server chắc chắn chấp nhận upload | `100` chỉ là tín hiệu tạm thời; phản hồi cuối có thể lỗi | Kiểm tra status cuối và kết quả lưu dữ liệu |
| Tin server luôn gửi `100 Continue` | Có thể trả lỗi sớm, trì hoãn hoặc không tương thích | Kiểm thử end-to-end cả qua proxy |
| Bật `expectContinue` cho mọi POST nhỏ | Có thể tăng thời gian chờ mà không tiết kiệm băng thông | Chọn theo kích thước và xác suất bị từ chối sớm |
| Tạo một `byte[]` lớn bằng toàn file rồi dùng `ofByteArray` | Dữ liệu lớn chiếm RAM không cần thiết | Dùng `ofFile` hoặc stream publisher |
| Tạo `ofInputStream(() -> existingStream)` bằng cùng một stream | Phát lại body khi retry/redirect có thể thất bại | Supplier mở stream mới, hoặc tắt/kiểm soát replay |
| Sửa hoặc xóa file đang được `ofFile` đọc | Byte thay đổi giữa lúc xác định size và lúc upload | Giữ file nguồn ổn định đến khi request kết thúc |
| Giả định mọi `Content-Length` của client là đáng tin | Server có thể bị vượt quota hoặc dữ liệu sai | Server đếm byte thực nhận, giới hạn kích thước và timeout |
| Tự set `Expect` hoặc `Content-Length` sai | Sai giao thức hoặc bị HTTP Client từ chối header | Dùng builder và publisher chuẩn |
| Cho rằng `BodyHandlers.ofFile` là API gửi file | Nhầm chiều request/response | Upload dùng `BodyPublishers.ofFile` |
| Chỉ thấy timeout rồi POST lại ngay | Server có thể đã xử lý request trước đó | Idempotency/upload session, xác minh trạng thái |
| Dùng `expectContinue` để thay xác thực | Server vẫn phải kiểm tra token và phân quyền | Auth/validation ở server, dùng HTTPS |
| Dùng chunked transfer như resume upload | Không thể nối tiếp upload đã gián đoạn chỉ nhờ framing | Dùng giao thức multipart/resumable riêng |
| Gửi hàng nghìn upload async cùng lúc | Tăng disk I/O, socket, bộ nhớ và áp lực server | Giới hạn concurrency, backpressure và theo dõi tiến độ |
| Nghĩ demo `status=200` chứng minh có gói 100 trên wire | Stdout chỉ có cấu hình và response cuối | Dùng tracing/wire log khi cần xác thực handshake |

## 11. Bài tập thực hành

**Bài 1 — Bật/tắt Expect.** Chạy chương trình mẫu với `expectContinue(true)`, sau đó đổi thành `false`. So sánh `request.expectContinue()` và kết quả byte nhận. Hai cách đều có thể thành công; đừng coi việc không thấy khác biệt stdout là chứng minh không có khác biệt về handshake.

**Bài 2 — Phân biệt status.** Giả sử server trả `100 Continue` trước body và sau khi đọc file trả `422 Unprocessable Content`. Status cuối của `HttpResponse.statusCode()` là gì? **Đáp án:** `422`, không phải `100`.

**Bài 3 — Chọn publisher.** Bạn có tệp 5 GB trên đĩa, không cần sửa nội dung trước khi gửi. Chọn `BodyPublishers.ofFile(path)` thay vì nạp toàn tệp qua `Files.readAllBytes(path)` rồi dùng `ofByteArray(...)`. Giải thích ảnh hưởng heap và file I/O.

**Bài 4 — Retry an toàn.** Một `POST /uploads` bị timeout sau khi gửi hết body, server có thể đã tạo đối tượng. Viết phương án dùng idempotency key hoặc upload session ID; hỏi trạng thái phía server trước khi gửi lại dữ liệu.

**Bài 5 — Supplier.** Viết `BodyPublishers.ofInputStream(...)` mở một `Files.newInputStream(file)` mới cho mỗi lần gọi. Giải thích vì sao trả đúng một instance `InputStream` đã mở từ trước là nguy hiểm.

**Bài 6 — HTTP server nhận streaming.** Mở rộng server demo để trả `413` nếu **số byte thực nhận** vượt giới hạn. Giữ vòng lặp đọc theo khối và tránh nạp cả body. Thử file nhỏ/file lớn và quan sát status cuối; không phụ thuộc vào việc client chắc chắn không gửi bất kỳ byte nào.

**Bài 7 — Ước lượng lợi ích.** Nếu body có 1 GiB nhưng server từ chối theo headers, bật `expectContinue` có thể tránh phải truyền payload nếu server phản hồi sớm. Nếu server luôn chấp nhận, client có thể trả thêm chi phí chờ xác nhận. Hãy mô tả những phép đo cần thu thập: upload duration, bytes sent, early rejection rate, timeout rate và khả năng tương thích proxy.

### Checklist trước khi đưa upload lớn vào sản phẩm

1. Đã chọn `BodyPublisher` streaming và không giữ cả payload trong RAM?
2. Đã xác nhận server/proxy hỗ trợ `Expect: 100-continue` ở đường đi thực tế?
3. Chỉ bật `expectContinue` khi hợp với kích thước/tỷ lệ từ chối/độ trễ?
4. Đã phân biệt **100 interim** với **status cuối** và xác minh dữ liệu đã được lưu?
5. Đã quản lý timeout, upload đồng thời, response body và luồng bị hủy?
6. Source file/stream có giữ dữ liệu ổn định, có thể replay khi cần?
7. Có idempotency key, session/resume hoặc chiến lược kiểm tra kết quả trước retry?
8. Server có xác thực, quota, kiểm tra số byte thực nhận, content type và lưu trữ an toàn?
9. Với dữ liệu nhạy cảm, đã dùng HTTPS, bảo vệ token và tránh redirect sai host?
10. Có telemetry để đo lợi ích thực tế thay vì cho rằng bật Expect luôn nhanh hơn?

## Tài liệu chính thức

- [Oracle Java SE 11 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): `expectContinue(boolean)`, mặc định false, hành vi yêu cầu server phản hồi trước khi phát body.
- [Oracle Java SE 25 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): API vẫn còn được hỗ trợ trong JDK hiện đại.
- [Oracle Java SE 11 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): `ofFile`, `ofInputStream`, `ofByteArray`, `fromPublisher`.
- [Oracle Java SE 25 — HttpRequest.BodyPublisher](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html): contract về `contentLength`, subscription và phát lại khi gửi lại.
- [Oracle Java SE 25 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): sự khác nhau giữa tiêu thụ response và phát request body.
- [RFC 9110 — HTTP Semantics, Expect / 100 Continue](https://www.rfc-editor.org/rfc/rfc9110.html): ngữ nghĩa cơ chế `100-continue`, phản hồi thông tin và status cuối.
- [OpenJDK JEP 321 — HTTP Client (Standard)](https://openjdk.org/jeps/321): Java HTTP Client được chuẩn hóa từ Java 11.

**Tóm tắt:** `expectContinue(true)` tạo cơ hội để server đồng ý hoặc từ chối **trước khi upload body lớn**; nó không thay thế streaming, xác thực, idempotency, kiểm soát dung lượng hay xử lý lỗi. Với tệp lớn, kết hợp publisher dạng luồng, timeout hợp lý, giới hạn đồng thời và xác nhận phản hồi cuối cùng mới là thiết kế đáng tin cậy.