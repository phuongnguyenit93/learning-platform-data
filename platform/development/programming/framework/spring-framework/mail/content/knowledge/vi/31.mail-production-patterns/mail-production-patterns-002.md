# Outbox pattern cho yêu cầu gửi mail bền vững

Trong ứng dụng **Spring Framework Mail**, việc gửi email trực tiếp thường được viết rất ngắn:

~~~java
orderRepository.save(order);
mailSender.send(message);
~~~

Tuy nhiên, ở production, **database transaction** và **SMTP submission** là hai tác vụ thuộc hai hệ thống khác nhau. Một transaction database không thể tự rollback email đã được SMTP relay chấp nhận; ngược lại, khi ứng dụng crash sau khi commit dữ liệu mà trước khi gửi SMTP, email có thể không bao giờ được gửi.

**Transactional outbox pattern** giải quyết khoảng trống quan trọng bằng cách **lưu ý định gửi email vào cùng transaction database với thay đổi nghiệp vụ**. Khi transaction commit, business state và mail job cùng tồn tại bền vững. Khi rollback, cả hai không được ghi nhận. Một worker độc lập đọc mail job đã commit, tạo MIME, gửi qua `JavaMailSender` và cập nhật trạng thái.

Outbox không biến SMTP thành một transaction exactly-once. Worker có thể gửi thành công rồi chết trước khi lưu `SUBMITTED`, khiến cùng một job được retry và email bị gửi trùng. Do đó, ngoài việc ghi outbox, hệ thống cần **idempotency, claim/lease, backoff, phân loại lỗi, quản lý attachment, kiểm soát quota, audit và monitoring**.

Bài học này trình bày đầy đủ luồng transactional outbox cho Spring Mail, từ những rủi ro dual-write tới schema, Java code, polling nhiều worker, crash windows và kiểm thử.

## 1. Vấn đề dual-write khi gửi email

Một use case xác nhận đơn hàng:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {

    Order order = orderRepository.require(orderId);

    order.confirm();

    mailService.sendOrderConfirmation(order);
}
~~~

`@Transactional` có thể quản lý thay đổi ở database nhưng **không biến SMTP send thành thao tác tham gia transaction**. Những tình huống có thể xảy ra:

| Tình huống | Hệ quả |
| --- | --- |
| SMTP nhận email, DB commit thất bại | Người nhận thấy xác nhận cho nghiệp vụ chưa commit |
| DB commit rồi JVM crash trước SMTP | Không có email dù nghiệp vụ hoàn tất |
| SMTP chậm trong transaction | Giữ lock DB lâu, tăng latency |
| SMTP timeout sau DATA | Không chắc relay đã nhận chưa |
| HTTP request được retry | Có thể tạo nhiều yêu cầu gửi |
| Provider outage | HTTP có thể fail dù thay đổi nghiệp vụ hợp lệ |

Một cách làm khác cũng chưa an toàn:

~~~text
1. Commit order transaction.
2. Gọi mailSender.send(...).
~~~

Nó có **crash window giữa bước 1 và 2**. Thêm `try/catch` không giúp phục hồi một công việc chưa từng được ghi bền vững.

## 2. Outbox thay đổi kiến trúc như thế nào?

~~~mermaid
flowchart TD
    A["Business request"] --> B["BEGIN transaction"]
    B --> C["Update domain entities"]
    B --> D["INSERT mail_outbox"]
    C --> E["COMMIT atomically"]
    D --> E
    E --> F["Outbox poller / dispatcher"]
    F --> G["Claim job"]
    G --> H["Compose MIME"]
    H --> I["JavaMailSender.send"]
    I --> J["Persist attempt result"]
~~~

Luồng chuẩn:

1. Application service kiểm tra authorization và business rule.
2. Trong **một transaction DB**, lưu business state và một mail outbox row.
3. Commit transaction.
4. Worker tìm job đã đến hạn.
5. Worker claim job để tránh nhiều process cùng làm.
6. Worker dựng MIME bằng sender profile/recipient/template đã phê duyệt.
7. Gửi qua SMTP relay.
8. Lưu trạng thái gửi hoặc lập lịch retry.

Điểm quyết định: **không gọi SMTP bên trong transaction nghiệp vụ**; transaction chỉ ghi ý định gửi. Nếu worker bị dừng nhiều phút, công việc vẫn tồn tại trong outbox DB.

### Outbox bảo đảm gì và không bảo đảm gì?

| Tính chất | Có được không? |
| --- | --- |
| Business state và mail intent commit cùng nhau | Có, nếu cùng transactional resource |
| Intent tồn tại qua JVM restart | Có, khi DB durable |
| Không tạo intent khi transaction rollback | Có |
| Worker có thể retry | Có, khi thiết kế status/scheduler |
| Không tạo duplicate intent từ cùng event | Có thể nhờ unique key |
| SMTP gửi exactly once | **Không tự bảo đảm** |
| Người nhận đã nhận email vào inbox | **Không được bảo đảm** |
| Provider không bao giờ từ chối email | **Không được bảo đảm** |

Outbox là cách tạo **durable work**, không phải phép màu loại bỏ những giới hạn của một external side effect.

## 3. Ba khái niệm: intent, attempt, delivery

**Mail intent** là “cần gửi một thông báo nghiệp vụ”, ví dụ biên nhận thanh toán cho đơn hàng ORD-981.

**Send attempt** là một lần worker cố gửi intent tới relay.

**Delivery outcome** là kết quả cuối ở phía nhận, có thể đến sau qua provider webhook hoặc bounce.

~~~text
Mail intent: payment-receipt-981

Attempt 1:
  temporary SMTP timeout

Attempt 2:
  SMTP relay accepted

Provider feedback:
  deferred -> delivered
~~~

`JavaMailSender.send(...)` trả thành công chỉ chứng tỏ quá trình submission không báo lỗi ở thời điểm đó; không có nghĩa khách hàng đã đọc hoặc email đã vào inbox.

Có thể đặt status `SUBMITTED` thay vì `SENT` để tránh hiểu nhầm với delivered.

## 4. Outbox khác @Async ra sao?

Một cách viết:

~~~java
@Async("mailExecutor")
public void sendEmail(MailCommand command) {
    mailSender.send(buildMessage(command));
}
~~~

`@Async` giúp chuyển việc gửi sang thread khác khi Spring proxy áp dụng đúng, nhưng **task đang chờ trong executor in-memory có thể biến mất khi process chết**.

| Đặc tính | `@Async` đơn thuần | Transactional outbox |
| --- | --- | --- |
| Không chặn HTTP thread | Có thể | Có |
| Job tồn tại qua restart | Không mặc định | Có |
| Atomic với business transaction | Không | Có |
| Retry schedule bền vững | Cần xây thêm | Có thể dùng DB |
| Lịch sử attempts | Không tự có | Có thể lưu |
| Chống duplicate SMTP | Không | Vẫn phải xử lý khả năng trùng |

Có thể dùng `@Async` cho dispatcher, nhưng dữ liệu nguồn phải là mail outbox đã commit, không chỉ là một queued Runnable.

## 5. Outbox khác message broker ra sao?

Broker bền vững giúp queueing, nhưng vẫn có dual-write nếu làm:

~~~text
Commit business DB
  -> Publish Kafka/RabbitMQ event
~~~

và JVM crash sau commit trước publish.

Transactional outbox có thể dùng:

~~~text
A. DB polling:
business DB + outbox -> worker -> JavaMailSender

B. CDC relay:
business DB + outbox -> CDC -> broker -> mail worker
~~~

Trong cả hai, **business change và outbox row phải nằm trong cùng transaction**. CDC hoặc broker thêm khả năng scale nhưng không làm SMTP trở nên exactly-once.

Với số mail vừa phải, database polling thường đơn giản hơn; với throughput lớn có thể cân nhắc relay/broker và consumer idempotency.

## 6. Mô hình trạng thái outbox

~~~mermaid
flowchart TD
    A["PENDING"] --> B["CLAIMED"]
    B --> C{"Send result"}
    C -->|"Accepted"| D["SUBMITTED"]
    C -->|"Temporary"| E["RETRY"]
    C -->|"Permanent"| F["FAILED_PERMANENT"]
    C -->|"Ambiguous"| G["UNKNOWN_OUTCOME"]
    E --> B
    G --> H["Reconcile / retry policy"]
    H --> B
    A --> I["CANCELED"]
~~~

| Status | Ý nghĩa |
| --- | --- |
| `PENDING` | Job đã commit, chưa đến lượt xử lý |
| `CLAIMED` | Một worker đang giữ lease |
| `RETRY` | Job có thể thử lại khi tới `nextAttemptAt` |
| `SUBMITTED` | Relay đã xác nhận submission |
| `UNKNOWN_OUTCOME` | Không thể chắc relay đã nhận chưa |
| `FAILED_PERMANENT` | Không tự retry cùng payload |
| `CANCELED` | Có quyết định nghiệp vụ không gửi nữa |

Một job có thể cần trạng thái `HOLD` hoặc `ACTION_REQUIRED` khi credential/account bị khóa. Tên status do ứng dụng định nghĩa; Spring Mail không áp đặt chúng.

## 7. Ví dụ schema mail_outbox

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    purpose VARCHAR(80) NOT NULL,
    business_event_id VARCHAR(160) NOT NULL,
    idempotency_key VARCHAR(320) NOT NULL,
    recipient_contact_id VARCHAR(160),
    sender_profile_id VARCHAR(160) NOT NULL,
    template_id VARCHAR(160) NOT NULL,
    template_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(40) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
    lease_owner VARCHAR(160),
    lease_token UUID,
    lease_until TIMESTAMP WITH TIME ZONE,
    submitted_at TIMESTAMP WITH TIME ZONE,
    last_failure_category VARCHAR(100),
    last_failure_message VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_mail_outbox_intent UNIQUE (idempotency_key)
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox (status, next_attempt_at, created_at);
~~~

Đây là SQL minh họa theo phong cách PostgreSQL. Kiểu dữ liệu, syntax index và cách claim phải chỉnh theo database thực tế.

Các cột quan trọng:

- `id` định danh job.
- `tenant_id`, `purpose`, `sender_profile_id` bảo vệ routing/quota/audit.
- `business_event_id` liên kết domain event.
- `idempotency_key` giúp chống duplicate enqueue.
- `recipient_contact_id` hoặc recipient snapshot được quản lý theo policy.
- `template_id` và `template_version` giúp giữ nội dung nhất quán.
- `payload_json` chứa thông tin cần thiết, tránh lưu credential.
- `attempt_count`, `next_attempt_at` dùng cho retry.
- `lease_owner`, `lease_token`, `lease_until` giúp multi-worker coordination.

Không đặt SMTP password, reset token plaintext, PDF Base64 hoặc full MIME vào outbox nếu không có yêu cầu bảo mật/retention rất cụ thể.

## 8. Idempotency key phải ổn định theo ý định gửi

Một khóa ví dụ:

~~~java
String key =
        "payment-receipt:"
        + tenantId + ":"
        + paymentId + ":"
        + recipientContactId + ":v1";
~~~

Nếu payment event được nhận hai lần, cùng một intent nên tạo **một outbox row**, thường được bảo vệ bằng unique constraint của DB.

Phân biệt:

- **HTTP retry:** không tạo mail job mới.
- **Duplicate webhook:** không tạo mail job mới.
- **Resend theo yêu cầu:** là intent mới, cần key/version mới.
- **Đổi địa chỉ recipient:** chính sách phải xác định snapshot hay resolve lại.
- **Nhiều recipients:** cần key rõ theo recipient hoặc nhóm nhận.

Không sinh UUID mới làm idempotency key mỗi lần gọi lặp rồi cho rằng đã có dedupe. UUID job ID có thể khác idempotency key.

### Unique outbox key không bảo đảm SMTP đúng một lần

Nếu worker đã gửi nhưng chưa ghi status, job có thể được gửi lại. Idempotency ở tầng **enqueue** và idempotency của **external submission** là hai bài toán khác nhau.

## 9. Ghi business state và outbox cùng transaction

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void confirmOrder(
            UUID orderId,
            AuthenticatedActor actor) {

        Order order = orders.require(orderId);

        order.requireAccess(actor);

        if (order.isConfirmed()) {
            return;
        }

        order.confirm();

        MailOutboxJob job =
                MailOutboxJob.orderConfirmed(
                        order,
                        "order-confirmed:"
                                + order.getId()
                );

        outbox.insertIfAbsent(job);
    }
}
~~~

Các class/method là abstraction do ứng dụng định nghĩa, không phải API mặc định của Spring. Cần đảm bảo business entity và outbox cùng một DB transaction manager/resource.

Khi `@Transactional` commit thành công, cả business state và job cùng tồn tại; khi rollback, cả hai bị rollback.

### Không đặt SMTP vào method này

Transaction business không nên đợi mở kết nối TLS, tạo MIME và nhận SMTP response. Worker sẽ làm phần external I/O sau commit.

## 10. Những lỗi thường gặp với @Transactional

**Self-invocation:** Một method tự gọi `this.transactionalMethod()` có thể bỏ qua Spring proxy transaction ở mô hình proxy-based thông thường.

**REQUIRES_NEW sai chỗ:** Ghi outbox bằng transaction riêng có thể commit dù business transaction rollback, phá vỡ tính atomic cần có.

**Rollback rules:** Checked exception và rollback policy cần hiểu rõ; không tự mặc định mọi exception đều gây rollback như nhau.

**Tài nguyên DB khác nhau:** Nếu business state ở database A và outbox ở database B, hai lời gọi repository không tự tạo một transaction nguyên tử.

**Transaction event listener:** `@TransactionalEventListener(phase = AFTER_COMMIT)` có thể đánh thức worker, nhưng **không thay thế bản ghi outbox**. Nếu chỉ gửi email trong after-commit listener, process vẫn có thể crash giữa DB commit và listener.

## 11. Hai chiều commit và rollback

~~~text
BEGIN
  UPDATE orders SET status = 'CONFIRMED'
  INSERT INTO mail_outbox (...)
COMMIT
~~~

Sau commit, worker có thể gửi dù HTTP request đã kết thúc.

Nếu fail:

~~~text
BEGIN
  UPDATE orders ...
  INSERT INTO mail_outbox (...)
ROLLBACK
~~~

Sau rollback, không có mail intent durable. Đây là ranh giới bảo đảm chính.

Không làm:

~~~text
COMMIT order
  -> INSERT mail_outbox
~~~

vì có khoảng trống crash. Cũng không nên gửi SMTP trước commit chỉ để giảm latency rồi bỏ qua nguy cơ false notification.

## 12. Payload: reference hay snapshot?

Một job có thể lưu:

~~~json
{
  "orderId": "order-981",
  "recipientContactId": "contact-77",
  "receiptObjectKey": "receipts/tenant-42/order-981-v1",
  "currency": "VND"
}
~~~

**Reference-only** giữ payload nhỏ, nhưng worker có thể đọc dữ liệu đã thay đổi sau vài ngày.

**Snapshot** giữ nội dung theo thời điểm event, hỗ trợ audit, nhưng tốn storage và có thể chứa PII.

Một cách cân bằng:

1. Ghi tenant, purpose, event ID và recipient intent.
2. Pin template version và locale khi cần.
3. Lưu immutable snapshot hoặc object reference cho dữ liệu quan trọng.
4. Không lưu secret/token thừa.
5. Đặt payload schema version.
6. Gắn retention và quyền truy cập theo tenant.

Một biên nhận thanh toán cần phản ánh giá tiền/tình trạng chính xác tại thời điểm event; một email marketing lại có thể phải recheck consent ngay trước khi send.

## 13. Template version và nội dung gửi trễ

Giả sử job được tạo với template version 3 nhưng worker xử lý sau outage khi production đã có version 4. Nếu worker luôn render template mới nhất, cùng intent có thể gửi nội dung khác.

~~~text
templateId: ORDER_CONFIRMED
templateVersion: 3
locale: vi-VN
snapshotId: order-snapshot-981
~~~

Với email có yêu cầu kiểm toán, pin template/snapshot giúp kết quả ổn định. Với thông báo ít nhạy cảm, dùng template mới có thể được chấp nhận nếu policy nói rõ.

Dữ liệu người dùng đưa vào HTML phải được escape theo context; outbox không tự ngăn template injection hoặc HTML injection.

## 14. Khi nào worker bắt đầu gửi?

Một dispatcher nên:

1. Tìm job `PENDING` hoặc `RETRY` đến hạn.
2. Claim một batch nhỏ trong transaction ngắn.
3. Commit claim.
4. Gửi SMTP ngoài transaction claim.
5. Ghi kết quả trong transaction ngắn khác.
6. Tiếp tục poll/retry.

~~~mermaid
flowchart LR
    A["Poll due jobs"] --> B["Claim + lease"]
    B --> C["Commit claim"]
    C --> D["Compose MIME"]
    D --> E["SMTP submission"]
    E --> F["Save outcome"]
~~~

Không giữ DB locks xuyên `mailSender.send(...)` vì SMTP có thể rất chậm hoặc timeout.

## 15. Claim với PostgreSQL SKIP LOCKED

Một cách claim batch đa worker:

~~~sql
WITH picked AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY')
      AND next_attempt_at <= now()
    ORDER BY next_attempt_at, created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox m
SET status = 'CLAIMED',
    lease_owner = :worker_id,
    lease_token = :lease_token,
    lease_until = now() + interval '2 minutes',
    updated_at = now()
FROM picked
WHERE m.id = picked.id
RETURNING m.*;
~~~

`:batch_size`, `:worker_id`, `:lease_token` là bind parameters. Một token chung cho batch vẫn có thể dùng khi update result luôn kiểm tra cả job ID và token; token riêng cho mỗi claim giúp tracing rõ hơn.

`FOR UPDATE SKIP LOCKED` cho phép worker khác bỏ qua row đang được một transaction khác lock. Nó không tự giải quyết lease expiry, duplicate SMTP hay fairness.

Lưu ý:

- Chạy query trong DB transaction thực.
- Commit claim nhanh.
- Dùng index phục vụ `status` và `next_attempt_at`.
- Đặt batch size theo capacity.
- Không coi SQL này portable cho mọi database.
- Khi volume lớn, cân nhắc fairness theo tenant và purpose.


## 16. Lease để phục hồi khi worker chết

Nếu worker claim một job rồi process crash, job sẽ kẹt `CLAIMED` mãi nếu không có cơ chế hết hạn.

~~~text
10:00  Worker A claim job-981
10:01  Worker A crash
10:02  leaseUntil đi qua
10:03  Worker B reclaim job-981
~~~

Một hệ thống có thể cho reclaim khi:

~~~sql
WHERE (
    status IN ('PENDING', 'RETRY')
    AND next_attempt_at <= now()
)
OR (
    status = 'CLAIMED'
    AND lease_until < now()
)
~~~

Khi reclaim, phải sinh lease token mới và cập nhật owner. Một worker cũ có thể bị pause lâu, sau đó thức dậy dù lease đã mất.

### Fencing token khi hoàn thành

Chỉ cho phép worker đang giữ lease hợp lệ cập nhật trạng thái:

~~~sql
UPDATE mail_outbox
SET status = 'SUBMITTED',
    submitted_at = now(),
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :job_id
  AND status = 'CLAIMED'
  AND lease_token = :lease_token;
~~~

Nếu số row cập nhật bằng 0, không được coi thao tác mark thành công; job có thể đã được worker khác reclaim.

**Fencing chỉ bảo vệ DB status.** Nó không thu hồi được SMTP message đã được worker cũ gửi. Sau lease expiry, hai worker vẫn có thể cùng thực hiện external send nếu worker cũ chưa dừng.

## 17. Lease duration, heartbeat và timeout

Nếu một email có attachment lớn mất 90 giây để gửi mà lease chỉ 30 giây, một worker khác có thể reclaim khi attempt đầu vẫn hoạt động.

Một lease quá dài lại làm phục hồi sau crash chậm.

Các cách kiểm soát:

- Đặt timeout SMTP có giới hạn.
- Chọn lease phù hợp thời gian gửi dự kiến.
- Gia hạn lease bằng heartbeat cho job dài.
- Dùng token/version để renew có điều kiện.
- Không để một worker giữ job vô hạn.
- Tách report rendering nặng khỏi SMTP attempt khi cần.
- Ghi nhận lease expiration và khả năng gửi trùng.

Heartbeat phải kiểm tra token của worker hiện tại; không cho worker đã mất lease gia hạn hoặc cập nhật trạng thái.

**Lease không tạo exactly-once.** Nó là cơ chế coordination và crash recovery.

## 18. Tách transaction claim khỏi SMTP send

Một scheduler minh họa:

~~~java
@Component
public class MailOutboxScheduler {

    private final MailClaimService claims;
    private final MailAttemptProcessor processor;

    public MailOutboxScheduler(
            MailClaimService claims,
            MailAttemptProcessor processor) {
        this.claims = claims;
        this.processor = processor;
    }

    @Scheduled(
        fixedDelayString =
                "${app.mail.outbox.poll-delay-ms:1000}"
    )
    public void poll() {

        List<ClaimedMailJob> batch =
                claims.claimDueJobs(20);

        for (ClaimedMailJob job : batch) {
            processor.process(job);
        }
    }
}
~~~

Claim service đặt transaction riêng:

~~~java
@Service
public class MailClaimService {

    private final MailOutboxRepository repository;

    public MailClaimService(
            MailOutboxRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<ClaimedMailJob> claimDueJobs(
            int limit) {
        return repository.claimDueJobs(limit);
    }
}
~~~

Worker xử lý **ngoài transaction claim**:

~~~java
@Service
public class MailAttemptProcessor {

    private final JavaMailSender mailSender;
    private final MailComposer composer;
    private final MailAttemptResultService results;

    public MailAttemptProcessor(
            JavaMailSender mailSender,
            MailComposer composer,
            MailAttemptResultService results) {
        this.mailSender = mailSender;
        this.composer = composer;
        this.results = results;
    }

    public void process(ClaimedMailJob job) {

        try {
            MimeMessage message =
                    composer.compose(
                            mailSender,
                            job
                    );

            mailSender.send(message);

            results.markSubmitted(
                    job.jobId(),
                    job.leaseToken()
            );

        } catch (Exception failure) {
            results.recordFailure(
                    job.jobId(),
                    job.leaseToken(),
                    failure
            );
        }
    }
}
~~~

Đây là **khung kiến trúc**, không phải file có thể compile một mình: cần định nghĩa các model/repository/component tương ứng, xử lý null/validation và exception policy. Production result service phải phân loại lỗi, không retry mọi exception giống nhau.

`MailAttemptResultService` nên là bean riêng nếu muốn `@Transactional` proxy hoạt động rõ ràng, tránh self-invocation trong cùng class.

## 19. Dựng MIME từ job đã được phê duyệt

Một composer minh họa:

~~~java
@Component
public class MailComposer {

    private final SenderPolicy senderPolicy;
    private final RecipientResolver recipientResolver;
    private final MailTemplateRenderer renderer;

    public MimeMessage compose(
            JavaMailSender sender,
            ClaimedMailJob job)
            throws MessagingException {

        ApprovedSenderProfile profile =
                senderPolicy.requireAllowed(job);

        String recipient =
                recipientResolver.resolve(job);

        RenderedMail rendered =
                renderer.render(
                        job.templateId(),
                        job.templateVersion(),
                        job.payload()
                );

        MimeMessage mime =
                sender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(
                        mime,
                        true,
                        "UTF-8"
                );

        helper.setFrom(
                profile.fromAddress()
        );

        if (profile.replyToAddress() != null) {
            helper.setReplyTo(
                    profile.replyToAddress()
            );
        }

        helper.setTo(recipient);
        helper.setSubject(rendered.subject());

        helper.setText(
                rendered.plainText(),
                rendered.htmlText()
        );

        mime.setHeader(
                "X-Correlation-Id",
                job.jobId().toString()
        );

        return mime;
    }
}
~~~

`SenderPolicy`, `RecipientResolver`, `RenderedMail` và các type liên quan là abstraction của ứng dụng. Trong hệ thống nhiều tenant, cần chọn đúng `JavaMailSender` qua provider/account registry **trước khi** gọi `createMimeMessage()`. Không lấy SMTP host/credential từ HTTP request chưa xác minh.

Một job tồn tại trong DB không có nghĩa tất cả policy lúc enqueue vẫn hợp lệ:

- Sender domain có thể đã bị revoke.
- Recipient đã unsubscribe.
- Tenant có thể bị suspended.
- Security token có thể đã hết hạn.
- Attachment đã bị xóa theo policy.
- Template/consent thay đổi.

Các kiểm tra cần đúng thời điểm gửi phải được chạy lại.

## 20. Tách correlation, Message-ID và provider ID

Một hệ thống có thể sử dụng:

| Identifier | Vai trò |
| --- | --- |
| Outbox job ID | Định danh ý định gửi |
| Idempotency key | Chặn duplicate enqueue |
| Attempt ID | Định danh một lần submit |
| Correlation ID | Liên kết log/tracing |
| Header `Message-ID` | Hỗ trợ threading/tracing |
| Provider message ID | Đối soát submission/delivery |
| Business event ID | Liên kết domain event |

Thêm header:

~~~java
mime.setHeader(
        "X-Correlation-Id",
        job.getId().toString()
);
~~~

không buộc SMTP provider hay receiving MX loại duplicate. Tương tự, `Message-ID` không phải idempotency guarantee toàn mạng.

Đừng tự kết luận “relay sẽ thấy cùng Message-ID và chỉ phát một email”. Cần dựa vào contract provider nếu có API idempotency riêng; SMTP thông thường không có khóa idempotency phổ quát.

## 21. Crash window sau SMTP acceptance

Đây là giới hạn cốt lõi:

~~~text
1. Worker A claim job-981.
2. Worker A gửi toàn bộ MIME.
3. SMTP server trả 250 OK / accepted.
4. Worker A crash trước UPDATE status = SUBMITTED.
5. Lease hết hạn.
6. Worker B reclaim và gửi lại job-981.
~~~

Người nhận **có thể nhận hai email**, dù outbox chỉ có một row duy nhất.

Nếu cố mark `SUBMITTED` **trước** khi gửi để tránh duplicate:

~~~text
1. DB mark SUBMITTED.
2. JVM crash.
3. SMTP chưa được gọi.
~~~

thì lại có nguy cơ **mất email**.

Vì không thể commit atomically ở cả DB và SMTP, hai thứ tự đều có một crash window. Transactional outbox chủ yếu hỗ trợ **at-least-once processing/submission attempts** theo khả năng retry; không tự bảo đảm exactly-once external effects hoặc inbox delivery.

### Mục tiêu production thực tế

- Không làm mất durable mail intent do crash trước worker.
- Có cơ chế retry và phục hồi job CLAIMED kẹt.
- Giảm nguy cơ duplicate bằng lease/timeouts/observability.
- Chấp nhận và xử lý duplicate nếu nó xảy ra.
- Định nghĩa chính sách cho những email không thể gửi trùng tùy tiện (ví dụ token, thông báo tài chính).
- Không hứa một bảo đảm mà SMTP/provider không có.

## 22. SMTP unknown outcome

Một tình huống khó:

~~~text
Client gửi DATA.
Server đã accept.
Network đứt trước khi client đọc response.
Client nhận timeout.
~~~

Client không biết chắc provider đã nhận hay chưa. Đây là **unknown outcome**, không đơn thuần là thất bại chắc chắn.

Một bộ phân loại có thể là:

~~~java
public enum MailFailureCategory {
    TEMPORARY_TRANSPORT,
    PROVIDER_THROTTLED,
    AUTHENTICATION_FAILED,
    INVALID_SENDER,
    INVALID_RECIPIENT,
    MESSAGE_TOO_LARGE,
    CONTENT_POLICY_REJECTED,
    ATTACHMENT_UNAVAILABLE,
    UNKNOWN_OUTCOME,
    UNEXPECTED_ERROR
}
~~~

Cần xem SMTP reply code, enhanced status, nested exceptions của Jakarta Mail và quy tắc provider, thay vì chỉ kiểm tra `exception.getMessage().contains("timeout")` rồi retry.

| Failure | Hướng xử lý |
| --- | --- |
| Temporary network trước submission | Retry có backoff |
| Rate limit hoặc transient provider error | Retry theo deadline/hint |
| SMTP AUTH sai | Hold/alert/rotate secret |
| Sending domain chưa verified | Không retry nóng, sửa cấu hình |
| Hard message size reject | Giảm payload hoặc link tải |
| Permanent invalid recipient | Fail/suppression theo policy |
| Storage unavailable tạm thời | Retry trong retention window |
| Unknown outcome | Reconcile nếu provider hỗ trợ; retry có xét duplicate |
| Crash sau accepted | Job có thể được gửi lại |

Lỗi không chắc chắn cũng có thể xuất hiện khi gọi provider HTTP API. Provider-specific idempotency token chỉ hữu ích nếu có hợp đồng rõ về việc provider xử lý nó.

## 23. Retry backoff và jitter

Một lỗi provider tạm thời không nên làm hàng nghìn worker retry mỗi 100 ms.

Lịch minh họa:

~~~text
Attempt 1: ngay lập tức
Attempt 2: sau khoảng 30 giây
Attempt 3: sau khoảng 1 phút
Attempt 4: sau khoảng 2 phút
Attempt 5: sau khoảng 4 phút
...
Giới hạn max delay, số attempts và tuổi job.
~~~

Một hàm Java có exponential backoff và jitter:

~~~java
public Duration nextDelay(int attemptCount) {

    int exponent =
            Math.min(
                    Math.max(attemptCount - 1, 0),
                    8
            );

    long baseSeconds =
            Math.min(
                    30L * (1L << exponent),
                    3600L
            );

    long jitterSeconds =
            ThreadLocalRandom.current()
                    .nextLong(0L, 16L);

    return Duration.ofSeconds(
            baseSeconds + jitterSeconds
    );
}
~~~

Đây là policy ví dụ; thực tế phải xác định rõ attempt count tăng lúc claim hay lúc bắt đầu send. Nếu provider công bố retry delay, cần tôn trọng contract đó.

Không retry không giới hạn với lỗi permanent như message quá lớn, địa chỉ From chưa được phép hoặc credential bị thu hồi. Những lỗi đó có thể chuyển `FAILED_PERMANENT` hoặc `ACTION_REQUIRED`.

## 24. Retry khác nhau theo mail purpose

Một OTP chỉ có giá trị vài phút. Một biên nhận thanh toán có thể cần retry dài hơn. Một chiến dịch marketing có thể phải dừng khi campaign window kết thúc.

| Mail purpose | Yêu cầu đặc biệt |
| --- | --- |
| OTP | TTL ngắn; không gửi mã đã hết hạn |
| Password reset | Recheck token validity |
| Payment receipt | Giữ snapshot/audit, hỗ trợ resend |
| Order status | Xem trạng thái hiện tại và policy |
| Marketing | Consent, unsubscribe, suppression, expiry |
| Operations | Escalation nếu mail channel thất bại |

Độ bền vững không có nghĩa “cứ tiếp tục gửi mãi”. Một mail có token đã hết hạn hoặc người nhận đã unsubscribe có thể phải bị cancel theo quy tắc.

## 25. Attachment nên lưu trong durable storage

Không nên đưa file lớn vào outbox payload:

~~~java
public record MailCommand(
        String recipient,
        byte[] reportPdf) {
}
~~~

Nếu PDF được Base64 encode trong JSON và lưu vào DB, bảng outbox nhanh chóng phình lớn, backup nặng và worker dễ giữ nhiều byte[] trong heap.

Một payload nhẹ:

~~~json
{
  "reportId": "report-981",
  "attachmentStorageKey": "reports/tenant-42/report-981-v1",
  "attachmentBytes": 5242880,
  "attachmentVersion": "v1"
}
~~~

Worker lấy resource khi cần:

~~~java
InputStreamSource source = () ->
        attachmentStorage.openReadableStream(
                job.attachmentStorageKey()
        );

helper.addAttachment(
        "report.pdf",
        source,
        "application/pdf"
);
~~~

`attachmentStorage` là API ứng dụng minh họa. Source phải có khả năng mở stream mới mỗi lần Jakarta Mail yêu cầu; `InputStreamResource` bọc một stream đã mở có thể không đáp ứng được việc đọc lại.

Storage cần:

- Có thể đọc từ worker replica khác.
- Tồn tại qua restart và retry window.
- Kiểm tra tenant/authorization.
- Có immutable version/checksum khi nội dung phải cố định.
- Có retention/cleanup không xóa quá sớm.
- Có size/security policy và malware scanning phù hợp.

Local `/tmp` của HTTP request thường không phải durable reference cho outbox job.

## 26. Kích thước MIME, queue memory và backpressure

Một attachment 10 MiB có thể thành MIME part lớn hơn khoảng 13 MiB do Base64/line wrapping, chưa tính header và HTML. Provider có max message size riêng; Spring `JavaMailSender` không tự thay application policy.

Cần giới hạn:

- Kích thước mỗi attachment.
- Tổng raw attachment bytes.
- Số attachment và inline images.
- Estimated MIME bytes.
- Số SMTP connections/worker active.
- Số job claim trước khi thực thi.
- Memory/disk của staging và report renderer.
- Rate limit theo provider/account.

Nếu worker claim 2.000 job nhưng executor queue chỉ có capacity 100, các job còn lại bị giữ lease dù không có worker xử lý. **Claim chỉ trong phạm vi có capacity thực**.

### Queue không phải memory limit

Một queue 100 tasks chứa `byte[]` 20 MiB vẫn có thể giữ xấp xỉ 2.000 MiB raw arrays. Outbox worker nên queue **job IDs/lease tokens**, không queue attachment bytes.

## 27. Gửi một hay nhiều recipient mỗi job?

Hai mô hình:

**Một job nhiều recipients:** ít message hơn, nhưng partial acceptance, To/Cc privacy và retry từng recipient phức tạp.

**Một job mỗi recipient:** dễ áp recipient policy, suppression, tracing, quota, template personalization và retry độc lập.

Đối với transactional notification cá nhân hóa, một job/recipient thường dễ kiểm soát hơn. Nếu gửi nhiều recipients trong một SMTP message, cần hiểu partial send semantics và không cho lộ email người nhận trong To/Cc khi họ không được phép biết nhau.

## 28. Multi-tenant, quota và fair scheduling

Nếu worker luôn chọn job cũ nhất, một tenant có một triệu email marketing có thể làm trễ password reset của tenant khác.

Có thể:

- Tách lane theo purpose.
- Priority class với capacity dành riêng.
- Rate limit theo provider account và tenant.
- Fair scheduling giữa các tenant.
- Quota global theo nhà cung cấp.
- Concurrency riêng cho attachment lớn.
- Giới hạn retry để tránh một nhóm lỗi chiếm hết worker.

Một quota limiter local trên mỗi JVM không đảm bảo global provider quota nếu nhiều replicas cùng dùng account. Cần limiter phân tán hoặc phân chia capacity có chủ đích.

Không để bulk marketing chiếm toàn bộ worker mà security mail phải chờ vô hạn.

## 29. Shutdown và deploy an toàn

Khi pod/service nhận tín hiệu dừng:

1. Ngừng claim job mới.
2. Cho in-flight attempts hoàn tất trong grace period phù hợp.
3. Ghi kết quả nếu còn thời gian.
4. Không mark SUBMITTED trước SMTP.
5. Để các job CLAIMED chưa xong được lease expiry phục hồi.
6. Không xóa attachment còn RETRY.
7. Giữ log/attempt ID để tra cứu.

Graceful shutdown giảm xác suất duplicate, nhưng **không loại bỏ crash window** ngay sau SMTP acceptance.

Liveness probe cấu hình sai gây restart loop có thể làm rất nhiều attempt chưa kịp cập nhật trạng thái. Monitoring và shutdown settings cần đi cùng lease/timeout policy.

## 30. Polling định kỳ và wake-up event

Ví dụ scheduler:

~~~java
@Scheduled(
    fixedDelayString =
            "${app.mail.outbox.poll-delay-ms:1000}"
)
public void run() {
    // Claim batch nhỏ, xử lý từng job,
    // ghi kết quả theo lease token.
}
~~~

Có thể phát local event sau commit để worker thức dậy nhanh hơn. Nhưng event/listener chỉ là tối ưu latency; nếu nó mất do crash, scheduler định kỳ vẫn phải scan outbox.

Không dùng `@TransactionalEventListener(AFTER_COMMIT)` **để thay outbox** bằng lời gọi SMTP không được persist.

## 31. Lịch sử attempts và audit

Một bảng attempts giúp điều tra:

~~~sql
CREATE TABLE mail_send_attempt (
    id UUID PRIMARY KEY,
    mail_job_id UUID NOT NULL,
    attempt_number INTEGER NOT NULL,
    worker_id VARCHAR(160),
    provider_id VARCHAR(100),
    provider_account_id VARCHAR(160),
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    outcome VARCHAR(80),
    failure_category VARCHAR(100),
    provider_message_id VARCHAR(250),
    smtp_reply_code VARCHAR(50)
);
~~~

Một attempt có thể đã bắt đầu và crash, nên `finished_at` có thể null. Cần định nghĩa số attempt tăng ở bước nào cho nhất quán.

Không ghi raw mail content, credential hoặc token vào attempts/error log. Ghi job ID, provider/account, status, reply code và reason category thường đủ cho observability.

## 32. Provider feedback và delivery outcome

Sau khi SMTP relay accept, provider có thể phát:

~~~text
SUBMITTED
  -> DEFERRED
  -> DELIVERED
  -> BOUNCED
  -> COMPLAINED
~~~

Tùy provider, dữ liệu có thể đến từ webhook/API hoặc bounce mailbox; không phải SMTP account nào cũng có đủ tất cả feedback.

Khi nhận event:

1. Verify signature/source và provider account.
2. Parse đúng event version.
3. Map provider message ID tới outbox job/attempt.
4. Dedupe event.
5. Update trạng thái delivery/recipient.
6. Áp suppression đúng tenant/purpose.
7. Audit event không map được hoặc bất thường.

Không tin raw tenant ID do webhook gửi nếu chưa xác minh. Không coi `mailSender.send` thành công là proof delivered.


## 33. Monitoring outbox trong production

Một HTTP API có thể ghi mail intent thành công, nhưng worker bị lỗi và hàng nghìn email không được gửi. Nếu không quan sát backlog và độ tuổi job, người vận hành có thể không biết hệ thống đang ngừng gửi.

| Metric | Ý nghĩa |
| --- | --- |
| `mail_outbox_pending_count` | Số job đang chờ |
| `mail_outbox_retry_count` | Job đang chờ retry |
| `mail_outbox_oldest_pending_age_seconds` | Tuổi job chờ lâu nhất |
| `mail_outbox_claimed_count` | Job đang có lease |
| `mail_outbox_expired_lease_total` | Số lease hết hạn |
| `mail_outbox_submit_total` | Số SMTP attempts theo outcome |
| `mail_outbox_submit_duration_seconds` | Latency submission |
| `mail_outbox_failure_total` | Lỗi theo category |
| `mail_outbox_unknown_outcome_total` | Kết quả SMTP mơ hồ |
| `mail_outbox_permanent_failed_count` | Job cần can thiệp |
| `mail_outbox_provider_throttle_total` | Throttling |
| `mail_outbox_attachment_read_failure_total` | Lỗi đọc attachment |
| `mail_outbox_delivery_feedback_total` | Event delivered/bounced |

Metrics label có thể theo provider, purpose, error category hoặc account class. Không dùng recipient email, subject đầy đủ hoặc token làm label vì privacy và cardinality.

### Alert nên có

- Oldest pending age vượt SLA, đặc biệt với mail bảo mật.
- SMTP AUTH/TLS failure tăng.
- Throttling, retry hoặc UNKNOWN_OUTCOME tăng đột biến.
- Expired lease tăng sau deploy.
- Worker không poll thành công trong một khoảng dài.
- Attachment storage không đọc được.
- Permanent failures tăng.
- Outbox table tăng nhanh và cleanup không chạy.
- Provider feedback không map được tới job.

Đừng chỉ đếm tổng row: một bảng lưu nhiều lịch sử `SUBMITTED` có thể lớn nhưng healthy, còn vài job `PENDING` bị kẹt nhiều giờ lại đáng báo động.

## 34. Correlation end-to-end

Một mail job có thể được theo dõi:

~~~mermaid
flowchart LR
    A["Business event"] --> B["DB transaction"]
    B --> C["Outbox job"]
    C --> D["Worker attempt"]
    D --> E["SMTP provider"]
    E --> F["Delivery feedback"]
~~~

Structured log ví dụ:

~~~text
businessEventId: order-981
mailJobId: mail-981
attemptId: attempt-2
tenantId: tenant-42
purpose: TRANSACTIONAL
senderProfileId: tx-tenant-42
providerId: relay-a
outcome: SUBMITTED
~~~

Nên ghi ID nội bộ và trạng thái, không log toàn bộ MIME, token hay credential.

API có thể trả `202 Accepted` sau khi **outbox đã commit**, với ý nghĩa yêu cầu gửi đã được tiếp nhận bền vững. Không hứa delivered nếu chỉ mới enqueue.

## 35. Retention, cleanup và dữ liệu nhạy cảm

Outbox và attempt history sẽ tăng dần. Cần chính sách:

- Giữ job `SUBMITTED` bao lâu để audit và đối soát feedback?
- Giữ `FAILED_PERMANENT` bao lâu cho vận hành?
- Payload chứa PII được bảo vệ và xóa khi nào?
- Attachment còn cần cho retry hoặc resend không?
- Một file được nhiều job tham chiếu sẽ cleanup thế nào?
- Provider webhook đến muộn có còn mapping ID không?
- Có cần archive historical attempts sang storage rẻ hơn?
- Cleanup có ảnh hưởng transaction/query claim không?

Không xóa row ngay sau SMTP accepted nếu cần đối soát và audit, nhưng cũng không giữ body/recipient PII vô thời hạn.

Một cleanup task nên xét trạng thái cuối, retention, references còn active và quy định dữ liệu theo tenant.

## 36. Khi nào cần tối ưu database outbox?

Những vấn đề thường gặp khi throughput lớn:

- Query due jobs chậm do index không phù hợp.
- Historical rows nhiều.
- Claim contention.
- Retry rows chưa đến hạn bị quét nhiều.
- Cleanup tạo nhiều dead tuples.
- Business writes và SMTP worker tranh I/O.
- Một tenant marketing chiếm phần lớn backlog.

Các lựa chọn:

1. Index theo status và `next_attempt_at`.
2. Batch claim hợp lý, fairness theo tenant/purpose.
3. Archive completed rows.
4. Tách bảng active jobs và history khi có lý do.
5. Partial index/partition nếu database hỗ trợ.
6. CDC relay và broker khi throughput yêu cầu.
7. Rate limit admission và worker.

Không xây kiến trúc CDC phức tạp cho nhu cầu vài trăm email/ngày khi polling DB đáp ứng tốt. Đúng transaction và idempotency quan trọng hơn tối ưu sớm.

## 37. Kiểm thử tính nguyên tử của transaction

Một integration test cần chứng minh:

~~~text
BEGIN
  UPDATE order
  INSERT mail_outbox
COMMIT
=> Cả order update và outbox job cùng tồn tại.

BEGIN
  UPDATE order
  INSERT mail_outbox
ROLLBACK
=> Cả hai đều không tồn tại như thay đổi mới.
~~~

Ví dụ test rollback:

~~~java
@Test
void rollbackDoesNotLeaveMailIntent() {

    assertThrows(
            BusinessRuleException.class,
            () -> service.performFailingOrderFlow(
                    orderId
            )
    );

    assertFalse(
            outboxRepository.existsByBusinessEventId(
                    orderId.toString()
            )
    );
}
~~~

`performFailingOrderFlow` là use case/test seam minh họa. Phải dùng database transaction thực, không chỉ mock repository rồi suy ra atomicity.

Nếu test được bọc `@Transactional` và fixture chưa commit, worker chạy thread khác có thể không đọc thấy job. Khi test dispatcher, cần commit fixture theo contract.

## 38. Kiểm thử duplicate request và idempotency

Một domain event có thể bị nhận hai lần. Test:

~~~java
@Test
void duplicateOrderEventCreatesOneMailJob() {

    service.confirmOrder(orderId, actor);
    service.confirmOrder(orderId, actor);

    assertEquals(
            1L,
            outboxRepository.countByIdempotencyKey(
                    expectedKey
            )
    );
}
~~~

Ngoài kiểm tra tuần tự, phải test race: hai thread/process cùng insert một key. Unique constraint của DB bảo vệ tình huống `SELECT exists` rồi cả hai cùng insert.

Điều này chỉ xác minh **idempotency enqueue**. Nó không chứng minh SMTP không thể gửi trùng sau crash.

Một yêu cầu resend có chủ đích cần intent/key mới và audit/authorization tương ứng.

## 39. Kiểm thử worker với SMTP test server

Có thể dùng GreenMail hoặc Mailpit:

~~~text
Committed mail_outbox row
  -> worker claim
  -> MailComposer
  -> JavaMailSender
  -> test SMTP server
  -> assertions MIME + DB state
~~~

Những assertion cần có:

- Job `PENDING` đến hạn được claim.
- Test server nhận đúng From, To, Subject và correlation ID.
- Relay accepted thì worker ghi `SUBMITTED`.
- Job final không bị poll gửi lại.
- Transient error chuyển `RETRY`, đặt `nextAttemptAt`.
- Permanent error không retry mãi.
- Attachment còn tồn tại và đọc lại được.
- Lease expired có thể reclaim.
- Completion token cũ không được cập nhật DB.
- Mỗi test chỉ kiểm tra message của mình.

Không sử dụng inbox production; test chạy song song nên có SMTP server hoặc correlation namespace riêng.

## 40. Crash window và fault injection

Có thể mô phỏng lỗi ở các ranh giới quan trọng:

| Điểm lỗi | Hành vi cần xác nhận |
| --- | --- |
| Business update trước outbox insert | Rollback không để lại state nửa vời |
| Outbox insert trước commit | Không có job durable nếu rollback |
| Commit trước poll | Job còn chờ |
| Claim trước SMTP | Lease expiry cho phép reclaim |
| SMTP đang gửi | Phân loại transient/unknown |
| SMTP accepted trước status update | Job có thể resend |
| Sau status update | Không poll gửi lại |
| Worker cũ dùng lease token cũ | DB update không thành công |
| File mất trước retry | Lỗi storage được phân loại |
| Credential rotate | Worker dùng approved secret version |

Một test điển hình:

~~~text
Fake SMTP sender ghi nhận một submission.
Mô phỏng worker crash trước markSubmitted.
Lease hết hạn và job được reclaim.
Worker mới gửi lại; fake sender ghi nhận submission thứ hai.
~~~

Kết quả này phản ánh giới hạn thực của hệ thống: DB outbox và SMTP relay không có atomic commit chung. Test không nên che giấu duplicate bằng cách xóa message khỏi capture.

## 41. Kiểm thử nhiều worker claim đồng thời

Hai worker cùng trỏ database test:

~~~text
Worker A claim batch 10
Worker B claim batch 10
~~~

Cần kiểm tra:

- Cùng job không nằm trong hai active leases hợp lệ.
- Worker B có thể claim row khác khi A lock một row.
- Lease hết hạn được reclaim bằng token mới.
- Completion token cũ cập nhật 0 row.
- Job không kẹt CLAIMED vô hạn.
- Job RETRY không được claim trước deadline.
- Batch không vượt execution capacity.
- Job ưu tiên không bị starvation bởi bulk mail.

Mock repository không thể chứng minh transaction lock/`SKIP LOCKED` hoạt động dưới contention thực tế. Nên dùng database test phù hợp production.

## 42. Test retry và thời gian

Không cho test ngủ vài phút chỉ để kiểm tra exponential backoff. Có thể inject `Clock`:

~~~java
Clock testClock =
        Clock.fixed(
                Instant.parse(
                        "2026-11-12T00:00:00Z"
                ),
                ZoneOffset.UTC
        );
~~~

Các case:

- Retry delay tăng theo attempt.
- Jitter nằm trong giới hạn.
- Maximum age/attempts được enforce.
- OTP/password reset token hết hạn thì cancel.
- Recipient unsubscribe trước khi gửi marketing.
- Hard size reject không retry cùng payload.
- Unknown outcome được log và xử lý theo policy.
- Worker không claim trước `nextAttemptAt`.
- Graceful shutdown không nhận job mới.

## 43. Những lỗi thiết kế thường gặp

### 43.1. Gửi SMTP trong @Transactional

SMTP không rollback cùng DB, có thể giữ DB lock trong thời gian network chậm.

### 43.2. Chỉ dùng AFTER_COMMIT listener

Crash sau commit trước listener có thể mất email nếu không có durable outbox.

### 43.3. Chỉ dùng @Async và queue in-memory

Job chưa chạy có thể mất khi JVM restart.

### 43.4. Ghi outbox với REQUIRES_NEW riêng

Outbox có thể commit dù business rollback.

### 43.5. Không có idempotency key

Duplicate HTTP request/webhook tạo nhiều mail intents.

### 43.6. Coi unique key là exactly-once SMTP

Crash sau relay accepted vẫn có thể gửi lại.

### 43.7. Giữ transaction claim xuyên mailSender.send

Gây lock contention và transaction timeout.

### 43.8. Không có lease expiration

Worker crash làm job kẹt.

### 43.9. Không có fencing token

Worker cũ có thể cập nhật status sau khi mất lease.

### 43.10. Lease quá ngắn

Job bị reclaim khi SMTP attempt trước vẫn đang chạy.

### 43.11. Retry mọi loại lỗi giống nhau

Hard size, invalid sender, AUTH failure và timeout cần chính sách khác.

### 43.12. Không backoff/jitter

Provider outage gây retry storm.

### 43.13. Không phân loại unknown outcome

Khó audit và xử lý duplicate.

### 43.14. Lưu PDF Base64 trong outbox

DB và heap phình lớn.

### 43.15. Xóa attachment trước khi retry xong

Worker không tìm được file.

### 43.16. Dùng latest template mà không có version policy

Mail gửi trễ có nội dung khác intent.

### 43.17. Không recheck consent/tenant

Có thể gửi tới người đã unsubscribe hoặc tenant suspended.

### 43.18. Bulk mail chiếm toàn bộ worker

Security mail trễ SLA.

### 43.19. Claim nhiều job hơn executor capacity

Lease hết hạn trước khi send, tăng reclaim/duplicate.

### 43.20. Không monitoring backlog age

Outage lâu mà API vẫn trả accepted.

### 43.21. Coi SUBMITTED là DELIVERED

Relay accepted chưa chắc email vào inbox.

### 43.22. Cleanup outbox quá sớm

Mất audit và provider feedback mapping.

## 44. Câu hỏi tình huống

**Câu 1.** DB commit payment thành công nhưng SMTP outage. Outbox giúp gì?

Job đã commit còn trong DB để worker retry.

**Câu 2.** Transaction rollback sau khi insert outbox trong cùng transaction. Job có tồn tại không?

Không, cả business state và outbox rollback.

**Câu 3.** SMTP accepted rồi worker crash trước mark SUBMITTED. Có thể gửi trùng không?

Có, đây là crash window cơ bản.

**Câu 4.** @Async executor bị kill khi task đang chờ. Job có bền vững không?

Không mặc định. Cần durable outbox.

**Câu 5.** Hai worker cùng poll PENDING, tránh claim trùng ra sao?

Atomic DB claim với locking/conditional update, lease và fencing.

**Câu 6.** Worker cũ mất lease rồi vẫn ghi SUBMITTED. Ngăn bằng gì?

Completion cần kiểm tra lease token, dù external SMTP side effect có thể đã xảy ra.

**Câu 7.** Provider trả hard message too large. Có nên retry y nguyên?

Không, cần giảm size hoặc đổi phương án.

**Câu 8.** SMTP timeout sau DATA có chắc chưa gửi?

Không, có thể là unknown outcome.

**Câu 9.** Password reset job chờ tới lúc token hết hạn. Có nên gửi?

Cần recheck TTL và cancel theo security policy.

**Câu 10.** Attachment nằm ở local /tmp, retry trên pod khác. Có ổn không?

Không chắc; cần durable storage accessible từ worker.

**Câu 11.** Tenant A marketing làm tenant B không nhận mail bảo mật kịp. Khắc phục?

Quota, priority, fair scheduling và reserved capacity.

**Câu 12.** Có thể dùng AFTER_COMMIT listener để đánh thức dispatcher?

Có, nhưng outbox row vẫn cần persist để phòng mất tín hiệu.

**Câu 13.** HTTP trả 202 ngay sau outbox commit nghĩa delivered?

Không, chỉ có nghĩa yêu cầu gửi được tiếp nhận bền vững.

**Câu 14.** Một message nhiều recipients và SMTP partial accept. Làm gì?

Theo dõi từng recipient và tránh retry trùng; cân nhắc tách job/recipient.

**Câu 15.** SMTP credential đã rotate nhưng sender cache cũ vẫn dùng password cũ. Làm gì?

Invalidate/recreate theo credential version.

**Câu 16.** Test rollback chỉ dùng mock repository có chứng minh atomicity không?

Không. Cần integration test DB transaction thực.

**Câu 17.** Message-ID cố định có bảo đảm SMTP exactly-once không?

Không, provider/receiving server không có obligation dedupe phổ quát.

**Câu 18.** Worker claim 500 job khi chỉ còn 5 slots. Rủi ro?

Lease hết hạn trước khi chạy, gây reclaim và có thể duplicate.

## 45. Mô hình ghi nhớ

~~~mermaid
flowchart TD
    A["Business event"] --> B["Authorization + business validation"]
    B --> C["BEGIN transaction"]
    C --> D["Update business state"]
    C --> E["INSERT outbox unique intent"]
    D --> F["COMMIT"]
    E --> F
    F --> G["Worker claim due job"]
    G --> H["Short DB transaction + lease token"]
    H --> I["Resolve sender / recipient / template / storage"]
    I --> J["JavaMailSender.send"]
    J --> K{"SMTP result"}
    K -->|"Accepted"| L["SUBMITTED"]
    K -->|"Transient"| M["RETRY + backoff"]
    K -->|"Permanent"| N["FAILED_PERMANENT"]
    K -->|"Unknown"| O["Reconcile / retry"]
    M --> G
    O --> G
    L --> P["Provider delivery feedback"]
~~~

Những nguyên tắc cần ghi nhớ:

1. **Business state và outbox được ghi trong cùng transaction** để tránh dual-write gap.
2. **Không gửi SMTP trong business transaction** rồi kỳ vọng mail được rollback.
3. **`@Async` không tạo durability**; nguồn sự thật phải là durable job store.
4. **Unique idempotency key chống duplicate enqueue**, không ngăn được mọi duplicate SMTP.
5. **Worker claim atomically**, dùng lease và fencing theo DB.
6. **Commit claim trước network I/O**, không giữ DB locks xuyên SMTP.
7. **Lease có expiration/heartbeat phù hợp** để phục hồi sau crash.
8. **SMTP accepted khác delivered**, timeout có thể là unknown outcome.
9. **Outbox không bảo đảm exactly-once external side effects**, phải chấp nhận/reconcile duplicate.
10. **Retry có backoff, jitter, cutoff và failure classification**, không lặp hard errors vô hạn.
11. **Payload/template/recipient có snapshot/version policy** cho job xử lý trễ.
12. **Attachment dùng durable storage**, outbox giữ reference thay vì Base64 bytes lớn.
13. **Recheck tenant, sender identity, consent và token validity tại send time** theo use case.
14. **Multi-tenant cần fairness/quota**, không để bulk mail làm chậm security mail.
15. **Monitoring backlog age, failures, lease expiry và unknown outcomes** là quan trọng.
16. **Provider feedback phải xác minh và map về đúng job/tenant**.
17. **Test transaction, concurrency và crash windows** bằng database và SMTP test server cô lập.

Trong Spring Framework Mail, transactional outbox là **ranh giới cam kết bền vững giữa quyết định nghiệp vụ và ý định gửi email**. Khi transaction commit, công việc còn đó để tiếp tục; khi rollback, không có ý định gửi tương ứng. Phía sau ranh giới ấy, SMTP vẫn có thể chậm, lỗi, gửi trùng hoặc không chắc kết quả. Một kiến trúc production đúng phải quản lý giới hạn này bằng idempotency, worker lease, retry phù hợp, durable storage, authorization, audit và observability để việc gửi email đáng tin cậy hơn ngay cả khi hạ tầng gặp sự cố.




