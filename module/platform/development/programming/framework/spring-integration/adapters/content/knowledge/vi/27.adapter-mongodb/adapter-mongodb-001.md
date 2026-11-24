# MongoDB inbound channel adapter trong Spring Integration

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Hiểu vai trò của **MongoDB inbound channel adapter** khi lấy dữ liệu từ MongoDB và đưa vào `MessageChannel` của Spring Integration.
- Phân biệt **polling MongoDB**, **change stream**, **outbound adapter** và **outbound gateway**.
- Cấu hình `MongoOperations` / `MongoTemplate`, collection, query, entity class và poller bằng **Spring Integration Java DSL** hoặc XML.
- Phân biệt payload dạng **`List<T>` (mặc định)** và **một đối tượng `T`** khi bật `expectSingleResult(true)`; hiểu chức năng của splitter.
- Xác định rõ `fixedDelay`, `maxMessagesPerPoll`, kích thước mỗi lần query và cách chọn batch hợp lý.
- Phát hiện rủi ro **đọc lại document qua nhiều lần poll**, thiết kế trạng thái xử lý, idempotency, claim/lease, retry và transaction phù hợp.
- Kiểm thử truy vấn, message payload, header nguồn collection, lỗi kết nối và vòng đời endpoint.
- Tích hợp dữ liệu MongoDB với file, SFTP, HTTP, JMS, AMQP, Kafka, cơ sở dữ liệu hoặc các hệ thống khác qua `MessageChannel`.

Bài thuộc chương **Adapter MongoDB** của module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; đồng thời chú trọng hợp đồng message, xử lý lỗi và vòng đời kết nối. Tại đây, **MongoDB là nguồn dữ liệu**, còn Spring Integration biến kết quả truy vấn thành message để một luồng nghiệp vụ có thể tiếp nhận, biến đổi và chuyển tiếp.

## 1. Bài toán: lấy sự kiện còn chờ trong MongoDB

Một hệ thống ghi các bản ghi telemetry vào collection `inbox_events`. Một service khác cần định kỳ đọc những document có `status=NEW` rồi kiểm tra và chuyển dữ liệu sang bộ xử lý nghiệp vụ.

Ví dụ dữ liệu trong MongoDB:

~~~json
{
  "_id": "evt-101",
  "type": "DEVICE_READING",
  "deviceId": "node-7",
  "temperatureC": 26.5,
  "status": "NEW",
  "createdAt": "2026-11-01T08:00:00Z"
}
~~~

Luồng dự kiến:

~~~mermaid
flowchart LR
    DB["MongoDB<br/>inbox_events"] -->|"Query theo lịch"| MS["MongoDbMessageSource"]
    P["Poller<br/>fixed delay"] -.-> MS
    MS -->|"Message<List<InboxEvent>>"| C["MessageChannel"]
    C --> S["Splitter"]
    S -->|"Message<InboxEvent>"| V["Validate / Service"]
    V --> OUT["HTTP / Kafka / AMQP / DB"]
~~~

**Điểm mấu chốt:** MongoDB inbound adapter là một **polling consumer**. Nó không chủ động nghe một socket kết nối mới như UDP, cũng không mặc định đăng ký MongoDB change stream. Nó chỉ gọi truy vấn MongoDB khi **poller kích hoạt**, sau đó đưa kết quả vào luồng message.

Một lần truy vấn thành công cũng **không đồng nghĩa** document đã được xử lý đúng một lần. Nếu cứ truy vấn `status=NEW` mà không thay đổi trạng thái, cùng document sẽ tiếp tục xuất hiện ở những lần poll sau.

## 2. MongoDB inbound adapter khác những thành phần nào?

| Thành phần | Ai kích hoạt? | Thực hiện | Kết quả |
|---|---|---|---|
| **MongoDB inbound channel adapter** | Poller theo lịch | Query MongoDB | Phát một Spring `Message` từ kết quả tìm kiếm |
| **MongoDB change stream inbound adapter** | Subscription/event từ MongoDB | Theo dõi thay đổi collection/database | Phát các change events khi có thay đổi |
| **MongoDB outbound channel adapter** | Message đi vào input channel | Ghi/cập nhật dữ liệu MongoDB | Chủ yếu side effect ghi, không phải một kênh query định kỳ |
| **MongoDB outbound gateway** | Request message đi vào channel | Query/cập nhật theo hợp đồng gateway | Trả response message về reply channel |
| **MongoDB message store** | Channel/aggregator/ứng dụng dùng store | Lưu message hoặc group message | Cung cấp persistence cho một số pattern Integration |
| **Spring Data MongoTemplate trực tiếp** | Code ứng dụng gọi method | Thao tác MongoDB theo API | Trả đối tượng trực tiếp cho caller |

MongoDB inbound adapter phù hợp khi **nguồn dữ liệu là collection được quét theo lịch**. Nếu cần phản ứng gần thời gian thực theo thay đổi MongoDB và môi trường hỗ trợ, cân nhắc **change stream**. Nếu muốn tìm document **theo từng request cụ thể** từ HTTP hoặc message khác, gateway thường phù hợp hơn.

## 3. Kiến trúc của một polling inbound adapter

Trong Spring Integration, cơ chế này có các lớp:

~~~mermaid
flowchart TD
    T["Trigger: fixedDelay / cron"] --> P["SourcePollingChannelAdapter"]
    P --> R["MongoDbMessageSource.receive()"]
    R --> Q["MongoOperations.find/findOne"]
    Q --> DB["MongoDB collection"]
    DB --> Q
    Q --> M{"Có kết quả?"}
    M -->|Không| N["Không phát message"]
    M -->|Có| C["Output MessageChannel"]
    C --> H["Splitter / Transformer / Handler"]
~~~

- **`MongoDbMessageSource`** mô tả cách truy vấn MongoDB. Nó không tự lên lịch gọi `receive()`.
- **Poller** quyết định tần suất và số lần `receive()` trong một chu kỳ.
- **`MessageChannel`** tách nơi lấy dữ liệu khỏi nơi xử lý.
- **Handler/transformer/splitter** quyết định cấu trúc message và xử lý nghiệp vụ.
- **MongoDB collection** tiếp tục là nguồn sự thật; một message được tạo không có nghĩa một document tự biến mất hay tự chuyển trạng thái.

### 3.1. Một lần poll có thể tạo payload dạng List

Theo API `MongoDbMessageSource`, mặc định `expectSingleResult=false`. Khi đó adapter dùng thao tác tương ứng `MongoOperations.find(Query, Class)`. Payload của một message là **danh sách các document được ánh xạ**. Danh sách rỗng được xem như không có message.

Ví dụ truy vấn trả ba document:

~~~text
Poller kích hoạt
    |
    v
MongoDB tìm 3 document
    |
    v
1 Message<List<InboxEvent>>
    payload.size() = 3
    |
    v
Splitter
    |
    +--> Message<InboxEvent> evt-101
    +--> Message<InboxEvent> evt-102
    +--> Message<InboxEvent> evt-103
~~~

**Không nhầm số message với số document:** một `Message<List<InboxEvent>>` vẫn là **một message** của message source.

### 3.2. Khi bật expectSingleResult=true

Với `expectSingleResult(true)`, adapter sử dụng `findOne(...)` và payload là **một document**. Nếu không tìm thấy đối tượng, `receive()` không sinh message.

| Cấu hình | Thao tác đọc | Payload khi có kết quả | Dùng splitter? |
|---|---|---|---|
| `expectSingleResult(false)` (mặc định) | `find(...)` | `List<InboxEvent>` | Thường có, để xử lý từng document |
| `expectSingleResult(true)` | `findOne(...)` | `InboxEvent` | Không cần nếu một event mỗi message |

Khi chọn một document theo thứ tự, hãy cấu hình query có **sort xác định** nếu thứ tự có ý nghĩa. Không mặc định document đầu tiên do MongoDB trả về luôn là document cũ nhất.

## 4. Chuẩn bị dự án và kết nối MongoDB

### 4.1. Dependencies

Với dự án Spring Boot có dependency management tương thích với Spring Integration:

~~~xml
<!-- Bên trong <dependencies> của pom.xml -->
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
~~~

Ví dụ starter MongoDB ở đây dùng cách đặt tên của **Spring Boot 3.x**. Khi dùng major version khác, cần kiểm tra artifact starter và BOM tương ứng; không trộn Spring Data, Spring Integration và MongoDB Driver từ các major version không tương thích. Nếu dùng module MongoDB trực tiếp, cần chọn driver synchronous phù hợp. Bài này tập trung vào **blocking/polling inbound adapter**, không dùng reactive driver.

### 4.2. Cấu hình URI cho lab

Với Spring Boot 3.x, ví dụ `application.yml`:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/adapter_lab
~~~

Đây là **MongoDB local trong môi trường lab**. Với môi trường thật, hãy dùng cấu hình bảo mật ngoài source code (secret manager, biến môi trường hoặc cấu hình được quản trị); không hard-code user/password trong repository. Chỉ cấp quyền đọc hoặc cập nhật các collection cần thiết cho adapter.

Spring Boot có thể tự tạo `MongoTemplate`/`MongoOperations` khi MongoDB starter và connection config hợp lệ. Nếu ứng dụng có nhiều MongoDB connection, hãy inject đúng bean hoặc sử dụng qualifier rõ ràng.

### 4.3. Tạo dữ liệu thử trong mongosh

Chọn database và tạo hai event:

~~~javascript
use adapter_lab

db.inbox_events.insertMany([
  {
    _id: "evt-101",
    type: "DEVICE_READING",
    deviceId: "node-7",
    temperatureC: 26.5,
    status: "NEW",
    createdAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: "evt-102",
    type: "DEVICE_READING",
    deviceId: "node-8",
    temperatureC: 25.9,
    status: "NEW",
    createdAt: ISODate("2026-11-01T08:00:01Z")
  }
])

db.inbox_events.find({ status: "NEW" })
~~~

Nếu chạy thử nhiều lần, thao tác `insertMany` với cùng `_id` sẽ gặp lỗi trùng key. Có thể thay seed bằng `updateOne(..., { upsert: true })` hoặc làm sạch dữ liệu **chỉ trong database lab** theo quy trình an toàn; không tự xóa collection thật.

## 5. Mô hình dữ liệu (entity class)

Dùng Java 17+ và Spring Data MongoDB:

~~~java
package example.mongodb;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "inbox_events")
public record InboxEvent(
        @Id String id,
        String type,
        String deviceId,
        double temperatureC,
        String status,
        Instant createdAt) {
}
~~~

Spring Data MongoDB chịu trách nhiệm ánh xạ các trường trong document thành Java object. Record này là **entity minh họa**; ứng dụng thật cần kiểm tra version/schema, field null, miền giá trị, định danh thiết bị và yêu cầu nghiệp vụ trước khi chuyển tiếp.

Nếu dùng `entityClass(InboxEvent.class)`, payload sẽ gồm các entity được MongoDB mapping. Nếu không cấu hình entity class, kiểu mặc định phụ thuộc phiên bản và API; **không nên dựa vào kiểu thô mặc định** khi viết handler có hợp đồng rõ ràng.

## 6. Ví dụ Java DSL: poll MongoDB và phát từng event

Cấu hình gồm một message source, một poller và một channel. Ví dụ **chỉ đọc** để người học thấy luồng; chưa tự chuyển trạng thái document.

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class MongoInboundFlowConfig {

    @Bean("mongoEvents")
    public MessageChannel mongoEvents() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow mongoInboundFlow(
            MongoOperations mongoTemplate) {

        return IntegrationFlow
                .from(
                    MongoDb.inboundChannelAdapter(
                            mongoTemplate, "{ 'status': 'NEW' }")
                        .collectionName("inbox_events")
                        .entityClass(InboxEvent.class)
                        .expectSingleResult(false),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(1)))
                .split()
                .channel("mongoEvents")
                .get();
    }
}
~~~

Các thành phần:

1. `MongoDb.inboundChannelAdapter(mongoTemplate, query)` tạo DSL spec cho `MongoDbMessageSource`.
2. `collectionName("inbox_events")` chỉ định collection cần đọc.
3. `entityClass(InboxEvent.class)` ánh xạ kết quả thành entity có kiểu rõ ràng.
4. `expectSingleResult(false)` chọn `find(...)`, tạo một message với payload là danh sách entity nếu có kết quả.
5. `Pollers.fixedDelay(5000)` đặt lịch chạy sau khoảng dừng giữa các lần poll; đơn vị ở đây là mili giây.
6. `maxMessagesPerPoll(1)` quy định tối đa **một lần lấy message từ source trong một chu kỳ**, **không phải** giới hạn một document.
7. `split()` tách `List<InboxEvent>` thành message riêng cho từng entity.
8. `mongoEvents` là channel cho downstream handler.

**Cảnh báo cho lab:** vì query chỉ lọc `status=NEW` và chưa cập nhật trạng thái, **cả hai document có thể được phát lại trong mỗi lần poll**. Đây là hành vi bình thường của một truy vấn lặp, không phải Spring Integration tự sinh “exactly once”. Trong demo, chỉ quan sát một vài chu kỳ rồi dừng adapter. Phần sau trình bày cách thay đổi trạng thái và giới hạn trùng lặp.

### 6.1. Handler tiếp nhận một event

~~~java
package example.mongodb;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.mongodb.support.MongoHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class InboxEventHandler {

    private static final Logger log =
            LoggerFactory.getLogger(InboxEventHandler.class);

    @ServiceActivator(inputChannel = "mongoEvents")
    public void handle(Message<InboxEvent> message) {
        InboxEvent event = message.getPayload();

        if (event.id() == null || event.id().isBlank()
                || event.deviceId() == null
                || !Double.isFinite(event.temperatureC())) {
            throw new IllegalArgumentException(
                    "Invalid inbox document");
        }

        String collection = message.getHeaders()
                .get(MongoHeaders.COLLECTION_NAME, String.class);

        log.info("MongoDB event id={}, device={}, collection={}",
                event.id(), event.deviceId(), collection);

        // Demo chỉ ghi log. Thực tế: xử lý idempotent và commit.
    }
}
~~~

Với kết quả từ MongoDB inbound, header `MongoHeaders.COLLECTION_NAME` (tên thực tế `mongo_collectionName`) cho biết collection đã query. Header này là **metadata của Spring Message**, không phải một trường tự động được thêm vào MongoDB document.

Nếu downstream cần chuyển event ra HTTP, Kafka, JMS/AMQP hoặc file/SFTP, hãy xác định những field được phép chuyển tiếp; không tự serializing toàn bộ headers sang hệ thống khác.

### 6.2. Thử kết quả mong đợi

Sau khi khởi động Spring context và kết nối được MongoDB, trong lần poll có kết quả:

~~~text
MongoDB event id=evt-101, device=node-7, collection=inbox_events
MongoDB event id=evt-102, device=node-8, collection=inbox_events
~~~

Mỗi event xuất hiện như một payload riêng **sau splitter**. Nếu chưa có logic đánh dấu hoàn thành, những dòng log trên có thể lặp lại ở chu kỳ tiếp theo. Nếu không có bản ghi thỏa query, `MongoDbMessageSource.receive()` không tạo message và handler không được gọi.

## 7. Điều chỉnh batch size và thứ tự query

### 7.1. maxMessagesPerPoll khác số bản ghi

Đây là sai sót phổ biến:

~~~text
maxMessagesPerPoll(1)
  = tối đa một MessageSource.receive() trong một poll
  ≠ tối đa một MongoDB document trả về trong query
~~~

Ví dụ `find(...)` trả 10.000 document: vẫn có thể là **một message với List chứa 10.000 phần tử**. Splitter sẽ tiếp tục đưa từng phần tử vào downstream. Hệ thống có thể tốn nhiều RAM và giữ luồng poll lâu.

**Hạn chế kích thước kết quả tại query** hoặc dùng `expectSingleResult(true)` khi phù hợp. Một poll interval dài không tự giải quyết rủi ro query không giới hạn.

### 7.2. Query có limit và sort rõ ràng

Khi muốn lấy tối đa 50 document `NEW` theo `createdAt`, sử dụng Spring Data `Query` và overload DSL nhận `MongoDatabaseFactory`:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.dsl.MongoDb;

@Bean
public IntegrationFlow boundedMongoInboundFlow(
        MongoDatabaseFactory mongoDatabaseFactory) {

    Query query = new Query(Criteria.where("status").is("NEW"))
            .with(Sort.by(Sort.Direction.ASC, "createdAt"))
            .limit(50);

    return IntegrationFlow
            .from(
                MongoDb.inboundChannelAdapter(
                        mongoDatabaseFactory, query)
                    .collectionName("inbox_events")
                    .entityClass(InboxEvent.class),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(5000)
                           .maxMessagesPerPoll(1)))
            .split()
            .channel("mongoEvents")
            .get();
}
~~~

**Đây là phương án thay thế** `mongoInboundFlow` trước đó, không đăng ký cả hai flow cùng quét một tập `NEW` trong bài lab trừ khi bạn cố ý muốn nghiên cứu hiện tượng đọc trùng.

Nếu nhiều bản ghi có cùng `createdAt`, hãy bổ sung sort theo `_id` để có thứ tự ổn định:

~~~java
.with(Sort.by(Sort.Order.asc("createdAt"),
              Sort.Order.asc("_id")))
~~~

Đoạn sort là biểu thức thay thế cho lời gọi `with(...)` ở trên, **không dùng cả hai liên tiếp** khi chỉ muốn một thứ tự sort.

### 7.3. Khi muốn một document mỗi lần poll

Dùng:

~~~java
MongoDb.inboundChannelAdapter(
        mongoTemplate, "{ 'status': 'NEW' }")
    .collectionName("inbox_events")
    .entityClass(InboxEvent.class)
    .expectSingleResult(true)
~~~

Khi đó payload là **một `InboxEvent`**, bỏ bước `split()` trong flow. Tuy nhiên, nếu không cập nhật trạng thái/chỉ mục đọc, `findOne(...)` có thể chọn lại **chính document đó** ở chu kỳ tiếp theo.

## 8. Nguy cơ lớn nhất: lặp lại cùng dữ liệu qua nhiều lần poll

Giả sử collection có:

~~~text
evt-101: NEW
evt-102: NEW
~~~

Sau hai lần poll nếu không đổi trạng thái:

~~~text
Poll 1: evt-101, evt-102
Poll 2: evt-101, evt-102
Poll 3: evt-101, evt-102
...
~~~

Tác động có thể nghiêm trọng khi downstream ghi database, tính phí, gửi email hoặc phát Kafka event: một document có thể dẫn đến **nhiều side effects**.

### 8.1. Giải pháp đơn giản: update khi đã đọc

Spring Integration MongoDB inbound message source hỗ trợ **`updateExpression`**; Java DSL cung cấp `update(...)`. Ví dụ:

~~~java
import org.springframework.data.mongodb.core.query.Update;

MongoDb.inboundChannelAdapter(
        mongoTemplate, "{ 'status': 'NEW' }")
    .collectionName("inbox_events")
    .entityClass(InboxEvent.class)
    .expectSingleResult(false)
    .update(new Update().set("status", "CLAIMED"))
~~~

Bản cập nhật khiến document được truy vấn không còn khớp điều kiện `status=NEW` ở lần poll sau. Ví dụ là **cơ chế tránh đọc lặp đơn giản**, không phải bảo đảm giao hàng.

**Điều cần hiểu trước khi dùng:**

- Update ở message source gắn với **giai đoạn đọc/poll**, không phải một ACK rằng toàn bộ downstream đã commit.
- Nếu document được đổi thành `CLAIMED` rồi service crash trước khi xử lý xong, bản ghi có thể bị **kẹt**, không còn khớp query `NEW`.
- Nếu nhiều instance chạy cùng query, chỉ thêm `update(...)` **không mặc nhiên chứng minh mỗi document được claim nguyên tử bởi đúng một instance**.
- Nếu entity có `status` được đọc là `NEW` trước update, payload đưa downstream có thể vẫn chứa giá trị **cũ**; không coi field trong payload là trạng thái DB sau update.
- Cần chính sách retry, kiểm soát concurrency và quan sát document bị kẹt.

### 8.2. Trạng thái xử lý có lease và khả năng phục hồi

Một state machine hợp lý hơn cho công việc quan trọng:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> PROCESSING: Claim có owner + lease
    PROCESSING --> DONE: Xử lý và commit thành công
    PROCESSING --> RETRY: Lỗi tạm thời
    RETRY --> PROCESSING: Backoff + claim lại
    PROCESSING --> RETRY: Lease hết hạn / worker chết
    RETRY --> DEAD: Vượt số lần thử / lỗi không thể sửa
~~~

Có thể lưu các trường:

~~~json
{
  "_id": "evt-101",
  "status": "PROCESSING",
  "claimOwner": "worker-3",
  "leaseUntil": "2026-11-23T09:00:00Z",
  "attempt": 2,
  "lastErrorCode": null
}
~~~

Trong ứng dụng production, nếu nhiều instance cùng đọc, hãy dùng thao tác MongoDB **claim nguyên tử có điều kiện**, ví dụ logic dựa trên `findAndModify` hoặc mô hình tương đương phù hợp với document và transaction. Đảm bảo:

1. Chỉ claim bản ghi đang `NEW` hoặc bản ghi có lease được phép thu hồi.
2. Gán `claimOwner`, `leaseUntil` và `attempt` cùng lúc với việc claim.
3. Worker xử lý document trong khoảng lease; gia hạn nếu công việc kéo dài.
4. Sau thành công, đánh dấu `DONE` theo điều kiện owner/version phù hợp.
5. Sau lỗi, ghi trạng thái `RETRY` và `nextAttemptAt` hoặc `DEAD`.
6. Thiết kế **idempotency** tại tác động nghiệp vụ vì retry có thể tạo duplicate.

**Quan trọng:** nếu yêu cầu claim nguyên tử xuyên nhiều instance, mô hình polling message source mặc định cần được đánh giá và có thể cần **custom MessageSource / outbound gateway / service claim**. Không nên ngụ ý `query + update` mặc định của adapter là một transaction bảo đảm exactly once.

### 8.3. Không nhầm transaction synchronization với MongoDB transaction

Spring Integration có **transaction synchronization** cho poller, cho phép thực thi hành động sau commit hoặc rollback của transaction đang được quản lý. Tài liệu cũng nêu `PseudoTransactionManager` để tạo callback synchronization khi không có transaction thực.

**PseudoTransactionManager không khiến MongoDB tự trở thành giao dịch nguyên tử.** Nếu cần MongoDB multi-document transaction, phải cấu hình transaction manager/replica set và thiết kế transaction thật phù hợp. Ngay cả transaction thật cũng không tự làm các side effect HTTP/Kafka thành một distributed exactly-once transaction.

## 9. Header và hợp đồng Message

Một message từ MongoDB inbound có thể bao gồm:

~~~text
Message<List<InboxEvent>>:
  payload = [evt-101, evt-102]
  headers:
    mongo_collectionName = "inbox_events"
    id = UUID của Spring Message
    timestamp = thời điểm tạo Message
~~~

Sau splitter, mỗi `Message<InboxEvent>` có thể kèm headers thích hợp từ message đầu vào và thêm metadata sequence/group của splitter tùy cấu hình.

| Thành phần | Từ đâu? | Ý nghĩa |
|---|---|---|
| `Message.payload` | `find()` hoặc `findOne()` | Dữ liệu truy vấn MongoDB |
| `MongoHeaders.COLLECTION_NAME` | MongoDB message source | Collection đã được truy vấn |
| `MessageHeaders.ID` | Spring Messaging | Định danh của message nội bộ |
| `MessageHeaders.TIMESTAMP` | Spring Messaging | Thời gian tạo message |
| `InboxEvent.id` | MongoDB document `_id` | Định danh nghiệp vụ/tài liệu, phù hợp làm cơ sở idempotency |
| `status / attempt / leaseUntil` | Document nếu ứng dụng quy định | Trạng thái xử lý và phục hồi |

**Không dùng UUID của Spring Message như event ID bền vững.** Một document bị poll lại sẽ tạo message khác, với UUID message khác. Để chống trùng, dùng `_id` của document hoặc khóa nghiệp vụ ổn định.

Nếu đưa payload sang JMS, AMQP, Kafka hoặc HTTP, chuyển đổi sang DTO/event schema tường minh. Không tự đưa tất cả message headers ra ngoài, đặc biệt các thông tin điều hành hệ thống hoặc object Java chỉ có ý nghĩa trong process.

## 10. Ví dụ XML namespace

Dự án sử dụng Spring Integration XML có thể cấu hình tương đương:

~~~xml
<int-mongodb:inbound-channel-adapter
        id="mongoInboundAdapter"
        channel="mongoQueryResults"
        mongo-template="mongoTemplate"
        collection-name="inbox_events"
        entity-class="example.mongodb.InboxEvent"
        query="{ 'status': 'NEW' }"
        auto-startup="false">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-mongodb:inbound-channel-adapter>
~~~

Đoạn trên phải nằm trong XML Spring có khai báo namespace `int` và `int-mongodb` đúng phiên bản, cùng bean `mongoTemplate` và channel `mongoQueryResults`.

- `query` nhận truy vấn tĩnh.
- `query-expression` nhận SpEL trả chuỗi query hoặc đối tượng `Query` tùy API; **không cấu hình đồng thời** với `query`.
- `collection-name` và `collection-name-expression` là hai cách chọn collection.
- `mongo-template` và `mongodb-factory` là các đường cấu hình thay thế, **không chỉ định cả hai** cho cùng adapter.
- `entity-class` xác định kiểu object được đọc.
- `auto-startup=false` phù hợp khi muốn chủ động start qua quy trình test/bảo trì; production có thể để tự khởi động theo lifecycle.

XML ví dụ không tự cấu hình một splitter. Nếu `expectSingleResult` ở mặc định, downstream của `mongoQueryResults` phải xử lý payload `List` hoặc cấu hình splitter riêng.

## 11. Polling so với change stream

| Tiêu chí | Polling inbound | Change stream inbound |
|---|---|---|
| Cơ chế | Query định kỳ | Subscribe các thay đổi được MongoDB phát |
| Độ trễ | Phụ thuộc lịch poll, thời gian query và xử lý | Thường thấp khi luồng thay đổi hoạt động |
| Payload | Entity hoặc List query result | ChangeStreamEvent hoặc body tùy cấu hình |
| Tải DB | Các query ngay cả khi không có thay đổi | Theo hoạt động change stream và subscription |
| Theo dõi trạng thái | Cần query/update/claim hoặc checkpoint do app thiết kế | Cần lưu/resume token và xử lý retry/resubscription phù hợp |
| Yêu cầu môi trường | Kết nối MongoDB query bình thường | MongoDB deployment có hỗ trợ change streams và quyền thích hợp |
| Tình huống phù hợp | Work queue đơn giản, batch import, xử lý định kỳ | Phản ứng theo update/insert, CDC-style integration |

Spring Integration có `MongoDbChangeStreamMessageProducer` và Java DSL `MongoDb.changeStreamInboundChannelAdapter(...)` cho trường hợp change stream. **Đây là endpoint khác** với `MongoDb.inboundChannelAdapter(...)` của bài này. Không suy luận MongoDB inbound polling tự có resume token hoặc tự theo dõi tất cả insert theo thứ tự thời gian.

## 12. Error handling, retry và vòng đời

### 12.1. Phân loại lỗi

| Lỗi | Điểm phát sinh | Cách xử lý |
|---|---|---|
| MongoDB không kết nối được | Trong một lần poll/query | Ghi metric/error channel phù hợp, backoff/retry, kiểm tra timeout |
| Sai collection hoặc quyền | Khi query MongoDB | Sửa cấu hình và role DB, không retry mù không giới hạn |
| Query quá rộng | `find()` trả List lớn | Giới hạn query, limit/sort/projection và index |
| Document không map được | Trong Mongo mapping/convert | Kiểm tra schema/version, error handling/quarantine |
| Không có kết quả | `receive()` trả null | Không phải lỗi, không phát message |
| Handler HTTP/Kafka/DB lỗi | Downstream của channel | Retry có giới hạn, idempotency, không đánh dấu DONE trước commit |
| Process chết sau claim | Trạng thái `PROCESSING` kẹt | Lease timeout, recovery/reconciliation |
| Nhiều instance cùng đọc | Trùng claim/side effect | Claim nguyên tử, owner/version và idempotency |
| Consumer backlog | Queue/executor đầy | Giảm batch/rate, bounded queue và backpressure |
| Restart poller | Source được start lại và query tiếp | Không có replay đảm bảo riêng nếu chưa thiết kế trạng thái |

### 12.2. Vòng đời của adapter

Polling inbound endpoint được Spring quản lý theo lifecycle. Với `autoStartup=true`, endpoint có thể bắt đầu poll khi context khởi động. Nếu DB chưa sẵn sàng, cần chính sách lỗi/health và retry phù hợp; không mặc định khởi động context đồng nghĩa một lần query đã thành công.

Khi `stop()`, poller ngừng tạo các lần nhận mới theo lifecycle; những message đã được lấy hoặc giao cho xử lý bất đồng bộ có thể còn đang chạy. Nếu dùng `QueueChannel`/`ExecutorChannel`, cần kế hoạch **drain** và kiểm tra việc commit khi shutdown.

**Không dựa vào `Thread.sleep` để đảm bảo đã xử lý hết.** Đo queue depth, active tasks, state DB và điều kiện dừng có deadline. Đối với luồng đọc dữ liệu bền, khôi phục sau restart phụ thuộc cách document được claim/ack, không chỉ riêng Spring endpoint startup.

### 12.3. Poller và error channel

Khi exception xuất hiện trong quá trình poll hoặc downstream, Spring Integration có cơ chế error channel/advice tùy cấu hình đồng bộ/bất đồng bộ. Cần xác nhận **đường lỗi thật** của poller trong ứng dụng:

- Query lỗi có thể xảy ra **trước khi có một message payload**.
- Lỗi validate xảy ra **sau khi message đã được tạo**.
- Lỗi commit xảy ra **sau khi xử lý nghiệp vụ**.
- Document bị bỏ qua do query không khớp **không tạo ErrorMessage**.

Không chỉ bắt mọi exception rồi log và tiếp tục; cần biết khi nào được retry, trạng thái document nào cần chuyển sang `RETRY` và lỗi nào cần báo động.

## 13. Quan sát và tối ưu vận hành

Một số chỉ số phù hợp:

| Metric | Mục đích |
|---|---|
| `mongo_poller_runs_total` | Số lần poll thực hiện |
| `mongo_query_duration_seconds` | Độ trễ truy vấn |
| `mongo_query_results_total` | Số document lấy được |
| `mongo_empty_polls_total` | Các lần query không có kết quả |
| `mongo_inbound_messages_total` | Số Spring Messages do adapter phát |
| `mongo_handler_processed_total` | Số document xử lý thành công |
| `mongo_handler_errors_total` | Số lỗi xử lý downstream |
| `mongo_processing_lease_expired_total` | Số document `PROCESSING` quá hạn cần phục hồi |
| `mongo_processing_lag_seconds` | Thời gian từ createdAt tới lúc xử lý |
| `mongo_queue_depth` | Số công việc đang chờ ở downstream |

**Đừng nhầm:**
- Số `Message<List<InboxEvent>>` với số document.
- Poll thành công với xử lý nghiệp vụ thành công.
- `update(status=CLAIMED)` với ACK rằng downstream đã commit.
- `MessageHeaders.ID` với `InboxEvent.id`.

Trong production cần index phù hợp với query, ví dụ nếu lọc `status` và sort `createdAt`:

~~~javascript
db.inbox_events.createIndex({ status: 1, createdAt: 1, _id: 1 })
~~~

Không tạo index tùy tiện trên collection lớn mà chưa đánh giá chi phí build/index write load. Khi số document `DONE` tăng mạnh, quy định retention/archive phù hợp để collection không phình vô hạn.

Với nhiều instance, ghi metric theo instance và tổng hợp đúng kiểu; không dùng label theo từng `_id` hoặc device ID nếu có số lượng cực lớn.

## 14. Kiểm thử MongoDB inbound adapter

### 14.1. Unit test logic xử lý

Tách nghiệp vụ ra khỏi Spring Integration khi có thể:

~~~java
public final class InboxValidator {

    public void validate(InboxEvent event) {
        if (event == null
                || event.id() == null
                || event.id().isBlank()
                || event.deviceId() == null
                || event.deviceId().isBlank()
                || !Double.isFinite(event.temperatureC())) {
            throw new IllegalArgumentException(
                    "Invalid MongoDB inbox event");
        }
    }
}
~~~

JUnit test:

~~~java
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class InboxValidatorTest {

    @Test
    void acceptsValidDocument() {
        InboxEvent event = new InboxEvent(
                "evt-101", "DEVICE_READING", "node-7",
                26.5, "NEW", Instant.parse("2026-11-01T08:00:00Z"));

        assertDoesNotThrow(
                () -> new InboxValidator().validate(event));
    }

    @Test
    void rejectsMissingDeviceId() {
        InboxEvent event = new InboxEvent(
                "evt-102", "DEVICE_READING", null,
                25.9, "NEW", Instant.parse("2026-11-01T08:00:00Z"));

        assertThrows(IllegalArgumentException.class,
                () -> new InboxValidator().validate(event));
    }
}
~~~

Đây là **unit test**, không xác nhận MongoDB query hoặc poller hoạt động.

### 14.2. Integration test với MongoDB thật

Có thể dùng một MongoDB test instance do môi trường CI quản lý hoặc **Testcontainers** khi runner hỗ trợ Docker. Kiểm thử nên đi qua:

~~~text
Seed MongoDB document
       |
       v
MongoDbMessageSource + poller
       |
       v
QueueChannel test sink
       |
       v
JUnit receive(timeout) + assert
~~~

Một flow riêng cho test có thể kết thúc bằng `QueueChannel` thay vì handler thật:

~~~java
@Bean("mongoTestSink")
public org.springframework.integration.channel.QueueChannel testSink() {
    return new org.springframework.integration.channel.QueueChannel(16);
}
~~~

Trong cấu hình **dành riêng cho test**, sau splitter chuyển output sang `mongoTestSink`. JUnit chờ:

~~~java
Message<?> result = testSink.receive(5000);
assertNotNull(result, "No MongoDB event received");
assertInstanceOf(InboxEvent.class, result.getPayload());
assertEquals("evt-101", ((InboxEvent) result.getPayload()).id());
~~~

Đây là **đoạn assertion minh họa**, đặt trong test class có inject `testSink` và context đã seed data. Tách test flow khỏi business handler để không có hai consumer cùng tranh một `QueueChannel`.

Các case cần bao phủ:

1. Query trả **0 document**: không có message trong test sink sau timeout hữu hạn.
2. Query trả **1 hoặc nhiều document**: kiểm tra payload dạng List trước splitter, từng entity sau splitter.
3. Có hai document `NEW`: đảm bảo không hiểu nhầm `maxMessagesPerPoll(1)` là chỉ một document.
4. Để query read-only chạy nhiều chu kỳ: xác nhận hiện tượng lặp message xảy ra.
5. Bật `update(...)` ở **test riêng**: xem trạng thái trong MongoDB sau poll và đánh giá crash trước xử lý.
6. Mô phỏng MongoDB ngừng hoạt động và hoạt động trở lại: kiểm tra error policy, readiness và retry.
7. Chạy hai instance cùng query: kiểm tra trùng claim/idempotency, không giả định adapter tự giải quyết.
8. Dừng/start endpoint: xác minh các document chưa `DONE` có thể được phục hồi theo chính sách.

**Dọn dữ liệu lab** bằng collection/database test riêng; không dùng bộ kiểm thử phá hủy dữ liệu trong MongoDB production.

## 15. Bảo mật và kiểm soát truy cập

- Dùng tài khoản MongoDB có **least privilege**: đọc đúng collection và chỉ cấp update nếu adapter thực sự cần thay đổi trạng thái.
- Không hard-code credentials, connection string có mật khẩu hoặc token trong source code/log.
- Thiết lập TLS, network policy, quyền kết nối, secret rotation và timeout thích hợp theo môi trường.
- Hạn chế `query-expression` / `collection-name-expression` không đáng tin cậy; **đừng cho input của người dùng tùy ý điều khiển collection/query**.
- Kiểm tra kiểu/size/schema của document trước khi phát ra HTTP, Kafka, JMS/AMQP hoặc email.
- Nếu chứa dữ liệu nhạy cảm, ghi log theo `eventId` và mã lỗi, không dump toàn bộ document.
- Với polling quá thường xuyên, cấu hình index, batch limit và backoff để không gây quá tải MongoDB.

MongoDB là nguồn dữ liệu bền nhưng **độ bền của nguồn không đồng nghĩa độ tin cậy của toàn pipeline**. Nếu handler gửi tới hệ thống khác rồi crash, bản ghi có thể cần retry; nếu làm lại, phải tránh gây side effect trùng lặp.

## 16. Bài thực hành tổng hợp

Bài tập: tạo một service **MongoDB → Spring Integration → xử lý telemetry**, mở rộng sang Kafka hoặc HTTP khi cần.

### Phần A — Polling cơ bản

1. Tạo database `adapter_lab`, collection `inbox_events` và seed hai document `status=NEW`.
2. Viết `InboxEvent` với `@Document`, `@Id` và các field tương ứng.
3. Cấu hình `MongoDb.inboundChannelAdapter(...)`, `entityClass(InboxEvent.class)`, `collectionName("inbox_events")`.
4. Dùng `Pollers.fixedDelay(5000).maxMessagesPerPoll(1)`, ghi log mỗi lần query và mỗi message xử lý.
5. Thử **bỏ `split()`**: quan sát payload là List. Thêm `split()` lại để mỗi event vào một message.
6. Chạy qua hai chu kỳ không update status; giải thích hiện tượng cùng document xuất hiện lại.

### Phần B — Query và vòng đời

1. Dùng `Query` có `limit(50)`, sort theo `createdAt` và `_id`; giải thích vì sao maxMessagesPerPoll không thay thế query limit.
2. Tạo thêm vài document `status=DONE`, xác nhận query NEW không đọc chúng.
3. Tắt MongoDB trong môi trường lab, quan sát lỗi poll, bật lại và xác minh khả năng phục hồi.
4. Tắt/start polling endpoint; phân biệt document chưa đọc, document đã phát message và document đã commit nghiệp vụ.

### Phần C — Độ tin cậy

1. Dùng `update(new Update().set("status", "CLAIMED"))` ở test riêng, xem document còn khớp query NEW không.
2. Giả lập crash sau claim nhưng trước khi xử lý; đề xuất lease và recovery.
3. Chạy hai worker đọc cùng collection; nêu rủi ro race, sử dụng claim nguyên tử khi cần.
4. Tạo unique key phía downstream từ `_id` để chống trùng khi retry.
5. Phân biệt transaction synchronization của Spring Integration với MongoDB transaction thực.
6. Thiết kế metric query count, document count, processing lag, retry và error.

### Phần D — Tích hợp hệ thống khác

1. Chuyển `InboxEvent` thành DTO gửi Kafka/JMS/AMQP qua `MessageChannel`, chỉ chọn field được phép.
2. Nếu muốn thay polling bằng change stream, liệt kê điều kiện cần có và cách quản lý resume token.
3. Nếu dữ liệu lớn hoặc cần replay, cân nhắc outbox/broker và idempotent consumer.
4. So sánh MongoDB inbound adapter với outbound gateway khi cần đọc một document theo request HTTP.

**Câu hỏi tự đánh giá:**

- Ai kích hoạt `MongoDbMessageSource.receive()`?
- Vì sao `expectSingleResult(false)` có thể tạo một `Message<List<T>>`?
- `maxMessagesPerPoll(1)` có giới hạn query trả đúng một document không?
- Vì sao một query `status=NEW` được lặp sẽ đọc lại dữ liệu?
- `update(...)` ở source có đồng nghĩa handler đã commit không?
- Làm sao để tránh hai instance cùng xử lý một document khi có concurrency?
- `MongoHeaders.COLLECTION_NAME` cung cấp thông tin gì?
- Khi không có document, adapter phát message rỗng hay không tạo message?
- Vì sao `PseudoTransactionManager` không tự biến mọi thao tác MongoDB thành transaction?
- Khi nào nên chọn change stream hoặc outbound gateway thay polling inbound?

## 17. Tài liệu tham khảo

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): inbound adapter, query, XML, update expression, change stream, reactive và transaction synchronization.
- [Spring Integration API — MongoDb DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): factory `inboundChannelAdapter`, các overload MongoOperations/MongoDatabaseFactory.
- [Spring Integration API — MongoDbMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/inbound/MongoDbMessageSource.html): `find`/`findOne`, payload dạng List hoặc entity, kết quả rỗng.
- [Spring Integration API — MongoDbMessageSourceSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/AbstractMongoDbMessageSourceSpec.html): `entityClass`, `collectionName`, `expectSingleResult`, `update`.
- [Spring Integration Reference — Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html): poller, fixed-delay, max-messages-per-poll, transaction.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): `MongoTemplate`, `Query`, entity mapping, index và transaction.

## Kết luận

**MongoDB inbound channel adapter** là thành phần **đọc MongoDB theo lịch poll** và đưa kết quả vào `MessageChannel`. Khi dùng `MongoDbMessageSource`, hãy nhớ **một lần poll có thể phát một message chứa List document**; splitter và `expectSingleResult` quyết định cách dữ liệu đến handler.

Trong **SPRING_INTEGRATION_ADAPTERS**, adapter chỉ giải quyết **cách nhận dữ liệu từ nguồn**. Độ tin cậy nghiệp vụ còn phụ thuộc query, batch limit, trạng thái xử lý, claim/lease, idempotency, retry, transaction và vòng đời. Muốn nối dữ liệu từ MongoDB sang HTTP, Kafka, JMS, AMQP, file, SFTP hay database khác, hãy đặt rõ hợp đồng message và quyết định khi nào một document thật sự được coi là **xử lý hoàn tất**.
