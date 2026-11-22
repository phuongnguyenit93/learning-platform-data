# Message key để nhận diện cùng một yêu cầu gửi

Trong **Spring Framework Mail**, một ứng dụng có thể gửi email bằng `JavaMailSender` khi người dùng đăng ký, đặt hàng, thanh toán hoặc yêu cầu đặt lại mật khẩu. Trong hệ thống thật, một yêu cầu gửi không nhất thiết chỉ được xử lý một lần: client HTTP có thể gửi lại vì timeout, event có thể được phát lại, message broker có thể giao cùng job nhiều lần, hoặc worker có thể khởi động lại sau khi SMTP server đã nhận thư.

Nếu mỗi lần xử lý lại tạo một email mới, người nhận có thể thấy hai, ba hoặc nhiều thông báo giống nhau. Để nhận biết những lần gọi nào thuộc **cùng một yêu cầu gửi về mặt nghiệp vụ**, ứng dụng có thể gắn một **message key** ổn định cho yêu cầu đó.

Ví dụ, khi đơn hàng `A123` được xác nhận một lần:

~~~text
Sự kiện nghiệp vụ: ORDER_CONFIRMED
Đơn hàng:         A123
Phiên bản sự kiện: 1
Kênh:             EMAIL

Message key: order-confirmed:A123:v1:email
~~~

Nếu hệ thống nhận lại cùng sự kiện do retry, nó dùng **đúng message key cũ**, không tạo một key mới. Từ đó, kho lưu trữ có thể phát hiện yêu cầu đã được tiếp nhận và trả về cùng job thay vì tạo thêm một job gửi.

**Giới hạn cần hiểu ngay:** message key giúp nhận diện và chống tiếp nhận trùng yêu cầu ở tầng ứng dụng. Nó không tự buộc SMTP server hoặc hộp thư người nhận xử lý email theo nguyên tắc *exactly once*. Việc tránh gửi trùng phụ thuộc thêm vào lưu trữ bền vững, ràng buộc duy nhất, trạng thái job, retry, provider và cách xử lý kết quả không xác định.

## 1. Message key là gì?

**Message key** là một định danh được gắn với **một ý định gửi email cụ thể**, thường do application service hoặc thành phần tạo job xác định trước khi gửi.

Một key tốt trả lời câu hỏi:

> Hai lần xử lý này có đang cố thực hiện cùng một yêu cầu gửi mà nghiệp vụ đã tạo ra trước đó hay không?

Nếu câu trả lời là “cùng yêu cầu”, hai lần xử lý nên dùng cùng key. Nếu là một thông báo mới hợp lệ, cần dùng key mới.

Ví dụ:

| Tình huống | Message key | Hành vi mong muốn |
| --- | --- | --- |
| Client retry cùng request xác nhận đơn A123 | Giữ nguyên key của request đầu | Không tạo job mới |
| Broker giao lại event `OrderConfirmed(A123, v1)` | Giữ nguyên key | Worker nhận biết job cũ |
| Đơn A123 được xác nhận ở một lần chuyển trạng thái hợp lệ khác | Key mới có version/event ID khác | Tạo thông báo mới nếu nghiệp vụ cho phép |
| Gửi email nhắc thanh toán lần 1 và lần 2 | Hai key khác nhau | Cho phép hai lời nhắc khác nhau |
| Gửi cùng thông báo cho hai người nhận độc lập | Key khác theo recipient identity hoặc job identity | Không vô tình bỏ sót người nhận |
| Worker retry lần 3 sau SMTP timeout | Vẫn dùng key của job ban đầu | Theo dõi mọi attempt trên một yêu cầu |

Message key có thể là một chuỗi do ứng dụng tạo ra, một UUID ổn định được lưu cùng event, hoặc một token idempotency do client cung cấp rồi được server ràng buộc vào nghiệp vụ.

### 1.1. Phân biệt “cùng yêu cầu” với “nội dung giống nhau”

Hai email có nội dung giống nhau chưa chắc là một yêu cầu:

- Cùng nội dung nhắc thanh toán nhưng gửi theo hai kỳ nhắc khác nhau là **hai thông báo hợp lệ**.
- Cùng nội dung xác nhận đơn hàng nhưng do retry của một job là **một yêu cầu được xử lý lặp lại**.
- Hai người khác nhau nhận thông báo giống nhau là **hai lần gửi độc lập**, nếu hệ thống quản lý từng recipient như từng job.

Vì vậy, **không dùng riêng body hoặc subject làm message key**. Key phải mang ý nghĩa nghiệp vụ, không phải chỉ là dấu vân tay của nội dung.

## 2. Phân biệt các ID thường xuất hiện trong luồng gửi mail

Trong code Spring Mail, nhiều tên định danh dễ bị nhầm:

| Định danh | Đại diện cho | Khi retry | Ai tạo/kiểm soát |
| --- | --- | --- | --- |
| **Message key / idempotency key** | Ý định gửi email duy nhất theo nghiệp vụ | **Giữ nguyên** | Application/client theo contract |
| **Job ID / outbox ID** | Bản ghi công việc đã tiếp nhận | Thường giữ nguyên trong cùng job | Database/job service |
| **Attempt ID** | Một lần thử gọi transport | **Thay đổi** ở mỗi attempt | Worker |
| **Correlation ID / trace ID** | Liên kết log/tracing giữa các thành phần | Có thể giữ hoặc tạo span mới | Hệ thống observability |
| **RFC 5322 Message-ID** | Header định danh email message | Có thể giữ nguyên hoặc thay đổi theo chính sách MIME/provider | Mail library/ứng dụng |
| **Provider message ID** | Định danh do nhà cung cấp mail cấp hoặc trả về | Phụ thuộc provider và mỗi lần submit | Provider |
| **Business event ID** | Một sự kiện nghiệp vụ đã phát sinh | Giữ nguyên khi phát lại cùng event | Domain/event store |

Ví dụ một job:

~~~text
businessEventId = evt-8f2a
messageKey      = order-confirmed:A123:evt-8f2a:alice
outboxJobId     = job-752
attemptId       = attempt-1
correlationId   = trace-204

Retry:
messageKey      = order-confirmed:A123:evt-8f2a:alice
outboxJobId     = job-752
attemptId       = attempt-2
correlationId   = trace-205
~~~

Key và job ID xác định **cùng yêu cầu**; attempt ID phân biệt **các lần thực thi**.

### 2.1. Không nhầm message key với header Message-ID

Trong MIME, một email có thể có header:

~~~text
Message-ID: <a123-confirmation-752@example.com>
~~~

Header `Message-ID` được các hệ thống email sử dụng cho việc nhận diện message, hội thoại và xử lý liên quan. Nó **không phải** một idempotency key được SMTP chuẩn hóa để từ chối email gửi lặp.

Ngay cả khi hai email có cùng `Message-ID`, không nên giả định mọi SMTP server hoặc mail client sẽ tự động gộp chúng hoặc bỏ qua bản thứ hai. Ngược lại, một provider có thể thay đổi Message-ID hoặc trả định danh provider riêng. Kho chống trùng của ứng dụng vẫn phải sử dụng **message key và trạng thái bền vững** theo contract của ứng dụng.

### 2.2. Correlation ID không tự bảo đảm idempotency

Trace ID có thể được tạo mới khi request được retry. Nếu dùng trace ID làm key, cùng sự kiện sẽ bị xem là job mới. Correlation ID phù hợp để tìm log, không phải lựa chọn mặc định để xác định một yêu cầu gửi duy nhất.

## 3. Quy tắc thiết kế message key

Một message key hữu ích cần có các thuộc tính sau:

1. **Ổn định qua retry:** cùng yêu cầu thì luôn dùng lại key.
2. **Phân biệt sự kiện hợp lệ:** thông báo mới thật sự phải có key khác.
3. **Có phạm vi duy nhất rõ ràng:** toàn hệ thống, trong từng tenant, từng loại thông báo hoặc từng recipient.
4. **Không chứa dữ liệu nhạy cảm không cần thiết:** tránh email cá nhân, số điện thoại, token xác thực hoặc thông tin thanh toán.
5. **Có thể so sánh/đối chiếu bằng quy tắc xác định:** không phụ thuộc thời gian hệ thống ngẫu nhiên ở mỗi attempt.
6. **Được lưu bền vững:** chỉ kiểm tra bằng cache trong bộ nhớ không đủ cho nhiều instance hoặc restart.
7. **Có chính sách vòng đời và retention:** biết giữ key bao lâu để phát hiện request lặp.

### 3.1. Cấu trúc key theo nghiệp vụ

Một cách tạo key:

~~~text
<event-type>:<business-object-id>:<event-version>:<channel>:<recipient-id>
~~~

Ví dụ:

~~~text
order-confirmed:order-123:event-5:email:user-88
password-reset-request:request-774:email:user-88
payment-reminder:invoice-29:round-2:email:user-88
~~~

Các thành phần có ý nghĩa:

- `event-type` phân biệt xác nhận, nhắc thanh toán, thông báo hủy.
- `business-object-id` xác định đối tượng nghiệp vụ.
- `event-version` hoặc event ID xác định một lần phát sinh cụ thể.
- `channel` phân biệt email với SMS/push nếu cùng kho key dùng cho nhiều kênh.
- `recipient-id` phân biệt các job gửi độc lập cho những người nhận khác nhau.

Nếu một job đại diện cho **một email có nhiều To/Cc/Bcc**, scope key có thể là job notification duy nhất thay vì từng recipient. Nhưng nếu worker tách một sự kiện thành nhiều job độc lập theo recipient, cần đưa recipient identity vào scope hoặc key.

### 3.2. Không chỉ dùng order ID

Key như:

~~~text
order-123
~~~

thường quá rộng. Cùng order có thể cần:

- email xác nhận;
- email cập nhật giao hàng;
- email hoàn tiền;
- nhiều lần nhắc thanh toán;
- email hủy.

Nếu mọi thông báo dùng cùng key, hệ thống sẽ loại nhầm các thông báo hợp lệ. Cần thêm loại sự kiện và instance/version.

### 3.3. Không tạo UUID mới ở mỗi lần retry

Sai:

~~~java
public String keyForRetry() {
    return UUID.randomUUID().toString();
}
~~~

Nếu mỗi retry tạo một UUID mới, kho deduplication không thể nhận diện yêu cầu trước đó.

Đúng khi **key UUID được tạo một lần và lưu lại**:

~~~java
String messageKey = request.getMessageKey(); // Đã được tạo ở ingress.
queue.publish(new MailJob(messageKey, payload));

// Khi retry:
queue.publish(new MailJob(messageKey, payload));
~~~

UUID ngẫu nhiên hoàn toàn có thể là message key, miễn là nó được cấp một lần cho request gốc và lưu/publish ổn định. Điểm quan trọng là **ổn định theo ý định gửi**, không phải nhất thiết là một chuỗi tự mô tả được.

### 3.4. Thời gian và attempt không nên nằm trong key nếu chỉ là retry

Không nên tạo key:

~~~text
order-confirmed:A123:2026-11-12T15:00:00.123
order-confirmed:A123:2026-11-12T15:00:03.481
~~~

nếu hai timestamp chỉ là hai attempt của cùng một thông báo. Cách này khiến deduplication mất tác dụng. Nếu mốc thời gian thực sự biểu diễn **hai kỳ gửi có chủ ý** (ví dụ lời nhắc ngày 1 và ngày 7), thì nó có thể là thành phần của identity nghiệp vụ, nhưng cần chuẩn hóa theo kỳ thay vì dùng thời gian chạy của worker.

## 4. Key do client cung cấp hay do server sinh?

Hai nguồn tạo key phổ biến có đặc điểm khác nhau.

| Cách tạo | Ví dụ | Khi phù hợp | Điểm cần lưu ý |
| --- | --- | --- | --- |
| **Client-supplied idempotency key** | Header `Idempotency-Key: 7f3c...` | HTTP API nhận một lệnh có thể retry | Xác thực caller, phạm vi tenant, giới hạn độ dài, kiểm tra payload |
| **Server-derived business key** | `order-confirmed:123:event-8` | Event-driven/internal use case | Định nghĩa chính xác identity và event version |
| **Server-generated persistent UUID** | `f02e...` | Tạo job mới có ID bền vững | Sinh một lần và trả/lưu lại để retry dùng chung |

### 4.1. Ví dụ API HTTP với Idempotency-Key

Client có thể gửi:

~~~http
POST /api/orders/A123/confirm
Idempotency-Key: 6cd7e0f2-5bf1-4d3b-8bc3-02c431190c8c
Content-Type: application/json

{"notifyCustomer":true}
~~~

Nếu request timeout, client gửi lại với **cùng key**. Server tìm bản ghi đã tiếp nhận:

- chưa có: kiểm tra quyền, xử lý nghiệp vụ và ghi nhận key;
- đã có và payload tương đương: trả kết quả/job trước đó;
- đã có nhưng payload khác: báo conflict, không âm thầm sử dụng lại key cho một ý định mới.

Một response ví dụ:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "jobId": "job-752",
  "status": "PENDING"
}
~~~

Khi cùng request được gửi lại, server có thể trả cùng `jobId` với trạng thái mới nhất. Contract API cần ghi rõ response của request đầu và request trùng, khoảng thời gian key còn hiệu lực, cũng như xử lý trường hợp payload mismatch.

**Lưu ý:** không cung cấp endpoint “gửi email tới bất kỳ địa chỉ nào” chỉ vì đã có idempotency key. Validation, authorization, rate limiting và chính sách chống lạm dụng vẫn là những lớp bảo vệ độc lập.

### 4.2. Dùng event ID của nghiệp vụ

Một event bền vững:

~~~java
public record OrderConfirmedEvent(
        String eventId,
        String orderId,
        String customerId,
        String customerEmail,
        int version) {
}
~~~

Khi cùng event được replay, `eventId` không thay đổi. Có thể dùng:

~~~java
String messageKey = "order-confirmation:"
        + event.eventId()
        + ":email:"
        + event.customerId();
~~~

Nếu yêu cầu gửi **cùng một event cho nhiều người nhận**, mỗi recipient có thể có key riêng. Nếu chính sách là gửi một email duy nhất tới nhiều người nhận cùng lúc, tạo một job có identity riêng rồi lưu danh sách người nhận như dữ liệu job.

## 5. Phạm vi uniqueness: key duy nhất ở đâu?

Key không thể được thiết kế đúng nếu không xác định rõ phạm vi.

Ví dụ trong hệ thống multi-tenant, hai tenant cùng dùng chuỗi:

~~~text
order-confirmed:123:v1:email
~~~

Nếu khóa duy nhất chỉ nằm trên cột `message_key` của một database dùng chung, hai yêu cầu không liên quan có thể va chạm.

Nên cân nhắc ràng buộc theo scope:

~~~sql
UNIQUE (tenant_id, message_key)
~~~

Nếu event type hoặc channel không nằm trong giá trị key, chúng có thể cần là cột scope:

~~~sql
UNIQUE (tenant_id, notification_type, channel, message_key)
~~~

Quy tắc chọn scope phải nhất quán giữa **người tạo key**, **unique constraint** và **logic tìm lại job**. Không chỉ kiểm tra uniqueness bằng một phép tìm kiếm tùy ý trước khi insert.

### 5.1. Tránh đưa PII thô vào key

Không nên:

~~~text
reset-password:nguyen.an@example.net:2026-11-12
~~~

Email cá nhân sẽ xuất hiện trong log, metric, URL hoặc bảng outbox nếu key được dùng để trace. Có thể dùng account ID nội bộ hoặc một opaque event ID:

~~~text
reset-password:req-7c22:email:user-88
~~~

Nếu yêu cầu che cả ID nghiệp vụ, có thể dùng UUID lưu bền vững hoặc HMAC của chuỗi canonical bằng secret được quản lý phù hợp. Không dùng hash thường rồi coi như dữ liệu đã được ẩn an toàn, đặc biệt với tập giá trị đầu vào có thể đoán.

### 5.2. Key không phải bí mật hay cơ chế xác thực

Biết message key không có nghĩa được phép đọc job, lấy nội dung email, xem trạng thái người khác hoặc gửi lại email. Mọi API lookup phải kiểm tra authorization theo tenant và chủ thể liên quan. Key là công cụ nhận diện request, **không phải bearer token**.

## 6. Vòng đời message key và trạng thái gửi

Một key thường đi cùng bản ghi trạng thái bền vững.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Insert key + job
    PENDING --> PROCESSING: Worker claim
    PROCESSING --> SUBMITTED: Transport accepted
    PROCESSING --> RETRY_WAIT: Temporary/uncertain error
    RETRY_WAIT --> PROCESSING: Retry same key
    PROCESSING --> FAILED_FINAL: Permanent failure
    SUBMITTED --> [*]: Retention / archive
    FAILED_FINAL --> [*]: Retention / archive
~~~

Tên trạng thái chỉ là ví dụ:

| Trạng thái | Ý nghĩa | Hành vi khi nhận lại cùng key |
| --- | --- | --- |
| `PENDING` | Yêu cầu đã được ghi, chưa gửi | Trả cùng job, không insert mới |
| `PROCESSING` | Worker đang giữ claim/lease | Trả cùng job; không khởi tạo attempt song song |
| `RETRY_WAIT` | Đang chờ thử lại | Trả job cũ và lịch retry |
| `SUBMITTED` | Lần gọi transport đã hoàn tất không báo lỗi | Không gửi lại chỉ vì HTTP request lặp |
| `FAILED_FINAL` | Kết thúc thất bại theo chính sách | Trả trạng thái thất bại; retry thủ công cần quy tắc rõ |

**`SUBMITTED` không đồng nghĩa email đã tới Inbox.** `JavaMailSender.send(...)` có thể hoàn tất quá trình nộp thư cho SMTP transport nhưng không bảo đảm delivery cuối cùng. Nếu sản phẩm cần `DELIVERED` hoặc `BOUNCED`, hãy bổ sung trạng thái riêng từ provider event/webhook.

### 6.1. Retention và key đã hết hạn

Một kho idempotency không nhất thiết giữ bản ghi mãi mãi. Tuy nhiên, xóa key quá sớm có thể khiến một request retry muộn được hiểu thành yêu cầu hoàn toàn mới.

Hãy xác định thời hạn theo:

- thời gian client có thể retry cùng request;
- thời gian job nằm trong queue;
- lịch retry/backoff và thời gian dead-letter;
- thời gian tối đa cần hỗ trợ retry thủ công;
- yêu cầu lưu trữ và xóa dữ liệu cá nhân.

Nếu một key bị xóa trong khi broker vẫn có thể replay event cũ, deduplication có thể thất bại. Với yêu cầu nghiệp vụ quan trọng, có thể giữ **tombstone tối thiểu** (scope + key + trạng thái/identity cần thiết) sau khi xóa payload nhạy cảm, thay vì xóa luôn mọi dấu vết.

### 6.2. Cùng key nhưng payload khác phải làm gì?

Ví dụ client gửi:

~~~text
Key: confirm-order-A123
Payload 1: recipient=alice@example.net, amount=220000
~~~

Sau đó gửi:

~~~text
Key: confirm-order-A123
Payload 2: recipient=bob@example.net, amount=500000
~~~

Không nên trả “đã tiếp nhận” mà bỏ qua sự khác biệt, cũng không nên gửi thêm email mới dưới cùng key.

Một policy phổ biến là lưu **payload fingerprint** rồi từ chối khi key đã tồn tại nhưng dữ liệu có ý nghĩa khác:

~~~text
Same scoped key + same canonical fingerprint -> existing job
Same scoped key + different fingerprint     -> conflict (HTTP 409)
Different scoped key                        -> new logical request
~~~

Fingerprint phải được tạo từ những trường xác định danh tính và nội dung của yêu cầu: recipient, loại thông báo, template/version, dữ liệu nghiệp vụ có ý nghĩa. Không đưa các giá trị thay đổi ở từng attempt như timestamp retry, trace ID hoặc số lần thử vào fingerprint.

## 7. Lưu key bằng database và unique constraint

Một cách triển khai đáng tin cậy là tạo bảng outbox/job có ràng buộc duy nhất.

### 7.1. Schema tham khảo

~~~sql
CREATE TABLE mail_outbox (
    id                VARCHAR(64) PRIMARY KEY,
    tenant_id         VARCHAR(64) NOT NULL,
    message_key       VARCHAR(200) NOT NULL,
    request_digest    CHAR(64) NOT NULL,
    notification_type VARCHAR(80) NOT NULL,
    recipient         VARCHAR(320) NOT NULL,
    template_id       VARCHAR(120) NOT NULL,
    template_version  VARCHAR(40),
    payload_json      TEXT NOT NULL,
    status            VARCHAR(30) NOT NULL,
    attempts          INTEGER NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMP,
    claimed_until     TIMESTAMP,
    submitted_at      TIMESTAMP,
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL,
    CONSTRAINT uq_mail_message_key
        UNIQUE (tenant_id, message_key)
);
~~~

Schema này minh họa:

- `tenant_id`: phạm vi của key.
- `message_key`: định danh ý định gửi.
- `request_digest`: fingerprint để phát hiện tái sử dụng key với nội dung khác.
- `payload_json`: snapshot dữ liệu cần gửi/render.
- `status` và `attempts`: vòng đời của job, **không** phải thành phần identity.
- `claimed_until`: lease giúp nhiều worker phối hợp claim.
- `submitted_at`: thời điểm sender đã hoàn tất thao tác nộp thư.

Đây là schema tổng quát; kiểu JSON, UTC/timestamp with time zone, index, giới hạn chiều dài và phương thức claim phụ thuộc database cụ thể. Các cột chứa địa chỉ và payload có thể là dữ liệu cá nhân, cần chính sách quyền truy cập, mã hóa và retention phù hợp.

### 7.2. Vì sao SELECT trước rồi INSERT chưa đủ?

Code dễ gặp:

~~~java
if (!repository.existsByMessageKey(messageKey)) {
    repository.save(job);
}
~~~

Hai instance có thể chạy đồng thời:

~~~text
Worker A: SELECT -> chưa có key
Worker B: SELECT -> chưa có key
Worker A: INSERT job A
Worker B: INSERT job B
~~~

Nếu database không có unique constraint, có thể tạo hai job. Dù có check ở tầng Java, **database vẫn phải cưỡng chế tính duy nhất**.

Khi có unique constraint, một insert sẽ thắng; insert còn lại phải được coi là một lần nhận lại cùng yêu cầu, sau khi so sánh fingerprint và đọc job cũ. Đừng biến mọi unique violation thành lỗi nội bộ HTTP 500.

## 8. Upsert an toàn với cùng key

Ví dụ PostgreSQL cho phép:

~~~sql
INSERT INTO mail_outbox (
    id, tenant_id, message_key, request_digest,
    notification_type, recipient, template_id,
    template_version, payload_json, status,
    created_at, updated_at
)
VALUES (
    :id, :tenantId, :messageKey, :requestDigest,
    :notificationType, :recipient, :templateId,
    :templateVersion, :payloadJson, 'PENDING',
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
)
ON CONFLICT (tenant_id, message_key) DO NOTHING;
~~~

Nếu insert thành công: ứng dụng đã tạo job mới.

Nếu conflict: ứng dụng đọc job theo `tenant_id` và `message_key`, so sánh `request_digest` rồi trả lại job đã có hoặc báo mismatch.

Điều kiện quan trọng:

- Ràng buộc UNIQUE phải đúng scope.
- Cùng key **không được UPDATE đè payload của job cũ**.
- Một conflict không tự chứng minh payload tương đương; luôn kiểm tra fingerprint.
- Cần hiểu isolation level và thời điểm record từ transaction cạnh tranh trở nên nhìn thấy được.
- Cách upsert khác nhau giữa PostgreSQL, MySQL, SQL Server và các database khác; ví dụ này không portable nguyên xi.

### 8.1. Ví dụ service Spring với NamedParameterJdbcTemplate

Giả sử có command đã được ứng dụng kiểm tra:

~~~java
public record MailCommand(
        String tenantId,
        String messageKey,
        String notificationType,
        String recipient,
        String templateId,
        String templateVersion,
        String canonicalPayloadJson) {
}
~~~

`canonicalPayloadJson` là snapshot đã serialize theo quy tắc ổn định: cùng dữ liệu logic phải tạo cùng chuỗi canonical. Một serializer thông thường không nhất thiết tạo JSON có thứ tự thuộc tính cố định; cần cấu hình canonicalization hoặc xây fingerprint từ các trường chuẩn hóa được quy định rõ.

Service tạo hoặc trả job:

~~~java
import java.util.Map;
import java.util.UUID;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MailJobSubmissionService {
    private final NamedParameterJdbcTemplate jdbc;
    private final PayloadDigests digests;

    public MailJobSubmissionService(
            NamedParameterJdbcTemplate jdbc,
            PayloadDigests digests) {
        this.jdbc = jdbc;
        this.digests = digests;
    }

    @Transactional
    public MailJobReceipt submit(MailCommand command) {
        // Validate key, recipient, authorization và template
        // ở application boundary trước khi gọi repository.
        String digest = digests.sha256(command);
        String newJobId = UUID.randomUUID().toString();

        String sql = """
                INSERT INTO mail_outbox (
                    id, tenant_id, message_key, request_digest,
                    notification_type, recipient, template_id,
                    template_version, payload_json, status,
                    created_at, updated_at
                ) VALUES (
                    :id, :tenantId, :messageKey, :digest,
                    :notificationType, :recipient, :templateId,
                    :templateVersion, :payload, 'PENDING',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                ON CONFLICT (tenant_id, message_key) DO NOTHING
                """;

        Map<String, ?> params = Map.ofEntries(
                Map.entry("id", newJobId),
                Map.entry("tenantId", command.tenantId()),
                Map.entry("messageKey", command.messageKey()),
                Map.entry("digest", digest),
                Map.entry("notificationType", command.notificationType()),
                Map.entry("recipient", command.recipient()),
                Map.entry("templateId", command.templateId()),
                Map.entry("templateVersion",
                        command.templateVersion() == null
                                ? "" : command.templateVersion()),
                Map.entry("payload", command.canonicalPayloadJson())
        );

        int inserted = jdbc.update(sql, params);
        if (inserted == 1) {
            return new MailJobReceipt(newJobId, "PENDING", false);
        }

        MailJobReceiptWithDigest old = jdbc.queryForObject(
                """
                SELECT id, status, request_digest
                FROM mail_outbox
                WHERE tenant_id = :tenantId
                  AND message_key = :messageKey
                """,
                Map.of(
                        "tenantId", command.tenantId(),
                        "messageKey", command.messageKey()),
                (rs, rowNum) -> new MailJobReceiptWithDigest(
                        rs.getString("id"),
                        rs.getString("status"),
                        rs.getString("request_digest"))
        );

        if (old == null || !old.requestDigest().equals(digest)) {
            throw new IdempotencyConflictException(
                    "Message key was already used with another request");
        }

        return new MailJobReceipt(old.id(), old.status(), true);
    }
}

record MailJobReceipt(String jobId, String status, boolean duplicate) {}
record MailJobReceiptWithDigest(
        String id, String status, String requestDigest) {}
~~~

Đây là ví dụ Spring JDBC dành cho PostgreSQL, không phải một hệ thống mail worker hoàn chỉnh. Các class `PayloadDigests` và `IdempotencyConflictException` là thành phần ứng dụng cần định nghĩa. Trong thực tế, phải validate input trước khi chèn, bảo vệ quyền truy cập tenant, giới hạn độ dài key và xử lý lỗi database theo contract.

Lưu ý rằng trong ví dụ, `templateVersion` null được chuẩn hóa thành chuỗi rỗng khi insert; fingerprint cũng phải dùng cùng quy tắc chuẩn hóa. Trong triển khai thực, có thể sử dụng SQL parameter source hỗ trợ null thay vì thay giá trị null bằng chuỗi rỗng nếu hai trạng thái mang ý nghĩa khác nhau.

### 8.2. Fingerprint SHA-256 là gì?

Fingerprint giúp phát hiện **sự khác biệt của yêu cầu khi cùng key được dùng lại**. Ví dụ khái niệm:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class PayloadDigests {
    public String sha256(MailCommand command) {
        String canonical = String.join(
                "\n",
                command.notificationType(),
                command.recipient(),
                command.templateId(),
                command.templateVersion() == null
                        ? "" : command.templateVersion(),
                command.canonicalPayloadJson()
        );

        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(canonical.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

Đoạn này chỉ minh họa ý tưởng. Với production, canonicalization phải loại bỏ mọi sự mơ hồ do dấu phân tách, chuẩn hóa địa chỉ/Unicode/locale theo quy tắc nghiệp vụ và không bỏ sót các field có ý nghĩa. Nếu dùng dấu xuống dòng làm separator, cần bảo đảm dữ liệu không thể tạo cùng chuỗi canonical qua cách ghép khác nhau; cách chắc chắn hơn là serialize một cấu trúc có schema rõ ràng bằng định dạng canonical hoặc dùng length-prefix cho từng field.

SHA-256 ở đây phục vụ **so sánh nhất quán**, không phải mã hóa hay xác thực người dùng. Không coi digest là secret, cũng không dùng digest để thay thế authorization.

## 9. Kết hợp message key với transaction nghiệp vụ

Khi email được tạo do một giao dịch database, chỉ lưu message key trong một map/cache ngoài transaction vẫn có thể để lại khoảng trống.

Ví dụ:

~~~text
T1 Update order = CONFIRMED
T2 Database COMMIT thành công
T3 Process crash trước khi ghi mail job/key
T4 Không có email job để worker gửi
~~~

Để tránh mất yêu cầu gửi, dùng **transactional outbox**: tạo outbox row chứa message key **trong cùng transaction** với việc cập nhật đơn hàng.

~~~mermaid
flowchart TD
    A["BEGIN transaction"] --> B["Update business entity"]
    B --> C["Insert outbox with stable message key"]
    C --> D{"COMMIT"}
    D -->|Rollback| E["Không có update, không có job"]
    D -->|Success| F["Business state và mail job đều bền vững"]
    F --> G["Worker claim mail job"]
    G --> H["SMTP submission"]
    H --> I["Update status / schedule retry"]
~~~

Một service:

~~~java
@Transactional
public void confirmOrder(Long orderId, String eventId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();

    String key = "order-confirmed:"
            + eventId
            + ":email:"
            + order.getCustomerId();

    mailJobSubmissionService.submit(
            new MailCommand(
                    order.getTenantId(),
                    key,
                    "ORDER_CONFIRMED",
                    order.getCustomerEmail(),
                    "order-confirmation",
                    "v1",
                    canonicalOrderMailPayload(order))
    );
}
~~~

Để hai thao tác thật sự cùng transaction, repository nghiệp vụ và outbox phải dùng đúng transaction manager/datasource; `submit` không được dùng `REQUIRES_NEW` một cách vô ý. Cũng cần xem xét cách `@Transactional` được áp dụng thông qua Spring proxy; tự gọi một method trong cùng bean có thể không đi qua proxy.

Nếu transaction rollback, cả thay đổi đơn hàng lẫn outbox row phải rollback. Nếu commit thành công rồi tiến trình dừng, job vẫn ở database để worker lấy lại.

### 9.1. Message key không thay thế outbox

Một key đúng chỉ giúp **nhận diện cùng yêu cầu**. Nếu chỉ giữ key trong bộ nhớ:

- nhiều instance có thể tạo trùng;
- restart làm mất trạng thái;
- không có job bền vững để retry;
- không bảo đảm đồng bộ với commit nghiệp vụ.

Outbox là nơi lưu yêu cầu gửi và trạng thái; key là ràng buộc giúp tránh tiếp nhận trùng.

## 10. Retry một job: key ổn định, attempt ID thay đổi

Khi worker xử lý một outbox job, nó có thể gặp lỗi SMTP tạm thời.

~~~text
Job:
  jobId       = job-752
  messageKey  = order-confirmed:A123:event-5:email:user-88
  status      = RETRY_WAIT
  attempts    = 2

Attempt tiếp theo:
  jobId       = job-752
  messageKey  = order-confirmed:A123:event-5:email:user-88
  attemptId   = try-3
~~~

Không tạo thêm outbox row cho mỗi attempt. Worker nên giữ job ID và message key cố định, chỉ tăng attempt count hoặc ghi bản ghi attempt riêng khi cần audit.

### 10.1. Claim job trước khi gửi

Nếu hai worker nhận cùng job một lúc, cả hai có thể gọi `sender.send`. Message key trong bảng outbox giúp chỉ có một **job**, nhưng không tự ngăn hai worker **xử lý job đó đồng thời**.

Vì vậy, worker cần cơ chế claim/lease:

1. Chọn job `PENDING` hoặc `RETRY_WAIT` đủ điều kiện.
2. Claim bằng update có điều kiện hoặc row lock.
3. Ghi owner/lease expiry và tăng attempts.
4. Commit transaction claim ngắn.
5. Gửi SMTP ngoài transaction claim.
6. Cập nhật kết quả trong transaction mới.

Một số database hỗ trợ `SELECT ... FOR UPDATE SKIP LOCKED`; hệ thống khác có thể dùng optimistic locking, compare-and-swap update hoặc queue broker có visibility timeout. Chọn theo hạ tầng đang dùng.

Nếu worker crash, lease phải hết hạn để job được nhận lại. Nếu job có thể chạy lâu hơn lease, cần cơ chế gia hạn hoặc fencing token để giảm trường hợp hai worker cùng xử lý do lease hết hạn quá sớm.

### 10.2. Backoff không làm thay đổi identity

Ví dụ lịch retry:

~~~text
Attempt 1: ngay lập tức
Attempt 2: sau 30 giây
Attempt 3: sau 2 phút
Attempt 4: sau 10 phút
Sau đó:   FAILED_FINAL / dead-letter
~~~

Các mốc chỉ minh họa, không phải thời gian bắt buộc. Có thể thêm jitter và giới hạn attempts để tránh nhiều worker dồn lên SMTP provider cùng lúc. `messageKey` vẫn là một giá trị xuyên suốt mọi attempt.

### 10.3. Không retry mọi lỗi như nhau

| Nhóm kết quả | Ví dụ | Cách cân nhắc |
| --- | --- | --- |
| Lỗi tạm thời | SMTP 4xx hoặc lỗi mạng tạm thời | Retry với backoff/limit |
| Lỗi vĩnh viễn | Địa chỉ bị từ chối dứt khoát hoặc lỗi dữ liệu | Sửa dữ liệu/chính sách; không retry vô hạn |
| Authentication/config | Credentials sai hoặc TLS config lỗi | Cần vận hành can thiệp |
| Kết quả không xác định | Timeout sau khi có thể đã truyền toàn bộ message | Có nguy cơ gửi trùng khi retry |
| Transport thành công | `JavaMailSender.send` trả về không lỗi | Đánh dấu `SUBMITTED`, không tạo job mới |

Không thể kết luận “lỗi SMTP nghĩa là email chưa tới provider” chỉ từ một exception tổng quát. Cần lưu trạng thái attempt và nguyên nhân đủ để quyết định.

## 11. Giới hạn: tại sao message key không tạo exactly-once SMTP?

Xét tình huống:

~~~text
1. Worker lấy job J-752 (key K).
2. Worker gửi email.
3. SMTP server chấp nhận thông điệp.
4. Worker bị crash trước khi ghi status = SUBMITTED.
5. Lease của job hết hạn.
6. Worker khác nhận lại J-752 và gửi lại cùng email.
~~~

Database vẫn chỉ có **một job và một message key**. Nhưng SMTP có thể nhận **hai lần gửi** vì kết quả gửi và cập nhật trạng thái database không thuộc một transaction nguyên tử.

Điều message key có thể bảo đảm, nếu dùng unique constraint đúng, là:

- cùng yêu cầu không bị insert thành hai outbox job độc lập;
- retry HTTP/event có thể tìm được job trước đó;
- có một identity ổn định để theo dõi tất cả attempts.

Điều nó **không tự bảo đảm**:

- SMTP server nhận đúng một bản;
- không có timeout mơ hồ;
- provider không gửi trùng;
- người nhận chỉ thấy một email;
- delivery thành công.

Nếu provider qua API hỗ trợ **idempotency key phía provider**, có thể chuyển message key hoặc một key suy ra từ nó theo yêu cầu provider. Khi đó phải xem rõ phạm vi, TTL và semantics của provider, không tự suy diễn rằng SMTP thuần có tính năng tương tự.

### 11.1. Message-ID có giúp chống gửi trùng không?

Có thể đặt một RFC 5322 `Message-ID` ổn định khi retry, nhưng không được xem đây là cơ chế deduplication đáng tin cậy giữa tất cả SMTP server và mail client. Một số hệ thống có thể dùng header này để hiển thị hội thoại hoặc xử lý duplicate theo chính sách riêng, song không có bảo đảm chung rằng mọi lần submission với cùng header sẽ bị từ chối.

Hãy quản lý idempotency tại tầng ứng dụng và tận dụng API provider khi có hỗ trợ chính thức.

## 12. Cùng message key nhưng cần gửi lại có chủ ý

Một lần gửi thất bại vĩnh viễn hoặc một email bị bounce có thể khiến bộ phận hỗ trợ muốn gửi lại.

Có hai ý định khác nhau:

1. **Tiếp tục cùng yêu cầu:** retry lại job cũ vì lỗi tạm thời hoặc thao tác thủ công được cho phép. Giữ cùng key, tăng attempt, ghi audit.
2. **Tạo một thông báo mới:** ví dụ khách hàng cập nhật địa chỉ email, nội dung được sửa hoặc người dùng bấm “Gửi lại xác nhận” theo chính sách. Tạo identity nghiệp vụ mới và key mới.

Không tự động tạo key mới khi nhận lỗi để “vượt qua” unique constraint. Làm vậy khiến cơ chế chống trùng bị vô hiệu.

### 12.1. Resend cần định nghĩa rõ

Ví dụ:

~~~text
order-confirmed:A123:event-5:email:user-88
~~~

Nếu thực sự có lệnh resend độc lập:

~~~text
order-confirmed-resend:A123:resend-request-2:email:user-88
~~~

Lệnh resend nên đi qua authorization, rate limit và audit. Hệ thống cần xác định có cho gửi lại cùng link/token hay phải tạo token mới. Với email xác minh hoặc đặt lại mật khẩu, việc phát hành token mới là một sự kiện bảo mật riêng; không coi chỉ đổi message key là đủ.

### 12.2. Fan-out nhiều recipient

Khi một sự kiện cần gửi cho ba người:

~~~text
invoice-issued:INV-30:event-8:email:customer-1
invoice-issued:INV-30:event-8:email:finance-2
invoice-issued:INV-30:event-8:email:admin-3
~~~

Mỗi recipient có một identity job nếu worker gửi từng email. Nếu chỉ dùng key `invoice-issued:INV-30:event-8` cho cả ba job trong cùng scope, unique constraint có thể chặn hai người nhận còn lại.

Ngược lại, với một `MimeMessage` duy nhất có nhiều To/Cc/Bcc, có thể xác định một key cấp message/job và giữ recipient list đã chuẩn hóa trong payload fingerprint. Không có một cách scope đúng cho mọi ứng dụng; phải chọn tương ứng với đơn vị công việc cần chống trùng.

## 13. Validation và bảo mật message key

Message key thường có mặt trong request HTTP, hàng đợi hoặc database. Vì vậy, cần áp dụng giới hạn đầu vào:

- Giới hạn độ dài, ví dụ 1–200 ký tự theo contract.
- Chỉ chấp nhận các ký tự hợp lệ theo format đã công bố.
- Không cho CR/LF hoặc ký tự điều khiển làm ảnh hưởng log/header.
- Không chấp nhận key rỗng.
- Ràng buộc key với tenant/user/use case đã được xác thực.
- Không cho một client sử dụng key để truy cập job của tenant khác.
- Không dùng key làm phép kiểm tra quyền hoặc mã xác thực.
- Không đưa PII thô vào metric label.

### 13.1. Ví dụ value object

~~~java
import java.util.Objects;
import java.util.regex.Pattern;

public record MailMessageKey(String value) {
    private static final Pattern ALLOWED =
            Pattern.compile("[A-Za-z0-9:._-]{1,200}");

    public MailMessageKey {
        Objects.requireNonNull(value, "messageKey");
        if (!ALLOWED.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "Invalid mail message key");
        }
    }
}
~~~

Đây là policy minh họa cho key ASCII do ứng dụng sinh. Nếu sản phẩm cho client gửi UUID hoặc định dạng khác, điều chỉnh regex cho đúng contract. Nếu sử dụng Unicode trong key, cần định nghĩa normalization và giới hạn byte/ký tự nhất quán; không mặc định mọi backend xử lý so sánh Unicode giống nhau.

### 13.2. Không để key thành vector gây từ chối dịch vụ

Một người dùng có thể gửi hàng nghìn key ngẫu nhiên để cố tạo vô hạn job mới. Idempotency key không tự chống spam hoặc abuse. Cần:

- authentication/authorization;
- rate limit theo account/tenant;
- kiểm soát quota gửi mail;
- giới hạn payload và recipient;
- giám sát số job và dung lượng outbox;
- cleanup/retention rõ ràng;
- xác thực nghiệp vụ trước khi ghi nhận yêu cầu gửi.

Nếu request trùng được trả lại từ kho, vẫn cần kiểm tra người gọi có quyền đọc thông tin job đó.

## 14. Observability: theo dõi key mà không rò rỉ dữ liệu

Message key giúp liên kết các lần thử gửi cùng job:

~~~text
mailJobId=job-752
messageKey=order-confirmed:A123:event-5:email:user-88
attempt=1
status=RETRY_WAIT
reason=SMTP_TEMPORARY_ERROR
~~~

Lần thử sau:

~~~text
mailJobId=job-752
messageKey=order-confirmed:A123:event-5:email:user-88
attempt=2
status=SUBMITTED
~~~

Trong hệ thống có dữ liệu nhạy cảm, có thể log một key đã rút gọn/mã hóa theo policy hoặc chỉ log job ID. Không log toàn bộ recipient list, subject, body, token reset hoặc attachment bytes chỉ để debug retry.

### 14.1. Metric nên có

| Metric | Ý nghĩa |
| --- | --- |
| `mail_jobs_created_total` | Số logical job mới |
| `mail_idempotency_hits_total` | Số lần cùng key và cùng request được nhận lại |
| `mail_idempotency_conflicts_total` | Số lần reuse key với payload khác |
| `mail_attempts_total` | Số lần gọi transport |
| `mail_retry_scheduled_total` | Số lần lên lịch retry |
| `mail_submission_failures_total` | Số lần transport báo lỗi |
| `mail_jobs_pending` | Số job chờ |
| `mail_jobs_oldest_age_seconds` | Tuổi job chưa hoàn tất lâu nhất |

Không gắn từng `messageKey` làm label Prometheus vì số giá trị rất lớn, gây cardinality cao. Có thể gắn nhãn theo loại thông báo, tenant nhóm nhỏ được kiểm soát, provider hoặc kết quả.

### 14.2. Cảnh báo vận hành

Một vài tín hiệu cần theo dõi:

- tỷ lệ idempotency conflict tăng bất thường: có thể client tái sử dụng key sai;
- nhiều job ở `PROCESSING` vượt lease: worker crash hoặc deadlock;
- attempts tăng mạnh: SMTP provider có vấn đề;
- key hết hạn trước khi job hoàn tất: retention sai;
- cùng business event tạo nhiều message key: lỗi thiết kế identity;
- job `SUBMITTED` nhưng provider báo bounce: cần phân biệt submission với delivery.

## 15. Kiểm thử message key và deduplication

Test tốt cần xác nhận **ngữ nghĩa yêu cầu**, không chỉ kiểm tra phương thức tạo chuỗi key.

### 15.1. Unit test: cùng event tạo cùng key

~~~java
@Test
void sameEventProducesSameMessageKey() {
    OrderConfirmedEvent event =
            new OrderConfirmedEvent(
                    "evt-8f2a", "A123", "user-88");

    String first = keys.forOrderConfirmation(event);
    String retry = keys.forOrderConfirmation(event);

    assertEquals(first, retry);
}
~~~

`keys` là factory theo quy tắc ứng dụng; `OrderConfirmedEvent` là fixture tối giản minh họa. Test đối ứng cũng cần xác nhận hai event thật sự khác nhau sinh key khác nhau.

### 15.2. Integration test: cùng key tạo một job

1. Tạo request với key K và fingerprint F.
2. Gọi submission service hai lần.
3. Cả hai lần trả cùng job ID.
4. Database chỉ có một row với scope + key K.
5. Gọi lại K với fingerprint F2 khác.
6. Service báo conflict; không update đè payload cũ.

### 15.3. Concurrency test: hai request cùng lúc

Cho hai thread/instance submit cùng scoped key đồng thời. Xác nhận:

- unique constraint bảo đảm không có hai outbox row;
- một request tạo job, request còn lại đọc đúng job cũ;
- không có false success với payload khác;
- logic xử lý transaction conflict phù hợp database đang dùng.

Chỉ mock repository để test “check rồi insert” không chứng minh an toàn concurrency. Cần chạy với database thật hoặc môi trường integration test có behavior tương đương.

### 15.4. Retry test

Cho worker xử lý cùng job hai lần:

~~~text
Attempt 1: MailSendException
Status: RETRY_WAIT
Attempt 2: transport returns normally
Status: SUBMITTED
~~~

Xác nhận `messageKey` và job ID không đổi, attempts tăng, và không có outbox row mới.

### 15.5. Crash window test

Mô phỏng transport đã nhận thư nhưng worker chết trước khi commit trạng thái `SUBMITTED`. Xác nhận hệ thống có thể nhận lại job sau lease expiry và có cơ chế quan sát nguy cơ duplicate. Không viết assertion “SMTP luôn chỉ nhận một email” nếu provider không có idempotency support.

### 15.6. Retention test

Thử replay event cũ tại những mốc:

- key còn hiệu lực;
- job đang chờ retry;
- job đã `SUBMITTED`;
- key đã hết retention nhưng event vẫn có thể được replay.

Nếu chính sách đòi hỏi deduplication lâu dài, cần giữ tombstone hoặc identity nghiệp vụ đủ lâu.

## 16. Những lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Tạo UUID mới cho mỗi retry | Request cũ bị xem là mới | Tạo/lưu key một lần |
| Chỉ dùng subject/body làm key | Chặn nhầm email hợp lệ, không phản ánh identity | Dùng event/job/business identity |
| Chỉ dùng order ID | Các loại email của cùng order bị va chạm | Thêm event type và version |
| Không có tenant/recipient scope | Va chạm giữa người dùng hoặc tenant | Unique constraint theo scope |
| SELECT rồi INSERT không có UNIQUE | Race tạo nhiều job | Database unique constraint + conflict handling |
| Same key nhưng ghi đè payload | Ý nghĩa request thay đổi âm thầm | Lưu fingerprint, trả conflict |
| Chỉ lưu key trong cache | Mất dữ liệu sau restart, nhiều instance không thống nhất | Lưu key/job bền vững |
| Xóa key trước khi hết retry window | Replay muộn tạo job mới | Retention/tombstone |
| Dùng attempt ID làm key | Mọi attempt là job mới | Giữ message key, thay attempt ID |
| Dùng RFC Message-ID như bảo đảm chống trùng | SMTP/client không có bảo đảm loại trùng chung | Idempotency tại application/provider |
| Giữ DB transaction mở trong lúc gửi SMTP | Lock/connection tồn tại lâu | Claim ngắn, gửi ngoài transaction |
| Retry vô hạn khi SMTP timeout | Gửi trùng, tải provider | Retry policy, xử lý kết quả không xác định |
| In raw email/token trong key hoặc log | Rò rỉ thông tin | Opaque key, log tối thiểu |
| Cho caller chọn key để xem job người khác | Lộ trạng thái/thông tin | Authentication + authorization |
| Coi `SUBMITTED` là `DELIVERED` | Báo sai tình trạng thư | Theo dõi provider delivery riêng |

## 17. Quy trình thiết kế message key cho một loại email mới

Khi thêm email thông báo mới vào module Spring Framework Mail, có thể đi theo trình tự:

1. **Xác định đơn vị logical send:** một email tới một người nhận, hay một message chứa nhiều recipient?
2. **Xác định sự kiện nguồn:** order confirmed, invoice issued, reminder round, reset request.
3. **Định nghĩa identity:** event ID, business object ID và event version đủ để phân biệt sự kiện.
4. **Xác định scope:** tenant, notification type, channel, recipient nếu cần.
5. **Chọn cách tạo key:** business-derived ổn định hoặc UUID tạo một lần và lưu bền vững.
6. **Định nghĩa fingerprint:** field nào phải giữ nguyên nếu cùng key được dùng lại?
7. **Tạo unique constraint:** database phải cưỡng chế đúng phạm vi.
8. **Kết hợp outbox nếu cần độ tin cậy:** job và thay đổi nghiệp vụ được ghi trong cùng transaction.
9. **Định nghĩa retry:** key/job giữ nguyên, attempt thay đổi, có backoff và giới hạn.
10. **Định nghĩa retention và manual resend:** khi nào giữ tombstone, khi nào tạo identity mới?
11. **Kiểm thử concurrency, payload mismatch và crash window:** không giả định exactly-once SMTP.

### 17.1. Bảng hợp đồng ví dụ

| Thuộc tính | Quyết định cho email xác nhận đơn |
| --- | --- |
| Logical send | Một email xác nhận cho một customer |
| Event identity | `OrderConfirmedEvent.eventId` |
| Scope | `tenantId` + `messageKey` |
| Key format | `order-confirmed:<eventId>:email:<customerId>` |
| Payload fingerprint | Recipient, template/version, snapshot đơn hàng |
| New request | Key chưa tồn tại |
| Duplicate request | Key trùng, fingerprint trùng: trả job cũ |
| Conflict | Key trùng, fingerprint khác: từ chối |
| Retry | Cùng job/key, attempt tăng |
| Submission status | `SUBMITTED` sau transport không báo lỗi |
| Delivery status | Qua provider events nếu được hỗ trợ |
| Retention | Ít nhất bao trùm replay/retry window đã cam kết |

## 18. Tình huống tổng hợp: xác nhận đơn hàng với một key xuyên suốt

Giả sử khách hàng xác nhận đơn hàng A123. Ứng dụng tạo sự kiện `evt-8f2a` và message key:

~~~text
order-confirmed:evt-8f2a:email:user-88
~~~

Luồng:

~~~mermaid
sequenceDiagram
    participant U as HTTP client
    participant A as Order service
    participant D as DB + outbox
    participant W as Mail worker
    participant S as SMTP

    U->>A: Confirm order, idempotency key K
    A->>D: Update order + INSERT mail job K
    D-->>A: COMMIT, job-752
    A-->>U: 202 / job-752

    U->>A: Retry same request, key K
    A->>D: Lookup scoped key K
    D-->>A: Existing job-752
    A-->>U: Same job-752

    W->>D: Claim job-752
    W->>S: Send message, attempt-1
    S-->>W: Temporary failure
    W->>D: RETRY_WAIT
    W->>D: Claim job-752 later
    W->>S: Send message, attempt-2
    S-->>W: Accepted
    W->>D: SUBMITTED
~~~

Trong toàn bộ quy trình:

- client retry không tạo job mới;
- event replay không tạo yêu cầu mới nếu cùng event identity;
- worker giữ cùng message key xuyên suốt các lần thử;
- database unique constraint chống hai job cùng scoped key;
- trạng thái xử lý và attempts thay đổi, không thay đổi logical identity;
- SMTP vẫn có thể nhận email trùng ở crash window, nên hệ thống không tuyên bố exactly-once delivery.

Nếu sau đó khách hàng chủ động yêu cầu gửi lại xác nhận vì muốn nhận một thư mới, đó có thể là **một sự kiện nghiệp vụ mới** với message key khác, kèm rate limit và audit. Không được “giải quyết” deduplication bằng cách sinh key mới cho mọi retry.

## 19. Những điều cần nhớ

- **Message key định danh một ý định gửi**, không định danh một lần thử transport.
- Cùng yêu cầu thì giữ nguyên key qua HTTP retry, broker redelivery và worker retry.
- Thông báo mới hợp lệ phải có identity mới; không dùng nội dung email làm tiêu chí duy nhất.
- Xác định rõ scope tenant, event type, channel và recipient trước khi chọn unique constraint.
- Dùng database unique constraint để chống race; kiểm tra trước rồi insert bằng code không đủ.
- Với cùng key, phải so sánh fingerprint để phát hiện request khác dữ liệu.
- Message key, job ID, attempt ID, trace ID và RFC `Message-ID` có vai trò khác nhau.
- Kết hợp message key với transactional outbox khi cần lưu yêu cầu gửi cùng giao dịch nghiệp vụ.
- Giữ key/tombstone đủ lâu theo retry và replay window; xóa quá sớm làm mất khả năng deduplication.
- Message key **không tự bảo đảm SMTP gửi đúng một lần**; crash giữa SMTP submission và cập nhật DB vẫn có thể tạo duplicate.

Thiết kế message key đúng giúp hệ thống Spring Mail phân biệt **yêu cầu mới** với **lần xử lý lặp lại của yêu cầu cũ**. Khi key ổn định, scope rõ ràng và được lưu cùng job bền vững, ứng dụng có cơ sở để retry, quan sát trạng thái và giảm email trùng mà không vô tình bỏ sót những thông báo thật sự cần gửi.

### Tài liệu tham khảo

- **Spring Framework Reference — Transaction Management:** `@Transactional` và transaction boundaries.
- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper` và hành vi gửi mail.
- **Spring JDBC — NamedParameterJdbcTemplate:** câu lệnh tham số hóa và truy cập database.
- **Transactional Outbox Pattern:** lưu thay đổi nghiệp vụ và yêu cầu xử lý ngoài hệ thống trong cùng transaction.
- **RFC 5322 — Internet Message Format:** header `Message-ID` và định danh email message.
- **RFC 5321 — Simple Mail Transfer Protocol:** SMTP submission, phản hồi và giới hạn giao nhận.
