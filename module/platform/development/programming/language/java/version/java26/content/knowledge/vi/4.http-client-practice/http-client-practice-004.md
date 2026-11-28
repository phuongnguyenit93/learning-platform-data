# BodyHandler phù hợp với văn bản, tệp và dữ liệu truyền luồng

Khi gửi request bằng `java.net.http.HttpClient`, bạn phải chọn một `BodyHandler<T>` để quyết định cách nhận response body. Lựa chọn này ảnh hưởng trực tiếp đến kiểu dữ liệu của `HttpResponse<T>`, thời điểm response được trả về, lượng bộ nhớ sử dụng và cách giải phóng tài nguyên.

Với response nhỏ như JSON hoặc thông báo lỗi, đọc thành `String` thường tiện nhất. Với nội dung nhị phân hoặc tệp lớn, ghi trực tiếp ra file hoặc đọc theo luồng giúp tránh giữ toàn bộ nội dung trong heap. Với dữ liệu dạng dòng hoặc luồng byte cần xử lý liên tục, dùng các handler streaming để tiêu thụ dữ liệu khi nó đến.

## 1. BodyHandler và BodySubscriber làm gì?

`BodyHandler<T>` nhận thông tin ban đầu của response, gồm status và headers, rồi chọn một `BodySubscriber<T>`. Subscriber nhận các phần dữ liệu dạng `ByteBuffer` theo thứ tự và chuyển chúng thành kiểu `T` mà chương trình cần. Các lớp tiện ích `HttpResponse.BodyHandlers` và `HttpResponse.BodySubscribers` cung cấp sẵn những cách xử lý phổ biến.

Kiểu `T` quyết định cách sử dụng `response.body()`:

- `String`, `byte[]` hoặc `Path`: body được tích lũy hoặc ghi xong trước khi response hoàn tất.
- `InputStream`, `Stream<String>` hoặc `Flow.Publisher`: response có thể được trả về ngay sau khi nhận headers; chương trình tiếp tục tiêu thụ body sau đó.

Các handler dựng sẵn như `ofString()` và `ofFile()` không tự kiểm tra mã trạng thái HTTP. Nếu server trả `404` hoặc `500`, body lỗi vẫn được xử lý theo handler đã chọn. Khi cần hành vi khác nhau theo status hoặc headers, hãy tự tạo `BodyHandler` bằng lambda nhận `ResponseInfo`.

## 2. Chọn handler theo loại dữ liệu

| Loại response | Handler phù hợp | Đặc điểm và lưu ý |
|---|---|---|
| JSON, XML, văn bản nhỏ | `BodyHandlers.ofString()` | Dễ parse; giữ toàn bộ body trong bộ nhớ |
| Văn bản cần charset xác định | `BodyHandlers.ofString(charset)` | Chủ động chọn bộ mã ký tự |
| Tệp nhị phân nhỏ | `BodyHandlers.ofByteArray()` | Tiện xử lý bytes; bộ nhớ tăng theo kích thước body |
| Tải thẳng xuống tệp | `BodyHandlers.ofFile(path)` | Ghi body ra file, không cần gom cả file vào heap |
| Tệp có tên do server cung cấp | `BodyHandlers.ofFileDownload(directory)` | Lấy filename từ `Content-Disposition`; phải xem filename là dữ liệu không đáng tin cậy |
| Dữ liệu văn bản dạng dòng | `BodyHandlers.ofLines()` | Đọc từng dòng; phải đóng `Stream` |
| Dữ liệu cần xử lý theo khối byte | `BodyHandlers.ofInputStream()` | Đọc từng phần qua `InputStream`; phải đóng stream |
| Luồng byte theo Flow API | `BodyHandlers.ofPublisher()` | Có backpressure; chỉ được subscribe một lần và phải tiêu thụ hoặc hủy subscription |
| Không cần body | `BodyHandlers.discarding()` | Bỏ qua body, vẫn nhận status và headers |

Không dùng `ofString()` hoặc `ofByteArray()` cho file lớn chỉ vì cách gọi ngắn hơn. Hai handler này phải giữ toàn bộ nội dung trước khi trả body; một response lớn có thể gây tăng heap hoặc `OutOfMemoryError`.

## 3. Nhận văn bản và JSON

### 3.1. Dùng charset theo response

`BodyHandlers.ofString()` đọc charset từ header `Content-Type`. Nếu header không có charset hoặc charset không được hỗ trợ, handler dùng UTF-8. Nếu giao thức của API quy định rõ UTF-8, có thể khai báo tường minh để code thể hiện đúng hợp đồng:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.test/v1/products"))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

if (response.statusCode() < 200 || response.statusCode() >= 300) {
    throw new java.io.IOException("HTTP status: " + response.statusCode());
}

String json = response.body();
```

Chọn charset tường minh chỉ khi nó phù hợp với giao thức của endpoint. Nếu server trả văn bản theo charset khác, ép UTF-8 sẽ làm sai nội dung. Với JSON trao đổi giữa các hệ thống, UTF-8 là lựa chọn tương thích phổ biến và nên được ghi rõ trong hợp đồng API.

### 3.2. Giới hạn kích thước response

Một response văn bản nhỏ có thể trở thành response rất lớn do lỗi server, dữ liệu bất thường hoặc endpoint bị lạm dụng. Từ JDK 25, `BodyHandlers.limiting(downstreamHandler, capacity)` giới hạn số byte body được chuyển đến handler bên dưới. Nếu số byte vượt giới hạn, quá trình xử lý body kết thúc bằng `IOException`.

```java
long maxJsonBytes = 2L * 1024 * 1024;

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.limiting(
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8),
                maxJsonBytes));

if (response.statusCode() < 200 || response.statusCode() >= 300) {
    throw new java.io.IOException("HTTP status: " + response.statusCode());
}
```

Giới hạn này áp dụng cho byte body thực tế được nhận, kể cả khi server không gửi `Content-Length` hoặc giá trị header không đáng tin cậy. Có thể kiểm tra thêm `Content-Length` để từ chối sớm, nhưng không nên chỉ dựa vào header đó. `limiting` là API chính thức từ JDK 25, có sẵn trên JDK 26 và không cần bật preview.

### 3.3. Đọc văn bản theo từng dòng

Khi xử lý log, NDJSON hoặc một response văn bản dài được phân tách theo dòng, `ofLines()` trả về `Stream<String>`. Response có thể được trả về trước khi toàn bộ body đến nơi, nên chương trình đọc các dòng dần dần thay vì tạo một `String` lớn.

```java
import java.util.stream.Stream;

HttpResponse<Stream<String>> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    if (response.statusCode() < 200 || response.statusCode() >= 300) {
        throw new java.io.IOException("HTTP status: " + response.statusCode());
    }

    lines.filter(line -> !line.isBlank())
            .forEach(System.out::println);
}
```

`ofLines()` dùng charset theo quy tắc của `ofString()` và tách dòng theo cách tương tự `BufferedReader.readLine()`. Phải đọc stream đến hết hoặc đóng nó. Nếu dừng sớm mà không đóng, request và tài nguyên kết nối có thể chưa được giải phóng; kết nối cũng có thể không tái sử dụng được.

## 4. Ghi response trực tiếp ra tệp

### 4.1. Dùng ofFile cho file nhị phân hoặc file lớn

`BodyHandlers.ofFile(path)` ghi body vào file và trả `HttpResponse<Path>`. Cách gọi mặc định tương đương `ofFile(path, CREATE, WRITE)`. Nếu ghi đè file đã có và muốn loại bỏ phần đuôi còn sót lại từ file cũ, hãy truyền thêm `TRUNCATE_EXISTING`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;

Path target = Path.of("downloads", "manual.pdf");
Files.createDirectories(target.getParent());
Path temporaryFile = Files.createTempFile(target.getParent(), "manual-", ".part");

try {
    HttpResponse<Path> response = client.send(
            request,
            HttpResponse.BodyHandlers.limiting(
                    HttpResponse.BodyHandlers.ofFile(
                            temporaryFile,
                            StandardOpenOption.CREATE,
                            StandardOpenOption.WRITE,
                            StandardOpenOption.TRUNCATE_EXISTING),
                    50L * 1024 * 1024));

    if (response.statusCode() < 200 || response.statusCode() >= 300) {
        throw new java.io.IOException("Download failed: HTTP " + response.statusCode());
    }

    try {
        Files.move(response.body(), target,
                StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING);
    } catch (AtomicMoveNotSupportedException ex) {
        Files.move(response.body(), target, StandardCopyOption.REPLACE_EXISTING);
    }
} finally {
    Files.deleteIfExists(temporaryFile);
}
```

Ví dụ giới hạn file tải xuống ở 50 MiB. Nếu vượt giới hạn, handler ném `IOException`. Body được ghi vào file tạm; chỉ sau khi response hoàn tất và status hợp lệ, chương trình mới chuyển file tạm sang file đích. Nếu hệ thống file hỗ trợ atomic move, người đọc sẽ không thấy trạng thái file đích bị ghi dở. Khối `finally` xóa file tạm khi có lỗi.

Lưu ý: ví dụ trên dùng `ofFile` trực tiếp nên body lỗi HTTP cũng có thể được ghi vào file trước khi code kiểm tra status. Nếu muốn bỏ body của response lỗi và chỉ mở file khi status thành công, hãy chọn `BodySubscriber` dựa trên `ResponseInfo` như ví dụ tiếp theo.

### 4.2. Chọn subscriber theo status trước khi ghi file

`BodyHandler` được gọi sau khi nhận status và headers, trước khi xử lý body. Ta có thể trả về subscriber ghi file khi status thành công, hoặc subscriber bỏ qua body khi server trả lỗi. Cách này còn cho phép đặt giới hạn byte ngay tại subscriber:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.net.http.HttpResponse;

Path target = Path.of("downloads", "report.bin");
Files.createDirectories(target.getParent());

HttpResponse<Path> response = client.send(request, info -> {
    if (info.statusCode() >= 200 && info.statusCode() < 300) {
        return HttpResponse.BodySubscribers.limiting(
                HttpResponse.BodySubscribers.ofFile(
                        target,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.WRITE,
                        StandardOpenOption.TRUNCATE_EXISTING),
                100L * 1024 * 1024);
    }

    // Vẫn nhận status và headers, nhưng bỏ qua body lỗi.
    return HttpResponse.BodySubscribers.replacing(target);
});

if (response.statusCode() < 200 || response.statusCode() >= 300) {
    throw new IOException("Download failed: HTTP " + response.statusCode());
}
```

Đây là ví dụ tập trung vào cách chọn subscriber. Khi thay file quan trọng, hãy dùng file tạm và bước move sau khi tải thành công thay vì ghi thẳng vào file đích. Nếu server gửi `Content-Length`, có thể kiểm tra trước để từ chối file quá lớn; `limiting` vẫn là lớp bảo vệ chính vì nó đếm số byte thực sự được chuyển tới subscriber.

### 4.3. Dùng tên file từ Content-Disposition

`BodyHandlers.ofFileDownload(directory)` lưu response trong thư mục chỉ định và lấy tên file từ header `Content-Disposition`. Header phải khai báo kiểu `attachment` và tham số `filename`. API chỉ dùng thành phần tên cuối cùng nếu filename chứa nhiều thành phần đường dẫn, nhưng tên file vẫn do server kiểm soát.

Chỉ dùng handler này khi ứng dụng chấp nhận tên do server đề xuất. Kiểm tra thư mục đích, quyền ghi, loại file và chính sách ghi đè; nếu cần tên file cố định hoặc quy tắc đặt tên riêng, dùng `ofFile(path)` với đường dẫn do ứng dụng quyết định. Không ghép filename từ response vào một đường dẫn tùy ý mà chưa kiểm tra.

## 5. Xử lý dữ liệu truyền luồng

### 5.1. ofInputStream cho xử lý theo khối byte

`BodyHandlers.ofInputStream()` trả `HttpResponse<InputStream>` ngay khi headers đã được nhận. Body tiếp tục được đọc khi chương trình gọi `read()`. Điều này hữu ích khi muốn chuyển dữ liệu theo từng khối sang bộ giải mã, parser, bộ ghi file hoặc một pipeline xử lý khác.

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.limiting(
                HttpResponse.BodyHandlers.ofInputStream(),
                100L * 1024 * 1024));

if (response.statusCode() < 200 || response.statusCode() >= 300) {
    try (InputStream errorBody = response.body()) {
        errorBody.transferTo(OutputStream.nullOutputStream());
    }
    throw new java.io.IOException("HTTP status: " + response.statusCode());
}

Path target = Path.of("downloads", "streamed-data.bin");
Files.createDirectories(target.getParent());

try (InputStream body = response.body();
     OutputStream output = Files.newOutputStream(
             target,
             StandardOpenOption.CREATE,
             StandardOpenOption.WRITE,
             StandardOpenOption.TRUNCATE_EXISTING)) {
    byte[] buffer = new byte[16 * 1024];
    int count;
    while ((count = body.read(buffer)) != -1) {
        output.write(buffer, 0, count);
    }
}
```

Vòng lặp chỉ giữ một buffer nhỏ trong bộ nhớ. Thay `output.write(...)` bằng xử lý chunk phù hợp nếu dữ liệu cần được giải mã hoặc phân tích trực tiếp. Luôn đóng `InputStream`, kể cả khi xử lý lỗi hoặc dừng sớm. Đóng stream trước khi đọc đến EOF có thể làm kết nối hiện tại bị đóng thay vì tái sử dụng.

### 5.2. ofPublisher cho Flow API và backpressure

Khi cần tích hợp với pipeline reactive hoặc muốn kiểm soát số lượng chunk được yêu cầu, `BodyHandlers.ofPublisher()` trả về `Flow.Publisher<List<ByteBuffer>>`:

```java
import java.nio.ByteBuffer;
import java.util.List;
import java.util.concurrent.Flow;

HttpResponse<Flow.Publisher<List<ByteBuffer>>> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofPublisher());

if (response.statusCode() < 200 || response.statusCode() >= 300) {
    throw new java.io.IOException("HTTP status: " + response.statusCode());
}

Flow.Publisher<List<ByteBuffer>> publisher = response.body();
publisher.subscribe(mySubscriber);
```

`mySubscriber` là một `Flow.Subscriber<List<ByteBuffer>>` do ứng dụng cài đặt. Subscriber nhận `Subscription` trong `onSubscribe`, gọi `request(n)` khi sẵn sàng xử lý thêm dữ liệu, xử lý từng danh sách buffer trong `onNext`, rồi hoàn tất ở `onComplete` hoặc xử lý lỗi ở `onError`. Cơ chế `request(n)` là backpressure: consumer điều tiết lượng dữ liệu mà publisher gửi tiếp.

Publisher từ `ofPublisher()` chỉ được subscribe một lần. Phải subscribe và yêu cầu dữ liệu đến khi hoàn tất, hoặc gọi `cancel()` nếu không thể tiếp tục. Nếu không, request có thể vẫn mở và tài nguyên của client chưa được giải phóng. Nếu chỉ cần đọc byte theo cách tuần tự, `ofInputStream()` thường đơn giản hơn.

### 5.3. Chuyển dữ liệu văn bản theo dòng tới Flow Subscriber

Nếu nguồn là văn bản dạng dòng, có thể dùng `BodyHandlers.fromLineSubscriber(subscriber)` để adapter body thành các chuỗi dòng. Handler này phù hợp với bộ phân tích log hoặc bộ xử lý NDJSON đã cài đặt `Flow.Subscriber<String>`. Khi dùng overload có `finisher`, giá trị trả về của hàm finisher trở thành `response.body()` sau khi subscriber hoàn tất.

Không dùng `BodyHandlers.ofByteArrayConsumer()` cho consumer xử lý chậm hoặc cần backpressure: API này không flow-controlled, nên consumer phải xử lý kịp lượng dữ liệu được chuyển tới. Với xử lý bất đồng bộ cần điều tiết tốc độ, chọn `ofPublisher()` hoặc tự cài đặt `BodySubscriber` có kiểm soát demand.

## 6. Tạo BodyHandler tùy chỉnh

Một `BodyHandler` tùy chỉnh hữu ích khi cần kết hợp nhiều điều kiện: status code, content type, content length hoặc chính sách dung lượng. Ví dụ dưới đây nhận response JSON thành `String` khi status thành công; với response lỗi, body bị bỏ qua. Cả hai nhánh đều có giới hạn byte:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.net.http.HttpResponse;
import java.util.Locale;

long maxBodyBytes = 2L * 1024 * 1024;

HttpResponse<String> response = client.send(request, info -> {
    String contentType = info.headers()
            .firstValue("Content-Type")
            .orElse("");
    String mediaType = contentType.split(";", 2)[0]
            .trim()
            .toLowerCase(Locale.ROOT);

    boolean success = info.statusCode() >= 200 && info.statusCode() < 300;
    boolean json = mediaType.equals("application/json") || mediaType.endsWith("+json");

    if (success && json) {
        return HttpResponse.BodySubscribers.limiting(
                HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8),
                maxBodyBytes);
    }

    return HttpResponse.BodySubscribers.limiting(
            HttpResponse.BodySubscribers.replacing(""),
            maxBodyBytes);
});

if (response.statusCode() < 200 || response.statusCode() >= 300) {
    throw new IOException("HTTP status: " + response.statusCode());
}
if (response.body().isEmpty()) {
    throw new IOException("Expected a JSON response");
}
```

Trong hệ thống thực tế, kiểm tra `Content-Type` nên xử lý cả tham số như `charset` và các media type JSON có hậu tố `+json` nếu API cho phép. Đoạn code minh họa nguyên tắc chọn subscriber; việc parse JSON vẫn cần thư viện JSON và xử lý lỗi riêng. Nếu endpoint hợp lệ có thể trả JSON rỗng, hãy phân biệt trường hợp đó với việc body bị bỏ qua bằng kiểu kết quả hoặc trạng thái riêng thay vì kiểm tra `isEmpty()`.

## 7. Những lỗi thường gặp và cách tránh

- **Đọc file lớn bằng `ofByteArray()` hoặc `ofString()`.** Dùng `ofFile()`, `ofInputStream()` hoặc `ofPublisher()` để giới hạn bộ nhớ.
- **Quên đóng stream.** Đóng `InputStream` hoặc `Stream<String>` bằng try-with-resources; với publisher, tiêu thụ đến hết hoặc cancel subscription.
- **Giả định handler tự kiểm tra status.** Handler dựng sẵn nhận body ở mọi status. Kiểm tra `statusCode()` hoặc tự chọn subscriber từ `ResponseInfo`.
- **Ghi đè file nhưng thiếu `TRUNCATE_EXISTING`.** File mới ngắn hơn file cũ có thể còn dữ liệu đuôi. Truyền rõ `CREATE`, `WRITE`, `TRUNCATE_EXISTING` khi muốn thay thế nội dung.
- **Không giới hạn body.** Dùng `BodyHandlers.limiting()` cho văn bản, stream hoặc file có kích thước tối đa đã biết.
- **Tin filename từ server.** `Content-Disposition` là dữ liệu bên ngoài; kiểm tra tên file và thư mục đích.
- **Xử lý chunk quá chậm hoặc giữ quá nhiều chunk.** Với Flow API, chỉ `request(n)` khi consumer sẵn sàng; tránh giữ các buffer không cần thiết.
- **Tạo `HttpClient` mới cho mỗi request.** Tái sử dụng một client để tận dụng cấu hình và connection pool của client.

## 8. Quy tắc chọn nhanh cho Java 26

| Tình huống | Lựa chọn khuyến nghị |
|---|---|
| REST API trả JSON nhỏ | `ofString(UTF_8)` kết hợp giới hạn dung lượng và kiểm tra status |
| JSON hoặc văn bản có thể lớn, cần parse theo dòng | `ofLines()` và đóng stream |
| Download file lớn | `ofFile()` hoặc `ofInputStream()` với giới hạn byte; dùng file tạm nếu cần bảo toàn file đích |
| Chuyển byte sang parser hoặc pipeline reactive | `ofPublisher()` và `Flow.Subscriber` có backpressure |
| Response không cần nội dung | `discarding()` |
| Cần chọn cách đọc theo status/header | Custom `BodyHandler` nhận `ResponseInfo` |

`HttpClient`, `BodyHandler` và `BodySubscriber` là API chuẩn từ JDK 11; từng handler cụ thể được bổ sung theo các bản JDK khác nhau. `BodyHandlers.limiting()` và `BodySubscribers.limiting()` là API chuẩn từ JDK 25. Trên JDK 26, các API được giới thiệu trong bài không cần `--enable-preview` hoặc module incubator. Chọn handler theo kích thước và cách tiêu thụ body sẽ giúp ứng dụng sử dụng bộ nhớ có kiểm soát và giải phóng kết nối đúng cách.

## Tài liệu tham khảo

- [Java SE 26 API: HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Java SE 26 API: HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
- [Java SE 26 API: HttpResponse.BodyHandler](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html)
- [Java SE 26 API: HttpResponse.BodySubscriber](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html)
- [Java SE 26 API: HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html)
- [JEP 321: HTTP Client (Standard)](https://openjdk.org/jeps/321)
