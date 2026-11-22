# Duplicate message do crash sau khi side effect trong Spring Integration Runtime

## Mục tiêu bài học

Trong **SPRING_INTEGRATION_RUNTIME**, một message có thể đi qua inbound adapter, channel, poller, executor, service activator và message store rồi tạo side effect tại cơ sở dữ liệu, broker hoặc dịch vụ bên ngoài. **Crash sau khi side effect** là tình huống ứng dụng đã thực hiện tác dụng nghiệp vụ nhưng chết **trước khi ghi nhận hoàn tất hoặc ack message**. Khi restart, nguồn có thể giao lại cùng yêu cầu và handler tạo tác dụng lần hai nếu không có idempotency.

Đây là bài thuộc chương **Persistence và restart**. Mục tiêu không phải xóa sạch duplicate delivery bằng mọi giá, mà là bảo đảm **nhiều lần delivery của cùng thao tác chỉ dẫn đến một kết quả nghiệp vụ hợp lệ**.

Sau bài học, bạn có thể:

- Vẽ timeline crash giữa **side effect – transaction commit – checkpoint – acknowledgment – restart**.
- Phân biệt **delivery**, **handler attempt** và **business side effect** khi có retry nhiều tầng.
- Chọn khóa idempotency đúng: **eventId/operationId**, không nhầm với message ID hay correlationId.
- Giải thích vì sao ghi dấu đã xử lý **quá sớm** làm mất nghiệp vụ, còn **quá muộn** có thể tạo duplicate.
- Áp dụng **transactional inbox** cho thay đổi thuộc cùng DB và **transactional outbox** cho phát event.
- Thiết kế bảo vệ payment/HTTP/email side effect bằng idempotency key, đối soát và trạng thái chưa xác định.
- Hiểu giới hạn của **MessageStore**, **MetadataStore**, **IdempotentReceiverInterceptor**, transaction, executor và poller.
- Kiểm thử các crash window, broker redelivery, multi-instance và persistent state sau restart.

> **Nguyên tắc:** Broker có thể giao lại message. Quan trọng là **business operation không bị áp dụng hai lần**. Spring Integration cung cấp công cụ điều phối; tính idempotent của nghiệp vụ phải được thiết kế tại nơi phát sinh side effect.

## 1. Timeline: thanh toán thành công nhưng message chưa được ack

Giả sử consumer nhận lệnh ChargePayment với **paymentId=PAY-42**.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Spring Integration consumer
    participant P as Payment provider
    B->>C: Deliver PAY-42 (delivery 1)
    C->>P: Charge PAY-42
    P-->>C: Đã trừ tiền, response OK
    Note over C: Process crash trước ACK
    B->>C: Redeliver PAY-42 (delivery 2)
    C->>P: Charge PAY-42 lần nữa?
    Note over P: Có nguy cơ trừ tiền hai lần
~~~

**Side effect** là thay đổi có thể quan sát bên ngoài handler: charge, ghi DB đã commit, gửi email, publish event, tạo file, gọi API. Side effect không phải lúc nào cũng rollback được khi JVM chết.

Timeline:

~~~text
T0  Consumer nhận message M1.
T1  Handler xác thực và bắt đầu xử lý.
T2  Payment provider đã nhận và thực hiện charge.
T3  Ứng dụng chưa commit trạng thái PROCESSED hoặc chưa ACK nguồn.
T4  Pod/process bị kill.
T5  Broker phát lại cùng paymentId trong delivery mới.
T6  Handler chạy lại; nếu không idempotent, có thể charge lần hai.
~~~

Delivery mới có thể được adapter biểu diễn thành **Spring Message mới** với một **MessageHeaders.ID khác**, dù paymentId vẫn là một. Vì vậy ID kỹ thuật của Spring Message **không phù hợp làm khóa chống lặp xuyên restart**.

**Đọc đúng khái niệm commit:** Gọi repository.save() chưa chứng minh DB đã commit; nó có thể nằm trong transaction chưa kết thúc. Tương tự, client gọi broker.send() chưa chứng minh broker đã xác nhận publish bền vững. Thiết kế crash window phải dựa vào **khoảnh khắc một side effect thật sự đã commit** theo hợp đồng từng hệ thống.

## 2. Ma trận crash và hậu quả

| Vị trí crash | Side effect | Dấu hoàn tất / ack | Rủi ro |
| --- | --- | --- | --- |
| Trước khi side effect | Chưa xảy ra | Chưa hoàn tất | Có thể xử lý lại |
| **Sau effect commit, trước ghi dấu xử lý** | **Đã xảy ra** | Chưa ghi dấu | **Duplicate effect khi replay** |
| Sau khi ghi dấu bền vững, trước broker ack | Đã xảy ra | Dấu có, ack chưa | Delivery có thể lặp; dedup có thể chặn effect |
| **Sau ack, trước effect commit** | Có thể chưa xảy ra | Ack đã xong | **Mất nghiệp vụ khi crash** |
| Sau publish event, trước đánh dấu outbox đã gửi | Broker có thể đã nhận | Outbox vẫn pending | Publish event có thể lặp |
| Sau đánh dấu outbox đã gửi, trước publish | Broker chưa nhận | Outbox tưởng đã gửi | **Mất event** |

Hai lỗi đối xứng cần tránh:

1. **Ack/dấu đã xử lý quá sớm:** lần sau bỏ qua một nghiệp vụ chưa hề hoàn tất.
2. **Ack/dấu đã xử lý quá muộn:** lần sau lặp lại một side effect đã hoàn tất.

Với tài nguyên **không chia sẻ cùng transaction**, đổi thứ tự hai dòng code thường chỉ đổi **kiểu lỗi**, không xóa khoảng hở. Cần mẫu thiết kế chịu được crash.

## 3. Delivery, retry attempt và business operation

| Khái niệm | Đơn vị | Ví dụ |
| --- | --- | --- |
| **Delivery** | Một lần broker/poller giao message tới consumer | Kafka record được đọc lại sau offset chưa commit; JMS/AMQP redelivery theo cấu hình |
| **Handler attempt** | Một lần gọi logic handler | RequestHandlerRetryAdvice gọi handler 3 lần trong một delivery |
| **External call attempt** | Một lần gọi HTTP/DB client | HTTP client thử lại request timeout |
| **Business operation** | Một thao tác nghiệp vụ duy nhất | charge:PAY-42 |

Một nghiệp vụ có thể đi qua nhiều delivery và nhiều attempt:

~~~text
operationId = charge:PAY-42
delivery #1
  handler attempt #1 -> HTTP timeout (provider có thể đã charge)
  handler attempt #2 -> HTTP timeout
  process crash trước ack
delivery #2
  handler attempt #1 -> gọi lại charge:PAY-42
~~~

Có thể có **3 HTTP calls, 2 deliveries, nhưng chỉ nên có 1 charge nghiệp vụ**. Nếu provider không hỗ trợ idempotency hoặc API tra cứu trạng thái, timeout không đủ chứng minh rằng charge chưa xảy ra.

### Bảo đảm giao message không tự bảo đảm side effect

- **At-most-once** thường ưu tiên không lặp delivery, nhưng có thể mất message khi crash.
- **At-least-once** ưu tiên giao lại khi chưa xác nhận; duplicate delivery là tình huống phải dự kiến.
- **Exactly-once** chỉ có ý nghĩa trong phạm vi tài nguyên và giao thức cụ thể hỗ trợ nó. Không tự mở rộng sang HTTP, email, một DB khác hoặc mọi adapter trong Spring Integration.
- **Idempotent operation** nhận diện cùng một lệnh qua nhiều attempt và không áp dụng side effect ngoài ý muốn thêm lần nào.

Mục tiêu khả thi cho nhiều flow là **at-least-once delivery + durable business idempotency**.

## 4. Khóa chống duplicate: dùng gì và không dùng gì?

| Trường | Ý nghĩa | Phù hợp làm dedup key? |
| --- | --- | --- |
| **MessageHeaders.ID** | Định danh kỹ thuật của một Spring Message | **Không**, có thể thay khi adapter tạo message mới |
| **eventId** | Định danh một event nguồn duy nhất | Có, nếu producer bảo đảm ổn định |
| **paymentId / operationId** | Định danh một side effect nghiệp vụ | Có, theo loại thao tác |
| **orderId** | Định danh thực thể | Không đủ nếu cùng order có nhiều thao tác khác nhau |
| **correlationId** | Liên kết các message cùng workflow | Không mặc định; workflow có thể chứa nhiều event |
| **deliveryCount / attemptId** | Số lần thử hoặc delivery | Không, chúng thay đổi khi retry |
| **traceId** | Truy vết một execution phân tán | Không thay idempotency key |

**Ví dụ khóa tốt:** consumer=order-projection-v1, eventId=EV-42; hoặc operation=payment-capture, paymentId=PAY-42.

**Namespace rất quan trọng:** Hai consumer độc lập xử lý cùng eventId để tạo hai projection khác nhau không được chặn lẫn nhau. Dedupe key nên bao gồm **consumer/operation name**. Nếu khóa trùng mà payload khác nội dung, hãy ghi **identity conflict** và điều tra, không âm thầm bỏ qua một lệnh có thể đã bị sửa.

Khi retry, giữ **eventId/idempotencyKey/correlationId** ổn định; chỉ tạo executionId/trace span/attempt number mới cho chẩn đoán.

## 5. Ba anti-pattern thường gây mất hoặc lặp side effect

### A. Đánh dấu DONE trước khi thực hiện side effect

~~~java
// Sai khi metadata được commit độc lập với side effect.
if (metadataStore.putIfAbsent(eventId, "DONE") != null) {
    return; // đã thấy event
}
paymentProvider.charge(paymentId);
~~~

Nếu crash **sau putIfAbsent nhưng trước charge**, lần delivery sau thấy DONE và bỏ qua. Nghiệp vụ **không hề xảy ra** dù store báo hoàn tất.

### B. Đánh dấu DONE sau khi external API trả thành công

~~~java
paymentProvider.charge(paymentId);
metadataStore.put(eventId, "DONE");
~~~

Nếu provider đã charge nhưng JVM crash trước khi ghi DONE, lần sau gọi provider lần nữa. **Có nguy cơ thu tiền hai lần**. Dời dòng ghi xuống sau không làm hai hệ thống có chung transaction.

### C. Dùng Set/HashMap in-memory để chống lặp

~~~java
Set<String> seen = ConcurrentHashMap.newKeySet();
if (seen.add(eventId)) {
    performBusinessEffect();
}
~~~

Set mất khi restart và mỗi replica có bản riêng; thao tác add còn có cùng lỗi **claim trước, crash trước effect**. ConcurrentHashMap chỉ giúp một số thao tác atomic **trong một JVM**, không làm state bền vững.

**Thiết kế đúng phụ thuộc tài nguyên:** side effect trong DB dùng transaction chung với inbox; event ra broker dùng outbox; HTTP/payment dùng provider idempotency và đối soát; file/FTP cần checkpoint bền vững cùng quy tắc xử lý trùng.

## 6. Transactional Inbox: xử lý lại message nhưng không update DB hai lần

Giả sử consumer nhận **OrderConfirmed**, cập nhật projection và ghi một outbox event. Ba thay đổi **inbox + projection + outbox** cùng nằm trong một **PostgreSQL transaction**.

~~~mermaid
flowchart TD
    M["Inbound eventId=EV-42"] --> T["DB transaction"]
    T --> I{"INSERT inbox<br/>consumer + eventId"}
    I -- "Key đã commit" --> D["Duplicate: bỏ qua update"]
    I -- "Key mới" --> U["UPDATE / INSERT business data"]
    U --> O["INSERT outbox event"]
    O --> C["COMMIT cả ba bảng"]
    C --> A["ACK theo adapter contract"]
    D --> A
~~~

Nếu process chết **trước DB commit**, toàn bộ các thay đổi rollback cùng nhau. Nếu chết **sau DB commit nhưng trước broker ack**, broker có thể redeliver, nhưng khóa inbox đã tồn tại nên handler không thực hiện lại thay đổi.

### SQL mẫu (PostgreSQL)

~~~sql
CREATE TABLE processed_message (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE order_projection (
    order_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    last_event_id TEXT NOT NULL
);

CREATE TABLE outbox_message (
    outbox_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    published_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

**processed_message** không chỉ có ý nghĩa “tôi đã gặp event”, mà là **transaction chứa việc xử lý event đã được commit**. Đừng tách việc ghi DONE sang một transaction khác rồi gọi đó là transactional inbox.

### Ví dụ Service Activator dùng JdbcTemplate

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

record OrderConfirmed(String eventId, String orderId) {}

@Component
class OrderProjectionHandler {
    private final JdbcTemplate jdbc;

    OrderProjectionHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @ServiceActivator(inputChannel = "confirmedOrders")
    @Transactional(transactionManager = "transactionManager")
    public void handle(Message<OrderConfirmed> incoming) {
        OrderConfirmed event = incoming.getPayload();
        if (event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()) {
            throw new IllegalArgumentException("Missing business ID");
        }

        int claimed = jdbc.update("""
                INSERT INTO processed_message(consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """,
                "order-projection-v1", event.eventId());

        if (claimed == 0) {
            return; // Đã được xử lý và commit trong DB này.
        }

        jdbc.update("""
                INSERT INTO order_projection(order_id, status, last_event_id)
                VALUES (?, 'CONFIRMED', ?)
                ON CONFLICT (order_id)
                DO UPDATE SET status = EXCLUDED.status,
                              last_event_id = EXCLUDED.last_event_id
                """,
                event.orderId(), event.eventId());

        jdbc.update("""
                INSERT INTO outbox_message(
                    outbox_id, order_id, event_type, payload_json)
                VALUES (?, ?, 'ORDER_CONFIRMED',
                    jsonb_build_object(
                        'orderId', CAST(? AS TEXT),
                        'sourceEventId', CAST(? AS TEXT)))
                """,
                "order-confirmed:" + event.eventId(),
                event.orderId(),
                event.orderId(),
                event.eventId());
    }
}
~~~

**Điều kiện để ví dụ đúng:**

1. Sử dụng PostgreSQL cho **ON CONFLICT** và **jsonb_build_object**; DB khác cần cú pháp khác.
2. Cả ba SQL chạy trong **cùng transaction** với một transaction manager/DataSource; annotation **@Transactional** phải thực sự được Spring proxy/advice áp dụng.
3. Khi bất kỳ update nào ném exception trước commit, cả **inbox, projection và outbox** rollback. Không bắt exception rồi return success.
4. **Unique constraint** bảo vệ hai consumer cùng xử lý eventId đồng thời; đừng thay bằng cặp SELECT rồi INSERT rời rạc.
5. Ví dụ không xử lý **event version/out-of-order**; nhiều eventId khác nhau của cùng order cần luật thứ tự/version riêng.
6. Nếu cùng eventId nhưng nội dung khác, cần so sánh fingerprint/điều tra xung đột; code tối giản chưa thực hiện.
7. ACK nguồn xảy ra theo adapter, **không được giả định** nằm trong cùng transaction DB. Việc redelivery vẫn có thể xảy ra và được inbox xử lý an toàn.

### Bốn tình huống crash với transactional inbox

~~~text
A. Crash sau INSERT inbox nhưng trước COMMIT
   → ROLLBACK cả inbox + business + outbox.
   → Lần sau được xử lý lại.

B. Crash sau UPDATE business nhưng trước COMMIT
   → ROLLBACK cả thay đổi business và inbox.
   → Lần sau xử lý lại, không mất nghiệp vụ.

C. Crash sau COMMIT nhưng trước ACK nguồn
   → Dấu inbox và business/outbox đã commit.
   → Redelivery được nhận diện; không áp dụng effect lần hai.

D. Crash sau ACK đúng theo topology này
   → DB đã commit trước đó.
   → Không cần replay để hoàn tất phần DB.
~~~

**Quan trọng:** Đừng dùng một transaction test luôn rollback vào cuối mỗi test rồi kết luận state vẫn còn qua restart. Phải kiểm tra bằng commit thật, và tạo tiến trình mới khi cần chứng minh durability.

## 7. Transactional Outbox: side effect publish vẫn có thể lặp

Đối với event phải được gửi ra broker **sau DB commit**, outbox giải quyết khoảng hở giữa thay đổi DB và publish. Handler **ghi event vào outbox trong transaction**; publisher riêng đọc pending event và phát.

~~~mermaid
sequenceDiagram
    participant D as Business DB
    participant W as Outbox publisher
    participant B as Broker
    participant C as Consumer
    W->>D: Read pending EV-42
    D-->>W: Event EV-42
    W->>B: Publish EV-42
    B-->>W: Ack accepted
    Note over W: Crash trước khi mark published
    W->>D: Sau restart: EV-42 vẫn pending
    W->>B: Publish EV-42 lại
    B->>C: Có thể nhận hai lần cùng eventId
    Note over C: Consumer idempotent
~~~

**Không đánh dấu published trước khi gửi** chỉ để né duplicate: crash trước publish sẽ **mất event**. Publisher nên:

- Có claim/lease hoặc transaction DB phù hợp khi nhiều publisher cùng chạy; ví dụ **FOR UPDATE SKIP LOCKED** khi thiết kế theo PostgreSQL.
- Gửi cùng một **outbox_id/eventId ổn định** trong mọi lần publish.
- Chờ xác nhận broker theo hợp đồng producer, rồi mới cập nhật trạng thái published.
- Retry/backoff có giới hạn, cảnh báo backlog và có replay an toàn sau restart.
- Được consumer downstream xử lý idempotent vì event có thể publish nhiều lần.

**afterCommit callback** có thể đánh thức publisher sớm, nhưng không thay thế bảng outbox: app vẫn có thể crash giữa DB commit và callback.

## 8. External side effect: payment, email và HTTP

Khi side effect ở HTTP API hoặc payment provider, một transaction DB cục bộ không atomic với kết quả phía ngoài:

~~~text
DB: lưu CHARGE_REQUESTED
HTTP: provider nhận và charge thành công
PROCESS: crash trước khi ghi CONFIRMED
RESTART: chỉ nhìn thấy CHARGE_REQUESTED
~~~

Không thể biết chắc provider đã charge hay chưa chỉ từ DB nội bộ. Cần **idempotency key do provider thực thi** và/hoặc API **tra cứu kết quả**.

~~~java
record ChargeCommand(String paymentId, long amountMinor, String currency) {}

// Pseudocode: chữ ký của payment SDK thực tế có thể khác.
String idempotencyKey = "charge:" + command.paymentId();
ChargeResult result = paymentClient.charge(
        command.amountMinor(),
        command.currency(),
        idempotencyKey);
~~~

Những câu hỏi bắt buộc trước khi tự động retry:

1. Provider giữ idempotency key **bao lâu**, và có bắt buộc payload phải giống không?
2. Key được áp dụng cho **lệnh thu tiền** hay chỉ một request/endpoint cụ thể?
3. Timeout có thể xảy ra **sau commit** của provider không? Có API query theo paymentId/reference không?
4. Key đã hết thời hạn lưu giữ thì một message cũ bị replay có thể tạo charge mới không?
5. Nếu provider không hỗ trợ idempotency, có quy trình đối soát/human review trước khi gọi lại không?

### Trạng thái kết quả chưa xác định

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> REQUESTED: Ghi lệnh + key
    REQUESTED --> CONFIRMED: Provider xác nhận thành công
    REQUESTED --> FAILED: Provider xác nhận thất bại chắc chắn
    REQUESTED --> UNKNOWN: Timeout / crash / mất response
    UNKNOWN --> RECONCILING: Tra cứu provider
    RECONCILING --> CONFIRMED: Đã charge
    RECONCILING --> FAILED: Chứng minh chưa charge
    RECONCILING --> REQUESTED: Có thể retry an toàn theo hợp đồng
~~~

Giữ **paymentId/idempotencyKey/provider reference/correlationId/attempt/status** trong một kho bền vững. **UNKNOWN_OUTCOME không đồng nghĩa FAILED**. Gửi charge lại ngay sau timeout khi chưa biết kết quả có thể gây double charge.

**Email cũng có khoảng hở tương tự:** SMTP đã chấp nhận email nhưng process crash trước khi mark sent; replay có thể gửi lần nữa. Nếu nền tảng email không hỗ trợ idempotency hoặc một cơ chế dedup phù hợp, phải chấp nhận khả năng duplicate và thiết kế trải nghiệm/tác dụng giảm thiểu hậu quả.

## 9. IdempotentReceiverInterceptor và MetadataStore trong Spring Integration

Spring Integration cung cấp **IdempotentReceiverInterceptor** để hỗ trợ mẫu **Idempotent Receiver** tại endpoint. Cơ chế này sử dụng **MessageSelector**; một cấu hình phổ biến là **MetadataStoreSelector** làm việc với **ConcurrentMetadataStore**.

~~~text
Inbound message
  → IdempotentReceiverInterceptor
      → MetadataStoreSelector(eventId)
          → accepted / duplicate
      → MessageHandler
~~~

Điểm quan trọng là phân biệt **lọc duplicate** với **đảm bảo side effect đã thực sự được commit**.

| Cơ chế | Có ích trong trường hợp nào? | Giới hạn |
| --- | --- | --- |
| **IdempotentReceiverInterceptor** | Chặn hoặc đánh dấu message bị nhận lại trước handler | Không tự làm side effect atomic với dấu xử lý |
| **MetadataStoreSelector** | Quy tắc tạo/check key và so sánh metadata | Chính sách ghi key cần phù hợp transaction |
| **ConcurrentMetadataStore** | Atomic put-if-absent/compare-and-set tùy implementation | Atomic trên key không đồng nghĩa atomic với HTTP/payment |
| **SimpleMetadataStore** | Demo, một JVM, ít yêu cầu durability | Mất dấu khi restart |
| **Persistent MetadataStore** | Bảo toàn state nhận diện qua restart | Có thể vẫn xảy ra crash window giữa ghi metadata và effect |

Theo hợp đồng của interceptor, nếu không cấu hình **discard channel** hoặc **throw-on-rejection**, một duplicate có thể được **đánh dấu header duplicateMessage=true** rồi vẫn chuyển đến handler; handler cần tự quyết định cách xử lý. Không mặc định rằng mọi duplicate đã được bỏ qua.

### Bẫy “claim trước” với persistent metadata

Giả sử selector ghi key vào store **trước khi handler xử lý**. Nếu key đã commit, rồi JVM chết trước side effect, replay có thể bị coi là duplicate và bỏ qua. Đây chính là **mất nghiệp vụ**; thay **SimpleMetadataStore** bằng **JdbcMetadataStore** không giải quyết được nếu checkpoint vẫn độc lập với effect.

Muốn xử lý an toàn:

- Nếu side effect nằm trong **cùng DB**, dùng transaction/unique constraint gắn **inbox và effect** như phần 6.
- Nếu side effect ở **hệ thống khác**, dùng state machine **REQUESTED/UNKNOWN/CONFIRMED**, idempotency provider và đối soát.
- Nếu metadata dùng để giữ **checkpoint của nguồn file/FTP**, đánh giá việc **flush**, durability và ý nghĩa “đã xem” so với “đã xử lý xong”.

**PropertiesPersistingMetadataStore** ví dụ là một loại lưu metadata xuống file; cách ghi thực tế liên quan cơ chế flush. Không suy đoán mọi lần put đều đã an toàn trước **hard crash** nếu không xác minh cấu hình.

## 10. MessageStore, channel và ranh giới thread/transaction

Spring Integration có **MessageStore** để giữ message cho các EIP như QueueChannel, aggregator, delayer. Store persistent giảm rủi ro mất **message đã lưu bền vững**, nhưng không biết một HTTP call ngoài DB đã có side effect hay chưa.

### Thread boundary có thể làm đổi thời điểm ack

~~~mermaid
flowchart TD
    B["Inbound adapter"] --> T["Nguồn / transaction A"]
    T --> E["ExecutorChannel"]
    E --> H["Handoff thành công"]
    H --> A["Nguồn có thể hoàn tất theo contract"]
    E -. "Worker thread khác" .-> W["Handler / transaction B"]
    W --> D[("Business DB")]
    W --> F["ErrorMessage nếu lỗi async"]
~~~

**Spring transaction thường gắn với thread.** Qua **ExecutorChannel** hoặc PollableChannel sang một consumer khác, transaction từ thread A không tự truyền sang thread B. Nếu producer được xem là thành công ngay sau handoff, crash trước khi worker commit có thể khiến nghiệp vụ chưa được hoàn thành; cách phục hồi phụ thuộc vào độ bền của hàng đợi và ack semantics.

| Thành phần | Câu hỏi cần kiểm tra khi crash/restart |
| --- | --- |
| **DirectChannel** | Handler có cùng thread/transaction với producer không? Exception có truyền ngược để rollback không? |
| **ExecutorChannel** | Task đã enqueue nhưng chưa chạy có được lưu bền vững không? Transaction/ack của producer kết thúc khi nào? |
| **QueueChannel + PollingConsumer** | Queue backing store có persistent không? Receive/remove có nằm trong transaction phù hợp không? |
| **JMS/AMQP/Kafka inbound** | Ack/nack/offset và redelivery được quyết định ở đâu, theo container và transaction nào? |
| **RequestHandlerRetryAdvice** | Một delivery có thể gọi handler nhiều lần không; có chồng lên retry client/broker không? |
| **MessageGroupStore** | Aggregator complete/release có sống qua restart và có thể phát output lặp không? |
| **errorChannel** | Lỗi async có tới error consumer không? Có giữ failedMessage/correlationId để xác định nghiệp vụ lỗi không? |

**Không thể kết luận một message sẽ được redeliver chỉ vì handler ném exception.** Nếu lỗi xảy ra sau async handoff, nguồn đã ack, hoặc recovery callback tiêu thụ exception, kết quả có thể khác. Luôn kiểm thử theo **adapter/version/config thực tế**.

### Persistent MessageStore không phải transaction toàn cục

Một store như **JdbcMessageStore, RedisMessageStore hoặc MongoDbMessageStore** có thể giữ message/group qua restart, với điều kiện durability và serializer tương thích. Nhưng:

- Không phải mọi **payload/header** đều serialize được. Header **replyChannel/errorChannel** chứa object nội bộ JVM có thể mất hoặc cần map thành tên channel.
- Một message đã được lấy khỏi queue/store có được phục hồi sau crash hay không phụ thuộc transaction và semantics của **receive/remove**.
- Một aggregator đã release có thể còn metadata, nhưng downstream side effect có thể chưa hoặc đã xảy ra; cần business idempotency.
- Khi nhiều instance dùng chung store, cần coordination/locking và xử lý duplicate; persistence không tự biến mọi output thành exactly-once.

Để chống mất nghiệp vụ, hãy xác định **nguồn sự thật** cho từng giai đoạn: broker/queue giữ delivery, DB giữ effect/inbox, outbox giữ event chưa publish, provider giữ trạng thái thanh toán.

## 11. Retry, correlation và error handling trong một lần crash

Mỗi retry có thể tạo message kỹ thuật mới hoặc tracing span mới:

~~~text
delivery #1: springMessageId=M1, eventId=EV-42, correlationId=checkout-O-42
    handler attempt #1: timeout
    handler attempt #2: timeout
JVM crash trước ACK
delivery #2: springMessageId=M2, eventId=EV-42, correlationId=checkout-O-42
~~~

Mọi attempt phải giữ:

- **eventId/operationId/idempotencyKey** như cũ, để chống side effect trùng.
- **correlationId** để liên kết sự kiện, kết quả, retry và lỗi của workflow.
- **attempt/delivery count** riêng cho quan sát, không làm dedup key.
- **source coordinates** như topic/partition/offset khi adapter cung cấp; không xem đó là danh tính nghiệp vụ đa nguồn.
- **failedMessage hoặc originalMessage** trong ErrorMessage khi có, để truy ra eventId từ message gốc.

### Không retry nóng mọi lỗi

| Loại lỗi | Ví dụ | Quyết định phù hợp |
| --- | --- | --- |
| Lỗi transient trước effect | DB connection tạm mất, HTTP 503 có hợp đồng idempotency | Retry có giới hạn + backoff |
| Payload hỏng | JSON sai, thiếu eventId | Quarantine/DLQ, không lặp vô hạn |
| Duplicate đã commit | Inbox key tồn tại và nội dung nhất quán | Bỏ qua hiệu ứng, xác nhận delivery theo hợp đồng |
| Unknown external outcome | Provider timeout sau khi có thể đã charge | Reconcile trước khi kết luận FAILED hoặc gọi lại |
| Lỗi outbox publish | Broker chưa xác nhận | Giữ pending, retry publish; downstream idempotent |
| Identity conflict | Cùng eventId nhưng payload khác | Alert/quarantine để điều tra |

Đừng cấu hình retry ở **HTTP client + handler + broker + scheduler** độc lập rồi vô tình tạo số lần gọi theo cấp số nhân. Một retry policy đầu-cuối cần có **retry owner**, max attempts, deadline, backoff, recovery và key idempotency ổn định.

### Error flow không tự quyết định ACK

ErrorMessage có thể mang MessagingException/failedMessage tùy nguồn lỗi. Nó chỉ phản ánh lỗi được phát tới error channel. Việc **error handler log rồi return bình thường** có thể khiến xử lý được coi như thành công ở một số topology. Muốn redelivery, cần tuân thủ cơ chế adapter; muốn quarantine, cần ghi **FailureJournal/DLQ bền vững** trước khi xác nhận đã giải quyết.

## 12. Kiểm thử crash window: phải kill đúng thời điểm

Một bài test chỉ gọi handler hai lần trong cùng process **không kiểm chứng được lỗi sau crash**. Cần fault injection khi business DB đã commit nhưng nguồn chưa ack, rồi restart consumer với **cùng kho dữ liệu**.

### Ma trận kiểm thử

| Ca | Điểm tạo crash/lỗi | Kỳ vọng |
| --- | --- | --- |
| A | Trước side effect | Replay thực hiện được; không mất nghiệp vụ |
| B | Sau INSERT inbox nhưng trước DB commit | Rollback cả inbox và DB work; replay thành công |
| C | Sau UPDATE projection nhưng trước commit | Không có dữ liệu đã commit một nửa |
| D | **Sau DB commit, trước broker ack** | Broker có thể redeliver; inbox chặn effect lần hai |
| E | Sau publish outbox, trước mark published | Publisher có thể publish lặp; downstream không làm side effect trùng |
| F | Sau provider charge, trước lưu CONFIRMED | Retry/reconciliation dùng cùng paymentId; không thu tiền hai lần |
| G | Sau ghi metadata độc lập, trước side effect | Không được coi nhầm nghiệp vụ là DONE |
| H | Hai consumer cùng eventId | Unique constraint/atomic claim chặn hai commit có hiệu lực |
| I | Persistent QueueChannel có message chờ, rồi restart | Đọc được message theo hợp đồng store |
| J | Aggregator đủ điều kiện release, crash trước/đang output | State group và downstream idempotency được kiểm tra |
| K | ExecutorChannel handoff rồi worker lỗi | Error flow/transaction/ack thực tế được xác minh |
| L | Hết thời gian giữ idempotency key, replay event cũ | Có chính sách ngăn hoặc đối soát late replay |

### Quy trình integration test có restart thực

1. Tạo **broker/test queue** và **PostgreSQL** giữ dữ liệu khi worker bị kill.
2. Gửi **eventId=EV-42** và cấu hình consumer để có điểm có thể quan sát sau commit nhưng trước ack theo adapter.
3. Tại checkpoint đó, **kill process/container**, không dùng graceful shutdown (graceful shutdown có thể xử lý xong in-flight message).
4. Khởi động worker mới, dùng lại **cùng broker và DB**.
5. Kiểm tra nguồn có thể redeliver, nhưng **processed_message** vẫn chỉ có một key và **outbox/projection** chỉ có một logical effect.
6. Tiếp tục fault injection ở bước publish outbox và API payment; quan sát recovery và idempotency.

**Giới hạn kiểm thử:** Việc chèn checkpoint thật sự **giữa commit và ack** phụ thuộc adapter. Nếu chỉ đặt Thread.sleep() trong handler rồi restart ứng dụng, bạn có thể chưa chạm đúng crash window. Dùng test seam/fault hook hoặc một consumer process được kiểm soát và ghi rõ điều gì đã chứng minh.

### Assertion vào kết quả, không chỉ số lần handler chạy

~~~text
processed_message:
    1 row cho (order-projection-v1, EV-42)
order_projection:
    đúng trạng thái nghiệp vụ mong muốn
outbox_message:
    1 logical outbox_id cho EV-42
broker:
    có thể giao EV-42 nhiều lần theo at-least-once contract
provider:
    một payment theo paymentId nếu provider có idempotency
logs/traces:
    cùng eventId/correlationId xuyên restart
~~~

Không dùng assertion “handler được gọi đúng một lần” làm thước đo duy nhất: **handler có thể chạy hai lần nhưng effect vẫn phải đúng một lần**.

## 13. Ví dụ test duplicate delivery với hai Spring Message khác ID

Đoạn dưới minh họa logic test với handler transactional ở phần 6. Nó cần chạy trong Spring test context có **JdbcTemplate/transaction manager và PostgreSQL thật**, vì test chỉ dùng mock repository không thể chứng minh durability của transaction.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class InboxReplayTest {
    @Autowired OrderProjectionHandler handler;
    @Autowired JdbcTemplate jdbc;

    @Test
    void redeliveryDoesNotApplyProjectionTwice() {
        OrderConfirmed event = new OrderConfirmed("EV-42", "O-42");

        Message<OrderConfirmed> delivery1 =
                MessageBuilder.withPayload(event).build();
        Message<OrderConfirmed> delivery2 =
                MessageBuilder.withPayload(event).build();

        handler.handle(delivery1);
        handler.handle(delivery2);

        Integer inboxCount = jdbc.queryForObject("""
                SELECT count(*) FROM processed_message
                 WHERE consumer_name='order-projection-v1'
                   AND event_id='EV-42'
                """, Integer.class);

        Integer outboxCount = jdbc.queryForObject("""
                SELECT count(*) FROM outbox_message
                 WHERE outbox_id='order-confirmed:EV-42'
                """, Integer.class);

        assertEquals(1, inboxCount);
        assertEquals(1, outboxCount);
    }
}
~~~

**Fragment test, chưa chạy độc lập:** Cần @SpringBootTest/@SpringJUnitConfig, fixture schema, transaction proxy và cleanup giữa các test. Nếu test method chạy trong một transaction của test framework bị rollback ở cuối, nó không chứng minh state đã commit qua restart. Với crash test, commit thật và dùng process khác.

### Kiểm thử hai consumer đồng thời

Hai thread/replica cùng nhận eventId=EV-42:

- Cả hai có thể chạy tới INSERT processed_message gần như đồng thời.
- **PRIMARY KEY (consumer_name, event_id)** chặn hai row đã commit với cùng key.
- Một transaction có thể chờ transaction kia quyết định commit/rollback. Nếu giao dịch đầu rollback, giao dịch sau cần xử lý lại được.
- Khi cả hai kết thúc, chỉ có **một logical projection update và một outbox event** theo key.
- Nếu chúng cùng update một order từ **hai eventId khác nhau**, đây là bài toán ordering/version riêng, không được giải bằng dedup eventId.

Một test ConcurrentHashMap trong một JVM không chứng minh hành vi trên hai replica dùng chung DB.

## 14. Persistence và restart: nhiều nguồn sự thật phải khớp nhau

~~~mermaid
flowchart LR
    Q[("Broker / ChannelMessageStore<br/>delivery state")] --> H["Consumer"]
    H --> I[("Business DB / Inbox<br/>applied state")]
    I --> O[("Outbox / FailureJournal<br/>publication state")]
    O --> E["External broker / API"]
~~~

Các lớp có thể **tạm thời không đồng ý** sau crash:

- Broker biết message chưa ack nên muốn phát lại.
- Business DB biết hiệu ứng đã commit.
- Outbox biết event chưa publish hoặc chưa đánh dấu published.
- Provider biết payment đã thành công nhưng DB nội bộ vẫn ghi UNKNOWN.

Quy trình phục hồi tốt thường là:

1. Broker redeliver message chưa xác nhận.
2. Consumer đối chiếu **inbox** và áp dụng nghiệp vụ nếu chưa commit.
3. Outbox publisher quét **pending** và phát lại có kiểm soát.
4. Reconciliation worker tra cứu **UNKNOWN_OUTCOME** ở provider.
5. Monitoring phát hiện pending quá lâu, identity conflicts và side effect không đối soát được.

### Cẩn trọng khi giữ message trong persistent store

Spring Integration hỗ trợ JDBC, Redis, MongoDB message store tùy component. Với persistent MessageStore:

- Xem payload và header **có serialize/deserial​ize được sau upgrade** hay không.
- Header như replyChannel/errorChannel dạng object có thể chỉ có ý nghĩa trong JVM cũ; cân nhắc **channel name** và mapping.
- Kiểm tra trạng thái group aggregator, release/expire, timer sau restart và policy message đến muộn.
- Hai instance dùng chung store vẫn cần locking/concurrency control và business idempotency.
- Message đã bị consumer lấy khỏi store rồi crash có được phục hồi không phụ thuộc **transaction và receive/remove semantics**.

**Persistent state không tự tạo exactly-once.** Nó chỉ giữ một phần sự thật đã commit; vẫn phải xác định lúc nào dấu được ghi và nó có atomic với effect hay không.

## 15. Quan sát và chẩn đoán duplicate do crash

Một hệ thống at-least-once có thể thấy duplicate delivery bình thường. Điều phải cảnh báo là **duplicate business effect**, không phải mọi lần replay.

| Chỉ số / sự kiện | Câu hỏi vận hành |
| --- | --- |
| **delivery attempts** | Broker/poller giao lại message nhiều tới đâu? |
| **handler retry attempts** | RetryAdvice hoặc client retry có đang khuếch đại số call? |
| **inbox duplicate count** | Bao nhiêu message được chặn an toàn nhờ key bền vững? |
| **business duplicate effect count** | Có thực sự update/charge/sent trùng không? |
| **outbox pending age** | Event đã commit nhưng chưa publish đã chờ bao lâu? |
| **unknown payment count** | Bao nhiêu side effect cần đối soát? |
| **correlation missing count** | Bao nhiêu lỗi không lần về được eventId/operationId? |
| **queue depth / consumer lag** | Backlog tăng vì crash, retry storm hay downstream quá tải? |
| **identity conflict count** | Cùng eventId nhưng nội dung khác? |

Ví dụ log do ứng dụng tự định nghĩa:

~~~text
flow=orderPersistence endpoint=orderProjectionHandler
eventId=EV-42 orderId=O-42 correlationId=checkout-O-42
deliveryAttempt=2 handlerAttempt=1
inboxResult=DUPLICATE businessEffect=SKIPPED
source=kafka partition=3 offset=10852
decision=ACK_AFTER_VERIFIED_COMMIT
~~~

**Không lưu thông tin thanh toán nhạy cảm** hoặc raw payload bí mật trong log. Giữ **eventId, paymentId** trong trace/log có kiểm soát; tránh dùng mỗi ID riêng biệt làm tag cardinality cao trong hệ metrics.

### Checklist khi phát hiện side effect hai lần

1. Có hai eventId khác nhau, hay một eventId được giao lại?
2. Side effect đã commit trước khi ack ở đâu?
3. Key idempotency có thay sau restart, transformer hoặc retry không?
4. Dấu DONE được commit **trước, sau hay cùng transaction** với business effect?
5. Provider có thật sự thực thi idempotency key và nó còn hiệu lực không?
6. Có retry lồng ở HTTP client, handler, broker hoặc scheduled replay không?
7. ExecutorChannel có làm nguồn xác nhận handoff khi worker chưa xử lý xong không?
8. Outbox publisher có phát lại sau crash và consumer downstream có dedup không?
9. Store/metadata có bị reset khi deploy, thay namespace hoặc schema không?
10. UNKNOWN_OUTCOME có bị coi nhầm thành FAILED và tự động charge lại không?

## 16. Bài thực hành tổng hợp

**Đề bài:** Một flow nhận OrderConfirmed từ broker, cập nhật PostgreSQL, phát OrderReady và gọi payment provider. Ứng dụng có hai replica. Broker giao theo at-least-once; container đôi khi chết ngay sau DB commit hoặc payment charge.

**Yêu cầu:** Không tạo hai projection/outbox event cho cùng eventId; không charge hai lần cho cùng paymentId nếu provider có hỗ trợ idempotency; outbox phải phục hồi sau crash; trạng thái UNKNOWN phải được đối soát; correlation vẫn truy vết được sau restart.

Hướng thiết kế:

1. **Inbound:** Xác thực eventId, correlationId, orderId, paymentId và giữ chúng qua mọi transformer/retry.
2. **Business DB:** Ghi inbox theo consumer+eventId, cập nhật đơn và ghi outbox trong **cùng transaction**; dùng unique constraint.
3. **Outbox publisher:** Poll pending, claim an toàn, publish với eventId cố định, đánh dấu sau xác nhận; consumer downstream idempotent.
4. **Payment:** Dùng paymentId/idempotency key, trạng thái REQUESTED/UNKNOWN/CONFIRMED, có tra cứu provider sau timeout.
5. **Error flow:** Không nuốt exception rồi ack giả; lưu FailureJournal/DLQ khi không thể xử lý, với business correlation.
6. **Restart:** DB, outbox và trạng thái provider là nguồn sự thật; không dựa vào RAM hoặc riêng callback afterCommit.
7. **Concurrency:** Test hai replica cùng eventId và tình huống crash sau commit trước ack.
8. **Quan sát:** Ghi eventId, operationId, delivery/attempt, điểm commit, ack, outbox publish và reconciliation status.

### Câu hỏi tự kiểm tra

**1.** DB commit thành công, app chết trước broker ack; broker redeliver. Đó có phải bug của broker?

**Không.** Đây là kết quả hợp lệ của at-least-once khi ack chưa hoàn tất. Inbox/idempotency phải chặn effect trùng.

**2.** Dùng persistent MetadataStore để ghi DONE trước HTTP call đã đủ an toàn?

**Không.** Crash sau dấu DONE nhưng trước effect sẽ làm message replay bị bỏ qua; side effect không bao giờ xảy ra.

**3.** @Transactional bao quanh DB và HTTP payment có rollback được payment nếu DB rollback?

**Không với HTTP thông thường.** Cần provider idempotency, query trạng thái và reconciliation.

**4.** Outbox event đã publish nhưng app chết trước khi mark published; có nên xóa outbox để tránh duplicate?

**Không.** Làm vậy có thể mất event trong những tình huống chưa publish thực sự. Chấp nhận publish lặp, dùng downstream dedup.

**5.** Có thể dùng correlationId làm dedup key cho mọi event của cùng order không?

**Không mặc định.** Một workflow/order có nhiều thao tác hợp lệ; dedup cần định danh **một event hoặc một business operation cụ thể**.

## 17. Checklist production

- Đã liệt kê crash windows từ **receive → effect → commit → ack → restart**?
- Đã tách **delivery count**, **handler attempt** và **business effect**?
- Dedup key ổn định qua redelivery, có namespace consumer/operation?
- **Inbox + DB effect + outbox** có commit/rollback trong **cùng transaction thật**?
- Có unique constraint/atomic claim bảo vệ nhiều consumer đồng thời?
- Có tránh ack source quá sớm và tránh nuốt exception thành success?
- Outbox có phục hồi publish sau crash, và downstream có idempotency?
- External API/payment có key được phía đích hỗ trợ và quy trình **UNKNOWN_OUTCOME reconciliation**?
- Đã xác định transaction/ack theo adapter và ranh giới **ExecutorChannel / QueueChannel**?
- MetadataStore/MessageStore có bền vững qua restart, serializer/headers tương thích?
- Có retention dedup đủ dài so với broker redelivery và delayed replay?
- Retry có giới hạn, không lồng nhiều tầng vô thức, có recovery/DLQ rõ ràng?
- Có giữ failed/original message, eventId, correlationId và idempotencyKey trong error path?
- Đã kiểm thử **hard crash sau DB commit trước ack**, sau payment effect và sau outbox publish?
- Có đo **duplicate delivery an toàn** tách biệt với **duplicate business effect**?

## Kết luận

**Duplicate message do crash sau khi side effect** là một trong những rủi ro cốt lõi khi message flow phải phối hợp nhiều tài nguyên với các thời điểm commit/ack khác nhau. Spring Integration điều phối channel, endpoint, poller, executor, retry, error flow và persistence, nhưng **không tự bảo đảm một HTTP/DB/broker side effect chỉ xảy ra một lần**.

Chiến lược bền vững là **chấp nhận redelivery nhưng chống lặp ở ranh giới nghiệp vụ**: transactional inbox cho DB, transactional outbox cho event phải publish, idempotency key và đối soát cho external side effect. Cùng với **persistent state, correlation, retry hữu hạn và test hard crash tại đúng khoảng hở**, hệ thống có thể khôi phục sau restart mà không lặp hoặc bỏ sót kết quả nghiệp vụ.

## Tài liệu tham khảo

- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html)
- [Spring Integration Reference — Idempotent Receiver Enterprise Integration Pattern](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html)
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
