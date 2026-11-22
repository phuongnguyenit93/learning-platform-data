# Lưu trạng thái xử lý idempotent và thời hạn chống trùng

Trong serverless, một request hoặc message có thể được gửi lại khi client timeout, function bị dừng giữa chừng, queue giao message nhiều lần hoặc hệ thống retry sau lỗi tạm thời. Nếu mỗi lần nhận đều tạo đơn hàng, thu tiền hoặc gửi notification mới, một thao tác nghiệp vụ có thể tạo ra nhiều side effect.

**Idempotency** giúp một thao tác được gửi nhiều lần vẫn tạo ra một kết quả nghiệp vụ duy nhất trong phạm vi đã định nghĩa. Để đạt được điều đó, hệ thống cần lưu trạng thái xử lý bền vững theo một khóa ổn định, phối hợp các request đồng thời bằng thao tác atomic, và giữ bản ghi đủ lâu để bao phủ toàn bộ khoảng retry/redelivery/replay có thể xảy ra.

Bài học này tập trung vào cách lưu idempotency state trong database hoặc kho dữ liệu dùng chung, chọn khóa và fingerprint, xử lý trạng thái PROCESSING/SUCCEEDED, phục hồi worker bị chết bằng lease, xác định retention window và bảo vệ side effect bên ngoài. Các ví dụ dùng Java và SQL để minh họa cho HTTP function, queue consumer và event-driven workflow.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao retry và at-least-once delivery đòi hỏi idempotency state bền vững.
- Phân biệt idempotency, duplicate detection và exactly-once processing.
- Thiết kế idempotency key có scope theo tenant, operation và business action.
- Dùng request fingerprint để phát hiện cùng key nhưng payload khác.
- Lưu trạng thái xử lý bằng unique constraint và atomic claim.
- Chọn transaction ngắn cho thao tác đồng bộ hoặc lease cho công việc dài hạn.
- Xử lý request lặp khi bản ghi đang PROCESSING hoặc đã SUCCEEDED.
- Tính retention window từ client retry, queue retention, redelivery, DLQ và replay.
- Phân biệt logical expiry với thời điểm TTL storage xóa vật lý bản ghi.
- Bảo vệ side effect bên ngoài bằng downstream idempotency, outbox và saga.
- Kiểm thử race condition, crash window, retry và hết hạn chống trùng.

## 1. Vì sao phải lưu trạng thái idempotent?

Một function có thể hoàn tất nghiệp vụ nhưng response không đến được caller. Caller chỉ nhìn thấy timeout nên gửi lại cùng request. Một queue consumer có thể xử lý message xong nhưng chết trước khi acknowledgement được ghi nhận; broker giao lại message. Một workflow có thể retry task vì không nhận được kết quả dù side effect ở hệ thống đích đã xảy ra.

Ví dụ:

1. Client gửi `POST /orders` với yêu cầu tạo đơn.
2. Function ghi đơn hàng và trả HTTP response.
3. Mạng bị ngắt trước khi client nhận response.
4. Client retry vì không biết lần đầu đã thành công chưa.
5. Nếu function tạo order mới, một yêu cầu của người dùng tạo hai đơn.

Một ví dụ khác với thanh toán:

1. Function gọi payment provider.
2. Provider đã charge thẻ thành công.
3. Function timeout trước khi lưu kết quả hoặc trả response.
4. Queue giao lại message.
5. Function gọi charge lần nữa.

Trong cả hai tình huống, chỉ kiểm tra trạng thái trong RAM hoặc biến static không đủ. Instance có thể bị thu hồi, invocation khác có thể chạy trên JVM khác và nhiều request có thể đến đồng thời.

### Idempotency không đồng nghĩa exactly-once

- **Idempotency:** lặp lại cùng một thao tác với cùng khóa và cùng ý nghĩa không tạo thêm kết quả nghiệp vụ.
- **Duplicate detection:** nhận diện một event/request đã thấy trước đó.
- **At-least-once delivery:** hệ thống có thể giao lại một message cho đến khi được xác nhận hoặc hết chính sách retry.
- **Exactly-once effect:** hiệu ứng nghiệp vụ chỉ xảy ra một lần trong phạm vi được bảo đảm. Đây thường là thuộc tính được xây bằng transaction, idempotency và giao thức giữa các hệ thống; không thể suy ra chỉ từ việc broker có deduplication.

Idempotency cần được đặt ở ranh giới có thể tạo side effect. Queue FIFO, broker deduplication hoặc retry policy có thể giảm duplicate, nhưng không thay thế trạng thái idempotency ở consumer và dịch vụ đích.

## 2. Xác định phạm vi của một idempotent operation

Trước khi tạo key, cần xác định chính xác “cùng một thao tác” nghĩa là gì.

Một key nên được scope theo những yếu tố cần phân biệt, thường gồm:

- Tenant hoặc account sở hữu yêu cầu.
- Operation hoặc endpoint, ví dụ `orders.create` hay `payments.capture`.
- Idempotency key do client/producer cung cấp hoặc do hệ thống tạo và lưu cùng event.
- Business entity/action nếu key được suy ra từ nghiệp vụ, ví dụ order ID + capture attempt.

Không dùng một key toàn cục không có scope nếu hai tenant hoặc hai loại operation có thể vô tình trùng chuỗi key.

Ví dụ cùng chuỗi `req-123` có thể hợp lệ cho hai tenant khác nhau, nhưng phải được lưu thành hai phạm vi độc lập:

~~~text
tenant-A | orders.create   | req-123
tenant-B | orders.create   | req-123
tenant-A | payments.capture| req-123
~~~

Một schema thường dùng unique key tổng hợp:

~~~sql
UNIQUE (tenant_id, operation, idempotency_key)
~~~

Nếu key được tạo từ business ID, hãy xác định nó đại diện cho một hành động cụ thể. Một order có thể có nhiều lần thanh toán hợp lệ, do đó `orderId` đơn lẻ có thể quá rộng; cần phân biệt `payment.capture`, `payment.refund` hoặc attempt tương ứng.

### Key phải ổn định qua retry

Với HTTP, client tạo key một lần cho thao tác và gửi lại đúng key khi retry. Không tạo UUID mới mỗi lần client thử lại.

Với event, producer tạo event ID khi event được ghi nhận và giữ nguyên ID qua các lần publish retry hoặc replay. Nếu outbox worker tạo event ID mới mỗi lần gửi, consumer không thể nhận diện duplicate.

Với workflow, idempotency key nên phản ánh business action, không chỉ execution attempt. Một retry của cùng task phải dùng lại key; một hành động nghiệp vụ mới cần key mới.

### Key cần khó đoán và không chứa dữ liệu nhạy cảm

Client có thể dùng UUID ngẫu nhiên đủ entropy. Không đưa email, số thẻ, access token hoặc thông tin cá nhân trực tiếp vào key. Nếu key được tạo từ dữ liệu nghiệp vụ, cân nhắc HMAC với secret được quản lý an toàn và bảo đảm key không thể bị dùng để suy ra dữ liệu gốc.

Key không phải cơ chế xác thực. Caller vẫn phải được xác thực và phân quyền trước khi đọc hoặc replay kết quả đã lưu.

## 3. Request fingerprint: phát hiện key bị dùng sai

Cùng một idempotency key phải đại diện cho cùng một yêu cầu nghiệp vụ. Nếu client gửi key cũ nhưng payload khác, hệ thống không nên âm thầm trả kết quả cũ hoặc thực hiện yêu cầu mới.

Lưu một **request fingerprint** (hash của dữ liệu đã chuẩn hóa) cùng key:

| Trường | Vai trò |
|---|---|
| `idempotency_key` | Nhận diện lần thao tác logic |
| `request_hash` | Phát hiện payload khác khi key được tái sử dụng |
| `operation` | Phân biệt loại hành động |
| `tenant_id` | Cô lập phạm vi |
| `status` | Trạng thái xử lý |
| `response/result` | Kết quả được replay cho request lặp |

Fingerprint nên được tạo từ các trường có ảnh hưởng đến kết quả nghiệp vụ sau khi normalize. Không hash JSON thô nếu thứ tự property, whitespace, format số hoặc biểu diễn ngày có thể khác nhau dù ý nghĩa giống nhau.

Ví dụ, hai payload sau có thể mang cùng ý nghĩa:

~~~json
{"orderId":"ord-7","quantity":2}
~~~

~~~json
{
  "quantity": 2,
  "orderId": "ord-7"
}
~~~

Hash byte của hai chuỗi JSON khác nhau. Có thể canonicalize JSON, hoặc tốt hơn là tạo một biểu diễn chuẩn từ command đã validate:

~~~java
public record CreateOrderFingerprintInput(
        String tenantId,
        String customerId,
        String currency,
        java.util.List<LineFingerprint> lines) {
}

public record LineFingerprint(
        String sku,
        int quantity,
        long unitPriceMinor) {
}
~~~

Thứ tự line item có thể có ý nghĩa hoặc không tùy contract. Nếu không có ý nghĩa, cần sắp xếp ổn định trước khi hash; nếu có ý nghĩa, giữ nguyên thứ tự. Không tự normalize làm thay đổi semantics.

### Java: tạo SHA-256 fingerprint

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class RequestFingerprint {
    private RequestFingerprint() {
    }

    public static String sha256(String canonicalPayload) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(canonicalPayload.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is unavailable", impossible);
        }
    }
}
~~~

Hàm trên giả định `canonicalPayload` đã được tạo ổn định từ command đã validate. Không đưa secret hoặc dữ liệu thanh toán thô vào fingerprint input nếu không cần. SHA-256 fingerprint dùng để so sánh payload; nó không phải chữ ký xác thực request.

Khi một key đã tồn tại:
- Hash giống nhau: đây là retry/duplicate của cùng thao tác.
- Hash khác nhau: trả lỗi conflict theo API contract, thường là HTTP 409, và không chạy nghiệp vụ.

Không thay fingerprint cũ bằng fingerprint mới khi key bị tái sử dụng.

## 4. Lưu idempotency state bền vững

Idempotency record cần nằm trong kho dữ liệu dùng chung mà mọi instance xử lý cùng scope có thể truy cập. Với thao tác tài chính hoặc ghi dữ liệu quan trọng, database có transaction và unique constraint thường là lựa chọn phù hợp.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id          VARCHAR(100) NOT NULL,
    operation          VARCHAR(100) NOT NULL,
    idempotency_key    VARCHAR(200) NOT NULL,
    request_hash       CHAR(64) NOT NULL,
    status             VARCHAR(20) NOT NULL,
    response_status    INTEGER,
    response_body      JSONB,
    result_reference   VARCHAR(300),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at         TIMESTAMPTZ NOT NULL,
    lease_owner        UUID,
    lease_until        TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, operation, idempotency_key),
    CHECK (status IN ('PROCESSING', 'SUCCEEDED', 'FAILED_RETRYABLE', 'FAILED_FINAL'))
);

CREATE INDEX idx_idempotency_expiry
    ON idempotency_record (expires_at);
~~~

Giải thích:

- Primary key ngăn hai instance tạo hai record cho cùng key/scope.
- `request_hash` phát hiện key bị dùng với payload khác.
- `status` thể hiện tiến trình xử lý.
- `response_status` và `response_body` cho phép trả lại kết quả cũ nếu API cần replay response.
- `result_reference` có thể trỏ đến order/payment record thay vì lưu response lớn.
- `expires_at` là thời điểm hết hiệu lực logic theo chính sách retention.
- `lease_owner` và `lease_until` phục vụ xử lý công việc dài hạn có thể cần takeover.

Không phải hệ thống nào cũng cần tất cả cột. Với một thao tác đồng bộ ngắn trong cùng database, lease có thể không cần. Với event consumer, có thể chỉ cần event ID, consumer name, status và processed time. Thiết kế theo contract thực tế, không sao chép schema lớn hơn mức cần thiết.

### Lưu kết quả đến mức nào?

Có ba cách thường gặp:

1. Lưu response đã chuẩn hóa nếu response nhỏ, ổn định và được phép lưu.
2. Lưu resource ID/result reference rồi dựng response từ dữ liệu nghiệp vụ hiện tại.
3. Lưu mã kết quả cùng status nếu caller chỉ cần biết thao tác đã hoàn tất.

Nếu lưu response body, phải cân nhắc PII, secret, retention, mã hóa và quyền đọc. Không lưu access token, credential hoặc dữ liệu thẻ. Khi replay response nhạy cảm, xác thực và phân quyền caller hiện tại trước khi trả kết quả đã lưu.

## 5. Trạng thái xử lý và chuyển trạng thái

Một mô hình đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> PROCESSING: Claim key
    PROCESSING --> SUCCEEDED: Commit result
    PROCESSING --> FAILED_RETRYABLE: Transient failure
    PROCESSING --> FAILED_FINAL: Permanent failure
    FAILED_RETRYABLE --> PROCESSING: Retry / lease takeover
    SUCCEEDED --> [*]
    FAILED_FINAL --> [*]
~~~

| Trạng thái | Ý nghĩa | Request lặp |
|---|---|---|
| `PROCESSING` | Một worker đã claim key và đang xử lý | Chờ, trả in-progress hoặc retry sau; không chạy song song cùng side effect |
| `SUCCEEDED` | Kết quả nghiệp vụ đã commit | Trả lại kết quả đã lưu |
| `FAILED_RETRYABLE` | Lỗi tạm thời, có thể thử lại | Cho retry theo policy và lease |
| `FAILED_FINAL` | Lỗi nghiệp vụ hoặc lỗi vĩnh viễn | Trả lại lỗi đã lưu hoặc yêu cầu key mới theo contract |

Không phải lỗi nào cũng nên lưu thành FAILED_FINAL. Ví dụ input invalid có thể bị từ chối trước khi claim key; lỗi timeout tạm thời có thể retry. Hãy phân loại rõ.

### Request trùng khi đang PROCESSING

Nếu key đã được claim nhưng chưa có kết quả cuối, API cần quy định hành vi:

- Chờ một khoảng ngắn rồi đọc lại kết quả.
- Trả HTTP 202 với operation/status URL để caller polling.
- Trả HTTP 409 hoặc 425/429 theo contract, kèm `Retry-After` nếu phù hợp.
- Với queue consumer, không acknowledge message nếu công việc chưa hoàn tất; để trigger retry theo chính sách.

Không để request thứ hai thực hiện cùng side effect chỉ vì request thứ nhất chưa ghi trạng thái SUCCEEDED. Hành vi cụ thể phụ thuộc loại trigger và SLA.

## 6. Atomic claim bằng unique constraint

Không dùng quy trình “SELECT trước, nếu chưa có thì INSERT” mà không có atomic protection. Hai invocation có thể cùng đọc thấy chưa có record rồi cùng thực hiện nghiệp vụ.

Mẫu nguy hiểm:

~~~sql
SELECT *
FROM idempotency_record
WHERE tenant_id = :tenant
  AND operation = :operation
  AND idempotency_key = :key;

-- Nếu không có dòng, hai invocation đều có thể đi tiếp và INSERT.
~~~

Dùng unique constraint cùng thao tác insert atomic:

~~~sql
INSERT INTO idempotency_record (
    tenant_id,
    operation,
    idempotency_key,
    request_hash,
    status,
    expires_at
)
VALUES (
    :tenant,
    :operation,
    :key,
    :request_hash,
    'PROCESSING',
    :expires_at
)
ON CONFLICT (tenant_id, operation, idempotency_key) DO NOTHING
RETURNING tenant_id;
~~~

- Có dòng trả về: invocation hiện tại đã claim key.
- Không có dòng: key đã tồn tại; đọc record hiện tại và so sánh fingerprint/status.
- Nếu hai transaction insert cùng key, unique index điều phối cạnh tranh. Transaction thứ hai sẽ chờ kết quả transaction thứ nhất theo database isolation/locking semantics rồi mới biết insert có thành công không.

Đây là phần bảo đảm concurrency ở database. Một `synchronized` hoặc `ConcurrentHashMap` trong Java không thể thay thế vì các invocation có thể chạy trên nhiều JVM.

## 7. Mẫu A: thao tác đồng bộ ngắn trong cùng database transaction

Nếu nghiệp vụ và idempotency record cùng nằm trong một database, cách đơn giản nhất là đưa claim, business write, lưu kết quả và outbox vào **cùng transaction**:

1. Bắt đầu transaction.
2. Insert idempotency key bằng unique constraint.
3. Nếu insert thất bại do key đã tồn tại, đọc record đã commit và xử lý duplicate.
4. Nếu claim thành công, thực hiện business writes.
5. Ghi outbox event nếu cần phát event.
6. Cập nhật idempotency record thành SUCCEEDED và lưu result.
7. Commit transaction.
8. Chỉ sau commit mới trả response/acknowledge message.

Khi transaction rollback, cả claim và business write đều rollback. Một retry sau đó có thể claim lại key. Khi transaction commit, duplicate request nhìn thấy SUCCEEDED và trả lại kết quả.

### Ví dụ SQL trong transaction

~~~sql
BEGIN;

INSERT INTO idempotency_record (
    tenant_id, operation, idempotency_key,
    request_hash, status, expires_at
)
VALUES (
    :tenant, 'orders.create', :key,
    :request_hash, 'PROCESSING', :expires_at
)
ON CONFLICT DO NOTHING
RETURNING tenant_id;

-- Chỉ tiếp tục nếu INSERT trả về một dòng:
INSERT INTO orders (order_id, tenant_id, customer_id, status)
VALUES (:order_id, :tenant, :customer_id, 'CREATED');

INSERT INTO outbox_event (
    event_id, aggregate_id, event_type, payload, created_at
)
VALUES (
    :event_id, :order_id, 'OrderCreated', :payload, now()
);

UPDATE idempotency_record
SET status = 'SUCCEEDED',
    response_status = 201,
    response_body = :response_json,
    updated_at = now()
WHERE tenant_id = :tenant
  AND operation = 'orders.create'
  AND idempotency_key = :key;

COMMIT;
~~~

Các lệnh business write chỉ chạy khi claim thành công. Nếu không claim được, rollback/đóng transaction hiện tại rồi đọc record đã tồn tại bằng transaction mới hoặc xử lý theo logic tương đương. Không tiếp tục insert order.

Trong mô hình này, PROCESSING có thể chưa hiển thị cho transaction khác vì record được commit cùng kết quả cuối. Đó là chủ ý: thao tác ngắn được xử lý nguyên tử, duplicate sẽ chờ transaction đầu tiên rồi đọc kết quả cuối. Nếu transaction kéo dài nhiều phút, giữ lock lâu sẽ không phù hợp; dùng mô hình lease riêng.

### Java: ranh giới transaction

Ví dụ minh họa với Spring:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CreateOrderTransactionalService {
    private final IdempotencyRepository idempotency;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public CreateOrderTransactionalService(
            IdempotencyRepository idempotency,
            OrderRepository orders,
            OutboxRepository outbox) {
        this.idempotency = idempotency;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public StoredResult create(
            CreateOrderCommand command,
            String requestHash) {

        boolean claimed = idempotency.tryInsertProcessing(
                command.tenantId(),
                "orders.create",
                command.idempotencyKey(),
                requestHash);

        if (!claimed) {
            throw new DuplicateKeyException(
                    "Idempotency key already exists");
        }

        Order order = orders.insert(command);
        outbox.insert(OrderCreatedEvent.from(order));

        StoredResult result = StoredResult.created(order);
        idempotency.markSucceeded(
                command.tenantId(),
                "orders.create",
                command.idempotencyKey(),
                result);

        return result;
    }
}
~~~

Đây là phác thảo application service. Adapter/controller cần bắt DuplicateKeyException hoặc kết quả claim=false, đọc record đã commit và:
- so sánh request hash;
- trả kết quả đã lưu nếu SUCCEEDED;
- trả conflict nếu hash khác;
- xử lý in-progress nếu kiến trúc có trạng thái PROCESSING đã commit riêng.

Không gọi payment provider hoặc API ngoài trong transaction database dài. Transaction này chỉ phù hợp khi side effect cần commit cùng database hoặc được ghi vào outbox.

## 8. Mẫu B: công việc dài hạn dùng lease và recovery

Một workflow có thể chạy nhiều phút hoặc chờ callback. Không nên giữ database transaction mở trong suốt thời gian đó. Thay vào đó:

1. Atomically claim key và commit trạng thái PROCESSING.
2. Ghi `lease_owner` và `lease_until`.
3. Worker thực hiện công việc bên ngoài transaction.
4. Gia hạn lease nếu công việc vẫn hoạt động.
5. Khi hoàn tất, cập nhật SUCCEEDED với điều kiện owner token vẫn đúng.
6. Nếu worker chết, worker khác có thể takeover sau khi lease hết hạn.
7. Worker cũ nếu hồi phục không được phép ghi đè kết quả của worker mới.

Ví dụ claim record ban đầu:

~~~sql
INSERT INTO idempotency_record (
    tenant_id, operation, idempotency_key,
    request_hash, status, lease_owner,
    lease_until, expires_at
)
VALUES (
    :tenant, :operation, :key,
    :request_hash, 'PROCESSING', :owner_token,
    now() + interval '60 seconds',
    :expires_at
)
ON CONFLICT DO NOTHING
RETURNING *;
~~~

Gia hạn lease chỉ khi worker hiện tại vẫn sở hữu record:

~~~sql
UPDATE idempotency_record
SET lease_until = now() + interval '60 seconds',
    updated_at = now()
WHERE tenant_id = :tenant
  AND operation = :operation
  AND idempotency_key = :key
  AND status = 'PROCESSING'
  AND lease_owner = :owner_token
  AND lease_until > now();
~~~

Nếu update count = 0, worker không còn quyền sở hữu lease hoặc lease đã hết hạn. Nó phải dừng side effect mới và kiểm tra trạng thái hiện tại.

### Takeover sau khi lease hết hạn

Một worker mới có thể claim lại PROCESSING record đã hết lease bằng conditional update:

~~~sql
UPDATE idempotency_record
SET lease_owner = :new_owner_token,
    lease_until = now() + interval '60 seconds',
    updated_at = now()
WHERE tenant_id = :tenant
  AND operation = :operation
  AND idempotency_key = :key
  AND status = 'PROCESSING'
  AND lease_until < now()
RETURNING *;
~~~

Chỉ một worker có thể thành công trong việc cập nhật cùng record dưới transaction/locking semantics phù hợp. Dùng database time (`now()`) để so sánh lease, tránh phụ thuộc clock của các instance.

### Owner token và fencing

Owner token giúp worker cũ không thể cập nhật record sau khi worker mới takeover. Tuy nhiên, chỉ kiểm tra token trong database chưa đủ nếu worker cũ đã gửi request ra payment provider hoặc một hệ thống ngoài.

Với resource có thể hỗ trợ fencing, dùng token tăng đơn điệu (fencing number/version) và yêu cầu resource đích từ chối thao tác có token cũ. Nếu hệ thống đích không hỗ trợ fencing, cần idempotency key ổn định ở hệ thống đích hoặc cơ chế reconciliation.

Lease không phải bằng chứng worker cũ đã dừng. Nó chỉ cho biết quyền sở hữu logic đã hết hạn. Worker cũ có thể bị pause rồi chạy tiếp; mọi write phải được bảo vệ bằng owner/fencing check và side effect phải idempotent.

## 9. Trạng thái FAILED và chính sách retry

Không phải lỗi nào cũng xử lý giống nhau.

| Nhóm lỗi | Ví dụ | Trạng thái/chính sách |
|---|---|---|
| Validation/permanent business error | Quantity không hợp lệ, account bị khóa | Có thể lưu FAILED_FINAL hoặc từ chối trước khi claim |
| Conflict nghiệp vụ | Hết hàng, trạng thái không cho phép | Lưu kết quả lỗi nếu contract yêu cầu retry cùng key trả cùng kết quả |
| Transient infrastructure | Database tạm thời unavailable | Rollback transaction ngắn hoặc FAILED_RETRYABLE |
| Timeout không rõ kết quả | Request downstream timeout sau khi gửi | Kiểm tra downstream bằng cùng idempotency key trước khi thử lại |
| Worker crash | Instance bị thu hồi khi PROCESSING | Lease expiry và recovery |
| Permission/configuration error | IAM AccessDenied, secret sai | Không retry vô hạn; alert và sửa cấu hình |

Nếu cùng một key đã nhận lỗi nghiệp vụ cuối cùng, retry có nên trả lại cùng lỗi hay được phép thử lại khi điều kiện thay đổi? Cần quyết định trong API contract.

Ví dụ:
- Với `orders.create`, nếu hết hàng là kết quả cuối của lần yêu cầu đó, retry cùng key nên trả lại conflict đã lưu; muốn thử tạo lại sau khi hàng được bổ sung thì client tạo key mới.
- Với lỗi database tạm thời trước khi commit, transaction rollback và key chưa được ghi nhận; retry cùng key có thể chạy lại.
- Với payment timeout không rõ charge đã xảy ra chưa, không tạo key mới. Hãy query provider hoặc retry bằng cùng downstream idempotency key.

## 10. Xác định retention window và TTL

Retention window là khoảng thời gian hệ thống giữ idempotency record để nhận diện retry/duplicate của cùng thao tác. Nếu record bị xóa quá sớm, một retry muộn có thể bị coi là yêu cầu mới và tạo side effect lần nữa.

Hãy xác định **thời điểm muộn nhất mà cùng thao tác còn có thể được gửi lại**, tính từ lần đầu được chấp nhận. Retention phải bao phủ toàn bộ khoảng này cộng safety margin.

Các nguồn thời gian cần xét:

- Client retry window: client hoặc mobile app có thể retry trong bao lâu?
- API gateway/load balancer retry: lớp trung gian có tự retry không?
- Queue retention và redelivery: message có thể tồn tại và được giao lại bao lâu?
- Visibility/ack deadline và retry backoff: message có thể được giao lại sau nhiều lần delay không?
- DLQ retention và replay: operator có thể replay message sau bao lâu?
- Workflow timeout: một execution có thể tiếp tục hoặc resume sau bao lâu?
- Scheduled retry hoặc delayed delivery: công việc có thể được lên lịch lại đến thời điểm nào?
- Disaster recovery/restore: backup hoặc event archive có thể được replay sau bao lâu?
- Clock skew và thời gian vận hành: cần margin để tránh hết hạn ngay tại ranh giới.

Một công thức định hướng:

~~~text
retention window
  >= latest permitted retry/redelivery/replay horizon
     + operational safety margin
~~~

Nếu các cửa sổ diễn ra nối tiếp nhau, hãy tính tổng thời gian từ lần đầu đến lần replay muộn nhất. Nếu chúng là các giới hạn độc lập tính từ cùng mốc, lấy mốc muộn nhất. Đừng chỉ chọn TTL theo thời gian retry của HTTP client mà bỏ qua DLQ hoặc replay thủ công.

### Ví dụ tính retention

Giả sử:
- Client có thể retry trong 24 giờ.
- Queue giữ message tối đa 4 ngày.
- DLQ có thể được replay trong vòng 14 ngày từ lúc nhận đầu tiên.
- Vận hành cần thêm 2 ngày để xử lý sự cố.

Retention cần ít nhất bao phủ 14 ngày + 2 ngày margin = 16 ngày, nếu mốc DLQ đã tính từ lần nhận đầu tiên. Nếu DLQ retention bắt đầu sau khi message chuyển sang DLQ và thời gian đó có thể cộng tiếp với queue retention, phải tính horizon nối tiếp thực tế thay vì lấy max đơn giản.

### TTL không phải thời điểm xóa chính xác

Nhiều kho dữ liệu hỗ trợ TTL nhưng xóa vật lý bất đồng bộ. Ví dụ DynamoDB TTL, Firestore TTL hoặc cơ chế expiry của cache có thể không xóa record đúng vào giây `expires_at`. PostgreSQL thường cần job/scheduled cleanup hoặc partition retention để xóa bản ghi.

Vì vậy, tách hai khái niệm:

- **Logical expiry:** ứng dụng coi key hết hiệu lực theo `expires_at`.
- **Physical deletion:** storage thực sự xóa record sau đó để thu hồi dung lượng.

TTL storage là cơ chế dọn dẹp, không nên là logic duy nhất quyết định một duplicate có được phép chạy lại hay không. Ứng dụng cần kiểm tra `expires_at` và chính sách xử lý record hết hạn một cách có chủ đích.

### Không cho PROCESSING record hết hạn tùy tiện

Nếu record đang PROCESSING nhưng `expires_at` đến trước khi công việc kết thúc, TTL có thể xóa record và một invocation khác tạo claim mới trong khi worker cũ vẫn chạy.

Đối với công việc dài:
- Lease deadline và retention expiry là hai thời gian khác nhau.
- Lease có thể hết để worker khác takeover.
- Retention không được kết thúc khi operation vẫn đang PROCESSING.
- Chỉ bắt đầu tính thời gian lưu sau khi terminal state được ghi, hoặc đặt expires_at đủ xa và gia hạn khi còn xử lý.
- Cleanup job không xóa record PROCESSING đang có lease hợp lệ.

## 11. TTL theo loại storage

Cơ chế TTL khác nhau theo nền tảng:

| Storage | Cơ chế thường gặp | Lưu ý thiết kế |
|---|---|---|
| PostgreSQL/MySQL | Cột expires_at + scheduled cleanup/partition | Ứng dụng tự áp dụng logical expiry; cleanup có thể chạy theo batch |
| DynamoDB | TTL attribute theo epoch time | Xóa vật lý bất đồng bộ; không dựa vào việc item biến mất đúng hạn |
| Redis | Key expiry/EXPIRE | Phù hợp cache/coordination khi cấu hình durability và failover phù hợp; cân nhắc eviction/persistence |
| Firestore | TTL policy trên timestamp field | Xóa theo cơ chế nền, không đảm bảo ngay tại thời điểm expiry |
| Object/event archive | Lifecycle/retention policy | Có thể cần giữ event/schema lâu hơn idempotency record |

Không phải mọi storage đều có cùng semantics về atomic conditional write, durability, replication và TTL. Trước khi chọn kho idempotency, xác minh:
- Có atomic insert-if-absent hoặc conditional update không?
- Unique constraint có hoạt động trên phạm vi multi-region cần dùng không?
- Read-after-write consistency có đủ cho duplicate detection không?
- TTL có thể xóa PROCESSING record không?
- Failover hoặc restore có thể làm mất key đã ghi không?
- Throughput và cost phù hợp với số request không?

Với nghiệp vụ tài chính, đừng dùng cache có eviction làm nguồn chuẩn duy nhất cho idempotency nếu mất key có thể tạo charge trùng. Có thể dùng Redis như lớp phối hợp hoặc tối ưu, nhưng bản ghi chuẩn nên ở nơi có durability/consistency đáp ứng yêu cầu nghiệp vụ.

## 12. Bản ghi hết hạn và hành vi khi key quay lại

Khi key đã hết logical retention, có một số lựa chọn:

1. **Cho phép thao tác mới:** phù hợp khi contract quy định key chỉ duy nhất trong một khoảng thời gian.
2. **Từ chối key cũ:** phù hợp khi key được xem là định danh không bao giờ tái sử dụng.
3. **Chỉ cho tái sử dụng với payload giống hoặc business version mới:** cần quy tắc rõ ràng và kiểm soát atomic.

Với thanh toán hoặc tạo đơn có hậu quả lâu dài, thường nên có unique business constraint bền vững bên cạnh TTL idempotency. Ví dụ order ID hoặc payment operation ID không được tạo lại chỉ vì idempotency record hết hạn.

Nếu record hết hạn vẫn còn do cleanup bất đồng bộ, không được tùy tiện xóa rồi insert bằng hai thao tác riêng. Dùng transaction và conditional update dựa trên `expires_at`, status và lease để chỉ một invocation được quyền tái sử dụng record. Nếu key cũ còn có thể xuất hiện từ DLQ replay, retention đã chọn quá ngắn.

## 13. Side effect bên ngoài database

Một transaction SQL không thể nguyên tử bao trùm payment provider, email API, object storage và database khác. Cần thiết kế riêng cho side effect.

### Dùng downstream idempotency key

Nếu payment provider hỗ trợ idempotency, gửi cùng key cho mọi retry của cùng payment operation. Lưu provider reference và kết quả để có thể query lại khi timeout không rõ kết quả.

Không tạo key mới chỉ vì lần gọi trước timeout. Timeout không chứng minh provider chưa thực hiện charge.

### Transactional outbox

Khi cần cập nhật database và phát event:

1. Trong một transaction, ghi business record, idempotency result và outbox event.
2. Worker đọc outbox và publish event.
3. Khi publish thành công, đánh dấu event đã gửi.
4. Nếu worker crash trước khi đánh dấu, event có thể được publish lại.
5. Consumer deduplicate bằng event ID ổn định.

Outbox giải quyết khoảng trống giữa database commit và message publish. Nó không đảm bảo broker chỉ giao một lần.

### Saga và compensation

Với quy trình nhiều hệ thống, ví dụ giữ hàng rồi charge payment:
- Ghi trạng thái từng bước.
- Dùng idempotency key riêng cho từng business action.
- Retry bước có thể retry.
- Nếu bước sau thất bại vĩnh viễn, chạy compensation như release inventory hoặc refund.
- Lưu kết quả compensation để retry compensation cũng idempotent.

Không coi rollback code hoặc xóa idempotency record là compensation. Side effect đã xảy ra ở hệ thống ngoài cần hành động nghiệp vụ bù trừ.

## 14. Java: mô hình hóa idempotency state

Có thể biểu diễn trạng thái và quyết định xử lý bằng kiểu Java rõ ràng:

~~~java
public enum IdempotencyStatus {
    PROCESSING,
    SUCCEEDED,
    FAILED_RETRYABLE,
    FAILED_FINAL
}

public sealed interface IdempotencyDecision {
    record Execute(String ownerToken) implements IdempotencyDecision {}
    record Replay(StoredResult result) implements IdempotencyDecision {}
    record InProgress(java.time.Instant retryAfter)
            implements IdempotencyDecision {}
    record KeyConflict() implements IdempotencyDecision {}
    record RejectFinal(StoredResult result)
            implements IdempotencyDecision {}
}

public record StoredResult(
        int statusCode,
        String responseBody,
        String resourceId) {
}
~~~

Interface store có thể tách khỏi framework:

~~~java
public interface IdempotencyStore {
    IdempotencyDecision claim(
            IdempotencyScope scope,
            String key,
            String requestHash);

    void complete(
            IdempotencyScope scope,
            String key,
            String ownerToken,
            StoredResult result);

    void markRetryableFailure(
            IdempotencyScope scope,
            String key,
            String ownerToken);

    void extendLease(
            IdempotencyScope scope,
            String key,
            String ownerToken);
}

public record IdempotencyScope(
        String tenantId,
        String operation) {
}
~~~

Implementation thật cần đảm bảo atomicity bằng database unique constraint hoặc conditional write. Interface không tự tạo ra bảo đảm concurrency; fake in-memory chỉ phù hợp unit test tuần tự.

### Xử lý kết quả claim ở handler

~~~java
public final class IdempotentOrderHandler {
    private final IdempotencyStore store;
    private final PlaceOrderUseCase useCase;

    public IdempotentOrderHandler(
            IdempotencyStore store,
            PlaceOrderUseCase useCase) {
        this.store = store;
        this.useCase = useCase;
    }

    public StoredResult handle(
            IdempotencyScope scope,
            String key,
            String requestHash,
            PlaceOrderCommand command) {

        IdempotencyDecision decision =
                store.claim(scope, key, requestHash);

        if (decision instanceof IdempotencyDecision.Replay replay) {
            return replay.result();
        }
        if (decision instanceof IdempotencyDecision.KeyConflict) {
            throw new IdempotencyKeyConflictException();
        }
        if (decision instanceof IdempotencyDecision.InProgress) {
            throw new OperationInProgressException();
        }
        if (decision instanceof IdempotencyDecision.RejectFinal rejected) {
            return rejected.result();
        }

        IdempotencyDecision.Execute execute =
                (IdempotencyDecision.Execute) decision;

        try {
            PlaceOrderResult result = useCase.execute(command);
            StoredResult stored = new StoredResult(
                    201,
                    "{\"orderId\":\"" + result.orderId() + "\"}",
                    result.orderId());

            store.complete(
                    scope, key, execute.ownerToken(), stored);
            return stored;
        } catch (RuntimeException error) {
            store.markRetryableFailure(
                    scope, key, execute.ownerToken());
            throw error;
        }
    }
}

class IdempotencyKeyConflictException extends RuntimeException {
}

class OperationInProgressException extends RuntimeException {
}
~~~

Đây là skeleton cho công việc có claim/lease tách biệt; không dùng nguyên mẫu này thay cho transaction ngắn ở mục 7. JSON response trong ví dụ được ghép chuỗi để minh họa; production nên dùng serializer và lưu response đã chuẩn hóa. Cũng cần phân loại exception để chỉ đánh dấu retryable với lỗi thực sự có thể thử lại.

Với transaction ngắn, claim, business write và complete phải cùng transaction. Nếu `store.complete` thất bại sau khi use case đã thực hiện side effect ở hệ thống ngoài, cần downstream idempotency/reconciliation; không được giả định lần retry sẽ an toàn.

## 15. Quy tắc xử lý request trùng theo trigger

| Trigger | Khi nhận duplicate | Khi đang xử lý | Khi đã thành công |
|---|---|---|---|
| HTTP API | So sánh key + fingerprint | 202/409/Retry-After theo contract | Replay response/result |
| SQS/queue | Dùng message/event ID hoặc business key | Không ack khi chưa hoàn tất; lease/retry | Ack duplicate sau khi xác nhận đã xử lý |
| Pub/Sub/event bus | Dùng event ID ổn định | Nack/retry hoặc lưu trạng thái in-progress | Ack/return success theo semantics |
| Workflow task | Key theo execution + task/business action | Resume/checkpoint hoặc lease | Trả kết quả đã lưu |
| Scheduled invocation | Key theo schedule occurrence/window | Chỉ một worker claim | Bỏ qua hoặc trả kết quả lần chạy trước |

Các nền tảng có semantics acknowledgement, retry và ordering khác nhau. Adapter phải map trạng thái idempotency sang hành vi trigger đúng cách. Không trả HTTP 200 hoặc acknowledge message chỉ vì key đang PROCESSING nếu việc đó có thể làm mất công việc chưa hoàn tất.

## 16. Bảo mật và quyền truy cập idempotency store

Idempotency record có thể chứa tenant ID, operation, resource reference và response data. Hãy bảo vệ như dữ liệu nghiệp vụ.

- Scope key theo tenant/account và operation.
- Xác thực và phân quyền caller trước khi replay response.
- Không lưu token, password, payment credentials hoặc full card data.
- Giới hạn quyền đọc/ghi store theo từng function.
- Mã hóa dữ liệu khi lưu và khi truyền.
- Dùng retention/cleanup phù hợp với chính sách dữ liệu.
- Không ghi raw idempotency key vào metric labels.
- Log key đã mask/hash hoặc correlation ID khi cần điều tra.
- Audit thao tác replay, reset hoặc xóa record.
- Không cho client tự yêu cầu xóa record để vượt qua deduplication window.

Nếu key có thể đoán được và response chứa dữ liệu nhạy cảm, attacker có thể thử truy vấn kết quả cũ. Vì vậy, idempotency key không thay thế authorization; response replay phải tuân theo quyền hiện tại của caller.

## 17. Quan sát idempotency và retention

Nên theo dõi các chỉ số sau:

| Metric/log | Ý nghĩa |
|---|---|
| `idempotency_claim_total` | Số lần claim mới |
| `idempotency_replay_total` | Số request trả lại kết quả cũ |
| `idempotency_conflict_total` | Cùng key nhưng fingerprint khác |
| `idempotency_in_progress_total` | Duplicate gặp operation đang chạy |
| `idempotency_lease_takeover_total` | Số lần worker khác takeover lease |
| `idempotency_expired_key_total` | Key đã hết logical retention nhưng vẫn xuất hiện |
| `idempotency_store_error_total` | Lỗi đọc/ghi store |
| `idempotency_record_age` | Tuổi record và trạng thái |
| `outbox_oldest_unpublished_age` | Event chờ publish lâu nhất |

Metric labels nên giới hạn ở operation, consumer, outcome và environment. Không dùng idempotency key, tenant ID hoặc order ID làm label có cardinality cao.

Alert nên tập trung vào:
- Tỷ lệ conflict tăng bất thường.
- PROCESSING record tồn tại lâu hơn lease/processing SLA.
- Lease takeover tăng đột biến.
- Store timeout hoặc conditional write failure.
- Record cleanup không theo kịp dung lượng.
- Duplicate xuất hiện sau khi retention đã hết.
- Outbox backlog hoặc DLQ tăng.

Log nên có operation, masked key/hash prefix, event ID, owner token đã mask, trạng thái và correlation ID. Không log response body nhạy cảm.

## 18. Kiểm thử idempotency và crash window

Unit test tuần tự không đủ để xác minh idempotency ở hệ thống phân tán. Cần test theo tầng.

### Unit tests

- Cùng key + cùng fingerprint + SUCCEEDED trả kết quả đã lưu.
- Cùng key + fingerprint khác trả conflict.
- Key mới claim thành công.
- PROCESSING trả trạng thái in-progress.
- FAILED_RETRYABLE có thể được claim lại theo policy.
- FAILED_FINAL trả kết quả lỗi đã lưu.
- Key hết logical retention được xử lý theo contract.
- Worker cũ không thể complete sau khi lease owner đã thay đổi.

### Database/concurrency integration tests

- Hai transaction cùng claim một key: chỉ một transaction thành công.
- Hai key khác nhau cùng operation có thể xử lý độc lập.
- Duplicate request chờ transaction đầu commit rồi đọc kết quả.
- Transaction rollback không để lại record/business write một phần.
- Unique constraint vẫn hoạt động khi nhiều connection đồng thời.
- Conditional takeover chỉ cấp lease cho một worker.
- Cleanup không xóa record PROCESSING còn lease hợp lệ.

### Failure/recovery tests

| Điểm crash | Điều cần xác minh |
|---|---|
| Trước khi claim | Retry có thể claim bình thường |
| Sau claim nhưng trước business write trong cùng transaction | Rollback xóa cả claim |
| Sau business write nhưng trước commit | Transaction rollback toàn bộ |
| Sau commit nhưng trước HTTP response | Retry replay cùng kết quả |
| Sau publish outbox nhưng trước đánh dấu sent | Event có thể publish lại nhưng consumer dedupe |
| Sau external payment success nhưng trước local update | Retry dùng cùng downstream key hoặc reconciliation |
| Worker chết khi PROCESSING | Lease hết hạn và worker mới takeover |
| Worker cũ hồi phục sau takeover | Owner/fencing check ngăn stale completion |
| DLQ replay sau nhiều ngày | Record còn trong retention và duplicate không tạo side effect mới |

### Kiểm thử TTL

- Key còn trong retention phải replay kết quả cũ.
- Key vừa hết logical retention phải tuân theo policy tái sử dụng/từ chối.
- Storage chưa xóa vật lý record không được làm thay đổi logic expiry.
- Cleanup job không xóa record đang PROCESSING.
- Replay trong DLQ window không vượt quá retention.
- Backup restore hoặc disaster recovery không làm mất key còn hiệu lực.

Test thời gian bằng Clock giả lập hoặc điều khiển timestamp trong test database. Không dùng `Thread.sleep()` để đợi TTL thật trong unit test.

## 19. Checklist thiết kế idempotency state

- [ ] Xác định thao tác nghiệp vụ nào cần idempotency và side effect được bảo vệ.
- [ ] Key ổn định qua client retry, broker redelivery và replay.
- [ ] Key được scope theo tenant/account và operation.
- [ ] Cùng key nhưng payload khác được phát hiện bằng fingerprint.
- [ ] Fingerprint được tạo từ command đã normalize, không phụ thuộc JSON formatting.
- [ ] Record được lưu trong shared durable store.
- [ ] Unique constraint/conditional write bảo vệ atomic claim.
- [ ] Trạng thái PROCESSING, SUCCEEDED và failure có semantics rõ.
- [ ] Duplicate khi PROCESSING có hành vi HTTP/queue phù hợp.
- [ ] Transaction ngắn gộp claim, business write, outbox và result khi cùng database.
- [ ] Công việc dài dùng lease, owner token, recovery và fencing phù hợp.
- [ ] Lease timeout tách biệt với retention TTL.
- [ ] Retention bao phủ client retry, queue retention, redelivery, DLQ và replay.
- [ ] Logical expiry được kiểm tra độc lập với physical TTL deletion.
- [ ] PROCESSING record không bị cleanup khi công việc còn hoạt động.
- [ ] Side effect ngoài database dùng downstream idempotency hoặc reconciliation.
- [ ] Business uniqueness lâu dài được bảo vệ riêng với TTL idempotency.
- [ ] Response replay vẫn kiểm tra authorization và không lộ dữ liệu nhạy cảm.
- [ ] Có metric cho replay, conflict, in-progress, takeover và store errors.
- [ ] Có unit, concurrency, integration và crash-recovery tests.

## Tự kiểm tra

1. Vì sao client timeout không chứng minh lần xử lý đầu tiên đã thất bại?
2. Idempotency khác exactly-once processing như thế nào?
3. Vì sao idempotency key cần scope theo tenant và operation?
4. Request fingerprint giải quyết vấn đề gì khi client tái sử dụng key?
5. Unique constraint giúp ngăn race condition “SELECT rồi INSERT” ra sao?
6. Khi nào nên gộp claim và business write trong một transaction?
7. Vì sao công việc dài cần lease và owner/fencing check?
8. Retention window cần tính những khoảng retry/redelivery/replay nào?
9. Logical expiry khác physical TTL deletion như thế nào?
10. Vì sao TTL không nên xóa một record đang PROCESSING?
11. Nếu payment provider đã charge nhưng function timeout, cần retry bằng cách nào?
12. Transactional outbox giải quyết vấn đề gì và không bảo đảm điều gì?
13. Vì sao in-memory Map không đủ để bảo vệ idempotency giữa nhiều function instance?
14. Những crash window nào phải được kiểm thử trước khi đưa consumer vào production?

Lưu trạng thái idempotent là một phần của thiết kế dữ liệu, không phải một cache phụ thêm sau khi gặp duplicate. Khóa phải ổn định và có scope, database phải claim atomically, trạng thái phải đủ để replay hoặc phục hồi, và retention phải bao phủ toàn bộ thời gian message/request còn có thể quay lại. Khi kết hợp transaction, lease, downstream idempotency, outbox và kiểm thử crash window, Java function có thể retry an toàn hơn mà không tạo side effect trùng.

