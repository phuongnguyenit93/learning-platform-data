# Java 11+ — Kiểm thử và tối ưu: Streaming body với bên nhận chậm và hủy giữa chừng

## 1. Vấn đề: bên nhận chậm không có nghĩa phải nạp cả body vào RAM

Một HTTP response có thể rất lớn, đến theo nhiều đợt và được xử lý chậm hơn tốc độ bên gửi tạo dữ liệu. Ví dụ: client tải một file vài GB từ server nhưng chỉ ghi được vài MB/s xuống ổ đĩa, hoặc xử lý từng mẩu dữ liệu trước khi chuyển sang hệ thống khác. Nếu bên nhận gom toàn bộ response thành `byte[]` hoặc `String` trước khi xử lý, bộ nhớ có thể tăng mạnh và ứng dụng mất khả năng hủy sớm khi đã có đủ dữ liệu.

Từ **Java 11**, module **`java.net.http`** cung cấp HTTP client hiện đại với **`HttpClient`**, **`HttpResponse.BodyHandlers.ofPublisher()`**, **`HttpResponse.BodyHandlers.ofInputStream()`** và các adapter dựa trên **`java.util.concurrent.Flow`**. Đây là API công khai, vẫn được duy trì trên các JDK hiện đại. Không cần dùng `HttpURLConnection` hoặc cài một thư viện reactive riêng chỉ để minh họa backpressure và hủy giữa chừng.

Một client được thiết kế tốt cần giải quyết đồng thời:

1. **Streaming:** nhận các phần body dần dần, không bắt buộc nạp toàn bộ vào bộ nhớ.
2. **Backpressure:** khi consumer chậm, nó phải điều khiển số đơn vị dữ liệu muốn nhận tiếp; không tạo queue không giới hạn.
3. **Cancellation:** khi người dùng hủy, timeout hoặc đã có đủ dữ liệu, dừng nhu cầu nhận tiếp và giải phóng tài nguyên liên quan.
4. **Tính đúng đắn:** phân biệt response headers đã có với body đã đọc xong; kiểm tra HTTP status, byte count, lỗi đọc và terminal signals.
5. **Kiểm thử tái hiện được:** tạo server cục bộ có response dài và chia chunk, cho subscriber nhận chậm, sau đó hủy trước khi đọc hết.
6. **Tương thích:** dùng đúng những phương thức đã có trong Java 11; không dựa vào các API chỉ được bổ sung trong JDK mới hơn.

**Giới hạn của bài:** nội dung chính là **nhận streaming HTTP response body** ở phía Java HTTP client. Với **request body upload**, `HttpRequest.BodyPublisher` cũng có cơ chế Flow nhưng vòng đời khác; không nên copy trực tiếp logic hủy của response vào upload mà bỏ qua đặc tả tương ứng.

## 2. Tại sao `sendAsync()` hoàn thành mà body vẫn đang chạy?

Với handler `BodyHandlers.ofString()` hoặc `ofByteArray()`, response thường chỉ sẵn sàng khi body đã được tích lũy đầy đủ vào giá trị kết quả. Nhưng với một **streaming handler**, `HttpResponse` có thể trở lại khi **headers đã đọc xong**, trong khi còn rất nhiều body bytes chưa đến.

Ví dụ:

```java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
    client.sendAsync(request, HttpResponse.BodyHandlers.ofPublisher())
          .get(5, TimeUnit.SECONDS);
```

Đây là **snippet** cần có `client`, `request` và imports như chương trình đầy đủ ở mục 9. Khi `get()` trả `HttpResponse`:

- Có thể kiểm tra `response.statusCode()` và `response.headers()`.
- `response.body()` trả **`Flow.Publisher<List<ByteBuffer>>`**, tức nguồn để **subscribe và đọc body**.
- Body **chưa chắc đã được nhận hết**; thậm chí ở chế độ publisher, dữ liệu body chỉ được đưa tới consumer khi có subscription và demand hợp lệ.
- Hoàn tất `CompletableFuture<HttpResponse<...>>` **không phải** bằng chứng consumer đã ghi hết file, parse hết dữ liệu hay đã nhận `onComplete()`.
- Nếu quyết định không đọc nữa, không được bỏ quên body publisher; phải **subscribe và cancel** hoặc dùng một handler khác có cách kết thúc tài nguyên rõ ràng.

**Hai giai đoạn khác nhau:**

```text
HttpClient.sendAsync(request, BodyHandlers.ofPublisher())
                 |
                 | nhận response headers
                 v
       CompletableFuture<HttpResponse<Publisher>>
                 |
           status / headers
                 |
           response.body()
                 |
             subscribe()
                 |
            onSubscribe(s)
                 |
             request(n)
                 |
           onNext(batch) ...
                 |
         +-------+---------+
         |                 |
      onComplete         cancel()
    hoặc onError        best-effort stop
         |                 |
    body terminal     app tự ghi nhận hủy;
                       terminal callback không chắc có
```

Đừng triển khai `sendAsync(...ofPublisher()).thenRun(() -> markDownloadCompleted())` rồi gọi download thành công: bước đó có thể chỉ báo **headers sẵn sàng**. Cần theo dõi tín hiệu xử lý body ở **subscriber**, cộng kích thước các batches, xác thực nội dung nếu cần, và phân biệt **completed, cancelled, failed**.

## 3. API Java 11 nào phù hợp cho bên nhận chậm?

| API | Dạng trả về | Ý nghĩa | Điểm cần nhớ |
| --- | --- | --- | --- |
| `BodyHandlers.ofPublisher()` | `Publisher<List<ByteBuffer>>` | Cho subscriber tự điều khiển demand và hủy. | Publisher **chỉ được subscribe một lần**. |
| `BodyHandlers.ofInputStream()` | `InputStream` | Đọc body theo từng khối bằng `read(...)`. | **Đọc tới EOF hoặc `close()`** nếu dừng sớm. |
| `BodyHandlers.ofLines()` | `Stream<String>` | Đọc body dạng các dòng text. | Đọc hết hoặc **`BaseStream.close()`**. |
| `BodyHandlers.fromSubscriber(...)` | `Void` hoặc kết quả qua finisher | Dùng `Flow.Subscriber<List<ByteBuffer>>` do ứng dụng cung cấp. | Vòng đời response-future/finisher khác `ofPublisher()`; cần xử lý terminal. |
| `BodyHandlers.fromLineSubscriber(...)` | Subscriber nhận `String` từng dòng. | Phù hợp cho line protocol/NDJSON theo quy tắc tách dòng. | Dòng text không đồng nghĩa byte chunk; charset/boundaries phải đúng. |
| `BodyHandlers.ofFile(path)` | `Path` | Ghi toàn bộ body vào file. | Không trả response cho đến khi file body đã được ghi theo handler. |
| `BodyHandlers.ofByteArray()` | `byte[]` | Thu body đầy đủ trong bộ nhớ. | Không phù hợp cho file không giới hạn kích thước. |
| `BodyHandlers.ofString()` | `String` | Thu/giải mã body đầy đủ trong bộ nhớ. | Không phải streaming consumer có demand do app kiểm soát. |
| `BodyHandlers.ofByteArrayConsumer(...)` | `Void` | Callback nhận các byte arrays khi chúng tới. | Javadoc Java 11 nêu **không flow-controlled**, consumer phải xử lý kịp tốc độ đến. |

Bài chọn **`ofPublisher()`** vì thể hiện rõ cả **`request(n)`** và **`cancel()`**. Với một tác vụ ghi file đơn giản, `ofFile(path)` có thể ít code và an toàn hơn; với logic chặn đọc theo block, `ofInputStream()` dễ đọc hơn. **Chọn API theo yêu cầu**, không ép mọi HTTP request phải dùng reactive subscriber.

### Chính xác kiểu của một phần body

Đây không phải `Flow.Publisher<ByteBuffer>`, cũng không phải `Publisher<byte[]>`:

```java
Flow.Publisher<List<ByteBuffer>>
```

Mỗi lần `onNext(...)` được gọi, consumer nhận **một `List<ByteBuffer>`**. Một list có thể chứa một hay nhiều buffers và một buffer có thể chứa nhiều bytes. Vì vậy:

- `request(1)` yêu cầu tối đa **một lần gọi `onNext` tiếp theo**, không phải **một byte**.
- Kích thước dữ liệu trong một `onNext` **không cố định**, không phải luôn 8 KiB, và không gắn 1:1 với chunk HTTP/TCP packet/server write.
- Để đếm bytes, duyệt **mọi `ByteBuffer` trong list**, cộng `buffer.remaining()` hoặc consume bytes đúng cách.
- Không lưu tham chiếu `ByteBuffer` và xử lý sau callback mà không hiểu ownership/lifetime. Nếu phải xử lý async, copy dữ liệu vào bounded buffer **được quản lý** hoặc xử lý ngay trước khi request item tiếp theo.
- `ByteBuffer.remaining()` là số bytes từ `position` tới `limit`, không phải `capacity()`. Nếu dùng `capacity()`, byte count sẽ sai.

## 4. Cơ chế `Flow.Subscription` và backpressure

Java 11 có chuẩn **`java.util.concurrent.Flow`** với:

- `Flow.Publisher<T>`: nguồn phát items.
- `Flow.Subscriber<T>`: bên nhận.
- `Flow.Subscription`: liên kết giữa hai bên, dùng **`request(n)`** và **`cancel()`**.
- `Flow.Processor<T,R>`: có thể vừa nhận vừa phát, dùng khi ghép nhiều stages có quản lý demand.

**Vòng đời thông thường:**

```text
subscribe(subscriber)
       |
       v
onSubscribe(subscription)
       |
       +-- request(1)  ------> cho phép 1 onNext
                                |
                                v
                          onNext(batch)
                                |
                       xử lý batch xong
                                |
                                v
                          request(1)
                                |
                               ...
                                |
                         onComplete()  /  onError(error)
```

`request(n)` **tăng lượng demand** chưa được đáp ứng. Nếu `n <= 0`, đặc tả Flow sẽ báo `onError(IllegalArgumentException)`. `request(Long.MAX_VALUE)` thực tế có thể coi như demand không giới hạn; đây không phải lựa chọn đúng khi app cần điều tiết backpressure theo capacity còn trống.

Với consumer chậm, một chiến lược cơ bản là **chỉ request một item khi đã xử lý item trước**. Bài kiểm thử sẽ mô phỏng một giai đoạn xử lý chậm bằng **`ScheduledExecutorService`**: nó **đợi 20 ms trước khi gửi demand tiếp theo**, nhưng không `Thread.sleep()` ngay trong callback do HTTP client gọi.

### Backpressure không đồng nghĩa “server lập tức ngừng gửi”

`Flow.Subscription.request(1)` điều khiển việc publisher phát dữ liệu tới **subscriber này**. Các lớp khác vẫn có thể có buffer:

- HTTP client đang có buffers nội bộ.
- TCP receive/send buffers trong OS.
- Proxy, HTTP/2 flow-control windows và HTTP server có thể buffer.
- Server có thể đã ghi dữ liệu xuống socket trước khi subscriber chậm.
- Các hệ thống hoặc adapter trung gian có thể chuyển demand thành một cơ chế flow control khác.

Do đó **không suy ra `request(1)` khiến server chỉ được phép gửi đúng 8 KiB hoặc chỉ chiếm đúng một batch RAM ở mọi tầng**. Backpressure giúp ứng dụng kiểm soát tốc độ tiếp nhận ở API boundary, nhưng cần **giới hạn queue, concurrency, số bytes và tài nguyên** để bảo vệ toàn bộ pipeline.

## 5. Tại sao không `Thread.sleep(...)` trong `onNext()`?

`onNext` có thể được gọi trên một thread do HTTP client/provider quản lý. Nếu callback **blocking lâu**, ví dụ parse JSON nặng, ghi DB chậm, gọi network khác hoặc `Thread.sleep(1000)`, ta có thể:

- Giữ các thread quan trọng của HTTP client/provider quá lâu.
- Làm chậm các subscriptions khác.
- Tăng memory/queue pressure ở tầng khác.
- Tăng nguy cơ deadlock nếu callback chờ một future phụ thuộc chính luồng đó.
- Khiến latency và connection reuse xấu đi.

**Lựa chọn tốt hơn:** callback làm công việc nhẹ (kiểm tra schema, byte count, đưa dữ liệu vào bounded pipeline), rồi chỉ cấp demand tiếp khi downstream có capacity. Trong demo, dùng một **scheduler độc lập** gọi `subscription.request(1)` sau khoảng 20 ms để mô phỏng consumer chậm **mà không block callback 20 ms**.

**Không đồng nghĩa** mọi xử lý data thực tế chỉ cần timer: nếu ghi file, bảo đảm write hoàn thành trước khi request thêm; nếu xử lý DB, dùng completion signal của downstream và quản lý số tác vụ đồng thời. Timer chỉ là fixture dùng để kiểm tra semantics backpressure.

### Tránh unbounded queue khi chuyển việc ra executor

Mô hình nguy hiểm:

```java
@Override
public void onNext(List<ByteBuffer> batch) {
    unboundedExecutor.submit(() -> process(batch));
    subscription.request(Long.MAX_VALUE);
}
```

Đây là **mã minh họa sai, không chạy độc lập**: `unboundedExecutor` và `process` không được định nghĩa. Nó thể hiện lỗi thiết kế: downstream tạo tác vụ không giới hạn, publisher được phép tiếp tục phát vô hạn, và các `ByteBuffer` có thể không an toàn để lưu lâu mà không copy/quản lý lifecycle.

Thiết kế phù hợp hơn:

1. Dùng **bounded queue** hoặc semaphore permits.
2. Bảo đảm sở hữu dữ liệu (copy cần thiết hoặc xử lý trong callback).
3. Chỉ `request(1)` khi một slot xử lý đã sẵn sàng.
4. Đặt deadline/tổng byte limit để không giữ connection mãi khi downstream treo.
5. Khi lỗi downstream, **cancel subscription** và báo lỗi qua một state/future riêng của ứng dụng.

## 6. Hủy giữa chừng bằng `Flow.Subscription.cancel()`

Với `BodyHandlers.ofPublisher()`, khi subscriber đã nhận `Flow.Subscription` ở `onSubscribe`, nó có thể:

```java
subscription.cancel();
```

Theo Java 11 `Flow.Subscription`, **`cancel()` là best-effort**:

- Nó yêu cầu eventually stop delivering items.
- Có thể vẫn có thêm signal/message do race/in-flight data.
- **Không đảm bảo** subscriber sẽ nhận `onComplete()` hoặc `onError()` sau khi hủy.
- Không đảm bảo server ngay lập tức dừng write hoặc không có một byte nào được gửi thêm qua network.
- Tùy giao thức HTTP/1.1, HTTP/2 và implementation, cancellation có thể làm **đóng connection, reset stream hoặc hạn chế connection reuse**. Không coi hủy một stream là đóng chắc chắn toàn bộ connection trong mọi trường hợp.

**Điểm đặc biệt quan trọng:** sau `cancel()`, ứng dụng phải có **cơ chế hoàn tất/cập nhật trạng thái riêng** (ví dụ `CompletableFuture<Result>` hoặc atomic lifecycle state), vì chờ `onComplete()` sau cancel có thể khiến tác vụ treo vô hạn.

### Hủy không giống nhận hết body

| Kết thúc | Đang xảy ra gì? | Cách đánh dấu |
| --- | --- | --- |
| **`onComplete()`** | Publisher báo đã phát hết data cho subscription này theo điều kiện bình thường. | Có thể đánh dấu **body fully consumed** nếu app đã xử lý hết bytes và validate đủ. |
| **`onError(error)`** | Publisher thông báo lỗi không phục hồi. | Đánh dấu **failed**, propagate nguyên nhân, cleanup. |
| **`cancel()`** | Subscriber không muốn nhận tiếp. | Đánh dấu **cancelled/partial** ở application state ngay theo logic của mình. |
| **Response headers available** | HTTP status/headers đã đọc được. | **Không** đánh dấu body completed. |
| **`sendAsync future.cancel(true)`** | Yêu cầu hủy CompletableFuture/request theo contract runtime. | Không dùng làm thay thế duy nhất cho `Flow.Subscription.cancel()` khi publisher đã được trả về. |

**Khi hủy một download** đã ghi file tạm, phải quyết định rõ: xóa file không hoàn chỉnh, đánh dấu partial/resumable nếu protocol hỗ trợ, hoặc lưu checksum/offset được xác minh. Không rename file partial thành file hoàn chỉnh chỉ vì `sendAsync` future thành công hoặc `cancel()` không ném exception.

### Hủy và HTTP/1.1 so với HTTP/2

- **HTTP/1.1:** một response đang được truyền trên một connection; không đọc hết mà cancel có thể khiến connection không reuse được.
- **HTTP/2:** protocol multiplex nhiều streams trên một connection; implementation có thể hủy stream mà không phải đóng connection, nhưng **không có bảo đảm từ Java API rằng mọi connection sẽ luôn được reuse**.
- **Flow cancellation:** là API-level signal, còn TCP/HTTP thực tế xử lý bất đồng bộ. Không test giả định “server đã gửi chính xác N bytes trước khi bị hủy”.

Nếu chính ứng dụng tạo HTTP client cho nhiều requests, không xây cache/connection-health logic dựa trên việc `cancel()` đồng nghĩa “connection vẫn sạch”. Theo dõi metrics thực và đóng/giải phóng resources khi thích hợp.

## 7. Những semantics phải biết của `ofPublisher()`

### 7.1. Publisher của một response chỉ subscribe được một lần

Javadoc `HttpResponse.BodySubscribers.ofPublisher()` nêu rõ **publisher chỉ có một subscriber thực sự**:

- First subscription hợp lệ nhận response bytes.
- Một subscription thứ hai sẽ bị từ chối; subscriber sau sẽ được `onSubscribe` với empty subscription và nhận `onError(IllegalStateException)`.
- Không dùng `response.body().subscribe(a)` rồi `subscribe(b)` để vừa lưu file vừa parse JSON. **Đó không phải multicast publisher**.

Nếu muốn dữ liệu đến nhiều consumers, xây **tee/fan-out processor** có bounded buffering, quản lý backpressure của tất cả downstream và ownership ByteBuffer, hoặc ghi file một lần rồi để consumers đọc file. Mỗi downstream chậm có thể ảnh hưởng toàn pipeline; quyết định drop/buffer/wait phải rõ.

### 7.2. Mỗi subscription chỉ cần một terminal path

`Flow.Subscriber` được gọi theo thứ tự tuần tự cho subscription. Khi `onComplete` hoặc `onError` đã xảy ra, không được thiết kế logic cần một terminal callback thứ hai. Với `cancel`, **không được đợi** bất kỳ terminal callback nào để bắt đầu cleanup.

Phân biệt:

- **Normal success:** body fully processed và `onComplete()`.
- **Error:** `onError()` hoặc lỗi request trước khi có publisher.
- **Cancellation:** chính ứng dụng cancel và hoàn tất trạng thái `cancelled`.
- **Timeout:** downstream quá lâu; app phải **cancel**, không chỉ hoàn tất future báo timeout.
- **Shutdown:** app/server ngừng; cleanup đang hoạt động, báo tác vụ không hoàn chỉnh nếu cần.

### 7.3. `Flow.Subscription.request(n)` đếm item, không phải bytes

Trong API này, **mỗi item là `List<ByteBuffer>`**. Nếu request một item, một `onNext` có thể chứa nhiều buffers. Do vậy, mỗi batch có thể vượt qua một ngưỡng byte. Nếu logic “hủy khi >= 64 KiB”, số byte cuối nhận được có thể **lớn hơn 64 KiB**; đừng assert chính xác bằng 64 KiB.

Trong demo, điều kiện test đúng là:

```text
cancel-bytes-positive=true
cancel-bytes-less-than-total=true
```

Không kiểm tra `cancel-bytes==65536` hay `cancel-batches==8`: những đại lượng đó phụ thuộc HTTP client buffering, server scheduling và hệ điều hành.

## 8. Thiết kế bài test không phụ thuộc mạng ngoài

Để xác minh thật sự việc **streaming body, bên nhận chậm, hủy giữa chừng**, ta tạo:

- **Local HTTP server** qua `com.sun.net.httpserver.HttpServer` (module `jdk.httpserver` có trong JDK 11 phù hợp). Đây là **test server**, không phải gợi ý chọn server cho production.
- Endpoint **`/full`** gửi **512 KiB** dữ liệu, chia khối `8192` byte và `flush` để mô phỏng streaming.
- Endpoint **`/cancel`** dự kiến gửi **8 MiB**, đủ lớn để consumer có cơ hội hủy sớm.
- Server chạy trên **`127.0.0.1`** với port hệ điều hành tự cấp, không dùng Internet hoặc hard-code một port có thể bị chiếm.
- Client dùng **HTTP/1.1** có chủ đích để tính chất network test dễ giải thích; đây không phải giới hạn của `ofPublisher`.
- Subscriber `SlowSubscriber` chỉ `request(1)` ở đầu; sau mỗi `onNext`, scheduler đợi **20 ms** rồi mới request item kế tiếp.
- Mode full duyệt tới `onComplete`; mode cancel hủy khi đã quan sát ít nhất **64 KiB**.
- Chương trình không in timestamps, port, số network chunks hoặc byte count thực tế lúc hủy, vì những thông số ấy không tất định.

Kỳ vọng kiểm chứng:

| Tình huống | Đúng khi nào? | Vì sao |
| --- | --- | --- |
| Full response | HTTP `200`, body `524288` bytes, `onComplete` được gọi, không cancel trước. | Đã đọc trọn body. |
| Bên nhận chậm | `onNext` có ít nhất một batch và demand được cấp từng batch qua timer. | Thử được control flow có backpressure. |
| Hủy giữa chừng | HTTP `200`, đã nhận số byte > 0 nhưng nhỏ hơn **8 MiB**, đặt `cancelled=true`. | Đã nhận một phần, chủ động cancel, không đợi terminal. |
| Cleanup | Server, thread pool và scheduler được dừng ở `finally`. | Test không để lại service hoặc threads chạy nền. |
| Không dựa số chunks | Không assert số lần `onNext` chính xác. | Chunk boundaries là implementation detail. |

**Thí nghiệm không chứng minh backpressure end-to-end tuyệt đối đến socket/server:** nó kiểm chứng giao thức `Flow` và tài nguyên bên nhận, còn TCP window và buffering của HTTP client có hành vi phụ thuộc implementation.

## 9. Java 11 hoàn chỉnh, đã biên dịch và chạy: `HttpSlowCancelDemo.java`

### 9.1. Mã nguồn

Lưu đúng file **`HttpSlowCancelDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
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
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public final class HttpSlowCancelDemo {
    private static final int BLOCK = 8192;
    private static final int FULL_BYTES = 512 * 1024;
    private static final int CANCEL_BYTES = 8 * 1024 * 1024;

    private static void serve(HttpExchange exchange, int total) throws IOException {
        exchange.getResponseHeaders().set(
                "Content-Type", "application/octet-stream");
        exchange.sendResponseHeaders(200, 0);
        byte[] block = new byte[BLOCK];
        Arrays.fill(block, (byte) 7);
        try (OutputStream stream = exchange.getResponseBody()) {
            for (int sent = 0; sent < total; sent += BLOCK) {
                int n = Math.min(BLOCK, total - sent);
                stream.write(block, 0, n);
                stream.flush();
                try {
                    Thread.sleep(2);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        } catch (IOException connectionClosedByClient) {
            // HTTP/1.1 cancellation may close the TCP connection.
        } finally {
            exchange.close();
        }
    }

    static final class Result {
        final long bytes;
        final int batches;
        final boolean cancelled;
        final boolean completed;

        Result(long bytes, int batches, boolean cancelled, boolean completed) {
            this.bytes = bytes;
            this.batches = batches;
            this.cancelled = cancelled;
            this.completed = completed;
        }
    }

    static final class SlowSubscriber implements Flow.Subscriber<List<ByteBuffer>> {
        private final ScheduledExecutorService scheduler;
        private final long cancelAt;
        private final CompletableFuture<Result> done = new CompletableFuture<>();
        private final AtomicLong bytes = new AtomicLong();
        private final AtomicInteger batches = new AtomicInteger();
        private volatile Flow.Subscription subscription;
        private volatile boolean cancelled;

        SlowSubscriber(ScheduledExecutorService scheduler, long cancelAt) {
            this.scheduler = scheduler;
            this.cancelAt = cancelAt;
        }

        @Override
        public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            s.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> buffers) {
            long amount = 0;
            for (ByteBuffer buffer : buffers) {
                amount += buffer.remaining();
            }
            long total = bytes.addAndGet(amount);
            int count = batches.incrementAndGet();

            if (cancelAt > 0 && total >= cancelAt) {
                cancelled = true;
                subscription.cancel();
                done.complete(new Result(total, count, true, false));
            } else {
                scheduler.schedule(() -> {
                    if (!cancelled) {
                        subscription.request(1);
                    }
                }, 20, TimeUnit.MILLISECONDS);
            }
        }

        @Override
        public void onError(Throwable error) {
            done.completeExceptionally(error);
        }

        @Override
        public void onComplete() {
            done.complete(new Result(
                    bytes.get(), batches.get(), false, true));
        }

        void cancel() {
            Flow.Subscription s = subscription;
            if (s != null) {
                cancelled = true;
                s.cancel();
            }
        }

        Result await() throws Exception {
            return done.get(15, TimeUnit.SECONDS);
        }
    }

    static HttpResponse<Flow.Publisher<List<ByteBuffer>>> open(
            HttpClient client, URI uri) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(20)).GET().build();
        return client.sendAsync(
                request, HttpResponse.BodyHandlers.ofPublisher())
                .get(5, TimeUnit.SECONDS);
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/full", x -> serve(x, FULL_BYTES));
        server.createContext("/cancel", x -> serve(x, CANCEL_BYTES));
        var serverPool = Executors.newCachedThreadPool();
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        server.setExecutor(serverPool);
        server.start();

        SlowSubscriber full = null;
        SlowSubscriber partial = null;
        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            URI base = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort());

            HttpResponse<Flow.Publisher<List<ByteBuffer>>> r1 =
                    open(client, base.resolve("/full"));
            full = new SlowSubscriber(scheduler, 0);
            r1.body().subscribe(full);
            Result first = full.await();
            System.out.println("full-status=" + r1.statusCode());
            System.out.println("full-completed=" + first.completed);
            System.out.println("full-bytes=" + first.bytes);
            System.out.println("full-batches-positive=" + (first.batches > 0));
            System.out.println("full-cancelled=" + first.cancelled);

            HttpResponse<Flow.Publisher<List<ByteBuffer>>> r2 =
                    open(client, base.resolve("/cancel"));
            partial = new SlowSubscriber(scheduler, 64 * 1024);
            r2.body().subscribe(partial);
            Result second = partial.await();
            System.out.println("cancel-status=" + r2.statusCode());
            System.out.println("cancelled-midstream=" + second.cancelled);
            System.out.println("cancel-bytes-positive=" + (second.bytes > 0));
            System.out.println("cancel-bytes-less-than-total=" +
                    (second.bytes < CANCEL_BYTES));
            System.out.println("cancel-had-batches=" + (second.batches > 0));
        } finally {
            if (full != null) full.cancel();
            if (partial != null) partial.cancel();
            server.stop(0);
            serverPool.shutdownNow();
            scheduler.shutdownNow();
        }
    }
}
```

**Chú ý có chủ đích trong test:**

- `Thread.sleep(2)` chỉ dùng trong **server fixture**, không phải trong subscriber callback. Nó giúp response kéo dài đủ lâu cho test hủy.
- `scheduler.schedule(...)` cấp lại demand sau 20 ms mà không chiếm thread callback để ngủ.
- `slow` dùng `cancelAt=0` để đọc hết; `partial` dùng `cancelAt=64*1024` để chủ động hủy sau khi đạt ngưỡng.
- `done.complete(...)` khi hủy là **future của ứng dụng**, không phải tín hiệu do HTTP publisher hứa sẽ tự phát sau cancellation.
- `Result` ghi trạng thái kết thúc **tại thời điểm đạt điều kiện test**, tránh sửa trạng thái lịch sử khi bước `finally` dọn dẹp.
- `AtomicLong/AtomicInteger` là cách phòng vệ về concurrency/snapshot; Flow đảm bảo callback của cùng subscriber được gọi theo thứ tự tuần tự, nhưng thread phát callback vẫn có thể khác thread của app.
- Đoạn server catch `IOException` để chấp nhận trường hợp client đã đóng kết nối khi hủy. Trong production, chỉ bỏ qua lỗi đã phân loại rõ là expected client disconnect, còn lỗi server/disk khác cần log và xử lý.

### 9.2. Biên dịch và chạy Java 11

```bash
javac -encoding UTF-8 --release 11 --add-modules jdk.httpserver HttpSlowCancelDemo.java
java --add-modules jdk.httpserver HttpSlowCancelDemo
```

`HttpServer` là **JDK-specific test utility** nằm ở module `jdk.httpserver`, nên lệnh minh họa khai báo module tường minh. Client API `java.net.http` thuộc module `java.net.http` có trong Java 11. `var` là cú pháp local-variable type inference đã có trước Java 11, nên mã nguồn biên dịch hợp lệ với `--release 11`.

**Stdout chính xác đã kiểm chứng khi chạy chương trình hoàn chỉnh:**

```text
full-status=200
full-completed=true
full-bytes=524288
full-batches-positive=true
full-cancelled=false
cancel-status=200
cancelled-midstream=true
cancel-bytes-positive=true
cancel-bytes-less-than-total=true
cancel-had-batches=true
```

Các dòng **không** in số bytes nhận được trước cancellation hoặc số `onNext` chính xác, vì những số đó phụ thuộc runtime, chunking và network scheduling; chỉ kiểm tra điều kiện đúng về mặt logic.

### 9.3. Giải thích từng bước kết quả

**Full response (`/full`):**

1. Client gửi GET tới loopback HTTP server. `statusCode() == 200` xác minh response hợp lệ cho fixture.
2. `BodyHandlers.ofPublisher()` trả body publisher sau khi headers có mặt.
3. Client subscribe **một lần**, subscriber `request(1)`.
4. Sau mỗi `onNext(List<ByteBuffer>)`, subscriber cộng `remaining()` của các buffers và scheduler cấp tiếp một item demand sau 20 ms.
5. Khi publisher hoàn tất, `onComplete()` gọi `done.complete(Result)`.
6. `full-bytes=524288` chính xác bằng `512*1024` bytes server dự kiến gửi; `full-completed=true` và `full-cancelled=false` thể hiện đường hoàn tất bình thường.
7. `full-batches-positive=true` xác nhận có ít nhất một `onNext`, nhưng **không giả định 64 batches chỉ vì server ghi 64 khối 8192 bytes**.

**Partial response (`/cancel`):**

1. Server bắt đầu gửi body có tổng mục tiêu `8*1024*1024` bytes.
2. Subscriber lại `request(1)` mỗi lần, với khoảng trễ 20 ms giữa các lượt demand.
3. Khi tổng bytes quan sát được đạt **ít nhất 64 KiB**, subscriber gọi `subscription.cancel()`.
4. Ứng dụng lập tức hoàn tất future `done` theo trạng thái `cancelled`; **không đợi onComplete/onError**, vì sau cancel các callback đó có thể không đến.
5. `cancel-bytes-positive=true` chứng tỏ body đã đến một phần.
6. `cancel-bytes-less-than-total=true` xác nhận app chưa consume hết 8 MiB.
7. `cancel-had-batches=true` chứng tỏ đã có sự kiện nhận data trước khi hủy.
8. Test **không xác nhận server đã ngừng gửi chính xác tại 64 KiB**; điều này không được đảm bảo bởi `Flow.cancel`.

### 9.4. Tính tương thích và giới hạn của test

Chương trình dùng **API Java 11** và được biên dịch với `javac --release 11`. Khi chạy trên JDK mới hơn, người học cần hiểu đó là thử **class tương thích Java 11 trên runtime hiện tại**, không phải bằng chứng đã chạy trên bản JDK 11 cụ thể nếu chưa chọn đúng runtime 11.

Test fixture dùng HTTP/1.1 và loopback. Khi chuyển sang HTTP/2, server production, TLS, proxy hoặc internet latency, quy tắc Flow vẫn đúng nhưng **chunk sizes, buffering, thời điểm hủy, khả năng reuse connection và lỗi TCP** có thể khác. Không dùng một kết quả local loopback để đảm bảo network behavior trong mọi môi trường.

## 10. Một lựa chọn gọn hơn: `ofInputStream()` và `close()`

Nếu bài toán chỉ cần đọc tuần tự theo buffer và không muốn tự viết `Flow.Subscriber`, Java 11 có thể dùng:

```java
HttpResponse<InputStream> response =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());

if (response.statusCode() != 200) {
    try (InputStream errorStream = response.body()) {
        // Xử lý/trích giới hạn dữ liệu lỗi hoặc đóng ngay.
    }
    throw new IOException("HTTP " + response.statusCode());
}

try (InputStream body = response.body()) {
    byte[] buffer = new byte[8192];
    long total = 0;
    int n;
    while ((n = body.read(buffer)) != -1) {
        total += n;
        // Xử lý/chuyển tiếp buffer[0..n) trước khi đọc tiếp.
        if (total >= 64 * 1024) {
            break; // Ví dụ chủ động không đọc tiếp.
        }
    }
} // close() nếu chưa EOF, thông báo dừng/giải phóng tài nguyên.
```

Đây là **snippet** phải đặt trong method có `HttpClient client` và `HttpRequest request`, imports `java.io.InputStream`/`IOException`. `try-with-resources` quan trọng hơn việc chỉ `break`:

- `BodyHandlers.ofInputStream()` trả một stream mà response headers có thể sẵn sàng khi body chưa nhận hết.
- Khi đọc tới **EOF**, connection có cơ hội được tái sử dụng theo implementation.
- Khi **không đọc hết**, gọi `InputStream.close()` để giải phóng resources. Javadoc Java 11 nêu việc đóng sớm **có thể làm underlying HTTP connection bị đóng**.
- **Không** bỏ stream lại mà không đọc hoặc đóng; có thể giữ resources/connection và gây cạn connection pool.
- Với body lớn, không gọi `readAllBytes()` rồi nhận là vẫn đang thực hành bounded streaming; method này tạo một array chứa toàn bộ bytes.
- Với không có nhu cầu tự quản lý reactive pipeline, cách dùng stream có thể ít code hơn nhưng **`read()` là blocking operation**; nên chạy trong luồng/worker phù hợp, không trên UI/event loop.

**Phân biệt với `Flow.cancel()`:** `InputStream.close()` là con đường kết thúc tài nguyên của streaming InputStream, còn `Flow.Subscription.cancel()` là con đường của subscriber. Không thay chúng bằng một `CompletableFuture.cancel()` khi body đã được bàn giao.

## 11. Xử lý lỗi HTTP status và body khi muốn bỏ qua

Các `BodyHandlers` chuẩn như `ofPublisher()` **không tự reject HTTP 404/500**. Một HTTP response 503 vẫn có body (thậm chí rất dài). Vì vậy phải:

- Kiểm tra `statusCode()` trước khi giả định payload là business data.
- Nếu không cần error body, **subscribe rồi cancel** (đối với `ofPublisher`) hoặc **close stream** (đối với `ofInputStream`), không bỏ response body treo.
- Nếu cần error payload, đọc **có giới hạn bytes/time**, tránh server trả lỗi hàng GB làm app OOM.
- Với API nâng cao, có thể dùng `BodyHandler` tùy biến nhận `ResponseInfo` và chọn subscriber phù hợp dựa trên status/headers, ví dụ `discarding()` cho những response không cần giữ body.
- Đừng đặt mọi HTTP 4xx/5xx thành lỗi transport: status code là HTTP application-level outcome; transport `IOException` hoặc `onError` là đường lỗi khác.

Ví dụ **snippet** của một `BodyHandler` custom:

```java
HttpResponse.BodyHandler<Void> handler = info ->
        HttpResponse.BodySubscribers.discarding();
```

Đây là handler **luôn bỏ body**, không phải đoạn mã kiểm tra status; trong code thực tế, `info.statusCode()` có thể quyết định handler và downstream type. Cần chú ý generic types và tradeoff streaming/cancellation: discarding body tới cuối khác hủy sớm; việc bỏ nhưng **drain tới hết** có thể cho phép reuse connection, nhưng tiêu tốn network time/bandwidth.

## 12. Timeout và hủy đúng ở từng tầng

Cần phân biệt bốn loại thời hạn:

| Giới hạn | Áp dụng | Khi quá hạn |
| --- | --- | --- |
| **`connectTimeout`** trên `HttpClient.Builder` | Thiết lập connection. | Không thay toàn bộ deadline cho body processing. |
| **`HttpRequest.Builder.timeout(Duration)`** | Timeout của HTTP request theo client contract. | Không dùng như cơ chế duy nhất bảo vệ **downstream consumer** khi body đã giao thành streaming publisher. |
| **`CompletableFuture.get(timeout, unit)`** | Thời gian caller chờ một future hoàn thành. | Nó có thể ném `TimeoutException` nhưng **không tự động cancel mọi công việc HTTP/body**. |
| **Application body processing deadline** | Thời hạn từ headers tới fully consumed hoặc cancelled. | Phải tự **cancel `Flow.Subscription`** hoặc close `InputStream` khi deadline qua. |

Trong ví dụ, `open(...)` dùng `get(5,SECONDS)` để giới hạn chờ response headers, trong khi `SlowSubscriber.await()` dùng `get(15,SECONDS)` cho phần body. **Đây là hạn mức của bài test**, không phải khuyến nghị hard-code 5/15 giây cho mọi ứng dụng.

**Đường xử lý chuẩn nếu body chậm quá deadline:**

```text
Deadline exceeded
       |
       +-- mark request outcome TIMEOUT
       |
       +-- cancel Flow.Subscription
       |   (hoặc close InputStream)
       |
       +-- stop downstream jobs / release permits / temp files
       |
       +-- publish result once with timeout cause
       |
       +-- observe metrics; do not await onComplete after cancel
```

Nếu `done.get(...)` ném `TimeoutException`, phải **đảm bảo cleanup trong `catch/finally`**. Trong chương trình demo, `finally` gọi `cancel()` cho các subscriber đã được tạo, rồi dừng server/scheduler. Với ứng dụng sản phẩm, cần xử lý thêm tình huống **timeout trước khi `onSubscribe` có mặt**: lưu ý cancellation state và hủy subscription ngay khi nó đến, hoặc hủy HTTP request future khi còn đang chờ headers.

**Không đồng nhất `CompletableFuture.orTimeout(...)` với transport cancellation.** Nó làm future hoàn thành thất bại theo timeout nhưng không tự bảo đảm body publisher dừng và mọi tài nguyên được giải phóng. Cần một đường cancel/close cụ thể cho resource đang mở.

## 13. Exception, race và đúng một lần hoàn tất

Các race đáng kiểm thử:

1. Hủy ngay sau `onSubscribe` nhưng trước lần `onNext` đầu tiên.
2. Hủy **đúng lúc `onNext` đang được phát**.
3. Hủy khi `onComplete` gần xảy ra.
4. Downstream lỗi trong lúc một lượt `request(1)` đã được lên lịch.
5. Server đóng socket giữa chừng.
6. Consumer vượt deadline nhưng một callback từ request trước vẫn tới.
7. Ứng dụng shutdown trong khi subscriber đang chờ chunk tiếp.
8. Có hai nơi cùng yêu cầu cancel (người dùng + timeout).

Một trạng thái hệ thống phù hợp có thể dùng:

```text
NEW -> HEADERS_RECEIVED -> SUBSCRIBED -> RECEIVING
                                          |
                        +-----------------+----------------+
                        |                 |                |
                    COMPLETED          FAILED           CANCELLED
                  (onComplete)        (onError)     (app action / timeout)
```

**Đừng cập nhật `CANCELLED` thành `COMPLETED` chỉ vì một tín hiệu đến muộn**. Trong hệ thống nghiêm túc, dùng một state machine có atomic compare-and-set hoặc `CompletableFuture.complete` để chỉ một outcome được chấp nhận. `CompletableFuture.complete` chỉ thành công ở lần đầu; đây là công cụ hữu ích, nhưng bản thân nó không thay thế việc release network resource.

### Một trường hợp anti-pattern

```java
subscription.cancel();
done.get(); // Có thể chờ vô hạn nếu chỉ complete trong onComplete/onError.
```

Đây là **snippet sai**, không phải khuyến nghị. `Flow.Subscription` không bảo đảm phát terminal callback sau cancellation. Cần tự complete `done` khi chọn cancellation, hoặc có một cancellation future riêng.

### Không để exception thoát ra trực tiếp từ `onNext`

`Flow.Subscriber.onNext` không có khai báo checked exceptions. Nếu code muốn parse/decode/ghi và có lỗi, ứng dụng cần xử lý lỗi nội bộ, thông báo failure qua future và cancel subscription:

```java
try {
    processBatch(buffers);
} catch (Exception error) {
    subscription.cancel();
    done.completeExceptionally(error);
}
```

Đây là **snippet minh họa** cần có `processBatch`/`buffers`/`subscription`/`done`; không phải một chương trình độc lập. Phải tránh trường hợp xử lý nửa batch rồi request thêm trước khi cập nhật state. Nếu có IO/DB output, quyết định rollback/partial cleanup theo mục tiêu nghiệp vụ.

## 14. Kiểm soát tài nguyên: bytes, queue, concurrency, memory

Backpressure có ích nhưng không thay thế resource limits.

| Rủi ro | Cách kiểm soát |
| --- | --- |
| **Body kích thước không biết trước** | Đặt giới hạn tổng bytes app chấp nhận; hủy khi vượt. |
| **Bên nhận quá chậm** | Deadline và idle timeout riêng; không giữ connection vô hạn. |
| **Quá nhiều downloads đồng thời** | Semaphore hoặc bounded concurrency; tránh mở hàng nghìn streams chưa consume. |
| **Downstream queue không giới hạn** | Dùng bounded queue và chỉ request khi có capacity. |
| **Một `onNext` quá lớn** | Kiểm tra tổng `remaining()` trước khi cấp phát/copy; không coi batch luôn 8 KiB. |
| **Nhiều `ByteBuffer` một list** | Duyệt toàn list; không bỏ sót buffers sau phần tử đầu. |
| **Byte count tràn** | Dùng `long` và kiểm tra overflow khi nhận dữ liệu không tin cậy. |
| **File tạm khi hủy** | Đánh dấu partial, close/delete hoặc resume theo protocol có xác thực. |
| **Kết nối HTTP không reuse** | Quan sát metrics và behavior theo protocol; cancellation có thể làm close connection. |
| **HTTP 503 với body dài** | Giới hạn dữ liệu error body và kết thúc subscription phù hợp. |
| **Tệp nén/giải nén** | Giới hạn cả compressed bytes và expanded content; tránh decompression bomb. |
| **Sai checksum hoặc Content-Length** | Xác thực byte count, checksum và protocol khi **đọc hết**; cancelled body không phải payload hợp lệ đầy đủ. |

### Byte budget phải được tính theo body mà ứng dụng thực nhận

Nếu protocol ứng dụng yêu cầu tối đa 100 MiB **sau giải nén**, chỉ đặt `Content-Length <= 100MiB` không đủ. Server có thể dùng transfer-encoding chunked (không có Content-Length) hoặc nén dữ liệu. Cần kiểm tra kích thước khi **đang xử lý**, dừng khi vượt giới hạn, và giữ số bytes/records đọc đã xử lý để log có thể hành động.

Khi tính `total += amount` với input có khả năng rất lớn, dùng arithmetic có kiểm tra overflow hoặc so sánh theo remaining budget. Mã demo dùng số nhỏ cố định để tập trung vào streaming/cancellation; product code cần byte cap rõ.

## 15. Ưu tiên response handler đơn giản khi phù hợp

Một số lựa chọn triển khai thực tế:

**Ghi file đầy đủ:** dùng `BodyHandlers.ofFile(path)` nếu không cần kiểm soát transform từng chunk; chuẩn bị đường dẫn an toàn và ghi file tạm rồi rename sau khi hoàn tất. Nếu cần abort sớm theo nội dung hoặc dữ liệu lạ, dùng publisher/inputstream có byte budget.

**Đọc text theo dòng:** dùng `BodyHandlers.ofLines()` hoặc `fromLineSubscriber(...)`. Với NDJSON, cần hiểu charset, dòng cuối thiếu newline, newline boundaries qua bytes và trường hợp một dòng cực dài. Một line có thể chứa dữ liệu lớn bất thường nên cần limit.

**Xử lý nhị phân hoặc tự tạo pipeline:** dùng `ofPublisher()` với `Flow.Subscriber<List<ByteBuffer>>`; nhớ mỗi batch là list và chỉ subscribe một lần. Nếu muốn nhận rồi write DB, cân nhắc bounded queue và request-on-completion.

**Cần blocking parser:** dùng `ofInputStream()` trong một worker thread phù hợp. `try-with-resources` đảm bảo close khi parser báo lỗi hoặc đủ dữ liệu.

**Dữ liệu nhỏ và đã có giới hạn chắc chắn:** `ofByteArray` hoặc `ofString` có thể đơn giản và tốt hơn, nhưng **đừng dùng cho body chưa biết giới hạn**.

Không có một API tốt nhất cho mọi mục đích. Đo số bytes/second, peak resident memory, số connections đang mở, queue depth, tail latency và cancellation effectiveness trên runtime/HTTP protocol thực.

## 16. Những giả định sai thường gặp

| Giả định sai | Cách hiểu đúng |
| --- | --- |
| “`sendAsync` trả response thì toàn bộ body đã xong.” | Với `ofPublisher`/`ofInputStream`, **headers có thể sẵn trước body**. |
| “`ofPublisher` là `Publisher<byte[]>`.” | Kiểu chính xác là `Publisher<List<ByteBuffer>>`. |
| “`request(1)` nhận một byte hoặc một HTTP chunk.” | Nó cấp demand cho **một `onNext` item**, là một list buffers. |
| “Server ghi 8192 byte/lần thì subscriber cũng nhận đúng 8192.” | HTTP/TCP/client buffering không bảo đảm 1:1. |
| “Backpressure ngăn mọi buffering trong network stack.” | Nó kiểm soát demand ở Flow boundary; các tầng vẫn có buffers. |
| “Consumer chậm thì `Thread.sleep` ngay trong callback cho dễ.” | Có thể block thread client/provider; nên schedule demand khi sẵn capacity. |
| “`request(Long.MAX_VALUE)` sẽ bảo vệ RAM.” | Đó là demand thực tế không giới hạn; cần bounded processing. |
| “`cancel()` dừng network ngay lập tức.” | **Best-effort**; in-flight messages có thể còn đến. |
| “Sau `cancel()` chắc chắn nhận `onComplete`.” | **Không bảo đảm**; app tự hoàn tất state cancelled. |
| “`CompletableFuture.cancel(true)` luôn hủy body publisher đã trả về.” | Không dùng thay thế cho hủy **Flow subscription** sau khi body đã được giao. |
| “Hủy response luôn giữ connection reuse.” | Có thể đóng connection/stream tùy HTTP version. |
| “Không subscribe và bỏ `response.body()` sẽ tự cleanup.” | Javadoc yêu cầu subscribe và consume/cancel để giải phóng resource. |
| “Một publisher có thể subscribe nhiều consumers.” | `ofPublisher` của mỗi response **chỉ một subscriber**. |
| “Lưu `ByteBuffer` vào queue vô hạn rồi dùng sau là an toàn.” | Cần ownership/copy và bounded queue. |
| “`buffer.capacity()` là số bytes nhận được.” | Phải đọc `buffer.remaining()` hoặc số bytes đã consume. |
| “HTTP 404/503 sẽ ném IOException.” | HTTP status application-level vẫn là response hợp lệ có body. |
| “Request timeout tự bảo vệ downstream parser.” | Streaming body có vòng đời riêng; cần application deadline/cancellation. |
| “`InputStream.close()` luôn phải đọc hết trước.” | Có thể close sớm để hủy, nhưng ảnh hưởng connection reuse. |
| “Gọi `readAllBytes()` trên stream là bounded streaming.” | Nó tích lũy toàn bộ body vào RAM. |
| “Cancelled download vẫn có file hợp lệ để dùng.” | Đây là **partial data**, cần kiểm chứng/resume hoặc xóa. |
| “Bài test localhost chứng minh server production lập tức dừng gửi.” | Nó chỉ xác minh hành vi client/subscriber trong fixture cụ thể. |
| “Các callback sau cancel không thể xảy ra.” | `Flow.cancel` cho phép additional messages trong race. |
| “HttpClient Java 11 dùng `try (HttpClient client = ...)`.” | `HttpClient` Java 11 **không triển khai AutoCloseable**; phương thức close/shutdown có ở các JDK mới hơn, không copy vào bài Java 11. |

## 17. Chiến lược kiểm thử có giá trị

| Test | Thiết kế | Điều cần assert |
| --- | --- | --- |
| **Consumer chậm đọc hết** | Local server streaming body 512KiB; `request(1)` sau delay. | `onComplete`, đúng **524288** bytes, không cancel. |
| **Hủy giữa chừng** | Local server body 8MiB; cancel sau >=64KiB. | Đã đọc >0 và <8MiB, state `cancelled`. |
| **Không cố định chunk boundaries** | Server chia 8KiB nhưng client được coalesce/split. | Đếm theo `remaining()`, không assert số batches. |
| **Không gửi demand ngay** | Chỉ request khi timer/downstream sẵn capacity. | Không có logic `request(Long.MAX_VALUE)` hoặc unbounded queue. |
| **Double subscribe** | Gọi subscribe hai lần trên cùng publisher trong test phụ. | Subscription thứ hai nhận `IllegalStateException` theo Javadoc. |
| **Cancel trước data** | Hủy ngay `onSubscribe`. | App state cancelled, không chờ onComplete. |
| **Server ngắt kết nối** | Đóng socket giữa body. | Báo failed/onError hoặc lỗi phù hợp; không coi partial là success. |
| **Downstream xử lý lỗi** | Processor/worker ném exception có kiểm soát. | Cancel upstream, future lỗi, cleanup. |
| **HTTP 503** | Server trả status 503 với body. | Đọc status, có chính sách consume/cancel error body. |
| **Deadline** | Server treo/consumer không request thêm. | Timeout app dẫn đến cancel/cleanup; không chỉ future exception. |
| **Body quá giới hạn** | Gửi >maxBytes hoặc không có Content-Length. | Hủy và báo byte limit exceeded. |
| **Đóng sớm InputStream** | `try-with-resources` và `break` giữa body. | Connection/resources không bị bỏ quên. |
| **Stress nhiều requests** | Nhiều subscription đồng thời, consumer chậm. | Bound concurrency/queue/heap, không leak threads/connections. |
| **HTTP/2 và TLS** | Server hỗ trợ HTTP/2, proxy hoặc HTTPS ở môi trường test. | Cancellation/reuse theo thực nghiệm, không hard-code HTTP/1.1 behavior. |
| **Memory** | Body lớn hơn heap test. | Streaming không cần lưu nguyên body, peak memory trong budget. |

### Nên đo những metrics nào?

- **Response headers latency**: time to first headers.
- **Body processing latency**: time from subscription đến onComplete/onError/cancel outcome.
- **Bytes received/processed** và **bytes expected** khi có protocol metadata đáng tin.
- **Requested vs delivered Flow items**, average/max bytes per item.
- **Downstream queue depth**, worker utilization, blocked time.
- **Active subscriptions**, cancelled/failed/completed outcomes.
- **Connection reuse/close/reset**, socket error rate.
- **Application heap/RSS** và GC pauses khi tải nặng.
- **Deadline breaches** và số bản ghi/file partial phải cleanup.

Không gộp hết metrics thành “HTTP latency” duy nhất. Khi consumer chậm, thời gian nhận toàn bộ body có thể dài do chính tốc độ xử lý của client, không phải server/network luôn chậm.

## 18. Checklist triển khai an toàn trên Java 11+

1. Dùng **`java.net.http.HttpClient`** và chọn body handler theo kích thước/kiểu dữ liệu.
2. Với body lớn, tránh `ofString`/`ofByteArray` khi chưa có byte limit.
3. Với `ofPublisher()`, dùng chính xác `Flow.Publisher<List<ByteBuffer>>` và **subscribe đúng một lần**.
4. Ở `onSubscribe`, giữ `Flow.Subscription` hợp lệ và cấp demand theo capacity.
5. Hiểu `request(n)` đếm **items/onNext calls**, không đếm bytes; `n <= 0` là lỗi.
6. Chỉ yêu cầu thêm item khi downstream đã xử lý/lưu an toàn batch hiện tại.
7. Không block nặng trong callback; tách xử lý khỏi HTTP client thread và giới hạn queue.
8. Đếm bytes theo **mọi `ByteBuffer.remaining()`**, không dựa vào số lần server write.
9. Kiểm tra `statusCode`, headers, byte limit, checksum và dữ liệu không tin cậy.
10. Khi hủy, gọi **`subscription.cancel()`** hoặc **`InputStream.close()`** tùy handler.
11. Sau cancel, **không chờ `onComplete`**; tự ghi nhận cancelled và cleanup.
12. Khi timeout app, phải cancel resource; chỉ `Future.get(timeout)` là chưa đủ.
13. Không đánh dấu partial file/response là completed khi chưa validate dữ liệu.
14. Xem cancellation là **best-effort**; connection reuse và server stop phụ thuộc protocol.
15. Đặt deadline, size limit, concurrency limit, buffer limit và timeout downstream.
16. Test với server chậm, receiver chậm, hủy sớm, lỗi giữa body, input không có Content-Length và tải concurrent.
17. Dùng Java 11 API thực sự có trong target runtime; không dùng `HttpClient.close()` nếu build còn phải chạy trên Java 11.
18. Đối chiếu memory/network/connection metrics trên HTTP/1.1, HTTP/2 và môi trường sản phẩm trước khi kết luận hiệu năng.

## 19. Tổng kết

Một HTTP response streaming đúng nghĩa cần **điều khiển nhu cầu nhận dữ liệu** và **quyết định rõ cách kết thúc sớm**. Với Java 11:

- `BodyHandlers.ofPublisher()` trả `Publisher<List<ByteBuffer>>` sau headers; application subscribe và gọi `request(n)` để điều tiết.
- `request(1)` chỉ cấp demand cho **một item**, không phải một byte hoặc một HTTP chunk.
- Với receiver chậm, nên cấp lại demand **sau khi downstream xử lý xong**, không gom dữ liệu vào queue vô hạn hoặc block lâu trong callback HTTP.
- `Subscription.cancel()` là **best-effort**, có thể vẫn còn in-flight messages, không buộc `onComplete/onError` chạy và có thể ảnh hưởng HTTP connection reuse.
- Nếu chọn `BodyHandlers.ofInputStream()`, đọc hết hoặc **`close()`** khi dừng giữa chừng.
- Để kết luận thành công, cần **body processed/validated**, không chỉ `sendAsync` đã trả response headers.
- Mã kiểm thử cục bộ đã xác nhận nhận đầy đủ **524.288 byte** với consumer chậm, và nhận một phần rồi cancel trước body mục tiêu **8 MiB**.

### Tài liệu chính thức, phù hợp Java 11 và các JDK hiện đại

- [Oracle Java SE 11 — `HttpResponse.BodyHandlers`: `ofPublisher`, `ofInputStream`, `fromSubscriber`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Oracle Java SE 11 — `HttpResponse.BodySubscribers`: `ofPublisher`, một subscription, resource cleanup/cancel](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
- [Oracle Java SE 11 — `HttpClient`: `send`/`sendAsync` và vòng đời response](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 11 — `HttpRequest.Builder.timeout`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Oracle Java SE 11 — `Flow.Subscription`: `request(n)`, `cancel()`, best-effort cancellation](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [Oracle Java SE 11 — `Flow.Subscriber`: `onSubscribe/onNext/onError/onComplete` lifecycle](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html)
- [Oracle Java SE 11 — `com.sun.net.httpserver.HttpServer` cho server kiểm thử cục bộ](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [OpenJDK JEP 321 — HTTP Client (Standard), JDK 11](https://openjdk.org/jeps/321)
- [Oracle Java SE 25 — `BodySubscribers.ofPublisher` vẫn là API được hỗ trợ](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
