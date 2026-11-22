# Bảo đảm không gửi trùng do một thao tác được gọi lại

Một thao tác gửi email có thể được gọi nhiều lần vì người dùng nhấn nút hai lần, trình duyệt gửi lại request sau timeout, gateway retry, ứng dụng xử lý lại message trong queue hoặc worker khởi động lại sau sự cố. Nếu mỗi lần gọi đều tạo một email mới, người nhận có thể nhận nhiều thư giống nhau dù người dùng chỉ thực hiện một hành động nghiệp vụ.

Trong **Spring Framework Mail**, **JavaMailSender** gửi message qua SMTP, còn **MimeMessageHelper** chuẩn bị nội dung MIME. Hai API này không tự biết hai lời gọi **send(...)** có đại diện cho cùng một thao tác hay không. Muốn tránh tạo email trùng, ứng dụng cần quản lý **idempotency** ở tầng nghiệp vụ và lưu trạng thái gửi một cách bền vững.

Điểm cần hiểu rõ: ứng dụng có thể bảo đảm một thao tác được gọi lại không tạo thêm nhiều yêu cầu gửi trong database/queue. Nhưng SMTP không cung cấp cơ chế idempotency phổ quát để bảo đảm tuyệt đối một email chỉ được giao đúng một lần trong mọi tình huống lỗi mạng. Bài học sẽ phân biệt hai phạm vi đó và trình bày cách thiết kế phù hợp.

## 1. Idempotency là gì?

Một thao tác được gọi là **idempotent** khi thực hiện lại cùng thao tác với cùng định danh không làm phát sinh thêm hiệu ứng nghiệp vụ ngoài kết quả của lần đầu.

Ví dụ, người dùng bấm “Gửi hóa đơn” cho đơn hàng ORD-2026-001. Trình duyệt gửi request nhưng không nhận được phản hồi vì mạng chậm. Người dùng bấm lại. Nếu server tạo hai notification khác nhau, hai email hóa đơn có thể được gửi. Nếu server nhận diện đây là cùng một thao tác, request thứ hai có thể trả lại kết quả của request đầu mà không tạo thêm notification.

```text
Lần gọi đầu:
  POST /orders/ORD-2026-001/send-invoice
  Idempotency-Key: 8f...a2
          |
          v
  Tạo notification N-123
          |
          v
  Đưa N-123 vào hàng đợi gửi

Lần gọi lại:
  POST /orders/ORD-2026-001/send-invoice
  Idempotency-Key: 8f...a2
          |
          v
  Tìm thấy thao tác đã được ghi nhận
          |
          v
  Trả lại notification N-123
  Không tạo notification N-124
```

Idempotency không có nghĩa là mọi email gửi cho cùng một địa chỉ và cùng subject đều bị gộp thành một. Hai lần gửi có thể là hai hành động hợp lệ khác nhau. Ứng dụng cần định nghĩa **đâu là một thao tác nghiệp vụ duy nhất** và cấp định danh cho thao tác đó.

## 2. Phân biệt thao tác bị gọi lại và yêu cầu gửi lại có chủ đích

Hai trường hợp nhìn bên ngoài có thể giống nhau nhưng ý nghĩa khác nhau:

| Trường hợp | Ý nghĩa | Hành vi mong muốn |
| --- | --- | --- |
| Browser retry do timeout | Cùng một thao tác chưa nhận được phản hồi | Trả lại kết quả cũ, không tạo thêm notification |
| Người dùng double-click | Cùng một thao tác bị gửi hai request gần như đồng thời | Chỉ ghi nhận một lần |
| API gateway retry | Hạ tầng gửi lại cùng request | Nhận diện cùng idempotency key |
| Worker xử lý lại outbox event | Cùng notification được xử lý lại sau lỗi | Dùng notification ID ổn định và chính sách retry |
| Người dùng bấm “Gửi lại email” sau khi email đã được gửi | Một hành động mới có chủ đích | Tạo một resend operation mới theo nghiệp vụ |
| Người dùng yêu cầu gửi hóa đơn cho một lần mua khác | Sự kiện nghiệp vụ khác | Tạo notification mới |

**Không dùng recipient + subject làm idempotency key.** Một người có thể nhận nhiều hóa đơn, nhiều thông báo hoặc nhiều bản cập nhật hợp lệ với cùng subject.

Ví dụ, hai lần gửi hóa đơn cho cùng một đơn hàng có thể được coi là:

- Cùng một thao tác nếu request thứ hai chỉ là retry của thao tác đầu.
- Một thao tác mới nếu người dùng chủ động chọn “Gửi lại bản sao” sau đó.

Quy tắc này phải được thể hiện trong API và mô hình dữ liệu, thay vì suy đoán từ nội dung email.

## 3. Idempotency key là gì?

**Idempotency key** là một định danh do client hoặc server tạo để nhận diện một thao tác logic. Khi request được retry, client gửi lại **cùng key**. Server dùng key đó để tìm kết quả đã ghi nhận.

Ví dụ HTTP request:

```http
POST /api/orders/ORD-2026-001/send-invoice HTTP/1.1
Idempotency-Key: 8f6e4a10-2e58-4b82-9b3c-6b2a7c6f12a2
Content-Type: application/json

{
  "recipient": "customer@example.net"
}
```

Nếu request bị retry, client gửi lại đúng giá trị Idempotency-Key. Server có thể trả về cùng notification ID và trạng thái hiện tại.

### Quy tắc chọn key

- Key phải được tạo cho **một thao tác logic**, không phải cho mỗi lần thử HTTP.
- Key nên có độ ngẫu nhiên đủ mạnh, ví dụ UUID.
- Key cần được giới hạn theo tenant, người gọi hoặc loại operation.
- Không dùng email address, tên khách hàng hay dữ liệu cá nhân làm key.
- Không dùng key làm cơ chế xác thực hoặc phân quyền.
- Client phải lưu key đủ lâu để gửi lại khi timeout; không tạo UUID mới cho mỗi lần retry.

Một scope có thể gồm:

```text
tenant_id + operation_name + idempotency_key
```

Nhờ vậy, cùng một chuỗi key ở hai tenant hoặc hai loại operation khác nhau không nhất thiết bị coi là cùng thao tác.

### Key và request payload phải nhất quán

Giả sử client gửi:

```text
Idempotency-Key: abc-123
recipient = customer-a@example.net
```

Sau đó lại dùng key abc-123 nhưng đổi recipient thành customer-b@example.net. Đây không còn là retry của cùng request. Server nên phát hiện sự khác nhau và trả lỗi conflict, thay vì âm thầm trả kết quả cũ hoặc gửi sang người nhận mới.

Một cách thực hiện là lưu **request hash** cùng key:

```text
scope: tenant-01 / send-invoice
key: abc-123
request_hash: SHA-256(canonical request)
notification_id: N-123
```

Khi key đã tồn tại:

- Hash giống nhau: trả lại kết quả của thao tác đã ghi nhận.
- Hash khác nhau: từ chối request vì key đã được dùng cho payload khác.

Hash phải được tính từ dữ liệu đã chuẩn hóa theo một quy tắc ổn định. Không hash trực tiếp một JSON object có thứ tự field không xác định rồi coi mọi serialization đều tương đương.

## 4. Hai lớp chống trùng cần phối hợp

Một hệ thống gửi email thường cần hai loại định danh:

1. **Request idempotency key:** nhận diện request từ client bị retry.
2. **Business key:** nhận diện thông báo tương ứng với một sự kiện nghiệp vụ, ví dụ “hóa đơn của đơn hàng X đã được phát hành”.

Hai lớp này giải quyết những nguồn trùng khác nhau:

| Lớp | Ngăn trường hợp nào? | Ví dụ |
| --- | --- | --- |
| Request idempotency key | Client gửi lại cùng request | Double-click hoặc HTTP timeout |
| Business key | Hai luồng backend cùng tạo một thông báo cho một sự kiện | Listener và scheduled job cùng xử lý một order event |
| Notification ID | Worker retry cùng một notification | Worker xử lý lại outbox row |
| Provider idempotency key (nếu API hỗ trợ) | Provider nhận lại cùng yêu cầu gửi | Gửi lại API request sau timeout |

Không phải mọi hệ thống đều cần cả bốn lớp. Nhưng chỉ có idempotency key ở HTTP layer vẫn chưa đủ nếu backend có thể tạo cùng một notification từ hai event consumer hoặc hai job khác nhau.

### Ví dụ business key

Một key có thể được tạo từ:

```text
notification_type = INVOICE_READY
business_event_id = order-123-invoice-issued-v1
```

Database có thể đặt unique constraint trên cặp (notification_type, business_event_id). Nhờ đó, hai worker cùng cố tạo email xác nhận hóa đơn cho cùng một sự kiện chỉ có thể ghi nhận một notification.

Nếu nghiệp vụ cho phép gửi lại bản sao, hãy biểu diễn đó là một operation mới có định danh riêng, ví dụ resend_request_id, thay vì bỏ unique constraint hoặc thay đổi key một cách tùy tiện.

## 5. Không dựa vào bộ nhớ của một instance ứng dụng

Một cách làm không an toàn là lưu các key đã xử lý trong HashSet hoặc ConcurrentHashMap:

```java
private final Set<String> processedKeys = ConcurrentHashMap.newKeySet();

public void send(String key, String recipient) {
    if (!processedKeys.add(key)) {
        return;
    }

    mailSender.send(buildMessage(recipient));
}
```

Cách này có thể tránh gọi lặp trong cùng một JVM khi chỉ có một instance, nhưng không đáp ứng yêu cầu của ứng dụng chạy thực tế:

- Khi process restart, Set bị mất.
- Nhiều instance có bộ nhớ riêng nên cùng key có thể được xử lý ở cả hai instance.
- Hai thread có thể cùng vượt qua bước kiểm tra nếu logic check/insert không nguyên tử.
- Không có lịch sử bền vững để biết email đã được xử lý hay chưa.
- Không thể phục hồi trạng thái sau crash hoặc triển khai lại.

Idempotency cần được lưu ở nơi các instance cùng nhìn thấy và có cơ chế **atomicity**, thường là database với unique constraint/transaction hoặc một kho dữ liệu phân tán có thao tác nguyên tử phù hợp.

## 6. Lưu idempotency key và trạng thái trong database

Một schema minh họa:

```sql
CREATE TABLE mail_idempotency (
    id                  UUID PRIMARY KEY,
    tenant_id           VARCHAR(100) NOT NULL,
    operation_name      VARCHAR(100) NOT NULL,
    idempotency_key     VARCHAR(150) NOT NULL,
    request_hash        VARCHAR(64) NOT NULL,
    notification_id     UUID NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at          TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_mail_idempotency_scope
        UNIQUE (tenant_id, operation_name, idempotency_key)
);

CREATE TABLE mail_notification (
    id                  UUID PRIMARY KEY,
    notification_type   VARCHAR(100) NOT NULL,
    business_event_id   VARCHAR(200) NOT NULL,
    recipient           VARCHAR(320) NOT NULL,
    template_key        VARCHAR(150) NOT NULL,
    template_version    INTEGER NOT NULL,
    status              VARCHAR(30) NOT NULL,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMP WITH TIME ZONE,
    lease_until         TIMESTAMP WITH TIME ZONE,
    provider_message_id VARCHAR(300),
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    submitted_at        TIMESTAMP WITH TIME ZONE,
    last_error          TEXT,
    CONSTRAINT uq_mail_business_event
        UNIQUE (notification_type, business_event_id)
);
```

Đây là schema khởi đầu, cần điều chỉnh kiểu timestamp, giới hạn dữ liệu và index theo database thực tế. Nếu lưu payload hoặc mail model, cần xác định dữ liệu nào được phép lưu, thời gian retention và quyền truy cập.

Ý nghĩa các cột:

- tenant_id, operation_name, idempotency_key: phạm vi của thao tác.
- request_hash: phát hiện key bị tái sử dụng với request khác.
- notification_id: liên kết request với notification đã tạo.
- business_event_id: ngăn backend tạo hai notification cho cùng sự kiện.
- status: trạng thái xử lý hiện tại.
- attempt_count, next_attempt_at: quản lý retry.
- lease_until: thời điểm hết quyền xử lý tạm thời của worker.
- provider_message_id: ID provider trả về nếu có.
- submitted_at: thời điểm SMTP/provider đã chấp nhận message theo kết quả quan sát được.

### Unique constraint mới là hàng rào cuối

Đoạn code kiểu:

```java
if (!repository.existsByIdempotencyKey(key)) {
    repository.save(record);
}
```

không đủ an toàn khi có hai request đồng thời:

```text
Request A: exists? -> false
Request B: exists? -> false
Request A: insert
Request B: insert
```

Nếu database không có unique constraint, hai bản ghi có thể cùng tồn tại. Hãy để database bảo vệ uniqueness và dùng thao tác insert/claim nguyên tử.

## 7. Xử lý request lặp một cách nguyên tử

Luồng xử lý cần đảm bảo:

1. Kiểm tra key đã được ghi nhận chưa.
2. Nếu đã có, so sánh request hash và trả lại kết quả cũ.
3. Nếu chưa có, tạo notification và ghi key trong cùng transaction.
4. Chỉ commit khi cả hai bản ghi đã được lưu thành công.

Pseudocode:

```java
@Transactional
public NotificationReceipt requestInvoiceEmail(
        String tenantId,
        String idempotencyKey,
        InvoiceMailCommand command
) {
    String requestHash = requestHasher.hash(command);

    IdempotencyClaim claim = idempotencyRepository.claim(
            tenantId,
            "SEND_INVOICE",
            idempotencyKey,
            requestHash
    );

    if (!claim.created()) {
        if (!claim.requestHash().equals(requestHash)) {
            throw new IdempotencyConflictException(
                    "Key was already used with another request"
            );
        }
        return notificationRepository.getReceipt(
                claim.notificationId()
        );
    }

    UUID notificationId = claim.notificationId();
    notificationRepository.insertPending(
            notificationId,
            command
    );

    return new NotificationReceipt(notificationId, "PENDING");
}
```

Đây là cấu trúc minh họa; claim(...) cần được triển khai bằng một thao tác database nguyên tử. Không được thực hiện kiểu SELECT rồi INSERT mà không có unique constraint.

### Ví dụ thao tác atomic với PostgreSQL

Một cách thường dùng là INSERT ... ON CONFLICT DO NOTHING:

```sql
INSERT INTO mail_idempotency (
    id,
    tenant_id,
    operation_name,
    idempotency_key,
    request_hash,
    notification_id,
    created_at
)
VALUES (
    :id,
    :tenantId,
    :operationName,
    :idempotencyKey,
    :requestHash,
    :notificationId,
    CURRENT_TIMESTAMP
)
ON CONFLICT (
    tenant_id,
    operation_name,
    idempotency_key
)
DO NOTHING;
```

Sau đó đọc bản ghi theo scope và key:

```sql
SELECT request_hash, notification_id
FROM mail_idempotency
WHERE tenant_id = :tenantId
  AND operation_name = :operationName
  AND idempotency_key = :idempotencyKey;
```

Nếu insert đã tạo row, request hiện tại sở hữu thao tác mới. Nếu row đã tồn tại, request hiện tại đọc kết quả cũ và so sánh hash. Cả claim và insert notification phải nằm trong cùng transaction; nếu tạo notification thất bại, claim cũng phải rollback.

Với database khác, dùng cơ chế upsert/unique constraint tương đương. Cần kiểm tra semantics transaction và isolation level của database đang sử dụng.

## 8. Transactional outbox: ghi nhận yêu cầu gửi cùng nghiệp vụ

Một lỗi khác xảy ra khi ứng dụng cập nhật database và gửi email trong cùng một method:

```java
@Transactional
public void confirmOrder(Order order) {
    order.confirm();
    orderRepository.save(order);

    mailSender.send(buildConfirmationMessage(order));
}
```

Gửi SMTP là một side effect bên ngoài database. Transaction database có thể rollback, nhưng SMTP server không thể rollback email đã nhận. Ví dụ:

1. SMTP đã nhận email.
2. Sau đó transaction database thất bại.
3. Đơn hàng rollback về trạng thái cũ nhưng email xác nhận đã được gửi.

Hoặc ngược lại, database commit nhưng lỗi SMTP khiến request không biết phải xử lý tiếp thế nào.

**Transactional outbox** giải quyết vấn đề ghi nhận yêu cầu gửi:

```text
Một transaction database:
  - cập nhật trạng thái đơn hàng
  - tạo notification PENDING
  - tạo outbox event
          |
          v
       COMMIT
          |
          v
Worker đọc outbox
          |
          v
Gửi email qua JavaMailSender
          |
          v
Cập nhật trạng thái notification
```

Điểm quan trọng là trạng thái nghiệp vụ và yêu cầu gửi được ghi **trong cùng transaction database**. Worker chỉ xử lý những yêu cầu đã commit.

### Ví dụ bảng outbox

```sql
CREATE TABLE mail_outbox (
    id              UUID PRIMARY KEY,
    notification_id UUID NOT NULL UNIQUE,
    event_type      VARCHAR(100) NOT NULL,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at    TIMESTAMP WITH TIME ZONE
);
```

Ví dụ service nghiệp vụ:

```java
@Transactional
public UUID confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    UUID notificationId = UUID.randomUUID();

    mailNotificationRepository.insertPending(
            notificationId,
            "ORDER_CONFIRMED",
            order.getId().toString(),
            order.getCustomerEmail()
    );

    outboxRepository.insert(
            UUID.randomUUID(),
            notificationId,
            "MAIL_NOTIFICATION_CREATED"
    );

    return notificationId;
}
```

Đây là ví dụ rút gọn. Cần có unique constraint theo business event để hai lần gọi confirmOrder hoặc hai listener không tạo cùng notification. Nếu thao tác xác nhận đơn hàng vốn đã idempotent, trạng thái đơn hàng và notification cần được cập nhật theo cùng quy tắc.

### Outbox không tự bảo đảm email chỉ gửi một lần

Outbox bảo đảm yêu cầu gửi không bị mất khi transaction nghiệp vụ commit. Worker thường xử lý theo mô hình **at-least-once**: một event có thể được đọc lại nếu worker chết hoặc mất xác nhận. Vì vậy, worker vẫn cần notification ID ổn định, cơ chế claim và cách xử lý kết quả gửi.

Outbox giải quyết atomicity giữa database và việc ghi nhận công việc; nó không biến SMTP thành một hệ thống exactly-once.

## 9. State machine cho notification

Không nên chỉ có một cột boolean sent. Cần trạng thái đủ để phân biệt đang chờ, đang gửi, đã được chấp nhận, lỗi có thể retry và kết quả chưa rõ.

Một state machine minh họa:

```text
PENDING
   |
   v
PROCESSING
   |
   +---- SMTP/provider chấp nhận ----> SUBMITTED
   |
   +---- Lỗi tạm thời đã biết -------> RETRY_WAIT
   |
   +---- Lỗi vĩnh viễn đã biết -----> FAILED
   |
   +---- Kết quả mơ hồ -------------> UNKNOWN

RETRY_WAIT
   |
   | đến next_attempt_at
   v
PROCESSING

UNKNOWN
   |
   +---- Provider xác nhận đã nhận -> SUBMITTED
   |
   +---- Có bằng chứng chưa nhận ---> RETRY_WAIT
   |
   +---- Không xác định được -------> xử lý theo policy
```

Ý nghĩa:

| Trạng thái | Mô tả |
| --- | --- |
| PENDING | Notification đã được ghi nhận, chưa được worker xử lý |
| PROCESSING | Một worker đang giữ quyền xử lý tạm thời |
| RETRY_WAIT | Lỗi có thể retry, chờ đến thời điểm tiếp theo |
| SUBMITTED | SMTP/provider đã chấp nhận yêu cầu gửi theo kết quả quan sát được |
| FAILED | Lỗi vĩnh viễn hoặc đã hết chính sách retry |
| UNKNOWN | Không biết chắc SMTP/provider đã nhận message hay chưa |

Không nên đặt tên SUBMITTED thành DELIVERED nếu chỉ nhận được phản hồi SMTP thành công. SMTP server chấp nhận message không chứng minh thư đã tới Inbox; việc giao cuối cùng, bounce và spam filtering là các trạng thái khác.

### Vì sao cần trạng thái UNKNOWN?

Giả sử worker gọi SMTP và connection bị timeout. Nếu timeout xảy ra trước khi message được truyền, có thể retry an toàn. Nhưng nếu SMTP server đã nhận toàn bộ message và phản hồi bị mất trên đường về, worker không biết message đã được chấp nhận hay chưa.

Nếu worker tự động retry mọi timeout, có nguy cơ gửi trùng. Nếu worker đánh dấu thất bại vĩnh viễn, email có thể bị mất. UNKNOWN thể hiện sự thật rằng hệ thống chưa đủ bằng chứng để chọn một trong hai kết quả.

## 10. Claim notification để nhiều worker không gửi cùng lúc

Khi chạy nhiều instance, hai worker có thể cùng đọc một notification PENDING. Cần cơ chế claim nguyên tử.

Một cách phổ biến với PostgreSQL là SELECT ... FOR UPDATE SKIP LOCKED:

```sql
BEGIN;

SELECT id
FROM mail_notification
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND (next_attempt_at IS NULL
       OR next_attempt_at <= CURRENT_TIMESTAMP)
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 20;

-- Cập nhật các row đã chọn thành PROCESSING
-- và đặt lease_until theo chính sách worker.

COMMIT;
```

Worker chỉ xử lý những row mà nó đã claim. SKIP LOCKED cho phép các worker khác lấy những row chưa bị khóa thay vì cùng lấy một notification.

Trong triển khai thật, cần cập nhật status và lease trong transaction, rồi trả về các row đã claim. Không giữ transaction database mở trong lúc chờ SMTP network.

### Lease có tác dụng gì?

Nếu worker chết, trạng thái PROCESSING không thể tồn tại mãi. Một lease cho biết quyền xử lý tạm thời hết hạn khi nào:

```text
notification N-123
status      = PROCESSING
worker_id   = worker-2
lease_until = 10:05:00Z
```

Sau thời điểm lease hết hạn, hệ thống có thể xem xét khôi phục công việc. Nhưng **không nên mặc định lease hết hạn đồng nghĩa email chắc chắn chưa được gửi**. Worker có thể đã gửi thành công rồi chết trước khi cập nhật database. Trường hợp này cần chuyển sang UNKNOWN hoặc áp dụng chính sách reconcile/retry có cân nhắc rủi ro trùng.

### Không giữ khóa database trong lúc gọi SMTP

SMTP có thể mất nhiều giây hoặc timeout. Nếu giữ row lock trong suốt thời gian gửi:

- Transaction kéo dài.
- Các worker khác phải chờ.
- Database connection bị chiếm.
- Deadlock hoặc lock contention có thể tăng.

Nên claim và commit trước, gửi bên ngoài transaction, rồi mở transaction ngắn để ghi kết quả. Cần một lease/claim token để ngăn worker cũ ghi đè kết quả sau khi quyền xử lý đã được chuyển.

## 11. Ví dụ worker gửi email trong Spring

Worker cần tách ba bước: claim, gửi và ghi kết quả.

### 11.1. Claim batch

```java
@Component
public class MailOutboxWorker {

    private final MailNotificationRepository repository;
    private final JavaMailSender mailSender;

    public MailOutboxWorker(
            MailNotificationRepository repository,
            JavaMailSender mailSender
    ) {
        this.repository = repository;
        this.mailSender = mailSender;
    }

    @Scheduled(fixedDelayString = "1000")
    public void processBatch() {
        List<ClaimedNotification> batch =
                repository.claimNextBatch(20);

        for (ClaimedNotification item : batch) {
            processOne(item);
        }
    }
}
```

claimNextBatch(...) phải thực hiện transaction claim nguyên tử và trả về một claim token/lease phù hợp. Annotation SCHEDULED chỉ kích hoạt polling; nó không tự bảo đảm một notification chỉ được một instance xử lý.

### 11.2. Gửi và phân loại kết quả

```java
private void processOne(ClaimedNotification item) {
    try {
        MimeMessage message = buildMessage(item);
        mailSender.send(message);

        repository.markSubmitted(
                item.notificationId(),
                item.claimToken()
        );
    } catch (MailAuthenticationException ex) {
        repository.markFailed(
                item.notificationId(),
                item.claimToken(),
                "SMTP authentication failed"
        );
    } catch (MailSendException ex) {
        repository.recordSendFailure(
                item.notificationId(),
                item.claimToken(),
                classify(ex)
        );
    } catch (MailException ex) {
        repository.recordSendFailure(
                item.notificationId(),
                item.claimToken(),
                classify(ex)
        );
    }
}
```

Đây là khung minh họa. classify(ex) cần dựa trên nguyên nhân và giai đoạn thất bại có thể xác định; không được coi mọi MailSendException hoặc MailException là retry an toàn. Nếu không biết SMTP server đã nhận message hay chưa, ghi nhận UNKNOWN để reconcile theo policy.

Không nên bắt exception rồi bỏ qua, vì notification có thể bị giữ ở PROCESSING hoặc không được retry đúng cách. Cũng không nên ghi SUBMITTED trước khi gọi sender: nếu process chết trước khi gửi, email sẽ bị mất nhưng database lại báo đã gửi.

## 12. Giới hạn của exactly-once khi gửi qua SMTP

Đây là giới hạn quan trọng nhất khi thiết kế chống gửi trùng.

Xét hai thao tác:

1. Gửi message tới SMTP server.
2. Cập nhật database thành SUBMITTED.

Hai thao tác thuộc hai hệ thống khác nhau. Không có transaction chung bảo đảm cả hai cùng commit hoặc cùng rollback.

### Cửa sổ lỗi gây kết quả mơ hồ

```text
Worker                       SMTP server              Database
  |                              |                       |
  |------ DATA / message ------->|                       |
  |                              |                       |
  |<----- 250 accepted ----------|                       |
  |                              |                       |
  X process crash                |                       |
  |                              |                       |
  |                              |                 status vẫn PROCESSING
  |                              |                       |
  |---- restart / retry -------->|                       |
  |                              |                       |
  |                    Có thể nhận email lần thứ hai    |
```

Nếu process chết sau khi SMTP chấp nhận message nhưng trước khi database ghi SUBMITTED, lần chạy tiếp theo có thể gửi lại. Database chỉ biết lần cập nhật cuối cùng chưa xảy ra; nó không thể tự suy ra SMTP đã nhận message.

### Vì sao không đánh dấu SENT trước khi gửi?

Nếu ghi trạng thái đã gửi trước:

```text
Database: status = SUBMITTED
       |
       X process crash trước SMTP
       |
       v
Không có email được gửi,
nhưng hệ thống không còn retry
```

Đây là cách chuyển nguy cơ duplicate thành nguy cơ mất email. Không có thứ tự đơn giản nào giải quyết được atomicity giữa database và SMTP.

### Cách diễn đạt chính xác về bảo đảm

Với SMTP thuần, hệ thống thường có thể đạt:

- **Exactly-once acceptance trong database:** một logical request chỉ tạo một notification record.
- **At-least-once processing:** worker có thể thử xử lý lại notification nếu gặp lỗi.
- **Best-effort duplicate reduction:** giảm nguy cơ gửi trùng bằng state, claim, stable IDs và reconciliation.

Không nên hứa **exactly-once delivery** nếu provider/transport không hỗ trợ idempotency hoặc cơ chế deduplication có hợp đồng rõ ràng.

## 13. Nếu nhà cung cấp có API idempotency

Một số email provider cung cấp HTTP API và có thể hỗ trợ idempotency key theo hợp đồng riêng. Nếu provider hỗ trợ:

1. Tạo một provider key ổn định cho notification.
2. Gửi lại cùng key khi retry cùng notification.
3. Không tạo key mới cho từng attempt.
4. Đọc chính sách provider về thời gian lưu key, phạm vi uniqueness và payload mismatch.
5. Lưu provider message ID và phản hồi.

Ví dụ khái niệm:

```http
POST /provider/messages
Idempotency-Key: notification-7f6b...
Content-Type: application/json

{
  "to": ["customer@example.net"],
  "subject": "Hóa đơn của bạn",
  "html": "<p>...</p>"
}
```

Đây là ví dụ minh họa giao thức, không phải endpoint chung của mọi provider. Phải dùng đúng tài liệu API của nhà cung cấp đang chọn.

### JavaMailSender và provider API không giống nhau

JavaMailSender thường gửi qua SMTP. API SMTP không có header idempotency tiêu chuẩn phổ quát tương đương các API HTTP provider. Nếu cần provider-level deduplication, có thể phải dùng API chính thức của provider thay vì SMTP, hoặc chấp nhận giới hạn của SMTP.

Không thêm một header tùy ý tên Idempotency-Key vào MIME message rồi kỳ vọng mọi SMTP server tự deduplicate. Server chỉ có thể xử lý header đó nếu nhà cung cấp định nghĩa rõ hành vi hỗ trợ.

## 14. Message-ID có ngăn gửi trùng không?

Không. Message-ID là định danh của email message theo chuẩn email. Nó hữu ích cho việc theo dõi, tham chiếu và một số cơ chế threading, nhưng không phải idempotency key được mọi SMTP server hoặc mailbox bắt buộc dùng để loại bỏ thư trùng.

Ví dụ:

```java
message.setHeader(
        "Message-ID",
        "<notification-123@mail.example.org>"
);
```

Nếu gửi hai lần cùng một Message-ID, server hoặc client có thể vẫn chấp nhận và hiển thị hai message. Một số hệ thống có thể gộp hoặc xử lý khác, nhưng ứng dụng không được dựa vào hành vi không được bảo đảm đó.

Message-ID ổn định có thể hỗ trợ correlation khi điều tra; **database idempotency và provider idempotency** mới là cơ chế chống xử lý lặp có chủ đích.

## 15. Phân loại lỗi trước khi retry

Không phải lỗi gửi email nào cũng có thể retry an toàn.

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Lỗi trước khi kết nối/gửi dữ liệu | DNS lookup fail, không mở được socket | Thường có thể retry với backoff |
| SMTP từ chối rõ ràng trước khi nhận message | Authentication fail, sender/recipient bị từ chối | Sửa cấu hình hoặc dữ liệu; không retry liên tục |
| SMTP phản hồi tạm thời rõ ràng | Một số phản hồi 4xx | Retry theo policy và thời gian chờ |
| SMTP phản hồi thành công | Server trả phản hồi chấp nhận message | Ghi SUBMITTED; theo dõi delivery riêng |
| Connection mất sau khi truyền message, trước khi nhận phản hồi cuối | Timeout sau DATA | Kết quả mơ hồ; UNKNOWN và reconcile |
| Database lỗi sau khi SMTP đã chấp nhận | Không ghi được trạng thái SUBMITTED | Reconcile; không tự coi là chưa gửi |
| Template/model lỗi | Thiếu biến bắt buộc, template không tồn tại | Sửa dữ liệu/template; không retry SMTP |
| Recipient không hợp lệ | Địa chỉ sai cú pháp hoặc bị từ chối vĩnh viễn | Sửa dữ liệu hoặc đánh dấu lỗi cuối |

MailException của Spring là lớp exception bao quát; không phải mọi subclass đều cho biết chắc chắn message đã được server chấp nhận hay chưa. Việc phân loại cần dựa trên thông tin transport/provider có thể cung cấp.

### Exponential backoff

Với lỗi tạm thời đã biết, có thể tăng dần khoảng cách giữa các lần retry:

```text
attempt 1: chờ 10 giây
attempt 2: chờ 30 giây
attempt 3: chờ 2 phút
attempt 4: chờ 10 phút
attempt 5: chờ 30 phút
```

Đây chỉ là ví dụ lịch retry; hệ thống thực tế cần giới hạn số lần thử, thêm jitter để tránh nhiều worker retry cùng lúc và tôn trọng hướng dẫn của SMTP/provider.

Không retry vô hạn. Khi vượt giới hạn, đưa notification sang FAILED hoặc dead-letter/review queue tùy nghiệp vụ. Với UNKNOWN, chính sách phải xét rủi ro gửi trùng và khả năng truy vấn trạng thái provider.

## 16. Xử lý trạng thái UNKNOWN và reconciliation

Khi worker không biết chắc message đã được chấp nhận hay chưa, có một số cách:

### Cách 1 — Tra cứu provider

Nếu provider cung cấp API hoặc event log có thể tra theo notification ID/provider message ID, hãy dùng dữ liệu đó để xác định message đã được chấp nhận/giao chưa.

### Cách 2 — Provider webhook/event

Một số dịch vụ gửi email phát webhook cho trạng thái accepted, delivered, bounced hoặc deferred. Có thể lưu provider event theo notification ID và cập nhật trạng thái. Webhook cũng có thể được gửi lặp, nên endpoint webhook phải idempotent riêng.

### Cách 3 — Đưa vào hàng đợi reconciliation

Nếu không thể tự xác định, giữ UNKNOWN, ghi attempt metadata và đưa vào quy trình xử lý riêng. Tùy mức độ quan trọng, có thể:

- Chờ thêm provider event.
- Cho nhân viên vận hành xem lịch sử.
- Retry sau một khoảng thời gian với cảnh báo rằng có nguy cơ trùng.
- Không retry tự động nếu email mang tính pháp lý hoặc có thể gây tác động lớn.

Không xóa notification UNKNOWN hoặc đổi thành FAILED chỉ để worker lấy lại. Trạng thái cần phản ánh mức độ chắc chắn của hệ thống.

## 17. Idempotency ở API endpoint

Ví dụ controller:

```java
@RestController
@RequestMapping("/api/orders")
public class InvoiceMailController {

    private final InvoiceMailRequestService requestService;

    public InvoiceMailController(
            InvoiceMailRequestService requestService
    ) {
        this.requestService = requestService;
    }

    @PostMapping("/{orderId}/send-invoice")
    public ResponseEntity<NotificationReceipt> sendInvoice(
            @PathVariable UUID orderId,
            @RequestHeader("Idempotency-Key") String key,
            @AuthenticationPrincipal AppUser user
    ) {
        NotificationReceipt receipt =
                requestService.requestInvoice(
                        user.tenantId(),
                        user.id(),
                        orderId,
                        key
                );

        return ResponseEntity.accepted().body(receipt);
    }
}
```

Controller chỉ nhận key và chuyển việc xử lý sang service. Service phải:

- Xác thực người dùng có quyền yêu cầu gửi hóa đơn cho order.
- Kiểm tra key có định dạng và độ dài hợp lệ.
- Tạo request hash từ thao tác đã chuẩn hóa.
- Claim key trong database bằng unique constraint.
- Tạo notification/outbox trong cùng transaction.
- Trả cùng notification ID khi nhận lại cùng request.

Không để client truyền một notification ID tùy ý rồi server tin rằng request đã được xử lý. ID và trạng thái phải được xác định từ dữ liệu lưu trữ có thẩm quyền.

### Phản hồi HTTP cho request lặp

Một quy ước có thể là:

| Tình huống | Phản hồi gợi ý |
| --- | --- |
| Key mới, request hợp lệ, notification đã được ghi nhận | 202 Accepted với notification ID |
| Cùng key, cùng payload, thao tác đang chờ/đang xử lý | Trả lại notification ID và trạng thái hiện tại |
| Cùng key, cùng payload, đã xử lý | Trả lại kết quả đã lưu |
| Cùng key nhưng payload khác | 409 Conflict |
| Thiếu key trong endpoint yêu cầu idempotency | 400 Bad Request |
| Người dùng không có quyền với order/recipient | 403 hoặc 404 theo policy |

HTTP status cụ thể tùy API contract. Điều quan trọng là request lặp không tạo notification mới và client có thể hiểu trạng thái đã được ghi nhận.

## 18. Idempotency key ở client

Client cần tạo key **một lần cho thao tác**, rồi giữ lại nếu phải retry:

```javascript
const idempotencyKey = crypto.randomUUID();

async function submitInvoiceRequest(orderId) {
  return fetch("/api/orders/" + orderId + "/send-invoice", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey
    }
  });
}
```

Đây là ví dụ JavaScript ở phía client. Nếu request timeout, gọi lại submitInvoiceRequest với **cùng idempotencyKey**. Nếu người dùng bắt đầu một thao tác gửi lại có chủ đích, tạo key mới theo operation mới.

Không tạo key bên trong mỗi lần gọi hàm nếu hàm đó được dùng để retry:

```javascript
// Không phù hợp: mỗi lần retry lại tạo key mới.
async function retrySend(orderId) {
  const key = crypto.randomUUID();
  // gửi request với key mới
}
```

Nếu key bị tạo mới cho mỗi lần thử, server không có căn cứ nhận diện các request là cùng thao tác.

## 19. Phân biệt idempotency key và business event key

Hãy xét hai tình huống:

**Tình huống A:** người dùng gọi endpoint hai lần do timeout. Hai request có cùng Idempotency-Key. Đây là cùng một thao tác từ client.

**Tình huống B:** hai consumer nhận cùng event InvoiceIssued do message broker giao lặp. Có thể mỗi consumer tạo một request key khác nhau hoặc không có HTTP request nào. Lúc này cần business event key ổn định.

Một business key có thể là:

```text
INVOICE_READY:order-123:invoice-version-1
```

Database unique constraint:

```sql
CREATE UNIQUE INDEX uq_invoice_notification_event
ON mail_notification (notification_type, business_event_id);
```

Nếu hai consumer cùng tạo notification cho cùng event, chỉ một insert thành công. Consumer còn lại đọc notification đã tồn tại và không tạo bản thứ hai.

### Có nên dùng cả hai?

Trong hệ thống có cả HTTP command và event-driven workflow, thường nên có:

- Request idempotency key cho request lặp từ client.
- Business event key cho notification phát sinh từ sự kiện nghiệp vụ.
- Notification ID cho worker retry.

Mỗi key có scope riêng. Không nên dùng một UUID tùy ý thay thế tất cả các định danh.

## 20. Gửi đồng bộ và gửi bất đồng bộ

### Gửi đồng bộ trong HTTP request

Luồng:

```text
HTTP request
   |
   v
Idempotency check
   |
   v
Build MimeMessage
   |
   v
JavaMailSender.send
   |
   v
HTTP response
```

Ưu điểm là code đơn giản và người gọi có thể nhận kết quả gửi trực tiếp. Hạn chế:

- Request giữ connection trong lúc SMTP xử lý.
- Timeout ở client/gateway có thể xảy ra dù SMTP đã nhận message.
- Retry ở HTTP layer dễ tạo duplicate nếu không có idempotency record bền vững.
- Khó xử lý queue, retry, rate limit và lỗi tạm thời.

Nếu vẫn gửi đồng bộ, hãy ghi nhận thao tác và trạng thái bền vững trước khi gọi SMTP, dùng key ổn định và xử lý kết quả mơ hồ. Không chỉ dùng một cờ trong memory.

### Gửi bất đồng bộ bằng outbox

Luồng:

```text
HTTP request
   |
   v
Idempotency + transaction
   |
   +-- business update
   +-- notification PENDING
   +-- outbox event
   |
   v
HTTP 202 + notificationId

Worker
   |
   v
Claim notification
   |
   v
JavaMailSender.send
   |
   v
Record SUBMITTED / RETRY_WAIT / FAILED / UNKNOWN
```

Ưu điểm:

- HTTP request không phải chờ SMTP.
- Có thể retry theo policy.
- Có trạng thái để theo dõi.
- Có thể giới hạn tốc độ gửi.
- Notification được ghi cùng transaction nghiệp vụ.

Hạn chế:

- Cần worker, outbox và state machine.
- Cần xử lý concurrency, lease, retry và dead-letter.
- Vẫn cần xử lý cửa sổ lỗi giữa SMTP acceptance và database update.

Với hệ thống nghiệp vụ cần độ tin cậy, mô hình bất đồng bộ thường dễ vận hành hơn vì trạng thái và retry được quản lý rõ ràng.

## 21. Lưu ý khi dùng @Transactional và @Async

Không nên giả định @Transactional và @Async tự tạo ra cơ chế idempotency:

- @Transactional chỉ quản lý transaction của resource tham gia transaction manager; SMTP không nằm trong transaction database.
- @Async chỉ chạy method ở thread khác; nếu job chạy lại hoặc nhiều instance cùng xử lý, vẫn có nguy cơ duplicate.
- @Scheduled có thể chạy trên nhiều instance nếu ứng dụng scale out; cần database claim/lock.
- Retry annotation có thể gọi lại method; nếu method gửi SMTP trực tiếp mà không có stable operation ID, có thể gửi trùng.

Ví dụ không đủ an toàn:

```java
@Async
@Retryable
public void sendInvoice(String recipient) {
    mailSender.send(buildMessage(recipient));
}
```

Đoạn này không cho biết lần gọi nào là cùng một thao tác, không lưu trạng thái bền vững và không xử lý kết quả mơ hồ. Nếu dùng retry framework, hãy retry một notification có ID ổn định và lưu attempt/status trong database.

### Transactional event listener không thay thế outbox

@TransactionalEventListener(AFTER_COMMIT) có thể giúp chỉ xử lý event sau khi transaction commit. Tuy nhiên, nếu process chết sau commit nhưng trước khi listener thực thi, event trong memory có thể bị mất. Với yêu cầu không mất notification, hãy lưu outbox row trong cùng transaction và dùng worker đọc từ database.

## 22. Quản lý resend có chủ đích

Một hệ thống chống duplicate vẫn cần chức năng “Gửi lại email” khi người dùng thật sự yêu cầu.

Hãy phân biệt:

- **Retry:** thử lại cùng notification vì lỗi tạm thời hoặc kết quả chưa rõ.
- **Resend:** tạo một thao tác nghiệp vụ mới theo yêu cầu của người dùng hoặc nhân viên.

Ví dụ data model:

```text
notification_id: N-100
business_event_id: INVOICE_READY:order-123
status: SUBMITTED

resend_request_id: R-201
resend_of_notification_id: N-100
status: PENDING
```

Resend có thể liên kết tới notification gốc nhưng có ID và audit record riêng. Nếu business policy cho phép gửi lại, thao tác này tạo notification mới rõ ràng. Nó không nên tái sử dụng idempotency key của request cũ.

### Không tự động gửi lại chỉ vì người dùng không thấy email

Người nhận có thể không thấy email vì:

- Thư vào spam hoặc quarantine.
- Mailbox rule chuyển thư sang folder khác.
- Provider đã giao nhưng client không đồng bộ.
- Địa chỉ email sai hoặc đã thay đổi.
- Email bị bounce sau SMTP acceptance.

Trước khi tạo resend, nên hiển thị trạng thái đã biết và cân nhắc kiểm tra provider event. Resend có chủ đích vẫn có thể tạo thư trùng ở phía người nhận; UI nên nói rõ hành động này.

## 23. Retention của idempotency record

Không nên xóa idempotency record ngay sau khi notification được gửi. Client có thể retry muộn vì gateway, queue hoặc người dùng chưa nhận được phản hồi.

Thời gian lưu phụ thuộc:

- Thời hạn retry của client/API gateway.
- Thời gian tồn tại của queue và dead-letter queue.
- Thời gian vận hành cho phép replay.
- Quy định lưu trữ audit.
- Chính sách privacy/data retention.

Nếu xóa key quá sớm, request cũ được gửi lại có thể bị coi là thao tác mới. Nếu giữ vô hạn, bảng có thể tăng không kiểm soát và chứa dữ liệu không cần thiết.

Một số nguyên tắc:

1. Giữ key ít nhất lâu hơn cửa sổ retry hợp lệ.
2. Giữ business event uniqueness theo thời gian cần bảo đảm không phát lại notification.
3. Có thể xóa payload nhạy cảm sớm hơn nhưng giữ tombstone/metadata idempotency tối thiểu.
4. Không xóa record đang PROCESSING, RETRY_WAIT hoặc UNKNOWN.
5. Khi hết retention, xác định rõ request cũ có được phép tạo thao tác mới hay không.

## 24. Bảo mật và quyền riêng tư

Idempotency key không phải bí mật xác thực. Người có key không tự động được quyền xem trạng thái hoặc gửi email cho người khác.

Ứng dụng vẫn cần:

- Xác thực người gọi.
- Kiểm tra quyền với order/customer/recipient.
- Scope key theo tenant và operation.
- Giới hạn độ dài và ký tự key.
- Không log toàn bộ payload email nếu có PII.
- Không đưa access token hoặc reset token vào idempotency key.
- Giới hạn tốc độ tạo notification để tránh abuse.
- Kiểm soát ai được tạo resend.
- Giữ audit metadata tối thiểu nhưng đủ điều tra.

Nếu key được lưu trong database, có thể lưu hash của key thay vì giá trị nguyên bản tùy threat model. Tuy nhiên, cần bảo đảm hệ thống có thể tra cứu key hiệu quả và không làm yếu tính uniqueness.

## 25. Quan sát và vận hành

Để biết hệ thống có đang gửi trùng hay không, cần theo dõi các chỉ số và log:

| Metric/field | Ý nghĩa |
| --- | --- |
| idempotency_replay_count | Số request được nhận diện là retry |
| idempotency_conflict_count | Số lần một key được dùng với payload khác |
| notification_created_count | Số notification mới được tạo |
| notification_submitted_count | Số message được SMTP/provider chấp nhận |
| notification_retry_count | Số lần retry |
| notification_unknown_count | Số kết quả gửi chưa xác định |
| notification_failed_count | Số notification lỗi cuối |
| outbox_lag | Độ trễ từ lúc tạo đến lúc worker xử lý |
| provider_message_id | Định danh provider để tra cứu |

Log nên có:

```text
notificationId=N-123
businessEventId=INVOICE_READY:order-123
attempt=2
status=UNKNOWN
providerMessageId=...
```

Không ghi toàn bộ nội dung email, token hoặc thông tin thanh toán chỉ để debug. Dùng notification ID để liên kết log giữa API, worker và provider.

### Phân biệt request replay với email thực sự gửi lại

Khi client retry, metric idempotency_replay_count tăng nhưng notification_created_count không tăng tương ứng. Đây là hành vi mong muốn. Nếu notification count tăng mỗi lần cùng thao tác bị retry, key hoặc unique constraint đang không hoạt động đúng.

## 26. Kiểm thử idempotency

Kiểm thử cần tập trung vào các tình huống lặp và concurrency, không chỉ kiểm tra một lần gửi thành công.

### Test 1 — Cùng key, cùng payload

Gửi cùng request hai lần:

```text
Request A: key K, payload P
Request B: key K, payload P
```

Kỳ vọng:

- Chỉ có một idempotency record.
- Chỉ có một notification.
- Hai response tham chiếu cùng notification ID.
- Worker chỉ thấy một logical notification.

### Test 2 — Cùng key, payload khác

```text
Request A: key K, recipient A
Request B: key K, recipient B
```

Kỳ vọng:

- Request thứ hai nhận conflict.
- Không tạo notification gửi tới recipient B.
- Không thay đổi request đã được ghi nhận.

### Test 3 — Hai request đồng thời

Khởi chạy nhiều request đồng thời cùng scope/key/payload.

Kỳ vọng:

- Database unique constraint chỉ cho một claim thành công.
- Các request còn lại nhận lại cùng notification.
- Không có hai outbox event cho cùng business key.

### Test 4 — Hai key khác nhau nhưng cùng business event

```text
Request A: key K1, business event E
Request B: key K2, business event E
```

Nếu policy quy định một notification cho mỗi business event, unique constraint business key phải ngăn notification thứ hai. Nếu nghiệp vụ cho phép resend, request phải đi qua operation resend riêng.

### Test 5 — Worker chết trước khi gửi

Claim notification rồi dừng process trước khi gọi SMTP.

Kỳ vọng:

- Lease hết hạn được phát hiện.
- Notification được khôi phục theo policy.
- Không tạo notification ID mới.

### Test 6 — Worker chết sau khi SMTP chấp nhận

Mô phỏng SMTP nhận message nhưng process chết trước khi ghi SUBMITTED.

Kỳ vọng:

- Hệ thống không giả định chắc chắn email chưa gửi.
- Notification có thể được đưa sang UNKNOWN.
- Reconciliation hoặc policy xử lý rủi ro duplicate được áp dụng.

### Test 7 — SMTP từ chối tạm thời và vĩnh viễn

Kỳ vọng:

- Lỗi tạm thời được retry có giới hạn.
- Lỗi vĩnh viễn không retry vô hạn.
- Mỗi attempt được ghi nhận.

### Test 8 — Request resend có chủ đích

Gửi cùng invoice lần nữa bằng operation resend mới.

Kỳ vọng:

- Tạo notification mới theo policy.
- Có liên kết với notification gốc.
- Audit ghi nhận ai yêu cầu resend và thời điểm.

## 27. Ví dụ hoàn chỉnh về luồng nghiệp vụ

Giả sử người dùng chọn “Gửi hóa đơn qua email” trong trang chi tiết đơn hàng.

### Bước 1 — Client tạo key

Client tạo một UUID cho lần thao tác và giữ nguyên trong mọi lần retry của request đó.

### Bước 2 — API kiểm tra key

Controller nhận Idempotency-Key, xác thực người dùng và gọi service. Service tính request hash và claim key trong database.

### Bước 3 — Ghi notification/outbox

Trong cùng transaction:

- Lưu idempotency record.
- Tạo notification PENDING.
- Ghi outbox event.
- Commit.

Nếu request được gửi lại với cùng key và payload, server trả cùng notification ID.

### Bước 4 — Worker claim notification

Worker dùng row lock/lease để nhận một notification. Nhiều worker không được cùng claim một row đang được xử lý.

### Bước 5 — Render và gửi

Worker tải mail model, render template, tạo MimeMessage, thiết lập MimeMessageHelper và gọi JavaMailSender.send(...).

### Bước 6 — Ghi kết quả

- SMTP chấp nhận rõ ràng: ghi SUBMITTED.
- Lỗi tạm thời đã biết: ghi RETRY_WAIT.
- Lỗi vĩnh viễn: ghi FAILED.
- Kết quả không rõ: ghi UNKNOWN và reconcile.

### Bước 7 — Client tra trạng thái

Client có thể gọi endpoint trạng thái theo notification ID mà server cấp, sau khi kiểm tra quyền truy cập. Không cần gửi request mới chỉ để hỏi email đã gửi chưa.

```text
Client
  |
  | POST + Idempotency-Key
  v
API / Idempotency service
  |
  | unique key + request hash
  v
Database transaction
  |-- business update
  |-- notification PENDING
  |-- outbox row
  v
Worker claim
  |
  v
Render template
  |
  v
JavaMailSender / SMTP
  |
  v
Record SUBMITTED / RETRY_WAIT / FAILED / UNKNOWN
  |
  v
Status endpoint
```

## 28. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tạo UUID mới mỗi lần HTTP retry | Server coi mỗi request là thao tác mới | Giữ cùng key cho cùng logical operation |
| Chỉ lưu key trong memory | Mất trạng thái khi restart hoặc scale out | Lưu bền vững trong database/distributed store |
| SELECT rồi INSERT không unique constraint | Hai request đồng thời tạo hai record | Unique index và atomic insert/claim |
| Chỉ kiểm tra idempotency ở controller | Backend event/worker vẫn tạo trùng | Thêm business key và notification uniqueness |
| Gửi SMTP trong transaction database | Không rollback được side effect ngoài DB | Dùng outbox và worker |
| Đánh dấu submitted trước khi gửi | Có thể mất email khi process crash | Chỉ ghi nhận sau khi có kết quả chấp nhận |
| Retry mọi exception | Có thể gửi trùng khi kết quả mơ hồ | Phân loại lỗi, dùng UNKNOWN và reconciliation |
| Coi timeout là chắc chắn chưa gửi | Có thể tạo duplicate | Xem giai đoạn thất bại và trạng thái provider |
| Dùng Message-ID làm deduplication | SMTP/mailbox có thể vẫn nhận nhiều thư | Dùng idempotency ở application/provider |
| Coi outbox là exactly-once delivery | Worker vẫn có thể gửi lại sau crash | Hiểu outbox là atomic record + at-least-once processing |
| Dùng recipient + subject làm key | Chặn cả những email hợp lệ trong tương lai | Dùng request/business operation ID |
| Không phân biệt retry và resend | Không biết đâu là thao tác mới có chủ đích | Resend có operation ID và audit riêng |
| Xóa key quá sớm | Retry muộn có thể tạo notification mới | Định nghĩa retention theo cửa sổ retry/replay |
| Worker giữ DB lock khi gửi SMTP | Lock kéo dài, giảm throughput | Claim trong transaction ngắn, gửi ngoài transaction |
| Không ghi notification ID vào log | Khó điều tra duplicate | Correlate API, worker và provider bằng stable ID |

## 29. Quy tắc thiết kế nhanh

| Nhu cầu | Cơ chế nên dùng |
| --- | --- |
| Chống double-click/retry HTTP | Idempotency key + request hash |
| Chống hai backend listener tạo cùng email | Business event key + unique constraint |
| Ghi yêu cầu gửi cùng thay đổi nghiệp vụ | Transactional outbox |
| Chống nhiều worker cùng xử lý một row | Atomic claim, row lock/lease |
| Retry cùng notification | Notification ID ổn định + attempt state |
| Chống provider nhận lặp | Provider API idempotency nếu có hỗ trợ |
| Xử lý timeout sau khi gửi | UNKNOWN + reconciliation/policy |
| Cho phép người dùng gửi lại có chủ đích | Resend operation mới, liên kết notification gốc |
| Điều tra email đã được chấp nhận chưa | Provider message ID/event và log |

## 30. Kết luận

Để tránh gửi trùng khi một thao tác được gọi lại, ứng dụng cần nhận diện **logical operation** thay vì coi mỗi lời gọi method hoặc HTTP request là một email mới. Idempotency key giúp nhận ra request retry; request hash phát hiện key bị dùng với payload khác; business key ngăn nhiều luồng backend tạo cùng notification; database unique constraint bảo vệ các trường hợp chạy đồng thời. Transactional outbox ghi nhận yêu cầu gửi cùng transaction nghiệp vụ, còn worker quản lý claim, attempt và trạng thái gửi.

Với Spring Framework Mail, JavaMailSender chỉ thực hiện việc gửi qua transport. Nó không tự chống duplicate. SMTP cũng không bảo đảm exactly-once trong tình huống process mất kết nối sau khi server có thể đã nhận message. Vì vậy, hãy phân biệt SUBMITTED, FAILED và UNKNOWN, dùng provider idempotency nếu có, và reconcile những kết quả mơ hồ. Resend có chủ đích cần một operation mới và audit riêng. Thiết kế như vậy giúp request retry không tạo thêm notification ngoài ý muốn, đồng thời phản ánh trung thực giới hạn của việc gửi email qua hệ thống bên ngoài.
