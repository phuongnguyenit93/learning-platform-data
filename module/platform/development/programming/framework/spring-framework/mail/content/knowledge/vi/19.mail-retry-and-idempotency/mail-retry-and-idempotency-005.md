# Retry ở client, queue worker hoặc nhà cung cấp

Trong ứng dụng Spring Framework Mail, email có thể được gửi trực tiếp từ một request, qua hàng đợi công việc, hoặc thông qua dịch vụ email bên ngoài. Ở mỗi tầng đều có khả năng xuất hiện lỗi tạm thời: HTTP request timeout, worker bị restart, SMTP server trả mã 4xx, provider áp dụng rate limit hoặc mail server của người nhận tạm thời không nhận thư.

Một phản xạ dễ gặp là “lỗi thì retry”. Nhưng nếu **client, queue worker và nhà cung cấp cùng retry mà không phân định trách nhiệm**, một thông báo nghiệp vụ có thể tạo thành nhiều email giống nhau. Ngược lại, nếu ứng dụng ngừng ngay sau mọi exception, email quan trọng có thể bị mất dù lỗi chỉ kéo dài vài giây.

Bài học này giải thích **retry ở client, queue worker hoặc nhà cung cấp** trong ngữ cảnh Spring Mail; cách phân biệt một yêu cầu gửi với một lần thử gửi và với quá trình giao thư của SMTP provider; cách dùng idempotency key, transactional outbox, backoff, trạng thái `UNKNOWN` và webhook để tăng độ tin cậy mà không gây gửi trùng không kiểm soát.

## 1. Trước tiên, phân biệt ba tầng retry

Giả sử người dùng nhấn “Gửi hóa đơn” trong một ứng dụng web:

```text
Trình duyệt / HTTP client
        |
        | POST /orders/123/send-receipt
        v
Backend Spring Boot
        |
        | Ghi email_outbox
        v
Database / queue
        |
        | Worker claim job
        v
Spring Mail / JavaMailSender
        |
        | SMTP submission
        v
SMTP relay / Email provider
        |
        | Delivery retry nếu server đích tạm hoãn
        v
Mail server người nhận
        |
        v
Inbox / spam / quarantine
```

Ở đây có **ba nơi khác nhau có thể retry**:

| Tầng | Thao tác đang thử lại | Ai điều khiển? | Mục tiêu |
|---|---|---|---|
| **Client** | Gọi lại HTTP API yêu cầu gửi | Trình duyệt, mobile app, service gọi API | Bảo đảm yêu cầu nghiệp vụ được ghi nhận. |
| **Queue worker** | Thử gửi một job đã được ghi nhận | Ứng dụng và queue/outbox worker | Bảo đảm job được xử lý và gửi tới SMTP/provider. |
| **Nhà cung cấp** | Thử giao tiếp email đã được tiếp nhận đến server đích | SMTP relay/MTA/email provider | Khắc phục lỗi tạm thời trong quá trình delivery. |

Cùng một chữ “retry” nhưng **không cùng đối tượng**:

- Client retry **yêu cầu tạo việc gửi**.
- Worker retry **một attempt gửi** thuộc yêu cầu đã tồn tại.
- Provider retry **việc chuyển giao** của message mà provider đã tiếp nhận.

**Nguyên tắc:** xác định tầng nào đã nhận trách nhiệm trước khi quyết định có cần một lượt retry mới ở tầng trước hay không.

## 2. Ba kết quả quan trọng: chưa tạo, đã nhận để xử lý, đã được SMTP tiếp nhận

Cần tách rõ các mốc:

1. **Yêu cầu nghiệp vụ đã được lưu:** API tạo bản ghi outbox thành công.
2. **Submission đã được SMTP/provider chấp nhận:** hệ thống gửi nhận phản hồi chấp nhận từ upstream.
3. **Delivery đã được xác nhận theo provider:** provider hoặc MTA có tín hiệu rằng mail server đích đã nhận thư.

Ba mốc này không đồng nghĩa.

```text
POST /send-receipt
   |
   | 202 Accepted: outbox saved
   v
Email worker
   |
   | SMTP 250 / successful submission
   v
Provider accepted
   |
   | Provider retries delivery if needed
   v
Destination mail server
   |
   | Delivery event, if provider supports
   v
Application receives event
```

HTTP `202 Accepted` có thể chỉ có nghĩa API đã lưu job để xử lý, không có nghĩa SMTP đã gửi. Một lời gọi `JavaMailSender.send(...)` thành công thường cho biết SMTP submission đã hoàn tất mà không phát sinh lỗi đồng bộ; nó **không chứng minh email đã đến Inbox hoặc được đọc**.

Việc chọn retry phải dựa vào **mốc nào đã chắc chắn hoàn tất** và **mốc nào chưa rõ kết quả**.

## 3. Tạo một email logic, nhiều attempt nhưng không tạo nhiều job trùng

Một cách mô hình hóa:

- `businessEventId`: sự kiện nghiệp vụ, chẳng hạn đơn hàng đã thanh toán.
- `messageKey`: một email logic cần gửi do sự kiện đó.
- `attemptId`: một lượt worker gọi SMTP/provider.
- `providerMessageId`: ID do provider trả/cung cấp nếu có.
- `deliveryEventId`: ID của một webhook event.

Ví dụ:

```text
business_event = order-123-paid
  |
  +-- message_key = msg-a817
        |
        +-- attempt_id = att-1 -> temporary SMTP failure
        +-- attempt_id = att-2 -> SMTP_ACCEPTED
                                |
                                +-- provider delivery attempt #1 -> deferred
                                +-- provider delivery attempt #2 -> delivered
```

Client nhấn gửi lại cùng yêu cầu vì mạng chập chờn **không nên tự động tạo thêm message key**. Worker thử gửi lại sau lỗi tạm thời **giữ message key và tạo attempt ID mới**. Provider thử giao lại sau khi đã nhận email **không cần backend tạo thêm một email khác**.

Một yêu cầu gửi lại mới do người dùng chủ động thực hiện ở thời điểm khác có thể tạo message key mới theo quy tắc nghiệp vụ. Cần định nghĩa rõ “retry cũ” khác “gửi mới”.

## 4. Retry ở client: HTTP timeout không có nghĩa server chưa làm gì

Giả sử mobile app gửi:

```http
POST /api/orders/123/send-receipt HTTP/1.1
Content-Type: application/json

{"language":"vi","destination":"verified-primary"}
```

Server có thể đã commit outbox và trả `202`, nhưng response bị mất trên mạng. Client chỉ thấy timeout.

Nếu client gửi lại request, server có thể tạo hai outbox row và gửi hai thư nếu không có cơ chế deduplication.

### 4.1. Dùng Idempotency-Key cho API tạo yêu cầu gửi

Client tạo một key ổn định cho **một hành động** rồi gửi kèm:

```http
POST /api/orders/123/send-receipt HTTP/1.1
Idempotency-Key: 79dd3864-6018-4d85-8e65-1f865c7d42d3
Content-Type: application/json

{"language":"vi","destination":"verified-primary"}
```

Nếu request timeout, client retry với **cùng key và cùng dữ liệu**, không tạo key mới.

Backend xử lý:
- Lần đầu: tạo một outbox row, trả message key.
- Lần lặp: trả lại kết quả của yêu cầu cũ, không tạo job mới.
- Cùng key nhưng payload khác: từ chối, thường bằng lỗi conflict, thay vì âm thầm dùng job cũ hoặc tạo job thứ hai.

Ví dụ response của API:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "messageKey": "msg-a817",
  "status": "QUEUED"
}
```

Response này nói yêu cầu đã được chấp nhận để xử lý, **chưa phải email đã giao thành công**.

### 4.2. Scope của idempotency key

Không đặt unique constraint toàn hệ thống chỉ theo một chuỗi do client gửi mà không có ngữ cảnh. Một cách thiết kế là duy nhất theo:

```text
tenant_id + actor_id + operation + idempotency_key
```

Ví dụ `operation=send-order-receipt`. Nếu actor khác hoặc API khác dùng cùng key, chúng không nên vô tình nhận kết quả của người khác.

Lưu thêm **request fingerprint** từ những trường có ý nghĩa nghiệp vụ (đã canonicalize) để phát hiện cùng key nhưng dữ liệu không tương đương. Không lưu token nhạy cảm hoặc toàn bộ body tùy ý nếu không cần.

Key do client tạo không phải một cơ chế authorization. Backend vẫn phải xác thực người gọi có quyền yêu cầu gửi email của đơn hàng đó tới đúng người nhận.

### 4.3. Unique constraint phải bảo vệ khỏi request đồng thời

Mẫu “SELECT trước, nếu chưa có thì INSERT” chưa đủ khi hai request tới cùng lúc; cả hai có thể cùng thấy chưa có bản ghi.

Cần unique constraint và thao tác insert có kiểm soát tranh chấp:

```sql
CREATE TABLE email_request_dedupe (
    tenant_id         VARCHAR(64) NOT NULL,
    actor_id          VARCHAR(64) NOT NULL,
    operation         VARCHAR(80) NOT NULL,
    idempotency_key   VARCHAR(120) NOT NULL,
    request_hash      VARCHAR(64) NOT NULL,
    message_key       VARCHAR(64) NOT NULL,
    created_at        TIMESTAMP NOT NULL,
    PRIMARY KEY (
        tenant_id, actor_id, operation, idempotency_key
    )
);
```

Trong transaction, insert bản ghi dedupe cùng outbox; khi gặp xung đột, truy xuất bản ghi cũ và so sánh fingerprint. Cần xử lý unique violation hoặc dùng cú pháp upsert của database thích hợp, không chỉ dựa vào kiểm tra ở application layer.

### 4.4. Khi nào client nên retry?

| Kết quả HTTP | Hành vi gợi ý |
|---|---|
| `202` hoặc response thành công có message key | Không tạo yêu cầu mới; theo dõi trạng thái nếu cần. |
| Timeout/network drop trước khi biết response | Có thể retry **cùng Idempotency-Key**, giới hạn số lần. |
| `429 Too Many Requests` | Tôn trọng `Retry-After` nếu có và quota của dịch vụ. |
| `503 Service Unavailable` | Retry có backoff nếu API hỗ trợ idempotency. |
| `400` do request không hợp lệ | Sửa request; không lặp vô hạn. |
| `401/403` | Xử lý xác thực/quyền; không coi là sự cố SMTP tạm thời. |
| `409` do key cũ đi với payload khác | Không retry y nguyên; cần sửa luồng client. |

HTTP retry nên có giới hạn, backoff/jitter và không biến thao tác “Gửi” thành một vòng lặp không giới hạn. Chống double-click ở UI có ích cho trải nghiệm nhưng **không thay thế idempotency ở server**.

## 5. Retry ở queue worker: chỉ gửi lại job đã tồn tại

Sau khi outbox được commit, một worker có thể nhận trách nhiệm gửi. Lỗi có thể xảy ra trong quá trình render, tạo MIME, kết nối SMTP hoặc lưu kết quả gửi.

Ví dụ vòng đời:

```text
PENDING
   |
   v
LEASED / SENDING
   |
   +--> SMTP_ACCEPTED
   |
   +--> RETRY_WAIT ----> LEASED / SENDING
   |
   +--> FAILED_PERMANENT
   |
   +--> UNKNOWN ----> reconciliation / manual decision
```

Các trạng thái chỉ mang tính minh họa, nhưng cần phân biệt:
- chưa xử lý;
- đang được worker sở hữu;
- được phép thử lại;
- lỗi chắc chắn không thể giải quyết bằng retry nguyên yêu cầu;
- kết quả chưa xác định;
- SMTP đã chấp nhận.

### 5.1. Outbox transaction

Với email quan trọng, nên ghi business event và outbox row trong cùng transaction:

```text
BEGIN
  update order status = PAID
  insert email_outbox(
      message_key,
      business_event_key,
      template,
      status = PENDING
  )
COMMIT
```

Nhờ đó, ứng dụng không gặp cảnh đơn hàng đã thanh toán nhưng tiến trình chết trước khi ghi nhu cầu gửi email.

Một constraint nghiệp vụ như `(business_event_key, template, recipient_role)` có thể giúp không tạo hai email logic cho cùng event, song điều kiện duy nhất thực tế cần phụ thuộc bài toán gửi lại có chủ đích của sản phẩm.

### 5.2. Claim job có khóa hoặc lease

Hai worker không được đồng thời lấy cùng job rồi gửi hai lần. Với PostgreSQL, một chiến lược là `FOR UPDATE SKIP LOCKED` trong transaction ngắn:

```sql
WITH next_job AS (
    SELECT message_key
    FROM email_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND next_attempt_at <= CURRENT_TIMESTAMP
    ORDER BY next_attempt_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE email_outbox e
SET status = 'LEASED',
    lease_token = :newLeaseToken,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    updated_at = CURRENT_TIMESTAMP
FROM next_job n
WHERE e.message_key = n.message_key
RETURNING e.*;
```

Worker commit transaction claim trước khi gọi SMTP; không nên giữ database transaction mở trong suốt thời gian network I/O. Với hệ thống queue có visibility timeout, áp dụng cơ chế claim/ack tương ứng của queue.

Lease token đóng vai trò như fencing marker: khi worker ghi kết quả, dùng compare-and-set theo token để ngăn worker cũ cập nhật một job mà worker mới đã claim:

```sql
UPDATE email_outbox
SET status = :newStatus,
    lease_token = NULL,
    lease_until = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE message_key = :messageKey
  AND lease_token = :leaseToken
  AND status = 'LEASED';
```

Nếu số dòng cập nhật bằng 0, worker phải xử lý khả năng quyền sở hữu đã hết hạn. Fencing giúp bảo vệ **trạng thái database**, nhưng không thể thu hồi một email đã được SMTP nhận. Nếu lease hết hạn trong lúc network call vẫn chạy, worker mới có thể gửi trùng; do đó cần timeout, lease đủ phù hợp, heartbeat/renewal khi cần và xử lý `UNKNOWN`.

### 5.3. Acknowledge queue đúng thời điểm

Với queue ngoài database, cần tránh:
- Ack trước khi outbox/result được lưu bền vững rồi process crash: mất job.
- Không ack dù đã xác định kết quả và không có chiến lược dedupe: job bị giao lại.
- Requeue không giới hạn dù lỗi là dữ liệu/template sai.

Một nguyên tắc là **ack sau khi đã ghi bền vững quyết định xử lý**: thành công, lịch retry, lỗi vĩnh viễn hoặc trạng thái không rõ để reconciliation. Cơ chế thực thi phụ thuộc broker; outbox/database vẫn nên lưu state đáng tin cậy.

### 5.4. Không retry cùng đối tượng MimeMessage mãi

Mỗi attempt nên tạo `MimeMessage`/`MimeMessageHelper` mới, rồi render nội dung từ dữ liệu hoặc bản snapshot đã được kiểm soát. Không chia sẻ các đối tượng mutable này giữa worker thread.

Nếu nội dung được dựng lại khi retry, cân nhắc:
- Cần giữ đúng số tiền/ngày giờ ở thời điểm sự kiện hay dùng giá trị mới nhất?
- Link có token có còn hiệu lực không?
- Template version có thay đổi giữa hai attempt không?
- Attachment có còn đúng nội dung đã được phê duyệt không?

Với email mang ý nghĩa pháp lý/tài chính, thường cần lưu reference/version hoặc snapshot an toàn để retry không làm thay đổi nội dung nghiệp vụ ngoài ý muốn.

## 6. Retry ở tầng SMTP submission: hiểu lỗi trước khi thử lại

Khi dùng Spring Mail, điểm gửi thường là:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo(recipient);
helper.setSubject(subject);
helper.setText(plainText, htmlText);

mailSender.send(message);
```

`send(...)` có thể ném `MailException`, trong khi các thao tác tạo `MimeMessage` có thể ném `MessagingException`. Không nên retry mọi exception theo một quy tắc chung.

### 6.1. SMTP 4xx và 5xx

SMTP response thường chia làm hai lớp:

| Phản hồi | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| `421` | Dịch vụ SMTP không khả dụng, đóng kết nối | Có thể retry sau backoff nếu biết message chưa được chấp nhận. |
| `450` | Mailbox tạm thời không khả dụng | Retry có kiểm soát ở tầng phù hợp. |
| `451` | Lỗi tạm thời ở server | Retry có backoff. |
| `452` | Thiếu tài nguyên tạm thời | Retry sau khoảng chờ; không retry dồn dập. |
| `550` | Mailbox/recipient bị từ chối vĩnh viễn trong ngữ cảnh thường gặp | Không gửi lại nguyên request vô hạn; xem nguyên nhân. |
| `552` | Vượt giới hạn lưu trữ/kích thước theo phản hồi server | Cần xem mã mở rộng và mô tả; thường phải thay đổi nội dung/chính sách. |
| `554` | Giao dịch bị từ chối | Thường không có ích khi lặp nguyên yêu cầu; cần chẩn đoán. |

Đây là định hướng, **không đủ để tự động quyết định mọi trường hợp**. Cần xem SMTP command thất bại (`MAIL FROM`, `RCPT TO`, `DATA`, sau DATA), enhanced status code như `4.x.x`/`5.x.x`, thông điệp từ relay và chính sách provider. Một mã `4xx` báo lỗi tạm thời, nhưng không có nghĩa retry ngay là thích hợp; một lỗi quota có thể cần chờ lâu hơn.

### 6.2. Lỗi của Spring Mail

Một số exception liên quan:

| Exception | Tình huống | Có tự động retry không? |
|---|---|---|
| `MailAuthenticationException` | Xác thực SMTP thất bại | Thường cần sửa credential/config; tránh retry dồn dập. |
| `MailPreparationException` | Lỗi khi chuẩn bị message | Thường phải sửa dữ liệu/template/attachment. |
| `MailParseException` | Không parse/chuẩn bị email đúng | Không retry nguyên input cho đến khi sửa lỗi. |
| `MailSendException` | Một hoặc nhiều message không gửi được | Cần xét nguyên nhân, message và trạng thái các recipient. |
| `MailException` khác | Lỗi ở tầng mail abstraction | Phân loại theo nguyên nhân cụ thể; không assume transient. |

Không chỉ dựa vào tên exception để kết luận rằng SMTP chắc chắn chưa nhận thư. Ví dụ lỗi kết nối hoặc timeout **sau khi server nhận DATA** có thể khiến ứng dụng không biết server đã chấp nhận message hay chưa.

### 6.3. Timeout và trạng thái UNKNOWN

Giả sử:

```text
Worker                     SMTP relay
  |---- DATA + content -------->|
  |---- end-of-DATA ----------->|
  |                              | accept and enqueue
  |<--- connection lost ---------X
  |
  +-- exception / timeout
```

Worker có thể nghĩ là lỗi; SMTP relay có thể đã nhận message. Nếu retry toàn bộ email ngay, người nhận có thể nhận hai bản.

Với trường hợp không xác định chắc chắn:
1. Lưu `attemptId` và `messageKey`.
2. Ghi `UNKNOWN` thay vì tuyên bố chắc chắn `FAILED`.
3. Tra cứu provider/SMTP log nếu có khả năng.
4. Đợi event hoặc thực hiện reconciliation theo giới hạn thời gian.
5. Chỉ retry khi chính sách chấp nhận rủi ro duplicate hoặc đã xác minh chưa tiếp nhận.

Không có cách tổng quát nào để đạt exactly-once chỉ bằng `JavaMailSender` và generic SMTP. Application key hay custom MIME header không làm SMTP tự động deduplicate.

### 6.4. Nhiều người nhận và partial success

Một email có nhiều địa chỉ `To`/`Cc`/`Bcc` có thể tạo trạng thái phức tạp:
- một số recipient được chấp nhận;
- recipient khác bị từ chối;
- provider thực hiện partial send tùy cấu hình;
- exception không nhất thiết có nghĩa mọi người nhận đều chưa nhận thư.

Nếu gửi hàng loạt, cân nhắc **một email logic cho mỗi recipient** hoặc tối thiểu lưu kết quả theo recipient. Đừng retry nguyên danh sách mù quáng sau một partial failure vì có thể gửi lại cho những người đã được chấp nhận.

Nếu dùng `MailSendException`, có thể kiểm tra failed messages/exceptions được Spring cung cấp khi phù hợp; thông tin về successful recipients còn phụ thuộc Jakarta Mail/provider và policy sendpartial. Cần kiểm thử với relay thực tế.

## 7. Retry ở nhà cung cấp: submission khác với delivery

Khi SMTP relay hoặc email provider đã phản hồi chấp nhận submission, nó thường giữ trách nhiệm chuyển tiếp email. Nếu mail server đích trả lỗi tạm thời, MTA/provider có thể tự đưa message trở lại hàng đợi để thử giao sau.

```text
Application --SMTP accepted--> Provider queue
                                 |
                                 +--> delivery attempt #1: 451
                                 |
                                 +--> wait according to provider policy
                                 |
                                 +--> delivery attempt #2: accepted
                                 |
                                 +--> delivered event (if supported)
```

Trong lúc này, backend **không nên tạo một email submission mới chỉ vì provider ghi nhận deferred**. Provider đã có message và đang retry delivery theo chính sách của họ. Resubmit thêm có thể gây gửi trùng nếu cả hai bản cùng được giao sau đó.

Các trạng thái phổ biến:
- `processed/accepted`: provider đã nhận để xử lý;
- `deferred`: tạm hoãn, thường còn trong hàng đợi;
- `delivered`: giao thành công theo định nghĩa provider;
- `bounced`: không giao được, thường là kết quả cuối của một tuyến giao;
- `dropped/suppressed`: provider không gửi do policy/suppression;
- `complaint`: tín hiệu phản hồi spam nếu provider hỗ trợ.

Tên chính xác và ý nghĩa event khác nhau giữa các provider. Generic SMTP không bảo đảm có webhook và không tự cung cấp API đọc trạng thái delivery.

### 7.1. Khi provider báo deferred

Hành vi nên làm:
- Ghi lại event liên kết với provider message ID và application message key.
- Hiển thị trạng thái đúng (“đang giao” hoặc “tạm hoãn”), không gọi là chưa gửi.
- Tôn trọng thời gian retry/thời hạn giữ queue của provider.
- Chờ event tiếp theo hoặc tra cứu dashboard/API nếu cần.
- Chỉ cân nhắc resubmit khi provider xác nhận message đã thất bại/đã bị loại, và chính sách nghiệp vụ cho phép.

### 7.2. Khi provider báo bounced

Phân loại theo kết quả:
- Hard bounce/địa chỉ không tồn tại: thường không nên gửi lại tự động.
- Soft bounce hoặc lỗi tạm thời đã hết thời gian provider retry: có thể cần quyết định nghiệp vụ, nhưng không tự loop vô hạn.
- Chính sách reputation/suppression: sửa vấn đề gốc; gửi lặp có thể làm xấu reputation.
- Mailbox đầy: phụ thuộc chính sách, có thể có chiến lược liên hệ khác.

Nhiều provider tự quản lý suppression list. Ứng dụng phải tránh tự động gửi lại tới recipient đã bị suppress hoặc có complaint.

### 7.3. Khi dùng HTTP Email API thay SMTP

Nếu gửi qua API của provider (không dùng trực tiếp `JavaMailSender`), provider có thể hỗ trợ:
- Idempotency key theo API;
- mã phản hồi `429` và header `Retry-After`;
- provider request/message ID;
- metadata/custom arguments gắn message key.

Đó là khả năng **riêng của API/provider**, không mặc nhiên có ở SMTP. Cần đọc contract của provider và chỉ dựa vào cơ chế thực sự được hỗ trợ. Retry HTTP submission vẫn phải phân biệt timeout không rõ kết quả và lỗi chắc chắn chưa được provider nhận.

## 8. Ai nên là chủ sở hữu retry?

Một lỗi thiết kế là xếp nhiều vòng retry chồng nhau:

```text
HTTP client retries 3 times
  × Service-level retry 3 times
  × Worker retries 5 times
  × SMTP library retries 2 times
  = potential 90 submissions
```

Phép nhân chỉ minh họa rủi ro khi mọi tầng có thể tạo lại thao tác gửi; thực tế phụ thuộc idempotency và chính sách của mỗi tầng.

Thay vào đó, phân trách nhiệm:

| Tầng | Quyền retry | Điểm dừng / bàn giao |
|---|---|---|
| Client | Retry request đến API với cùng idempotency key | Khi API xác nhận đã ghi nhận job hoặc lỗi không thể retry. |
| API service | Commit outbox/idempotency; không tự gửi và retry vô hạn trong HTTP request | Sau khi job được lưu bền vững. |
| Queue worker | Retry SMTP submission nếu quyết định an toàn và trong ngân sách | Khi SMTP accepted, thất bại vĩnh viễn hoặc UNKNOWN cần reconciliation. |
| SMTP provider | Retry delivery sau khi đã accepted | Theo queue lifetime/policy provider. |
| Application delivery-event handler | Cập nhật trạng thái và quyết định nghiệp vụ kế tiếp | Không tự resubmit deferred message một cách mù quáng. |

**Chỉ một tầng nên chủ động retry cùng một thao tác side effect tại một thời điểm.** Các tầng khác có thể retry việc xác nhận trạng thái, nhưng không mặc nhiên lặp lại gửi.

## 9. Backoff, jitter và ngân sách retry

### 9.1. Exponential backoff

Thay vì retry mỗi 100 ms, dùng khoảng chờ tăng dần, ví dụ:

```text
attempt 1: gửi ngay
attempt 2: chờ khoảng 2 giây
attempt 3: chờ khoảng 4 giây
attempt 4: chờ khoảng 8 giây
attempt 5: chờ khoảng 16 giây
```

Con số chỉ minh họa. Cần cân đối thời gian giao dịch, hạn sử dụng link, giới hạn tài nguyên và policy provider.

Một công thức cơ bản:

```text
delay = min(maxDelay, baseDelay × 2^(attemptNumber - 1))
```

Nếu tất cả worker cùng retry ở đúng các mốc, chúng có thể tạo **thundering herd**. Thêm jitter để phân tán:

```text
fullJitterDelay = random(0, cappedExponentialDelay)
```

### 9.2. Ví dụ tính thời điểm retry

```java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;

public class RetrySchedule {

    private static final long BASE_SECONDS = 2;
    private static final long MAX_SECONDS = 300;

    public Instant nextAttemptAt(int attemptNumber, Instant now) {
        if (attemptNumber < 1) {
            throw new IllegalArgumentException("attemptNumber >= 1");
        }

        int exponent = Math.min(attemptNumber - 1, 20);
        long cap = Math.min(
            MAX_SECONDS,
            BASE_SECONDS * (1L << exponent)
        );

        long delaySeconds =
            ThreadLocalRandom.current().nextLong(cap + 1);

        return now.plus(Duration.ofSeconds(delaySeconds));
    }
}
```

Đây là minh họa full jitter, không phải quy tắc mặc định của Spring Mail. Với production, có thể đặt **minimum delay** để tránh giá trị 0 khi provider đang rate limit. Nếu provider công bố `Retry-After` qua API, cần ưu tiên chính sách đó khi phù hợp.

### 9.3. Retry budget

Nên giới hạn theo nhiều chiều:
- tối đa số attempt cho một message key;
- tổng thời gian kể từ khi tạo outbox;
- deadline nghiệp vụ, ví dụ link xác minh sắp hết hạn;
- số lần retry đồng thời theo tenant/provider;
- số lượng job đang chờ và độ dài hàng đợi;
- quota/rate limit được provider công bố.

Ví dụ:
- Email xác minh phải có ý nghĩa trong 15 phút: không retry một ngày mà vẫn gửi link đã hết hạn.
- Email hóa đơn có thời hạn dài: có thể chờ lâu hơn, nhưng phải có đường xử lý khi hết ngân sách.
- Alert khẩn cấp có thể dùng kênh dự phòng thay vì tiếp tục retry SMTP hàng giờ.

Khi vượt retry budget, chuyển sang `DEAD_LETTER`/`FAILED_PERMANENT` hoặc workflow điều tra, không âm thầm bỏ mất job.

### 9.4. Circuit breaker và rate limiting

Nếu SMTP provider đang lỗi diện rộng, hàng nghìn worker retry đồng loạt sẽ tăng tải và có thể kích hoạt rate limit. Nên kết hợp:
- queue concurrency limit;
- rate limiter theo provider/account;
- circuit breaker khi upstream không khả dụng;
- exponential backoff có jitter;
- alert khi queue backlog hoặc retry rate tăng bất thường.

Circuit breaker không thay thế outbox; nó chỉ tạm ngăn các call có khả năng thất bại và giúp hệ thống phục hồi có kiểm soát.

## 10. Idempotency ở từng tầng

Idempotency nghĩa là lặp lại **cùng một yêu cầu logic** không tạo thêm tác động nghiệp vụ ngoài ý muốn trong phạm vi cơ chế bảo vệ đã thiết kế.

| Tầng | Cách thực hiện | Giới hạn |
|---|---|---|
| Client → API | `Idempotency-Key`, scope theo tenant/operation, fingerprint, unique constraint | Chỉ bảo vệ việc tạo job, không bảo đảm SMTP exactly-once. |
| Business → Outbox | Unique key theo business event + notification type | Phải định nghĩa khi nào được phép gửi lại có chủ đích. |
| Queue → Worker | Atomic claim, lease/fencing, lưu attempt, dedupe message key | Không loại trừ mọi duplicate sau timeout không rõ kết quả. |
| Worker → Provider API | Provider idempotency key nếu API hỗ trợ | Chỉ có hiệu lực theo contract/thời hạn provider. |
| SMTP submission | Không có idempotency chung cho custom header | Không thể giả định relay tự dedupe. |
| Provider webhook → DB | Unique provider event ID; xử lý state transition | Event có thể đến trễ, lặp hoặc sai thứ tự. |

### 10.1. Application message key không phải RFC Message-ID

`Message-ID` là header email chuẩn, thường do Jakarta Mail/provider tạo. Nó dùng cho message identity và threading. Application `messageKey` là mã nội bộ cho email logic qua các attempt. Một retry có thể tạo một MIME message mới với Message-ID khác nhưng **cùng message key**.

Có thể gắn key vào custom header:

```java
message.setHeader(
    "X-Application-Message-Key",
    messageKey
);

message.setHeader(
    "X-Mail-Attempt-ID",
    attemptId
);
```

Các header này hỗ trợ tracing, nhưng **không phải cơ chế chống gửi trùng của SMTP**. Người nhận có thể xem raw header nên không nhúng secret hoặc dữ liệu cá nhân.

### 10.2. Đừng dùng cùng idempotency key cho yêu cầu nghiệp vụ mới

Nếu người dùng chủ động gửi lại hóa đơn cho địa chỉ khác, đó có thể là email logic mới và phải có key mới. Nếu client chỉ retry request vì không nhận response, phải giữ key cũ.

Quy tắc này nên được mô tả trong API contract, không phụ thuộc việc người dùng nhấn nút cách nhau bao nhiêu giây.

## 11. Thiết kế cơ sở dữ liệu cho retry minh bạch

Một mô hình tham khảo:

```sql
CREATE TABLE email_outbox (
    message_key       VARCHAR(64) PRIMARY KEY,
    business_event_id VARCHAR(120) NOT NULL,
    template_name     VARCHAR(120) NOT NULL,
    recipient_ref     VARCHAR(120) NOT NULL,
    status            VARCHAR(32) NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMP NOT NULL,
    lease_token       VARCHAR(64),
    lease_until       TIMESTAMP,
    provider_id       VARCHAR(255),
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL
);

CREATE TABLE email_attempt (
    attempt_id        VARCHAR(64) PRIMARY KEY,
    message_key       VARCHAR(64) NOT NULL,
    attempt_number    INTEGER NOT NULL,
    started_at        TIMESTAMP NOT NULL,
    finished_at       TIMESTAMP,
    outcome           VARCHAR(32) NOT NULL,
    error_category    VARCHAR(64),
    rfc_message_id    VARCHAR(255),
    provider_id       VARCHAR(255),
    CONSTRAINT fk_email_attempt_outbox
        FOREIGN KEY (message_key)
        REFERENCES email_outbox(message_key),
    CONSTRAINT uq_email_attempt_number
        UNIQUE (message_key, attempt_number)
);
```

Có thể thêm bảng `email_delivery_event` với unique provider event ID để xử lý webhook.

Gợi ý ý nghĩa trạng thái outbox:
- `PENDING`: chờ gửi lần đầu.
- `LEASED`: worker đang sở hữu job.
- `RETRY_WAIT`: chờ thời điểm tiếp theo.
- `SMTP_ACCEPTED`: upstream đã nhận submission.
- `DELIVERED`: có event delivery tương ứng.
- `FAILED_PERMANENT`: cần sửa dữ liệu/chính sách hoặc đã hết ngân sách.
- `UNKNOWN`: không rõ upstream đã nhận hay chưa.
- `DEAD_LETTER`: đã chuyển sang xử lý riêng.

Chỉ dựa vào cột `status` tổng hợp có thể mất lịch sử quan trọng; bảng attempt lưu diễn biến từng lần thử giúp điều tra và đối soát.

## 12. Ví dụ Spring Boot: API ghi outbox, worker chịu trách nhiệm gửi

### 12.1. API không gửi SMTP trong HTTP request

Ví dụ minh họa:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderReceiptController {

    private final ReceiptRequestService receiptService;

    public OrderReceiptController(
            ReceiptRequestService receiptService) {
        this.receiptService = receiptService;
    }

    @PostMapping("/{orderId}/send-receipt")
    public ResponseEntity<ReceiptRequestResult> requestReceipt(
            @PathVariable String orderId,
            @RequestHeader("Idempotency-Key") String key,
            Principal principal) {

        ReceiptRequestResult result = receiptService.requestReceipt(
            principal.getName(),
            orderId,
            key
        );

        return ResponseEntity.accepted().body(result);
    }
}
```

`ReceiptRequestService` là service do ứng dụng định nghĩa, cần:
1. Xác thực actor có quyền gửi hóa đơn của order.
2. Validate định dạng và scope của Idempotency-Key.
3. Trong transaction, ghi bản ghi dedupe cùng outbox.
4. Trả lại cùng message key cho request trùng hợp lệ.
5. Từ chối cùng key nhưng thay đổi nội dung có ý nghĩa.
6. Không gọi `JavaMailSender` trực tiếp trong transaction nghiệp vụ.

Kết quả minh họa:

```java
public record ReceiptRequestResult(
    String messageKey,
    String status
) {}
```

HTTP `202` mang nghĩa đã nhận yêu cầu để xử lý; UI có thể hiển thị “Đã ghi nhận yêu cầu gửi” thay vì “Email đã tới hộp thư”.

### 12.2. Worker gửi và ghi attempt

Service có thể được gọi bởi scheduler hoặc queue consumer:

```java
@Service
public class MailSubmissionWorker {

    private final JavaMailSender mailSender;
    private final MailOutboxRepository repository;
    private final MailRetryPolicy retryPolicy;

    public MailSubmissionWorker(
            JavaMailSender mailSender,
            MailOutboxRepository repository,
            MailRetryPolicy retryPolicy) {
        this.mailSender = mailSender;
        this.repository = repository;
        this.retryPolicy = retryPolicy;
    }

    public void process(ClaimedMailJob job) {
        String attemptId = UUID.randomUUID().toString();

        repository.startAttempt(
            job.messageKey(),
            job.leaseToken(),
            attemptId
        );

        try {
            MimeMessage message =
                mailSender.createMimeMessage();

            MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom("no-reply@example.com");
            helper.setTo(job.recipient());
            helper.setSubject(job.subject());
            helper.setText(job.plainText(), job.htmlText());

            message.setHeader(
                "X-Application-Message-Key",
                job.messageKey()
            );
            message.setHeader(
                "X-Mail-Attempt-ID",
                attemptId
            );

            mailSender.send(message);

            repository.markAccepted(
                job.messageKey(),
                job.leaseToken(),
                attemptId,
                message.getMessageID()
            );

        } catch (MailException | MessagingException ex) {
            RetryDecision decision = retryPolicy.classify(
                ex,
                job.attemptNumber()
            );

            repository.recordOutcome(
                job.messageKey(),
                job.leaseToken(),
                attemptId,
                decision
            );
        }
    }
}
```

Đây là **skeleton minh họa**, không phải implementation đầy đủ:
- `ClaimedMailJob`, `MailOutboxRepository`, `MailRetryPolicy` và `RetryDecision` là các interface/model ứng dụng tự định nghĩa.
- Repository phải thực thi atomic claim/lease fencing trong transaction ngắn.
- `classify(...)` cần dựa trên nguyên nhân kỹ thuật thực tế, mã SMTP và khả năng kết quả `UNKNOWN`; không retry tất cả `MailException`.
- `markAccepted(...)` là mốc **SMTP submission accepted**, không phải recipient delivered.
- Nếu ghi kết quả vào DB thất bại sau khi gửi, job có thể cần reconciliation; không nên tự resend ngay.
- Lần xử lý sau phải tạo MIME message mới, nhưng giữ `messageKey`.
- Nội dung job cần được bảo vệ và ràng buộc với đúng recipient; không log nội dung, token hoặc attachment.

### 12.3. Không dùng @Retryable quanh mọi lệnh send một cách máy móc

Có thể dùng Spring Retry/Resilience4j cho các lời gọi mạng **an toàn để thử lại**, nhưng decorator quanh `mailSender.send(message)` có thể che khuất:
- attempt ID;
- kết quả SMTP không rõ;
- partial success;
- retry budget;
- các lần gửi trùng;
- trạng thái outbox được lưu sau từng attempt.

Nếu có retry ngay trong worker, cần quy tắc rõ ràng và tốt nhất ghi attempt/decision vào storage. Với email có side effect không thể đảo ngược, **retry bền vững qua outbox thường dễ kiểm soát hơn một vòng lặp retry trong request**.

## 13. Trường hợp provider đã nhận nhưng phía ứng dụng tưởng thất bại

Đây là ca quan trọng nhất cần thiết kế trước:

```text
T0: Worker bắt đầu attempt #1.
T1: Worker gửi hết dữ liệu email.
T2: SMTP relay ghi message vào queue.
T3: Đường truyền đứt trước khi worker thấy response.
T4: Worker thấy timeout.
T5: Job bị giao lại vì lease hết hạn.
T6: Worker attempt #2 gửi cùng nội dung.
T7: Người nhận có thể nhận hai thư.
```

Kết quả tại T4 phải được xem là **không xác định** trừ khi có bằng chứng chắc chắn provider chưa nhận message.

Một chiến lược thực tế:
1. Trước gửi, lưu message key và attempt ID.
2. Gắn custom headers hoặc provider metadata phù hợp.
3. Khi lỗi không rõ, lưu trạng thái `UNKNOWN`.
4. Reconcile qua provider ID, log SMTP hoặc webhook nếu có.
5. Nếu không có dữ liệu để xác minh, áp dụng chính sách chấp nhận rủi ro theo loại email.
6. Nếu buộc phải gửi lại, theo dõi cả hai attempt dưới cùng message key.

Các email rủi ro cao, như reset mật khẩu hoặc xác thực giao dịch, có thể yêu cầu thiết kế token/flow sao cho gửi trùng không tạo hành động nghiệp vụ không mong muốn. Một link xác minh chỉ có hiệu lực một lần và được kiểm tra server-side giúp giảm rủi ro nghiệp vụ, dù bản thân duplicate email vẫn là trải nghiệm không tốt.

## 14. Provider webhook, event trùng và event sai thứ tự

Sau khi SMTP accepted, provider có thể gửi webhook:

```text
accepted -> deferred -> delivered
```

Nhưng webhook có thể:
- được gửi lại cùng một event vì endpoint phản hồi timeout;
- đến trễ;
- đến sai thứ tự;
- thiếu metadata tùy provider;
- chứa dữ liệu recipient hoặc lý do bounce nhạy cảm.

Handler nên:
1. Xác minh chữ ký webhook hoặc cơ chế xác thực chính thức.
2. Deduplicate bằng provider event ID hoặc khóa ổn định do provider định nghĩa.
3. Map provider message ID/custom metadata về message key và attempt.
4. Lưu event history bất biến hoặc append-only.
5. Áp dụng state transition theo quy tắc, không để deferred đến trễ “lùi” trạng thái sau delivered.
6. Không dùng event `deferred` làm lý do gọi `JavaMailSender.send` thêm một lần.
7. Bảo vệ quyền truy cập vào log và payload webhook.

Ví dụ bảng:

```sql
CREATE TABLE email_delivery_event (
    provider          VARCHAR(80) NOT NULL,
    provider_event_id VARCHAR(255) NOT NULL,
    message_key       VARCHAR(64) NOT NULL,
    provider_id       VARCHAR(255),
    event_type        VARCHAR(50) NOT NULL,
    event_at          TIMESTAMP,
    received_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (provider, provider_event_id)
);
```

Nếu provider không cung cấp event ID ổn định, cần thiết kế dedupe theo tài liệu provider và tính chất payload; không tự giả định một timestamp là duy nhất.

## 15. Ma trận quyết định retry theo tình huống

| Tình huống | Client retry? | Worker retry? | Provider retry? | Lưu ý |
|---|---|---|---|---|
| Browser timeout khi POST tạo outbox | Có, cùng idempotency key | Theo job được tạo | Chưa liên quan | Không tạo hai job. |
| API trả 202 và message key | Không cần | Có thể thực hiện lần gửi đầu | Chưa liên quan | 202 không phải delivered. |
| Worker crash trước khi gọi SMTP | Không | Có, sau reclaim lease | Chưa liên quan | Đảm bảo không có submission đã xảy ra. |
| SMTP 451 trước khi nhận DATA | Không | Có, backoff | Chưa accepted | Lưu lỗi tạm thời, kiểm tra response thực tế. |
| SMTP AUTH sai credential | Không | Không retry dồn dập | Không | Cần sửa cấu hình/secret. |
| MIME build lỗi vì template thiếu biến | Không | Không retry nguyên input | Không | Sửa dữ liệu hoặc template. |
| SMTP timeout sau DATA, không rõ relay nhận chưa | Không | UNKNOWN, reconcile trước khi resubmit | Có thể đã tiếp nhận | Nguy cơ gửi trùng. |
| Provider đã accepted, delivery deferred | Không | Không gửi submission mới | Có, theo policy provider | Theo dõi delivery event. |
| Provider hard bounce | Không | Không retry nguyên email | Thường ngừng | Xử lý recipient/policy. |
| Webhook delivered đến hai lần | Không | Không | Không liên quan | Deduplicate event; không gửi mail mới. |
| Người dùng chủ động yêu cầu gửi lại hợp lệ | Yêu cầu mới với key mới theo policy | Gửi email logic mới | Theo provider | Phân biệt với retry cũ. |

Đây là ma trận định hướng; quyết định thực tế phụ thuộc loại email, SMTP/provider response, khả năng xác minh trạng thái và chính sách nghiệp vụ.

## 16. Quan sát vận hành: đếm đúng thứ cần đếm

Các metric hữu ích:
- số yêu cầu HTTP gửi email và số request trùng theo idempotency key;
- số outbox item `PENDING`, `RETRY_WAIT`, `UNKNOWN` và dead-letter;
- số attempt SMTP cho mỗi message key;
- độ trễ từ outbox created tới SMTP accepted;
- tỷ lệ SMTP 4xx/5xx và timeout;
- số lần lease hết hạn/reclaim job;
- provider deferred, delivered, bounced, complaint;
- tỷ lệ duplicate submission được phát hiện hoặc nghi ngờ;
- tuổi của job già nhất trong queue;
- số lượt retry theo provider/tenant.

Một structured log ví dụ:

```json
{
  "event": "email.send_attempt",
  "messageKey": "msg-a817",
  "attemptId": "att-2",
  "retryOwner": "outbox-worker",
  "attemptNumber": 2,
  "outcome": "SMTP_ACCEPTED",
  "smtpProvider": "relay-primary",
  "latencyMs": 781
}
```

Tránh log:
- body HTML/plain;
- email hoặc dữ liệu cá nhân không cần thiết;
- attachment bytes/Base64;
- URL có token;
- password/SMTP credential;
- toàn bộ exception nếu có thể chứa chi tiết nhạy cảm.

Hãy liên kết log qua message key, attempt ID và correlation ID. Nếu có Message-ID hoặc provider ID, lưu như metadata bổ sung. Người dùng không nên tự xem lịch sử email của người khác chỉ vì biết message key; endpoint tra cứu cần authorization.

### 16.1. Alert đáng quan tâm

- Queue backlog tăng liên tục.
- Job ở `RETRY_WAIT` quá lâu.
- Số `UNKNOWN` tăng đột biến.
- Provider liên tục trả rate limit hoặc lỗi kết nối.
- Bounce/complaint tăng bất thường.
- Worker bị reclaim lease nhiều lần.
- Có tín hiệu gửi trùng cùng business event/recipient.
- Gửi email xác minh sau khi token hết hạn.

Alert nên phân biệt sự cố submission với sự cố delivery; cách xử lý của hai loại khác nhau.

## 17. Những ngộ nhận thường gặp

### “Mọi 4xx đều retry ngay”

Không. 4xx là nhóm phản hồi tạm thời nhưng có thể liên quan rate limit, greylisting hoặc quá tải. Cần backoff theo policy và không dồn request.

### “Nếu send ném exception thì chắc chắn chưa gửi”

Không. Timeout sau DATA hoặc mất kết nối lúc relay đã nhận message có thể dẫn đến kết quả `UNKNOWN`.

### “Message key giống nhau thì SMTP tự bỏ bản trùng”

Không. Generic SMTP không cam kết dedupe theo custom header. Key giúp trace; cần cơ chế idempotency ở tầng hỗ trợ và xử lý kết quả không rõ.

### “Client retry và worker retry càng nhiều càng tin cậy”

Không. Retry chồng nhau có thể gây bão request, vượt quota và tạo duplicate. Cần một tầng sở hữu mỗi loại retry và ngân sách tổng.

### “Provider deferred nghĩa là backend phải gửi lại”

Không. Provider thường vẫn giữ message và tự retry delivery. Backend chỉ nên theo dõi trạng thái, không tự tạo submission mới.

### “SMTP accepted nghĩa là delivered”

Không. Submission accepted không có nghĩa mail server đích đã nhận, và delivered cũng không đảm bảo người dùng nhìn thấy Inbox hoặc đã mở thư.

### “Gắn @Retryable quanh JavaMailSender là đủ”

Không. Cần outbox, attempt history, status UNKNOWN, phân loại lỗi, backoff, timeout và kiểm soát trùng lặp.

### “Idempotency-Key là một dạng authorization”

Không. Key chỉ giúp nhận diện request lặp. Server vẫn phải xác thực actor, tenant, đối tượng nghiệp vụ và người nhận.

## 18. Bài tập thực hành

### Bài 1 — Client timeout

Một HTTP POST gửi hóa đơn đã commit outbox, nhưng response bị mất. Thiết kế `Idempotency-Key` và API response để request lặp trả cùng message key mà không tạo job mới.

### Bài 2 — Hai worker tranh chấp

Hai worker cùng đọc một job `PENDING`. Dùng atomic claim hoặc `FOR UPDATE SKIP LOCKED` để chỉ một worker có lease. Giải thích tại sao lease fencing chỉ bảo vệ DB state, không thể thu hồi SMTP submission đã xảy ra.

### Bài 3 — SMTP 451

SMTP relay trả `451` trước khi chấp nhận dữ liệu. Thiết kế `RETRY_WAIT`, exponential backoff có jitter, giới hạn số attempt và cách ghi error category.

### Bài 4 — Timeout sau DATA

Worker timeout sau khi gửi xong message. Hãy mô tả vì sao không được ghi `FAILED` chắc chắn và thiết kế reconciliation trước khi resubmit.

### Bài 5 — Provider deferred

Provider đã accepted rồi báo deferred do server đích greylisting. Hãy giải thích tầng nào đang retry và vì sao worker không nên gọi `send(...)` một lần nữa.

### Bài 6 — 429 ở Provider API

Khi dùng HTTP provider API, nhận `429` và `Retry-After`. Hãy thiết kế rate limit, delay và provider idempotency key nếu API hỗ trợ. Phân biệt cơ chế này với generic SMTP.

### Bài 7 — Retry budget

Đặt giới hạn tối đa 5 attempt và thời hạn 10 phút cho email xác minh. Hãy xác định cách xử lý khi job chờ quá thời hạn hoặc token đã hết hiệu lực.

### Bài 8 — Partial recipient success

Một thư có ba recipient, hai người được chấp nhận, một người bị từ chối. Hãy đề xuất mô hình theo dõi từng recipient hoặc chia thành một email logic cho mỗi recipient để tránh resend cho những người đã được chấp nhận.

### Bài 9 — Webhook đến trễ

Provider gửi `delivered` rồi một event `deferred` cũ đến muộn. Hãy lưu event history, deduplicate và cập nhật trạng thái theo state machine để không làm trạng thái tổng lùi lại.

### Bài 10 — Điều tra gửi trùng

Một khách hàng nhận hai email xác nhận. Dùng business event ID, message key, attempt ID, RFC Message-ID và provider message ID để xác định trùng do client tạo hai job, worker retry không rõ kết quả hay provider giao nhiều lần.

## 19. Tổng kết

**Retry ở client, queue worker hoặc nhà cung cấp** là ba cơ chế khác nhau, không thể thay thế cho nhau. Client retry yêu cầu API tạo job, worker retry SMTP/provider submission của job đã được ghi nhận, còn MTA/provider retry delivery sau khi đã tiếp nhận message.

Một thiết kế đáng tin cậy trong Spring Framework Mail nên:
1. Dùng **Idempotency-Key** cho request tạo email và unique constraint ở backend.
2. Ghi yêu cầu vào **transactional outbox**; không gửi trực tiếp như side effect khó kiểm soát trong transaction nghiệp vụ.
3. Cho worker **claim job độc quyền**, lưu attempt và dùng backoff/jitter với giới hạn rõ ràng.
4. Phân loại lỗi thành **retryable, permanent và UNKNOWN**, đặc biệt với timeout sau DATA.
5. Khi SMTP/provider đã accepted, **không resubmit chỉ vì provider đang deferred**; để provider retry delivery theo policy.
6. Ghép webhook/provider IDs vào message key, xử lý event trùng/sai thứ tự và bảo vệ thông tin nhạy cảm.

Idempotency giúp giảm việc tạo job/gửi trùng, nhưng **không biến SMTP thành exactly-once delivery**. Mục tiêu thực tế là phân quyền retry đúng tầng, ghi nhận trạng thái trung thực, giảm duplicate ngoài ý muốn và có đường reconciliation khi kết quả không rõ.
