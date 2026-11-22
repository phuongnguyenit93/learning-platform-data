# Cancellation, interruption và khả năng phản hồi của transport trong HTTP bất đồng bộ (Java 11)

## 1. Mục tiêu bài học

Với `java.net.http.HttpClient`, ứng dụng Java 11 có thể gửi HTTP request bằng `sendAsync(...)` và nhận ngay một `CompletableFuture<HttpResponse<T>>`. Tuy nhiên, việc **người dùng hủy thao tác**, **future chuyển sang trạng thái cancelled**, **thread đang chờ bị interrupt**, **transport ngừng gửi/nhận**, và **server thực sự ngừng xử lý** là những sự kiện **không tương đương**.

Ví dụ: người dùng đóng màn hình khi một request tạo đơn hàng đang gửi. Ứng dụng có thể ngừng chờ response trong tích tắc, nhưng request đã đến server và đơn hàng vẫn được tạo. Nếu sau đó retry một cách vô điều kiện, nghiệp vụ có thể bị thực hiện hai lần.

Bài này giúp bạn:

- Phân biệt hủy `CompletableFuture` với dừng HTTP exchange và side effect phía server.
- Hiểu Java 11 hỗ trợ và **không bảo đảm** điều gì khi `cancel(...)` được gọi.
- Phân biệt `Thread.interrupt()`, `InterruptedException`, `CompletableFuture.get()/join()` và `HttpClient.send()`.
- Chọn `HttpRequest.timeout(...)`, `connectTimeout(...)`, `orTimeout(...)`, deadline nghiệp vụ và cancellation đúng mục đích.
- Hiểu hành vi transport HTTP/1.1, HTTP/2 trên JDK mới mà không áp đặt ngược bảo đảm đó cho Java 11.
- Thiết kế HTTP client có khả năng phản hồi tốt với tải, body streaming, cancellation, giới hạn concurrency và shutdown.
- Thực hành mã **Java 11 chạy độc lập**, cùng các trích đoạn tích hợp HTTP thực có giới hạn được nêu rõ.

Các API được giới thiệu vẫn hữu ích trên JDK hiện đại; khác biệt do phiên bản JDK được tách rõ. Không xem chi tiết implementation hoặc một lần test thành bảo đảm giao thức.

## 2. Bốn tầng trạng thái phải tách riêng

| Tầng | Thao tác/sự kiện | Bạn thực sự biết gì? | Điều **không được suy ra** |
| --- | --- | --- | --- |
| **Future ứng dụng** | `future.cancel(true)` | Future có thể chuyển sang completed exceptionally với `CancellationException` | Mạng đã dừng; server chưa nhận request |
| **Thread chờ** | `thread.interrupt()`, `InterruptedException` | Thread được yêu cầu ngắt; thao tác chờ có thể kết thúc bằng exception | HTTP exchange chắc chắn đã bị hủy |
| **HTTP transport** | Cố hủy exchange, đóng kết nối, reset HTTP/2 stream | Client có thể cố giải phóng tài nguyên theo triển khai/JDK | Không có byte nào đã rời client; tài nguyên giải phóng tức thì |
| **Nghiệp vụ server** | Nhận và xử lý POST/PUT/GET | Phụ thuộc trạng thái thực trên server | Việc cancel ở client hoàn tác transaction đã commit |

Một future bị hủy chỉ xác định **cách caller nhận kết quả trong tương lai**. Transport và server có thể đang ở trạng thái khác. Đây là lý do cần idempotency, tra cứu trạng thái tác vụ và thiết kế dừng có kiểm soát cho hoạt động có side effect.

### Sơ đồ thời gian của một tình huống thực tế

```text
T0 client gọi sendAsync(POST tạo đơn)
T1 byte request đi qua mạng
T2 server bắt đầu thực hiện nghiệp vụ
T3 người dùng nhấn "Hủy"
T4 client gọi future.cancel(true)
T5 future báo CancellationException cho người chờ
T6 server có thể vẫn commit nghiệp vụ
T7 việc giải phóng kết nối có thể diễn ra sau đó
```

Đây là **một kịch bản có thể xảy ra**, không phải thứ tự bắt buộc của mọi request. Không dùng kết quả `isCancelled()` để kết luận server đã bỏ giao dịch.

## 3. Java 11 khác JDK hiện đại ở mức bảo đảm cancellation

### 3.1. Hợp đồng `CompletableFuture` nói gì?

Trên Java 11, `CompletableFuture.cancel(boolean mayInterruptIfRunning)` làm future hoàn thành **bằng hủy**, tức một dạng exceptional completion. Người chờ future có thể nhận `CancellationException` (hoặc exception bọc nó ở dependent stage).

Theo `CompletableFuture` thông thường, tham số `mayInterruptIfRunning` **không tự điều khiển thread đang làm việc** vì `CompletableFuture` không trực tiếp sở hữu hoạt động nền. Hai lời gọi `cancel(true)` và `cancel(false)` **không phải** hai cơ chế chắc chắn ngắt/không ngắt I/O, trừ khi implementation cụ thể cung cấp hành vi bổ sung.

Hệ quả:

- `future.isCancelled()` mô tả trạng thái future, **không** chứng minh network đã dừng.
- `future.isDone()` có thể `true` vì thành công, thất bại, timeout hoặc cancel; **không** đồng nghĩa thành công.
- Dependent stage như `thenApply(...)` có thể hoàn thành lỗi theo upstream, nhưng hủy một stage **không tự động bảo đảm** hủy exchange ở stage khác.
- Khi một task đã hoàn tất, `cancel(...)` không biến một response thành canceled.

### 3.2. Javadoc `java.net.http` Java SE 11

Tài liệu package `java.net.http` của **Java 11** nói rằng gọi `cancel` trên `CompletableFuture` do HTTP API trả về **có thể không ngắt thao tác nền**, dù vẫn hữu ích để làm các stage phụ thuộc chưa hoàn thành kết thúc ở trạng thái ngoại lệ.

Vì vậy, nếu **mã và runtime là JDK 11**, hãy coi `sendAsync(...).cancel(true)` là cơ chế **hủy nhu cầu nhận kết quả ở phía ứng dụng**, **không phải bảo đảm transport sẽ bị dừng**. Một số bản phát hành có thể chứa bản vá triển khai, nhưng không thiết kế hợp đồng nghiệp vụ dựa vào một hành vi không được tài liệu Java SE 11 bảo đảm.

### 3.3. JDK 16+/17/21/25: nỗ lực hủy exchange tốt hơn nhưng vẫn best effort

Javadoc của các JDK mới hơn mô tả **implementation `HttpClient` mặc định** trả future có khả năng hủy HTTP exchange. Trên future có thể hủy và chưa hoàn tất, `cancel(true)` **cố gắng** hủy exchange để giải phóng tài nguyên nhanh hơn:

- Hủy **không bảo đảm được áp dụng ở thời điểm chính xác**.
- Request **vẫn có thể đã được gửi**, vì công việc có thể chạy bất đồng bộ trên thread khác.
- Tài nguyên nền có thể chỉ được giải phóng **bất đồng bộ**.
- Với **HTTP/1.1**, nỗ lực hủy có thể khiến kết nối nền bị **đóng đột ngột**.
- Với **HTTP/2**, nỗ lực hủy có thể làm **reset stream**; một số tình huống khác (đặc biệt với interruption của `send()`) có thể ảnh hưởng cả kết nối.

**Không diễn giải “cancelable” thành “server chắc chắn chưa xử lý”.** Các chi tiết transport là **best effort của default JDK HttpClient**, không phải giao dịch hủy từ xa với bảo đảm toàn cục. Với client khác hoặc implementation khác, cần xem tài liệu riêng.

### 3.4. Bảng chọn cách suy luận theo JDK

| Tình huống | Java 11 | JDK hiện đại có ghi nhận cancellable HTTP future |
| --- | --- | --- |
| Gọi `cancel(true)` trên future chưa hoàn tất | Future có thể chuyển cancelled; không bảo đảm ngắt I/O | Future chuyển cancelled; **có nỗ lực** hủy HTTP exchange đối với default implementation |
| `isCancelled() == true` | Chỉ chứng minh future cancelled | Vẫn **không** chứng minh server chưa xử lý |
| Bắt `InterruptedException` khi `send()` | Thread chờ bị interrupt; Java 11 không nêu cam kết cụ thể việc cancel transport ở mô tả `send` | Default JDK client cố hủy exchange theo Javadoc mới, nhưng không bảo đảm ngay |
| `sendAsync` đã trả `HttpResponse<InputStream>` | Future có thể đã hoàn thành dù body stream chưa đọc | Tương tự; cần quản lý trực tiếp body stream |
| Chỉ muốn giới hạn thời gian chờ kết quả | Dùng timeout/deadline | Dùng timeout/deadline, cộng cancellation/cleanup dựa vào JDK |

Bảng nhằm **tránh áp đặt hành vi của JDK mới lên Java 11**, đồng thời giữ kiến thức có giá trị cho hệ thống nâng cấp hiện nay.

## 4. `Thread.interrupt()` khác `CompletableFuture.cancel()`

### 4.1. Interrupt là tín hiệu cho thread, không phải cho HTTP server

`Thread.interrupt()` đặt trạng thái interrupt của thread. Nhiều thao tác chờ hỗ trợ interrupt (chẳng hạn `Thread.sleep`, `Object.wait`, `Future.get`) sẽ ném `InterruptedException`. Nhưng thread chỉ dừng công việc một cách có kiểm soát nếu code đang chờ hoặc chủ động kiểm tra/cộng tác với tín hiệu này.

Thông thường, khi một phương thức chờ ném `InterruptedException`, **cờ interrupt bị xóa**. Nếu không thể truyền exception lên caller, nên khôi phục nó:

```java
try {
    Thread.sleep(1000);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Ghi nhận yêu cầu dừng hoặc chuyển tiếp lên tầng điều phối.
}
```

Đây là **trích đoạn**. Không bắt `InterruptedException` rồi bỏ qua và tiếp tục làm việc lâu dài như không có gì xảy ra. Khi tầng trên cũng dùng interrupt để dừng, việc nuốt interrupt có thể làm chương trình tắt chậm hoặc treo.

### 4.2. `send()` đồng bộ và `sendAsync()` bất đồng bộ

```java
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
```

`send()` là lời gọi **đồng bộ** và khai báo `throws IOException, InterruptedException`. Nếu thread chờ bị ngắt, caller có thể nhận `InterruptedException`. Với default client JDK mới, tài liệu nói cố gắng hủy exchange, nhưng có thể request đã tới server; trên Java 11 không mặc định suy ra bảo đảm này.

Ngược lại:

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request, HttpResponse.BodyHandlers.ofString());
```

`sendAsync()` trở về với future, không bắt caller phải chờ. Interrupt **thread gọi `sendAsync` sau khi nó đã trả về** không phải cách đáng tin để hủy một exchange do các thread khác đang tiến hành. Muốn biểu diễn yêu cầu hủy, quản lý future/cancellation token và tài nguyên HTTP theo JDK mục tiêu.

### 4.3. `get()` và `join()` có hành vi chờ khác nhau

| Cách chờ | Khi future bị hủy | Khi **thread chờ** bị interrupt |
| --- | --- | --- |
| `future.get()` | Có thể ném `CancellationException` | Ném `InterruptedException` khi đang chờ; caller phải xử lý |
| `future.get(timeout, unit)` | Có thể ném `CancellationException` | Có thể ném `InterruptedException`; nếu quá hạn chờ, ném `TimeoutException` |
| `future.join()` | Ném `CancellationException` với future bị hủy | **Không** khai báo `InterruptedException`; không xem việc interrupt thread là hủy future |
| `future.orTimeout(...)` | Nếu future đã cancel, timeout không làm nó thành công trở lại | Đặt cơ chế hoàn thành future khi hết thời hạn; **không** tự chứng minh transport đã dừng |

**Rất quan trọng:** `get(timeout, unit)` chỉ giới hạn **thời gian chờ của lời gọi get**. Khi nó ném `TimeoutException`, underlying future **không tự động bị cancel**. Cần chính sách tiếp theo: tiếp tục đợi, hủy future, dừng công việc nghiệp vụ hoặc thông báo caller.

## 5. `orTimeout`, `completeOnTimeout` và HTTP request timeout

Trong Java 11 có nhiều cơ chế deadline nhưng không thay thế cho nhau:

| API | Tác động chính | Khi hữu ích |
| --- | --- | --- |
| `HttpClient.Builder.connectTimeout(Duration)` | Thời hạn thiết lập kết nối mới (theo hợp đồng HTTP client) | Tránh kẹt quá lâu ở bước kết nối |
| `HttpRequest.Builder.timeout(Duration)` | Thời hạn của HTTP request theo Javadoc `HttpRequest`; có thể ném `HttpTimeoutException` | Giới hạn thời gian request theo chính sách ứng dụng |
| `future.get(n, TimeUnit.SECONDS)` | Giới hạn thời gian **caller chờ kết quả**, không làm future hoàn thành lỗi | Caller có deadline chờ riêng |
| `future.orTimeout(n, unit)` | **Chính future đó** hoàn thành đặc biệt với `TimeoutException` nếu chưa kết thúc sau deadline | Biểu diễn timeout trong chuỗi `CompletableFuture` |
| `future.completeOnTimeout(value, n, unit)` | **Chính future đó** hoàn thành bình thường bằng giá trị dự phòng nếu hết hạn | Chỉ hợp lý khi fallback không làm người dùng hiểu nhầm thao tác gốc đã thành công |
| `future.cancel(true)` | Cố hủy future; việc tác động transport khác nhau theo JDK | Người dùng bỏ tác vụ, workflow không còn cần kết quả |

**`orTimeout` không phải lời gọi HTTP transport cancellation riêng.** Trên Java 11, việc future hoàn thành vì timeout cũng **không bảo đảm** HTTP I/O nền đã dừng. Vì vậy, không dùng mỗi `orTimeout` để kiểm soát số socket hoặc request đang còn hoạt động.

Ví dụ **trích đoạn** dành cho một future mà ứng dụng tạo:

```java
CompletableFuture<String> result = new CompletableFuture<>();
result.orTimeout(3, TimeUnit.SECONDS);

// Khi chưa hoàn thành sau 3 giây, result kết thúc bằng TimeoutException.
// Việc này không tự hủy một network request bất kỳ.
```

Cần import `java.util.concurrent.CompletableFuture` và `java.util.concurrent.TimeUnit`. `orTimeout` **trả về cùng future**, không tạo một future “timeout wrapper” độc lập. Nếu gọi trên future của `sendAsync`, nó có thể đổi trạng thái chính future đó và các dependent stage.

**Không dùng `completeOnTimeout("OK", ...)` để giả định server đã xử lý thành công:** nếu task thực vẫn chạy, một kết quả giả thành công có thể gây sai lệch nghiệp vụ.

## 6. Mã Java 11 chạy độc lập: kiểm tra cancellation và interruption không phụ thuộc mạng

Chương trình sau minh họa **trạng thái `CompletableFuture`** và **interruption của thread chờ** bằng các thao tác chuẩn Java 11. Nó **không gọi HTTP** và **không mô phỏng khả năng ngắt transport**; đó chính là ranh giới cần nhớ khi đọc output.

Tạo file **`FutureCancellation11Demo.java`**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;

public class FutureCancellation11Demo {
    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<Integer> dependent =
                source.thenApply(String::length);

        boolean cancelled = source.cancel(true);

        System.out.println("cancel returned: " + cancelled);
        System.out.println("source cancelled: " + source.isCancelled());
        System.out.println("source done: " + source.isDone());
        System.out.println("dependent exceptional: "
                + dependent.isCompletedExceptionally());

        try {
            source.join();
        } catch (CancellationException ex) {
            System.out.println("source join: CancellationException");
        }

        try {
            dependent.join();
        } catch (CompletionException ex) {
            System.out.println("dependent cause: "
                    + ex.getCause().getClass().getSimpleName());
        }

        CompletableFuture<String> timed = new CompletableFuture<>();
        CompletableFuture<String> returned =
                timed.orTimeout(5, TimeUnit.SECONDS);

        System.out.println("orTimeout same future: " + (timed == returned));
        timed.complete("ready");
        System.out.println("completed value: " + timed.join());

        // Chỉ minh họa interrupt tại một thao tác chờ có thể interrupt.
        Thread.currentThread().interrupt();
        try {
            Thread.sleep(1);
        } catch (InterruptedException ex) {
            System.out.println("sleep interrupted: yes");
            Thread.currentThread().interrupt();
        }
        System.out.println("interrupt restored: "
                + Thread.currentThread().isInterrupted());
        Thread.interrupted(); // Xóa flag thử nghiệm trước khi kết thúc.
    }
}
```

Biên dịch/chạy bằng **JDK 11** (hoặc JDK mới hơn có `--release 11`):

```bash
javac --release 11 -encoding UTF-8 FutureCancellation11Demo.java
java FutureCancellation11Demo
```

Đầu ra dự kiến **xác định, không phụ thuộc network**:

```text
cancel returned: true
source cancelled: true
source done: true
dependent exceptional: true
source join: CancellationException
dependent cause: CancellationException
orTimeout same future: true
completed value: ready
sleep interrupted: yes
interrupt restored: true
```

Giải thích:

1. `source` chưa hoàn thành khi gọi `cancel(true)`, nên hủy thành công và `isCancelled()/isDone()` đều thành `true`.
2. `dependent` cần kết quả bình thường của `source`, nên cũng hoàn thành đặc biệt; `join()` của nó ném `CompletionException` có cause là `CancellationException`.
3. `source.join()` ném trực tiếp `CancellationException`.
4. `orTimeout` trả về **cùng** đối tượng `timed`. Code hoàn thành `timed` ngay với `"ready"` trước deadline 5 giây, nên không có timeout thật.
5. Sau khi tự đặt cờ interrupt, `Thread.sleep` lập tức ném `InterruptedException`; catch khôi phục cờ, rồi dòng sau in `true`. Dòng `Thread.interrupted()` cuối chỉ dọn trạng thái demo.
6. **Không có kết luận transport nào** từ ví dụ này vì chương trình không tạo HTTP exchange. Muốn đánh giá hủy network thật cần thử với server có thể ghi nhận khi nhận request và khi client ngắt kết nối.

## 7. Trích đoạn Java 11 tích hợp `sendAsync` với cancel và deadline

Ví dụ sau là **trích đoạn bên trong một method**, cần `client` là `HttpClient` đã tạo, `uri` là endpoint hợp lệ, và xử lý vòng đời của client ở cấp ứng dụng:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> exchange =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString());

CompletableFuture<Integer> status =
        exchange.thenApply(HttpResponse::statusCode);

// Người dùng hoặc workflow không còn cần request:
boolean accepted = exchange.cancel(true);

// accepted/isCancelled chỉ báo trạng thái future.
// Java 11 KHÔNG bảo đảm transport đã dừng và
// không chứng minh server chưa xử lý request.
```

Cần import `java.net.http.HttpRequest`, `java.net.http.HttpResponse`, `java.net.http.HttpClient`, `java.time.Duration` và `java.util.concurrent.CompletableFuture`; `status` là dependent future (trong trường hợp bị hủy có thể kết thúc lỗi). Không lấy đoạn này làm chương trình mạng chạy độc lập vì nó yêu cầu server thật.

**Tại sao giữ `exchange` riêng?** Nếu chỉ lưu `status` và gọi `status.cancel(true)`, bạn đang thao tác với **dependent future**, không có bảo đảm hủy upstream exchange. Khi cần yêu cầu hủy nguyên request, giữ reference tới future trả trực tiếp từ `sendAsync`. Dù thế, trên Java 11 vẫn không có cam kết dừng I/O.

### 7.1. Đừng áp dụng `cancel` máy móc cho GET/POST

Cancel chỉ có ý nghĩa ở tầng tài nguyên/caller; yêu cầu nghiệp vụ còn phải xét HTTP method và idempotency:

- **GET** thường được thiết kế không tạo side effect nghiệp vụ, nhưng có thể đã được server xử lý, ghi audit/log, tiêu thụ tài nguyên hoặc kích hoạt hành vi ngoài ý muốn nếu endpoint thiết kế kém.
- **POST** tạo đơn/thanh toán có thể đã commit ngay cả khi future bị hủy; retry cần **idempotency key** và hỗ trợ chống xử lý trùng ở server.
- **PUT/DELETE** có ngữ nghĩa idempotent theo HTTP khi được triển khai đúng, nhưng không vì thế mà hủy chắc chắn được server; cần hiểu chính xác hợp đồng endpoint, điều kiện cập nhật và tính đúng đắn.
- Một request có thể đã gửi một phần request body; cancellation không bảo đảm body chưa đến server.

Tối ưu hóa transport **không thay thế** chính sách retry, deduplication và truy vấn trạng thái nghiệp vụ ở hệ thống đích.

## 8. `send()` và xử lý `InterruptedException` đúng

Nếu cần dùng `send()` đồng bộ, đừng biến interrupt thành lỗi bị nuốt:

```java
static HttpResponse<String> fetch(
        HttpClient client, HttpRequest request)
        throws IOException, InterruptedException {
    try {
        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw ex;
    }
}
```

Đây là **phương thức minh họa**, cần import `java.io.IOException`, `java.net.http.HttpClient`, `HttpRequest` và `HttpResponse`. Cách này vừa khôi phục trạng thái interrupt, vừa chuyển quyết định dừng lên tầng gọi. Caller có thể chọn dừng workflow hoặc ghi nhận cancellation.

Lưu ý:

- `InterruptedException` chứng minh **thread gọi API bị interrupt**, không bảo đảm server chưa xử lý request.
- Với Java 11, Javadoc `send` chỉ khai báo interruption; không tự thêm bảo đảm transport của các JDK mới.
- Với các JDK hiện đại, default client **cố** hủy exchange khi `send()` bị interrupt, nhưng không cam kết thời điểm hay hiệu lực tuyệt đối.
- Không retry ngay một POST sau `InterruptedException` nếu không biết tình trạng transaction phía server.

### Nếu chỉ interrupt một thread đang `get()` future?

```java
try {
    HttpResponse<String> response =
            exchange.get(2, TimeUnit.SECONDS);
    process(response);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Quyết định chính sách đối với exchange đang chạy riêng.
} catch (TimeoutException ex) {
    // Chỉ quá hạn chờ get: exchange chưa chắc đã bị cancel.
}
```

Đây là **trích đoạn** cần xử lý thêm `ExecutionException` và các ngoại lệ liên quan, import `TimeUnit`, `TimeoutException`. `process(response)` là hàm nghiệp vụ do ứng dụng định nghĩa. Không dùng nguyên trích đoạn để biên dịch độc lập.

Nếu cần yêu cầu hủy exchange sau `get` timeout/interrupt, code có thể gọi `exchange.cancel(true)`, nhưng **tác dụng transport phụ thuộc JDK**. Việc gián đoạn thread chờ future không tự động có nghĩa HTTP client phải ngừng công việc ở thread nền.

## 9. Response body streaming: future hoàn thành chưa chắc body đã xử lý xong

`HttpClient.sendAsync` có thể dùng nhiều `BodyHandler<T>`:

| Body handler | `T` | Ý nghĩa liên quan cancellation |
| --- | --- | --- |
| `BodyHandlers.ofString()` | `String` | Body được thu thập thành chuỗi; phải cân nhắc memory cho response lớn |
| `BodyHandlers.ofByteArray()` | `byte[]` | Body thu thập thành mảng byte; giới hạn kích thước |
| `BodyHandlers.ofInputStream()` | `InputStream` | Future có thể hoàn thành khi stream đã được cung cấp, **trước khi caller đọc hết body** |
| `BodyHandlers.ofLines()` | `Stream<String>` | Caller phải tiêu thụ/đóng stream, và future có thể hoàn thành trước khi stream được đọc hết |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Caller subscribe, `request(n)`/`cancel()` và quản lý backpressure theo Flow |

**Trường hợp dễ nhầm:** một `CompletableFuture<HttpResponse<InputStream>>` đã `isDone() == true` vì `HttpResponse` và stream đã có. Gọi `future.cancel(true)` lúc đó thường trả `false` vì future đã hoàn tất. Điều này **không** có nghĩa body đã tải xong hoặc không còn I/O. Muốn ngừng đọc body, **đóng `InputStream`**:

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] buffer = new byte[8192];
    int count;
    while ((count = body.read(buffer)) != -1) {
        if (shouldStop()) {
            break;
        }
        consume(buffer, count);
    }
}
```

Đây là **trích đoạn**, cần import `InputStream`, `IOException`, `HttpResponse`; `shouldStop()` và `consume(...)` là hàm nghiệp vụ chưa định nghĩa, không phải chương trình chạy độc lập. Khi vòng lặp kết thúc sớm, `try-with-resources` đóng stream. Tùy giao thức và tình trạng exchange, việc đóng sớm có thể ảnh hưởng khả năng tái sử dụng kết nối. Không giữ body stream treo để chờ future được cancel.

Với custom `Flow.Subscriber` của response body, nếu không thể tiếp tục, gọi `Flow.Subscription.cancel()` và giải phóng tài nguyên do ứng dụng sở hữu. `cancel()` là **best effort**: publisher có thể còn gửi một số tín hiệu đang trên đường và không bắt buộc phát `onComplete` hoặc `onError` sau cancel. Nếu có thể xử lý hết dữ liệu an toàn, tiếp tục cấp demand và đọc đến terminal để giải phóng tài nguyên có kiểm soát.

## 10. Khả năng phản hồi của HTTP transport và ứng dụng

“Có cancel” không đồng nghĩa “ứng dụng phản hồi nhanh”. Một service HTTP bất đồng bộ có thể vẫn bị nghẽn vì queue, backpressure, callback chậm, body lớn hoặc thiếu timeout.

### 10.1. Không block luồng xử lý phản hồi

`sendAsync` thường trả future ngay, nhưng callback sau đó có thể chạy trên thread hoàn tất future hoặc default executor, phụ thuộc cách dùng `CompletionStage`:

```java
exchange.thenApply(HttpResponse::body)
        .thenApply(this::parseLargeDocument);
```

Đây là **trích đoạn trong một lớp có phương thức `parseLargeDocument`**, không chạy độc lập. Nếu parse lớn gây block lâu, có thể trì hoãn callback khác, tăng latency và gây áp lực CPU. Với tác vụ tốn CPU, chọn `thenApplyAsync` cùng một `Executor` được quản lý theo năng lực hệ thống.

```java
CompletableFuture<Result> parsed =
        exchange.thenApply(HttpResponse::body)
                .thenApplyAsync(this::parseLargeDocument, cpuExecutor);
```

Đây là **trích đoạn cần định nghĩa `Result`, `parseLargeDocument` và `cpuExecutor`**. Cần đặt giới hạn concurrency/queue theo tải thực, không tạo thread mới vô hạn. Dùng executor chỉ định cũng không tự sửa được tài nguyên HTTP I/O còn chạy sau khi future bị hủy.

### 10.2. Dùng các deadline ở đúng tầng

Thiết kế thường có:

1. **Connect timeout**: thời hạn thiết lập kết nối mới.
2. **Request timeout**: giới hạn thời gian thực hiện HTTP request theo API.
3. **Business deadline**: caller không chờ quá mức có thể chấp nhận.
4. **Cancellation policy**: dừng nhận kết quả, hủy transport nếu implementation hỗ trợ, hoặc đóng body stream đã cấp.
5. **Shutdown deadline**: khi ứng dụng tắt, chờ một khoảng có giới hạn rồi áp dụng chính sách dừng còn lại.

Không đặt cùng một con số thời gian cho mọi tầng mà không phân tích hành vi thực. Nếu operation có streaming body kéo dài, phải kiểm tra cách timeout tương tác với response body trong bản JDK cụ thể; không suy ra `orTimeout(5s)` luôn chặn mọi byte I/O sau 5 giây.

### 10.3. Phân biệt hủy kết quả với giải phóng tài nguyên

Khi người dùng rời trang, nhiều hệ thống chỉ cần **không cập nhật UI bằng kết quả cũ**. Điều này có thể giải quyết bằng **generation/version token** trên state ứng dụng mà không giả vờ transport đã hủy.

Nếu cần giảm lưu lượng và giải phóng kết nối, hãy:

- Theo dõi future gốc và trạng thái request.
- Áp dụng cancel theo JDK mục tiêu, sau đó kiểm tra resource metrics.
- Với streaming body, đóng/cancel nguồn dữ liệu.
- Giới hạn số request đang gửi và thời gian chạy.
- Dùng server-side cancellation protocol nếu nghiệp vụ thực sự cần dừng job từ xa; HTTP future cancellation không phải protocol hủy job.

Kết quả UI “canceled” có thể được hiển thị nhanh, trong khi cleanup transport diễn ra trễ hơn. Đây là trạng thái bình thường nếu hệ thống vận hành đúng và có giới hạn tài nguyên.

## 11. Quản lý retry, idempotency và tính đúng đắn

Nếu một request bị ngắt trong khi server xử lý, client có thể nhận một trong các tình huống:

| Quan sát ở client | Điều có thể đã xảy ra ở server | Quyết định an toàn |
| --- | --- | --- |
| Future canceled | Server chưa nhận, đã nhận một phần hoặc đã commit | Không suy đoán; dùng idempotency/truy vấn trạng thái |
| `TimeoutException` từ `get(timeout)` | Tác vụ mạng có thể vẫn chạy, server có thể vẫn xử lý | Đặt deadline + quyết định cancel riêng |
| `HttpTimeoutException` | Yêu cầu HTTP không hoàn thành trong thời hạn | Vẫn không suy ra side effect chưa xảy ra |
| `InterruptedException` trên `send()` | Thời gian ngắt không đồng bộ với commit server | Không retry mù quáng |
| `IOException` (connection reset) | Server có thể đã xử lý rồi mất đường trả response | Retry theo chính sách và idempotency |
| HTTP status 500 | Server trả lỗi; có thể đã thay đổi một phần trạng thái | Đọc hợp đồng API và logic nghiệp vụ |

Với hoạt động có side effect (đơn hàng, thanh toán, tạo resource), giải pháp thường cần:

- **Idempotency key** ổn định cho một business operation qua các attempt.
- **Server deduplication** hoặc transaction semantics có thể kiểm chứng; một header `Idempotency-Key` không có tác dụng nếu server không hỗ trợ.
- **Status lookup** theo operation ID để phân giải kết quả không chắc chắn.
- Retry có giới hạn, backoff và tổng deadline; tránh retry mọi lỗi.
- Dữ liệu request body phát lại phải ổn định nếu operation gửi lại.
- Observability đủ để phân biệt caller cancel với downstream failure.

**Cancel không phải rollback.** Dừng nhận HTTP response không đồng nghĩa server đã hủy giao dịch hoặc giải phóng mọi tác vụ.

## 12. Lifecycle và shutdown: phân biệt API JDK

Từ **Java 21**, `HttpClient` triển khai `AutoCloseable` và có `close()`, `shutdown()`, `shutdownNow()`, `awaitTermination(Duration)`, `isTerminated()`. Các API này **không có trong Java 11**.

Trên Java 11, đừng viết `client.close()` hoặc `client.shutdownNow()` rồi tin mã sẽ chạy. Thay vào đó:

- Tái sử dụng client cho những request cùng cấu hình.
- Ngừng nhận việc mới khi ứng dụng shutdown.
- Theo dõi future đang xử lý, request timeout, retry và các body stream do caller sở hữu.
- Dừng executor **do ứng dụng tạo và sở hữu**, nhưng chỉ sau khi xử lý công việc phụ thuộc; `executor.shutdown()` không phải API đóng toàn bộ HTTP client.
- Dùng cơ chế riêng cho shutdown deadline và resource metrics.

Trên **JDK 21+**, có thể gọi `client.shutdown()`, `client.awaitTermination(duration)`, rồi `shutdownNow()` nếu cần best effort theo chính sách. Tuy nhiên, một body `InputStream` hoặc `Publisher` chưa được đọc/cancel có thể làm shutdown lâu; `shutdownNow()` cũng không đảm bảo mọi I/O dừng ngay lập tức.

**Không đánh đồng** shutdown client (phạm vi toàn client, ảnh hưởng nhiều request) với cancel một future (phạm vi một exchange/chain) hoặc đóng một response stream (phạm vi body riêng).

## 13. Những lỗi phổ biến cần tránh

| Sai lầm | Vấn đề | Cách đúng |
| --- | --- | --- |
| `future.cancel(true)` rồi cho rằng request chưa gửi | Server có thể đã xử lý | Treat cancellation as local result state; idempotency/status lookup |
| Giả định Java 11 cancel chắc chắn hủy I/O | Javadoc Java 11 không bảo đảm | Thiết kế phiên bản-aware; đo transport riêng |
| Áp hành vi JDK 21 lên `--release 11` | Sai hợp đồng hoặc không biên dịch | Đọc API Java SE 11 và ghi phần mới riêng |
| Dùng `future.orTimeout` như một socket-close API | Future có thể timeout còn I/O chạy | Tách timeout kết quả và cleanup transport |
| `get(timeout)` timeout rồi quên future gốc | Request vẫn có thể chạy | Giữ reference exchange và áp policy sau timeout |
| Chỉ cancel dependent stage | Không bảo đảm hủy upstream exchange | Giữ future trả trực tiếp từ `sendAsync` nếu cần yêu cầu cancel |
| Ngắt thread gọi `sendAsync` sau khi nó trả về | Không điều khiển chính xác I/O nền | Quản lý future/cancel token/body |
| Nuốt `InterruptedException` | Ứng dụng không phản hồi với shutdown | Truyền tiếp hoặc restore interrupt |
| Xem `join()` như `get()` có checked interrupt | Cơ chế chờ khác nhau | Chọn API chờ theo yêu cầu interruption |
| Cancel sau khi nhận `InputStream` rồi bỏ quên body | Future đã hoàn thành nhưng stream vẫn mở | Đọc đến EOF hoặc đóng body stream |
| Hủy custom subscription rồi đợi terminal bắt buộc | `cancel` không bảo đảm `onComplete`/`onError` | Quản lý trạng thái hủy và cleanup độc lập |
| Coi HTTP 500 là `onError` của Flow | HTTP status có thể có body hoàn chỉnh | Kiểm tra status và body riêng |
| Retry POST sau timeout không dùng idempotency | Có thể ghi dữ liệu trùng | Dùng server deduplication/operation ID |
| Block lâu trong callback async | Tăng độ trễ và làm nghẽn executor | Tách xử lý nặng, giới hạn queue/concurrency |
| Dùng `client.close()` trong Java 11 | API không tồn tại | Java 11 quản lý client theo app; JDK 21+ mới có close |
| Xem `shutdownNow()` là bảo đảm tuyệt đối | Vẫn có tác vụ/bộ nhớ/tài nguyên chưa giải phóng | Best effort + timeout + monitoring |

## 14. Checklist triển khai và kiểm thử

Trước khi đưa một luồng HTTP bất đồng bộ vào production, trả lời:

1. **Phiên bản JDK** đang biên dịch và chạy là gì? Cancellation docs có nêu nỗ lực hủy transport không?
2. **Future gốc** từ `sendAsync` có được giữ lại để yêu cầu hủy đúng exchange không?
3. **Thời hạn** connect, request, wait và business deadline được phân biệt chưa?
4. **Interruption** ở đường đồng bộ có được truyền hoặc restore thay vì nuốt?
5. **BodyHandler** trả `String`, `InputStream`, `Stream<String>` hay `Publisher`? Ai quản lý việc đọc/đóng/cancel?
6. **Side effect** trên server có thể đã xảy ra sau khi caller cancel không? Có operation ID/idempotency?
7. **Callback async** có block lâu hoặc tích lũy nhiều dữ liệu trong memory không?
8. **Concurrent requests** và queue có bị giới hạn để tránh dồn tài nguyên khi upstream chậm?
9. **Transport cancellation** có được quan sát thực qua server log, connection metrics và end-to-end test theo HTTP/1.1 và HTTP/2?
10. **Shutdown** có ngừng nhận việc, xử lý các in-flight request, body stream và executor đúng ownership không?

Kịch bản nên thử: cancel trước khi gửi, trong lúc gửi body, sau headers nhưng chưa đọc body, trong lúc nhận body lớn, sau khi future hoàn tất, request timeout, thread interrupt khi `send`, mất kết nối đúng lúc server commit, response HTTP 4xx/5xx, và nhiều request cùng lúc. Cần kiểm tra kết quả nghiệp vụ **trên server**, không chỉ `future.isCancelled()`.

## 15. Bài tập tự đánh giá

**Bài 1.** Java 11 gọi `future.cancel(true)` và `future.isCancelled() == true`. Có chắc server không nhận request?

**Đáp án:** Không. Đó là trạng thái future. Javadoc `java.net.http` Java 11 không bảo đảm cancellation sẽ ngắt underlying operation; server có thể đã nhận hoặc xử lý request.

**Bài 2.** `future.get(2, TimeUnit.SECONDS)` ném `TimeoutException`. Future có tự cancel không?

**Đáp án:** Không. Đây là timeout của người chờ `get`. Future gốc có thể vẫn chưa hoàn tất và transport có thể vẫn chạy.

**Bài 3.** `future.orTimeout(2, TimeUnit.SECONDS)` trả về một future khác hẳn, để future gốc chạy bình thường?

**Đáp án:** Không. `orTimeout` trả về **chính future đó**, có thể hoàn thành đặc biệt nếu deadline tới trước. Đây vẫn không phải bảo đảm hủy I/O trên Java 11.

**Bài 4.** Future `sendAsync(..., ofInputStream())` đã hoàn tất, nhưng ứng dụng chưa đọc body stream. Gọi `future.cancel(true)` có đủ không?

**Đáp án:** Không. Future có thể đã hoàn thành, nên `cancel` không giải quyết body đang mở. Phải đọc hoặc đóng `InputStream`, và quản lý stream theo hợp đồng response.

**Bài 5.** Tại sao restore interrupt trong `catch (InterruptedException ex)` có ý nghĩa?

**Đáp án:** Các thao tác chờ có thể xóa cờ interrupt khi ném exception. Restore giúp các tầng điều phối phía trên biết thread được yêu cầu dừng nếu exception không tự được xử lý theo chính sách dừng.

**Bài 6.** JDK mới mô tả HTTP/2 stream reset khi cancel. Có suy ra server chưa chạy nghiệp vụ không?

**Đáp án:** Không. Reset transport có thể đến sau khi request đã được xử lý. Cancellation không phải rollback.

**Bài 7.** Một POST được retry sau timeout với cùng body nhưng server không hỗ trợ idempotency. Có an toàn không?

**Đáp án:** Chưa chắc. Server có thể xử lý cả hai attempt. Cần chính sách nghiệp vụ, idempotency hoặc tra cứu trạng thái giao dịch, không dựa vào HTTP cancellation.

## 16. Tóm tắt và tài liệu chính thức

- Trên **Java 11**, future cancellation **không có bảo đảm** dừng HTTP transport; hủy kết quả cục bộ khác với hủy network và hoàn tác nghiệp vụ.
- `Thread.interrupt` ảnh hưởng thread đang chờ; `send` có thể ném `InterruptedException`, nhưng server có thể đã nhận request. Với `get(timeout)`, timeout chờ không tự hủy future.
- `CompletableFuture.orTimeout` kết thúc **chính future đó** nếu quá hạn, **không** được dùng làm bằng chứng underlying I/O đã ngừng.
- Trên các **JDK mới**, default `HttpClient` có hành vi **best effort** khi cancel HTTP exchange: HTTP/1.1 có thể đóng connection, HTTP/2 có thể reset stream; không bảo đảm thời điểm và không tự rollback server.
- Nếu body streaming đã được trao cho caller, xử lý/đóng `InputStream` hoặc cancel subscription; không dùng future state để suy đoán body đã tải xong.
- Muốn khả năng phản hồi tốt phải kết hợp deadlines, resource cleanup, giới hạn concurrency, quản lý interrupt, idempotency, observability và shutdown đúng JDK.

**Nguồn API Oracle/Java SE còn áp dụng:**

- [`java.net.http` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/package-summary.html) — nêu rõ `cancel` của returned future có thể không interrupt underlying operation.
- [`HttpClient` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html) — `send`, `sendAsync`, request/response lifecycle.
- [`CompletableFuture` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — `cancel`, `get`, `join`, `orTimeout`, `completeOnTimeout`.
- [`HttpRequest.Builder` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html) — request timeout.
- [`HttpClient` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html) — JDK mới mô tả nỗ lực hủy HTTP exchange.
- [`HttpClient` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html) — `cancel(true)`, interruption và API lifecycle thêm từ JDK 21.
- [`HttpClient` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html) — đối chiếu API trên JDK hiện đại.
