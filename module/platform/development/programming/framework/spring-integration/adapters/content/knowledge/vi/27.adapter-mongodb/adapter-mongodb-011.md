# Xử lý duplicate key và retry trong Spring Integration MongoDB

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích lỗi **MongoDB E11000 duplicate key** (thường có mã `11000`), tại sao nó xuất hiện khi `insert`, `upsert`, `update` hoặc thao tác bulk vi phạm unique index, và cách Spring Data chuyển thành `DuplicateKeyException`.
- Phân biệt **message được giao trùng**, **business request lặp lại hợp lệ**, **ID xung đột với nội dung khác** và **trùng do sai thiết kế unique index**; không xem tất cả duplicate là thành công.
- Thiết kế business idempotency key ổn định qua retry/restart, quy định phạm vi tenant/nguồn, dùng MongoDB `_id` hoặc compound unique index làm điểm phân xử race.
- So sánh `insert`, `save`, `upsert`, `updateFirst`, `findAndModify` và `insertMany/bulkWrite` về duplicate/error semantics.
- Xây dựng handler Spring Integration nhận message từ HTTP/JMS/AMQP/Kafka/file/SFTP, ghi inbox MongoDB và phân loại kết quả **INSERTED / ALREADY_ACCEPTED / CONFLICT**.
- Giải thích **Retryable Writes của MongoDB driver** khác **Spring Integration `RequestHandlerRetryAdvice` / Spring Retry** và khác redelivery của broker.
- Phân loại **lỗi tạm thời** (network, failover, timeout, resource contention) với **lỗi vĩnh viễn** (unique conflict, schema, auth); cấu hình retry có max attempts, exponential backoff, jitter, recovery channel.
- Xử lý trường hợp **MongoDB đã ghi nhưng response/ACK thất lạc**, sau đó retry gặp E11000; biết cách đối soát cùng event ID và payload thay vì tạo key mới.
- Biết ranh giới của retry trong MongoDB transaction, including `TransientTransactionError`, `UnknownTransactionCommitResult` và quy định không tự retry mọi duplicate-key.
- Thiết kế dead-letter/quarantine, transactional outbox/inbox, ack policy, observability, graceful shutdown và test concurrency, duplicate, timeout, restart.

Bài thuộc chương **Adapter MongoDB** của module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành kết nối file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, đồng thời xử lý hợp đồng message, lỗi và vòng đời kết nối. Chủ đề ở đây là **tính đúng đắn khi một dữ liệu được gửi lại hoặc nhiều worker cùng ghi**: lỗi duplicate key vừa là công cụ bảo vệ tính duy nhất, vừa có thể là dấu hiệu một request hợp lệ đã được xử lý trước đó.

> **Phạm vi phiên bản:** ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data MongoDB, Spring Integration 6.x và Spring Retry 2.x tương thích với BOM của dự án. Các API của Spring Integration 7.x hoặc Spring Retry đời mới có thể thay đổi; đối chiếu theo dependency thực tế. Ví dụ mongosh chỉ dùng database test, không thao tác dữ liệu production.

## 1. Bài toán: nguồn gửi lại đúng event, nhưng database báo lỗi

Một thiết bị gửi event qua HTTP hoặc Kafka:

~~~json
{
  "tenantId": "tenant-a",
  "eventId": "evt-1001",
  "deviceId": "node-7",
  "sequence": 1001,
  "temperatureC": 26.5,
  "occurredAt": "2026-11-23T02:00:00Z"
}
~~~

Tại lần nhận đầu tiên, ứng dụng ghi `event_inbox` MongoDB thành công. Nhưng ngay sau khi database ghi, kết nối mất, nên producer **không nhận được xác nhận**. Producer hoặc broker phát lại **cùng event**.

~~~mermaid
sequenceDiagram
    participant P as Producer / Broker
    participant I as Spring Integration
    participant M as MongoDB
    P->>I: evt-1001
    I->>M: insert(_id=tenant-a|evt-1001)
    M->>M: ghi thành công
    M--xI: ACK thất lạc / timeout
    Note over P: Chưa được xác nhận
    P->>I: redelivery evt-1001
    I->>M: insert(cùng _id)
    M-->>I: E11000 duplicate key
    I->>M: readback bằng _id, so sánh nội dung
    M-->>I: nội dung trùng hoàn toàn
    I-->>P: ALREADY_ACCEPTED, theo chính sách ACK
~~~

**Đọc kỹ sơ đồ:** E11000 của lần ghi thứ hai không nhất thiết có nghĩa toàn bộ request ban đầu thất bại. Nếu record đã tồn tại **và nội dung nghiệp vụ thật sự khớp**, lần nhận lại có thể là **idempotent repeat**. Nhưng nếu ID giống mà amount/device/content khác, đây là **business conflict** phải được báo rõ.

### 1.1. Các kết quả nên phân biệt

| Tình huống | Kết quả xử lý | Có retry insert nguyên trạng ngay? |
|---|---|---|
| ID chưa có, insert thành công | `INSERTED` | Không |
| ID đã có, payload tương đương, trạng thái đã nhận bền | `ALREADY_ACCEPTED` | Không cần |
| ID đã có nhưng payload khác | `CONFLICT` | **Không**; cảnh báo/quarantine |
| E11000 do **index khác** `_id` | `CONFLICT` hoặc vấn đề data model | **Không** retry mù |
| Network timeout, chưa rõ insert đã xảy ra | `UNKNOWN` → reconcile/retry có giới hạn | Có thể, **giữ nguyên ID** |
| MongoDB unavailable | `TRANSIENT_FAILURE` | Có, nếu có retry policy |
| Mapping/schema validation sai | `INVALID_MESSAGE` | Không; sửa nguồn dữ liệu |
| Duplicate sau khi consumer đã commit | `ALREADY_PROCESSED` theo business state | Không phát side effect lần hai |

**Không đặt tên chung `SUCCESS` cho tất cả trường hợp trên.** Kết quả “đã ghi vào inbox” và “đã phát Kafka” hoặc “đã thanh toán” là **hai business stages khác nhau**.

## 2. E11000 duplicate key xuất phát từ đâu?

Trong MongoDB, collection mặc định có unique index trên `_id`. Ứng dụng có thể thêm unique indexes trên những business keys khác. Nếu một thao tác tạo hoặc cập nhật document làm trùng một giá trị được unique index bảo vệ, server thường trả lỗi:

~~~text
E11000 duplicate key error collection: lab.event_inbox
index: _id_ dup key: { _id: "tenant-a|evt-1001" }
~~~

Mã server thường là **`11000`**. Với Spring Data MongoDB dùng `MongoTemplate`/`MongoOperations`, lỗi thường được dịch thành:

~~~java
org.springframework.dao.DuplicateKeyException
~~~

Đây là subclass của `DataIntegrityViolationException` trong Spring DAO exception hierarchy. Với raw MongoDB Java driver, bạn có thể thấy `MongoWriteException` hoặc `MongoBulkWriteException` chứa write error code `11000`; **không** giả định mọi code path đều ném trực tiếp cùng một Spring DAO exception.

### 2.1. Vì sao lỗi không chỉ xảy ra trên insert?

| MongoDB operation | Khi nào có thể E11000? | Lưu ý |
|---|---|---|
| `insertOne` / `MongoOperations.insert` | `_id` hoặc unique business key trùng | Phù hợp lưu event bất biến |
| `insertMany` / `bulkWrite` | Một hay nhiều document vi phạm unique index | Có thể partial success nếu không transaction |
| `save` với `_id` đã có | Có thể **replace** document tương ứng, nhưng vẫn có thể vi phạm **unique index khác** | Không dùng save để ngăn duplicate message |
| `updateOne` / `updateFirst` | Cập nhật field làm đụng unique key document khác | Không nhất thiết do duplicate event |
| `upsert` | Nhánh insert mới đụng unique constraint, hoặc race giữa workers | Một số trường hợp có thể được server xử lý đặc biệt; không dựa vào điều đó |
| `findAndModify` + upsert | Upsert tạo document mới trùng index | Cần query/unique key tương thích |
| Tạo unique index trên dữ liệu cũ | Collection đã tồn tại giá trị trùng | Index build có thể thất bại |
| Replacing document có field mới | Unique index của field mới bị đụng | Phải đối chiếu đúng index name |

### 2.2. E11000 không phải “đã có cùng event”

Một collection có thể có đồng thời:

~~~javascript
db.event_inbox.createIndex(
  { tenantId: 1, eventId: 1 },
  { unique: true }
)

db.event_inbox.createIndex(
  { tenantId: 1, deviceId: 1, sequence: 1 },
  { unique: true }
)
~~~

Giả sử `eventId=evt-2001` chưa tồn tại nhưng `(tenant-a,node-7,sequence=1001)` đã thuộc event `evt-1001`: lệnh insert mới có thể gây E11000 vì **index thứ hai**. Vì vậy, khi bắt DuplicateKeyException:

1. Dùng **business key cố định** để đọc lại record tương ứng.
2. So sánh tenant, eventId và nội dung canonical.
3. Nếu không có record với đúng ID mà vẫn E11000, hãy nghi ngờ **index khác hoặc dữ liệu conflict**.
4. Không suy luận mọi duplicate đều nên ACK như thành công.

## 3. Unique index và cách thiết kế business key

### 3.1. Ưu tiên ID ổn định qua retry

Một business event ID phải:

- Được producer hoặc tầng ingress tạo **một lần** cho một sự kiện logic.
- Giữ nguyên khi broker redeliver, HTTP retry, MongoDB driver retry hoặc application retry.
- Có phạm vi rõ ràng theo tenant/nguồn/loại event khi cần.
- Không dựa trên Spring `MessageHeaders.ID` mới của mỗi lần dispatch.
- Không dùng `UUID.randomUUID()` mới cho mỗi lần thử ghi cùng event.

Ví dụ cách tạo MongoDB `_id` có namespace cho lab:

~~~java
String mongoId = tenantId + "|" + eventId;
~~~

**Production phải validate** tenantId/eventId và quy định escaping/độ dài để tránh va chạm: `tenant-a|x` + `y` không được trùng logic với một cặp ID khác do ký tự phân tách. Có thể dùng một generated canonical encoded ID hoặc unique compound index.

### 3.2. Compound unique index

Ví dụ mongosh:

~~~javascript
use integration_lab

db.event_inbox.createIndex(
  { tenantId: 1, eventId: 1 },
  {
    unique: true,
    name: "uq_tenant_event"
  }
)
~~~

Dùng unique index này khi eventId chỉ duy nhất **trong một tenant**. Nếu eventId là global unique, `_id` tự nhiên có thể đã đủ.

Khi test:

~~~javascript
db.event_inbox.insertOne({
  _id: "doc-1", tenantId: "tenant-a",
  eventId: "evt-1001", status: "RECEIVED"
})

db.event_inbox.insertOne({
  _id: "doc-2", tenantId: "tenant-a",
  eventId: "evt-1001", status: "RECEIVED"
})
// Lệnh thứ hai gây duplicate key trên uq_tenant_event.
~~~

**Không chạy seed nhiều lần trên production.** Test database/collection phải được cô lập. Nếu muốn tạo unique index trên collection đã có dữ liệu trùng, index build có thể fail; hãy audit/migrate duplicates trước.

### 3.3. Null, missing field và partial unique index

Một **single-field unique index** thường cho phép tối đa **một entry** có giá trị `null`/missing cho field đó. Compound unique index cũng có quy tắc riêng cho tổ hợp giá trị null/missing. Nếu dữ liệu legacy chưa có eventId, việc tạo unique index có thể khiến inserts hợp lệ khác gặp E11000.

Trong một business collection có mixed schema:

~~~javascript
db.event_inbox.createIndex(
  { tenantId: 1, eventId: 1 },
  {
    unique: true,
    name: "uq_tenant_event_valid",
    partialFilterExpression: {
      tenantId: { $type: "string" },
      eventId: { $type: "string" }
    }
  }
)
~~~

**Đây chỉ là ví dụ policy cho dữ liệu test**, không phải cách chấp nhận thiếu ID trong nghiệp vụ cần idempotency. Một partial index áp dụng uniqueness **chỉ cho documents khớp filter**; document nằm ngoài filter **không được bảo vệ bởi index đó**. Với inbox production cần eventId bắt buộc, hãy validate schema/ID trước insert và có migration dữ liệu.

### 3.4. Giới hạn unique indexes trên sharded collection

Trên MongoDB sharded cluster, unique index có những hạn chế liên quan shard key. Không mặc định một unique index trên `eventId` được enforce **toàn cluster** nếu nó không tuân theo quy tắc prefix shard key. Thiết kế tenant/shard key và unique index cùng nhau, đọc MongoDB Manual cho version/topology cụ thể.

### 3.5. Index khác với query performance

Unique index bảo đảm ràng buộc dữ liệu, nhưng:

- Tăng chi phí ghi và bộ nhớ/disk.
- Không thay thế rate limit hoặc backpressure.
- Không tự thay thế API authorization theo tenant.
- Không thể sửa một race bằng `if (!exists) insert` đơn thuần; **unique index mới là nơi phân xử cuối**.

## 4. Insert, save, upsert và findAndModify khác nhau

### 4.1. insert: lỗi duplicate giúp phát hiện redelivery

~~~java
mongoOperations.insert(event, "event_inbox");
~~~

Với event bất biến, `insert` thường dễ lý giải: **chưa có → insert, đã có → E11000**. Sau lỗi, service đọc lại theo business key và quyết định duplicate hợp lệ hay conflict.

### 4.2. save: không phải công cụ “ignore duplicate”

~~~java
mongoOperations.save(event, "event_inbox");
~~~

Nếu document có cùng ID, `save` có thể **thay thế** document theo ID thay vì báo duplicate. Đây là rủi ro nếu một message cũ được redeliver sau khi document đã có trạng thái `DONE`: save từ payload cũ có thể ghi status lại `NEW` hoặc ghi đè field nghiệp vụ mới.

**Không dùng save làm idempotent inbox insert** nếu dữ liệu hoặc state có thể thay đổi sau lần ghi đầu. Nếu thực sự cần upsert/replace, quy định version/optimistic locking.

### 4.3. Update có điều kiện không cần đọc trước

Nếu muốn đánh dấu một event đã xử lý:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(id)
            .and("status").is("PROCESSING")
            .and("claimOwner").is(workerId));

Update update = new Update()
    .set("status", "DONE");

UpdateResult result = mongoOperations.updateFirst(
    query, update, "event_inbox");

boolean changed = result.getMatchedCount() == 1;
~~~

Đoạn này là một fragment cần imports `Query`, `Criteria`, `Update`, `UpdateResult` và bean MongoOperations. Việc cập nhật có điều kiện giúp tránh worker cũ đánh dấu DONE khi đã mất quyền claim. Vẫn phải xác định **business commit đã thành công trước khi mark DONE**.

### 4.4. findAndModify để claim atomically

~~~java
Query eligible = Query.query(
    Criteria.where("status").is("NEW"))
    .with(Sort.by(
        Sort.Order.asc("createdAt"),
        Sort.Order.asc("_id")));

Update claim = new Update()
    .set("status", "PROCESSING")
    .set("claimOwner", workerId)
    .set("leaseUntil", leaseDeadline);

InboxEvent claimed = mongoOperations.findAndModify(
    eligible, claim,
    FindAndModifyOptions.options().returnNew(true),
    InboxEvent.class, "event_inbox");
~~~

Một `findAndModify` conditional update atomically trên một document giúp hai workers không đồng thời thắng claim cùng document theo query `status=NEW`. Tuy nhiên cần chính sách **lease expiry/reclaim, fencing/version, retry và idempotency** khi worker chết.

### 4.5. Upsert và race

`update(..., upsert=true)` có thể giúp tạo record nếu chưa có, nhưng không tự là idempotency protocol cho mọi business request. Nếu hai workers cùng upsert trên filter không tương thích unique index hoặc update đổi unique fields, có thể gặp duplicate key. Từ MongoDB **8.1**, một upsert gây duplicate-key bên trong **multi-document transaction** không được server tự retry theo hành vi tài liệu. Không viết retry vô hạn trên DuplicateKeyException để “chờ nó hết”.

## 5. Hợp đồng kết quả: inserted, already accepted, conflict

Một API ingest đáng tin nên định nghĩa kết quả theo nghiệp vụ:

| Kết quả | Khi nào? | Có nên ACK source? |
|---|---|---|
| **INSERTED** | MongoDB insert đã được xác nhận và record có trong durable inbox | Có thể ACK nếu contract chỉ yêu cầu nhận vào inbox |
| **ALREADY_ACCEPTED** | Record cùng ID **và cùng nội dung nghiệp vụ** đã được chấp nhận | Thường có thể ACK lại, nếu business state/durability còn đúng |
| **CONFLICT** | Cùng ID nhưng nội dung khác hoặc unique index khác xung đột | Không coi là success; đưa DLQ/quarantine hoặc trả HTTP 409 |
| **RETRYABLE_FAILURE** | DB tạm unavailable hoặc network transient | Không ACK sớm; retry có giới hạn |
| **UNKNOWN_OUTCOME** | Timeout/mất response, chưa biết kết quả | Reconcile cùng ID trước khi quyết định |
| **INVALID_MESSAGE** | Thiếu tenant/eventId, sai schema/size | Không retry như lỗi transient |

**Một duplicate có thể được ACK như idempotent success chỉ sau khi đã đối chiếu nội dung**, và chỉ trong phạm vi “đã được nhận bền”. Nếu client yêu cầu chứng minh “đã xử lý thanh toán”, phải kiểm tra business completion chứ không chỉ inbox record.

## 6. Thiết lập dự án và dữ liệu demo

### 6.1. Maven dependencies

Với Spring Boot 3.x và Spring Integration 6.x theo BOM tương thích:

~~~xml
<!-- Các dependency bên trong <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-mongodb</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.retry</groupId>
    <artifactId>spring-retry</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Đây là ví dụ blocking.MongoDB reactive cần `spring-boot-starter-data-mongodb-reactive`/ReactiveMongoOperations, Reactor và retry operator khác. Không tự đặt phiên bản khác BOM khi chưa kiểm thử.

### 6.2. URI lab

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/integration_lab
~~~

MongoDB local không có auth chỉ cho lab. Production cần secret management/TLS, least privilege, write concern phù hợp, timeout/pool, health checks và database/collection tách biệt. MongoDB Retryable Writes yêu cầu topology replica set hoặc sharded cluster, không hoạt động tương tự trên standalone.

### 6.3. Domain event và inbox record

~~~java
package example.mongoingest;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

public record IncomingTelemetry(
        String tenantId,
        String eventId,
        String deviceId,
        long sequence,
        BigDecimal temperatureC,
        Instant occurredAt) {
}

@Document(collection = "event_inbox")
public record InboxEvent(
        @Id String id,
        String tenantId,
        String eventId,
        String deviceId,
        long sequence,
        @Field(targetType = FieldType.DECIMAL128)
        BigDecimal temperatureC,
        Instant occurredAt,
        String status,
        Instant receivedAt) {
}
~~~

Trong Java thật, mỗi public top-level type đặt ở file `.java` riêng hoặc thay public tùy tổ chức package. `@Field(targetType=DECIMAL128)` giúp giữ giá trị thập phân theo BSON Decimal128; test converter/schema cụ thể. Không dùng `status`, `receivedAt` để xác định event content equality vì đây là **mutable metadata** khác nhau giữa những lần nhận.

### 6.4. Seed/test unique indexes

~~~javascript
use integration_lab

db.event_inbox.createIndex(
  { tenantId: 1, eventId: 1 },
  { unique: true, name: "uq_tenant_event" }
)

db.event_inbox.createIndex(
  { tenantId: 1, deviceId: 1, sequence: 1 },
  { unique: true, name: "uq_tenant_device_sequence" }
)
~~~

Tạo index trong migration trước khi traffic bắt đầu; không tạo/dropping indexes khi request đang retry. Đừng auto-create unique indexes trong production mà không đánh giá dữ liệu đã tồn tại. Nếu index thứ hai không phải ràng buộc nghiệp vụ (ví dụ device có thể phát sửa event cùng sequence), **không tạo nó**; bài dùng nó để minh họa E11000 từ index khác.

## 7. Handler idempotency: insert rồi đọc lại record

### 7.1. Enum kết quả và lỗi conflict

~~~java
package example.mongoingest;

public enum IngestOutcome {
    INSERTED,
    ALREADY_ACCEPTED
}
~~~

~~~java
package example.mongoingest;

public final class IngestConflictException
        extends RuntimeException {
    public IngestConflictException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

### 7.2. Service xử lý duplicate rõ ràng

~~~java
package example.mongoingest;

import java.time.Instant;
import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.stereotype.Service;

@Service
public class MongoInboxIngestService {

    private final MongoOperations mongo;

    public MongoInboxIngestService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public IngestOutcome ingest(IncomingTelemetry input) {
        validate(input);

        // Dùng cùng ID cho mọi lần retry/redelivery.
        String id = input.tenantId() + "|" + input.eventId();

        InboxEvent candidate = new InboxEvent(
            id,
            input.tenantId(),
            input.eventId(),
            input.deviceId(),
            input.sequence(),
            input.temperatureC(),
            input.occurredAt(),
            "RECEIVED",
            Instant.now());

        try {
            mongo.insert(candidate, "event_inbox");
            return IngestOutcome.INSERTED;
        } catch (DuplicateKeyException duplicate) {
            InboxEvent existing = mongo.findById(
                id, InboxEvent.class, "event_inbox");

            // Cùng _id mà record vẫn không thấy hoặc không khớp:
            // có thể do index khác, race, read consistency hoặc
            // conflict nghiệp vụ. Không ACK như success.
            if (existing == null || !sameBusinessEvent(
                    input, existing)) {
                throw new IngestConflictException(
                    "Event identity/content conflict", duplicate);
            }

            return IngestOutcome.ALREADY_ACCEPTED;
        }
    }

    private static boolean sameBusinessEvent(
            IncomingTelemetry input, InboxEvent stored) {
        return Objects.equals(input.tenantId(), stored.tenantId())
            && Objects.equals(input.eventId(), stored.eventId())
            && Objects.equals(input.deviceId(), stored.deviceId())
            && input.sequence() == stored.sequence()
            && stored.temperatureC() != null
            && input.temperatureC().compareTo(stored.temperatureC()) == 0
            && Objects.equals(input.occurredAt(), stored.occurredAt());
    }

    private static void validate(IncomingTelemetry input) {
        if (input == null
                || input.tenantId() == null
                || !input.tenantId().matches("[A-Za-z0-9_-]{1,64}")
                || input.eventId() == null
                || !input.eventId().matches("[A-Za-z0-9_-]{1,128}")
                || input.deviceId() == null
                || input.deviceId().isBlank()
                || input.sequence() < 0
                || input.temperatureC() == null
                || input.occurredAt() == null) {
            throw new IllegalArgumentException(
                "Invalid incoming telemetry");
        }
    }
}
~~~

**Giải thích code quan trọng:**

1. `mongo.insert(...)` được dùng vì inbox nhận event **bất biến**; không dùng `save` có thể overwrite state.
2. ID là `tenantId|eventId`, giữ nguyên khi retry. Regex trong ví dụ ngăn ký tự `|` gây ambiguity; production phải validate mọi nguồn dữ liệu và tenant authorization.
3. `DuplicateKeyException` **không bị retry**. Service đọc lại record theo ID ổn định.
4. Chỉ khi **toàn bộ business fields tương đương** mới trả `ALREADY_ACCEPTED`.
5. `status`/`receivedAt` không được so sánh: chúng là metadata của lần xử lý.
6. Nếu existing null mà có E11000, có thể do **index khác**, sai ID hoặc read consistency; coi là conflict/needs investigation.
7. Nếu record có cùng ID nhưng payload khác, throw `IngestConflictException`, không nuốt lỗi.
8. `temperatureC.compareTo(...)` là so sánh giá trị số; nếu business muốn bảo toàn chính xác cả scale (ví dụ 26.50 khác 26.5), dùng chuẩn canonical của domain và nhất quán khi serialize.
9. MongoDB readback ở đây cần dùng cùng MongoDB primary/consistent context phù hợp; nếu ứng dụng cấu hình đọc secondary lag, một E11000 có thể xuất hiện trước khi readback thấy record. Xem mục retry ambiguity.

**Lưu ý thiết kế:** service trả `ALREADY_ACCEPTED` khi record đã tồn tại và payload khớp, ngay cả khi `status=RECEIVED/PROCESSING`. Điều đó chỉ có nghĩa **đã bền hóa ở inbox**, không khẳng định downstream đã xử lý xong. Nếu API cần `ALREADY_PROCESSED` thì phải kiểm tra trạng thái DONE và side effect đích.

## 8. Race giữa hai worker: unique index là điểm phân xử

Cả hai worker cùng đọc `evt-1001` trước khi database có record:

~~~mermaid
sequenceDiagram
    participant A as Instance A
    participant B as Instance B
    participant D as MongoDB
    A->>D: insert(_id=tenant-a|evt-1001)
    B->>D: insert(_id=tenant-a|evt-1001)
    D-->>A: Inserted
    D-->>B: E11000
    B->>D: findById(tenant-a|evt-1001)
    D-->>B: matching canonical event
    Note over A,B: Chỉ một inbox document được tạo
~~~

Đây là **atomic uniqueness tại MongoDB index**, không phải distributed mutex cho toàn bộ business pipeline. A có thể insert xong rồi crash trước khi phát Kafka; B có thể trả ALREADY_ACCEPTED nhưng **không** đảm nhận gửi lại ngay. Vì vậy cần **worker đọc inbox PENDING và xử lý có retry/lease**, hoặc transactional outbox gắn với thay đổi nghiệp vụ.

### 8.1. Vì sao exists() trước insert không ngăn race?

~~~java
// Sai nếu dùng làm cơ chế chống trùng duy nhất.
if (!mongo.exists(queryByEventId, InboxEvent.class)) {
    mongo.insert(candidate, "event_inbox");
}
~~~

Giữa `exists` và `insert`, worker khác có thể đã insert. **Unique index và catch/compare** là cơ chế cuối cùng. Pre-check có thể hữu ích để tối ưu một số read-heavy workload, nhưng không thay thế constraint.

### 8.2. Không lấy Spring Message ID làm event ID

Spring Integration tạo `MessageHeaders.ID` khác nhau khi một event được bọc/gửi lại ở các flow khác. Nếu dùng `message.getHeaders().getId()` làm unique key, redelivery có thể thành hai record khác nhau. Dùng business event ID từ nguồn/tầng ingest được giữ nguyên.

### 8.3. Duplicate key là cơ chế nhận diện, không phải cleanup

Không xóa document cũ sau E11000 chỉ để retry insert: hành động đó có thể xóa một event đã xử lý hoặc record đang thuộc worker khác. Nếu business muốn sửa event đã được gửi, thiết kế **correction event mới có ID khác** hoặc quy trình versioned update có điều kiện.
## 9. Bảng quyết định retry: lỗi nào nên thử lại?

**Không dùng `catch(Exception) { retry(); }` cho MongoDB.** Retry có thể làm một lỗi cấu hình/sai dữ liệu lặp vô hạn hoặc tạo thêm side effects khi kết quả lần trước chưa rõ.

| Loại lỗi | Ví dụ Java/driver | Quyết định mặc định | Lý do |
|---|---|---|---|
| Unique constraint | `DuplicateKeyException` / code 11000 | **Không retry insert mù**; đọc lại và phân loại | Ràng buộc dữ liệu sẽ không tự biến mất |
| Duplicate với payload trùng | Record đã tồn tại đúng business fields | `ALREADY_ACCEPTED` | Idempotent repeat |
| Duplicate khác payload | Cùng ID, business data khác | `CONFLICT`, quarantine/HTTP 409 | Cần xử lý nguồn hoặc nghiệp vụ |
| Schema/validation | `IllegalArgumentException`, mapping error | Không retry tự động | Dữ liệu sẽ không tự sửa |
| Authentication/authorization | Mongo auth/permission denied | Không retry liên tục | Cần sửa credential/role |
| Thao tác tạm thời unavailable | Failover, node selection, network transient | Retry **có giới hạn** nếu an toàn | Hệ thống có thể hồi phục |
| Lock/write conflict | Lỗi conflict tạm thời phù hợp MongoDB semantics | Retry transaction/operation có policy | Cạnh tranh trạng thái |
| Write concern timeout | `wtimeout`/missing majority ACK | **UNKNOWN**, reconcile cùng ID | Write có thể đã áp dụng |
| Network timeout sau write | Socket timeout/lost response | **UNKNOWN**, cùng ID rồi đối soát | Không đủ bằng chứng chưa ghi |
| Transaction commit unknown | `UnknownTransactionCommitResult` | Theo protocol retry **commit**/reconcile | Có thể transaction đã commit |
| Retryable transaction transient | `TransientTransactionError` | Có thể retry toàn transaction nếu an toàn | Transaction có thể được thực hiện lại |
| Database full/quota | Write errors/resource exhaustion | Cảnh báo/khắc phục trước khi retry nhiều | Retry mù làm quá tải |
| Downstream Kafka/HTTP timeout | Publish result không rõ | Reconcile broker/destination với event ID | Không phải MongoDB insert failure |

### 9.1. Ba nguyên tắc retry

1. **Phân loại lỗi đúng.** Spring Data exception translation thường hữu ích, nhưng driver errors có thể bị bọc trong `MessagingException` hoặc một exception của framework.
2. **Chỉ retry operation idempotent hoặc có reconciliation.** Nếu side effect không thể lặp an toàn, không tự động retry khi result unknown.
3. **Có ngân sách retry.** Max attempts, backoff+jitter, deadline, circuit breaker, DLQ/recovery và monitoring.

### 9.2. TransientDataAccessException không bao gồm mọi lỗi network

Spring Data có nhiều nhánh `DataAccessException`: một số sự cố resource/connection có thể bị translate sang loại khác hoặc đi lên qua raw MongoDB driver exception. Nếu cấu hình retry chỉ `TransientDataAccessException`, **đó là một tập con bảo thủ**, không phải bộ phân loại đầy đủ mọi lỗi tạm thời.

Đừng dùng `DataAccessException.class` làm retryable catch-all; nó có thể bao gồm cả `DuplicateKeyException`, `DataIntegrityViolationException` hoặc exception vĩnh viễn khác. Nên viết exception classifier theo version driver/Spring Data và test cause chain.

### 9.3. Retry không thể thay business reconciliation

Khi MongoDB đã ghi nhưng timeout response, một lần retry `insert` cùng ID có thể trả E11000. **Không biến E11000 thành lỗi vĩnh viễn ngay lập tức** nếu ứng dụng có cơ chế kiểm tra record trùng nội dung và đã được chấp nhận; nhưng cũng không biến tất cả E11000 thành success.

## 10. Driver Retryable Writes và application retry khác nhau

MongoDB Java driver hỗ trợ **Retryable Writes** cho một số write operations, khi topology và write concern đáp ứng điều kiện. Với driver hiện đại, tính năng này thường bật mặc định trong replica set/sharded cluster.

Ví dụ URI thử nghiệm:

~~~text
mongodb://mongo-test:27017/integration_lab?replicaSet=rs0&retryWrites=true&w=majority
~~~

URI chỉ minh họa; replica set phải tồn tại và tên đúng. Không khai `retryWrites=true` trên standalone rồi coi như sẽ có cùng behavior.

### 10.1. Driver làm gì?

Khi một operation thuộc nhóm retryable gặp lỗi network hoặc không tìm thấy primary khỏe, driver có thể **thử lại một lần** theo protocol MongoDB, với logical session/transaction number phù hợp. Đây là cơ chế **phía driver/server**, khác vòng lặp gọi lại business service do Spring Integration.

| Cơ chế | Ai điều khiển? | Có thể lặp phần nào? | Điều cần nhớ |
|---|---|---|---|
| **Driver retryable write** | MongoDB driver | Một write operation đủ điều kiện theo protocol | Thường retry một lần; topology/ack requirements |
| **Spring Retry** | `RetryTemplate` / advice | Method/message handler | Có thể chạy lại cả business handler |
| **Broker redelivery** | Kafka/JMS/AMQP container | Một nguồn message | Có thể xảy ra sau process crash |
| **HTTP client retry** | Client/proxy | Toàn bộ API request | Cần Idempotency-Key |
| **Mongo transaction retry** | Driver/API/ứng dụng | Transaction body hoặc commit theo error label | Không nhầm retry whole transaction với retry commit |

**Một event có thể trải qua cả năm tầng retry**. Nếu mỗi tầng đều retry nhiều lần không budget, số attempts nhân lên và tạo retry storm.

### 10.2. Driver Retryable Writes không retry mọi loại lỗi

- **`w:0` unacknowledged writes** không thuộc retryable writes protocol.
- Standalone deployment không hỗ trợ cơ chế giống replica set/sharded cluster.
- Writes **bên trong một multi-document transaction** không được retry riêng lẻ như outside-transaction writes.
- **Commit/abort transaction** có retry semantics riêng; driver có thể thử lại commit/abort ngay cả khi `retryWrites=false`.
- **E11000 duplicate key** không phải một sự cố kết nối transient chỉ vì tên chứa “key”; lỗi xác định unique constraint.

Từ MongoDB **6.1**, error label `NoWritesPerformed` có thể giúp nhận diện tình huống cả hai lần thử retryable write đều thất bại và **không có write nào được thực hiện**. Nếu không có label này, **không suy ra ngược lại rằng đã ghi**; chỉ biết không có bằng chứng “zero writes” từ label. Cần đối soát business key nếu outcome không rõ.

### 10.3. Nếu đã có driver retry, có cần Spring Retry?

Có thể cần, nhưng phục vụ lớp khác. Ví dụ:

- Driver retry một lần trong thời gian network failover ngắn.
- Spring Retry áp vài attempts khi service nhận exception transient đã được dịch, với backoff.
- Broker redeliver sau restart nếu message chưa ACK.

Chúng phải dùng **cùng business event ID**, cùng idempotency semantics và budget tổng hợp. Trong luồng có SLA thấp, có thể **không** retry đồng bộ dài tại request thread; chuyển thành durable queue/retry scheduling.

## 11. Spring Integration RequestHandlerRetryAdvice

Spring Integration có `org.springframework.integration.handler.advice.RequestHandlerRetryAdvice`, bọc một **MessageHandler** để thử lại khi handler ném exception.

Trong Spring Integration 6.x, advice có thể dùng `RetryTemplate` từ `spring-retry`.

### 11.1. Bean RetryAdvice chỉ retry lỗi transient

~~~java
package example.mongoingest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.dao.TransientDataAccessException;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class MongoRetryAdviceConfig {

    @Bean("mongoTransientRetryAdvice")
    public RequestHandlerRetryAdvice mongoTransientRetryAdvice() {

        RetryTemplate template = RetryTemplate.builder()
            .maxAttempts(3)
            .exponentialBackoff(200L, 2.0, 2000L, true)
            .retryOn(TransientDataAccessException.class)
            .traversingCauses()
            .build();

        RequestHandlerRetryAdvice advice =
                new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        // Không set RecoveryCallback ở đây:
        // sau 3 attempts exception được propagate cho nguồn.
        return advice;
    }
}
~~~

**Giải thích:**

- `maxAttempts(3)` = **1 lần đầu + tối đa 2 lần retry**, không phải 3 retries sau lần đầu.
- Backoff có jitter để giảm hai worker đồng loạt đánh vào MongoDB.
- `retryOn(TransientDataAccessException.class)` là bộ phân loại **bảo thủ**, không bao quát mọi MongoDB driver error.
- `traversingCauses()` quan trọng vì Spring Integration có thể bọc lỗi gốc trong `MessagingException`.
- `DuplicateKeyException` **không** được retry theo policy này vì nó không thuộc subclass transient đã chọn.
- Không có `RecoveryCallback`, exception sau khi hết attempts đi tiếp cho upstream/error channel theo cấu hình.
- Advice stateless này tạm giữ thread giữa attempts; với traffic cao và backoff dài, cân nhắc retry scheduling ngoài thread thay vì nhân số blocked consumers.

### 11.2. Service activator được bọc advice

~~~java
package example.mongoingest;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class MongoInboxEndpoint {

    private final MongoInboxIngestService service;

    public MongoInboxEndpoint(MongoInboxIngestService service) {
        this.service = service;
    }

    @ServiceActivator(
        inputChannel = "mongoIngestRequests",
        adviceChain = "mongoTransientRetryAdvice")
    public IngestOutcome handle(IncomingTelemetry input) {
        return service.ingest(input);
    }
}
~~~

Trong cùng Spring context, `MongoInboxIngestService` sẽ trả INSERTED/ALREADY_ACCEPTED hoặc ném conflict/exception. Advice chỉ retry transient lỗi **sau khi handler được gọi**, theo danh sách exception đã chọn.

**Đừng đặt thêm một retry advice bừa bãi trên mọi downstream handler**: nếu một handler đã phát Kafka rồi sau đó exception khi log/commit, retry nguyên handler có thể phát Kafka nhiều lần.

### 11.3. @MessagingGateway tạo request/reply đồng bộ

~~~java
package example.mongoingest;

import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface MongoInboxGateway {

    @Gateway(
        requestChannel = "mongoIngestRequests",
        replyTimeout = 5000)
    IngestOutcome ingest(IncomingTelemetry event);
}
~~~

Cần đăng ký gateway interface qua `@IntegrationComponentScan` hoặc cấu hình tương đương. Khi gọi:

~~~java
IngestOutcome outcome = gateway.ingest(event);
~~~

Caller được trả kết quả service theo request/reply, **nếu flow thực sự đồng bộ và không bị chuyển qua async channel**. `replyTimeout` giới hạn thời gian caller đợi reply, không tự rollback MongoDB write. Nếu caller hết timeout nhưng DB đã ghi, retry cùng event ID dẫn tới duplicate được nhận diện.

### 11.4. RetryAdvice có thể đi cùng Java DSL

Thay cho `@ServiceActivator`, một IntegrationFlow có thể dùng:

~~~java
@Bean
public IntegrationFlow mongoIngestFlow(
        MongoInboxIngestService service,
        RequestHandlerRetryAdvice mongoTransientRetryAdvice) {

    return IntegrationFlow.from("mongoIngestRequests")
        .handle(service, "ingest",
            endpoint -> endpoint.advice(
                mongoTransientRetryAdvice))
        .get();
}
~~~

**Đây là phương án thay thế** annotation endpoint ở mục 11.2. Không đăng ký cả hai consumer cùng nhận `mongoIngestRequests` rồi kỳ vọng mỗi message chắc chắn tới cùng một service theo thứ tự. Trong Java DSL, ref/method resolution và reply channel tuân theo Spring Integration message handler contract.

## 12. Recovery channel, error channel và ACK

Sau khi hết số lần retry:

- **Không có RecoveryCallback:** exception được ném lên caller hoặc error flow theo channel/endpoint. Với JMS/Kafka, container quyết định rollback/redelivery dựa trên lỗi và config.
- **Có RecoveryCallback gửi ErrorMessage:** lỗi có thể được chuyển sang recovery channel; tùy callback, lỗi **được xử lý** và không còn propagate như trước.
- **Có durable DLQ/quarantine được xác nhận:** có thể quyết định ACK nguồn sau khi đã lưu bền bản lỗi theo business policy.
- **Chỉ ghi log rồi return:** không đủ khi dữ liệu không được phép mất.

### 12.1. ErrorMessageSendingRecoverer

Spring Integration hỗ trợ:

~~~java
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;

RequestHandlerRetryAdvice advice =
        new RequestHandlerRetryAdvice();

advice.setRetryTemplate(retryTemplate);
advice.setRecoveryCallback(
        new ErrorMessageSendingRecoverer(
            recoveryMessageChannel));
~~~

Đây là fragment với `retryTemplate`/`recoveryMessageChannel` đã được inject/khởi tạo. **Hệ quả quan trọng:** khi recovery callback gửi lỗi sang channel rồi trả về bình thường, upstream có thể xem handler đã hoàn tất. Nếu recovery channel chỉ là `QueueChannel` in-memory hoặc handler chỉ log, **không có durable guarantee** để ACK nguồn.

Nếu cần không mất event:

1. Consumer của recovery channel phải lưu bền retry/dead-letter (hoặc lỗi phải tiếp tục propagate để broker redeliver).
2. Xác định fallback khi recovery channel bị đầy/down.
3. Không đưa payload nhạy cảm nguyên bản vào log/DLQ thiếu phân quyền.
4. Chỉ ACK original sau khi durable recovery đã được xác nhận.
5. Kiểm soát error-channel loop (handler lỗi gửi lỗi về chính channel đang lỗi).

### 12.2. XML retry advice

Spring Integration XML (mẫu tùy phiên bản 6.x):

~~~xml
<int:service-activator
        input-channel="mongoIngestRequests"
        ref="mongoInboxEndpoint"
        method="handle">
    <int:request-handler-advice-chain>
        <ref bean="mongoTransientRetryAdvice"/>
    </int:request-handler-advice-chain>
</int:service-activator>
~~~

Cấu hình này là **phương án thay thế annotation endpoint**, bean `mongoInboxEndpoint` và `mongoTransientRetryAdvice` phải tồn tại. Cần khai báo XML namespace/schema `int` đúng version và các channels. Mẫu dùng Java bean advice để giữ **exception classifier** của retry template; không chỉ thêm XML handler-retry-advice mặc định cho mọi exception rồi hy vọng DuplicateKeyException bị loại.

### 12.3. Error channel không đồng nghĩa broker dead-letter

Một `ErrorMessage` trên `errorChannel` là **Spring Message chứa exception**, không phải bảo đảm broker nhận message đã được dead-letter. Để không mất dữ liệu, recovery flow phải có một bước ghi bền/ACK phù hợp.

Nếu error consumer ném exception, cần kiểm tra nó propagate đi đâu, tránh vòng lặp vô hạn và tránh ACK upstream trước khi xử lý recovery xong.

## 13. Stateful retry và broker redelivery

Spring Integration phân biệt:

- **Stateless retry:** thử lại ngay trong cùng handler invocation, giữ call stack/thread giữa attempts.
- **Stateful retry:** lưu retry state theo **stable key**, ném exception để **nguồn** (JMS/Kafka/AMQP...) có cơ hội redeliver, lần sau tiếp tục bộ đếm/backoff.

### 13.1. Vì sao stateful retry hữu ích?

Ví dụ JMS listener nhận một order event. Nếu DB failover và xử lý phải thử lại, ta có thể để JMS transaction rollback để broker redeliver sau; không cần giữ một thread trong một sleep dài tại MongoDB handler.

Tuy nhiên:

- Một stable state key phải dựa trên business event ID/message identity có tính ổn định của nguồn, không dựa vào mỗi Spring Message UUID mới.
- Spring Integration 6.x và 7.x có các method/API cấu hình stateful retry khác nhau; cần đối chiếu Javadoc của version.
- Stateful retry cache có giới hạn và thường là in-memory; không tự tạo durable exactly-once.
- Broker redelivery policy, max delivery count và dead-letter queue phải được phối hợp với retry state.
- Không nhân số attempts vô hạn bằng cách bật cùng lúc retry advice dài, broker redelivery vô hạn và HTTP client retry vô hạn.

### 13.2. Một kế hoạch hợp lý theo lớp

~~~text
MongoDB driver retry (mức driver, operation đủ điều kiện)
        ↓
Spring Integration handler retry (2–3 attempts, transient only)
        ↓
Exception propagate nếu vẫn lỗi
        ↓
Broker nack/rollback → redelivery có delay/backoff + DLQ
        ↓
Durable retry/quarantine & operational reconciliation
~~~

Phân bổ **time budget**. Ví dụ API HTTP có deadline 3 giây sẽ không đủ cho 3 attempts × 2 giây + Mongo driver server selection delay. Khi traffic lớn, chọn retry bất đồng bộ có lưu bền thay cho kéo dài latency request.

## 14. Retry transaction không đồng nghĩa retry riêng từng insert

Trong multi-document MongoDB transaction:

- Mọi operations phải cùng `ClientSession`/transaction context.
- Write concern áp ở **cấp transaction**, không áp riêng mỗi insert.
- Lỗi trước commit có thể khiến transaction abort.
- Commit response có thể chưa rõ; không tự phát lại toàn bộ external side effect.
- MongoDB có error labels như `TransientTransactionError` và `UnknownTransactionCommitResult`.
- MongoDB 8.1 trở đi: **upsert duplicate key trong transaction không tự được server retry** theo hành vi được tài liệu hóa.

### 14.1. Một transaction ghi event + outbox

~~~java
@Service
public class OrderEventApplicationService {

    private final MongoOperations mongo;

    public OrderEventApplicationService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void appendOrderAndOutbox(
            OrderRecord order, OutboxEvent outbox) {

        mongo.insert(order, "orders");
        mongo.insert(outbox, "outbox_events");
        // Không publish Kafka trước khi transaction commit.
    }
}
~~~

Đây là **fragment** cần classes `OrderRecord`, `OutboxEvent` và bean `MongoTransactionManager` ở cùng MongoDatabaseFactory. Transactions cần MongoDB topology hỗ trợ (thường replica set). `DuplicateKeyException` từ một insert có thể làm transaction fail/abort; không tự bắt rồi tiếp tục dùng transaction session đã lỗi để thử lại insert.

### 14.2. Unknown commit result

~~~mermaid
sequenceDiagram
    participant I as Integration service
    participant M as MongoDB
    I->>M: insert order + outbox in txn
    I->>M: commitTransaction()
    M->>M: commit xong
    M--xI: commit ACK thất lạc
    Note over I: UnknownTransactionCommitResult
    I->>M: retry commit theo driver protocol / reconcile business keys
~~~

Khi commit outcome chưa rõ, **không gọi lại business side effects ngoài MongoDB** như gửi email/Kafka trong transaction callback. Theo driver transaction retry protocol, sau đó đọc lại trạng thái bằng business keys và kiểm tra outbox. Khi một operation trong transaction bị lỗi transient trước commit, retry lại toàn transaction chỉ an toàn nếu transaction body **không có side effect ngoài database**.

### 14.3. @Transactional và RetryAdvice nesting

Vị trí áp advice/transaction quyết định một attempt dùng session mới hay chạy trong transaction hiện tại. Ví dụ:

- Retry **bên ngoài** service transactional: mỗi attempt có thể mở transaction mới.
- Retry **bên trong** transaction: lỗi có thể đánh dấu transaction rollback-only; retry một insert trong cùng session không tạo transaction sạch.
- Async `QueueChannel` tách thread, nên transaction context imperative không tự truyền sang worker khác.
- Self-invocation `this.method()` có thể bỏ qua Spring AOP `@Transactional`.

Cần test integration thật để biết **attempt boundary** và commit/abort. Không mặc định thêm cả `@Retryable` + `@Transactional` + Integration RetryAdvice là an toàn.

## 15. Reactive MongoDB: onErrorResume, retryWhen và duplicate comparison

Với `ReactiveMongoOperations`, lỗi xảy ra trong publisher **khi được subscribe**, không nhất thiết lúc gọi method tạo `Mono`.

### 15.1. Retry chỉ transient, không retry duplicate

~~~java
package example.mongoingest;

import java.time.Duration;

import org.springframework.dao.TransientDataAccessException;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public final class ReactiveInboxWriter {

    private final ReactiveMongoOperations mongo;

    public ReactiveInboxWriter(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }

    public Mono<InboxEvent> insertWithTransientRetry(
            InboxEvent event) {

        return mongo.insert(event, "event_inbox")
            .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200))
                    .maxBackoff(Duration.ofSeconds(2))
                    .filter(error ->
                        error instanceof TransientDataAccessException));
    }
}
~~~

**`Retry.backoff(2, ...)` cho phép 2 retries sau initial subscription**, khác cách đặt `maxAttempts(3)` của Spring Retry. Mẫu này cũng chỉ là **classifier bảo thủ**, cần mở rộng cho driver failures phù hợp sau khi kiểm thử. `DuplicateKeyException` không được retry.

### 15.2. Phân loại duplicate trong một reactive chain

~~~java
public Mono<IngestOutcome> insertOrRecognize(
        IncomingTelemetry input) {

    validate(input); // Reuse validation của service đồng bộ.

    InboxEvent candidate = buildCandidate(input);

    return mongo.insert(candidate, "event_inbox")
        .thenReturn(IngestOutcome.INSERTED)
        .onErrorResume(
            DuplicateKeyException.class,
            duplicate -> mongo.findById(
                    candidate.id(),
                    InboxEvent.class,
                    "event_inbox")
                .flatMap(existing -> {
                    if (sameBusinessEvent(input, existing)) {
                        return Mono.just(
                            IngestOutcome.ALREADY_ACCEPTED);
                    }
                    return Mono.error(new IngestConflictException(
                        "Event identity/content conflict",
                        duplicate));
                })
                .switchIfEmpty(
                    Mono.error(new IngestConflictException(
                        "Duplicate key on another index or unseen record",
                        duplicate))));
}
~~~

Đây là **fragment** của class `ReactiveInboxWriter` cần thêm imports `DuplicateKeyException`, `Mono` và định nghĩa `validate/buildCandidate/sameBusinessEvent` giống sync service ở mục 7. Để đảm bảo tính nhất quán, không dùng raw DTO chưa xác thực hoặc một read preference tới secondary lag khi reconcile.

### 15.3. Không nuốt onError

~~~java
// Sai nếu business cần ghi bền:
return mongo.insert(event)
    .onErrorResume(e -> Mono.empty())
    .then();
~~~

Bất kỳ lỗi network/DB nào cũng có thể biến thành `onComplete` để upstream ACK nhầm. Nếu muốn fallback, phải bền hóa vào durable retry/dead-letter store hoặc propagate lỗi.

### 15.4. Mono retry khác transaction retry

Nếu Mono được đặt trong `TransactionalOperator`, thứ tự operator `retryWhen` và `as(tx::transactional)` quyết định có retry **toàn transaction** hay chỉ một operation trong cùng transaction. Không thêm `retryWhen` bừa bên trong transaction đã bị lỗi.

Với `ReactiveMongoTransactionManager`, operations trong cùng transaction cần compose theo thứ tự/serialization phù hợp driver; đừng mặc định dùng concurrent `flatMap` trên cùng session.

## 16. Bulk insert: partial success và duplicate theo index

MongoDB bulk/insertMany có thể xử lý nhiều documents trong một operation. Khi một record trùng unique key:

- **Ordered bulk** thường dừng tại lỗi đầu tiên theo thứ tự; phần trước lỗi có thể đã ghi.
- **Unordered bulk** tiếp tục xử lý các operations khác khi có thể; thứ tự không được bảo đảm.
- Nếu không bọc trong transaction phù hợp, một exception **không** tự rollback những records đã insert thành công.
- Một `MongoBulkWriteException` có thể chứa danh sách write errors kèm index của operation, code `11000`, và kết quả đã hoàn thành.
- Đừng catch một bulk exception rồi retry **toàn batch với ID mới**.
- Nếu retry toàn batch giữ nguyên business IDs, nhiều records đã ghi có thể tạo thêm E11000; cần reconcile **từng item**.

### 16.1. Demo mongosh

~~~javascript
use integration_lab

db.bulk_events.insertMany(
  [
    { _id: "evt-a", status: "NEW" },
    { _id: "evt-a", status: "NEW" },
    { _id: "evt-b", status: "NEW" }
  ],
  { ordered: false }
)
// Có E11000 ở phần tử thứ hai, nhưng evt-a và evt-b
// có thể đã được insert thành công.
~~~

Không giả định index trả về trong exception đồng nghĩa thứ tự commit giữa shards. Với workload lớn, giữ **result per eventId** hoặc một inbox status để đối soát.

### 16.2. Không dùng một retry policy chung cho bulk

Một `insertMany` gồm 1000 sự kiện là 1000 business units. Lỗi ở document thứ 17 không nhất thiết làm 999 events còn lại thất bại. Thiết kế retry/ack theo **đơn vị nghiệp vụ**, không chỉ “batch HTTP thành công/thất bại”.
## 17. MongoDbStoringMessageHandler không tự “ignore duplicate”

Spring Integration MongoDB outbound channel adapter dùng `MongoDbStoringMessageHandler` ghi payload vào collection theo `MongoOperations`. Thông thường nó dùng `save` semantics, không phải một cơ chế **insert-only + catch E11000 + đối chiếu payload**.

### 17.1. Java DSL writer đơn giản

~~~java
package example.mongoingest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.MongoOperations;

@Configuration
@EnableIntegration
public class MongoRawWriterConfig {

    @Bean
    public IntegrationFlow rawMongoWriter(MongoOperations mongo) {
        return IntegrationFlow.from("mongoRawWrites")
            .handle(
                MongoDb.outboundChannelAdapter(mongo)
                    .collectionName("event_inbox"))
            .get();
    }
}
~~~

**Đây là flow demo**, không dùng làm thay thế `MongoInboxIngestService` nếu nghiệp vụ cần insert-only và phân biệt INSERTED / ALREADY_ACCEPTED / CONFLICT. Một source file hoặc HTTP request lặp lại có thể khiến `save` overwrite document cũ. Với write concern cụ thể, cấu hình `MongoTemplate`/driver; `MessageChannel` không tự có thuộc tính write concern.

### 17.2. Khi nào dùng service thay cho storing adapter?

Nếu business phải phân loại E11000:

1. Producer gửi `Message<IncomingTelemetry>` tới endpoint.
2. Endpoint validate/authorize, gọi `MongoInboxIngestService.ingest(...)`.
3. Service dùng `insert` + unique constraint + so sánh record sau DuplicateKeyException.
4. Service trả outcome rõ ràng hoặc throw conflict.
5. Retry advice chỉ thử lại những lỗi transient đã phân loại.
6. ACK nguồn dựa trên **durable outcome**, không dựa vào channel đã nhận message.

`MongoDbOutboundGateway` phù hợp **đọc query request/reply**, không phải writer insert-only. Có thể dùng gateway để readback, nhưng một gateway call riêng không mặc định nằm trong cùng MongoDB session/transaction với write trước đó.

## 18. MongoDbMessageSource polling và duplicate

Spring Integration MongoDB inbound adapter sử dụng `MongoDbMessageSource` được poller gọi `receive()` theo lịch.

~~~mermaid
flowchart LR
    P["Poller"] --> M["MongoDbMessageSource"]
    M --> Q["find(status=NEW, limit=50)"]
    Q --> L["Message<List<InboxEvent>>"]
    L --> S["Splitter"]
    S --> H["Business handler"]
    H --> D["Kafka / HTTP / DB"]
~~~

Theo cấu hình blocking mặc định với `expectSingleResult(false)`, source có thể trả **một `Message<List<T>>`**. Nó không tự ghi nhớ những document đã poll và không tự đánh dấu DONE.

### 18.1. Query limit và poller limit khác nhau

~~~text
fixedDelay(5000)
maxMessagesPerPoll(1)
Query.limit(50)
~~~

Điều đó chỉ giới hạn **một lần source receive trong mỗi poll** và **tối đa 50 MongoDB documents/query**, không làm lần poll kế tiếp tự chọn 50 documents mới. Nếu query vẫn có `status=NEW`, cùng event có thể được đọc lại.

### 18.2. updateExpression không chứng minh business đã xử lý xong

~~~java
MongoDb.inboundChannelAdapter(
        mongo,
        "{ 'status': 'NEW' }")
    .collectionName("event_inbox")
    .entityClass(InboxEvent.class)
    .update(new Update().set("status", "CLAIMED"));
~~~

Đây là builder fragment cần gắn vào IntegrationFlow có poller. Nếu hai worker cùng query NEW trước update, cả hai vẫn có thể nhận cùng document. Nếu app crash sau CLAIMED trước publish Kafka, event có thể kẹt. **CLAIMED không bằng DONE**; cần owner/lease/attempt, recovery và idempotent downstream.

### 18.3. Unique insert và atomic claim là hai bài toán khác nhau

- **Unique inbox insert:** không tạo hai records cho cùng business event ID.
- **Atomic work claim:** chỉ một worker đang giữ quyền xử lý một work item tại một thời điểm, thường qua conditional `findAndModify`.
- **Idempotent downstream:** ngay cả khi publish/redelivery sau crash, không tạo business side effect trùng.
- **Durable outbox:** có bản ghi bền cho bước cần publish, không phụ thuộc process memory.

## 19. ACK policy theo nguồn dữ liệu

| Nguồn | Khi nào ACK nếu yêu cầu bền hóa inbox? | Thất bại thì làm gì? |
|---|---|---|
| HTTP API | Sau MongoDB insert/đối chiếu đã xác nhận | Client retry cùng Idempotency-Key |
| Kafka consumer | Sau durable processing theo contract | Container retry/seek/DLT nếu chưa commit offset |
| JMS queue | Sau durable state/transaction nghiệp vụ | Rollback session/nack nếu DB chưa thành công |
| AMQP/RabbitMQ | Sau durable state | Nack/requeue có budget, DLX theo policy |
| File inbound | Sau khi parse/ghi durable inbox | Quarantine/move theo trạng thái, không xóa file quá sớm |
| SFTP inbound | Sau khi download và lưu nội dung/marker có recovery | Retry transfer/handler, tránh mất khi filter seen sớm |
| MongoDB polling | Sau claim/business state đúng contract | Retry, lease expiry, owner/version |

**Bảng là nguyên tắc kiến trúc**, không phải tất cả adapters đều có cùng API ACK. Cần kiểm tra đặc tính của Kafka/JMS/AMQP/file/SFTP adapter, transaction threading, error channel và recovery handler theo version.

### 19.1. HTTP Idempotency-Key

~~~text
POST /telemetry
Idempotency-Key: evt-1001

Body: { "tenantId":"tenant-a", "eventId":"evt-1001", ... }
~~~

Server xác thực tenant và ràng buộc key với canonical request body. Same key + same business payload có thể trả outcome tương đương; same key + khác payload trả HTTP 409/conflict. Không tự tin một header do client gửi mà không kiểm soát quyền.

### 19.2. Kafka/JMS và khoảng trống ACK

Nếu consumer commit Kafka offset hoặc JMS ACK **trước** MongoDB inbox write hoàn tất, process crash có thể làm mất event. Nếu ACK **sau**, process crash giữa MongoDB ACK và broker ACK có thể gây redelivery, nhưng unique ID giúp ingest idempotent.

Một `@Transactional("mongoTransactionManager")` chỉ quản lý MongoDB session, **không tự commit JMS/Kafka transaction**. Producer Kafka idempotence cũng không thay thế idempotency của business effect xuyên MongoDB.

### 19.3. File/SFTP/UDP có đặc tính khác broker

File/SFTP dùng remote/local filters, file move/rename và trạng thái nguồn; không có mặc định cùng semantics broker ACK. UDP là best-effort, không có broker redelivery. Cần replay/recovery theo contract nguồn, không mong unique MongoDB index làm nguồn tự gửi lại dữ liệu bị mất.

## 20. Transactional outbox và duplicate ở đích

Một pipeline tin cậy có thể dùng MongoDB transaction để ghi **business state + outbox event**:

~~~mermaid
sequenceDiagram
    participant P as Source
    participant I as Ingest
    participant DB as MongoDB
    participant W as Outbox worker
    participant B as Broker
    participant C as Consumer
    P->>I: evt-1001
    I->>DB: transaction insert inbox + outbox
    DB-->>I: commit ACK
    I-->>P: accepted
    W->>DB: atomic claim eventId
    W->>B: publish eventId
    B-->>W: broker ACK
    W->>DB: conditional mark SENT
    B->>C: eventId
    C->>C: unique dedup + business effect
~~~

### 20.1. Vì sao outbox vẫn có thể publish trùng?

Outbox worker có thể publish thành công nhưng crash **trước khi đánh dấu SENT**. Sau khi lease hết hạn, worker khác gửi lại. Vì vậy outbox thường mang **at-least-once delivery**, consumer phải deduplicate theo cùng event ID hoặc có idempotent effect.

### 20.2. Unique key không thay thế transaction

Một unique inbox key có thể ngăn hai records cho một event; nó **không làm hai lệnh insert inbox + outbox tự atomic**. Khi cần hai collections commit/abort cùng nhau, dùng `MongoTransactionManager` cùng MongoDatabaseFactory trên deployment hỗ trợ transaction. MongoDB transaction vẫn **không commit Kafka/JMS/HTTP**.

### 20.3. Lỗi payload conflict ở outbox

Nếu event ID cũ được tái sử dụng với nội dung mới, đó là business conflict, không phải một duplicate được phép tự bỏ qua. Dùng correction event ID/version riêng hoặc quy trình cập nhật nghiệp vụ được kiểm soát; không xóa unique constraint để “làm sạch lỗi”.

## 21. Kiểm thử unit: cùng payload, payload khác và retry policy

### 21.1. Kiểm thử INSERTED và ALREADY_ACCEPTED

~~~java
package example.mongoingest;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoOperations;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class MongoInboxIngestServiceTest {

    private IncomingTelemetry event() {
        return new IncomingTelemetry(
            "tenant-a", "evt-1001", "node-7", 1001L,
            new BigDecimal("26.5"),
            Instant.parse("2026-11-23T02:00:00Z"));
    }

    @Test
    void firstInsertReturnsInserted() {
        MongoOperations mongo = mock(MongoOperations.class);
        MongoInboxIngestService service =
                new MongoInboxIngestService(mongo);

        assertEquals(IngestOutcome.INSERTED,
                service.ingest(event()));

        verify(mongo).insert(
            any(InboxEvent.class), eq("event_inbox"));
    }

    @Test
    void sameEventAfterDuplicateIsAlreadyAccepted() {
        MongoOperations mongo = mock(MongoOperations.class);
        MongoInboxIngestService service =
                new MongoInboxIngestService(mongo);

        doThrow(new DuplicateKeyException("E11000"))
            .when(mongo)
            .insert(any(InboxEvent.class), eq("event_inbox"));

        InboxEvent existing = new InboxEvent(
            "tenant-a|evt-1001",
            "tenant-a", "evt-1001", "node-7", 1001L,
            new BigDecimal("26.50"),
            Instant.parse("2026-11-23T02:00:00Z"),
            "DONE", Instant.parse("2026-11-23T02:01:00Z"));

        when(mongo.findById(
            eq("tenant-a|evt-1001"),
            eq(InboxEvent.class),
            eq("event_inbox")))
            .thenReturn(existing);

        assertEquals(IngestOutcome.ALREADY_ACCEPTED,
                service.ingest(event()));
    }

    @Test
    void differentPayloadIsConflict() {
        MongoOperations mongo = mock(MongoOperations.class);
        MongoInboxIngestService service =
                new MongoInboxIngestService(mongo);

        doThrow(new DuplicateKeyException("E11000"))
            .when(mongo)
            .insert(any(InboxEvent.class), eq("event_inbox"));

        InboxEvent existing = new InboxEvent(
            "tenant-a|evt-1001",
            "tenant-a", "evt-1001", "node-7", 1001L,
            new BigDecimal("99.0"),
            Instant.parse("2026-11-23T02:00:00Z"),
            "RECEIVED", Instant.now());

        when(mongo.findById(
            anyString(),
            eq(InboxEvent.class),
            eq("event_inbox")))
            .thenReturn(existing);

        assertThrows(IngestConflictException.class,
                () -> service.ingest(event()));
    }
}
~~~

Các tests này kiểm tra **business decision**, không chứng minh MongoDB thật có unique index. Test database phải riêng.

### 21.2. Test RetryTemplate không thử lại duplicate

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.retry.support.RetryTemplate;
import static org.junit.jupiter.api.Assertions.*;

class RetryClassificationTest {

    @Test
    void duplicateKeyIsNotRetried() {
        RetryTemplate template = RetryTemplate.builder()
            .maxAttempts(3)
            .retryOn(
                org.springframework.dao.TransientDataAccessException.class)
            .traversingCauses()
            .build();

        AtomicInteger calls = new AtomicInteger();

        assertThrows(DuplicateKeyException.class,
            () -> template.execute(context -> {
                calls.incrementAndGet();
                throw new DuplicateKeyException("E11000");
            }));

        assertEquals(1, calls.get());
    }
}
~~~

Thêm test ném `TransientDataAccessException` phù hợp, xác minh maxAttempts=3 nghĩa **1 initial + 2 retries**, và test cause chain `MessagingException`. Test E11000 từ unique index khác nhưng findById trả null phải ném conflict, không trả ALREADY_ACCEPTED.
## 22. Integration test MongoDB thật và concurrent inserts

### 22.1. Kiểm thử duplicate trên test database

Dùng MongoDB test instance độc lập hoặc Testcontainers nếu runner cho phép Docker. Ví dụ `@SpringBootTest`:

~~~java
package example.mongoingest;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoInboxIngestIT {

    @Autowired MongoOperations mongo;
    @Autowired MongoInboxIngestService service;

    @Test
    void duplicateIsIdempotentIfContentMatches() {
        String id = "it-" + UUID.randomUUID();

        IncomingTelemetry event = new IncomingTelemetry(
            "tenant-test", id, "node-test", 100L,
            new BigDecimal("26.5"),
            Instant.parse("2026-11-23T02:00:00Z"));

        String mongoId = "tenant-test|" + id;
        Query byId = Query.query(
                Criteria.where("_id").is(mongoId));

        try {
            assertEquals(IngestOutcome.INSERTED,
                    service.ingest(event));
            assertEquals(IngestOutcome.ALREADY_ACCEPTED,
                    service.ingest(event));
            assertEquals(1,
                mongo.count(byId, "event_inbox"));
        } finally {
            mongo.remove(byId, "event_inbox");
        }
    }
}
~~~

**Điều kiện:** ứng dụng test có bean service, MongoOperations thật và database/index đúng; `@SpringBootTest` không tự khởi chạy MongoDB server. Chỉ cleanup key do test tạo, tuyệt đối không chạy test trên production.

### 22.2. Hai worker cùng insert cùng event

Trong integration test trên MongoDB thật:

1. Tạo một event ID ngẫu nhiên duy nhất.
2. Hai threads/instances cùng chờ `CountDownLatch` rồi gọi `ingest(event)`.
3. Assert chỉ **một** lần trả `INSERTED` và lần kia trả `ALREADY_ACCEPTED` khi payload trùng.
4. Assert chỉ có một document theo unique key.
5. Lặp với cùng ID nhưng payload khác giữa hai workers: worker thua phải báo `CONFLICT`.
6. Cleanup đúng test key, có timeout hữu hạn cho threads.
7. Nếu test hai app instances thật, dùng cùng MongoDB deployment/collection/unique index.

Test race với Mockito không đủ chứng minh constraint MongoDB. Test hai clients trên một MongoDB local chỉ là một phần; failover/replication consistency cần môi trường test riêng.

### 22.3. Test write result unknown

Trên replica set test cô lập:

- Chủ động tạo tình huống network timeout/ACK lost sau một insert.
- Dùng cùng `_id`/business event ID khi thử lại.
- Khi lần sau gặp E11000, query/readback record và so sánh canonical fields.
- Không khẳng định exception đầu tiên có nghĩa write bị rollback.
- Phân biệt MongoDB error label `NoWritesPerformed` khi version/driver hỗ trợ.
- Nếu readback không thấy record ngay do cấu hình secondary, kiểm tra read preference/read concern trước khi kết luận là conflict.
- Theo dõi số lần retry của driver, Spring Retry và broker để tránh retry storm.

**Không làm network fault/failover trên production** để thực hành.

## 23. Reactive test với StepVerifier

Reactive MongoDB phát lỗi qua publisher, sau subscription. Ví dụ với một collection test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import reactor.test.StepVerifier;

@SpringBootTest
class ReactiveDuplicateKeyIT {

    @Autowired ReactiveMongoOperations reactiveMongo;

    @Test
    void repeatedInsertEmitsDuplicateError() {
        InboxEvent event = testEventWithUniqueId();

        StepVerifier.create(
            reactiveMongo.insert(event, "event_inbox")
                .then(reactiveMongo.insert(
                    event, "event_inbox")))
            .expectError(DuplicateKeyException.class)
            .verify();
    }
}
~~~

Đây là **test fragment**: phải cung cấp `testEventWithUniqueId()`, test collection/unique index, reactor-test dependency và cleanup sau test, bao gồm nhánh error. Nó không được chạy trên production. Nếu muốn kiểm thử reactive service `insertOrRecognize(...)`, subscribe hai invocations qua StepVerifier và assert INSERTED rồi ALREADY_ACCEPTED.

### 23.1. Không retryWhen mọi Throwable

~~~java
// Sai: retry cả duplicate vĩnh viễn.
return reactiveMongo.insert(event, "event_inbox")
    .retryWhen(Retry.max(10));
~~~

Thay bằng retry chỉ những lỗi đã phân loại:

~~~java
return reactiveMongo.insert(event, "event_inbox")
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(200))
            .filter(ex ->
                ex instanceof TransientDataAccessException));
~~~

Đây là fragment với imports `Retry`, `Duration` và `TransientDataAccessException`; nó chỉ xử lý một **tập con** lỗi transient. `onErrorResume(DuplicateKeyException.class, ...)` cần **đọc lại record và đối chiếu business contents**, không trả `Mono.empty()` để che mọi duplicate.

## 24. Metrics, logging và cảnh báo production

Các metric gợi ý (không mặc định framework xuất đúng tên):

| Metric | Ý nghĩa |
|---|---|
| `mongo_inbox_insert_attempt_total` | Số insert attempts |
| `mongo_inbox_inserted_total` | Số insert được ACK |
| `mongo_duplicate_key_total` | Tổng E11000 |
| `mongo_duplicate_same_payload_total` | Idempotent repeat |
| `mongo_duplicate_conflict_total` | Trùng ID khác nội dung / index conflict |
| `mongo_application_retry_attempt_total` | Retry ở handler |
| `mongo_retry_exhausted_total` | Hết retry budget |
| `mongo_unknown_write_outcome_total` | Timeout/mất ACK, result chưa xác định |
| `mongo_reconciliation_success_total` | Đối soát business key thành công |
| `mongo_reconciliation_unresolved_total` | Trạng thái chưa xác định |
| `mongo_bulk_partial_success_total` | Batch có partial successes |
| `mongo_inbox_pending_depth` | Event đang chờ business handler |
| `mongo_outbox_redelivery_total` | Event được broker/worker gửi lại |
| `mongo_business_committed_total` | Business side effect đã commit |
| `integration_dlq_depth` | Event trong durable dead-letter/quarantine |

Log có ích:

~~~text
ingest_attempt       eventId=evt-1001 tenant=tenant-a
mongo_insert_ack     eventId=evt-1001
mongo_duplicate      eventId=evt-1001 index=_id_
reconciliation_ok    eventId=evt-1001 outcome=ALREADY_ACCEPTED
business_conflict    eventId=evt-1001 reason=payload_mismatch
retry_exhausted      eventId=evt-1001 attempts=3
~~~

**Không log payload nhạy cảm, credentials, URI đầy đủ có password.** Đừng dùng mỗi `eventId`/deviceId làm metric label cardinality cao; correlation IDs có thể được quản lý trong tracing/log có retention và quy định PII phù hợp.

### 24.1. Khi nào cần cảnh báo?

- `duplicate_same_payload` tăng: có thể do nguồn redelivery/ACK chậm, chưa chắc là bug.
- `duplicate_conflict` tăng: có thể do ID collision, event producer lỗi hoặc data model/index sai.
- Retry attempts tăng đồng thời với MongoDB failover: kiểm tra retry storm, connection pool và backoff.
- Outbox/inbox backlog tăng sau downtime: cần capacity/recovery.
- DLQ tăng: cần có runbook, owner và replay policy.
- Unknown outcomes tăng: xem write concern/driver timeouts/network.

## 25. Troubleshooting checklist

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
|---|---|---|
| E11000 ở request “đầu tiên” | Record đã tồn tại từ lần trước hoặc index khác xung đột | Đọc theo key, xem index name |
| Retry liên tục vẫn E11000 | Unique constraint vĩnh viễn | Dừng retry duplicate, đối soát |
| Cùng ID khác payload | Producer tái sử dụng key sai | Conflict/quarantine, không overwrite |
| save không báo lỗi nhưng state reset | Replace document cùng ID | Insert-only cho immutable inbox |
| Hai workers cùng đọc absent | Race `exists → insert` | Unique index phân xử |
| HTTP timeout nhưng record đã có | ACK lost | Retry cùng Idempotency-Key |
| Kafka redelivery sau DB commit | Offset chưa commit | Inbox idempotency và ACK đúng |
| Lỗi MongoDB sau write nhưng document tồn tại | Unknown outcome | Readback bằng ID |
| Error recovery xong nhưng message bị ACK | Recoverer suppress error | Durable recovery/propagate |
| RetryAdvice không kích hoạt | Wiring endpoint/advice sai hoặc exception khác | Kiểm tra adviceChain và cause |
| Duplicate vẫn được retry | Classifier default retry mọi exception | Chọn retryOn transient only |
| Retry quá nhanh gây tải | Không backoff/jitter | Giới hạn attempts/backoff |
| Driver+Spring+broker retry nhiều | Multiplicative retry budget | Thống nhất deadline/cap |
| Bulk insert lỗi dù vài docs đã có | Partial success | Reconcile per event ID |
| Unique index deploy fail | Dữ liệu cũ trùng/null | Migration có kiểm soát |
| Sharded uniqueness không đúng | Index không tương thích shard key | Review schema/index |
| Inbox kẹt PROCESSING | Worker crash/lease không expiry | Lease/recovery/fencing |
| Business effect trùng ở đích | Không có idempotent consumer | Unique downstream inbox |
| Transaction bị abort rồi retry một insert riêng | Transaction context đã invalid | Retry đúng boundary |
| Reactive Mono error bị nuốt | onErrorResume trả empty | Propagate/quarantine có ACK |
| Test pass nhưng không kiểm tra payload conflict | Thiếu case khác nội dung | Unit/integration cases |

### 25.1. Trình tự khoanh vùng

~~~text
Source event + stable business key
    -> validate + tenant authorization
    -> Spring Integration Message / handler
    -> RetryAdvice (transient only)
    -> MongoOperations.insert + unique index
    -> E11000? findById + canonical comparison
    -> INSERTED / ALREADY_ACCEPTED / CONFLICT
    -> ACK source hoặc durable retry/DLQ
    -> Inbox processor + atomic claim/lease
    -> Outbox + broker publish
    -> Idempotent business commit ở đích
~~~

`MessageChannel.send()==true` không chứng minh DB commit nếu dùng asynchronous channel. Luôn đối chiếu ranh giới **source ACK → durable state → business side effect**.

## 26. Bài thực hành tổng hợp

Xây pipeline **HTTP/Kafka/JMS → Spring Integration → MongoDB event_inbox → worker → Kafka/JMS/HTTP/DB**.

### Phần A — MongoDB E11000

1. Tạo database test và collection `event_inbox`.
2. Tạo compound unique index `(tenantId, eventId)`.
3. Insert một document rồi insert lại với cùng ID bằng mongosh, xem code 11000.
4. Thử unique index khác `(tenantId,deviceId,sequence)`, cùng tuple nhưng eventId mới.
5. Thử dữ liệu thiếu/null và lập kế hoạch partial index/migration nếu business cần.
6. So sánh `insert`, `save`, `upsert` và update có điều kiện.

### Phần B — Idempotent inbox service

1. Dựng entity `IncomingTelemetry` và `InboxEvent`, dùng stable ID.
2. Implement `MongoInboxIngestService.ingest(...)`.
3. Assert INSERTED ở lần đầu và ALREADY_ACCEPTED ở redelivery cùng nội dung.
4. Assert CONFLICT khi cùng ID khác temperature/device.
5. Test E11000 ở index khác mà findById không thấy expected ID.
6. Test hai concurrent workers; assert một inbox document tồn tại.
7. Bật read preference phù hợp cho reconciliation sau timeout.

### Phần C — RetryAdvice

1. Tạo `RequestHandlerRetryAdvice` với maxAttempts=3.
2. Chọn `TransientDataAccessException` và traversing causes.
3. Gắn vào đúng ServiceActivator hoặc Java DSL endpoint, không cả hai.
4. Unit test DuplicateKeyException được thử **một lần**.
5. Unit test transient error được retry có giới hạn.
6. Thử recovery channel; phân biệt in-memory ErrorMessage với durable DLQ.
7. Thử HTTP/JMS/Kafka ACK khi DB down để ngăn xác nhận sớm.

### Phần D — Driver, bulk và unknown result

1. Trên replica set test, bật Retryable Writes.
2. So sánh driver retry, Spring Retry, broker redelivery.
3. Mô phỏng lost ACK sau insert; retry **cùng business ID**.
4. Reconcile canonical payload; không tạo UUID mới.
5. Chạy unordered bulk với một document duplicate và kiểm tra các documents đã ghi.
6. Không retry toàn batch bằng IDs mới, dùng per-item outcomes.
7. Test `NoWritesPerformed` label theo version khi có error phù hợp.

### Phần E — Reliability và vận hành

1. Ghi inbox + outbox trong MongoDB transaction; test rollback nếu outbox insert lỗi.
2. Simulate crash sau broker publish ACK trước khi mark SENT.
3. Thêm idempotent consumer theo event ID, assert một business effect.
4. Dùng atomic `findAndModify` claim với owner/lease/version.
5. Bổ sung DLQ/quarantine và reconciliation runbook.
6. Đo duplicate same-payload vs conflict, attempts, exhausted retry, unknown result.
7. Thử graceful shutdown khi còn pending inbox/outbox events.

**Câu hỏi tự đánh giá:**

- E11000 báo điều gì, có luôn là `_id` trùng không?
- E11000 có thể xảy ra trên update/upsert/bulk/index build không?
- Vì sao E11000 không tự chứng minh hai payload giống nhau?
- `insert` và `save` khác nhau ra sao khi ID đã có?
- Vì sao `exists() → insert()` không ngăn race?
- Null/missing trong unique index gây vấn đề gì?
- Khi nào trả ALREADY_ACCEPTED, khi nào trả CONFLICT?
- Vì sao không dùng Spring MessageHeaders.ID làm dedup key?
- Driver retryable write khác Spring Retry như thế nào?
- `maxAttempts(3)` là bao nhiêu lần gọi handler?
- Vì sao DuplicateKeyException thường không retry?
- Cause traversal quan trọng ra sao khi lỗi bị bọc trong MessagingException?
- ACK bị mất có thể biến một retry thành E11000 thế nào?
- ErrorMessageSendingRecoverer có thể khiến upstream ACK nhầm không?
- Stateful retry và broker redelivery khác stateless retry như thế nào?
- Label NoWritesPerformed nói chính xác điều gì?
- Unordered bulk có thể thành công một phần không?
- E11000 của upsert trong transaction MongoDB 8.1 có tự được retry không?
- Khi commit transaction response lost, có thể coi là chắc chắn rollback không?
- Vì sao outbox vẫn cần idempotent consumer?
- Làm sao test đồng thời cả duplicate hợp lệ và duplicate conflict?

## 27. Tài liệu tham khảo

- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): unique constraints, null/missing, partial indexes và sharded indexes.
- [MongoDB Manual — insertOne](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertOne/): ví dụ lỗi `11000`.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): driver retry, topology và `NoWritesPerformed`.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): transaction retry/error labels và duplicate upsert.
- [MongoDB Manual — bulkWrite](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/): ordered/unordered và partial successes.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): ACK, durability và wtimeout.
- [Spring Data MongoDB — CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): insert/save/update/upsert/bulk.
- [Spring Framework API — DuplicateKeyException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DuplicateKeyException.html): DAO exception hierarchy.
- [Spring Integration — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): inbound/outbound/gateway.
- [Spring Integration — Provided Advice Classes](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): RequestHandlerRetryAdvice, stateless/stateful retry và recoverer.
- [Spring Integration API — RequestHandlerRetryAdvice 6.4](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html): setRetryTemplate và recovery callback.
- [Spring Retry API — RetryTemplateBuilder 2.x](https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplateBuilder.html): maxAttempts, retryOn, traversingCauses, exponentialBackoff.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): MongoTransactionManager, ReactiveMongoTransactionManager.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): retryWhen/onErrorResume.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): kiểm thử Publisher và onError.

## Kết luận

**E11000 là lỗi ràng buộc unique index, không phải yêu cầu phải retry.** Trong **SPRING_INTEGRATION_ADAPTERS**, xử lý đúng bắt đầu với **business event ID ổn định**, unique constraint, và quyết định **INSERTED / ALREADY_ACCEPTED / CONFLICT** sau khi đối chiếu nội dung thật. `insert` thường phù hợp cho inbox lưu event bất biến; `save` có thể overwrite state, không tự là công cụ dedup.

Retry phải được thiết kế **theo loại lỗi và theo tầng**: MongoDB driver Retryable Writes, Spring Integration retry advice, broker redelivery và HTTP retry đều có trách nhiệm riêng. Không retry duplicate key vô hạn; không coi timeout là write chắc chắn chưa xảy ra; không ACK chỉ vì một message đã vào channel RAM. Với workflow xuyên MongoDB/Kafka/JMS/HTTP/SFTP, cần **durable inbox/outbox, atomic claim/lease, idempotent consumer, bounded retry, reconciliation, metrics và recovery** để bảo toàn tính đúng đắn khi crash hoặc redelivery.






