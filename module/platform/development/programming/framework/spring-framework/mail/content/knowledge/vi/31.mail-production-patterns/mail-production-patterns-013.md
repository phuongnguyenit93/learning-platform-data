# Thiết kế audit trail không lưu quá mức

Trong một hệ thống **Spring Framework Mail** chạy production, nhóm vận hành cần trả lời các câu hỏi như: *“Vì sao email xác nhận đơn hàng không được gửi?”*, *“Hệ thống có thử gửi thông báo này hai lần không?”*, *“Ai yêu cầu gửi lại?”*, *“SMTP relay đã chấp nhận thông báo ở lần thử nào?”* hoặc *“Có bằng chứng gì cho việc một email bị bounce?”*.

Một cách triển khai thiếu cân nhắc là ghi toàn bộ `MimeMessage`, địa chỉ người nhận, subject, HTML body, attachment, SMTP transcript và stack trace vào database/log ở mỗi bước. Cách đó giúp debug nhất thời nhưng tạo ra kho dữ liệu nhạy cảm khó kiểm soát: OTP, liên kết reset mật khẩu, hóa đơn, thông tin khách hàng, token, tiêu đề và nội dung email có thể tồn tại trong hệ thống audit lâu hơn mục đích ban đầu.

Ngược lại, chỉ ghi `sent=true` cũng không đủ. Khi SMTP timeout sau khi server đã nhận dữ liệu, ứng dụng có thể không biết thư đã được chấp nhận hay chưa. Khi nhiều worker retry, một trạng thái boolean không cho biết lịch sử attempt, nguyên nhân, quyền yêu cầu gửi và bằng chứng kết quả.

**Thiết kế audit trail không lưu quá mức** nghĩa là lưu **đúng sự kiện, đúng định danh, đúng mức chi tiết, đúng thời hạn và đúng người được phép xem**. Audit cần đủ để giải thích hành động và kết quả, nhưng không biến thành bản sao hộp thư hay kho chứa toàn bộ dữ liệu cá nhân.

Bài học hướng dẫn thiết kế audit trong mail pipeline từ domain event đến SMTP/provider delivery, phân biệt audit với log/metric/trace, xây event schema có tính tối thiểu, xử lý correlation và idempotency, thiết kế storage/retention/redaction, bảo vệ tính toàn vẹn, triển khai mẫu với Java/Spring và SQL, kiểm thử cũng như quy trình xử lý sự cố.

## 1. Audit trail trả lời câu hỏi gì?

Audit trail là chuỗi bản ghi cho phép giải thích **một hành động đáng kể đã xảy ra khi nào, do tác nhân hoặc thành phần nào khởi tạo, với đối tượng logic nào, theo quyết định nào và kết quả đã quan sát được là gì**.

Trong email, những câu hỏi quan trọng thường thuộc năm nhóm:

1. **Nguồn gốc:** sự kiện nghiệp vụ, API, lịch định kỳ hay người vận hành nào yêu cầu gửi?
2. **Quyết định:** vì sao thông báo được chấp nhận, từ chối, hủy, hoãn hoặc chuyển route?
3. **Thực thi:** worker/attempt nào thử submit qua SMTP hoặc provider API?
4. **Kết quả:** provider chấp nhận, từ chối rõ ràng, hay kết quả không chắc chắn?
5. **Hậu xử lý:** hệ thống nhận bounce, deferred, delivered hoặc yêu cầu resend/hủy theo policy nào?

Audit trail **không bắt buộc trả lời** “nguyên văn HTML của email là gì?” bằng cách lưu lại từng byte. Nếu cần chứng minh nội dung mẫu, có thể lưu `templateKey`, `templateVersion` và các tham chiếu đã kiểm soát, tùy mục đích và nghĩa vụ lưu giữ.

### Audit không có nghĩa tự động chứng minh giao thư

Ngay cả audit ghi `SMTP_ACCEPTED`, điều đó thường chỉ là bằng chứng next-hop SMTP relay đã chấp nhận submission. Nó không chứng minh thư đã vào inbox, được mở hay được đọc. Nếu provider gửi webhook `delivered`, cần lưu **nguồn và ngữ nghĩa của event đó** thay vì đổi tên nó thành “người dùng đã nhận”.

## 2. Vì sao lưu quá mức là rủi ro production?

Một email có thể chứa:

- Mã OTP và link xác thực/reset mật khẩu.
- Tên, địa chỉ, số điện thoại, hóa đơn và thông tin thanh toán.
- Subject có dữ liệu nghiệp vụ nhạy cảm.
- Địa chỉ người nhận và người gửi.
- File đính kèm chứa hợp đồng, ảnh hoặc báo cáo.
- Header có message identifiers hoặc token định tuyến.
- Nội dung HTML với URL cá nhân hóa.
- Credential hoặc access token do cấu hình/debug log vô tình in ra.
- Metadata cho phép suy đoán hoạt động của người dùng.

Nếu sao chép tất cả vào audit:

- Số bản sao dữ liệu nhạy cảm tăng.
- Xóa dữ liệu theo retention hoặc yêu cầu hợp lệ trở nên phức tạp.
- Nhiều nhóm được cấp quyền xem audit sẽ có quyền đọc nội dung họ không cần.
- Log aggregation, backup và hệ thống phân tích có thể giữ dữ liệu lâu hơn mail service.
- Chi phí lưu trữ và truy vấn tăng theo số attempt/retry.
- Khi sự cố bảo mật xảy ra, phạm vi ảnh hưởng lớn hơn.

Nguyên tắc: **Một trường dữ liệu chỉ nên xuất hiện trong audit nếu có mục đích kiểm toán/vận hành rõ, không có cách ít nhạy cảm hơn để trả lời câu hỏi đó và có chính sách lưu giữ đi kèm.**

## 3. Audit, operational log, metric và distributed trace khác nhau

| Cơ chế | Mục tiêu | Dạng dữ liệu | Ví dụ |
|---|---|---|---|
| **Audit trail** | Chứng minh chuỗi quyết định/hành động đáng kể | Structured event, có retention và kiểm soát truy cập | `MAIL_SUBMISSION_ACCEPTED` |
| **Application log** | Chẩn đoán lỗi và hoạt động kỹ thuật | Dòng log có severity/correlation | SMTP connection timeout ở route X |
| **Metric** | Quan sát khối lượng, tỷ lệ, độ trễ | Counter/Gauge/Timer, tag hữu hạn | `mail_send_attempt_total` |
| **Distributed trace** | Theo dõi đường đi một request qua services | Span/trace ID và thời lượng | API → outbox → worker → provider |

Không cần ghi **toàn bộ log** vào audit. Cũng không cần biến mọi request health check, mỗi lần poll queue hay mỗi câu lệnh SQL thành audit event.

Một hệ thống có thể có:

```text
Business event: OrderPaid
      |
      +-- audit: notification requested
      +-- metric: notification created +1
      +-- trace: order workflow
      |
      v
SMTP attempt
      |
      +-- audit: attempt started / accepted / rejected / unknown
      +-- metric: attempts, latency, result
      +-- log: classified technical diagnostic
```

Các mục đích khác nhau dẫn đến chính sách retention và quyền truy cập khác nhau.

## 4. Chọn đúng sự kiện cần audit

Không phải mọi thao tác đều xứng đáng là một sự kiện audit bền vững.

| Sự kiện | Nên audit? | Vì sao |
|---|---|---|
| Yêu cầu gửi được chấp nhận bền vững | Có | Chứng minh nguồn gốc logical notification |
| Yêu cầu bị từ chối bởi policy/consent | Tùy yêu cầu, thường nên có tổng quát | Giải thích quyết định không gửi |
| Worker claim job | Tùy mức điều tra | Có thể lưu ở processing/attempt state thay vì event lịch sử dài hạn |
| SMTP attempt bắt đầu | Thường có với email quan trọng | Phân biệt job đã thử hay chỉ đang chờ |
| SMTP submission được chấp nhận | Có | Bằng chứng kết quả submission |
| SMTP known rejection | Có | Phân loại lỗi và quyết định retry |
| SMTP outcome không chắc chắn | Có | Điều tra duplicate risk |
| Provider bounce/delivery event | Có khi là tín hiệu nghiệp vụ cần giữ | Theo dõi kết quả downstream |
| Người vận hành yêu cầu resend/cancel | Có | Hành động có quyền và tác động thực |
| Thay đổi sender/route policy | Có, thuộc audit cấu hình | Giải thích lý do thay đổi hành vi |
| Mỗi lần scheduler thức dậy | Thường không cần audit từng tick | Dùng metric/log thay thế |
| Mỗi lần kiểm tra SMTP health | Thường không | Dùng health/metric, tránh event noise |
| Mỗi header/attachment được đọc | Thường không | Không tạo audit thành bản sao message |
| Mọi lần retry scheduler kiểm tra `nextAttemptAt` | Không | Không mang ý nghĩa business mới |

**Tối thiểu hóa sự kiện** quan trọng không kém tối thiểu hóa trường dữ liệu.

## 5. Ba lớp định danh cần giữ rõ

Một thiết kế gửi mail thường có:

1. **Business occurrence/source event**: sự kiện nghiệp vụ sinh nhu cầu thông báo.
2. **Logical notification**: yêu cầu gửi một thông báo cụ thể theo contract.
3. **Submission attempt**: một lần worker thử submit qua SMTP/provider.

Ví dụ:

```text
sourceEventId   = order-paid-801
notificationId  = notif-302
attemptId       = attempt-302-02
providerRoute   = transactional-primary
```

Một notification có thể có nhiều attempts. Một event nghiệp vụ có thể sinh nhiều notifications theo nhiều recipients.

Không dùng một ID duy nhất cho mọi cấp rồi suy ra không có retry/duplicate.

### Message-ID và provider ID không giống notification ID

- `notificationId`: khóa logic do ứng dụng tạo.
- `attemptId`: khóa cho một lần submit.
- MIME `Message-ID`: header theo chuẩn email, có thể được tạo bởi ứng dụng/JavaMail.
- `providerMessageId`: định danh provider công bố, có thể không có hoặc có semantics riêng.
- `providerEventId`: định danh event webhook, nếu provider cung cấp.

Một audit event nên lưu các ID **chỉ khi cần correlation**, không tự giả định chúng có cùng phạm vi hoặc cùng nghĩa.

## 6. Event schema tối thiểu nên có gì?

Một event audit gửi mail có thể gồm:

| Trường | Vai trò | Lưu ý |
|---|---|---|
| `auditEventId` | Định danh bản ghi audit | UUID/ULID hoặc ID duy nhất do server tạo |
| `schemaVersion` | Version contract audit | Hỗ trợ consumer/migration |
| `eventType` | Loại hành động từ danh mục hữu hạn | Không nhận arbitrary text |
| `occurredAt` | Khi hành động xảy ra | UTC/Instant |
| `recordedAt` | Khi event được lưu | Giúp phát hiện độ trễ |
| `notificationId` | Tham chiếu logical notification | Không chứa email/PII |
| `attemptId` | Tham chiếu attempt nếu có | Nullable theo loại event |
| `sourceType` | API, schedule, domain event, manual | Enum/hữu hạn |
| `actorType` | USER, SERVICE, SYSTEM, OPERATOR | Không dùng username tự do làm taxonomy |
| `actorRef` | Định danh đã giảm nhạy cảm/được phân quyền | Có thể nullable hoặc pseudonym |
| `providerRoute` | Route/provider nội bộ | ID ổn định, không phải hostname/credential |
| `outcome` | ACCEPTED, REJECTED, UNKNOWN... | Đúng ngữ nghĩa |
| `reasonCode` | Mã lý do hữu hạn | Không lưu raw exception |
| `policyVersion` | Phiên bản quyết định/consent policy | Khi cần tái hiện lý do |
| `correlationId` | Kết nối log/trace nghiệp vụ | Không chứa thông tin cá nhân |
| `evidenceRef` | Tham chiếu tới bằng chứng hạn chế quyền, nếu có | Không phải raw body |

Không phải **mọi event phải chứa tất cả field**. Một event `MAIL_REQUESTED` không cần `attemptId`. Một `MAIL_RESEND_AUTHORIZED` có thể cần `actorRef` và `authorizationContextRef` nhưng không cần SMTP response code.

Cách thiết kế tốt là **event-specific allowlist** thay vì một JSON không có giới hạn với mọi giá trị do caller cung cấp.

## 7. Ví dụ JSON audit event không chứa nội dung thư

```json
{
  "auditEventId": "ae-4d73",
  "schemaVersion": 1,
  "eventType": "MAIL_SUBMISSION_ACCEPTED",
  "occurredAt": "2026-11-12T08:05:10Z",
  "recordedAt": "2026-11-12T08:05:11Z",
  "notificationId": "notif-302",
  "attemptId": "attempt-302-02",
  "sourceType": "DOMAIN_EVENT",
  "actorType": "SERVICE",
  "providerRoute": "transactional-primary",
  "outcome": "SMTP_ACCEPTED",
  "reasonCode": null,
  "correlationId": "corr-801",
  "templateKey": "order-confirmation",
  "templateVersion": "v7"
}
```

Bản ghi **không chứa** recipient email, subject thực tế, HTML body, attachment bytes, SMTP password hoặc raw authentication response. Muốn tìm recipient, hệ thống có thể truy vấn bản ghi notification được phân quyền, có retention khác, thay vì lặp trường này trong mọi audit event.

### Không “ẩn” dữ liệu nhạy cảm trong correlation ID

Một `correlationId` như `john@example.com-20261112` vẫn là dữ liệu có thể xác định danh tính dù được đặt tên là ID. Dùng opaque/random identifier, không nhúng email, số điện thoại, mã đơn hàng có thể đoán hoặc token.

## 8. Thực hiện data classification trước khi định schema

Có thể chia dữ liệu của mail pipeline thành bốn nhóm:

| Nhóm | Ví dụ | Cách xử lý audit |
|---|---|---|
| **Operational metadata** | Event type, time, outcome, route alias | Có thể lưu nếu cần |
| **Pseudonymous reference** | Internal userRef/recipientRef | Hạn chế quyền, retention cụ thể |
| **Personal/sensitive content** | Email address, subject, body, invoice details | Tránh lưu trong audit; chỉ tham chiếu storage riêng |
| **Secrets/high-risk data** | SMTP password, OAuth token, OTP, reset token | Không đưa vào audit/log |
 
Một `recipientRef` có thể vẫn là dữ liệu cá nhân nếu hệ thống khác ánh xạ được nó tới một con người. **Pseudonymization không phải anonymization**; cần bảo vệ cả bảng ánh xạ, quyền truy vấn và backup.

Nếu một trường không phục vụ audit use case nào được chấp thuận, bỏ nó khỏi schema ngay từ đầu.

## 9. Audit trail không nên lưu full MimeMessage

Một anti-pattern:

```java
// KHÔNG NÊN: ghi lại toàn bộ MIME trong audit.
ByteArrayOutputStream buffer =
        new ByteArrayOutputStream();

mimeMessage.writeTo(buffer);

auditRepository.save(
        new AuditRecord(
                notificationId,
                buffer.toByteArray()
        )
);
```

Rủi ro:

- Lưu toàn bộ body và attachment.
- Có thể giữ OTP, URL cá nhân hóa và metadata nhạy cảm.
- Tăng lượng dữ liệu theo số lần retry.
- Khi xuất audit cho đội vận hành, nội dung email bị lộ.
- Tạo thêm nơi phải thực thi xóa dữ liệu và retention.
- Với message lớn, gây áp lực memory/DB/storage.

**Audit chỉ cần bằng chứng rằng message đã được chuẩn bị hoặc submit theo contract**, không cần tự biến thành một mailbox thứ hai.

Nếu vì nghĩa vụ cụ thể phải lưu bản gốc message, hãy thiết kế **evidence store riêng** với encryption, retention, access approval, integrity và deletion policy; audit chỉ chứa `evidenceRef` có quyền, không chứa raw MIME.

## 10. Subject có thật sự cần lưu không?

Subject có vẻ nhỏ, nhưng có thể chứa:

```text
Đơn hàng #801 của Nguyễn Văn A
Mã xác minh: 123456
Thông báo về khoản vay ...
Kết quả khám ...
```

Lưu subject raw trong audit có thể rò rỉ PII hoặc nội dung nhạy cảm. Thay vì vậy, lưu:

- `notificationType`: `ORDER_CONFIRMATION`.
- `templateKey`: `order-confirmation`.
- `templateVersion`: `v7`.
- `locale` khi cần giải thích formatting.
- `renderResult` hoặc `renderErrorCode` nếu đã được chuẩn hóa.
- `businessRef` đã kiểm soát, nếu audit use case cần liên kết.

Không suy ra rằng có template version là luôn có thể tái tạo byte-for-byte email: dynamic variables, attachment, thời điểm render, timezone và template engine version có thể thay đổi. Nếu nghiệp vụ cần chứng minh **nội dung chính xác đã gửi**, phải có evidence retention riêng theo yêu cầu cụ thể.

## 11. Địa chỉ email người nhận: lưu ở đâu?

Recipient email cần cho việc gửi, nhưng không nhất thiết cần lặp trong audit events.

Một thiết kế:

```text
mail_notification
  notification_id
  recipient_ref
  encrypted_destination_ref
  status
  retention_class

mail_audit_event
  audit_event_id
  notification_id
  event_type
  outcome
  occurred_at
```

Bản ghi notification có thể được phân quyền cao hơn audit. Khi operator tra cứu theo `notificationId`, application service kiểm tra quyền rồi trả thông tin cần thiết.

Nếu một tác vụ điều tra yêu cầu xem địa chỉ cụ thể, có thể cung cấp qua **just-in-time privileged lookup**, với audit riêng cho hành động truy cập dữ liệu.

Không áp dụng quy tắc “mọi người được xem audit cũng được xem recipient address”.

## 12. Có nên hash email address để tìm kiếm không?

Một số hệ thống cần tìm audit theo recipient mà không lưu địa chỉ raw.

Hash không khóa như SHA-256(email) **không tự bảo đảm ẩn danh**: không gian địa chỉ phổ biến có thể bị thử đoán bằng dictionary. Nếu muốn lập index tra cứu có bảo vệ hơn, có thể cân nhắc **HMAC với khóa bí mật** trên giá trị email đã chuẩn hóa theo policy.

Nhưng cần hiểu:

- HMAC vẫn tạo identifier ổn định, có thể liên kết hoạt động của cùng recipient.
- Ai có khóa/khả năng tra cứu vẫn có thể nhận diện đối tượng.
- Khóa cần quản lý trong KMS/secret manager và luân chuyển.
- Chuẩn hóa email cần thận trọng: domain thường không phân biệt chữ hoa/chữ thường; local-part có semantics tùy hệ thống. Không áp dụng quy tắc xóa dấu chấm/alias kiểu nhà cung cấp một cách tùy tiện.
- Lookup HMAC có thể không phù hợp nếu dữ liệu bị xóa hoặc khóa bị luân chuyển.
- Ngay cả HMAC vẫn có thể là dữ liệu cá nhân theo ngữ cảnh.

**Không dùng hash như lời khẳng định rằng audit không còn chứa dữ liệu cá nhân.**

### Ví dụ pseudonymous lookup

```text
normalizedDestination
        |
        v
HMAC(keyId, canonicalizedAddress)
        |
        v
recipientLookupToken
```

Audit có thể giữ lookup token khi có use case cụ thể; nhưng phương án mặc định vẫn là **giữ opaque recipientRef ở notification store** và phân quyền truy vấn, vì càng ít index định danh càng ít rủi ro.

## 13. Mã lỗi nên được chuẩn hóa, không ghi raw exception

Một exception SMTP có thể chứa hostname, địa chỉ người nhận, provider response, username hoặc dữ liệu khác. Không nên đưa toàn bộ `exception.getMessage()` vào audit event.

Thiết kế taxonomy:

```java
public enum MailAuditReason {
    AUTHENTICATION,
    AUTHORIZATION,
    INVALID_RECIPIENT,
    INVALID_SENDER,
    INVALID_MESSAGE,
    RATE_LIMITED,
    CONNECTION,
    TLS,
    TIMEOUT,
    PROVIDER_UNAVAILABLE,
    POLICY_SUPPRESSED,
    EXPIRED,
    UNKNOWN
}
```

Khi lưu:

```json
{
  "eventType": "MAIL_SUBMISSION_REJECTED",
  "notificationId": "notif-302",
  "attemptId": "attempt-302-01",
  "reasonCode": "RATE_LIMITED",
  "providerRoute": "transactional-primary"
}
```

Thông tin debug kỹ thuật chi tiết hơn có thể nằm trong **operational log ngắn hạn**, vẫn cần redaction và giới hạn truy cập. Nếu cần lưu raw provider response làm bằng chứng đặc biệt, dùng evidence store có retention và approval, không trộn với audit mặc định.

### SMTP 4xx/5xx cần ngữ cảnh

Một mã SMTP có thể giúp phân loại nhưng không nên quyết định audit outcome bằng quy tắc “4xx = mọi lúc retry, 5xx = mọi lúc fail vĩnh viễn”. Cần xét lệnh SMTP, stage, extended status code và cause chain nếu có.

## 14. State machine cho notification và attempt

Tránh chỉ lưu `sent=true/false`.

Một model:

```text
NOTIFICATION
  CREATED
    |
    +--> SUPPRESSED_BY_POLICY
    +--> CANCELLED
    +--> EXPIRED
    |
    v
  PENDING
    |
    v
  PROCESSING
    |
    +--> SUBMISSION_ACCEPTED
    +--> RETRY_SCHEDULED
    +--> FAILED_FINAL
    +--> UNKNOWN_REVIEW
```

Từng **attempt** có lịch sử riêng:

```text
ATTEMPT_STARTED
     |
     +--> SMTP_ACCEPTED
     +--> KNOWN_REJECTED
     +--> UNKNOWN
```

Một audit trail nên ghi lại **chuyển trạng thái có ý nghĩa** và bằng chứng, không bắt buộc lưu mọi lần đọc polling từ database.

### Kết quả không chắc chắn là sự thật cần audit

Nếu SMTP đã nhận DATA nhưng response cuối bị mất, worker có thể không biết chắc message đã accepted hay chưa. Audit event `MAIL_SUBMISSION_UNKNOWN` nên giữ nguyên sự không chắc chắn này; không tự biến thành `FAILED` để tiện retry.

## 15. Accepted, delivered và read khác nhau

| Trạng thái | Điều đã biết | Điều chưa chắc |
|---|---|---|
| `REQUESTED` | Có yêu cầu nghiệp vụ | Chưa chắc đã lưu bền vững nếu chưa commit |
| `QUEUED` | Yêu cầu được lưu/nhận theo contract | Chưa gửi SMTP |
| `SMTP_ACCEPTED` | Next-hop SMTP transport xác nhận submission | Chưa chứng minh inbox delivery |
| `DELIVERED_EVENT` | Provider báo delivered theo định nghĩa của họ | Không nhất thiết inbox hay người dùng đọc |
| `BOUNCED_EVENT` | Provider báo bounce | Cần xét loại/per-recipient |
| `OPEN_EVENT` | Tracking pixel hoặc tín hiệu tương tự nếu bật | Có thể bị chặn hoặc kích hoạt bởi proxy; không chứng minh người thật đọc |

**Audit không được đổi tên bằng chứng thành kết luận mạnh hơn.** Khi trình bày cho người vận hành hoặc báo cáo, cần giữ nghĩa của nguồn trạng thái.

Nếu sản phẩm không dùng open tracking, không cần thêm trường/event “open” chỉ vì một provider có hỗ trợ.

## 16. Audit trail trong nhiều recipient

Một `MimeMessage` có thể gửi tới nhiều người nhận, nhưng kết quả có thể không đồng nhất: SMTP server có thể chấp nhận một số recipients và từ chối số khác.

Nếu nghiệp vụ cần truy vết từng người, cân nhắc:

- Một logical notification per recipient; hoặc
- Một batch notification với child recipient submission records.

Không gắn một event `MAIL_ACCEPTED` chung cho toàn bộ batch khi transport đã báo partial acceptance.

Dữ liệu tối thiểu per-recipient có thể là:

```text
notificationId
recipientRef
attemptId
recipientOutcome
errorCategory
```

Tránh lặp địa chỉ email raw trong mọi event; sử dụng internal refs và những bảng được phân quyền.

## 17. Audit được ghi khi nào để không sai sự thật?

Hai tình huống dễ nhầm:

1. **Ghi event `MAIL_REQUESTED` trước khi outbox commit**: nếu transaction rollback, audit vẫn tuyên bố có một request đã được chấp nhận.
2. **Gửi SMTP trước khi ghi attempt**: nếu process chết, có thể không còn bằng chứng rằng đã thực hiện một lần gửi.

Giải pháp không phải một transaction khổng lồ bao cả database và SMTP. Thay vào đó, ghi sự kiện theo đúng **transaction boundary có thể bảo đảm**.

Một chiến lược:

```text
Transaction A:
  insert notification
  insert audit event NOTIFICATION_QUEUED
COMMIT

Transaction B:
  claim job
  insert attempt STARTED
COMMIT

Outside DB transaction:
  send SMTP

Transaction C:
  record outcome for attempt
  insert audit event matching outcome
COMMIT
```

Nếu process chết sau SMTP trước transaction C, attempt vẫn tồn tại ở trạng thái bắt đầu hoặc không rõ kết quả; recovery phải xử lý thay vì tự tuyên bố never sent.

## 18. Transactional outbox giúp audit và event dispatch nhất quán

Giả sử nghiệp vụ tạo đơn hàng, đồng thời muốn gửi email:

```text
Transaction:
  Save order
  Insert mail notification PENDING
  Insert minimal MAIL_REQUESTED audit event
COMMIT
```

Nếu transaction rollback, không có notification/audit event được commit. Worker chỉ xử lý bản ghi `PENDING` sau commit.

Nếu audit event còn phải xuất sang một hệ thống audit tập trung, dùng **transactional outbox cho việc publish audit**:

```text
Business DB transaction
    |
    +-- notification row
    +-- audit event row
    +-- audit publication outbox row
    |
    v
COMMIT
    |
    v
Audit publisher retries until event handed off
```

Không cố bắt một transaction JDBC bao luôn SMTP và hệ thống audit remote. SMTP không tham gia transaction database và lỗi network có thể khiến outcome không chắc chắn.

### Đồng bộ audit nội bộ với external audit store

Nếu ứng dụng lưu audit nội bộ rồi đẩy sang kho tập trung, cần định nghĩa:

- Nguồn sự thật nào là authoritative?
- Event ID nào dùng để deduplicate?
- Kho tập trung giữ event bao lâu?
- Khi audit publisher chậm, ứng dụng có chặn mail không?
- Làm sao phát hiện audit lag?
- Ai có quyền xem các loại event?
- Cơ chế reconcile giữa outbox và audit store?

Không báo “audit đã được ghi ở kho trung tâm” nếu chỉ mới enqueue để publish.

## 19. Schema SQL tối thiểu

Ví dụ giản lược:

```sql
CREATE TABLE mail_audit_event (
    audit_event_id      VARCHAR(64) PRIMARY KEY,
    schema_version      INTEGER NOT NULL,
    event_type          VARCHAR(64) NOT NULL,
    occurred_at         TIMESTAMP NOT NULL,
    recorded_at         TIMESTAMP NOT NULL,
    notification_id     VARCHAR(64),
    attempt_id          VARCHAR(64),
    actor_type          VARCHAR(24),
    actor_ref           VARCHAR(128),
    source_type         VARCHAR(32),
    provider_route      VARCHAR(64),
    outcome_code        VARCHAR(48),
    reason_code         VARCHAR(48),
    correlation_id      VARCHAR(128),
    policy_version      VARCHAR(64)
);

CREATE INDEX ix_mail_audit_notification_time
    ON mail_audit_event (
        notification_id,
        occurred_at
    );

CREATE INDEX ix_mail_audit_attempt
    ON mail_audit_event (attempt_id);
```

Đây là schema minh họa. Kiểu thời gian có time zone, retention partition, tenant scope, uniqueness và row-level access cần tùy database/kiến trúc.

**Không có cột** `subject`, `html_body`, `smtp_password`, `access_token`, `mime_bytes` hoặc `attachment_blob`. Nếu một use case thật sự yêu cầu loại dữ liệu đó, cần evidence store có purpose, legal basis/retention và quyền riêng, không tùy tiện thêm cột vào bảng audit chung.

### Có cần foreign key không?

Foreign key tới notification giúp integrity nếu hai bảng có cùng retention. Nhưng nếu notification PII bị xóa sớm hơn audit, một ràng buộc cứng có thể cản deletion. Cân nhắc dùng opaque reference và chính sách tombstone/xóa ánh xạ khi cần, thay vì giữ dữ liệu chỉ để foreign key còn hợp lệ.

## 20. Java domain model cho audit event

Một kiểu bất biến, không có trường body/recipient raw:

```java
import java.time.Instant;

public record MailAuditEvent(
        String auditEventId,
        int schemaVersion,
        MailAuditEventType eventType,
        Instant occurredAt,
        Instant recordedAt,
        String notificationId,
        String attemptId,
        MailActorType actorType,
        String actorRef,
        String sourceType,
        String providerRoute,
        String outcomeCode,
        MailAuditReason reasonCode,
        String correlationId,
        String policyVersion
) {
}
```

Enum:

```java
public enum MailAuditEventType {
    NOTIFICATION_QUEUED,
    NOTIFICATION_SUPPRESSED,
    NOTIFICATION_CANCELLED,
    ATTEMPT_STARTED,
    SUBMISSION_ACCEPTED,
    SUBMISSION_REJECTED,
    SUBMISSION_UNKNOWN,
    RETRY_SCHEDULED,
    NOTIFICATION_EXPIRED,
    PROVIDER_BOUNCED,
    PROVIDER_DELIVERED,
    MANUAL_RESEND_AUTHORIZED,
    MAIL_ROUTE_POLICY_CHANGED
}

public enum MailActorType {
    USER,
    SERVICE,
    SYSTEM,
    OPERATOR
}
```

Đây là model minh họa. Không nhất thiết mọi enum dùng cùng một bảng; audit của thay đổi cấu hình có thể có schema riêng và retention khác.

### Vì sao record/enum có ích?

- Schema được ràng buộc hơn một `Map<String,Object>` không kiểm soát.
- Giảm nguy cơ vô tình thêm raw MIME vào audit payload.
- Event types có danh mục hữu hạn, dễ index.
- Có thể viết validation theo từng event.
- Hỗ trợ versioning có chủ đích.

Đặc biệt không nên có phương thức `audit(Object payload)` mặc định serialize toàn bộ object nghiệp vụ vào JSON, vì object có thể chứa password hoặc email body ngoài dự kiến.

## 21. Một service audit nhận event có cấu trúc

```java
import java.time.Clock;
import java.util.UUID;

public final class MailAuditService {

    private final Clock clock;
    private final MailAuditRepository repository;

    public MailAuditService(
            Clock clock,
            MailAuditRepository repository
    ) {
        this.clock = clock;
        this.repository = repository;
    }

    public void submissionAccepted(
            String notificationId,
            String attemptId,
            String providerRoute,
            String correlationId
    ) {
        var now = clock.instant();

        repository.insert(
            new MailAuditEvent(
                UUID.randomUUID().toString(),
                1,
                MailAuditEventType.SUBMISSION_ACCEPTED,
                now,
                now,
                notificationId,
                attemptId,
                MailActorType.SERVICE,
                null,
                "MAIL_WORKER",
                providerRoute,
                "SMTP_ACCEPTED",
                null,
                correlationId,
                null
            )
        );
    }
}
```

`MailAuditRepository` là interface do ứng dụng tự triển khai. Trong production có thể cần `Clock`, `IdGenerator` và transaction service được inject để kiểm soát test và idempotency.

Đoạn code cố ý **không truyền `MimeMessage` vào audit service**. Khi cần thay đổi lý do audit, thay đổi API event có chủ đích, không đưa cả object mail vào hệ thống logging.

## 22. Ghi audit cùng trạng thái trong transaction phù hợp

Ví dụ service xử lý kết quả một attempt:

```java
import org.springframework.transaction.annotation.Transactional;

public class MailAttemptFinalizer {

    private final MailAttemptRepository attempts;
    private final MailAuditRepository audit;

    public MailAttemptFinalizer(
            MailAttemptRepository attempts,
            MailAuditRepository audit
    ) {
        this.attempts = attempts;
        this.audit = audit;
    }

    @Transactional
    public void markAccepted(
            String attemptId,
            String claimToken,
            AcceptedEvidence evidence
    ) {
        int updated = attempts.markAcceptedIfOwned(
                attemptId,
                claimToken,
                evidence
        );

        if (updated != 1) {
            throw new IllegalStateException(
                    "Attempt ownership not valid"
            );
        }

        audit.insert(
                AuditEvents.submissionAccepted(
                        attemptId,
                        evidence
                )
        );
    }
}
```

`MailAttemptRepository`, `AcceptedEvidence` và `AuditEvents` là các abstraction minh họa.

Tính chất cần giữ:

- Update trạng thái và insert audit **thuộc cùng local transaction** khi có thể.
- `claimToken` giúp ngăn stale worker ghi đè kết quả sau khi mất lease.
- Nếu update 0 row, không ghi event accepted giả.
- Event insert thất bại thì transaction phải xử lý nhất quán theo policy.
- Không thực hiện SMTP network I/O trong transaction này.
- Nếu audit ở external system, sử dụng publication outbox thay vì giả định transaction phân tán.

### Không chạy SMTP trong transaction finalize

Vì SMTP là side effect bên ngoài, gọi `send` giữa `BEGIN` và `COMMIT` không tạo atomicity. Rollback DB không “unsend” được email.

## 23. Audit và idempotency

Mỗi attempt có thể bị worker ghi lại kết quả nhiều lần do retry update, webhook duplicate hoặc message broker redelivery. Audit trail phải tránh **đếm sự kiện vật lý lặp thành nhiều hành động nghiệp vụ**.

Có thể dùng một semantic dedupe key:

```text
attemptId + auditEventType + outcomeVersion
```

hoặc ID của source event gốc có uniqueness trong database.

Ví dụ:

```sql
CREATE TABLE mail_audit_dedupe (
    source_system      VARCHAR(64) NOT NULL,
    source_event_id    VARCHAR(128) NOT NULL,
    audit_event_id     VARCHAR(64) NOT NULL,
    PRIMARY KEY (source_system, source_event_id)
);
```

Đây là một lựa chọn minh họa. Contract phải định nghĩa rõ `sourceEventId` là ID của **event**, không phải notification ID; cùng một notification có thể hợp lệ có nhiều attempts/events.

### Không dedupe nhầm các sự kiện hợp lệ

Một attempt có thể có:

- `ATTEMPT_STARTED`.
- `SUBMISSION_UNKNOWN`.
- Sau reconciliation có event bổ sung `SUBMISSION_RECONCILED`.

Không nên ghi đè/xóa sự kiện cũ như thể không bao giờ có uncertainty. Có thể dùng event sửa sai/correction liên kết event gốc.

Đồng thời không tạo `SUBMISSION_ACCEPTED` lần hai cho cùng attempt chỉ vì webhook trả về trạng thái delivered.

## 24. Audit sự kiện từ provider webhook

Khi nhận webhook bounce/delivered:

1. Xác thực nguồn theo contract provider.
2. Kiểm tra signature/timestamp nếu được hỗ trợ.
3. Giới hạn payload size, parsing và schema.
4. Xác định `providerEventId` hoặc source event dedupe key.
5. Tìm đúng provider route, attempt, notification và recipient.
6. Lưu event có ý nghĩa và trạng thái theo policy.
7. Không dùng raw webhook body làm audit record mặc định.
8. Bảo vệ việc event đến trùng hoặc sai thứ tự.

Ví dụ bản ghi:

```json
{
  "eventType": "PROVIDER_BOUNCED",
  "notificationId": "notif-302",
  "attemptId": "attempt-302-02",
  "providerRoute": "transactional-primary",
  "outcomeCode": "BOUNCED",
  "reasonCode": "INVALID_RECIPIENT",
  "occurredAt": "2026-11-12T08:10:00Z",
  "recordedAt": "2026-11-12T08:10:01Z"
}
```

Không cần lưu full bounce message, người nhận raw hoặc toàn bộ request headers vào audit.

### Event trễ hoặc sai thứ tự

Một webhook `DEFERRED` có thể được nhận **sau** event `DELIVERED` dù xảy ra trước. Event store nên giữ `occurredAt` và `recordedAt` tách biệt; derived status phải theo state machine chứ không đơn giản `last-write-wins` dựa trên thời gian nhận.

Nếu provider có những event như complaint sau delivered, cần giữ ngữ nghĩa gốc thay vì áp đặt thứ tự tuyến tính quá đơn giản.

## 25. Audit hành động thủ công có quyền

Những hành động operator thường cần audit kỹ hơn automated retry:

- Yêu cầu gửi lại notification.
- Hủy job hoặc hủy campaign.
- Đổi SMTP route.
- Tăng quota/rate limit tạm thời.
- Reprocess DLQ.
- Override suppression/consent theo quy trình hợp lệ.
- Xuất báo cáo audit.
- Xem bản evidence nhạy cảm trong khu vực hạn chế.

Một event `MANUAL_RESEND_AUTHORIZED` có thể cần:

```json
{
  "eventType": "MANUAL_RESEND_AUTHORIZED",
  "notificationId": "notif-302",
  "actorType": "OPERATOR",
  "actorRef": "staff-ref-18",
  "reasonCode": "CUSTOMER_SUPPORT_APPROVED",
  "policyVersion": "resend-policy-v3",
  "correlationId": "corr-incident-40"
}
```

`actorRef` có thể trỏ đến identity store có phân quyền. Không cần lưu tên, email cá nhân, toàn bộ request body hoặc lý do dạng free-text chứa PII nếu không có use case đã được phê duyệt.

### Phân biệt authorization và execution

Một người được cấp quyền resend không đồng nghĩa notification đã thực sự được gửi lại. Cần lưu event authorization/action request riêng với attempt/SMTP outcome.

## 26. Audit không phải kho chứa debug SMTP

Với Jakarta Mail/Spring Mail, bật SMTP debug có thể giúp điều tra giao thức nhưng phải xem đây là **công cụ kỹ thuật được kiểm soát**.

Không:

```text
Persist entire SMTP conversation forever
Persist AUTH transcript
Persist raw MimeMessage
Persist all recipient addresses inside audit
```

Đặc biệt tránh chế độ debug authentication dễ làm lộ credential. Nếu bật diagnostic log, cần:

- Quyền truy cập hạn chế.
- Thời gian bật ngắn.
- Cơ chế redaction.
- Không cho log đi vào nhiều destinations ngoài ý muốn.
- Xóa theo retention.
- Tắt sau khi điều tra.
- Audit riêng ai bật debug và trong bao lâu nếu có yêu cầu vận hành.

Audit trail chỉ cần `reasonCode=AUTHENTICATION` hoặc `TLS` và references an toàn; không cần lưu chuỗi AUTH hoặc password.

## 27. Error category và thông tin forensic

Một yêu cầu điều tra có thể cần nhiều chi tiết hơn audit tối thiểu. Giải pháp là phân tầng:

```text
Standard audit event
  eventType, time, IDs, route, outcome, reasonCode
            |
            v
Privileged diagnostic reference (optional)
  error details, bounded retention, redaction
            |
            v
Restricted evidence store (rarely)
  raw artifacts, explicit approval and retention
```

Từng tầng có:

- Mục đích.
- Owner.
- Điều kiện truy cập.
- Thời hạn lưu.
- Audit việc truy cập.
- Cơ chế xóa/quản lý khóa.

Không trao quyền “xem standard audit” rồi tự động cấp quyền tải raw MIME evidence.

## 28. Retention theo mục đích, không một con số cho mọi dữ liệu

Một hệ thống có thể cần các retention classes:

| Loại dữ liệu | Mục tiêu | Chính sách minh họa |
|---|---|---|
| SMTP diagnostic logs | Debug lỗi ngắn hạn | Ngắn, auto-expire |
| Mail submission attempts | Điều tra retry/unknown | Theo SLO và thời gian tranh chấp |
| Minimal audit events | Truy vết quyết định/hành động | Theo yêu cầu pháp lý/nghiệp vụ đã phê duyệt |
| Recipient destination mapping | Gửi thư và hỗ trợ khách hàng | Hết mục đích thì xóa/giảm nhạy cảm |
| Raw MIME/attachment evidence | Mục đích đặc biệt nếu bắt buộc | Kho riêng, quyền/retention chặt |
| Aggregated metrics | Xu hướng vận hành | Thường có thể giữ lâu hơn nếu không định danh |
| Backup copies | Phục hồi sự cố | Cần lịch hết hạn và cơ chế xử lý dữ liệu đã xóa |

Các khoảng thời gian cụ thể (7 ngày, 30 ngày, 12 tháng...) **không nên được tuyên bố là mặc định bắt buộc**. Chúng phụ thuộc mục đích, hợp đồng, chính sách tổ chức và pháp luật áp dụng. Hãy định nghĩa retention bằng policy được phê duyệt rồi cấu hình thực thi.

### Tránh giữ dữ liệu vô hạn “đề phòng cần dùng”

Nếu không có mục đích rõ, retention vô hạn làm chi phí và rủi ro tăng. Với email giao dịch quan trọng, không được xóa audit sớm hơn yêu cầu hợp lệ; với dữ liệu không cần lưu, không giữ chỉ vì storage rẻ.

## 29. Retention policy phải có owner và thực thi được

Một policy production cần ít nhất:

```text
dataClass
purpose
owner
retentionPeriod
startOfRetention
deletionMethod
legalHoldException
accessRoles
backupHandling
verification/alerting
```

Ví dụ:

```text
mail_audit_minimal:
  purpose: submission traceability
  owner: messaging-platform
  retention: defined by approved policy
  start: event recordedAt
  deletion: partition drop / controlled delete
  access: audited operator roles
  legalHold: explicit scoped flag
```

Đây là **policy template**, không phải YAML cấu hình có sẵn trong Spring Boot.

Có thể có nhiều đồng hồ thời gian: `occurredAt` phản ánh thời điểm sự kiện, `recordedAt` phản ánh lúc lưu, `retentionUntil` phản ánh thời điểm phải xử lý theo policy. Cần tránh event đến trễ khiến retention vượt quy định một cách vô ý.

## 30. Xóa dữ liệu và giữ integrity của audit

Một khó khăn: audit có thể liên kết với user/recipient trong khi dữ liệu cá nhân phải được xóa khi hết mục đích hoặc theo yêu cầu hợp lệ.

Có thể chọn:

- **Xóa trường định danh** khỏi bản ghi phụ trợ khi hết retention.
- **Xóa bảng ánh xạ pseudonym** để audit chỉ còn event không thể liên kết bằng dữ liệu còn giữ, nếu phù hợp.
- **Tombstone** logical notification với ID và trạng thái tối thiểu.
- **Xóa toàn bộ audit** khi hết retention và không có legal hold.
- **Crypto-shredding** trong kiến trúc mã hóa có key phân vùng thực sự phù hợp, hiểu rõ backup/key management.

Không được gọi một bản ghi “ẩn danh” nếu vẫn còn `notificationId` và bảng backup/lookup cho phép truy ngược về người nhận.

### Append-only và quyền được xóa không mâu thuẫn về mặt thiết kế

“Append-only” có thể là nguyên tắc chống sửa sự kiện **trong thời hạn lưu**, không đồng nghĩa giữ dữ liệu cá nhân mãi mãi. Có thể thiết kế audit segment/partition theo retention, xóa đúng hạn và ghi nhận thao tác xóa theo chính sách mà không giữ lại chính dữ liệu cần xóa.

Nếu có yêu cầu legal hold, cần xác định phạm vi và thẩm quyền rõ; không biến nó thành một cờ để giữ mọi dữ liệu vô thời hạn.

## 31. Giảm dữ liệu ngay ở nguồn event

Một nguyên tắc hiệu quả:

> **Đừng thu thập dữ liệu nhạy cảm trước rồi trông chờ redaction cứu mọi bản sao.**

Ví dụ API dễ gây rủi ro:

```java
public void audit(Object event) {
    String json = objectMapper.writeValueAsString(event);
    auditRepository.insert(json);
}
```

Bất cứ class nào đưa vào cũng có thể được serialize, kể cả `MailCommand` có recipient, subject, body và tokens.

Tốt hơn:

```java
public interface MailAuditRecorder {

    void recordSubmissionAccepted(
            String notificationId,
            String attemptId,
            String routeId
    );

    void recordSubmissionFailure(
            String notificationId,
            String attemptId,
            String routeId,
            MailAuditReason reason
    );
}
```

Interface hẹp ngăn caller truyền raw `MimeMessage` hoặc `Exception`. Với event phức tạp hơn, dùng DTO đã được allowlist.

**Redaction ở sink chỉ là lớp phòng thủ bổ sung**, không phải chiến lược data minimization duy nhất.

## 32. Redaction khi bắt buộc dùng structured log

Nếu cần log sự cố:

```java
logger.warn(
        "Mail attempt failed: notificationId={}, "
      + "attemptId={}, route={}, reason={}",
        notificationId,
        attemptId,
        routeId,
        errorCategory
);
```

Tránh:

```java
logger.error(
        "Failed to send {} to {} with secret {}",
        mimeMessage,
        recipientEmail,
        smtpPassword
);
```

Không giả định mọi `toString()` an toàn. Một command/domain object có thể được generator tự động đưa cả body/recipient vào `toString()`.

Khi cần ghi stack trace, hãy đánh giá exception cause chain có thể chứa địa chỉ/hostname/provider message gì, và giữ nó trong diagnostic log có quyền, retention ngắn. Không copy raw stack trace sang audit event.

## 33. Audit trail không nên chứa metric labels có cardinality cao

Các metric hữu ích:

```text
mail_audit_recorded_total
mail_audit_write_failure_total
mail_submission_attempt_total
mail_submission_accepted_total
mail_submission_unknown_total
mail_provider_event_duplicate_total
```

Tags an toàn hơn:

```text
event_type=SUBMISSION_ACCEPTED
route=transactional-primary
outcome=SMTP_ACCEPTED
error_category=TIMEOUT
```

Không dùng:

- `notificationId`, `attemptId`, `providerMessageId`.
- Email người nhận hoặc user ID.
- Subject/body.
- Raw exception message.
- Tên attachment hoặc URL cá nhân hóa.

Cardinality cao gây vấn đề storage/cost và tăng khả năng rò rỉ PII. Dùng log/audit DB có phân quyền cho truy vấn theo ID; dùng metric chỉ để đo xu hướng aggregate.

## 34. Tính toàn vẹn: append-only không đồng nghĩa bất biến tuyệt đối

Audit nhằm điều tra nên cần giảm nguy cơ bị sửa/xóa trái phép.

Các biện pháp:

- Application role chỉ có quyền INSERT và SELECT cần thiết; hạn chế UPDATE/DELETE.
- Partition retention được điều khiển bởi tài khoản dịch vụ riêng.
- Có audit độc lập cho thay đổi quyền/policy và deletion jobs.
- Backup và disaster recovery có kiểm soát.
- Audit store không cùng quyền quản trị rộng với mọi hệ thống.
- Giám sát gap, duplicate event IDs và ingestion lag.

Nếu yêu cầu bằng chứng chống sửa mạnh hơn, có thể cân nhắc:

- Hash chain giữa các bản ghi hoặc segment.
- HMAC/digital signature với khóa bảo vệ.
- WORM/immutable storage trong thời hạn áp dụng.
- External checkpoint/attestation.
- Periodic verification jobs.

Nhưng **hash chain chỉ phát hiện một số kiểu thay đổi** khi checkpoint/khóa đáng tin cậy; nó không tự chứng minh ai đã gửi email, SMTP acceptance hoặc tính hợp pháp của việc thu thập dữ liệu.

### Không tạo hash của full MIME chỉ vì muốn integrity

Hash raw message có thể có use case kiểm tra integrity cụ thể, nhưng vẫn có khả năng liên kết/đối chiếu dữ liệu và cần cân nhắc data minimization. Nếu không có mục đích, chỉ giữ template version và event outcome.

## 35. Phân quyền đọc audit theo least privilege

Không phải mọi người trong nhóm kỹ thuật cần xem mọi audit record.

Một mô hình:

| Vai trò | Quyền phù hợp |
|---|---|
| Application worker | Append audit tối thiểu |
| Support agent | Tra cứu những notification thuộc phạm vi ticket được giao |
| Operations engineer | Xem event timeline và reason codes |
| Security auditor | Xem access/configuration audit theo quyền |
| Compliance/data steward | Quản lý retention/legal hold và export theo approval |
| Database retention job | Xóa/partition maintenance theo policy |
| Developer thông thường | Truy cập dữ liệu test hoặc thông tin đã giảm nhạy cảm |

**Authorization cần kiểm tra ở service/API layer** ngay cả khi bảng audit chỉ chứa opaque IDs. Một lookup từ `notificationId` sang recipient/address có thể vượt giới hạn tenant nếu không có kiểm tra quyền.

Dùng tenant scoping và row-level security khi phù hợp; không chỉ dựa vào một điều kiện frontend ẩn nút “xem email”.

## 36. Audit chính hành động truy cập audit

Một hệ thống audit có giá trị cũng cần biết:

- Ai tra cứu timeline của notification nhạy cảm?
- Ai xuất dữ liệu audit ra file?
- Ai dùng quyền đặc biệt để xem raw MIME evidence?
- Ai thay đổi retention/policy?
- Ai yêu cầu xóa hoặc legal hold?
- Ai kích hoạt manual resend?

Nên ghi **access audit** cho những thao tác nhạy cảm, nhưng không tạo vòng lặp vô hạn kiểu “ghi audit cho một lần ghi audit cho một lần ghi audit”. Thiết kế audit-of-audit ở kênh riêng hoặc có event type giới hạn và guard phù hợp.

Không cần audit mọi lần refresh dashboard metric thông thường nếu không có lý do bảo mật/nghiệp vụ.

## 37. Multi-tenant và ranh giới dữ liệu

Nếu hệ thống phục vụ nhiều tenant:

- Audit phải luôn gắn phạm vi tenant có thể kiểm tra.
- Một tenant không được tra cứu `notificationId` của tenant khác.
- `providerRoute` và actorRef không được tiết lộ credential/sender profile bí mật.
- Nếu audit tập trung dùng chung, storage/query phải có tenant filtering/authorization.
- Export audit phải được kiểm tra phạm vi dữ liệu.
- Retention class có thể khác nếu policy hợp lệ, nhưng cần tránh rò rỉ qua việc gộp dữ liệu.
- Khi offboard tenant, xử lý cả audit, mappings, attachments, backups và legal holds theo chính sách.

Có thể thêm `tenantRef` dạng opaque vào event nếu cần kiểm soát phạm vi truy vấn, nhưng nó vẫn có thể là identifier cần bảo vệ. Không nên mặc định dùng `tenantRef` làm Prometheus label nếu số tenant rất lớn.

### Các event cross-tenant

Một batch provider event có thể chứa nhiều recipients/tenants. Webhook handler phải map mỗi event tới đúng notification/tenant trước khi tạo audit, không tin tenant ID do payload không được xác thực cung cấp.

## 38. Khi nào dùng evidenceRef?

Audit bình thường nên đủ với event metadata. Có những trường hợp ngoại lệ cần bằng chứng chi tiết:

- Tranh chấp hợp đồng về **nội dung chính xác** được gửi.
- Điều tra gian lận hoặc an ninh được phê duyệt.
- Nghĩa vụ lưu trữ tài liệu theo chính sách cụ thể.
- Sự cố hiếm cần raw provider response.
- Xác minh chữ ký nội dung nếu hệ thống có yêu cầu riêng.

Khi đó:

```text
mail_audit_event
  eventId
  notificationId
  eventType
  evidenceRef (nullable)
                |
                v
    Restricted evidence store
      - encryption at rest
      - scoped access
      - immutable object/version if required
      - explicit retention
      - access audit
      - deletion/hold policy
```

Không lưu raw payload trực tiếp vào audit chỉ vì thêm một cột BLOB nhanh hơn. `evidenceRef` phải đủ an toàn: không là public URL hoặc presigned URL sống quá lâu.

## 39. Audit cho sender/route/template changes

Không chỉ email attempts mới cần audit. Những cấu hình có thể làm thay đổi toàn bộ hành vi gửi:

- Thay SMTP provider hoặc failover route.
- Bật/tắt SMTP AUTH, thay TLS policy.
- Thay verified sender profile.
- Thay retry/backpressure policy.
- Thay template version được phát hành.
- Đổi suppression/consent rule.
- Bật manual replay hoặc mass resend.

Một configuration audit có thể lưu:

```json
{
  "eventType": "MAIL_ROUTE_POLICY_CHANGED",
  "actorType": "OPERATOR",
  "actorRef": "staff-ref-18",
  "policyVersion": "mail-route-v8",
  "changeCategory": "FAILOVER_PRIORITY",
  "occurredAt": "2026-11-12T08:20:00Z"
}
```

Không lưu **SMTP password cũ/mới**, API token hoặc private keys trong audit diff. Nếu cần biết secret đã được rotate, lưu `secretVersionRef` hoặc `rotationEventId` không chứa giá trị secret.

### Template change có lưu nội dung không?

Với template version được quản lý trong repository/artifact store, audit có thể giữ `templateKey` và version/hash đã được phê duyệt. Không cần sao chép toàn bộ template HTML vào mỗi email audit event.

## 40. Audit và pháp luật: không giả định một retention chung

Yêu cầu bảo vệ dữ liệu, lưu chứng từ, ngành nghề và khu vực pháp lý có thể khác nhau và thay đổi. Không nên khẳng định “tất cả audit email phải lưu 7 năm” hoặc “mọi địa chỉ email phải xóa sau 30 ngày” mà chưa xác định phạm vi và căn cứ thực tế.

Một quy trình đúng:

1. Xác định mục đích và loại dữ liệu.
2. Xác định bên kiểm soát/xử lý dữ liệu và hệ thống liên quan.
3. Xác định chính sách pháp lý/hợp đồng áp dụng.
4. Phê duyệt retention và quyền truy cập.
5. Cấu hình deletion và xử lý backup.
6. Rà soát khi provider, ngành nghề hoặc địa bàn thay đổi.
7. Ghi nhận ngoại lệ/legal hold có thẩm quyền.

Đây là hướng thiết kế kỹ thuật; khi cần kết luận pháp lý, phải đối chiếu quy định thực tế với bộ phận phụ trách.

## 41. Vận hành retention và backup

Một deletion job không nên chỉ xóa bảng chính trong khi dữ liệu vẫn tồn tại vô hạn trong:

- Application logs.
- Log aggregation/SIEM.
- Database replicas.
- Backups/snapshots.
- Data warehouse exports.
- Developer debug dumps.
- Queue/DLQ.
- Temporary object storage.
- Incident attachments.

Cần có **data inventory và deletion coverage**. Với bản backup không thể chỉnh sửa tại chỗ, phải có thời hạn hết hạn, quy trình restore an toàn và chính sách xử lý dữ liệu đáng lẽ đã bị xóa khi khôi phục.

### Lưu event quá dài có thể tốn kém

Mỗi logical notification có thể có vài attempts; mỗi attempt lại có nhiều sự kiện. Nếu hệ thống gửi hàng triệu thông báo/ngày, audit events có thể tăng rất nhanh.

Có thể dùng:

- Phân vùng theo thời gian và retention class.
- Chỉ mục đúng truy vấn thực tế.
- Event type allowlist.
- Archive/compaction có kiểm soát nếu policy cho phép.
- Tránh lặp lại template/body/recipient ở mỗi event.
- Giới hạn payload JSON tùy biến.

Không “tiết kiệm storage” bằng cách xóa ngẫu nhiên event quan trọng trước thời hạn, nhưng cũng không cần ghi mỗi trạng thái poll của worker.

## 42. Monitoring sức khỏe của chính audit pipeline

Một audit trail hữu ích phải có khả năng phát hiện nó đang bị thiếu sự kiện.

Metric gợi ý:

| Tín hiệu | Mục đích |
|---|---|
| `mail_audit_append_success_total` | Số events ghi thành công |
| `mail_audit_append_failure_total` | Ghi event thất bại |
| `mail_audit_publish_pending` | Event chờ đẩy sang audit store ngoài |
| `mail_audit_publish_oldest_age_seconds` | Tuổi event chờ lâu nhất |
| `mail_audit_dedupe_total` | Duplicate source events đã loại |
| `mail_audit_retention_delete_total` | Số bản ghi được xóa theo policy |
| `mail_audit_retention_overdue` | Dữ liệu quá hạn chưa được xóa |
| `mail_audit_schema_rejected_total` | Event không hợp lệ bị từ chối |
| `mail_audit_integrity_failure_total` | Integrity check lỗi nếu có |

Những tên này là ví dụ, không phải meter có sẵn trong Spring Mail.

Alert nên dựa vào tỷ lệ lỗi, ingestion lag, retention overdue và sự chênh lệch giữa notification/attempt transitions với audit events. Không dùng “audit service còn UP” làm bằng chứng mọi sự kiện đã được ghi.

## 43. Kiểm thử data minimization

Một số bài test không cần SMTP thật, chỉ kiểm schema:

```java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void auditEventHasNoMailContentFields() {
    MailAuditEvent event =
            auditFactory.submissionAccepted(
                    "notif-302",
                    "attempt-302-01",
                    "transactional-primary"
            );

    String serialized = objectMapper.writeValueAsString(
            event
    );

    assertThat(serialized)
            .doesNotContain("smtpPassword")
            .doesNotContain("accessToken")
            .doesNotContain("htmlBody")
            .doesNotContain("attachmentBytes")
            .doesNotContain("customer@example.net");
}
```

`auditFactory` và `objectMapper` là test fixtures do ứng dụng cấu hình; tên field trong assert chỉ là một lớp phòng vệ. Test mạnh hơn nên xác nhận **allowlist trường được phép** thay vì chỉ tìm một vài từ cấm, vì nội dung nhạy cảm có thể nằm trong một field tên khác.

### Kiểm thử contract của event schema

- Event type thuộc enum hợp lệ.
- `schemaVersion` rõ.
- `occurredAt`/`recordedAt` dùng `Instant`.
- `attemptId` chỉ bắt buộc ở event attempt.
- Không có subject/body/recipient raw ở standard audit.
- `reasonCode` từ danh mục hữu hạn.
- Không được truyền arbitrary object để serialize.
- `correlationId` không chứa PII.
- Có tối đa payload size theo policy nếu dùng JSON extension.

## 44. Kiểm thử tính nhất quán transaction

Các case:

1. Tạo notification và audit event cùng transaction; rollback thì cả hai không tồn tại.
2. Finalize attempt accepted và ghi audit trong cùng transaction.
3. Update attempt thất bại vì claim token không hợp lệ; không ghi audit accepted.
4. Ghi audit thất bại; transaction phản hồi theo policy nhất quán.
5. External audit publisher chết; local outbox event vẫn còn để retry.
6. External audit consumer nhận trùng event; dedupe theo source event ID.
7. Crash sau SMTP accepted trước database finalize; attempt không tự được ghi thành known rejected.
8. Audit event đến sau trạng thái hiện hành; timeline vẫn ghi chính xác timestamps.

Các bài test về transaction/locking nên dùng database tương thích với production nếu cần xác nhận isolation, không chỉ mock repository.

### Audit write failure xử lý thế nào?

Đây là quyết định SLO/compliance:

- Với hành động cần audit bắt buộc trước khi được thực hiện, phải chặn/rollback phần có thể rollback khi không persist được audit.
- Với SMTP attempt đã thực hiện, không thể rollback network side effect; cần state recovery và incident alert nếu audit finalize thất bại.
- Với metric/log best-effort, không được nhầm chúng với audit bắt buộc.
- Có thể dùng local durable event outbox để tránh phụ thuộc vào một audit service remote trên đường gửi.

**Không âm thầm nuốt audit exception rồi báo cho nghiệp vụ rằng đã bảo đảm audit.**

## 45. Kiểm thử redaction và quyền truy cập

Một ma trận:

| Test | Kỳ vọng |
|---|---|
| Support agent truy vấn notification thuộc ticket của họ | Chỉ thấy fields được phép |
| Support agent truy vấn tenant khác | Bị từ chối |
| Operator xem timeline | Thấy IDs, outcome và reasonCode |
| Operator không có quyền mở evidence | Không truy cập raw MIME |
| Privileged evidence access được duyệt | Có audit access riêng |
| Webhook chứa email/raw payload | Audit chỉ lưu normalized event |
| SMTP exception chứa username | Audit không chứa raw message |
| Token xuất hiện trong `toString()` của command | Không serialize command vào audit |
| Export audit | Scope, retention và access được kiểm tra |
| Xóa recipient mapping | Audit giảm khả năng liên kết theo policy |
| Retention overdue | Có alert và remediation |
| Backup restore | Deletion policy được áp dụng sau restore |

Không chỉ test HTTP status; cần xác minh **body response và export** không chứa các trường ngoài quyền.

## 46. Kiểm thử chống sửa, chống trùng và event order

Nếu hệ thống áp dụng append-only hoặc integrity checking:

- Test user role thường không thể UPDATE/DELETE audit event.
- Test retention job chỉ xóa đúng phạm vi được phép.
- Test event ID duplicate được deduplicate hoặc từ chối rõ.
- Test integrity mismatch được phát hiện/alert.
- Test correction event liên kết event trước, không âm thầm sửa quá khứ.
- Test event xảy ra trước nhưng ghi sau vẫn có hai timestamps.
- Test manual resend event riêng với SMTP accepted event.
- Test webhook delivered/bounced không bị đếm thành submission attempt mới.
- Test multi-recipient partial outcome khi transport hỗ trợ.

Không xem hash chain là bảo đảm tuyệt đối nếu khóa/checkpoint cũng nằm cùng hệ thống có thể bị sửa.

## 47. Một case study: email xác nhận đơn hàng

Giả sử một khách hoàn tất thanh toán, ứng dụng cần gửi email xác nhận.

### Trước khi gửi

```text
Business event:
  ORDER_PAID

Audit:
  NOTIFICATION_QUEUED
  notificationId=notif-302
  sourceType=DOMAIN_EVENT
  templateKey=order-confirmation
  templateVersion=v7
```

Không cần đưa tên khách, địa chỉ email hoặc tổng giá trị đơn hàng vào audit nếu những dữ liệu đó đã được quản lý ở domain/notification store có quyền.

### Lần thử thứ nhất bị rate limit

```text
Audit:
  ATTEMPT_STARTED
  notificationId=notif-302
  attemptId=attempt-302-01

Audit:
  SUBMISSION_REJECTED
  attemptId=attempt-302-01
  reasonCode=RATE_LIMITED

Audit:
  RETRY_SCHEDULED
  notificationId=notif-302
  nextAttemptRef=retry-policy-v2
```

Không lưu raw SMTP response nếu không cần; log kỹ thuật có thể giữ thêm thông tin an toàn trong thời hạn ngắn.

### Lần thử thứ hai thành công

```text
Audit:
  ATTEMPT_STARTED
  attemptId=attempt-302-02

Audit:
  SUBMISSION_ACCEPTED
  attemptId=attempt-302-02
  outcome=SMTP_ACCEPTED
  providerRoute=transactional-primary
```

### Provider trả webhook delivered

```text
Audit:
  PROVIDER_DELIVERED
  attemptId=attempt-302-02
  providerRoute=transactional-primary
  eventSource=PROVIDER_WEBHOOK
```

Nếu một khách hàng khiếu nại, hệ thống có thể hiển thị timeline này mà không cần cho operator xem toàn bộ nội dung email, token hoặc file đính kèm.

## 48. Anti-pattern thường gặp

| Anti-pattern | Rủi ro | Giải pháp |
|---|---|---|
| Lưu full `MimeMessage` vào audit | Sao chép body/attachment và PII | Metadata tối thiểu, evidence store riêng khi cần |
| Lưu subject ở mọi event | Subject có thể chứa PII/OTP | Template key/version |
| Lưu recipient raw vào mọi attempt | Nhân bản dữ liệu cá nhân | recipientRef và privileged lookup |
| Hash email không khóa rồi gọi là ẩn danh | Có thể dictionary attack/linking | Data minimization; HMAC có quản trị nếu cần |
| Serialize arbitrary event object | Vô tình lưu secret/bodies | Typed DTO và allowlist |
| Audit toàn bộ SMTP debug | Rò rỉ credential/provider info | Reason taxonomy, debug ngắn hạn |
| `sent=true` duy nhất | Không biết attempts/unknown | Event timeline/state machine |
| Gọi `send` thành công rồi ghi DELIVERED | Sai chứng cứ | SMTP_ACCEPTED |
| Ghi audit trước commit nhưng báo QUEUED | Event giả khi rollback | Local transaction |
| Ghi audit remote đồng bộ trước mọi HTTP request | Lỗi dependency làm gián đoạn hoặc mất event | Local durable outbox + publisher |
| Nuốt lỗi audit | Mất traceability âm thầm | Failure policy và alert |
| Audit ID dùng email/token | PII lộ qua index/URL/log | Opaque identifiers |
| Mọi operator xem raw MIME | Vi phạm least privilege | Restricted evidence access |
| Append-only vô thời hạn | Không thực hiện retention/deletion | Policy, partitions, exceptions có kiểm soát |
| Log/metric chứa recipient làm tag | Cardinality và privacy | Enum tags |
| Webhook raw body là audit payload | PII/token/schema drift | Verify, normalize, dedupe |
| Không audit manual resend | Không biết ai tạo duplicate | Authorized action event |
| Bảo toàn integrity nhưng không có deletion plan | Vướng retention/privacy | Segmenting và scoped deletion |

## 49. Checklist thiết kế production

1. Xác định **mục đích kiểm toán** trước khi chọn fields.
2. Phân biệt audit, diagnostic log, metric và trace.
3. Danh mục event chỉ gồm quyết định/hành động đáng kể.
4. Tách business occurrence, notification, attempt và provider event ID.
5. Dùng event DTO có field allowlist và version.
6. Không truyền raw `MimeMessage`/`Exception`/`MailCommand` vào audit serializer.
7. Không lưu OTP, reset token, SMTP secrets, attachment bytes.
8. Tránh subject và recipient raw nếu có cách tham chiếu ít nhạy cảm hơn.
9. Nếu dùng HMAC pseudonym, quản lý khóa và không gọi đó là anonymous.
10. Phân biệt SMTP accepted, known rejected, unknown và downstream delivered.
11. Ghi audit đúng thời điểm transaction; không tạo bằng chứng sai.
12. Tách network SMTP I/O khỏi database transaction.
13. Có idempotent event ID và xử lý webhook duplicate.
14. Có correlation và attempt history đủ để điều tra retry.
15. Manual resend/cancel/route change có actor và authorization audit.
16. Retention được phê duyệt, có owner, start time và deletion job.
17. Có inventory cho logs, exports, backups, queues và evidence store.
18. Quyền xem audit khác quyền xem raw email/evidence.
19. Có access audit cho những truy vấn và export nhạy cảm.
20. Kiểm soát multi-tenant và quyền tra cứu ID.
21. Có integrity/tamper-evidence nếu yêu cầu nhưng hiểu giới hạn.
22. Metric/alert cho audit write failure, publication lag và retention overdue.
23. Unit test allowlist/redaction và log không chứa secrets.
24. Integration test transaction, replay, crash, unknown outcome.
25. Có runbook xử lý khi audit pipeline chậm hoặc hỏng.

## 50. Ghi nhớ

- **Audit trail tốt không phải audit trail lưu nhiều nhất**, mà là lưu đủ sự kiện đúng nghĩa với ít dữ liệu nhạy cảm nhất.
- Event loại `NOTIFICATION_QUEUED`, `ATTEMPT_STARTED`, `SUBMISSION_ACCEPTED`, `SUBMISSION_REJECTED`, `SUBMISSION_UNKNOWN` và provider events thường hữu ích hơn full MIME.
- Không nhầm SMTP accepted với delivered/inbox/read.
- Notification ID, attempt ID và provider ID có phạm vi khác nhau.
- Subject, recipient address, body và attachment có thể mang thông tin nhạy cảm; không lặp vào audit mặc định.
- Typed audit event và field allowlist giúp ngăn accidental data collection từ đầu nguồn.
- Pseudonym không tự động là anonymous; lookup/key vẫn cần kiểm soát.
- Event type và reason code nên hữu hạn; không copy raw exception hoặc SMTP transcript.
- Ghi audit trong đúng local transaction và dùng outbox khi cần đẩy ra kho tập trung.
- SMTP không tham gia transaction database, nên không thể rollback email đã accepted.
- Append-only phục vụ integrity trong thời gian lưu, nhưng vẫn phải có retention/deletion policy.
- Quyền xem audit timeline không đồng nghĩa quyền tải raw MIME evidence.
- Ghi actor và lý do cho manual resend, override policy hoặc truy cập evidence.
- Monitoring phải phát hiện audit write failures/lag, không chỉ đếm email sent.
- Test nên xác minh field allowlist, rollback, deduplication, access control và deletion coverage.

**Kết luận:** Trong Spring Framework Mail production, một audit trail có giá trị là **chuỗi sự kiện có cấu trúc mô tả ai/điều gì đã yêu cầu gửi, thông báo nào đã được nhận xử lý, attempt nào được SMTP chấp nhận hoặc từ chối, và bằng chứng downstream nào đã xuất hiện**. Hãy lưu định danh và trạng thái ở mức tối thiểu, đặt raw content ở nguồn dữ liệu riêng được phân quyền khi thật sự cần, và áp dụng retention, integrity cùng kiểm thử nhất quán. Nhờ đó hệ thống vừa điều tra được sự cố gửi thư, vừa không xây thêm một kho dữ liệu cá nhân quá mức dưới tên “audit”.
