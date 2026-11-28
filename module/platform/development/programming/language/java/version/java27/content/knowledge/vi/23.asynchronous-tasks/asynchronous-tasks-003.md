# Xử lý lỗi, timeout và giới hạn của cancellation

Trong Java 27, một tác vụ bất đồng bộ có thể hoàn tất với **giá trị thành công**, hoàn tất bằng **ngoại lệ**, bị **hủy** hoặc vẫn đang thực thi sau khi người gọi đã **hết thời gian chờ**. Những trạng thái này liên quan nhưng không đồng nghĩa. Đặc biệt, một **CompletableFuture** đã hoàn tất với **TimeoutException** không chứng minh rằng công việc nền đã dừng, và **CompletableFuture.cancel(true)** không bảo đảm ngắt thread thực hiện công việc.

Bài thuộc chương **Tác vụ bất đồng bộ** và tập trung vào API **CompletableFuture**, **CompletionStage**, **Future**, **ExecutorService** và cơ chế hủy hợp tác trong Java hiện đại. Các ví dụ sử dụng tính năng vẫn áp dụng trong Java 27, không phụ thuộc vào API legacy.

Mục tiêu học tập:

- Phân biệt **lỗi của tác vụ**, **lỗi của callback** và **lỗi tại phía chờ kết quả**.
- Chọn đúng **exceptionally()**, **handle()**, **whenComplete()**, **exceptionallyCompose()**.
- Hiểu **join()**, **get()**, **get(timeout)** và việc đóng gói ngoại lệ.
- Sử dụng **orTimeout()**, **completeOnTimeout()** mà không hiểu sai khả năng dừng tác vụ.
- Biết giới hạn của **Future.cancel(...)**, cancellation giữa các stage, interruption và cleanup.
- Thiết kế deadline, retry, fallback và backpressure có chủ đích.

## 1. Trạng thái kết thúc của CompletableFuture

Một **CompletableFuture<T>** đại diện cho kết quả có thể chưa sẵn sàng. Nó triển khai **Future<T>** và **CompletionStage<T>**, nhờ đó vừa có thể chờ kết quả, vừa nối thêm các bước xử lý.

~~~text
                      CHƯA HOÀN TẤT
                             |
               +-------------+-------------+
               |                           |
               v                           v
      HOÀN TẤT BÌNH THƯỜNG          HOÀN TẤT NGOẠI LỆ
      kết quả T (có thể null)      Throwable, cancellation
               |                           |
               +-------------+-------------+
                             |
                         ĐÃ HOÀN TẤT
~~~

Trạng thái kết thúc chỉ được thiết lập một lần qua các thao tác thông thường. Nếu nhiều bên cùng cố hoàn tất, chỉ một bên thắng:

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> future = new CompletableFuture<>();

System.out.println(future.complete("first"));   // true
System.out.println(future.complete("second"));  // false
System.out.println(future.join());              // first
~~~

**isDone()** là true nếu future đã hoàn tất theo bất kỳ đường nào, bao gồm thành công, ngoại lệ hoặc cancellation. Không được coi **isDone()** là bằng chứng nghiệp vụ đã thành công.

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("unavailable"));

System.out.println(failed.isDone());                  // true
System.out.println(failed.isCompletedExceptionally()); // true
~~~

**CompletableFuture.failedFuture(Throwable)** tạo một future đã hoàn tất ngoại lệ, rất hữu ích để biểu diễn lỗi hoặc viết ví dụ kiểm thử mà không cần tạo thread nền.

## 2. Nguồn lỗi trong chuỗi tác vụ

Lỗi có thể xuất hiện ở nhiều chỗ:

1. **Trước khi tạo được future:** dữ liệu đầu vào sai hoặc executor từ chối nhận task.
2. **Trong công việc nền:** lambda của **supplyAsync()** hoặc **runAsync()** ném ngoại lệ.
3. **Trong stage xử lý:** **thenApply()**, **thenCompose()**, callback chuyển đổi hoặc callback phục hồi có lỗi.
4. **Trong thao tác I/O:** network timeout, lỗi đọc tệp, kết nối không sẵn sàng.
5. **Ở phía chờ:** thread gọi **get()** bị interrupt hoặc **get(timeout)** hết thời gian.
6. **Khi dọn dẹp:** đóng kết nối, stream hoặc executor phát sinh lỗi.

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<Integer> pipeline =
        CompletableFuture.supplyAsync(() -> 24)
                .thenApply(value -> 100 / (value - 24));
~~~

Stage đầu có thể thành công với giá trị 24. Stage thứ hai ném **ArithmeticException**, nên future trả về từ **thenApply()** hoàn tất ngoại lệ. Điều đó **không** có nghĩa stage đầu bị thay đổi thành lỗi.

### Các stage bình thường bỏ qua đường lỗi

~~~java
CompletableFuture<String> source =
        CompletableFuture.failedFuture(
                new IllegalStateException("service down"));

CompletableFuture<String> next =
        source.thenApply(value -> {
            System.out.println("Not executed");
            return value.toUpperCase();
        });
~~~

Hàm trong **thenApply()** không chạy vì source không có kết quả thành công. **next** hoàn tất ngoại lệ và có thể được xử lý tại một stage phục hồi tiếp theo.

Một pipeline cần xác định rõ **lỗi nào phục hồi được, lỗi nào cần truyền tiếp**. Không nên coi mọi exception là lỗi tạm thời có thể thử lại.

## 3. Executor và vị trí thực thi callback

~~~java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(() -> "data");
~~~

Nếu không truyền executor, các tác vụ async thường được chạy qua executor mặc định của CompletableFuture (thông thường liên quan đến **ForkJoinPool.commonPool()**, với quy tắc dự phòng của JDK).

Nếu cần kiểm soát nơi chạy:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    CompletableFuture<String> future =
            CompletableFuture.supplyAsync(() -> "ready", executor);

    System.out.println(future.join()); // ready
}
~~~

Các method không có hậu tố **Async** như **thenApply()**, **handle()**, **whenComplete()** có thể chạy callback trong thread hoàn tất stage hoặc một thread khác tham gia quá trình hoàn tất. Chúng **không nhất thiết tạo thread mới**.

~~~java
CompletableFuture<String> converted =
        source.thenApplyAsync(
                value -> transform(value),
                executor
        );
~~~

Ví dụ trên giả định **source**, **transform(...)** và **executor** đã được định nghĩa. Biến thể **Async** cho phép chỉ định executor để chạy callback. Nên tách công việc chặn lâu khỏi thread đang hoàn tất stage khi cần.

Virtual thread giúp giảm chi phí chờ I/O trong nhiều tình huống nhưng **không tự bảo vệ dữ liệu dùng chung, không tạo backpressure và không sửa giới hạn cancellation**.

## 4. join() và get(): khác biệt về cách biểu diễn lỗi

Khi chờ một CompletableFuture, hai phương thức thường gặp là:

~~~java
String value = future.join();
// hoặc
String value = future.get();
~~~

| Trạng thái | **join()** | **get()** |
|---|---|---|
| Thành công | Trả kết quả T | Trả kết quả T |
| Hoàn tất ngoại lệ thông thường | Thường ném **CompletionException** chứa cause | Ném **ExecutionException** chứa cause |
| Bị cancel | Có thể ném **CancellationException** trực tiếp | Ném **CancellationException** cho future bị cancel |
| Thread chờ bị interrupt | Không khai báo InterruptedException | Có thể ném **InterruptedException** |
| Chờ có thời hạn | Không có overload timeout | **get(timeout, unit)** |

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

CompletableFuture<Integer> invalid =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid input"));

try {
    invalid.join();
} catch (CompletionException exception) {
    System.out.println(exception.getCause().getMessage());
    // invalid input
}
~~~

**get()** yêu cầu caller xử lý hoặc khai báo **InterruptedException** và **ExecutionException**. **join()** không khai báo các checked exception đó nên tiện cho composition, nhưng không phải một cơ chế xử lý lỗi tự động.

### Không giả định lỗi luôn có cùng lớp bọc

Tại callback xử lý lỗi, **Throwable** có thể là exception gốc hoặc một **CompletionException** chứa exception gốc, tùy cách stage được tạo và hoàn tất. Không nên phân loại lỗi chỉ dựa trên chuỗi tên lớp bọc.

Nếu cần lấy nguyên nhân để quyết định retry hoặc fallback:

~~~java
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

static Throwable rootCause(Throwable error) {
    Throwable current = error;

    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }

    return current;
}
~~~

Khi ghi log, hãy giữ toàn bộ chuỗi **cause** và thông tin stack trace, không chỉ giữ thông điệp từ nguyên nhân cuối cùng.

## 5. exceptionally(): khôi phục bằng một giá trị

**exceptionally(...)** chỉ gọi hàm xử lý khi stage trước hoàn tất ngoại lệ. Nó tạo stage kết quả kiểu T, thường dùng để chuyển lỗi thành **fallback** hợp lệ.

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> answer =
        CompletableFuture.<String>failedFuture(
                        new IllegalStateException("upstream unavailable"))
                .exceptionally(error -> "cached-value");

System.out.println(answer.join()); // cached-value
~~~

Nếu source thành công, hàm fallback không chạy:

~~~java
CompletableFuture<String> answer =
        CompletableFuture.completedFuture("live")
                .exceptionally(error -> "cached");

System.out.println(answer.join()); // live
~~~

Nên dùng fallback khi hợp đồng nghiệp vụ chấp nhận dữ liệu thay thế: ví dụ cấu hình không bắt buộc, dữ liệu cache còn hiệu lực hoặc chế độ giảm chức năng đã được công bố.

**Tránh âm thầm biến mọi lỗi thành null hoặc chuỗi rỗng.** Nếu caller không phân biệt được “kết quả thật” và “thất bại đã bị che”, lỗi dữ liệu có thể xuất hiện muộn hơn ở nơi khó chẩn đoán.

### Hàm fallback có thể gây lỗi mới

~~~java
CompletableFuture<String> answer =
        CompletableFuture.<String>failedFuture(
                        new IllegalArgumentException("bad request"))
                .exceptionally(error -> {
                    throw new IllegalStateException(
                            "recovery failed", error);
                });
~~~

Stage mới hoàn tất ngoại lệ do callback. Việc bọc lỗi có thể hợp lý để chuyển ngữ nghĩa giữa các tầng API, nhưng không nên bọc nhiều lần không có mục đích.

## 6. handle(): hợp nhất đường thành công và thất bại

**handle((value, error) -> ...)** được gọi sau khi source hoàn tất, bất kể thành công hay lỗi, và có thể đổi kiểu kết quả từ T sang U.

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<Integer> result =
        CompletableFuture.<String>failedFuture(
                        new IllegalArgumentException("bad text"))
                .handle((value, error) ->
                        error == null ? value.length() : 0);

System.out.println(result.join()); // 0
~~~

Khi thành công, **error == null**; khi thất bại, callback nhận thông tin lỗi. Giá trị thành công **value** có thể là null theo hợp đồng của future, nên hãy kiểm tra **error**, không chỉ kiểm tra **value != null**.

### Biểu diễn lỗi thành dữ liệu nghiệp vụ

~~~java
sealed interface LookupResult permits Found, Unavailable {}

record Found(String value) implements LookupResult {}

record Unavailable(String reason) implements LookupResult {}

CompletableFuture<LookupResult> result =
        CompletableFuture.supplyAsync(() -> "item-42")
                .<LookupResult>handle((value, error) ->
                        error == null
                                ? new Found(value)
                                : new Unavailable("lookup failed"));
~~~

Kiểu **LookupResult** giúp caller xử lý cả hai khả năng tường minh. Tuy nhiên, nếu hệ thống cần alert hoặc phân tích nguyên nhân, hãy ghi nhận Throwable ở tầng thích hợp; đừng biến toàn bộ lỗi thành một lý do chung rồi mất dấu lỗi gốc.

**handle() cũng có thể ném exception**, ví dụ khi phần thân callback tự thất bại. Nó không bảo đảm pipeline từ đó trở đi luôn thành công.

## 7. whenComplete(): quan sát, không phải fallback

**whenComplete(...)** phù hợp cho log, telemetry hoặc cleanup nhẹ khi không có ý định đổi kết quả của source.

~~~java
CompletableFuture<String> observed =
        CompletableFuture.completedFuture("OK")
                .whenComplete((value, error) -> {
                    if (error == null) {
                        System.out.println("completed=" + value);
                    } else {
                        System.err.println("failed=" + error);
                    }
                });

System.out.println(observed.join());
~~~

Kết quả:

~~~text
completed=OK
OK
~~~

Nếu source đã lỗi, **whenComplete** không tự biến lỗi thành giá trị thành công. Nếu callback quan sát ném exception khi source thành công, stage kết quả có thể bị lỗi do callback; nếu source đã lỗi, lỗi source được ưu tiên theo hợp đồng **whenComplete**.

Đừng thực hiện I/O chặn lâu trong callback mà không hiểu thread thực thi nó. Nếu cần tách logging nặng:

~~~java
future.whenCompleteAsync(
        (value, error) -> logResult(value, error),
        loggingExecutor
);
~~~

Ví dụ giả định **logResult(...)** và **loggingExecutor** đã được định nghĩa.

## 8. exceptionallyCompose(): phục hồi bằng một stage khác

Khi fallback cần một tác vụ bất đồng bộ khác, **exceptionallyCompose(...)** nhận một hàm trả **CompletionStage<T>** rồi nối nó vào pipeline.

~~~java
import java.util.concurrent.CompletableFuture;

static CompletableFuture<String> fetchPrimary() {
    return CompletableFuture.failedFuture(
            new IllegalStateException("primary unavailable"));
}

static CompletableFuture<String> fetchBackup() {
    return CompletableFuture.completedFuture("backup-value");
}

static CompletableFuture<String> fetchWithBackup() {
    return fetchPrimary()
            .exceptionallyCompose(error -> fetchBackup());
}
~~~

Kết quả:

~~~java
System.out.println(fetchWithBackup().join()); // backup-value
~~~

**exceptionallyCompose() không tự retry tác vụ đã lỗi.** Nó chỉ chạy hàm phục hồi mà bạn truyền vào. Trong ví dụ, hàm đó gọi **fetchBackup()**.

So sánh:

- **thenCompose(fn)** chạy khi source thành công, nhận giá trị rồi nối stage tiếp theo.
- **exceptionallyCompose(fn)** chạy trên đường lỗi và nối stage phục hồi.
- **exceptionally(fn)** chuyển lỗi thành **giá trị T**, không phải stage mới.

Các biến thể **Async** có thể thích hợp khi callback cần một executor cụ thể.

## 9. Bảng chọn API xử lý lỗi

| Phương thức | Khi source thành công | Khi source thất bại | Mục tiêu |
|---|---|---|---|
| **exceptionally(fn)** | Bỏ qua fn, giữ giá trị | Gọi fn để cung cấp T | Fallback trực tiếp |
| **handle(fn)** | Gọi fn với value và error=null | Gọi fn với thông tin lỗi | Chuyển cả hai đường thành U |
| **whenComplete(action)** | Quan sát giá trị | Quan sát lỗi | Logging/telemetry, giữ ngữ nghĩa kết quả nguồn |
| **exceptionallyCompose(fn)** | Giữ giá trị | Gọi fn trả CompletionStage<T> | Fallback bất đồng bộ |
| **thenApply(fn)** | Chuyển T thành U | Không gọi fn, truyền đường lỗi | Xử lý giá trị thành công |
| **thenCompose(fn)** | Nối tác vụ bất đồng bộ tiếp | Không gọi fn, truyền đường lỗi | Composition đường thành công |

Có thể kết hợp chúng theo những ranh giới nghiệp vụ cụ thể:

~~~java
CompletableFuture<String> result =
        fetch()
                .whenComplete((value, error) ->
                        recordMetric(error))
                .exceptionally(error -> "cached")
                .thenApply(String::strip);
~~~

Ví dụ giả định **fetch()** và **recordMetric(...)** đã tồn tại. Đây là một pipeline **quan sát → phục hồi → chuyển đổi**. Nếu mục đích là “caller phải biết hệ thống bị lỗi”, bỏ fallback ở tầng này và truyền lỗi lên caller.

## 10. Phân loại lỗi trước khi retry hoặc fallback

Không phải lỗi nào cũng khắc phục bằng cùng một cách.

| Loại tình huống | Cách xử lý nên cân nhắc |
|---|---|
| Dữ liệu đầu vào không hợp lệ | Trả lỗi có cấu trúc; thường không retry cùng dữ liệu |
| Lỗi kết nối tạm thời | Retry có giới hạn, backoff và deadline |
| Hết quota hoặc bị từ chối quá tải | Backpressure, xử lý theo chính sách của dịch vụ |
| Timeout | Xác nhận trạng thái thực; xem xét dừng chờ, dừng tác vụ hoặc fallback |
| **CancellationException** | Thường tôn trọng ý định hủy; không mặc nhiên đổi thành thành công |
| **NullPointerException** do lỗi chương trình | Sửa lỗi; không che bằng fallback chung |
| Lỗi môi trường nghiêm trọng | Không biến mọi Error thành kết quả nghiệp vụ bình thường |

Một handler như:

~~~java
future.exceptionally(error -> "default");
~~~

có thể chuyển cả đường **cancellation** thành thành công nếu không có điều kiện phân loại. Khi caller yêu cầu hủy, hành vi đó có thể không đúng.

**Không phân loại lỗi chỉ theo message.** Dựa trên loại exception, cause chain, mã lỗi ổn định và hợp đồng của dịch vụ được gọi.

## 11. Timeout khi chờ: get(timeout, unit)

**Future.get(timeout, unit)** giới hạn thời gian **thread đang chờ kết quả**. Nó không tự hoàn tất hay hủy future.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

CompletableFuture<String> pending = new CompletableFuture<>();

try {
    pending.get(50, TimeUnit.MILLISECONDS);
} catch (TimeoutException exception) {
    System.out.println("Caller stopped waiting");
}

System.out.println(pending.isDone()); // false
~~~

Đây là một future chưa có ai hoàn tất, vì thế chờ có thời hạn sẽ hết thời gian. Sau **TimeoutException** của **get(timeout)**, future vẫn ở trạng thái chưa hoàn tất.

Ngoài TimeoutException, lời gọi **get(timeout)** có thể ném **InterruptedException**, **ExecutionException** hoặc **CancellationException** theo tình huống.

**Kết luận:** timeout tại điểm chờ là chính sách của caller, không phải lệnh dừng công việc.

## 12. orTimeout(): hoàn tất chính CompletableFuture bằng lỗi

**CompletableFuture.orTimeout(timeout, unit)** sắp xếp hoàn tất **chính future đang nhận lời gọi** với **TimeoutException** nếu nó vẫn chưa hoàn tất khi hết hạn.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

CompletableFuture<String> pending = new CompletableFuture<>();

CompletableFuture<String> timed =
        pending.orTimeout(50, TimeUnit.MILLISECONDS);

System.out.println(timed == pending); // true

try {
    timed.join();
} catch (CompletionException exception) {
    System.out.println(
            exception.getCause() instanceof TimeoutException); // true
}
~~~

Những hệ quả:

- Nếu source hoàn tất trước hạn, kết quả của source được giữ.
- Nếu timeout thắng, future hoàn tất ngoại lệ.
- **orTimeout() trả về cùng đối tượng CompletableFuture**, không tạo một future độc lập.
- Các dependent stage có thể nhận đường lỗi timeout.
- **Tác vụ chạy bên dưới không tự bị interrupt hoặc dừng** chỉ vì future đã timed out.

### Khi dùng một future chia sẻ

~~~java
CompletableFuture<String> shared = fetchShared();

shared.orTimeout(1, TimeUnit.SECONDS);
~~~

Nếu **shared** được nhiều caller sử dụng, timeout đặt bởi caller A có thể ảnh hưởng tới caller B. Khi mỗi caller có timeout riêng, nên tạo một ranh giới kết quả riêng; nhưng ngay cả stage phụ thuộc hoặc bản sao completion cũng **không mặc nhiên dừng công việc nguồn** khi hết hạn.

## 13. completeOnTimeout(): hoàn tất bằng fallback

**completeOnTimeout(value, timeout, unit)** đưa ra **giá trị thành công dự phòng** nếu future chưa hoàn tất khi thời hạn tới.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

CompletableFuture<String> pending = new CompletableFuture<>();

pending.completeOnTimeout(
        "temporarily unavailable",
        50,
        TimeUnit.MILLISECONDS
);

System.out.println(pending.join()); // temporarily unavailable
~~~

Phương thức này cũng trả lại **chính future nguồn**.

| Cơ chế | Khi hết thời gian | Có thay đổi trạng thái future? | Có tự dừng tác vụ nền? |
|---|---|---|---|
| **get(timeout, unit)** | Caller nhận TimeoutException | Không | Không |
| **orTimeout(...)** | Future hoàn tất ngoại lệ TimeoutException | Có | Không |
| **completeOnTimeout(...)** | Future hoàn tất bình thường với fallback | Có | Không |

Chọn **completeOnTimeout()** khi giá trị thay thế là hợp đồng hợp lệ. Với thanh toán, tạo đơn hàng hoặc ghi dữ liệu có side effect, timeout không có nghĩa “chắc chắn chưa làm” hay “có thể coi là thành công với default”.

## 14. Timeout không đồng nghĩa công việc đã dừng

Hình dung một request đang được gửi:

~~~text
Tác vụ nền: gọi hệ thống ngoài ------------------> có thể vẫn chạy
                   |
                   +-- Sau 500 ms: CompletableFuture timeout
                   |
Caller: ngừng chờ và trả phản hồi fallback
~~~

Tác vụ nền có thể tiếp tục ghi dữ liệu, gửi email hoặc hoàn tất một giao dịch sau khi caller không còn chờ kết quả.

Hệ quả đối với thiết kế:

1. Retry sau timeout có thể tạo **side effect trùng lặp**.
2. Timeout tại tầng CompletableFuture không thay thế timeout tại socket, HTTP client hoặc driver.
3. Cần quy định rõ ai sở hữu tài nguyên và ai có quyền đóng.
4. Với thao tác quan trọng, dùng **idempotency key**, trạng thái yêu cầu hoặc cơ chế xác nhận kết quả thực tế trước khi retry.
5. Nếu một callback không còn cần thiết, có thể không phải tiếp tục xử lý kết quả, nhưng việc bỏ kết quả **khác** với dừng công việc đã khởi chạy.

Đừng dùng trạng thái **isCompletedExceptionally()** của future để suy ra một giao dịch ngoài hệ thống đã rollback.

## 15. Future.cancel(...) và CompletableFuture.cancel(...)

**Future.cancel(boolean mayInterruptIfRunning)** biểu diễn yêu cầu hủy theo hợp đồng Future. Với những Future được **ExecutorService.submit(...)** trả về, **cancel(true)** có thể yêu cầu interrupt thread thực thi tác vụ nếu nó đang chạy; vẫn không bảo đảm việc tác vụ thật sự ngừng ngay.

**CompletableFuture.cancel(mayInterruptIfRunning)** khác ở điểm quan trọng: tham số boolean **không được sử dụng để điều khiển interruption** của computation. Nó hoàn tất future theo trạng thái hủy bằng **CancellationException** nếu future chưa hoàn tất theo cách khác.

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> pending = new CompletableFuture<>();

boolean cancelled = pending.cancel(true);

System.out.println(cancelled);             // true
System.out.println(pending.isCancelled()); // true
System.out.println(pending.isDone());      // true

try {
    pending.join();
} catch (CancellationException exception) {
    System.out.println("Future cancelled");
}
~~~

Kết quả **cancelled=true** mô tả trạng thái của future; **không chứng minh một thread nền đã bị ngắt**.

| Khía cạnh | Future thực thi từ executor (tùy implementation) | CompletableFuture |
|---|---|---|
| **cancel(false)** | Hủy không yêu cầu interrupt thread chạy | Hoàn tất theo cancellation |
| **cancel(true)** | Có thể yêu cầu interrupt nếu task đang chạy | Boolean không điều khiển interrupt |
| Có bảo đảm task dừng ngay? | Không | Không |
| Caller đọc future đã cancel | Thường nhận CancellationException | Nhận CancellationException |
| Muốn dừng công việc thật | Tác vụ cần hợp tác với tín hiệu | Cần cơ chế hủy tác vụ thực sự bên ngoài future nếu muốn dừng |

Không suy diễn hành vi cancellation của một thư viện hay framework cụ thể thành quy tắc chung cho tất cả Future.

## 16. Cancellation giữa các stage không truyền hai chiều hoàn toàn

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> source = new CompletableFuture<>();

CompletableFuture<Integer> dependent =
        source.thenApply(String::length);

source.cancel(false);
~~~

Khi source bị cancel, **thenApply(String::length)** không thực hiện chuyển đổi giá trị. Dependent stage hoàn tất ngoại lệ theo đường cancellation của source. Khi gọi **dependent.join()**, lỗi có thể được biểu diễn bằng **CompletionException** chứa **CancellationException** làm cause:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletionException;

try {
    dependent.join();
} catch (CompletionException exception) {
    System.out.println(
            exception.getCause() instanceof CancellationException);
    // true
}
~~~

**Hủy dependent không mặc nhiên hủy source**. Tương tự, hủy một future tổng hợp không đồng nghĩa hủy tất cả các task thành phần.

Nếu cần hủy một nhóm công việc, hãy giữ handle của từng tác vụ thực sự có khả năng hủy và xây dựng chính sách cancellation xuyên suốt pipeline.

### Tôn trọng cancellation khi phục hồi lỗi

~~~java
CompletableFuture<String> recovered =
        source.exceptionally(error -> "fallback");
~~~

Một handler chung như vậy có thể che ý định hủy bằng cách tạo ra kết quả thành công. Nếu cancellation phải được chuyển tới caller, hãy phân loại nguyên nhân và giữ đường hủy thay vì trả fallback không điều kiện.

## 17. InterruptedException và cooperative cancellation

Một số thao tác chờ như **Thread.sleep()**, **BlockingQueue.take()** hoặc **Future.get()** có thể ném **InterruptedException** khi thread bị interrupt.

Ví dụ với Future được tạo bằng executor:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {

    Future<?> task = executor.submit(() -> {
        try {
            Thread.sleep(10_000);
            System.out.println("Completed normally");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            System.out.println("Cancellation signal observed");
        }
    });

    task.cancel(true);
}
~~~

Nếu task bắt đầu và đang chờ trong **sleep()**, yêu cầu interrupt có thể làm sleep ném InterruptedException. Nếu cancellation xảy ra trước khi task bắt đầu, phần thân task có thể không chạy; thứ tự và số dòng log không cố định.

Mẫu khi không truyền InterruptedException lên được:

~~~java
try {
    performBlockingOperation();
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Đoạn trên giả định **performBlockingOperation()** khai báo InterruptedException. Nếu có thể khai báo **throws InterruptedException**, truyền ngoại lệ lên caller thường rõ ràng hơn.

**Không nuốt InterruptedException** trong vòng lặp vô hạn: điều đó có thể khiến hệ thống không thể tắt đúng cách.

## 18. Khi công việc không hợp tác với interrupt

Một chương trình CPU-bound hoặc lời gọi I/O không phản hồi interruption có thể tiếp tục chạy dù một Future đã bị cancel.

~~~java
static long calculateUntilInterrupted() {
    long sum = 0;

    while (!Thread.currentThread().isInterrupted()) {
        sum++;
    }

    return sum;
}
~~~

Ví dụ chỉ minh họa kiểm tra cờ interrupt. Trong chương trình thật, vòng lặp cần một mục tiêu tính toán và điều kiện hoàn thành; không nên dùng busy loop để chờ tín hiệu.

**Thread.interrupted()** đọc đồng thời xóa cờ interrupt của thread hiện tại, còn **Thread.currentThread().isInterrupted()** kiểm tra mà không xóa nó.

Với I/O, nên chọn API có **connection timeout**, **read timeout** hoặc phương thức đóng tài nguyên phù hợp. Interrupt là cơ chế hữu ích nhưng không thay thế hợp đồng của hệ thống ngoài.

## 19. Dọn dẹp tài nguyên và sở hữu executor

Nếu một tác vụ mở stream hoặc kết nối, chính tác vụ hoặc thành phần sở hữu phải đóng tài nguyên theo hợp đồng.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

static CompletableFuture<String> loadFile(
        Path path, Executor executor) {

    return CompletableFuture.supplyAsync(() -> {
        try {
            return Files.readString(path);
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    }, executor);
}
~~~

**Files.readString(...)** xử lý tài nguyên đọc tệp theo hợp đồng của nó. Khi tự mở **BufferedReader** hoặc stream, nên dùng **try-with-resources bên trong task**.

**Cancel CompletableFuture trả về không chứng minh tác vụ đọc tệp đã dừng.** Muốn dừng I/O, phải dựa vào cơ chế hỗ trợ của tác vụ và tài nguyên thực sự.

### Tránh đóng executor trong method trả future

~~~java
static CompletableFuture<String> startWork() {
    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
        return CompletableFuture.supplyAsync(
                () -> slowOperation(), executor);
    }
}
~~~

Ví dụ giả định **slowOperation()** tồn tại. Cách tổ chức này có thể phá ý định trả về ngay: **ExecutorService.close() chờ tác vụ kết thúc** trước khi thoát khỏi try-with-resources. Với API bất đồng bộ, nên quản lý executor ở cấp service hoặc thành phần có vòng đời dài hơn một lời gọi.

Đóng tài nguyên sau timeout cần có chính sách rõ về những task vẫn đang sử dụng tài nguyên; đóng một connection được mượn từ component khác mà không có quyền sở hữu cũng có thể gây lỗi.

## 20. Retry có giới hạn, backoff và idempotency

**Retry là tạo một lần thực thi mới**, không phải chỉ gắn một callback fallback lên cùng future đã lỗi.

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("unavailable"));

CompletableFuture<String> fallback =
        failed.exceptionally(error -> "cached");
~~~

**fallback** trả giá trị dự phòng, **không chạy lại tác vụ đã thất bại**.

Retry nên có các yếu tố:

- **Giới hạn số lần thử** và deadline tổng.
- **Phân loại lỗi** để tránh retry lỗi đầu vào không hợp lệ.
- **Backoff**, có thể thêm jitter khi nhiều caller cùng retry.
- **Idempotency** đối với thao tác có side effect.
- **Tín hiệu hủy** để không tạo thêm lần thử mới sau khi caller đã bỏ yêu cầu.
- **Giới hạn concurrency** để retry không gây quá tải ngược.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;

Executor delayed =
        CompletableFuture.delayedExecutor(100, TimeUnit.MILLISECONDS);

CompletableFuture<String> later =
        CompletableFuture.supplyAsync(() -> "next-attempt", delayed);
~~~

**delayedExecutor(...)** chỉ giúp trì hoãn lịch bắt đầu task; nó không tự xác định khi nào retry, không tự quản lý deadline hoặc hủy những attempt trước.

Đặc biệt, timeout một yêu cầu ghi dữ liệu **không chứng minh lần ghi trước chưa thực hiện**. Retry cần cơ chế kiểm tra trạng thái/idempotency key nếu không muốn tạo bản ghi trùng.

## 21. allOf(), anyOf() và nhiều tác vụ cùng lúc

**CompletableFuture.allOf(...)** tạo một stage tổng hợp kết thúc sau khi các future thành phần đều kết thúc. Nếu có thành phần lỗi, stage tổng hợp cũng hoàn tất ngoại lệ theo hợp đồng.

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> first =
        CompletableFuture.completedFuture("A");

CompletableFuture<String> second =
        CompletableFuture.completedFuture("B");

CompletableFuture<Void> all =
        CompletableFuture.allOf(first, second);

all.join();
System.out.println(first.join() + second.join()); // AB
~~~

**allOf()** trả **CompletableFuture<Void>**, không tự tạo danh sách kết quả. Nếu tổng hợp thành công, có thể đọc các future thành phần sau đó.

**anyOf(...)** hoàn tất theo **future đầu tiên hoàn tất**, có thể là thành công hoặc lỗi. Nó **không** tự bỏ qua lỗi để tìm thành công đầu tiên.

~~~java
CompletableFuture<Object> earliest =
        CompletableFuture.anyOf(first, second);
~~~

Nếu đặt timeout lên stage tổng hợp:

~~~java
CompletableFuture<Void> combined =
        CompletableFuture.allOf(first, second);

combined.orTimeout(1, TimeUnit.SECONDS);
~~~

Việc combined timeout **không tự hủy những task thành phần**. Tác vụ có thể vẫn chạy và gây side effect. Với workload có nhiều nhánh, hãy xác định khi nào bỏ kết quả, khi nào yêu cầu hủy các nhánh và cách giải phóng tài nguyên.

## 22. Deadline tổng và giới hạn tải

Giả sử một request có deadline 2 giây:

~~~text
Deadline của caller: 2 giây
       |
       +-- Tra cache
       |
       +-- Gọi dịch vụ A
       |
       +-- Nếu cần, gọi dịch vụ B
       |
       +-- Tổng hợp kết quả
~~~

Nếu từng bước tự chờ 2 giây, tổng thời gian có thể vượt deadline của caller. Nên truyền **thời gian còn lại** hoặc một deadline xuyên suốt các bước.

**System.nanoTime()** phù hợp để đo **khoảng thời gian** theo đồng hồ đơn điệu, không phải để làm timestamp lịch. Khi chuyển deadline sang timeout của một API, cần tính lại ngân sách còn lại và xử lý trường hợp đã hết hạn.

### Timeout không thay thế backpressure

Ngay cả khi mọi CompletableFuture có **orTimeout(...)**, các task nền vẫn có thể chạy sau khi caller đã bỏ kết quả. Khi số lượng task tăng nhanh, timeout ở phía kết quả có thể không giảm tải hệ thống ngoài.

Cần phối hợp:

- **Giới hạn concurrency**, ví dụ bằng Semaphore hoặc pool giới hạn kết nối.
- **Queue có sức chứa hữu hạn** hoặc chính sách từ chối.
- **Timeout tại tầng I/O** (network, database, HTTP client).
- **Cooperative cancellation** và cleanup.
- **Deadline của yêu cầu**.
- **Metrics** cho success, failure, timeout, cancel và task còn chạy sau timeout.

Virtual thread có thể làm chi phí chờ nhẹ hơn nhưng **không làm tài nguyên ngoài như socket, database connection hoặc rate limit trở nên vô hạn**.

## 23. Ví dụ tổng hợp chạy độc lập

Lưu chương trình dưới đây thành **AsyncFailureDemo.java**. Ví dụ dùng những future chưa hoàn tất thay cho một tác vụ ngủ lâu để mô phỏng timeout có kết quả dự đoán được, không phụ thuộc timing của thread nền.

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class AsyncFailureDemo {
    private AsyncFailureDemo() {}

    public static void main(String[] args) throws Exception {
        // 1. Phục hồi khi source lỗi.
        CompletableFuture<String> recovered =
                CompletableFuture.<String>failedFuture(
                                new IllegalStateException("service down"))
                        .thenApply(String::toUpperCase)
                        .exceptionally(error -> "cached");

        System.out.println("recovered=" + recovered.join());

        // 2. handle() chuyển lỗi thành kiểu kết quả khác.
        CompletableFuture<Integer> handled =
                CompletableFuture.<String>failedFuture(
                                new IllegalArgumentException("bad input"))
                        .handle((value, error) ->
                                error == null ? value.length() : 0);

        System.out.println("handled=" + handled.join());

        // 3. whenComplete() quan sát, giữ giá trị ban đầu.
        CompletableFuture<String> observed =
                CompletableFuture.completedFuture("OK")
                        .whenComplete((value, error) ->
                                System.out.println("observed=" + value));

        System.out.println("result=" + observed.join());

        // 4. Phục hồi bằng một future khác.
        CompletableFuture<String> backup =
                CompletableFuture.<String>failedFuture(
                                new IllegalStateException("remote down"))
                        .exceptionallyCompose(error ->
                                CompletableFuture.completedFuture("local"));

        System.out.println("backup=" + backup.join());

        // 5. Timeout tại get() không hoàn tất future.
        CompletableFuture<String> waiting = new CompletableFuture<>();

        try {
            waiting.get(20, TimeUnit.MILLISECONDS);
        } catch (TimeoutException exception) {
            System.out.println("get timeout, done=" + waiting.isDone());
        }

        // 6. orTimeout() hoàn tất chính future bằng TimeoutException.
        CompletableFuture<String> timed = new CompletableFuture<>();
        boolean sameInstance =
                timed.orTimeout(20, TimeUnit.MILLISECONDS) == timed;

        System.out.println("same-instance=" + sameInstance);

        try {
            timed.join();
        } catch (CompletionException exception) {
            System.out.println("orTimeout="
                    + (exception.getCause() instanceof TimeoutException));
        }

        // 7. completeOnTimeout() cung cấp giá trị dự phòng.
        CompletableFuture<String> fallback = new CompletableFuture<>();

        fallback.completeOnTimeout(
                "default", 20, TimeUnit.MILLISECONDS);

        System.out.println("completeOnTimeout=" + fallback.join());

        // 8. Cancel source và quan sát dependent stage.
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<Integer> dependent =
                source.thenApply(String::length);

        System.out.println("cancelled=" + source.cancel(true));

        try {
            source.join();
        } catch (CancellationException exception) {
            System.out.println("source cancelled");
        }

        try {
            dependent.join();
        } catch (CompletionException exception) {
            System.out.println("dependent-cause-is-cancellation="
                    + (exception.getCause()
                            instanceof CancellationException));
        }
    }
}
~~~

Kết quả dự kiến:

~~~text
recovered=cached
handled=0
observed=OK
result=OK
backup=local
get timeout, done=false
same-instance=true
orTimeout=true
completeOnTimeout=default
cancelled=true
source cancelled
dependent-cause-is-cancellation=true
~~~

Giải thích:

1. **thenApply(...)** không chạy khi source lỗi; **exceptionally(...)** cung cấp fallback.
2. **handle(...)** có thể chuyển lỗi thành giá trị thành công kiểu khác.
3. **whenComplete(...)** chỉ quan sát, không làm thay đổi giá trị thành công.
4. **exceptionallyCompose(...)** cung cấp một stage phục hồi riêng.
5. **get(timeout)** hết thời gian nhưng future nguồn vẫn chưa hoàn tất.
6. **orTimeout()** và **completeOnTimeout()** sửa trạng thái **chính future đó** nếu timeout thắng.
7. **cancel(true)** đánh dấu source là bị hủy, không chứng minh tác vụ nền nào đã bị interrupt.
8. Stage phụ thuộc không chạy hàm thành công và nhận đường hoàn tất ngoại lệ từ source.

Ví dụ không thực hiện mạng hoặc database. Trong hệ thống thật, phải bổ sung timeout I/O, quản lý task thực thi, quan sát lỗi và giải quyết side effect đúng theo hợp đồng.

## 24. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| **exceptionally(error -> null)** cho mọi lỗi | Lỗi bị che, null gây hỏng ở stage sau | Dùng fallback có nghĩa hoặc kiểu Result |
| Dùng **whenComplete()** để phục hồi | Không chuyển lỗi thành thành công | Dùng exceptionally/handle/exceptionallyCompose |
| Chỉ log message của exception | Mất cause và stack trace | Giữ Throwable cùng chuỗi nguyên nhân |
| Tưởng **get(timeout)** dừng task | Caller hết chờ nhưng task vẫn chạy | Dùng cơ chế cancellation/I/O timeout riêng |
| Áp **orTimeout()** lên future chia sẻ | Một caller có thể gây timeout cho caller khác | Tạo ranh giới completion riêng |
| Dùng **completeOnTimeout()** cho thao tác cần xác nhận chính xác | Biến “chưa biết kết quả” thành giá trị thành công giả | Thiết kế trạng thái unknown/pending |
| Tưởng **CompletableFuture.cancel(true)** ngắt thread | Boolean bị bỏ qua trong cơ chế interruption của CompletableFuture | Quản lý Future task hoặc cancellation token |
| Tưởng hủy một dependent stage sẽ hủy source | Không có propagation hai chiều tự động | Quản lý vòng đời toàn nhóm tác vụ |
| Retry ngay sau timeout ghi dữ liệu | Side effect có thể bị lặp | Dùng idempotency và kiểm tra trạng thái |
| Nuốt InterruptedException | Tác vụ khó dừng | Propagate hoặc restore interrupt |
| Dùng virtual thread để sửa race | Kiểu thread không thay đổi an toàn dữ liệu | Dùng đồng bộ và cấu trúc concurrent thích hợp |
| Đóng executor trong method trả future | **close()** có thể chờ tác vụ khiến API mất tính bất đồng bộ | Quản lý executor ở cấp service |
| Callback không Async thực hiện I/O chặn lâu | Làm chậm thread hoàn tất stage | Tách việc nặng qua executor phù hợp |
| Dùng **Thread.sleep()** để đợi hoàn tất | Không chứng minh công việc đã xong | Dùng Future.get/join/latch |
| Bỏ qua lỗi executor từ chối task | Callback/task không được lên lịch | Xử lý từ chối và vòng đời shutdown |

## 25. Checklist cho API bất đồng bộ Java 27

Trước khi công khai một method trả về **CompletableFuture<T>** hoặc dùng nó trong pipeline, kiểm tra:

- Kết quả thành công có được mô tả rõ? Null có hợp lệ không?
- Lỗi được phân loại thành **có thể khôi phục**, **không thể khôi phục** và **cancellation** chưa?
- Có dùng đúng **exceptionally()**, **handle()**, **whenComplete()**, **exceptionallyCompose()** theo mục đích?
- Các callback có giữ nguyên cause chain và thông tin chẩn đoán không?
- Timeout là giới hạn **thời gian chờ của caller** hay **trạng thái completion của future**?
- Có vô tình áp timeout lên một **future dùng chung** giữa nhiều caller không?
- Sau timeout, task nền và side effect có thể vẫn tiếp tục không?
- Nếu cần dừng tác vụ thật, có **Future thực thi**, cancellation token, interrupt hoặc I/O API phù hợp không?
- Task có kiểm tra tín hiệu hủy, giải phóng tài nguyên và tôn trọng InterruptedException không?
- Retry có **giới hạn, backoff, deadline và idempotency** không?
- allOf/anyOf có được dùng đúng semantics, không giả định tự hủy các task con không?
- Có giới hạn concurrency và backlog, ngay cả khi sử dụng virtual threads không?
- Executor nào chạy task và callback; ai sở hữu và đóng executor?
- Có timeout tương ứng trong tầng HTTP/database/file I/O không?
- Đã kiểm thử các đường thành công, lỗi, timeout, cancel, retry và shutdown chưa?

## Kết luận

Trong Java 27, **xử lý lỗi**, **timeout** và **cancellation** là ba cơ chế riêng. **exceptionally()** tạo giá trị phục hồi, **handle()** xử lý cả hai đường, **whenComplete()** quan sát, còn **exceptionallyCompose()** cho phép fallback bằng một tác vụ bất đồng bộ khác.

**get(timeout)** chỉ giới hạn thời gian chờ. **orTimeout()** và **completeOnTimeout()** có thể hoàn tất chính CompletableFuture sau thời hạn nhưng **không bảo đảm dừng công việc đang chạy**. Quan trọng hơn, **CompletableFuture.cancel(true)** không gửi interrupt tới thread tác vụ theo ý nghĩa của tham số boolean.

Một hệ thống bất đồng bộ đáng tin cần kết hợp **deadline, timeout thực ở tầng I/O, cancellation hợp tác, quản lý tài nguyên, giới hạn tải, retry an toàn và quan sát lỗi**. Trạng thái của CompletableFuture không phải là bằng chứng cuối cùng về những side effect đã hoặc chưa xảy ra ở hệ thống bên ngoài.
