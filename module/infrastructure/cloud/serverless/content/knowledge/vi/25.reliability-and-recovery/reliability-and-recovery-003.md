# Retry với exponential backoff, jitter và giới hạn số lần

Trong serverless, một function có thể thất bại tạm thời vì network chập chờn, database quá tải, API đối tác trả 503 hoặc message broker chưa sẵn sàng. Retry giúp hoàn tất công việc khi lỗi có thể tự phục hồi. Tuy nhiên, retry không đúng cách có thể làm sự cố nặng hơn: nhiều function cùng gọi lại một dependency đang quá tải, tạo retry storm, nhân số request và làm cạn concurrency.

Một retry policy tốt phải trả lời bốn câu hỏi: **lỗi nào được retry, chờ bao lâu trước lần tiếp theo, thử tối đa bao nhiêu lần và khi nào phải dừng**. Với Java serverless, policy còn phải tính đến deadline của invocation, giới hạn thời gian nền tảng, cơ chế retry của queue/event source và khả năng xử lý trùng. Nếu một lần gọi có thể đã tạo tác dụng phụ trước khi timeout, retry phải đi cùng idempotency.

Bài học trình bày cách phân loại lỗi, tính exponential backoff có jitter, đặt giới hạn attempts và elapsed time, triển khai retry trong Java, phối hợp với retry do nền tảng quản lý và vận hành DLQ/redrive.

## 1. Retry là gì và khi nào nên dùng?

Retry là việc thực hiện lại một thao tác sau khi lần trước thất bại. Mục đích là vượt qua lỗi tạm thời mà không yêu cầu người dùng hoặc hệ thống upstream phải tự gửi lại ngay.

Ví dụ phù hợp:

- HTTP request đến API đối tác gặp connection reset.
- Database tạm thời từ chối kết nối do failover.
- Queue consumer gặp lỗi 503 từ dependency.
- Object storage trả lỗi throttling.
- DNS lookup hoặc network route gặp lỗi thoáng qua.

Retry không sửa được lỗi logic hoặc dữ liệu không hợp lệ. Nếu request luôn thiếu trường bắt buộc, token luôn sai hoặc business rule từ chối thao tác, thử lại cùng dữ liệu thường chỉ tốn thời gian và chi phí.

### Retry có giới hạn

Một retry policy thường gồm:

- **Max attempts:** tổng số lần thực hiện, bao gồm lần đầu.
- **Initial delay:** khoảng chờ ban đầu trước lần retry đầu tiên.
- **Backoff multiplier:** hệ số tăng thời gian chờ, thường là 2.
- **Maximum delay:** mức chờ tối đa.
- **Maximum elapsed time:** ngân sách thời gian tối đa cho cửa sổ retry; timeout từng attempt và invocation deadline vẫn phải giới hạn thời gian thực thi.
- **Retryable classifier:** điều kiện xác định lỗi nào có thể retry.
- **Jitter:** độ ngẫu nhiên thêm vào delay để tránh nhiều client retry cùng lúc.

Không dùng retry vô hạn. Một dependency lỗi kéo dài có thể khiến function tiêu tốn concurrency, tiền compute và thời gian của người dùng mà không tạo ra kết quả.

## 2. Phân loại lỗi trước khi retry

Bước đầu tiên là phân loại lỗi theo khả năng phục hồi và ý nghĩa nghiệp vụ.

| Loại lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Lỗi mạng tạm thời | Connection reset, connect timeout, DNS timeout | Có thể retry có giới hạn |
| Lỗi quá tải | HTTP 429, 503, throttling | Backoff, jitter, tôn trọng Retry-After |
| Lỗi server tạm thời | HTTP 500, 502, 504 | Có thể retry nếu operation an toàn |
| Lỗi đầu vào | HTTP 400, schema không hợp lệ | Không retry |
| Lỗi xác thực/quyền | HTTP 401, 403 | Không retry cùng credential; sửa identity/config |
| Lỗi nghiệp vụ | Payment declined, trạng thái không hợp lệ | Thường không retry tự động |
| Không tìm thấy | HTTP 404 | Tùy contract; thường không retry nếu tài nguyên thực sự không tồn tại |
| Conflict | HTTP 409 | Chỉ retry khi contract chỉ ra conflict tạm thời |
| Timeout với kết quả chưa rõ | Client timeout sau khi server có thể đã commit | Chỉ retry với idempotency hoặc cơ chế tra cứu trạng thái |

### HTTP status không phải classifier hoàn chỉnh

Không phải mọi 5xx đều chắc chắn retry an toàn và không phải mọi 4xx đều là lỗi vĩnh viễn. Hãy đọc contract của dependency.

Ví dụ:

- 429 thường có nghĩa vượt rate limit; cần chờ theo Retry-After nếu có.
- 503 có thể là bảo trì hoặc quá tải tạm thời.
- 500 có thể do bug lặp lại, retry liên tục không giúp ích.
- 409 có thể là optimistic-lock conflict có thể thử lại sau khi đọc trạng thái mới, hoặc là duplicate request không nên lặp.

Classifier nên dựa trên loại exception, status, error code của provider và trạng thái operation. Không dùng quy tắc chung kiểu “catch Exception rồi retry”.

## 3. Exponential backoff

Exponential backoff tăng thời gian chờ sau mỗi lần thất bại. Thay vì gọi lại liên tục sau một khoảng cố định, client giãn dần các lần retry để dependency có thời gian phục hồi.

Công thức delay trước lần retry thứ (n):

```text
delay(n) = min(maxDelay, initialDelay × multiplier^(n - 1))
```

Với multiplier bằng 2:

- Retry 1: 200 ms.
- Retry 2: 400 ms.
- Retry 3: 800 ms.
- Retry 4: 1.600 ms.
- Retry 5: 3.200 ms.

Nếu maxDelay là 2 giây, delay sẽ dừng tăng ở 2 giây.

### Ví dụ tính toán

Giả sử:

- initialDelay = 250 ms.
- multiplier = 2.
- maxDelay = 2.000 ms.
- maxAttempts = 5 (gồm lần đầu).

| Lần thực hiện | Thời điểm tương đối nếu không có jitter | Chờ trước lần tiếp theo |
|---|---:|---:|
| Attempt 1 | 0 ms | 250 ms |
| Attempt 2 | 250 ms | 500 ms |
| Attempt 3 | 750 ms | 1.000 ms |
| Attempt 4 | 1.750 ms | 2.000 ms |
| Attempt 5 | 3.750 ms | Dừng |

Tổng thời gian chờ tối đa trong ví dụ là 3.750 ms, chưa tính thời gian xử lý từng attempt. Đây là lý do cần tính cả thời gian thực thi, không chỉ cộng các delay.

## 4. Vì sao cần jitter?

Nếu hàng nghìn function cùng nhận 503 tại một thời điểm và đều dùng backoff cố định, chúng có thể retry đồng loạt sau 1 giây, rồi lại đồng loạt sau 2 giây. Khi dependency vừa phục hồi, lượng request dồn cục lại có thể làm nó quá tải lần nữa. Hiện tượng này gọi là thundering herd.

Jitter thêm yếu tố ngẫu nhiên vào delay để phân tán các lần retry.

### Full jitter

Một lựa chọn phổ biến là full jitter:

```text
cap(n) = min(maxDelay, initialDelay × 2^(n - 1))
actualDelay(n) = random(0, cap(n))
```

Ví dụ cap là 800 ms, mỗi client chọn delay ngẫu nhiên từ 0 đến 800 ms. Các client không còn cùng retry tại một thời điểm cố định.

### Một số chiến lược jitter

| Chiến lược | Cách tính | Đặc điểm |
|---|---|---|
| No jitter | Dùng toàn bộ exponential delay | Dễ tạo đợt retry đồng bộ |
| Full jitter | Random từ 0 đến cap | Phân tán tốt, delay trung bình thấp hơn cap |
| Equal jitter | cap/2 + random(0, cap/2) | Có một mức chờ tối thiểu |
| Decorrelated jitter | Delay mới ngẫu nhiên dựa trên delay trước và cap | Phân tán tốt với chuỗi retry dài |

Full jitter phù hợp làm mặc định cho nhiều workload phân tán. Nếu dependency cung cấp Retry-After, client nên tôn trọng thời điểm được yêu cầu thay vì bỏ qua để dùng delay ngắn hơn.

## 5. Giới hạn số lần và tổng thời gian

Max attempts và max elapsed time giải quyết hai rủi ro khác nhau:

- Max attempts ngăn một operation thử quá nhiều lần.
- Max elapsed time ngăn bắt đầu thêm lần retry khi đã tiêu tốn hết ngân sách thời gian, kể cả do attempt trước chậm hoặc backoff lớn.

Cần làm rõ cách đếm: **maxAttempts thường bao gồm lần gọi đầu tiên**. Nếu maxAttempts = 4 thì có tối đa một lần đầu và ba lần retry. Một số SDK dùng maxRetries, khi đó tổng attempts bằng 1 + maxRetries.

Ví dụ:

- maxAttempts = 4.
- initialDelay = 200 ms.
- maxDelay = 1 giây.
- maxElapsed = 5 giây.

Nếu attempt đầu đã mất 4,5 giây, không nên tiếp tục ngủ 1 giây rồi gọi lại khi invocation chỉ còn 0,5 giây. Hãy dừng và trả lỗi theo contract hoặc chuyển công việc sang queue để xử lý bất đồng bộ.

### Deadline phải bao gồm mọi chặng

Một request đồng bộ có thể có deadline tổng 8 giây. Trong đó có:

- Xác thực và xử lý đầu vào.
- Gọi database.
- Gọi API đối tác.
- Các lần retry và backoff.
- Tạo response.

Không được dùng hết deadline ở retry của một dependency rồi không còn thời gian trả response hoặc ghi nhận trạng thái. Hãy truyền deadline/remaining time vào từng tầng thay vì mỗi tầng tự đặt timeout độc lập.

Max elapsed trong retry helper là giới hạn cửa sổ retry; nó không thể tự ngắt một HTTP call đang treo hoặc hủy một operation đã thành công sau deadline. Cấu hình connect timeout, request timeout và read timeout theo khả năng thư viện, đồng thời truyền remaining deadline để không bắt đầu attempt mới khi không còn đủ thời gian. Không biến một kết quả thành công nhưng đến muộn thành lỗi retry tự động, vì side effect có thể đã xảy ra.

## 6. Retry đồng bộ và retry bất đồng bộ

Không phải mọi retry đều nên diễn ra trong cùng invocation.

| Kiểu | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Synchronous retry | Function chờ, rồi gọi lại dependency trong cùng invocation | Lỗi ngắn, số lần thử ít, còn đủ deadline |
| Platform-managed retry | Queue, event source hoặc workflow giao lại event sau lỗi | Công việc nền có thể chờ và cần retry bền vững |
| Scheduled retry | Ghi trạng thái retry và lên lịch lần thử tiếp theo | Cần delay dài, thời gian retry cụ thể hoặc workflow nhiều bước |
| Manual redrive | Đưa message từ DLQ trở lại luồng xử lý sau khi sửa nguyên nhân | Poison message hoặc sự cố cần can thiệp |

### Synchronous retry

Ưu điểm là đơn giản và có thể trả kết quả ngay. Nhược điểm là giữ invocation, thread/concurrency và có thể làm tăng chi phí trong thời gian chờ.

Chỉ dùng cho retry ngắn. Nếu phải chờ vài phút hoặc nhiều giờ, đừng giữ một function invocation mở để sleep; lưu operation state và chuyển sang cơ chế bất đồng bộ.

### Platform-managed retry

Với message/event, nền tảng thường có cơ chế retry khi handler thất bại hoặc không acknowledge. Cần hiểu chính xác điều kiện retry, số lần, visibility/ack deadline, retention và cách xử lý partial batch failure của trigger đang dùng.

Không cộng thêm một vòng retry dài bên trong consumer nếu event source đã có retry policy tương ứng mà không tính tổng attempts. Hai lớp retry có thể nhân số lần gọi.

## 7. Retry budget và retry amplification

Một request có thể đi qua nhiều lớp:

1. API gateway retry function.
2. Function retry service nội bộ.
3. Service nội bộ retry database.
4. HTTP client retry API đối tác.

Nếu mỗi lớp cho phép ba attempts, một thao tác có thể tạo tối đa (3^4 = 81) lần gọi ở dependency sâu nhất trong trường hợp xấu. Con số thực tế phụ thuộc cấu trúc, nhưng ví dụ cho thấy retry lồng nhau có thể khuếch đại tải rất nhanh.

### Nguyên tắc kiểm soát

- Chọn một lớp sở hữu retry chính cho từng dependency.
- Các lớp còn lại dùng timeout và trả lỗi rõ ràng.
- Giới hạn tổng attempts trên toàn operation, không chỉ từng client.
- Dùng retry budget theo service hoặc dependency.
- Dùng circuit breaker để tạm ngừng request khi dependency liên tục lỗi.
- Dùng rate limit và bulkhead để giới hạn tác động.
- Không retry một request đã bị caller retry ở tầng ngoài nếu không có idempotency.

Retry budget có thể là tỷ lệ request retry tối đa so với request ban đầu trong một cửa sổ. Khi budget cạn, hệ thống trả lỗi sớm hoặc đưa công việc vào queue thay vì tiếp tục tạo tải.

## 8. Idempotency: điều kiện quan trọng trước khi retry

Một operation idempotent có cùng kết quả cuối cùng khi được thực hiện một lần hoặc nhiều lần với cùng định danh yêu cầu.

Ví dụ:

- Đặt trạng thái đơn hàng thành PAID có thể idempotent nếu thao tác chỉ cập nhật đến cùng trạng thái và có kiểm tra transition.
- Tạo đơn hàng mới không tự động idempotent: retry có thể tạo hai order.
- Gửi email không tự động idempotent: retry có thể gửi hai email.
- Gọi API thanh toán có thể hỗ trợ idempotency key theo contract của provider.

### Vì sao timeout nguy hiểm?

Client gửi lệnh charge payment. Provider đã trừ tiền nhưng response bị mất trên mạng. Function timeout và không biết giao dịch đã thành công hay chưa. Nếu retry với một request mới, khách hàng có thể bị charge hai lần.

Giải pháp:

- Tạo idempotency key ổn định cho business operation.
- Gửi cùng key ở mọi attempt.
- Lưu trạng thái và kết quả theo key.
- Provider phải hỗ trợ deduplication hoặc có API tra cứu operation.
- Nếu outcome chưa rõ, tra cứu trạng thái trước khi tạo một operation mới.

Không tạo idempotency key mới ở mỗi lần retry. Key phải đại diện cho cùng một hành động nghiệp vụ xuyên suốt các lần thử.

## 9. Lưu idempotency key trong database

Một bảng đơn giản có thể lưu key, trạng thái và kết quả:

~~~sql
CREATE TABLE idempotency_records (
    idempotency_key VARCHAR(128) PRIMARY KEY,
    request_hash    VARCHAR(128) NOT NULL,
    status          VARCHAR(24) NOT NULL,
    response_body   TEXT NULL,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
~~~

Luồng xử lý:

1. Nhận idempotency key từ caller hoặc tạo operation ID ở backend.
2. Tính request hash để phát hiện cùng key nhưng payload khác.
3. Tạo record ở trạng thái IN_PROGRESS bằng unique constraint.
4. Nếu key đã có trạng thái COMPLETED, trả kết quả đã lưu.
5. Nếu key đang IN_PROGRESS, trả trạng thái phù hợp hoặc cho caller polling.
6. Thực hiện nghiệp vụ trong transaction phù hợp.
7. Lưu kết quả và chuyển trạng thái COMPLETED.
8. Với lỗi tạm thời, giữ trạng thái có thể retry theo policy; với lỗi vĩnh viễn, ghi trạng thái terminal.

Unique constraint là lớp bảo vệ chống hai invocation cùng tạo record cho một key. Cần xử lý race khi hai request đến đồng thời; không chỉ thực hiện SELECT rồi INSERT vì cả hai có thể cùng thấy key chưa tồn tại.

### Cùng key nhưng payload khác

Nếu cùng idempotency key nhưng request hash khác, trả conflict theo contract. Không dùng kết quả cũ cho một payload khác vì có thể tạo nhầm giao dịch.

### TTL và retention

Idempotency record cần được giữ lâu hơn cửa sổ retry/replay tối đa của hệ thống và provider. Xóa record quá sớm có thể khiến một message cũ được redrive rồi thực hiện side effect lần nữa.

## 10. Retry cho HTTP client trong Java

JDK HttpClient không tự cung cấp một policy nghiệp vụ tổng quát cho mọi HTTP status. Ứng dụng cần quyết định lỗi nào retry, số lần, deadline và idempotency.

Một client có thể phân loại:

- Connect exception hoặc một số lỗi I/O tạm thời: có thể retry.
- HTTP 429: retry theo Retry-After và budget.
- HTTP 502/503/504: có thể retry theo contract.
- HTTP 400/401/403: không retry cùng request.
- HTTP 409: chỉ retry khi provider xác định đây là conflict tạm thời.
- Timeout sau khi gửi body: outcome có thể chưa rõ; cần idempotency key.

Đối với POST tạo tài nguyên hoặc charge payment, chỉ retry khi API hỗ trợ idempotency key hoặc có cách xác minh operation trước đó.

### Không retry mọi IOException một cách mù quáng

IOException có thể là connection reset, nhưng cũng có thể xảy ra sau khi request đã được gửi và server đã xử lý. Hãy phân biệt giai đoạn kết nối, gửi request và nhận response nếu thư viện/provider cho phép. Khi không thể biết outcome, xem operation là ambiguous và dùng idempotency/lookup.

## 11. Ví dụ Java: capped exponential backoff với full jitter

Đoạn code dưới đây minh họa retry đồng bộ cho một operation ngắn. Classifier được truyền từ bên ngoài để mỗi dependency có thể áp dụng contract riêng.

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.function.Predicate;

record RetryPolicy(
        int maxAttempts,
        Duration initialDelay,
        Duration maxDelay,
        Duration maxElapsed) {

    public RetryPolicy {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be >= 1");
        }
        if (initialDelay == null || initialDelay.isNegative()
                || initialDelay.isZero()
                || maxDelay == null
                || maxDelay.compareTo(initialDelay) < 0
                || maxElapsed == null
                || maxElapsed.isNegative()
                || maxElapsed.isZero()) {
            throw new IllegalArgumentException("Invalid retry durations");
        }
        if (maxDelay.compareTo(Duration.ofDays(1)) > 0
                || maxElapsed.compareTo(Duration.ofDays(1)) > 0) {
            throw new IllegalArgumentException("Retry durations are too large");
        }
        if (initialDelay.toMillis() < 1 || maxDelay.toMillis() < 1) {
            throw new IllegalArgumentException(
                    "Retry delays must be at least one millisecond");
        }
    }
}

@FunctionalInterface
interface CheckedSupplier<T> {
    T get() throws Exception;
}

public final class RetryExecutor {

    private RetryExecutor() {}

    public static <T> T execute(
            CheckedSupplier<T> operation,
            RetryPolicy policy,
            Predicate<Exception> retryable) throws Exception {

        long startedAt = System.nanoTime();
        long maxElapsedNanos = policy.maxElapsed().toNanos();
        long capMillis = policy.initialDelay().toMillis();
        long maxDelayMillis = policy.maxDelay().toMillis();

        for (int attempt = 1; attempt <= policy.maxAttempts(); attempt++) {
            try {
                return operation.get();
            } catch (Exception error) {
                boolean canRetry =
                        attempt < policy.maxAttempts()
                        && retryable.test(error);

                if (!canRetry) {
                    throw error;
                }

                long elapsed = System.nanoTime() - startedAt;
                long remaining = maxElapsedNanos - elapsed;

                if (remaining <= 0) {
                    throw error;
                }

                long cap = Math.min(capMillis, maxDelayMillis);

                // Full jitter: random delay in [0, cap].
                long delayMillis =
                        ThreadLocalRandom.current().nextLong(cap + 1);
                long delayNanos =
                        TimeUnit.MILLISECONDS.toNanos(delayMillis);

                if (delayNanos >= remaining) {
                    throw error;
                }

                try {
                    Thread.sleep(delayMillis);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    interrupted.addSuppressed(error);
                    throw interrupted;
                }

                capMillis = Math.min(
                        maxDelayMillis,
                        capMillis > maxDelayMillis / 2
                                ? maxDelayMillis
                                : capMillis * 2);
            }
        }

        throw new IllegalStateException("Retry loop ended unexpectedly");
    }
}
~~~

Ví dụ sử dụng:

~~~java
RetryPolicy policy = new RetryPolicy(
        4,
        Duration.ofMillis(200),
        Duration.ofSeconds(2),
        Duration.ofSeconds(5));

String result = RetryExecutor.execute(
        () -> partnerClient.getStatus(operationId),
        policy,
        error -> error instanceof java.io.IOException);
~~~

Đặt các type trong cùng package; class public nằm trong file `RetryExecutor.java`, còn `RetryPolicy` và `CheckedSupplier` là package-private. Đây là skeleton để giải thích policy. Trong production:

- Predicate cần phân loại lỗi cụ thể hơn IOException.
- HTTP response phải được chuyển thành exception có status/error code rõ ràng.
- Request cần per-attempt timeout nhỏ hơn remaining invocation deadline.
- POST có side effect cần idempotency key.
- Nên inject clock/sleeper/random source để unit test delay mà không phải chờ thật.
- Thread.sleep giữ thread và invocation trong thời gian chờ; chỉ dùng cho retry ngắn, không dùng để chờ hàng phút trong function.

Hàm trên giới hạn thời gian chờ giữa các attempt; nó không thể cưỡng chế ngắt một operation đang chạy. Timeout của HTTP/database client và deadline của nền tảng vẫn phải được cấu hình riêng.

## 12. Tôn trọng Retry-After và rate limit

Một số API trả header Retry-After khi giới hạn tốc độ hoặc tạm ngừng dịch vụ:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 3
Content-Type: application/json
~~~

Giá trị có thể là số giây hoặc HTTP date tùy contract. Client cần parse đúng định dạng được hỗ trợ và không retry trước thời điểm provider yêu cầu.

Chính sách kết hợp có thể là:

```text
chosenDelay = max(fullJitterDelay, retryAfterDelay)
```

Sau đó kiểm tra chosenDelay có nằm trong remaining deadline và retry budget không. Nếu không, dừng retry hoặc chuyển operation sang queue/scheduler. Không cắt Retry-After xuống một giá trị nhỏ hơn chỉ để giữ retry nhanh.

Với 429, cần giảm tốc độ request mới hoặc áp dụng token bucket/rate limiter; chỉ trì hoãn các request hiện tại mà vẫn tiếp tục gửi request mới ở tốc độ cũ thì chưa giải quyết được quá tải.

## 13. Retry trong function xử lý message/event

Function được kích hoạt bởi queue hoặc event source thường có retry do nền tảng điều khiển. Cần hiểu trigger semantics:

- Message có thể được giao lại nếu consumer không acknowledge.
- Stream record có thể được đọc lại khi batch thất bại.
- Một batch có thể chứa nhiều record; chỉ một record lỗi có thể khiến cả batch được retry nếu không hỗ trợ partial failure.
- Retry có thể tiếp tục đến khi hết retention hoặc đạt retry policy.
- Ordering có thể bị ảnh hưởng bởi poison message hoặc retry dài.

### Phân biệt retry của handler và retry của event source

Ví dụ consumer gọi API đối tác:

1. Event source giao message cho Java function.
2. Function gọi API đối tác.
3. API trả 503.
4. Function có thể retry ngắn một hoặc hai lần trong invocation.
5. Nếu vẫn thất bại, function trả lỗi/không acknowledge theo contract.
6. Event source giao lại message theo retry policy của nó.

Tổng attempts có thể là số retry nội bộ nhân với số lần delivery của event source. Hãy tính cả hai lớp và đặt giới hạn.

### Không giữ invocation để chờ retry dài

Nếu cần chờ 5 phút hoặc lâu hơn, hãy để event source/workflow/scheduler quản lý delay hoặc ghi retry state. Function nên kết thúc invocation sau khi lưu trạng thái cần thiết, tránh giữ concurrency trong thời gian sleep.

## 14. SQS, visibility timeout và dead-letter queue

Với Amazon SQS, message chưa được xóa sau khi consumer xử lý thành công có thể xuất hiện lại khi visibility timeout hết hạn. Nếu function xử lý lâu hơn visibility timeout, cùng message có thể được giao cho consumer khác trong khi invocation đầu vẫn chạy.

Cần:

- Đặt visibility timeout đủ dài so với thời gian xử lý tối đa và retry nội bộ.
- Đặt function timeout phù hợp.
- Dùng idempotency vì duplicate delivery vẫn có thể xảy ra.
- Cấu hình redrive policy và DLQ.
- Theo dõi ApproximateReceiveCount, queue age và DLQ depth.
- Chỉ xóa/ack message sau khi xử lý và ghi nhận kết quả bền vững.

DLQ giữ message đã vượt ngưỡng receive count hoặc redrive policy. DLQ không tự sửa message. Cần phân loại poison message, tìm nguyên nhân, quyết định sửa dữ liệu/config rồi redrive hay loại bỏ theo retention/compliance.

## 15. Pub/Sub, stream và các event source khác

Mỗi provider có semantics khác nhau:

- **Google Cloud Pub/Sub:** subscriber phải acknowledge trong ack deadline; message chưa được ack có thể được giao lại. Có thể cấu hình retry policy và dead-letter topic theo subscription cùng điều kiện phù hợp.
- **Kinesis Data Streams:** consumer xử lý theo shard/sequence; lỗi batch có thể làm record được đọc lại và ảnh hưởng tiến độ shard. Cần cân nhắc partial batch response, retry và age limit.
- **DynamoDB Streams:** thứ tự được bảo đảm theo item key trong phạm vi stream semantics; retry batch cần được thiết kế để không tạo side effect lặp.
- **Azure Queue/Service Bus:** delivery count, lock duration, abandon/dead-letter và auto-renew semantics khác nhau theo loại queue/subscription.
- **Kafka:** consumer offset chỉ nên commit theo semantics xử lý đã chọn; commit trước khi side effect bền vững có thể làm mất xử lý, commit sau có thể tạo duplicate.

Không áp dụng một con số timeout hoặc retry count chung cho mọi provider. Đọc đúng contract của trigger, function integration và runtime generation đang dùng.

## 16. Dead-letter queue và redrive an toàn

DLQ là nơi cách ly message không thể xử lý sau các lần delivery/retry theo policy. Nó giúp message poison không chặn toàn bộ luồng chính, đồng thời giữ bằng chứng để điều tra.

Một quy trình redrive an toàn:

1. Xác định message bị lỗi do code, dữ liệu, permission hay dependency.
2. Kiểm tra message schema và version.
3. Xác minh operation chưa hoàn tất hoặc side effect chưa xảy ra.
4. Sửa nguyên nhân trước khi redrive.
5. Giữ nguyên business idempotency key khi phát lại.
6. Redrive theo batch nhỏ và rate limit.
7. Theo dõi success, retry và DLQ count.
8. Dừng redrive nếu lỗi lặp lại hoặc dependency quá tải.

Không redrive toàn bộ DLQ cùng lúc nếu downstream không chịu được burst. Không tạo message ID mới để né deduplication. Nếu operation đã thành công nhưng message cũ nằm trong DLQ do ack failure, consumer phải nhận ra idempotency record và trả success mà không thực hiện side effect lần nữa.

## 17. Circuit breaker, bulkhead và rate limiter

Retry nên kết hợp với các cơ chế bảo vệ khác:

| Cơ chế | Mục đích | Khi nào hữu ích |
|---|---|---|
| Circuit breaker | Tạm ngừng gọi dependency khi tỷ lệ lỗi cao | Dependency đang lỗi kéo dài |
| Bulkhead | Giới hạn concurrency theo dependency hoặc workload | Một dependency chậm không được chiếm hết thread/connection |
| Rate limiter | Giới hạn request rate | API đối tác có quota hoặc trả 429 |
| Timeout | Giới hạn thời gian chờ mỗi attempt | Tránh giữ invocation quá lâu |
| Retry budget | Giới hạn phần tải phát sinh do retry | Tránh retry amplification |
| Queue/backpressure | Điều tiết tốc độ xử lý | Arrival rate vượt capacity |

Khi circuit breaker mở, không tiếp tục retry request mới đến dependency đó. Trả lỗi có thể xử lý được hoặc lưu operation để retry sau. Khi chuyển sang half-open, chỉ cho một lượng probe nhỏ để kiểm tra dependency đã phục hồi.

## 18. Timeout và deadline trong Java serverless

Mỗi attempt cần timeout riêng. Tổng deadline cần bao gồm thời gian xử lý, delay và cleanup.

Ví dụ:

- Invocation timeout: 10 giây.
- Xử lý trước khi gọi partner: 1 giây.
- Cần 2 lần gọi partner, mỗi lần timeout tối đa 2 giây.
- Một delay giữa hai lần retry: tối đa 500 ms.
- Cần 1 giây để ghi kết quả và trả response.

Ngân sách tối đa sơ bộ:

```text
1s + 2s + 0.5s + 2s + 1s = 6.5s
```

Còn 3,5 giây buffer cho biến động. Đây chỉ là phép tính ngân sách; timeout thực tế cần xét p95/p99 và các chặng khác.

Không đặt HTTP timeout 30 giây bên trong function có invocation timeout 10 giây. Nền tảng có thể chấm dứt function trước khi client timeout và cleanup. Đặt timeout từng dependency ngắn hơn deadline còn lại, và không bắt đầu attempt mới khi không còn đủ thời gian.

## 19. Quan sát retry và vận hành

Retry làm thay đổi tải và che khuất lỗi nếu chỉ quan sát tỷ lệ success cuối cùng. Một dependency có thể trả lỗi 30% lần đầu nhưng retry giúp cuối cùng thành công; nếu chỉ nhìn business success, đội vận hành không biết dependency đang bất ổn.

Theo dõi:

- Attempts trên mỗi operation.
- Retry count theo dependency và error class.
- Retry success rate.
- Exhausted retries.
- Delay thực tế và backoff distribution.
- 429/5xx, timeout và connection reset.
- Invocation duration và timeout.
- Queue age, receive count, ack deadline expiry.
- DLQ depth và redrive result.
- Idempotency hit/duplicate count.
- Circuit breaker open/half-open duration.

Không dùng operation ID, tenant ID hoặc message ID làm metric label có cardinality cao. Ghi các giá trị đó trong log/trace có kiểm soát; metric nên dùng dependency, error class, attempt bucket và outcome với tập giá trị hữu hạn.

### Log có cấu trúc

Một retry log có thể chứa:

~~~json
{
  "event": "dependency_retry",
  "dependency": "payment-api",
  "operationId": "pay-918",
  "attempt": 2,
  "maxAttempts": 4,
  "errorClass": "HTTP_503",
  "delayMs": 420,
  "remainingDeadlineMs": 2800
}
~~~

Không ghi token, secret, thông tin thanh toán nhạy cảm hoặc toàn bộ request/response body. Correlation ID và operation ID giúp nối các attempt mà không cần lưu payload.

## 20. Kiểm thử retry policy

Retry logic cần test bằng clock, sleeper, random source và fake dependency để tránh test chờ thật hoặc phụ thuộc mạng.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Thành công ở attempt đầu | Không retry |
| Lỗi transient rồi thành công | Retry theo policy và trả kết quả |
| Lỗi permanent | Dừng ngay |
| Đạt maxAttempts | Không gọi thêm |
| Hết maxElapsed | Không bắt đầu attempt mới |
| Delay đạt maxDelay | Không tăng cap vượt giới hạn |
| Jitter | Delay nằm trong khoảng được định nghĩa |
| Retry-After | Không retry sớm hơn thời điểm provider yêu cầu |
| Thread interrupted | Giữ interrupt flag và dừng |
| Timeout sau side effect | Cùng idempotency key không tạo duplicate |
| Hai request cùng key đồng thời | Unique constraint/lock chỉ cho một operation thắng |
| DLQ redrive | Operation đã hoàn tất không thực hiện side effect lần nữa |
| Dependency vẫn lỗi | Circuit breaker/rate limit bảo vệ hệ thống |

### Kiểm thử thời gian không cần sleep thật

Inject một interface Sleeper và nguồn random có thể điều khiển. Unit test xác minh các delay được yêu cầu là 200, 400, 800 ms theo cap và nằm trong khoảng jitter. Dùng fake clock để kiểm tra maxElapsed.

Ngoài unit test, cần integration test với queue/event source trong môi trường test để xác minh ack, visibility timeout, retry count, partial batch failure và DLQ theo đúng provider.

## 21. Những lỗi triển khai thường gặp

- **Retry mọi exception:** lỗi validation và authorization bị lặp vô ích; phân loại retryable/permanent.
- **Không có max attempts:** invocation có thể tiêu tốn thời gian và chi phí vô hạn; đặt giới hạn.
- **Chỉ giới hạn attempts, không giới hạn elapsed time:** một attempt chậm có thể vượt deadline; dùng cả hai.
- **Dùng fixed delay cho mọi client:** tạo thundering herd; thêm jitter.
- **Backoff tăng không có cap:** delay có thể vượt deadline; đặt maxDelay.
- **Retry POST không có idempotency:** có thể tạo giao dịch hoặc tài nguyên trùng.
- **Tạo idempotency key mới mỗi lần retry:** deduplication mất tác dụng; giữ key theo business operation.
- **Retry ở mọi tầng:** request bị nhân lên; xác định retry owner và tổng budget.
- **Ngủ lâu trong function:** giữ concurrency và tăng chi phí; dùng queue/scheduler cho delay dài.
- **Không tôn trọng Retry-After:** tiếp tục gây áp lực lên provider đang rate limit.
- **Không tính timeout/visibility/ack deadline:** message có thể được giao lại trong khi invocation đầu vẫn chạy.
- **Redrive toàn bộ DLQ cùng lúc:** tạo burst mới và lặp sự cố.
- **Không theo dõi retry count:** lỗi dependency bị che khuất bởi retry success.
- **Không xử lý interrupted thread:** function tiếp tục làm việc sau khi runtime muốn dừng.
- **Coi retry là exactly-once:** delivery thường có thể lặp; cần idempotency và state bền vững.

## 22. Quy trình thiết kế retry cho Java serverless

Khi thêm retry cho một dependency hoặc function, thực hiện theo thứ tự:

1. Xác định operation và tác dụng phụ có thể xảy ra.
2. Đọc contract của dependency để phân loại transient, permanent và ambiguous outcome.
3. Xác định lớp nào sở hữu retry: HTTP client, workflow hay event source.
4. Đặt maxAttempts, initialDelay, multiplier, maxDelay và maxElapsed.
5. Dùng exponential backoff có full jitter hoặc chiến lược jitter phù hợp.
6. Tính remaining invocation deadline trước mỗi lần retry.
7. Cấu hình timeout riêng cho mỗi attempt.
8. Tôn trọng Retry-After và rate limit của provider.
9. Dùng idempotency key ổn định cho operation có side effect.
10. Với async event, cấu hình ack/visibility timeout, retry policy và DLQ.
11. Giới hạn retry amplification bằng retry budget, circuit breaker và bulkhead.
12. Theo dõi retry count, exhausted retries, duplicate và DLQ.
13. Kiểm thử transient/permanent error, timeout, interruption, duplicate và redrive.
14. Chỉ redrive sau khi đã xác định nguyên nhân và kiểm soát tốc độ.

## 23. Ghi nhớ

Retry giúp vượt qua lỗi tạm thời, nhưng cũng tạo thêm tải và có thể lặp lại side effect. Hãy phân loại lỗi trước khi retry, dùng exponential backoff với jitter, đặt cả max attempts và max elapsed time, đồng thời tôn trọng deadline của function và Retry-After của dependency.

Với Java serverless, retry đồng bộ chỉ nên ngắn và có timeout rõ ràng. Công việc bất đồng bộ nên dùng retry policy của queue, event source hoặc workflow, kèm visibility/ack deadline, DLQ và redrive có kiểm soát. Không chồng nhiều lớp retry mà không tính tổng attempts.

Mọi operation có tác dụng phụ cần idempotency key ổn định và trạng thái bền vững. Theo dõi retry count, exhausted attempts, queue age và duplicate để thấy dependency đang bất ổn ngay cả khi lần thử sau thành công. Retry chỉ an toàn khi có giới hạn, có quan sát và có cách xử lý kết quả không chắc chắn.

