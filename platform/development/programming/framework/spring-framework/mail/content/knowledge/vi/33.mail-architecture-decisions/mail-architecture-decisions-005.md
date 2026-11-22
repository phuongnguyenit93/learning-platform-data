# Chọn retry trong ứng dụng hay trong nền tảng gửi

Trong Spring Framework Mail, một câu hỏi kiến trúc xuất hiện rất sớm khi xây hệ thống production: **khi gửi email thất bại, nên để ứng dụng tự retry hay để SMTP relay/Email Service Provider (ESP) xử lý?** Câu trả lời không phải “luôn dùng Spring Retry” hoặc “phó mặc toàn bộ cho provider”. Hai bên kiểm soát **những giai đoạn khác nhau** của vòng đời email, vì vậy trách nhiệm retry phải được phân chia theo **ranh giới chấp nhận thông điệp**, loại lỗi, yêu cầu nghiệp vụ và bằng chứng quan sát được.

Một ứng dụng dùng `JavaMailSender` có thể submit thông điệp tới SMTP submission server. Sau khi relay đã chấp nhận thông điệp, server còn phải tìm và giao thư tới hệ thống nhận; trong quá trình này, remote mailbox có thể trả lỗi tạm thời, greylisting, timeout hoặc deferred delivery. Nền tảng gửi thường có hàng đợi và chính sách retry của riêng nó. Nếu ứng dụng vẫn tự gửi lại cùng thông điệp chỉ vì chưa nhìn thấy delivery event, người nhận có thể nhận **nhiều bản email**.

Ngược lại, nếu kết nối từ ứng dụng tới SMTP relay bị từ chối **trước khi thông điệp được chấp nhận**, nền tảng chưa chắc đã có việc gì để retry. Khi đó ứng dụng có thể cần lưu ý định gửi bền vững và thực hiện retry có kiểm soát.

Bài học giải thích cách chọn vị trí retry, cơ chế phối hợp hai tầng, các tình huống SMTP/API thông dụng, cách thiết kế transactional outbox, idempotency, timeout/AMBIGUOUS, webhook/status reconciliation, ví dụ Spring và những quyết định vận hành nên ghi thành ADR (*Architecture Decision Record*). Các mô hình dữ liệu/enum trong ví dụ là thiết kế ứng dụng, không phải tính năng outbox/retry tự động có sẵn trong Spring Framework Mail.

## 1. Phải phân biệt các giai đoạn của email

Một email đi qua nhiều mốc trạng thái:

```text
Business event
      |
      v
APPLICATION REQUEST CREATED
      |
      v
Stored in local outbox / broker
      |
      v
Attempt to submit via SMTP or provider API
      |
      +--> Rejected / timeout / accepted?
      |
      v
PROVIDER ACCEPTED / QUEUED
      |
      v
Provider retries downstream delivery
      |
      +--> Deferred: recipient server says try later
      +--> Bounced: permanent or exhausted failure
      |
      v
DELIVERED (according to provider event)
      |
      v
Opened / clicked / read? (separate, imperfect signals)
```

Bốn mốc rất dễ bị nhầm:

1. **Created**: ứng dụng đã tạo ý định gửi.
2. **Submitted/accepted**: SMTP relay hoặc provider API đã xác nhận tiếp nhận để xử lý.
3. **Delivered**: có bằng chứng giao tới hệ thống nhận theo định nghĩa provider.
4. **Opened/read**: người dùng tương tác; đây không phải kết quả retry transport.

Một lời gọi `JavaMailSender.send(...)` kết thúc bình thường thường phản ánh việc submission hiện tại hoàn tất theo giao thức SMTP. **Nó không bảo đảm thư vào Inbox, không chứng minh người nhận đã đọc và không tự cung cấp trạng thái delivery.**

## 2. Retry trong ứng dụng và retry trong nền tảng gửi xử lý hai việc khác nhau

```text
                    APPLICATION
                        |
                Durable mail outbox
                        |
                 APP-LEVEL RETRY
               (pre-acceptance / intent)
                        |
                        v
                SMTP / Provider API
                        |
                  ACCEPTED/QUEUED
                        |
                 PLATFORM RETRY
               (downstream delivery)
                        |
                        v
                Recipient mail system
```

**Ứng dụng** thường có quyền quyết định:

- Có nên tạo email này không?
- Recipient đã được xác thực và đồng ý nhận chưa?
- Email có hết hạn hay bị hủy không?
- Khi submit thất bại trước acceptance, khi nào thử lại?
- Đã vượt số attempts và deadline chưa?
- Cần dùng provider/account nào?
- Có được gửi lại vì người dùng chủ động yêu cầu không?

**Nền tảng gửi** thường có quyền quyết định:

- Queue thông điệp đã được chấp nhận.
- Khi remote MX trả 4xx, defer bao lâu?
- Retry kết nối tới recipient domains thế nào?
- Phân bổ rate/connection theo miền nhận.
- Xử lý bounce, deferral, complaint, delivery notifications.
- Sau thời gian retry, khi nào coi delivery là failed?

Không nên tạo một scheduler của ứng dụng cứ gửi lại email sau mỗi 5 phút khi provider đã trả `250 OK` và đang tự thử giao thư.

## 3. “Nền tảng gửi” có thể là những hệ thống rất khác nhau

| Loại nền tảng | Ví dụ khái niệm | Khả năng thường gặp |
| --- | --- | --- |
| SMTP relay/SMTP submission service | Máy chủ SMTP chuyên trách hoặc dịch vụ SMTP hosted | Queue accepted mail; retry downstream |
| Email Service Provider qua HTTP API | Dịch vụ gửi transactional/bulk mail | Request acceptance, queue, events, suppression, retry policy |
| Self-hosted MTA | Postfix/Exim hoặc hệ thống tương tự | Quản lý queue và retry tới recipient MX |
| Local development mail catcher | GreenMail/Mailpit | Chủ yếu capture/test, không đại diện đầy đủ production delivery |
| Mail SDK/library | Jakarta Mail client, REST SDK | Có thể retry kết nối/request ở client; không nhất thiết có durable queue |
| Message broker nội bộ | RabbitMQ/Kafka/SQS hoặc công nghệ khác | Lưu yêu cầu nội bộ; không tự giao mail tới recipient |

Cùng tên “retry của provider” đôi khi chỉ **retry HTTP request trong SDK**, đôi khi là **retry giao thư sau khi provider đã nhận**. Hai chức năng đó khác hoàn toàn. Phải đọc hợp đồng API/SMTP và tài liệu cụ thể của nhà cung cấp.

**Không giả định mọi SMTP server đều có hàng đợi bền vững giống nhau**, mọi provider đều hỗ trợ webhook, hoặc SDK nào cũng có idempotency key.

## 4. Ranh giới quan trọng nhất: provider đã accepted chưa?

Một phép phân nhánh:

```text
Application attempts submission
              |
              v
Did provider definitively accept?
              |
        +-----+------+
        |            |
       YES           NO
        |            |
        v            v
Do not submit       Was rejection definitely
same logical mail   pre-acceptance?
again merely              |
because delivery     +----+-----+
is pending.          |          |
                     YES       UNKNOWN
                      |          |
                      v          v
                 App retry   AMBIGUOUS:
                 if policy   reconcile before retry
                 permits
```

**YES:** nếu relay trả mã thành công cho SMTP message submission hoặc provider API trả receipt thể hiện đã queue thành công, ứng dụng nên ghi `SUBMITTED`/`PROVIDER_ACCEPTED`. Từ đó việc delivery retry thường thuộc provider. Ứng dụng theo dõi events, không tự tạo một submission thứ hai do chưa thấy `DELIVERED`.

**NO, chắc chắn trước acceptance:** ví dụ TCP connection không mở được hoặc SMTP server từ chối submission mà chưa nhận message. Ứng dụng có thể retry theo backoff và deadline.

**UNKNOWN:** timeout đúng thời điểm final reply, HTTP response bị mất hoặc client crash sau khi provider có thể đã nhận. Đây là outcome `AMBIGUOUS`. Blind retry có thể gây duplicate, dù application DB ghi `FAILED`.

## 5. SMTP có nhiều thời điểm thất bại

Một phiên SMTP điển hình:

```text
Connect
  |
  v
Greeting / EHLO
  |
  v
STARTTLS / AUTH
  |
  v
MAIL FROM
  |
  v
RCPT TO (one or more)
  |
  v
DATA
  |
  v
message bytes + DATA terminator
  |
  v
final SMTP response
```

Các thời điểm có ý nghĩa khác nhau:

- **Connection failure trước greeting:** relay chưa biết message; thường an toàn hơn để ứng dụng retry.
- **AUTH/TLS failure:** phải phân loại lỗi cấu hình/permanent hoặc transient; retry nóng không giúp nếu credential sai.
- **MAIL FROM/RCPT TO rejection:** có thể chưa có accepted message hoàn chỉnh; nhưng phải chú ý multi-recipient partial acceptance.
- **DATA rejected với response xác định:** không được giả định message đã queued khi relay báo không nhận; xử lý theo status.
- **Final response 2xx sau DATA:** relay xác nhận acceptance; downstream delivery là trách nhiệm sau đó.
- **Timeout/mất response sau DATA:** relay có thể đã queue, client không biết; outcome ambiguous.

Chỉ dựa vào lớp exception `MailException` đôi khi không đủ để phân biệt mọi giai đoạn. Cần context được instrumentation theo hợp đồng thư viện, provider receipt hoặc nguồn bằng chứng khác.

## 6. SMTP 4xx và 5xx phải được hiểu theo giai đoạn

Một nguyên tắc giao thức thường gặp:

| SMTP reply | Ý nghĩa tổng quát | Hướng xử lý |
| --- | --- | --- |
| 2xx | Thành công ở lệnh/giai đoạn hiện tại | Xác định lệnh nào vừa hoàn tất |
| 4xx | Temporary negative completion | Có thể retry theo policy |
| 5xx | Permanent negative completion | Không retry nguyên nhân không thay đổi |
| Không nhận response | Chưa đủ bằng chứng | Xem giai đoạn, có thể AMBIGUOUS |

**Cùng là 4xx, nhưng bên nào retry phụ thuộc vị trí lỗi.**

- Relay ứng dụng đang kết nối trả `451` **trước acceptance**: ứng dụng có thể cần retry submission.
- Relay **đã accepted** rồi recipient MX trả 451 sau đó: provider thường sẽ tự retry delivery; ứng dụng không gửi lại.
- Provider API trả HTTP 429 trước khi nhận job: ứng dụng chờ theo `Retry-After`/cooldown và retry request.
- Provider đã queue job rồi báo `DEFERRED`: không gửi lại từ ứng dụng nếu provider đang xử lý delivery retry.

Không dùng một quy tắc “thấy bất kỳ 4xx ở đâu cũng gọi lại `JavaMailSender`”.

## 7. Mã HTTP API cũng cần phân loại acceptance

Nếu dùng ESP qua HTTP API thay cho SMTP:

| HTTP/API outcome | Có thể hiểu | Trách nhiệm cần xem |
| --- | --- | --- |
| 2xx có receipt accepted/queued | Provider đã nhận intent | Theo dõi provider status |
| 400/422 validation | Payload sai | Sửa payload; không retry nguyên yêu cầu |
| 401/403 | Authentication/authorization | Kiểm tra cấu hình và quyền; không retry nóng |
| 429 | Rate limit | Tôn trọng `Retry-After`, backoff, quota |
| 503/5xx | Provider tạm lỗi hoặc trạng thái không rõ | Xem hợp đồng response/idempotency |
| Client read timeout | Không biết provider có queue hay chưa | AMBIGUOUS và reconcile |
| Connection failure trước khi gửi request | Có thể chưa tới provider | Retry nếu được phân loại an toàn |

Không giả định “HTTP 500 luôn có nghĩa provider không nhận request”. Một hệ thống có thể commit queue rồi lỗi khi trả response, hoặc response bị mất trên đường về.

Nếu provider hỗ trợ **idempotency keys được định nghĩa rõ**, ứng dụng nên dùng cùng key cho các lần gửi lại cùng một logical intent. Nhưng phải hiểu scope, TTL và semantics của feature; không giả định tất cả ESP đều làm như nhau.

## 8. Vì sao không nên tự retry khi provider đang delivery retry?

Giả sử:

```text
T=00:00 Application submits N-1001.
T=00:01 Provider returns ACCEPTED.
T=00:02 Recipient MX returns temporary 451.
T=00:02 Provider schedules its own delivery retry.
T=00:05 Application sees not yet DELIVERED.
T=00:05 Application resubmits N-1001.
T=00:06 Provider now has TWO accepted copies.
T=00:12 Recipient MX recovers.
T=00:12 Both copies may be delivered.
```

Số lần người nhận nhận mail có thể nhiều hơn một dù application nghĩ đang thực hiện “recovery”. `Message-ID` không phải cam kết deduplication ở recipient MX.

Với transactional email, duplicate có thể gây confusion; với OTP, reset link, financial documents hoặc password-related flows, tác động có thể lớn hơn.

**Chờ provider delivery event không phải một timeout để ứng dụng tự resend mặc định.** Đó là trạng thái theo dõi, có thể có cảnh báo và escalation riêng.

## 9. Khi nào ứng dụng nên chịu trách nhiệm retry?

Ứng dụng nên có retry owner khi:

1. Submission tới SMTP relay/API **chưa được xác nhận** và có bằng chứng lỗi transient trước acceptance.
2. Mail intent được tạo trong business transaction và cần sống qua process restart.
3. Job phải chờ network/provider hoạt động trở lại.
4. Có template/content preparation tạm lỗi trước khi submit.
5. Provider API rate limit/cooldown yêu cầu chờ.
6. Có business deadline/expiry cần kiểm tra trước mỗi attempt.
7. Cần chọn lại provider/account khi provider chính không khả dụng.
8. Cần xử lý sự cố service-to-service, DNS, connect, TLS theo policy.
9. Một SDK tự retry trong memory không đáp ứng durability của nghiệp vụ.

**Điều kiện đi kèm:** ứng dụng phải quản lý idempotency, trạng thái bền vững, retry budget, backoff/jitter, scheduler/worker, metrics và outcome ambiguity. Retry trong ứng dụng không chỉ là thêm `for` loop.

## 10. Khi nào nên để nền tảng gửi retry?

Nên giao cho nền tảng khi:

- Provider **đã accepted và queued** thông điệp.
- Remote recipient MX tạm unavailable/greylisting/throttling.
- Cần delivery pacing theo domain, DNS/MX resolution và server backoff.
- Provider có hệ thống queue/retry được vận hành và giám sát tốt.
- Provider cung cấp delivery/deferred/bounced events.
- Application không có quyền truy cập hay hiểu biết chi tiết remote delivery.
- Delivery retry policy của provider đáp ứng SLA hoặc business expectations.

Lúc đó ứng dụng nên lưu receipt/correlation, theo dõi trạng thái và phản ứng với final bounce/complaint/expiry, **không xây thêm một vòng retry SMTP riêng vì chưa delivered**.

Một số nền tảng cho phép điều chỉnh retry window hoặc queue TTL; ứng dụng cần xác nhận thời gian tối đa provider giữ job khi chọn chính sách business deadline.

## 11. Hai tầng retry không loại trừ nhau

Kiến trúc phổ biến và hợp lý:

```text
Application DB outbox
      |
      +--> retries BEFORE provider acceptance
      |
      v
SMTP submission / Provider API
      |
      +--> acceptance confirmed
      |
      v
Provider queue
      |
      +--> retries AFTER acceptance
      |
      v
Recipient MX / mailbox
```

Đây không phải hai đội cùng xử lý một lỗi. Chúng xử lý **hai tập trạng thái khác nhau**.

Ứng dụng đảm bảo intent được submit hoặc kết thúc bằng lỗi/kết luận phù hợp. Provider đảm bảo nỗ lực delivery theo chính sách của họ sau khi nhận.

**Không cho phép hai bộ retry cùng nhìn một notification ở trạng thái chung `FAILED` thiếu giai đoạn và tự động gọi lại SMTP.**

## 12. Tách ba state machines để tránh nhầm lẫn

Một model có thể chia:

**Intent state:**

```text
CREATED -> READY -> PROCESSING
                -> CANCELLED / EXPIRED
```

**Submission state:**

```text
NOT_ATTEMPTED
     |
     v
SUBMITTING
     |
     +--> ACCEPTED
     +--> RETRY_WAIT
     +--> FAILED_PERMANENT
     +--> AMBIGUOUS
```

**Delivery state:**

```text
UNKNOWN / QUEUED
     |
     +--> DEFERRED
     +--> DELIVERED
     +--> BOUNCED
     +--> COMPLAINED
```

Có thể lưu trong một bảng hoặc nhiều bảng; điều cốt lõi là **không gộp `SUBMITTED` với `DELIVERED`**.

Một worker có thể hoàn tất submission trong khi delivery status vẫn `QUEUED`. Không để poller query `delivery_status != DELIVERED` rồi gửi lại tất cả.

## 13. Ma trận trách nhiệm theo sự cố

| Sự cố | Provider đã accepted? | Retry owner mặc định | Ghi chú |
| --- | --- | --- | --- |
| Business transaction rollback | Chưa có valid intent | Không gửi | Không tạo email sai |
| Template render lỗi transient | Chưa submit | Application | Retry preparation riêng |
| SMTP connect refused | Không | Application | Backoff/circuit breaker |
| SMTP credentials sai | Không | Configuration/operator | Không retry nóng |
| SMTP 421 trước DATA acceptance | Không xác nhận | Application | Theo phase và policy |
| SMTP final 250 sau DATA | Có | Provider cho downstream | Application chỉ track |
| Mất final response sau DATA | Không rõ | Reconciliation owner | Không retry mù |
| ESP API 429 không nhận job | Không | Application | Honor Retry-After |
| ESP API accepted receipt | Có | Provider | Lưu receipt |
| Recipient MX 451 sau provider acceptance | Có | Provider | Không tạo submission mới |
| Deferred event | Có | Provider | Đo queue age |
| Hard bounce cuối cùng | Có | Không auto retry y nguyên | Update suppression/policy |
| Customer yêu cầu bản sao sau delivered | Đã gửi | New resend workflow | New notification, audit |
| OTP token hết hạn trước submit | Có thể chưa | Identity/business workflow | Không gửi token cũ |

Ma trận này là baseline. Cần đối chiếu với từng provider và cụ thể cách họ báo acceptance, deferred, bounce và failed state.

## 14. Quyết định kiến trúc theo loại thông báo

| Loại email | Chiến lược thường hợp lý | Lý do |
| --- | --- | --- |
| OTP / authentication | App retry có deadline ngắn + provider retry khi accepted | Token có TTL; resend cũ nguy hiểm |
| Xác nhận đơn hàng | Durable outbox + provider delivery retry | Không mất intent sau commit |
| Hóa đơn / tài liệu | Durable intent, snapshot/attachments repeatable | Tính chính xác, audit, privacy |
| Marketing newsletter | Campaign queue và pacing + provider delivery retry | Volume cao, consent, quotas |
| Monthly digest | App scheduling/retry theo deadline + provider | Có thể chấp nhận trễ |
| Security incident alert | App durability/priority + provider | Nhiều kênh fallback có thể cần |
| Internal notification không quan trọng | Có thể đơn giản hơn theo SLO | Không over-engineer nếu mất một email chấp nhận được |

Không gắn nhãn một email “quan trọng” rồi tự bật retry vô hạn. Một thông báo quan trọng có thể có deadline rõ và không còn đúng sau khi nghiệp vụ đổi trạng thái.

## 15. JavaMailSender thực sự làm gì?

Spring Framework Mail cung cấp:

- `MailSender` để gửi `SimpleMailMessage`.
- `JavaMailSender` để tạo/gửi `MimeMessage`.
- `JavaMailSenderImpl` dùng Jakarta Mail transport.
- `MimeMessageHelper` để dựng HTML/attachment/inline.
- `MailException` và các subtype để phản ánh lỗi preparation/transport.

Ví dụ:

```java
MimeMessage mime = javaMailSender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(mime, true, "UTF-8");

helper.setFrom("notifications@example.test");
helper.setTo("buyer@example.test");
helper.setSubject("Xác nhận đơn hàng");
helper.setText(
    "Đơn hàng của bạn đã xác nhận.",
    "<p>Đơn hàng của bạn đã xác nhận.</p>"
);

javaMailSender.send(mime);
```

Đoạn code thực hiện **một lần submission call**. Spring Mail không tự tạo durable outbox, quản lý số attempts, retry qua restart, webhook inbox, provider status reconciliation hay guaranteed delivery.

Jakarta Mail transport có các hành vi giao thức/implementation riêng; không vì một property timeout hay kết nối lại mà mặc định đã có business-level retry policy.

## 16. Cấu hình Spring Boot Mail không tự bật durable retry

Ví dụ:

```yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
```

Các timeout giúp giới hạn thời gian chờ ở giai đoạn SMTP. Chúng không nói **khi nào và bao nhiêu lần** ứng dụng gửi lại sau failure.

Một timeout phải được hiểu theo phase. Nếu read timeout xảy ra sau khi gửi SMTP DATA, không được tự động khẳng định message chưa được accepted.

`spring.mail.test-connection` (nếu dùng) chỉ kiểm tra khả năng kết nối tại startup/đúng điểm cấu hình; nó cũng không thay thế retry pipeline hoặc delivery tracking.

## 17. Spring Retry @Retryable: khi nào phù hợp?

Spring Retry có thể hỗ trợ retry in-process cho các thao tác transient:

```java
@Retryable(
    retryFor = TransientPreparationException.class,
    maxAttempts = 3,
    backoff = @Backoff(
        delay = 500,
        multiplier = 2.0,
        maxDelay = 3000
    )
)
public PreparedMail prepare(EmailIntent intent) {
    return renderer.render(intent);
}
```

Các imports/classes tương ứng Spring Retry và ứng dụng cần được cấu hình đúng; ví dụ dùng `TransientPreparationException` do hệ thống định nghĩa.

Phù hợp hơn khi:

- Thao tác có tính idempotent/side-effect-free.
- Retry diễn ra trong cửa sổ ngắn.
- Lỗi rõ ràng trước SMTP acceptance.
- Không đòi hỏi sống qua process restart.
- Còn thread budget để chờ retry.

Không nên:

```java
@Retryable(retryFor = MailException.class)
public void sendAnything(MimeMessage mime) {
    javaMailSender.send(mime);
}
```

rồi coi đó là giải pháp đầy đủ cho mọi SMTP failure. `MailException` quá rộng; timeout sau DATA có thể ambiguous. Retry đồng bộ còn giữ thread/request và không bền vững khi JVM chết.

**Spring Retry, Resilience4j retry và provider delivery retry không phải cùng một lớp chức năng.** Chọn theo đúng boundary và durability cần thiết.

## 18. Vì sao durable outbox quan trọng hơn vòng lặp retry?

Giả sử:

```text
Database transaction:
  order = PAID
COMMIT

Application process:
  JavaMailSender.send(...)
  connection refused
  JVM crashes
```

Nếu intent gửi chỉ ở memory, email có thể không bao giờ được thử lại. Nếu gửi trực tiếp **trước** commit nghiệp vụ, email có thể đi dù transaction rollback.

Transactional outbox:

```text
BEGIN DB TRANSACTION
    update order to PAID
    insert mail_intent with status READY
COMMIT

Later:
    worker claims mail_intent
    submits to SMTP
    records outcome
```

Cách này đóng khoảng trống giữa business commit và tạo ý định gửi bền vững. Nó **không** làm SMTP và database trở thành một atomic transaction; vẫn cần xử lý crash sau SMTP acceptance nhưng trước khi DB update.

## 19. Model outbox theo hai giai đoạn

Ví dụ PostgreSQL:

```sql
CREATE TABLE mail_outbox (
    id                       UUID PRIMARY KEY,
    tenant_id                UUID NOT NULL,
    notification_id          UUID NOT NULL UNIQUE,
    business_idempotency_key VARCHAR(200) NOT NULL,
    category                 VARCHAR(40) NOT NULL,
    submission_state         VARCHAR(40) NOT NULL,
    delivery_state           VARCHAR(40) NOT NULL DEFAULT 'UNKNOWN',
    next_attempt_at          TIMESTAMPTZ,
    attempt_count            INT NOT NULL DEFAULT 0,
    max_attempts             INT NOT NULL,
    expires_at               TIMESTAMPTZ,
    provider_account         VARCHAR(100),
    provider_message_id      VARCHAR(255),
    locked_by                VARCHAR(100),
    lease_until              TIMESTAMPTZ,
    claim_version            BIGINT NOT NULL DEFAULT 0,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, business_idempotency_key)
);
```

`business_idempotency_key` phải được định nghĩa đúng phạm vi event/recipient/template. Một key quá rộng có thể chặn notification hợp lệ; quá hẹp có thể tạo nhiều intents cho cùng sự kiện.

Các states là model ứng dụng, không phải enum có sẵn trong Spring Mail. Một record có thể chứa content snapshot/reference, recipient reference và policy metadata dưới phân quyền phù hợp; **không cần đưa raw HTML/OTP vào operational logs**.

## 20. Claim job: tránh nhiều workers gửi cùng một intent

Ví dụ PostgreSQL claim những jobs chưa bắt đầu submission:

```sql
WITH due AS (
    SELECT id
    FROM mail_outbox
    WHERE submission_state IN ('READY', 'RETRY_WAIT')
      AND next_attempt_at <= NOW()
      AND (expires_at IS NULL OR expires_at > NOW())
    ORDER BY next_attempt_at, created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS o
SET submission_state = 'CLAIMED',
    locked_by = :worker_id,
    lease_until = NOW() + (:lease_seconds * INTERVAL '1 second'),
    claim_version = claim_version + 1,
    updated_at = NOW()
FROM due
WHERE o.id = due.id
RETURNING o.id, o.notification_id, o.claim_version;
```

Một transaction claim phải ngắn và commit trước SMTP. `SKIP LOCKED` giúp các pollers bỏ qua row locks của transaction khác; lease/claim_version dùng bảo vệ ownership sau commit.

**Điểm quan trọng:** nếu worker chết ở `CLAIMED` trước khi bắt đầu SMTP, job thường có thể được reclaim sau lease. Nếu chết ở `SUBMITTING` mà outcome có thể đã accepted, không được tùy tiện coi đó là “chắc chắn chưa gửi”. Phải định nghĩa recovery riêng cho pha có side effect.

## 21. Phân biệt CLAIMED và SUBMITTING để phục hồi

Một state machine thực dụng:

```text
READY / RETRY_WAIT
       |
       v
CLAIMED (no network side effect yet)
       |
       v
SUBMITTING (provider call may have begun)
       |
       +--> ACCEPTED
       +--> RETRY_WAIT (definite pre-accept failure)
       +--> FAILED_PERMANENT
       +--> AMBIGUOUS
```

Vấn đề nếu JVM crash:

- `CLAIMED` hết lease: có thể requeue nếu chứng minh chưa gọi provider theo quy trình ownership.
- `SUBMITTING` hết lease: **không biết** đã submit hay chưa; thường đưa vào reconciliation hoặc recovery có chính sách duplicate rõ.
- `ACCEPTED`: provider queue tiếp tục delivery; không replay submission.
- `RETRY_WAIT`: chỉ thử lại khi `nextAttemptAt` đến hạn.

Một hệ thống có provider-supported idempotency key có thể quyết định retry request ambiguous bằng cùng key theo hợp đồng provider. Với SMTP thuần, cơ chế đó thường không được đảm bảo.

Việc ghi state `SUBMITTING` trước network giúp thu hẹp vùng rủi ro nhưng không loại bỏ được mọi race. Không có transaction DB nào đảm bảo atomic exactly-once side effect trên SMTP.

## 22. Fencing stale workers

Nếu worker A giữ lease rồi bị treo, worker B có thể reclaim. A không được cập nhật trạng thái sau khi mất ownership.

Ví dụ:

```sql
UPDATE mail_outbox
SET submission_state = 'ACCEPTED',
    locked_by = NULL,
    lease_until = NULL,
    updated_at = NOW()
WHERE id = :job_id
  AND locked_by = :worker_id
  AND claim_version = :claimed_version
  AND submission_state = 'SUBMITTING';
```

Nếu affected rows = 0, ownership đã đổi. Ghi audit/diagnostic event để điều tra; không ghi đè mù.

Fencing bảo vệ **database state**, nhưng không thu hồi email SMTP đã gửi bởi stale worker. Vì vậy không claim quá sớm, cần bounded in-flight/lease renewal và quản lý trạng thái ambiguous.

## 23. Một abstraction chia rõ trách nhiệm

Trong code ứng dụng, tránh service trả `boolean sent` không có ngữ nghĩa cụ thể. Có thể định nghĩa:

```java
public enum SubmissionOutcome {
    ACCEPTED,
    DEFINITELY_REJECTED_TRANSIENT,
    DEFINITELY_REJECTED_PERMANENT,
    AMBIGUOUS
}
```

Receipt:

```java
public record SubmissionReceipt(
    SubmissionOutcome outcome,
    String providerAccount,
    String providerMessageId,
    String normalizedFailureCode
) {}
```

Port:

```java
public interface MailSubmissionPort {
    SubmissionReceipt submit(PreparedMail mail);
}
```

`PreparedMail`, receipt và enum là types do ứng dụng định nghĩa. `JavaMailSender` không mặc định trả object với các trường này.

Một SMTP adapter có thể không biết provider message ID; khi đó để `null` và lưu internal attempt ID. **Không bịa ID hoặc chuyển mọi `MailException` sang DEFINITELY_REJECTED_TRANSIENT**.

## 24. Worker xử lý receipt theo boundary

Pseudocode Java:

```java
public void process(ClaimedMailJob claim) {
    if (!eligibility.canSendNow(claim.notificationId())) {
        states.markSuppressedIfOwned(claim);
        return;
    }

    PreparedMail prepared =
        content.loadPrepared(claim.notificationId());

    states.markSubmittingIfOwned(claim);

    try {
        SubmissionReceipt receipt =
            submissionPort.submit(prepared);

        switch (receipt.outcome()) {
            case ACCEPTED ->
                states.markAcceptedIfOwned(claim, receipt);

            case DEFINITELY_REJECTED_TRANSIENT ->
                states.scheduleRetryIfOwned(
                    claim, backoff.nextAttempt(claim)
                );

            case DEFINITELY_REJECTED_PERMANENT ->
                states.markFailedIfOwned(claim, receipt);

            case AMBIGUOUS ->
                states.markAmbiguousIfOwned(claim, receipt);
        }
    } catch (RuntimeException unexpected) {
        // If the provider call may have started, do not assume NOT_SENT.
        states.markNeedsReconciliationIfOwned(claim);
        throw unexpected;
    }
}
```

Các services và classes là domain code minh họa. Phải bảo đảm `markSubmittingIfOwned` thành công và commit trước khi network call, tránh worker đã mất lease vẫn gửi.

Không dùng một `catch (Exception)` để luôn `RETRY_WAIT`; lỗi có thể phát sinh sau khi server đã accepted. Với một số provider/adapter, không thể kết luận outcome an toàn chỉ từ exception type; cần conservative AMBIGUOUS branch.

## 25. Backoff và jitter cho application retry

Một policy thường dùng exponential backoff có cap:

\[
d_n = \min(d_{\max}, d_0 \cdot 2^{n-1})
\]

Để tránh thundering herd, có thể dùng full jitter:

\[
w_n \sim U(0,d_n)
\]

Ví dụ những khoảng chờ tối đa:

| Attempt tiếp theo | Cap minh họa |
| --- | ---: |
| 2 | 10 giây |
| 3 | 20 giây |
| 4 | 40 giây |
| 5 | 80 giây |
| 6 trở đi | Tối đa theo cap đã cấu hình |

Jitter làm lệch các retries của nhiều jobs, không làm tăng provider quota. Nếu provider có `Retry-After` hoặc cooldown chính thức, policy cần tôn trọng chỉ dẫn đó trước khi tính lịch.

Không để vòng lặp `Thread.sleep` kéo dài trong HTTP request hoặc database transaction. Persist `nextAttemptAt` và cho scheduler claim job khi đến hạn.

## 26. Max attempts, deadline và business expiry

Một notification có thể có:

- `maxAttempts`: số attempts submission tối đa theo policy.
- `expiresAt`: sau mốc này không gửi nội dung cũ.
- `nextAttemptAt`: thời điểm được phép retry.
- `providerQueueDeadline`: nếu provider có khả năng cấu hình.
- `consentVersion`/recipient suppression status.

Ví dụ OTP:

```text
Created at     10:00:00
Token expires  10:05:00
SMTP outage    10:00-10:10
```

Không nên backlog và gửi OTP cũ lúc 10:10. Sau expiry, chuyển sang `EXPIRED` hoặc một business workflow khác cấp token mới nếu người dùng yêu cầu hợp lệ.

Lưu ý: **expiry của ứng dụng trước submission** chưa chắc thu hồi được message đã accepted nằm trong provider queue. Nếu nội dung có thời hạn rất ngắn, phải cân nhắc provider retry TTL/cancellation capabilities; nhiều nền tảng không hỗ trợ thu hồi mọi queued email.

## 27. Provider retry policy và delivery window phải được biết

Khi chọn platform-owned downstream retry, cần xác minh:

1. Provider có queue bền vững sau acceptance không?
2. Thời gian tối đa retry giao thư là bao lâu?
3. Cơ chế xử lý remote 4xx/greylisting?
4. Khi nào message bị final bounce hoặc expire?
5. Có phân biệt temporary và permanent failure?
6. Có webhook/API events cho deferred, delivered, bounced, complaint không?
7. Events có độ trễ và replay semantics thế nào?
8. Có giới hạn recipient domains/connection concurrency?
9. Có hỗ trợ cancellation khi content hết hạn?
10. Có thể tra provider message ID và queue status không?
11. Có cơ chế suppression và opt-out riêng không?
12. Nếu provider outage sau acceptance, cam kết recovery/retention là gì?

Không ghi trong kiến trúc “provider tự retry 72 giờ” nếu chưa có bằng chứng từ tài liệu/hợp đồng của provider đang dùng. Các nền tảng có thể khác nhau và có thể thay đổi cấu hình.

## 28. Webhook/event xử lý downstream delivery

Nếu provider có callback:

```text
Provider queue
      |
      +--> deferred
      +--> delivered
      +--> bounced
      +--> complained
      |
      v
Signed webhook / authenticated event
      |
      v
Verify authenticity + parse
      |
      v
Deduplicate provider event ID
      |
      v
Correlate providerMessageId / internal notificationId
      |
      v
Update delivery state
      |
      v
Metrics / suppression / alerts
```

Webhook handler **không** nên tự gửi lại email mỗi khi nhận `DEFERRED`. Deferred có thể chỉ mô tả một lần provider đang chờ thử tiếp.

Một final hard bounce có thể yêu cầu suppression, cleanup hoặc cập nhật customer contact; đó là business policy, không phải lệnh retry vô hạn.

## 29. Webhook không đảm bảo thứ tự và đúng một lần

Provider events có thể:

- Được gửi lặp lại do webhook retry.
- Đến ngoài thứ tự do queue/network.
- Đến sau khi ứng dụng restart.
- Có cùng message nhưng nhiều recipient statuses.
- Đến trước khi internal DB update `ACCEPTED` hoàn tất.
- Bị mất nếu endpoint ngừng hoạt động và provider retention hết hạn.

Do đó cần:

- Verify signature/authentication và timestamp/replay protection theo provider spec.
- Persist event ID có unique constraint hoặc dedup rule đáng tin.
- Dùng correlation key rõ giữa provider message và notification.
- Cập nhật state bằng monotonic rules/policy, không ghi đè `DELIVERED` bởi một event `DEFERRED` cũ.
- Có reconciliation bằng provider API khi event thiếu nếu provider hỗ trợ.
- Quản lý access/privacy của webhook payload.

Không dựa vào HTTP response của webhook như bằng chứng ứng dụng đã commit status, trừ khi logic đã xử lý durability đúng.

## 30. Một ví dụ bảng provider events

```sql
CREATE TABLE mail_provider_event (
    id                  UUID PRIMARY KEY,
    provider_account    VARCHAR(100) NOT NULL,
    provider_event_id   VARCHAR(255),
    provider_message_id VARCHAR(255),
    notification_id     UUID,
    recipient_ref       VARCHAR(200),
    event_type          VARCHAR(50) NOT NULL,
    occurred_at         TIMESTAMPTZ,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at        TIMESTAMPTZ
);

CREATE UNIQUE INDEX idx_mail_provider_event_dedup
ON mail_provider_event (provider_account, provider_event_id)
WHERE provider_event_id IS NOT NULL;
```

Nếu provider không cấp event ID, cần một dedup strategy khác dựa trên những trường có độ tin cậy phù hợp; không tự tạo unique constraint sai làm mất các event hợp lệ.

Một provider message có thể gửi cho nhiều recipients, vì vậy event có thể cần recipient-level identity. Dữ liệu recipient phải được bảo vệ theo privacy policy; operational logs chỉ nên hiển thị opaque IDs và event classes.

## 31. Reconciliation khi outcome ambiguous

Một quy trình:

```text
SUBMITTING attempt
      |
      +--> client timeout / process crash
      |
      v
AMBIGUOUS
      |
      v
Can provider query by request ID / idempotency key / queue ID?
      |
      +--> yes: find accepted evidence -> mark ACCEPTED
      |
      +--> no result: evidence still incomplete?
      |
      +--> provider contract confirms not accepted -> retry if eligible
      |
      +--> cannot determine -> hold / manual policy / bounded risk decision
```

“Không tìm thấy message ngay” không luôn chứng minh provider chưa nhận, vì indexing/API có thể eventual consistent. Thiết kế cần hiểu cửa sổ nhất quán và retention của provider.

Khi dùng SMTP relay thuần không có API tra cứu, có thể không thể reconcile hoàn toàn. Hệ thống phải chọn một **duplicate-risk policy** theo loại email:

- Với thông báo thông thường, business có thể chấp nhận khả năng duplicate thấp để ưu tiên at-least-once.
- Với tài liệu/security operations nhạy cảm, có thể cần manual review hoặc workflow xác thực riêng.
- Với một số loại mail, bỏ lỡ một email có thể kém nghiêm trọng hơn gửi hai lần; cũng phải nêu rõ lựa chọn.

Không quảng cáo exactly-once email delivery khi không có contract end-to-end hỗ trợ.

## 32. Message-ID và idempotency key có giống nhau?

Không.

- **Notification ID:** định danh logic do ứng dụng tạo.
- **Attempt ID:** định danh mỗi lần thử submit.
- **MIME Message-ID:** header email theo chuẩn thư, hữu ích cho correlation.
- **Provider message ID:** định danh hàng đợi/event ở provider nếu cấp.
- **HTTP API idempotency key:** khóa dedup request khi provider có feature rõ.
- **Business idempotency key:** chống tạo hai notification intents cho cùng một business event.

SMTP không có cơ chế chung buộc recipient MX loại trùng hai messages cùng MIME Message-ID. Việc cố giữ nguyên header Message-ID qua retry không tạo exactly-once.

Nếu provider HTTP API hỗ trợ idempotency key, phải đọc scope (account/endpoint), TTL, khả năng trả lại receipt và cách xử lý response timeout. Một key trùng nhưng payload khác có thể bị từ chối hoặc xử lý theo quy định riêng.

## 33. Chọn provider fallback cũng có thể tạo duplicate

Một luồng:

```text
Submit to provider A
      |
      +--> read timeout (UNKNOWN)
      |
      v
Immediately submit same mail to provider B
      |
      v
Both providers may have queued it
```

Provider fallback chỉ nên tự động khi đã có bằng chứng provider A **chưa accepted**, hoặc khi ứng dụng chấp nhận rõ ràng duplicate risk theo policy. Nếu A ambiguous, failover không an toàn hơn retry A theo cách thông thường.

Cần theo dõi:

- `notificationId` chung.
- `attemptId` riêng.
- `providerAccount`/`providerRequestId`.
- Acceptance evidence.
- Provider event mapping từ cả A và B.
- Quota/cooldown/suppression theo cả hai provider.
- Content snapshot và recipient eligibility.

Không tạo provider-specific headers chứa secret hoặc log full MIME để correlation.

## 34. Lưu nội dung để retry: snapshot hay render lại?

Nếu retry application submission, quyết định nội dung phải rõ:

**Snapshot/Prepared mail**

- Lưu subject/plain/HTML hoặc artifact references đã chuẩn bị an toàn.
- Đảm bảo attempts cùng logical intent dùng content version nhất quán.
- Hữu ích cho invoice/transactional audit.
- Cần policy retention/encryption và artifact availability.

**Render lại trước attempt**

- Dùng dữ liệu/template hiện tại.
- Có thể phản ánh business state mới hơn.
- Nhưng attempts khác nhau có thể tạo nội dung khác cho cùng notification.
- Có nguy cơ gửi OTP cũ hoặc sửa subject/attachments ngoài ý muốn.

Không chọn tự động. Một policy tốt có thể dùng immutable template version + data snapshot cho email cần tính lịch sử, và kiểm tra eligibility/expiry hiện thời trước submit.

Với security tokens, việc phát hành token mới phải thuộc identity workflow chứ không phải mail retry tự động render tùy ý.

## 35. Cancellation và delayed provider delivery

Nếu user hủy đơn hoặc thu hồi một link sau khi provider đã accepted email:

- Application có thể hủy jobs chưa submit.
- Nhưng không thể mặc nhiên xóa email đang nằm trong queue của một SMTP relay bên ngoài.
- Một số provider có API cancel/expire queued messages trong phạm vi nhất định; nhiều nơi không có.
- Nếu email chứa link có token, token phía server nên có khả năng revoke/expire độc lập với việc thư đã được phát.
- Business workflows cần cân nhắc khả năng thư tới muộn.

Vì vậy khi chọn để provider retry trong thời gian dài, phải xem **nội dung có còn hợp lệ khi tới muộn**. Email OTP TTL 5 phút không nên phụ thuộc vào một delivery retry window nhiều ngày để đạt trải nghiệm mong muốn.

## 36. SLA/SLO: đo submission và delivery riêng

Đề xuất hai SLO:

1. **Application submission SLO:** từ business commit/intent due đến khi provider accepted.
2. **Delivery outcome SLO:** từ provider acceptance đến provider delivered/bounced/final status, theo khả năng của nhà cung cấp.

Ví dụ metrics:

```text
mail_intent_to_acceptance_seconds
mail_submission_attempt_duration_seconds
mail_submission_accepted_total
mail_submission_failed_total
mail_submission_ambiguous_total
mail_submission_retry_scheduled_total

mail_provider_deferred_total
mail_provider_delivered_total
mail_provider_bounced_total
mail_provider_delivery_lag_seconds
mail_provider_event_processing_lag_seconds
```

Các tên trên là metrics ứng dụng gợi ý, không tự sinh bởi Spring Mail.

Một SLO về “email đến Inbox trong 2 giây” thường không thể chỉ do Spring/SMTP client kiểm soát. Phải dùng định nghĩa đầu-cuối khả thi và chỉ báo theo provider evidence; ngay cả DELIVERED event cũng có thể không phân biệt Inbox và Spam folder.

## 37. Đo hiệu quả retry thay vì chỉ tăng số attempts

Một dashboard hữu ích:

| Chỉ số | Tầng sở hữu | Câu hỏi |
| --- | --- | --- |
| Outbox READY oldest age | App | Có jobs nào chưa submit quá lâu? |
| Submission retry rate | App | Có provider outage/throttle? |
| Ambiguous attempt count | App | Có timeout khó đối soát? |
| Acceptance rate | App/Provider | Provider đã nhận bao nhiêu? |
| Provider deferred count | Provider events | Downstream đang tạm trì hoãn? |
| Delivery lag P95/P99 | Provider events | Thư đã accepted nhưng chậm giao? |
| Bounce/complaint rate | Provider events | Recipient quality/reputation thế nào? |
| Duplicate complaints | App/business | Có gửi trùng do layered retry? |
| Expired before submission | App | SLO và business deadline có phù hợp? |
| Provider webhook lag | App/Provider | Events có đang đến trễ? |

Không dùng recipient email hay subject làm metric labels; chúng có thể chứa PII và tạo high cardinality. Dùng provider, category và normalized outcome ở mức tổng hợp.

## 38. Backpressure và rate limit ở tầng ứng dụng

Dù provider đảm nhận delivery retry, ứng dụng vẫn phải giới hạn **submission rate**:

- SMTP provider có giới hạn messages/second, recipients/minute và concurrent connections.
- HTTP ESP API có burst/rate limit và 429 responses.
- Database outbox có thể có backlog lớn sau outage.
- Nếu worker trút toàn bộ backlog ngay khi provider phục hồi, có thể tạo retry storm.
- Nhiều instances cùng dùng provider account có thể vượt global quota dù từng JVM có limiter riêng.

Cần bounded workers, rate limiter theo provider/account và batch size phù hợp capacity. Application-level retry nên đặt `nextAttemptAt` cho mỗi job thay vì ngủ lâu trong thread.

Không dùng platform delivery retry làm lý do bỏ qua admission/submission throttling.

## 39. Một sơ đồ retry và circuit breaker

```text
Outbox READY
     |
     v
Worker claims if provider circuit permits
     |
     v
Token/permit from provider budget
     |
     v
Submit once
     |
     +--> accepted --------> STOP APP SUBMISSION RETRY
     |                         |
     |                         v
     |                   Provider queue/retry
     |
     +--> definite transient -> backoff+jitter -> RETRY_WAIT
     |
     +--> permanent -> FAILED / operator action
     |
     +--> ambiguous -> RECONCILE / policy gate
```

Circuit breaker bảo vệ provider/ứng dụng khi lỗi kéo dài, nhưng không tự đảm bảo một message đã accepted không bị submit lần nữa. Retry policy vẫn cần state machine và idempotency.

Một lỗi xác thực SMTP thường cần can thiệp cấu hình; open circuit/cooldown có thể ngăn hàng nghìn attempts lặp cùng credential sai.

## 40. Chọn giữa SMTP và ESP API ảnh hưởng khả năng retry

**SMTP submission:**

Ưu điểm:

- Chuẩn phổ biến, Spring `JavaMailSender` hỗ trợ trực tiếp.
- Dễ thay relay nếu chỉ cần gửi cơ bản.
- Provider có thể xử lý remote delivery retry.

Hạn chế:

- Client có thể không nhận provider queue ID.
- Timeout sau DATA là trường hợp ambiguous khó reconcile.
- Delivery event không có sẵn trong SMTP client.
- API gửi lại có idempotency key thường không phải phần của SMTP.

**ESP HTTP API:**

Ưu điểm có thể có:

- Receipt/provider request IDs.
- Idempotency key nếu được hỗ trợ.
- Delivery/deferred/bounce/complaint events.
- API tra trạng thái và cấu hình suppression.

Hạn chế:

- Vendor-specific SDK/schema/quotas.
- Response 5xx/timeout vẫn có thể ambiguous.
- Provider API idempotency không phải luôn có.
- Cần bảo vệ webhook, tokens và event data.
- Migration giữa providers có thể cần adapter/canonical model.

Chọn giao thức theo khả năng quan sát/đối soát và yêu cầu nghiệp vụ, không chỉ theo độ ngắn của code gửi email.

## 41. Quyết định dùng direct synchronous send khi nào?

Không phải mọi ứng dụng đều cần outbox phức tạp. Gửi trực tiếp có thể phù hợp khi:

- Email không quan trọng hoặc có thể mất mà nghiệp vụ vẫn đúng.
- Không cần guarantee sau process restart.
- Volume thấp.
- Request latency/SLO chấp nhận được.
- Retry manual hoặc ngoại lệ được xử lý ở workflow khác.
- Không có business transaction yêu cầu atomic intent.

Nhưng phải mô tả rủi ro: một lỗi mạng sau commit sẽ mất email nếu không có durable intent. Gửi trực tiếp trong database transaction cũng không khiến SMTP rollback được khi DB rollback.

Đối với hóa đơn, confirmation và notifications có yêu cầu tin cậy cao, durable outbox thường đáng giá hơn in-memory retry.

## 42. Ba phương án kiến trúc để so sánh

**Phương án A — Chỉ retry trong ứng dụng**

```text
App -> SMTP attempt
      -> retry every failure locally
```

Nếu không phân biệt accepted vs downstream, nguy cơ gửi trùng cao. Chỉ phù hợp trong phạm vi nhỏ khi platform không có queue và app hiểu chính xác acceptance.

**Phương án B — Chỉ dùng nền tảng gửi**

```text
App sends once
    -> if provider accepted, provider retries
```

Đơn giản sau acceptance, nhưng nếu app/process chết trước acceptance hoặc API bị lỗi, intent có thể mất.

**Phương án C — Hai tầng có ranh giới (thường phù hợp production)**

```text
Durable app intent
    -> app retries definite pre-accept failures
    -> provider acceptance
    -> provider retries downstream
    -> app records delivery events
```

Phương án C không phải retry gấp đôi cùng một failure. Nó phân chia ownership theo stage và vẫn cần AMBIGUOUS handling. Từng tổ chức có thể điều chỉnh trade-off cost/complexity/SLO.

## 43. Decision matrix theo yêu cầu

| Tiêu chí | Ưu tiên app retry | Ưu tiên platform retry |
| --- | --- | --- |
| Lỗi chưa tới provider | Có | Không có message để retry |
| Provider đã accepted | Không resubmit | Có, downstream delivery |
| Business expiry/consent | App quyết định | Provider cần nhận giới hạn nếu hỗ trợ |
| Remote MX temporary 4xx | Không thấy trực tiếp sau acceptance | Có |
| Process restart durability | App outbox/broker | Không thay app intent nếu chưa accepted |
| Per-domain throttling | Chỉ admission ở app | Provider thường hiểu MX/domain |
| Delivery/bounce events | App consume/act | Provider phát sự kiện |
| Provider API 429 | App backoff | Platform có thể chưa nhận job |
| Unknown acceptance | App reconcile/decide | Provider query/idempotency nếu hỗ trợ |
| Manual customer resend | App workflow | Platform submit notification mới theo quyết định app |
| Cost/duplicate control | App policy/IDs | Provider queue semantics |
| Vendor portability | App abstraction | Provider-specific retry behavior |

Cần kiểm chứng các năng lực cụ thể từ tài liệu/hợp đồng provider thay vì dựa vào giả định chung.

## 44. Kiến trúc đa provider và retry owner

Một adapter có thể che chi tiết provider:

```java
public interface ProviderMailGateway {
    SubmissionReceipt submit(
        PreparedMail mail,
        String logicalIdempotencyKey
    );

    Optional<ProviderDeliveryStatus> findStatus(
        String providerMessageId
    );
}
```

Phương thức `findStatus` là capability **tùy provider**, không phải mọi adapter phải thực hiện thật nếu nền tảng thiếu API. Có thể biểu diễn khả năng này bằng feature flag/capability contract, thay vì tự trả “not found” gây kết luận sai.

Một lựa chọn có thể là:

```text
ProviderCapabilities:
  supportsIdempotencyKey
  supportsStatusLookup
  supportsDeliveryWebhook
  supportsCancelQueued
  retryWindowPolicy
```

Không dùng feature flags này để giả vờ provider có chức năng không tồn tại. Worker cần biết khi nào có thể an toàn retry một ambiguous request bằng cùng idempotency key.

## 45. Tình huống A: Email xác nhận đơn hàng

Yêu cầu:

- Không mất intent sau order commit.
- Không gửi trước khi business transaction thành công.
- Tránh gửi trùng.
- Theo dõi bounce.
- Cho khách yêu cầu bản sao có lý do.

Thiết kế:

1. Trong order transaction, insert outbox `READY` với business idempotency key.
2. Worker claim và kiểm tra eligibility.
3. Render/sử dụng prepared snapshot và submit.
4. Nếu connect refused trước acceptance, app retry với backoff.
5. Nếu provider accepted, mark `ACCEPTED`; stop submission retry.
6. Provider tự thử giao thư nếu recipient MX tạm lỗi.
7. App nhận delivery/bounce webhook và cập nhật trạng thái.
8. Nếu khách yêu cầu bản sao sau delivered, tạo **resend notification mới**, không reset original.

Outcome ambiguous sau SMTP DATA cần chính sách riêng; không ghi chắc chắn `NOT_SENT` và retry lập tức.

## 46. Tình huống B: OTP có TTL 5 phút

Yêu cầu:

- Latency thấp.
- Token hết hạn sau vài phút.
- Không gửi mã cũ sau expiry.
- Anti-abuse và frequency caps.
- Không để provider queue gửi link đã vô hiệu mà gây nhầm lẫn.

Thiết kế:

1. Identity workflow tạo token theo policy và outbox intent.
2. App kiểm tra `expiresAt` trước mỗi attempt.
3. Retry pre-acceptance nhanh nhưng bounded theo thời gian còn lại.
4. Nếu accepted, provider xử lý delivery, nhưng app không tự resubmit chỉ vì chưa thấy delivered.
5. Nếu user bấm “Gửi mã mới”, identity service quyết định rotate/issue token, tạo notification khác.
6. Không dùng manual mail resend để copy raw OTP email cũ.
7. Nếu provider cho phép TTL/cancel, cân nhắc cấu hình tương thích; nếu không, token validation server-side vẫn kiểm soát hiệu lực.

Với OTP, nhiều retry có thể vô ích hơn việc user dùng một kênh xác thực khác, tùy threat model.

## 47. Tình huống C: Campaign marketing khối lượng lớn

Yêu cầu:

- Consent/suppression được áp trước khi gửi.
- Provider rate budget không bị vượt.
- Có thể chấp nhận gửi dàn trải.
- Theo dõi bounce/complaint và danh tiếng domain.
- Không gửi lại một recipient nhiều lần khi provider đang deferred.

Thiết kế:

1. Campaign scheduler tạo intents theo recipient/segment đã xác minh.
2. Worker áp quota và eligibility trước submit.
3. ESP nhận message và queue.
4. Provider retry remote delivery theo rate/domain policy.
5. App cập nhật suppression khi hard bounce/complaint.
6. App không dùng `delivery != DELIVERED` làm điều kiện submit lại campaign.
7. Restart/campaign pause chỉ ảnh hưởng jobs chưa accepted, hoặc dùng cancel API nếu provider có capability phù hợp.
8. Resend marketing là một campaign action có consent/frequency policy riêng.

Đối với bulk jobs, batch size chỉ điều khiển cấp việc nội bộ; provider quota vẫn là giới hạn độc lập.

## 48. Tình huống D: Provider primary mất kết nối

Giả sử primary trả connect refused rõ ràng trước khi gửi dữ liệu:

```text
N-1001 -> Provider A connect failed
             |
             v
         App retry policy
             |
             +--> backoff to A
             |
             +--> optional fallback to B
                  if policy and acceptance proof allow
```

Nếu A chưa bao giờ nhận message, failover có thể an toàn hơn. Nhưng nếu lỗi là read timeout sau DATA, chuyển ngay sang B có thể tạo hai bản. Phải lưu acceptance confidence và provider attempts.

Chính sách fallback nên cân nhắc:

- Provider B có cùng sender authorization/DKIM policy?
- Recipient suppression được đồng bộ thế nào?
- Content và attachments có repeatable không?
- Thời hạn business email còn phù hợp?
- Có global quota hoặc reputation constraints?
- Event callbacks từ A/B được correlate ra sao?

Không dùng provider fallback như một cách né quota hoặc bỏ qua suppression.

## 49. Kiểm thử: tách hai tầng một cách có chủ đích

**Unit tests cho application retry:**

- Connect failure trước acceptance → `RETRY_WAIT`.
- SMTP authentication permanent → stop/circuit/config action.
- Deadline expired → `EXPIRED`, không submit.
- Rate limit → retry theo cooldown.
- Attempt count exhausted → không retry vô hạn.
- Same business event → không tạo hai intents.
- Manual resend → notification mới, original không đổi.
- Unknown acceptance → `AMBIGUOUS`, không auto retry thường.

**Integration tests với SMTP capture (GreenMail/Mailpit):**

- Worker thực hiện submission và capture đúng MIME.
- Status `ACCEPTED` sau SMTP response thành công.
- Không resubmit khi chỉ có delivery status pending.
- Simulate server reject trước DATA theo khả năng fixture/test server.
- Simulate dropped response sau DATA bằng server stub/proxy để kiểm tra ambiguous path.
- Repeated worker delivery/restart không làm mất durable intent.
- Multiple workers atomic claim cùng job không tạo duplicate happy path.

**Webhook integration tests:**

- Event authenticity/signature invalid → reject.
- Duplicate event ID → dedup.
- Deferred rồi delivered → trạng thái cuối đúng.
- Out-of-order deferred sau delivered → không downgrade.
- Bounced/complained → cập nhật suppression phù hợp.
- Event đến trước internal receipt update → correlation/reconciliation.
- Provider status lookup tạm unavailable → không đưa ra kết luận “not accepted”.

## 50. Fault injection quan trọng hơn happy path đơn giản

Một bộ bài kiểm thử lỗi có thể thực hiện:

```text
Fault 1: DB transaction rolls back before outbox insert
Fault 2: JVM crashes after business commit, before worker claim
Fault 3: SMTP connect refused
Fault 4: SMTP rejects recipient before acceptance
Fault 5: SMTP DATA accepted, final response lost
Fault 6: Worker crashes after provider accepted, before DB commit
Fault 7: Provider defers downstream delivery
Fault 8: Provider webhook arrives twice and out of order
Fault 9: Provider event never arrives before reconciliation window
Fault 10: Rate limiter and provider 429 appear together
Fault 11: Recipient unsubscribes while job RETRY_WAIT
Fault 12: OTP expires while provider/worker is offline
```

Ở mỗi fault, xác nhận:

- Notification state chính xác.
- Retry owner rõ.
- Không gửi vô hạn.
- Không mất durable intent khi policy yêu cầu.
- Không tự nhận delivered.
- Không gây leak recipient/secret trong logs.
- Các bước manual reconciliation có thể thực hiện.

Mock `JavaMailSender.send()` ném exception đơn thuần không tái hiện đầy đủ ranh giới DATA acceptance. Cần protocol-aware test server/proxy cho tình huống ambiguous.

## 51. Observability và logging an toàn

Log sự kiện theo IDs:

```json
{
  "event": "mail.submission.attempt",
  "notificationId": "N-1001",
  "attemptId": "A2",
  "provider": "primary",
  "phase": "SUBMISSION",
  "outcome": "DEFINITELY_REJECTED_TRANSIENT",
  "failureClass": "SMTP_TEMPORARY",
  "nextAttemptAt": "2026-11-12T11:30:00Z"
}
```

Khi accepted:

```json
{
  "event": "mail.provider.accepted",
  "notificationId": "N-1001",
  "attemptId": "A3",
  "provider": "primary",
  "providerMessageId": "opaque-provider-id",
  "deliveryState": "QUEUED"
}
```

Không log full `MimeMessage`, subject, Bcc/To recipients, raw attachment, OTP, SMTP password hoặc nested exception message chứa recipient. Các trường `notificationId`/`attemptId` giúp điều tra mà không cần raw payload.

Nếu cần correlation recipient, dùng secure database lookups theo quyền thay vì đưa email address vào metric labels/traces.

## 52. Chọn mức độ phức tạp theo yêu cầu

Không phải email service nào cũng cần:

- Hai providers với fallback.
- Circuit breakers đa tầng.
- Sophisticated dynamic backoff.
- Reconciliation API.
- State machine nhiều chục states.
- Event sourcing toàn bộ email history.

Nhưng với hệ thống yêu cầu gửi chắc chắn, ít nhất cần:

1. Durable intent hoặc một nguồn công việc bền vững.
2. Phân biệt pre-accept failure và accepted.
3. Bounded application retries.
4. Deadline/eligibility recheck.
5. Outcome AMBIGUOUS xử lý có chủ đích.
6. Provider delivery/bounce observability nếu business cần.
7. Idempotency/duplicate-risk policy.
8. Logging/audit tối thiểu.

Tăng complexity phải gắn với cụ thể SLO, vendor capabilities và cost of missed vs duplicate messages.

## 53. Một ADR ngắn để ghi quyết định kiến trúc

Ví dụ:

```text
ADR: Retry ownership for transactional email

Context:
  Spring Boot app persists order confirmation intents.
  SMTP provider accepts messages into its durable queue.
  Provider exposes delivery/bounce events.

Decision:
  Application owns retry until definite provider acceptance.
  Provider owns delivery retry after acceptance.
  Application will not resubmit merely because delivery is pending.
  Ambiguous submission attempts enter reconciliation state.
  Outbox jobs expire according to business policy.
  Resend creates a new notification with explicit authorization.

Consequences:
  Need outbox, worker leases, retry budget and event dedup.
  Need provider SLA/webhook/retention monitoring.
  May still face ambiguous SMTP outcomes and duplicate risk.
  Cannot guarantee Inbox placement or exactly-once email delivery.

Review triggers:
  Provider contract change, new API idempotency support,
  repeated ambiguous incidents, tighter business deadlines.
```

ADR nên có owner, ngày hiệu lực, provider capability evidence và các trade-off được chấp nhận. Khi provider thay đổi retry window hoặc event schema, cần xem lại quyết định.

## 54. Anti-pattern cần tránh

| Anti-pattern | Vì sao sai | Thay thế |
| --- | --- | --- |
| Retry ứng dụng nếu `delivery != DELIVERED` | Provider có thể đang tự retry sau acceptance | Stop after accepted; track delivery |
| Coi `JavaMailSender.send()` là delivered | Submission khác delivery | Tách state và SLO |
| Gửi lại khi SMTP final response mất | Có thể relay đã queued | AMBIGUOUS/reconcile |
| Retry tất cả `MailException` như transient | AUTH, MIME, permanent errors khác nhau | Failure classification |
| Chỉ dùng `@Retryable` để bảo đảm không mất mail | In-memory/restart risk | Durable outbox |
| Gửi SMTP trong DB transaction | DB rollback không rollback email | Commit intent trước, gửi sau |
| Dùng Message-ID làm dedup key chắc chắn | SMTP không bảo đảm dedup | Business key/provider idempotency |
| Failover sang provider B khi A ambiguous | Có thể cả hai đã nhận | Acceptance-aware policy |
| Coi 4xx ở mọi stage đều app retry | 4xx downstream thuộc provider | Theo boundary |
| Tin mọi HTTP 500 nghĩa chưa nhận | Provider có thể queue rồi lỗi response | API idempotency/reconciliation |
| Không có max attempts/deadline | Retry vô hạn, gửi nội dung cũ | Budget + expiry |
| Retry ngay khi provider 429 | Tăng throttling | Retry-After/cooldown/jitter |
| Không theo dõi webhook event duplicates | Delivery state sai | Event dedup + monotonic updates |
| Gửi lại hard bounce bằng nguyên địa chỉ | Khả năng tiếp tục thất bại/suppression | Address remediation |
| Copy OTP mail cũ khi user nhấn resend | Token hết hạn hoặc không an toàn | Identity workflow mới |
| Bật provider+app retry không có owner | Hai tầng cùng gửi lại | Ownership matrix |
| Log full email để đối soát | Lộ nội dung người nhận | Opaque IDs và secure storage |
| Coi provider delayed event là failure | Event có thể đến trễ | Reconciliation window |

## 55. Runbook khi SMTP submission lỗi

1. Xác định notification ID, attempt ID, provider/account.
2. Xem phase failure: connect/auth/RCPT/DATA/final response/API.
3. Kiểm tra provider đã accepted/queued chưa.
4. Nếu chắc chắn chưa accepted, phân loại transient/permanent.
5. Nếu transient, xác định cooldown/Retry-After và nextAttemptAt.
6. Nếu permanent/configuration, sửa nguyên nhân; không retry nóng.
7. Nếu ambiguous, kiểm tra provider status/logs và idempotency capability.
8. Không gửi lại khi provider đã accepted và đang deferred downstream.
9. Kiểm tra recipient eligibility/consent/expiry trước attempt mới.
10. Theo dõi max attempts, queue age và circuit breaker.
11. Ghi normalized outcome và audit, không raw MIME.
12. Nếu cần thao tác manual, dùng authorization/idempotency và quyết định duplicate risk rõ.

## 56. Runbook khi khách nói “Chưa nhận được email”

1. Kiểm tra app đã tạo durable intent hay chưa.
2. Nếu chưa submit: xem outbox status và lỗi pre-acceptance.
3. Nếu `SUBMITTED`: kiểm tra provider queue/status.
4. Nếu provider `DEFERRED`: xem retry window/cooldown; chưa cần app resend.
5. Nếu `DELIVERED`: hỏi người dùng kiểm tra Spam/filtered mailbox theo quy trình hỗ trợ; event không chứng minh đã đọc.
6. Nếu `BOUNCED`: kiểm tra nguyên nhân và suppression, không retry nguyên địa chỉ mù quáng.
7. Nếu `AMBIGUOUS`: reconciliation và policy tránh duplicate.
8. Với OTP/reset link, kiểm tra expiry; nếu cần, hướng qua workflow cấp token mới.
9. Nếu cần bản sao có chủ đích, tạo **resend notification mới** với lý do và consent.
10. Cập nhật ticket bằng metadata đã được phân quyền, không đưa raw email/token vào logs.

## 57. Checklist quyết định trước production

- [ ] Đã định nghĩa cụ thể ranh giới provider acceptance?
- [ ] Biết trạng thái nào chắc chắn chưa accepted, nào accepted, nào ambiguous?
- [ ] App retry có durable outbox/broker nếu business yêu cầu?
- [ ] Retry có max attempts, backoff, jitter và deadline?
- [ ] `nextAttemptAt` tách khỏi polling interval?
- [ ] Có ownership/lease/fencing trong multi-worker?
- [ ] Không gửi SMTP trong business/claim DB transaction?
- [ ] Provider có retry downstream và retry window được xác nhận?
- [ ] App không resubmit khi provider delivery đang pending/deferred?
- [ ] Provider API idempotency/lookup capabilities đã được xác minh?
- [ ] Có handling AMBIGUOUS tránh duplicate?
- [ ] Events/webhooks được verify, dedup và xử lý out-of-order?
- [ ] Provider bounced/complaint cập nhật suppression?
- [ ] OTP/security content có expiration/reissue policy?
- [ ] Manual resend khác retry và có authorization?
- [ ] Provider fallback không chạy trên unknown acceptance một cách mù quáng?
- [ ] Submission và delivery SLO được đo riêng?
- [ ] Có tests cho timeout sau DATA và crash sau acceptance?
- [ ] Logs/metrics không chứa recipient, body, attachment, secret?
- [ ] Đã ghi quyết định, owner và review triggers vào ADR?

## 58. Ghi nhớ

- **Ứng dụng thường retry những lần submission chưa được provider xác nhận tiếp nhận**.
- **Nền tảng gửi thường retry giao thư downstream sau khi đã accepted/queued**.
- Hai tầng retry bổ sung cho nhau nếu có ownership rõ, không cùng gửi lại một accepted notification.
- `JavaMailSender` là abstraction gửi SMTP, không tự có durable outbox hoặc provider delivery tracking.
- SMTP `250` sau DATA và provider accepted receipt **không phải** bằng chứng Inbox delivery.
- SMTP 4xx ở client pre-acceptance khác remote 4xx sau provider acceptance.
- API 429 hoặc definite pre-accept transient error thường thuộc retry của ứng dụng.
- Timeout sau DATA, response lost hoặc crash sau provider acceptance có thể là `AMBIGUOUS`.
- `Message-ID` không tạo exactly-once email delivery.
- Provider idempotency keys và status APIs phải kiểm chứng theo hợp đồng thật.
- Durable intent/transactional outbox bảo vệ business commit trước khi gửi.
- Outbox không làm SMTP và database commit nguyên tử; cần state machine/lease/reconciliation.
- Backoff, jitter, retry budgets và expiry ngăn storm và gửi email đã mất giá trị.
- Consent, suppression và recipient eligibility cần recheck trước submission.
- Provider deferred/queued event không phải yêu cầu ứng dụng gửi lại.
- Webhook có thể duplicate và out-of-order; phải verify, dedup và update state cẩn thận.
- Resend theo yêu cầu người dùng là **notification mới**, không phải retry notification đã delivered.
- OTP/reset link mới phải do security workflow phát hành, không copy raw mail cũ.
- Nên đo submission latency và delivery lag riêng, với bằng chứng phù hợp.
- Kiến trúc cần ghi trade-off giữa mất mail, gửi trùng, latency, chi phí và vendor capabilities.

**Nguyên tắc cốt lõi:** Đừng hỏi “retry ở Spring hay ở provider?” như một lựa chọn chỉ được chọn một. Hãy hỏi **“thông điệp đã được nền tảng chấp nhận chưa, và tầng nào có đủ thông tin để retry an toàn ở giai đoạn này?”**. Để ứng dụng bảo vệ business intent và xử lý submission trước acceptance; để provider xử lý các nỗ lực delivery sau acceptance; giữ một trạng thái `AMBIGUOUS` cho trường hợp không thể xác nhận. Đó là ranh giới giúp hệ thống Spring Framework Mail có khả năng phục hồi mà không tự tạo vòng lặp gửi trùng.
