# Gọi nhiều I/O giả lập bằng CompletableFuture với timeout

## 1. Mục tiêu bài tập

Bạn cần xây dựng một chương trình **Java concurrency thuần Java** thực hiện đồng thời nhiều lời gọi I/O giả lập, giới hạn thời gian chờ và tổng hợp kết quả. Bài tập không phụ thuộc vào Spring hay web framework.

Sau bài này, bạn phải làm được những việc sau:

1. Phân biệt thời gian **thực hiện tuần tự** với thời gian **chạy song song các công việc có thời gian chờ I/O**.
2. Dùng `CompletableFuture.supplyAsync(..., executor)` để gửi các tác vụ độc lập vào một executor do mình quản lý.
3. Ghép kết quả bằng `CompletableFuture.allOf(...)` hoặc `thenCombine(...)` mà không gọi `join()` bên trong từng supplier để vô tình tuần tự hóa.
4. Thiết lập timeout cho từng tác vụ và cho toàn bộ giai đoạn chờ, chọn giữa **fallback** và **lỗi rõ ràng**.
5. Phân biệt **future kết thúc do timeout** với **I/O nền đã dừng**.
6. Phân loại lỗi, bảo đảm cleanup executor và đo độ trễ tổng đúng cách.
7. Hiểu giới hạn của thread pool, số request đồng thời, queue và cách kiểm thử logic bất đồng bộ một cách ít phụ thuộc vào `Thread.sleep()`.

**Tình huống:** một màn hình tổng hợp dữ liệu cần ba kết quả độc lập: thông tin người dùng, giá sản phẩm và gợi ý. Mỗi nguồn dữ liệu được giả lập bằng một hàm chờ rồi trả chuỗi. Nguồn gợi ý chậm cần trả giá trị dự phòng sau timeout, còn hai nguồn quan trọng phải thành công. Đây là ví dụ concurrency trong Java nói chung; khi gọi I/O thật sẽ còn có timeout ở tầng kết nối/socket và giới hạn tài nguyên riêng.

## 2. Hiểu bài toán trước khi viết code

Giả sử thời gian I/O bình thường là:

| Tác vụ | Thời gian giả lập | Vai trò | Chính sách |
| --- | ---: | --- | --- |
| User | 100 ms | Bắt buộc | Nếu lỗi/timeout, toàn bài thất bại |
| Price | 150 ms | Bắt buộc | Nếu lỗi/timeout, toàn bài thất bại |
| Recommendation | 1.500 ms | Có thể thiếu | Sau 300 ms trả fallback |
| Tổng | Không cộng trực tiếp | Ba tác vụ độc lập | Chờ đến khi các kết quả cần thiết sẵn sàng |

Nếu thực hiện **tuần tự** và chờ cả ba kết quả thật, thời gian xấp xỉ `100 + 150 + 1500 = 1750 ms`, chưa kể chi phí scheduling và xử lý. Nếu khởi chạy cả ba công việc cùng lúc trong các worker có khả năng thực thi, rồi chấp nhận fallback sau 300 ms, thời gian để có kết quả của ba future xấp xỉ `max(100, 150, 300) = 300 ms`. Đây là **ước lượng lý tưởng**, không phải bảo đảm cứng: máy quá tải, queue, GC hoặc việc timeout bị lập lịch muộn đều làm số đo thay đổi.

Điều quan trọng là phân biệt ba thời điểm:

- **Tác vụ được gửi:** gọi `supplyAsync` tạo future và yêu cầu executor chạy supplier.
- **Tác vụ hoàn tất ở tầng CompletableFuture:** có giá trị, lỗi hoặc bị hoàn tất đặc biệt bởi timeout.
- **I/O nền thật sự dừng:** thread supplier đã trả về, bị ngắt có hiệu lực hoặc lời gọi I/O đã được hủy ở API gốc.

Ba thời điểm **không nhất thiết trùng nhau**. Ví dụ `completeOnTimeout("fallback", ...)` có thể hoàn tất future bằng fallback khi supplier đang tiếp tục chờ mạng.

### Sơ đồ luồng

~~~mermaid
flowchart TD
    A[Khởi tạo executor] --> B[Gửi User I/O]
    A --> C[Gửi Price I/O]
    A --> D[Gửi Recommendation I/O]
    B --> E[Future User]
    C --> F[Future Price]
    D --> G{Recommendation kịp 300 ms?}
    G -->|Có| H[Giá trị thật]
    G -->|Không| I[Fallback]
    E --> J[allOf]
    F --> J
    H --> J
    I --> J
    J --> K{Các nguồn bắt buộc thành công?}
    K -->|Có| L[Tổng hợp kết quả]
    K -->|Không| M[Báo lỗi và xử lý]
    L --> N[Đóng executor]
    M --> N
~~~

`allOf` chỉ là một future đại diện cho sự hoàn tất của các future đầu vào, **không tự tổng hợp kết quả**. Sau khi `allOf` hoàn tất bình thường, bạn lấy giá trị từ từng future. Nếu một future đầu vào hoàn tất lỗi, `allOf` cũng hoàn tất lỗi. Cần đặt fallback/handler trên tác vụ được phép suy giảm **trước khi đưa vào `allOf`** nếu muốn cả nhóm tiếp tục thành công.

## 3. Lời giải hoàn chỉnh: ba I/O chạy đồng thời, một fallback có timeout

Chương trình sau dùng Java 17+, `CompletableFuture` và một `ExecutorService` có ba worker. `Thread.sleep(...)` xuất hiện **chỉ bên trong hàm giả lập I/O có độ trễ**, không được dùng làm tín hiệu đồng bộ giữa các thread hay làm điều kiện kiểm thử. Với API thật, thay phần ngủ bằng lời gọi HTTP/file/database có timeout và chính sách hủy riêng.

Tạo file **`ParallelIoTimeoutDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ParallelIoTimeoutDemo {
    private static String fakeIo(String source, long millis) {
        try {
            Thread.sleep(millis); // Chỉ mô phỏng I/O chậm.
            return source + "-ok";
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(source + " interrupted", e);
        }
    }

    private static CompletableFuture<String> callAsync(
            String source, long millis, ExecutorService executor) {
        return CompletableFuture.supplyAsync(
                () -> fakeIo(source, millis), executor);
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService ioPool = Executors.newFixedThreadPool(3);
        long started = System.nanoTime();

        try {
            // Cả ba lệnh được gửi trước khi chờ kết quả.
            CompletableFuture<String> user =
                    callAsync("user", 100, ioPool)
                            .orTimeout(5, TimeUnit.SECONDS);

            CompletableFuture<String> price =
                    callAsync("price", 150, ioPool)
                            .orTimeout(5, TimeUnit.SECONDS);

            CompletableFuture<String> recommendation =
                    callAsync("recommendation", 1_500, ioPool)
                            .completeOnTimeout(
                                    "recommendation-fallback",
                                    300, TimeUnit.MILLISECONDS);

            CompletableFuture<Void> all =
                    CompletableFuture.allOf(user, price, recommendation);

            // Chỉ chặn thread main tại ranh giới lấy kết quả.
            all.join();

            System.out.println("User: " + user.join());
            System.out.println("Price: " + price.join());
            System.out.println(
                    "Recommendation: " + recommendation.join());

            double elapsedMs =
                    (System.nanoTime() - started) / 1_000_000.0;
            System.out.printf(java.util.Locale.ROOT,
                    "Elapsed: %.1f ms%n", elapsedMs);
        } catch (CompletionException e) {
            System.err.println("Required I/O failed: " + e.getCause());
            throw e;
        } finally {
            ioPool.shutdownNow();
            if (!ioPool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "I/O worker pool did not terminate");
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ParallelIoTimeoutDemo.java
java ParallelIoTimeoutDemo
~~~

**Ví dụ stdout trong điều kiện chạy bình thường:**

~~~text
User: user-ok
Price: price-ok
Recommendation: recommendation-fallback
Elapsed: 309.2 ms
~~~

Ba dòng giá trị được dự kiến như trên khi hai tác vụ bắt buộc hoàn thành trước timeout 5 giây và recommendation chậm hơn ngưỡng 300 ms. **Dòng `Elapsed` là số đo phụ thuộc máy, không phải output cố định**; trên CI cực chậm, thời điểm hoàn tất cũng có thể khác. Nếu xảy ra timeout 5 giây ở nguồn bắt buộc, chương trình báo lỗi thay vì in kết quả thành công.

### Phân tích từng đoạn

**`supplyAsync`** nhận supplier và một executor. Việc gọi nó **không chờ** hàm `fakeIo` trả về; nó tạo một future có thể được hoàn tất sau này. Ba lời gọi `callAsync` diễn ra trước `all.join()`, vì vậy không có chuỗi “xong user mới bắt đầu price”.

**`orTimeout(5, SECONDS)`** trên user/price: nếu future chưa hoàn tất trước deadline, nó được hoàn tất **exceptionally** bằng `TimeoutException`. Đây là chính sách fail-fast ở cấp kết quả cho nguồn bắt buộc; không có fallback tự động. Mốc 5 giây trong bài dùng để tránh treo mãi, không phải giá trị tối ưu cho một dịch vụ thật.

**`completeOnTimeout("recommendation-fallback", 300, MILLISECONDS)`**: nếu future còn chưa hoàn tất khi hết 300 ms, nó được hoàn tất bình thường bằng chuỗi fallback. Nếu recommendation trả kịp, nhận giá trị thật. Do đó nguồn tùy chọn không làm fail toàn bộ kết quả chỉ vì bị chậm.

**`allOf(user, price, recommendation)`** chờ cả ba future đạt trạng thái hoàn tất. Nó không biết về ý nghĩa “bắt buộc” hay “tùy chọn”; ý nghĩa đó đến từ chính sách xử lý từng future. Sau khi `all.join()` trả thành công, các `join()` để đọc kết quả từ ba future đã xong **không còn chờ I/O**.

**`System.nanoTime()`** được dùng đo thời gian trôi qua. Không dùng `System.currentTimeMillis()` cho đo khoảng thời gian ngắn vì wall-clock có thể bị điều chỉnh. Nếu benchmark, phải chạy warm-up, lặp nhiều lần và tách thêm queue wait/worker time; một lần chạy này chỉ để minh họa.

**`finally`** tắt pool để chương trình không giữ worker sống sau khi main kết thúc. `shutdownNow()` cố ngắt các worker còn chạy; `fakeIo` có cơ chế xử lý `InterruptedException`. Với I/O thật, interrupt có thể không hủy ngay một lời gọi blocking, vì vậy việc đóng connection/request và cấu hình timeout tầng I/O vẫn cần được thiết kế.

### Điều rất dễ hiểu sai về timeout

Cả `orTimeout` lẫn `completeOnTimeout` trong Java 9+ **thay đổi trạng thái hoàn tất của chính CompletableFuture đang gọi**, và trả lại cùng future đó. Chúng không tạo ra một tác vụ “có thể tự động bị interrupt” và cũng không bảo đảm supplier `fakeIo` đã dừng. Khi recommendation vượt 300 ms, future đã nhận fallback nhưng supplier có thể còn đang ngủ/chờ; trong ví dụ `shutdownNow()` lúc cuối mới cố ngắt nó.

Một số hệ quả:

- Nếu kết quả thật tới sau khi future đã hoàn tất bởi fallback, kết quả thật **không thay thế được** giá trị hoàn tất trước đó.
- `CompletableFuture.cancel(true)` hoàn tất future theo hướng hủy; tham số `mayInterruptIfRunning` của CompletableFuture **không điều khiển interrupt của công việc nền** theo cách một `FutureTask` thông thường có thể làm. Không dựa vào `cancel(true)` như cơ chế hủy socket/thread.
- Nếu pool rất nhỏ và queue dài, timeout có thể xảy ra **trước cả khi supplier bắt đầu chạy**; do đó cần quan sát backlog và giới hạn công việc nhận vào.
- Timer dùng cho timeout chỉ quyết định trạng thái future; deadline của toàn bộ thao tác ngoại vi phải đi vào client I/O thật nếu muốn tránh tài nguyên bị chiếm lâu.

## 4. `allOf` và `thenCombine`: chọn cách tổng hợp phù hợp

**`allOf`** phù hợp khi có N future, cần biết **toàn bộ** đã hoàn tất rồi lấy riêng từng giá trị:

~~~java
// Mảnh code: userFuture và priceFuture là CompletableFuture<String>.
CompletableFuture<Void> done =
        CompletableFuture.allOf(userFuture, priceFuture);
done.join();
String summary = userFuture.join() + " | " + priceFuture.join();
~~~

**`thenCombine`** phù hợp để kết hợp giá trị từ hai future mà không chặn thread gọi:

~~~java
// Mảnh code: hai future đã được gửi vào executor thích hợp.
CompletableFuture<String> combined =
        userFuture.thenCombine(priceFuture,
                (user, price) -> user + " | " + price);
String summary = combined.join(); // Chặn ở ranh giới cuối.
~~~

Có thể ghép tiếp: `user.thenCombine(price, ...).thenCombine(recommendation, ...)`. Với các future độc lập, mô hình này giữ sự song song vì phép combine chỉ được thực hiện khi cả hai input sẵn sàng.

**Tránh phản mẫu sau:**

~~~java
// Sai về ý tưởng chạy song song: chờ ngay sau khi gửi từng request.
String user = callAsync("user", 100, pool).join();
String price = callAsync("price", 150, pool).join();
String rec = callAsync("recommendation", 1_500, pool).join();
~~~

Dù mỗi tác vụ dùng `supplyAsync`, `join()` ngay sau mỗi lần gửi khiến các yêu cầu được **gửi tuần tự**: price chỉ được gửi sau khi user xong, recommendation chỉ được gửi sau khi price xong. Hãy tạo toàn bộ futures trước, rồi đợi chúng ở cuối.

Cũng tránh gọi `join` trong supplier/callback đang chạy trong **cùng một executor nhỏ** nếu công việc cần chờ lại nằm trong queue của executor đó. Hai worker đều chặn để đợi tác vụ thứ ba chưa được chạy có thể gây starvation hoặc deadlock. Dùng composition bằng `thenCompose`/`thenCombine`, hoặc điều chỉnh thiết kế scheduler để không giữ worker chỉ để chờ một future khác.

## 5. Hai chính sách timeout: fallback hay fail?

| API | Khi hết hạn | Dùng khi nào |
| --- | --- | --- |
| `orTimeout(t, unit)` | Hoàn tất future bằng `TimeoutException` | Nguồn bắt buộc phải báo lỗi nếu quá chậm |
| `completeOnTimeout(value, t, unit)` | Hoàn tất future bằng giá trị fallback | Nguồn tùy chọn có kết quả thay thế hợp lệ |
| `get(t, unit)` | **Thread gọi `get`** ném `TimeoutException` | Giới hạn thời gian một thread sẵn sàng chờ; không tự thay đổi trạng thái future |
| `join()` | Chờ vô hạn, hoặc trả kết quả/ném `CompletionException` | Chỉ nên dùng khi có timeout/lifecycle/deadline rõ bên ngoài |
| `get()` | Chờ vô hạn, ném `ExecutionException` khi tác vụ lỗi | Khi cần phân loại lỗi checked và đã có cơ chế giới hạn chờ |

Đặc biệt: `future.get(200, MILLISECONDS)` hết hạn **không làm future tự hoàn tất thất bại**, nên lần gọi `get` sau vẫn có thể nhận kết quả nếu I/O đến muộn. Ngược lại, `future.orTimeout(200, MILLISECONDS)` thực sự gắn cơ chế hoàn tất exceptionally vào future khi quá hạn.

### Ví dụ độc lập: kiểm tra rõ exception do timeout

Không cần ngủ hay I/O thực: ta tạo một future mà cố ý **không có ai hoàn tất**, sau đó yêu cầu timeout. Đây là cách cô lập và kiểm tra cơ chế timeout thay vì phỏng đoán lịch chạy của worker.

Lưu thành `TimeoutPolicyDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TimeoutPolicyDemo {
    public static void main(String[] args) {
        CompletableFuture<String> pending = new CompletableFuture<>();
        CompletableFuture<String> timed =
                pending.orTimeout(100, TimeUnit.MILLISECONDS);

        try {
            timed.join();
            throw new AssertionError("Expected timeout");
        } catch (CompletionException e) {
            if (!(e.getCause() instanceof TimeoutException)) {
                throw e;
            }
            System.out.println("Timeout detected");
        }

        CompletableFuture<String> optional = new CompletableFuture<>();
        String fallback = optional
                .completeOnTimeout("cached", 100, TimeUnit.MILLISECONDS)
                .join();
        System.out.println("Fallback: " + fallback);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac TimeoutPolicyDemo.java
java TimeoutPolicyDemo
~~~

Stdout:

~~~text
Timeout detected
Fallback: cached
~~~

Hai future trong demo không có supplier, do đó không có công việc I/O nền để hủy. `orTimeout` đi qua `CompletionException` khi dùng `join`; `get` thì dùng `ExecutionException` để bao nguyên nhân. Phân biệt **timeout được phát hiện** và **nguồn thật đã dừng** là phần rất quan trọng của thiết kế.

## 6. Per-task timeout và overall deadline không giống nhau

Giả sử mỗi nguồn có timeout 500 ms, nhưng màn hình phải hoàn thành toàn bộ trong 700 ms. Có hai giới hạn khác nhau:

1. **Per-task timeout**: một nguồn riêng lẻ không được chờ quá ngưỡng quy định. Ví dụ recommendation có thể dùng fallback sau 300 ms.
2. **Overall deadline**: tổng thời gian từ khi nhận yêu cầu tới khi trả kết quả không quá một ngân sách chung.

Nếu gửi ba tác vụ **tuần tự** và gọi `get(500 ms)` từng cái, tổng thời gian có thể đến 1.500 ms. Nếu gửi đồng thời, thời gian thường gần max của các task, nhưng vẫn phải tính thời gian khởi tạo, queue, callback và xử lý cuối. Khi cần deadline chính xác về mặt thiết kế, tính **thời gian còn lại từ một deadline chung** thay vì cấp lại ngân sách đầy đủ mỗi khi chờ.

Mảnh minh họa cho một caller đồng bộ có **deadline còn lại**:

~~~java
// Mảnh code: all là CompletableFuture<Void>, budgetNanos tùy SLO.
long deadline = System.nanoTime() + budgetNanos;
long remaining = deadline - System.nanoTime();
if (remaining <= 0L) {
    throw new java.util.concurrent.TimeoutException("Budget exceeded");
}
all.get(remaining, java.util.concurrent.TimeUnit.NANOSECONDS);
~~~

Dùng `System.nanoTime()` để đo hiệu khoảng thời gian; với deadline cực dài, cần xét overflow, nhưng ngân sách tính bằng giây/phút trong test thường không gặp. Nếu có nhiều giai đoạn chờ, tính lại `remaining` trước mỗi lần chờ. Mốc `deadline` này giới hạn **thời gian caller chờ**, không tự động hủy các request đã gửi. Hãy chuyển deadline xuống cơ chế timeout của client I/O thực và chủ động cleanup khi quá hạn.

Một lỗi tinh vi là gắn `allOf(...).orTimeout(totalBudget)` rồi coi như mọi I/O bị hủy. Future tổng chỉ hoàn tất exceptionally; các futures con vẫn có thể chạy. Một lỗi khác là chỉ đặt timeout ở `get` trên thread main nhưng để executor không có chính sách hoàn tất và không có cleanup, khiến worker bị kẹt sau khi test kết thúc.

## 7. Xử lý lỗi khi một trong nhiều I/O thất bại

Khi các tác vụ có mức độ quan trọng khác nhau, cần nêu trước chính sách:

- **Nguồn bắt buộc:** có lỗi thì yêu cầu tổng bị lỗi; không hiển thị kết quả giả như thể dữ liệu thật.
- **Nguồn tùy chọn:** có thể thay bằng fallback, giá trị cache hoặc trạng thái “không có dữ liệu”, nhưng phải nhận diện kết quả suy giảm.
- **Một nguồn lỗi không nên làm mất thông tin lỗi của nguồn khác:** ghi nguồn nào thất bại và lý do; không nuốt mọi exception rồi báo thành công.

Các thao tác xử lý lỗi thường dùng:

| Phương thức | Công dụng | Lưu ý |
| --- | --- | --- |
| `exceptionally(ex -> fallback)` | Khi upstream lỗi, cung cấp fallback cùng kiểu | Bao gồm lỗi timeout/cancellation nếu không phân loại |
| `handle((value, ex) -> ...)` | Xử lý cả kết quả và lỗi, chuyển thành kiểu mới | Được gọi trong cả hai trường hợp |
| `whenComplete((value, ex) -> ...)` | Quan sát/log/metric khi hoàn tất | Thường bảo toàn kết quả hoặc lỗi gốc nếu callback không lỗi |
| `exceptionallyCompose(...)` | Khôi phục bằng một future khác (Java 12+) | Phù hợp khi fallback cũng bất đồng bộ |
| `thenCompose(value -> nextFuture)` | Ghép công việc phụ thuộc dữ liệu trước | Tránh `thenApply` tạo future lồng nhau |

Ví dụ một nguồn **có fallback khi bất kỳ lỗi nào**:

~~~java
// Mảnh code: sourceFuture là CompletableFuture<String>.
CompletableFuture<String> safe =
        sourceFuture.exceptionally(ex -> "unavailable");
~~~

Lưu ý fallback chung có thể vô tình giấu bug lập trình (`NullPointerException`), lỗi quyền truy cập hoặc dữ liệu sai. Trong code thực, phân loại ngoại lệ và chỉ fallback các lỗi đã định nghĩa. Nếu yêu cầu kiểm toán hay correctness quan trọng, thà fail rõ ràng hơn là thay kết quả mà không thông báo.

**Ngoại lệ trong CompletableFuture:** `join()` ném `CompletionException` (unchecked) khi pipeline thất bại; `get()` ném `ExecutionException` (checked). Cần xem `getCause()`/unwrap đúng lớp bao, và giữ interrupt đúng quy tắc khi dùng `get`. `allOf` khi có một hoặc nhiều future lỗi chỉ biểu diễn lỗi tổng; không mặc định cung cấp danh sách tất cả các nguồn lỗi. Muốn một báo cáo đầy đủ, chuẩn hóa từng kết quả thành record có trạng thái/thời lượng/lỗi rồi tổng hợp.

## 8. Giới hạn tài nguyên: chạy song song có chi phí

Ở ví dụ trên, `Executors.newFixedThreadPool(3)` tạo pool ba **platform thread**. Giả lập I/O bằng `Thread.sleep` khiến worker bị chiếm khi đang chờ. Với 3 việc và 3 worker, các task có thể chạy song song. Với 1.000 việc và 3 worker, phần lớn phải vào queue, khiến latency tổng tăng mạnh.

**Đặc biệt:** `Executors.newFixedThreadPool` dùng queue không giới hạn theo thiết kế mặc định; đây là API gọn cho bài tập nhưng **không phải lựa chọn an toàn tự động** cho nguồn tải sản xuất không giới hạn. Ở ứng dụng lớn, cân nhắc `ThreadPoolExecutor` có queue hữu hạn, chính sách rejection/backpressure, timeout ở API ngoại vi và giới hạn số request đồng thời.

Ví dụ cấu hình pool có hàng đợi hữu hạn:

~~~java
// Mảnh code cấu hình thay thế: phải shutdown đúng lifecycle.
java.util.concurrent.ThreadPoolExecutor bounded =
        new java.util.concurrent.ThreadPoolExecutor(
                3, 3,
                0L, java.util.concurrent.TimeUnit.MILLISECONDS,
                new java.util.concurrent.ArrayBlockingQueue<>(12),
                new java.util.concurrent.ThreadPoolExecutor.AbortPolicy());
~~~

`AbortPolicy` từ chối khi full bằng `RejectedExecutionException`. Nếu xảy ra ở `CompletableFuture.supplyAsync` lúc gửi việc, exception có thể được ném ngay tại thao tác submit, trước khi một future được trả về. Caller phải xử lý overload thay vì coi đây là một tương lai chắc chắn hoàn tất. Queue quá dài có thể làm future hết timeout **trong lúc chưa bắt đầu làm I/O**.

Không mặc định dùng `CompletableFuture.supplyAsync(supplier)` không truyền executor trong bài này: overload mặc định thường dùng `ForkJoinPool.commonPool()`, nơi các công việc khác trong JVM cũng có thể chia sẻ tài nguyên. Các tác vụ blocking I/O lâu trên common pool có thể làm chậm những công việc không liên quan. Truyền executor rõ ràng giúp quản lý số worker, giới hạn tài nguyên và cleanup.

Java 21 có **virtual threads**, có thể hữu ích với nhiều lời gọi I/O blocking. Tuy nhiên virtual threads không tăng năng lực backend và không thay thế giới hạn kết nối, deadline hay backpressure. Bài tập này dùng Java 17 để dễ chạy trong nhiều môi trường; khi nâng JDK, có thể thử executor virtual thread cho workload blocking nhưng vẫn phải giới hạn số request tới nguồn bên ngoài và đo hiệu năng.

## 9. Cách kiểm thử không phụ thuộc vào timing giả lập

`Thread.sleep` ở `fakeIo` là **mô hình thời gian chờ I/O** cho bài thực hành, không phải cách đảm bảo test đồng bộ đúng. Với bài kiểm thử logic phối hợp futures, bạn có thể dùng các `CompletableFuture` chưa hoàn tất và chủ động gọi `complete`/`completeExceptionally` để kiểm soát thứ tự.

Ví dụ giả lập kết quả đến trễ **mà không ngủ**:

~~~java
// Mảnh code kiểm thử orchestration.
CompletableFuture<String> user = new CompletableFuture<>();
CompletableFuture<String> price = new CompletableFuture<>();

CompletableFuture<String> combined =
        user.thenCombine(price, (u, p) -> u + "/" + p);

user.complete("alice");
if (combined.isDone()) {
    throw new AssertionError("Must still wait for price");
}

price.complete("120");
if (!"alice/120".equals(combined.join())) {
    throw new AssertionError("Incorrect aggregation");
}
~~~

Kết quả này được quyết định bởi **tín hiệu `complete` rõ ràng**, không phụ thuộc tốc độ scheduler. Tương tự, `completeExceptionally` cho phép kiểm tra nhánh lỗi, và future không bao giờ hoàn tất giúp kiểm tra timeout như `TimeoutPolicyDemo`.

Đối với integration test dùng I/O thật, có thể thêm độ trễ có kiểm soát trong fake server, điều chỉnh transport timeout, dùng `CountDownLatch` để xác nhận công việc đã bắt đầu rồi mới giải phóng. Hãy dùng timeout hữu hạn với các lệnh `get/await` và đóng executor/network client trong `finally`. Tránh assertion kiểu “ngủ 200 ms rồi hy vọng request đã xong” — đó là nguồn gây flaky test.

### Những quan sát nên đo

- Thời gian từ **trước khi gửi nhóm công việc** đến khi tổng hợp xong.
- Thời gian riêng từng nguồn: request được gửi, bắt đầu, hoàn tất; queue wait nếu đáng kể.
- Số task thành công, lỗi, timeout, fallback; không trộn fallback với kết quả thật trong thống kê.
- Số worker đang bận, số tác vụ chờ, số tác vụ đang chạy **sau khi future timeout**.
- Độ trễ p95/p99 và completion rate qua nhiều vòng; một phép đo `Elapsed` không đủ làm benchmark.

## 10. Bài tập mở rộng có tiêu chí chấp nhận

**Bài A — Tự ghép kết quả theo record.** Thay chuỗi riêng lẻ bằng `record Dashboard(String user, String price, String recommendation, boolean degraded)`. Khi recommendation timeout, đặt `degraded = true`; còn khi nhận giá trị thật, đặt false. Không được suy diễn degraded từ chuỗi tên fallback trong code production; nên có kiểu kết quả mô tả rõ trạng thái.

**Bài B — Kiểm tra một nguồn lỗi.** Sửa `fakeIo` để nguồn price ném exception và xác minh chương trình không in bảng kết quả thành công. Đặt handler chỉ cho recommendation và thử thêm lỗi recommendation để thấy fallback; tuyệt đối không nuốt lỗi của nguồn bắt buộc.

**Bài C — Chia timeout riêng và chung.** Cho recommendation timeout sau 300 ms; hai nguồn bắt buộc có per-task timeout phù hợp; thêm overall deadline 1 giây. Kiểm tra trường hợp một future thực hiện quá lâu hoặc queue nghẽn. Đảm bảo khi deadline tổng hết, chương trình báo lỗi và cleanup mọi tài nguyên cần quản lý.

**Bài D — Thử một pool nhỏ.** Giảm executor xuống 1 worker và quan sát cả ba task dù gửi đồng thời cũng sẽ **bị tuần tự hóa tại executor**; recommendation có thể timeout khi còn nằm trong queue. So sánh thời gian, trạng thái thực thi và giải thích tại sao gửi đồng thời chưa đủ khi năng lực worker nhỏ.

**Bài E — Giới hạn tải.** Thay fixed pool bằng bounded `ThreadPoolExecutor`, gửi nhiều lượt nhóm I/O; thử giới hạn queue và xử lý `RejectedExecutionException` một cách có kiểm soát. Không retry vô hạn; báo rõ số request accepted/rejected và thời gian queue.

**Bài F — Viết test deterministic.** Không sleep để đoán future đã xong. Dùng các `CompletableFuture` do test sở hữu để chủ động hoàn tất user/price/recommendation và kiểm tra `allOf`, `thenCombine`, fallback và xử lý lỗi. Với kiểm thử thời gian thực, dùng ngưỡng đủ rộng và cảnh báo nếu CI quá tải.

### Tiêu chí hoàn thành

- Gửi cả ba request trước khi đợi kết quả; không `join` ngay sau từng lần `supplyAsync`.
- Tách nguồn bắt buộc với nguồn tùy chọn; fallback chỉ nơi phù hợp.
- Có timeout hữu hạn, xử lý lỗi và quản lý lifecycle executor.
- Mô tả đúng ý nghĩa timeout: **future có thể hoàn tất trong khi supplier/I/O vẫn đang chạy**.
- Kết quả không phụ thuộc thứ tự callback in log; thứ tự hiển thị được quyết định ở bước tổng hợp.
- Có số đo thời gian thực tế và giải thích được vì sao nó khác tổng thời gian I/O tuần tự.
- Khi mở rộng sang nhiều yêu cầu, có giới hạn tài nguyên và số công việc đồng thời.

## 11. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `supplyAsync(...).join()` ngay sau từng lần gọi | Vô tình thực hiện tuần tự | Tạo toàn bộ futures trước, rồi tổng hợp/chờ cuối |
| Không truyền executor cho blocking I/O | Có thể làm nghẽn common pool | Dùng executor I/O riêng có giới hạn |
| Tin `orTimeout` sẽ ngắt thread đang I/O | Rò tài nguyên khi request nền vẫn chạy | Cấu hình timeout/hủy ở client I/O gốc, cleanup rõ ràng |
| `allOf` bị lỗi vì một nguồn tùy chọn | Mất cả bảng kết quả dù có fallback | Gắn fallback đúng nguồn trước khi gộp |
| `exceptionally` trả giá trị dự phòng cho mọi lỗi | Che giấu bug hoặc dữ liệu sai | Phân loại lỗi, giữ nguyên lỗi nguồn bắt buộc |
| `get(500ms)` từng future rồi coi là tổng deadline 500ms | Chờ tổng vượt ngân sách | Tính `remaining` từ deadline chung |
| Dùng pool một worker cho ba I/O blocking | Các tác vụ bị xếp hàng | Chọn số worker/loại concurrency theo workload, đo queue |
| Queue executor không giới hạn | Tăng backlog, memory, timeout | Bounded queue, rejection/backpressure |
| Chỉ nhìn `Elapsed` một lần | Nhầm kết quả demo với benchmark | Warm-up, đo nhiều vòng, latency/throughput/fallback rate |
| `Thread.sleep` trong test để “chờ hoàn thành” | Flaky hoặc pass giả | `Future.get`, latch, barrier, explicit completion |
| Bỏ qua `shutdown`/interrupt | Thread còn chạy, chương trình khó thoát | `try/finally`, shutdown, chờ termination |
| Coi fallback là kết quả nguồn thật | Metric và quyết định nghiệp vụ sai | Phân biệt trạng thái degraded/cache/timeout |

## 12. Câu hỏi tự kiểm tra

**1. Vì sao `allOf` không cho trực tiếp `List<String>`?** Nó trả `CompletableFuture<Void>` thể hiện thời điểm tất cả future đã hoàn tất; giá trị nằm trên từng future. Muốn một object kết quả, kết hợp các giá trị sau khi mọi future liên quan sẵn sàng hoặc dùng chuỗi `thenCombine`.

**2. `completeOnTimeout` có thể trả fallback khi supplier chưa từng bắt đầu không?** Có. Timeout tính từ khi gắn với future, trong khi supplier có thể còn đợi trong queue executor.

**3. `get(timeout)` khác `orTimeout` thế nào?** `get(timeout)` giới hạn việc **thread gọi đợi** và không tự hoàn tất future; `orTimeout` khiến future hoàn tất exceptionally khi deadline đến, dù thread chờ hay không.

**4. Tại sao `cancel(true)` trên `CompletableFuture` không được xem là bảo đảm ngắt supplier?** Vì trạng thái hủy future và việc kiểm soát thực thi tác vụ nền là hai cơ chế khác nhau; `CompletableFuture` không trực tiếp sở hữu một `FutureTask` để bảo đảm interrupt như một số API executor.

**5. Khi ba I/O độc lập cùng chạy, thời gian tổng luôn bằng max thời gian từng I/O không?** Không. Đây chỉ là xấp xỉ trong điều kiện các tác vụ thực sự được lên lịch đồng thời, pool đủ năng lực, không có queue lớn và overhead thấp. Timeout/fallback có thể làm thời gian lấy *kết quả được chấp nhận* ngắn hơn thời gian I/O thật.

**6. Nếu một nguồn bắt buộc thất bại, nên trả một bảng đã đủ dữ liệu không?** Chỉ nếu nghiệp vụ định nghĩa chế độ suy giảm đó là hợp lệ. Trong bài này user/price là bắt buộc, nên phải báo lỗi và cleanup thay vì cố coi kết quả thiếu là thành công.

**7. Có nên thay tất cả `Thread.sleep` bằng `CompletableFuture` không?** Không. `sleep` có thể được dùng để mô phỏng latency trong bài tập; vấn đề là dùng sleep làm **điều kiện xác nhận đồng bộ** hoặc thiết kế concurrency vô hạn. Với I/O thật, sử dụng client và timeout tương ứng.

**Điểm cốt lõi:** `CompletableFuture` cho phép khởi chạy, phối hợp, chuyển đổi và xử lý kết quả bất đồng bộ. Muốn gọi nhiều I/O hiệu quả, phải **gửi tất cả công việc trước**, **phân biệt timeout với hủy tác vụ nền**, **giới hạn tài nguyên**, và **quy định trước chính sách thất bại/fallback** cho từng nguồn.