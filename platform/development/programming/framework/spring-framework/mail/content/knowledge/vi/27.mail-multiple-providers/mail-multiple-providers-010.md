# Theo dõi deliverability khác nhau giữa các provider

Khi một ứng dụng sử dụng Spring Framework Mail để gửi email qua nhiều nhà cung cấp, việc gọi `JavaMailSender.send(...)` thành công **không có nghĩa người nhận đã thấy thư trong Inbox**. Spring Mail chủ yếu cung cấp API dựng MIME message và giao nội dung cho mail transport. Sau khi SMTP server đầu tiên chấp nhận thư, email còn có thể bị trì hoãn, từ chối tại server đích, rơi vào spam, bị chặn do chính sách, hoặc được provider thông báo bằng các sự kiện bất đồng bộ.

Điều này trở nên phức tạp hơn với **nhiều provider**: mỗi hệ thống có thuật ngữ, trạng thái, API, webhook, cơ chế suppression, cấu hình domain và mức chi tiết báo cáo khác nhau. Provider A có thể gọi một sự kiện là `processed`, provider B dùng `accepted`, provider C chỉ có phản hồi SMTP. Một dashboard cộng dồn các trạng thái mà không thống nhất định nghĩa có thể báo tỷ lệ giao thư rất đẹp trong khi thực tế thư vẫn đang `deferred` hoặc bị bounce.

Bài học này xây một cách tiếp cận **theo dõi deliverability đa nhà cung cấp** trong Spring Framework Mail: phân biệt submission, acceptance, delivery và engagement; chuẩn hóa sự kiện; tương quan từng notification với provider message ID và recipient; thu nhận webhook một cách an toàn; xử lý duplicate/out-of-order; tính metric có mẫu số rõ ràng; đối chiếu khi thiếu sự kiện; và dùng thông tin đó để quản trị routing, retry, failover cũng như chất lượng gửi email.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao `JavaMailSender.send(...)` không thể tự khẳng định email đã vào Inbox.
2. Phân biệt sự kiện của **application**, **SMTP transport**, **email provider**, **mailbox đích** và **người dùng**.
3. Nhận ra sự khác biệt về event taxonomy giữa các provider nhưng không phụ thuộc cứng vào nhãn của một sản phẩm.
4. Thiết kế trạng thái gửi theo **notification**, **attempt**, **provider** và **recipient**.
5. Xây một mô hình event chuẩn hóa và adapter cho nhiều provider.
6. Xử lý webhook an toàn, idempotent, có độ bền qua crash và chịu được event đến sai thứ tự.
7. Đo delivered/bounced/deferred/complaint với mẫu số, phạm vi và khoảng thời gian được định nghĩa rõ.
8. Phân biệt thiếu dữ liệu quan sát với kết quả giao thư thất bại.
9. Điều tra chênh lệch deliverability theo provider, domain người nhận, loại email và thời gian.
10. Chọn phương án retry/failover tránh lặp email, tránh vượt suppression và không làm hỏng uy tín gửi.

## 2. Vị trí của Spring Framework Mail trong chuỗi gửi email

`JavaMailSender` là abstraction của Spring Mail để ứng dụng gửi thông điệp email. Khi dùng `JavaMailSenderImpl` với SMTP, lời gọi thường đi qua các bước:

```text
Business service
      |
      v
Notification/Outbox (PENDING)
      |
      v
MimeMessage + JavaMailSender
      |
      v
SMTP provider A / B / C
      |
      +-- Local acceptance / queue
      |
      v
Receiving mail server (remote MTA)
      |
      +-- Accepted / delayed / rejected
      |
      v
Mailbox filters / spam placement
      |
      v
Mail client / user interaction
```

Tại mỗi tầng có một câu hỏi khác nhau:

| Tầng | Câu hỏi có thể trả lời | Nguồn bằng chứng |
| --- | --- | --- |
| Application | Yêu cầu gửi có được ghi nhận và xử lý không? | Notification/outbox record |
| SMTP submission | Mail server đầu tiên có phản hồi chấp nhận thao tác gửi không? | `JavaMailSender` và transport exception |
| Provider processing | Provider có xếp hàng, trì hoãn hoặc từ chối không? | Provider event/API/log |
| Remote delivery | Server email đích có chấp nhận thông điệp không? | Delivery event của provider |
| Mailbox placement | Thư vào Inbox, Promotions, spam hay bị rule lọc? | Seed tests, mailbox signals, công cụ chuyên biệt |
| Engagement | Người nhận có mở/click/tương tác không? | Tracking event có giới hạn đo lường |

**Không gộp sáu tầng này thành một cờ `sent=true`.** Cờ ấy thiếu khả năng diễn đạt một email đã submit nhưng vẫn đang retry, một email bounced sau khi được provider nhận, hoặc một thư đã giao tới server đích nhưng không thấy trong Inbox.

## 3. Các thuật ngữ cần phân biệt

### 3.1. Submitted

Trong ngữ cảnh Spring SMTP, `SUBMITTED` nên nghĩa là **lần gửi đã được SMTP transport xác nhận hoàn tất theo bằng chứng nó quan sát được**. Thông thường, không có exception từ `JavaMailSender.send(...)` cho một message giúp ứng dụng ghi nhận kết quả submission của lần thử ấy.

Nhưng kết quả đó không bảo đảm delivery cuối, không nói Inbox placement và có thể chưa kèm provider message ID.

### 3.2. Accepted hoặc processed

Nhiều provider có trạng thái hoặc sự kiện báo rằng chúng **đã nhận yêu cầu gửi và đang xử lý/đưa vào queue**. Tên event và điều kiện chính xác thay đổi theo provider: không được coi mọi event `accepted`, `processed` hoặc `queued` là tương đương với remote `delivered`.

### 3.3. Delivered

Trong nhiều dịch vụ email, `delivered` có nghĩa provider đã giao message tới hoặc nhận được phản hồi chấp nhận từ **mail server đích**. Đây là bằng chứng mạnh hơn `submitted`, nhưng vẫn **không chứng minh người dùng nhìn thấy email trong Inbox**.

Một message có thể bị đưa vào spam hoặc thư mục khác sau bước SMTP acceptance.

### 3.4. Deferred hoặc delayed

Một số sự kiện biểu thị provider chưa giao được ngay nhưng vẫn có thể thử lại theo lịch riêng. `DEFERRED` không phải luôn là thất bại cuối và cũng không đồng nghĩa ứng dụng nên gửi lại một bản nữa.

### 3.5. Bounce

`Bounce` thường báo nỗ lực delivery không thành công, có thể liên quan mailbox không tồn tại, domain/policy, tài nguyên tạm thời hoặc nhiều nguyên nhân khác. Phân biệt hard/soft bounce theo định nghĩa provider và các bằng chứng SMTP, không chỉ theo một chuỗi text.

### 3.6. Complaint

Complaint thường liên quan tín hiệu người nhận đánh dấu thư là spam hoặc cơ chế feedback của mailbox/provider. Nó có tác động đến uy tín gửi và suppression. Tỷ lệ complaint cần quan sát theo policy/provider và mẫu số nhất quán.

### 3.7. Rejected, dropped, suppressed

Provider có thể từ chối hoặc bỏ một message **trước khi thử giao tới server đích**, ví dụ do suppression list, chính sách nội dung, tài khoản hoặc quota. Không gọi trạng thái này là remote bounce nếu chưa có nỗ lực delivery tương ứng.

## 4. Bản đồ trạng thái từ business đến provider

Một mô hình quan sát:

```text
PENDING
   |
   v
PROCESSING
   |
   +---- build/validation error ---> PREPARATION_FAILED
   |
   +---- SMTP known failure ------> RETRY_WAIT / FAILED
   |
   +---- SMTP outcome uncertain --> UNKNOWN
   |
   v
SUBMITTED
   |
   +---- provider accepted/queued --> PROVIDER_ACCEPTED
   |
   +---- delayed ------------------> DEFERRED
   |                                   |
   |                                   +--> DELIVERED_REMOTE
   |                                   +--> BOUNCED
   |
   +---- delivered ----------------> DELIVERED_REMOTE
   |
   +---- rejected/dropped ---------> REJECTED / SUPPRESSED
   |
   +---- bounce -------------------> BOUNCED
   |
   +---- complaint ---------------> COMPLAINED
```

Sơ đồ cố ý **không** thể hiện một máy trạng thái tuyến tính cứng. Một provider có thể gửi một event delivered rồi tiếp tục phát các tín hiệu complaint; các sự kiện khác có thể được giao đến webhook **trễ, lặp hoặc sai thứ tự**.

Do đó, ở hệ thống đa provider, nên lưu **event ledger bất biến** bên cạnh trạng thái tổng hợp thay vì dùng một cột status ghi đè theo thứ tự webhook đến.

## 5. Vì sao tên event khác nhau giữa các provider?

Nhà cung cấp email có thể cung cấp các kênh khác nhau:

- **SMTP relay:** phản hồi trực tiếp khi submit, đôi khi thêm DSN/bounce mailbox.
- **HTTP Email API:** response có request/message ID và khả năng query status.
- **Event webhook:** HTTP callback cho accepted, delivered, bounce, complaint, unsubscribe hoặc engagement.
- **Message event API/log search:** tra cứu theo message ID, account, tag hoặc thời gian.
- **Notification bus:** phát sự kiện tới topic/queue do bạn kết nối.
- **Bounce mailbox:** gửi DSN tới return-path hoặc địa chỉ xử lý bounce.

Chúng cũng có các nhãn khác nhau. Ví dụ, khi đọc tài liệu của Amazon SES, SendGrid, Mailgun hoặc Postmark, bạn có thể gặp các nhóm như **send/delivery/bounce/complaint**, **processed/delivered/deferred/dropped**, **accepted/delivered/failed**, hoặc **delivery/bounce/spam complaint**. Đây chỉ là **ví dụ định hướng**, không phải danh sách event chính thức hoặc contract bất biến của từng sản phẩm.

**Luôn đọc tài liệu đúng API, account configuration và phiên bản provider đang tích hợp** trước khi map nhãn. Không viết code dựa trên giả định tất cả provider đều có cùng tên event, cùng payload, cùng mức độ chi tiết hoặc cùng định nghĩa `delivered`.

## 6. Bảng so sánh ở mức năng lực, không gắn cứng một API

| Năng lực | SMTP relay thông thường | Provider có event webhook | Provider có HTTP API + event log |
| --- | --- | --- | --- |
| Xác nhận submission tại thời điểm gửi | Thường có qua SMTP reply | Có thể có SMTP/API response | Có qua API response |
| Message ID riêng của provider | Không luôn có hoặc không luôn trả về qua SMTP | Tùy tích hợp | Thường có cách truy vấn/correlation |
| Delivered event | Không mặc định | Tùy cấu hình/event subscription | Tùy API |
| Bounce/complaint feedback | DSN/mailbox, hoặc không có | Có thể hỗ trợ webhook | Có thể hỗ trợ log và callback |
| Suppression information | Tùy relay | Tùy provider/account | Tùy provider/account |
| Tra cứu lịch sử | Tùy log và retention | Webhook do ứng dụng lưu | Có thể có API tra cứu |
| Reconciliation sau downtime | Khó nếu không có log | Cần replay/query nếu hỗ trợ | Dễ hơn khi có query API |
| Delivery tới Inbox | Không thể suy ra chỉ từ SMTP | Webhook delivered thường không xác nhận Inbox | API delivered thường không xác nhận Inbox |

Bảng này so sánh **lớp khả năng** chứ không chấm điểm một thương hiệu cụ thể. Cùng một provider có thể hỗ trợ những khả năng rất khác nhau giữa SMTP, REST API, sandbox, khu vực triển khai và gói dịch vụ.

## 7. “Deliverability” phải có định nghĩa đo lường

Trong thực tế, từ deliverability được dùng cho ít nhất ba câu hỏi:

1. **Submission success:** ứng dụng chuyển message cho provider thành công ở mức nào?
2. **Remote delivery:** bao nhiêu recipient được provider xác nhận đã giao tới mail server đích?
3. **Inbox placement:** bao nhiêu thư thực sự xuất hiện trong Inbox thay vì spam/Promotions/other?

Chỉ số thứ ba **không thể xác định chính xác từ sự kiện delivered thông thường**. Inbox placement cần mailbox/seed testing hoặc dữ liệu bổ sung được cấp quyền; và ngay cả khi dùng seed list, kết quả cũng chỉ là mẫu thử.

Không dùng tên dashboard “Inbox delivery rate” cho một công thức lấy `delivered_count / submitted_count` từ webhook. Tên đúng hơn thường là “provider-reported remote delivery rate”.

## 8. Phạm vi đo: per message hay per recipient?

Một message có thể có nhiều recipient:

```text
MimeMessage X
  To: a@example.net
  Cc: b@example.net
  Bcc: c@example.net
       |
       v
SMTP RCPT TO A / B / C
       |
       v
Provider deliverability events per recipient
```

Nếu chỉ lưu `message.status=DELIVERED`, bạn sẽ mất thông tin trường hợp A đã được remote MTA chấp nhận, B bị bounce và C bị deferred.

**Đơn vị quan sát quan trọng nhất cho deliverability thường là một notification/recipient tại một attempt/provider.** Có thể giữ một message chung cho nhiều recipient nhưng phải thiết kế event correlation đúng cấp.

| Chỉ số | Đơn vị nên khai báo |
| --- | --- |
| Message submission | Message attempt |
| Provider send event | Provider event hoặc message attempt |
| Remote delivered | Recipient delivery outcome |
| Bounce | Recipient delivery outcome |
| Complaint | Recipient feedback/event |
| Retry | Notification/recipient attempt |
| Unique notification sent | Notification ID |

Nếu một provider chỉ xuất aggregate event ở mức message, không được tự suy ra có đủ kết quả riêng cho tất cả recipient.

## 9. Cấu trúc dữ liệu cần theo dõi

Một hệ thống đa provider nên tách bốn loại ID:

| ID | Bên tạo | Để làm gì |
| --- | --- | --- |
| `notificationId` | Ứng dụng | Định danh yêu cầu gửi bền vững |
| `attemptId` | Ứng dụng | Một lần thử submit cụ thể, có thể dùng provider khác |
| `providerMessageId` | Provider (khi có) | Đối chiếu event hoặc API |
| `providerEventId` | Provider (khi có) | Khử trùng lặp webhook/event |

Đồng thời cần `recipientId` nội bộ để phân biệt kết quả theo người nhận, và `providerKey` để biết route được sử dụng.

### Vì sao cần cả notificationId và attemptId?

```text
Notification N-100
  |
  +-- Attempt A-1: Provider A, SMTP timeout -> UNKNOWN
  |
  +-- Attempt A-2: Provider B, accepted -> SUBMITTED
  |
  +-- Event từ Provider A tới muộn: delivered
  |
  +-- Event từ Provider B: delivered
```

Nếu chỉ có một `notificationId` và ghi đè `provider` hiện tại, sự kiện muộn từ Provider A có thể bị ghép nhầm sang attempt B, làm dashboard đếm sai và che khuất một sự cố **gửi trùng giữa hai provider**.

**Một event phải gắn với đúng provider + attempt + recipient**, hoặc được đánh dấu chưa thể tương quan để điều tra, không đoán bằng subject/body.

## 10. Dữ liệu không nên dùng làm khóa duy nhất

Các trường dưới đây có thể hữu ích để truy vết nhưng không nên bị xem là khóa toàn cục:

- `MimeMessage.getMessageID()`: Message-ID có thể do library hoặc relay tạo/cập nhật, không bảo đảm unique theo mọi chiều.
- `To`/`Cc`/`Bcc`: một recipient có thể nhận nhiều notification giống nhau.
- `Subject`: nhiều thư có thể chung subject; còn chứa dữ liệu cá nhân.
- Timestamp: nhiều event có thể cùng thời điểm, precision/clock khác nhau.
- Provider event type: một message có thể deferred nhiều lần.
- Provider message ID **không namespace**: có thể chỉ unique trong một provider/account/region.

Khóa correlation bền vững nên được thiết kế có namespace:

```text
providerKey + account/region scope + providerMessageId
                                    |
                                    v
                             attemptId
                                    |
                                    v
                       notificationId + recipientId
```

Nếu SMTP không trả provider message ID, hãy lưu bằng chứng bạn **thực sự có**, ví dụ application attempt ID và thời điểm gửi. Có thể thêm provider-supported custom metadata/header trong cấu hình được phép, nhưng không giả định mọi provider đều echo lại header tùy chỉnh trong delivery event.

## 11. Mô hình lưu trữ tách notification, attempt và event

Một thiết kế tham khảo:

```text
mail_notification
  notification_id (PK)
  message_type / template_version
  recipient_id / created_at
          |
          | 1 -> N
          v
mail_attempt
  attempt_id (PK)
  notification_id (FK)
  provider_key / provider_scope
  submission_outcome / provider_message_id
          |
          | 1 -> N (khi correlation xác lập được)
          v
mail_delivery_event
  ingest_id (PK)
  provider_key / provider_scope
  event_dedupe_key
  provider_event_type / canonical_event_type
  attempt_id / recipient_id
  occurred_at / received_at
```

Ba bảng phục vụ ba mục đích:

- **Notification** ghi nhận ý định gửi, tồn tại độc lập với provider.
- **Attempt** ghi từng lần ứng dụng thử submit; provider được chọn tại thời điểm ấy.
- **Delivery event** ghi dữ liệu feedback bất đồng bộ, kể cả thông tin đến muộn.

Có thể có thêm bảng `mail_recipient_outcome` làm **projection** hiện trạng theo recipient, nhưng projection không thay thế lịch sử event.

### Ví dụ schema PostgreSQL minh họa

```sql
CREATE TABLE mail_notification (
    notification_id UUID PRIMARY KEY,
    recipient_id UUID NOT NULL,
    message_type VARCHAR(80) NOT NULL,
    template_version VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE mail_attempt (
    attempt_id UUID PRIMARY KEY,
    notification_id UUID NOT NULL
        REFERENCES mail_notification(notification_id),
    provider_key VARCHAR(60) NOT NULL,
    provider_scope VARCHAR(100) NOT NULL,
    provider_message_id VARCHAR(300),
    submission_outcome VARCHAR(40) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    failure_category VARCHAR(60)
);

CREATE INDEX ix_mail_attempt_provider_message
    ON mail_attempt(
        provider_key, provider_scope, provider_message_id
    );

CREATE TABLE mail_delivery_event (
    ingest_id UUID PRIMARY KEY,
    provider_key VARCHAR(60) NOT NULL,
    provider_scope VARCHAR(100) NOT NULL,
    event_dedupe_key VARCHAR(300) NOT NULL,
    attempt_id UUID NULL REFERENCES mail_attempt(attempt_id),
    recipient_id UUID NULL,
    provider_message_id VARCHAR(300),
    provider_event_type VARCHAR(120) NOT NULL,
    canonical_event_type VARCHAR(60) NOT NULL,
    occurred_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    correlation_state VARCHAR(40) NOT NULL,
    UNIQUE (
        provider_key, provider_scope, event_dedupe_key
    )
);
```

Đây là **schema giảng dạy**, chưa bao gồm tất cả các index, partition, migration và security policy của hệ thống production. `event_dedupe_key` phải được adapter tạo theo **contract duy nhất phù hợp của từng provider**, không được mặc định mọi webhook đều có một trường `id` globally unique.

`recipient_id` có thể `NULL` trong inbox event khi chưa map được; giữ event ở trạng thái `UNMATCHED` để retry correlation sau, thay vì gán nhầm người nhận.

### Không lưu toàn bộ payload vào bảng chính nếu không cần

Webhook đôi khi chứa địa chỉ email, diagnostic string, IP hoặc thông tin tài khoản. Nếu phải giữ raw payload để điều tra:

- Cân nhắc một kho riêng có mã hóa và TTL ngắn.
- Gắn một reference hoặc hash/HMAC có quyền vào record.
- Giới hạn quyền truy cập và audit.
- Không đưa payload thô vào dashboard/log chung.
- Tuân thủ chính sách lưu dữ liệu và xóa theo quy định liên quan.

## 12. Chuẩn hóa sự kiện: giữ cả canonical và raw type

Một enum chuẩn hóa có thể bao gồm:

```java
public enum CanonicalMailEventType {
    PROVIDER_ACCEPTED,
    DEFERRED,
    DELIVERED_REMOTE,
    BOUNCED,
    COMPLAINED,
    PROVIDER_REJECTED,
    SUPPRESSED,
    UNSUBSCRIBED,
    OPENED,
    CLICKED,
    UNKNOWN
}
```

**Không nhất thiết mọi provider phải hỗ trợ mọi loại.** `UNKNOWN` dành cho event chưa có mapping hoặc không đủ bằng chứng; không âm thầm bỏ qua sự kiện mới rồi báo mọi thứ bình thường.

Ngoài canonical type, giữ:

- `providerKey`: provider đã gửi event.
- `providerScope`: account/subaccount/region hoặc route namespace.
- `providerEventType`: tên sự kiện gốc.
- `eventDedupeKey`: khóa dedup đã chuẩn hóa có scope.
- `providerMessageId`: nếu có.
- `attemptId` và `recipientId`: sau correlation, nếu có bằng chứng.
- `occurredAt`: thời điểm provider nói event xảy ra, nếu có.
- `receivedAt`: thời điểm hệ thống nhận.
- `failureCategory`: loại bounce, suppression hoặc chính sách, nếu phân tích được.
- `providerDiagnosticCode`: mã đã được kiểm soát, tránh lưu nguyên văn PII.

### DTO Java dành cho tầng chuẩn hóa

```java
import java.time.Instant;
import java.util.UUID;

public record NormalizedMailEvent(
        String providerKey,
        String providerScope,
        String eventDedupeKey,
        String providerEventType,
        CanonicalMailEventType canonicalType,
        String providerMessageId,
        UUID attemptId,
        UUID recipientId,
        Instant occurredAt,
        Instant receivedAt,
        String failureCategory
) {}
```

Trong thiết kế thật, cần thêm schema version, channel, event actor/source, confidence và khả năng phân biệt một event thuộc mức message hay per-recipient nếu provider hỗ trợ. Không ép `recipientId` có giá trị bằng cách tra subject hoặc tìm email address gần giống trong database.

## 13. Mapping là hợp đồng có phiên bản

Một bảng mapping có thể bắt đầu như sau:

| Ý nghĩa của provider event | Canonical type | Điều cần kiểm chứng trước khi map |
| --- | --- | --- |
| Provider đã chấp nhận yêu cầu | `PROVIDER_ACCEPTED` | Accepted ở account/queue hay remote server? |
| Provider trì hoãn/đang retry | `DEFERRED` | Có phải còn tiếp tục retry không? |
| Remote MTA chấp nhận message | `DELIVERED_REMOTE` | Delivered được định nghĩa ở stage nào? |
| Delivery thất bại | `BOUNCED` | Đây là final hay temporary? |
| Người nhận khiếu nại spam | `COMPLAINED` | Signal phát sinh theo recipient nào? |
| Provider từ chối trước khi giao | `PROVIDER_REJECTED` | Rejected hay bounce? |
| Suppression policy ngăn gửi | `SUPPRESSED` | Global/account/domain suppression? |
| Người dùng unsubscribe | `UNSUBSCRIBED` | Áp dụng cho loại thư nào? |
| Open/click tracking | `OPENED` / `CLICKED` | Tracking có được bật, privacy tác động ra sao? |

Nên giữ mapping ở adapter hoặc config có kiểm soát version thay vì viết một loạt `if` theo tên event trong business service.

### Không gom tất cả negative event thành BOUNCED

Ví dụ provider “dropped because suppressed” có thể chưa hề thử giao đến remote MTA. Nếu gom vào `BOUNCED`, chỉ số bounce sẽ bị đẩy lên sai, trong khi nguyên nhân thực tế là suppression hoặc policy.

Ngược lại, nếu bỏ negative event không map được, dashboard có thể chỉ đếm những message đã delivered và bỏ sót phần rơi khỏi pipeline.

## 14. Adapter cho từng provider

Kiến trúc nên đặt sự khác biệt provider ở rìa hệ thống:

```text
Provider A callback ---+
                       |
Provider B callback ---+--> Verify + Parse + Normalize
                       |             |
Provider C callback ---+             v
                                Event Inbox
                                      |
                                      v
                               Correlate/Dedup
                                      |
                                      v
                             Projection + Metrics
```

Một giao diện minh họa:

```java
public interface ProviderWebhookAdapter {

    String providerKey();

    VerifiedProviderPayload verify(
            byte[] rawPayload,
            Map<String, List<String>> headers
    );

    List<NormalizedMailEvent> normalize(
            VerifiedProviderPayload verifiedPayload
    );
}

public record VerifiedProviderPayload(
        String providerKey,
        byte[] originalBytes
) {}
```

Đây là API **do ứng dụng thiết kế**, không phải API có sẵn của Spring Mail. Trong triển khai thực tế có thể gộp hai bước hoặc không giữ raw byte array sau khi parse; điểm quan trọng là **xác thực trước khi tin dữ liệu, và mapping theo từng provider**.

Mỗi adapter chịu trách nhiệm:

- Xác định nội dung callback thuộc đúng provider/account được cấu hình.
- Xác minh chữ ký/token/cơ chế xác thực đúng tài liệu provider.
- Parse event theo schema và version cụ thể.
- Tạo dedupe key đúng scope và semantics.
- Chuẩn hóa thời gian, loại event và mã lỗi.
- Trích correlation metadata được provider cam kết trả về.
- Không log secret/raw payload.

Một adapter mới có thể được thêm vào mà không bắt business layer học thêm tên sự kiện riêng.

## 15. JavaMailSender không tự tạo event listener cho mọi provider

Trong Spring Mail:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, false, "UTF-8"
);

helper.setFrom("notice@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Xác nhận yêu cầu");
helper.setText("Thông báo thử nghiệm.");

mailSender.send(message);
```

Đoạn code này **chỉ thực hiện submission**. Spring không tự phát sinh callback “delivered/bounced/complained” cho mọi SMTP provider.

Nếu cần follow-up:

1. Cấu hình event publication của provider (webhook, topic/queue, API hoặc DSN mailbox).
2. Bảo đảm provider/account/domain đang dùng thực sự có quyền và đã bật đúng event types.
3. Gắn tương quan `attemptId` hoặc metadata được provider hỗ trợ.
4. Triển khai receiver và event store bên ngoài `JavaMailSender`.
5. Định nghĩa retention và reconciliation khi sự kiện không được nhận.

Nếu provider chỉ hỗ trợ SMTP reply và không có delivery feedback, dashboard nên hiển thị **“không có tín hiệu delivery”** thay vì lấy `SUBMITTED` làm delivered.

## 16. Provider message ID và custom headers

Để ghép một event tới attempt, có thể có các lựa chọn:

- Provider API trả message/request ID.
- Provider cho phép gắn custom arguments/tags/metadata và echo chúng trong event.
- Provider đưa message ID qua SMTP extension/header hoặc log có thể tra cứu.
- Ứng dụng lưu `Message-ID` của MIME và tìm kiếm bằng công cụ provider nếu hỗ trợ.
- Một hệ thống khác lưu inbound DSN và liên kết bằng những trường được cấp quyền.

**Không có giải pháp chung bảo đảm hoạt động với mọi provider SMTP.** Đặc biệt, một response SMTP `250 queued` có thể không cung cấp một message ID máy đọc được theo contract ổn định.

### Ví dụ header do ứng dụng đặt

```java
message.setHeader(
        "X-App-Attempt-Id",
        attemptId.toString()
);
```

Header kiểu này có thể hữu ích cho một số hệ thống hoặc khi điều tra message test. Tuy nhiên:

- Nó có thể xuất hiện trong thư tới người nhận; không dùng giá trị chứa PII/secret.
- Một provider có thể bỏ/sửa/không echo header trong event.
- Nó không phải giao diện correlation chính thức của mọi nhà cung cấp.
- Message ID/header có thể thay đổi khi forward hoặc relay.
- Đặt header không làm SMTP trở thành idempotent.

Khi provider có cơ chế metadata chính thức, ưu tiên cơ chế đó và test rằng metadata **thực sự quay lại** qua event.

## 17. SMTP provider routing cần lưu quyết định trước khi gửi

Ví dụ một hệ thống có ba route:

```text
Transactional -> Provider A
Bulk campaign -> Provider B
Fallback      -> Provider C (chỉ khi được phép)
```

`ProviderRouter` có thể chọn provider theo:

- Loại email và SLA.
- Country/region hoặc yêu cầu dữ liệu.
- Tenant/account đã được ủy quyền.
- Quota, throttling, trạng thái đường gửi.
- Warm-up/capacity và danh tiếng miền gửi.
- Chi phí và các đặc tính cần thiết (webhook, suppression, template metadata).

Kết quả routing phải được lưu trong `mail_attempt`:

```text
attemptId = A-1001
notificationId = N-500
providerKey = provider-a
providerScope = transactional-prod
routingReason = primary-transactional
startedAt = ...
```

Khi có event đến sau vài giờ, hệ thống phải biết nó thuộc **attempt nào** mà không suy ra từ provider đang active tại thời điểm nhận webhook.

## 18. Webhook là nguồn dữ liệu bất đồng bộ, không phải callback đồng bộ của send

Một luồng phổ biến:

```text
JavaMailSender.send(message)
        |
        +---- SMTP accepted ---> mark attempt SUBMITTED
        |
        v
Application trả kết quả cho caller

(vài giây/phút/giờ sau)

Provider event sender
        |
        v
HTTPS POST /webhooks/mail/provider-a
        |
        v
Verify authenticity + request limits
        |
        v
Persist durable event inbox
        |
        v
Return HTTP 2xx
        |
        v
Async correlate / normalize / project
        |
        v
Deliverability dashboard + remediation
```

Webhook **có thể** bị gửi trùng, bị giao chậm hoặc đến sai thứ tự. Trong một số hệ thống, provider retry callback khi endpoint không xác nhận thành công; chính sách thời gian và số lần retry là khác nhau. Receiver phải được thiết kế theo mô hình **at-least-once khi có thể**, không giả định exactly-once.

### Không block webhook vì gửi email khác

Không nên trong HTTP handler của webhook:

1. Thực hiện truy vấn hàng trăm bảng.
2. Tạo một batch email mới.
3. Gọi provider API nhiều lần.
4. Đợi SMTP sender gửi notification mới.
5. Chỉ sau đó mới trả HTTP `200`.

Một lỗi SMTP thứ cấp sẽ khiến provider retry webhook, tạo duplicate và tắc nghẽn. Tốt hơn là xác thực, ghi một bản event bền vững, trả acknowledgment, rồi xử lý nghiệp vụ bên trong worker độc lập.

## 19. Xác thực webhook phải theo đúng provider

Không được tin payload chỉ vì request có đường dẫn `/webhooks/mail/provider-a` hoặc header `X-Provider: A`. Bên ngoài Internet có thể gửi HTTP request đến endpoint đó.

Tùy provider, cơ chế xác thực có thể bao gồm:

- Chữ ký HMAC trên payload và timestamp.
- Chữ ký bất đối xứng với public key do provider cung cấp.
- Token hoặc credentials cho endpoint.
- Cơ chế thông báo qua message bus có IAM và chữ ký riêng.
- Quy trình xác nhận URL/subscription trước khi bắt đầu nhận event.

**Không có một công thức signature dùng được cho mọi provider.** Hãy tuân thủ cách canonicalize, thuật toán, header, key rotation và timestamp tolerance theo tài liệu của provider cụ thể.

### Nguyên tắc xác thực

1. Dùng HTTPS và giới hạn truy cập mạng hợp lý.
2. Xác minh signature/token trên **raw bytes** trước khi chỉnh sửa JSON.
3. Không tự reserialize JSON rồi dùng bản đã đổi whitespace/key order để kiểm chữ ký nếu provider yêu cầu raw body.
4. Nếu có timestamp/tolerance trong protocol xác thực, áp dụng chính xác để hạn chế replay.
5. Dùng key theo provider/account/scope và hỗ trợ xoay key.
6. So sánh MAC bằng hàm constant-time khi cơ chế provider dùng MAC và tài liệu yêu cầu.
7. Giới hạn kích thước body, số phần tử event batch và tốc độ request.
8. Không dùng IP allowlist như bằng chứng duy nhất nếu provider cung cấp signature có thể xác minh.
9. Chỉ xử lý nội dung sau khi xác thực và parse schema.
10. Ghi metric về invalid signature mà không log raw secret hoặc toàn payload.

Nếu provider gửi event qua queue/topic đã được bảo vệ bởi IAM, xác thực nguồn và quyền publish/subscribe tại message bus vẫn là phần bắt buộc của mô hình tin cậy.

## 20. Ví dụ Spring Boot webhook controller

Đây là **khung tích hợp** cho provider gửi JSON webhook qua HTTP POST; không phải endpoint có thể dùng ngay cho mọi provider. Interface `ProviderWebhookAdapter` sẽ được hiện thực theo tài liệu của từng nhà cung cấp.

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/webhooks/mail")
public class MailProviderWebhookController {

    private final ProviderWebhookRegistry registry;
    private final DeliveryEventInbox inbox;

    public MailProviderWebhookController(
            ProviderWebhookRegistry registry,
            DeliveryEventInbox inbox
    ) {
        this.registry = registry;
        this.inbox = inbox;
    }

    @PostMapping(
            path = "/{provider}",
            consumes = "application/json"
    )
    public ResponseEntity<Void> receive(
            @PathVariable String provider,
            @RequestHeader HttpHeaders headers,
            @RequestBody byte[] rawBody
    ) {
        ProviderWebhookAdapter adapter =
                registry.require(provider);

        VerifiedProviderPayload verified =
                adapter.verify(rawBody, headers);

        List<NormalizedMailEvent> events =
                adapter.normalize(verified);

        // Lưu bền vững và idempotent trước khi trả 2xx.
        // Worker khác sẽ xử lý projection/metrics.
        inbox.persist(events);

        return ResponseEntity.noContent().build();
    }
}
```

`ProviderWebhookRegistry` và `DeliveryEventInbox` là abstractions do ứng dụng triển khai. `verify(...)` phải ném một lỗi xác thực riêng khi signature không hợp lệ. Global exception handler/security layer cần phản hồi HTTP phù hợp, chẳng hạn `401/403` cho authentication failure và `400` cho payload sai cấu trúc, không chuyển mọi lỗi thành `200`.

### Các giới hạn của khung controller

- Chỉ hỗ trợ `application/json` như một ví dụ; một provider có thể gửi form-encoded, thông báo qua queue hoặc một envelope khác.
- Phải đặt **request body size limit trước khi toàn bộ body được nạp vào memory**.
- Phải kiểm soát batch event count và parser depth.
- Endpoint nên có timeout ngắn, autoscaling/rate limit và khả năng durable ingest.
- Nếu database/event inbox tạm lỗi, không báo thành công giả; xử lý HTTP response để provider có cơ hội retry theo contract của nó.
- Một số provider yêu cầu handshake hoặc challenge cho subscription; adapter và endpoint riêng phải hỗ trợ.

Đừng trả `2xx` rồi mới bắt đầu lưu event trong thread không có bảo đảm bền vững: process có thể chết ngay sau HTTP acknowledgment và làm mất vĩnh viễn feedback.

## 21. Vì sao nên có durable event inbox?

Một event inbox giúp tách tốc độ provider callback khỏi tốc độ xử lý nội bộ:

```text
Provider HTTP request
       |
       v
Signature verification
       |
       v
Insert event inbox (transaction)
       |
       +-- Duplicate event -> no-op, ack
       |
       +-- New event -> stored, ack
       |
       v
Background projector
       |
       +-- correlate attempt/recipient
       +-- normalize outcome
       +-- update recipient projection
       +-- emit metrics/audit
```

Lợi ích:

- Chịu được event đến trùng.
- Giữ event qua restart.
- Có thể retry projection khi database khác hoặc downstream service lỗi.
- Giữ được event chưa match attempt để reconciliation.
- Cho phép audit raw type và mapping phiên bản.
- Không khiến provider phải chờ business processing lâu.

Để xử lý cạnh tranh giữa các worker, inbox consumer cần claim/lease hoặc cơ chế message queue acknowledgment phù hợp. Nếu dùng database queue, transaction/row lock cần ngắn và đúng isolation.

## 22. Dedupe event đúng scope

Một webhook có thể chứa event ID; nhưng không phải provider nào cũng có ID duy nhất ở cấp event. Một batch có thể chứa nhiều recipient hoặc nhiều trạng thái với cùng message ID.

Nguyên tắc:

1. Ưu tiên **provider event ID** nếu contract của provider bảo đảm nó ổn định qua retries.
2. Namespace bằng provider/account/region hoặc event source.
3. Kiểm tra liệu event ID có unique theo **message**, **recipient**, **event** hay chỉ trong một time window.
4. Nếu cần tạo key từ composite fields, mô tả rõ khả năng collision.
5. Không dùng duy nhất `providerMessageId` làm event key: một message có nhiều event.
6. Không dùng riêng `timestamp`: nhiều event có thể cùng thời điểm hoặc clock precision khác.
7. Không dùng text body/recipient email làm khóa để tránh PII và matching mơ hồ.

### Ví dụ idempotent insert

```sql
INSERT INTO mail_delivery_event (
    ingest_id,
    provider_key,
    provider_scope,
    event_dedupe_key,
    attempt_id,
    recipient_id,
    provider_message_id,
    provider_event_type,
    canonical_event_type,
    occurred_at,
    received_at,
    correlation_state
)
VALUES (
    :ingestId,
    :providerKey,
    :providerScope,
    :dedupeKey,
    :attemptId,
    :recipientId,
    :providerMessageId,
    :providerEventType,
    :canonicalType,
    :occurredAt,
    now(),
    :correlationState
)
ON CONFLICT (
    provider_key, provider_scope, event_dedupe_key
)
DO NOTHING;
```

Đây là ví dụ PostgreSQL dựa trên unique constraint ở phần schema trước. Với provider không có event ID ổn định, adapter cần xây khóa dedupe phù hợp; **không bảo đảm mọi sự kiện lặp đều phân biệt được hoàn hảo**.

### Tại sao hash raw payload chưa chắc đủ?

Hash raw JSON có thể thay đổi khi provider gửi lại event nhưng thứ tự property hoặc envelope khác. Ngược lại, hai sự kiện riêng biệt có thể có nội dung giống hệt, đặc biệt với temporary deferral lặp theo chu kỳ.

Khi phải dùng fingerprint, nên dựa trên các trường được provider cam kết có ý nghĩa, gồm scope, message, recipient, event type và một sequence/event timestamp đáng tin cậy. Với trường hợp không đủ độ tin cậy, đánh dấu khả năng dedupe không hoàn chỉnh thay vì công bố “exactly once event ingestion”.

## 23. Một event có thể đến sai thứ tự

Ví dụ:

```text
Provider thực tế:
  10:00:00 ACCEPTED
  10:00:03 DEFERRED
  10:00:28 DELIVERED

Webhook đến ứng dụng:
  10:00:29 DELIVERED
  10:00:31 ACCEPTED
  10:00:33 DEFERRED
```

Nếu xử lý:

```java
notification.setStatus(event.canonicalType().name());
```

trạng thái cuối có thể bị ghi thành `DEFERRED` dù provider đã báo delivery.

### Cách xử lý bền vững

- Lưu mọi event hợp lệ vào ledger.
- Dùng `occurredAt` như thông tin, nhưng không tin tuyệt đối nếu provider/clock không có bảo đảm.
- Nhận diện những outcome có ý nghĩa cuối dựa theo **quy tắc từng provider** và attempt.
- Giữ `receivedAt` để đo độ trễ sự kiện và debugging.
- Không để event `PROVIDER_ACCEPTED` đến muộn làm mất dấu delivery đã quan sát.
- Nếu sự kiện mâu thuẫn, giữ flag `CONFLICT/NEEDS_RECONCILIATION`, không tùy tiện xóa bằng chứng.

Một event `COMPLAINED` có thể đến **sau** `DELIVERED_REMOTE`; đó không nhất thiết là mâu thuẫn. Delivery và complaint thuộc **hai chiều quan sát** khác nhau.

## 24. Đừng dùng một thứ tự enum để quyết định mọi trạng thái

Ví dụ sai:

```java
if (incoming.ordinal() > current.ordinal()) {
    current = incoming;
}
```

Ordinal của enum là thứ tự khai báo trong source code, không phải mô hình thời gian hoặc nghiệp vụ.

Một projection hợp lý có thể tách:

```text
submission_state:
  PENDING | SUBMITTED | FAILED | UNKNOWN

delivery_state:
  NOT_OBSERVED | QUEUED | DEFERRED |
  DELIVERED_REMOTE | BOUNCED | REJECTED |
  UNRESOLVED

feedback_state:
  NONE | COMPLAINED | UNSUBSCRIBED

engagement_state:
  NOT_MEASURED | OPEN_OBSERVED | CLICK_OBSERVED
```

Nhờ đó:

- Một thư có thể `DELIVERED_REMOTE` và `COMPLAINED`.
- Một thư có thể đã delivered nhưng engagement là `NOT_MEASURED`.
- Không thấy webhook không tự có nghĩa `BOUNCED`.
- Submission outcome `UNKNOWN` có thể được provider evidence đến muộn làm rõ.

Mỗi provider adapter có thể bổ sung trạng thái đặc thù, nhưng projection chung không nên ghi đè quá khứ một cách mất dữ liệu.

## 25. Trạng thái UNMATCHED không phải dữ liệu rác

Một webhook có thể đến trước khi mapping `providerMessageId -> attemptId` được commit hoặc nhận được từ API response. Hoặc provider chỉ gửi metadata thiếu một trường mà bạn tưởng luôn có.

```text
Webhook DELIVERED
   providerMessageId = X
   recipient metadata available
             |
             v
No matching attempt yet
             |
             v
Persist event as UNMATCHED
             |
             v
Async reconciliation later
```

Không xóa event chỉ vì nó chưa match ngay. Có thể:

- Retry correlation sau một khoảng ngắn.
- Tìm theo provider/scope/message ID đã namespace.
- Dùng một ID do ứng dụng gắn nếu provider thực sự echo lại theo contract.
- Đưa vào queue/manual review nếu không đủ dữ liệu.
- Đo `unmatched_event_count` và tuổi của event chưa ghép.

Tuy nhiên, không gán event bằng cách tìm “recipient email + subject + gần thời điểm” nếu có thể map nhầm giữa các notification có nội dung giống nhau. Nếu phải fallback matching, cần confidence, giới hạn phạm vi và audit.

## 26. Không thể mặc định webhook luôn đến

Một callback có thể không xuất hiện vì:

- Subscription chưa bật đúng event type.
- Endpoint tạm downtime, TLS/certificate/route lỗi.
- Provider ngừng retry sau một khoảng thời gian.
- Callback bị chặn do rate limit hoặc body limit.
- Message không đi qua đường gửi có feedback đang cấu hình.
- Delivery feedback không tồn tại cho loại SMTP relay đó.
- Provider đã gửi event nhưng application fail trước khi lưu.
- Account/region khác không được tích hợp.
- Provider có sampling hoặc retention giới hạn.

Vì vậy, thiếu event là **khoảng trống quan sát**, không tự động là một bounce hoặc delivery thành công. Cần dashboard cho cả **event coverage** và **delivery outcome**.

## 27. Reconciliation khi event bị mất hoặc tới muộn

Một luồng reconciliation:

```text
Attempt SUBMITTED > configured age threshold
                |
                v
No terminal delivery evidence
                |
                +--> Provider has query API?
                |       |
                |       +--> Query by supported IDs/scope
                |       +--> Normalize returned evidence
                |       +--> Persist as source-labeled observation
                |
                +--> DSN/bounce mailbox supported?
                |       |
                |       +--> Parse trusted feedback safely
                |
                +--> No evidence available?
                        |
                        +--> Mark as STALE_UNOBSERVED
                        +--> Alert only per business SLA
```

Không phải mọi provider hỗ trợ query theo message ID hoặc replay webhook; có thể cần đánh dấu không có dữ liệu sau ngưỡng thời gian. Dù đã quá một giờ, **`STALE_UNOBSERVED` không đồng nghĩa FAILED**.

Nếu dùng API reconciliation, cần:

- Rate limit và backoff riêng.
- Token scope tối thiểu và rotation.
- Batching theo khả năng API.
- Không truy vấn vô hạn những message đã hết retention.
- Gắn `source=RECONCILIATION_API` cho event quan sát thay vì giả làm webhook nguyên gốc.
- Idempotency giữa kết quả query và webhook thật.

## 28. Mẫu số quyết định ý nghĩa của delivery rate

Một dashboard rất dễ gây hiểu nhầm khi chỉ hiển thị:

```text
delivered_count / sent_count
```

Hai câu hỏi chưa được trả lời:

- `delivered_count` đếm **event** hay **recipient-attempt duy nhất**?
- `sent_count` đếm yêu cầu gửi, SMTP attempts, provider accepted hay recipient deliveries có thể quan sát?

Nếu một recipient nhận hai event delivered trùng, đếm cả hai có thể đẩy tỷ lệ vượt 100%. Nếu một notification retry qua hai provider, mẫu số không nhất quán cũng tạo sai lệch.

### Một định nghĩa có thể so sánh

Với một **cohort các recipient-attempt đã được provider chấp nhận** và đã có đủ thời gian quan sát:

\[
\text{Remote delivery rate} =
\frac{\text{Số recipient-attempt duy nhất có bằng chứng DELIVERED\_REMOTE}}
{\text{Số recipient-attempt đủ điều kiện trong cohort}}.
\]

Phải khai báo rõ:

1. Cohort được chọn theo thời điểm `submittedAt` hay `providerAcceptedAt`.
2. Mẫu số có loại provider-rejected/suppressed hay không.
3. Đơn vị là recipient-attempt hay unique notification-recipient.
4. Event đến trễ được tính vào cohort gốc như thế nào.
5. Một attempt gửi chung nhiều recipient được tách ra sao.
6. Có lọc transactional/bulk, tenant, region hoặc recipient domain không.
7. Các event chưa match hoặc không được provider hỗ trợ được xử lý thế nào.

Một công thức hữu ích cho provider A **không tự động hợp lệ** với provider B nếu hai bên có coverage và event semantics khác nhau.

## 29. Event coverage là một chỉ số độc lập

Nếu provider A gửi thông tin delivery phong phú và provider B chỉ báo submission, B có thể hiển thị gần 0% delivered **không phải vì email không tới**, mà vì ứng dụng không có feedback tương ứng.

Ví dụ chỉ số:

\[
\text{Outcome coverage} =
\frac{\text{Recipient-attempt có ít nhất một outcome có ý nghĩa}}
{\text{Recipient-attempt đủ điều kiện quan sát}}.
\]

`Outcome` phải được định nghĩa: có thể là delivered, final bounce, rejected, suppression hoặc một trạng thái đã xác định. Event `opened` không nên được dùng thay thế bằng chứng delivery.

Ngoài ra, cần quan sát:

- `webhook_ingest_requests_total`: lượng HTTP callbacks.
- `webhook_signature_failure_total`: thất bại xác thực.
- `webhook_duplicate_events_total`: event bị dedup.
- `webhook_unmatched_events_total`: event chưa map được attempt.
- `event_processing_lag_seconds`: độ trễ từ nhận đến projection.
- `provider_event_delay_seconds`: `receivedAt - occurredAt` khi hai timestamp đáng tin.
- `stale_unobserved_attempts`: attempt chưa thấy outcome sau ngưỡng SLA.

Một provider có remote delivery tốt nhưng webhook endpoint của ứng dụng hỏng vẫn có thể xuất hiện như một “sự cố deliverability” trên dashboard không tách coverage.

## 30. Cần cohort đủ tuổi để tránh right-censoring

Hãy tưởng tượng bạn nhìn vào dashboard lúc 10:05:

```text
10:00 - 10:05: 1,000 message vừa submitted
10:05:        600 delivered events đã tới
               400 message vẫn đang được provider xử lý
```

Nếu lấy 600/1.000 rồi kết luận “deliverability giảm còn 60%”, bạn đã trộn **chưa đủ thời gian giao thư** với **giao thư thất bại**.

Một phương pháp:

- Chọn cohort theo `submittedAt`.
- Chỉ đánh giá sau một khoảng tuổi phù hợp, ví dụ email đã submit ít nhất 1 giờ hoặc 24 giờ tùy SLA.
- Tách event `DEFERRED`, `BOUNCED`, `SUPPRESSED` và `UNOBSERVED`.
- Cho phép event đến muộn cập nhật kết quả của cohort cũ.
- Lưu cả dữ liệu “as-of time” nếu cần biết dashboard đã hiển thị gì tại thời điểm incident.

Khoảng “1 giờ/24 giờ” chỉ là ví dụ; giao hàng email phụ thuộc provider, domain nhận, tình trạng server và chính sách retry. Không có một ngưỡng chuẩn cho mọi loại email.

## 31. Ví dụ so sánh hai provider có cùng định nghĩa

Giả sử dữ liệu **giả lập** của hai cohort transactional, sau 24 giờ, được phân loại theo recipient-attempt duy nhất:

| Outcome sau 24 giờ | Provider A | Provider B |
| --- | ---: | ---: |
| Đủ điều kiện trong cohort | 1.000 | 1.000 |
| `DELIVERED_REMOTE` | 920 | 955 |
| `BOUNCED` | 35 | 20 |
| `DEFERRED` chưa kết thúc | 20 | 10 |
| `PROVIDER_REJECTED` | 10 | 5 |
| `UNOBSERVED` | 15 | 10 |
| Tổng các nhóm | 1.000 | 1.000 |

Trong **ví dụ minh họa**, tỷ lệ remote delivered tương ứng là 92,0% và 95,5% theo mẫu số đã chọn. Nhưng chưa thể kết luận B “tốt hơn cho mọi traffic”, vì:

- Hai provider có thể nhận traffic đến các domain khác nhau.
- Provider có thể có khác biệt về thời gian retry và feedback delay.
- Cohort có thể chưa đủ lớn cho một số phân nhóm.
- Email content, authentication domain, reputation hoặc mức danh sách sạch khác nhau.
- Một nhóm `UNOBSERVED` có thể là thiếu telemetry, không phải bị bounce.

**So sánh công bằng** cần cùng loại thông báo, cùng tiêu chí chọn recipient, cùng thời gian đo, cùng ý nghĩa outcome, và kiểm soát khác biệt traffic mix.

### Đừng cộng thẳng tất cả event

Bảng trên cố ý dùng **trạng thái tổng hợp loại trừ nhau tại thời điểm chụp** cho mỗi recipient-attempt. Trong event ledger thật, một recipient có thể có `DEFERRED` rồi `DELIVERED_REMOTE`, và sau đó `COMPLAINED`. Nếu cộng số event thay vì tạo projection, tổng có thể vượt số attempt.

## 32. Các tỷ lệ nên tính riêng

| Chỉ số | Một cách định nghĩa | Lưu ý |
| --- | --- | --- |
| Submission success rate | SMTP/API attempts thành công / attempts được thử | Không phải delivery |
| Provider acceptance rate | Provider-accepted recipient attempts / attempted recipient submissions | Cần provider accepted event hoặc response |
| Remote delivery rate | Unique delivered recipients / eligible recipient attempts trong mature cohort | Phụ thuộc event coverage |
| Final bounce rate | Unique bounced recipient attempts / eligible recipient attempts | Định nghĩa final phải nhất quán |
| Temporary deferral rate | Unique attempts có deferral / eligible attempts | Có thể chồng với delivered sau đó |
| Suppression rate | Unique suppressed recipients / attempted recipients | Cần tách compliance/policy |
| Complaint rate | Unique complaints / denominator đã định nghĩa rõ | Provider và chương trình feedback có khác biệt |
| Webhook coverage rate | Attempts có outcome feedback / eligible attempts | Đo mức quan sát |
| Unknown submission rate | Attempts có SMTP outcome mơ hồ / attempts được thử | Đo rủi ro retry/duplicate |

Một vài tỷ lệ như “ever deferred” **không loại trừ nhau** với “eventually delivered”; dashboard phải ghi rõ nếu một recipient được tính ở nhiều chỉ số.

### Complaint rate đặc biệt nhạy về mẫu số

Có hệ thống dùng complaint trên delivered, có hệ thống dùng complaint trên accepted hoặc theo định nghĩa riêng của provider. Khi so sánh:

- Đừng trộn hai mẫu số.
- Ghi thời gian event và cohort.
- Phân biệt số complaint events với số recipient duy nhất.
- Cân nhắc nguồn feedback không đại diện cho tất cả mailbox providers.

Không đối chiếu một tỷ lệ nội bộ với một ngưỡng uy tín công khai nếu công thức không tương thích với cách nhà cung cấp đo.

## 33. Thời gian giao thư quan trọng không kém tỷ lệ giao thành công

Đối với OTP, password reset hoặc thông báo bảo mật, một email giao sau 30 phút có thể không còn hữu dụng dù provider báo `DELIVERED_REMOTE`.

Có thể đo:

\[
\text{Delivery latency} =
\text{provider delivery occurredAt}
- \text{submission started/acceptedAt}.
\]

Định nghĩa timestamp cần nhất quán:

- `submissionStartedAt`: lúc ứng dụng bắt đầu thử.
- `providerAcceptedAt`: thời điểm provider xác nhận chấp nhận (nếu có).
- `deliveredAt`: thời điểm provider báo remote acceptance.
- `receivedAt`: thời điểm webhook tới ứng dụng.

**Không lấy webhook receivedAt làm deliveredAt một cách vô điều kiện.** Nếu event bị queue hai giờ rồi mới tới, latency tính từ receivedAt sẽ phản ánh chậm webhook, không chỉ chậm giao thư.

Dashboard nên thể hiện p50/p95/p99 delivery latency với:

- Một cohort đủ tuổi.
- Số quan sát.
- Mức missing timestamp.
- Event-time vs ingest-time phân biệt.
- Provider/recipient-domain/traffic-class segmentation.

Chỉ tính latency trong nhóm đã delivered dễ tạo **survivorship bias**. Một provider có 10% message bị treo mãi có thể có p95 tốt trong 90% còn lại; vì vậy xem latency **cùng** tỷ lệ delivered/unobserved.

## 34. Domain người nhận có thể quan trọng hơn provider tổng thể

Giả sử:

```text
Provider A: traffic chủ yếu tới domain X
Provider B: traffic chủ yếu tới domain Y
```

Nếu domain X có nhiều hộp thư không tồn tại hoặc throttling, A có thể hiện bounce/deferral cao hơn dù chất lượng route giữa hai provider tương đương cho cùng domain.

Nên phân nhóm theo:

- Provider và provider account/scope.
- Recipient domain group (đã kiểm soát số lượng nhóm).
- Transactional vs marketing/bulk.
- Template/message class.
- Region hoặc luồng nghiệp vụ, khi phù hợp.
- Cohort theo thời gian và tuổi event.

Không tạo time-series label cho **mọi địa chỉ email**, **mọi domain hiếm**, **tenant ID không giới hạn** hoặc **notification ID**. Cardinality cao khiến metrics đắt và rủi ro PII tăng.

### Tránh Simpson's paradox

Một provider có tổng delivery rate thấp hơn có thể lại tốt hơn trong từng domain riêng, nếu nó gánh nhiều traffic ở nhóm khó giao hơn. Khi quyết định routing, so sánh theo phân nhóm tương đồng trước khi dùng một con số tổng để chuyển toàn bộ traffic.

## 35. Open và click không phải bằng chứng đọc email chính xác

Một số provider cung cấp engagement events:

- `OPENED`: có tín hiệu tải pixel hoặc cơ chế đo mở.
- `CLICKED`: có tín hiệu truy cập link được provider theo dõi.
- `UNSUBSCRIBED`: có feedback ngừng nhận.

Nhưng chúng có giới hạn:

- Privacy proxy hoặc client có thể tải pixel trước khi người dùng thực sự đọc.
- Client chặn ảnh có thể khiến email được đọc nhưng không có open event.
- Security scanner hoặc link prefetch có thể kích hoạt click không do người dùng trực tiếp thao tác.
- Một provider có thể không bật open/click tracking; email transactional có thể không nên bị theo dõi bằng pixel.
- Việc dùng tracking cần tuân thủ thông báo/quyền riêng tư và chính sách sản phẩm.

Không lấy `openRate` để trực tiếp khẳng định Inbox placement, và không xem `click` là chứng cứ tuyệt đối một con người đã nhấn.

## 36. Quan sát Inbox placement là một bài toán riêng

Remote delivery không nói chính xác thư đi vào:

```text
Inbox
Promotions / Other tab
Junk / Spam
Quarantine
Mailbox rule folder
```

Để đánh giá Inbox placement, có thể sử dụng:

- Seed mailboxes thuộc nhiều dịch vụ để kiểm tra mẫu.
- Test inbox có sự đồng ý và quyền truy cập.
- Các công cụ đánh giá placement/reputation phù hợp.
- Tín hiệu hỗ trợ từ recipient/provider khi được phép.

Đây là **ước lượng theo mẫu**, không thể được suy ra hoàn toàn từ `JavaMailSender` hay event `delivered`. Cũng không nên triển khai cơ chế đăng nhập hộp thư cá nhân của khách hàng để đo Inbox mà không có quyền và mục đích rõ ràng.

## 37. Một dashboard đa provider hữu ích

Đề xuất nhóm thành ba lớp:

### Lớp vận hành submission

```text
Provider A/B/C
  - attempts/s
  - SMTP/API acceptance errors
  - p95 submit duration
  - 4xx/5xx groups
  - unknown outcomes
  - queue age / worker utilization
```

### Lớp deliverability feedback

```text
By mature cohort, message class, provider, domain group
  - remote delivered %
  - bounced %
  - deferred %
  - rejected/suppressed %
  - unobserved %
  - delivery latency p50/p95
  - sample size
```

### Lớp chất lượng telemetry

```text
  - incoming webhooks / invalid signatures
  - provider event coverage
  - duplicate rate
  - unmatched event count and age
  - processing lag
  - reconciliation backlog
```

Dashboard nên hiển thị **đơn vị, mẫu số, tuổi cohort, số lượng quan sát và độ tin cậy của nguồn**. Một biểu đồ không có các thông tin ấy dễ dẫn đến quyết định chuyển provider sai.

## 38. Alerts và SLO nên gắn với mục tiêu nghiệp vụ

Với transactional mail nhạy thời gian, có thể theo dõi:

- Tỷ lệ submission thành công trong khoảng thời gian ngắn.
- `p95` thời gian từ yêu cầu tới SMTP accepted.
- `p95` thời gian đến remote delivered khi feedback đáng tin.
- Tỷ lệ notification đã quá tuổi SLA nhưng chưa có outcome.
- Số email OTP không còn hiệu lực trước khi đạt submission/delivery.

Với bulk campaign:

- Bounce/complaint rate theo cohort lớn hơn.
- Suppression and unsubscribe compliance.
- Throttling/deferral theo recipient domain.
- Capacity/rate limit của từng provider route.

### Tránh alert noise

Một tỷ lệ bounce 10% từ 10 email không cùng ý nghĩa thống kê với 10% từ 100.000 email. Alert nên có:

1. Minimum sample size.
2. Cohort đủ tuổi.
3. Baseline theo provider và message class.
4. Nhiều cửa sổ thời gian hoặc threshold có ý nghĩa.
5. Kết hợp coverage để phát hiện webhook outage.
6. Phân loại severity theo tác động nghiệp vụ.

Không tự động failover toàn bộ lưu lượng chỉ vì một biến động ngắn của một metric có ít mẫu.

## 39. Khi nào nên chuyển provider?

Đa provider cho phép chọn tuyến gửi khác nhau, nhưng **failover không đồng nghĩa mọi email bị lỗi đều phải gửi lại qua nhà cung cấp khác**.

Phân loại theo bằng chứng:

| Trạng thái ở provider A | Có nên thử B ngay? | Lý do |
| --- | --- | --- |
| Không mở được TCP connection, chưa gửi DATA | Có thể, theo policy | Có bằng chứng chưa submit qua kết nối thất bại |
| SMTP AUTH sai credential | Không retry mù | Cần sửa cấu hình/route; B có thể hoạt động nhưng phải được phép |
| Provider trả 421/4xx tạm thời trước acceptance | Có điều kiện | Cần tôn trọng throttling, rate limit và route health |
| Recipient bị 550 vì địa chỉ/policy | Thường không | Provider B không làm recipient hợp lệ hơn; có thể là hành vi né kiểm soát |
| Provider báo suppressed/unsubscribed | Không | Phải tôn trọng suppression và sở thích nhận thư |
| Provider A đã accepted, đang deferred | Không tự động | A có thể tiếp tục giao; B sẽ tăng nguy cơ duplicate |
| Mất phản hồi cuối sau DATA | Không tự động | A có thể đã nhận; outcome là `UNKNOWN` |
| Provider A accepted nhưng delivery event bị trễ | Không chỉ vì thiếu webhook | Thiếu feedback không phải bằng chứng lỗi |
| Provider A có sự cố đã xác minh trước submission | Có thể chuyển route cho **attempt mới** | Cần lưu quyết định và ngăn duplicate |

Routing có thể tối ưu **future notifications** ngay khi route A gặp sự cố, nhưng retry những attempts trước đó cần xét trạng thái của từng message.

## 40. Khác biệt giữa routing và failover

**Routing**: chọn provider trước khi gửi một notification mới.

```text
New notification
        |
        +-- category=transactional -> Provider A
        +-- category=bulk          -> Provider B
        +-- region=restricted      -> Approved regional route
```

**Failover**: một attempt đã thử qua provider A không đạt mục tiêu, nên hệ thống cân nhắc attempt tiếp theo qua B.

```text
Notification N-100
        |
        v
Attempt A-1 -> Provider A
        |
        +-- outcome is definitely NOT SUBMITTED
                    |
                    v
              Policy allows retry
                    |
                    v
Attempt A-2 -> Provider B
```

Hai operation này có rủi ro khác nhau. Routing chọn đường trước lần thử thường không tạo duplicate; failover sau một lần thử `UNKNOWN` có thể tạo duplicate.

## 41. Ví dụ router abstraction cho nhiều JavaMailSender

Ứng dụng có thể tạo một `JavaMailSender` riêng cho từng provider SMTP với host/port, credential và TLS properties tương ứng:

```java
import org.springframework.mail.javamail.JavaMailSender;
import java.util.Map;

public record SelectedMailRoute(
        String providerKey,
        String providerScope,
        JavaMailSender sender
) {}

public final class MailProviderRouter {

    private final Map<String, SelectedMailRoute> routes;

    public MailProviderRouter(
            Map<String, SelectedMailRoute> routes
    ) {
        this.routes = Map.copyOf(routes);
    }

    public SelectedMailRoute require(String routeKey) {
        SelectedMailRoute route = routes.get(routeKey);
        if (route == null) {
            throw new IllegalArgumentException(
                    "Unknown approved mail route");
        }
        return route;
    }
}
```

Đây là abstraction do ứng dụng định nghĩa, không phải class có sẵn trong Spring Mail. Nó chỉ nhận route **đã được cấp quyền**.

### Sender được chọn trước khi tạo MimeMessage

```java
public void submit(
        UUID notificationId,
        String routeKey,
        String recipient,
        String subject,
        String body
) throws MessagingException {

    SelectedMailRoute route = router.require(routeKey);

    // Persist attemptId + providerKey + scope trước khi gửi.
    UUID attemptId = startAttempt(
            notificationId, route.providerKey(),
            route.providerScope());

    MimeMessage message = route.sender().createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message, false, "UTF-8");

    helper.setFrom("notice@example.org");
    helper.setTo(recipient);
    helper.setSubject(subject);
    helper.setText(body, false);

    try {
        route.sender().send(message);
        recordSubmitted(attemptId);
    } catch (MailException error) {
        recordSubmissionFailure(attemptId, error);
        throw error;
    }
}
```

`startAttempt`, `recordSubmitted` và `recordSubmissionFailure` là các method do ứng dụng triển khai. Ví dụ chưa thể hiện transactional outbox, lease, exception classification hay recipient-level outcome đầy đủ.

**Không giữ một database transaction mở suốt SMTP I/O.** Lưu attempt bằng giao dịch ngắn, submit bên ngoài giao dịch, rồi ghi kết quả bằng giao dịch ngắn khác. Khi crash sau SMTP acceptance nhưng trước khi ghi `SUBMITTED`, trạng thái có thể mơ hồ và phải được xử lý như một vấn đề reliability thực sự.

## 42. Tách deliverability và route health

Một provider có thể:

- **Route healthy:** SMTP connect/auth/submit rất nhanh, tỉ lệ lỗi tức thì thấp.
- **Deliverability kém:** remote MTA thường trì hoãn hoặc từ chối cho một số domain.

Hoặc ngược lại:

- **Route có latency cao:** SMTP submission chậm.
- **Remote delivery tốt:** khi đã accepted, phần lớn message giao thành công.

Nếu router chỉ dùng latency `JavaMailSender.send`, nó có thể chọn route nhanh nhất nhưng giao thư kém cho một nhóm người nhận. Nếu router chỉ nhìn bounce events vài giờ trước, nó có thể phản ứng chậm với outage SMTP hiện tại.

Một hệ thống routing nên xét nhiều tín hiệu:

| Nhóm | Ví dụ | Khoảng thời gian |
| --- | --- | --- |
| Submission health | Connect failures, SMTP 4xx/5xx, p95 submit latency | Giây/phút |
| Provider processing | Accepted/deferred backlog, provider status | Phút |
| Remote delivery | Cohort delivered/bounced/unobserved | Giờ/ngày |
| Sender reputation | Complaint/suppression, authentication and domain signals | Ngày/tuần |
| Capacity | Quota, connections, rate limits | Gần real-time |

Không trộn các tín hiệu có độ trễ và phạm vi khác nhau thành một “điểm provider” không giải thích được.

## 43. Suppression phải được quản lý xuyên provider

Mỗi provider có thể có danh sách suppression riêng để tránh gửi lại đến địa chỉ bounce hoặc complaint. Nếu ứng dụng dùng A và B:

```text
Provider A receives complaint for recipient R
                  |
                  v
Provider A suppression list
                  |
                  v
Application switches to Provider B
                  |
                  v
Provider B might not know suppression on A
```

Đó là một rủi ro nghiêm trọng. Nếu B không biết người nhận đã unsubscribe hoặc complaint trên A, failover có thể tiếp tục gửi một thư không mong muốn.

### Chính sách trung tâm

Ứng dụng nên có một nguồn chính sách thống nhất cho:

- Opt-out hoặc unsubscribe theo loại nội dung.
- Complaint/suppression theo recipient và phạm vi consent.
- Bounce không thể phục hồi theo policy.
- Tenant/account-specific do-not-contact.
- Yêu cầu pháp lý hoặc cam kết khách hàng.

Trước khi chọn route:

```text
Notification
     |
     v
Recipient eligibility / suppression check
     |
     +-- not allowed --> SUPPRESSED (no SMTP send)
     |
     +-- allowed --> route selection --> attempt
```

Không phải mọi loại email đều có cùng chính sách suppression: thông báo transactional, bảo mật, marketing có yêu cầu và cơ sở gửi khác nhau. Cần định nghĩa rõ theo nghiệp vụ và quy định áp dụng; **không dùng chuyển provider để né spam complaint hoặc opt-out**.

## 44. DNS authentication khi gửi qua nhiều provider

Deliverability không chỉ do API/Webhook. Mỗi provider hoặc route có thể yêu cầu cấu hình domain:

- SPF và envelope/return-path configuration.
- DKIM signing key/selector.
- DMARC alignment với domain hiển thị trong From.
- Custom tracking domain, nếu có.
- Bounce domain và feedback mailbox.
- TLS policy khi submit SMTP.

Khi thêm provider mới, nếu DNS/authentication chưa đầy đủ, message có thể được provider chấp nhận nhưng bị remote server đánh giá kém hơn.

### Bảng kiểm theo route

| Hạng mục | Provider A | Provider B | Ý nghĩa |
| --- | --- | --- | --- |
| Approved sender domain | Đã cấu hình? | Đã cấu hình? | Có quyền gửi From domain |
| DKIM signing | Đã xác minh? | Đã xác minh? | Tín hiệu xác thực thông điệp |
| SPF/envelope alignment | Phù hợp route? | Phù hợp route? | Tránh cấu hình return-path sai |
| DMARC policy/alignment | Kiểm tra | Kiểm tra | Đánh giá xác thực domain |
| Bounce/complaint feedback | Có hoạt động? | Có hoạt động? | Đủ telemetry và suppression |
| Tracking/links | Đúng domain và privacy policy? | Đúng? | Ảnh hưởng an toàn và đo lường |
| Rate limits/warm-up | Hiểu rõ? | Hiểu rõ? | Tránh throttling và reputation issues |

Không mặc định chỉ cần sao chép `spring.mail.host` sang host khác là đạt deliverability tương đương.

## 45. Reputation và warm-up khác nhau theo provider

Hai provider có thể có lịch sử danh tiếng, IP/domain pool, giới hạn throughput và chính sách xử lý khác nhau. Khi chuyển một lượng lớn traffic:

- Tốc độ gửi tăng đột ngột có thể khiến recipient servers throttling.
- Danh sách nhận kém chất lượng có thể gây bounce/complaint trên route mới.
- Shared IP pool hoặc dedicated IP có trade-off khác nhau.
- Một route đang được warm-up không nên nhận toàn bộ tải lớn ngay.
- Sender domain authentication và nội dung giống nhau vẫn không bảo đảm kết quả delivery giống nhau.

**Chuyển 100% traffic ngay khi dashboard báo A kém hơn B vài phần trăm** là quyết định dễ gây side effect. Nên áp dụng rollout có giới hạn, kiểm soát volume, quan sát cohort trưởng thành và so sánh cùng loại traffic.

## 46. Controlled experiment để so sánh provider

Nếu cần đánh giá thật sự provider nào phù hợp cho một loại email, có thể thiết kế thử nghiệm:

1. Chọn một tập notification đủ điều kiện, có consent và loại nội dung đồng nhất.
2. Chia traffic **ngẫu nhiên nhưng có kiểm soát** theo provider, không gửi hai bản cho cùng một người.
3. Giữ ổn định template, nội dung, From domain và tiêu chí recipient nếu có thể.
4. Kiểm tra DNS/authentication của cả hai route.
5. Cân bằng recipient-domain distribution.
6. Chọn cohort và mẫu số giống nhau.
7. Quan sát đủ thời gian cho deferred/bounce feedback.
8. Kiểm tra coverage và missing events ở từng provider.
9. Đo submission latency, remote delivery, complaint và chi phí.
10. Dừng hoặc giảm traffic nếu có tín hiệu rủi ro thật.

### Không gửi thử hai thư giống nhau tới cùng người nhận

Nếu người nhận nhận hai email chỉ để “đo provider A vs B”, kết quả có thể bị nhiễu bởi thư trùng, spam filtering và ảnh hưởng trải nghiệm. Đối với email nghiệp vụ hoặc OTP, thử nghiệm cần bảo đảm chỉ một attempt hợp lệ được cấp quyền gửi tại một thời điểm.

### So sánh segment, không chỉ tổng

Đặc biệt xem:

- Recipient domain group.
- Nội dung transactional hay campaign.
- Kích thước MIME.
- Giờ gửi và phân bố tải.
- Tài khoản/provider pool.
- Tuổi cohort và event coverage.

Một thử nghiệm tốt cần ghi cả **cách lấy mẫu và hạn chế của dữ liệu**, không chỉ kết quả phần trăm.

## 47. Failover sau UNKNOWN: cửa sổ gửi trùng

Tình huống:

```text
Attempt 1: Provider A
  - Application transmits MIME DATA
  - Connection drops before final response
  - Application records UNKNOWN

Immediately:
Attempt 2: Provider B
  - B accepts the same notification

Later:
  - Provider A sends DELIVERED event
  - Provider B sends DELIVERED event
```

Cả hai provider có thể đã submit cùng một notification. Kết quả là có khả năng người nhận nhận **hai bản**, dù mỗi `JavaMailSender` attempt được gọi một lần.

### Cách hạn chế

- Không failover tự động những `UNKNOWN` khi không có chính sách chấp nhận duplicate.
- Dùng provider query/reconciliation nếu hỗ trợ.
- Giữ attempt history và event correlation riêng cho A/B.
- Không xem `Message-ID` chung là cam kết provider tự loại duplicate.
- Khi quyết định resend, ghi `resendReason` và actor/policy.
- Với email nhạy thời gian, cân bằng độ trễ với nguy cơ gửi trùng theo nghiệp vụ.
- Nếu provider hỗ trợ idempotency cho API cụ thể, dùng đúng phạm vi và điều kiện của API đó.

Exactly-once **SMTP delivery** không được Spring Mail hay transactional outbox bảo đảm chung.

## 48. Không failover vì provider đang tự retry deferred

`DEFERRED` là trạng thái provider có thể còn tiếp tục thử delivery. Nếu ứng dụng ngay lập tức gửi một bản nữa qua B:

```text
A deferred + A retries later
B submitted now
        |
        v
Recipient may receive both
```

Để xử lý đúng cần biết:

1. Provider có tiếp tục retry hay đã terminal?
2. Event là temporary deferral hay final failure?
3. Ứng dụng có khả năng cancel attempt trong queue của provider hay không?
4. Provider có đảm bảo một yêu cầu hủy đã được áp dụng trước khi B submit không?
5. Người nhận có chấp nhận rủi ro duplicate không?

Trong đa số trường hợp, nên để provider hoàn thành retry lifecycle theo contract, và chỉ chuyển route cho **notification mới** hoặc những attempt đã xác định chắc chắn không được submit.

## 49. Cùng một raw event name chưa chắc cùng một ý nghĩa

Một ví dụ giả định về hai provider:

| Event của provider | Ý nghĩa đã kiểm tra trong tích hợp | Mapping |
| --- | --- | --- |
| A: `processed` | Đã nhận vào queue nội bộ | `PROVIDER_ACCEPTED` |
| A: `delivered` | Server đích đã chấp nhận | `DELIVERED_REMOTE` |
| B: `accepted` | Provider đã nhận yêu cầu | `PROVIDER_ACCEPTED` |
| B: `sent` | Provider đã chuyển vào pipeline gửi, chưa có remote proof | Không map thẳng sang `DELIVERED_REMOTE` |
| B: `temporary_failure` | Thử giao chưa xong, còn retry | `DEFERRED` |
| B: `final_failure` | Outcome terminal theo policy | `BOUNCED` hoặc `PROVIDER_REJECTED` tùy stage |

Bảng này là **taxonomy giả lập để minh họa cách thiết kế adapter**, không phải bản mapping được xác minh cho một provider có tên thương mại. Trong dự án thật, contract của provider và endpoint cụ thể mới quyết định mapping.

### Cần lưu lại raw event type để truy nguyên

Nếu một provider thay đổi tên event hoặc bổ sung phân loại mới, việc chỉ lưu canonical enum khiến khó điều tra event đã được chuyển đổi ra sao.

Nên giữ:

```text
providerKey
providerScope
providerEventType
canonicalEventType
mappingVersion
sourceSchemaVersion
```

Khi mapping logic thay đổi, có thể tái dựng projection từ event ledger đã lưu nếu retention/contract cho phép. Không âm thầm đổi lịch sử theo mapping mới mà không có dấu phiên bản.

## 50. Đặt tên metric tránh nhầm giữa event và message

Ví dụ dùng Micrometer:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class MailFeedbackMetrics {

    private final MeterRegistry registry;

    public MailFeedbackMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordAcceptedEvent(
            String approvedProviderLabel,
            CanonicalMailEventType type
    ) {
        Counter.builder("mail.feedback.events.accepted")
                .tag("provider", approvedProviderLabel)
                .tag("canonical_type", type.name())
                .register(registry)
                .increment();
    }
}
```

Trong ví dụ, `approvedProviderLabel` phải được chọn từ danh sách route đã cấu hình, không nhận trực tiếp chuỗi tùy ý trong webhook. `type.name()` có cardinality hữu hạn vì enum được kiểm soát.

**Counter này đếm số event hợp lệ được chấp nhận vào pipeline**, không phải số email delivery duy nhất. Nếu không gọi sau dedupe, cùng một webhook retry có thể bị đếm nhiều lần.

Để tính delivered rate, hãy dùng **distinct recipient-attempt outcomes từ projection hoặc truy vấn cohort**, không lấy một counter tổng tất cả event và chia cho số lần gọi `JavaMailSender.send`.

## 51. Đếm theo event-time hay receive-time?

Hai hệ thống dashboard có thể khác nhau dù cùng dữ liệu:

```text
Event happened: 10:00 yesterday
Webhook received: 11:00 today
```

- Dashboard theo **receivedAt** cho biết khi nào hệ thống ingest feedback.
- Dashboard theo **occurredAt** cho biết provider báo sự kiện diễn ra khi nào.
- Dashboard theo **submittedAt cohort** cho biết kết quả của các notification được gửi ở khoảng thời gian nào.

Mỗi cách phục vụ mục đích riêng:

| Thời gian | Dùng cho |
| --- | --- |
| `submittedAt` | Cohort delivery/SLO theo lứa notification |
| `occurredAt` | Timeline hoạt động của provider nếu timestamp đáng tin |
| `receivedAt` | Webhook ingestion health và event delay |
| `projectedAt` | Độ trễ xử lý nội bộ |
| `reconciledAt` | Thời điểm hệ thống bổ sung bằng chứng |

Không trộn các trục thời gian vào một biểu đồ mà không ghi nhãn; nếu event đến muộn, báo cáo cohort trước đó có thể thay đổi sau khi tính lại.

## 52. Một pipeline có thể có hai kiểu retry khác nhau

**Retry gửi email** và **retry xử lý webhook** là hai thao tác độc lập:

```text
Outbound retry:
Notification -> Provider submit attempt 1
             -> Provider submit attempt 2 (nếu được phép)

Inbound retry:
Provider sends DeliveryEvent E
          -> Webhook request retry E
          -> Inbox projector retry E
```

Inbound retry **không có nghĩa được gửi lại email**. Một webhook duplicate phải được khử trùng lặp hoặc xử lý idempotently, không kích hoạt thêm `JavaMailSender.send(...)`.

Ví dụ sai:

```java
if (event.canonicalType() == CanonicalMailEventType.DEFERRED) {
    mailSender.send(originalMimeMessage);
}
```

Provider có thể đang tự retry. Ứng dụng không nên tạo thêm submission attempt chỉ vì nhận `DEFERRED`; cần policy rõ ràng về terminal outcome, cancellation, suppression và duplicate.

## 53. Xử lý event batch và lỗi một phần

Một callback có thể mang nhiều events. Ví dụ:

```json
[
  {"event_id":"e-1","type":"delivered","message_id":"m-1"},
  {"event_id":"e-2","type":"deferred","message_id":"m-2"},
  {"event_id":"e-3","type":"bounced","message_id":"m-3"}
]
```

JSON này là **fixture giả** minh họa batch, không phải schema chung của bất kỳ provider nào.

Cần xác định theo provider contract:

- Một request có thể chứa bao nhiêu sự kiện?
- Chữ ký áp dụng cho toàn raw request hay từng event?
- Acknowledgment áp dụng cho toàn batch hay từng item?
- Nếu một item sai schema, có reject toàn batch không?
- Provider có retry lại toàn batch khi request fail không?
- Có thể nhận nhiều recipient của cùng message trong một event không?

Để không mất dữ liệu, có thể lưu **raw verified envelope reference** và các normalized event entries theo transaction phù hợp. Nếu chọn all-or-nothing, callback lỗi có thể được provider retry; nếu cho phép partial accept, cần contract cho việc acknowledgment từng item. Không tự bịa ra per-item acknowledgment khi API chỉ hỗ trợ HTTP status toàn request.

## 54. Contract test cho từng adapter

Một adapter provider nên được kiểm thử bằng **fixture giả lập đã xác minh từ tài liệu hoặc sandbox** của provider ấy.

Các test quan trọng:

1. Payload hợp lệ, signature hợp lệ: parse và normalize thành canonical event đúng.
2. Signature không hợp lệ: reject trước khi ghi trạng thái.
3. Payload bị sửa một byte: không còn được xem là hợp lệ nếu cơ chế chữ ký bảo vệ byte ấy.
4. Timestamp quá hạn/replay không được chấp nhận, khi provider hỗ trợ timestamp signature.
5. Event type chưa biết: giữ `UNKNOWN` và raw type cho điều tra, không biến thành DELIVERED.
6. Event thiếu message ID: lưu uncorrelated nếu không có khóa đáng tin.
7. Event có nhiều recipients: tạo đúng số observation theo contract.
8. Duplicate event ID: event inbox chỉ lưu/áp dụng một lần theo khóa dedupe.
9. Nhiều account có event ID giống nhau: không dedup chéo account.
10. Event timestamp dùng timezone/precision khác nhau: normalize đúng hoặc đánh dấu missing.
11. Event có diagnostic text nhạy cảm: không đi vào metrics/log.
12. Key rotation: chấp nhận key hợp lệ trong cửa sổ chuyển đổi theo contract.

Không cần gọi provider thật trong unit test mapper. Integration/sandbox test kiểm tra thêm endpoint, auth và event publication đúng theo account cấu hình.

## 55. Test webhook idempotency và sai thứ tự

Một scenario:

```text
Event E1 = DELIVERED_REMOTE
Event E2 = PROVIDER_ACCEPTED
Event E3 = DEFERRED

Delivery order to webhook:
E1, E1 again, E3, E2
```

Kỳ vọng:

- Event E1 được lưu một lần nếu provider event ID ổn định.
- Callback E1 lặp lại được acknowledgment an toàn.
- E2/E3 không làm mất evidence đã delivered.
- Projection thể hiện delivered đúng theo policy.
- Event history vẫn cho thấy E3/E2 đến muộn.
- Metric remote delivered unique recipient-attempt không tăng gấp đôi.
- Số duplicate webhook có thể được đo riêng.

### Pseudocode assertion

```java
// Pseudocode: eventFixtures, inbox, projector do app test cung cấp.
deliver(eventFixtures.delivered("e-1", "m-1"));
deliver(eventFixtures.delivered("e-1", "m-1"));
deliver(eventFixtures.deferred("e-3", "m-1"));
deliver(eventFixtures.accepted("e-2", "m-1"));

assertEquals(3, inbox.uniqueEventCount());
assertEquals(
        DeliveryState.DELIVERED_REMOTE,
        projector.outcomeFor("m-1")
);
assertEquals(1, projector.uniqueDeliveredCount());
```

Đoạn này mô tả kỳ vọng, không phải mã có thể compile độc lập. Trong hệ thống thật, `projector.outcomeFor(...)` phải dùng khóa đã namespace và tương quan đúng recipient/attempt; dùng riêng `"m-1"` ở đây chỉ để fixture ngắn gọn.

## 56. Test không match được message ID

Một provider event:

```json
{
  "event_id": "event-demo-104",
  "type": "delivered",
  "message_id": "unknown-demo-message"
}
```

Kỳ vọng:

- Chữ ký hợp lệ thì event được lưu bền vững.
- `correlation_state=UNMATCHED`.
- Không cập nhật ngẫu nhiên notification gần thời điểm ấy.
- Có retry correlation và metric `unmatched_events`.
- Nếu hết retention mà vẫn không ghép được, có incident/review policy.

Một test tốt cũng bảo đảm event từ `provider-a/account-1` không ghép với attempt của `provider-b/account-2` dù tình cờ có cùng providerMessageId.

## 57. Test failover khi chắc chắn chưa submit

Thiết lập hai SMTP test server:

```text
Provider A test endpoint: refused connection
Provider B test endpoint: accepts MAIL/RCPT/DATA
```

Kỳ vọng:

1. Attempt A-1 ghi provider A và connection failure trước submission.
2. Retry policy xác nhận có thể chuyển route (không vượt suppression).
3. Attempt A-2 ghi provider B, không sửa đè A-1.
4. B nhận đúng một DATA transaction của notification.
5. Recipient outcome có thể được cập nhật từ event mô phỏng của B.
6. Dashboard đếm **hai submit attempts**, nhưng **một notification**.

Nếu có nhiều recipient, cần phân biệt số recipient-attempt và message attempt; không biến “hai attempts” thành hai người nhận.

## 58. Test không failover khi kết quả UNKNOWN

Thiết lập server A đọc xong `DATA` rồi ngắt kết nối trước final reply; server B có thể chấp nhận nhưng phải **không được gọi tự động** khi policy không cho phép.

Kỳ vọng:

- Attempt A được ghi `UNKNOWN`.
- Không có submission request tự động sang B.
- Có reconciliation hoặc vận hành xử lý.
- Nếu event A về sau cho biết delivered, projection cập nhật attempt A.
- Nếu người vận hành chủ động resend theo policy, tạo attempt B riêng với lý do rõ ràng.

Điều này đặc biệt quan trọng khi ứng dụng gửi OTP, hóa đơn hoặc thông báo giao dịch: một bản trùng có thể gây nhầm lẫn hoặc side effect ngoài email.

## 59. Test suppression xuyên provider

Một kiểm thử nghiệp vụ:

```text
Provider A event: COMPLAINED for recipient R
        |
        v
Central recipient policy updated
        |
        v
New notification for R tries route B
        |
        v
Suppressed before SMTP send
```

Kỳ vọng:

- Event complaint được gắn đúng recipient.
- Policy của loại thư liên quan phản ánh suppression.
- Router không gọi `JavaMailSender.send` qua B khi policy cấm.
- Audit record giải thích `SUPPRESSED`.
- Không coi message không gửi là `BOUNCED` của B.

Chính sách loại trừ/ngoại lệ cho email giao dịch, bảo mật hay marketing phải được định nghĩa rõ trong nghiệp vụ và quy định áp dụng; test cần theo **policy thực tế**, không dùng một rule chung không được thẩm định.

## 60. Test provider API reconciliation

Nếu provider có API query message status, integration test nên kiểm tra luồng:

1. Một attempt đã `SUBMITTED` nhưng webhook chưa xuất hiện.
2. Reconciliation worker chọn attempt **đủ tuổi** và chưa có outcome.
3. Adapter dùng provider/account/scope và message ID hợp lệ để query.
4. Response test cho biết `DELIVERED_REMOTE`.
5. Bằng chứng được lưu với `source=PROVIDER_QUERY`.
6. Khi webhook `DELIVERED_REMOTE` đến sau, projection không tăng delivered count lần nữa.
7. Nếu provider API trả `NOT_FOUND` vì đã hết retention hoặc chưa index, không tự kết luận email đã fail.
8. API 429/5xx được retry với backoff và giới hạn quota.

Nhà cung cấp không có API query phải có chiến lược khác, ví dụ timeout observation có nhãn `UNOBSERVED`, hoặc DSN/bounce feedback nếu được hỗ trợ. Không viết một “reconciliation universal” giả định mọi provider có endpoint truy vấn.

## 61. DSN và bounce mailbox khi provider không có webhook

Một số hệ thống dựa vào **Delivery Status Notification (DSN)** hoặc mailbox nhận bounce thay vì webhook:

```text
Application -> SMTP relay
     |
     v
Remote delivery fails
     |
     v
DSN/bounce to configured return-path
     |
     v
Bounce mailbox processor
     |
     v
Parse + correlate + normalize event
```

Cần nhớ:

- `Return-Path` liên quan envelope sender, không chỉ là một header ứng dụng có thể đặt tùy ý.
- Không phải mọi failure đều sinh DSN mà ứng dụng truy cập được.
- DSN có thể đến rất trễ hoặc không mang tất cả metadata mà ứng dụng mong đợi.
- Bounce email có thể chứa toàn bộ hoặc một phần header/nội dung thư gốc, nên dữ liệu nhạy cảm.
- Parser phải xử lý MIME đa dạng và nguồn mail không tin cậy; không nên dựa vào regex một dòng.
- Cần xác thực nguồn/độ tin cậy của feedback để tránh spoofed bounce làm tắt gửi nhầm.

Nếu không có feedback đáng tin, dashboard phải công khai giới hạn thay vì biến SMTP submission thành remote delivered.

## 62. Một provider có thể có nhiều account, region hoặc subaccount

Provider key đơn giản có thể không đủ:

```text
provider-a
    |
    +-- account-transactions / region-1
    +-- account-marketing / region-1
    +-- account-support / region-2
```

Mỗi account/scope có thể khác:

- Credentials và webhook signing secret.
- Sending domain/return-path.
- Suppression/feedback settings.
- Event retention và query API permissions.
- Quota, rate limit, reputation.
- Endpoint và data residency.

Tương quan phải namespace provider message ID bằng `providerScope`; hệ thống event receiver cũng phải biết **chữ ký/credentials nào được phép cho scope ấy**.

Không chọn account/scope từ một header webhook chưa xác thực rồi dùng nó truy cập secrets tùy ý. Endpoint registry và verification policy cần kiểm soát giá trị được chấp nhận.

## 63. Secret và key rotation của nhiều provider

Mỗi route thường có ít nhất hai nhóm secret:

- Credentials để **submit** SMTP/API.
- Keys/token để **xác minh feedback** webhook/event source.

Hai nhóm này không nhất thiết dùng cùng cơ chế hoặc vòng đời. Một thiết kế an toàn:

| Secret | Dùng ở đâu | Quy tắc |
| --- | --- | --- |
| SMTP password/API key | Outbound sender | Không log, giới hạn quyền gửi |
| Webhook verification key | Inbound receiver | Không dùng như outbound credential |
| Reconciliation API token | Background query worker | Scope chỉ đọc khi có thể |
| HMAC key nội bộ | Correlation/hash nhạy cảm nếu dùng | Quản lý riêng, rotation |

Khi rotation:

1. Xác định provider hỗ trợ giai đoạn overlap key hay không.
2. Cập nhật key theo đúng contract provider.
3. Test signature hợp lệ với key đang active.
4. Không ngắt nhận webhook trong khi callback cũ còn được retry.
5. Không giữ token đã thu hồi vô thời hạn.
6. Audit người thay đổi cấu hình và route.

Không đưa credential vào `application.yml` commit lên repository. Dùng secret manager/environment được kiểm soát và tránh in cấu hình đầy đủ trong error handler.

## 64. Quyền riêng tư của recipient và dữ liệu sự kiện

Webhook có thể chứa địa chỉ email, bounce diagnostic, user agent, IP hoặc URL. Những trường này có thể là dữ liệu cá nhân hoặc dữ liệu nhạy cảm theo chính sách.

Nguyên tắc:

- Dùng `recipientId` nội bộ trong projection; chỉ truy ra email tại service được cấp quyền.
- Không ghi raw recipient email vào metric labels.
- Không log toàn bộ callback body hoặc SMTP diagnostic.
- Nếu lưu raw event, có encryption, access control và retention.
- Đối với tracking open/click, đánh giá mục đích, thông báo/consent và chính sách sử dụng phù hợp.
- Bảo vệ Bcc; không đưa danh sách người nhận ẩn vào dashboard mở rộng.
- Có chính sách xóa dữ liệu khỏi event store/analytics khi cần theo quy định và cam kết.

Một provider có thể yêu cầu lưu dữ liệu tại khu vực cụ thể; routing qua một provider khác có thể làm thay đổi phạm vi xử lý dữ liệu. Failover cần xem cả **điều kiện pháp lý/contract** chứ không chỉ health metric.

## 65. Ví dụ truy vấn dashboard từ projection

Giả sử hệ thống có một bảng projection `mail_recipient_outcome`, **mỗi dòng cho một recipient-attempt**, gồm:

```text
attempt_id
recipient_id
provider_key
message_class
submitted_at
delivery_state
feedback_coverage_state
```

Một truy vấn PostgreSQL minh họa cho cohort đã đủ 24 giờ:

```sql
SELECT
    provider_key,
    COUNT(*) AS recipient_attempts,
    COUNT(*) FILTER (
        WHERE delivery_state = 'DELIVERED_REMOTE'
    ) AS delivered,
    COUNT(*) FILTER (
        WHERE delivery_state = 'BOUNCED'
    ) AS bounced,
    COUNT(*) FILTER (
        WHERE delivery_state = 'DEFERRED'
    ) AS deferred,
    COUNT(*) FILTER (
        WHERE feedback_coverage_state = 'UNOBSERVED'
    ) AS unobserved
FROM mail_recipient_outcome
WHERE message_class = 'TRANSACTIONAL'
  AND submitted_at >= :cohortStart
  AND submitted_at < :cohortEnd
  AND submitted_at < now() - interval '24 hours'
GROUP BY provider_key
ORDER BY provider_key;
```

Đây là **SQL minh họa**; bảng projection và trạng thái phải do ứng dụng triển khai. Nếu một notification có nhiều attempts hoặc nhiều recipients, mẫu số sẽ là recipient-attempt, không phải unique notification.

Nếu muốn đo **unique notification delivered eventually**, cần một truy vấn khác tổng hợp trên `notificationId + recipientId` sau khi xử lý các attempts và duplicate. Không thể lấy kết quả theo attempt rồi đổi tên thành kết quả theo notification.

### Điều gì nên nằm bên cạnh bảng số?

- Cohort từ ngày nào đến ngày nào.
- Đã chờ bao lâu sau submit.
- Có bao nhiêu event chưa map được.
- Provider nào không cung cấp đủ loại feedback.
- Outcome được tính theo attempt hay notification.
- Phạm vi account/region.
- Các sự kiện bị late/replayed trong khoảng đo.

Đây là metadata bắt buộc để người vận hành không diễn giải sai chênh lệch giữa provider.

## 66. Runbook khi tỷ lệ delivered của một provider giảm

Giả sử dashboard báo Provider A giảm từ mức bình thường xuống thấp hơn rõ rệt. Không nên lập tức đổi toàn bộ route sang B.

### Bước 1 — Kiểm tra telemetry trước

- Có webhook callbacks không?
- Tỷ lệ invalid signature tăng đột ngột không?
- Inbox event queue có backlog không?
- Có thay signing key hoặc endpoint gần đây không?
- Dữ liệu có bị thiếu một account/region không?
- Event coverage giảm hay actual bounces/rejections tăng?

Nếu chỉ event coverage giảm, nguyên nhân có thể ở đường nhận feedback, không phải đường gửi.

### Bước 2 — Kiểm tra submission health

- `JavaMailSender.send` có tăng lỗi/timeout không?
- SMTP 4xx/5xx thuộc lệnh nào?
- Auth/TLS/connection có thay đổi không?
- Queue age có tăng?
- Provider quota/rate limit có bị chạm?

Nếu submission vẫn tốt nhưng remote delivered giảm, cần điều tra feedback/destination thay vì sửa cấu hình kết nối ngay.

### Bước 3 — So sánh cohort tương đồng

- Cùng loại thông báo.
- Cùng recipient domain group.
- Cùng giai đoạn gửi và thời gian quan sát.
- Cùng sender domain/authentication.
- Cùng định nghĩa delivered.
- Đủ sample size.

Không kết luận một provider tệ hơn nếu nó đang gánh tỷ lệ domain khó giao cao hơn hẳn.

### Bước 4 — Xem feedback chi tiết

- Bounce/deferral theo loại nguyên nhân.
- Complaint và suppression.
- Provider rejection trước delivery.
- Event đến trễ hoặc bị mất.
- Domain/account/template vừa được thay đổi.

### Bước 5 — Quyết định giảm tải hoặc chuyển route

Chỉ chọn provider B cho traffic **được phép**, qua route đã xác thực, đủ quota và không phá suppression. Với các attempts `UNKNOWN` hoặc provider A đang deferred, không tự động gửi lại.

### Bước 6 — Theo dõi sau hành động

- Routing decision và attempt history đã được lưu?
- Queue/SMTP errors có giảm?
- Provider B có bị throttling?
- Event coverage của B có đầy đủ?
- Complaint/suppression có tăng?
- Có cảnh báo duplicate do failover?

Một runbook tốt không chỉ khắc phục chỉ số trước mắt mà còn bảo đảm không tạo ra sự cố thứ hai.

## 67. Tình huống: dashboard báo deliverability bằng 0

Một provider đã được thêm vào, `JavaMailSender.send(...)` thành công, nhưng dashboard không có delivered event.

**Chẩn đoán đúng:**

1. Kiểm tra có bật subscription delivery events chưa.
2. Kiểm tra webhook URL, route, TLS và secret.
3. Kiểm tra event callback có đến receiver không.
4. Kiểm tra signature/parse/inbox/dedupe pipeline.
5. Kiểm tra provider gửi metadata có tương quan được attempt không.
6. Kiểm tra event query API hoặc log nếu provider hỗ trợ.

Nếu không có feedback, kết luận là **“không quan sát được remote delivery”**, không phải chắc chắn 0% email tới server đích.

## 68. Tình huống: A báo delivered, B chỉ báo accepted

Một dashboard lấy `A.delivered` chia tổng số gửi của A, còn `B.accepted` chia tổng số gửi B rồi đặt tên cả hai là “delivery rate”.

**Sai ở đâu?** Hai tử số phản ánh giai đoạn khác nhau. Cần chuẩn hóa event semantics, hoặc hiển thị hai chỉ số riêng với chú thích provider coverage. Không nên kết luận B tốt hơn chỉ vì có 99% accepted trong khi A có 95% delivered.

## 69. Tình huống: duplicate webhook làm delivered > 100%

Provider gửi retry của event delivered vì lần callback đầu không nhận được acknowledgment. Ứng dụng tăng counter delivered mỗi lần nhận.

**Cách sửa:** lưu event ID/scope bền vững, dedupe trong event inbox, tạo projection theo unique recipient-attempt. Đếm webhook requests và duplicate events riêng với unique delivery outcomes.

## 70. Tình huống: complaint trên A nhưng vẫn gửi từ B

Provider A báo complaint và tự đưa recipient vào suppression list của A. Router chuyển sang B vì A vừa bị rate limit.

**Nguy cơ:** B không biết policy của A nên vẫn gửi. Ứng dụng cần một suppression/eligibility policy trung tâm, kiểm tra trước routing và lưu sự kiện feedback tương ứng. Không dùng failover để bỏ qua unsubscribe/complaint.

## 71. Tình huống: webhook tới trước API response được lưu

Một event delivered có provider message ID nhưng attempt chưa được cập nhật mapping. Application không tìm thấy record và bỏ event.

**Cách sửa:** lưu event ở trạng thái `UNMATCHED`, retry correlation sau khi mapping được commit, có alert cho backlog lâu. Không tự gán theo subject hoặc recipient gần thời điểm nếu không có khóa đáng tin cậy.

## 72. Tình huống: provider A retry deferred sau khi đã chuyển sang B

A báo deferred; hệ thống lập tức gửi cùng email sang B. Sau đó A và B đều delivered.

**Cách sửa:** phân biệt deferred với final failure. Nếu A còn đang retry, không tự động submit sang B. Nếu đã làm, ledger phải gắn cả hai events vào hai attempts của cùng notification để có thể điều tra duplicate.

## 73. Tình huống: delivered nhưng người nhận báo không thấy email

Provider báo `DELIVERED_REMOTE`, còn người dùng nói không có email trong Inbox.

**Cần phân biệt:**

- Remote server đã chấp nhận email chưa?
- Có bounce/complaint hoặc policy event sau đó không?
- Email có thể ở spam/Promotions/quarantine không?
- Địa chỉ người nhận và alias có đúng không?
- Mailbox có rule chuyển thư không?
- Có thể dùng một test mailbox/seed list để tái hiện không?

Không kết luận provider nói dối hay người nhận nhầm; remote acceptance và Inbox placement là hai tầng khác nhau. Việc truy cập mailbox cá nhân cần quyền và mục đích phù hợp.

## 74. Những sai lầm thường gặp khi theo dõi đa provider

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi `JavaMailSender.send` không lỗi là delivered | Báo cáo sai tầng gửi | Ghi `SUBMITTED`, chờ provider/remote evidence |
| Map mọi `accepted/processed/sent` thành `DELIVERED_REMOTE` | Tỷ lệ giao thư bị thổi phồng | Đọc semantics từng provider |
| Chỉ lưu một `status` trên notification | Mất lịch sử attempts và các tín hiệu khác nhau | Event ledger + projection đa chiều |
| Không lưu `providerKey`/`providerScope` | Ghép nhầm message ID giữa account | Namespace correlation |
| Dùng Subject + email để match | Ghép nhầm và rủi ro PII | Provider metadata/attempt ID đáng tin |
| Đếm mọi webhook retry thành delivered mới | Delivered count vượt thực tế | Durable event inbox + dedupe |
| Ghi đè status theo thứ tự callback đến | Delivered bị thay bằng deferred cũ | Projection từ lịch sử, quy tắc rõ |
| Bỏ event chưa match | Không thể reconciliation, mất feedback | Giữ `UNMATCHED` và retry correlation |
| Không kiểm chữ ký webhook | Có thể bị giả mạo delivery/bounce/complaint | Xác thực theo provider trước khi xử lý |
| Trả `200` trước khi persist | Crash làm mất event sau acknowledgment | Durable write trước `2xx` |
| Coi không có event là thất bại | Đổ lỗi nhầm cho provider | Tách coverage và outcome |
| So sánh provider bằng tử số khác nhau | Xếp hạng sai | Thống nhất cohort, đơn vị, semantics |
| So số liệu khi cohort còn quá mới | Gán deferred thành failure | Cửa sổ observation đủ tuổi |
| Chỉ dùng tỷ lệ tổng | Bỏ qua mix recipient domains | So sánh từng phân nhóm tương đồng |
| Coi open/click là chứng cứ đọc | Sai vì proxy/scanner/client behavior | Engagement riêng, ghi giới hạn |
| Dùng delivered làm Inbox placement | Đánh giá sai vị trí thư | Seed/mailbox signals với quyền |
| Failover ngay sau timeout DATA | Có thể gửi trùng qua hai provider | `UNKNOWN` và reconciliation |
| Failover khi A vẫn deferred | A và B có thể cùng delivered | Kiểm tra finality và chính sách retry |
| Failover bỏ qua suppression | Vi phạm opt-out, tăng complaint | Chính sách eligibility chung |
| Chuyển provider nhưng chưa cấu hình DKIM/DMARC | Authentication/reputation bị ảnh hưởng | Validate domain route trước rollout |
| Ghi PII vào metric labels | Cardinality cao và lộ dữ liệu | Allowlist label, ID nội bộ |
| Chỉ kiểm thử happy-path webhook | Không chịu được invalid/duplicate/out-of-order | Contract/integration matrix |
| Coi provider event retention là vô hạn | Reconciliation không thể thực hiện sau hạn | Chính sách poll và observation cutoff |

## 75. Checklist onboarding một provider mới

### A. Đường gửi

- [ ] Đã xác nhận SMTP/API endpoint, khu vực, TLS và authentication phù hợp.
- [ ] Có sending domain và From address được phép.
- [ ] SPF, DKIM, DMARC và return-path đã kiểm tra theo cấu hình route.
- [ ] Hiểu limit về message size, recipient, throughput và connection.
- [ ] Tài khoản và quota dành cho đúng loại traffic.
- [ ] Đã xác định khi nào `send(...)` được coi là submission success.
- [ ] Đã xác định cách lưu `attemptId` và `providerMessageId` khi có.

### B. Đường feedback

- [ ] Provider có những event nào và semantics của từng event?
- [ ] Event publication đã được bật ở đúng account/region/subaccount?
- [ ] Có webhook, queue, status API hay DSN?
- [ ] Có method xác thực callback đúng tài liệu provider?
- [ ] Có cơ chế key rotation và request limit?
- [ ] Có event ID ổn định để dedupe không?
- [ ] Có metadata đáng tin để tương quan message/recipient không?
- [ ] Callback có thể chứa nhiều events và nhiều recipients không?
- [ ] Có chính sách retry callback và event retention nào?
- [ ] Có reconciliation API khi webhook bị mất không?

### C. Chuẩn hóa dữ liệu

- [ ] Raw type được map sang canonical type với mapping version.
- [ ] Bảo toàn raw type và source scope cho audit.
- [ ] Có trạng thái `UNKNOWN/UNMATCHED/UNOBSERVED` khi thiếu bằng chứng.
- [ ] Dedupe đúng provider + scope + event identity.
- [ ] Feedback state và delivery state được tách riêng.
- [ ] Không ghi đè event cũ chỉ vì webhook đến sai thứ tự.

### D. Bảo mật và tuân thủ

- [ ] Credentials gửi và verify webhook được quản lý riêng.
- [ ] Không log recipient/Subject/body/token trong event diagnostics.
- [ ] Raw payload có retention/quyền truy cập nếu cần lưu.
- [ ] Có suppression/opt-out policy trung tâm.
- [ ] Failover không bỏ qua suppression và data residency.
- [ ] Provider đã được phê duyệt cho loại dữ liệu và tenant tương ứng.

### E. Kiểm thử và vận hành

- [ ] Happy-path submission và feedback đã hoạt động trong sandbox.
- [ ] Invalid signature/payload bị reject.
- [ ] Duplicate/out-of-order events không làm sai projection.
- [ ] Unmatched event được lưu và reconcile.
- [ ] Timeout sau DATA không kích hoạt failover mù.
- [ ] Có dashboard provider-specific và event-coverage metrics.
- [ ] Alerts có sample-size và cohort đủ tuổi.
- [ ] Rollout traffic có giới hạn và phương án dừng.

## 76. Checklist khi so sánh deliverability giữa hai provider

Trước khi kết luận “Provider B tốt hơn Provider A”, hãy trả lời:

1. Hai route có gửi cùng loại email và nhóm recipient tương đồng không?
2. Có cùng sender domain, authentication và reputation conditions hợp lý không?
3. Hai provider có cung cấp **cùng loại remote delivery evidence** không?
4. Mẫu số là unique recipient, recipient-attempt hay message-attempt?
5. Có loại trừ/reconcile retries và duplicate webhook chưa?
6. Cohort đã đủ thời gian cho delivery feedback chưa?
7. Có bao nhiêu recipient vẫn deferred hoặc unobserved?
8. Feedback event coverage khác nhau bao nhiêu?
9. Có thay đổi template, nội dung, thời gian gửi hoặc routing gần đây không?
10. Bounce/complaint được phân loại theo cùng semantics chưa?
11. Có phân tích theo recipient domain group và traffic class không?
12. Khối lượng mẫu có đủ để đưa ra quyết định vận hành không?
13. Có tách Inbox placement và open/click khỏi remote delivered chưa?
14. Một sự cố webhook có đang bị nhầm thành sự cố deliverability không?
15. Nếu chuyển route, có nguy cơ làm mất suppression hoặc gửi trùng không?

Nếu một số câu trả lời còn thiếu, nên diễn giải kết quả là **quan sát tạm thời với giới hạn dữ liệu**, không phải bảng xếp hạng tuyệt đối.

## 77. Bài tập tự luyện

### Bài tập 1 — Hai provider với hai trạng thái khác nhau

Provider A báo `DELIVERED_REMOTE` cho 900/1.000 recipient-attempt. Provider B báo `PROVIDER_ACCEPTED` cho 990/1.000 attempt nhưng không gửi remote-delivered feedback.

**Câu hỏi:** Có thể nói B giao thư tốt hơn A không?

**Gợi ý:** không. Các tử số thuộc những tầng khác nhau; B thiếu nguồn đo remote delivery. Cần so sánh submission riêng và remote-delivered riêng, công bố event coverage.

### Bài tập 2 — Event duplicate

Một webhook delivered có cùng event ID đến ba lần. Database ghi ba dòng và dashboard báo tỷ lệ delivered vượt 100%.

**Gợi ý:** unique constraint/idempotent inbox theo provider + scope + event identity; projection distinct recipient-attempt; đo duplicate callbacks riêng.

### Bài tập 3 — Deferred đến sau delivered

Provider gửi event `DEFERRED` rồi `DELIVERED_REMOTE`, nhưng hệ thống nhận webhook delivered trước.

**Gợi ý:** không dùng last-arrival-wins. Lưu event ledger và quy tắc projection theo semantics; đừng để deferral cũ ghi đè delivered.

### Bài tập 4 — Mất webhook

SMTP submission thành công, sau 24 giờ không có webhook. Dashboard tự chuyển `FAILED`.

**Gợi ý:** thiếu feedback là `UNOBSERVED` hoặc `STALE_UNOBSERVED`, không phải thất bại chắc chắn; xem event coverage, query API/DSN nếu có.

### Bài tập 5 — Gửi trùng giữa provider

Attempt A gửi hết DATA nhưng mất final reply, ứng dụng chuyển ngay sang provider B. Sau đó cả A và B có delivered event.

**Gợi ý:** A phải được ghi `UNKNOWN`; cần reconciliation trước failover khi policy không chấp nhận duplicate. Hai event thuộc hai attempts của một notification, không ghi đè lên nhau.

### Bài tập 6 — Suppression xuyên route

Provider A ghi nhận complaint từ recipient R. Provider B không có R trong suppression list. Router chuẩn bị gửi marketing mail qua B.

**Gợi ý:** kiểm tra central eligibility/opt-out trước routing. Không dùng B để né complaint hoặc suppression.

### Bài tập 7 — Chênh lệch theo domain

Provider A có delivered rate thấp hơn B ở số tổng, nhưng A nhận phần lớn traffic tới domain đang tạm throttling.

**Gợi ý:** phân tích theo cohort/domain/message class, cân bằng traffic mix trước khi quy chênh lệch cho provider.

### Bài tập 8 — Complaint đến sau delivery

Một recipient đã `DELIVERED_REMOTE` sau đó có `COMPLAINED`.

**Gợi ý:** không xóa bằng chứng delivery. Giữ delivery state và feedback state riêng; cập nhật suppression theo policy.

### Bài tập 9 — Cùng message ID tại hai account

Provider báo message ID `m-123` trong account A và cũng có `m-123` tại account B. Application dùng một unique key toàn cục chỉ bằng message ID.

**Gợi ý:** namespace bằng provider + account/region + message ID; event ID/dedupe cũng phải có scope thích hợp.

### Bài tập 10 — Tracking open/click

Một provider báo open rate tăng rất cao nhưng click và phản hồi khách hàng không đổi.

**Gợi ý:** open pixel có thể bị tải bởi privacy proxy hoặc tự động; không kết luận Inbox placement hay mức đọc thực tăng chỉ từ event này.

### Bài tập 11 — Test webhook lỗi storage

Webhook signature hợp lệ, nhưng database event inbox đang không ghi được. Controller vẫn trả `204` trước khi persist.

**Gợi ý:** nguy cơ mất feedback sau acknowledgment. Chỉ trả success khi dữ liệu được ghi bền vững hoặc được nhận bởi một queue bền vững theo contract.

### Bài tập 12 — Bounce khác suppression

Provider A có event `dropped` do suppression; mapper ghi nó là `BOUNCED`.

**Gợi ý:** xác định stage và semantics: suppression trước delivery khác remote bounce. Dùng mapping version có contract và giữ raw type.

## 78. Những nguyên tắc cốt lõi cần ghi nhớ

1. **Spring Mail quản lý MIME và SMTP submission**, không tự cung cấp deliverability events xuyên mọi provider.
2. **Submitted, provider-accepted, remote-delivered, Inbox và engagement là các tầng khác nhau.**
3. **Provider event naming không đồng nhất**; phải map theo semantics và version, không chỉ theo tên.
4. **Recipient-attempt thường là đơn vị quan sát đúng**; đừng nhầm message với recipient hoặc webhook event.
5. **Lưu notification ID, attempt ID, provider scope, provider message ID và event ID** theo khả năng từng nguồn.
6. **Event ledger bất biến + projection** an toàn hơn một status ghi đè theo thứ tự callback đến.
7. **Webhook cần xác thực, giới hạn, lưu bền vững và xử lý idempotent**; duplicate/out-of-order là tình huống bình thường.
8. **Event không match hoặc không xuất hiện là khoảng trống quan sát**, không tự suy ra giao thư thành công/thất bại.
9. **Mẫu số, cohort age, event coverage và traffic mix** là điều kiện để so sánh tỷ lệ deliverability.
10. **Open/click không chứng minh người dùng đã đọc**, còn remote delivered không chứng minh Inbox placement.
11. **Failover sau `UNKNOWN` hoặc `DEFERRED` có nguy cơ duplicate**, phải dựa vào policy và reconciliation.
12. **Suppression/consent phải được tôn trọng xuyên provider**; không chuyển route để bỏ qua feedback tiêu cực.
13. **DNS authentication, reputation, quota và region** thuộc chất lượng mỗi route, không chỉ SMTP host.
14. **Đo được chất lượng telemetry trước khi kết luận chất lượng deliverability.**
15. **Không lưu PII/secret/raw payload vào metric labels hoặc log chung**, ngay cả khi đang điều tra lỗi.

## 79. Kết luận

Theo dõi deliverability giữa nhiều nhà cung cấp trong Spring Framework Mail là một **bài toán quan sát và thống nhất ngữ nghĩa**, không phải chỉ thêm vài nhánh `try/catch` quanh `JavaMailSender.send(...)`. Lời gọi gửi thành công mới cho biết SMTP submission theo bằng chứng transport; từ đó tới provider acceptance, remote delivery, bounce, complaint, suppression, Inbox placement và engagement là nhiều giai đoạn với các nguồn dữ liệu khác nhau.

Một kiến trúc đáng tin cậy lưu **notification và từng attempt theo provider**, định danh recipient rõ ràng, thu nhận callback/feedback an toàn, chuẩn hóa event qua adapter từng provider và lưu event ledger bền vững. Projection cần chịu được webhook lặp, đến trễ, không match hoặc thiếu hoàn toàn. Dashboard phải công bố **mẫu số, cohort, thời gian quan sát, coverage và phạm vi traffic**, đồng thời tách submission health khỏi deliverability và Inbox placement.

Cuối cùng, số liệu deliverability chỉ hữu ích khi giúp ứng dụng **hành động đúng**: sửa cấu hình SPF/DKIM/DMARC, xử lý suppression, giới hạn rate, đối chiếu event bị mất, cải thiện chất lượng danh sách nhận và chọn route có kiểm soát. Không được dùng failover để bỏ qua opt-out hoặc gửi lại mù một attempt có kết quả chưa rõ. Khi kết hợp event semantics, dữ liệu có nguồn gốc và quy trình vận hành thận trọng, hệ thống nhiều provider có thể so sánh chất lượng gửi thực tế mà không đánh đổi tính chính xác, riêng tư hoặc độ tin cậy của email nghiệp vụ.
