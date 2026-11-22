# Không gom nội dung không giới hạn vào bộ nhớ (Body streaming, Java 11+)

**Chủ đề cha: Body streaming.** Khi gọi HTTP bằng `java.net.http.HttpClient`, response body có thể chỉ vài byte hoặc lên tới hàng gigabyte; có khi không biết trước kích thước, chưa đến EOF, hoặc dữ liệu được gửi liên tục. Nếu chương trình **gom toàn bộ body** thành `String`, `byte[]`, `List` hoặc `ByteArrayOutputStream` mà không giới hạn, mức sử dụng heap có thể tăng cùng với dữ liệu đầu vào, gây GC nặng, giảm khả năng phục vụ hoặc `OutOfMemoryError`.

**Ý chính:** xử lý body theo luồng (*streaming*) và đặt **hạn mức byte thực nhận/ghi**, cộng thêm giới hạn thời gian và tài nguyên, thay vì tin rằng nội dung luôn nhỏ. Các API trong bài đã có từ Java 11 và vẫn được hỗ trợ trong Java hiện đại. Mọi ví dụ hoàn chỉnh dùng JDK 11 trở lên.

## 1. Gom toàn bộ body khác với streaming ra sao?

Hình dung server trả 500 MB:

```text
HTTP server
   |
   |   500 MB response body
   v
HttpClient
   +-- BodyHandlers.ofByteArray() -> byte[] chứa toàn bộ body
   +-- BodyHandlers.ofString() ----> String chứa toàn bộ nội dung đã giải mã
   +-- BodyHandlers.ofInputStream() -> InputStream -> đọc chunk -> xử lý
   +-- BodyHandlers.ofFile(path) ---> ghi tới đĩa
   +-- BodyHandlers.ofLines() -----> Stream<String> -> xử lý lần lượt từng dòng
   +-- BodyHandlers.ofPublisher() -> Flow.Publisher<List<ByteBuffer>>
   +-- BodyHandlers.discarding() --> bỏ dữ liệu nếu không cần body
```

Với kiểu **tích lũy**, ứng dụng phải giữ lượng dữ liệu có kích thước tỷ lệ với body. Với kiểu **streaming**, ứng dụng có thể tiêu thụ một khối nhỏ rồi tiếp tục khối kế tiếp. Nếu từng khối được ghi xuống file, gửi tiếp hoặc xử lý rồi loại bỏ, bộ nhớ do chính vòng lặp của ta cấp phát có thể giữ ở kích thước cố định.

Nhưng streaming **không tự đảm bảo** tổng bộ nhớ sử dụng cố định. Ví dụ chọn `ofInputStream()` rồi gọi `readAllBytes()` vẫn gom toàn bộ vào mảng; chọn `ofLines()` rồi `collect(toList())` vẫn giữ mọi dòng. Cần kiểm tra **toàn bộ pipeline**, từ HTTP handler, bộ giải mã, parser, cache, queue tới storage.

## 2. Chọn đúng BodyHandler

| Handler | Body kiểu Java | Đặc điểm |
| --- | --- | --- |
| `ofString()` | `String` | Gom và giải mã toàn bộ body; thuận tiện với response **đã có giới hạn nhỏ** |
| `ofByteArray()` | `byte[]` | Gom toàn bộ bytes vào heap; tránh với nguồn không có giới hạn |
| `ofInputStream()` | `InputStream` | Đọc từng khối, áp dụng byte limit, ghi file hay xử lý trực tiếp |
| `ofLines()` | `Stream<String>` | Đọc theo dòng; một dòng quá dài vẫn có thể tốn nhiều bộ nhớ |
| `ofFile(Path)` | `Path` | Ghi body xuống đĩa, không gom heap nhưng **không giới hạn dung lượng đĩa** |
| `ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Reactive streaming và backpressure, đòi hỏi subscriber quản lý tài nguyên |
| `discarding()` | `Void` | Đọc rồi bỏ body khi không cần nội dung |

Các handler dựng sẵn này **không tự xem HTTP status để quyết định có nhận body không**. Một response HTTP 500 vẫn có body, và `ofFile(path)` có thể ghi luôn body lỗi. Nếu nghiệp vụ chỉ chấp nhận 2xx, phải kiểm tra status và chọn cách xử lý phù hợp.

### Những đoạn code nguy hiểm nếu kích thước không biết trước

```java
// Có thể chiếm bộ nhớ theo kích thước toàn bộ response.
HttpResponse<byte[]> a = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());

HttpResponse<String> b = client.send(
        request, HttpResponse.BodyHandlers.ofString());
```

Đây là **mã minh họa** trong phương thức đã có `client`, `request`, các import và xử lý checked exceptions. Nó không sai khi nội dung đã được kiểm soát nhỏ, nhưng không nên dùng mặc định cho một API trả file hoặc dữ liệu không xác định kích thước.

Đã chọn streaming cũng không đủ nếu kết quả lại bị tích lũy:

```java
// Anti-pattern: đọc hết body vào bộ nhớ.
try (InputStream input = response.body()) {
    byte[] everything = input.readAllBytes();
}

// Anti-pattern: nguồn streaming nhưng đích vẫn phình to.
ByteArrayOutputStream memory = new ByteArrayOutputStream();
input.transferTo(memory);

// Anti-pattern: giữ mọi dòng của response.
List<String> all = lineStream.collect(Collectors.toList());
```

Các đoạn trên **không phải chương trình độc lập**; `input`, `lineStream` và `response` là biến minh họa. `readAllBytes()`, `transferTo()` có trong Java 11, nhưng việc dùng chúng trên nguồn không giới hạn phải xét kỹ dung lượng và đích nhận dữ liệu.

## 3. ofInputStream(): header đã về, body có thể chưa về hết

`BodyHandlers.ofInputStream()` thường là lựa chọn dễ hiểu nhất nếu bạn muốn tự quản lý số byte đọc.

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    // Đọc body thành từng khối và kiểm tra hạn mức.
}
```

Đây là đoạn minh họa. Khi `send(...)` trả về đối tượng `HttpResponse<InputStream>`, **response headers đã đọc xong nhưng body có thể chưa nhận hết**. Mỗi lời gọi `body.read(...)` có thể chờ thêm dữ liệu mạng. Đừng nhầm việc đã nhận status 200 với việc toàn bộ payload đã được tải và lưu thành công.

**Vòng đời rất quan trọng:**

- Đọc đến EOF để tiêu thụ toàn bộ dữ liệu, hoặc gọi `InputStream.close()` khi không tiếp tục đọc.
- Đóng sớm có thể khiến kết nối HTTP bên dưới không được tái sử dụng, nhưng cần thiết nếu body quá lớn hoặc response không hợp lệ.
- Dùng `try-with-resources` để bảo đảm stream đóng cả khi ném ngoại lệ.
- Không bỏ rơi `response.body()` sau khi đọc status/headers; kết nối và các tác vụ liên quan có thể bị giữ.
- Trong Java 11, `HttpClient` **không** có `AutoCloseable/close()` như các JDK từ Java 21; không dùng `try (HttpClient client = ...)` nếu biên dịch bằng `--release 11`.

### Kiểm tra status mà không gom error body

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    if (response.statusCode() != 200) {
        throw new IOException("HTTP status: " + response.statusCode());
    }
    // Đọc có giới hạn rồi xử lý/ghi tiếp.
}
```

Đoạn minh họa yêu cầu import `IOException` và các lớp HTTP. Vì body nằm trong `try-with-resources`, kể cả status 404/500 cũng không khiến stream bị bỏ mở. Nếu cần nội dung lỗi để log, chỉ đọc một **đoạn nhỏ có giới hạn**, không dùng `ofString()` trên error body không được kiểm soát.

## 4. Content-Length chỉ là một tín hiệu, không thay thế byte limit

Một số response có header `Content-Length`. Có thể xem để **từ chối sớm** nếu kích thước khai báo vượt ngưỡng:

```java
long maxBytes = 10L * 1024 * 1024;
OptionalLong declared = response.headers()
        .firstValueAsLong("Content-Length");

if (declared.isPresent() && declared.getAsLong() > maxBytes) {
    // Từ chối và đóng body trong try-with-resources.
}
```

Đây là đoạn minh họa. Cần import `java.util.OptionalLong`; nếu chuỗi header không phải số long hợp lệ thì `firstValueAsLong` có thể ném `NumberFormatException`.

**Vì sao vẫn phải đếm byte thực tế?**

1. Không phải mọi response có `Content-Length` (ví dụ có thể dùng chunked transfer hoặc các cơ chế khác).
2. Header từ bên ngoài không nên được tin là chính sách tài nguyên cuối cùng; có thể thiếu, sai, hoặc không mang thông tin mà ứng dụng mong đợi sau các bước xử lý.
3. Việc **giải nén** có thể khiến dữ liệu đầu ra lớn hơn nhiều so với số byte nén đầu vào. Nếu có giải nén, cần byte limit ở cả tầng nhận và tầng **sau giải nén**.
4. Không dùng `InputStream.available()` như tổng kích thước body: đó là ước lượng byte có thể đọc mà không block, không phải EOF hay Content-Length.

Một chính sách chặt chẽ thường bao gồm **max response bytes**, **max decompressed bytes**, số bản ghi/dòng, độ sâu cấu trúc, timeout, quota đĩa và số request đồng thời.

## 5. Thuật toán cốt lõi: đọc buffer cố định, đếm byte trước khi ghi

Một vòng lặp streaming có thể dùng `byte[8192]`, đếm `long total` và ghi tiếp từng khối. Kiểm tra `n > maxBytes - total` **trước khi ghi** giúp tránh vượt ngưỡng cũng như tránh lỗi cộng tràn số ở `total + n`.

### Ví dụ độc lập: `BoundedCopyDemo.java`

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public class BoundedCopyDemo {
    static final class LimitExceededException extends IOException {
        LimitExceededException() {
            super("Body exceeds configured byte limit");
        }
    }

    static long copyBounded(
            InputStream input, OutputStream output, long maxBytes)
            throws IOException {

        if (maxBytes < 0) {
            throw new IllegalArgumentException("Negative limit");
        }

        byte[] block = new byte[8192];
        long count = 0;
        int n;

        while ((n = input.read(block)) != -1) {
            if (n > maxBytes - count) {
                throw new LimitExceededException();
            }
            output.write(block, 0, n);
            count += n;
        }
        return count;
    }

    public static void main(String[] args) throws IOException {
        byte[] fixture = new byte[10_000];

        try (InputStream input = new ByteArrayInputStream(fixture);
             OutputStream output = OutputStream.nullOutputStream()) {
            System.out.println("accepted: "
                    + copyBounded(input, output, 12_000));
        }

        boolean rejected = false;
        try (InputStream input = new ByteArrayInputStream(fixture);
             OutputStream output = OutputStream.nullOutputStream()) {
            copyBounded(input, output, 5_000);
        } catch (LimitExceededException expected) {
            rejected = true;
        }
        System.out.println("rejected: " + rejected);
    }
}
```

Lệnh biên dịch và chạy bằng JDK 11+:

```bash
javac --release 11 -encoding UTF-8 BoundedCopyDemo.java
java BoundedCopyDemo
```

Stdout:

```text
accepted: 10000
rejected: true
```

**Phân tích:** Buffer `block` luôn 8192 byte, không tăng cùng input. Mảng `fixture` 10.000 byte là **dữ liệu test có kích thước biết trước**; trong production, `input` thường là response body. `OutputStream.nullOutputStream()` nhận rồi bỏ byte, phù hợp khi chỉ kiểm tra thuật toán và không muốn giữ nội dung.

Khi max bằng 5.000, một lần `read(block)` có thể nhận 8192 byte rồi phát hiện vượt ngưỡng; hàm ném exception **trước khi ghi khối đó**. Do đó nó giới hạn số **byte đã ghi**, không khẳng định chính xác số byte **đã đọc từ nguồn**. Muốn dừng đọc sau không quá `max+1` byte, hãy giới hạn độ dài mỗi lời gọi `read(buffer,0,len)` đến phần hạn mức còn lại, rồi thử đọc thêm đúng một byte để phân biệt EOF với input còn tiếp.

Dù có giới hạn, đích có thể đã nhận vài khối hợp lệ trước lúc gặp khối quá lớn. Nếu không chấp nhận file hỏng/thiếu, **ghi tệp tạm và chỉ đưa vào sử dụng khi hoàn tất**.

## 6. Ví dụ HTTP thực: dùng InputStream và tệp tạm có quota

Ví dụ sau tạo một HTTP server **loopback** (127.0.0.1) của JDK, trả đúng **8 khối × 2048 byte = 16.384 byte**. Không cần truy cập Internet.

Client gửi hai request bằng cùng một `HttpClient`:

- Request thứ nhất có max 20.000 byte: đọc hết và ghi tệp tạm, chuyển tệp tạm thành kết quả khi thành công.
- Request thứ hai có max 4.000 byte: từ chối khi vượt giới hạn, **xóa tệp tạm**, không sửa tệp kết quả từ request thứ nhất.

Hàm ghi tệp tạm dùng cùng thuật toán so sánh `n > maxBytes - total`. `close()` của stream nằm trong `try-with-resources` ở cả hai trường hợp.

### Ví dụ độc lập: `StreamingHttpDownload.java`

```java
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.util.Arrays;

public class StreamingHttpDownload {
    static final class TooLarge extends IOException {
        TooLarge() {
            super("Too many bytes");
        }
    }

    static long copyLimited(
            InputStream input, OutputStream output, long limit)
            throws IOException {
        if (limit < 0) {
            throw new IllegalArgumentException("Negative limit");
        }
        long total = 0;
        byte[] buffer = new byte[4096];
        int n;

        while ((n = input.read(buffer)) != -1) {
            if (n > limit - total) {
                throw new TooLarge();
            }
            output.write(buffer, 0, n);
            total += n;
        }
        return total;
    }

    static long save(InputStream input, Path destination, long limit)
            throws IOException {
        Path temp = Files.createTempFile(
                destination.getParent(), "download-", ".part");
        boolean moved = false;

        try {
            long count;
            try (OutputStream output = Files.newOutputStream(temp)) {
                count = copyLimited(input, output, limit);
            }
            Files.move(temp, destination,
                    StandardCopyOption.REPLACE_EXISTING);
            moved = true;
            return count;
        } finally {
            if (!moved) {
                Files.deleteIfExists(temp);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/download", exchange -> {
            byte[] chunk = new byte[2048];
            Arrays.fill(chunk, (byte) 'x');
            exchange.sendResponseHeaders(200, 8L * chunk.length);

            try (OutputStream out = exchange.getResponseBody()) {
                for (int i = 0; i < 8; i++) {
                    out.write(chunk);
                }
            } catch (IOException ignored) {
                // Client có thể đóng sớm khi vượt quota.
            }
        });

        Path dir = Files.createTempDirectory("stream-lesson-");
        Path destination = dir.resolve("result.bin");
        server.start();

        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/download");

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<InputStream> first = client.send(
                    request, HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = first.body()) {
                if (first.statusCode() != 200) {
                    throw new IOException("Unexpected status");
                }
                System.out.println("saved: "
                        + save(body, destination, 20_000));
            }

            HttpResponse<InputStream> second = client.send(
                    request, HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = second.body()) {
                if (second.statusCode() != 200) {
                    throw new IOException("Unexpected status");
                }
                try {
                    save(body, destination, 4_000);
                    throw new AssertionError("Expected quota failure");
                } catch (TooLarge expected) {
                    System.out.println("rejected: quota");
                }
            }

            System.out.println("previous file intact: "
                    + (Files.size(destination) == 16_384));
        } finally {
            try {
                Files.deleteIfExists(destination);
                Files.deleteIfExists(dir);
            } finally {
                server.stop(0);
            }
        }
    }
}
```

Biên dịch/chạy với module server test:

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 StreamingHttpDownload.java
java --add-modules jdk.httpserver StreamingHttpDownload
```

Stdout khi server loopback hoạt động bình thường:

```text
saved: 16384
rejected: quota
previous file intact: true
```

**Tại sao giữ được file hợp lệ?** Tệp đích chỉ bị thay thế **sau khi đã đọc hết body mà không vượt hạn mức**. Nếu `copyLimited` ném `TooLarge`, bước `Files.move` không chạy, tệp tạm bị xóa trong `finally`. Response InputStream cũng được đóng.

**Không nhầm với commit atomic:** `Files.move(temp,destination,REPLACE_EXISTING)` không đảm bảo mọi filesystem thay thế tệp nguyên tử. Nếu cần tính nguyên tử, xem xét `StandardCopyOption.ATOMIC_MOVE` và xử lý `AtomicMoveNotSupportedException` theo chính sách dự án.

**Về môi trường:** Ví dụ dùng socket loopback do chương trình tự mở; nếu sandbox chặn socket, kết quả có thể thất bại vì môi trường, không phải vì BodyHandler. Tình huống production cần thêm quota tổng dung lượng đĩa, xử lý URI/redirect không đáng tin, bảo vệ khỏi đường dẫn ngoài thư mục cho phép, checksum và giám sát tải.

## 7. ofFile() không tích lũy heap nhưng có thể làm đầy đĩa

`BodyHandlers.ofFile(target)` ghi body tới `Path`. Khi `send(...)` trả về `HttpResponse<Path>`, body đã được ghi xong vào file. Đây là cách đơn giản để tránh tạo một `byte[]` lớn, nhưng:

1. Không có sẵn byte limit của ứng dụng; server có thể gửi nhiều dữ liệu hơn dung lượng đĩa.
2. Handler dựng sẵn không phân biệt status 200 với 404/500 trước khi nhận body.
3. Khi xảy ra lỗi I/O giữa chừng, có thể phải dọn tệp không hoàn chỉnh.
4. Chọn đường dẫn từ nguồn đáng tin cậy; không ghép trực tiếp tên file do server/user không tin cậy cung cấp mà không kiểm soát.

Mẫu API (đoạn minh họa):

```java
HttpResponse<Path> result = client.send(
        request, HttpResponse.BodyHandlers.ofFile(target));

if (result.statusCode() != 200) {
    // Có thể target đã chứa body lỗi. Cần xử lý theo chính sách.
}
```

Nếu yêu cầu là **không bao giờ ghi quá N byte** và chỉ công bố file thành công, `ofInputStream` + bộ đếm + tệp tạm như mục trước cho phép kiểm soát rõ hơn. Với nhu cầu phức tạp, có thể viết `BodyHandler/BodySubscriber` riêng: `BodyHandler` có thể xét status/headers trước khi chọn subscriber.

## 8. ofLines() cũng có nguy cơ nếu một dòng rất dài

`BodyHandlers.ofLines()` trả `HttpResponse<Stream<String>>`. Nó thích hợp để tiêu thụ **dòng văn bản một cách tuần tự**, ví dụ dữ liệu line-oriented, và không cần tạo list chứa hết mọi dòng.

```java
HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    if (response.statusCode() != 200) {
        throw new IOException("Unexpected HTTP status");
    }
    lines.forEach(line -> {
        // Xử lý một dòng, không gom vào list.
    });
}
```

Đây là đoạn minh họa cần import `java.util.stream.Stream` và các lớp liên quan. `Stream<String>` phải được tiêu thụ hết hoặc đóng nếu dừng sớm, tương tự body dạng InputStream.

**Bẫy:** API trả một `String` cho mỗi dòng. Nếu server gửi một dòng không xuống hàng dài vài trăm MB, riêng việc **tạo một String cho dòng đó** đã có thể chiếm nhiều bộ nhớ, dù không collect toàn bộ. Kiểm tra `line.length()` sau khi có String có thể **quá muộn**.

Nếu yêu cầu là giới hạn **độ dài từng dòng/token**, cần đếm byte/ký tự trong lúc parse bằng buffer cố định hoặc chọn parser có giới hạn kích thước record, không chỉ dựa vào `ofLines()`.

## 9. ofPublisher() và backpressure

`BodyHandlers.ofPublisher()` trả `Flow.Publisher<List<ByteBuffer>>`. Publisher phát ra **các batch** chứa danh sách ByteBuffer. Subscriber thực hiện giao thức `Flow` và có thể chủ động xin thêm dữ liệu bằng `Flow.Subscription.request(n)`.

- `request(1)` là xin **một batch**, không phải đúng một byte.
- Publisher của body response chỉ cho **một subscriber** thực sự nhận dữ liệu; không dùng để đọc lại body nhiều lần.
- Subscriber phải xử lý các ByteBuffer có thứ tự; không tích lũy các batch vô hạn vào danh sách/queue.
- Đếm `buffer.remaining()` để áp dụng hạn mức **byte thực xử lý**, với kiểm tra trước khi cộng để tránh overflow.
- Nếu vượt hạn mức hoặc không xử lý tiếp, hãy `cancel()` subscription; ngừng sớm có thể ảnh hưởng khả năng tái sử dụng kết nối.
- Backpressure **không** bảo vệ khỏi consumer tự gom mọi byte hoặc một hàng đợi không có giới hạn; phải tự thiết kế queue, quota và chính sách lỗi.

Đoạn minh họa (không phải chương trình độc lập):

```java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.send(request, HttpResponse.BodyHandlers.ofPublisher());

Flow.Publisher<List<ByteBuffer>> publisher = response.body();
// Subscribe một lần; quản lý request(n), byte limit và cancel().
```

Nếu không cần reactive pipeline, `ofInputStream` với vòng đọc theo khối thường dễ kiểm thử hơn. `BodyHandlers.ofByteArrayConsumer(...)` cũng có thể đẩy các mảng byte cho consumer, nhưng tài liệu Java 11 cảnh báo subscriber đó **không được flow-control**; consumer chậm cần cân nhắc đặc biệt.

## 10. Timeout, giải nén, concurrency và các giới hạn khác

Byte limit chỉ là một lớp bảo vệ:

- **Timeout:** đặt `HttpRequest.Builder.timeout(Duration)`, connect timeout và chính sách chặn tác vụ chậm. Việc `send(ofInputStream())` đã trả headers không có nghĩa mọi bước đọc body/downstream đều được kiểm soát bằng cùng một timeout. Xem thêm read/idle timeout hoặc watchdog theo nhu cầu.
- **Giải nén:** nếu tầng ứng dụng giải nén gzip hoặc giải mã định dạng có hệ số nở lớn, cần hạn mức cả byte **trước** và **sau giải nén**. Một body nén nhỏ có thể mở rộng thành dữ liệu khổng lồ.
- **JSON/XML/CSV:** parser có thể tích lũy object tree, một chuỗi rất dài hoặc hàng triệu record. Dùng parser streaming và giới hạn độ sâu/số trường/độ dài token/record.
- **Tổng mức đồng thời:** 1000 request × buffer 8 KiB đã tốn nhiều hơn 1 request; còn có socket, executor, parser, file descriptor và queue. Đặt giới hạn request đang xử lý, quota theo tenant và chính sách backpressure.
- **File và bản ghi lỗi:** ghi vào file tạm; khi thất bại cần dọn partial file, không giữ mãi. Không log nguyên body lỗi chỉ để debug.
- **Bảo mật:** dữ liệu response là dữ liệu không tin cậy. Không dùng tên file/đường dẫn từ server mà không chuẩn hóa và giới hạn quyền truy cập; tránh log token, cookie hay payload nhạy cảm.
- **Kết nối:** đóng body sớm có thể khiến HTTP connection không tái sử dụng được. Đó không phải lý do để tiếp tục tải một body vô hạn; ưu tiên giới hạn tài nguyên.

### Phân biệt timeout với byte limit

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(20))
        .GET()
        .build();
```

Đây là đoạn minh họa. Timeout hạn chế **thời gian** theo hợp đồng request; byte limit hạn chế **dung lượng** mà chương trình xử lý. Cần cả hai, cộng thêm chính sách xử lý tình trạng đọc body bị chặn hoặc nguồn không kết thúc.

## 11. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách tránh |
| --- | --- | --- |
| Dùng `ofString()/ofByteArray()` cho response không kiểm soát kích thước | Heap tăng theo payload | Streaming và giới hạn byte |
| Chọn `ofInputStream()` rồi `readAllBytes()` | Vẫn gom toàn bộ | Đọc khối cố định |
| `transferTo(new ByteArrayOutputStream())` | Output đích tăng vô hạn | Ghi file có quota hoặc xử lý trực tiếp |
| Chỉ kiểm tra `Content-Length` | Thiếu/sai header không được bảo vệ | Đếm byte thực tế |
| Dùng `ofFile()` không quota | Đầy đĩa | Giới hạn dung lượng và dọn partial |
| Gặp 500 vẫn lưu body vào file | File chứa trang lỗi | Kiểm tra status/chọn BodyHandler |
| Không đóng InputStream khi dừng sớm | Giữ tài nguyên kết nối | try-with-resources và cancel |
| Dùng `ofLines()` với dòng không giới hạn | Một String vẫn có thể rất lớn | Giới hạn độ dài line lúc parse |
| Subscriber yêu cầu dữ liệu không giới hạn rồi tích lũy | OOM dù có Flow API | Backpressure và quota |
| Dồn kết quả vào `List`/cache | Streaming không còn hiệu quả | Xử lý từng item và bỏ |
| Không có giới hạn concurrency | Tổng buffer/socket/task quá lớn | Admission control, timeout, quota |

## 12. Bộ regression test cho giới hạn byte

Không cần tạo dữ liệu gigabyte trong unit test. Chỉ cần các biên nhỏ nhưng sát hợp đồng: rỗng, đúng hạn mức, vượt một byte, vượt một khối và hạn mức âm. Bài test Java thuần dưới đây ném `AssertionError` khi sai; không phụ thuộc vào JVM option `-ea` của câu lệnh `assert`.

### `StreamingLimitRegression.java`

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public class StreamingLimitRegression {
    private static int checks = 0;

    static void check(String name, boolean ok) {
        checks++;
        if (!ok) {
            throw new AssertionError(name);
        }
    }

    static final class TooLarge extends IOException {
        TooLarge() {
            super("Limit exceeded");
        }
    }

    static long copy(InputStream input, OutputStream output, long limit)
            throws IOException {
        if (limit < 0) {
            throw new IllegalArgumentException("Negative limit");
        }
        byte[] buffer = new byte[4096];
        long total = 0;
        int count;

        while ((count = input.read(buffer)) != -1) {
            if (count > limit - total) {
                throw new TooLarge();
            }
            output.write(buffer, 0, count);
            total += count;
        }
        return total;
    }

    public static void main(String[] args) throws IOException {
        try (InputStream in = new ByteArrayInputStream(new byte[0]);
             OutputStream out = OutputStream.nullOutputStream()) {
            check("empty", copy(in, out, 0) == 0);
        }

        try (InputStream in = new ByteArrayInputStream(new byte[4096]);
             OutputStream out = OutputStream.nullOutputStream()) {
            check("exact", copy(in, out, 4096) == 4096);
        }

        boolean oneExtra = false;
        try (InputStream in = new ByteArrayInputStream(new byte[4097]);
             OutputStream out = OutputStream.nullOutputStream()) {
            copy(in, out, 4096);
        } catch (TooLarge expected) {
            oneExtra = true;
        }
        check("one extra byte", oneExtra);

        boolean smallerLimit = false;
        try (InputStream in = new ByteArrayInputStream(new byte[10_000]);
             OutputStream out = OutputStream.nullOutputStream()) {
            copy(in, out, 5_000);
        } catch (TooLarge expected) {
            smallerLimit = true;
        }
        check("small limit", smallerLimit);

        boolean negative = false;
        try (InputStream in = new ByteArrayInputStream(new byte[1]);
             OutputStream out = OutputStream.nullOutputStream()) {
            copy(in, out, -1);
        } catch (IllegalArgumentException expected) {
            negative = true;
        }
        check("negative limit", negative);

        System.out.println("PASS: " + checks + " checks");
    }
}
```

```bash
javac --release 11 -encoding UTF-8 StreamingLimitRegression.java
java StreamingLimitRegression
```

```text
PASS: 5 checks
```

Có năm ca test độc lập, gồm kiểm tra thành công và từ chối. Một unit test từ `ByteArrayInputStream` **không thể** thay thế integration test về HTTP status, socket đóng giữa chừng, timeout và file I/O lỗi; các hành vi đó cần fixture chuyên biệt.

### Checklist test tích hợp nên bổ sung

- Server không trả Content-Length; client vẫn thực thi byte limit.
- Server khai báo kích thước nhỏ nhưng gửi nhiều hơn hoặc response không kết thúc; ứng dụng không lưu vượt quota.
- HTTP 400/500 có body lớn; không gom error body không giới hạn.
- Kết nối mất giữa chừng; file tạm bị xóa, không báo download thành công.
- Đóng/cancel trước EOF; không giữ tài nguyên vô hạn.
- Nhiều download đồng thời; áp dụng quota tổng và tài nguyên đích.
- Một dòng cực dài, một token JSON lớn hoặc dữ liệu nén nở mạnh; giới hạn ở tầng parse/giải nén có hiệu lực.

## 13. Câu hỏi củng cố

**A.** `BodyHandlers.ofInputStream()` có tự động bảo đảm ứng dụng không bao giờ gom toàn bộ body không?

**B.** Nếu server gửi `Content-Length: 1000`, có thể bỏ việc đếm byte thực đọc không?

**C.** Khi `send(request, ofInputStream())` trả về response 200, có thể coi file đã tải hoàn tất không?

**D.** Tại sao `BodyHandlers.ofFile(path)` vẫn có thể gây lỗi tài nguyên?

**E.** Nếu `ofLines()` được dùng với một dòng dài 200 MB, mã `line.length() > 1000` có bảo vệ bộ nhớ trước khi String được tạo không?

**F.** Khi vượt quota sau vài khối ghi, làm sao tránh công bố file thiếu dữ liệu như một file hợp lệ?

**G.** `Flow.Subscription.request(1)` tương ứng với một byte hay một batch?

**Đáp án:** A. Không: gọi `readAllBytes()` hoặc gom kết quả vào list/mảng vẫn có rủi ro. B. Không: phải đếm thực tế, Content-Length là thông tin hỗ trợ. C. Không: có thể mới nhận headers; phải đọc hết và kiểm tra. D. Vì có thể ghi file khổng lồ và làm đầy đĩa. E. Không: String dòng rất dài có thể đã được cấp phát trước lúc kiểm tra. F. Ghi tệp tạm, chỉ move/commit sau khi đọc hết trong hạn mức, xóa khi thất bại. G. Một **batch** gồm một hoặc nhiều ByteBuffer.

## Nguồn tài liệu chính thức

- [Java SE 11 — HttpResponse.BodyHandlers: ofInputStream, ofLines, ofFile, ofPublisher, ofByteArray, ofString](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html).
- [Java SE 11 — HttpResponse.BodySubscribers: vòng đời stream và dữ liệu theo luồng](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html).
- [Java SE 11 — HttpResponse.BodySubscriber và Flow API](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html).
- [Java SE 11 — HttpResponse.BodyHandler: chọn subscriber theo status/headers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html).
- [Java SE 11 — InputStream: read, readAllBytes, transferTo, close](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html).
- [Java SE 21 — HttpClient: các phương thức quản lý vòng đời được bổ sung](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html).
