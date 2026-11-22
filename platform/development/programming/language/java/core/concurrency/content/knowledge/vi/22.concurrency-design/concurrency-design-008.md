# Rate limiting và giới hạn in-flight requests trong Java concurrency

Hai cơ chế này cùng kiểm soát tải nhưng trả lời **hai câu hỏi khác nhau**:

- **Rate limiting:** cho phép bắt đầu bao nhiêu yêu cầu trong một đơn vị thời gian (ví dụ 100 yêu cầu/giây)?
- **In-flight limit (concurrency limit):** tại một thời điểm có tối đa bao nhiêu yêu cầu đã được nhận xử lý nhưng **chưa hoàn tất** (ví dụ 20 yêu cầu đồng thời)?

Một hệ thống có thể tuân thủ 100 yêu cầu/giây mà vẫn quá tải nếu mỗi yêu cầu kéo dài nhiều giây. Ngược lại, giới hạn 20 yêu cầu đang chạy vẫn có thể để hàng nghìn yêu cầu rất ngắn đi qua trong một giây. Vì vậy, trong nhiều hệ thống Java, cần **hai ngân sách độc lập**: tốc độ nhận việc và số việc đang tồn tại.

## 1. Khái niệm, đơn vị đo và quan hệ với độ trễ

| Đại lượng | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Arrival rate (λ) | Lượng yêu cầu đến mỗi giây | 150 requests/s |
| Admitted rate | Lượng yêu cầu được chấp nhận mỗi giây | 100 requests/s |
| In-flight (L) | Số yêu cầu đã bắt đầu nhưng chưa hoàn tất | 20 requests |
| Service time/latency (W) | Thời gian một yêu cầu ở trạng thái in-flight | 200 ms |
| Queue length | Số yêu cầu đang chờ để được nhận xử lý | 30 requests |
| Throughput | Số yêu cầu hoàn thành mỗi giây | 95 requests/s |

Một yêu cầu được tính là **in-flight** từ thời điểm đã chiếm ngân sách xử lý cho đến khi thành công, lỗi, hết hạn hoặc hủy **và thao tác nền thực sự kết thúc**. Nếu chỉ trả lỗi timeout cho người gọi nhưng công việc vẫn đang chạy, tải thực tế chưa được giải phóng.

Với hệ thống ổn định trong một khoảng quan sát đủ dài, **định luật Little** cho xấp xỉ:

```text
L ≈ λ × W
20 yêu cầu ≈ 100 yêu cầu/giây × 0,2 giây
```

Trong công thức, λ phải là tốc độ **thực sự đi vào** hệ thống đang đo, W là **thời gian trung bình** ở cùng ranh giới đo, L là mức in-flight **trung bình**. Đây không phải công thức bảo đảm đỉnh tải hay cách chọn giới hạn chỉ từ p95/p99. Ví dụ cùng 100 requests/s, nếu thời gian trung bình tăng từ 0,2 lên 2 giây, số yêu cầu tồn đọng trung bình tăng từ khoảng 20 lên 200 nếu không có cơ chế chặn. Khi tài nguyên phía sau chỉ chịu được 30 công việc đồng thời, hàng đợi và độ trễ có thể tăng mất kiểm soát.

**Phân biệt:** rate limit kiểm soát **dòng vào**; concurrency limit kiểm soát **sức chứa đang bận**; queue limit kiểm soát **số công việc chờ**. Giới hạn số thread không thay thế hoàn toàn ba cơ chế này: thread có thể xử lý nhiều tác vụ bất đồng bộ, và virtual thread cũng có thể làm quá tải database hoặc API đích.

## 2. Các thuật toán rate limiting thường gặp

### 2.1. Fixed window counter

Chia thời gian thành cửa sổ cố định, chẳng hạn 10:00:00–10:00:59; mỗi yêu cầu tăng bộ đếm và bị từ chối khi quá ngưỡng. Ưu điểm: dễ triển khai, lưu ít trạng thái. Nhược điểm: ở ranh giới cửa sổ, một client có thể gửi gần hết hạn mức cuối cửa sổ cũ rồi tiếp tục gần hết hạn mức đầu cửa sổ mới, tạo burst lớn trong thời gian rất ngắn.

### 2.2. Sliding window

Theo dõi mức sử dụng của cửa sổ trượt. **Sliding log** lưu dấu thời gian từng yêu cầu, chính xác cho ngưỡng trượt nhưng tốn bộ nhớ và chi phí dọn log. **Sliding window counter** kết hợp bộ đếm các cửa sổ kề nhau để ước lượng mức sử dụng với chi phí thấp hơn, đổi lại có sai số. Phù hợp khi cần giới hạn theo số yêu cầu trong 1 phút/giờ và quan tâm burst ở ranh giới.

### 2.3. Token bucket

Bucket có dung lượng tối đa `B` token, nạp thêm `r` token/giây. Mỗi thao tác được nhận tiêu thụ một token (hoặc nhiều token nếu tính theo trọng số).

```text
tokens_mới = min(B, tokens_cũ + r × thời_gian_đã_trôi_qua)
chấp_nhận nếu tokens_mới >= chi_phí; nếu chấp_nhận thì trừ chi_phí
```

Khi bucket đầy, có thể nhận burst tối đa `B` yêu cầu ngay lập tức; về dài hạn tốc độ được duy trì xấp xỉ `r`. Ví dụ `B = 10`, `r = 5/s` cho phép tối đa 10 yêu cầu tức thời sau khi để bucket nạp đầy, rồi trung bình 5 yêu cầu/giây. **Bucket capacity là burst allowance, không phải giới hạn in-flight.** Cần đồng bộ trạng thái token vì nhiều thread có thể tranh cùng một bucket.

### 2.4. Leaky bucket / nhịp xuất đều

Các yêu cầu vào một hàng chờ hữu hạn và được phát ra theo nhịp đều, giúp san bằng burst. Nếu hàng đợi đầy phải từ chối hoặc áp dụng chính sách rơi việc; hàng chờ dài làm tăng latency. Một số tài liệu dùng thuật ngữ leaky bucket cho biến thể bộ đếm tương đương token bucket, vì thế khi thiết kế cần ghi rõ **hành vi phát việc và quy tắc xếp hàng**.

**Chọn thuật toán theo ngữ nghĩa:** giới hạn quota trong cửa sổ dùng window; cho phép burst có kiểm soát dùng token bucket; yêu cầu nhịp xử lý khá đều dùng pacing/queue. Giới hạn theo người dùng, API key, tenant hay endpoint cần xác định **khóa tính quota** và cách xóa trạng thái khóa ít dùng.

## 3. Ví dụ Java 17: token bucket an toàn khi nhiều thread gọi

Ví dụ dưới đây minh họa limiter **trong một JVM**, dùng `synchronized` bảo vệ token và dùng đồng hồ nano đơn điệu. Truyền đồng hồ vào constructor để kiểm thử mà không cần `Thread.sleep`; `AtomicLong` chỉ đóng vai trò đồng hồ giả ở `main`. Mỗi lần gọi `tryAcquire()` là thử nhận **một** token; nếu không đủ, trả về `false` ngay.

```java
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public class TokenBucketDemo {
    static final class TokenBucket {
        private final int capacity;
        private final double tokensPerNano;
        private final LongSupplier nanoClock;
        private double tokens;
        private long lastNanos;

        TokenBucket(int capacity, double tokensPerSecond, LongSupplier nanoClock) {
            if (capacity <= 0 || !Double.isFinite(tokensPerSecond)
                    || tokensPerSecond <= 0 || nanoClock == null) {
                throw new IllegalArgumentException("Invalid bucket configuration");
            }
            this.capacity = capacity;
            this.tokensPerNano = tokensPerSecond / 1_000_000_000.0;
            this.nanoClock = nanoClock;
            this.tokens = capacity;
            this.lastNanos = nanoClock.getAsLong();
        }

        synchronized boolean tryAcquire() {
            long now = nanoClock.getAsLong();
            long elapsed = now - lastNanos;
            if (elapsed > 0) {
                tokens = Math.min(capacity, tokens + elapsed * tokensPerNano);
                lastNanos = now;
            }
            if (tokens < 1.0) {
                return false;
            }
            tokens -= 1.0;
            return true;
        }
    }

    public static void main(String[] args) {
        AtomicLong fakeClock = new AtomicLong(0);
        TokenBucket bucket = new TokenBucket(3, 2.0, fakeClock::get);

        System.out.println(bucket.tryAcquire());
        System.out.println(bucket.tryAcquire());
        System.out.println(bucket.tryAcquire());
        System.out.println(bucket.tryAcquire());

        fakeClock.addAndGet(500_000_000L);
        System.out.println(bucket.tryAcquire());
        fakeClock.addAndGet(500_000_000L);
        System.out.println(bucket.tryAcquire());
    }
}
```

Lưu thành `TokenBucketDemo.java`, biên dịch và chạy với JDK 17 trở lên:

```bash
javac TokenBucketDemo.java
java TokenBucketDemo
```

Kết quả xác định (không phụ thuộc tốc độ máy):

```text
true
true
true
false
true
true
```

Ban đầu có ba token. Lần thứ tư bị từ chối. Với tốc độ hai token/giây, mỗi lần tăng đồng hồ giả thêm 500 ms sẽ nạp lại một token. Không cần ngủ, spin hay tạo thread chỉ để đợi token.

**Ranh giới của ví dụ:** `synchronized` làm cho một instance an toàn khi gọi đồng thời; nó **không** chia sẻ quota giữa nhiều JVM/process và không đảm bảo công bằng cho các thread tranh token. `System.nanoTime()` phù hợp để đo khoảng thời gian trong tiến trình; không dùng `currentTimeMillis()` làm đồng hồ đo elapsed vì giờ hệ thống có thể bị chỉnh. Trong ứng dụng thực tế, có thể tạo bucket với `System::nanoTime`; với nhiều key, phải quản lý vòng đời bucket và tránh giữ vô hạn một đối tượng cho mỗi key. Phép tính `double` phù hợp để minh họa rate thông thường; hệ thống đòi độ chính xác/quy tắc làm tròn nghiêm ngặt nên chọn biểu diễn và kiểm thử sai số rõ ràng.

## 4. Giới hạn in-flight bằng Semaphore

`java.util.concurrent.Semaphore` đại diện cho số **permit** đang có. Với `new Semaphore(20)`, tối đa 20 thao tác được nhận khi mỗi thao tác chiếm đúng một permit:

1. **Trước khi** bắt đầu công việc, thử chiếm permit bằng `tryAcquire()` hoặc chờ có thời hạn bằng `tryAcquire(timeout, unit)`.
2. Nếu không lấy được permit, **không được bắt đầu** công việc đã dự kiến; trả một kết quả từ chối/bận hoặc đưa vào hàng đợi có giới hạn.
3. Nếu đã lấy được permit, phải `release()` **đúng một lần** khi công việc thực sự kết thúc, kể cả khi lỗi.
4. Không `release()` nếu `acquire` thất bại; `Semaphore` không gắn quyền sở hữu với thread, nên release thừa có thể âm thầm nâng số thao tác đồng thời vượt ngưỡng.

Với mã **đồng bộ**:

```java
if (!permits.tryAcquire()) {
    throw new java.util.concurrent.RejectedExecutionException("Busy");
}
try {
    performBlockingOperation();
} finally {
    permits.release();
}
```

Đoạn trên là **mẫu minh họa**, cần có đối tượng `permits` và hàm `performBlockingOperation()` của ứng dụng; nó không phải tệp Java chạy độc lập. `finally` là cần thiết vì hàm bên trong có thể ném exception. Tuy nhiên, nếu phương thức chỉ **khởi chạy** công việc bất đồng bộ rồi trả về ngay, release trong `finally` sẽ **quá sớm**; phải gắn release vào thời điểm completion của công việc thật.

### Ví dụ Java 17 đầy đủ: bảo vệ CompletableFuture

Ở đây mỗi `CompletableFuture` đại diện cho một công việc chưa hoàn tất. `call` thử chiếm permit trước khi gọi supplier, giải phóng permit khi future nguồn hoàn thành; nếu supplier ném exception hoặc trả `null`, cũng trả permit. Khi hết permit, supplier không được gọi. Demo điều khiển completion thủ công nên kết quả không phụ thuộc scheduler.

```java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;

public class InFlightDemo {
    static final class InFlightLimiter {
        private final int maximum;
        private final Semaphore permits;

        InFlightLimiter(int maximum) {
            if (maximum <= 0) {
                throw new IllegalArgumentException("maximum must be positive");
            }
            this.maximum = maximum;
            this.permits = new Semaphore(maximum);
        }

        <T> CompletableFuture<T> call(Supplier<CompletableFuture<T>> operation) {
            Objects.requireNonNull(operation, "operation");
            if (!permits.tryAcquire()) {
                return CompletableFuture.failedFuture(
                        new RejectedExecutionException("Too many in-flight requests"));
            }

            CompletableFuture<T> source;
            try {
                source = Objects.requireNonNull(operation.get(), "future");
            } catch (RuntimeException | Error failure) {
                permits.release();
                return CompletableFuture.failedFuture(failure);
            }
            return source.whenComplete((value, failure) -> permits.release());
        }

        int inFlight() {
            return maximum - permits.availablePermits();
        }
    }

    public static void main(String[] args) {
        InFlightLimiter limiter = new InFlightLimiter(2);
        CompletableFuture<String> sourceA = new CompletableFuture<>();
        CompletableFuture<String> sourceB = new CompletableFuture<>();
        CompletableFuture<String> sourceD = new CompletableFuture<>();

        CompletableFuture<String> resultA = limiter.call(() -> sourceA);
        CompletableFuture<String> resultB = limiter.call(() -> sourceB);
        CompletableFuture<String> rejected =
                limiter.call(() -> CompletableFuture.completedFuture("C"));

        System.out.println("rejected=" + rejected.isCompletedExceptionally());
        System.out.println("inFlight=" + limiter.inFlight());

        sourceA.complete("A"); // A finishes: its permit returns.
        CompletableFuture<String> resultD = limiter.call(() -> sourceD);
        sourceB.complete("B");
        sourceD.complete("D");

        System.out.println("results="
                + resultA.join() + resultB.join() + resultD.join());
        System.out.println("inFlight=" + limiter.inFlight());
    }
}
```

Lưu thành `InFlightDemo.java` rồi chạy:

```bash
javac InFlightDemo.java
java InFlightDemo
```

Stdout:

```text
rejected=true
inFlight=2
results=ABD
inFlight=0
```

Lần gọi C bị từ chối khi A và B vẫn chưa hoàn thành; supplier C không được thực thi. Sau khi A kết thúc, D có thể bắt đầu. `whenComplete` vẫn được kích hoạt khi nguồn hoàn thành exceptional hoặc bị hủy, nên permit được trả ở các trường hợp đó **nếu chính future nguồn thực sự hoàn thành**.

**Lưu ý về cancellation:** `resultA` là một future phụ thuộc, khác `sourceA`. Hủy future trả về không có nghĩa tự động hủy `sourceA` hoặc giải phóng permit ngay; trong ví dụ, permit giữ đến khi `sourceA` hoàn thành. Trong mã thực tế phải định nghĩa rõ ai sở hữu future nguồn, cách truyền cancellation và deadline tới tác vụ/downstream, và chỉ release khi tác vụ được coi là kết thúc theo ranh giới tài nguyên đã chọn. Không được release thêm trong nhánh timeout rồi lại release khi callback completion chạy.

**Lưu ý về fairness:** `new Semaphore(maximum, true)` hỗ trợ chính sách FIFO cho các thao tác chờ có thứ tự; riêng `tryAcquire()` không tham gia đầy đủ quy tắc fairness. Fairness có thể đổi lấy throughput và không thay thế hàng đợi hữu hạn, deadline hoặc SLA.

## 5. Kết hợp rate và in-flight limit đúng ranh giới

Mô hình tổng quát:

```text
request đến
  → xác định key/quota
  → kiểm tra rate token (cho phép / từ chối)
  → kiểm tra in-flight permit (nhận / từ chối hoặc chờ có hạn)
  → chạy công việc
  → công việc kết thúc thật sự (success/failure/cancel)
  → trả permit
```

Trong sơ đồ, nếu quota đếm **lần thử** thì token được tính ngay cả khi permit không còn; đây có thể là chính sách hợp lệ để hạn chế spam. Nếu quota đếm **công việc thật sự được nhận**, cần phối hợp hai bước theo chính sách khác: lấy permit rồi thử token, nếu token hết phải trả permit ngay. **Không giữ permit trong lúc chờ token được nạp** vì sẽ làm mất sức chứa không cần thiết. Việc “refund” token khi bị hết permit cần được thiết kế thành thao tác nhất quán; tự cộng lại token thiếu đồng bộ có thể làm vượt quota.

Chọn rõ mỗi giới hạn áp dụng ở đâu:

- **Global instance:** bảo vệ tổng tài nguyên của một JVM; giới hạn chỉ đúng với instance đó.
- **Per-key:** tránh một người dùng/tenant độc chiếm quota; cần key normalization, eviction và xử lý key có cardinality cao.
- **Per-downstream:** có thể đặt concurrency riêng cho database, kết nối HTTP, thiết bị, tác vụ CPU nặng; nên đo theo tài nguyên thật.
- **Per-operation cost:** request tốn 10 lần tài nguyên có thể cần 10 token hoặc weighted admission, không mặc định mọi request bằng nhau.

Với nhiều process hoặc nhiều máy, mỗi instance tự có bucket 100/s nghĩa là **tổng quota có thể gần bằng số instance nhân 100/s**. Nếu cần quota **toàn cụm**, phải dùng bộ đếm/bucket chia sẻ và cập nhật **nguyên tử** (ví dụ lưu trữ tập trung có script/transaction phù hợp), hoặc phân phối ngân sách rõ ràng cho từng instance. Cần định nghĩa hành vi khi nơi lưu quota lỗi, latency tăng, clock lệch, và khi hai request tranh token; chỉ đọc rồi ghi counter bằng hai lệnh rời nhau là dễ race. Tương tự, `Semaphore` JDK không tự cung cấp giới hạn in-flight toàn cụm.

## 6. Waiting, backpressure, timeout và queue

`tryAcquire()` là **fail fast**: phù hợp khi phía trên có thể nhận phản hồi bận và retry hợp lý. `tryAcquire(timeout, TimeUnit.MILLISECONDS)` cho phép **chờ có hạn** ở luồng blocking; phải tính thời gian chờ vào deadline tổng. `acquire()` có thể chờ vô thời hạn và dễ giữ thread/virtual thread lẫn kết nối, khiến tải ẩn tích tụ.

Hàng đợi không giới hạn biến giới hạn concurrency thành **tăng latency và sử dụng bộ nhớ vô hạn dưới quá tải**. Ví dụ `Executors.newFixedThreadPool(n)` sử dụng queue không giới hạn trên thực tế; chỉ chỉnh số worker không đồng nghĩa hệ thống đã có backpressure an toàn. Nếu cần queue, dùng queue có dung lượng được thiết kế rõ, deadline của phần tử, policy khi đầy và giám sát queue age.

**Không dùng vòng lặp spin** liên tục gọi `tryAcquire()`; nó đốt CPU và không công bằng. Nếu phải đợi token, dùng lịch hẹn/đợi có giới hạn với thời điểm sớm nhất đủ token; bảo đảm scheduler không mở thêm một hàng chờ vô hạn. Với luồng xử lý bất đồng bộ, ưu tiên composition/callback và cơ chế giới hạn số việc chờ thay vì chặn thread chỉ để giữ chỗ.

Khi bị từ chối, có thể trả trạng thái quá nhiều yêu cầu (ví dụ HTTP 429 khi ràng buộc rate/quota), hoặc dịch vụ đang bận (ví dụ HTTP 503 trong ngữ cảnh overload), kèm thời gian retry nếu **có thể tính đáng tin**. Không đưa `Retry-After` tùy tiện: in-flight saturation không tự cho biết khi nào một tác vụ sẽ kết thúc. Client cần exponential backoff với jitter, giới hạn tổng thời gian và số lần thử; retry tức thời hàng loạt có thể tạo **retry storm**. Nếu API có idempotency/side effect, phải xét an toàn của retry.

Timeout phải áp dụng theo **deadline đầu-cuối** qua queue, bước nhận permit và downstream; timeout chỉ của caller không bảo đảm công việc nền dừng. Với công việc lâu dài như streaming, cần quyết định khi nào request không còn chiếm permit và có cơ chế đóng nguồn/chấm dứt tác vụ rõ ràng.

## 7. Chọn thông số bằng số đo, tránh đoán ngưỡng

Ví dụ downstream thường hoàn thành 100 requests/s với latency trung bình 200 ms. Little's Law cho tải in-flight trung bình khoảng 20. Tuy nhiên, không nên đặt `maxInFlight = 20` chỉ bằng phép nhân này: có burst, thời gian đuôi dài, cạnh tranh khóa, stop-the-world pause, nhu cầu dự phòng và thay đổi hiệu năng khi quá tải. Bắt đầu bằng khả năng thực của tài nguyên (connection pool, CPU, giới hạn dịch vụ đích), kiểm tra bằng load test, rồi hiệu chỉnh theo throughput, độ trễ và lỗi.

Một quy trình thực tế:

1. **Xác định mục tiêu:** tải bền vững, burst cho phép, latency/timeout, quota mỗi key và ngưỡng tài nguyên downstream.
2. **Đo baseline:** throughput hoàn tất, p50/p95/p99 latency, số in-flight, saturation và error rate ở các mức tải.
3. **Đặt rate dài hạn** thấp hơn tốc độ bền vững đã đo nếu cần headroom; chọn `capacity` theo burst mà phần sau có thể hấp thụ.
4. **Đặt max in-flight** theo tài nguyên thật và kiểm nghiệm ở kịch bản latency tăng gấp vài lần; tránh cho phép hàng trăm tác vụ cùng làm nghẽn pool 20 kết nối.
5. **Quy định overload:** reject sớm, chờ rất ngắn có deadline, hoặc hàng đợi hữu hạn; không mở queue vô hạn để “giữ” mọi request.
6. **Thử các tình huống bất thường:** nhiều client đồng loạt, tác vụ chậm/hung, lỗi downstream, timeout/cancel, hot key, autoscaling và retry.

Các chỉ số nên theo dõi:

| Metric | Điều cần nhìn |
| --- | --- |
| `requests_attempted_total`, `rate_rejected_total` | Tổng lần thử và số bị rate limiter từ chối; tách theo key có kiểm soát cardinality |
| `concurrency_rejected_total` | Số yêu cầu không lấy được in-flight permit |
| `inflight_current`, `inflight_limit` | Mức sử dụng permit và thời gian duy trì gần trần |
| `queue_depth`, `queue_wait_seconds` | Hàng đợi có tăng liên tục và chờ có vượt deadline không |
| `request_duration_seconds` (p50/p95/p99) | Độ trễ của công việc đã được nhận; phân biệt thời gian queue |
| `downstream_errors_total`, `timeouts_total` | Thất bại, timeout và khả năng downstream đang bão hòa |
| `completed_total` / throughput | Limiter có giúp throughput ổn định hay đang bóp nghẹt không |

Metric gắn mọi user ID làm label trực tiếp sẽ gây **cardinality cao**; thường đo tổng và các nhóm bounded, log/audit riêng khi cần truy vết từng client. Đồng hồ đo đỉnh theo giây/phút có thể che khuất burst ngắn; chọn độ phân giải quan sát phù hợp.

## 8. Những lỗi thiết kế và cách kiểm thử

**Nhầm rate với concurrency:** “50 requests/s” không giới hạn được “50 requests cùng lúc”. Cần hai test riêng: burst tức thời với bucket đầy và nhiều future cố ý chưa complete.

**Release quá sớm:** trả permit ngay sau khi khởi tạo `CompletableFuture` khiến số thao tác thật vượt trần. Gắn release với completion của nguồn đại diện cho thao tác thật.

**Rò/đếm dư permit:** quên release trong failure path làm dừng hệ thống dần; release hai lần làm vô hiệu hóa giới hạn. Mỗi acquire thành công phải có đúng một lần release, kể cả supplier throw và cancellation.

**Chờ vô hạn:** tác vụ bị xếp hàng lâu hơn deadline rồi vẫn được chạy, gây lãng phí và tăng tail latency. Có giới hạn queue/wait time, kiểm tra deadline lại trước khi chạy.

**Dùng clock hệ thống cho refill:** chỉnh giờ/NTP có thể làm token nạp bất thường. Dùng monotonic elapsed trong process; nếu distributed, dùng nguồn thời gian/logic nhất quán với bộ lưu trạng thái.

**Không kiểm tra race:** `if (count < limit) count++` không nguyên tử và có thể overshoot. Dùng synchronization/atomic CAS đúng vòng lặp hoặc một store atomic nếu chia sẻ qua process.

**Quota bị nhân khi scale out:** mỗi máy áp dụng full budget độc lập làm tổng mức cho phép tăng cùng số máy. Tài liệu hóa quota là per-instance hay global và kiểm thử nhiều instance.

**Quên chính sách side effect:** nếu request bị timeout nhưng lệnh ghi vẫn tiếp tục, retry có thể tạo tác vụ trùng. Kết hợp deadline, cancellation khi khả thi và idempotency cho thao tác cần thiết.

Bộ test tối thiểu nên bao gồm:

- **Token bucket:** bucket đầy nhận tối đa `capacity` yêu cầu tức thì; yêu cầu tiếp theo bị từ chối; đồng hồ giả tiến đúng khoảng tạo token mới; nhiều thread tranh cùng instance không vượt tổng token.
- **In-flight:** tạo `N` future chưa complete thì future thứ `N+1` bị từ chối và supplier không chạy; sau khi hoàn thành một nguồn, một việc mới vào được.
- **Lỗi:** supplier ném exception, future complete exceptionally và future nguồn cancel đều trả permit; exception trước khi lấy permit không làm phát sinh release.
- **Hủy/timeout:** callback completion đến muộn không khiến release hai lần; timeout của caller được phân biệt với việc nguồn còn chạy.
- **Overload:** queue không vượt dung lượng, không vượt deadline, throughput không sụp vì retry storm; giới hạn per-key độc lập và giới hạn tổng vẫn hoạt động.

## 9. Kết luận áp dụng

Trong Java concurrency, **rate limiter** định lượng *bao nhiêu công việc được chấp nhận theo thời gian*, còn **in-flight limiter** định lượng *bao nhiêu công việc có thể giữ tài nguyên cùng lúc*. Token bucket là lựa chọn dễ hiểu cho tốc độ có burst; `Semaphore` là building block hiệu quả cho giới hạn đồng thời của một JVM. Chỉ ghép hai cơ chế mới giải quyết đầy đủ nếu kết hợp **ranh giới completion chính xác, deadline, backpressure, bounded queue, observability và chính sách distributed** phù hợp với hệ thống.