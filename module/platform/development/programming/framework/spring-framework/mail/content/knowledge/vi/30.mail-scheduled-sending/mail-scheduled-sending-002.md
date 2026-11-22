# Lưu thời điểm gửi cùng trạng thái message

## 1. Vì sao phải lưu lịch gửi và trạng thái cùng nhau?

Trong ứng dụng **Spring Framework Mail**, một yêu cầu gửi email không nhất thiết được gửi ngay. Người dùng có thể đặt lịch nhận báo cáo sáng thứ Hai; hệ thống có thể cần chờ một khoảng sau khi tạo đơn hàng; chiến dịch chỉ được phép gửi trong giờ hành chính; hoặc SMTP provider đang giới hạn tốc độ và job phải đợi lượt.

Một lệnh `JavaMailSender.send(...)` chỉ thực hiện **một lần nộp thư** tới SMTP server tại thời điểm được gọi. Nó không tự giải quyết việc hẹn giờ, ghi nhớ trạng thái sau restart, điều phối nhiều instance, hủy lịch hoặc retry. Nếu chỉ giữ lịch trong RAM:

~~~java
// Ví dụ không đủ bền vững cho email nghiệp vụ.
scheduler.schedule(() -> mailSender.send(message), sendTime);
~~~

thì khi ứng dụng restart, lịch đã đăng ký có thể biến mất. Khi SMTP lỗi, không có bản ghi bền vững để biết email còn chờ hay đã gửi thử. Nếu người dùng bấm hủy đúng lúc worker gửi, một flag trong bộ nhớ cũng không đủ đồng bộ giữa các replica.

Giải pháp thường dùng là lưu **email job** trong database, với ít nhất:

- **Thời điểm được phép gửi** (`scheduled_at`).
- **Trạng thái công việc** (`status`).
- **Thời điểm thử lại** (`next_attempt_at`) nếu có retry.
- **Số lần đã thực sự gửi thử** (`attempt_count`).
- **Thời điểm provider chấp nhận** (`submitted_at`) nếu có.
- **Thông tin ownership/lease** khi nhiều worker xử lý.

Sau đó một worker định kỳ tìm những job **đã tới giờ và còn đủ điều kiện** để gửi.

~~~text
Application / User
        |
        v
Create mail job:
  scheduledAt + status=PENDING
        |
        v
Durable database / outbox
        |
        v
Due-job dispatcher
        |
        v
Claim -> Compose -> JavaMailSender
        |
        +-- Accepted  -> SUBMITTED
        +-- Temporary -> RETRY, nextAttemptAt
        +-- Permanent -> FAILED
        +-- Unclear   -> UNKNOWN
~~~

**Nguyên tắc cốt lõi:** thời điểm và trạng thái phải mô tả **cùng một thực thể công việc**, được thay đổi bằng transaction có kiểm soát, thay vì lưu lịch trong một nơi và status trong một biến riêng không có tính nhất quán.

## 2. Phân biệt mail job, MIME message và email đã được giao

Trong bài, từ *message* xuất hiện ở ba lớp:

| Lớp | Khái niệm | Định danh thường dùng | Trạng thái |
|---|---|---|---|
| Nghiệp vụ | Yêu cầu gửi email đã lên lịch | `mailJobId` | PENDING, RETRY, SUBMITTED... |
| SMTP/MIME | Đối tượng `MimeMessage` gửi tới server | Header `Message-ID`, attempt ID | Đang tạo/submit |
| Delivery | Thư được provider chuyển đến mailbox | Provider message ID, delivery event | Delivered, bounced, deferred... |

Một mail job có thể tạo nhiều **submission attempts** nếu gặp lỗi tạm thời. Một submission attempt có thể mang cùng hoặc khác `Message-ID` tùy cách tạo message; `Message-ID` không tự bảo đảm idempotency. Và một lần `send(...)` thành công chưa chứng minh thư đã vào inbox.

Vì thế:

~~~text
PENDING       -> chưa tới lượt hoặc chưa được claim
PROCESSING    -> worker đã claim và đang xử lý
SUBMITTED     -> SMTP/API báo đã chấp nhận submission
DELIVERED     -> có tín hiệu delivery từ provider/receiver nếu tích hợp
BOUNCED       -> provider báo không giao thành công
~~~

Không gọi tất cả các trường hợp là `SENT` mà không định nghĩa cụ thể. Nếu ứng dụng dùng trạng thái `SENT`, tài liệu và code cần nói rõ đó là **đã nộp thành công cho provider** hay **đã giao tới mailbox**.

## 3. Những mốc thời gian cần lưu

Một record có thể có các timestamp sau:

| Trường | Ý nghĩa | Khi nào đặt giá trị? |
|---|---|---|
| `created_at` | Thời điểm tạo job | Khi transaction tạo job |
| `scheduled_at` | Thời điểm gửi mong muốn ban đầu/mới nhất | Khi người dùng hoặc nghiệp vụ lên lịch |
| `next_attempt_at` | Thời điểm sớm nhất worker được thử gửi | Khi tạo job và khi defer/retry |
| `claimed_at` | Worker bắt đầu sở hữu job | Khi claim thành công |
| `lease_until` | Giới hạn thời gian giữ quyền xử lý | Khi claim/renew lease |
| `attempt_started_at` | Lần submit thực tế bắt đầu | Khi attempt được ghi |
| `submitted_at` | Provider đã chấp nhận submission | Khi có xác nhận success từ adapter |
| `last_failed_at` | Lần lỗi được ghi nhận gần nhất | Khi attempt thất bại |
| `delivered_at` | Provider báo đã giao thư | Khi nhận delivery event đáng tin |
| `cancelled_at` | Job được hủy khi còn hủy được | Khi hủy hợp lệ |
| `updated_at` | Lần cập nhật state gần nhất | Trên mỗi state transition |
| `expires_at` | Hạn cuối còn có ý nghĩa để gửi | Khi tạo job nếu nội dung có thời hạn |

**Không nhất thiết bảng nào cũng cần tất cả trường.** Bắt đầu bằng `scheduled_at`, `next_attempt_at`, `status` và một vài trường audit; chỉ bổ sung mốc tương ứng khi nghiệp vụ cần. Nhưng tránh gộp mọi thời điểm vào một trường mơ hồ tên `sentTime`.

### scheduled_at và next_attempt_at không giống nhau

Giả sử một email được lên lịch:

~~~text
scheduled_at   = 2026-11-15T09:00:00Z
next_attempt_at= 2026-11-15T09:00:00Z
status         = PENDING
~~~

Đến 09:00, SMTP provider bị lỗi tạm thời. Worker lên lịch retry:

~~~text
scheduled_at   = 2026-11-15T09:00:00Z  (giữ lịch nghiệp vụ)
next_attempt_at= 2026-11-15T09:05:00Z  (thời gian retry)
status         = RETRY
attempt_count  = 1
~~~

Nếu ghi đè `scheduled_at` thành 09:05 mỗi khi retry, ứng dụng mất lịch gốc và khó tính **độ trễ so với cam kết người dùng**. Nên phân biệt hai trường.

### submitted_at khác delivered_at

`JavaMailSender.send(...)` không cung cấp một cam kết đồng bộ rằng người nhận đã nhận thư. Vì vậy:

~~~text
submitted_at = sau khi SMTP submission accepted
delivered_at = null nếu chưa có xác nhận giao thư
~~~

Nếu chưa tích hợp webhook/DSN/tracking, có thể **không có `delivered_at`**. Đừng tự gán `delivered_at = submitted_at` chỉ để làm dashboard đẹp.

## 4. Mô hình trạng thái cho email hẹn giờ

Một mô hình đủ chi tiết cho nhiều hệ thống:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CLAIMED: Đến giờ, claim thành công
    PENDING --> CANCELLED: Hủy trước khi claim
    PENDING --> EXPIRED: Vượt deadline
    PENDING --> PENDING: Đổi lịch
    CLAIMED --> PROCESSING: Bắt đầu attempt
    CLAIMED --> PENDING: Giải phóng claim an toàn
    CLAIMED --> CANCELLED: Hủy trước điểm submit, có kiểm soát
    PROCESSING --> SUBMITTED: Provider accepted
    PROCESSING --> RETRY: Lỗi temporary đã phân loại
    PROCESSING --> FAILED: Lỗi permanent
    PROCESSING --> UNKNOWN: Outcome không chắc chắn
    RETRY --> CLAIMED: Tới nextAttemptAt
    RETRY --> CANCELLED: Hủy trước khi gửi lại
    RETRY --> EXPIRED: Vượt deadline
    SUBMITTED --> DELIVERED: Provider delivery event
    SUBMITTED --> BOUNCED: Provider bounce event
    UNKNOWN --> RETRY: Đối soát cho phép thử lại
    UNKNOWN --> SUBMITTED: Đối soát thấy accepted
~~~

Tên trạng thái là **enum ứng dụng tự định nghĩa**, không phải enum có sẵn của Spring Mail. Một hệ thống nhỏ có thể không dùng `CLAIMED` riêng và chỉ lưu `PROCESSING` với lease. Quan trọng là chỉ cho phép **transition hợp lệ** và ghi mốc thời gian đồng bộ.

| Status | Có được worker claim để gửi? | Ghi chú |
|---|---|---|
| PENDING | Có, khi đến giờ | Chưa gửi thử |
| RETRY | Có, khi `next_attempt_at <= now` | Đã có lỗi có khả năng retry |
| CLAIMED/PROCESSING | Không bởi worker khác nếu lease còn hiệu lực | Cần ownership/fencing |
| SUBMITTED | Không | Provider đã accepted; delivery là bước khác |
| DELIVERED | Không | Trạng thái hậu giao thư nếu có evidence |
| BOUNCED | Không tự gửi lại | Cần chính sách bounce/complaint |
| FAILED | Không | Lỗi permanent hoặc vượt max attempts |
| CANCELLED | Không | Hủy trước điểm không thể thu hồi |
| EXPIRED | Không | Nội dung quá hạn nghiệp vụ |
| UNKNOWN | Không retry tự động vô điều kiện | Phải đối soát hoặc áp policy riêng |

Một status như `WAITING_QUOTA` có thể được dùng nếu muốn phân biệt job bị rate limiter trì hoãn; cũng có thể giữ `PENDING` kèm `next_attempt_at` và `defer_reason`. Không nên tạo quá nhiều trạng thái mà không có ngữ nghĩa và hành động vận hành rõ ràng.

## 5. Chọn múi giờ và kiểu dữ liệu thời gian

**Nên lưu thời điểm thực tế ở UTC**, ví dụ Java `Instant` và PostgreSQL `TIMESTAMPTZ`, để so sánh và claim nhất quán.

~~~java
import java.time.Instant;

Instant scheduledAt = Instant.parse(
        "2026-11-15T09:00:00Z");
~~~

Nếu người dùng chọn **09:00 theo giờ địa phương**, ứng dụng phải biết timezone, chẳng hạn `Asia/Ho_Chi_Minh` hoặc `Europe/Berlin`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.Instant;

LocalDateTime localTime =
        LocalDateTime.of(2026, 11, 16, 9, 0);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime zoned = localTime.atZone(zone);
Instant scheduledAt = zoned.toInstant();
~~~

Với một **lần gửi cụ thể**, lưu `scheduled_at` dưới dạng instant là đủ cho việc dispatch. Với lịch **lặp lại** như “09:00 mỗi thứ Hai theo giờ Paris”, còn phải lưu `ZoneId`, quy tắc recurrence và policy xử lý daylight saving time (DST), không thể chỉ cộng 7 × 24 giờ mãi.

### DST: giờ không tồn tại và giờ lặp lại

Ở một số múi giờ, khi đổi DST:

- Có những local time **không tồn tại** (đồng hồ nhảy qua một giờ).
- Có những local time **xuất hiện hai lần** (đồng hồ quay lại một giờ).

`LocalDateTime.atZone(...)` có quy tắc mặc định để xử lý các tình huống đó, nhưng quy tắc mặc định chưa chắc phù hợp yêu cầu sản phẩm. Hãy chọn rõ policy:

1. Giờ không tồn tại: dời đến thời điểm hợp lệ tiếp theo hay từ chối yêu cầu?
2. Giờ lặp lại: dùng offset sớm hay muộn, hay hỏi người dùng?
3. Hiển thị lịch đã chọn theo timezone nào?
4. Khi người dùng đổi timezone, có giữ instant cũ hay giữ giờ địa phương?

Không sử dụng `LocalDateTime.now()` rồi ghi thẳng vào database như thể đó là UTC. Không lấy múi giờ mặc định của container làm timezone của người dùng.

## 6. “Gửi đúng giờ” nghĩa là gì?

Một scheduler không bảo đảm SMTP server sẽ nhận message ở chính xác mili-giây `scheduled_at`. Thời gian thực tế còn phụ thuộc:

~~~text
Scheduled instant
       |
       +-- Đợi scheduler tick
       +-- DB claim/lease
       +-- Quota/rate limiter
       +-- Worker queue
       +-- MIME rendering / attachments
       +-- DNS/TLS/SMTP connection
       |
       v
Provider accepts message
~~~

Có thể đo:

\[
\text{dispatchLag} =
  \text{attemptStartedAt} - \text{scheduledAt}
\]

\[
\text{submissionLag} =
  \text{submittedAt} - \text{scheduledAt}
\]

Hai phép đo có thể âm hoặc dương nếu một job được gửi sớm vì bug hoặc clock skew; **job không nên được submit trước `scheduled_at`** trừ khi chính sách cho phép. Ngoài ra, `submittedAt` có thể null khi job lỗi hoặc chưa được thử.

Nên cam kết theo **SLA trễ tối đa có điều kiện**, ví dụ “bắt đầu xử lý trong vòng một phút sau lịch nếu provider còn quota”, thay vì hứa một email chắc chắn xuất hiện trong inbox đúng 09:00.

## 7. Thiết kế bảng lưu lịch gửi và trạng thái

Một bảng PostgreSQL minh họa:

~~~sql
CREATE TABLE scheduled_mail (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    notification_type VARCHAR(80) NOT NULL,
    sender_profile_id VARCHAR(80) NOT NULL,

    recipient_ref VARCHAR(160) NOT NULL,
    payload_ref VARCHAR(255) NOT NULL,
    business_idempotency_key VARCHAR(180) NOT NULL,

    status VARCHAR(24) NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,

    attempt_count INT NOT NULL DEFAULT 0,
    claimed_at TIMESTAMPTZ,
    lease_until TIMESTAMPTZ,
    claim_token UUID,

    submitted_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    last_failed_at TIMESTAMPTZ,
    last_error_code VARCHAR(80),

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT chk_mail_attempts
        CHECK (attempt_count >= 0),
    CONSTRAINT chk_mail_expiry
        CHECK (expires_at IS NULL
               OR expires_at > created_at),
    CONSTRAINT chk_mail_status
        CHECK (status IN (
            'PENDING', 'RETRY', 'CLAIMED',
            'PROCESSING', 'SUBMITTED',
            'DELIVERED', 'BOUNCED',
            'FAILED', 'CANCELLED',
            'EXPIRED', 'UNKNOWN'
        )),
    CONSTRAINT uq_mail_business_intent
        UNIQUE (tenant_id, business_idempotency_key)
);
~~~

Các trường `recipient_ref` và `payload_ref` có thể trỏ tới dữ liệu được bảo vệ trong database hoặc object storage. Đây là **schema minh họa**, cần tùy biến theo yêu cầu thực tế. Tránh đặt mật khẩu SMTP, token, raw MIME hoặc HTML chứa dữ liệu cá nhân vào trường log/status không được kiểm soát.

### Vì sao cần version?

`version` giúp triển khai **optimistic concurrency control** cho hủy/đổi lịch, hoặc làm fencing của state updates. Một worker không nên ghi đè job vừa bị người dùng đổi lịch nếu chính sách chưa cho phép. Trường `claim_token` dùng để nhận diện **lượt claim hiện tại** khi cập nhật trạng thái, vì hai worker có thể xử lý cùng một job vào hai thời điểm khác nhau.

### Vì sao cần business_idempotency_key?

Một use case có thể được gọi lặp:

~~~text
HTTP request A tạo mail xác nhận order-100
Client timeout, không biết request thành công
HTTP request B lặp lại cùng ý định
~~~

Nếu chỉ cấp UUID mới cho mỗi lần gọi, có thể tạo hai job giống nhau. Một khóa nghiệp vụ như `ORDER_RECEIPT:order-100:version-1` kết hợp `tenant_id` giúp tránh **tạo trùng ý định gửi**, khác với dedup ở SMTP transport.

Không dùng nội dung tùy ý của client như raw email làm idempotency key để ghi vào log. Key có thể là định danh opaque hoặc dẫn xuất từ business event có kiểm soát. Chỉ unique trong phạm vi có ý nghĩa: một order có thể có nhiều lần gửi lại **được ủy quyền** và cần key mới.

## 8. Index để tìm những email đã đến hạn

Một scheduler thường truy vấn:

~~~sql
SELECT id
FROM scheduled_mail
WHERE status IN ('PENDING', 'RETRY')
  AND next_attempt_at <= CURRENT_TIMESTAMP
  AND scheduled_at <= CURRENT_TIMESTAMP
ORDER BY next_attempt_at, id
LIMIT 100;
~~~

Không nên quét toàn bộ bảng vài giây một lần khi có hàng triệu job.

~~~sql
CREATE INDEX idx_scheduled_mail_ready
    ON scheduled_mail (next_attempt_at, id)
    WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX idx_scheduled_mail_claim_lease
    ON scheduled_mail (lease_until)
    WHERE status IN ('CLAIMED', 'PROCESSING');

CREATE INDEX idx_scheduled_mail_created
    ON scheduled_mail (created_at, id);
~~~

Các index là gợi ý. Query thực tế còn có thể lọc theo `sender_profile_id`, tenant, priority và provider route; cần chọn index theo workload và `EXPLAIN ANALYZE` ở môi trường phù hợp.

**Lưu ý về partial index:** điều kiện predicate chỉ dựa vào status cố định, không đặt `CURRENT_TIMESTAMP` trong predicate index (giá trị thay đổi theo thời gian không phù hợp với yêu cầu immutability). Điều kiện thời gian được áp trong query và index theo `next_attempt_at` hỗ trợ quét có thứ tự.

### Cẩn trọng với partitioning

Nếu bảng lưu lịch sử nhiều năm và vài trăm triệu hàng, có thể cân nhắc partition/archive, nhưng đừng partition theo `scheduled_at` một cách máy móc khi job retry sau nhiều tháng: active job vẫn nằm ở partition cũ. Chọn mô hình theo truy vấn active và retention, có thể tách bảng trạng thái đang chờ khỏi lịch sử attempts.

## 9. Tạo job và dữ liệu nghiệp vụ trong cùng transaction

Giả sử khi tạo đơn hàng, hệ thống phải hẹn email xác nhận sau một giờ. Một anti-pattern:

~~~java
orderRepository.save(order);
mailScheduler.scheduleEmail(order); // Ghi nơi khác sau đó.
~~~

Nếu process crash giữa hai thao tác, đơn hàng tồn tại nhưng email intent không được tạo. Ngược lại, nếu email được tạo trước khi đơn hàng commit, có thể gửi thư cho một giao dịch đã rollback.

Khi cả hai cùng một database, **transactional outbox** là lựa chọn phổ biến:

~~~text
BEGIN TRANSACTION
  INSERT / UPDATE business order
  INSERT scheduled_mail(
    scheduled_at,
    next_attempt_at,
    status='PENDING',
    business_idempotency_key,
    ...
  )
COMMIT

Sau commit:
  dispatcher đọc job đến hạn
  SMTP submit ở ngoài transaction
~~~

Spring example:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final ScheduledMailRepository scheduledMail;
    private final Clock clock;

    public OrderApplicationService(
            OrderRepository orders,
            ScheduledMailRepository scheduledMail,
            Clock clock) {
        this.orders = orders;
        this.scheduledMail = scheduledMail;
        this.clock = clock;
    }

    @Transactional
    public void confirmOrder(ConfirmOrderCommand command) {
        Order order = orders.confirm(command);

        Instant plannedAt = clock.instant()
                .plus(Duration.ofHours(1));

        scheduledMail.insertIfAbsent(
                new ScheduledMailIntent(
                        order.tenantId(),
                        "ORDER_RECEIPT",
                        "ORDERS",
                        order.customerRef(),
                        order.payloadRef(),
                        "ORDER_RECEIPT:" + order.id(),
                        plannedAt,
                        plannedAt,
                        "PENDING"));
    }
}
~~~

`OrderRepository`, `ConfirmOrderCommand`, `ScheduledMailRepository` và các record trong ví dụ là abstraction do ứng dụng xây dựng, không có sẵn trong Spring Mail. `insertIfAbsent` cần thực thi idempotently bằng unique constraint và xử lý conflict; không chỉ kiểm tra `exists` rồi insert riêng rẽ vì race.

**Không gọi `mailSender.send(...)` trong transaction tạo order.** SMTP là network side effect không rollback cùng database; transaction mở qua SMTP sẽ giữ resource lâu và có thể gửi email cho giao dịch cuối cùng rollback.

## 10. Tạo job bằng UPSERT để chống duplicate intent

Với PostgreSQL, có thể tránh việc tạo hai job cho cùng một business event bằng unique constraint và `ON CONFLICT`:

~~~sql
INSERT INTO scheduled_mail (
    id, tenant_id, notification_type,
    sender_profile_id, recipient_ref, payload_ref,
    business_idempotency_key,
    status, scheduled_at, next_attempt_at
) VALUES (
    :id, :tenant_id, :notification_type,
    :sender_profile_id, :recipient_ref, :payload_ref,
    :business_key,
    'PENDING', :scheduled_at, :scheduled_at
)
ON CONFLICT (tenant_id, business_idempotency_key)
DO NOTHING;
~~~

Sau conflict, code cần **xác định job đã tồn tại** và trả ID/trạng thái phù hợp với API. Không mặc định request lặp lại được quyền đổi lịch của job cũ; thao tác *create* và *reschedule* nên có contract khác nhau.

### Khi nào không nên DO UPDATE toàn bộ?

Một HTTP retry có thể mang payload cũ, trong khi người dùng đã hủy hoặc đổi lịch. Nếu UPSERT bằng `DO UPDATE SET status='PENDING'` vô điều kiện, request cũ có thể “hồi sinh” job đã CANCELLED hoặc SUBMITTED. Chỉ cập nhật bằng transition hợp lệ, kiểm tra version/status và quyền.

## 11. Phân biệt lịch người dùng với deadline và lịch thử lại

Ba điều kiện khác nhau:

~~~text
scheduledAt:     gửi không sớm hơn thời điểm này
nextAttemptAt:   retry/defer không sớm hơn thời điểm này
expiresAt:       sau mốc này không còn nên gửi
~~~

Khi chọn job đã tới giờ:

\[
\text{eligible}(j,t) =
  j.status \in \{PENDING,RETRY\}
  \land j.scheduledAt \le t
  \land j.nextAttemptAt \le t
  \land (j.expiresAt = null \lor t < j.expiresAt)
\]

Trong thực tế còn phải kiểm tra suppression/consent, user preference, quota, sender eligibility và chính sách nghiệp vụ **ngay trước khi gửi**.

Ví dụ OTP hết hiệu lực:

~~~text
scheduledAt   = 09:00:00
expiresAt     = 09:05:00
nextAttemptAt = 09:06:00 do provider outage
~~~

Khi 09:06, không được gửi OTP đã hết hạn chỉ vì worker cuối cùng cũng có permit. Đưa job sang `EXPIRED` và ghi lý do không nhạy cảm. Email marketing có thể có deadline hoàn toàn khác; không áp một expiry chung cho mọi loại thông báo.

## 12. Dispatcher tìm job đến hạn như thế nào?

Một dispatcher thường được đánh thức theo lịch, lấy **batch nhỏ** và chỉ submit các job có thể xử lý ngay:

~~~text
Scheduler tick
      |
      v
Query jobs WHERE status in PENDING/RETRY
    AND scheduledAt <= now
    AND nextAttemptAt <= now
      |
      v
Claim atomically
      |
      v
Load payload and check eligibility
      |
      v
Acquire provider rate/concurrency permit
      |
      v
Begin SMTP attempt
      |
      v
Save outcome
~~~

Không nên lấy 100.000 job đã đến hạn rồi `submit` hết vào một `ThreadPoolTaskExecutor` queue trong RAM. Khi chỉ gửi được vài thư/giây, các job đợi lâu trong executor có thể hết lease, mất trạng thái khi restart hoặc bị worker khác claim lại.

### Poll interval và batch size

Ví dụ scheduler chạy mỗi giây, mỗi lần claim tối đa 50 job. Con số này **không bảo đảm 50 thư/giây**; throughput còn phụ thuộc quota, concurrency, thời gian tạo MIME, độ trễ SMTP và số worker. Cần chọn batch size phù hợp năng lực, không chỉ tăng batch size để “gửi nhanh”.

### Cần đánh thức dispatcher ngay khi có job mới không?

Polling đơn giản thường đủ với SLA theo giây/phút. Với độ trễ thấp, có thể phát một tín hiệu qua broker hoặc database notification sau commit để đánh thức worker sớm. Tuy nhiên, **database vẫn là nguồn sự thật**: nếu tín hiệu bị mất, polling định kỳ phải bảo đảm job đến hạn không bị bỏ qua.

## 13. Claim atomically bằng PostgreSQL SKIP LOCKED

Nếu có nhiều Spring Boot replicas, câu lệnh:

~~~sql
SELECT id FROM scheduled_mail
WHERE status = 'PENDING'
  AND next_attempt_at <= CURRENT_TIMESTAMP;
~~~

**không đủ**. Hai worker có thể cùng đọc một job trước khi bất kỳ worker nào đánh dấu xử lý.

PostgreSQL hỗ trợ `FOR UPDATE SKIP LOCKED` để worker lấy các row chưa bị khóa bởi transaction khác. Một lệnh claim:

~~~sql
WITH eligible AS (
    SELECT id
    FROM scheduled_mail
    WHERE status IN ('PENDING', 'RETRY')
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND next_attempt_at <= CURRENT_TIMESTAMP
      AND (expires_at IS NULL
           OR expires_at > CURRENT_TIMESTAMP)
    ORDER BY next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE scheduled_mail AS job
SET status = 'CLAIMED',
    claimed_at = CURRENT_TIMESTAMP,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    claim_token = :claim_token,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
FROM eligible
WHERE job.id = eligible.id
RETURNING
    job.id,
    job.claim_token,
    job.version,
    job.scheduled_at,
    job.next_attempt_at;
~~~

Lệnh này được thực hiện trong **transaction ngắn**, sau đó commit. `SKIP LOCKED` bỏ qua các row đang bị transaction khác khóa; nó phù hợp cho queue consumers nhưng không bảo đảm FIFO tuyệt đối.

`:claim_token` là UUID ngẫu nhiên do worker tạo cho lượt claim. Có thể dùng một token chung cho batch nhưng tốt hơn lưu **attempt ownership** rõ ràng cho từng job; database transaction và update conditions vẫn phải bảo vệ từng row. Một worker cần ghi nhận ID/claim token của các job nó thật sự sở hữu.

### Không giữ database row lock trong lúc SMTP

Sai:

~~~text
BEGIN
  SELECT ... FOR UPDATE
  JavaMailSender.send(...)
  UPDATE status
COMMIT
~~~

SMTP có thể block nhiều giây. Giữ transaction và row lock suốt thời gian đó làm database connection pool bị giữ, chặn các thao tác hủy/đổi lịch và tăng contention.

Đúng hơn:

~~~text
TX1: Claim + set lease + COMMIT

SMTP submission (không giữ TX1)

TX2: Save outcome if claim token is still current
~~~

Giữa TX1 và TX2 có thể xảy ra crash. Lease, idempotency và xử lý `UNKNOWN` là các lớp bắt buộc để giải quyết trạng thái dở dang, chứ `SKIP LOCKED` không tự bảo đảm exactly-once gửi mail.

## 14. Lease và fencing token: phục hồi khi worker crash

Worker có thể chết sau khi claim nhưng trước khi cập nhật kết quả:

~~~text
Worker A claims job
   status=CLAIMED
   leaseUntil=09:02
   claimToken=A-123

Worker A crashes

After lease expires:
   Worker B can recover job
   claimToken=B-789
~~~

Nếu A thực ra chỉ bị pause lâu rồi chạy lại, A có thể ghi kết quả sau B. Vì vậy mọi state update của worker phải có điều kiện ownership:

~~~sql
UPDATE scheduled_mail
SET status = 'SUBMITTED',
    submitted_at = CURRENT_TIMESTAMP,
    lease_until = NULL,
    claim_token = NULL,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :job_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token
RETURNING id;
~~~

Nếu không có row được update, worker **đã mất quyền ghi state** và phải xử lý như một race cần điều tra/đối soát; không tự ghi đè bằng update không điều kiện.

### Lease expiry không đồng nghĩa “SMTP chưa được gửi”

Đây là điểm quan trọng:

~~~text
Worker A claims
Worker A calls SMTP
SMTP provider accepts
Worker A crashes before saving SUBMITTED
Lease expires
Worker B sees expired PROCESSING
~~~

Nếu B tự động đưa job về PENDING rồi gửi lại, người nhận có thể nhận **hai thư**. Fencing token bảo vệ database khỏi stale writer, **không thể thu hồi email đã nộp cho SMTP server**.

Do đó tách hai trường hợp:

- **CLAIMED nhưng chưa bắt đầu submit**, có bằng chứng chưa phát sinh external side effect: có thể đưa về PENDING để xử lý lại.
- **PROCESSING/attempt đã bắt đầu** mà chưa lưu outcome: có khả năng provider đã accepted; chuyển sang `UNKNOWN` để đối soát/chọn chính sách retry.

Ngay cả mốc “bắt đầu submit” lưu trong database và việc thực sự gọi network cũng không thể tạo atomic transaction tuyệt đối giữa DB với SMTP. Hệ thống cần nhận thức giới hạn đó thay vì đưa ra bảo đảm giả.

## 15. Đánh dấu bắt đầu gửi trước khi gọi JavaMailSender

Sau khi claim và kiểm tra business eligibility, quota, worker có thể tạo một **attempt record** trước khi gọi SMTP:

~~~sql
CREATE TABLE mail_submission_attempt (
    id UUID PRIMARY KEY,
    mail_job_id UUID NOT NULL REFERENCES scheduled_mail(id),
    attempt_number INT NOT NULL,
    provider_id VARCHAR(80) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(24),
    error_code VARCHAR(80),
    provider_message_id VARCHAR(255),
    UNIQUE (mail_job_id, attempt_number)
);
~~~

Và trong transaction:

~~~sql
UPDATE scheduled_mail
SET status = 'PROCESSING',
    attempt_count = attempt_count + 1,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :job_id
  AND status = 'CLAIMED'
  AND claim_token = :claim_token
  AND (expires_at IS NULL
       OR expires_at > CURRENT_TIMESTAMP)
RETURNING attempt_count;
~~~

Nếu thành công, insert một row `mail_submission_attempt` cho attempt tương ứng trong **cùng transaction**, sau đó commit rồi mới gọi `JavaMailSender.send(...)`.

### Vì sao attempt_count không tăng khi bị rate limiter deny?

Nếu chưa được phép gọi SMTP vì quota chưa có permit, đó là **deferral**, không phải SMTP attempt. Hãy đặt `next_attempt_at` mới, giải phóng claim và giữ `attempt_count`. Số lần rate-limiter defer có thể được đo riêng, không dùng số lần này để áp max SMTP retry.

### Có thể có lỗi khi tạo MIME?

Lỗi template/attachment/resource xảy ra **trước khi thực sự submit** nếu compose được thực hiện trước network call. Có thể ghi `MIME_PREPARATION_FAILED` và tách `attempt_count` hoặc `preparation_attempt_count` theo chính sách; không tự khẳng định provider đã bị gọi. Thứ tự “compose trước hay reserve permit trước” là một trade-off cần được mô tả rõ trong dispatcher.

## 16. Cập nhật trạng thái bằng compare-and-set

Một state transition an toàn thường có điều kiện cả **ID, trạng thái hiện tại và ownership/version**:

~~~sql
UPDATE scheduled_mail
SET status = 'RETRY',
    next_attempt_at = :next_attempt_at,
    last_failed_at = CURRENT_TIMESTAMP,
    last_error_code = :safe_error_code,
    claim_token = NULL,
    lease_until = NULL,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :job_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token
RETURNING id;
~~~

`:safe_error_code` nên là enum/code được chuẩn hóa, ví dụ `SMTP_TEMPORARY_FAILURE`; không dump nguyên `exception.getMessage()` vì provider có thể echo recipient hoặc dữ liệu nhạy cảm.

Khi có 0 row được update:

- Job có thể đã bị một worker khác claim sau lease expiry.
- Người dùng có thể đã hủy khi job chưa bắt đầu gửi.
- Một component khác có thể đã ghi kết quả.
- Worker có thể đang dùng claim token cũ.

**Không xử lý bằng cách bỏ điều kiện status/token rồi update lại.** Cần tra trạng thái hiện tại và áp policy đối soát phù hợp.

## 17. Hủy lịch và đổi giờ gửi phải xử lý cạnh tranh

Giả sử người dùng đặt lịch 10:00 rồi đổi sang 11:00. Một HTTP request có thể đến đúng lúc dispatcher đang claim.

### Khi còn PENDING hoặc RETRY

Có thể reschedule atomically:

~~~sql
UPDATE scheduled_mail
SET scheduled_at = :new_scheduled_at,
    next_attempt_at = :new_scheduled_at,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :job_id
  AND tenant_id = :tenant_id
  AND status IN ('PENDING', 'RETRY')
  AND version = :expected_version
RETURNING id, version;
~~~

Nếu update thành công, lịch mới được ghi. Nếu không, không đoán rằng job đã được đổi; trả về conflict hoặc trạng thái thực tế cho caller. Nếu job đã bị claim, tùy nghiệp vụ có thể yêu cầu worker release claim trước khi cho reschedule.

### Khi đã CLAIMED hoặc PROCESSING

Hủy ở trạng thái CLAIMED có thể được phép nếu **chưa bước sang điểm không thể thu hồi** và transaction kiểm soát ownership. Sau khi đã bắt đầu gọi SMTP, không thể bảo đảm ngăn thư đến người nhận.

Một API nên thể hiện rõ:

~~~text
Cancellation accepted:
    job was PENDING/RETRY -> CANCELLED

Cancellation rejected/conflict:
    job is PROCESSING/SUBMITTED/UNKNOWN
    cannot guarantee email will not be sent
~~~

Không phản hồi “Đã hủy thành công” khi chỉ set một flag rồi worker đã gửi SMTP ở thread khác. Với email đã được provider accepted, một chức năng “recall” (nếu có) là nghiệp vụ/phụ thuộc provider riêng, không phải SQL rollback.

## 18. Tạo scheduler trong Spring Boot

Một cách đơn giản để đánh thức dispatcher là `@Scheduled`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class MailSchedulingConfiguration {
}
~~~

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class ScheduledMailPoller {
    private final MailDispatchService dispatcher;

    public ScheduledMailPoller(
            MailDispatchService dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(
            fixedDelayString = "${app.mail.dispatch.poll-delay-ms:1000}")
    public void dispatchDue() {
        dispatcher.processReadyBatch();
    }
}
~~~

`MailDispatchService` là service ứng dụng, không phải class có sẵn của Spring Mail. Scheduler chỉ kích hoạt quá trình tìm job, không ghi nhớ toàn bộ lịch trong RAM.

Ví dụ cấu hình:

~~~yaml
app:
  mail:
    dispatch:
      poll-delay-ms: 1000
      batch-size: 50
      max-concurrent: 5
      lease-seconds: 120
~~~

Các trường `app.mail.dispatch.*` là **cấu hình tự định nghĩa**. Việc đặt chúng vào YAML không tự tạo durable scheduler hay outbox; application phải bind và thực thi.

### fixedDelay và fixedRate khác nhau

- `fixedDelay`: khoảng thời gian giữa **khi invocation trước kết thúc** và **khi invocation kế tiếp bắt đầu** theo scheduler semantics.
- `fixedRate`: cố gắng chạy theo chu kỳ cố định; có thể dẫn đến các đợt phải chờ hoặc overlap khi cách cấu hình executor/task khác nhau.
- `cron`: kích hoạt theo lịch biểu; phù hợp nhắc dispatcher hoặc tác vụ định kỳ, không nên thay việc lưu `scheduled_at` cho từng mail job.

**Không giữ hàng nghìn SMTP submissions trực tiếp trong một scheduled invocation chạy đồng bộ.** Nên có worker pool giới hạn, claim batch theo năng lực và tách việc thực hiện network khỏi scheduler tick.

### Nhiều replicas đều kích hoạt @Scheduled

Nếu triển khai 4 Spring Boot pods, mỗi pod có thể chạy `@Scheduled`. Không có cơ chế leader election mặc định tự động khiến chỉ một pod chạy. Với PostgreSQL `SKIP LOCKED` và claim/lease đúng cách, nhiều dispatcher có thể cạnh tranh an toàn hơn. Với một cron task chỉ được phép chạy một lần toàn cụm, cần thêm distributed locking phù hợp.

## 19. Đường đi của một mail job qua các lớp service

Một thiết kế tách trách nhiệm:

~~~text
ScheduledMailPoller
   |
   v
MailDispatchService
   |
   +-- MailJobRepository.claimDueBatch()
   +-- EligibilityService.validate()
   +-- ProviderQuotaGate.tryReserve()
   +-- MimeMessageFactory.compose()
   +-- MailSubmissionAdapter.submit()
   +-- MailJobRepository.commitOutcome()
~~~

Các abstraction nên có contract rõ:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public interface MailJobRepository {
    List<ClaimedMailJob> claimDueBatch(
            Instant now, int batchSize);

    boolean beginSubmission(UUID id, UUID claimToken);

    boolean markSubmitted(
            UUID id, UUID claimToken, Instant submittedAt);

    boolean deferForRetry(
            UUID id, UUID claimToken,
            Instant nextAttemptAt,
            String errorCode);

    boolean markUnknown(
            UUID id, UUID claimToken, String errorCode);
}

public record ClaimedMailJob(
        UUID id,
        UUID claimToken,
        String notificationType,
        String payloadRef,
        Instant scheduledAt,
        Instant nextAttemptAt,
        Instant expiresAt) {
}
~~~

`MailJobRepository` và `ClaimedMailJob` là mã minh họa. Mỗi method lưu state nên dùng transaction ngắn và kiểm tra token/status. Những method trả `false` khi state không còn tương thích; caller phải xử lý lost claim, không lặp ghi không điều kiện.

## 20. Ví dụ dispatcher kết hợp JavaMailSender

Đoạn dưới cho thấy luồng chính; nó cố ý dùng interface để tránh trộn SQL, SMTP và retry vào cùng một class:

~~~java
import java.time.Clock;
import java.time.Instant;
import org.springframework.mail.MailException;
import org.springframework.stereotype.Service;

@Service
public final class MailDispatchService {
    private final MailJobRepository jobs;
    private final MailSubmissionAdapter sender;
    private final MailErrorPolicy errorPolicy;
    private final Clock clock;

    public MailDispatchService(
            MailJobRepository jobs,
            MailSubmissionAdapter sender,
            MailErrorPolicy errorPolicy,
            Clock clock) {
        this.jobs = jobs;
        this.sender = sender;
        this.errorPolicy = errorPolicy;
        this.clock = clock;
    }

    public void processReadyBatch() {
        Instant now = clock.instant();
        for (ClaimedMailJob job :
                jobs.claimDueBatch(now, 50)) {
            dispatchOne(job);
        }
    }

    private void dispatchOne(ClaimedMailJob job) {
        // Production: kiểm tra lại consent, expiry, quota,
        // sender authorization và claim ownership trước submit.
        if (!jobs.beginSubmission(job.id(), job.claimToken())) {
            return;
        }

        try {
            sender.submit(job);
            boolean saved = jobs.markSubmitted(
                    job.id(), job.claimToken(), clock.instant());
            if (!saved) {
                // Không tự gửi lại; cần đối soát claim/state.
                reportStateConflict(job.id());
            }
        } catch (MailException ex) {
            MailSubmissionDecision decision =
                    errorPolicy.decide(ex, clock.instant());
            if (decision.kind() == SubmissionKind.RETRY) {
                jobs.deferForRetry(
                        job.id(), job.claimToken(),
                        decision.nextAttemptAt(),
                        decision.errorCode());
            } else {
                jobs.markUnknown(
                        job.id(), job.claimToken(),
                        decision.errorCode());
            }
        }
    }

    private void reportStateConflict(java.util.UUID jobId) {
        // Log jobId + mã lỗi nội bộ; báo reconciliation.
    }
}
~~~

`MailSubmissionAdapter`, `MailErrorPolicy`, `MailSubmissionDecision` và `SubmissionKind` là abstraction của ứng dụng. Ví dụ **không phải implementation production hoàn chỉnh**:

- Chưa triển khai `FAILED` cho permanent error, quota deferral trước submit, xử lý MIME preparation failure, recovery từ lease hoặc outbox reservation.
- `catch (MailException)` không bao trùm mọi lỗi I/O/resource/database; các lỗi phải được phân loại theo phase.
- Khi SMTP đã accepted nhưng cập nhật `markSubmitted` thất bại, không được retry ngay. Phải ghi nhận và đối soát outcome.
- Trước `beginSubmission` cần kiểm tra lại eligibility/expiration; trong ứng dụng thực, claim/eligibility/transition phải được đồng bộ bằng DB conditions.
- Nếu method xử lý 50 job tuần tự mà mỗi SMTP call rất chậm, throughput sẽ thấp; có thể dispatch vào bounded executor nhưng vẫn phải bảo đảm lease và không claim nhiều hơn capacity.

### Adapter gửi SMTP

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;

public interface MailSubmissionAdapter {
    void submit(ClaimedMailJob job);
}

public final class SmtpMailSubmissionAdapter
        implements MailSubmissionAdapter {
    private final JavaMailSender mailSender;
    private final ScheduledMimeMessageFactory factory;

    public SmtpMailSubmissionAdapter(
            JavaMailSender mailSender,
            ScheduledMimeMessageFactory factory) {
        this.mailSender = mailSender;
        this.factory = factory;
    }

    @Override
    public void submit(ClaimedMailJob job) {
        MimeMessage message = mailSender.createMimeMessage();
        factory.populate(message, job);
        mailSender.send(message);
    }
}
~~~

`ScheduledMimeMessageFactory.populate(...)` phải được thiết kế để có thể báo lỗi chuẩn bị nội dung riêng. Nếu dùng `MimeMessageHelper`, thường cần xử lý `jakarta.mail.MessagingException` trong factory. Ví dụ adapter giả định factory đã chuyển lỗi đó thành một exception ứng dụng có ý nghĩa phù hợp, thay vì ném checked exception chưa khai báo.

Một ưu điểm của adapter là code business/scheduler không cần biết chi tiết SMTP và có thể thay thế bằng fake sender trong unit test.

## 21. Kiểm soát thời gian bằng Clock

Không hardcode `Instant.now()` rải rác trong mọi class nếu cần test mốc thời gian:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfiguration {
    @Bean
    Clock utcClock() {
        return Clock.systemUTC();
    }
}
~~~

Trong test có thể dùng:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
        Instant.parse("2026-11-15T08:59:59Z"),
        ZoneOffset.UTC);
~~~

Test không cần `Thread.sleep(...)` để chờ tới 09:00. Có thể khởi tạo lại fixed clock tại instant sau deadline, hoặc dùng một mutable test clock được điều khiển bởi test. Các timestamp cho **quyết định nghiệp vụ** cần thống nhất nguồn clock; nếu SQL dùng `CURRENT_TIMESTAMP` còn Java dùng clock giả, test integration phải xem xét sự khác biệt này.

### Đồng hồ database và đồng hồ ứng dụng

Một SQL claim dùng `CURRENT_TIMESTAMP` theo DB server; application đôi khi tính `nextAttemptAt` bằng Java. Nếu clock lệch nhau, job có thể bị gửi sớm/muộn hoặc lease timeout sai.

Quy tắc vận hành:

- Đồng bộ thời gian host/DB qua cơ chế time synchronization đáng tin.
- Dùng UTC/instant trong state.
- Chọn rõ **nguồn giờ quyết định due/lease**; với claim DB, ưu tiên đồng hồ DB trong transaction đó.
- Không dùng timestamp từ client làm clock tin cậy để quyết định job đến hạn.
- Giám sát lệch giờ khi có nhiều regions hoặc external dependencies.

## 22. Retry khác với đặt lại lịch hẹn ban đầu

Khi SMTP provider trả lỗi tạm thời, cập nhật:

~~~text
status         = RETRY
scheduled_at   = giữ nguyên
next_attempt_at= now + backoff
attempt_count  = attempt_count thực tế
last_error_code= SMTP_TEMPORARY_FAILURE
last_failed_at = now
~~~

Đừng tăng `scheduled_at` thành giờ retry nếu trường này đại diện **lịch do người dùng chọn**. Nhờ đó có thể phân tích:

- Email bị trễ bao lâu so với lịch ban đầu?
- Bao nhiêu thời gian bị ảnh hưởng bởi quota?
- Có bao nhiêu lần SMTP thực sự được gọi?
- Người dùng đổi lịch bao nhiêu lần, khác với retry tự động ra sao?

### Retry nào an toàn?

Không phải mọi exception đều bảo đảm có thể gọi lại:

| Phản hồi | Chính sách gợi ý |
|---|---|
| Lỗi build template/MIME | Không retry SMTP; sửa dữ liệu hoặc resource |
| Authentication rejected | Pause tuyến, sửa credential |
| SMTP temporary rejection rõ ràng | Retry với backoff và rate permit |
| SMTP permanent rejection | Mark FAILED / suppress, không retry mù |
| TCP connect fail trước SMTP session | Có thể retry theo policy |
| Connection lost sau DATA | UNKNOWN; có thể provider đã accepted |
| `mailSender.send` trả thành công | Mark SUBMITTED, không retry vì chưa có delivery event |

Một `MailSendException` có thể chứa các nguyên nhân khác nhau, đặc biệt khi gửi batch messages. Classifier phải xét phase, status code và kết quả được biết, không chỉ coi mọi `MailException` là tạm thời.

## 23. Exponential backoff và jitter cho next_attempt_at

Nếu 1.000 job cùng lỗi lúc 09:00 và đều retry lúc 09:01, các worker có thể đồng thời mở nhiều kết nối SMTP, tạo một đợt throttling mới.

**Exponential backoff** với giới hạn trần:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Trong đó:

- `d0` là khoảng chờ cơ bản.
- `n` là lần thất bại liên tiếp.
- `dmax` là thời gian chờ tối đa.

Thêm jitter để phân tán lần retry:

\[
d_{\text{actual}} \sim U(0,d_n)
\]

Với **full jitter**, delay có thể rất nhỏ; nếu provider yêu cầu không thử lại quá sớm, hãy đặt thời gian chờ tối thiểu hoặc chọn một biến thể jitter có sàn.

Ví dụ Java:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;

public final class MailRetrySchedule {
    private final long baseMillis;
    private final long maximumMillis;

    public MailRetrySchedule(Duration base, Duration max) {
        this.baseMillis = base.toMillis();
        this.maximumMillis = max.toMillis();
        if (baseMillis <= 0 || maximumMillis < baseMillis) {
            throw new IllegalArgumentException(
                    "Invalid mail retry intervals");
        }
    }

    public Instant nextAttemptAt(
            Instant now, int failureNumber) {
        if (failureNumber < 1) {
            throw new IllegalArgumentException(
                    "failureNumber must start at 1");
        }

        long cap = baseMillis;
        for (int i = 1; i < failureNumber; i++) {
            if (cap >= maximumMillis) {
                break;
            }
            cap = cap > maximumMillis / 2
                    ? maximumMillis
                    : cap * 2;
        }

        long randomizedMillis =
                ThreadLocalRandom.current().nextLong(cap + 1);
        return now.plusMillis(randomizedMillis);
    }
}
~~~

Khi dùng trong production cần thêm:

- Max attempts, retry deadline và tổng tuổi job.
- Min retry delay nếu provider không chấp nhận retry ngay.
- Phân loại lỗi permanent/auth/UNKNOWN không đi vào retry mù.
- Tôn trọng provider-specific cooldown.
- Kết hợp `next_attempt_at` với daily quota reset/rate limiter permit.
- Lưu `next_attempt_at` trong DB trước khi kết thúc worker, không chỉ đặt timer trong RAM.

### Retry-After có áp dụng cho SMTP không?

Với **HTTP email API**, provider có thể trả HTTP 429 và header `Retry-After`; cần đọc theo tài liệu API. Với **SMTP**, không có một header HTTP Retry-After phổ quát tương đương. SMTP dùng reply code như 421/450/451/452 và các enhanced codes khác tùy provider; không được coi mọi 4xx là “rate limit”.

## 24. Khi rate limiter từ chối, cập nhật trạng thái ra sao?

Một job đúng lịch không phải lúc nào cũng được phép gọi SMTP ngay. Provider có thể đã cạn recipients/day, hoặc một account đã đạt giới hạn message/second.

Trường hợp quota chưa có permit:

~~~text
Trước:
status          = CLAIMED
scheduled_at    = 09:00
next_attempt_at = 09:00
attempt_count   = 0

Quota gate denies until 09:01

Sau:
status          = PENDING
scheduled_at    = 09:00  (giữ nguyên)
next_attempt_at = 09:01
attempt_count   = 0     (không có SMTP attempt)
defer_reason    = PROVIDER_RATE_LIMIT
~~~

Lưu thời điểm **thử sớm nhất** theo permit/quota, không giữ worker ngủ trong nhiều phút.

Khi nhiều giới hạn chồng nhau:

~~~text
message rate next available  = 09:01
daily quota next recheck     = 10:00
security lane policy        = 09:30
~~~

thì một thời điểm hợp lý để xem xét lại có thể là:

\[
\text{nextAttemptAt} =
 \max(\text{earliestAllowedAt}_1,
      \text{earliestAllowedAt}_2,
      \ldots)
\]

Lưu ý không thể luôn tính chính xác một thời điểm nếu provider chỉ cho biết quota ước tính. Khi đó đặt thời điểm recheck thận trọng và **luôn xin permit lại** trước submission. Với mail ưu tiên cao, có thể có quota reservation riêng được phê duyệt; không tự bypass giới hạn provider.

### Không dùng trạng thái RETRY cho mọi loại defer

Nếu chưa từng gọi SMTP, trạng thái `PENDING` với `defer_reason=QUOTA` là dễ hiểu. `RETRY` nên được dành cho các công việc đã thất bại theo contract của ứng dụng. Nếu chọn mô hình khác, cần nhất quán giữa logic, dashboard và attempt counter.

## 25. Lưu lịch sử chuyển trạng thái để điều tra

Bảng hiện tại cho biết trạng thái **mới nhất**, nhưng người vận hành còn cần biết job đã đi qua các trạng thái gì.

Ví dụ:

~~~text
09:00:00 PENDING
09:00:01 CLAIMED
09:00:02 PROCESSING
09:00:03 RETRY / TEMPORARY_SMTP_FAILURE
09:05:15 CLAIMED
09:05:16 PROCESSING
09:05:17 SUBMITTED
~~~

Có thể tạo bảng audit:

~~~sql
CREATE TABLE scheduled_mail_status_event (
    id BIGSERIAL PRIMARY KEY,
    mail_job_id UUID NOT NULL
        REFERENCES scheduled_mail(id),
    transition_id UUID NOT NULL UNIQUE,
    from_status VARCHAR(24),
    to_status VARCHAR(24) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    actor_type VARCHAR(32) NOT NULL,
    actor_ref VARCHAR(100),
    attempt_number INT,
    safe_reason_code VARCHAR(80),
    detail_ref VARCHAR(160)
);

CREATE INDEX idx_mail_status_event_job
    ON scheduled_mail_status_event (
        mail_job_id, occurred_at, id);
~~~

Ghi event **trong cùng transaction** với update `scheduled_mail.status`. Nếu insert audit event thất bại mà status vẫn commit, lịch sử không còn phản ánh thực tế.

Một record sự kiện nên có:

| Trường | Mục đích |
|---|---|
| `transition_id` | Chống tạo trùng sự kiện khi client retry |
| `from_status` / `to_status` | Theo dõi state machine |
| `occurred_at` | Mốc thời gian chính thức |
| `actor_type` | USER, SYSTEM, WORKER, PROVIDER_CALLBACK... |
| `actor_ref` | Opaque ID, không phải email/password |
| `attempt_number` | Nối với lần SMTP submit |
| `safe_reason_code` | QUOTA, SMTP_TEMPORARY, CANCELLED_BY_USER... |
| `detail_ref` | Tham chiếu chẩn đoán có quyền, không chứa raw MIME |

Không log raw exception/SMTP transcript vào bảng audit dạng text tự do. Provider response có thể chứa địa chỉ người nhận, subject hoặc thông tin server nhạy cảm.

### Trạng thái hiện tại và event history không được mâu thuẫn

Với nguồn sự thật là database:

~~~text
TX:
  UPDATE scheduled_mail ... WHERE expected_status/token
  INSERT scheduled_mail_status_event ...
COMMIT
~~~

Nếu 0 row được update do optimistic lock, **không tạo event như thể transition đã xảy ra**. Hệ thống có thể dùng event sourcing chuyên biệt, nhưng vẫn cần consistency và idempotency của event append.

## 26. Khi có delivery event: gắn với đúng message attempt

Sau khi SMTP accepted, một số provider cung cấp webhook hoặc DSN về kết quả giao thư:

~~~text
scheduled_mail:
  status       = SUBMITTED
  submitted_at = 09:05:17

provider webhook later:
  event        = DELIVERED
  event_time   = 09:05:45

scheduled_mail:
  status       = DELIVERED
  delivered_at = 09:05:45
~~~

Để nối event đúng mail job, lưu **provider message ID** hoặc attempt correlation khi provider hỗ trợ:

~~~text
mailJobId
  |
  +-- submissionAttemptId
         |
         +-- providerId
         +-- providerMessageId
         +-- submittedAt
~~~

Nếu webhook đến trùng, xử lý idempotently theo `eventId`/provider event key đã được kiểm chứng. Nếu webhook đến **không theo thứ tự**, cần policy transition:

- `DELIVERED` không bị một event `SUBMITTED` tới muộn ghi lùi lại.
- `BOUNCED` và `DELIVERED` có thể cần mô hình trạng thái delivery tách biệt khi provider phát nhiều loại event cho cùng thư.
- Một provider callback có timestamp nguồn riêng; cần lưu thời gian **nhận callback** nếu muốn đo delay và kiểm tra clock skew.
- Nếu provider không cung cấp delivery confirmation, `delivered_at` để null thay vì suy luận từ `submitted_at`.

### Tách submission state và delivery state khi workflow lớn

Một cột `status` duy nhất có thể không mô tả hết:

~~~text
submissionStatus = ACCEPTED
deliveryStatus   = DEFERRED
processingStatus = DONE
~~~

Với hệ thống nhiều provider, nhiều recipients, bounce và complaint tracking, có thể dùng **submission_attempt** và **delivery_event** tables, còn job status thể hiện lifecycle điều phối. Không cần ép mọi sự kiện vào một enum khổng lồ không có transitions rõ ràng.

## 27. Cách xử lý message có nhiều người nhận

Một `MimeMessage` có thể gửi tới nhiều To/Cc/Bcc. Provider có thể accept một phần recipient, từ chối phần còn lại hoặc báo kết quả delivery riêng từng người.

Nếu nghiệp vụ cần lưu trạng thái **theo từng người nhận**, một job chỉ có một `submitted_at` là không đủ. Có thể bổ sung:

~~~sql
CREATE TABLE scheduled_mail_recipient (
    mail_job_id UUID NOT NULL
        REFERENCES scheduled_mail(id),
    recipient_ref VARCHAR(160) NOT NULL,
    recipient_role VARCHAR(8) NOT NULL,
    submission_status VARCHAR(24) NOT NULL,
    delivery_status VARCHAR(24),
    submitted_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    last_error_code VARCHAR(80),
    PRIMARY KEY (mail_job_id, recipient_ref)
);
~~~

Đây là schema gợi ý cho trường hợp `recipient_ref` có unique semantics trong một job; nếu cùng mailbox xuất hiện ở nhiều role hoặc có recipient delivery IDs khác nhau, cần khóa riêng thích hợp.

Với email cá nhân hóa, một **mail job/recipient** thường đơn giản hơn để audit, retry và bảo vệ Bcc. Nhưng thiết kế có thể có yêu cầu broadcast; phải chọn cấu trúc đáp ứng ngữ nghĩa phần recipient mà provider thực sự trả về.

## 28. API tạo, xem, đổi và hủy lịch gửi

Một API nên trả rõ **trạng thái hiện tại và mốc thời gian** thay vì chỉ `200 OK` và chuỗi “email đã gửi”.

### Tạo yêu cầu đặt lịch

~~~http
POST /api/notification-jobs
Idempotency-Key: order-receipt-1001-v1
Content-Type: application/json

{
  "notificationType": "ORDER_RECEIPT",
  "businessRef": "order-1001",
  "scheduledAt": "2026-11-16T09:00:00+07:00"
}
~~~

Phía server:

1. Xác thực quyền với `businessRef`.
2. Chỉ chấp nhận những `notificationType` đã được cấp quyền.
3. Parse `scheduledAt` thành `OffsetDateTime` hoặc một kiểu chứa đủ thông tin timezone để chuyển sang `Instant`.
4. Kiểm tra thời điểm hợp lệ, giới hạn đặt lịch trước/quá xa và policy thời hạn.
5. Tạo job `PENDING` và `next_attempt_at = scheduled_at` trong transaction.
6. Trả ID opaque và dữ liệu trạng thái.

Ví dụ response:

~~~json
{
  "jobId": "018d51e2-13d9-7479-a1a7-256b9f641100",
  "status": "PENDING",
  "scheduledAt": "2026-11-16T02:00:00Z",
  "nextAttemptAt": "2026-11-16T02:00:00Z",
  "submittedAt": null,
  "version": 1
}
~~~

Đây là API minh họa, không phải endpoint có sẵn trong Spring Mail. Không nên cho client truyền raw SMTP credentials, arbitrary From, thư HTML chưa được cấp quyền hoặc quota override tùy ý.

### Đổi lịch

~~~http
PATCH /api/notification-jobs/{jobId}/schedule
If-Match: "1"
Content-Type: application/json

{
  "scheduledAt": "2026-11-16T10:00:00+07:00"
}
~~~

Server chỉ cho đổi khi state hợp lệ, kiểm tra `version`/ETag và ghi transition. Nếu job đã được claim/bắt đầu submission, có thể trả HTTP 409 Conflict tùy policy. Không nói “đổi lịch thành công” rồi âm thầm để worker gửi theo lịch cũ.

### Hủy lịch

~~~http
POST /api/notification-jobs/{jobId}/cancel
~~~

Trả kết quả phân biệt:

~~~text
CANCELLED: job còn ở trạng thái có thể hủy
CONFLICT: job đang PROCESSING / đã SUBMITTED
ALREADY_CANCELLED: yêu cầu lặp lại, idempotent
NOT_FOUND / FORBIDDEN: không có quyền hoặc job không tồn tại
~~~

Không để response vô tình lộ thông tin về job của tenant khác. Nếu chưa có quyền, phản hồi nên tuân thủ chính sách bảo mật API của ứng dụng.

## 29. Lịch lặp lại khác với job gửi một lần

Một bảng `scheduled_mail` là nơi lưu **các lần gửi cụ thể**. Nếu người dùng yêu cầu:

> Gửi báo cáo lúc 08:00 mỗi thứ Hai theo giờ địa phương.

thì nên có **lịch định kỳ** riêng và tạo từng job occurrence:

~~~text
RecurringSchedule
  id=weekly-report-42
  time=08:00
  dayOfWeek=MONDAY
  zoneId=Asia/Ho_Chi_Minh
  status=ACTIVE
  revision=3
            |
            v
ScheduledMail occurrence #1
  scheduledAt=...
  status=SUBMITTED
            |
            v
ScheduledMail occurrence #2
  scheduledAt=...
  status=PENDING
~~~

Điều này cho phép:

- Lịch tổng được tạm dừng/hủy mà không xóa lịch sử đã gửi.
- Mỗi occurrence có `scheduled_at`, `next_attempt_at` và `status` riêng.
- Retry của tuần trước không làm thay đổi thời điểm tuần sau.
- Mỗi occurrence có idempotency key như `scheduleId:occurrenceLocalDate:revision`.
- DST và timezone được xử lý ở bước **tính occurrence** thay vì khi worker SMTP submit.

**Không coi một mail job duy nhất là recurring schedule bằng cách ghi đè `scheduled_at` sau mỗi lần gửi.** Làm vậy mất lịch sử và khiến submittedAt của occurrence trước bị trộn với lịch mới.

### Scheduler misfire sau downtime

Nếu application tắt vào 08:00 và chạy lại lúc 09:30, hệ thống phải có chính sách:

1. **Catch up:** gửi những occurrence đã lỡ nếu còn hạn.
2. **Skip:** bỏ occurrence đã quá muộn, tạo occurrence tiếp theo.
3. **Coalesce:** gộp nhiều occurrence bỏ lỡ thành một bản tổng hợp nếu nghiệp vụ cho phép.
4. **Manual review:** cần người vận hành quyết định cho các thông báo nhạy cảm.

Chính sách misfire nên được **lưu thành cấu hình/quy tắc nghiệp vụ**, không tự suy luận từ việc một cron tick đã bị mất.

## 30. Khi nào cần Quartz thay cho @Scheduled?

Một số hệ thống sử dụng Quartz với JDBC JobStore để lưu trigger/jobs, đặc biệt khi có nhiều cron schedules, calendars và yêu cầu scheduling nâng cao.

Tuy nhiên, ngay cả khi Quartz giúp **kích hoạt tác vụ đúng lịch và lưu trigger**, email workflow vẫn phải quản lý:

- Trạng thái từng mail job.
- Idempotency key.
- SMTP submission attempts.
- Xử lý `UNKNOWN_OUTCOME` và delivery events.
- Quyền hủy/đổi lịch.
- Provider quota và retries.
- Nội dung/recipient cần bảo vệ.

| Phương án | Phù hợp | Cần tự xây |
|---|---|---|
| `@Scheduled` + database outbox | Nhiều email jobs với thời điểm riêng, query due jobs | Claim/lease, state machine, retry, metrics |
| Quartz JDBC JobStore | Cron/trigger/calendars phức tạp | Mail lifecycle, SMTP idempotency, delivery tracking |
| Message queue delayed delivery | Pipeline event-driven, độ trễ tốt nếu broker hỗ trợ | Persistence/state, cancellation, retry/expiry semantics |
| External scheduler | Hệ thống đã có dịch vụ lập lịch chung | Mail job state, routing, quota, outage recovery |

Không có lựa chọn nào tự bảo đảm **exactly-once delivery** qua SMTP. Quartz trigger “đã chạy” không đồng nghĩa email “đã delivered”.

## 31. Retry sau khi worker chết: một bảng quyết định

Thử xét các cửa sổ lỗi:

| Điểm crash | Trạng thái còn trong DB | Cách phục hồi |
|---|---|---|
| Trước tạo job commit | Không có job | Client retry nghiệp vụ với idempotency key |
| Sau tạo job commit, trước poll | PENDING | Scheduler sau tiếp tục lấy |
| Sau claim, trước attempt | CLAIMED | Lease expiry; có thể reclaim sau khi xác minh chưa submit |
| Sau ghi PROCESSING, trước network call | PROCESSING | Có thể thấy UNKNOWN dù SMTP chưa gọi; cần reconcile/policy |
| Sau SMTP accepted, trước DB commit | PROCESSING | Outcome UNKNOWN; tránh resend vô điều kiện |
| Sau DB mark SUBMITTED | SUBMITTED | Không gửi lại; đợi delivery events |
| Sau RETRY commit, trước scheduled tick | RETRY | Query due khi đến nextAttemptAt |
| Trong lúc provider webhook đến | SUBMITTED/DELIVERED... | Callback idempotent và transition có điều kiện |

### Vì sao không thể xử lý tất cả crash bằng một retry?

Không có transaction phân tán nguyên tử giữa PostgreSQL và SMTP server trong thiết kế thông thường. Một lần `send(...)` có thể hoàn tất ở server mà ứng dụng chưa kịp ghi `SUBMITTED`. Việc gửi lại có nguy cơ tạo thư trùng.

Biện pháp:

- Ghi trạng thái attempt trước khi bắt đầu network I/O.
- Đặt status `UNKNOWN` khi không có bằng chứng chắc chắn.
- Dùng provider API/message trace hoặc idempotency key **chỉ khi provider thật sự hỗ trợ semantics đó**.
- Đối với thông báo có thể gửi lại, quyết định rõ mức rủi ro duplicate.
- Với giao dịch nhạy cảm, cân nhắc cần reconciliation/manual approval trước khi retry.
- Không dùng `Message-ID` như một bảo đảm dedup tuyệt đối ở bên nhận.

## 32. Sử dụng giờ hệ thống và timestamp chính xác

Một số bẫy về dữ liệu thời gian:

### 32.1. Cắt bỏ timezone khi nhận từ API

~~~text
"2026-11-16T09:00:00"
~~~

Chuỗi này là **local date-time không có offset/timezone**. Nếu user ở Việt Nam, Paris hoặc New York, nó chỉ tới những instant khác nhau. Cần thêm timezone hoặc yêu cầu input có offset:

~~~text
"2026-11-16T09:00:00+07:00"
~~~

### 32.2. Dùng SQL TIMESTAMP WITHOUT TIME ZONE

`TIMESTAMP WITHOUT TIME ZONE` không lưu timezone/offset và dễ tạo nhầm lẫn khi app/DB session cấu hình khác nhau. Với thời điểm gửi tuyệt đối, `TIMESTAMPTZ` là lựa chọn phù hợp trong PostgreSQL; nó lưu ngữ nghĩa instant và hiển thị theo timezone session.

### 32.3. Dùng đồng hồ local của client cho lease

Lease expiry không nên dựa vào một timestamp không đáng tin do browser gửi lên. Database có thể dùng `CURRENT_TIMESTAMP` trong transaction claim/renew; API request time chỉ là input nghiệp vụ được kiểm tra.

### 32.4. Cộng ngày bằng số mili-giây cho lịch địa phương

Một recurrence “09:00 mỗi ngày” không giống “cộng 86.400 giây” khi timezone có DST. Tính occurrence theo local date/time + ZoneId rồi chuyển sang Instant.

### 32.5. So sánh bằng string

~~~java
if (scheduledString.compareTo(nowString) <= 0) { ... }
~~~

Chuỗi có offset khác nhau không nhất thiết có thứ tự từ điển phản ánh thứ tự instant. Parse thành `Instant` hoặc `OffsetDateTime`, rồi so bằng kiểu thời gian.

### 32.6. Nghĩ rằng submittedAt luôn sau scheduledAt vài mili-giây

Nếu backlog lớn, rate limiter từ chối hoặc server chậm, `submittedAt` có thể trễ phút/giờ. SLA nên đo độ trễ thực và cảnh báo khi vượt ngưỡng.

## 33. Unit test: chỉ gửi khi đến scheduled_at

Điểm quan trọng nhất của hệ thống đặt lịch là **không gửi sớm**. Có thể kiểm tra policy bằng `Clock.fixed` và một hàm thuần:

~~~java
import java.time.Instant;

public enum ScheduledMailStatus {
    PENDING,
    RETRY,
    CLAIMED,
    PROCESSING,
    SUBMITTED,
    DELIVERED,
    BOUNCED,
    FAILED,
    CANCELLED,
    EXPIRED,
    UNKNOWN
}

public record MailDueSnapshot(
        ScheduledMailStatus status,
        Instant scheduledAt,
        Instant nextAttemptAt,
        Instant expiresAt) {
}

public final class MailDuePolicy {
    private MailDuePolicy() {
    }

    public static boolean isDue(
            MailDueSnapshot job, Instant now) {
        boolean eligibleStatus =
                job.status() == ScheduledMailStatus.PENDING
                || job.status() == ScheduledMailStatus.RETRY;

        return eligibleStatus
                && !job.scheduledAt().isAfter(now)
                && !job.nextAttemptAt().isAfter(now)
                && (job.expiresAt() == null
                    || now.isBefore(job.expiresAt()));
    }
}
~~~

JUnit 5 + AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class MailDuePolicyTest {
    private static final Instant NINE =
            Instant.parse("2026-11-16T09:00:00Z");

    @Test
    void doesNotSendBeforeScheduledInstant() {
        MailDueSnapshot job = new MailDueSnapshot(
                ScheduledMailStatus.PENDING,
                NINE, NINE, null);

        assertThat(MailDuePolicy.isDue(
                job, NINE.minusMillis(1))).isFalse();
        assertThat(MailDuePolicy.isDue(
                job, NINE)).isTrue();
    }

    @Test
    void retryMustWaitForNextAttemptAt() {
        MailDueSnapshot retry = new MailDueSnapshot(
                ScheduledMailStatus.RETRY,
                NINE,
                NINE.plusSeconds(300),
                null);

        assertThat(MailDuePolicy.isDue(
                retry, NINE.plusSeconds(60))).isFalse();
        assertThat(MailDuePolicy.isDue(
                retry, NINE.plusSeconds(300))).isTrue();
    }

    @Test
    void cancelledAndExpiredJobsNeverBecomeDue() {
        MailDueSnapshot cancelled = new MailDueSnapshot(
                ScheduledMailStatus.CANCELLED,
                NINE, NINE, null);
        MailDueSnapshot expired = new MailDueSnapshot(
                ScheduledMailStatus.PENDING,
                NINE, NINE, NINE.plusSeconds(120));

        assertThat(MailDuePolicy.isDue(
                cancelled, NINE.plusSeconds(1))).isFalse();
        assertThat(MailDuePolicy.isDue(
                expired, NINE.plusSeconds(120))).isFalse();
    }
}
~~~

Test thuần trên xác nhận **quy tắc thời gian trong Java**, không thay thế integration test của SQL `WHERE scheduled_at <= CURRENT_TIMESTAMP`, claim/lease hay việc provider thực sự gửi. Với SQL dùng đồng hồ database, cần một test integration có dữ liệu thời gian xác định và transaction isolation phù hợp.

## 34. Unit test: transition không hợp lệ phải bị từ chối

Trạng thái không nên thay đổi tùy ý:

~~~text
PENDING -> CANCELLED      hợp lệ
PENDING -> SUBMITTED      không hợp lệ nếu bỏ qua submission
SUBMITTED -> PENDING      không hợp lệ
CANCELLED -> PROCESSING   không hợp lệ
RETRY -> PROCESSING       hợp lệ nếu claim/ownership đúng
UNKNOWN -> RETRY          chỉ khi reconciliation/policy cho phép
~~~

Ví dụ một validator cho các transitions có chủ đích:

~~~java
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

public final class MailStatusTransitions {
    private static final Map<
            ScheduledMailStatus, Set<ScheduledMailStatus>> ALLOWED =
            Map.of(
                ScheduledMailStatus.PENDING,
                EnumSet.of(
                        ScheduledMailStatus.CLAIMED,
                        ScheduledMailStatus.CANCELLED,
                        ScheduledMailStatus.EXPIRED),
                ScheduledMailStatus.RETRY,
                EnumSet.of(
                        ScheduledMailStatus.CLAIMED,
                        ScheduledMailStatus.CANCELLED,
                        ScheduledMailStatus.EXPIRED),
                ScheduledMailStatus.CLAIMED,
                EnumSet.of(
                        ScheduledMailStatus.PROCESSING,
                        ScheduledMailStatus.PENDING,
                        ScheduledMailStatus.CANCELLED),
                ScheduledMailStatus.PROCESSING,
                EnumSet.of(
                        ScheduledMailStatus.SUBMITTED,
                        ScheduledMailStatus.RETRY,
                        ScheduledMailStatus.FAILED,
                        ScheduledMailStatus.UNKNOWN),
                ScheduledMailStatus.SUBMITTED,
                EnumSet.of(
                        ScheduledMailStatus.DELIVERED,
                        ScheduledMailStatus.BOUNCED)
            );

    private MailStatusTransitions() {
    }

    public static boolean mayTransition(
            ScheduledMailStatus from,
            ScheduledMailStatus to) {
        return ALLOWED.getOrDefault(
                from, Set.of()).contains(to);
    }
}
~~~

Đây là policy tối giản, không bao phủ tất cả workflows. Khi cần thêm `UNKNOWN` reconciliation, requeue dưới sự phê duyệt hoặc cập nhật trạng thái delivery phức tạp, hãy xây bảng transitions phù hợp; **không thêm một `else return true` cho các trạng thái lạ**.

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class MailStatusTransitionsTest {
    @Test
    void rejectsResendOfAlreadySubmittedJob() {
        assertThat(MailStatusTransitions.mayTransition(
                ScheduledMailStatus.SUBMITTED,
                ScheduledMailStatus.PENDING)).isFalse();
    }

    @Test
    void allowsCancellationWhileStillPending() {
        assertThat(MailStatusTransitions.mayTransition(
                ScheduledMailStatus.PENDING,
                ScheduledMailStatus.CANCELLED)).isTrue();
    }
}
~~~

**Quan trọng:** validator trong Java không tự khóa race ở database. Mỗi SQL update vẫn cần expected status/version/claim token. Test transitions nên đi kèm test repository chịu cạnh tranh.

## 35. Integration test: hai worker không claim cùng job

Một test quan trọng nhất của queue DB là chạy **hai transaction trên hai connection** đồng thời:

~~~text
Database has 1 due job J

Worker A starts claim TX
Worker B starts claim TX

Expected:
  Exactly one worker owns J
  Both cannot mark J as PROCESSING
~~~

Nếu dùng `FOR UPDATE SKIP LOCKED`:

- Đảm bảo hai connections/transactions thật sự chạy đồng thời, không dùng cùng một transaction test bao trùm cả hai.
- Dùng barrier như `CountDownLatch` để kiểm soát điểm bắt đầu.
- Kiểm tra claim token/version thuộc một worker.
- Kiểm tra worker không sở hữu không thể update bằng claim token sai.
- Rollback/commit đúng cách để không để test treo vì lock.

### Test crash windows

| Kịch bản | Điều kiện | Kỳ vọng |
|---|---|---|
| IT-01 | Job chưa đến hạn | Không claim, không gửi |
| IT-02 | Đến đúng scheduledAt | Có thể claim |
| IT-03 | Retry chưa tới nextAttemptAt | Không claim |
| IT-04 | Two workers race | Một owner cho một job |
| IT-05 | Worker crash sau claim, trước submit | Reclaim theo lease và policy |
| IT-06 | Worker crash sau attempt started | Không tự resend như outcome chắc chắn |
| IT-07 | SMTP accepted, DB update fail | UNKNOWN/reconciliation, không blind retry |
| IT-08 | User cancel trước claim | Không gọi SMTP |
| IT-09 | User cancel khi PROCESSING | Trả conflict/ghi outcome phù hợp |
| IT-10 | Reschedule với version cũ | Update bị từ chối |
| IT-11 | Provider quota deny | Defer, không tăng SMTP attempt |
| IT-12 | Permanent failure | FAILED, không retry vô hạn |
| IT-13 | Delayed delivery webhook | Không ghi lùi state SUBMITTED |
| IT-14 | Duplicate webhook | Không tạo double state event |
| IT-15 | DST overlap/gap | Xử lý theo timezone policy |
| IT-16 | Recurrence misfire | Catch-up/skip/coalesce đúng quy tắc |
| IT-17 | Job expiry trước retry | EXPIRED, không gửi |
| IT-18 | App restart với PENDING jobs | Job vẫn tồn tại trong DB |

Nên sử dụng SMTP sink/test double (như GreenMail hoặc Mailpit tùy luồng kiểm thử) thay vì gửi mail thật cho khách hàng. Nếu muốn mô phỏng *connection lost after DATA*, test double phải điều khiển đúng phase SMTP; một mock chỉ ném `RuntimeException` trước khi gọi send không mô tả được ambiguous outcome.

## 36. Quan sát tác động lịch gửi và trạng thái

Một dashboard không nên chỉ đếm số thư “đã gửi”. Các thước đo hữu ích:

| Metric | Mục đích |
|---|---|
| `mail_scheduled_pending` | Số job PENDING/RETRY chưa hoàn tất |
| `mail_due_backlog_count` | Số job đã đến hạn nhưng chưa claim |
| `mail_dispatch_lag_seconds` | `attempt_started_at - scheduled_at` |
| `mail_submission_lag_seconds` | `submitted_at - scheduled_at` |
| `mail_attempt_total` | Số lần thực sự gọi provider |
| `mail_retry_scheduled_total` | Số job chuyển sang retry |
| `mail_quota_defer_total` | Số lần defer do chưa có permit |
| `mail_claim_conflict_total` | Số lần claim token/status conflict |
| `mail_expired_total` | Số job quá hạn chưa gửi |
| `mail_cancelled_total` | Số job được hủy đúng policy |
| `mail_unknown_outcome_total` | Số attempt cần đối soát |
| `mail_oldest_due_age_seconds` | Tuổi của job đến hạn lâu nhất |
| `mail_delivery_event_total` | Delivery/bounce event nếu provider hỗ trợ |

Các label nên có cardinality thấp như `notification_type`, `provider_id`, `status`, `failure_kind`. Không dùng `mailJobId`, recipient email, subject hoặc raw error text làm metrics label; chúng có cardinality cao và có thể làm lộ dữ liệu.

### Đo backlog đúng thời điểm

Một job được đặt lịch cho tháng sau là PENDING nhưng **không phải due backlog** hôm nay. Dashboard nên phân biệt:

~~~text
scheduled future:
    scheduled_at > now

due pending:
    scheduled_at <= now
    next_attempt_at <= now
    status in PENDING/RETRY

waiting retry/quota:
    scheduled_at <= now
    next_attempt_at > now
~~~

Nếu chỉ đếm mọi PENDING rồi báo backlog tăng, hệ thống có thể báo động sai khi người dùng đặt nhiều lịch tương lai. Ngược lại, chỉ đếm due jobs có thể bỏ qua lượng retry bị trì hoãn rất lớn; nên có cả hai góc nhìn.

### Đặt SLA theo loại thông báo

Email OTP có thể có deadline ngắn, email báo cáo định kỳ có thể chịu trễ vài phút, campaign có thể gửi trong một cửa sổ dài. Cần đo theo **loại notification** và provider quota; không áp cùng một ngưỡng delay cho mọi job.

## 37. Log, tracing và dữ liệu riêng tư của mail job

Mail job thường chứa recipient, subject, payload và reference đến thông tin người dùng. Trạng thái và lịch gửi có thể được quan sát rộng hơn dữ liệu nghiệp vụ, nên **không dump cả entity**:

~~~java
// Không nên nếu toString() có recipient, body hoặc secret.
log.info("Scheduled email {}", job);

// Không nên: provider có thể echo email trong exception.
log.error("Mail submission failed", exception);
~~~

Nên log theo schema đã duyệt:

~~~text
event=scheduled_mail_transition
mailJobId=opaque-job-123
notificationType=ORDER_RECEIPT
fromStatus=PROCESSING
toStatus=RETRY
attempt=2
provider=PRIMARY_SMTP
reasonCode=SMTP_TEMPORARY_FAILURE
scheduleLagBucket=1m_5m
~~~

`mailJobId` nên là một ID opaque, không tạo bằng cách ghép email hoặc subject. Nếu cần tra người nhận thật, dùng trang hỗ trợ có authorization và audit, không đặt email ở mọi dòng log.

### Bảo vệ cả bảng status event

Một số event có thể nhạy cảm ngay cả khi không chứa email:

~~~text
notificationType=PASSWORD_RESET
occurredAt=...
tenant=...
~~~

Kết hợp thời gian và loại thông báo có thể tiết lộ hoạt động của người dùng. Nên giới hạn quyền đọc, retention và khả năng export bảng trạng thái/audit theo nguyên tắc least privilege.

### Không dùng raw exception message làm last_error_code

Provider có thể trả:

~~~text
550 5.1.1 <customer@example.test> rejected
~~~

Thay vì lưu nguyên văn, hãy phân loại:

~~~text
last_error_code=SMTP_PERMANENT_RECIPIENT_FAILURE
~~~

Nếu cần raw diagnostic trong một sự cố đặc biệt, lưu ở kênh có quyền riêng và thời hạn ngắn, không truyền qua log tập trung. Chỉ log mã lỗi an toàn và trạng thái job.

## 38. Phân quyền khi hẹn, sửa và hủy lịch

Một yêu cầu đổi `scheduled_at` không chỉ là update một timestamp:

- Người gọi có quyền quản lý notification của tenant này không?
- Họ được phép thay đổi schedule của loại thư đó không?
- Recipient và payload có còn hợp lệ với business event không?
- Job đã được claim, bắt đầu gửi, accepted hoặc cancelled chưa?
- Thay đổi lịch có vi phạm quiet hours, consent hoặc SLA không?
- Một job đã `SUBMITTED` có bị tạo lại trái phép do API retry không?

### Không dùng job ID dễ đoán để bỏ qua authorization

Ngay cả khi ID là UUID ngẫu nhiên, cần kiểm tra tenant/owner trong query:

~~~sql
UPDATE scheduled_mail
SET status = 'CANCELLED',
    cancelled_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :job_id
  AND tenant_id = :authorized_tenant_id
  AND status IN ('PENDING', 'RETRY')
  AND version = :expected_version
RETURNING id;
~~~

Khi không có row, phải trả kết quả theo authorization policy, không tiết lộ sự tồn tại của job thuộc tenant khác.

### Kiểm tra quyền tại thời điểm dispatch

Người dùng có thể unsubscribe sau khi job được tạo nhưng trước `scheduled_at`. Nếu nội dung thuộc loại phải tuân thủ opt-out, worker phải kiểm tra lại suppression list/consent trước submit. Không coi “đã được lên lịch” là quyền vĩnh viễn để gửi.

Với thông báo bảo mật/giao dịch, các ngoại lệ pháp lý/nghiệp vụ và phân loại consent khác nhau cần được xác định bởi sản phẩm; không tự gom mọi email vào một chính sách.

## 39. Retention, archival và bảo vệ nội dung

Bảng scheduled jobs, attempts, provider event và audit có thể tăng nhanh. Để vận hành lâu dài, xác định:

1. Active jobs được giữ bao lâu?
2. Terminal states `SUBMITTED/FAILED/CANCELLED/EXPIRED` cần giữ bao lâu để hỗ trợ khách hàng và audit?
3. Body HTML, attachment và recipient được giữ theo retention nào?
4. Khi xóa job, có cần giữ một audit record không chứa dữ liệu người nhận?
5. Backup/database replicas và object storage có cùng chính sách bảo vệ không?
6. Kết quả deletion có được thực hiện ở tất cả bản sao theo quy định không?

Không xóa PENDING/RETRY jobs chỉ vì `created_at` đã cũ; có thể đó là email đã được hẹn vào tương lai xa. Không archive một PROCESSING job đang giữ lease mà không hiểu trạng thái gửi.

### Trạng thái terminal và nội dung gốc có lifecycle khác nhau

Một email đã `SUBMITTED` có thể chỉ cần giữ metadata:

~~~text
mailJobId
notificationType
scheduledAt
submittedAt
status
providerRef
errorCode (nếu có)
~~~

trong khi raw MIME/attachment có thể được xóa sớm hơn theo chính sách. Nếu cần retry sau vài ngày, payload phải còn truy xuất được, có quyền đọc hợp lệ và version ổn định. Không để job RETRY trỏ tới file tạm đã bị xóa.

### Giữ snapshot hay render lại khi gửi?

Hai cách:

| Cách | Ưu điểm | Rủi ro |
|---|---|---|
| Snapshot content khi tạo job | Nội dung đúng phiên bản đã hẹn | Lưu thêm PII; cần encryption/retention |
| Lưu template ID + dữ liệu cần thiết, render lúc gửi | Ít lưu raw MIME, có thể lấy dữ liệu mới | Dữ liệu/template thay đổi khiến nội dung khác lúc đặt lịch |

Nên định nghĩa **content versioning** và trường hợp dữ liệu nghiệp vụ thay đổi/hết hiệu lực. Ví dụ hóa đơn đã phát hành có thể cần snapshot bất biến; thông báo nhắc nhở lịch hẹn có thể cần đọc lại thời gian hẹn mới nhất. Không có một chiến lược đúng cho mọi loại email.

## 40. Runbook: email đến giờ nhưng chưa gửi

Giả sử khách hàng hỏi vì sao một email hẹn 09:00 vẫn chưa tới lúc 09:20. Chẩn đoán theo thứ tự:

~~~mermaid
flowchart TD
    A[Mail job chưa tới người nhận] --> B{Có job trong database?}
    B -- Không --> C[Kiểm tra transaction tạo intent / idempotency]
    B -- Có --> D{scheduledAt và nextAttemptAt đã tới giờ?}
    D -- Không --> E[Kiểm tra timezone / lịch bị đổi / backoff]
    D -- Có --> F{status là gì?}
    F -- PENDING/RETRY --> G[Kiểm tra claim, index, poller, quota]
    F -- CLAIMED/PROCESSING --> H[Kiểm tra lease, attempt, provider outcome]
    F -- SUBMITTED --> I[Kiểm tra delivery/bounce tại provider]
    F -- UNKNOWN --> J[Reconcile, không resend mù]
    F -- CANCELLED/EXPIRED/FAILED --> K[Kiểm tra transition history và policy]
~~~

### Bước 1: xác định lịch và timezone

Truy vấn:

~~~sql
SELECT
    id, status, scheduled_at, next_attempt_at,
    expires_at, attempt_count,
    claimed_at, lease_until,
    submitted_at, updated_at, last_error_code
FROM scheduled_mail
WHERE id = :job_id;
~~~

Kiểm tra client chọn giờ với timezone/offset nào, có đổi lịch hay không, và `next_attempt_at` có đang phản ánh một retry/quota deferral.

### Bước 2: nếu đã due mà vẫn PENDING

- Scheduler có đang chạy trên ít nhất một instance không?
- Query có lọc status/due time đúng không?
- Có quota/capacity không? Job có bị `next_attempt_at` lùi?
- DB connection pool có bị cạn?
- Index/query có chậm do backlog lớn không?
- Một tenant/lane khác có chiếm toàn bộ executor không?
- Có quá nhiều job bị claim trong RAM khiến lease sắp hết không?

### Bước 3: nếu CLAIMED/PROCESSING lâu

- Lease còn hay đã hết?
- Worker có đang gửi SMTP thật hay bị treo trong I/O?
- Có timeout cấu hình cho connect/read/write của SMTP transport không?
- Có log attempt started và provider accepted không?
- Worker có thể đã crash sau khi provider accepted không?
- Nếu lease expiry, recovery có phân biệt claim chưa gửi với attempt đã bắt đầu không?

Đừng reset hàng loạt `PROCESSING -> PENDING` để “gỡ kẹt” nếu có khả năng những job đó đã được accepted; có thể gây email trùng.

### Bước 4: nếu SUBMITTED nhưng người nhận chưa thấy

- Kiểm tra provider message trace/accepted ID nếu có.
- Xem delivery, bounce, spam classification hoặc mailbox filters.
- Nhớ rằng `submitted_at` là mốc nộp thành công, không phải inbox delivery.
- Không tự gửi lại qua provider khác chỉ vì chưa có `delivered_at`.

### Bước 5: khi sự cố kéo dài

Giới hạn traffic không quan trọng, bảo vệ deadline của OTP/transactional, ghi nhận backlog age và kích hoạt incident procedure. Chỉ dùng thao tác manual replay khi biết rõ trạng thái/outcome và quyền vận hành.

## 41. Những lỗi thiết kế thường gặp

### 41.1. Chỉ dùng ScheduledExecutorService/Thread.sleep

Nếu lịch chỉ ở RAM, restart làm mất job. Với yêu cầu nghiệp vụ cần bền vững, lưu scheduled_at và status trong database/outbox.

### 41.2. Chỉ lưu status, không lưu scheduled_at

Một job `PENDING` không cho biết được gửi khi nào, liệu đã trễ SLA hay chưa. Cần mốc thời gian có ngữ nghĩa rõ.

### 41.3. Chỉ lưu scheduled_at, không lưu status

Worker không biết job đã gửi, hủy hay retry. Nó có thể gửi cùng email ở mỗi lần poll.

### 41.4. Ghi đè scheduled_at bằng next retry time

Làm mất lịch ban đầu; dashboard không còn đo được độ trễ của provider và lịch nghiệp vụ. Giữ `scheduled_at` riêng với `next_attempt_at`.

### 41.5. Gán sentAt ngay trước khi gọi send

~~~java
job.setSubmittedAt(clock.instant());
mailSender.send(message);
~~~

Nếu SMTP thất bại, database có thể hiện “đã gửi” dù chưa accepted. Chỉ ghi `submitted_at` sau khi có kết quả submission success; với lỗi không rõ, dùng `UNKNOWN`.

### 41.6. Gán deliveredAt khi JavaMailSender không ném exception

`send(...)` trả thành công không đồng nghĩa thư đã được giao vào inbox. Delivery confirmation cần nguồn khác.

### 41.7. Dùng @Scheduled mà không có claim/lease

Nhiều Spring Boot pods có thể cùng lấy một job và gửi trùng. Dùng atomic claim, ownership/fencing và idempotency.

### 41.8. Chỉ SELECT rồi UPDATE

Hai worker cùng SELECT PENDING trước khi update. Cần transaction/lock/conditional update để đảm bảo chỉ một worker claim.

### 41.9. Giữ transaction DB mở qua SMTP call

Kết nối mạng chậm khiến DB row lock/connection bị giữ lâu, tăng contention và timeout. Tách transaction ngắn ở claim và commit outcome.

### 41.10. Khi lease hết hạn thì gửi lại mọi PROCESSING

Nếu server đã accepted trước khi worker crash, retry gây duplicate. Phân biệt chưa submit với outcome unknown.

### 41.11. Dùng Message-ID như khóa exactly-once

Message-ID là header/correlation, không phải idempotency guarantee của SMTP hoặc người nhận. Không dựa hoàn toàn vào nó để tránh email trùng.

### 41.12. Tăng attempt_count khi rate limiter từ chối

Chưa có SMTP request mà đếm thành retry thực tế có thể khiến job bị max attempts quá sớm. Tách defer vì quota khỏi SMTP attempt.

### 41.13. Đổi lịch bằng SQL UPDATE không kiểm tra trạng thái

Một job `SUBMITTED` hoặc `CANCELLED` có thể bị hồi sinh bởi request cũ. Kiểm tra status/version và quyền ở mỗi transition.

### 41.14. Hủy thành công khi email đã PROCESSING

Hủy database record không thể thu hồi network submission đã bắt đầu. API nên trả conflict hoặc trạng thái không thể bảo đảm hủy, tùy workflow.

### 41.15. Dùng LocalDateTime không có timezone cho thời điểm tuyệt đối

Đặc biệt nguy hiểm khi người dùng khác múi giờ hoặc triển khai ở region khác. Chuyển thành `Instant`, lưu timezone riêng cho recurring rules.

### 41.16. Coi cron tick là durable mail job

Một tick bị bỏ lỡ khi app tắt có thể không có record để xử lý lại. Lưu occurrence job riêng và xác định misfire policy.

### 41.17. Lặp lại business create không có idempotency key

Request timeout khiến client retry và tạo hai job. Cần business idempotency key với unique constraint; không giải quyết bằng cách chỉ query “có email cùng subject không?”.

### 41.18. Claim quá nhiều job vượt năng lực SMTP

Job hết lease khi còn nằm trong executor queue; worker khác claim lại. Claim batch theo tốc độ thật, bounded queue và backpressure.

### 41.19. Không lưu lịch sử trạng thái

Một status `FAILED` không cho biết trước đó retry bao nhiêu lần và lúc nào. Event/attempt log có kiểm soát hỗ trợ chẩn đoán.

### 41.20. Coi submitted/delivered là một trạng thái

Không thể phân biệt lỗi submission với bounce xảy ra sau khi provider accepted. Tách mốc và nguồn evidence.

### 41.21. Coi mọi SMTP exception là temporary

Auth failure hoặc invalid sender không thể sửa bằng retry vô hạn. Cần classifier theo response/phase và chính sách khác nhau.

### 41.22. Không kiểm tra consent khi đến giờ gửi

Một email lên lịch tuần trước có thể không còn hợp lệ hôm nay. Revalidate suppression/eligibility trước submit.

### 41.23. Xóa payload khi job chưa terminal

Worker retry sau vài giờ không còn nội dung/attachment cần thiết. Phải thống nhất retention giữa mail job và payload storage.

### 41.24. Đưa email/subject vào metric labels

Tạo cardinality cao và lộ dữ liệu. Dùng notification type, provider và status là label thuộc tập giá trị kiểm soát; tra recipient qua hệ nghiệp vụ có quyền.

## 42. Câu hỏi thường gặp

**Có cần database để hẹn gửi mail không?** Với email có thể bỏ khi process restart, timer trong RAM có thể đủ; với email nghiệp vụ cần tin cậy, nên lưu intent/trạng thái bền vững bằng database, outbox hoặc scheduler store phù hợp.

**Spring Mail có API `sendAt` không?** `JavaMailSender` phục vụ tạo và submit SMTP message; việc lập lịch bền vững và trạng thái job cần được ứng dụng hoặc hệ thống scheduling khác quản lý.

**Nên lưu thời gian bằng kiểu gì?** Một lần gửi cụ thể dùng `Instant` trong Java, `TIMESTAMPTZ` trong PostgreSQL. Với recurrence cần thêm `ZoneId` và quy tắc xử lý DST.

**scheduled_at khác next_attempt_at như thế nào?** `scheduled_at` là thời điểm mong muốn theo nghiệp vụ. `next_attempt_at` là thời điểm sớm nhất worker được thử tiếp, có thể dời do retry/quota.

**Nếu scheduled_at ở tương lai thì status là gì?** Thường `PENDING`; worker chỉ claim khi `scheduled_at` và `next_attempt_at` cùng tới hạn.

**Nếu người dùng đặt lịch rồi đổi giờ?** Cập nhật `scheduled_at` và `next_attempt_at` bằng optimistic concurrency/điều kiện status. Không cho request cũ ghi đè job đã bắt đầu gửi.

**Khi nào status trở thành SUBMITTED?** Sau khi SMTP/API trả kết quả accepted theo adapter. Đây không phải bằng chứng delivery tới hộp thư người nhận.

**Có nên đặt sent_at hay submitted_at?** Có thể dùng `sent_at` nếu định nghĩa rõ, nhưng `submitted_at` thường diễn đạt đúng việc provider accepted hơn. Không dùng tên biến mơ hồ rồi suy luận đó là delivered.

**Có thể dùng một cột status cho toàn bộ delivery lifecycle không?** Với workflow đơn giản có thể. Với nhiều recipients, bounce/deferred/provider events, nên cân nhắc bảng attempts/delivery riêng.

**Có cần update status cùng timestamp trong một transaction không?** Có. Nếu trạng thái và timestamp được ghi ở hai transaction không liên quan, sự cố có thể tạo record `SUBMITTED` mà `submitted_at` vẫn null, hoặc ngược lại.

**@Scheduled có tự giữ lịch qua restart không?** Không đối với từng task runtime đã đăng ký. Khi dùng `@Scheduled` để poll DB, job vẫn ở DB và được đọc lại sau restart.

**Quartz có thay thế bảng scheduled_mail không?** Quartz có thể lưu trigger/calendar và phát event theo lịch, nhưng mail business state, attempt history, idempotency và delivery tracking vẫn cần mô hình phù hợp.

**Có thể có nhiều dispatcher không?** Có, nếu claim atomic, lease và checkpoint state đúng; `@Scheduled` trên nhiều pods không tự loại trừ nhau.

**SKIP LOCKED có bảo đảm exactly-once email delivery?** Không. Nó tránh hai worker claim đồng thời trong transaction, không làm SMTP và DB cập nhật nguyên tử.

**Lease expired có nghĩa job chắc chắn chưa gửi?** Không. Worker có thể đã gọi SMTP rồi crash trước commit. Cần nhận biết attempt started và trạng thái unknown.

**Tại sao có status UNKNOWN?** Khi không thể xác định provider đã accepted hay chưa, ví dụ connection mất sau DATA. Retry ngay có thể gây trùng email.

**Làm sao ngăn người dùng hủy sau khi đã gửi?** Kiểm tra state/ownership atomically. Khi job đã PROCESSING/SUBMITTED, API phải nói rõ không thể bảo đảm thu hồi việc gửi.

**Khi quota hết, có nên tăng attempt_count không?** Không nếu chưa gọi SMTP. Cập nhật defer reason và `next_attempt_at`, giữ scheduled_at.

**Nếu job tới giờ nhưng worker chậm, có mất mail không?** Không nếu job được lưu bền vững và chưa hết hạn/không bị xóa. Nhưng sẽ có dispatch lag; cần giám sát và capacity planning.

**Có nên giữ tất cả job SUBMITTED mãi không?** Không mặc định. Xác định retention/audit, dọn payload nhạy cảm theo chính sách; bảo đảm không dọn job chưa terminal.

**Một email có nhiều người nhận thì status tính thế nào?** Cần xác định status là cấp message hay recipient. Nếu cần delivery riêng từng người, lưu recipient-level status/attempt events.

**Có thể dùng Message-ID để deduplicate retries không?** Chỉ dùng làm tín hiệu correlation; không phải bảo đảm provider hoặc receiver sẽ chỉ giao một email.

**Đồng hồ ứng dụng và DB khác nhau thì sao?** Due/lease comparisons có thể lệch. Đồng bộ clock và chọn nguồn thời gian nhất quán, ưu tiên DB time cho atomic DB claim.

**Có nên lưu cron expression trong mọi mail job?** Mail job một lần chỉ cần instant. Lịch lặp lại nên có recurring schedule riêng, từ đó tạo những occurrence jobs cụ thể.

**Nếu cron bị lỡ khi ứng dụng tắt, có tự gửi bù không?** Phụ thuộc misfire policy: catch up, skip, coalesce hoặc manual review; cần được thiết kế và lưu rõ.

**Nếu không nhận được delivery webhook thì sao?** Có thể giữ `SUBMITTED` với `delivered_at = null`, hoặc trạng thái delivery `UNKNOWN/NOT_TRACKED` tùy mô hình. Không tự gán delivered khi SMTP success.

**Có nên dùng Redis thay database làm lịch gửi?** Redis/delayed queue có thể là một thành phần, nhưng phải xem durability, restart recovery, cancellation, dedup và business transaction. Nếu dữ liệu nghiệp vụ nằm trong SQL, outbox cùng database có lợi thế nhất quán.

**Có cần test SMTP production để kiểm tra scheduling không?** Không. Unit test bằng fixed clock/mock sender, integration test với PostgreSQL và SMTP sink/test server. Production chỉ dùng rollout quan sát có kiểm soát.

## 43. Tổng kết

**“Lưu thời điểm gửi cùng trạng thái message”** là nền tảng để biến một lệnh gửi email thành một quy trình **đặt lịch, retry, hủy và quan sát được** trong Spring Framework Mail.

Hệ thống nên phân biệt:

~~~text
scheduledAt    -> người dùng/nghiệp vụ muốn gửi khi nào
nextAttemptAt  -> worker có thể thử gửi sớm nhất khi nào
status         -> job đang ở bước nào
attemptCount   -> số lần thực sự thử submit
claimedAt      -> worker nào đang sở hữu, từ khi nào
leaseUntil     -> thời điểm quyền xử lý hết hạn
submittedAt    -> provider đã accepted lúc nào
deliveredAt    -> xác nhận delivery lúc nào, nếu có
expiresAt      -> sau lúc nào không được gửi nữa
~~~

Một luồng hoạt động đáng tin:

~~~text
Business transaction
      |
      v
INSERT scheduled_mail:
  scheduled_at + next_attempt_at + PENDING
      |
      v
Database commit
      |
      v
@Scheduled polls due rows
      |
      v
Atomic claim + lease
      |
      v
Revalidate eligibility + quota
      |
      v
Record submission attempt
      |
      v
JavaMailSender.send(...)
      |
      +-- Accepted -> SUBMITTED + submitted_at
      +-- Temporary -> RETRY + next_attempt_at
      +-- Permanent -> FAILED + last_error_code
      +-- Uncertain -> UNKNOWN + reconciliation
      |
      v
Provider delivery events (nếu có)
      |
      v
DELIVERED / BOUNCED + timestamps
~~~

Những nguyên tắc quan trọng:

1. **Lưu lịch gửi và trạng thái trong một hệ dữ liệu bền vững**, cập nhật có transaction và điều kiện transition rõ ràng.
2. **Không trộn lịch ban đầu với lịch thử lại**; giữ `scheduled_at` và `next_attempt_at` riêng.
3. **Không dùng `submitted_at` để khẳng định inbox delivery**; phân biệt submission và delivery.
4. **Claim an toàn khi có nhiều worker**, nhưng hiểu rằng lease/fencing không tự tạo exactly-once SMTP.
5. **Hủy, đổi lịch và retry có kiểm soát concurrency**, không cho job terminal tự hồi sinh.
6. **Dùng Instant/UTC cho thời điểm tuyệt đối, ZoneId cho recurrence**, có quy tắc DST và misfire.
7. **Theo dõi backlog, dispatch lag, attempts, unknown outcomes và status history**, không chỉ số thư gửi thành công.

Khi mô hình thời gian và trạng thái được định nghĩa từ đầu, ứng dụng có thể phục hồi sau restart, điều phối gửi theo quota, giải thích vì sao một email bị trễ và xử lý yêu cầu hỗ trợ mà không phải phỏng đoán “email đã gửi hay chưa”. Đồng thời, những giới hạn vốn có của SMTP vẫn được phản ánh trung thực: **đã gửi tới provider** không đồng nghĩa **đã giao tới người nhận**, và retry không phải lúc nào cũng an toàn nếu kết quả submission chưa rõ.
