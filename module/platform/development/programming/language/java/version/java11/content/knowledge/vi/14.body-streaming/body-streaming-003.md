# `BodyHandlers.ofPublisher()` và nhu cầu nhận dữ liệu (backpressure) trong Java 11+

## 1. Bài toán: nhận HTTP response theo tốc độ mà ứng dụng xử lý được

Một HTTP response có thể chứa vài byte, vài MB hoặc một luồng dữ liệu rất lớn. Nếu tải toàn bộ body thành `String` hoặc `byte[]` trước khi xử lý, ứng dụng có thể dùng nhiều bộ nhớ và khó phối hợp với một hệ thống nhận dữ liệu chậm (ghi database, ghi file, giải mã, truyền sang worker khác).

Java 11 cung cấp `java.net.http.HttpResponse.BodyHandlers.ofPublisher()` để trả response body dưới dạng **`Flow.Publisher<List<ByteBuffer>>`**. Ứng dụng đăng ký một `Flow.Subscriber<List<ByteBuffer>>`, chủ động thông báo **nhu cầu nhận bao nhiêu lượt dữ liệu** bằng `Flow.Subscription.request(long n)`, và xử lý từng lượt trong `onNext`.

Đây là cơ chế **Reactive Streams/Flow backpressure**: bên nhận có thể yêu cầu từng đợt thay vì ngầm nhận mọi nội dung về bộ nhớ. Nhưng có giới hạn cần hiểu chính xác: nhu cầu tính theo **số lần phát item (`List<ByteBuffer>`)**, **không phải số byte**, và nó không thay thế toàn bộ chính sách giới hạn bộ nhớ, dung lượng dữ liệu hoặc bảo vệ trước server chậm.

Định dạng API:

~~~java
HttpResponse.BodyHandler<Flow.Publisher<List<ByteBuffer>>> handler =
        HttpResponse.BodyHandlers.ofPublisher();
~~~

`ofPublisher()` là API chuẩn của **Java 11**, vẫn xuất hiện trong tài liệu API Java hiện hành. Nó **không** phải `SubmissionPublisher`, không tự tạo subscriber xử lý dữ liệu giúp ứng dụng, và không biến tất cả HTTP calls thành thao tác thực hiện trong thread riêng.

### Ba mốc thời gian cần phân biệt

~~~text
client.send(request, BodyHandlers.ofPublisher())
       |
       v
Nhận status + response headers
       |
       v
HttpResponse<Flow.Publisher<List<ByteBuffer>>> được trả về
       |
       |    Body có thể chưa nhận hết
       v
response.body().subscribe(subscriber)
       |
       v
subscriber.onSubscribe(subscription)
       |
       v
subscription.request(n)  <-- bên nhận thông báo nhu cầu
       |
       v
subscriber.onNext(List<ByteBuffer>) ... có thể lặp nhiều lần
       |
       +------> request(thêm nhu cầu) nếu còn chỗ xử lý
       |
       v
subscriber.onComplete() hoặc onError(Throwable)
       |
       v
Trao đổi body kết thúc theo hợp đồng
~~~

**`send(...)` vẫn là phương thức đồng bộ**: có thể chặn thread gọi để nhận response headers. Với `ofPublisher`, việc nhận **toàn bộ** body **không nhất thiết hoàn tất** khi `send` trả về. Tương tự, future của `sendAsync(..., ofPublisher())` có thể hoàn tất khi response/publisher đã sẵn sàng, không phải khi subscriber xử lý xong body.

## 2. Vai trò `HttpClient`, `HttpRequest`, `BodyHandler`, `Publisher` và `Subscriber`

| Thành phần | Trách nhiệm | Ai chủ động? |
| --- | --- | --- |
| `HttpClient` | Gửi HTTP request, nhận status/headers và phối hợp nhận body | Client triển khai luồng HTTP |
| `HttpRequest` | Mô tả URI, method, headers, timeout và request body nếu có | Ứng dụng tạo |
| `BodyHandlers.ofPublisher()` | Chọn cách biểu diễn **response body** dưới dạng publisher | Ứng dụng chọn khi gọi `send` |
| `HttpResponse<Flow.Publisher<List<ByteBuffer>>>` | Giữ metadata response và publisher của body | HTTP client trả về |
| `Flow.Publisher<List<ByteBuffer>>` | Nguồn phát các nhóm `ByteBuffer` chứa bytes HTTP response | Publisher phát khi có demand |
| `Flow.Subscriber<List<ByteBuffer>>` | Nhận dữ liệu, xử lý, quyết định yêu cầu tiếp hay hủy | Ứng dụng triển khai |
| `Flow.Subscription` | Kết nối kiểm soát `request(n)` và `cancel()` giữa subscriber/publisher | Subscriber giữ và dùng |
| `BodySubscriber<Flow.Publisher<...>>` | Adapter bên trong HTTP client tạo publisher từ luồng body | `ofPublisher()` tạo/điều phối |

Đừng nhầm `HttpRequest.BodyPublishers` với `HttpResponse.BodyHandlers`:

- `HttpRequest.BodyPublishers.ofString(...)` là **đầu ra** từ client sang server.
- `HttpResponse.BodyHandlers.ofPublisher()` là **đầu vào** từ server về client, được nhận qua subscriber.

Không thể truyền `Flow.Subscriber<ByteBuffer>` thay cho `Flow.Subscriber<List<ByteBuffer>>` một cách tùy tiện. Một **item** của publisher là một **`List<ByteBuffer>`**, tức có thể chứa nhiều buffer và nhiều byte. Generic type ở đây rất quan trọng.

## 3. Hợp đồng `BodyHandlers.ofPublisher()`

Chữ ký trong Java 11+:

~~~java
public static HttpResponse.BodyHandler<
        Flow.Publisher<List<ByteBuffer>>> ofPublisher();
~~~

Mẫu gọi:

~~~java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.send(request, HttpResponse.BodyHandlers.ofPublisher());

int status = response.statusCode();
Flow.Publisher<List<ByteBuffer>> bodyPublisher = response.body();
~~~

Các dòng là **minh họa**, cần imports `java.net.http.*`, `java.nio.ByteBuffer`, `java.util.List`, `java.util.concurrent.Flow` cùng `client`/`request` đã tạo hợp lệ.

Các quy tắc đặc biệt quan trọng:

1. **Status và headers có thể đã sẵn sàng trước body.** Khi `HttpResponse` được trả về, việc đọc headers đã hoàn tất; body có thể vẫn đang tải xuống. `response.body()` không phải mảng bytes hay nội dung đã tải xong.
2. **Phải đăng ký subscriber đúng một lần.** Publisher trả về từ `ofPublisher()` chỉ hỗ trợ **một subscriber thành công**. Nếu `subscribe` thêm lần nữa, subscriber bổ sung nhận `onSubscribe` với subscription rỗng rồi `onError(new IllegalStateException(...))`. Không dùng cùng publisher như nguồn phát nhiều lần hay cho nhiều người nhận độc lập.
3. **Phải xử lý vòng đời nhận dữ liệu.** Sau khi lấy body publisher, ứng dụng cần subscribe và một trong hai điều: (a) yêu cầu đủ dữ liệu đến `onComplete`/`onError`, hoặc (b) `cancel()` nếu không tiếp tục nhận. **Không chỉ lấy `HttpResponse` rồi bỏ mặc publisher.**
4. **Không tự giải mã:** các phần tử là `ByteBuffer` chứa byte. Muốn hiểu text/JSON cần charset và parser riêng. Boundary của các buffer **không phải** ranh giới dòng, ký tự UTF-8 hay thông điệp nghiệp vụ.
5. **Không tự bảo đảm giới hạn bộ nhớ:** có demand nhưng một item có thể chứa nhiều buffer và mỗi buffer có nhiều bytes; hệ điều hành và HTTP client cũng có thể buffer dữ liệu. Subscriber phải giới hạn tổng byte đã nhận/lưu và khả năng tiêu thụ.
6. **HTTP 4xx/5xx vẫn có publisher.** `BodyHandlers.ofPublisher()` mặc định nhận body không phân biệt status. Quyết định xử lý/bỏ body phải dựa vào `statusCode()` và hợp đồng ứng dụng.

`ofPublisher()` thường dùng khi muốn kết nối HTTP body đến một pipeline streaming có subscriber chuyên biệt. Nếu ứng dụng chỉ muốn tải tệp thông thường hoặc nhận chuỗi nhỏ, các handler khác có thể đơn giản hơn đáng kể.

## 4. Giao thức `Flow.Subscriber` và ý nghĩa của nhu cầu

Subscriber triển khai bốn callback:

~~~java
public interface Subscriber<T> {
    void onSubscribe(Flow.Subscription subscription);
    void onNext(T item);
    void onError(Throwable throwable);
    void onComplete();
}
~~~

Đây là **chữ ký rút gọn minh họa** của `Flow.Subscriber<T>` (trong JDK, interface là nested type của `Flow`). Với `ofPublisher`, `T` là `List<ByteBuffer>`. Ý nghĩa:

| Callback | Khi nào | Nên làm gì? |
| --- | --- | --- |
| `onSubscribe(subscription)` | Đăng ký thành công; nhận khả năng điều khiển demand | Lưu subscription, gọi `request(n)` dương khi sẵn sàng |
| `onNext(list)` | Publisher có một item được phép phát theo demand | Xử lý các `ByteBuffer` **theo thứ tự**, không giả định item = 1 byte |
| `onError(error)` | Luồng thất bại, signal kết thúc do lỗi | Ghi nhận nguyên nhân, hoàn tất kết quả thất bại và giải phóng resource ứng dụng |
| `onComplete()` | Publisher không còn dữ liệu, signal hoàn tất bình thường | Hoàn tất kết quả thành công và cleanup |

Một subscriber chuẩn có thể nhận **nhiều `onNext`**, và các signal đến subscriber phải tuân thủ thứ tự/hợp đồng của `Flow`. Đừng tự gọi trực tiếp `onNext` để mô phỏng lại cơ chế demand khi code thực đã có publisher.

### `request(n)`: chính xác là đếm cái gì?

~~~java
subscription.request(1);
~~~

Lệnh trên cấp phép **tối đa một lời gọi `onNext` mới** (hoặc ít hơn nếu đã kết thúc). Với `Flow.Publisher<List<ByteBuffer>>`, **một `onNext` chứa một `List<ByteBuffer>`** chứ không phải chỉ một buffer hay một byte.

Ví dụ *minh họa*, không phải kích thước cố định:

~~~text
request(1)
    --> onNext([ByteBuffer(100 bytes), ByteBuffer(40 bytes)])
        (1 item, gồm 2 buffers và tổng 140 bytes)

request(1) lần nữa
    --> onNext([ByteBuffer(18 bytes)])
        (1 item, gồm 1 buffer và 18 bytes)
~~~

Số byte/buffer mỗi item phụ thuộc mạng, provider, hệ điều hành và cách HTTP client phân phối dữ liệu; các con số 100/40/18 chỉ minh họa **không được dùng để dự đoán kết quả thực tế**.

Theo `Flow.Subscription`:

- `request(n > 0)` tăng nhu cầu chưa được đáp ứng; có thể gọi nhiều lần theo hợp đồng.
- `request(0)` hoặc `request(n < 0)` là **sai**: subscriber sẽ nhận `onError` với `IllegalArgumentException`.
- `request(Long.MAX_VALUE)` có thể được xem như nhu cầu không giới hạn; tiện cho sink đủ nhanh nhưng làm mất kiểm soát từng lượt.
- `request(1)` mỗi lần sau khi xử lý xong giúp kiểm soát lượng công việc đang chờ, **không** có nghĩa “chỉ được nhận một byte trong RAM”.
- Khi subscriber **không request thêm**, publisher không được tự ý gọi `onNext` vượt demand, nhưng resource/connection có thể vẫn mở, và bytes có thể đang được buffer ở các tầng khác.
- `request(n)` kiểm soát **số item**, không chỉ định max response size hay timeout.

### Backpressure thực chất giúp ích gì?

Nếu producer (HTTP response) phát nhanh nhưng consumer (ví dụ đẩy sang ổ đĩa hay một service xử lý) chậm, subscriber có thể yêu cầu dữ liệu mới **sau khi** đã xử lý/bố trí chỗ cho item trước. Đây là tín hiệu giúp hạn chế lượng dữ liệu đẩy vào pipeline nhanh hơn năng lực xử lý.

Đây là **điều phối nhu cầu**, không phải giao thức yêu cầu HTTP server phải sản xuất chính xác `n` byte mỗi lần, không phải cơ chế chống mọi cuộc tấn công DoS, và không thay thế một hàng đợi có giới hạn hoặc deadline ứng dụng.

## 5. Ví dụ Java 11 hoàn chỉnh: `request(1)` và kiểm tra một subscriber duy nhất

Ví dụ dùng `com.sun.net.httpserver.HttpServer` từ module **`jdk.httpserver`** để mở endpoint loopback, không cần Internet. Một `HttpClient` gửi GET tới server, `ofPublisher()` trả publisher, và một `CollectingSubscriber`:

- Ban đầu gọi `request(1)`.
- Trong mỗi `onNext`, duyệt **toàn bộ** `List<ByteBuffer>`, copy các byte còn lại vào `ByteArrayOutputStream`, rồi gọi `request(1)` tiếp.
- Khi `onComplete`, hoàn tất một `CompletableFuture<byte[]>`.
- Khi có `onError`, hoàn tất future theo dạng thất bại.
- Sau đó thử đăng ký subscriber thứ hai để thấy `IllegalStateException` theo hợp đồng `ofPublisher`.

**Lưu ý:** gom bytes vào bộ nhớ ở ví dụ chỉ để dễ kiểm chứng. Với payload lớn, thay bộ đệm tích lũy bằng sink có giới hạn dung lượng và kiểm soát tốc độ/cleanup theo nghiệp vụ.

Tạo tệp **PublisherDemandDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
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
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PublisherDemandDemo {
    static class CollectingSubscriber implements Flow.Subscriber<List<ByteBuffer>> {
        private Flow.Subscription subscription;
        private final ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        private final AtomicInteger batches = new AtomicInteger();
        final CompletableFuture<byte[]> finished = new CompletableFuture<>();

        @Override public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            s.request(1);
        }
        @Override public void onNext(List<ByteBuffer> items) {
            try {
                for (ByteBuffer item : items) {
                    byte[] part = new byte[item.remaining()];
                    item.get(part);
                    buffer.write(part, 0, part.length);
                }
                batches.incrementAndGet();
                subscription.request(1);
            } catch (RuntimeException e) {
                subscription.cancel();
                finished.completeExceptionally(e);
            }
        }
        @Override public void onError(Throwable error) {
            finished.completeExceptionally(error);
        }
        @Override public void onComplete() {
            finished.complete(buffer.toByteArray());
        }
        int batchCount() {
            return batches.get();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/download", PublisherDemandDemo::serve);
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/download");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();

            HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
                    client.send(request, HttpResponse.BodyHandlers.ofPublisher());
            System.out.println("status=" + response.statusCode());
            System.out.println("publisherAvailable=" + (response.body() != null));

            CollectingSubscriber subscriber = new CollectingSubscriber();
            response.body().subscribe(subscriber);
            byte[] received = subscriber.finished.get(5, TimeUnit.SECONDS);
            System.out.println("text=" +
                    new String(received, StandardCharsets.UTF_8));
            System.out.println("batchesPositive=" +
                    (subscriber.batchCount() > 0));

            CompletableFuture<Boolean> rejected = new CompletableFuture<>();
            response.body().subscribe(new Flow.Subscriber<List<ByteBuffer>>() {
                @Override public void onSubscribe(Flow.Subscription s) {
                    s.request(1);
                }
                @Override public void onNext(List<ByteBuffer> value) {
                    rejected.complete(false);
                }
                @Override public void onError(Throwable error) {
                    rejected.complete(error instanceof IllegalStateException);
                }
                @Override public void onComplete() {
                    rejected.complete(false);
                }
            });
            System.out.println("secondRejected=" +
                    rejected.get(5, TimeUnit.SECONDS));
        } finally {
            server.stop(0);
        }
    }

    private static void serve(HttpExchange exchange) throws IOException {
        byte[] data = "STREAM-HELLO".getBytes(StandardCharsets.UTF_8);
        try {
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, data.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(data);
            }
        } finally {
            exchange.close();
        }
    }
}
~~~

Biên dịch bằng **JDK 11 trở lên** có module `jdk.httpserver`; ví dụ không dựa vào API chỉ có ở Java 21:

~~~bash
javac --release 11 --add-modules jdk.httpserver PublisherDemandDemo.java
java --add-modules jdk.httpserver PublisherDemandDemo
~~~

**Stdout chính xác** đã kiểm tra trên JDK 24 khi biên dịch `--release 11`:

~~~text
status=200
publisherAvailable=true
text=STREAM-HELLO
batchesPositive=true
secondRejected=true
~~~

### Tại sao kết quả đúng?

1. `status=200`: server nội bộ đã trả HTTP 200 với body. Status được đọc từ `HttpResponse` ngay khi response headers đã có.
2. `publisherAvailable=true`: `response.body()` là publisher, không phải byte array. Publisher cần được subscribe để tiêu thụ nội dung.
3. `text=STREAM-HELLO`: `onNext` duyệt mọi `ByteBuffer` theo thứ tự, copy byte đến khi hết dữ liệu, rồi `onComplete` hoàn tất future. Payload được tạo bằng UTF-8 và chỉ decode khi đã thu đủ bytes.
4. `batchesPositive=true`: có ít nhất một `onNext` chứa bytes; demo **không in số lần `onNext` cụ thể**, vì độ phân mảnh buffer và số đợt phụ thuộc runtime/network.
5. `secondRejected=true`: publisher không cho phép subscribe thành công hai lần. Subscriber thứ hai nhận lỗi `IllegalStateException` qua `onError` theo hợp đồng, chứ không phải nhận bản sao thứ hai của body.

Vòng đời tài nguyên của ví dụ: `try/finally` dừng server. HTTP request được xử lý hoàn tất đến `onComplete`, không bỏ publisher ở trạng thái chưa subscribe. Một ứng dụng thực tế còn phải có chính sách hủy subscription khi **đợi future vượt deadline**, quản lý lỗi từ sink, retry và đóng/giải phóng resource có ownership riêng.

## 6. Điều gì xảy ra khi chỉ nhận một phần body?

Giả sử subscriber đã nhận vài KB nhưng người dùng hủy download, hoặc hệ thống đích không còn chỗ lưu. Không nên chỉ **ngừng gọi `request` và bỏ quên `Subscription`**. Khi không còn muốn dữ liệu, gọi `subscription.cancel()`.

Mẫu ý tưởng:

~~~java
class CancellingSubscriber implements Flow.Subscriber<List<ByteBuffer>> {
    private Flow.Subscription subscription;
    @Override public void onSubscribe(Flow.Subscription s) {
        subscription = s;
        s.request(1);
    }
    @Override public void onNext(List<ByteBuffer> item) {
        // Kiểm tra điều kiện hủy; quản lý số byte thực tế.
        if (shouldStop()) {
            subscription.cancel();
            return;
        }
        consume(item);
        subscription.request(1);
    }
    @Override public void onError(Throwable error) { handleError(error); }
    @Override public void onComplete() { finish(); }
}
~~~

Đây là **mã phác thảo, không độc lập**: `shouldStop`, `consume`, `handleError` và `finish` phải do ứng dụng triển khai; cần imports, cleanup và thread-safety. Điểm chính là hành động **`cancel()` tường minh** khi không thể/không muốn tiếp tục.

**Hợp đồng của `cancel()` trong `Flow`:**

- `cancel()` đề nghị dừng phát thêm item theo cơ chế *best effort*.
- Một số signal có thể vẫn đến sau `cancel()` do race/in-flight data; handler cần chịu được.
- Subscriber **không được trông chờ** `onComplete()` hay `onError()` sẽ luôn được gọi sau khi cancel.
- HTTP client có thể phải hủy stream hoặc đóng underlying connection, tùy HTTP version/implementation. Vì vậy cancel sớm có thể giảm khả năng tái sử dụng kết nối so với việc đọc hết body.
- Nếu đã cancel, ứng dụng phải tự hoàn tất promise/trạng thái nghiệp vụ phù hợp và thu hồi tài nguyên sink; đừng chỉ chờ một `onComplete` sẽ không bao giờ tới.

**Quan trọng:** Nếu `response.statusCode()` là 404 nhưng application không cần error body, vẫn phải giải phóng publisher: lựa chọn subscribe rồi tiêu thụ/bỏ byte đến hết, hoặc subscribe và cancel ngay theo policy. Không được đơn thuần `return` sau khi đọc status mà không quản lý publisher.

## 7. Nhu cầu dữ liệu có liên quan gì đến HTTP server?

Cơ chế Flow có hai bên:

~~~text
Server gửi response bytes
           |
           v
HTTP Client / network buffers / protocol
           |
           v
Flow.Publisher<List<ByteBuffer>>
           |
        demand
           |
           v
Subscriber xử lý onNext
           |
           v
Sink (file / database / parser / queue có giới hạn)
           |
       yêu cầu tiếp
           |
           +------ subscription.request(1)
~~~

Backpressure có thể làm HTTP client hạn chế chuyển data xuống subscriber khi demand bằng 0. Tuy nhiên **không có cam kết byte-for-byte rằng server sẽ dừng gửi ngay**, vì còn buffer, TCP flow control và pipeline của runtime.

### Bounded processing vs unbounded queue

**Mẫu tốt:** subscriber chỉ gọi `request(1)` sau khi đã xử lý xong item trước hoặc khi sink có capacity. Nếu sink bất đồng bộ, có thể dùng một hàng đợi **có giới hạn**, xác nhận item đã được xử lý và sau đó phát demand mới. Việc điều phối cần đúng thread-safety và trạng thái hủy.

**Mẫu dễ gây lỗi:** ngay khi `onNext` nhận item, sao chép vào một queue vô hạn rồi gọi `request(Long.MAX_VALUE)`. Khi sink chậm hơn nguồn, queue phát triển không giới hạn, khiến backpressure chỉ còn trên danh nghĩa. Cũng không nên giữ tham chiếu đến rất nhiều `ByteBuffer` trong bộ nhớ mà không có byte budget.

### Không giải mã UTF-8 riêng lẻ theo từng chunk

Một ký tự Unicode UTF-8 có thể bị cắt giữa hai `ByteBuffer` hoặc hai lần `onNext`. Ví dụ chữ tiếng Việt có dấu không bắt buộc nằm trọn trong một buffer. Làm như sau dễ sai:

~~~java
// Minh họa LỖI có thể xảy ra khi chunk cắt giữa ký tự UTF-8:
// String part = StandardCharsets.UTF_8.decode(buffer).toString();
// processText(part);
~~~

Thay vào đó, nếu dữ liệu text nhỏ và được giới hạn, có thể gom đủ byte rồi decode **một lần**. Với stream text lớn, dùng `CharsetDecoder` giữ trạng thái giữa các lần nhận, xử lý phần byte chưa đủ tạo thành code point và kết thúc bằng `flush` đúng hợp đồng. Nếu là nhị phân, đừng decode text. Đồng thời phải xử lý nội dung giả mạo charset, giới hạn dung lượng và ranh giới giao thức nghiệp vụ (message framing).

## 8. Ví dụ tích hợp với `sendAsync`

`sendAsync(request, BodyHandlers.ofPublisher())` trả:

~~~java
CompletableFuture<HttpResponse<Flow.Publisher<List<ByteBuffer>>>> pending =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofPublisher());
~~~

**Đây là mã minh họa**, cần có `client` và `request`, imports `CompletableFuture`/`Flow`/`List`/`ByteBuffer`. Future `pending` hoàn tất khi `HttpResponse` với publisher đã có (sau headers). Để đợi body xử lý xong, cần **một completion signal thứ hai của subscriber**:

~~~java
CompletableFuture<byte[]> allBytes = pending.thenCompose(response -> {
    if (response.statusCode() != 200) {
        // Không được bỏ mặc publisher; vẫn cần subscribe rồi drain/cancel.
    }
    CollectingSubscriber subscriber = new CollectingSubscriber();
    response.body().subscribe(subscriber);
    return subscriber.finished;
});
~~~

Đoạn này là **mẫu kết nối phác thảo**, giả định lớp `CollectingSubscriber` ở phần 5 và quy tắc status riêng; comments chưa phải nhánh lỗi hoàn chỉnh. `thenCompose` hợp nhất future của response với future của **quá trình nhận/tiêu thụ body**, tránh lỗi phổ biến “future có HttpResponse rồi nên body đã xong”.

Trong sản phẩm nên xử lý `onError`, timeout, cancellation, các trường hợp HTTP status không mong muốn và giới hạn byte trước khi coi `allBytes` thành công. Việc `CompletableFuture.cancel(...)` hoặc `orTimeout(...)` không tự tạo bằng chứng server đã ngừng truyền và không thay cho policy `Flow.Subscription.cancel()`.

### Ai gọi callback? Có phải `onNext` được chạy ngay trong thread caller?

Không được giả định như vậy. Các lời gọi signal của `Flow` theo hợp đồng được điều phối bởi publisher/implementation, **không phải cam kết chạy trên thread UI hay thread đã gọi `subscribe`**. Mỗi subscriber cần có trạng thái được công bố an toàn giữa các thread. Với kết quả `CompletableFuture`, callback có thể hoàn tất trên thread do HTTP client sử dụng.

Tránh giữ khóa nghiệp vụ trong `onNext` khi có thể block dài; tránh dùng `Thread.sleep` để mô phỏng xử lý nặng. Backpressure nên theo capacity thực tế, còn công việc nặng có thể được đưa vào executor/hàng đợi có giới hạn với tín hiệu hoàn tất rõ ràng.

## 9. So sánh các lựa chọn nhận body HTTP hiện hành

| Nhu cầu | `BodyHandler` | Kiểu `HttpResponse<T>` | Đặc điểm |
| --- | --- | --- | --- |
| Text/JSON nhỏ và đã giới hạn size | `ofString(UTF_8)` | `HttpResponse<String>` | Tích lũy/giải mã toàn bộ body, dễ dùng |
| Bytes nhỏ cần giữ nguyên | `ofByteArray()` | `HttpResponse<byte[]>` | Lấy byte array sau khi nhận đủ |
| Tải file thông thường | `ofFile(path, options)` | `HttpResponse<Path>` | HTTP client ghi xuống file, tự quản lý quyền/ghi đè |
| Dòng dữ liệu theo pull-style | `ofInputStream()` | `HttpResponse<InputStream>` | `read` từng phần; phải đọc/đóng stream |
| Text từng dòng | `ofLines()` | `HttpResponse<Stream<String>>` | Tiêu thụ một lần, đóng Java stream |
| Reactive subscriber kiểm soát demand | `ofPublisher()` | `HttpResponse<Flow.Publisher<List<ByteBuffer>>>` | `request(n)`/`cancel()` và subscribe một lần |
| Chỉ cần status/headers | `discarding()` | `HttpResponse<Void>` | Bỏ body theo handler |
| Đã có subscriber và muốn nối trực tiếp | `fromSubscriber(subscriber)` | `HttpResponse<Void>` hoặc kiểu tùy biến với finisher | Tránh publisher trung gian, nhưng quản lý subscriber phải chuẩn |

### Khi nào nên chọn `ofPublisher()`?

Chọn khi bài toán thực sự cần **tiếp nhận dữ liệu theo nhu cầu**: bơm body vào pipeline có backpressure, xử lý các chunk của response với logic riêng, đưa dữ liệu qua một reactive subscriber có khả năng hủy, và theo dõi completion của luồng riêng với việc nhận headers.

Không phải mọi download đều cần reactive API. Với yêu cầu lưu file không cần custom subscriber, `ofFile` đơn giản hơn; với một stream pull/read tuần tự, `ofInputStream` dễ tiếp cận hơn; với JSON nhỏ, `ofString` và parser thường dễ bảo trì hơn.

## 10. Xử lý lỗi và tình huống biên

### 10.1 HTTP status không mong đợi

`ofPublisher()` không tự từ chối response khi mã 404/500. Có thể kiểm tra `response.statusCode()` trước `subscribe`, nhưng vẫn phải giải phóng body. Nếu cần lựa chọn cách nhận body dựa vào status **trước khi body bắt đầu đến**, hãy dùng `HttpResponse.BodyHandler<T>` tùy biến nhận `ResponseInfo`, giữ kiểu `T` nhất quán giữa các nhánh.

### 10.2 Subscriber xử lý lỗi

`onNext` không khai báo checked `IOException`. Nếu đang ghi file/database và sink báo lỗi, catch exception ở callback, **cancel subscription**, đánh dấu future/trạng thái thất bại và dọn sink theo chính sách. Không ném unchecked exception tùy ý rồi trông chờ HTTP client tự dọn mọi resource ứng dụng. Thất bại có thể xảy ra sau khi đã xử lý một phần body; không mặc định thao tác có tính transactional.

### 10.3 `request(0)`, nhu cầu bằng âm và nhu cầu vô hạn

`request(0)` hoặc giá trị âm vi phạm hợp đồng Flow và gây `onError(IllegalArgumentException)`. `request(Long.MAX_VALUE)` gần như bỏ giới hạn đếm item; chỉ dùng khi subscriber thực sự có thể xử lý liên tục theo đúng capacity. Không ép số byte muốn nhận thành giá trị `request(n)`.

### 10.4 Hết timeout khi đang streaming

`HttpRequest.Builder.timeout(Duration)` không phải một lời hứa rằng mọi callback `onNext` hoặc việc xử lý downstream kéo dài về sau đều tự bị giới hạn bởi cùng deadline. Khi dùng publishing body, response có thể đã được trả về sau headers nhưng body chưa hoàn tất. Thiết kế deadline tổng, tín hiệu cancel và chính sách phát hiện HTTP peer quá chậm/không gửi thêm dữ liệu nếu nghiệp vụ cần.

### 10.5 `onComplete` và tài nguyên

Khi subscriber đã yêu cầu đủ và nhận `onComplete`, body hoàn tất bình thường theo hợp đồng; nếu xảy ra lỗi thì dùng `onError`. Sau `cancel` có thể **không** có signal kết thúc. Bất kể đường đi nào, resource đích do ứng dụng sở hữu (tệp, connection DB, parser, executor) vẫn cần được giải phóng.

### 10.6 Giới hạn bộ nhớ và dữ liệu độc hại

`Flow` cung cấp backpressure theo item, **không phải** giới hạn tổng response bytes. Có thể từ chối response khi `Content-Length` vượt hạn mức, nhưng header có thể thiếu hoặc không đúng. Cần đếm bytes thực sự nhận trong `onNext`; nếu vượt hạn mức, hủy subscription và trả lỗi. Với archive, ảnh hoặc JSON, còn cần giới hạn sau giải nén/parse và kiểm soát CPU.

### 10.7 Thao tác đồng thời và thứ tự

`Flow` quy định signal tới một subscriber có trật tự; tuy nhiên không được giả định `onNext` chạy cùng thread gửi request. Nếu dùng executor khác để xử lý body, thứ tự xử lý/commit byte phải được bảo toàn. Các lỗi copy buffer và race giữa cancel/demand/close có thể làm dữ liệu bị cắt thiếu hoặc thất bại.

## 11. Checklist thực hành với `ofPublisher()`

1. **Có cần reactive demand thật không?** Nếu chỉ đọc text/file, cân nhắc handler đơn giản hơn.
2. **Khai báo đúng generic chưa?** `Flow.Publisher<List<ByteBuffer>>`, subscriber nhận `List<ByteBuffer>` chứ không chỉ `ByteBuffer`.
3. **Đã kiểm tra HTTP status và headers?** Không coi 4xx/5xx là exception tự phát.
4. **Đã subscribe đúng một lần?** Publisher từ `ofPublisher()` không được dùng để đăng ký nhiều consumer.
5. **`onSubscribe` có lưu subscription và gọi `request(n)` dương?** Tránh `n <= 0`.
6. **Đã nhận đúng mọi buffer trong mỗi list theo thứ tự chưa?** Không coi mỗi list là một byte hay một message.
7. **Mỗi lần yêu cầu tiếp có dựa vào capacity xử lý thực không?** Tránh queue vô hạn hoặc request vô hạn vô tình.
8. **Đã quản lý cả `onError` và `onComplete`?** Không chỉ quan sát future chứa `HttpResponse`.
9. **Nếu không dùng hết body, đã gọi `cancel` tường minh chưa?** Tránh giữ resource/HTTP connection vô hạn.
10. **Đã có chính sách khi cancel không tạo terminal event?** Chủ động hoàn tất promise và cleanup.
11. **Đã giới hạn tổng bytes, thời gian, idle và tải hệ thống?** Demand không thay thế policy an toàn.
12. **Nếu là text, đã xử lý charset và ký tự bị chia giữa buffer đúng cách chưa?**
13. **Có quản lý thread-safety và quyền sở hữu resource đích?** Callback không nhất thiết chạy trên main thread.
14. **Đã test response chậm, lỗi mạng, 404/500, hủy giữa chừng, subscriber thứ hai và thiếu demand?**

## 12. Những ngộ nhận phổ biến

| Ngộ nhận | Điều đúng theo API |
| --- | --- |
| “`send(..., ofPublisher())` nghĩa là tải xong toàn bộ response body.” | Trả response sau headers; body có thể chưa nhận hết |
| “`response.body()` là `byte[]`.” | Nó là `Flow.Publisher<List<ByteBuffer>>` |
| “`request(1)` nhận đúng một byte.” | Một item là **một list nhiều ByteBuffer**, có thể chứa nhiều byte |
| “Cứ tạo subscriber mà không `request` vẫn có data.” | Demand dương cần thiết để nhận `onNext` |
| “`request(0)` nghĩa là tạm dừng hợp lệ.” | Sai; `request(n <= 0)` gây `onError(IllegalArgumentException)` |
| “Publisher cho nhiều subscriber đọc lại body.” | `ofPublisher` chỉ hỗ trợ một subscriber |
| “Thêm `subscribe` lần hai thì nhận thêm dữ liệu.” | Lần hai bị từ chối `onError(IllegalStateException)` |
| “Không cần subscribe nếu chỉ xem status.” | Phải tiêu thụ/cancel publisher để dọn exchange |
| “Dừng request thêm là đã hủy resource.” | Phải `cancel()` nếu không muốn tiếp tục |
| “`cancel` luôn dẫn đến `onComplete`.” | Không; cancel là best effort và terminal event không bảo đảm |
| “Cứ `Long.MAX_VALUE` là có backpressure chặt.” | Gần như bỏ điều tiết số item phát |
| “Một `onNext` là một message JSON/text hoàn chỉnh.” | Boundary không phải ranh giới ứng dụng/UTF-8 |
| “`ofPublisher` tự parse JSON.” | Publisher chỉ phát byte; parser do ứng dụng xây |
| “Đã kiểm tra `Content-Length` là chắc chắn byte budget an toàn.” | Header có thể thiếu/sai; phải đếm thực tế |
| “Future của `sendAsync` hoàn tất là body đã consume xong.” | Future có thể chỉ báo response/publisher sẵn sàng |
| “Backpressure bảo đảm server ngừng gửi ngay.” | Còn network/OS/HTTP client buffering và cơ chế giao thức |

**Ghi nhớ cuối:** Với `BodyHandlers.ofPublisher()`, `HttpResponse.body()` là **publisher chỉ cho một subscriber**. Bên nhận phải `subscribe`, gọi `request(n)` để phát nhu cầu theo **số `List<ByteBuffer>`**, xử lý tuần tự các bytes, và kết thúc bằng `onComplete`/`onError` hoặc chủ động `cancel()` khi không tiếp tục. Đó là cách tận dụng streaming có backpressure mà không nhầm với giới hạn byte hay tự động hoàn tất download.

## Tài liệu tham khảo chính thức còn áp dụng

- [Oracle Java SE 11 — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofPublisher()` và thời điểm trả response.
- [Oracle Java SE 11 — `HttpResponse.BodySubscribers`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): publisher một subscriber, quy định subscribe/consume/cancel.
- [Oracle Java SE 11 — `HttpResponse.BodySubscriber<T>`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html): thứ tự `List<ByteBuffer>`, completion stage và Flow integration.
- [Oracle Java SE 11 — `Flow.Subscriber<T>`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html): `onSubscribe`, `onNext`, `onError`, `onComplete`.
- [Oracle Java SE 11 — `Flow.Subscription`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): `request(n)`, demand, `n <= 0` và `cancel()`.
- [Oracle Java SE 25 — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): mô tả API tiếp tục được hỗ trợ.
- [Oracle Java SE 25 — `HttpResponse.BodySubscribers`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): quy tắc dọn HTTP exchange và tái sử dụng connection.
- [Oracle Java SE 25 — `HttpClient`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html): vòng đời streaming/publishing body và shutdown tài nguyên.
- [Oracle Java SE 11 — module `jdk.httpserver`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/module-summary.html): test HTTP server nội bộ của ví dụ.

Bài học chỉ sử dụng cơ chế `Flow` và HTTP Client API đã có trong Java 11 và tiếp tục được hỗ trợ trên JDK hiện đại; không đưa các API incubator hoặc kỹ thuật legacy vào chương trình ví dụ.