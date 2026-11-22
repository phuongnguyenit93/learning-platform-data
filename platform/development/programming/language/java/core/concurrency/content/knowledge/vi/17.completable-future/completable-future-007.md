# CompletableFuture.allOf() và anyOf() với nhiều tác vụ song song

## 1. Bài toán: tổng hợp nhiều công việc bất đồng bộ

Giả sử một request cần đồng thời gọi ba nguồn dữ liệu độc lập: hồ sơ, cấu hình và gợi ý. Có hai yêu cầu nghiệp vụ khác nhau:

1. **Phải có đủ cả ba kết quả** trước khi xử lý tiếp: đây là kiểu phối hợp *all*.
2. **Chỉ cần tác vụ hoàn tất đầu tiên** rồi quyết định bước tiếp theo: đây là kiểu phối hợp *any*.

Java cung cấp hai factory method static trên `java.util.concurrent.CompletableFuture`:

~~~java
// Chữ ký khái niệm, không phải chương trình độc lập.
static CompletableFuture<Void> allOf(CompletableFuture<?>... cfs);

static CompletableFuture<Object> anyOf(CompletableFuture<?>... cfs);
~~~

- **`CompletableFuture.allOf(...)`** tạo một Future tổng hợp hoàn tất khi **tất cả** Future đầu vào đã hoàn tất. Nếu tất cả thành công, Future tổng hợp thành công với kết quả kiểu `Void`, tức `join()` trả `null`. Nếu một hay nhiều Future đầu vào thất bại, Future tổng hợp hoàn tất ngoại lệ theo hợp đồng.
- **`CompletableFuture.anyOf(...)`** tạo Future tổng hợp nhận **outcome của Future đầu tiên hoàn tất**. Outcome có thể là giá trị thành công, exception, hoặc kết quả hủy được biểu diễn theo cơ chế exceptional completion. `anyOf` **không** mặc định đợi “thành công đầu tiên”.
- **Cả hai chỉ phối hợp trạng thái**: gọi factory không tự tạo thread, không tự chạy callable, không tự đặt timeout, và không đảm bảo tự hủy các tác vụ còn lại khi tổng hợp hoàn tất.

Đây là kiến thức **Java concurrency nói chung**, dùng API JDK thuần. Các ví dụ chạy trên **Java 17+**.

### Mục tiêu học tập

Sau bài, bạn sẽ biết:

1. Chọn đúng `allOf` hay `anyOf` theo yêu cầu “tất cả” hoặc “hoàn tất đầu tiên”.
2. Tạo tác vụ bằng `supplyAsync/runAsync` và chọn executor phù hợp.
3. Lấy kết quả riêng của từng `CompletableFuture<T>` sau `allOf` mà không ép kiểu nguy hiểm từ `Void`.
4. Giải thích exception, `CompletionException`, `ExecutionException` và cancellation ở từng cấp.
5. Không coi `anyOf` là first-success; biết thiết kế fallback hoặc winner policy có kiểm soát.
6. Xử lý timeout, giới hạn tài nguyên, tránh `join()` gây nghẽn worker và dọn executor đúng.
7. Viết test có thứ tự xác định bằng `CountDownLatch`, không phụ thuộc vào `Thread.sleep` để đoán lịch.

## 2. Các phương thức không thực thi công việc thay bạn

Nhìn vào hai dòng sau:

~~~java
// Minh họa Java 17+, không phải chương trình độc lập.
CompletableFuture<String> profile =
    CompletableFuture.supplyAsync(() -> loadProfile(), ioExecutor);

CompletableFuture<String> settings =
    CompletableFuture.supplyAsync(() -> loadSettings(), ioExecutor);

CompletableFuture<Void> both =
    CompletableFuture.allOf(profile, settings);
~~~

`supplyAsync` gửi công việc tới executor. `allOf` chỉ tạo **một phụ thuộc** vào việc cả hai task hoàn tất; nó không có nhiệm vụ tự gọi `loadProfile()` hoặc `loadSettings()`.

Nếu hai Future đầu vào đã hoàn tất, Future tổng hợp có thể hoàn tất ngay. Nếu đầu vào đang chờ trong executor bị nghẽn, `allOf` cũng phải chờ. Do đó “dùng CompletableFuture” không có nghĩa chương trình có concurrency tốt hơn nếu bạn sử dụng executor sai hoặc có dependency cycle.

### 2.1. supplyAsync và runAsync

| API | Dữ liệu trả về của task | Future nhận được |
| --- | --- | --- |
| `supplyAsync(Supplier<T>)` | `T` | `CompletableFuture<T>` |
| `supplyAsync(Supplier<T>, executor)` | `T` | `CompletableFuture<T>` |
| `runAsync(Runnable)` | Không trả giá trị | `CompletableFuture<Void>` |
| `runAsync(Runnable, executor)` | Không trả giá trị | `CompletableFuture<Void>` |
| `allOf(cfs...)` | Không gộp thành mảng/list giá trị | `CompletableFuture<Void>` |
| `anyOf(cfs...)` | Outcome từ một đầu vào thắng | `CompletableFuture<Object>` |

Nếu không truyền executor, các async method thường dùng `ForkJoinPool.commonPool()` theo chính sách API/JVM. Với I/O chặn lâu, database, network hoặc các tác vụ cần giới hạn concurrency, nên cân nhắc executor riêng với số worker, queue và shutdown rõ ràng.

### 2.2. “Song song” không đồng nghĩa N thread được đảm bảo

Gửi N task không tự cam kết N task sẽ chạy cùng một lúc. Một single-thread executor thực hiện từng task tuần tự; fixed pool có kích thước K cho tối đa K worker đang thực thi; scheduler còn quyết định chính xác thời điểm chạy. Chỉ khi **công việc độc lập** và năng lực executor đủ, các task mới có khả năng tiến triển đồng thời.

Quan trọng: hãy **tạo/gửi các Future đầu vào trước khi chờ**, nếu muốn khai thác concurrency.

~~~java
// Có thể chạy đồng thời, nếu executor có đủ worker.
CompletableFuture<Integer> a = supplyAsync(this::taskA, executor);
CompletableFuture<Integer> b = supplyAsync(this::taskB, executor);
CompletableFuture.allOf(a, b).join();
~~~

Đừng viết một chuỗi mà bạn gọi `join()` ngay sau khi gửi A rồi mới tạo B, nếu mục tiêu là khởi động A và B cùng lúc.

## 3. allOf(): đợi toàn bộ, không tự tổng hợp giá trị

### 3.1. Hợp đồng thành công

~~~text
A: RUNNING ------ SUCCESS(10) ---------+
                                       |
B: RUNNING ------------- SUCCESS(20) --+--> allOf = SUCCESS(null)
                                       |
C: RUNNING ---- SUCCESS(30) -----------+
~~~

`CompletableFuture.allOf(a, b, c)` trả `CompletableFuture<Void>`. Khi tất cả đầu vào hoàn tất bình thường, phép `all.join()` hoàn thành bình thường và trả **null** vì kiểu là `Void`.

**Không viết:**

~~~java
// SAI về kiểu kết quả, chỉ là minh họa ý tưởng lỗi.
// List<Integer> values = CompletableFuture.allOf(a, b, c).join();
~~~

Cần lấy kết quả từ **chính các Future đã mang kiểu** `CompletableFuture<Integer>` là A, B và C.

### 3.2. Lấy kết quả sau allOf

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
CompletableFuture<List<Integer>> combined =
    CompletableFuture.allOf(a, b, c)
        .thenApply(ignored -> List.of(a.join(), b.join(), c.join()));
~~~

Bởi vì `thenApply` (normal-completion continuation) chỉ chạy sau khi `allOf` hoàn tất thành công, ba `join` trên đầu vào đều có kết quả thành công đã sẵn có. Đoạn này **không phụ thuộc vào** một thread bị block để chờ ba task tiếp tục thực thi tại thời điểm continuation chạy.

`List.of(...)` không cho phần tử `null`; nếu một task có thể trả null, dùng cấu trúc dữ liệu cho phép null hoặc chuyển giá trị sang một kiểu biểu diễn “không có kết quả” rõ ràng. Đừng chỉ dùng `List.of` với giá trị nullable rồi giả định allOf lỗi do concurrency.

### 3.3. Ví dụ 1 — gộp ba kết quả có kiểu (Java 17+)

Tạo tệp `AllOfValuesDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class AllOfValuesDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> first =
            CompletableFuture.completedFuture(10);
        CompletableFuture<Integer> second =
            CompletableFuture.completedFuture(20);
        CompletableFuture<Integer> third =
            CompletableFuture.completedFuture(30);

        CompletableFuture<Void> all =
            CompletableFuture.allOf(first, second, third);

        CompletableFuture<List<Integer>> values =
            all.thenApply(ignored ->
                List.of(first.join(), second.join(), third.join()));

        System.out.println("all result null = "
            + (all.join() == null));
        System.out.println("values = " + values.join());
        System.out.println("sum = " +
            values.join().stream().mapToInt(Integer::intValue).sum());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac AllOfValuesDemo.java
java AllOfValuesDemo
~~~

Stdout chính xác:

~~~text
all result null = true
values = [10, 20, 30]
sum = 60
~~~

Ba Future đã thành công trước khi tạo `all`, nên không có lịch chạy cạnh tranh. `all.join() == null` chứng minh `allOf` trả kiểu `Void`, chứ không trả list chứa ba giá trị. Giá trị được lấy từ từng Future theo đúng thứ tự do `List.of(first.join(), ...)` chỉ định.

### 3.4. Thứ tự kết quả là do bạn định nghĩa

Nếu task 3 hoàn thành trước task 1, `allOf` vẫn **không sắp xếp** kết quả theo thứ tự hoàn thành. Khi bạn viết `List.of(first.join(), second.join(), third.join())`, list có thứ tự **đầu vào 1, 2, 3**, bất kể thứ tự task thực sự kết thúc.

Nếu cần thứ tự hoàn thành, hãy thiết kế một event queue hoặc một callback ghi kết quả kèm ID khi từng task hoàn tất. `allOf` không cung cấp “danh sách theo thời gian hoàn thành”.

## 4. allOf() với task chạy đồng thời thật sự

Để không chỉ học từ Future đã complete sẵn, ví dụ sau dùng `ExecutorService` và `CountDownLatch` nhằm chứng minh cả ba worker đã chạy tới một điểm trước khi được phép hoàn tất.

### Ví dụ 2 — ba task tiến triển đồng thời (Java 17+)

Tạo tệp `ParallelAllOfDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ParallelAllOfDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        CountDownLatch entered = new CountDownLatch(3);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<Integer> a =
                CompletableFuture.supplyAsync(
                    () -> calculate(1, entered, release), pool);
            CompletableFuture<Integer> b =
                CompletableFuture.supplyAsync(
                    () -> calculate(2, entered, release), pool);
            CompletableFuture<Integer> c =
                CompletableFuture.supplyAsync(
                    () -> calculate(3, entered, release), pool);

            CompletableFuture<Void> all =
                CompletableFuture.allOf(a, b, c);

            entered.await();
            System.out.println("before release = " + all.isDone());

            release.countDown();
            all.join();

            List<Integer> results = List.of(
                a.join(), b.join(), c.join());

            System.out.println("results = " + results);
            System.out.println("all done = " + all.isDone());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    static int calculate(int id, CountDownLatch entered,
            CountDownLatch release) {
        entered.countDown();

        try {
            release.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted", ex);
        }

        return id * 10;
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ParallelAllOfDemo.java
java ParallelAllOfDemo
~~~

Stdout khi không bị interrupt ngoài ý muốn:

~~~text
before release = false
results = [10, 20, 30]
all done = true
~~~

Vì sao kết quả không phụ thuộc scheduler?

1. `newFixedThreadPool(3)` có ba worker để chạy ba tác vụ đã gửi.
2. Mỗi task `countDown()` rồi chờ latch `release`. `entered.await()` chỉ trở về khi cả ba task đã tới điểm chờ.
3. Main in `all.isDone()` **trước** khi đếm `release`, nên chưa task nào có thể trả kết quả và `all` phải chưa hoàn tất.
4. Sau khi main mở latch, các task có thể kết thúc theo thứ tự nào cũng được, nhưng `all.join()` đợi cả ba và `List.of(a.join(), b.join(), c.join())` giữ thứ tự đã định.
5. `finally` mở latch cả khi xảy ra exception, tránh để worker đứng chờ mãi vì main thoát sớm; pool được shutdown theo lifecycle.

Ví dụ dùng latch để chứng minh concurrency, không dùng `Thread.sleep(100)` để đoán thread đã bắt đầu chạy. Nếu dùng pool chỉ có **một** worker, việc main chờ `entered` đạt 0 sẽ không tiến triển, vì worker đầu tiên bị chặn ở `release`; đây là một ví dụ điển hình về việc test phải có năng lực executor phù hợp.

## 5. allOf() khi một hay nhiều Future thất bại

### 5.1. Không có chuyện “allOf thất bại thì các task khác tự bị hủy”

Nếu một đầu vào hoàn tất ngoại lệ, Future tổng hợp **cuối cùng** cũng hoàn tất ngoại lệ. Theo contract `allOf`, nó hoàn tất khi **tất cả** Future đầu vào hoàn tất; không nên dựa vào hành vi “fail-fast ngay sau lỗi đầu tiên” nếu không có giao thức riêng.

Các task còn lại **không tự động bị interrupt hoặc cancel chỉ vì một task thất bại**. Nếu công việc bên ngoài vẫn đang thực thi, nó có thể tiếp tục tiêu thụ CPU/I/O cho đến khi xong hoặc được hủy theo protocol.

~~~text
A: FAILED(error A) ------------------+
B: ------------ SUCCESS(value B) ----+--> allOf: exceptional completion
C: ---------------- SUCCESS(value C) -+
~~~

Nếu **nhiều** đầu vào thất bại, không dựa vào thứ tự chọn một exception duy nhất của Future tổng hợp như một kết quả có thứ tự nghiệp vụ. Để báo cáo tất cả lỗi, kiểm tra **từng Future đầu vào** sau khi đã biết tất cả hoàn tất.

### 5.2. CompletionException và ExecutionException

Với `CompletableFuture`, hai cách chờ phổ biến:

| API | Có thể block nếu chưa hoàn tất? | Khi Future thất bại |
| --- | --- | --- |
| `join()` | Có | Ném unchecked `CompletionException` (thường bọc nguyên nhân), hoặc `CancellationException` trong các trường hợp hủy |
| `get()` | Có | Ném checked `ExecutionException` (bọc nguyên nhân); cũng có `InterruptedException` hoặc `CancellationException` |
| `get(timeout, unit)` | Có giới hạn | Như `get`, thêm `TimeoutException` |
| `isCompletedExceptionally()` | Không đợi | Chỉ cho biết exceptional completion, bao gồm cả hủy trong nhiều triển khai; không trả nguyên nhân |

`join()` tiện trong composition nhưng **không làm ngoại lệ biến mất**. Không catch trống `CompletionException` rồi giả vờ xử lý thành công; phải phân loại nguyên nhân, bù trừ tài nguyên và báo đúng trạng thái nếu nghiệp vụ yêu cầu.

### 5.3. Ví dụ 3 — allOf thất bại nhưng task tốt vẫn giữ kết quả (Java 17+)

Tạo tệp `AllOfFailureDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AllOfFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> failed =
            CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid A"));
        CompletableFuture<Integer> good =
            CompletableFuture.completedFuture(20);

        CompletableFuture<Void> all =
            CompletableFuture.allOf(failed, good);

        try {
            all.join();
        } catch (CompletionException ex) {
            System.out.println("all failed cause = "
                + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("good result = " + good.join());
        System.out.println("failed exceptional = "
            + failed.isCompletedExceptionally());
        System.out.println("good exceptional = "
            + good.isCompletedExceptionally());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac AllOfFailureDemo.java
java AllOfFailureDemo
~~~

Stdout:

~~~text
all failed cause = IllegalArgumentException
good result = 20
failed exceptional = true
good exceptional = false
~~~

`allOf` chỉ tổng hợp kết quả hoàn tất, nó không xóa giá trị của `good` và không biến tất cả đầu vào thành FAILED. Sau khi `all` đã hoàn tất, có thể phân loại từng Future: một Future có lỗi và một Future thành công.

Nếu bạn cần **partial success** (dùng những kết quả tốt dù có task lỗi), thiết kế một outcome type rõ ràng thay vì chỉ gọi `all.join()` và bỏ toàn bộ kết quả khi ném exception.

## 6. Thu thập đầy đủ outcome thay vì bỏ cuộc ở lỗi đầu tiên

Một pipeline thường cần báo cáo “có 3 task, 2 thành công, 1 thất bại” thay vì chỉ một exception.

### 6.1. Biến lỗi thành giá trị có kiểu

Trong Java 17, ta có thể tạo kiểu record:

~~~java
// Khái niệm Java 17+, không phải chương trình độc lập.
record Outcome<T>(T value, Throwable error) {
    boolean success() {
        return error == null;
    }
}
~~~

Mỗi Future được chuyển bằng `handle((value, error) -> new Outcome<>(...))`. `handle` chạy với cả success và exceptional completion, nên những Future bao bọc Outcome có thể hoàn tất **bình thường** dù task gốc thất bại; `allOf` trên các Future Outcome sau đó có thể dùng để chờ **tất cả** và lấy danh sách không mất thông tin thất bại.

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
CompletableFuture<Outcome<Integer>> safeA =
    originalA.handle((value, error) -> new Outcome<>(value, error));

CompletableFuture<Outcome<Integer>> safeB =
    originalB.handle((value, error) -> new Outcome<>(value, error));

CompletableFuture<Void> all =
    CompletableFuture.allOf(safeA, safeB);

CompletableFuture<List<Outcome<Integer>>> results =
    all.thenApply(unused -> List.of(safeA.join(), safeB.join()));
~~~

Cẩn thận: `error` có thể là `CompletionException` bao bọc nguyên nhân; nếu cần hiển thị nguyên nhân gốc, unwrap có kiểm soát. Nếu `handle` tự ném exception khi tạo Outcome/logging, wrapper Future cũng có thể thất bại; không coi `handle` là “hàng rào miễn nhiễm lỗi”.

### 6.2. Lỗi không nên trở thành giá trị giả success

Một cách sai là `exceptionally(error -> 0)` cho mọi lỗi rồi tiếp tục coi 0 là dữ liệu thật. Điều này **che mất** phân biệt “kết quả thật bằng 0” và “tác vụ thất bại”. Nếu muốn fallback bằng 0, phải xác định đây là chính sách nghiệp vụ có chủ ý và ghi lại outcome riêng khi cần audit.

Giao thức tổng hợp tốt thường có các nhãn: `SUCCESS(value)`, `FAILED(cause)`, `CANCELLED`, `TIMED_OUT` (nếu bạn chủ động phân loại timeout). Không trộn các trường hợp bằng một `null` hoặc integer sentinel mơ hồ.

## 7. anyOf(): thắng là người hoàn tất đầu tiên, không phải người thành công đầu tiên

### 7.1. Hợp đồng then chốt

~~~text
Task A: ------ SUCCESS("A") ----------------
Task B: -- FAILED(error B) -----------------
Task C: --------- SUCCESS("C") -------------

anyOf(A, B, C) có thể FAILED theo B,
vì B hoàn tất trước, dù A/C có thể thành công sau đó.
~~~

`anyOf` hoàn tất khi **bất kỳ** Future đầu vào nào hoàn tất. Nếu đầu vào thắng thành công với giá trị `v`, Future tổng hợp thành công với `v`. Nếu đầu vào thắng thất bại, Future tổng hợp cũng hoàn tất ngoại lệ.

**Không diễn giải `anyOf` thành “first non-null”, “first valid”, “first successful”, “fastest HTTP 200” hoặc “fastest successful replica”.** Những chính sách này cần logic lọc hoặc tiếp tục đợi khi gặp thất bại.

### 7.2. Tại sao trả CompletableFuture<Object>?

Các Future đầu vào có thể có kiểu khác nhau:

~~~java
// Mẫu Java, không phải chương trình độc lập.
CompletableFuture<Integer> price = ...;
CompletableFuture<String> label = ...;

CompletableFuture<Object> winner =
    CompletableFuture.anyOf(price, label);
~~~

Do không biết loại input nào hoàn tất trước, API trả kiểu `Object`. Ép thẳng `(String) winner.join()` là không an toàn nếu price thắng với `Integer`.

Nếu tất cả đầu vào cùng kiểu `String`, bạn vẫn nhận `CompletableFuture<Object>`. Có thể dùng `thenApply(String.class::cast)` sau khi bảo đảm mọi đầu vào thành công đều trả `String`, hoặc bọc kết quả thành record có kiểu/ID nguồn.

### 7.3. Ví dụ 4 — chọn người hoàn tất đầu tiên một cách xác định (Java 17+)

Để thấy rõ semantics mà không phụ thuộc race, ta điều khiển việc hoàn tất thủ công.

Tạo tệp `AnyOfWinnerDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;

public class AnyOfWinnerDemo {
    public static void main(String[] args) {
        CompletableFuture<String> slow = new CompletableFuture<>();
        CompletableFuture<String> fast = new CompletableFuture<>();

        CompletableFuture<Object> winner =
            CompletableFuture.anyOf(slow, fast);

        fast.complete("fast");
        slow.complete("slow");

        System.out.println("winner = " + winner.join());
        System.out.println("slow = " + slow.join());
        System.out.println("fast = " + fast.join());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac AnyOfWinnerDemo.java
java AnyOfWinnerDemo
~~~

Stdout:

~~~text
winner = fast
slow = slow
fast = fast
~~~

`fast.complete("fast")` xảy ra trước `slow.complete("slow")` trong cùng thread, nên `anyOf` đã nhận kết quả thắng. Việc slow hoàn tất sau đó không thay đổi giá trị của Future tổng hợp đã terminal.

**Lưu ý:** Đây là ví dụ **đảm bảo thứ tự completion**, không giả vờ chứng minh một thread thực sự nhanh hơn thread khác. Trong workload song song thực tế, ai hoàn tất trước do thời gian xử lý, lập lịch, I/O và lỗi quyết định.

## 8. anyOf() và exception: một lỗi nhanh có thể thắng

### Ví dụ 5 — Future thất bại đầu tiên thắng cuộc đua (Java 17+)

Tạo tệp `AnyOfFailureDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AnyOfFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> bad = new CompletableFuture<>();
        CompletableFuture<Integer> good = new CompletableFuture<>();

        CompletableFuture<Object> winner =
            CompletableFuture.anyOf(bad, good);

        bad.completeExceptionally(
            new IllegalArgumentException("bad response"));
        good.complete(42);

        try {
            winner.join();
        } catch (CompletionException ex) {
            System.out.println("winner failure = "
                + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("winner exceptional = "
            + winner.isCompletedExceptionally());
        System.out.println("other result = " + good.join());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac AnyOfFailureDemo.java
java AnyOfFailureDemo
~~~

Stdout:

~~~text
winner failure = IllegalArgumentException
winner exceptional = true
other result = 42
~~~

Kết quả tốt 42 **không sửa lại outcome** của `winner` đã thất bại. Bởi vậy nếu cần “lấy kết quả **thành công** nhanh nhất trong nhiều nguồn dự phòng”, `anyOf` đơn giản **chưa đủ**.

### 8.1. First-completion vs first-success vs first-acceptable

| Chính sách | Khi một task lỗi nhưng task khác còn chạy | Cách tiếp cận |
| --- | --- | --- |
| First-completion | Kết thúc ngay theo outcome đầu tiên, kể cả FAILED | `anyOf` |
| First-success | Chỉ kết thúc thành công khi có một task thành công; nếu mọi task lỗi, báo thất bại | Cần coordinator kết hợp outcome và đếm thất bại |
| First-acceptable | Có thể bỏ qua kết quả thành công nhưng không đạt validation; tiếp tục chờ | Coordinator với validation/timeout |
| All-success-required | Một lỗi làm toàn yêu cầu thất bại theo hợp đồng, dù task khác thành công | `allOf` cùng error policy |
| All-settled | Chờ tất cả, trả danh sách trạng thái của từng task | `handle` mỗi task rồi `allOf` |

Đừng chỉ dùng `anyOf(futures).exceptionally(error -> fallback)` rồi tuyên bố đã có “first success”: callback đó có thể chạy ngay sau lỗi đầu tiên **trước khi** Future khác hoàn tất thành công.

### 8.2. Cách thiết kế first-success đúng về mặt giao thức

Một coordinator có thể nhận callback `whenComplete` từ từng Future:

1. Khi một Future hoàn tất **thành công**, thử `winner.complete(value)`. Chỉ callback đầu tiên complete thành công thay đổi Future đích.
2. Khi một Future thất bại, tăng bộ đếm thất bại; **chỉ khi tất cả** đã thất bại mới completeExceptionally Future đích (và phải xử lý race giữa thành công và thất bại).
3. Ghi nhận cancellation, timeout và điều kiện “kết quả không hợp lệ” theo chính sách rõ.
4. Nếu tất cả nguồn đều thất bại, lưu/ghép nguyên nhân đủ cho debug, thay vì chỉ thông báo lỗi ngẫu nhiên.

Mẫu này cần xử lý đồng bộ **đếm kết quả** và “đã có success chưa” để không tuyên bố thất bại trong khi success vừa tới. Có thể dùng `AtomicInteger` cho đếm thất bại và `CompletableFuture.complete(...)` cho single-winner, nhưng phải suy luận về các đường completion, memory visibility và thứ tự callback thật cẩn thận.

### 8.3. Ví dụ 6 — first-success với cả lỗi và thành công (Java 17+)

Một implementation đơn giản dùng wrapper chuyển cả outcome thành giá trị rồi chọn thành công đầu tiên. Với ba task có thể hoàn tất theo thứ tự khác nhau, coordinator sau đảm bảo không bỏ cuộc chỉ vì task đầu tiên lỗi.

Tạo tệp `FirstSuccessDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicInteger;

public class FirstSuccessDemo {
    static <T> CompletableFuture<T> firstSuccess(
            CompletableFuture<T>... inputs) {
        if (inputs.length == 0) {
            throw new IllegalArgumentException("inputs empty");
        }

        CompletableFuture<T> result = new CompletableFuture<>();
        AtomicInteger failures = new AtomicInteger();

        for (CompletableFuture<T> input : inputs) {
            input.whenComplete((value, error) -> {
                if (error == null) {
                    result.complete(value);
                } else if (failures.incrementAndGet()
                        == inputs.length) {
                    result.completeExceptionally(error);
                }
            });
        }
        return result;
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> first = new CompletableFuture<>();
        CompletableFuture<Integer> second = new CompletableFuture<>();
        CompletableFuture<Integer> third = new CompletableFuture<>();

        CompletableFuture<Integer> best =
            firstSuccess(first, second, third);

        first.completeExceptionally(
            new IllegalArgumentException("first failed"));
        second.complete(99);
        third.complete(77);

        System.out.println("first success = " + best.join());
        System.out.println("third = " + third.join());
        System.out.println("first failed = "
            + first.isCompletedExceptionally());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FirstSuccessDemo.java
java FirstSuccessDemo
~~~

Stdout:

~~~text
first success = 99
third = 77
first failed = true
~~~

**Vì sao hoạt động trong ví dụ?** `first` lỗi trước, coordinator tăng failure count nhưng không kết thúc. `second` thành công tiếp theo, hoàn tất `best` với 99. `third` tới sau không thay đổi best đã hoàn tất.

**Giới hạn:** Đây là mẫu **minh họa tối giản**, không phải thư viện race đầy đủ. Nó chọn một Throwable khi tất cả thất bại, không gộp lỗi và không có giao thức hủy các input còn lại, timeout hay null/validation policy. Khi nhiều callback thực sự chạy đồng thời, `CompletableFuture.complete` đảm bảo chỉ một completion thắng; bộ đếm failure cùng logic “chỉ khi tất cả input lỗi” vẫn đảm bảo không trả failure nếu một input thành công, miễn mọi input chỉ hoàn tất một lần và callback không ném lỗi trước khi cập nhật. Chính sách **first-success** là yêu cầu bổ sung, không phải tính năng mặc định của `anyOf`.

## 9. Trường hợp zero input, null input và mảng biến độ dài

### 9.1. Khi không có Future đầu vào

Theo contract:

- `CompletableFuture.allOf()` **không tham số** trả Future **đã hoàn tất thành công** với `null`: không có việc gì phải đợi.
- `CompletableFuture.anyOf()` **không tham số** trả một Future **chưa hoàn tất**: không có input nào có thể thắng.

Đây là edge case quan trọng. Nếu business yêu cầu “ít nhất một nguồn dữ liệu”, phải validate danh sách **trước** `anyOf`, nếu không caller `join()` có thể chờ vô hạn trên một Future không ai hoàn tất.

### 9.2. Ví dụ 7 — mảng rỗng (Java 17+)

Tạo tệp `EmptyAggregatesDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;

public class EmptyAggregatesDemo {
    public static void main(String[] args) {
        CompletableFuture<Void> allEmpty =
            CompletableFuture.allOf();
        CompletableFuture<Object> anyEmpty =
            CompletableFuture.anyOf();

        System.out.println("all empty done = "
            + allEmpty.isDone());
        System.out.println("all empty null = "
            + (allEmpty.join() == null));
        System.out.println("any empty done = "
            + anyEmpty.isDone());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac EmptyAggregatesDemo.java
java EmptyAggregatesDemo
~~~

Stdout:

~~~text
all empty done = true
all empty null = true
any empty done = false
~~~

**Không gọi `anyEmpty.join()` trong ví dụ**, vì không có Future đầu vào hay producer nào để làm nó hoàn tất.

### 9.3. Null đầu vào

Không truyền một `null` làm Future đầu vào:

~~~java
// SAI: phần tử null không hợp lệ.
CompletableFuture.allOf(
    CompletableFuture.completedFuture("ok"), null);
~~~

Trường hợp này gây `NullPointerException` theo contract. Nếu danh sách có giá trị null là dữ liệu thành công của task, nó khác với chính **đối tượng Future là null**. Cần phân biệt `CompletableFuture.completedFuture(null)` (Future hợp lệ) với `(CompletableFuture<?>) null` (không phải Future).

Một danh sách `List<CompletableFuture<T>>` thường được chuyển sang mảng:

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
CompletableFuture<?>[] array =
    futures.toArray(new CompletableFuture<?>[0]);
CompletableFuture<Void> all = CompletableFuture.allOf(array);
~~~

Kiểm tra `futures` không null, các phần tử không null, và danh sách có đang bị thread khác sửa đồng thời hay không. Nếu danh sách mutable và có writer, chụp một cấu trúc ổn định trước khi tạo aggregation.

## 10. Cancellation: hủy aggregate không tự hủy input

Đây là lỗi thiết kế có tác động thực tế rất lớn. `CompletableFuture.allOf(...)` và `anyOf(...)` tạo **Future phụ thuộc**, nhưng không biến chúng thành một cancellation scope quản lý vòng đời của toàn bộ task.

Nếu bạn gọi:

~~~java
// Mẫu Java 17+, không độc lập.
CompletableFuture<Void> all =
    CompletableFuture.allOf(a, b, c);
all.cancel(true);
~~~

Không có bảo đảm `a`, `b` và `c` sẽ tự bị cancel hay interrupt. Thường chỉ **aggregate Future** chuyển thành trạng thái hủy. Các input có thể tiếp tục chạy, tiêu thụ tài nguyên hoặc hoàn tất bình thường.

Tương tự, nếu `anyOf(a, b, c)` nhận được winner và hoàn tất, các loser không tự dừng. Nếu yêu cầu nghiệp vụ “ai thắng thì hủy các yêu cầu còn lại”, phải thực hiện hành động cancel thích hợp và xử lý thực tế rằng tác vụ đã gửi ra ngoài có thể vẫn đang chạy.

### 10.1. Ví dụ 8 — cancel aggregate không cascade (Java 17+)

Tạo tệp `CancelAggregateDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;

public class CancelAggregateDemo {
    public static void main(String[] args) {
        CompletableFuture<String> a = new CompletableFuture<>();
        CompletableFuture<String> b = new CompletableFuture<>();

        CompletableFuture<Void> combined =
            CompletableFuture.allOf(a, b);

        combined.cancel(true);

        System.out.println("combined cancelled = "
            + combined.isCancelled());
        System.out.println("a cancelled = " + a.isCancelled());
        System.out.println("b cancelled = " + b.isCancelled());

        a.complete("A");
        b.complete("B");

        System.out.println("a result = " + a.join());
        System.out.println("b result = " + b.join());
        System.out.println("combined still cancelled = "
            + combined.isCancelled());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CancelAggregateDemo.java
java CancelAggregateDemo
~~~

Stdout:

~~~text
combined cancelled = true
a cancelled = false
b cancelled = false
a result = A
b result = B
combined still cancelled = true
~~~

Ví dụ dùng Future chưa gắn worker để tách bạch **trạng thái aggregate** khỏi cancellation của input. `cancel(true)` trên aggregate không tự gọi `a.cancel(true)` hay `b.cancel(true)`.

**Quan trọng:** `CompletableFuture.cancel(true)` không dùng `mayInterruptIfRunning` để điều khiển thực thi theo contract của class này. Đừng suy ra từ boolean true rằng underlying task hoặc HTTP call chắc đã dừng. Hủy thực tế của tác vụ I/O thường cần API hỗ trợ cancellation, timeout hoặc đóng tài nguyên.

### 10.2. Input bị hủy có làm aggregate isCancelled() không?

Một input bị `cancel(...)` thường trở thành exceptionally completed, và aggregate phụ thuộc có thể hoàn tất ngoại lệ theo contract. **Không suy ra rằng `allOf.isCancelled()` hoặc `anyOf.isCancelled()` nhất thiết là true** khi một input bị hủy: trạng thái cancellation của **đối tượng aggregate** khác với việc nó hoàn tất ngoại lệ do CancellationException từ input.

Để báo cáo hủy chính xác, quan sát từng input nếu cần, đồng thời phân biệt `CancellationException` gốc, `CompletionException` bao bọc và trạng thái của aggregate.

## 11. Timeout và deadline khi chờ nhiều task

### 11.1. Timeout chỉ giới hạn điều gì?

Những API thường gặp:

- `all.get(timeout, unit)`: giới hạn **thời gian chờ của caller**; khi hết giờ có thể ném `TimeoutException`, **không tự cancel** all hay các input.
- `all.orTimeout(timeout, unit)`: theo Java 9+, đặt đường exceptional completion bằng `TimeoutException` nếu Future **đó** chưa hoàn tất đúng hạn. Nó trả lại **chính CompletableFuture được gọi**, không phải một Future hoàn toàn độc lập.
- `all.completeOnTimeout(value, timeout, unit)`: đặt một giá trị completion nếu Future chưa hoàn tất sau hạn; với `allOf` kiểu `Void`, giá trị phù hợp thường là `null`, nhưng đó là một quyết định dễ che lỗi “chưa đủ task”.
- `any.orTimeout(...)`: áp dụng timeout cho chính `any`, không làm các input tự dừng.

**Timeout của aggregate không đồng nghĩa đã hủy được các tác vụ gốc**. Nếu caller bỏ cuộc ở deadline, các task gốc có thể còn chiếm worker/connection và tạo side effect.

### 11.2. Mẫu deadline có cancel theo hợp đồng riêng

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
CompletableFuture<Void> all =
    CompletableFuture.allOf(a, b, c);

try {
    all.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    a.cancel(true);
    b.cancel(true);
    c.cancel(true);
    // Báo timeout; xác nhận cleanup của thao tác ngoài khi cần.
}
~~~

Cần xử lý hoặc truyền `InterruptedException` và `ExecutionException` ở caller. Cancel các `CompletableFuture` này thường chỉ thay đổi trạng thái của chúng; **để dừng I/O thật**, tích hợp API cancellation của chính công việc.

Không viết logic nghiệp vụ dựa vào giả định “đã hủy tất cả nên không còn callback nào đến”. Cancellation và sự hoàn tất bên ngoài có thể đua nhau; một request hủy trễ có thể không ngăn downstream đã xử lý dữ liệu.

### 11.3. Timeout khác lỗi thực thi

Nếu `anyOf` nhận một Future thất bại sớm, nó sẽ hoàn tất ngoại lệ dù các task khác chưa đến deadline. Nếu muốn first-success-until-deadline, cần coordinator không hoàn tất do lỗi sớm, gắn deadline riêng và thống kê các nguồn còn đang xử lý.

## 12. Tránh deadlock, starvation và blocking không đúng chỗ

### 12.1. Đừng join Future của task chưa được executor chạy

Một ví dụ thiết kế nguy hiểm:

~~~java
// SAI nếu cả hai task chạy cùng single-thread executor.
ExecutorService pool = Executors.newSingleThreadExecutor();

CompletableFuture<Integer> outer =
    CompletableFuture.supplyAsync(() -> {
        CompletableFuture<Integer> inner =
            CompletableFuture.supplyAsync(() -> 42, pool);
        return inner.join(); // Block worker duy nhất của pool.
    }, pool);
~~~

`outer` chiếm worker duy nhất, gửi `inner` vào queue rồi chờ inner. Nhưng inner không thể chạy vì worker bị outer chiếm. Đây là một **dependency stall/deadlock ở mức task**, dù không có monitor lock cổ điển.

Cách sửa thường là thiết kế composition **không chặn** bằng `thenCompose`, `thenCombine` hoặc gửi các task độc lập từ ngoài worker rồi gắn continuation; nếu bắt buộc block, phân tích capacity/queue và dependency trước khi chọn executor.

### 12.2. thenApply và thenApplyAsync

- `thenApply(fn)` có thể chạy ở thread hoàn tất stage đầu vào hoặc thread đang đăng ký callback nếu stage đã hoàn tất, tùy tình huống.
- `thenApplyAsync(fn)` gửi continuation tới executor mặc định; overload có executor cho phép điều khiển nơi chạy.
- Không mặc định rằng mọi continuation đều chạy trên main hay trên một worker riêng.

Nếu continuation của `allOf` làm công việc nặng, nên cân nhắc `thenApplyAsync(..., dedicatedExecutor)` phù hợp. Nếu chỉ lấy kết quả từ các Future đã success, `thenApply` thường đơn giản hơn, tránh scheduling overhead.

### 12.3. Không gọi join trên mọi Future ở cùng pool trước khi chúng được gửi

Để giữ concurrency, khởi động tất cả công việc độc lập trước rồi compose Future. Khi có thứ tự phụ thuộc thật (ví dụ B cần kết quả A), dùng `thenCompose` để biểu diễn phụ thuộc thay vì block một worker bằng `join` chờ task sau.

`CompletableFuture` giúp **biểu diễn dependency graph**, nhưng không tự ngăn bạn xây một dependency graph có vòng chờ.

## 13. Quản lý lỗi và log tập trung

### 13.1. Quan sát outcome của từng input

Một aggregate allOf FAILED có thể chỉ cung cấp một nguyên nhân, nhưng với monitoring thường cần biết **nguồn nào hỏng**. Gắn ID:

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
record Result<T>(String source, T value, Throwable failure) {}

CompletableFuture<Result<String>> profileResult =
    profile.handle((value, err) ->
        new Result<>("profile", value, err));

CompletableFuture<Result<String>> settingsResult =
    settings.handle((value, err) ->
        new Result<>("settings", value, err));
~~~

Bạn có thể allOf trên các Future Result và thu danh sách sau khi hoàn tất. Khi một source lỗi, hãy lưu exception với source name/context, thay vì chỉ log “CompletionException” không rõ tác vụ nào.

### 13.2. Chú ý CompletionException lồng nhau

`CompletionException` có thể bọc `IllegalArgumentException` hoặc một lỗi domain; nhiều stage có thể tạo những lớp bọc. Khi đưa lỗi vào log/HTTP response, bóc nguyên nhân phù hợp nhưng không làm mất stack trace và context.

Không “unwrap đến cùng” một cách mù quáng nếu những wrapper có ý nghĩa nghiệp vụ. Ví dụ `CancellationException`, `TimeoutException` hay exception do lỗi resource có thể cần chính sách riêng.

### 13.3. allOf không cung cấp transaction

Nếu ba task thực hiện ba cập nhật không thể đảo ngược, `allOf` chỉ **đợi outcome**, không có rollback khi một task hỏng. Nếu cần atomic business operation, hãy thiết kế transaction, idempotency, compensation hoặc outbox/ack protocol riêng.

Với `anyOf` chạy nhiều nguồn dự phòng, **loser** cũng có thể đã hoàn thành side effect trước khi bạn cố cancel; chỉ dùng kiểu đua như vậy với các task an toàn khi chạy trùng hoặc có cơ chế loại trùng.

## 14. Hiểu hủy và interrupt trong CompletableFuture

Một số nhầm lẫn thường gặp:

1. Gọi `cf.cancel(true)` trên một `CompletableFuture` không cam kết interrupt thread đang chạy Supplier. Theo contract, `mayInterruptIfRunning` không được dùng để điều khiển thực thi của class.
2. Khi aggregate allOf/anyOf bị cancel, input không tự bị cancel. Từng input có thể tiếp tục chạy.
3. Khi Future đầu vào bị cancel, dependent stage có thể exceptional completion với `CompletionException` bọc `CancellationException`, chứ không bắt buộc chính aggregate báo `isCancelled() == true`.
4. Một `Future` bị cancel không chứng minh file đã đóng, connection đã release hoặc bên thứ ba đã rollback.
5. `anyOf` thắng không tự hủy loser; việc hủy loser cũng không đảm bảo dừng được những side effect đã bắt đầu.

Nếu cần **structured lifetime** của nhiều task con, không nên kỳ vọng `allOf/anyOf` tự cung cấp. Bạn phải xác định scope ownership, deadline, cancellation, tài nguyên và điểm xác nhận hoàn tất.

### 14.1. khi nào nên cancel loser?

Khi nhiều task thu thập **cùng một dữ liệu có thể thay thế**, việc cancel loser có thể tiết kiệm tài nguyên, nhưng chỉ khi:

- Mỗi task có cancellation mechanism thực sự hiệu lực.
- Side effect là idempotent hoặc được hạn chế.
- Kết quả muộn không ghi đè winner.
- Cleanup không bỏ quên connection, permit hay buffer.
- Caller không giữ một Future có vẻ cancel nhưng worker thực vẫn chạy âm thầm.

Nếu task thực thi ghi dữ liệu quan trọng, “ai xong trước” có thể không phải chiến lược đúng; đừng dùng cuộc đua để xác định nghiệp vụ trước khi làm rõ tính nhất quán.

## 15. Edge cases và contract cần thuộc

| Tình huống | `allOf` | `anyOf` |
| --- | --- | --- |
| Không có input | Hoàn tất thành công với `null` ngay | Trả Future chưa hoàn tất |
| Một input, success | Theo input, hoàn tất success với `null` | Trả giá trị đầu vào |
| Một input, failure | Exceptional completion | Exceptional completion |
| N input đều success | Hoàn tất khi tất cả đã success | Hoàn tất khi một input đầu tiên success |
| N input, một failure sớm | Cuối cùng exceptional completion; không tự cancel các input còn lại | Failure sớm có thể thắng ngay |
| N input, một input bị cancel | Aggregate có thể exceptional completion; không nhất thiết tự là cancelled | Cancellation có thể là exceptional winner |
| Input có result `null` | Aggregate success vẫn là `null` | Winner có thể success với `null` |
| Nhiều Future hoàn tất gần đồng thời | Không sinh danh sách kết quả | Winner phụ thuộc completion race; không hứa thứ tự |
| Gọi cancel trên aggregate | Không tự động cancel các input | Không tự động cancel các input |
| Timeout của caller khi chờ | Không tự cancel input | Không tự cancel input |

**Nhắc lại:** `anyOf` không ưu tiên “input nằm trước trong mảng”. Khi hai Future đua thật sự, winner do thời điểm hoàn tất quyết định, không phải vì một Future được đưa vào mảng tại index 0.

## 16. Bài tập mở rộng

### Bài tập A: Ba nguồn độc lập

Viết ba `CompletableFuture<String>` tải dữ liệu A, B, C trên executor cố định. Dùng `allOf` và `thenApply` để trả `List<String>` theo thứ tự A, B, C. Đưa `CountDownLatch` vào test để chứng minh cả ba task đã bắt đầu trước khi xử lý kết quả.

**Điều kiện đúng:** không dùng `join()` ngay sau khi tạo mỗi Future; không dùng `all.join()` như một `List`; có shutdown executor.

### Bài tập B: Một nguồn thất bại

Đổi B thành task ném `IllegalArgumentException`. Phân biệt `all.join()` ném `CompletionException` với `B.join()` ném lỗi tương ứng. Dùng `handle` để thu report chứa A SUCCESS, B FAILED và C SUCCESS.

**Điều kiện đúng:** không làm mất kết quả tốt, không biến lỗi thành thành công giả nếu nghiệp vụ cần báo thất bại.

### Bài tập C: First-completion và first-success

Tạo hai Future với một task thất bại trước, một task thành công sau. So sánh kết quả `anyOf` và coordinator `firstSuccess` ở phần trước.

**Điều kiện đúng:** `anyOf` lỗi theo người hoàn tất đầu tiên; `firstSuccess` vẫn nhận giá trị thành công của task sau.

### Bài tập D: Timeout nhưng không tự hủy

Dùng một `CompletableFuture` chưa complete và gọi `get(100, TimeUnit.MILLISECONDS)` để quan sát `TimeoutException`. Kiểm tra Future vẫn có thể được `complete("late")` sau timeout.

**Điều kiện đúng:** timeout của phép chờ không tự hủy Future. Đặt timeout test hợp lý để tránh chờ lâu, nhưng không phụ thuộc độ chính xác tuyệt đối của scheduler.

### Bài tập E: Cancel một aggregate

Tạo hai Future chưa complete, allOf chúng rồi gọi `all.cancel(true)`. Kiểm tra trạng thái của từng input trước và sau khi chúng được complete riêng; so sánh với `CancelAggregateDemo`.

**Điều kiện đúng:** không suy diễn input đã bị cancel/interrupt do hủy aggregate.

## 17. Kiểm thử đồng thời: không đoán lịch chạy

### 17.1. Những lỗi test dễ mắc

~~~java
// SAI về ý định kiểm thử deterministic.
// Không phải chương trình độc lập.
CompletableFuture<String> a =
    CompletableFuture.supplyAsync(() -> slowCall());
CompletableFuture<String> b =
    CompletableFuture.supplyAsync(() -> fastCall());

Thread.sleep(50);
assertEquals("fast", CompletableFuture.anyOf(a, b).join());
~~~

Không có bảo đảm `fastCall` hoàn tất trước `slowCall` chỉ vì tên hàm hoặc thời lượng sleep main. Trên CI bận, DNS/network/JIT/scheduler có thể khác. Nếu cần test **semantics**, dùng manual `complete` trên Future chưa hoàn tất hoặc latch để điều khiển thứ tự.

### 17.2. Các case test bắt buộc

- `allOf` tất cả thành công: Future tổng hợp là `Void`, giá trị nằm ở từng input.
- `allOf` một task thất bại: lỗi được phản ánh, task tốt vẫn giữ outcome.
- `anyOf` success trước: winner lấy đúng value, loser vẫn chạy/complete.
- `anyOf` failure trước: aggregate thất bại, dù task còn lại có thể success sau.
- `anyOf` input types khác nhau: không ép kiểu `Object` thiếu kiểm tra.
- Mảng rỗng: allOf done, anyOf chưa done; không join anyOf rỗng.
- Có phần tử Future `null`: factory từ chối.
- Task trả `null` hợp lệ: không nhầm với Future null.
- Cancel aggregate: input không mặc định bị cancel.
- Input cancel: phân biệt exceptional completion và isCancelled của aggregate.
- Timeout: caller timeout không làm input tự dừng.
- InterruptedException của `get()`: propagate hoặc restore flag theo contract.
- Executor quá ít worker: phát hiện dependency stall, không để test treo vô thời hạn.
- Shutdown: không rò worker hoặc callback giữ tài nguyên quá lâu.

### 17.3. Đo hiệu năng đúng cách

Mọi phép đo cần phân biệt:

1. **Submission latency**: mất bao lâu để gửi các task.
2. **Execution latency từng task**: CPU/I/O thực tế.
3. **Aggregation latency**: đến khi có đủ tất cả hoặc đến winner.
4. **Cancellation/cleanup latency**: bao lâu sau khi hủy mà tài nguyên thật sự release.
5. **Tail latency**: p95/p99, đặc biệt allOf thường bị chi phối bởi task chậm nhất trong nhóm.

Không lấy vài số đo `System.currentTimeMillis()` rồi kết luận `anyOf` luôn tốt hơn `allOf`. Hai method giải quyết **hai nghĩa vụ nghiệp vụ khác nhau**, không thể so sánh đơn thuần như hai triển khai tương đương.

## 18. Checklist dùng allOf/anyOf trước khi đưa vào sản phẩm

- Công việc có **độc lập** và có thể chạy đồng thời hay phải có dependency order?
- Bạn cần **tất cả**, **hoàn tất đầu tiên**, **thành công đầu tiên**, hay **kết quả đạt validation đầu tiên**?
- Đã chọn executor phù hợp với CPU-bound hay blocking I/O?
- Có giới hạn queue, số worker, số request đang bay và tài nguyên dùng chung không?
- Có tránh `join()` chờ task con trên cùng executor đang bị chiếm hết worker không?
- Với `allOf`, có thu giá trị từ từng typed Future thay vì ép kiểu `Void`?
- Nếu một input có thể trả null, list tổng hợp có kiểu dữ liệu cho phép null không?
- Khi một task lỗi, có xác định muốn fail cả yêu cầu hay giữ partial results?
- Có thu lỗi theo source ID, không chỉ một exception từ aggregate?
- Với `anyOf`, có hiểu lỗi đầu tiên cũng là winner không?
- Có tránh ép kiểu `Object` thiếu kiểm tra từ anyOf hỗn hợp kiểu?
- Có validate danh sách input không rỗng trước anyOf không?
- Có tránh để Future null trong varargs không?
- Có deadline cho request và chính sách timeout thực tế?
- Có rõ **ai** có trách nhiệm cancel loser/input và làm cleanup không?
- Có tránh coi `cancel(true)` của CompletableFuture là bằng chứng worker đã bị interrupt không?
- Có test outcome với latch và complete thủ công thay vì sleep đoán scheduler?
- Có shutdown executor với deadline và xử lý task còn chạy không?
- Có kiểm tra việc side effect sau timeout/hủy được xử lý đúng idempotency không?

## 19. Câu hỏi tự kiểm tra

**1.** `CompletableFuture.allOf(a, b).join()` trả danh sách kết quả của a và b không?

Không. `allOf` trả `CompletableFuture<Void>`; khi success, `join()` trả `null`. Dùng `a.join()` và `b.join()` để lấy giá trị của từng Future sau khi allOf success.

**2.** `anyOf(a,b)` có đảm bảo là task thành công đầu tiên không?

Không. Nó hoàn tất theo **outcome của task đầu tiên hoàn tất**; task đó có thể thất bại. First-success cần coordinator khác.

**3.** Nếu một task lỗi, `allOf` có tự cancel các task còn lại?

Không. Các input có thể tiếp tục chạy và tạo side effect. Phải có cancellation protocol riêng khi cần.

**4.** `anyOf` đã trả winner, các task thua có tự dừng không?

Không. Kết quả aggregate đã kết thúc không làm loser tự bị cancel hoặc interrupt.

**5.** Vì sao `anyOf` trả `CompletableFuture<Object>`?

Vì đầu vào có thể khác kiểu và compiler không biết input nào thắng. Nếu mọi input có cùng kiểu, cần chuyển kiểu có kiểm tra hoặc dùng wrapper record.

**6.** `allOf()` và `anyOf()` không tham số khác nhau thế nào?

`allOf()` trả Future đã success với null; `anyOf()` trả Future chưa complete, không có người thắng. Không gọi `join()` trên anyOf rỗng mà không có logic bổ sung.

**7.** `get(timeout)` ném `TimeoutException` có nghĩa các task đã bị cancel?

Không. Đó chỉ là timeout **đợi của caller**. Future có thể tiếp tục hoàn tất sau đó.

**8.** Một task trong pool 1 thread tạo task con ở cùng pool rồi `join()` task con. Nguy cơ gì?

Task con không có worker rảnh để chạy, còn task cha block chờ; có thể bị deadlock/dependency stall. Nên dùng composition không chặn và thiết kế capacity phù hợp.

**9.** `allOf` có đảm bảo kết quả theo thứ tự hoàn thành không?

Không. Thứ tự bạn gom giá trị (ví dụ `List.of(a.join(),b.join())`) do bạn định nghĩa; không phải thứ tự task kết thúc.

**10.** Tại sao `allOf` có thể có lỗi nhưng một số input vẫn SUCCESS?

Vì mỗi Future có outcome riêng. Aggregate có thể FAILED nếu bất kỳ input lỗi, dù các input khác đã hoàn tất thành công.

**11.** Cancel `CompletableFuture.allOf(a,b)` có chắc làm `a.isCancelled()` và `b.isCancelled()` thành true không?

Không. Aggregate cancellation không cascade bắt buộc xuống input.

**12.** Nếu task A hoàn tất thành công với null và task B còn chạy, `anyOf(A,B)` có thể success với null không?

Có. Null là **giá trị kết quả hợp lệ** của A, không phải tín hiệu “chưa hoàn tất”.

## 20. Tài liệu JDK và tóm tắt

Các hợp đồng nên đối chiếu trong Javadoc của JDK đang dùng:

- [CompletableFuture — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [CompletionStage — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [ExecutorService — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Future — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)

**Bảng ghi nhớ:**

~~~text
allOf(a, b, c):
  Chờ tất cả Future hoàn tất.
  Nếu tất cả success -> CompletableFuture<Void> success(null).
  Nếu một hay nhiều lỗi -> aggregate exceptional completion.
  Giá trị nằm trong từng typed Future đầu vào.

anyOf(a, b, c):
  Lấy outcome hoàn tất đầu tiên: success HOẶC failure.
  Trả CompletableFuture<Object>.
  Không mặc định là first-success, không cancel loser.

Cả hai:
  Không tự chạy task, không tạo thread, không tự đặt timeout.
  Không tự cancel các input khi aggregate hoàn tất/hủy.
  Không phải transaction, không tự cleanup side effect.
~~~

**Kết luận:** Chọn `allOf` khi công việc cần **toàn bộ kết quả**, dùng `anyOf` khi muốn **outcome hoàn tất đầu tiên** và chấp nhận cả trường hợp failure chiến thắng. Với yêu cầu phức tạp hơn như first-success, partial successes, deadline hay cancel loser, phải thiết kế giao thức rõ ràng thay vì gán cho hai factory method những bảo đảm mà chúng không có.