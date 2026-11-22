# Dùng `CompletableFuture.completeOnTimeout()` để hoàn tất bằng giá trị dự phòng

`CompletableFuture.completeOnTimeout(value, timeout, unit)` cho phép đặt một thời hạn cho kết quả của một `CompletableFuture`. Nếu future chưa hoàn tất khi hết thời gian, nó được hoàn tất bình thường bằng giá trị dự phòng đã cung cấp. Nhờ vậy, chuỗi xử lý bất đồng bộ có thể tiếp tục với một giá trị thay thế thay vì phải kết thúc bằng lỗi timeout.

Phương thức được bổ sung từ Java 9 và vẫn là API hiện hành. Nó phù hợp khi ứng dụng có một kết quả dự phòng hợp lệ, chẳng hạn dữ liệu cache, cấu hình mặc định hoặc thông báo tạm thời. Cần hiểu rõ rằng phương thức hoàn tất đối tượng future bằng fallback; nó không tự dừng công việc nền đang tạo kết quả ban đầu.

## 1. Chữ ký và hợp đồng

```java
public CompletableFuture<T> completeOnTimeout(
        T value, long timeout, TimeUnit unit)
```

- `value`: giá trị dự phòng dùng để hoàn tất future nếu deadline đến trước khi future hoàn tất.
- `timeout`: khoảng thời gian chờ.
- `unit`: đơn vị của khoảng thời gian, ví dụ `TimeUnit.MILLISECONDS` hoặc `TimeUnit.SECONDS`.
- Giá trị trả về: chính đối tượng `CompletableFuture` hiện tại.

Phương thức không tạo một future độc lập. Nó đăng ký việc hoàn tất future hiện tại bằng `value` khi hết thời gian, nếu future vẫn chưa có kết quả. Vì vậy, gọi `completeOnTimeout()` làm thay đổi trạng thái của chính future nhận lời gọi.

## 2. Điều gì quyết định kết quả cuối cùng?

Việc hoàn tất bình thường từ tác vụ gốc và việc hoàn tất bằng timeout có thể xảy ra cạnh tranh. Quy tắc của `CompletableFuture` là lần hoàn tất thành công đầu tiên thắng:

1. Nếu tác vụ gốc hoàn tất trước deadline, giá trị hoặc exception của tác vụ gốc được giữ lại; fallback không ghi đè kết quả đã hoàn tất.
2. Nếu deadline đến trước khi future hoàn tất, future được hoàn tất bình thường bằng `value`.
3. Nếu future đã hoàn tất trước khi gọi `completeOnTimeout()`, lời gọi không thay đổi kết quả.
4. Sau khi future đã hoàn tất bằng fallback, kết quả đến muộn từ tác vụ gốc không thể thay đổi future đó nữa.

Điểm thứ tư rất quan trọng: timeout quyết định kết quả mà các bên đang quan sát qua future, nhưng không đảm bảo phần tính toán bên dưới đã dừng.

## 3. Ví dụ hoàn chỉnh: fallback khi tác vụ chạy quá lâu

Ví dụ sau tạo một tác vụ giả lập phản hồi chậm. Future được đặt deadline 50 ms, trong khi tác vụ mất khoảng 300 ms. Kết quả quan sát qua future là fallback; latch cho thấy tác vụ nền vẫn chạy đến cuối.

Tạo tệp `CompleteOnTimeoutDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class CompleteOnTimeoutDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch taskFinished = new CountDownLatch(1);
        CompletableFuture<String> request = CompletableFuture.supplyAsync(() -> {
            try {
                Thread.sleep(300);
                return "server response";
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new CompletionException(ex);
            } finally {
                taskFinished.countDown();
            }
        });

        CompletableFuture<String> withFallback = request.completeOnTimeout(
                "cached fallback", 50, TimeUnit.MILLISECONDS);

        System.out.println("Same future: " + (request == withFallback));
        System.out.println("Result: " + withFallback.get());
        System.out.println("Completed exceptionally: " + withFallback.isCompletedExceptionally());
        System.out.println("Underlying task finished later: "
                + taskFinished.await(2, TimeUnit.SECONDS));

        CompletableFuture<String> alreadyCompleted = CompletableFuture.completedFuture("ready");
        alreadyCompleted.completeOnTimeout("fallback", 50, TimeUnit.MILLISECONDS);
        System.out.println("Existing result preserved: " + alreadyCompleted.get());
    }
}
```

Biên dịch và chạy bằng JDK 9 trở lên:

```bash
javac --release 9 -Xlint:all CompleteOnTimeoutDemo.java
java CompleteOnTimeoutDemo
```

Kết quả stdout:

```text
Same future: true
Result: cached fallback
Completed exceptionally: false
Underlying task finished later: true
Existing result preserved: ready
```

`request == withFallback` là `true`, xác nhận phương thức trả về cùng future. Future hoàn tất bình thường với `cached fallback`, nên `isCompletedExceptionally()` là `false`. Tác vụ nguồn vẫn chạy xong sau đó; kết quả `server response` trả về muộn không ghi đè fallback. Future đã hoàn tất sẵn với `ready` cũng giữ nguyên kết quả.

## 4. Fallback là kết quả bình thường, không phải lỗi timeout

`completeOnTimeout()` hoàn tất future bằng giá trị được truyền vào. Vì đây là completion bình thường, các continuation như `thenApply()`, `thenAccept()` hoặc `thenCompose()` tiếp tục xử lý fallback giống như một kết quả thông thường:

```java
CompletableFuture<String> display = request
        .completeOnTimeout("cached response", 200, TimeUnit.MILLISECONDS)
        .thenApply(String::toUpperCase);
```

Nếu timeout thắng, continuation nhận `CACHED RESPONSE`. Nếu tác vụ gốc hoàn tất trước deadline, continuation nhận kết quả gốc đã chuyển thành chữ hoa. Các bước tiếp theo không tự biết giá trị đến từ tác vụ thật hay fallback; nếu nghiệp vụ cần phân biệt, hãy biểu diễn nguồn dữ liệu rõ ràng trong kiểu kết quả, chẳng hạn một object có trường `source` hoặc `isFallback`.

Không nên dùng một chuỗi fallback có vẻ giống dữ liệu thật nếu phía sau cần phân biệt hai trường hợp. Giá trị thay thế nên có ý nghĩa rõ ràng theo hợp đồng nghiệp vụ.

## 5. `completeOnTimeout()` không hủy tác vụ gốc

Phương thức này chỉ hoàn tất `CompletableFuture`. Nó không tự động:

- Ngắt thread đang chạy tác vụ.
- Hủy HTTP request, truy vấn cơ sở dữ liệu hoặc thao tác I/O nền.
- Dừng process con hoặc tác vụ được gửi đến executor.
- Hoàn tác tác dụng phụ mà tác vụ đã thực hiện.

Trong ví dụ, supplier vẫn ngủ đủ thời gian và chạy `finally` sau khi future đã trả fallback. Điều đó có nghĩa tác vụ nền có thể tiếp tục tiêu thụ thread, kết nối và tài nguyên. Nếu tác vụ có side effect, side effect vẫn có thể xảy ra sau khi caller đã nhận fallback.

Nếu cần dừng công việc thật sự, hãy dùng timeout/cancellation của API tạo tác vụ, giao thức hủy riêng hoặc cơ chế interruption mà tác vụ chủ động hỗ trợ. Không giả định `CompletableFuture.cancel(true)` sẽ ngắt thread đang chạy: hợp đồng `CompletableFuture` không dùng tham số `mayInterruptIfRunning` để điều khiển xử lý. Việc hủy phải được thiết kế ở tầng sở hữu tác vụ hoặc tài nguyên.

Với HTTP client, database driver hoặc thư viện I/O, ưu tiên cấu hình timeout của chính client/driver để giới hạn tài nguyên bên dưới. `completeOnTimeout()` có thể bổ sung chính sách kết quả cho caller, nhưng không thay thế timeout ở tầng vận chuyển.

## 6. So sánh `completeOnTimeout()`, `orTimeout()` và `get(timeout, unit)`

| API | Kết quả khi hết thời gian | Tác động lên future |
| --- | --- | --- |
| `completeOnTimeout(value, timeout, unit)` | Hoàn tất bình thường bằng `value` | Hoàn tất chính future hiện tại |
| `orTimeout(timeout, unit)` | Hoàn tất exceptional với `TimeoutException` | Hoàn tất chính future hiện tại |
| `get(timeout, unit)` | Lần gọi `get` ném `TimeoutException` nếu chưa có kết quả | Không tự hoàn tất hoặc thay đổi future chỉ vì lần chờ này hết hạn |

Dùng `completeOnTimeout()` khi fallback là một kết quả hợp lệ theo nghiệp vụ. Dùng `orTimeout()` khi vượt deadline phải được xem là lỗi và các bước xử lý lỗi cần nhận `TimeoutException`.

`get(timeout, unit)` chỉ giới hạn thời gian của lần chờ hiện tại. Nếu nó ném `TimeoutException`, future vẫn có thể tiếp tục chạy và hoàn tất sau đó. Điều này khác với `completeOnTimeout()` và `orTimeout()`, vì hai phương thức sau thay đổi trạng thái hoàn tất của future.

`completeOnTimeout()` và `orTimeout()` đều trả về cùng future. Không nên áp dụng cả hai chính sách timeout độc lập lên cùng một future rồi kỳ vọng một kết quả xác định: hành động timeout nào hoàn tất trước sẽ thắng. Hãy chọn một chính sách rõ ràng cho mỗi future.

## 7. Xử lý khi tác vụ gốc hoàn tất exceptional

`completeOnTimeout()` chỉ cung cấp fallback nếu future chưa hoàn tất. Nếu tác vụ gốc hoàn tất exceptional trước deadline, exception đó được giữ lại; fallback không tự thay thế lỗi đã xảy ra.

Ngược lại, nếu timeout hoàn tất future bằng fallback trước, một exception xuất hiện muộn từ tác vụ nguồn không thể thay đổi trạng thái future đã hoàn tất. Điều này có thể khiến lỗi muộn không được quan sát qua future đó. Nếu cần theo dõi lỗi hoặc trạng thái của tác vụ nền sau timeout, hãy ghi nhận chúng ở một kênh giám sát riêng.

Các bước xử lý exception như `exceptionally()`, `handle()` hoặc `whenComplete()` vẫn tuân theo trạng thái thực tế của future. Khi fallback được dùng, chuỗi xử lý đi theo nhánh kết quả bình thường; khi tác vụ gốc lỗi trước deadline, chuỗi xử lý đi theo nhánh exceptional.

## 8. Giá trị fallback được đánh giá khi nào?

Tham số đầu tiên là một giá trị `T`, không phải `Supplier<T>`. Java đánh giá biểu thức đối số trước khi gọi phương thức:

```java
future.completeOnTimeout(createFallback(), 200, TimeUnit.MILLISECONDS);
```

`createFallback()` chạy ngay khi biểu thức gọi phương thức được đánh giá, kể cả khi future sau đó hoàn tất bằng kết quả thật trước deadline. `completeOnTimeout()` trì hoãn thời điểm hoàn tất future, không trì hoãn việc tạo đối số fallback.

Vì vậy, nên truyền một giá trị fallback đã có sẵn hoặc một biểu thức rẻ. Nếu việc tạo fallback rất tốn kém và chỉ muốn thực hiện sau khi deadline hết hạn, cần thiết kế cơ chế lập lịch riêng bằng executor/scheduler và xử lý race hoàn tất một cách tường minh; `completeOnTimeout()` không nhận supplier để làm việc đó.

`CompletableFuture` cho phép kết quả `null`, nên API không biến fallback null thành một giá trị mặc định khác. Tuy nhiên, nếu các bước tiếp theo yêu cầu dữ liệu không null, hãy truyền fallback không null hoặc biểu diễn trạng thái thiếu bằng kiểu dữ liệu rõ ràng.

## 9. Thời gian timeout và lựa chọn đơn vị

Luôn chọn đơn vị dễ đọc và phù hợp với deadline:

```java
future.completeOnTimeout(fallback, 250, TimeUnit.MILLISECONDS);
future.completeOnTimeout(fallback, 5, TimeUnit.SECONDS);
```

Timeout là cơ chế lập lịch, không phải đồng hồ thời gian thực bảo đảm callback chạy chính xác tại một nanosecond cụ thể. Tải hệ thống, scheduling và khả năng thực thi thread có thể làm thời điểm hoàn tất thực tế trễ hơn deadline dự kiến. Hãy xem đây là giới hạn thời gian logic cho kết quả, không phải bảo đảm chính xác về thời gian CPU.

Truyền `TimeUnit` hợp lệ và tránh dùng con số không có đơn vị. Một timeout quá ngắn có thể khiến fallback thường xuyên thắng do chi phí lập lịch hoặc tải hệ thống; hãy chọn deadline dựa trên SLA và đặc tính thực tế của tác vụ.

## 10. Lỗi thiết kế thường gặp

- **Tưởng rằng phương thức trả về future mới:** nó trả về chính future hiện tại và thay đổi trạng thái của future đó.
- **Tưởng rằng timeout sẽ dừng tác vụ nguồn:** nó chỉ hoàn tất future; tác vụ nền có thể tiếp tục.
- **Dùng fallback như thể chắc chắn là dữ liệu thật:** các continuation không tự phân biệt fallback với kết quả nguồn.
- **Dùng fallback để che mọi exception:** lỗi xảy ra trước deadline vẫn được giữ lại; `completeOnTimeout()` không thay thế cơ chế xử lý exception.
- **Tạo fallback tốn kém trong đối số:** biểu thức fallback được đánh giá ngay khi gọi phương thức.
- **Kết hợp `completeOnTimeout()` và `orTimeout()` trên cùng future:** hai hành động tranh quyền hoàn tất; chỉ hành động thắng đầu tiên có hiệu lực.
- **Dùng `get(timeout, unit)` và nghĩ future đã bị timeout:** chỉ lần chờ bị giới hạn; future vẫn có thể hoàn tất sau đó.
- **Bỏ qua side effect muộn:** tác vụ nguồn có thể tiếp tục ghi dữ liệu hoặc gọi dịch vụ sau khi caller đã nhận fallback.

## 11. Quy trình áp dụng

1. Xác định deadline phù hợp với yêu cầu nghiệp vụ và đơn vị thời gian.
2. Chọn fallback có ý nghĩa rõ ràng và tương thích với kiểu `T`.
3. Quyết định timeout là kết quả bình thường (`completeOnTimeout`) hay lỗi (`orTimeout`).
4. Kiểm tra tác vụ nguồn có tiếp tục tiêu thụ tài nguyên hoặc tạo side effect sau timeout hay không.
5. Nếu cần dừng công việc nền, cấu hình timeout/cancellation tại API thực thi tác vụ; không dựa riêng vào việc hoàn tất future.
6. Nếu caller cần biết đã dùng fallback, đưa nguồn kết quả vào kiểu dữ liệu thay vì suy đoán từ giá trị.
7. Kiểm thử cả ba tình huống: tác vụ hoàn tất trước deadline, timeout thắng, và tác vụ nguồn hoàn tất exceptional.

`CompletableFuture.completeOnTimeout()` là cách đặt giá trị dự phòng cho kết quả bất đồng bộ khi future chưa hoàn tất đúng hạn. Dùng nó khi fallback là kết quả bình thường có thể chấp nhận; đồng thời quản lý riêng vòng đời tác vụ nguồn, vì hoàn tất future không đồng nghĩa với việc công việc bên dưới đã bị hủy.