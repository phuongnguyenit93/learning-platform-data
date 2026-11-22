# Rate limit, bulkhead và giới hạn gọi dịch vụ bên ngoài

Khi ứng dụng Java 21 gọi database, HTTP API hoặc một dịch vụ bên ngoài, cần kiểm soát hai đại lượng khác nhau: **tốc độ bắt đầu request** và **số request đang chạy cùng lúc**. Rate limit kiểm soát tốc độ; bulkhead giới hạn tài nguyên hoặc số công việc đồng thời để một downstream chậm không làm cạn toàn bộ hệ thống.

Hai cơ chế bổ sung cho nhau. Một rate limit có thể cho phép 100 request mỗi giây nhưng nếu mỗi request mất vài giây, số request đang in-flight vẫn có thể tăng cao. Ngược lại, một semaphore chỉ cho phép 20 request đồng thời nhưng không giới hạn tốc độ nếu request hoàn tất rất nhanh. Khi tích hợp dịch vụ bên ngoài, thường cần cả rate limit, concurrency limit, timeout, giới hạn hàng đợi và chính sách retry phù hợp.

## 1. Phân biệt rate limit và concurrency limit

**Rate limit** giới hạn số lần gọi được chấp nhận trong một khoảng thời gian, ví dụ 50 request/giây hoặc 2.000 request/phút cho một API key. Mục tiêu thường là tuân thủ quota của nhà cung cấp, bảo vệ dịch vụ khỏi burst quá lớn hoặc phân phối công bằng tài nguyên giữa tenant.

**Concurrency limit** giới hạn số lời gọi đang thực hiện tại cùng thời điểm. Ví dụ chỉ cho phép tối đa 20 truy vấn đồng thời đến database hoặc tối đa 8 request đang chờ phản hồi từ một dịch vụ đối tác.

| Cơ chế | Giới hạn | Câu hỏi trả lời | Ví dụ |
|---|---|---|---|
| Rate limit | Số lần bắt đầu trong thời gian | Trong một giây/phút được gọi bao nhiêu lần? | Tối đa 100 request/giây/API key |
| Concurrency limit | Số tác vụ đang in-flight | Cùng lúc được có bao nhiêu lời gọi? | Tối đa 20 request đang chạy |
| Bulkhead | Mức tài nguyên dành riêng cho một nhóm công việc | Một downstream lỗi/chậm có thể chiếm bao nhiêu tài nguyên? | Pool 8 worker và queue 100 task cho dịch vụ X |
| Queue limit | Số công việc được phép chờ | Khi hết worker, được giữ lại bao nhiêu task? | Tối đa 100 task chờ trước khi từ chối |

Rate limit không thay thế bulkhead và ngược lại. Một request rate thấp vẫn có thể giữ kết nối lâu; một concurrency limit cao vẫn có thể cho phép burst request quá lớn.

## 2. Vì sao cần giới hạn khi gọi dịch vụ bên ngoài?

Giả sử ứng dụng có nhiều virtual threads và mỗi request đều gọi cùng một dịch vụ thanh toán. Nếu dịch vụ đó chỉ xử lý ổn định 30 request đồng thời, việc để hàng nghìn tác vụ cùng gọi sẽ tạo queue, timeout và retry dây chuyền.

Các rủi ro thường gặp:

- **Quota bị vượt:** nhà cung cấp giới hạn request/giây hoặc request/ngày; ứng dụng gửi quá nhiều sẽ nhận lỗi 429 hoặc bị khóa quota.
- **Downstream quá tải:** request đến nhanh hơn khả năng xử lý, khiến latency và số request in-flight tăng.
- **Cạn tài nguyên cục bộ:** connection pool, worker thread, file descriptor hoặc bộ nhớ bị chiếm bởi các lời gọi đang chờ.
- **Lỗi lan truyền:** một dịch vụ chậm làm giữ request của ứng dụng, khiến các endpoint khác cũng thiếu tài nguyên.
- **Retry storm:** nhiều request timeout cùng retry, làm downstream đang quá tải nhận thêm request.

Rate limit và bulkhead tạo ranh giới bảo vệ quanh từng dependency. Mỗi dịch vụ có thể có quota và giới hạn concurrency riêng, phù hợp với năng lực cũng như hợp đồng của nhà cung cấp.

## 3. Rate limiting với token bucket

Một thuật toán phổ biến là **token bucket**. Bucket có dung lượng tối đa và được bổ sung token theo tốc độ cố định. Mỗi request cần lấy một token trước khi được phép gọi:

- Bucket có capacity 10: có thể cho phép một burst tối đa 10 request khi bucket đầy.
- Tốc độ refill 5 token/giây: sau burst, trung bình có thêm 5 quyền gọi mỗi giây.
- Nếu không còn token, request bị từ chối hoặc phải chờ theo chính sách ứng dụng.

Token bucket cho phép burst ngắn nhưng kiểm soát tốc độ trung bình. Đây là điểm khác với fixed window đơn giản, nơi request có thể dồn vào hai phía ranh giới cửa sổ và tạo burst lớn.

Ví dụ minh họa rate limiter trong một JVM:

```java
final class TokenBucketRateLimiter {
    private final double capacity;
    private final double tokensPerNano;

    private double tokens;
    private long lastRefillNanos;

    TokenBucketRateLimiter(int capacity, double refillPerSecond) {
        if (capacity <= 0 || !Double.isFinite(refillPerSecond)
                || refillPerSecond <= 0) {
            throw new IllegalArgumentException("Invalid rate limit configuration");
        }

        this.capacity = capacity;
        this.tokensPerNano = refillPerSecond / 1_000_000_000.0;
        this.tokens = capacity;
        this.lastRefillNanos = System.nanoTime();
    }

    synchronized boolean tryAcquire() {
        long now = System.nanoTime();
        long elapsed = now - lastRefillNanos;

        if (elapsed > 0) {
            tokens = Math.min(capacity, tokens + elapsed * tokensPerNano);
            lastRefillNanos = now;
        }

        if (tokens < 1.0) {
            return false;
        }

        tokens -= 1.0;
        return true;
    }
}
```

Sử dụng:

```java
TokenBucketRateLimiter limiter = new TokenBucketRateLimiter(10, 5.0);

if (!limiter.tryAcquire()) {
    throw new RateLimitExceededException("Request rate exceeded");
}

callExternalService();
```

Ví dụ trên dùng `synchronized` để bảo vệ trạng thái bucket trong một JVM. `System.nanoTime()` phù hợp để đo thời gian trôi qua vì không bị ảnh hưởng bởi việc chỉnh đồng hồ hệ thống. Đây là code minh họa thuật toán; hệ thống production thường nên dùng thư viện rate limiter đã được kiểm thử hoặc API của gateway, đặc biệt khi cần nhiều bucket, quota động, metric và phân phối trên nhiều instance.

## 4. Các thuật toán rate limit thường gặp

| Thuật toán | Cách hoạt động | Ưu điểm | Điểm cần lưu ý |
|---|---|---|---|
| Fixed window counter | Đếm request trong từng cửa sổ thời gian cố định | Đơn giản, ít bộ nhớ | Có thể tạo burst ở ranh giới hai cửa sổ |
| Sliding window log | Lưu timestamp request và loại timestamp đã hết hạn | Kiểm soát chính xác theo cửa sổ trượt | Tốn bộ nhớ khi request nhiều |
| Sliding window counter | Kết hợp counter cửa sổ hiện tại và cửa sổ trước | Nhẹ hơn log, giảm burst ở ranh giới | Là phép xấp xỉ theo trọng số |
| Token bucket | Token được refill theo thời gian, request tiêu thụ token | Cho phép burst có giới hạn và kiểm soát tốc độ trung bình | Cần chọn capacity và refill rate phù hợp |
| Leaky bucket | Xử lý request theo tốc độ thoát ổn định, thường qua queue | Làm mượt tốc độ gửi ra | Queue cần giới hạn; phải định nghĩa hành vi khi đầy |

Không có thuật toán tốt nhất cho mọi trường hợp. Nếu nhà cung cấp cho phép burst ngắn nhưng giới hạn tốc độ trung bình, token bucket thường dễ mô hình hóa. Nếu cần nhịp xử lý đầu ra ổn định, có thể cân nhắc leaky bucket hoặc queue có scheduler.

## 5. Bulkhead với Semaphore

Bulkhead pattern lấy ý tưởng từ các khoang kín trên tàu: sự cố ở một khoang không làm toàn bộ tàu chìm. Trong ứng dụng, mỗi dependency hoặc nhóm công việc có thể có giới hạn concurrency riêng để một downstream chậm không chiếm hết tài nguyên phục vụ các dependency khác.

`Semaphore` là cách đơn giản để giới hạn số lời gọi đang chạy:

```java
import java.util.concurrent.Semaphore;

final class PaymentClient {
    private final Semaphore permits = new Semaphore(20);

    PaymentResult charge(PaymentRequest request) {
        if (!permits.tryAcquire()) {
            throw new BulkheadFullException("Payment service is busy");
        }

        try {
            return callPaymentProvider(request);
        } finally {
            permits.release();
        }
    }

    private PaymentResult callPaymentProvider(PaymentRequest request) {
        // Gọi HTTP API đồng bộ hoặc SDK blocking.
        return new PaymentResult();
    }
}
```

`tryAcquire()` từ chối ngay khi hết permit, phù hợp với fail-fast. `finally` bảo đảm permit được trả lại cả khi lời gọi thành công hoặc ném exception. Nếu quên release, số permit giảm dần và bulkhead có thể bị khóa vĩnh viễn.

Nếu muốn chờ một khoảng thời gian để lấy permit, dùng `tryAcquire(timeout, unit)`. Chỉ chờ theo cách này trên worker thread hoặc virtual thread, không chặn event-loop. Khi chờ hết thời gian, xử lý như quá tải hoặc timeout theo hợp đồng API.

Semaphore giới hạn số lời gọi đang giữ permit, không giới hạn tốc độ bắt đầu. Nếu lời gọi hoàn tất rất nhanh, ứng dụng vẫn có thể gửi hàng nghìn request mỗi giây qua 20 permit.

## 6. Bulkhead bằng executor và queue hữu hạn

Một kiểu bulkhead khác là dành executor riêng cho một dependency. Thread pool giới hạn số tác vụ đang chạy; bounded queue giới hạn số tác vụ chờ:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadFactory factory = Thread.ofPlatform()
        .name("partner-api-", 0)
        .factory();

ThreadPoolExecutor partnerExecutor = new ThreadPoolExecutor(
        8,
        8,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(100),
        factory,
        new ThreadPoolExecutor.AbortPolicy());
```

Với cấu hình này, tối đa 8 task chạy trên executor và tối đa 100 task chờ trong queue. Khi pool và queue đều đầy, `execute`/`submit` từ chối tác vụ bằng `RejectedExecutionException`.

Không dùng `CallerRunsPolicy` nếu executor có thể được submit từ event-loop: khi quá tải, policy đó có thể chạy công việc blocking ngay trên thread gọi và chặn event-loop. Queue không giới hạn cũng không phải bulkhead hữu hiệu vì số task chờ và bộ nhớ có thể tăng mãi.

Executor chuyên biệt phù hợp khi cần cô lập cả worker thread và queue. Semaphore phù hợp khi đã có executor hoặc virtual threads và chỉ cần giới hạn số lời gọi đồng thời đến dependency.

## 7. Kết hợp rate limit và bulkhead

Khi gọi một dịch vụ ngoài, thường cần cả hai cơ chế. Ví dụ sau chỉ thực hiện lời gọi nếu còn concurrency permit và còn token rate limit:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.Semaphore;

final class DownstreamGuard {
    private final Semaphore inFlight = new Semaphore(20);
    private final TokenBucketRateLimiter rateLimiter =
            new TokenBucketRateLimiter(10, 5.0);

    <T> T call(Callable<T> operation) throws Exception {
        if (!inFlight.tryAcquire()) {
            throw new BulkheadFullException("Too many concurrent calls");
        }

        try {
            if (!rateLimiter.tryAcquire()) {
                throw new RateLimitExceededException("Call rate exceeded");
            }

            return operation.call();
        } finally {
            inFlight.release();
        }
    }
}
```

Trong ví dụ, permit concurrency được lấy trước và luôn được trả trong `finally`. Nếu bucket hết token, lời gọi không được thực hiện và semaphore permit được trả ngay. Một token chỉ bị tiêu thụ khi request vượt qua cả hai điều kiện và chuẩn bị gọi downstream.

`TokenBucketRateLimiter`, `BulkheadFullException` và `RateLimitExceededException` là các lớp ví dụ đã mô tả hoặc cần định nghĩa trong ứng dụng. `operation.call()` có thể blocking, vì vậy chỉ gọi `DownstreamGuard.call(...)` trên worker/virtual thread phù hợp, không gọi trực tiếp trên event-loop.

## 8. Sử dụng với Virtual Threads trong Java 21

Virtual threads giúp tạo một virtual thread cho mỗi task mà không cần tạo một platform thread cho mỗi lần chờ. Tuy nhiên, chúng không làm quota hoặc khả năng xử lý của downstream tăng lên.

Ví dụ, ứng dụng có thể chạy mỗi request trên virtual thread nhưng vẫn giới hạn số lời gọi thanh toán đồng thời bằng semaphore:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

ExecutorService requestExecutor = Executors.newVirtualThreadPerTaskExecutor();

Future<PaymentResult> future = requestExecutor.submit(() ->
        paymentClient.charge(request));
```

Trong ví dụ, `paymentClient.charge(...)` cần áp dụng bulkhead và rate limiter như các phần trước. Executor virtual-thread nên được quản lý theo vòng đời ứng dụng và đóng khi ứng dụng dừng, không tạo rồi đóng lại cho từng request.

Nếu dùng `Semaphore.acquire()` để đợi permit trong virtual thread, thao tác chờ có thể unmount virtual thread khỏi carrier trong trường hợp JVM hỗ trợ. Nhưng không dùng blocking acquire trên event-loop. Nếu không muốn giữ request chờ, dùng `tryAcquire()` để từ chối sớm và trả phản hồi quá tải.

Không tạo một thread pool virtual threads với số thread cố định để giới hạn downstream; mô hình thông dụng là virtual thread-per-task kết hợp semaphore hoặc giới hạn tại connection pool/API client. Số virtual threads có thể lớn, còn tài nguyên bên ngoài vẫn cần giới hạn riêng.

## 9. Giới hạn theo từng tenant, API key hoặc endpoint

Rate limit có thể áp dụng ở nhiều phạm vi:

- **Global:** giới hạn tổng số request của cả ứng dụng tới một dịch vụ.
- **Per tenant/API key:** mỗi khách hàng hoặc khóa API có quota riêng.
- **Per user/IP:** giới hạn theo người dùng hoặc địa chỉ nguồn, khi định danh đó đáng tin cậy.
- **Per endpoint/operation:** thao tác đắt như tạo báo cáo hoặc gửi thanh toán có quota thấp hơn thao tác đọc thông thường.

Không nên dùng một bucket duy nhất cho mọi tenant nếu hợp đồng yêu cầu công bằng giữa khách hàng. Ngược lại, tạo bucket không giới hạn theo một key do client tự khai có thể gây tăng bộ nhớ vì client tạo vô số key khác nhau. Cần xác thực danh tính, giới hạn cardinality, chính sách hết hạn và dọn dẹp bucket không còn hoạt động.

Nếu ứng dụng chạy nhiều instance, rate limiter lưu trong bộ nhớ từng JVM chỉ giới hạn cục bộ. Ví dụ 5 instance, mỗi instance cho 100 request/giây, có thể cho phép tổng cộng gần 500 request/giây. Nếu quota là global, cần một bộ điều phối dùng chung như API gateway hoặc kho dữ liệu hỗ trợ cập nhật nguyên tử; không chỉ nhân bản cùng một cấu hình local trên mỗi node.

## 10. Xử lý khi bị rate limit hoặc bulkhead từ chối

Hành vi từ chối cần rõ ràng và có thể quan sát:

- Với API nhận request từ client, vượt quota thường được ánh xạ thành HTTP `429 Too Many Requests`; có thể trả `Retry-After` nếu biết thời điểm phù hợp để thử lại.
- Nếu dịch vụ không thể tiếp nhận vì đang quá tải hoặc bulkhead đầy, HTTP `503 Service Unavailable` thường phù hợp hơn.
- Với lời gọi nội bộ, có thể ném exception nghiệp vụ riêng để tầng gọi quyết định fallback, queue lại hoặc trả lỗi.
- Không âm thầm bỏ request nếu hợp đồng yêu cầu kết quả; nếu có cơ chế drop, phải thể hiện rõ trong giao thức và metric.

Không retry ngay lập tức khi nhận 429 hoặc 503. Retry nên có exponential backoff, jitter, số lần tối đa và tổng deadline. Tôn trọng `Retry-After` khi nhà cung cấp trả về. Với thao tác có side effect như thanh toán hoặc tạo đơn hàng, cần idempotency key hoặc cơ chế chống thực thi trùng trước khi retry.

## 11. Timeout, permit và vòng đời lời gọi

Timeout của request và giới hạn concurrency phải được phối hợp. Khi đã lấy semaphore permit, cần giữ permit cho đến khi lời gọi downstream thực sự kết thúc hoặc được xác nhận đã hủy. Không trả permit ngay khi caller timeout nếu công việc nền vẫn đang chạy; nếu làm vậy, ứng dụng có thể khởi chạy thêm lời gọi trong khi các lời gọi cũ vẫn chiếm downstream, khiến giới hạn thực tế bị vượt.

Đặt timeout ở HTTP client, JDBC driver hoặc SDK thực hiện I/O. `Future.get(timeout, unit)` chỉ giới hạn thời gian caller chờ; nó không tự bảo đảm request bên ngoài đã dừng. Cancellation có thể chỉ là yêu cầu hợp tác, tùy API.

Khi retry, không giữ permit trong thời gian backoff. Trả permit sau khi một attempt kết thúc, chờ theo chính sách retry bên ngoài vùng giữ permit, rồi lấy permit và token mới cho attempt tiếp theo. Mỗi attempt thực sự gửi tới downstream thường phải tiêu thụ quota rate limit.

## 12. Chọn giới hạn dựa trên latency và throughput

Little's Law giúp ước lượng số request trung bình đang in-flight trong điều kiện ổn định:

\[
N = \lambda \times W
\]

Trong đó `N` là số request trung bình trong hệ thống, `λ` là throughput (request/giây) và `W` là latency trung bình (giây). Ví dụ, downstream hoàn tất 40 request/giây với latency trung bình 0,5 giây thì số request trung bình đang in-flight xấp xỉ:

\[
N = 40 \times 0.5 = 20
\]

Con số 20 là ước lượng trung bình, không phải giới hạn concurrency an toàn mặc định. Cần tính thêm burst, p95/p99 latency, giới hạn connection, timeout, headroom và khả năng phục hồi của downstream. Bắt đầu với giới hạn thận trọng rồi load test và điều chỉnh theo số liệu thực tế.

## 13. Metrics cần theo dõi

Để biết giới hạn có hoạt động đúng hay đang quá chặt, theo dõi:

- Số request được rate limiter cho phép và từ chối theo từng phạm vi quota.
- Token bucket còn bao nhiêu token hoặc thời gian chờ dự kiến nếu thư viện cung cấp metric.
- Số lời gọi đang in-flight và số semaphore permit còn lại.
- Số task đang chạy, queue depth và số lần executor reject.
- Latency downstream p50/p95/p99, throughput, timeout và error rate.
- Số lần retry, tổng thời gian backoff và kết quả sau retry.
- Mức sử dụng connection pool, CPU, heap và số kết nối mạng.

Tránh gắn nhãn metric bằng giá trị tenant hoặc API key có cardinality rất cao nếu hệ thống giám sát không được thiết kế cho điều đó. Có thể tổng hợp theo nhóm tenant, endpoint hoặc quota tier và lưu định danh chi tiết trong log/tracing có kiểm soát.

## 14. Lỗi thường gặp và cách xử lý

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ dùng rate limit, không giới hạn in-flight | Request chậm tích tụ và giữ tài nguyên | Thêm semaphore hoặc bulkhead riêng cho dependency |
| Chỉ dùng semaphore, không rate limit | Burst nhanh vẫn có thể vượt quota nhà cung cấp | Thêm rate limiter theo quota |
| Quên `release()` semaphore | Permit bị mất sau lỗi và bulkhead dần khóa | Đặt release trong `finally` sau khi acquire thành công |
| Dùng queue không giới hạn | Queue, bộ nhớ và latency tăng khi downstream chậm | Dùng bounded queue và từ chối tải có kiểm soát |
| Dùng `CallerRunsPolicy` từ event-loop | Blocking task có thể chạy trên event-loop | Dùng rejection policy không chạy task trên caller |
| Chỉ rate limit trong từng JVM nhưng quota là global | Tổng lưu lượng nhiều instance vượt quota | Dùng gateway hoặc bộ điều phối phân tán có cập nhật nguyên tử |
| Retry ngay sau 429/503 | Tạo thêm tải trong lúc dịch vụ quá tải | Backoff, jitter, retry budget và tôn trọng `Retry-After` |
| Trả permit khi caller timeout nhưng request vẫn chạy | Số lời gọi thực tế vượt concurrency limit | Giữ permit đến khi downstream operation kết thúc/hủy thực sự |
| Dùng blocking acquire trên event-loop | Event-loop bị giữ trong lúc chờ permit | Dùng fail-fast hoặc chuyển việc chờ sang worker/virtual thread |
| Tạo quá nhiều bucket theo key tùy ý | Tăng bộ nhớ và cardinality | Xác thực key, giới hạn số bucket và dọn dẹp trạng thái |

## 15. Checklist khi tích hợp dịch vụ bên ngoài

- Xác định quota theo giây/phút/ngày và phạm vi áp dụng của nhà cung cấp.
- Đặt rate limit riêng cho global, tenant, API key hoặc endpoint theo hợp đồng.
- Đặt concurrency limit phù hợp với khả năng xử lý và connection pool của downstream.
- Dùng token bucket hoặc thuật toán khác phù hợp với burst và tốc độ trung bình cần kiểm soát.
- Dùng semaphore hoặc bulkhead executor để cô lập tài nguyên của từng dependency.
- Dùng bounded queue và chính sách từ chối rõ ràng; tránh `CallerRunsPolicy` trên event-loop.
- Đặt timeout ở API I/O và deadline tổng cho request.
- Chỉ trả permit khi lời gọi thực sự kết thúc hoặc được hủy; không để timeout caller làm sai số in-flight.
- Retry có backoff, jitter, giới hạn số lần và idempotency khi có side effect.
- Nếu chạy nhiều instance, xác định quota là local hay global và chọn cơ chế phối hợp phù hợp.
- Theo dõi rate, in-flight, queue, rejection, latency, timeout, retry và downstream error.
- Load test với burst và downstream chậm để xác nhận hệ thống từ chối tải có kiểm soát.

Rate limit kiểm soát tốc độ, bulkhead kiểm soát mức tài nguyên bị chiếm, còn concurrency limit giới hạn số lời gọi đang chạy. Kết hợp chúng với queue hữu hạn, timeout và retry có giới hạn giúp ứng dụng Java 21 bảo vệ dịch vụ bên ngoài và ngăn một dependency chậm làm ảnh hưởng toàn hệ thống.
