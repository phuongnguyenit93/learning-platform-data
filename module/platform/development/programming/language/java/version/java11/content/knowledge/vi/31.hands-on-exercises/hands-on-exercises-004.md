# Upload và download tệp lớn bằng HTTP body streaming (Java 11)

## 1. Mục tiêu của bài thực hành

Khi một tệp có dung lượng hàng trăm MB hoặc vài GB, cách đọc toàn bộ tệp vào byte[] rồi mới gửi HTTP, hoặc nhận toàn bộ HTTP response vào byte[], dễ làm tăng mạnh heap và gây OutOfMemoryError. **Body streaming** xử lý tệp theo từng khối byte ngay khi dữ liệu được đọc/gửi/nhận, thay vì đợi có toàn bộ nội dung.

Sau bài này, bạn có thể:

- Upload file dạng raw HTTP body bằng **java.net.http.HttpClient** và **HttpRequest.BodyPublishers.ofFile(Path)** (Java 11).
- Download file bằng **HttpResponse.BodyHandlers.ofInputStream()**, kiểm tra HTTP status trước khi ghi, rồi lưu vào tệp tạm.
- Viết HTTP server minh họa sử dụng **HttpExchange.getRequestBody()** / **getResponseBody()** để xử lý stream ở hai chiều.
- Xử lý đóng tài nguyên, giới hạn dung lượng, lỗi truyền dở, kiểm tra số byte/kiểm tra SHA-256 và đổi tên file khi hoàn tất.
- Biết khi nào cần multipart/form-data, backpressure, retry/idempotency hoặc giao thức resumable.

Các API chính trong bài có mặt từ Java 11 và vẫn được sử dụng trong các bản Java hiện đại. Mã được viết để biên dịch bằng **javac --release 11**, không dùng API mới chỉ có từ Java 16/17/21.

## 2. Cơ chế streaming từ client đến server

~~~text
UPLOAD:
tệp nguồn -> HttpRequest.BodyPublisher -> HTTP request body
           -> server InputStream -> tệp .part -> tệp đã upload

DOWNLOAD:
tệp trên server -> server OutputStream -> HTTP response body
                 -> BodyHandler / client InputStream -> tệp .part -> file tải xong
~~~

Một vòng lặp đọc/ghi với bộ đệm 64 KiB không cần giữ toàn bộ file trong bộ nhớ:

~~~java
// Snippet dùng trong một phương thức đã có InputStream in, OutputStream out.
byte[] buffer = new byte[64 * 1024];
int n;
while ((n = in.read(buffer)) != -1) {
    out.write(buffer, 0, n);
}
~~~

Độ phức tạp bộ nhớ của phần sao chép do ta viết là **O(kích thước buffer)**, không tăng tỷ lệ thuận theo kích thước file. Tuy nhiên HttpClient, TCP/TLS, hệ điều hành và các kết nối đồng thời cũng có buffer và tài nguyên riêng; không thể suy rằng tổng bộ nhớ ứng dụng luôn bằng đúng 64 KiB.

Các thành phần Java 11 cần phân biệt:

| Thành phần | Công dụng |
| --- | --- |
| HttpRequest.BodyPublisher | Cung cấp byte của request body lên đường truyền. ofFile(Path) đọc file từng phần. |
| HttpResponse.BodyHandler<T> | Chọn chiến lược tiếp nhận response theo headers/status và tạo BodySubscriber. |
| HttpResponse.BodySubscriber<T> | Tiếp nhận các khối byte của response; implementation có thể đẩy ra file, stream hoặc tập hợp bộ nhớ. |
| java.util.concurrent.Flow | Cơ chế Publisher/Subscriber cho nguồn streaming tùy chỉnh, yêu cầu demand (backpressure), xử lý error/cancel. |
| InputStream / OutputStream | API blocking truyền các byte theo luồng ở client hoặc server. |

**HTTP framing:** Với HTTP/1.1, khi biết trước dung lượng body có thể dùng Content-Length; nếu không biết có thể dùng Transfer-Encoding: chunked. HTTP/2 dùng DATA frame và flow control riêng, không dùng cơ chế chunked của HTTP/1.1. Với Java HttpClient, **không tự gán Transfer-Encoding hoặc tự đóng gói chunk**; để client và protocol handler làm việc đó.

**Streaming khác multipart:** BodyPublishers.ofFile(path) gửi **raw byte** từ file, thường với Content-Type: application/octet-stream. Nó không tự tạo multipart/form-data. Nếu API yêu cầu multipart, phải tạo part header, boundary và body đúng chuẩn, dùng encoder hỗ trợ streaming; đổi mỗi Content-Type không đủ.

## 3. Lựa chọn API Java 11

### Upload

- **BodyPublishers.ofFile(Path)**: thuận tiện nhất khi có tệp trên đĩa, không cần Files.readAllBytes(). Content length có thể xác định từ tệp.
- **BodyPublishers.ofInputStream(Supplier<? extends InputStream>)**: dành cho nguồn động hoặc stream không biết trước độ dài. Supplier phải mở **InputStream mới** khi được gọi. Trình HTTP client có thể cần phát lại request do xác thực/redirect và gọi supplier nhiều lần.
- **BodyPublishers.fromPublisher(Flow.Publisher<ByteBuffer>)**: cho nguồn reactive/tùy chỉnh. Nếu khai báo contentLength thì số byte phát phải đúng; publisher phải tuân thủ request(n), cancel và phát lỗi đúng quy tắc.

Ví dụ nguồn stream động (đây là snippet trong phương thức đã có biến Path source):

~~~java
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofInputStream(() -> {
            try {
                return java.nio.file.Files.newInputStream(source);
            } catch (java.io.IOException e) {
                throw new java.io.UncheckedIOException(e);
            }
        });
~~~

Không mở một stream duy nhất bên ngoài supplier rồi cố sử dụng lại stream đã đọc hết. Với file cố định, ofFile(source) ngắn gọn hơn.

### Download

- **BodyHandlers.ofFile(path)**: stream thẳng response xuống file. Lưu ý: các body handler dựng sẵn **không kiểm tra HTTP status để tự bỏ body lỗi**; nội dung trang lỗi 404/500 cũng có thể được ghi vào file.
- **BodyHandlers.ofInputStream()**: trả về response với InputStream; khi nhận HttpResponse, headers có thể đã xong nhưng **body vẫn đang được tải**. Kiểm tra status trước khi tạo file đích, đọc stream theo khối và luôn đóng stream sau khi dùng.
- **BodyHandlers.ofByteArray()/ofString()**: chỉ dùng khi biết response nhỏ (ví dụ JSON xác nhận), tránh nhận toàn bộ file lớn bằng các handler này.
- **BodyHandlers.ofPublisher()**: phục vụ pipeline reactive nâng cao, cần đăng ký subscription và quản lý nó đầy đủ.

## 4. Ví dụ Java 11 chạy được: server, upload, download, xác minh

Để tập trung vào bản chất streaming mà không phải cài thư viện, chương trình dùng HTTP server nhẹ có trong JDK: **com.sun.net.httpserver.HttpServer**. Đây là server **thực hành trên localhost**, không phải mẫu cấu hình production.

Luồng thực hiện: tạo file nguồn 2 MiB theo từng khối 64 KiB; chạy server tại 127.0.0.1 với cổng ngẫu nhiên; gửi POST upload file; server đọc request theo stream vào file tạm; client GET download theo stream vào file tạm; đối chiếu số byte và SHA-256; dọn file sau thử nghiệm.

Tạo tệp **StreamingFileDemo.java** với **toàn bộ** mã sau:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.security.MessageDigest;

public class StreamingFileDemo {
    private static final int BUFFER_BYTES = 64 * 1024;
    private static final long MAX_UPLOAD_BYTES = 50L * 1024 * 1024;

    public static void main(String[] args) throws Exception {
        Path work = Files.createTempDirectory("stream-demo-");
        Path source = work.resolve("source.bin");
        Path stored = work.resolve("stored.bin");
        Path downloaded = work.resolve("downloaded.bin");
        createSample(source);

        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/file", exchange -> handle(exchange, stored));
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/file");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(10))
                    .build();

            HttpRequest upload = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofMinutes(3))
                    .header("Content-Type", "application/octet-stream")
                    .POST(HttpRequest.BodyPublishers.ofFile(source))
                    .build();
            HttpResponse<Void> uploaded = client.send(upload, HttpResponse.BodyHandlers.discarding());
            if (uploaded.statusCode() != 201) {
                throw new IOException("Upload failed: HTTP " + uploaded.statusCode());
            }
            System.out.println("Upload: HTTP " + uploaded.statusCode());

            HttpRequest download = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofMinutes(3))
                    .GET()
                    .build();
            HttpResponse<InputStream> response = client.send(
                    download, HttpResponse.BodyHandlers.ofInputStream());
            long received;
            try (InputStream in = response.body()) {
                if (response.statusCode() != 200) {
                    throw new IOException("Download failed: HTTP " + response.statusCode());
                }
                Path partial = Files.createTempFile(work, "download-", ".part");
                try {
                    try (OutputStream out = Files.newOutputStream(partial)) {
                        received = copyChunks(in, out);
                    }
                    long expected = response.headers()
                            .firstValueAsLong("Content-Length").orElse(-1L);
                    if (expected >= 0 && received != expected) {
                        throw new IOException("Incomplete download: " + received + " of " + expected);
                    }
                    replaceFile(partial, downloaded);
                } finally {
                    Files.deleteIfExists(partial);
                }
            }
            System.out.println("Download: HTTP " + response.statusCode()
                    + ", " + received + " bytes");
            System.out.println("SHA-256 matches: " + MessageDigest.isEqual(
                    sha256(source), sha256(downloaded)));
        } finally {
            server.stop(0);
            Files.deleteIfExists(source);
            Files.deleteIfExists(stored);
            Files.deleteIfExists(downloaded);
            Files.deleteIfExists(work);
        }
    }

    private static void handle(HttpExchange exchange, Path stored) throws IOException {
        try {
            if ("POST".equals(exchange.getRequestMethod())) {
                Path partial = Files.createTempFile(stored.getParent(), "incoming-", ".part");
                boolean tooLarge = false;
                try {
                    try (InputStream in = exchange.getRequestBody();
                         OutputStream out = Files.newOutputStream(partial)) {
                        byte[] buffer = new byte[BUFFER_BYTES];
                        long total = 0;
                        int n;
                        while ((n = in.read(buffer)) != -1) {
                            total += n;
                            if (total > MAX_UPLOAD_BYTES) {
                                tooLarge = true;
                                break;
                            }
                            out.write(buffer, 0, n);
                        }
                    }
                    if (tooLarge) {
                        exchange.sendResponseHeaders(413, -1);
                        return;
                    }
                    replaceFile(partial, stored);
                    exchange.sendResponseHeaders(201, -1);
                } finally {
                    Files.deleteIfExists(partial);
                }
            } else if ("GET".equals(exchange.getRequestMethod())) {
                if (!Files.isRegularFile(stored)) {
                    exchange.sendResponseHeaders(404, -1);
                    return;
                }
                exchange.getResponseHeaders().set("Content-Type", "application/octet-stream");
                exchange.sendResponseHeaders(200, Files.size(stored));
                try (InputStream in = Files.newInputStream(stored);
                     OutputStream out = exchange.getResponseBody()) {
                    copyChunks(in, out);
                }
            } else {
                exchange.getResponseHeaders().set("Allow", "GET, POST");
                exchange.sendResponseHeaders(405, -1);
            }
        } finally {
            exchange.close();
        }
    }

    private static long copyChunks(InputStream in, OutputStream out) throws IOException {
        byte[] buffer = new byte[BUFFER_BYTES];
        long total = 0;
        int n;
        while ((n = in.read(buffer)) != -1) {
            out.write(buffer, 0, n);
            total += n;
        }
        return total;
    }

    private static void replaceFile(Path temp, Path target) throws IOException {
        try {
            Files.move(temp, target,
                    StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException e) {
            Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private static void createSample(Path path) throws IOException {
        byte[] block = new byte[BUFFER_BYTES];
        for (int i = 0; i < block.length; i++) {
            block[i] = (byte) (i % 251);
        }
        try (OutputStream out = Files.newOutputStream(path)) {
            for (int i = 0; i < 32; i++) {
                out.write(block);
            }
        }
    }

    private static byte[] sha256(Path path) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = Files.newInputStream(path)) {
            byte[] buffer = new byte[BUFFER_BYTES];
            int n;
            while ((n = in.read(buffer)) != -1) {
                digest.update(buffer, 0, n);
            }
        }
        return digest.digest();
    }
}
~~~

### Biên dịch và chạy

Yêu cầu JDK 11 trở lên:

~~~bash
javac --release 11 StreamingFileDemo.java
java StreamingFileDemo
~~~

Kết quả đã được kiểm tra bằng biên dịch với --release 11 và chạy trên JDK tương thích:

~~~text
Upload: HTTP 201
Download: HTTP 200, 2097152 bytes
SHA-256 matches: true
~~~

File 2 MiB chỉ phục vụ thử nghiệm nhanh; các phương thức copyChunks(), ofFile(), ofInputStream() hoạt động theo cùng nguyên tắc với file lớn hơn. Demo xóa thư mục tạm trong nhánh cuối để không để lại dữ liệu thử.

### Phân tích từng phần

**Upload phía client:** BodyPublishers.ofFile(source) cho phép HTTP client đọc dần tệp từ ổ đĩa. Ứng dụng không chuyển toàn bộ tệp sang byte[]. HttpClient có thể được dùng lại cho nhiều request. BodyHandlers.discarding() không giữ response body trong heap. Sau upload, ứng dụng kiểm tra status **201 Created**.

**Upload phía server:** InputStream từ getRequestBody() được đọc thành khối 64 KiB và ghi vào tệp incoming-*.part. Biến total kiểm tra MAX_UPLOAD_BYTES **trong lúc nhận**, vì chỉ tin header Content-Length sẽ không đủ: header có thể thiếu hoặc không đúng. Nếu quá giới hạn, server từ chối với 413; tệp tạm được xóa. Đổi tên tệp xảy ra sau khi nhận đủ dữ liệu. Server demo cố định đích stored.bin, không lấy file path tùy ý từ người gửi.

**Download phía server:** Response được khai báo Content-Type: application/octet-stream, Content-Length qua Files.size(stored), rồi sao chép từ FileInputStream sang getResponseBody(). Server không gom nội dung vào bộ nhớ trước khi gửi.

**Download phía client:** BodyHandlers.ofInputStream() đưa quyền đọc response body cho client. Trước khi ghi file, kiểm tra HTTP 200. Sau đó chép theo khối vào download-*.part trong try-with-resources. Nếu đang download mà xảy ra IOException, tệp tạm bị xóa. Nếu có Content-Length, so sánh với số byte thực nhận; khi hợp lệ mới đổi tên sang downloaded.bin. Stream response luôn được đóng kể cả HTTP status không thành công. SHA-256 của hai file được tính theo stream và đối chiếu ở cuối.

**Thư mục tạm và atomic move:** Các file .part và file đích nằm cùng thư mục để tạo điều kiện cho Files.move(..., ATOMIC_MOVE). Không phải filesystem nào cũng hỗ trợ atomic move; hàm replaceFile có fallback. Ở production cần cân nhắc tính nhất quán và chính sách thay file của ứng dụng, kể cả khi fallback không bảo đảm atomicity.

## 5. Thực hành mở rộng với file lớn

Trong createSample(), đổi vòng lặp tạo dữ liệu từ 32 thành 640 để sinh **40 MiB**, vẫn nằm dưới giới hạn upload 50 MiB của demo:

~~~bash
javac --release 11 StreamingFileDemo.java
java -Xmx128m StreamingFileDemo
~~~

Khi chạy thành công, dòng download hiển thị **41943040 bytes** và SHA-256 matches: true. Đây là cách kiểm chứng thực tế rằng ứng dụng không cần mảng byte[] có kích thước bằng toàn bộ tệp; peak heap vẫn có thể thay đổi theo JDK, kết nối, TLS và môi trường. Không dùng một bài thử duy nhất để khẳng định đủ tài nguyên cho production.

### Khi endpoint cho phép ghi thẳng vào file

Có thể thay phần download bằng:

~~~java
// Snippet: cần có HttpClient client, HttpRequest request, Path destination.
HttpResponse<Path> result = client.send(
        request, HttpResponse.BodyHandlers.ofFile(destination));
if (result.statusCode() != 200) {
    // Lưu ý: body phản hồi lỗi có thể đã được ghi vào destination.
    throw new IOException("Unexpected status: " + result.statusCode());
}
~~~

**Cảnh báo:** Đây là ví dụ đơn giản về API; khác với bản chính, nó không tránh được việc ghi error body vào đích trước khi kiểm tra status. Với đầu vào không tin cậy, dùng ofInputStream + kiểm tra status + file .part hoặc một BodyHandler tùy chỉnh để chọn BodySubscriber theo status. Khi body handler dạng ofFile trả về thành công, body đã được ghi xong; khi dùng ofInputStream, body có thể chưa được nhận xong.

### Khi cần tiếp tục truyền sau đứt mạng

- **Download resume**: yêu cầu HTTP Range: bytes=offset- và kiểm tra server thực sự trả **206 Partial Content** cùng Content-Range đúng. Dùng ETag và If-Range để bảo đảm phần trước/sau thuộc một phiên bản. Nếu server trả **200 OK** toàn bộ file, không được append mù vào phần đã tải.
- **Upload resume**: POST body streaming không tự lưu tiến độ cho lần nối lại. Cần API hỗ trợ offset/chunk, phiên upload, xác minh từng phần và idempotency; tránh tự retry POST gây upload trùng hoặc ghi đè không mong muốn.
- **Kích thước không xác định**: Content-Length có thể không xuất hiện (ví dụ chunked), nên số byte thực nhận và checksum phía nguồn đáng tin cậy là căn cứ bổ sung.
- **Đồng thời nhiều upload**: mỗi request có stream, buffer, socket và đĩa riêng. Giới hạn concurrency, dung lượng, băng thông và thời gian để tránh cạn tài nguyên.

## 6. Checklist xử lý production

1. **Hợp đồng API:** xác định raw octet-stream hay multipart/form-data, method, status thành công, MIME hợp lệ, giới hạn kích thước, checksum và chính sách ghi đè.
2. **Bảo mật:** dùng HTTPS khi truyền qua mạng, xác thực và kiểm tra quyền truy cập; không tin tên file/đường dẫn/Content-Type do client gửi; dùng thư mục đích kiểm soát, ngăn path traversal và xem xét quét file theo quy định.
3. **Bộ nhớ/đĩa:** không dùng Files.readAllBytes hoặc BodyHandlers.ofByteArray cho file lớn; có quota, giới hạn kích thước khi stream, giới hạn số transfer đồng thời, đủ dung lượng tạm và quy trình dọn .part.
4. **Lỗi:** xử lý HTTP status, IOException, InterruptedException trong ngữ cảnh phù hợp, kiểm tra số byte và checksum; chỉ công bố file cuối khi đã tải xong.
5. **Timeout:** connectTimeout liên quan bước kết nối. Request timeout không thay thế toàn bộ chiến lược phát hiện stalled transfer; với ofInputStream, việc đọc body còn có thể kéo dài sau lúc nhận HttpResponse. Xây timeout/cancel theo tầng ứng dụng.
6. **Tính toàn vẹn:** nếu có Content-Length, so byte thực nhận; so hash từ nguồn tin cậy. Hash khớp giữa hai file do cùng một ứng dụng tạo chỉ xác nhận bản sao trong bài thử, không chứng minh dữ liệu đến từ bên gửi đáng tin.
7. **Quan sát:** log ID truyền file, bytes, thời gian, throughput, HTTP status, loại lỗi; tránh log token hoặc nội dung file. Theo dõi số kết nối, heap, GC, file descriptor và disk I/O.
8. **Phục hồi:** với file vài GB và mạng không ổn định, xem xét giao thức upload/download resumable thay vì gửi lại toàn bộ body.

## 7. Lỗi phổ biến

| Lỗi | Vì sao xảy ra | Hướng sửa |
| --- | --- | --- |
| OutOfMemoryError | Tạo byte[]/String chứa toàn bộ file | BodyPublisher/ofInputStream/ofFile và xử lý khối nhỏ. |
| File tải về chứa nội dung lỗi 404 | BodyHandlers.ofFile() ghi response bất kể status | Kiểm tra status trước khi ghi; dùng file tạm. |
| File được coi là hoàn tất dù bị mất mạng | Ghi trực tiếp vào đích rồi bỏ qua exception | Ghi .part, xóa khi lỗi, xác minh bytes/hash, đổi tên cuối. |
| Server hết đĩa | Thiếu quota/giới hạn upload và cleanup | Giới hạn byte thực nhận, quota đĩa, dọn file tạm. |
| Tệp ghi sai thư mục | Tin path/filename từ client | Dùng đích cố định hoặc ID do server cấp, validate path. |
| POST gửi lại tạo dữ liệu trùng | Retry không có idempotency | Idempotency key hoặc upload session có offset. |
| Treo hoặc giữ tài nguyên khi tải lỗi | Không đóng response InputStream | try-with-resources; đóng/hủy khi không tiêu thụ body. |
| Sai định dạng multipart | Gửi raw file nhưng server chờ multipart parts | Encoder multipart streaming đúng boundary/part headers. |
| Đặt sai Transfer-Encoding | Tự điều khiển framing HTTP | Để HttpClient tự chọn Content-Length/chunked hoặc HTTP/2 framing. |

## 8. Câu hỏi tự kiểm tra

1. Vì sao BodyPublishers.ofFile(path) không cần tải toàn bộ file vào heap?
2. Vì sao nhận được HttpResponse<InputStream> chưa có nghĩa là đã tải xong response body?
3. Rủi ro của BodyHandlers.ofFile(destination) nếu server trả 500 và error body là HTML?
4. Tại sao server cần đếm byte thực nhận thay vì chỉ dựa vào Content-Length?
5. Vì sao một request upload streaming không tự hỗ trợ resume hay retry POST an toàn?

**Đáp án gợi ý:** (1) đọc và phát byte tăng dần; (2) status/header có thể đến trước phần cuối của body; (3) HTML lỗi có thể được ghi đè vào file đích; (4) header thiếu/sai và cần thực thi quota; (5) resume/idempotency là hợp đồng giao thức ở tầng ứng dụng.

## 9. Tài liệu đối chiếu chính thức (Java 11)

- HttpClient: https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html
- HttpRequest.BodyPublishers: https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html
- HttpResponse.BodyHandlers: https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- HttpResponse.BodySubscribers: https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html

Bài này tập trung vào các API còn áp dụng cho ứng dụng Java hiện nay; ví dụ biên dịch đúng target Java 11 để người học không vô tình phụ thuộc tính năng mới hơn.