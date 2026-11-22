# `BodyPublishers.fromPublisher` với `Flow.Publisher<ByteBuffer>` trong Java 11+

## 1. Mục đích: dùng nguồn dữ liệu theo luồng làm HTTP request body

Từ **Java 11**, HTTP Client chuẩn trong `java.net.http` có thể gửi nội dung của một HTTP request từ `HttpRequest.BodyPublisher`. Khi dữ liệu của ứng dụng đã được tạo theo mô hình **Reactive Streams** của `java.util.concurrent.Flow` (chẳng hạn pipeline tạo các khối byte theo nhu cầu), ta có thể dùng **`HttpRequest.BodyPublishers.fromPublisher(...)`** để chuyển nguồn đó thành request body.

Khác với việc gom toàn bộ dữ liệu vào một `byte[]` hoặc `String` trước khi gửi, `Flow.Publisher<ByteBuffer>` có thể **phát lần lượt các `ByteBuffer`**. HTTP client đóng vai trò subscriber và lấy dữ liệu theo cơ chế **demand/backpressure**: subscriber chỉ định bao nhiêu *buffer item* nó sẵn sàng nhận, còn publisher không được gửi vượt số lượng đã yêu cầu. Điều này giúp thiết kế đường truyền phù hợp với nguồn phát theo khối, nhưng **không tự động bảo đảm** bộ nhớ ít, không blocking hoặc không lỗi — các đặc tính đó vẫn phụ thuộc cách viết publisher.

Chủ đề này thuộc nhóm **request body**: ta đang nói về *dữ liệu client gửi lên server* qua `POST`, `PUT` hoặc một method khác cho phép body, **không phải** publisher nhận response body từ server.

## 2. Hai overload hiện hành và ý nghĩa `contentLength`

Các chữ ký Java 11 (vẫn có trên JDK hiện đại):

```java
HttpRequest.BodyPublisher fromPublisher(
        Flow.Publisher<? extends ByteBuffer> publisher)

HttpRequest.BodyPublisher fromPublisher(
        Flow.Publisher<? extends ByteBuffer> publisher,
        long contentLength)
```

| Lời gọi | `BodyPublisher.contentLength()` | Khi sử dụng |
| --- | --- | --- |
| `BodyPublishers.fromPublisher(source)` | `-1` — số byte **chưa biết** | Dữ liệu được tạo dần, không biết trước tổng số byte. |
| `BodyPublishers.fromPublisher(source, length)` | `length` — **số byte chính xác, dương** | Nguồn bảo đảm tổng byte được phát đúng bằng `length`. |

**Quan trọng:**

- Trong overload hai tham số, `contentLength` phải **lớn hơn 0**. Giá trị `0` hoặc số âm gây `IllegalArgumentException` ngay khi gọi phương thức. Nếu cần body rỗng, dùng `BodyPublishers.noBody()`.
- `length` là **tổng số byte thực** của tất cả `ByteBuffer` được phát, **không phải** số `ByteBuffer`, số ký tự, số lần `onNext` hay `String.length()`.
- Khi không biết độ dài, `contentLength() == -1` báo rằng độ dài chưa xác định. Không tự điền một độ dài ước tính hoặc tự đặt `Content-Length` không khớp.
- Nếu khai báo độ dài cố định nhưng publisher phát ít hoặc nhiều byte hơn, quá trình gửi không đáp ứng hợp đồng và có thể thất bại. Không dựa vào một loại exception hay HTTP status cố định để xem lệch số byte là bình thường.
- `BodyPublisher.contentLength()` là thông tin **trước/lúc gửi**, không phải thống kê được cập nhật dần sau mỗi buffer; giá trị phải ổn định.

Phương thức này là **adapter**: nó **không tự mã hóa** dữ liệu đầu vào, không tự biết đó là JSON và không tự gọi server. Nếu dữ liệu là text, hãy biến thành byte với charset rõ ràng trước khi xuất `ByteBuffer`. `Content-Type` cần được đặt độc lập theo hợp đồng API.

## 3. Luồng dữ liệu và vai trò của `Flow`

Mô hình cơ bản:

```text
Nguồn dữ liệu
     |
     v
Flow.Publisher<ByteBuffer>  -- onSubscribe -->
     |                            |
     |                    HTTP Client subscriber
     |                    request(n) = nhu cầu n buffer
     +------ onNext(ByteBuffer) <---+
     +------ onNext(ByteBuffer) <---+
     +------ onComplete() hoặc onError()
     |
BodyPublishers.fromPublisher(...)
     |
HttpRequest.Builder.POST(bodyPublisher)
     |
HttpClient.send(...) / sendAsync(...)
```

Sơ đồ là mô tả **vai trò và tín hiệu logic**, không phải lời khẳng định rằng `fromPublisher(...)` ngay lập tức đăng ký/đọc nguồn. Thực tế publisher được HTTP client **subscribe khi cần truyền request body**; việc gọi `fromPublisher(...)` hoặc `build()` chỉ chuẩn bị request.

Các thành phần:

1. **`Flow.Publisher<ByteBuffer>`** tạo các mảnh byte. Có thể là nguồn tự viết hoặc một thư viện Reactive Streams tương thích `Flow`.
2. **`Flow.Subscriber<? super ByteBuffer>`** nhận các mảnh: `onSubscribe`, `onNext`, `onError`, `onComplete`.
3. **`Flow.Subscription`** là kênh điều khiển: `request(n)` để xin thêm item và `cancel()` để hủy.
4. **`HttpRequest.BodyPublisher`** kế thừa `Flow.Publisher<ByteBuffer>`, đồng thời bổ sung `contentLength()` để HTTP client biết độ dài nếu có.
5. **HTTP client** tiêu thụ body khi gửi request, có thể hủy subscription vì lỗi, và có thể subscribe lại nếu phải gửi lại body do tình huống xác thực/chuyển hướng/gửi lại.

`request(n)` đếm **số lần gọi `onNext(ByteBuffer)`**, không đếm byte. Ví dụ hai buffer lần lượt dài 4 và 5 byte là **hai item**, nhưng tổng content length là **9 byte**. Khi subscriber gọi `request(1)`, publisher chỉ được phát thêm tối đa **một** item trước khi nhận demand tiếp theo.

Publisher phải gửi đúng trình tự tín hiệu của `Flow`, không phát quá demand, phát không quá một tín hiệu kết thúc (`onComplete` hoặc `onError`), và chấp nhận việc subscriber hủy. Nếu `request(n)` được gọi với `n <= 0`, subscriber phải nhận `onError` với `IllegalArgumentException`. Không dùng vòng lặp đẩy dữ liệu vô hạn mà bỏ qua `Subscription.request(...)`.

## 4. Ví dụ Java hoàn chỉnh: publisher phát hai `ByteBuffer`, body có/không có độ dài

Ví dụ sau chạy **không cần mạng**: nó tạo một publisher đơn giản, bọc bằng `fromPublisher`, xây `HttpRequest` và dùng một subscriber minh họa để xem các chunk. Không có `HttpClient.send(...)`, nên output ổn định và không phụ thuộc server.

Nguồn phát hai phần của chuỗi `Xin chào` bằng UTF-8:

- `"Xin "`: 4 byte.
- `"chào"`: 5 byte (ký tự `à` chiếm 2 byte UTF-8).
- Tổng cộng: **9 byte**, nhưng chỉ có **2 buffer item**.

Tạo tệp **`FromPublisherDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpRequest.BodyPublisher;
import java.net.http.HttpRequest.BodyPublishers;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.concurrent.Flow;

public class FromPublisherDemo {
    public static void main(String[] args) {
        byte[] first = "Xin ".getBytes(StandardCharsets.UTF_8);
        byte[] second = "chào".getBytes(StandardCharsets.UTF_8);

        Flow.Publisher<ByteBuffer> source =
                new TwoChunkPublisher(first, second);

        BodyPublisher unknown = BodyPublishers.fromPublisher(source);
        BodyPublisher exact = BodyPublishers.fromPublisher(
                source, (long) first.length + second.length);

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/upload"))
                .header("Content-Type", "text/plain; charset=UTF-8")
                .POST(exact)
                .build();

        System.out.println("unknownLength=" + unknown.contentLength());
        System.out.println("fixedLength=" + exact.contentLength());
        System.out.println("requestMethod=" + request.method());
        System.out.println("hasBody=" + request.bodyPublisher().isPresent());
        System.out.println("contentType=" +
                request.headers().firstValue("Content-Type")
                        .orElse("missing"));

        // Kiểm tra publisher trực tiếp, KHÔNG gửi HTTP.
        source.subscribe(new RecordingSubscriber());
    }

    // Demo tuần tự, đồng bộ: nguồn phát lại được ở mỗi subscribe.
    // Production publisher phải xử lý an toàn cả luồng đồng thời/lỗi/cancel.
    private static final class TwoChunkPublisher
            implements Flow.Publisher<ByteBuffer> {
        private final byte[][] parts;

        TwoChunkPublisher(byte[]... chunks) {
            parts = new byte[chunks.length][];
            for (int i = 0; i < chunks.length; i++) {
                parts[i] = chunks[i].clone();
            }
        }

        @Override
        public void subscribe(
                Flow.Subscriber<? super ByteBuffer> subscriber) {
            Objects.requireNonNull(subscriber);
            subscriber.onSubscribe(new Flow.Subscription() {
                private int next;
                private long demand;
                private boolean terminated;
                private boolean draining;

                @Override
                public void request(long n) {
                    if (terminated) {
                        return;
                    }
                    if (n <= 0) {
                        terminated = true;
                        subscriber.onError(new IllegalArgumentException(
                                "request(n) requires n > 0"));
                        return;
                    }

                    // Tránh tràn long khi cộng dồn demand.
                    demand = Long.MAX_VALUE - demand < n
                            ? Long.MAX_VALUE : demand + n;

                    // Subscriber có thể request tiếp từ trong onNext.
                    if (draining) {
                        return;
                    }
                    draining = true;
                    try {
                        while (!terminated && demand > 0
                                && next < parts.length) {
                            demand--;
                            // Mỗi subscription nhận các ByteBuffer mới.
                            byte[] bytes = parts[next++].clone();
                            subscriber.onNext(ByteBuffer.wrap(bytes));
                        }
                        if (!terminated && next == parts.length) {
                            terminated = true;
                            subscriber.onComplete();
                        }
                    } finally {
                        draining = false;
                    }
                }

                @Override
                public void cancel() {
                    terminated = true;
                }
            });
        }
    }

    private static final class RecordingSubscriber
            implements Flow.Subscriber<ByteBuffer> {
        private Flow.Subscription subscription;
        private final ByteArrayOutputStream collected =
                new ByteArrayOutputStream();
        private int chunkCount;

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(ByteBuffer item) {
            byte[] bytes = new byte[item.remaining()];
            item.get(bytes);
            collected.writeBytes(bytes);
            chunkCount++;
            subscription.request(1);
        }

        @Override
        public void onError(Throwable error) {
            System.out.println("error=" +
                    error.getClass().getSimpleName());
        }

        @Override
        public void onComplete() {
            System.out.println("chunks=" + chunkCount);
            System.out.println("text=" +
                    collected.toString(StandardCharsets.UTF_8));
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17+** (các API được dùng cũng tương thích Java 11):

```bash
javac FromPublisherDemo.java
java FromPublisherDemo
```

**Stdout chính xác:**

```text
unknownLength=-1
fixedLength=9
requestMethod=POST
hasBody=true
contentType=text/plain; charset=UTF-8
chunks=2
text=Xin chào
```

**Từng bước:**

1. `source` chứa **hai** mảng byte nội bộ; mỗi lần `subscribe(...)` tạo một `Flow.Subscription` mới, vì vậy không dùng lại một subscription đã tiêu thụ.
2. `unknown.contentLength() == -1` vì overload một tham số không biết trước số byte.
3. `exact.contentLength() == 9` vì đã cung cấp tổng byte UTF-8 chính xác. Đây **không** phải hai item hay `"Xin chào".length()`.
4. `request.bodyPublisher().isPresent()` trả `true` vì builder đã gọi `POST(exact)`. Request chưa được gửi; chưa có phản hồi.
5. `RecordingSubscriber` gọi `request(1)` ở `onSubscribe` và sau mỗi `onNext`. Publisher phát từng buffer theo demand. Bộ thu ghép các byte thành `Xin chào` rồi nhận `onComplete`.
6. Các byte của mỗi buffer được sao chép để không giữ tham chiếu tới buffer đã phát. Điều này còn hỗ trợ tạo dữ liệu mới khi subscribe lại.

**Giới hạn có chủ ý của ví dụ:** `TwoChunkPublisher` hoạt động đồng bộ, tuần tự để minh họa giao thức và backpressure. Nó **không phải** mẫu publisher hoàn chỉnh dùng cho nhiều luồng đồng thời hay nguồn I/O bất đồng bộ. Trong hệ thống thật, việc cộng dồn demand, serialize các tín hiệu, xử lý lỗi từ nguồn, cancellation, scheduler và vòng đời buffer phải được thiết kế theo Reactive Streams/`Flow`.

## 5. Gửi request thực tế

Trong ứng dụng, dùng `BodyPublisher` từ `fromPublisher` như các publisher khác:

```java
HttpClient client = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/upload"))
        .header("Content-Type", "application/octet-stream")
        .POST(BodyPublishers.fromPublisher(source))
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

System.out.println(response.statusCode());
```

Đây là **đoạn mã minh họa đặt bên trong phương thức có thể xử lý/khai báo `IOException` và `InterruptedException`**, với biến `source` đã có; cần import `java.net.http.HttpClient`, `HttpResponse`, `HttpRequest`, `URI` và `StandardCharsets`. Không phải chương trình độc lập. Khi chạy, đoạn này **có kết nối mạng thật**; kết quả không cố định vì phụ thuộc API, TLS, authentication, lỗi mạng, trạng thái server và nội dung publisher.

`HttpClient.sendAsync(request, handler)` cũng nhận request tương tự và trả `CompletableFuture<HttpResponse<T>>`. Việc **không đồng bộ của HTTP client** không tự làm cho publisher tự viết trở nên non-blocking hoặc thread-safe. Nếu `publisher.subscribe(...)` hoặc quá trình phát buffer làm công việc chặn lâu, điều đó có thể ảnh hưởng throughput và luồng thực thi; cần kiến trúc phù hợp.

## 6. Backpressure: phải hiểu `request(n)` đúng đơn vị

Trong `Flow`, một lần `onNext(ByteBuffer)` là **một item**; số byte của item bằng `buffer.remaining()` tại thời điểm được giao. Ví dụ:

```text
Subscriber gọi request(1)
Publisher phát buffer A: 4 byte
Subscriber gọi request(1)
Publisher phát buffer B: 5 byte
Publisher gọi onComplete()
Tổng: 2 item, 9 byte
```

Không thể suy ra rằng `request(9)` nghĩa là xin 9 byte. Nó cho phép tối đa 9 **item**, có thể tương ứng lượng byte rất khác nhau tùy kích thước từng buffer. Cần giới hạn cả số item và tổng byte đang giữ trong RAM khi thiết kế pipeline lớn.

**Những quy tắc của `Flow.Subscription` cần giữ:**

- Chỉ gửi `onNext` khi có demand dương chưa được đáp ứng.
- `request(n > 0)` **cộng thêm** `n` item vào nhu cầu; không phải đặt lại số item còn được phép phát.
- `request(n <= 0)` phải đưa subscription tới `onError` với `IllegalArgumentException`.
- Khi subscriber gọi `cancel()`, publisher phải ngừng phát dữ liệu theo khả năng cho phép và giải phóng tài nguyên; hủy không nhất thiết dẫn đến `onComplete`.
- `onError` và `onComplete` là **tín hiệu kết thúc**, không được phát lẫn lộn, lặp nhiều lần hoặc gửi `onNext` sau khi đã kết thúc.
- Khi phát bất đồng bộ, các callback tới cùng một subscriber phải tuân theo ràng buộc thứ tự/serialize của `Flow`; không được để nhiều worker tự gọi `onNext` đồng thời tùy tiện.

Khi publisher tự phát byte từ file/network, ngoài demand cần xử lý **partial reads**, EOF, lỗi I/O, hủy giữa chừng và đóng tài nguyên. Không giữ toàn bộ dữ liệu trong danh sách buffer nếu mục đích ban đầu là streaming bộ nhớ nhỏ.

## 7. Quyền sở hữu `ByteBuffer` sau `onNext`

Một `ByteBuffer` có các thuộc tính `position`, `limit`, `capacity`. Khi phát một item, HTTP client đọc phần byte từ `position` tới `limit` (tức `remaining()` byte), không phải mặc nhiên từ chỉ số 0 tới `capacity`.

Ví dụ **minh họa** nguồn đang điền dữ liệu vào buffer:

```java
ByteBuffer buffer = ByteBuffer.allocate(64); // Chế độ ghi.
buffer.put("hello".getBytes(StandardCharsets.UTF_8));
buffer.flip();                               // Chuyển sang chế độ đọc.
subscriber.onNext(buffer);                   // Bàn giao buffer.
```

Đoạn này không độc lập; `subscriber` phải là một `Flow.Subscriber<? super ByteBuffer>` đã được `onSubscribe` và có demand hợp lệ. Sau khi gọi `onNext(buffer)` để bàn giao cho HTTP client, **publisher không được tiếp tục truy cập/thay đổi buffer đó**. Không `clear()` rồi ghi đè vùng lưu trữ khi phía nhận còn có thể đang đọc.

Đặc biệt, `ByteBuffer.wrap(byteArray)` **chia sẻ mảng byte** với buffer. Không được sửa lại mảng backing sau khi publish. Muốn tách dữ liệu, cấp buffer mới, copy mảng hoặc sử dụng cơ chế quản lý vòng đời rõ ràng, tránh corruption do tái sử dụng bộ nhớ quá sớm.

`ByteBuffer.allocateDirect(...)` có thể hữu ích với một số pipeline, nhưng **không phải điều kiện bắt buộc** của `fromPublisher`. Buffer heap cũng hợp lệ. Chọn heap/direct theo đo đạc và yêu cầu nguồn dữ liệu, không mặc định direct luôn nhanh hơn.

Một trường hợp hay gặp: đọc file vào `ByteBuffer`, gọi `flip()` rồi `onNext`, sau đó ngay lập tức `clear()` và đọc thêm vào **cùng buffer**. Cách này có thể làm hỏng request body vì dữ liệu cũ chưa được HTTP client tiêu thụ xong. Hãy dùng các buffer có vòng đời riêng hoặc cơ chế phối hợp an toàn.

## 8. Tái đăng ký khi phải gửi lại request body

HTTP client có thể phải **subscribe lại** BodyPublisher nếu một request cần phát lại do authentication, chuyển hướng, hoặc cơ chế gửi lại phù hợp. Theo hợp đồng `BodyPublisher`, **mỗi subscription mới phải có thể cung cấp lại cùng nội dung byte** để request được gửi lại đúng.

Điều này dẫn đến sự khác biệt quan trọng:

| Nguồn | Khả năng gửi lại body |
| --- | --- |
| Publisher tạo `ByteBuffer` mới từ dữ liệu bất biến khi mỗi `subscribe` | Có thể tái phát cùng nội dung, nếu triển khai demand/cancel/lỗi đúng. |
| Publisher phát từ một `InputStream` đã bị đọc hết và không tạo lại được | Không thể tự phát lại nội dung nếu không mở nguồn mới/ghi cache. |
| Publisher “hot” chỉ phát sự kiện hiện tại | Subscriber sau có thể bỏ lỡ dữ liệu cũ, không phù hợp nếu không có cơ chế replay. |
| Publisher từ file mở lại tại mỗi lần subscribe | Có thể gửi lại nếu file vẫn tồn tại và **nội dung không thay đổi**; cần xử lý lỗi. |

Với `fromPublisher(...)`, adapter **không tự lưu cache và không biến một nguồn chỉ đọc được một lần thành replayable**. Nếu nguồn không thể tạo lại body, cần thiết kế giới hạn việc phát lại request theo HTTP client/API, lưu nguồn ở nơi có thể đọc lại, hoặc chọn publisher phù hợp hơn.

Đừng coi `java.util.concurrent.SubmissionPublisher` mặc nhiên là publisher có thể phát lại nội dung cũ. Nó hỗ trợ cách công bố bất đồng bộ, nhưng không tự đảm bảo replay cho subscriber tới sau. Nếu muốn dùng làm request body, phải xem xét kỹ thời điểm subscribe, thời điểm submit, vòng đời executor, backpressure và retry.

## 9. Khi nào cần overload có độ dài cố định?

Với một nguồn có thể tính chính xác tổng byte **trước khi gửi**:

```java
byte[] data = "hello".getBytes(StandardCharsets.UTF_8);
long exactBytes = data.length;

HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.fromPublisher(source, exactBytes);
```

Đây là **đoạn minh họa**, `source` chỉ phù hợp nếu nó thực sự phát đúng 5 byte. Biến `data` chỉ dùng để cho thấy cách tính byte. Trên dữ liệu UTF-8 chứa tiếng Việt, dùng số byte của dữ liệu đã mã hóa thay vì chiều dài `String`.

Đối với dữ liệu không biết trước tổng số byte, dùng overload không khai báo độ dài:

```java
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.fromPublisher(source);
// body.contentLength() == -1
```

Khi body có độ dài không biết trước, cách truyền tải/framing do client quyết định theo phiên bản HTTP thực tế. Ví dụ, với HTTP/1.1 có thể sử dụng chunked transfer coding, trong khi HTTP/2 sử dụng cơ chế frame riêng; **không đồng nhất** `unknown length` với việc luôn có header `Transfer-Encoding: chunked` trong mọi giao thức.

### Vì sao không truyền `0`?

```java
BodyPublishers.fromPublisher(source, 0); // IllegalArgumentException
```

Overload có `long contentLength` yêu cầu **số dương**; nó không được dùng để mô tả body rỗng. Nếu request không có body, dùng:

```java
HttpRequest.BodyPublisher body = BodyPublishers.noBody();
```

Về mặt API, `BodyPublisher` nói chung có thể báo `contentLength() == 0` đối với body rỗng (ví dụ `noBody()`). Nhưng **chính overload `fromPublisher(source, contentLength)`** là trường hợp yêu cầu strictly positive length. Không nhầm hai quy tắc.

## 10. Lỗi phổ biến và cách tránh

| Sai sót | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Truyền `Flow.Publisher<String>` vào `fromPublisher` | Sai kiểu: API yêu cầu publisher của `ByteBuffer`. | Mã hóa text thành byte UTF-8 và publish `ByteBuffer`. |
| Đếm `String.length()` để làm `contentLength` | Độ dài không khớp nếu có ký tự UTF-8 đa byte. | Cộng tổng số byte sau khi mã hóa. |
| Truyền `contentLength=0` vào overload hai tham số | `IllegalArgumentException`. | Dùng `BodyPublishers.noBody()` nếu không gửi payload. |
| Publisher bỏ qua `request(n)` | Vi phạm backpressure; subscriber có thể quá tải hoặc giao thức phát lỗi. | Chỉ phát theo số **item** được yêu cầu, quản lý queue/buffer. |
| Nghĩ `request(1)` là xin một byte | Sai đơn vị; một item có thể chứa nhiều byte. | Phân biệt demand item và content length byte. |
| Không gọi `onComplete()` sau khi hết input | HTTP client có thể chờ request body hoàn tất. | Phát đúng một terminal signal khi stream xong. |
| Chỉnh sửa `ByteBuffer` sau `onNext` | Có thể làm hỏng byte đang gửi. | Bàn giao ownership, cấp buffer mới hoặc bảo đảm an toàn vòng đời. |
| Gắn nguồn một lần với request được gửi lại | Body lần gửi sau thiếu/khác dữ liệu. | Dùng publisher replayable, dữ liệu ổn định mỗi subscription. |
| Truyền publisher nhưng không gọi `send`/`sendAsync` | Request chỉ tồn tại trong bộ nhớ; chưa gửi đi. | Xây `HttpRequest`, rồi gửi bằng `HttpClient`. |
| Nghĩ `fromPublisher` tự thêm `Content-Type: application/json` | Header không được suy ra từ kiểu publisher. | Tự đặt đúng `Content-Type` theo payload. |
| Dùng `Flow.Publisher<List<ByteBuffer>>` của response body như đầu vào trực tiếp | Sai kiểu so với request publisher; hai hướng có API khác nhau. | Chuyển đổi/flatten từng `ByteBuffer` đúng cách trước khi dùng làm request body. |

## 11. Tự kiểm tra

**Câu 1:** `Flow.Publisher<ByteBuffer>` phát 3 buffer lần lượt 100, 200 và 50 byte. Nếu subscriber gọi `request(2)` thì được phát tối đa bao nhiêu buffer? Tổng content length là bao nhiêu nếu gửi đủ?

**Đáp án:** Tối đa **2 buffer item** trước demand tiếp theo; tổng byte toàn body là **350** nếu cả 3 buffer được phát. `request(2)` không có nghĩa 2 byte.

**Câu 2:** `BodyPublishers.fromPublisher(source).contentLength()` trả giá trị gì?

**Đáp án:** `-1`, thể hiện không biết trước độ dài.

**Câu 3:** Khi có tổng 9 byte, nên dùng `fromPublisher(source, 9)` hay `fromPublisher(source, 2)` nếu nguồn phát 2 buffer?

**Đáp án:** `fromPublisher(source, 9)`, vì đối số là **số byte**, không phải số buffer.

**Câu 4:** Tại sao nguồn đọc từ một stream đã tiêu thụ hết có thể không phù hợp với HTTP client?

**Đáp án:** Khi HTTP client subscribe lại để phát lại request, nguồn không thể tạo lại cùng dữ liệu. Cần nguồn có thể phát lại hoặc một chiến lược lưu/phát lại phù hợp.

**Câu 5:** Sau khi publisher gọi `onNext(buffer)`, có thể `clear()` và ghi đè ngay lên cùng buffer để phát item kế tiếp không?

**Đáp án:** Không. HTTP client có thể đang dùng nội dung đó; publisher không được truy cập/thay đổi buffer đã bàn giao. Cần buffer có vòng đời an toàn.

**Câu 6:** `BodyPublishers.fromPublisher(source, 0)` dùng để gửi body rỗng có đúng không?

**Đáp án:** Không. Overload có độ dài cố định yêu cầu giá trị **dương** và ném `IllegalArgumentException` nếu `0`. Dùng `BodyPublishers.noBody()`.

**Ghi nhớ:** `BodyPublishers.fromPublisher` là cầu nối giữa `Flow.Publisher<ByteBuffer>` và request body trong Java 11+. Dùng overload một tham số khi chưa biết tổng byte (`contentLength() == -1`); dùng overload hai tham số khi biết **chính xác số byte dương**. Publisher phải tuân thủ **demand/backpressure**, **terminal signals**, **vòng đời `ByteBuffer`** và **khả năng phát lại cùng nội dung khi được subscribe lại**. Việc dựng publisher/request không đồng nghĩa request đã được gửi.

**Tham khảo chuẩn:** [Oracle Java SE 11 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html); [HttpRequest.BodyPublisher](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html); [Flow.Subscription](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.Subscription.html); [Oracle Java SE 25 — HttpRequest.BodyPublisher](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html).
