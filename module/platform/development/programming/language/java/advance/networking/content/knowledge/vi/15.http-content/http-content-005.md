# Nhận dạng luồng bằng ofInputStream, ofLines hoặc ofPublisher trong Java HttpClient (Java 17+)

Khi nhận một HTTP response lớn hoặc được gửi dần, ứng dụng không nên mặc định gọi `HttpResponse.BodyHandlers.ofString()` hoặc `ofByteArray()` để gom **toàn bộ body vào bộ nhớ**. Java 17 có ba kiểu nhận body **dạng luồng**: `ofInputStream()` trả `InputStream` byte-oriented, `ofLines()` trả `Stream<String>` đã tách dòng, còn `ofPublisher()` trả một `Flow.Publisher<List<ByteBuffer>>` có **demand/backpressure** theo chuẩn `java.util.concurrent.Flow`. Chọn sai hoặc bỏ mặc luồng có thể làm kết nối HTTP không được giải phóng, ứng dụng giữ tài nguyên lâu, hoặc xử lý byte/text sai.

Đây là bài Knowledge trong mục **Nội dung HTTP** của **Java Advance - networking**, tập trung vào **nhận dạng ba phương pháp streaming body**, cách chọn theo kiểu dữ liệu, trách nhiệm kết thúc exchange, Flow subscription và các tình huống lỗi. Các ví dụ chạy độc lập trên **JDK 17+**, sử dụng HTTP server loopback nên không cần gọi API công khai hay Internet.

## 1. Bảng so sánh nhanh ba BodyHandler

| API Java 17 | Kiểu `HttpResponse<T>.body()` | Mức trừu tượng | Khi nào thích hợp | Trách nhiệm sau `send` |
| --- | --- | --- | --- | --- |
| `BodyHandlers.ofInputStream()` | `InputStream` | **Byte stream**, đọc theo số byte tùy ý | Tệp nhị phân, dữ liệu không biết định dạng, parser nhận `InputStream` | **Đọc tới EOF hoặc đóng `InputStream`** |
| `BodyHandlers.ofLines()` | `Stream<String>` | **Text line stream**, đã giải mã charset và tách dòng | Nhật ký, danh sách text, NDJSON, dòng sự kiện khi có parser phù hợp | **Duyệt tới hết hoặc đóng `Stream`** |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | **Reactive byte stream**, có `Subscription` | Pipeline bất đồng bộ, consumer xử lý `ByteBuffer` và demand | **Subscribe đúng một lần; request đến terminal event hoặc cancel** |

**Điểm chung quan trọng:** với cả ba kiểu trên, `client.send(request, handler)` hoặc future `sendAsync` có thể cung cấp đối tượng `HttpResponse` **sau khi đọc xong response headers**, trong lúc **body chưa được nhận hết**. “Đã có `HttpResponse`” không đồng nghĩa “đã xử lý xong body”, và **không** đồng nghĩa connection chắc chắn đã sẵn sàng để reuse. 

So sánh thêm:

- `ofString()` và `ofByteArray()` thông thường trả response sau khi **toàn bộ body** đã được tích lũy; đơn giản nhưng không lý tưởng cho nội dung quá lớn.
- `ofFile(path)` ghi trực tiếp ra tệp theo handler, thường tiện hơn tự đọc `InputStream` khi mục đích chỉ là tải file, nhưng vẫn cần kiểm soát đường dẫn, kích thước, thời gian và lỗi I/O.
- Không phương pháp nào biến HTTP thành UDP datagram. **TCP/HTTP body vẫn là chuỗi byte có thể chia thành nhiều lần nhận**; mọi ranh giới batch/buffer do transport quyết định, không phải ranh giới application message.

## 2. HttpClient, BodyHandler và BodySubscriber đóng vai trò gì?

Chuỗi xử lý trong JSSE/JDK HttpClient có thể xem như sau:

```text
HttpClient.send / sendAsync
          |
          v
HTTP response status + headers received
          |
          v
BodyHandler<T> nhận ResponseInfo
          |
          | chọn một BodySubscriber<T>
          v
BodySubscriber<T> nhận dữ liệu dạng List<ByteBuffer>
          |
          +-- ofInputStream -> InputStream (caller kéo byte)
          +-- ofLines       -> Stream<String> (caller kéo dòng)
          +-- ofPublisher   -> Flow.Publisher<List<ByteBuffer>> (caller subscribe)
          |
          v
body drained / stream closed / subscription cancelled
          |
          v
Exchange resources released theo cơ chế implementation
```

- **`BodyHandler<T>`** được chọn khi status và headers có sẵn, *trước khi* đọc toàn body. Handler quyết định subscriber nào tiếp nhận nội dung.
- **`BodySubscriber<T>`** thực chất là subscriber của một flow `List<ByteBuffer>` do HTTP implementation xuất bản. Nó chuyển byte tới kiểu kết quả `T`.
- **`HttpResponse<T>`** mang status code, headers, request, version và `body()` kiểu `T`.
- **`BodyHandlers.ofInputStream/ofLines/ofPublisher`** tạo adapter tương ứng. Đừng nhầm *response* đã được trả cho ứng dụng với *subscriber* đã phát ra terminal `onComplete`.

Hợp đồng Java 17 về streaming/cleanup được mô tả tường minh trong [BodySubscribers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html). 

## 3. Trường hợp 1 — ofInputStream(): nhận luồng byte thô

Khai báo đúng kiểu:

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream input = response.body()) {
    // Đọc một phần có giới hạn hoặc đọc hết tùy giao thức.
}
```

Đây là **snippet minh họa**, `client`, `request`, các imports và method bao ngoài chưa được khai báo. Với `InputStream`:

1. `read(byte[])` hoặc `read(byte[], off, len)` trả số **byte** thực nhận, **không** cam kết một lần đọc tương ứng một đoạn do server ghi. Kiểm tra `-1` là EOF. Với buffer có chỗ, khi chưa có dữ liệu, read có thể block.
2. Khi muốn tiêu thụ từng phần, dùng buffer cố định để tránh tạo một mảng cực lớn. Đừng gọi `readAllBytes()`/`transferTo(ByteArrayOutputStream)` vô điều kiện với body không giới hạn.
3. Nếu body chứa UTF-8, một ký tự nhiều byte **có thể nằm vắt giữa hai lần `read`**. Không decode mỗi chunk như một `String` độc lập; dùng decoder có trạng thái hoặc ghép byte đúng frame/dữ liệu trước khi decode.
4. **Luôn có đường cleanup**: đọc tới EOF, hoặc `input.close()` nếu dừng sớm/do lỗi. Đóng sớm có thể khiến underlying HTTP connection bị đóng và không thể reuse.
5. Response code có thể là 4xx/5xx mà body vẫn tồn tại và phải được đọc/đóng; `send` không mặc định ném exception cho mọi HTTP error status.

Đặc biệt, trong Java 17, `ofInputStream` **không chờ tải xong body mới trả response**. Vì vậy code đo chỉ thời gian `send` trả về có thể đo chủ yếu quá trình nhận headers chứ không phải thời gian download trọn nội dung. 

## 4. Khi nào nên đọc byte stream thay vì text?

Chọn `ofInputStream` nếu:

- Response là **binary file** (ảnh, PDF, ZIP, protobuf, payload không phải text). Không dùng `ofLines` để xử lý byte tùy ý, vì charset conversion có thể làm biến đổi thông tin.
- Bạn cần xử lý dữ liệu tuần tự bằng API vốn nhận `InputStream`: parser JSON streaming, decompressor hoặc copy-to-file với kiểm tra checksum.
- Cần dùng **kích thước byte chính xác** để so sánh digest, signature hoặc validate `Content-Length`.
- Muốn tự kiểm soát **giới hạn byte**, chunk size, tốc độ, bộ đệm và thời điểm cancel/close.
- Dữ liệu có thể không có dấu xuống dòng hoặc định dạng dòng; xử lý bằng line abstraction không đem lại lợi ích.

Hãy tránh giữ toàn bộ `InputStream` trong một singleton hoặc chia sẻ nó cho nhiều worker cùng đọc. `HttpResponse<InputStream>.body()` là một nguồn dữ liệu của **exchange cụ thể**, không phải một cache có thể đọc lại. Nếu consumer cần replay nội dung, hãy ghi vào file hoặc buffer có giới hạn theo đúng chính sách rồi mở nguồn mới.

## 5. Tính chính xác và resource cleanup của ofInputStream

Một vòng đọc có giới hạn để chống response body quá lớn:

```java
// Snippet minh họa: input là InputStream; maxBytes là trần an toàn.
long total = 0;
byte[] chunk = new byte[8192];
int n;
while ((n = input.read(chunk)) != -1) {
    total += n;
    if (total > maxBytes) {
        throw new IOException("Response body too large");
    }
    // Xử lý ngay chunk[0..n), KHÔNG giữ cả buffer mutable.
}
```

Để code trên chạy độc lập cần các biến/imports/exception handling bên ngoài. Trong production nên đặt kiểm tra trần **trước khi cấp phát/tích lũy**, tránh phép cộng tràn số và xét cả kích thước sau giải nén nếu ứng dụng giải nén response. Khi điều kiện vượt trần xảy ra, `try-with-resources` phải đóng stream. Không chờ vô hạn cho peer không gửi EOF, đặt timeout/deadline và có phương án cancel thích hợp.

`Content-Length` có thể hỗ trợ quyết định sớm nhưng **không phải chứng chỉ an toàn**: response có thể dùng chunked encoding, HTTP/2 không có header này, hoặc metadata đến từ nguồn không tin cậy. Đặt **actual bytes consumed cap** bên cạnh kiểm tra headers.

**Đọc hết body không bảo đảm kết nối TCP sẽ được reuse**; nó chỉ thỏa yêu cầu cleanup để có cơ hội reuse theo implementation và server policy. Đóng sớm stream có thể đóng connection để không còn dữ liệu body không đọc, nhất là HTTP/1.1. 

## 6. Trường hợp 2 — ofLines(): text được chia thành dòng

Khai báo đúng kiểu:

```java
HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    lines.forEach(line -> processLine(line));
}
```

Đây là **snippet minh họa**, cần định nghĩa `client`, `request`, `processLine` và imports. `ofLines()` tự giải mã body theo charset và trả về `Stream<String>`, với mỗi string là một dòng theo quy tắc `BufferedReader.lines()`. **Không** xử lý nó như `List<String>` đã tải sẵn. Ở lúc `send` trả về, stream có thể vẫn phải chờ byte từ server.

Chọn `ofLines` cho nội dung **thực sự phân định bằng dòng**, chẳng hạn:

- **NDJSON / JSON Lines**: mỗi dòng hoàn chỉnh là một JSON object, parser được gọi cho từng dòng.
- **Log streaming**: server gửi các dòng văn bản, consumer xử lý tuần tự.
- **CSV theo dòng đơn giản** nếu protocol đảm bảo các trường **không chứa newline được quote**. CSV RFC 4180 có multiline field cần parser CSV đầy đủ; `ofLines` đơn thuần không đủ.
- **SSE (Server-Sent Events)**: mỗi dòng là một thành phần của event protocol; cần **parser SSE** để xử lý nhiều dòng `data:`, dòng trống phân cách event, `id`, `retry` và comments. **Không** đồng nhất “mỗi dòng = một SSE event”.

Dòng trống có thể có ý nghĩa đối với giao thức. Không tự lọc mọi `""` nếu chưa hiểu protocol.

## 7. Charset và ranh giới text của ofLines

`BodyHandlers.ofLines()` theo API Java 17 dùng character set từ `Content-Type` header khi xác định được, và dùng UTF-8 khi header không chỉ định charset hỗ trợ. Nó dựa trên bộ giải mã ký tự, vì thế UTF-8 nhiều byte bị chia bởi TCP read/chunking vẫn được xử lý qua trạng thái decoder. 

Ví dụ response text:

```text
Content-Type: text/plain; charset=UTF-8

alpha
Xin chào
omega
```

`Stream<String>` sẽ cung cấp các phần tử theo dòng: `"alpha"`, `"Xin chào"`, `"omega"`. Dấu kết thúc dòng **không phải** một phần của từng `String` trả về. Khác biệt quan trọng: một dòng cuối không có ký tự xuống dòng vẫn có thể được trả như một dòng; không nên giả định mỗi string được kết thúc bằng newline.

Giới hạn cần lưu ý:

- Nếu server khai báo charset sai, hoặc dữ liệu không hợp lệ theo encoding đó, giải mã có thể tạo text không như ý; xác minh **Content-Type/charset** khi có yêu cầu nghiêm ngặt.
- `Stream<String>` là **sequential, consumable stream** cho một exchange. Không gọi lại terminal operation lần hai để “đọc lại” từ đầu.
- `Stream.toList()` cũng sẽ gom mọi dòng vào memory. Nó tiện trong demo nhỏ nhưng **không phải lựa chọn an toàn cho luồng không giới hạn**; production nên xử lý từng dòng và có giới hạn số dòng, chiều dài dòng, tổng bytes, deadline.
- Nếu consumer dừng sớm bằng `limit(10)`, đó **không có nghĩa response đã đến EOF**. Phải `close()` stream trong `try-with-resources`; connection có thể không reuse.
- Với line quá dài không có newline, decoder/line reader có thể giữ bộ nhớ đáng kể **trước khi trả ra một dòng**. Nếu nguồn không tin cậy cần enforce size bằng một parser/decoder byte-oriented có quota, thay vì chỉ dựa trên số dòng đã đọc.

## 8. Cleanup của Stream<String> cũng bắt buộc

Mẫu an toàn:

```java
HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    lines.limit(100).forEach(line -> System.out.println(line));
} // close dù đã dừng sớm.
```

Chỉ là snippet minh họa, chưa có `client`/`request`. Với stream text:

- **Đọc hết dòng** hoặc **đóng stream** để implementation giải phóng resources exchange.
- Nếu `Stream.limit(100)` dừng trong khi server còn gửi, việc đóng sớm **có thể làm HTTP connection không được tái sử dụng**.
- Không trả thẳng `response.body()` lên một API cấp cao mà không quy định ai phải đóng; ví dụ service trả `Stream<String>` cho caller phải ghi rõ **caller owns stream**.
- Không chạy các terminal operations khác nhau đồng thời trên cùng stream. Nó không phải một broadcast publisher và không thể subscribe nhiều lần.
- Khi exception xảy ra trong parser của một dòng, try-with-resources vẫn chạy `close()`. Xử lý cả exception I/O/decoding đúng với layer truyền và business.

Trong Java 17, `HttpResponse.BodySubscribers.ofLines(Charset)` là lớp phía dưới dùng charset được chọn; chỉ cần `BodyHandlers.ofLines()` là cách phổ biến để API tự dựa vào headers. 

## 9. Trường hợp 3 — ofPublisher(): Flow.Publisher<List<ByteBuffer>>

Khai báo đúng kiểu (đừng bỏ `List`):

```java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.send(request, HttpResponse.BodyHandlers.ofPublisher());

Flow.Publisher<List<ByteBuffer>> publisher = response.body();
// Bắt buộc đăng ký đúng một Flow.Subscriber nhận List<ByteBuffer>.
```

Đây là snippet minh họa, cần imports và setup request/client. **Publisher này chỉ cho phép một subscriber**. Lần subscribe thứ hai được báo `onError(IllegalStateException)` theo hợp đồng Java 17. Nếu không subscribe hoặc subscribe nhưng không request/cancel, response body có thể bị treo chưa tiêu thụ và giữ resources. 

Type thực là **`Flow.Publisher<List<ByteBuffer>>`**, không phải `Flow.Publisher<ByteBuffer>` và cũng không phải `Flow.Publisher<byte[]>`. Mỗi `onNext` nhận **một list** gồm một hoặc nhiều `ByteBuffer`; các byte trong list cùng thứ tự với HTTP response body. Số list/buffer và độ dài từng buffer do implementation/quá trình truyền quyết định. Không dùng số lượng `onNext` để đếm số message trong NDJSON hay số HTTP chunks.

## 10. Flow Subscription: request(n) là số batch, không phải byte

`Flow` cung cấp bốn callback cốt lõi:

| Callback | Khi nào | Việc consumer cần làm |
| --- | --- | --- |
| `onSubscribe(subscription)` | Đăng ký được chấp thuận | Lưu `Flow.Subscription`, gọi `request(n)` với `n > 0` khi sẵn sàng |
| `onNext(List<ByteBuffer>)` | Producer gửi một batch theo demand | Xử lý buffer trong list theo thứ tự, cập nhật byte count/state |
| `onError(Throwable)` | Luồng kết thúc vì lỗi | Kết thúc future, cleanup, không chờ `onComplete` |
| `onComplete()` | Toàn body đã được phát xong | Chốt kết quả, giải phóng state, không request thêm |

Một `request(1)` cho phép producer phát **một lần `onNext`** (một `List<ByteBuffer>`), **không** bảo đảm chỉ một byte, một HTTP frame hoặc một dòng text. Nếu muốn điều phối mức tiêu thụ theo byte chính xác, consumer phải đếm byte `remaining()` và dùng hàng đợi/quota riêng.

```text
HTTP body bytes -> Publisher
                     |
                    onSubscribe(s)
                     |
                    s.request(1)
                     |
                    onNext([bufA, bufB])
                     |
                 xử lý hết batch
                     |
                    s.request(1)
                     |
                    onNext([bufC])
                     |
                    ... onComplete hoặc onError
```

Khi consumer không thể tiếp tục, gọi `subscription.cancel()`. Việc cancel sớm có thể khiến HTTP connection bị đóng hoặc HTTP/2 stream bị reset theo tình huống. **Không giả định cancel sẽ “giữ pooling nguyên vẹn”.** 

## 11. ByteBuffer trong onNext: xử lý đúng và an toàn

Java 17 mô tả luồng `List<ByteBuffer>` từ `BodySubscriber` là những **unmodifiable lists chứa read-only ByteBuffers**; không được mutate underlying contents. Consumer có thể đọc qua `get`, `remaining` và tạo `duplicate()` khi cần giữ position của view riêng. 

```java
// Snippet: được gọi từ Flow.Subscriber<List<ByteBuffer>>.onNext.
long bytesInThisBatch = 0;
for (ByteBuffer item : batch) {
    ByteBuffer view = item.duplicate();
    bytesInThisBatch += view.remaining();
    // Đọc view.get(...) với giới hạn để không giữ buffer vô hạn.
}
```

Quan trọng:

- `ByteBuffer.remaining()` tính số **byte còn từ position đến limit**, không phải capacity.
- Một Unicode code point UTF-8 có thể bị chia **giữa hai ByteBuffer**, giữa hai list hoặc giữa các event. **Không tự decode mỗi buffer thành String** rồi nối, vì có thể tạo replacement characters. Dùng `CharsetDecoder` giữ trạng thái qua các batch, hoặc tích lũy **đúng một đơn vị logic có giới hạn** rồi decode.
- Không giả định buffer luôn heap-backed có `array()`; byte buffer có thể read-only/direct và `array()` không được hỗ trợ. Dùng `get(...)` trên duplicate/slice hoặc cơ chế streaming decoder.
- Không lưu giữ vô hạn các `ByteBuffer` nhận vào queue của consumer. Nếu cần xử lý asynchronous sau `onNext`, phải có ownership, bounded capacity và chiến lược khi nào gọi `request` tiếp.
- Một `onNext` là **một delivery batch**, không bảo đảm một request/response body riêng hay packet mạng.

Trong demo nhỏ, callback xử lý hết batch rồi gọi `request(1)`. Ở pipeline production có nhiều stages, chỉ request tiếp khi stage phía sau **có capacity**.

## 12. Ví dụ Java 17+ số 1 — cả ba handler trên một HTTP server loopback

Tệp **`StreamingBodyHandlersDemo.java`** dựng `HttpServer` chuẩn của JDK từ module `jdk.httpserver` trên `127.0.0.1` và port tự cấp. Server trả cùng một body UTF-8 có ba dòng, gồm tiếng Việt đa byte. Một `HttpClient` chung thực hiện ba GET riêng, lần lượt dùng `ofInputStream`, `ofLines` và `ofPublisher`.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
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
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public class StreamingBodyHandlersDemo {
    private static final String CONTENT = "alpha\nXin chào\nomega\n";

    private static final class Collector
            implements Flow.Subscriber<List<ByteBuffer>> {
        private final ByteArrayOutputStream data =
                new ByteArrayOutputStream();
        private final CompletableFuture<byte[]> done =
                new CompletableFuture<>();
        private Flow.Subscription subscription;

        @Override
        public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            s.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> batch) {
            try {
                for (ByteBuffer item : batch) {
                    ByteBuffer copy = item.duplicate();
                    byte[] bytes = new byte[copy.remaining()];
                    copy.get(bytes);
                    data.write(bytes, 0, bytes.length);
                }
                subscription.request(1);
            } catch (RuntimeException ex) {
                subscription.cancel();
                done.completeExceptionally(ex);
            }
        }

        @Override
        public void onError(Throwable error) {
            done.completeExceptionally(error);
        }

        @Override
        public void onComplete() {
            done.complete(data.toByteArray());
        }

        byte[] await() throws Exception {
            return done.get(10, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress local =
                InetAddress.getByAddress(new byte[]{127, 0, 0, 1});
        byte[] payload = CONTENT.getBytes(StandardCharsets.UTF_8);
        AtomicInteger hits = new AtomicInteger();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService serverPool = Executors.newFixedThreadPool(2);
        server.createContext("/data", exchange -> {
            try {
                hits.incrementAndGet();
                exchange.getResponseHeaders().set("Content-Type",
                        "text/plain; charset=UTF-8");
                exchange.sendResponseHeaders(200, payload.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(payload);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(serverPool);
        server.start();

        try {
            URI target = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/data");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(target)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<InputStream> a = client.send(
                    request, HttpResponse.BodyHandlers.ofInputStream());
            ByteArrayOutputStream inputBytes = new ByteArrayOutputStream();
            try (InputStream in = a.body()) {
                byte[] buffer = new byte[5];
                int n;
                while ((n = in.read(buffer)) != -1) {
                    inputBytes.write(buffer, 0, n);
                }
            }
            System.out.println("InputStream matches: "
                    + java.util.Arrays.equals(
                            payload, inputBytes.toByteArray()));

            HttpResponse<Stream<String>> b = client.send(
                    request, HttpResponse.BodyHandlers.ofLines());
            List<String> lines;
            try (Stream<String> stream = b.body()) {
                lines = stream.toList();
            }
            System.out.println("ofLines: " + lines);

            HttpResponse<Flow.Publisher<List<ByteBuffer>>> c =
                    client.send(request,
                            HttpResponse.BodyHandlers.ofPublisher());
            Collector collector = new Collector();
            c.body().subscribe(collector);
            byte[] raw = collector.await();
            System.out.println("Publisher matches: "
                    + java.util.Arrays.equals(payload, raw));
            System.out.println("Requests served: " + hits.get());
        } finally {
            server.stop(0);
            serverPool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 StreamingBodyHandlersDemo.java
java --add-modules jdk.httpserver StreamingBodyHandlersDemo
```

Stdout trên lần chạy thành công:

```text
InputStream matches: true
ofLines: [alpha, Xin chào, omega]
Publisher matches: true
Requests served: 3
```

**Tại sao chương trình có giá trị kiểm chứng?**

1. `HttpServer` trả body cố định, header `Content-Type: text/plain; charset=UTF-8`; `ofLines` đọc đúng ba dòng dù các ký tự Unicode có thể rơi qua nhiều lần đọc.
2. `ofInputStream` đọc bằng buffer **5 byte** (nhỏ hơn nhiều ký tự Unicode nối tiếp) và so sánh **raw bytes** toàn body. Code **không decode từng chunk**, tránh làm hỏng UTF-8.
3. `try (InputStream in = a.body())` đảm bảo đóng stream khi hoàn tất hoặc khi code đọc lỗi.
4. `ofLines` trả `Stream<String>`; chương trình dùng `try (Stream<String> stream = b.body())`. `toList()` chỉ chấp nhận được ở demo vì body rất nhỏ; với stream không giới hạn phải xử lý từng dòng/quota.
5. `ofPublisher` trả `Flow.Publisher<List<ByteBuffer>>`. `Collector` request **một batch** mỗi lần, sao chép các byte từ `duplicate()` rồi request tiếp. `CompletableFuture` được hoàn tất trong `onComplete` hoặc `onError`, và caller đợi có timeout.
6. `Requests served: 3` đếm **ba HTTP requests**, không phải ba TCP connections; code không khẳng định socket reuse chỉ từ con số này.
7. Demo không cần Internet và giới hạn thời gian gửi request. Nó **không** phải HTTP server production, không có authentication, compression policy hay giới hạn memory cho consumer `Collector` (vì payload đã cố định rất nhỏ).

## 13. Ví dụ Java 17+ số 2 — giới hạn body và tính chỉ-được-subscribe-một-lần

Tệp **`StreamingLimitsDemo.java`** minh họa hai ràng buộc thường bị bỏ quên:

- Một HTTP response có body 4.096 byte bị **từ chối** sau khi consumer `ofInputStream` vượt trần 100 byte; `try-with-resources` đóng stream ngay cả khi throw.
- Một publisher `ofPublisher` cho body `PUBLISHER` (9 byte) được subscribe lần đầu, xử lý hết với `request(1)`, và lần subscribe thứ hai được thông báo **`IllegalStateException`** theo hợp đồng API.

```java
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
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;

public class StreamingLimitsDemo {
    private static byte[] readLimited(InputStream input, int max)
            throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[7];
        int total = 0;
        for (int n; (n = input.read(buffer)) != -1;) {
            if (n > max - total) {
                throw new IOException("body limit exceeded");
            }
            output.write(buffer, 0, n);
            total += n;
        }
        return output.toByteArray();
    }

    private static final class CountSubscriber
            implements Flow.Subscriber<List<ByteBuffer>> {
        final CompletableFuture<Long> result = new CompletableFuture<>();
        private Flow.Subscription subscription;
        private long count;

        @Override
        public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            s.request(1);
        }
        @Override
        public void onNext(List<ByteBuffer> batch) {
            for (ByteBuffer buffer : batch) {
                count += buffer.remaining();
            }
            subscription.request(1);
        }
        @Override
        public void onError(Throwable error) {
            result.completeExceptionally(error);
        }
        @Override
        public void onComplete() {
            result.complete(count);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress local =
                InetAddress.getByAddress(new byte[]{127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService serverPool = Executors.newFixedThreadPool(2);
        byte[] large = new byte[4096];
        byte[] small = "PUBLISHER".getBytes(
                java.nio.charset.StandardCharsets.UTF_8);

        server.createContext("/large", exchange -> {
            try {
                exchange.sendResponseHeaders(200, large.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(large);
                }
            } finally {
                exchange.close();
            }
        });
        server.createContext("/small", exchange -> {
            try {
                exchange.sendResponseHeaders(200, small.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(small);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(serverPool);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest largeRequest = HttpRequest.newBuilder(
                    URI.create(base + "/large"))
                    .timeout(Duration.ofSeconds(5)).GET().build();

            HttpResponse<InputStream> response = client.send(
                    largeRequest,
                    HttpResponse.BodyHandlers.ofInputStream());

            boolean rejected = false;
            try (InputStream in = response.body()) {
                readLimited(in, 100);
            } catch (IOException ex) {
                rejected = "body limit exceeded".equals(ex.getMessage());
            }
            System.out.println("Body limit rejected: " + rejected);

            HttpRequest smallRequest = HttpRequest.newBuilder(
                    URI.create(base + "/small"))
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<Flow.Publisher<List<ByteBuffer>>> published =
                    client.send(smallRequest,
                            HttpResponse.BodyHandlers.ofPublisher());

            CountSubscriber first = new CountSubscriber();
            published.body().subscribe(first);
            System.out.println("Publisher bytes: "
                    + first.result.get(10, TimeUnit.SECONDS));

            CompletableFuture<Boolean> secondRejected =
                    new CompletableFuture<>();
            published.body().subscribe(
                    new Flow.Subscriber<List<ByteBuffer>>() {
                        @Override
                        public void onSubscribe(Flow.Subscription s) {
                            s.request(1);
                        }
                        @Override
                        public void onNext(List<ByteBuffer> value) {
                            secondRejected.complete(false);
                        }
                        @Override
                        public void onError(Throwable error) {
                            secondRejected.complete(
                                    error instanceof IllegalStateException);
                        }
                        @Override
                        public void onComplete() {
                            secondRejected.complete(false);
                        }
                    });
            System.out.println("Second subscriber rejected: "
                    + secondRejected.get(10, TimeUnit.SECONDS));
        } finally {
            server.stop(0);
            serverPool.shutdownNow();
        }
    }
}
```

Chạy:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 StreamingLimitsDemo.java
java --add-modules jdk.httpserver StreamingLimitsDemo
```

Stdout kỳ vọng:

```text
Body limit rejected: true
Publisher bytes: 9
Second subscriber rejected: true
```

Giải thích:

1. `readLimited` kiểm tra `n > max - total` **trước khi** cộng và ghi thêm, tránh vượt ngân sách. Khi body lớn hơn trần, ném `IOException`. `try-with-resources` ở caller đảm bảo đóng body stream.
2. Việc close sớm là lựa chọn bảo vệ memory, nhưng có thể **đóng connection** khiến nó không reuse, nhất là HTTP/1.1. Tính đúng đắn và an toàn của ứng dụng **quan trọng hơn cố gắng giữ socket mở bằng cách đọc hết body không đáng tin**.
3. `CountSubscriber` request một batch rồi đếm `remaining()` của các byte buffers trong list, cho tới `onComplete`. Một `Publisher` không có API “đọc lại” như collection.
4. Lần thứ hai gọi `subscribe` vẫn nhận tín hiệu `onSubscribe` rồi `onError(IllegalStateException)` theo quy tắc `ofPublisher`; chương trình ghi `true` khi loại lỗi đúng.
5. Test không thể đo số connection reused, không thể chứng minh flow backpressure đã giới hạn byte memory trong mọi trường hợp. Nó xác minh kiểu dữ liệu và hợp đồng publisher/lifecycle trên JDK 17.

## 14. sendAsync có nghĩa là body đã tải xong chưa?

Không nhất thiết. Với streaming handlers:

```java
CompletableFuture<HttpResponse<InputStream>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofInputStream());

// Response có thể xuất hiện khi body chưa nhận đủ.
HttpResponse<InputStream> response = future.join();
try (InputStream in = response.body()) {
    // Đọc theo lifecycle của riêng mình.
}
```

Đây là snippet minh họa. `sendAsync` trả future chứa `HttpResponse<InputStream>` **khi body object đã sẵn sàng theo handler**, không hứa body đã tiêu thụ hết. Với `ofPublisher`, bạn còn cần **subscribe và đợi terminal event của publisher**; nếu chỉ đợi `sendAsync(...).join()` rồi bỏ publisher, exchange chưa có lý do để tự hoàn tất và giải phóng tài nguyên.

Với `ofLines`, việc future có response trước khi lines đến cũng là điều bình thường. Caller phải quyết định ai giữ stream, ai consume, ai close, và error/deadline phát sinh ở lớp nào. Không trộn “future đã complete” với “business record cuối đã được xử lý”.

## 15. Flow backpressure không thay thế giới hạn kích thước ứng dụng

Flow request/demand giúp consumer điều khiển số batch sẵn sàng nhận, nhưng một batch có thể chứa **nhiều `ByteBuffer` với tổng kích thước khác nhau**. Do đó:

- `request(1)` không phải giới hạn **1 byte** hoặc **1 KiB**.
- Nếu giữ tất cả buffers đã nhận vào một `List` toàn cục, bộ nhớ vẫn có thể tăng theo body.
- Nếu subscribe rồi không request, body có thể chờ vô thời hạn trong khi tài nguyên exchange còn giữ. Cần timeout/cancel.
- Nếu downstream không sẵn sàng, không request thêm cho tới khi có capacity. Kết hợp bounded queue và cơ chế báo tiến triển.
- Callback `onNext` không nên thực hiện I/O/blocking công việc quá chậm làm nghẽn thread delivery; khi chuyển sang worker, phải thiết kế buffer lifetime, copy/slice và ordering phù hợp.

**Flow control ở mức batch không đồng nghĩa backpressure hoàn hảo xuyên mọi buffer/transport layer.** JDK, TLS, HTTP/2 và các queue nội bộ có thể còn buffer data. Cần có trần tổng byte, request timeout/deadline, số request in-flight và chính sách cancel.

## 16. Resource ownership và kết nối reuse: đường nào giải phóng tài nguyên?

| Handler | Đường “happy path” | Dừng sớm / lỗi | Khả năng reuse |
| --- | --- | --- | --- |
| `ofInputStream` | Đọc tới EOF rồi đóng stream | `InputStream.close()` trong `finally`/try-with-resources | Đọc hết tạo điều kiện reuse; close trước EOF có thể buộc đóng connection |
| `ofLines` | Duyệt tới hết các dòng và đóng stream | `Stream.close()` | Dừng sớm có thể ngăn reuse |
| `ofPublisher` | Subscribe **một lần**, request tới `onComplete`/`onError` | `subscription.cancel()` | Cancel trước completion có thể ảnh hưởng reuse |
| `ofString`/`ofByteArray` | Handler đã gom toàn body trước khi trả response | Giới hạn tải/memory ở policy | Có cơ hội reuse nếu exchange hoàn tất; body size là rủi ro |

Với **streaming response**, người tạo `HttpRequest` chưa chắc là người nhận trách nhiệm đóng body. Cần làm rõ contract giữa service và caller. Ví dụ API service trả `Stream<String>` có thể phải yêu cầu caller dùng try-with-resources; nếu service tự đọc hết vào DTO thì service nên tự đóng trước khi trả kết quả.

**Trong Java 17, `HttpClient` không có `close()` public để thay cho việc close body streams**. Dù client reused lâu dài, vẫn phải đóng đúng những body-specific resources. Không đóng `InputStream` của response chỉ vì bạn dùng cùng một `HttpClient` cho nhiều request.

## 17. Kiểm soát status code, Content-Type và ứng dụng đọc streaming

`BodyHandlers.ofInputStream/ofLines/ofPublisher` **không tự loại body** khi response có HTTP 404, 429 hoặc 500. Response vẫn có status/headers và thường có error body. Xây logic:

```text
1. Nhận status + headers qua HttpResponse.
2. Chỉ chấp nhận status/content-type mà protocol ứng dụng hỗ trợ.
3. Nếu status thành công:
     Chọn parser streaming thích hợp, đặt giới hạn/quota.
4. Nếu status lỗi:
     Có thể đọc error body tối đa N byte hoặc bỏ với chính sách rõ.
5. Trong mọi nhánh: drain hoặc close/cancel body.
6. Xử lý metrics/retry theo request semantics, không retry mù side-effect.
```

Nếu cần quyết định **subscriber ngay khi thấy status/headers**, một custom `BodyHandler<T>` có thể kiểm tra `ResponseInfo` rồi chọn `BodySubscribers.discarding()` cho trường hợp không muốn body, hoặc subscriber phù hợp cho trường hợp muốn stream. Tránh tải cả HTML error page khổng lồ chỉ để lấy status.

**Với streaming text**, đừng dựa vào `Content-Type: text/plain` mà chưa kiểm tra charset/body encoding của upstream. Khi server có `Content-Encoding` (gzip/br...), không giả định API `ofLines` sẽ tự đưa ra text đã giải nén theo mọi kiểu: cần kiểm tra HTTP client/proxy/provider và protocol agreement, có thể cần decompressing stage riêng.

## 18. Lưu ý đặc thù NDJSON, SSE và binary streaming

### NDJSON

Mỗi dòng độc lập chứa một JSON value có cấu trúc đã thỏa thuận. `ofLines()` giúp **cung cấp từng dòng**, nhưng việc parse JSON/validate schema, giới hạn line length, kiểm tra charset và logic retry vẫn thuộc ứng dụng. Đừng gom toàn bộ `Stream<String>` bằng `toList()` khi server có thể gửi dữ liệu vô hạn.

### Server-Sent Events

`text/event-stream` có các dòng `data:`, `event:`, `id:`, `retry:` và dòng trống phân cách event. `ofLines()` phù hợp làm nguồn line input, **không phải một parser SSE hoàn chỉnh**. Một event có thể gồm nhiều dòng data; phải ghép theo quy tắc SSE, xử lý reconnect và `Last-Event-ID` nếu dùng đúng giao thức.

### Binary / checksums / codecs

`ofInputStream()` thích hợp làm nguồn cho parser/codec dạng byte. `ofPublisher()` thích hợp khi pipeline tiếp nhận `List<ByteBuffer>` theo Flow; cả hai cần kiểm tra total bytes/hash/signature theo protocol. **Không** biến binary thành dòng Unicode bằng `ofLines()` rồi trông chờ byte output còn nguyên.

### UTF-8 split giữa các lượt đọc

Với `ofInputStream` hoặc `ofPublisher`, boundary của `read`/`onNext` là tùy ý. Chữ `à`, `ộ` và emoji có thể có byte bị tách; giải mã bằng decoder giữ trạng thái qua chunks hoặc theo frame hoàn chỉnh. `ofLines` thực hiện decoding và tách dòng cho trường hợp text.

## 19. Timeout, cancellation và lỗi giữa stream

Các tình huống:

- **`client.send` thành công trả `HttpResponse<InputStream>`** nhưng sau đó `input.read` vẫn có thể block, ném `IOException` hoặc gặp EOF khi đọc body. Bắt lỗi ở **lớp tiêu thụ stream**, không chỉ quanh `send`.
- **`Stream<String>` gặp lỗi I/O trong khi duyệt** có thể báo qua unchecked wrapper như `UncheckedIOException` theo API dòng/stream; cần cleanup và propagate cho nghiệp vụ phù hợp.
- **`ofPublisher` gặp lỗi I/O sau headers** sẽ báo qua `onError(Throwable)`. Consumer phải hoàn tất future/promise của mình trên cả `onComplete` và `onError`, nếu không caller có thể chờ mãi.
- **Không subscribe** vào publisher hoặc **không request** sau `onSubscribe` có thể giữ response bị treo: request positive demand hoặc cancel.
- **Timeout per-request** và **deadline end-to-end** là hai mục tiêu có thể khác nhau, đặc biệt với streaming body kéo dài/không EOF. `HttpRequest.Builder.timeout(...)` không nên bị xem là công cụ tự đủ để kết thúc một stream nghiệp vụ vô hạn đã trả headers.
- **Cancel sau khi server đã xử lý** không hoàn tác side effect. Với POST/payment, đừng dùng cancellation/retry như bằng chứng request chưa chạy.

Một cấu trúc vận hành tốt phải có **cơ chế dừng stream được thiết kế**: HTTP server có thể cung cấp protocol-level end marker; application có deadline, byte cap, line cap, pause/resume hoặc graceful cancel khi user hủy. Khi cancel, giải phóng state và ngừng giữ references tới stream/subscription.

## 20. Hiệu năng và trade-off lựa chọn API

| Mục tiêu | Chọn trước | Vì sao |
| --- | --- | --- |
| JSON nhỏ vài KB, cần DTO ngay | `ofString` hoặc handler byteArray/parser phù hợp | Đơn giản, ít state |
| ZIP/PDF/ảnh lớn | `ofInputStream` hoặc `ofFile` | Bảo tồn byte, có thể stream ra disk/hash |
| Text theo dòng | `ofLines` | Giảm công tự decode + split line |
| NDJSON/stream log | `ofLines` + parser từng dòng + hạn mức | Mỗi record xử lý dần |
| SSE | `ofLines` + state machine SSE | Lines ≠ events |
| Reactive pipeline có downstream Flow | `ofPublisher` | Điều khiển demand bằng `Subscription` |
| Consumer đã làm việc với `InputStream` | `ofInputStream` | Ít chuyển đổi, dễ tích hợp |
| Không cần body | `discarding()` | Không phải mở stream rồi bỏ quên |
| Muốn tải file thẳng vào đường dẫn | `ofFile(path)` | Tránh tự copy tất cả byte về heap |

**Đừng chọn `ofPublisher` chỉ vì nghe “hiệu năng cao”**. Nó đòi hỏi xử lý asynchronous completion, demand, errors, cancellation và potential batching. Nếu business logic đơn giản tiêu thụ một `InputStream`, một giải pháp blocking có giới hạn có thể **dễ kiểm chứng hơn** và đủ tốt.

Ngược lại, nếu đã có Flow/reactive pipeline và nhu cầu backpressure thực tế, `ofPublisher` giúp nối nguồn HTTP vào pipeline đúng mô hình thay vì chặn thread chỉ để chờ `InputStream.read`.

## 21. Lỗi phổ biến cần tránh

1. **Xem `ofInputStream` là cách tải xong rồi mới trả response.** Sai: response có thể sẵn sàng sau headers, body còn đang nhận.
2. **Không close InputStream khi mới đọc vài byte.** Có thể rò exchange resources và làm pool không reuse.
3. **Gọi `readAllBytes()` với body từ Internet không có trần.** Có thể OOM.
4. **Giải mã UTF-8 mỗi lần `read` thành String.** Ký tự đa byte có thể bị chia; dùng decoder giữ trạng thái.
5. **Giữ `Stream<String>` sau khi service trả về mà không mô tả ai close.** Dễ rò resource.
6. **Gọi `toList()` trên dòng vô hạn.** Chuyển streaming về buffer không giới hạn.
7. **Dùng `ofLines` cho binary content.** Charset conversion làm mất thông tin byte.
8. **Nghĩ một dòng SSE = một SSE event.** Event có thể chứa nhiều dòng data; cần parser đúng.
9. **Đăng ký `Flow.Subscriber<ByteBuffer>` thay vì `Subscriber<List<ByteBuffer>>`.** Sai generic type.
10. **Nghĩ `subscription.request(1)` = 1 byte.** Nó là một item `List<ByteBuffer>`, kích thước không cố định.
11. **Không bao giờ request sau `onSubscribe`.** Flow không tiến triển, resource có thể giữ lâu.
12. **Subscribe hai lần vào `ofPublisher()`.** Publisher chỉ cho phép một subscriber; lần sau `onError(IllegalStateException)`.
13. **Bỏ qua `onError` và chỉ đợi `onComplete`.** Future business chờ vô hạn khi HTTP body lỗi.
14. **Lưu mọi ByteBuffer vào một list lớn vô hạn.** Vẫn OOM dù đã dùng reactive API.
15. **Giả định ByteBuffer luôn có mảng `array()`.** Read-only/direct buffers có thể không có.
16. **Gọi `new String(chunk, UTF_8)` từng onNext.** Dễ cắt Unicode và ra ký tự lỗi.
17. **Cho rằng close/cancel sớm vẫn bảo đảm HTTP connection reuse.** Có thể khiến underlying connection đóng.
18. **Cho rằng HTTP status 500 làm body handler tự bỏ qua body.** Không: caller/handler phải định nghĩa policy.
19. **Cho rằng một lần read/onNext là một TCP packet hoặc một HTTP/2 frame.** Boundary delivery không tương ứng như vậy.
20. **Không đặt byte/line/deadline caps.** Streaming không đồng nghĩa tài nguyên không giới hạn sẽ tự được bảo vệ.
21. **Đọc tất cả dữ liệu trong callback onNext làm nghẽn I/O thread và không có downstream capacity.** Phải có xử lý nhẹ, ownership và bounded handoff.
22. **Không phân biệt body completion với business processing completion.** HTTP body nhận hết chưa chứng minh record đã commit.

## 22. Tự kiểm tra kiến thức

**Câu 1.** Phương thức nào phù hợp nhất khi cần truyền byte response vào ZIP decoder? **`ofInputStream()`** hoặc API file/raw byte phù hợp, không `ofLines()`.

**Câu 2.** `HttpResponse<Stream<String>>` đã được trả nhưng chưa iterate stream; có nghĩa body đã tới EOF không? **Không**. Cần consume hoặc close.

**Câu 3.** `Flow.Publisher<List<ByteBuffer>>` gửi một `List` gồm 3 buffers; `request(1)` có cho phép nhận không? **Có**, một item là **một List**, không phải một ByteBuffer hay một byte.

**Câu 4.** Muốn đọc 50 dòng đầu rồi dừng, gọi `lines.limit(50).forEach(...)` là đủ cleanup chưa? **Chưa**. Phải dùng `try-with-resources` để close stream khi dừng sớm.

**Câu 5.** Hai thread muốn độc lập parse response body do `ofPublisher` tạo, có thể subscribe cả hai vào cùng publisher không? **Không**. Publisher này chỉ cho phép một subscriber. Nếu cần multicast, xây stage riêng có ownership/backpressure và copies phù hợp.

**Câu 6.** Đóng `InputStream` sau khi chỉ đọc 1/100 body, có chắc connection được reuse không? **Không**; có thể bị đóng và không dùng cho exchange sau.

**Câu 7.** Body đến qua hai ByteBuffers, byte đầu của một ký tự UTF-8 ở buffer A, byte còn lại ở buffer B. Có nên tạo String cho A và B độc lập rồi nối không? **Không**; dùng decoder có trạng thái.

**Câu 8.** `ofPublisher()` trả `HttpResponse` sau headers, có thể bỏ object publisher mà không đăng ký không? **Không nên**. Cần subscribe/request tới terminal event hoặc cancel theo hợp đồng để giải phóng resources.

**Câu 9.** `BodyHandlers.ofLines()` có phải một SSE parser hoàn chỉnh? **Không**. Nó chỉ tách text thành dòng; SSE event framing còn có các quy tắc khác.

**Câu 10.** Nếu response status 404 mà body handler là `ofInputStream()`, có đọc được error body không? **Có**, trừ khi application custom handler quyết định khác; vẫn phải close body.

## 23. Checklist áp dụng trong ứng dụng Java 17

1. **Đang xử lý raw byte, text theo dòng hay Flow pipeline?** Chọn `ofInputStream`, `ofLines` hoặc `ofPublisher` tương ứng.
2. **Đã ghi đúng generic type chưa?** `InputStream`, `Stream<String>`, `Flow.Publisher<List<ByteBuffer>>`.
3. **Ai chịu trách nhiệm đóng/cancel?** Với InputStream/Stream dùng try-with-resources; với publisher subscribe một lần, request tới terminal hoặc cancel.
4. **Có body cap/line cap/deadline không?** Không để Internet body dẫn đến OOM hoặc stream kéo dài vô hạn.
5. **Đã xác thực Content-Type, charset và status chưa?** Không tự parse HTML error thành NDJSON, không đọc binary như text.
6. **Có xử lý ranh giới UTF-8 đúng không?** Không decode buffer chunks độc lập.
7. **Flow demand đã được tính đúng theo item List<ByteBuffer> chưa?** Một `request(1)` không phải 1 byte.
8. **Có xử lý onError/onComplete/cancel và hoàn tất future riêng chưa?** Không để business chờ mãi.
9. **Có bỏ giữ resources sau early stop không?** Đóng stream/cancel, chấp nhận trade-off connection reuse nếu cần để an toàn.
10. **Có phân biệt response headers ready với body processing finished không?** Thời gian, metrics và retry policy dựa trên đúng mốc.
11. **Có chia sẻ HttpClient hợp lý và không gộp dữ liệu nhiều tenant sai scope không?** Connection pooling là tối ưu có điều kiện; stream lifecycle vẫn ở cấp từng exchange.
12. **Đã test với body lớn, chunk nhỏ, multibyte Unicode split, invalid charset, slow source, early cancel và second subscribe chưa?** Đặc biệt chú ý lỗi không xuất hiện với response nhỏ trên loopback.

**Kết luận:** `ofInputStream()` cho **byte-oriented pull streaming**, `ofLines()` cho **text-oriented line streaming**, còn `ofPublisher()` cho **Flow-oriented push với demand và một subscriber duy nhất**. Cả ba cho phép xử lý dần body sau khi headers sẵn sàng. Lựa chọn nào cũng yêu cầu **tiêu thụ hết hoặc đóng/cancel đúng cách**, giữ giới hạn tài nguyên và xử lý lỗi sau khi `HttpResponse` đã được trả về. Đó là điều kiện để một ứng dụng HTTP lớn vừa đúng dữ liệu vừa không làm mất khả năng tận dụng kết nối.

### Tài liệu API Java 17

- [HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [HttpResponse.BodySubscribers — ofInputStream, ofLines, ofPublisher](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
- [HttpResponse.BodySubscriber và Flow<List<ByteBuffer>>](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html)
- [HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html)
- [java.util.concurrent.Flow](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html)
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [jdk.httpserver.HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html).