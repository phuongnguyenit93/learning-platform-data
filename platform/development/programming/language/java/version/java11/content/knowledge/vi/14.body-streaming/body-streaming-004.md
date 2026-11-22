# BodySubscriber với Flow.Subscription trong Body streaming — Java 11+

## Mục tiêu

Khi tải một HTTP response lớn, ứng dụng thường **không muốn giữ toàn bộ response body trong một `String` hoặc `byte[]`**. Java HTTP Client chuẩn từ Java 11 hỗ trợ xử lý body theo từng phần qua `HttpResponse.BodySubscriber<T>` và cơ chế điều tiết dữ liệu của `java.util.concurrent.Flow.Subscription`.

Bài này tập trung vào **luồng dữ liệu response nhận về (download/response body)**, không nhầm với `HttpRequest.BodyPublisher` dùng để **phát request body đi (upload)**. Sau bài, bạn có thể:

- Giải thích liên hệ `BodyHandler` → `BodySubscriber<T>` → `Flow.Subscription` → `CompletionStage<T>`.
- Viết đúng chữ ký `onNext(List<ByteBuffer>)` và hiểu vì sao **`request(1)` không phải yêu cầu một byte**.
- Tự xây `BodySubscriber<Long>` đếm số byte đã nhận, xử lý `onSubscribe/onNext/onError/onComplete` và hoàn tất `getBody()`.
- Sử dụng `request(n)` để điều phối demand; hủy bằng `cancel()` khi quá giới hạn, đồng thời tránh làm treo future.
- Hiểu ảnh hưởng của việc không tiêu thụ hết response tới tài nguyên và khả năng dùng lại kết nối.
- Biết khi nào **không nên** tự viết subscriber và nên dùng `BodyHandlers.ofFile/ofInputStream/ofPublisher/fromSubscriber`.

**Phiên bản:** API `HttpResponse.BodySubscriber`, `Flow.Subscription` và các `BodyHandlers` liên quan đã có ở **Java 11** và còn hiện hành trên JDK mới. Ví dụ hoàn chỉnh được biên dịch bằng `javac --release 11`; không sử dụng API thử nghiệm hoặc cấu trúc đã lỗi thời.

## 1. Bức tranh tổng thể: ai phát, ai nhận, ai quyết định tốc độ?

Một response HTTP gồm headers và body. `HttpClient` nhận dữ liệu mạng và cung cấp body cho subscriber theo giao thức `Flow`:

```text
Server HTTP response
    |
    | bytes + network/TLS/HTTP framing
    v
Java HttpClient (publisher nội bộ)
    |
    | onSubscribe(Flow.Subscription s)
    | onNext(List<ByteBuffer> buffers) — chỉ theo demand
    | onComplete() hoặc onError(Throwable)
    v
HttpResponse.BodySubscriber<T>
    |  request(n) / cancel() trên subscription
    |  getBody(): CompletionStage<T>
    v
HttpResponse<T>.body()
```

Tách ba thành phần:

- **`HttpResponse.BodyHandler<T>`** là *factory* chọn cách xử lý body dựa trên `HttpResponse.ResponseInfo` (status, headers, version). Nó trả về một `BodySubscriber<T>` cho response đó.
- **`HttpResponse.BodySubscriber<T>`** là **bên nhận byte của response**, chuyển dữ liệu thành kết quả kiểu `T`: `String`, file, stream, tổng số byte, hash, hoặc kiểu nghiệp vụ tùy thiết kế.
- **`Flow.Subscription`** là quan hệ điều khiển giữa bên phát và bên nhận: subscriber gọi `request(n)` để cho phép có thêm `n` lần `onNext(...)` hoặc `cancel()` để yêu cầu dừng.

Điểm dễ nhầm: HTTP **request** được gửi đi có `BodyPublisher`, còn HTTP **response** được nhận về có `BodySubscriber`. Cả hai dùng `Flow`, nhưng kiểu phần tử khác nhau.

## 2. Chữ ký chính xác của `BodySubscriber<T>`

Theo Java 11:

```java
public static interface HttpResponse.BodySubscriber<T>
        extends Flow.Subscriber<List<ByteBuffer>> {
    CompletionStage<T> getBody();
}
```

Đây là **chữ ký API để đọc hiểu**, không phải đoạn khai báo độc lập cần tự thêm vào dự án.

Các callback mà một subscriber phải triển khai:

| Phương thức | Khi nào được gọi? | Việc cần làm |
| --- | --- | --- |
| `onSubscribe(Flow.Subscription s)` | Trước mọi tín hiệu khác của subscription | Lưu subscription; quyết định demand ban đầu, ví dụ `s.request(1)` |
| `onNext(List<ByteBuffer> item)` | Có dữ liệu theo demand đã cấp | Duyệt **cả danh sách** buffer, tiêu thụ/ghi/đếm số byte, rồi xin thêm nếu còn khả năng xử lý |
| `onError(Throwable error)` | Luồng gặp lỗi không thể khôi phục | Dừng xử lý, báo lỗi cho future/tài nguyên |
| `onComplete()` | Luồng đã kết thúc thành công | Hoàn tất kết quả và dọn tài nguyên |
| `getBody()` | Có thể được gọi bất kỳ lúc nào so với các callback | Trả ngay một `CompletionStage<T>` mô tả kết quả; **không block chờ body trong chính lời gọi này** |

### Vì sao `onNext` nhận `List<ByteBuffer>`?

Đây là điểm **đặc trưng của HTTP response**:

```java
void onNext(List<ByteBuffer> buffers)
```

Một lần `onNext` chứa **một danh sách** `ByteBuffer`, không nhất thiết chỉ có một buffer; số lượng và kích thước buffer do implementation quyết định. Dữ liệu theo thứ tự các danh sách và thứ tự các buffer trong từng danh sách biểu diễn đúng thứ tự body response.

Không viết nhầm:

```java
// SAI cho HttpResponse.BodySubscriber:
// void onNext(ByteBuffer buffer)
```

Chữ ký `Flow.Subscriber<ByteBuffer>` được dùng ở một số tình huống khác, chẳng hạn **request BodyPublisher**; nhưng `HttpResponse.BodySubscriber<T>` chính là `Flow.Subscriber<List<ByteBuffer>>`.

Theo đặc tả Java HTTP Client, các danh sách giao đến subscriber là **không thể sửa đổi**, còn `ByteBuffer` trong đó là **read-only**. Không gọi `put(...)` vào chúng hoặc thêm/xóa phần tử khỏi list. Nếu cần xử lý bytes và giữ dữ liệu lại lâu dài, hãy sao chép vào bộ đệm/nguồn lưu có giới hạn với quyền sở hữu rõ ràng; đừng giả định mọi callback sẽ được gọi trên cùng một thread.

## 3. `Flow.Subscription.request(n)`: demand tính bằng lần `onNext`

Tại `onSubscribe`, subscriber thường cấp demand:

```java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}
```

Đây là đoạn **minh họa bên trong một lớp subscriber**, cần field `Flow.Subscription subscription`. `request(1)` cho phép tối đa **một lần `onNext(List<ByteBuffer>)`** trong phần demand hiện có, **không phải một byte** và **không phải một `ByteBuffer`**.

Ví dụ:

```text
subscription.request(1)
          |
          v
onNext([ByteBuffer 512 B, ByteBuffer 1024 B])
          |
          | xử lý tổng 1536 B
          v
subscription.request(1)  // cho phép danh sách tiếp theo
```

Giới hạn `request(1)` là **mức điều tiết sự kiện gửi danh sách**, không phải quota bytes. Danh sách tiếp theo có thể chứa lượng byte khác, vì vậy để hạn chế dung lượng response phải **đếm từng `buffer.remaining()`**.

Các quy tắc cơ bản từ `Flow.Subscription`:

- `request(n)` với `n > 0` tăng demand. Publisher có thể phát tối đa số tín hiệu `onNext` chưa được đáp ứng; terminal signal có thể đến trước khi dùng hết demand.
- `request(0)` hay `request(n âm)` là yêu cầu không hợp lệ: subscriber sẽ nhận `onError(IllegalArgumentException)` theo hợp đồng.
- `request(Long.MAX_VALUE)` có thể coi như demand gần như **không giới hạn**, không phù hợp nếu bạn chưa có cơ chế giới hạn tài nguyên độc lập.
- `cancel()` yêu cầu dừng theo **best effort**; có thể vẫn xuất hiện một vài tín hiệu sau khi gọi cancel, và **không bắt buộc** có tiếp `onComplete` hoặc `onError`.
- Tín hiệu của mỗi subscription được gọi theo thứ tự tuần tự, nhưng **không bảo đảm cùng một thread**; nếu phối hợp với thread khác, phải xử lý đồng bộ thích hợp.

**Backpressure khác rate limit:** `request(1)` chỉ cho phép một lần giao `List<ByteBuffer>` trước khi xin tiếp; nó không bảo đảm mạng truyền tối đa X byte/giây. Muốn giới hạn bandwidth hoặc xử lý CPU, cần rate limiter, bounded queue, scheduling và mức đồng thời phù hợp.

## 4. Phân biệt `getBody()` và vòng đời bytes

`BodySubscriber<T>.getBody()` trả một `CompletionStage<T>` có thể truy cập bất kỳ lúc nào. **Thời điểm future hoàn thành tùy kiểu body**:

- Với `T = String`, `byte[]`, tổng byte hoặc kết quả tính sau khi duyệt hết: stage thường hoàn thành **sau khi body đã tiêu thụ xong**.
- Với `T = InputStream` hoặc kiểu streaming khác: stage **có thể hoàn thành sớm**, khi stream đã sẵn sàng nhưng bytes vẫn tiếp tục được tiêu thụ bởi người gọi.

Điều đó giải thích vì sao `HttpResponse<InputStream> response = client.send(request, BodyHandlers.ofInputStream())` có thể trả về trước khi body đọc hết. Khi đó **người gọi phải đọc đến EOF hoặc đóng stream** để quản lý tài nguyên.

Trong ví dụ tự tạo ở phần sau, kiểu trả về là `Long` (số byte nhận được), nên `getBody()` trả `CompletableFuture<Long>` chỉ hoàn tất sau `onComplete`, hoặc hoàn tất lỗi nếu `onError`/vượt quota.

### Không block trong `getBody()`

Tránh mã kiểu:

```java
// KHÔNG NÊN: đây là anti-pattern minh họa.
// getBody() không được chặn để đợi kết quả từ callback.
return result.join();
```

Ngoài việc sai kiểu nếu phương thức đòi `CompletionStage<T>`, chờ đồng bộ trong `getBody()` có thể gây deadlock hoặc ngăn event loop nhận dữ liệu để hoàn tất stage.

Cách đúng:

```java
@Override
public CompletionStage<Long> getBody() {
    return result;
}
```

Đây là phương thức bên trong custom subscriber, với `CompletableFuture<Long> result` đã khởi tạo. Nó trả handle ngay, còn callback sẽ hoàn tất future sau.

## 5. Ví dụ chạy được: đếm response byte và hủy khi quá giới hạn

Chương trình tự tạo HTTP server loopback ở `127.0.0.1`, cổng ngẫu nhiên, trả **3 khối mỗi khối 1.024 byte** (tổng **3.072 byte**). Client dùng `BodySubscriber<Long>` tự viết:

- Lần 1: quota 4.096 byte, nhận đủ body và trả `Long = 3072`.
- Lần 2: quota 2.048 byte, callback phát hiện vượt giới hạn, gọi `subscription.cancel()` và hoàn tất future ở trạng thái lỗi.
- Subscriber chủ động gọi `request(1)` **sau khi xử lý xong** mỗi danh sách buffer, nên không đòi hỏi publisher đẩy vô hạn tín hiệu vào code của mình.

Đây là **ví dụ Java 11+ độc lập**; không cần Internet hay thư viện Maven.

**Tệp `BodySubscriberDemo.java`:**

```java
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
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Flow;

public class BodySubscriberDemo {
    private static final class BoundedCounter
            implements HttpResponse.BodySubscriber<Long> {
        private final long maxBytes;
        private final CompletableFuture<Long> result =
                new CompletableFuture<>();
        private Flow.Subscription subscription;
        private long count;

        BoundedCounter(long maxBytes) {
            if (maxBytes < 0) {
                throw new IllegalArgumentException(
                        "maxBytes must be nonnegative");
            }
            this.maxBytes = maxBytes;
        }

        @Override
        public CompletionStage<Long> getBody() {
            return result;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> buffers) {
            for (ByteBuffer buffer : buffers) {
                int length = buffer.remaining();
                if (length > maxBytes - count) {
                    subscription.cancel();
                    result.completeExceptionally(
                            new IOException(
                                    "Response exceeds byte limit"));
                    return;
                }
                count += length;
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
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/data", exchange -> {
            byte[] block = new byte[1024];
            exchange.getResponseHeaders().set(
                    "Content-Type", "application/octet-stream");
            exchange.sendResponseHeaders(
                    200, 3L * block.length);
            try (OutputStream out =
                    exchange.getResponseBody()) {
                for (int i = 0; i < 3; i++) {
                    out.write(block);
                }
            }
        });
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            URI uri = URI.create(
                    "http://127.0.0.1:"
                            + server.getAddress().getPort()
                            + "/data");
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(10))
                    .GET()
                    .build();

            HttpResponse<Long> accepted = client.send(
                    request, info -> new BoundedCounter(4096));
            System.out.println(
                    "status=" + accepted.statusCode());
            System.out.println("bytes=" + accepted.body());

            boolean rejected = false;
            try {
                client.send(
                        request,
                        info -> new BoundedCounter(2048));
            } catch (IOException ex) {
                rejected = true;
            }
            System.out.println(
                    "overLimitRejected=" + rejected);
        } finally {
            server.stop(0);
        }
    }
}
```

### Lệnh biên dịch/chạy

Lưu mã thành `BodySubscriberDemo.java`:

```bash
javac -encoding UTF-8 BodySubscriberDemo.java
java BodySubscriberDemo
```

Khi dùng JDK mới hơn và muốn kiểm tra tính tương thích nguồn/API Java 11:

```bash
javac --release 11 -encoding UTF-8 BodySubscriberDemo.java
java BodySubscriberDemo
```

**Stdout đã kiểm tra bằng việc thực sự biên dịch `--release 11` và chạy:**

```text
status=200
bytes=3072
overLimitRejected=true
```

`HttpServer` là tiện ích HTTP server đi kèm JDK trong module `jdk.httpserver`, dùng để tạo fixture cục bộ; trong môi trường module hạn chế hãy bảo đảm module có sẵn. Hai lượt gọi có thể dùng kết nối khác nhau; **stdout không phải bằng chứng cho connection reuse**.

### Tại sao mã này đáng chú ý?

**(1) Mỗi response có subscriber riêng.** Handler `info -> new BoundedCounter(...)` tạo một subscriber mới cho từng lần gửi. Đừng chia sẻ một `BoundedCounter` đã hoàn tất giữa nhiều response: counter, future và subscription phải thuộc một vòng đời response.

**(2) `onNext` đếm byte mà không cần sao chép.** `buffer.remaining()` trả số byte còn lại trong buffer. Khi chỉ cần đếm dữ liệu đã nhận, không cần `byte[]` chứa toàn body; không cần thay đổi vị trí buffer hoặc ghi vào nó.

**(3) Quota kiểm tra trước khi cộng.** Điều kiện `length > maxBytes - count` tránh cộng vượt ngân sách và cũng tránh overflow không cần thiết. Với `count <= maxBytes` như invariant của class, phép trừ hợp lệ.

**(4) Đếm mọi buffer trong một danh sách.** Không được lấy `buffers.size()` làm số byte; đó là **số `ByteBuffer`**, còn `request(1)` cấp một lần `onNext` gồm cả danh sách.

**(5) `onComplete` đánh dấu thành công.** `result.complete(count)` báo đã nhận và kiểm tra hết body; không nhầm việc nhận HTTP status `200` là đủ để kết luận body hợp lệ.

**(6) Quá quota là lỗi của quá trình nhận body.** HTTP server vẫn có thể trả **status 200**, nhưng client không chấp nhận payload vì vượt giới hạn riêng. Trong phép thử, `client.send(...)` ném `IOException`; biến `rejected` thành `true`. Đây là khác biệt giữa **HTTP status** và **kết quả xử lý body**.

**(7) `cancel()` không tự hoàn tất future.** Code vừa `cancel()` vừa `result.completeExceptionally(...)`. Flow không bắt buộc báo `onError` hoặc `onComplete` sau khi hủy, nên nếu chỉ cancel và chờ callback kết thúc, future của `getBody()` có thể bị treo.

**(8) Connection có thể bị ảnh hưởng.** Khi hủy trước khi đọc hết response, underlying HTTP/1.1 connection có thể phải đóng; với HTTP/2 có thể reset stream tùy triển khai/giao thức. **Không mặc định connection tiếp tục có thể tái sử dụng sau khi cancel**.

**(9) Mẫu tối giản có một trách nhiệm.** Subscriber ở ví dụ tập trung vào quota/count. Trong hệ thống có lifecycle phức tạp, cần trạng thái terminal, idempotent cancellation, bảo vệ callback đến muộn và chính sách lỗi/đóng tài nguyên nhất quán. Không dùng ngay nguyên mẫu tối giản làm nền tảng reactive framework khi chưa kiểm thử các race condition.

## 6. Thứ tự tín hiệu và vòng đời của một subscription

Một lần nhận thành công thường có trình tự:

```text
onSubscribe(s)
    s.request(1)
onNext([buffer(s)])
    xử lý dữ liệu
    s.request(1)
onNext([buffer(s)])
    xử lý dữ liệu
    s.request(1)
...
onComplete()
    result.complete(value)
```

Lỗi có thể đến dưới dạng:

```text
onSubscribe(s)
    s.request(1)
onNext([buffer(s)])
    ...
onError(ex)
    result.completeExceptionally(ex)
```

Hoặc subscriber **chủ động từ chối**:

```text
onSubscribe(s)
    s.request(1)
onNext([buffer(s) vượt giới hạn])
    s.cancel()
    result.completeExceptionally(quotaError)
    // Không chờ onComplete/onError tiếp theo!
```

Theo hợp đồng `Flow.Subscriber`, các callback của **một subscription** được gọi tuần tự, `onSubscribe` đến trước, và `onComplete` hoặc `onError` đánh dấu trạng thái terminal của luồng chưa bị cancel. Tuy nhiên mã ứng dụng không nên giả định:

- Callback chạy trên UI thread, main thread hoặc cùng một worker thread qua mọi lần gọi.
- Mỗi `onNext` chỉ có đúng một `ByteBuffer`.
- `request(1)` ràng buộc kích thước byte hay bảo đảm thời gian nhận tiếp.
- Gọi `cancel()` sẽ tạo ra một `onComplete` hoặc `onError` theo sau.
- Sau `cancel()` chắc chắn không còn callback nào nữa; đây là best effort.
- Có thể gọi lại `getBody().join()` ngay trong callback mà không rủi ro chặn luồng xử lý.

**Lưu ý:** subscriber dùng một `CompletableFuture` đã hoàn thành để biểu diễn trạng thái lỗi/thành công. Khi thiết kế sản phẩm, có thể giữ thêm cờ terminal/cancelled để bỏ qua các tín hiệu đến muộn và không tiếp tục `request` sau hủy.

## 7. So sánh ba lựa chọn: tự viết `BodySubscriber`, dùng adapter hay dùng handler có sẵn

Không phải trường hợp nào cũng cần trực tiếp triển khai `BodySubscriber<T>`.

| Mục đích | Cách ưu tiên | Ghi chú |
| --- | --- | --- |
| Body nhỏ, muốn có String | `BodyHandlers.ofString(UTF_8)` | Đọc cả body vào String, đơn giản nhưng dùng RAM theo dữ liệu |
| Body lớn, lưu thành file | `BodyHandlers.ofFile(path)` | Tránh tự tích trữ mọi byte trong heap |
| Đọc body từng phần kiểu stream | `BodyHandlers.ofInputStream()` | Response có thể sẵn sàng trước EOF; phải đọc/đóng stream |
| Nhận lại `Flow.Publisher<List<ByteBuffer>>` | `BodyHandlers.ofPublisher()` | Subscriber phía ứng dụng subscribe **một lần**, phải drain/cancel |
| Đã có `Flow.Subscriber<List<ByteBuffer>>` | `BodyHandlers.fromSubscriber(...)` | Adapter từ subscriber tự viết, tránh tự triển khai getBody |
| Cần kết quả tùy chỉnh `T` và kiểm soát chính xác demand | Tự triển khai `BodySubscriber<T>` | Cần xử lý stage, Flow, cancel, lỗi và tài nguyên |

### Adapter `fromSubscriber` giúp giảm boilerplate

Java 11 có:

```java
HttpResponse.BodyHandler<Void> handler =
        HttpResponse.BodyHandlers.fromSubscriber(mySubscriber);
```

Đây là đoạn **minh họa** với `mySubscriber` là `Flow.Subscriber<? super List<ByteBuffer>>` đã có. Subscriber nhận toàn bộ tín hiệu body; `HttpResponse.body()` thuộc loại `Void`. Nếu cần lấy kết quả kiểu `T`, có overload nhận `finisher` để tính kết quả sau `onComplete`:

```java
HttpResponse.BodyHandler<Long> handler =
        HttpResponse.BodyHandlers.fromSubscriber(
                myCounterSubscriber, CounterSubscriber::getCount);
```

Đây là đoạn **minh họa cấu trúc**, trong đó `CounterSubscriber` và `getCount` là lớp/phương thức bạn **phải tự định nghĩa**; không phải API JDK có sẵn. Không chép hai đoạn này như chương trình độc lập. Khi subscriber đã dùng cơ chế `Flow` đúng, adapter có thể giúp kết nối với HTTP client thuận tiện hơn.

### `ofPublisher()` để xử lý reactive ở tầng ngoài

`BodyHandlers.ofPublisher()` trả kiểu:

```java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.send(
                request,
                HttpResponse.BodyHandlers.ofPublisher());
```

Đây là đoạn minh họa cần có `client`/`request` và xử lý checked exceptions. Đặc điểm:

- Sau khi headers đã có, `HttpResponse` có thể được trả về **trước khi body được tiêu thụ hết**.
- Bạn phải subscribe **chính xác một lần** vào `response.body()`; subscription tiếp theo không được coi là một lượt tải lại body.
- Bên subscribe phải **request đủ demand** cho đến khi `onComplete/onError`, hoặc `cancel` khi thực sự không dùng tiếp.
- Nếu không subscribe hoặc không request dữ liệu, tài nguyên HTTP exchange có thể còn bị giữ.
- Không ép kết quả trực tiếp thành `String` rồi nghĩ publisher đã tự gom/giải mã toàn bộ nội dung.

**Phân biệt quan trọng:** `HttpRequest.BodyPublisher` (upload) có phần tử `ByteBuffer`; còn publisher trả từ `HttpResponse.BodyHandlers.ofPublisher()` có phần tử `List<ByteBuffer>` (download).

## 8. Bộ đệm, xử lý dữ liệu và giới hạn tài nguyên

### `ByteBuffer` bất biến theo hợp đồng nhận response

ByteBuffer nhận qua `BodySubscriber` là read-only; bạn vẫn đọc được `remaining()`, `get()`, `asReadOnlyBuffer()`. Nếu muốn tính hash, giải mã hoặc ghi file:

- Duyệt mọi buffer trong danh sách `onNext` theo đúng thứ tự.
- Nếu cần đọc một buffer mà không thay đổi `position`, dùng bản sao view `asReadOnlyBuffer()` (view chia sẻ bytes, position/limit riêng).
- Không dùng `buffer.array()` trừ khi đã chắc chắn buffer có array phù hợp; direct/read-only buffer có thể không expose array.
- Khi cần giữ bytes sau callback, quản lý quyền sở hữu/copy rõ ràng, cùng quota và bounded queue.
- Khi decode UTF-8 theo các khối, **không tự `new String(chunk)` độc lập cho mỗi chunk** nếu một code point có thể bị chia giữa hai khối. Dùng `CharsetDecoder` hoặc API streaming đúng cách.

### Tránh công việc block kéo dài trong `onNext`

Một custom subscriber có thể chịu trách nhiệm xử lý nhanh từng chunk, nhưng callback có thể chạy trên executor/luồng do HttpClient quản lý. Nếu mỗi lần `onNext` thực hiện I/O blocking rất lâu, chờ lock ngoài hoặc tính toán CPU nặng, luồng xử lý có thể bị chậm và ảnh hưởng đến request khác.

Một chiến lược nâng cao:

1. Tạo queue **có giới hạn** cho công việc ghi file/xử lý.
2. Sau `onNext`, chuyển dữ liệu an toàn sang queue, không để queue tăng vô hạn.
3. Chỉ gọi `request(1)` sau khi có dung lượng để xử lý thêm, hoặc từ bộ xử lý đã tiêu thụ queue, đồng bộ hóa đúng cách.
4. Khi lỗi, hoàn tất future lỗi, cancel subscription và đóng tài nguyên.
5. Khi EOF, bảo đảm dữ liệu đã ghi/flush hoàn tất **trước khi** hoàn tất kết quả nghiệp vụ.

Phương thức `request(1)` giúp **điều tiết số tín hiệu đang đòi**, nhưng nếu bạn giữ toàn bộ bytes vào một `ArrayList<byte[]>`, bộ nhớ vẫn tăng đến hết body. Backpressure không thay cho quota bytes hoặc chính sách bộ nhớ hữu hạn.

### Dữ liệu quá lớn hoặc không đáng tin

Ngay cả nếu header `Content-Length` khai báo 1 MiB, phía nhận vẫn cần đếm byte **thực nhận**. Header có thể thiếu, không đáng tin với dữ liệu bên ngoài, hoặc luồng bị lỗi. Trong ví dụ, subscriber **không chỉ đọc header** mà áp giới hạn ở từng buffer.

Khi vượt quota:

- Báo một lỗi rõ ràng: giới hạn bao nhiêu byte, loại dữ liệu nào, API nào cần xử lý.
- Gọi `cancel()` để yêu cầu ngừng nhận thêm; **đừng** chỉ ngừng `request` rồi để future mãi pending.
- Hoàn tất kết quả ở trạng thái lỗi; không công bố nội dung tải xuống đã “hoàn tất” khi chỉ nhận một phần.
- Đóng file tạm, xóa phần bị hỏng và ghi log phù hợp, tránh ghi payload nhạy cảm vào log.
- Nếu response body đang là `InputStream`, lựa chọn đọc hết để cố tái dùng kết nối hay đóng sớm phải dựa trên kích thước, bảo mật và ngân sách; **không đọc vô hạn** chỉ để giữ keep-alive.

## 9. Các tình huống lỗi và xử lý thực tế

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Viết `onNext(ByteBuffer)` | Không khớp chữ ký `BodySubscriber<T>` | Dùng `onNext(List<ByteBuffer>)` |
| Nghĩ `request(1)` là 1 byte | Sai ngân sách và pacing | Nó cho phép 1 lần `onNext`, có thể chứa nhiều buffer/byte |
| Nghĩ `request(0)` là “tạm dừng” | Tạo lỗi `IllegalArgumentException` | Không xin thêm khi chưa sẵn sàng; khi sẵn sàng mới `request(n > 0)` |
| Đếm `buffers.size()` để tính bytes | Đếm số `ByteBuffer`, không phải byte | Cộng `buffer.remaining()` cho từng buffer |
| Chỉ hoàn tất future ở `onComplete`, rồi gọi `cancel` khi lỗi | Có thể treo `getBody()` mãi | `completeExceptionally` ngay cả khi cancel |
| Không xử lý `onError` | Future không trả lỗi đúng | Hoàn tất exceptional stage, dọn tài nguyên |
| Lấy `getBody().join()` trong `getBody()` | Deadlock/chặn callback/không đúng kiểu | Trả `CompletionStage<T>` ngay |
| Không `request` ở `onSubscribe` | Có thể không bao giờ có dữ liệu `onNext` | Xin demand hợp lý hoặc chủ đích dừng/cancel |
| Gọi `request(Long.MAX_VALUE)` nhưng tích toàn bộ bytes | OOM với response lớn | Dùng buffer/queue/quota có giới hạn |
| Không kiểm tra status/headers khi cần | Có thể tải body lỗi lớn không cần thiết | Dùng `BodyHandler(ResponseInfo)` để quyết định cách nhận |
| Tự ý sửa `ByteBuffer` được HttpClient đưa vào | Vi phạm read-only contract | Chỉ đọc; copy/view khi cần |
| Dùng `buffer.array()` trên direct/read-only buffer | Có thể ném `UnsupportedOperationException`/`ReadOnlyBufferException` | Duyệt byte bằng API buffer |
| Không subscribe `BodyHandlers.ofPublisher()` | Response có thể giữ tài nguyên chưa được giải phóng | Subscribe một lần và drain/cancel |
| Xem `cancel` là bảo đảm luồng kết thúc ngay | Không đúng: cancel best-effort | Quản lý terminal state/future/tài nguyên độc lập |
| Nghĩ kết nối luôn được tái dùng sau cancel | Có thể bị đóng hoặc reset stream | Đánh đổi giữa bỏ body và giữ connection, đo thực tế |
| Reuse một subscriber cho nhiều response | Future và subscription lẫn nhau | Tạo instance mới cho mỗi response |
| Nhầm upload và download body | Cấu hình sai API | Upload dùng `BodyPublisher`; download dùng `BodySubscriber/BodyHandler` |

## 10. Câu hỏi và bài tập kiểm tra

**Bài 1 — Flow demand.** Subscriber gọi `request(1)`; lần `onNext` đến chứa 3 `ByteBuffer` với `remaining()` lần lượt 100, 300, 500 byte. Tổng byte? **900 byte**. Số lần `onNext` được tiêu thụ? **1**. Muốn có batch tiếp theo phải xin demand mới.

**Bài 2 — Phát hiện vượt quota.** Quota 2.048 byte, trước callback có `count = 2.000`, buffer tiếp theo dài 60 byte. Điều gì xảy ra? **Không cộng thành 2.060 rồi cho qua**; vì `60 > 2048 - 2000` nên cancel và hoàn tất lỗi.

**Bài 3 — Kiểu generic.** Vì sao `BodySubscriber<Long>` có `getBody(): CompletionStage<Long>` nhưng `onNext` vẫn nhận `List<ByteBuffer>`? Vì `Long` mô tả **kiểu kết quả cuối**, còn dòng sự kiện đầu vào của HTTP response luôn là danh sách buffer byte.

**Bài 4 — Tải file.** Nếu chỉ cần tải response lớn xuống file, nên ưu tiên gì thay vì viết custom subscriber? **`BodyHandlers.ofFile(path)`**, kết hợp kiểm soát quota bên client/server nếu nguồn không đáng tin.

**Bài 5 — Hủy.** Tại sao sau `subscription.cancel()` không nên chỉ chờ `onError` mới hoàn tất `CompletableFuture`? Vì cancel best-effort và không bắt buộc có terminal callback. Hãy tự hoàn tất future ở trạng thái lỗi/hủy.

**Bài 6 — Streaming response.** Nếu `BodyHandlers.ofInputStream()` trả response đã có headers nhưng người gọi chưa đọc EOF, body đã hoàn tất chưa? **Chưa chắc**. Caller phải xử lý stream và đóng/đọc đến hết.

**Bài 7 — Nâng cấp code.** Sửa `BoundedCounter` để có cờ terminal rõ ràng, bỏ qua `onNext` đến muộn sau cancel; viết test cho response rỗng, 1 byte, đúng quota và vượt quota. Chứng minh `getBody()` luôn hoàn tất thành công hoặc lỗi.

**Bài 8 — Nhận dữ liệu Unicode.** Thiết kế subscriber tính SHA-256 hoặc giải mã UTF-8 với `CharsetDecoder` từ nhiều `List<ByteBuffer>`. Tại sao không giải mã từng buffer thành chuỗi độc lập? Vì ký tự UTF-8 có thể nằm trên ranh giới chunk.

### Checklist khi viết `BodySubscriber` mới

1. Đã dùng đúng `Flow.Subscriber<List<ByteBuffer>>`, không nhầm với request publisher?
2. `getBody()` trả `CompletionStage<T>` ngay cả khi body chưa nhận xong?
3. `onSubscribe` lưu subscription và cấp demand dương phù hợp?
4. `onNext` xử lý **mọi ByteBuffer** theo thứ tự và chỉ xin thêm khi đã sẵn sàng?
5. Có quota byte, giới hạn queue/concurrency và không giữ toàn body khi không cần?
6. `onError`, `onComplete` và nhánh cancel có hoàn tất future đúng, không treo?
7. Có dọn tài nguyên, bảo vệ callback đến muộn và xử lý race condition khi nâng cấp lên production?
8. Có xử lý status, lỗi HTTP, timeout và connection reuse theo tình huống?
9. Có ưu tiên handler/subscriber sẵn có khi không cần tùy biến?
10. Ví dụ và code dùng API **còn hiện hành**, tương thích JDK tối thiểu của sản phẩm?

## Tài liệu chính thức

- [Oracle Java SE 11 — HttpResponse.BodySubscriber](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html): `Flow.Subscriber<List<ByteBuffer>>`, `getBody()`, read-only buffers, tài nguyên và cancellation.
- [Oracle Java SE 25 — HttpResponse.BodySubscriber](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html): hợp đồng API tiếp tục áp dụng trong JDK hiện đại.
- [Oracle Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofFile`, `ofInputStream`, `ofPublisher`, `fromSubscriber`.
- [Oracle Java SE 25 — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): các subscriber tiêu chuẩn và adapter.
- [Oracle Java SE 11 — Flow.Subscription](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): `request(n)`, nhu cầu theo phần tử, `cancel()` best-effort.
- [Oracle Java SE 25 — Flow.Subscriber](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html): thứ tự tín hiệu `onSubscribe/onNext/onError/onComplete`.
- [OpenJDK JEP 321 — HTTP Client (Standard)](https://openjdk.org/jeps/321): Java HTTP Client chính thức từ Java 11.

**Kết luận:** `BodySubscriber<T>` xác định cách **nhận** một response body thành giá trị kiểu `T`, còn `Flow.Subscription` kiểm soát **demand và cancellation**. Cấp `request(1)` điều tiết **một lần giao `List<ByteBuffer>`**, không phải một byte hay một giới hạn tốc độ; muốn xử lý body lớn an toàn cần cả quota bytes, giới hạn tài nguyên, hoàn tất future trên mọi nhánh và quản lý kết nối đúng cách.