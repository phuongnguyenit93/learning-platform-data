# Write concern và transaction trong Spring Integration MongoDB

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **write concern** của MongoDB là mức **xác nhận thao tác ghi** với các thành phần `w`, `j` và `wtimeout`, khác với thời gian query, thời gian poll và business ACK.
- Phân biệt `w:0` (không đợi ACK), `w:1` (primary/standalone ACK), `w:"majority"` (đa số thành viên lưu dữ liệu theo cơ chế MongoDB) và `j:true` (yêu cầu ghi journal); biết ảnh hưởng của topology, durability và failover.
- Giải thích vì sao **write concern timeout không tự rollback**, và khi nhận timeout/mất ACK, trạng thái ghi có thể **chưa biết**; cần cùng event ID, retry giới hạn và đối soát thay vì sinh ID mới.
- Hiểu **MongoDB multi-document transaction** dựa trên `ClientSession`, yêu cầu topology hỗ trợ, phân biệt commit/abort với single-document atomic update.
- Cấu hình `MongoTemplate.setWriteConcern(...)` hoặc `WriteConcernResolver` đúng tầng, không nhầm cấu hình write concern của template với một thuộc tính `MessageChannel`.
- Cấu hình `MongoTransactionManager`/`TransactionTemplate`/`@Transactional` cho blocking operations và `ReactiveMongoTransactionManager`/`TransactionalOperator` cho reactive operations.
- Tích hợp transaction với `MongoDbStoringMessageHandler`, `MongoDbMessageSource`, poller và `MessageChannel`; phân biệt **real MongoDB transaction** với **`PseudoTransactionManager`/transaction synchronization**.
- Biết vì sao MongoDB transaction **không tự commit** Kafka offset, JMS ACK, HTTP response, SFTP file move hoặc JDBC transaction ở database độc lập.
- Thiết kế **transactional outbox/inbox**, business idempotency, unique index, atomic claim/lease, retry/compensation và khôi phục sau crash.
- Viết kiểm thử rollback/commit trên replica set, majority write concern, timeout ambiguity, after-commit callback, double consumer và lỗi external publisher.

Bài thuộc chương **Adapter MongoDB** trong module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`, thực hành với file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, chú trọng hợp đồng message, xử lý lỗi và vòng đời kết nối. Ở đây, MongoDB là một hệ thống lưu trữ trong **chuỗi xử lý message**, nên phải tách ba loại cam kết: **MongoDB đã xác nhận write**, **MongoDB transaction đã commit** và **nghiệp vụ xuyên hệ thống đã hoàn tất**.

> **Phạm vi phiên bản:** ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data MongoDB/Spring Integration tương thích qua BOM; các package `MongoDatabaseFactory` và `ReactiveMongoDatabaseFactory` là tên API hiện đại. Việc cấu hình transaction cần MongoDB deployment hỗ trợ (thường replica set hoặc sharded cluster). Ví dụ URI local/credentials không phù hợp production.

## 1. Bài toán nghiệp vụ: ghi Order và Outbox Event

Một API nhận yêu cầu đặt hàng. Ứng dụng muốn:

1. Nhận `OrderCommand(orderId, tenantId, amount)` qua HTTP/JMS/Kafka hoặc một Spring `MessageChannel`.
2. Ghi document đơn hàng vào MongoDB collection `orders`.
3. Ghi **outbox event** vào collection `outbox_events` để một worker khác phát Kafka.
4. Tránh tình huống **có order nhưng không có outbox**, hoặc ngược lại.
5. Chỉ báo order đã được ghi **sau khi transaction commit**.
6. Không gửi Kafka message hai lần về mặt **tác động nghiệp vụ**, dù outbox worker crash và phải phát lại.

~~~mermaid
flowchart LR
  A["HTTP / JMS / Kafka"] --> B["ordersInput channel"]
  B --> C["OrderApplicationService"]
  C --> T["MongoDB transaction"]
  T --> O[("orders")]
  T --> E[("outbox_events")]
  E --> P["Outbox poller"]
  P --> K["Kafka publisher"]
  K --> D["Idempotent consumer"]
~~~

**Vấn đề:** chỉ đặt `writeConcern=MAJORITY` cho lệnh ghi order **không** làm hai lệnh `insert(order)` và `insert(outbox)` trở thành một transaction. Ngược lại, transaction MongoDB giữa hai collection **không** tự commit Kafka publish/ACK. Cả **write concern**, **transaction** và **outbox** đều có vai trò riêng.

### 1.1. Một số trạng thái có thể xảy ra

| Mốc | Đã xảy ra? | Có thể khẳng định điều gì? |
|---|---|---|
| `MessageChannel.send()` trả true | Message được channel chấp nhận | **Chưa chắc** MongoDB đã ghi, đặc biệt flow async |
| `MongoOperations.insert()` trả thành công ngoài transaction | Write được ACK theo write concern đang áp dụng | Không phải toàn bộ nghiệp vụ đã commit |
| `TransactionTemplate.execute()` trả sau commit | MongoDB transaction manager đã hoàn tất commit thành công theo phản hồi | Không tự bao gồm Kafka/JMS/HTTP |
| `wtimeout` hoặc network error | Không nhận được confirmation yêu cầu | **Không biết chắc** write chưa xảy ra |
| Outbox event được commit | Event nằm bền trong MongoDB theo write/commit concern | Chưa chắc broker đã nhận |
| Kafka publish ACK thành công | Broker xác nhận theo producer configuration | Chưa chắc consumer đã xử lý nghiệp vụ |
| Consumer business commit | Tác động đích thành công | Cần idempotency khi broker redeliver |

## 2. Write concern là gì?

**Write concern** là mức xác nhận MongoDB cần đáp ứng trước khi trả kết quả cho một write operation (insert, update, delete hoặc commit transaction).

Ví dụ cấu trúc MongoDB:

~~~javascript
{
  w: "majority",
  j: true,
  wtimeout: 3000
}
~~~

- **`w`**: số lượng thành viên hoặc điều kiện majority/custom tag phải xác nhận.
- **`j`**: có yêu cầu xác nhận thao tác ghi đã vào **on-disk journal** không.
- **`wtimeout`**: giới hạn thời gian để thỏa yêu cầu write concern khi operation đã được thực hiện; **không phải** tổng timeout của mọi bước database/driver.

Write concern không trực tiếp trả lời câu hỏi “**document nào được đọc**” (đó là `ReadConcern`/read preference/query), cũng không tự trả lời “**bao nhiêu document được thay đổi**” (cần xem `matchedCount`/`modifiedCount`/duplicate key/business state).

### 2.1. Các mức w quan trọng

| Cấu hình | Điều MongoDB yêu cầu trước khi trả ACK | Rủi ro chính |
|---|---|---|
| `{w: 0}` | Không yêu cầu server ACK cho write | Client không biết server có chấp nhận, validation/write lỗi có thể không được phản ánh |
| `{w: 1}` | Primary hoặc standalone xác nhận thao tác ghi | Có thể rollback khi failover trước khi dữ liệu lan sang secondary đủ mức |
| `{w: 2}` | Hai thành viên phù hợp xác nhận (ví dụ primary + 1 secondary) | Nếu thiếu node phù hợp, write concern timeout |
| `{w: "majority"}` | Đa số thành viên bỏ phiếu **có dữ liệu** theo quy tắc MongoDB xác nhận | Latency/availability phụ thuộc topology, có thể timeout |
| `{w: "majority", j: true}` | Majority concern và yêu cầu journal theo semantics/version/config | Không đồng nghĩa “Kafka đã ACK” hoặc “không bao giờ mất dữ liệu trong mọi sự cố” |

**Đừng đặt `w:0` cho các message yêu cầu giao hàng bền/ACK chính xác.** Với unacknowledged writes, một caller không có đủ bằng chứng để quyết định business event đã được ghi.

### 2.2. Majority không phải “một node bất kỳ”

Giả sử replica set có ba thành viên dữ liệu và phiếu bầu: `Primary P`, `Secondary S1`, `Secondary S2`.

~~~mermaid
sequenceDiagram
    participant App as Integration app
    participant P as Primary
    participant S1 as Secondary 1
    participant S2 as Secondary 2
    App->>P: insert(order), w=majority
    P->>P: apply write/oplog
    P-->>S1: replicate oplog
    P-->>S2: replicate async
    S1-->>P: acknowledge sufficient
    P-->>App: write concern satisfied
~~~

Trong mô hình ba node voting data-bearing, majority thường tương ứng **hai** thành viên. Với topology có arbiter, tag hoặc members không voting, phép tính cần theo đúng **MongoDB replication rules**, không đơn giản lấy số node chia đôi. MongoDB hiện đại mặc định dùng `w:"majority"` trong phần lớn triển khai, nhưng có ngoại lệ với topology chứa arbiter và có thể bị override bằng cluster/client/operation settings.

**Không hard-code giả định “default luôn là w:1” hoặc “default luôn là majority”**. Kiểm tra cấu hình cluster/driver thực tế, nhất là khi nâng cấp MongoDB hoặc đổi topology.

### 2.3. j:true có ý nghĩa gì?

`j:true` yêu cầu acknowledgment sau khi thao tác ghi được journal hóa trên những thành viên áp dụng theo quy tắc phiên bản MongoDB. Nó giúp giảm rủi ro mất dữ liệu khi node crash, nhưng:

- `j:true` **không tự bảo đảm majority replication** nếu `w` thấp.
- Majority và journaling tương tác với cấu hình `writeConcernMajorityJournalDefault` và MongoDB version.
- `w:"majority"` mặc định thường có journal durability trong replica set hiện đại, nhưng phải kiểm tra deployment.
- Journal ACK của MongoDB **không chứng minh** downstream Kafka hoặc database khác đã commit.

### 2.4. MongoDB 8.0+ và read-after-write trên secondary

Từ MongoDB 8.0, majority acknowledgment có thể đạt khi các members đã **durably written oplog entries**; secondary có thể **apply** thay đổi vào collection cục bộ sau đó.

Vì thế, sau khi nhận `w:"majority"` ACK, một query ngay lập tức gửi tới secondary mà không có causal consistency có thể **chưa thấy kết quả mới**. Nếu workflow yêu cầu read-your-writes, dùng read preference/session/causal consistency phù hợp; đừng coi majority write ACK là bảo đảm mọi secondary đã sẵn sàng trả document.

## 3. wtimeout: write concern không đạt không tự rollback

Điểm phải ghi nhớ:

> **`wtimeout` xảy ra không có nghĩa MongoDB đã hoàn tác write ở primary.** Một write có thể đã thực hiện nhưng chưa đạt đủ số ACK replication theo yêu cầu tại thời điểm timeout.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant A as Spring Integration
    participant P as Mongo Primary
    participant S as Mongo Secondary
    A->>P: insert(evt-101) with w=majority
    P->>P: apply write locally
    Note over S: Mất mạng hoặc replication chậm
    P--xA: writeConcernError / wtimeout
    Note over A: Kết quả cuối cùng chưa xác định
    Note over P: Write có thể vẫn tồn tại
~~~

Nếu app coi mọi timeout là “chưa có document” và retry với `UUID.randomUUID()` mới, nó có thể tạo **hai business records**. Nếu retry cùng business `_id`/unique key, nó có thể gặp duplicate key (đôi khi là bằng chứng lần ghi cũ đã tới server); vẫn phải kiểm tra nội dung và trạng thái nghiệp vụ, không tự nuốt mọi duplicate key.

### 3.1. Ba loại timeout cần phân biệt

| Timeout | Điều nó giới hạn | Khi timeout có tự rollback? |
|---|---|---|
| `wtimeout` | Thời gian thỏa write concern replication | **Không** tự undo write đã áp dụng |
| `serverSelectionTimeout` | Driver chờ chọn server phù hợp | Không tự khẳng định write đã/ chưa thực hiện |
| Socket/read/network timeout | Driver chờ I/O hoặc response | Kết quả write có thể chưa biết |
| Query max time | Thời gian thực hiện operation tại server, tùy API | Không thay thế transaction rollback semantics |
| `@Gateway(replyTimeout)` | Caller chờ Spring Messaging reply | Không tự cancel/undo MongoDB write |
| Poller `fixedDelay` | Lịch gọi source | Không phải transaction/write timeout |

Trong các trường hợp **response lost**, phải reconcile qua unique key và dữ liệu thực tế, hoặc retry theo operation protocol chính thức với idempotency. **ACK bị mất không có nghĩa dữ liệu bị mất.**

### 3.2. wtimeout trong mongosh

Ví dụ lệnh ghi dùng write concern tường minh:

~~~javascript
use integration_lab

db.runCommand({
  insert: "audit_events",
  documents: [
    { _id: "audit-101", kind: "ORDER_ACCEPTED", orderId: "order-101" }
  ],
  writeConcern: { w: "majority", j: true, wtimeout: 3000 }
})
~~~

Chạy trên database **test** thuộc một replica set để quan sát các chính sách replication. Đừng dùng ví dụ này làm bài kiểm tra trên production; nếu collection/ID đã tồn tại, có thể nhận duplicate-key error. Với `wtimeout`, server có thể trả write concern error ngay cả khi thao tác ghi đã được áp dụng.

## 4. Write concern khác ReadConcern và ReadPreference

Ba khái niệm thường bị nhầm:

- **WriteConcern**: mức xác nhận cho ghi/commit.
- **ReadConcern**: tính nhất quán/độ bền dữ liệu mà read yêu cầu (ví dụ `local`, `majority`, `snapshot` trong ngữ cảnh phù hợp).
- **ReadPreference**: chọn node đọc (`primary`, `secondary`, ...).

| Nhu cầu | Điều cần xét |
|---|---|
| Không mất write mới khi primary failover | `w:"majority"` và durability của deployment |
| Đọc dữ liệu đã được majority xác nhận | `ReadConcern.MAJORITY` phù hợp |
| Đọc “đúng write vừa thực hiện” qua nhiều nodes | Causal consistency/session và read preference phù hợp |
| Có snapshot đồng nhất trong transaction | Transaction read concern `snapshot` nếu được hỗ trợ |
| Thao tác read mới sau write trong thread | Không tự mặc định transaction nếu chưa có session/transaction manager |
| Ghi từ SFTP sang MongoDB rồi HTTP | Cần định nghĩa ACK/compensation ngoài MongoDB |

Causal consistency khi dùng session có những điều kiện về write/read concern. Không ngầm coi một `MongoTemplate.find()` đọc từ secondary ngay lập tức sẽ thấy một majority write trong mọi MongoDB version/topology.

## 5. Write concern khác transaction

| Khả năng | Write concern | MongoDB transaction |
|---|---|---|
| Mục tiêu | Khi nào server ACK write | Nhóm các thao tác thành một đơn vị commit/abort |
| Một document update | MongoDB vốn có atomicity theo một document | Có thể dùng nhưng thường không cần transaction |
| Hai collection `orders` và `outbox_events` | **Không** tự atomic | Có thể atomic nếu cùng MongoDB deployment/session thích hợp |
| Rollback nhiều write khi exception | **Không** do write concern | Có thể abort transaction |
| Chọn mức durability của commit | Áp vào write bình thường | **Transaction-level write concern** tại commit |
| Kafka/JMS/HTTP side effect | Không áp dụng | **Không tự tham gia** |
| Failover/unknown result | Phải reconcile | Có thể có unknown commit result cần reconcile/retry commit theo protocol |
| Chi phí | Replication ACK latency | Session, transaction locks/resources/commit overhead |

**MongoDB single-document operations vốn là atomic** ở cấp document. Nếu chỉ cần claim một job NEW thành PROCESSING theo điều kiện, `findAndModify` hoặc `updateFirst` có điều kiện thường phù hợp hơn mở transaction nhiều document mà không cần thiết.

Transaction có ích khi ứng dụng cần bảo đảm **hai hay nhiều thao tác MongoDB** cùng commit hoặc cùng abort, ví dụ ghi order và outbox entry.

## 6. Chuẩn bị Spring Boot và MongoDB replica set lab

### 6.1. Maven dependencies

Cho Spring Boot 3.x:

~~~xml
<!-- Phần dependencies trong pom.xml -->
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
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

**Không cần tự thêm phiên bản driver**, hãy để BOM tương thích quản lý Spring Data/MongoDB driver/Integration. Nếu chỉ muốn reactive, dùng `spring-boot-starter-data-mongodb-reactive` và reactive transaction manager riêng; không inject nhầm `MongoTemplate` vào reactive endpoint.

### 6.2. MongoDB topology

MongoDB multi-document transactions yêu cầu deployment hỗ trợ (thường replica set hoặc sharded cluster). **Một standalone mongod không phù hợp** để chạy test transaction theo nghĩa replica set, dù vẫn có thể thử thao tác CRUD.

Spring Boot lab:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/integration_lab?replicaSet=rs0
~~~

`rs0` chỉ là tên minh họa của **replica set đã được khởi tạo** trong môi trường thử. Không tự thêm `replicaSet=rs0` vào URI production khi cluster không có tên đó.

Xem topology bằng mongosh trên test deployment:

~~~javascript
rs.status()
db.hello()
db.getMongo().getWriteConcern()
~~~

Một số lệnh chỉ hợp lệ trên thành viên replica set hoặc đòi quyền phù hợp. Nếu `getWriteConcern()` không có giá trị override, phải kiểm tra default của cluster/server/driver; output trống **không chứng minh w:1**.

### 6.3. Hai collection cần tồn tại

Trong mongosh test:

~~~javascript
use integration_lab

db.createCollection("orders")
db.createCollection("outbox_events")
db.createCollection("audit_events")

db.orders.createIndex({ tenantId: 1, orderId: 1 }, { unique: true })
db.outbox_events.createIndex({ eventId: 1 }, { unique: true })
~~~

Tạo collections/indexes **trước** bài test transaction để tránh phụ thuộc việc implicit create bên trong transaction; các quy tắc MongoDB về DDL trong transaction khác nhau theo version/topology, nên không coi DDL tự phát là một phần transaction nghiệp vụ an toàn.

### 6.4. Schema demo

~~~java
package example.mongodbtx;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderRecord(
        @Id String id,
        String tenantId,
        String orderId,
        BigDecimal amount,
        String status,
        Instant createdAt) {
}

@Document(collection = "outbox_events")
public record OutboxEvent(
        @Id String id,
        String tenantId,
        String eventId,
        String aggregateId,
        String type,
        String status,
        Instant createdAt) {
}

public record OrderCommand(
        String orderId,
        String tenantId,
        BigDecimal amount) {
}
~~~

Các record là các **top-level Java types riêng** khi đưa vào dự án thật. Dùng unique business ID/tenant để tránh duplicate. `@Id` map sang MongoDB `_id`; nếu cần giữ độ chính xác số tiền, cấu hình `@Field(targetType = FieldType.DECIMAL128)` hoặc custom converter cho `BigDecimal`, test đọc/ghi thật.

## 7. Đặt write concern ở Java driver và Spring Data

### 7.1. MongoTemplate.setWriteConcern

Spring Data `MongoTemplate` có setter:

~~~java
void setWriteConcern(com.mongodb.WriteConcern writeConcern)
~~~

Ví dụ cấu hình một MongoTemplate thay thế auto-config:

~~~java
package example.mongodbtx;

import com.mongodb.WriteConcern;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.MongoTemplate;

@Configuration
public class MongoConcernConfig {

    @Bean
    public MongoTemplate mongoTemplate(
            MongoDatabaseFactory databaseFactory) {

        MongoTemplate template =
                new MongoTemplate(databaseFactory);

        template.setWriteConcern(
            WriteConcern.MAJORITY
                .withWTimeout(3000, TimeUnit.MILLISECONDS));

        return template;
    }
}
~~~

**Đây là một cấu hình template của ứng dụng**, không bắt buộc thêm nếu Boot đã cấp một MongoTemplate khác có concern phù hợp. Một bean MongoTemplate mới dùng cùng factory nhưng thiếu custom mapping/converters có thể thay đổi behavior; production nên giữ mapping/converter và connection options nhất quán.

Nếu không `setWriteConcern`, MongoTemplate nhận default từ MongoDB driver/database/collection settings. Driver/client URI và server/global default cũng có thể tham gia; **không suy từ code mà bỏ qua deployment**.

### 7.2. MongoDB URI với write concern

Connection string có các tùy chọn tương ứng, ví dụ:

~~~text
mongodb://db-host-a,db-host-b/integration_lab?replicaSet=rs0&w=majority&journal=true
~~~

URI này chỉ là **minh họa**, không phải hostname thật. Các driver/MongoDB version mới có chính sách timeout khác nhau; tùy chọn `wtimeoutMS` trong connection string đã được đánh dấu deprecated trong tài liệu MongoDB mới, có thể dùng `timeoutMS` theo supported driver/operation semantics. **Không coi các timeout đó là hoàn toàn đồng nghĩa**: overall operation timeout và write concern wait limit có phạm vi khác nhau.

Trong production, ưu tiên cấu hình rõ trên driver/template/transaction và kiểm tra behavior qua integration tests thay vì dựa vào default vô tình.

### 7.3. WriteConcernResolver theo loại operation

Spring Data cung cấp `WriteConcernResolver` để chọn chính sách theo MongoDB action. Ví dụ:

~~~java
import com.mongodb.WriteConcern;
import org.springframework.data.mongodb.core.WriteConcernResolver;
import org.springframework.data.mongodb.core.MongoAction;

public final class DomainWriteConcernResolver
        implements WriteConcernResolver {

    @Override
    public WriteConcern resolve(MongoAction action) {
        if ("audit_events".equals(action.getCollectionName())) {
            return WriteConcern.MAJORITY;
        }
        return action.getDefaultWriteConcern();
    }
}
~~~

Đăng ký ở thời điểm cấu hình bean:

~~~java
template.setWriteConcernResolver(
        new DomainWriteConcernResolver());
~~~

Đây là **phương án cho write operations bình thường ngoài transaction**. Trong MongoDB multi-document transaction, write concern phải đặt **ở cấp transaction**, không áp write concern riêng cho từng lệnh bên trong transaction. Đừng dùng một resolver để cố override transaction commit policy trên từng operation.

**Không cập nhật MongoTemplate setters theo từng request**: template là singleton được nhiều thread dùng. Chọn settings lúc startup; nếu cần policy khác nhau theo business domain, tách template/factory có chủ đích hoặc resolver thread-safe.

## 8. Spring Integration MongoDB outbound adapter kế thừa write concern từ template

`MongoDbStoringMessageHandler` nhận `MongoOperations` đã cấu hình hoặc `MongoDatabaseFactory`; nó ghi message payload vào MongoDB collection.

### 8.1. Java DSL với MongoTemplate đã cấu hình

~~~java
package example.mongodbtx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.outbound.MongoDbStoringMessageHandler;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.data.mongodb.core.MongoTemplate;

@Configuration
@EnableIntegration
public class MongoAuditOutboundFlow {

    @Bean
    public MongoDbStoringMessageHandler mongoAuditWriter(
            MongoTemplate mongoTemplate) {

        MongoDbStoringMessageHandler writer =
                new MongoDbStoringMessageHandler(mongoTemplate);

        writer.setCollectionNameExpression(
            new LiteralExpression("audit_events"));
        return writer;
    }

    @Bean
    public IntegrationFlow auditFlow(
            MongoDbStoringMessageHandler mongoAuditWriter) {

        return IntegrationFlow.from("toMongoAudit")
                .handle(mongoAuditWriter)
                .get();
    }
}
~~~

**Điều cần hiểu:**

- Handler ghi payload theo semantics của `MongoOperations.save(...)` và collection expression.
- Không có một `writeConcern` property riêng của `MessageChannel` trong flow này.
- Write concern áp theo `MongoTemplate`/driver khi handler dùng template đó.
- Chọn `MongoDbStoringMessageHandler(MongoDatabaseFactory)` có thể tạo MongoTemplate riêng với default concern khác; muốn policy cụ thể, truyền template đã cấu hình.
- Nếu handler chạy đồng bộ qua `DirectChannel`, exception MongoDB có thể lan lên producer; nếu có `QueueChannel`/`ExecutorChannel`, caller `send()` có thể trả trước khi write hoàn tất.
- `save` không đồng nghĩa insert-only: cùng `_id` có thể ghi đè document. Không coi ACK thành công là không có duplicate nghiệp vụ.
- Writer chỉ là outbound adapter **một chiều**; muốn query request/reply, dùng MongoDB outbound gateway hoặc service thao tác `MongoOperations`.

### 8.2. Cảnh báo về kiểu dữ liệu và transaction

Nếu payload đến từ một projection entity chỉ lấy vài fields, đừng dùng writer `save` để “đổi một field”: save có thể thay thế cả document và xóa field vắng mặt. Dùng `updateFirst/findAndModify` cho partial update với filter ID/owner/version.

Nếu cần nhóm nhiều writes MongoDB thành transaction, **đặt transaction boundary ở service/endpoint phù hợp**. Chỉ gửi hai messages riêng qua writer không tự tạo một transaction chung: có thể bị xử lý trên hai threads, hai connections hoặc hai lần commit.
## 9. MongoTransactionManager: transaction MongoDB thật

Spring Data MongoDB cung cấp `MongoTransactionManager`, quản lý `ClientSession` và gắn session vào thread hiện tại cho MongoTemplate cùng `MongoDatabaseFactory`.

### 9.1. Tạo transaction manager với options

~~~java
package example.mongodbtx;

import com.mongodb.TransactionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class MongoTransactionConfig {

    @Bean("mongoTransactionManager")
    public MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .readPreference(ReadPreference.primary())
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        return new MongoTransactionManager(
                databaseFactory, options);
    }

    @Bean
    public TransactionTemplate mongoTransactionTemplate(
            MongoTransactionManager mongoTransactionManager) {
        return new TransactionTemplate(
                mongoTransactionManager);
    }
}
~~~

Giải thích:

1. `MongoTransactionManager` lấy `ClientSession` từ đúng factory.
2. `ReadConcern.SNAPSHOT` giúp các reads trong transaction làm việc theo snapshot semantics được MongoDB hỗ trợ.
3. `ReadPreference.primary()` phù hợp với write transaction.
4. **`WriteConcern.MAJORITY` áp ở **cấp transaction**, đặc biệt khi commit**, không phải write concern riêng của từng `insert` trong transaction.
5. `TransactionTemplate` là API imperative; nó không nhận `Mono` rồi tự subscribe.
6. Nếu MongoDB chỉ là standalone hoặc cluster thiếu khả năng transaction, các lệnh mở/commit transaction có thể thất bại.
7. Nếu dự án có nhiều transaction managers (JDBC, JMS, MongoDB), hãy **chỉ rõ** manager bằng tên/qualifier.

**Lưu ý:** nếu bạn đã định nghĩa `MongoTemplate` ở mục 7, cả template và transaction manager phải dùng **cùng MongoDatabaseFactory**. Nếu một operation đi qua MongoTemplate dùng factory khác, nó có thể chạy **ngoài transaction bạn đang kỳ vọng**.

### 9.2. Transaction-level concern và giới hạn per-operation

MongoDB yêu cầu **không đặt write concern riêng cho các write operations bên trong multi-document transaction**; concern ở cấp transaction được dùng khi commit.

Do đó:

- Đặt `WriteConcern.MAJORITY` trong `TransactionOptions` như ví dụ.
- Không gọi raw MongoDB collection operation với `withWriteConcern(...)` riêng cho từng insert trong transaction.
- Không giả định `MongoTemplate.setWriteConcernResolver` áp được một concern khác nhau cho từng document bên trong transaction.
- Nếu cần concern khác cho collection A và B trong cùng transaction, phải xem lại yêu cầu thiết kế vì **commit là một transaction-level concern**.
- Transactional commit báo lỗi/timeout có thể có **unknown commit result**, cần logic retry/reconciliation tương ứng MongoDB driver/server labels.

### 9.3. MongoDB transaction có chi phí

Transaction có thể giữ session, snapshot và resource trong quá trình thực thi. Không nên:

- Mở transaction rồi chờ HTTP/SFTP response nhiều phút.
- Đọc một collection rất lớn và giữ toàn bộ xử lý trong transaction.
- Tạo rất nhiều messages và giữ transaction trong lúc một queue async đang drain.
- Làm network gọi Kafka/JMS/HTTP **trước khi** MongoDB commit rồi giả định side effect sẽ rollback khi database abort.
- Mở nhiều transactions trên những database factories/clusters khác nhau rồi coi như một transaction phân tán.

Giữ transaction **ngắn**, gồm các MongoDB operations thật sự cần atomicity.

## 10. @Transactional: ghi order và outbox cùng commit

Một service Java dùng MongoOperations synchronous:

~~~java
package example.mongodbtx;

import java.time.Instant;
import java.math.BigDecimal;

import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final MongoOperations mongo;

    public OrderApplicationService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void acceptOrder(OrderCommand command) {
        if (command == null
                || command.orderId() == null
                || command.orderId().isBlank()
                || command.tenantId() == null
                || command.tenantId().isBlank()
                || command.amount() == null
                || command.amount().signum() <= 0) {
            throw new IllegalArgumentException(
                    "Invalid order command");
        }

        // Lab: yêu cầu xác thực tenant đã được thực hiện
        // trước khi gọi service. Production phải enforce quyền thật.
        Instant now = Instant.now();
        String eventId = "order-accepted:" + command.orderId();

        OrderRecord order = new OrderRecord(
                command.orderId(),
                command.tenantId(),
                command.orderId(),
                command.amount(),
                "ACCEPTED",
                now);

        OutboxEvent outbox = new OutboxEvent(
                eventId,
                command.tenantId(),
                eventId,
                command.orderId(),
                "ORDER_ACCEPTED",
                "PENDING",
                now);

        mongo.insert(order, "orders");
        mongo.insert(outbox, "outbox_events");

        // Không gọi kafkaTemplate.send() ở đây.
        // Hai MongoDB inserts cùng commit hoặc rollback.
    }
}
~~~

**Điều kiện để transaction thực sự chạy:**

- Method `public` được **gọi qua Spring proxy** (Spring-managed bean), không gọi `this.acceptOrder(...)` từ method khác cùng object rồi mong AOP chặn.
- Spring transaction management được bật trong cấu hình Spring Boot phù hợp.
- `mongoTransactionManager` có tồn tại và dùng cùng factory với MongoOperations.
- Client MongoDB kết nối replica set/sharded cluster hỗ trợ transaction.
- Tất cả các lệnh MongoDB cần nhóm atomicity phải tham gia cùng session/transaction.
- Collection/index đã được chuẩn bị; không trộn schema/DDL initialization vào một request transaction production.

### 10.1. Nếu lệnh insert thứ hai thất bại thì sao?

Nếu `orders` insert được thực hiện nhưng `outbox_events` insert báo duplicate key hoặc exception trước commit, transaction manager phải **abort** transaction; các writes chưa commit trong transaction không được công bố như writes đã commit.

~~~mermaid
sequenceDiagram
    participant I as Spring Integration
    participant S as @Transactional Service
    participant D as MongoDB
    I->>S: acceptOrder(command)
    S->>D: start transaction (session)
    S->>D: insert order
    S->>D: insert outbox
    D-->>S: duplicate key/error
    S->>D: abort transaction
    S-->>I: exception
~~~

Đây là lý do cần test rollback trên MongoDB **replica set** thay vì chỉ mock MongoOperations. Mockito không thể chứng minh hai operations cùng rollback trong storage engine.

### 10.2. @Transactional khác write concern cao

Giả sử không có transaction:

~~~java
mongo.insert(order, "orders");         // ACK majority
mongo.insert(outbox, "outbox_events"); // Ném exception
~~~

Kết quả có thể là **order tồn tại nhưng outbox không tồn tại**. Majority write concern của lần insert đầu **không rollback** nó khi insert thứ hai thất bại.

Ngược lại, trong transaction, commit có `w:1` hoặc chưa cấu hình phù hợp có thể ảnh hưởng mức durability khi replica set failover. **Tính atomic giữa các writes** và **mức xác nhận/durability commit** là hai trục cần thiết kế cùng nhau.

### 10.3. Duplicate business ID phải được xử lý tường minh

Nếu client/Kafka redeliver cùng `orderId`:

- Unique `_id`/`(tenantId, orderId)` có thể từ chối lần ghi trùng.
- Handler nên kiểm tra trạng thái order hiện có và payload có khớp yêu cầu cũ hay không.
- Không nuốt mọi `DuplicateKeyException` như thành công: duplicate ID nhưng amount khác là conflict nghiệp vụ.
- Không dùng UUID mới cho cùng order request chỉ để “tránh lỗi trùng”.
- Nếu caller timeout sau commit, sự tồn tại của order/outbox theo business key giúp reconcile.

## 11. TransactionTemplate: khi cần kiểm soát programmatic

Nếu không muốn dùng proxy `@Transactional` hoặc muốn test lỗi trong một phạm vi rõ ràng, sử dụng `TransactionTemplate`.

~~~java
package example.mongodbtx;

import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ProgrammaticOrderService {

    private final MongoOperations mongo;
    private final TransactionTemplate mongoTx;

    public ProgrammaticOrderService(
            MongoOperations mongo,
            TransactionTemplate mongoTransactionTemplate) {
        this.mongo = mongo;
        this.mongoTx = mongoTransactionTemplate;
    }

    public void saveOrderAndOutbox(
            OrderRecord order, OutboxEvent outbox) {

        mongoTx.executeWithoutResult(status -> {
            mongo.insert(order, "orders");
            mongo.insert(outbox, "outbox_events");
        });
    }
}
~~~

- `executeWithoutResult` chỉ hoàn tất khi callback và commit/abort theo transaction manager hoàn thành.
- Exception `RuntimeException` mặc định gây rollback theo Spring transaction semantics; checked exceptions cần chính sách tùy cách dùng.
- Đừng gọi một async producer và mặc định nó sẽ chờ Kafka ACK trong transaction.
- TransactionTemplate cũng cần đúng manager nếu ứng dụng có thêm JDBC transaction manager.

### 11.1. Cẩn trọng với Spring proxy và self-invocation

Ví dụ này **không tự kích hoạt @Transactional** nếu `acceptOrder` được gọi từ method khác trên chính object:

~~~java
@Service
public class BrokenSelfInvocation {

    public void entry(OrderCommand command) {
        acceptOrder(command); // this-call bypasses proxy.
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void acceptOrder(OrderCommand command) {
        // Đừng giả định transaction đã được kích hoạt.
    }
}
~~~

Đây là **mẫu lỗi minh họa**, không phải implementation để dùng trong production. Tách service transactional bean được inject vào caller, hoặc dùng `TransactionTemplate` như mục 11.

## 12. Spring Integration MessageChannel và transaction boundary

Một `IntegrationFlow` chuyển `OrderCommand` vào transactional service:

~~~java
package example.mongodbtx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderIntegrationFlowConfig {

    @Bean
    public IntegrationFlow orderCommandsFlow(
            OrderApplicationService service) {
        return IntegrationFlow.from("ordersInput")
                .handle(service, "acceptOrder")
                .get();
    }
}
~~~

Ví dụ producer gửi vào `ordersInput`:

~~~java
Message<OrderCommand> message =
    MessageBuilder.withPayload(
        new OrderCommand(
            "order-101",
            "tenant-a",
            new BigDecimal("125.00")))
        .build();

ordersInput.send(message);
~~~

Producer cần inject `MessageChannel ordersInput`, import `MessageBuilder`, `Message`, `BigDecimal`. Flow sử dụng message handler gọi service method **qua proxy được inject**, nên `@Transactional` ở service có cơ hội mở transaction đúng cách.

### 12.1. Synchronous DirectChannel

Nếu đường từ producer đến handler là đồng bộ, service hoàn tất hoặc ném exception trong call stack của sender. **Tuy nhiên đừng coi `send()==true` như business ACK chung**: một flow có transformer/router/async channel ở giữa có thể đổi semantics.

Nếu yêu cầu caller biết kết quả order, thiết kế **request/reply gateway** trả DTO sau commit, với error mapping rõ ràng. Outbound storing adapter chỉ có nhiệm vụ lưu payload, không tự trả business result như gateway.

### 12.2. QueueChannel / ExecutorChannel thay đổi ranh giới

~~~text
Thread A: MessageChannel.send()
    -> QueueChannel accepts in-memory message
    -> returns true

Thread B (sau đó): receives message
    -> @Transactional acceptOrder()
    -> MongoDB commit hoặc rollback
~~~

**Thread A không nằm trong transaction mà thread B mở.** Một transaction context imperative thường được bind vào **thread**, không tự lan qua QueueChannel, thread pool hoặc future.

Nếu Kafka/JMS source được ACK ngay khi `QueueChannel` nhận message vào RAM, process crash có thể làm mất việc chưa ghi MongoDB. Hãy dùng durable broker/store hoặc giữ ACK tới sau transaction commit theo endpoint semantics.

### 12.3. Hợp đồng error và timeout

- MongoDB error ở service đồng bộ có thể propagate qua `DirectChannel` để caller xử lý.
- Với asynchronous channels, lỗi phát ở worker thread và có thể được gửi tới error channel.
- Reply timeout của caller không rollback MongoDB transaction đang chạy nếu operation không được cancel/rollback đúng cách.
- `TransactionTemplate` exception trước commit khác với **unknown commit result** sau timeout; cần phân loại.
- Khi transaction abort, upstream vẫn phải định nghĩa retry/backoff và idempotency.

## 13. MongoDbMessageSource polling, trạng thái và transaction

MongoDB inbound channel adapter dùng `SourcePollingChannelAdapter` để gọi `MongoDbMessageSource.receive()` theo lịch. Bản thân source chỉ tạo message từ query; để một chuỗi nhiều thao tác MongoDB cùng tham gia transaction, phải đặt `MongoTransactionManager` ở ranh giới thực sự bao trùm các thao tác đồng bộ đó.

`MongoDbMessageSource` query MongoDB theo lịch:

~~~text
Poller -> MongoDbMessageSource.receive()
       -> Query(status=NEW)
       -> Message<List<Document>>
       -> Splitter
       -> business handlers
~~~

Một poller với `maxMessagesPerPoll(1)` có thể nhận **một Message chứa nhiều documents**, không phải một document. Nếu query không thay đổi trạng thái, poll sau có thể lấy lại cùng NEW documents.

### 13.1. updateExpression làm gì?

Một MongoDB inbound source có thể dùng:

~~~java
MongoDb.inboundChannelAdapter(
        mongoOperations, "{ 'status':'NEW' }")
    .collectionName("inbox_events")
    .entityClass(OrderRecord.class)
    .update(new Update().set("status", "CLAIMED"));
~~~

Đây là **builder minh họa**, cần gắn poller + flow thật, và entity/collection phải hợp schema. `updateExpression` có thể giúp các documents vừa đọc không còn khớp query trong chu kỳ sau, **nhưng không chứng minh downstream đã commit**.

Cảnh báo:

- App crash sau CLAIMED trước Kafka ACK → document có thể kẹt.
- Hai worker có thể query cùng NEW trước khi update.
- Một `MongoTransactionManager` không tự biến thao tác query rồi update thành atomic claim từng document giữa nhiều workers khi isolation/concurrency chưa được thiết kế và kiểm thử.
- Nếu query/filter không đổi sau update, document vẫn có thể được poll lại.
- Khi downstream là async channel, transaction của poller thường không bao trùm business handler ở thread khác.

### 13.2. Poller có transaction advice

Spring Integration cho phép poller cấu hình transaction advice và synchronization callbacks. Ví dụ XML:

~~~xml
<!-- Các bean MongoTemplate, mongoTransactionManager, channels
     và XML namespaces int/int-mongodb cần được khai báo hợp lệ. -->
<int-mongodb:inbound-channel-adapter
        id="mongoWorkPoller"
        channel="inboxMessages"
        mongo-template="mongoTemplate"
        collection-name="inbox_events"
        query="{ 'status':'NEW' }"
        entity-class="example.mongodbtx.OrderRecord">

    <int:poller fixed-delay="5000"
                max-messages-per-poll="1">
        <int:transactional
            transaction-manager="mongoTransactionManager"/>
    </int:poller>
</int-mongodb:inbound-channel-adapter>
~~~

**Đây là một cấu hình minh họa transaction advice.** Transaction mở quanh đoạn xử lý **đồng bộ trong scope poller task**, không bao trùm Kafka publish async được đẩy sang thread riêng; nó không tự bảo đảm claim độc quyền giữa nhiều instances hay exactly-once.

### 13.3. Single-document atomic claim đáng tin hơn read-then-update

Một lựa chọn cho work queue MongoDB:

~~~java
package example.mongodbtx;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Repository;

@Repository
public class InboxClaimRepository {

    private final MongoOperations mongo;

    public InboxClaimRepository(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public OrderRecord claimOne(String workerId) {
        Query eligible = Query.query(
            Criteria.where("status").is("NEW"))
            .with(Sort.by(
                Sort.Order.asc("createdAt"),
                Sort.Order.asc("_id")));

        Update update = new Update()
            .set("status", "PROCESSING")
            .set("claimOwner", workerId);

        return mongo.findAndModify(
            eligible, update,
            FindAndModifyOptions.options().returnNew(true),
            OrderRecord.class, "inbox_events");
    }
}
~~~

**Cần điều chỉnh schema**: class `OrderRecord` ví dụ không chứa `claimOwner`, nên nó chỉ là minh họa query/update; dùng một `InboxWorkItem` entity có owner, lease, attempt và version trong code thực tế. `createdAt` trong entity demo có thể được dùng để sort nếu field thực tồn tại.

Quan trọng hơn: `findAndModify` với filter `status=NEW` + update `PROCESSING` là **một thao tác MongoDB atomic trên document**, giúp chỉ một worker thắng claim cùng document tại một thời điểm (theo điều kiện). Nó vẫn **không** chứng minh nghiệp vụ đã hoàn tất, cần lease/recovery cho worker chết và fencing/version nếu owner cũ thức dậy.

## 14. PseudoTransactionManager không phải transaction MongoDB

Spring Integration cung cấp:

~~~java
org.springframework.integration.transaction.PseudoTransactionManager
~~~

Nó là implementation `PlatformTransactionManager` phục vụ **transaction synchronization** khi không có database transaction thực. Nó giúp kích hoạt callbacks:

- `beforeCommit`
- `afterCommit`
- `afterRollback`

**Nhưng nó không commit hoặc rollback MongoDB, Kafka, JMS hay filesystem.**

### 14.1. Transaction synchronization XML minh họa

~~~xml
<bean id="pseudoTransactionManager"
      class="org.springframework.integration.transaction.PseudoTransactionManager"/>

<int:transaction-synchronization-factory id="syncFactory">
    <int:after-commit channel="afterSuccessfulPoll"/>
    <int:after-rollback channel="afterFailedPoll"/>
</int:transaction-synchronization-factory>

<!-- Trong poller của một inbound adapter có channel -->
<int:poller fixed-delay="5000">
    <int:transactional
        transaction-manager="pseudoTransactionManager"
        synchronization-factory="syncFactory"/>
</int:poller>
~~~

Phần `int:poller` ở đây là **fragment cần đặt bên trong inbound adapter**; không phải XML configuration hoàn chỉnh. `afterSuccessfulPoll` và `afterFailedPoll` là channels có consumers.

Khi xử lý đồng bộ kết thúc bình thường, callbacks “after-commit” có thể chạy; nếu exception xảy ra trong scope, “after-rollback” có thể chạy. **Đây là trạng thái điều phối của pseudo transaction**, không là MongoDB commit result.

### 14.2. Rủi ro khi callback afterCommit đi gửi Kafka

~~~text
MongoDB transaction COMMIT (orders + outbox)
   -> afterCommit callback gửi Kafka
   -> process crash trước khi Kafka ACK
   -> lần restart không có bảo đảm callback chạy lại
~~~

Dù callback chạy **sau** MongoDB commit, nó vẫn có khoảng trống crash và không là một durable work queue. Với event bắt buộc phát, **transactional outbox** ghi event cùng transaction rồi có worker riêng retry là mô hình bền hơn.

### 14.3. afterRollback không hoàn tác một file đã gửi

Nếu poller xử lý File/SFTP rồi phát qua HTTP, một pseudo rollback callback có thể dùng để đổi tên file hoặc ghi log thất bại. Nhưng dữ liệu HTTP đã gửi không thể tự động “thu hồi” chỉ vì callback báo rollback; cần compensation hoặc idempotent downstream theo nghiệp vụ.

**Tên callback không biến nguồn không transaction thành transactional resource.**

## 15. Transactional outbox: nối MongoDB với Kafka/JMS an toàn hơn

Đối với MongoDB → broker, một mô hình bền phổ biến:

1. Transaction MongoDB ghi **order + outbox event** với business ID ổn định.
2. Commit transaction với write concern phù hợp.
3. Outbox publisher đọc các entry PENDING theo limit/sort, claim atomically theo owner/lease.
4. Gửi Kafka/JMS, đợi broker acknowledgment theo contract.
5. Đánh dấu outbox SENT với conditional owner/version.
6. Khi crash ở bất kỳ bước nào, recovery worker có thể retry.
7. Consumer downstream deduplicate theo event ID; redelivery không tạo double business side effects.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant TX as Mongo transaction
    participant DB as MongoDB
    participant W as Outbox Worker
    participant B as Kafka/JMS broker
    API->>TX: acceptOrder(order-101)
    TX->>DB: insert orders(order-101)
    TX->>DB: insert outbox(evt-order-101)
    TX->>DB: commit w=majority
    DB-->>API: commit ACK
    W->>DB: atomically claim PENDING event
    DB-->>W: outbox event
    W->>B: publish(eventId)
    B-->>W: broker ACK
    W->>DB: conditional mark SENT
~~~

### 15.1. Hai crash windows quan trọng

**Crash trước khi broker ACK:** outbox vẫn PENDING/PROCESSING, lease sẽ hết hạn, worker khác retry. Broker có thể chưa nhận hoặc đã nhận; **event ID giữ nguyên**.

**Crash sau broker ACK nhưng trước khi update SENT:** lần chạy sau có thể publish lại cùng event. Vì vậy **at-least-once delivery + idempotent consumer** vẫn cần thiết. Outbox **không** tự tạo exactly-once effect xuyên broker và hệ thống đích.

### 15.2. Chọn ID và unique index

- Order có business ID cố định trong phạm vi tenant.
- Outbox event có eventId ổn định, tốt nhất uniqueness `(tenantId, eventId)`.
- Source/broker producer dùng lại eventId khi retry.
- Consumer lưu dedup/inbox theo cùng eventId với một unique constraint hoặc transaction cùng business effect trong DB đích.
- Không dùng Spring `MessageHeaders.ID` mới phát sinh mỗi redelivery làm dedup key.
- Nếu duplicate key có payload khác, phân loại là **conflict**, không tự nuốt.

### 15.3. Bảo đảm ACK theo từng hệ thống

| Hệ thống | Mốc ACK | Rủi ro nếu ACK trước |
|---|---|---|
| HTTP caller | Sau MongoDB transaction commit thành công | Client tưởng order đã tạo nhưng transaction fail |
| Kafka consumer nguồn | Theo chính sách commit offset sau durable processing | Message đã được offset commit nhưng DB chưa ghi |
| JMS session | Sau business state được lưu bền | Broker không redeliver khi DB fail |
| SFTP/File | Sau khi file contents được chuyển vào durable inbox/broker | File bị move/delete dù downstream chưa xử lý |
| Kafka/JMS outbox publisher | Sau broker producer ACK | SENT quá sớm dù broker chưa có event |
| Outbox DB status | Sau broker ACK, update theo owner | Nếu crash trước update có duplicate nhưng không mất sự kiện |

**Không có một atomic global ACK giữa MongoDB, HTTP, Kafka và SFTP chỉ bằng một `@Transactional`**.

## 16. ReactiveMongoTransactionManager và transaction trong Reactor

Trong reactive MongoDB pipeline, sử dụng:

~~~java
org.springframework.data.mongodb.ReactiveMongoTransactionManager
~~~

Thay vì thread-local, reactive transaction context được truyền theo **Reactor subscriber context**.

### 16.1. Reactive transaction manager với options

~~~java
package example.mongodbtx;

import com.mongodb.TransactionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class ReactiveMongoTransactionConfig {

    @Bean("reactiveMongoTransactionManager")
    public ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {

        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .readPreference(ReadPreference.primary())
            .writeConcern(WriteConcern.MAJORITY)
            .build();

        return new ReactiveMongoTransactionManager(
            factory, options);
    }

    @Bean
    public TransactionalOperator mongoTransactionalOperator(
            ReactiveMongoTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
~~~

Cần MongoDB reactive driver và `spring-boot-starter-data-mongodb-reactive` cùng BOM tương thích; không inject blocking MongoTransactionManager vào reactive pipeline rồi mong nó quản lý subscriber context.

### 16.2. TransactionalOperator và Mono

~~~java
package example.mongodbtx;

import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public final class ReactiveOrderWriter {

    private final ReactiveMongoOperations mongo;
    private final TransactionalOperator tx;

    public ReactiveOrderWriter(
            ReactiveMongoOperations mongo,
            TransactionalOperator tx) {
        this.mongo = mongo;
        this.tx = tx;
    }

    public Mono<Void> persistOrderAndOutbox(
            OrderRecord order, OutboxEvent outbox) {

        Mono<Void> work =
            mongo.insert(order, "orders")
                .then(mongo.insert(outbox, "outbox_events"))
                .then();

        return work.as(tx::transactional);
    }
}
~~~

**Quan trọng:**

- Tạo `Mono` không đồng nghĩa transaction đã bắt đầu. Nó chạy khi publisher **được subscribe**.
- Sử dụng cùng `ReactiveMongoDatabaseFactory` trong manager và operations.
- Ghép các MongoDB operations **theo thứ tự**, không chạy nhiều writes song song trên **cùng transactional ClientSession**.
- Spring Data MongoDB khuyến nghị tránh `flatMap` concurrent operations trong cùng MongoDB transaction vì driver yêu cầu các operations trên session được serialize. Dùng `then`/`concatMap` cho chuỗi cần transaction.
- Không tự gọi `subscribe()` bên trong service rồi trả Mono.empty; như vậy transaction completion bị tách khỏi caller.
- TransactionalOperator chỉ bao MongoDB operations nằm **bên trong cùng composed publisher/session**, không tự mở rộng qua Kafka/HTTP/JMS.

### 16.3. @Transactional trên phương thức reactive

Một Spring-managed service có thể khai báo:

~~~java
@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> saveReactiveOrder(
        OrderRecord order, OutboxEvent outbox) {
    return mongo.insert(order, "orders")
        .then(mongo.insert(outbox, "outbox_events"))
        .then();
}
~~~

Đây là **fragment** trong một `@Service` dùng `ReactiveMongoOperations mongo` đã inject. Phương thức phải được gọi qua Spring AOP proxy và **trả Publisher** để Spring áp reactive transaction khi subscribe; không gọi `block()` ở event-loop.

### 16.4. ReactiveMongoDbStoringMessageHandler và ACK

`ReactiveMongoDbStoringMessageHandler` trả `Mono<Void>` cho write, thường được compose vào Spring Integration reactive flow qua `FluxMessageChannel`.

Đừng coi một `MessageChannel.send()==true` là MongoDB transaction ACK: downstream publisher có thể chưa được subscribe hoặc chưa hoàn tất. Khi dùng reactive transaction với `TransactionalOperator`, chỉ báo business success **sau transaction publisher terminal signal** theo đúng contract.

## 17. MongoDB commit concern và transaction options

Ở MongoDB multi-document transaction:

- **Set write concern ở transaction level**, không từng write.
- Khi commit, server dùng transaction-level write concern để trả ACK.
- `ReadConcern.SNAPSHOT` có semantics về consistent snapshot trong transaction.
- `ReadPreference.primary()` thường cần cho write transaction.
- Transaction-level `w:"majority"` giúp commit được xác nhận ở mức durability theo deployment, không là ACK cho external systems.

Trong Spring Data MongoDB hiện đại, `@Transactional` còn hỗ trợ các **MongoDB transaction labels** theo version, ví dụ:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    label = {
        "mongo:writeConcern=MAJORITY",
        "mongo:readConcern=SNAPSHOT"
    })
public void auditedWrite() {
    // MongoDB writes tham gia session/transaction.
}
~~~

Đoạn trên là **API minh họa cho các version hỗ trợ transaction labels**; hãy đối chiếu Spring Data MongoDB/Spring Framework version và resolver trong dự án. Nếu không dùng labels, khai báo `TransactionOptions` khi tạo manager như mục 9.

**Không chồng thêm các options tùy ý vào một transaction đã tham gia từ trước** rồi kỳ vọng labels ở method lồng bên trong thay concern của transaction cha.

## 18. MongoDB transaction limitations và lỗi commit

### 18.1. Cần prepare collection/index trước khi chạy nghiệp vụ

Transactions có giới hạn về DDL, implicit collection creation, topology và resource budget; behavior có thay đổi theo MongoDB version. Một cách vận hành an toàn là **khởi tạo schema/index riêng trong deployment migration**, không tạo index/collection trong transaction xử lý request.

### 18.2. Retry transaction không giống retry một lệnh insert

MongoDB/driver có thể gắn labels như:

- **`TransientTransactionError`**: transaction có thể thất bại tạm thời, đôi khi cần retry lại **toàn bộ transaction**.
- **`UnknownTransactionCommitResult`**: chưa chắc commit đã/ chưa thành công; cần **retry commit theo driver protocol** hoặc reconcile dữ liệu.

Không bọc mọi exception bằng retry mù toàn bộ business method, nhất là khi method có external HTTP/Kafka/JMS side effect. Một transaction callback có thể chạy lại và tạo duplicate side effect nếu ứng dụng đặt chúng trong callback.

### 18.3. Commit là ranh giới quan trọng

~~~text
1. startTransaction()
2. insert(order)
3. insert(outbox)
4. commitTransaction()
5. confirm outcome / return to caller
~~~

Nếu lỗi xảy ra ở (2) hoặc (3) trước commit, abort có thể rollback transaction. Nếu mất response ở (4), **commit result có thể unknown**, không đơn giản suy “đã rollback”. Dùng driver retryable commit semantics, kiểm tra business key và outbox state sau failover.

### 18.4. Transaction timeout / lock conflicts / write skew

- Transaction mở lâu làm tăng resource usage và có thể chạm timeout/resource limits.
- Nhiều transaction cùng sửa một document có thể gây write conflict; cần retry có budget.
- Snapshot isolation không thay thế mọi unique business invariants. Dùng unique indexes/conditional updates để bảo vệ ràng buộc quan trọng.
- Một business predicate trải nhiều documents có thể cần thiết kế phù hợp để chống concurrency anomalies.
- Ghi journal/majority ACK có chi phí latency; chọn SLA và mức durability dựa trên nghiệp vụ.

**Không so sánh transaction như một chiếc khóa toàn database.** Một transaction không có nghĩa mọi worker phải chạy tuần tự; vẫn cần thiết kế consistency ở đúng vùng dữ liệu.
## 19. Kiểm thử transaction blocking trên MongoDB replica set

**Không dùng mock để chứng minh transaction storage-level.** Một Mockito stub có thể kiểm tra service gọi `mongo.insert` theo thứ tự nhưng không chứng minh MongoDB đã commit/rollback thật. Cần replica set **dành riêng cho test**, ví dụ một single-node replica set hoặc Testcontainers MongoDB cấu hình replica set phù hợp.

### 19.1. Kiểm thử rollback giữa hai writes

Ví dụ `@SpringBootTest` đã có `TransactionTemplate` trỏ tới `MongoTransactionManager`, MongoOperations, collections/indexes sẵn:

~~~java
package example.mongodbtx;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoOrderTransactionIT {

    @Autowired
    MongoOperations mongo;

    @Autowired
    TransactionTemplate mongoTransactionTemplate;

    @Test
    void rollsBackOrderAndOutboxTogether() {
        String key = "it-" + UUID.randomUUID();
        String eventId = "evt-" + key;
        Instant now = Instant.now();

        OrderRecord order = new OrderRecord(
            key, "tenant-test", key,
            new BigDecimal("12.50"), "ACCEPTED", now);

        OutboxEvent outbox = new OutboxEvent(
            eventId, "tenant-test", eventId, key,
            "ORDER_ACCEPTED", "PENDING", now);

        IllegalStateException exception = assertThrows(
            IllegalStateException.class,
            () -> mongoTransactionTemplate.executeWithoutResult(status -> {
                mongo.insert(order, "orders");
                mongo.insert(outbox, "outbox_events");
                throw new IllegalStateException("forced rollback");
            }));

        assertEquals("forced rollback", exception.getMessage());

        assertFalse(mongo.exists(
            Query.query(Criteria.where("_id").is(key)),
            OrderRecord.class, "orders"));

        assertFalse(mongo.exists(
            Query.query(Criteria.where("_id").is(eventId)),
            OutboxEvent.class, "outbox_events"));
    }
}
~~~

**Điểm kiểm tra quan trọng:** nếu test chỉ mock MongoOperations, `assertFalse(mongo.exists(...))` không kiểm tra dữ liệu thật. Hãy chắc chắn Spring Boot Test kết nối đúng replica set test, không phải production, và `TransactionTemplate` được inject từ bean có manager MongoDB.

### 19.2. Kiểm thử commit thành công

Một test khác có thể dùng cùng fixture, nhưng **không ném exception**:

~~~java
mongoTransactionTemplate.executeWithoutResult(status -> {
    mongo.insert(order, "orders");
    mongo.insert(outbox, "outbox_events");
});

assertTrue(mongo.exists(
    Query.query(Criteria.where("_id").is(order.id())),
    OrderRecord.class, "orders"));

assertTrue(mongo.exists(
    Query.query(Criteria.where("_id").is(outbox.id())),
    OutboxEvent.class, "outbox_events"));
~~~

Đây là fragment trong một test method có `order/outbox` đã tạo với ID test duy nhất, các imports và fixture cần thiết. Sau khi assertions chạy, **cleanup chính hai IDs đã seed** trong database test. Không gọi `dropDatabase()` trên một database được chia sẻ.

### 19.3. Test trùng event ID

Thử gọi `OrderApplicationService.acceptOrder(...)` hai lần với cùng `orderId` và tenant:

1. Lần đầu phải commit order/outbox.
2. Lần hai gặp duplicate key hoặc được service xử lý như yêu cầu idempotent theo **business policy** đã chọn.
3. Đếm `orders` và `outbox_events` chỉ có một bản ghi cho business key.
4. Nếu lần hai có amount khác, phải báo **conflict**, không im lặng coi là thành công.
5. Test với hai HTTP/Kafka requests đồng thời để bảo đảm unique constraint và transaction xử lý race.

Đây là bài test **business idempotency**, không chỉ test `w:"majority"`.

## 20. Kiểm thử transaction reactive bằng StepVerifier

Với reactive MongoDB, tất cả operations phải ở trong **publisher chain được subscribe**. Tạo `OrderRecord/OutboxEvent` có IDs test duy nhất, dùng `ReactiveMongoOperations` và `TransactionalOperator` đúng factory.

### 20.1. Kiểm thử commit

~~~java
import reactor.test.StepVerifier;
import reactor.core.publisher.Mono;

Mono<Void> write =
    mongo.insert(order, "orders")
        .then(mongo.insert(outbox, "outbox_events"))
        .then()
        .as(tx::transactional);

StepVerifier.create(write)
    .verifyComplete();
~~~

Chỉ khi `StepVerifier` subscribe và publisher báo `onComplete`, test mới có tín hiệu commit thành công theo transaction manager. Sau đó **đọc lại hai collection** và assert hai IDs. Đoạn này là fragment của integration test có reactive MongoDB test instance, bean `mongo` và `tx` đã inject.

### 20.2. Kiểm thử rollback

~~~java
Mono<Void> failing =
    mongo.insert(order, "orders")
        .then(mongo.insert(outbox, "outbox_events"))
        .then(Mono.error(
            new IllegalStateException("forced rollback")))
        .as(tx::transactional);

StepVerifier.create(failing)
    .expectErrorMatches(ex ->
        ex instanceof IllegalStateException
            && "forced rollback".equals(ex.getMessage()))
    .verify();
~~~

Sau failure, dùng một query **ngoài transaction đã abort** để assert hai documents không tồn tại. Không tự kết luận rollback chỉ vì `StepVerifier` nhận `onError`; database readback là phần bắt buộc của integration test.

### 20.3. Không chạy nhiều operations song song trên một session

Trong transaction, tránh mẫu sau:

~~~java
// Cảnh báo: không chạy concurrent flatMap MongoDB operations
// cùng transactional ClientSession rồi kỳ vọng driver hỗ trợ.
return Flux.fromIterable(orders)
    .flatMap(order -> mongo.insert(order, "orders"))
    .then()
    .as(tx::transactional);
~~~

Dùng `concatMap`/`then` khi cần serialize I/O:

~~~java
return Flux.fromIterable(orders)
    .concatMap(order -> mongo.insert(order, "orders"))
    .then()
    .as(tx::transactional);
~~~

Không giữ transaction mở cho một Flux vô hạn; giới hạn batch và lifetime. Nếu chỉ cần ghi mỗi event độc lập, chia thành các transactions ngắn theo key/job thay vì một transaction toàn bộ stream.

## 21. Kiểm thử write concern và unknown result

### 21.1. Không “giả lập” durability chỉ bằng setWriteConcern

Một unit test:

~~~java
WriteConcern concern = WriteConcern.MAJORITY;
assertNotNull(concern);
~~~

không chứng minh MongoDB đã majority-acknowledge. Muốn xác minh phải chạy trên topology thật và quan sát behavior từ driver/server, với điều kiện quyền và rủi ro được kiểm soát.

### 21.2. Failure injection trên replica set test

Những tình huống hữu ích:

| Test | Môi trường | Kết quả phải phân biệt |
|---|---|---|
| `w:1`, primary đang hoạt động | Replica set test | Write nhận ACK ở primary |
| `w:majority`, đủ members | Replica set test | Write ACK khi đạt concern |
| `w:majority`, secondary không sẵn sàng | **Chỉ** replica set cô lập | Có thể timeout/availability error |
| `wtimeout` sau primary apply | Failure injection có kiểm soát | Không tự khẳng định write rollback |
| Driver timeout trước ACK | Mạng giả lập | Kết quả có thể chưa rõ; reconcile cùng ID |
| Duplicate ID sau retry | Unique index | Có thể chứng minh một write trước đó đã tới DB |
| Transaction fail trước commit | DB test | Abort hai documents |
| Transaction commit ACK thất lạc | Replica set/fault injection | Unknown commit outcome, retry/reconcile |
| Service bị exception sau DB commit trước Kafka publish | Outbox worker | Outbox vẫn chờ retry |
| Kafka publish ACK rồi crash trước SENT | Broker + DB test | Có thể redeliver cùng event ID |

Chỉ làm replication failover/network fault trên **test environment**. Đừng dừng primary/secondary của production để minh họa một bài học.

### 21.3. Kiểm tra kết quả đúng cách

Một write concern timeout không phải tín hiệu “record chắc chắn không tồn tại”. Khi ứng dụng nhận lỗi:

1. Ghi lại request/correlation/business ID, operation type và error label (không log secrets).
2. Không cấp một business ID mới để retry cùng event.
3. Nếu driver có protocol retry commit/operation an toàn, tuân thủ protocol.
4. Readback bằng query phù hợp, read concern/session khi yêu cầu nhất quán.
5. Xác minh trạng thái order/outbox cùng payload/tenant, không chỉ `exists()` nếu conflict có thể xảy ra.
6. Chỉ ACK upstream sau khi tình trạng durable processing được xác lập.
7. Nếu không thể xác định trạng thái, đưa vào **reconciliation queue** thay vì tiếp tục như thành công.

**Không đặt toàn bộ error classifier thành `onErrorResume(e -> Mono.empty())`** trong reactive transaction: nó có thể biến failure thành completion rồi ACK nhầm.

## 22. Ma trận lỗi và chính sách phục hồi

| Vị trí lỗi | Biểu hiện | Cách xử lý |
|---|---|---|
| Connection/auth sai | Driver operation không chạy | Sửa config/secret/role, không retry vô hạn |
| Standalone không hỗ trợ transaction | Error khi start/commit transaction | Dùng replica set/sharded test deployment phù hợp |
| MongoTemplate dùng factory khác manager | Operation nằm ngoài transaction | Truy vết beans/factory/session, sửa wiring |
| WriteConcern w:0 | Không có write ACK đáng tin | Không dùng cho business durable events |
| wtimeout | Write có thể đã áp dụng | Reconcile ID, không tự xem là rollback |
| Primary step-down | Transient/unknown results | Retry có giới hạn, driver protocol, business key |
| MongoDB duplicate key | Record cùng key đã tồn tại | So sánh payload/status và phân loại duplicate/conflict |
| Outbox insert fail sau order insert | Transaction abort | Test rollback cả hai collections |
| MongoDB transaction commit unknown | Client thiếu xác nhận | Retry commit/reconcile, không phát lại side effect bừa |
| Transaction rất dài | Timeout/lock/resource pressure | Giảm scope, batch ngắn |
| MongoDB write conflict | Transaction bị abort | Retry toàn transaction nếu an toàn/idempotent |
| Kafka send fail sau DB commit | Outbox PENDING/PROCESSING | Broker retry, lease recovery |
| Kafka ACK rồi worker chết | SENT chưa được đánh dấu | Redelivery với event ID ổn định |
| JDBC transaction không được Mongo manager quản lý | Hai resource không atomic | Outbox/saga, không giả định 2PC |
| DirectChannel đổi thành QueueChannel | Transaction context bị ngắt | Xác định ACK/transaction ở worker đúng thread |
| PseudoTransactionManager được dùng nhầm | Không có MongoDB rollback thật | Dùng MongoTransactionManager khi cần MongoDB transaction |
| MongoDbMessageSource đọc lặp NEW | Polling query read-only | Claim/lease/idempotency, update đúng trạng thái |
| Two workers claim cùng document | Read-then-update race | Conditional atomic findAndModify |
| Reactive Mono không subscribe | Không có write thật | Compose/subscribe theo framework |
| Reactive flatMap parallel trong transaction | Driver session contention | then/concatMap, sequential operations |

### 22.1. Cùng lỗi exception nhưng hai cách hiểu

**`DuplicateKeyException`:** có thể do retry trùng **cùng payload** đã commit trước đó, hoặc một client khác dùng cùng key với **payload khác**. Phải query business record và so sánh nội dung, đừng nuốt hết như idempotent success.

**`MongoTransactionException`/transaction error labels:** có thể do dữ liệu, quyền, topology hoặc transient failover. Không retry vô hạn; phân loại transient vs permanent và giới hạn attempts/backoff.

**Write concern error:** operation server đã làm có thể còn tồn tại, cần reconciliation; không coi mọi exception đều có nghĩa storage rollback.

## 23. Observability: đo đúng ACK và commit

Các metric gợi ý (không mặc định Spring Integration tự sinh đúng tên):

| Metric | Đo điều gì? |
|---|---|
| `mongo_write_attempt_total` | Số write attempts |
| `mongo_write_ack_total` | Write operation được ACK |
| `mongo_write_concern_timeout_total` | Lỗi wtimeout |
| `mongo_write_unknown_result_total` | Trạng thái operation chưa rõ |
| `mongo_write_latency_seconds` | Latency write đến ACK |
| `mongo_transaction_begin_total` | Số transaction bắt đầu |
| `mongo_transaction_commit_success_total` | Commit ACK thành công |
| `mongo_transaction_abort_total` | Transaction abort/rollback |
| `mongo_transaction_commit_unknown_total` | Commit outcome chưa xác định |
| `mongo_transaction_duration_seconds` | Thời gian transaction mở |
| `mongo_transaction_retry_total` | Số lần retry có kiểm soát |
| `mongo_outbox_pending_depth` | Outbox events đang chờ |
| `mongo_outbox_oldest_age_seconds` | Tuổi event PENDING cũ nhất |
| `mongo_outbox_publish_success_total` | Broker ACK thành công |
| `mongo_outbox_publish_error_total` | Broker publish thất bại |
| `mongo_outbox_redelivery_total` | Outbox event có dấu hiệu gửi lại |
| `integration_business_committed_total` | Nghiệp vụ downstream hoàn tất |

**Phân biệt** MongoDB write ACK, transaction commit ACK, broker publish ACK và business completion. Một service chỉ tăng `mongo_write_success_total` khi handler được gọi không đủ để đo durability.

### 23.1. Trace theo correlation và business ID

~~~text
order_received       orderId=order-101
mongo_tx_started      orderId=order-101
mongo_order_inserted  orderId=order-101
mongo_outbox_inserted eventId=order-accepted:order-101
mongo_tx_committed    orderId=order-101
outbox_claimed        eventId=order-accepted:order-101
broker_publish_ack    eventId=order-accepted:order-101
outbox_marked_sent    eventId=order-accepted:order-101
consumer_committed    eventId=order-accepted:order-101
~~~

Không log credentials, PAN, secrets, nội dung đặt hàng nhạy cảm hoặc payload nguyên vẹn. Tránh metric labels theo từng `orderId`/`eventId` vì cardinality quá cao; dùng tracing/logs với retention và PII policy đúng.

### 23.2. Cảnh báo quan trọng

- Số `wtimeout` tăng sau một node failover không đồng nghĩa tất cả writes thất bại/rollback.
- Outbox backlog tăng có thể do broker down, transaction commit thành công nhưng worker chưa gửi.
- Transaction duration tăng có thể do giữ network calls trong transaction hoặc pool thiếu connection.
- Duplicate events tăng có thể do crash window sau broker ACK trước khi mark SENT; đây là điều outbox **phải dự liệu**.
- MongoDB replication lag có thể ảnh hưởng majority ACK latency và read consistency.
- Mốc xử lý downstream nên dùng business key/trace ID qua nhiều hệ thống thay vì dựa trên Spring Message UUID.

## 24. Bảo mật và vận hành production

### 24.1. Credential và quyền

- Dùng MongoDB account có quyền read/write **đúng collections** `orders`/`outbox_events`.
- Quyền tạo collection/index và thao tác admin nên thuộc deployment/migration, không thuộc service runtime khi không cần.
- URI/credentials từ secret manager, không hard-code password hoặc log full connection URI.
- Bật TLS/network controls theo môi trường.
- Tenant được xác thực ở server; query và write phải giữ `tenantId` đúng phạm vi quyền.
- Transaction không tự bảo vệ cross-tenant access nếu service thiếu authorization.
- Unique index trên business IDs phải có tenant scope đúng hoặc ID namespace để tránh collision.

### 24.2. Replica set và durability

- Xác minh topology thực tế, majority count và trường hợp có arbiter.
- Chọn write concern theo **business SLA** về latency, durability và availability.
- Test failover trên môi trường cô lập trước khi rollout.
- Đo replication lag, journal pressure, client pool, transaction duration và error labels.
- Có readiness/liveness hợp lý, không “ready” khi database chưa đủ khả năng đáp ứng workload.
- Quản lý backup/restore nhất quán cho business collections, outbox và trạng thái idempotency.
- Sau restore, kiểm tra outbox PENDING/PROCESSING và state drift để tránh mất sự kiện.

### 24.3. Chiến lược phát hành

Khi deploy một version mới có đổi schema hoặc event format:

1. Đảm bảo consumer hiểu version cũ/mới trong giai đoạn chuyển tiếp.
2. Migration indexes/collections ở bước riêng, không giữa request transaction.
3. Bảo đảm outbox eventId/aggregateId ổn định qua restart.
4. Giữ cấu hình transaction manager theo cùng MongoDatabaseFactory.
5. Dừng producer/poller theo lifecycle có kiểm soát, cho worker drain đến deadline.
6. Khi còn pending work, lưu trạng thái bền để instance mới tiếp tục xử lý.
7. Đừng xóa outbox events ngay sau broker send nếu chưa xác định retention/replay/audit.

## 25. Chọn giải pháp: một document, nhiều document hay nhiều hệ thống?

| Yêu cầu | Giải pháp nên xem xét |
|---|---|
| Cập nhật một job từ NEW sang PROCESSING | **Conditional update/findAndModify** atomic trên một document |
| Ghi order + outbox trong cùng MongoDB deployment | **MongoTransactionManager** + transaction-level write concern |
| Chỉ muốn chọn mức ACK write | **WriteConcern** phù hợp, không cần transaction nhiều document |
| Ghi message vào MongoDB qua Integration outbound adapter | **MongoDbStoringMessageHandler** với MongoTemplate cấu hình đúng |
| File/SFTP inbound poll xong mới chạy callback | Transaction synchronization; **PseudoTransactionManager chỉ callback**, không transaction DB |
| MongoDB → Kafka không được mất event | **Transactional outbox** + retry + idempotent Kafka consumer |
| Kafka → MongoDB và commit offset | Durable inbox/transactional state + ACK policy phù hợp; không giả định một `@Transactional` bao Kafka |
| MongoDB + PostgreSQL cập nhật cùng lúc | Saga/outbox/compensation hoặc thiết kế phân tán được thẩm định; không suy MongoTransactionManager quản lý PostgreSQL |
| Nhiều workers cùng poll MongoDB | Atomic claim, lease, owner/version, idempotent processing |
| Reactive MongoDB nhiều writes cần atomic | `ReactiveMongoTransactionManager` + `TransactionalOperator`, serialize operations trong session |
| Chỉ cần phát hiện update từ MongoDB | Change stream với resume token/checkpoint; không thay thế transaction cross-system |

**Sự lựa chọn không phải “bật transaction cho mọi nơi”.** Chỉ mở transaction ở phạm vi cần atomic MongoDB state; kết nối các hệ thống khác bằng message contract, durable state và idempotency.

## 26. Bài thực hành tổng hợp

Xây hệ thống **Order API → Spring Integration → MongoDB orders + outbox → Kafka/JMS** và kiểm tra durability/rollback trên replica set.

### Phần A — Write concern

1. Cài MongoDB replica set **chỉ dành cho lab/test**.
2. Tạo collections/indexes như mục 6.
3. Thử write concern `w:1`, `w:"majority"` và cấu hình `j:true` tương ứng.
4. So sánh mức ACK, latency và yêu cầu topology; không kết luận chỉ từ một lần chạy.
5. Thử `wtimeout` trong failure injection an toàn, xác nhận write có thể còn tồn tại.
6. Kiểm tra default cluster/driver thực tế thay vì giả định.
7. Giải thích `ReadConcern.MAJORITY` khác với `WriteConcern.MAJORITY`.
8. Trả lời vì sao secondary sau ACK majority có thể còn chưa apply write ở MongoDB hiện đại.

### Phần B — Spring Data MongoDB transaction

1. Tạo `MongoTransactionManager` trên cùng MongoDatabaseFactory với MongoTemplate.
2. Chọn `TransactionOptions` với `ReadConcern.SNAPSHOT`, `ReadPreference.primary()` và `WriteConcern.MAJORITY`.
3. Viết `OrderApplicationService.acceptOrder(...)` với `@Transactional`.
4. Ghi order và outbox trong cùng transaction; assert cả hai sau commit.
5. Ném exception có chủ đích trong **test-only** transaction sau hai insert, assert cả hai rollback.
6. Thử duplicate business ID và amount conflict.
7. Thử self-invocation không qua Spring proxy để hiểu transaction boundary.
8. Thử operation sử dụng một MongoTemplate khác factory, phân tích nguy cơ chạy ngoài transaction.

### Phần C — Spring Integration endpoints

1. Tạo `IntegrationFlow.from("ordersInput").handle(service,"acceptOrder")`.
2. Gửi một OrderCommand từ producer, assert MongoDB commit và outbox PENDING.
3. So sánh DirectChannel và QueueChannel về transaction context và thời điểm `send()` trả.
4. Cấu hình MongoDbStoringMessageHandler dùng MongoTemplate có write concern phù hợp.
5. Thử MongoDB inbound polling nhận NEW documents và mô tả rủi ro đọc trùng.
6. Thử `updateExpression` trong flow riêng; giải thích vì sao CLAIMED chưa phải DONE.
7. Dùng `PseudoTransactionManager` với callback để thấy nó **không** rollback MongoDB.

### Phần D — Outbox và failure

1. Viết worker claim outbox PENDING với `findAndModify` + lease.
2. Gửi eventId ổn định tới broker test.
3. Broker ACK thành công rồi crash trước update SENT: retry có thể publish lại.
4. Thêm idempotent consumer theo event ID; assert chỉ một business effect.
5. Gây lỗi broker trước ACK; xác nhận outbox không bị đánh dấu SENT sai.
6. Giới hạn retries, backoff và phân loại lỗi transient/permanent.
7. Dùng reconciliation khi transaction commit/write result là unknown.

### Phần E — Reactive và vận hành

1. Tạo `ReactiveMongoTransactionManager`/`TransactionalOperator` với cùng ReactiveMongoDatabaseFactory.
2. Compose hai reactive inserts bằng `then`, không `subscribe()` rời rạc.
3. Dùng `StepVerifier` test commit, rollback và lỗi khi MongoDB down.
4. So sánh `flatMap` concurrent và `concatMap` sequential khi nằm trong một transaction.
5. Theo dõi metrics transaction begin/commit/abort/unknown, wtimeout và outbox backlog.
6. Thiết kế graceful shutdown và recovery khi còn pending outbox events.
7. Viết runbook cho replica set failover, credential rotation và backup/restore.

**Câu hỏi tự đánh giá:**

- Write concern `w`, `j` và `wtimeout` kiểm soát điều gì?
- `w:0` có phù hợp với business event bắt buộc được ghi bền không?
- `w:1` khác `w:"majority"` ở đâu?
- Majority ACK có nghĩa mọi secondary đã apply document chưa?
- Vì sao write concern timeout không tự rollback một write?
- WriteConcern và ReadConcern có thể thay thế nhau không?
- Vì sao two inserts với majority ACK không trở thành transaction?
- MongoDB single-document atomic update có cần multi-document transaction không?
- Vai trò của `ClientSession` và `MongoTransactionManager` là gì?
- Trong transaction, đặt write concern ở cấp nào?
- Vì sao MongoTemplate và manager cần chung MongoDatabaseFactory?
- Vì sao một `@Transactional` self-invocation có thể không kích hoạt AOP?
- Khi đổi DirectChannel thành QueueChannel, transaction scope thay đổi thế nào?
- `PseudoTransactionManager` có rollback MongoDB được không?
- afterCommit callback có thay thế transactional outbox không?
- Vì sao MongoDB commit không tự commit Kafka/JMS/HTTP?
- Crash sau broker ACK nhưng trước SENT gây chuyện gì?
- Vì sao idempotency key phải là business ID ổn định?
- Khi commit result không xác định, có nên tạo event ID mới để retry không?
- `ReactiveMongoTransactionManager` lưu transaction context ở đâu?
- Vì sao cần serialize các MongoDB reactive operations trong cùng transaction?
- Test với Mockito có chứng minh rollback MongoDB thật không?
- Vì sao transaction có thể làm giảm throughput nếu giữ mở quá lâu?
- Khi nào nên dùng findAndModify thay cho transaction nhiều document?

## 27. Tài liệu tham khảo

- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): định nghĩa `w`, `j`, `wtimeout`, majority, implicit default và acknowledgment behavior.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): phạm vi transaction, concerns/options, commit/abort và các giới hạn.
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/): majority/snapshot consistency.
- [MongoDB Manual — Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/): cấu hình concern/timeout và các thay đổi phiên bản.
- [Spring Data MongoDB Reference — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): ClientSession, MongoTransactionManager, ReactiveMongoTransactionManager, TransactionTemplate/TransactionalOperator và transaction labels.
- [Spring Data MongoDB Reference — Template Configuration](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-config.html): setWriteConcern, WriteConcernResolver và defaults.
- [Spring Data MongoDB API — MongoTemplate](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html): setWriteConcern, setWriteConcernResolver.
- [Spring Data MongoDB API — MongoTransactionManager](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/MongoTransactionManager.html): constructor với MongoDatabaseFactory/TransactionOptions, session binding.
- [Spring Data MongoDB API — ReactiveMongoTransactionManager](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/ReactiveMongoTransactionManager.html): Reactor Context, reactive session và transaction options.
- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): inbound/outbound adapters, MongoDbMessageSource, updateExpression và transaction synchronization.
- [Spring Integration API — MongoDbStoringMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/outbound/MongoDbStoringMessageHandler.html): factory/template constructors và write payload.
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): poller transaction advice, beforeCommit/afterCommit/afterRollback, PseudoTransactionManager và reactive transactions.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, QueueChannel, ExecutorChannel và thread boundaries.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): reactive publisher composition/transaction subscription.
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): kiểm thử onNext/onComplete/onError và rollback.
- [MongoDB Manual — findAndModify](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/): single-document conditional update/claim.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): driver retryable write behavior, failure classification.

## Kết luận

**Write concern** trả lời câu hỏi **MongoDB cần bao nhiêu và kiểu xác nhận nào trước khi trả ACK**; **transaction** trả lời câu hỏi **những thao tác MongoDB nào phải commit hoặc abort cùng nhau**. `wtimeout` không chứng minh một write đã rollback; `w:"majority"` không đồng nghĩa Kafka/JMS/HTTP đã nhận. Trong multi-document transaction, write concern phải được xác định ở **cấp transaction**, không áp riêng cho từng insert/update.

Trong **SPRING_INTEGRATION_ADAPTERS**, áp dụng `MongoTemplate` với concern được kiểm soát, `MongoTransactionManager` hoặc `ReactiveMongoTransactionManager` đúng factory/session, transaction boundary đúng thread/Publisher, và phân biệt `PseudoTransactionManager` với MongoDB transaction thật. Với luồng xuyên MongoDB và broker/file/HTTP, hãy kết hợp **transactional outbox, event ID ổn định, conditional claim/lease, idempotent consumer, retry/backoff, monitoring và reconciliation**. **Commit MongoDB là một bước kỹ thuật quan trọng, không phải cam kết exactly-once cho toàn bộ hệ thống.**




