# Gửi lại sau timeout mà không xét khả năng server đã nhận

Trong **Spring Framework Mail**, một lỗi vận hành nguy hiểm là bắt mọi exception từ `JavaMailSender.send(...)` rồi lập tức gửi lại email, với giả định: **“Không thấy kết quả thành công nghĩa là SMTP server chưa nhận thư.”** Giả định đó không đúng trong môi trường mạng phân tán.

Ví dụ, ứng dụng đang gửi email hóa đơn cho khách hàng. Nó đã truyền toàn bộ nội dung SMTP `DATA`, SMTP relay đã lưu email vào hàng đợi và chuẩn bị trả `250 OK`, nhưng kết nối mạng đứt ngay trước khi ứng dụng nhận được phản hồi. `JavaMailSender` có thể báo timeout hoặc lỗi kết nối; ứng dụng tưởng thất bại, lập tức retry. Kết quả: **relay có thể nhận hai bản email giống nhau**, dù ứng dụng chỉ tạo một yêu cầu nghiệp vụ.

Vấn đề không nằm ở việc “có nên retry” nói chung mà ở chỗ **phải biết kết quả của lần gửi trước có đủ chắc chắn hay không**. Nếu đã có bằng chứng SMTP server từ chối message trước khi chấp nhận, việc retry có thể phù hợp. Nếu server đã chấp nhận, không submit lần nữa. Nếu kết quả chưa xác định, phải ghi nhận **UNKNOWN**, đối soát khi có thể, và áp dụng quyết định có kiểm soát theo loại email.

Bài học này phân tích chính xác thời điểm có thể xảy ra duplicate trong SMTP, cách Spring Mail/Jakarta Mail báo lỗi, giới hạn của `Message-ID` và idempotency key, thiết kế transactional outbox, attempt history, lease/recovery, phương án reconciliation, kiểm thử lỗi “server accepted nhưng client timeout” và runbook vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao một timeout không chứng minh SMTP server chưa chấp nhận email.
2. Mô tả các giai đoạn `CONNECT → EHLO/TLS/AUTH → MAIL FROM → RCPT TO → DATA → final 250`.
3. Phân biệt **SMTP submission accepted**, **delivery deferred**, **delivered** và **đã vào Inbox**.
4. Xác định các bằng chứng cho kết quả `ACCEPTED`, `PROVEN_NOT_ACCEPTED` và `UNKNOWN`.
5. Phân loại connect/read/write timeout theo **giai đoạn giao thức**, thay vì chỉ nhìn exception class.
6. Hiểu giới hạn của `MailSendException`, `MailAuthenticationException` và nested Jakarta Mail exceptions.
7. Tránh lỗi `catch (MailException) { retry(); }`.
8. Thiết kế message key, attempt ID, outbox và unique business idempotency key.
9. Xử lý crash sau SMTP acceptance nhưng trước database commit.
10. Tránh retry tự động một job có lease hết hạn nếu kết quả mạng chưa rõ.
11. Biết khi nào có thể dùng provider logs/API/webhook để đối soát.
12. Hiểu vì sao RFC `Message-ID` hoặc custom header không tạo exactly-once SMTP.
13. Xử lý partial success khi gửi nhiều recipients/messages.
14. Thiết lập retry budget, exponential backoff và trạng thái dead letter.
15. Viết unit/integration tests có fault injection sau `DATA`.
16. Vận hành các job `UNKNOWN` mà không làm tăng spam, duplicate hoặc rò rỉ thông tin.

## 2. Tình huống thực tế: cùng một email bị gửi hai lần

Giả sử hệ thống gửi thông báo thanh toán:

```text
Business event:
Payment #P-1001 completed
             |
             v
Email job msg-1001
             |
             v
Spring JavaMailSender
             |
             v
SMTP relay
             |
             v
Recipient mailbox
```

Tại lần thử thứ nhất:

```text
Application                         SMTP relay
     |                                   |
     |---- TCP/TLS/AUTH ---------------->|
     |---- MAIL FROM ------------------->|
     |---- RCPT TO --------------------->|
     |---- DATA ------------------------>|
     |<--- 354 Start mail input --------|
     |---- headers + body ------------->|
     |---- end-of-DATA <CRLF>.<CRLF> -->|
     |                                   |
     |                                   | queue message
     |                                   | prepare 250 OK
     |<---------- network breaks --------X
     |                                   |
     | java.net.SocketTimeoutException   |
     |                                   |
     v                                   v
Application thinks "failed"       Relay has accepted mail
     |
     | retry same email immediately
     v
SMTP relay accepts second copy
```

Kết quả có thể là hai email:
- Cùng subject.
- Cùng nội dung.
- Cùng recipient.
- Thậm chí có cùng RFC `Message-ID` nếu ứng dụng cố tái sử dụng.
- Nhưng vẫn là **hai SMTP submissions** độc lập.

Nếu đó là newsletter, người nhận khó chịu. Nếu đó là email yêu cầu xác nhận thanh toán, họ có thể hiểu nhầm giao dịch bị thực hiện hai lần. Với email có link hành động, duplicate còn gây rối ở tầng nghiệp vụ.

**Kết luận cốt lõi:** Một lỗi phía client chỉ chứng minh **client không hoàn tất quan sát thành công**; không tự chứng minh phía server không thực hiện side effect.

## 3. Phân biệt ba loại “thành công” của email

Một ứng dụng mail cần tách:

| Trạng thái | Bằng chứng | Không chứng minh |
|---|---|---|
| **QUEUED** | App đã lưu outbox/job hoặc queue chấp nhận yêu cầu | SMTP server đã nhận |
| **SMTP_ACCEPTED** | SMTP server/relay chấp nhận submission theo phản hồi cuối phù hợp | Đã giao tới mailbox người nhận |
| **DELIVERED** | Provider/receiver có event giao thư theo định nghĩa của họ | Người dùng đã xem hoặc thư chắc chắn vào Inbox |
| **OPENED/ENGAGED** | Có tín hiệu tracking/interaction phù hợp | Mọi người nhận đều đọc; tracking luôn đáng tin |

Lời gọi:

```java
javaMailSender.send(mimeMessage);
```

không ném lỗi thường cho biết submission hoàn tất theo API transport được dùng, **không phải** email đã được người nhận mở hay được đảm bảo vào Inbox.

### 3.1. Provider accepted rồi vẫn có thể deferred

SMTP relay nhận email vào hàng đợi, nhưng server đích tạm trả lỗi. Provider có thể tiếp tục retry delivery trong nhiều giờ theo chính sách.

```text
Application -> Provider: SMTP_ACCEPTED
Provider -> Receiver: 451 temporary failure
Provider -> Receiver later: retry
```

**Đừng submit một bản email mới** qua Spring Mail chỉ vì delivery status tạm là `DEFERRED`. Đó là hai tầng retry khác nhau:
- Application retry **submission**.
- Provider retry **delivery** sau khi đã nhận trách nhiệm.

### 3.2. Retry của provider không phải retry của ứng dụng

Nếu provider đang retry giao thư, ứng dụng không nên tự can thiệp bằng một email mới trừ khi có thiết kế backup delivery có kiểm soát và chấp nhận rủi ro duplicate.

## 4. Đi qua từng giai đoạn của một SMTP transaction

Một phiên submission SMTP thông thường:

```text
1. TCP connect
2. (Implicit TLS hoặc EHLO + STARTTLS)
3. EHLO / authentication
4. MAIL FROM:<sender>
5. RCPT TO:<recipient>
6. DATA
7. Server: 354
8. Client: headers + body + end-of-DATA
9. Server: 250 (nếu accepted)
10. QUIT / connection close
```

Các reply trong từng giai đoạn có ý nghĩa khác nhau.

### 4.1. Connect, TLS và AUTH

Nếu client **chưa thiết lập kết nối** hoặc **chưa có lệnh gửi message**, relay không thể đã nhận message từ attempt đó. Ví dụ, kết nối TCP bị từ chối trước khi tạo phiên SMTP có thể là bằng chứng chưa submit.

Nhưng thông tin này phải đến từ **bằng chứng giao thức/thời điểm thực tế**, không chỉ từ một exception outer class chung chung.

### 4.2. MAIL FROM và RCPT TO

`MAIL FROM` khai báo envelope sender; `RCPT TO` khai báo recipient được yêu cầu. Server có thể chấp nhận recipient ở giai đoạn này, nhưng **đó chưa phải acceptance của toàn bộ nội dung message**.

Với nhiều recipients, có thể có recipient được chấp nhận và recipient bị từ chối. Những ngoại lệ/partial success này phải được xử lý riêng.

### 4.3. DATA và phản hồi 354

Khi client gửi `DATA`, relay thường trả `354`, nghĩa là client có thể truyền nội dung. `354` **không có nghĩa message đã được nhận vào queue để giao**.

### 4.4. Kết thúc DATA

Khi client truyền xong nội dung và dấu kết thúc `<CRLF>.<CRLF>` (theo SMTP DATA framing), server xử lý rồi trả phản hồi cuối.

- **2xx cuối sau DATA:** message được server chấp nhận tại giai đoạn submission.
- **4xx/5xx cuối sau DATA:** server báo không chấp nhận theo semantics của giao thức, cần xử lý theo loại mã và chính sách.
- **Không có phản hồi quan sát được:** không thể suy luận chắc chắn accepted hay rejected chỉ từ timeout.

Một `250` trả về cho `EHLO` hoặc `RCPT TO` không thay thế `250` cuối sau DATA.

### 4.5. QUIT và disconnect

Một kết nối mất sau khi server đã trả `250` cuối vẫn có thể dẫn tới lỗi hoặc trạng thái không rõ ở phía caller, tùy cách thư viện quản lý shutdown. Message đã được accepted trước đó không bị thu hồi chỉ vì `QUIT`/TCP close không diễn ra trọn vẹn.

## 5. Ma trận bằng chứng tại từng phase

| Vị trí lỗi đã được xác minh | Server có thể đã accepted email chưa? | Phân loại thận trọng |
|---|---|---|
| Validation lỗi, chưa gọi SMTP | Không | `PERMANENT_INPUT_FAILURE` |
| DNS resolution fail trước TCP connect | Không đối với attempt này | `PROVEN_NOT_ACCEPTED` |
| TCP connect bị từ chối trước SMTP session | Không đối với attempt này | `PROVEN_NOT_ACCEPTED` |
| TLS handshake fail trước khi truyền nội dung | Không đối với attempt này | `PROVEN_NOT_ACCEPTED` / config error |
| AUTH reject trước gửi message | Không đối với attempt này | `PROVEN_NOT_ACCEPTED` / auth error |
| MAIL FROM bị từ chối rõ ràng | Message chưa được accepted | `PROVEN_NOT_ACCEPTED` |
| RCPT TO bị từ chối rõ ràng trước DATA | Message chưa được accepted cho recipient đó | Xử lý theo recipient |
| Server trả 4xx/5xx cuối sau DATA và client nhận rõ reply | Server báo không accepted theo giao thức | `PROVEN_NOT_ACCEPTED` theo evidence |
| Timeout trong lúc truyền DATA | Chưa kết luận chắc chắn | `UNKNOWN` nếu không có bằng chứng phủ định |
| Timeout chờ reply sau end-of-DATA | **Có thể đã accepted** | `UNKNOWN` |
| Client nhận 250 cuối sau DATA | Có bằng chứng accepted | `SMTP_ACCEPTED` |
| Client nhận 250 nhưng DB update fail | Accepted, DB chưa ghi nhận | Cần reconciliation/không resend mù |
| Provider báo deferred sau SMTP_ACCEPTED | Đã accepted; delivery đang chờ | Không retry submission |
| Lỗi ở consumer/queue sau message đã được gửi | Có thể đã accepted | `UNKNOWN` nếu thiếu receipt bền vững |

**Lưu ý:** Mã lỗi từ transport wrapper đôi khi không lộ phase chính xác. Nếu không thể chứng minh chưa accepted, hãy chọn trạng thái **UNKNOWN** thay vì “retryable chắc chắn”.

## 6. Timeout không phải một loại lỗi duy nhất

Trong Spring Mail/Jakarta Mail, các timeout thường gặp:

| Cấu hình | Mục đích | Một timeout gợi ý điều gì |
|---|---|---|
| `mail.smtp.connectiontimeout` | Giới hạn chờ TCP connect | Kết nối chưa được thiết lập trong thời gian cho phép |
| `mail.smtp.timeout` | Giới hạn đọc socket | Đang chờ phản hồi SMTP/TLS ở phase nào đó |
| `mail.smtp.writetimeout` | Giới hạn ghi socket | Không hoàn tất ghi dữ liệu trong thời gian cho phép |
| Worker/job deadline | Giới hạn toàn bộ attempt ở tầng ứng dụng | Attempt quá thời hạn, cần biết đã có side effect chưa |
| Queue receive timeout | Chờ lấy job khỏi queue | Không cho biết SMTP đã xảy ra hay chưa |

### 6.1. Connect timeout

Nếu xác minh kết nối chưa thành lập và chưa có giao thức SMTP được thực hiện, retry sau backoff có thể an toàn về mặt duplicate submission. Nhưng vẫn phải cân nhắc provider outage, quota và routing permissions.

### 6.2. Read timeout

`SocketTimeoutException: Read timed out` **không nói rõ đang chờ greeting, EHLO, AUTH, 354 hay 250 cuối**. Cùng một exception class có thể xuất hiện:
- trước khi gửi message;
- sau khi truyền xong DATA;
- sau khi server có thể đã chấp nhận.

Vì vậy **không được phân loại read timeout = chắc chắn chưa gửi**.

### 6.3. Write timeout

Nếu socket write timeout trong lúc truyền dữ liệu, client có thể không biết chính xác server nhận đến đâu. Dữ liệu đã ghi vào socket có thể nằm trong network buffers, còn server có thể đã đọc một phần hoặc toàn bộ.

Không mặc định “write chưa hoàn tất thì server chưa nhận message” nếu không có bằng chứng chắc chắn rằng end-of-DATA không bao giờ đến được server.

### 6.4. Tổng deadline

Một attempt có thể gồm nhiều lệnh SMTP, xử lý MIME và database writes. Socket timeout riêng lẻ **không phải** deadline tổng. Nếu worker bị process kill vì hết deadline, khả năng outcome chưa rõ càng tăng.

## 7. Cấu hình Spring Boot: timeout hợp lý nhưng không thay đổi semantics

Ví dụ SMTP submission port 587 với STARTTLS:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    protocol: smtp
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
```

Các cổng/hostname chỉ để minh họa. Giá trị thật phụ thuộc provider, hạ tầng và kết quả đo thực tế.

### 7.1. Thời gian quá ngắn có thể tăng UNKNOWN

Giảm `mail.smtp.timeout` từ 30 giây xuống 1 giây không tự khiến hệ thống đáng tin hơn. Nếu provider phản hồi chậm ở thời điểm final DATA acceptance, timeout quá ngắn có thể làm tăng số attempts `UNKNOWN` và tăng số quyết định retry khó xử lý.

### 7.2. Thời gian quá dài cũng nguy hiểm

Timeout quá dài chiếm worker threads, trì hoãn shutdown, tăng backlog và có thể làm lease outbox hết hạn trước khi SMTP attempt kết thúc.

Chọn thời gian dựa trên:
- SLA/provider latency;
- concurrency budget;
- worker lease duration;
- network path;
- throughput;
- khả năng đối soát;
- nghiệp vụ chấp nhận chờ bao lâu.

### 7.3. TLS mode phải đúng

587 thường dùng `smtp` + STARTTLS required. 465 thường dùng implicit TLS, ví dụ `mail.smtp.ssl.enable=true`. Sai TLS mode có thể tạo lỗi connection/handshake, nhưng **khi đã có thông tin endpoint rõ**, không nên che lỗi bằng tắt certificate hostname verification.

## 8. Một catch block gây gửi trùng như thế nào?

Anti-pattern rất phổ biến:

```java
public void sendWithRetry(MimeMessage message) {
    for (int attempt = 1; attempt <= 3; attempt++) {
        try {
            mailSender.send(message);
            return;
        } catch (MailException ex) {
            // Sai: không biết server đã accepted chưa.
            log.warn("Send failed; retrying", ex);
        }
    }
}
```

Vấn đề:
1. `MailException` không chứa trong chính loại exception một cam kết rằng server chưa nhận message.
2. Retry ngay có thể gửi trùng sau timeout cuối DATA.
3. Không có backoff/rate limit.
4. Không có persisted attempt history.
5. Không có trạng thái `UNKNOWN`.
6. Không phân biệt lỗi permanent với transient.
7. Dùng lại cùng `MimeMessage` mutable có thể kéo theo thêm vấn đề về state/headers.
8. Không có idempotency ở tầng business.
9. Nếu process crash giữa attempts, không có căn cứ để quyết định tiếp tục.
10. Không theo dõi provider có đang tự retry delivery hay không.

**Không được suy ra “retry an toàn” chỉ vì một exception đã bị ném ra từ `send()`.**

## 9. Spring JavaMailSender có thể báo lỗi như thế nào?

Spring Mail thường cung cấp:
- `MailException`: nhóm exception cơ sở.
- `MailSendException`: lỗi trong quá trình gửi.
- `MailAuthenticationException`: lỗi liên quan xác thực.
- `MailPreparationException`: lỗi tạo message ở tầng chuẩn bị.
- `MailParseException`: lỗi phân tích message/address.
- Nested Jakarta Mail `MessagingException`, `SendFailedException` và nhiều network causes.

Tên class phản ánh **khu vực lỗi được thư viện phát hiện**, không phải một proof-of-nonacceptance của relay.

### 9.1. MailSendException và failed messages

`MailSendException` có API hỗ trợ quan sát những message bị báo lỗi trong một lời gọi gửi nhiều messages. Nhưng “failed” theo exception handling ở client không có nghĩa SMTP server chắc chắn **chưa từng chấp nhận** message tương ứng.

Đặc biệt:
- Connection có thể mất sau final DATA.
- Batch gửi nhiều messages có thể đã submit một phần.
- Exception cause có thể được gói nhiều lớp.
- Provider có thể trả response đặc thù hoặc partial recipient result.

Không viết thuật toán resend dựa duy nhất vào `MailSendException.getFailedMessages()` như thể đó là tập “chắc chắn chưa được relay accepted”.

### 9.2. MailAuthenticationException

Nếu chắc chắn AUTH bị từ chối trước nội dung message, có thể kết luận attempt đó chưa accepted. Nhưng policy thường là sửa secret, scope hoặc provider configuration, **không retry liên tục** mỗi vài mili giây.

### 9.3. MessagingException.getNextException()

Jakarta Mail cho phép lồng các exception chi tiết. Khi chẩn đoán, có thể cần quan sát:
- chained `MessagingException`;
- underlying socket exception;
- SMTP reply/command;
- provider-specific exception;
- phase mà wrapper đang thực hiện.

Không in toàn bộ exception chain vào logs công khai nếu có thể chứa recipient hoặc SMTP metadata nhạy cảm.

### 9.4. Lỗi build MIME trước network

Nếu validation thất bại rõ ràng **trước khi gọi `send(...)`**, ví dụ recipient format bị từ chối trong bước dựng message, đây là lỗi đầu vào/cấu hình, không phải kết quả UNKNOWN của SMTP submission.

Nhưng nếu code vừa build MIME vừa trigger I/O qua provider-specific operations, phải tách boundaries để biết lúc nào network side effect bắt đầu.

## 10. Định nghĩa outcome chung: không chỉ boolean

Một mô hình an toàn hơn:

```java
public enum SubmissionOutcome {
    SMTP_ACCEPTED,
    PROVEN_NOT_ACCEPTED_RETRYABLE,
    PROVEN_NOT_ACCEPTED_PERMANENT,
    UNKNOWN
}
```

Ý nghĩa:

| Outcome | Có được tự retry? | Ghi chú |
|---|---|---|
| `SMTP_ACCEPTED` | **Không** | Provider đã accepted submission |
| `PROVEN_NOT_ACCEPTED_RETRYABLE` | Có thể | Chỉ sau policy/backoff/quota |
| `PROVEN_NOT_ACCEPTED_PERMANENT` | Không | Sửa dữ liệu/credential/cấu hình |
| `UNKNOWN` | **Không retry mù** | Reconciliation hoặc quyết định có kiểm soát |

### 10.1. UNKNOWN là thông tin có ích

`UNKNOWN` không có nghĩa hệ thống kém chất lượng; đó là cách diễn đạt đúng thông tin đang thiếu. Một state machine không có `UNKNOWN` thường buộc phải **nói sai** bằng một trong hai nhãn:
- FAILED, rồi retry tạo duplicate.
- SUCCESS, rồi có thể làm mất email thực sự chưa được accepted.

### 10.2. Không gộp UNKNOWN vào RETRY_WAIT

Nếu scheduler chỉ query `status IN ('PENDING','RETRY_WAIT')`, hãy giữ `UNKNOWN` ở trạng thái riêng không được tự động claim. Khi điều tra hoàn tất, hệ thống mới chuyển sang hướng xử lý phù hợp theo policy.

### 10.3. ACCEPTED có thể đến từ nguồn nào?

Nguồn rõ ràng có thể là:
- client nhận final SMTP 250 cho đúng message;
- provider API/log cung cấp bằng chứng accepted có thể liên kết chắc với attempt;
- một delivery event được xác thực đủ để chứng minh upstream đã nhận email.

Không lấy một log `250` mơ hồ cho EHLO/RCPT làm proof accepted; phải có phase/correlation tương ứng.

## 11. Phân biệt email logic, attempt và provider submission

Một email nghiệp vụ có thể có nhiều attempts, nhưng **đó không phải lý do cho phép nhiều successful submissions**.

```text
Business event: order-1001-paid
    |
    v
Email logic:
messageKey = msg-1001
    |
    +--> attempt att-1
    |      provider A
    |      status = PROVEN_NOT_ACCEPTED_RETRYABLE
    |
    +--> attempt att-2
           provider A
           status = SMTP_ACCEPTED
           |
           +--> delivery deferred
           +--> delivered
```

Khi attempt thứ hai đã `SMTP_ACCEPTED`, application không submit attempt thứ ba chỉ vì chưa thấy delivery event.

### 11.1. Message key

`messageKey` là khóa do ứng dụng tạo cho một **email logic**. Nó giữ nguyên qua retry và reconcile.

### 11.2. Attempt ID

`attemptId` là khóa cho một **lượt giao tiếp với provider**. Mỗi attempt có:
- provider/route;
- start time;
- completion/outcome;
- safe error code;
- optional provider reference;
- correlation metadata.

### 11.3. Provider message ID

Nếu provider có message ID/queue ID qua SMTP response/API/webhook, lưu riêng. Không giả định generic SMTP luôn có một ID được chuẩn hóa cho tra cứu.

### 11.4. RFC Message-ID

Header `Message-ID` là metadata của email theo RFC, **không** là giao thức idempotency được SMTP server cam kết thực hiện. Hai submissions cùng Message-ID vẫn có thể tạo hai messages trong mailbox.

## 12. Idempotency ở tầng business khác exactly-once SMTP

Một hệ thống có thể ngăn business event tạo hai job:

```text
PaymentCompleted(orderId=1001)
     |
     v
Unique business key:
tenantId + eventType + orderId + notificationType
     |
     v
One email outbox row
```

Nhưng sau khi job tồn tại, việc SMTP submit có thể mơ hồ.

### 12.1. Idempotency bảo vệ được điều gì?

- HTTP client retry không tạo hai outbox rows cho cùng yêu cầu.
- Event bus redelivery không tạo hai email logic.
- Scheduler nhiều replicas không tạo hai occurrences trùng.
- Worker claim có thể dùng unique constraint để tránh hai attempts đồng thời theo policy.

### 12.2. Idempotency không bảo vệ được điều gì?

- SMTP transport không tự hiểu business key.
- SMTP relay không bắt buộc dedupe theo `X-Idempotency-Key`.
- RFC Message-ID không phải khóa unique của mailbox.
- Một client retry sau UNKNOWN có thể tạo hai accepted submissions.

### 12.3. Ba dạng bảo đảm cần tách

| Khẳng định | Có thể xây được không? |
|---|---|
| Một business event tạo một email logic | Có, với unique business key |
| Mỗi thời điểm chỉ một worker claim một job | Có, với atomic claim/lease |
| SMTP submission exactly once qua lỗi mạng bất kỳ | **Không thể mặc định bảo đảm bằng generic SMTP** |

Đừng quảng cáo “exactly once email delivery” chỉ vì đã thêm database transaction hoặc queue idempotency key.

## 13. Transactional outbox để giữ email logic qua sự cố

Một thiết kế bền vững:

```text
Business transaction
    |
    +-- update business state
    +-- insert email_outbox(messageKey, PENDING)
    |
    v
Commit
    |
    v
Outbox dispatcher
    |
    v
Claim job + attempt record
    |
    v
JavaMailSender.submit outside DB transaction
    |
    +--> accepted
    +--> proven rejected/transient
    +--> unknown
    |
    v
Persist outcome
```

Tại sao cần outbox?
- Không mất yêu cầu khi process crash.
- Giữ lịch sử đã thử gửi.
- Ngăn producer tạo job trùng qua unique keys.
- Cho phép retry/backoff có kiểm soát.
- Có chỗ lưu `UNKNOWN` để tránh replay nguy hiểm.
- Cho phép can thiệp thủ công và reconciliation.

### 13.1. Không giữ transaction database trong SMTP call

Một anti-pattern:

```java
@Transactional
public void createAndSendEmail(...) {
    businessRepository.save(...);
    mailSender.send(...);
    outboxRepository.markAccepted(...);
}
```

Nếu SMTP server accepted nhưng DB commit lỗi, database rollback **không thể thu hồi email**. Khi business event được xử lý lại, email có thể bị submit lần nữa.

Thiết kế đúng là commit business event + outbox **trước**, sau đó submit ngoài DB transaction, rồi ghi kết quả bằng transaction khác.

## 14. Schema outbox và attempt history tham khảo

Ví dụ PostgreSQL:

```sql
CREATE TABLE email_outbox (
    message_key UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    business_event_key VARCHAR(160) NOT NULL,
    category VARCHAR(40) NOT NULL,
    recipient_ref VARCHAR(256) NOT NULL,
    payload_ref VARCHAR(512) NOT NULL,
    status VARCHAR(40) NOT NULL,
    send_at TIMESTAMPTZ NOT NULL,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_email_business_event
        UNIQUE (tenant_id, business_event_key),
    CONSTRAINT ck_email_attempt_count
        CHECK (attempt_count >= 0)
);

CREATE TABLE email_submit_attempt (
    attempt_id UUID PRIMARY KEY,
    message_key UUID NOT NULL
        REFERENCES email_outbox(message_key),
    attempt_number INTEGER NOT NULL,
    provider_key VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(48) NOT NULL,
    safe_error_code VARCHAR(120),
    smtp_phase VARCHAR(48),
    provider_reference VARCHAR(255),
    correlation_key VARCHAR(160),
    CONSTRAINT uq_email_attempt_number
        UNIQUE (message_key, attempt_number)
);

CREATE INDEX idx_email_outbox_due
    ON email_outbox(next_attempt_at, send_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE INDEX idx_email_outbox_unknown
    ON email_outbox(updated_at)
    WHERE status = 'UNKNOWN';
```

Đây là schema minh họa, chưa gồm toàn bộ CHECK constraints, retention, access controls hoặc trạng thái delivery; production cần mở rộng theo yêu cầu.

### 14.1. Vì sao có cả outbox và attempt?

Outbox mô tả **một email logic**. Attempt mô tả **một lần thử gửi thực tế**. Nếu lần đầu bị timeout và một người vận hành cần điều tra, lịch sử attempt là dữ liệu quan trọng để biết:
- provider nào được dùng;
- lúc nào bắt đầu;
- lỗi ở phase nào nếu biết;
- có nhận SMTP acceptance không;
- có thể query provider bằng correlation nào.

### 14.2. Snapshot nội dung và quyền truy cập

Nếu nội dung email thay đổi giữa các lần retry, người nhận có thể nhận các phiên bản khác nhau. Cần lưu:
- template ID/version hoặc rendered snapshot;
- recipient/sender identity;
- attachment references có lifetime rõ;
- business parameters không nhạy cảm;
- data retention/encryption phù hợp.

Không lưu reset password token, OTP hoặc dữ liệu khách hàng plaintext lâu hơn cần thiết chỉ để hỗ trợ retry.

## 15. State machine cho submission có kết quả UNKNOWN

Một ví dụ:

```text
           PENDING
              |
              v
          CLAIMED
              |
              v
           SENDING
         /    |     \
        /     |      \
       v      v       v
 SMTP_ACCEPTED  RETRY_WAIT  UNKNOWN
                    |         |
                    v         v
                 PENDING   RECONCILING
                              |
               +--------------+-------------+
               |              |             |
               v              v             v
         CONFIRMED_       CONFIRMED_     UNRESOLVED
          ACCEPTED        NOT_ACCEPTED
               |              |             |
               v              v             v
         STOP SUBMIT      SAFE RETRY     POLICY/REVIEW
```

Các tên là domain states gợi ý; không phải Spring Mail built-in enum.

### 15.1. ACCEPTED là điểm kết thúc việc retry submission

Sau `SMTP_ACCEPTED`, các trạng thái tiếp theo như `DEFERRED`, `DELIVERED`, `BOUNCED` nên thuộc **delivery tracking** riêng.

### 15.2. Retry wait chỉ dành cho kết quả có thể retry

`RETRY_WAIT` nên được tạo khi:
- có bằng chứng attempt chưa accepted;
- lỗi được phân loại transient;
- retry budget chưa hết;
- message chưa expired;
- route vẫn được phép.

### 15.3. UNKNOWN không tự có deadline “retry ngay”

Có thể đặt deadline reconciliation hoặc manual review, nhưng không đồng nghĩa hết thời hạn đó là bằng chứng chưa gửi. Nếu hệ thống quyết định gửi lại sau deadline dù vẫn UNKNOWN, đó là **chính sách chấp nhận duplicate risk**, phải được phân biệt với “safe retry”.

## 16. Atomic claim và lease không giải quyết được SMTP ambiguity

Một dispatcher dùng PostgreSQL:

```sql
WITH due AS (
    SELECT message_key
    FROM email_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND send_at <= :now
      AND next_attempt_at <= :now
      AND (expires_at IS NULL OR expires_at > :now)
    ORDER BY next_attempt_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE email_outbox e
SET status = 'SENDING',
    attempt_count = e.attempt_count + 1,
    lease_token = :leaseToken,
    lease_expires_at = :leaseExpiresAt,
    updated_at = :now
FROM due
WHERE e.message_key = due.message_key
RETURNING
    e.message_key,
    e.attempt_count,
    e.lease_token;
```

Một transaction ngắn có thể claim job và insert attempt record. Sau khi commit, worker mới gọi SMTP.

### 16.1. Claim atomically tránh hai workers gửi đồng thời

Nếu hai workers cùng poll, `FOR UPDATE SKIP LOCKED` giúp chia công việc theo DB row locking, không claim cùng row trong cùng thời điểm. Đây là cải thiện quan trọng.

### 16.2. Nhưng worker vẫn có thể chết sau SMTP accepted

```text
TX1: claim job; commit
      |
      v
SMTP: server accepted DATA
      |
      v
worker process crashes
      |
      v
TX2: mark accepted never executes
```

Sau restart, DB vẫn có thể là `SENDING` với lease đã hết hạn. Nếu worker recovery đổi tất cả stale `SENDING` thành `PENDING`, nó sẽ **gửi trùng** những email thực tế đã accepted.

### 16.3. Lease expiry không là bằng chứng chưa submit

Lease expiry chỉ cho biết worker chưa cập nhật/renew ownership đúng hạn. Nó không cho biết SMTP đã nhận hay chưa.

Vì vậy stale `SENDING` cần:
- tra cứu attempt history;
- phân loại theo phase evidence nếu có;
- chuyển `UNKNOWN` khi thiếu bằng chứng;
- đối soát trước khi quyết định resubmit.

### 16.4. Fencing token chỉ bảo vệ DB state

Ví dụ update outcome:

```sql
UPDATE email_outbox
SET status = 'SMTP_ACCEPTED',
    lease_token = NULL,
    lease_expires_at = NULL,
    updated_at = :now
WHERE message_key = :messageKey
  AND status = 'SENDING'
  AND lease_token = :leaseToken;
```

Nếu kết quả 0 rows, worker không còn sở hữu lease hợp lệ. Không ghi đè một state mới. Nhưng fencing **không ngăn SMTP server đã nhận một message từ stale worker**.

## 17. Không thể atomically commit cả database và SMTP

Sự khác biệt giữa local transaction và network side effect:

```text
Database transaction             SMTP relay
        |                            |
        | BEGIN                      |
        | UPDATE status=SENDING      |
        | COMMIT                     |
        |                            |
        |---- send email ----------->|
        |<--- SMTP 250 OK -----------|
        |                            |
        | BEGIN                      |
        | UPDATE accepted            |
        | COMMIT (may fail!)         |
```

Không có một database transaction thông thường có thể bao gồm SMTP server của provider như một participant hỗ trợ 2-phase commit.

### 17.1. Cố gửi trong transaction cũng không giải quyết

Đặt `@Transactional` quanh `send()` không biến SMTP thành một resource có rollback. DB rollback được, nhưng email đã accepted sẽ không bị thu hồi.

### 17.2. Outbox cho at-least-once execution, không tự cho exactly-once effect

Outbox có thể bảo đảm công việc không mất ở ứng dụng. Nhưng nếu phải retry attempt UNKNOWN, **external effect** có thể xảy ra nhiều lần.

Một hệ thống tốt cần xác định:
- Với email nào ưu tiên **không mất** hơn **không trùng**?
- Với email nào ưu tiên tránh duplicate?
- Có provider hỗ trợ request idempotency thật không?
- Có thể reconcile trước khi retry không?
- Có thể chấp nhận manual review không?

Đây là quyết định nghiệp vụ và vận hành, không chỉ một annotation Java.

## 18. Cách tạo message key và idempotency key

Ví dụ một sự kiện thanh toán:

```text
tenantId: tenant-7
businessEvent: payment-settled
paymentId: pay-1001
notificationType: receipt-v1

business key:
tenant-7|payment-settled|pay-1001|receipt-v1

messageKey:
msg-4a3... (opaque UUID)
```

Khi event bus redelivery, unique business key ngăn tạo email logic thứ hai. Nhưng nếu SMTP attempt đầu UNKNOWN, cùng message key **không bảo đảm relay deduplicate**.

### 18.1. Không tái sử dụng HTTP idempotency key tùy tiện

Idempotency key do người dùng gửi phải được scope theo tenant/operation, có validation và retention. Không để tenant A đoán key của tenant B rồi truy cập kết quả.

### 18.2. Header theo dõi không phải lệnh chống gửi trùng

Có thể gắn:

```java
mimeMessage.setHeader(
    "X-Application-Message-Key",
    messageKey
);
mimeMessage.setHeader(
    "X-Mail-Attempt-ID",
    attemptId
);
```

Các headers này có thể hỗ trợ đối soát nếu provider bảo toàn chúng, nhưng:
- không phải mọi provider cho phép query theo custom header;
- người nhận có thể thấy header;
- SMTP không tự dedupe theo header;
- không nên đưa secret/customer ID nhạy cảm.

### 18.3. RFC Message-ID là một metadata riêng

`Message-ID` thường giúp mail clients liên kết một email, nhưng cùng một giá trị có thể xuất hiện trong hai SMTP submissions. Không dùng nó như một guarantee rằng recipient sẽ chỉ nhận một bản.

### 18.4. “Deduplication ở phía người nhận” không chắc chắn

Một số mail clients có thể gom thread hoặc hiển thị trùng ít rõ ràng, nhưng đó là behavior tùy hệ thống. Không được dựa vào UI grouping làm biện pháp chống duplicate ở giao thức.

## 19. Thiết kế adapter Spring Mail với kết quả thận trọng

Một adapter chuẩn hóa outcome cần đặc biệt tránh sai lầm “exception == NOT_ACCEPTED”.

Ví dụ code minh họa:

```java
package com.example.mail;

import java.time.Instant;

public enum SubmitStatus {
    ACCEPTED,
    UNKNOWN
}

public record SubmitReceipt(
    String messageKey,
    String attemptId,
    SubmitStatus status,
    Instant observedAt
) {}
```

Adapter:

```java
package com.example.mail;

import java.time.Clock;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class ConservativeSmtpGateway {

    private final JavaMailSender mailSender;
    private final Clock clock;

    public ConservativeSmtpGateway(
            JavaMailSender mailSender,
            Clock clock) {
        this.mailSender = mailSender;
        this.clock = clock;
    }

    public SubmitReceipt submit(
            MailDraft draft,
            String attemptId) {

        MimeMessage mime = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

            helper.setFrom(draft.from());
            helper.setTo(draft.to());
            helper.setSubject(draft.subject());
            helper.setText(
                draft.plainText(),
                draft.htmlText()
            );

            mime.setHeader(
                "X-Application-Message-Key",
                draft.messageKey()
            );
            mime.setHeader(
                "X-Mail-Attempt-ID",
                attemptId
            );

        } catch (MessagingException ex) {
            // Input/preparation error trước khi gọi SMTP.
            throw new MailPreparationFailure(
                "MIME_PREPARATION_FAILED", ex
            );
        }

        try {
            mailSender.send(mime);

            return new SubmitReceipt(
                draft.messageKey(),
                attemptId,
                SubmitStatus.ACCEPTED,
                clock.instant()
            );
        } catch (MailException ex) {
            // Không có phase evidence: bảo thủ = UNKNOWN.
            throw new SubmissionOutcomeUnknown(
                draft.messageKey(),
                attemptId,
                ex
            );
        }
    }
}
```

`MailDraft`, `MailPreparationFailure` và `SubmissionOutcomeUnknown` là các model/exception do ứng dụng định nghĩa. Ví dụ cố ý không cố phân loại mọi lỗi Spring Mail thành an toàn retry chỉ bằng exception class.

### 19.1. Vì sao conservative default là UNKNOWN?

Khi dùng abstraction `JavaMailSender`, adapter không nhất thiết thấy từng SMTP command và reply. Nếu send ném exception, nó có thể không biết relay đã chấp nhận nội dung chưa.

Default `UNKNOWN` giúp tránh duplicate cho đến khi có thêm bằng chứng.

### 19.2. Khi nào có thể phân loại PROVEN_NOT_ACCEPTED?

Khi hệ thống có **bằng chứng đáng tin** rằng một attempt chưa được accepted, ví dụ:
- validation fail trước khi gọi network;
- TCP connect failure được xác minh trước SMTP session;
- SMTP server trả refusal ở phase xác định;
- provider API trả lỗi có contract cụ thể về non-acceptance.

Đừng “đoán phase” từ lời văn ngoại lệ chung. Có thể xây classifier dựa vào transport instrumentation hoặc một SMTP adapter chuyên sâu, nhưng cần kiểm thử với implementation đang dùng.

### 19.3. Không chỉ có try/catch; phải persist outcome

Một gateway có thể phát exception `SubmissionOutcomeUnknown`. Application service phải ghi kết quả vào durable state và dừng automatic resubmission. Nếu chỉ ném exception ra queue consumer rồi broker redeliver ngay, ta lại quay về lỗi ban đầu.

## 20. Worker orchestration: lưu UNKNOWN thay vì retry mù

Một luồng xử lý hợp lý:

```text
Claim due job
      |
      v
Create attempt record
      |
      v
Build validated MIME
      |
      v
SMTP submit
      |
      +--> returned successfully
      |       |
      |       v
      |    save SMTP_ACCEPTED
      |
      +--> explicit, proven non-acceptance
      |       |
      |       +--> transient -> RETRY_WAIT
      |       |
      |       +--> permanent -> DEAD_LETTER
      |
      +--> cannot determine acceptance
              |
              v
           save UNKNOWN
              |
              v
        reconciliation queue
```

### 20.1. Pseudocode

```java
ClaimedMail claim = repository.claimDueJob();

Attempt attempt = repository.startAttempt(claim);

try {
    SubmitReceipt receipt =
        smtpGateway.submit(claim.toMailDraft(), attempt.id());

    repository.markSmtpAccepted(
        claim.messageKey(),
        attempt.id(),
        receipt.observedAt(),
        claim.leaseToken()
    );

} catch (SubmissionOutcomeUnknown ex) {
    repository.markUnknown(
        claim.messageKey(),
        attempt.id(),
        "SMTP_ACCEPTANCE_NOT_OBSERVED",
        claim.leaseToken()
    );

    reconciliationQueue.requestReview(
        claim.messageKey(), attempt.id()
    );

} catch (MailPreparationFailure ex) {
    repository.markPermanentFailure(
        claim.messageKey(),
        attempt.id(),
        "MIME_PREPARATION_FAILED",
        claim.leaseToken()
    );
}
```

Đoạn pseudocode nhấn mạnh workflow, không phải source chạy độc lập; repository, claim, lease và failure mapping là các thành phần dự án phải triển khai. Nếu DB ghi `UNKNOWN` cũng thất bại, recovery phải xử lý stale `SENDING` như potentially unknown sau restart.

### 20.2. Cẩn trọng với transaction boundary

- Transaction claim/insert attempt: commit trước SMTP.
- SMTP call: ngoài DB transaction.
- Transaction persist outcome: commit sau SMTP.
- Nếu commit outcome lỗi: không tự động resend.
- Fencing token bảo vệ state writes từ stale workers.

### 20.3. Không retry chính thao tác gửi trong @Retryable một cách vô điều kiện

`@Retryable` hoặc `RetryTemplate` có thể hữu ích cho transient operation, nhưng nếu đặt trực tiếp quanh `JavaMailSender.send(...)` và bắt mọi `MailException`, nó có thể tự submit lại một message đang UNKNOWN.

Retry framework **không tự hiểu semantics SMTP acceptance**. Hãy chỉ retry khi classifier và state machine chứng minh đủ điều kiện.

## 21. Reconciliation là gì và bắt đầu từ đâu?

**Reconciliation** là quá trình đối chiếu attempt của ứng dụng với bằng chứng ở provider/SMTP relay để xác định liệu message đã accepted hay chưa.

Các nguồn có thể có:
- Provider dashboard hoặc submission logs.
- SMTP relay queue logs do tổ chức quản trị.
- Provider API tra cứu message/submission.
- Webhooks/event stream.
- Message ID/queue ID/correlation key được provider hỗ trợ.
- Nhật ký từ một gateway trung gian do tổ chức kiểm soát.
- Thông tin xác thực từ downstream nếu phù hợp và có quyền sử dụng.

Không phải SMTP provider nào cũng cung cấp đủ thông tin để kết luận, đặc biệt với generic SMTP.

### 21.1. Cần correlation key có thể dùng được

Mỗi attempt nên có:
- messageKey/attemptId ở ứng dụng;
- provider route;
- thời gian kết nối/submission;
- envelope sender/recipient reference phù hợp;
- optional provider queue ID;
- optional opaque custom header;
- SMTP transcript metadata đã redacted nếu có.

Không ghi mật khẩu, token hoặc toàn bộ email content vào log chỉ để phục vụ tìm kiếm.

### 21.2. Đối soát thành công theo ba hướng

**A. Xác nhận accepted:**
- Lưu `SMTP_ACCEPTED`.
- Dừng retry submission.
- Tiếp tục theo dõi delivery nếu provider hỗ trợ.

**B. Xác nhận không accepted:**
- Chuyển sang trạng thái retryable/permanent theo bằng chứng.
- Áp dụng retry budget, deadline và route policy.
- Không tự động retry nếu recipient/consent đã thay đổi.

**C. Không thể kết luận:**
- Giữ `UNKNOWN/UNRESOLVED`.
- Chuyển manual review hoặc policy riêng.
- Không nói “failed” một cách chắc chắn.

### 21.3. Không lấy “không thấy trong dashboard” làm chắc chắn chưa gửi

Provider logs/API có thể:
- có độ trễ indexing;
- không giữ lâu;
- thiếu quyền truy vấn;
- bị lọc sai thời gian/recipient;
- không ghi nhận đầy đủ một số SMTP paths.

**Absence of evidence không tự là evidence of absence.** Chỉ kết luận chưa accepted nếu công cụ/provider có contract đủ mạnh cho sự phủ định đó.

## 22. Tín hiệu từ delivery webhook có giúp không?

Có, nhưng cần biết phạm vi.

Một webhook `delivered` liên kết chắc tới attempt là bằng chứng mạnh rằng provider đã tiếp nhận và xử lý message. Nhưng **không nhận được webhook** không chứng minh provider chưa accepted.

Các rủi ro:
- webhook đến trễ;
- webhook bị mất;
- provider retry callback;
- event bị duplicate hoặc out-of-order;
- message mapping sai;
- provider ID khác RFC Message-ID;
- thiếu verified signature;
- data retention ngắn.

### 22.1. Webhook phải được xác thực

- Xác minh chữ ký theo provider specification.
- Bảo vệ endpoint khỏi replay.
- Dedupe event IDs.
- Map event về đúng tenant/provider/attempt.
- Không cho event của provider A ghi đè attempt provider B.
- Lưu event history theo retention policy.

### 22.2. Delivered không nhất thiết nghĩa là vào Inbox

Một số providers định nghĩa delivered là “recipient server accepted”. Điều này không chứng minh thư nằm trong Inbox thay vì Spam hoặc đã được người dùng đọc.

## 23. Khi provider không có API đối soát

Generic SMTP đôi khi không cung cấp khả năng query một submission đã biến mất khỏi ứng dụng.

Khi không thể kết luận:
1. Ghi `UNKNOWN`.
2. Kiểm tra deadline/loại email.
3. Đánh giá rủi ro **không gửi** so với **gửi trùng**.
4. Xác định ai có quyền ra quyết định resend.
5. Nếu policy cho resend, ghi rõ đó là **resend với duplicate risk được chấp nhận**, không gọi “safe retry”.
6. Thể hiện message key/attempt history và lý do trong audit.
7. Tránh tạo hàng loạt duplicates khi có outage diện rộng.

### 23.1. Email có mức rủi ro khác nhau

| Loại email | Rủi ro bỏ sót | Rủi ro duplicate | Hướng policy có thể |
|---|---|---|---|
| Hóa đơn/biên nhận | Cao | Cao về trải nghiệm/truy nguyên | Reconcile/manual review, có thể gửi bản thay thế rõ ràng |
| Reset password/OTP | Có deadline | Duplicate link/token gây nhầm | Không resend token cũ vô điều kiện |
| Marketing/newsletter | Thường chấp nhận chậm/bỏ kỳ | Spam complaint/reputation | Ưu tiên tránh duplicate |
| Cảnh báo khẩn cấp | Cao | Có thể chấp nhận một số lặp | Escalation qua kênh khác, policy được duyệt |
| Báo cáo định kỳ | Phụ thuộc thời điểm | Trùng báo cáo gây nhiễu | Hạn chế retry sau deadline |
| Notification nội bộ | Phụ thuộc nghiệp vụ | Có thể ít nghiêm trọng hơn | Thiết lập rõ ngưỡng chấp nhận |

Đây là ví dụ về khung quyết định, không phải quy tắc tuyệt đối. Hệ thống phải có owner nghiệp vụ/pháp lý bảo đảm chính sách phù hợp.

### 23.2. Một thông báo “thay thế” có thể tốt hơn retry giả định

Khi không thể xác minh việc gửi biên nhận ban đầu, ứng dụng có thể cung cấp cho người dùng một cách xem hóa đơn trong account và gửi một thông báo mới có nội dung minh bạch theo yêu cầu, thay vì âm thầm resend cùng payload. Phải tuân theo policy, không tiết lộ dữ liệu thanh toán qua một kênh không an toàn.

## 24. Sử dụng HTTP email API có idempotency có thay thế SMTP không?

Một số nhà cung cấp có **HTTP API** cho gửi email với một `idempotency key` hoặc request reference. Trong trường hợp provider thực sự có contract deduplication, retry API có thể an toàn hơn generic SMTP ở một số dạng timeout.

Nhưng phải kiểm tra:
- Key được scope theo account/endpoint hay toàn hệ thống?
- Thời hạn deduplication là bao lâu?
- Payload khác nhưng cùng key sẽ bị từ chối hay được coi như cùng request?
- Retry API trả lại kết quả cũ hay tạo submission mới?
- Key có được giữ khi request đã accepted nhưng response mất?
- Webhook/status lookup có map theo key đó không?
- Cơ chế áp dụng cho **HTTP API**, không phải SMTP login với cùng provider?

Không tự kết luận rằng provider hỗ trợ idempotency qua **SMTP** chỉ vì provider HTTP API có tính năng đó.

### 24.1. Thiết kế port chung, adapter khác nhau

```text
OutboundMailPort
    |
    +--> SMTP JavaMailSender adapter
    |       generic SMTP: no standard idempotency
    |
    +--> HTTP Email API adapter
            idempotency only when vendor contract supports it
```

Domain service có thể dùng chung message key, nhưng adapter phải thể hiện capability thật. Đừng che UNKNOWN chỉ để mọi providers trả cùng một boolean.

### 24.2. HTTP API vẫn cần quan sát kết quả

Nếu provider API trả 202 Accepted, đó là acceptance của API request, không tự chứng minh mailbox đã nhận. Delivery events và suppression vẫn phải theo dõi riêng.

## 25. Retry budget, backoff và rate limit

Khi đã **chứng minh chưa accepted** và lỗi transient, retry vẫn phải có giới hạn.

Ví dụ policy:
- Tối đa 4 attempts.
- Exponential backoff với jitter.
- Tôn trọng `Retry-After` hoặc provider throttle guidance nếu có.
- Dừng khi email hết hạn.
- Giới hạn concurrent submissions.
- Không vượt quota account/provider.
- Không thử lại lỗi permanent mà không có thay đổi dữ liệu/cấu hình.

### 25.1. Ví dụ tính backoff

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryBackoff {

    public static Duration delayFor(int attemptNumber) {
        if (attemptNumber < 1) {
            throw new IllegalArgumentException(
                "attemptNumber must be positive"
            );
        }

        int exponent = Math.min(attemptNumber - 1, 5);
        long maxSeconds = Math.min(60L * (1L << exponent), 1800L);

        long delay = ThreadLocalRandom.current()
            .nextLong(1L, maxSeconds + 1L);

        return Duration.ofSeconds(delay);
    }
}
```

Đây là một biến thể jitter minh họa, không phải công thức bắt buộc. Backoff **chỉ áp dụng cho attempt được phép retry**, không biến UNKNOWN thành retryable.

### 25.2. Circuit breaker không thay trạng thái email

Nếu SMTP provider outage, circuit breaker có thể ngăn các submission mới và giúp bảo vệ hệ thống. Nhưng circuit breaker **không thể kết luận** những attempts đang UNKNOWN trước khi circuit mở đã được accepted hay chưa.

### 25.3. Quota theo provider

Nếu có nhiều providers:
- quota có thể khác;
- credential/verified From khác;
- failover phải được phê duyệt;
- provider B không được dùng để né suppression hoặc auth failure của A;
- một timeout của A sau DATA không an toàn để thử qua B ngay.

## 26. Queue và broker redelivery có thể tạo duplicate tương tự

Không chỉ vòng lặp retry mới gây lỗi. Một hệ thống có thể dùng:
- RabbitMQ.
- Kafka.
- Spring Integration `QueueChannel`.
- JMS.
- Database scheduled jobs.

Ví dụ:

```text
Broker delivers mail job
       |
       v
Consumer calls JavaMailSender
       |
       v
SMTP accepts message
       |
       v
Consumer crashes before broker ACK
       |
       v
Broker redelivers same job
       |
       v
Consumer calls JavaMailSender again
       |
       v
DUPLICATE
```

### 26.1. Broker at-least-once không có nghĩa SMTP exactly-once

Broker có thể bảo đảm message sẽ được giao lại khi consumer chưa ack, nhưng không thể rollback side effect ở SMTP relay. Đó là vấn đề dual-write giống database.

### 26.2. Commit offset sau SMTP không tự giải quyết

Với Kafka, nếu consumer gửi SMTP rồi commit offset lỗi, record có thể được đọc lại. Kafka exactly-once processing cho nội bộ Kafka transactions không mặc định làm SMTP transport idempotent.

### 26.3. ACK trước SMTP cũng không an toàn

Nếu ACK job trước khi gửi, worker crash có thể làm **mất email**. Do đó, không có vị trí ACK đơn giản nào cùng lúc đảm bảo no-loss và no-duplicate qua SMTP bất kỳ.

### 26.4. Cần durable attempt state và recovery

Consumer nên:
1. Nạp email logic/outbox state.
2. Không tự gửi nếu đã accepted/unknown.
3. Claim bằng transaction/lock phù hợp.
4. Tạo attempt record.
5. Gọi SMTP.
6. Persist outcome.
7. ACK broker theo quy trình có idempotency/recovery.

Trên redelivery, message key giúp tra cứu state, nhưng phải hiểu rằng database có thể chưa ghi receipt dù provider đã accepted; do đó còn cần reconciliation.

## 27. Multi-recipient và partial success

Email có nhiều recipients là một trường hợp riêng:

```text
MAIL FROM:<sender>
RCPT TO:<alice@example.net> -> 250
RCPT TO:<bob@example.net>   -> 550
RCPT TO:<carol@example.net> -> 250
DATA -> ...
```

Tùy SMTP provider và Jakarta Mail configuration, message có thể được submit cho một tập recipients, còn một số recipients bị từ chối. Một `MailSendException` hoặc `SendFailedException` có thể đại diện cho tình huống không thuần túy “cả email không được gửi”.

### 27.1. Không resend nguyên danh sách recipients

Nếu Alice và Carol đã nằm trong một successful submission nhưng Bob bị từ chối, resend nguyên danh sách có thể làm Alice/Carol nhận thêm bản khác.

### 27.2. Theo dõi recipient outcome khi cần

Với email nghiệp vụ cần xử lý từng người nhận, một lựa chọn là **một email logic riêng cho từng recipient**, giúp:
- retry độc lập;
- suppression độc lập;
- tránh lộ danh sách người nhận;
- tracking riêng;
- giảm partial recipient ambiguity.

Nếu batch/multi-recipient là requirement, cần lưu accepted/refused recipients và kiểm tra thư viện có thể report partial sends ở mức nào. Chỉ retry các recipient **đã được xác minh là chưa accepted**, không đoán từ exception ngoài cùng.

### 27.3. sendPartial là behavior cần hiểu rõ

Một số SMTP provider Jakarta Mail có cấu hình liên quan việc gửi tới các recipient hợp lệ ngay cả khi một số recipient bị từ chối (ví dụ `mail.smtp.sendpartial`). Không bật hoặc tắt bừa bãi mà chưa thiết kế cách ghi kết quả theo recipient.

### 27.4. Gửi mảng MimeMessage cũng có partial outcome

`JavaMailSender.send(MimeMessage...)` có thể thực hiện nhiều submissions. Nếu lỗi giữa batch, không mặc định toàn bộ batch chưa được relay accepted. Attempt tracking ở mức từng message là an toàn hơn cho retry.

## 28. SMTP provider đã accepted nhưng delivery bị chậm

Một tình huống dễ bị nhầm:

```text
09:00 JavaMailSender.send returns success
09:00 Provider status: accepted/queued
09:05 Provider attempts delivery; receiver temp rejects
09:20 Provider retries delivery
09:21 Provider reports delivered
```

Nếu ứng dụng có watchdog:
> “Không thấy delivered trong 10 phút, retry submission.”

Nó có thể gửi trùng vì provider đang tự retry delivery. Delivery SLA phải được điều phối khác:
- theo dõi deferred;
- alert nếu quá ngưỡng;
- không tạo submission mới mặc định;
- xét provider-specific cancellation/retry policy;
- có thể liên hệ người nhận qua kênh khác khi nghiệp vụ cho phép.

**Timeout của application SMTP submission** và **thời gian delivery của provider** là hai biến độc lập.

## 29. Token, hóa đơn và thời hạn khi quyết định resend

Có những email không còn giá trị sau một thời điểm:
- OTP.
- Password reset.
- Verification link.
- Event reminder.
- Promotion hết hạn.
- Temporary approval request.

Nếu attempt UNKNOWN, retry sau một giờ có thể gửi một nội dung đã lỗi thời, ngay cả khi duplicate không xảy ra.

### 29.1. Ba mốc cần lưu

- `sendAt`: thời điểm sớm nhất được submit.
- `nextAttemptAt`: thời điểm retry có thể được xem xét.
- `expiresAt`: hạn cuối còn được phép gửi theo nghiệp vụ.

### 29.2. OTP/reset token không nên được tái sử dụng mù quáng

Nếu token đã hết hạn, không nên retry bản email cũ như thể token vẫn hợp lệ. Có thể yêu cầu người dùng thực hiện lại flow xác minh và tạo một yêu cầu mới với key khác, theo chính sách bảo mật.

### 29.3. Hoàn tất nghiệp vụ không phụ thuộc email

Payment/order status cần dựa trên transaction trong hệ thống thanh toán/đơn hàng, không dựa vào việc client nhận email hay không. Email là notification, không phải nguồn sự thật về giao dịch.

### 29.4. Duplicate action links phải được xử lý

Ngay cả khi email bị gửi hai lần, hệ thống nên bảo vệ business actions khỏi chạy hai lần: unique transaction IDs, one-time tokens, idempotent command handlers và validation. Đây là defense-in-depth, không phải lý do cho phép spam email duplicate.

## 30. Quan sát vận hành: tách attempts, accepted và unknown

Những metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| `mail_submit_attempts_total{provider,outcome}` | Số attempts theo kết quả |
| `mail_submit_unknown_total{provider}` | Số lần chưa biết accepted hay không |
| `mail_submit_accepted_total{provider}` | Submission được quan sát accepted |
| `mail_submit_proven_rejected_total{provider,category}` | Lỗi có bằng chứng chưa accepted |
| `mail_outbox_unknown_count` | Số jobs đang chờ reconciliation |
| `mail_outbox_stale_sending_count` | Jobs hết lease cần kiểm tra |
| `mail_reconciliation_duration_seconds` | Thời gian tìm kết quả |
| `mail_reconciliation_resolved_total{result}` | Bao nhiêu UNKNOWN đã giải quyết |
| `mail_duplicate_suspected_total` | Trường hợp nghi duplicate |
| `mail_provider_deferred_total{provider}` | Delivery deferred nếu có event |
| `mail_outbox_oldest_due_age_seconds` | Backlog chậm |
| `mail_retry_attempts_total{reason}` | Số lần retry đã được policy cho phép |

Không dùng recipient, messageKey hoặc attemptId làm Prometheus labels vì cardinality cao và rủi ro riêng tư.

### 30.1. Structured log cho mỗi attempt

```json
{
  "event": "mail.submit.attempt",
  "messageKey": "msg-1001",
  "attemptId": "att-2",
  "providerKey": "transactional",
  "outcome": "UNKNOWN",
  "reasonCode": "RESPONSE_NOT_OBSERVED_AFTER_DATA",
  "smtpPhase": "WAITING_FINAL_DATA_REPLY",
  "durationMs": 10015,
  "retryAutomatically": false
}
```

**Chỉ ghi `smtpPhase` cụ thể khi thật sự quan sát được** qua gateway/transport instrumentation. Nếu dùng `JavaMailSender` thông thường mà không biết phase, ghi `UNDETERMINED`; đừng bịa bằng chứng.

### 30.2. Trace bảo mật

Có thể gắn opaque correlation key vào MIME headers theo policy, nhưng:
- người nhận có thể xem;
- provider có thể thay/bỏ header;
- nó không có tính chất security credential;
- không chứa tenant secret, payment token hoặc dữ liệu nhạy cảm.

### 30.3. Alert nên hành động được

- UNKNOWN tăng sau deploy/JDK/provider change.
- SMTP read timeouts tăng ở một profile.
- Retry count tăng bất thường sau kết nối mất.
- Có jobs `UNKNOWN` bị claim lại (vi phạm state machine).
- SMTP provider accepted events xuất hiện nhiều lần cho cùng message key.
- Reconciliation không hoạt động hoặc provider logs mất trước khi đối soát.
- Stale sending attempts tăng và worker leases không renew.

## 31. Runbook khi xảy ra timeout hàng loạt

### Bước 1 — Khoanh vùng

Xác định:
- Provider/profile nào bị ảnh hưởng.
- Khoảng thời gian lỗi.
- Có phải TCP connect fail, TLS fail, AUTH fail hay read timeout sau DATA.
- Số attempts có nguy cơ accepted.
- Job categories và deadlines.
- Có thay đổi về deployment, network, quota hoặc certificates không.

### Bước 2 — Ngăn automatic resend nguy hiểm

- Tạm pause route hoặc mở circuit breaker nếu cần.
- Bảo vệ các job UNKNOWN khỏi retry worker.
- Không chỉnh toàn bộ status thành PENDING.
- Giữ attempts history và event logs.
- Đảm bảo in-flight jobs có cơ chế drain/record outcome.

### Bước 3 — Tập hợp bằng chứng

- App attempt IDs.
- SMTP provider account/route.
- Thời điểm start/end.
- Safe exception class/code.
- SMTP phase nếu được ghi tin cậy.
- Provider queue/submission IDs.
- Webhooks đã xác thực.
- Relay logs nếu thuộc quyền quản trị.

Không trích xuất plaintext credentials hoặc raw body vào incident ticket.

### Bước 4 — Đối soát từng nhóm

| Nhóm | Hành động |
|---|---|
| Chắc accepted | Mark SMTP_ACCEPTED, không resend |
| Chắc non-accepted, transient | Backoff/retry trong policy |
| Chắc permanent reject | Dead letter hoặc sửa input/config |
| Chưa rõ | UNKNOWN + review/policy |
| Đã expired/cancelled | Không submit |
| Provider accepted nhưng deferred | Theo dõi delivery, không resend application |

### Bước 5 — Khôi phục có kiểm soát

Khi sửa lỗi mạng/timeout:
- test connect/TLS/AUTH tới đúng endpoint;
- smoke test với mailbox được phép;
- giới hạn concurrency/quota khi resume;
- không gửi lại hàng loạt UNKNOWN;
- đo delivery/bounce và số duplicate nghi ngờ.

### Bước 6 — Postmortem

Ghi rõ:
- Vì sao timeout xuất hiện?
- Lỗi nằm ở phase nào?
- Có bao nhiêu accepted được chứng minh?
- Có bao nhiêu UNKNOWN còn lại?
- Có quyết định resend với duplicate risk không?
- Bằng chứng từ provider/log được lưu đủ không?
- Cần thay đổi timeout, retry classifier, outbox hay monitoring?

## 32. Unit test: exception không tự làm job thành RETRY_WAIT

Ví dụ test orchestration:

```java
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class UnknownSubmissionPolicyTest {

    @Test
    void unknownOutcomeMustNotRetryAutomatically() {
        OutboxRepository repository =
            mock(OutboxRepository.class);
        SmtpGateway gateway =
            mock(SmtpGateway.class);

        MailWorker worker =
            new MailWorker(repository, gateway);

        MailJob job = TestJobs.pending("msg-1001");

        when(repository.claimOne()).thenReturn(job);

        doThrow(new SubmissionOutcomeUnknown(
            "msg-1001",
            "att-1",
            new java.net.SocketTimeoutException(
                "No SMTP final response"
            )
        )).when(gateway).send(job);

        worker.processOne();

        verify(repository).markUnknown(
            eq("msg-1001"), anyString()
        );

        verify(repository, never()).scheduleRetry(
            eq("msg-1001"), any()
        );

        verify(gateway, times(1)).send(job);
    }
}
```

`OutboxRepository`, `SmtpGateway`, `MailWorker` và `TestJobs` là các loại trong ứng dụng/test fixture, không phải Spring classes có sẵn. Mục đích là khẳng định **một exception không làm phát sinh attempt thứ hai** nếu outcome chưa rõ.

### 32.1. Test classifier theo evidence

Một bộ unit tests nên bao gồm:
- Validation fail trước send → permanent.
- DNS/connect failure được xác minh trước SMTP → non-accepted.
- AUTH rejected trước DATA → non-accepted, cần sửa config.
- Timeout không biết phase → UNKNOWN.
- Timeout chờ final DATA reply → UNKNOWN.
- Final 250 có bằng chứng → accepted.
- Final 4xx/5xx được nhận rõ → rejected theo SMTP semantics.
- Provider delivery deferred → không submit lại.
- Receipt DB persist fail → stale/UNKNOWN recovery, không auto retry.

### 32.2. Không test bằng exception message substring duy nhất

Một test như:

```java
if (ex.getMessage().contains("timeout")) {
    retry();
}
```

là không đủ. Cùng chuỗi có thể xuất hiện ở nhiều phase. Tests nên dựa trên structured evidence/state, không phụ thuộc wording của provider/JDK version.

## 33. Integration test quan trọng nhất: accepted nhưng client không thấy 250

Đây là test giúp phát hiện đúng lỗi “retry mù sau timeout”.

### 33.1. Fault-injecting SMTP server

Thiết kế một SMTP test server có thể:

1. Chấp nhận TCP/TLS/AUTH trong test.
2. Nhận `MAIL FROM` và `RCPT TO`.
3. Trả `354` cho `DATA`.
4. Đọc toàn bộ message đến end-of-DATA.
5. Lưu message vào test mailbox/queue.
6. **Không trả final 250 cho client**, hoặc làm rơi kết nối đúng lúc.
7. Khi client báo timeout, test kiểm tra server đã lưu một bản.

```text
JUnit worker                    Fake SMTP relay
      |                               |
      |--- DATA content -------------->|
      |--- end-of-DATA --------------->|
      |                                | stores message #1
      |<--- final 250 deliberately lost|
      |                                |
      | timeout                       |
      |                                |
      v                                v
outbox = UNKNOWN               accepted count = 1
      |
      v
next polling cycle
      |
      v
must NOT send again           accepted count remains 1
```

### 33.2. Assertions cốt lõi

- Worker ghi `UNKNOWN`.
- Không tạo second automatic attempt.
- Outbox không chuyển thẳng `RETRY_WAIT`.
- SMTP test server có đúng một message accepted từ lần thử đầu.
- Khi job/worker restart, vẫn không gửi lại.
- Khi xuất hiện provider evidence, reconcile sang `SMTP_ACCEPTED`.
- Retry worker query không bao gồm `UNKNOWN`.
- Logs không chứa credential/email body.

### 33.3. GreenMail/Mailpit có thể chưa đủ

Một SMTP sandbox thông thường rất tốt cho happy path/MIME tests, nhưng không phải tất cả có tùy chọn **cố tình mất final DATA reply sau khi đã lưu message**. Để mô phỏng đúng nguy cơ, có thể cần một fake SMTP server/fault-injecting proxy chuyên biệt.

Không gây lỗi như vậy trên SMTP provider production hoặc gửi thử tới mailbox khách hàng thật.

### 33.4. Test được gì và chưa được gì?

Test này chứng minh **hệ thống của bạn không tự retry UNKNOWN** trong kịch bản được mô phỏng. Nó không chứng minh provider thật có cùng behavior ở mọi lỗi, cũng không tạo exactly-once SMTP guarantee.

## 34. Integration test: DB commit failure sau acceptance

Một trường hợp còn khó hơn:

```text
Worker receives final SMTP 250
       |
       v
Provider accepted
       |
       v
DB update outcome fails
       |
       v
Worker crashes
       |
       v
Stale SENDING record remains
```

Test:

1. Persist outbox job `PENDING`.
2. Claim và tạo attempt.
3. Fake SMTP gateway trả accepted.
4. Giả lập database không persist được `SMTP_ACCEPTED`.
5. Restart worker trên cùng DB.
6. Recovery phát hiện stale `SENDING`.
7. Assert **không auto resend**.
8. Đưa sang reconciliation/UNKNOWN.
9. Nếu provider evidence xác nhận accepted, mark accepted.
10. Nếu không có evidence, giữ unresolved và theo policy.

### 34.1. Không tự tin chỉ vì có lease

Nếu worker mất lease, một process khác có thể nhận job. Nhưng lease/heartbeat là cơ chế phân quyền worker, không phải xác nhận external side effect chưa xảy ra.

### 34.2. Test fencing

Một worker cũ cố ghi kết quả với lease token hết hạn phải không ghi đè outcome của worker mới. Điều này bảo vệ database state; vẫn phải quản lý SMTP side effects riêng.

## 35. Integration test: nhiều recipients và nhiều messages

Cần thêm các case:

- Alice accepted, Bob rejected, Carol accepted.
- One message accepted rồi batch throw exception ở message tiếp theo.
- Retry policy không gửi lại Alice/Carol.
- Một recipient bị suppress vẫn không được resend qua provider khác.
- Một message có cùng RFC Message-ID được submit hai lần và test server có thể lưu hai bản.
- Một broker redelivery không bypass outbox state.
- Khi worker được pause, các attempts đã in-flight được drain theo policy.
- Khi provider reports deferred, application không tạo attempt mới.

Nếu sản phẩm gửi một email riêng cho từng recipient, test idempotency theo `(messageKey,recipientId)` thay vì batch result chung.

## 36. Bảo mật và quyền riêng tư khi đối soát

Lỗi timeout không phải lý do để nới lỏng bảo mật.

### 36.1. Giữ TLS và hostname verification

Nếu timeout sau STARTTLS hoặc TLS handshake fail, xử lý endpoint/network/certificate đúng cách. Không tắt:
- `starttls.required` khi policy yêu cầu;
- `mail.smtp.ssl.checkserveridentity`;
- kiểm tra CA chain.

Dùng `mail.smtp.ssl.trust=*` trong production có thể che lỗi certificate và tăng rủi ro MITM.

### 36.2. Không log raw SMTP AUTH

Một raw protocol trace có thể chứa email addresses, message bodies hoặc authentication metadata. Chỉ bật chẩn đoán có kiểm soát, redact dữ liệu và giới hạn access.

### 36.3. Reconciliation dashboard cần phân quyền

Operator tra cứu UNKNOWN có thể nhìn thấy:
- recipient;
- subject;
- business reference;
- provider;
- correlation IDs.

Phải áp dụng tenant isolation, audit access và retention. Không cho operator tenant A xem attempts của tenant B.

### 36.4. Không sử dụng resend để né suppression

Nếu recipient đã hard bounce, spam complaint hoặc unsubscribe, application không được gửi qua provider B để “chữa” việc provider A chưa giao. Consent/suppression policy phải được kiểm tra tại thời điểm gửi.

## 37. Sai lầm thiết kế thường gặp

### “Có timeout là chưa gửi”

Sai. Nếu timeout sau end-of-DATA, server có thể đã accepted. Phải có trạng thái UNKNOWN.

### “Có MailSendException là toàn bộ email thất bại”

Sai. Với nhiều messages/recipients, có thể có partial success hoặc server-side acceptance không quan sát được. Cần tracking theo message/recipient nếu use case yêu cầu.

### “Catch exception rồi thử lại ba lần trong cùng thread”

Dễ tạo duplicate, retry storm và mất attempt history. Cần classify outcome và durable retry policy.

### “Thêm @Retryable là giải quyết”

Không. Retry framework không biết SMTP server đã chấp nhận DATA chưa. Chỉ dùng retry cho trường hợp đã được chứng minh an toàn.

### “Giữ nguyên Message-ID thì provider sẽ dedupe”

Không có guarantee đó trong generic SMTP.

### “Broker chỉ giao một lần”

Nếu consumer crash trước ack/offset commit, broker có thể redeliver. Dù không redeliver, timeout ứng dụng vẫn có thể không rõ outcome.

### “Đã có transactional outbox là exactly-once”

Outbox giải quyết no-loss và một số duplicate ở tầng business, không tự biến SMTP thành transactional participant.

### “Lease hết hạn nghĩa là worker chưa gửi”

Không. Worker có thể đã được relay accepted trước khi ngừng heartbeat.

### “Provider chưa báo delivered thì gửi lại”

Không. Provider có thể đang tự retry delivery sau accepted; application resubmission tạo bản thứ hai.

### “Không tìm thấy message trên dashboard là chưa accepted”

Không chắc. Dashboard/API có thể trễ hoặc thiếu dữ liệu. Chỉ coi là proof khi provider contract hỗ trợ kết luận đó.

### “Sau sự cố cứ reset tất cả về PENDING”

Đây là cách dễ tạo duplicate hàng loạt nhất. Phải tách accepted, proven rejected, unknown, expired và cancelled.

### “Tăng timeout vô hạn sẽ hết ambiguity”

Không. Timeout dài giảm một số lỗi nhưng process/network/DB vẫn có thể fail. Cần state machine và reconciliation.

## 38. Checklist trước khi đưa retry SMTP vào production

### 38.1. Business và danh tính email

- [ ] Có messageKey cho email logic.
- [ ] Có unique business event/idempotency key.
- [ ] Mỗi attempt có attemptId riêng.
- [ ] Phân biệt sender, recipient và provider IDs.
- [ ] Có expiration và consent/suppression checks.
- [ ] Không dựa vào RFC Message-ID như dedupe guarantee.

### 38.2. SMTP outcome

- [ ] Phân biệt accepted, proven non-accepted và unknown.
- [ ] Không suy luận non-accepted từ MailException chung.
- [ ] Timeout chờ final DATA reply được coi UNKNOWN.
- [ ] SMTP final 250 có ý nghĩa riêng so với EHLO/RCPT 250.
- [ ] Provider deferred không kích hoạt application submission retry.
- [ ] Partial recipients/messages được theo dõi đúng mức cần thiết.

### 38.3. Persistence và recovery

- [ ] Transactional outbox có trạng thái bền vững.
- [ ] Attempt history lưu route/time/outcome.
- [ ] Claim atomic, có lease/fencing khi cần.
- [ ] SMTP send nằm ngoài DB transaction.
- [ ] Stale SENDING không tự đổi PENDING.
- [ ] UNKNOWN không nằm trong auto-retry query.
- [ ] Có reconciliation queue/manual review policy.
- [ ] DB commit failure sau SMTP accepted đã được test.

### 38.4. Retry

- [ ] Chỉ retry khi có bằng chứng an toàn.
- [ ] Backoff + jitter + max attempts.
- [ ] Có provider quotas/concurrency limits.
- [ ] Không retry lỗi permanent liên tục.
- [ ] Không bypass suppression, tenant isolation hoặc From verification.
- [ ] Có policy cho UNKNOWN unresolved theo loại email.
- [ ] Không gửi token/email đã hết hạn.

### 38.5. Tests và observability

- [ ] Fake SMTP test chấp nhận DATA nhưng làm mất final reply.
- [ ] Test không có second submission tự động.
- [ ] Test restart từ stale SENDING.
- [ ] Test partial recipients/batch outcomes.
- [ ] Test broker redelivery.
- [ ] Test provider accepted rồi delivery deferred.
- [ ] Có metric UNKNOWN/accepted/reconciled.
- [ ] Logs redacted, không lưu raw credential/body.

## 39. Bài tập thực hành

### Bài 1 — Vẽ giai đoạn SMTP

Vẽ chuỗi TCP/TLS/AUTH/MAIL FROM/RCPT TO/DATA/250. Chỉ ra chính xác reply nào xác nhận message đã accepted.

### Bài 2 — Timeout sau DATA

Một fake SMTP relay đã lưu message và làm rơi final 250. Client nhận read timeout. Hãy xác định trạng thái đúng của attempt và giải thích tại sao không retry ngay.

### Bài 3 — Connect timeout

Client chưa thiết lập TCP connection; không có SMTP command nào được gửi. Phân tích điều kiện nào cho phép retry sau backoff và điều kiện nào buộc chờ sửa config.

### Bài 4 — Exception classifier

Thiết kế classifier chỉ trả `PROVEN_NOT_ACCEPTED` khi có evidence rõ. Những exception không biết phase phải trả `UNKNOWN`.

### Bài 5 — Thay vòng lặp retry

Refactor code `catch(MailException){ sendAgain(); }` thành một workflow ghi outbox, attempt, outcome và next action.

### Bài 6 — Database schema

Tạo `email_outbox` và `email_submit_attempt`. Thêm unique business key, lease token, status và index cho jobs đến hạn.

### Bài 7 — Atomic claim

Dùng PostgreSQL `FOR UPDATE SKIP LOCKED` để hai workers không claim cùng job. Test hai transactions đồng thời.

### Bài 8 — Crash sau accepted

Fake gateway trả SMTP accepted nhưng repository update outcome lỗi. Restart worker và assert không tự resend stale SENDING.

### Bài 9 — Message-ID không dedupe

Gửi hai test emails cùng RFC Message-ID tới SMTP sandbox và kiểm tra vì sao không được khẳng định chỉ có một bản được nhận.

### Bài 10 — Broker redelivery

Broker phát lại message sau consumer crash trước ACK. Dùng message key để tra cứu outbox và ngăn resend các trạng thái accepted/unknown.

### Bài 11 — Provider reconciliation

Mô phỏng ba kết quả lookup: accepted, proven rejected, no reliable record. Viết transitions và giải thích tại sao “không thấy record” chưa đủ để retry.

### Bài 12 — Delivery deferred

Provider đã accepted và sau 10 phút báo deferred. Đảm bảo application không tạo attempt mới và chỉ cập nhật delivery tracking.

### Bài 13 — Partial recipients

Một SMTP submission có ba recipients, một người bị 550 còn hai người accepted. Thiết kế tracking và retry để không gửi trùng hai người đã accepted.

### Bài 14 — Batch send

`JavaMailSender.send(MimeMessage...)` submit được hai messages rồi lỗi ở message thứ ba. Thiết kế lưu outcomes/attempts riêng.

### Bài 15 — Timeout và worker lease

SMTP read timeout 30 giây nhưng lease 10 giây. Phân tích nguy cơ stale worker và đề xuất lease/heartbeat/fencing policy.

### Bài 16 — Retry deadline

Một email xác minh sẽ hết hạn sau 15 phút. Attempt UNKNOWN và quá hạn. Thiết kế chính sách không resend token cũ.

### Bài 17 — Multi-provider failover

Provider A timeout sau end-of-DATA, B vẫn hoạt động. Chứng minh vì sao không thể lập tức chuyển sang B, ngay cả khi From domain đã verified.

### Bài 18 — HTTP API idempotency

Chọn một provider HTTP API có contract idempotency rõ. Mô tả phạm vi/time-to-live của key và khác biệt với SMTP Message-ID.

### Bài 19 — Incident runbook

Có 5.000 emails bị timeout trong 10 phút. Phân nhóm attempts theo evidence, pause route, reconcile, resume và giám sát duplicate.

### Bài 20 — Monitoring

Tạo dashboard gồm SMTP accepted, UNKNOWN, stale leases, reconciliation lag, retry rate và delivery deferred. Đặt cảnh báo khi số UNKNOWN tăng đột ngột.

## 40. Tổng kết

**Gửi lại sau timeout mà không xét khả năng server đã nhận** là một lỗi nghiêm trọng trong Spring Framework Mail vì SMTP là giao thức có side effect qua mạng, trong khi client có thể mất phản hồi xác nhận.

Những nguyên tắc quan trọng nhất:

1. **Không thấy kết quả thành công không đồng nghĩa server chưa accepted.** Relay có thể đã nhận toàn bộ DATA và trả 250 nhưng client bị timeout.
2. **Phải xem phase và bằng chứng**, không chỉ xem loại exception. `MailException` hoặc `SocketTimeoutException` không tự chứng minh một attempt an toàn để retry.
3. **Phân loại rõ `SMTP_ACCEPTED`, `PROVEN_NOT_ACCEPTED` và `UNKNOWN`.** Những gì chưa xác định phải được biểu diễn trung thực.
4. **Không retry UNKNOWN tự động** nếu chưa có policy chấp nhận rủi ro duplicate hoặc bằng chứng reconciliation phù hợp.
5. **SMTP accepted không phải delivered.** Provider có thể tiếp tục retry delivery; application không nên gửi lại chỉ vì mail deferred.
6. **Business idempotency, Message-ID và transactional outbox không tự tạo exactly-once SMTP.** Chúng bảo vệ các lớp khác của workflow.
7. **Outbox và attempt history** giúp lưu tình trạng qua crash/restart, truy nguyên provider và đối soát.
8. **Lease/fencing chỉ bảo vệ quyền xử lý và DB state**, không thu hồi được email đã accepted ở relay.
9. **Không giữ DB transaction qua SMTP call.** Nếu DB persist outcome thất bại sau accepted, recovery phải coi attempt là potentially unknown.
10. **Partial recipients và batch sends** cần kết quả theo người nhận/message để không resend những phần đã accepted.
11. **Retry an toàn cần bằng chứng, backoff, deadline, quota và consent policy**, không phải vòng lặp gửi lại vô điều kiện.
12. **Kiểm thử fault injection sau end-of-DATA** là cách trực tiếp nhất để phát hiện cơ chế retry tạo duplicate trong một tình huống timeout thực tế.

Khi xây dựng được ranh giới giữa **điều đã được xác nhận**, **điều bị từ chối rõ ràng** và **điều chưa biết**, ứng dụng Spring Mail có thể phục hồi sau lỗi mạng mà không đánh đổi sự tin cậy bằng hàng loạt email trùng lặp.
