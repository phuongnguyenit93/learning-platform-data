# Thời điểm nhận HttpResponse khác với thời điểm đọc xong toàn bộ body

## 1. Phân biệt hai mốc thời gian

**Trong Java 17, nhận được `HttpResponse<T>` không luôn có nghĩa là đã tải và tiêu thụ hết HTTP response body.** Điều này phụ thuộc vào `HttpResponse.BodyHandler<T>` được truyền cho `HttpClient.send(...)` hoặc `sendAsync(...)`.

- Với `BodyHandlers.ofString()`, `BodyHandlers.ofByteArray()` và `BodyHandlers.ofFile(...)`, một response hoàn tất **thành công** cho biết body đã được subscriber đọc/xử lý hết theo dạng `String`, `byte[]` hoặc file.
- Với `BodyHandlers.ofInputStream()`, `BodyHandlers.ofLines()` và `BodyHandlers.ofPublisher()`, `HttpResponse` có thể được trả về **ngay sau khi headers được nhận đủ**, còn body tiếp tục đến sau. `response.body()` chỉ là **InputStream**, **Stream<String>** hoặc **Flow.Publisher<List<ByteBuffer>>** để caller tiêu thụ tiếp.
- Đối với `BodyHandlers.discarding()`, response thành công báo body đã được subscriber bỏ qua/tiêu thụ, không phải response body rỗng theo giao thức.

**Ghi nhớ:** completion của **response handle**, completion của **HTTP body** và completion của **business processing** là ba sự kiện khác nhau. Chúng có thể trùng nhau đối với một số handler, nhưng không được gộp làm một trong thiết kế client HTTP.

~~~text
Server:  gửi headers --- chunk body #1 ------- chunk body #2 ---- END
                 |           |                      |            |
Client:          v           v                      v            v
                 status/headers sẵn
                 |
                 +-- ofInputStream / ofLines / ofPublisher:
                 |     HttpResponse có thể xuất hiện từ đây
                 |     body vẫn còn đang đến; phải read/subscribe tiếp
                 |
                 +-- ofString / ofByteArray / ofFile:
                       HttpResponse thành công sau khi subscriber
                       đã đọc/xử lý xong toàn bộ body
~~~

Javadoc `HttpResponse` nói rõ thời điểm response trở nên available phụ thuộc BodyHandler. Tên `send` hoặc `sendAsync` **không tự quyết định** body có hoàn tất trước khi response được trả về hay không.

## 2. Các lớp API liên quan

`HttpClient` tổ chức việc nhận response theo hai pha:

1. **Nhận status code và headers.** `BodyHandler<T>.apply(ResponseInfo)` được gọi khi metadata đã có, **trước khi các byte body được chuyển tới subscriber**.
2. **Nhận body qua `BodySubscriber<T>`** do handler lựa chọn. Subscriber có thể gom dữ liệu thành `String`/`byte[]` hoặc trả một stream/publisher để caller xử lý incremental.

~~~text
                 HttpRequest
                      |
                      v
                HttpClient.send/sendAsync
                      |
                      v
                STATUS + HEADERS
                      |
                      v
           BodyHandler.apply(ResponseInfo)
                      |
                      v
                BodySubscriber<T>
                   /           \
              collector      streaming
                |               |
           chờ body hết     trả handle sớm
                |               |
                +------ HttpResponse<T> ------+
                                              |
                                      response.body(): T
~~~

Điều quan trọng là **`response.body()` trả đối tượng kiểu `T`**. Một object `InputStream` không có nghĩa toàn bộ byte đã được đọc; một `String` hoàn chỉnh từ `ofString` lại khác. Tương tự, publisher có thể sẵn ngay cả khi chưa có subscriber nào đăng ký.

### 2.1. Các mốc kiểm chứng

| Mốc | Đã biết | Chưa thể kết luận |
|---|---|---|
| Mở TCP/TLS thành công | Có kết nối giao vận thích hợp | Server đã phản hồi |
| Nhận headers | Biết status, headers, một số metadata | Body đầy đủ |
| `BodyHandler.apply` được gọi | Client đã đọc metadata và chọn subscriber | Body đã được subscriber xử lý hết |
| Có `HttpResponse<InputStream>` | Có stream để tiếp tục đọc | Đã tới EOF |
| Có `HttpResponse<String>` thành công | Subscriber đã dựng xong String từ body | JSON hợp lệ, nghiệp vụ thành công |
| `InputStream.read() == -1` | Body stream đã tới EOF theo API | File/DB đã commit |
| `Flow.Subscriber.onComplete()` | Publisher thông báo hoàn tất body thành công | Business consumer khác đã xong |
| Database commit | Nghiệp vụ đã ghi theo semantics giao dịch | Không thay thế kiểm tra lỗi trước đó |

Cũng phải phân biệt hai loại “đọc xong”: **network transport đã nhận đủ body bytes** và **ứng dụng đã đọc/parse/lưu dữ liệu**. Với streaming, chúng có thể bị tách ra bởi queue, backpressure, thread khác hoặc các bước xử lý nghiệp vụ.

## 3. Bảng so sánh các BodyHandlers quan trọng

| Handler Java 17 | Kiểu `response.body()` | Response có thể trả **trước khi body hoàn tất**? | Trách nhiệm caller |
|---|---|---|---|
| `BodyHandlers.ofString()` | `String` | Không, khi response hoàn tất thành công | Parse/validate dữ liệu và quản lý kích thước |
| `BodyHandlers.ofByteArray()` | `byte[]` | Không | Tránh tải không giới hạn vào heap |
| `BodyHandlers.ofFile(Path)` | `Path` | Không | Kiểm tra file, checksum và dọn file lỗi |
| `BodyHandlers.discarding()` | `Void` | Không; body được discard | Kiểm tra HTTP status |
| `BodyHandlers.replacing(value)` | `T` thay thế | Không; body được discard | Không nhầm value với nội dung server gửi |
| `BodyHandlers.ofInputStream()` | `InputStream` | **Có** | Đọc EOF hoặc close stream |
| `BodyHandlers.ofLines()` | `Stream<String>` | **Có** | Duyệt hết dòng hoặc close stream |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | **Có** | Subscribe một lần; demand/onComplete/onError/cancel |
| `BodyHandlers.ofByteArrayConsumer(...)` | `Void` | Không, sau khi body đã giao cho consumer | Consumer phải xử lý đủ nhanh |
| BodyHandler tùy chỉnh | Tùy `BodySubscriber<T>` | Tùy contract subscriber | Xác định chính xác khi getBody hoàn tất |

**Không nói mọi handler đều “chờ tải xong”.** `ofInputStream` trả handle sau headers vì nó tạo stream cho caller tự đọc; `ofPublisher` trả publisher để caller subscribe. Ngược lại, `ofFile` đợi body được viết hết vào file mới trả `Path` qua response thành công.

### 3.1. Lưu ý `ofString()`

~~~java
// Trích đoạn: client/request đã được tạo sẵn.
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
String text = response.body();
~~~

Khi `send` hoàn tất thành công, `text` chứa nội dung body đã được handler chuyển thành String. Theo Javadoc Java 17, `ofString()` dùng charset được chỉ định trong response `Content-Type` khi phù hợp, nếu thiếu/không hỗ trợ thì dùng UTF-8. Một String tạo thành công **không chứng minh** nội dung là JSON hợp lệ hay server đã xử lý đúng nghiệp vụ.

Với response lớn, `ofString()` có thể tạo áp lực heap. Nếu cần đọc file vài gigabyte, chuyển sang `ofFile` hoặc streaming body thay vì gom toàn bộ byte thành String.

### 3.2. `ofFile` không phải bằng chứng file bền vững

~~~java
// Trích đoạn: outputPath đã được xác định và chuẩn bị hợp lệ.
HttpResponse<java.nio.file.Path> downloaded = client.send(
        request, HttpResponse.BodyHandlers.ofFile(outputPath));
java.nio.file.Path saved = downloaded.body();
~~~

Tài liệu Java 17 ghi rõ lúc `HttpResponse<Path>` được trả, body đã được ghi hết vào file. Tuy nhiên điều đó **không tự bảo đảm** file đã được `fsync` ra vật lý, checksum hợp lệ, chữ ký file chính xác hoặc nội dung không độc hại. Caller còn phải kiểm tra status, kích thước, checksum và chính sách file cleanup. Một response lỗi cũng có thể ghi body lỗi vào file, nên không được bỏ qua `statusCode()`.

### 3.3. `discarding()` khác việc “quên không đọc stream”

`discarding()` tiêu thụ rồi bỏ body theo handler, do đó không để một `InputStream` chưa đọc cho application quản lý. Ngược lại, nếu gọi `ofInputStream()` rồi không đọc và cũng không close, app có thể giữ resources/kết nối không cần thiết. Khi không cần body, nên chọn `discarding()` hoặc đóng sớm streaming body theo policy, không bỏ mặc.

## 4. `send` và `sendAsync`: completion phụ thuộc handler

### 4.1. `HttpClient.send(...)`

`send` là lời gọi đồng bộ theo **điểm hoàn tất do BodyHandler xác định**:

~~~java
HttpResponse<InputStream> early = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());
// Đã có headers; HTTP body có thể đang tiếp tục được truyền.

HttpResponse<String> buffered = client.send(
        request, HttpResponse.BodyHandlers.ofString());
// Đã có String hoàn chỉnh khi lời gọi này thành công.
~~~

Đây là các **trích đoạn API** trên hai request độc lập. Đừng coi “send đồng bộ” là “mọi HTTP body đều đã đọc xong”. Stream trả ra có thể tiếp tục block ở `read` sau khi `send` đã trả.

### 4.2. `HttpClient.sendAsync(...)`

~~~java
CompletableFuture<HttpResponse<InputStream>> streamFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

CompletableFuture<HttpResponse<String>> textFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
~~~

Điểm dễ nhầm:

- `streamFuture.join()` có thể trả `HttpResponse<InputStream>` chỉ sau headers. `join` **không tự đọc stream tới EOF**.
- `textFuture.join()` chỉ trả thành công sau khi subscriber `ofString` đã dựng String.
- `thenApply(HttpResponse::statusCode)` trên streaming future có thể chạy **rất sớm** và chỉ biết metadata.
- `CompletableFuture.isDone()` true không chứng minh success nếu future đã **fail/cancel**; ngay cả success của streaming future cũng không chứng minh body hoàn tất.
- `HttpResponse<T>.body()` của publisher là publisher một lần, **không phải một future tự hoàn tất business consumer**.

**Hệ quả:** nếu code dùng `sendAsync(...ofInputStream()).thenAccept(r -> logSuccess())`, chữ “success” rất dễ bị hiểu nhầm thành đã tải hoàn chỉnh. Đúng hơn là ghi **response_headers_received**, rồi có **body_completed/body_failed/body_aborted** riêng.

## 5. `ofInputStream()`: có response trước EOF

Với `BodyHandlers.ofInputStream()`, Javadoc Java 17 nói rằng **headers đã được đọc đầy đủ khi `HttpResponse` trở về**, nhưng body **có thể chưa nhận hết**. `response.body()` cho caller một `InputStream` để đọc byte khi chúng được gửi tới.

~~~java
// Trích đoạn: client/request đã tồn tại.
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

System.out.println(response.statusCode()); // Biết HTTP status.
try (InputStream in = response.body()) {
    byte[] bytes = in.readAllBytes();        // Chỉ khi tới EOF mới đủ body.
}
~~~

Ví dụ dùng `readAllBytes()` chỉ phù hợp với body nhỏ/được kiểm soát. Đối với dữ liệu lớn nên đọc theo block và giới hạn tổng byte. Tách rõ:

1. `HttpResponse` có sẵn: đã có response metadata và stream.
2. `in.read(buffer)`: có thể **chặn** nếu chưa có byte mới; một lần đọc không phải toàn body.
3. `in.read() == -1` hoặc `readAllBytes()` hoàn thành không lỗi: stream tới EOF.
4. `InputStream.close()` trước EOF: **chấm dứt/huỷ việc tiêu thụ**, không phải “body đã xử lý thành công”.

### 5.1. Đọc stream xong hoặc đóng là bắt buộc

Javadoc `BodySubscribers.ofInputStream()` yêu cầu người dùng **đọc tới EOF hoặc `close()`**, để giải phóng resources liên quan tới HTTP exchange. Đóng trước khi đọc hết **có thể** khiến underlying connection không được reuse; đó là trade-off hợp lý nếu muốn dừng download.

**Không dùng `available() == 0` làm tiêu chí EOF.** `available()` chỉ ước lượng byte có thể đọc không blocking, không phải remaining response length. Cũng không lấy `Content-Length` làm bằng chứng rằng bytes thực tế đã được nhận đủ.

### 5.2. Lỗi có thể xảy ra sau khi đã in status 200

~~~java
// Trích đoạn, giả định response là HttpResponse<InputStream>.
try (InputStream in = response.body()) {
    byte[] data = new byte[8192];
    for (int n; (n = in.read(data)) != -1;) {
        consume(data, n);
    }
} catch (IOException ex) {
    // Lỗi body processing/transport có thể xảy ra SAU headers.
}
~~~

`consume` ở đây là hàm của ứng dụng, không phải một chương trình độc lập. Server có thể đóng bất thường, gửi body sai framing hoặc mạng lỗi khi đang truyền. `HttpResponse` đã tồn tại nhưng body chưa complete; ghi trạng thái **body_failed** thay vì coi response status 200 là download success.

Nếu một worker thread tiêu thụ stream, ownership cần rõ: scope của caller không được auto-close stream ngay sau khi gửi reference cho worker chưa xử lý xong.

## 6. `ofLines()`: Stream<String> đọc lười (lazy)

~~~java
HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    lines.forEach(System.out::println);
}
~~~

Ở đây `Stream<String>` không phải `List<String>` đã được dựng xong. Các dòng được đọc/giải mã khi dữ liệu đến; một dòng chưa kết thúc có thể khiến lần duyệt tiếp theo đợi thêm byte. Response có thể được trả về **khi body chưa nhận đủ**.

Quan trọng:

- **Tiêu thụ đến hết hoặc close `Stream<String>`** theo Javadoc.
- Dùng terminal operation short-circuit như `limit(5)` hoặc `findFirst()` chưa chắc đọc hết body; vẫn cần `close()`.
- Dòng văn bản không phải TCP packet, HTTP chunk hay một message nghiệp vụ được bảo đảm. Cần định nghĩa newline encoding, record size và chính sách lỗi.
- Nếu ứng dụng dùng SSE, NDJSON, log live stream, body có thể kéo dài không giới hạn: “đợi full response” có thể là sai mục tiêu; đọc từng record với deadline/backpressure riêng.

## 7. `ofPublisher()`: HttpResponse chứa một Publisher

`BodyHandlers.ofPublisher()` trả `HttpResponse<Flow.Publisher<List<ByteBuffer>>>` **sau headers, không cần đợi full body**. Body là một publisher để caller subscribe:

~~~java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.send(request, HttpResponse.BodyHandlers.ofPublisher());

Flow.Publisher<List<ByteBuffer>> publisher = response.body();
~~~

Subscriber có bốn phương thức cơ bản:

| Callback | Ý nghĩa |
|---|---|
| `onSubscribe(Flow.Subscription s)` | Nhận subscription, phát `request(n)` hoặc `cancel()` |
| `onNext(List<ByteBuffer> items)` | Nhận một **event** mang danh sách ByteBuffer |
| `onError(Throwable error)` | Stream thất bại; không coi là hoàn tất thành công |
| `onComplete()` | Stream được báo hoàn tất thành công |

`subscription.request(1)` xin **một lần `onNext`**, **không phải một byte**. Mỗi event có thể mang nhiều ByteBuffer, mỗi buffer chứa số byte thay đổi theo I/O. Chọn demand theo tốc độ xử lý downstream để tránh queue/memory phình to.

**Publisher của `ofPublisher` chỉ cho subscribe một lần.** Lần subscribe thứ hai không tạo bản copy response mới; theo Javadoc, subscriber thứ hai nhận `onError` với `IllegalStateException`. Nếu cần fan-out cho nhiều consumer, application phải có cơ chế multicast riêng ở tầng nhận body.

### 7.1. Khi nào body publisher được coi là xong?

- **`HttpResponse<Publisher>` xuất hiện:** chỉ có publisher handle.
- **`onSubscribe` xuất hiện:** thiết lập subscription, chưa chắc nhận byte.
- **`onNext`:** có một số byte, chưa bảo đảm toàn body.
- **`onComplete`:** được thông báo **toàn bộ body đã đến** theo publisher.
- **`onError`:** không có complete thành công.
- **`cancel`:** caller đã từ bỏ nhận tiếp, **không phải success**.

Khi không cần toàn body, subscriber phải `cancel()` thay vì “đăng ký nhưng không request và cũng không cancel”. Cancel có thể làm connection không được reuse tùy HTTP version/implementation; vẫn tốt hơn để resources treo vô hạn.

### 7.2. ByteBuffer ownership trong callback

Một event `onNext` gồm danh sách ByteBuffer. Mẫu an toàn thường xử lý/copy data trong callback rồi mới request event tiếp theo:

~~~java
// Trích đoạn ở onNext(List<ByteBuffer> items):
for (ByteBuffer item : items) {
    byte[] copy = new byte[item.remaining()];
    item.get(copy);
    output.write(copy, 0, copy.length);
}
subscription.request(1);
~~~

`output` là sink ứng dụng (ví dụ `ByteArrayOutputStream` trong test), không phải mẫu sản xuất với body không giới hạn. Không giữ reference tới ByteBuffer từ upstream vô thời hạn và tự cho rằng ownership hoặc backing storage mãi bất biến; dùng copy/lease và backpressure rõ ràng.

## 8. Demo Java 17+ chạy được: giữ lại nửa body để chứng minh mốc hoàn tất

Demo dùng `HttpServer` cục bộ trong module JDK `jdk.httpserver`. Server gửi `part1-part2` thành hai phần, nhưng **dừng sau phần đầu** đến khi client giải phóng `CountDownLatch`. Vì thế, chương trình **không phụ thuộc Thread.sleep hay timing may rủi**.

Ba trường hợp trên ba endpoint khác nhau:

1. `/stream` với `ofInputStream()`: client đã có HttpResponse và status 200 khi phần cuối chưa được gửi. Sau đó đọc `part1-`, mở chốt và đọc `part2` đến EOF.
2. `/string` với `ofString()`: client biết server đã gửi phần đầu, nhưng future response **chưa complete**; chỉ sau khi mở chốt và body nhận hết mới có String `part1-part2`.
3. `/publisher` với `ofPublisher()`: client có response/publisher khi phần cuối chưa gửi; subscriber request các events, đợi `onComplete` rồi mới ghi nhận full body.

Tạo file **`HttpBodyTimingDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class HttpBodyTimingDemo {
    private static final int SECONDS = 5;

    static class Gate {
        final CountDownLatch firstSent = new CountDownLatch(1);
        final CountDownLatch finish = new CountDownLatch(1);
    }

    private static void sendInTwoParts(HttpExchange exchange, Gate gate)
            throws IOException {
        byte[] first = "part1-".getBytes(StandardCharsets.US_ASCII);
        byte[] last = "part2".getBytes(StandardCharsets.US_ASCII);
        exchange.getResponseHeaders().set("Content-Type", "text/plain");
        exchange.sendResponseHeaders(200, first.length + last.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(first);
            out.flush();
            gate.firstSent.countDown();
            try {
                if (!gate.finish.await(SECONDS, TimeUnit.SECONDS)) {
                    throw new IOException("Test server release timeout");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IOException(e);
            }
            out.write(last);
        } finally {
            gate.firstSent.countDown();
            exchange.close();
        }
    }

    private static void await(CountDownLatch latch) throws Exception {
        if (!latch.await(SECONDS, TimeUnit.SECONDS)) {
            throw new IOException("Deadline exceeded");
        }
    }

    public static void main(String[] args) throws Exception {
        Gate streamGate = new Gate();
        Gate stringGate = new Gate();
        Gate publisherGate = new Gate();
        InetAddress host = InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(new InetSocketAddress(host, 0), 0);
        server.createContext("/stream",
                exchange -> sendInTwoParts(exchange, streamGate));
        server.createContext("/string",
                exchange -> sendInTwoParts(exchange, stringGate));
        server.createContext("/publisher",
                exchange -> sendInTwoParts(exchange, publisherGate));
        server.start();
        try {
            URI base = new URI("http", null, host.getHostAddress(),
                    server.getAddress().getPort(), "/", null, null);
            HttpClient client = HttpClient.newHttpClient();

            HttpResponse<InputStream> streamed = client.sendAsync(
                    HttpRequest.newBuilder(base.resolve("stream")).GET().build(),
                    HttpResponse.BodyHandlers.ofInputStream())
                    .get(SECONDS, TimeUnit.SECONDS);
            await(streamGate.firstSent);
            System.out.println("streamStatus=" + streamed.statusCode());
            System.out.println("streamBeforeBodyEnd=" +
                    (streamGate.finish.getCount() == 1));
            try (InputStream in = streamed.body()) {
                System.out.println("streamFirst=" +
                        new String(in.readNBytes(6), StandardCharsets.US_ASCII));
                streamGate.finish.countDown();
                System.out.println("streamRest=" +
                        new String(in.readAllBytes(), StandardCharsets.US_ASCII));
            }

            CompletableFuture<HttpResponse<String>> buffered = client.sendAsync(
                    HttpRequest.newBuilder(base.resolve("string")).GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            await(stringGate.firstSent);
            System.out.println("stringDoneBeforeRelease=" + buffered.isDone());
            stringGate.finish.countDown();
            System.out.println("stringBody=" +
                    buffered.get(SECONDS, TimeUnit.SECONDS).body());

            HttpResponse<Flow.Publisher<List<ByteBuffer>>> published =
                    client.sendAsync(
                            HttpRequest.newBuilder(base.resolve("publisher"))
                                    .GET().build(),
                            HttpResponse.BodyHandlers.ofPublisher())
                            .get(SECONDS, TimeUnit.SECONDS);
            await(publisherGate.firstSent);
            System.out.println("publisherBeforeBodyEnd=" +
                    (publisherGate.finish.getCount() == 1));
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            CountDownLatch completed = new CountDownLatch(1);
            AtomicReference<Throwable> error = new AtomicReference<>();

            published.body().subscribe(new Flow.Subscriber<>() {
                Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    s.request(1);
                }

                @Override
                public void onNext(List<ByteBuffer> items) {
                    for (ByteBuffer item : items) {
                        byte[] copy = new byte[item.remaining()];
                        item.get(copy);
                        bytes.write(copy, 0, copy.length);
                    }
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable failure) {
                    error.set(failure);
                    completed.countDown();
                }

                @Override
                public void onComplete() {
                    completed.countDown();
                }
            });

            publisherGate.finish.countDown();
            await(completed);
            if (error.get() != null) {
                throw new IOException("Publisher failure", error.get());
            }
            System.out.println("publisherBody=" +
                    bytes.toString(StandardCharsets.US_ASCII));
        } finally {
            streamGate.finish.countDown();
            stringGate.finish.countDown();
            publisherGate.finish.countDown();
            server.stop(0);
        }
    }
}
~~~

Chạy trên **JDK 17 trở lên**:

~~~bash
javac --release 17 --add-modules jdk.httpserver HttpBodyTimingDemo.java
java --add-modules jdk.httpserver HttpBodyTimingDemo
~~~

**Stdout chính xác đã kiểm chứng khi biên dịch `--release 17` và chạy trên OpenJDK 24:**

~~~text
streamStatus=200
streamBeforeBodyEnd=true
streamFirst=part1-
streamRest=part2
stringDoneBeforeRelease=false
stringBody=part1-part2
publisherBeforeBodyEnd=true
publisherBody=part1-part2
~~~

### 8.1. Kết quả chỉ nói điều gì?

- `streamStatus=200` và `streamBeforeBodyEnd=true`: client đã có response metadata dù server chưa mở chốt gửi phần cuối. Đó là **response-before-body-completed**.
- `streamFirst=part1-`: ứng dụng mới đọc sáu byte đầu sau khi response được trả. Việc đọc là bước riêng và có thể blocking.
- `streamRest=part2`: sau khi mở chốt, client nhận phần cuối rồi tới EOF.
- `stringDoneBeforeRelease=false`: `ofString` chưa hoàn tất response future khi body chưa gửi hết, dù headers và phần đầu đã tới.
- `stringBody=part1-part2`: body collector trả String sau khi nhận đủ.
- `publisherBeforeBodyEnd=true`: publisher handle được trả sớm.
- `publisherBody=part1-part2`: subscriber đã nhận body rồi gọi `onComplete`; chương trình chỉ in nội dung sau latch completion.

Chương trình **không** khẳng định mỗi lần server `write` tương ứng một lần client `read` hoặc một `onNext`. TCP và HTTP client có thể chia/gộp bytes theo tình huống. Chốt đồng bộ đảm bảo **phần cuối chưa được phép gửi**, không phụ thuộc packet boundary.

### 8.2. Giới hạn của demo

- Server dùng HTTP **loopback**, không dùng Internet hay TLS; mục tiêu kiểm tra **mốc nhận HttpResponse**, không đo bảo mật HTTPS.
- Tổng body 11 byte, nên `ByteArrayOutputStream` an toàn trong demo; file tải thật cần quota và streaming sink.
- Demo giữ mỗi exchange hữu hạn và deadline 5 giây; stream live production có thể không kết thúc.
- Publisher của demo chỉ subscribe một lần, request 1 event/lượt và copy dữ liệu trước khi request tiếp.
- Khi test thất bại, finally mở các chốt và dừng server; caller thực tế còn cần policy timeout/cancellation sâu hơn.

## 9. Metadata HTTP không phải chứng nhận body đủ

Một `HttpResponse<T>` cho phép lấy:

| Phương thức | Nội dung |
|---|---|
| `statusCode()` | HTTP status code |
| `headers()` | Map các response headers |
| `version()` | Phiên bản HTTP |
| `uri()` | URI request tương ứng response, có thể là cuối cùng khi auto redirect |
| `request()` | Request liên quan |
| `body()` | Giá trị kiểu `T` theo handler |

Những metadata này có sẵn khi response handle được trả. Nhưng **`response.body()` có thể là streaming handle**, chưa có byte cuối. Một status 200 không nói gì về số byte sau đó bị mất/lỗi; một Content-Length hợp lệ không chứng minh Java đã nhận đủ body.

Một response status 404/500 cũng có thể chứa body. Các `BodyHandlers` built-in như `ofString` **không tự bỏ body vì status >= 400**. Nếu muốn chọn chính sách theo status, dùng custom `BodyHandler` hoặc xử lý response status với cleanup phù hợp.

### 9.1. HTTP framing và EOF

HTTP/1.1 có cơ chế độ dài body như `Content-Length` hoặc `Transfer-Encoding: chunked`; HTTP/2/HTTP/3 có frame/stream end phù hợp. `HttpClient` xử lý framing để caller nhận `InputStream`/Publisher ở mức **HTTP body bytes**, không phải tự parse raw chunk delimiters.

- **`Content-Length`** mô tả lượng byte theo semantics HTTP, không phải số ký tự Unicode sau decode hay số bytes đã tải tới thời điểm xem header.
- **Chunked** chia body trên wire, nhưng không bảo đảm mỗi `InputStream.read` hoặc `onNext` khớp một HTTP chunk.
- **HTTP/2 end-of-stream** có thể hoàn tất body stream mà TCP connection vẫn sống để phục vụ nhiều request.
- **HEAD, 204, 304** và các trường hợp đặc biệt có quy tắc không có body theo HTTP; không nên ép chờ một payload không tồn tại.
- Nếu server đóng sớm/truncated framing, consumer có thể nhận IOException/onError **sau khi response handle đã được cung cấp**.

Do đó EOF của `InputStream` là **EOF của HTTP response body** theo abstraction, không nhất thiết là TCP connection đóng.

## 10. Timeouts: timeout response không chắc bao phủ body đọc sau

| Cơ chế | Mục đích | Ngộ nhận cần tránh |
|---|---|---|
| `HttpClient.Builder.connectTimeout` | Giới hạn giai đoạn thiết lập connection theo contract | Không phải thời hạn tải body |
| `HttpRequest.Builder.timeout` | Giới hạn HTTP request/response exchange theo API | Không mặc định giám sát mãi caller đọc stream sau response sớm |
| `CompletableFuture.orTimeout` của `sendAsync` | Giới hạn thời điểm hoàn tất response future | Streaming future có thể hoàn tất ngay sau headers |
| `InputStream.read` | Đọc body bytes, có thể block | `response` đã tới không nghĩa từng read có deadline |
| `Flow.Subscription.cancel()` | Dừng tiêu thụ publisher | Không phải full body success |

Dùng `sendAsync(...ofInputStream()).orTimeout(...)` **không đủ** để đặt deadline đọc toàn bộ streaming body: khi future đã hoàn tất sớm, deadline Future không tiếp tục đại diện cho việc đọc. Một service cần **deadline tổng thể**, giới hạn số byte, **idle timeout** (nếu phù hợp) và cơ chế cancellation/close stream theo môi trường JDK thực tế.

Không nên coi `CompletableFuture.cancel(true)` trên future **đã thành công và trả stream** là một thao tác tự động đọc/đóng stream. Chính caller đang giữ handle phải quản lý giải phóng resources.

## 11. Connection reuse, cleanup và trạng thái kết thúc

Đối với streaming handler, **caller có trách nhiệm kết thúc việc tiêu thụ**:

| Kiểu body | Kết thúc thành công | Khi bỏ dở |
|---|---|---|
| `InputStream` | Đọc đến `-1` | `close()` |
| `Stream<String>` | Duyệt đến hết | `Stream.close()` |
| `Flow.Publisher` | `onComplete()` | `Subscription.cancel()` |
| `String` / `byte[]` | Handler đã hoàn tất việc gom body | Quản lý memory/application processing riêng |
| `Path` từ `ofFile` | Handler đã ghi xong file | Dọn file lỗi/không hợp lệ, kiểm tra checksum |

Đóng stream sớm/cancel publisher có thể làm HTTP connection **không được reuse**. Nhưng vẫn cần đóng/cancel nếu consumer không tiếp tục, thay vì giữ network resources và heap memory mãi.

**Ba outcome không được gộp:**

- `BODY_COMPLETED`: đã đọc hết thành công qua EOF/onComplete.
- `BODY_FAILED`: gặp IOException, publisher onError, decode lỗi, quá hạn, framing lỗi.
- `BODY_ABORTED`: caller chủ động đóng/cancel trước khi body hoàn tất.

Với live stream có mục đích chạy lâu dài, không nhận toàn bộ body không nhất thiết là lỗi; app thường dựa trên **số record đã xử lý và trạng thái subscription** chứ không cố chờ toàn bộ body vô hạn.

## 12. Tối ưu bộ nhớ và backpressure cho body lớn

Với body nhỏ, `ofString()/ofByteArray()` đơn giản. Với download 500 MiB, việc gom toàn bộ có thể gây heap pressure hoặc `OutOfMemoryError`. Hãy cân nhắc `ofFile`, `ofInputStream` hoặc `ofPublisher`:

| Yêu cầu | Lựa chọn thường phù hợp |
|---|---|
| JSON nhỏ, giới hạn size rõ ràng | `ofString` hoặc `ofByteArray` rồi parse |
| File download lớn đến disk | `ofFile`, kiểm tra status/checksum/file size |
| Gửi bytes tới một parser streaming | `ofInputStream` với quota/deadline |
| Nhận NDJSON hay dòng text dần | `ofLines`, phải close khi dừng sớm |
| Pipeline reactive/backpressure | `ofPublisher`, theo demand và một subscriber |
| Không cần body | `discarding` |

`Content-Length` có thể vắng, sai hoặc phản ánh nội dung nén, vì vậy **đếm byte thực tiêu thụ** và áp limits thay vì chỉ tin header. Với nội dung nén, cần quota sau giải nén để phòng zip bomb. Cũng cần giới hạn thời gian không có tiến độ và số ByteBuffer đang chờ trong downstream queue.

Với publisher, `request(1)` tính **event** chứ không phải byte; mỗi event có thể chứa nhiều buffer. Không tự động `request(Long.MAX_VALUE)` rồi cất toàn bộ dữ liệu vào danh sách chưa giới hạn.

## 13. HTTP status khác lỗi trong lúc đọc body

HTTP 404/500 là **status do server trả về**, không nhất thiết Java throw exception. Ngược lại, transport I/O có thể lỗi khi đang tải body sau status 200.

Ví dụ luồng xử lý:

~~~text
response_received(status=200)
    |
    +-- body_stream read/Flow onNext ... 
           |
           +-- EOF/onComplete: body_completed
           |
           +-- IOException/onError: body_failed
           |
           +-- app close/cancel: body_aborted
~~~

Không nên log download_success ngay trong `thenApply(HttpResponse::statusCode)` khi dùng streaming. Log time-to-headers, time-to-first-byte, body-duration, bytes-read và business completion riêng. Một app có thể đã commit 20 record rồi gặp lỗi ở record 21; business layer phải có transaction/idempotency policy phù hợp.

### 13.1. Custom BodyHandler chọn cách xử lý theo status

Vì `BodyHandler` nhận status/headers trước body, bạn có thể chọn cách tiêu thụ khác:

~~~java
// Trích đoạn: client/request tồn tại và đã import StandardCharsets.
HttpResponse.BodyHandler<String> handler = info ->
        info.statusCode() == 200
                ? HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8)
                : HttpResponse.BodySubscribers.replacing("BODY_SKIPPED");

HttpResponse<String> response = client.send(request, handler);
~~~

Khi status khác 200, chuỗi `BODY_SKIPPED` là **giá trị do client tự tạo**, không phải nội dung body thật từ server. `replacing` discard body rồi trả giá trị. Đừng vô tình báo “server trả BODY_SKIPPED”.

## 14. Lỗi phổ biến cần sửa

| Hiểu nhầm | Vì sao sai | Hướng sửa |
|---|---|---|
| `send` đã trả => tất cả body đã tải | Với `ofInputStream` và `ofLines` có thể trả trước EOF | Đọc EOF/close theo policy |
| `sendAsync(...).join()` => full body | Future có thể là future của **stream handle** | Xét handler và theo dõi body completion |
| `response.body()` luôn là byte[]/String | Có thể là InputStream/Publisher/Stream | Xem kiểu `T` |
| `statusCode()==200` => download success | Body I/O còn có thể lỗi | Ghi body completed riêng |
| `InputStream.available()==0` => EOF | available không phải remaining length | Dùng `read()==-1` |
| `ofFile` trả Path trước khi ghi xong | Handler đợi body được ghi hết | Chỉ xử lý Path sau successful response |
| `ofLines().limit(1)` đã tự đóng body | Short-circuit chưa tiêu thụ hết | Dùng try-with-resources |
| Publisher được subscribe nhiều lần | `ofPublisher` chỉ chấp nhận một subscriber | Tự fan-out nếu cần |
| `subscription.request(1)` là một byte | Đây là một event onNext | Xử lý List<ByteBuffer> và quota |
| `close` stream = tải thành công | Đóng sớm là aborted | Có trạng thái aborted |
| Body size từ Content-Length là chắc chắn | Metadata có thể thiếu/sai | Đếm byte và giới hạn |
| Body đã đọc hết nghĩa parse thành công | Schema/encoding/commit có thể lỗi | Tách app processing success |
| Response 500 sẽ tự ném IOException | HTTP status không tự là I/O error | Xử lý status/body và close |
| Không cần close stream vì client quản lý | Caller sở hữu stream handle | EOF hoặc close/cancel |
| Timeout của future response giám sát toàn stream | Future có thể done trước body | Deadline riêng cho body |

## 15. Checklist thực hành

**Trước khi chọn handler:** body có lớn không, có cần incremental processing không, có downstream chậm không, có file path/quota/checksum policy không? Dùng collector hay streaming? Có cần đo riêng response headers và body bytes?

**Khi HttpResponse có sẵn:** chỉ ghi nhận status/headers và kiểu body. Nếu body là InputStream/Stream/Publisher, phân công rõ owner và cơ chế cleanup. Không coi response handle là full download nếu contract không cho phép.

**Khi tiêu thụ:** đọc cho đến EOF hoặc onComplete, kiểm tra lỗi giữa chừng, hạn chế bytes/time, không tin Content-Length là số liệu tuyệt đối; stream text phải giữ trạng thái charset/record framing.

**Khi kết thúc:** phân biệt complete, failed, aborted; close/cancel khi bỏ dở, xử lý ảnh hưởng connection reuse; file cần checksum, business data cần parse/transaction kiểm tra riêng.

## 16. Câu hỏi tự kiểm tra

**1. Nhận được `HttpResponse<InputStream>` chứng minh body đủ chưa?** Chưa. Headers đã sẵn; stream có thể còn đang truyền.

**2. `send(...ofString())` trả thành công nghĩa gì?** Subscriber đã tạo đầy đủ String từ body, không tự chứng minh nội dung hợp lệ.

**3. `sendAsync(...ofPublisher()).join()` thành công nhưng chưa subscribe, body hoàn tất chưa?** Không thể kết luận. Phải subscribe một lần rồi đợi onComplete hoặc xử lý onError/cancel.

**4. `InputStream.read() == -1` nghĩa kết nối TCP chắc chắn đóng?** Không. Đây là EOF của body stream theo API; HTTP connection có thể được reuse.

**5. `InputStream.available() == 0` nghĩa body đã kết thúc?** Không; available không phải EOF.

**6. `BodyHandlers.ofFile` trả Path ở thời điểm nào?** Sau khi body đã được subscriber ghi hết vào file.

**7. `ofLines` dừng ở dòng thứ năm bằng limit(5) cần làm gì?** Đóng Stream nếu không đọc hết.

**8. Publisher có subscribe hai lần để hai người nhận cùng body được không?** Không với `ofPublisher`; phải tự fan-out.

**9. `request(1)` trong Flow xin một byte?** Không, một event `onNext`; event có thể mang nhiều ByteBuffer.

**10. HTTP 200 đã tới nhưng `InputStream.read` ném IOException sau đó. Body success?** Không; đó là body failure sau headers.

**11. Vì sao demo dùng CountDownLatch thay Thread.sleep?** Để chắc chắn server giữ phần cuối body, không phụ thuộc scheduler.

**12. `BodyHandlers.discarding` khác bỏ mặc InputStream như thế nào?** Discarding tiêu thụ và bỏ body; bỏ mặc stream có thể giữ connection/resources.

**13. Stream close trước EOF có là body completed?** Không, đánh dấu aborted, dù connection resources có thể được giải phóng.

**14. `response.body()` là String thì JSON schema đã được validate?** Không; String chỉ là bước decode.

## 17. Tài liệu Java và HTTP chính thức

- [Java SE 17 – HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): response có sẵn trước/sau body phụ thuộc `BodyHandler`.
- [Java SE 17 – HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofString`, `ofByteArray`, `ofFile`, `ofInputStream`, `ofLines`, `ofPublisher` và discard.
- [Java SE 17 – HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): streaming completion, EOF/close, single subscription và cleanup.
- [Java SE 17 – HttpResponse.BodyHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html): custom handler được gọi sau headers/trước body.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`/`sendAsync`.
- [Java SE 17 – Flow](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html): `Publisher`/`Subscriber`/`Subscription`.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback test server.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP status và response semantics.
- [RFC 9112 – HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): message framing và body.
- [RFC 9113 – HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): DATA frames và end-of-stream.

**Kết luận:** `HttpResponse<T>` báo **đã có kết quả mà BodyHandler quyết định**, chứ không phải một lời khẳng định chung rằng mọi byte body đã tới. Với handler gom body như `ofString/ofByteArray/ofFile`, successful response tương ứng body đã được xử lý hết theo dạng mong muốn. Với `ofInputStream/ofLines/ofPublisher`, response có thể xuất hiện sau headers trong khi body vẫn đang đến; phải theo dõi **EOF/onComplete**, lỗi/cancel, quotas, timeout và cleanup để biết khi nào body thực sự hoàn tất.
