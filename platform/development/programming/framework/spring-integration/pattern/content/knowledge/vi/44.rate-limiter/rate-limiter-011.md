# Kiểm thử burst và sustained load

## 1. Bài toán: Rate limiter đúng khi thử ít request chưa chắc đúng dưới tải

Trong module **SPRING_INTEGRATION_PATTERN**, Spring Integration giúp ghép các Enterprise Integration Patterns (EIP) thành message flow ít phụ thuộc: **Gateway** tiếp nhận yêu cầu, **Filter** kiểm tra, **Transformer** chuẩn hóa payload, **Router** chọn nhánh, **Service Activator** gọi dependency, **Splitter** tách công việc và **Aggregator** ghép kết quả. Khi một API bên ngoài có quota hoặc giới hạn khả năng chịu tải, ta đặt **rate limiter** tại điểm phù hợp để ngăn lưu lượng vượt mức cho phép.

Một phép thử “gửi 11 request và thấy request thứ 11 bị chặn” chỉ kiểm tra một thời điểm. Nó không chứng minh limiter:

- Chịu được **burst**: nhiều request đến cùng lúc, có thể đến từ nhiều thread hoặc pod.
- Giữ đúng tốc độ với **sustained load**: dòng request liên tục trong vài phút hoặc lâu hơn.
- Bổ sung permit đúng theo thời gian, không cấp trùng do race condition.
- Không làm tăng latency vô hạn hoặc giữ thread chờ khi hết permit.
- Phân biệt đúng **request bị limiter từ chối**, **request gọi upstream thất bại**, và **message được defer**.
- Không nhân quota theo số pod, không bị retry hoặc Splitter âm thầm vượt hạn mức.
- Vẫn trả kết quả có hợp đồng và giữ **correlation ID** qua Gateway, Router, error channel và Aggregator.

**Mục tiêu của bài:** thiết kế một bộ kiểm thử có giả định, số đo và tiêu chí pass/fail rõ ràng cho cả burst lẫn sustained load, rồi tích hợp kết quả vào Spring Integration.

~~~mermaid
flowchart LR
    A[Load generator] --> B[Gateway / Consumer]
    B --> C[Filter / Router]
    C --> D{Rate limiter}
    D -->|ALLOW| E[Stock Client]
    D -->|REJECT| F[RATE_LIMITED outcome]
    E --> G[Reply / Aggregator]
    F --> G
    D -.-> H[Permit metrics]
    E -.-> I[Upstream calls / latency]
    G -.-> J[Gateway outcomes]
~~~

## 2. Định nghĩa chính xác burst và sustained load

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Offered load** | Lượng request gửi đến limiter, gồm cả bị từ chối | 200 request/giây |
| **Admitted load** | Lượng request được cấp permit | Khoảng 50 request/giây sau khi hết burst |
| **Completed throughput** | Lượng công việc thật hoàn thành ở downstream | Có thể thấp hơn admitted nếu upstream chậm/lỗi |
| **Burst** | Lưu lượng tăng mạnh trong khoảng rất ngắn | 100 request gần như cùng lúc |
| **Sustained load** | Lưu lượng kéo dài tương đối ổn định | 200 request/giây trong 10 phút |
| **Capacity** | Số permit tối đa có thể tích lũy trong mô hình token bucket | 20 token |
| **Refill rate** | Tốc độ bổ sung token theo thời gian | 10 token/giây |
| **Rejection** | Không cấp phép cho một request | RATE_LIMITED hoặc HTTP 429 |
| **Wait policy** | Chờ token, từ chối ngay hoặc hoãn xử lý | timeout 0 hoặc bounded wait |

**Burst test** chủ yếu kiểm tra capacity, cạnh tranh đồng thời và phản hồi khi cạn permit. **Sustained-load test** chủ yếu kiểm tra refill, tốc độ trung bình sau giai đoạn đầu, độ ổn định khi tải lớn kéo dài và backlog.

Hai bài kiểm thử có thể cho kết quả khác nhau. Limiter cấp đúng 20 permit cho 100 request đồng thời nhưng refill sai 10 lần mỗi giây sẽ vượt quota sau vài phút. Ngược lại, limiter duy trì 10 request/giây trung bình nhưng cho burst 1.000 request trong một mili giây có thể làm upstream sập ngay lập tức.

### 2.1. Đừng nhầm Rate limiter với Bulkhead hoặc Circuit breaker

- **Rate limiter** giới hạn số lời gọi theo thời gian hoặc thuật toán quota.
- **Bulkhead/concurrency limiter** giới hạn số lời gọi *đang chạy đồng thời*.
- **Circuit breaker** ngắt lời gọi mới khi dependency lỗi/chậm theo chính sách.
- **Retry** thử lại lỗi tạm thời và có thể tạo thêm lời gọi vật lý.
- **Queue/backpressure** điều hòa công việc không thể xử lý ngay.

Một limiter 50 request/giây vẫn có thể khiến hàng nghìn request đang chạy nếu mỗi request giữ kết nối lâu. Vì vậy sustained-load test phải đo cả **in-flight concurrency**, latency và trạng thái pool/thread, không chỉ số permit.

## 3. Chọn thuật toán trước khi viết assertion

Các thuật toán khác nhau có **ngữ nghĩa burst khác nhau**. Không thể viết một test “mỗi giây chính xác 10 request” rồi áp cho mọi loại limiter.

| Thuật toán | Mô hình | Điều nên kiểm thử |
| --- | --- | --- |
| **Token bucket** | Token tích lũy tới capacity, refill theo thời gian | Burst ban đầu, refill và upper bound theo khoảng thời gian |
| **Leaky bucket / paced queue** | Làm mượt tốc độ phát ra | Khoảng cách đầu ra, queue length và waiting deadline |
| **Fixed window** | Đếm request trong từng cửa sổ lịch | Trần theo từng window; có thể burst gần ranh giới hai window |
| **Sliding window** | Đếm trong cửa sổ trượt | Trần theo mọi cửa sổ có độ dài xác định, nếu implementation đáp ứng |
| **Resilience4j RateLimiter theo chu kỳ refresh** | Cấp số permit theo các refresh period | Số permit mỗi chu kỳ, chờ cấp phép và hành vi sát ranh giới kỳ |

Resilience4j RateLimiter dùng **limitForPeriod** và **limitRefreshPeriod**; không mặc định đánh đồng nó với một token bucket refill liên tục. Nếu chọn thư viện này, dùng **contract của từng refresh period** để kiểm thử. Những ví dụ token bucket bên dưới là mô hình độc lập nhằm làm rõ toán học và đồng thời.

### 3.1. Upper bound của token bucket

Giả sử bucket ban đầu đầy, capacity **C**, refill liên tục **r token/giây**, mỗi request tiêu đúng **1 token**, không có reset hoặc sửa config giữa chừng. Trong một khoảng thời gian độ dài **T**, số lượt được cấp tối đa thỏa:

\[
A(T) \le C + rT.
\]

Vì số request là số nguyên, có thể sử dụng giới hạn nguyên dựa trên cách làm tròn của implementation. Trong khoảng **5 giây** với C = 20 và r = 10 token/giây, tổng số request được cấp không được vượt **70** theo mô hình lý tưởng. Trong **60 giây**, giới hạn là **620**.

Lưu ý:

- Giới hạn này **bao gồm burst token có sẵn**; nó không khẳng định số cho phép trong mọi giây đúng bằng r.
- Ở cửa sổ ngắn, số request có thể vượt r do token tích lũy.
- Mỗi cửa sổ trượt bất kỳ có thể bắt đầu với tối đa C token, nên giới hạn dài hạn vẫn có dạng C + rT.
- Với số học dấu phẩy động, thời điểm sát boundary cần tolerance nhỏ và cách làm tròn đã được định nghĩa.
- Nếu một request tốn nhiều token, cần tính theo **tổng cost**, không chỉ số request.

Ví dụ hệ thống được chào mời **200 request/giây** suốt 60 giây, với C = 20, r = 10/giây. Trong 12.000 request đầu vào, số được cấp theo mô hình lý tưởng **không vượt 620** và số từ chối **ít nhất 11.380**, giả sử từng request yêu cầu một permit, không chờ vô hạn và không có thay đổi chính sách. Thực tế số được cấp có thể ít hơn nếu tải không tới đúng thời điểm refill hoặc backend không theo kịp.

### 3.2. Tốc độ sustained sau khi hết burst

Khi hết số token ban đầu và vẫn có request đủ dày, throughput được cấp dài hạn phải tiến tới refill rate **r**, không tăng theo offered load. Đối với C = 20, r = 10/giây:

- Trong vài mili giây đầu có thể cấp tới 20 request.
- Sau khi cạn token, cần khoảng **100 ms** để có một token mới.
- Với tải đủ lớn, khoảng 10 request mới mỗi giây có thể được cấp về lâu dài.
- Nếu không có tải một thời gian, bucket có thể tích token lại và tạo burst mới.

**Sustained load test không chỉ kiểm tra tổng request được cấp**: nó còn phải đo p95/p99 latency, CPU, queue age, upstream errors và số message được trả kết quả hay chuyển sang defer.

## 4. Lập kế hoạch kiểm thử theo giả định có thể đo

Một test plan cần nêu ít nhất:

| Tham số | Ví dụ | Lý do |
| --- | --- | --- |
| Điểm đặt limiter | Trước StockClient | Mỗi HTTP attempt được kiểm soát |
| Quota scope | stock.read:GLOBAL | Nhiều pod dùng cùng một ngân sách |
| Thuật toán | Token bucket | Biết capacity/refill rõ ràng |
| Capacity | 20 | Burst đầu được cho phép |
| Refill | 10 token/giây | Throughput dài hạn mong muốn |
| Cost | 1 token cho mỗi HTTP attempt | Retry cũng cần tính permit |
| Chính sách khi cạn | Reject ngay | Không giữ thread chờ |
| Offered load | 200 request/giây | Cao hơn khả năng cấp phép |
| Thời lượng | 60 giây | Quan sát sustained sau burst |
| Kết quả từ upstream | Fake Stock API trả 200 trong 10 ms | Tách lỗi upstream khỏi limiter |
| Tiêu chí đạt | Upper bound, không overshoot, outcome rõ | Có assertion kiểm chứng được |

Khi thay đổi một tham số như retry, số pod, thời gian xử lý upstream hoặc chính sách queue, cần xác nhận lại **đơn vị quota**. Một request Gateway có thể tạo nhiều outbound calls qua Splitter; không được so trực tiếp request đầu vào với permit dành cho từng call vật lý mà bỏ qua hệ số fan-out.

### 4.1. Ba tầng kiểm thử nên có

1. **Unit test xác định được thời gian:** dùng fake clock để kiểm tra capacity, refill, boundary và thread safety mà không sleep.
2. **Integration test Spring Integration:** gửi message qua Gateway/Filter/Router và xác nhận khi RATE_LIMITED thì StockClient không bị gọi; giữ correlation và outcome.
3. **Load/distributed test:** dùng load generator độc lập, nhiều process/pod, shared quota backend hoặc limiter implementation thật; đo throughput, latency và lỗi dưới burst/sustained load.

Unit test trong một JVM **không chứng minh quota toàn cluster**, cho dù nhiều thread gọi chung một object.

## 5. Tạo token bucket có clock điều khiển được để học và test

Để tránh unit test phụ thuộc scheduler, ta dùng một token bucket đơn giản nhận **LongSupplier** làm nguồn thời gian đơn điệu dạng nano giây. Test cập nhật AtomicLong thay vì chờ thời gian thực.

**Đây là implementation minh họa trong một JVM**, không phải distributed limiter, không hỗ trợ policy version/hot reload, không có persistence và không thay thế một thư viện production đã được kiểm thử.

~~~java
public final class DeterministicTokenBucket {

    private final int capacity;
    private final double refillPerSecond;
    private final LongSupplier tickerNanos;

    private double tokens;
    private long lastNanos;

    public DeterministicTokenBucket(
            int capacity,
            double refillPerSecond,
            LongSupplier tickerNanos
    ) {
        if (capacity <= 0 || !Double.isFinite(refillPerSecond)
                || refillPerSecond <= 0 || tickerNanos == null) {
            throw new IllegalArgumentException("Invalid bucket config");
        }
        this.capacity = capacity;
        this.refillPerSecond = refillPerSecond;
        this.tickerNanos = tickerNanos;
        this.tokens = capacity; // Bucket bắt đầu đầy.
        this.lastNanos = tickerNanos.getAsLong();
    }

    public synchronized boolean tryAcquire() {
        long now = tickerNanos.getAsLong();

        if (now > lastNanos) {
            double elapsedSeconds =
                    (now - lastNanos) / 1_000_000_000.0;
            tokens = Math.min(
                    capacity,
                    tokens + elapsedSeconds * refillPerSecond
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
~~~

Giải thích:

- **synchronized** bảo đảm hai thread trong cùng JVM không cùng trừ một token.
- **tickerNanos** có thể dùng **System::nanoTime** khi chạy thông thường, và **AtomicLong::get** trong test. Đồng hồ này dùng đo khoảng thời gian, không dùng như timestamp để log.
- Refill chỉ diễn ra khi now lớn hơn lastNanos; tránh cộng thời gian âm nếu fake clock đi lùi.
- **Math.min(capacity, ...)** ngăn token tích lũy vượt burst capacity.
- Dùng **double** cho đơn giản; production cần quy tắc số học, rounding, overflow và deadline chặt chẽ hơn.
- Bucket khởi tạo đầy là một **chính sách**. Một số hệ thống khởi tạo rỗng hoặc warmup để tránh burst ngay khi khởi động.

Với clock giả, cần bắt đầu từ giá trị cố định và chỉ tăng. Không nên dùng **System.currentTimeMillis** để đo elapsed time ở một thuật toán cần tính khoảng ngắn vì wall clock có thể bị điều chỉnh.

## 6. Unit test burst tại cùng một thời điểm

Nếu capacity = 5 và refill = 2 token/giây, khi clock chưa tiến thì:

- Năm lần tryAcquire đầu tiên phải thành công.
- Lần thứ sáu phải bị từ chối.
- Sau 500 ms mới bổ sung được một token.
- Khi không có thời gian trôi qua tiếp, lời gọi ngay sau permit thứ sáu lại bị từ chối.

~~~java
@Test
void burstConsumesCapacityAndThenRejects() {
    AtomicLong nanos = new AtomicLong(0);
    DeterministicTokenBucket bucket =
            new DeterministicTokenBucket(
                    5, 2.0, nanos::get
            );

    for (int i = 0; i < 5; i++) {
        assertTrue(bucket.tryAcquire());
    }
    assertFalse(bucket.tryAcquire());

    nanos.addAndGet(500_000_000L); // 500 ms, đúng 1 token.
    assertTrue(bucket.tryAcquire());
    assertFalse(bucket.tryAcquire());
}
~~~

Test không sleep nên rất ổn định. Nó kiểm chứng **capacity, reject sau burst và refill** chứ chưa kiểm tra concurrency.

### 6.1. Cạnh tranh 40 thread cho 10 permit

~~~java
@Test
void concurrentBurstNeverGrantsMoreThanCapacity()
        throws Exception {
    AtomicLong nanos = new AtomicLong(0);
    DeterministicTokenBucket bucket =
            new DeterministicTokenBucket(10, 1.0, nanos::get);

    ExecutorService pool = Executors.newFixedThreadPool(40);
    CountDownLatch ready = new CountDownLatch(40);
    CountDownLatch start = new CountDownLatch(1);
    List<Future<Boolean>> futures = new ArrayList<>();

    try {
        for (int i = 0; i < 40; i++) {
            futures.add(pool.submit(() -> {
                ready.countDown();
                start.await();
                return bucket.tryAcquire();
            }));
        }

        assertTrue(ready.await(5, TimeUnit.SECONDS));
        start.countDown();

        int granted = 0;
        for (Future<Boolean> future : futures) {
            if (future.get()) {
                granted++;
            }
        }

        assertEquals(10, granted);
        assertEquals(30, futures.size() - granted);
    } finally {
        start.countDown();
        pool.shutdownNow();
    }
}
~~~

**Điểm quan sát:** 40 thread cùng tranh một bucket đã đầy 10 token; vì fake clock không thay đổi, **chỉ 10 lần ALLOW**. Nếu implementation dùng “đọc tokens → kiểm tra → ghi tokens” không nguyên tử, hai thread có thể cùng nhận cùng một token, dẫn đến overshoot.

Đây là test thread safety **trong một process**, không bảo đảm Redis/script/database hoặc các pod thực tế sử dụng cùng một bộ đếm.

## 7. Unit test sustained load với fake time

Sau khi dùng hết burst ban đầu, một limiter refill 10 token/giây phải cấp tối đa một token mỗi 100 ms. Ta có thể mô phỏng **60 giây sustained load** chỉ trong một bài test không sleep.

~~~java
@Test
void sustainedLoadConvergesToRefillRate() {
    AtomicLong nanos = new AtomicLong(0);
    DeterministicTokenBucket bucket =
            new DeterministicTokenBucket(10, 10.0, nanos::get);

    // Xóa burst ban đầu để chỉ đo khả năng refill.
    for (int i = 0; i < 10; i++) {
        assertTrue(bucket.tryAcquire());
    }
    assertFalse(bucket.tryAcquire());

    int allowed = 0;
    int rejected = 0;

    for (int step = 0; step < 600; step++) {
        nanos.addAndGet(100_000_000L); // 100 ms.
        if (bucket.tryAcquire()) {
            allowed++;
        }

        // Một request nữa tới ngay cùng thời điểm.
        if (!bucket.tryAcquire()) {
            rejected++;
        }
    }

    assertEquals(600, allowed);  // 60 s x 10 token/s.
    assertEquals(600, rejected); // Không tích token ngoài capacity.
}
~~~

**Giới hạn của test:** nguồn thời gian được điều khiển và không có chi phí network/scheduler. Vì vậy test cho thấy **thuật toán refill**, không phải chứng cứ rằng hệ thống có thể xử lý 10 HTTP calls/giây khi upstream chậm.

Một sustained-load test thật nên đo:

- **Offered RPS** từ load generator độc lập.
- **Allowed RPS**, **rejected RPS** và **outbound RPS**.
- **Latency p50/p95/p99** của Gateway và Stock Client.
- **Thread count, CPU, memory, connection pool và in-flight calls**.
- **Queue depth/oldest age** nếu request được defer.
- **Error codes và fallback outcomes** để không nhầm một request được chấp nhận với một giao dịch đã thành công.

## 8. Kiểm thử Resilience4j RateLimiter: semantics theo refresh period

Nếu dùng **Resilience4j RateLimiter** thay vì token bucket tự viết, cấu hình tiêu biểu là:

~~~java
RateLimiterConfig config = RateLimiterConfig.custom()
        .limitForPeriod(10)
        .limitRefreshPeriod(Duration.ofSeconds(1))
        .timeoutDuration(Duration.ZERO)
        .build();

RateLimiter limiter = RateLimiter.of("stock-read", config);
~~~

Trong ví dụ, limiter cho một số permit theo **chu kỳ refresh** và không đợi khi hết permit vì timeoutDuration bằng 0. Đừng đặt assertion về refill liên tục từng 100 ms của token bucket lên implementation này. Những lần thử sát ranh giới refresh period có thể thấy nhiều request được phép trong một cửa sổ trượt rất ngắn.

### 8.1. Test đơn giản cho một chu kỳ rất dài

Có thể tạo cấu hình test với refresh period dài hơn đáng kể thời gian chạy test để kiểm tra burst trước khi có refresh:

~~~java
@Test
void resilienceLimiterRejectsAfterPeriodPermits() {
    RateLimiterConfig config = RateLimiterConfig.custom()
            .limitForPeriod(3)
            .limitRefreshPeriod(Duration.ofHours(1))
            .timeoutDuration(Duration.ZERO)
            .build();

    RateLimiter limiter =
            RateLimiter.of("burst-test", config);

    int allowed = 0;
    for (int i = 0; i < 10; i++) {
        if (limiter.acquirePermission()) {
            allowed++;
        }
    }

    assertEquals(3, allowed);
}
~~~

Refresh period một giờ chỉ phục vụ test **burst trong một khoảng rất ngắn**; đó không phải cấu hình vận hành. Với các bài test qua ranh giới refresh, ưu tiên cơ chế clock/timing mà implementation có thể kiểm soát hoặc integration test có dung sai thời gian và đủ số mẫu. Không dùng một vòng sleep cố định rồi khẳng định timing chính xác tới mili giây.

**Cần xác minh API và phiên bản của Resilience4j thực tế** khi đem code vào dự án. Những ví dụ này dùng các API Java phổ biến: RateLimiterConfig, RateLimiter.of và acquirePermission.

## 9. Đặt limiter tại điểm gọi phù hợp trong Spring Integration

Khi quota provider tính **mỗi HTTP attempt**, rate limiter nên nằm **sát StockClient**, sau Filter/Transformer/Router và trước lệnh gọi outbound. Nếu Gateway hoặc Splitter tạo nhiều nhánh, mỗi nhánh dùng đúng quota key cho dependency của nó.

### 9.1. Hợp đồng request và kết quả

~~~java
public record StockQuery(String sku, String correlationId) {}

public record StockOutcome(
        String sku,
        String correlationId,
        String status,
        Integer availableUnits
) {}

public interface StockClient {
    int availableUnits(String sku);
}
~~~

Với outcome:

- **FRESH**: nhận dữ liệu mới từ StockClient.
- **RATE_LIMITED**: limiter không cấp permit, không hề gọi StockClient.
- **UNAVAILABLE**: dependency hoặc cơ sở cấp quota gặp lỗi, không thể trả kết quả tin cậy.

Không tự trả **availableUnits = 0** khi RATE_LIMITED; số 0 có nghĩa nghiệp vụ “hết hàng” và khác với không thể kiểm tra tồn kho.

### 9.2. IntegrationFlow Java DSL

~~~java
@MessagingGateway(defaultRequestChannel = "stock.lookup.requests")
public interface StockGateway {
    StockOutcome lookup(StockQuery query);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockRateLimiterConfig {

    @Bean
    public RateLimiter stockReadLimiter() {
        RateLimiterConfig config = RateLimiterConfig.custom()
                .limitForPeriod(10)
                .limitRefreshPeriod(Duration.ofSeconds(1))
                .timeoutDuration(Duration.ZERO)
                .build();
        return RateLimiter.of("stock-read", config);
    }

    @Bean
    public IntegrationFlow stockLookupFlow(
            StockClient client,
            RateLimiter stockReadLimiter
    ) {
        return IntegrationFlow.from("stock.lookup.requests")
                .handle(StockQuery.class, (query, headers) -> {
                    if (!stockReadLimiter.acquirePermission()) {
                        return new StockOutcome(
                                query.sku(),
                                query.correlationId(),
                                "RATE_LIMITED",
                                null
                        );
                    }

                    int units = client.availableUnits(query.sku());

                    return new StockOutcome(
                            query.sku(),
                            query.correlationId(),
                            "FRESH",
                            units
                    );
                })
                .get();
    }
}
~~~

Ví dụ dùng limiter **trong một process**, thích hợp minh họa EIP và test một instance. Không dùng nó để cam kết **10 request/giây trên toàn cluster** nếu có nhiều pod độc lập. Muốn kiểm tra quota toàn cluster, thay phần acquire bằng một **SharedRateGate** có thao tác nguyên tử trên backend chung, và test bằng nhiều process.

Flow này chỉ trả RATE_LIMITED như một **outcome**. Nếu đầu vào là REST API, boundary có thể ánh xạ nó thành HTTP **429** và Retry-After theo hợp đồng. Spring Integration không tự biến một record có status RATE_LIMITED thành mã HTTP 429.

## 10. Integration test Gateway: bị chặn thì không gọi client

Mục tiêu là test hành vi message flow, không chỉ test một object RateLimiter.

Ví dụ với Spring Boot/Spring Integration test context đã đăng ký Gateway và mock StockClient:

~~~java
@Test
void gatewayReturnsRateLimitedWithoutExtraClientCalls() {
    // Test fixture riêng dùng limiter còn đúng 2 permit,
    // không chờ token mới trong khoảng kiểm thử.
    when(stockClient.availableUnits("SKU-1"))
            .thenReturn(7);

    StockQuery query = new StockQuery("SKU-1", "corr-101");

    StockOutcome first = gateway.lookup(query);
    StockOutcome second = gateway.lookup(query);
    StockOutcome third = gateway.lookup(query);

    assertEquals("FRESH", first.status());
    assertEquals("FRESH", second.status());
    assertEquals("RATE_LIMITED", third.status());

    assertNull(third.availableUnits());
    assertEquals("corr-101", third.correlationId());
    verify(stockClient, times(2))
            .availableUnits("SKU-1");
}
~~~

**Fixture bắt buộc:** trong test context, cần cấu hình limiter giới hạn **2 permit** với refresh period đủ dài, tách biệt instance limiter của test khỏi các test khác. Nếu để limiter mặc định 10 permit hoặc dùng chung một singleton qua nhiều test, assertion trên có thể sai không phải vì flow hỏng mà vì fixture không xác định.

Kiểm thử thêm:

1. Filter loại SKU không hợp lệ **trước limiter**.
2. Router đi tới nhánh Pricing không làm tiêu permit Stock.
3. Gateway reply/correlation đúng ở cả FRESH và RATE_LIMITED.
4. Khi StockClient ném timeout sau khi permit được cấp, quota vật lý đã được tiêu; error path phải rõ.
5. Khi một nhánh Splitter bị rate limit, Aggregator không chờ thiếu reply vô hạn.

## 11. Burst load test thực tế: tránh lỗi ở ranh giới và công cụ tạo tải

Đối với token bucket C = 20, r = 10 token/giây, một burst-load test nên có ít nhất hai đợt:

**Đợt A — cùng một thời điểm logic:** gửi 100 request đồng thời vào một bucket bắt đầu đầy. Nếu thời gian không tiến và mỗi request cần một token, tối đa **20 ALLOW**, ít nhất **80 REJECT**.

**Đợt B — sau khi cạn token:** cho thời gian trôi thêm 500 ms. Với refill 10/s, có thể nhận **5 token mới** nếu bucket vẫn còn 0. Nếu không có token nào được tiêu trước đợt thứ hai, có tối đa 5 request mới được phép, phần còn lại bị từ chối.

Với load generator thật, không thể cho 100 network requests đến **chính xác cùng nano giây**. Refill có thể diễn ra trong lúc requests đến, nên **không dùng assertion đúng bằng 20** cho một test kéo dài hàng trăm mili giây; so sánh với bound theo **elapsed time thực**, dung sai hợp lý và đo timestamp phía limiter nếu cần.

### 11.1. Chọn load generator

Có thể dùng k6, Gatling, JMeter hoặc công cụ nội bộ; điều quan trọng không phải tên công cụ mà là **cách nó phát request**.

- **Open-loop:** phát request theo lịch có target arrival rate, không giảm lượng đề nghị chỉ vì server xử lý chậm. Hữu ích để kiểm tra limiter khi bị overload.
- **Closed-loop:** mỗi virtual user gửi request kế tiếp sau khi nhận response. Khi latency tăng, offered load có thể **tự giảm**, khiến limiter trông như đã qua sustained-load test dù không bị ép đủ tải.

Khi đo overload, dùng open-loop hoặc ít nhất đo **arrival rate thực** và số request bị load generator bỏ lịch vì chính bản thân nó quá tải. Hiện tượng **coordinated omission** có thể làm latency và mức nghẽn trông tốt hơn thực tế nếu driver dừng tạo request khi target chậm.

Tách **load generator** khỏi máy chạy application nếu cần độ tin cậy; nếu chúng tranh CPU, số đo dễ bị méo.

### 11.2. Burst nhiều tenant

Nếu có quota riêng theo tenant, gửi burst đồng thời từ tenant A và B:

- Nếu A và B có bucket độc lập, việc A hết token không được làm B bị từ chối.
- Nếu hai tenant thuộc cùng quota group, tổng permit phải nằm trong bound của bucket chung.
- Tenant context phải được xác thực; request giả mạo tenant không được tạo một bucket mới để vượt quota.

Bài test cần đối chiếu **bucket scope**, không chỉ tổng số response 429.

## 12. Sustained-load test: giữ tải lâu và đo toàn bộ vòng đời

Một kế hoạch load test minh họa trong môi trường test/staging:

| Giai đoạn | Thời lượng | Offered load | Mục đích |
| --- | --- | --- | --- |
| Warmup | 30 giây | 5 req/s | Ổn định JVM, connection pool và monitoring |
| Burst | 1–2 giây | 200 req/s | Kiểm tra capacity, reject và race |
| Sustained | 5 phút | 200 req/s | Kiểm tra refill, throughput, latency và leak |
| Recovery | 1 phút | 5 req/s | Xem hệ thống có hết backlog và trở lại bình thường |
| Idle rồi burst lại | 30 giây idle + burst | 200 req/s | Kiểm tra bucket tái tích lũy sau idle |

Các thời lượng chỉ là bài tập thiết kế, cần điều chỉnh theo SLA và tài nguyên staging. **Không phát tải ngoài hạn mức vào production hay API của bên thứ ba**; dùng fake dependency hoặc môi trường được phép kiểm thử.

### 12.1. Assertion của sustained load

Với token bucket C = 20, r = 10/s, khi cho tải đủ lớn kéo dài **T = 300 giây**, tổng admitted tối đa xấp xỉ **20 + 10 × 300 = 3.020** nếu ban đầu đầy và không reset. Để kiểm tra ổn định, nên chia từng khoảng quan sát và đánh giá:

- Tổng ALLOW tuân theo **upper bound** của bucket trong toàn khoảng.
- Sau khi hết burst, **admitted rate trung bình** tiến tới 10/s, không tăng theo offered rate 200/s.
- **Rejected rate** tăng phù hợp với overload; không âm thầm thả message.
- **Outbound calls** không vượt lượng được cấp permit nếu mỗi attempt phải lấy một permit.
- **Gateway p95/p99** của nhánh RATE_LIMITED không tăng vô hạn vì giữ thread chờ.
- **CPU, memory, thread, heap, connection pool** không tăng không giới hạn.
- Nếu có queue/defer, **queue depth/age** có chính sách giới hạn, không tích tụ mãi.
- Nếu upstream giả lập chậm, limiter không bị hiểu nhầm là bulkhead.

Phải chú ý **cửa sổ đo**: nếu warmup đã tiêu token, không còn giả định “bucket đầy tại đầu sustained”. Dùng một mốc reset có kiểm soát hoặc tính bound từ trạng thái thực, không cộng burst ban đầu hai lần.

### 12.2. Tại sao không nên assert đúng 10 request từng giây?

Token bucket cho phép token tích lũy tới capacity; request có thể đến ngay trước hoặc sau ranh giới cửa sổ đo. Trong một giây có thể thấy hơn 10 ALLOW nhờ token tích từ trước, trong giây khác ít hơn. Một assertion “mỗi giây phải đúng 10” sẽ fail sai.

Thay vào đó, kiểm tra **upper bound của mọi cửa sổ theo mô hình** và tốc độ trung bình dài hạn. Nếu upstream yêu cầu trần cứng mỗi rolling window, cần chuyển sang thuật toán hỗ trợ hợp đồng đó và viết assertion tương ứng.

## 13. Load test đa pod: tổng quota không được nhân theo số instance

Giả sử quota toàn cụm là **120 permit/giây**. Ba pod có cùng cấu hình local 120 permit/giây vẫn có thể phát tổng 360 permit/giây. Test một pod không phát hiện lỗi này.

~~~mermaid
flowchart LR
    A[Load generator] --> B[Load balancer]
    B --> C[Pod 1]
    B --> D[Pod 2]
    B --> E[Pod 3]
    C --> F[Shared atomic bucket]
    D --> F
    E --> F
    F --> G[Upstream fake]
~~~

**Bài test phân tán bắt buộc:**

1. Dùng **nhiều process/pod thật**, không chỉ nhiều thread chung JVM.
2. Mọi pod hướng vào **cùng authoritative bucket key**; state không bị tạo theo pod.
3. Bắt đầu bằng bucket có **120 permit**, tạm ngừng refill hoặc dùng test window mà refill được kiểm soát.
4. Gửi đồng thời hơn **120 yêu cầu** qua ít nhất ba pod.
5. Xác minh **tổng ALLOW tối đa 120**, dù mỗi pod có nhiều request.
6. Scale lên bốn hoặc sáu pod và kiểm tra tổng quota **không tự nhân**.
7. Kiểm thử Redis/database backend thật trong điều kiện race, timeout và failover.

Nếu có **global + per-tenant quota**, cần test cả hai giới hạn. Khi cấp nhiều permit thuộc nhiều bucket, thao tác phải atomic theo contract; nếu chỉ trừ tuần tự, một lỗi giữa chừng có thể làm lệch ngân sách.

**Lưu ý mức bảo đảm:** một shared atomic store có thể cấp permit đúng theo key tại một node, nhưng failover/replication và network partition có thể làm mất cập nhật. Nếu yêu cầu không vượt quota dưới mọi lỗi, phải xác minh chính sách HA/consistency của backend; không chỉ thử concurrent calls lúc cluster khỏe.

## 14. Tương tác với Retry, Circuit Breaker, Queue và Aggregator

### 14.1. Retry làm tăng số lần cần permit

Nếu một Gateway request được retry ba lần và provider tính quota theo **HTTP attempt**, limiter phải cấp token cho **mỗi attempt**. Nếu gate nằm ngoài Retry, có thể xảy ra một permit cho ba lời gọi vật lý, làm vượt quota provider.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Retry hữu hạn]
    B --> C[Rate limiter]
    C -->|ALLOW| D[StockClient]
    C -->|REJECT| E[Không retry tức thời]
~~~

Một lỗi RATE_LIMITED không nên bị Retry bắt rồi thử lại liên tục trong cùng handler. Với message bất đồng bộ, có thể defer tới lịch sau nếu còn TTL/attempt budget.

Bài test cần có:

- Một request có 1, 2 hoặc 3 attempt vật lý.
- Số lần cấp permit phù hợp số outbound calls thực tế.
- Nếu permit bị từ chối, StockClient **không được gọi** ở attempt đó.
- Không có vòng retry vô hạn do hết token.
- Tác vụ ghi cần **idempotency key**, không tự phát lại vì mất response.

### 14.2. Rate limiter không được làm sai circuit breaker

Limiter REJECTED là **quyết định quota**, không phải Stock API vừa lỗi. Nếu dùng cùng một generic exception cho RATE_LIMITED và UPSTREAM_TIMEOUT rồi đưa vào breaker, breaker có thể OPEN dù dependency khỏe.

Nên tách:

- **RATE_LIMITED**: không được cấp permit, thường không đi qua client/breaker để tính upstream failure.
- **BREAKER_REJECTED**: circuit không cấp quyền vì tình trạng dependency.
- **UPSTREAM_TIMEOUT**: client được gọi và thất bại.
- **BULKHEAD_FULL**: hết tài nguyên đồng thời.

Vị trí order của RateLimiter, CircuitBreaker và Retry có tác động khác nhau. Viết rõ thứ tự và kiểm thử bằng **permit counter + remote-call counter + exception category**.

### 14.3. Gateway, Filter, Router và Aggregator

- **Filter** nên loại request không hợp lệ trước limiter, để validation error không tiêu quota outbound.
- **Router** đưa message vào bucket của đúng dependency/operation; không dùng chung Stock và Pricing ngoài ý muốn.
- **Gateway** phải nhận RATE_LIMITED result hoặc exception có hợp đồng; không để caller chờ vô hạn.
- **Splitter** có thể nhân một message thành nhiều outbound calls; mỗi nhánh phải lấy permit đúng đơn vị quota.
- **Aggregator** cần nhận outcome RATE_LIMITED cho nhánh bị chặn, hoặc có group timeout/partial result; không chờ thiếu reply mãi.
- **Error channel** cần phân biệt reject bình thường với exception kỹ thuật. Không mặc định limiter trả false sẽ tự tạo ErrorMessage.
- **Correlation ID** và sequence metadata cần giữ xuyên qua reject/fallback để truy vết message.

Nếu một request bị hoãn vào durable queue, phải có **nextAttemptAt**, attempts tối đa, TTL, DLQ, backpressure và idempotency để queue không tích tụ vô hạn khi sustained load lớn hơn năng lực cấp permit.

## 15. Ma trận kiểm thử hoàn chỉnh

| Kịch bản | Tiêu chí pass |
| --- | --- |
| Bucket bắt đầu đầy | C permit đầu được cấp, request kế tiếp bị reject tại cùng timestamp |
| Bucket bắt đầu rỗng | Chỉ cấp permit khi đã refill đủ |
| Cạn token và clock không tiến | Không cấp thêm token |
| Refill sau 500 ms | Số token mới đúng theo rate và quy tắc làm tròn |
| Idle lâu | Token không vượt capacity |
| Burst 40 thread trong 1 JVM | Không cấp quá capacity, không race |
| Burst có boundary refresh | Assertion theo thuật toán; không dùng công thức token bucket cho fixed window |
| Sustained offered rate cao hơn quota | Admitted rate dài hạn không tăng theo offered rate |
| Sustained offered rate thấp hơn quota | Không reject vô cớ khi còn permit |
| Tải kéo dài nhiều phút | CPU/memory/thread/queue không tăng vô hạn |
| Nhiều pod, cùng bucket | Tổng ALLOW không nhân theo pod |
| Global và tenant quota cùng tồn tại | Mỗi giới hạn đều được thực thi theo scope |
| Tenant chưa xác thực | Không thể tạo key mới để vượt quota |
| Config giảm quota khi đang chạy | Không overshoot ngoài mức bảo đảm migration |
| Retry khi outbound timeout | Mỗi HTTP attempt tiêu permit đúng chính sách |
| Limiter reject | Không gọi client, không retry tức thời |
| Circuit breaker OPEN | Không tính RATE_LIMITED thành upstream failure |
| Splitter có một nhánh bị chặn | Aggregator trả partial/error đúng và không treo |
| Shared quota store timeout | Fail-open/fail-closed/defer theo policy, có metric |
| Acquire response bị mất | Xử lý trạng thái chưa rõ, không tự cấp token trùng |
| Backend failover | Mức bảo đảm quota phù hợp thiết kế, có test riêng |
| Autoscaling | Tổng quota và metric vẫn đúng khi số pod thay đổi |
| Metrics/tracing | Allowed, rejected, remote calls, correlation và outcome khớp nhau |

Không nên chỉ khẳng định “test pass” vì tổng response 200 đủ lớn. Với limiter, **REJECTED đúng chính sách cũng là một kết quả hợp lệ**. Pass/fail phải dựa trên quota, fairness, latency và mức suy giảm đã định nghĩa.

## 16. Metrics và cách đọc kết quả load test

| Metric | Ý nghĩa |
| --- | --- |
| **attempted_total / offered_rps** | Tổng request đi vào limiter |
| **allowed_total / admitted_rps** | Tổng permit đã cấp |
| **rejected_total / rejected_rps** | Tổng request bị từ chối vì quota |
| **client_calls_total** | Số HTTP calls thực sự được thực thi |
| **gateway_latency p50/p95/p99** | Thời gian caller nhận kết quả |
| **rate_gate_latency** | Chi phí quyết định permit |
| **in_flight / connection pool usage** | Độ đồng thời, tránh hiểu nhầm với rate |
| **retry_attempts** | Số lời gọi thêm do Retry |
| **fallback_total** | Kết quả cache/unavailable, không phải fresh |
| **queue_depth / oldest_message_age** | Backlog khi defer |
| **aggregator_expired_groups** | Nhánh RATE_LIMITED làm thiếu reply |
| **quota_store_errors / config_version** | Backend và rollout có đang khỏe không |

Các đẳng thức hữu ích để kiểm tra trong một phạm vi đã định nghĩa:

~~~text
attempted = allowed + rejected + other_terminal_decisions

client_calls <= allowed
    (khi một ALLOW cấp quyền cho tối đa một outbound attempt)

completed_success <= client_calls
    (khi đang đo success thật của upstream)
~~~

Các đẳng thức cần hiểu theo **cùng khoảng đo, cùng bucket và cùng đơn vị đếm**, có xét in-flight requests ở ranh giới. Nếu tổng counter được thu thập bất đồng bộ từ nhiều pod, có thể có sai lệch tạm thời do scrape lag; không lập tức kết luận lỗi thuật toán từ một snapshot lệch mili giây.

**Không gắn request ID, SKU, correlation ID vào metric tags** nếu cardinality rất lớn. Dùng tag ổn định như **limiter name**, **operation**, **tenant group**, **region**, **outcome**. ID chi tiết nên nằm trong log/trace có kiểm soát.

### 16.1. Biểu hiện thường gặp của cấu hình sai

- **Burst đúng nhưng sustained vượt quota:** refill được cộng sai hoặc mỗi pod dùng local bucket.
- **Sustained đúng nhưng burst làm upstream quá tải:** capacity quá cao hoặc thiếu bulkhead.
- **RPS trông ổn vì load generator bị chậm:** cần so target arrival rate với observed offered rate.
- **Allowed cao nhưng client calls thấp:** có thể còn pending, cache/fallback hoặc lỗi flow trước client.
- **Reject nhanh nhưng Gateway latency rất cao:** retry, queue hoặc Aggregator vẫn đang chờ.
- **Nhiều HTTP 429 từ upstream dù limiter ít reject:** quota key sai, retry bypass gate hoặc có traffic ngoài hệ thống đang dùng chung upstream.
- **Một tenant chiếm gần hết permit:** thiếu phân vùng quota/fairness hoặc shared scope không phù hợp.

## 17. Checklist thực hành

- [ ] Ghi rõ scope, algorithm, capacity, refill/refresh period và cost mỗi request.
- [ ] Phân biệt token bucket, fixed-window và Resilience4j refresh-cycle semantics.
- [ ] Unit test burst và refill bằng fake clock; không dựa vào sleep dài.
- [ ] Test race đồng thời để không cấp vượt capacity khi cạn token.
- [ ] Dùng offered load cao hơn quota trong sustained test; đo arrival rate thực.
- [ ] Theo dõi admitted, rejected, completed throughput và p95/p99 latency.
- [ ] Kiểm tra burst cap và upper bound dài hạn; không assert từng giây phải đúng r.
- [ ] Kiểm tra CPU, memory, thread, connection pool, queue depth và recovery.
- [ ] Integration test Gateway/Filter/Router và StockClient call counter.
- [ ] Test Retry, Circuit Breaker, timeout và kết quả RATE_LIMITED riêng biệt.
- [ ] Splitter/Aggregator có outcome/correlation và group timeout cho nhánh bị chặn.
- [ ] Test nhiều pod và shared backend thực, không nhầm thread test với distributed test.
- [ ] Test quota theo tenant/global, config update, autoscaling và backend outage.
- [ ] Không phát tải không kiểm soát tới production hoặc provider ngoài.
- [ ] Dashboard phân biệt ALLOW/REJECT/ERROR, client calls và latency theo scope.

**Kiểm thử burst và sustained load** xác nhận hai năng lực khác nhau của rate limiter: **khống chế đợt tăng tải tức thời** và **duy trì tốc độ dài hạn trong giới hạn**. Khi kết hợp giả lập thời gian để test thuật toán, integration test qua Spring Integration Gateway/Router/Filter, và load test nhiều pod với telemetry đầy đủ, ta có thể chứng minh limiter bảo vệ dependency đúng mục tiêu mà không làm mất message, che lỗi retry hoặc khiến Aggregator treo khi bị từ chối.
