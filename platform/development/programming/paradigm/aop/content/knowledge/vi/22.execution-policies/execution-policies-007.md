# Giới hạn tốc độ hoặc số lời gọi đồng thời bằng Aspect-Oriented Programming (AOP)

## 1. Tại sao đặt chính sách giới hạn ở một aspect?

Trong một hệ thống có nhiều điểm thực thi, không phải phương thức nào cũng được phép nhận vô hạn lời gọi. Một tác vụ có thể tiêu tốn connection, thread, CPU, bộ nhớ hoặc hạn ngạch dịch vụ bên ngoài. Khi nhiều nơi cần cùng chính sách kiểm soát tải, **Aspect-Oriented Programming (AOP)** cho phép áp dụng logic giới hạn ở những *join point* đã chọn thay vì chèn mã kiểm tra và giải phóng tài nguyên vào từng phương thức nghiệp vụ.

Có hai câu hỏi độc lập:

1. **Giới hạn tốc độ (rate limiting):** Trong một khoảng thời gian, hệ thống cho phép bao nhiêu yêu cầu bắt đầu? Ví dụ trung bình 10 yêu cầu/giây với khả năng chấp nhận một đợt ngắn 20 yêu cầu.
2. **Giới hạn số lời gọi đồng thời (concurrency limiting):** Tại một thời điểm, có tối đa bao nhiêu thao tác đang thực thi/chưa hoàn tất? Ví dụ chỉ năm thao tác đang sử dụng pool kết nối.

Chúng có thể áp dụng riêng hoặc kết hợp. Rate limiter điều tiết **nhịp bắt đầu**; concurrency limiter điều tiết **số tác vụ đang tồn tại**. Một aspect phù hợp sẽ chặn lời gọi tại đầu vào, ra quyết định nhận/từ chối/chờ, rồi chuyển tiếp hoặc dừng thao tác theo chính sách được công bố.

**Mục tiêu học tập:** hiểu thuật toán giới hạn, xác định đúng đơn vị đo và phạm vi điểm cắt, triển khai advice bảo toàn kết quả/exception/cancellation, kiểm soát bộ nhớ và thời gian chờ, và đánh giá được tác động trong đa luồng, bất đồng bộ hoặc nhiều instance.

## 2. Phân biệt hai giới hạn bằng ví dụ

Giả sử hệ thống cho phép tối đa **20 lời gọi mỗi giây** và tối đa **4 lời gọi đồng thời**.

- Nếu 20 lời gọi đến rất nhanh và mỗi lời gọi kết thúc trong 1 ms, concurrency có thể không vượt 4 nhưng rate limiter vẫn từ chối lời gọi vượt ngân sách đã cấp.
- Nếu chỉ 5 lời gọi đến trong một giây nhưng mỗi lời gọi mất 10 giây, rate có thể hợp lệ trong khi concurrency limiter phải chặn lời gọi thứ năm nếu bốn lời gọi trước vẫn chưa kết thúc.
- Nếu một lời gọi kết thúc nhưng ngay lập tức có lời gọi khác thay thế, số tác vụ đang chạy vẫn tối đa 4; giới hạn số lần bắt đầu trong giây là một trục kiểm soát khác.

| Thuộc tính | Rate limiter | Concurrency limiter |
| --- | --- | --- |
| Đối tượng giới hạn | Số lượt đến/được phép bắt đầu theo thời gian | Số thao tác chưa kết thúc |
| Đơn vị cấu hình | calls/s, calls/min, tokens/s, burst capacity | Số permit, slot hoặc in-flight tasks |
| Trạng thái chính | Token, cửa sổ thời gian, số lượt trong cửa sổ | Số permit đang giữ và số permit còn trống |
| Khi thao tác hoàn tất | Thường không hoàn lại token đã tiêu thụ | Trả lại permit đúng một lần |
| Khi không còn hạn ngạch | Từ chối hoặc chờ có hạn mức | Từ chối hoặc chờ có hạn mức |
| Rủi ro nếu thiếu cơ chế | Burst/spam và vượt quota | Cạn tài nguyên, nghẽn pool, OOM |
| Vấn đề khó | Định nghĩa thời gian, burst, phân vùng quota | Định nghĩa vòng đời, timeout, cancellation, deadlock |

Đối với một tác vụ đã hoàn tất, số slot được giải phóng có thể tăng ngay; với rate limiting, kết thúc nhanh **không tạo thêm ngân sách tốc độ**. Cần tránh nhầm lẫn này khi cấu hình cả hai.

### Giới hạn in-flight không đồng nghĩa giới hạn thread

Một tác vụ bất đồng bộ có thể rời thread gọi rồi tiếp tục chờ I/O trong tương lai. Nếu mục tiêu là giới hạn số request đang được xử lý, slot phải được giữ đến khi có trạng thái terminal, **không phải** đến khi phương thức trả về đối tượng `Future` hoặc `CompletionStage`. Ngược lại, nếu chính sách chỉ nhằm giới hạn số lần thread thực thi đoạn CPU đồng bộ, phạm vi giữ slot ngắn hơn có thể đúng. Trước khi code, luôn ghi rõ đơn vị và thời điểm “bắt đầu/kết thúc”.

## 3. Vị trí đặt aspect trong đường thực thi

Trong AOP nói chung:

- **Join point:** điểm có thể áp dụng can thiệp, ví dụ thực thi phương thức được chọn.
- **Pointcut:** biểu thức/chính sách chọn phương thức, loại thao tác, nhóm tài nguyên hoặc vùng code được kiểm soát.
- **Before advice:** có thể kiểm tra quota trước khi cho tác vụ chạy, nhưng khó tự bảo đảm trả permit trên mọi đường thoát nếu không có cơ chế phối hợp.
- **Around advice:** phù hợp để lấy permit/token, chuyển tiếp lời gọi gốc **đúng một lần**, quan sát thành công/exception, rồi trả permit trong `finally` khi vòng đời là đồng bộ.
- **After advice:** có thể quan sát kết thúc, nhưng phải gắn đúng với lần đã acquire và đường kết thúc thực tế.

Luồng tổng quát của một around advice đồng bộ:

~~~mermaid
flowchart TD
    A[Lời gọi đi qua pointcut] --> B{Còn slot đồng thời?}
    B -->|Không| R[Từ chối hoặc chờ có giới hạn]
    B -->|Có| C[Giữ slot]
    C --> D{Có token tốc độ?}
    D -->|Không| E[Trả slot rồi từ chối]
    D -->|Có| F[Gọi nghiệp vụ đúng một lần]
    F --> G[Trả kết quả hoặc chuyển tiếp lỗi gốc]
    G --> H[Trả slot trong finally]
~~~

Điều kiện **chính sách áp dụng đúng nơi** quan trọng không kém thuật toán. Một lời gọi trực tiếp bỏ qua proxy, lời gọi nội bộ không đi qua điểm chặn hoặc một đường API chưa được chọn sẽ không tự động chịu giới hạn. Với weaving ở mức bytecode, khả năng bắt các điểm này có thể khác. Phải xác minh điểm cắt thực tế bằng test, thay vì chỉ tin vào khai báo.

### Đặt giới hạn ở biên có ý nghĩa nghiệp vụ

Nếu mỗi request đi qua ba method A→B→C nhưng cả ba đều được cùng một limiter bảo vệ, một request có thể tiêu thụ ba token hoặc ba slot và tự chặn chính nó. Cần xác định **một đơn vị logic**:

- Theo user/API key: hạn ngạch một khách hàng.
- Theo endpoint/operation: bảo vệ một loại thao tác.
- Theo resource pool: bảo vệ database, hệ thống tệp hoặc dịch vụ ngoài.
- Theo request logic: mỗi request chỉ nhận một quyết định kiểm soát ở một biên nhất quán.
- Theo attempt: mỗi lần retry được xem là một lần gọi thật sự, có thể cần tính vào quota để tránh khuếch đại tải.

Pointcut quá rộng còn có thể chọn chính thư viện điều khiển quota, tạo đệ quy. Chọn phạm vi có chủ ý và loại trừ code enforcement/telemetry khỏi các điểm cần bảo vệ.

## 4. Các thuật toán giới hạn tốc độ

### 4.1 Fixed window counter

Chia thời gian thành các cửa sổ cố định, ví dụ từng phút. Mỗi cửa sổ đếm số yêu cầu; khi đạt N thì từ chối tiếp cho đến cửa sổ mới.

**Ưu điểm:** đơn giản, dễ triển khai và lưu trữ. **Nhược điểm:** có thể nhận gần 2N yêu cầu trong khoảng rất ngắn ở ranh giới hai cửa sổ: N lời gọi vào cuối cửa sổ cũ và N vào đầu cửa sổ mới. Vì vậy hạn mức “100/phút” không đảm bảo mọi khoảng 60 giây liên tục đều tối đa 100 lần.

### 4.2 Sliding window log hoặc sliding window counter

- **Sliding log:** giữ timestamp của các yêu cầu còn nằm trong khoảng trượt; trước khi quyết định, bỏ những timestamp đã hết hạn rồi kiểm đếm. Rõ ràng nhưng có thể dùng bộ nhớ tỷ lệ với số yêu cầu và số khóa.
- **Sliding window counter:** tổng hợp các cửa sổ nhỏ hơn hoặc nội suy giữa cửa sổ hiện tại và trước đó; giảm bộ nhớ nhưng có sai số phụ thuộc thuật toán.
- Phải công bố ranh giới bao gồm/không bao gồm, cách xử lý thời gian lùi và clock giữa các máy.

### 4.3 Token bucket

Một xô có dung lượng tối đa `capacity` và tốc độ nạp `rate` token/giây. Mỗi lần bắt đầu công việc tốn một hoặc nhiều token. Token tích lũy khi ít tải, đến tối đa dung lượng; do đó có thể hỗ trợ burst ngắn nhưng giữ tốc độ trung bình lâu dài.

Ví dụ `capacity = 5` và `rate = 2 tokens/s`:

- Ban đầu đầy 5 token, có thể nhận năm yêu cầu ngay.
- Yêu cầu thứ sáu ngay sau đó bị từ chối nếu chưa được nạp thêm token.
- Sau 0,5 giây không tiêu thụ token, xô có thêm khoảng một token.
- Sau thời gian chờ dài, xô không vượt quá 5 token.

Mô hình tính ở thời điểm `now`:

`tokens = min(capacity, tokens + elapsedSeconds × rate)`

Khi `tokens >= cost`, trừ `cost` và nhận; nếu không, từ chối hoặc tính thời gian đợi. Với token phân số dùng `double`, cần chú ý sai số dấu phẩy động và kiểm thử ranh giới; với quota quan trọng có thể dùng đại lượng nguyên và đơn vị thời gian đủ nhỏ. Dùng nguồn thời gian monotonic cho elapsed; thời gian lịch có thể nhảy do đồng bộ đồng hồ.

**Điểm mạnh:** hỗ trợ burst có giới hạn, tương đối dễ áp dụng. **Điểm yếu:** giới hạn trung bình và burst không cấm mọi đợt dồn trong khoảng rất ngắn; nếu yêu cầu một nhịp phát đều, cân nhắc cơ chế spacing/queue có giới hạn.

### 4.4 Leaky bucket và điều phối nhịp

Mô hình leaky bucket thường đưa yêu cầu vào một bộ đệm có sức chứa giới hạn và xử lý/cho phép rời đi theo nhịp đều. Nó giúp làm mượt tốc độ, nhưng thêm **queueing latency**, khả năng đầy hàng đợi và trách nhiệm hủy việc đang chờ. Một thuật toán “leaky bucket” cụ thể còn phụ thuộc cách định nghĩa của từng tài liệu/công cụ: nên kiểm tra nó là traffic shaper có queue hay cách tính tương đương timestamp.

**Không có thuật toán nào “tốt nhất” cho mọi workload.** Nếu muốn chấp nhận burst nhỏ rồi hồi phục, token bucket hợp lý; nếu cần trần số yêu cầu trong cửa sổ trượt, dùng window thích hợp; nếu cần phát với nhịp đều, xét scheduler/queue có giới hạn.

## 5. Giới hạn số lời gọi đồng thời bằng permit

Một semaphore đếm permit là cơ chế phù hợp cho tác vụ đồng bộ:

1. Xác định số slot tối đa `maxConcurrent`.
2. Khi vào advice, gọi `tryAcquire()` để chiếm một permit; nếu không có, từ chối ngay hoặc chờ theo timeout.
3. Chỉ sau khi lấy permit thành công mới cho nghiệp vụ chạy.
4. Dùng `finally` trả permit khi nghiệp vụ kết thúc hoặc ném lỗi.
5. Không trả permit nếu chưa lấy được; không trả hai lần; không giữ permit khi tác vụ đã kết thúc.

Bất biến lý tưởng ở thời điểm ổn định:

`0 <= inFlight <= maxConcurrent`

`availablePermits + inFlight = maxConcurrent`

Lưu ý đây là mô hình tổng quát khi một tác vụ giữ đúng một permit và không có thao tác thay đổi số permit khác. Khi nhiều thread đang acquire/release, snapshot của các bộ đếm do nhiều API cung cấp có thể chênh lệch trong khoảnh khắc.

### Fail-fast hay đợi?

**Fail-fast:** `tryAcquire()` trả về ngay. Ưu điểm là latency của yêu cầu bị từ chối có thể dự đoán, tránh tạo thêm queue. Nhược điểm là số lỗi “busy” tăng trong burst ngắn.

**Chờ có thời hạn:** `tryAcquire(timeout, unit)` có thể giảm tỷ lệ từ chối khi slot sắp được giải phóng, nhưng phải ràng buộc timeout, số thread chờ, cancellation và deadline của request. Một hệ thống tạo vô hạn thread để chờ permit chỉ di chuyển bài toán quá tải vào bộ nhớ và scheduler.

**Chờ vô hạn:** dễ gây nghẽn và làm thời gian phản hồi vượt hạn mức; không nên chọn mặc định cho API có latency SLO. Với event loop hoặc callback quan trọng, không nên block thread chỉ để chờ semaphore; dùng giải pháp bất đồng bộ với queue có giới hạn hoặc từ chối sớm.

### Fairness và ưu tiên

Một semaphore có thể dùng chính sách công bằng, nhưng công bằng không tự tạo thêm capacity và cũng không đồng nghĩa deadline luôn được đáp ứng. Fairness thường có thêm chi phí điều phối; với traffic nhiều mức ưu tiên, cần chính sách dành slot hoặc tách pool rõ ràng. Đừng để request chậm hoặc retry chiếm hết slot của tác vụ quan trọng mà không có chiến lược admission control.

## 6. Kết hợp hai giới hạn trong một around advice

Nếu cả rate và concurrency đều có hiệu lực, thứ tự kiểm tra ảnh hưởng semantics:

**Phương án A: kiểm tra rate rồi concurrency.** Dễ phản ánh mọi attempt vào rate quota, nhưng nếu bị concurrency từ chối thì token đã bị tiêu thụ; muốn hoàn token phải định nghĩa rõ tính công bằng và thuật toán rollback.

**Phương án B: giữ slot concurrency rồi kiểm tra rate.** Một yêu cầu bị từ chối vì hết slot không tiêu tốn token tốc độ; nếu thiếu token thì phải trả ngay slot. Cách này hữu ích khi rate quota chỉ dành cho yêu cầu thực sự được phép đi vào nhánh xử lý. Nhưng lúc nhiều thread tranh permit, thứ tự admission có thể khác thứ tự arrival.

Không có thứ tự nào mặc định phù hợp mọi quota; hãy xác định rõ **bị concurrency từ chối có tính vào hạn ngạch hay không**, và ai sở hữu quyền quyết định (client, endpoint, operation, tenant). Ví dụ Java dưới đây minh họa **Phương án B, fail-fast**, nhằm giữ code đơn giản và bảo toàn permit.

Các phản hồi bị từ chối cần có ý nghĩa:

- Trong API, có thể quy ước lỗi rate limit / busy, ví dụ phản hồi giao thức tương ứng và gợi ý thời gian retry khi ước tính được.
- Trong thư viện phương thức, có thể ném exception phân biệt `RateExceeded` và `CapacityExceeded` để caller xử lý.
- Không giả vờ một lệnh gọi đã thành công khi chưa chạy nghiệp vụ.
- Không thay lỗi nghiệp vụ thành “rate exceeded” sau khi nghiệp vụ đã bắt đầu, trừ khi có chính sách ngắt chủ động và hợp đồng rõ ràng.

## 7. Ví dụ Java 17+ chạy độc lập: token bucket + semaphore trong advice

Ví dụ tạo **JDK dynamic proxy** để minh họa around advice cho interface `Task`. Một token bucket dùng đồng hồ monotonic do chúng ta cung cấp, nên có thể kiểm thử nạp token bằng cách tăng clock ảo mà không dùng `Thread.sleep()`. Một semaphore giới hạn số lời gọi đang chạy; ví dụ thứ hai cố ý giữ một cuộc gọi đang bận bằng `CountDownLatch` để kiểm tra từ chối một cuộc gọi khác. Hai thử nghiệm dùng hai limiter độc lập.

**Tệp: `AopAdmissionDemo.java`**

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public class AopAdmissionDemo {
    public interface Task {
        String execute(String id) throws InterruptedException;
    }

    static final class RateExceeded extends RuntimeException {
        RateExceeded() {
            super("rate limit");
        }
    }

    static final class CapacityExceeded extends RuntimeException {
        CapacityExceeded() {
            super("concurrency limit");
        }
    }

    static final class ManualClock implements LongSupplier {
        private final AtomicLong now = new AtomicLong();

        @Override
        public long getAsLong() {
            return now.get();
        }

        void advanceNanos(long nanos) {
            now.addAndGet(nanos);
        }
    }

    static final class TokenBucket {
        private final double capacity;
        private final double refillPerSecond;
        private final LongSupplier ticker;
        private double tokens;
        private long lastNanos;

        TokenBucket(double capacity, double refillPerSecond,
                    LongSupplier ticker) {
            if (!(capacity > 0) || !(refillPerSecond > 0)) {
                throw new IllegalArgumentException("positive limits required");
            }
            this.capacity = capacity;
            this.refillPerSecond = refillPerSecond;
            this.ticker = ticker;
            this.tokens = capacity;
            this.lastNanos = ticker.getAsLong();
        }

        synchronized boolean tryConsume() {
            long now = ticker.getAsLong();
            // Với đồng hồ monotonic, elapsed bình thường luôn >= 0.
            if (now > lastNanos) {
                double elapsedSeconds =
                    (now - lastNanos) / 1_000_000_000.0;
                tokens = Math.min(
                    capacity, tokens + elapsedSeconds * refillPerSecond
                );
                lastNanos = now;
            }

            if (tokens < 1.0) {
                return false;
            }
            tokens -= 1.0;
            return true;
        }
    }

    static final class AdmissionAdvice implements InvocationHandler {
        private final Object target;
        private final TokenBucket bucket;
        private final Semaphore slots;

        AdmissionAdvice(Object target, TokenBucket bucket, int concurrent) {
            if (concurrent <= 0) {
                throw new IllegalArgumentException("positive slots required");
            }
            this.target = target;
            this.bucket = bucket;
            this.slots = new Semaphore(concurrent);
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            if (method.getDeclaringClass() == Object.class) {
                try {
                    return method.invoke(target, args);
                } catch (InvocationTargetException error) {
                    throw error.getCause();
                }
            }

            if (!slots.tryAcquire()) {
                throw new CapacityExceeded();
            }

            try {
                if (!bucket.tryConsume()) {
                    throw new RateExceeded();
                }

                try {
                    return method.invoke(target, args);
                } catch (InvocationTargetException error) {
                    // Bảo toàn nguyên nhân lỗi gốc của nghiệp vụ.
                    throw error.getCause();
                }
            } finally {
                // Đúng một release cho mỗi acquire thành công.
                slots.release();
            }
        }
    }

    static Task guarded(Task target, TokenBucket bucket, int concurrent) {
        return (Task) Proxy.newProxyInstance(
            Task.class.getClassLoader(),
            new Class<?>[] {Task.class},
            new AdmissionAdvice(target, bucket, concurrent)
        );
    }

    static final class HeldTask implements Task {
        final CountDownLatch entered = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);

        @Override
        public String execute(String id) throws InterruptedException {
            if ("hold".equals(id)) {
                entered.countDown();
                release.await();
            }
            return "ok-" + id;
        }
    }

    public static void main(String[] args) throws Exception {
        ManualClock ticker = new ManualClock();
        Task rateTask = guarded(
            id -> "ok-" + id,
            new TokenBucket(2, 2, ticker),
            2
        );

        System.out.println(rateTask.execute("first"));
        System.out.println(rateTask.execute("second"));

        try {
            rateTask.execute("third");
        } catch (RateExceeded error) {
            System.out.println("rate=blocked");
        }

        ticker.advanceNanos(500_000_000L);
        System.out.println(rateTask.execute("after-refill"));

        HeldTask held = new HeldTask();
        Task concurrentTask = guarded(
            held,
            new TokenBucket(100, 100, System::nanoTime),
            1
        );

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<String> first = pool.submit(
                () -> concurrentTask.execute("hold")
            );
            held.entered.await();

            try {
                concurrentTask.execute("other");
            } catch (CapacityExceeded error) {
                System.out.println("concurrency=blocked");
            }

            held.release.countDown();
            System.out.println(first.get());
            System.out.println(concurrentTask.execute("after-release"));
        } finally {
            held.release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac AopAdmissionDemo.java
java AopAdmissionDemo
~~~

**Stdout kỳ vọng** (bỏ qua môi trường làm gián đoạn chương trình bất thường):

~~~text
ok-first
ok-second
rate=blocked
ok-after-refill
concurrency=blocked
ok-hold
ok-after-release
~~~

Giải thích:

1. Xô của `rateTask` có dung lượng 2 token; hai lời gọi đầu được nhận. Lời gọi thứ ba xảy ra cùng thời điểm trên clock ảo nên bị từ chối.
2. Tăng clock ảo 500 triệu nano giây tương đương 0,5 giây. Với mức nạp 2 token/giây, xô nhận thêm một token; lời gọi tiếp theo được nhận.
3. `HeldTask` có một lời gọi được giữ chờ trên thread trong pool. Khi nó đã vào thân phương thức, semaphore của proxy chỉ có một slot và đang bận. Lời gọi từ main bị từ chối vì concurrency.
4. Khi mở latch, lời gọi đầu hoàn tất và `finally` giải phóng slot. Lời gọi sau đó được nhận.
5. Nếu nghiệp vụ ném exception, advice mở lớp bọc `InvocationTargetException` để caller thấy lỗi gốc; `finally` vẫn trả slot. Một yêu cầu bị rate từ chối sau khi giữ slot cũng trả slot đúng một lần.

**Giới hạn của ví dụ:** Đây là proxy trong cùng một JVM, chỉ bảo vệ những lời gọi **thực sự đi qua proxy**. Token bucket dùng `double` và một khóa `synchronized`, phù hợp để giải thích thuật toán nhưng có thể gây contention khi số thread lớn. `Semaphore` là giới hạn trong process; khi chạy nhiều instance mỗi instance sẽ có quota riêng. Chương trình minh họa phương thức **đồng bộ**; với future/stream, trả permit khi `method.invoke` kết thúc có thể quá sớm. Đây là các vấn đề cần xử lý trong hệ thống thật.

## 8. Lời gọi đồng bộ, bất đồng bộ và vòng đời permit

### Đồng bộ

Với lời gọi đồng bộ, `try/finally` là cách phổ biến và đáng tin:

~~~java
boolean acquired = semaphore.tryAcquire();
if (!acquired) {
    throw new CapacityExceeded();
}
try {
    return invokeOriginal();
} finally {
    semaphore.release();
}
~~~

Đây là **mã ý tưởng**, trong đó `semaphore` và `invokeOriginal()` là các thành phần do ứng dụng cung cấp. `finally` thực thi khi phương thức hoàn tất bình thường hoặc ném exception. Nếu sử dụng chờ permit có thể bị ngắt, giữ nguyên hoặc xử lý đúng trạng thái interruption theo hợp đồng của ứng dụng.

### CompletionStage hoặc future

Một phương thức có thể trả `CompletionStage<Result>` gần như lập tức trong khi tác vụ bên trong tiếp tục nhiều giây. Nếu lời khuyên thực thi trả permit ngay sau khi trả stage, hệ thống có thể nhận **vô hạn tác vụ đang chờ I/O**, dù semaphore chỉ có vài slot. Vì thế để giới hạn số **logical in-flight operations**, phải giữ slot đến completion thành công, exceptional completion hoặc cancellation theo semantics đã chọn.

Thiết kế khái niệm:

1. Lấy permit trước khi gọi phương thức gốc; nếu không lấy được, từ chối.
2. Gọi phương thức gốc đúng một lần và nhận stage.
3. Nếu lệnh gọi đồng bộ ném exception trước khi trả stage, release ngay rồi ném lại.
4. Gắn callback completion chỉ release một lần; nếu callback quan sát bị chạy lại hoặc có đường cleanup khác, dùng một bộ bảo vệ at-most-once.
5. Bảo đảm cancellation của wrapper (nếu có) truyền đúng theo hợp đồng và không trả permit trước thời điểm được coi là terminal thực tế.
6. Hạn chế callback nặng trên thread hoàn tất; phân biệt deadline đã hết với tác vụ gốc **đã thật sự dừng**.

Ví dụ ở mức khái niệm, **không phải chương trình độc lập**:

~~~java
if (!semaphore.tryAcquire()) {
    throw new CapacityExceeded();
}

CompletionStage<Result> stage;
try {
    stage = invokeOriginalReturningStage();
} catch (Throwable original) {
    semaphore.release();
    throw original;
}

if (stage == null) {
    semaphore.release();
    throw new IllegalStateException("Unexpected null stage");
}

stage.whenComplete((result, error) -> semaphore.release());
return stage;
~~~

Ở đây `semaphore`, `invokeOriginalReturningStage()`, `Result` và exception là các thành phần giả định. Code chỉ minh họa **giữ permit đến completion của stage**. Trong triển khai đầy đủ cần xử lý lỗi khi đăng ký callback, chính sách null stage, làm rõ cancellation/timeout và bảo đảm release đúng một lần khi có nhiều đường terminal. Đặc biệt, việc gọi `cancel(true)` trên một `CompletableFuture` không tự bảo đảm tác vụ nền bị dừng; không thể tuyên bố đã giải phóng năng lực xử lý gốc chỉ vì future đại diện chuyển sang trạng thái canceled.

### Stream hoặc Publisher

Một publisher có thể được đăng ký nhiều lần, phát nhiều phần tử, hủy giữa chừng hoặc kéo dài vô hạn. Giới hạn **số subscription đang hoạt động** khác giới hạn **số lần gọi phương thức tạo publisher**. Muốn giữ slot trong vòng đời subscription, aspect hoặc decorator phải bám vào `subscribe`, các tín hiệu terminal `onComplete`/`onError` và `cancel` theo định nghĩa kết thúc; cần bảo toàn `request(n)` và backpressure. Không tự `subscribe` thêm chỉ để đo hoặc chiếm slot.

Nếu một subscription không kết thúc và không hủy, slot có thể được giữ vô hạn. Vì thế phải định nghĩa thời hạn, chính sách idle timeout và cleanup; timeout quan sát không tự chứng minh nguồn đã dừng gửi dữ liệu.

## 9. Chính sách từ chối, chờ và retry

### Từ chối nhanh

Khi hết token hoặc permit, hệ thống có thể ném exception có kiểu riêng, trả kết quả domain biểu thị “busy”, hoặc ánh xạ sang mã phản hồi giao thức tại biên hệ thống. Cần phân biệt **từ chối trước khi nghiệp vụ bắt đầu** với **lỗi trong lúc nghiệp vụ chạy**.

Ở hệ thống nhận request qua HTTP, rate-limit rejection thường được biểu diễn bằng `429 Too Many Requests`; thiếu tài nguyên tạm thời có thể cần chính sách phản hồi riêng tùy thiết kế API, chẳng hạn `503 Service Unavailable`. Mã cụ thể phải nhất quán với hợp đồng. `Retry-After` chỉ nên đưa ra khi có thời gian chờ ước tính hợp lý; không bịa mốc hồi phục nếu điều kiện phụ thuộc tải không thể đoán.

### Chờ có giới hạn

Token bucket có thể tính thời gian còn thiếu token; semaphore có thể dùng `tryAcquire(timeout, unit)`. Đợi chỉ hợp lý khi:

- Request còn deadline đủ dài và client chưa hủy.
- Queue/nhóm thread chờ được **giới hạn**.
- Có cơ chế loại yêu cầu khỏi queue khi quá hạn hoặc khi client hủy.
- Thời gian chờ và thứ tự ưu tiên đã được định nghĩa.
- Trạng thái đầy hệ thống không tạo vòng lặp retry nội bộ làm mọi request chờ lâu hơn.

Không nên dùng một queue vô hạn như cách “làm mượt” rate limit: nó làm tăng latency, chiếm memory và che khuất overload.

### Retry không kiểm soát tạo bão lưu lượng

Nếu caller nhận từ chối rồi retry ngay, hệ thống có thể nhận **nhiều attempt hơn** so với original request. Client nên cân nhắc exponential backoff, jitter, deadline và giới hạn số lần thử khi nghiệp vụ cho phép. Server phải xác định retry tiêu thụ token mới hay được tính chung vào request logic theo quota; cả hai có hệ quả công bằng và capacity.

Việc advice âm thầm retry thao tác gốc có thể gây side effect lặp (ghi dữ liệu, thanh toán, gửi thông báo). Một advice chỉ dùng để giới hạn tải thường **không nên tự gọi lại** nghiệp vụ để “đợi slot”.

## 10. Phạm vi quota: toàn cục, theo nhóm hay theo khách hàng?

Mỗi limiter cần một **khóa nhận diện chính sách** (key). Ví dụ:

| Khóa | Mục tiêu | Vấn đề cần kiểm tra |
| --- | --- | --- |
| Toàn ứng dụng | Bảo vệ CPU/memory của một instance | Nhiều instance có thể vượt quota tổng |
| Per-operation | Bảo vệ một phương thức hoặc loại tài nguyên | Điểm cắt lồng nhau, nhiều overload |
| Per-client/API key | Công bằng quota giữa khách hàng | Xác thực danh tính, nhiều key, churn |
| Per-tenant | Ngăn một tenant chiếm hết tài nguyên | Quota chung cho tài khoản, bucket lớn |
| Per-external dependency | Bảo vệ tài nguyên downstream | Nhiều operation chia sẻ một quota thực |
| Theo nhóm ưu tiên | Dành capacity cho request quan trọng | Starvation, thay đổi ưu tiên động |

Không được dùng chỉ một IP như định danh đáng tin duy nhất nếu môi trường có proxy/NAT hoặc header giả mạo. Lấy danh tính từ nguồn xác thực, chuẩn hóa key và hạn chế số bucket được tạo. Một bucket mới cho mỗi user ID không bao giờ dọn có thể gây rò rỉ bộ nhớ; cân nhắc TTL, giới hạn kích thước map, chính sách thu hồi và đồng bộ hóa khi tạo bucket.

Một hạn ngạch **theo tenant** không đồng nghĩa với limit riêng trên từng instance. Nếu có 5 instance và mỗi instance cho 100 requests/s, tổng hệ thống có thể nhận gần 500 requests/s khi traffic phân bố đều, chứ không tự thành quota toàn cục 100 requests/s.

## 11. Nhiều instance và điều phối phân tán

Để thực sự áp dụng hạn mức chung trên nhiều JVM/process, trạng thái quota cần phối hợp ở nơi dùng chung hoặc sử dụng cơ chế phân bổ ngân sách có kiểm soát. Những lựa chọn thường gặp:

- **Bộ đếm/token bucket ở kho dữ liệu có thao tác nguyên tử:** thao tác kiểm tra và trừ quota phải atomic; mô hình read→if→write tách rời có thể tạo race, vượt hạn mức.
- **Cấp ngân sách cho từng instance:** giảm độ trễ truy cập coordinator nhưng có nguy cơ mất cân bằng, thừa hạn ngạch ở máy ít tải hoặc overshoot khi phân phối lại.
- **Gateway/admission layer:** giới hạn ở biên trước khi vào ứng dụng; vẫn có thể cần thêm giới hạn concurrency cục bộ để bảo vệ pool nội bộ.
- **Semaphore phân tán hoặc lease:** cần cơ chế gia hạn, thời hạn, xử lý process chết và tránh một permit bị sở hữu đồng thời khi lease hết hạn.

### Vấn đề clock và độ chính xác

Token bucket hoặc sliding window phân tán phải xác định clock nguồn; việc mỗi instance dùng `System.nanoTime()` riêng không cho ra mốc có thể so sánh giữa các process. Coordinator có thể giữ thời gian thống nhất hoặc dùng thuật toán có quy định về skew. Tính công bằng và giới hạn cứng toàn cục thường đánh đổi lấy latency, availability và chi phí giao tiếp mạng.

### Coordinator lỗi thì sao?

Một aspect có thể quyết định:

- **Fail-closed:** khi không lấy được quyết định quota thì từ chối, tránh vượt hạn mức nhưng có thể làm gián đoạn dịch vụ.
- **Fail-open có giám sát:** cho phép một lượng request nhất định đi qua khi coordinator lỗi, ưu tiên tính sẵn sàng nhưng chấp nhận rủi ro vượt quota.
- **Local fallback có ngân sách nhỏ:** giới hạn tạm thời từng instance, có thể chặn bớt mức overshoot nhưng phải định nghĩa tính nhất quán khi coordinator phục hồi.

Không có lựa chọn chung cho mọi hệ thống. Chẳng hạn quota theo hợp đồng thương mại, bảo vệ tài nguyên hữu hạn hoặc giới hạn truy cập chống lạm dụng có thể yêu cầu mức bảo đảm khác nhau. Ghi lại chính sách khi coordinator gián đoạn, timeout kết nối, retry, và cách xử lý event trễ.

## 12. Quản lý lock, contention và hiệu suất của advice

Chính sách giới hạn là một điểm nóng tiềm năng: mọi lời gọi cùng khóa sẽ cạnh tranh trên trạng thái quota.

- `synchronized` quanh một token bucket bảo đảm cập nhật nhất quán trong cùng JVM nhưng có thể thành bottleneck khi hàng nghìn thread dùng chung bucket.
- Cơ chế CAS/atomic có thể giảm một số contention, nhưng cần thiết kế đúng với thao tác gồm đọc thời gian, refill và trừ token; không thể chỉ thay counter bằng atomic rồi bỏ qua race.
- `Semaphore` điều phối permit nhưng có chi phí cạnh tranh; fairness có thể thay đổi thông lượng.
- Tạo quá nhiều per-key limiter làm tăng bộ nhớ; tạo quá ít limiter khiến các nhóm độc lập tranh chung lock và quota.
- Ghi log đồng bộ trên đường từ chối có thể trở thành điểm nghẽn đặc biệt khi đang bị spam.
- Thời gian chờ vào lock/queue và thời gian nghiệp vụ nên được đo riêng, để biết chính limiter có làm tăng latency không.

Ước lượng đơn giản: nếu advice mất trung bình 3 µs CPU cho mỗi lần gọi và có 100.000 lần gọi/giây, tổng thời gian xử lý bổ sung cỡ 0,3 CPU-second mỗi giây, **chưa tính** cache contention, GC, log, điều phối thread hoặc ảnh hưởng khi tải bão hòa. Đây là phép nhân minh họa, không phải một benchmark.

Nên đo hiệu ứng A/B ở các mức tải, gồm p95/p99 latency, achieved throughput, CPU, allocation/GC, số lần timeout, queue length và rate rejection. Tối ưu limiter mà làm sai tính chính xác của quota không phải cải tiến.

## 13. Quan sát và đánh giá chính sách

Một tập metrics hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| `admission_attempts_total` | Số lần qua advice tại điểm giới hạn |
| `admission_allowed_total` | Số lần được cấp phép và bắt đầu |
| `admission_rejected_total{reason="rate"}` | Số lần từ chối do hết token |
| `admission_rejected_total{reason="concurrency"}` | Số lần từ chối do hết slot |
| `admission_wait_seconds` | Phân phối thời gian chờ nếu hỗ trợ đợi |
| `admission_in_flight` | Số tác vụ hiện đang giữ permit |
| `admission_duration_seconds` | Thời lượng thực thi theo vòng đời đã định nghĩa |
| `admission_limiter_failures_total` | Lỗi trong chính cơ chế kiểm soát (coordinator, registry...) |
| `admission_active_keys` | Số bucket/key đang được lưu |
| `admission_queue_depth` | Số yêu cầu chờ trong queue có giới hạn |

Từ chối trước nghiệp vụ và lỗi nghiệp vụ nên có nhãn outcome **khác nhau**. Ví dụ tỷ lệ từ chối do quota bằng `rejected / attempts` trong một khoảng; tỷ lệ thất bại nghiệp vụ có thể lấy `business_failed / admitted_and_completed`. Không đưa rejection vào mẫu số lỗi nghiệp vụ mà không công bố rõ.

Một phản hồi quá tải có thể tăng khi cấu hình limiter phát huy tác dụng, trong khi ứng dụng vẫn khỏe; ngược lại, `admission_rejected_total = 0` không chứng minh hệ thống có đủ capacity nếu một đường gọi bypass pointcut.

Giảm cardinality: tránh gắn request ID, user ID tự do, token bí mật hoặc stack trace riêng vào từng metric series. Với tenant nhiều, cân nhắc tổng hợp theo cấp quota hoặc dùng log/trace phân quyền để drill down. Hạn chế log mọi rejection trong một đợt tấn công; metrics đếm tổng hợp thường an toàn tài nguyên hơn.

## 14. Kiểm thử đúng chức năng và góc cạnh

### Kiểm thử rate limiter

1. **Bucket vừa khởi tạo:** nhận đúng số token bằng capacity, từ chối yêu cầu kế tiếp khi chưa refill.
2. **Refill có kiểm soát:** dùng đồng hồ giả; sau 0,5 giây ở mức 2 token/s có thêm một token.
3. **Capacity:** sau khoảng idle dài không nạp vượt dung lượng xô.
4. **Boundary:** test đúng mốc cửa sổ, token phân số, độ trễ rất nhỏ, đồng hồ không tiến hoặc bị lệch theo mô hình triển khai.
5. **Concurrency trong một bucket:** nhiều thread chạy `tryConsume` đồng thời không được tiêu cùng một token hai lần.
6. **Per-key isolation:** tài khoản A hết quota không tự làm cạn quota B nếu chính sách tách biệt.
7. **Retry:** việc retry tạo attempt mới được tính theo đúng chính sách, không vô tình được miễn quota.

### Kiểm thử concurrency limiter

1. Giữ tối đa N lời gọi chưa hoàn tất, thử lời gọi thứ N+1 và xác nhận từ chối/đợi đúng cấu hình.
2. Khi một lời gọi hoàn tất, lời gọi mới có thể nhận permit.
3. Khi nghiệp vụ ném exception, permit được trả và lỗi gốc được chuyển tiếp.
4. Khi chính sách rate từ chối sau khi đã acquire slot, slot được trả ngay.
5. Khi có timeout, interruption, cancellation, bảo đảm cleanup phù hợp vòng đời và không release hai lần.
6. Với nhiều thread, không vượt `maxConcurrent` ở bất kỳ thời điểm quan sát hợp lệ; không phụ thuộc thời gian `sleep` để tạo trùng lặp khó tái hiện.
7. Với reentrant call hoặc điểm cắt lồng nhau, kiểm tra tránh tự deadlock và đếm kép; xác định có cho phép lệnh gọi nội bộ dùng chung permit hay không.

### Kiểm thử AOP và tích hợp

- Kiểm tra điểm cắt thật sự đi qua proxy/weaving và không có đường bypass khi gọi trực tiếp.
- Mỗi thao tác gốc được thực thi đúng một lần khi được nhận, không thực thi khi bị từ chối.
- Giá trị trả về, exception, side effect và context không bị biến đổi ngoài chính sách.
- Tác vụ async giữ slot tới terminal thật; không trả sớm khi trả future.
- Mọi queue có giới hạn, số thread chờ và độ trễ từ chối nằm trong ngân sách tài nguyên.
- Khi tăng instance, quota tổng có đúng như thiết kế không; test khi coordinator chậm hoặc mất kết nối.
- Khi áp lực tải lớn, liệu policy có tạo starvation, retry storm hoặc lỗi thứ cấp từ logging.

### Kiểm thử tải

Chạy các kịch bản sau với offered load và thời gian chạy rõ ràng: thấp hơn ngưỡng rate, gần ngưỡng rate, burst vượt capacity, tác vụ chậm khiến semaphore đầy, request bị cancel, lỗi nghiệp vụ, coordinator lỗi. Đo cả **offered rate** và **completed rate**, vì nếu bên phát tải bị chặn, hệ thống có thể trông khỏe dù chưa được thử đến đúng ngưỡng.

Ngoài throughput, theo dõi p95/p99, thời gian chờ, tỉ lệ accepted/rejected, số connection/thread, CPU, heap, queue và độ trễ downstream. Đặt mục tiêu trước khi thử: chẳng hạn không quá ba tác vụ sử dụng một resource có capacity ba, queue không tăng vô hạn, reject có phân loại rõ và request quan trọng không bị starvation.

## 15. Những sai lầm thường gặp

**“Rate limit 100/s nghĩa là luôn có tối đa 100 request cùng lúc.”** Sai. Một burst hoặc thời lượng chạy kéo dài có thể khiến số in-flight lớn hơn nhiều; cần concurrency limiter riêng.

**“Semaphore 10 slot nghĩa là không quá 10 request mỗi giây.”** Sai. Nếu mỗi request xong trong 1 ms, 10 slot có thể xử lý nhiều đợt trong một giây; không có trần tốc độ bắt đầu.

**“Dùng `finally` là đủ cho mọi phương thức async.”** Không chính xác. `finally` kết thúc khi phương thức trả future/publisher, có thể trước khi công việc thực sự xong.

**“Mỗi instance có 100 tokens/s tức toàn hệ thống có 100 tokens/s.”** Sai nếu có nhiều instance độc lập; phải thiết kế quota phối hợp hoặc ngân sách phân bổ.

**“Cho mọi request chờ đến khi được chạy sẽ tránh từ chối.”** Có thể gây backlog, latency vượt deadline và OOM. Chờ phải có giới hạn và có chính sách hủy.

**“Từ chối càng ít càng tốt.”** Nếu tất cả request đều được nhận đến khi tài nguyên sụp đổ, hệ thống không còn thực hiện được mục tiêu bảo vệ. Admission control chủ động có thể duy trì chất lượng phục vụ cho những request đã nhận.

**“Tắt logging là policy đủ nhanh.”** Chưa chắc: lock, registry, phân phối key, quota coordinator, serialization hoặc proxy dispatch có thể vẫn là nút nghẽn.

**“Dùng pointcut rất rộng sẽ tự bảo vệ toàn chương trình.”** Có thể đếm kép, tự khóa khi reentrant hoặc áp quota cho code infrastructure. Cần chọn biên nghiệp vụ phù hợp và kiểm tra đường gọi thật.

**“Từ chối do thiếu token cũng là lỗi xử lý nghiệp vụ.”** Từ chối admission xảy ra trước khi chạy nghiệp vụ; cần quan sát nó riêng với exception sinh trong nghiệp vụ.

## 16. Quy trình triển khai thực tế

1. **Xác định tài nguyên cần bảo vệ:** CPU, connection, hạn ngạch remote API, tenant SLA, queue hoặc một operation cụ thể.
2. **Viết hợp đồng:** giới hạn bắt đầu theo thời gian hay số in-flight; có burst không; ai dùng chung quota; lỗi/hủy được tính thế nào.
3. **Chọn thuật toán:** window, token bucket, scheduler hoặc semaphore dựa trên workload và yêu cầu về độ chính xác/công bằng.
4. **Chọn pointcut:** xác minh những lời gọi thực sự chịu policy; tránh đếm kép, bypass và recursion.
5. **Chọn cách từ chối/chờ:** fail-fast hoặc hàng đợi có giới hạn; định nghĩa lỗi/timeout/retry cho caller.
6. **Thiết kế vòng đời slot:** phương thức đồng bộ dùng `finally`; tác vụ async theo terminal; stream theo subscription; xử lý cancellation.
7. **Thiết kế trạng thái quota:** per-instance, per-key hoặc phối hợp phân tán, xử lý đồng hồ và race.
8. **Đo & kiểm thử:** các tình huống biên, parallel calls, load burst, resource slow, timeout, collector/coordinator lỗi, chi phí của advice.
9. **Triển khai theo giai đoạn:** bắt đầu với mức bảo vệ bảo thủ, theo dõi rejected/accepted, latency và mức dùng tài nguyên; hiệu chỉnh từ kết quả thực tế và yêu cầu dịch vụ.

## 17. Kết luận

Giới hạn tốc độ và giới hạn số lời gọi đồng thời giải quyết hai khía cạnh quá tải khác nhau. **Rate limiter** quản lý ngân sách bắt đầu công việc theo thời gian; **concurrency limiter** quản lý số công việc còn đang diễn ra. AOP có thể thực thi cả hai tại một biên chung bằng around advice, miễn là chính sách được áp dụng đúng điểm cắt, gọi nghiệp vụ đúng một lần, giữ nguyên kết quả/lỗi và quản lý token/permit theo vòng đời đã chọn. Với tác vụ bất đồng bộ hoặc hệ nhiều instance, định nghĩa vòng đời và trạng thái quota quan trọng hơn câu lệnh `tryAcquire()` đơn lẻ. Một thiết kế an toàn phải có giới hạn hàng đợi, chính sách lỗi, khả năng quan sát và kiểm thử tải để chứng minh hệ thống được bảo vệ thực sự.