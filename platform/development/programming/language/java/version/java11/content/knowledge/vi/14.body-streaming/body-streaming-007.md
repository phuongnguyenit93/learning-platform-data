# Backpressure và giới hạn tốc độ xử lý khi streaming HTTP body — Java 11

## Mục tiêu

Khi tải một HTTP response lớn hoặc gửi một request body theo luồng, mạng có thể cung cấp dữ liệu nhanh hơn khả năng xử lý của ứng dụng. Nếu cứ đọc và đưa mọi chunk vào hàng đợi không giới hạn, bộ nhớ tăng theo dữ liệu chưa được xử lý; nếu xử lý blocking ngay trong callback I/O, nhiều kết nối khác có thể chậm theo. **Backpressure** là cơ chế cho phía tiêu thụ kiểm soát *số lượng phần tử được phép phát thêm* trước khi tiêu thụ tiếp, qua đó tạo đường truyền dữ liệu có giới hạn.

Java 11 có các API còn được hỗ trợ để thực hiện điều này: `java.util.concurrent.Flow`, `Flow.Subscription.request(long)`, `HttpResponse.BodyHandlers.ofPublisher()`, `BodyHandlers.fromSubscriber(...)` và `HttpRequest.BodyPublishers.fromPublisher(...)`. `BodySubscriber` của HTTP Client dùng chuẩn `Flow.Subscriber<List<ByteBuffer>>`; `BodyPublisher` của request dùng `Flow.Publisher<ByteBuffer>`. Hãy dùng đúng kiểu ở từng hướng dữ liệu.

Sau bài này, bạn sẽ biết:

1. Giải thích chính xác vòng đời `Publisher → Subscription → Subscriber`; phân biệt `request(1)` với «đọc một byte».
2. Dùng **demand hữu hạn** để nhận một batch HTTP body, giao việc xử lý sang executor riêng, và chỉ gọi `request(1)` tiếp khi batch trước đã được xử lý.
3. Phân biệt **backpressure**, **rate limiting (byte/giây hoặc request/giây)**, **giới hạn số request đồng thời**, **giới hạn tổng kích thước body** và **bộ nhớ đệm**.
4. Hạn chế tốc độ xử lý mà không dùng `Thread.sleep` bên trong `onNext` của luồng callback mạng; hiểu giới hạn của phương pháp pacing bằng thời gian.
5. Xử lý đúng `onComplete`, `onError`, `cancel`, response 4xx/5xx và hủy khi vượt ngưỡng dung lượng.
6. Chạy bài kiểm thử end-to-end bằng HTTP server cục bộ, xác minh nhận đủ byte, demand một batch mỗi lần, pacing và hủy khi vượt kích thước.
7. Biết khi nào chọn `ofInputStream()`, `ofLines()`, `ofPublisher()` hay một custom subscriber thay vì `ofString()`/`ofByteArray()`.

Các phương thức được dùng trong chương trình đều có sẵn trên Java 11; phần giới thiệu tránh những API chỉ xuất hiện ở JDK mới hơn baseline Java 11.

## 1. Tại sao streaming cần backpressure?

Ví dụ server trả body 2 GiB, còn ứng dụng chỉ có thể xử lý trung bình 4 MiB/giây. Nếu callback mạng nhận được bao nhiêu cũng đưa ngay vào một `ArrayList<byte[]>` hoặc `BlockingQueue` không giới hạn, sau một thời gian ngắn dữ liệu chưa được xử lý có thể tăng rất lớn, gây áp lực GC hoặc `OutOfMemoryError`.

Đường dữ liệu mong muốn:

~~~text
Network / HTTP Client
      |
      v
Flow.Publisher<List<ByteBuffer>>
      |
      | onSubscribe(subscription)
      | request(1)  <----------------------------+
      v                                         |
Flow.Subscriber.onNext(batch)                  |
      |                                         |
      v                                         |
bounded single-worker processing               |
      |                                         |
      +---- after processing -> request(1) -----+
      |
      v
onComplete / onError / cancel
~~~

Điểm cốt lõi không phải «đọc ít byte hơn trong một lần», mà là **không cấp thêm demand khi chưa có năng lực xử lý**. Dữ liệu có thể đang nằm trong bộ đệm của HTTP Client, TLS, hệ điều hành, TCP hoặc phía server: backpressure ở `Flow` **không có nghĩa** toàn mạng chỉ giữ đúng một batch hay server ngừng tạo dữ liệu ngay lập tức.

### 1.1. Các đơn vị giới hạn cần phân biệt

| Khái niệm | Đơn vị | Cách điều khiển | Điều nó **không** bảo đảm |
| --- | --- | --- | --- |
| **Flow demand** | Số lần `onNext` | `subscription.request(n)` | Không có ý nghĩa «n bytes». |
| **Body limit** | Tổng bytes | Đếm số `ByteBuffer.remaining()`, từ chối/hủy khi vượt | Không ép các buffer thấp hơn tầng ứng dụng không bao giờ cấp phát. |
| **Processing rate** | Bytes/giây, records/giây | Pacing, token bucket, lịch xử lý | Không nhất thiết giới hạn tốc độ server phát/đường truyền ở mọi tầng. |
| **Concurrency limit** | Số tác vụ kết nối đang hoạt động | `Semaphore`, executor có giới hạn, hàng đợi bounded | Không giới hạn trực tiếp bytes mỗi request. |
| **Queue capacity** | Số phần tử và/hoặc tổng bytes đang chờ | Queue bounded + quy tắc quá tải | Không tự kiểm soát kích thước một phần tử đơn lẻ. |
| **Timeout** | Thời gian | `HttpRequest.Builder.timeout`, `CompletableFuture.orTimeout` | Không làm server rollback một request đã nhận. |

Một sản phẩm có thể phải **kết hợp cả năm** quy tắc đầu với timeout. Chỉ dùng `request(1)` là chưa đủ để giới hạn tổng dung lượng, và chỉ đặt `Semaphore` cho 10 request không ngăn một response đơn lẻ có body nhiều GiB.

## 2. Hợp đồng Java Flow trong Java 11

### 2.1. Publisher, Subscriber và Subscription

Các interface `java.util.concurrent.Flow` được giới thiệu từ Java 9 và vẫn được hỗ trợ:

- `Flow.Publisher<T>`: nguồn phát phần tử kiểu `T`.
- `Flow.Subscriber<T>`: phía nhận, định nghĩa `onSubscribe`, `onNext`, `onError` và `onComplete`.
- `Flow.Subscription`: kết nối điều khiển giữa một publisher và một subscriber; hỗ trợ `request(long n)` và `cancel()`.

Vòng đời thường gặp:

~~~text
publisher.subscribe(subscriber)
  -> subscriber.onSubscribe(subscription)
  -> subscriber calls subscription.request(n)
  -> publisher calls onNext(item) at most as demanded
  -> more request(n) / more onNext(item)
  -> onComplete() OR onError(cause)
~~~

**`request(n)` cộng thêm `n` vào demand chưa được đáp ứng**, không gán demand bằng `n`. Theo Javadoc, `n <= 0` là yêu cầu không hợp lệ và dẫn đến `onError` với `IllegalArgumentException`. `request(Long.MAX_VALUE)` được xem như nhu cầu gần như không giới hạn; đừng dùng nó trong một subscriber cần kiểm soát lượng công việc đang chờ.

`cancel()` là **best effort**, có thể còn tín hiệu phát ra sau khi gọi; subscription đã hủy không buộc nhận `onComplete` hay `onError`. Không dựa vào terminal callback để giải phóng tài nguyên **sau khi tự chủ động cancel**: tự kết thúc result future và cleanup theo chính sách của ứng dụng.

Theo hợp đồng `Flow`, callback đến một subscription được tổ chức theo thứ tự, nhưng không nên giả định callback luôn chạy trên một thread có tên cụ thể. Nếu đưa dữ liệu vào executor khác, chính code của bạn phải đảm bảo thứ tự, xử lý lỗi và đóng executor.

### 2.2. Với HTTP response, một item không phải một byte

Java 11 định nghĩa:

~~~java
HttpResponse.BodySubscriber<T>
        extends Flow.Subscriber<List<ByteBuffer>>
~~~

Khi dùng `BodyHandlers.ofPublisher()`, kiểu body là:

~~~java
Flow.Publisher<List<ByteBuffer>>
~~~

Vậy `request(1)` cấp quyền nhận **một lần `onNext(List<ByteBuffer>)`**, mà list có thể chứa nhiều buffer và mỗi buffer có số byte thay đổi. Không suy luận «một request demand = một `ByteBuffer` = một TCP packet = một KB». Kích thước từng list/buffer phụ thuộc phân đoạn và implementation.

Các list được chuyển đến `BodySubscriber` không thể sửa cấu trúc, còn các `ByteBuffer` là read-only. Sau khi chuyển đến subscriber, HTTP Client không tiếp tục dùng lại chúng theo hợp đồng Javadoc. Khi xử lý, có thể dùng `buffer.asReadOnlyBuffer()` hoặc `duplicate()` để có cursor riêng, không thay position/limit của buffer nguồn. Nếu cần chuyển dữ liệu sang hệ thống khác quản lý lâu dài, quyết định rõ quyền sở hữu hoặc tạo bản copy phù hợp.

### 2.3. Với HTTP request, hướng publisher khác

`HttpRequest.BodyPublisher` mở rộng `Flow.Publisher<ByteBuffer>`: mỗi item là **một `ByteBuffer`**, không phải `List<ByteBuffer>`. Để dùng nguồn publisher tự viết:

~~~java
// Minh họa: source là một Flow.Publisher<ByteBuffer> hợp lệ.
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.fromPublisher(source);
~~~

Overload với `contentLength`:

~~~java
// Minh họa: exactLength phải là tổng số byte thực sự phát đi.
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.fromPublisher(source, exactLength);
~~~

Không dùng nhầm `Flow.Publisher<List<ByteBuffer>>` của response làm `BodyPublisher` request mà không có bước chuyển đổi đúng kiểu. Với overload độ dài cố định, `exactLength` phải đúng với tổng bytes. Nếu không biết trước độ dài, dùng overload không có độ dài để client chọn framing phù hợp.

Nếu HTTP Client phải gửi lại request (retry/redirect/auth challenge theo cấu hình và tình huống), body publisher có thể được subscribe lại; custom publisher cần có chiến lược tái phát đúng dữ liệu hoặc từ chối phù hợp. Đừng thiết kế publisher dựa trên một `InputStream` chỉ đọc được một lần mà mặc định việc resend luôn an toàn.

## 3. Chọn cách streaming response phù hợp

### 3.1. So sánh các BodyHandler

| API Java 11 | `HttpResponse.body()` | Đặc điểm |
| --- | --- | --- |
| `BodyHandlers.ofString()` | `String` | Đọc và decode toàn bộ body; đơn giản nhưng giữ toàn văn bản trong bộ nhớ. |
| `BodyHandlers.ofByteArray()` | `byte[]` | Giữ toàn bộ bytes trong bộ nhớ; không thích hợp cho payload không giới hạn. |
| `BodyHandlers.ofFile(path)` | `Path` | Stream body vào file; phù hợp tải tệp, phải kiểm soát nơi lưu/permission/dung lượng. |
| `BodyHandlers.ofInputStream()` | `InputStream` | Response trả về sau khi đọc headers, body có thể chưa đọc hết; người gọi đọc/đóng stream. |
| `BodyHandlers.ofLines()` | `Stream<String>` | Stream dòng văn bản, đóng stream và dùng charset theo hợp đồng. |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Stream bytes theo `Flow`; **chỉ được subscribe một lần**. |
| `BodyHandlers.fromSubscriber(subscriber)` | `Void` | Adapter cho subscriber tự quản lý dữ liệu đích; response future hoàn tất sau terminal event của subscriber. |
| `BodyHandlers.fromLineSubscriber(...)` | Tùy overload | Chuyển dữ liệu text thành từng dòng cho `Flow.Subscriber<String>`. |
| `BodyHandlers.buffering(handler, bufferSize)` | Theo handler bên trong | Tập hợp buffer trước khi chuyển downstream; **không** phải rate limiter hay giới hạn tổng body. |

Javadoc `BodySubscriber` có lưu ý quan trọng: để giải phóng tài nguyên của HTTP exchange, subscriber phải **tiếp tục request cho tới `onComplete`/`onError` hoặc cancel** nếu không muốn/không thể đọc tiếp. Hủy trước khi tiêu thụ hết body có thể khiến kết nối HTTP bên dưới bị đóng, giảm khả năng reuse.

`BodyHandlers.ofPublisher()` trả response khi đã đọc headers, trong lúc body có thể còn đang đến. Nếu chỉ lấy `HttpResponse` rồi **không subscribe** hoặc không cancel, tài nguyên có thể bị giữ lại. Với `ofInputStream()` cũng cần tiêu thụ/đóng stream; không dùng `readAllBytes()` cho body lớn khi mục tiêu là bounded memory.

### 3.2. Ví dụ luồng đọc bằng InputStream

Đoạn **minh họa**, giả định `client` và `request` đã có:

~~~java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream input = response.body()) {
    byte[] chunk = new byte[8192];
    long total = 0;
    int count;
    while ((count = input.read(chunk)) != -1) {
        total += count;
        if (total > 50L * 1024 * 1024) {
            throw new IOException("Body exceeds 50 MiB");
        }
        processBytes(chunk, count);
    }
}
~~~

`processBytes` là một method nghiệp vụ **minh họa**, không thuộc JDK. Cách này giữ một buffer ứng dụng khoảng 8 KiB và tự kiểm giới hạn tổng bytes. Lệnh `input.read(...)` có thể **block**, vì vậy cần chạy trên luồng I/O/worker phù hợp; tránh dùng trực tiếp trong UI/event loop. Đóng `InputStream` trước khi đọc hết có thể khiến HTTP exchange bị hủy và làm kết nối khó reuse.

Nếu muốn mô hình non-blocking/event-driven, `ofPublisher` kết hợp `Flow.Subscription` giúp điều tiết từng item.

## 4. Thiết kế subscriber với cửa sổ demand nhỏ

### 4.1. Vì sao dùng cửa sổ 1 batch?

Một subscriber đơn giản nhưng dễ gây quá tải:

~~~java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(Long.MAX_VALUE);  // effectively unbounded
}
~~~

Nó cho phép publisher đẩy rất nhiều `onNext` trước khi consumer hoàn tất xử lý, đặc biệt nếu người viết `onNext` đưa dữ liệu vào một hàng đợi mới. Nếu queue không giới hạn, bytes tồn đọng có thể tăng không giới hạn.

Cửa sổ một batch:

~~~java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}

// onNext: nhận batch, giao xử lý sang worker riêng.
// Sau khi worker hoàn tất batch đó:
// subscription.request(1);
~~~

Lợi ích: không cấp thêm demand cho đến khi consumer hoàn tất công việc trước. **Đừng gọi `request(1)` ngay sau khi chỉ enqueue một tác vụ** nếu mục tiêu của bạn là giới hạn **công việc chưa hoàn tất**; khi đó dữ liệu vẫn có thể xếp chồng trong executor queue.

Với throughput cao hơn, có thể dùng cửa sổ `W > 1` và một executor có queue bounded; tuy nhiên phải giảm demand theo số việc đang thực thi/chờ, đồng thời giới hạn **bytes mỗi batch**. Một batch có thể rất lớn ngay cả khi `W == 1`, nên cần thêm giới hạn dung lượng.

### 4.2. Tách callback khỏi xử lý nặng

**Không** làm database write, parse JSON khối lượng lớn, mã hóa hoặc `Thread.sleep` trong `onNext` chạy trên thread callback HTTP không kiểm soát. Khi processing lâu:

1. `onNext` xác nhận batch và chuyển sang **executor riêng** theo quyền sở hữu dữ liệu rõ ràng.
2. Worker đo kích thước, kiểm hạn mức, xử lý bytes theo thứ tự.
3. Worker chỉ gọi `subscription.request(1)` sau khi xử lý thành công và còn muốn tiếp tục.
4. Nếu lỗi, hoàn tất result future một cách rõ ràng rồi gọi `subscription.cancel()` để ngừng nhận thêm.
5. `onComplete`/`onError` hoàn tất future kết quả, dọn dẹp executor sau khi công việc queued đã xử lý theo đúng thứ tự.

Một executor đơn luồng giúp giữ thứ tự các batch đối với **một** response. Trong server xử lý nhiều response đồng thời, không nên tạo vô hạn executor/threads theo mỗi response; dùng pool được quản lý với giới hạn số request và queue hợp lý. Ví dụ bên dưới ưu tiên tính minh bạch bằng một worker đơn luồng cho **một** response test.

## 5. Giới hạn tốc độ xử lý khác backpressure

Giả sử bạn muốn **không xử lý quá nhanh** (ví dụ để giảm áp lực database hoặc IO downstream). Sau khi xử lý batch `B` bytes, có thể chờ tương ứng với tốc độ mục tiêu `R` bytes/giây trước khi request batch tiếp theo:

~~~text
pauseNanos = B * 1_000_000_000 / R
~~~

Trong ví dụ runnable, thao tác tạm chờ dùng `LockSupport.parkNanos` trên **worker riêng**, không trên callback HTTP. Nó minh họa **pacing tiêu thụ** theo bytes và có thể gây trễ giữa các lần cấp demand.

Nhưng đây **không phải rate limiter chính xác có SLA cứng**:

- Batch đầu có thể đến ngay; hệ thống cho phép burst.
- `parkNanos` chỉ là cơ chế chờ best-effort; scheduling, interrupt và clock có thể khiến thời gian thực chênh lệch.
- Bytes có thể đã ở trong TCP/HTTP Client buffers trước khi app đọc; pacing không tương đương «server chỉ phát R bytes/giây».
- Công thức `B * 1e9` cần phòng tràn `long` cho input lớn; demo chỉ dùng batch nhỏ.
- Nếu cần **giới hạn thực sự theo cửa sổ thời gian và burst**, dùng thuật toán **token bucket** hoặc **leaky bucket** với clock đơn điệu, capacity hữu hạn và kiểm số tokens trước khi xử lý. Nếu yêu cầu giới hạn cả request/giây, đặt limiter **trước khi gửi request**, không chỉ ở subscriber response.

### 5.1. Token bucket: công thức thiết kế

Với tốc độ nạp `r` tokens/giây, dung lượng tối đa `capacity` và số tokens hiện tại:

~~~text
elapsedSeconds = (nowNanos - lastNanos) / 1e9
tokens = min(capacity, tokens + elapsedSeconds * r)

if tokens >= cost:
    tokens -= cost
    allow action
else:
    schedule a later retry / wait asynchronously
~~~

Nếu chọn **mỗi token tương ứng một byte**, `cost` nên là số bytes thực tế; nếu chọn **mỗi token tương ứng một request**, `cost = 1`. Một request streaming có kích thước chưa biết có thể phải charge theo từng batch. Các thao tác cập nhật state của token bucket dùng chung phải thread-safe; không nên nắm lock trong lúc chờ I/O.

Tại vị trí tích hợp với `Flow`, chỉ **cấp demand mới khi đã có tài nguyên xử lý**. Nhưng vì `request(1)` cấp một lần `onNext(List<ByteBuffer>)` với kích thước chưa biết trước, không thể coi request-demand là bộ cấp phát token theo byte chính xác: app có thể kiểm/điều tiết số byte đã nhận và cân nhắc giới hạn byte tổng, hoặc dùng một tầng buffer phân khúc riêng có quy tắc capacity rõ ràng.

### 5.2. Giới hạn số kết nối hoặc request đồng thời

Nếu hệ thống thực hiện nhiều request lớn, hãy giới hạn số response đang stream:

~~~java
// Minh họa: semaphore chung do ứng dụng quản lý.
Semaphore slots = new Semaphore(8);
slots.acquire();
try {
    // Gửi request, stream body, xử lý terminal state.
} finally {
    slots.release();
}
~~~

Đoạn code là **minh họa**, không phải chương trình độc lập. Trong pipeline bất đồng bộ, **không** gọi `slots.release()` ngay sau `sendAsync` (khi body chưa xử lý xong), mà giữ permit tới terminal state của body hoặc chính sách hủy. Không gọi `slots.acquire()` blocking trên event-loop/UI thread; có thể dùng hàng đợi bounded hoặc dispatcher bất đồng bộ.

## 6. Chương trình Java 11 chạy độc lập: streaming + demand + pacing + byte cap

Tạo file **HttpBackpressureDemo.java**. Chương trình sử dụng:

- HTTP server thử nghiệm `jdk.httpserver` trên `127.0.0.1`, port tự cấp, phát **128 KiB** dữ liệu binary theo nhiều lần ghi.
- HTTP Client Java 11 với `BodyHandlers.ofPublisher()` để nhận `Flow.Publisher<List<ByteBuffer>>`.
- Subscriber chỉ `request(1)`, chuyển batch nhận về **executor riêng**; xử lý toàn bộ bytes theo thứ tự rồi mới request tiếp.
- Tính **sum byte không dấu** để kiểm data integrity mà không giữ toàn bộ body trong RAM.
- Pacing đơn giản trên worker ở mức mục tiêu **1 MiB/giây** cho demo, không khẳng định tốc độ mạng đạt con số tuyệt đối.
- Kiểm `maxBytes`; thử body lớn hơn ngưỡng **4 KiB** để hủy và complete future bằng lỗi có nguyên nhân rõ.

**Lưu ý:** vì kích thước `List<ByteBuffer>` do HTTP Client lựa chọn, test không assert chính xác số callback/batch; nó chỉ yêu cầu đã có ít nhất một batch và không có hơn một batch đang xử lý cùng lúc. Một batch có thể gồm nhiều ByteBuffer. `BodyHandlers.ofPublisher()` chỉ cho phép subscribe một lần cho response publisher; ví dụ dùng request mới cho bài test thứ hai.

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
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
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.LockSupport;

public class HttpBackpressureDemo {
    private static void check(boolean pass, String message) {
        if (!pass) throw new AssertionError(message);
    }

    static final class Stats {
        final long bytes;
        final long sum;
        final int batches;
        final int peakPending;
        final long pacedNanos;

        Stats(long bytes, long sum, int batches, int peakPending,
              long pacedNanos) {
            this.bytes = bytes;
            this.sum = sum;
            this.batches = batches;
            this.peakPending = peakPending;
            this.pacedNanos = pacedNanos;
        }
    }

    static final class BoundedSubscriber
            implements Flow.Subscriber<List<ByteBuffer>>, AutoCloseable {
        final CompletableFuture<Stats> done = new CompletableFuture<>();
        private final ExecutorService processor =
                Executors.newSingleThreadExecutor();
        private final AtomicInteger pending = new AtomicInteger();
        private final AtomicInteger peak = new AtomicInteger();
        private final AtomicInteger batches = new AtomicInteger();
        private final long maxBytes;
        private final long bytesPerSecond;
        private volatile Flow.Subscription subscription;

        private long bytes;
        private long sum;
        private long pacedNanos;

        BoundedSubscriber(long maxBytes, long bytesPerSecond) {
            this.maxBytes = maxBytes;
            this.bytesPerSecond = bytesPerSecond;
        }

        @Override
        public void onSubscribe(Flow.Subscription s) {
            if (subscription != null) {
                s.cancel();
                return;
            }
            subscription = s;
            s.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> buffers) {
            int current = pending.incrementAndGet();
            peak.updateAndGet(old -> Math.max(old, current));
            if (current != 1) {
                done.completeExceptionally(
                        new IllegalStateException("More than one outstanding batch"));
                subscription.cancel();
                return;
            }
            batches.incrementAndGet();
            processor.execute(() -> {
                try {
                    long batchBytes = 0;
                    for (ByteBuffer buffer : buffers) {
                        ByteBuffer read = buffer.asReadOnlyBuffer();
                        int size = read.remaining();
                        if (size > maxBytes - bytes) {
                            throw new IllegalStateException("Body size limit exceeded");
                        }
                        batchBytes += size;
                        while (read.hasRemaining()) {
                            sum += read.get() & 0xFF;
                            bytes++;
                        }
                    }
                    if (bytesPerSecond > 0 && batchBytes > 0) {
                        long pause = batchBytes * 1_000_000_000L / bytesPerSecond;
                        pacedNanos += pause;
                        LockSupport.parkNanos(pause);
                    }
                    pending.decrementAndGet();
                    if (!done.isDone()) {
                        subscription.request(1);
                    }
                } catch (Throwable failure) {
                    pending.decrementAndGet();
                    done.completeExceptionally(failure);
                    subscription.cancel();
                }
            });
        }

        @Override
        public void onError(Throwable failure) {
            done.completeExceptionally(failure);
        }

        @Override
        public void onComplete() {
            processor.execute(() -> done.complete(new Stats(
                    bytes, sum, batches.get(), peak.get(), pacedNanos)));
        }

        @Override
        public void close() {
            if (!done.isDone() && subscription != null) {
                subscription.cancel();
            }
            processor.shutdownNow();
        }
    }

    private static HttpRequest get(URI base) {
        return HttpRequest.newBuilder(base.resolve("/stream"))
                .timeout(Duration.ofSeconds(10)).GET().build();
    }

    public static void main(String[] args) throws Exception {
        final byte[] payload = new byte[128 * 1024];
        long expectedSum = 0;
        for (int i = 0; i < payload.length; i++) {
            payload[i] = (byte) (i % 251);
            expectedSum += payload[i] & 0xFF;
        }

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService serverExecutor = Executors.newFixedThreadPool(2);
        server.setExecutor(serverExecutor);
        server.createContext("/stream", exchange -> {
            exchange.getResponseHeaders().set(
                    "Content-Type", "application/octet-stream");
            exchange.sendResponseHeaders(200, payload.length);
            try (OutputStream output = exchange.getResponseBody()) {
                for (int offset = 0; offset < payload.length; offset += 2048) {
                    output.write(payload, offset,
                            Math.min(2048, payload.length - offset));
                    output.flush();
                }
            } catch (IOException mayBeCancellation) {
                // The size-limit test intentionally cancels a response.
            }
        });
        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();

            HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
                    client.send(get(base),
                            HttpResponse.BodyHandlers.ofPublisher());
            check(response.statusCode() == 200, "HTTP 200 required");

            try (BoundedSubscriber reader =
                    new BoundedSubscriber(256 * 1024, 1024 * 1024)) {
                response.body().subscribe(reader);
                Stats stats = reader.done.orTimeout(10, TimeUnit.SECONDS).join();
                check(stats.peakPending == 1 && stats.batches >= 1,
                        "one demanded batch at a time");
                System.out.println("PASS one-batch backpressure");

                check(stats.bytes == payload.length && stats.sum == expectedSum,
                        "all bytes must be processed");
                System.out.println("PASS full streaming body");

                check(stats.pacedNanos > 0, "worker configured with pacing");
                System.out.println("PASS worker pacing configured");
            }

            HttpResponse<Flow.Publisher<List<ByteBuffer>>> limited =
                    client.send(get(base),
                            HttpResponse.BodyHandlers.ofPublisher());
            try (BoundedSubscriber reader = new BoundedSubscriber(4096, 0)) {
                limited.body().subscribe(reader);
                boolean rejected = false;
                try {
                    reader.done.orTimeout(10, TimeUnit.SECONDS).join();
                } catch (java.util.concurrent.CompletionException expected) {
                    rejected = expected.getCause() instanceof IllegalStateException
                            && expected.getCause().getMessage()
                                    .contains("Body size limit");
                }
                check(rejected, "oversized body must cancel subscription");
                System.out.println("PASS size cap and cancellation");
            }
            System.out.println("ALL BACKPRESSURE TESTS PASSED");
        } finally {
            server.stop(0);
            serverExecutor.shutdownNow();
        }
    }
}
~~~

### Biên dịch và chạy

Có thể dùng **JDK 11** hoặc JDK mới có hỗ trợ target 11. Module `jdk.httpserver` chỉ cung cấp server test cục bộ, còn HTTP Client thuộc `java.net.http`.

~~~bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 HttpBackpressureDemo.java
java --add-modules jdk.httpserver -cp . HttpBackpressureDemo
~~~

**Đầu ra mong đợi nếu tất cả điều kiện đúng:**

~~~text
PASS one-batch backpressure
PASS full streaming body
PASS worker pacing configured
PASS size cap and cancellation
ALL BACKPRESSURE TESTS PASSED
~~~

Giải thích từng nhóm:

1. **One-batch demand:** subscriber gọi `request(1)` lần đầu, chỉ request lại từ worker sau khi xử lý xong; `peakPending` ghi nhận tối đa một batch đang được xử lý. Đây là kiểm thử cơ chế **demand một item**, không kiểm định số bytes của batch.
2. **Integrity:** server phát đúng 128 KiB; subscriber đếm tổng bytes và tổng các giá trị byte unsigned. Đây là phép kiểm dữ liệu gọn, không cần giữ cả body; với hệ thống thực, có thể dùng SHA-256 để kiểm integrity nếu có expected digest đáng tin.
3. **Worker pacing:** công thức chuyển bytes đã xử lý thành thời gian chờ được kích hoạt, nhưng bài test cố ý **không assert tốc độ mạng đo bằng đồng hồ** vì scheduling và buffering khiến phép đo không ổn định.
4. **Size cap:** subscriber có `maxBytes=4096`. Khi một buffer vượt giới hạn còn lại, nó hoàn tất `CompletableFuture` bằng `IllegalStateException` rồi `cancel`; test kiểm đúng lý do. Tín hiệu từ HTTP sau khi cancel có thể đến thêm, vì hủy là best-effort.

`HttpClient.send(..., ofPublisher())` được dùng để minh họa rằng ngay cả ở API `send`, response có thể được trả khi headers đã có còn body **chưa được tiêu thụ**. Sau khi nhận publisher, app subscribe rồi chờ `reader.done` ở ranh giới chương trình test. Có thể dùng `sendAsync(..., ofPublisher())` nếu cần không chặn cả bước nhận headers; **không** dùng `join()` ngay trên event loop thực chỉ để biến chương trình thành «bất đồng bộ trên danh nghĩa».

**Giới hạn của mẫu:** demo tạo executor riêng cho từng subscriber, dùng phép cộng tổng byte, dữ liệu nhỏ và pacing best-effort. Đây không phải production-ready HTTP gateway với SLA, retry, circuit breaker hoặc queue đa kết nối. Các hệ thống lớn cần quản lý pool/queue chung, giới hạn concurrency và số bytes trên mọi response, chính sách hủy, độ dài tối đa của từng item cũng như metrics.

## 7. Xử lý lỗi, hủy và vòng đời kết nối

### 7.1. `onError` và `onComplete`

- `onComplete()` có nghĩa publisher đã phát hết body bình thường; theo `Flow`, không có thêm `onNext` sau terminal signal.
- `onError(Throwable)` cho biết lỗi không thể tiếp tục trên subscription; consumer phải hoàn tất future theo trạng thái lỗi và giải phóng nguồn lực.
- Nếu ứng dụng **tự quyết định dừng sớm** vì body quá lớn, lỗi parse, lỗi downstream hoặc user hủy, hãy chủ động hoàn tất future/trạng thái ứng dụng rồi gọi `subscription.cancel()`.
- `cancel()` có thể khiến HTTP connection bị đóng và không reuse; cũng có thể không phát `onComplete` hay `onError` mới, vì vậy không được để future kết quả treo chờ callback terminal mà bạn không còn được bảo đảm nhận.

Trong code demo, `done.completeExceptionally(failure)` được gọi **trước** `subscription.cancel()` ở nhánh lỗi tự phát hiện để giữ nguyên nhân vượt giới hạn, kể cả khi cancel kích hoạt tín hiệu lỗi khác đồng thời. `CompletableFuture` chỉ chấp nhận lần hoàn tất đầu tiên, nên thứ tự này giúp chẩn đoán rõ ràng.

### 7.2. HTTP status không phải Flow error

`BodyHandlers.ofPublisher()` có thể cung cấp body cho response **404 hoặc 500** như với 200. `Flow` kiểm soát luồng dữ liệu, **không** định nghĩa thành công nghiệp vụ theo status code.

Thông thường nên kiểm:

~~~java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.send(request, HttpResponse.BodyHandlers.ofPublisher());

if (response.statusCode() != 200) {
    // Quyết định drain, discard hoặc cancel body theo chính sách.
}
// Nếu chấp nhận: chỉ subscribe một lần vào response.body().
~~~

Đoạn trên là **minh họa**, không phải chương trình độc lập. Không nên bỏ mặc body 4xx mà không subscribe/cancel vì có thể giữ tài nguyên. Có thể chọn một `BodyHandler` khác theo `ResponseInfo.statusCode()` khi biết status trước khi xử lý body.

### 7.3. Timeout và lượng dữ liệu chưa xử lý

`HttpRequest.Builder.timeout(Duration)` và `CompletableFuture.orTimeout` là giới hạn **thời gian**, không phải dung lượng. `orTimeout` chỉ ảnh hưởng trạng thái future; nếu ứng dụng muốn dừng HTTP body, phải tính tới **hủy subscription/đóng stream** theo đường đi I/O thực tế. Đặc biệt `BodyHandlers.ofPublisher()` trả future/response khi headers sẵn, vì vậy một timeout chỉ đặt trên future **nhận headers** không tự giới hạn thời gian tiêu thụ body về sau.

Dùng deadline hoặc watchdog riêng cho cả quá trình xử lý body khi cần bảo đảm thời gian kết thúc; đồng thời cài giới hạn bytes và số công việc đang chờ. Nếu server gửi bytes chậm, body consumption có thể kéo dài sau khi đã nhận headers.

### 7.4. Bộ nhớ không tự được giới hạn tuyệt đối ở mọi tầng

Subscriber demo không lưu toàn bộ body, và chỉ xử lý một item trong executor. Nhưng **một item `List<ByteBuffer>` có thể lớn**; chính HTTP Client, hệ điều hành, TLS hoặc server cũng có buffer riêng. Giới hạn 4 KiB được kiểm **khi một item đến callback**, nên không thể tuyên bố máy chưa từng nhận nhiều hơn 4 KiB từ mạng.

Để triển khai biên giới tài nguyên có yêu cầu cứng hơn: kiểm `Content-Length` khi có nhưng **không chỉ tin header**, đo bytes thực tế, giới hạn từng queue/buffer, chỉ định timeout và quyền hủy. Nếu dữ liệu quá lớn, trả lỗi rõ và xử lý resource lifecycle thay vì cứ đợi/chứa dữ liệu.

## 8. Checklist thiết kế backpressure thực tế

| Câu hỏi | Gợi ý kiểm tra |
| --- | --- |
| Mỗi `onNext` chứa gì? | Response: `List<ByteBuffer>`, request: `ByteBuffer`. |
| Demand cấp theo đơn vị nào? | `request(n)` cấp **n item**, không cấp n bytes. |
| Khi nào cấp thêm demand? | Sau khi consumer **xử lý xong**, không chỉ sau khi enqueue. |
| Công việc nặng chạy ở đâu? | Worker/executor riêng được giới hạn, tránh block callback HTTP. |
| Queue có giới hạn không? | Giới hạn theo item và nếu cần cả tổng bytes. |
| Body có kích thước tối đa không? | Kiểm bytes nhận thực tế, không chỉ `Content-Length`. |
| Có pacing/rate limit không? | Đo bytes/giây hoặc request/giây bằng cơ chế riêng, đừng nhầm demand với token. |
| Có limit số request đồng thời không? | Semaphore/dispatcher hoặc pool đúng vòng đời body. |
| Nếu cancel thì tương lai result ra sao? | Complete future rõ ràng trước/đồng thời cancel; không chờ terminal callback không được bảo đảm. |
| Nếu body bị bỏ dở thì sao? | Drain/cancel/close để giải phóng HTTP exchange và xét khả năng connection reuse. |
| Có phụ thuộc bản Java mới hơn 11 không? | Kiểm Javadoc `Since`; tránh dùng API chỉ có ở JDK mới nếu baseline 11. |

### Những lỗi phổ biến

1. **`request(1)` được coi là một byte hoặc một TCP packet.** Thực tế một item của response là `List<ByteBuffer>` với kích thước biến thiên.
2. **Gọi `request(Long.MAX_VALUE)` rồi enqueue vào queue không giới hạn.** Điều đó có thể triệt tiêu lợi ích backpressure.
3. **`request(1)` ngay sau khi enqueue, chưa chờ xử lý.** Hàng đợi có thể tiếp tục phình ra.
4. **Block trong callback `onNext`.** Làm giảm tính đáp ứng của HTTP Client và có thể ảnh hưởng request khác.
5. **Chỉ dựa vào `Content-Length` để giới hạn body.** Header có thể vắng/sai hoặc dữ liệu được truyền kiểu khác; phải đếm bytes thực tế.
6. **Coi `BodyHandlers.buffering(..., bufferSize)` là rate limiter.** Nó điều chỉnh buffering giữa các subscriber, không đặt SLA bytes/giây hay tổng bytes tối đa.
7. **Không subscribe/đọc/đóng/cancel response body.** Giữ tài nguyên HTTP exchange, có thể ảnh hưởng tái sử dụng kết nối.
8. **Đợi `onComplete` sau `cancel`.** `cancel` không bảo đảm terminal callback.
9. **Dùng một `Flow.Publisher` của `ofPublisher` để subscribe nhiều lần.** Javadoc quy định response publisher chỉ được subscribe một lần.
10. **Nhầm streaming response với request body.** `BodySubscriber` nhận `List<ByteBuffer>`, request `BodyPublisher` phát `ByteBuffer`.
11. **Xem pacing bằng `parkNanos` như cam kết băng thông chính xác.** Cần chính sách burst, clock, token bucket và đo lường thực tế nếu có SLA.
12. **Dùng `readAllBytes()` trong đường xử lý tệp rất lớn.** Có thể đưa toàn bộ dữ liệu vào heap, trái mục tiêu streaming.
13. **Hủy giữa chừng mà không báo trạng thái nghiệp vụ.** Future có thể treo, dữ liệu được xử lý một phần không có đánh dấu.
14. **Giữ một worker/thread riêng cho mỗi request không giới hạn.** Pool/task queue bị cạn khi số request tăng; cần concurrency limit tổng thể.

## 9. Câu hỏi tự đánh giá

**1.** Với `BodyHandlers.ofPublisher()`, `subscription.request(1)` nhận được bao nhiêu byte?

**Đáp án:** Không xác định cố định. Nó cho phép tối đa một `onNext` với một `List<ByteBuffer>`; số bytes bên trong list phụ thuộc implementation và dữ liệu được phân đoạn.

**2.** Vì sao nên gọi `request(1)` **sau** khi worker hoàn tất batch?

**Đáp án:** Để số batch đang xử lý/chờ nằm trong cửa sổ demand hữu hạn, thay vì liên tục đưa dữ liệu vào một queue có thể tăng không giới hạn.

**3.** `BodyPublisher` của request có cùng kiểu item với `BodySubscriber` của response không?

**Đáp án:** Không. Request publisher là `Flow.Publisher<ByteBuffer>`; response subscriber nhận `Flow.Subscriber<List<ByteBuffer>>`.

**4.** `BodyHandlers.ofPublisher()` đã trả response nghĩa là body đã tải hết chưa?

**Đáp án:** Chưa chắc. Response có thể được trả khi headers sẵn, body còn được stream thông qua publisher; client phải subscribe và tiêu thụ/cancel.

**5.** Một service giới hạn 4 request chạy đồng thời đã tự giới hạn 100 MiB tổng download chưa?

**Đáp án:** Chưa. Concurrency và byte capacity là hai giới hạn độc lập; cần cả byte cap theo response/tổng hệ thống nếu yêu cầu.

**6.** Đặt `request(1)` và xử lý batch xong rồi `LockSupport.parkNanos` có bảo đảm server không gửi nhanh hơn mức đặt không?

**Đáp án:** Không. Nó điều tiết bước cấp demand/processing ở ứng dụng, trong khi server và các buffer tầng dưới vẫn có thể gửi/giữ dữ liệu trước. Không phải rate limit mạng cứng.

**7.** Sau khi subscriber `cancel()`, có bảo đảm nhận `onComplete` không?

**Đáp án:** Không. Cancel là best-effort và có thể không có terminal callback. Ứng dụng phải chủ động hoàn tất future/cleanup theo chính sách.

**8.** Tại sao phải ghi lại nguyên nhân lỗi vào future trước khi gọi `cancel()` trong nhánh app tự từ chối body?

**Đáp án:** Việc hủy có thể kích hoạt tín hiệu lỗi từ nguồn bất đồng bộ; hoàn tất future trước giúp giữ đúng lỗi nghiệp vụ như vượt giới hạn bytes thay vì bị một lỗi hủy khác ghi đè.

**9.** `BodyHandlers.buffering(handler, 8192)` là giới hạn body 8192 bytes không?

**Đáp án:** Không. Tham số `bufferSize` điều chỉnh lượng dữ liệu buffer trước khi phát downstream, không phải tổng dung lượng phản hồi. Cần giới hạn tổng bytes riêng.

**10.** Nếu server trả status 404, `BodyHandlers.ofPublisher()` có tự fail vì business error không?

**Đáp án:** Không. Nó tiếp tục xử lý body theo contract; ứng dụng phải xét `statusCode()`, lựa chọn tiêu thụ/discard/cancel body và trả lỗi tương ứng.

## 10. Tài liệu chính thức

- [Java SE 11 — `java.util.concurrent.Flow`: Publisher, Subscriber, Subscription và backpressure](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.html)
- [Java SE 11 — `Flow.Subscription.request/cancel`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [Java SE 11 — `HttpResponse.BodySubscriber`: nhận `List<ByteBuffer>`, quy tắc request/cancel](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html)
- [Java SE 11 — `HttpResponse.BodyHandlers`: ofPublisher, ofInputStream, ofLines, fromSubscriber, buffering](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Java SE 11 — `HttpResponse.BodySubscribers`: buffering và các adapter](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
- [Java SE 11 — `HttpRequest.BodyPublisher`: publish bytes cho request](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html)
- [Java SE 11 — `HttpRequest.BodyPublishers`: fromPublisher và contentLength](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [JDK 26 — `Flow.Subscription`: đối chiếu API vẫn được hỗ trợ](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
