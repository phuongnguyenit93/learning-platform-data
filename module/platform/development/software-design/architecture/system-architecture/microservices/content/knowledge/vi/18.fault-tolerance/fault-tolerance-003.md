# Retry có giới hạn, Exponential Backoff và Jitter

## 1. Mục tiêu và bối cảnh

Trong hệ thống phân tán, một request có thể thất bại tạm thời vì mạng chập chờn, dịch vụ phụ thuộc vừa khởi động lại, kết nối bị reset hoặc máy chủ đang quá tải. **Retry** là việc thực hiện lại thao tác sau một lỗi được đánh giá là có khả năng phục hồi. Retry có ích khi lỗi chỉ tồn tại ngắn hạn; nếu dùng tùy tiện, nó làm tăng độ trễ, khuếch đại tải và thậm chí tạo tác dụng phụ lặp lại.

Ba cơ chế cần kết hợp:

- **Retry có giới hạn (bounded retry):** giới hạn số lần thử và tổng thời gian chờ.
- **Exponential backoff:** sau mỗi lỗi tạm thời, tăng khoảng chờ theo cấp số nhân tới một mức trần.
- **Jitter:** ngẫu nhiên hóa thời gian chờ để nhiều client không cùng gửi lại tại một thời điểm.

Mục tiêu của chính sách retry là tăng xác suất hoàn tất một thao tác an toàn **trong ngân sách thời gian cho phép**, đồng thời bảo vệ hệ thống phía sau.

### Ví dụ dễ hình dung

Một API đặt hàng gọi dịch vụ kiểm tra tồn kho. Dịch vụ tồn kho trả HTTP 503 trong lúc thay phiên bản triển khai. Thử lại sau khoảng chờ ngắn có thể thành công. Nhưng nếu 2.000 request đều retry ngay lập tức, dịch vụ vừa phục hồi lại nhận thêm một đợt tải lớn. Backoff giảm nhịp gọi; jitter phân tán các lần gọi đó theo thời gian.

## 2. Quyết định có nên retry hay không

Chỉ retry khi đồng thời đáp ứng các điều kiện sau:

1. **Lỗi có thể phục hồi:** ví dụ timeout tạm thời, kết nối bị reset, 502/503/504 hoặc 429 theo chính sách của API. Lỗi dữ liệu sai, thiếu quyền hoặc tài nguyên không tồn tại thường không tự biến mất.
2. **Thao tác an toàn khi lặp lại:** hoặc thao tác có tính idempotent, hoặc phía server hỗ trợ khóa chống thực hiện trùng.
3. **Còn ngân sách:** còn lượt thử, còn deadline và còn đủ thời gian cho khoảng chờ cộng với một lượt gọi có ý nghĩa.
4. **Không có tín hiệu dừng:** người gọi chưa hủy, thread chưa bị interrupt, circuit breaker chưa mở, dịch vụ chưa yêu cầu dừng.

Bảng gợi ý cho API HTTP (hợp đồng của từng API luôn có quyền quyết định cuối cùng):

| Tình huống | Retry? | Điều kiện/giải thích |
|---|---|---|
| HTTP 200–299 | Không | Thành công, kết thúc |
| HTTP 400/401/403/404/422 | Thường không | Request sai, thiếu xác thực/quyền hoặc không có tài nguyên |
| HTTP 408 | Có thể | Request timeout; phải xét idempotency và trạng thái xử lý phía server |
| HTTP 409 | Tùy API | Chỉ retry nếu xung đột thực sự tạm thời và có chiến lược làm mới trạng thái |
| HTTP 429 | Thường có | Tôn trọng Retry-After và giới hạn tốc độ |
| HTTP 500 | Tùy API | Có thể là lỗi nội bộ kéo dài; không mặc định retry mọi 500 |
| HTTP 502/503/504 | Thường có | Lỗi upstream, không sẵn sàng hoặc gateway timeout tạm thời |
| Network timeout/reset | Có thể | Không suy ra request chưa được server thực thi |
| Validation/business error | Không | Sửa dữ liệu hoặc xử lý nghiệp vụ thay vì lặp lại |

Với gRPC, các mã như UNAVAILABLE và đôi khi RESOURCE_EXHAUSTED có thể retry theo hợp đồng; INVALID_ARGUMENT, PERMISSION_DENIED thường không. DEADLINE_EXCEEDED đòi hỏi kiểm tra thời gian tổng thể và nguy cơ thao tác đã hoàn tất ở server.

**Nguyên tắc quan trọng:** "Không nhận được phản hồi" không đồng nghĩa "server chưa thực hiện thao tác". Timeout sau khi gửi lệnh thanh toán là tình huống điển hình cần bảo vệ chống trùng lặp.

## 3. Retry có giới hạn: hai giới hạn phải đi cùng nhau

Chính sách tối thiểu cần những tham số sau:

| Tham số | Ý nghĩa | Ví dụ |
|---|---|---|
| maxAttempts | Tổng số lượt gọi, **bao gồm lượt đầu tiên** | 4 lượt = 1 lượt gốc + tối đa 3 lần thử lại |
| baseDelay | Thời gian chờ nền sau lần thất bại thứ nhất | 200 ms |
| maxDelay | Trần cho một khoảng backoff | 2 giây |
| totalBudget/deadline | Tổng thời gian cho toàn bộ thao tác, gồm gọi và chờ | 5 giây |
| perAttemptTimeout | Timeout tối đa của từng lượt gọi riêng lẻ | 1 giây |
| retryablePredicate | Hàm quyết định lỗi nào đủ điều kiện retry | Timeout, 503, 429 hợp lệ |

Không nên chỉ đặt maxAttempts. Bốn request mà mỗi request có thể treo 30 giây vẫn vượt xa deadline 5 giây. Ngược lại, chỉ có deadline mà không giới hạn số lượt có thể gây retry dồn dập khi lỗi trả về tức thì.

Ví dụ: một endpoint cần trả kết quả trong 3 giây. Nếu lần đầu đã tiêu tốn 2,8 giây thì việc tiếp tục chờ backoff 1 giây là vô nghĩa. Hãy kết thúc bằng lỗi có ngữ cảnh thay vì vượt deadline. Khi người gọi hủy request, hủy luôn timer và retry đang chờ.

**Đặt deadline ở ranh giới nghiệp vụ:** thời gian của HTTP request, RPC, hàng đợi và các dịch vụ con phải nằm trong ngân sách của operation cấp trên; dịch vụ con không tự bắt đầu một ngân sách dài mới sau mỗi lần retry.

## 4. Exponential backoff

Với k là thứ tự **lần retry** bắt đầu từ 1 (không tính lần gọi đầu), khoảng chờ xác định trước jitter là:

~~~text
cappedDelay(k) = min(maxDelay, baseDelay × 2^(k - 1))
~~~

Nếu baseDelay = 200 ms và maxDelay = 2.000 ms:

| Lần gọi | Trạng thái | Chờ trước lượt này (chưa jitter) |
|---|---|---|
| 1 | Gọi ban đầu | 0 ms |
| 2 | Retry 1 | 200 ms |
| 3 | Retry 2 | 400 ms |
| 4 | Retry 3 | 800 ms |
| 5 | Retry 4 | 1.600 ms |
| 6 | Retry 5 | 2.000 ms (đã chạm trần) |

Backoff theo cấp số nhân cho dịch vụ đích thêm thời gian hồi phục và giảm tốc độ bắn request khi lỗi kéo dài. **maxDelay không phải là giới hạn tổng thời gian**: cần kiểm tra deadline trước mỗi sleep và mỗi lần gọi.

Một số lưu ý kỹ thuật:

- Tăng gấp đôi bằng phép tính có giới hạn để tránh integer overflow, đặc biệt khi số lượt thử lớn.
- Đừng thực hiện phép tính số mũ không giới hạn rồi mới lấy min nếu kiểu số có thể tràn.
- Dùng đồng hồ đơn điệu (monotonic clock) để tính ngân sách trôi qua, không lấy chênh lệch thời gian từ đồng hồ hệ thống có thể bị chỉnh.
- Tránh retry vô hạn; ngay cả khi delay đã đạt trần, số lượt và ngân sách vẫn phải dừng.

## 5. Jitter: giải quyết hiện tượng nhiều client cùng retry

Nếu 1.000 client cùng nhận 503 lúc 10:00:00 và cùng áp dụng backoff cố định 200 ms, chúng sẽ quay lại gần như đồng thời lúc 10:00:00.200. Hiện tượng đồng bộ này gọi là **thundering herd**; nó có thể khiến dịch vụ phục hồi lại quá tải. Jitter xáo thời điểm gửi để request trải rộng ra.

Có ba biến thể phổ biến, với d là cappedDelay(k):

| Biến thể | Cách tính khoảng chờ | Đặc điểm |
|---|---|---|
| Full jitter | random(0, d) | Phân tán mạnh; thời gian chờ trung bình khoảng d/2 |
| Equal jitter | d/2 + random(0, d/2) | Giữ một nửa thời gian chờ tối thiểu |
| Decorrelated jitter | min(cap, random(base, previousDelay × 3)) | Khoảng chờ phụ thuộc lần trước, ít đồng bộ, biến động lớn hơn |

Trong đó random(a, b) có nghĩa lấy ngẫu nhiên đều trong khoảng từ a đến b; việc bao gồm đầu mút tùy thư viện nhưng không làm thay đổi bản chất thuật toán.

**Lựa chọn mặc định phù hợp cho nhiều client:** capped exponential backoff với **full jitter**, kết hợp maxAttempts và deadline. Với API nghiêm ngặt về tốc độ hoặc có chỉ dẫn Retry-After, hãy ưu tiên hợp đồng phía server.

Ví dụ full jitter với d = 800 ms: client A có thể đợi 95 ms, B đợi 510 ms, C đợi 734 ms. Cả ba vẫn dùng cùng chính sách nhưng không còn tạo đỉnh tải đúng tại mốc 800 ms.

**Jitter không giải quyết mọi quá tải.** Khi có hàng triệu client, cần thêm rate limiting, giới hạn concurrency, hàng đợi, backpressure và circuit breaker.

## 6. Idempotency: điều kiện để retry không gây hậu quả kép

Một thao tác **idempotent** cho cùng trạng thái kết quả sau khi thực hiện nhiều lần như sau một lần. Trong HTTP, GET thường là phép đọc; PUT được thiết kế theo ngữ nghĩa idempotent; POST thường không đảm bảo điều đó. Tuy nhiên cần kiểm tra triển khai thực tế: một GET có tác dụng phụ hoặc một PUT gửi notification mỗi lần vẫn có thể gây rủi ro khi lặp.

Ví dụ nguy hiểm:

~~~text
Client -> POST /payments (100.000đ)
Server -> ghi nhận thanh toán thành công
Phản hồi -> bị timeout trên đường về
Client -> retry POST /payments
Server -> có thể thu thêm 100.000đ nếu không chống trùng
~~~

Cách bảo vệ thao tác tạo mới/thanh toán:

1. Client sinh **idempotency key** cho một ý định nghiệp vụ, ví dụ mã yêu cầu thanh toán duy nhất.
2. Mọi lần retry của cùng ý định dùng **chính khóa đó**, không tạo khóa mới.
3. Server ghi nhớ khóa, tham số request và kết quả trong khoảng thời gian được quy định; lần lặp trả lại kết quả cũ hoặc trạng thái tương đương.
4. Server xử lý cạnh tranh đồng thời bằng ràng buộc duy nhất/transaction; chỉ lưu key trong cache không bền có thể chưa đủ.
5. Khi key được gửi với payload khác, server phải từ chối hoặc áp dụng quy tắc rõ ràng; cần công bố TTL lưu khóa.

Idempotency key không đồng nghĩa với exactly-once execution trên mọi thành phần. Khi luồng đi qua database, message broker hoặc dịch vụ khác, có thể cần unique constraint, transactional outbox, deduplication và consumer idempotent.

Với thao tác không thể chứng minh an toàn khi lặp, hãy truy vấn trạng thái bằng request ID hoặc chuyển sang bước hòa giải thay vì retry mù.

## 7. Ví dụ triển khai Java: bounded exponential backoff với full jitter

Đoạn Java dưới đây dùng thư viện chuẩn, minh họa bộ thực thi retry đồng bộ. Một chính sách mẫu có 4 lượt gọi tối đa, base 200 ms, trần 2 giây và ngân sách toàn thao tác 5 giây. Hàm nhận predicate để **chỉ retry lỗi tạm thời mà ứng dụng nhận diện được**.

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.Predicate;

public final class RetrySupport {
    private RetrySupport() {}

    public record Policy(
            int maxAttempts,
            long baseDelayMs,
            long maxDelayMs,
            long totalBudgetMs
    ) {
        public Policy {
            if (maxAttempts < 1 || baseDelayMs < 1
                    || maxDelayMs < baseDelayMs
                    || maxDelayMs > 60_000
                    || totalBudgetMs < 1) {
                throw new IllegalArgumentException("Invalid retry policy");
            }
        }
    }

    public static <T> T execute(
            Callable<T> operation,
            Predicate<Exception> isRetryable,
            Policy policy
    ) throws Exception {
        final long startedAt = System.nanoTime();
        final long budgetNanos =
                TimeUnit.MILLISECONDS.toNanos(policy.totalBudgetMs());
        long delayMs = policy.baseDelayMs();
        Exception lastError = null;

        for (int attempt = 1; attempt <= policy.maxAttempts(); attempt++) {
            if (System.nanoTime() - startedAt >= budgetNanos) {
                if (lastError != null) throw lastError;
                throw new TimeoutException("Retry budget exhausted");
            }

            try {
                return operation.call();
            } catch (Exception error) {
                if (error instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                    throw error;
                }
                if (!isRetryable.test(error)
                        || attempt == policy.maxAttempts()) {
                    throw error;
                }

                lastError = error;
                long remainingNanos =
                        budgetNanos - (System.nanoTime() - startedAt);
                if (remainingNanos <= 0) throw error;

                // Full jitter: uniform trong [0, delayMs].
                long jitterMs = ThreadLocalRandom.current()
                        .nextLong(delayMs + 1);
                long waitNanos = TimeUnit.MILLISECONDS.toNanos(jitterMs);

                // Không chờ nếu sẽ tiêu hết ngân sách.
                if (waitNanos >= remainingNanos) throw error;
                try {
                    TimeUnit.NANOSECONDS.sleep(waitNanos);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw interrupted;
                }

                // Nhân đôi có trần, tránh overflow.
                delayMs = delayMs > policy.maxDelayMs() / 2
                        ? policy.maxDelayMs()
                        : Math.min(policy.maxDelayMs(), delayMs * 2);
            }
        }
        throw new AssertionError("Unreachable");
    }
}
~~~

Cách sử dụng mang tính minh họa:

~~~java
RetrySupport.Policy policy =
        new RetrySupport.Policy(4, 200, 2_000, 5_000);

Result result = RetrySupport.execute(
    () -> inventoryClient.readStock(productId),
    error -> error instanceof TransientInventoryException,
    policy
);
~~~

Ở đây Result, inventoryClient và TransientInventoryException là các thành phần ứng dụng cần định nghĩa theo dự án. **Không retry tất cả Exception:** một NullPointerException, lỗi mapping dữ liệu hoặc lỗi xác thực thường cần được sửa, không được che bằng retry.

Giới hạn của ví dụ cần hiểu rõ trước khi đưa vào production:

- Bộ thực thi này kiểm tra ngân sách **giữa** các lượt gọi nhưng không thể ngắt một operation đang treo. HTTP/RPC client phải cấu hình timeout riêng từng lượt và truyền deadline/cancellation khi được hỗ trợ.
- Ví dụ chưa đọc Retry-After từ HTTP 429/503; ứng dụng thật cần xử lý chỉ dẫn này trước khi quyết định delay.
- Đây là mô hình đồng bộ dùng sleep; trong server xử lý nhiều request đồng thời, có thể dùng scheduler/asynchronous retry để tránh giữ thread trong lúc chờ.
- Cần bổ sung telemetry, phân biệt lỗi gốc với lỗi hết ngân sách và chính sách riêng theo endpoint.
- Nếu baseDelay lớn hơn tổng ngân sách hoặc thao tác đã tiêu gần hết deadline, chính sách sẽ dừng sớm; đó là hành vi có chủ ý.

## 8. Xử lý Retry-After và giới hạn tốc độ

Header **Retry-After** có thể được server gửi kèm 429 hoặc 503. Giá trị có thể là số giây hoặc một thời điểm HTTP-date. Client phải giải mã cả hai dạng hợp lệ, kiểm soát giá trị quá lớn và xét ảnh hưởng lệch đồng hồ với dạng ngày.

Một quy tắc hữu ích:

~~~text
delayByPolicy = fullJitter(cappedExponentialDelay)
delayToUse = max(delayByPolicy, validRetryAfterDelay)
if delayToUse không còn nằm trong deadline:
    dừng/đưa lỗi về caller; không tiếp tục retry
~~~

Nếu API quy định Retry-After là thời điểm sớm nhất được phép thử lại thì **không được** dùng jitter để rút ngắn khoảng chờ đó. Khi cần phân tán tải hơn nữa, có thể cộng jitter không âm phía sau mốc Retry-After, miễn vẫn ở trong deadline và hợp đồng API cho phép.

Khi service bị rate limit liên tục, tối ưu trước tiên là **giảm tốc độ tạo request** hoặc đặt hàng đợi, thay vì tăng số lần thử lại. Với một client có nhiều luồng đồng thời, dùng rate limiter dùng chung hoặc retry budget cấp dịch vụ để tất cả luồng không tự tiêu thụ tài nguyên vô hạn.

## 9. Retry trong kiến trúc Microservices

### 9.1. Tránh retry ở mọi tầng

Giả sử A gọi B, B gọi C và mỗi tầng thử tối đa 3 lần cho một yêu cầu thất bại: trong trường hợp xấu, C có thể nhận **3 × 3 = 9** lượt gọi; nếu thêm một tầng retry thứ ba, mức khuếch đại có thể thành **27**. Do đó cần xác định rõ tầng nào chịu trách nhiệm retry.

Khuyến nghị:

- Retry ở tầng **có đủ ngữ cảnh lỗi và tính an toàn nghiệp vụ**; tầng còn lại nên trả lỗi có phân loại.
- Dùng **cùng deadline** xuyên suốt các RPC con; không làm mới deadline vô hạn.
- Đặt retry budget theo dịch vụ/client, ví dụ giới hạn tỷ lệ request phụ được tạo bởi retry so với request gốc.
- Tách chính sách cho request đọc, ghi, tác vụ nền và gọi dịch vụ bên thứ ba.

### 9.2. Retry và các cơ chế khác

| Cơ chế | Vai trò | Quan hệ với retry |
|---|---|---|
| Timeout/deadline | Chặn thao tác kéo dài quá mức | Điều kiện dừng bắt buộc |
| Circuit breaker | Ngừng gọi nhanh khi dependency đang lỗi nặng | Không retry xuyên qua breaker đang mở |
| Rate limiter | Giới hạn số request đi ra | Áp dụng cho cả request mới lẫn retry |
| Bulkhead/concurrency limit | Cô lập tài nguyên, tránh một dependency chiếm hết thread/connection | Chặn retry làm đầy pool |
| Queue + DLQ | Đệm công việc nền và lưu những việc hết số lần xử lý | Phân biệt retry của job với retry HTTP |
| Idempotency/deduplication | Tránh tác dụng phụ lặp lại | Điều kiện cốt lõi cho thao tác ghi |

Với message broker, một lần redelivery thường đã là một hình thức retry. Cần thiết lập số lần giao, delay, dead-letter queue và idempotent consumer; không lồng vòng retry vô hạn bên trong handler rồi để broker tiếp tục retry vô hạn bên ngoài.

### 9.3. Đặt giới hạn theo tài nguyên thực tế

Retry làm tăng tổng lượng công việc. Nếu request gốc đến 100 lần/giây mà mỗi request tạo thêm 3 lượt retry, hệ thống có thể thấy tới 400 lượt gọi/giây trong thời kỳ lỗi. Nên cân nhắc tổng lưu lượng đến dependency, pool kết nối, QPS quota, queue depth, chi phí trả phí theo request và fairness giữa các tenant.

Ở hệ thống có tải cao, có thể giới hạn retry theo **token budget**: mỗi request gốc góp một lượng token, retry tiêu token, và khi token cạn hệ thống ưu tiên request mới. Đây là cơ chế bổ sung; vẫn cần maxAttempts và deadline cho từng request.

## 10. Một luồng quyết định mẫu

~~~text
Bắt đầu thao tác có deadline
    |
    v
Gọi dependency với timeout mỗi lượt
    |
    +-- Thành công --------------------------> Trả kết quả
    |
    +-- Lỗi vĩnh viễn / không idempotent ----> Trả lỗi, không retry
    |
    +-- Lỗi tạm thời
          |
          +-- Caller hủy / hết lượt /
          |   hết deadline / breaker mở ----> Trả lỗi phù hợp
          |
          v
     Tính capped backoff + jitter
     Áp dụng Retry-After nếu có
          |
          +-- Chờ sẽ vượt deadline ----------> Trả lỗi
          |
          v
     Chờ có thể hủy -> thử lại
~~~

Ví dụ một request tra cứu hàng tồn kho với maxAttempts = 4, base = 200 ms, cap = 2 giây:

- Lượt 1: mất 120 ms, trả 503.
- Retry 1: full jitter chọn 90 ms; lượt 2 mất 150 ms, vẫn 503.
- Retry 2: full jitter chọn 310 ms trong khung 0–400 ms; lượt 3 mất 100 ms và trả 200.
- Tổng khoảng 770 ms, 3 lượt gọi; không tạo lượt 4 vì đã thành công.

Đây chỉ là một quỹ đạo ngẫu nhiên để hiểu thuật toán; thời gian thực tế khác nhau theo request và scheduler.

## 11. Quan sát và vận hành

Mỗi lần retry nên có trace/span hoặc event có cấu trúc với các trường: operation/dependency, attemptIndex, maxAttempts, errorClass/statusCode, chosenDelayMs, elapsedMs, remainingBudgetMs và outcome cuối cùng. **Không log token, thông tin thanh toán hay payload nhạy cảm** chỉ để debug retry.

Theo dõi tối thiểu:

- Tỷ lệ request có retry và số lượt retry trung bình/p95 trên một thao tác.
- Tỷ lệ thành công ở lần đầu so với thành công sau retry; tỷ lệ hết lượt và hết deadline.
- Độ trễ end-to-end p50/p95/p99, không chỉ latency của một lượt RPC.
- QPS thực đến dependency, status 429/503, saturation và queue depth.
- Số lần bị chặn bởi circuit breaker, rate limiter và retry budget.

Tỷ lệ "thành công sau retry" tăng có thể vừa là dấu hiệu resilience đang hoạt động, vừa là cảnh báo dependency đang suy giảm. Retry không được che mất lỗi gốc: lưu hoặc gắn nguyên nhân gần nhất và mã lỗi phân loại trong thông tin trả về.

Khi dependency đã quá tải, hành động đúng có thể là giảm concurrency, bật load shedding hoặc tạm ngừng retry; tăng maxAttempts thường làm sự cố nghiêm trọng hơn.

## 12. Kiểm thử chính sách retry

Nên dùng fake clock/fake sleeper và bộ sinh số ngẫu nhiên có thể điều khiển để kiểm thử logic mà không phải chờ thời gian thực. Kiểm thử các kịch bản:

| Kịch bản | Kết quả kỳ vọng |
|---|---|
| Thành công ngay lượt đầu | Gọi đúng 1 lần, không sleep |
| Lỗi tạm thời 2 lần rồi thành công | Gọi 3 lần, có 2 khoảng chờ hợp lệ |
| Lỗi vĩnh viễn (ví dụ 400) | Dừng ngay, không tạo retry |
| Lỗi tạm thời liên tục | Dừng ở maxAttempts, không thêm lượt |
| Hết deadline giữa các lượt | Dừng dù vẫn còn maxAttempts |
| Backoff chạm maxDelay | Các delay không vượt trần |
| Full jitter với nhiều client | Delay nằm trong [0, cappedDelay], phân tán trên nhiều mẫu |
| Có Retry-After hợp lệ | Không gọi trước thời điểm server yêu cầu |
| Caller hủy hoặc thread interrupt | Dừng chờ, bảo toàn tín hiệu hủy |
| Timeout sau ghi thành công | Không tạo thanh toán/đơn hàng trùng |
| Retry tầng A, B, C | Không gây số lượt gọi nhân lên ngoài ngân sách thiết kế |

Bổ sung fault injection bằng proxy/stub tạo timeout, 429, 503, connection reset và mô phỏng dependency phục hồi. Khi tải cao, đánh giá histogram thời điểm retry để phát hiện các đỉnh đồng bộ. Đừng dùng bài kiểm thử chỉ khẳng định có "retry 3 lần" mà bỏ qua deadline hoặc idempotency.

## 13. Những lỗi thiết kế thường gặp

1. **Retry vô hạn:** cạn connection, thread và quota; cần maxAttempts, deadline, retry budget.
2. **Retry ngay lập tức:** tạo thêm tải đúng khi dependency suy yếu; cần backoff.
3. **Backoff không jitter:** client đồng bộ thành các đợt truy cập; thêm jitter.
4. **Retry mọi exception:** che lỗi lập trình, dữ liệu hoặc xác thực; phân loại lỗi rõ ràng.
5. **Retry POST không chống trùng:** gây nhiều giao dịch; dùng idempotency key và ràng buộc tại server.
6. **Bỏ qua Retry-After:** tiếp tục bị 429 và vi phạm hạn mức dịch vụ.
7. **Retry ở nhiều tầng:** khuếch đại request theo cấp số nhân; thống nhất chủ sở hữu retry.
8. **Chỉ tính timeout cho từng lượt:** tổng thời gian vượt SLO; đặt deadline end-to-end.
9. **Dùng sleep chặn thread trong hệ thống tải cao:** làm cạn worker pool; cân nhắc scheduler bất đồng bộ.
10. **Không đo số request bổ sung:** retry âm thầm đẩy dependency đến quá tải; có metrics và giới hạn tập trung.

## 14. Checklist thiết kế trước khi đưa vào production

- [ ] Đã liệt kê lỗi retryable và non-retryable theo hợp đồng dependency?
- [ ] Đã xác nhận thao tác idempotent hoặc có cơ chế chống trùng bền vững?
- [ ] maxAttempts bao gồm lượt đầu và có deadline toàn thao tác?
- [ ] Timeout mỗi lượt, hủy request và interrupt được lan truyền đúng?
- [ ] Backoff tăng theo cấp số nhân, có trần và jitter?
- [ ] Đã xử lý 429/503 Retry-After đúng thời điểm?
- [ ] Đã chọn một tầng chịu trách nhiệm retry và kiểm soát tổng lưu lượng?
- [ ] Có rate limit, circuit breaker hoặc concurrency limit khi cần?
- [ ] Có metrics/trace phân biệt success-first-try, recovered-by-retry và exhausted?
- [ ] Đã kiểm thử lỗi tạm thời, lỗi vĩnh viễn, timeout sau side effect, tải đồng thời và hết ngân sách?

## 15. Ghi nhớ

**Một retry tốt phải có lý do, an toàn, giới hạn và quan sát được.** Exponential backoff cho hệ thống thời gian phục hồi; jitter tránh các client dồn vào cùng một nhịp; maxAttempts và deadline bảo vệ trải nghiệm người dùng và tài nguyên. Với thao tác ghi, idempotency là phần không thể tách rời. Nếu lỗi kéo dài hoặc tải hệ thống đang tăng, biết **dừng retry đúng lúc** cũng quan trọng như biết thử lại.

Các thuật ngữ cần nắm: transient failure, bounded retries, per-attempt timeout, end-to-end deadline, capped exponential backoff, full/equal/decorrelated jitter, thundering herd, idempotency key, Retry-After, retry budget, circuit breaker và backpressure.