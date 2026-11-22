# Đưa yêu cầu gửi mail vào outbox

## 1. Vì sao cần outbox khi gửi email?

Trong ứng dụng Spring, một thao tác nghiệp vụ thường vừa ghi dữ liệu vào database vừa phát sinh email. Ví dụ, khi khách hàng đặt hàng, ứng dụng lưu đơn hàng và muốn gửi email xác nhận. Hai thao tác này thuộc hai hệ thống khác nhau:

- Database quản lý transaction và có thể rollback dữ liệu.
- SMTP server là hệ thống bên ngoài; khi đã chấp nhận message, database không thể yêu cầu SMTP hoàn tác email.

Nếu gọi gửi mail ngay trong transaction, ứng dụng có thể gặp tình huống email đã được gửi nhưng transaction database rollback. Ngược lại, nếu commit database trước rồi mới gửi mail, process có thể dừng giữa hai thao tác và yêu cầu gửi bị mất.

Đây là bài toán **dual write**: một use case phải ghi thành công vào hai nơi độc lập nhưng không có transaction phân tán bảo đảm cả hai cùng thành công.

~~~mermaid
flowchart TD
    A[Đặt hàng] --> B[BEGIN database transaction]
    B --> C[Lưu đơn hàng]
    C --> D[Gửi email qua SMTP]
    D --> E[COMMIT database]
    D --> F[SMTP lỗi]
    E --> G[Đơn hàng đã lưu]
    F --> H[Email không gửi được]
    G --> I[Trạng thái hai hệ thống không đồng bộ]
~~~

**Transactional outbox** giải quyết khoảng trống này bằng cách ghi một bản ghi thể hiện **ý định gửi email** vào cùng database và cùng transaction với dữ liệu nghiệp vụ. Một worker đọc bản ghi đó sau khi commit, tạo email và gửi qua Spring Mail.

~~~mermaid
flowchart TD
    A[Application service] --> T[Database transaction]
    T --> O[Lưu đơn hàng]
    T --> X[Thêm mail outbox record]
    O --> C[COMMIT]
    X --> C
    C --> W[Outbox worker]
    W --> M[Mail service / JavaMailSender]
    M --> S[SMTP server]
~~~

Nếu transaction commit, cả đơn hàng và yêu cầu gửi đều tồn tại. Nếu transaction rollback, cả hai đều không tồn tại. Việc gửi SMTP được xử lý sau đó và có thể retry khi provider tạm thời không sẵn sàng.

**Outbox bảo đảm tính atomic của dữ liệu nghiệp vụ và ý định gửi trong database. Nó không biến SMTP thành một phần của database transaction và không tự bảo đảm email được giao đúng một lần.**

## 2. Phân biệt outbox với gửi mail sau commit bằng event

Một cách khác là dùng Spring event:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderConfirmed(OrderConfirmedEvent event) {
    mailService.sendConfirmation(event);
}
~~~

Listener chỉ chạy sau khi transaction commit. Cách này tránh gửi email trước khi dữ liệu nghiệp vụ được commit, nhưng event trong bộ nhớ process không phải một hàng đợi bền vững.

Ví dụ process có thể dừng ngay sau commit và trước khi listener thực hiện gửi:

~~~text
Database COMMIT thành công
          |
          v
Process bị dừng đột ngột
          |
          v
Listener chưa gửi mail
          |
          v
Không có job bền vững để khôi phục
~~~

So sánh:

| Tiêu chí | AFTER_COMMIT event | Transactional outbox |
|---|---|---|
| Tránh gửi trước commit | Có | Có |
| Lưu ý định gửi cùng transaction | Không mặc định | Có |
| Khôi phục sau process restart | Không tự có | Có, worker đọc lại bản ghi |
| Retry có trạng thái | Phải tự xây dựng | Là một phần của thiết kế outbox |
| Độ phức tạp | Thấp hơn | Cao hơn |
| Phù hợp | Thông báo best-effort | Thông báo cần lưu bền vững và retry |

Có thể kết hợp domain event và outbox: use case phát sinh sự kiện nghiệp vụ, một handler trong cùng transaction chuyển sự kiện thành outbox record. Điều kiện bắt buộc là **việc ghi outbox phải tham gia cùng transaction database** với thay đổi nghiệp vụ.

Nếu email có thể mất mà không ảnh hưởng nghiệp vụ, AFTER_COMMIT có thể đủ. Nếu email xác nhận đơn hàng, thanh toán hoặc thay đổi quyền truy cập cần được xử lý sau khi ứng dụng restart, outbox là lựa chọn phù hợp hơn.

## 3. Luồng xử lý transactional outbox

Một luồng đầy đủ gồm hai giai đoạn:

**Giai đoạn ghi nghiệp vụ và ý định gửi**

1. Nhận command từ controller hoặc message consumer.
2. Validate quy tắc nghiệp vụ.
3. Lưu dữ liệu nghiệp vụ trong database transaction.
4. Tạo outbox record mô tả email cần gửi.
5. Commit cả dữ liệu nghiệp vụ và outbox record cùng lúc.

**Giai đoạn gửi email**

1. Worker tìm các outbox record đến hạn xử lý.
2. Claim một nhóm record để worker khác không lấy cùng lúc.
3. Commit trạng thái claim và lease.
4. Dựng nội dung email từ payload/template.
5. Gửi qua Mail service và JavaMailSender.
6. Ghi trạng thái SMTP submission thành công hoặc lỗi.
7. Với lỗi có thể retry, lên lịch lần thử tiếp theo.
8. Với lỗi không thể tự khắc phục, đưa record vào trạng thái cần xử lý thủ công.

~~~mermaid
sequenceDiagram
    participant API as Application Service
    participant DB as Database
    participant W as Outbox Worker
    participant SMTP as SMTP Server
    API->>DB: BEGIN
    API->>DB: Save order
    API->>DB: Insert mail outbox
    API->>DB: COMMIT
    W->>DB: Claim pending record
    DB-->>W: Claimed payload + lease
    W->>SMTP: JavaMailSender.send()
    SMTP-->>W: SMTP response
    W->>DB: Mark SUBMITTED or schedule retry
~~~

Worker không nên giữ database transaction mở trong lúc gọi SMTP. Network call có thể chậm hoặc timeout; giữ transaction lâu làm tăng lock contention, giữ connection và cản trở các transaction nghiệp vụ khác.

## 4. Thiết kế bảng mail_outbox

Một schema cơ bản có thể chứa các trường:

| Cột | Ý nghĩa |
|---|---|
| id | ID duy nhất của outbox record |
| event_key | Khóa idempotency ở cấp nghiệp vụ, có unique constraint |
| aggregate_type | Loại đối tượng nghiệp vụ, ví dụ Order |
| aggregate_id | ID đơn hàng hoặc tài khoản liên quan |
| event_type | Loại thông báo, ví dụ ORDER_CONFIRMED |
| recipient | Địa chỉ người nhận |
| payload | Dữ liệu snapshot hoặc reference cần để dựng email |
| payload_version | Phiên bản cấu trúc payload |
| status | PENDING, CLAIMED, RETRY, SUBMITTED, DEAD hoặc UNKNOWN |
| attempt_count | Số lần worker đã claim/thử xử lý |
| available_at | Thời điểm sớm nhất được phép xử lý |
| claimed_by | ID worker đang giữ lease |
| lease_token | Token nhận diện lần claim hiện tại |
| lease_until | Thời điểm lease hết hạn |
| last_error_code | Mã lỗi đã chuẩn hóa |
| last_error_at | Thời điểm lỗi gần nhất |
| created_at | Thời điểm tạo outbox record |
| submitted_at | Thời điểm SMTP chấp nhận submission |

Ví dụ DDL cho PostgreSQL:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    event_key VARCHAR(200) NOT NULL UNIQUE,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    payload JSONB NOT NULL,
    payload_version INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_by VARCHAR(120),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    last_error_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMPTZ,
    CONSTRAINT mail_outbox_status_check
        CHECK (status IN (
            'PENDING', 'CLAIMED', 'RETRY',
            'SUBMITTED', 'DEAD', 'UNKNOWN'
        )),
    CONSTRAINT mail_outbox_attempt_check
        CHECK (attempt_count >= 0)
);

CREATE INDEX mail_outbox_ready_idx
    ON mail_outbox (available_at, created_at)
    WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX mail_outbox_lease_idx
    ON mail_outbox (lease_until)
    WHERE status = 'CLAIMED';

CREATE INDEX mail_outbox_aggregate_idx
    ON mail_outbox (aggregate_type, aggregate_id, created_at);
~~~

DDL trên là một điểm khởi đầu, cần điều chỉnh kiểu dữ liệu, index và retention theo database thực tế. PostgreSQL dùng JSONB; nếu dùng MySQL, SQL Server hoặc Oracle, kiểu JSON, cú pháp claim và index có thể khác.

### Vì sao event_key cần unique?

Một request có thể được gửi lại do client retry, message broker redelivery hoặc ứng dụng nhận command trùng. Nếu mỗi lần xử lý đều tạo outbox record mới, người nhận có thể nhận nhiều email giống nhau.

`event_key` biểu diễn **một ý định thông báo nghiệp vụ duy nhất**, ví dụ:

~~~text
order:ORD-2026-001:confirmation:v1
account:ACC-901:welcome:v1
payment:PAY-773:receipt:v1
~~~

Unique constraint giúp database từ chối việc ghi lặp cùng một ý định. Khóa phải được thiết kế theo nghiệp vụ; không dùng một chuỗi ngẫu nhiên mới mỗi lần retry vì như vậy không chống được duplicate request.

## 5. Ghi outbox trong cùng transaction với đơn hàng

Ví dụ use case đặt hàng sử dụng Spring transaction:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {
    private final OrderRepository orderRepository;
    private final MailOutboxRepository outboxRepository;

    public PlaceOrderService(
            OrderRepository orderRepository,
            MailOutboxRepository outboxRepository) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        Order order = orderRepository.save(
                Order.create(command.customerId(), command.items()));

        String eventKey = "order:" + order.getId()
                + ":confirmation:v1";

        OrderConfirmationPayload payload =
                new OrderConfirmationPayload(
                        order.getId().toString(),
                        order.getCustomerName(),
                        order.getCustomerEmail(),
                        order.getTotal().toPlainString());

        outboxRepository.insert(
                UUID.randomUUID(),
                eventKey,
                "Order",
                order.getId().toString(),
                "ORDER_CONFIRMED",
                order.getCustomerEmail(),
                payload,
                1);

        return order.getId();
    }
}
~~~

Các class OrderRepository, MailOutboxRepository, Order, PlaceOrderCommand và OrderConfirmationPayload là abstraction minh họa do ứng dụng định nghĩa. Điều kiện quan trọng là cả repository nghiệp vụ và outbox repository phải dùng **cùng database transaction manager và cùng transaction boundary**.

Nếu insert outbox thất bại, transaction đặt hàng phải rollback để không có đơn hàng đã commit mà thiếu ý định gửi. Nếu lưu đơn hàng thất bại, outbox cũng không được commit. Không bắt exception insert outbox rồi bỏ qua, vì làm vậy sẽ phá vỡ bảo đảm của mô hình.

### Repository ghi outbox

Với Spring JDBC, có thể dùng một lệnh insert:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcMailOutboxRepository implements MailOutboxRepository {
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public JdbcMailOutboxRepository(
            JdbcTemplate jdbcTemplate,
            ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    @Override
    public void insert(
            UUID id,
            String eventKey,
            String aggregateType,
            String aggregateId,
            String eventType,
            String recipient,
            Object payload,
            int payloadVersion) {
        try {
            String json = objectMapper.writeValueAsString(payload);
            jdbcTemplate.update("""
                    INSERT INTO mail_outbox (
                        id, event_key, aggregate_type, aggregate_id,
                        event_type, recipient, payload, payload_version
                    )
                    VALUES (?, ?, ?, ?, ?, ?, CAST(? AS jsonb), ?)
                    """,
                    id, eventKey, aggregateType, aggregateId,
                    eventType, recipient, json, payloadVersion);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize mail outbox payload", ex);
        }
    }
}
~~~

Ví dụ SQL dùng cú pháp JSONB của PostgreSQL. JdbcTemplate tham gia transaction Spring hiện tại khi được cấu hình cùng DataSource/transaction manager. Không mở một connection độc lập hoặc tự commit ở repository này.

Nếu unique constraint của event_key vi phạm, hãy quyết định theo ngữ cảnh: đó có thể là command trùng đã được xử lý. Use case nên trả kết quả idempotent phù hợp hoặc phát hiện xung đột; không được tạo một event_key mới chỉ để insert lại và gửi email thêm lần nữa.

## 6. Payload nên chứa snapshot hay chỉ chứa aggregate ID?

Có hai cách lưu dữ liệu để worker dựng email.

**Snapshot payload** chứa các trường cần gửi tại thời điểm nghiệp vụ commit:

~~~json
{
  "orderId": "ORD-2026-001",
  "customerName": "Nguyễn Minh Anh",
  "recipient": "customer@example.test",
  "total": "2230000",
  "currency": "VND",
  "locale": "vi-VN"
}
~~~

Ưu điểm là nội dung email phản ánh trạng thái tại thời điểm phát sinh sự kiện. Nếu khách hàng đổi địa chỉ email hoặc đơn hàng thay đổi sau đó, worker vẫn có snapshot đã được lưu. Nhược điểm là payload có thể chứa dữ liệu cá nhân và cần quản lý schema/retention.

**Reference payload** chỉ chứa ID của đối tượng:

~~~json
{
  "orderId": "ORD-2026-001"
}
~~~

Worker truy vấn order khi xử lý. Payload nhỏ hơn và tránh lưu trùng dữ liệu, nhưng email có thể phản ánh trạng thái mới nhất thay vì trạng thái lúc sự kiện phát sinh. Đối tượng có thể bị xóa hoặc thay đổi trước khi worker chạy.

| Tiêu chí | Snapshot | Reference |
|---|---|---|
| Phản ánh trạng thái lúc commit | Rõ ràng | Không bảo đảm |
| Kích thước payload | Lớn hơn | Nhỏ hơn |
| Phụ thuộc truy vấn lại domain data | Ít hơn | Có |
| Dữ liệu nhạy cảm trong outbox | Có thể nhiều hơn | Có thể ít hơn |
| Phù hợp | Receipt, confirmation cần nội dung lịch sử | Thông báo cần trạng thái mới nhất |

Không có lựa chọn đúng cho mọi email. Hãy quyết định theo ý nghĩa nghiệp vụ, chính sách quyền riêng tư và khả năng lưu giữ dữ liệu.

### Version hóa payload

Outbox record có thể tồn tại lâu hơn một phiên bản ứng dụng. Nếu worker mới đọc payload cũ với schema đã đổi, việc deserialize có thể thất bại hoặc diễn giải sai dữ liệu. Dùng payload_version và giữ khả năng đọc các phiên bản còn tồn tại:

~~~java
public record OrderConfirmationPayloadV1(
        String orderId,
        String customerName,
        String recipient,
        String total,
        String currency,
        String locale) {
}
~~~

Khi thay đổi schema, tạo phiên bản mới và định tuyến deserialize theo payload_version. Không âm thầm đổi nghĩa một field đang được worker cũ/new cùng đọc.
## 7. Claim outbox record an toàn khi có nhiều worker

Một ứng dụng có thể chạy nhiều instance hoặc nhiều worker để tăng throughput. Nếu tất cả cùng truy vấn các bản ghi PENDING rồi gửi, cùng một email có thể được xử lý đồng thời nhiều lần.

Worker cần **claim** bản ghi trong một transaction ngắn. Database phải đảm bảo mỗi record chỉ được một worker giữ lease tại một thời điểm.

Với PostgreSQL, có thể dùng `FOR UPDATE SKIP LOCKED`:

~~~sql
WITH candidates AS (
    SELECT id
    FROM mail_outbox
    WHERE
        (status IN ('PENDING', 'RETRY')
            AND available_at <= CURRENT_TIMESTAMP)
        OR
        (status = 'CLAIMED'
            AND lease_until < CURRENT_TIMESTAMP)
    ORDER BY available_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 50
)
UPDATE mail_outbox AS item
SET status = 'CLAIMED',
    claimed_by = :worker_id,
    lease_token = gen_random_uuid(),
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    attempt_count = item.attempt_count + 1
FROM candidates
WHERE item.id = candidates.id
RETURNING
    item.id,
    item.event_key,
    item.event_type,
    item.recipient,
    item.payload,
    item.payload_version,
    item.attempt_count,
    item.lease_token,
    item.lease_until;
~~~

Ý nghĩa:

- `FOR UPDATE` khóa các row được chọn trong transaction claim.
- `SKIP LOCKED` cho phép worker khác bỏ qua row đang bị worker khác claim, thay vì chờ.
- `LIMIT` giới hạn batch size để một worker không chiếm quá nhiều công việc.
- `lease_until` xác định thời điểm claim hết hạn nếu worker chết hoặc không hoàn tất.
- `lease_token` nhận diện lần claim cụ thể, tránh worker cũ cập nhật trạng thái sau khi row đã được worker mới claim lại.
- `attempt_count` tăng khi worker nhận việc; cần thống nhất định nghĩa đây là số lần claim hay số lần thực sự gọi SMTP.

Hàm `gen_random_uuid()` có sẵn trong các phiên bản PostgreSQL hiện đại; nếu database chưa hỗ trợ, có thể sinh token trong ứng dụng và truyền vào câu lệnh claim theo cách phù hợp. SQL trên là ví dụ PostgreSQL, không dùng nguyên văn cho mọi hệ quản trị.

### Claim phải commit trước khi gửi SMTP

Nên tách thành một service transaction riêng:

~~~java
@Service
public class MailOutboxClaimService {
    private final MailOutboxJdbcRepository repository;

    public MailOutboxClaimService(
            MailOutboxJdbcRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<ClaimedMail> claimBatch(
            String workerId, int batchSize) {
        return repository.claim(workerId, batchSize);
    }
}
~~~

Khi phương thức trả về qua Spring transactional proxy, transaction claim đã kết thúc và commit. Worker sau đó mới gọi SMTP. Không đặt toàn bộ vòng poll, send và update trạng thái trong cùng một transaction dài.

Nếu dùng Spring Data JPA, có thể triển khai claim bằng native query hoặc repository tùy database. Với PostgreSQL và nhiều worker, `SKIP LOCKED` là một cơ chế phổ biến để tránh tranh chấp. Phải kiểm tra isolation level và hành vi locking của database đang dùng.

### Lease hết hạn và khôi phục công việc

Nếu worker bị kill sau khi claim, row không nên bị kẹt vĩnh viễn ở CLAIMED. Khi `lease_until` đã qua, một worker khác có thể claim lại.

Lease nên dài hơn thời gian gửi tối đa dự kiến, bao gồm timeout kết nối và timeout ghi SMTP. Với công việc lâu, worker có thể gia hạn lease định kỳ. Nếu lease quá ngắn, worker thứ hai có thể claim cùng email khi worker đầu vẫn đang gửi.

`lease_token` bảo vệ cập nhật trạng thái: worker chỉ được đánh dấu thành công/thất bại nếu token vẫn là token của lần claim mình giữ. Nó không ngăn được việc SMTP nhận cùng email hai lần nếu hai worker thực sự cùng gửi trong một khoảng thời gian.

## 8. Gửi mail ngoài transaction claim

Worker có thể điều phối như sau:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailOutboxWorker {
    private final MailOutboxClaimService claimService;
    private final OutboxMailSender mailSender;
    private final MailOutboxStateService stateService;

    public MailOutboxWorker(
            MailOutboxClaimService claimService,
            OutboxMailSender mailSender,
            MailOutboxStateService stateService) {
        this.claimService = claimService;
        this.mailSender = mailSender;
        this.stateService = stateService;
    }

    @Scheduled(fixedDelay = 1000)
    public void poll() {
        List<ClaimedMail> batch =
                claimService.claimBatch("mail-worker-1", 50);

        for (ClaimedMail item : batch) {
            try {
                mailSender.send(item);
                stateService.markSubmitted(
                        item.id(), item.leaseToken());
            } catch (RetryableMailException ex) {
                stateService.scheduleRetry(
                        item, ex.errorCode(), ex.retryAfter());
            } catch (PermanentMailException ex) {
                stateService.markDead(
                        item.id(), item.leaseToken(), ex.errorCode());
            } catch (UnknownSubmissionException ex) {
                stateService.markUnknown(
                        item.id(), item.leaseToken(), ex.errorCode());
            }
        }
    }
}
~~~

`ClaimedMail`, `OutboxMailSender`, các exception và state service là abstraction minh họa. Trong ứng dụng thực, cần cấu hình `@EnableScheduling`, worker ID ổn định theo instance và cơ chế ghi log/metrics. Nếu dùng nhiều worker thread trong một instance, mỗi worker cần claim token riêng.

Luồng này có ba ranh giới transaction:

1. **Claim transaction:** chọn row và đặt lease, sau đó commit.
2. **SMTP call:** thực hiện ngoài database transaction.
3. **State transaction:** cập nhật SUBMITTED, RETRY, DEAD hoặc UNKNOWN sau khi có kết quả.

### Cập nhật trạng thái phải kiểm tra lease token

Khi SMTP chấp nhận message:

~~~sql
UPDATE mail_outbox
SET status = 'SUBMITTED',
    submitted_at = CURRENT_TIMESTAMP,
    claimed_by = NULL,
    lease_token = NULL,
    lease_until = NULL,
    last_error_code = NULL,
    last_error_at = NULL
WHERE id = :id
  AND status = 'CLAIMED'
  AND lease_token = :lease_token;
~~~

Worker cần kiểm tra số row được update. Nếu bằng 0, claim đã hết hạn hoặc row đã được worker khác thay đổi; không được ghi đè trạng thái mới bằng kết quả cũ.

Khi cần retry:

~~~sql
UPDATE mail_outbox
SET status = 'RETRY',
    available_at = :next_attempt_at,
    last_error_code = :error_code,
    last_error_at = CURRENT_TIMESTAMP,
    claimed_by = NULL,
    lease_token = NULL,
    lease_until = NULL
WHERE id = :id
  AND status = 'CLAIMED'
  AND lease_token = :lease_token;
~~~

Các câu lệnh state update cũng phải chạy trong transaction ngắn. Không cập nhật row chỉ dựa trên ID nếu có khả năng claim cũ đã hết hạn và một worker khác đã nhận việc.

## 9. Retry có giới hạn và backoff

SMTP provider có thể tạm thời từ chối kết nối, giới hạn tốc độ hoặc gặp lỗi mạng. Worker nên phân loại lỗi và lên lịch retry thay vì lặp liên tục.

Một chính sách phổ biến là **exponential backoff có jitter**:

~~~text
delay = min(maxDelay, baseDelay * 2^(attempt - 1))
nextAttempt = now + delay + randomJitter
~~~

Ví dụ với base delay 10 giây, max delay 30 phút:

| Lần thử | Delay cơ sở trước jitter |
|---|---:|
| 1 | 10 giây |
| 2 | 20 giây |
| 3 | 40 giây |
| 4 | 80 giây |
| 5 | 160 giây |
| 6 | 320 giây |
| Các lần sau | Tăng đến tối đa 30 phút |

Jitter ngẫu nhiên giúp nhiều worker không cùng retry đồng loạt sau khi provider phục hồi. Nếu provider trả Retry-After hoặc hướng dẫn thời gian thử lại, chính sách có thể tôn trọng giá trị đó trong giới hạn cấu hình.

### Không retry mọi lỗi

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Connection refused, timeout trước khi truyền message, SMTP 4xx | Retry có backoff |
| Có thể khắc phục sau khi đổi cấu hình | Sai credential, TLS config không phù hợp | Dừng retry dồn dập, cảnh báo vận hành |
| Vĩnh viễn theo message/recipient | Địa chỉ sai, SMTP 5xx recipient rejected | DEAD hoặc cần xử lý thủ công |
| Nội dung không hợp lệ | Template thiếu biến, attachment không đọc được | Sửa dữ liệu/template; không retry SMTP vô ích |
| Kết quả không chắc chắn | Timeout sau khi DATA đã được truyền, client không nhận được phản hồi cuối | UNKNOWN hoặc retry theo chính sách chấp nhận rủi ro trùng |

Các exception của Spring Mail không phải lúc nào cũng đủ để xác định chính xác SMTP đã chấp nhận message hay chưa. Có thể cần xem nguyên nhân gốc, mã SMTP, giai đoạn giao thức và khả năng đối soát với provider.

### Trạng thái DEAD và xử lý thủ công

Sau số lần thử tối đa, hoặc khi lỗi được xác định là vĩnh viễn, có thể chuyển record sang DEAD. Cần lưu mã lỗi đã chuẩn hóa, thời điểm, attempt count và thông tin chẩn đoán an toàn. Một công cụ vận hành có thể cho phép:

- Xem các record DEAD theo loại email và thời điểm.
- Kiểm tra payload đã được khử nhạy cảm.
- Sửa dữ liệu nguồn hoặc cấu hình.
- Tạo một lần phát lại có kiểm soát và ghi audit.

Không nên tự động retry vô hạn. Nó có thể tạo tải liên tục, làm tăng chi phí và khiến provider khóa tài khoản gửi.
## 10. Outbox không bảo đảm exactly-once qua SMTP

Transactional outbox giúp ứng dụng không làm mất **ý định gửi** giữa lúc commit database và lúc worker bắt đầu xử lý. Tuy nhiên, còn một khoảng trống khác:

~~~text
Worker gửi message
       |
       v
SMTP server trả 250 Accepted
       |
       v
Worker bị crash trước khi cập nhật outbox
       |
       v
Lease hết hạn, worker khác claim lại
       |
       v
Email có thể được gửi lần thứ hai
~~~

Database chưa ghi nhận SUBMITTED, trong khi SMTP có thể đã nhận message. Khi worker retry, ứng dụng không thể biết chắc lần trước đã được server chấp nhận hay chưa.

Đây là lý do outbox thường cung cấp **at-least-once processing**: record được xử lý lại cho đến khi đạt trạng thái cuối hoặc cần can thiệp. Nó không tự cung cấp **exactly-once delivery**.

### Vì sao Message-ID không giải quyết hoàn toàn duplicate?

Ứng dụng có thể tạo một Message-ID ổn định cho mỗi outbox event và giữ nguyên khi retry:

~~~java
helper.setMessageId(
        "<" + outboxEventId + "@mail.example.test>");
~~~

Message-ID hữu ích cho việc đối soát và nhận diện cùng một message. Tuy nhiên, SMTP chuẩn không bắt buộc server hoặc mailbox client phải loại bỏ các message trùng Message-ID. Vì vậy, không coi Message-ID là cơ chế idempotency được bảo đảm.

Nếu dùng email provider qua HTTP API có hỗ trợ **idempotency key**, hãy truyền event key ổn định và tuân theo thời hạn/lược đồ idempotency của provider. Khả năng này phụ thuộc nhà cung cấp; không phải API gửi email nào cũng có.

### Giảm rủi ro gửi trùng

- Tạo event_key ổn định và unique trong database để tránh tạo nhiều ý định gửi cho cùng một sự kiện.
- Giữ nguyên Message-ID giữa các lần retry để hỗ trợ trace và đối soát.
- Nếu provider hỗ trợ idempotency key, dùng outbox event ID làm key.
- Ghi trạng thái UNKNOWN khi không thể xác định submission đã thành công hay chưa.
- Với email không được phép gửi trùng, thiết kế quy trình đối soát hoặc xác nhận thủ công cho trạng thái không chắc chắn.
- Không retry mù một message có thể đã được SMTP chấp nhận nếu tác động gửi trùng rất lớn.

**Idempotency của việc tạo outbox record** và **idempotency của việc gửi ra SMTP** là hai vấn đề khác nhau. Unique event key giải quyết việc tạo ý định trùng trong database; nó không thể thu hồi một message đã được SMTP nhận.

## 11. Trạng thái UNKNOWN và quyết định retry

Khi SMTP client nhận được lỗi trước khi bắt đầu truyền nội dung, có thể kết luận submission chưa hoàn tất và retry thường an toàn hơn. Nhưng nếu connection mất sau khi client đã gửi phần DATA và trước khi nhận phản hồi cuối, trạng thái trở nên không chắc chắn.

Ví dụ:

~~~text
Client                         SMTP server
  |                                  |
  |------ MAIL FROM ---------------->|
  |------ RCPT TO ------------------>|
  |------ DATA --------------------->|
  |------ message body ------------>|
  |------ <CRLF>.<CRLF> ------------>|
  |                                  | Có thể đã lưu message
  |       Connection lost            |
  X                                  |
~~~

Worker không biết server đã commit message vào queue hay chưa. Có hai lựa chọn:

| Chính sách | Hành vi | Rủi ro |
|---|---|---|
| Retry ngay | Tăng khả năng cuối cùng có email | Có thể gửi trùng |
| Đưa vào UNKNOWN để đối soát | Tránh gửi lại mù | Có thể trì hoãn hoặc bỏ sót email nếu server thực ra chưa nhận |

Lựa chọn phụ thuộc ý nghĩa thông báo. Email thông tin ít ảnh hưởng có thể ưu tiên retry; email liên quan mã giao dịch, xác nhận thanh toán hoặc thông báo nhạy cảm có thể cần đối soát trước.

Không phải mọi MailSendException đều đồng nghĩa với trạng thái UNKNOWN. Cần xem nested cause, mã SMTP, giai đoạn lỗi và khả năng đối soát với provider. Hãy phân loại theo bằng chứng kỹ thuật, không chỉ dựa vào tên exception.

## 12. Bảo đảm thứ tự email theo đối tượng nghiệp vụ

Nhiều worker dùng SKIP LOCKED có thể xử lý các outbox record theo thứ tự khác nhau. Ví dụ một đơn hàng phát sinh:

1. ORDER_CONFIRMED.
2. ORDER_SHIPPED.
3. ORDER_DELIVERED.

Nếu record đầu bị retry còn record sau sẵn sàng, worker khác có thể gửi ORDER_SHIPPED trước ORDER_CONFIRMED. Nếu thứ tự thông báo có ý nghĩa, cần thiết kế thêm.

Một số cách:

- Lưu aggregate_version hoặc sequence number cho từng event.
- Chỉ claim event chưa xử lý sớm nhất của mỗi aggregate.
- Phân vùng worker theo aggregate ID để cùng một aggregate đi qua cùng luồng.
- Dùng một hàng đợi có partition key theo aggregate nếu chuyển tiếp sang broker.

Ví dụ điều kiện logic:

~~~text
ORDER_CONFIRMED sequence=1
ORDER_SHIPPED   sequence=2
ORDER_DELIVERED sequence=3

Chỉ cho phép sequence=2 xử lý khi sequence=1
đã đạt trạng thái cuối được nghiệp vụ chấp nhận.
~~~

Không phải email nào cũng cần thứ tự tuyệt đối. Nếu hai thông báo độc lập, cho phép xử lý song song sẽ tăng throughput và giảm độ trễ. Chỉ thêm serialization khi thứ tự thực sự là yêu cầu nghiệp vụ.

## 13. Worker cần được vận hành và quan sát như một thành phần riêng

Outbox là một cơ chế bền vững, nhưng nếu không có worker hoặc worker ngừng chạy, email vẫn nằm chờ. Hệ thống cần theo dõi tình trạng backlog và thời gian xử lý.

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| outbox_pending_count | Số record đang chờ |
| outbox_oldest_pending_age | Tuổi của record chờ lâu nhất |
| outbox_claimed_count | Số record đang có lease |
| outbox_expired_lease_count | Số lease đã hết hạn |
| outbox_retry_count | Số record đang retry |
| outbox_dead_count | Số record cần xử lý thủ công |
| outbox_unknown_count | Số submission chưa xác định kết quả |
| mail_submission_success_total | Số lần SMTP submission được chấp nhận |
| mail_submission_failure_total | Số lần submission thất bại |
| mail_submission_duration | Thời gian gửi qua SMTP |

Nên theo dõi cả **backlog age** thay vì chỉ đếm số record. Một outbox có 100 record mới tạo có thể bình thường; một record quan trọng đã chờ nhiều giờ có thể là sự cố.

### Log có correlation ID

Mỗi outbox record nên có ID ổn định để nối log giữa:

~~~text
HTTP request
  -> orderId
  -> outboxEventId
  -> workerId
  -> SMTP submission attempt
  -> provider message reference (nếu có)
~~~

Có thể ghi event_key, aggregate_id, attempt_count, worker_id, status transition và mã lỗi đã chuẩn hóa. Không ghi password, access token, toàn bộ HTML body, token reset hoặc dữ liệu người nhận không cần thiết vào log.

### Cảnh báo vận hành

- Pending age vượt ngưỡng.
- Worker không poll hoặc không có heartbeat.
- Retry tăng đột biến.
- DEAD/UNKNOWN xuất hiện hoặc tăng nhanh.
- SMTP provider trả lỗi xác thực, quota hoặc throttling.
- Lease hết hạn liên tục, có thể worker bị treo hoặc thời gian xử lý vượt cấu hình.

Một dashboard tốt cho phép xem trạng thái theo loại email, provider, thời gian và nguyên nhân lỗi mà không tiết lộ nội dung riêng tư.

## 14. Quản lý vòng đời dữ liệu outbox

Outbox có thể tăng liên tục. Cần có chính sách lưu trữ:

- Giữ record PENDING, CLAIMED, RETRY, DEAD và UNKNOWN theo nhu cầu vận hành.
- Record SUBMITTED có thể được archive hoặc xóa sau thời hạn audit đã thống nhất.
- Giữ đủ thời gian để đối soát, điều tra duplicate và xử lý khiếu nại.
- Không xóa record còn lease hoặc đang retry.
- Nếu cần lưu audit lâu dài, chuyển metadata tối thiểu sang bảng archive thay vì giữ payload nhạy cảm vô thời hạn.

Với PostgreSQL, các index partial trên trạng thái sẵn sàng và lease giúp query worker tránh quét toàn bảng. Tuy nhiên, khi dữ liệu tăng lớn, cần xem query plan, vacuum, bloat và chiến lược partition/archival. Không thêm index trên mọi cột vì mỗi index làm tăng chi phí insert/update.

### Tránh lưu dữ liệu nhạy cảm lâu hơn cần thiết

Payload có thể chứa email, tên, tổng tiền, địa chỉ hoặc token. Hãy:

- Chỉ lưu các field cần để tạo email.
- Mã hóa hoặc bảo vệ cột/payload theo yêu cầu dữ liệu.
- Giới hạn quyền đọc bảng outbox cho worker và công cụ vận hành.
- Không đưa secret hoặc token có thời hạn dài vào payload.
- Xóa hoặc rút gọn payload sau khi xử lý nếu không cần audit nội dung.
- Áp dụng retention đồng bộ với chính sách dữ liệu của ứng dụng.

## 15. Khi nào dùng polling và khi nào dùng CDC/message broker?

Một worker có thể polling trực tiếp bảng outbox bằng SQL. Với lưu lượng vừa phải, đây là cách đơn giản và dễ vận hành. Khi hệ thống cần nhiều consumer hoặc thông lượng cao, có thể dùng **Change Data Capture (CDC)** để đọc thay đổi của outbox rồi phát sang message broker.

~~~mermaid
flowchart TD
    A[Business transaction] --> B[Business table + Outbox table]
    B --> C{Cách dispatch}
    C --> D[Polling worker]
    C --> E[CDC connector]
    D --> F[Mail sender]
    E --> G[Message broker]
    G --> H[Mail consumer]
    H --> F
    F --> I[SMTP / Email provider]
~~~

| Tiêu chí | Polling | CDC + broker |
|---|---|---|
| Thành phần cần vận hành | Database và worker | Database log, connector, broker, consumer |
| Độ trễ | Theo chu kỳ poll | Có thể thấp hơn |
| Độ phức tạp | Thấp hơn | Cao hơn |
| Nhiều consumer | Cần mở rộng logic claim/dispatch | Broker hỗ trợ fan-out/partition |
| Phù hợp | Ứng dụng vừa/nhỏ, ít loại event | Hệ thống phân tán, nhiều consumer, throughput cao |

CDC không làm mất đi nhu cầu idempotency. Connector hoặc consumer có thể phát lại record sau restart; mail consumer vẫn phải xử lý duplicate và lưu trạng thái theo event ID.

Nếu dùng broker, một mô hình phổ biến là outbox dispatcher/CDC phát event sang broker; consumer gửi email. Khi broker đã nhận event nhưng dispatcher chưa ghi nhận offset/position, event có thể được phát lại. Consumer phải có deduplication phù hợp.

**Không cần thêm Kafka chỉ để gửi một email xác nhận đơn hàng** nếu polling worker đáp ứng được tải và yêu cầu vận hành. Chọn kiến trúc theo throughput, số consumer, latency và khả năng đội ngũ vận hành.

## 16. Kiểm thử transactional outbox

Test quan trọng nhất là chứng minh dữ liệu nghiệp vụ và outbox record có cùng kết quả transaction.

### Test transaction commit

Khi use case thành công:

~~~java
@Test
void savesOrderAndOutboxTogether() {
    UUID orderId = placeOrderService.placeOrder(validCommand);

    assertThat(orderRepository.findById(orderId)).isPresent();
    assertThat(outboxRepository.findByAggregateId(orderId.toString()))
            .hasSize(1);
}
~~~

Đây là ví dụ integration test; repository và database cần dùng cùng transaction manager. Nếu test method tự được đánh dấu @Transactional và rollback ở cuối test, dữ liệu có thể không tồn tại sau khi test kết thúc. Hãy hiểu rõ transaction của test và transaction của use case trước khi assert.

### Test outbox insert lỗi làm transaction rollback

Giả lập lỗi ở bước insert outbox và xác nhận đơn hàng không được commit:

~~~java
@Test
void rollsBackOrderWhenOutboxInsertFails() {
    doThrow(new IllegalStateException("outbox unavailable"))
            .when(outboxRepository)
            .insert(any(), any(), any(), any(), any(), any(), any(), anyInt());

    assertThatThrownBy(() -> placeOrderService.placeOrder(validCommand))
            .isInstanceOf(IllegalStateException.class);

    assertThat(orderRepository.findAll()).isEmpty();
}
~~~

Test minh họa cần chạy với transaction/database thật để xác minh rollback. Nếu chỉ mock cả order repository và outbox repository, test chỉ xác nhận luồng gọi, không chứng minh atomicity.

### Test worker gửi thành công

Với một outbox record PENDING, worker claim, gửi thành công và cập nhật SUBMITTED. Có thể mock Mail sender để xác nhận đúng payload/recipient, nhưng phần state transition nên kiểm tra với database test:

~~~java
@Test
void marksRecordSubmittedAfterSuccessfulSend() {
    ClaimedMail claimed = claimService.claimOne("worker-test");

    worker.process(claimed);

    assertThat(outboxRepository.findById(claimed.id()).orElseThrow()
            .status()).isEqualTo("SUBMITTED");
}
~~~

### Test retry và DEAD

- Lỗi tạm thời làm status thành RETRY, available_at nằm trong tương lai.
- Lỗi vĩnh viễn làm status thành DEAD.
- Quá số lần thử tối đa không tiếp tục retry vô hạn.
- Khi lease token không còn khớp, worker cũ không thể cập nhật trạng thái.
- Lease hết hạn cho phép worker mới claim lại.

### Test cạnh tranh giữa nhiều worker

Chạy hai worker đồng thời trên nhiều outbox record và xác nhận:

- Một record chỉ được claim bởi một worker tại cùng thời điểm.
- Worker thứ hai bỏ qua row đang lock.
- Các record không bị mất khi một worker dừng.
- Batch size và lease hoạt động đúng dưới tải.

Test này cần database hỗ trợ đúng câu lệnh locking được dùng. H2 có thể không tái hiện đầy đủ hành vi PostgreSQL SKIP LOCKED; nên dùng Testcontainers PostgreSQL hoặc database integration phù hợp khi kiểm tra locking thật.

### Test crash window sau SMTP acceptance

Mô phỏng worker gửi thành công nhưng crash trước state update. Khi lease hết hạn, record có thể được xử lý lại. Test cần chứng minh hệ thống thể hiện rõ **rủi ro duplicate** và áp dụng idempotency/deduplication theo khả năng provider, thay vì khẳng định exactly-once.

## 17. Các lỗi thiết kế thường gặp

**Ghi outbox bằng REQUIRES_NEW.** Nếu outbox được commit trong transaction riêng còn transaction đơn hàng rollback, hệ thống có thể gửi email cho đơn hàng không tồn tại. Outbox insert phải tham gia transaction nghiệp vụ; propagation REQUIRED thường phù hợp khi cùng transaction manager.

**Ghi outbox ở một database khác.** Hai DataSource độc lập không tự atomic chỉ vì cùng nằm trong một phương thức @Transactional. Muốn cùng rollback/commit cần một cơ chế phân tán phù hợp; transactional outbox truyền thống giả định business data và outbox cùng transaction database.

**Gửi SMTP trong transaction ghi nghiệp vụ.** Việc này kéo network latency vào transaction và tạo tình huống email gửi rồi database rollback. Worker gửi sau commit để giữ ranh giới.

**Claim rồi giữ transaction trong lúc send.** SMTP có thể chậm hoặc timeout, khiến row lock và connection bị giữ lâu. Claim/commit trước, send ngoài transaction, update trạng thái trong transaction mới.

**Không có lease hoặc cơ chế phục hồi.** Worker crash có thể để row CLAIMED mãi mãi. Dùng lease hết hạn và quy trình reclaim có kiểm soát.

**Lease quá ngắn.** Worker thứ hai có thể reclaim trong khi worker đầu đang gửi. Lease phải tương thích timeout, batch size và thời gian xử lý; với tác vụ dài cần heartbeat gia hạn.

**Không kiểm tra lease token khi update.** Worker cũ có thể ghi đè kết quả của worker mới. Mỗi lần claim nên có token riêng và mọi state update cần điều kiện theo token.

**Retry vô hạn hoặc không phân loại lỗi.** Lỗi template, credential sai và recipient không hợp lệ không được xử lý giống timeout tạm thời. Dùng retry policy, max attempts và DEAD/UNKNOWN.

**Tuyên bố exactly-once.** Outbox không loại bỏ khoảng trống giữa SMTP acceptance và database update. Hãy công khai khả năng duplicate và dùng idempotency nếu provider hỗ trợ.

**Không version hóa payload.** Record cũ có thể không deserialize được sau khi deploy phiên bản mới. Dùng payload_version và giữ backward compatibility trong thời gian record còn tồn tại.

**Lưu toàn bộ MIME message trong outbox mà không có chính sách dữ liệu.** HTML, attachment và token có thể chứa thông tin nhạy cảm. Chỉ lưu payload cần thiết, bảo vệ truy cập và áp dụng retention.

## 18. Lộ trình triển khai trong Spring Framework Mail

Một cách triển khai theo từng bước:

1. Xác định loại email cần bảo đảm bền vững và thời điểm nghiệp vụ phát sinh.
2. Thiết kế bảng outbox, status, event key, payload version và index.
3. Tạo repository ghi outbox bằng cùng DataSource/transaction manager với dữ liệu nghiệp vụ.
4. Trong use case @Transactional, lưu dữ liệu nghiệp vụ và insert outbox record.
5. Tạo claim service dùng locking/lease phù hợp database.
6. Tạo worker lấy batch, commit claim rồi gọi mail adapter ngoài transaction.
7. Tạo state service để đánh dấu SUBMITTED, RETRY, DEAD hoặc UNKNOWN bằng lease token.
8. Thêm backoff, jitter, giới hạn retry và chính sách xử lý lỗi không chắc chắn.
9. Thêm metrics, log correlation, cảnh báo backlog và quy trình replay có audit.
10. Kiểm thử commit/rollback, nhiều worker, lease expiry, lỗi SMTP và crash window.
11. Đặt chính sách retention và bảo vệ payload.

### Ranh giới giữa các thành phần

~~~text
Application layer
  PlaceOrderService
      |
      +--> OrderRepository
      |
      +--> MailOutboxRepository
                |
                v
          Database transaction

Infrastructure
  MailOutboxClaimService
      |
      v
  MailOutboxWorker
      |
      +--> Template renderer
      |
      +--> MimeMessageHelper
      |
      +--> JavaMailSender
                |
                v
             SMTP
~~~

Application service biết **khi nào cần gửi** và ghi ý định gửi. Worker biết **khi nào xử lý record**. Mail adapter biết **cách dựng và gửi email**. Cách phân chia này giúp thay SMTP provider hoặc template mà không làm thay đổi transaction nghiệp vụ.

## 19. Khi nào không cần transactional outbox?

Outbox thêm schema, worker, retry, trạng thái và công cụ vận hành. Không phải mọi email đều cần mức đảm bảo này.

Có thể chọn cách đơn giản hơn khi:

- Email chỉ mang tính tiện ích và có thể gửi lại bằng thao tác thủ công.
- Mất một email không làm sai dữ liệu hoặc quyền lợi nghiệp vụ.
- Ứng dụng có lưu lịch sử thông báo theo cách khác và chấp nhận khoảng trống gửi.
- Lưu lượng thấp, rủi ro mất email nhỏ và chi phí vận hành outbox lớn hơn lợi ích.

Nên cân nhắc outbox khi:

- Email phản ánh giao dịch đã commit như đơn hàng, thanh toán hoặc thay đổi tài khoản.
- Không được mất yêu cầu gửi khi process restart.
- Cần retry và audit trạng thái gửi.
- Có nhiều worker hoặc nhiều instance cùng xử lý.
- Hệ thống cần tách latency SMTP khỏi HTTP request.

Quyết định nên dựa trên **hậu quả nếu email không được gửi hoặc bị gửi trùng**, yêu cầu audit và khả năng vận hành, không chỉ dựa vào việc ứng dụng đã có Spring Mail.

## 20. Nguyên tắc cần nhớ

Transactional outbox ghi **dữ liệu nghiệp vụ và ý định gửi mail trong cùng transaction database**. Sau commit, worker claim record bằng lease, gửi email qua JavaMailSender ngoài transaction và cập nhật trạng thái bằng một transaction ngắn khác.

Thiết kế cần có event key để chống tạo ý định trùng, lease/token để phối hợp nhiều worker, retry có giới hạn, trạng thái UNKNOWN cho kết quả SMTP không chắc chắn, và chính sách retention/bảo vệ payload. Nếu cần thứ tự theo aggregate, phải bổ sung sequence hoặc cơ chế phân vùng phù hợp.

**Outbox bảo đảm yêu cầu gửi được lưu bền vững cùng nghiệp vụ; SMTP vẫn có thể nhận trùng khi worker crash sau acceptance.** Hãy thiết kế và vận hành theo semantics đó, dùng idempotency của provider nếu có và không khẳng định exactly-once delivery khi SMTP không cung cấp bảo đảm này.
