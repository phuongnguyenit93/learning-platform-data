# ofFile và upload tệp bằng HttpClient trong Java 11

**Chủ đề cha:** Request body  
**Phạm vi:** `java.net.http.HttpRequest.BodyPublishers.ofFile(Path)`, gửi tệp bằng `HttpClient`, phân biệt raw request body và `multipart/form-data`, xử lý HTTP status, vòng đời tệp, bộ nhớ, lỗi và kiểm thử.

Java 11 cung cấp HTTP Client chuẩn qua module `java.net.http`. Với một endpoint nhận **nguyên nội dung tệp** làm HTTP request body, `HttpRequest.BodyPublishers.ofFile(path)` là lựa chọn trực tiếp: ứng dụng đưa `Path` cho publisher, rồi gắn publisher vào `POST`, `PUT` hoặc một phương thức HTTP được API chấp nhận. Bạn không cần đọc toàn bộ tệp thành `byte[]` trước khi gửi. API này vẫn được dùng trong các phiên bản Java hiện đại.

Nhưng **upload tệp không chỉ có một định dạng**. Một endpoint nhận body thô (`application/octet-stream`, `text/plain`, `application/json`...) khác với endpoint yêu cầu form `multipart/form-data` chứa `Content-Disposition`, `filename` và boundary. `ofFile` chỉ cung cấp **byte nội dung tệp**; nó không tự biến request thành multipart, không tự bổ sung tên tệp hoặc metadata nghiệp vụ. Chọn đúng cách gửi theo **hợp đồng API phía server**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Viết request `PUT` hoặc `POST` với `BodyPublishers.ofFile(Path)` trên Java 11, đặt `Content-Type`, timeout và xử lý response.
2. Giải thích sự khác biệt giữa **request body publisher** (`ofFile`, dùng để upload) và **response body handler** (`BodyHandlers.ofFile`, dùng để tải phản hồi xuống tệp).
3. Phân biệt kích thước theo byte với độ dài chuỗi, tệp 0 byte với tệp không tồn tại, `contentLength()` với kích thước nội dung thực sự cần kiểm tra.
4. Phân biệt upload raw body và multipart; tạo request multipart đúng cú pháp trên Java 11 bằng `ofInputStream` khi endpoint bắt buộc form.
5. Nhận diện lỗi tạo publisher, lỗi khi đọc tệp trong quá trình gửi, lỗi mạng và HTTP 4xx/5xx; thiết kế timeout, retry và quản lý tài nguyên.
6. Kiểm thử upload hoàn toàn trên loopback, so sánh byte ở server và kiểm tra đúng HTTP method, header, body.

## 2. API trọng tâm: `BodyPublishers.ofFile(Path)`

Khai báo Java 11:

```java
public static HttpRequest.BodyPublisher ofFile(Path path)
        throws FileNotFoundException
```

`HttpRequest.BodyPublishers` là lớp chứa các factory tạo `BodyPublisher`. `ofFile` nhận đường dẫn đến tệp và trả một publisher cung cấp byte của tệp cho HTTP request khi gửi. Trên Java 11, `FileNotFoundException` có thể xảy ra ngay tại bước tạo publisher nếu không tìm thấy đường dẫn; lỗi đọc tệp phát sinh về sau, khi thực tế gửi request, vẫn cần xử lý `IOException`.

Ví dụ cấu hình cho endpoint **đã quy định raw bytes** (trích đoạn, cần import và biến `path`/`uri` phù hợp):

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/octet-stream")
        .timeout(Duration.ofSeconds(30))
        .PUT(HttpRequest.BodyPublishers.ofFile(path))
        .build();
```

`ofFile` **không quyết định** HTTP method: `.PUT(publisher)` chọn PUT, `.POST(publisher)` chọn POST, và `.method("PATCH", publisher)` chỉ nên dùng khi endpoint hỗ trợ PATCH với payload đó. Phải lựa chọn theo tài liệu server. PUT thường mang ngữ nghĩa tạo/thay thế tài nguyên tại URI được chỉ định; POST thường yêu cầu server xử lý một tài nguyên hoặc một hành động. Không tự suy rằng mọi upload đều phải là POST.

Các vai trò cần tách rõ:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `Path` | Chỉ đường dẫn tệp local trên máy chạy JVM | `Path.of("data/report.bin")` |
| `BodyPublishers.ofFile(path)` | Cấp byte tệp để **gửi đi** | Body của HTTP request |
| `HttpRequest.Builder.POST/PUT` | Chọn phương thức HTTP và gắn publisher | `.PUT(publisher)` |
| `Content-Type` | Mô tả **loại dữ liệu trong request body** | `application/octet-stream`, `text/plain; charset=UTF-8` |
| `HttpClient.send` / `sendAsync` | Thực thi request đồng bộ / bất đồng bộ | Trả `HttpResponse<T>` hoặc `CompletableFuture<HttpResponse<T>>` |
| `HttpResponse.BodyHandlers.ofString` | Đọc **response body** như văn bản | Nhận thông báo lỗi/xác nhận từ server |
| `HttpResponse.BodyHandlers.ofFile` | Ghi **response body** vào tệp local | Download, hoàn toàn khác `ofFile` bên request |

**Không nhầm `BodyPublishers.ofFile` với `BodyHandlers.ofFile`.** Tên giống nhau nhưng nằm ở hai phía của HTTP exchange: request **upload** và response **download**.

### 2.1 Byte nào thực sự được gửi?

Với raw upload, dữ liệu được gửi là **nội dung tệp**. Tên tệp, đường dẫn local, timestamp, quyền truy cập hoặc field form **không tự xuất hiện** trong request body. Ví dụ tệp UTF-8 chứa `"Xin chào\n"` có:

- `String.length() == 9` ký tự UTF-16 trong ví dụ này.
- Dữ liệu UTF-8 dài **10 byte** vì chữ `à` có hai byte trong UTF-8.
- `Files.size(file) == 10` khi tệp chứa đúng chuỗi đó mã hóa UTF-8.
- `BodyPublishers.ofFile(file).contentLength() == 10` cho tệp ổn định trong ví dụ thực hành.

Kích thước `Content-Length` nếu có được tính theo **byte**, không phải số ký tự của chuỗi Java. Không tự đặt `Content-Length` bằng `text.length()`. Hãy để HTTP client quản lý framing/độ dài từ publisher. Khi không biết trước độ dài, HTTP client có thể chọn framing phù hợp với phiên bản HTTP thực tế.

### 2.2 Publisher khác snapshot nội dung

`ofFile` không phải lời hứa rằng dữ liệu được sao chép thành một mảng bất biến ngay khi gọi factory. Nó cung cấp nội dung tệp trong quá trình gửi. Nếu ứng dụng sửa, thay thế hoặc xóa file sau khi tạo publisher nhưng trước/khi request được gửi, nội dung/độ dài có thể không khớp và upload có thể thất bại. **Giữ tệp ổn định** cho đến khi hoàn tất request, đặc biệt nếu cơ chế gửi lại/đăng ký lại publisher có thể đọc tệp thêm lần nữa.

Đối với yêu cầu cần snapshot nhất quán, hãy tạo snapshot trên disk, kiểm tra hash và làm rõ thời điểm đóng băng dữ liệu. Không dùng `Files.exists(path)` ở một thời điểm rồi coi thao tác đọc trong tương lai chắc chắn thành công; file và quyền truy cập có thể thay đổi giữa hai thời điểm.

## 3. Cách gửi một tệp thô tới endpoint

Đối với một dịch vụ có endpoint nhận body là dữ liệu của file, luồng cơ bản:

```text
Tệp local (Path)
   ↓
HttpRequest.BodyPublishers.ofFile(path)
   ↓
HttpRequest.Builder.PUT/POST(publisher)
   ↓
HttpClient.send(..., responseHandler)
   ↓
Server nhận raw bytes
   ↓
HttpResponse: status + headers + body xác nhận/lỗi
```

Một request minh họa (không phải chương trình độc lập):

```java
Path source = Path.of("data/report.csv");
HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://uploads.example.com/api/report"))
        .header("Content-Type", "text/csv; charset=UTF-8")
        .timeout(Duration.ofMinutes(2))
        .POST(HttpRequest.BodyPublishers.ofFile(source))
        .build();

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

if (response.statusCode() / 100 != 2) {
    throw new IOException("Upload failed: HTTP " + response.statusCode());
}
```

Cần import `URI`, `Path`, `HttpRequest`, `HttpClient`, `HttpResponse`, `StandardCharsets`, `Duration`, `IOException`; phương thức bao quanh phải khai báo hoặc xử lý `FileNotFoundException`, `IOException`, `InterruptedException`. Đường dẫn và URL trong đoạn trên chỉ để **minh họa cấu hình**; đừng gửi file thật đến một endpoint chưa được bạn kiểm soát/xác minh.

**Tại sao kiểm tra status?** HTTP 400/401/413/415/500 thường vẫn trả về một `HttpResponse` bình thường; `HttpClient.send` không tự ném exception chỉ vì mã HTTP không phải 2xx. Cần đọc status, xác minh response schema và áp dụng logic nghiệp vụ.

**Tại sao đặt cả hai timeout?** `connectTimeout` điều khiển thời gian thiết lập kết nối, còn `request.timeout` điều khiển giới hạn thời gian cho request. Hãy chọn giá trị từ SLA và kích thước file; timeout quá ngắn có thể cắt upload hợp lệ, timeout quá dài gây nghẽn tài nguyên khi server không phản hồi.

## 4. Ví dụ chạy độc lập: upload raw bằng PUT trên máy local

Để tránh phụ thuộc dịch vụ Internet hoặc API credential, chương trình sau chạy một server HTTP trên **127.0.0.1** bằng module JDK `jdk.httpserver`, tạo tệp UTF-8 tạm, upload qua `BodyPublishers.ofFile` và kiểm tra **nguyên byte**, HTTP method cùng `Content-Type` ở server. File được xóa và server dừng sau khi request kết thúc.

Đây là test loopback dùng HTTP để dễ quan sát. **Khi upload file thực tế qua mạng, sử dụng HTTPS**, kiểm tra TLS và chính sách xác thực.

Lưu thành **`RawFileUploadDemo.java`**:

```java
import com.sun.net.httpserver.HttpServer;
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

public class RawFileUploadDemo {
    public static void main(String[] args) throws Exception {
        String sample = "Xin chào\n";
        byte[] expected = sample.getBytes(StandardCharsets.UTF_8);
        Path file = Files.createTempFile("upload-raw-", ".txt");
        Files.writeString(file, sample, StandardCharsets.UTF_8);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/raw", exchange -> {
            byte[] actual;
            try (var input = exchange.getRequestBody()) {
                actual = input.readAllBytes();
            }
            boolean accepted = "PUT".equals(exchange.getRequestMethod())
                    && "text/plain; charset=UTF-8".equals(
                            exchange.getRequestHeaders().getFirst("Content-Type"))
                    && Arrays.equals(expected, actual);

            byte[] reply = ("received=" + actual.length
                    + ", matched=" + accepted)
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(accepted ? 201 : 400, reply.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(reply);
            }
        });
        server.start();

        try {
            HttpRequest.BodyPublisher publisher =
                    HttpRequest.BodyPublishers.ofFile(file);

            HttpRequest request = HttpRequest.newBuilder(
                            URI.create("http://127.0.0.1:"
                                    + server.getAddress().getPort() + "/raw"))
                    .header("Content-Type", "text/plain; charset=UTF-8")
                    .timeout(Duration.ofSeconds(10))
                    .PUT(publisher)
                    .build();

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(5))
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

            System.out.println("file-bytes=" + Files.size(file));
            System.out.println("publisher-length=" + publisher.contentLength());
            System.out.println("status=" + response.statusCode());
            System.out.println("body=" + response.body());
        } finally {
            server.stop(0);
            Files.deleteIfExists(file);
        }
    }
}
```

Lệnh biên dịch/chạy trên JDK 11 trở lên có hỗ trợ Java 11:

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 RawFileUploadDemo.java
java --add-modules jdk.httpserver RawFileUploadDemo
```

**Stdout chính xác của lần chạy thành công:**

```text
file-bytes=10
publisher-length=10
status=201
body=received=10, matched=true
```

Diễn giải:

1. `Files.createTempFile` tạo tệp hợp lệ; `Files.writeString(..., UTF_8)` ghi đúng dữ liệu nguồn.
2. `BodyPublishers.ofFile(file)` tạo publisher với `contentLength() == 10`; chương trình không cần `Files.readAllBytes` ở client.
3. Server local nhận request PUT và body byte-for-byte giống dữ liệu mong đợi. Nó trả `201` khi method, `Content-Type` và byte đều đúng, `400` nếu sai.
4. `HttpClient.send` nhận `HttpResponse<String>`; chương trình in status và nội dung body do server tạo.
5. `server.stop(0)` và `Files.deleteIfExists(file)` dọn tài nguyên trong `finally`.

Đây là server **chỉ phục vụ demo**: nó cố ý đọc toàn bộ body vào RAM để so sánh với chuỗi 10 byte. Server sản xuất cần giới hạn kích thước request, xử lý luồng theo từng phần, xác thực người dùng, xác định thư mục được phép ghi và quản lý các request đồng thời.

## 5. Trường hợp tệp 0 byte, không tồn tại hoặc không đọc được

**Tệp rỗng khác tệp không tồn tại.** Một file hợp lệ có kích thước 0 có thể được upload như body rỗng nếu API server chấp nhận. Một đường dẫn không tồn tại lại làm việc tạo `ofFile(path)` thất bại với `FileNotFoundException` trên Java 11. Tệp có thể tồn tại nhưng về sau không đọc được vì quyền truy cập, khóa, thay đổi nội dung hoặc lỗi disk; việc gửi vẫn có thể thất bại qua luồng lỗi I/O.

| Trạng thái | `Files.size` | `BodyPublishers.ofFile` | Điều cần kiểm tra |
|---|---|---|---|
| File tồn tại, 10 byte | 10 | Publisher có độ dài đã biết trong ví dụ | Server nhận đủ, byte chính xác |
| File tồn tại, 0 byte | 0 | Publisher độ dài 0 | Server có cho phép empty upload không? |
| File không tồn tại | Ném lỗi khi đọc size | `FileNotFoundException` khi tạo publisher | Báo rõ missing file |
| File bị xóa sau khi tạo publisher | Có thể có size lúc kiểm tra trước | Request sau đó có thể thất bại | Không coi publisher là snapshot |
| File không có quyền đọc | Phụ thuộc OS/quyền | Có thể lỗi lúc tạo hoặc lúc gửi | Phân biệt lỗi truy cập với HTTP response |
| Server từ chối file quá lớn | File và publisher có thể hợp lệ | Có thể gửi được request nhưng nhận HTTP 413 | Đọc status và chính sách giới hạn |

### Ví dụ độc lập: kiểm thử hai ca biên

Lưu thành **`FilePublisherBoundaryDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.net.http.HttpRequest;
import java.nio.file.Files;
import java.nio.file.Path;

public class FilePublisherBoundaryDemo {
    public static void main(String[] args) throws Exception {
        Path empty = Files.createTempFile("upload-empty-", ".bin");
        Path missing = empty.resolveSibling(
                empty.getFileName().toString() + ".missing");
        try {
            HttpRequest.BodyPublisher publisher =
                    HttpRequest.BodyPublishers.ofFile(empty);
            System.out.println("empty-size=" + Files.size(empty));
            System.out.println("empty-publisher-length="
                    + publisher.contentLength());

            try {
                HttpRequest.BodyPublishers.ofFile(missing);
                System.out.println("missing-file-rejected=false");
            } catch (FileNotFoundException expected) {
                System.out.println("missing-file-rejected=true");
            }
        } finally {
            Files.deleteIfExists(empty);
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 FilePublisherBoundaryDemo.java
java FilePublisherBoundaryDemo
```

```text
empty-size=0
empty-publisher-length=0
missing-file-rejected=true
```

Demo không gửi HTTP request; nó chỉ xác minh hợp đồng factory và chiều dài tệp rỗng. `missing` là đường dẫn không tồn tại được tạo từ tên file tạm mới, nên test không cần xóa file thực của người dùng.

**Nguyên tắc khi báo lỗi:** `FileNotFoundException` và `IOException` là lỗi về nguồn local/truyền tải, còn HTTP 4xx/5xx là server trả một **mã trạng thái**. Không gộp tất cả thành “upload thất bại” mà bỏ mất nguyên nhân, nhất là khi hệ thống cần hướng dẫn người dùng chọn lại file.

## 6. Raw body và multipart/form-data là hai giao thức khác nhau

Một số endpoint nhận **chính nội dung tệp**:

```http
PUT /files/report HTTP/1.1
Content-Type: application/octet-stream

<dãy byte nhị phân của tệp>
```

Đây là minh họa cấu trúc HTTP; các header framing và byte cụ thể do HTTP client quản lý. Với dạng này, `BodyPublishers.ofFile(path)` là lựa chọn phù hợp.

Nhiều API nhận form có trường file, ví dụ tên field `file` và thêm metadata:

```http
POST /upload HTTP/1.1
Content-Type: multipart/form-data; boundary=demo-boundary

--demo-boundary
Content-Disposition: form-data; name="file"; filename="report.txt"
Content-Type: text/plain; charset=UTF-8

<nội dung tệp>
--demo-boundary--
```

Trong dữ liệu truyền thực, các dòng giao thức multipart dùng **CRLF (`\r\n`)**, có phần mở/đóng boundary, header cho từng part và byte file không bị thay đổi. Khối văn bản chỉ giúp hình dung cấu trúc, không phải byte dump hoàn chỉnh.

**Chỉ gọi `ofFile(path)` và thêm header `Content-Type: multipart/form-data` là SAI.** Server cần thấy boundary và các part thực sự trong body. Đặt nhãn multipart cho raw byte sẽ khiến parser server không đọc được file như form field. Tương tự, `ofFile` không tự lấy `file.getFileName()` để thêm `filename`.

### 6.1 Java 11 có API tạo multipart sẵn không?

`HttpRequest.BodyPublishers` của Java 11 **không có factory multipart/form-data tích hợp**. Có hai lựa chọn còn phù hợp:

- Dùng thư viện HTTP/multipart tương thích runtime của dự án, ưu tiên khi cần nhiều field, nhiều file, biểu diễn filename Unicode, streaming, retry và xử lý case phức tạp.
- Khi cần dùng JDK thuần và hiểu giao thức, tạo đúng byte của phần header/boundary, luồng byte file, phần kết thúc, rồi dùng `BodyPublishers.ofInputStream(Supplier<InputStream>)` để cấp toàn bộ chuỗi byte ấy cho HTTP request.

Tránh đưa `BodyPublishers.concat(...)` vào ví dụ cam kết **Java 11**: phương thức này ra đời ở **Java 16**, không biên dịch với `--release 11`. Cách dùng `SequenceInputStream` và `BodyPublishers.ofInputStream` trong ví dụ tiếp theo tương thích Java 11 và vẫn hữu ích với các bản Java sau.

### 6.2 Ví dụ độc lập: upload một part tệp theo multipart/form-data

Đây là ví dụ có chủ đích về byte framing. Nó dùng **một part**, tên field `file`, tên file tĩnh an toàn `hello.txt`, dữ liệu `Xin chào\n` và boundary ngẫu nhiên. `ofInputStream` nhận supplier để có thể mở **luồng mới** nếu HTTP client cần gửi lại body. `SequenceInputStream` ghép lần lượt phần mở, byte tệp và phần đóng; server loopback kiểm tra đúng **toàn bộ byte**.

Lưu thành **`MultipartUploadDemo.java`**:

```java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.SequenceInputStream;
import java.io.UncheckedIOException;
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
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.function.Supplier;

public class MultipartUploadDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("upload-form-", ".txt");
        byte[] data = "Xin chào\n".getBytes(StandardCharsets.UTF_8);
        Files.write(file, data);

        String boundary = "java11-" + UUID.randomUUID();
        String prefix = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"file\";"
                + " filename=\"hello.txt\"\r\n"
                + "Content-Type: text/plain; charset=UTF-8\r\n\r\n";
        String suffix = "\r\n--" + boundary + "--\r\n";
        byte[] prefixBytes = prefix.getBytes(StandardCharsets.UTF_8);
        byte[] suffixBytes = suffix.getBytes(StandardCharsets.UTF_8);
        byte[] expected = new byte[prefixBytes.length + data.length
                + suffixBytes.length];
        System.arraycopy(prefixBytes, 0, expected, 0, prefixBytes.length);
        System.arraycopy(data, 0, expected, prefixBytes.length, data.length);
        System.arraycopy(suffixBytes, 0, expected, prefixBytes.length
                + data.length, suffixBytes.length);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/multipart", exchange -> {
            byte[] actual;
            try (InputStream input = exchange.getRequestBody()) {
                actual = input.readAllBytes();
            }
            boolean ok = "POST".equals(exchange.getRequestMethod())
                    && ("multipart/form-data; boundary=" + boundary).equals(
                            exchange.getRequestHeaders().getFirst("Content-Type"))
                    && Arrays.equals(expected, actual);

            byte[] reply = ("multipart-valid=" + ok)
                    .getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(ok ? 201 : 400, reply.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(reply);
            }
        });
        server.start();

        try {
            Supplier<InputStream> parts = () -> {
                try {
                    return new SequenceInputStream(Collections.enumeration(
                            List.of(new ByteArrayInputStream(prefixBytes),
                                    Files.newInputStream(file),
                                    new ByteArrayInputStream(suffixBytes))));
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            };
            HttpRequest.BodyPublisher publisher =
                    HttpRequest.BodyPublishers.ofInputStream(parts);

            HttpRequest request = HttpRequest.newBuilder(
                            URI.create("http://127.0.0.1:"
                                    + server.getAddress().getPort()
                                    + "/multipart"))
                    .header("Content-Type",
                            "multipart/form-data; boundary=" + boundary)
                    .timeout(Duration.ofSeconds(10))
                    .POST(publisher)
                    .build();

            HttpResponse<String> response = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build()
                    .send(request, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println("publisher-length=" + publisher.contentLength());
            System.out.println("file-bytes=" + data.length);
            System.out.println("status=" + response.statusCode());
            System.out.println("body=" + response.body());
        } finally {
            server.stop(0);
            Files.deleteIfExists(file);
        }
    }
}
```

Lệnh chạy:

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 MultipartUploadDemo.java
java --add-modules jdk.httpserver MultipartUploadDemo
```

Stdout đã kiểm chứng:

```text
publisher-length=-1
file-bytes=10
status=201
body=multipart-valid=true
```

**Các điểm cần hiểu:**

1. `Content-Type` **cấp HTTP request** là `multipart/form-data; boundary=...`; trong body còn có `Content-Disposition` và `Content-Type` **của part file**.
2. `prefix` kết thúc bằng một dòng trống `\r\n\r\n` trước byte file. `suffix` bắt đầu bằng `\r\n` và đóng bằng `--boundary--\r\n`.
3. Server so sánh chính xác byte của toàn bộ multipart body, không chỉ chuỗi text được giải mã; trong môi trường thật nó cần một multipart parser có giới hạn kích thước và quy tắc filename.
4. `ofInputStream` có `contentLength() == -1` vì supplier không công bố kích thước tổng trước. Giá trị `-1` là **độ dài chưa biết**, không phải file rỗng hay upload lỗi. HTTP client chọn framing thích hợp với giao thức được sử dụng.
5. `supplier` có khả năng mở file stream mới khi được gọi. Một lần gửi lại request có thể yêu cầu tạo stream mới; file phải còn tồn tại/ổn định tới khi request hoàn thành. `UncheckedIOException` chỉ giúp đưa checked exception của việc mở stream qua lambda supplier, không có nghĩa lỗi sẽ bị bỏ qua.
6. Ví dụ tạo mảng `expected` ở **server/test** để so sánh chính xác; phía client upload file bằng stream, không gom toàn bộ file vào `byte[]` để gửi.
7. Các chuỗi `boundary`/tên file của ví dụ do chương trình kiểm soát. Trong sản phẩm thực, tên file và field lấy từ người dùng phải được kiểm tra/escape để không thể chèn CR/LF, dấu quote hoặc cấu trúc multipart giả. Với file lớn/nhiều file, nên dùng một thư viện multipart trưởng thành thay vì mở rộng đoạn demo thành parser/serializer tự viết.

## 7. Khi nào chọn loại BodyPublisher nào?

| API Java 11 | Dữ liệu nguồn | Content length | Khi nên chọn |
|---|---|---|---|
| `BodyPublishers.ofFile(path)` | Nguyên nội dung file | Độ dài đã biết nếu file ổn định/đọc được | Raw PUT/POST tệp lên API |
| `BodyPublishers.ofByteArray(bytes)` | `byte[]` có sẵn trong RAM | Đã biết | Payload nhỏ hoặc đã được xử lý thành bytes |
| `BodyPublishers.ofString(text, charset)` | Chuỗi được mã hóa thành byte | Đã biết | JSON/XML/text nhỏ, chọn charset rõ ràng |
| `BodyPublishers.ofInputStream(supplier)` | Luồng mở khi subscriber yêu cầu | Chưa biết, báo `-1` | Multipart streaming tự tạo, nguồn luồng khác |
| `BodyPublishers.fromPublisher(publisher)` | `Flow.Publisher<ByteBuffer>` tùy biến | Có overload chưa biết / biết chính xác | Pipeline streaming tùy biến, kiểm soát backpressure |
| `BodyPublishers.noBody()` | Không có request body | 0 | Endpoint không cần body |

Bảng trên dựa trên API Java 11. Phía nhận response có lựa chọn độc lập: `BodyHandlers.ofString` cho text, `ofByteArray` cho phản hồi nhỏ cần giữ bytes, `ofFile` nếu cần lưu phản hồi thành file, `discarding` nếu body không cần lưu. Không dùng `BodyHandlers.ofFile` để thay cho `BodyPublishers.ofFile`.

**Đừng đọc toàn bộ file lớn bằng `Files.readAllBytes(path)` chỉ để đưa vào `ofByteArray`** nếu mục tiêu đơn giản là raw upload. `ofFile` giảm nhu cầu tự giữ toàn bộ nội dung file trong bộ nhớ ứng dụng. Tuy vậy, việc dùng file publisher không đảm bảo “zero-copy” ở mọi JVM, OS hoặc HTTP version; kiểm thử throughput/bộ nhớ trên workload thật nếu cần tối ưu.

### 7.1 Tệp bất biến trong lúc gửi và lần gửi lại

`BodyPublisher` có thể được subscriber sử dụng lại, ví dụ do cơ chế xác thực, redirect hoặc retry ở tầng cao hơn. Mỗi lần cần gửi nội dung tương ứng, dữ liệu phải nhất quán theo hợp đồng request. Với `ofFile`, hãy giữ file không thay đổi cho đến khi quá trình gửi hoàn tất; nếu cần retry sau đó, xác minh file vẫn đúng phiên bản và payload.

`ofInputStream` nhận một `Supplier<InputStream>` vì cần mở stream mới khi có lần phát lại. Không trả cùng một `InputStream` đã đọc hết ở các lần supplier được gọi; lần tiếp theo sẽ thiếu dữ liệu. Nếu không thể mở lại, thiết kế upload một lần có kiểm soát và quản lý chính sách lỗi/redo riêng.

## 8. Quản lý HTTP status, timeout và retry

### 8.1 Phân nhóm lỗi đúng nguyên nhân

| Tình huống | Lớp lỗi / biểu hiện thường gặp | Hướng xử lý |
|---|---|---|
| Path không tồn tại khi tạo publisher | `FileNotFoundException` | Báo file thiếu, yêu cầu chọn lại hoặc sửa đường dẫn |
| Tệp thay đổi/mất quyền đọc trong lúc gửi | Có thể `IOException` hoặc request thất bại | Giữ bản snapshot ổn định, ghi nhận nguyên nhân |
| Mạng mất hoặc server không nhận request | `IOException` ở `send`; future thất bại khi `sendAsync` | Xác định request có thể đã tới server hay chưa |
| Request bị gián đoạn | `InterruptedException` ở `send` | Truyền tiếp hoặc khôi phục interrupt flag khi đã catch |
| Quá hạn | `HttpTimeoutException`, một lớp của `IOException` | Đặt timeout theo kích thước/SLA; xem lại khả năng retry |
| Server từ chối xác thực | HTTP `401` hoặc `403` | Cập nhật token/quyền theo đúng policy |
| File quá lớn so với API | HTTP `413` | Giảm kích thước/chọn upload nhiều phần nếu API hỗ trợ |
| Server không hỗ trợ Content-Type | HTTP `415` | Dùng đúng raw/multipart và MIME type |
| Server từ chối vì sai hợp đồng | HTTP `400`, `422` tùy API | Xem cấu trúc payload và thông báo server |
| Server hoặc gateway lỗi | HTTP `5xx` | Retry có kiểm soát, xem tính idempotent và trạng thái server |

Status HTTP không được ngầm chuyển thành exception khi dùng `BodyHandlers.ofString`. Với phản hồi thành công, không chỉ dựa vào status: một số API trả ID/ETag/hash hoặc JSON xác nhận; hãy kiểm tra trường đó và nếu cần so checksum/size phía server với nguồn.

### 8.2 Retry một file upload không phải lúc nào cũng an toàn

Nếu request bị timeout **sau khi server đã nhận và xử lý file**, client có thể không biết kết quả cuối. Retry mù quáng một lệnh POST tạo tài nguyên mới có thể tạo **hai bản ghi** hoặc hai lần tính phí. Cách giảm rủi ro:

- Ưu tiên API có ngữ nghĩa idempotent phù hợp, chẳng hạn PUT vào resource URI cố định khi server thực sự thực hiện đúng hợp đồng.
- Nếu API hỗ trợ, dùng idempotency key/request ID duy nhất và chính sách chống xử lý trùng do server xác nhận.
- Phân loại lỗi nào có thể thử lại; chỉ retry có giới hạn với backoff phù hợp. Đừng retry mọi HTTP 4xx.
- Giữ file/snapshot ổn định giữa các lần thử. Gửi lại cùng tên nhưng byte khác nhau là một request nghiệp vụ khác.

Mặc định nên **thận trọng với redirect khi upload**. Theo chính sách HTTP và cấu hình client, redirect có thể đổi method, hoặc chuyển dữ liệu đến URL khác. Chỉ follow redirect khi đích đã được xác thực và hợp đồng API cho phép. Ví dụ dùng `HttpClient.Redirect.NEVER` để tránh tự phát lại body tới vị trí không mong muốn.

### 8.3 `sendAsync` không có nghĩa file upload hoàn tất ngay

`sendAsync(request, handler)` trả `CompletableFuture<HttpResponse<T>>` để có thể kết hợp, hủy, giám sát và chờ ở ranh giới thích hợp. Nó không biến việc gửi file thành tức thời. Khi tương lai hoàn tất với `HttpResponse<String>`, vẫn phải kiểm tra HTTP status; future hoàn tất thành công có thể chứa 4xx/5xx.

Trích đoạn áp dụng với `client`, `request` đã tạo và khi gọi ở phương thức khác:

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

future.thenApply(response -> {
    if (response.statusCode() / 100 != 2) {
        throw new IllegalStateException(
                "Upload status: " + response.statusCode());
    }
    return response.body();
}).thenAccept(System.out::println);
```

Cần import `CompletableFuture`, `HttpResponse` và `StandardCharsets`; đây là **trích đoạn**, chưa định nghĩa vòng đời chờ/kết thúc ứng dụng. Với dịch vụ thực, phải tiếp nhận nhánh hoàn tất lỗi (`exceptionally`/`handle`) và đảm bảo file còn tồn tại cho tới khi future hoàn tất. Hủy future hoặc mất kết nối **không chứng minh** server đã hoàn tác upload.

## 9. Kiểm tra đường dẫn và bảo vệ file

Upload tệp có thể chứa dữ liệu cá nhân, bí mật hoặc nội dung độc hại. Các nguyên tắc còn đúng trong Java hiện đại:

1. **Chọn tệp:** xác nhận path nằm trong phạm vi mà ứng dụng được quyền đọc. Nếu đường dẫn đến từ input bên ngoài, giới hạn directory, kiểm soát symlink/real path khi phù hợp và kiểm tra quyền. `Path.normalize()` một mình không phải cơ chế bảo vệ mọi trường hợp path traversal hoặc symlink.
2. **Kiểm tra kích thước:** dùng `Files.size(path)` khi cần chính sách `maxUploadBytes`; không chỉ tin client UI. Kiểm tra file ổn định, nhận thức rằng file có thể đổi sau kiểm tra.
3. **MIME type:** `Content-Type` phải theo hợp đồng server; đừng chỉ tin đuôi tên file hoặc kết quả `Files.probeContentType` khi mục tiêu là kiểm soát loại dữ liệu an toàn. Server phải xác minh lại.
4. **Nơi gửi:** production dùng HTTPS, xác minh certificate/hostname và danh sách host được phép; không cho URL đến từ dữ liệu không tin cậy điều khiển việc gửi file nội bộ.
5. **Đăng nhập:** cấp token/authorization qua phương thức an toàn của ứng dụng; tránh ghi token, body file hoặc response chứa bí mật vào log.
6. **Multipart filename:** header `filename="..."` là metadata có thể bị lợi dụng; loại bỏ/escape CR, LF, quote, kiểm soát Unicode và không dùng path local đầy đủ. Server không được tin tên file do client gửi để quyết định đường dẫn ghi.
7. **Phía server:** giới hạn request size, số file/part, timeout đọc, dung lượng disk, loại nội dung, quyền tệp, chính sách scan nội dung và phân quyền người dùng phù hợp với rủi ro sản phẩm.
8. **Bản ghi và retry:** dùng request ID/hash khi cần kiểm tra trùng, không lưu bí mật trong URL/query string, kiểm soát việc xóa file tạm và log trạng thái rõ.

Nếu file phải được giữ nguyên từng byte (chữ ký, dữ liệu đã nén, snapshot), không chuyển `Files.readString` rồi `BodyPublishers.ofString` để upload: việc giải mã/mã hóa văn bản có thể thay đổi byte. `ofFile` gửi file raw; việc đổi tên tệp, đặt field multipart hoặc thêm metadata nên thực hiện ở **giao thức**, không sửa bytes một cách âm thầm.

## 10. Ma trận kiểm thử upload tệp

Một ứng dụng đáng tin cần thử cả client, request framing và server validation:

| Ca | Cách chuẩn bị | Điều cần xác minh |
|---|---|---|
| Raw tệp văn bản UTF-8 | `"Xin chào\n"` | Nhận **10 byte**, nội dung đúng và đúng charset |
| Tệp nhị phân | `byte[]{0, -1, 10, 13}` | Server nhận byte `00 FF 0A 0D` đúng thứ tự |
| Tệp 0 byte | File hiện hữu, `Files.size == 0` | Upload hợp lệ hoặc lỗi nghiệp vụ rõ ràng |
| File không tồn tại | Path mới không có file | `FileNotFoundException` được xử lý |
| File không đọc được | Thay quyền hoặc xóa sau khi tạo publisher | Không coi mất file là HTTP 2xx |
| Đúng HTTP method | Endpoint yêu cầu PUT | Phải thực sự gửi PUT, không chỉ POST |
| Đúng Content-Type | Server yêu cầu `application/pdf` hoặc loại khác | Header khớp đặc tả |
| Raw vs multipart | Endpoint đòi `multipart/form-data` | Có boundary, các part và filename hợp lệ |
| File lớn | Lớn hơn giới hạn của server | HTTP 413 và thông báo có ích |
| Network timeout | Server cố ý trì hoãn | Không treo vô hạn; lỗi được ghi nhận |
| HTTP 401/403/415/5xx | Server test trả status tương ứng | Phân loại status, không coi response là success |
| Redirect | Server trả 30x sang host khác | Không rò rỉ payload ngoài domain đã tin |
| Retry request | Server đã xử lý rồi trả lỗi giả | Không sinh thao tác trùng không kiểm soát |
| Payload sửa giữa các lần gửi | File thay đổi sau khi tạo publisher | Có chính sách giữ snapshot; phát hiện mismatch |
| Cleanup | Request thành công/lỗi/timeout | Đóng tài nguyên và xóa file tạm khi không cần |

Với test tích hợp, dùng server local trên loopback như ví dụ hoặc test HTTP server của dự án, so sánh **byte** và cấu trúc request thực tế. Đừng chỉ khẳng định phương thức xây dựng `HttpRequest` không ném exception: cần chứng minh server thật sự nhận nội dung đúng. Với các test liên quan mạng, đừng dựa vào độ trễ giả định; dùng tín hiệu đồng bộ, timeout chẩn đoán và input ổn định.

## 11. Các lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách đúng |
|---|---|---|
| Dùng `ofFile` cho endpoint yêu cầu multipart nhưng chỉ thêm header multipart | Body thiếu boundary/part header | Chọn đúng multipart publisher hoặc thư viện |
| Gán `Content-Type` theo đuôi file mà không đối chiếu API | Server có thể trả 415 hoặc diễn giải sai | Theo hợp đồng server, xác minh nội dung |
| Nghĩ `ofFile` gửi cả tên file và đường dẫn | Raw body chỉ chứa byte tệp | Truyền metadata qua API được server quy định |
| Tạo file publisher rồi thay/xóa tệp trước khi send | Body có thể đổi hoặc lỗi đọc | Giữ tệp ổn định tới khi upload xong |
| Tính Content-Length bằng `String.length()` | Ký tự Unicode không luôn 1 byte UTF-8 | Tính theo byte; để client quản lý framing |
| Dùng `Files.readAllBytes` cho mọi file lớn | Có thể ngốn RAM | Dùng `ofFile` hoặc publisher streaming |
| Không đọc response status | HTTP 4xx/5xx vẫn có response | Kiểm tra status và body xác nhận |
| Retry POST ngay sau timeout mà không hỏi server | Có thể tạo hai bản ghi | Idempotency key hoặc thao tác/idempotency rõ |
| Tự follow redirect không kiểm soát | Có thể đổi method hoặc gửi file sang host khác | Chính sách redirect tường minh |
| Dùng một InputStream đã đọc hết trong supplier | Lần gửi lại không còn byte | Mỗi lần supplier trả một stream mới |
| Không có timeout/giới hạn kích thước | Treo request hoặc tiêu tốn tài nguyên | Deadline và quota theo chính sách |
| Nhầm `BodyHandlers.ofFile` là API upload | Đây là API lưu phản hồi | Upload dùng `BodyPublishers.ofFile` |
| Không đóng tài nguyên/phá vòng đời tệp tạm | Rò rỉ file handle, xóa quá sớm hoặc để file nhạy cảm lại | Cleanup sau khi send/future hoàn tất |
| Tự xây multipart với CRLF sai hoặc thiếu boundary đóng | Server không parse được | Dùng serializer đã test, đúng framing |
| Chèn filename người dùng vào header không escape | Có nguy cơ sai cấu trúc hoặc header injection | Kiểm tra và encode/escape theo chuẩn |

## 12. Câu hỏi thực hành có đáp án

**Bài 1 — raw và multipart.** Một REST endpoint yêu cầu `PUT /files/42` với body `application/octet-stream`. Cần `ofFile` hay tự thêm multipart?  
**Đáp án:** dùng `BodyPublishers.ofFile(path)` trực tiếp, đặt `Content-Type` đúng; không thêm boundary nếu server không yêu cầu.

**Bài 2 — file form.** Server đòi `multipart/form-data` với `name="document"` và `filename`. Bạn gọi `.POST(ofFile(path))` rồi đặt `Content-Type: multipart/form-data`; điều gì sai?  
**Đáp án:** body vẫn chỉ là nội dung file; không có delimiter, `Content-Disposition` và metadata của part. Phải tạo multipart đúng chuẩn hoặc dùng thư viện.

**Bài 3 — Unicode length.** Tệp UTF-8 có chuỗi `"Xin chào\n"`. `String.length()` là 9, nhưng file size là 10. Có nên set Content-Length bằng 9?  
**Đáp án:** không. HTTP body length tính bằng byte; để HTTP client quản lý length theo publisher.

**Bài 4 — không có file.** `BodyPublishers.ofFile(path)` ném `FileNotFoundException`. Có nên tự thay bằng `BodyPublishers.noBody()` rồi upload?  
**Đáp án:** chỉ khi yêu cầu nghiệp vụ thực sự cho phép **không có file**. Nếu file bắt buộc, phải báo lỗi thay vì âm thầm gửi body rỗng.

**Bài 5 — server trả 415.** `send` trả `HttpResponse` status 415 mà không ném `IOException`. Có lỗi ở HttpClient không?  
**Đáp án:** không. Đó là phản hồi HTTP; cần kiểm tra Content-Type và dạng body theo hợp đồng endpoint.

**Bài 6 — multipart length.** Ví dụ `ofInputStream(supplier)` trả `contentLength() == -1`. Có nghĩa file không có dữ liệu?  
**Đáp án:** không. Đây là **độ dài body chưa biết**, không phải 0; demo vẫn gửi được file 10 byte cộng multipart framing.

**Bài 7 — retry.** Client timeout sau khi gửi xong request POST, server có thể đã tạo tài nguyên. Có nên gửi lại ngay không?  
**Đáp án:** chỉ khi có chiến lược chống trùng, ví dụ idempotency key do server hỗ trợ hoặc tra trạng thái request trước.

**Bài 8 — file thay đổi.** Một thread tạo publisher từ path, thread khác ghi đè file trong lúc upload. Dữ liệu upload có còn chắc chắn là snapshot ban đầu?  
**Đáp án:** không có bảo đảm như vậy. Giữ file bất biến tới khi hoàn tất hoặc dùng snapshot đã xác minh.

**Bài 9 — bảo mật.** Input người dùng quyết định cả đường dẫn source và URL upload. Bạn cần xác minh gì trước?  
**Đáp án:** phạm vi file được phép đọc, real path/symlink, kích thước, loại nội dung và danh sách server được phép nhận dữ liệu qua HTTPS; không gửi file nội bộ tới URL tùy ý.

## 13. Tài liệu chính thức

- [Java SE 11 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): `ofFile`, `ofInputStream`, `ofByteArray`, `noBody` và các publisher cơ bản.
- [Java SE 11 — HttpRequest](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html): builder, method, timeout và `BodyPublisher`.
- [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, redirect, kết nối.
- [Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): cách xử lý response body, trong đó có `ofFile` cho download.
- [Java SE 11 — Files](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html): `size`, `newInputStream`, `createTempFile` và thao tác file.
- [Java SE 11 — HttpServer](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): HTTP server nhẹ dùng trong ví dụ loopback.
- [RFC 7578 — multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578): boundary, `Content-Disposition`, filename và cấu trúc part.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ý nghĩa các method và status của HTTP.

**Nguyên tắc áp dụng:** Trước khi viết request, xác định **server cần raw body hay multipart**, method và kiểu dữ liệu nào. Với raw bytes, `BodyPublishers.ofFile(Path)` là API ngắn gọn, có giá trị lâu dài. Với form upload, xây đúng framing hoặc dùng thư viện; trong mọi trường hợp kiểm tra byte, status, chính sách file, timeout và retry thay vì giả định gửi request không lỗi đồng nghĩa upload thành công.