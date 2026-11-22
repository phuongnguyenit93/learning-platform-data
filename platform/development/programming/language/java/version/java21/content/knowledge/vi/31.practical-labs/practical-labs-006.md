# Bổ sung timeout, cancellation, semaphore và context cho từng request

Trong bài thực hành này, xây dựng một request handler tổng hợp dữ liệu từ nhiều dịch vụ đối tác. Mỗi request có deadline chung; các lời gọi chạy đồng thời bằng virtual thread; một `Semaphore` dùng chung giới hạn số lời gọi đang hoạt động; context như trace ID và tenant reference được truyền tường minh tới từng task; các task còn lại bị hủy khi hết deadline hoặc request bên ngoài bị interrupt.

Bài lab kết hợp các API ổn định có trong Java 21: `ExecutorService`, `Executors.newVirtualThreadPerTaskExecutor()`, `Future`, `ExecutorCompletionService`, `Semaphore`, `ThreadLocal`, `Duration` và `System.nanoTime()`. Không cần bật preview feature.

## 1. Bài toán và yêu cầu

Giả sử endpoint `GET /dashboard` cần lấy dữ liệu từ ba dịch vụ: catalog, pricing và inventory. Các dịch vụ có độ trễ khác nhau; nếu một dịch vụ chậm, endpoint vẫn cần trả kết quả từng phần trong ngân sách thời gian cho phép.

Yêu cầu của bài lab:

| Yêu cầu | Quy tắc |
|---|---|
| Deadline request | Ngân sách chờ kết quả là 700 ms trong ví dụ |
| Concurrent I/O | Mỗi lời gọi đối tác chạy trên virtual thread |
| Giới hạn tải downstream | Tối đa 2 lời gọi đối tác đồng thời trên mỗi JVM instance |
| Kết quả | Thu thập kết quả theo thứ tự hoàn thành, không chờ theo thứ tự gửi |
| Timeout | Mỗi bước dùng phần thời gian còn lại của cùng deadline |
| Cancellation | Hủy các task chưa hoàn tất khi deadline hết hoặc handler bị interrupt |
| Context | Truyền trace ID và tenant reference; không truyền password/token trong context chung |
| Cleanup | Luôn trả semaphore permit và khôi phục/xóa ThreadLocal trong `finally` |

`Semaphore` phải được chia sẻ giữa các request trong cùng JVM. Nếu tạo một semaphore mới bên trong mỗi request, giới hạn concurrency sẽ áp dụng riêng từng request và không bảo vệ được dịch vụ downstream khỏi tổng tải của process. `Semaphore` không phải distributed limiter: nếu chạy 5 JVM instance, mỗi instance có 2 permit thì tổng số lời gọi có thể lên tới 10. Nếu quota cần áp dụng trên toàn cluster, dùng gateway hoặc cơ chế distributed rate/concurrency limiting phù hợp.

## 2. Thiết kế luồng xử lý

```text
Request đến
    |
    v
Tạo deadline bằng System.nanoTime()
    |
Cài RequestContext trên thread xử lý request
    |
Submit các task vào virtual-thread executor dùng chung
    |
Mỗi task capture context và chạy độc lập
    |
Thử lấy Semaphore permit với thời gian còn lại
    |
Gọi dịch vụ đối tác với timeout còn lại
    |
CompletionService nhận task hoàn thành trước
    |
    +---- Đủ kết quả ------------------> Trả response tổng hợp
    |
    +---- Hết deadline ----------------> cancel(true) task còn lại
    |
    +---- Request bị interrupt --------> cancel(true), truyền interrupt lên
    |
Mỗi task finally: release permit + restore context
```

Deadline được tính bằng `System.nanoTime()` vì đây là đồng hồ đơn điệu phù hợp để đo khoảng thời gian. Không dùng `LocalDateTime.now()` hoặc `System.currentTimeMillis()` để trừ thời gian timeout vì đồng hồ hệ thống có thể được điều chỉnh.

## 3. Tạo context tối thiểu cho request

Context chỉ chứa thông tin cần cho correlation và định tuyến. Không lưu bearer token, password, cookie hoặc secret vào `ThreadLocal` dùng chung. `tenantRef` là dữ liệu định tuyến trong ví dụ, không phải bằng chứng caller được phép truy cập tenant; kiểm tra authorization tại service/data boundary.

```java
record RequestContext(String traceId, String tenantRef) {
    RequestContext {
        Objects.requireNonNull(traceId);
        Objects.requireNonNull(tenantRef);
        if (!traceId.matches("[A-Za-z0-9._-]{1,128}") || tenantRef.isBlank()) {
            throw new IllegalArgumentException("Invalid request context");
        }
    }
}
```

Khai báo context hiện tại:

```java
private static final ThreadLocal<RequestContext> CURRENT_CONTEXT =
        new ThreadLocal<>();
```

ThreadLocal không tự truyền context từ request thread sang task được submit vào executor. Vì vậy, cần capture snapshot ở thời điểm submit và cài đặt nó trong phạm vi task. Sau khi task kết thúc, khôi phục context trước đó hoặc gọi `remove()`.

## 4. Dùng một deadline chung cho toàn bộ request

Không cấp cho mỗi dịch vụ một timeout độc lập bằng toàn bộ request timeout. Nếu ba dịch vụ đều được chờ tối đa 700 ms tuần tự hoặc theo từng bước, tổng thời gian có thể vượt xa ngân sách 700 ms.

```java
private static long deadlineAfter(Duration timeout) {
    if (timeout.isZero() || timeout.isNegative()) {
        throw new IllegalArgumentException("timeout must be positive");
    }

    return System.nanoTime() + timeout.toNanos();
}

private static long remainingNanos(long deadlineNanos) {
    long remaining = deadlineNanos - System.nanoTime();
    return Math.max(remaining, 0L);
}
```

Tạo deadline một lần khi bắt đầu request. Mỗi lần chờ semaphore, chờ Future hoặc gọi I/O, tính lại thời gian còn lại. Nhờ vậy, thời gian xếp hàng và thời gian thực thi cùng tiêu thụ một ngân sách chung.

Với request timeout là 700 ms:

| Thời điểm | Thời gian đã dùng | Ngân sách còn lại |
|---|---:|---:|
| Bắt đầu request | 0 ms | 700 ms |
| Chờ permit | 100 ms | 600 ms |
| Gọi downstream | 250 ms | 350 ms |
| Tổng thời gian gần deadline | 650 ms | 50 ms |

Các con số trong bảng chỉ minh họa cách trừ deadline. Trong code, dùng nanosecond để tránh làm tròn từng bước sang millisecond.

Deadline giới hạn thời gian các thao tác chờ trong logic ứng dụng; nó không phải bảo đảm hard real-time rằng method luôn trả về đúng tại millisecond thứ 700. Scheduler, xử lý interrupt và cleanup có thể khiến thời điểm trả về thực tế trễ hơn một chút. Vì vậy, vẫn cần đo latency quan sát được và đặt ngân sách phù hợp cho tầng gọi.

## 5. Giới hạn concurrency bằng Semaphore dùng chung

Khai báo semaphore tại phạm vi ứng dụng hoặc phạm vi client downstream, không tạo lại cho từng request:

```java
private static final Semaphore PARTNER_LIMIT = new Semaphore(2, true);
```

Hai tham số có ý nghĩa:

- `2`: tối đa hai task cùng giữ permit để gọi các dịch vụ đối tác.
- `true`: yêu cầu fairness tại điểm cấp permit cho các task đang chờ; fairness có thể giảm throughput trong một số workload nhưng hạn chế việc task mới vượt qua task đã chờ lâu.

Semaphore giới hạn số lời gọi đang in-flight, không giới hạn số request mỗi giây. Nếu downstream áp dụng quota theo tốc độ, cần thêm rate limiter/token bucket hoặc cơ chế quota riêng.

Task lấy permit bằng `tryAcquire(remaining, NANOSECONDS)`. Đây là thao tác có timeout và có thể bị interrupt. Không dùng `acquire()` vô thời hạn trong request có deadline.

```java
long remaining = remainingNanos(deadlineNanos);
if (remaining == 0
        || !PARTNER_LIMIT.tryAcquire(remaining, TimeUnit.NANOSECONDS)) {
    throw new TimeoutException("No downstream permit before deadline");
}

try {
    // Gọi dịch vụ đối tác.
} finally {
    PARTNER_LIMIT.release();
}
```

Chỉ release sau khi đã acquire thành công. Đặt `release()` trong `finally` để bảo đảm permit được trả khi I/O thành công, ném exception, timeout hoặc task bị interrupt.

## 6. Capture và khôi phục context cho từng task

Wrapper sau đây capture context tại thời điểm submit:

```java
private static <T> Callable<T> withContext(Callable<T> task) {
    RequestContext captured = CURRENT_CONTEXT.get();

    return () -> {
        RequestContext previous = CURRENT_CONTEXT.get();

        if (captured == null) {
            CURRENT_CONTEXT.remove();
        } else {
            CURRENT_CONTEXT.set(captured);
        }

        try {
            return task.call();
        } finally {
            if (previous == null) {
                CURRENT_CONTEXT.remove();
            } else {
                CURRENT_CONTEXT.set(previous);
            }
        }
    };
}
```

Wrapper xử lý cả trường hợp context được capture là `null`: nó xóa context có thể còn sót trên worker trong lúc chạy task. Sau khi task hoàn tất, context cũ của worker được khôi phục.

Virtual-thread-per-task executor tạo thread riêng cho từng task, nhưng truyền context tường minh vẫn giúp code có hợp đồng rõ ràng và có thể tái sử dụng nếu executor thay đổi. Không dùng `InheritableThreadLocal` để ngầm truyền mọi dữ liệu request.

## 7. Định nghĩa client và kết quả

Để lab chạy được mà không cần dịch vụ mạng, tạo một interface client có timeout và một implementation giả lập độ trễ:

```java
@FunctionalInterface
interface PartnerClient {
    String fetch(
            String partner,
            RequestContext context,
            Duration timeout
    ) throws Exception;
}

record PartnerResult(String partner, String value, Duration elapsed) { }

record AggregateResponse(
        List<PartnerResult> successes,
        Map<String, String> failures,
        boolean deadlineExceeded
) {
    AggregateResponse {
        successes = List.copyOf(successes);
        failures = Collections.unmodifiableMap(new LinkedHashMap<>(failures));
    }
}
```

Implementation giả lập tôn trọng timeout và dùng `sleep` có thể interrupt để mô phỏng một thao tác I/O đang chờ:

```java
static final class SimulatedPartnerClient implements PartnerClient {
    private final Map<String, Duration> latency;
    private final AtomicInteger activeCalls = new AtomicInteger();
    private final AtomicInteger maxConcurrentCalls = new AtomicInteger();

    SimulatedPartnerClient(Map<String, Duration> latency) {
        this.latency = Map.copyOf(latency);
    }

    @Override
    public String fetch(
            String partner,
            RequestContext context,
            Duration timeout
    ) throws InterruptedException, TimeoutException {

        long plannedNanos = latency.getOrDefault(
                partner, Duration.ofMillis(100)).toNanos();
        long timeoutNanos = timeout.toNanos();

        if (timeoutNanos <= 0) {
            throw new TimeoutException("No time remaining");
        }

        int active = activeCalls.incrementAndGet();
        maxConcurrentCalls.accumulateAndGet(active, Math::max);

        try {
            TimeUnit.NANOSECONDS.sleep(Math.min(plannedNanos, timeoutNanos));

            if (plannedNanos > timeoutNanos) {
                throw new TimeoutException("Partner timed out: " + partner);
            }

            return "data-from-" + partner + "-for-" + context.tenantRef();
        } finally {
            activeCalls.decrementAndGet();
        }
    }

    int maxConcurrentCalls() {
        return maxConcurrentCalls.get();
    }
}
```

`SimulatedPartnerClient` chỉ phục vụ thực hành. Nó không mô phỏng đầy đủ network stack, connection pool, retry hoặc timeout của một HTTP client thật. Điểm quan trọng là `sleep` phản ứng với interrupt và `finally` giảm bộ đếm active call trong mọi đường thoát.

## 8. Gọi một đối tác với deadline và permit

Mỗi task lấy context đã được wrapper cài đặt, chờ permit trong phần thời gian còn lại, rồi gọi client với timeout được tính lại sau khi lấy permit:

```java
private static PartnerResult callPartner(
        String partner,
        PartnerClient client,
        Semaphore partnerLimit,
        long deadlineNanos
) throws Exception {

    long started = System.nanoTime();
    long remaining = remainingNanos(deadlineNanos);

    if (remaining == 0
            || !partnerLimit.tryAcquire(remaining, TimeUnit.NANOSECONDS)) {
        throw new TimeoutException("Timed out waiting for partner permit");
    }

    try {
        RequestContext context = CURRENT_CONTEXT.get();
        if (context == null) {
            throw new IllegalStateException("Request context is missing");
        }

        remaining = remainingNanos(deadlineNanos);
        if (remaining == 0) {
            throw new TimeoutException("Request deadline exceeded");
        }

        String value = client.fetch(
                partner,
                context,
                Duration.ofNanos(remaining)
        );

        return new PartnerResult(
                partner,
                value,
                Duration.ofNanos(System.nanoTime() - started)
        );
    } finally {
        partnerLimit.release();
    }
}
```

Elapsed time bắt đầu trước khi chờ semaphore, vì vậy nó phản ánh cả thời gian chờ permit và thời gian gọi downstream. Nếu chỉ muốn đo thời gian I/O, hãy ghi thêm một mốc thời gian ngay sau khi acquire permit.

## 9. Fan-out và fan-in theo thứ tự hoàn thành

`ExecutorCompletionService` đưa Future đã hoàn tất vào completion queue. Handler có thể nhận task xong trước mà không bị chặn bởi một task chậm đứng đầu danh sách submit.

```java
private static AggregateResponse fanOut(
        ExecutorService executor,
        Semaphore partnerLimit,
        PartnerClient client,
        List<String> partners,
        long deadlineNanos
) throws InterruptedException {

    CompletionService<PartnerResult> completion =
            new ExecutorCompletionService<>(executor);

    Map<Future<PartnerResult>, String> pending = new IdentityHashMap<>();
    List<PartnerResult> successes = new ArrayList<>();
    Map<String, String> failures = new LinkedHashMap<>();

    int completed = 0;
    boolean deadlineExceeded = false;

    try {
        for (String partner : partners) {
            Callable<PartnerResult> task = withContext(() ->
                    callPartner(partner, client, partnerLimit, deadlineNanos));

            Future<PartnerResult> future = completion.submit(task);
            pending.put(future, partner);
        }

        while (completed < partners.size()) {
            long remaining = remainingNanos(deadlineNanos);
            if (remaining == 0) {
                deadlineExceeded = true;
                break;
            }

            Future<PartnerResult> future = completion.poll(
                    remaining, TimeUnit.NANOSECONDS);

            if (future == null) {
                deadlineExceeded = true;
                break;
            }

            completed++;
            String partner = pending.remove(future);

            try {
                successes.add(future.get());
            } catch (ExecutionException failure) {
                Throwable cause = failure.getCause();
                String type = cause == null
                        ? "ExecutionException"
                        : cause.getClass().getSimpleName();
                failures.put(partner, type);
            } catch (CancellationException cancelled) {
                failures.put(partner, "Cancelled");
            }
        }
    } catch (InterruptedException interrupted) {
        pending.keySet().forEach(future -> future.cancel(true));
        throw interrupted;
    } catch (RuntimeException | Error failure) {
        pending.keySet().forEach(future -> future.cancel(true));
        throw failure;
    }

    if (deadlineExceeded) {
        pending.forEach((future, partner) -> {
            future.cancel(true);
            failures.put(partner, "Request deadline exceeded");
        });
    }

    return new AggregateResponse(successes, failures, deadlineExceeded);
}
```

Các điểm cần chú ý:

- `poll(remaining, NANOSECONDS)` chờ tối đa phần deadline còn lại.
- `future.get()` được gọi sau khi Future đã xuất hiện trong completion queue nên không phải chờ một task chưa hoàn tất.
- `ExecutionException` biểu thị task thất bại; lưu loại exception thay vì đưa nguyên message có thể chứa dữ liệu nhạy cảm vào response.
- Khi deadline hết, `cancel(true)` gửi interrupt tới task chưa hoàn tất.
- Khi thread điều phối bị interrupt, hủy các task còn lại rồi truyền `InterruptedException` lên caller.

Trong hệ thống thực tế, nên giới hạn số partner đầu vào và xác thực danh sách trước khi submit. Semaphore giới hạn số task giữ permit gọi downstream, nhưng bản thân nó không giới hạn số Future được tạo hoặc kích thước danh sách chờ.

## 10. Đặt context cho request và khôi phục sau khi xử lý

Handler đặt context trên thread đang xử lý request, gọi fan-out rồi khôi phục giá trị trước đó trong `finally`:

```java
private static AggregateResponse handleRequest(
        ExecutorService executor,
        Semaphore partnerLimit,
        PartnerClient client,
        RequestContext context,
        List<String> partners,
        Duration timeout
) throws InterruptedException {

    long deadlineNanos = deadlineAfter(timeout);
    RequestContext previous = CURRENT_CONTEXT.get();
    CURRENT_CONTEXT.set(context);

    try {
        return fanOut(
                executor,
                partnerLimit,
                client,
                partners,
                deadlineNanos
        );
    } finally {
        if (previous == null) {
            CURRENT_CONTEXT.remove();
        } else {
            CURRENT_CONTEXT.set(previous);
        }
    }
}
```

Không xóa ThreadLocal của worker từ thread điều phối. `ThreadLocal.remove()` chỉ tác động tới thread đang gọi nó. Mỗi task phải tự restore hoặc remove context trong wrapper của task.

## 11. Ghép các phần thành chương trình chạy được

Đặt các import và định nghĩa ở các mục trước trong cùng file `RequestOrchestratorLab.java`, cùng với class chứa `main`:

```java
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public final class RequestOrchestratorLab {
    private static final ThreadLocal<RequestContext> CURRENT_CONTEXT =
            new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        SimulatedPartnerClient client = new SimulatedPartnerClient(Map.of(
                "catalog", Duration.ofMillis(100),
                "pricing", Duration.ofMillis(250),
                "inventory", Duration.ofSeconds(3)
        ));

        Semaphore partnerLimit = new Semaphore(2, true);
        List<String> partners = List.of("catalog", "pricing", "inventory");

        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            // Hai request chạy đồng thời nhưng chia sẻ cùng một semaphore.
            Future<AggregateResponse> requestA = executor.submit(() -> handleRequestAndCheckContext(
                    executor,
                    partnerLimit,
                    client,
                    new RequestContext("trace-7f31", "tenant-a"),
                    partners,
                    Duration.ofMillis(700)
            ));

            Future<AggregateResponse> requestB = executor.submit(() -> handleRequestAndCheckContext(
                    executor,
                    partnerLimit,
                    client,
                    new RequestContext("trace-9c42", "tenant-b"),
                    partners,
                    Duration.ofMillis(700)
            ));

            AggregateResponse responseA = requestA.get(3, TimeUnit.SECONDS);
            AggregateResponse responseB = requestB.get(3, TimeUnit.SECONDS);

            verifyTenant(responseA, "tenant-a");
            verifyTenant(responseB, "tenant-b");

            System.out.println("Request A successes: " + responseA.successes().size());
            System.out.println("Request A failures: " + responseA.failures());
            System.out.println("Request B successes: " + responseB.successes().size());
            System.out.println("Request B failures: " + responseB.failures());
            System.out.println("Max concurrent downstream calls: "
                    + client.maxConcurrentCalls());

            // Mô phỏng request bên ngoài bị hủy trong khi task con còn chạy.
            Future<AggregateResponse> request = executor.submit(() -> handleRequest(
                    executor,
                    partnerLimit,
                    client,
                    new RequestContext("trace-cancel", "tenant-demo"),
                    partners,
                    Duration.ofSeconds(10)
            ));

            TimeUnit.MILLISECONDS.sleep(150);
            System.out.println("Cancellation requested: " + request.cancel(true));
        }

        // Executor đã đóng và chờ task kết thúc; mọi permit phải được trả.
        if (partnerLimit.availablePermits() != 2) {
            throw new IllegalStateException("A downstream permit was not released");
        }

        if (client.maxConcurrentCalls() > 2) {
            throw new IllegalStateException("Semaphore concurrency limit was exceeded");
        }

    }

    private static AggregateResponse handleRequestAndCheckContext(
            ExecutorService executor,
            Semaphore partnerLimit,
            PartnerClient client,
            RequestContext context,
            List<String> partners,
            Duration timeout
    ) throws InterruptedException {
        AggregateResponse response = handleRequest(
                executor, partnerLimit, client, context, partners, timeout);

        if (CURRENT_CONTEXT.get() != null) {
            throw new IllegalStateException("Request context leaked on handler thread");
        }
        return response;
    }

    private static void verifyTenant(AggregateResponse response, String expectedTenant) {
        for (PartnerResult result : response.successes()) {
            if (!result.value().endsWith("-for-" + expectedTenant)) {
                throw new IllegalStateException("Context crossed request boundary");
            }
        }
    }

    // Đặt các record, interface và method của những mục trước vào đây:
    // RequestContext, PartnerResult, AggregateResponse, PartnerClient,
    // SimulatedPartnerClient, deadlineAfter, remainingNanos, withContext,
    // callPartner, fanOut, handleRequest và handleRequestAndCheckContext.
}
```

Để chạy, đặt các định nghĩa `record`, interface và method ở các mục trước vào class `RequestOrchestratorLab` như nested type/method, rồi biên dịch bằng JDK 21:

```bash
javac --release 21 RequestOrchestratorLab.java
java RequestOrchestratorLab
```

Các imports của mục HttpClient ở phần sau cần được chuyển lên đầu file nếu bạn thay implementation giả lập bằng HTTP thật.

Output cụ thể thay đổi theo lịch chạy thread và môi trường. Các đối tác có latency ngắn thường hoàn tất trước; inventory có latency dài có thể timeout hoặc bị hủy khi deadline hết. Số lời gọi downstream đồng thời trên JVM không vượt quá 2. Sau khi executor đóng, số permit phải trở về 2 và context trên từng handler thread được khôi phục.

## 12. Thay client giả lập bằng HttpClient

Khi chuyển sang HTTP thật, dùng một `HttpClient` dùng chung và đặt timeout cho từng request bằng phần thời gian còn lại:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

static String fetchHttp(
        HttpClient client,
        URI uri,
        RequestContext context,
        Duration remaining
) throws IOException, InterruptedException {

    HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(remaining)
            .header("X-Correlation-Id", context.traceId())
            .GET()
            .build();

    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
    );

    if (response.statusCode() < 200 || response.statusCode() >= 300) {
        throw new IOException("Downstream returned HTTP " + response.statusCode());
    }

    return response.body();
}
```

Khởi tạo client dùng chung:

```java
HttpClient httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(250))
        .build();
```

`HttpRequest.timeout` giới hạn thời gian cho request HTTP; `connectTimeout` giới hạn thời gian thiết lập kết nối. Deadline ở tầng orchestrator vẫn cần thiết vì nó còn bao gồm thời gian chờ semaphore và thời gian chờ các task khác. Không đặt lại timeout đầy đủ cho từng downstream sau khi đã tiêu thụ một phần ngân sách request.

Trong code thực tế, map partner name sang URI từ cấu hình tin cậy, giới hạn response body, xác thực TLS, xử lý status/retry theo chính sách và không đưa token vào `RequestContext`. Nếu cần credential, lấy từ credential provider tại thời điểm gọi và chỉ truyền vào client trong phạm vi cần thiết.

## 13. Kiểm thử các tình huống quan trọng

| Tình huống | Cách tạo | Kết quả cần xác minh |
|---|---|---|
| Tất cả đối tác phản hồi nhanh | Mọi latency thấp hơn deadline | Có đủ kết quả, `deadlineExceeded` là false |
| Một đối tác chậm | Một latency lớn hơn ngân sách còn lại | Kết quả nhanh vẫn được giữ; task chậm timeout/cancel |
| Semaphore hết permit | Nhiều request cùng gọi với giới hạn nhỏ | Task chờ permit chỉ chờ đến deadline; không có acquire vô hạn |
| Request bị interrupt | Hủy Future của handler bằng `cancel(true)` | Handler hủy task con và truyền `InterruptedException` |
| Downstream ném exception | Client giả lập ném `IOException` | Failure được ghi nhận; permit vẫn được trả |
| Task bị interrupt khi đang I/O | Client dùng thao tác chờ có thể interrupt | Task thoát qua `finally`; permit và context được cleanup |
| Hai request liên tiếp | Dùng cùng executor và semaphore | Context request trước không xuất hiện trong task request sau |
| Nhiều request đồng thời | Gửi nhiều handler cùng lúc | Tổng downstream call đang hoạt động vẫn không vượt giới hạn semaphore |

Đối với test cancellation, không chỉ kiểm tra `Future.cancel(true)` trả về `true`. Giá trị đó cho biết yêu cầu hủy được chấp nhận, không chứng minh task con đã kết thúc ngay. Hãy chờ tín hiệu cleanup hoặc đợi executor kết thúc rồi kiểm tra permit và active-call counter.

Trong server framework, client disconnect không phải lúc nào cũng tự động interrupt thread đang xử lý request. Cần nối callback/cancellation signal của framework với cơ chế hủy task con; ví dụ này mô phỏng trường hợp handler bị interrupt. Không tự suy luận rằng mọi HTTP server đều interrupt request thread khi socket phía client đóng.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Tạo một semaphore mới cho từng request | Tổng tải downstream vẫn không bị giới hạn | Dùng semaphore dùng chung theo service/client |
| Dùng `Semaphore.acquire()` vô hạn | Request có thể chờ quá deadline | Dùng `tryAcquire(remaining, NANOSECONDS)` |
| Đặt timeout đầy đủ cho từng lời gọi | Tổng request có thể vượt ngân sách | Tính một deadline và truyền remaining time |
| Dùng `currentTimeMillis()` để đo elapsed time | Đồng hồ hệ thống có thể nhảy | Dùng `System.nanoTime()` |
| Thu Future theo thứ tự submit | Task chậm đầu danh sách chặn việc lấy kết quả nhanh | Dùng `ExecutorCompletionService` |
| Không gọi `cancel(true)` khi deadline hết | Task không cần thiết vẫn tiếp tục giữ tài nguyên | Hủy Future còn pending |
| Cho rằng cancel đồng nghĩa task đã dừng | I/O không phản ứng với interrupt có thể vẫn chạy | Dùng API có timeout/cancellation và kiểm tra cleanup |
| Không release permit trong `finally` | Semaphore dần cạn permit | Release đúng một lần sau khi acquire thành công |
| Truyền toàn bộ ThreadLocal hoặc token | Context có thể rò rỉ dữ liệu nhạy cảm | Capture allowlist context bất biến |
| Xóa ThreadLocal worker từ request thread | Không xóa được giá trị gắn với worker | Mỗi task tự restore/remove trong `finally` |
| Tạo quá nhiều Future mà không giới hạn input | Semaphore giới hạn I/O nhưng backlog vẫn tăng | Giới hạn số partner/request hoặc thêm admission control |

## 15. Nguyên tắc áp dụng vào service thật

- Một deadline monotonic cho toàn bộ request; mỗi lần chờ hoặc gọi I/O dùng thời gian còn lại.
- Semaphore dùng chung để bảo vệ tài nguyên downstream; chọn permit count theo quota và capacity đã đo.
- Virtual thread phù hợp với nhiều task chờ I/O; semaphore và deadline mới là cơ chế giới hạn tải.
- `CompletionService` hỗ trợ fan-in theo thứ tự hoàn thành và xử lý kết quả từng phần.
- Cancellation phải đi đến task con; task và API I/O cần phản ứng với interrupt hoặc timeout.
- Context chỉ chứa thông tin cần thiết, không chứa credential; truyền snapshot tường minh và cleanup trong `finally`.
- `ExecutorService` nên được quản lý ở vòng đời ứng dụng; không tạo/đóng executor toàn cục trong mỗi request.
- Theo dõi timeout, cancellation, thời gian chờ permit, số permit đang dùng, downstream latency và số task còn hoạt động.

## Tài liệu tham khảo chính thức

- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 21 API — ExecutorCompletionService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html)
- [Java SE 21 API — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 21 API — Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 21 API — ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java SE 21 API — HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 21 API — HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html#timeout(java.time.Duration))
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
