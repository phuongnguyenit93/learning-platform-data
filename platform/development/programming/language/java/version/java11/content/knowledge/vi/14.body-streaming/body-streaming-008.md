# Đọc hết, hủy hoặc đóng body để trả tài nguyên — Body streaming trong Java 11+

## 1. Vấn đề: đã nhận HttpResponse không có nghĩa đã đọc xong body

Java 11 cung cấp `java.net.http.HttpClient` và các `HttpResponse.BodyHandlers` để xử lý response body. Với handler gom toàn bộ dữ liệu như `ofString()` hoặc `ofByteArray()`, khi `client.send(...)` trả về thì body đã được đọc và chuyển thành đối tượng kết quả.

Nhưng với các handler **streaming** như `ofInputStream()`, `ofLines()` và `ofPublisher()`, `client.send(...)` có thể trả `HttpResponse<T>` **sau khi đã nhận xong response headers, trong khi byte body vẫn đang được nhận qua mạng**. Khi đó, việc giữ một body mà không đọc tiếp, không đóng và không hủy có thể giữ tài nguyên gắn với HTTP exchange, ảnh hưởng connection pool và khiến request không hoàn tất.

Nguyên tắc cốt lõi:

> **Khi đã nhận streaming response body, ứng dụng phải chủ động đưa nó về một trạng thái kết thúc:** hoặc **đọc hết** đến EOF/`onComplete`, hoặc **đóng/hủy** nếu không muốn đọc tiếp.

Đây là kiến thức **vẫn áp dụng hiện nay** trên Java 11 và các bản JDK mới. Nó không chỉ dành cho response thành công `2xx`: response `4xx`/`5xx` cũng có body, có thể cần đóng hoặc tiêu thụ tương tự.

Bài tập trung vào tài nguyên **response body đang được stream**, không nhầm với `HttpRequest.BodyPublisher` vốn cung cấp dữ liệu chiều **gửi lên server**.

## 2. Chọn BodyHandler và nghĩa vụ kết thúc tương ứng

`HttpResponse.BodyHandlers` cung cấp nhiều chiến lược xử lý dữ liệu:

| BodyHandler | Kiểu của `response.body()` | Khi nào response được xem là đã xử lý body? | Việc cần làm của caller |
| --- | --- | --- | --- |
| `ofString()` | `String` | Body đã được gom và giải mã trước khi trả response | Không cần tự đóng `String` |
| `ofByteArray()` | `byte[]` | Đã gom toàn bộ byte | Không cần đóng mảng; lưu ý bộ nhớ |
| `ofFile(path)` | `Path` | Đã ghi xong body ra file trước khi trả response | Quản lý file kết quả và lỗi file theo nghiệp vụ |
| `discarding()` | `Void` (thường `null`) | Đã nhận rồi bỏ dữ liệu body | Phù hợp khi không cần nội dung |
| `ofInputStream()` | `InputStream` | **Có thể chưa nhận xong body** | Đọc đến EOF hoặc gọi `close()` |
| `ofLines()` | `Stream<String>` | **Có thể chưa nhận xong body** | Đọc hết các dòng hoặc gọi `close()` |
| `ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | **Có thể chưa nhận xong body** | **Subscribe một lần**, yêu cầu dữ liệu đến completion/error hoặc gọi `Subscription.cancel()` |

**Đừng suy luận** rằng `response.statusCode() == 200`, hoặc đối tượng `HttpResponse` đã tồn tại, có nghĩa byte body đã được tiêu thụ. Với các streaming handler, chính **đối tượng body** là nơi caller phải hoàn thành vòng đời.

Một ví dụ chọn đúng handler:

- API trả một JSON nhỏ: `ofString()` tiện để đọc toàn bộ.
- Tải file lớn: `ofFile(path)` hoặc `ofInputStream()` với vòng lặp copy có giới hạn.
- Đọc dữ liệu theo dòng: `ofLines()`; đóng stream cả khi chỉ đọc một số dòng.
- Pipeline bất đồng bộ với backpressure: `ofPublisher()`; bảo đảm request đến terminal signal hoặc cancel.
- Không cần nội dung: `discarding()` thay vì mở stream rồi bỏ đó.

## 3. ofInputStream(): đọc đến EOF hoặc đóng stream

### 3.1. Đọc hết với try-with-resources

`BodyHandlers.ofInputStream()` trả về `HttpResponse<InputStream>`. Trong Java 11, response có thể được trả ngay khi đọc xong headers; `InputStream` mới là nơi byte tiếp tục đến.

Với body nhỏ đã tin cậy:

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream in = response.body()) {
    byte[] data = in.readAllBytes(); // Chỉ phù hợp khi kích thước có giới hạn.
    System.out.println("Received bytes: " + data.length);
}
```

Đây là **mảnh mã** cần biến `client` và `request`, cùng import và xử lý `IOException`/`InterruptedException`. `readAllBytes()` có trong Java 11. Đọc đến `-1`/EOF nghĩa là nội dung đã được nhận hết; `try`-with-resources vẫn đảm bảo gọi `close()` nếu đọc thất bại.

**Lưu ý bộ nhớ:** với body lớn hoặc không đáng tin cậy, không dùng `readAllBytes()` vô điều kiện vì có thể dùng hết RAM. Nên đọc theo chunk, giới hạn tổng byte, và đóng trong `finally`/try-with-resources.

### 3.2. Streaming theo chunk, kiểm soát kích thước

Mảnh code sau minh họa đọc dữ liệu có giới hạn, không gom toàn bộ vào mảng lớn:

```java
long maxBytes = 10L * 1024 * 1024; // Ví dụ giới hạn 10 MiB.
long received = 0;

HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream in = response.body()) {
    byte[] buf = new byte[8192];
    int n;
    while ((n = in.read(buf)) != -1) {
        if (n > maxBytes - received) {
            throw new IOException("Response body exceeds size limit");
        }
        received += n;
        // Xử lý đúng buf[0..n); ví dụ ghi ra OutputStream.
    }
}
```

Nếu vượt giới hạn, ném ngoại lệ bên trong `try` vẫn kích hoạt `close()` để trả tài nguyên. Kiểm tra `n > maxBytes - received` tránh cộng vượt giới hạn; ứng dụng thật cần kiểm soát thêm timeout, tốc độ nhận và nơi ghi kết quả.

### 3.3. Chỉ cần một phần? Đóng sớm, không để body treo

Ví dụ chỉ muốn đọc 5 byte đầu:

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream in = response.body()) {
    byte[] prefix = in.readNBytes(5);
    System.out.println(new String(prefix, StandardCharsets.UTF_8));
} // Đóng ngay cả khi chưa đọc hết body.
```

`InputStream.readNBytes(int)` có từ Java 9; dùng được trên Java 11. Nếu không muốn đọc tiếp, **`close()` là cách kết thúc đúng**.

**Hệ quả:** đóng `InputStream` trước khi đến EOF **có thể làm kết nối HTTP bên dưới bị đóng và không tái sử dụng được**. Đây là trade-off: giải phóng exchange sớm, nhưng có thể mất lợi thế keep-alive. Đừng hứa rằng đóng sớm **luôn** chỉ đóng một HTTP/2 stream hay **luôn** đóng cả TCP connection; hành vi tùy giao thức và triển khai.

**Không cố đọc hết một response khổng lồ từ nguồn không đáng tin cậy chỉ để giữ kết nối.** Khi nội dung không cần thiết hoặc vượt giới hạn tài nguyên, đóng sớm là phương án có chủ đích.

## 4. ofLines(): Stream<String> cũng phải đóng

`BodyHandlers.ofLines()` trả `HttpResponse<Stream<String>>` và giải mã văn bản theo charset của response. `Stream<String>` này **gắn với I/O**, khác stream thuần bộ nhớ như `List.stream()`.

Đọc hết toàn bộ dòng:

```java
HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    lines.forEach(System.out::println);
}
```

Nếu chỉ cần dòng đầu tiên:

```java
HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    String first = lines.findFirst().orElse("<empty>");
    System.out.println(first);
} // findFirst() dừng sớm; close() dọn tài nguyên.
```

Các đoạn trên là **mảnh mã minh họa** trong phương thức xử lý `IOException`/`InterruptedException`. Với stream I/O, **terminal operation không tự bảo đảm đóng tài nguyên khi chỉ đọc một phần**. `findFirst()`, `limit(n)`, `anyMatch(...)` có thể dừng khi chưa tiêu thụ hết response. Vì vậy **dùng try-with-resources** dù bạn định xử lý hết các dòng.

Khi đọc hết đến cuối stream, exchange có thể hoàn thành bình thường; `close()` vẫn là lớp bảo vệ cho lỗi hoặc dừng sớm. Nếu đóng stream trước khi tiêu thụ hết, kết nối có thể không được tái sử dụng cho request sau.

**Không nên biến stream ra ngoài phạm vi try rồi đóng ở nơi khác mà không có ownership rõ ràng.** Nếu method trả `Stream<String>` cho caller, API của bạn phải nêu rõ caller chịu trách nhiệm `close()`.

## 5. ofPublisher(): subscribe một lần, tiêu thụ đến terminal hoặc cancel

`BodyHandlers.ofPublisher()` trả về:

```java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response;
```

Khi response headers có sẵn, body vẫn có thể đang truyền. `response.body()` là một `Flow.Publisher` phát các nhóm `List<ByteBuffer>`.

**Khác với publisher request body:**

- Publisher từ `BodyHandlers.ofPublisher()` **chỉ được subscribe đúng một lần**.
- Một subscriber mới sau lần đầu sẽ nhận `onError(IllegalStateException)` theo hợp đồng.
- Nếu **không subscribe**, luồng body có thể không được tiêu thụ; request và tài nguyên tương ứng có thể bị giữ lại.
- Sau khi subscribe, caller phải **request dữ liệu** cho tới `onComplete()` hoặc `onError(Throwable)`, **hoặc** gọi `Flow.Subscription.cancel()` khi không muốn nhận tiếp.

### 5.1. Tiêu thụ toàn bộ dữ liệu

Mẫu ý tưởng:

```java
response.body().subscribe(new Flow.Subscriber<List<ByteBuffer>>() {
    private Flow.Subscription subscription;

    @Override public void onSubscribe(Flow.Subscription s) {
        subscription = s;
        s.request(1);
    }

    @Override public void onNext(List<ByteBuffer> buffers) {
        for (ByteBuffer part : buffers) {
            // Xử lý part trong phạm vi callback.
        }
        subscription.request(1);
    }

    @Override public void onError(Throwable error) {
        // Kết thúc có lỗi, báo trạng thái cho caller.
    }

    @Override public void onComplete() {
        // Toàn bộ body đã được tiêu thụ.
    }
});
```

Đây là **mảnh code**; cần bộ đồng bộ hóa để caller biết khi nào callback hoàn thành và xử lý lỗi. Chương trình độc lập ở mục 7 dùng `CountDownLatch` và `AtomicReference<Throwable>` cho mục đích này.

**Backpressure:** `request(1)` yêu cầu một **nhóm** `List<ByteBuffer>`, không phải một byte. Không dùng `onNext` để lưu tham chiếu buffer rồi sửa nó sau khi callback kết thúc; hãy xử lý/copy nội dung theo hợp đồng.

### 5.2. Không cần đọc hết: cancel subscription

```java
@Override public void onNext(List<ByteBuffer> chunk) {
    // Đã có đủ dữ liệu để quyết định không nhận tiếp.
    subscription.cancel();
}
```

Đây là **mảnh code đặt trong implementation của Subscriber** đã giữ `subscription` từ `onSubscribe`. Sau `cancel()`, **đừng chờ chắc chắn sẽ có `onComplete()` hoặc `onError()`**: cancel là con đường kết thúc chủ động riêng của subscriber.

Không có một phương thức `close()` trực tiếp trên `Flow.Publisher` trả về từ `ofPublisher()`. Muốn giải phóng exchange, phải **subscribe đúng một lần rồi consume hoặc cancel**, không bỏ mặc publisher sau `response.body()`.

Hủy trước khi nhận hết có thể làm HTTP connection bị đóng hoặc giảm khả năng reuse; khi dùng HTTP/2, cancellation thường có thể tác động ở mức stream, nhưng không nên dựa vào cơ chế transport cụ thể như một bảo đảm cho mọi phiên bản JDK.

### 5.3. Custom BodySubscriber cũng phải kết thúc

Nếu tự triển khai `HttpResponse.BodySubscriber<T>` hay dùng `BodySubscribers.fromSubscriber(...)`, phải tuân thủ:

- Trong `onSubscribe`, ghi nhận `Flow.Subscription`.
- Gọi `request(n)` để nhận đủ dữ liệu cho tới khi có `onComplete`/`onError`, **hoặc gọi `cancel()`**.
- Nếu xử lý gặp lỗi, dừng/`cancel` và báo lỗi hợp lý; không giữ một subscription mở mà không tiếp tục request.
- Không giữ `List<ByteBuffer>` hay `ByteBuffer` được bàn giao rồi truy cập/sửa bất đồng bộ trái hợp đồng.
- Với callback chậm hoặc blocking, cân nhắc lập kế hoạch xử lý phù hợp để không chặn tiến trình nhận body.

## 6. ofString, ofByteArray, ofFile, discarding: khi không cần tự đóng body streaming

### Đã gom đầy đủ: ofString và ofByteArray

```java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
String body = response.body();
```

`ofString()` và `ofByteArray()` nhận đủ body trước khi `send` trả `HttpResponse`. Không có `InputStream`/`Stream` trả cho caller để đóng, nhưng chúng có thể tiêu thụ nhiều bộ nhớ: không dùng bừa cho download rất lớn.

### Ghi file: ofFile

```java
Path file = Path.of("downloads", "artifact.bin");
HttpResponse<Path> response = client.send(
        request, HttpResponse.BodyHandlers.ofFile(file));
```

Ở đây `response.body()` là đường dẫn file đã được ghi xong khi response được trả về. Caller quản lý file theo yêu cầu sản phẩm (kiểm tra `statusCode`, kích thước, xác minh nội dung, dọn file lỗi/không cần). Không có `InputStream` response streaming do `ofFile` trả để tự đóng.

Với dữ liệu lớn, `ofFile` thường hợp lý hơn `ofByteArray`; tuy vậy vẫn cần bảo vệ đường dẫn đích và giới hạn tải theo yêu cầu hệ thống.

### Không cần nội dung: discarding

```java
HttpResponse<Void> response = client.send(
        request, HttpResponse.BodyHandlers.discarding());

System.out.println(response.statusCode());
```

`discarding()` **tiêu thụ và bỏ body**. Đây là cách rõ ràng khi không cần lấy dữ liệu, tốt hơn việc dùng `ofInputStream` rồi không bao giờ đọc/đóng. Không nên suy luận rằng `HEAD` hoặc status `204` là lúc nào cũng có body cần đọc; chọn handler dựa trên loại exchange và yêu cầu cụ thể.

## 7. Chương trình kiểm chứng Java 11: EOF, close, cancel, discarding

Ví dụ hoàn chỉnh sau chạy với **Java 11 trở lên**, không cần server Internet hay thư viện ngoài JDK. Nó tự mở HTTP server **loopback** bằng mô-đun `jdk.httpserver`, gửi response văn bản 3 dòng và response lớn phục vụ ca hủy.

**Các ca kiểm thử:** đọc hết InputStream, đóng InputStream sớm, đọc hết các dòng, đóng Stream khi chỉ đọc dòng đầu, nhận đủ Flow publisher, hủy Flow publisher sau batch đầu, và discard body.

Tạo tệp **`StreamingBodyCleanupDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamingBodyCleanupDemo {
    private static final byte[] TEXT = "alpha\nbeta\ngamma\n"
            .getBytes(StandardCharsets.UTF_8);

    private static void serve(HttpExchange exchange) throws IOException {
        byte[] content;
        if (exchange.getRequestURI().getPath().equals("/large")) {
            content = new byte[65536];
            java.util.Arrays.fill(content, (byte)'x');
        } else {
            content = TEXT;
        }
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(200, content.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(content);
        } catch (IOException expectedIfClientCancelled) {
            // Ca hủy/đóng sớm có thể ngắt phần ghi phía server.
        } finally {
            exchange.close();
        }
    }

    private static HttpRequest req(int port, String path) {
        return HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
    }

    private static String gather(
            Flow.Publisher<List<ByteBuffer>> publisher) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        publisher.subscribe(new Flow.Subscriber<List<ByteBuffer>>() {
            private Flow.Subscription subscription;

            @Override public void onSubscribe(Flow.Subscription s) {
                subscription = s;
                s.request(1);
            }

            @Override public void onNext(List<ByteBuffer> parts) {
                for (ByteBuffer part : parts) {
                    byte[] chunk = new byte[part.remaining()];
                    part.get(chunk);
                    out.write(chunk, 0, chunk.length);
                }
                subscription.request(1);
            }

            @Override public void onError(Throwable error) {
                failure.set(error);
                done.countDown();
            }

            @Override public void onComplete() {
                done.countDown();
            }
        });

        if (!done.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("publisher did not terminate");
        }
        if (failure.get() != null) {
            throw new AssertionError("publisher failed", failure.get());
        }
        return new String(out.toByteArray(), StandardCharsets.UTF_8);
    }

    private static boolean cancelOnFirstBatch(
            Flow.Publisher<List<ByteBuffer>> publisher) throws Exception {
        CountDownLatch done = new CountDownLatch(1);
        AtomicBoolean cancelled = new AtomicBoolean();

        publisher.subscribe(new Flow.Subscriber<List<ByteBuffer>>() {
            private Flow.Subscription subscription;

            @Override public void onSubscribe(Flow.Subscription s) {
                subscription = s;
                s.request(1);
            }

            @Override public void onNext(List<ByteBuffer> bytes) {
                cancelled.set(true);
                subscription.cancel();
                done.countDown();
            }

            @Override public void onError(Throwable error) {
                done.countDown();
            }

            @Override public void onComplete() {
                done.countDown();
            }
        });

        if (!done.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("cancel was not observed");
        }
        return cancelled.get();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", StreamingBodyCleanupDemo::serve);
        server.start();

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        try {
            int port = server.getAddress().getPort();

            HttpResponse<InputStream> streamResponse = client.send(
                    req(port, "/text"),
                    HttpResponse.BodyHandlers.ofInputStream());
            String body;
            try (InputStream input = streamResponse.body()) {
                body = new String(
                        input.readAllBytes(), StandardCharsets.UTF_8);
            }
            System.out.println("input EOF: " + body.replace("\n", "|"));

            HttpResponse<InputStream> early = client.send(
                    req(port, "/text"),
                    HttpResponse.BodyHandlers.ofInputStream());
            byte[] prefix;
            try (InputStream input = early.body()) {
                prefix = input.readNBytes(5);
            }
            System.out.println("input early close: "
                    + new String(prefix, StandardCharsets.UTF_8));

            HttpResponse<Stream<String>> lineResponse = client.send(
                    req(port, "/text"),
                    HttpResponse.BodyHandlers.ofLines());
            List<String> lines;
            try (Stream<String> stream = lineResponse.body()) {
                lines = stream.collect(Collectors.toList());
            }
            System.out.println("lines EOF: " + lines);

            HttpResponse<Stream<String>> shortLines = client.send(
                    req(port, "/text"),
                    HttpResponse.BodyHandlers.ofLines());
            String first;
            try (Stream<String> stream = shortLines.body()) {
                first = stream.findFirst().orElse("<none>");
            }
            System.out.println("lines early close: " + first);

            HttpResponse<Flow.Publisher<List<ByteBuffer>>> pubResponse =
                    client.send(req(port, "/text"),
                            HttpResponse.BodyHandlers.ofPublisher());
            String fromPublisher = gather(pubResponse.body());
            System.out.println("publisher complete: "
                    + fromPublisher.replace("\n", "|"));

            HttpResponse<Flow.Publisher<List<ByteBuffer>>> cancelled =
                    client.send(req(port, "/large"),
                            HttpResponse.BodyHandlers.ofPublisher());
            System.out.println("publisher cancelled: "
                    + cancelOnFirstBatch(cancelled.body()));

            HttpResponse<Void> discarded = client.send(
                    req(port, "/text"),
                    HttpResponse.BodyHandlers.discarding());
            System.out.println("discarded: "
                    + (discarded.statusCode() == 200
                        && discarded.body() == null));

            System.out.println("ALL CHECKS PASSED");
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa file; `--release 11` kiểm tra API và cú pháp Java 11 ngay cả khi máy có JDK mới:

```bash
javac --release 11 --add-modules jdk.httpserver StreamingBodyCleanupDemo.java
java --add-modules jdk.httpserver StreamingBodyCleanupDemo
```

**Đầu ra đã biên dịch/chạy kiểm chứng:**

```text
input EOF: alpha|beta|gamma|
input early close: alpha
lines EOF: [alpha, beta, gamma]
lines early close: alpha
publisher complete: alpha|beta|gamma|
publisher cancelled: true
discarded: true
ALL CHECKS PASSED
```

Giải thích:

1. **`input EOF`:** `readAllBytes()` nhận đủ 3 dòng; dấu `|` chỉ thay ký tự `\n` để hiển thị dễ quan sát. `try` đóng stream sau khi đọc.
2. **`input early close`:** `readNBytes(5)` chỉ lấy `alpha`; thoát `try` tự đóng stream dù body chưa được đọc hết.
3. **`lines EOF`:** `collect` tiêu thụ các dòng `alpha`, `beta`, `gamma`; sau đó stream vẫn được đóng trong `try`.
4. **`lines early close`:** `findFirst()` chỉ cần một dòng; đóng stream là bắt buộc khi không đọc tiếp.
5. **`publisher complete`:** subscriber `request(1)` từng nhóm, đọc ByteBuffer, chờ `onComplete` và xác nhận không có `onError`.
6. **`publisher cancelled`:** callback hủy `Flow.Subscription` sau batch đầu; hàm trả true vì đã gọi `cancel()`. Ca này **không** đo lường việc TCP connection có bị đóng hay không.
7. **`discarded`:** handler tự nhận rồi bỏ body, trả kiểu `Void`; khi nhận xong, không còn streaming body do caller nắm giữ.

Mã này giới hạn các thử nghiệm trong localhost. `jdk.httpserver` là mô-đun JDK tiêu chuẩn nhưng môi trường hạn chế loopback có thể từ chối bind port. `gather` gom kết quả vào RAM **chỉ vì dữ liệu kiểm thử nhỏ**; với response lớn cần xử lý từng batch thay vì tích lũy hết.

## 8. sendAsync, cancellation và thời điểm thật sự hoàn thành exchange

`HttpClient.sendAsync(request, handler)` trả `CompletableFuture<HttpResponse<T>>`. Với handler streaming, future có thể hoàn thành khi **đã có response headers và đối tượng streaming body**, trong khi body vẫn đang được nhận.

```java
CompletableFuture<HttpResponse<InputStream>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

HttpResponse<InputStream> response = future.join();

try (InputStream input = response.body()) {
    // Đọc hết hoặc đóng sớm khi không cần thêm dữ liệu.
}
```

Đây là **mảnh mã** với `client`, `request` đã khai báo. Việc `future.join()` trả về **không bảo đảm** stream đã đến EOF. Sau khi nhận body, bạn vẫn có trách nhiệm quản lý vòng đời của nó.

**`future.cancel(true)` khác việc đóng body đang có:** khi future chưa hoàn thành, Java HTTP Client mặc định có thể cố hủy exchange, nhưng thời điểm hủy có hiệu lực không được cam kết tuyệt đối. Khi future đã trả về response chứa `InputStream`/`Stream`/publisher, đừng chỉ gọi cancel lên future rồi bỏ body; hãy **đóng hoặc hủy chính streaming body** theo API của nó.

Nếu thread bị ngắt khi `send()` đang chờ, `InterruptedException` là tín hiệu hủy/lỗi phải xử lý. Không bắt rồi nuốt tín hiệu interrupt và cũng không coi server chắc chắn chưa nhận request, vì một exchange có thể đã bắt đầu.

## 9. Đóng response body khác với đóng HttpClient

Đây là một điểm **khác nhau theo phiên bản Java**, dễ gây code không biên dịch nếu nhầm API mới với Java 11:

- Trên **Java 11**, `HttpClient` **chưa triển khai `AutoCloseable`** và chưa có API lifecycle `close()`/`shutdown()` như các JDK mới. Vì vậy **không** viết `try (HttpClient client = HttpClient.newHttpClient())` trong ví dụ yêu cầu `javac --release 11`.
- Từ **Java 21**, `HttpClient` triển khai `AutoCloseable` với `close()`, `shutdown()`, `shutdownNow()`, `awaitTermination(...)` và `isTerminated()`. Khi dùng JDK 21+, có thể chủ động quản lý vòng đời cả client.
- **Dù trên Java 21+ có thể đóng HttpClient**, việc để streaming body không đọc/không close/không cancel có thể làm request chưa hoàn tất và **làm chậm hoặc kẹt shutdown có trật tự**. Dọn body **trước** khi yêu cầu đóng client.

Mẫu **chỉ dành cho JDK 21+**, **không biên dịch với `--release 11`**:

```java
try (HttpClient client = HttpClient.newHttpClient()) {
    HttpResponse<InputStream> response = client.send(
            request, HttpResponse.BodyHandlers.ofInputStream());

    try (InputStream input = response.body()) {
        // Đọc hết hoặc chủ động dừng sớm.
    }
}
```

Mảnh trên còn cần xử lý ngoại lệ và khai báo `request`. Trong Java 11, cách đúng là **tái sử dụng một `HttpClient`** ở phạm vi ứng dụng thích hợp, và **đóng/tận dụng hết các response body streaming** sau mỗi request. Không tạo mới client cho mỗi lời gọi chỉ để tránh quản lý response body, vì có thể mất lợi ích connection pooling.

**Đóng `HttpResponse` không phải một thao tác chuẩn:** `HttpResponse` không phải tài nguyên AutoCloseable. Đối tượng cần đóng là `InputStream`, `Stream<String>` hoặc subscription tùy handler đã dùng.

## 10. Tài nguyên, connection reuse và giới hạn dữ liệu không đáng tin cậy

### Đọc hết có thể giúp tái sử dụng kết nối, nhưng không phải lời hứa tuyệt đối

Khi đã nhận đủ byte response, client có cơ hội hoàn tất trao đổi và tái sử dụng kết nối keep-alive nếu giao thức và trạng thái kết nối cho phép. Tuy nhiên, không nên assert rằng cùng một socket chắc chắn được tái sử dụng chỉ vì đã đọc EOF.

### Đóng/hủy sớm có thể hy sinh connection reuse

Đóng `InputStream`, `Stream` hoặc hủy `Flow.Subscription` trước khi EOF/`onComplete` có thể làm client đóng kết nối bên dưới. Đây là hành vi được Javadoc cảnh báo, không phải “lỗi” của `close` hay `cancel`.

Khi response quá lớn, không tin cậy hoặc không còn ý nghĩa, **giải phóng tài nguyên sớm quan trọng hơn cố duy trì connection reuse**. Không tự drain hàng gigabyte chỉ để tiết kiệm một lần handshake.

### Quy định chính sách cho mọi ngả rẽ

Các nhánh thường quên cleanup:

- Nhận `statusCode >= 400` rồi throw exception trước khi nhận và close body.
- Đọc 10 dòng đầu bằng `limit(10)` rồi trả kết quả, quên đóng stream.
- `Flow.Subscriber` gặp lỗi parse dữ liệu rồi dừng request(n) nhưng không cancel subscription.
- `sendAsync` hoàn tất với `InputStream` nhưng callback không xử lý/đóng do exception.
- Đọc file streaming quá kích thước cho phép nhưng không `close()` trong `finally`.
- Thấy publisher từ `ofPublisher` nhưng không bao giờ subscribe.

Với `ofInputStream` và `ofLines`, có thể dùng `try`-with-resources ngay sau khi nhận body, dù bên trong code có nhiều nhánh `return` hay `throw`. Với `ofPublisher`, quản lý một subscription có terminal/cancel rõ ràng trong cả đường đi thành công và lỗi.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Pool kết nối tăng hoặc request kéo dài | Streaming body chưa tiêu thụ và chưa đóng | Drain đến EOF hoặc close/cancel |
| `send(...)` đã trả response nhưng tài nguyên vẫn còn | Streaming handler chỉ cần headers để trả response | Quản lý vòng đời `response.body()` |
| `findFirst()` lấy đúng dòng nhưng ứng dụng vẫn giữ exchange | Stream kết thúc sớm nhưng chưa `close` | Đặt `Stream<String>` trong try-with-resources |
| `readNBytes(n)` xong rồi bỏ InputStream | Chỉ đọc prefix, không đóng | Luôn `close` khi không đọc tiếp |
| `ofPublisher` không có dữ liệu được xử lý | Không subscribe, hoặc quên `request(n)` | Subscribe **một lần**, request đến terminal hoặc cancel |
| Publisher bị subscribe hai lần | `ofPublisher` là publisher response one-shot | Chỉ một subscriber; lần hai nhận `IllegalStateException` |
| Subscriber chờ `onComplete` sau cancel | Cancel không bảo đảm có terminal callback | Tự quản lý trạng thái đã hủy |
| HTTP connection không tái sử dụng sau close sớm | Client có thể đóng transport khi body chưa hết | Chấp nhận trade-off; chỉ drain khi an toàn/hợp lý |
| Đóng `HttpClient` nhưng shutdown treo | Streaming body còn mở hoặc subscriber không request/cancel | Hoàn tất/close/cancel mọi body trước shutdown |
| Dùng `try (HttpClient ...)` với `--release 11` | `AutoCloseable` của HttpClient có từ Java 21 | Java 11 chỉ dùng try-with-resources cho body stream |
| Dùng `readAllBytes` cho dữ liệu vô hạn | Không giới hạn kích thước body | Đọc theo chunk, giới hạn byte và deadline |
| Cho rằng `HttpResponse` phải gọi `close` | HttpResponse không phải AutoCloseable | Đóng body hoặc cancel subscription theo handler |
| Không xử lý lỗi đọc và hủy | `IOException` hoặc `onError` xuất hiện giữa stream | Try-with-resources, ghi nhận lỗi và kết thúc đúng vòng đời |

## 12. Bài tập tự kiểm tra

**Câu 1.** Gọi `send(request, BodyHandlers.ofInputStream())` rồi chỉ kiểm tra `statusCode()` và bỏ response. Đã đủ để trả tài nguyên chưa?  
**Đáp án:** Chưa. Phải đọc body đến EOF hoặc `close()` nếu không đọc.

**Câu 2.** `Stream<String> lines` từ `BodyHandlers.ofLines()` gọi `findFirst()` có cần `close()` không?  
**Đáp án:** Có. `findFirst` thường kết thúc sớm; stream có tài nguyên I/O và phải được đóng.

**Câu 3.** `BodyHandlers.ofPublisher()` có cho subscribe hai lần như một số custom request body publisher không?  
**Đáp án:** Không. Response publisher này chỉ cho **một** subscriber; lần subscribe sau gây `onError(IllegalStateException)`.

**Câu 4.** Khi không muốn nhận tiếp publisher, có nên giữ subscription mở nhưng không gọi `request(n)` nữa?  
**Đáp án:** Không. Gọi `cancel()` để kết thúc có chủ đích.

**Câu 5.** Đóng InputStream trước EOF có bảo đảm cùng TCP connection được tái sử dụng không?  
**Đáp án:** Không. Javadoc cảnh báo có thể đóng connection và không tái sử dụng được.

**Câu 6.** Tại sao không nên đọc hết một body cực lớn chỉ để giữ connection?  
**Đáp án:** Vì giới hạn bộ nhớ, băng thông, thời gian và rủi ro từ nguồn không đáng tin cậy có thể lớn hơn lợi ích keep-alive. Đóng/hủy sớm là lựa chọn hợp lý.

**Câu 7.** Trên Java 11 có thể dùng `try (HttpClient client = ...)` không?  
**Đáp án:** Không, API `HttpClient` chỉ triển khai `AutoCloseable` từ Java 21. Với Java 11, quản lý tài nguyên theo từng streaming body.

## 13. Ghi nhớ

Với **Body streaming** trên Java 11+, `HttpResponse` có thể được trả về khi **chưa đọc xong body**. Caller chịu trách nhiệm hoàn tất việc nhận dữ liệu:

- **`ofInputStream()`:** đọc đến EOF hoặc `InputStream.close()`.
- **`ofLines()`:** đọc hết dòng hoặc `Stream.close()`.
- **`ofPublisher()`:** subscribe một lần, request đến `onComplete`/`onError` hoặc `Subscription.cancel()`.
- **Không cần dữ liệu:** cân nhắc `BodyHandlers.discarding()` thay vì mở streaming body rồi bỏ mặc.
- **Đóng sớm:** có thể mất khả năng tái sử dụng connection, nhưng cần thiết để kiểm soát tài nguyên.
- **Java 11 và Java 21+:** `HttpClient` có vòng đời `AutoCloseable` từ Java 21; dù vậy phải xử lý body streaming đúng cách trước khi đóng client.

Đừng nhầm việc **đã có status/header**, **đã đọc hết body**, **đã đóng stream**, và **đã giải phóng HTTP exchange** là cùng một sự kiện.

### Tài liệu tham khảo chính thức còn áp dụng

- [Java 11 — HttpResponse.BodySubscribers: ofInputStream, ofLines, ofPublisher và yêu cầu đóng/hủy](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
- [Java 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Java 11 — HttpClient: send và sendAsync](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java 21 — HttpClient: AutoCloseable và close (Since: 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java 25 — HttpClient: tài nguyên streaming/publishing body và shutdown](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java 25 — BodySubscribers: hợp đồng hiện hành](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
