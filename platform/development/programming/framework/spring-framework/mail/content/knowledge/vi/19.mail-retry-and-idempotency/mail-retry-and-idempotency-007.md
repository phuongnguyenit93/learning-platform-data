# Idempotency khi worker đọc lại outbox

Trong ứng dụng Spring Framework Mail, việc gửi email thường được tách khỏi transaction nghiệp vụ: service cập nhật trạng thái đơn hàng và ghi một bản ghi **outbox**, sau đó worker đọc outbox và gọi `JavaMailSender`. Cách này tránh tình huống transaction database đã commit nhưng tiến trình gửi thông báo bị mất mà không có dấu vết.

Nhưng outbox không tự bảo đảm một email chỉ được gửi đúng một lần. Worker có thể đọc lại cùng job khi restart, retry, timeout, hết lease hoặc khi nhiều instance cùng polling. Nghiêm trọng hơn, SMTP relay có thể đã chấp nhận thư, nhưng worker chết trước khi kịp cập nhật trạng thái `SENT`. Lần đọc tiếp theo không biết chắc thư đã gửi, và việc thử lại có thể tạo bản sao thứ hai.

**Idempotency khi worker đọc lại outbox** có nghĩa hệ thống nhận diện cùng một ý định gửi, tránh tạo job trùng, tránh nhiều worker xử lý đồng thời khi có thể, và quản lý việc retry mà không gây side effect ngoài ý muốn trong các tình huống kiểm soát được. Nó **không có nghĩa** Spring Mail, SMTP hoặc database outbox có khả năng thực hiện một distributed transaction đảm bảo “exactly once” đến inbox.

Bài học này giải thích các mức độ trùng lặp, khóa định danh ổn định, unique constraint, claim/lease, lock token, trạng thái job, crash window, xử lý kết quả không chắc chắn, backoff, outbox worker và các ví dụ Java/Spring Boot với PostgreSQL.

## 1. Outbox dùng để giải quyết vấn đề gì?

Một luồng gửi đồng bộ đơn giản:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    orderRepository.confirm(orderId);
    mailSender.send(createMessage(orderId));
}
~~~

Có hai hệ thống khác nhau: database và SMTP. Transaction database không rollback được email đã chuyển cho relay. Nếu gửi thành công nhưng transaction rollback, người nhận có thể nhận thông báo cho đơn hàng chưa được xác nhận. Nếu database commit rồi tiến trình chết trước khi gọi SMTP, thông báo có thể bị mất.

Với **transactional outbox**, thay vì gửi trong transaction, service ghi một **ý định gửi**:

~~~mermaid
flowchart TD
    A["Xác nhận đơn hàng"] --> B["Transaction DB"]
    B --> C["UPDATE orders"]
    B --> D["INSERT mail_outbox"]
    C --> E["COMMIT"]
    D --> E
    E --> F["Worker poll outbox"]
    F --> G["Claim job"]
    G --> H["JavaMailSender.send"]
    H --> I["Ghi nhận kết quả"]
~~~

Cập nhật đơn hàng và thêm outbox record nằm trong cùng transaction. Cả hai commit hoặc cả hai rollback. Sau commit, worker có thể tìm job ngay cả khi request process kết thúc.

Tuy nhiên, đoạn từ **claim → gửi SMTP → cập nhật trạng thái** không thuộc một transaction nguyên tử duy nhất. Worker có thể làm lại. Đây là lý do cần idempotency.

## 2. Định nghĩa idempotency trong hệ thống gửi mail

Một thao tác idempotent cho cùng yêu cầu nhiều lần không tạo thêm kết quả nghiệp vụ ngoài lần đầu.

Giả sử có sự kiện:

~~~text
Business event: ORDER_CONFIRMED
Event ID: evt-981
Order: ORD-2048
Recipient: contact-77
~~~

Nếu hệ thống nhận lại chính event `evt-981`, nó vẫn nên có **một công việc gửi email logic** cho `contact-77`, không tạo thêm job cho mỗi lần nhận lại.

Cần phân biệt:

| Ranh giới | Tình huống trùng | Biện pháp |
| --- | --- | --- |
| Đưa yêu cầu vào outbox | Event/request bị chạy hai lần | Idempotency key + unique constraint |
| Worker nhận job | Hai worker cùng lấy một row | Claim nguyên tử, row lock, lease |
| Worker cập nhật kết quả | Worker cũ ghi đè trạng thái mới | Lock token hoặc version check |
| Gửi ra SMTP relay | Gửi xong rồi crash trước mark SENT | Không giải quyết tuyệt đối bằng DB; cần chính sách retry và provider dedupe nếu có |
| Xử lý phản hồi provider | Cùng webhook được giao lại | Dedupe event của provider riêng |

Một bảng outbox có unique key giải quyết được **duplicate enqueue**; nó không tự ngăn hai lần gọi SMTP với cùng một outbox record.

## 3. At-least-once và giới hạn exactly-once

Khi worker có retry và phục hồi job sau crash, một công việc có thể được **xử lý ít nhất một lần** theo ý định của hệ thống nếu hạ tầng hoạt động và chính sách retry cho phép. Nhưng mỗi lần xử lý có thể dẫn tới một lần gửi SMTP, kể cả khi lần trước đã thành công mà kết quả chưa kịp ghi vào database.

~~~text
Worker A: claim job
Worker A: gửi tới SMTP
SMTP relay: chấp nhận email
Worker A: process crash trước UPDATE SENT

Worker B: thấy lease hết hạn
Worker B: claim lại job
Worker B: gửi lần nữa
SMTP relay: chấp nhận email lần nữa
~~~

Có thể chỉ có **một** outbox row, nhưng **hai** lần gửi mail. Không có ràng buộc SQL nào tự thu hồi thư đã được relay chấp nhận.

Cần dùng các thuật ngữ chính xác:

- **At-most-once attempt:** Không cố retry sau tình huống không chắc chắn; ít gửi trùng hơn nhưng có nguy cơ mất thư.
- **At-least-once processing:** Có cơ chế retry và phục hồi; tránh mất ý định gửi nhưng chấp nhận một số lần xử lý lặp.
- **Exactly-once external effect:** Chỉ có thể tuyên bố khi hệ thống nhận hỗ trợ deduplication/transaction tương ứng với hợp đồng rõ ràng; SMTP thông thường không cung cấp một idempotency key chuẩn để bảo đảm điều đó.

**Kết luận:** Thiết kế outbox có thể bảo đảm hơn về tính bền vững của yêu cầu gửi, chứ không có nghĩa mỗi email chắc chắn xuất hiện đúng một lần trong inbox.

## 4. Các nguyên nhân khiến worker đọc lại cùng job

Worker có thể gặp lại một outbox row do:

1. Process bị kill hoặc JVM crash khi đang gửi.
2. Server restart hoặc deploy khi job chưa được mark `SENT`.
3. SMTP timeout và worker không nhận được phản hồi cuối cùng.
4. Worker dừng lâu do GC pause khiến lease hết hạn.
5. Worker khác reclaim job đã quá hạn.
6. Retry được lên lịch sau lỗi tạm thời.
7. Queue/event consumer giao lại message.
8. Scheduler poll chồng nhau.
9. Operator chọn “retry” thủ công.
10. Cơ chế ghi outbox ban đầu tạo nhiều job tương đương.

Phải xử lý cả **trùng job logic** lẫn **trùng lần xử lý cùng một row**. Chỉ thêm `isSent = true` không đủ vì thời gian giữa đọc, gửi và ghi lại vẫn có race condition.

## 5. Xây dựng idempotency key ổn định

Idempotency key đại diện **một ý định gửi thông báo**, không phải một lần thử gửi.

Một định danh có thể kết hợp:

~~~text
tenantId : eventId : mailPurpose : recipientId : contentVersion
~~~

Ví dụ:

~~~text
tenant-42:evt-981:ORDER_CONFIRMED:contact-77:v1
~~~

Các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `tenantId` | Không gộp nhầm job giữa các tenant |
| `eventId` | Định danh sự kiện nghiệp vụ được tạo một lần |
| `mailPurpose` | Phân biệt xác nhận, hóa đơn, cảnh báo... |
| `recipientId` | Phân biệt các người nhận logic |
| `contentVersion` | Chỉ dùng nếu version mới thực sự là ý định gửi khác |

### 5.1. Không dùng UUID mới ở mỗi retry

Sai:

~~~java
String key = UUID.randomUUID().toString();
outbox.insertIfAbsent(key, mailData);
~~~

Nếu hàm được gọi lại, key mới tạo một công việc logic khác. UUID ngẫu nhiên có thể dùng cho `job_id` hoặc `attempt_id`, nhưng **key chống trùng phải được tái tạo thành cùng giá trị** từ dữ liệu nghiệp vụ ổn định.

### 5.2. Không chọn khóa quá rộng

Nếu key chỉ là email address, việc gửi hóa đơn và gửi xác nhận đơn hàng có thể chặn lẫn nhau. Nếu key chỉ có `orderId`, các email cho sự kiện thanh toán và giao hàng của cùng đơn có thể bị coi là trùng.

### 5.3. Không chọn khóa quá hẹp

Nếu thêm `LocalDateTime.now()`, attempt number hoặc UUID của request vào key, hai lần retry thường có key khác nhau. Không còn tác dụng idempotency.

### 5.4. “Gửi lại theo yêu cầu” có phải là cùng công việc?

Cần quyết định theo nghiệp vụ:

- Nếu user retry một HTTP request do timeout, đó thường là **cùng ý định gửi** và nên dùng cùng key.
- Nếu user chủ động yêu cầu một bản sao hóa đơn mới sau nhiều ngày, đó có thể là **ý định gửi mới** với `resendRequestId` riêng.
- Nếu cùng một campaign gửi nhiều đợt, mỗi đợt có thể có ID riêng.

Không xóa job cũ hoặc đổi ngẫu nhiên key chỉ để né unique constraint. Việc gửi lại có chủ đích cần được phân biệt và audit.

## 6. Thiết kế bảng mail_outbox

Một schema PostgreSQL minh họa:

~~~sql
CREATE TABLE mail_outbox (
    id                 uuid PRIMARY KEY,
    tenant_id          uuid NOT NULL,
    idempotency_key    text NOT NULL,
    business_event_id  text NOT NULL,
    mail_purpose       text NOT NULL,
    recipient_id       text NOT NULL,
    recipient_address  text NOT NULL,
    payload            jsonb NOT NULL,

    status             text NOT NULL DEFAULT 'PENDING',
    attempt_count      integer NOT NULL DEFAULT 0,
    next_attempt_at    timestamptz NOT NULL DEFAULT now(),

    lock_token         uuid,
    locked_until       timestamptz,

    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    sent_at            timestamptz,
    last_error_code    text,

    CONSTRAINT uq_mail_job UNIQUE (
        tenant_id, idempotency_key
    ),

    CONSTRAINT chk_mail_status CHECK (
        status IN ('PENDING', 'SENDING', 'RETRY', 'SENT', 'DEAD')
    )
);
~~~

Index phục vụ worker polling:

~~~sql
CREATE INDEX idx_mail_ready
    ON mail_outbox (next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX idx_mail_lease
    ON mail_outbox (locked_until)
    WHERE status = 'SENDING';
~~~

Đây là schema minh họa, không phải migration áp dụng trực tiếp cho mọi hệ thống. Có thể thêm `provider_message_id`, `last_attempt_at`, `max_attempts`, `error_details_ref`, schema version, correlation ID và các index khác tùy nhu cầu.

### Một row cho mỗi recipient?

Với email có nội dung riêng theo từng người nhận, thường nên tạo **một outbox job cho mỗi recipient logic**. Ví dụ:

~~~text
evt-981 + ORDER_CONFIRMED + contact-77 → job A
evt-981 + ORDER_CONFIRMED + contact-88 → job B
~~~

Như vậy mỗi địa chỉ có trạng thái retry, suppression và audit riêng. Gửi một message với nhiều To/Cc/Bcc có thể có yêu cầu riêng về bảo mật và tính kết quả cho từng recipient.

## 7. Insert outbox cùng transaction với nghiệp vụ

Một luồng SQL khái quát:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE id = :order_id
  AND status = 'PENDING';

-- Chỉ tạo event/outbox khi nghiệp vụ thực sự có
-- một chuyển trạng thái hợp lệ tương ứng.
INSERT INTO mail_outbox (
    id, tenant_id, idempotency_key,
    business_event_id, mail_purpose,
    recipient_id, recipient_address, payload
)
VALUES (
    :job_id, :tenant_id, :key,
    :event_id, 'ORDER_CONFIRMED',
    :recipient_id, :recipient, :payload
)
ON CONFLICT (tenant_id, idempotency_key)
DO NOTHING;

COMMIT;
~~~

Điều quan trọng là cập nhật nghiệp vụ và insert outbox commit/rollback **cùng nhau**. Trong mã thật, chỉ insert khi chuyển trạng thái được xác nhận và event ID có tính ổn định; ví dụ trên lược giản bước kiểm tra kết quả UPDATE.

Trong Spring:

~~~java
@Service
public class OrderConfirmationService {

    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderConfirmationService(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void confirm(UUID orderId, UUID actorId) {
        Order order = orders.findForUpdate(orderId)
                .orElseThrow();

        boolean newlyConfirmed = order.confirm(actorId);

        if (!newlyConfirmed) {
            return; // Không phát sinh thêm event.
        }

        String eventId = order.confirmationEventId();
        String key = String.join(":",
                order.tenantId().toString(),
                eventId,
                "ORDER_CONFIRMED",
                order.recipientContactId().toString(),
                "v1"
        );

        outbox.insertIfAbsent(
                MailOutboxDraft.fromOrder(order, key)
        );
    }
}
~~~

`Order`, `MailOutboxDraft`, `findForUpdate` và `insertIfAbsent` là các thành phần ứng dụng giả định; chúng cần được triển khai tương ứng. `insertIfAbsent` phải dựa trên unique constraint/atomic SQL, không chỉ `findByKey` rồi `insert` vì hai transaction có thể race.

**Lưu ý với JPA:** Bắt `DataIntegrityViolationException` do vi phạm unique key trong một transaction rồi tiếp tục làm việc có thể không an toàn vì transaction đã bị đánh dấu rollback-only. Cách dùng `ON CONFLICT DO NOTHING` (PostgreSQL) hoặc cơ chế upsert tương ứng thường phù hợp hơn khi conflict là kết quả được dự kiến.

## 8. State machine của job

Một mô hình trạng thái dễ hiểu:

| Status | Ý nghĩa |
| --- | --- |
| `PENDING` | Đã commit, đang chờ worker |
| `SENDING` | Một worker đã claim với lease hiện tại |
| `RETRY` | Chờ thử lại sau lỗi tạm thời hoặc kết quả không chắc chắn |
| `SENT` | Ứng dụng ghi nhận thao tác gửi thành công ở tầng SMTP |
| `DEAD` | Không tự động retry tiếp, cần xử lý riêng |

~~~mermaid
flowchart TD
    A["PENDING"] --> B["SENDING"]
    B -->|"send thành công"| C["SENT"]
    B -->|"lỗi retryable"| D["RETRY"]
    D -->|"đến next_attempt_at"| B
    B -->|"lỗi vĩnh viễn / hết lượt"| E["DEAD"]
    B -->|"lease hết hạn"| F["claim lại"]
    F --> B
~~~

Ở đây `SENT` được định nghĩa rõ là **worker đã thấy `JavaMailSender.send(...)` trả về thành công và ghi được kết quả vào database**. Không hiểu `SENT` là “đã vào inbox”. Nếu cần tracking delivery, dùng provider callback/bounce feedback và trạng thái riêng.

### Các trường phục vụ claim

- `locked_until`: hết hạn quyền claim để worker khác có thể phục hồi.
- `lock_token`: token mới ở mỗi claim để tránh worker cũ cập nhật trạng thái.
- `attempt_count`: số lần thử/claim theo định nghĩa hệ thống.
- `next_attempt_at`: thời điểm cho phép retry.
- `last_error_code`: phân loại lỗi để quan sát và điều hành.

`lock_token` thay đổi mỗi lần claim; `idempotency_key` không đổi.

## 9. Không đọc PENDING bằng SELECT rồi gửi ngay

Cách nguy hiểm:

~~~text
Worker A: SELECT row 123 WHERE status=PENDING
Worker B: SELECT row 123 WHERE status=PENDING
Worker A: SMTP send
Worker B: SMTP send
Worker A: UPDATE SENT
Worker B: UPDATE SENT
~~~

Hai worker cùng nhìn thấy `PENDING` trước khi một bên thay đổi status. Cần biến thao tác **claim** thành bước nguyên tử.

Với PostgreSQL, có thể dùng `FOR UPDATE SKIP LOCKED`:

~~~sql
WITH candidates AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        status IN ('PENDING', 'RETRY')
        AND next_attempt_at <= now()
    ) OR (
        status = 'SENDING'
        AND locked_until < now()
    )
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS m
SET
    status = 'SENDING',
    attempt_count = m.attempt_count + 1,
    lock_token = gen_random_uuid(),
    locked_until = now() + interval '2 minutes',
    updated_at = now()
FROM candidates c
WHERE m.id = c.id
RETURNING
    m.id, m.lock_token, m.attempt_count,
    m.recipient_address, m.mail_purpose, m.payload;
~~~

Trong một transaction ngắn, worker:

1. Chọn các job có thể xử lý.
2. Dùng row lock, bỏ qua row đã bị worker khác khóa.
3. Cập nhật status thành `SENDING` và tạo token.
4. Nhận snapshot job cần xử lý.
5. **Commit transaction claim**.
6. Sau commit mới render và gửi SMTP.

`gen_random_uuid()` là hàm PostgreSQL tạo UUID; đảm bảo database/version có hỗ trợ thích hợp. Nếu dùng database khác, cần cơ chế claim tương đương, không sao chép `SKIP LOCKED` khi dialect không hỗ trợ.

### Vì sao không giữ transaction trong lúc gửi?

Một lần gửi SMTP có thể chờ kết nối, TLS, AUTH, timeout và truyền attachment. Giữ DB transaction/row lock trong suốt network I/O làm tăng contention, giữ connection pool và ảnh hưởng những worker khác. Cách thường dùng là **claim ngắn → send ngoài transaction → mark ngắn**.

Đổi lại, giữa send và mark luôn có một crash window; đó là giới hạn của hệ thống.

## 10. Lease và lock token

Giả sử:

~~~text
10:00 Worker A claim job-123
      lock_token = token-A
      locked_until = 10:02

10:02 Worker A vẫn treo
      Worker B claim lại job-123
      lock_token = token-B
      locked_until = 10:04
~~~

Nếu A quay lại và dùng token-A cập nhật `SENT`, update phải không có tác dụng:

~~~sql
UPDATE mail_outbox
SET
    status = 'SENT',
    sent_at = now(),
    locked_until = NULL,
    lock_token = NULL,
    last_error_code = NULL,
    updated_at = now()
WHERE id = :job_id
  AND status = 'SENDING'
  AND lock_token = :claim_token
RETURNING id;
~~~

Nếu `RETURNING` rỗng, token đã lỗi thời hoặc job không còn `SENDING`. Worker không được ghi đè trạng thái chỉ vì bản thân nó tưởng đã hoàn tất.

### Lock token không ngăn side effect SMTP đã xảy ra

Một tình huống vẫn có thể gửi trùng:

~~~text
Worker A gửi rất chậm
Lease A hết hạn
Worker B claim token-B, bắt đầu gửi
SMTP nhận thư của A
A không mark SENT được vì token-A cũ
SMTP cũng nhận thư của B
B mark SENT bằng token-B
~~~

Lease và token giúp kiểm soát **quyền cập nhật database**. Chúng không thể rollback lời gọi SMTP đã bắt đầu. Vì vậy, không nên tuyên bố fencing token cung cấp exactly-once gửi email.

### Heartbeat khi send lâu

Nếu xử lý có thể vượt lease, worker có thể gia hạn:

~~~sql
UPDATE mail_outbox
SET
    locked_until = now() + interval '2 minutes',
    updated_at = now()
WHERE id = :job_id
  AND status = 'SENDING'
  AND lock_token = :claim_token;
~~~

Khi update trả 0 row, worker đã mất quyền claim. Có thể ngừng các bước còn có thể dừng an toàn; nhưng nếu SMTP đã được relay chấp nhận, không thể “hủy” hoàn toàn side effect bằng heartbeat.

## 11. Crash windows quan trọng

| Thời điểm thất bại | State quan sát | Hướng phục hồi | Nguy cơ trùng |
| --- | --- | --- | --- |
| Trước commit transaction nghiệp vụ | Chưa có job commit | Không gửi | Không từ job đó |
| Sau commit, trước khi worker claim | `PENDING` | Claim khi poll | Thấp |
| Sau claim, trước SMTP | `SENDING` | Hết lease rồi claim lại | Thấp nếu chưa gửi |
| Trong SMTP, chưa biết relay nhận chưa | `SENDING` | Phân loại outcome unknown | **Có** |
| Relay chấp nhận, worker chết trước mark | `SENDING` | Retry/đối soát | **Có** |
| Mark `SENT` commit thành công | `SENT` | Không poll lại bình thường | Không cần gửi |
| Worker cũ hoàn thành sau lease | Token cũ | Từ chối update của worker cũ | Side effect có thể vẫn xảy ra |

Điểm khó nhất:

~~~mermaid
sequenceDiagram
    participant W as Worker A
    participant S as SMTP
    participant DB as Database
    participant R as Worker B
    W->>DB: Claim token-A
    W->>S: Send email
    S-->>W: 250 accepted
    Note over W: Crash trước mark SENT
    R->>DB: Lease hết, claim token-B
    R->>S: Send email lần nữa
    S-->>R: 250 accepted
    R->>DB: Mark SENT token-B
~~~

Unique constraint trên `idempotency_key` không giúp ở đây vì **không hề insert thêm row nào**. Cả hai worker xử lý cùng job.

## 12. SMTP timeout là kết quả không chắc chắn

Ví dụ:

~~~text
Worker gửi hết nội dung SMTP
Relay chấp nhận message
Mạng đứt trước khi worker nhận phản hồi
Worker báo timeout
~~~

Worker không thể suy ra chắc chắn “chưa gửi”. Nếu retry, email có thể bị gửi hai lần. Nếu không retry, email có thể bị mất trong trường hợp relay thực sự chưa nhận.

Có thể chọn chính sách:

- **Best effort:** Retry với backoff, chấp nhận khả năng trùng cho thông báo ít nhạy cảm.
- **Risk-sensitive:** Đánh dấu trạng thái cần đối soát, không retry ngay khi outcome mơ hồ.
- **Provider idempotency:** Nếu API gửi thực sự hỗ trợ idempotency key, dùng cùng key qua retry trong phạm vi provider quy định.
- **Manual review:** Với một số thông báo quan trọng, cho phép operator xác định có gửi lại hay không.

Không có quyết định đúng cho mọi use case. Cần cân bằng giữa rủi ro **thiếu thông báo** và rủi ro **gửi trùng**.

### Message-ID có giúp SMTP dedupe không?

Email có header `Message-ID`, ví dụ:

~~~text
Message-ID: <mail-evt981@example.org>
~~~

Header này hỗ trợ định danh, correlation, threading hoặc debug. Nhưng **không có quy tắc SMTP phổ quát bắt relay phải từ chối email trùng Message-ID**. Gửi hai lần cùng Message-ID vẫn có thể tạo hai thư tới người nhận.

Thư viện có thể tạo/thay đổi Message-ID khi serialize message. Nếu cần cố định header để tracing, phải hiểu Jakarta Mail/provider cụ thể; việc này vẫn không thay thế idempotency của hệ thống nhận.

## 13. Gửi thành công chưa phải phát tới inbox

Khi:

~~~java
mailSender.send(mimeMessage);
repository.markSent(job.id(), job.lockToken());
~~~

`send(...)` trả bình thường là thành công ở tầng gửi mà ứng dụng quan sát. Relay có thể còn phải route và giao email; bounce hoặc lỗi cuối cùng có thể xuất hiện sau.

Nên đặt nghĩa rõ cho `SENT`:

> `SENT` = ứng dụng ghi nhận thao tác giao thư cho transport đã hoàn thành thành công; chưa bảo đảm delivered.

Nếu sản phẩm cần trạng thái `DELIVERED` hoặc `BOUNCED`, phải bổ sung provider feedback, delivery status notification hoặc webhook phù hợp. Các webhook cũng có thể redelivery và cần cơ chế dedupe riêng.

## 14. Spring worker: tách claim, send và mark

Một mô hình:

~~~text
MailOutboxPoller
  → MailClaimService.claimBatch()  (DB transaction ngắn)
  → MailDeliveryWorker.process(job)
     → MailRenderer.render(job)
     → MailGateway.send(mail)      (SMTP ngoài DB transaction)
     → MailStateService.markSent() (DB transaction ngắn)
     → hoặc recordFailure()        (DB transaction ngắn)
~~~

### 14.1. Scheduler

~~~java
@Configuration
@EnableScheduling
public class MailOutboxSchedulingConfig {
}
~~~

~~~java
@Component
public class MailOutboxPoller {

    private final MailClaimService claims;
    private final MailDeliveryWorker delivery;

    public MailOutboxPoller(
            MailClaimService claims,
            MailDeliveryWorker delivery) {
        this.claims = claims;
        this.delivery = delivery;
    }

    @Scheduled(
        fixedDelayString = "${mail.outbox.poll-delay-ms:2000}"
    )
    public void poll() {
        List<ClaimedMailJob> jobs = claims.claimBatch(20);

        for (ClaimedMailJob job : jobs) {
            delivery.process(job);
        }
    }
}
~~~

Ví dụ xử lý tuần tự để làm rõ ngữ nghĩa. Hệ thống lớn có thể dùng nhiều process hoặc executor có giới hạn, nhưng vẫn cần claim an toàn và rate limit SMTP. `@EnableScheduling` bật scheduler; `@Async` không bắt buộc chỉ để poll outbox.

### 14.2. Claimed job là snapshot

~~~java
public record ClaimedMailJob(
        UUID id,
        UUID lockToken,
        int attemptCount,
        String recipient,
        String purpose,
        String payloadJson) {
}
~~~

Không nên giữ một JPA entity mutable gắn persistence context qua transaction boundary và worker thread. DTO bất biến mang những dữ liệu cần xử lý an toàn và rõ ràng hơn.

### 14.3. Claim service

~~~java
@Service
public class MailClaimService {

    private final MailOutboxJdbcRepository repository;

    public MailClaimService(MailOutboxJdbcRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<ClaimedMailJob> claimBatch(int limit) {
        return repository.claimReady(limit);
    }
}
~~~

`claimReady` là method ứng dụng tự triển khai bằng SQL claim atomic ở trên. `@Transactional` cần đi qua Spring proxy như thông thường; không dựa vào self-invocation nếu muốn advice áp dụng.

### 14.4. Worker thực hiện và ghi kết quả

~~~java
@Component
public class MailDeliveryWorker {

    private final MailRenderer renderer;
    private final MailGateway gateway;
    private final MailStateService states;

    public MailDeliveryWorker(
            MailRenderer renderer,
            MailGateway gateway,
            MailStateService states) {
        this.renderer = renderer;
        this.gateway = gateway;
        this.states = states;
    }

    public void process(ClaimedMailJob job) {
        try {
            RenderedMail mail = renderer.render(job);
            gateway.send(mail);

        } catch (Exception preparationOrSendFailure) {
            states.recordFailure(
                    job.id(),
                    job.lockToken(),
                    job.attemptCount(),
                    preparationOrSendFailure
            );
            return;
        }

        // Phải là một transaction DB riêng.
        states.markSent(job.id(), job.lockToken());
    }
}
~~~

`MailRenderer`, `MailGateway`, `RenderedMail` và `MailStateService` là abstraction của ứng dụng, không phải toàn bộ đều có sẵn trong Spring. Ví dụ minh họa việc phân tách trách nhiệm; triển khai production cần xử lý lỗi của chính `recordFailure` và `markSent`, có monitoring và recovery.

**Không bắt chung lỗi DB mark status để coi như một SMTP failure.** SMTP có thể đã thành công; nếu DB mark bị lỗi, job có thể bị claim lại và gửi trùng. Phải lưu/log rõ tình huống này.

### 14.5. Gateway Spring Mail

~~~java
@Component
public class SpringMailGateway implements MailGateway {

    private final JavaMailSender mailSender;

    public SpringMailGateway(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Override
    public void send(RenderedMail mail) {
        try {
            MimeMessage message = mailSender.createMimeMessage();

            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom(mail.from());
            helper.setTo(mail.recipient());
            helper.setSubject(mail.subject());
            helper.setText(
                    mail.plainText(),
                    mail.htmlText()
            );

            mailSender.send(message);

        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Không thể tạo MIME message", ex
            );
        }
    }
}
~~~

`MailPreparationException` là exception do ứng dụng tự định nghĩa. `JavaMailSender.send` còn có thể ném `MailException` và các nguyên nhân SMTP/network cần được phân loại.

Gateway chỉ gửi content đã chuẩn bị. Việc chọn recipient, tính số tiền, template và idempotency thuộc application/domain layer.

## 15. Đánh dấu retry theo token

Khi gửi thất bại và lỗi retryable, thay đổi trạng thái có điều kiện:

~~~sql
UPDATE mail_outbox
SET
    status = 'RETRY',
    next_attempt_at = :retry_at,
    last_error_code = :error_code,
    locked_until = NULL,
    lock_token = NULL,
    updated_at = now()
WHERE id = :job_id
  AND status = 'SENDING'
  AND lock_token = :claim_token;
~~~

Nếu update trả 0 row, worker đã mất quyền claim và không nên ghi đè trạng thái mới. Khi lỗi vĩnh viễn hoặc hết retry budget, chuyển `DEAD` bằng điều kiện token tương tự.

### Retry có backoff và jitter

Một lịch retry có thể dùng:

\[
d_n = \min(d_{\max}, d_{\mathrm{base}} \cdot 2^{n-1}) + jitter
\]

Trong đó `n` là số lần thử đã ghi nhận, `d_base` là khoảng chờ ban đầu, `d_max` là mức trần. Jitter giúp tránh hàng nghìn job retry cùng lúc.

Ví dụ base 30 giây và cap 30 phút:

| Attempt | Độ trễ cơ bản |
| --- | --- |
| 1 | 30 giây |
| 2 | 60 giây |
| 3 | 120 giây |
| 4 | 240 giây |
| 5 | 480 giây |

Giới hạn phép nhân để tránh overflow và đặt max attempts phù hợp. Một job không thể render do dữ liệu sai sẽ không tự lành sau hàng trăm lần retry.

### Phân loại lỗi

| Loại | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Temporary SMTP failure | Provider tạm không nhận, bị throttling | Retry sau backoff |
| Permanent recipient rejection | Địa chỉ không được phép/không hợp lệ | `DEAD` hoặc xử lý policy |
| Rendering/data failure | Thiếu template, payload sai | Không retry vô hạn |
| Network timeout sau khi gửi dữ liệu | Không biết relay đã nhận chưa | Outcome uncertain, chính sách rủi ro riêng |
| DB failure khi mark sent | SMTP có thể đã thành công | Recovery và nguy cơ duplicate |
| Lease expiration | Worker chậm hoặc crash | Reclaim có kiểm soát |

Không xem mọi `MailException` là lỗi tạm thời. Khi đọc provider-specific code, phải xem ngữ nghĩa lỗi và trạng thái SMTP thực.

## 16. Ranh giới transaction và @Async

Một lỗi thiết kế:

~~~java
@Transactional
public void confirmOrder(UUID id) {
    orderRepository.confirm(id);
    mailWorker.sendAsync(createMailCommand(id));
}
~~~

Nếu `mailWorker` có `@Async` và được gọi qua proxy, worker có thể chạy **trước khi transaction `confirmOrder` commit**. Nếu transaction rollback sau đó, email có thể đã gửi sai.

Để tránh:

- Dùng transactional outbox: ghi job cùng transaction nghiệp vụ, worker chỉ đọc job sau commit.
- Với trường hợp best effort, có thể dùng cơ chế after-commit event phù hợp, nhưng event in-memory không có tính bền vững như outbox.
- Không giữ database transaction bao trùm SMTP với kỳ vọng có thể rollback thư.
- Không coi `@Async` là một durable queue: executor in-memory có thể mất task khi process chết.

`@Async` vẫn có thể dùng để chạy nhiều worker song song, nhưng **outbox database mới là nơi lưu ý định gửi bền vững**. Cần kiểm soát thread pool, queue, saturation và SMTP rate limit.

## 17. Snapshot nội dung và người nhận

Outbox có thể lưu:

~~~json
{
  "orderId": "ORD-2048",
  "eventId": "evt-981",
  "recipientId": "contact-77",
  "recipientAddress": "buyer@example.org",
  "mailPurpose": "ORDER_CONFIRMED",
  "templateVersion": 1,
  "locale": "vi-VN"
}
~~~

Hai chiến lược thường gặp:

| Chiến lược | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Lưu snapshot dữ liệu khi tạo job | Các attempt dùng cùng thông tin | Payload có thể chứa PII và trở nên lỗi thời |
| Lưu ID để resolve lại lúc gửi | Dữ liệu gọn, có thể áp dụng policy mới | Recipient/content thay đổi giữa các attempt |
| Snapshot + kiểm tra lại policy | Giữ ý định cũ, tôn trọng suppression/consent mới | Cần định nghĩa trường nào được phép thay đổi |

Với email giao dịch, snapshot giúp nội dung thống nhất. Với marketing, kiểm tra trạng thái unsubscribe/suppression mới nhất thường rất quan trọng.

**Đừng để retry của cùng job tự động đổi sang recipient mới** chỉ vì email profile đã thay đổi, nếu chưa xác định lại quyền nhận và ý nghĩa của idempotency key. Một người nhận khác có thể là một ý định gửi mới.

## 18. Giới hạn idempotency của SMTP

`JavaMailSender` là API thực hiện gửi MIME qua mail transport; nó không có một tham số chuẩn như:

~~~java
mailSender.send(message, idempotencyKey);
~~~

để yêu cầu mọi SMTP relay khử trùng. Không nên tự phát minh một SMTP header rồi coi provider chắc chắn tôn trọng nó.

Nếu dùng một **email API provider** hỗ trợ idempotency key theo tài liệu, ứng dụng có thể truyền cùng key trong mọi retry để giới hạn duplicate submission trong thời gian được provider cam kết. Cần xác định:

- Phạm vi key theo account/tenant.
- Thời gian giữ kết quả dedupe.
- Cách xử lý hai request concurrent.
- Response trả về khi timeout.
- Khả năng tra cứu trạng thái gửi theo request ID.
- Khác biệt giữa “submitted”, “accepted”, “delivered”.

Khi dùng SMTP thông thường, phải chấp nhận một khoảng không chắc chắn giữa relay acceptance và DB status update.

## 19. Testing cho idempotency và failure windows

Không cần gửi email thật để kiểm thử phần lớn thiết kế.

### 19.1. Duplicate enqueue

Tạo cùng một business event hai lần. Xác nhận unique constraint chỉ cho một outbox row có cùng `tenant_id` và `idempotency_key`. Với thử nghiệm concurrency, tạo hai transaction cùng insert để kiểm tra database thực chứ không chỉ mock repository.

### 19.2. Hai worker claim đồng thời

Tạo 20 job `PENDING`, chạy hai worker claim cùng lúc. Xác nhận không có job nào được claim bởi cả hai khi lease còn hợp lệ. PostgreSQL `FOR UPDATE SKIP LOCKED` nên được kiểm thử trên DB có semantics tương ứng, không giả định H2 giống hoàn toàn.

### 19.3. Crash sau claim, trước send

Claim job nhưng không gọi gateway, để lease hết hạn rồi claim lại. Job phải phục hồi theo policy, đồng thời `attempt_count` và `lock_token` đổi phù hợp.

### 19.4. Crash sau SMTP, trước mark SENT

Fake gateway ghi nhận đã nhận lệnh gửi; gây lỗi ở bước mark DB. Sau lease, job sẽ có thể được claim lại. Bài kiểm thử phải **thể hiện khả năng duplicate**, không coi đó là bug SQL có thể sửa bằng unique key.

### 19.5. Stale lock token

Worker A claim token-A; sau expiry worker B claim token-B. A cố mark `SENT` bằng token-A và phải update 0 row. B được phép mark bằng token-B.

### 19.6. Timeout mơ hồ

Fake SMTP client mô phỏng relay đã nhận message nhưng caller nhận timeout. Xác nhận outcome được phân loại là unknown hoặc retry theo chính sách và metric cảnh báo nguy cơ trùng.

### 19.7. Backoff và dead state

- `RETRY` chỉ claim khi `next_attempt_at` tới hạn.
- Attempt không vượt giới hạn đã định.
- Lỗi permanent chuyển `DEAD`.
- `SENT` không được claim bình thường.
- Job đã hết lease có thể được reclaim.
- Manual replay phải theo policy/audit.

### 19.8. Test nội dung riêng khỏi transport

Test renderer với snapshot dữ liệu, test gateway bằng fake sender hoặc SMTP test server. Test worker policy với mock gateway và DB test repository. Không trộn mọi kiểm thử với gửi SMTP production.

## 20. Monitoring và vận hành

Những metric hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| Số job `PENDING` và `RETRY` | Mức backlog |
| Tuổi job cũ nhất chưa hoàn tất | Độ trễ thông báo |
| Số `SENDING` quá hạn lease | Worker chết hoặc bị treo |
| Phân phối `attempt_count` | Retry bất thường |
| Số `DEAD` theo reason | Lỗi cần can thiệp |
| Số stale-token update | Cạnh tranh/lease expiry |
| Số duplicate enqueue bị unique key chặn | Request/event bị lặp |
| Số kết quả SMTP unknown | Rủi ro gửi trùng |
| Thời gian SMTP và lỗi timeout | Nút thắt ở transport |
| Độ trễ event → SMTP accepted | Sức khỏe pipeline |

Audit nên giúp đối soát `business_event_id`, `idempotency_key`, `outbox_id`, `attempt_id`, thời điểm claim/send, reason code và chuyển trạng thái.

Không log SMTP credential, reset token, toàn bộ body email hay dữ liệu người nhận không cần thiết. Dùng contact ID/correlation ID, masking và retention phù hợp.

### Retry thủ công

Khi operator xem một job `DEAD`:

1. Kiểm tra lỗi gốc và trạng thái hiện tại.
2. Xác định retry **cùng ý định** hay gửi **ý định mới**.
3. Nếu retry cùng ý định, giữ idempotency key và audit thay đổi trạng thái.
4. Nếu gửi lại mới có chủ đích, tạo resend event/request ID riêng.
5. Kiểm tra recipient policy, consent/suppression và quyền trước khi gửi.

Không xóa key cũ để lách ràng buộc chống trùng.

## 21. Retention của outbox và deduplication key

Nếu xóa toàn bộ job `SENT` ngay sau gửi, một event cũ được replay có thể tạo lại job vì unique key đã biến mất. Cần giữ dấu vết idempotency đủ lâu cho cửa sổ replay thực tế.

Một số phương án:

- Giữ job `SENT` trong thời gian retention đủ dài.
- Archive outbox và giữ bảng dedupe key nhỏ hơn.
- Duy trì lịch sử notification theo event/recipient.
- Định nghĩa TTL của key dựa trên loại mail và yêu cầu audit.

Chính sách retention cũng phải xét dữ liệu cá nhân trong payload. Không có một thời hạn chung cho mọi sản phẩm; email hóa đơn, marketing và cảnh báo bảo mật có nhu cầu khác nhau.

## 22. Những lỗi triển khai phổ biến

### 22.1. Sinh key ngẫu nhiên mỗi lần retry

Dẫn tới nhiều outbox job tương đương. Key phải ổn định theo business event/purpose/recipient.

### 22.2. Chỉ có SELECT PENDING mà không claim atomic

Hai worker có thể cùng gửi một job. Dùng locking/conditional update phù hợp database.

### 22.3. Mark SENT trước SMTP

Nếu chết sau khi mark nhưng trước khi gửi, job bị coi là xong và email bị mất.

### 22.4. Cho rằng mark SENT sau SMTP là nguyên tử

Nếu relay nhận mail rồi process crash trước DB commit, retry có thể gửi trùng.

### 22.5. Dùng Message-ID làm dedupe guarantee

Message-ID không buộc SMTP relay từ chối message trùng.

### 22.6. Không có lease expiry

Worker chết để job ở `SENDING` mãi mãi.

### 22.7. Không dùng token khi cập nhật status

Worker cũ có thể ghi đè trạng thái của worker mới.

### 22.8. Lease quá ngắn hoặc SMTP timeout vô hạn

Job dễ bị claim lại trong lúc worker trước vẫn đang gửi. Đặt thời gian hợp lý, cân nhắc heartbeat và timeouts.

### 22.9. Retry mọi lỗi như nhau

Lỗi recipient/policy vĩnh viễn không tự hết; không retry vô hạn.

### 22.10. Xem SMTP timeout là chắc chắn chưa gửi

Relay có thể đã chấp nhận mail; retry mang nguy cơ trùng.

### 22.11. Gọi SMTP trong transaction DB dài

Tăng DB contention mà không tạo atomicity giữa SMTP và database.

### 22.12. Coi @Async là durable job queue

Executor in-memory có thể mất task khi process restart; outbox mới giữ intent bền vững.

### 22.13. Không tách tenant và purpose trong key

Có thể gộp nhầm các thông báo hợp lệ.

### 22.14. Xóa dedupe history quá sớm

Event replay muộn có thể lại enqueue và gửi thông báo đã gửi.

### 22.15. Không phân biệt accepted và delivered

`send` trả về bình thường chưa chứng minh email đã vào inbox.

## 23. Câu hỏi tự suy luận

**Câu 1.** Có một outbox record `SENT` nhưng worker polling đọc lại nó. Nên làm gì?

Bỏ qua. `SENT` không phải trạng thái cho phép claim lại trong luồng thông thường.

**Câu 2.** Hai HTTP request giống nhau tạo hai UUID khác nhau làm idempotency key. Có chống trùng không?

Không. Cần một key ổn định cho cùng ý định gửi.

**Câu 3.** Hai worker cùng SELECT `PENDING` rồi gửi trước UPDATE. Có thể xảy ra điều gì?

Cả hai gửi cùng job. Cần claim atomic bằng khóa/điều kiện DB.

**Câu 4.** SMTP đã chấp nhận email nhưng worker crash trước mark `SENT`. Unique constraint có ngăn retry gửi trùng không?

Không. Unique constraint chặn tạo record khác cùng key, không chặn hai lần gửi của cùng record.

**Câu 5.** Vì sao phải có lock token?

Để worker giữ lease cũ không cập nhật đè lên trạng thái sau khi worker khác claim. Nó không rollback SMTP đã gửi.

**Câu 6.** Có thể dùng cùng Message-ID để SMTP tự loại thư trùng không?

Không có bảo đảm SMTP phổ quát như vậy.

**Câu 7.** Timeout sau khi gửi dữ liệu SMTP có nghĩa chắc chắn chưa gửi?

Không. Đây có thể là kết quả không xác định; relay có thể đã nhận.

**Câu 8.** Job `RETRY` có `next_attempt_at` tương lai. Worker có nên claim ngay không?

Không, trừ một thủ tục vận hành có chủ đích cho phép override.

**Câu 9.** Có thể giữ DB transaction mở đến khi `JavaMailSender.send` hoàn thành không?

Có thể viết được nhưng không nên dùng làm cách tạo atomicity. SMTP không rollback theo DB và transaction dài gây giữ resource.

**Câu 10.** `@Async` có tự phục hồi 500 job trong queue sau khi JVM crash không?

Không. Outbox persisted hoặc queue bền vững mới giúp phục hồi theo thiết kế.

**Câu 11.** Khi retry cùng một job, idempotency key thay đổi bao nhiêu lần?

Không thay đổi; chỉ attempt ID/claim token thay đổi.

**Câu 12.** Khi `JavaMailSender.send` trả về bình thường, hệ thống có thể gắn trạng thái `DELIVERED` chưa?

Chưa đủ căn cứ. Cần provider feedback hoặc cơ chế delivery tracking riêng.

## 24. Mô hình ghi nhớ

~~~mermaid
flowchart TD
    A["Business event"] --> B["Stable idempotency key"]
    B --> C["DB transaction: business + outbox"]
    C --> D["Unique constraint chống duplicate enqueue"]
    D --> E["Atomic claim + lease + token"]
    E --> F["Render nội dung đã kiểm soát"]
    F --> G["JavaMailSender.send"]
    G --> H{"Outcome"}
    H -->|"Thành công"| I["Mark SENT có token"]
    H -->|"Tạm thời / unknown"| J["RETRY hoặc đối soát"]
    H -->|"Vĩnh viễn"| K["DEAD"]
    J --> E
~~~

Các điểm phải nhớ:

1. **Transactional outbox lưu bền vững ý định gửi cùng transaction nghiệp vụ.**
2. **Worker có thể xử lý at-least-once** do retry, restart và lease expiry.
3. **Key phải ổn định** theo event/purpose/recipient; không sinh mới ở mỗi attempt.
4. **Unique constraint chống duplicate enqueue**, không tự bảo đảm SMTP chỉ được gọi một lần.
5. **Claim nguyên tử và lease** giảm việc nhiều worker cùng xử lý một job.
6. **Lock token ngăn stale state update**, không thu hồi side effect đã xảy ra ở SMTP.
7. **Crash sau SMTP acceptance trước mark SENT vẫn có thể gây gửi trùng.**
8. **Timeout có thể là kết quả không chắc chắn**; retry phải theo SLA và chính sách rủi ro.
9. **Tách transaction claim, SMTP send và transaction mark**, không giữ khóa database khi chờ network.
10. **Dùng retry/backoff, giới hạn attempts, audit, monitoring và retention** để xử lý replay thực tế.
11. **Phân biệt SMTP accepted với delivered**, không hứa exactly-once delivery khi hạ tầng không hỗ trợ.
12. **Kiểm tra consent/recipient policy ở thời điểm phù hợp**, vì idempotency không tự tạo quyền gửi.

Trong Spring Framework Mail, `JavaMailSender` chịu trách nhiệm tạo kết nối gửi MIME qua SMTP; database và worker orchestration chịu trách nhiệm lưu job, chống enqueue trùng, phân phối công việc, retry và theo dõi trạng thái. Thiết kế đúng giúp worker đọc lại outbox mà vẫn giữ ngữ nghĩa nghiệp vụ nhất quán, đồng thời nói rõ giới hạn không thể loại bỏ hoàn toàn việc gửi trùng ở ranh giới giữa database và SMTP.
