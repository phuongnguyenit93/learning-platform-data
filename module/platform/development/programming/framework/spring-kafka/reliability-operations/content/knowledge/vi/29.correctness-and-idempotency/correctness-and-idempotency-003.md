# Idempotency key trong Spring Kafka

Kafka consumer thường phải chấp nhận khả năng một record được giao nhiều lần. Consumer có thể đã ghi dữ liệu vào database nhưng process crash trước khi commit offset; rebalance có thể khiến partition được giao cho consumer khác; producer hoặc error handler có thể retry; operator có thể replay một record từ DLT. Trong những tình huống đó, cùng một **logical operation** có thể đi qua listener nhiều lần.

Nếu mỗi lần delivery đều tạo một side effect mới, hệ thống có thể ghi trùng đơn hàng, trừ tiền nhiều lần, gửi nhiều email hoặc phát sinh các bản ghi nghiệp vụ lặp. **Idempotency key** giúp nhận diện những lần thực thi đại diện cho cùng một operation để hệ thống chỉ áp dụng side effect một lần theo contract đã chọn.

Trong module **Spring Kafka Reliability Operations**, idempotency key là một phần quan trọng của tính đúng và idempotency. Cần hiểu rằng Kafka record key, event ID và idempotency key có thể liên quan nhưng không đồng nghĩa. Một thiết kế đáng tin phải xác định rõ phạm vi key, tạo key ổn định, lưu dấu xử lý một cách atomic với business side effect, xử lý duplicate đồng thời, giữ deduplication state đủ lâu và có quy tắc rõ cho retry, DLT và replay.

Bài học này trình bày cách thiết kế key, triển khai inbox/deduplication table với database transaction, bảo vệ external API calls, xử lý race conditions, chọn retention, quan sát duplicate và kiểm thử các crash boundaries.

## 1. Idempotency là gì?

Một operation được gọi là **idempotent** nếu thực hiện nhiều lần với cùng một input và cùng một identity không làm thay đổi kết quả nghiệp vụ sau lần đầu.

Ví dụ, lệnh đặt trạng thái đơn hàng thành SHIPPED có thể được thiết kế idempotent:

~~~text
setOrderStatus(order-100, SHIPPED)

Lần 1: CREATED -> SHIPPED
Lần 2: SHIPPED -> SHIPPED
Lần 3: SHIPPED -> SHIPPED
~~~

Ngược lại, một operation tăng số dư:

~~~text
balance = balance + 100
~~~

không idempotent nếu chạy nhiều lần. Nếu cùng một message được xử lý ba lần, số dư có thể tăng 300.

Idempotency key cung cấp một identity ổn định cho operation. Ứng dụng lưu key đã xử lý và kiểm tra trước khi áp dụng side effect:

~~~text
Receive message
      |
      v
Extract idempotency key
      |
      v
Key already completed?
   /       \
 yes       no
  |         |
  v         v
Skip     Apply side effect
duplicate    |
             v
        Persist key + result
~~~

Sơ đồ là mô hình khái niệm. Trong production, bước kiểm tra và ghi key phải được thực hiện atomic để hai consumer đồng thời không cùng vượt qua kiểm tra.

## 2. Vì sao Kafka consumer cần idempotency key?

Kafka consumer thường được triển khai theo at-least-once delivery semantics: một record chưa được commit có thể được giao lại. Điều này là bình thường và giúp tránh mất dữ liệu.

Một tình huống điển hình:

~~~text
1. Consumer nhận record E.
2. Listener ghi order vào database.
3. Database commit thành công.
4. Process crash trước khi Kafka offset commit.
5. Consumer mới nhận lại E.
6. Listener ghi order lần nữa.
~~~

Kafka không biết database đã commit side effect ở bước 3. Offset commit và database transaction là hai hệ thống khác nhau nếu không có một cơ chế phối hợp phù hợp.

Idempotency key cho phép consumer nhận ra lần giao lại ở bước 5 là cùng một operation với lần đã hoàn tất. Khi đó listener có thể trả về thành công mà không thực hiện side effect lần nữa.

Các nguyên nhân redelivery thường gặp:

- Process crash sau database commit nhưng trước offset commit.
- Consumer rebalance khi listener chưa commit.
- Offset commit thất bại hoặc timeout khiến kết quả chưa rõ.
- Error handler retry record.
- Retry topic chuyển cùng logical event qua một consumer khác.
- DLT replay sau khi sửa dữ liệu hoặc code.
- Operator chạy lại một batch hoặc import.
- Producer gửi lại cùng command sau timeout.

**Duplicate delivery không nhất thiết là lỗi của Kafka.** Consumer phải được thiết kế để chịu được điều đó.

## 3. Idempotency key, Kafka key và event ID khác nhau

Ba loại identity thường bị nhầm:

| Identity | Mục đích chính | Ví dụ |
|---|---|---|
| Kafka record key | Partitioning và ordering theo key | order-100 |
| Event ID | Định danh một event cụ thể trong business contract | evt-7f3a |
| Idempotency key | Định danh một operation cần chống thực hiện lặp | order-create:cmd-91 |
| Trace ID | Liên kết spans trong một distributed trace | trace-abc |
| Topic/partition/offset | Định vị một record trong Kafka log | orders.events/2/105 |

Kafka key thường được dùng để chọn partition. Nhiều events khác nhau của cùng một order có thể có cùng Kafka key order-100:

~~~text
Kafka key = order-100

Event A: OrderCreated
Event B: OrderAddressChanged
Event C: OrderShipped
~~~

Nếu dùng Kafka key làm idempotency key, event B và C có thể bị coi là duplicate của event A. Đó là sai vì chúng là các operation khác nhau.

Event ID thường phù hợp làm idempotency key khi mỗi event đại diện cho đúng một operation cần áp dụng một lần. Nhưng không phải mọi hệ thống đều có event ID đúng contract; đôi khi cần một key theo command hoặc business operation.

Trace ID cũng không phù hợp: một event có thể được xử lý trong trace mới khi retry/replay, và một trace có thể chứa nhiều events.

## 4. Chọn phạm vi của idempotency key

Trước khi tạo key, cần trả lời: **một operation được xem là trùng trong phạm vi nào?**

Một số phạm vi thường gặp:

- Theo consumer/service: mỗi consumer chỉ áp dụng side effect của mình một lần.
- Theo loại operation: tạo đơn hàng và gửi hóa đơn có identity khác nhau.
- Theo tenant: cùng command ID ở hai tenant khác nhau có thể là hai operation riêng.
- Theo aggregate: một order có thể có nhiều commands khác nhau.
- Theo hệ thống downstream: mỗi external API có thể có idempotency contract riêng.

Ví dụ key có namespace:

~~~text
tenant-42:order-create:cmd-91
tenant-42:reserve-inventory:cmd-91
tenant-42:charge-payment:cmd-91
~~~

Cùng command ID nhưng ba side effects khác nhau. Nếu dùng một key chung mà không có operation namespace, lần xử lý thứ hai có thể bị skip nhầm.

Thiết kế schema thường có một hoặc nhiều thành phần:

- consumer_name hoặc operation_name.
- tenant_id nếu business identity cần phân tách theo tenant.
- idempotency_key.
- payload_hash hoặc request fingerprint.
- trạng thái và kết quả operation.
- processed_at/created_at.

Không mặc định namespace phải là Kafka consumer group. Nếu hai consumer groups cùng chịu trách nhiệm cho cùng một side effect và cần chống duplicate toàn hệ thống, key scope phải được chia sẻ theo business operation. Ngược lại, nếu hai groups thực hiện hai side effects khác nhau, chúng cần namespace riêng.

## 5. Tạo key ổn định qua mọi lần delivery

Một idempotency key phải được tạo **một lần cho logical operation** và giữ nguyên khi producer retry, consumer redeliver, record đi qua retry topic hoặc được replay từ DLT.

Các nguồn key có thể dùng:

1. Event ID do producer tạo khi event được tạo.
2. Command ID do API/client cung cấp và được lưu cùng command.
3. Operation ID được tạo tại service khởi tạo workflow.
4. Business natural key kết hợp operation type và version nếu contract đảm bảo uniqueness.
5. Source Kafka coordinates nếu chỉ cần deduplicate đúng một record nguồn trong phạm vi một topic log.

Ví dụ event:

~~~json
{
  "eventId": "evt-7f3a",
  "eventType": "OrderCreated",
  "tenantId": "tenant-42",
  "orderId": "order-100",
  "occurredAt": "2026-11-15T10:00:00Z"
}
~~~

Nếu eventId được tạo khi producer tạo event và không đổi qua retry, có thể dùng:

~~~text
consumer = order-projection
idempotency_key = evt-7f3a
~~~

Không tạo UUID mới mỗi lần listener chạy. Nếu tạo key bên trong consumer cho mỗi delivery, hai lần giao lại sẽ có hai keys khác nhau và deduplication không hoạt động.

## 6. Không dùng business entity ID đơn lẻ nếu entity có nhiều events

Giả sử một order có nhiều thay đổi:

~~~text
order-100:
  OrderCreated
  AddressChanged
  PaymentAuthorized
  OrderShipped
~~~

Nếu key chỉ là order-100, event đầu tiên có thể khiến ba event sau bị coi là duplicate.

Có thể dùng:

~~~text
order-100:created:version-1
order-100:address-changed:version-2
order-100:payment-authorized:version-3
order-100:shipped:version-4
~~~

Tuy nhiên, một event ID riêng thường rõ ràng hơn nếu producer có thể tạo nó. Entity ID phù hợp với idempotent state-setting operation khi semantics thực sự là “đặt trạng thái hiện tại thành X”, nhưng không phù hợp với mọi command tăng/giảm hoặc append-only event.

**Key phải nhận diện operation, không chỉ nhận diện object mà operation tác động lên.**

## 7. Dùng source topic/partition/offset làm key khi nào?

Nếu record không có event ID, tọa độ Kafka có thể tạo một identity cho record nguồn:

~~~text
orders.events:2:105
~~~

Key này nhận diện một record trong một topic partition log. Nó có thể phù hợp khi mục tiêu là chống xử lý lại cùng source record trong consumer.

Nhưng có giới hạn:

- Khi record được copy sang retry topic, tọa độ destination thay đổi.
- Khi record được publish sang DLT rồi replay, tọa độ mới không giống source.
- Khi topic được migrate hoặc dữ liệu được republish, cùng logical event có thể có tọa độ khác.
- Nếu hai clusters có cùng topic/partition/offset, key có thể collision nếu thiếu cluster/namespace.
- Nếu operation được phát lại có chủ đích, key theo source coordinates có thể không nhận diện cùng business operation.

Nếu cần chống duplicate xuyên retry/DLT/replay, event ID hoặc operation ID bền vững thường phù hợp hơn. Nếu dùng Kafka coordinates, hãy giữ original coordinates trong DLT metadata và namespace key theo cluster/topic.

## 8. Key cần có payload fingerprint để phát hiện reuse sai

Một lỗi khó phát hiện là cùng idempotency key nhưng payload khác nhau:

~~~text
Request 1:
  key = payment-100
  amount = 50.00

Request 2:
  key = payment-100
  amount = 500.00
~~~

Nếu hệ thống chỉ thấy key đã tồn tại và silently skip request 2, có thể che giấu một client bug hoặc key collision nghiêm trọng.

Có thể lưu payload hash/canonical request fingerprint cùng key:

| Key | Payload hash | Hành vi |
|---|---|---|
| payment-100 | hash-A | Lần đầu, xử lý |
| payment-100 | hash-A | Duplicate hợp lệ, trả kết quả cũ |
| payment-100 | hash-B | Key reuse conflict, cảnh báo/lỗi |

Hash phải được tính từ một representation có canonicalization ổn định. Không hash JSON serialization tùy ý nếu field ordering, whitespace hoặc default values có thể thay đổi nhưng semantics giống nhau.

Một canonical request có thể gồm operation type, tenant, amount, currency và business fields đã chuẩn hóa. Cần tránh đưa secrets hoặc PII thô vào hash material nếu không cần.

Nếu cùng key nhưng payload khác, đừng coi là duplicate bình thường. Hãy trả một conflict có thể điều tra.

## 9. Lưu idempotency state trong database

Với side effect nằm trong relational database, cách phổ biến là lưu processed key trong một bảng inbox/deduplication.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_messages (
    consumer_name   VARCHAR(120) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    payload_hash    BYTEA NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, idempotency_key)
);
~~~

Primary key đảm bảo một consumer namespace không lưu hai lần cùng key. Nếu multi-tenant namespace đã được mã hóa trong key, có thể dùng key đó; hoặc thiết kế tenant_id thành cột riêng và đưa vào unique constraint.

Một schema có tenant riêng:

~~~sql
CREATE TABLE processed_operations (
    consumer_name   VARCHAR(120) NOT NULL,
    tenant_id       VARCHAR(120) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    payload_hash    BYTEA NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        consumer_name,
        tenant_id,
        idempotency_key
    )
);
~~~

Bảng này là một inbox/deduplication ledger. Nó phải được lưu bền vững qua process restart. Một HashSet trong memory không đủ cho nhiều pods hoặc consumer rebalance vì mỗi instance có state riêng và state sẽ mất khi restart.

## 10. Ghi idempotency marker và business side effect trong cùng transaction

Đây là nguyên tắc quan trọng nhất:

**Insert idempotency marker và thực hiện business mutation phải nằm trong cùng một database transaction.**

Nếu marker commit trước side effect:

~~~text
Insert processed key
Commit
Process crashes
Business update chưa xảy ra
Redelivery thấy key đã có
Skip
=> Mất business operation
~~~

Nếu side effect commit trước marker:

~~~text
Business update
Commit
Process crashes
Marker chưa được ghi
Redelivery
Business update chạy lại
=> Duplicate side effect
~~~

Cách đúng:

~~~text
BEGIN TRANSACTION
    |
    v
Insert idempotency key
    |
    +--> Key đã tồn tại?
    |        |
    |        +--> Đọc fingerprint/kết quả
    |        +--> Commit/return duplicate
    |
    +--> Key mới
             |
             v
       Apply business mutation
             |
             v
       Persist result/state
             |
             v
       COMMIT
~~~

Nếu transaction rollback, marker và business mutation cùng rollback. Nếu transaction commit, cả hai cùng tồn tại. Khi record được giao lại, database nhận diện key đã hoàn tất.

Đây là cách bảo vệ side effect **nằm trong cùng database transaction**. Nó không tự bao phủ HTTP request, email hoặc một database khác.

## 11. Ví dụ SQL atomic với PostgreSQL

Có thể dùng INSERT ... ON CONFLICT DO NOTHING để giành quyền xử lý key:

~~~sql
INSERT INTO processed_messages (
    consumer_name,
    idempotency_key,
    payload_hash
)
VALUES (
    :consumerName,
    :idempotencyKey,
    :payloadHash
)
ON CONFLICT (consumer_name, idempotency_key)
DO NOTHING
RETURNING idempotency_key;
~~~

Diễn giải:

- Nếu trả về một row, transaction đã insert marker và có quyền tiếp tục business operation.
- Nếu không trả row, key đã được insert/commit bởi một transaction khác hoặc đã tồn tại trước đó.
- Unique constraint khiến hai consumer đồng thời không thể cùng insert thành công cùng key.
- Nếu transaction cạnh tranh chưa commit, database sẽ xử lý xung đột theo isolation/locking semantics; lệnh có thể phải chờ transaction kia.

Khi insert không thành công vì duplicate, đọc payload_hash đã lưu và so sánh với hash hiện tại. Nếu khác, báo key reuse conflict.

Tất cả thao tác phải nằm trong cùng transaction. Đừng chạy INSERT ở một datasource transaction rồi business mutation ở datasource khác và giả định chúng atomic.

## 12. Triển khai service với Spring @Transactional

Ví dụ dưới đây dùng JdbcTemplate và một repository có câu SQL atomic:

~~~java
@Service
public class IdempotentOrderProcessor {

    private final JdbcTemplate jdbcTemplate;
    private final OrderRepository orderRepository;

    public IdempotentOrderProcessor(
            JdbcTemplate jdbcTemplate,
            OrderRepository orderRepository) {
        this.jdbcTemplate = jdbcTemplate;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public ProcessingResult process(OrderCreated event) {

        String consumerName = "order-projection";
        String key = event.eventId();
        byte[] payloadHash = hashCanonicalEvent(event);

        int inserted = jdbcTemplate.update("""
                INSERT INTO processed_messages (
                    consumer_name,
                    idempotency_key,
                    payload_hash
                )
                VALUES (?, ?, ?)
                ON CONFLICT (consumer_name, idempotency_key)
                DO NOTHING
                """,
                consumerName,
                key,
                payloadHash
        );

        if (inserted == 0) {
            byte[] previousHash = jdbcTemplate.queryForObject(
                    """
                    SELECT payload_hash
                    FROM processed_messages
                    WHERE consumer_name = ?
                      AND idempotency_key = ?
                    """,
                    byte[].class,
                    consumerName,
                    key
            );

            if (!MessageDigest.isEqual(
                    previousHash,
                    payloadHash)) {
                throw new IdempotencyKeyConflictException(key);
            }

            return ProcessingResult.DUPLICATE;
        }

        orderRepository.createProjection(event);

        return ProcessingResult.APPLIED;
    }
}
~~~

Đây là ví dụ PostgreSQL/JDBC; cần bổ sung helper hashCanonicalEvent, ProcessingResult, exception và repository theo domain. SQL text blocks yêu cầu Java hỗ trợ text block. Nếu dùng database khác, cú pháp upsert có thể khác.

Vì method có @Transactional, marker insert và createProjection tham gia cùng transaction nếu cùng transaction manager/data source. Nếu createProjection ném exception, marker cũng rollback.

Không bắt exception rồi trả success bên trong transaction nếu muốn rollback. Spring transaction rollback mặc định theo runtime exceptions; checked exceptions cần rollbackFor hoặc cách cấu hình phù hợp.

## 13. Vì sao cần unique constraint thay vì SELECT rồi INSERT?

Một cách dễ viết nhưng không an toàn:

~~~java
if (!repository.existsByIdempotencyKey(key)) {
    repository.insert(key);
    orderRepository.create(event);
}
~~~

Hai consumers có thể cùng chạy:

~~~text
Consumer A                  Consumer B
----------                  ----------
SELECT key -> absent        SELECT key -> absent
INSERT key                  INSERT key
CREATE order                CREATE order
~~~

Cả hai cùng thấy absent trước khi một bên insert. Nếu không có unique constraint, có thể tạo duplicate side effect.

Ngay cả khi có unique constraint, chỉ SELECT trước rồi mới thực hiện side effect vẫn không đủ. Hãy **dùng unique constraint làm concurrency arbiter**, insert marker trước trong transaction rồi chỉ side effect nếu insert thành công.

Một distributed lock hoặc in-memory synchronized block không thay thế unique constraint vì các consumer có thể chạy trên nhiều JVM/pods.

## 14. Xử lý duplicate đồng thời và transaction isolation

Với hai consumers cùng nhận cùng key, database phải quyết định transaction nào sở hữu operation.

~~~text
Transaction A                       Transaction B
-------------                       -------------
INSERT key=evt-100                  INSERT key=evt-100
unique slot acquired                waits/conflicts
apply business mutation             |
COMMIT                              |
                                    INSERT returns duplicate
                                    read stored hash/result
                                    skip side effect
~~~

Trong PostgreSQL với unique constraint và ON CONFLICT, transaction cạnh tranh thường phải chờ kết quả của transaction giữ unique key. Nếu transaction A rollback, B có thể insert thành công và trở thành owner. Nếu A commit, B đi vào nhánh duplicate.

Không chỉ dùng một cache kiểm tra key trước DB rồi mới xử lý. Cache có thể giúp giảm reads, nhưng database unique constraint vẫn là nơi quyết định cuối cùng.

Khi sử dụng nhiều database engines, hãy xác nhận semantics của upsert, isolation level và locking. Không dựa vào giả định concurrency của PostgreSQL cho mọi hệ quản trị.

## 15. Cùng key nhưng payload hash khác phải là conflict

Một key reuse conflict có thể chỉ ra:

- Producer tạo event ID sai hoặc tái sử dụng ID.
- API client gửi cùng idempotency key cho hai request khác nhau.
- Một event bị mutate khi retry.
- Canonicalization không ổn định.
- Tenant namespace bị thiếu.
- Version/schema khác nhau nhưng key không có operation version.
- Bug trong replay tool.

Ví dụ exception:

~~~java
public class IdempotencyKeyConflictException
        extends RuntimeException {

    public IdempotencyKeyConflictException(String key) {
        super("Idempotency key reused with different payload");
    }
}
~~~

Không đưa raw key hoặc payload vào exception message nếu chúng có thể chứa thông tin nhạy cảm. Có thể ghi một fingerprint đã giới hạn và key hash trong structured logs.

Key conflict không nên bị xử lý như duplicate thành công. Tùy nghiệp vụ, có thể phân loại non-retryable, quarantine vào DLT hoặc phát alert cho producer contract violation.

## 16. Idempotency với Spring Kafka listener

Listener nên chuyển việc xử lý vào một Spring service có transaction rõ ràng:

~~~java
@Component
public class OrderListener {

    private final IdempotentOrderProcessor processor;

    public OrderListener(IdempotentOrderProcessor processor) {
        this.processor = processor;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "orders-service"
    )
    public void onOrder(OrderCreated event) {
        processor.process(event);
    }
}
~~~

Khi processor trả về DUPLICATE, listener có thể return bình thường. Container xem invocation hoàn tất và offset được commit theo AckMode đang cấu hình.

Khi processor ném exception, listener failure đi vào error handler. Nếu retry lại cùng record, key vẫn giống nhau. Nếu lần đầu đã commit transaction, retry trở thành duplicate và không lặp business mutation.

Không gọi acknowledge trước khi processor transaction commit. Nếu dùng MANUAL AckMode, hãy acknowledge sau khi service trả về với transaction đã hoàn tất theo contract.

## 17. Offset commit và database transaction là hai ranh giới

Idempotency key giúp xử lý cửa sổ crash giữa DB commit và Kafka offset commit:

~~~text
Kafka record
    |
    v
DB transaction:
  insert key + business update
    |
    v
DB COMMIT
    |
    +--> process crash
    |
    v
Kafka offset chưa commit
    |
    v
Redelivery
    |
    v
Key đã tồn tại -> skip business mutation
    |
    v
Listener return success
    |
    v
Offset commit
~~~

Đây là một trong những lợi ích quan trọng nhất của inbox/deduplication pattern.

Nếu offset commit trước DB transaction, crash sau commit offset nhưng trước database commit có thể làm record không được giao lại và side effect bị mất. Vì thế, khi dùng database side effects, cần cấu hình acknowledgement boundary để DB commit xảy ra trước khi record được xem là hoàn tất.

Idempotency không biến database và Kafka thành một distributed transaction. Nó làm redelivery an toàn trong failure window mà at-least-once processing tạo ra.

## 18. Idempotency key không phải Kafka producer idempotence

Kafka producer có cơ chế idempotence để ngăn duplicate writes do producer retries ở tầng Kafka protocol. Cơ chế này dựa trên producer ID, sequence numbers và broker handling.

Nó **không tự chống duplicate business processing ở consumer**:

| Kafka producer idempotence | Business idempotency key |
|---|---|
| Bảo vệ producer retries trong protocol scope | Bảo vệ logical operation ở business layer |
| Áp dụng cho writes của producer | Áp dụng cho side effects do consumer thực hiện |
| Không thay thế DB unique constraint | Thường được enforce bằng DB unique constraint |
| Không ngăn consumer redelivery sau offset chưa commit | Nhận diện redelivery cùng operation |
| Không bảo vệ HTTP/payment/email side effects | Có thể phối hợp với external API idempotency |

Bật enable.idempotence=true cho producer là hữu ích, nhưng không thay thế consumer deduplication. Cũng không nhầm nó với exactly-once semantics của Kafka transactions.

## 19. Kafka exactly-once semantics không tự bảo vệ external database

Kafka transactions có thể phối hợp consume-transform-produce trong Kafka để atomically commit output records và consumed offsets theo transaction semantics. Nhưng nếu listener còn ghi vào PostgreSQL, gọi payment API hoặc gửi email, các side effects đó không tự nằm trong Kafka transaction.

~~~text
Kafka input
    |
    v
Kafka transaction
    |
    +--> produce Kafka output
    |
    +--> commit consumed offset
    |
    v
Kafka transaction commit

PostgreSQL / HTTP API / Email
    |
    +--> không tự thuộc Kafka transaction
~~~

Một consumer có thể dùng Kafka EOS cho Kafka-to-Kafka flow và vẫn cần idempotency key hoặc inbox/outbox khi có external side effects.

Đừng tuyên bố "exactly once" cho toàn bộ business workflow chỉ vì producer transaction được bật. Hãy chỉ rõ exactly-once boundary nằm ở đâu.

## 20. Idempotency với external API

Giả sử listener nhận PaymentRequested và gọi payment gateway:

~~~text
Kafka listener
     |
     v
POST /payments
     |
     v
Payment gateway charges card
     |
     v
Response bị timeout trên network
~~~

Timeout không cho biết gateway đã charge hay chưa. Nếu consumer retry bằng một request mới, khách hàng có thể bị charge hai lần.

Nếu gateway hỗ trợ idempotency key, gửi cùng key cho mọi retry của cùng payment operation:

~~~http
POST /payments
Idempotency-Key: payment-command-91
Content-Type: application/json
~~~

Lần retry dùng cùng key và cùng request body. Gateway có thể trả lại kết quả đã lưu thay vì tạo charge mới, theo contract của provider.

Cần kiểm tra:

- API provider có thật sự hỗ trợ idempotency không.
- Key scope theo merchant/account/endpoint nào.
- Thời hạn provider giữ key.
- Cùng key với payload khác được xử lý thế nào.
- Response gốc có được trả lại không.
- Timeout sau khi request được nhận có thể tra cứu bằng key không.
- Key có giới hạn độ dài/ký tự không.

Không tự thêm header Idempotency-Key rồi giả định một API bất kỳ sẽ thực thi semantics idempotent. Server nhận request phải có cơ chế lưu và enforce key.

## 21. Database inbox và external API idempotency cần phối hợp

Một bảng processed_messages chỉ bảo vệ database transaction của chính service. Nó không thể atomic với payment gateway.

Một failure window:

~~~text
1. Insert idempotency marker.
2. Call payment API.
3. Gateway charge thành công.
4. Service crash trước khi ghi payment result.
5. Kafka redelivery.
6. Marker tồn tại, service skip.
~~~

Nếu marker đã commit trước external call, service có thể skip một operation chưa lưu kết quả local. Nếu marker cùng transaction nhưng external call xảy ra trước commit, crash/timeout vẫn có thể tạo trạng thái không rõ.

Một số hướng thiết kế:

- Gửi idempotency key ổn định tới external provider.
- Lưu operation state và provider request key.
- Dùng trạng thái PENDING/COMPLETED/FAILED có transition rõ.
- Có reconciliation job tra cứu trạng thái external operation sau timeout.
- Dùng outbox để phát command bền vững.
- Dùng saga/compensation khi workflow gồm nhiều hệ thống.
- Không coi một network timeout là bằng chứng external operation thất bại.

Với side effect quan trọng như thanh toán, idempotency của provider và reconciliation là lớp bảo vệ cần thiết; local database marker không đủ.

## 22. Inbox pattern cho Kafka consumer

**Inbox pattern** lưu message đã nhận hoặc đã xử lý trong database cùng business state change. Bảng processed_messages là một dạng inbox đơn giản.

~~~text
Kafka record
     |
     v
Consumer
     |
     v
BEGIN DB TRANSACTION
     |
     +--> INSERT inbox/idempotency key
     |
     +--> Apply business state change
     |
     +--> Store outcome
     |
     v
COMMIT
     |
     v
Listener success / Kafka offset commit
~~~

Inbox giúp:

- Chống redelivery.
- Xác định duplicate.
- Lưu dấu vết operation.
- Có thể lưu payload hash và kết quả xử lý.
- Hỗ trợ audit/reconciliation.
- Phân biệt message đã nhận với message đã hoàn tất nếu schema có trạng thái.

Một inbox table cần unique constraint. Nếu chỉ lưu log text "processed eventId" mà không có unique constraint/transaction, nó không bảo đảm concurrency safety.

## 23. Outbox pattern khi service vừa ghi DB vừa publish Kafka

Idempotency key thường đi cùng **outbox pattern** ở phía producer. Ví dụ service tạo order và muốn publish OrderCreated:

~~~text
BEGIN DB TRANSACTION
    |
    +--> INSERT order
    |
    +--> INSERT outbox event với eventId
    |
    v
COMMIT
    |
    v
Outbox relay đọc event
    |
    v
Publish Kafka
    |
    v
Mark outbox row sent
~~~

Nếu relay publish thành công rồi crash trước khi mark sent, event có thể được publish lại. Consumer vẫn cần idempotency key để chống duplicate business side effect.

Outbox giải quyết atomicity giữa business database state và việc ghi ý định publish trong cùng database. Nó không bảo đảm message chỉ xuất hiện đúng một lần trên Kafka trong mọi failure mode.

Kết hợp thường gặp:

- Producer side: outbox event ID ổn định.
- Kafka: record key/partitioning theo business aggregate nếu cần ordering.
- Consumer side: inbox/idempotency table với unique key.
- Database side effect: cùng transaction với inbox marker.
- External API: provider idempotency key và reconciliation.

## 24. Idempotency state có thể cần PENDING và COMPLETED

Mô hình đơn giản chỉ lưu một marker đã xử lý phù hợp khi side effect và marker commit cùng transaction.

Với workflow dài hoặc external API, có thể cần state machine:

~~~text
NEW
 |
 v
PENDING
 |
 +--> COMPLETED
 |
 +--> RETRYABLE_FAILURE
 |
 +--> PERMANENT_FAILURE
 |
 +--> UNKNOWN_EXTERNAL_RESULT
~~~

Ví dụ schema:

~~~sql
CREATE TABLE idempotent_operations (
    operation_scope VARCHAR(120) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    payload_hash BYTEA NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    result_reference VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (operation_scope, idempotency_key)
);
~~~

Các trạng thái phải có semantics rõ:

- PENDING: operation đã được nhận và đang xử lý.
- COMPLETED: side effect đã hoàn tất và có kết quả bền vững.
- RETRYABLE_FAILURE: có thể thử lại.
- PERMANENT_FAILURE: cần xử lý thủ công hoặc DLT.
- UNKNOWN_EXTERNAL_RESULT: request ngoài đã timeout, chưa biết kết quả.

Không đánh dấu COMPLETED trước khi side effect hoàn tất. Nếu dùng PENDING, cần quy tắc lease/timeout và cơ chế phục hồi khi worker chết giữa chừng.

## 25. Lease và fencing cho operation xử lý lâu

Một workflow PENDING có thể bị worker bỏ dở. Sau một thời gian, worker khác có thể cần tiếp tục. Nếu chỉ có một cột status và updated_at, worker cũ có thể quay lại sau khi lease hết và cùng commit kết quả với worker mới.

Có thể dùng:

- lease_owner.
- lease_until.
- attempt/version number.
- optimistic locking.
- fencing token tăng dần.
- state transition có điều kiện.

Ví dụ:

~~~sql
UPDATE idempotent_operations
SET status = 'PENDING',
    lease_owner = :workerId,
    lease_until = now() + interval '30 seconds',
    version = version + 1
WHERE operation_scope = :scope
  AND idempotency_key = :key
  AND (
      status = 'NEW'
      OR (status = 'PENDING' AND lease_until < now())
  )
RETURNING version;
~~~

Worker chỉ được commit kết quả nếu fencing version vẫn là version nó sở hữu. Các downstream systems cần hiểu fencing token nếu side effect có thể được gửi từ worker cũ sau khi lease hết.

Lease không thay thế external idempotency key. Nó chỉ giúp điều phối ownership; network timeout vẫn có thể khiến kết quả external operation không rõ.

## 26. Idempotency trong batch listener

Một batch có nhiều records và mỗi record có một idempotency key riêng:

~~~text
Batch:
  E1 -> key-1
  E2 -> key-2
  E3 -> key-3
  E4 -> key-4
~~~

Có hai lựa chọn transaction:

**Một transaction cho toàn batch**

- Insert markers và apply tất cả business changes trong một transaction.
- Nếu một record lỗi, cả batch rollback.
- Retry batch có thể thấy các records trước chưa commit, nên xử lý lại.
- Mỗi key vẫn cần unique constraint.

**Một transaction cho từng record**

- Mỗi record commit độc lập.
- Một số records có thể đã hoàn tất trước khi batch thất bại.
- Khi batch được retry, những records đã commit trở thành duplicates và được skip.
- Cần hiểu Spring Kafka batch error handling và offset semantics.

Không dùng một idempotency key cho cả batch nếu từng record là business operation độc lập. Nếu batch itself là một command duy nhất, key batch cần được định nghĩa riêng và các item semantics phải rõ.

## 27. DLT replay và idempotency key

Khi record được đưa vào DLT rồi replay, câu hỏi quan trọng là: replay có đại diện cho **cùng logical operation** hay một operation mới?

Nếu replay để thử lại cùng business event sau khi sửa database outage, giữ nguyên idempotency key. Nếu side effect đã commit trước khi consumer crash, replay sẽ được nhận diện là duplicate.

~~~text
Source event E, key=evt-100
       |
       v
Business DB commit
       |
       v
Offset commit failure
       |
       v
Record redelivery / DLT replay
       |
       v
Same key evt-100
       |
       v
Skip duplicate side effect
~~~

Nếu replay nhằm sửa một projection hoặc tái tạo dữ liệu từ đầu, policy có thể khác. Khi đó cần một **rebuild namespace** hoặc một operation version mới được định nghĩa rõ, để tránh xóa deduplication state một cách vô ý.

Không tự thêm replay timestamp vào idempotency key. Làm vậy sẽ biến mỗi lần replay thành một operation mới và có thể lặp side effects.

Nếu cố ý tạo một operation mới, hãy ghi audit, xác định compensation/side effect behavior và bảo đảm key versioning là một quyết định nghiệp vụ.

## 28. Retention của idempotency keys

Deduplication state phải được giữ đủ lâu để bao phủ mọi khả năng redelivery/replay mà hệ thống cam kết hỗ trợ.

Một nguyên tắc:

~~~text
Idempotency retention
    >= max(
         Kafka source retention,
         retry-topic delay horizon,
         DLT retention/replay horizon,
         producer retry window,
         business replay window
       )
~~~

Đây là cách ước lượng theo các horizon độc lập; thực tế cần cộng thêm khoảng an toàn cho thời gian điều tra, replication/backup và các workflow có thể bị trì hoãn.

Nếu xóa key quá sớm:

1. Record cũ được replay.
2. Marker không còn.
3. Consumer coi đó là operation mới.
4. Business side effect chạy lần nữa.

Nếu giữ vĩnh viễn:

- Bảng deduplication tăng không giới hạn.
- Index phình to.
- Vacuum/maintenance tốn tài nguyên.
- Query/backup/restore nặng hơn.
- Cần partitioning hoặc archival.

Retention là một phần của reliability contract. Nếu DLT có thể được replay sau sáu tháng nhưng marker chỉ giữ bảy ngày, hệ thống không bảo đảm idempotency cho replay sáu tháng.

## 29. Dọn dẹp idempotency records an toàn

Một bảng có processed_at có thể dọn theo batch:

~~~sql
DELETE FROM processed_messages
WHERE processed_at < now() - interval '90 days';
~~~

Đây là ví dụ đơn giản, không nên chạy một DELETE khổng lồ trong production nếu bảng lớn. Có thể:

- Partition table theo processed_at.
- Drop partition cũ sau khi hết retention.
- Delete theo batch giới hạn.
- Archive audit records.
- Giám sát dead tuples và index size.
- Đồng bộ retention với Kafka topics và DLT replay policy.

Không xóa key cho operation PENDING hoặc UNKNOWN_EXTERNAL_RESULT chỉ dựa vào tuổi record. Những trạng thái đó cần reconciliation trước khi dọn.

Nếu consumer group được reset về offset cũ, hoặc topic được replay từ backup, phải xem xét retention policy trước khi cho phép thao tác.

## 30. Idempotency key và multi-tenant systems

Nếu hệ thống multi-tenant, key cần được namespace hoặc unique constraint theo tenant khi hai tenants có thể dùng cùng command IDs.

Ví dụ:

~~~text
tenant-a:payment:cmd-100
tenant-b:payment:cmd-100
~~~

Hai keys khác nhau vì cùng cmd-100 ở hai tenant là hai operations khác nhau.

Schema:

~~~sql
PRIMARY KEY (
    operation_scope,
    tenant_id,
    idempotency_key
)
~~~

Không lấy tenant ID thô từ payload rồi tin tưởng vô điều kiện. Phải xác thực tenant theo security context hoặc contract đã được kiểm tra. Một producer gửi sai tenant ID có thể gây collision hoặc ghi side effect vào sai namespace.

Nếu tenant ID là PII hoặc nhạy cảm, dùng một internal tenant identifier phù hợp và bảo vệ nó trong logs/metrics.

## 31. Idempotency key có cần hash không?

Một số hệ thống muốn giới hạn độ dài hoặc tránh lưu raw key. Có thể lưu digest:

~~~text
raw idempotency key
       |
       v
canonicalization
       |
       v
SHA-256
       |
       v
stored key digest
~~~

Ưu điểm:

- Độ dài cố định.
- Index nhỏ và ổn định hơn với keys dài.
- Không lưu raw key trong bảng deduplication.
- Dễ chuẩn hóa key input.

Nhưng hash không tự giải quyết mọi vấn đề:

- Cần canonicalization giống nhau giữa producer/consumer.
- Collision dù cực hiếm vẫn là một khía cạnh của contract.
- Nếu key có entropy thấp, hash không bảo vệ khỏi dictionary guessing.
- Debug cần có cách đối chiếu an toàn.
- Payload hash và idempotency key hash là hai mục đích khác nhau.

Nếu raw key chứa secret hoặc PII, tốt hơn là thiết kế một opaque random ID không mang thông tin nhạy cảm ngay từ đầu. Không coi SHA-256 của email hoặc phone là dữ liệu vô danh tuyệt đối.

## 32. Idempotency key và ordering/version của aggregate

Idempotency ngăn một operation bị thực hiện hai lần, nhưng không tự bảo đảm thứ tự events.

Ví dụ:

~~~text
Order version 2: AddressChanged
Order version 3: OrderShipped
~~~

Nếu version 3 đến trước version 2, hai event có idempotency keys khác nhau nên cả hai đều có thể được xử lý. Hệ thống vẫn có thể chuyển state sai nếu không kiểm tra version/order.

Có thể lưu aggregate version và áp dụng optimistic condition:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = :incomingVersion
WHERE order_id = :orderId
  AND version = :incomingVersion - 1;
~~~

Nếu update không tác động row, cần phân biệt duplicate, stale event và missing predecessor. Idempotency key xử lý duplicate identity; version check xử lý ordering/state transition. Hai cơ chế bổ sung nhau.

Kafka key có thể được dùng để giữ events của cùng aggregate trong một partition, nhưng partitioning không thay thế version validation vì producer retries, migrations và nhiều sources vẫn có thể ảnh hưởng order.

## 33. Side effect không nằm trong database transaction

Một số side effects không thể rollback cùng inbox marker:

- Gửi email.
- Gửi SMS.
- Gọi payment gateway.
- Gọi partner REST API.
- Tạo file trên object storage.
- Gửi lệnh tới một hệ thống khác.
- Phát một message Kafka khác.

Không đặt lời gọi HTTP trong một DB transaction rồi giả định DB rollback sẽ hủy HTTP request. Nếu HTTP thành công và transaction rollback, lần retry có thể gửi lại HTTP.

Các lựa chọn:

1. External API hỗ trợ idempotency key.
2. Ghi intent vào outbox trong cùng DB transaction rồi worker thực hiện side effect.
3. Lưu operation state và reconciliation.
4. Dùng saga/compensation cho workflow nhiều hệ thống.
5. Thiết kế side effect là state-setting nếu nghiệp vụ cho phép.
6. Có timeout và phân loại kết quả UNKNOWN khi không biết remote đã xử lý hay chưa.

Một email provider không hỗ trợ idempotency có thể gửi duplicate dù local service đã có marker. Có thể dùng outbox để bảo đảm dispatch intent, nhưng vẫn cần provider deduplication hoặc một chiến lược chấp nhận duplicate/compensation.

## 34. Idempotency cho payment và inventory

### Payment

Key nên đại diện cho một charge/refund operation cụ thể:

~~~text
merchant-42:charge:payment-command-91
merchant-42:refund:refund-command-18
~~~

Không chỉ dùng orderId nếu một order có thể charge nhiều lần, capture nhiều lần hoặc refund từng phần.

Lưu provider reference và kết quả để khi retry có thể trả kết quả cũ hoặc query provider. Nếu timeout không rõ charge đã xảy ra chưa, không tạo key mới để thử lại.

### Inventory

Một command reserve stock có thể dùng:

~~~text
warehouse-3:reserve:reservation-command-100
~~~

Nếu cùng command đến hai lần, chỉ reserve một lần. Nhưng một order có thể cần nhiều reservation adjustments; key phải nhận diện từng adjustment.

Khi inventory release hoặc compensation, đó là operation riêng với key riêng, không reuse key reserve.

## 35. Error handling khi idempotency storage gặp sự cố

Nếu database deduplication table unavailable, consumer không thể xác định record đã xử lý hay chưa. Có hai lựa chọn nguy hiểm:

- Tiếp tục side effect mà không kiểm tra key: có thể duplicate.
- Bỏ qua record và commit offset: có thể mất business operation.

Với side effect quan trọng, cách an toàn thường là **fail processing và để retry/backoff** thay vì bypass idempotency check.

~~~text
Idempotency DB unavailable
       |
       v
Cannot determine duplicate state
       |
       +--> Do not apply unguarded side effect
       |
       +--> Throw retryable exception
       |
       v
Error handler/backoff
       |
       v
Retry after recovery
~~~

Không retry vô hạn với backoff quá ngắn. Có thể phối hợp circuit breaker hoặc pause listener khi DB outage kéo dài. Khi recovery, cùng key vẫn được sử dụng.

Nếu deduplication store là một database riêng với business DB, cần giải quyết atomicity giữa hai stores. Một key check ở Redis rồi business write ở PostgreSQL không atomic; Redis outage/eviction có thể làm duplicate side effect. Ưu tiên cùng transactional database hoặc một protocol được thiết kế rõ.

## 36. Duplicate không nhất thiết là success trong mọi business contract

Khi key đã tồn tại:

- Nếu payload hash giống và operation COMPLETED: có thể trả kết quả cũ hoặc skip side effect.
- Nếu payload hash khác: conflict.
- Nếu operation PENDING: chờ, trả trạng thái in-progress hoặc điều phối lease.
- Nếu operation RETRYABLE_FAILURE: tiếp tục theo retry policy.
- Nếu operation UNKNOWN_EXTERNAL_RESULT: reconcile trước khi gửi lại.
- Nếu operation PERMANENT_FAILURE: trả trạng thái lỗi đã lưu hoặc chuyển quarantine.

Một API command thường nên trả **kết quả ban đầu** cho client khi họ retry cùng key, thay vì chỉ trả "duplicate". Kafka listener có thể không cần trả business response ra ngoài, nhưng vẫn cần biết operation đã completed hay chưa.

Không đánh dấu mọi key tồn tại là duplicate success nếu schema có nhiều trạng thái. Chỉ skip khi trạng thái thực sự bảo đảm side effect đã hoàn tất.

## 37. Observability cho idempotency

Metrics hữu ích:

| Metric | Ý nghĩa |
|---|---|
| idempotency_first_seen_total | Key mới được nhận |
| idempotency_duplicate_total | Duplicate được nhận diện |
| idempotency_key_conflict_total | Cùng key nhưng payload fingerprint khác |
| idempotency_in_progress_total | Operation đang PENDING |
| idempotency_reconciliation_total | Operation cần đối chiếu external result |
| idempotency_store_error_total | Không truy cập được deduplication store |
| idempotency_processing_duration | Thời gian xử lý operation |
| idempotency_cleanup_total | Số records được dọn |
| idempotency_lease_expired_total | Operation lease hết hạn |

Metric tags nên có cardinality thấp như consumer, operation type và outcome. Không đưa idempotency key, event ID, order ID hoặc trace ID vào metric labels.

Structured logs có thể ghi key fingerprint đã rút gọn hoặc mã correlation đã được phép:

~~~json
{
  "level": "INFO",
  "event": "kafka_duplicate_skipped",
  "listener_id": "ordersListener",
  "consumer_group": "orders-service",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "operation_scope": "order-projection",
  "idempotency_outcome": "duplicate"
}
~~~

Không log raw payload hoặc key nếu chúng chứa dữ liệu nhạy cảm. Trace có thể liên kết lần delivery hiện tại với upstream processing, nhưng idempotency key vẫn là identity business riêng.

## 38. Kiểm thử idempotency đúng failure boundaries

Một test chỉ gọi processor hai lần tuần tự không đủ chứng minh concurrency safety hoặc crash recovery.

Các tình huống cần thử:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Cùng key, cùng payload lần đầu | Business side effect áp dụng một lần |
| Cùng key, cùng payload lần hai | Duplicate được skip/trả kết quả cũ |
| Cùng key, payload khác | Key conflict, không silently skip |
| Hai consumers đồng thời cùng key | Chỉ một transaction áp dụng side effect |
| Crash trước DB commit | Marker và side effect cùng rollback |
| Crash sau DB commit trước offset commit | Redelivery bị deduplicate |
| Offset commit trước DB commit trong cấu hình sai | Test phát hiện nguy cơ mất side effect |
| DB unavailable | Không bypass idempotency check |
| DLT replay cùng event ID | Không lặp side effect đã hoàn tất |
| Retry topic redelivery | Cùng logical key được giữ nguyên |
| Key khác nhau cho hai commands cùng order | Cả hai operations hợp lệ được xử lý |
| Tenant khác nhau, cùng command ID | Không collision nếu scope khác |
| Key cũ sau retention expiry | Behavior phù hợp replay policy |
| Lease hết hạn, worker cũ quay lại | Fencing ngăn stale worker commit |
| External API timeout sau khi remote thành công | Retry cùng provider key không lặp side effect |
| Batch lỗi giữa chừng | Các item đã commit được deduplicate khi batch retry |
| Payload hash canonicalization | Equivalent requests tạo cùng fingerprint |

Nên kiểm tra database rows và business state, không chỉ assert listener method được gọi bao nhiêu lần. Với concurrency test, tạo nhiều threads/transactions thật trên cùng database unique constraint.

## 39. Quy trình triển khai idempotency key

1. Xác định logical operation cần chống thực hiện lặp.
2. Phân biệt Kafka key, event ID, command ID và trace ID.
3. Chọn namespace: consumer, operation, tenant hoặc business scope.
4. Tạo key tại nguồn một lần và giữ nguyên qua retry/replay.
5. Định nghĩa canonical payload fingerprint.
6. Tạo inbox/deduplication table có unique constraint.
7. Insert marker và business side effect trong cùng DB transaction.
8. Xử lý duplicate theo stored status và payload hash.
9. Để exception đi qua error handler khi transaction chưa hoàn tất.
10. Commit Kafka offset sau khi business transaction đã hoàn tất.
11. Với external APIs, gửi cùng provider idempotency key và lưu kết quả.
12. Với workflow dài, thiết kế PENDING/COMPLETED, lease và fencing.
13. Chọn retention theo source/retry/DLT/replay horizons.
14. Dọn records theo batch/partition và giữ các operation chưa hoàn tất.
15. Ghi metrics/logs cho duplicate, conflict, store errors và reconciliation.
16. Kiểm thử concurrency, crash, timeout, DLT replay và cleanup.

## 40. Checklist trước production

- Idempotency key nhận diện logical operation, không chỉ entity.
- Key được tạo một lần ở producer/command boundary và ổn định qua redelivery.
- Không tạo key random mới mỗi lần listener chạy.
- Không nhầm Kafka record key với event ID/idempotency key.
- Key scope có operation/tenant namespace phù hợp.
- Cùng key với payload khác được phát hiện thành conflict.
- Payload hash dùng canonical representation ổn định.
- Database unique constraint là concurrency arbiter.
- Marker và business mutation cùng một transaction.
- Duplicate chỉ được skip khi operation đã hoàn tất.
- Offset không commit trước business transaction.
- Retry/DLT/replay giữ nguyên key cho cùng logical operation.
- Replay có chủ đích tạo operation mới phải có policy/version rõ.
- Retention bao phủ mọi redelivery/replay horizon đã cam kết.
- Cleanup không xóa PENDING hoặc UNKNOWN operations.
- External API có idempotency contract hoặc reconciliation/compensation.
- Outbox/inbox được dùng đúng ranh giới.
- Kafka EOS không bị hiểu nhầm là exactly-once cho database/HTTP.
- Async workers có lease/fencing nếu xử lý dài và có thể chạy trùng.
- Batch listener có semantics key/transaction theo từng item hoặc batch rõ ràng.
- Metrics không dùng idempotency key làm tag.
- Logs không lộ payload, PII hoặc secrets.
- Đã test crash sau DB commit trước offset commit.
- Đã test hai consumers đồng thời với cùng key.
- Có runbook cho key conflict, store outage, duplicate spike và replay.

**Kết luận:** Idempotency key là identity ổn định của một logical operation, giúp Spring Kafka consumer chịu được redelivery, retry, rebalance và DLT replay mà không lặp business side effect. Phần quyết định tính đúng là **key phải giữ nguyên qua mọi lần delivery, unique constraint phải điều phối cạnh tranh, và idempotency marker phải commit atomic cùng side effect trong cùng database transaction**. Với external systems, cần provider idempotency key, outbox/reconciliation hoặc compensation. Retention và replay policy cũng phải khớp nhau; nếu deduplication state bị xóa trước khi event cũ có thể quay lại, bảo vệ idempotency không còn hiệu lực.

