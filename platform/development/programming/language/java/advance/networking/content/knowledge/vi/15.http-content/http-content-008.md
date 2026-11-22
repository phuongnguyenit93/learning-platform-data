# Flow.Publisher, Flow.Subscriber và nhu cầu nhận dữ liệu (backpressure) trong nội dung HTTP Java

Khi một HTTP server gửi response rất lớn, hoặc client cần upload dữ liệu theo nhiều phần, không nên mặc định **đọc toàn bộ body vào RAM rồi mới xử lý**. Java 17 cung cấp cơ chế điều phối lưu lượng theo nhu cầu qua `java.util.concurrent.Flow`. Trong đó, **`Flow.Publisher<T>` phát các phần tử**, **`Flow.Subscriber<T>` tiêu thụ**, còn **`Flow.Subscription.request(n)` cho biết subscriber cho phép nhận thêm bao nhiêu phần tử**. Cơ chế này gọi là **backpressure**: bên nhận chủ động thông báo mức dữ liệu có thể tiếp nhận, giúp bên phát không phải đẩy dữ liệu vô hạn vào hàng đợi.

Chủ đề này đặc biệt quan trọng trong **nội dung HTTP** với `java.net.http.HttpClient`:

- Phía **gửi request**: `HttpRequest.BodyPublisher` **kế thừa `Flow.Publisher<ByteBuffer>`**. HTTP client đăng ký subscriber vào publisher này để lấy các byte body đưa ra network.
- Phía **nhận response**: `HttpResponse.BodySubscriber<T>` **kế thừa `Flow.Subscriber<List<ByteBuffer>>`**. HTTP client phát các **danh sách buffer** body đến subscriber.
- `HttpResponse.BodyHandlers.ofPublisher()` cho phép ứng dụng nhận **`Flow.Publisher<List<ByteBuffer>>`** thay vì chờ toàn bộ response body thành một String/byte array, rồi đăng ký subscriber và điều tiết số lượng item đã yêu cầu.
- `HttpRequest.BodyPublishers.fromPublisher(...)` nối một `Flow.Publisher<ByteBuffer>` do ứng dụng cung cấp vào HTTP request body.

Bài học phân biệt nhu cầu theo **số item** và dung lượng thực tế **theo byte**, giải thích giao thức tín hiệu `onSubscribe/onNext/onError/onComplete`, xử lý `request(n)` và `cancel()`, cách tránh nghẽn khi publisher/subscriber chạy bất đồng bộ, và cách dùng streaming thật trong HTTP. Một chương trình Java 17+ hoàn chỉnh ở mục 8 chạy trên loopback, kiểm tra cả Flow thuần và request/response HTTP mà không cần Internet.

## 1. Vấn đề: bên phát nhanh, bên nhận chậm

Giả sử một HTTP response có 500 MB nhưng ứng dụng chỉ xử lý được 2 MB mỗi giây. Nếu HTTP client tích lũy toàn bộ 500 MB rồi mới trả `String` hoặc `byte[]`, nó có thể giữ lượng bộ nhớ rất lớn; nếu ứng dụng không đủ RAM, có thể gặp GC pressure hay `OutOfMemoryError`.

Với streaming, ứng dụng muốn thực hiện quy trình:

~~~text
HTTP server/network  ->  HttpClient  ->  downstream application
      gửi byte             nhận byte        giải mã / lưu file
          |                    |                    |
          |       Flow.Publisher<List<ByteBuffer>>  |
          |                    |                    |
          |                    +--- onSubscribe ---->|
          |                    |<-- request(1) ------+
          |                    +--- onNext(batch A) -> xử lý A
          |                    |<-- request(1) ------+
          |                    +--- onNext(batch B) -> xử lý B
          |                    |<-- request(1) ------+
          |                    ...
          |                    +--- onComplete() --->|
~~~

Bên tiêu thụ chủ động giới hạn **số lần gọi `onNext` còn được phép**, thay vì xin một số byte chính xác. Publisher hợp lệ không được phát `onNext` vượt quá nhu cầu đang còn. Khi downstream hoàn tất item, nó có thể cấp thêm demand.

**Lưu ý quan trọng:** Flow backpressure là **giao thức cấp ứng dụng giữa Publisher và Subscriber**. Nó không bảo đảm socket không còn byte nào trong kernel buffer, server ngừng gửi tức thì hoặc giảm bộ nhớ về 0: HTTP client, TCP/HTTP/2, proxy, OS và publisher vẫn có thể giữ buffer nội bộ. Tuy nhiên, nó giúp hạn chế việc đẩy item tới ứng dụng nhanh hơn mức ứng dụng đã chấp thuận.

## 2. Bốn giao diện quan trọng của java.util.concurrent.Flow

`Flow` có các giao diện lồng nhau:

| Interface | Vai trò | Phương thức đáng nhớ |
| --- | --- | --- |
| `Flow.Publisher<T>` | Nguồn phát item kiểu `T`; tạo subscription cho subscriber | `subscribe(Subscriber<? super T>)` |
| `Flow.Subscriber<T>` | Bên nhận, xử lý item và tín hiệu kết thúc | `onSubscribe`, `onNext`, `onError`, `onComplete` |
| `Flow.Subscription` | Liên kết điều khiển **một publisher–subscriber subscription** | `request(long n)`, `cancel()` |
| `Flow.Processor<T,R>` | Vừa nhận `T` như Subscriber, vừa phát `R` như Publisher | Kết hợp hai hướng, cần chuyển demand đúng |

Các giao diện này tương ứng với mô hình Reactive Streams. Một đối tượng Publisher có thể có một hay nhiều subscriber tùy implementation; **mỗi subscription có demand riêng**, không được chia lẫn số item được phép giữa các subscriber.

### 2.1. Vai trò và vòng đời Subscriber

Một vòng đời bình thường:

~~~text
Publisher.subscribe(subscriber)
      |
      v
subscriber.onSubscribe(subscription)
      |
      +--> subscription.request(n), với n > 0
               |
               v
          subscriber.onNext(item)  (0 hoặc nhiều lần,
               |                   không vượt demand)
               +--> request(m) nếu muốn nhận thêm
               |
               +--> subscriber.onComplete() khi hết nguồn
               |
               +--> hoặc subscriber.onError(cause) khi lỗi
~~~

Khi đã nhận tín hiệu kết thúc `onComplete` hoặc `onError`, subscription đó không được phát item tiếp. Hai tín hiệu terminal này **loại trừ nhau** trong luồng hợp lệ. `onSubscribe` phải đến trước item hoặc terminal signal cho subscription.

**Không gọi `onNext` trước `onSubscribe`**, không gọi `onNext(null)` nếu giao thức/implementation không chấp nhận null, không phát sau terminal. Publisher chịu trách nhiệm tuân thủ serialization/tín hiệu đúng; Subscriber cũng phải giữ sự phối hợp thread-safe nếu dùng chung state với ngoài callback.

### 2.2. Subscription.request(n) — số lượng item, không phải byte

`subscription.request(n)` **cộng thêm** `n` vào nhu cầu chưa đáp ứng của subscription. Nếu gọi liên tiếp `request(2)` rồi `request(3)`, tổng demand mới được cấp là 5 item trừ số đã nhận. Flow cho phép `Long.MAX_VALUE` như nhu cầu hiệu quả không giới hạn.

Ví dụ số học:

| Sự kiện | Demand còn hiệu lực |
| --- | ---: |
| Vừa subscribe, chưa request | 0 |
| Subscriber gọi `request(2)` | 2 |
| Publisher phát `onNext(A)` | 1 |
| Subscriber gọi `request(3)` | 4 |
| Publisher phát `onNext(B)` | 3 |
| Publisher phát `onNext(C)` | 2 |

Một lời gọi `request(2)` **không bắt buộc** Publisher phải phát chính xác hai item ngay: nếu không có dữ liệu, nếu đã kết thúc, hoặc có điều kiện scheduling, có thể nhận ít hơn. Publisher không được vượt hạn mức mà subscriber đã cho phép.

Gọi `request(0)` hoặc `request(-1)` là **không hợp lệ**: theo hợp đồng `Flow.Subscription`, subscriber sẽ được báo `onError(IllegalArgumentException)`. Không dùng `request(0)` như “tạm dừng”; muốn tạm dừng thì đơn giản **không yêu cầu thêm**.

### 2.3. Đề nghị một item một lần

Một cách dễ học là bắt đầu bằng `request(1)`, sau khi xử lý xong `onNext(item)` mới cấp thêm một item:

~~~java
// Fragment Java 17+, subscriber xử lý từng item kiểu String.
Flow.Subscriber<String> subscriber = new Flow.Subscriber<>() {
    private Flow.Subscription subscription;

    @Override
    public void onSubscribe(Flow.Subscription s) {
        subscription = s;
        s.request(1);
    }

    @Override
    public void onNext(String value) {
        process(value);         // Helper của ứng dụng.
        subscription.request(1); // Chỉ yêu cầu thêm sau khi xử lý.
    }

    @Override
    public void onError(Throwable error) {
        recordFailure(error);   // Helper của ứng dụng.
    }

    @Override
    public void onComplete() {
        markFinished();         // Helper của ứng dụng.
    }
};
~~~

Đây là **fragment**, không phải class chạy độc lập; `process/recordFailure/markFinished` phải được định nghĩa. Trong production, cần xử lý exception do `process` ném, giới hạn thời gian xử lý, cancellation và phối hợp thread. Nếu `process(value)` tốn nhiều thời gian, việc gọi trực tiếp trong `onNext` cũng có thể giữ thread dispatch của publisher; có thể chuyển xử lý sang bounded executor/queue và chỉ gọi `request(1)` **sau khi** item thực sự được tiêu thụ.

Ưu điểm của request(1) là đơn giản, dễ kiểm tra không vượt demand. Nhược điểm là nhiều vòng báo nhu cầu, overhead lớn hơn khi item nhỏ và tốc độ cao.

### 2.4. Request theo lô và refill

Với batch kích thước 8, có thể request 8 item ban đầu, sau khi xử lý 4 item thì request thêm 4. Bằng cách đó, outstanding demand được giữ trong khoảng gần 4–8 item trong điều kiện liên tục phát/tiêu thụ:

~~~java
// Fragment: cùng subscription, callback được gọi theo thứ tự.
private static final int WINDOW = 8;
private Flow.Subscription subscription;
private int handledSinceRefill;

@Override
public void onSubscribe(Flow.Subscription s) {
    subscription = s;
    s.request(WINDOW);
}

@Override
public void onNext(Item item) {
    consume(item); // Helper phải hoàn thành hoặc có cơ chế ack nội bộ.
    if (++handledSinceRefill == WINDOW / 2) {
        handledSinceRefill = 0;
        subscription.request(WINDOW / 2);
    }
}
~~~

Đây là **mẫu thuật toán**, không phải một file Java có thể biên dịch riêng (cần class `Item` và `consume`). Cần chọn window theo số lượng item, kích thước trung bình/lớn nhất, dung lượng queue, CPU/I/O downstream và deadline. Đừng tối ưu mỗi số lời gọi request mà bỏ qua memory budget.

**Một subscription không tự động biến item thành byte:** nếu mỗi item là 1 KB, demand 8 gần 8 KB payload; nếu mỗi item là 8 MB, demand 8 có thể đưa vào downstream tới 64 MB cộng overhead. Vì vậy backpressure theo item không đủ để áp một **byte limit** chắc chắn nếu item có kích thước biến thiên.

## 3. Cancel và tín hiệu kết thúc: không giống nhau

`Subscription.cancel()` yêu cầu Publisher **cuối cùng ngừng gửi**. Theo Javadoc, đây là **best-effort**; một số tín hiệu đã lên lịch có thể vẫn xuất hiện sau lúc gọi cancel. Một subscription bị hủy **không bắt buộc** phát `onComplete` hoặc `onError`.

So sánh:

| Hành động | Ai khởi tạo | Ý nghĩa |
| --- | --- | --- |
| `request(n>0)` | Subscriber | Cho phép nhận thêm n item |
| `cancel()` | Subscriber | Không muốn nhận thêm; Publisher cố gắng dừng |
| `onComplete()` | Publisher | Kết thúc bình thường của nguồn phát |
| `onError(Throwable)` | Publisher | Kết thúc vì lỗi |
| `close()` trên `SubmissionPublisher` | Nguồn phát | Ngừng nhận submit mới; truyền completion tới subscriber hiện hữu sau dữ liệu đã nhận |

Một subscriber muốn bỏ response HTTP có thể gọi `cancel()`, nhưng điều này có thể khiến underlying HTTP connection **không còn tái sử dụng được**. Do đó phải xác định chính sách: **đọc hết body tới onComplete/onError** hoặc chủ động cancel và chấp nhận chi phí đóng connection.

Không dùng `cancel()` như một tín hiệu rằng server chắc chắn đã dừng phát, transaction từ xa đã rollback hoặc toàn bộ data trong các queue đã được xóa. Đối với tác vụ nghiệp vụ có side effects, cần protocol/cơ chế riêng để xác định trạng thái.

## 4. SubmissionPublisher: một nguồn dữ liệu có backpressure sẵn trong JDK

`java.util.concurrent.SubmissionPublisher<T>` là implementation cơ bản của `Flow.Publisher<T>` từ Java 9. Nó thường dùng Executor để phân phối tín hiệu bất đồng bộ và có buffer riêng theo subscriber, với giới hạn dung lượng cấu hình.

~~~java
// Fragment Java 17+, dùng được trong ứng dụng với vòng đời Executor.
ExecutorService executor = Executors.newSingleThreadExecutor();

try (SubmissionPublisher<String> publisher =
         new SubmissionPublisher<>(executor, 8)) {

    publisher.subscribe(subscriber); // Subscriber<String> do ứng dụng định nghĩa.

    publisher.submit("A");
    publisher.submit("B");
    publisher.close();
} finally {
    executor.shutdownNow();
}
~~~

Đoạn này chỉ minh họa cách khởi tạo, **không** phải một chương trình độc lập: chưa có `subscriber` hay chờ asynchronous completion. Với workload thật, việc shutdown executor **ngay sau khi close** có thể làm callback chưa được phân phối xong. Trong chương trình hoàn chỉnh mục 8, code đợi `CountDownLatch` báo complete trước khi shutdown.

### submit() và offer() khác nhau

- `submit(item)` phát cho các subscriber hiện tại theo cơ chế của SubmissionPublisher; khi **buffer của một subscriber đã đầy**, lời gọi có thể **block** để chờ tài nguyên. Điều đó là **backpressure lên producer**, không phải lời hứa non-blocking.
- `offer(item, ...)` hỗ trợ hành vi xử lý khi không đủ chỗ (ví dụ drop hoặc retry có kiểm soát), có biến thể timeout. Nếu drop một item trong chuỗi dữ liệu HTTP body, bạn có thể làm hỏng nội dung request/response; **không dùng drop như cách mặc định cho body byte stream**.
- Giá trị `submit` trả về là **ước lượng lag** giữa các subscriber, không phải số item đã được phát tới HTTP peer hay byte thực sự đã đi ra mạng.
- `SubmissionPublisher.close()` không đồng nghĩa mọi subscriber đã xử lý xong. Đợi tín hiệu `onComplete` hoặc một Future/latch kiểm tra ở downstream nếu cần xác nhận pipeline kết thúc.

Ví dụ nghẽn: producer gửi 1.000 item rất nhanh, subscriber chỉ `request(1)` mỗi vài giây, buffer giới hạn 8. Ban đầu các item có thể vào queue, nhưng khi queue đầy, `submit` có thể block. Nếu producer và consumer dispatch **chung một thread** mà thread đó lại block trong `submit`, có nguy cơ deadlock/starvation. Vì vậy, chọn executor/queue/cơ chế điều tiết đúng.

**Không nhầm buffer capacity với demand:** publisher có thể có queue nội bộ ngay cả khi subscriber chưa request item nào. Backpressure giới hạn phát tới subscriber chứ không tự bảo đảm dữ liệu upstream không bao giờ được buffer.

## 5. HTTP request: BodyPublisher là Flow.Publisher<ByteBuffer>

Với Java 17, `HttpRequest.BodyPublisher` có chữ ký kế thừa như sau:

~~~java
// Ý tưởng API từ java.net.http; không phải file Java chạy độc lập.
interface BodyPublisher extends Flow.Publisher<ByteBuffer> {
    long contentLength();
}
~~~

Đây là chữ ký **rút gọn** để nhấn mạnh quan hệ kiểu. Một BodyPublisher có hai trách nhiệm: cung cấp byte dữ liệu qua Flow và công bố chiều dài body khi biết. HttpClient là subscriber của request BodyPublisher.

Có các factory phổ biến:

~~~java
// Fragment minh họa, không gửi mạng trong đoạn này.
HttpRequest.BodyPublisher text =
        HttpRequest.BodyPublishers.ofString("Hello", StandardCharsets.UTF_8);

HttpRequest.BodyPublisher binary =
        HttpRequest.BodyPublishers.ofByteArray(new byte[] {1, 2, 3});

HttpRequest.BodyPublisher empty =
        HttpRequest.BodyPublishers.noBody();

HttpRequest.BodyPublisher streamed =
        HttpRequest.BodyPublishers.ofInputStream(() -> openInputStream());
~~~

`ofString` và `ofByteArray` thường phù hợp payload nhỏ; `ofFile(Path)` hoặc `ofInputStream(Supplier<InputStream>)` thích hợp khi không muốn giữ toàn bộ body trong String/byte[]. Đối với supplier dạng InputStream, hãy tạo **stream mới cho mỗi lần được yêu cầu** nếu client cần thử lại request; một InputStream đã đọc hết thường không thể phát lại an toàn. `openInputStream()` trong fragment là helper do ứng dụng cung cấp, không phải API JDK.

### 5.1. Adapter fromPublisher

Nếu đã có một `Flow.Publisher<ByteBuffer>`:

~~~java
// Fragment: publisher do ứng dụng cung cấp, bytes thực phải khớp.
Flow.Publisher<ByteBuffer> source = makeByteBufferPublisher();

HttpRequest.BodyPublisher unknownLength =
        HttpRequest.BodyPublishers.fromPublisher(source);

HttpRequest.BodyPublisher knownLength =
        HttpRequest.BodyPublishers.fromPublisher(source, 1_024);
~~~

- `fromPublisher(source)` đặt `contentLength() == -1` (không biết chiều dài). HTTP/1.1 có thể dùng một dạng framing như chunked transfer; HTTP/2 có cơ chế framing riêng. Đừng tự chèn `Content-Length` giả.
- `fromPublisher(source, contentLength)` yêu cầu **số byte dương chính xác**. Chỉ dùng khi có thể đảm bảo nguồn sẽ phát đúng số byte đó, không thừa, không thiếu.
- Nếu body **rỗng**, dùng `BodyPublishers.noBody()` thay cho known length 0 ở overload có chiều dài, vì Javadoc quy định độ dài truyền vào overload này phải **dương**.
- `BodyPublisher.contentLength()` có thể được hỏi nhiều lần và phải trả **một giá trị cố định** giữa các lần hỏi; đừng để nó phụ thuộc trạng thái còn bao nhiêu byte đã đọc.

HttpClient có thể **subscribe lại** request BodyPublisher khi cần gửi lại request (theo chính sách redirect/authentication/retry). Publisher phải có khả năng tạo một sequence mới **tương đương** cho từng subscription. Một `SubmissionPublisher` hot đã phát dữ liệu trước khi HttpClient subscribe **không tự replay** các item đó; dùng trực tiếp nó làm nguồn upload có thể làm mất phần body hoặc không hỗ trợ gửi lại. Trong ứng dụng thực, thường chọn publisher **cold/replayable** hoặc cơ chế dữ liệu có thể mở lại.

### 5.2. Quyền sở hữu ByteBuffer phía request

Javadoc `HttpRequest.BodyPublisher` yêu cầu các `ByteBuffer` được publisher cấp phát cho mỗi lượt phát và **không được publisher truy cập/sửa sau khi publish tới HTTP Client**. Không gửi cùng một ByteBuffer mutable rồi tiếp tục gọi `put/clear/flip` trên thread khác:

~~~java
// Sai về ownership: một buffer mutable được sửa sau khi publish.
ByteBuffer shared = ByteBuffer.allocate(1024);
// publisher.onNext(shared);    // Ví dụ phương thức giả định.
shared.clear();                 // HTTP client có thể chưa tiêu thụ xong.
~~~

Đoạn trên là **anti-pattern mô tả**, không phải class chạy độc lập. Trong một Publisher đúng, mỗi subscription có state độc lập; khi phát, tạo buffer hợp lệ rồi giao quyền đọc cho HttpClient. Nếu nguồn dữ liệu chia sẻ còn có thể thay đổi, copy bytes hoặc thiết kế ownership rõ ràng. Đừng cho publisher tự sửa buffer sau publication.

### 5.3. POST streaming qua Flow

~~~java
// Fragment Java 17+; uri và Flow.Publisher<ByteBuffer> source có sẵn.
HttpRequest upload = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.fromPublisher(source))
        .build();

HttpResponse<Void> response = client.send(
        upload, HttpResponse.BodyHandlers.discarding());
~~~

Đoạn này chưa chạy độc lập vì `uri/source/client` là thành phần của ứng dụng. `send` đồng bộ **đợi HttpResponse theo BodyHandler**, còn publisher được HTTP client subscribe và điều phối theo demand. Việc có Flow không làm đoạn code calling `send` tự trở thành asynchronous đối với luồng gọi. Có thể dùng `sendAsync` để client thread không phải đợi, với quản lý lỗi/timeout/cancellation tương ứng.

**Content-Type vẫn phải đúng**: publisher chỉ phát bytes. Nếu bytes là JSON, dùng `Content-Type: application/json` theo API; nếu là binary, dùng `application/octet-stream` hoặc media type được thỏa thuận. Flow không tự động serialization JSON hoặc bảo đảm server chấp nhận method.

## 6. HTTP response: BodySubscriber nhận List<ByteBuffer>, không phải một ByteBuffer

Chữ ký rất quan trọng:

~~~java
// Ý tưởng API từ java.net.http, chỉ để minh họa generics.
interface BodySubscriber<T>
        extends Flow.Subscriber<List<ByteBuffer>> {
    CompletionStage<T> getBody();
}
~~~

Ở phía **nhận response**, HttpClient là nguồn dữ liệu và BodySubscriber là bên tiêu thụ. Nhưng item kiểu **`List<ByteBuffer>`**, không phải `ByteBuffer` đơn lẻ. Mỗi `onNext(batch)` có thể chứa **một hoặc nhiều** buffer. Theo Javadoc Java 17, các danh sách là **unmodifiable** và các ByteBuffer là **read-only**, thứ tự các buffer tương ứng thứ tự byte của response.

Do đó:

~~~java
// Fragment cho Flow.Subscriber<List<ByteBuffer>>.
@Override
public void onNext(List<ByteBuffer> batch) {
    for (ByteBuffer buffer : batch) {
        byte[] chunk = new byte[buffer.remaining()];
        buffer.get(chunk); // ĐỌC hợp lệ dù buffer read-only.
        processBytes(chunk); // Helper ứng dụng.
    }
    subscription.request(1);
}
~~~

`buffer.get(chunk)` đọc byte và di chuyển position của buffer cục bộ. `buffer.put(...)` có thể ném `ReadOnlyBufferException`. Nếu cần truyền buffer qua một pipeline asynchronous khác, hãy giữ rõ ownership và thời hạn sống, hoặc copy lượng byte cần thiết; Javadoc đảm bảo HttpClient không tái sử dụng các list/buffer đã giao, nhưng code nghiệp vụ vẫn phải đồng bộ việc dùng state chia sẻ.

### 6.1. BodyHandlers.ofPublisher()

Một lựa chọn streaming:

~~~java
// Fragment Java 17+, client và request đã khởi tạo.
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.send(request, HttpResponse.BodyHandlers.ofPublisher());

Flow.Publisher<List<ByteBuffer>> bodyPublisher = response.body();
// PHẢI subscribe đúng một lần và đọc hết hoặc cancel.
bodyPublisher.subscribe(mySubscriber);
~~~

Với `ofPublisher()`, `HttpResponse` có thể trả về **ngay sau khi response headers đã được đọc**, trong khi response body **vẫn đang được truyền**. Publisher này **chỉ được subscribe một lần**. Lần subscribe thứ hai sẽ nhận `onError(IllegalStateException)` theo hợp đồng JDK; không coi nó là nguồn replayable cho nhiều consumer.

Để giải phóng tài nguyên của HTTP exchange, phải **đăng ký đúng một subscriber** rồi hoặc:
- yêu cầu dữ liệu đến `onComplete/onError`, hoặc
- gọi `Subscription.cancel()` khi thật sự không cần phần còn lại.

**Đừng lấy `client.send(..., ofPublisher())` trả về làm bằng chứng body đã đọc hết.** Status/headers đã có, nhưng callback `onNext` tiếp tục về sau. Nếu bạn quên subscribe hoặc subscribe nhưng không request item nào, exchange có thể giữ tài nguyên lâu. Với HTTP/1.1, cancel giữa body có thể khiến connection bị đóng và không được tái sử dụng; với HTTP/2, việc hủy stream phụ thuộc protocol và implementation.

### 6.2. Nhu cầu request(1) ở đây đếm cái gì?

Đối với `BodyHandlers.ofPublisher()`:

~~~text
subscription.request(1)
    |
    +--> Cho phép tối đa 1 lần onNext(List<ByteBuffer>)
            |
            +--> batch có thể gồm buffer 1 (512 bytes)
            +--> batch có thể gồm buffer 2 (2048 bytes)
            +--> ... tổng byte không cố định
~~~

Do đó `request(1)` **không có nghĩa chỉ cho nhận một byte hoặc đúng một network packet**. HTTP/1.1 chunk, HTTP/2 frame, socket read, `ByteBuffer` và Flow item có ranh giới **không nhất thiết trùng nhau**. Không parse JSON, UTF-8 hoặc message boundary riêng biệt bằng cách giả định một `onNext` = một message.

Nếu body dùng UTF-8, một ký tự đa byte có thể bị chia giữa các buffer. Khi nhận từng buffer, hãy dùng `CharsetDecoder` incremental hoặc tích lũy số byte hợp lý tới khi có một đơn vị mã hóa hoàn chỉnh; đừng gọi `new String(chunk, UTF_8)` độc lập trên mọi chunk rồi nối lại nếu encoding có thể bị tách giữa chừng.

### 6.3. BodyHandlers.ofString/ofByteArray/ofFile/ofInputStream

| BodyHandler | Kiểu `response.body()` | Đặc điểm tài nguyên |
| --- | --- | --- |
| `ofString()` | `String` | Thường tích lũy toàn bộ body trước khi trả, thuận tiện response nhỏ |
| `ofByteArray()` | `byte[]` | Tích lũy toàn bộ bytes, dễ tốn heap với response lớn |
| `ofFile(path)` | `Path` | Ghi body ra tệp, giảm nhu cầu giữ toàn bộ body trong byte[] |
| `ofInputStream()` | `InputStream` | Cung cấp stream để caller đọc về sau, phải đọc hết hoặc close |
| `ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Caller quản lý Flow subscriber, demand và completion/cancel |
| `discarding()` | `Void` | Đọc rồi bỏ body theo chính sách handler, không lưu nội dung |

**Chọn đơn giản trước:** tải một JSON vài KB thì `ofString()` hợp lý. Tải file nhiều GB có thể dùng `ofFile(path)` thay vì tự viết subscriber. `ofPublisher()` hữu ích khi cần pipeline transform/parse trực tuyến, điều phối mức tải, hoặc tích hợp Flow downstream. Không chọn Flow chỉ để làm code phức tạp hơn.

### 6.4. BodySubscriber.getBody() và CompletionStage

`HttpResponse.BodySubscriber<T>` cung cấp `CompletionStage<T> getBody()`. Thời điểm stage hoàn thành phụ thuộc **kiểu T và subscriber**:

- Nếu `T` là `String` hoặc `byte[]` tích lũy toàn bộ, stage thường chỉ hoàn thành sau khi body được nhận và chuyển đổi xong.
- Nếu `T` là kiểu streaming như `InputStream` hoặc `Publisher<...>`, stage có thể hoàn thành **trước khi toàn bộ body được đọc**, bởi caller cần dùng stream/publisher để tiếp tục xử lý.

Đừng nhầm “CompletableFuture<HttpResponse<Publisher<...>>> đã complete” với “đã nhận đủ response body”. Phải quản lý completion của subscriber riêng nếu nghiệp vụ cần biết dữ liệu đã đi qua xử lý hay chưa.

## 7. Ví dụ tương tác HTTP Flow đúng và sai

### 7.1. Subscriber không request dữ liệu: phản hồi dừng ở phía ứng dụng

~~~java
// Anti-pattern: không ai gọi request() sau onSubscribe.
public void onSubscribe(Flow.Subscription s) {
    this.subscription = s;
    // Không request(1), nên không có demand cho onNext.
}
~~~

Publisher tuân thủ Flow không phát `onNext` nếu không có demand. Nếu chờ dữ liệu trong khi không hề request, ứng dụng tự tạo trạng thái đứng. Không sửa bằng `Thread.sleep()`; phải cấp nhu cầu hoặc quyết định cancel.

### 7.2. Request Long.MAX_VALUE: bỏ kiểm soát demand

~~~java
// Có thể đúng cho nguồn nhỏ, nhưng bỏ giới hạn ở tầng Flow.
public void onSubscribe(Flow.Subscription s) {
    this.subscription = s;
    s.request(Long.MAX_VALUE);
}
~~~

Đây là nhu cầu hiệu quả không giới hạn. Khi một subscriber chậm nhưng được cấp rất nhiều item trước, downstream có thể bị overload nếu publisher/adapter tiếp tục phát nhanh hoặc stage trung gian lưu queue. Nên chọn window dựa trên memory budget; dù vậy, `request(1)` cũng không đủ ràng buộc số byte nếu mỗi item lớn.

### 7.3. Lưu toàn bộ vào ByteArrayOutputStream: demo hợp lệ, không bounded memory

~~~java
// Fragment trong onNext; CHỈ phù hợp body nhỏ có giới hạn.
for (ByteBuffer part : batch) {
    byte[] bytes = new byte[part.remaining()];
    part.get(bytes);
    collector.write(bytes, 0, bytes.length);
}
subscription.request(1);
~~~

Dù request một batch một lần, `ByteArrayOutputStream` **vẫn tăng vô hạn theo tổng response size**. Đây **không** phải xử lý streaming bounded-memory ở tầng ứng dụng. Chương trình chạy độc lập mục 8 cố ý tích lũy một response 10 byte để chứng minh API; khi áp dụng thật cho file lớn, cần ghi ra sink có giới hạn hoặc xử lý trực tuyến rồi bỏ bytes đã xử lý.

### 7.4. Chuyển việc nặng ra worker queue cần giữ backpressure

Nếu `onNext` chỉ `queue.offer(batch)` rồi ngay lập tức `request(1)` mà queue không giới hạn, upstream vẫn đẩy nhanh hơn consumer và memory tăng. Mẫu tốt hơn:

~~~text
onNext(batch)
    |
    +--> validate size, copy/transfer data sang BOUNDED work queue
    |
    +--> worker xử lý xong batch (ack)
              |
              +--> nếu chưa cancelled và còn capacity:
                         subscription.request(1)
              |
              +--> nếu xử lý lỗi:
                         cancel / fail pipeline / cleanup
~~~

Một queue hữu hạn có thể cần từ chối/đợi/thực hiện backpressure bổ sung; đừng block mãi trong callback nếu thread đó cũng có trách nhiệm tiêu thụ queue, vì có thể deadlock. Cần serial hóa hoặc đồng bộ các lần request/cancel và close để tránh race khi nhiều worker hoàn tất đồng thời.

## 8. Chương trình Java 17+ chạy độc lập: Flow + HTTP streaming

Chương trình **`FlowHttpDemo.java`** có hai phần kiểm thử rõ ràng:

1. **Flow thuần:** `SubmissionPublisher<String>` cùng một subscriber dùng `request(1)`, nhận A rồi B và kết thúc. Dùng `CountDownLatch` đợi callback để việc in stdout có thứ tự.
2. **HTTP loopback:** server local bằng `com.sun.net.httpserver.HttpServer` có route `/data` trả `HELLO-FLOW` và route `/upload` echo bytes của POST. Client dùng `BodyHandlers.ofPublisher()` để đọc response GET qua `Flow.Subscriber<List<ByteBuffer>>`, và dùng `BodyPublishers.fromPublisher(...)` để upload bốn byte `PING`.

Điểm học quan trọng ở ví dụ HTTP là custom request publisher tạo **subscription mới** cho mỗi lần subscribe, trả ByteBuffer mới và không truy cập buffer sau publication. Như vậy không dùng một nguồn nóng đã mất dữ liệu trước khi HttpClient kịp subscribe.

**Lưu toàn bộ mã dưới đây vào tệp `FlowHttpDemo.java`:**

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
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public class FlowHttpDemo {
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;
    private static final long SECONDS = 5;

    private static void flowExample() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<Throwable> error = new AtomicReference<>();

        try (SubmissionPublisher<String> publisher =
                     new SubmissionPublisher<>(executor, 8)) {

            publisher.subscribe(new Flow.Subscriber<String>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    System.out.println("flowSubscribed");
                    s.request(1);
                }

                @Override
                public void onNext(String item) {
                    System.out.println("flowNext=" + item);
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable throwable) {
                    error.set(throwable);
                    done.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("flowComplete");
                    done.countDown();
                }
            });

            publisher.submit("A");
            publisher.submit("B");
            publisher.close();

            if (!done.await(SECONDS, TimeUnit.SECONDS)) {
                throw new TimeoutException("Flow did not finish");
            }
            if (error.get() != null) {
                throw new IllegalStateException(
                        "Flow failed", error.get());
            }
        } finally {
            executor.shutdownNow();
        }
    }

    // HTTP response server-side; chỉ dùng cho local demo.
    private static void reply(HttpExchange exchange, String text)
            throws IOException {
        byte[] body = text.getBytes(UTF8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(200, body.length);

        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body);
        }
    }

    // Cold/replayable Publisher: mỗi subscription có buffer riêng.
    // Chỉ dành cho payload nhỏ 4 byte trong demo, không phải
    // implementation đa chunk/đa consumer production.
    private static Flow.Publisher<ByteBuffer> singleChunk(
            byte[] source) {
        byte[] content = source.clone();

        return subscriber -> subscriber.onSubscribe(
                new Flow.Subscription() {
            private boolean terminated;

            @Override
            public synchronized void request(long n) {
                if (terminated) {
                    return;
                }
                terminated = true;

                if (n <= 0) {
                    subscriber.onError(new IllegalArgumentException(
                            "positive demand required"));
                    return;
                }

                // Mỗi subscribe tạo mảng/buffer mới.
                // Sau onNext, Publisher không được sửa nó nữa.
                subscriber.onNext(
                        ByteBuffer.wrap(content.clone())
                                .asReadOnlyBuffer());
                subscriber.onComplete();
            }

            @Override
            public synchronized void cancel() {
                terminated = true;
            }
        });
    }

    private static void httpExample() throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);

        server.createContext("/data", exchange -> {
            try (InputStream ignored = exchange.getRequestBody()) {
                reply(exchange, "HELLO-FLOW");
            }
        });

        server.createContext("/upload", exchange -> {
            byte[] body;
            try (InputStream in = exchange.getRequestBody()) {
                body = in.readAllBytes();
            }
            reply(exchange,
                    exchange.getRequestMethod() + ":"
                            + new String(body, UTF8));
        });

        server.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpRequest get = HttpRequest.newBuilder(
                    URI.create(base + "/data"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            // HttpResponse chứa publisher body, không phải String.
            HttpResponse<Flow.Publisher<List<ByteBuffer>>> download =
                    client.send(
                            get,
                            HttpResponse.BodyHandlers.ofPublisher());

            CountDownLatch done = new CountDownLatch(1);
            AtomicReference<Throwable> failure =
                    new AtomicReference<>();
            ByteArrayOutputStream bytes =
                    new ByteArrayOutputStream();

            download.body().subscribe(
                    new Flow.Subscriber<List<ByteBuffer>>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    s.request(1); // Một LIST mỗi lượt, không phải 1 byte.
                }

                @Override
                public void onNext(List<ByteBuffer> batch) {
                    for (ByteBuffer buffer : batch) {
                        byte[] chunk = new byte[buffer.remaining()];
                        buffer.get(chunk);
                        bytes.write(chunk, 0, chunk.length);
                    }
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    failure.set(error);
                    done.countDown();
                }

                @Override
                public void onComplete() {
                    done.countDown();
                }
            });

            if (!done.await(SECONDS, TimeUnit.SECONDS)) {
                throw new TimeoutException(
                        "HTTP body did not finish");
            }
            if (failure.get() != null) {
                throw new IOException(
                        "HTTP response body failed", failure.get());
            }

            System.out.println(
                    "downloadStatus=" + download.statusCode());
            System.out.println(
                    "downloadText="
                            + new String(bytes.toByteArray(), UTF8));

            // Tạo body publisher từ một nguồn Flow tái subscribe được.
            byte[] payload = "PING".getBytes(UTF8);
            HttpRequest post = HttpRequest.newBuilder(
                    URI.create(base + "/upload"))
                    .timeout(Duration.ofSeconds(5))
                    .header(
                            "Content-Type",
                            "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.fromPublisher(
                            singleChunk(payload), payload.length))
                    .build();

            HttpResponse<String> upload = client.send(
                    post,
                    HttpResponse.BodyHandlers.ofString(UTF8));

            System.out.println(
                    "uploadStatus=" + upload.statusCode());
            System.out.println(
                    "uploadText=" + upload.body());

        } finally {
            server.stop(0);
        }
    }

    public static void main(String[] args) throws Exception {
        flowExample();
        httpExample();
    }
}
~~~

**Biên dịch/chạy với JDK 17+** (không cần thư viện bên ngoài):

~~~bash
javac FlowHttpDemo.java
java FlowHttpDemo
~~~

Chương trình dùng module JDK `jdk.httpserver`. Trong cấu hình module-path tự quản lý, có thể cần `--add-modules jdk.httpserver` ở lệnh biên dịch/chạy; classpath/unnamed module của bản JDK chuẩn thường tự resolve module này.

**Đầu ra kiểm chứng với JDK/JShell trên loopback**:

~~~text
flowSubscribed
flowNext=A
flowNext=B
flowComplete
downloadStatus=200
downloadText=HELLO-FLOW
uploadStatus=200
uploadText=POST:PING
~~~

### Diễn giải chi tiết

- `flowSubscribed` đến trước dữ liệu. Subscriber gọi `request(1)` rồi lần lượt nhận A, B. Sau mỗi item, subscriber cấp thêm một quyền nhận. `SubmissionPublisher.close()` kích hoạt kết thúc sau các item đã được phân phối; `CountDownLatch` đảm bảo main chỉ đi tiếp khi hoàn thành.
- HTTP GET trả `statusCode()==200` và body Publisher; subscriber của ứng dụng dùng `request(1)` trên **List<ByteBuffer>**. Dù HTTP client chia `HELLO-FLOW` thành bao nhiêu list/chunk, code nối **bytes theo đúng thứ tự** rồi mới giải mã UTF-8, nên không phụ thuộc chunking mạng.
- `singleChunk(payload)` tạo Flow source mới cho từng subscription. Vì payload dài 4 byte, `fromPublisher(..., payload.length)` có content length đúng 4. Server echo method cùng body thành `POST:PING`.
- Hai endpoint chỉ chạy trên `127.0.0.1` và port ngẫu nhiên để không cần Internet/API key. `HttpServer` chỉ echo/đưa dữ liệu cố định; **không phải server production**.
- Program cố ý dùng `ByteArrayOutputStream` để dễ in response 10 byte; **không được suy luận demo download có bộ nhớ bounded cho response bất kỳ**. Với file lớn, dùng `BodyHandlers.ofFile()` hoặc thiết kế streaming sink có hạn mức và cơ chế cấp demand sau khi sink hoàn tất.

**Về số chunk:** demo không in số lần `onNext`, bởi HTTP client có thể phân chia `List<ByteBuffer>` khác nhau tùy runtime/protocol/network. Đầu ra chỉ dựa trên body đã ghép và status, là những quan sát đáng tin hơn trong môi trường kiểm thử loopback bình thường.

### Lưu ý về request Publisher của demo

`singleChunk` là ví dụ tối giản cho **đúng một item duy nhất**: một request(n>0) cho phép gửi item đó rồi complete. Nó không đại diện cho mọi vấn đề của publisher tổng quát như phát nhiều batch, đồng bộ callback đa thread, stream từ disk, retry, cancel race hay giới hạn thời gian. Production nên dùng các `BodyPublishers` có sẵn hoặc thư viện đã tuân thủ Reactive Streams và kiểm chứng tính replayable.

Mặc dù `request(n)` trong demo có thể phát ngay trên thread gọi request, chương trình vẫn hợp lệ với ý tưởng subscription một item. Điều này cũng minh họa vì sao custom publisher phải **chịu được reentrancy**; không mặc định mọi signal luôn chạy ở thread executor tách biệt. Publisher phức tạp cần serialize signal và tránh giữ lock khi gọi user callback để giảm nguy cơ deadlock.

## 9. Ví dụ subscriber streaming đúng nghĩa với bounded sink

Để không tích lũy cả body vào heap, nên xử lý từng batch rồi bỏ bytes đã xử lý. Một phương án tải file là dùng `BodyHandlers.ofFile(path)`; không cần tự quản lý Flow. Nếu bài toán cần custom transform/parser, phải xác định điều gì xảy ra khi downstream chậm.

Giả sử ứng dụng ghi body vào một file output stream với giới hạn tổng 20 MB:

~~~java
// Fragment trong một Flow.Subscriber<List<ByteBuffer>>;
// cần có OutputStream out mở sẵn, Flow.Subscription subscription,
// long totalBytes, boolean terminal và helper cleanup.
private static final long MAX_BYTES = 20L * 1024 * 1024;

@Override
public void onNext(List<ByteBuffer> batch) {
    try {
        for (ByteBuffer part : batch) {
            int n = part.remaining();
            if (totalBytes + n > MAX_BYTES) {
                subscription.cancel();
                closeOutputAndReportTooLarge();
                return;
            }
            byte[] chunk = new byte[n];
            part.get(chunk);
            out.write(chunk);
            totalBytes += n;
        }
        // Sau khi downstream write của batch hoàn tất.
        subscription.request(1);
    } catch (IOException error) {
        subscription.cancel();
        closeOutputAndReportFailure(error);
    }
}
~~~

Đây là **fragment**, không phải class biên dịch độc lập; `closeOutputAndReportTooLarge/Failure` là helper ứng dụng. `totalBytes + n` phải xử lý tràn số nguyên nếu không có giới hạn n hợp lý; có thể kiểm tra dạng `n > MAX_BYTES - totalBytes` an toàn hơn. Mọi đường kết thúc `onComplete/onError/cancel` phải đóng output đúng một lần; xử lý exception trong callback và không request tiếp sau cancel.

**Quan trọng:** `out.write(chunk)` là thao tác **blocking**. Nếu gọi trực tiếp trong onNext của HTTP client với tệp/network sink chậm, callback có thể giữ thread dispatch và ảnh hưởng các exchange khác. Giải pháp tùy yêu cầu: dùng `BodyHandlers.ofFile(path)`, dùng bounded worker queue với ack trước request tiếp, hoặc thiết kế asynchronous sink có ownership chính xác.

Khi chuyển dữ liệu sang queue worker, không nên đưa thẳng những `ByteBuffer` mutable đang được đổi position đồng thời ở hai thread. Trong Java HttpClient, buffer nhận là read-only nên không thể ghi, nhưng position của từng object vẫn là mutable; tránh nhiều thread cùng gọi `get` trên cùng instance mà không phối hợp. Dùng `asReadOnlyBuffer()` để tạo view position độc lập hoặc copy byte theo giới hạn nếu cần.

## 10. Nhu cầu số item không thay thế được hạn mức tài nguyên

Giả sử HTTP response publisher phát `List<ByteBuffer>`, mỗi batch có thể chứa nhiều buffers với tổng byte thay đổi:

| Demand | Giả định batch size | Byte tối đa từ chính các item được cấp demand |
| --- | --- | --- |
| `request(1)` | 1 batch, 2 KB | Khoảng 2 KB cho batch đó |
| `request(1)` | 1 batch, 512 KB | Khoảng 512 KB cho batch đó |
| `request(8)` | 8 batch, mỗi batch 1 MB | Có thể tới khoảng 8 MB |
| `request(Long.MAX_VALUE)` | Không giới hạn số item | Không có byte budget từ Flow demand |

Các kích thước chỉ là **giả định để tính minh họa**, không phải hứa hẹn HttpClient sẽ phát batch có kích thước như vậy. Mỗi stage cần kiểm soát thêm:

- **Số bytes mỗi item:** giới hạn payload lớn bất thường.
- **Tổng bytes của response:** kiểm tra `Content-Length` nếu có nhưng không hoàn toàn tin header; đếm bytes thật nhận.
- **Hàng đợi nội bộ:** bounded queue, max in-flight items/bytes, reject hoặc cancel khi quá tải.
- **Thời gian xử lý:** timeout/deadline tổng; slow consumer có thể giữ HTTP connection lâu.
- **Số request/connection đồng thời:** Flow per response không tự giới hạn số HTTP requests hoặc tổng tài nguyên của nhiều flow.
- **Quyền sở hữu và rò rỉ tài nguyên:** kết thúc bình thường phải drain; khi bỏ cuộc phải cancel/close.

Flow demand đảm bảo **không phát quá số onNext đã được cho phép** trong một subscription hợp lệ. Nó **không** đảm bảo mức sử dụng RAM cố định, vì kích thước mỗi item, buffer upstream/downstream và ứng dụng tự lưu dữ liệu là các yếu tố riêng.

## 11. Khi xử lý nội dung HTTP, có những tầng backpressure nào?

Xét một luồng:

~~~text
Ứng dụng producer
      |
      | (1) Flow demand: request(n) item ByteBuffer
      v
HttpRequest.BodyPublisher
      |
      | (2) Buffer/framing trong HttpClient
      v
HTTP/1.1 hoặc HTTP/2
      |
      | (3) TCP socket buffer và TCP receive window,
      |     HTTP/2 flow control nếu áp dụng
      v
Proxy / server / network
      |
      | (4) HTTP client response BodySubscriber<List<ByteBuffer>>
      v
Ứng dụng downstream Subscriber
      |
      | (5) Queue, file, DB, parser, consumer
      v
Kết thúc xử lý
~~~

Backpressure ở tầng Flow có thể gây giảm tốc độ producer khi downstream không yêu cầu thêm, nhưng phải qua **buffer và scheduler** ở từng tầng. Ví dụ, server đã gửi một lượng dữ liệu vào TCP send buffer trước khi client tạm dừng request item. HTTP/2 dùng flow-control window ở protocol, nhưng ứng dụng vẫn không có quyền giả định một request(1) tương ứng với một WINDOW_UPDATE hay một TCP read duy nhất. Với HTTP/1.1, việc đọc chậm có thể khiến TCP receive window hạn chế sender **theo thời gian**, không lập tức và không phải điều khiển tuyệt đối.

Mục tiêu thiết kế là **end-to-end bounded work**, không phải “chỉ cần thêm `request(1)` là đủ”. Nếu một stage nhận item rồi tự lưu vào danh sách không giới hạn, backpressure đã bị đứt ở stage đó.

## 12. Flow.Processor: biến đổi dữ liệu có giữ nhu cầu

`Flow.Processor<T,R>` đồng thời là `Subscriber<T>` (nhận dữ liệu upstream) và `Publisher<R>` (phát downstream). Dùng khi cần giải mã/biến đổi hoặc lọc dữ liệu, nhưng phải chuyển demand hợp lý.

~~~text
Publisher<ByteBuffer> -> Processor<ByteBuffer, ParsedEvent>
                                   |
                                   v
                           Subscriber<ParsedEvent>
                                  request(n)
                                   |
                       Processor quyết định khi nào
                       request upstream tiếp
~~~

Một processor sai có thể:
- Request `Long.MAX_VALUE` ở upstream rồi tích lũy toàn bộ khi downstream chỉ request(1), làm memory tăng.
- Gửi `onNext` cho downstream không đủ demand.
- Drop bytes/item tùy tiện khiến payload HTTP bị hỏng.
- Gọi upstream request trong callback khi đang giữ lock, gây reentrancy/deadlock.

Vì vậy không nên tự xây processor để parse JSON body lớn nếu không có nhu cầu thực tế; có thể dùng parser streaming uy tín và thiết kế queue/ack có giới hạn. Khi cần parse line-delimited JSON/NDJSON, hãy nhớ HTTP chunk không khớp line boundary; parser phải giữ bytes còn dang dở giữa các batch và chỉ phát event sau khi có frame hoàn chỉnh.

## 13. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `onSubscribe` đã chạy nhưng `onNext` không đến | Subscriber chưa gọi `request(n>0)`, hoặc upstream chưa có dữ liệu | Cấp demand đúng; đo readiness và trạng thái upstream |
| `request(0)` gây lỗi | Nhu cầu phải dương | Không dùng 0 để pause; ngừng request thêm |
| Flow subscriber nhận `List<ByteBuffer>` nhưng code ép `ByteBuffer` | Sai generic type của response BodySubscriber | Duyệt từng buffer trong batch |
| Request body publisher dùng `Flow.Publisher<List<ByteBuffer>>` | Sai phía request: BodyPublisher phát `ByteBuffer` đơn lẻ | Cung cấp `Flow.Publisher<ByteBuffer>` |
| Body upload thiếu byte khi retry | Dùng hot/non-replayable publisher hoặc stream đã hết | Tạo nguồn mới per subscription/retry; kiểm chứng contentLength |
| `Content-Length` sai | Đếm ký tự thay vì byte, hoặc nguồn phát thiếu/thừa | Dùng publisher có content length chuẩn, không tự set header |
| Tải response lớn vẫn OOM dù `request(1)` | Ứng dụng lưu tất cả byte vào ByteArrayOutputStream/List không giới hạn | Xử lý từng chunk, giải phóng, dùng ofFile hay bounded sink |
| `send(... ofPublisher)` trả về nhưng logic chưa xong | Response chỉ cần headers trước; body streaming còn chạy | Đợi downstream onComplete/onError theo deadline |
| Subscriber thứ hai của `ofPublisher()` báo lỗi | Publisher response chỉ cho subscribe một lần | Chỉ có một consumer hoặc tự tạo multicast có kiểm soát |
| `cancel()` xong vẫn có callback in-flight | Cancel là best-effort | State idempotent, tránh double cleanup, bỏ item muộn |
| `SubmissionPublisher.submit` “treo” | Buffer cho slow subscriber đầy | Dùng bounded executor/queue, không block trên cùng thread consumer |
| `SubmissionPublisher.offer` khiến file hỏng | Item bị drop | Không cho drop dữ liệu body stream, dùng backpressure/timeout/error |
| Tăng `request(1000)` nhưng throughput không tăng | Bottleneck ở network, disk, CPU, server hoặc overhead | Đo bằng metrics, tăng window có kiểm soát |
| UTF-8 bị lỗi khi nhận từng chunk | Ký tự bị tách giữa các ByteBuffer | Giữ bytes hoặc dùng streaming decoder |
| Subscriber onNext ném exception | Callback có lỗi xử lý/IO | Catch, cancel/close theo chính sách, báo lỗi một lần |
| HTTP connection không reuse | Body không được tiêu thụ hết hoặc cancel giữa chừng | Drain body khi hợp lý; chấp nhận đóng connection khi cancel |

### 13.1. Dữ liệu không đến sau khi subscribe

Đầu tiên kiểm tra `onSubscribe` đã có chưa, bạn có lưu đúng Subscription không, đã request số dương chưa và publisher có dữ liệu không. Đừng chẩn đoán “mạng chậm” trước khi xác minh chính ứng dụng có **demand**. Trong HTTP, nhớ rằng ofPublisher subscriber thứ hai luôn bị từ chối; log subscriber lifecycle cho đúng exchange.

### 13.2. Publisher phát nhiều hơn demand

Một custom publisher phải quản lý tổng demand của **từng subscription** và serialize signal. Đừng gọi `onNext` vô điều kiện theo vòng đọc file/network, bởi có thể vi phạm Flow. Dùng các BodyPublishers chuẩn khi có thể; nếu tự viết, kiểm thử `request(1)`, request cộng dồn, request 0/âm, cancel race, nhiều subscriber, reentrant request và error path.

### 13.3. Vì sao không nên gọi long-running DB request trong onNext?

Phương thức `onNext` có thể chạy trên thread dispatch/callback của Publisher hoặc HttpClient. Một thao tác blocking lâu có thể ảnh hưởng những subscription khác, gây chậm toàn pipeline. Nếu cần xử lý DB, chuyển sang executor riêng **có giới hạn**; chỉ request batch tiếp theo khi công việc tương ứng đã hoàn thành và queue còn sức chứa.

### 13.4. Lỗi khi tự làm fan-out

Nếu một Publisher có ba subscriber, mỗi subscriber có demand và buffer khác nhau. Một subscriber chậm có thể kéo `SubmissionPublisher.submit` bị chặn vì buffer riêng của nó đầy; tốc độ toàn nguồn có thể bị ảnh hưởng. Không giả định Flow mặc định multicast với xử lý công bằng/độc lập hoặc bỏ qua subscriber chậm mà không có policy.

### 13.5. Việc cancellation có hủy request trên server không?

Không chắc. HTTP client có thể ngừng đọc/gửi data và đóng stream/connection, nhưng server có thể đã nhận, xác thực, ghi dữ liệu hoặc commit tác vụ trước đó. Đặc biệt POST thanh toán/upload xử lý nghiệp vụ có thể đã xảy ra. Để biết kết quả, cần request ID, idempotency key, trạng thái nghiệp vụ và chính sách retry, không dựa trên `cancel()`.

## 14. Quy tắc production cho streaming HTTP an toàn

Một pipeline thực tế nên đặt rõ:

1. **Max body bytes:** giới hạn tổng byte download/upload, không chỉ đọc `Content-Length` do peer công bố.
2. **Max in-flight bytes/items:** mỗi subscriber có số item outstanding nhỏ và giới hạn kích thước mỗi item; bounded queues xuyên suốt pipeline.
3. **Deadlines:** connect timeout, request timeout, timeout xử lý/chờ sink; chậm kéo dài không được giữ socket/worker vô hạn.
4. **Error propagation:** upstream lỗi → báo cho downstream/cancel và đóng tài nguyên; downstream lỗi → không request thêm, cancel upstream, trả lỗi cho task tương ứng.
5. **Idempotent termination:** chỉ hoàn tất future/latch/request một lần; `onError` và `onComplete` không đi cùng nhau; cancel có thể còn tín hiệu muộn.
6. **Demand policy:** request theo lô dựa trên throughput và byte budget, không phải hard-code Long.MAX_VALUE ở mọi stage.
7. **ByteBuffer ownership:** với request, publisher không sửa buffer sau khi gửi cho HttpClient; với response, danh sách và buffer read-only; nếu gửi qua worker, quản lý position/thread đúng.
8. **Replayable uploads:** chuẩn bị BodyPublisher cho trường hợp resend và kiểm tra `contentLength()` chính xác; nếu không replayable thì cấu hình retry/redirect tương ứng và xử lý thất bại rõ ràng.
9. **Charset/framing:** ghép/giải mã dữ liệu theo bytes, không suy luận một onNext là một dòng JSON hay một code point UTF-8.
10. **Resource cleanup:** với `ofPublisher()` phải subscribe một lần và consume tới terminal hoặc cancel; với InputStream/Stream/File phải đóng theo API.
11. **Bảo mật:** TLS/hostname verification, auth đúng, không log token, giới hạn body tránh zip bomb/decompression bomb nếu có bước giải nén, tránh parse input chưa xác thực.
12. **Observability:** ghi bytes nhận/gửi, demand đang outstanding, queue depth, buffer sử dụng, thời gian chờ, số cancellation/error, status/latency HTTP và concurrency; không log payload nhạy cảm.

Chỉ báo `request(1)` mà không giới hạn **payload size và toàn bộ response length** là chưa đủ. Tài nguyên của ứng dụng bị tiêu thụ theo **byte × số flow × thời gian giữ**, không chỉ theo số onNext.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `Flow.Subscription.request(3)` có nghĩa là yêu cầu thêm ba byte không?  
**Đáp án:** Không. Nó cấp nhu cầu nhận thêm tối đa ba **item/onNext**. Item có thể là `ByteBuffer` hoặc `List<ByteBuffer>` với byte size không cố định.

**Câu 2.** Gọi `request(2)`, đã nhận một item, tiếp tục gọi `request(4)`. Demand còn lại là bao nhiêu?  
**Đáp án:** Ban đầu 2, tiêu thụ 1 còn 1, cộng thêm 4 thành **5 item**, nếu không có item/tín hiệu nào khác chen vào.

**Câu 3.** Nếu Subscriber không gọi `request` sau `onSubscribe`, Publisher có được phát `onNext` hợp lệ không?  
**Đáp án:** Không vượt demand bằng 0. Subscriber phải request số dương nếu muốn data; đừng dùng request(0) để tạm dừng.

**Câu 4.** `request(0)` có phải “pause” không?  
**Đáp án:** Không. Theo Flow contract, nó phải dẫn đến báo `onError(IllegalArgumentException)`; pause bằng cách chưa request thêm.

**Câu 5.** Vì sao `HttpRequest.BodyPublisher` là `Publisher<ByteBuffer>` mà `HttpResponse.BodySubscriber<T>` là `Subscriber<List<ByteBuffer>>`?  
**Đáp án:** Đó là hai hợp đồng generics khác nhau của JDK: phía request phát từng ByteBuffer; phía response HttpClient phát từng **danh sách ByteBuffer** (batch). Không ép một dạng sang dạng kia.

**Câu 6.** `BodyHandlers.ofPublisher()` trả về `HttpResponse`, có thể khẳng định toàn bộ body đã tải xong không?  
**Đáp án:** Không. Headers có thể đã xong trong khi body vẫn streaming. Subscriber phải nhận đến onComplete/onError hoặc cancel.

**Câu 7.** Một response `ofPublisher()` có thể subscribe hai consumer độc lập không?  
**Đáp án:** Không. Publisher được trả về chỉ cho phép một lần subscribe; lần thứ hai nhận lỗi. Nếu cần hai consumer, phải tạo fan-out có điều tiết/giới hạn riêng.

**Câu 8.** `HttpRequest.BodyPublishers.fromPublisher(source, 1024)` có nghĩa body dài 1.024 ký tự không?  
**Đáp án:** Không. Đây là chính xác **1.024 byte** và publisher phải phát đúng lượng đó. Không tự dùng String.length() thay byte count UTF-8.

**Câu 9.** Vì sao một `SubmissionPublisher` hot có thể là lựa chọn tệ cho HTTP upload retry?  
**Đáp án:** Dữ liệu gửi trước khi HTTP client subscribe không được replay cho subscriber mới; request resend có thể không nhận lại cùng body. Cần nguồn mới/replayable theo subscription.

**Câu 10.** `cancel()` có chắc sẽ gọi `onComplete()` không?  
**Đáp án:** Không. Cancellation là best-effort, sau cancel không bắt buộc terminal signal và có thể còn tín hiệu đã lên lịch.

**Câu 11.** Có `request(1)` thì ứng dụng có chắc không tốn nhiều RAM không?  
**Đáp án:** Không. Một item có thể rất lớn; queue ở stage khác hoặc collector tích lũy toàn bộ response có thể không bounded.

**Câu 12.** Khi nào nên dùng `BodyHandlers.ofFile()` thay vì `ofPublisher()`?  
**Đáp án:** Khi chỉ cần tải response lớn ra tệp theo API có sẵn, không cần custom transform hoặc Flow processing. Nó thường đơn giản hơn và ít lỗi hơn.

**Câu 13.** Nếu một chữ tiếng Việt bị chia giữa hai ByteBuffer nhận từ HTTP, phải làm gì?  
**Đáp án:** Ghép byte hợp lý hoặc dùng CharsetDecoder incremental; không decode từng fragment như chuỗi độc lập rồi nối.

**Câu 14.** `SubmissionPublisher.submit(item)` có thể block không?  
**Đáp án:** Có. Khi buffer của subscriber không đủ và downstream chậm, submit có thể block chờ tài nguyên. `offer` có thể drop theo policy, không phù hợp để tự động bỏ byte của body.

**Câu 15.** `onNext` đã đưa batch sang worker queue rồi có nên request tiếp ngay không?  
**Đáp án:** Chỉ khi queue có giới hạn/sức chứa và backpressure end-to-end vẫn đúng. Nếu chưa xử lý mà vẫn request vô hạn, downstream có thể OOM.

**Câu 16.** `Flow.Processor<T,R>` dùng khi nào?  
**Đáp án:** Khi cần một stage vừa tiêu thụ upstream vừa phát downstream, như parse bytes thành events; phải truyền nhu cầu, bảo toàn thứ tự và quản lý buffer/timeout.

## 16. Tài liệu chính thức

- Java SE 17 — `Flow` và ví dụ nhu cầu, request theo batch: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html
- Java SE 17 — `Flow.Publisher`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Publisher.html
- Java SE 17 — `Flow.Subscriber`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html
- Java SE 17 — `Flow.Subscription.request/cancel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html
- Java SE 17 — `SubmissionPublisher`, `submit/offer/close`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html
- Java SE 17 — `HttpRequest.BodyPublisher` (Flow.Publisher<ByteBuffer>): https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html
- Java SE 17 — `HttpRequest.BodyPublishers.fromPublisher` và nguồn có thể replay: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html
- Java SE 17 — `HttpResponse.BodySubscriber<T>` (Flow.Subscriber<List<ByteBuffer>>): https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html
- Java SE 17 — `HttpResponse.BodyHandlers.ofPublisher/ofFile/ofInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- Java SE 17 — `HttpResponse.BodySubscribers.ofPublisher/fromSubscriber`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html
- Java SE 17 — `HttpClient`, `send/sendAsync`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
