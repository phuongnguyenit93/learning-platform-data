# Giới hạn kích thước, tài nguyên và tốc độ phát Request Body (Java 11+)

## Mục tiêu

Khi gửi một HTTP request có body lớn (upload ảnh, tài liệu, bản sao lưu, dữ liệu được sinh liên tục), ứng dụng cần kiểm soát **ba giới hạn khác nhau**:

1. **Kích thước:** một request không được gửi quá số byte được phép.
2. **Tài nguyên:** không giữ toàn bộ body trong heap, không mở vô hạn file/stream/kết nối, không tạo quá nhiều upload đồng thời.
3. **Tốc độ phát:** giới hạn lượng dữ liệu nguồn được cung cấp theo thời gian, tránh làm quá tải mạng hoặc phía nhận.

Trong **Java 11**, `java.net.http.HttpRequest.BodyPublisher` cho phép ứng dụng phát nội dung request qua cơ chế `Flow.Publisher<ByteBuffer>`. Các publisher chuẩn như `ofFile(...)`, `ofInputStream(...)` và `fromPublisher(...)` tiếp tục được hỗ trợ trong JDK hiện đại. Tuy nhiên, **không có một lời gọi `HttpRequest.Builder.maxBodyBytes(...)` chuẩn tự động giải quyết cả ba ngân sách trên**: bạn phải lựa chọn publisher, kiểm tra giới hạn và điều tiết ở đúng tầng.

Sau bài này, bạn có thể chọn API theo kích thước dữ liệu, phân biệt backpressure với bandwidth throttling, viết chương trình Java 11 chạy được để upload từ file với giới hạn byte và pacing, đồng thời thiết kế biện pháp bảo vệ cho client và server.

## 1. BodyPublisher làm việc ở đâu trong HTTP Client?

Luồng dữ liệu điển hình:

```text
File / InputStream / dữ liệu phát sinh
       |
       | đọc từng phần, kiểm tra quota, điều tiết nguồn
       v
HttpRequest.BodyPublisher
       |  Flow.Publisher<ByteBuffer>
       |  onSubscribe / request(n) / onNext / onComplete
       v
HttpClient (HTTP/1.1 hoặc HTTP/2, TLS, socket)
       |
       v
Server: xác thực, giới hạn body, lưu/tiêu thụ nội dung
       |
       v
HttpResponse: status + headers + response body
```

Các tầng này **không đồng nhất**:

- **`BodyPublisher`** cung cấp byte cho phía gửi; nó không tự đảm bảo byte đó đã được server lưu thành công.
- **`HttpClient`** quản lý gửi dữ liệu, protocol, kết nối và lỗi. Một client có thể gửi nhiều request; không cần tạo client mới chỉ để upload một file khác.
- **Server** bắt buộc tự kiểm tra request body thực nhận. Giới hạn phía client là một lớp bảo vệ, **không phải cơ chế an toàn đủ cho server**.
- **`HttpResponse.BodyHandler`** xử lý chiều **response**; đừng nhầm `BodyPublishers.ofFile(...)` để **upload** với `BodyHandlers.ofFile(...)` để **download**.

Theo Javadoc, `HttpRequest.BodyPublisher` là một `Flow.Publisher<ByteBuffer>`. Khi gửi request, `HttpClient` subscribe để nhận dữ liệu. Nếu cần gửi lại request vì một lý do hợp lệ, publisher có thể được **subscribe lại**; nguồn dữ liệu phải có chiến lược phát lại hoặc báo lỗi rõ ràng.

## 2. Chọn publisher theo kích thước và dạng dữ liệu

| Publisher Java 11+ | Nguồn | Chi phí và giới hạn cần lưu ý | Khi phù hợp |
| --- | --- | --- | --- |
| `BodyPublishers.ofString(text)` | `String` đã có | Chuỗi đã ở trong RAM; encoding tạo bytes | JSON/text nhỏ |
| `BodyPublishers.ofByteArray(bytes)` | Mảng `byte[]` | Toàn mảng đã có trong heap | Payload nhỏ, đã được tính trước |
| `BodyPublishers.ofFile(path)` | Tệp trên đĩa | Có thể đọc file khi gửi, không cần dựng toàn bộ `byte[]` | Upload file, biết đường dẫn |
| `BodyPublishers.ofInputStream(supplier)` | `InputStream` mở theo yêu cầu | Streaming; độ dài thường không biết trước | Nguồn động hoặc muốn bọc stream để kiểm soát |
| `BodyPublishers.fromPublisher(flowPublisher)` | Publisher `ByteBuffer` tùy chỉnh | Phải tự giữ đúng hợp đồng `Flow` | Pipeline async/reactive chuyên biệt |
| `BodyPublishers.fromPublisher(flowPublisher, length)` | Publisher custom + độ dài biết trước | `length` là **số byte chính xác** phải phát, không phải “số byte tối đa” | Giao thức yêu cầu length chính xác |

Đoạn mẫu cho tệp đã có và được kiểm tra kích thước trước:

```java
long bytes = Files.size(file);
if (bytes > maxBytes) {
    throw new IOException("Upload too large");
}
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofFile(file);
```

**Đây là đoạn minh họa**, không phải chương trình độc lập: cần `Path file`, `long maxBytes` cùng import `Files`, `IOException` và `HttpRequest`. Đọc toàn bộ file bằng `Files.readAllBytes(file)` trước khi gửi là **không cần thiết** nếu mục tiêu chỉ là upload nội dung tệp.

**Không tự kết luận `ofFile` luôn giữ bộ nhớ tuyệt đối cố định**: client, TLS, body publisher, response và các request song song vẫn có buffer/cấp phát. Lợi ích là tránh việc **ứng dụng tự giữ cả file** dưới dạng một mảng hoặc chuỗi.

### Content length của publisher

`publisher.contentLength()` trả về:

- `0`: body rỗng.
- Số dương: số **byte chính xác** được khai báo.
- Số âm, thường `-1`: **chưa biết** độ dài trước khi phát.

Không dùng `contentLength() == -1` để hiểu “body không giới hạn”. Nó chỉ có nghĩa publisher **không công bố trước** kích thước. Ví dụ `ofInputStream(...)` có thể báo `-1` dù nguồn thực sự chỉ có 8 KiB. Điều này khác với quy tắc nghiệp vụ “không được gửi quá 16 KiB”.

Với `fromPublisher(publisher, length)`, giá trị `length` dương phải **đúng bằng số byte sẽ phát**, không được đưa `MAX_UPLOAD_BYTES` vào đó để mong client tự ngắt tại quota. Nếu publisher phát thiếu hoặc thừa so với length khai báo, quá trình truyền có thể thất bại hoặc làm sai framing theo hợp đồng HTTP.

## 3. Giới hạn kích thước: kiểm tra trước và ràng buộc khi đọc

Nếu bạn có đường dẫn tệp, bước đầu hợp lý là kiểm tra:

```java
long size = Files.size(file); // byte trên đĩa
if (size > MAX_BYTES) {
    throw new IOException("File exceeds upload budget");
}
```

Đây là **đoạn minh họa** trong một phương thức có xử lý `IOException` và biến `Path file`; `MAX_BYTES` là chính sách do ứng dụng định nghĩa.

Ưu điểm là **từ chối sớm**, không cần mở kết nối và gửi dữ liệu nếu file quá lớn. Nhưng kiểm tra này **không đủ trong mọi tình huống**:

- Tệp có thể thay đổi giữa thời điểm `Files.size(file)` và lúc publisher đọc nó (**time-of-check/time-of-use**, TOCTOU).
- Nguồn có thể không có kích thước trước: stream từ cảm biến, dữ liệu sinh theo thời gian, dữ liệu giải nén.
- Nội dung đã biến đổi (mã hóa, nén, multipart encoding) có thể có **độ dài trên wire khác độ dài file nguồn**.
- Nếu giới hạn là dung lượng **phần request body gửi đi**, phải đo bytes **sau các phép biến đổi tạo body**, không đo nhầm độ dài ký tự Java hay số dòng.

Vì vậy đối với dữ liệu không hoàn toàn đáng tin, nên có **bộ đếm byte trên luồng phát thực tế**. Khi sắp vượt hạn mức, nên **báo lỗi thay vì trả EOF giả**. EOF giả có thể khiến server tiếp nhận một file bị cắt nhưng vẫn coi request là hoàn tất.

Một luồng giới hạn byte có thể bọc `InputStream` bên trong `BodyPublishers.ofInputStream(...)`. Ví dụ đầy đủ ở phần 6 thực hiện cả preflight và kiểm tra trong khi đọc.

### Cẩn trọng với đơn vị đo

- `Files.size(path)`, `BodyPublisher.contentLength()` và HTTP `Content-Length` tính theo **byte**.
- `String.length()` tính theo **đơn vị UTF-16**, không phải byte UTF-8.
- Với payload JSON hoặc Unicode, phải đo **bytes đã được encode**, không lấy số ký tự làm giới hạn upload.
- Một file 1 MiB = **1.048.576 byte**; 1 MB theo hệ thập phân = **1.000.000 byte**. Ghi rõ đơn vị trong cấu hình và API.

## 4. Giới hạn tài nguyên: bộ nhớ, file handle và số upload đồng thời

### Tránh nạp body lớn vào RAM

**Không nên dùng cho file tùy ý rất lớn:**

```java
byte[] entireFile = Files.readAllBytes(file);
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofByteArray(entireFile);
```

Đây là mã minh họa. Nó tạo mảng kích thước theo toàn bộ file, dễ tăng áp lực heap và garbage collection. Nếu file đã nằm trên đĩa, `BodyPublishers.ofFile(file)` thường là lựa chọn đơn giản. Nếu cần đọc có bộ đếm/rate limiter, bọc `InputStream` và dùng `ofInputStream(Supplier)`.

### Giới hạn số lần upload đồng thời

Ngay cả khi **mỗi** upload có buffer nhỏ, **hàng nghìn upload đồng thời** vẫn có thể giữ quá nhiều socket, TLS state, future, file descriptor và băng thông. Cần giới hạn **concurrency**, độc lập với kích thước body.

Ví dụ **đoạn minh họa đồng bộ** có thể dùng `Semaphore`:

```java
Semaphore slots = new Semaphore(3);

slots.acquire(); // Có thể ném InterruptedException
try {
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString());
    // Xử lý status/response.
} finally {
    slots.release();
}
```

Đoạn code này cần các biến `client`/`request` đã tạo và import `java.util.concurrent.Semaphore`, `java.net.http.HttpResponse`; `send` có thể ném `IOException` và `InterruptedException`. Để có tác dụng trên **nhiều request**, các request đó phải dùng **chung Semaphore**, không tạo một semaphore mới cho mỗi lần gửi. `3` chỉ là giá trị minh họa, không phải khuyến nghị cố định.

Với `sendAsync()`, phải giữ permit **cho đến khi request kết thúc** (ví dụ release trong `whenComplete`), không release ngay sau khi `sendAsync` trả về future. Cũng cần release permit khi thao tác khởi tạo request thất bại.

### Đóng và hủy tài nguyên đúng cách

- `ofInputStream(supplier)` mở stream theo yêu cầu; mỗi lần subscription nên có stream **mới, đọc được từ đầu**, và phải được đóng khi hoàn thành hoặc ngừng.
- Nếu ứng dụng tự xây `BodyPublisher`, phải xử lý `cancel()`, `onError`, `onComplete` và đóng file/channel/queue ở thời điểm thích hợp; không để publisher giữ tài nguyên vô hạn.
- Không tạo mới `HttpClient` cho mọi upload chỉ vì các request khác file. Tái dùng client theo nhóm cấu hình và ranh giới bảo mật giúp có cơ hội dùng chung kết nối.
- Với Java 11, `HttpClient` **không có** `close()` public; từ Java 21 mới có các API vòng đời như `close()/shutdown()`. Đừng chép đoạn `try (HttpClient client = ...)` Java 21 vào chương trình bắt buộc biên dịch với `--release 11`.
- Một body đã tiêu thụ và response đã đóng không có nghĩa server đã lưu file thành công. Kiểm tra status cuối cùng và hợp đồng nghiệp vụ.

## 5. “Backpressure” khác “giới hạn byte mỗi giây”

`BodyPublisher` tuân theo Reactive Streams API của Java `Flow`. Subscriber của HTTP client có thể gọi:

```java
subscription.request(n);
```

Ở đây `n` là số **phần tử `ByteBuffer`** được yêu cầu, **không phải số byte**, không phải “n request HTTP”, và không phải số byte/giây.

Nếu publisher nhận được demand cho 2 buffer:

- Có thể phát tối đa 2 lần `onNext(buffer)` trong phạm vi demand đó.
- Một buffer có thể chứa 512 B; buffer khác có thể chứa 64 KiB. Demand 2 **không** có nghĩa chỉ được phát 2 byte.
- Publisher không nên phát vượt demand; phải hỗ trợ cancellation và giao các tín hiệu đúng trình tự.
- Nếu làm publisher custom, **không sửa hoặc tái sử dụng `ByteBuffer` sau khi đã phát nó cho client**; Javadoc yêu cầu nội dung buffer không bị can thiệp sau khi publish.

**Backpressure điều tiết tốc độ tiêu thụ tương đối giữa producer và subscriber**, nhưng không cam kết một giới hạn băng thông vật lý, chẳng hạn 100 KiB/s. HTTP/2 flow control cũng là cơ chế khác với quota ứng dụng.

Muốn giới hạn **tốc độ phát dữ liệu**, bạn cần cơ chế riêng:

- **Pacing bằng thời gian** khi đọc nguồn (như ví dụ): trì hoãn cung cấp byte mới cho publisher.
- **Token bucket/leaky bucket** theo byte để cho phép burst có giới hạn và tốc độ trung bình cấu hình được.
- **Scheduler + `Flow.Publisher<ByteBuffer>` tuân thủ demand** cho hệ thống reactive quy mô lớn, tránh block nhiều thread đọc.
- **Giới hạn tổng lưu lượng của nhiều upload** bằng rate limiter chung, không chỉ đặt rate trên từng request.

**Bộ giới hạn tốc độ đặt tại nguồn chỉ điều tiết tốc độ cấp byte từ ứng dụng**; transport còn có buffer và có thể phát bytes lên socket theo những cụm khác nhau. Do đó nó không phải cam kết chính xác rằng Wi-Fi/TCP sẽ luôn truyền không quá X byte trong mọi cửa sổ thời gian.

## 6. Chương trình chạy được: body có byte budget và pacing

Ví dụ sau tự tạo file **8 KiB** và HTTP server loopback; cho phép **tối đa 16 KiB**; dùng một `InputStream` bọc kiểm tra byte đã đọc và tạo nhịp cấp dữ liệu theo tốc độ danh nghĩa **128 KiB/s**. Server cũng tự giới hạn số byte thực nhận và trả `413 Content Too Large` nếu vượt.

Đây là bài học minh họa cơ chế, **không phải rate limiter production**: việc dùng `sleep(...)` trong `InputStream.read(...)` có thể block thread của HTTP client. Ở hệ thống có hàng trăm upload đồng thời, hãy dùng rate limiter có kiểm soát, async scheduling, queue hữu hạn, giám sát và giới hạn concurrency.

**Tệp: `UploadBudgetDemo.java`** (Java 11+).

```java
import com.sun.net.httpserver.HttpServer;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InterruptedIOException;
import java.io.OutputStream;
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
import java.util.concurrent.TimeUnit;

public class UploadBudgetDemo {
    private static final long MAX_BYTES = 16 * 1024;
    private static final long BYTES_PER_SECOND = 128 * 1024;

    private static final class BudgetedPacedInputStream
            extends FilterInputStream {
        private final long maxBytes;
        private final long bytesPerSecond;
        private final long started = System.nanoTime();
        private long sent;

        BudgetedPacedInputStream(
                InputStream in, long maxBytes, long bytesPerSecond) {
            super(in);
            if (maxBytes < 0 || bytesPerSecond <= 0) {
                throw new IllegalArgumentException(
                        "Invalid budget or rate");
            }
            this.maxBytes = maxBytes;
            this.bytesPerSecond = bytesPerSecond;
        }

        @Override
        public int read() throws IOException {
            byte[] one = new byte[1];
            int count = read(one, 0, 1);
            return count == -1 ? -1 : one[0] & 0xff;
        }

        @Override
        public int read(byte[] bytes, int offset, int length)
                throws IOException {
            java.util.Objects.checkFromIndexSize(
                    offset, length, bytes.length);
            if (length == 0) {
                return 0;
            }

            long remaining = maxBytes - sent;
            if (remaining == 0) {
                if (in.read() == -1) {
                    return -1;
                }
                throw new IOException(
                        "Request body exceeds byte budget");
            }

            int allowed = (int) Math.min(
                    1024L, Math.min(remaining, (long) length));
            int count = in.read(bytes, offset, allowed);
            if (count <= 0) {
                return count;
            }

            sent += count;
            long targetNanos =
                    sent * 1_000_000_000L / bytesPerSecond;
            long elapsedNanos = System.nanoTime() - started;
            long delayNanos = targetNanos - elapsedNanos;
            if (delayNanos > 0) {
                try {
                    TimeUnit.NANOSECONDS.sleep(delayNanos);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new InterruptedIOException(
                            "Paced upload interrupted");
                }
            }
            return count;
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile(
                "upload-budget-", ".bin");
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/upload", exchange -> {
            long count = 0;
            byte[] block = new byte[2048];
            boolean exceeded = false;
            try (InputStream input =
                    exchange.getRequestBody()) {
                int size;
                while ((size = input.read(block)) != -1) {
                    count += size;
                    if (count > MAX_BYTES) {
                        exceeded = true;
                        break;
                    }
                }
            }

            int status = exceeded ? 413 : 200;
            byte[] reply = (exceeded
                    ? "too-large"
                    : "received=" + count)
                    .getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(
                    status, reply.length);
            try (OutputStream output =
                    exchange.getResponseBody()) {
                output.write(reply);
            }
        });

        try {
            byte[] block = new byte[1024];
            Arrays.fill(block, (byte) 'A');
            try (OutputStream out =
                    Files.newOutputStream(file)) {
                for (int i = 0; i < 8; i++) {
                    out.write(block);
                }
            }

            long fileBytes = Files.size(file);
            if (fileBytes > MAX_BYTES) {
                throw new IOException(
                        "File exceeds upload budget");
            }

            server.start();
            HttpRequest.BodyPublisher publisher =
                    HttpRequest.BodyPublishers.ofInputStream(
                            () -> {
                try {
                    return new BudgetedPacedInputStream(
                            Files.newInputStream(file),
                            MAX_BYTES,
                            BYTES_PER_SECOND);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            });

            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort()
                    + "/upload");
            HttpRequest request =
                    HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(15))
                    .header("Content-Type",
                            "application/octet-stream")
                    .POST(publisher)
                    .build();

            HttpClient client =
                    HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println("fileBytes=" + fileBytes);
            System.out.println(
                    "publisherLength=" + publisher.contentLength());
            System.out.println("status=" + response.statusCode());
            System.out.println("body=" + response.body());
        } finally {
            server.stop(0);
            Files.deleteIfExists(file);
        }
    }
}
```

### Lệnh chạy

Lưu đúng tên `UploadBudgetDemo.java`, từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 UploadBudgetDemo.java
java UploadBudgetDemo
```

Hoặc kiểm tra tương thích Java 11 trên JDK mới hơn:

```bash
javac --release 11 -encoding UTF-8 UploadBudgetDemo.java
java UploadBudgetDemo
```

**Stdout chính xác trong phép chạy đã kiểm tra:**

```text
fileBytes=8192
publisherLength=-1
status=200
body=received=8192
```

Ví dụ đã được **biên dịch bằng `javac --release 11`** và chạy thực tế. Không có thông tin thời gian upload trong stdout vì thời gian đo phụ thuộc hệ điều hành, tải CPU và scheduling, không phải giá trị cố định.

`HttpServer` thuộc module JDK `jdk.httpserver`. Đây là server nội bộ dùng để tái tạo kết quả mà không cần Internet, không phải một upload server production. Trong cấu hình module hạn chế, phải có module `jdk.httpserver` để chạy ví dụ.

### Giải thích chi tiết

**Một: bộ nhớ.** Tệp 8 KiB được tạo từ một `byte[1024]` ghi lặp 8 lần. Khi upload, `ofInputStream` mở `Files.newInputStream(file)` theo yêu cầu, không gọi `Files.readAllBytes(file)`.

**Hai: giới hạn trước khi gửi.** `Files.size(file)` được so với `MAX_BYTES = 16 * 1024`. Tệp lớn hơn 16 KiB bị từ chối trước khi tạo và thực thi HTTP request trong ví dụ.

**Ba: giới hạn khi phát.** `BudgetedPacedInputStream` chỉ cho đọc tối đa 1.024 byte mỗi lần, cộng `sent`. Khi chạm ngân sách mà nguồn **còn byte**, nó ném `IOException` thay vì âm thầm cắt body. Điều này bảo vệ khỏi trường hợp dữ liệu nguồn tăng sau bước kiểm tra size hoặc nguồn không biết trước kích thước. Ngân sách này áp dụng **cho mỗi instance InputStream/subscription**, không tự đặt giới hạn tổng bytes gửi trong mọi lần retry.

**Bốn: điều tiết gần đúng.** Sau mỗi chunk, stream tính số nano-giây lẽ ra đã trôi qua theo số byte `sent` và `BYTES_PER_SECOND`, rồi sleep phần thời gian còn thiếu. Nó ước lượng **nhịp cung cấp dữ liệu từ nguồn**, không kiểm soát chính xác thời điểm packet rời socket; nếu lịch trình bị chậm, những lần đọc sau cũng có thể diễn ra nhanh hơn để “bắt kịp” mức trung bình từ lúc bắt đầu.

**Năm: source replay.** Supplier tạo **stream mới cho mỗi lần gọi**. Đó là yêu cầu thiết kế tốt khi HTTP client cần phát lại body do redirect/authentication/retry trong những điều kiện cho phép. File phải giữ nguyên và đọc được đến khi request thực sự kết thúc.

**Sáu: server tự kiểm tra.** Server đếm **byte thực nhận** và có nhánh trả `413` khi vượt quota. Dù client đã có quota, server vẫn phải tự bảo vệ. Với request quá lớn, việc server đóng request stream và phản hồi sớm có thể khiến phía client nhận response `413` hoặc gặp lỗi truyền/đóng kết nối tùy thời điểm; đừng viết test phụ thuộc một kết quả duy nhất trong tình huống race đó.

**Bảy: kết quả.** `publisherLength=-1` nghĩa là publisher **không công bố trước content length**. Đó không phải bằng chứng rằng payload vô hạn. `received=8192` là số byte server đo được, trong khi `200` chỉ là HTTP status trả về theo logic server demo.

**Tám: quản lý tài nguyên.** `try-with-resources` được dùng cho các stream đọc/ghi, `finally` dừng server và xóa tệp tạm. Với Java 11, chưa có `HttpClient.close()` như Java 21+; client của ví dụ ngắn được phép kết thúc cùng tiến trình.

## 7. Điều tiết tốc độ cho nhiều request: tránh giới hạn “mỗi request” bị nhân lên

Giả sử mỗi request được cấu hình **128 KiB/s**, nhưng ứng dụng khởi chạy 50 request đồng thời. Tổng thông lượng cấp byte có thể tiến tới **50 × 128 KiB/s** trong điều kiện thuận lợi. **Giới hạn trên mỗi request không phải giới hạn tổng toàn dịch vụ.**

Nếu tổ chức chỉ được dùng một ngân sách tải lên toàn cục:

1. Tạo **một rate limiter chia sẻ** giữa các upload, theo byte (không chỉ theo số request).
2. Kết hợp với **concurrency limiter** để số file/sockets/futures đang hoạt động không tăng vô hạn.
3. Phân biệt **burst allowance** với **sustained rate**. Token bucket có thể cho phép một burst ngắn rồi điều tiết theo tốc độ trung bình.
4. Đặt giới hạn dung lượng/tenant, công bằng hàng đợi và timeout khi upload chờ token quá lâu.
5. Đo số byte đã phát, thời gian chờ token, số upload đang hoạt động, số lần bị server từ chối và trạng thái hoàn tất.

Đừng dùng `Thread.sleep()` không giới hạn trên hàng trăm worker thread để tạo rate limit toàn cục. Với ứng dụng async/reactive lớn, dùng publisher có scheduling không chặn, bộ đếm token và buffer hữu hạn, **đồng thời tuân thủ `Flow.Subscription.request(n)` và `cancel()`**.

### Lưu ý về `Flow.Publisher<ByteBuffer>` tự viết

Một publisher custom cần đảm bảo:

- `onSubscribe(subscription)` đúng hợp đồng.
- Chỉ phát `onNext(buffer)` khi có demand còn lại; `request(n)` với `n <= 0` là yêu cầu không hợp lệ.
- `onComplete()` hoặc `onError(...)` đúng lúc và không phát thêm dữ liệu sau terminal signal.
- `cancel()` dừng công việc theo khả năng triển khai, đóng file, ngừng đọc và giải phóng queue.
- Không giữ các `ByteBuffer` vô hạn trong memory queue; buffer chỉ được phát khi có nhu cầu và ngân sách bộ nhớ.
- Không thay đổi `ByteBuffer` sau khi giao cho HTTP client.
- Cung cấp cùng dữ liệu nếu có subscription lại để retry hợp lệ; không tự phát lại dữ liệu có side effect mà chưa có chính sách idempotency.

Sử dụng `BodyPublishers.fromPublisher(custom)` cho độ dài chưa biết hoặc overload có `contentLength` chính xác khi phù hợp. Với nghiệp vụ thông thường, **ưu tiên các publisher có sẵn**; viết reactive publisher từ đầu dễ tạo bug về concurrency, cancellation và memory hơn lợi ích nó mang lại.

## 8. Client và server phải có hai lớp bảo vệ độc lập

Không chỉ client, **server** nhận upload cũng cần quy tắc về kích thước, thời gian và số tài nguyên:

| Rủi ro | Client nên làm | Server nên làm |
| --- | --- | --- |
| Body vượt dung lượng | Kiểm tra size nguồn + byte counter khi phát | Giới hạn từ headers **và** byte thực nhận; trả `413` khi phù hợp |
| Nguồn không biết trước length | Stream với quota; không coi `-1` là unlimited | Áp đặt ngân sách bằng byte count, kể cả khi HTTP dùng chunked |
| Upload quá chậm / treo | Timeout, deadline, cancel, giới hạn chờ và concurrency | Read timeout/idle timeout, giới hạn tốc độ tối thiểu nếu thích hợp, chống slow upload |
| Quá nhiều upload | Semaphore, bounded queue, global rate limiter | Quota theo user/IP/tenant, admission control, `429` khi phù hợp |
| File/heap/disk bị đầy | Không nạp toàn file, đóng stream, giới hạn file nguồn | Giới hạn dung lượng lưu, streaming sang vùng tạm có quota, dọn file lỗi |
| Retry sau timeout | Idempotency key/upload session và xác minh trạng thái | Tạo contract chống trùng và upload resume nếu cần |
| Nội dung độc hại | Không dựa vào tên file; bảo vệ token | Xác thực, kiểm tra định dạng thực, MIME, tên/đường dẫn, quyền và bảo vệ storage |

**HTTP `413 Content Too Large`** là phản hồi server từ chối vì **request content lớn hơn giới hạn**, theo RFC 9110. Đừng dùng nó để mô tả bất kỳ lỗi quota/concurrency nào; ví dụ quá nhiều request thường cần chính sách và status khác như `429 Too Many Requests` khi phù hợp.

### HTTP transfer framing không tự giải quyết quota

- Nếu content length đã biết, HTTP client có thể gửi độ dài chính xác theo phiên bản giao thức.
- Khi độ dài chưa biết trên HTTP/1.1, transport có thể dùng `Transfer-Encoding: chunked`; HTTP/2 dùng DATA frames/flow control của giao thức.
- **Chunked transfer encoding không phải upload theo phần có thể resume** và không áp đặt giới hạn nội dung.
- `Content-Length` nếu xuất hiện cũng **không được server tin tuyệt đối**. Server phải đếm byte thực đọc, bảo vệ quota và kiểm tra tính hợp lệ theo protocol.

## 9. Timeout, cancellation và retry không đồng nghĩa “upload chưa xảy ra”

Có thể đặt timeout khi xây request:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofMinutes(2))
        .POST(publisher)
        .build();
```

Đây là đoạn minh họa với `URI uri`, `BodyPublisher publisher` đã có và import `HttpRequest`, `Duration`.

Nhưng:

- **Timeout** không đặt giới hạn byte hoặc byte/giây. `connectTimeout` liên quan kết nối mới; request timeout không thay quota.
- Khi `send()` ném `IOException`, server **có thể đã nhận một phần hoặc toàn bộ body**. Không tự retry vô điều kiện, nhất là POST có side effects.
- Khi `sendAsync()` kết thúc bất thường hoặc bị `cancel()`, cancellation thường là **best effort**; không tự suy server chưa xử lý.
- Publisher có thể nhận **subscription mới** nếu request cần phát lại. Bọc stream mới đúng cách, nhưng quota per subscription **không** thay quota tổng mọi retry.
- Nếu cần retry/resume cho file lớn, dùng upload session, ID, offset/checksum và API có hợp đồng rõ ràng; việc cắt body thành các chunk HTTP không tự mang lại tính năng resume.

Một thực hành an toàn là duy trì **idempotency key** khi API hỗ trợ, xác minh upload ID/trạng thái server trước retry, giới hạn số lần retry và backoff. File nguồn phải ổn định giữa các lần phát nếu server mong nội dung giống nhau.

## 10. Khi nào dùng `expectContinue(true)`?

`HttpRequest.Builder.expectContinue(true)` (Java 11+) đề nghị server có phản hồi đầu tiên, thường **`100 Continue`** hoặc lỗi sớm, trước khi client bắt đầu phát body. Với file rất lớn, nó có thể giúp tránh gửi body nếu server từ chối ngay qua headers.

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .expectContinue(true)
        .POST(publisher)
        .build();
```

Đây chỉ là đoạn minh họa; không phải server nào cũng xử lý nhanh hoặc giống nhau, và bước chờ có thể tăng latency. Không dùng `expectContinue` thay cho quota/streaming, kiểm tra size hay chứng thực. Đặc biệt `100 Continue` là phản hồi **trung gian**, còn ứng dụng vẫn cần kiểm tra phản hồi **cuối cùng**.

## 11. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đọc file vài GB bằng `readAllBytes` rồi `ofByteArray` | Bộ nhớ heap tăng theo file | Dùng `ofFile` hoặc `ofInputStream` |
| Chỉ dùng `Files.size` để quyết định | File có thể thay đổi, nguồn không biết size | Thêm byte counter trong khi đọc |
| Trả `-1` như EOF khi vừa chạm byte quota dù nguồn còn dữ liệu | Server có thể coi file bị cắt là hoàn tất | Phát lỗi rõ ràng, không cắt dữ liệu âm thầm |
| Gọi `fromPublisher(pub, MAX_BYTES)` như thể `MAX_BYTES` là quota | `length` là số byte **chính xác**, không phải max | Quota xử lý riêng; chỉ công bố exact length |
| Tự đặt `Content-Length` sai | Lỗi framing/protocol hoặc bị client từ chối | Dựa vào publisher và hợp đồng body |
| Coi `Flow.request(5)` là yêu cầu 5 byte | Demand tính **số buffer/onNext**, không phải byte | Tách backpressure với byte-based limiter |
| Publisher phát vượt demand hoặc không đóng khi cancel | Lỗi Flow, treo, rò bộ nhớ/file descriptor | Tuân thủ subscription và quản lý tài nguyên |
| Chỉ giới hạn 100 KiB/s **mỗi request** nhưng chạy 100 request | Tổng lưu lượng có thể quá cao | Limiter tổng + concurrency limit |
| Gọi `Thread.sleep` trên quá nhiều thread I/O để throttle | Nghẽn thread và tăng latency | Async scheduler/rate limiter phù hợp production |
| Chỉ kiểm tra Content-Length phía server | Nguồn/chunked có thể không khai báo độ dài | Đếm byte thực nhận và xử lý quá giới hạn |
| Nhầm Content-Length với kích thước ký tự `String` | Sai trên Unicode và body biến đổi | Đếm byte ở tầng gửi |
| Dùng một InputStream đã đọc cho các lần subscribe sau | Retry/redirect có thể gửi body rỗng hoặc lỗi | Supplier trả stream mới với nội dung ổn định |
| Xem timeout là bằng chứng server chưa lưu dữ liệu | Tạo upload trùng khi retry | Idempotency key và kiểm tra trạng thái |
| Kết luận demo pacing có bảo đảm chính xác băng thông mạng | Socket/TLS/OS có buffering, scheduling thay đổi | Đo wire-level throughput và đặt global policy |
| Quên giới hạn kích thước request ở server | Client ngoài có thể bỏ qua mọi quota phía client | Server luôn kiểm tra riêng và báo `413` phù hợp |

## 12. Bài tập và câu hỏi kiểm tra

**Bài 1 — Tính ngân sách.** File dài 20 KiB, ngân sách tối đa 16 KiB. Chương trình nên gửi gì? **Đáp án:** không gửi; kiểm tra từ trước và báo lỗi. Nếu file lớn thêm sau preflight, stream wrapper phát lỗi khi chạm quota và thấy nguồn vẫn còn byte.

**Bài 2 — Content length.** `BodyPublishers.ofInputStream(supplier).contentLength()` có thể là `-1`. Điều đó có nghĩa body được phép lớn vô hạn? **Không**; chỉ là chưa biết length tại thời điểm thiết kế publisher. Ứng dụng và server vẫn phải áp quota.

**Bài 3 — Flow demand.** Subscriber gọi `request(2)`, publisher gửi hai buffer lần lượt chứa 1 KiB và 8 KiB. Số phần tử `Flow` đã giao là bao nhiêu? **2**, tổng payload **9 KiB**; đây không phải rate 2 B/s hay limit 2 bytes.

**Bài 4 — Thay đổi chính sách.** Trong ví dụ, đổi `MAX_BYTES` thành 4 KiB khi file vẫn 8 KiB. Dự đoán kết quả. **Đáp án:** bước `Files.size(file)` sẽ ném `IOException` trước khi upload; vì demo không bắt riêng exception đó, sẽ không có bốn dòng stdout thành công như trước.

**Bài 5 — Pacing.** Đổi `BYTES_PER_SECOND` thành 32 KiB/s, chạy lại và đo thời gian. Tại sao stdout vẫn cho `received=8192` nhưng thời gian có thể khác? Vì pacing làm chậm **đọc nguồn**, còn thời gian thực còn phụ thuộc scheduler, network stack, máy chủ và hệ điều hành.

**Bài 6 — Tổng tài nguyên.** Có 20 uploads, mỗi upload 128 KiB/s. Tổng lưu lượng tiềm năng là bao nhiêu? **2.560 KiB/s** nếu tất cả liên tục hoạt động đủ tốc độ. Muốn giới hạn toàn hệ thống chỉ 512 KiB/s, cần **rate limiter chia sẻ**, không chỉ giới hạn cho mỗi request.

**Bài 7 — Server bảo vệ độc lập.** Viết test cho server nhận request với length không biết trước và hơn 16 KiB. Giải thích vì sao server vẫn phải đếm byte thực nhận và có thể trả HTTP 413, dù một client chính thống đã giới hạn quota.

**Bài 8 — Retry.** Một POST upload lớn bị timeout sau khi truyền gần xong. Có được tự động gửi lại ngay không? **Không** nếu chưa biết server có lưu bản trước hay không. Thiết kế idempotency hoặc upload session/resume.

### Checklist trước khi đưa vào production

1. Dung lượng tối đa **tính theo byte gửi đi**, có kiểm tra trước và trong lúc phát nếu nguồn có thể thay đổi?
2. Nguồn file/stream có được mở, đọc dần, đóng/cancel và có khả năng phát lại khi cần?
3. Có tránh giữ một body lớn dưới dạng `String`/`byte[]` trong RAM?
4. Có giới hạn **concurrency**, queue, thread, file descriptor, timeout và per-request/global bandwidth?
5. Publisher custom có tuân thủ `Flow`, demand, cancellation, terminal signals, quyền sở hữu `ByteBuffer`?
6. Có tách **backpressure** khỏi **rate limiting bằng byte/giây**?
7. Server có tự áp quota/timeout và kiểm tra byte thực nhận dù client khai báo Content-Length?
8. Có xử lý status cuối, HTTP 413, retry/idempotency và upload resume nếu cần?
9. Có đo memory, bytes thực gửi, latency, tốc độ thực, concurrency và cancellation thay vì đoán từ cấu hình?
10. Kiểm tra code theo JDK tối thiểu cần hỗ trợ, tránh vô tình dùng API mới không có trong Java 11?

## Tài liệu chính thức

- [Oracle Java SE 11 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): `ofFile`, `ofInputStream`, `ofByteArray`, `fromPublisher` và chiều dài biết/không biết trước.
- [Oracle Java SE 25 — HttpRequest.BodyPublisher](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html): `Flow.Publisher<ByteBuffer>`, subscription lại, lifecycle và `contentLength()`.
- [Oracle Java SE 11 — Flow.Subscription](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): `request(n)` tính số phần tử, `cancel()` và demand hợp lệ.
- [Oracle Java SE 25 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request timeout, POST và `expectContinue`.
- [Oracle Java SE 25 — HttpClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html): API gửi đồng bộ/bất đồng bộ và quản lý tài nguyên.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): status `413 Content Too Large`, `Content-Length` và ý nghĩa HTTP.
- [OpenJDK JEP 321 — HTTP Client (Standard)](https://openjdk.org/jeps/321): Java HTTP Client chuẩn từ Java 11.

**Kết luận:** body lớn phải được kiểm soát bằng **ba ngân sách tách biệt — byte, tài nguyên và tốc độ**. Publisher dạng streaming giảm nhu cầu giữ toàn bộ dữ liệu trong RAM; byte counter bảo vệ dung lượng; limiter theo thời gian và concurrency kiểm soát tốc độ/tải. Các cơ chế `Flow` và HTTP giúp điều phối truyền dữ liệu nhưng **không tự thay thế chính sách quota của ứng dụng hoặc server**.