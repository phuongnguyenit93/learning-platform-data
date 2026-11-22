# Kiểm tra retry không tạo bão gửi trong Spring Framework Mail

Một ứng dụng Spring có thể gửi email bất đồng bộ qua JavaMailSender, message broker hoặc transactional outbox. Khi SMTP relay hoạt động bình thường, vài chục worker có thể xử lý thông điệp rất nhanh. Tuy nhiên, nếu relay tạm từ chối, bị rate-limit hoặc mất kết nối, cơ chế thử lại (retry) thiết kế không đúng có thể biến một sự cố nhỏ thành **bão gửi (retry storm)**: các worker đồng loạt thử lại, tạo thêm kết nối, tăng hàng đợi, gây thêm timeout rồi tiếp tục retry.

Một bài kiểm tra retry hiệu quả không chỉ xác nhận rằng email được thử lại sau lỗi. Nó còn phải chứng minh rằng **mọi lần thử lại đều được giới hạn, phân tán theo thời gian, lưu trạng thái bền vững và không làm quá tải SMTP khi lỗi đang xảy ra hoặc khi relay vừa phục hồi**. Trong ngữ cảnh Spring Framework Mail, đây là bài toán phối hợp giữa phân loại lỗi SMTP, lịch retry, idempotency, rate limiting, concurrency, queue, state machine, và phép thử dưới tải.

> Nguyên tắc trung tâm: retry là một nguồn lưu lượng gửi email thực sự. Nó phải chịu cùng giới hạn tài nguyên và chính sách điều phối với email mới, không được bypass chỉ vì đó là một lần thử lại.

## 1. Retry storm là gì?

Giả sử một hệ thống đang có 2.000 email cần gửi. SMTP relay tạm thời không sẵn sàng. Nếu 100 worker nhận lỗi và ngay lập tức gọi lại send(), sẽ có thể xảy ra vòng lặp:

1. Nhiều worker cùng gửi SMTP.
2. Relay phản hồi tạm thời hoặc timeout.
3. Worker đồng loạt retry không chờ hoặc cùng chờ đúng một khoảng thời gian.
4. Relay tiếp tục nhận nhiều yêu cầu cùng lúc và ngày càng khó phục hồi.
5. Worker tạo thêm lần thử, chiếm thread, connection, bộ nhớ và quota.
6. Khi relay khôi phục, toàn bộ backlog cùng đổ vào tạo một đợt tải đột biến mới.

~~~mermaid
flowchart TD
    A["Nhiều email cần gửi"] --> B["SMTP bị lỗi / throttling"]
    B --> C["Worker retry đồng loạt"]
    C --> D["Tăng kết nối, timeout, queue"]
    D --> E["Relay tiếp tục quá tải"]
    E --> C
    E --> F["Outage kéo dài"]
~~~

Trong nhiều hệ thống, bão gửi xuất hiện do **đồng bộ hóa thời điểm retry**, không đơn thuần do có nhiều email. Nếu 10.000 job cùng đặt nextAttemptAt bằng thời điểm hiện tại cộng chính xác 60 giây, sau một phút sẽ có một đợt retry mới. Việc các job đều tuân theo một delay cố định không bảo đảm phân tán lưu lượng.

### Các nguyên nhân thường gặp

| Nguyên nhân | Hiện tượng | Hậu quả |
| --- | --- | --- |
| Retry ngay lập tức | Gửi lại trong vòng lặp khi send() lỗi | Tăng CPU, kết nối và số lần thử |
| Delay cố định giống nhau | Các job thất bại cùng lúc cũng retry cùng lúc | Thundering herd |
| Retry lồng nhiều lớp | Spring Retry, queue redelivery và worker đều retry | Nhân số lần gửi ngoài dự kiến |
| Không giới hạn số lần thử | Một record lỗi vĩnh viễn không bao giờ kết thúc | Queue và attempt history tăng liên tục |
| Retry không qua rate limiter | Khi relay phục hồi, hàng nghìn job đồng loạt gửi | Vượt quota, relay lại từ chối |
| Nhiều replica có limiter riêng | Mỗi pod nghĩ mình đang ở dưới ngưỡng | Tổng tốc độ toàn cụm vượt hạn mức |
| Hết lease đồng loạt | Nhiều record đang xử lý cùng được claim lại | Gửi trùng và tăng tải |
| Replay cả dead-letter queue | Một thao tác vận hành tạo burst lớn | Quá tải và mất kiểm soát |
| Không phân loại lỗi | Sai địa chỉ, sai mật khẩu cũng retry | Tốn quota mà không thể phục hồi |
| Không kiểm tra expiry | Email chiến dịch/OTP hết hạn vẫn được retry | Gửi muộn hoặc nội dung không còn hợp lệ |

### Vì sao phải kiểm tra cả điều kiện hồi phục?

Khi SMTP đang lỗi, nhiều hệ thống chỉ ghi RETRY_PENDING nên có vẻ ít hoạt động. Nhưng ngay khi SMTP phục hồi, tất cả record đến hạn có thể được chọn và gửi đồng thời. Vì vậy, bài test phải mô phỏng **trước lỗi, trong lỗi và sau phục hồi**. Một limiter chỉ hoạt động khi server đang lỗi là chưa đủ.

## 2. Xác định các bất biến cần được kiểm chứng

Trước khi viết test, hãy định nghĩa các quy tắc mà hệ thống bắt buộc phải giữ trong mọi tình huống.

| Bất biến | Nội dung cần chứng minh |
| --- | --- |
| Bounded attempts | Một thông điệp không vượt giới hạn retry đã cấu hình |
| Bounded throughput | Tổng số submit trong mọi cửa sổ không vượt quota được áp dụng |
| Bounded concurrency | Số lần gửi SMTP đang chạy không vượt số slot |
| Shared budget | Email mới, retry và replay dùng chung ngân sách SMTP |
| Durable scheduling | nextAttemptAt và attempt count sống qua process restart |
| Classified failures | Chỉ lỗi thích hợp mới retry; lỗi permanent dừng |
| Jitter | Retry từ các job cùng lỗi không hoàn toàn cùng một thời điểm |
| No hot loop | Khi thiếu permit, worker defer thay vì thử liên tục |
| No silent loss | Email giao dịch bắt buộc vẫn ở outbox cho tới trạng thái cuối phù hợp |
| No uncontrolled duplicate | Một job không bị claim đồng thời ở nhiều worker |
| Unknown outcome safety | Không tự coi kết quả SMTP không rõ là thất bại chắc chắn |
| Policy compliance | Consent, expiry, suppression và priority vẫn được kiểm tra trước retry |
| Auditable outcomes | Mọi lần thử có trạng thái, thời điểm và mã lỗi để điều tra |

**Không nên dùng “không có email trùng trong mọi tình huống” làm lời hứa tuyệt đối khi transport là SMTP thuần.** Nếu relay đã nhận DATA nhưng kết nối đứt trước phản hồi cuối, ứng dụng có thể không biết thư đã được chấp nhận hay chưa. Có thể giảm rủi ro duplicate bằng idempotency và đối soát, nhưng không tự bảo đảm exactly-once delivery end-to-end.

## 3. Cơ chế khuếch đại lưu lượng do retry

Hãy tách:

- **First attempts:** lần gửi đầu tiên cho từng notification.
- **Retry attempts:** những lần gửi bổ sung sau lỗi.
- **Resend:** yêu cầu gửi lại mới có chủ đích của người dùng/nhân viên vận hành.
- **Replay:** xử lý lại một bản ghi outbox hoặc dead-letter sau khi điều tra.

Nếu có N thông điệp, mỗi thông điệp được thử tối đa A lần (tính cả lần đầu), số lần submit tối đa về mặt lý thuyết là:

\[
T_{\max} = N \times A
\]

Ví dụ, 10.000 thông điệp với tối đa 5 attempts có thể tạo đến 50.000 lần thử SMTP trong một đợt lỗi. Nếu bên trong mỗi attempt của outbox còn có thư viện tự retry 3 lần, tổng số lần gọi transport có thể cao hơn dự kiến.

Một hệ thống cần quản lý **retry budget toàn cục** ngoài giới hạn attempts trên từng record. Ví dụ, trong một cửa sổ thời gian, chỉ cho retry tiêu thụ một tỷ lệ ngân sách nhất định để email mới quan trọng vẫn có khả năng gửi. Tỷ lệ cụ thể phải được chọn theo SLA và quota thực tế; không có con số mặc định phù hợp với mọi hệ thống.

### Retry amplification khi nhiều lớp cùng tham gia

~~~text
Outbox:      max 5 attempts
Spring Retry: max 3 attempts per outbox attempt
Broker:      redelivery có thể lặp theo policy
-----------------------------------------------
Tổng lời gọi SMTP có thể tăng ngoài 5 attempts mong muốn
~~~

Khi kiểm thử, cần xác định lớp nào sở hữu số lần thử tổng. Nếu adapter có retry ngắn cho network transient, phải tính các lần này vào ngân sách thực sự và bảo đảm retry lồng không làm vượt quota.

## 4. Phân loại lỗi: retry đúng mới tránh được bão gửi

Retry chỉ phù hợp với lỗi có khả năng phục hồi. Nếu lỗi là permanent hoặc do dữ liệu, thử lại nhiều lần chỉ tạo tải và log không cần thiết.

| Lỗi | Tình huống điển hình | Chiến lược |
| --- | --- | --- |
| Connection refused/tạm mất mạng | Relay không kết nối được | Retry có backoff, có thể dùng circuit breaker |
| SMTP 421 | Dịch vụ tạm không sẵn sàng | Retry có giới hạn; điều chỉnh tốc độ theo ngữ cảnh |
| SMTP 450/451/452 | Lỗi tạm thời khác nhau | Retry sau khi phân loại, không mặc định coi là rate limit |
| SMTP 4.7.x | Thường liên quan chính sách/tạm giới hạn tùy provider | Đọc mã và hướng dẫn cụ thể của provider |
| SMTP 5xx recipient | Địa chỉ bị từ chối vĩnh viễn | FAILED_PERMANENT/suppression theo policy |
| SMTP authentication failure | Sai credential, bị khóa quyền relay | Không retry liên tục; cảnh báo sửa cấu hình |
| Template not found/parse failure | Lỗi nội dung hoặc đóng gói resource | Dừng retry mù, sửa template rồi replay |
| MIME/attachment invalid | Tệp hoặc dữ liệu không hợp lệ | Sửa nguồn dữ liệu, không retry vô hạn |
| JavaMailSender đang chờ kết quả không rõ | Connection lost sau DATA | SUBMISSION_UNKNOWN, đối soát hoặc policy duplicate |
| Hết token rate limiter | Chưa gọi SMTP | Defer; không tính là SMTP failure attempt |
| Bị hủy/hết hạn/unsubscribe | Policy không cho phép gửi | CANCELLED/EXPIRED/SUPPRESSED |

### 4xx không đồng nghĩa luôn bị throttling

Mã 4xx thường thể hiện lỗi tạm thời, nhưng không phải mọi 4xx đều nói rằng server quá tải. Ví dụ, một mailbox tạm không khả dụng có thể là lỗi cục bộ, không cần giảm tốc độ toàn provider. Khi test adaptive throttling, dùng một lỗi đã được **bộ phân loại của ứng dụng xác định chắc chắn là throttling**, không dùng bất kỳ 4xx nào.

### SMTP không có header Retry-After kiểu HTTP

Khi dùng email provider qua HTTP API, phản hồi 429 có thể kèm Retry-After. SMTP không có HTTP header Retry-After chuẩn trong giao thức. Một provider có thể cung cấp chỉ dẫn retry trong enhanced status hoặc phần text phản hồi riêng, nhưng không nên viết code luôn tìm HTTP header từ một exception SMTP.

### Phân loại bằng adapter

Trong Spring, JavaMailSender có thể ném MailException hoặc các subclass bọc lỗi Jakarta Mail. Việc đọc SMTP status cần dựa trên exception/cause cụ thể của transport đã dùng. Tốt hơn nên chuẩn hóa:

~~~java
public enum FailureKind {
    TEMPORARY,
    THROTTLED,
    PERMANENT,
    CONTENT_ERROR,
    SUBMISSION_UNKNOWN
}

public record MailFailure(
        FailureKind kind,
        String code,
        boolean retryable
) {
}
~~~

Các giá trị này là model nội bộ. Việc ánh xạ exception vào MailFailure phải được kiểm tra bằng unit/integration test với adapter thực tế, không chỉ parse chuỗi message bằng regex.

## 5. Exponential backoff và jitter

**Exponential backoff** giãn thời gian giữa các lần thử. **Jitter** thêm độ phân tán để nhiều job không cùng retry vào một thời điểm.

Một công thức backoff có giới hạn:

\[
d_n = \min(d_{\max}, d_0 \cdot 2^{n-1})
\]

Trong đó:

- n là số lần thất bại đã hoàn tất (n bắt đầu từ 1).
- d0 là độ trễ cơ sở, ví dụ 1 giây.
- dmax là độ trễ tối đa, ví dụ 2 phút.

Với **full jitter**, delay được chọn trong một khoảng ngẫu nhiên từ 0 đến d_n. Tuy nhiên, trong một số hệ thống, delay có thể bằng 0 sẽ dẫn đến retry quá nhanh. Có thể đặt một ngưỡng tối thiểu nhỏ và chọn ngẫu nhiên trong khoảng [minimum, d_n] để tránh hot loop; đó là một biến thể thực tiễn, không còn là full jitter thuần túy.

### Ví dụ so sánh

| Job | Backoff cố định 60 giây | Backoff có jitter |
| --- | --- | --- |
| A | 10:01:00 | 10:00:24 |
| B | 10:01:00 | 10:00:41 |
| C | 10:01:00 | 10:00:57 |
| D | 10:01:00 | 10:00:36 |

Các thời điểm có jitter chỉ để minh họa. Mục tiêu không phải “ngẫu nhiên càng nhiều càng tốt”, mà là làm giảm số lần retry cùng dồn vào một thời điểm.

### Một implementation Java có thể kiểm thử

Ví dụ dưới đây nhận một nguồn random qua hàm, giúp test kiểm tra ranh giới mà không phải ngủ thật:

~~~java
package com.example.mail;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.LongUnaryOperator;

public final class RetryDelay {

    private final long initialMillis;
    private final long maxMillis;
    private final long minimumMillis;
    private final LongUnaryOperator randomBelow;

    public RetryDelay(
            Duration initial,
            Duration maximum,
            Duration minimum,
            LongUnaryOperator randomBelow) {

        this.initialMillis = initial.toMillis();
        this.maxMillis = maximum.toMillis();
        this.minimumMillis = minimum.toMillis();
        this.randomBelow = Objects.requireNonNull(randomBelow);

        if (minimumMillis < 0
                || initialMillis < 1
                || minimumMillis > initialMillis
                || initialMillis > maxMillis
                || maxMillis == Long.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid retry delays");
        }
    }

    public Duration afterFailures(int failureCount) {
        if (failureCount < 1) {
            throw new IllegalArgumentException(
                    "At least one failure is required");
        }

        long upperBound = initialMillis;
        for (int n = 1; n < failureCount; n++) {
            if (upperBound >= maxMillis) {
                break;
            }
            // Nhân đôi nhưng không gây overflow.
            upperBound = upperBound > maxMillis / 2
                    ? maxMillis
                    : Math.min(maxMillis, upperBound * 2);
        }

        long span = upperBound - minimumMillis + 1;
        long offset = randomBelow.applyAsLong(span);
        if (offset < 0 || offset >= span) {
            throw new IllegalStateException(
                    "Random source produced an invalid offset");
        }
        return Duration.ofMillis(minimumMillis + offset);
    }

    public static RetryDelay production() {
        return new RetryDelay(
                Duration.ofSeconds(1),
                Duration.ofMinutes(2),
                Duration.ofMillis(250),
                bound -> ThreadLocalRandom.current().nextLong(bound));
    }
}
~~~

Ý nghĩa:

- Lần thất bại thứ nhất có upper bound bằng initial.
- Những lần tiếp theo tăng upper bound theo cấp số nhân, tối đa bằng maximum.
- Random tạo offset trong khoảng hợp lệ.
- Delay luôn không âm và không nhỏ hơn minimum.
- Không dùng System.currentTimeMillis để đo khoảng chờ trong chính thuật toán.
- Test có thể truyền hàm luôn trả 0 hoặc trả bound - 1 để kiểm tra giới hạn.

Đây là lớp tính toán delay, không tự gửi email, không lưu outbox và không đảm bảo giới hạn lưu lượng toàn cụm. Jitter chỉ là **một lớp bảo vệ**; khi có 100.000 job đến hạn, vẫn cần một global rate limiter.

## 6. Giới hạn số attempts và tuổi thông điệp

Không nên chỉ dựa vào backoff để cho một message retry vô hạn. Mỗi notification cần:

- maxAttempts: số lần thử SMTP tối đa, bao gồm lần đầu.
- maxAge hoặc expiresAt: tuổi tối đa của notification.
- firstAttemptAt, lastAttemptAt và nextAttemptAt.
- failure kind, mã lỗi đã chuẩn hóa và trạng thái cuối.

Ví dụ policy:

~~~java
public record MailRetryPolicy(
        int maxAttempts,
        Duration maxAge,
        RetryDelay retryDelay
) {
    public MailRetryPolicy {
        if (maxAttempts < 1 || maxAge.isNegative()
                || maxAge.isZero()) {
            throw new IllegalArgumentException(
                    "Invalid retry policy");
        }
    }
}
~~~

Khi một lần gửi thất bại, lịch thử tiếp chỉ được tạo nếu:

1. Lỗi được phân loại là retryable.
2. Attempts hiện tại chưa đạt maxAttempts.
3. Notification chưa bị hủy hoặc suppress.
4. Thời điểm thử lại chưa vượt expiresAt.
5. Provider/account không đang bị disable theo policy.

### Một ví dụ timeline

~~~text
Created:          10:00:00
Attempt 1:        10:00:01  -> SMTP temporary failure
Attempt 2:        10:00:02  -> SMTP temporary failure
Attempt 3:        10:00:04  -> SMTP temporary failure
Attempt 4:        10:00:08  -> SMTP accepted
Status:           SUBMITTED
~~~

Đây chỉ là timeline minh họa; trong hệ thống có jitter, thời điểm thật khác nhau. Nếu một email OTP hết hiệu lực lúc 10:03, worker không được gửi nó vào 10:05 dù attempts vẫn còn.

### Đếm attempts thế nào cho nhất quán?

Một attempt nên đại diện cho **một lần ứng dụng thực sự bắt đầu submit SMTP**, không phải một lần scheduler nhìn thấy record. Thiếu token, không có slot hoặc bị circuit breaker từ chối trước khi gọi transport thường là **deferred**, không phải SMTP failure. Nếu adapter có retry nội bộ, các lần gọi transport đó vẫn cần được tính trong giới hạn ngân sách tổng hoặc được phản ánh rõ trong telemetry.

## 7. Lưu nextAttemptAt trong transactional outbox

Không dùng Thread.sleep() hoặc hàng nghìn scheduled future trong memory làm cơ chế retry bền vững. Nếu process restart, lịch retry trong bộ nhớ có thể biến mất. Một outbox record có thể chứa:

~~~java
public enum OutboxStatus {
    PENDING,
    PROCESSING,
    RETRY_PENDING,
    SUBMITTED,
    SUBMISSION_UNKNOWN,
    FAILED_PERMANENT,
    DEAD_LETTER,
    SUPPRESSED,
    EXPIRED
}

public record MailOutboxSnapshot(
        java.util.UUID id,
        String notificationType,
        OutboxStatus status,
        int attempts,
        java.time.Instant createdAt,
        java.time.Instant nextAttemptAt,
        java.time.Instant expiresAt,
        String lastErrorCode
) {
}
~~~

Một lần thử lỗi tạm thời có thể chuyển:

~~~text
PROCESSING
  -> record attempt failure
  -> calculate nextAttemptAt
  -> RETRY_PENDING
  -> commit transaction
~~~

Worker chỉ claim record khi nextAttemptAt không lớn hơn thời điểm hiện tại. Không giữ connection SMTP hoặc transaction database mở trong lúc chờ.

### Những trạng thái không được tự động retry

| Trạng thái | Có nên scheduler claim? |
| --- | --- |
| PENDING, đến hạn | Có |
| RETRY_PENDING, đến hạn | Có |
| PROCESSING còn lease | Không |
| SUBMITTED | Không |
| FAILED_PERMANENT | Không |
| DEAD_LETTER | Chỉ sau quyết định replay |
| SUBMISSION_UNKNOWN | Không retry mù |
| SUPPRESSED | Không |
| EXPIRED | Không |

Nếu một outbox record đã SUBMITTED nhưng user yêu cầu gửi lại hóa đơn, đó thường là một **resend request mới**, không phải việc reset trạng thái bản ghi cũ về PENDING.

## 8. Rate limiting: lớp bảo vệ không thể thiếu

Exponential backoff và jitter giảm thời điểm trùng nhau, nhưng không bảo đảm tổng lưu lượng nhỏ hơn quota provider. Một **token bucket hoặc sliding-window limiter toàn cụm** phải chặn việc submit khi không còn ngân sách.

Các giới hạn thường cần kết hợp:

| Giới hạn | Mục tiêu |
| --- | --- |
| Global messages/second | Không vượt quota một SMTP credential/provider |
| Global recipients/minute | Tính đúng quota người nhận |
| Max in-flight SMTP sends | Không mở quá nhiều kết nối/lần gửi đồng thời |
| Per-domain rate | Giảm burst tới một miền nhận |
| Per-tenant budget | Không để tenant lớn chiếm toàn bộ năng lực |
| Retry budget | Không để retry lấn hết email mới |
| Category reservation | Giữ năng lực cho OTP và email giao dịch |
| Daily quota | Không vượt hạn mức ngày |

**Limiter trên mỗi JVM không đủ** nếu ứng dụng chạy nhiều replica. N replica, mỗi replica tự cho 20 email/giây có thể tạo khoảng N × 20 email/giây. Cần dùng một limiter phân tán hoặc một cổng gửi tập trung có tổng ngân sách phù hợp.

### Mọi đường gửi phải đi qua cùng cổng

~~~mermaid
flowchart LR
    A["Email mới"] --> D["Shared dispatch gate"]
    B["Scheduled retry"] --> D
    C["Replay / resend"] --> D
    D --> E["Rate + concurrency + policy"]
    E --> F["JavaMailSender"]
    F --> G["SMTP relay"]
~~~

Không nên giới hạn chỉ trong REST API tạo email. Retry và replay thường chạy nền, có thể bỏ qua API đó. Cũng không nên tạo một worker đặc biệt cho dead-letter replay mà không có limiter.

### Khi không có permit

- Không gọi JavaMailSender.
- Không tăng attempts nếu chưa hề thử SMTP.
- Giữ hoặc đưa record về trạng thái chờ.
- Đặt một thời điểm kiểm tra lại hợp lý, tránh polling nóng.
- Không giữ hàng nghìn record ở PROCESSING chỉ để chờ token.

Nếu limiter service không khả dụng, chính sách an toàn thường là **defer dispatch và alert**, giữ dữ liệu trong outbox. Không bypass toàn bộ limiter rồi gửi vô hạn.

## 9. Concurrency limit và queue pressure

Rate limit giới hạn tốc độ trung bình; concurrency giới hạn số lời gọi send đang hoạt động. Hai cơ chế cần được test riêng.

Ví dụ guard bằng Semaphore:

~~~java
import java.util.concurrent.Semaphore;

public final class SmtpConcurrencyGate {
    private final Semaphore permits;

    public SmtpConcurrencyGate(int maxInflight) {
        if (maxInflight < 1) {
            throw new IllegalArgumentException("Invalid concurrency");
        }
        this.permits = new Semaphore(maxInflight);
    }

    public boolean tryEnter() {
        return permits.tryAcquire();
    }

    public void leave() {
        permits.release();
    }
}
~~~

Chỉ gọi leave sau khi tryEnter trả true; dùng finally khi đã lấy thành công slot. Nếu lệnh gửi ném exception mà không release slot, throughput có thể giảm dần tới 0.

### Không xếp retry vào executor vô hạn

Với Spring ThreadPoolTaskExecutor, cần cấu hình:

~~~java
@Configuration
@EnableAsync
public class MailExecutorConfig {

    @Bean("mailExecutor")
    ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();
        return executor;
    }
}
~~~

Đây là thông số minh họa; không phải giới hạn mặc định của Spring. Khi executor từ chối task, phải giữ notification trong outbox và reschedule, không coi tác vụ bị từ chối như email đã gửi. @Async cũng không phải durable queue: process dừng có thể làm mất task nằm trong memory. Worker nên claim batch nhỏ theo slot/permit khả dụng.

## 10. Claim record bằng lease: tránh retry cùng một email ở nhiều worker

Trong hệ thống nhiều worker, hai instance có thể cùng thấy một record đến hạn. Nếu cả hai gọi send() trước khi database ghi trạng thái PROCESSING, duplicate xảy ra ngay cả khi không có lỗi SMTP.

Worker nên dùng cơ chế **claim nguyên tử**:

1. Chọn record PENDING hoặc RETRY_PENDING đã đến hạn.
2. Gán PROCESSING, leaseOwner và leaseUntil trong transaction.
3. Commit transaction claim.
4. Gọi SMTP ngoài transaction.
5. Ghi kết quả trong một transaction riêng với kiểm tra leaseOwner/generation.

Với PostgreSQL, có thể dùng FOR UPDATE SKIP LOCKED cho một batch:

~~~sql
SELECT id
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_PENDING')
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY next_attempt_at, created_at
LIMIT 20
FOR UPDATE SKIP LOCKED;
~~~

Ví dụ chỉ là phần SELECT; ứng dụng cần UPDATE các record được claim trong cùng transaction trước khi commit. Cú pháp phụ thuộc database. Với hệ khác, có thể dùng compare-and-set bằng UPDATE có điều kiện, optimistic locking hoặc queue broker có cơ chế claim/ack phù hợp.

### Điều gì xảy ra khi worker chết?

Nếu worker bị kill sau khi claim, lease sẽ hết hạn. Hệ thống cần phục hồi record để tiếp tục xử lý. Nhưng **lease hết hạn không chứng minh email chưa được gửi**:

- Worker có thể chết trước khi gọi SMTP: retry an toàn theo nghĩa chưa submit.
- Worker có thể chết sau khi SMTP chấp nhận nhưng trước khi ghi SUBMITTED: kết quả không rõ.
- Worker có thể bị pause lâu, một worker khác claim lại, rồi worker cũ thức dậy: nguy cơ gửi trùng.

Cần test cả ba trường hợp. Những hệ thống đòi hỏi rủi ro duplicate rất thấp có thể dùng submission ledger, provider ID đối soát hoặc quy trình xử lý SUBMISSION_UNKNOWN thay vì retry tất cả lease hết hạn ngay lập tức.

### Fencing token hoặc generation

Khi claim, có thể tăng deliveryGeneration hoặc leaseVersion. Mỗi worker chỉ được cập nhật state nếu phiên bản trong database vẫn khớp phiên bản nó nhận được.

~~~sql
UPDATE mail_outbox
SET status = 'SUBMITTED',
    updated_at = CURRENT_TIMESTAMP
WHERE id = :messageId
  AND status = 'PROCESSING'
  AND lease_owner = :workerId
  AND lease_version = :claimedVersion;
~~~

Nếu số dòng cập nhật bằng 0, worker đã mất quyền ghi trạng thái và cần xử lý theo policy. Fencing tránh một worker cũ ghi đè trạng thái của worker mới, nhưng **không thể thu hồi email đã ra khỏi ứng dụng**. Nó không tự giải quyết exactly-once SMTP.

## 11. Luồng dispatcher an toàn trước retry storm

Một dispatcher có thể phối hợp status, classifier và dispatch gate như sau:

~~~text
pollDueRecords():
    nếu circuit breaker đang OPEN:
        không claim thêm
        ghi metric deferred
        return

    capacity = min(freeConcurrencySlots, smallBatchLimit)
    nếu capacity == 0:
        return

    records = claimDueWithLease(capacity)

    for each record:
        nếu đã hết hạn, bị hủy hoặc bị suppress:
            ghi trạng thái cuối; continue

        nếu không còn quota rate limit:
            release lease, giữ record và đặt nextAttemptAt mới
            KHÔNG tăng số SMTP attempts
            continue

        nếu không lấy được concurrency slot:
            defer record; continue

        try:
            render MIME, kiểm tra nội dung
            record started-attempt
            transport.submit()
            mark SUBMITTED
        catch classified temporary error:
            nếu hết attempts/expiry: mark DEAD_LETTER
            ngược lại: schedule retry với backoff + jitter
        catch permanent/content error:
            mark FAILED_PERMANENT
        catch ambiguous SMTP error:
            mark SUBMISSION_UNKNOWN
        finally:
            release concurrency slot
~~~

Không dùng một transaction database dài bao quanh toàn bộ vòng gửi. Nếu một batch có nhiều message, lỗi của một message không nên khiến các message đã được submit qua SMTP bị rollback trạng thái cùng nhau theo cách tạo duplicate hàng loạt.

### Đừng tự retry ngay trong catch

Đoạn code dưới đây tạo nguy cơ bão gửi:

~~~java
// Không nên áp dụng kiểu này:
while (true) {
    try {
        mailSender.send(message);
        break;
    } catch (MailException failure) {
        // Lặp tức thời; không backoff, không giới hạn.
    }
}
~~~

Ngay cả khi thêm Thread.sleep cố định, một nhóm worker lỗi cùng lúc vẫn có thể thức dậy cùng lúc. Hãy lưu nextAttemptAt và để scheduler dispatch theo quota dùng chung.

### Một ví dụ điều phối với các lớp có trách nhiệm rõ

~~~java
public interface SmtpTransport {
    void submit(MimeMessage message);
}

public interface RetryScheduler {
    void schedule(UUID notificationId, Instant when, String code);
    void permanentFailure(UUID notificationId, String code);
    void submissionUnknown(UUID notificationId, String code);
    void submitted(UUID notificationId);
}

public interface DispatchBudget {
    boolean tryAcquire(int recipientCount);
}
~~~

Các interface trên là adapter ứng dụng, không phải API có sẵn của Spring Mail. Adapter SmtpTransport có thể sử dụng JavaMailSender; RetryScheduler cập nhật outbox bằng transaction; DispatchBudget kiểm soát quota dùng chung.

Một worker được thiết kế tốt có thể kiểm thử mà không cần SMTP thật, vì có thể thay transport bằng fake trả lỗi theo kịch bản và thay Clock bằng đồng hồ điều khiển được.

## 12. Lập danh sách các phép thử trước khi triển khai

Một test suite phải kiểm tra **tính đúng đắn**, **khả năng chịu tải** và **khả năng phục hồi**.

| ID | Kịch bản | Điều phải chứng minh |
| --- | --- | --- |
| T01 | SMTP lỗi tạm thời một lần | Một retry được lên lịch, không gửi lại ngay |
| T02 | SMTP liên tục lỗi tạm thời | Delay tăng có giới hạn, không vượt maxAttempts |
| T03 | 1.000 job lỗi cùng lúc | nextAttemptAt được phân tán, không cùng dồn một timestamp |
| T04 | SMTP lỗi vĩnh viễn | Không retry, record chuyển terminal state |
| T05 | Lỗi template/MIME | Không gửi lại mù; cần sửa dữ liệu/template |
| T06 | Không có rate token | Defer, không gọi SMTP và không tăng attempts |
| T07 | Concurrency đầy | Không vượt in-flight limit, không mất job |
| T08 | Nhiều replica | Tổng tốc độ không vượt quota dùng chung |
| T09 | Worker chết khi đang PROCESSING | Lease recovery có kiểm soát |
| T10 | Relay phục hồi sau outage | Backlog được xả theo rate, không tạo surge |
| T11 | Retry và email mới đồng thời | Tổng throughput vẫn trong budget |
| T12 | Retry cùng với manual replay | Không bypass limiter hoặc duplicate scheduler |
| T13 | Provider trả throttling | Giảm tốc và retry có backoff/jitter |
| T14 | Email hết hạn trước retry | Đánh dấu EXPIRED, không gửi |
| T15 | Người nhận unsubscribe | SUPPRESSED; không gọi SMTP |
| T16 | Kết quả SMTP không rõ | Không tự đánh dấu gửi thất bại chắc chắn rồi retry bừa |
| T17 | Outbox restart | nextAttemptAt, attempts và status được giữ nguyên |
| T18 | Retry lồng nhiều lớp | Tổng lời gọi thực không vượt budget mong đợi |
| T19 | Hàng đợi quá tải | Không tạo thread/task/record PROCESSING không giới hạn |
| T20 | SMTP tạm phục hồi rồi lỗi lại | Circuit breaker/rate limiter vẫn giới hạn các lần thử |

Mỗi test cần một **quan sát đo được**: số lần submit, thời điểm attempts, trạng thái outbox, max in-flight, số token đã cấp, tuổi backlog và tỷ lệ lỗi. Chỉ kiểm tra rằng “sau một lúc email được gửi” là chưa đủ.

## 13. Unit test tính backoff mà không dùng Thread.sleep

Độ trễ ngẫu nhiên dễ làm test flaky nếu gọi Thread.sleep và đo thời gian thực. Cách tốt hơn là inject nguồn random hoặc clock.

### Kiểm tra ranh giới jitter

Với lớp RetryDelay đã trình bày:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class RetryDelayTest {

    @Test
    void delayRemainsWithinConfiguredBounds() {
        RetryDelay lowest = new RetryDelay(
                Duration.ofSeconds(1),
                Duration.ofSeconds(8),
                Duration.ofMillis(250),
                bound -> 0L);

        RetryDelay highest = new RetryDelay(
                Duration.ofSeconds(1),
                Duration.ofSeconds(8),
                Duration.ofMillis(250),
                bound -> bound - 1);

        assertEquals(Duration.ofMillis(250),
                lowest.afterFailures(1));
        assertEquals(Duration.ofSeconds(1),
                highest.afterFailures(1));
        assertEquals(Duration.ofSeconds(2),
                highest.afterFailures(2));
        assertEquals(Duration.ofSeconds(8),
                highest.afterFailures(20));
    }

    @Test
    void requiresAtLeastOneFailure() {
        RetryDelay retry = RetryDelay.production();
        assertThrows(IllegalArgumentException.class,
                () -> retry.afterFailures(0));
    }
}
~~~

Những phép thử này kiểm tra **giới hạn thuật toán** với nguồn random tất định. Chúng không chứng minh jitter thực tế phân bố đều theo thời gian khi có 10.000 notification. Điều đó cần một test khác ở cấp scheduler hoặc tải.

### Kiểm tra nhiều job không cùng một timestamp

Một test scheduler có thể:

1. Tạo 1.000 notification cùng fail tại cùng thời điểm.
2. Cấp một nguồn random có seed cố định hoặc chuỗi offset biết trước.
3. Tính nextAttemptAt cho mỗi record.
4. Nhóm record theo các bucket thời gian nhỏ.
5. Xác nhận scheduler không đặt toàn bộ vào cùng một bucket và global limiter vẫn bảo vệ throughput.

Không đặt kỳ vọng xác suất quá chặt trên một random seed tùy ý. Đối với kiểm thử thuật toán, dùng dữ liệu determinisitic; đối với kiểm thử tính chất phân phối, chạy nhiều seed hoặc dùng mô phỏng có điều kiện thống kê phù hợp.

## 14. Dùng Clock giả để kiểm thử lịch retry

Đồng hồ giả cho phép test “tiến thời gian” trong vài mili giây thực thi mà không phải chờ phút hoặc giờ.

Ví dụ một Clock có thể điều chỉnh:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.concurrent.atomic.AtomicReference;

public final class MutableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public MutableClock(Instant initial, ZoneId zone) {
        this.current = new AtomicReference<>(initial);
        this.zone = zone;
    }

    public void advance(Duration amount) {
        if (amount.isNegative()) {
            throw new IllegalArgumentException("Cannot go backward");
        }
        current.updateAndGet(now -> now.plus(amount));
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new Clock() {
            @Override public Instant instant() {
                return MutableClock.this.instant();
            }
            @Override public ZoneId getZone() {
                return newZone;
            }
            @Override public Clock withZone(ZoneId z) {
                return MutableClock.this.withZone(z);
            }
        };
    }
}
~~~

Class minh họa dùng cùng một instant có thể cập nhật và hỗ trợ zone khác nhau. Trong production, sử dụng Clock.systemUTC() hoặc nguồn thời gian phù hợp; trong test, dùng MutableClock.

### Luồng test với thời gian ảo

~~~text
now = 10:00:00
outbox message is PENDING

worker.dispatch() -> SMTP 421
assert status == RETRY_PENDING
assert nextAttemptAt > 10:00:00
assert submitCount == 1

worker.dispatch() at 10:00:00
assert submitCount == 1     // Chưa đến hạn

clock.advance(nextAttemptAt - now)
worker.dispatch() -> SMTP accepted
assert status == SUBMITTED
assert submitCount == 2
~~~

Nếu scheduler tự dùng Instant.now() ở nhiều chỗ, test khó kiểm soát đồng hồ và các instance có thể không cùng tiêu chuẩn thời gian. Inject Clock vào các component tạo nextAttemptAt và so sánh thời điểm, hoặc dùng thời gian database một cách nhất quán cho thao tác claim.

### Cẩn trọng với clock skew giữa các worker

Trong hệ phân tán, clock của các instance có thể lệch nhau. Đừng chỉ dựa vào so sánh ở local clock để claim lease nếu database dùng đồng hồ khác. Có thể tính lease và hạn xử lý bằng thời gian database hoặc đồng bộ thời gian đáng tin cậy, rồi test trường hợp instance nhanh/chậm hơn vài giây. Clock skew không nên làm record được claim lại quá sớm hoặc bị kẹt lâu ngoài SLA.

## 15. Test số lần gọi transport và retry nhiều lớp

Giả sử outbox cho tối đa ba attempts, còn lớp transport cũng có một retry annotation. Nếu test chỉ nhìn attempts trong database, nó có thể cho kết quả 3 nhưng thực tế SMTP bị gọi đến 9 lần.

Một test cần đếm **số lần gọi transport thật**:

~~~java
@Test
void doesNotMultiplyTransportRetriesUnexpectedly() {
    when(transport.submit(any()))
            .thenThrow(new TemporarySmtpException("421"));

    // Giả định dispatcher được chạy với policy maxAttempts = 3.
    simulateAllDueAttemptsThroughDispatcher();

    verify(transport, times(3)).submit(any());
    assertEquals(3, outboxRecord.getAttempts());
}
~~~

Các class và hàm simulate ở đây minh họa cấu trúc test. Điều cần đo là số cuộc gọi SMTP trên cùng notification, không chỉ số lần scheduler nhìn thấy record.

Nếu có retry nội bộ ở adapter, có thể sửa expectation cho đúng policy, nhưng số lần gọi tối đa phải được **công khai và giới hạn**. Nếu broker tự redeliver message khi worker ném exception, cần phối hợp ack, nack, backoff và outbox state để không phát sinh hai scheduler retry độc lập.

### Test khi message bị broker redeliver

Tạo cùng message ID đến consumer hai lần, cả hai lần đều cố xử lý. Kết quả mong đợi:

- Lần đầu claim được hoặc đã hoàn tất.
- Lần sau thấy record không còn đủ điều kiện hoặc lease không hợp lệ.
- Không tạo hai notification record mới.
- Không cho hai worker cùng gửi trong trường hợp có thể kiểm soát bằng claim.

Đừng dùng một biến boolean local để deduplicate khi hệ thống có nhiều replica; trạng thái/idempotency cần được lưu bền vững.

## 16. Kiểm thử concurrency bằng latch thay vì sleep

Để chứng minh số lần send đồng thời không vượt giới hạn, có thể dùng fake transport giữ các cuộc gọi tại một điểm đồng bộ bằng CountDownLatch.

Ý tưởng:

~~~java
AtomicInteger inFlight = new AtomicInteger();
AtomicInteger maxObserved = new AtomicInteger();

void simulatedSmtpSend() {
    int now = inFlight.incrementAndGet();
    maxObserved.accumulateAndGet(now, Math::max);
    try {
        releaseLatch.await();
    } finally {
        inFlight.decrementAndGet();
    }
}
~~~

Trong test, khởi động nhiều task cố gọi send cùng lúc, chỉ cho những task đã lấy được concurrency slot vào simulatedSmtpSend. Khi các task đồng thời chờ trên latch, xác nhận maxObserved không lớn hơn cấu hình.

Các điểm test cần xử lý:

- Dùng timeout cho latch để tránh test treo vô hạn khi có lỗi.
- Xả latch trong finally của test.
- Tạo đủ task để thực sự có contention.
- Kiểm tra slot được trả lại sau một exception.
- Xác nhận task bị thiếu slot sẽ defer chứ không tự tạo vòng lặp nóng.

Chỉ đo tổng thời gian hoàn thành không đủ chứng minh concurrency. Cần đo **số in-flight tối đa**.

## 17. Kiểm thử rate limit theo cửa sổ thời gian

Với provider cho phép tối đa R lần submit trong một cửa sổ W, test cần kiểm tra:

\[
\text{submitCount}(t-W,\ t] \le R
\]

Trong môi trường test, số lần gọi phải được ghi cùng timestamp từ clock mô phỏng. Sau đó quét các cửa sổ trượt để bảo đảm không vượt R. Nếu limiter là token bucket cho phép burst, tiêu chí phải phản ánh **cả tốc độ refill lẫn burst capacity**; không dùng một tiêu chí sliding window cứng rồi kết luận sai một thuật toán token bucket được cấu hình cho phép burst.

### Ví dụ acceptance criteria cho một test load

Giả sử cấu hình thử nghiệm:

- Global bucket refill: 10 token/giây.
- Burst capacity: 20 token.
- Max concurrent submits: 4.
- Mỗi message tiêu thụ 1 token.

Sau khi bắt đầu với bucket đầy, một số message có thể được submit thành burst. Trong một khoảng T giây, số permit được cấp tối đa theo mô hình token bucket xấp xỉ:

\[
\text{granted}(T) \le 20 + 10T
\]

Đây là **giới hạn trong mô hình kiểm thử**, không phải quota mặc định của SMTP provider. Khi test ở ranh giới thời gian cần chú ý rounding/timestamp resolution; có thể kiểm chứng trực tiếp log cấp token của limiter. Số in-flight đồng thời phải không vượt 4.

Nếu có năm replica, chúng **vẫn phải chia cùng** bucket 20/10, chứ không phải mỗi replica có bucket riêng.

### Test limiter phân tán

Một integration test với Redis hoặc limiter store thực có thể:

1. Tạo N worker chạy đồng thời, mỗi worker lấy permit.
2. Dùng một shared key đại diện SMTP credential.
3. Đếm tổng số permit đã cấp theo cửa sổ.
4. Kiểm tra không vượt cấu hình.
5. Giả lập một worker dừng rồi khởi động lại.
6. Xác nhận limiter không reset quota vì JVM restart.

Không dùng chỉ mock Redis rồi kết luận atomicity của Lua script hoặc transaction thật đã được xác minh. Cần test với store phù hợp khi tính nguyên tử là yêu cầu quan trọng.

## 18. Fault injection: SMTP lỗi hàng loạt rồi phục hồi

Đây là phép thử quan trọng để phát hiện retry storm. Hãy dùng một SMTP fake/test relay hoặc adapter transport có thể thay đổi trạng thái theo thời gian. Không thực hiện thí nghiệm quá tải trên SMTP production.

### Kịch bản A: outage hoàn toàn

Giả định môi trường kiểm thử có:

- 5.000 notification PENDING trong outbox.
- 4 worker replica.
- Global budget 10 message/giây, burst capacity 20.
- Max in-flight sends 4.
- SMTP fake trả lỗi tạm thời trong 3 phút.
- Retry policy tối đa 5 attempts, backoff có jitter.

Trình tự:

1. Bắt đầu worker và cho SMTP fake trả lỗi TEMPORARY.
2. Đo submit count theo thời gian, số attempt của mỗi record và số record RETRY_PENDING.
3. Cho clock tiến qua các thời điểm retry.
4. Quan sát worker có tôn trọng limiter khi retry hay không.
5. Sau 3 phút thời gian giả lập, chuyển SMTP fake sang ACCEPT.
6. Tiếp tục chạy cho đến khi backlog được xử lý hoặc các record đạt trạng thái cuối.

Kết quả mong đợi:

- Tổng số lần submit trên toàn cụm không vượt ngân sách của limiter.
- Max in-flight không vượt 4.
- Trong outage, attempt không tăng vô hạn.
- Không có vòng lặp retry với delay bằng 0 ngoài policy.
- Sau phục hồi, backlog giảm có kiểm soát thay vì phát burst vô hạn.
- Những record quá attempts có thể chuyển DEAD_LETTER; không phải tất cả 5.000 record đều chắc chắn SUBMITTED vì policy đã giới hạn số lần thử.
- Lịch sử attempt và trạng thái cuối phải nhất quán.

Không nên đặt kỳ vọng 5.000 email chắc chắn gửi xong chỉ vì relay đã phục hồi. Nếu nhiều bản ghi đã đạt maxAttempts trước khi phục hồi, chúng cần quy trình replay sau can thiệp.

### Kịch bản B: tỷ lệ lỗi cao nhưng không phải 100%

Thiết lập fake SMTP phản hồi theo chuỗi cố định:

~~~text
10 attempts:
  2 ACCEPT
  7 TEMPORARY_FAILURE
  1 PERMANENT_FAILURE
~~~

Phép thử phải xác nhận:

- Các message ACCEPT chuyển SUBMITTED.
- Các message temporary retry theo policy, không cùng thời điểm.
- Message permanent dừng lại.
- Limiter tính cả những attempts thất bại đã thực sự gửi tới relay.
- Retry và first attempts cạnh tranh quota có kiểm soát.
- Số lần tạo notification không tự tăng do retry.

Sử dụng chuỗi phản hồi được lập trình sẵn hoặc seed cố định để test có thể tái lập. Một random generator không cố định có thể làm test load không ổn định.

### Kịch bản C: relay phục hồi nhưng quota giảm

Một outage có thể được giải quyết bằng việc chuyển sang provider có quota thấp hơn. Nếu hệ thống lập tức dùng tốc độ cũ, provider dự phòng cũng có thể bị rate-limit.

Test:

1. Relay A bị lỗi.
2. Route sang relay B với hạn mức thấp hơn.
3. Có backlog lớn và các job retry đến hạn.
4. Kiểm tra total submit tới B không vượt quota B.
5. Sau khi A phục hồi, kiểm tra quá trình chuyển route không gửi cùng record hai lần ngoài policy.

Không coi failover là lý do bỏ qua limiter. Mỗi provider/account phải có ngân sách riêng và tổng worker vẫn tuân theo trạng thái outbox.

## 19. Test circuit breaker và ngăn bão sau khi mở lại

Circuit breaker giúp dừng gọi SMTP khi provider đang outage diện rộng. Nó có ba trạng thái khái niệm:

~~~text
CLOSED -- lỗi diện rộng vượt ngưỡng --> OPEN
OPEN   -- hết thời gian tạm dừng -----> HALF_OPEN
HALF_OPEN -- probe thành công ---------> CLOSED
HALF_OPEN -- tiếp tục lỗi ------------> OPEN
~~~

Khi OPEN, worker nên giữ job trong outbox và không gọi SMTP. Khi HALF_OPEN, chỉ cho một số probe gửi thử. Khi CLOSED trở lại, **rate limiter vẫn phải hoạt động**, vì backlog sau outage có thể rất lớn.

### Những phép thử cần có

| Kịch bản | Kỳ vọng |
| --- | --- |
| Provider timeout liên tục | Breaker mở theo ngưỡng |
| Breaker OPEN | Không có submit mới, job vẫn bền vững |
| HALF_OPEN | Chỉ số probe giới hạn được phép |
| Probe thất bại | Breaker trở lại OPEN |
| Probe thành công | Breaker đóng theo policy |
| Breaker đóng, backlog lớn | Drain vẫn qua rate limiter/concurrency gate |
| Một recipient bị 550 | Không mở breaker toàn provider chỉ vì lỗi riêng |

Circuit breaker không phải công cụ duy nhất để nhận biết throttling; phản hồi rate-limit đôi khi cần **giảm tốc độ** thay vì mở breaker hoàn toàn. Lớp phân loại lỗi phải quyết định tín hiệu nào dùng để giảm rate, mở breaker hoặc đánh dấu lỗi permanent.

## 20. Retry budget để tránh chiếm hết năng lực của email mới

Giả sử SMTP đã phục hồi và có 10.000 retry đang chờ. Nếu tất cả quota được dùng cho retry, những email OTP mới có thể bị chậm cho đến khi backlog cũ được xử lý hết.

Một chiến lược là tách ngân sách:

- Global provider limit: không vượt tổng quota.
- Reserved capacity: bảo vệ email bảo mật/giao dịch mới.
- Retry budget: giới hạn tỷ lệ permit dùng cho retry.
- Optional campaign budget: không để marketing chiếm hết năng lực.
- Fairness per tenant: một tenant không độc chiếm.

~~~text
                 Global SMTP budget
                         |
            +------------+------------+
            |            |            |
         New urgent    New normal     Retry pool
            |            |            |
            +------------+------------+
                         |
                  Shared concurrency
                         |
                    SMTP relay
~~~

Các nhánh vẫn phải nằm trong giới hạn global. Không cấp quota riêng cho từng nhánh theo cách tổng vượt ngân sách provider.

### Test priority dưới backlog

1. Tạo 20.000 email marketing RETRY_PENDING.
2. Tạo 10 email OTP PENDING khi backlog đã lớn.
3. Cho fake SMTP ACCEPT.
4. Chạy worker với global limiter.
5. Đo thời gian từ OTP được tạo đến lúc được SUBMITTED.
6. Kiểm tra OTP nằm trong SLO của môi trường thử nghiệm.
7. Kiểm tra email marketing không bị bỏ âm thầm; chúng chờ hoặc hết hạn theo policy.

Không kiểm tra priority chỉ bằng thứ tự lấy record trong một batch. Cần đo **end-to-end queue latency** vì nhiều worker/queue có thể tác động tới kết quả.

### Tránh starvation

Ưu tiên tuyệt đối cũng có rủi ro: nếu email khẩn cấp luôn đến với lưu lượng cao, email giao dịch thông thường sẽ không được gửi. Có thể dùng weighted fair scheduling hoặc reserved capacity có cơ chế mượn quota. Test phải xác nhận nhóm thấp vẫn được xử lý trong giới hạn thời gian được cam kết khi năng lực còn phù hợp.

## 21. Thử nghiệm SMTP có kết quả không xác định và idempotency

Một bài test retry storm chưa đầy đủ nếu bỏ qua trường hợp SMTP đã nhận thông điệp nhưng client không nhận được xác nhận.

### Cửa sổ không chắc chắn sau DATA

~~~text
Mail worker                SMTP relay
    |                          |
    |----- MAIL/RCPT/DATA ---->|
    |                          | Accept message
    |<---- final response -----X  Network drops
    |
    | Không biết relay đã nhận hay chưa
~~~

Nếu worker tự chuyển record về RETRY_PENDING rồi gửi lại ngay, người nhận có thể nhận hai email. Cách xử lý:

- Phân biệt lỗi chắc chắn trước submit với lỗi không rõ kết quả.
- Dùng trạng thái SUBMISSION_UNKNOWN khi phù hợp.
- Lưu notification ID, attempt ID và provider message ID nếu có.
- Đối soát với provider event/API nếu nền tảng cho phép.
- Chỉ retry sau khi áp dụng policy duplicate của nghiệp vụ.

### Test tình huống này

Fake transport cần hỗ trợ hành vi:

1. Ghi nhận rằng phía relay đã nhận message.
2. Ném exception mô phỏng mất phản hồi cuối.
3. Dispatcher nhận exception thuộc loại outcome unknown.
4. Xác nhận record chuyển SUBMISSION_UNKNOWN, không lập tức trở lại PENDING.
5. Kiểm tra worker khác không claim record SUBMISSION_UNKNOWN tự động.

Nếu provider có API idempotency hỗ trợ khóa ổn định, test rằng retry dùng cùng key; nếu dùng SMTP trực tiếp, không giả định header Message-ID giúp loại trùng tuyệt đối.

### Idempotency key trong database

Một khóa nghiệp vụ có thể là:

~~~text
ORDER_CONFIRMED:order-184:recipient-42
~~~

Unique constraint giúp hai consumer cùng nhận một event không tạo hai notification record cho cùng một mục tiêu. Tuy nhiên, unique constraint **không bảo đảm** relay không chấp nhận hai lần submit cùng record khi client bị timeout ở thời điểm không chắc chắn.

### Test race condition khi enqueue

Cho hai thread đồng thời tạo notification với cùng idempotency key. Một transaction thắng; transaction còn lại phải nhận record hiện có hoặc xử lý unique constraint violation có kiểm soát. Không được tạo hai bản ghi gửi song song.

### Retry OTP và reset token

Nếu email chứa OTP hoặc reset link, retry cùng notification thường phải dùng challenge/token còn hiệu lực theo policy. Không tạo token mới cho mỗi lần gọi SMTP. Khi token hết hạn, record cần EXPIRED hoặc được thay bằng một yêu cầu mới; không gửi lại nội dung đã hết tác dụng chỉ vì còn attempts.

## 22. Kiểm tra expiry, consent và suppression ngay trước retry

Một thông điệp có thể đủ điều kiện lúc enqueue nhưng không còn được phép gửi lúc retry.

Ví dụ:

~~~text
10:00  User đăng ký nhận newsletter
10:01  Newsletter được enqueue
10:02  SMTP outage, job RETRY_PENDING
10:05  User unsubscribe
10:10  SMTP phục hồi, job đến hạn
10:10  Worker re-check preference -> SUPPRESSED
~~~

Kết quả đúng là **không gửi email marketing**. Worker không nên chỉ dựa vào consent snapshot lúc tạo job nếu chính sách yêu cầu tôn trọng unsubscribe mới nhất.

Các kiểm tra trước dispatch:

- Notification còn trong thời hạn.
- Recipient còn hợp lệ và được phép nhận.
- Consent/preferences hiện tại cho phép với email tùy chọn.
- Không nằm trong suppression list.
- Attachment hoặc resource đã được phê duyệt và vẫn đúng version.
- Token hoặc link nhạy cảm còn hiệu lực.
- Template/payload đúng version theo chính sách.

### Test không tăng attempts cho suppression

Nếu worker phát hiện người nhận vừa unsubscribe trước khi gọi SMTP, đó là một quyết định nghiệp vụ, không phải một lần thử gửi thất bại. Record chuyển SUPPRESSED, không gọi transport và không tăng số attempts thực.

### Không gửi email khuyến mại hết hạn

Khi chiến dịch kết thúc, backlog retry của chiến dịch không nên được giải phóng ồ ạt. Đánh dấu EXPIRED và dừng. Điều này vừa tránh gửi nội dung sai thời điểm vừa giảm áp lực lên SMTP.

## 23. Kiểm thử khi application restart và triển khai nhiều phiên bản

Lịch retry cần sống qua restart/deploy. Nếu worker dựa trên ScheduledFuture hoặc delay queue trong memory, khi process dừng, kế hoạch retry có thể bị mất. Nếu application khởi động lại và đọc tất cả FAILED như PENDING, nó có thể tạo một đợt bão gửi.

### Kịch bản restart

1. Cho SMTP fake trả lỗi tạm thời.
2. Worker ghi RETRY_PENDING, attempts = 1 và nextAttemptAt trong tương lai.
3. Dừng worker/process.
4. Khởi động lại một worker mới với cùng database.
5. Trước nextAttemptAt, không được gọi SMTP.
6. Tại/sau nextAttemptAt, worker claim đúng record qua rate limiter.
7. Xác nhận attempt history không bị reset.

### Kịch bản rolling deployment

Trong rolling update, một số pod mới và cũ có thể cùng chạy. Test:

- Chúng dùng chung limiter global.
- Claim record không bị duplicate giữa hai phiên bản.
- Outbox schema tương thích trong giai đoạn chuyển tiếp.
- Không reset nextAttemptAt khi deploy.
- Không chạy một migration làm hàng nghìn record RETRY_PENDING trở thành PENDING cùng lúc.
- Lease của worker cũ được xử lý theo policy khi pod bị dừng.

### Test chênh lệch đồng hồ

Nếu mỗi instance tính lease hoặc nextAttemptAt theo clock riêng, một pod nhanh hơn có thể claim record sớm. Dùng database time hoặc chiến lược time synchronization nhất quán, và test với worker clock lệch trong khoảng rủi ro đã xác định.

## 24. Tích hợp SMTP test server và chaos testing

Unit test cho phép kiểm tra backoff, policy và trạng thái. Để phát hiện lỗi ở ranh giới Spring Mail/Jakarta Mail, cần thêm integration test với một SMTP server test có thể trả các phản hồi được chỉ định.

### Môi trường kiểm thử nên tách biệt

- Không dùng mailbox người dùng thật.
- Không dùng credential SMTP production.
- Không gửi lưu lượng stress đến provider thật khi chưa có môi trường/tài khoản test được cho phép.
- Dùng fake transport, SMTP capture server hoặc dịch vụ thử nghiệm được cấu hình rõ.
- Tách database, queue, Redis và metric của bài test khỏi môi trường production.

Có thể sử dụng thư viện SMTP test hoặc một fake server tự triển khai cho các phản hồi đặc biệt. Một SMTP capture server chỉ nhận thư thành công không đủ để test 421/451, drop connection giữa DATA và phản hồi cuối, hoặc delay bất thường; cần một server/fault injector có khả năng điều khiển các giai đoạn này.

### Một ma trận fault injection

| Điểm gây lỗi | Phép thử | Kỳ vọng |
| --- | --- | --- |
| Trước khi connect | Connection refused | Retry có backoff, attempts hữu hạn |
| Trong TLS handshake | Timeout hoặc lỗi chứng chỉ | Phân loại đúng; lỗi cấu hình chứng chỉ không retry mù |
| Sau kết nối, trước DATA | Server trả 421 | Retryable, không burst |
| Khi RCPT TO | Một recipient bị từ chối permanent | Không retry vô hạn recipient đó |
| Sau khi server nhận DATA | Cắt kết nối trước phản hồi cuối | SUBMISSION_UNKNOWN |
| Khi ghi outbox state | Database tạm lỗi | Không biến thành hàng nghìn resend không kiểm soát |
| Khi limiter thiếu token | Token unavailable | Defer, không gọi SMTP |
| Khi Redis limiter outage | Shared gate unavailable | Không bypass quota toàn cụm |
| Khi worker kill | PROCESSING bị ngắt | Lease/state recovery có kiểm soát |
| Khi relay vừa phục hồi | Backlog lớn | Drain theo rate, không spike |

### Network latency và message size

Ngoài exception, hãy mô phỏng SMTP chậm. Một lệnh send có attachment lớn có thể kéo dài hơn một email text. Nếu concurrency gate không giới hạn, lượng memory và kết nối có thể tăng mạnh. Test kết hợp:

- Các message lớn/nhỏ.
- Thời gian phản hồi ngắn/dài.
- Số worker khác nhau.
- Quota recipient và message.
- Backlog lâu ngày đến hạn cùng thời điểm.

Một pipeline ổn định phải giữ được giới hạn in-flight và không đưa vô hạn task vào executor dù SMTP rất chậm.

## 25. Đo lường để phát hiện bão gửi trong vận hành

Để biết retry đang gây tải hay không, cần phân biệt first attempts, retry attempts, suppressed và provider failures.

| Metric gợi ý | Cách sử dụng |
| --- | --- |
| mail_first_attempts_total | Số lần thử đầu tiên |
| mail_retry_attempts_total | Lưu lượng retry |
| mail_smtp_submissions_total | Tổng số lần gọi SMTP được thực hiện |
| mail_smtp_temporary_failures_total | Lỗi có thể thử lại |
| mail_smtp_permanent_failures_total | Lỗi vĩnh viễn |
| mail_smtp_unknown_total | Kết quả submit không rõ |
| mail_rate_limited_total | Số lần bị defer vì thiếu token |
| mail_inflight_sends | Số lần submit đang hoạt động |
| mail_outbox_pending | Số message đang chờ |
| mail_outbox_oldest_age_seconds | Tuổi message chờ lâu nhất |
| mail_retry_pending | Số job chờ retry |
| mail_dead_letter_total | Số job chuyển dead-letter |
| mail_retry_schedule_lag_seconds | Độ lệch giữa nextAttemptAt và lúc worker thực sự xử lý |
| mail_limiter_available_tokens | Mức permit còn lại, nếu exporter cung cấp |
| mail_circuit_breaker_state | Trạng thái breaker |
| mail_dispatch_latency_seconds | Độ trễ submit |

Tên metric do ứng dụng tự định nghĩa; có thể triển khai bằng Micrometer và Spring Boot Actuator. Không sử dụng full email address, notification ID hay SMTP transcript làm metric label, vì vừa lộ dữ liệu vừa tạo cardinality rất cao.

### Tỷ lệ retry

Một metric hữu ích:

\[
\text{retryRatio} =
\frac{\text{retryAttempts}}{\text{firstAttempts}+\text{retryAttempts}}
\]

Nếu retryRatio tăng đột biến, có thể có sự cố transport/provider hoặc một lỗi hệ thống. Tuy nhiên, đừng tự kết luận “bão gửi” chỉ từ tỷ lệ: một hệ thống ít lưu lượng có thể có tỷ lệ 50% với số lần thử rất nhỏ. Cần xem thêm **tổng attempts/giây, backlog, throttling và in-flight**.

### Retry storm alert

Một alert có thể kết hợp:

- Tổng attempt throughput gần chạm hoặc vượt ngưỡng kiểm soát.
- Retry attempt rate tăng nhanh so với baseline.
- SMTP 4xx/throttling tăng.
- Tuổi backlog tăng.
- Retry queue đến hạn nhiều cùng thời điểm.
- Circuit breaker mở/đóng liên tục.

Thông số alert phụ thuộc SLA và năng lực provider. Không dùng một ngưỡng chung cho OTP và marketing.

## 26. Log và audit của mỗi attempt

Một bản ghi attempt nên có:

~~~json
{
  "notificationId": "notification-184",
  "attemptNumber": 3,
  "kind": "RETRY",
  "outcome": "SMTP_TEMPORARY_FAILURE",
  "smtpCode": "421",
  "scheduledFor": "2026-11-12T09:00:40Z",
  "startedAt": "2026-11-12T09:00:41Z",
  "nextAttemptAt": "2026-11-12T09:02:17Z",
  "providerKey": "transactional-primary"
}
~~~

Đây là schema log minh họa, không phải output mặc định của Spring. Dữ liệu log nên đủ để tra cứu và tái lập lịch retry, nhưng không lưu password SMTP, OTP, reset token, body hoặc attachment bytes. Nếu SMTP response chứa thông tin người nhận, cần làm sạch hoặc giới hạn quyền xem.

### Tại sao cần attempt history?

Nếu chỉ lưu status = RETRY_PENDING và lastError = timeout, khó biết record đã retry 2 lần hay 200 lần; những lần thử đã dồn vào thời điểm nào; hoặc có hai replica cùng gửi hay không. Attempt history và correlation ID giúp xác định bão đến từ đâu.

### Đừng ghi mỗi lần polling như một retry

Nếu scheduler kiểm tra 1.000 record chưa đến hạn nhưng không gọi SMTP, không được tăng retry_attempts_total. Nên phân biệt:

- Poll/claim/defer.
- Permit granted/denied.
- SMTP submit started.
- SMTP submit completed/failed.

Phân biệt này quan trọng để tính đúng số lần thực sự tạo tải cho relay.

## 27. Một kịch bản kiểm thử end-to-end có thể tái lập

Để chứng minh hệ thống không tạo bão gửi, có thể xây một bài test mô phỏng:

### Dữ liệu đầu vào

~~~text
Notifications: 10,000
Notification categories:
  - 1,000 transactional
  - 9,000 optional

Workers: 4 replicas
Shared token bucket:
  - 20 permits/second
  - burst capacity 40
SMTP concurrency: 6
Retry:
  - max attempts 4
  - bounded exponential backoff + jitter

SMTP fake:
  - phút đầu: temporary failure
  - phút thứ hai: 50% temporary failure
  - sau đó: accept
~~~

Các số trên chỉ dùng cho môi trường thử nghiệm, không phải cấu hình khuyến nghị cho production.

### Trình tự và điểm quan sát

**Giai đoạn 1 — enqueue**

- Tạo 10.000 notification với idempotency key riêng.
- Xác nhận không tạo bản ghi trùng.
- Đưa tất cả vào outbox với trạng thái PENDING.

**Giai đoạn 2 — provider outage**

- Bật fake SMTP temporary failure.
- Cho worker chạy trong thời gian giả lập một phút.
- Đếm tổng attempts, max in-flight, số lần defer và nextAttemptAt.
- Xác nhận retry không tăng vượt maxAttempts.

**Giai đoạn 3 — partial recovery**

- Fake SMTP chấp nhận một nửa requests.
- Chạy worker thêm một khoảng thời gian.
- Xác nhận record thành công chuyển SUBMITTED.
- Record lỗi tạm thời tiếp tục được giãn retry.

**Giai đoạn 4 — full recovery**

- Fake SMTP chấp nhận mọi request.
- Chạy dispatcher với backlog còn lại.
- Xác nhận limiter vẫn giữ throughput và in-flight.
- Email mới quan trọng vẫn được xử lý theo reserved capacity.

**Giai đoạn 5 — restart và replay**

- Dừng một worker rồi khởi động lại.
- Phát lại một số record DEAD_LETTER đủ điều kiện.
- Xác nhận retry/replay dùng chung limiter và lịch sử được giữ.
- Xác nhận record SUBMITTED không bị replay theo cách gửi trùng.

### Tiêu chí đạt

| Tiêu chí | Điều cần đo |
| --- | --- |
| Không bão lưu lượng | Tổng permit/submit phù hợp token bucket theo thời gian |
| Không bão kết nối | Max observed in-flight không vượt 6 |
| Không retry vô hạn | Mỗi record không vượt 4 SMTP attempts theo policy |
| Không mất notification bắt buộc | Record được lưu và có trạng thái cuối/trạng thái xử lý còn theo dõi được |
| Không gửi tùy chọn hết hạn | Các record hết hạn chuyển EXPIRED/SUPPRESSED |
| Không ghi sai trạng thái | SUBMITTED chỉ khi transport có kết quả chấp nhận đáng tin cậy |
| Không duplicate do claim đồng thời | Chỉ một lease owner hợp lệ xử lý cùng record |
| Không bão sau hồi phục | Backlog giảm trong giới hạn, không burst vượt budget |
| Có khả năng điều tra | Attempt history và metric phản ánh lỗi và các lần thử |

Một integration test không cần thật sự chờ nhiều phút: có thể dùng clock giả cho lịch outbox, điều khiển nhịp gửi trong test harness và fake transport. Với benchmark mạng thật, đo theo wall clock trong một môi trường cô lập phù hợp.

## 28. Kiểm thử đặc biệt: queue và rate limiter không cùng trạng thái

Một vấn đề thực tế là các thành phần có thông tin không đồng bộ. Ví dụ outbox đã claim 100 message trong khi rate limiter chỉ còn 5 token. Nếu worker đưa tất cả 100 record vào memory executor để chờ token, lease có thể hết hạn trước khi chúng được gửi.

### Test thiếu permit ngay sau khi claim

1. Claim một batch nhỏ.
2. Làm shared limiter trả về không có token.
3. Xác nhận worker không gọi SMTP.
4. Xác nhận record được trả về trạng thái chờ hoặc có nextAttemptAt hợp lý.
5. Xác nhận không tăng attempts.
6. Xác nhận lease được giải phóng/điều chỉnh đúng và record không mắc kẹt PROCESSING.

### Test thua race giữa kiểm tra và lấy token

Hai worker có thể cùng quan sát limiter “còn 1 token”, nhưng chỉ một worker được phép thực sự tiêu thụ token. Kiểm tra số dư trước rồi cập nhật sau bằng thao tác không nguyên tử có thể khiến cả hai gửi.

Hãy test hai worker cùng lấy permit cuối cùng:

- Chỉ một request nhận được permit.
- Request còn lại nhận kết quả defer.
- Không có counter âm hoặc quota vượt ngưỡng.
- Nếu dùng Redis/Lua, xác minh với Redis thật hoặc môi trường tích hợp tương ứng.

### Test queue bị đầy

Với executor hữu hạn:

- Khi quá số thread và queue capacity, task mới bị từ chối có chủ đích.
- Email bắt buộc vẫn tồn tại trong outbox, không bị drop.
- Người vận hành thấy metric rejected/deferred.
- Worker không catch RejectedExecutionException rồi đánh dấu SUBMITTED.

Nếu dùng CallerRunsPolicy, test rằng HTTP request không bất ngờ bị giữ chờ SMTP trong luồng nghiệp vụ cần phản hồi nhanh. Chính sách rejection phải phù hợp với kiến trúc, không chỉ làm biến mất exception.

## 29. Các lỗi thiết kế dễ dẫn tới bão gửi

### 29.1. Retry vô hạn trong vòng while

Một đoạn while(true) có thể tạo hàng nghìn lần gọi khi SMTP từ chối ngay. Phải có giới hạn attempts và backoff.

### 29.2. Delay cố định cho mọi message

Các message cùng lỗi sẽ cùng thức dậy, tạo thundering herd. Dùng jitter và giới hạn toàn cục.

### 29.3. Chỉ test một notification

Một notification retry đúng không chứng minh 10.000 notification cùng retry không tạo spike. Cần test tải đồng thời.

### 29.4. Chỉ đếm số record, không đếm số lời gọi SMTP thật

Retry lồng trong adapter có thể làm nhiều lần gọi transport hơn số attempts của outbox. Cần đếm physical submits.

### 29.5. Bỏ rate limiter khi retry/replay

Email mới có thể đúng quota, nhưng retry và replay tạo bão. Mọi nguồn gửi phải qua cùng dispatch gate.

### 29.6. Một limiter riêng trên mỗi replica

Tốc độ tổng nhân lên theo số pod. Dùng budget chung hoặc dispatcher tập trung.

### 29.7. Giới hạn thread nhưng không giới hạn tốc độ

Vài thread gửi nhanh vẫn có thể vượt quota theo giây/phút. Cần cả rate và concurrency.

### 29.8. Gọi Thread.sleep trong transaction

Giữ connection/lock trong thời gian chờ, làm database khó phục vụ. Lưu nextAttemptAt và commit; worker quay lại khi đến hạn.

### 29.9. Đặt maxAttempts nhưng không kiểm tra expiry

OTP đã hết hiệu lực hoặc email chiến dịch đã hết hạn vẫn có thể gửi muộn. Kiểm tra thời hạn trước retry.

### 29.10. Coi thiếu rate token là lỗi SMTP

Nếu chưa gọi transport, không nên tăng SMTP attempt count hoặc đưa record vào failure retry chain. Đây là deferred dispatch.

### 29.11. Mở circuit breaker toàn provider vì lỗi một recipient

Lỗi recipient riêng lẻ không phản ánh provider outage. Phân loại tín hiệu chính xác.

### 29.12. Đóng circuit breaker là xả hết backlog

Khi relay phục hồi, backlog lớn vẫn phải qua limiter. Tăng throughput từ từ theo policy.

### 29.13. Replay mọi dead-letter cùng một lúc

Có thể gây burst, gửi nội dung đã lỗi thời hoặc vượt consent. Replay cần filter, dry-run, rate limit, audit và batch nhỏ.

### 29.14. Coi SMTP outcome unknown là chắc chắn thất bại

Retry ngay có thể gửi trùng nếu relay đã nhận. Cần trạng thái riêng và đối soát theo khả năng provider.

### 29.15. Dùng Message-ID để tuyên bố exactly-once

Message-ID có ích để trace, nhưng không ép mọi relay/mailbox loại bỏ bản sao. Không coi nó là idempotency guarantee.

### 29.16. Chỉ test với SMTP luôn thành công

Không thể phát hiện lỗi retry, jitter, timeout, breaker hoặc redelivery nếu fake server chỉ ACCEPT. Phải có failure injection.

### 29.17. Dựa vào Thread.sleep trong test

Test dễ flaky khi CI chậm hoặc scheduler có jitter. Inject Clock và random source để kiểm tra logic tất định.

### 29.18. Không kiểm tra lỗi khi trạng thái cập nhật thất bại

SMTP có thể đã nhận message nhưng database không ghi SUBMITTED, khiến record được xử lý lại. Cần test lỗi database sau submit và có chính sách unknown/duplicate.

### 29.19. Không ưu tiên thông báo thiết yếu

Retry marketing chiếm hết quota khiến OTP hoặc email giao dịch đến muộn. Dùng reserved budget hoặc fair scheduling.

### 29.20. Không giám sát tuổi backlog

Số lượng queue có thể nhỏ nhưng một OTP đã chờ quá thời hạn. Theo dõi oldest age và dispatch latency theo category.

## 30. Một quy trình kiểm thử và đưa vào vận hành

Trước khi đưa cơ chế retry mới vào production, có thể đi theo thứ tự sau:

1. **Xác định quota thật:** message/s, recipient/min, connection, daily và kích thước email; phân biệt provider/account.
2. **Liệt kê mọi nguồn gửi:** first send, retries, replay, resend, campaign và manual dispatch.
3. **Chọn mô hình trạng thái:** PENDING, PROCESSING, RETRY_PENDING, SUBMITTED, UNKNOWN, FAILED, EXPIRED và SUPPRESSED phù hợp.
4. **Định nghĩa retry policy:** loại lỗi, maxAttempts, backoff, jitter, maxAge, circuit breaker và cách xử lý unknown outcome.
5. **Định nghĩa shared dispatch gate:** global budget, concurrency, per-tenant/domain/category và retry budget.
6. **Định nghĩa transaction boundaries:** claim, SMTP và state update không nằm trong một transaction dài.
7. **Thêm idempotency key và lease:** tránh enqueue và claim trùng; lưu attempt history.
8. **Viết unit test clock/random:** không dùng sleep thật cho logic thời gian.
9. **Viết integration test database/limiter:** kiểm tra atomic claim và shared permit giữa replica.
10. **Viết fault-injection test:** timeout, 421, 5xx, mất kết nối sau DATA, limiter outage và database outage.
11. **Mô phỏng outage rồi recovery:** backlog lớn phải được drain trong rate/concurrency limit.
12. **Kiểm tra policy người nhận:** consent, expiry, suppression, OTP token và template version.
13. **Kiểm tra metrics/alert:** thấy được throughput, retry ratio, oldest age, queue depth và rate-limit state.
14. **Triển khai có kiểm soát:** tăng dần worker/concurrency và quan sát phản hồi provider, không mở quota hết mức ngay.
15. **Chuẩn bị runbook:** giảm rate, dừng marketing, mở breaker, điều tra DLQ và replay từng batch.

### Bảng kiểm nghiệm thu

| Yêu cầu | Cách chứng minh |
| --- | --- |
| Không vượt giới hạn tốc độ | Test token bucket/sliding window trên toàn cụm |
| Không vượt số connection | Quan sát max in-flight bằng latch/test transport |
| Không đồng bộ hóa retry | Jitter test và histogram nextAttemptAt |
| Không retry vô hạn | Test maxAttempts và terminal status |
| Không mất email bắt buộc | Outbox persistence/restart test |
| Không gửi trùng do concurrent claim | Database integration test với hai worker |
| Không tự retry unknown outcome | SMTP response-loss test |
| Không bão sau provider recovery | Fault injection outage → ACCEPT |
| Không gửi email hết hạn/unsubscribed | Policy test trước dispatch |
| Không bypass quota khi manual replay | Replay integration test |
| Có thể quan sát sự cố | Attempt history, metric và log correlation |

Những tiêu chí này là mục tiêu kiểm thử thiết kế, không phải lời khẳng định một hệ thống đã đáp ứng cho tới khi có kết quả kiểm nghiệm thực tế.

## 31. Câu hỏi tự kiểm tra

**1. Retry storm khác một hàng đợi email lớn như thế nào?**

Hàng đợi lớn là lượng công việc còn chờ. Retry storm là việc các lần thử lại khuếch đại lưu lượng, đồng bộ thời gian hoặc vượt khả năng SMTP, có thể làm sự cố kéo dài. Một queue lớn có thể được drain an toàn nếu có limiter; một queue nhỏ vẫn có thể tạo storm nếu mỗi message retry vô hạn.

**2. Vì sao exponential backoff không đủ?**

Nếu nhiều job cùng thất bại và dùng cùng dãy delay, chúng vẫn retry cùng thời điểm. Cần jitter và một rate limiter dùng chung.

**3. Full jitter có thể trả delay bằng 0 không?**

Có. Vì vậy một số hệ thống đặt delay tối thiểu hoặc chọn biến thể jitter khác để tránh retry tức thời, nhất là khi lỗi xảy ra rất nhanh.

**4. MaxAttempts nên đếm số lần scheduler poll hay số lần submit SMTP?**

Thông thường nên đếm attempts thực sự bắt đầu gọi transport. Việc thiếu token hoặc thiếu slot trước khi gọi SMTP chỉ là defer, không phải SMTP attempt.

**5. Có nên retry lỗi SMTP 5xx liên tục không?**

Không. Mã 5xx thường biểu thị lỗi vĩnh viễn cho yêu cầu hiện tại; cần điều tra nguyên nhân. Không gom tất cả exception thành retryable.

**6. Vì sao cần đo số lần gọi transport thật?**

Vì retry có thể tồn tại trong nhiều lớp. Outbox báo ba attempts nhưng Spring Retry hoặc broker redelivery có thể tạo nhiều hơn ba lần gọi SMTP.

**7. Nhiều pod, mỗi pod có token bucket riêng thì có bảo đảm quota không?**

Không. Tổng tốc độ có thể tăng theo số pod. Cần shared limiter hoặc dispatcher tập trung.

**8. Hết permit khi record đã được claim thì làm gì?**

Release hoặc defer claim, giữ record trong outbox, đặt thời điểm thử lại hợp lý và không tăng SMTP attempts khi chưa gửi.

**9. Tại sao không dùng Thread.sleep để kiểm tra backoff?**

Vì test chậm, phụ thuộc scheduler và dễ flaky. Inject Clock cùng random source để điều khiển thời gian và kết quả.

**10. Cần test điều gì khi SMTP phục hồi?**

Backlog lớn không được gửi đồng loạt vượt quota, max in-flight phải được giữ, và email quan trọng mới không bị retry cũ chiếm toàn bộ năng lực.

**11. Khi SMTP relay đã nhận DATA nhưng phản hồi bị mất, có thể retry ngay không?**

Không nên retry mù. Kết quả submit có thể không xác định; cần policy xử lý SUBMISSION_UNKNOWN, đối soát hoặc chấp nhận duplicate risk theo nghiệp vụ.

**12. Unique idempotency key có bảo đảm không gửi trùng qua SMTP không?**

Không. Nó giúp ngăn tạo hai outbox record cho cùng sự kiện, nhưng không loại bỏ mọi duplicate ở bước submit network không có transaction chung với database.

**13. Tại sao phải kiểm tra consent lại khi retry marketing?**

Người dùng có thể unsubscribe sau khi enqueue. Khi đến thời điểm retry, hệ thống phải tôn trọng preference/suppression hiện tại.

**14. Circuit breaker mở lại có cho gửi hết backlog ngay được không?**

Không. Sau khi phục hồi, limiter vẫn phải điều tiết; nếu không có thể tạo outage lần thứ hai.

**15. Những metric nào giúp phát hiện storm?**

Tổng SMTP attempts/giây, retry attempts/giây, tỷ lệ lỗi tạm thời, rate-limited count, max in-flight, tuổi backlog và trạng thái circuit breaker là các tín hiệu quan trọng.

**16. Có nên chạy thí nghiệm bão gửi trên SMTP production không?**

Không. Dùng fake SMTP, capture server hoặc môi trường tải thử được phép, để tránh ảnh hưởng người nhận và uy tín gửi.

## Kết luận

**Kiểm tra retry không tạo bão gửi là kiểm tra toàn bộ cơ chế điều phối khi lỗi và khi phục hồi, không phải chỉ kiểm tra một lần thử lại thành công.** Với Spring Framework Mail, hãy phân loại lỗi trước retry, dùng exponential backoff có jitter, giới hạn attempts và tuổi thông điệp, lưu nextAttemptAt trong outbox bền vững, claim bằng lease và giữ idempotency key rõ ràng. Mọi lần gửi mới, retry, resend và replay phải đi qua cùng rate limiter và concurrency gate trên toàn cụm. Test cần có clock/random giả, fault injection, nhiều worker đồng thời, SMTP response-loss, restart và outage-recovery với backlog lớn; đồng thời quan sát số lời gọi transport thực, max in-flight, retry ratio và tuổi hàng đợi. **Một hệ thống đạt yêu cầu phải phục hồi dần theo năng lực SMTP, không làm mất email quan trọng, không gửi email hết hạn hoặc bị suppress và không để chính cơ chế retry tạo thêm một sự cố mới.**
