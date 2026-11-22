# Giới hạn số lần thử và ngân sách thời gian tổng

Retry (*thực thi lại*) giúp một thao tác phục hồi khi gặp lỗi tạm thời như deadlock, serialization failure hoặc dịch vụ phụ thuộc bị gián đoạn trong thời gian ngắn. Nhưng retry chỉ hữu ích khi có giới hạn. Nếu ứng dụng thử vô hạn, mỗi yêu cầu có thể giữ tài nguyên lâu, làm hàng đợi dài thêm và tạo áp lực lớn hơn lên chính hệ thống đang gặp sự cố.

Một chính sách retry cần kiểm soát ít nhất hai điều: **số lần thử tối đa** và **ngân sách thời gian tổng** (*overall time budget* hoặc deadline). Số lần thử giới hạn số lần một thao tác được thực hiện. Ngân sách thời gian giới hạn tổng thời gian từ lúc bắt đầu đến khi thành công hoặc trả lỗi, bao gồm thời gian chạy từng lần, thời gian chờ giữa các lần và overhead của ứng dụng.

Ví dụ, một yêu cầu đặt hàng có deadline `2 giây` và tối đa `3 lần thử` (tính cả lần đầu). Nếu lần đầu mất `700 ms`, lần hai mất `600 ms`, và backoff giữa hai lần là `100 ms`, ứng dụng chỉ còn khoảng `600 ms` cho lần cuối và overhead. Không thể bắt đầu thêm một lần thử kéo dài `1 giây` rồi vẫn tuyên bố đã tuân thủ deadline `2 giây`.

## 1. Vì sao retry phải có giới hạn?

Một số lỗi có thể tự biến mất nếu thử lại sau một khoảng ngắn:

- Database chọn transaction làm deadlock victim.
- Hệ quản trị từ chối transaction vì serialization conflict.
- Một kết nối bị reset tạm thời hoặc pool chưa có connection sẵn.
- Dịch vụ phụ thuộc trả `503 Service Unavailable` hoặc báo quá tải tạm thời.
- Một thao tác bị giới hạn tốc độ và phản hồi thời điểm có thể thử lại.

Tuy nhiên, thử lại cũng tiêu thụ tài nguyên: CPU, connection, thread, socket, transaction, bộ nhớ và năng lực xử lý của dịch vụ phụ thuộc. Khi một dependency đang quá tải, nhiều caller cùng retry liên tục có thể khiến tải tăng lên và làm hệ thống khó phục hồi hơn.

Retry không giới hạn có thể gây ra:

- Request giữ thread hoặc connection lâu hơn mức cần thiết.
- Hàng đợi request tăng, kéo theo timeout ở các tầng phía trên.
- Một sự cố ngắn biến thành retry storm (*bão retry*).
- Cùng một thao tác nghiệp vụ bị thực hiện nhiều lần nếu không có idempotency.
- Một yêu cầu hết thời gian hữu ích nhưng vẫn tiếp tục chạy ở tầng dưới.
- Nhiều lớp trong hệ thống cùng retry, làm số lần gọi thực tế tăng theo cấp số nhân.

Vì vậy, retry phải là một phần của chính sách độ tin cậy có giới hạn, không phải vòng lặp “thử đến khi được”.

## 2. Phân biệt số lần thử và số lần retry

Thuật ngữ cần được định nghĩa rõ vì cấu hình giữa thư viện và framework có thể khác nhau:

- **Attempt** là một lần thực hiện thao tác, bao gồm lần đầu.
- **Retry** là một lần thực hiện lại sau lần đầu.
- `maxAttempts = 3` thường có nghĩa tối đa ba attempt: lần đầu và hai lần retry.
- `maxRetries = 3` thường có nghĩa một lần đầu cộng thêm ba lần retry, tổng cộng bốn attempt.

Ví dụ:

```text
maxAttempts = 3

Attempt 1: thực hiện lần đầu -> lỗi tạm thời
Backoff
Attempt 2: retry lần thứ nhất -> lỗi tạm thời
Backoff
Attempt 3: retry lần thứ hai -> thành công

Tổng số attempt: 3
Tổng số retry:   2
```

Không nên đặt tên cấu hình chỉ là `retries` nếu chưa xác định nó đếm lần đầu hay chỉ đếm lần thực hiện lại. Hãy ghi rõ trong tài liệu, log và metric. Khi đổi thư viện retry, kiểm tra semantics của `maxAttempts`, `maxRetries`, `maxTries` hoặc cấu hình tương đương.

Số lần thử tối đa là một **trần**, không phải mục tiêu phải dùng hết. Nếu thao tác thành công ở attempt đầu, kết thúc ngay. Nếu lỗi không thể khắc phục bằng retry, cũng kết thúc ngay dù còn attempt.

## 3. Ngân sách thời gian tổng và timeout mỗi attempt

Hai giới hạn thời gian có vai trò khác nhau:

- **Attempt timeout:** thời gian tối đa dành cho một lần thực hiện. Nó ngăn một attempt bị treo quá lâu.
- **Overall deadline:** thời điểm muộn nhất mà toàn bộ thao tác phải kết thúc. Nó bao gồm tất cả attempt, backoff và overhead.

Ví dụ một API có ngân sách tổng `2.000 ms`, tối đa `3` attempt và timeout mỗi attempt tối đa `800 ms`:

```text
Tổng deadline: 2.000 ms tính từ lúc nhận request

Attempt 1: tối đa 800 ms
Backoff:   100 ms
Attempt 2: tối đa 800 ms
Backoff:   200 ms
Attempt 3: chỉ dùng phần thời gian còn lại
```

Không thể cộng cứng `800 + 100 + 800 + 200 + 800 = 2.700 ms` rồi xem đó là chính sách hai giây. Attempt cuối phải bị giới hạn bởi thời gian còn lại; nếu không còn đủ thời gian để thực hiện một attempt hữu ích, ứng dụng nên dừng và trả lỗi timeout/deadline.

### Tính thời gian còn lại

Tại thời điểm bắt đầu, xác định deadline một lần:

```text
deadline = startTime + totalBudget
```

Trước mỗi attempt hoặc lần chờ, tính:

```text
remaining = deadline - now
```

Sau đó:

```text
attemptTimeout = min(configuredAttemptTimeout, remaining)
```

Nếu cần chừa thời gian để trả response, rollback hoặc ghi log, hãy trừ phần dự phòng đó khỏi ngân sách có thể dùng cho attempt. Không bắt đầu attempt mới khi `remaining` đã hết hoặc không đủ cho thời gian tối thiểu cần thiết.

### Dùng đồng hồ monotonic

Để đo timeout trong một tiến trình, nên dùng đồng hồ monotonic, chẳng hạn `System.nanoTime()` trong Java. Đồng hồ này đo khoảng thời gian trôi qua và không bị thay đổi bởi việc đồng bộ giờ hệ thống hoặc chỉnh đồng hồ.

Không nên tính deadline nội bộ bằng cách so sánh `System.currentTimeMillis()` với thời gian bắt đầu nếu có thể tránh được; wall clock có thể nhảy tiến hoặc lùi. `Instant` phù hợp cho timestamp lịch và log, còn `System.nanoTime()` phù hợp cho đo thời lượng và deadline trong cùng tiến trình.

## 4. Backoff giữa các lần thử

Nếu lỗi có thể do tài nguyên đang bận, retry ngay lập tức thường khiến caller tiếp tục đụng vào cùng điểm nghẽn. **Backoff** là khoảng chờ trước lần thử tiếp theo.

Một cách phổ biến là exponential backoff (*lùi thời gian theo cấp số nhân*):

\[
d_n = \min(d_{max}, d_0 \times 2^{n-1})
\]

Trong đó:

- `d0` là thời gian chờ ban đầu.
- `n` là số thứ tự lần retry, bắt đầu từ `1`.
- `dmax` là mức chờ tối đa.

Ví dụ `d0 = 100 ms`, `dmax = 1.000 ms`:

| Lần retry | Backoff trước lần thử |
|---:|---:|
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1.000 ms (đã chạm mức trần) |
| 6 | 1.000 ms |

Backoff giúp giảm tần suất thử lại khi lỗi kéo dài. Nhưng nếu mọi client đều chờ đúng `100 ms`, rồi cùng retry tại cùng thời điểm, chúng vẫn có thể tạo thành một đợt tải đồng bộ.

## 5. Jitter để tránh retry đồng bộ

**Jitter** thêm độ ngẫu nhiên vào thời gian backoff để các client không cùng thử lại ở một thời điểm.

Một lựa chọn thường dùng là *full jitter*:

\[
d_n^{actual} \sim Uniform(0, \min(d_{max}, d_0 \times 2^{n-1}))
\]

Với backoff trần `400 ms`, mỗi client chọn một thời gian ngẫu nhiên từ `0` đến `400 ms`. Nhờ vậy, các request được phân tán thay vì cùng dồn vào một mốc.

Ví dụ minh họa:

```text
Không có jitter:
Client A: lỗi -> chờ 200 ms -> retry
Client B: lỗi -> chờ 200 ms -> retry
Client C: lỗi -> chờ 200 ms -> retry
                     ^ cùng thời điểm

Có full jitter:
Client A: lỗi -> chờ  35 ms -> retry
Client B: lỗi -> chờ 147 ms -> retry
Client C: lỗi -> chờ 192 ms -> retry
```

Một biến thể khác là *equal jitter*, giữ lại một phần thời gian chờ cố định và ngẫu nhiên hóa phần còn lại. Dù chọn biến thể nào, thời gian chờ thực tế vẫn phải nằm trong ngân sách deadline tổng.

Jitter không làm lỗi biến mất và cũng không thay thế giới hạn số lần thử. Nó chỉ giảm khả năng nhiều caller cùng tạo một đợt retry.

## 6. Quyết định lỗi nào được retry

Không phải lỗi nào cũng có thể cải thiện bằng việc thực hiện lại cùng thao tác. Cần phân loại lỗi dựa trên semantics của database, driver, dịch vụ và nghiệp vụ.

| Nhóm lỗi | Có nên retry? | Cách xử lý thường phù hợp |
|---|---|---|
| Deadlock victim | Thường có | Rollback transaction thất bại rồi retry toàn bộ transaction trong ngân sách còn lại. |
| Serialization failure | Thường có | Bắt đầu transaction mới, đọc snapshot mới và chạy lại logic. |
| Lock timeout | Tùy chính sách | Có thể retry nếu còn deadline và tải cho phép; tránh lặp nhanh vào cùng hàng nóng. |
| Connection reset trước khi gửi request | Có thể | Tạo kết nối mới và thử lại nếu thao tác an toàn. |
| Mất kết nối khi đang commit | Kết quả có thể chưa rõ | Kiểm tra trạng thái bằng idempotency key hoặc cơ chế tra cứu; không giả định transaction chắc chắn rollback. |
| Validation error | Không | Sửa đầu vào hoặc trả lỗi cho caller. |
| Unique constraint violation | Thường không | Xử lý như xung đột dữ liệu/nghiệp vụ, trừ khi đó là một cơ chế phối hợp được thiết kế riêng. |
| Foreign key hoặc CHECK violation | Không | Sửa dữ liệu hoặc quy trình nghiệp vụ. |
| Permission/authentication error | Không theo cách retry cùng thông tin | Làm mới credential hoặc trả lỗi quyền truy cập theo chính sách. |
| SQL syntax/schema error | Không | Sửa code hoặc schema. |
| Rate limit có `Retry-After` | Có thể | Chờ theo chỉ dẫn của server nếu còn deadline và policy cho phép. |

Danh sách trên là hướng dẫn, không phải quy tắc cho mọi hệ quản trị. Ví dụ, một lỗi unique có thể được dùng để phân xử cạnh tranh trong một quy trình insert-if-absent; nhưng việc xử lý thường là đọc trạng thái đã thắng và tiếp tục theo nghiệp vụ, không phải lặp lại cùng câu insert vô hạn.

### Retry cần dữ liệu đầu vào mới khi nào?

Với deadlock hoặc serialization failure, transaction đã bị hủy hoặc không còn hợp lệ. Phải mở transaction mới, đọc dữ liệu mới và tính lại các quyết định. Chỉ chạy lại câu SQL cuối cùng với những giá trị đã tính từ snapshot cũ có thể tái tạo lỗi logic.

Với lỗi mạng, cần phân biệt thao tác có chắc chắn chưa được gửi hay không. Nếu server có thể đã thực hiện request nhưng response bị mất, việc gửi lại có thể lặp tác dụng. Đây là vấn đề *ambiguous outcome* (kết quả không xác định), cần idempotency hoặc tra cứu trạng thái.

## 7. Retry toàn bộ transaction, không chỉ statement cuối

Một transaction thường có chuỗi phụ thuộc:

```text
BEGIN
  đọc số dư
  kiểm tra số dư đủ
  ghi ledger
  trừ tiền tài khoản A
  cộng tiền tài khoản B
COMMIT
```

Nếu deadlock hoặc serialization failure làm transaction bị hủy, các bước đã thực hiện trong transaction không còn là kết quả được commit. Retry đúng phải bắt đầu transaction mới và chạy lại toàn bộ logic, bao gồm đọc, kiểm tra và mọi cập nhật.

Không nên:

```text
T1 đọc balance = 100
T1 tính debit = 80
T1 bị deadlock và rollback

Retry riêng câu UPDATE với debit = 80
```

Trong thời gian giữa hai lần, giao dịch khác có thể đã thay đổi số dư. Giá trị `80` được tính từ snapshot cũ có thể không còn hợp lệ.

Nên:

```text
Rollback transaction cũ
BEGIN transaction mới
  đọc số dư hiện tại
  kiểm tra lại điều kiện
  tính lại số tiền được phép trừ
  ghi ledger và cập nhật tài khoản
COMMIT
```

Mỗi attempt phải có transaction boundary rõ ràng. Không giữ transaction hoặc connection đang lỗi trong lúc backoff; rollback và trả connection về pool trước khi ngủ.

## 8. Deadline propagation qua nhiều tầng

Một request có thể đi qua nhiều thành phần:

```text
Client
  -> API Gateway
      -> Order Service
          -> Inventory Service
              -> Database
```

Nếu mỗi tầng tự đặt timeout riêng mà không biết thời gian còn lại của request, tổng thời gian có thể vượt deadline của client. Ví dụ gateway cho `2 s`, order service lại chờ inventory `2 s`, rồi database tiếp tục chờ `2 s`; request có thể chạy lâu hơn nhiều so với thời gian caller còn chờ.

**Deadline propagation** truyền thời điểm hết hạn hoặc ngân sách còn lại xuống các tầng dưới. Mỗi tầng chỉ được dùng phần thời gian còn lại sau khi trừ overhead và phần dự phòng để trả kết quả.

Ví dụ:

| Thành phần | Ngân sách được cấp |
|---|---:|
| Toàn request | 2.000 ms |
| API xử lý và serialize response | Dự phòng 200 ms |
| Order Service | Tối đa 1.800 ms |
| Inventory Service | Tối đa 900 ms trong phần còn lại |
| Database attempt | Không vượt thời gian còn lại của Inventory Service |

Các con số chỉ minh họa cách phân bổ. Trong thực tế, không phải mọi nhánh đều chạy tuần tự; một số lời gọi song song cần được tính theo critical path và deadline chung.

Khi gọi dịch vụ ngoài, gửi timeout/deadline phù hợp qua protocol hoặc metadata được hệ thống hỗ trợ. Tầng dưới không nên bắt đầu công việc mới khi deadline đã hết. Nếu caller hủy request, tầng dưới nên hủy công việc có thể hủy để tránh tiếp tục tiêu thụ tài nguyên vô ích.

## 9. Ví dụ Java: retry có giới hạn attempt và deadline

Đoạn mã dưới đây minh họa cấu trúc tổng quát. `performOneAttempt` phải tự bảo đảm mỗi lần chạy nằm trong một transaction mới và timeout của lời gọi bên dưới được cấu hình theo `attemptTimeout`.

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryPolicy {
    private RetryPolicy() {}

    public static <T> T execute(
            int maxAttempts,
            Duration totalBudget,
            Duration perAttemptTimeout,
            Duration initialBackoff,
            Duration maxBackoff,
            RetryableOperation<T> operation) throws Exception {

        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be >= 1");
        }

        long started = System.nanoTime();
        long budgetNanos = totalBudget.toNanos();
        long deadline = started + budgetNanos;

        Exception lastFailure = null;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) {
                throw new RetryDeadlineExceededException(lastFailure);
            }

            long attemptNanos = Math.min(
                    perAttemptTimeout.toNanos(), remaining);

            try {
                return operation.run(attempt, Duration.ofNanos(attemptNanos));
            } catch (Exception ex) {
                lastFailure = ex;

                if (!isRetryable(ex) || attempt == maxAttempts) {
                    throw ex;
                }

                remaining = deadline - System.nanoTime();
                if (remaining <= 0) {
                    throw new RetryDeadlineExceededException(ex);
                }

                long cap = exponentialCapNanos(
                        initialBackoff.toNanos(),
                        maxBackoff.toNanos(),
                        attempt);
                long delay = ThreadLocalRandom.current().nextLong(cap + 1);

                if (delay >= remaining) {
                    throw new RetryDeadlineExceededException(ex);
                }

                try {
                    long millis = delay / 1_000_000;
                    int nanos = (int) (delay % 1_000_000);
                    Thread.sleep(millis, nanos);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw interrupted;
                }
            }
        }

        throw new RetryDeadlineExceededException(lastFailure);
    }

    private static long exponentialCapNanos(
            long initial, long maximum, int retryNumber) {
        long cap = initial;
        for (int i = 1; i < retryNumber && cap < maximum; i++) {
            if (cap > maximum / 2) {
                return maximum;
            }
            cap *= 2;
        }
        return Math.min(cap, maximum);
    }

    private static boolean isRetryable(Exception ex) {
        // Thay bằng bộ phân loại lỗi cụ thể của database/driver.
        return ex instanceof TransientDatabaseException;
    }

    @FunctionalInterface
    public interface RetryableOperation<T> {
        T run(int attempt, Duration timeout) throws Exception;
    }
}
```

Đây là khung minh họa, không phải một thư viện retry hoàn chỉnh. Trong mã production cần bổ sung các kiểu exception, cách truyền timeout xuống JDBC/HTTP, xử lý trường hợp `cap` bằng `Long.MAX_VALUE`, reserve thời gian để cleanup/response và chính sách khi operation không hỗ trợ cancellation. `operation.run` phải thực sự tôn trọng timeout được truyền vào; chỉ tính `attemptNanos` trong vòng lặp không thể tự dừng một JDBC call hoặc HTTP request bị treo.

Một điểm quan trọng trong ví dụ là `maxAttempts` bao gồm lần đầu. `attempt == 1` là lần thực hiện ban đầu; sau lỗi ở attempt 1, `attempt` kế tiếp mới là retry thứ nhất. Backoff chỉ xảy ra giữa hai attempt, không xảy ra sau attempt cuối.

## 10. Thiết kế transaction boundary khi dùng Java và Spring

Với Spring, cần bảo đảm mỗi lần retry chạy trong một transaction mới. Nếu annotation `@Transactional` bao quanh toàn bộ vòng lặp, các lần thử có thể dùng chung transaction hoặc persistence context đã bị đánh dấu rollback-only, tùy cấu trúc proxy và cách gọi.

Một cấu trúc thường dễ hiểu là đặt một lần thực hiện transaction trong bean/service riêng, còn vòng retry nằm ở lớp điều phối:

```java
public Result processWithRetry(Command command) {
    return retryPolicy.execute(() -> transactionWorker.processOnce(command));
}
```

```java
@Service
public class TransactionWorker {
    @Transactional
    public Result processOnce(Command command) {
        // Đọc dữ liệu mới, kiểm tra lại bất biến,
        // ghi toàn bộ thay đổi trong một transaction.
        return ...;
    }
}
```

Hai bean tách biệt giúp lời gọi đi qua Spring proxy, tạo transaction mới cho mỗi lần `processOnce` theo propagation đã cấu hình. Nếu gọi một method `@Transactional` khác bằng `this.method()` trong cùng bean, self-invocation có thể bỏ qua proxy và không tạo ranh giới transaction như mong đợi.

Nếu transaction thất bại, phải để transaction kết thúc/rollback trước khi backoff. Không ngủ trong khi đang giữ connection hoặc khóa. Với yêu cầu rõ ràng cần `REQUIRES_NEW`, hãy kiểm tra tác động lên transaction bên ngoài và connection pool; không thêm propagation chỉ để làm lỗi biến mất.

## 11. Idempotency và kết quả commit không xác định

Giới hạn attempt và deadline không đủ để bảo đảm thao tác an toàn khi gửi lại. Cần xem xét điều gì xảy ra nếu server đã thực hiện thao tác nhưng response bị mất.

Ví dụ:

```text
Client gửi yêu cầu tạo payment
Server ghi payment và COMMIT thành công
Kết nối bị đứt trước khi response tới client
Client không biết payment đã được tạo hay chưa
Client gửi lại yêu cầu
```

Nếu request thứ hai tạo một payment mới, khách hàng có thể bị tính tiền hai lần. Đây không phải trường hợp đơn giản của transaction rollback; kết quả commit của request đầu đã không xác định đối với caller.

Một cách xử lý là **idempotency key**. Client tạo một khóa ổn định cho một ý định nghiệp vụ và gửi lại cùng khóa trong các lần retry. Server lưu khóa cùng kết quả thao tác trong transaction. Nếu nhận lại cùng khóa, server trả kết quả đã lưu thay vì thực hiện thao tác lần nữa.

Ví dụ cấu trúc:

```sql
CREATE TABLE idempotency_records (
    idempotency_key VARCHAR(100) PRIMARY KEY,
    request_hash VARCHAR(128) NOT NULL,
    response_body TEXT,
    status VARCHAR(20) NOT NULL
);
```

Server phải bảo đảm việc claim key, thực hiện thay đổi nghiệp vụ và lưu kết quả được phối hợp transactionally. Nếu cùng key được gửi với payload khác, không nên âm thầm trả kết quả cũ hoặc thực hiện request mới; cần báo lỗi sử dụng key không nhất quán.

Idempotency key không làm mọi thao tác tự động idempotent. Nó cần phạm vi duy nhất, thời gian lưu, xử lý request đang chạy và cách phục hồi nếu tiến trình chết giữa chừng. Với tác dụng phụ bên ngoài database, cần phối hợp outbox hoặc cơ chế idempotency của dịch vụ nhận.

## 12. Không để retry ở nhiều tầng nhân số lần gọi

Một hệ thống có thể có retry trong HTTP client, service, repository và driver. Nếu mỗi tầng cho phép ba attempt độc lập, số lần gọi thực tế có thể nhân lên.

Ví dụ ba tầng cùng cho tối đa `3` attempt:

```text
API retry:       tối đa 3 lần gọi Order Service
Order retry:     mỗi lần tối đa 3 lần gọi Inventory
Inventory retry: mỗi lần tối đa 3 lần gọi Database

Số lần gọi database tệ nhất: 3 × 3 × 3 = 27
```

Đây là cách retry amplification làm tải tăng mạnh. Nên chọn một tầng sở hữu retry cho một lỗi cụ thể, truyền deadline xuống dưới và để các tầng còn lại trả lỗi rõ ràng. Có thể có retry ở tầng thấp cho lỗi kết nối rất hẹp và retry nghiệp vụ ở tầng cao, nhưng phải tính tổng ngân sách và số lần gọi kết hợp.

Đừng bọc một transaction đã có retry nội bộ bằng một retry chung không phân biệt lỗi. Nếu tầng dưới đã dùng hết ngân sách và trả lỗi, tầng trên retry lại có thể vượt deadline và làm nhân tải.

## 13. Retry budget theo thời gian và theo tải

Ngoài giới hạn từng request, hệ thống lớn có thể cần một **retry budget** theo tỷ lệ hoặc cửa sổ thời gian. Ví dụ, chỉ cho phép một tỷ lệ nhỏ số request là retry trong một phút. Khi ngân sách retry cạn, request mới trả lỗi nhanh hoặc dùng fallback thay vì tiếp tục tạo tải.

Phân biệt:

- **Per-request attempt limit:** giới hạn số lần thử của một request.
- **Per-request deadline:** giới hạn tổng thời gian của request.
- **Service retry budget:** giới hạn tổng lượng retry mà một service được phép tạo trong một khoảng thời gian.
- **Rate limit/concurrency limit:** giới hạn tốc độ hoặc số thao tác đồng thời, áp dụng cho cả request đầu và retry theo chính sách.

Retry budget theo service giúp ngăn một dependency lỗi kéo cả hệ thống vào retry storm. Ngưỡng nên dựa trên baseline và SLO, có metric theo dõi và được điều chỉnh bằng dữ liệu thực tế.

## 14. Circuit breaker khác retry như thế nào?

Retry giả định lỗi có thể tạm thời và thử lại sau khi chờ. **Circuit breaker** theo dõi tỷ lệ lỗi hoặc timeout của dependency và tạm thời ngăn lời gọi mới khi dependency có vẻ đang hỏng.

Các trạng thái thường gặp:

- `CLOSED`: cho phép request đi qua và theo dõi kết quả.
- `OPEN`: từ chối nhanh hoặc dùng fallback trong một khoảng thời gian, tránh tiếp tục gọi dependency đang lỗi.
- `HALF_OPEN`: cho phép một số probe giới hạn để kiểm tra dependency đã phục hồi chưa.

Circuit breaker không thay thế retry. Một request có thể retry một lỗi tạm thời trong khi breaker vẫn `CLOSED`. Nếu lỗi kéo dài, breaker có thể mở và ngăn các request tiếp tục thử. Cần phối hợp deadline, retry budget và breaker để không tạo hàng đợi quá lớn.

Không nên retry khi breaker đang `OPEN`; lời gọi đó sẽ bị từ chối ngay và chỉ tiêu thụ thêm thời gian cùng tài nguyên ở caller.

## 15. Quan sát và ghi log retry

Retry có thể che giấu lỗi tạm thời nếu chỉ ghi nhận kết quả cuối. Cần theo dõi cả số lần thử và thời gian đã tiêu thụ.

Các metric hữu ích:

- Số request kết thúc thành công ở attempt 1, 2, 3...
- Tổng số retry theo dependency và loại lỗi.
- Tỷ lệ retry thành công so với thất bại.
- Thời gian backoff thực tế.
- Số request hết deadline trước khi thử lại.
- Số request dừng do đạt `maxAttempts`.
- Số request bị từ chối bởi retry budget hoặc circuit breaker.
- Số deadlock, serialization failure, lock timeout và connection failure.
- Thời gian transaction và thời gian chờ khóa.

Log nên chứa `requestId`/trace ID, attempt number, max attempts, lỗi phân loại, thời gian còn lại, backoff đã chọn và dependency liên quan. Tránh ghi payload nhạy cảm hoặc thông tin xác thực.

Khi quan sát, tỷ lệ thành công cuối cùng cao không đồng nghĩa hệ thống khỏe. Nếu hầu hết request đều thành công sau ba lần retry, dependency có thể đang quá tải hoặc contention cao. Retry che bớt lỗi ở bề mặt nhưng vẫn làm tăng latency và chi phí.

## 16. Cách thiết kế chính sách retry cho một thao tác

Trước khi bật retry, hãy xác định:

1. **Thao tác có thể thực hiện lại an toàn không?** Có thể cần idempotency key, unique request ID hoặc transaction được thiết kế lại.
2. **Những lỗi nào là tạm thời?** Phân loại deadlock, serialization, lock timeout, lỗi mạng và lỗi nghiệp vụ riêng.
3. **Retry ở tầng nào?** Chọn một chủ sở hữu chính để tránh retry amplification.
4. **Số attempt tối đa là bao nhiêu?** Nói rõ có bao gồm lần đầu hay không.
5. **Ngân sách thời gian tổng là bao nhiêu?** Phù hợp SLA của caller và dependency.
6. **Timeout mỗi attempt là bao nhiêu?** Không vượt thời gian còn lại của deadline.
7. **Backoff và jitter ra sao?** Có mức ban đầu, mức trần và phân tán thời điểm retry.
8. **Có đủ thời gian để thử lại không?** Không bắt đầu attempt vô ích khi deadline sắp hết.
9. **Transaction có được tạo mới mỗi attempt không?** Rollback trước backoff, đọc lại dữ liệu và tính lại logic.
10. **Khi kết quả commit không rõ thì làm gì?** Tra cứu bằng idempotency key hoặc trạng thái nghiệp vụ.
11. **Retry budget và circuit breaker có cần thiết không?** Đặc biệt khi dependency dùng chung có thể quá tải.
12. **Metric nào chứng minh chính sách có ích?** Theo dõi latency, attempt distribution, retry success và lỗi cuối.

Một chính sách tốt phải dừng ở một trong ba kết quả rõ ràng: thành công; thất bại không retry được; hoặc hết attempt/deadline/retry budget. Mọi nhánh đều phải giải phóng transaction, connection và tài nguyên đang giữ.

## 17. Kết luận

Giới hạn số lần thử ngăn một thao tác lặp vô hạn; ngân sách thời gian tổng bảo đảm tất cả attempt và backoff nằm trong thời gian caller còn chấp nhận. Hai giới hạn phải được áp dụng cùng nhau. Trước mỗi attempt, tính thời gian còn lại và giới hạn timeout của attempt; giữa các attempt, dùng exponential backoff có jitter nếu loại lỗi và deadline cho phép.

Chỉ retry lỗi tạm thời và thực hiện lại toàn bộ transaction bằng transaction mới khi transaction cũ đã bị hủy. Retry cần an toàn với idempotency, đặc biệt khi kết quả commit không rõ. Hãy tránh retry ở nhiều tầng không phối hợp, cân nhắc retry budget và circuit breaker khi dependency quá tải, đồng thời đo attempt, latency và tỷ lệ retry thành công. Mục tiêu là phục hồi trong một khoảng thời gian có kiểm soát, rồi trả kết quả rõ ràng khi thao tác không thể hoàn thành.
