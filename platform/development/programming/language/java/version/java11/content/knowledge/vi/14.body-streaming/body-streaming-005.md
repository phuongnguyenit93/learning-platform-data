# `request(n)`, `cancel()`, `onNext()`, `onError()` và `onComplete()` trong Body Streaming của Java 11

## 1. Mục tiêu bài học

Khi HTTP client nhận một response lớn, không phải lúc nào ta cũng muốn gom toàn bộ nội dung vào `String` hoặc `byte[]`. Với **Java 11**, module `java.net.http` hỗ trợ nhận body theo luồng, dựa trên mô hình **Reactive Streams** được chuẩn hóa trong `java.util.concurrent.Flow`. Mô hình đó gồm publisher (bên phát), subscriber (bên nhận) và subscription (kết nối giữa hai bên).

Năm thao tác/tín hiệu cốt lõi của bài:

- **`request(long n)`**: subscriber yêu cầu nhận thêm tối đa `n` *phần tử* (`onNext` calls), tức cơ chế **demand/backpressure**.
- **`cancel()`**: subscriber tuyên bố không muốn tiếp tục nhận dữ liệu; publisher cố gắng ngừng phát và giải phóng tài nguyên.
- **`onNext(T item)`**: publisher chuyển một phần tử dữ liệu đến subscriber khi có demand.
- **`onError(Throwable error)`**: publisher báo lỗi không thể phục hồi; đây là một **terminal signal**.
- **`onComplete()`**: publisher báo đã phát hết dữ liệu bình thường; cũng là **terminal signal**.

Còn một callback nền tảng không thể bỏ qua là **`onSubscribe(Flow.Subscription)`**: subscriber được nhận subscription **trước** những callback dữ liệu/lỗi/kết thúc và thường gọi `request(n)` tại đây.

**Điểm riêng của HTTP response:** `HttpResponse.BodySubscriber<T>` kế thừa `Flow.Subscriber<List<ByteBuffer>>`, tức **mỗi lần `onNext` mang một `List<ByteBuffer>`**, không phải một byte hay một `ByteBuffer` đơn lẻ. Vì thế `request(1)` cho phép nhận *một danh sách buffer*, **không** phải một byte.

Kiến thức này vẫn áp dụng trên JDK hiện đại; các ví dụ độc lập sử dụng Java 11. Không dựa vào API chỉ xuất hiện ở bản JDK mới, không đồng nhất Flow backpressure với giới hạn bộ nhớ chính xác hoặc timeout HTTP.

## 2. Ba thành phần của `Flow`

| Thành phần | API Java 11 | Trách nhiệm |
| --- | --- | --- |
| Publisher | `Flow.Publisher<T>` | Cho phép subscriber đăng ký qua `subscribe(...)`; phát các phần tử và tín hiệu terminal |
| Subscriber | `Flow.Subscriber<T>` | Nhận `onSubscribe`, `onNext`, `onError`, `onComplete`; quyết định tốc độ yêu cầu thêm |
| Subscription | `Flow.Subscription` | Kết nối từng subscriber với publisher; cung cấp `request(long)` và `cancel()` |

Một subscription là hợp đồng riêng giữa một subscriber và publisher. Subscriber phải giữ tham chiếu subscription do `onSubscribe` cung cấp để gọi `request` hoặc `cancel`; không được tự tạo subscription giả để điều khiển HTTP client thật.

Đối với **response body của `HttpClient`**, HTTP client đóng vai trò publisher byte response; custom `HttpResponse.BodySubscriber<T>` là bên nhận. Trong mỗi `onNext`, bạn nhận một **danh sách không thể chỉnh sửa của các `ByteBuffer` chỉ đọc** theo implementation note Java 11. Các list và buffer được gửi theo thứ tự byte của response.

Đối với **request body gửi đi**, `HttpRequest.BodyPublisher` là **publisher của `ByteBuffer`**, còn HTTP client là subscriber nhận các byte để gửi lên mạng. Hai chiều tuân theo Flow nhưng **kiểu phần tử của chúng khác nhau**:

| Luồng dữ liệu | Publisher/Subscriber liên quan | Kiểu mỗi `onNext` |
| --- | --- | --- |
| Gửi HTTP request body | `HttpRequest.BodyPublisher` → HTTP client | `ByteBuffer` |
| Nhận HTTP response body | HTTP client → `HttpResponse.BodySubscriber<T>` | `List<ByteBuffer>` |
| `SubmissionPublisher<T>` trong ví dụ học Flow | `SubmissionPublisher<T>` → subscriber tùy chọn | `T` do ta lựa chọn |

**Không dùng `BodyPublisher` và `BodySubscriber` như hai tên thay thế cho nhau**: thứ nhất phát request body, thứ hai nhận response body.

## 3. Chu trình sự kiện tiêu chuẩn

Dòng sự kiện của một subscription bình thường:

```text
Publisher                         Subscriber
    |                                 |
    |------ onSubscribe(sub) -------->|
    |                                 |---- sub.request(n) ---->|
    |------ onNext(item 1) ---------->|
    |------ onNext(item 2) ---------->|
    |            ...                  |---- sub.request(m) ---->|
    |------ onNext(item ...) -------->|
    |------ onComplete() ------------>|
    |                                 |
    |  Kết thúc: không có tín hiệu tiếp theo
```

Nếu phát sinh lỗi không thể tiếp tục, `onError(Throwable)` thay thế `onComplete()`:

```text
onSubscribe → onNext* → onError(error)
```

Khi subscriber chủ động hủy:

```text
onSubscribe → onNext* → cancel()
           → [publisher cố gắng dừng]
           → không bắt buộc onComplete hoặc onError
```

**Các bất biến quan trọng theo `Flow.Subscriber`:**

1. `onSubscribe` được gọi trước những phương thức callback khác của subscription đó.
2. Các lời gọi callback đến một subscriber trong **một subscription** được gọi theo thứ tự tuần tự; không nên tự suy ra chúng luôn chạy trên cùng một thread.
3. `onComplete` và `onError` là **hai dạng terminal khác nhau**. Sau một trong hai tín hiệu, subscription đó không được tiếp tục gọi callback.
4. `onError` không phải tín hiệu “HTTP status 4xx/5xx”. HTTP 404 vẫn có thể có body được phát bình thường và kết thúc bằng `onComplete`. Kiểm tra status code riêng.
5. `cancel()` không nhất thiết phát tín hiệu terminal; việc chờ mãi `onComplete` sau `cancel()` có thể làm workflow bị treo.

Không viết callback `onNext` có logic block lâu, truy vấn mạng đồng bộ hoặc gom mọi item vào bộ nhớ không giới hạn mà không tính backpressure và tài nguyên.

## 4. `request(long n)`: điều khiển demand

`Flow.Subscription.request(n)` **cộng thêm** `n` vào lượng demand chưa đáp ứng của subscription. Mỗi lần `onNext` thành công tiêu thụ một đơn vị demand; publisher chỉ có thể phát số item `onNext` tương ứng với demand còn lại (trừ khi subscription đã kết thúc nên có thể nhận ít hơn).

Ví dụ subscriber gọi:

```java
subscription.request(1);
```

Nó đang nói: “Tôi sẵn sàng nhận **thêm một item**”. Khi nhận xong `onNext`, subscriber có thể xử lý item rồi gọi tiếp:

```java
@Override
public void onNext(List<ByteBuffer> buffers) {
    for (ByteBuffer buffer : buffers) {
        process(buffer);
    }
    subscription.request(1);
}
```

Đây là **trích đoạn minh họa**, cần lớp có biến `subscription` kiểu `Flow.Subscription` và phương thức `process(ByteBuffer)`. Ý nghĩa: yêu cầu một **batch** mới sau khi xử lý xong batch hiện tại.

### 4.1. `n` là số item, không phải số byte

Với `HttpResponse.BodySubscriber`, một item là một `List<ByteBuffer>` có thể chứa nhiều buffer, mỗi buffer có nhiều byte. Vì vậy:

- `request(1)` có nghĩa là xin thêm **một `onNext(List<ByteBuffer>)`**.
- `request(3)` cho phép thêm tối đa **ba `onNext`**.
- `request(Long.MAX_VALUE)` có thể được hiểu là demand **gần như không giới hạn**.
- `request(n)` không yêu cầu chính xác `n` byte, không bảo đảm list chỉ có `n` buffer và không xác định kích thước byte của batch.

Ví dụ một response 1 MiB có thể được chuyển thành số lượng batch khác nhau tùy HTTP client, mạng, protocol và xử lý backpressure. Không thiết kế logic nghiệp vụ phụ thuộc số lần `onNext` hoặc số buffer trong mỗi list nếu hợp đồng ứng dụng không định nghĩa chúng.

### 4.2. `request(0)` và `request(-1)` không hợp lệ

Theo hợp đồng Java 11 `Flow.Subscription`, gọi `request(n)` với **`n <= 0`** gây tín hiệu `onError` với `IllegalArgumentException`; đó là **lỗi giao thức demand**, không phải phép hỏi “tôi có đang rảnh không?”.

**Không dùng:**

```java
subscription.request(0);   // Không hợp lệ.
subscription.request(-10); // Không hợp lệ.
```

Nếu subscriber hiện chưa thể xử lý thêm, **đừng yêu cầu thêm**. Nếu không còn cần dữ liệu, gọi `cancel()`. Khi thiết kế cửa sổ demand, tính toán sao cho số được đưa vào `request` luôn dương; demand tăng cộng dồn và đạt mức `Long.MAX_VALUE` được xem như gần như không giới hạn.

### 4.3. Demand không phải bộ giới hạn bộ nhớ tuyệt đối

`request(1)` giúp điều chỉnh tốc độ phát, nhưng **không cam kết chỉ có một byte được lưu trong heap**. Một item `List<ByteBuffer>` có thể lớn, bản thân publisher/HTTP client có bộ đệm, và callback của bạn có thể tích lũy dữ liệu khác.

Muốn kiểm soát bộ nhớ còn cần:

- Không gom toàn bộ response vào `ByteArrayOutputStream` hoặc `List` nếu body có thể lớn.
- Giới hạn tổng byte đã xử lý, kích thước bản ghi, số request đồng thời và phần dữ liệu đang chờ.
- Dừng/cancel nếu vượt giới hạn theo chính sách đã xác định.
- Đo sử dụng heap và backpressure thực tế ở tải đại diện.

## 5. `onNext(T item)`: nhận và xử lý dữ liệu

Với HTTP response, callback có dạng:

```java
@Override
public void onNext(List<ByteBuffer> buffers) {
    for (ByteBuffer buffer : buffers) {
        while (buffer.hasRemaining()) {
            byte value = buffer.get();
            // Xử lý mỗi byte; nếu cần chuyển sang nơi khác,
            // lưu dữ liệu an toàn trước khi callback kết thúc.
        }
    }
    subscription.request(1);
}
```

Đây là **trích đoạn**, không phải lớp chạy độc lập. Việc đọc bằng `get()` làm thay đổi `position` của buffer đó; vì `BodySubscriber` Java 11 được cung cấp các buffer **read-only** (không ghi được), bạn vẫn có thể đọc và di chuyển vị trí đọc theo hợp đồng `ByteBuffer`. Nếu cần giữ trạng thái vị trí gốc, dùng `buffer.duplicate()` để tạo view với `position/limit` riêng.

**Lưu ý với dữ liệu nhị phân và text:**

- Dữ liệu được gửi thành **nhiều chunk**; một chuỗi UTF-8 có thể bị cắt giữa các byte của cùng một Unicode code point. Đừng giải mã mỗi `ByteBuffer` riêng như một chuỗi độc lập rồi nối; dùng `CharsetDecoder` duy trì trạng thái, hoặc `BodyHandlers.ofString`/`fromLineSubscriber` khi phù hợp mục tiêu.
- Nếu cần lưu buffer sang hàng đợi xử lý bất đồng bộ, phải có giới hạn hàng đợi/backpressure và chính sách sở hữu dữ liệu rõ ràng. Không giả định có thể giữ tùy tiện reference trong môi trường có mutable source hoặc thay đổi vị trí/đời sống dữ liệu.
- `ByteBuffer.remaining()` là số **byte chưa đọc** của buffer hiện tại. Cộng `remaining()` trước khi đọc là cách nhanh để đếm byte nhưng không phải cơ chế tự kiểm tra giới hạn tổng; hãy kiểm tra overflow nếu dữ liệu không kiểm soát.
- Với xử lý ghi file, database hoặc một sink chậm, cần thiết kế demand theo thời điểm **sink đã tiêu thụ an toàn**, thay vì luôn gọi `request(Long.MAX_VALUE)` trong `onSubscribe`.

### 5.1. Nếu xử lý item thất bại thì sao?

Không nên mặc định `throw` ra khỏi `onNext` sẽ được biến thành `onError` một cách an toàn. Javadoc `Flow.Subscriber` nói hành vi có thể không bảo đảm nếu callback ném exception, và có thể làm subscription bị cancel. Thiết kế rõ việc:

1. Bắt lỗi của logic xử lý trong callback.
2. Ghi nhận thất bại vào trạng thái kết quả ứng dụng.
3. **`cancel()`** subscription nếu không thể tiếp tục.
4. Không request thêm sau khi đã lỗi hoặc hủy.
5. Đóng nguồn/sink do ứng dụng sở hữu và thông báo lỗi cho caller.

`onError` là tín hiệu từ **publisher/subscription**; lỗi do chính subscriber xử lý sai cần được quản lý hợp lý thay vì gọi trực tiếp `onError` như thể publisher đã phát lỗi.

## 6. `onError(Throwable)`: nhánh thất bại

`onError` báo rằng luồng không thể hoàn thành bình thường. Các tình huống thực tế gồm lỗi I/O đọc body, lỗi giao thức, hoặc sai demand (`request(0)`). Callback này là **terminal** cho subscription đó.

Mẫu xử lý:

```java
@Override
public void onError(Throwable error) {
    result.completeExceptionally(error);
    closeOwnedSink();
}
```

Đây là **trích đoạn**; `result` được giả định là `CompletableFuture` của ứng dụng và `closeOwnedSink()` là hàm cleanup do code tự triển khai. Không được để `onError` tiếp tục ném exception: hợp đồng `Flow.Subscriber` quy định hành vi **không xác định** nếu chính `onError` ném lỗi.

Phân biệt:

- **Network/transport error**: có thể dẫn đến `onError`.
- **HTTP 404/500**: vẫn là HTTP response có status code, có thể có body nhận đủ và `onComplete` bình thường; status khác 2xx **không tự động** tương đương `onError`.
- **Lỗi logic ở sink**: có thể cần hủy subscription và hoàn thành future của ứng dụng ở trạng thái lỗi; không đợi vô thời hạn tín hiệu từ publisher sau khi hủy.

Chính sách retry request ở tầng ứng dụng phải xem xét idempotency, deadline, tình trạng server đã xử lý hay chưa và nguyên nhân lỗi. `onError` không tự động bảo đảm retry an toàn.

## 7. `onComplete()`: kết thúc nhận body bình thường

`onComplete()` cho biết publisher đã **phát hết dữ liệu của subscription** một cách bình thường. Với body response, đây là thời điểm phù hợp để hoàn tất checksum, xác nhận số byte đã nhận, flush/close sink và hoàn thành kết quả của subscriber nếu ứng dụng cần toàn bộ body.

```java
@Override
public void onComplete() {
    result.complete(totalBytes);
}
```

Đây là **trích đoạn** cần `CompletableFuture<Long> result` và `long totalBytes`. Không đợi thêm `onNext` sau khi đã nhận `onComplete`.

Nhưng cần phân biệt:

1. `onComplete()` của **body stream** không đồng nghĩa server trả status 2xx. HTTP status phải kiểm tra riêng.
2. `onComplete()` không bảo đảm sink của bạn đã bền vững trên đĩa nếu sink còn buffer cần flush hoặc transaction chưa commit.
3. Với `BodySubscriber<T>`, `getBody()` cung cấp `CompletionStage<T>`; thời điểm stage hoàn thành phụ thuộc kiểu `T`. Nếu `T` là một giá trị thu thập đầy đủ, nó thường hoàn thành sau khi nhận hết; nếu `T` là kiểu streaming như `InputStream`, stage có thể hoàn thành **trước khi mọi byte body được đọc**.
4. Với `BodyHandlers.ofPublisher()`, response có thể được cung cấp sau header trong khi body vẫn đang stream; caller phải subscribe vào publisher được trả về và tiêu thụ/cancel đúng cách.

Vì vậy, không dùng một tín hiệu duy nhất để suy ra “mọi tài nguyên HTTP, xử lý nghiệp vụ và file đều đã hoàn tất” mà không kiểm tra hợp đồng API và sink thực tế.

## 8. `cancel()`: hủy và giải phóng tài nguyên

`Flow.Subscription.cancel()` yêu cầu publisher **cuối cùng ngừng gửi tín hiệu** tới subscriber. Đây là cơ chế **best effort**; Javadoc Java 11 nêu rõ:

- Có thể vẫn có thêm tín hiệu tới subscriber sau khi gọi `cancel()`.
- Subscription đã cancel **không bắt buộc** phát `onComplete` hoặc `onError`.
- `cancel()` không nên được hiểu là “gọi xong chắc chắn tất cả I/O đã dừng ngay”.
- Với HTTP response body, hủy trước khi đọc hết có thể làm **đóng kết nối HTTP nền** và giảm khả năng tái sử dụng kết nối, tùy phiên bản giao thức và implementation.

Khi nào nên cancel:

- Người dùng bỏ thao tác download.
- Ứng dụng vượt giới hạn byte/record và không muốn nhận thêm.
- Sink đã lỗi, không thể tiếp tục xử lý.
- Deadline nghiệp vụ hết và không còn cần body.

Khi nào nên **tiếp tục request đến EOF**: nếu response body cần được đọc hết và ứng dụng có thể xử lý an toàn, hãy cấp demand tiếp cho đến `onComplete` hoặc `onError`. Đây thường là hướng giúp HTTP client giải phóng tài nguyên và có cơ hội tái sử dụng kết nối.

**Không viết:**

```java
subscription.cancel();
completionFuture.join(); // Có thể treo nếu chỉ hoàn thành trong onComplete/onError.
```

Đây là **anti-pattern minh họa**, `completionFuture` được giả định là future chỉ hoàn thành trong callback terminal. Nếu subscriber chủ động cancel, hãy **tự hoàn thành trạng thái hủy của ứng dụng** bằng cơ chế riêng (ví dụ future của consumer, token hủy, callback cleanup) theo hợp đồng nghiệp vụ; đừng dựa vào terminal signal sẽ xuất hiện sau cancel.

`cancel()` không tương đương `HttpClient.close()`, không nhất thiết hủy request khác đang sử dụng client, và không thay thế việc đóng file/socket/sink **do ứng dụng** tạo ra.

## 9. Chương trình Java 11 chạy độc lập: backpressure từng batch

Chương trình dùng `SubmissionPublisher<List<ByteBuffer>>` để mô phỏng **hình dạng dữ liệu của HTTP response body** nhưng **không gọi mạng**. Subscriber chỉ request **một batch mỗi lần**, nhận hai batch, đếm tổng byte và đợi tín hiệu `onComplete()`. Điều này minh họa các callback Flow thực sự mà không phụ thuộc HTTP server.

Tạo tệp **`FlowBodyStreamingDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;

public class FlowBodyStreamingDemo {

    static final class CountingSubscriber
            implements Flow.Subscriber<List<ByteBuffer>> {
        private Flow.Subscription subscription;
        private long bytes;
        private int batches;
        private final CompletableFuture<Long> done =
                new CompletableFuture<>();

        @Override
        public void onSubscribe(Flow.Subscription sub) {
            subscription = sub;
            System.out.println("onSubscribe: request(1)");
            sub.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> buffers) {
            long batchBytes = 0;
            for (ByteBuffer buffer : buffers) {
                batchBytes += buffer.remaining();
            }
            batches++;
            bytes += batchBytes;
            System.out.println("onNext: batch " + batches
                    + ", bytes=" + batchBytes);

            // Chỉ xin batch tiếp theo sau khi đã xử lý batch này.
            subscription.request(1);
        }

        @Override
        public void onError(Throwable error) {
            done.completeExceptionally(error);
        }

        @Override
        public void onComplete() {
            System.out.println("onComplete");
            done.complete(bytes);
        }

        long awaitBytes() {
            return done.join();
        }

        int batchCount() {
            return batches;
        }

        long totalBytes() {
            return bytes;
        }
    }

    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (SubmissionPublisher<List<ByteBuffer>> publisher =
                new SubmissionPublisher<>(executor, 8)) {
            CountingSubscriber subscriber = new CountingSubscriber();
            publisher.subscribe(subscriber);

            publisher.submit(List.of(
                    ByteBuffer.wrap(
                            "Hi".getBytes(StandardCharsets.UTF_8)),
                    ByteBuffer.wrap(
                            "!".getBytes(StandardCharsets.UTF_8))));
            publisher.submit(List.of(
                    ByteBuffer.wrap(
                            "Java".getBytes(StandardCharsets.UTF_8))));
            publisher.close();

            long received = subscriber.awaitBytes();
            System.out.println("Summary: batches="
                    + subscriber.batchCount()
                    + ", bytes=" + received);
        } finally {
            executor.shutdown();
        }
    }
}
```

Biên dịch và chạy bằng **JDK 11**:

```bash
javac --release 11 -encoding UTF-8 FlowBodyStreamingDemo.java
java FlowBodyStreamingDemo
```

**Đầu ra xác định theo các batch được phát:**

```text
onSubscribe: request(1)
onNext: batch 1, bytes=3
onNext: batch 2, bytes=4
onComplete
Summary: batches=2, bytes=7
```

**Giải thích kết quả:**

- `onSubscribe` nhận subscription và request **1 item**.
- Batch 1 chứa **hai `ByteBuffer`**, lần lượt là `"Hi"` (2 byte ASCII) và `"!"` (1 byte): chỉ **một** `onNext` nhưng tổng 3 byte.
- Subscriber xử lý batch 1 rồi `request(1)` tiếp; batch 2 chứa `"Java"` (4 byte).
- Khi publisher `close()`, dữ liệu đã nhận được xử lý hết và publisher gửi `onComplete`.
- `awaitBytes()` đợi `CompletableFuture` của ứng dụng hoàn thành khi nhận `onComplete`; kết quả 7 byte từ 2 batch.
- Dùng executor một luồng để minh họa thứ tự dễ hiểu. Callback `Flow` nói chung không buộc chạy trên một thread cố định; không thiết kế dựa vào giả định ấy.
- `SubmissionPublisher` chỉ là nguồn dữ liệu mô phỏng cho bài học, **không phải `HttpClient`**. Nó giúp thử logic Flow mà không dùng mạng. `publisher.close()` là phương thức riêng của `SubmissionPublisher`; đừng nhầm với `cancel()` của `Flow.Subscription` hoặc lifecycle của HTTP client.

Ở đây `List.of` là Java 9+, `SubmissionPublisher` là Java 9+, `ByteBuffer`, `Flow` và `CompletableFuture` đều khả dụng trong Java 11. Khi tự xử lý HTTP thực, hình dạng `List<ByteBuffer>` đến từ `HttpClient` thay vì một `SubmissionPublisher` tự tạo.

## 10. Gắn Flow subscriber vào HTTP response thực tế

Cách đơn giản nhất nếu chỉ cần các handler phổ biến là dùng `HttpResponse.BodyHandlers.ofString()`, `ofByteArray()`, `ofFile(...)`, `ofInputStream()` hoặc `ofLines()` phù hợp. Với nhu cầu **tự kiểm soát backpressure và xử lý batch**, Java 11 có adapter:

```java
HttpResponse.BodyHandlers.fromSubscriber(subscriber)
HttpResponse.BodyHandlers.fromSubscriber(subscriber, finisher)
```

- Phiên bản **một tham số** tạo `BodyHandler<Void>`: body byte được chuyển cho subscriber, không trả nội dung body hoàn chỉnh qua `HttpResponse.body()`; subscriber phải cung cấp kết quả/side effect qua cơ chế riêng.
- Phiên bản **hai tham số** tạo `BodyHandler<T>`: `finisher` được áp dụng **sau khi subscriber nhận `onComplete`** và trả kết quả gắn vào `response.body()`.
- Adapter nhận `Flow.Subscriber<? super List<ByteBuffer>>`, không nhận `Flow.Subscriber<ByteBuffer>` hoặc `Flow.Subscriber<byte[]>`.

Ví dụ **trích đoạn Java 11**, đặt trong một phương thức, dùng `CountingSubscriber` đã định nghĩa trong chương trình độc lập, `client` kiểu `HttpClient` và `request` kiểu `HttpRequest`:

```java
CountingSubscriber counter = new CountingSubscriber();

HttpResponse.BodyHandler<Long> handler =
        HttpResponse.BodyHandlers.fromSubscriber(
                counter, CountingSubscriber::totalBytes);

HttpResponse<Long> response = client.send(request, handler);
int statusCode = response.statusCode();
long responseBytes = response.body();
```

Đoạn này cần import `java.net.http.HttpResponse` và xử lý `IOException`/`InterruptedException`, cũng cần HTTP endpoint thực; **không phải chương trình chạy độc lập**. Nó thể hiện: dữ liệu body đi qua `counter.onNext(List<ByteBuffer>)`, còn `response.body()` được tạo bởi finisher sau khi nhận hết body thành công. Không dùng **cùng một subscriber instance** để xử lý nhiều response đồng thời nếu subscriber đó không được thiết kế đặc biệt cho multi-subscription; thường tạo instance mới cho mỗi response.

**Phân biệt thêm `HttpResponse.BodySubscriber<T>` trực tiếp:** ngoài các callback `Flow.Subscriber<List<ByteBuffer>>`, lớp này có `getBody()` trả `CompletionStage<T>`; nếu tự triển khai, phải định nghĩa khi stage hoàn tất thành công hoặc thất bại. Dùng `BodyHandlers.fromSubscriber` giúp tái sử dụng `Flow.Subscriber` thông thường mà không cần tự viết toàn bộ `BodySubscriber`.

## 11. Một quy tắc cực quan trọng về đóng hoặc hủy body

Tài liệu `HttpResponse.BodySubscriber` Java 11 khuyến nghị:

> Nếu có thể tiếp tục xử lý, subscriber nên tiếp tục `request` dữ liệu cho đến `onComplete` hoặc `onError`; nếu không thể tiếp tục thì `cancel` subscription.

Lý do: một exchange HTTP còn body chưa được đọc hết có thể giữ kết nối/tài nguyên. Hủy trước khi nhận hết body có thể khiến kết nối nền bị đóng và không tái sử dụng được cho request sau.

Chú ý trường hợp body trả ra **publisher** bằng `BodyHandlers.ofPublisher()`:

- `HttpResponse.body()` là một `Flow.Publisher<List<ByteBuffer>>` để caller đăng ký.
- Publisher body này cho phép **một subscriber**; không phải nguồn replayable vô hạn.
- Caller phải subscribe, yêu cầu dữ liệu đến hết hoặc cancel khi không cần nữa.
- Chỉ nhận được `HttpResponse` và header không đồng nghĩa byte body đã được tiêu thụ xong.
- Không đợi quá trình xử lý body kết thúc nếu bạn chưa subscribe/request dữ liệu mà lại đang chờ một tín hiệu phụ thuộc vào việc tiêu thụ ấy.

Cần quản lý deadline, cancellation, cleanup file/network và số request đang hoạt động riêng, vì Flow signal chỉ là một phần của vòng đời HTTP.

## 12. Tự triển khai `BodySubscriber`: các điểm cần kiểm tra

Khi cần viết class triển khai `HttpResponse.BodySubscriber<T>` thay vì dùng handler sẵn có, hãy thiết kế:

1. **`getBody()` có thể được gọi bất kỳ lúc nào** so với các callback Flow; trả về cùng cơ chế `CompletionStage<T>` hợp lệ, không đợi `onComplete` rồi mới có thể lấy stage.
2. `onSubscribe` lưu subscription, chuẩn bị trạng thái và gọi `request(n > 0)`.
3. `onNext(List<ByteBuffer>)` đọc byte **theo đúng thứ tự list**, không giữ mọi byte trong heap khi body lớn.
4. `onError` hoàn thành stage thất bại và cleanup tài nguyên do ứng dụng sở hữu.
5. `onComplete` hoàn thành stage bình thường sau khi xử lý xong dữ liệu, trừ khi kiểu body có ngữ nghĩa streaming khác.
6. Nếu không còn muốn nhận byte, `cancel` subscription; **không chờ terminal bắt buộc sau cancel**.
7. Không gọi `request` khi subscriber đã terminal hoặc đã hủy.
8. Không tự phát `onNext` hoặc `onComplete` để “đẩy nhanh HTTP client”; các callback thuộc publisher.
9. Kiểm soát lỗi tại callback và đảm bảo lỗi business/sink không khiến callback ném exception không kiểm soát.
10. Với dữ liệu text, dùng decoder streaming để tránh chia sai code point Unicode giữa các batch.

**Đừng luôn bắt buộc viết custom BodySubscriber.** API có sẵn `BodyHandlers.ofFile`, `ofInputStream`, `ofLines` và `fromLineSubscriber` thường dễ bảo trì hơn nếu khớp nhu cầu; custom subscriber phù hợp khi thật sự cần tiêu thụ byte theo batch, chuyển dữ liệu vào pipeline riêng hoặc tự kiểm soát demand.

## 13. Cancel khác failure, terminal khác HTTP status

Một số cách hiểu sai dẫn đến bug:

| Trường hợp | Sự kiện Flow phù hợp | Ý nghĩa |
| --- | --- | --- |
| Nhận đủ tất cả body một cách bình thường | `onComplete()` | Stream kết thúc thành công ở tầng publisher |
| Publisher/subscription gặp lỗi không thể tiếp tục | `onError(Throwable)` | Stream kết thúc thất bại |
| Subscriber không muốn nhận body nữa | `subscription.cancel()` | Yêu cầu dừng best effort; không đòi terminal callback |
| HTTP 404 có body nhận đầy đủ | Có thể `onNext*` rồi `onComplete` | Status code 404 là kết quả HTTP, không tự động là `onError` |
| HTTP 200 nhưng connection đứt giữa body | Có thể `onError` | Có header/status 200 không đảm bảo body được nhận đủ |
| `request(0)` | `onError(IllegalArgumentException)` theo Flow contract | Demand không hợp lệ |
| `request(1)` với item `List<ByteBuffer>` chứa 1 MiB | Một `onNext` có thể đưa 1 MiB | Demand là số item, không phải số byte |

Trong thiết kế nghiệp vụ, đừng kết luận “download thành công” chỉ từ HTTP status 200, và đừng kết luận “HTTP request thất bại” chỉ vì user chủ động cancel body nếu business có chủ đích hủy.

## 14. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Quên `request(n)` trong `onSubscribe` | Không có demand, publisher có thể không gửi `onNext`, pipeline đứng chờ | Request giá trị dương hoặc quyết định cancel |
| Gọi `request(0)` để “tạm dừng” | Sai hợp đồng; `onError(IllegalArgumentException)` | Muốn tạm dừng thì **chưa gọi request thêm** |
| Dùng `request(Long.MAX_VALUE)` dù xử lý chậm | Dễ vượt khả năng sink/buffer nếu không kiểm soát | Chia demand thành từng đợt, giới hạn tài nguyên |
| Tưởng `request(1)` nghĩa là 1 byte | Dễ tính sai kích thước và bộ nhớ | 1 item `List<ByteBuffer>` có thể chứa nhiều byte |
| Xử lý trong `onNext` xong mà không request nữa | Dừng nhận data mặc dù chưa hết response | Gọi `request` tiếp sau khi tiêu thụ xong |
| Gọi `cancel` rồi chờ `onComplete` bắt buộc | Có thể treo vì cancel không bảo đảm terminal | Quản lý trạng thái hủy riêng |
| Gọi `onError` thủ công khi business validation fail | Nhầm callback publisher với xử lý lỗi subscriber | Cancel và thông báo lỗi qua future/trạng thái ứng dụng |
| Để exception thoát khỏi `onNext` hoặc `onError` | Hành vi sau đó không bảo đảm | Bắt lỗi, cancel, hoàn thành kết quả/cleanup an toàn |
| Không kiểm tra HTTP status | Nhận đủ body HTTP 500 rồi tưởng nghiệp vụ thành công | Kiểm tra `response.statusCode()` riêng |
| Gom mọi buffer vào `List` không giới hạn | Dùng heap tăng theo kích thước body | Xử lý/chuyển tiếp incremental, đặt limit |
| Giải mã UTF-8 mỗi batch độc lập | Lỗi khi ký tự chia qua batch | `CharsetDecoder` có trạng thái hoặc handler phù hợp |
| Tưởng `onComplete` đồng nghĩa file đã durable | Sink có thể chưa flush/commit | Hoàn tất sink theo hợp đồng I/O |
| Gọi cancel mọi lúc để “tối ưu” | Có thể giảm tái sử dụng kết nối | Nếu có thể, tiêu thụ hết; cancel khi thật sự không cần |
| Coi `close()` trên publisher demo là `cancel()` | Nhầm vòng đời nguồn phát với từng subscription | Quản lý đúng cấp độ owner và Flow subscription |

## 15. Bài luyện tập tự kiểm tra

**Bài 1.** Subscriber HTTP gọi `subscription.request(2)`. Mỗi `onNext` chứa một `List<ByteBuffer>` có 5 buffer. Có phải subscriber yêu cầu 2 byte hay 2 buffer?

**Đáp án:** Không. Nó yêu cầu tối đa **2 lần `onNext`**, mỗi lần có thể chứa nhiều `ByteBuffer` và nhiều byte; tổng kích thước byte không xác định chỉ từ `request(2)`.

**Bài 2.** Gọi `subscription.request(0)` có phải cách hợp lệ để tạm dừng 2 giây?

**Đáp án:** Không. `n <= 0` vi phạm hợp đồng và dẫn đến `onError(IllegalArgumentException)`. Để không nhận thêm batch, đơn giản là chưa gọi `request` mới cho đến khi ready; để dừng hẳn thì `cancel`.

**Bài 3.** Sau `cancel()` mà không bao giờ nhận `onComplete()` thì publisher có vi phạm Java 11 `Flow.Subscription` không?

**Đáp án:** Không. Đã cancel thì publisher **không bắt buộc** gửi `onComplete`/`onError`. Đây là lý do không đợi future chỉ hoàn thành trong terminal khi chính bạn đã cancel.

**Bài 4.** HTTP server trả status 404 và gửi đầy đủ trang lỗi. Có phải custom subscriber bắt buộc được gọi `onError`?

**Đáp án:** Không. Response vẫn có body hợp lệ được truyền qua `onNext` và có thể kết thúc `onComplete`. Status 404 phải xử lý riêng.

**Bài 5.** Body bị ngắt vì network sau khi đã nhận 3 batch. Có thể nhận tín hiệu nào?

**Đáp án:** Thường là `onError` do lỗi truyền; đã terminal thì không chờ thêm `onNext` hoặc `onComplete` cho subscription đó.

**Bài 6.** Trong mã ví dụ, hai batch có `3` và `4` byte, subscriber dùng `request(1)` sau từng `onNext`. Kết quả tổng?

**Đáp án:** **2 batch, 7 byte**. Hai item Flow không đồng nghĩa hai byte.

**Bài 7.** Một sink ghi file bị lỗi trong `onNext`. Có nên ném exception không kiểm soát hoặc chờ `onComplete`?

**Đáp án:** Không. Ghi nhận lỗi, `cancel` subscription khi không thể tiếp tục, giải phóng tài nguyên và hoàn thành trạng thái thất bại của ứng dụng; tránh phụ thuộc vào terminal sau cancel.

## 16. Checklist triển khai và tài liệu tham khảo

Checklist trước khi đưa subscriber vào ứng dụng:

1. Có phân biệt request body (`Publisher<ByteBuffer>`) với response body (`Subscriber<List<ByteBuffer>>`) không?
2. `onSubscribe` có xử lý subscription hợp lệ và yêu cầu lượng data dương không?
3. Demand có được điều chỉnh theo tốc độ xử lý của downstream, không tính nhầm số byte?
4. `onNext` có xử lý theo đúng thứ tự buffer, giải mã streaming và giới hạn dung lượng không?
5. `onError`/`onComplete` có bảo đảm kết quả/future và cleanup của ứng dụng không?
6. Sau `cancel` có tránh chờ terminal bắt buộc và không tiếp tục request không?
7. Có kiểm tra HTTP status code độc lập với kết thúc Flow không?
8. Có đóng/hủy/tiêu thụ response body để không giữ tài nguyên HTTP lâu hơn cần thiết không?
9. Có test body rỗng, body lớn, network error, cancel, request(0), byte split ở ranh giới và slow sink không?
10. Có tránh dùng API chưa có ở JDK 11 nếu mục tiêu biên dịch là `--release 11` không?

**Ghi nhớ:** `request(n)` điều khiển **số item `onNext`**, `cancel()` yêu cầu dừng **best effort**, `onNext` giao dữ liệu, còn `onError` và `onComplete` là hai **terminal signal loại trừ nhau**. Trong HTTP response Java 11, **một item = một `List<ByteBuffer>`**. Backpressure giúp phối hợp tốc độ, nhưng cần giới hạn byte, concurrency và cleanup bổ sung.

Tài liệu Oracle Java SE 11 (còn áp dụng trên JDK hiện đại):

- [`Flow.Subscription` (Java SE 11)](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.Subscription.html) — `request(n)`, `cancel` và quy tắc demand.
- [`Flow.Subscriber` (Java SE 11)](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html) — `onSubscribe`, `onNext`, `onError`, `onComplete`.
- [`HttpResponse.BodySubscriber` (Java SE 11)](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html) — `Flow.Subscriber<List<ByteBuffer>>` và trách nhiệm drain/cancel.
- [`HttpResponse.BodyHandlers` (Java SE 11)](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html) — `fromSubscriber`, `ofPublisher`, `fromLineSubscriber`.
- [`HttpRequest.BodyPublisher` (Java SE 11)](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html) — chiều gửi request body qua Flow.
- [`Flow.Subscription` (Java SE 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Flow.Subscription.html) — đối chiếu API tiếp tục hiện diện trên JDK hiện đại.
