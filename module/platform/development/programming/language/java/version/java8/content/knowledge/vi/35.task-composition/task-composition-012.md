# Thiết kế deadline, timeout và quản lý executor theo API Java hiện hành

**Chủ đề:** Java 8 → Ghép tác vụ → Thiết kế deadline, timeout và quản lý executor theo API hiện hành.

Trong ứng dụng Java xử lý HTTP, truy vấn dữ liệu, thanh toán hoặc ghép nhiều lời gọi dịch vụ, một tác vụ bất đồng bộ có thể **chạy quá lâu**. Để bảo vệ độ trễ người dùng và tài nguyên hệ thống, cần thiết kế ba yếu tố liên quan nhưng **không đồng nghĩa**:

1. **Deadline (hạn cuối của toàn yêu cầu):** một thời điểm hoặc một ngân sách thời gian mà sau đó yêu cầu không còn hữu ích.
2. **Timeout (thời gian chờ tối đa cho một thao tác):** giới hạn thời gian chờ một kết quả hoặc hoàn thành một stage.
3. **Executor (nơi thực thi công việc):** chịu trách nhiệm thread, hàng đợi, giới hạn tải, từ chối công việc và vòng đời tài nguyên.

Một API có **CompletableFuture.orTimeout(...)** không tự bảo đảm **dừng HTTP request thực tế**, cũng không tự giải quyết tình trạng quá tải của thread pool. Ngược lại, một executor có nhiều thread không thể thay thế chính sách deadline và không làm các thao tác đã timeout tự trở nên an toàn.

**Thông điệp trọng tâm:** truyền một **ngân sách còn lại** qua toàn bộ pipeline, đặt timeout ở cả **lớp chờ kết quả** và **I/O thực tế** khi có hỗ trợ, quản lý executor như một tài nguyên dài hạn, giới hạn đồng thời và xử lý cleanup/cancellation theo hợp đồng rõ ràng.

Các ví dụ đầy đủ chạy trên **Java 17+**, trừ những đoạn ghi rõ **Java 21+**. Một số khả năng được bổ sung sau Java 8 được ghi phiên bản cụ thể; không dùng API đã bị thay thế làm giải pháp mặc định. Những điểm liên quan **Java SE 27** được đối chiếu với tài liệu API hiện hành; tính năng còn ở trạng thái preview sẽ **không** được trình bày như API ổn định.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **timeout**, **deadline**, **TTL**, **cancellation** và **shutdown**.
2. Giải thích vì sao **ba bước cùng timeout 1 giây** có thể làm tổng yêu cầu tốn gần 3 giây.
3. Thiết kế một ngân sách thời gian duy nhất, tính thời gian còn lại bằng **System.nanoTime()**.
4. Biết khi nào cần **Instant/Clock** và khi nào cần **monotonic elapsed time**.
5. Hiểu chính xác **CompletableFuture.orTimeout**, **completeOnTimeout**, **copy**, **delayedExecutor**.
6. Phân biệt timeout của **Future.get(timeout)** với việc hoàn tất future bằng lỗi timeout.
7. Không nhầm **future đã timeout/hủy** với **tác vụ I/O đã thực sự dừng**.
8. Nối các bước phụ thuộc bằng **thenCompose** và truyền deadline qua từng bước.
9. Chọn executor, số lượng thread, hàng đợi giới hạn và **RejectedExecutionHandler** phù hợp.
10. Thiết kế **shutdown/awaitTermination/shutdownNow**, không làm rò thread.
11. Hiểu khi nào **virtual threads** (Java 21+) phù hợp và vì sao vẫn cần giới hạn tải.
12. Viết unit test deadline/timeout có tính xác định và không phụ thuộc Thread.sleep.
13. Quan sát metrics về timeout, queue, latency và ngăn retry khuếch đại quá tải.
14. Nhận diện chính xác trạng thái **StructuredTaskScope preview** của JDK hiện hành.

## 2. Bốn khái niệm phải tách biệt

| Khái niệm | Câu hỏi giải quyết | Ví dụ |
|---|---|---|
| **Timeout** | Một thao tác được phép chờ tối đa bao lâu? | Truy vấn database có timeout 300ms |
| **Deadline** | Toàn yêu cầu phải hoàn tất trước hạn nào? | HTTP response còn 800ms |
| **Cancellation** | Khi không muốn kết quả nữa, tác vụ bên dưới có bị dừng không? | Người dùng đóng trang, hủy query đang chạy |
| **Executor** | Ai chạy callback, tác vụ và hàng đợi? | Pool 4 worker threads + queue giới hạn |
| **TTL (time to live)** | Một dữ liệu/phiên có hiệu lực trong bao lâu? | Token hết hạn sau 15 phút |
| **Scheduled work** | Công việc được khởi động khi nào? | Chạy tác vụ lúc 09:00 hoặc sau 5 phút |

**Timeout của thao tác** là một chính sách vận hành; **TTL** thường là thời hạn nghiệp vụ của một dữ liệu. Cả hai có thể biểu diễn bằng Duration nhưng không được sử dụng thay nhau tùy tiện.

**Deadline** có thể được thể hiện bằng:

- Một **Instant** để ghi vào log, truyền qua process/API hoặc giải thích cho người dùng.
- Một **ngân sách theo đồng hồ monotonic** để quyết định việc đã tiêu thụ bao nhiêu thời gian trong một JVM.

Hai biểu diễn phục vụ mục tiêu khác nhau. Một Instant có thể được trao đổi giữa máy; một giá trị System.nanoTime() **không** có mốc epoch và **không được gửi** như thời điểm tuyệt đối cho máy khác.

## 3. Sơ đồ request có nhiều bước phụ thuộc

Giả sử một API có ba bước:

~~~text
Request đến
   │ ngân sách tổng = 1.000ms
   ▼
A. Lấy hồ sơ         260ms
   │ còn 740ms
   ▼
B. Tính hạn mức       410ms
   │ còn 330ms
   ▼
C. Xác nhận          280ms
   │ còn 50ms
   ▼
Trả response trước deadline
~~~

Một cách viết dễ sai:

~~~text
A có timeout 1.000ms
B có timeout 1.000ms
C có timeout 1.000ms

Tổng thời gian tệ nhất ≈ 3.000ms + queue/overhead.
~~~

**Nếu toàn request chỉ có 1.000ms**, bước B phải biết thời gian A đã dùng; C phải biết cả A và B đã tiêu tốn bao nhiêu. Vì vậy thời gian còn lại không được "reset" về một giây khi qua bước mới.

### 3.1. Ngân sách thời gian tổng

Một chiến lược đơn giản:

~~~text
remaining = originalBudget - elapsedSinceRequestStart

Mỗi bước:
    nếu remaining <= 0 → hết ngân sách, không khởi động thêm
    nếu remaining > 0 → gọi tác vụ với timeout <= remaining
    sau khi bước xong → tính lại remaining
~~~

**Lưu ý:** Cách tính ngân sách này giới hạn **thời gian tổng**, không tự dừng công việc bên dưới. Thêm timeout của HTTP client, JDBC/database, hoặc cancellation phù hợp với subsystem.

### 3.2. Deadline không phải phép cộng timeout qua các stage

Nếu có **thenCompose(A).thenCompose(B).thenCompose(C)**, hãy tạo deadline ở **biên request**, rồi truyền **cùng deadline** vào tất cả các bước. Một stage riêng có thể có giới hạn nhỏ hơn ngân sách tổng, ví dụ B tối đa 200ms, nhưng không nên cấp B thời gian lớn hơn request còn lại.

~~~text
stepTimeout = min(remainingOverall, maxAllowedForThisStep)
~~~

Khi còn 0ms, chọn **fail fast** hoặc một fallback theo hợp đồng, không vô tình xếp hàng công việc mới vô ích.

## 4. Tại sao đo timeout bằng System.nanoTime()?

**System.nanoTime()** là nguồn đo thời gian trôi qua trong cùng JVM. Giá trị tuyệt đối của nó có gốc tùy ý, có thể âm, và **không liên quan tới UTC**.

Đối với thời lượng như 500ms:

~~~java
long start = System.nanoTime();

// Thực hiện công việc.
long elapsed = System.nanoTime() - start;
~~~

Nếu cần kiểm tra đã quá thời gian cho phép:

~~~java
long timeoutNanos = TimeUnit.MILLISECONDS.toNanos(500);
boolean timedOut =
        System.nanoTime() - start >= timeoutNanos;
~~~

Đây là các đoạn minh họa, cần import **java.util.concurrent.TimeUnit** ở đoạn thứ hai.

**Ưu tiên phép hiệu** hơn cách so **System.nanoTime() >= start + timeoutNanos**. Theo tài liệu System.nanoTime(), việc cộng để tạo một mốc tuyệt đối có thể gặp vấn đề overflow quanh giá trị gốc tùy ý.

**Giới hạn của phép hiệu:** Hợp đồng nanoTime giải thích rằng hiệu giữa hai giá trị trong cùng JVM có ý nghĩa trong phạm vi thời gian thực tế **dưới khoảng 292 năm**. Timeout dịch vụ thông thường ngắn hơn rất nhiều.

### 4.1. Tại sao không dùng Instant.now() để đo budget nội bộ?

**Instant.now()** phản ánh đồng hồ hệ thống (wall clock), có thể bị điều chỉnh theo đồng bộ thời gian hoặc cấu hình. Nó phù hợp với **createdAt**, **expiresAt** theo thời gian thực, log hoặc contract API.

Đối với **elapsed time của request trong một JVM**, System.nanoTime phù hợp hơn vì không dùng epoch/wall-clock để tính khoảng chênh.

**Không suy rằng nanoTime đo chính xác tới một nanosecond thực tế** chỉ vì đơn vị trả về là nanosecond; độ phân giải phụ thuộc nền tảng.

### 4.2. Khi nào Instant là đúng?

- "Token hết hạn lúc **2026-04-01T10:15Z**": dùng Instant.
- "Request này còn **250ms để hoàn tất trong JVM**": dùng monotonic budget.
- "Hạn cuối được nhận từ hệ thống khác": nhận Instant có offset rõ ràng, đối chiếu bằng Clock tương ứng, tính **Duration còn lại**, rồi chuyển thành ngân sách monotonic tại biên của mình.
- "Deadline cho một cuộc gọi HTTP": cần gắn timeout vào chính HTTP client và/hoặc request context; CompletableFuture wrapper không đủ.

## 5. Mẫu MonotonicBudget có thể kiểm thử

Trong production, nguồn ticker là **System::nanoTime**. Trong unit test, ta có thể inject **LongSupplier** do một **AtomicLong** cung cấp, nhờ đó test tự tiến thời gian mà không cần sleep.

Lưu thành **MonotonicBudgetDemo.java**:

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public class MonotonicBudgetDemo {
    static final class Budget {
        private final LongSupplier ticker;
        private final long startedAtNanos;
        private final long allowedNanos;

        Budget(Duration timeout, LongSupplier ticker) {
            Objects.requireNonNull(timeout);
            this.ticker = Objects.requireNonNull(ticker);

            if (timeout.isNegative() || timeout.isZero()) {
                throw new IllegalArgumentException(
                        "timeout must be positive");
            }

            // toNanos() có thể ném ArithmeticException
            // nếu Duration quá lớn để biểu diễn bằng long.
            this.allowedNanos = timeout.toNanos();
            this.startedAtNanos = ticker.getAsLong();
        }

        long remainingNanos() {
            long elapsed =
                    ticker.getAsLong() - startedAtNanos;

            if (elapsed <= 0L) {
                return allowedNanos;
            }

            if (elapsed >= allowedNanos) {
                return 0L;
            }

            return allowedNanos - elapsed;
        }

        boolean expired() {
            return remainingNanos() == 0L;
        }
    }

    public static void main(String[] args) {
        AtomicLong fakeNanos =
                new AtomicLong(1_000_000_000L);

        Budget budget = new Budget(
                Duration.ofMillis(500),
                fakeNanos::get);

        System.out.println("startMs="
                + TimeUnit.NANOSECONDS.toMillis(
                        budget.remainingNanos()));

        fakeNanos.addAndGet(200_000_000L);

        System.out.println("after200Ms="
                + TimeUnit.NANOSECONDS.toMillis(
                        budget.remainingNanos()));

        fakeNanos.addAndGet(300_000_000L);

        System.out.println("after500Ms="
                + TimeUnit.NANOSECONDS.toMillis(
                        budget.remainingNanos()));

        System.out.println("expired=" + budget.expired());
    }
}
~~~

~~~bash
javac -encoding UTF-8 MonotonicBudgetDemo.java
java MonotonicBudgetDemo
~~~

**Stdout xác định:**

~~~text
startMs=500
after200Ms=300
after500Ms=0
expired=true
~~~

**Giải thích:**

1. Fake ticker bắt đầu tại số nanoseconds do test chọn; số đó không phải timestamp UTC.
2. Constructor chụp mốc ticker ban đầu và thời lượng cho phép.
3. Test thay đổi ticker bằng **AtomicLong.addAndGet**, không dùng Thread.sleep.
4. Sau 200ms mô phỏng còn 300ms; sau 500ms mô phỏng hết ngân sách.
5. Phương thức còn lại trả tối thiểu 0, không trả thời lượng âm cho caller.

**Các giả định của mẫu:** ticker biểu diễn nguồn thời gian tiến hợp lý trong cùng JVM; timeout đủ nhỏ để **Duration.toNanos()** không overflow và khoảng đo không vượt miền phép hiệu long trong thực tế. Với một clock fake bị cố ý lùi, ví dụ trả tối đa ngân sách ban đầu; production **System.nanoTime** là nguồn phù hợp hơn cho elapsed time.

### 5.1. Tạo budget production

Một service có thể dùng:

~~~java
Budget budget = new Budget(
        Duration.ofMillis(800),
        System::nanoTime);
~~~

Đây là đoạn minh họa trong phạm vi class có Budget tương tự ở ví dụ trên. **Budget được tạo một lần khi request bắt đầu**, không tạo lại cho từng bước.

### 5.2. Không truyền nanoTime nguyên giá trị giữa các JVM

Giá trị **System.nanoTime()** có gốc tùy ý **cho mỗi JVM**. Không serialize startedAtNanos vào HTTP headers để máy khác tự so; nó sẽ không cùng mốc.

Ở biên service-to-service, cần truyền **deadline dạng Instant**, **remaining budget có đơn vị rõ ràng**, hoặc cơ chế deadline propagation của protocol/framework. Mỗi máy nên tính **local monotonic budget** mới dựa trên thông tin nhận được, có xem xét clock skew, network transit, độ chính xác và chính sách bảo mật.

## 6. CompletableFuture có những API timeout nào?

Các API thông dụng hiện nay:

| API | Mục đích | Tác động lên future nào? |
|---|---|---|
| **future.get(timeout, unit)** | Chờ trong thread hiện tại tối đa một khoảng | **Không tự hoàn tất** future gốc khi get timeout |
| **future.orTimeout(timeout, unit)** | Nếu chưa xong, hoàn tất exceptionally với TimeoutException | **Chính future gọi orTimeout** |
| **future.completeOnTimeout(value, timeout, unit)** | Nếu chưa xong, hoàn tất bình thường bằng fallback | **Chính future gọi completeOnTimeout** |
| **future.copy()** | Tạo dependent future theo dõi giá trị của future gốc | Bản sao là một future khác |
| **CompletableFuture.delayedExecutor(...)** | Lên lịch chạy command qua một executor sau khoảng trễ | Trả Executor, không phải một future timeout |
| **ScheduledExecutorService.schedule(...)** | Hẹn chạy task sau độ trễ | Trả ScheduledFuture, cần quản lý riêng |
| **Future.cancel(...)** | Yêu cầu hủy hoặc hoàn tất theo trạng thái cancellation | Tùy implementation, **không bảo đảm dừng I/O** |

**orTimeout**, **completeOnTimeout**, **copy** và **delayedExecutor** được bổ sung từ **Java 9**. Chúng đều vẫn là API hiện hành. Với dự án bắt buộc compile Java 8, phải dùng công cụ tương đương hoặc cơ chế timeout của client/scheduler; ví dụ Java 17+ trong bài có thể dùng những API này trực tiếp.

## 7. Future.get(timeout) khác orTimeout thế nào?

**Future.get(500, MILLISECONDS)** có thể chặn thread gọi trong tối đa 500ms. Nếu không có kết quả, nó ném **TimeoutException** cho chính lần chờ đó.

~~~java
try {
    String result = future.get(500, TimeUnit.MILLISECONDS);
    // Sử dụng kết quả.
} catch (TimeoutException ex) {
    // Thread gọi đã hết thời gian chờ.
}
~~~

Đây là đoạn minh họa với future kiểu **Future<String>** và import các lớp tương ứng.

**Quan trọng:** Một lần **get(timeout)** thất bại **không tự thay trạng thái completion** của future. Future có thể tiếp tục chạy và hoàn tất sau đó; một thread khác có thể lấy kết quả.

Ngược lại, **orTimeout(500, MILLISECONDS)** cài cơ chế để **chính CompletableFuture** được hoàn tất bất thường nếu chưa xong trước hạn.

~~~java
CompletableFuture<String> limited =
        original.orTimeout(500, TimeUnit.MILLISECONDS);
~~~

**limited và original là cùng một đối tượng**, không phải copy. Khi timer timeout, CompletableFuture này mang exceptional completion.

### 7.1. Bảng diễn giải

| Trường hợp | Người gọi nhận gì? | Future nguồn sau khi hết thời gian chờ |
|---|---|---|
| **get(timeout)** | Checked TimeoutException từ lệnh get | Có thể vẫn **pending** |
| **orTimeout(...)** | Composed future có exceptional completion | Chính future đã gọi **bị hoàn tất exceptionally** |
| **completeOnTimeout(...)** | Future có giá trị fallback | Chính future đã gọi **hoàn tất bình thường** |
| **copy().orTimeout(...)** | Nhánh copy có thể timeout | Future gốc **không bị nhánh timeout hoàn tất** |

**Đây là khác biệt kiến trúc quan trọng khi future gốc được chia sẻ**. Một timeout của người gọi A không nên vô tình làm hỏng future đang được người gọi B dùng.

## 8. orTimeout và completeOnTimeout là thao tác trên cùng object

Hai phương thức có hợp đồng **trả về chính CompletableFuture nhận lời gọi**:

~~~java
CompletableFuture<String> original =
        new CompletableFuture<>();

CompletableFuture<String> same =
        original.orTimeout(0, TimeUnit.MILLISECONDS);

// same == original là true.
~~~

Đây là đoạn minh họa Java 9+, có thể chạy trên Java 17+.

**Không nhầm "cú pháp chaining" với "tạo stage mới".** Các phương thức như **thenApply** và **thenCompose** tạo stage phụ thuộc; nhưng **orTimeout** gắn điều kiện thời gian cho chính future đã gọi.

### 8.1. completeOnTimeout dùng cho fallback có ý nghĩa

~~~java
CompletableFuture<String> output =
        new CompletableFuture<String>()
                .completeOnTimeout(
                        "not-available",
                        2,
                        TimeUnit.SECONDS);
~~~

Nếu future chưa hoàn tất sau 2 giây, nó được hoàn tất **bình thường** với giá trị fallback. Điều này phù hợp với dữ liệu cache tùy chọn hay thông tin phụ trợ có thể bị thiếu.

**Không dùng completeOnTimeout trả "thanh toán thành công" hoặc "đã đặt hàng"** nếu thao tác thật có thể vẫn chạy. Fallback không nên nói dối về side effect của request.

### 8.2. TimeoutException không chứng minh việc remote đã dừng

Khi future timeout, I/O HTTP, truy vấn database hoặc một thao tác trên executor có thể vẫn thực thi.

~~~text
HTTP request ───────────── đang gửi / server đang xử lý ─────►
      │
      └──── future.orTimeout(300ms)
                     │
                     └── caller thấy TimeoutException

Remote side effect có thể xảy ra dù caller không nhận được kết quả.
~~~

Nếu muốn dừng request thực sự, cần hỗ trợ **cancellation/abort của HTTP client**, statement timeout của driver/database hoặc giao thức phù hợp. **Tác vụ có thể không thể hủy an toàn** sau khi đã ghi dữ liệu; thiết kế idempotency và trạng thái "unknown" khi kết quả không chắc chắn.

## 9. Tạo nhánh timeout riêng bằng copy()

Vì orTimeout làm thay đổi completion của future nhận lời gọi, khi future gốc chia sẻ với các caller khác, một lựa chọn hiện đại là:

~~~java
CompletableFuture<T> view =
        original.copy().orTimeout(
                timeoutNanos,
                TimeUnit.NANOSECONDS);
~~~

Đây là **đoạn minh họa generic**, cần khai báo original và timeoutNanos đúng kiểu. **copy()** tạo một future mới sẽ theo dõi kết quả của original, nhưng timeout chỉ được gắn vào nhánh copy này.

**Hệ quả quan trọng:**

- Caller nhận **view** có thể bị timeout.
- Future **original** vẫn có thể pending và hoàn tất về sau.
- Những caller khác đang quan sát original không tự nhận timeout vì nhánh view.
- **copy không hủy công việc thực tế**; nó tách trạng thái quan sát, không thay transport.

### 9.1. Ví dụ đầy đủ: timeout, copy, fallback và get(0)

Lưu thành **CompletableFutureTimeoutDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CompletableFutureTimeoutDemo {
    public static void main(String[] args) throws Exception {
        CompletableFuture<String> direct =
                new CompletableFuture<>();

        CompletableFuture<String> same =
                direct.orTimeout(0, TimeUnit.MILLISECONDS);

        System.out.println("sameObject=" + (same == direct));

        try {
            direct.join();
        } catch (CompletionException ex) {
            System.out.println("directCause="
                    + ex.getCause().getClass().getSimpleName());
        }

        CompletableFuture<String> pending =
                new CompletableFuture<>();

        try {
            pending.get(0, TimeUnit.MILLISECONDS);
        } catch (TimeoutException ex) {
            System.out.println("getTimeout="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("stillPending=" + !pending.isDone());

        CompletableFuture<String> original =
                new CompletableFuture<>();

        CompletableFuture<String> view =
                original.copy().orTimeout(
                        0, TimeUnit.MILLISECONDS);

        try {
            view.join();
        } catch (CompletionException ex) {
            System.out.println("branchCause="
                    + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("originalPending="
                + !original.isDone());

        original.complete("LATE");

        System.out.println("originalValue=" + original.join());

        CompletableFuture<String> fallback =
                new CompletableFuture<String>()
                        .completeOnTimeout(
                                "FALLBACK",
                                0,
                                TimeUnit.MILLISECONDS);

        System.out.println("fallbackValue=" + fallback.join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 CompletableFutureTimeoutDemo.java
java CompletableFutureTimeoutDemo
~~~

**Stdout:**

~~~text
sameObject=true
directCause=TimeoutException
getTimeout=TimeoutException
stillPending=true
branchCause=TimeoutException
originalPending=true
originalValue=LATE
fallbackValue=FALLBACK
~~~

**Giải thích:**

1. **same==direct** vì orTimeout trả chính đối tượng nhận lời gọi.
2. Khi future **direct** còn pending và timeout bằng 0, timeout timer khiến nó hoàn tất bất thường.
3. **get(0, ...)** trên future pending ném TimeoutException cho caller, nhưng **pending vẫn pending**.
4. **copy().orTimeout(0, ...)** tạo view bị timeout; **original** không bị hoàn tất bởi timeout nhánh.
5. Sau đó original vẫn có thể **complete("LATE")**; view đã timeout không đổi kết quả.
6. **completeOnTimeout("FALLBACK", 0, ...)** cung cấp giá trị fallback.

**Vì sao có timeout=0?** Ví dụ dùng giá trị 0 để kiểm chứng contract ngay, **không đợi đồng hồ**; điều kiện timeout vẫn được thực hiện qua cơ chế của CompletableFuture. Trong production, dùng giới hạn dương có ý nghĩa với deadline thực tế.

## 10. Thiết kế deadline chung cho pipeline nhiều bước

Với **thenCompose**, một pipeline thường có dạng:

~~~text
loadUserAsync(id)
   │ User
   ▼
loadCartAsync(user)
   │ Cart
   ▼
reserveAsync(cart)
   │ Reservation
   ▼
respond
~~~

**Sai lầm thường gặp:** Gắn **orTimeout(800ms)** cho từng bước, khiến một request "còn 800ms" bị cấp lại 800ms tại mỗi bước. Điều này có thể kéo tổng độ trễ lên nhiều lần ngân sách mục tiêu.

**Thiết kế tốt hơn:**

1. Tạo **budget tổng** một lần tại đầu request.
2. Trước khi khởi động B, đọc **budget.remainingNanos()**.
3. Nếu không còn thời gian, fail fast hoặc fallback đúng nghĩa.
4. Nếu còn, truyền timeout **min(remaining, stepLimit)** xuống HTTP/DB client.
5. Tạo **future view** của toàn pipeline với giới hạn còn lại.
6. Nếu timeout, thực hiện **cancel/abort transport** khi an toàn và được API hỗ trợ.
7. Ghi lại outcome có thể không chắc chắn nếu remote đã nhận tác vụ.

### 10.1. Không đặt timeout lớn hơn ngân sách còn lại

Một công thức:

~~~text
overallBudget = 800ms
elapsed       = 470ms
remaining     = 330ms
stepLimit     = 500ms

effectiveTimeout = min(330ms, 500ms) = 330ms
~~~

Không dùng stepLimit=500ms nguyên vẹn vì bước hiện tại không có quyền sử dụng vượt deadline tổng.

### 10.2. Đọc lại remaining trước mỗi thao tác

Mẫu mã minh họa cho một service đã có Budget:

~~~java
long remaining = budget.remainingNanos();

if (remaining == 0L) {
    return CompletableFuture.failedFuture(
            new TimeoutException("deadline exceeded"));
}

return api.fetchAsync(
        request,
        Duration.ofNanos(remaining));
~~~

Đây là **đoạn minh họa** Java 17+, trong đó api.fetchAsync nhận timeout do ứng dụng định nghĩa; không phải chữ ký bắt buộc của một HTTP client Java tiêu chuẩn.

**Quan trọng:** một client có thể yêu cầu timeout theo millisecond (hoặc độ phân giải riêng). Chuyển đổi đơn vị có thể làm tròn xuống 0 và thành "không timeout" nếu API diễn giải 0 theo nghĩa vô hạn. Hãy kiểm tra hợp đồng và dùng chuyển đổi an toàn (ví dụ ceil lên 1ms khi còn sub-ms) nếu phù hợp, đồng thời không cho phép một bước vượt deadline tổng.

### 10.3. Races giữa kiểm tra và khởi động

Sau khi kiểm tra budget còn 300ms, vẫn có thời gian trôi trước khi request thật được gửi. **Đây là race có thật**, không thể giải quyết bằng cách đọc clock một lần rồi coi kết quả bất biến. Cần cài deadline trong client/transport, bảo đảm cancellation và xử lý response đến muộn theo hợp đồng.

**Deadline là giới hạn theo dõi và chính sách hành động**, không phải phép thuật dừng ngay mọi CPU/I/O chính xác tại nanosecond.

## 11. Một ví dụ pipeline deadline có thể biên dịch

Ví dụ sau dùng **hai bước phụ thuộc**, kết quả xác định, một Budget dùng chung, executor được cấp từ bên ngoài và **copy().orTimeout(...)** cho đường quan sát. Nó không giả lập network hoặc I/O thực tế.

Lưu thành **DeadlinePipelineDemo.java**:

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.LongSupplier;

public class DeadlinePipelineDemo {
    static final class Budget {
        private final long initialNanos;
        private final long startNanos;
        private final LongSupplier ticker;

        Budget(Duration timeout, LongSupplier ticker) {
            Objects.requireNonNull(timeout);
            this.ticker = Objects.requireNonNull(ticker);

            if (timeout.isNegative() || timeout.isZero()) {
                throw new IllegalArgumentException(
                        "timeout must be positive");
            }

            initialNanos = timeout.toNanos();
            startNanos = ticker.getAsLong();
        }

        long remainingNanos() {
            long elapsed = ticker.getAsLong() - startNanos;

            if (elapsed <= 0L) {
                return initialNanos;
            }

            return elapsed >= initialNanos
                    ? 0L
                    : initialNanos - elapsed;
        }
    }

    static CompletableFuture<Integer> loadAccountAsync(
            String accountId, Executor executor) {

        return CompletableFuture.supplyAsync(
                () -> accountId.length(),
                executor);
    }

    static CompletableFuture<String> loadSummaryAsync(
            int value, Executor executor) {

        return CompletableFuture.supplyAsync(
                () -> "SUMMARY-" + (value * 10),
                executor);
    }

    static CompletableFuture<String> run(
            String accountId,
            Budget budget,
            Executor executor) {

        if (budget.remainingNanos() == 0L) {
            return CompletableFuture.failedFuture(
                    new TimeoutException("deadline exceeded"));
        }

        CompletableFuture<String> workflow =
                loadAccountAsync(accountId, executor)
                        .thenCompose(value -> {
                            if (budget.remainingNanos() == 0L) {
                                return CompletableFuture.failedFuture(
                                        new TimeoutException(
                                                "deadline exceeded"));
                            }

                            return loadSummaryAsync(value, executor);
                        });

        long remaining = budget.remainingNanos();

        if (remaining == 0L) {
            return CompletableFuture.failedFuture(
                    new TimeoutException("deadline exceeded"));
        }

        return workflow.copy().orTimeout(
                remaining, TimeUnit.NANOSECONDS);
    }

    public static void main(String[] args) {
        ExecutorService executor =
                Executors.newFixedThreadPool(2);

        try {
            Budget budget = new Budget(
                    Duration.ofSeconds(5),
                    System::nanoTime);

            String result = run("user", budget, executor).join();

            System.out.println("result=" + result);
        } finally {
            executor.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DeadlinePipelineDemo.java
java DeadlinePipelineDemo
~~~

**Stdout trong điều kiện thực thi bình thường và không vượt 5 giây:**

~~~text
result=SUMMARY-40
~~~

**Lưu ý kiểm thử:** Vì chương trình dùng Clock thật và ExecutorService thật, rất khó hứa stdout trong mọi môi trường cực kỳ quá tải. Nếu tổng công việc không kịp 5 giây, chương trình có thể kết thúc bằng CompletionException có nguyên nhân TimeoutException. Đây là hành vi đúng của budget, không phải sai của thenCompose. Để unit test xác định, sử dụng fake ticker và CompletableFuture điều khiển bằng complete(...) như các mục khác.

**Các giới hạn cố ý của demo:**

- Không có HTTP/DB thật, nên không minh họa transport timeout hoặc hủy request thật.
- **copy().orTimeout** tạo timeout cho đường kết quả; các bước supplyAsync có thể vẫn chạy sau timeout.
- Vì executor được tạo tại main, main chịu trách nhiệm shutdown.
- **Executor shutdown** không đồng nghĩa hủy task ngay; cần awaitTermination với chính sách rõ khi production dừng ứng dụng.

### 11.1. Vì sao dùng thenCompose?

Bước **loadSummaryAsync** cần kết quả từ **loadAccountAsync** nên thenCompose là lựa chọn đúng. Nếu hai bước độc lập, có thể khởi động cả hai trước rồi dùng thenCombine, nhưng vẫn phải áp chung ngân sách tổng.

## 12. Timeout ở nhiều tầng: không thể chỉ đặt một nơi

Một hệ thống thực tế có nhiều tầng:

~~~text
HTTP ingress deadline
       │
       ▼
Business service budget
       │
       ├── Database query timeout
       │
       ├── Downstream HTTP connect timeout
       │       └── Response/request timeout
       │
       ├── Async pipeline timeout view
       │
       └── Executor admission and queue wait budget
~~~

### 12.1. Các loại timeout khi gọi HTTP

- **Connect timeout:** chờ thiết lập kết nối.
- **Request/response timeout:** thời gian cho một lời gọi hoặc vòng đời request (tùy API).
- **Read/socket timeout:** thời gian chờ dữ liệu ở tầng transport, semantics tùy thư viện.
- **Deadline tổng:** ngân sách từ khi request được chấp nhận, bao gồm cả xếp hàng và nhiều downstream call.

**Không coi connect timeout bằng end-to-end request timeout.** Một kết nối thiết lập nhanh vẫn có thể nhận response rất chậm.

### 12.2. java.net.http.HttpClient (Java 11+)

**HttpClient.Builder.connectTimeout(Duration)** đặt giới hạn kết nối trong những tình huống kết nối mới cần được thiết lập. **HttpRequest.Builder.timeout(Duration)** đặt timeout cho request cụ thể.

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(300))
        .build();

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/api"))
        .timeout(Duration.ofMillis(700))
        .GET()
        .build();
~~~

Đây là **đoạn minh họa cấu hình**, yêu cầu import **java.net.URI**, **java.net.http.HttpClient**, **java.net.http.HttpRequest** và **java.time.Duration**. Không thực hiện kết nối mạng trong bài.

**Client timeout là lớp bảo vệ cho I/O thật.** Nếu caller còn 250ms, không nên giữ request timeout=700ms cố định. Tính timeout hiệu lực từ budget và giới hạn theo hợp đồng riêng, rồi tạo request tương ứng.

### 12.3. Database timeout

Với JDBC, **Statement.setQueryTimeout(int seconds)** có thể được sử dụng để yêu cầu giới hạn thời gian thực thi statement theo driver/database, nhưng độ phân giải là giây và chính sách hủy phụ thuộc driver. Các thư viện/driver khác có API timeout riêng.

Đừng cho rằng **CompletableFuture.orTimeout(300ms)** bao quanh một JDBC blocking query tự ngắt được query đang chạy. Khi cần thời gian ngắn hơn một giây hoặc cancellation tin cậy, chọn API driver/database phù hợp hoặc cơ chế quản lý query ở server.

### 12.4. Queue wait cũng tiêu thụ ngân sách

Một task chờ 400ms trong executor queue rồi mới chạy 300ms đã tốn 700ms tổng, dù thời gian CPU bên trong task chỉ 300ms. Nếu deadline đo tại request arrival, **thời gian chờ hàng đợi phải được tính**.

**Chỉ đặt timeout bên trong task sau khi nó được start có thể bỏ qua queue wait**, khiến request vượt SLA trước khi tác vụ bắt đầu.

## 13. Executor, ExecutorService và ThreadPoolExecutor

Ba cấp abstraction:

| API | Vai trò |
|---|---|
| **Executor** | Thực thi Runnable thông qua execute |
| **ExecutorService** | Thêm submit, shutdown, awaitTermination, Future |
| **ThreadPoolExecutor** | Cấu hình chi tiết core/max threads, queue, keepAlive, rejection |
| **ScheduledExecutorService** | Lên lịch chạy task theo độ trễ hoặc chu kỳ |
| **ForkJoinPool** | Pool tối ưu cho các tác vụ chia nhỏ/ghép và work stealing |
| **Virtual-thread-per-task executor** | Tạo virtual thread cho mỗi task, Java 21+ |

**Một Executor không nhất thiết tạo thread mới.** Nó có thể chạy trực tiếp trong calling thread, dùng pool, hoặc sử dụng một cơ chế khác theo implementation.

### 13.1. Mối liên hệ với CompletableFuture

~~~java
CompletableFuture<Integer> future =
        CompletableFuture.supplyAsync(
                () -> 21,
                executor);
~~~

Đây là đoạn minh họa; **executor** đã được khai báo.

**supplyAsync** gửi supplier đến executor. Khi cần một callback có chính sách thực thi rõ:

~~~java
CompletableFuture<Integer> result =
        future.thenApplyAsync(
                n -> n * 2,
                executor);
~~~

**thenApply** không Async có thể chạy inline trên thread hoàn tất source, không hứa sử dụng executor cũ. **thenApplyAsync/thenComposeAsync(..., executor)** làm rõ nơi thực thi callback theo hợp đồng Executor.

### 13.2. CompletableFuture commonPool

Các phương thức Async không nhận Executor của CompletableFuture tiêu chuẩn thường dùng **ForkJoinPool.commonPool()**, với những ngoại lệ/fallback như tài liệu JDK mô tả.

**Không mặc định đưa blocking I/O lâu và số lượng lớn vào common pool.** Khi nhiều callback chặn, pool có thể bị nghẽn hoặc gây starvation. Chọn asynchronous client hoặc Executor phù hợp với workload.

## 14. Một ví dụ rõ ràng về executor lifecycle

Lưu thành **ExecutorLifecycleDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ExecutorLifecycleDemo {
    public static void main(String[] args)
            throws InterruptedException {

        ExecutorService executor =
                Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<Integer> result =
                    CompletableFuture.supplyAsync(
                            () -> 21,
                            executor)
                            .thenApplyAsync(
                                    n -> n * 2,
                                    executor);

            System.out.println("answer=" + result.join());
        } finally {
            executor.shutdown();

            boolean stopped =
                    executor.awaitTermination(
                            2, TimeUnit.SECONDS);

            if (!stopped) {
                executor.shutdownNow();
            }

            System.out.println("terminated="
                    + executor.isTerminated());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExecutorLifecycleDemo.java
java ExecutorLifecycleDemo
~~~

**Stdout trong ví dụ không có task tồn đọng:**

~~~text
answer=42
terminated=true
~~~

**Giải thích:**

1. Executor được tạo một lần cho cả workflow, không phải mỗi callback.
2. Hai stage dùng cùng executor có chủ đích.
3. join tại main là một ranh giới đồng bộ có chủ đích; không dùng join trong mapper.
4. Sau khi đã biết result hoàn tất, main gọi shutdown để không nhận thêm task mới.
5. **awaitTermination** chờ pool ngừng hoặc hết thời gian; khi quá hạn mới thử shutdownNow.
6. Trong hệ thống thật, cần xử lý **InterruptedException** và thực hiện shutdown theo lifecycle cấp ứng dụng thay vì tạo pool trong mỗi request.

**Lưu ý:** Đoạn demo khai báo throws InterruptedException và không thể hiện full shutdown khi main bị interrupt. Phần tiếp theo mô tả mẫu shutdown production có xử lý interrupt.

## 15. shutdown, awaitTermination, shutdownNow và close

Vòng đời executor có các trạng thái quan trọng:

~~~text
RUNNING
   │ shutdown()
   ▼
SHUTDOWN: không nhận task mới, xử lý task đã nhận
   │ mọi task hoàn tất
   ▼
TERMINATED
~~~

**shutdownNow()** là nỗ lực khẩn cấp để hủy task chưa chạy và interrupt task đang chạy; **không bảo đảm mọi task dừng ngay**, vì code có thể không phản ứng với interrupt.

### 15.1. Mẫu graceful shutdown có thời gian chờ

~~~java
static void stopExecutor(
        ExecutorService pool,
        long graceSeconds) {

    pool.shutdown();

    try {
        if (!pool.awaitTermination(
                graceSeconds, TimeUnit.SECONDS)) {

            pool.shutdownNow();

            if (!pool.awaitTermination(
                    graceSeconds, TimeUnit.SECONDS)) {

                System.err.println(
                        "Executor did not terminate");
            }
        }
    } catch (InterruptedException ex) {
        pool.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

Đây là **phương thức minh họa** trong một class, cần import **ExecutorService** và **TimeUnit**.

**Tại sao phải restore interrupt?** Một thread bị interrupt trong lúc chờ shutdown có thể mang tín hiệu hủy của ứng dụng. Khôi phục interrupted flag giúp code bên ngoài nhìn thấy tín hiệu đó. Không nuốt InterruptedException âm thầm.

### 15.2. ExecutorService.close() trong Java 19+

Từ **Java 19**, ExecutorService triển khai **AutoCloseable.close()**. Trên Java 21+, có thể viết:

~~~java
try (ExecutorService pool =
             Executors.newVirtualThreadPerTaskExecutor()) {

    // Submit và đợi các task thuộc scope của pool.
}
~~~

Đây là **đoạn minh họa Java 21+** (virtual thread executor) chứ không phải ví dụ Java 17.

**close()** khởi tạo orderly shutdown và **chờ executor kết thúc**. Đây là hành vi thuận tiện khi vòng đời ngắn và bạn muốn đợi mọi task, nhưng **không phải "ngừng ngay không chờ"**. Nếu có task treo và bạn cần tối đa N giây cho shutdown, hãy dùng **shutdown → awaitTermination → shutdownNow** với thời gian chờ kiểm soát được.

### 15.3. Ai sở hữu executor?

- **Application-level singleton pool:** application/container lifecycle chịu trách nhiệm shutdown, không shutdown sau mỗi request.
- **Pool tạo cục bộ cho một công việc có vòng đời rõ:** người tạo phải close/shutdown.
- **Executor do framework cung cấp:** tuân theo quy tắc ownership của framework, không tự gọi shutdown trên tài nguyên bạn không sở hữu.
- **ForkJoinPool.commonPool():** không coi nó như pool sở hữu riêng để gọi shutdown theo từng request.

**Không tạo một ExecutorService trong mỗi lệnh gọi API rồi quên shutdown.** Thread và queue là tài nguyên phải được quản lý.

## 16. Vì sao Executors.newFixedThreadPool không phải "bounded" hoàn toàn?

**Executors.newFixedThreadPool(n)** tạo pool có số worker thread tương đối cố định, nhưng sử dụng **hàng đợi không giới hạn** theo hợp đồng API.

~~~java
ExecutorService pool =
        Executors.newFixedThreadPool(4);
~~~

Đây là đoạn minh họa.

Số worker bị giới hạn **không đồng nghĩa queue bị giới hạn**. Nếu request đến nhanh hơn tốc độ xử lý, hàng đợi có thể tăng, chiếm bộ nhớ và làm tác vụ bắt đầu khi deadline đã hết.

### 16.1. Cần hai loại giới hạn

1. **Giới hạn concurrency:** bao nhiêu công việc được thực thi đồng thời.
2. **Giới hạn queue/admission:** bao nhiêu công việc được phép chờ.

Một thiết kế chỉ giới hạn số thread nhưng cho queue vô tận có thể tạo **latency rất cao** dưới tải. Đối với dịch vụ cần SLA, đôi khi từ chối sớm (**fail fast**) tốt hơn nhận tất cả rồi để chúng quá hạn trong queue.

## 17. ThreadPoolExecutor với queue hữu hạn và AbortPolicy

Có thể tạo executor với:

~~~java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2,                     // corePoolSize
        4,                     // maximumPoolSize
        30L,                   // keepAliveTime
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(16),
        new ThreadPoolExecutor.AbortPolicy());
~~~

Đây là **đoạn minh họa**, cần import từ **java.util.concurrent**. Cấu hình chỉ là ví dụ về cấu trúc, **không phải khuyến nghị kích thước cố định cho mọi ứng dụng**.

Khi pool/queue không thể nhận thêm tác vụ, **AbortPolicy** ném **RejectedExecutionException**. Caller cần chọn chính sách HTTP error, backpressure, fallback hoặc retry có kiểm soát.

### 17.1. Các RejectedExecutionHandler phổ biến

| Chính sách | Hành vi | Cảnh báo |
|---|---|---|
| **AbortPolicy** | Ném RejectedExecutionException | Rõ ràng, phù hợp fail-fast nếu caller xử lý |
| **CallerRunsPolicy** | Caller tự chạy task khi executor còn hoạt động | Có thể chặn thread xử lý request/event loop |
| **DiscardPolicy** | Im lặng bỏ task | Dễ mất công việc và tạo future chờ vô hạn |
| **DiscardOldestPolicy** | Loại task chờ cũ rồi retry | Có thể làm mất yêu cầu cũ; không phù hợp khi cần bảo đảm xử lý |

**Không chọn DiscardPolicy để "tối ưu" dịch vụ cần trả kết quả cho mỗi request**; việc bỏ một Runnable mà không hoàn tất tương ứng future có thể khiến caller chờ không có kết quả. Với tác vụ có side effect, silent discard còn có thể vi phạm tính toàn vẹn nghiệp vụ.

### 17.2. Ví dụ kiểm tra rejection xác định

Lưu thành **BoundedExecutorDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedExecutorDemo {
    public static void main(String[] args)
            throws InterruptedException {

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1,
                1,
                0L,
                TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();

            // Worker đang bận, một Runnable chờ trong queue.
            pool.execute(() -> {});

            try {
                // Worker bận và queue đã đầy.
                pool.execute(() -> {});
            } catch (RejectedExecutionException ex) {
                System.out.println("rejected=true");
            }

            System.out.println("queueSize="
                    + pool.getQueue().size());
        } finally {
            release.countDown();
            pool.shutdown();
            System.out.println("terminated="
                    + pool.awaitTermination(
                            2, TimeUnit.SECONDS));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 BoundedExecutorDemo.java
java BoundedExecutorDemo
~~~

**Stdout trong điều kiện worker đáp ứng bình thường:**

~~~text
rejected=true
queueSize=1
terminated=true
~~~

**Giải thích:**

- Pool có một worker và queue một phần tử.
- **started.await()** bảo đảm worker đã bắt đầu và đang chờ release.
- Task thứ hai chiếm queue.
- Task thứ ba bị từ chối với AbortPolicy.
- finally giải phóng latch và thực hiện shutdown/awaitTermination.

**Lưu ý production:** Không nên dựa vào một cấu hình pool cực nhỏ làm mặc định. Đây là test của cơ chế admission. Ở dịch vụ thật, cần xem throughput, thời gian chờ, số core, blocking ratio, kích cỡ queue, memory và SLA để cấu hình.

## 18. Executor và deadline phải được thiết kế cùng nhau

Xét một task có ngân sách 300ms nhưng phải chờ queue 500ms. Khi task bắt đầu, ngân sách đã hết.

**Cách xử lý:**

- Đo deadline từ lúc **request vào hệ thống**, không phải lúc worker được cấp.
- Kiểm tra remaining **trước khi submit**.
- Kiểm tra remaining lại **ngay khi task bắt đầu**, nếu tác vụ hỗ trợ fail fast.
- Dùng bounded queue/concurrency để tránh nhận quá nhiều công việc vô ích.
- Truyền timeout hiệu lực vào I/O client hoặc database.
- Nếu executor từ chối, trả **overload/retryable response** có chính sách, không nhầm với timeout downstream.
- Tránh retry tự động khiến queue càng đầy và delay càng tăng.

### 18.1. Một ví dụ kiểm tra budget trong worker

~~~java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> {
            if (budget.remainingNanos() == 0L) {
                throw new CompletionException(
                        new TimeoutException(
                                "budget expired before start"));
            }

            return performWork();
        }, executor);
~~~

Đây là **đoạn minh họa**, cần các biến budget, executor và performWork, import CompletionException/TimeoutException.

**Đây không phải giải pháp đủ:** Nếu performWork() blocking và không có timeout, nó vẫn có thể chạy quá hạn. Kiểm tra trước lúc bắt đầu **chỉ là một lớp bảo vệ**.

## 19. Virtual threads trong Java 21+

**Virtual threads** được chuẩn hóa trong Java 21. Với nhiều thao tác I/O blocking theo kiểu một request/một công việc, virtual threads giúp giảm chi phí giữ một platform thread riêng cho mỗi tác vụ đang chờ I/O.

Factory hiện đại:

~~~java
ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor();
~~~

**Từ Java 21 trở lên**, mỗi task được submit tạo một virtual thread mới. Executor này **không giới hạn số virtual threads được tạo**, theo tài liệu API.

**Không suy rằng virtual threads làm CPU chạy song song vô hạn hoặc loại bỏ giới hạn database connection, HTTP connection, API rate limit, bộ nhớ.** Nếu tạo vô hạn request, downstream vẫn có thể bị quá tải.

### 19.1. Ví dụ đầy đủ cho Java 21+

Lưu thành **VirtualThreadExecutorDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadExecutorDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            Future<Boolean> result =
                    executor.submit(() ->
                            Thread.currentThread().isVirtual());

            System.out.println("virtual=" + result.get());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 VirtualThreadExecutorDemo.java
java VirtualThreadExecutorDemo
~~~

**Stdout trên Java 21+:**

~~~text
virtual=true
~~~

**Giải thích:**

- newVirtualThreadPerTaskExecutor tạo virtual thread cho task.
- get() trong main là ranh giới chờ kết quả.
- ExecutorService.close() khi ra khỏi try-with-resources sẽ shutdown và chờ task hoàn tất.
- **Đây không phải mã chạy trên Java 17** vì factory virtual thread chưa có.

### 19.2. Virtual threads không thay admission control

Khi sử dụng virtual threads, một thiết kế nên kiểm soát concurrency **ở ranh giới gọi downstream**, ví dụ qua:

- **Semaphore** giới hạn số lời gọi tới DB/API.
- Giới hạn pool connection/HTTP requests.
- Rate limiting theo tenant hoặc route.
- Bounded work queue hoặc thành phần admission cấp service.
- Timeouts và deadlines được truyền xuống mỗi request.

**Đừng chỉ đặt semaphore bên trong mỗi virtual thread nếu hệ thống đã tạo hàng triệu thread trước khi được nhận vào tài nguyên**: chúng vẫn tiêu thụ tài nguyên. Có thể cần giới hạn **trước khi submit** hoặc cơ chế admission phù hợp.

### 19.3. CPU-bound và blocking I/O

- **CPU-bound:** số core là giới hạn vật lý quan trọng; virtual threads không tạo thêm CPU.
- **I/O-bound với blocking API hỗ trợ tốt:** virtual threads thường giúp dùng mô hình lập trình tuần tự dễ đọc hơn với nhiều request đồng thời.
- **Nonblocking I/O:** CompletableFuture/async APIs vẫn phù hợp khi cần pipeline, composition hoặc kiến trúc đã dùng I/O phi chặn.
- **Executor mỗi task:** cần sở hữu và shutdown theo lifecycle; không tạo rồi quên.

**Không bắt buộc chuyển toàn bộ CompletableFuture sang virtual threads**. Chọn mô hình phù hợp với stack, thư viện, khả năng test, telemetry và nhu cầu concurrency.

## 20. Structured concurrency theo trạng thái Java SE 27

**StructuredTaskScope** xuất hiện trong các bản JDK hiện đại như một mô hình gom các subtasks vào một scope có vòng đời rõ ràng, hỗ trợ chờ kết quả, cancellation và cấu hình timeout trong các API preview.

**Tính đến Java SE 27, StructuredTaskScope vẫn là PREVIEW API**, theo Oracle JDK 27 documentation. Chương trình sử dụng nó cần bật preview features, và hợp đồng API có thể thay đổi giữa các bản JDK.

Vì Special Note yêu cầu kiến thức **vẫn áp dụng hiện nay và không dùng kiến thức đã lỗi thời**, bài này:

- Giới thiệu **khái niệm structured concurrency** như lựa chọn đang được phát triển, không gọi nó là API ổn định.
- **Không** đưa những snippet preview có chữ ký từng thay đổi giữa Java 21–27 làm mẫu mặc định cho Java 17.
- Với ứng dụng production cần API ổn định và tương thích rộng, dùng **ExecutorService**, **Future/CompletableFuture**, cancellation/timeout của client và lifecycle rõ ràng.
- Nếu dự án chủ động chấp nhận JDK preview, chỉ dùng **đúng phiên bản JDK đang chạy** và tài liệu preview của nó.

**Tránh các hướng dẫn đã cũ** về tên constructor/method của StructuredTaskScope từ các bản preview trước: chữ ký của API này đã thay đổi; không sao chép ví dụ chưa đối chiếu phiên bản JDK.

## 21. ScheduledExecutorService và delayedExecutor khác timeout

Một tác vụ "chạy sau 5 giây" không tự tương đương với "công việc này có deadline 5 giây".

### 21.1. ScheduledExecutorService

~~~java
ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

ScheduledFuture<?> scheduled =
        scheduler.schedule(
                () -> doSomething(),
                5,
                TimeUnit.SECONDS);
~~~

Đây là **đoạn minh họa**, doSomething cần được định nghĩa.

- Scheduler được yêu cầu **khởi động** Runnable sau khoảng trễ.
- ScheduledFuture đại diện cho công việc đã đặt lịch.
- **scheduled.cancel(...)** có thể hủy lịch khi chưa chạy hoặc đưa tín hiệu interrupt khi phù hợp.
- Không tự giới hạn **thời lượng chạy** của doSomething sau khi nó bắt đầu.
- Scheduler cần **shutdown** bởi component sở hữu.

### 21.2. Ví dụ đầy đủ: hủy lịch chưa chạy

Lưu thành **ScheduledTaskDemo.java**:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class ScheduledTaskDemo {
    public static void main(String[] args) {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        try {
            ScheduledFuture<?> task = scheduler.schedule(
                    () -> System.out.println("SHOULD_NOT_RUN"),
                    10,
                    TimeUnit.DAYS);

            System.out.println("cancelled="
                    + task.cancel(false));
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScheduledTaskDemo.java
java ScheduledTaskDemo
~~~

**Stdout:**

~~~text
cancelled=true
~~~

**Giải thích:** Công việc được hẹn quá xa, nên ví dụ hủy trước khi tới lịch mà không cần sleep. Đây là minh họa **scheduled cancellation**, không phải deadline thực thi.

### 21.3. CompletableFuture.delayedExecutor

~~~java
Executor delayed = CompletableFuture.delayedExecutor(
        500,
        TimeUnit.MILLISECONDS,
        baseExecutor);
~~~

Đây là **đoạn minh họa**, baseExecutor cần được khai báo.

Factory trả một **Executor** đưa task sang baseExecutor sau khoảng trễ. Nó **không** tự biến task thành một future có deadline, không đảm bảo task sẽ hoàn tất trong 500ms, và không thay thế shutdown của baseExecutor.

### 21.4. Clock.fixed không làm scheduler chạy

Một Clock cố định giúp kiểm thử quy tắc dùng **Instant.now(clock)**, nhưng **không tự điều khiển ScheduledExecutorService** hay CompletableFuture timers dựa trên thời gian thực. Nếu muốn test scheduling không ngủ chờ, cần một **fake scheduler / controllable executor / test clock của framework**, không chỉ Clock.fixed.

## 22. Cancellation thực tế và InterruptedException

**CompletableFuture.cancel(...)** làm chính future mang trạng thái cancellation. Theo hợp đồng CompletableFuture, tham số **mayInterruptIfRunning** không bảo đảm interrupt công việc đang thực thi như một số Future implementation khác.

Trong khi đó, với **Future** do một ExecutorService tạo bằng **submit**, cancel(true) thường là nỗ lực interrupt thread đang chạy theo hợp đồng implementation; task phải **hợp tác kiểm tra interrupt**, và không có đảm bảo rằng một side effect ở bên ngoài được rollback.

### 22.1. Tầng cancellation cần rõ ràng

~~~text
Caller không cần kết quả nữa
              │
              ▼
Cancel future / response view
              │
              ├── Hủy yêu cầu HTTP nếu client hỗ trợ
              ├── Cancel database statement nếu driver hỗ trợ
              ├── Ngừng submit các bước chưa bắt đầu
              ├── Phát tín hiệu interrupt cho task phù hợp
              └── Ghi nhận trạng thái không chắc chắn của remote side effect
~~~

**Không dùng cancel như một dạng transaction rollback.** Một lệnh đặt hàng có thể đã được server xử lý dù client đã timeout/cancel.

### 22.2. Xử lý InterruptedException

Một tác vụ blocking sử dụng interrupt-aware APIs:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Đây là **mã minh họa** với blockingOperation() giả định có khai báo throws InterruptedException.

Khi đã bắt InterruptedException mà không tiếp tục ném, thường nên **khôi phục interrupted flag** để tầng gọi hoặc framework nhận biết tín hiệu hủy. Không nuốt interrupt rồi tiếp tục chạy vòng lặp vô hạn.

**Không tự gọi Thread.stop()** hay cơ chế dừng thread cưỡng bức không an toàn. Dùng cancellation có hợp tác và giới hạn tài nguyên ở lớp thích hợp.

## 23. Xử lý lỗi: timeout, rejection, cancellation và remote failure

Những lỗi này không hoàn toàn giống nhau:

| Trạng thái | Ý nghĩa | Gợi ý xử lý |
|---|---|---|
| **TimeoutException** | Không có kết quả trong hạn chờ | Quyết định fallback, retry an toàn, ghi timeout |
| **RejectedExecutionException** | Executor không nhận thêm task | Fail fast, backpressure, overload response |
| **CancellationException** | Future/task bị hủy | Phân biệt caller cancel với lỗi hệ thống |
| **ExecutionException** | Future.get gặp exceptional completion | Xem nguyên nhân trong cause |
| **CompletionException** | join hoặc stage thể hiện exceptional completion | Xem cause; không chỉ log wrapper |
| **InterruptedException** | Thread đang chờ bị interrupt | Restore flag hoặc propagate |
| **I/O/client exception** | Lỗi mạng/DB/remote cụ thể | Chính sách theo retryability/idempotency |

**Đừng bắt tất cả Throwable rồi trả "success=false" không có lý do**, vì sẽ làm mất khả năng phân biệt client timeout, hệ thống quá tải và lỗi dữ liệu.

### 23.1. Phân loại lỗi ở biên API

Một hệ thống cần thống nhất:

- Deadline hết → trả trạng thái timeout phù hợp với protocol/framework.
- Executor quá tải → báo overload, thường **không nên** xếp lại vào chính queue đang đầy.
- Caller hủy → không cố gửi thêm response không cần thiết, nhưng vẫn cần cleanup.
- Remote đã nhận request nhưng client timeout → tránh khẳng định thao tác chưa xảy ra.
- Retry → phải dùng idempotency hoặc chính sách xác định với side effect.

**Không biến TimeoutException thành bằng chứng rằng một giao dịch chưa được thực thi.**

## 24. Retry với cùng deadline, không cấp lại budget

Giả sử retry tối đa ba lần cho một API downstream. Nếu mỗi lần retry lại dùng **timeout=1 giây**, một request có thể chạy quá 3 giây, chưa kể backoff.

Thiết kế đúng:

~~~text
remainingTotal = initialBudget - elapsed

for each attempt:
    nếu remainingTotal == 0 → dừng
    attemptTimeout = min(remainingTotal, perAttemptCap)
    thực hiện attempt với timeout hiệu lực
    nếu lỗi retryable và còn budget:
        backoff phải nằm trong remainingTotal
        tính lại remainingTotal
        retry nếu an toàn
~~~

**Không retry vô điều kiện** đối với thao tác thanh toán, tạo đơn hoặc cập nhật trạng thái bên ngoài. Có thể cần idempotency key, transaction semantics và hiểu lỗi "không rõ kết quả".

### 24.1. Backoff tiêu thụ ngân sách

Nếu còn 100ms và backoff được đề xuất 200ms, không nên ngủ 200ms rồi retry như thể còn đủ thời gian.

**Trong code async, tránh Thread.sleep để backoff** trên các thread có giá trị cao. Dùng scheduler/timer hoặc delayedExecutor đúng mục đích, và kiểm tra deadline lại sau khi backoff kết thúc.

### 24.2. Budget không tự phải chia đều

Ba bước không cần mỗi bước đúng một phần ba thời gian. Có thể quy định:

- A có cap 150ms.
- B có cap 500ms.
- C được phần còn lại.
- Mọi cap vẫn bị giới hạn bởi **remaining overall budget**.

Chính sách này là thiết kế latency, không phải hành vi mặc định của CompletableFuture.

## 25. Timeout phải tính cả queueing và remote latency

Đối với tác vụ tổng, có thể đo:

~~~text
Total elapsed
  = time waiting in admission/queue
  + time executing callbacks
  + remote network/DB latency
  + retries/backoff
  + response serialization/cleanup
~~~

Nếu chỉ đo thời gian bên trong supplier mà bỏ qua queue và retries, số đo không phản ánh độ trễ người dùng.

**Gợi ý metrics:**

- **request_duration** (từ ingress tới response).
- **deadline_remaining_at_start** cho từng bước.
- **executor_active_threads**, **queue_depth**, **rejected_tasks**.
- **timeouts_total** theo stage/remote client.
- **cancel_attempts / cancellations_confirmed** nếu client có hỗ trợ.
- **retry_count** và **retry_budget_consumed**.
- **dependency latency histogram**.

**Không nhét thông tin cá nhân/secret vào tên metric hoặc log.** Dùng route, stage, error category và correlation ID theo chính sách bảo mật.

## 26. Thread context, transaction và resource cleanup

Callback trong CompletableFuture có thể chạy trên thread khác với thread tạo request. Không mặc định mọi **ThreadLocal**, logging MDC, security context hoặc transaction context được truyền xuyên qua tất cả stage.

~~~java
CompletableFuture<String> result =
        future.thenComposeAsync(
                value -> client.fetchAsync(value),
                executor);
~~~

Đây là **đoạn minh họa**.

Nếu client cần headers, requestId hoặc security context, **truyền tường minh** hoặc dùng context propagation của framework có kiểm thử. Không dựa vào ThreadLocal ngầm khi có callback chạy trên executor khác.

**Quản lý tài nguyên:** Nếu task mở connection, stream hoặc file, cần finally/try-with-resources phù hợp trong chính task hoặc API client. Future bị cancel không tự chạy cleanup cho mọi tài nguyên mà supplier đã tạo.

## 27. CompletableFuture và giới hạn backpressure

**thenCompose**, **thenCombine**, **allOf** không tự giới hạn số request hoặc số future đang chạy. Một fan-out có 100.000 phần tử có thể tạo 100.000 tác vụ/HTTP calls nếu code khởi động tất cả ngay.

Cần định nghĩa:

1. **Admission:** có nhận công việc mới khi hệ thống tải cao không?
2. **Concurrency cap:** tối đa bao nhiêu request tới dependency?
3. **Queue limit:** có chấp nhận chờ hay từ chối sớm?
4. **Deadline:** công việc còn thời gian hợp lệ để xử lý không?
5. **Cancellation:** khi caller bỏ cuộc, có thể dừng bao nhiêu tài nguyên?
6. **Failure isolation:** một dependency chậm có chiếm hết mọi thread?
7. **Observability:** biết đang chậm do queue, CPU, HTTP hay database?

Không thể sửa vấn đề này chỉ bằng tăng kích thước thread pool. Pool lớn hơn có thể làm tăng concurrency đối với downstream đang quá tải và khiến tình hình tệ hơn.

### 27.1. Bulkhead theo dependency

Nếu hai upstream/downstream khác nhau có mức độ tin cậy khác nhau, có thể dùng:

- Executor riêng phù hợp theo loại workload.
- Semaphore giới hạn concurrency tới một dependency.
- Connection pool và retry policy riêng.
- Deadline tổng vẫn chung cho request.

Tách tài nguyên theo dependency giúp lỗi ở một hệ thống không làm mọi task khác chờ trong cùng queue, nhưng cần cân đối chi phí thread/bộ nhớ.

## 28. Kiểm thử deadline và executor không dùng sleep

Unit test của business logic nên sử dụng:

- **Fake monotonic ticker** như AtomicLong/LongSupplier.
- **CompletableFuture** chưa hoàn tất; gọi **complete/completeExceptionally** để kiểm soát thứ tự.
- **Clock.fixed** cho deadline dựa trên Instant/TTL theo UTC.
- **Direct executor** như **Runnable::run** nếu muốn callback chạy đồng bộ, nhưng phải nhận ra test này không mô phỏng scheduling thật.
- **Bounded executor** nhỏ và **CountDownLatch** khi cần kiểm tra rejection hoặc xếp hàng.
- **Fake scheduler** khi test lịch chạy; Clock.fixed không tự kích hoạt scheduled task.
- **Timeout=0** cho test contract future mà không cần chờ thật.
- Test integration có timeout hữu hạn và quản lý teardown nếu thực sự muốn kiểm chứng timer.

**Không dùng Thread.sleep với hy vọng "sau 20ms chắc task đã chạy"**, vì CI có thể chậm hơn.

### 28.1. Test hai mức

**Unit test logic:**

- Ngân sách 500ms, fake ticker tiến 200ms → còn 300ms.
- Tiến tới 500ms → expired.
- Deadline 0 → không submit công việc mới.
- Timeout của copy không làm original hoàn tất.
- Reject khi pool/queue đầy.
- Callback nối phụ thuộc chỉ chạy khi dữ liệu trước hoàn tất.

**Integration test:**

- HTTP/DB client có transport timeout hoạt động.
- Request hủy có gửi cancellation/abort đúng hợp đồng hay không.
- Executor shutdown trong deployment có chờ hoặc force stop đúng thời hạn.
- Metrics và error mapping chính xác.
- Deadline propagation tới downstream thực tế.
- Hệ thống chịu tải ổn định khi queue tăng.

Không thể dùng unit test fake để chứng minh tài nguyên remote đã được hủy; cần integration test hoặc contract test tương ứng.

## 29. Một kiểm thử phân biệt timeout view và công việc nguồn

Ví dụ ở mục 9 đã cho thấy:

~~~text
source pending
   ├── copy() ── orTimeout(0) ──► TimeoutException
   │
   └── original vẫn pending
                  └── complete("LATE") thành công
~~~

**Điều này quan trọng trong hệ thống cache/refresh.** Nhiều caller có thể chờ một future được chia sẻ. Nếu caller A có deadline 100ms và B có deadline 1s, việc gọi **source.orTimeout(100ms)** có thể hoàn tất source cho cả hai; sử dụng **source.copy().orTimeout(...)** có thể tách kết quả chờ giữa các caller.

Nhưng nếu caller B cũng cần hủy công việc khi không còn ai dùng, một **shared-operation lifecycle** riêng sẽ cần quản lý số subscribers hoặc chính sách abort. **copy không cung cấp ref-counted cancellation**.

## 30. Thực hành về error handling

Một pipeline có thể gắn handler:

~~~java
CompletableFuture<String> result =
        fetchUserAsync(userId)
                .thenCompose(this::fetchSummaryAsync)
                .exceptionally(error -> "unavailable");
~~~

Đây là đoạn minh họa trong class có các phương thức phù hợp.

**Dùng exceptionally để trả fallback khi đó là chính sách đúng**, không phải để che mọi lỗi hệ thống. Nếu chỉ cần logging, dùng **whenComplete**. Nếu cần xử lý cả success và failure, dùng **handle**.

**TimeoutException** thường là nguyên nhân bên trong CompletionException khi dùng join trên future hoàn tất bất thường. Không định tuyến chỉ dựa trên exception message; phân loại theo kiểu exception hoặc mã lỗi ứng dụng.

### 30.1. Đừng retry khi executor đã từ chối vì quá tải

Nếu task bị **RejectedExecutionException**, retry tức thì vào cùng queue thường vô ích và có thể tạo thác retry.

Có thể:

- Trả overload response phù hợp.
- Áp backoff ngắn còn nằm trong budget.
- Giảm concurrency từ ingress.
- Dùng bulkhead khác khi có phương án fallback được thiết kế.

Không dùng vòng lặp vô hạn để cố submit.

## 31. Những lỗi thường gặp

### Lỗi 1 — Mỗi bước nhận lại full timeout

~~~text
A: 1s timeout
B: 1s timeout
C: 1s timeout
~~~

Nếu deadline tổng là 1s, đây không phải hợp đồng đúng. Truyền **remaining budget**.

### Lỗi 2 — Dùng Instant.now để đo elapsed request

Wall-clock có thể bị chỉnh; dùng **System.nanoTime** cho elapsed local, **Instant/Clock** cho timestamp và deadline tuyệt đối.

### Lỗi 3 — So nanoTime bằng start+timeout

Có thể gặp overflow vì gốc nanoTime tùy ý. Ưu tiên **now-start >= timeoutNanos**.

### Lỗi 4 — Gửi nanoTime sang service khác

Gốc nanoTime chỉ có ý nghĩa trong JVM hiện tại. Truyền Duration còn lại hoặc deadline Instant qua protocol rõ ràng.

### Lỗi 5 — Gọi source.orTimeout để tạo view riêng

orTimeout trả **chính source**; có thể làm các caller khác bị timeout. Dùng **source.copy().orTimeout** nếu muốn theo dõi riêng.

### Lỗi 6 — Nghĩ completeOnTimeout là kết quả remote thật

Fallback chỉ là giá trị ứng dụng tự đặt. Tác vụ dưới có thể vẫn đang chạy hoặc đã gây side effect.

### Lỗi 7 — Nghĩ Future.get(timeout) hủy task

get timeout chỉ giới hạn lần chờ. Không tự cancel future.

### Lỗi 8 — Gắn timeout lên future nhưng không đặt timeout I/O

Một HTTP/DB call có thể vẫn tiếp tục chiếm kết nối hoặc thread. Thiết lập transport timeout và cancellation chính xác.

### Lỗi 9 — Dùng cancel(true) rồi mặc định mọi thread đã bị interrupt

CompletableFuture.cancel không bảo đảm interrupt công việc đang chạy. Cần hiểu loại Future/Executor cụ thể.

### Lỗi 10 — Dùng Executors.newFixedThreadPool rồi nghĩ queue hữu hạn

Fixed thread count không đồng nghĩa bounded queue. Thiết kế admission với bounded queue/concurrency.

### Lỗi 11 — Dùng CallerRunsPolicy trên event loop mà không đánh giá

Policy này có thể ép thread caller chạy blocking task, tăng độ trễ hoặc làm tắc event loop.

### Lỗi 12 — Dùng DiscardPolicy cho tác vụ phải trả kết quả

Có thể làm mất task im lặng và không hoàn tất đúng future nghiệp vụ.

### Lỗi 13 — Tạo ExecutorService theo từng request, không shutdown

Gây rò thread/queue, tốn bộ nhớ. Pool thường cần lifecycle cấp ứng dụng.

### Lỗi 14 — Gọi shutdownNow rồi giả định đã dừng hết

shutdownNow là best effort interrupt; task không đáp ứng có thể tiếp tục. Cần chờ, log và policy quá hạn shutdown.

### Lỗi 15 — Dùng ExecutorService.close mà nghĩ luôn không chặn

close chờ executor hoàn tất. Nếu phải giới hạn shutdown time, dùng shutdown/awaitTermination.

### Lỗi 16 — Dùng virtual threads để chạy CPU-bound vô hạn

Virtual threads không tạo thêm CPU, không thay queue/connection limits. Giới hạn concurrency theo resource.

### Lỗi 17 — Xem StructuredTaskScope là stable trên Java SE 27

Nó vẫn là **preview API**, không là dependency mặc định không bật preview.

### Lỗi 18 — Dùng Clock.fixed để mong ScheduledExecutorService chạy

Clock chỉ kiểm soát đọc thời gian ứng dụng, không tự kích hoạt timer.

### Lỗi 19 — Dùng Thread.sleep trong unit test deadline

Test chậm và dễ flaky. Dùng fake ticker, incomplete CompletableFuture và latch khi phù hợp.

### Lỗi 20 — Timeout là bằng chứng giao dịch chưa xảy ra

Remote có thể đã xử lý dù client timeout; cần idempotency và reconciliation.

### Lỗi 21 — Retry không trừ backoff khỏi ngân sách

Backoff và queue wait cũng tiêu thụ deadline tổng.

### Lỗi 22 — Không xử lý RejectedExecutionException

Có thể để request thất bại không được phân loại hoặc gây lỗi toàn hệ thống. Chọn overload policy rõ ràng.

### Lỗi 23 — Không kiểm tra budget khi task bắt đầu sau queue

Một task đã hết hạn có thể vẫn thực thi vô ích nếu chỉ kiểm tra trước lúc submit.

### Lỗi 24 — Bắt InterruptedException rồi tiếp tục như bình thường

Có thể làm shutdown/cancellation thất bại. Restore flag hoặc propagate theo contract.

### Lỗi 25 — Gán timeout số 0 mà không đọc hợp đồng client

Một số client coi 0 là "không timeout" thay vì timeout tức thì. Cần hiểu API, tránh việc giá trị còn lại làm tròn xuống 0 rồi vô tình bỏ giới hạn.

### Lỗi 26 — Dùng thời gian executor execution thay vì total latency

Không tính queue wait, retries, serialization và cleanup; SLA thực tế có thể bị vượt.

### Lỗi 27 — Giao nhiệm vụ async nhưng assume MDC/ThreadLocal tự truyền

Callback có thể chạy trên thread khác; truyền context tường minh hoặc dùng giải pháp của framework được kiểm thử.

### Lỗi 28 — Khi timeout thì bỏ qua tài nguyên đang mở

Future completion không tự cleanup HTTP response body, stream, DB statement hoặc resource riêng; quản lý đúng lớp.

### Lỗi 29 — Nghĩ nhiều thread hơn tự giải quyết overload

Tăng concurrency có thể làm DB/API nghẽn hơn. Theo dõi queue, latency và từ chối sớm.

### Lỗi 30 — Không phân biệt deadline theo request và TTL dữ liệu

TTL là hiệu lực nghiệp vụ, request deadline là giới hạn xử lý; có thể cùng dùng Duration nhưng không cùng ý nghĩa.

## 32. Checklist thiết kế production

Trước khi đưa một pipeline async vào production, xác minh:

1. **Deadline được tạo một lần** tại ingress.
2. **Remaining budget** được tính từ monotonic ticker khi xử lý nội bộ.
3. **Không reset full timeout** trên mỗi stage/retry.
4. Timeout transport/client không lớn hơn ngân sách và cap riêng.
5. Đã xác định chính sách cho **budget=0**, âm và Duration quá lớn.
6. **Timeout copy/view** được dùng nếu không muốn mutate shared future.
7. **Future timeout không được coi là hủy remote**.
8. Có chiến lược cancellation, idempotency và reconciliation.
9. Executor có **ownership/lifecycle** rõ ràng.
10. **Shutdown** được kiểm chứng qua awaitTermination; có phương án khi task không hợp tác.
11. Queue hoặc admission không tăng vô hạn.
12. **RejectedExecutionException** được chuyển thành overload policy.
13. Pool không lẫn blocking work/CPU-heavy work không kiểm soát.
14. Virtual threads nếu dùng có **admission/concurrency cap**.
15. Structured concurrency preview không vô tình được coi là API stable.
16. Scheduled tasks có scheduler/cancellation riêng.
17. Log/metrics phân biệt deadline, timeout, rejection, cancellation.
18. Retry và backoff đều dùng **cùng tổng budget**.
19. Thread context và tài nguyên được truyền/đóng đúng.
20. Unit tests không phụ thuộc Thread.sleep hoặc system clock.
21. Integration test kiểm chứng timeout thực tế của HTTP/DB client.
22. Dữ liệu deadline truyền giữa hệ thống có units và clock-skew policy.
23. Số liệu tail latency p95/p99 và queue được theo dõi.
24. Không trả kết quả "thành công" khi timeout của side effect còn bất định.

## 33. Bài tập thực hành

### Bài 1 — Sửa deadline bị reset

Một request có tổng timeout 800ms, các bước A, B, C đều được gọi với timeout 800ms. Hãy thiết kế lại bằng một Budget, giải thích vì sao B và C không thể nhận lại đủ 800ms sau khi A đã tiêu tốn 350ms.

### Bài 2 — Dùng monotonic ticker

Viết Budget có constructor nhận Duration và LongSupplier. Test với AtomicLong: bắt đầu 700ms, tiến 200ms, tiến tiếp 500ms. Không dùng sleep.

### Bài 3 — Phân biệt get và orTimeout

Một CompletableFuture chưa hoàn tất. Gọi get(0, TimeUnit.MILLISECONDS) rồi kiểm tra isDone; tiếp theo tạo future khác và gọi orTimeout(0, ...). So sánh trạng thái.

### Bài 4 — Shared future

Một future gốc được hai caller cùng theo dõi. Caller A muốn timeout 100ms, B muốn timeout 900ms. Hãy mô tả vì sao **source.orTimeout(100ms)** nguy hiểm và cách tạo view riêng.

### Bài 5 — Vòng đời ExecutorService

Tạo fixed pool 2 workers. Submit vài công việc, lấy kết quả, shutdown và awaitTermination. Giải thích vì sao phải shutdown trong finally hoặc lifecycle callback.

### Bài 6 — Bounded queue

Tạo ThreadPoolExecutor 1 worker, queue 1. Dùng CountDownLatch khiến worker bận, submit thêm hai task và quan sát RejectedExecutionException. Đảm bảo cleanup trong finally.

### Bài 7 — Virtual threads

Trên Java 21+, dùng newVirtualThreadPerTaskExecutor và kiểm tra isVirtual. Thiết kế thêm giới hạn concurrency khi gọi một DB pool có 10 connections.

### Bài 8 — Cancellation của HTTP request

Đặt một CompletableFuture.orTimeout quanh HTTP request. Hãy giải thích vì sao timeout wrapper chưa đủ và cần dùng cơ chế cancellation/abort của HTTP client như thế nào.

### Bài 9 — Retry có deadline

Một request còn 200ms, lần gọi đầu lỗi sau 80ms và backoff là 100ms. Hỏi lần retry còn bao nhiêu thời gian trước khi trừ overhead? Nếu thời gian còn quá ít để thực hiện hiệu quả, nên làm gì?

### Bài 10 — Scheduled task không phải deadline

Dùng ScheduledExecutorService.schedule với delay 10 ngày, hủy ScheduledFuture ngay, xác minh task không chạy mà không sleep. Giải thích vì sao schedule không tự giới hạn thời lượng của task đã bắt đầu.

## 34. Câu hỏi tự kiểm tra

**Câu 1.** Deadline khác timeout của một stage như thế nào?

**Câu 2.** Ba stage có timeout riêng 1s có tự bảo đảm request tổng dưới 1s không?

**Câu 3.** Tại sao System.nanoTime phù hợp đo elapsed-time hơn Instant.now?

**Câu 4.** Có được gửi số nanoTime nguyên bản từ JVM A sang JVM B để so không?

**Câu 5.** Nên so nanoTime bằng now-start hay now >= start+timeout?

**Câu 6.** Future.get(timeout) có làm future gốc complete exceptionally không?

**Câu 7.** CompletableFuture.orTimeout trả future mới hay chính đối tượng đã gọi?

**Câu 8.** completeOnTimeout có thể làm một remote operation dừng không?

**Câu 9.** Muốn timeout riêng cho một caller dùng future được chia sẻ, có thể làm gì?

**Câu 10.** Gắn timeout ở future có tự hủy database query đang chạy không?

**Câu 11.** Timeout của transport và overall deadline có quan hệ thế nào?

**Câu 12.** Queue wait có tính vào request deadline không?

**Câu 13.** Executors.newFixedThreadPool giới hạn queue không?

**Câu 14.** ThreadPoolExecutor.AbortPolicy làm gì khi task bị từ chối?

**Câu 15.** CallerRunsPolicy có rủi ro nào với event loop?

**Câu 16.** shutdown() có ngay lập tức chấm dứt mọi task không?

**Câu 17.** shutdownNow có bảo đảm mọi task đã dừng không?

**Câu 18.** ExecutorService.close() có chờ task hoàn tất không?

**Câu 19.** close() được bổ sung từ Java phiên bản nào?

**Câu 20.** newVirtualThreadPerTaskExecutor có từ Java nào?

**Câu 21.** Virtual threads có loại bỏ nhu cầu giới hạn DB connections không?

**Câu 22.** StructuredTaskScope trong Java SE 27 đã là API stable chưa?

**Câu 23.** Clock.fixed có tự làm ScheduledExecutorService chạy sau thời gian mô phỏng không?

**Câu 24.** Một timeout có chứng minh server chưa thực hiện thanh toán không?

**Câu 25.** Retry và backoff phải dùng budget mới hay cùng budget ban đầu?

**Câu 26.** CompletableFuture.cancel(true) có bảo đảm interrupt task supplyAsync không?

**Câu 27.** Khi task bị queue chờ tới lúc deadline hết, nên cân nhắc điều gì?

**Câu 28.** Khi đang shutdown và bắt InterruptedException, nên làm gì với interrupted flag?

**Câu 29.** Vì sao cần metrics queue_depth và rejected_tasks?

**Câu 30.** Thuộc tính nào làm một test deadline xác định và nhanh?

### Đáp án

1. **Deadline** là hạn cuối của toàn yêu cầu, còn **timeout** giới hạn một thao tác/chờ cụ thể.
2. **Không.** Nếu cấp lại thời gian ở mỗi bước, tổng có thể gần 3s hoặc hơn.
3. **nanoTime** dùng elapsed trong JVM, không gắn wall clock/UTC có thể bị điều chỉnh.
4. **Không.** Giá trị có gốc tùy ý theo JVM, không cùng mốc giữa hai JVM.
5. Dùng **System.nanoTime()-start >= timeoutNanos** theo hướng dẫn API để tránh vấn đề cộng overflow.
6. **Không.** Nó chỉ ném TimeoutException cho lần chờ.
7. **Chính CompletableFuture đó**.
8. **Không.** Nó chỉ hoàn tất future bằng fallback; remote có thể tiếp tục.
9. **source.copy().orTimeout(...)** nếu muốn tách nhánh theo dõi, kèm chính sách cancellation khi cần.
10. **Không.** Cần timeout/cancellation của client hoặc driver.
11. Timeout hiệu lực ở từng bước không nên vượt remaining budget tổng; phải hiểu semantics thực tế của client.
12. **Có**, nếu deadline tính từ request ingress.
13. **Không.** Fixed thread pool dùng hàng đợi không giới hạn.
14. Ném **RejectedExecutionException**.
15. Nó có thể bắt caller chạy task và chặn event loop hoặc request thread.
16. **Không.** shutdown không nhận task mới nhưng để task đã nhận hoàn tất.
17. **Không.** Nó cố cancel pending và interrupt running, không bắt buộc mọi task hợp tác.
18. **Có**; close thực hiện orderly shutdown và chờ.
19. **Java 19**.
20. **Java 21**.
21. **Không.** DB connection pool/rate limit vẫn là giới hạn thực tế.
22. **Chưa**; StructuredTaskScope còn là **preview API** ở Java SE 27.
23. **Không.** Clock.fixed không tự điều khiển scheduler/timer.
24. **Không.** Remote side effect có thể đã xảy ra dù response timeout.
25. **Cùng budget ban đầu**, trừ cả thời gian của các attempts và backoff.
26. **Không được bảo đảm** bởi CompletableFuture; transport/task cần cơ chế hủy riêng.
27. Kiểm tra **remaining** ngay khi task bắt đầu và fail fast nếu hết, đồng thời giới hạn queue.
28. **Restore flag** qua Thread.currentThread().interrupt() hoặc propagate theo hợp đồng.
29. Chúng phân biệt tắc nghẽn/overload với lỗi remote và cảnh báo latency sắp tăng.
30. **Fake ticker/Clock, incomplete CompletableFuture được điều khiển bằng complete, bounded executor/latch**, không sleep.

## 35. Tổng kết

**Deadline, timeout và executor phải được thiết kế như một hệ thống thống nhất**. Một lời gọi orTimeout không đủ để bảo đảm mọi phần của request dừng đúng hạn và không làm hệ thống quá tải.

Những nguyên tắc cốt lõi:

- **Tạo một deadline/budget ở request boundary** và truyền thời gian còn lại xuyên qua mọi stage/retry.
- **Dùng System.nanoTime để đo elapsed time trong JVM**, không biến nanoTime thành epoch timestamp hoặc gửi sang JVM khác.
- **Future.get(timeout)** chỉ giới hạn lần chờ; **orTimeout/completeOnTimeout** hoàn tất **chính future gọi chúng**.
- **copy().orTimeout** giúp tách timeout view khỏi shared future gốc, nhưng **không tự dừng I/O**.
- Đặt **transport timeout/cancellation** ở HTTP/DB client, không chỉ CompletableFuture wrapper.
- Đừng reset timeout mỗi bước; queue, retry, backoff và serialization đều tiêu tốn budget tổng.
- **ExecutorService phải có owner và lifecycle**: shutdown, awaitTermination, có kế hoạch khi cần shutdownNow.
- **Fixed thread pool không tự giới hạn queue**; dùng bounded admission và xử lý RejectedExecutionException.
- **Virtual threads (Java 21+)** hữu ích cho blocking I/O nhưng không tạo tài nguyên vô hạn; vẫn cần giới hạn concurrency.
- **StructuredTaskScope ở Java SE 27 vẫn là preview**, không đưa vào ví dụ ổn định Java 17+.
- **Test bằng future điều khiển thủ công, fake ticker và latch**, không Thread.sleep.
- **Timeout không chứng minh remote chưa hoàn tất**; mọi side effect quan trọng cần retry/idempotency/reconciliation phù hợp.

### Tài liệu chính thức Oracle đang áp dụng

- [CompletableFuture — Java SE 27: orTimeout, completeOnTimeout, copy, delayedExecutor, cancellation](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [ExecutorService — Java SE 27: shutdown, awaitTermination, shutdownNow, close](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Executors — Java SE 27: newFixedThreadPool, newVirtualThreadPerTaskExecutor](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html)
- [ThreadPoolExecutor — Java SE 27: bounded queues, pool sizing, rejection policies](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [System.nanoTime — Java SE 27: elapsed-time và cách so timeout](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html)
- [ScheduledExecutorService — Java SE 27: lịch chạy và scheduled futures](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)
- [java.net.http.HttpClient — Java SE 27: kết nối và request timeout](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html)
- [java.net.http.HttpRequest — Java SE 27: timeout cho request](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [StructuredTaskScope — Java SE 27: PREVIEW, không là API ổn định](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
