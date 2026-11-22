# Xác định chính sách thử lại có giới hạn và tính an toàn khi chạy lại

> **Module:** Spring Framework – concurrency  
> **Nhóm:** Xử lý ngoại lệ  
> **Mục tiêu:** thiết kế **bounded retry** (thử lại với số lần và thời gian hữu hạn) đồng thời chứng minh một tác vụ **an toàn để chạy lại** theo đúng hợp đồng nghiệp vụ. Retry giúp vượt qua lỗi tạm thời nhưng cũng có thể gây giao dịch trùng, quá tải dây chuyền hoặc che lỗi vĩnh viễn nếu làm sai.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Quyết định **có nên retry hay không** dựa trên bản chất lỗi, tính an toàn của thao tác và trạng thái không chắc chắn của lần gọi trước.
2. Viết một chính sách rõ ràng về `maxAttempts`, timeout mỗi lần, deadline tổng, exponential backoff, jitter, điều kiện dừng và exhausted handling.
3. Phân biệt **retryable failure** với **idempotent operation**: lỗi có thể hết sau khi thử lại không đồng nghĩa thao tác chạy lại là an toàn.
4. Hiểu idempotency key, deduplication, transaction boundary, unique constraint, outbox và cách xử lý “server đã thực hiện nhưng client chưa nhận response”.
5. Viết chương trình Java 17 dùng retry hữu hạn, test không cần đợi đồng hồ thật và xác nhận đúng số lần gọi.
6. Áp dụng vào `ThreadPoolTaskExecutor`, `CompletableFuture` và Spring Retry/Resilience4j mà không block worker vô hạn, không retry theo tầng nhân cấp số lần gọi.
7. Thiết kế metrics, log, kiểm thử tải, trường hợp hủy và graceful shutdown để kiểm soát retry trong production.

## 2. Vấn đề gốc: thất bại không có nghĩa thao tác chưa được thực hiện

Hình dung một ứng dụng gửi yêu cầu thanh toán:

~~~text
Client                       Payment service
   |                                |
   +----- POST /charge ------------>|
   |                                +--- ghi giao dịch thành công
   |                                |
   |<-------- response bị mất --- X  |
   |                                |
   +--- timeout ở client             |
   |                                |
   +--- retry không có định danh --->|--- có thể ghi thêm lần nữa
~~~

Client chỉ nhìn thấy `TimeoutException` hoặc lỗi socket, nên **không biết chắc** server chưa xử lý. Nếu retry như một giao dịch mới, khách hàng có thể bị trừ tiền hai lần. Đây là **kết quả không rõ (ambiguous outcome)**, không phải bằng chứng chưa thực thi.

Retry đúng cần trả lời **hai câu hỏi độc lập**:

- **Lỗi có khả năng tạm thời không?** Ví dụ một TCP connect timeout do hệ thống phụ trợ ngắn hạn quá tải.
- **Nếu lần trước thực ra đã thành công, thực hiện lại cùng yêu cầu có gây hậu quả mới không?** Nếu có, cần idempotency/dedup/reconciliation hoặc không tự động thử lại.

Một API có thể **retryable về mặt kỹ thuật** nhưng **không an toàn khi chạy lại về mặt nghiệp vụ**. Không nên cho mọi request dùng chung một chính sách retry chỉ vì chúng đều ném `RuntimeException`.

## 3. Định nghĩa retry, attempt, idempotency và duplicate

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Attempt** | Một lần thực sự gọi operation/remote endpoint |
| **Retry** | Một attempt bổ sung **sau** một attempt trước thất bại |
| **Max attempts** | Tổng số attempt, **bao gồm** lần đầu, nếu API quy định như vậy |
| **Backoff** | Thời gian chờ trước attempt tiếp theo |
| **Jitter** | Biến thiên ngẫu nhiên của khoảng backoff để phân tán retry |
| **Retry budget** | Giới hạn tài nguyên được phép dùng cho retry (số lượng, thời gian, tỷ lệ) |
| **Deadline** | Thời điểm cuối toàn operation phải kết thúc |
| **Idempotent** | Lặp lại cùng yêu cầu có cùng **hiệu ứng dự định** lên hệ thống như một lần thực hiện |
| **Deduplication** | Phát hiện nhiều lần giao cùng identity và không áp dụng side effect hai lần |
| **At-least-once delivery** | Có thể gửi lại để tránh mất việc, nên phía nhận phải xử lý duplicate |
| **Unknown outcome** | Caller mất response, không biết việc trước đó đã commit hay chưa |

**Lưu ý cách đếm:** nếu chính sách của ứng dụng là **`maxAttempts = 3`**, nó thường có nghĩa **lần đầu + tối đa 2 lần thử lại**. Nhưng API khác có thể đặt tên `maxRetries = 3`, nghĩa là **1 lần đầu + 3 lần thử lại = tối đa 4 attempts**. Hãy đọc hợp đồng thư viện và đo số invocation thực tế thay vì suy từ tên thuộc tính.

### Idempotency không có nghĩa response byte-by-byte giống nhau

Theo RFC 9110, idempotency nói về **hiệu ứng dự định** trên server, không phải bắt buộc mọi mã HTTP, timestamp, log hoặc response đều giống hệt nhau. Một `PUT` lặp lại cùng representation có thể để lại cùng trạng thái tài nguyên, dù mỗi lần ghi thêm bản ghi audit. Bài toán thanh toán có yêu cầu mạnh hơn: **không ghi nhận cùng một charge hai lần** khi retry cùng operation identity.

## 4. Phân loại lỗi trước khi quyết định retry

Không có bộ quy tắc “mọi 5xx retry, mọi 4xx không retry” đúng cho tất cả API. Một ma trận khởi đầu:

| Nhóm lỗi | Có nên retry? | Điều kiện/giải thích |
| --- | --- | --- |
| Lỗi validation/thiếu trường bắt buộc, `400`, `422` | Thường **không** | Gửi lại y hệt không sửa input không giúp thành công |
| Sai quyền `401`/`403` | Không retry y hệt | Cần refresh credential hoặc thay quyền theo logic riêng, tránh loop |
| `404` với resource vĩnh viễn không tồn tại | Thường không | Nhưng hệ thống eventual consistency có thể cho phép retry ngắn nếu contract nói vậy |
| Xung đột `409`/optimistic locking | Phân tích trước | Có thể cần đọc trạng thái mới, merge hoặc thông báo conflict; không lặp thao tác mù |
| `408 Request Timeout` | Có thể | Chỉ khi operation an toàn để chạy lại hoặc đã có identity/dedup |
| `429 Too Many Requests` | Có thể sau chờ | Tôn trọng `Retry-After`/quota, hạn chế tổng số lần, tránh cùng lúc retry |
| `502 Bad Gateway` / `503 Service Unavailable` / `504 Gateway Timeout` | Thường xem là ứng viên | Kiểm tra loại downstream và tính idempotent, không retry liên tục khi quá tải |
| `500 Internal Server Error` | Có thể hoặc không | Có hệ thống báo lỗi 500 sau khi đã commit; không giả định vô side effect |
| TCP connect failure trước khi request được gửi | Thường có thể | Cần xác nhận client/transport thực sự chưa gửi yêu cầu |
| Read timeout / connection reset **sau khi gửi** | **Kết quả không chắc chắn** | Phải đảm bảo idempotency hoặc thực hiện status lookup/reconciliation |
| Lỗi dữ liệu/parse deterministic | Không | Cùng input sẽ lỗi lại, thử nhiều lần chỉ tiêu tốn tài nguyên |
| `CancellationException` hoặc chủ động hủy | Thường không | Người dùng hoặc hệ thống đã quyết định không tiếp tục |
| `InterruptedException` | Không auto-retry mù | Khôi phục interrupt flag hoặc truyền lên chính sách hủy |
| JVM `Error` / `OutOfMemoryError` | Không dùng retry thông thường | Cần xử lý lỗi hệ thống, tránh khuếch đại sự cố |

Phân loại nên được **cụ thể hóa bằng exception type và contract**. Ví dụ, thư viện HTTP có thể gộp timeout và connection errors vào một lớp exception chung, nhưng phải kiểm tra **giai đoạn gửi** để biết hiệu ứng có thể đã xảy ra hay chưa.

Đừng dùng `catch (Exception e) { retry(); }` cho mọi exception. Đặc biệt, lỗi programmer bug như `NullPointerException` hoặc dữ liệu bất hợp lệ sẽ bị lặp lại hàng loạt, làm log nhiễu và tăng tải.

### Retryable không đồng nghĩa recoverable

- **Retryable:** thử lại có cơ hội đổi kết quả.
- **Recoverable:** có đường xử lý khác khi không thể hoàn thành (trả fallback, queue bền vững, yêu cầu người dùng can thiệp).
- **Idempotent:** lặp lại không làm tăng số side effect mong muốn.
- **Compensatable:** có thể thực hiện một hành động bù sau khi đã phát sinh hiệu ứng. Bù trừ không phải một bảo đảm exactly-once.

Một tác vụ có thể retryable nhưng không idempotent, chẳng hạn gọi API “tạo hóa đơn mới” với mỗi POST không có operation key.

## 5. Chính sách retry cần có những thuộc tính nào?

Hãy ghi chính sách thành một bản mô tả có thể kiểm tra:

~~~text
Operation: partner.readProduct
Identity: tenantId + productId
Max attempts: 3 (bao gồm lần đầu)
Retry only: connect timeout; HTTP 429/502/503/504 theo contract
Never retry: validation, authorization, cancellation, interrupt
Per-attempt timeout: 700 ms
Overall deadline: 2.5 s từ lúc bắt đầu
Backoff: exponential base=100 ms, cap=500 ms, full jitter
Retry-After: tôn trọng nếu còn nằm trong deadline
On exhaustion: trả lỗi có cause gốc + metrics + trạng thái rõ ràng
Idempotency: read-only; không có side effect nghiệp vụ
Concurrency budget: bounded executor/queue, không retry vô hạn
~~~

Đây là **ví dụ thiết kế**, không phải thông số mặc định cho mọi hệ thống. Cùng chiến lược không được tự động áp vào `partner.createPayment` mà chưa có cơ chế tránh charge trùng.

### 5.1. Tổng số lần thử

Gọi `A` là max attempts:

~~~text
A = 1 -> 1 lần gọi đầu, 0 retry
A = 2 -> 1 lần gọi đầu, tối đa 1 retry
A = 3 -> 1 lần gọi đầu, tối đa 2 retries
~~~

Mỗi attempt có thể kết thúc bằng success, lỗi không retry được, timeout hoặc cancellation. Khi đạt ngưỡng, **dừng**, không lặp vòng vô hạn hoặc gửi việc lại queue mà không có chính sách tổng.

Nếu hệ thống có HTTP client tự retry và tầng service lại retry, số request thật có thể cao hơn kỳ vọng:

~~~text
service retry 3 attempts
  × SDK retry 3 attempts / service attempt
  = tới 9 request downstream cho 1 logical operation
~~~

Nếu thêm một API gateway cũng retry 2 lần, mức tối đa lý thuyết có thể thành 18 lần. Phải biết chính sách ở **tất cả các tầng**, tránh “retry storm”.

### 5.2. Timeout mỗi attempt và deadline tổng

Đặt `maxAttempts` chưa đủ. Giả sử mỗi attempt có read timeout 10 giây và có 3 attempts: dù backoff rất ngắn, yêu cầu có thể kéo dài hơn 30 giây, vượt xa SLA HTTP 2 giây.

Phân biệt:

- **Per-attempt timeout:** giới hạn một lần gọi mạng/I/O.
- **Overall deadline:** giới hạn toàn logical operation gồm attempts và thời gian chờ giữa chúng.
- **Queue wait budget:** nếu task phải đợi `ThreadPoolTaskExecutor` mới bắt đầu, nó cũng phải được trừ vào deadline.
- **Client disconnect/cancellation:** nếu request đã bị hủy, không tiếp tục retry trừ khi công việc đã chuyển sang workflow nền có chủ đích.

Trước khi bắt đầu attempt mới, kiểm tra thời gian còn lại có đủ cho **min attempt timeout + backoff** hoặc ít nhất một khoảng hữu ích không. Không làm tròn deadline từ lúc lên lịch mà quên thời gian chờ queue.

### 5.3. Backoff tăng dần

Một công thức exponential backoff không jitter:

\[
d_k = \min(d_{\max}, d_0 \cdot 2^{k-1})
\]

Trong đó `k` là số lần thất bại đã xảy ra trước retry tiếp theo (`k=1` là delay đầu tiên), `d_0` là delay cơ bản, `d_max` là mức trần.

Ví dụ `d_0 = 100 ms`, `d_max = 500 ms`:

| Sau attempt thất bại số | Delay trước retry tiếp |
| --- | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 500 ms (đạt cap) |
| 5 | 500 ms |

Không nhân đôi `long` vô hạn rồi mới gọi `Math.min`: biểu thức có thể overflow. Có thể dùng so sánh trước khi nhân đôi hoặc thư viện backoff đã xử lý overflow.

### 5.4. Jitter chống đồng loạt gọi lại

Nếu 10.000 client cùng nhận 503 và đều chờ đúng 1 giây, chúng sẽ đồng loạt gọi lại, gây một đợt tải thứ hai.

Một cách là **full jitter**: với backoff tính được `d_k`, chọn ngẫu nhiên delay trong khoảng `[0, d_k]` (định nghĩa chính xác inclusive/exclusive theo implementation). Có cả equal jitter và decorrelated jitter với phân phối khác nhau; cần chọn theo nhu cầu.

Jitter không có nghĩa bỏ cap/deadline. Chọn delay xong vẫn kiểm tra còn đủ ngân sách để thực thi retry. Nếu server trả `Retry-After`, hãy tôn trọng ý nghĩa thời điểm có thể thử lại và giới hạn budget; không dùng jitter để thử **sớm hơn** yêu cầu của server khi contract yêu cầu chờ tối thiểu.

### 5.5. Điều kiện dừng hợp lệ

Dừng retry khi:

1. Operation thành công.
2. Gặp lỗi không retryable.
3. Đạt max attempts.
4. Deadline tổng hết hoặc không đủ ngân sách cho attempt kế tiếp.
5. Được cancel/interrupt, Spring context đang đóng hoặc client không còn cần kết quả.
6. Circuit breaker đã mở, rate/concurrency budget không cho phép retry hoặc cơ chế overload shedding yêu cầu dừng.

Nếu hết attempts, **trả/phát trạng thái thất bại có cause** theo hợp đồng. Không được log rồi trả một kết quả thành công giả, hoặc gọi lại trong background không giới hạn mà không có job ownership.

## 6. Ví dụ Java 17 chạy độc lập: bounded retry với kết quả xác định

Ví dụ sau thực sự hiện thực một **vòng lặp có tối đa 3 attempts**, chỉ retry loại lỗi do chính ứng dụng gắn nhãn là tạm thời. Nó sử dụng `Sleeper` có thể inject để không phụ thuộc `Thread.sleep` trong test.

Tạo tệp **`BoundedRetryDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedRetryDemo {

    @FunctionalInterface
    interface CheckedOperation<T> {
        T run() throws Exception;
    }

    @FunctionalInterface
    interface Sleeper {
        void pause(long millis) throws InterruptedException;
    }

    static final class TransientFailure extends Exception {
        TransientFailure(String message) {
            super(message);
        }
    }

    static final class RetryPolicy {
        private final int maxAttempts;
        private final long baseMs;
        private final long capMs;
        private final Sleeper sleeper;

        RetryPolicy(int maxAttempts, long baseMs, long capMs,
                    Sleeper sleeper) {
            if (maxAttempts < 1 || baseMs < 0 || capMs < baseMs) {
                throw new IllegalArgumentException("invalid policy");
            }
            this.maxAttempts = maxAttempts;
            this.baseMs = baseMs;
            this.capMs = capMs;
            this.sleeper = sleeper;
        }

        long backoffAfterFailure(int failedAttempt) {
            long delay = baseMs;
            for (int i = 1; i < failedAttempt; i++) {
                if (delay > capMs / 2) {
                    return capMs;
                }
                delay = Math.min(capMs, delay * 2);
            }
            return Math.min(capMs, delay);
        }

        <T> T call(CheckedOperation<T> action) throws Exception {
            for (int attempt = 1; attempt <= maxAttempts; attempt++) {
                try {
                    return action.run();
                } catch (TransientFailure failure) {
                    if (attempt == maxAttempts) {
                        throw failure;
                    }

                    long delay = backoffAfterFailure(attempt);
                    System.out.println(
                            "retry after " + attempt + " = "
                                    + delay + "ms");

                    try {
                        sleeper.pause(delay);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        throw interrupted;
                    }
                }
            }
            throw new AssertionError("unreachable");
        }
    }

    public static void main(String[] args) throws Exception {
        // Test sleeper: không đợi thời gian thật.
        RetryPolicy retry = new RetryPolicy(3, 100, 500, ms -> {});

        AtomicInteger calls = new AtomicInteger();
        String result = retry.call(() -> {
            int attempt = calls.incrementAndGet();
            System.out.println("call = " + attempt);
            if (attempt < 3) {
                throw new TransientFailure("temporary");
            }
            return "OK";
        });

        System.out.println("result = " + result);
        System.out.println("attempts = " + calls.get());

        AtomicInteger invalidCalls = new AtomicInteger();
        try {
            retry.call(() -> {
                invalidCalls.incrementAndGet();
                throw new IllegalArgumentException("bad request");
            });
        } catch (IllegalArgumentException failure) {
            System.out.println(
                    "not retryable = " + failure.getMessage());
        }
        System.out.println(
                "validation attempts = " + invalidCalls.get());

        AtomicInteger downCalls = new AtomicInteger();
        try {
            retry.call(() -> {
                downCalls.incrementAndGet();
                throw new TransientFailure("service unavailable");
            });
        } catch (TransientFailure failure) {
            System.out.println(
                    "exhausted = " + failure.getMessage());
        }
        System.out.println(
                "exhausted attempts = " + downCalls.get());
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac BoundedRetryDemo.java
java BoundedRetryDemo
~~~

**Stdout chính xác của chương trình**:

~~~text
call = 1
retry after 1 = 100ms
call = 2
retry after 2 = 200ms
call = 3
result = OK
attempts = 3
not retryable = bad request
validation attempts = 1
retry after 1 = 100ms
retry after 2 = 200ms
exhausted = service unavailable
exhausted attempts = 3
~~~

### Giải thích output

- Ở trường hợp đầu, attempt 1 và 2 ném `TransientFailure`, nên retry được schedule sau delay tính toán; attempt 3 trả `"OK"`. Tổng cộng có **3 attempts**, **2 retries**.
- `IllegalArgumentException` không thuộc catch trong retry loop, nên **chỉ gọi một lần**, không “chữa” input bằng cách thử thêm.
- Khi downstream luôn thất bại, loop dừng ở attempt 3 và **ném lại lỗi cuối** `TransientFailure`; không thử lần thứ tư.
- Thời gian đợi chỉ được **ghi kế hoạch** chứ không thực sự chờ vì truyền `ms -> {}`. Đó là cách kiểm thử logic backoff mà không bị flaky do scheduler.
- Nếu thay bằng `Thread::sleep`, chính **thread gọi `RetryPolicy.call`** sẽ bị block trong lúc chờ; điều này chỉ phù hợp với môi trường synchronous/worker được quản lý. Không gọi nó trên event-loop hoặc dùng để chiếm request thread quá lâu.
- Bài demo cố tình tách policy cơ bản (maxAttempts, loại lỗi, backoff, interrupt) khỏi production policy còn phải bổ sung **overall deadline, per-attempt timeout, jitter, HTTP status/Retry-After, quan sát metrics và idempotency**. Không nên copy nguyên demo thành client tiền thật.

### Vì sao không đặt một while(true)?

`while(true)` chỉ an toàn khi mọi đường đều chứng minh được có điều kiện dừng hữu hạn. Chính sách ở đây dùng `for (attempt <= maxAttempts)`, nên tránh vô hạn ngay cả khi lỗi tạm thời lặp mãi. Các component gọi retry **nhiều tầng** vẫn phải có ngân sách tổng, không thể chỉ dựa vào giới hạn cục bộ.

## 7. Tính an toàn khi chạy lại: ba kiểu thao tác

### 7.1. Read-only và thao tác không có side effect dự định

Tra cứu sản phẩm theo ID, lấy một trạng thái được xác định rõ thường có thể retry sau lỗi mạng. Tuy nhiên, **GET không tự động an toàn** nếu endpoint thực chất làm thay đổi trạng thái nghiêm trọng (ví dụ dùng GET để kích hoạt chuyển tiền): đó là API thiết kế sai semantics. Giới hạn thời gian vẫn cần để tránh bombard downstream.

### 7.2. Thao tác đặt trạng thái (idempotent theo nghiệp vụ)

Ví dụ `setInventoryLevel(productId, 10)`: gọi cùng request nhiều lần vẫn đặt mức tồn kho thành 10. Với HTTP, `PUT` là idempotent theo semantics chuẩn khi resource server thực hiện đúng hợp đồng.

Khác với `incrementInventory(productId, 10)`: gọi hai lần cộng thêm 20, **không idempotent**. Tên method hoặc HTTP verb riêng nó không làm phép cộng trở nên an toàn khi retry.

### 7.3. Thao tác tạo hoặc chuyển tiền (non-idempotent nếu không có key)

Ví dụ:

~~~text
createPayment(order=7, amount=500000)
createPayment(order=7, amount=500000)
~~~

Nếu API tạo một payment ID mới cho mỗi lần gọi, kết quả là **hai khoản thanh toán**, dù payload giống hệt. Để có thể retry, cần định danh một logical operation, ví dụ `Idempotency-Key: pay-order-7-v1` và xử lý trùng ở phía nhận.

**Đừng sinh key mới cho mỗi attempt**. Cùng logical operation phải dùng cùng idempotency key qua các retries, kể cả sau timeout/mất response. Nếu request thật sự là một giao dịch mới, phải dùng identity mới theo business contract.

## 8. Idempotency key: contract tối thiểu

Một mô hình thanh toán hoặc tạo job có thể định nghĩa:

~~~http
POST /payments HTTP/1.1
Idempotency-Key: 8fb1e0c4-... 
Content-Type: application/json

{"orderId":"order-7","amount":500000,"currency":"VND"}
~~~

Đây là **ví dụ HTTP minh họa**, key là placeholder cấu trúc, không phải token được cấp thực tế.

Phía server cần:

1. **Xác thực/giới hạn scope** của key: cùng key dưới cùng tenant/account hoặc namespace, tránh khách hàng A vô tình va chạm B.
2. **So khớp payload** bằng request fingerprint ổn định. Nếu key giống nhưng nội dung tiền/số lượng khác, phải báo xung đột/không hợp lệ theo API contract, không âm thầm trả response của request cũ.
3. **Claim key atomic**: hai request đồng thời cùng key không được cùng vượt qua bước kiểm tra rồi đều thực thi side effect.
4. **Lưu trạng thái** như `IN_PROGRESS`, `SUCCEEDED`, `FAILED_FINAL` và kết quả nghiệp vụ để request trùng biết hành động phù hợp.
5. **Có chính sách cho IN_PROGRESS**: chờ giới hạn, trả 202/409 hoặc hướng dẫn poll; không tự khẳng định đã thành công.
6. **Giữ key đủ lâu** theo thời gian mà client có thể retry/replay, có TTL và quy trình cleanup rõ.
7. **Xử lý crash giữa các bước**: lưu key nhưng side effect chưa chạy, hoặc side effect đã chạy nhưng chưa lưu kết quả; cần transaction boundary/outbox/provider idempotency/reconciliation.

### Bảng trạng thái cơ bản

| Trạng thái theo key | Request mới cùng key/payload | Điều kiện cần nhớ |
| --- | --- | --- |
| Chưa có key | Thử claim atomic và bắt đầu operation | UNIQUE constraint/transaction/conditional write |
| `IN_PROGRESS` | Không thực thi side effect lần hai; trả trạng thái/đợi có giới hạn | Nếu owner chết cần lease/timeout/recovery an toàn |
| `SUCCEEDED` | Trả kết quả đã lưu hoặc status của operation cũ | Không tạo thêm payment/job |
| `FAILED_FINAL` | Trả lỗi terminal đã lưu, hoặc contract cho phép tạo operation mới bằng key mới | Không coi cùng key là một giao dịch mới |
| Key cũ nhưng payload khác | Từ chối theo contract (thường 409 hoặc lỗi tương ứng) | Ngăn dùng lại key sai mục đích |

Không được dùng `if (!map.containsKey(key)) { performSideEffect(); map.put(key,...); }` trong môi trường cạnh tranh: hai thread/pod có thể cùng qua check trước khi write. `synchronized` local hoặc `ConcurrentHashMap` cũng **không** giải quyết việc nhiều pod/replica và lưu dữ liệu sau restart.

### Atomic claim và business transaction

Nếu side effect là cập nhật **cùng một database**, có thể tận dụng UNIQUE index và transaction để claim key + ghi nghiệp vụ + lưu outcome trong một boundary phù hợp. Nếu side effect là gọi **payment provider bên ngoài**, local DB transaction **không thể** khiến HTTP call từ xa và DB commit trở nên atomic. Khi đó cần chuyển **cùng idempotency key tới provider** nếu provider hỗ trợ, ghi outbox/status và có cơ chế reconciliation cho tình huống kết quả không chắc chắn.

**Không hứa exactly-once end-to-end chỉ vì có idempotency table.** Thực tế, mục tiêu là một logical effect duy nhất theo key trong phạm vi contract và failure model mà hệ thống có thể kiểm soát.

## 9. Java 17: demo idempotency nội bộ một JVM

Ví dụ ngắn này cho thấy cùng một identity trả cùng một kết quả trong **bộ nhớ một tiến trình**, không tăng số logical operation lần hai. Nó **không** phải implementation thanh toán production hoặc idempotency phân tán.

Tạo tệp **`LocalIdempotencyDemo.java`**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class LocalIdempotencyDemo {
    private static final ConcurrentHashMap<String, String> operations =
            new ConcurrentHashMap<>();

    private static final AtomicInteger committed =
            new AtomicInteger();

    static String recordOnce(String key) {
        return operations.computeIfAbsent(key, ignored -> {
            int number = committed.incrementAndGet();
            return "operation-" + number;
        });
    }

    public static void main(String[] args) {
        System.out.println("first = " + recordOnce("order-7"));
        System.out.println("retry = " + recordOnce("order-7"));
        System.out.println("logical operations = " + committed.get());
    }
}
~~~

Chạy:

~~~bash
javac LocalIdempotencyDemo.java
java LocalIdempotencyDemo
~~~

**Stdout xác định:**

~~~text
first = operation-1
retry = operation-1
logical operations = 1
~~~

Trong demo, `computeIfAbsent` là thao tác đồng bộ phù hợp để thêm một entry trong một `ConcurrentHashMap` của cùng JVM; callback tạo kết quả in-memory, không gọi downstream.

**Cảnh báo quan trọng:** Không đặt thao tác chuyển tiền/gửi email thật vào callback `computeIfAbsent` rồi kết luận an toàn production. Nếu callback gây side effect bên ngoài rồi JVM chết trước khi map lưu entry, retry có thể thực hiện side effect lần nữa. Nếu nhiều pod có map riêng, mỗi pod có thể thực hiện một lần. Để tránh trùng thật, cần state được lưu bền và được điều phối cùng business operation/provider.

## 10. Mô hình dữ liệu thực tế cho idempotent operation

Một bảng minh họa PostgreSQL:

~~~sql
CREATE TABLE idempotent_operations (
    tenant_id        VARCHAR(100) NOT NULL,
    operation_key    VARCHAR(200) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    status           VARCHAR(30)  NOT NULL,
    response_payload TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, operation_key)
);
~~~

Đây là **DDL minh họa**, cần bổ sung giới hạn độ dài, index, retention và quyền truy cập tùy hệ thống. `PRIMARY KEY` đảm bảo hai transaction không cùng chèn một key trong một database. Nhưng table này tự nó **chưa** bảo đảm atomic effect với hệ thống bên ngoài.

Một luồng tham khảo:

~~~text
Request (tenant, idempotency key, request body)
                |
                v
Validate + fingerprint request body
                |
                v
Atomic INSERT / claim key
                |
       +--------+--------------------+
       |                             |
   claim được                   đã tồn tại
       |                             |
       v                             +-- mismatch body -> reject
 status IN_PROGRESS                 |
       |                             +-- SUCCEEDED -> reuse outcome
       v                             |
 perform business side effect       +-- IN_PROGRESS -> wait/poll policy
       |                             |
       v                             +-- failed -> follow explicit contract
 Save durable outcome
       |
       v
 Return response
~~~

Điều khó nhất là **crash giữa side effect và ghi outcome**. Nếu hai thay đổi cùng database, cần transaction phù hợp. Nếu hệ thống gọi bên ngoài, phải dựa vào remote idempotency token hoặc quy trình xác minh trạng thái thực tế.

### Khi IN_PROGRESS bị kẹt

Một record IN_PROGRESS không nên khóa mãi vì instance xử lý cũ đã chết. Có thể dùng lease + owner token/fencing; khi lease hết, worker mới phải xác định thao tác cũ đã áp dụng chưa trước khi chạy lại. Chỉ xóa record và chạy lại mà không reconciliation có thể gây duplicate.

### Khi payload thay đổi

Cùng key, một bên yêu cầu 500.000 VND, bên kia 700.000 VND: đó **không** phải cùng logical command. Server phải từ chối theo contract, không lấy kết quả cũ hoặc tạo thêm side effect với cùng key.

### Khi key hết hạn

TTL ngắn hơn khả năng client replay có thể biến retry muộn thành operation mới. Chọn retention dựa trên SLA retry, xử lý queue, thời gian reconciliation và đặc tính nghiệp vụ; với thanh toán/đơn hàng cần lưu dấu vết nghiệp vụ bền vững hơn cache quota ngắn hạn.

## 11. Các kiểu công việc concurrency và điểm đặt retry

### 11.1. Retry ở HTTP client

Trong các lời gọi downstream, retry thường phù hợp **ở ranh giới gọi remote**, vì đây là nơi biết loại lỗi, mã HTTP, trạng thái gửi request và deadline. Hãy chuyển operation identity qua header, không sinh key trong mỗi attempt.

~~~java
public Receipt callProvider(String key, ChargeRequest request) {
    return paymentHttpClient.charge(key, request);
}
~~~

Đây là **snippet service**, các kiểu `Receipt`, `ChargeRequest` và `paymentHttpClient` thuộc ứng dụng. Đối với `charge`, retry chỉ an toàn khi provider hỗ trợ semantics idempotency theo `key`, hoặc có cơ chế status lookup/reconciliation đủ mạnh.

### 11.2. Retry trong ThreadPoolTaskExecutor

Một `ThreadPoolTaskExecutor` chỉ quyết định **worker/queue**, không tự tạo retry policy cho lỗi nghiệp vụ. Nếu task ném exception:

- `execute(Runnable)` với Runnable thô có thể để lỗi thoát trên worker/error observer.
- `submit(Callable)` thường giữ lỗi trong `Future`; caller gọi `get()` để thấy `ExecutionException` có cause.
- Lỗi **task rejection** khi pool bão hòa xảy ra tại thời điểm gửi; tự gửi lại ngay lập tức trong vòng lặp không delay có thể làm quá tải nặng hơn.
- Worker ngủ trong `Thread.sleep(backoff)` tiếp tục **chiếm slot**; nếu có hàng nghìn retry chờ, có thể gây thread starvation. Dùng scheduler/delayed queue có giới hạn hoặc retry async nonblocking khi cần nhiều pending retries.

**Không** dùng một retry vô hạn bên trong một Runnable mà không theo dõi trạng thái: nếu task bị cancel, shutdown hoặc context đóng, worker có thể không thoát đúng hạn.

### 11.3. Retry với CompletableFuture

Một future thất bại **không tự chạy lại** chỉ vì bạn gọi:

~~~java
future.exceptionally(error -> fallback);
~~~

Đó là **recovery từ lỗi của stage**, không tự tạo attempt mới. Để retry một `CompletableFuture`, cần **supplier tạo future mới cho mỗi attempt** và điều phối delay/exhaustion:

~~~java
Supplier<CompletableFuture<Receipt>> freshAttempt =
        () -> provider.chargeAsync(sameIdempotencyKey, request);
~~~

Đây là **snippet**, giả định `provider`, `sameIdempotencyKey`, `request` và type `Receipt` có sẵn.

Mỗi attempt phải gọi `freshAttempt.get()` để tạo một operation mới theo cùng logical idempotency identity; chỉ đăng ký callback khác lên **cùng một future đã exceptional** không phải thử lại.

Một scheduler có giới hạn có thể lên lịch attempt tiếp:

~~~java
scheduler.schedule(
        () -> startNextAttemptIfAllowed(),
        delayMillis,
        TimeUnit.MILLISECONDS);
~~~

Đây là **snippet**, cần `scheduler`, `startNextAttemptIfAllowed()`, `delayMillis` và deadline logic thực tế. Lên lịch không chặn worker nhưng job scheduler cũng cần queue capacity, ownership, cancel và shutdown. Khi future kết hợp thất bại, còn phải phân biệt retry **toàn chuỗi** hay chỉ source bị lỗi.

### 11.4. @Async và proxy của Spring

`@Async` quyết định cách dispatch một method qua Spring proxy, **không tự retry**. Nếu kết hợp `@Async` với retry annotation:

- Kiểm tra thứ tự interceptor và kiểu trả về thực tế.
- `@Async void` không trả Future để caller biết kết quả, phải có `AsyncUncaughtExceptionHandler` hoặc giám sát job riêng.
- `@Async CompletableFuture` yêu cầu quan sát future exceptional; retry một completion stage không giống retry method synchronous.
- Gọi từ chính bean bằng `this.method()` trong proxy mode thông thường bypass `@Async` và các advice proxy như retry.
- Không giả định transaction của caller hoặc MDC/security context tự chuyển vào worker.

Nếu công việc có side effect quan trọng, một queue có persistence, job ID và trạng thái retry bền vững thường phù hợp hơn một callback fire-and-forget trong JVM.

## 12. Spring Retry và Spring Framework 7: hai cách đếm dễ nhầm

Có **hai API khác nhau** cần phân biệt theo version/dependency, ngay cả khi annotation cùng tên `@Retryable`.

### 12.1. Spring Retry 2.x (module riêng, dùng với nhiều ứng dụng Spring 6/Boot 3)

Spring Retry nằm trong dependency **`org.springframework.retry:spring-retry`**, không phải một tính năng mặc định cứ có Spring 6.2 là tự bật. Đối với annotation/proxy, cần cấu hình `@EnableRetry` và các thành phần Spring AOP phù hợp.

Ví dụ Spring Retry 2.x:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.annotation.EnableRetry;

@Configuration
@EnableRetry
public class RetryConfiguration {
}
~~~

Một service:

~~~java
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Retryable;
import org.springframework.stereotype.Service;

@Service
public class RemoteCatalog {
    private final PartnerClient client;

    public RemoteCatalog(PartnerClient client) {
        this.client = client;
    }

    @Retryable(
            retryFor = TemporaryPartnerFailure.class,
            maxAttempts = 3,
            backoff = @Backoff(
                    delay = 200,
                    multiplier = 2.0,
                    maxDelay = 1000))
    public Product load(String productId) {
        return client.fetch(productId);
    }
}
~~~

Đây là **các class minh họa trong ứng dụng Spring Retry 2.x**, cần các kiểu `PartnerClient`, `TemporaryPartnerFailure`, `Product` do dự án định nghĩa và dependency Spring Retry/AOP. `maxAttempts = 3` nghĩa là **3 lần gọi tổng cộng** (lần đầu + tối đa 2 retries). Backoff ví dụ: 200 ms rồi 400 ms, nếu cả hai retry đều xảy ra.

**Cảnh báo proxy:** gọi `this.load(...)` từ chính bean trong proxy mode có thể bypass retry advice. Gọi từ bean khác qua Spring proxy. Retry annotation cũng không thay thế overall deadline/idempotency và có thể block thread lúc backoff tùy interceptor.

### 12.2. Spring Framework 7 core resilience

Từ **Spring Framework 7.0**, core Spring Framework có bộ resilience API riêng, trong đó có một annotation `@Retryable` thuộc package **`org.springframework.resilience.annotation`**. Nó **không đồng nhất** với `org.springframework.retry.annotation.Retryable` của module Spring Retry.

Với cơ chế Framework 7, thuộc tính đếm retry sau lần đầu (ví dụ `maxRetries` trong reference) được định nghĩa theo **số lần retry**; tài liệu core ghi rõ tổng attempts bằng **1 initial attempt + số retry được phép**. Đây là một lý do quan trọng phải đọc đúng **version** và **package** của annotation đang dùng, không chuyển cấu hình `maxAttempts=3` từ Spring Retry sang một API `maxRetries=3` rồi mặc định vẫn chỉ có 3 lần gọi.

Khi nâng cấp Spring/Boot, hãy kiểm tra dependency graph, annotation import, proxy activation và semantics retry thực tế bằng test đếm invocation. Không giả định ứng dụng Spring Framework 6 có core `@Retryable` thuộc package Framework 7.

### 12.3. Khi nào dùng thư viện thay vì tự viết loop?

- **Spring Retry:** logic retry method synchronous, tích hợp bean/proxy, dễ xác định exception classifier và recovery.
- **Resilience4j Retry:** cấu hình retry, metric, composition với CircuitBreaker/RateLimiter/Bulkhead; cần chú ý cách decorator và thư viện nhận kết quả async.
- **HTTP client/SDK có retry tích hợp:** tận dụng khi đã biết semantics endpoint và có deadline/idempotency.
- **Custom loop:** phù hợp cho ví dụ học hoặc policy rất đặc thù, nhưng cần tự kiểm soát timeout, scheduler, observability và race condition.

Dù dùng công cụ nào, **không để nhiều tầng tự động retry cùng một thao tác** nếu không nắm được tổng số attempts.

## 13. Retry khác Circuit Breaker, Rate Limiter và Bulkhead

| Cơ chế | Câu hỏi chính | Khi nào giúp? |
| --- | --- | --- |
| Retry | “Lỗi tạm thời này có đáng thử lại trong budget không?” | Glitch ngắn hạn, lỗi transient, kết quả an toàn khi chạy lại |
| Circuit Breaker | “Downstream đang lỗi hàng loạt, có nên ngưng gửi việc một thời gian?” | Tránh đập liên tục vào dependency không khỏe |
| Rate Limiter | “Mỗi khoảng thời gian được bao nhiêu lượt?” | Giới hạn quota/rate theo client hoặc backend |
| Bulkhead/Semaphore | “Có bao nhiêu lời gọi đồng thời được giữ tài nguyên?” | Bảo vệ DB/HTTP connection, memory, worker |
| Timeout | “Một attempt hoặc toàn operation được chờ bao lâu?” | Ngăn request treo vô hạn |
| Idempotency | “Lặp cùng operation có tạo side effect trùng không?” | Ngăn thu tiền/đặt hàng/gửi job hai lần |
| Outbox/Job store | “Crash/restart có mất ý định thực hiện hoặc trạng thái retry không?” | Workflow cần durability và retry sau process restart |

**Retry là cách tạo thêm tải**, không phải cách giảm tải: với 10% lỗi và retry liên tục, hệ thống phụ trợ có thể nhận nhiều request hơn mức traffic ban đầu. Khi downstream đang bão hòa, backoff/jitter, circuit breaker, rate limit và retry budget giúp giảm khuếch đại.

### Tính toán retry storm qua nhiều tầng

Nếu một API frontend cho 3 attempts và service backend lại cho 3 attempts trên cùng remote call, một request nghiệp vụ có thể tạo **9 calls remote** ở trường hợp lỗi dai dẳng. Nếu client người dùng lại retry 2 lần, tổng thành **18 calls remote**. Cần quyết định **tầng nào sở hữu retry chính**, còn tầng khác truyền nguyên nhân/đặt deadline thay vì nhân số attempts.

### Budget theo tỷ lệ

Ngoài maxAttempts từng logical operation, nhiều hệ thống còn dùng “retry tokens” hoặc giới hạn retries trong một khoảng thời gian. Mục đích là tránh khi dependency gặp outage, hàng nghìn operation mỗi operation retry 3 lần tạo tổng tải quá lớn. Tỷ lệ retry được phép nên dựa vào SLO/downstream capacity và có thể giảm khi circuit breaker mở.

## 14. Xử lý HTTP Retry-After một cách đúng nghĩa

`Retry-After` là HTTP header có thể biểu thị **số giây chờ** hoặc **thời điểm HTTP-date**; không nên tự diễn giải mọi giá trị là milliseconds. Ví dụ:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 3
Content-Type: text/plain

Temporarily unavailable
~~~

Client có thể xem xét thử lại **sau ít nhất 3 giây** nếu còn trong overall deadline và operation an toàn để chạy lại. Nếu SLA cho phép chờ tối đa 1 giây, policy đúng có thể là **không retry ngay**, trả lỗi có nguyên nhân thay vì bất chấp header.

Với 429, rate limiter có thể gợi ý thời điểm quota hồi phục. Nhưng không phải mọi response 429/503 đều có Retry-After; client cần fallback backoff với jitter có cap. Cần parse HTTP-date theo chuẩn, dùng clock đáng tin và tính thêm độ trễ mạng.

## 15. Cách kiểm soát timeout và cancellation trong Spring concurrency

Một request có chuỗi:

~~~text
HTTP request deadline = 2.5 s
    |
    +-- thread pool queue wait
    +-- attempt 1: connect + read timeout
    +-- backoff
    +-- attempt 2
    +-- backoff
    +-- attempt 3
    |
    v
Response / failure trước deadline
~~~

Thời gian **xếp hàng** trong executor vẫn thuộc ngân sách tổng, không thể bỏ qua. Lưu deadline bằng nguồn đo elapsed-time phù hợp, ví dụ `System.nanoTime()` cho timeout trong JVM (đừng dùng `currentTimeMillis()` làm nguồn monotonic).

### Khi bị interrupt

Trong code blocking:

~~~java
try {
    Thread.sleep(delayMillis);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "Retry interrupted", interrupted);
}
~~~

Đây là **snippet**, cần `delayMillis` đã được tính. Tác vụ nên tôn trọng shutdown/cancel; không bắt interrupt rồi lập tức retry lần nữa.

### Khi CompletableFuture timeout

`future.orTimeout(2, TimeUnit.SECONDS)` sẽ làm future hoàn thành exceptional nếu chưa xong khi đến hạn. Nó không mặc nhiên dừng remote request hoặc rollback side effect đã xảy ra. Tương tự, `future.get(2, TimeUnit.SECONDS)` hết hạn **chỉ là caller ngừng chờ**, còn task có thể vẫn chạy.

Khi hợp nhất nhiều attempt, cancellation cần được chuyển tới attempt hiện tại nếu underlying client hỗ trợ và việc hủy không gây side effect mới; không tự hủy một request thanh toán đã vào server rồi khẳng định chưa thanh toán.

## 16. Kết quả không chắc chắn: xử lý theo hợp đồng nghiệp vụ

Giả sử service tạo order:

1. Client gửi `createOrder(orderKey=K)`.
2. Server commit order thành công.
3. Connection bị reset trước khi client nhận order ID.
4. Client nhận `IOException`.

Ba chiến lược:

**A. Có idempotency key và server dedup:** client retry **cùng K**. Server trả order ID cũ, không tạo order mới.

**B. Có status lookup:** trước khi retry operation tạo mới, truy vấn theo `clientOrderId=K` hoặc tìm trạng thái đã commit. Nếu xác định chưa có, mới cân nhắc gửi lại; việc kiểm tra cũng cần xử lý race/concurrent requests.

**C. Không có identity/dedup và hậu quả lớn:** không tự retry. Báo trạng thái chưa xác định, lưu thông tin để reconciliation hoặc yêu cầu operator/manual review.

Tránh trả lỗi “order failed” như một khẳng định chắc chắn nếu kết quả thực tế **chưa biết**; nếu client tự bấm lại như một đơn mới, hậu quả có thể nghiêm trọng hơn.

### Outbox và retry sau crash

Trong nghiệp vụ cần phát event khi ghi DB, **transactional outbox** giúp ghi trạng thái nghiệp vụ và một hàng outbox trong cùng transaction; worker gửi outbox sau đó. Delivery có thể **at-least-once**, nên consumer vẫn phải idempotent theo event ID. Đừng coi outbox là công cụ magical exactly-once across systems.

## 17. Sơ đồ quyết định trước mỗi retry

~~~text
Attempt thất bại
        |
        v
Đã cancel / interrupt / shutdown?
   | yes -> DỪNG; trả cancellation/interruption
   | no
   v
Exception/HTTP status thật sự có cơ hội hồi phục?
   | no -> DỪNG; báo lỗi gốc
   | yes
   v
Operation chạy lại có an toàn?
   | no/unknown -> STATUS LOOKUP / RECONCILE / DỪNG
   | yes
   v
Đạt maxAttempts / retry budget?
   | yes -> DỪNG; báo exhaustion
   | no
   v
Còn deadline sau khi chờ backoff/Retry-After?
   | no -> DỪNG; báo deadline exhaustion
   | yes
   v
Chọn delay với backoff + jitter / Retry-After
        |
        v
Chờ không chặn nếu async, kiểm soát queue
        |
        v
Retry SAME logical operation identity
        |
        +-- ghi attempt metric và quay lại
~~~

Quy trình cần phân biệt “truy vấn trạng thái” với “gọi lại gây side effect”; một số read-only lookup cũng có quota và timeout riêng.

## 18. Giám sát để biết retry đang giúp hay gây hại

Những chỉ số tối thiểu:

| Metric | Ý nghĩa |
| --- | --- |
| `operation_attempts_total` | Tổng số attempt thực tế theo operation/endpoint |
| `operation_retries_total` | Số attempt bổ sung sau lần đầu |
| `operation_retry_exhausted_total` | Số logical operation hết quota |
| `retry_delay_ms` | Phân bố delay và jitter |
| `attempt_latency_ms` | Thời gian mỗi attempt |
| `operation_latency_ms` | Tổng latency kể cả queue/backoff |
| `retry_success_after_failure` | Phần trăm operation thành công sau khi retry |
| `retry_not_safe_total` | Số lần không retry vì unknown outcome/idempotency thiếu |
| `idempotency_duplicate_total` | Số request trùng key được dedup |
| `idempotency_in_progress` | Key đang xử lý và thời gian bị treo |
| `downstream_rejections` | 429/503/connection saturation, dấu hiệu retry đang tăng tải |

Gắn correlation ID, logical operation ID và **attempt number** vào log/tracing. Tránh dùng mỗi retry như một transaction mới với ID mới hoàn toàn khiến không nối được nguyên nhân.

Không đưa key thanh toán, token bảo mật, payload nhạy cảm hoặc thông tin cá nhân chưa che vào log; có thể hash/key scope và dùng internal job ID. Cần có cảnh báo khi retry exhausted tăng hoặc p99 latency tăng dù tỉ lệ thành công cuối cùng có vẻ vẫn ổn.

## 19. Những test quan trọng

### 19.1. Test số lần gọi chính xác

Dùng một fake operation ném `TransientFailure` hai lần rồi thành công. Assert tổng calls = 3, delay đã lên lịch = 100/200 ms trong cấu hình ví dụ, result = OK. Với lỗi validation, assert calls = 1. Với lỗi transient vĩnh viễn, assert calls không vượt maxAttempts.

### 19.2. Test thời gian bằng fake clock/sleeper

Không cần `Thread.sleep(1000)` trong unit test. Inject `Sleeper`/`Clock` hoặc scheduler kiểm soát được; assert policy đã chọn delay, deadline và cancellation đúng. Khi kiểm thử full jitter, inject nguồn random có seed hoặc fake random để test phân phối/biên mà không cố đo chính xác thời gian hệ điều hành.

### 19.3. Test timeout sau commit

Mô phỏng server **đã commit** nhưng response bị mất. Client retry cùng key; assert số business transaction thực = 1 và response trả về cùng resource. Nếu hệ thống không có dedup, test này phải báo **không an toàn để retry**, không cố che bằng retry thêm.

### 19.4. Test hai request cùng key đến đồng thời

Cho hai thread/pod đồng thời claim cùng key: chỉ một owner được thực thi side effect. Owner thứ hai nhận kết quả cũ, trạng thái pending, hoặc response theo contract. Unit test dùng `CountDownLatch`, integration test dùng database/Redis transaction thật; `synchronized` local không chứng minh an toàn đa pod.

### 19.5. Test retry storm và nested policies

Load test khi 30% downstream calls bị 503, giữ nguyên request rate của client và quan sát **tổng requests tới downstream**. Nếu upstream và SDK cùng retry, kiểm tra hệ số nhân. Kiểm tra bảo vệ bằng circuit breaker/retry budget và kết quả khi downstream hoàn toàn không phục hồi.

### 19.6. Test cancellation/shutdown

Đóng Spring context hoặc cancel future khi đang chờ backoff. Verify không có attempt mới sau cancellation/deadline; worker được giải phóng, tài nguyên trả về, không có queue retry vô hạn.

### 19.7. Test phân loại lỗi

Tách test cho validation, authentication, conflict, timeout trước khi gửi, timeout sau khi gửi, 429/503 có Retry-After, 500 sau commit, interrupt/cancel và failure nội bộ code. **Không** chỉ test mỗi happy path “thất bại một lần rồi thành công”.

## 20. Sai lầm thường gặp

**Sai lầm 1: “Bắt mọi Exception rồi retry”.**  
Lỗi dữ liệu, bug lập trình hoặc từ chối quyền sẽ không tự biến mất; retry tạo thêm tải và che nguyên nhân.

**Sai lầm 2: “maxAttempts=3 nghĩa là 3 retry cộng lần đầu”.**  
Sai với Spring Retry 2.x: `maxAttempts` tính cả lần đầu. Một số API khác dùng `maxRetries` để đếm lần sau; phải đọc đúng contract.

**Sai lầm 3: “Timeout chứng minh server chưa chạy”.**  
Sai: server có thể đã commit và chỉ mất response. Phải xét unknown outcome.

**Sai lầm 4: “POST cùng payload là idempotent”.**  
Không mặc định. Nếu API tạo mới mỗi lần, cùng payload vẫn tạo hai record/payment.

**Sai lầm 5: “Mỗi attempt dùng idempotency key mới cho chắc”.**  
Ngược lại, nó phá dedup giữa các attempts của cùng logical operation.

**Sai lầm 6: “Chỉ cần ConcurrentHashMap là an toàn”.**  
Nó không chia sẻ giữa pod, không bền qua crash, không atomic với remote side effect.

**Sai lầm 7: “Backoff cố định là đủ khi hàng nghìn client cùng lỗi”.**  
Retry đồng loạt sau cùng một delay có thể gây thundering herd; cần jitter/budget.

**Sai lầm 8: “Đã có maxAttempts nên không cần deadline”.**  
Ba lần I/O mỗi lần 20 giây vẫn có thể vượt SLA một phút.

**Sai lầm 9: “Có tổng deadline nên không cần per-attempt timeout”.**  
Một attempt I/O không giới hạn có thể không phản ứng với deadline nếu client không được cấu hình hủy.

**Sai lầm 10: “Thread.sleep trong @Async không tốn tài nguyên”.**  
Nó giữ worker, có thể làm đầy pool và queue; dùng scheduler khi nhiều retry dài.

**Sai lầm 11: “CompletableFuture.exceptionally là retry”.**  
Nó xử lý exceptional completion; để thử lại phải gọi supplier tạo attempt mới.

**Sai lầm 12: “Mọi tầng đều retry 3 lần là tăng khả năng thành công mà không có giá”.**  
Có thể tạo 9 hoặc 27 calls thực tới cùng dependency.

**Sai lầm 13: “@Retryable ở method nào cũng chạy”.**  
Với proxy-based Spring Retry, self-invocation thường bypass advice; cần gọi qua bean/proxy, cấu hình AOP đúng và test thật.

**Sai lầm 14: “@Async void ném lỗi lên caller”.**  
Ngoại lệ trong worker không tự truyền về caller; cần handler hoặc Future/status riêng.

**Sai lầm 15: “Idempotency key đã lưu là chắc chắn đúng một lần”.**  
Crash sau remote side effect nhưng trước khi lưu outcome vẫn có thể gây duplicate. Dùng provider key, transaction/outbox, reconciliation.

**Sai lầm 16: “Retry thất bại thì trả success để người dùng yên tâm”.**  
Đó là che lỗi. Cần báo trạng thái thất bại/chưa xác định hoặc job pending có thể theo dõi.

**Sai lầm 17: “Hết Retry-After thì nhất định thử lại”.**  
Nếu deadline đã hết hoặc operation không an toàn, cần dừng.

**Sai lầm 18: “Retry luôn có thể cải thiện hệ thống đang quá tải”.**  
Retry tăng traffic. Khi backend bão hòa, có thể làm outage kéo dài; cần backoff/jitter, rate/bulkhead/circuit breaker.

## 21. Bài tập tự luyện

### Bài 1 — Đếm đúng số attempts

Policy `maxAttempts=4`, operation fail transient mãi. Có bao nhiêu lần gọi tất cả?

**Đáp án:** tối đa 4 attempts, gồm 1 lần đầu + 3 retries nếu code policy dùng định nghĩa này. Đừng nhầm với `maxRetries=4` ở API khác.

### Bài 2 — Lỗi validation

API nhận thiếu `customerId` và trả 400. Có nên tự retry không?

**Đáp án:** không retry cùng payload. Cần sửa input hoặc trả lỗi validation cho client.

### Bài 3 — Timeout sau khi gửi thanh toán

Client đã gửi request chuyển tiền, bị read timeout. Có thể tự gửi lại bằng một key mới không?

**Đáp án:** không an toàn. Server có thể đã ghi giao dịch. Dùng lại cùng idempotency key nếu provider hỗ trợ hoặc status lookup/reconciliation; nếu không có bảo đảm, xử lý unknown outcome theo contract.

### Bài 4 — Tính backoff

Base = 100 ms, multiplier 2, cap 500 ms, maxAttempts=5. Nếu mọi attempt thất bại, delay nào xảy ra giữa các attempts trước khi exhausted?

**Đáp án:** 100 ms, 200 ms, 400 ms, 500 ms — có 4 khoảng chờ cho tối đa 5 lần gọi. Jitter có thể thay đổi delay thật trong giới hạn đã định.

### Bài 5 — Spring Retry khác Framework 7

Một nhóm đang dùng Spring Retry `org.springframework.retry.annotation.Retryable(maxAttempts=3)`. Nhóm khác tham khảo Spring Framework 7 core `@Retryable` với `maxRetries=3`. Số invocation tối đa có cùng không?

**Đáp án:** không. Trong Spring Retry, maxAttempts 3 là 3 lần tổng; trong core Framework 7, maxRetries 3 có thể cho 1 lần đầu + 3 retries. Phải xác minh đúng API và import.

### Bài 6 — Retry qua nhiều tầng

HTTP client retry 3 attempts, service cũng retry 3 attempts. Khi lỗi liên tục, tối đa bao nhiêu calls downstream cho một operation?

**Đáp án:** có thể là 9. Hãy chọn nơi sở hữu retry và đặt budget tổng.

### Bài 7 — Idempotency khi chạy nhiều pod

Hai request cùng key đến hai pod, mỗi pod dùng `HashMap` riêng để dedup. Có bảo đảm thực hiện đúng một lần không?

**Đáp án:** không. Hai map không chia sẻ state. Dùng database/coordination atomic hoặc provider idempotency để chặn duplicate toàn cụm.

### Bài 8 — Thread pool đầy

Một `ThreadPoolTaskExecutor` đã đầy. Service catch `TaskRejectedException` rồi ngay lập tức gọi submit lại trong vòng `while(true)`. Hệ quả?

**Đáp án:** vòng lặp có thể đốt CPU và đẩy áp lực vào executor đang đầy. Cần fail fast hoặc retry có giới hạn/backoff, đồng thời cân nhắc giới hạn queue và ownership.

### Bài 9 — Không có Retry-After

Server trả 503 không có Retry-After. Bạn nên làm gì?

**Đáp án:** nếu operation an toàn để chạy lại, chọn backoff với jitter, tôn trọng attempts/deadline/budget; nếu không an toàn thì dừng và reconcile thay vì mặc định retry.

### Bài 10 — CompletableFuture

`future.exceptionally(ex -> defaultValue)` có tạo thêm HTTP request không?

**Đáp án:** không. Nó chỉ recover failure của future. Retry thật cần nhà cung cấp tạo attempt mới và một bộ điều phối delay/exhaustion.

## 22. Checklist áp dụng cho Spring production

- [ ] Định nghĩa logical operation và phạm vi idempotency rõ: user/tenant/key/payload hash.
- [ ] Phân loại retryable exception/status; không retry validation/bug/interrupt bừa bãi.
- [ ] Max attempts **có giới hạn** và cách đếm đã được test.
- [ ] Có per-attempt timeout, overall deadline và retry budget toàn tầng.
- [ ] Backoff có cap, jitter; xử lý `Retry-After` đúng đơn vị và giới hạn.
- [ ] Không retry non-idempotent operation khi outcome chưa rõ nếu thiếu dedup/lookup.
- [ ] Giữ **cùng idempotency key** qua toàn bộ retries của một logical operation.
- [ ] Dùng atomic claim/unique constraint; xử lý mismatch, IN_PROGRESS, crash và TTL.
- [ ] Với external side effect: provider idempotency/outbox/reconciliation, không suy exactly-once chỉ từ DB local.
- [ ] Không nested retry quá mức; hiểu retry đã được bật trong SDK/client.
- [ ] Không sleep lâu trong pool nhỏ hoặc request thread, ưu tiên scheduler có giới hạn nếu async.
- [ ] Với Spring Retry: có dependency và proxy, method public được gọi qua bean; phân biệt Spring Framework 7 core.
- [ ] Với `@Async`/`CompletableFuture`: có error observer và cancellation lifecycle.
- [ ] Metrics có attempt, retry, exhausted, deadline, duplicate, latency và saturation.
- [ ] Có test timeout sau commit, duplicate concurrent, failover và shutdown.
- [ ] Không trả success giả khi exhaustion/unknown outcome; báo trạng thái có thể theo dõi.

## 23. Tóm tắt

**Retry tốt = đúng lỗi + đúng thao tác + số lần hữu hạn + ngân sách thời gian/tài nguyên + backoff/jitter + kết quả có thể quan sát.** Không có điều kiện nào trong số này là tùy chọn khi lỗi có thể gây ảnh hưởng nghiệp vụ.

**An toàn khi chạy lại** đòi hỏi hơn việc gửi request giống nhau: phải xác định cùng **logical operation identity**, bảo đảm **cùng side effect không được áp dụng hai lần** trong phạm vi contract, và xử lý kết quả không chắc chắn do timeout/crash.

Trong Spring concurrency, `ThreadPoolTaskExecutor`/`@Async` giải quyết việc dispatch công việc, không tự giải quyết retry hay idempotency. Spring Retry hoặc Resilience4j hỗ trợ orchestration nhưng không biến một thao tác chuyển tiền không có dedup trở thành an toàn. Nếu không thể chứng minh retry an toàn, **dừng, tra cứu trạng thái hoặc reconcile**, thay vì thử lại mù.

## Tài liệu tham khảo

- Java SE 17 — `ExecutorService`, `Future`, `ScheduledExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
- Java SE 17 — `ConcurrentHashMap`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- Java SE 17 — `CompletableFuture`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- RFC 9110 — HTTP Semantics, safe/idempotent methods và `Retry-After`: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 6585 — HTTP 429 Too Many Requests: https://www.rfc-editor.org/rfc/rfc6585.html
- Spring Retry 2.x `@Retryable` (maxAttempts tính cả lần đầu): https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Retryable.html
- Spring Retry `@EnableRetry`: https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/EnableRetry.html
- Spring Framework 7 — Core Resilience Features: https://docs.spring.io/spring-framework/reference/core/resilience.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- AWS Builders' Library — Timeouts, retries, backoff with jitter: https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
- Microservices.io — Transactional Outbox Pattern: https://microservices.io/patterns/data/transactional-outbox.html
