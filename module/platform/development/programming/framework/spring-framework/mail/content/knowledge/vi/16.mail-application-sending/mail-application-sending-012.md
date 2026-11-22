# Ghi nhận message key để truy nguyên một email

Khi người dùng báo “tôi không nhận được email”, nhóm vận hành cần tìm được đúng thông điệp đã phát sinh từ một nghiệp vụ: email được tạo khi nào, worker nào xử lý, đã thử gửi bao nhiêu lần, SMTP relay có tiếp nhận không, provider có báo bounce hay delivery không. Chỉ tìm theo subject, địa chỉ người nhận hoặc thời gian thường không đủ vì những giá trị đó có thể lặp lại.

Trong **Spring Framework Mail**, nên tạo một **application message key** do ứng dụng quản lý, lưu cùng yêu cầu gửi và dùng xuyên suốt database, outbox, worker, log và provider events. Có thể gắn key vào custom MIME header như `X-Application-Message-Key` để hỗ trợ tra cứu raw email. Header là phương tiện truyền correlation; database/outbox vẫn là nguồn sự thật chính.

Message key cần được phân biệt với RFC `Message-ID`, correlation ID, attempt ID, SMTP queue ID và provider message ID. Mỗi loại định danh có phạm vi và mục đích riêng.

## 1. Email đi qua nhiều tầng

```text
Nghiệp vụ (đơn hàng, tài khoản, hóa đơn)
       |
       v
Email service / template renderer
       |
       v
Outbox / queue / background worker
       |
       v
MimeMessage + JavaMailSender
       |
       v
SMTP relay / email provider
       |
       v
Mail server của người nhận
       |
       v
Mailbox / spam filter / client
```

Mỗi tầng có thể có log và ID riêng:
- Nghiệp vụ tạo email xác nhận đơn hàng.
- Outbox lưu công việc gửi email.
- Worker nhận công việc và tạo một lần thử gửi.
- Spring Mail tạo MIME message.
- SMTP relay tiếp nhận message và ghi queue ID.
- Provider phát event như delivered, bounced hoặc deferred.
- Mail server đích có thể chấp nhận thư nhưng thư vẫn vào spam hoặc bị người dùng lọc.

Một message key tốt giúp:
- Liên kết email với bản ghi nghiệp vụ và yêu cầu gửi.
- Tra cứu log của worker và SMTP submission.
- Phân biệt các lần retry của cùng email logic.
- Ghép webhook delivery/bounce về đúng email.
- Hỗ trợ điều tra lỗi, đối soát và audit.
- Tránh tìm kiếm bằng nội dung hoặc dữ liệu cá nhân.

## 2. Phân biệt các loại định danh

| Định danh | Ai tạo? | Phạm vi | Mục đích |
|---|---|---|---|
| **Application message key** | Ứng dụng | Một email logic/nghiệp vụ | Tra cứu xuyên suốt hệ thống. |
| **Correlation ID** | Request gateway hoặc ứng dụng | Một luồng nghiệp vụ có thể tạo nhiều email | Liên kết các thao tác liên quan. |
| **Attempt ID** | Worker/ứng dụng | Một lần thử gửi | Phân biệt từng lần retry. |
| **RFC Message-ID** | MIME library/provider hoặc ứng dụng theo chính sách | Một MIME message cụ thể | Định danh email theo chuẩn, hỗ trợ threading/tra cứu. |
| **SMTP queue ID** | SMTP relay/MTA | Một lần tiếp nhận tại relay | Tra cứu log của MTA. |
| **Provider message ID** | Email provider | Một lần submission tại provider | Tra cứu dashboard/API/webhook. |
| **Provider event ID** | Provider | Một sự kiện cụ thể | Deduplicate và đối soát webhook. |

### 2.1. Application message key

Đây là mã do ứng dụng chủ động tạo, ví dụ UUID hoặc ULID:

```text
email_01JCM7YQ5J3Z6T4F8A2N9K1M6P
```

Key nên:
- duy nhất theo phạm vi database/tenant phù hợp;
- không chứa email người nhận, tên, số điện thoại hoặc dữ liệu nhạy cảm;
- ổn định trong suốt vòng đời của một email logic;
- được lưu trong database và xuất hiện trong log liên quan;
- không thay đổi chỉ vì một lần retry.

Một key ngẫu nhiên không phải token xác thực. Người biết message key không tự động có quyền xem nội dung email hoặc tải attachment.

### 2.2. Correlation ID

Correlation ID thường gắn với request hoặc luồng nghiệp vụ lớn hơn. Một request tạo đơn hàng có thể phát sinh email xác nhận, email cho kho và email cho bộ phận hỗ trợ. Các email đó có **message key riêng nhưng cùng correlation ID**.

```text
correlation_id = flow_7f92...
  |
  +-- message_key = order-confirmation-...
  |
  +-- message_key = warehouse-notification-...
  |
  +-- message_key = customer-receipt-...
```

Không nhất thiết dùng correlation ID làm message key; hai khái niệm có phạm vi khác nhau.

### 2.3. Attempt ID

Nếu cùng email logic được gửi lại do lỗi tạm thời, message key giữ nguyên nhưng mỗi lần thử có attempt ID riêng:

```text
message_key = msg_01J...
  |
  +-- attempt_id = att_001  -> timeout
  +-- attempt_id = att_002  -> SMTP accepted
```

### 2.4. RFC Message-ID

RFC `Message-ID` là header chuẩn của email, thường có dạng:

```text
Message-ID: <unique-value@example-mail-host>
```

Nó định danh một thông điệp MIME cụ thể và có thể được mail client dùng trong threading hoặc tra cứu raw message. Thư viện mail/SMTP provider có thể tự tạo Message-ID. Một lần retry có thể tạo MIME message mới và có Message-ID khác, dù đó vẫn là cùng email logic.

**Không nên đặt application key vào header Message-ID chỉ để tiện tìm kiếm.** Hãy giữ Message-ID theo vai trò chuẩn của nó và lưu nó như thuộc tính bổ sung nếu có thể lấy được. Application key nên có field riêng trong database và có thể được truyền qua custom header.

### 2.5. SMTP queue ID và provider message ID

SMTP relay có thể ghi queue ID trong log. Đây là ID nội bộ của MTA, không phải chuẩn dùng chung cho mọi server. `JavaMailSender.send(...)` cũng không có hợp đồng tổng quát trả về queue ID.

Email provider có thể cung cấp provider message ID hoặc metadata riêng qua API response, webhook, dashboard hoặc custom argument. Không nên giả định Spring Mail tự cung cấp mọi ID của nhà cung cấp.

## 3. Tạo và lưu message key

### 3.1. Dùng UUID hoặc ULID

Một lựa chọn đơn giản là UUID ngẫu nhiên:

```java
import java.util.UUID;

String messageKey = UUID.randomUUID().toString();
```

Hoặc dùng ULID nếu hệ thống đã có thư viện và quy ước tương ứng. Tránh dùng số tăng tuần tự có thể làm lộ lưu lượng hoặc thứ tự nội bộ khi key xuất hiện trong header/log.

### 3.2. Sinh key một lần cho một email logic

Message key nên được tạo khi ứng dụng quyết định phát sinh một email logic, trước khi đưa công việc vào queue/outbox.

Ví dụ:
- Đơn hàng ORD-001 tạo email xác nhận lần đầu: sinh key.
- Worker retry do lỗi tạm thời: dùng lại key đó.
- Người dùng chủ động yêu cầu gửi lại hóa đơn vào tuần sau như hành động mới: thường tạo key mới, có thể liên kết với cùng business entity/correlation.

Điều quan trọng là xác định rõ đâu là retry của cùng thông điệp và đâu là yêu cầu gửi mới.

### 3.3. Lưu unique constraint

Database nên có unique constraint cho key:

```sql
CREATE TABLE email_outbox (
    message_key       VARCHAR(64) PRIMARY KEY,
    correlation_id    VARCHAR(64),
    business_type     VARCHAR(40) NOT NULL,
    business_id       VARCHAR(100) NOT NULL,
    template_name     VARCHAR(120) NOT NULL,
    recipient_ref     VARCHAR(100) NOT NULL,
    status            VARCHAR(32) NOT NULL,
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL
);
```

Đây là schema minh họa. `recipient_ref` có thể là ID nội bộ hoặc dữ liệu được bảo vệ; không nhất thiết lưu địa chỉ email dạng rõ trong bảng log. Bổ sung index theo business type/ID, status hoặc created_at tùy nhu cầu.

Nếu một nghiệp vụ chỉ được gửi một loại thông báo một lần, có thể thêm unique constraint nghiệp vụ, ví dụ trên business type, business ID, template name và notification version. Message key định danh bản ghi; constraint nghiệp vụ giúp chống tạo hai email logic ngoài ý muốn.

## 4. Lưu key trước khi gửi: Outbox pattern

Không nên chỉ tạo key trong bộ nhớ rồi gửi ngay nếu email quan trọng và cần truy nguyên. Nếu ứng dụng crash sau khi SMTP nhận thư nhưng trước khi ghi trạng thái, database có thể không biết email đã được gửi. Ngược lại, nếu ghi trạng thái SENT trước khi gọi SMTP rồi process crash, email có thể chưa từng rời ứng dụng.

Outbox pattern giúp ghi yêu cầu gửi cùng transaction nghiệp vụ:

```text
Database transaction
  |
  +--> update business data
  |
  +--> insert email_outbox(message_key, status=PENDING)
  |
  v
COMMIT
  |
  v
Outbox worker claims row
  |
  v
Create attempt + send MIME
  |
  v
Persist result / provider events
```

Trong transaction tạo đơn hàng:
1. Lưu đơn hàng.
2. Sinh message key.
3. Tạo bản ghi outbox ở trạng thái `PENDING`.
4. Commit cả hai cùng nhau.

Worker đọc outbox và gửi. Nếu ứng dụng restart, yêu cầu gửi vẫn tồn tại để được xử lý tiếp.

Outbox không tự đảm bảo exactly-once delivery. SMTP/provider có thể tiếp nhận thư nhưng ứng dụng mất kết nối trước khi nhận kết quả. Khi đó trạng thái có thể không rõ ràng; cần mô hình hóa `UNKNOWN` hoặc trạng thái tương đương và có chính sách reconciliation.

## 5. Gắn message key vào MIME header trong Spring Mail

Có thể thêm custom header vào `MimeMessage`:

```java
message.setHeader(
    "X-Application-Message-Key",
    messageKey
);
```

Có thể thêm correlation ID và attempt ID:

```java
message.setHeader("X-Correlation-ID", correlationId);
message.setHeader("X-Mail-Attempt-ID", attemptId);
```

Header custom giúp nhóm vận hành xem raw source hoặc tìm metadata trong log/provider nếu hệ thống giữ header đó. Tuy nhiên:
- Relay hoặc hệ thống trung gian có thể loại bỏ custom header.
- Người nhận có thể xem raw headers; không đặt secret hoặc dữ liệu cá nhân vào đó.
- Không phải provider nào cũng cho phép lọc dashboard theo custom header.
- Cần kiểm tra khả năng giữ header bằng test gửi qua provider thực tế.

**Database/outbox vẫn là nguồn sự thật chính.** Header chỉ là phương tiện mang correlation key qua các tầng.

### 5.1. Ví dụ tạo message có custom header

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class TracedMailSender {

    private final JavaMailSender mailSender;

    public TracedMailSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            String subject,
            String plainText,
            String htmlText,
            String messageKey,
            String correlationId,
            String attemptId) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(plainText, htmlText);

        message.setHeader(
            "X-Application-Message-Key",
            messageKey
        );

        if (correlationId != null && !correlationId.isBlank()) {
            message.setHeader("X-Correlation-ID", correlationId);
        }

        message.setHeader("X-Mail-Attempt-ID", attemptId);

        mailSender.send(message);
    }
}
```

Các key trong ví dụ phải do server tạo, có định dạng giới hạn và không chứa CR/LF. Không lấy trực tiếp header từ request rồi chuyển tiếp sang outgoing message; nếu cần nhận correlation ID từ request, hãy validate theo quy tắc tin cậy của hệ thống.

### 5.2. Thứ tự xây dựng message

Có thể đặt custom header sau khi tạo `MimeMessageHelper` và sau khi `setText(...)`. Jakarta Mail sẽ lưu header khi chuẩn bị message. Không cần tự viết MIME boundary hoặc chèn header vào chuỗi body.

Nếu có inline resource, giữ thứ tự:
1. `helper.setText(plainText, htmlText)`;
2. `helper.addInline(...)` cho resource được tham chiếu;
3. `helper.addAttachment(...)` cho attachment độc lập;
4. gửi sau khi hoàn thiện message.

### 5.3. Không dùng custom header làm bí mật

Ví dụ không nên:

```text
X-Application-Message-Key: customer-email=alice@example.com
X-Reset-Password-Token: secret-token-value
X-Internal-Database-ID: 123456
```

Header có thể xuất hiện trong raw email, log relay, hệ thống provider hoặc thư được forward. Chỉ đặt mã định danh opaque, không nhúng password, reset token, session ID, thông tin tài chính hoặc dữ liệu cá nhân không cần thiết.

## 6. Lưu Message-ID và các ID do provider tạo

Sau khi message được chuẩn bị và gửi, có thể đọc RFC Message-ID từ `MimeMessage` nếu implementation đã tạo header:

```java
mailSender.send(message);

String rfcMessageId = message.getMessageID();
```

Với `JavaMailSenderImpl`, việc chuẩn bị MIME thường gọi `saveChanges()` trước khi gửi, và Message-ID có thể được tạo trong quá trình đó. Tuy nhiên, implementation tùy biến hoặc provider có thể có hành vi khác; hãy coi giá trị có thể không có sẵn và xác nhận bằng integration test trong môi trường gửi thực tế.

Có thể lưu `rfcMessageId` như thuộc tính bổ sung của attempt:

```sql
CREATE TABLE email_attempt (
    attempt_id          VARCHAR(64) PRIMARY KEY,
    message_key         VARCHAR(64) NOT NULL,
    attempt_number      INTEGER NOT NULL,
    rfc_message_id      VARCHAR(255),
    provider_message_id VARCHAR(255),
    smtp_queue_id       VARCHAR(255),
    started_at          TIMESTAMP NOT NULL,
    accepted_at         TIMESTAMP,
    outcome             VARCHAR(32) NOT NULL
);
```

Không ghi đè application message key bằng Message-ID. Message-ID có thể khác qua các lần gửi lại; message key giữ liên kết tới email logic.

SMTP queue ID và provider message ID cần được lấy từ nơi cung cấp chúng:
- SMTP server logs nếu tổ chức quản lý relay;
- provider API response nếu dùng API gửi;
- provider event webhook;
- dashboard/search API của provider;
- metadata hoặc custom argument được provider hỗ trợ.

Generic SMTP không đảm bảo `JavaMailSender` trả lại queue ID. Nếu cần ID đó, phải xác định cách tích hợp cụ thể với MTA/provider.

## 7. Mô hình dữ liệu cho message và attempt

Một mô hình đơn giản tách email logic khỏi các lần gửi:

```text
email_outbox
  message_key (PK)
  correlation_id
  business_type / business_id
  template_name / template_version
  recipient_ref
  status
  created_at / updated_at
       |
       | 1-to-many
       v
email_attempt
  attempt_id (PK)
  message_key (FK)
  attempt_number
  rfc_message_id
  provider_message_id
  smtp_queue_id
  started_at / accepted_at
  outcome / error_code
       |
       | 1-to-many
       v
email_event
  event_id (PK)
  attempt_id or provider_message_id
  event_type
  provider_event_time
  received_at
  metadata_ref
```

Vai trò:
- `email_outbox` mô tả email logic cần gửi.
- `email_attempt` mô tả từng lần worker thử gửi.
- `email_event` lưu sự kiện bất đồng bộ như delivered, bounced hoặc complaint.

Không cần lưu toàn bộ HTML hoặc file attachment trong bảng log. Nếu cần lưu nội dung để audit, dùng storage có quyền truy cập, mã hóa và retention rõ ràng; outbox thường chỉ cần template/version và tham chiếu dữ liệu cần render.

## 8. Trạng thái gửi: SMTP accepted không đồng nghĩa delivered

Trạng thái nên diễn đạt chính xác điều hệ thống đã biết:

| Trạng thái | Ý nghĩa |
|---|---|
| `PENDING` | Đã tạo yêu cầu gửi, chưa có worker xử lý. |
| `SENDING` | Worker đang thực hiện một attempt. |
| `SMTP_ACCEPTED` | SMTP relay đã chấp nhận thông điệp ở bước submission. |
| `DELIVERED` | Provider báo đã giao/được mail server đích tiếp nhận theo định nghĩa event của provider. |
| `DEFERRED` | Provider hoặc mail server tạm hoãn giao. |
| `BOUNCED` | Provider báo không giao được. |
| `COMPLAINED` | Có sự kiện complaint/spam report nếu provider hỗ trợ. |
| `FAILED` | Có lỗi xác định trước khi thông điệp được chấp nhận. |
| `UNKNOWN` | Kết quả không rõ, ví dụ kết nối timeout sau khi relay có thể đã nhận thư. |

`SMTP_ACCEPTED` chỉ nói SMTP server đã tiếp nhận message; nó không chứng minh email vào Inbox, không bị spam filter và đã được người nhận đọc. Một provider event `delivered` thường phản ánh server nhận đã chấp nhận thư, không có nghĩa con người đã mở hoặc đọc nó.

Không phải mọi SMTP provider đều cung cấp webhook delivery/bounce. Nếu chỉ có generic SMTP, trạng thái cuối có thể dừng ở `SMTP_ACCEPTED` hoặc dựa trên log MTA nội bộ.

## 9. Retry và idempotency

### 9.1. Giữ message key, tạo attempt ID mới

Một retry là lần thử khác của cùng email logic:

```text
message_key = msg_abc
  |
  +-- attempt_id = att_001
  |      outcome = UNKNOWN
  |
  +-- attempt_id = att_002
         outcome = SMTP_ACCEPTED
```

Không sinh message key mới mỗi khi retry, nếu không lịch sử của một email logic sẽ bị chia thành nhiều bản ghi không liên kết. Attempt ID cần mới để phân biệt mỗi lần gửi.

Mỗi attempt nên tạo `MimeMessage` mới. Không tái sử dụng cùng một mutable message hoặc `MimeMessageHelper` qua các thread/lần retry.

### 9.2. SMTP không cung cấp exactly-once mặc định

Một tình huống khó:
1. Worker gửi message.
2. SMTP relay tiếp nhận thành công.
3. Kết nối bị đứt trước khi ứng dụng nhận được phản hồi.
4. Worker ghi nhận timeout và retry.

Lúc này email đầu có thể đã được gửi; retry có thể tạo email thứ hai. Message key giúp nhận ra cả hai thuộc cùng một yêu cầu, nhưng **không tự ngăn SMTP gửi trùng**.

Các biện pháp:
- Outbox và trạng thái attempt rõ ràng.
- Idempotency key ở API provider nếu provider hỗ trợ.
- Reconciliation qua provider logs/events trước khi retry trường hợp `UNKNOWN`.
- Retry có backoff và giới hạn số lần.
- Unique constraint để không tạo nhiều email logic cho cùng event nghiệp vụ.
- Thiết kế nội dung có mã tham chiếu để người nhận nhận biết email lặp nếu điều đó vẫn xảy ra.

Không tuyên bố exactly-once chỉ vì application message key duy nhất.

### 9.3. Idempotency key khác message key như thế nào?

Message key định danh email logic. Idempotency key là token được một API/provider dùng để nhận diện yêu cầu lặp và tránh thực thi lặp trong phạm vi/thời hạn do provider định nghĩa. Có thể dùng cùng một giá trị nếu provider cho phép và semantics phù hợp, nhưng không mặc định mọi SMTP relay hiểu custom header như idempotency key.

## 10. Gắn provider webhook về đúng message key

Khi provider gửi webhook event, event có thể chứa provider message ID, recipient, event type, timestamp, SMTP response/bounce reason, custom metadata và event ID riêng.

Quy trình xử lý:

```text
Provider webhook
      |
      v
Verify signature / authenticate source
      |
      v
Persist event metadata safely
      |
      v
Deduplicate by provider event ID
      |
      v
Map provider message ID / custom metadata
      |
      v
Find email_attempt and message_key
      |
      v
Update event history and aggregate status
```

Các điểm cần chú ý:
1. Xác minh chữ ký webhook hoặc cơ chế xác thực provider cung cấp.
2. Không tin event body chỉ vì endpoint nhận được request.
3. Lưu provider event ID với unique constraint để webhook gửi lại không tạo event trùng.
4. Mapping theo provider message ID hoặc custom metadata đã được cấu hình và kiểm thử.
5. Chấp nhận webhook đến trễ hoặc sai thứ tự; lưu event history thay vì giả định trạng thái luôn đến theo thứ tự.
6. Không lấy recipient từ webhook rồi dùng để thay đổi dữ liệu nghiệp vụ nếu chưa xác thực event.
7. Chỉ ghi metadata cần thiết; bounce reason có thể chứa địa chỉ hoặc thông tin cần bảo vệ.

Custom header `X-Application-Message-Key` có thể được provider giữ lại, nhưng không có bảo đảm chung cho mọi relay. Nếu provider hỗ trợ custom arguments/tags hoặc metadata fields, ưu tiên cơ chế chính thức của provider và kiểm tra cách metadata xuất hiện trong event. Database mapping vẫn cần giữ provider message ID và message key.

## 11. Ví dụ worker: ghi attempt và gửi message có key

Đoạn code sau minh họa một worker. Repository là interface do ứng dụng định nghĩa; việc claim row và transaction phải được triển khai phù hợp với database/queue đang dùng.

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.time.Instant;
import java.util.UUID;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class EmailOutboxWorker {

    private final JavaMailSender mailSender;
    private final EmailOutboxRepository repository;

    public EmailOutboxWorker(
            JavaMailSender mailSender,
            EmailOutboxRepository repository) {
        this.mailSender = mailSender;
        this.repository = repository;
    }

    public void deliver(EmailOutboxItem item) {
        String attemptId = UUID.randomUUID().toString();
        Instant startedAt = Instant.now();

        repository.markSending(
            item.messageKey(),
            attemptId,
            startedAt
        );

        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom("no-reply@example.com");
            helper.setTo(item.recipient());
            helper.setSubject(item.subject());
            helper.setText(item.plainText(), item.htmlText());

            message.setHeader(
                "X-Application-Message-Key",
                item.messageKey()
            );
            message.setHeader(
                "X-Mail-Attempt-ID",
                attemptId
            );

            if (item.correlationId() != null) {
                message.setHeader(
                    "X-Correlation-ID",
                    item.correlationId()
                );
            }

            mailSender.send(message);

            // RFC Message-ID có thể đã được tạo trong quá trình
            // saveChanges/send; lưu nếu implementation cung cấp.
            String rfcMessageId = null;
            try {
                rfcMessageId = message.getMessageID();
            } catch (MessagingException ignored) {
                // Message-ID là metadata bổ sung, không đảo ngược
                // kết quả SMTP submission đã thành công.
            }

            repository.markSmtpAccepted(
                item.messageKey(),
                attemptId,
                rfcMessageId,
                Instant.now()
            );

        } catch (MailException | MessagingException ex) {
            // Không phải mọi lỗi đều chứng minh SMTP chưa nhận thư.
            // Repository cần phân loại lỗi chắc chắn thất bại và
            // lỗi có kết quả không rõ để tránh retry mù.
            repository.recordSendError(
                item.messageKey(),
                attemptId,
                classify(ex),
                Instant.now()
            );
        }
    }

    private String classify(Exception ex) {
        return ex.getClass().getSimpleName();
    }
}
```

Đây là skeleton để minh họa mối liên hệ giữa message key và attempt. Trong hệ thống thật:
- `EmailOutboxItem` nên được load từ outbox đã claim một cách an toàn.
- `markSending` và `markSmtpAccepted` cần kiểm soát cạnh tranh giữa nhiều worker.
- Phân loại `MailException` cần dựa trên loại lỗi, response và khả năng xác định kết quả submission; không gom tất cả thành `FAILED`.
- Nếu SMTP timeout ở thời điểm không xác định, ghi `UNKNOWN` hoặc trạng thái tương đương và reconciliation trước khi retry.
- Không ghi `ex.getMessage()` nguyên văn nếu có thể chứa recipient, host, nội dung hoặc thông tin nhạy cảm.
- Nên dùng clock có thể inject trong test thay vì gọi `Instant.now()` trực tiếp ở mọi vị trí.

## 12. Log và truy vấn để điều tra email

Một log có ích có thể chứa:

```json
{
  "event": "email.smtp_accepted",
  "messageKey": "msg_01JCM7YQ5J3Z6T4F8A2N9K1M6P",
  "attemptId": "att_8e71...",
  "correlationId": "flow_7f92...",
  "rfcMessageId": "<abc123@example-mail-host>",
  "template": "order-confirmation",
  "provider": "smtp-relay-a",
  "durationMs": 842
}
```

Đây là ví dụ cấu trúc log; không cần log đầy đủ recipient hoặc nội dung email để tra cứu.

Một quy trình support có thể là:
1. Người dùng cung cấp mã đơn hàng hoặc ticket reference qua kênh hỗ trợ.
2. Nhân viên được cấp quyền tra cứu bản ghi nghiệp vụ để tìm message key.
3. Dùng message key tìm outbox record và các attempt.
4. Kiểm tra thời gian, trạng thái, lỗi đã chuẩn hóa và Message-ID nếu có.
5. Nếu đã `SMTP_ACCEPTED`, dùng provider ID/SMTP log để điều tra tiếp.
6. Nếu provider báo `BOUNCED`, đọc bounce category/reason theo quyền truy cập.
7. Nếu provider báo `DELIVERED` nhưng người dùng không thấy thư, hướng dẫn kiểm tra spam/quarantine và xác minh mailbox; không khẳng định người nhận đã đọc.

Ví dụ truy vấn SQL:

```sql
SELECT
    o.message_key,
    o.correlation_id,
    o.status,
    o.created_at,
    a.attempt_id,
    a.attempt_number,
    a.rfc_message_id,
    a.provider_message_id,
    a.smtp_queue_id,
    a.outcome,
    a.accepted_at
FROM email_outbox o
LEFT JOIN email_attempt a
    ON a.message_key = o.message_key
WHERE o.message_key = :messageKey
ORDER BY a.attempt_number;
```

Trong hệ thống lớn, có thể tìm theo business reference đã được người hỗ trợ xác thực, sau đó lấy message key. Không cho phép endpoint public nhận message key bất kỳ rồi trả toàn bộ lịch sử gửi; key không phải cơ chế authorization.

## 13. Bảo mật và quyền riêng tư

Message key có thể xuất hiện ở nhiều hệ thống. Cần:
- Dùng key opaque, không nhúng email, tên, số điện thoại hoặc mã khách hàng nhạy cảm.
- Không dùng key làm bearer token hoặc password.
- Không ghi reset token, URL có token, nội dung thư hoặc Base64 attachment vào log.
- Giới hạn quyền truy vấn lịch sử email theo vai trò.
- Che/mã hóa recipient nếu lưu ở dạng có thể nhận diện.
- Có retention policy cho outbox, attempts, events và provider payload.
- Giới hạn dữ liệu webhook lưu lại; chỉ giữ trường cần thiết.
- Không đưa custom header chứa dữ liệu nội bộ nhạy cảm vào thư.
- Kiểm soát log access và audit truy vấn support.

Custom header có thể được người nhận nhìn thấy trong raw source. Hãy coi header là dữ liệu có thể lộ ra ngoài. Nếu không muốn expose application key, dùng một opaque external correlation token hoặc chỉ lưu mapping ở provider metadata nếu được hỗ trợ.

## 14. Những hiểu lầm phổ biến

### “Message-ID chính là message key”

Không. RFC Message-ID định danh một MIME message; application message key định danh một email logic trong ứng dụng. Một email retry có thể có Message-ID khác nhưng giữ cùng application key.

### “SMTP send không ném exception nghĩa là email đã vào Inbox”

Không. Nó thường chỉ cho biết SMTP relay đã chấp nhận message. Delivery, spam filtering và việc người dùng mở thư là các bước khác.

### “Thêm X-Application-Message-Key vào header là đủ”

Không. Header hỗ trợ tracing nhưng có thể bị strip hoặc không được provider index. Phải lưu key trong outbox/database và dùng nó ở log của ứng dụng.

### “Retry cần tạo message key mới”

Không nếu đó là retry của cùng email logic. Giữ message key, tạo attempt ID mới. Một yêu cầu gửi lại mới do người dùng chủ động có thể là message logic mới theo quy tắc nghiệp vụ.

### “Message key duy nhất bảo đảm không gửi trùng”

Không. SMTP không mặc định cung cấp idempotency theo custom header. Cần outbox, unique constraints, provider idempotency nếu có và xử lý kết quả UNKNOWN.

### “Provider message ID luôn có trong JavaMailSender”

Không. Generic SMTP không đảm bảo API gửi trả provider-specific ID. Phải dùng provider API, webhook hoặc log của relay.

### “Có thể lưu mọi nội dung email vào log để tiện tìm”

Không nên. Dùng message key, attempt ID, template/version, status và ID provider; giữ nội dung nhạy cảm trong storage có kiểm soát nếu thực sự cần audit.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Không tìm được email theo business ID | Không lưu mapping business reference → message key | Ghi business type/ID trong outbox hoặc bảng mapping. |
| Nhiều email cùng subject bị nhầm | Tìm theo subject và timestamp | Tra cứu bằng message key. |
| Retry bị coi là email logic mới | Sinh key ở mỗi lần worker chạy | Sinh key khi tạo outbox item, giữ qua retry. |
| Không phân biệt được các lần thử | Chỉ có một status trên outbox | Tạo bảng attempt với attempt ID riêng. |
| Message-ID null trong log | Chưa được tạo hoặc implementation/provider không expose | Lưu tùy chọn; xác nhận bằng integration test. |
| Custom header không xuất hiện ở thư nhận | Relay/provider loại bỏ header | Giữ DB mapping; dùng provider metadata chính thức. |
| Provider event không map được | Chưa lưu provider message ID/custom metadata | Bổ sung mapping và kiểm tra webhook payload. |
| Webhook cập nhật trạng thái hai lần | Provider retry event, không dedupe | Unique constraint theo provider event ID. |
| Trạng thái bị lùi do event đến sai thứ tự | Giả định webhook luôn đúng thứ tự | Lưu event history và áp dụng state transition có quy tắc. |
| Timeout gây gửi trùng | Không biết relay đã nhận hay chưa | Ghi UNKNOWN, reconcile trước retry; dùng idempotency API nếu có. |
| Log lộ dữ liệu cá nhân | Ghi toàn bộ MIME/exception/recipient | Log key và metadata tối thiểu, che thông tin. |
| Message key dùng như token truy cập | Nhầm correlation ID với authorization | Kiểm tra quyền độc lập trên mọi endpoint tra cứu. |

## 16. Bài tập thực hành

### Bài 1 — Phân biệt các ID

Một email có application key `msg-A`, attempt `att-1` rồi retry `att-2`, RFC Message-ID khác nhau ở mỗi lần và SMTP queue ID do relay tạo. Hãy mô tả ID nào ổn định qua retry và ID nào thuộc một lần submission.

### Bài 2 — Thêm custom header

Tạo một `MimeMessage` bằng Spring Mail, gọi `setText(...)`, sau đó đặt:
- `X-Application-Message-Key`;
- `X-Correlation-ID`;
- `X-Mail-Attempt-ID`.

Gửi qua SMTP sandbox và kiểm tra raw source xem header nào được giữ lại.

### Bài 3 — Outbox

Thiết kế transaction tạo đơn hàng và một outbox row `PENDING`. Chứng minh khi process restart, worker vẫn tìm được message key và tiếp tục xử lý.

### Bài 4 — Retry

Mô phỏng attempt đầu timeout và attempt thứ hai SMTP accepted. Hãy giữ cùng message key, tạo attempt ID mới và lưu từng kết quả riêng.

### Bài 5 — Message-ID

Gửi một email qua `JavaMailSenderImpl`, đọc `MimeMessage.getMessageID()` sau khi gửi nếu có, và lưu nó như metadata bổ sung. Giải thích vì sao không dùng giá trị này thay application key.

### Bài 6 — Webhook

Tạo một webhook event `bounced` có provider event ID. Xác minh chữ ký, deduplicate event, map provider message ID về attempt và cập nhật message status.

### Bài 7 — Kết quả UNKNOWN

Giả lập SMTP relay có thể đã nhận message nhưng kết nối timeout trước khi worker nhận phản hồi. Thiết kế cách giữ trạng thái `UNKNOWN` và reconciliation trước retry.

### Bài 8 — Điều tra support

Cho message key, viết truy vấn lấy outbox, attempts và provider events. Thiết kế quyền để nhân viên support chỉ xem các email thuộc khách hàng/case được phân quyền.

## 17. Tổng kết

Để truy nguyên một email trong Spring Framework Mail, hãy tạo **application message key** khi tạo yêu cầu gửi, lưu key cùng outbox/business reference và dùng nó xuyên suốt log, worker, attempts và provider events. Có thể gắn key vào custom MIME header như `X-Application-Message-Key` để hỗ trợ tra cứu raw email, nhưng database/outbox vẫn là nguồn sự thật vì header có thể bị hệ thống trung gian loại bỏ.

Phân biệt key này với **correlation ID**, **attempt ID**, RFC **Message-ID**, SMTP queue ID và provider message ID. Giữ message key qua retry, tạo attempt ID mới cho mỗi lần thử, ghi nhận `SMTP_ACCEPTED` riêng với `DELIVERED`, và xử lý kết quả `UNKNOWN` khi submission timeout. Cuối cùng, xác thực webhook, chống event trùng, giới hạn quyền tra cứu và không đưa dữ liệu nhạy cảm vào header/log. Với những quy tắc đó, một email có thể được truy tìm từ nghiệp vụ ban đầu tới các lần gửi và sự kiện giao nhận mà không cần dựa vào subject hoặc nội dung thư.
