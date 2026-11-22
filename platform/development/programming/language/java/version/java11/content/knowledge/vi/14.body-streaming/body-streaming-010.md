# Java 11 — Kiểm thử tải lớn, người đọc chậm và ngắt giữa chừng

**Chủ đề:** Java 11 → Body streaming. Bài học tập trung vào kiểm thử **HTTP response body được nhận theo luồng** bằng API chuẩn `java.net.http.HttpClient`: xử lý payload lớn mà không gom hết vào RAM, giả lập **consumer đọc chậm**, kiểm chứng **đóng sớm/cancel**, và phát hiện **server ngắt kết nối khi chưa gửi đủ body**. Nội dung chỉ dùng kiến thức vẫn áp dụng hiện nay và API có trong Java 11; không dựa vào HTTP Client incubator cũ, virtual thread, record hay những API chỉ có ở phiên bản Java mới hơn.

**Mục tiêu học:** Hiểu vòng đời `BodyHandlers.ofInputStream()` và `ofPublisher()`; xây fixture local tái hiện ba tình huống; đo số byte, tính toàn vẹn, thời gian và tài nguyên; phân biệt EOF hợp lệ với body bị cắt; kiểm thử backpressure, timeout và cleanup; tránh unit test phụ thuộc thời gian mạng và cơ chế buffer ngẫu nhiên.

## 1. Vì sao body streaming cần một chiến lược kiểm thử khác?

Với response nhỏ:

~~~java
HttpResponse<byte[]> response = client.send(
    request, HttpResponse.BodyHandlers.ofByteArray());
~~~

Đây là **đoạn minh họa**: `client`/`request` đã được khai báo. `ofByteArray()` phải gom dữ liệu body vào mảng byte trước khi response hoàn tất. Cách này thuận tiện cho JSON/ảnh nhỏ đã được giới hạn kích thước, nhưng rủi ro khi nhận file hàng trăm MB hoặc dữ liệu không đáng tin cậy.

Đối với body lớn:

~~~java
HttpResponse<InputStream> response = client.send(
    request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = body.read(buffer)) != -1) {
        consume(buffer, 0, n);
    }
}
~~~

Đây là **đoạn minh họa**, `consume` là hàm ứng dụng và code phải xử lý `IOException`/`InterruptedException`. `ofInputStream()` có trên Java 11. Khi `send` trả `HttpResponse<InputStream>`, **headers đã đến, nhưng body có thể chưa được nhận hết**. Phần đọc tiếp tục diễn ra trong vòng lặp sau đó.

Điểm cốt lõi: **nhận được status 200 và một InputStream không có nghĩa đã tải xong nội dung**. Test phải đọc tới EOF hợp lệ, kiểm byte count/checksum/schema, và đóng stream trong cả nhánh thành công lẫn thất bại.

### 1.1. API streaming của Java 11

| BodyHandler | Kiểu trả về của response | Đặc điểm | Quy tắc tài nguyên |
| --- | --- | --- | --- |
| `BodyHandlers.ofByteArray()` | `byte[]` | Gom hết body trong RAM. | Chỉ dùng khi size đã kiểm soát. |
| `BodyHandlers.ofString(charset)` | `String` | Gom và giải mã toàn bộ body. | Không dành cho body khổng lồ. |
| `BodyHandlers.ofInputStream()` | `InputStream` | Stream từng phần khi bytes đến. | Đọc tới EOF **hoặc đóng** khi dừng. |
| `BodyHandlers.ofLines()` | `Stream<String>` | Giải mã theo dòng. | Tiêu thụ hết **hoặc đóng** Stream. |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Luồng reactive, subscriber kiểm soát demand. | Subscribe **đúng một lần**, đi tới terminal event hoặc cancel. |
| `BodyHandlers.ofFile(path)` | `Path` | Ghi body xuống file. | Kiểm soát path, dung lượng và cleanup file partial. |
| `BodyHandlers.discarding()` | `Void` | Tiêu thụ và bỏ bytes. | Không phù hợp khi cần kiểm body thực nhận. |

`BodyHandlers.ofByteArrayConsumer(...)` có trên Java 11 nhưng **subscriber của factory này không flow-controlled** theo tài liệu JDK. Không chọn nó làm bằng chứng “consumer chậm sẽ tạo backpressure an toàn” nếu callback xử lý dữ liệu chậm hoặc bị block.

**Phân biệt hai chiều:** `HttpRequest.BodyPublisher` phát **request body đi lên server**. Bài này chủ yếu xử lý `HttpResponse.BodyHandler` và `BodySubscriber` nhận **response body từ server**. Khi thiết kế integration test hai chiều (upload/download), cần kiểm riêng cả producer và consumer.

## 2. Ba nhóm kiểm thử và các câu hỏi phải trả lời

### 2.1. Tải lớn (large body)

Cần chứng minh:

- Client xử lý **đủ N byte** mà không dùng một mảng có kích thước N chỉ để nhận dữ liệu.
- Mọi lần `read(buffer)` đều xử lý **đúng `n` byte vừa đọc**, không dùng `buffer.length` khi chưa được lấp đầy.
- Nội dung không sai thứ tự, mất chunk, lặp chunk hoặc bị đổi mã hóa.
- Không có tăng RAM/GC bất thường tỷ lệ với kích thước body do **ứng dụng** lưu trữ.
- Body thực sự kết thúc bình thường và HTTP status/schema hợp lệ.
- Không mất tài nguyên: đóng InputStream, file tạm, socket/stream trong các nhánh lỗi.

### 2.2. Người đọc chậm (slow consumer)

Cần chứng minh:

- Client vẫn đúng khi đọc mỗi lần ít byte hoặc nghỉ giữa các lần xử lý.
- Không tự tạo queue vô hạn giữa network và downstream.
- Có chính sách timeout/deadline và giới hạn tài nguyên khi consumer chậm kéo dài.
- Nếu dùng `Flow.Publisher`, demand được quản lý đúng; không gửi tín hiệu `request(n)` quá mức có thể xử lý.
- Việc giảm tốc không làm tăng số byte cuối cùng hoặc đổi thứ tự dữ liệu.

**Lưu ý quan trọng:** Một `Thread.sleep(2)` sau mỗi lượt đọc **chỉ mô phỏng ứng dụng tiêu thụ chậm**. OS socket buffer và buffer nội bộ của JDK có thể hấp thụ toàn bộ response nhỏ trước khi bạn thấy network backpressure. Để kết luận producer bị làm chậm thực sự, cần tải đủ lớn, đo tốc độ gửi ở server, queue depth, heap/RSS và trạng thái demand dưới môi trường kiểm soát được.

### 2.3. Ngắt giữa chừng (interrupted transfer)

Có **ít nhất hai** tình huống khác nhau:

1. **Client chủ động ngừng đọc**: người dùng hủy download, đạt giới hạn dữ liệu hoặc đóng `InputStream` sớm. Đây là hành vi ứng dụng quyết định, không phải bằng chứng server truyền sai.
2. **Server/đường truyền dừng sớm**: body đã công bố một độ dài nhưng truyền thiếu hoặc TCP connection bị reset. Đây là download **không hoàn chỉnh** và không được publish thành công.
3. Một tình huống liên quan là **thread bị interrupt/timeout/cancel future**. Thời điểm hủy không bảo đảm server chưa gửi/nhận gì; cleanup và trạng thái nghiệp vụ cần tách riêng.

Test không nên chỉ mong một exception class duy nhất cho mọi OS/JDK/proxy. Khi byte count mong đợi đã biết, hãy phát hiện **thiếu byte** dù thư viện ném `IOException` hay báo EOF sớm. Với body không biết length, cần checksum, trailer/manifest hoặc framing/schema đủ mạnh để xác định tính hoàn chỉnh theo hợp đồng.

## 3. Kế hoạch kiểm thử có thể đo được

| Case | Fixture | Assertion chính | Tránh khẳng định |
| --- | --- | --- | --- |
| Large fixed length | Server sinh 2 MiB byte `'Z'` theo block 4 KiB | Nhận đúng 2.097.152 byte; tất cả là `Z`. | “Heap của cả JVM không vượt 8 KiB”. |
| Slow reader | Server sinh 64 KiB; client ngủ ngắn sau mỗi lần đọc | Nhận đúng 65.536 byte, không mất hoặc lặp. | “Server chắc chắn bị TCP backpressure”. |
| Early close | Server bắt đầu gửi 2 MiB; client chỉ đọc 4 KiB rồi đóng | Client đã đọc đúng 4.096 byte, tài nguyên được đóng. | “Server chắc chắn dừng ngay tại byte 4.096”. |
| Abrupt truncation | Raw server khai `Content-Length: 32768` nhưng gửi 1024 byte | Nhận diện thiếu body bằng exception **hoặc** byte count. | Exception message giống nhau giữa JDK. |
| Empty response | Content-Length 0 hoặc status 204 đúng hợp đồng | EOF hợp lệ, không tự coi là lỗi. | “Mọi EOF đều là lỗi”. |
| Unknown length | Chunked HTTP/1.1 hoặc H2 không có Content-Length | Theo dõi EOF framing và checksum/schema riêng. | “Không có Content-Length = lỗi”. |
| Large concurrency | N response đồng thời, mỗi response có budget | Không OOM, không leak, không đổi body giữa request. | “Một request pass chứng minh N request pass”. |

**Bộ đo cốt lõi:** số byte mong đợi và thực nhận; checksum/hash khi cần; status và Content-Type; latency/throughput (p50/p95/p99); thời gian chờ read; số request lỗi/timed out; RSS/heap/GC, CPU, socket/FD, số stream đang mở và dữ liệu chưa xử lý. Phân biệt chỉ số **đầu vào/đầu ra của ứng dụng** với metric do OS/network cung cấp.

## 4. Chương trình Java 11 hoàn chỉnh: cả ba tình huống trong một lần chạy

Chương trình sau dùng `HttpServer` cục bộ cho tải lớn, người đọc chậm và đóng sớm; dùng một `ServerSocket` TCP tối giản để **cố ý gửi HTTP/1.1 response thiếu byte**. Nó chỉ cần JDK 11, không truy cập Internet và không có dependency ngoài. Tất cả endpoint bind vào loopback `127.0.0.1` và sử dụng cổng động.

- `/large` trả 2 MiB ký tự byte `'Z'`, được tạo **theo từng block 4096 byte**, không phân bổ mảng 2 MiB tại server.
- `/slow` trả 64 KiB tương tự, nhưng client nghỉ 2 ms sau mỗi `read` để mô phỏng consumer chậm.
- `/early` trả 2 MiB, client chỉ đọc đủ 4096 byte rồi đóng stream dù body chưa được ứng dụng tiêu thụ hết.
- Raw HTTP test trả header `Content-Length: 32768` rồi **chỉ gửi 1024 byte**, đóng socket để kích hoạt phát hiện body bị cắt.

**Lưu nguyên vẹn thành tệp `StreamingLoadDemo.java`:**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicBoolean;

public final class StreamingLoadDemo {
    static final int LARGE = 2 * 1024 * 1024;
    static final int SLOW = 64 * 1024;

    private StreamingLoadDemo() {
    }

    static final class Result {
        final long bytes;
        final boolean valid;

        Result(long bytes, boolean valid) {
            this.bytes = bytes;
            this.valid = valid;
        }
    }

    private static void serve(HttpExchange exchange, int size)
            throws IOException {
        byte[] block = new byte[4096];
        Arrays.fill(block, (byte) 'Z');
        try {
            exchange.getResponseHeaders().set(
                "Content-Type", "application/octet-stream");
            exchange.sendResponseHeaders(200, size);
            try (OutputStream out = exchange.getResponseBody()) {
                for (int left = size; left > 0; ) {
                    int n = Math.min(left, block.length);
                    out.write(block, 0, n);
                    left -= n;
                }
            }
        } finally {
            exchange.close();
        }
    }

    static Result consume(InputStream in, boolean slow)
            throws IOException, InterruptedException {
        byte[] buf = new byte[2048];
        long total = 0;
        boolean valid = true;
        int n;
        while ((n = in.read(buf)) != -1) {
            for (int i = 0; i < n; i++) {
                if (buf[i] != (byte) 'Z') {
                    valid = false;
                }
            }
            total += n;
            if (slow) {
                Thread.sleep(2);
            }
        }
        return new Result(total, valid);
    }

    static long readBounded(InputStream in, long maxBytes)
            throws IOException {
        byte[] buf = new byte[2048];
        long total = 0;
        int n;
        while ((n = in.read(buf)) != -1) {
            if (n > maxBytes - total) {
                throw new IOException("Response exceeds byte limit");
            }
            total += n;
        }
        return total;
    }

    private static HttpRequest request(URI uri) {
        return HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(15))
            .GET()
            .build();
    }

    private static Result fetch(HttpClient client, URI uri,
            boolean slow) throws Exception {
        HttpResponse<InputStream> response = client.send(
            request(uri), HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream in = response.body()) {
            if (response.statusCode() != 200) {
                throw new IOException("Unexpected HTTP status");
            }
            return consume(in, slow);
        }
    }

    private static int stopEarly(HttpClient client, URI uri)
            throws Exception {
        HttpResponse<InputStream> response = client.send(
            request(uri), HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream in = response.body()) {
            if (response.statusCode() != 200) {
                throw new IOException("Unexpected HTTP status");
            }
            byte[] buf = new byte[512];
            int total = 0;
            while (total < 4096) {
                int n = in.read(
                    buf, 0, Math.min(buf.length, 4096 - total));
                if (n == -1) {
                    throw new EOFException("Body ended early");
                }
                total += n;
            }
            return total;
        } // Đóng sớm: không tự đọc hết 2 MiB.
    }

    private static boolean truncatedResponse(HttpClient client)
            throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (ServerSocket listener =
                 new ServerSocket(0, 1, loopback)) {
            listener.setSoTimeout(5000);
            AtomicBoolean sent = new AtomicBoolean(false);

            Thread sender = new Thread(() -> {
                try (Socket socket = listener.accept()) {
                    socket.setSoTimeout(5000);

                    InputStream in = socket.getInputStream();
                    int[] end = {13, 10, 13, 10};
                    int state = 0;
                    int inspected = 0;
                    while (state < 4 && inspected < 16384) {
                        int c = in.read();
                        if (c < 0) {
                            throw new EOFException("Request incomplete");
                        }
                        inspected++;
                        state = (c == end[state])
                            ? state + 1 : (c == 13 ? 1 : 0);
                    }
                    if (state != 4) {
                        throw new IOException("Request header too large");
                    }

                    OutputStream out = socket.getOutputStream();
                    String headers =
                        "HTTP/1.1 200 OK\r\n" +
                        "Content-Type: application/octet-stream\r\n" +
                        "Content-Length: 32768\r\n" +
                        "Connection: close\r\n\r\n";
                    out.write(headers.getBytes(
                        StandardCharsets.US_ASCII));
                    out.write(new byte[1024]);
                    out.flush();
                    sent.set(true);
                    // Kết thúc socket sớm, không gửi đủ 32768 byte.
                } catch (IOException ignored) {
                    // Fixture được kiểm tra qua sent ở cuối.
                }
            }, "truncated-response-fixture");

            sender.setDaemon(true);
            sender.start();

            URI uri = URI.create(
                "http://127.0.0.1:" + listener.getLocalPort() + "/cut");

            boolean failed = false;
            long received = 0;
            try {
                HttpResponse<InputStream> response = client.send(
                    request(uri),
                    HttpResponse.BodyHandlers.ofInputStream());
                try (InputStream in = response.body()) {
                    byte[] buf = new byte[1024];
                    int n;
                    while ((n = in.read(buf)) != -1) {
                        received += n;
                    }
                }
            } catch (IOException e) {
                failed = true;
            }

            sender.join(2000);
            if (!sent.get()) {
                throw new IllegalStateException(
                    "Truncation fixture did not send response");
            }
            return failed || received != 32768L;
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/large", e -> serve(e, LARGE));
        server.createContext("/slow", e -> serve(e, SLOW));
        server.createContext("/early", e -> {
            try {
                serve(e, LARGE);
            } catch (IOException ignored) {
                // Client có thể đã đóng stream giữa khi server ghi.
            }
        });
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .followRedirects(HttpClient.Redirect.NEVER)
                .connectTimeout(Duration.ofSeconds(3))
                .build();

            String base = "http://127.0.0.1:" +
                server.getAddress().getPort();

            Result large = fetch(
                client, URI.create(base + "/large"), false);
            if (large.bytes != LARGE || !large.valid) {
                throw new AssertionError("Large body mismatch");
            }
            System.out.println("large.bytes=" + large.bytes);
            System.out.println("large.valid=" + large.valid);

            Result slow = fetch(
                client, URI.create(base + "/slow"), true);
            if (slow.bytes != SLOW || !slow.valid) {
                throw new AssertionError("Slow body mismatch");
            }
            System.out.println("slow.bytes=" + slow.bytes);
            System.out.println("slow.valid=" + slow.valid);

            int early = stopEarly(
                client, URI.create(base + "/early"));
            System.out.println("early.read=" + early);

            System.out.println("truncated.detected=" +
                truncatedResponse(client));
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 11 với tệp source UTF-8; module `jdk.httpserver` là module JDK phục vụ fixture, không phải production server:

~~~bash
javac -encoding UTF-8 --add-modules jdk.httpserver StreamingLoadDemo.java
java --add-modules jdk.httpserver StreamingLoadDemo
~~~

**Stdout kỳ vọng khi loopback hoạt động bình thường và các assertion đều đạt:**

~~~text
large.bytes=2097152
large.valid=true
slow.bytes=65536
slow.valid=true
early.read=4096
truncated.detected=true
~~~

**Giải thích và giới hạn của kết quả:**

1. Server tạo buffer 4096 byte rồi tái sử dụng để ghi; client dùng buffer 2048 byte để đọc. Chương trình **không chủ ý giữ cả 2 MiB response vào một mảng**. Tuy nhiên, điều đó **không chứng minh tổng heap/RSS của JVM đúng bằng 2048/4096 byte**: JDK, OS và HTTP implementation vẫn có bộ đệm riêng.
2. Hàm `consume` kiểm từng byte có bằng `Z` hay không, cộng đúng số `n` trả về từ `read`. Response có 2 MiB nên số byte chính xác `2 × 1024 × 1024 = 2.097.152`.
3. Case `slow` ngủ 2 ms sau mỗi lượt đọc. Tổng số byte vẫn 65.536; **không assert số lượt read hoặc tổng thời gian**, vì việc chia chunk phụ thuộc nhiều tầng.
4. `stopEarly` chủ động đọc đúng 4 KiB rồi đóng `InputStream`. Đây là một **early close có kiểm soát**, không phải test chắc chắn server đã ngừng gửi tại thời điểm đó: dữ liệu có thể đang nằm trong socket buffers.
5. Raw fixture gửi response header nêu rõ `Content-Length: 32768` nhưng chỉ gửi 1024 byte rồi đóng socket. Client phải nhận ra không đầy đủ; code coi **`IOException` hoặc byte count nhỏ hơn 32768** đều là bằng chứng lỗi.
6. Raw fixture **chỉ phục vụ HTTP/1.1** và chỉ dùng cho kiểm thử trên loopback; không phải HTTP server đủ chức năng. Nó chờ đến hết request headers rồi mới trả response, tránh nhầm “client chưa gửi gì” thành lỗi truncation.
7. Nếu thread fixture không phát được response, chương trình ném `IllegalStateException` thay vì in một kết quả “pass” giả. Nếu bind/connect loopback bị cấm, demo cũng không có đủ stdout như trên.
8. `server.stop(0)` dọn server cục bộ; stream client đều được đóng với `try-with-resources`. Case client ngừng đọc có thể khiến server ghi gặp `IOException` và đó là hành vi có thể dự kiến của fixture này.
9. Dùng cùng `HttpClient` với `HTTP_1_1` để các endpoint local đơn giản, không nhằm chứng minh hiệu năng HTTP/2. Trên hệ thống thực, stream/cancel có thể diễn ra khác giữa hai phiên bản giao thức.

## 5. Không giả định read() sẽ lấp đầy mảng

Giả sử:

~~~java
byte[] buf = new byte[8192];
int n = in.read(buf);
~~~

`n` có thể là một số **nhỏ hơn 8192**, ngay cả khi vẫn còn hàng MB dữ liệu ở phía server. Chỉ vùng `[0,n)` mới là dữ liệu hợp lệ của lượt đọc. Nếu dùng `new String(buf, UTF_8)` hoặc `digest.update(buf)` mà không truyền số byte `n`, bạn có thể nạp byte cũ ở cuối mảng, làm sai checksum hoặc định dạng.

Đúng khi tính hash:

~~~java
MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
byte[] buf = new byte[8192];
int n;
long total = 0;
while ((n = in.read(buf)) != -1) {
    sha256.update(buf, 0, n);
    total += n;
}
byte[] digest = sha256.digest();
~~~

Đây là **đoạn minh họa** với `in` là `InputStream` đã được quản lý và các import `java.security.MessageDigest`; cần xử lý `NoSuchAlgorithmException` và `IOException`. SHA-256 dùng để đối chiếu nội dung với hash đáng tin cậy, **không chỉ** xác nhận byte count. Nếu file đến từ nguồn không tin cậy, hash do chính cùng nguồn gửi qua kênh không xác thực không phải bằng chứng chống giả mạo.

### 5.1. Đọc ít byte liên tục không phải lỗi

Khi consumer chậm hoặc mạng chia nhiều phần, `read` có thể trả 1 byte, 7 byte, 4096 byte... miễn là hợp đồng InputStream được tôn trọng. **Không** áp đặt:

~~~java
int n = in.read(buf);
if (n < buf.length) {
    throw new IOException("Wrong response size");
}
~~~

Đây là **đoạn cố tình sai**. Lượt đọc ngắn hoàn toàn bình thường. EOF `-1` chỉ đánh dấu hết stream; tính hợp lệ của EOF phụ thuộc framing/protocol và dữ liệu dự kiến.

## 6. Đọc đủ byte: Content-Length và EOF

Nếu server công bố `Content-Length` đáng tin theo giao thức, kết quả tải hoàn chỉnh phải có đúng số byte tương ứng (trong phạm vi representation trên wire được trả về, trước những phép biến đổi ngoài HTTP client nếu có). Khi đọc stream, đừng chỉ dừng ở “không ném exception”:

~~~java
long expected = response.headers()
    .firstValueAsLong("Content-Length")
    .orElse(-1L);

long actual = 0;
try (InputStream in = response.body()) {
    byte[] buf = new byte[8192];
    int n;
    while ((n = in.read(buf)) != -1) {
        actual += n;
        if (actual > MAX_BYTES) {
            throw new IOException("Response exceeds limit");
        }
        process(buf, 0, n);
    }
}
if (expected >= 0 && actual != expected) {
    throw new EOFException("Incomplete response body");
}
~~~

Đây là **đoạn minh họa**: `response` có kiểu `HttpResponse<InputStream>`, `MAX_BYTES` và `process` do ứng dụng xác định, có xử lý `IOException`. Nếu stream ném `IOException` trong khi đọc, đoạn kiểm sau stream có thể không chạy; tầng gọi vẫn phải coi đó là thất bại.

**Phạm vi của Content-Length:** Trong response chunked HTTP/1.1 hoặc HTTP/2, header này có thể không có. Không biến “không có header” thành 0. Nếu dữ liệu phải khớp một file/record cụ thể, dùng kích thước từ metadata đáng tin, hash, checksum hoặc framing ứng dụng để phát hiện thiếu dữ liệu khi không biết tổng byte qua header.

**Chú ý với nén:** `Content-Length` có thể mô tả **số byte của representation đã nén**, trong khi số byte sau khi giải nén lớn hơn nhiều. Nếu áp dụng `GZIPInputStream` hoặc decoder riêng, phải đo và giới hạn **cả compressed bytes và decompressed bytes** theo đúng hợp đồng từng lớp. Không so số byte UTF-8 sau decode với Content-Length của compressed response.

### 6.1. Không tin tuyệt đối vào header do bên ngoài cung cấp

Header có thể thiếu, không hợp lệ hoặc không khớp ngữ nghĩa ứng dụng. Java HTTP client có thể phát hiện lỗi protocol trước khi code kiểm thủ công. Bạn vẫn cần kiểm tra **số byte thật**, checksum/schema và giới hạn tài nguyên. `firstValueAsLong` có thể gặp giá trị không hợp lệ; production cần policy rõ cho header mâu thuẫn, không lấy một giá trị đáng ngờ rồi cấp phát mảng cùng độ dài.

## 7. Người đọc chậm: backpressure nằm ở đâu?

### 7.1. InputStream blocking

Với `ofInputStream()`, người dùng gọi `read` theo nhịp xử lý. Nếu consumer dừng lâu, dữ liệu có thể được đệm trong JDK, kernel và server; về lâu dài các giới hạn buffer/flow-control sẽ ảnh hưởng tốc độ producer, tùy implementation và protocol. Nhưng **không có lời hứa một `Thread.sleep(100)` sẽ lập tức làm server chậm 100 ms**.

Cần test hai loại người đọc chậm:

- **Chậm vì CPU/validation:** consumer nhận chunk rồi tính toán nặng.
- **Chậm vì sink:** ghi xuống disk, DB, object store hoặc gọi API khác có throughput thấp.

Khi có sink chậm, không tự tạo một queue không giới hạn. Giải pháp thường là xử lý đồng bộ trong luồng tiêu thụ hoặc **queue bounded** với chính sách chặn/hủy/backpressure rõ ràng. Thời gian chờ trong bất kỳ queue nào cũng thuộc **end-to-end deadline** mà ứng dụng đặt ra.

### 7.2. Flow.Publisher trong Java 11

~~~java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
    client.send(request, HttpResponse.BodyHandlers.ofPublisher());

Flow.Publisher<List<ByteBuffer>> publisher = response.body();
publisher.subscribe(subscriber);
~~~

Đây là **đoạn minh họa**, `subscriber` là `Flow.Subscriber<List<ByteBuffer>>` do ứng dụng định nghĩa, cần import `java.nio.ByteBuffer`, `java.util.List`, `java.util.concurrent.Flow`, `HttpResponse`. Publisher từ `ofPublisher()` **chỉ được subscribe một lần**; phải consume tới `onComplete/onError` hoặc `cancel` subscription nếu dừng.

Trong `onSubscribe(Flow.Subscription s)`, gọi `s.request(1)` nghĩa là yêu cầu **một phần tử Publisher** (ở đây là `List<ByteBuffer>`), **không phải một byte**. Một list có thể chứa nhiều ByteBuffer; mỗi ByteBuffer có `remaining()` riêng. Không suy từ số lần `onNext` ra số TCP packet, HTTP/2 frame hoặc số byte được gửi.

Một subscriber đơn giản đếm byte theo batch:

~~~java
Flow.Subscriber<List<ByteBuffer>> counter =
    new Flow.Subscriber<List<ByteBuffer>>() {
        private Flow.Subscription subscription;
        private long total;

        @Override
        public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            s.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> buffers) {
            for (ByteBuffer b : buffers) {
                total += b.remaining();
            }
            subscription.request(1);
        }

        @Override
        public void onError(Throwable e) {
            System.err.println("Stream error: " + e.getClass());
        }

        @Override
        public void onComplete() {
            System.out.println("Total bytes: " + total);
        }
    };
~~~

Đây là **đoạn minh họa** (cần import `Flow`, `List`, `ByteBuffer`). Nó đếm `remaining()` nhưng chưa copy/parse data; không phải consumer production có deadline và cancellation đầy đủ. Để kiểm backpressure với consumer thật, chỉ gửi `request(1)` **sau khi xử lý xong** batch trước. Nếu việc xử lý là I/O chậm, dùng executor/queue bounded, không block tùy tiện trong callback đến mức kẹt thread phục vụ HTTP.

### 7.3. Cancel khác dừng server

`Flow.Subscription.cancel()` báo rằng consumer không muốn nhận thêm phần tử. `InputStream.close()` kết thúc việc đọc phía client. Hành vi của underlying network connection phụ thuộc version HTTP và implementation; hủy stream có thể khiến kết nối không được tái sử dụng. **Không hứa `cancel()` hoặc `close()` hoàn tác request đã xử lý ở server**.

## 8. Kiểm thử ngắt giữa chừng mà không bị “pass giả”

### 8.1. Early close chủ động

Trình tự:

1. Bắt đầu GET file lớn với `BodyHandlers.ofInputStream()`.
2. Xác nhận status/headers.
3. Đọc đúng 4096 byte, kiểm byte count.
4. Đóng stream **trước khi ứng dụng tiêu thụ hết body**.
5. Theo dõi server/exchange/kết nối được dọn hoặc bị hủy tùy implementation.

**Assertion hợp lệ:** client chủ động ngừng đọc sau đúng 4096 byte, không leak handle theo bài test.

**Assertion không hợp lệ:** server chắc chắn chỉ gửi đúng 4096 byte lên dây. Hệ thống có thể đã đệm thêm bytes trước khi consumer đóng.

### 8.2. Server chủ động cắt body

Khi server công bố `Content-Length: 32768` rồi đóng TCP sau 1024 byte, response **không hoàn chỉnh**. Có thể xảy ra:

- `InputStream.read` ném `IOException` khi phát hiện thiếu payload.
- Client/API phát hiện framing error ngay tại một bước khác và ném exception.
- Ở một implementation/hệ thống test không kiểm đủ framing, consumer thấy EOF sớm; **byte-count check** vẫn từ chối kết quả.

Vì vậy điều kiện test nên là **“không publish thành công”**, chứ không phải `assertThrows(SpecificIOException.class)` duy nhất. Nếu phía nhận đang ghi file, phải xóa file tạm hoặc rollback, không rename thành tên chính thức chỉ vì đã nhận status 200.

### 8.3. Phân biệt timeout, interruption và EOF

| Hiện tượng | Cơ chế | Cách báo cáo |
| --- | --- | --- |
| User hủy | `InputStream.close()`/subscription cancel do ứng dụng | `CANCELLED`, không báo server corrupt nếu chưa có bằng chứng. |
| Server gửi thiếu bytes | EOF/IOException khi Content-Length chưa đủ | `INCOMPLETE_BODY` và byte count, giữ cause. |
| Đợi quá lâu không có bytes | Read stall/deadline ứng dụng | `STREAM_STALLED` hoặc timeout rõ ràng. |
| DNS/connect/TLS fail trước response | `IOException`/TLS exception từ `send` | `NO_RESPONSE`, không tự gán status. |
| Thread bị interrupt | `InterruptedException` hoặc hủy từ task owner | Giữ interrupted flag khi bắt và cleanup. |
| Tải xong đầy đủ | EOF đúng, size/hash/schema hợp lệ | `COMPLETED`. |

Không dùng một biến boolean `success = response.statusCode()==200` trước khi tiêu thụ stream. Với body streaming, HTTP status 200 mới là **điều kiện cần**, chưa phải điều kiện đủ cho download thành công.

## 9. Thời gian và tính ổn định của slow-reader tests

Bài kiểm thử thường mắc lỗi `Thread.sleep(100)` rồi assert “request phải mất ít nhất 100 ms” hoặc “server phải block”. Các khẳng định này dễ flaky do scheduler, GC, hệ điều hành, socket buffer, HTTP connection reuse và độ tải của CI.

### 9.1. Phân loại test

- **Unit test:** giả lập `InputStream` trả những đoạn rất ngắn, chậm hoặc ném IOException sau N byte. Chủ yếu kiểm logic reader, boundary và cleanup; không cần network.
- **Local integration test:** `HttpServer` tạo response theo block, client Java HTTP đọc; kiểm byte count, status, close, invalid length.
- **Fault injection test:** raw ServerSocket, Toxiproxy hoặc hạ tầng mạng kiểm soát được để cắt socket, reset, tăng latency, giảm bandwidth. Chạy trong environment dành riêng.
- **Load/stress test:** đo concurrency, heap, CPU, GC, FD và latency trong một khoảng tải có budget; không ép chạy nặng ở mọi unit test commit.
- **Soak test:** tải kéo dài để phát hiện file descriptor leak, thread/connection leak hoặc queue phình to theo thời gian.

### 9.2. Khi thật sự muốn quan sát backpressure

Chọn payload lớn hơn đáng kể so với buffer các tầng, áp dụng reader delay và đo **bytes producer đã ghi đến socket theo thời gian**. Nếu producer ghi bị chặn/chậm dần trong điều kiện đã loại trừ nguyên nhân khác, đó là dấu hiệu cần phân tích. Với HTTP/2, quan sát flow-control window/stream-level metrics khi hạ tầng cung cấp; với HTTP/1.1, xem TCP send buffer và throughput.

Đừng đánh giá backpressure chỉ bằng “client cuối cùng vẫn nhận đủ dữ liệu”. Hệ thống có thể âm thầm tích lũy dữ liệu trong RAM để đạt kết quả đúng một lần nhưng sẽ sập khi N client cùng đọc chậm.

## 10. Kiểm thử bằng JUnit Jupiter 5.x, phù hợp Java 11

Những test sau tập trung vào **reader logic** mà không tạo socket, bổ sung cho chương trình HTTP cục bộ ở mục 4. Chúng chứng minh code không giả định mỗi read đầy buffer và có giới hạn byte.

Lưu **`StreamingLoadDemoTest.java`** cùng package với `StreamingLoadDemo.java`. Cần dependency JUnit Jupiter bản tương thích JDK 11 và test runner được cấu hình; JUnit **không có sẵn** trong Java SE.

~~~java
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StreamingLoadDemoTest {
    @Test
    void smallReadsMustNotLoseBytes() throws Exception {
        byte[] data = new byte[10007];
        Arrays.fill(data, (byte) 'Z');

        try (InputStream fragmented = new FilterInputStream(
                new ByteArrayInputStream(data)) {
            @Override
            public int read(byte[] b, int off, int len)
                    throws IOException {
                return super.read(b, off, Math.min(len, 7));
            }
        }) {
            StreamingLoadDemo.Result result =
                StreamingLoadDemo.consume(fragmented, false);

            assertEquals(10007L, result.bytes);
            assertTrue(result.valid);
        }
    }

    @Test
    void oversizedInputIsRejectedWithoutFullBuffering() {
        byte[] data = new byte[4096];

        assertThrows(IOException.class, () -> {
            try (InputStream in = new ByteArrayInputStream(data)) {
                StreamingLoadDemo.readBounded(in, 1024L);
            }
        });
    }

    @Test
    void exactLimitIsAccepted() throws Exception {
        byte[] data = new byte[1024];

        try (InputStream in = new ByteArrayInputStream(data)) {
            assertEquals(1024L,
                StreamingLoadDemo.readBounded(in, 1024L));
        }
    }
}
~~~

**Ý nghĩa:** test đầu đưa các lần `read` tối đa 7 byte vào reader, kiểm đủ 10.007 byte mà không lặp/mất; test thứ hai chứng minh giới hạn 1024 byte thực nhận, test cuối chứng minh đúng bằng giới hạn thì được chấp nhận. Đây không phải benchmark tốc độ mạng; network behavior đã được kiểm chứng riêng qua fixture.

**Lưu ý:** đoạn `readBounded` kiểm giới hạn **sau khi lần đọc trả n byte**. Nó có thể đã nhận thêm vài byte vào buffer trước khi ném exception; giới hạn này ngăn dữ liệu bị **chấp nhận/tích lũy quá mức ở ứng dụng**, không cam kết network chỉ truyền đúng maxBytes byte. Để hạn chế tuyệt đối bytes chuyển qua mạng cần chính sách ở proxy/server và tầng network, không chỉ code sau khi đã đọc.

### 10.1. Test fake InputStream ném lỗi giữa chừng

Có thể tạo `InputStream` mô phỏng dữ liệu đứt sau N bytes; mục tiêu là đảm bảo caller **không publish output thành công** khi đã nhận một phần dữ liệu:

~~~java
InputStream broken = new InputStream() {
    private int emitted;

    @Override
    public int read() throws IOException {
        if (emitted == 1024) {
            throw new IOException("Injected disconnect");
        }
        emitted++;
        return 'Z';
    }
};
~~~

Đây là **đoạn minh họa**, không phải toàn lớp test. Dùng `assertThrows(IOException.class, () -> ...)` để kiểm reader, rồi assert staging/cleanup ở tầng lưu file. Test này phù hợp với unit level nhưng không chứng minh HTTP/1.1 chunked/TLS/proxy thực tế xử lý disconnect theo một exception message cố định.

## 11. Một streaming download an toàn cần trạng thái hoàn tất rõ ràng

Với tệp quan trọng, nên dùng mô hình:

~~~text
REQUESTED
   |
   v
HEADERS_RECEIVED --status/header invalid--> REJECTED
   |
   v
RECEIVING_TO_TEMP
   |             \
   |              \-- I/O / cancel / timeout --> FAILED / CANCELLED
   |
   v
EOF + BYTE_COUNT + HASH + SCHEMA CHECK
   |                              |
   |                              \-- sai --> FAILED, xóa file tạm
   v
VERIFY_OK
   |
   v
PUBLISH_AT_DESTINATION
   |
   v
COMPLETED
~~~

Các trạng thái phải được thiết kế theo hợp đồng dịch vụ, không coi đó là API Java bắt buộc. File đích phải nằm trong thư mục được phép, với quyền tối thiểu, tránh path traversal/symlink race; ghi file tạm rồi kiểm chứng trước khi chuyển/rename. Nếu cần atomicity/độ bền, xem giới hạn filesystem, `ATOMIC_MOVE` và kiểm soát concurrent writer.

**Nếu client ngắt giữa chừng:** xóa hoặc đánh dấu file tạm không hợp lệ, trả trạng thái CANCELLED/FAILED, giữ nguyên file đang sử dụng ở đích. Không trả `COMPLETED` chỉ vì đã tạo được một file có vài KB đầu.

**Với parse dữ liệu streaming:** nếu từng record đã được commit vào database trước khi phát hiện lỗi cuối stream, cần transaction/staging hoặc cơ chế bù trừ. Đừng để “download thất bại” nhưng dữ liệu nghiệp vụ đã được ghi một nửa mà không có chính sách.

## 12. Quản lý timeout, deadline và cancellation

`HttpClient.newBuilder().connectTimeout(...)` đặt thời hạn thiết lập kết nối mới. `HttpRequest.Builder.timeout(...)` đặt timeout cho request theo API. Tuy nhiên, với `ofInputStream()`, **HttpResponse có thể được trả về trước khi body đọc hết**. Đừng suy ra rằng chỉ một request timeout đảm bảo business operation đọc toàn bộ body được bảo vệ khỏi mọi kiểu **stall** sau đó.

Cần thêm **end-to-end deadline** do tầng ứng dụng quản lý cho toàn bộ quá trình: thiết lập kết nối → nhận headers → nhận/giải mã body → ghi xuống sink → verify/publish. Deadline nên được áp dụng bằng task owner, cancellation, socket/network policy hoặc cơ chế supervision phù hợp; không dựa riêng vào `Thread.sleep`/`Future.get` mà thiếu xử lý dừng stream.

Trong code demo, `Thread.sleep(2)` là **cố ý làm chậm test**, không phải retry hay backoff. Khi thực sự bắt `InterruptedException`:

~~~java
try {
    Thread.sleep(delayMillis);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    closeOrCancelActiveStream();
    return;
}
~~~

Đây là **đoạn minh họa**, `delayMillis` và `closeOrCancelActiveStream()` thuộc ứng dụng, không phải API JDK. Khi propagate interruption, bảo toàn tín hiệu và dọn body. Một future bị cancel cũng không chứng minh server chưa xử lý request; không retry POST có side effect khi chưa biết idempotency contract.

### 12.1. Chạy nhiều download đồng thời

Nếu tải N file cùng lúc, giới hạn **concurrency và tài nguyên tổng**, không chỉ maxBytes mỗi file:

- `maxConcurrentDownloads`; số socket/stream/file descriptor; số writer/worker.
- `maxBytesPerDownload` và `maxBytesInFlight`.
- Queue có kích thước cố định; policy từ chối hoặc chờ có deadline.
- Đường dẫn lưu file được kiểm soát, phân quyền, quota disk và cleanup.
- Memory budget gồm JDK/OS buffers, hashing/decompression và queue bên ứng dụng.

Tránh tạo `CompletableFuture` không giới hạn rồi `join` từng cái, vì lượng request đã phát ra có thể vượt budget trước khi bạn chờ. Dùng semaphore/bounded executor và xử lý failure/cancel ở tầng điều phối.

## 13. HTTP/1.1, HTTP/2 và flow control

`BodyHandlers.ofInputStream()` và `ofPublisher()` áp dụng cho HTTP response qua HTTP/1.1 lẫn HTTP/2; `response.version()` cho biết phiên bản thực tế của response đã nhận. Lưu ý:

- HTTP/1.1 truyền theo framing của giao thức đó; có thể dùng `Content-Length` hoặc chunked transfer encoding, không có cam kết mỗi `read` tương ứng một chunk HTTP.
- HTTP/2 dùng stream và frame, có flow-control ở tầng HTTP/2; ranh giới `ByteBuffer`/`List<ByteBuffer>` của Flow API không phải frame ứng dụng.
- Nếu client cancel hoặc đóng sớm, một HTTP/2 stream có thể được hủy theo cơ chế riêng, trong khi kết nối đến cùng origin có thể còn phục vụ stream khác; nhưng hành vi cụ thể của implementation có thể ảnh hưởng connection reuse.
- Một benchmark local `HttpServer` ở bài này chỉ kiểm **HTTP/1.1**; không được dùng nó làm chứng cứ tính đúng đắn của H2 flow control. Khi H2 là yêu cầu sản phẩm, dùng server fixture hỗ trợ TLS/ALPN hoặc H2 rõ ràng và test riêng.
- `Content-Encoding: gzip` là nén representation, không đồng nhất với HTTP/2. Đếm **bytes nén** và **bytes giải nén** ở đúng tầng.

**Quan trọng:** không nhầm `BodyHandlers.buffering(handler, 8192)` với giới hạn toàn bộ body 8192 byte. Đây là công cụ điều chỉnh kích thước nhóm dữ liệu giao cho downstream subscriber, **không giới hạn tổng dung lượng response**. Nếu downstream vẫn là `ofByteArray()`, cả body lớn vẫn có thể được tích lũy.

## 14. Kịch bản stress test vận hành

Khi chuyển từ demo sang performance/integration test, dùng workload có giới hạn, có thể tái lập, tách khỏi unit test nhanh.

| Kịch bản | Cách phát tải | Quan sát | Điều kiện cần quan tâm |
| --- | --- | --- | --- |
| Một file lớn | 100 MiB được phát theo block nhỏ | Heap/RSS, số byte, hash, throughput | Không gom toàn bộ vào RAM, file đúng checksum. |
| N file đồng thời | 10–50 request trong môi trường test có tài nguyên đủ | Peak RSS, FD, GC, pending tasks | Không rò rỉ sau khi dừng; không queue vô hạn. |
| 10% consumer chậm | Delay có kiểm soát trong sink | Queue depth, server write latency | Producer không vượt budget, tiến triển khi có demand. |
| Consumer tắt giữa body | Đóng/cancel sau một ngưỡng byte | File tạm, streams/FD, error categories | Không publish partial file, cleanup. |
| Network cut | Đóng socket khi còn Content-Length | Byte mismatch, cause, retry policy | Không ghi nhận completed. |
| Mạng nhiều lần `read` ngắn | Giảm kích thước chunk/fragment | Parser state, hash, count | Không lặp/mất byte hoặc hỏng UTF-8. |
| File nén tỷ lệ cao | Payload compressed nhỏ, output lớn | Compressed/decompressed size, CPU | Dừng tại hạn mức, không OOM. |
| Chạy liên tục | Lặp download/cancel hàng nghìn lần có giới hạn | FD/thread count, RSS theo thời gian | Không có xu hướng leak. |

**Nguyên tắc thiết kế ngưỡng:** đặt budget theo hạ tầng cụ thể (RAM, CPU, network, disk, số kết nối). Không công bố một con số peak-heap mang tính phổ quát; các GC/JDK, nền tảng và cấu hình khác nhau. Tập trung vào xu hướng, regression và khả năng hoàn tất của workload.

### 14.1. Tái hiện ổn định và tránh flaky CI

- Dùng local loopback/fixture cho correctness; dùng network shaping chỉ trong integration environment có quyền điều khiển.
- Chọn seed cố định cho dữ liệu ngẫu nhiên, hoặc pattern có checksum tính trước.
- Không assert thời gian đến từng millisecond; dùng deadline rộng để ngăn treo và đo latency để phân tích, không làm phép test pass/fail dựa trên scheduler.
- Nếu cần kiểm producer bị block, đo timestamp từ **chính producer** và đảm bảo payload đủ lớn, thay vì đo bằng số lần consumer sleep.
- Dùng fault injection có cờ xác nhận fixture thật sự tạo lỗi; nếu không gửi được response như dự kiến, test phải thất bại vì lỗi fixture, không cho qua.
- Ghi rõ loại protocol, JDK distribution/update, heap settings, số lần retry/timeout, OS và mức tải để so sánh công bằng.
- Khi test lỗi không định danh exception class, vẫn assert **bất biến nghiệp vụ**: incomplete ≠ success; file tạm không thành file chính.

## 15. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ assert HTTP status 200 | Body vẫn có thể bị cắt/truncate. | Đọc tới EOF, so byte count/hash/schema. |
| Dùng `ofByteArray()` để “test streaming 10 GB” | Gom toàn bộ body vào RAM. | `ofInputStream`, `ofPublisher` hoặc `ofFile` với limits. |
| Dùng `buffer.length` thay vì `n` | Trộn byte cũ/byte rác vào kết quả. | Chỉ xử lý `[0,n)`. |
| Test chờ đủ 8192 byte ở mỗi `read` | Thất bại giả trên mạng phân mảnh. | Chấp nhận short reads, vòng lặp tới EOF. |
| Chỉ tin Content-Length header | Thiếu/chỉ đúng ở một tầng encoding, có thể không đáng tin. | Đếm bytes thực, hash/manifest, giới hạn tài nguyên. |
| Gọi `response.body()` là xong | Stream có thể chưa được tiêu thụ. | Đọc và đóng/cancel đúng vòng đời. |
| Quên đóng stream khi user cancel | Rò rỉ tài nguyên và kết nối. | `try-with-resources`/close trong mọi nhánh. |
| Gọi `Thread.sleep` rồi khẳng định server đã backpressure | OS/JDK có buffer, không chứng minh được. | Đo producer latency, queue và memory dưới tải đủ lớn. |
| Hủy consumer nhưng báo network error | Hành vi chủ động bị gộp vào thất bại server. | Phân loại CANCELLED riêng. |
| Server gửi thiếu, client vẫn rename file tạm | Publish file corrupt. | Verify hoàn chỉnh rồi mới publish. |
| Retry POST sau timeout không có idempotency | Có thể tạo side effect trùng. | Retry policy/idempotency key theo hợp đồng. |
| Dùng `ofByteArrayConsumer` làm test backpressure | Subscriber này không flow-controlled. | `ofPublisher` và quản lý `Flow.Subscription`. |
| Đọc `ByteBuffer.capacity()` làm byte count | Có thể đọc ngoài cửa sổ dữ liệu hợp lệ. | Dùng `remaining()`. |
| Subscribe nhiều lần vào publisher của `ofPublisher()` | Subscriber sau bị lỗi theo contract. | Subscribe đúng một lần; tạo request mới nếu cần. |
| Tin `cancel` bảo đảm server lập tức dừng gửi | Buffering/transport timing khác nhau. | Assert cleanup/semantics, không assert lượng network tuyệt đối. |
| So sánh compressed Content-Length với decoded bytes | Kết luận nhầm mất dữ liệu. | Đo đúng tầng compressed/decompressed. |
| Chỉ test một file mà tuyên bố memory bounded khi N kết nối | Tổng bộ đệm và queue có thể vượt budget. | Load test có concurrency limit, giám sát heap/RSS/FD. |
| Lấy raw response body để log lỗi | Rò rỉ dữ liệu nhạy cảm, log bùng nổ. | Log status, bytes, timings và error category an toàn. |

## 16. Checklist xác nhận một pipeline streaming hoạt động đúng

1. **Đúng API:** `ofInputStream`/`ofPublisher`/`ofFile` phù hợp với loại body, thay vì gom vào `String`/`byte[]` vô hạn.
2. **Trạng thái hoàn tất:** HTTP headers/status khác với body đã nhận hết; phân biệt streaming-in-progress, completed, failed và cancelled.
3. **Giới hạn:** bytes, thời gian, số request đồng thời, bộ nhớ, disk và dữ liệu sau giải nén đều có budget.
4. **Byte chính xác:** mỗi lần chỉ xử lý `n` byte thực nhận; có checksum/framing cho dữ liệu quan trọng.
5. **Reader chậm:** downstream có bounded queue/demand; không có cơ chế tự động tích lũy vô hạn.
6. **Hủy sớm:** caller đóng/cancel đúng cách, không publish dữ liệu partial; ghi nhận cancellation riêng.
7. **Ngắt từ server:** incomplete content length/EOF/IO đều làm fail, không báo download hoàn chỉnh.
8. **Test fixture:** lỗi test được tiêm thực sự; không dựa vào website công cộng hoặc timing scheduler.
9. **Cleanup:** InputStream, Flow.Subscription, file tạm, thread và server fixture đều được quản lý.
10. **Tương thích:** source và dependencies dùng được trên Java 11; không dùng API legacy hoặc API xuất hiện sau Java 11.
11. **Observability:** bytes-in, bytes-out, latency, checksum result, cancel/error, memory/FD có thể quan sát mà không log raw nội dung nhạy cảm.
12. **Tách hợp đồng:** với POST/PUT upload, replay/timeout còn liên quan idempotency và xác nhận server-side commit, không chỉ streaming response.

## 17. Bài tập thực hành

**Bài 1 — thay kích thước:** Đổi `LARGE` từ 2 MiB lên 8 MiB, giữ buffer client 2048 byte. Giải thích vì sao số byte cuối đổi nhưng API streaming không bắt buộc ứng dụng tạo mảng 8 MiB.

**Bài 2 — short reads:** Dùng test `FilterInputStream` chỉ trả tối đa 7 byte. Thử sai bằng cách cộng `buf.length` thay vì `n`; quan sát test hash/count phát hiện lỗi.

**Bài 3 — người đọc chậm:** Tăng delay từ 2 ms lên 10 ms. Đo wall-clock, server write duration, heap và số byte. Vì sao tăng delay không chắc kéo dài server write duration tương ứng khi response nhỏ hơn socket buffers?

**Bài 4 — early close:** Đổi ngưỡng đọc trước khi đóng từ 4096 thành 8192 byte. Assert đúng số byte ứng dụng đã đọc. Không assert server thực gửi đúng 8192 byte; giải thích buffer/network race.

**Bài 5 — truncated body:** Raw fixture khai 32768 byte nhưng gửi 1024. Thay 1024 thành 4096, xác nhận vẫn detect incomplete; sau đó sửa fixture gửi đủ 32768 để test mới xác nhận success. Không bỏ qua cờ `sent` dùng phát hiện lỗi fixture.

**Bài 6 — Content-Length vắng mặt:** Tạo endpoint truyền chunked HTTP/1.1; kiểm rằng absence của header không tự khiến reader thất bại. Đề xuất checksum/trailer/schema để phát hiện response thiếu về mặt nghiệp vụ.

**Bài 7 — bộ nhớ và concurrency:** Chạy 10 download 8 MiB với queue bounded. Theo dõi peak heap/RSS và FD; so với cách `ofByteArray()` gom toàn bộ. Nêu vì sao bộ đệm nội bộ vẫn tồn tại dù code của bạn chỉ tạo buffer 2048 byte.

**Bài 8 — File download:** Chuyển từ `ofInputStream` sang ghi file tạm với `ofFile`/streaming. Chỉ rename khi hash và byte count đúng; test server disconnect không tạo file “complete”.

**Bài 9 — Flow:** Dùng `ofPublisher()` với subscriber chỉ `request(1)` sau khi xử lý xong batch. Cố tình chậm consumer, đo queue; giải thích tại sao một yêu cầu `request(1)` không có nghĩa chỉ nhận một byte.

**Bài 10 — gzip bomb:** Tạo fixture test có compressed size nhỏ, uncompressed size cao trong môi trường giới hạn; đặt budget cho cả hai, abort khi vượt và kiểm cleanup.

**Bài 11 — status 200 nhưng data sai:** Server gửi đủ 4096 byte nhưng một byte bị đổi từ `Z` sang `Y`. Tại sao byte count vẫn đúng mà content validation/hash phải fail?

**Bài 12 — kiểm thử interruption:** Trong lúc tải, yêu cầu task owner cancel. Bảo đảm dọn InputStream/Flow subscription và báo `CANCELLED`, không tự động retry POST hay khẳng định server chưa thực hiện side effect.

## 18. Nguồn chuẩn và ghi nhớ

- [Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofInputStream`, `ofPublisher`, `ofFile`, `ofLines`, `discarding` và khác biệt thời điểm response sẵn sàng.
- [Java SE 11 — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): hợp đồng đóng stream, subscribe một lần, cancel và `ofByteArrayConsumer` không flow-controlled.
- [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): vòng đời send/sendAsync, cấu hình client và response.
- [Java SE 11 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request timeout và options.
- [Java SE 11 — HttpExchange](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): server test, Content-Length cố định, đóng stream trước khi ghi đủ sẽ kết thúc exchange lỗi.
- [Java SE 11 — Flow](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.html): publisher/subscriber, subscription request/cancel.

**Ghi nhớ:** Khi **body streaming**, kết quả HTTP 200 chưa đồng nghĩa tải hoàn tất. Hãy kiểm số byte và tính toàn vẹn tới EOF, dùng bộ đệm có giới hạn, kiểm reader chậm dưới tải thực tế, đóng/cancel đúng lúc và **phân biệt early-close chủ động với network truncation**. Những nguyên tắc này giúp các ứng dụng Java 11 xử lý response lớn an toàn và còn phù hợp cho hệ thống Java hiện nay.