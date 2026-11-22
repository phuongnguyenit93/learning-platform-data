# Tích hợp HTTP client, file I/O và dịch vụ bên ngoài

Một quy trình backend thường phải đọc file, gửi dữ liệu tới dịch vụ HTTP bên ngoài, nhận kết quả rồi lưu file hoặc metadata về máy chủ. Java 21 cho phép viết luồng này theo phong cách tuần tự bằng các API blocking quen thuộc: `HttpClient.send`, `Files`, `InputStream` và `OutputStream`. Khi request chạy trên virtual thread, lời gọi mạng blocking có thể tạm dừng virtual thread để carrier phục vụ tác vụ khác.

Điều đó không có nghĩa mọi loại I/O đều có cùng cách lập lịch. Trong Java 21, nhiều thao tác file system có thể giữ carrier trong lúc chờ; runtime có thể bù bằng cách mở rộng số carrier thread. Vì vậy, cần thiết kế vòng đời tài nguyên, giới hạn tải, timeout và cách ghi file cẩn thận.

## 1. Luồng tích hợp thường gặp

Một request có thể thực hiện các bước sau:

1. Xác thực request và kiểm tra quyền truy cập file.
2. Đọc file nhỏ hoặc mở stream cho file lớn.
3. Gửi file hoặc metadata đến một dịch vụ HTTP.
4. Kiểm tra HTTP status và nội dung response.
5. Lưu response vào file tạm, kiểm tra kết quả rồi chuyển sang vị trí đích.
6. Ghi nhận trạng thái hoàn tất và trả response cho caller.

~~~text
Client request
      |
      v
Validate input and file access
      |
      v
Read local file / open stream
      |
      v
HTTP request to external service
      |
      v
Check status, headers and response
      |
      v
Write temporary file
      |
      v
Validate and move to destination
      |
      v
Return result
~~~

Các bước phụ thuộc nhau vẫn được viết tuần tự. Khi request được xử lý trên virtual thread, thao tác mạng blocking có thể unmount virtual thread khỏi carrier. Những request khác tiếp tục chạy trong lúc request hiện tại chờ.

Virtual thread không tự biến các bước tuần tự thành song song. Nếu nhiều lời gọi độc lập cần chạy đồng thời, hãy thiết kế concurrency riêng và kiểm soát số lời gọi tới dịch vụ downstream.

## 2. Dùng lại HttpClient cho nhiều request

`HttpClient` trong Java 21 là immutable sau khi được tạo và có thể gửi nhiều request. Mỗi client thường quản lý connection pool riêng; tạo một client mới cho mỗi request sẽ làm giảm khả năng tái sử dụng connection.

Tạo client ở phạm vi ứng dụng hoặc service:

~~~java
static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(3))
    .followRedirects(HttpClient.Redirect.NORMAL)
    .build();
~~~

`connectTimeout` giới hạn thời gian thiết lập một kết nối mới. Nếu client tái sử dụng kết nối đã có, connect timeout không áp dụng cho request đó. Timeout cho từng request được đặt trên `HttpRequest.Builder`:

~~~java
HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://files.example.com/api/import"))
    .timeout(Duration.ofSeconds(20))
    .header("Accept", "application/json")
    .GET()
    .build();

HttpResponse<String> response = HTTP_CLIENT.send(
    request,
    HttpResponse.BodyHandlers.ofString()
);
~~~

`send` là lời gọi đồng bộ: nó chờ request được gửi và response được nhận. Nếu bị interrupt, phương thức ném `InterruptedException`. Nếu lỗi truyền tải xảy ra, nó có thể ném `IOException`.

Cần nhớ rằng HTTP status 4xx hoặc 5xx không tự động trở thành exception. Sau khi nhận response, ứng dụng phải kiểm tra `statusCode()` và quyết định cách xử lý.

## 3. Chọn BodyHandler theo kích thước response

Response handler quyết định cách body được tiêu thụ. Chọn kiểu phù hợp giúp tránh giữ dữ liệu lớn trong heap.

| BodyHandler | Cách nhận body | Phù hợp khi |
|---|---|---|
| `ofString()` | Đọc toàn bộ body thành String | JSON nhỏ, thông báo hoặc response văn bản ngắn |
| `ofByteArray()` | Đọc toàn bộ body thành byte array | Payload nhị phân nhỏ và có giới hạn kích thước |
| `ofInputStream()` | Trả InputStream khi đã nhận headers; body được đọc dần | Muốn tự kiểm tra status rồi stream/copy |
| `ofFile(path)` | Ghi body trực tiếp vào file | Download file, tránh giữ toàn bộ body trong heap |
| `ofLines()` | Cung cấp Stream các dòng | Response dạng text theo dòng; phải đóng stream |

Không nên dùng `ofString()` hoặc `ofByteArray()` cho file lớn nếu không có giới hạn dung lượng rõ ràng. Khi dùng `ofInputStream()`, phải đọc tới EOF hoặc đóng stream để giải phóng tài nguyên của HTTP exchange.

Ví dụ nhận response dạng stream:

~~~java
HttpResponse<InputStream> response = HTTP_CLIENT.send(
    request,
    HttpResponse.BodyHandlers.ofInputStream()
);

try (InputStream body = response.body()) {
    if (response.statusCode() / 100 != 2) {
        throw new IOException(
            "Dịch vụ trả HTTP " + response.statusCode()
        );
    }

    Files.copy(body, destination, StandardCopyOption.REPLACE_EXISTING);
}
~~~

Trong ví dụ này, body được đóng dù copy thành công hay ném exception. Với dữ liệu lớn, có thể copy sang file tạm rồi chuyển sang file đích sau khi hoàn tất, để file đích không xuất hiện dưới dạng nội dung tải dở.

## 4. Upload file bằng BodyPublishers.ofFile

`HttpRequest.BodyPublishers.ofFile(path)` tạo request body từ nội dung file. Cách này phù hợp khi cần gửi file lên dịch vụ ngoài mà không cần đọc toàn bộ file thành một byte array trước.

~~~java
static HttpResponse<String> uploadFile(
        Path source,
        URI endpoint)
        throws IOException, InterruptedException {

    if (!Files.isRegularFile(source) || !Files.isReadable(source)) {
        throw new IOException("File nguồn không tồn tại hoặc không đọc được");
    }

    HttpRequest request = HttpRequest.newBuilder(endpoint)
        .timeout(Duration.ofMinutes(2))
        .header("Content-Type", "application/octet-stream")
        .header("Accept", "application/json")
        .PUT(HttpRequest.BodyPublishers.ofFile(source))
        .build();

    HttpResponse<String> response = HTTP_CLIENT.send(
        request,
        HttpResponse.BodyHandlers.ofString()
    );

    if (response.statusCode() / 100 != 2) {
        throw new IOException(
            "Upload thất bại, HTTP " + response.statusCode()
        );
    }

    return response;
}
~~~

Ví dụ dùng PUT vì endpoint được giả định hỗ trợ thay thế hoặc lưu tài nguyên theo semantics của PUT. Nếu API yêu cầu POST hoặc multipart form, hãy chọn method và body publisher đúng theo hợp đồng của dịch vụ.

Trước khi upload, cần kiểm tra quyền truy cập file, kích thước tối đa và loại nội dung. Giữ file nguồn ổn định và không xóa hoặc sửa nó cho tới khi `send` hoàn tất. Không nên tin MIME type do client tự khai báo; nếu dịch vụ yêu cầu kiểm tra nội dung, hãy xác minh bằng quy tắc của hệ thống.

## 5. Download trực tiếp vào file

Với response lớn, `BodyHandlers.ofFile` ghi body vào file thay vì tạo một String hoặc byte array lớn trong heap. Body hoàn tất trước khi `send` trả về response.

Ví dụ đơn giản:

~~~java
Path directory = Path.of("downloads");
Files.createDirectories(directory);
Path downloaded = Files.createTempFile(directory, "report-", ".pdf");

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://files.example.com/reports/current"))
    .timeout(Duration.ofMinutes(2))
    .header("Accept", "application/pdf")
    .GET()
    .build();

HttpResponse<Path> response = HTTP_CLIENT.send(
    request,
    HttpResponse.BodyHandlers.ofFile(downloaded)
);

if (response.statusCode() / 100 != 2) {
    Files.deleteIfExists(downloaded);
    throw new IOException(
        "Download thất bại, HTTP " + response.statusCode()
    );
}
~~~

Ví dụ này tạo một tên file mới để body lỗi không ghi đè một bản report đã tồn tại. Trong ứng dụng thực tế, cần xóa file tạm nếu lời gọi `send` hoặc ghi body ném exception; mục tiếp theo minh họa đầy đủ vòng đời đó.

BodyHandler ghi body trước khi ứng dụng kiểm tra status, vì vậy response lỗi cũng có thể đã được ghi vào file. Nếu cần giữ file đích cũ nguyên vẹn cho đến khi download thành công, hãy ghi vào file tạm rồi chuyển file đó sau khi kiểm tra status.

## 6. Ghi file tạm trước khi thay thế file đích

Một quy trình an toàn hơn là ghi response vào file tạm trong cùng thư mục với file đích. Sau khi nhận response thành công, chuyển file tạm sang tên đích. Nếu request hoặc ghi file thất bại, file đích hiện có không bị ghi dở bởi body tải về.

~~~java
static Path downloadToFile(
        URI uri,
        Path destination)
        throws IOException, InterruptedException {

    Path target = destination.toAbsolutePath();
    Path directory = target.getParent();

    Files.createDirectories(directory);

    Path temporary = Files.createTempFile(
        directory,
        ".download-",
        ".part"
    );

    boolean completed = false;

    try {
        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofMinutes(2))
            .header("Accept", "application/octet-stream")
            .GET()
            .build();

        HttpResponse<Path> response = HTTP_CLIENT.send(
            request,
            HttpResponse.BodyHandlers.ofFile(
                temporary,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING
            )
        );

        if (response.statusCode() / 100 != 2) {
            throw new IOException(
                "Download thất bại, HTTP " + response.statusCode()
            );
        }

        Files.move(
            temporary,
            target,
            StandardCopyOption.REPLACE_EXISTING
        );

        completed = true;
        return target;
    } finally {
        if (!completed) {
            Files.deleteIfExists(temporary);
        }
    }
}
~~~

File tạm nằm trong cùng thư mục với file đích để thường ở cùng file store. `Files.move` với `REPLACE_EXISTING` thay file đích khi provider hỗ trợ. Nếu cần bảo đảm chuyển file nguyên tử, có thể yêu cầu `ATOMIC_MOVE`; thao tác này có thể không được file system hỗ trợ, và hành vi khi file đích đã tồn tại phụ thuộc implementation. Không được giả định mọi file system đều hỗ trợ atomic replacement.

Trong môi trường nhiều request, cần tránh hai request cùng ghi vào một tên đích mà không có quy tắc phối hợp. Có thể dùng tên file theo request ID, version hoặc cơ chế khóa ở tầng nghiệp vụ.

## 7. Đọc và ghi file bằng Files

Với file văn bản nhỏ, `Files.readString` và `Files.writeString` là cách ngắn gọn:

~~~java
String metadata = Files.readString(
    Path.of("config", "metadata.json"),
    StandardCharsets.UTF_8
);

Files.writeString(
    Path.of("work", "metadata-copy.json"),
    metadata,
    StandardCharsets.UTF_8,
    StandardOpenOption.CREATE,
    StandardOpenOption.TRUNCATE_EXISTING,
    StandardOpenOption.WRITE
);
~~~

`Files.readString(path)` mặc định dùng UTF-8. API này đọc toàn bộ nội dung vào một String và được thiết kế cho trường hợp đơn giản; tài liệu Java SE 21 không khuyến nghị dùng nó cho file rất lớn.

Với file lớn, đọc theo luồng:

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        Path.of("logs", "application.log"),
        StandardCharsets.UTF_8)) {

    String line;
    while ((line = reader.readLine()) != null) {
        processLine(line);
    }
}
~~~

Ghi dữ liệu theo luồng:

~~~java
try (BufferedWriter writer = Files.newBufferedWriter(
        Path.of("work", "result.txt"),
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE)) {

    writer.write("Đã xử lý");
    writer.newLine();
}
~~~

Đóng reader/writer bằng try-with-resources để flush và giải phóng tài nguyên đúng lúc. Nếu dùng `Files.lines(path)`, hãy đóng Stream bằng try-with-resources vì stream này giữ file mở trong lúc duyệt.

## 8. File I/O và virtual thread trên Java 21

HTTP socket I/O của JDK thường cho phép virtual thread unmount khỏi carrier trong khi chờ mạng. File system I/O có đặc tính khác trên Java 21.

Nhiều thao tác file I/O trong JDK 21 có thể chặn carrier thread thay vì unmount virtual thread. Scheduler có thể bù bằng cách tạm thời tạo thêm carrier thread để giữ khả năng thực thi các virtual thread khác. Đây là cơ chế bù của runtime, không có nghĩa file I/O trở thành non-blocking hoặc không giới hạn tài nguyên.

Vì vậy:

- Không suy luận rằng mọi lời gọi blocking đều giải phóng carrier.
- Đo workload có nhiều thao tác đọc/ghi file, nhất là trên filesystem mạng hoặc storage chậm.
- Giữ thời gian mở file và thời gian giữ buffer ở mức cần thiết.
- Với file I/O khối lượng lớn, cân nhắc executor riêng có giới hạn concurrency để bảo vệ scheduler và storage.
- Không tạo thêm một platform thread cho mỗi thao tác file; nếu cần giới hạn, dùng một executor có số worker và hàng đợi được kiểm soát.

Virtual thread vẫn hữu ích để tổ chức request có nhiều bước I/O. Nhưng năng lực đọc/ghi file phụ thuộc filesystem, thiết bị lưu trữ, dung lượng buffer và cơ chế triển khai của JDK.

## 9. Quản lý timeout và deadline

Một quy trình tích hợp có nhiều điểm có thể chờ: mở kết nối, upload, chờ dịch vụ xử lý, download response và ghi file. Cần đặt timeout theo từng ranh giới.

| Ranh giới | Cấu hình |
|---|---|
| Thiết lập kết nối HTTP mới | `HttpClient.Builder.connectTimeout` |
| Toàn bộ HTTP request | `HttpRequest.Builder.timeout` |
| Đọc response dạng stream | Đọc body có kiểm soát, đóng stream khi hủy hoặc không dùng nữa |
| Đọc/ghi file | Kiểm soát dung lượng, thời gian xử lý và cancellation theo khả năng API/file system |
| Toàn bộ nghiệp vụ | Deadline tổng thể do ứng dụng/server quản lý |

Connect timeout chỉ có tác dụng khi cần tạo kết nối mới. Request timeout áp dụng cho request cụ thể. Một deadline nghiệp vụ tổng thể cần tính cả thời gian xếp hàng, file I/O, HTTP và xử lý kết quả; không nên cộng các timeout riêng thành một thời gian chờ vô hạn.

Nếu request bị hủy hoặc thread bị interrupt, hãy truyền tín hiệu hủy lên tầng gọi khi có thể. Đóng stream và channel đang mở để giải phóng tài nguyên. Không giả định mọi driver, filesystem hoặc thao tác native đều dừng tức thời chỉ vì virtual thread bị interrupt.

## 10. Xử lý status, retry và lỗi từ dịch vụ ngoài

`HttpClient.send` trả về response cho cả status thành công lẫn status lỗi HTTP. Ứng dụng cần kiểm tra status code trước khi xem body là kết quả nghiệp vụ hợp lệ.

Các nguyên tắc thực tế:

- Với 2xx, xác minh body, content type, kích thước và checksum nếu nghiệp vụ yêu cầu.
- Với 4xx, thường xử lý như lỗi request hoặc quyền truy cập; không retry tự động một cách mù quáng.
- Với 429 hoặc 503, xem xét header `Retry-After` và chính sách retry có giới hạn.
- Với timeout hoặc lỗi kết nối, chỉ retry khi request có thể lặp an toàn.
- Với POST tạo tài nguyên hoặc thanh toán, dùng idempotency key theo hợp đồng API để tránh tạo tác dụng phụ trùng lặp.
- Dùng backoff có giới hạn và jitter; tránh retry liên tục khiến dịch vụ đang lỗi chịu thêm tải.
- Không ghi token, cookie, thông tin xác thực hoặc dữ liệu nhạy cảm vào log.

Nếu dịch vụ trả lỗi, file tạm phải được đóng và xóa. Không chuyển file lỗi thành file kết quả chính thức.

## 11. Kiểm tra đường dẫn và nội dung file

Tên file hoặc đường dẫn đến từ request hay header của dịch vụ ngoài phải được xem là dữ liệu không đáng tin cậy.

- Không nối trực tiếp chuỗi do người dùng gửi vào thư mục lưu trữ.
- Chuẩn hóa đường dẫn và kiểm tra nó vẫn nằm trong thư mục gốc được phép.
- Không dùng nguyên filename trong `Content-Disposition` làm đường dẫn đích mà chưa xác thực.
- Đặt giới hạn kích thước upload/download và dung lượng lưu trữ.
- Kiểm tra content type, phần mở rộng và nội dung thực tế theo yêu cầu của ứng dụng.
- Dùng thư mục có quyền truy cập phù hợp; tránh để file tạm hoặc file upload nhạy cảm có thể được phục vụ công khai.
- Xóa file tạm khi thất bại và có cơ chế dọn file tạm còn sót sau sự cố process.

Ví dụ kiểm tra một tên file đơn giản trước khi tạo đường dẫn:

~~~java
static Path resolveInside(Path root, String fileName)
        throws IOException {

    Path base = root.toRealPath();
    Path target = base.resolve(fileName).normalize();

    if (!target.startsWith(base)) {
        throw new SecurityException("Đường dẫn nằm ngoài thư mục cho phép");
    }

    return target;
}
~~~

Trong hệ thống có thể có symbolic link hoặc thay đổi đường dẫn đồng thời, chỉ kiểm tra normalize/startsWith có thể chưa đủ để ngăn mọi tình huống race hoặc traversal qua link. Với dữ liệu không tin cậy, nên dùng tên file do server tạo và kiểm soát thư mục lưu trữ.

## 12. Lựa chọn API theo kích thước và mục tiêu

| Nhu cầu | API gợi ý |
|---|---|
| Gọi API ngoài và nhận JSON nhỏ | `HttpClient.send` + `BodyHandlers.ofString` |
| Gửi file lên dịch vụ | `BodyPublishers.ofFile` |
| Tải file lớn về đĩa | `BodyHandlers.ofFile` |
| Kiểm tra status trước khi tự copy body | `BodyHandlers.ofInputStream` + try-with-resources |
| Đọc file văn bản nhỏ | `Files.readString` |
| Đọc file lớn theo dòng | `Files.newBufferedReader` hoặc `Files.lines` có đóng stream |
| Ghi file văn bản nhỏ | `Files.writeString` |
| Ghi file lớn theo luồng | `Files.newBufferedWriter` hoặc stream/channel |
| Tránh file đích chứa dữ liệu tải dở | Tải vào file tạm rồi move sau khi xác thực |

## 13. Checklist triển khai

- [ ] Dùng một HttpClient dùng chung cho nhiều request.
- [ ] Đặt connect timeout và request timeout.
- [ ] Chọn BodyHandler theo kích thước response; tránh giữ file lớn trong heap.
- [ ] Đóng InputStream, reader, writer và channel bằng try-with-resources.
- [ ] Dùng BodyPublishers.ofFile cho upload file phù hợp.
- [ ] Download vào file tạm và chỉ chuyển sang file đích sau khi status hợp lệ.
- [ ] Kiểm tra HTTP status; không xem mọi response là thành công.
- [ ] Retry có giới hạn và chỉ khi request có thể lặp an toàn.
- [ ] Kiểm soát filename, đường dẫn, kích thước và content type từ nguồn không tin cậy.
- [ ] Đo tác động file I/O lên carrier, storage và heap khi chạy Java 21.
- [ ] Dùng admission control hoặc executor giới hạn khi khối lượng file I/O có thể vượt năng lực storage.
- [ ] Có cơ chế xóa file tạm và xử lý request bị hủy.

## Tài liệu tham khảo chính thức

- [Java SE 21 API — HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 21 API — HttpClient.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java SE 21 API — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java SE 21 API — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [Java SE 21 API — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Java SE 21 API — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [Java SE 21 API — FileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html)
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [Oracle Java 21 Core Libraries — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Dev.java — Virtual Threads and Pinning](https://dev.java/learn/new-features/virtual-threads/)

