# Hoàn thành future khi body dạng luồng còn mở và trách nhiệm của bên sử dụng

**Chủ đề:** Java Advance - networking  
**Nhóm:** HTTP bất đồng bộ  
**API trọng tâm:** Java 17+, **java.net.http.HttpClient.sendAsync(...)**, **HttpResponse.BodyHandlers.ofInputStream()**, **ofLines()**, **ofPublisher()**, **CompletableFuture**, **InputStream**, **Stream<String>**, **Flow.Publisher<List<ByteBuffer>>**.

Khi dùng Java HTTP client bất đồng bộ, một lập trình viên dễ suy ra:

> **sendAsync hoàn thành thành công nghĩa là HTTP response đã được đọc hết và mọi tài nguyên mạng đã được trả lại.**

Suy luận ấy **sai với response body dạng luồng**. **CompletableFuture<HttpResponse<InputStream>>** có thể hoàn thành ngay sau khi headers đã được nhận và một **InputStream** đã sẵn sàng cho caller. Trong khi đó server vẫn đang gửi phần sau của body, network connection vẫn đang vận chuyển byte và tài nguyên liên quan vẫn có thể đang được giữ. Với **ofLines()** hay **ofPublisher()**, cách tách biệt thời điểm nhận response object và thời điểm tiêu thụ hết body cũng tương tự.

**Nguyên tắc cốt lõi:** **future hoàn thành chỉ có nghĩa giá trị HttpResponse<T> theo BodyHandler đã sẵn sàng; nó không tự chứng nhận rằng body dạng streaming đã được đọc hết, đóng hoặc hủy.** Người nhận **T** chịu trách nhiệm thực hiện nốt vòng đời tiêu thụ/hủy body. Nếu bỏ quên bước đó, có thể giữ tài nguyên I/O, khiến kết nối không được tái sử dụng, tạo backpressure treo hoặc làm việc shutdown HttpClient không hoàn tất như mong muốn.

Bài này làm rõ thời điểm hoàn thành future, trách nhiệm sở hữu stream, cancellation, lỗi sau khi future đã completed, backpressure, các mẫu sử dụng an toàn, và ví dụ **Java 17** có server trên loopback cố ý giữ body chưa kết thúc để kiểm tra chính xác.

## 1. Phân tách hai thời điểm: response sẵn sàng và body đã kết thúc

Xem diễn biến HTTP response với một body dài:

~~~text
Client                                  Server
  |                                       |
  | ------------ HTTP request ---------> |
  |                                       |
  | <----- HTTP status + headers -------- |
  |           (status = 200)              |
  |                                       |
  |  CompletableFuture<HttpResponse<
  |      InputStream>> có thể completed
  |              │                        |
  |              ▼                        |
  |    response.body(): InputStream       |
  |                                       |
  | <---------- body chunk A ------------ |
  |    read() có thể trả byte của A       |
  |                                       |
  |        server vẫn đang tạo dữ liệu    |
  |             (chờ / chậm)              |
  |                                       |
  | <---------- body chunk B ------------ |
  |                                       |
  | <-------- end of response body -------|
  |                                       |
  |    read đến EOF / close stream        |
  |    => giải phóng tài nguyên liên quan |
~~~

Giả sử một server trả **status 200** và header **Transfer-Encoding: chunked** cho HTTP/1.1, rồi giữ connection mở trong lúc tạo các chunk. Java có thể trả **HttpResponse<InputStream>** sau headers mà không cần đợi chunk cuối. Caller đọc **InputStream** khi data tới; nếu không đọc hoặc không đóng, việc xử lý response ở tầng body **vẫn chưa hoàn tất**.

Phân biệt ba mốc:

| Mốc | Cái gì đã có? | Cái gì chưa được bảo đảm? |
| --- | --- | --- |
| **Future mới được tạo** | CompletableFuture đại diện cho việc gửi/nhận response | Headers, status, body có thể chưa có |
| **Future complete thành công** | HttpResponse<T> đã sẵn sàng theo BodyHandler; có status/headers/body object | Với streaming **T**, toàn bộ body chưa chắc được đọc/đóng |
| **Body được drain đến EOF, hoàn thành hoặc hủy/close** | Consumer đã kết thúc trách nhiệm nhận body theo contract | Không có bảo đảm kết nối cụ thể chắc chắn được reuse; phụ thuộc protocol và state |

Đừng nhầm **future.isDone()** với **inputStream.available()**, **đã thấy EOF**, **body.close()** hay **đã giải phóng socket**. **available()** không cho biết tổng kích thước body còn lại; nó chỉ phản ánh số byte ước lượng có thể đọc mà không block theo contract InputStream.

## 2. Cơ chế Java: BodyHandler, BodySubscriber và getBody()

Ở tầng Java HTTP client, caller đưa **BodyHandler<T>** để quyết định body sẽ được biểu diễn dưới dạng gì. Client nhận status/headers, tạo **BodySubscriber<T>**, chuyển dữ liệu nhận được vào subscriber, và hoàn thành future khi body object **T** có sẵn theo semantics của subscriber.

**HttpResponse.BodySubscriber<T>.getBody()** trả **CompletionStage<T>**. Thời điểm stage này complete tùy loại **T**:

- Với **String**, **byte[]**, hoặc dữ liệu cần thu đủ trước khi tạo giá trị cuối, stage thường complete **sau khi toàn bộ body đã xử lý**.
- Với **InputStream**, stage có thể complete **trước khi byte của body được đọc hết**, vì caller cần InputStream để đọc tiếp.
- Với **Stream<String>** hoặc **Flow.Publisher<List<ByteBuffer>>**, stage cũng có thể sẵn sàng sớm để caller chủ động tiêu thụ từng phần.

Đây là khác biệt **về contract**, không phải lỗi timing hoặc bug của CompletableFuture. Với streaming, chính **body object** là đầu vào của pha xử lý tiếp theo. Phần còn lại không tự xảy ra chỉ vì caller đã nhận HttpResponse.

### So sánh BodyHandlers thường gặp

| BodyHandler | Kiểu body T | Future/HttpResponse có thể sẵn sàng khi nào? | Người dùng cần làm gì? |
| --- | --- | --- | --- |
| **ofString()** | String | Khi body đã được tích lũy/giải mã hoàn chỉnh | Xử lý String; cân nhắc memory với body lớn |
| **ofByteArray()** | byte[] | Khi body đã được tích lũy hoàn chỉnh | Xử lý byte[]; giới hạn kích thước để tránh OOM |
| **ofFile(path)** | Path | Sau khi response body đã được ghi vào file theo handler | Xử lý Path; dọn file theo application lifecycle |
| **discarding()** | Void | Sau khi subscriber đã nhận/bỏ nội dung theo semantics | Không cần đọc thủ công InputStream |
| **ofInputStream()** | InputStream | Sớm, sau headers; body có thể chưa nhận đủ | **Đọc đến EOF hoặc close** |
| **ofLines()** | Stream<String> | Sớm, sau headers; dòng có thể chưa tới hết | **Duyệt đến hết hoặc close Stream** |
| **ofPublisher()** | Flow.Publisher<List<ByteBuffer>> | Sớm, sau headers; byte còn đang truyền | **Subscribe một lần, request đến terminal signal hoặc cancel** |

**ofFile** vẫn là cách xử lý body theo dòng trong implementation, nhưng **future<Path>** đại diện file đã được xử lý xong, khác việc caller tự nhận InputStream và đọc từng chunk sau khi future hoàn thành.

**Không dùng ofString() cho mọi response lớn** nếu không biết kích thước: nó có thể cần giữ toàn bộ nội dung trong RAM. Ngược lại, **ofInputStream()** giảm nhu cầu giữ cả body nhưng chuyển trách nhiệm lifecycle từ HTTP client sang consumer.

## 3. ofInputStream(): future hoàn thành sớm, stream vẫn mở

Ví dụ:

~~~java
// Snippet: client và request đã tồn tại.
CompletableFuture<HttpResponse<InputStream>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

future.thenAccept(response -> {
    InputStream stream = response.body();
    // Lúc này status và headers đã có.
    // stream có thể CHƯA được đọc hết.
});
~~~

Đoạn trên **chưa an toàn** vì không đọc/đóng stream. Nó minh họa đúng hiện tượng nhưng không giải phóng resource. Một đoạn consumer hoàn chỉnh phải đảm bảo **read-to-EOF hoặc close** ngay cả khi parse/ghi file/thao tác nghiệp vụ thất bại.

**Javadoc Java 17** nêu rõ: **ofInputStream** có thể trả HttpResponse sau khi headers được đọc, không chờ entire body; caller phải **đọc hết tới EOF** hoặc **gọi InputStream.close()** nếu không muốn tiếp tục. Việc đóng sớm có thể khiến HTTP connection bị đóng và không được dùng lại.

### Mẫu an toàn: try-with-resources

~~~java
// Snippet nằm trong nơi có HttpResponse<InputStream> response.
try (InputStream in = response.body()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = in.read(buffer)) != -1) {
        processBytes(buffer, 0, n);
    }
}
~~~

**processBytes(...)** là method ứng dụng phải tự định nghĩa; đoạn này chỉ minh họa resource ownership, không phải chương trình độc lập. **try-with-resources** bảo đảm **close()** được gọi cả khi processBytes ném exception. Nếu đã đọc đến EOF thì close vẫn là cách diễn đạt rõ ràng rằng scope sở hữu stream đã kết thúc.

**Không gọi** stream.close() ngay khi vừa có HttpResponse nếu consumer vẫn cần đọc dữ liệu sau đó. Bên nhận phải quy định rõ ai sở hữu stream, lúc nào body cần còn mở và cách truyền quyền sở hữu.

### Read tới EOF hay close sớm?

Hai cách cùng **giúp hoàn tất trách nhiệm tài nguyên**, nhưng có trade-off:

- **Đọc đến EOF**: thường cho phép HTTP client xử lý hoàn chỉnh response body và tạo điều kiện để tái sử dụng connection; còn phải tuân thủ protocol và mọi state của connection.
- **Close sớm** khi không cần dữ liệu: giải phóng trách nhiệm của consumer; tùy HTTP/1.1, HTTP/2 và provider, việc đóng/hủy có thể khiến connection bị đóng, stream bị reset hoặc không thể reuse.
- **Không làm gì**: nguy hiểm nhất. Body vẫn chưa tiêu thụ/hủy; request có thể bị kẹt, connection/pool slots bị giữ và shutdown có thể không kết thúc.

Không viết **readAllBytes()** vô điều kiện để “dọn stream” khi response có thể rất lớn hoặc stream vô hạn: cách đó có thể tốn RAM và treo lâu. Dùng buffer có giới hạn, hạn mức byte/thời gian, giải nén an toàn và hủy nếu không còn cần.

## 4. ofLines(): Stream<String> cũng là tài nguyên cần đóng

**HttpResponse.BodyHandlers.ofLines()** trả body kiểu **Stream<String>**. Đây không phải java.util.stream.Stream thông thường chỉ đọc từ một collection đã có sẵn: nó **được hậu thuẫn bởi response body đang truyền**, nên việc duyệt stream có thể chờ byte mới trên mạng.

~~~java
// Snippet: client và request đã tồn tại.
CompletableFuture<HttpResponse<Stream<String>>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofLines());

future.thenAccept(response -> {
    try (Stream<String> lines = response.body()) {
        lines.forEach(line -> {
            System.out.println(line);
        });
    }
});
~~~

**try-with-resources** trên Stream là thiết yếu. Nếu gọi **limit(10)** để chỉ xem 10 dòng, terminal operation **không đọc hết body**; sau 10 dòng, bắt buộc close Stream. Nếu stream lỗi khi đang duyệt, close vẫn phải chạy.

~~~java
// Sai: lấy 3 dòng rồi quên đóng Stream.
response.body().limit(3).forEach(System.out::println);
// Response vẫn có thể còn vô số dòng chưa nhận.
~~~

**Đúng:**

~~~java
try (Stream<String> lines = response.body()) {
    lines.limit(3).forEach(System.out::println);
} // close dù mới lấy ba dòng.
~~~

**Encoding:** ofLines() xác định charset theo thông tin Content-Type như trong Javadoc, và các dòng tương ứng semantics của BufferedReader. Một dòng text dài bất thường có thể làm tăng memory sử dụng; cần giới hạn độ dài và tổng số dòng với dữ liệu không tin cậy. **onClose ở Stream** không được dùng thay hợp đồng đóng của body; hãy gọi **Stream.close()** bằng try-with-resources.

## 5. ofPublisher(): một lần subscribe, request hoặc cancel

**HttpResponse.BodyHandlers.ofPublisher()** trả:

~~~java
Flow.Publisher<List<ByteBuffer>>
~~~

Future có thể complete ngay khi headers đã có, nhưng **byte của body được giao khi subscriber đăng ký và request dữ liệu**. Caller sở hữu nghĩa vụ **subscribe đúng một lần** và quản lý lifecycle của **Flow.Subscription**.

Quy tắc quan trọng từ **BodySubscribers.ofPublisher()**:

1. Publisher trả về từ response **chỉ cho phép một subscriber**. Lần subscribe sau sẽ nhận một subscription rỗng và tín hiệu **onError(IllegalStateException)**.
2. Subscriber phải giữ **Flow.Subscription** khi **onSubscribe(subscription)** được gọi.
3. Gọi **subscription.request(n)** với **n > 0** để có demand. Không request dữ liệu có thể làm nguồn bị ngưng vì backpressure.
4. Khi **onNext(List<ByteBuffer>)**, xử lý các buffers theo order. Không giả định một callback tương ứng một HTTP packet, một message hoặc một buffer duy nhất.
5. Nếu muốn nhận toàn bộ body, tiếp tục request tới khi nhận **onComplete** hoặc **onError**.
6. Nếu bỏ dở, gọi **subscription.cancel()**. Chỉ bỏ reference Publisher hay để subscriber không request tiếp **không** thay thế cancellation.

~~~text
HttpResponse<Publisher> được trả
        |
        v
subscribe(new Flow.Subscriber<>())
        |
        v
onSubscribe(subscription)
        |
        +-- request(1) --> onNext(List<ByteBuffer>)
        |                      |
        |                      +-- process + request(1) --> ...
        |
        +-- khi không muốn nhận nữa --> cancel()
        |
        +-- khi hết body --> onComplete()
        |
        +-- khi lỗi --> onError(Throwable)
~~~

**Không có Publisher.close() chuẩn** trên Flow.Publisher. Cơ chế giải phóng quyền nhận là **subscription.cancel()**; khi nhận đến hết thì **onComplete** hoặc **onError** là terminal signal.

### Ví dụ subscriber tối thiểu theo demand

~~~java
// Snippet: publisher có kiểu Flow.Publisher<List<ByteBuffer>>.
publisher.subscribe(new Flow.Subscriber<List<ByteBuffer>>() {
    private Flow.Subscription subscription;
    private long bytes;

    @Override
    public void onSubscribe(Flow.Subscription s) {
        subscription = s;
        s.request(1);
    }

    @Override
    public void onNext(List<ByteBuffer> buffers) {
        for (ByteBuffer buffer : buffers) {
            bytes += buffer.remaining();
            // Cần thực sự xử lý hoặc copy dữ liệu trước khi request thêm.
            buffer.position(buffer.limit());
        }
        subscription.request(1);
    }

    @Override
    public void onError(Throwable error) {
        System.err.println("Body failed: " + error);
    }

    @Override
    public void onComplete() {
        System.out.println("Body finished, bytes=" + bytes);
    }
});
~~~

Đây là **snippet**; biến **publisher** và import **java.util.concurrent.Flow**, **java.nio.ByteBuffer**, **java.util.List** phải tồn tại ở scope. Đoạn trên dùng **position(limit)** chỉ để thể hiện đã tiêu thụ mà không giữ nội dung; ứng dụng thực cần copy/chuyển dữ liệu theo protocol, xử lý backpressure và giới hạn độ lớn. Với một subscriber có thể stop sớm, thêm nhánh gọi **subscription.cancel()** thay vì tiếp tục request.

**Đừng xử lý việc chậm vô hạn ngay trong onNext** nếu callback của implementation dùng event/client thread. Với pipeline lớn, đưa dữ liệu sang bounded queue/worker có backpressure, và bảo đảm không request thêm vô hạn khi worker chưa tiêu thụ xong.

## 6. Thành công của future không phải hoàn tất của consumer

Xem ba future có cùng một URL nhưng khác BodyHandler:

~~~java
CompletableFuture<HttpResponse<String>> a =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

CompletableFuture<HttpResponse<InputStream>> b =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

CompletableFuture<HttpResponse<Flow.Publisher<List<ByteBuffer>>>> c =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofPublisher());
~~~

**a** thường hoàn thành khi string body đã tích lũy xong; **b** và **c** có thể hoàn thành sau headers trong khi body vẫn tiếp tục. Đây là ba request độc lập trong snippet, không phải ba cách “nhìn cùng một response” miễn phí.

**Lỗi tư duy:**

~~~text
Future completed successfully
    -> status HTTP = 200
    -> đánh dấu job hoàn thành
    -> bỏ quên InputStream
    -> network body còn mở / transport resources còn được giữ
~~~

**Thiết kế đúng có hai stage/ownership khác nhau:**

~~~text
Stage A: acquire response (headers + streaming body handle)
    -> CompletableFuture<HttpResponse<InputStream>>

Stage B: consume or close body
    -> CompletableFuture<Result> riêng do application quản lý
    -> hoàn thành khi đọc/parse/ghi/xác minh xong,
       hoặc thất bại/hủy và đã cleanup
~~~

Đối với một API mà caller chỉ cần nội dung hoàn chỉnh, trả về **CompletableFuture<Result>** đã bao gồm pha B thay vì trao InputStream ra bên ngoài không có ownership rõ ràng. Ngược lại, nếu API là streaming API, trả **body handle** và yêu cầu consumer phải close/cancel theo contract.

### Sau khi future thành công, read vẫn có thể lỗi

Một server có thể gửi status 200 + headers, khiến future ofInputStream complete, rồi đóng TCP đột ngột giữa body. Khi **in.read(...)** chạy sau đó, caller có thể nhận **IOException**, EOF/truncated body hoặc lỗi decoding theo protocol. **CompletableFuture<HttpResponse<InputStream>> đã complete thành công trước đó sẽ không tự chuyển ngược sang exceptional** vì read sau này thất bại.

Tương tự:

- **Stream<String>** có thể thất bại trong lúc duyệt/giải mã.
- **Flow.Publisher** có thể phát **onError** sau khi outer future đã completed.
- Lỗi parse JSON/application protocol có thể phát sinh khi consumer xử lý byte cuối; đó là **consumer-stage error**, không được bỏ đi vì outer future thành công.

Hãy ghi lại **status/header stage** và **body-consumption stage** riêng khi cần quan sát chính xác.

## 7. Chương trình Java 17+ hoàn chỉnh: chứng minh future done nhưng body chưa hết

Demo này sử dụng **HttpServer** trên **127.0.0.1** và **java.net.http.HttpClient**. Server có endpoint **/held** với response body được chia thành hai phần:

1. Server gửi headers + chunk đầu **alpha** rồi flush.
2. Server **chờ CountDownLatch** không gửi chunk cuối.
3. Client **sendAsync(... ofInputStream())** lấy được HttpResponse trong lúc server đang chờ.
4. Client in **futureDoneBeforeBodyEOF=true** và **serverBodyEndedBeforeRelease=false** để chứng minh hai lifecycle độc lập.
5. Client đọc chunk đầu, mở latch cho server gửi **omega**, rồi đọc tới EOF và đóng InputStream.
6. Demo kiểm tra thêm **ofLines()**, **ofPublisher()** với demand, và **ofString()**.

Việc dùng CountDownLatch giúp xác nhận **có chủ đích** future completed trước khi body được hoàn tất; không dựa vào sleep hoặc một race khó tái tạo. Dùng cổng 0 để hệ điều hành cấp port thực, không đòi hỏi Internet.

### Mã nguồn: AsyncBodyOwnershipDemo.java

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
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;

public class AsyncBodyOwnershipDemo {
    private static final CountDownLatch allowLastChunk = new CountDownLatch(1);
    private static final CountDownLatch serverBodyEnded = new CountDownLatch(1);

    private static void heldBody(HttpExchange exchange) throws IOException {
        try (exchange) {
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, 0);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write("alpha\n".getBytes(StandardCharsets.UTF_8));
                out.flush();
                try {
                    if (!allowLastChunk.await(5, TimeUnit.SECONDS)) {
                        throw new IOException("Consumer did not release the last chunk");
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IOException("Server interrupted", e);
                }
                out.write("omega\n".getBytes(StandardCharsets.UTF_8));
                out.flush();
            }
        } finally {
            serverBodyEnded.countDown();
        }
    }

    private static void fixedBody(HttpExchange exchange, String content)
            throws IOException {
        try (exchange) {
            byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/held", AsyncBodyOwnershipDemo::heldBody);
        server.createContext("/lines", e -> fixedBody(e, "one\ntwo\n"));
        server.createContext("/publisher", e -> fixedBody(e, "DATA"));
        server.createContext("/string", e -> fixedBody(e, "DONE"));
        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newHttpClient();

            HttpRequest heldRequest = HttpRequest.newBuilder(
                    base.resolve("held"))
                    .timeout(Duration.ofSeconds(8)).GET().build();
            CompletableFuture<HttpResponse<InputStream>> firstFuture =
                    client.sendAsync(heldRequest,
                            HttpResponse.BodyHandlers.ofInputStream());
            HttpResponse<InputStream> first =
                    firstFuture.get(5, TimeUnit.SECONDS);

            System.out.println("status=" + first.statusCode());
            System.out.println("futureDoneBeforeBodyEOF=" +
                    firstFuture.isDone());
            System.out.println("serverBodyEndedBeforeRelease=" +
                    (serverBodyEnded.getCount() == 0));

            try (InputStream stream = first.body()) {
                byte[] prefix = stream.readNBytes(6);
                System.out.println("first=" +
                        new String(prefix, StandardCharsets.UTF_8).trim());

                allowLastChunk.countDown();
                byte[] suffix = stream.readAllBytes();
                System.out.println("remaining=" +
                        new String(suffix, StandardCharsets.UTF_8).trim());
            } finally {
                allowLastChunk.countDown();
            }

            if (!serverBodyEnded.await(5, TimeUnit.SECONDS)) {
                throw new IOException("Server stream did not close");
            }
            System.out.println("serverBodyEndedAfterRead=true");

            HttpRequest linesRequest = HttpRequest.newBuilder(
                    base.resolve("lines")).GET().build();
            HttpResponse<Stream<String>> linesResponse = client.sendAsync(
                    linesRequest, HttpResponse.BodyHandlers.ofLines()).join();
            try (Stream<String> lines = linesResponse.body()) {
                System.out.println("lines=" +
                        String.join("|", lines.toList()));
            }

            HttpRequest pubRequest = HttpRequest.newBuilder(
                    base.resolve("publisher")).GET().build();
            HttpResponse<Flow.Publisher<List<ByteBuffer>>> pubResponse =
                    client.sendAsync(pubRequest,
                            HttpResponse.BodyHandlers.ofPublisher()).join();
            CompletableFuture<String> consumed = new CompletableFuture<>();
            ByteArrayOutputStream collected = new ByteArrayOutputStream();

            pubResponse.body().subscribe(new Flow.Subscriber<>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    s.request(1);
                }

                @Override
                public void onNext(List<ByteBuffer> buffers) {
                    for (ByteBuffer buffer : buffers) {
                        byte[] bytes = new byte[buffer.remaining()];
                        buffer.get(bytes);
                        collected.writeBytes(bytes);
                    }
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    consumed.completeExceptionally(error);
                }

                @Override
                public void onComplete() {
                    consumed.complete(
                            collected.toString(StandardCharsets.UTF_8));
                }
            });
            System.out.println("publisherBody=" +
                    consumed.get(5, TimeUnit.SECONDS));

            HttpResponse<String> textResponse = client.sendAsync(
                    HttpRequest.newBuilder(base.resolve("string"))
                            .GET().build(),
                    HttpResponse.BodyHandlers.ofString()).join();
            System.out.println("stringBody=" + textResponse.body());
        } finally {
            allowLastChunk.countDown();
            server.stop(0);
        }
    }
}
~~~

### Biên dịch và chạy

Yêu cầu **JDK 17+**, có module tiêu chuẩn **jdk.httpserver**. Tạo file **AsyncBodyOwnershipDemo.java** với nội dung đúng ở trên, trong một thư mục tạm để thực hành:

~~~bash
javac --release 17 -encoding UTF-8 AsyncBodyOwnershipDemo.java
java AsyncBodyOwnershipDemo
~~~

**Stdout xác minh từ lần biên dịch --release 17 và chạy thực tế trên JDK 24:**

~~~text
status=200
futureDoneBeforeBodyEOF=true
serverBodyEndedBeforeRelease=false
first=alpha
remaining=omega
serverBodyEndedAfterRead=true
lines=one|two
publisherBody=DATA
stringBody=DONE
~~~

### Giải thích bằng chứng của demo

- **status=200**: headers được client đọc và HttpResponse đã sẵn sàng.
- **futureDoneBeforeBodyEOF=true**: future cung cấp response đã completed.
- **serverBodyEndedBeforeRelease=false**: server chưa kết thúc body; nó đang chờ latch của client. Vì latch chưa mở, không thể ngộ nhận body đã hoàn tất trong khi chỉ nhìn status.
- **first=alpha**: client đọc được phần dữ liệu đầu từ InputStream trong lúc luồng còn đang mở.
- **remaining=omega**: sau khi mở latch, client nhận phần còn lại, đọc đến EOF và đóng stream.
- **serverBodyEndedAfterRead=true**: server đã đóng body theo quy trình demo.
- **lines=one|two**: Stream<String> đã được duyệt đến hết trong try-with-resources.
- **publisherBody=DATA**: subscriber đã subscribe, request từng đợt, nhận onNext và onComplete.
- **stringBody=DONE**: đối chiếu với BodyHandlers.ofString() trả một String hoàn chỉnh.

Demo **không** khẳng định mọi body dạng streaming luôn còn byte khi future complete: body cực ngắn có thể đã hoàn tất vào thời điểm ấy. Điều quan trọng là **Java API cho phép future complete trước khi body kết thúc**; chương trình có latch để chứng minh bằng một tình huống xác định.

**Vì sao HttpClient không nằm trong try-with-resources?** API HttpClient tại Java 17 **chưa** kế thừa AutoCloseable; các API đóng HttpClient (close/shutdown/awaitTermination) được bổ sung từ **Java 21**. Mã biên dịch với --release 17 phải giữ compatibility; production Java 21+ có thể sử dụng client.close() khi app shutdown, nhưng **đóng client không thay thế trách nhiệm giải phóng body streaming**.

**Cẩn trọng:** Trong demo, **readAllBytes()** an toàn vì server chỉ gửi một chunk nhỏ cuối cùng. Không copy cách này cho download/stream dài hoặc không giới hạn.

## 8. Thiết kế asynchronous pipeline có trách nhiệm: stage đọc body riêng

Một mẫu thường gặp nhưng sai:

~~~java
CompletableFuture<Void> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream())
                .thenAccept(response -> {
                    System.out.println("status=" + response.statusCode());
                    // BỎ QUÊN response.body(): chưa đọc, chưa đóng.
                });
~~~

**thenAccept** kết thúc nhưng network resources có thể vẫn đang giữ. Một biến CompletableFuture<Void> do thenAccept tạo cũng complete, không làm stream tự cleanup.

### Mẫu đúng: xử lý body trong một stage có ownership

~~~java
// Snippet: client/request/ioExecutor đã được tạo.
// ioExecutor nên là một ExecutorService có giới hạn thread/queue.
CompletableFuture<Long> consumed =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofInputStream())
        .thenApplyAsync(response -> {
            try (InputStream in = response.body()) {
                long total = 0;
                byte[] buffer = new byte[8192];
                int n;
                while ((n = in.read(buffer)) != -1) {
                    total += n;
                    if (total > 10_000_000L) {
                        throw new IOException("Response exceeds size limit");
                    }
                    // Xử lý chunk tại đây, không giữ toàn bộ body trong RAM.
                }
                return total;
            } catch (IOException e) {
                throw new java.io.UncheckedIOException(e);
            }
        }, ioExecutor);
~~~

Đây là **snippet không chạy độc lập**: cần import, biến **ioExecutor**, **client**, **request** và chính sách giới hạn tài nguyên của ứng dụng. Nó cho thấy:

1. **Outer future** hoàn thành khi response/InputStream sẵn sàng.
2. **thenApplyAsync** chuyển việc **blocking read** sang executor do ứng dụng quản lý, không ép callback mạng làm việc nặng.
3. **try-with-resources** bảo đảm stream close dù parse/IO thất bại.
4. **consumed** đại diện kết quả **đã đọc xong body hoặc đã cleanup sau lỗi**, chứ không chỉ nhận headers.
5. **UncheckedIOException** giữ cause đọc body để caller phân loại; cần xử lý **CompletionException** khi join.

**Quan trọng:** **thenApplyAsync** không phải cơ chế tự động kiểm soát backpressure. Nếu executor có hàng đợi vô hạn và nhiều response stream chờ đọc, bạn vẫn có thể hết tài nguyên. Dùng số worker/queue có giới hạn, quota per host, timeout và chính sách cancellation.

### Ai sở hữu InputStream khi stage thất bại trước khi chạy?

Đây là một góc khó: nếu pipeline dùng executor và task **bị reject/hủy** giữa lúc HttpResponse đã có nhưng **chưa chuyển stream vào try-with-resources**, tài nguyên có thể không được đóng. Thiết kế production cần định nghĩa rành mạch handoff:

- Callback nhận HttpResponse phải sở hữu handle ngay và **đảm bảo** sẽ có consumer tiếp nhận.
- Nếu không thể schedule consumer, phải **close stream ngay** trong nhánh thất bại.
- Sau khi handoff thành công, chỉ một owner chịu trách nhiệm close.
- Tránh để cả hai bên cùng tự ý read/close mà không có chính sách đồng bộ.
- Đảm bảo shutdown executor không bỏ quên response bodies đang mở.

Một cách đơn giản với workload nhỏ là xử lý body trong một method rõ ownership và gọi trực tiếp từ một worker do application kiểm soát; với workload lớn, xây stream manager có registry các active bodies và cleanup khi shutdown.

## 9. Cancellation: hủy future khác đóng stream đã nhận

**CompletableFuture.cancel(true)** trong default HttpClient có thể yêu cầu hủy HTTP exchange **khi future chưa hoàn thành**. Javadoc không hứa sẽ hủy ngay lập tức, và request có thể đã được gửi/server đã bắt đầu xử lý. Hành vi transport tùy HTTP version (HTTP/1.1 có thể đóng connection, HTTP/2 có thể reset stream).

**Sau khi future đã hoàn thành** với **HttpResponse<InputStream>**, việc gọi **cancel(true)** trên **chính future đó** thường không còn hiệu lực hủy: CompletableFuture đã ở terminal state, không thể đảo completion thành cancel. **Muốn dừng body, đóng InputStream** hoặc với publisher **subscription.cancel()**.

~~~text
Future còn pending:
    cancel(true) -> attempt cancel HTTP exchange
                    (best effort; không đồng nghĩa server rollback)

Future đã success -> HttpResponse<InputStream>:
    future.cancel(true) không thay thế body.close()
    caller phải đọc đến EOF hoặc close InputStream

Future đã success -> HttpResponse<Publisher>:
    future.cancel(true) không thay thế subscription.cancel()
    caller phải subscribe rồi drain tới terminal hoặc cancel
~~~

### Quy tắc cancellation theo thời điểm

| Thời điểm | Cần quản lý gì? | Hành động đúng |
| --- | --- | --- |
| Trước khi gửi | Request chưa submit | Không gửi; giải phóng dữ liệu đầu vào nếu thuộc sở hữu caller |
| Sau sendAsync, trước future complete | HTTP exchange đang tiến triển | Có thể gọi cancel(true), hiểu đây là best-effort |
| Future đã có HttpResponse<InputStream> | Streaming body mở | Close body stream hoặc đọc đến EOF |
| Future đã có HttpResponse<Stream<String>> | Stream line-backed mở | Close Stream hoặc duyệt đến hết |
| Future đã có HttpResponse<Publisher> | Subscription chưa được nhận/hoàn thành | Subscribe một lần, request đến terminal hoặc cancel |
| Đã đọc/hủy body hoàn chỉnh | Resource lifecycle kết thúc theo contract | Xác minh không còn reference/worker bị bỏ quên |

### Timeout không tự biến future thành body-consumption deadline

**HttpRequest.Builder.timeout(Duration)** là giới hạn của request theo API; với streaming BodyHandler, future có thể hoàn tất sớm trong khi đọc body vẫn đang chờ. Do đó **không** giả định **future.orTimeout(...)** sau khi headers sẵn sàng sẽ tự chấm dứt mọi thao tác read sau đó. Nếu body cần deadline/idle timeout riêng, ứng dụng phải thiết kế giám sát và chủ động **close/cancel body** khi quá hạn.

Ví dụ service trả headers rồi mở một stream sự kiện dài hạn: đó có thể là hành vi đúng theo giao thức, không phải một HTTP request “bị lỗi” chỉ vì body chưa kết thúc. Consumer cần chính sách khi nào vẫn tiếp tục đợi, khi nào thoát.

## 10. Flow.Publisher: tiêu thụ đủ, hủy sớm và backpressure

Khác với InputStream blocking, **Flow.Publisher** theo mô hình **Reactive Streams** nhận demand qua **Flow.Subscription.request(n)**. Cơ chế này phù hợp pipeline tiêu thụ từng nhóm **List<ByteBuffer>**.

### Vì sao chỉ subscribe mà không request là chưa đủ?

~~~java
publisher.subscribe(new Flow.Subscriber<>() {
    @Override
    public void onSubscribe(Flow.Subscription s) {
        // BUG: không s.request(...)
    }

    @Override
    public void onNext(List<ByteBuffer> buffers) {
        // Không được gọi nếu không có demand.
    }

    @Override public void onError(Throwable error) {}
    @Override public void onComplete() {}
});
~~~

Subscriber chưa tạo demand có thể khiến upstream **không gửi thêm dữ liệu**, dù server và connection còn hoạt động. Nếu cả pipeline chờ nhau, tài nguyên có thể giữ rất lâu. Nếu consumer không muốn nhận dữ liệu, gọi **s.cancel()**; nếu muốn nhận, gọi **s.request(n)** theo một giới hạn hợp lý.

### Hủy sau khi đã nhận một số chunk

~~~java
// Snippet: hủy khi đã đạt ngưỡng mong muốn.
@Override
public void onNext(List<ByteBuffer> chunks) {
    for (ByteBuffer buf : chunks) {
        processed += buf.remaining();
        consume(buf);
    }
    if (processed >= byteLimit) {
        subscription.cancel();
    } else {
        subscription.request(1);
    }
}
~~~

Đây là **snippet** dùng các biến/method do ứng dụng tự định nghĩa. Không phải cứ cancel là sẽ nhận onComplete: sau cancel, upstream có thể không gọi onComplete; caller nên tự hoàn thành **consumer-level CompletableFuture** của mình theo trạng thái **cancelled/early-stop** đúng yêu cầu.

**Không giữ ByteBuffer từ onNext vô thời hạn** và giả định nội dung đó không bao giờ thay đổi: nếu cần dùng sau callback, copy dữ liệu theo chiến lược quản lý bộ nhớ và ownership. Tránh copy toàn bộ response lớn vào ByteArrayOutputStream trong production nếu không có size limit. Demo chỉ gom 4 byte để dễ quan sát.

### Một subscriber có thể tách complete của body

~~~text
responseFuture: CompletableFuture<HttpResponse<Publisher>>
   └─ completed khi headers và Publisher sẵn sàng

bodyDone: CompletableFuture<Result>
   ├─ completed khi onComplete + parse cuối thành công
   ├─ completed exceptionally khi onError/parse failure
   └─ cancelled/early-stop sau subscription.cancel() theo policy
~~~

Chỉ dùng **responseFuture.thenAccept(response -> response.body().subscribe(...))** mà không trả về/quan sát **bodyDone** sẽ làm tầng gọi trên nhìn thấy “hoàn tất” trước khi body thật được tiêu thụ. Tổ chức riêng bodyDone và truyền ra ngoài khi cần kết quả cuối cùng.

## 11. Các lỗi sau khi future complete cần xử lý riêng

Một HTTP response có thể có status 200 và future completed; nhưng trong quá trình tiêu thụ body vẫn phát sinh:

- **IOException** khi InputStream đọc mạng bị reset/đóng hoặc body lỗi.
- **UncheckedIOException/exception** khi duyệt Stream<String> hoặc decoder gặp dữ liệu lỗi tùy handler.
- **Flow.Subscriber.onError** khi publisher gặp lỗi network/protocol/cancellation.
- **ParseException, IllegalArgumentException, JSON decoding error** khi consumer phân tích body, dù transport thành công.
- **Size limit exceeded** khi consumer phát hiện body lớn hơn giới hạn.
- **Checksum mismatch** khi ứng dụng yêu cầu integrity end-to-end độc lập với HTTP/TLS.
- **Timeout do application** khi stream chưa phát dữ liệu mới đủ lâu.
- **Disk I/O failure** khi ghi download từ InputStream sang file.

**Đừng ghi metric request_success=true ngay khi responseFuture.complete** nếu thành công nghiệp vụ cần body đầy đủ. Ít nhất nên tách:

~~~text
http_response_ready=true
http_status=200
response_future_completed=true
body_state=READING
body_bytes_received=...
body_result=PENDING
connection_state=not_asserted
~~~

Khi body kết thúc:

~~~text
http_response_ready=true
http_status=200
response_future_completed=true
body_state=EOF_AND_CLOSED
body_bytes_received=...
body_result=SUCCESS
~~~

Hoặc:

~~~text
http_response_ready=true
http_status=200
response_future_completed=true
body_state=CLOSED_EARLY
body_result=CANCELLED_BY_CONSUMER
reason=size_limit
~~~

Một **HttpResponse.statusCode() == 200** cũng không chứng minh body JSON đã parse hợp lệ hoặc business operation đúng. Hãy định nghĩa thành công theo contract của ứng dụng, không theo trạng thái một future trung gian.

## 12. Khi nào đóng sớm và ảnh hưởng đến connection pooling?

Java HTTP client có thể dùng lại connection cho request khác nếu còn phù hợp, nhưng streaming body có thể đang chiếm network resources.

**Read to EOF** là cách tốt nếu bạn thật sự cần nội dung và body có giới hạn. Nó thường giúp client hoàn tất response sạch sẽ, tạo điều kiện cho connection reuse.

**Close early** là cách đúng khi caller muốn từ chối/bỏ dở body, ví dụ:

- Response có **Content-Type** không đúng contract.
- Header báo **Content-Length** vượt giới hạn (vẫn phải bảo vệ cả trường hợp thiếu/sai header).
- Chỉ cần vài byte đầu để quyết định, không muốn download tiếp.
- Người dùng hủy tải file.
- Job bị timeout hoặc parent request bị cancel.
- Parser báo dữ liệu hỏng và không thể tiếp tục.

Tuy nhiên, **close() trước EOF có thể khiến HTTP/1.1 connection bị đóng hoặc không reuse**; với các protocol multiplex như HTTP/2, việc hủy một stream có thể có cơ chế khác. **Không** hứa sẽ reuse socket sau close sớm. Cũng đừng cố đọc hàng GB không cần thiết chỉ để giữ keep-alive nếu điều đó hại bandwidth/RAM/latency.

### Vì sao resource leak khó thấy trong test nhỏ?

Một chương trình gửi một request rồi exit có thể không bộc lộ vấn đề. Khi chạy server lâu dài, hàng trăm streaming bodies bị bỏ quên có thể gây:

- Tăng **active connections** hoặc stream count.
- Connection pool không có slot hữu ích dù future count đã giảm.
- Memory giữ buffers/callback references.
- Quá nhiều threads chờ read.
- Backpressure kéo dài giữa client và server.
- **HttpClient.close()** ở Java 21+ chờ rất lâu hoặc không hoàn tất vì những stream chưa drain/cancel.

Theo **HttpClient Javadoc Java 21+**, orderly shutdown của client cần các request đã submit chạy đến completion. Nếu caller không close/cancel/drain streaming bodies, quá trình shutdown có thể không hoàn thành đúng mong đợi. **Đóng HttpClient không phải giải pháp thay cho closing body streams**.

## 13. Về quyền sở hữu stream khi gọi nhiều service/layer

Giả sử Service A gọi HTTP client rồi trả InputStream cho Service B:

~~~text
Service A
  -> HttpClient.sendAsync(... ofInputStream())
  -> HttpResponse<InputStream>
  -> trả InputStream sang Service B
                              |
                              +-- Ai phải close?
                              +-- Khi timeout của A?
                              +-- Khi B bị cancel?
                              +-- Khi response body quá lớn?
~~~

Nếu A đóng ngay khi method kết thúc, B sẽ không đọc được. Nếu A không đóng, còn B quên đóng, leak sẽ xuất hiện. Cần một trong các hợp đồng sau:

1. **A owns and consumes:** A đọc body trong scope của mình, parse/ghi và trả **CompletableFuture<Result>**; A chịu trách nhiệm close.
2. **Ownership transfer:** A trả **streaming handle** rõ ràng cho B, tài liệu hóa rằng **B bắt buộc close/cancel**, và A bảo đảm cleanup nếu không handoff được.
3. **Structured streaming:** A trả Publisher hoặc abstraction có cancellation, backpressure, deadline và lifecycle do một pipeline manager quản lý.
4. **No stream needed:** nếu body nhỏ và hữu hạn, dùng **ofString/ofByteArray** để tránh chuyển quyền sở hữu một tài nguyên sống.

**Một tài nguyên, một owner ở mỗi thời điểm** là nguyên tắc tốt. Bên nào chịu trách nhiệm cuối cùng phải được thể hiện qua API contract, code review và tests. Không giấu InputStream trong một record response mà người dùng tưởng là dữ liệu đã có sẵn toàn bộ.

## 14. Lỗi phổ biến trong code bất đồng bộ

| Anti-pattern | Hậu quả | Cách xử lý |
| --- | --- | --- |
| **future.isDone() = true** nên bỏ qua body | Response body còn mở, leak tài nguyên | Đọc đến EOF hoặc close/cancel |
| **thenAccept(HttpResponse::statusCode)** rồi không đọc stream | HTTP request còn outstanding ở tầng body | Xây consumer có ownership |
| **future.cancel(true)** sau successful completion | Không hủy InputStream đã giao | Close InputStream hoặc cancel subscription |
| **ofLines().limit(3)** rồi không close | Dừng sớm mà stream còn mở | try-with-resources cho Stream |
| **ofPublisher()** rồi không subscribe | Body bytes không được consume | Subscribe một lần và request/cancel |
| Subscribe hai lần vào publisher | Lần sau onError(IllegalStateException) | Chỉ một subscriber |
| Subscriber không request | Backpressure làm pipeline chờ | request(n) hoặc cancel |
| Subscriber bỏ giữa chừng không cancel | Exchange có thể chưa hoàn tất | subscription.cancel() |
| **readAllBytes()** cho body không giới hạn | Có thể OOM hoặc chờ vô hạn | Bounded chunk processing, byte/deadline limits |
| Không đóng khi parse lỗi | Exception branch leak | try-with-resources và finally |
| Đọc body trên thread callback không kiểm soát | Block network/executor, starvation | Dùng bounded worker executor |
| Thấy 200 rồi coi job nghiệp vụ xong | Body có thể lỗi hoặc thiếu | BodyDone/parseDone future riêng |
| Đóng InputStream trước khi handoff | Consumer gặp stream đã đóng | Quy định ownership transfer |
| Chỉ close HttpClient khi shutdown | Shutdown có thể mắc kẹt với streams | Đóng/drain/cancel từng body |
| Tin Content-Length tuyệt đối | Server vẫn có thể gửi lỗi/malformed | Đặt giới hạn byte thực đã đọc |
| Gộp body failure vào HTTP 500 | Làm sai phân loại transport/consumer | Log exception/cause riêng |
| Đọc body tùy ý nhiều thread | Race về position/state/close | Một reader hoặc đồng bộ theo protocol |

## 15. Thiết kế timeout, cancellation và các stream lâu dài

### Không đồng nhất response timeout và body idle timeout

Một request stream như **Server-Sent Events (SSE)**, streaming log, tải dữ liệu dài hoặc media có thể dự định mở nhiều phút/giờ. Future cung cấp **InputStream/Publisher** có thể hoàn thành sớm; việc body chưa EOF không nhất thiết là lỗi. Chính ứng dụng cần quản lý **heartbeat, idle timeout, cancellation, max duration và maximum bytes**.

Một policy có thể gồm:

| Ngưỡng | Ví dụ | Hành động khi vượt |
| --- | --- | --- |
| **Connect timeout** | 3 giây | Hủy attempt/chuyển exception |
| **Response headers deadline** | 5 giây | Timeout request nếu chưa có response |
| **Body idle timeout** | 30 giây không có byte | Close/cancel body theo API contract |
| **Maximum body duration** | 10 phút cho một job hữu hạn | Dừng, cleanup, báo timeout |
| **Max body bytes** | 20 MiB | Từ chối/close khi vượt; kể cả khi Content-Length thiếu |
| **Max active streams** | 100 per service | Backpressure/queue/reject hợp lý |

Các số trên **chỉ minh họa**, không phải default của Java API. **HttpClient.Builder.connectTimeout()** và **HttpRequest.Builder.timeout()** có semantics riêng; không mặc định chúng áp được **body idle timeout** trong mọi trường hợp streaming. Khi deadline application hết, owner phải chủ động quản lý close/cancel và completion của consumer-level future.

### Cẩn trọng khi cancel từ thread khác

Nếu một thread đang block trong **InputStream.read()** và thread khác gọi **close()**, phản ứng cụ thể phụ thuộc implementation/transport; code cần handle IOException/cancellation và đóng đúng một lần. Trong default JDK client, một số interrupt khi blocking read có thể khiến request bị cancel và stream đóng. **Không** hứa một chính xác message exception hay thời điểm giải phóng socket trên mọi JDK/HTTP version.

Nếu dùng Publisher, giữ reference Subscription trong state an toàn cho cancellation từ ngoài. Gọi **cancel()** khi không nhận nữa, và hoàn tất consumer-level future phù hợp; không chờ onComplete sau cancel như một bảo đảm.

## 16. Test cần có trước khi triển khai

| Tình huống | Cách mô phỏng | Điều phải xác minh |
| --- | --- | --- |
| Headers tới trước body end | Dùng CountDownLatch trên server như demo | responseFuture completed khi server còn giữ chunk cuối |
| Body ít byte | Server trả 1–2 byte rồi kết thúc | Consumer vẫn close/drain đúng |
| Body lớn | Stream hàng MB/GB có kiểm soát | Không gom hết vào RAM nếu không cần |
| Body vô hạn/chậm | Server giữ stream mở | Có application deadline/cancel khi cần |
| Đóng sớm | Chỉ đọc prefix rồi close | Không giữ tài nguyên; không giả định keep-alive reuse |
| Parser throw exception | Consumer ném giữa vòng read | finally/try-with-resources vẫn close |
| Publisher demand=0 | Subscriber không request | Không treo vô hạn khi ứng dụng quyết định cancel |
| Publisher cancel | Đạt byte limit rồi cancel | Không cần onComplete để giải phóng |
| Publisher subscribe lần hai | Subscribe hai lần vào một body publisher | Lần thứ hai nhận error theo contract |
| Body I/O failure sau future complete | Server abort giữa body | Future success không che lỗi ở read/onError |
| Caller cancel trước future done | Cancel sendAsync future | Best-effort cancellation, no false guarantee |
| Caller cancel sau future done | Cancel future rồi kiểm tra body ownership | Vẫn phải close body |
| Executor rejects task | Saturate bounded executor | Stream được close nếu handoff consumer thất bại |
| Client shutdown với stream mở | Mở body nhưng không consume | Shutdown có thể bị chặn; cleanup stream trước |

**Không nên dựa vào Thread.sleep để “chứng minh future completed trước body”.** Sleep có thể thay đổi theo scheduling/CPU. Dùng **CountDownLatch** hoặc barrier để server giữ response body cho đến khi client đã quan sát được future completed.

### Mẹo kiểm thử Publisher

Sử dụng một **Flow.Subscriber** ghi lại số lần **onSubscribe**, **onNext**, **onComplete**, **onError** và **cancel**. Viết assertion để bảo đảm **chỉ một** terminal signal cho đường hoàn tất bình thường, không request dữ liệu sau terminal, và không giữ subscription khi consumer đã hủy.

Với HTTP response lớn, dùng bounded buffers để kiểm tra backpressure: subscriber chỉ request tiếp sau khi chunk trước đã được xử lý. Điều này tạo contract có thể kiểm thử, thay vì rely vào kích thước socket buffer hay delay ngẫu nhiên.

## 17. Quan sát vận hành: hai chiều completed khác nhau

Trên một service thực, nên có metric tách:

~~~text
HTTP response stage:
  request_started
  response_headers_received
  response_future_completed
  http_status

Streaming body stage:
  response_body_open
  response_body_bytes_received
  response_body_eof
  response_body_close
  response_body_cancel
  response_body_error
  active_stream_count
  body_lifetime_ms
~~~

Một hệ thống có nhiều **response_future_completed** nhưng **response_body_close** rất ít có thể đang có **resource leaks**, hoặc là một ứng dụng streaming dài hạn có chủ đích; cần kết hợp **active stream count**, tuổi stream và cancellation policy.

Không log raw body chứa thông tin nhạy cảm. Khi debug sự cố, log **request/trace ID, endpoint được làm mờ nếu chứa dữ liệu cá nhân, status, loại body handler, open/close/cancel events, duration, bytes**. Nếu HTTP status 200 nhưng body đọc thất bại, ghi riêng HTTP response stage và body failure stage.

### Tránh tối ưu sai

- Tăng số lượng HTTP connections không chữa được logic quên close body.
- Thêm worker threads không thay thế backpressure và bounded queue.
- Tắt timeout để “cho stream sống mãi” không phù hợp với API không phải streaming vô hạn.
- Dùng ofByteArray để tránh phải close có thể chuyển lỗi từ socket leak thành **OOM**.
- Dùng body stream nhưng gọi readAllBytes ngay có thể mất hoàn toàn lợi ích streaming.

## 18. Bài tập tự kiểm tra

1. Vì sao **CompletableFuture<HttpResponse<InputStream>>** có thể completed khi server vẫn chưa gửi chunk cuối? Điều gì trong contract BodySubscriber tạo ra hành vi đó?
2. So sánh **ofString()** với **ofInputStream()** về thời điểm future complete, bộ nhớ và ownership.
3. Client dùng **thenAccept(response -> log(status))** và không động vào InputStream. Điều gì có thể xảy ra với request completion và connection pool?
4. Một consumer gọi **input.readNBytes(1024)** rồi dừng vì chỉ cần prefix. Nó cần xử lý stream như thế nào?
5. Với **ofLines()**, tại sao **limit(5)** + **forEach** không đồng nghĩa body đã đọc hết? Giải thích vai trò **Stream.close()**.
6. Một **Flow.Publisher<List<ByteBuffer>>** được trả từ ofPublisher nhưng chưa subscribe. Có thể khẳng định HTTP exchange đã giải phóng hết resources không?
7. Subscriber đã subscribe nhưng không **request(n)** và cũng không cancel. Nó có thể gây gì cho body pipeline?
8. Một Publisher bị subscribe hai lần. Java Javadoc quy định lần thứ hai nhận gì?
9. Outer future hoàn thành với status 200 rồi InputStream.read ném IOException. Future có bị chuyển ngược sang exceptional không? Bạn nên báo lỗi ở future nào?
10. Nếu **CompletableFuture.cancel(true)** được gọi sau khi outer future completed, nó có thể thay thế **InputStream.close()** không?
11. Giải thích vì sao **HttpClient.close()** từ Java 21 không phải giải pháp cho một ứng dụng không drain/close streaming bodies.
12. Thiết kế API trả về **CompletableFuture<Result>** mà Result chỉ xuất hiện khi body đã parse xong; xác định callback nào sở hữu InputStream.
13. Xây service nhận response lớn nhưng chỉ cần checksum. Làm thế nào để đọc chunk-by-chunk và giới hạn byte, thay vì readAllBytes?
14. Tạo một test server cố ý abort body sau khi đã gửi headers. Bạn mong outer future và consumer-stage future thể hiện gì?
15. Với một SSE stream mở hàng giờ, hãy thiết kế idle timeout, cancellation, resource ownership và active streams monitoring.

## 19. Checklist code review

- [ ] Với **ofInputStream()**, ai sẽ gọi **close()** hoặc đọc tới EOF?
- [ ] Với **ofLines()**, ai sẽ duyệt hết hoặc **close Stream**?
- [ ] Với **ofPublisher()**, đã subscribe **một lần** và request đủ hoặc cancel?
- [ ] Có tách **responseFuture completed** và **bodyConsumption completed**?
- [ ] Có đường cleanup khi parse exception, timeout, caller cancel và executor rejection?
- [ ] Có giới hạn total bytes, idle time, active streams, worker queue và memory?
- [ ] Không coi **status 200** hay **future.isDone()** là chứng nhận body hoàn chỉnh?
- [ ] Có xử lý IOException sau khi future đã completed?
- [ ] Có tránh blocking read trong callback/executor không được kiểm soát?
- [ ] Có chính sách ownership khi handoff body stream qua nhiều lớp?
- [ ] Có hiểu close sớm có thể ảnh hưởng connection reuse?
- [ ] Nếu Java 21+ dùng HttpClient.close(), đã đảm bảo streaming requests có thể hoàn thành hoặc bị hủy?
- [ ] Có test deterministic chứng minh future hoàn thành khi body vẫn mở?

**Ghi nhớ:** **sendAsync + streaming BodyHandler chia công việc thành hai giai đoạn.** Giai đoạn 1 hoàn thành **CompletableFuture<HttpResponse<T>>** khi response và streaming handle đã sẵn sàng. Giai đoạn 2 do **consumer** sở hữu: **read-to-EOF hoặc close InputStream; duyệt hết hoặc close Stream<String>; subscribe/request đến terminal signal hoặc cancel Flow.Subscription**. Chỉ sau khi xử lý đúng giai đoạn 2 mới có cơ sở nói rằng **body đã hoàn tất về mặt sử dụng và tài nguyên có đường giải phóng hợp lệ**. Đừng dùng future completed để thay nghĩa vụ này.

### Tài liệu chính thức

- [HttpClient — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [HttpResponse.BodyHandler — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html)
- [HttpResponse.BodySubscriber — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html)
- [HttpResponse.BodyHandlers — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [HttpResponse.BodySubscribers — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
- [Flow.Publisher — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Publisher.html)
- [Flow.Subscription — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [HttpClient — Java SE 21: close/shutdown và streaming resources](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [HttpServer — Java SE 17 (test fixture)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
