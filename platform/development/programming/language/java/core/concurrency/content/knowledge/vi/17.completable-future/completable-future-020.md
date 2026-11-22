# exceptionallyCompose(): phục hồi bằng một CompletionStage bất đồng bộ

## 1. Khi phục hồi lỗi cũng là một công việc bất đồng bộ

Trong một pipeline Java `CompletableFuture<T>`, một bước có thể **hoàn tất thành công** với giá trị `T` hoặc **hoàn tất bất thường** do exception, cancellation, timeout được chủ động thiết lập, v.v. Nếu một công việc chính thất bại, nhiều hệ thống cần thực hiện **một bước bất đồng bộ khác** để phục hồi:

- Nguồn dữ liệu chính không hoạt động, thử dịch vụ dự phòng.
- Một lần gọi tới dependency thất bại tạm thời, khởi tạo lần thử lại với giới hạn.
- Không đọc được bản ghi, thực hiện truy vấn bất đồng bộ sang kho khác.
- Một phép tính phân tán thất bại, chuyển sang một đường xử lý dự phòng và chờ kết quả thật của đường đó.

`exceptionallyCompose` giải quyết chính bài toán này: **khi stage hiện tại thất bại, gọi hàm nhận lỗi, hàm đó trả về một `CompletionStage<T>` mới, rồi nối (compose/flatten) kết quả của stage phục hồi vào pipeline**.

```text
                  ┌─ thành công: T ────────────────────┐
primaryStage ─────┤                                     ├─> result: T
                  └─ thất bại: Throwable ──────────────┤
                                            │           │
                                            ▼           │
                                  exceptionallyCompose  │
                                            │           │
                                            ▼           │
                                fallbackStage: T ───────┘
                                   /         \
                             thành công     thất bại
                              → result T     → result lỗi
```

**Điểm cốt lõi:** `exceptionallyCompose` không biến mọi lỗi thành kết quả hợp lệ. Nó chỉ tạo cơ hội phục hồi bằng một stage khác; nếu stage dự phòng cũng thất bại, kết quả cuối vẫn thất bại. Bài học thuộc phạm vi **Java Concurrency thuần JDK**, không phụ thuộc framework.

## 2. API và yêu cầu phiên bản Java

`exceptionallyCompose` được thêm vào `CompletionStage` từ **Java 12** và có sẵn trong Java 17. Ba overload quan trọng khi gọi trên `CompletableFuture<T>`:

```java
CompletableFuture<T> exceptionallyCompose(
        Function<Throwable, ? extends CompletionStage<T>> fn);

CompletableFuture<T> exceptionallyComposeAsync(
        Function<Throwable, ? extends CompletionStage<T>> fn);

CompletableFuture<T> exceptionallyComposeAsync(
        Function<Throwable, ? extends CompletionStage<T>> fn,
        Executor executor);
```

Đây là **chữ ký API minh họa**, không phải chương trình biên dịch độc lập. Với biến tĩnh kiểu `CompletionStage<T>`, các phương thức tương ứng trả `CompletionStage<T>`; với biến kiểu `CompletableFuture<T>`, phương thức được implement trả `CompletableFuture<T>`.

Các thành phần:

- `T`: **cùng một kiểu kết quả** trước và sau phục hồi. Ví dụ, nếu nguồn có kiểu `CompletableFuture<Order>`, hàm phục hồi cần trả một stage cho `Order`, không phải `CompletionStage<String>` khi chưa chuyển kiểu.
- `Throwable`: ngoại lệ biểu diễn nguyên nhân hoàn tất bất thường của nguồn. Nó có thể là exception gốc hoặc một `CompletionException` bọc nguyên nhân; không mặc định nó luôn chính xác là lớp exception ứng dụng đã ném.
- `Function<Throwable, ? extends CompletionStage<T>>`: hàm dựng/khởi chạy **stage phục hồi**, không trả giá trị `T` trực tiếp.
- `Async`: nói về **cách thực thi callback tạo stage phục hồi**, không nhất thiết nói về executor chạy toàn bộ nghiệp vụ bên trong stage được trả về.

`exceptionallyCompose` được gọi lúc **xây dựng graph**; hàm `fn` chỉ được kích hoạt khi nguồn hoàn tất **exceptionally**. Nếu nguồn đã thành công, stage mới tiếp tục mang kết quả đó và callback phục hồi không chạy.

### Kiểu trả về: tránh nested CompletableFuture

Ý tưởng tương đương với “flatMap trên nhánh lỗi”:

```java
CompletableFuture<String> recovered =
        primary.exceptionallyCompose(error ->
                CompletableFuture.supplyAsync(() -> "from backup", executor));
```

`primary` là một `CompletableFuture<String>` và `executor` do ứng dụng khai báo; đây là fragment minh họa. Kết quả có kiểu **`CompletableFuture<String>`**, không phải `CompletableFuture<CompletableFuture<String>>`. Stage mới chờ cho stage từ callback hoàn tất, rồi lấy **giá trị hoặc lỗi của stage đó** làm completion của mình.

Vì vậy, nếu callback trả về một `CompletionStage<T>` đang pending, stage phục hồi cũng **chưa hoàn tất** cho đến khi stage đó hoàn tất. Không có lời hứa callback phải tạo một task trên thread mới; callback có thể trả `completedFuture` hoặc `failedFuture` ngay.

## 3. So sánh exceptionally(), exceptionallyCompose() và thenCompose()

| API | Chạy khi nào? | Callback trả gì? | Kết quả |
| --- | --- | --- | --- |
| `exceptionally(error -> fallbackValue)` | Nguồn thất bại | Một **giá trị T** | Stage mới hoàn tất với fallback value |
| `exceptionallyCompose(error -> fallbackStage)` | Nguồn thất bại | Một **CompletionStage<T>** | Stage mới hoàn tất theo kết quả/lỗi của fallback stage |
| `thenCompose(value -> nextStage)` | Nguồn thành công | Một **CompletionStage<U>** | Stage mới hoàn tất theo stage kế tiếp |
| `handle((value, error) -> result)` | Nguồn thành công **hoặc** thất bại | Một **giá trị U** | Stage mới mang giá trị callback trả về, hoặc lỗi do callback ném |
| `whenComplete((value, error) -> ...)` | Nguồn thành công hoặc thất bại | Không trả giá trị; callback quan sát | Thường giữ outcome gốc, không dành để chuyển lỗi thành giá trị |
| `exceptionallyAsync(error -> value, executor)` | Nguồn thất bại | Một **giá trị T**, callback async | Không phải compose stage; có từ Java 12 |

Nếu lỗi có thể được khôi phục **ngay lập tức** từ dữ liệu có sẵn, `exceptionally` đơn giản hơn:

```java
CompletableFuture<String> value =
        primary.exceptionally(error -> "cached");
```

Nếu phải **gọi thêm một tác vụ bất đồng bộ** và chỉ có thể trả kết quả sau khi tác vụ ấy xong, dùng `exceptionallyCompose`:

```java
CompletableFuture<String> value =
        primary.exceptionallyCompose(error ->
                CompletableFuture.supplyAsync(
                        () -> loadBackup(), backupExecutor));
```

Hai fragment giả định `primary` có kiểu `CompletableFuture<String>`; `loadBackup` và `backupExecutor` là thành phần do ứng dụng khai báo.

**Đừng** dùng `thenCompose` để phục hồi một nguồn đã fail: `thenCompose` chỉ chạy callback khi nguồn **thành công**, vì thế callback dự phòng trong nhánh `thenCompose` sẽ bị bỏ qua khi nguồn failed.

## 4. Ví dụ Java 17 chạy độc lập: nguồn chính lỗi, dùng nguồn dự phòng

Chương trình sau cố ý tạo một nguồn chính bị lỗi, rồi phục hồi bằng `CompletableFuture.supplyAsync` trên một executor riêng. Chương trình còn chứng minh rằng callback phục hồi không chạy khi nguồn chính thành công, và lỗi của future gốc **không bị sửa đổi** bởi nhánh phục hồi.

Lưu file **`ExceptionallyComposeDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ExceptionallyComposeDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService backupPool = Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<String> primary =
                    CompletableFuture.failedFuture(
                            new IllegalStateException("primary offline"));

            CompletableFuture<String> recovered =
                    primary.exceptionallyCompose(error ->
                            CompletableFuture.supplyAsync(
                                    () -> "backup:OK", backupPool));

            System.out.println("Recovered: " + recovered.join());
            System.out.println("Original failed: "
                    + primary.isCompletedExceptionally());

            AtomicBoolean fallbackCalled = new AtomicBoolean(false);
            CompletableFuture<String> healthy =
                    CompletableFuture.completedFuture("primary:OK");

            CompletableFuture<String> unchanged =
                    healthy.exceptionallyCompose(error -> {
                        fallbackCalled.set(true);
                        return CompletableFuture.completedFuture("backup:OK");
                    });

            System.out.println("Healthy: " + unchanged.join());
            System.out.println("Fallback called: " + fallbackCalled.get());
        } finally {
            backupPool.shutdown();
            if (!backupPool.awaitTermination(5, TimeUnit.SECONDS)) {
                backupPool.shutdownNow();
            }
        }
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac ExceptionallyComposeDemo.java
java ExceptionallyComposeDemo
```

Stdout xác định trong lần chạy thành công:

```text
Recovered: backup:OK
Original failed: true
Healthy: primary:OK
Fallback called: false
```

Giải thích:

1. `failedFuture` tạo `primary` ở trạng thái exceptional ngay từ đầu.
2. `exceptionallyCompose` tạo **future mới** `recovered` và gọi hàm phục hồi với lỗi của `primary`.
3. Callback tạo `CompletableFuture.supplyAsync(...)`, lập lịch công việc dự phòng trên `backupPool`.
4. `recovered.join()` chỉ trả khi fallback stage đã hoàn thành bằng `"backup:OK"`.
5. `primary.isCompletedExceptionally()` vẫn `true`: pipeline phục hồi **không xóa lỗi của future gốc**.
6. Future `healthy` đã thành công nên callback của `exceptionallyCompose` không được gọi; biến `fallbackCalled` vẫn `false`.

Không có lệnh in trong callback hoặc worker, nên thứ tự stdout không phụ thuộc lịch chạy executor. `backupPool.shutdown()` được gọi trong `finally`, tránh bỏ quên thread. Một giá trị do `supplyAsync` sinh ra có thể đến nhanh hoặc chậm, nhưng `join()` đợi tới khi nó sẵn sàng.

## 5. Bảng outcome: điều gì xảy ra ở từng nhánh?

| Outcome của nguồn | Callback phục hồi | Outcome của future trả về |
| --- | --- | --- |
| Nguồn thành công với `T` | **Không gọi** | Thành công với đúng giá trị `T` |
| Nguồn thành công với `null` | **Không gọi** | Thành công với `null` |
| Nguồn thất bại; callback trả stage thành công với `T` | Được gọi | Thành công với `T` từ stage fallback |
| Nguồn thất bại; callback trả stage cũng thất bại | Được gọi | Thất bại theo outcome của stage fallback |
| Nguồn thất bại; callback ném exception | Được gọi | Stage tổng hợp thất bại do callback |
| Nguồn thất bại; callback trả `null` thay vì stage | Được gọi | Không tạo được stage hợp lệ; dependent hoàn tất bất thường |
| Nguồn bị `cancel(...)` | Đây là exceptional completion | Có thể gọi callback và tạo fallback; cần chính sách rõ |
| Nguồn chưa hoàn tất | Chưa được gọi | Stage phụ thuộc vẫn chờ |

**“Phục hồi bất đồng bộ” không đồng nghĩa “luôn thành công”.** Fallback có thể thất bại, treo hoặc hết deadline. Code phải quyết định xử lý lỗi thứ hai và có giới hạn thời gian/hủy ở các dependency thực sự.

Có thể quan sát outcome bằng `join()` hoặc `get()` ở ranh giới cần lấy giá trị:

- `join()` thường ném `CompletionException` nếu stage exceptional; nếu chính future bị hủy, có thể ném `CancellationException` trực tiếp.
- `get()` khai báo `ExecutionException` và `InterruptedException`; có thể ném `CancellationException`.
- `get(timeout,unit)` thêm `TimeoutException` khi đợi quá thời gian, **không tự thay đổi trạng thái future hoặc hủy tác vụ**.

Nếu một future phụ thuộc vào một nguồn bị hủy, exception có thể đến dưới dạng `CompletionException` bọc `CancellationException`. Do đó, khi phân loại, hãy xem cause, không chỉ so sánh class của exception bề mặt.

## 6. exceptionallyComposeAsync: callback được thực thi thế nào?

Ba overload cung cấp cùng ý nghĩa **phục hồi bằng stage khác** nhưng khác nơi chạy callback nhận exception.

### 6.1. exceptionallyCompose(fn)

Callback không mặc nhiên được nộp vào executor riêng. Theo chính sách các non-Async dependent của `CompletableFuture`, callback có thể chạy trên thread đang hoàn tất stage nguồn hoặc thread tham gia completion; nếu nguồn đã completed, callback có thể chạy ngay trong thread gọi gắn stage. **Không nên phụ thuộc tên thread**.

Phù hợp khi callback rất nhẹ: kiểm tra loại lỗi, chọn nhánh fallback và **trả về một stage** mà không block.

### 6.2. exceptionallyComposeAsync(fn)

Callback được thực thi bằng default asynchronous execution facility của stage. Với `CompletableFuture` chuẩn, thường dùng `ForkJoinPool.commonPool()`; một số môi trường/triển khai có thể dùng chiến lược fallback. Không nên mặc định rằng common pool là nơi phù hợp cho I/O blocking dài.

### 6.3. exceptionallyComposeAsync(fn, executor)

Callback được lập lịch trên `Executor` được cung cấp. Lựa chọn này giúp kiểm soát nơi quyết định fallback, chính sách queue/capacity và vòng đời executor:

```java
CompletableFuture<String> recovered =
        primary.exceptionallyComposeAsync(
                error -> loadFromBackupAsync(),
                callbackExecutor);
```

Đoạn này là fragment; `loadFromBackupAsync()` cần trả `CompletionStage<String>`, còn `callbackExecutor` được ứng dụng cấu hình. **Lưu ý then chốt:** executor của overload này dùng để chạy **hàm callback**, không nhất thiết là executor nội bộ mà `loadFromBackupAsync` sử dụng. Nếu callback tạo `supplyAsync(..., otherExecutor)`, task dự phòng chạy trên `otherExecutor`.

### Không dùng Async để giả định có thêm song song

Việc gọi `exceptionallyComposeAsync` chỉ có ý nghĩa sau khi có lỗi. Nó không biến nguồn chính thành asynchronous, không tự tạo retry và không nâng throughput nếu recovery thực chất chỉ trả `completedFuture("fallback")`. Trong trường hợp callback nhẹ, scheduling bổ sung còn có thể gây overhead.

Nếu callback phải thực hiện I/O chặn, tốt hơn là nó **khởi tạo** công việc bất đồng bộ rồi trả stage ngay, thay vì chiếm worker callback để chờ `get()`/`join()`.

## 7. Sự khác biệt quan trọng: trả stage, không chờ stage

Mẫu sai:

```java
// Fragment không nên dùng: đợi fallback ngay trong callback.
CompletableFuture<String> result =
        primary.exceptionally(error ->
                loadFromBackupAsync().toCompletableFuture().join());
```

`exceptionally` yêu cầu callback **trả `String`**, nên code này block bằng `join()` cho tới khi fallback xong. Nếu callback chạy trên pool hạn chế thread và fallback cần chính pool ấy, việc block có thể làm tăng latency, gây thread starvation hoặc deadlock.

Cách diễn đạt đúng:

```java
CompletableFuture<String> result =
        primary.exceptionallyCompose(error -> loadFromBackupAsync());
```

Callback **trả stage** và pipeline tiếp tục theo completion của stage ấy. Không chiếm thread chỉ để đợi trong callback. Hai snippet giả định `primary` là `CompletableFuture<String>` và `loadFromBackupAsync()` trả `CompletionStage<String>`.

### Vì sao không dùng exceptionally(error -> supplyAsync(...))?

Với `primary` kiểu `CompletableFuture<String>`, `exceptionally` cần một `String`. Một callback trả `CompletableFuture<String>` sẽ không đúng kiểu. Có thể ép sang kiểu quá rộng như `Object` nhưng gây nested value hoặc mất type safety — trái mục đích. `exceptionallyCompose` được tạo để *flatten* nhánh phục hồi bất đồng bộ.

## 8. Ví dụ Java 17: lỗi dự phòng cũng phải được truyền đúng

Không có API nào đảm bảo nguồn dự phòng luôn thành công. Dưới đây là chương trình độc lập cho ba kết quả: nguồn thành công, nguồn lỗi nhưng fallback thành công, và nguồn lỗi với fallback cũng lỗi.

Lưu file `RecoveryOutcomeDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class RecoveryOutcomeDemo {
    public static void main(String[] args) {
        CompletableFuture<String> ok =
                CompletableFuture.completedFuture("main");
        CompletableFuture<String> fail =
                CompletableFuture.failedFuture(
                        new IllegalStateException("main failed"));

        CompletableFuture<String> kept =
                ok.exceptionallyCompose(error ->
                        CompletableFuture.completedFuture("never-used"));

        CompletableFuture<String> recovered =
                fail.exceptionallyCompose(error ->
                        CompletableFuture.completedFuture("backup"));

        CompletableFuture<String> failedAgain =
                fail.exceptionallyCompose(error ->
                        CompletableFuture.failedFuture(
                                new IllegalArgumentException("backup failed")));

        System.out.println("Normal: " + kept.join());
        System.out.println("Recovered: " + recovered.join());

        try {
            failedAgain.join();
        } catch (CompletionException error) {
            System.out.println("Fallback error: "
                    + error.getCause().getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac RecoveryOutcomeDemo.java
java RecoveryOutcomeDemo
```

Stdout:

```text
Normal: main
Recovered: backup
Fallback error: IllegalArgumentException
```

Trong trường hợp cuối, `failedAgain` không khôi phục thành công vì stage từ callback bị lỗi. Stage kết quả phản ánh lỗi của fallback, không giữ giá trị của main. Nếu cần giữ **cả hai lỗi** để quan sát, ghi nhận nguyên nhân thứ nhất trước khi khởi động fallback và ghi nhận nguyên nhân thứ hai khi fallback failed; không mặc định pipeline trả về đầy đủ một tập nguyên nhân.

Ví dụ quan sát nguồn và fallback:

```java
CompletableFuture<String> result =
        primary.exceptionallyCompose(error -> {
            logPrimaryFailure(error);
            return backupAsync().whenComplete((value, backupError) -> {
                if (backupError != null) {
                    logBackupFailure(backupError);
                }
            });
        });
```

Đây là fragment; `logPrimaryFailure`, `logBackupFailure` và `backupAsync` do ứng dụng định nghĩa. `whenComplete` được dùng cho quan sát outcome và tránh ném exception mới từ logging; nó không dành để thay giá trị kết quả. Khi cả nguồn và backup lỗi, người vận hành cần phân loại/lưu nguyên nhân rõ ràng.

## 9. Phân loại lỗi: khi nào nên thử fallback?

Không phải lỗi nào cũng có thể hoặc nên phục hồi. Một số ví dụ:

| Loại lỗi | Có nên fallback/retry? | Lý do |
| --- | --- | --- |
| Timeout tạm thời ở dependency | Có thể, nếu còn deadline và hệ thống dự phòng độc lập | Có thể vượt qua lỗi tạm thời |
| Nguồn chính không sẵn sàng | Có thể chuyển sang nguồn dự phòng khác | Cần chính sách nhất quán và dữ liệu đủ mới |
| Lỗi xác thực/ủy quyền | Thường không | Thử lại đường khác có thể che giấu lỗi bảo mật |
| Dữ liệu đầu vào không hợp lệ | Thường không | Lỗi không hết khi đổi nguồn |
| Resource exhausted / rate limit | Cân nhắc trì hoãn hoặc ngừng | Retry ngay có thể làm sự cố nặng thêm |
| Cancellation do caller yêu cầu | Thường **không** khởi chạy lại | Người dùng đã không muốn công việc tiếp tục |
| Lỗi lập trình (`NullPointerException`, bug) | Không nên tự che bằng fallback mù quáng | Cần sửa lỗi và giám sát |

`Throwable` trong callback có thể là `CompletionException` bọc exception ứng dụng. Nếu cần kiểm tra nguyên nhân gốc, unwrap **có kiểm soát**:

```java
static Throwable unwrapCompletion(Throwable error) {
    Throwable current = error;
    while (current instanceof java.util.concurrent.CompletionException
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

Đây là **fragment method độc lập về mặt cú pháp** cần đặt trong một class khi biên dịch. Không tự động unwrap mọi `RuntimeException`: một exception do ứng dụng tạo có thể giữ nguyên ý nghĩa riêng. Nên dựa vào hợp đồng lỗi của dependency, tránh lọc theo thông điệp exception.

Ví dụ chỉ fallback nếu là lỗi tạm thời:

```java
CompletableFuture<String> result =
        primary.exceptionallyCompose(error -> {
            Throwable root = unwrapCompletion(error);
            if (root instanceof java.io.IOException) {
                return loadBackupAsync();
            }
            return CompletableFuture.failedFuture(error);
        });
```

Đây là fragment; `primary`, `loadBackupAsync` và `unwrapCompletion` do ứng dụng cung cấp. `CompletableFuture.failedFuture(error)` giữ đường lỗi thay vì tạo một thành công giả. Trong chương trình thật, `CancellationException` hoặc các lỗi có quy tắc đặc biệt nên được xử lý trước chính sách fallback chung.

## 10. Phục hồi có giới hạn: retry tạo một stage mới mỗi lần

`exceptionallyCompose` phù hợp để viết retry **có giới hạn**: sau lỗi của attempt hiện tại, tạo attempt mới bằng một hàm `Supplier<CompletableFuture<T>>`. Điều cần nhớ là **gắn handler lại vào cùng một future đã thất bại không chạy lại công việc**. Retry phải *thực sự gọi lại* logic khởi tạo attempt.

Ví dụ Java 17 độc lập. Hai attempt đầu cố ý lỗi; attempt thứ ba thành công. Chương trình giới hạn tối đa hai lần retry sau attempt đầu, nên kết quả xác định.

Lưu file `ExceptionallyComposeRetryDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class ExceptionallyComposeRetryDemo {
    static <T> CompletableFuture<T> retry(
            Supplier<CompletableFuture<T>> operation,
            int retriesLeft) {

        if (retriesLeft < 0) {
            throw new IllegalArgumentException("Negative retriesLeft");
        }

        CompletableFuture<T> current;
        try {
            current = operation.get();
        } catch (Throwable failure) {
            current = CompletableFuture.failedFuture(failure);
        }

        return current.exceptionallyCompose(error -> {
            if (retriesLeft == 0) {
                return CompletableFuture.failedFuture(error);
            }
            return retry(operation, retriesLeft - 1);
        });
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger attempts = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Supplier<CompletableFuture<String>> operation = () ->
                    CompletableFuture.supplyAsync(() -> {
                        int n = attempts.incrementAndGet();
                        if (n < 3) {
                            throw new IllegalStateException("temporary");
                        }
                        return "OK";
                    }, pool);

            CompletableFuture<String> finalResult =
                    retry(operation, 2);

            System.out.println("Result: " + finalResult.join());
            System.out.println("Attempts: " + attempts.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Chạy:

```bash
javac ExceptionallyComposeRetryDemo.java
java ExceptionallyComposeRetryDemo
```

Stdout:

```text
Result: OK
Attempts: 3
```

Mỗi lần `operation.get()` sinh **một `CompletableFuture` mới** và lập lịch một lời gọi `supplyAsync` mới. Khi một attempt bị lỗi, nhánh `exceptionallyCompose` gọi `retry` với số lần thử còn lại giảm 1. Kết quả cuối là `OK` ở lần thứ ba.

### Giới hạn của ví dụ retry

Đây là ví dụ kiến thức, **chưa phải cơ chế retry production**:

- Retry trong demo diễn ra ngay sau lỗi, không có **backoff + jitter** để tránh nhiều client cùng thử lại.
- Không có deadline tổng hoặc giới hạn tải đồng thời.
- Không phân loại lỗi tạm thời và lỗi vĩnh viễn.
- Không kiểm tra cancellation của caller; một yêu cầu đã bị hủy không nên vô tình được thử lại.
- Nếu nhiều attempt đều thất bại nhanh, việc compose lặp có thể tạo nhiều completion node; giới hạn thấp giúp tránh tạo chuỗi quá dài.
- Một operation có side effect như gửi thanh toán/ghi database có thể **không an toàn khi retry**, trừ khi có idempotency key hoặc giao thức xử lý trùng lặp.
- Nếu một attempt đã được một hệ thống bên ngoài chấp nhận nhưng trả timeout, retry có thể khiến công việc thực hiện nhiều lần. Đừng suy luận timeout đồng nghĩa chưa xử lý.

Với sản phẩm thực, nên có retry budget, deadline, exponential backoff/jitter, error classification, metrics và điều kiện dừng rõ ràng.

## 11. Timeout: recovery không tự đặt deadline cho các nguồn

`exceptionallyCompose` không có tham số timeout. Nếu nguồn đang **pending mãi**, callback phục hồi **không chạy**, bởi vì chưa có exceptional completion.

Có thể tạo deadline cho nguồn bằng `orTimeout`:

```java
CompletableFuture<String> primary = loadPrimaryAsync();

CompletableFuture<String> result =
        primary.orTimeout(1, TimeUnit.SECONDS)
               .exceptionallyCompose(error -> loadBackupAsync());
```

Đây là fragment; `loadPrimaryAsync` và `loadBackupAsync` do ứng dụng khai báo. `orTimeout` (Java 9+) hoàn tất **chính future được gọi** bằng `TimeoutException` khi đến hạn, đồng thời trả **cùng đối tượng future**, không tự tạo bản sao. Khi primary timeout và exceptional, handler có thể bắt đầu backup.

**Bốn lưu ý bắt buộc:**

1. Timeout của primary **không tự hủy** công việc I/O gốc, và có thể có kết quả về muộn dù future đã bị complete exceptionally.
2. Deadline một giây ở `primary` **không tự giới hạn thời gian của backup**. Nếu backup không hoàn tất, `result` vẫn có thể pending lâu.
3. Nếu nhiều thành phần giữ cùng tham chiếu `primary`, `orTimeout` thay đổi trạng thái được quan sát bởi tất cả; quyết định ownership rất quan trọng.
4. `result.get(1, TimeUnit.SECONDS)` chỉ timeout **thread đang chờ** và ném `TimeoutException`; nó **không** làm `result` exceptional và vì thế không tự kích hoạt `exceptionallyCompose`.

Nếu cần deadline cho toàn quá trình kể cả backup, có thể đặt timeout trên stage **cuối** hoặc thiết kế shared deadline cấp request:

```java
CompletableFuture<String> result =
        loadPrimaryAsync()
            .orTimeout(400, TimeUnit.MILLISECONDS)
            .exceptionallyCompose(error -> loadBackupAsync());

result.orTimeout(1200, TimeUnit.MILLISECONDS);
```

Đây là fragment minh họa hai deadline **tính từ lúc mỗi `orTimeout` được gọi**, không phải 400 ms + 1200 ms cho từng stage một cách tuần tự. Thời điểm scheduler quyết định chính xác việc timeout/complete, nên con số chỉ là ngân sách mong muốn. Khi cần chính xác thời gian còn lại của request, tính deadline chung và truyền cho client/tác vụ; chỉ timeout CompletableFuture không giải phóng socket/worker.

**Đừng dùng fallback cho mọi `TimeoutException` theo mặc định**. Cần kiểm tra hạn tổng và số lần thử; nếu primary timeout đã dùng gần hết ngân sách, bắt đầu một backup dài có thể làm yêu cầu còn chậm hơn.

## 12. Cancellation: bị hủy cũng là exceptional completion

Khi `CompletableFuture.cancel(...)` thành công, future trở nên completed exceptionally với `CancellationException`. Điều này có nghĩa handler `exceptionallyCompose` **có thể chạy cả khi nguồn bị hủy**. Nếu handler phục hồi mọi `Throwable` mà không kiểm tra, chương trình có thể **khởi động backup ngay cả khi caller đã yêu cầu dừng**.

Ví dụ fragment:

```java
CompletableFuture<String> pending = new CompletableFuture<>();
CompletableFuture<String> recovered =
        pending.exceptionallyCompose(error ->
                CompletableFuture.completedFuture("fallback"));

pending.cancel(true);
System.out.println(recovered.join()); // fallback
```

Đây là fragment hợp lệ khi có import `CompletableFuture`. Nó minh họa chính sách “phục hồi cả cancellation”; **không nhất thiết phù hợp** với các request bị người dùng hủy.

Cách bảo toàn cancellation qua một nhánh phục hồi cần kiểm tra cause và trả stage exceptional tương ứng:

```java
CompletableFuture<String> recovered =
        primary.exceptionallyCompose(error -> {
            Throwable root = unwrapCompletion(error);
            if (root instanceof java.util.concurrent.CancellationException) {
                return CompletableFuture.failedFuture(error);
            }
            return loadBackupAsync();
        });
```

`primary`, `unwrapCompletion`, `loadBackupAsync` là các thành phần do ứng dụng cung cấp. Trong ví dụ này, khi gặp hủy, handler không khởi chạy backup; việc trả `failedFuture(error)` làm stage kết quả vẫn hoàn tất **bất thường**. Không nhất thiết `recovered.isCancelled()` sẽ là `true`; dependent có thể hoàn tất bằng exception bọc `CancellationException`, vì vậy hãy kiểm tra outcome/causes thay vì dựa vào một flag cụ thể của stage phụ thuộc.

### Hủy kết quả phục hồi không bảo đảm hủy fallback

`CompletableFuture.cancel(true)` **không sử dụng interrupt** để điều khiển luồng chạy trong implementation `CompletableFuture`; `mayInterruptIfRunning` không có tác dụng theo mô tả API. Hủy stage đầu ra không tự động bảo đảm rằng task đang chạy bên trong `supplyAsync` hoặc client I/O thực sự dừng.

Nếu phải hủy công việc nền, giữ một cancellation handle riêng (ví dụ `Future<?>` của executor `submit` hoặc API hỗ trợ cancel từ client), truyền deadline, xử lý interruption và cleanup. Cần phân biệt **future đã canceled**, **thread được interrupt**, và **side effect thực sự đã dừng**.

## 13. Đặt recovery ở đâu trong chuỗi stage?

Vị trí gắn handler quyết định **lỗi nào** nó có thể bắt được.

### Phục hồi nguồn trước phép biến đổi

```java
CompletableFuture<Integer> result =
        fetchNumberAsync()
            .exceptionallyCompose(error -> loadNumberBackupAsync())
            .thenApply(value -> 100 / value);
```

Ở đây recovery xử lý lỗi từ `fetchNumberAsync`. Nếu `thenApply` sau đó chia cho 0, lỗi mới phát sinh **sau handler**, nên nó không được xử lý bởi handler đã đặt trước.

### Phục hồi toàn pipeline sau phép biến đổi

```java
CompletableFuture<Integer> result =
        fetchNumberAsync()
            .thenApply(value -> 100 / value)
            .exceptionallyCompose(error -> loadResultBackupAsync());
```

Lúc này handler cuối có thể xử lý lỗi từ cả nguồn lẫn phép biến đổi `thenApply`. Cần cân nhắc: nếu việc chia cho 0 cho thấy bug/data invalid, có nên chuyển sang backup không? Phục hồi “mọi lỗi” cuối pipeline có thể che giấu lỗi lập trình.

Hai đoạn là fragment minh họa, các hàm `fetchNumberAsync`, `loadNumberBackupAsync` và `loadResultBackupAsync` chưa được khai báo. Trong code thực, nên đặt handler sát ranh giới dependency được phép fallback và chỉ phục hồi các lỗi đã được phân loại.

### Recovery không thay đổi tất cả các nhánh của một future

```java
CompletableFuture<String> primary = loadPrimaryAsync();

CompletableFuture<String> recovered =
        primary.exceptionallyCompose(error -> loadBackupAsync());

CompletableFuture<String> observed =
        primary.whenComplete((value, error) -> audit(value, error));
```

Đây là fragment. Nếu primary thất bại, `recovered` có thể thành công nhờ fallback nhưng `observed` vẫn thấy lỗi gốc. Mỗi dependent của `primary` có outcome riêng theo graph; không có việc “sửa lại primary” chỉ bằng gắn một handler.

## 14. Threading, blocking và khả năng cạn worker

Dù `exceptionallyCompose` hỗ trợ bất đồng bộ qua stage trả về, ứng dụng vẫn có thể tạo bottleneck nếu callback:

- Gọi `get()`/`join()` để đợi fallback trong thread đang complete nguồn.
- Chạy I/O blocking dài trong `exceptionallyComposeAsync` trên `ForkJoinPool.commonPool()`.
- Chia sẻ một executor pool rất nhỏ cho nguồn chính, callback và fallback, trong khi callback lại đợi task chưa có worker để chạy.
- Retry không giới hạn, làm queue phình to khi dependency đang lỗi.
- Ghi log đồng bộ đắt đỏ từ hàng nghìn callback.
- Giữ lock quan trọng trong lúc đợi fallback.

Phương án thông thường là callback **rất ngắn**, chỉ phân loại lỗi và khởi tạo/nhận `CompletionStage<T>` từ một API không chặn. Phần I/O hoặc tính toán tốn thời gian được chạy bởi executor thích hợp, có timeout và backpressure.

Ví dụ tốt:

```java
CompletableFuture<String> result =
        primary.exceptionallyCompose(error -> {
            if (!shouldFallback(error)) {
                return CompletableFuture.failedFuture(error);
            }
            return fetchBackupAsync(); // Trả stage, không block ở đây.
        });
```

Đây là fragment; `shouldFallback` và `fetchBackupAsync` do ứng dụng định nghĩa. Nếu `fetchBackupAsync` thực ra block trước khi trả stage, đổi tên method thành Async **không làm công việc bất đồng bộ**.

Với việc tự tạo `ExecutorService`, phải quản lý shutdown, giới hạn queue/capacity và rejection. Nếu executor không nhận công việc (`RejectedExecutionException`), callback hoặc stage phục hồi có thể fail; đây cũng là lỗi cần chẩn đoán, không phải thành công fallback.

## 15. Memory visibility và dữ liệu trong stage phục hồi

`CompletableFuture` có cơ chế hoàn tất/nhận kết quả đáp ứng đồng bộ hóa của Java Concurrency; một thread quan sát completion thành công của stage phụ thuộc có thể sử dụng giá trị đã được công bố đúng cách từ bước trước. Tuy nhiên, **điều đó không tự biến mọi object mutable dùng chung thành thread-safe**.

Ví dụ không an toàn: nhiều retry cùng sửa `HashMap` thường hoặc biến đếm `int` dùng chung mà không có lock/atomic, rồi coi `join()` ở cuối sẽ sửa được race trước đó. Không đúng; race đã xảy ra khi các worker đang chạy.

Nên ưu tiên mỗi attempt tạo kết quả độc lập/immutable, ví dụ record Java 17:

```java
record UserInfo(long id, String name) {}

CompletableFuture<UserInfo> result =
        fetchPrimaryUserAsync()
                .exceptionallyCompose(error -> fetchBackupUserAsync());
```

Đây là fragment; hai hàm async trả cùng kiểu `CompletionStage<UserInfo>`. Nếu mỗi stage trả kết quả bất biến, bước sau dễ kiểm tra và tránh việc nhiều worker cùng sửa state.

Khi cần bộ đếm số attempt hoặc metric, dùng `AtomicInteger` hoặc hệ thống telemetry thread-safe. Không dựa vào “thứ tự callback thường chạy” như một cơ chế đồng bộ.

## 16. Các lỗi phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `exceptionally` để trả `CompletableFuture<T>` | Sai kiểu callback (đáng lẽ trả `T`) | Dùng `exceptionallyCompose` |
| Dùng `thenCompose` để xử lý nguồn đã fail | Callback không chạy khi nguồn thất bại | Gắn `exceptionallyCompose` trên nhánh lỗi |
| Gọi `fallbackFuture.join()` trong `exceptionally` | Block thread; có thể nghẽn worker | Trả stage trực tiếp từ `exceptionallyCompose` |
| Tưởng `exceptionallyCompose` luôn chạy callback | Nguồn thành công sẽ đi thẳng qua | Chỉ callback khi exceptional |
| Tưởng API này tự retry nguồn | Nó chỉ gọi một function tạo stage | Supplier phải thực sự tạo attempt mới |
| Retry vô hạn hoặc không backoff | Quá tải dependency và queue | Giới hạn attempt, deadline, backoff/jitter |
| Phục hồi cả lỗi nghiệp vụ vĩnh viễn | Che bug, trả dữ liệu sai | Phân loại cause, chỉ fallback lỗi được phép |
| Phục hồi cancellation không có chủ ý | Request đã hủy vẫn khởi chạy backup | Kiểm tra `CancellationException` và giữ chính sách hủy |
| Cho rằng `exceptionallyComposeAsync` bắt backup chạy trên executor được truyền | Executor chỉ áp dụng callback; backup tự chọn nơi chạy | Xác định executor của stage dự phòng |
| Chỉ timeout primary mà không giới hạn backup | Request có thể chờ backup vô hạn | Deadline tổng và timeout I/O |
| Dùng `orTimeout` nhưng tưởng nó tạo bản sao | Nó thay trạng thái trên chính future được gọi | Quản lý ownership của future và deadline |
| Dùng `get(timeout)` và mong handler chạy | get timeout chỉ ảnh hưởng caller | Muốn exceptional completion thì thiết kế stage deadline |
| Hủy output rồi coi task nguồn đã dừng | CompletableFuture.cancel không interrupt task | Cancellation handle riêng, cooperative stop |
| Mất lỗi primary khi fallback cũng lỗi | Chẩn đoán thiếu nguyên nhân ban đầu | Log/trace cả hai outcome |
| Gắn handler quá xa sau các phép biến đổi | Có thể che lỗi lập trình không thuộc dependency | Đặt recovery tại ranh giới lỗi có thể phục hồi |
| Dùng side effect không idempotent trong retry | Có thể tạo duplicate operation | Idempotency key, đối chiếu trạng thái |

## 17. Checklist trước khi triển khai

1. **Xác định lỗi nào được phép phục hồi**: timeout tạm thời, dependency unavailable hay loại lỗi cụ thể?
2. **Đặt handler đúng stage** để không vô tình bắt các lỗi không liên quan.
3. **Giữ cùng kiểu `T`** giữa nguồn và fallback; nếu cần đổi kiểu, chuyển đổi có chủ đích trong cả hai nhánh.
4. **Callback không block**; trả `CompletionStage<T>` do dịch vụ dự phòng tạo.
5. **Chọn overload Async** khi cần điều khiển nơi chạy callback, không giả định executor này điều khiển mọi task bên trong fallback.
6. **Giới hạn retry** nếu callback tạo lại attempt; có retry budget, backoff/jitter, deadline, phân loại lỗi.
7. **Tôn trọng cancellation** nếu user đã hủy hoặc request đã không còn cần kết quả.
8. **Đặt timeout tổng lẫn I/O**, tránh chỉ timeout primary rồi bỏ quên backup.
9. **Bảo toàn quan sát lỗi** của primary và backup khi cần điều tra sự cố.
10. **Dùng result immutable và telemetry thread-safe**, tránh state mutable shared.
11. **Kiểm tra side effect/idempotency** trước khi tự thử lại yêu cầu đã gửi ra ngoài.
12. **Test đủ nhánh**: nguồn thành công, nguồn lỗi/fallback thành công, fallback lỗi, callback ném lỗi, callback trả null, cancellation, timeout và executor rejection.

## 18. Câu hỏi tự kiểm tra

**1. Tại sao `exceptionallyCompose` khác `exceptionally`?**  
`exceptionally` trả một giá trị `T` ngay từ callback; `exceptionallyCompose` trả một `CompletionStage<T>` và chờ outcome của stage đó.

**2. Nếu primary thành công, callback của `exceptionallyCompose` có chạy không?**  
Không. Stage trả về tiếp tục thành công với giá trị primary.

**3. Nếu primary lỗi và fallback cũng lỗi, kết quả cuối thế nào?**  
Hoàn tất bất thường; không có giá trị thành công. Cần quan sát riêng nếu muốn giữ đủ thông tin của cả hai lỗi.

**4. Dùng `thenCompose` để xử lý primary thất bại có được không?**  
Không. `thenCompose` chạy callback khi upstream thành công, không phải nhánh exceptional.

**5. `exceptionallyComposeAsync(fn, executor)` có bảo đảm task backup chạy trên executor đó?**  
Không. Executor chạy callback; stage backup có thể sử dụng executor khác.

**6. Handler gắn vào một future có làm future gốc trở lại thành công không?**  
Không. Nó tạo stage phụ thuộc mới; future gốc vẫn giữ outcome của mình.

**7. Gọi `primary.orTimeout(...)` rồi `exceptionallyCompose` có tự dừng I/O đang chạy không?**  
Không. Timeout CompletableFuture không tự đóng socket hoặc interrupt tác vụ nguồn.

**8. `get(timeout)` của future chưa xong có tự kích hoạt recovery không?**  
Không. Timeout của `get` chỉ là thời gian đợi ở thread caller; nó không làm future hoàn tất exceptional.

**9. Nếu primary bị cancel, callback phục hồi có thể chạy không?**  
Có vì cancellation là exceptional completion. Ứng dụng phải quyết định có nên fallback hay giữ hủy.

**10. Retry đúng phải làm gì ngoài việc gắn lại `exceptionallyCompose`?**  
Phải thực sự tạo attempt mới, giới hạn số lần, phân loại lỗi, tôn trọng deadline, cancellation và idempotency.

**11. `exceptionallyCompose` có từ phiên bản Java nào?**  
Từ Java 12; có thể dùng trong Java 17 trở lên mà không cần thư viện bổ sung.

## Tài liệu tham khảo

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Java SE 17 — Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
