# BackOffPolicy khi kết nối thất bại trong Spring Integration Adapters

> **Chương:** Reliability  
> **Bài học:** BackOffPolicy khi kết nối thất bại  
> **Phạm vi:** Kết nối các hệ thống ngoài bằng **Spring Integration** thông qua inbound/outbound adapter, gateway, poller và MessageChannel. Bài áp dụng cho luồng **File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu**, đồng thời giải thích hợp đồng message, lỗi kết nối, retry, xác nhận xử lý và vòng đời kết nối.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **RetryPolicy** quyết định *có được thử lại hay không* với **BackOffPolicy** quyết định *chờ bao lâu trước lần thử lại tiếp theo*.
2. Giải thích cách **RetryTemplate, RetryContext, BackOffContext, RetryCallback, RecoveryCallback** và **RequestHandlerRetryAdvice** phối hợp trong Spring Integration.
3. Lựa chọn **no backoff, fixed, exponential, randomized/jitter** theo loại lỗi, tải hệ thống, thời gian khôi phục và đặc tính nguồn/đích.
4. Tính số **attempts**, các khoảng nghỉ và tổng **latency budget**; kết hợp connection/read timeout, deadline, rate limit, circuit breaker và bulkhead.
5. Phân loại lỗi kết nối tạm thời, lỗi xác thực/phân quyền, lỗi dữ liệu và **unknown outcome** để tránh retry vô nghĩa hoặc gây hiệu ứng nghiệp vụ trùng.
6. Xác định đúng ranh giới retry đối với **HTTP outbound gateway, SFTP, File inbound poller, JMS/AMQP, Kafka và JDBC**.
7. Thiết kế **idempotency, acknowledgement, transaction, DLQ/parking, delayed retry** để không mất message khi retry in-process đã hết ngân sách.
8. Xây dựng metrics, cảnh báo và kiểm thử tình huống kết nối lỗi, quá tải, restart, gián đoạn dài, poison message và khôi phục.

## 2. Vì sao cần backoff khi kết nối thất bại?

Một Spring Integration Flow có thể đọc file đơn hàng trên SFTP, chuyển thành message, gọi một HTTP API của đối tác, lưu kết quả trong database rồi gửi thông báo qua AMQP.

~~~text
SFTP inbound adapter
   -> MessageChannel
   -> transformer / validator
   -> outbound HTTP gateway
   -> JDBC status update
   -> outbound AMQP adapter
~~~

Khi outbound HTTP gateway không kết nối được do đối tác đang quá tải, một cách xử lý ngây thơ là thử lại ngay lập tức trong vòng lặp.

~~~text
08:00:00.000  Kết nối thất bại
08:00:00.005  Thử lại
08:00:00.010  Thử lại
08:00:00.015  Thử lại
...
~~~

Nếu 1.000 instance cùng làm như vậy, hệ thống đích nhận một **làn sóng request bổ sung** đúng lúc đang không khỏe. Cơ chế retry, vốn được xây để tăng độ tin cậy, có thể trở thành nguyên nhân khiến sự cố kéo dài.

**Backoff** tạo ra một khoảng nghỉ có chủ đích giữa các lần thử. Khoảng nghỉ có thể cố định hoặc tăng dần, đôi khi được ngẫu nhiên hóa để nhiều client không tái thử cùng thời điểm.

**BackOffPolicy không làm một request trở nên idempotent, không tự xác định exception nào đáng retry, cũng không bảo đảm hệ thống bên ngoài đã hay chưa xử lý request trước khi trả timeout.**

Câu hỏi quan trọng không phải “nên chờ 500 ms hay 1.000 ms?”, mà là:

> “Lỗi này có khả năng phục hồi khi thử lại không; nếu có, **chúng ta nên thử lại lúc nào, bao nhiêu lần và liệu việc thực hiện lại có an toàn?**”

### Một tình huống thực tế

- Lúc 09:00, 300 message phải gọi API tạo hóa đơn.
- Partner API trả **HTTP 503** trong 20 giây.
- Nếu tất cả client retry ngay, hệ thống dễ bị đẩy vào trạng thái quá tải lặp lại.
- Nếu tất cả client dùng **fixed backoff chính xác 1 giây**, chúng vẫn có thể đồng loạt retry ở giây tiếp theo.
- Nếu dùng **exponential backoff có jitter**, các lần thử được dàn ra trong thời gian nhất định.
- Nếu partner down hàng giờ, **không nên giữ hàng trăm worker thread ngủ chờ**; cần bền vững hóa message và dùng delayed retry hoặc một hàng chờ phù hợp.

## 3. Phân biệt RetryPolicy, BackOffPolicy và recovery

Trong Spring Retry, các thành phần có trách nhiệm khác nhau.

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **RetryTemplate** | Điều phối vòng đời nhiều attempt | Chạy handler tối đa 4 lần theo cấu hình |
| **RetryPolicy** | Có còn được retry không? | Tối đa 4 attempts; chỉ với lỗi transient |
| **BackOffPolicy** | Đợi bao lâu trước attempt tiếp theo? | 250 ms, 500 ms, 1.000 ms |
| **RetryCallback** | Công việc nào được thực hiện lại? | Gọi HTTP GET của đối tác |
| **RetryContext** | Chuỗi retry đang ở attempt nào, lỗi gần nhất là gì? | retryCount và lastThrowable |
| **BackOffContext** | Trạng thái riêng của chiến lược chờ | Khoảng nghỉ đang tăng theo cấp số nhân |
| **RecoveryCallback** | Hết retry thì xử lý ra sao? | Đưa vào parking, thông báo lỗi hoặc rethrow |
| **RequestHandlerRetryAdvice** | Spring Integration dùng retry ở đâu? | Bọc một message handler được gắn advice |

Một BackOffPolicy không quyết định request nên được gọi lại nếu **RetryPolicy không còn cho phép**. Khi callback thành công, không cần thêm backoff. Khi thất bại không thuộc loại retryable, chính sách có thể dừng ngay mà không đợi.

### Phân biệt attempt và retry

Nếu RetryPolicy đặt **maxAttempts = 4**:

| Lần thực thi | Cách gọi | Có backoff trước lần này không? |
|---|---|---|
| 1 | Initial attempt | Không |
| 2 | Retry thứ nhất | Có, sau lỗi lần 1 |
| 3 | Retry thứ hai | Có, sau lỗi lần 2 |
| 4 | Retry thứ ba | Có, sau lỗi lần 3 |
| Sau lần 4 vẫn lỗi | Exhausted/recovery | Không mở attempt thứ năm |

Do đó **4 attempts = 1 attempt ban đầu + tối đa 3 retries**, không phải 4 lần thử lại sau lần đầu.

## 4. Vòng đời BackOffPolicy bên trong RetryTemplate

Trong API Spring Retry, **BackOffPolicy.start(RetryContext)** tạo **BackOffContext** cho một chuỗi retry, và **BackOffPolicy.backOff(BackOffContext)** thực thi chiến lược nghỉ trước lần thử tiếp theo.

Cơ chế này giúp một chuỗi retry có trạng thái backoff riêng, trong khi policy object có thể được chia sẻ theo cách triển khai phù hợp. Nó **không biến thời gian ngủ hoặc RetryContext thành dữ liệu bền vững qua restart**.

~~~mermaid
flowchart TD
    A["Message tới handler"] --> B["RetryTemplate mở RetryContext"]
    B --> C["BackOffPolicy.start: tạo BackOffContext"]
    C --> D{"RetryPolicy cho phép attempt?"}
    D -->|"Có"| E["Gọi handler / RetryCallback"]
    E -->|"Thành công"| F["Kết thúc, trả kết quả"]
    E -->|"Exception"| G["Phân loại lỗi, cập nhật RetryContext"]
    G --> H{"Có thể retry và còn budget?"}
    H -->|"Có"| I["BackOffPolicy.backOff"]
    I --> D
    H -->|"Không"| J{"RecoveryCallback?"}
    J -->|"Có"| K["Recovery có chủ đích"]
    J -->|"Không"| L["Trả/ném lỗi cho caller, container"]
    K --> M["Kết thúc chuỗi retry"]
    L --> M
~~~

Sơ đồ mang tính khái niệm; việc phân loại exception và quyết định exhaustion do RetryPolicy, RetryTemplate điều phối. **Backoff chỉ điều chỉnh thời điểm**, không bảo đảm retry sẽ thành công.

### Những biến trạng thái thường cần quan sát

- Số attempts đã thực hiện, không nhầm với số lần retry.
- Lỗi gần nhất và lớp lỗi đã phân loại.
- Khoảng chờ đã áp dụng trước attempt tiếp theo.
- Tổng thời gian đã dùng.
- Deadline còn lại của nghiệp vụ/request.
- Idempotency key và event ID ổn định.
- Kết quả cuối cùng: SUCCESS, EXHAUSTED, CANCELLED, PARKED hoặc DLQ.

## 5. Các loại BackOffPolicy phổ biến

Spring Retry cung cấp các chiến lược backoff phù hợp những nhu cầu khác nhau. Tên lớp và khả năng cấu hình cần đối chiếu phiên bản dependency của dự án khi áp dụng.

| Loại | Ý tưởng | Khi phù hợp | Rủi ro |
|---|---|---|---|
| **NoBackOffPolicy** | Không chờ giữa attempts | Một số trường hợp nội bộ rất rẻ, biết chắc sẽ phục hồi ngay | Retry storm, CPU/request burst |
| **FixedBackOffPolicy** | Đợi một khoảng cố định mỗi lần | Lỗi ngắn, tải thấp, tần suất ổn định | Nhiều client đồng bộ thời điểm retry |
| **ExponentialBackOffPolicy** | Khoảng chờ tăng theo multiplier, bị chặn bởi maxInterval | Remote service quá tải, mất kết nối ngắn | Nếu không jitter, nhiều client vẫn đồng bộ |
| **ExponentialRandomBackOffPolicy** | Dựa trên exponential backoff và thêm ngẫu nhiên hóa theo ngữ nghĩa của implementation | Nhiều instance cùng gọi đối tác | Cần hiểu phân phối/giới hạn thực tế |
| **UniformRandomBackOffPolicy** | Chọn khoảng chờ ngẫu nhiên trong miền cấu hình | Muốn rải attempts nhưng không nhất thiết tăng dần | Phải chọn min/max hợp lý |

### 5.1. NoBackOffPolicy

Không có khoảng chờ giữa lần thất bại và lần thử tiếp theo. Có thể hữu ích với lỗi xung đột cực ngắn trong một thao tác nội bộ rẻ, nhưng **không nên là mặc định cho network failure**.

Ngay cả khi số attempts được giới hạn, 500 client cùng thử lại 3 lần liên tiếp có thể nhân tải đột ngột lên dịch vụ đang không khỏe.

### 5.2. FixedBackOffPolicy

Nếu khoảng nghỉ là 500 ms và có tối đa 4 attempts:

~~~text
Attempt 1 --fail--> sleep 500 ms
Attempt 2 --fail--> sleep 500 ms
Attempt 3 --fail--> sleep 500 ms
Attempt 4 --fail--> exhausted
~~~

Tổng thời gian chờ là **3 × 500 ms = 1.500 ms** nếu cả bốn lần đều lỗi và RetryPolicy vẫn cho phép retry.

Ưu điểm: đơn giản, dễ dự toán. Hạn chế: nhiều client nhận lỗi cùng thời điểm dễ **thức dậy cùng nhịp**.

### 5.3. ExponentialBackOffPolicy

Với initialInterval = 250 ms, multiplier = 2, maxInterval = 2.000 ms và 6 attempts, dãy nghỉ xấp xỉ:

~~~text
Attempt 1 --fail-->  250 ms
Attempt 2 --fail-->  500 ms
Attempt 3 --fail--> 1000 ms
Attempt 4 --fail--> 2000 ms
Attempt 5 --fail--> 2000 ms (chạm trần)
Attempt 6 --fail--> exhausted
~~~

Tổng nghỉ = **250 + 500 + 1.000 + 2.000 + 2.000 = 5.750 ms**.

Công thức tư duy với khoảng nghỉ thứ i (i bắt đầu từ 1):

**delay(i) = min(maxInterval, initialInterval × multiplier^(i−1)).**

Công thức mô tả ý tưởng của exponential backoff, chưa tính làm tròn, giới hạn riêng hay randomization của implementation. **Khoảng nghỉ chỉ xảy ra giữa các attempts**, nên với N attempts nhiều nhất N−1 lần nghỉ.

### 5.4. Randomized backoff và jitter

Jitter là thành phần ngẫu nhiên được đưa vào khoảng nghỉ để giảm **thundering herd**, khi hàng trăm client retry đồng thời sau một sự cố chung.

Ví dụ hai worker cùng cần retry một API:

~~~text
Không jitter:
  Worker A: 250 ms -> 500 ms -> 1000 ms
  Worker B: 250 ms -> 500 ms -> 1000 ms
  Request thường tiếp tục trùng thời điểm.

Có jitter (minh họa):
  Worker A: 210 ms -> 670 ms -> 940 ms
  Worker B: 330 ms -> 450 ms -> 1220 ms
  Request được phân tán hơn.
~~~

Các con số có jitter trong bảng chỉ để minh họa, **không mô tả chính xác công thức của một lớp Spring Retry cụ thể**. Các thuật toán full jitter, equal jitter, decorrelated jitter hoặc ngẫu nhiên hóa exponential có phân phối khác nhau. Cần dựa vào contract của thư viện và test cấu hình triển khai.

**Không nên biến jitter thành độ trễ không có giới hạn**; vẫn cần max interval, max attempts và tổng deadline.

## 6. Tính toán ngân sách thời gian khi kết nối lỗi

Một lỗi lớn là chỉ cấu hình BackOffPolicy mà quên **mỗi attempt có thể tự chờ timeout rất lâu**.

Giả sử:

- maxAttempts = 5;
- mỗi HTTP attempt có timeout tối đa 1,5 giây;
- exponential backoff lần lượt 250, 500, 1.000, 2.000 ms;
- không có jitter.

Tổng thời gian xấp xỉ trong trường hợp cả năm lần timeout:

**5 × 1,5 s + (0,25 + 0,5 + 1 + 2) s = 11,25 giây**.

Chưa kể thời gian tạo kết nối, TLS handshake, scheduling, dispatch, queue và xử lý dữ liệu. Nếu caller của HTTP inbound gateway chỉ đợi 5 giây, retry policy như vậy sẽ **vượt ngân sách request**.

### Công thức tổng quát

Với N attempts:

**T_total ≈ Σ T_attempt(i) + Σ delay(i),** trong đó tổng delay có nhiều nhất N−1 phần tử.

Để an toàn cần:

1. Connection timeout riêng cho việc thiết lập kết nối.
2. Read/response timeout cho lời gọi đang chờ.
3. **Total deadline** cho hành động nghiệp vụ hoặc request.
4. Max attempts theo loại lỗi/operation.
5. Backoff có trần và randomization phù hợp.
6. Ngân sách chung của các tầng (client, gateway, adapter, broker).
7. Cách hủy hoặc dừng khi caller không còn chờ và operation không nên tiếp tục.

**BackOffPolicy không tự giới hạn toàn bộ thời gian của một lời gọi mạng bị treo.** Nếu thiếu network timeout, có thể không bao giờ tới bước backoff.

### Gợi ý phân tầng thời gian

| Tầng | Ví dụ mục tiêu | Ghi chú |
|---|---|---|
| TCP connect | Một hạn nhỏ, theo mạng và đối tác | Không đồng nhất với read timeout |
| HTTP response | Phù hợp API cụ thể | Cân nhắc thao tác đắt và kết quả chưa rõ |
| Handler attempts | 2–4 attempts minh họa | Không phải chuẩn cho mọi hệ thống |
| In-process backoff | Hàng trăm ms đến vài giây khi hợp lý | Phụ thuộc SLA và worker concurrency |
| Durable delayed retry | Phút hoặc giờ khi sự cố kéo dài | Có trạng thái lưu bền và giám sát |
| Business deadline | Thời điểm nghiệp vụ không còn cần thao tác | Không tiếp tục gửi tác vụ đã hết hiệu lực |

## 7. Phân loại lỗi trước khi chọn khoảng chờ

Không nên đưa tất cả exception qua cùng một BackOffPolicy. **Retryability** phụ thuộc cả loại lỗi và độ an toàn khi lặp lại operation.

| Lỗi/triệu chứng | Có nên retry? | Backoff tham khảo | Điều cần xác minh |
|---|---|---|---|
| Connection reset, network unreachable tạm thời | Có thể | Exponential + jitter | Outcome của request trước có rõ không? |
| Connect timeout | Có thể | Giới hạn, tăng dần | DNS, firewall, giới hạn số kết nối |
| Read timeout sau HTTP POST | Chưa chắc | Không retry mù | Đích có thể đã xử lý; cần idempotency/đối soát |
| HTTP 429 | Thường có điều kiện | Retry-After/rate-limit-aware | Quota, loại request, hạn deadline |
| HTTP 503 | Có thể | Exponential + jitter | Tránh áp lực khi partner quá tải |
| HTTP 502/504 | Có thể nhưng không chắc an toàn | Có budget | Upstream có thể đã commit side effect |
| HTTP 400, invalid schema | Thường không | Không backoff | Sửa payload hoặc contract |
| HTTP 401/403 | Thường không retry cùng credential | Không backoff | Refresh credential qua luồng hợp lệ, sửa quyền |
| SFTP authentication/host-key failure | Không retry cùng cấu hình | Không backoff vô hạn | Chứng thực và xác minh host đúng |
| SFTP/AMQP/JMS temporary connectivity | Có thể | Exponential + jitter, theo client | Session/failover/ack state |
| Kafka broker tạm không sẵn sàng | Tùy adapter/container | Backoff của error handler/container | Partition, commit, rebalance và version |
| JDBC deadlock/serialization conflict | Có thể với transaction mới phù hợp | Backoff ngắn có jitter | Rollback/recreate transaction |
| Unique constraint/validation failure | Thường không | Không | Xung đột dữ liệu hoặc duplicate cần phân loại |
| Disk full/permission denied | Thường không retry liên tục | Dừng/cảnh báo | Cần người hoặc hệ thống khắc phục |
| Poison message | Không với cùng payload | Không | Quarantine/DLQ, sửa dữ liệu |
| Service bị rate-limit kéo dài | Không giữ thread vô hạn | Durable delayed retry | Tuân thủ retry budget và tuổi message |

### Unknown outcome khác với transient error

**Transient** nghĩa là nguyên nhân có thể tự biến mất. **Unknown outcome** nghĩa là không biết thao tác trước đã có hiệu ứng hay chưa. Hai đặc tính này độc lập.

Ví dụ đối tác trả timeout sau khi ghi đơn hàng thành công. Lỗi mạng có thể tạm thời, nhưng gửi lại POST có thể **tạo hai đơn hàng**. Vì vậy ngoài RetryPolicy/BackOffPolicy, cần một trong các cơ chế:

- Idempotency key được đối tác hỗ trợ;
- Tra cứu trạng thái bằng business transaction ID;
- Upsert theo khóa nghiệp vụ;
- Transaction/outbox/inbox hoặc reconciliation;
- Manual review nếu không thể xác minh an toàn.

## 8. Ví dụ Java: cấu hình ExponentialRandomBackOffPolicy

Ví dụ sử dụng Spring Retry kết hợp một số exception từ Spring Web. Đây là **cấu hình minh họa**, cần đối chiếu phiên bản Spring Retry/Spring Integration/Spring Web và cách HTTP client ném hoặc bọc exception trong dự án.

~~~java
import java.util.HashMap;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.ExponentialRandomBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;

@Configuration
public class PartnerRetryConfig {

    @Bean
    public RetryTemplate partnerRetryTemplate() {
        Map<Class<? extends Throwable>, Boolean> retryable = new HashMap<>();

        // Ví dụ: phân loại dựa trên exception thực tế của HTTP client.
        retryable.put(ResourceAccessException.class, true);
        retryable.put(HttpClientErrorException.TooManyRequests.class, true);
        retryable.put(HttpServerErrorException.ServiceUnavailable.class, true);

        // 4 attempts TỔNG. Xét nguyên nhân bên trong wrapper khi phù hợp.
        // Exception khác: không retry theo cấu hình mẫu.
        SimpleRetryPolicy retryPolicy =
                new SimpleRetryPolicy(4, retryable, true, false);

        ExponentialRandomBackOffPolicy backOff =
                new ExponentialRandomBackOffPolicy();
        backOff.setInitialInterval(250L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(2_000L);

        RetryTemplate retryTemplate = new RetryTemplate();
        retryTemplate.setRetryPolicy(retryPolicy);
        retryTemplate.setBackOffPolicy(backOff);

        return retryTemplate;
    }
}
~~~

### Những giới hạn phải hiểu của ví dụ

- **ResourceAccessException** có thể bao gồm lỗi kết nối hoặc I/O; với HTTP POST có side effect, đánh dấu retryable trong bảng exception **chưa đủ** để chứng minh an toàn.
- **HttpClientErrorException.TooManyRequests** chỉ thể hiện status 429 được HTTP client diễn giải như exception đó; Retry-After cần xử lý riêng nếu muốn tôn trọng thời gian server yêu cầu.
- Một HTTP client hoặc endpoint có thể bọc lỗi trong **MessagingException** hoặc exception riêng; cần kiểm tra cause chain và các exception thực tế.
- **ExponentialRandomBackOffPolicy** thêm randomization nhưng không tự giới hạn số attempts; **SimpleRetryPolicy** chịu trách nhiệm về giới hạn đó.
- Không có **end-to-end deadline**, circuit breaker, rate limiter, persistent queue hoặc idempotency được cấu hình trong ví dụ.
- Nếu partner trả 500/502/504 nhưng không thuộc classifier, có thể không được retry; phải đưa ra lựa chọn dựa trên hợp đồng API thay vì tự mở rộng catch-all.
- Với response lỗi **không nên retry**, việc định nghĩa backoff không làm chúng được retry; phải xem RetryPolicy.

### Ví dụ fixed backoff khi môi trường nhỏ

~~~java
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

RetryTemplate template = new RetryTemplate();

SimpleRetryPolicy retryPolicy = new SimpleRetryPolicy(3);
FixedBackOffPolicy fixedBackOff = new FixedBackOffPolicy();
fixedBackOff.setBackOffPeriod(400L);

template.setRetryPolicy(retryPolicy);
template.setBackOffPolicy(fixedBackOff);

// 3 attempts tổng, tối đa 2 khoảng nghỉ x 400 ms.
// Ví dụ SimpleRetryPolicy(3) chưa giới hạn danh sách exception.
~~~

Ví dụ này để hiểu wiring, **không nên dùng cấu hình retry mọi exception một cách vô điều kiện** cho adapter production.

## 9. Gắn BackOffPolicy vào Spring Integration

Ở Spring Integration, cách thông dụng là cấu hình BackOffPolicy trên **RetryTemplate** rồi gắn RetryTemplate đó vào **RequestHandlerRetryAdvice** của endpoint.

### 9.1. Tạo RequestHandlerRetryAdvice

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class IntegrationAdviceConfig {

    @Bean
    public RequestHandlerRetryAdvice partnerRetryAdvice(
            RetryTemplate partnerRetryTemplate) {

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(partnerRetryTemplate);

        // Không nuốt lỗi ở đây. Khi exhausted, exception còn
        // phải được xử lý bởi caller / error flow / consumer container
        // theo ngữ nghĩa của nguồn.
        return advice;
    }
}
~~~

Nếu chọn RecoveryCallback riêng, phải phân biệt **recovery thành công** với **kết thúc do lỗi**. Một RecoveryCallback ghi log rồi trả bình thường có thể làm caller coi handler đã xử lý xong, ảnh hưởng tới ack/commit.

### 9.2. Chỉ retry một outbound HTTP gateway

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.integration.http.dsl.Http;

@Configuration
public class PartnerStatusFlow {

    @Bean
    IntegrationFlow partnerStatusIntegrationFlow(
            RequestHandlerRetryAdvice partnerRetryAdvice) {

        return IntegrationFlow.from("statusRequestChannel")
                .handle(
                    Http.outboundGateway(
                            "https://partner.example.invalid/api/status")
                        .httpMethod(HttpMethod.GET)
                        .expectedResponseType(String.class),
                    endpoint -> endpoint.advice(partnerRetryAdvice)
                )
                .channel("statusReplyChannel")
                .get();
    }
}
~~~

**GET** được dùng để tách vấn đề backoff khỏi một POST tạo nghiệp vụ. Domain example.invalid chỉ mang tính minh họa.

Trong flow này:

- **MessageChannel** nhận message.
- **Outbound HTTP gateway** gửi request đến partner.
- **RequestHandlerRetryAdvice** bao quanh invocation của handler được gắn advice.
- **RetryTemplate** quyết định thử lại; BackOffPolicy điều khiển khoảng chờ.
- Kết quả thành công được chuyển tới channel tiếp theo.
- Khi exhausted, lỗi theo đường exception/error handling đã cấu hình.

**Điều không xảy ra tự động:** retry advice **không** tự đọc lại file SFTP upstream, **không** retry mọi transformer trước endpoint, **không** quản lý offset Kafka và **không** bảo đảm một operation HTTP non-idempotent an toàn khi lặp lại.

### 9.3. Tại sao vị trí advice rất quan trọng?

~~~text
SFTP.inboundAdapter
    -> parse file
    -> transform record
    -> HTTP.outboundGateway [retry advice]
    -> JDBC.outboundAdapter
    -> AMQP.outboundAdapter
~~~

Nếu HTTP outbound gateway thất bại, advice thử lại **handler HTTP**. Nó không có nghĩa là toàn bộ các bước trước/sau được chạy lại.

Nếu đặt retry ở cấp service gọi cả HTTP + JDBC + AMQP, một lỗi AMQP phía cuối có thể làm lặp HTTP và DB — tức là **phạm vi retry sai**. Nên tách đơn vị nghiệp vụ hoặc áp dụng outbox và các state transition rõ.

## 10. BackOffPolicy và poller: hai cơ chế thời gian khác nhau

Spring Integration hỗ trợ **poller** để định kỳ lấy message từ MessageSource như File/SFTP/JDBC. Poller có **fixedDelay/fixedRate/cron hoặc trigger khác**, nhưng đó là **lịch kiểm tra nguồn**, không phải BackOffPolicy của RetryTemplate.

### Ví dụ

~~~text
Poller SFTP: mỗi 5 giây kiểm tra thư mục từ xa.
Lúc 10:00: SFTP server timeout.

Những cơ chế có thể tồn tại:
  A. Poller thử lại theo lịch kế tiếp lúc 10:00:05.
  B. Một thao tác SFTP riêng được bọc retry 3 attempts.
  C. Scheduler điều chỉnh lịch poll khi upstream down lâu.
~~~

**A, B và C không tương đương.** Nếu vừa có 3 attempts với backoff 2 giây trong mỗi poll, vừa poll mỗi 5 giây, lượng request đến SFTP có thể nhiều hơn dự kiến. Cần tính tổng các tầng và xác định ai chịu trách nhiệm reconnect.

### Đặc điểm của poller

- Khi poller không tìm thấy message, đó thường là trạng thái bình thường, **không phải exception để RetryTemplate xử lý**.
- Nếu poller lấy file rồi downstream lỗi, lần poll kế tiếp **không bảo đảm lấy lại cùng file** nếu accept-once filter hoặc metadata store đã ghi nhận nó.
- Một poller có concurrency có thể chạy nhiều hoạt động song song; backoff giữ worker thread có thể làm ảnh hưởng tiến độ.
- Với nguồn bị lỗi kéo dài, điều chỉnh **polling schedule** hoặc tạm dừng adapter có thể hiệu quả hơn giữ thread trong RetryTemplate.
- Khi khôi phục, không nên cho tất cả poller trên nhiều instance thức dậy cùng lúc và đẩy tải quá lớn.

**Backoff của retry handler khác với lịch poll và khác với retry/reconnect nội bộ của client library.**

## 11. Backoff cho File adapter: không retry nội dung hỏng như lỗi kết nối

File system có đặc điểm khác remote API: một file có thể **chưa được ghi xong**, mất quyền đọc hoặc chứa nội dung không hợp lệ.

### Inbound File

| Tình huống | Chiến lược | Vai trò của backoff |
|---|---|---|
| File chưa hoàn thành upload | Dùng tên tạm, marker ready, filter phù hợp | Đợi lần poll tiếp theo; không retry parse liên tục |
| Transient filesystem I/O | Retry có giới hạn nếu an toàn | Fixed/exponential ngắn tùy tải |
| Permission denied | Sửa quyền/ACL | Backoff đơn thuần không giải quyết |
| JSON/CSV invalid | Quarantine với reason code | Không retry cùng payload |
| Downstream HTTP lỗi sau khi file được nhận | Xử lý record bền vững, retry đúng handler | Backoff phía outbound, không dựa vào poll lại |
| File đã move/archive nhầm | Recovery qua staging/backup | Retry chỉ sau khi xác minh state |

### Hợp đồng file hoàn chỉnh

Một quy trình phù hợp:

1. Đối tác ghi **orders-45.part**.
2. Sau khi hoàn tất, publish thành **orders-45.ready** theo cơ chế có bảo đảm phù hợp.
3. File inbound adapter chỉ nhận tập file đã ready.
4. Ghi một **business event ID ổn định** cho mỗi record hoặc file.
5. Parse/validate; invalid vào quarantine.
6. Downstream retry theo operation và budget riêng.
7. Sau khi hoàn tất hoặc bảo toàn lỗi, archive theo trạng thái nghiệp vụ.

**Không nên biến file accept-once filter thành cơ chế bảo đảm exactly-once end-to-end**: worker restart, metadata store không bền hoặc replay sẽ thay đổi hành vi. Idempotency ở tầng nghiệp vụ vẫn cần thiết.

### Outbound File

Nếu ghi file gặp lỗi I/O giữa chừng, retry trực tiếp cùng đích có thể tạo file dở hoặc ghi đè. Nên dùng **temporary output + publish/rename khi khả năng filesystem cho phép**, và tên file gắn với event ID. Backoff chỉ giúp tránh thử lại I/O liên tục, không tự giải quyết tính nguyên tử của file.

## 12. Backoff cho SFTP: kết nối, session và trạng thái transfer

SFTP là nơi BackOffPolicy dễ có ích vì kết nối từ xa có thể lỗi ngắt quãng. Tuy nhiên, adapter có nhiều khâu khác nhau:

- Mở session và xác thực host/user;
- Liệt kê remote directory;
- Tải file về local staging;
- Upload file ra remote;
- Rename/move remote file;
- Đóng/trả session về pool hoặc cache.

### Phân loại theo thao tác

| Thao tác | Lỗi có thể retry | Cần tránh |
|---|---|---|
| Kết nối SFTP | Timeout, connection reset tạm thời | Retry sai private key hoặc host key không xác minh |
| Liệt kê file | Server bận, network tạm không ổn định | Poll trùng gây tải hoặc thu nhiều lần |
| Download | Đứt mạng giữa transfer | Coi local partial file là hoàn tất |
| Upload | Đứt kết nối khi đã gửi gần xong | Gửi trùng/ghi đè file từ xa chưa biết trạng thái |
| Rename remote | Server timeout | Giả định rename chưa thực thi nếu response mất |
| Delete remote | Network timeout sau delete | Retry dẫn tới lỗi missing file gây xử lý sai |

### Quy trình upload có thể khôi phục

~~~text
Message eventId=invoice-882-v4
   -> chọn remote tempName dựa trên eventId
   -> upload phần dữ liệu
   -> kiểm tra kết quả/size/checksum nếu có
   -> publish/rename thành tên final
   -> ghi trạng thái CONFIRMED
~~~

Nếu upload timeout, cần hỏi **file tạm hoặc file cuối đã tồn tại chưa**, kích thước/hash có phù hợp không, và chính sách overwrite là gì. **Không giả định tất cả SFTP server hỗ trợ atomic rename theo cùng ngữ nghĩa**, đặc biệt khi đổi filesystem hoặc có hệ thống đích gián tiếp.

### Reconnect không đồng nghĩa replay

Một client SFTP có thể tự khởi tạo session mới khi session cũ hỏng. Nhưng:

- Session mới **không trả lời** transfer trước đã hoàn tất bao nhiêu byte.
- Remote accept-once/local metadata đã có thể ghi nhận file.
- Handler retry lại outbound HTTP **không tự tải lại SFTP file**.
- Backoff không thay kiểm soát host key, credential rotation hoặc quyền thư mục.

Cần xác định nơi lưu **transfer state** và **message state**, cách dùng session factory/cache, cũng như điều kiện retire và refresh connection.

## 13. Backoff cho HTTP outbound gateway

HTTP outbound gateway thường là ứng viên rõ nhất để dùng RequestHandlerRetryAdvice, vì nó biểu diễn một lời gọi remote có thể timeout.

### Phân biệt status và operation

| Response/lỗi | Backoff? | Điều kiện quan trọng |
|---|---|---|
| 429 Too Many Requests | Có thể; ưu tiên thông tin Retry-After hợp lệ | Quota, giới hạn thời gian chờ, endpoint và idempotency |
| 503 Service Unavailable | Có thể, exponential + jitter | Tránh khuếch đại quá tải |
| 502 Bad Gateway | Có thể tùy nguồn lỗi | Kiểm tra kết quả trước đó có thể đã hoàn tất |
| 504 Gateway Timeout | Có thể nhưng outcome có thể unknown | POST có side effect phải đối soát |
| Connect timeout | Có thể giới hạn | Network/DNS/đường kết nối và retry budget |
| Read timeout | Có thể, cần hiểu side effect | Không suy luận đích chưa nhận |
| 400 Validation | Thường không | Sửa schema/payload |
| 401/403 | Thường không retry cùng credential | Đánh giá xác thực/quyền |
| 404 | Tùy hợp đồng | Một số hệ thống eventual consistency |
| 409 | Tùy nghiệp vụ | Conflict có thể là already processed hoặc lỗi cần người xử lý |
| 500 | Không tự động retry mọi request | Đích có thể đã commit trước khi báo lỗi |

### Retry-After: thông báo của hệ thống đích

Nếu server trả **Retry-After** dạng thời gian chờ hoặc thời điểm HTTP-date, client cần diễn giải theo giao thức, kiểm tra đầu vào và **giới hạn bởi total deadline**.

Ví dụ:

~~~text
Response: HTTP 429
Retry-After: 10

Client budget:
  Deadline còn 4 giây.
  Server gợi ý chờ 10 giây.

Quyết định hợp lý:
  Không giữ request HTTP inbound chờ quá deadline.
  Có thể chuyển message sang delayed retry có lưu bền,
  hoặc trả lỗi có thể xử lý cho caller theo hợp đồng.
~~~

**ExponentialBackOffPolicy mặc định không tự động đọc header Retry-After của HTTP response.** Muốn tôn trọng header, cần thêm logic theo HTTP response/error và một cơ chế lập lịch chờ phù hợp.

### POST và idempotency key

~~~text
10:00:00  POST /orders, Idempotency-Key=order-782-v2
10:00:01  Partner ghi order thành công
10:00:02  Response bị mất
10:00:03  Client thấy timeout
10:00:04  Client retry cùng idempotency key sau backoff
10:00:05  Partner trả cùng kết quả order đã xử lý
~~~

Đây là hành vi mong đợi **nếu đối tác có contract idempotency thực sự**, bao gồm cách lưu kết quả, TTL và xử lý payload khác nhau với cùng key. Nếu không có contract, cần **query trạng thái hoặc reconciliation**, không gửi lại POST mù.

## 14. JMS/AMQP: backoff trong handler khác broker redelivery

JMS và AMQP mang theo cơ chế giao message, xác nhận, rollback/requeue và dead-letter. Backoff có thể được đặt:

1. **Bên trong handler:** RetryTemplate thử vài lần, tạm nghỉ ngắn.
2. **Tại listener container/broker:** message bị rollback/nack và được redeliver.
3. **Qua delayed queue/retry destination:** message được lưu rồi giao lại sau một khoảng thời gian dài hơn.

Ba lớp có thể cộng dồn số attempts. Nếu:

- Handler: 4 attempts;
- Broker: tối đa 5 lần delivery;
- Manual replay: thêm 3 vòng;

tổng số lần handler có thể lên tới **4 × 5 × 3 = 60** nếu tất cả lớp đều chạy đủ lượt, chưa kể retries bên trong HTTP client. Vì vậy phải có **retry budget end-to-end** và đếm đủ mỗi vòng.

### JMS listener

Cần xác định:

- Session có transacted không?
- Lỗi handler có propagate ra listener/container không?
- Container rollback rồi broker redeliver thế nào?
- Lúc nào message được acknowledge?
- Hết lượt có DLQ/poison-message policy không?
- Nếu handler đã gửi outbound HTTP rồi rollback JMS, lần giao lại có tạo side effect trùng không?

**BackOffPolicy trong handler thường giữ thread đang xử lý**. Với lỗi broker kéo dài, ưu tiên cơ chế redelivery/delayed processing của container/broker được cấu hình thay vì ngủ vô hạn.

### AMQP/RabbitMQ

Cần phân biệt:

- **Requeue ngay**: có thể tạo hot loop và đẩy CPU/broker lên cao.
- **Delayed retry**: dùng TTL/DLX, delayed exchange khi có hỗ trợ hoặc cơ chế retry của container phù hợp.
- **Dead-letter**: message hết budget được chuyển vào nơi có owner và đường replay.
- **Prefetch và concurrency**: nếu message nằm trong handler ngủ backoff lâu, số consumer slot bị chiếm tăng.
- **Publisher confirms** và consumer ack là hai việc khác nhau; gửi được message chưa chắc downstream đã xử lý.

### Một chiến lược tham chiếu

~~~mermaid
flowchart TD
    B["JMS/AMQP broker giao message"] --> H["Handler với retry ngắn"]
    H --> V{"Thành công?"}
    V -->|"Có"| A["Ack/commit theo cấu hình"]
    V -->|"Không"| R{"Còn attempts?"}
    R -->|"Có"| W["Backoff có giới hạn rồi retry"]
    W --> H
    R -->|"Không"| P{"Parking/DLQ bền vững?"}
    P -->|"Có"| D["Ghi DLQ/delayed queue rồi xác nhận nguồn theo contract"]
    P -->|"Không"| E["Propagate error -> rollback/nack theo policy"]
    E --> B
~~~

Không nên giả định **ghi DLQ trên broker khác và ack message nguồn là một transaction nguyên tử**. Khi không có transaction phân tán, cần thiết kế chống trùng và xử lý crash ở giữa hai thao tác.

## 15. Kafka: backoff phải phù hợp offset và thứ tự partition

Kafka lưu record theo partition; khi consumer xử lý thất bại, hệ thống cần quyết định **block/seek/retry, retry topic, DLT và offset commit**.

Spring Integration Kafka adapters thường phối hợp với các thành phần của **Spring for Apache Kafka**; các cơ chế retry trên listener container/error handler có thể khác với RequestHandlerRetryAdvice của một handler trong Integration Flow.

### Những ranh giới không được nhầm

- **Handler retry:** thử lại code xử lý một message trên cùng luồng.
- **Container error handler:** quản lý record/batch thất bại, seek/backoff/recover theo cấu hình.
- **Retry topic:** đưa record sang topic khác để xử lý sau, tùy kiến trúc.
- **DLT:** đích giữ record không thể xử lý trong luồng chính.
- **Offset commit:** broker consumer group đánh dấu tiến độ đọc, không phải bằng chứng nghiệp vụ ngoài Kafka đã commit.

### Vì sao backoff dài trong consumer nguy hiểm?

- Consumer thread có thể bị giữ trong thời gian dài.
- Record gây lỗi có thể chặn những record sau trong cùng partition.
- Batch và retry có thể tương tác phức tạp với ordering.
- Consumer group heartbeat, poll interval và rebalance là giới hạn vận hành cần tính.
- Một lần timeout sau ghi database/outbound HTTP có thể tạo duplicate khi record replay.

Với retry dài hơn mức phù hợp cho consumer thread, có thể cần **retry topic/delayed scheduling**. Nhưng chuyển sang retry topic có thể thay đổi **thứ tự xử lý** giữa records cùng key; phải quyết định liệu nghiệp vụ có cho phép hay không.

### Ví dụ: record xử lý thất bại

~~~text
Partition 2:
  offset 100: order-created
  offset 101: order-updated
  offset 102: order-cancelled

Nếu offset 100 lỗi tạm thời:
  A. Retry tại chỗ có thể giữ thứ tự nhưng chặn partition.
  B. Chuyển offset 100 sang retry topic có thể cho offset 101
     chạy trước nếu không có cơ chế bảo vệ ordering.

Không chọn A/B chỉ dựa vào latency.
Hãy xác định state machine theo orderId và business version.
~~~

**BackOffPolicy không tự thực hiện offset seek hoặc commit**, cũng không tự biến xử lý database/HTTP thành exactly-once trên toàn hệ thống.

## 16. JDBC: backoff khi database connection/transaction lỗi

Database retry cần tách lỗi kết nối khỏi lỗi của **transaction đã thay đổi dữ liệu**.

| Trường hợp | Hướng xử lý |
|---|---|
| Connection pool tạm hết connection | Giới hạn concurrency, timeout, backoff; phân tích pool sizing |
| DB failover ngắn | Retry có giới hạn nếu thao tác an toàn và connection được làm mới |
| Deadlock / serialization conflict | Rollback toàn transaction thích hợp, mở transaction mới rồi retry |
| Unique constraint violation | Thường cần xem duplicate/business conflict, không retry không điều kiện |
| Syntax/schema error | Sửa SQL/migration, không retry |
| DB timeout sau commit không rõ | Query theo business key, đối soát outcome |
| Transaction rollback-only | Không cố lặp operation bên trong transaction không thể commit |

### Sai lầm phổ biến

~~~text
@Transactional
processOrder():
    HTTP POST tạo đơn hàng thành công
    DB UPDATE gặp deadlock

Retry toàn processOrder():
    HTTP POST được gửi lại
    DB UPDATE có thể thành công

Kết quả nếu không idempotent:
    Đối tác có thể có hai đơn hàng.
~~~

Hướng thiết kế đúng hơn:

- **Đơn vị transaction database** được retry riêng khi có thể rollback/mở mới.
- Lời gọi đối tác phải có **idempotency key**, query trạng thái hoặc một state machine bền vững.
- Dùng **transactional outbox** để lưu ý định phát message cùng giao dịch dữ liệu.
- Consumer/updater dùng stable event ID và unique constraint phù hợp.
- Backoff cho deadlock thường nên ngắn và có jitter để tránh hai transaction tiếp tục xung đột.

### JDBC inbound polling

Nếu poller đọc các hàng trạng thái NEW rồi đánh dấu PROCESSING, handler lỗi cần có cơ chế chuyển RETRY_WAIT, ghi nextAttemptAt hoặc lease hết hạn. **RetryTemplate in-memory không tự giữ attempt count sau application restart**.

~~~text
NEW -> CLAIMED -> PROCESSING -> DONE
                    |
                    +-> RETRY_WAIT -> PROCESSING
                    |
                    +-> PARKED (cần người xử lý)
~~~

Cần transaction/claim atomic, identity của worker, lease, timeout, max attempts **bền qua restart** và idempotency tại tác dụng phụ.

## 17. Khi nào nên chuyển sang delayed retry bền vững?

**BackOffPolicy thông thường trong RetryTemplate điều phối thời gian nghỉ của một chuỗi retry đang chạy trong process.** Nó không phải một hệ lập lịch job bền vững và không bảo toàn pending attempt qua crash.

Dùng **short in-process retry** khi:

- Lỗi có thể phục hồi sau vài trăm mili giây hoặc vài giây.
- Số attempts nhỏ, timeout chặt.
- Có thread/concurrency đủ cho tải dự kiến.
- Operation an toàn để thực hiện lại.
- Caller hoặc message handler còn deadline phù hợp.

Dùng **durable delayed retry** khi:

- Đối tác có thể down nhiều phút/giờ.
- Retry-After yêu cầu đợi lâu hơn deadline request.
- Hàng nghìn message đang chờ mà không nên giữ thread.
- Cần khôi phục qua process restart hoặc redeploy.
- Cần inspect, pause, replay và quản lý tuổi message.
- Có nghiệp vụ hạn hoàn thành riêng, khác thời gian giữ kết nối.

### So sánh

| Khía cạnh | RetryTemplate + BackOffPolicy | Delayed retry bền vững |
|---|---|---|
| Trạng thái retry | Trong process/chuỗi gọi | Queue/topic/job store/DB |
| Thời gian phù hợp | Thường ngắn | Có thể dài |
| Dùng worker thread trong lúc chờ | Thường có | Không nhất thiết |
| Tồn tại qua restart | Không tự có | Có nếu storage/transaction đúng |
| Quan sát từng lần | RetryListener/metrics | Trạng thái job/queue và event |
| Giữ thứ tự message | Tùy handler/container | Phải thiết kế riêng |
| Số attempts toàn chu kỳ | Context in-memory | Attempt count phải lưu bền |
| Terminal state | Exception hoặc RecoveryCallback | DLQ/PARKED + owner/retention |
| Thích hợp khi tải lớn và đích down lâu | Thường hạn chế | Thường tốt hơn nếu có kiểm soát |

### Ví dụ state cho delayed retry

~~~json
{
  "eventId": "invoice-sync-882-v4",
  "targetSystem": "partner-erp",
  "operation": "invoice.upsert",
  "state": "RETRY_WAIT",
  "attemptCountPersisted": 6,
  "nextAttemptAt": "2026-11-23T09:30:00Z",
  "deadlineAt": "2026-11-24T00:00:00Z",
  "lastErrorCategory": "REMOTE_SERVICE_UNAVAILABLE",
  "payloadRef": "secured-store/item-882",
  "idempotencyKeyRef": "invoice-sync-882-v4",
  "correlationId": "corr-77ab"
}
~~~

Đây là schema minh họa, không phải một kiểu message sẵn có của Spring Integration. Không lưu access token, khóa riêng hoặc dữ liệu nhạy cảm nguyên văn trong record retry.

## 18. Kết hợp timeout, rate limiter, circuit breaker và bulkhead

Backoff là **một trong nhiều biện pháp độ tin cậy**.

| Biện pháp | Câu hỏi giải quyết | Quan hệ với backoff |
|---|---|---|
| **Connection/read timeout** | Một attempt được phép chờ bao lâu? | Không có timeout, không thể dự toán tổng retry |
| **Total deadline** | Toàn operation còn ý nghĩa trong bao lâu? | Ngừng retry nếu backoff vượt hạn |
| **Rate limiter** | Được gửi bao nhiêu request/giây? | Giảm vượt quota và retry burst |
| **Circuit breaker** | Hệ thống đích đang thất bại hàng loạt, có nên gọi nữa không? | Khi open, thường dừng các attempt mới |
| **Bulkhead/concurrency limit** | Bao nhiêu worker được giữ bởi một phụ thuộc? | Ngăn một partner down chiếm hết thread |
| **Backpressure** | Upstream có đang đẩy nhanh hơn downstream xử lý? | Cần queue bound và flow control |
| **Idempotency** | Lặp operation có gây tác dụng phụ trùng không? | Là điều kiện an toàn độc lập |
| **DLQ/parking** | Hết retry có giữ message để điều tra/replay không? | Hệ quả sau exhaustion |
| **Transaction/outbox** | Dữ liệu nghiệp vụ và event có được bảo toàn nhất quán không? | Ngăn mất/nhân đôi do rollback/crash |

### Khi circuit breaker open

Nếu mọi request vào một dependency đang down đều thử 4 attempts, hệ thống có thể tăng tải gấp bội. Circuit breaker giúp từ chối nhanh các request mới ở trạng thái open theo chính sách. Khi half-open, chỉ một số request thử nghiệm nên được đi qua.

**Thứ tự ghép circuit breaker, RetryAdvice, rate limiter và transaction advice ảnh hưởng trực tiếp đến số lần gọi thật.** Hãy đo bằng test; không giả định các cách ghép có ngữ nghĩa tương đương.

### Backoff có thể làm nghẽn thread

Giả sử một handler có 20 worker threads. Đối tác lỗi, mỗi message chiếm một thread 10 giây gồm attempt timeout và backoff. Trong lúc đó, nếu incoming rate cao hơn throughput đang xử lý, backlog tăng.

Không chỉ chỉnh maxInterval; cần:

- Giảm attempts ở tầng đồng bộ.
- Giới hạn concurrency tới đối tác.
- Dùng delayed retry khi sự cố dài.
- Theo dõi queue depth, oldest-message age và retrying threads.
- Giới hạn số message đang được xử lý hoặc áp dụng backpressure.
- Đảm bảo bounded memory và trạng thái terminal rõ ràng.

## 19. Retry storm và hiện tượng nhân bản attempts qua nhiều tầng

Hãy xét một request gốc:

~~~text
Client HTTP:
   retry tối đa 3 attempts
      -> API Gateway:
          retry tối đa 4 attempts
             -> Spring Integration HTTP handler:
                 retry tối đa 5 attempts
~~~

Trong tình huống xấu nhất, partner API có thể nhận **3 × 4 × 5 = 60 lần gọi** cho một thao tác nghiệp vụ, nếu mỗi tầng thử hết attempts và không có giới hạn bổ sung.

Nếu operation là POST không idempotent, hậu quả có thể nghiêm trọng. Ngay cả với GET an toàn, 60 calls có thể khiến hệ thống đích đang quá tải càng khó phục hồi.

### Quy tắc thiết kế ngân sách end-to-end

1. Ghi rõ **owner của retry** cho từng loại lỗi và điểm nối.
2. Tránh retry chồng chéo ở HTTP client, proxy, gateway, advice, broker.
3. Cộng **max attempts xấp xỉ** giữa những tầng có thể lồng nhau.
4. Đặt total deadline phù hợp business contract.
5. Dùng **idempotency key chung qua mọi lần lặp**.
6. Thiết kế circuit breaker/rate limit dựa trên tải của **đích thực**, không chỉ từng instance.
7. Thêm jitter khi nhiều instance có thể nhận lỗi cùng lúc.
8. Sau budget ngắn, chuyển sang durable retry nếu còn hợp đồng xử lý.

### Phân biệt retry count ở từng tầng

Nếu metric ở RequestHandlerRetryAdvice báo ba retries, điều đó không chứng minh broker chỉ giao message một lần. Cần log/metric riêng:

- **Handler attempts**;
- **Container deliveries/redeliveries**;
- **Durable redrives**;
- **HTTP client-level attempts**;
- **Business events hoàn tất**.

**Một đơn hàng chỉ nên được đếm một lần ở metric nghiệp vụ**, bất kể nó tạo nhiều attempts kỹ thuật.

## 20. Error channel, RecoveryCallback và điểm dừng an toàn

Khi RetryPolicy đã exhausted, cần chọn **terminal outcome**:

- Propagate exception để caller hoặc listener container xử lý rollback/nack.
- Ghi vào DLQ/parking bền vững.
- Lưu lại một job retry chậm với nextAttemptAt.
- Chuyển invalid payload sang quarantine.
- Trả fallback chỉ khi **hợp đồng nghiệp vụ** cho phép.
- Cảnh báo và tạo incident cho mất kết nối kéo dài hoặc lỗi credentials.

### Đường recovery không được nuốt message

Một anti-pattern:

~~~text
RecoveryCallback:
    logger.error("Đã retry nhiều lần")
    return null

Caller/consumer:
    handler kết thúc bình thường
    container có thể ack/commit

Kết quả:
    Message chưa được xử lý
    nhưng nguồn nghĩ đã xong.
~~~

**RecoveryCallback trả bình thường không tự nghĩa là thông điệp đã được bảo toàn.** Nếu cần lưu DLQ/parking trước ack, phải xác minh thao tác lưu **thành công và bền vững**. Nếu lưu thất bại, cần propagate exception hoặc dùng phương án rollback/ack đã được thiết kế.

### Ví dụ RecoveryCallback chủ động rethrow

~~~java
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
advice.setRetryTemplate(retryTemplate);

advice.setRecoveryCallback(context -> {
    Throwable last = context.getLastThrowable();

    // Không coi lỗi là success; caller/container cần xử lý terminal failure.
    throw new IllegalStateException(
            "Outbound handler exhausted retry attempts", last);
});
~~~

Ví dụ này cố ý không ghi DLQ, vì việc ghi DLQ đúng cách phụ thuộc **loại nguồn, transaction/ack, channel và broker**. Trong production cần phân loại terminal failure và gắn correlation ID để support điều tra.

### ErrorChannel không tự là durable queue

**ErrorChannel** trong Spring Integration là tuyến truyền error message theo cấu hình. Nếu nó là channel in-memory, không thể xem là storage bền vững. Khi recovery cần tồn tại qua restart, nên có message store, broker DLQ hoặc database parking được kiểm soát.

## 21. Idempotency và lỗi “đã xử lý nhưng không nhận được phản hồi”

Backoff có thể khiến nhiều lần gọi cách nhau lâu hơn, nhưng **không loại bỏ khả năng side effect trùng**. Sự cố nguy hiểm nhất là **outcome unknown**.

### Các lớp cần tách

1. **Message được giao lại:** cùng event xuất hiện lần nữa.
2. **Handler được gọi lại:** cùng business event có thêm attempt.
3. **Destination xử lý lại:** có thể tạo side effect thứ hai.
4. **Business effect được xác nhận:** phải idempotent ở phạm vi đã chọn.

Ví dụ một event order.updated được retry từ broker sau khi timeout. Nếu mỗi lần gửi nó tới partner với mã order mới, partner sẽ tạo nhiều bản ghi. Cần dùng **business event ID ổn định** hoặc idempotency key do hợp đồng quy định.

### Inbox/outbox

- **Inbox/dedupe:** phía nhận lưu event ID đã xử lý và kết quả, dùng unique constraint/transaction khi phù hợp.
- **Transactional outbox:** ghi nghiệp vụ và ý định gửi cùng transaction database; worker có thể publish lại và consumer phải idempotent.
- **Stateful workflow:** tách các bước OUTBOUND_PENDING, OUTCOME_UNKNOWN, CONFIRMED, PARKED để không lặp toàn flow mù.
- **Reconciliation:** hỏi đích xem request trước đã thành công khi response bị mất.

### Một ví dụ ranh giới đúng

~~~text
SFTP file chứa eventId=inv-882-v4
    -> parse, validate
    -> inbox ghi RECEIVED
    -> HTTP upsert cùng idempotency key
       -> nếu timeout: TRA CỨU trạng thái
       -> nếu tạm lỗi: retry với backoff
       -> nếu exhausted: PARKED
    -> xác nhận ERP_CONFIRMED
    -> DB transaction lưu DONE + outbox notification
    -> AMQP publisher gửi outbox event
    -> đối tác nhận và dedupe
~~~

**Không nên đặt toàn bộ chuỗi này trong một RetryCallback** vì lỗi ở bước cuối có thể khiến bước HTTP trước đó chạy lại và tạo hiệu ứng không mong muốn.

## 22. Connection lifecycle: reconnect, failover và làm sạch tài nguyên

Khi kết nối thất bại, ngoài retry/backoff cần xem **vòng đời connection và session**.

### Những trạng thái cần quan sát

- Connection chưa mở được.
- Connection đã mở nhưng authentication thất bại.
- Connection đã dùng nhưng bị đóng bởi phía remote.
- Connection pool trả về một session stale.
- Lời gọi thành công ở remote nhưng response bị mất.
- Connection bị hủy trong lúc backoff.
- Service được deploy lại khi còn message đang chờ retry.

### Những việc phải đảm bảo

1. **Không dùng lại session/connection hỏng** nếu client/pool yêu cầu invalidate.
2. Đóng/trả tài nguyên đúng cách sau lỗi và cancellation.
3. Kiểm tra credential rotation, TLS/SSH host key và auth failures; không giảm bảo mật để “cho kết nối lại”.
4. Không mở quá nhiều connection mới do retry burst.
5. Đảm bảo backoff có thể được dừng khi ứng dụng shutdown hoặc job bị cancel; xử lý interruption theo hợp đồng thư viện.
6. Khi remote service thay IP/endpoint do failover, chính sách retry phải phù hợp DNS/cache và client connection pooling.
7. Sau reconnect, kiểm tra **trạng thái nghiệp vụ** chứ không mặc định remote chưa xử lý request trước.

### Interruption và shutdown

Trong Java, một worker đang nghỉ backoff có thể bị **interrupt** khi shutdown. Nếu policy dùng Sleeper/thread sleep, việc gián đoạn có thể nổi thành exception liên quan đến backoff/interruption tùy API. Không nên bắt mọi exception rồi tiếp tục retry bất chấp shutdown. Hãy propagate cancellation, giải phóng tài nguyên và bảo toàn message chưa hoàn tất qua nguồn/parking theo thiết kế.

## 23. Observability: log đủ để hiểu backoff và kết quả cuối

Cần quan sát **độ tin cậy của message**, không chỉ số lần exception.

### Các trường log nên có

| Trường | Ý nghĩa |
|---|---|
| eventId/businessKey | Nhận dạng ổn định qua retry, broker redelivery, restart |
| correlationId/traceId | Liên kết inbound, outbound, retry và recovery |
| adapter/flow/endpointId | Biết điểm nào đang thử lại |
| targetSystem | SFTP host alias, HTTP partner, broker, topic, DB theo tên an toàn |
| attemptIndex/maxAttempts | Đếm lần gọi chính xác |
| errorCategory/exceptionType | Phân loại transient, permanent, unknown |
| scheduledDelayMs/actualDelayMs | Phân biệt policy và thời gian thực tế |
| elapsedMs/deadlineRemainingMs | Phát hiện vượt latency budget |
| policyType/policyVersion | Fixed/exponential/jitter và cấu hình |
| finalOutcome | SUCCESS, EXHAUSTED, PARKED, DLQ, CANCELLED |
| sourceAck/commitOutcome | Message/offset có được xác nhận nguồn không |
| idempotencyKeyRef | Liên kết attempts với một nghiệp vụ mà không lộ secret |

**Không log toàn bộ payload nhạy cảm, access token, password, private key SFTP hoặc các header bảo mật.** Với metric, không đưa eventId/transactionId làm label để tránh **high-cardinality**.

### Bộ metric đề xuất

| Metric | Cách đo | Mục đích |
|---|---|---|
| **retry_attempts_total** | Số handler attempts, phân theo endpoint/error category | Phát hiện tỷ lệ lỗi phụ thuộc |
| **retry_success_after_failure_total** | Số chuỗi thành công sau ít nhất một lần retry | Đo ích lợi của retry |
| **retry_exhausted_total** | Chuỗi retry hết budget | Theo dõi recovery load |
| **backoff_requested_seconds** | Phân phối khoảng nghỉ được policy yêu cầu | Kiểm tra cấu hình delay |
| **backoff_actual_seconds** | Khoảng nghỉ thực quan sát được | Phát hiện scheduling/sự cố runtime |
| **handler_latency_seconds** | Latency tổng gồm attempts/backoff, P50/P95/P99 | Đánh giá ảnh hưởng tới SLA |
| **source_redelivery_total** | Số message từ broker/file/job được giao lại | Tách redelivery và in-process retries |
| **delayed_retry_backlog** | Số message chờ lịch retry bền vững | Đo quy mô sự cố kéo dài |
| **dlq_or_parked_age_seconds** | Tuổi của message bị dừng xử lý | Phát hiện tác vụ quan trọng bị bỏ quên |
| **duplicate_business_effect_total** | Hiệu ứng nghiệp vụ trùng được xác nhận | Kiểm tra tính an toàn retry |
| **circuit_breaker_open_count** | Lần dependency bị mở breaker | Nhận diện lỗi lan rộng |
| **pool_waiting_threads** | Số thread bị giữ/chờ trong integration pool | Tránh nghẽn do backoff |
| **reconnect_failures_total** | Lần mở kết nối/số session lỗi theo adapter | Tìm sự cố network/client |

**Tăng retry attempts không tự là tốt hay xấu.** Nó có thể cho thấy hệ thống đích đang gặp vấn đề; cần so với request volume, success rate, latency và duplicate effects.

## 24. Thiết kế kiểm thử BackOffPolicy đáng tin

Kiểm thử không nên chỉ assert “cuối cùng thành công”. Cần kiểm tra **số attempts, điều kiện dừng, khoảng nghỉ và side effects**.

### Kiểm thử đơn vị cho fixed backoff

~~~java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

// Đoạn mã minh họa bên trong một test method.
RetryTemplate template = new RetryTemplate();

SimpleRetryPolicy policy = new SimpleRetryPolicy(3);
FixedBackOffPolicy backOff = new FixedBackOffPolicy();
backOff.setBackOffPeriod(1L); // 1 ms để test không chờ lâu.

template.setRetryPolicy(policy);
template.setBackOffPolicy(backOff);

AtomicInteger calls = new AtomicInteger();

String result = template.execute(ctx -> {
    if (calls.incrementAndGet() < 3) {
        throw new IOException("Temporary connection issue");
    }
    return "OK";
});

// Assertions mong đợi:
// result.equals("OK")
// calls.get() == 3
// 2 khoảng nghỉ giữa các lần thử.
~~~

Ví dụ xác minh attempts; khi cần kiểm tra **đúng khoảng nghỉ hoặc dãy exponential**, hãy dùng **Sleeper/test double hoặc clock/scheduler abstraction** thích hợp với phiên bản Spring Retry để ghi các delay mà không phụ thuộc vào thời gian wall clock (dễ flaky). Không chạy integration test thực với delay nhiều phút chỉ để đếm dãy backoff.

### Ma trận kiểm thử

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| B1 | Thành công ngay attempt đầu | Chỉ một invocation, không backoff |
| B2 | Hai lỗi transient rồi thành công | Ba attempts, có hai khoảng nghỉ |
| B3 | Luôn lỗi với maxAttempts=4 | Bốn attempts, ba khoảng nghỉ, đi recovery |
| B4 | ValidationException hoặc HTTP 400 | Không retry, không backoff |
| B5 | HTTP 401/403 | Không lặp request với credential không hợp lệ |
| B6 | HTTP 429 và Retry-After hợp lệ | Không gọi sớm hơn chính sách server/deadline |
| B7 | Retry-After lớn hơn total deadline | Dừng/chuyển durable retry theo contract |
| B8 | Exponential backoff có maxInterval | Khoảng nghỉ tăng rồi chạm trần |
| B9 | Nhiều worker cùng lỗi | Jitter/rate limit tránh burst vượt ngân sách |
| B10 | Backoff bị interrupt do shutdown | Hủy sạch, bảo toàn message chưa hoàn tất |
| B11 | HTTP POST đã ghi xong nhưng timeout | Retry không tạo record thứ hai nếu contract idempotent |
| B12 | 503 lặp, partner down dài | Không giữ thread vô hạn; chuyển PARKED/delayed |
| B13 | RecoveryCallback trả bình thường | Ack chỉ khi message đã được bảo toàn như thiết kế |
| B14 | DLQ/parking ghi thất bại | Không mất message vì nuốt exception |
| B15 | SFTP disconnect giữa upload | Remote partial file được phát hiện/đối soát |
| B16 | SFTP sai host key | Không retry vượt qua kiểm tra xác thực host |
| B17 | File inbound vẫn đang upload | Không parse file dở, không tạo nghiệp vụ trùng |
| B18 | Poller chạy cùng handler retry | Tính được số lần gọi và tiến độ theo lịch |
| B19 | JMS broker redelivery × handler retry | Tổng attempts không vượt budget |
| B20 | AMQP requeue liên tục | Không tạo hot loop; DLQ theo policy |
| B21 | Kafka error handler backoff | Không commit offset sai hoặc phá ordering ngoài contract |
| B22 | JDBC deadlock | Mở transaction mới và commit đúng một lần |
| B23 | Restart ứng dụng giữa backoff | In-memory state mất; durable recovery hoạt động |
| B24 | Circuit breaker open | Không phát sinh remote call mới trái policy |
| B25 | Concurrent retries vượt pool | Có backpressure/metrics/alert, không cạn memory |
| B26 | Nested retries ở client và gateway | Đo được tổng attempts thực, có chặn budget |
| B27 | Delay config sai (0 hoặc cực lớn) | Test validation và cảnh báo cấu hình |
| B28 | Poison message sau exhaustion | Quarantine/DLQ với reason code và owner |

### Kiểm thử end-to-end với lỗi kết nối thật có kiểm soát

1. Chuẩn bị một HTTP/SFTP stub hoặc test container có thẩm quyền để mô phỏng lỗi.
2. Gắn stable eventId/correlationId cho message.
3. Cho stub trả lỗi transient hai lần rồi thành công.
4. Ghi call count, timestamps, exception, result và side effects.
5. Kiểm tra max attempts và khoảng nghỉ có phù hợp policy không.
6. Chuyển stub sang trạng thái “đã ghi nhưng response mất”, xác minh dedupe/reconciliation.
7. Tắt consumer giữa backoff, restart và kiểm tra message không bị mất.
8. Làm lỗi terminal recovery, bảo đảm nguồn không ack/commit sai.
9. Tăng concurrency thử nghiệm, đo queue depth và retry rate.
10. Ghi bằng chứng vào test report cùng cấu hình policy, không chỉ thông báo PASS/FAIL.

## 25. Tình huống thực hành: SFTP → HTTP ERP → JDBC → AMQP

### Bối cảnh

Doanh nghiệp nhận một file invoices.csv từ SFTP, mỗi record đại diện cho một hóa đơn cần đồng bộ sang ERP.

Spring Integration Flow:

~~~text
SFTP inbound adapter + poller
    -> staging file
    -> parser / validator
    -> MessageChannel
    -> HTTP outbound gateway -> ERP
    -> JDBC update status
    -> AMQP outbound adapter (notification)
    -> archive file
~~~

Các điều kiện nghiệp vụ:

- Mỗi hóa đơn có **invoiceId + version** duy nhất.
- Không được tạo trùng hóa đơn ERP.
- Hóa đơn lỗi dữ liệu phải được cách ly và có lý do.
- Hóa đơn đã được gửi nhưng chưa chắc kết quả cần được đối soát.
- Khi ERP down vài phút, không được giữ toàn bộ worker threads.
- Nếu ứng dụng restart, message pending không được biến mất.

### Dòng thời gian giả lập

| Thời gian | Sự kiện |
|---|---|
| 08:00 | Đối tác đang upload invoices.csv.part, file chưa sẵn sàng |
| 08:02 | Đối tác publish invoices.csv.ready |
| 08:03 | Poller lấy file, parse; hóa đơn A hợp lệ, hóa đơn B thiếu mã khách hàng |
| 08:04 | ERP trả HTTP 503 với một số request |
| 08:05 | HTTP POST của A được ERP ghi thành công nhưng response timeout |
| 08:06 | Nhiều worker retry cùng lúc, ERP tiếp tục quá tải |
| 08:08 | Database local gặp deadlock khi cập nhật trạng thái A |
| 08:09 | RabbitMQ tạm mất kết nối |
| 08:10 | Một instance ứng dụng restart trong lúc còn backoff |
| 08:15 | Đối tác SFTP có lỗi authentication vì khóa bị rotate |
| 08:30 | ERP khôi phục và yêu cầu giảm tốc độ gửi trong vài phút |

### Nhiệm vụ

1. Chỉ ra chính xác **những lỗi nên retry** và **những lỗi không nên retry**.
2. Đề xuất một BackOffPolicy thích hợp cho **HTTP 503**, gồm initial interval, multiplier, trần, jitter và max attempts.
3. Chứng minh công thức **tổng thời gian tối đa** cho chuỗi HTTP retries khi đã đặt timeout cho từng attempt.
4. Xác định vì sao **HTTP POST timeout sau khi ERP ghi xong** cần cách xử lý khác lỗi connect fail.
5. Phân biệt **lịch poll SFTP**, **backoff trong HTTP handler** và **delayed retry sau exhaustion**.
6. Thiết kế trạng thái bền vững để survive restart và tránh tạo hai hóa đơn ERP.
7. Giải thích JDBC deadlock và AMQP lỗi nên được retry ở **ranh giới nào**.
8. Thiết kế cách tránh retry storm và cơ chế recovery khi ERP down lâu.
9. Đề xuất metrics, alert và tối thiểu tám test cases có thể xác minh kết quả end-to-end.

### Hướng dẫn lời giải

**1. Phân loại.** HTTP 503 là ứng viên retry với backoff; timeout kết nối có thể retry khi operation an toàn. Hóa đơn B thiếu mã khách hàng là lỗi validation, **không** thử lại cùng payload. SFTP authentication do key rotate phải sửa credential theo quy trình bảo mật. JDBC deadlock thường có thể rollback và mở transaction mới. AMQP connection tạm lỗi có thể cần durable publication. POST outcome unknown phải **tra cứu/đối soát** hoặc dùng idempotency key.

**2. Policy tham chiếu.** Chọn ví dụ maxAttempts=4, initialInterval=250 ms, multiplier=2, maxInterval=2.000 ms, dùng randomization; đây là giá trị **minh họa**, không phải chuẩn bắt buộc. Đặt response/connect timeout và deadline tổng theo ERP SLA; nếu partner có Retry-After, cần xét thông tin đó và ngân sách nghiệp vụ.

**3. Tính thời gian.** Nếu bỏ randomization để dễ tính, dãy nghỉ của bốn attempts là 250, 500, 1.000 ms, tổng **1.750 ms**. Với timeout mỗi attempt tối đa 1,5 giây, tổng xấp xỉ **4 × 1,5 s + 1,75 s = 7,75 giây**, chưa tính overhead. Có jitter thì tính theo **giới hạn thực** của policy, không khẳng định con số chính xác là 7,75 giây.

**4. Unknown outcome.** ERP có thể đã commit hóa đơn A trước khi response bị mất. Gửi lại với **Idempotency-Key=invoiceId-version** theo hợp đồng ERP hoặc query theo business key. Nếu không có cơ chế xác minh, chuyển A sang OUTCOME_UNKNOWN và điều tra; không tái tạo invoice mù.

**5. Ba thời gian khác nhau.** Poller kiểm tra SFTP theo lịch, không đồng nghĩa retry cùng message. RetryTemplate chờ ngắn giữa các lần gọi ERP. Delayed retry lưu message bền vững và lập lịch xử lý khi ERP khôi phục, không giữ thread liên tục.

**6. Trạng thái bền vững.** Mỗi record có eventId, trạng thái RECEIVED/VALIDATED/ERP_PENDING/OUTCOME_UNKNOWN/ERP_CONFIRMED/NOTIFICATION_PENDING/DONE/PARKED, attempt count và nextAttemptAt. Dùng unique constraint và inbox/outbox. Khi restart, worker khôi phục các trạng thái chưa terminal mà không tạo duplicate.

**7. Ranh giới transaction.** JDBC deadlock rollback và retry **transaction database riêng**. AMQP outage xảy ra sau DB update, nên ghi notification event vào **transactional outbox**, publisher gửi khi broker trở lại. Không retry từ bước SFTP nếu chỉ AMQP bị lỗi.

**8. Khi quá tải.** Dùng exponential backoff có jitter, rate limiter, concurrency cap/circuit breaker. Hết lượt in-process thì chuyển delayed retry có trạng thái và alert. Khi ERP phục hồi, drain backlog có kiểm soát, tránh toàn bộ queue đồng loạt truy cập.

**9. Metrics/test.** Theo dõi retry_attempts_total, exhausted, actual backoff, handler latency, delayed backlog age, duplicate effects, event processing latency, outbound HTTP 503, SFTP reconnect failures, AMQP publish result. Test: invalid data, 503 rồi thành công, 503 dài hạn, timeout sau commit, SFTP auth error, DB deadlock, AMQP outage, crash giữa backoff, DLQ failure và concurrent retry storm.

### Một kiến trúc mục tiêu

~~~mermaid
flowchart LR
    S["SFTP file ready"] --> V["Stage + validate"]
    V -->|"Invalid"| Q["Quarantine có reason code"]
    V -->|"Valid"| I["Inbox: stable eventId"]
    I --> E["ERP state machine"]
    E --> H{"Lỗi gì / outcome nào?"}
    H -->|"Transient + safe retry"| R["Short retry: RetryTemplate + backoff"]
    H -->|"Outcome unknown"| C["Tra cứu / reconciliation"]
    R -->|"Thành công"| D["ERP_CONFIRMED"]
    C -->|"Đã xác minh"| D
    R -->|"Exhausted"| P["Durable RETRY_WAIT / PARKED"]
    P -->|"Đến lịch, còn hạn"| E
    D --> T["DB transaction: DONE + outbox"]
    T --> A["AMQP outbox publisher"]
    A -->|"Broker tạm lỗi"| W["Delayed publish + backoff"]
    W --> A
    A --> N["Notification confirmed"]
    N --> Z["Archive theo policy"]
~~~

Sơ đồ chỉ thể hiện trách nhiệm. Mọi vòng lặp delayed phải có **giới hạn attempts, thời hạn message, rate control và terminal state**; không thực hiện busy loop vô hạn.

## 26. Những anti-pattern dễ gặp

| Anti-pattern | Vì sao nguy hiểm | Cách khắc phục |
|---|---|---|
| Retry ngay lập tức khi kết nối fail | Khuếch đại tải | Backoff có giới hạn và jitter |
| Chỉ đặt backoff, không maxAttempts | Có thể lặp quá lâu/vô hạn | RetryPolicy rõ ràng |
| Chỉ đặt maxAttempts, không network timeout | Attempt đầu có thể treo | Connect/read timeout + deadline |
| Exponential không có trần | Delay rất dài, vượt SLA | maxInterval/total deadline |
| Fixed delay giống nhau ở hàng nghìn client | Request đồng loạt tái diễn | Jitter/rate limit |
| Retry tất cả exception | Dữ liệu invalid và auth lỗi không thể tự phục hồi | Exception classifier |
| Retry HTTP POST với outcome unknown | Tạo side effects trùng | Idempotency/tra cứu kết quả |
| Dùng RetryTemplate như job scheduler bền vững | Mất retry state khi restart | Delayed queue/job store |
| Đặt advice quanh toàn flow | Lặp lại thao tác đã thành công ở bước trước | Retry đúng handler/operation |
| Quên broker redelivery | Tổng attempts tăng ngoài kiểm soát | Retry budget end-to-end |
| Nuốt exception ở RecoveryCallback | Source có thể ack trước khi bảo toàn message | DLQ/parking có xác nhận hoặc rethrow |
| Không phân biệt poller và retry | Re-poll không chắc lấy lại message | Message state/replay riêng |
| Backoff dài trong Kafka consumer | Chặn partition và có rủi ro rebalance | Error handler/retry topics phù hợp |
| Retry JDBC trong rollback-only transaction | Transaction không thể commit | Mở transaction mới đúng scope |
| SFTP upload lại không kiểm remote state | File trùng hoặc partial | Temp file + checksum/reconcile |
| Reconnect bằng cách bỏ SSH host-key checking | Tăng nguy cơ kết nối giả | Bảo vệ trust/keys và sửa credential |
| Log token/secret mỗi attempt | Tạo rủi ro lộ thông tin | Structured log tối thiểu |
| Không đo số thread đang backoff | Hệ thống nghẽn mà không rõ nguyên nhân | Pool metrics, bulkhead, backpressure |
| DLQ không owner/retention | Poison message bị bỏ quên | Alert, triage, controlled redrive |
| Retry không có business expiry | Tiếp tục thao tác đã hết ý nghĩa | Deadline và trạng thái CANCELLED |

## 27. Checklist triển khai

- [ ] Đã xác định tất cả inbound/outbound adapters, gateways, pollers, channels và handler trong flow.
- [ ] Biết chính xác **điểm nào có quyền retry** và điểm nào do broker/client library tự retry.
- [ ] RetryPolicy chọn lỗi theo transient/permanent/unknown và operation idempotent.
- [ ] Có maxAttempts **tính cả lần ban đầu**; không retry không giới hạn.
- [ ] BackOffPolicy chọn fixed/exponential/jitter theo tải và đặc tính đối tác.
- [ ] Có initialInterval, multiplier, maxInterval và validation giá trị phù hợp.
- [ ] Đã đặt connection/read timeout, total deadline và retry budget end-to-end.
- [ ] HTTP 429/503 xét Retry-After, rate limit và circuit breaker.
- [ ] Tránh đồng thời client/gateway/advice/broker retry mà không cộng attempts.
- [ ] RequestHandlerRetryAdvice chỉ áp đúng handler cần retry.
- [ ] Không xem lịch poller là retry đảm bảo cùng message.
- [ ] File/SFTP có quy tắc publish hoàn tất, transfer state, metadata và replay.
- [ ] HTTP POST/upsert có idempotency key hoặc outcome reconciliation.
- [ ] JMS/AMQP broker redelivery, ack/nack/rollback và DLQ phù hợp.
- [ ] Kafka consumer offset, ordering, error handler và DLT đúng yêu cầu nghiệp vụ.
- [ ] JDBC retry đúng ranh giới transaction, tránh transaction rollback-only.
- [ ] Retry in-memory ngắn, delayed retry dài có lưu bền qua restart.
- [ ] RecoveryCallback không nuốt lỗi khi message chưa bảo toàn.
- [ ] Có trạng thái PARKED/DLQ, retention, owner, alert và controlled redrive.
- [ ] Log có event ID, correlation ID, attempts, delay, error category và terminal outcome.
- [ ] Không ghi credential, private key, token, dữ liệu khách hàng nguyên văn vào log.
- [ ] Theo dõi retry attempts, exhaustion, delay thực, backlog age, pool saturation và duplicate effects.
- [ ] Test error classification, HTTP outcome unknown, SFTP partial, Kafka/JMS/AMQP redelivery, JDBC deadlock, restart và recovery failure.
- [ ] Đã có runbook khi đối tác down dài, retry storm, credential lỗi hoặc backlog vượt SLA.

## 28. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| **BackOffPolicy** | Quy định chiến lược chờ trước attempt tiếp theo trong chuỗi retry |
| **RetryPolicy** | Quyết định có còn retry được không dựa trên số lần, exception hoặc điều kiện |
| **RetryTemplate** | Điều phối RetryCallback, RetryPolicy, BackOffPolicy và recovery |
| **BackOffContext** | Trạng thái của một phiên backoff, ví dụ mức exponential hiện tại |
| **RetryContext** | Trạng thái của một chuỗi retry đang thực hiện |
| **FixedBackOffPolicy** | Khoảng nghỉ cố định |
| **ExponentialBackOffPolicy** | Khoảng nghỉ tăng theo hệ số với trần |
| **ExponentialRandomBackOffPolicy** | Chiến lược exponential có ngẫu nhiên hóa theo thư viện |
| **Jitter** | Ngẫu nhiên hóa thời điểm retry để tránh các client cùng dồn request |
| **Retry storm / thundering herd** | Nhiều client retry đồng loạt, làm quá tải nguồn đích |
| **Retry budget** | Giới hạn attempts/tải/thời gian cho retry trên toàn đường xử lý |
| **RequestHandlerRetryAdvice** | Advice của Spring Integration bọc message handler bằng retry |
| **Poller** | Thành phần lấy message theo lịch từ MessageSource |
| **Redelivery** | Nguồn/broker giao lại message do chưa hoàn tất/ack |
| **DLQ / DLT** | Hàng/topic giữ message thất bại, cần xử lý riêng |
| **Delayed retry** | Retry được lập lịch qua storage/queue, không nhất thiết giữ thread |
| **Idempotency key** | Khóa ổn định giúp nhận biết cùng một yêu cầu nghiệp vụ khi retry |
| **Outcome unknown** | Không rõ lần gọi trước đã tạo hiệu ứng ở đích hay chưa |
| **Transactional outbox/inbox** | Mẫu bảo toàn ý định gửi và/hoặc dedupe nhận gắn transaction |
| **Circuit breaker** | Ngăn tiếp tục gọi dependency khi lỗi lan rộng theo chính sách |
| **Bulkhead** | Giới hạn tài nguyên cho một nhóm phụ thuộc để tránh lỗi lan sang luồng khác |

## 29. Tài liệu tham khảo và câu hỏi tự đánh giá

### Tài liệu tham khảo

- **Spring Retry Reference:** RetryTemplate, RetryPolicy, BackOffPolicy, RetryContext/BackOffContext, RetryListener và recovery.
- **Spring Integration Reference — Message Handler Advice:** RequestHandlerRetryAdvice và advice chain trên endpoint.
- **Spring Integration Reference — Polling Consumer, Message Channels, Error Handling:** lịch poll, ranh giới đồng bộ/bất đồng bộ và error channel.
- **Spring Integration Reference — File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC Adapters:** ngữ nghĩa riêng của nguồn/đích, filters, transactions và message lifecycle.
- **Spring AMQP và Spring for Apache Kafka Reference:** listener retry, nack/requeue, DLQ/DLT, consumer errors và offset management.
- **Spring Framework Transaction Management:** transaction propagation/rollback, ranh giới retry với commit.
- **Enterprise Integration Patterns:** Idempotent Receiver, Dead Letter Channel, Transactional Client, Guaranteed Delivery, Message Store và Retry.

### Câu hỏi tự đánh giá

1. Một RetryPolicy maxAttempts = 5 với exponential backoff không jitter cần tối đa mấy khoảng nghỉ?
2. Vì sao HTTP read timeout sau một POST tạo payment có thể nguy hiểm hơn connect timeout trước khi request gửi?
3. Trường hợp nào FixedBackOffPolicy tốt hơn ExponentialRandomBackOffPolicy, và ngược lại?
4. Nếu 100 consumer cùng retry sau 503, jitter giúp gì và **không** giúp gì?
5. Tại sao RequestHandlerRetryAdvice ở HTTP gateway không bảo đảm poller SFTP sẽ nhận lại file?
6. Khi JMS broker redelivery và handler đều retry, làm sao tính attempts tối đa?
7. Vì sao giữ Kafka consumer ngủ backoff rất lâu có thể làm tăng lag?
8. Nếu JDBC transaction đã rollback-only, cần thay đổi ranh giới retry thế nào?
9. Khi RecoveryCallback trả bình thường, vì sao cần xem lại ack/commit?
10. Nếu ERP trả Retry-After 30 giây mà HTTP inbound deadline chỉ còn 3 giây, kiến trúc nên làm gì?

### Đáp án ngắn

1. **Tối đa 4 khoảng nghỉ**, vì lần đầu không đợi.
2. Request có thể đã được đích xử lý nhưng response thất lạc, nên retry có nguy cơ tạo tác dụng phụ trùng.
3. Fixed phù hợp tải thấp/lỗi có thời gian hồi phục ổn định; exponential có jitter thích hợp hơn khi nhiều client và tải lỗi lan rộng.
4. Jitter phân tán thời điểm gọi, nhưng không loại bỏ nhu cầu idempotency, max attempts, rate limit và deadline.
5. Advice chỉ bọc handler được chỉ định; source polling/metadata có vòng đời độc lập.
6. Tính cả **số handler attempts cho mỗi delivery × số deliveries × số redrives** và các tầng retry khác.
7. Consumer slot/partition có thể bị giữ, gây trễ xử lý và tương tác với giới hạn poll/rebalance.
8. Rollback và mở **transaction mới** cho attempt thích hợp, tránh lặp các side effects trước đó.
9. Caller/container có thể xem handler đã thành công và ack dù message chưa vào kho recovery.
10. Trả lỗi theo contract hoặc chuyển **durable delayed retry**, không giữ inbound request vượt deadline.

**Điểm cần ghi nhớ:** **BackOffPolicy không quyết định có retry hay không**; nó điều khiển **thời điểm** của những retries đã được RetryPolicy cho phép. Trong Spring Integration Adapters, backoff chỉ thực sự tạo ra độ tin cậy khi được đặt **đúng ranh giới handler**, kết hợp với timeout, retry budget, idempotency, transaction/ack, error handling và recovery bền vững. Mục tiêu cuối cùng không phải “thử lại thật nhiều”, mà là **phục hồi khi lỗi tạm thời mà không khuếch đại quá tải, mất message hoặc nhân đôi hiệu ứng nghiệp vụ**.
