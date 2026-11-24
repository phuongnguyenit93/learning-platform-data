# Thiết kế thao tác lũy đẳng và khóa chống xử lý trùng

Trong hệ thống Spring Boot, một request có thể được gửi lại vì người dùng bấm nút hai lần, trình duyệt retry sau khi mất kết nối, API gateway timeout hoặc một worker nhận lại message. Nếu mỗi lần nhận đều tạo đơn hàng mới, trừ tiền hoặc gửi thông báo, hệ thống sẽ phát sinh tác dụng phụ trùng lặp dù từng lần gọi riêng lẻ đều hợp lệ.

**Idempotency** bảo đảm việc lặp lại cùng một yêu cầu logic không tạo thêm kết quả nghiệp vụ ngoài ý muốn. **Deduplication** nhận diện và bỏ qua những lần giao hoặc gửi trùng. **Lock** điều phối các tiến trình cùng muốn xử lý một tài nguyên tại một thời điểm. Ba kỹ thuật liên quan nhưng giải quyết các vấn đề khác nhau: khóa không tự bảo đảm idempotency, còn deduplication chỉ có hiệu lực trong phạm vi và thời gian được thiết kế.

Bài thuộc chương **Độ tin cậy** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **idempotent operation**, **idempotency key**, **deduplication** và **at-least-once delivery**.
2. Thiết kế API nhận khóa idempotency, ràng buộc phạm vi khóa và lưu kết quả xử lý.
3. Dùng unique constraint/transaction để ngăn hai request đồng thời cùng tạo một kết quả nghiệp vụ.
4. Phân biệt khóa database, distributed lock, lease, fencing token và optimistic concurrency.
5. Dùng điều kiện ghi như ETag, generation/version hoặc create-if-absent cho thao tác storage.
6. Kết hợp idempotency với transactional outbox/inbox khi database và messaging không có transaction chung.
7. Hiểu phạm vi của duplicate detection/lock trong Azure Service Bus, AWS SQS và Google Cloud Pub/Sub.
8. Kiểm thử retry, duplicate delivery, race condition, lock expiry và unknown outcome.
9. Quan sát duplicate, conflict, lock contention và trạng thái xử lý mà không lưu hoặc log dữ liệu nhạy cảm.

## 2. Idempotency là gì?

Một thao tác \(f\) là lũy đẳng nếu áp dụng nhiều lần với cùng đầu vào và cùng ngữ cảnh tạo ra kết quả quan sát được tương đương với một lần áp dụng:

\[
f(f(x)) = f(x)
\]

Đây là mô hình khái niệm; với API có side effect, cần xác định rõ **kết quả quan sát được** gồm trạng thái dữ liệu, giao dịch, message, email hay khoản thanh toán nào.

| Thao tác | Có thể lũy đẳng? | Điều kiện |
| --- | --- | --- |
| Đọc thông tin đơn hàng | Thường có | Không tạo side effect |
| Đặt trạng thái đơn hàng thành CANCELLED | Có thể | Cập nhật trạng thái theo quy tắc, không tạo thêm tác dụng phụ |
| Tăng số lượng tồn kho thêm 1 | Không | Mỗi lần gọi đều tăng thêm |
| Đặt tồn kho thành giá trị tuyệt đối 20 | Có thể | Cùng giá trị và cùng điều kiện/version |
| Tạo đơn hàng mới | Không mặc định | Cần idempotency key hoặc business unique key |
| Gửi email xác nhận | Không mặc định | Cần deduplication/outbox và kiểm soát gửi trùng |
| Gửi message lên broker | Không mặc định | Cần message identity/deduplication/consumer idempotency |

**HTTP method không tự bảo đảm nghiệp vụ idempotent.** PUT thường được thiết kế idempotent theo semantics HTTP; POST thường không. Nhưng nếu một endpoint PUT lại gửi thêm email hoặc trừ tiền mỗi lần nhận request, tác dụng phụ vẫn có thể bị lặp.

### Idempotency khác deduplication và lock

| Khái niệm | Câu hỏi giải quyết | Cơ chế điển hình |
| --- | --- | --- |
| **Idempotency** | Gọi lại cùng yêu cầu có tạo thêm tác dụng phụ không? | Lưu kết quả theo key, unique constraint, conditional update |
| **Deduplication** | Hai lần gửi/giao có cùng định danh có phải cùng một thông điệp không? | Message ID, inbox table, broker duplicate detection |
| **Lock** | Ai được phép xử lý tài nguyên trong khoảng thời gian này? | DB row lock, lease, distributed lock |
| **Optimistic concurrency** | Dữ liệu có thay đổi từ lúc đọc đến lúc ghi không? | Version, ETag, compare-and-set |
| **Fencing token** | Làm sao ngăn chủ lock cũ tiếp tục ghi sau khi lease hết hạn? | Token tăng đơn điệu được kiểm tra ở nơi ghi |

Một hệ thống bền vững thường kết hợp nhiều cơ chế: idempotency key cho API, unique constraint cho tính nguyên tử, outbox/inbox cho messaging và lock chỉ khi cần điều phối công việc.

## 3. Vì sao request hoặc message có thể bị xử lý trùng?

Các tình huống thường gặp:

- Người dùng nhấn nút thanh toán hai lần.
- Client gửi request nhưng mất response; client không biết server đã commit hay chưa nên gửi lại.
- API gateway retry một request sau timeout.
- Worker chết sau khi commit database nhưng trước khi acknowledge message.
- Broker giao lại message vì lock/visibility/ack deadline hết hạn.
- Publisher gửi message thành công nhưng mất acknowledgment và gửi lại.
- Hai replica cùng nhận hai request giống nhau gần như đồng thời.
- Job scheduler chạy lại job sau khi không nhận được heartbeat.
- Một thao tác upload bị retry sau khi server đã lưu blob nhưng client chưa nhận được response.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Spring Boot API
    participant DB as Database
    C->>A: POST /payments
    A->>DB: Commit payment
    DB-->>A: Commit thành công
    A--xC: Response bị mất
    C->>A: Retry cùng yêu cầu
    Note over C,A: Server không biết đây là retry nếu thiếu idempotency key
    A->>DB: Có thể tạo payment lần hai
~~~

**Timeout không chứng minh thao tác chưa xảy ra.** Request có thể đã được dịch vụ xử lý và commit, nhưng response bị mất trên đường về. Đây là lý do phải thiết kế trạng thái và khả năng tra cứu kết quả sau timeout.

## 4. Idempotency key cho API

Một **idempotency key** là định danh ổn định do client tạo hoặc server cấp, đại diện cho một ý định nghiệp vụ. Client phải gửi lại cùng key khi retry cùng một ý định.

Ví dụ:

~~~http
POST /api/payments
Idempotency-Key: 9a8b6f70-0a31-4f9c-8e0a-8e4f6dbcb120
Content-Type: application/json
~~~

Body:

~~~json
{
  "orderId": "ORD-2026-00125",
  "amount": 1250000,
  "currency": "VND"
}
~~~

Nếu client gửi lại cùng key và cùng payload, server trả lại kết quả đã lưu hoặc trạng thái đang xử lý. Nếu cùng key nhưng payload khác, server nên từ chối vì một key không được đại diện cho hai ý định khác nhau.

### Quy tắc thiết kế key

1. Key phải ổn định qua các lần retry của cùng một thao tác.
2. Key phải đủ khó đoán nếu nó có thể được dùng để truy xuất kết quả; không coi key là cơ chế xác thực.
3. Phạm vi key phải được xác định rõ: tenant, principal, operation hoặc endpoint.
4. Không dùng một key chung cho mọi request của một người dùng.
5. Không tự tạo key mới mỗi lần client retry.
6. Lưu fingerprint/hash của payload để phát hiện key bị tái sử dụng với nội dung khác.
7. Đặt retention phù hợp với thời gian client có thể retry và quy tắc nghiệp vụ.
8. Không chứa thông tin cá nhân, secret hoặc dữ liệu nhạy cảm trong key.

### Scope của idempotency key

Một bảng key nên xác định uniqueness theo phạm vi:

~~~text
(tenant_id, operation_name, idempotency_key)
~~~

Nếu chỉ unique theo idempotency_key toàn hệ thống, có thể xảy ra va chạm giữa các tenant hoặc operation khác nhau. Nếu unique theo user nhưng một user có nhiều ứng dụng/operation, cần cân nhắc thêm client/application scope.

**Key không thay thế authorization.** Khi trả lại kết quả đã lưu, server vẫn phải xác minh caller hiện tại có quyền xem kết quả đó. Không để idempotency key trở thành bearer token truy cập payment/order.

## 5. Fingerprint payload và xử lý key bị tái sử dụng

Ngoài key, server thường lưu **request fingerprint** để kiểm tra payload.

Ví dụ:

~~~text
fingerprint = SHA-256(
    canonicalize(
        tenantId,
        operationName,
        normalizedRequestBody,
        relevantBusinessHeaders
    )
)
~~~

Canonicalization phải ổn định: cùng dữ liệu logic tạo cùng fingerprint dù JSON field order hoặc whitespace khác nhau. Chỉ đưa các trường thực sự quyết định ý nghĩa nghiệp vụ vào fingerprint; không đưa trace ID, timestamp truyền tải hoặc header thay đổi theo mỗi lần retry.

| Request | Key | Fingerprint | Kết quả |
| --- | --- | --- | --- |
| Lần đầu | K1 | H1 | Bắt đầu xử lý |
| Retry cùng yêu cầu | K1 | H1 | Trả kết quả cũ/trạng thái đang xử lý |
| Cùng key, payload khác | K1 | H2 | Từ chối conflict |
| Ý định nghiệp vụ mới | K2 | H3 | Xử lý như yêu cầu mới |

Nếu payload chứa dữ liệu nhạy cảm, không lưu raw body chỉ để so sánh. Có thể lưu hash đã chuẩn hóa; chọn thuật toán và cách bảo vệ phù hợp với yêu cầu bảo mật. Hash không mã hóa dữ liệu và không thay thế encryption/access control.

## 6. Lưu idempotency record trong database

Một thiết kế phổ biến lưu record trong cùng database mà nghiệp vụ sử dụng.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id          VARCHAR(100) NOT NULL,
    operation_name     VARCHAR(100) NOT NULL,
    idempotency_key    VARCHAR(200) NOT NULL,
    request_hash       VARCHAR(64) NOT NULL,
    status             VARCHAR(20) NOT NULL,
    response_status    INTEGER,
    response_body      JSONB,
    resource_id        VARCHAR(100),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at         TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

Các trạng thái thường dùng:

| Trạng thái | Ý nghĩa |
| --- | --- |
| IN_PROGRESS | Key đã được nhận và thao tác đang xử lý |
| SUCCEEDED | Nghiệp vụ đã hoàn tất; có thể trả lại kết quả |
| FAILED_FINAL | Lỗi không thể retry bằng cùng ý định/key theo policy |
| RETRYABLE | Thất bại tạm thời; được phép tiếp tục theo chính sách |
| UNKNOWN | Không xác định được side effect đã xảy ra hay chưa; cần reconcile |

Không phải hệ thống nào cũng cần đủ trạng thái. Nếu toàn bộ nghiệp vụ và idempotency record nằm trong một transaction database, có thể đơn giản hơn. Nếu workflow kéo dài qua nhiều dịch vụ, cần trạng thái bền vững và cơ chế recovery rõ ràng.

### Vì sao cần unique constraint?

Hai request cùng key có thể đến hai replica cùng lúc. Cả hai cùng đọc thấy chưa có record rồi cùng xử lý. Một bước SELECT trước INSERT không đủ để chống race condition.

**Unique constraint/primary key** là hàng rào nguyên tử ở database: chỉ một transaction có thể tạo record cho key đó. Request còn lại phải đọc record hiện hữu và quyết định trả kết quả, chờ hoặc báo đang xử lý.

~~~mermaid
sequenceDiagram
    participant A as Replica A
    participant B as Replica B
    participant DB as Database
    par Cùng idempotency key
        A->>DB: INSERT key K
        B->>DB: INSERT key K
    end
    DB-->>A: Insert thành công
    DB-->>B: Unique constraint conflict
    A->>DB: Xử lý và cập nhật record
    B->>DB: Đọc record K
    DB-->>B: IN_PROGRESS hoặc kết quả đã lưu
~~~

**Không dùng distributed lock thay cho unique constraint.** Database phải bảo vệ uniqueness ngay tại nơi lưu trạng thái nghiệp vụ.

## 7. Quy trình xử lý API idempotent

Một flow tổng quát:

1. Xác thực caller và kiểm tra quyền nghiệp vụ.
2. Đọc idempotency key, xác định tenant/operation scope.
3. Chuẩn hóa request và tính fingerprint.
4. Thử tạo idempotency record với trạng thái IN_PROGRESS bằng thao tác atomic.
5. Nếu key đã tồn tại:
   - Fingerprint khác: trả conflict.
   - SUCCEEDED: trả lại kết quả đã lưu sau khi kiểm tra authorization.
   - IN_PROGRESS: trả trạng thái đang xử lý hoặc chờ có giới hạn.
   - FAILED_FINAL: trả lỗi cuối cùng đã ghi nhận.
   - RETRYABLE/UNKNOWN: đi theo recovery policy, không tự chạy lại mù.
6. Chủ sở hữu record thực hiện nghiệp vụ trong transaction/ranh giới phù hợp.
7. Lưu kết quả, resource ID và trạng thái hoàn tất.
8. Trả response.

### Response cho request trùng

| Tình trạng record | Phản hồi có thể dùng | Ý nghĩa |
| --- | --- | --- |
| Đã thành công | Cùng response/result đã lưu, thường cùng mã thành công | Retry nhận lại kết quả ban đầu |
| Đang xử lý | 202 Accepted kèm operation URL hoặc 409 Conflict theo API contract | Client biết thao tác chưa hoàn tất |
| Cùng key, payload khác | 409 Conflict | Key đã gắn với yêu cầu khác |
| Thất bại cuối cùng | Trả lỗi đã lưu hoặc mã lỗi tương ứng | Không chạy lại cùng key |
| Không xác định | 202/409 hoặc mã trạng thái theo contract | Cần tra cứu/reconcile |

Không có một status code duy nhất bắt buộc cho mọi API. Điều quan trọng là hợp đồng rõ ràng, response ổn định và caller biết cách tra cứu trạng thái.

## 8. Ví dụ Spring Boot: idempotency với unique constraint

Ví dụ dưới đây minh họa cấu trúc, cần điều chỉnh kiểu dữ liệu và SQL theo database thực tế.

### 8.1. Entity/record

~~~java
public record IdempotencyKey(
        String tenantId,
        String operation,
        String key) {
}

public record IdempotencyResult(
        String status,
        String requestHash,
        String resourceId,
        String responseJson) {
}
~~~

### 8.2. Repository contract

~~~java
public interface IdempotencyRepository {

    boolean tryInsertInProgress(
            IdempotencyKey key,
            String requestHash);

    IdempotencyResult find(IdempotencyKey key);

    void markSucceeded(
            IdempotencyKey key,
            String resourceId,
            String responseJson);

    void markFailedFinal(
            IdempotencyKey key,
            String errorCode);
}
~~~

tryInsertInProgress phải dựa vào **INSERT có unique constraint** và xử lý duplicate key theo semantics database. Không triển khai bằng SELECT rồi INSERT mà không có ràng buộc unique.

### 8.3. Application service

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentApplicationService {

    private final IdempotencyRepository idempotency;
    private final PaymentRepository payments;
    private final RequestFingerprint fingerprint;

    public PaymentApplicationService(
            IdempotencyRepository idempotency,
            PaymentRepository payments,
            RequestFingerprint fingerprint) {
        this.idempotency = idempotency;
        this.payments = payments;
        this.fingerprint = fingerprint;
    }

    public PaymentResponse create(
            String tenantId,
            String key,
            CreatePaymentCommand command) {

        String operation = "CREATE_PAYMENT";
        String hash = fingerprint.of(command);
        IdempotencyKey id = new IdempotencyKey(
                tenantId, operation, key);

        boolean owner = idempotency.tryInsertInProgress(id, hash);

        if (!owner) {
            IdempotencyResult existing = idempotency.find(id);

            if (!existing.requestHash().equals(hash)) {
                throw new IdempotencyConflictException();
            }

            if ("SUCCEEDED".equals(existing.status())) {
                return PaymentResponse.fromJson(existing.responseJson());
            }

            if ("IN_PROGRESS".equals(existing.status())) {
                throw new OperationInProgressException();
            }

            throw new OperationNeedsReconciliationException();
        }

        return createPaymentAndComplete(id, command);
    }

    @Transactional
    protected PaymentResponse createPaymentAndComplete(
            IdempotencyKey id,
            CreatePaymentCommand command) {

        Payment payment = payments.create(command);
        PaymentResponse response =
                new PaymentResponse(payment.id(), "ACCEPTED");

        idempotency.markSucceeded(
                id, payment.id(), response.toJson());

        return response;
    }
}
~~~

Đây là **pseudocode kiến trúc**, chưa phải implementation hoàn chỉnh. Một số điểm phải xử lý khi triển khai:

- Trong Spring proxy mode, self-invocation tới @Transactional method có thể không đi qua proxy. Nên tách transaction logic thành bean riêng hoặc đặt transaction boundary phù hợp.
- tryInsertInProgress và createPaymentAndComplete trong ví dụ phải có chiến lược transaction nhất quán. Nếu insert IN_PROGRESS được commit riêng rồi transaction nghiệp vụ rollback, cần recovery cho record mồ côi.
- Nếu record và payment được ghi trong cùng transaction, unique insert, payment insert và mark success có thể commit/rollback cùng nhau. Điều này phù hợp với thao tác ngắn hoàn toàn trong một database.
- Không gọi payment provider, Blob hoặc Service Bus trong transaction database dài nếu có thể tránh.
- Nếu side effect ở hệ thống ngoài database, cần outbox/state machine/reconciliation; transaction database không thể rollback giao dịch đã được hệ thống ngoài chấp nhận.
- Khi duplicate insert conflict, repository cần đọc lại record trong transaction mới hoặc sau khi transaction conflict kết thúc theo isolation semantics của database.

### 8.4. Ranh giới transaction đúng

Với nghiệp vụ chỉ ghi trong cùng một database:

~~~text
BEGIN
  INSERT idempotency record (unique key)
  INSERT payment/order
  UPDATE idempotency record = SUCCEEDED
COMMIT
~~~

Nếu bất kỳ bước nào thất bại trước commit, cả idempotency record và payment/order có thể rollback cùng nhau. Request retry sau đó có thể thử lại theo cùng key.

Với nghiệp vụ gọi external payment provider:

~~~text
BEGIN
  INSERT idempotency record
  INSERT payment intent / outbox command
COMMIT

Worker:
  Call payment provider with stable provider idempotency key
  Reconcile provider result
  Update payment and idempotency state
~~~

Không giữ transaction database mở trong khi chờ một API thanh toán từ xa. Dùng idempotency key ở provider nếu provider hỗ trợ và lưu trạng thái đối soát.

## 9. Chọn nơi lưu idempotency state

| Nơi lưu | Ưu điểm | Rủi ro/giới hạn |
| --- | --- | --- |
| **Cùng database nghiệp vụ** | Unique constraint và transaction có thể bảo vệ nguyên tử | Tăng tải DB; cần retention/cleanup |
| Redis | Độ trễ thấp, hỗ trợ atomic operations/TTL | Không tự đồng bộ với transaction nghiệp vụ; eviction/failover có thể làm mất record |
| Cosmos DB | Conditional create/ETag, scale và partitioning | Thiết kế partition key/transaction scope; consistency/unique key constraints theo container |
| DynamoDB | Conditional write và TTL | Thiết kế partition key, hot partition và TTL không xóa ngay lập tức |
| Firestore | Transaction/create precondition | Giới hạn transaction và contention theo document/key |
| Broker deduplication | Giảm duplicate message ở một phạm vi broker | Cửa sổ/semantics có giới hạn; consumer vẫn cần idempotent |

Nếu idempotency record nằm trong Redis nhưng order/payment nằm trong database, hai nơi không có transaction chung. Redis có thể ghi key thành công rồi database thất bại, hoặc ngược lại. Cần thiết kế trạng thái, recovery và nguồn sự thật rõ ràng.

**Với thao tác tài chính hoặc tác dụng phụ quan trọng, database transaction/unique constraint cùng trạng thái nghiệp vụ bền vững thường là nền tảng phù hợp hơn một cache TTL đơn thuần.**

## 10. Deduplication cho message: Inbox pattern

Broker thường cung cấp delivery semantics ít nhất một lần (**at-least-once**). Message có thể được giao lại nếu consumer chưa acknowledge/complete, lock hết hạn hoặc connection bị ngắt sau khi xử lý.

Consumer nên có **inbox/processed-message table**:

~~~sql
CREATE TABLE processed_messages (
    consumer_name  VARCHAR(100) NOT NULL,
    message_id     VARCHAR(200) NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    result_ref     VARCHAR(200),
    PRIMARY KEY (consumer_name, message_id)
);
~~~

Flow:

1. Nhận message có MessageId ổn định.
2. Bắt đầu database transaction.
3. Insert (consumer_name, message_id) vào inbox.
4. Nếu unique conflict, message đã xử lý; không chạy lại nghiệp vụ.
5. Nếu insert thành công, cập nhật business state.
6. Commit inbox record và business state cùng transaction.
7. Sau commit, complete/ack message.
8. Nếu process chết sau commit nhưng trước ack, broker giao lại; inbox phát hiện duplicate và consumer chỉ cần complete/ack mà không lặp side effect.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant DB as Database
    B->>C: Message M1
    C->>DB: BEGIN + INSERT inbox(M1)
    C->>DB: Update business state
    C->>DB: COMMIT
    C--xB: ACK bị mất / process crash
    B->>C: Redeliver M1
    C->>DB: INSERT inbox(M1)
    DB-->>C: Duplicate key
    C->>B: Complete/ACK, không lặp business update
~~~

Điều kiện quan trọng: **inbox record và business state phải nằm trong cùng transaction** nếu muốn bảo vệ nguyên tử. Nếu ghi inbox ở Redis rồi update database riêng, crash giữa hai bước vẫn có thể gây mất hoặc lặp xử lý.

### Consumer deduplication theo message ID

Message ID phải ổn định qua publisher retries. Nếu mỗi lần retry publisher tạo MessageId mới, inbox không nhận diện được duplicate. Nên dùng operation/event ID có nguồn gốc từ nghiệp vụ, không dùng trace ID ngẫu nhiên.

Nếu cùng message ID nhưng payload khác, consumer nên phát hiện conflict bằng fingerprint thay vì âm thầm bỏ qua.

## 11. Transactional outbox: bảo vệ publisher

Inbox bảo vệ consumer; **outbox** bảo vệ việc chuyển sự kiện từ database sang broker.

Giả sử một API cập nhật đơn hàng và phát OrderUpdated:

~~~text
BEGIN DATABASE TRANSACTION
  UPDATE orders
  INSERT outbox_events
COMMIT

Publisher:
  Read pending outbox event
  Send to broker using stable event ID
  Mark sent after suitable acknowledgement
~~~

Nếu database commit thành công nhưng broker tạm thời lỗi, outbox record vẫn còn để publisher thử lại. Nếu broker đã nhận nhưng ACK mất, publisher có thể gửi lại cùng event ID; consumer inbox/deduplication xử lý duplicate.

**Outbox không tạo exactly-once end-to-end.** Nó bảo đảm trạng thái nghiệp vụ và ý định phát sự kiện được lưu nguyên tử trong database; publish vẫn có thể lặp và consumer phải idempotent.

### Trạng thái outbox thường dùng

| Trạng thái | Ý nghĩa |
| --- | --- |
| PENDING | Chưa được publisher gửi |
| CLAIMED | Một worker đang xử lý/giữ lease |
| SENT | Đã nhận xác nhận publish theo contract |
| RETRY | Thử gửi lại sau thời điểm đã lên lịch |
| DEAD | Vượt retry budget hoặc lỗi cuối cùng, cần điều tra |

Publisher nhiều replica có thể dùng SELECT ... FOR UPDATE SKIP LOCKED, lease hoặc cơ chế claim atomic để chia công việc. Dù claim tránh hai worker cùng lấy một record trong thời điểm bình thường, **message ID ổn định và consumer idempotency vẫn cần thiết** vì worker có thể chết sau khi broker nhận message.

## 12. Khóa: khi nào cần và khi nào không?

**Lock** đảm bảo tại một thời điểm chỉ một tiến trình được quyền thực hiện một phần công việc trong phạm vi nhất định. Nhưng lock có thể hết hạn, mất kết nối hoặc bị tiến trình cũ tiếp tục sử dụng sau khi một tiến trình mới đã lấy lock.

| Cơ chế | Phạm vi | Đặc điểm |
| --- | --- | --- |
| **In-process mutex** | Một JVM | Không phối hợp được nhiều replica |
| **Database row lock** | Transaction/database | Có transaction semantics, nhưng lock lâu gây contention |
| **Unique constraint** | Database key | Ngăn tạo hai record trùng; thường phù hợp hơn lock cho uniqueness |
| **Optimistic locking** | Một row/document/version | Phát hiện update cạnh tranh mà không giữ lock lâu |
| **Distributed lease** | Nhiều process | Có owner và thời hạn; phải xử lý expiry/renewal |
| **Broker message lock** | Một lần giao message | Giới hạn thời gian consumer giữ message, không bảo đảm side effect chỉ xảy ra một lần |

### Không khóa mọi thứ

Nếu mục tiêu chỉ là ngăn tạo hai payment cho cùng một idempotency key, **unique constraint** thường đơn giản và chắc chắn hơn distributed lock.

Lock hữu ích khi cần loại trừ công việc tốn kém trong một khoảng thời gian, ví dụ chỉ một worker reconcile một account hoặc một job xử lý một partition. Dù có lock, thao tác ghi cuối cùng vẫn nên có idempotency/version/fencing để chống stale owner.

## 13. Distributed lock, lease và fencing token

Một distributed lock thường có thời hạn (**lease/TTL**) để nếu process chết thì lock có thể được giải phóng sau thời gian nhất định.

Ví dụ Redis thường gặp:

~~~text
SET lock:account:123 <unique-owner-token> NX PX 10000
~~~

- NX: chỉ tạo key nếu chưa tồn tại.
- PX 10000: TTL 10 giây.
- unique-owner-token: giá trị riêng để xác định chủ lock.

Khi release, phải kiểm tra owner token rồi mới xóa key bằng thao tác atomic (ví dụ Lua script). Nếu process A hết lease và process B lấy lock mới, A không được phép xóa lock của B.

### Vấn đề stale owner

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant L as Lock store
    participant B as Worker B
    participant R as Resource
    A->>L: Acquire lease
    L-->>A: Granted
    Note over A,L: A bị pause lâu hơn TTL
    L-->>B: Lease của A hết hạn
    B->>L: Acquire lease mới
    L-->>B: Granted
    A->>R: Tiếp tục ghi dù lease cũ đã hết
    B->>R: Ghi theo lease mới
~~~

Nếu A vẫn ghi được sau khi lease hết, hai worker có thể cùng tác động lên resource. Việc lock key đã hết TTL không tự ngăn process cũ tiếp tục chạy.

### Fencing token

Một **fencing token** là số tăng đơn điệu mỗi khi cấp lease mới. Resource đích chỉ chấp nhận thao tác từ token lớn hơn hoặc bằng token đã ghi nhận, theo contract cụ thể.

| Worker | Fencing token | Kết quả |
| --- | ---: | --- |
| Worker A | 41 | Được chấp nhận |
| Worker B sau khi A hết lease | 42 | Được chấp nhận, token mới hơn |
| Worker A tiếp tục chạy | 41 | Bị từ chối vì token cũ |

Fencing chỉ hiệu quả nếu **nơi ghi resource kiểm tra token**. Nếu lock store phát token nhưng database/Blob/API đích không xác minh, token không bảo vệ được side effect.

### Lease renewal

Nếu công việc dài hơn TTL, worker có thể renew lease. Cần:

- Renew trước khi hết hạn với khoảng dự phòng.
- Chỉ owner hiện tại mới được renew.
- Nếu renew thất bại, worker phải dừng bắt đầu side effect mới.
- Xử lý tình huống renew thành công nhưng response bị mất bằng cách kiểm tra owner/token.
- Không coi renew là bằng chứng worker cũ chưa bị pause hoặc mạng đã ổn định.

## 14. Optimistic concurrency: ETag và version

Không phải mọi thao tác đồng thời đều cần lock. **Optimistic concurrency** cho phép nhiều client đọc dữ liệu, nhưng chỉ chấp nhận update nếu version chưa thay đổi.

Ví dụ:

1. Client đọc order với version 7.
2. Client khác cập nhật thành version 8.
3. Client đầu gửi update với điều kiện version vẫn là 7.
4. Database/service từ chối vì version hiện tại là 8.
5. Client đọc lại và quyết định merge hoặc trả conflict.

~~~sql
UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
~~~

Nếu số row cập nhật bằng 0, version đã thay đổi hoặc resource không tồn tại. Đây là **compare-and-set**, không phải retry mù.

### ETag trong Azure Storage

Azure Blob Storage hỗ trợ điều kiện như **If-Match**/**If-None-Match** dựa trên ETag trong các operation phù hợp:

- **If-None-Match: \*** có thể dùng để tạo blob chỉ khi chưa tồn tại.
- **If-Match: <etag>** chỉ cho phép cập nhật nếu ETag hiện tại khớp giá trị đã đọc.
- Nếu điều kiện không khớp, service trả lỗi precondition/conflict tương ứng.

Những điều kiện này giúp ngăn ghi đè do race condition và hỗ trợ idempotency ở tầng resource. Cần kiểm tra API cụ thể của Blob SDK và error code/version đang dùng.

### ETag không phải idempotency key

ETag xác nhận version/trạng thái resource. Idempotency key xác định một ý định nghiệp vụ. Một thao tác có thể cần cả hai: key để nhận diện retry của cùng request, ETag để ngăn request khác ghi đè dữ liệu mới.

## 15. Khóa và điều kiện ghi trong các dịch vụ Azure

### Azure Blob Storage

Có thể kết hợp:

- Blob name ổn định theo resource/operation ID.
- Create-if-absent với điều kiện **If-None-Match: \***.
- Conditional update bằng ETag/If-Match.
- Blob lease khi cần loại trừ thao tác trên một blob trong khoảng thời gian.
- Metadata lưu operation ID hoặc version để hỗ trợ reconciliation.

**Blob lease không tự bảo đảm toàn bộ nghiệp vụ idempotent.** Lease có thể hết hạn hoặc mất, và tác dụng phụ ở database/Service Bus nằm ngoài phạm vi lease của Blob. Khi dùng lease, phải xử lý lease ID, renewal, release và lỗi lease conflict theo SDK/service contract.

### Azure Cosmos DB

Với Cosmos DB, thiết kế idempotency cần xét:

- Partition key và phạm vi transaction.
- **Transactional batch** chỉ áp dụng trong phạm vi logical partition theo hỗ trợ của API.
- Conditional create/upsert và ETag/If-Match theo operation.
- Unique key policy được cấu hình cho container; unique key được đánh giá trong phạm vi logical partition và có giới hạn thiết kế.
- Request charge/429 và retry của SDK.
- Consistency level và cách đọc lại trạng thái sau unknown outcome.

Không mặc định một transaction Cosmos DB có thể cập nhật nhiều logical partition hoặc đồng bộ với Service Bus. Nếu workflow vượt transaction boundary, cần outbox/saga/reconciliation phù hợp.

### Azure Service Bus

Service Bus cung cấp một số cơ chế hỗ trợ duplicate handling:

- **Duplicate detection** dùng MessageId để nhận diện message trùng trong một cửa sổ được cấu hình.
- **Peek-lock** giữ message trong thời gian lock; consumer complete/abandon/dead-letter theo settlement.
- **Sessions** hỗ trợ xử lý nhóm message theo session và session lock.
- Lock có thể được gia hạn theo cấu hình/client behavior.

Duplicate detection có **cửa sổ thời gian và phạm vi theo entity/configuration**; nó không phải kho idempotency vô hạn. Nếu cùng event được gửi lại sau cửa sổ hoặc MessageId khác, broker có thể coi là message mới. Consumer vẫn nên có inbox/deduplication bền vững cho side effect quan trọng.

## 16. So sánh idempotency và deduplication trên AWS, Azure, Google Cloud

| Nhu cầu | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| Conditional write object | Blob ETag/If-Match/If-None-Match | S3 conditional requests/preconditions tùy API | Cloud Storage generation preconditions |
| Database conditional write | Cosmos DB ETag/transactional batch/native unique key policy | DynamoDB condition expressions/transactions | Firestore transactions/create precondition; Spanner transactions |
| Broker duplicate handling | Service Bus duplicate detection theo MessageId/cửa sổ | SQS FIFO deduplication theo deduplication ID/cửa sổ; content-based option | Pub/Sub message IDs/delivery semantics; exactly-once delivery có phạm vi subscription/region theo tính năng |
| Consumer deduplication bền vững | Inbox table/database | DynamoDB/relational inbox | Firestore/Spanner/relational inbox |
| Lock/lease | Blob lease, Service Bus message lock, database/Redis lease | SQS visibility timeout, DynamoDB conditional lease/lock | Pub/Sub ack deadline, database/lease store |
| Retry và unknown outcome | SDK/service retry + idempotency state | SDK retry + conditional write | RPC retry + transaction/precondition |

Không ánh xạ máy móc **Service Bus duplicate detection** thành **SQS FIFO deduplication** hoặc Pub/Sub exactly-once delivery. Phạm vi, thời gian lưu dấu, message ordering, redelivery và ack semantics khác nhau.

### Một số giới hạn cần nhớ

- **Amazon SQS FIFO** có deduplication window hữu hạn; producer retry ngoài cửa sổ hoặc sử dụng deduplication ID khác vẫn có thể tạo message mới.
- **Google Cloud Pub/Sub exactly-once delivery** là tính năng có phạm vi và điều kiện cụ thể; không biến toàn bộ side effect của consumer thành exactly-once.
- **Cloud Storage generation preconditions** bảo vệ object version/write condition, không bảo vệ database và messaging cùng lúc.
- **DynamoDB conditional write** có thể bảo vệ uniqueness/claim theo key; TTL cleanup không nhất thiết xảy ra chính xác tại thời điểm hết hạn.
- **Cosmos DB unique key** có phạm vi logical partition; partition key cần được chọn theo invariant nghiệp vụ.

## 17. Retention, cleanup và tái sử dụng idempotency key

Idempotency record không thể giữ vô hạn trong mọi hệ thống. Cần xác định thời gian lưu dựa trên:

- Thời gian client/proxy có thể retry request.
- Thời gian broker có thể redeliver message.
- Chu kỳ batch/job hoặc workflow.
- Yêu cầu audit và tranh chấp nghiệp vụ.
- Rủi ro client gửi lại một key cũ sau khi record đã bị xóa.

Nếu xóa record quá sớm, một retry đến muộn có thể được hiểu là yêu cầu mới và tạo tác dụng phụ trùng.

### Chính sách retention

| Loại thao tác | Retention cần cân nhắc |
| --- | --- |
| API read không side effect | Có thể không cần idempotency record |
| Tạo đơn hàng | Theo cửa sổ retry của client và quy tắc chống tạo đơn trùng |
| Payment/financial operation | Theo chính sách nghiệp vụ, đối soát và audit; thường dài hơn retry HTTP thông thường |
| Message inbox | Ít nhất bao phủ cửa sổ redelivery/replay và yêu cầu chống xử lý trùng |
| Outbox event | Đến khi publish/đối soát xong; lịch sử có thể archive |
| Job scheduler | Bao phủ khả năng chạy lại/recovery của job |

### Hết hạn key không đồng nghĩa được phép tái sử dụng ngay

Nếu một payment đã hoàn thành, xóa idempotency record sau 24 giờ không có nghĩa cùng key hoặc cùng business operation có thể được tạo lại an toàn. Có thể cần giữ **business unique reference** lâu hơn record kỹ thuật. Nên tách:

- Idempotency cache/record phục vụ retry kỹ thuật.
- Unique business constraint bảo vệ invariant dài hạn.
- Audit/history phục vụ điều tra và đối soát.

Cleanup nên chạy theo batch có giới hạn, tránh xóa record đang IN_PROGRESS, UNKNOWN hoặc cần reconcile. Có thể partition theo ngày/tenant hoặc archive để quản lý dung lượng.

## 18. Xử lý trạng thái IN_PROGRESS và worker bị chết

Một request có thể tạo idempotency record IN_PROGRESS rồi process bị crash. Nếu không có recovery, key có thể bị kẹt mãi.

Một thiết kế workflow dài nên lưu thêm:

- owner_id hoặc worker ID.
- lease_until hoặc next_heartbeat_at.
- attempt_count.
- last_error_code.
- updated_at.
- operation_deadline hoặc expires_at.
- fencing_token nếu có lease và resource hỗ trợ kiểm tra.

Recovery worker có thể tìm record đã quá lease, xác định side effect đã xảy ra chưa, rồi chuyển sang RETRYABLE, UNKNOWN, SUCCEEDED hoặc FAILED_FINAL.

**Không chỉ dựa vào TTL để kết luận worker cũ đã dừng.** Process có thể pause lâu rồi tiếp tục chạy. Khi reclaim công việc, fencing/version check cần ngăn owner cũ ghi kết quả sau owner mới.

### Trạng thái không xác định

Nếu request đến payment provider bị timeout sau khi gửi, không thể lập tức đánh dấu FAILED_FINAL. Cần gọi API tra cứu theo provider idempotency key/transaction reference nếu được hỗ trợ, hoặc chờ webhook/settlement và reconcile. Trong thời gian chưa rõ, giữ trạng thái UNKNOWN và ngăn tạo một payment mới cho cùng business operation.

## 19. Lock không thay thế idempotency: ví dụ xử lý message

Giả sử một Service Bus consumer xử lý message OrderPaid:

~~~text
Worker A nhận message, lock 30 giây
Worker A gọi payment/accounting service
Worker A bị pause 40 giây
Lock hết hạn
Worker B nhận lại message và xử lý
Worker A tiếp tục chạy
~~~

Cả A và B có thể cùng thực hiện side effect nếu service đích không kiểm tra operation ID/version. Lock chỉ giảm xác suất xử lý đồng thời trong khoảng lease; nó không chứng minh worker cũ đã dừng.

Cách bảo vệ:

1. Dùng MessageId/event ID ổn định.
2. Consumer insert inbox record bằng unique constraint trong transaction cùng business update.
3. Nếu dùng distributed lock cho công việc dài, dùng lease + fencing token được resource đích kiểm tra.
4. Đảm bảo external API nhận idempotency key nếu hỗ trợ.
5. Complete message sau khi transaction business/inbox commit.
6. Nếu crash trước complete, redelivery được inbox nhận diện.

### Message ID phải ổn định

Publisher nên tạo event ID từ operation/event được lưu trong outbox. Nếu mỗi lần gửi lại tạo UUID mới, broker duplicate detection và consumer inbox sẽ không nhận ra đó là cùng một sự kiện.

## 20. Bảo mật idempotency key và lock

- Không coi idempotency key là credential hoặc bằng chứng caller có quyền.
- Ràng buộc key theo tenant/principal và operation; kiểm tra authorization khi trả response cũ.
- Không lưu raw secret hoặc payload nhạy cảm trong record nếu không cần.
- Không log toàn bộ request body, key hoặc lock owner token nếu chính sách yêu cầu che.
- Không cho caller tùy ý chọn resource ID để truy xuất kết quả của tenant khác.
- Lock key phải có namespace rõ ràng và TTL hợp lý; tránh key collision giữa môi trường/tenant.
- Redis lock release phải kiểm tra owner token atomic; không dùng DEL vô điều kiện.
- Giới hạn quyền truy cập bảng idempotency/inbox/outbox và bảo vệ dữ liệu audit.
- Cleanup phải tránh xóa record đang xử lý hoặc đang được dùng để reconcile.

## 21. Quan sát và kiểm thử

### Metrics nên theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| idempotency_first_seen_total | Yêu cầu được nhận lần đầu |
| idempotency_replay_total | Request trùng được trả lại kết quả |
| idempotency_conflict_total | Cùng key nhưng fingerprint khác |
| idempotency_in_progress_total | Request gặp operation đang xử lý |
| idempotency_unknown_outcome_total | Kết quả cần reconciliation |
| deduplication_hit_total | Message/resource duplicate được nhận diện |
| lock_acquire_total / lock_contended_total | Trạng thái tranh chấp lock |
| lease_expired_total | Lease hết hạn trước khi hoàn tất |
| fencing_rejected_total | Owner/token cũ bị từ chối |
| outbox_pending_count | Số event chưa publish |
| inbox_duplicate_total | Message đã xử lý được giao lại |

Không dùng idempotency key, user ID, payment ID hoặc message ID làm metric label có cardinality cao. Dùng các giá trị này trong log/trace có kiểm soát, masking và retention phù hợp.

### Test case bắt buộc

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Cùng key, cùng payload, request tuần tự | Chỉ một business effect; lần sau nhận lại kết quả |
| Cùng key, payload khác | Conflict; không chạy nghiệp vụ lần hai |
| Hai request đồng thời cùng key | Unique constraint chỉ cho một owner |
| Process crash sau commit, trước response | Retry nhận kết quả đã lưu |
| Process crash trước commit | Transaction rollback; recovery cho phép thử lại |
| Message redelivery sau commit, trước ACK | Inbox phát hiện duplicate |
| Lock hết hạn, worker cũ tiếp tục | Fencing/version ngăn stale write |
| Retry sau khi retention hết | Business unique constraint vẫn bảo vệ invariant cần giữ |
| Publisher mất ACK sau broker acceptance | Cùng event ID; consumer chống xử lý trùng |
| Redis lock store failover | Không giả định lock còn nguyên; kiểm tra fencing/idempotency |

### Kiểm thử race condition

Để kiểm tra hai request đồng thời:

1. Khởi chạy nhiều thread hoặc nhiều process gửi cùng idempotency key.
2. Đồng bộ thời điểm bắt đầu bằng barrier/latch.
3. Ghi nhận số lần business operation thực sự được thực hiện.
4. Xác minh chỉ một record/key được tạo.
5. Xác minh các request còn lại nhận response theo contract.
6. Chạy lại qua nhiều replica để kiểm tra uniqueness ở database, không chỉ lock trong JVM.

Không dùng synchronized trong một instance để kết luận hệ thống nhiều replica đã chống duplicate.

## 22. Bài thực hành: xây dựng API tạo payment idempotent

**Bối cảnh:** Spring Boot Payment API nhận POST /payments, tạo payment record và phát PaymentRequested lên Service Bus. Client có thể retry khi mất response; worker có thể crash sau khi publish.

### Phần A — Idempotency cho API

1. Yêu cầu header Idempotency-Key.
2. Xác định scope (tenant_id, operation, key).
3. Chuẩn hóa request và tính fingerprint.
4. Tạo bảng idempotency có unique constraint.
5. Trong một database transaction, tạo payment và cập nhật idempotency result nếu toàn bộ side effect còn trong database.
6. Nếu cùng key/payload đã thành công, trả kết quả cũ.
7. Nếu cùng key nhưng payload khác, trả conflict.
8. Nếu đang xử lý, trả operation status hoặc response theo API contract.

### Phần B — Outbox và consumer inbox

1. Trong transaction tạo payment, ghi thêm outbox event có event ID ổn định.
2. Publisher lấy pending event bằng claim/lease có giới hạn.
3. Gửi event lên Service Bus với MessageId bằng event ID.
4. Đánh dấu sent sau acknowledgment theo contract.
5. Consumer insert inbox record và business update trong cùng transaction.
6. Khi nhận duplicate, bỏ qua business update và complete message.

### Phần C — Khóa và concurrency

1. Chạy hai request đồng thời cùng key.
2. Xác minh unique constraint bảo vệ chỉ một payment.
3. Nếu có worker lease, dùng owner token/lease expiry và fencing/version.
4. Giả lập worker cũ tiếp tục sau khi lease hết.
5. Xác minh stale write bị từ chối ở nơi lưu trạng thái.

### Phần D — Failure injection

1. Ngắt response sau khi payment transaction commit.
2. Làm publisher mất ACK sau khi broker có thể đã nhận message.
3. Kill consumer sau database commit nhưng trước message completion.
4. Cho message redeliver và xác minh inbox ngăn side effect trùng.
5. Tạo cùng key với payload khác và xác minh conflict.
6. Kiểm tra cleanup/retention không xóa record còn cần đối soát.

### Sản phẩm cần nộp

- Schema idempotency, outbox và inbox.
- API contract cho header key và response khi replay/in-progress/conflict.
- Sơ đồ transaction boundary và message flow.
- Bằng chứng test concurrency, crash/retry và redelivery.
- Chính sách retention, reconciliation, lock/lease và fencing nếu dùng.
- Metrics duplicate, lock contention, outbox backlog và unknown outcome.

### Câu hỏi tự kiểm tra

1. Vì sao timeout của client không chứng minh server chưa commit?
2. Cùng idempotency key nhưng payload khác phải được xử lý thế nào?
3. Vì sao SELECT rồi INSERT không đủ chống hai request đồng thời?
4. Unique constraint và distributed lock giải quyết vấn đề khác nhau thế nào?
5. Vì sao lock hết TTL không bảo đảm worker cũ đã dừng?
6. Fencing token chỉ có tác dụng khi thành phần nào kiểm tra nó?
7. Inbox record phải nằm trong transaction nào để chống xử lý message trùng?
8. Outbox bảo vệ khoảng trống nào giữa database và broker?
9. Vì sao broker duplicate detection không thay thế consumer idempotency?
10. ETag/If-Match khác idempotency key ở điểm nào?
11. Vì sao retention của idempotency record phải xét cả business unique constraint?
12. Khi payment provider trả timeout với unknown outcome, tại sao không nên tạo payment mới ngay?

## 23. Ghi nhớ

- **Idempotency** bảo vệ kết quả nghiệp vụ khi cùng ý định được gửi lại; **deduplication** nhận diện lần gửi/giao trùng; **lock** điều phối quyền xử lý trong một phạm vi/thời hạn.
- Idempotency key cần ổn định, có scope, fingerprint payload và retention phù hợp. Cùng key nhưng payload khác phải bị từ chối theo API contract.
- **Unique constraint/conditional write** là hàng rào nguyên tử tại nơi lưu trạng thái. SELECT trước INSERT và synchronized trong một JVM không đủ chống race condition nhiều replica.
- **Distributed lease** có thể hết hạn khi worker cũ vẫn chạy. Dùng fencing/version được resource đích kiểm tra để ngăn stale owner.
- **Inbox/outbox** bảo vệ ranh giới database và messaging; không tạo exactly-once end-to-end, nên consumer vẫn phải idempotent.
- Blob ETag/lease, Cosmos DB partition/transaction, Service Bus duplicate detection/lock, SQS FIFO/visibility và Pub/Sub ack/exactly-once có phạm vi khác nhau.
- Timeout tạo unknown outcome; tra trạng thái, reconciliation, idempotency key và business unique constraint quan trọng hơn retry mù.
- Kiểm thử request đồng thời, crash giữa commit và ACK, lease expiry, duplicate delivery, payload conflict và retention; đo duplicate hit, contention và backlog.

## Tài liệu tham khảo

- [Azure Service Bus duplicate detection](https://learn.microsoft.com/azure/service-bus-messaging/duplicate-detection)
- [Azure Service Bus message locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Azure Blob Storage concurrency management](https://learn.microsoft.com/azure/storage/blobs/concurrency-manage)
- [Azure Cosmos DB transactional batch](https://learn.microsoft.com/azure/cosmos-db/nosql/transactional-batch)
- [Azure Cosmos DB unique keys](https://learn.microsoft.com/azure/cosmos-db/unique-keys)
- [AWS SQS FIFO deduplication](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [Amazon DynamoDB condition expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html)
- [Google Cloud Pub/Sub exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Cloud Storage request preconditions](https://cloud.google.com/storage/docs/request-preconditions)
- [Transactional outbox pattern](https://learn.microsoft.com/azure/architecture/databases/guide/transactional-outbox-cosmos)
