# MongoDbMessageSource polling trong Spring Integration

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **`MongoDbMessageSource`** là gì, tại sao nó thuộc mẫu **Polling Consumer** và vì sao phải đi cùng `SourcePollingChannelAdapter` / poller để tạo một luồng dữ liệu liên tục.
- Phân biệt vai trò của `MongoOperations`, `MongoTemplate`, `MongoDatabaseFactory`, `MongoDbMessageSource`, `MessageChannel` và downstream `MessageHandler`.
- Dùng Spring Integration Java DSL hoặc XML để đọc một collection MongoDB theo lịch `fixedDelay`, `fixedRate` hoặc cron.
- Hiểu chính xác **`expectSingleResult(false)` → `find()` → `Message<List<T>>`** và **`expectSingleResult(true)` → `findOne()` → `Message<T>`**; biết cách xử lý kết quả rỗng.
- Phân biệt **`maxMessagesPerPoll`** với **`Query.limit`**, giới hạn mỗi batch, sort, projection, index và memory consumption.
- Tạo query/collection động bằng **SpEL expression** được đánh giá ở mỗi lượt poll, thay vì đọc `payload` của một request không tồn tại.
- Hiểu tùy chọn **`updateExpression`** để cập nhật document vừa đọc, đồng thời nhận diện rủi ro crash, race, duplicate và việc đánh dấu trước khi downstream commit.
- Xây dựng chính sách **claim/lease, retry, idempotency, transaction**, error channel, observability và graceful shutdown khi nhiều worker cùng đọc dữ liệu.
- Viết unit test logic xử lý, test `MongoDbMessageSource.receive()` và integration test MongoDB → Spring Message → test channel.

Bài thuộc chương **Adapter MongoDB** trong module **SPRING_INTEGRATION_ADAPTERS**. Phạm vi module là kết nối hệ thống ngoài vào Spring Integration bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành luồng trao đổi qua file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, cùng hợp đồng message, xử lý lỗi và vòng đời kết nối. **MongoDbMessageSource là cầu nối từ MongoDB vào phía đầu nguồn của flow**; nó không phải hàng đợi bền, không tự tạo bảo đảm exactly-once và không thay thế một cơ chế claim đồng bộ giữa nhiều instance.

## 1. Bài toán: poll những document đang chờ xử lý

Một ứng dụng nhận dữ liệu sensor từ HTTP hoặc UDP và lưu vào collection `inbox_events` của MongoDB. Dịch vụ Integration khác cần định kỳ lấy các document có `status=NEW`, chuẩn hóa và gửi sang một hệ thống phân tích hoặc broker.

Document minh họa:

~~~json
{
  "_id": "evt-101",
  "tenantId": "tenant-a",
  "deviceId": "node-7",
  "temperatureC": 26.5,
  "status": "NEW",
  "createdAt": "2026-11-20T08:00:00Z"
}
~~~

Yêu cầu:

1. Mỗi 5 giây kiểm tra collection `inbox_events`.
2. Chỉ lấy document thuộc `tenant-a` và trạng thái `NEW`.
3. Giới hạn mỗi lần query tối đa 50 document, sort theo `createdAt` rồi `_id`.
4. Phát **mỗi event thành một Spring Message** cho handler.
5. Không gửi lại vô hạn một event đã xử lý; phục hồi được nếu worker chết giữa chừng.
6. Không khẳng định đã xử lý thành công chỉ vì một document đã được query.

~~~mermaid
flowchart LR
    T["Poller<br/>mỗi 5 giây"] --> S["MongoDbMessageSource.receive()"]
    S --> Q["MongoOperations.find(Query)"]
    DB[("MongoDB<br/>inbox_events")] <--> Q
    Q --> L["Message<List<InboxEvent>>"]
    L --> SP["Splitter"]
    SP -->|"Message<InboxEvent>"| CH["MessageChannel"]
    CH --> H["Validate / Business handler"]
    H --> O["HTTP / Kafka / JMS / AMQP / DB"]
~~~

**Điểm cốt lõi:** source **không giữ một kết nối push event kiểu change stream**. Nó thực hiện query theo lịch của poller. MongoDB collection có thể chứa cùng dữ liệu qua nhiều chu kỳ, vì thế **trạng thái xử lý và idempotency** là trách nhiệm của thiết kế nghiệp vụ.

## 2. MongoDbMessageSource đứng ở đâu trong kiến trúc?

Các thành phần liên quan:

| Thành phần | Vai trò | Ai kích hoạt? |
|---|---|---|
| `MongoClient` | MongoDB Java driver, kết nối/server selection/pool | Do client và Spring Data sử dụng |
| `MongoDatabaseFactory` | Cung cấp database và session theo cấu hình | Spring Data |
| `MongoOperations` / `MongoTemplate` | Thao tác `find`, `findOne`, `save`, `update` | Message source hoặc handler |
| **`MongoDbMessageSource`** | Thực thi query và tạo Spring `Message` | **Poller gọi `receive()`** |
| **`SourcePollingChannelAdapter`** | Tạo lịch để gọi source và gửi message | Spring Integration lifecycle/scheduler |
| `MessageChannel` | Đưa message từ source sang flow | Adapter gửi, handler nhận |
| `Splitter` | Chia `List<T>` thành nhiều `Message<T>` | Flow khi có danh sách |
| `@ServiceActivator` | Xử lý từng event | Có message đầu vào |
| `MongoDbOutboundGateway` | Truy vấn MongoDB cho **từng request/reply** | Caller gửi request message |
| `MongoDbStoringMessageHandler` | Ghi payload vào MongoDB | Có message từ upstream |
| `MongoDbChangeStreamMessageProducer` | Theo dõi event thay đổi kiểu change stream | Subscription; endpoint khác |

**Không nhầm `MongoDbMessageSource` với MongoDB outbound gateway.** Source lấy dữ liệu theo lịch, không yêu cầu request message. Gateway nhận message có payload/headers của caller, query theo request và trả reply.

### 2.1. Cơ chế một lượt poll

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant S as MongoDbMessageSource
    participant M as MongoOperations
    participant D as MongoDB
    participant C as MessageChannel
    P->>S: receive()
    S->>M: find(query, entityClass, collection)
    M->>D: MongoDB query
    D-->>M: List documents
    M-->>S: List<InboxEvent>
    alt List không rỗng
        S-->>P: Message<List<InboxEvent>>
        P->>C: send(message)
    else Không có document
        S-->>P: null
        Note over P: Không gửi Message
    end
~~~

Khi source trả `null` vì không có dữ liệu, đó thường là một **empty poll bình thường**, không phải MongoDB exception.

## 3. Hợp đồng payload: List theo mặc định, entity khi chọn single

Javadoc `MongoDbMessageSource` mô tả hai chế độ:

| Cấu hình | API MongoOperations | Payload khi tìm thấy | Không có kết quả |
|---|---|---|---|
| `expectSingleResult(false)`, **mặc định** | `find(Query, Class, collection)` | **`List<InboxEvent>`** trong **một Message** | List rỗng được xử lý như không có Message |
| `expectSingleResult(true)` | `findOne(Query, Class, collection)` | **`InboxEvent`** trong **một Message** | `null` → không có Message |

Ví dụ có ba document khớp query:

~~~text
Poller.run()
  └─ source.receive()
       └─ MongoDB.find() -> [evt-101, evt-102, evt-103]
            └─ 1 Message<List<InboxEvent>>
                 └─ splitter
                     ├─ Message<InboxEvent>(evt-101)
                     ├─ Message<InboxEvent>(evt-102)
                     └─ Message<InboxEvent>(evt-103)
~~~

**Một list có 50 document vẫn chỉ là một message** ở đầu ra message source. Khi dùng `split()`, downstream có thể nhận 50 messages riêng.

### 3.1. Khi nào dùng expectSingleResult(true)?

Chọn single-result khi bạn muốn **mỗi lần `receive()` chọn tối đa một document**, chẳng hạn một công việc đơn giản được chọn theo sort. Tuy nhiên:

- `findOne` **không tự đánh dấu đã tiêu thụ**.
- Nếu query vẫn khớp cùng document, các poll sau có thể lấy lại **đúng document đó**.
- Nếu “document đầu tiên” có ý nghĩa nghiệp vụ, phải sort rõ ràng; mặc định không nên giả định MongoDB trả bản ghi cũ nhất.
- Với nhiều worker, `findOne + update` không mặc nhiên là thao tác claim nguyên tử.

### 3.2. Đặt entityClass tường minh

Đặt `entityClass(InboxEvent.class)` để contract handler rõ ràng. Khi không khai báo, kiểu mặc định phụ thuộc API/phiên bản; tránh viết code handler ép kiểu mù sang `InboxEvent` khi source đang trả một kiểu BSON/driver khác.

### 3.3. Message headers

MongoDB inbound source cung cấp metadata collection:

~~~text
Message<List<InboxEvent>>
  payload:
    - InboxEvent(evt-101)
    - InboxEvent(evt-102)
  headers:
    mongo_collectionName = "inbox_events"
    id = <Spring Message ID>
    timestamp = <Spring Message timestamp>
~~~

Trong Java, truy cập bằng hằng số `MongoHeaders.COLLECTION_NAME` thuộc `org.springframework.integration.mongodb.support.MongoHeaders`. Header này mô tả **collection nguồn**, không phải field MongoDB tự được lưu trong mỗi document.

Khi splitter tạo message con, một số headers được truyền theo logic Spring Integration, đồng thời có thể thêm sequence headers. Nếu downstream phụ thuộc cụ thể vào một header, hãy assert sự tồn tại và kiểu của nó trong integration test.

## 4. Tạo dự án và dữ liệu thử

### 4.1. Maven dependencies

Với một dự án **Spring Boot 3.x** có dependency management tương thích:

~~~xml
<!-- Đặt trong <dependencies> của pom.xml -->
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

Chọn BOM/version tương thích với Spring Boot/Spring Data/Spring Integration thực tế. Bài này dùng **blocking `MongoOperations`** và MongoDB synchronous driver, không dùng reactive API.

### 4.2. URI MongoDB local

Trong `application.yml` của lab:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/adapter_lab
~~~

MongoDB local không mật khẩu chỉ là ví dụ. Production phải quản lý credentials qua secret manager/config, bật TLS khi cần, giới hạn quyền theo database/collection và cấu hình timeout, pool phù hợp.

Nếu Spring Boot đã tạo `MongoTemplate`/`MongoOperations`, hãy **inject bean đó**. Không khai báo thêm một MongoClient/factory/template trùng nếu không có lý do kiến trúc rõ ràng.

### 4.3. Tạo dữ liệu bằng mongosh

~~~javascript
use adapter_lab

db.inbox_events.insertMany([
  {
    _id: "evt-101",
    tenantId: "tenant-a",
    deviceId: "node-7",
    temperatureC: 26.5,
    status: "NEW",
    createdAt: ISODate("2026-11-20T08:00:00Z")
  },
  {
    _id: "evt-102",
    tenantId: "tenant-a",
    deviceId: "node-8",
    temperatureC: 25.8,
    status: "NEW",
    createdAt: ISODate("2026-11-20T08:00:01Z")
  },
  {
    _id: "evt-103",
    tenantId: "tenant-a",
    deviceId: "node-9",
    temperatureC: 24.9,
    status: "DONE",
    createdAt: ISODate("2026-11-20T08:00:02Z")
  }
])

db.inbox_events.find({
  tenantId: "tenant-a",
  status: "NEW"
}).sort({ createdAt: 1, _id: 1 }).limit(50)
~~~

Chạy seed lần hai với ID cũ có thể phát sinh duplicate-key exception. Dùng database test riêng và quy trình seed idempotent; không xóa collection production để làm lại bài tập.

### 4.4. Entity Java 17+

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "inbox_events")
public record InboxEvent(
        @Id String id,
        String tenantId,
        String deviceId,
        BigDecimal temperatureC,
        String status,
        Instant createdAt) {
}
~~~

Spring Data MongoDB sẽ dùng mapping/converter phù hợp để chuyển document sang `InboxEvent`. Nếu collection có dữ liệu không đồng nhất, dùng validation trước khi gửi hệ thống khác; ánh xạ Java thành công chưa chứng minh tất cả business fields hợp lệ.

## 5. Cấu hình Java DSL: inbound adapter với polling

Ví dụ dễ đọc nhất là Java DSL với source factory `MongoDb.inboundChannelAdapter(...)`:

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
public class MongoInboxInboundConfig {

    @Bean("inboxEvents")
    public MessageChannel inboxEvents() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow mongoInboxInboundFlow(
            MongoOperations mongoOperations) {

        return IntegrationFlow
                .from(
                    MongoDb.inboundChannelAdapter(
                            mongoOperations,
                            "{ 'tenantId': 'tenant-a', 'status': 'NEW' }")
                        .collectionName("inbox_events")
                        .entityClass(InboxEvent.class)
                        .expectSingleResult(false),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(1)))
                .split()
                .channel("inboxEvents")
                .get();
    }
}
~~~

**Giải thích từng phần:**

1. `MongoDb.inboundChannelAdapter(MongoOperations, String)` tạo `MongoDbMessageSourceSpec` với query tĩnh.
2. `collectionName("inbox_events")` xác định tập dữ liệu cần đọc.
3. `entityClass(InboxEvent.class)` ánh xạ document vào type rõ ràng.
4. `expectSingleResult(false)` dùng `find()` và phát `Message<List<InboxEvent>>`.
5. `Pollers.fixedDelay(5000)` kích hoạt source theo chu kỳ có **fixed delay** 5.000 ms giữa các lần kích hoạt.
6. `maxMessagesPerPoll(1)` giới hạn tối đa **một lần source nhận message trong mỗi poll task**, **không** giới hạn một document.
7. `.split()` tách danh sách thành từng `InboxEvent` riêng.
8. `.channel("inboxEvents")` chuyển messages sang consumer do ứng dụng đăng ký.

**Cảnh báo lab:** query chỉ đọc `status=NEW` nên `evt-101` và `evt-102` có thể xuất hiện **lặp lại ở mọi chu kỳ**, dù splitter/handler hoạt động chính xác. Đây không phải lỗi framework. Hãy làm bài đọc đơn giản trước rồi chuyển sang phần claim/retry để xử lý production.

### 5.1. Một handler để quan sát event

~~~java
package example.mongodb;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.mongodb.support.MongoHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class InboxEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(InboxEventObserver.class);

    @ServiceActivator(inputChannel = "inboxEvents")
    public void handle(Message<InboxEvent> message) {
        InboxEvent event = message.getPayload();

        if (event.id() == null || event.id().isBlank()
                || event.deviceId() == null
                || event.tenantId() == null
                || event.status() == null) {
            throw new IllegalArgumentException(
                    "Invalid MongoDB inbox event");
        }

        String collection = message.getHeaders()
                .get(MongoHeaders.COLLECTION_NAME, String.class);

        log.info("Polled event id={}, deviceId={}, collection={}",
                event.id(), event.deviceId(), collection);

        // Demo chỉ quan sát; chưa ACK, chưa claim, chưa ghi DONE.
    }
}
~~~

Observer này có thể nhận lại cùng ID qua nhiều poll. **Log thành công không đồng nghĩa downstream đã commit**; nếu cần đảm bảo tác động nghiệp vụ, phải có cơ chế đánh dấu hoàn thành theo điều kiện sau xử lý.

### 5.2. Đường truyền message và sự khác biệt loại channel

Trong flow ví dụ, `DirectChannel` gửi đồng bộ tới subscriber. Nếu business handler gọi HTTP/Kafka/DB mất nhiều thời gian, nó có thể làm việc poll kéo dài. Đặt một `ExecutorChannel` hoặc `QueueChannel` giữa source và handler có thể tách thread nhưng làm phức tạp **acknowledgment, error propagation và thứ tự xử lý**.

**Không kết luận “poll đã xong” đồng nghĩa “handler đã lưu bền”.** Với queue/executor, message có thể mới được chấp nhận vào bộ nhớ. Nếu process crash, message chưa được persist ở một nguồn bền có thể mất.

## 6. Poller: fixedDelay, fixedRate, maxMessagesPerPoll

Poller cấu hình **tần suất** và **số lần gọi `MessageSource.receive()`**. Với inbound adapter, poller là bắt buộc trừ khi dự án đã khai báo global default poller phù hợp.

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| `fixedDelay` | Lên lần kích hoạt kế tiếp sau một khoảng delay tính từ lần kết thúc trước | `fixedDelay(5000)` |
| `fixedRate` | Lịch chạy theo một nhịp định kỳ | `fixedRate(5000)` |
| `cron` | Lịch theo biểu thức cron | Mỗi phút/giờ theo nghiệp vụ |
| `maxMessagesPerPoll` | Số **lần gọi receive** tối đa trong mỗi poll task | `1` |
| `receiveTimeout` | Điều khiển thời gian gửi/nhận message ở tầng polling tùy endpoint/channel | **Không phải timeout MongoDB query** |
| Poller `taskExecutor` | Chuyển poll task sang thread pool khi cấu hình | Cần kiểm soát concurrency |
| `autoStartup` | Có tự khởi động endpoint khi context start không | true/false |
| `errorChannel` | Nơi nhận lỗi do poller xử lý theo cấu hình | Cần subscriber và chính sách retry |

### 6.1. maxMessagesPerPoll không giới hạn số document

~~~text
Poller configuration: maxMessagesPerPoll(1)
Query MongoDB:        find(status=NEW)
MongoDB result:       300 documents

Source receive():     1 lần
Message payload:      List<InboxEvent> dài 300
Splitter output:      300 Message<InboxEvent>
~~~

Nếu muốn mỗi poll xử lý tối đa 50 document, hãy đặt **`Query.limit(50)`** hoặc sử dụng single-result có thiết kế state phù hợp; không chỉ chỉnh `maxMessagesPerPoll`.

### 6.2. Không đặt maxMessagesPerPoll=-1 tùy tiện

Với `SourcePollingChannelAdapter`, giá trị mặc định của `maxMessagesPerPoll` là **1** (khác một số `PollingConsumer` lấy message từ queue). Khi đặt **-1**, poller có thể tiếp tục gọi source cho đến khi nhận `null`.

Với MongoDB query read-only luôn trả dữ liệu:

~~~text
receive() -> có List chứa evt-101
receive() -> lại có List chứa evt-101
receive() -> vẫn có List chứa evt-101
...
~~~

Nếu không thay trạng thái và query không bao giờ trả rỗng, một poll task với `maxMessagesPerPoll(-1)` có thể **lặp rất lâu hoặc không kết thúc**, làm quá tải database và downstream. Chỉ sử dụng giá trị âm khi bạn **chứng minh** nguồn thực sự cạn dữ liệu và có điều kiện dừng đáng tin cậy.

Trong các phiên bản Spring Integration hỗ trợ, giá trị `maxMessagesPerPoll(0)` có thể được dùng để tạm bỏ qua các lượt `receive()` (ví dụ khi điều khiển endpoint qua Control Bus); đừng tự coi đây là phương thức tắt hoàn toàn mọi thành phần kết nối.

### 6.3. Fixed delay khác fixed rate

~~~text
fixedDelay(5000)
Poll A: start t=0, complete t=2s
Poll B: start gần t=7s

fixedRate(5000)
Poll A: start gần t=0
Poll B: lịch kế tiếp gần t=5s
~~~

Đây là sơ đồ thời gian lý tưởng; scheduler, thread pool, thời gian query/handler và startup đều ảnh hưởng thời điểm thực tế. Đừng mặc định fixed rate cho phép chồng lấn mọi poll: điều đó còn phụ thuộc scheduler và task executor được cấu hình.

Với MongoDB I/O blocking hoặc downstream chậm, **fixed delay** thường dễ kiểm soát tải hơn. Với lịch business theo giờ/ngày, cân nhắc cron và timezone cụ thể của hệ thống.

### 6.4. Poller timeout không phải MongoDB driver timeout

Nếu MongoDB chưa phản hồi query, việc tăng/giảm `receiveTimeout` ở poller không tự thay `serverSelectionTimeout` hoặc socket/read timeout của driver. Phân biệt:

- **Poll trigger**: quyết định lúc nào thực hiện `receive()`.
- **MongoDB driver timeouts**: quyết định thời gian chờ server/connection/IO.
- **QueueChannel.receive(timeout)** trong test: thời gian JUnit đợi Spring Message.
- **Business handler timeouts**: giới hạn HTTP/DB/Kafka downstream theo contract.

Đặt timeout và retry ở **tầng thực sự phát sinh chi phí**.

## 7. Giới hạn kết quả bằng Query.limit và Sort

Để chỉ lấy 50 document mới nhất hoặc cũ nhất, dùng Spring Data `Query` có giới hạn ở phía MongoDB.

Ví dụ với **MongoDatabaseFactory** và overload DSL nhận `Query`:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.dsl.MongoDb;

@Bean
public IntegrationFlow boundedMongoInboxFlow(
        MongoDatabaseFactory mongoDatabaseFactory) {

    Query query = Query.query(
            Criteria.where("tenantId").is("tenant-a")
                    .and("status").is("NEW"))
            .with(Sort.by(
                    Sort.Order.asc("createdAt"),
                    Sort.Order.asc("_id")))
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
            .channel("inboxEvents")
            .get();
}
~~~

**Đây là một phương án thay thế** `mongoInboxInboundFlow` ở mục 5; không đăng ký cả hai cùng poll collection `NEW` trong lab nếu không muốn nghiên cứu cạnh tranh/đọc trùng.

### 7.1. Khi nào cần sort theo _id?

Nếu nhiều document có cùng `createdAt`, sort chỉ theo timestamp có thể khiến thứ tự các bản ghi cùng timestamp không xác định. Thêm `_id` giúp tạo một thứ tự phụ ổn định theo **giá trị _id**, không đồng nghĩa _id phản ánh chính xác thời điểm event ngoài đời.

### 7.2. Index theo filter + sort

Trong mongosh của lab:

~~~javascript
db.inbox_events.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: 1,
  _id: 1
})
~~~

Index có thể giúp query trên tenant/status và sort theo createdAt, nhưng phải kiểm tra query plan, kích thước collection và chi phí ghi thực tế trước khi đưa vào production. Nếu dùng nhiều filter/sort khác nhau, không tạo index theo mọi tổ hợp tùy tiện.

### 7.3. Projection và kiểu entity

Nếu chỉ cần vài field:

~~~java
query.fields()
        .include("_id")
        .include("deviceId")
        .include("tenantId")
        .include("status");
~~~

Những field không được query trả về có thể là `null`/giá trị mặc định khi map vào entity. Nếu handler yêu cầu `temperatureC` và `createdAt`, đừng loại chúng ra rồi mong entity vẫn đầy đủ. Cân nhắc một DTO projection riêng hoặc lấy đủ field cần thiết.

### 7.4. Batch to không chỉ tiêu tốn RAM

Một `Message<List<T>>` lớn còn gây:

- Thời gian query và MongoDB network payload tăng.
- Splitter tạo nhiều message liên tiếp, tiêu thụ thread/CPU.
- Downstream HTTP/Kafka/JMS/AMQP có thể bị quá tải.
- Thời gian một poll task dài, scheduler trễ so với kế hoạch.
- Retry cả batch trở nên phức tạp nếu chỉ một document lỗi.

Giảm batch size tại query, đặt giới hạn downstream và đo **số document/poll**, không chỉ đo **số message source/poll**.

## 8. Tạo MongoDbMessageSource bằng Java bean trực tiếp

Java DSL factory giúp viết gọn. Khi cần quản lý source như bean riêng hoặc cấu hình expression nâng cao, có thể khởi tạo class trực tiếp.

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.inbound.MongoDbMessageSource;
import org.springframework.data.mongodb.core.MongoOperations;

@Configuration
@EnableIntegration
public class ExplicitMongoSourceConfig {

    @Bean("inboxMongoSource")
    public MongoDbMessageSource inboxMongoSource(
            MongoOperations mongo) {

        MongoDbMessageSource source = new MongoDbMessageSource(
                mongo,
                new LiteralExpression(
                    "{ 'tenantId': 'tenant-a', 'status': 'NEW' }"));

        source.setCollectionNameExpression(
                new LiteralExpression("inbox_events"));
        source.setEntityClass(InboxEvent.class);
        source.setExpectSingleResult(false);
        return source;
    }

    @Bean
    public IntegrationFlow fromExplicitMongoSource(
            MongoDbMessageSource inboxMongoSource) {
        return IntegrationFlow
                .from(inboxMongoSource,
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(1)))
                .split()
                .channel("inboxEvents")
                .get();
    }
}
~~~

**Đoạn cấu hình này là phương án thay thế** mục 5 và cần có bean `inboxEvents`/handler trong cùng context. Tránh đăng ký hai nguồn cùng query rồi ngạc nhiên vì duplicate.

Hai constructor chính của source trong API hiện hành:

~~~java
new MongoDbMessageSource(
        mongoOperations, queryExpression);

new MongoDbMessageSource(
        mongoDatabaseFactory, queryExpression);
~~~

Trong cả hai trường hợp, `queryExpression` là một **Spring Expression** trả MongoDB JSON query string hoặc đối tượng `Query`. Với factory path, source có thể cần converter phù hợp với entity mapping của ứng dụng; với `MongoOperations` đã cấu hình, mapping đi qua template của Spring Data.

### 8.1. Cẩn trọng với bean source dùng lại

Nếu bean `inboxMongoSource` đã được đăng ký trong một flow có poller, **đừng gọi `source.receive()` thủ công trong một request HTTP hoặc một test chạy đồng thời**. Việc gọi thêm sẽ cạnh tranh đọc cùng dữ liệu với poller và có thể làm test hoặc nghiệp vụ nhìn thấy kết quả không như mong đợi.

Muốn kiểm thử source trực tiếp, tạo một **test source riêng không có poller chạy nền**, hoặc stop endpoint rồi mới kiểm tra trong một môi trường dữ liệu đã cô lập.

## 9. Dynamic query và collection expression mỗi lượt poll

Một MongoDB inbound source **không có request Message đầu vào**. Expression cần lấy tham số từ một bean/cấu hình quản trị hoặc nguồn trạng thái đã kiểm soát, **không phải `payload.deviceId`** từ HTTP caller.

Ví dụ provider tạo một Query mới mỗi lần đọc:

~~~java
package example.mongodb;

import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component("inboxReadPolicy")
public class InboxReadPolicy {

    private final AtomicReference<String> status =
            new AtomicReference<>("NEW");

    public Query currentQuery() {
        String selected = status.get();

        return Query.query(
                Criteria.where("tenantId").is("tenant-a")
                        .and("status").is(selected))
                .with(Sort.by(
                    Sort.Order.asc("createdAt"),
                    Sort.Order.asc("_id")))
                .limit(50);
    }

    public String currentCollection() {
        return "inbox_events";
    }

    public void selectStatusFromAdmin(String next) {
        if (!Set.of("NEW", "RETRY").contains(next)) {
            throw new IllegalArgumentException(
                    "Unsupported polling status");
        }
        status.set(next);
    }
}
~~~

Config source dùng SpEL:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.mongodb.inbound.MongoDbMessageSource;
import org.springframework.data.mongodb.core.MongoOperations;

@Bean
public MongoDbMessageSource policyMongoSource(
        MongoOperations mongo) {

    SpelExpressionParser parser = new SpelExpressionParser();

    MongoDbMessageSource source = new MongoDbMessageSource(
        mongo,
        parser.parseExpression(
            "@inboxReadPolicy.currentQuery()"));

    source.setCollectionNameExpression(
        parser.parseExpression(
            "@inboxReadPolicy.currentCollection()"));
    source.setEntityClass(InboxEvent.class);
    source.setExpectSingleResult(false);

    return source;
}
~~~

**Điều kiện:** bean `inboxReadPolicy` phải tồn tại trong Spring context; `MongoDbMessageSource` do Spring quản lý để SpEL có thể phân giải `@beanName`. Source cần được nối vào IntegrationFlow với poller như mục 8.

Khi admin đổi status sang RETRY, query được dùng ở **lượt `receive()` tiếp theo**. Không có đảm bảo mọi instance cùng đổi status vì ví dụ lưu trạng thái trong RAM. Production cần một nguồn điều phối được quản lý, cập nhật atomically và có cách kiểm tra consistency.

### 9.1. Đừng dùng Query mutable dùng chung

Một `Query` có thể chứa limit/sort/filter. Nếu nhiều thread cùng sửa một object Query rồi source sử dụng, có thể xảy ra race. Ví dụ provider tạo **Query mới mỗi lần gọi**, giúp mỗi poll có một snapshot rõ hơn.

### 9.2. Collection expression không thay database

`setCollectionNameExpression(...)` có thể chọn một collection động, nhưng nó vẫn nằm trong **database của MongoOperations/MongoDatabaseFactory được inject**. Nếu phải poll database khác, dùng bean template/factory khác được phân quyền, không lấy một string từ người dùng để thay connection.

### 9.3. Query và collection nên là một policy nhất quán

Nếu một worker đổi query status và collection ở hai biến độc lập đúng lúc poll bắt đầu, có thể tạo tổ hợp không mong muốn. Với chính sách động phức tạp, nên lưu **một immutable policy object** chứa status/collection/limit và cập nhật toàn bộ atomically hoặc serialize thay đổi ở đúng lifecycle boundary.

## 10. updateExpression: đánh dấu document vừa đọc

Từ Spring Integration 5.5, MongoDB inbound source hỗ trợ **`updateExpression`** để cập nhật những document vừa được lấy. Ý tưởng thường gặp: query các document `NEW`, chuyển chúng sang `CLAIMED` để poll sau không đọc lại.

### 10.1. Java DSL ví dụ

~~~java
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.integration.mongodb.dsl.MongoDb;

MongoDb.inboundChannelAdapter(
        mongo, "{ 'status': 'NEW' }")
    .collectionName("inbox_events")
    .entityClass(InboxEvent.class)
    .expectSingleResult(false)
    .update(new Update().set("status", "CLAIMED"));
~~~

Đây là **đoạn builder thay thế**, cần gắn vào một flow có poller và downstream. Không chạy đồng thời với source read-only ở mục 5 để đánh giá business logic.

### 10.2. Điều gì được update và điều gì chưa được bảo đảm?

Tài liệu Spring Integration nêu updateExpression thay đổi những entity **đã được source lấy từ collection**, giúp chúng không còn khớp query nếu update làm đổi field lọc.

Tuy vậy:

- **Đổi `status=CLAIMED` không có nghĩa business handler đã xử lý xong**.
- App crash sau update nhưng trước khi gửi Kafka/HTTP/JMS có thể để lại document bị kẹt ở CLAIMED.
- Một danh sách đã đọc có thể được phát sang downstream, nhưng từng handler có thể xử lý thành công/thất bại khác nhau.
- Nếu nhiều instance query cùng lúc, **read rồi update** không tự trở thành một atomic claim cho từng document.
- Payload có thể chứa giá trị field cũ được đọc trước update; không giả định `message.payload.status` tự thành CLAIMED.
- Update expression chỉ là một bước kỹ thuật trong source; ứng dụng vẫn cần retry, lease và kiểm soát concurrency.

Một test chỉ thấy document không còn `NEW` sau poll **chưa chứng minh event đã được giao cho hệ thống đích**.

### 10.3. Khi nào không nên bật update ngay?

- Khi mới học cách source trả `List<T>` và muốn quan sát payload.
- Khi downstream cần tự xác nhận thành công mới được đổi trạng thái.
- Khi có nhiều consumer, chưa có phân phối owner/lease.
- Khi cần phân biệt dữ liệu đã đọc với dữ liệu đã commit.
- Khi query vẫn còn khả năng chọn lại document vì update không đổi field lọc.

Để sản xuất có yêu cầu tin cậy, cần thiết kế cơ chế claim/lease hoặc transaction phù hợp, thay vì chỉ bổ sung một câu lệnh update.

## 11. Thiết kế claim, lease, ACK và idempotency

Một state machine có thể là:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> PROCESSING: Atomic claim + owner/lease
    PROCESSING --> DONE: Business commit thành công
    PROCESSING --> RETRY: Lỗi xử lý tạm thời
    PROCESSING --> RETRY: Lease hết hạn
    RETRY --> PROCESSING: Retry có backoff
    RETRY --> DEAD: Quá số lần thử
~~~

Document có thể chứa:

~~~json
{
  "_id": "evt-101",
  "status": "PROCESSING",
  "claimOwner": "worker-13",
  "leaseUntil": "2026-11-23T03:00:00Z",
  "attempt": 2,
  "nextAttemptAt": null,
  "lastErrorCode": null
}
~~~

**Ví dụ JSON chỉ minh họa trạng thái nghiệp vụ**, không phải các field MongoDbMessageSource tự tạo.

### 11.1. Race khi nhiều instance poll

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant D as MongoDB
    A->>D: find(status=NEW)
    B->>D: find(status=NEW)
    D-->>A: evt-101
    D-->>B: evt-101
    A->>D: update status=CLAIMED
    B->>D: update status=CLAIMED
    Note over A,B: Cả hai có thể xử lý cùng evt-101
~~~

**Chỉ thêm `updateExpression` không đủ để chứng minh claim nguyên tử.** Nếu cần mỗi job có một owner duy nhất, xem xét:

1. Dùng `MongoOperations.findAndModify(...)` với query điều kiện trạng thái/lease/owner trong **một MongoDB operation nguyên tử trên document**.
2. Ghi `claimOwner`, `leaseUntil`, `attempt` và version có điều kiện.
3. Worker chỉ đánh dấu DONE nếu vẫn là owner/version hợp lệ.
4. Job PROCESSING quá hạn được đưa trở lại retry theo chính sách.
5. Side effect downstream luôn có **idempotency key**, thường dựa trên `_id` hoặc event ID bền vững.
6. Theo dõi stuck jobs, duplicates, attempt count và dead-letter.

Khi muốn dùng claim nguyên tử làm **nguồn dữ liệu của IntegrationFlow**, có thể cần **custom MessageSource** hoặc service chuyên trách thực hiện findAndModify rồi tạo Spring Message. Không gọi một flow read-only thông thường là “exactly-once” khi chưa kiểm soát concurrency.

### 11.2. ACK nguồn và ACK nghiệp vụ

Một hệ thống xử lý event bền cần phân biệt:

~~~text
1. MongoDB query trả document
2. Spring Message được tạo
3. Message được channel chấp nhận
4. Handler bắt đầu xử lý
5. Kafka/JMS/HTTP/DB đích xác nhận kết quả
6. Trạng thái MongoDB chuyển DONE theo owner/version
~~~

Đánh dấu DONE ở bước 2–3 có thể làm mất công việc nếu crash ở bước 4–5. Với outbound broker/HTTP, cần xác định cách xử lý khi **đích đã nhận nhưng response thất lạc**; retry có thể gây duplicate, vì thế phải có ID ổn định và idempotent consumer.

### 11.3. Transaction synchronization không tự bảo đảm MongoDB transaction

Spring Integration có transaction synchronization quanh poller và callback trước/sau commit/rollback. Có ví dụ dùng `PseudoTransactionManager` để kích hoạt callback.

**PseudoTransactionManager không biến thao tác MongoDB thành transaction thật.** Muốn MongoDB multi-document transaction, cần topology hỗ trợ, `MongoTransactionManager` và ranh giới transaction đúng. Transaction MongoDB cũng **không tự bao trùm Kafka/JMS/HTTP** như một distributed transaction.

## 12. XML cấu hình MongoDB inbound adapter

Một cách tương đương trong Spring Integration XML:

~~~xml
<!-- XML khai báo namespace int và int-mongodb hợp lệ -->
<int:channel id="mongoRawResults"/>

<int-mongodb:inbound-channel-adapter
        id="mongoInboxInboundAdapter"
        channel="mongoRawResults"
        mongo-template="mongoTemplate"
        collection-name="inbox_events"
        query="{ 'tenantId':'tenant-a', 'status':'NEW' }"
        entity-class="example.mongodb.InboxEvent"
        auto-startup="false">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-mongodb:inbound-channel-adapter>
~~~

Đây là cấu hình **có output channel nhận List**, nếu `expectSingleResult` giữ mặc định false. Downstream cần một handler chấp nhận `List` hoặc một splitter riêng.

`auto-startup="false"` dành cho bài lab khi muốn khởi động thủ công; production tùy kiến trúc có thể chọn auto-start. Nếu inbound endpoint không start, poller không tự chạy chỉ vì MongoDB có dữ liệu.

### 12.1. XML query-expression động

~~~xml
<int-mongodb:inbound-channel-adapter
        id="mongoInboxDynamic"
        channel="mongoRawResults"
        mongo-template="mongoTemplate"
        query-expression="@inboxReadPolicy.currentQuery()"
        collection-name-expression="@inboxReadPolicy.currentCollection()"
        entity-class="example.mongodb.InboxEvent">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-mongodb:inbound-channel-adapter>
~~~

**Phương án thay thế**, không khai báo đồng thời hai adapter cùng dùng một channel/dataset nếu không có chủ đích. Bean `inboxReadPolicy` phải tồn tại trong context; query-expression trả MongoDB JSON query string hoặc Spring Data `Query`.

### 12.2. Các thuộc tính không trộn bừa

| Thuộc tính | Hợp đồng |
|---|---|
| `query` hoặc `query-expression` | **Một trong hai** |
| `collection-name` hoặc `collection-name-expression` | **Một trong hai** |
| `mongo-template` hoặc `mongodb-factory` | **Một trong hai**, theo config endpoint |
| `entity-class` | Java type của document sau mapping |
| `auto-startup` | Lifecycle endpoint |
| `poller` | Lịch source receive, số message nhận và error handling |
| `update-expression` (nếu dùng) | Cập nhật document vừa đọc; không phải ACK downstream |

Không gắn `query` và `poller` vào **MongoDB outbound storing adapter** rồi coi đó là inbound source. Writer xử lý message đến từ channel, còn source query MongoDB theo lịch.

## 13. So sánh MongoDB polling với change stream và outbound gateway

| Tiêu chí | MongoDbMessageSource | Change stream inbound | MongoDbOutboundGateway |
|---|---|---|---|
| Cơ chế kích hoạt | **Poller** | MongoDB change stream subscription | **Request Message** |
| Đọc bằng | `find` hoặc `findOne` | MongoDB change stream API | `find`/`findOne` hoặc callback theo request |
| Dữ liệu đầu ra | List/entity được query | Change event hoặc body tùy config | Reply cho caller |
| Có request payload đầu vào? | Không | Không theo kiểu gateway | **Có** |
| Độ trễ | Phụ thuộc lịch poll | Theo subscription và môi trường | Theo request/DB latency |
| Đọc lại khi không có trạng thái? | **Có thể** | Cần resume/checkpoint riêng | Caller có thể hỏi lại |
| Hợp lý cho | Batch/queue-like polling | CDC/near-real-time updates | API search/lookup theo request |
| Cơ chế phục hồi | Query/claim/lease/idempotency | Resume token/re-subscription | Retry/error/timeout của caller |

**MongoDB change stream** yêu cầu deployment, quyền và khả năng MongoDB tương ứng. Nó không tự là một MongoDbMessageSource polling cải tiến; đó là **endpoint khác với semantics riêng**.

## 14. Lỗi, timeout và error channel

### 14.1. Phân loại lỗi

| Hiện tượng | Có thể phát sinh ở đâu? | Cách xử lý |
|---|---|---|
| MongoDB connection down | Driver/MongoOperations khi poll | Retry có giới hạn, backoff, health/metrics |
| Auth sai/thiếu quyền read | Khi kết nối/query collection | Cập nhật role/secret, không retry mù |
| Collection sai | Query trả rỗng hoặc lỗi theo cấu hình | Kiểm tra tên DB/collection, Bean MongoOperations |
| Query expression lỗi | Trước khi chạy DB query | Test expression và BeanFactory/SpEL context |
| Document mapping thất bại | MongoConverter | Phân loại schema, quarantine/reconcile |
| Không có document | `receive()==null` | Không phải lỗi; đo empty poll |
| Handler lỗi sau splitter | Downstream service | Error channel/advice theo flow; retry/claim |
| Query quá rộng | DB trả danh sách lớn | Limit/sort/index/projection |
| Poll task kéo dài | MongoDB chậm hoặc handler block | Timeout, batch size, concurrency có giới hạn |
| Đọc trùng sau restart | Không có checkpoint/claim | Trạng thái DB và idempotency |
| Document kẹt PROCESSING | Worker crash/lease không hồi phục | Recovery/retry scheduler |
| Concurrent polling duplicates | Nhiều instance query trước update | Atomic claim/owner/version |
| Outbound message được ACK quá sớm | Async queue hoặc update trước commit | Ranh giới ACK và trạng thái DONE rõ |

### 14.2. Lỗi đồng bộ và bất đồng bộ

Với `DirectChannel` và handler đồng bộ, exception ở downstream có thể lan tới poller task. Nếu có executor hoặc channel bất đồng bộ, exception có thể đi sang error channel tại thread khác.

**Không mặc định mọi lỗi đều là một `ErrorMessage` duy nhất.** Một query trả list rỗng không phải exception; một DB query error xảy ra **trước khi có payload**; một handler save HTTP/Kafka lỗi xảy ra **sau khi message được sinh**. Cần đặt log/metric tại đúng ranh giới.

### 14.3. Poller error-channel trong XML

Trong ứng dụng đã cấu hình `mongoPollingErrors` làm channel và có handler lỗi thích hợp:

~~~xml
<int-mongodb:inbound-channel-adapter
        id="mongoInboxWithErrors"
        channel="mongoRawResults"
        mongo-template="mongoTemplate"
        collection-name="inbox_events"
        query="{ 'status':'NEW' }"
        entity-class="example.mongodb.InboxEvent">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"
                error-channel="mongoPollingErrors"/>
</int-mongodb:inbound-channel-adapter>
~~~

**Đây là cấu hình thay thế**, không khai báo song song với các adapter khác của ví dụ. Phải thêm `mongoPollingErrors` và consumer nhận `ErrorMessage` phù hợp. Không gửi lỗi nhạy cảm nguyên văn lên một kênh public; phân loại transient/permanent và áp retry budget.

## 15. Lifecycle, shutdown và backpressure

Spring quản lý endpoint theo `SmartLifecycle`:

- Khi ApplicationContext start, endpoint inbound có thể auto-start và kích hoạt poller.
- Poll task gọi `source.receive()` theo trigger.
- Khi stop, không nên lên thêm poll task mới; **những message đã lấy/đã chuyển vào queue** có thể vẫn đang được xử lý tùy kiến trúc.
- MongoDB client/pool thường thuộc bean Spring Data được dùng lại; không tạo client mới mỗi lần poll.
- Khi restart, source có thể query lại các document thỏa điều kiện; **không có durable cursor tự động cho query polling**.
- Khi scale lên nhiều instance, không dựa vào flag trạng thái trong RAM để đồng bộ ai đang claim document nào.
- Nếu downstream là `QueueChannel` in-memory, cần quyết định rõ xử lý pending events khi process chết.

### 15.1. Backpressure không phải tính năng tự động của MongoDB query

Nếu trong một chu kỳ source trả 10.000 document rồi splitter phát 10.000 message, hệ thống downstream có thể quá tải bất chấp poller 5 giây.

Biện pháp:

1. Giới hạn `Query.limit` và tài nguyên MongoDB.
2. Chọn `fixedDelay` phù hợp với thời gian xử lý.
3. Giới hạn concurrency và queue capacity.
4. Theo dõi queue depth, handler latency và retry.
5. Tạm giảm/tắt polling khi downstream không theo kịp.
6. Dùng durable broker/outbox khi không được mất dữ liệu.
7. Nếu nguồn là work queue, thiết kế **claim/release** thay vì quét lại toàn collection ở mỗi poll.

Một message source polling không tự thay thế cơ chế backpressure xuyên MongoDB → JMS/Kafka/HTTP.

## 16. Kiểm thử đơn vị MongoDbMessageSource

Có hai loại test khác nhau: **logic nghiệp vụ** không cần MongoDB và **source.receive()** với MongoOperations giả lập hoặc test database.

### 16.1. Unit test validator

~~~java
package example.mongodb;

public final class InboxEventValidator {

    public void validate(InboxEvent event) {
        if (event == null
                || event.id() == null || event.id().isBlank()
                || event.tenantId() == null
                || event.tenantId().isBlank()
                || event.deviceId() == null
                || event.deviceId().isBlank()
                || event.temperatureC() == null
                || event.status() == null) {
            throw new IllegalArgumentException(
                    "Invalid inbox event");
        }
    }
}
~~~

JUnit 5:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class InboxEventValidatorTest {

    @Test
    void acceptsValidEvent() {
        InboxEvent event = new InboxEvent(
                "evt-101", "tenant-a", "node-7",
                new BigDecimal("26.5"), "NEW",
                Instant.parse("2026-11-20T08:00:00Z"));

        assertDoesNotThrow(
                () -> new InboxEventValidator().validate(event));
    }

    @Test
    void rejectsMissingDeviceId() {
        InboxEvent event = new InboxEvent(
                "evt-102", "tenant-a", null,
                new BigDecimal("25.8"), "NEW",
                Instant.parse("2026-11-20T08:00:01Z"));

        assertThrows(IllegalArgumentException.class,
                () -> new InboxEventValidator().validate(event));
    }
}
~~~

Các test này không khởi tạo Spring context, không kiểm tra polling, nhưng giúp business contract được xác nhận nhanh.

### 16.2. Test source.receive() với MongoOperations mock

Để kiểm tra một source thực sự gọi `MongoOperations.find(...)` và chuyển list thành Message, có thể dùng Mockito và `LiteralExpression`. Test này **không có poller** nên không cạnh tranh với một endpoint khác.

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.mongodb.inbound.MongoDbMessageSource;
import org.springframework.integration.mongodb.support.MongoHeaders;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class MongoDbMessageSourceUnitTest {

    @Test
    void findReturnsOneMessageHoldingList() {
        MongoOperations mongo = mock(MongoOperations.class);

        InboxEvent event = new InboxEvent(
                "evt-101", "tenant-a", "node-7",
                new BigDecimal("26.5"), "NEW",
                Instant.parse("2026-11-20T08:00:00Z"));

        when(mongo.find(
                any(Query.class),
                eq(InboxEvent.class),
                eq("inbox_events")))
            .thenReturn(List.of(event));

        MongoDbMessageSource source = new MongoDbMessageSource(
                mongo, new LiteralExpression(
                    "{ 'tenantId':'tenant-a', 'status':'NEW' }"));

        source.setCollectionNameExpression(
                new LiteralExpression("inbox_events"));
        source.setEntityClass(InboxEvent.class);
        source.setExpectSingleResult(false);
        source.afterPropertiesSet();

        Message<?> result = source.receive();

        assertNotNull(result);
        assertInstanceOf(List.class, result.getPayload());
        assertEquals(1, ((List<?>) result.getPayload()).size());
        assertEquals("inbox_events", result.getHeaders()
                .get(MongoHeaders.COLLECTION_NAME));

        verify(mongo).find(
                any(Query.class),
                eq(InboxEvent.class),
                eq("inbox_events"));
    }

    @Test
    void emptyFindReturnsNoMessage() {
        MongoOperations mongo = mock(MongoOperations.class);

        when(mongo.find(
                any(Query.class),
                eq(InboxEvent.class),
                eq("inbox_events")))
            .thenReturn(List.of());

        MongoDbMessageSource source = new MongoDbMessageSource(
                mongo, new LiteralExpression("{ 'status':'NEW' }"));
        source.setCollectionNameExpression(
                new LiteralExpression("inbox_events"));
        source.setEntityClass(InboxEvent.class);
        source.afterPropertiesSet();

        assertNull(source.receive());
    }
}
~~~

**Lưu ý kỹ thuật:** ví dụ gọi `afterPropertiesSet()` vì source được tạo thủ công thay vì qua Spring context. Test có thể cần bổ sung cấu hình BeanFactory nếu thay LiteralExpression bằng `@bean.method()`. Với dependency/version khác, API initialization cần đối chiếu JavaDocs; tránh test mock một hành vi khác với source thực tế.

Unit test source kiểm tra chuyển đổi **query response → message**, nhưng chưa kiểm tra MongoDB thật và poller schedule.

### 16.3. Kiểm thử expectSingleResult(true)

Tạo source riêng với `setExpectSingleResult(true)` và stub:

~~~java
when(mongo.findOne(
        any(Query.class),
        eq(InboxEvent.class),
        eq("inbox_events")))
    .thenReturn(event);
~~~

Với kiểu này, `result.getPayload()` phải là một `InboxEvent` thay vì `List`. Nếu `findOne` trả null, `receive()` trả null. **Không dùng cùng source đang được poll trong ứng dụng** để test trực tiếp.

## 17. Integration test MongoDB → QueueChannel

Một integration test cần kiểm tra **query thật**, **message payload**, **header** và **wiring của polling adapter**.

~~~mermaid
flowchart LR
    S["JUnit seed MongoDB test"] --> DB["MongoDB test collection"]
    DB --> P["MongoDbMessageSource + Poller"]
    P --> SP["Splitter"]
    SP --> Q["QueueChannel: mongoTestSink"]
    Q --> A["JUnit receive(timeout) + asserts"]
~~~

Với Spring Boot Test và MongoDB test instance do CI quản lý hoặc Testcontainers (khi runner hỗ trợ Docker), cấu hình sink riêng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;

@Bean("mongoTestSink")
public QueueChannel mongoTestSink() {
    return new QueueChannel(32);
}
~~~

Trong một **test-only IntegrationFlow**, sau splitter chuyển vào `mongoTestSink`, thay vì handler nghiệp vụ thực:

~~~java
// Chỉ là đoạn cuối của flow riêng dành cho test:
.split()
.channel("mongoTestSink")
.get();
~~~

JUnit assertion trong class đã được tạo test context và đã seed một `NEW` document:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

@Autowired
@Qualifier("mongoTestSink")
QueueChannel testSink;

@Test
void receivesPolledDocument() {
    Message<?> received = testSink.receive(5000);

    assertNotNull(received, "Poll did not produce a Message");
    assertInstanceOf(InboxEvent.class, received.getPayload());

    InboxEvent event = (InboxEvent) received.getPayload();
    assertEquals("evt-101", event.id());
    assertEquals("tenant-a", event.tenantId());
}
~~~

Đây là **fragment của test class**, không phải Java file độc lập. Cần cấu hình Spring test context, MongoDB test instance, seed/cleanup dữ liệu và import còn lại phù hợp. Không chạy integration test này trên database production.

### 17.1. Test cases quan trọng

| Test | Assertion |
|---|---|
| Không có document khớp | Không có message tại sink trong timeout hữu hạn |
| Có một document khớp | Một `InboxEvent` sau splitter |
| Có ba document khớp | Ba payload sau splitter, không nhầm là ba lần source.receive |
| `expectSingleResult(true)` | Source trả một entity, flow không cần splitter |
| Query `limit(2)` | Không quá hai document từ một query |
| Query sort theo `createdAt/_id` | Thứ tự theo contract trong result list |
| `MongoHeaders.COLLECTION_NAME` | Header chỉ đúng collection được query |
| Query không update status | Event có thể xuất hiện lại ở poll sau |
| Có `updateExpression` | Field được đổi ở MongoDB, nhưng chưa chứng minh downstream commit |
| MongoDB down | Retry/error channel/health đúng, không treo vô hạn |
| Hai pollers cùng query | Phát hiện duplicate và cần atomic claim |
| Restart endpoint | Document chưa DONE được phục hồi theo state policy |

**Tránh false positive:** nếu query đáng ra đọc `evt-101` nhưng test chỉ assert `list.size() <= 50`, một danh sách rỗng cũng PASS dù endpoint sai. Hãy seed ID cụ thể, assert payload đúng ID và xác minh đúng collection.

### 17.2. Test chống flaky

- Dùng collection/database riêng, ID ngẫu nhiên có namespace test.
- Với polling, chờ message bằng `QueueChannel.receive(timeout)`, không dùng `Thread.sleep` cố định để “đợi poll”.
- Drain queue giữa các test hoặc tạo context riêng.
- Dừng endpoint trước khi cleanup data; tránh poll trong lúc teardown.
- Nếu kiểm tra **không có message**, phải hiểu timeout hữu hạn chỉ cho biết queue trống trong khoảng đó.
- Không chạy hai consumer cùng đọc một QueueChannel test sink nếu muốn JUnit nhận message.
- Khi thử source trực tiếp, không để background poller dùng cùng source.
- Chạy test qua nhiều chu kỳ để phát hiện duplicate; test một chu kỳ thường không chứng minh idempotency.

## 18. Quan sát hoạt động và bảo mật

Những metric gợi ý (không mặc định framework tự phát theo đúng tên):

| Metric | Ý nghĩa |
|---|---|
| `mongo_poller_run_total` | Số lần poll được kích hoạt |
| `mongo_poller_empty_total` | Số lần không tìm thấy dữ liệu |
| `mongo_query_duration_seconds` | Độ trễ MongoDB query |
| `mongo_query_result_documents` | Số document được đọc |
| `mongo_inbound_message_total` | Số Message<List<T>> từ source |
| `mongo_split_messages_total` | Số Message<T> sau splitter |
| `mongo_handler_success_total` | Số document hoàn tất nghiệp vụ |
| `mongo_handler_errors_total` | Số lỗi downstream |
| `mongo_claim_conflicts_total` | Lần tranh chấp claim |
| `mongo_lease_expired_total` | Số công việc PROCESSING quá hạn |
| `mongo_retry_scheduled_total` | Số retry đã được lên lịch |
| `mongo_inbox_lag_seconds` | Tuổi của document còn chờ |
| `mongo_pending_work_depth` | Số công việc đang đợi |

**Không đồng nhất** số source message với số document. Một `Message<List<T>>` có thể mang nhiều document; sau splitter số message thay đổi.

Một vài yêu cầu bảo mật:

1. MongoDB account có **least privilege** cho collection đọc và chỉ có quyền update khi thực sự cần.
2. URI, credentials, certificate không nằm trong source/log; dùng secrets/TLS.
3. Query có tenant filter/allowlist; không nhận raw JSON query/SpEL từ user không tin cậy.
4. Giới hạn batch/query time và rate để tránh scan toàn collection.
5. Validate schema/version/ID trước khi đưa sang HTTP/Kafka/JMS/AMQP.
6. Không đưa document nhạy cảm nguyên vẹn vào log/metric.
7. Khi dùng multi-tenant, `collectionNameExpression` **không tự chuyển database** hoặc xác thực quyền tenant.
8. Unique index/idempotency key cần theo business contract.
9. Monitor lease expiration, retries và backlog để biết worker có bị kẹt sau restart.
10. Dùng metric label cardinality hữu hạn, không theo từng document ID.

## 19. Bài thực hành tổng hợp

Thực hành dựng pipeline **MongoDB inbox → Spring Integration → xử lý từng event → Kafka/JMS/HTTP/DB**.

### Phần A — Source và payload

1. Tạo MongoDB `adapter_lab` và seed ba document như mục 4.
2. Cấu hình Spring Boot + dependency MongoDB Integration.
3. Viết `InboxEvent` với `@Document`, `@Id` và các field tương ứng.
4. Cấu hình `MongoDb.inboundChannelAdapter(...)`, `Pollers.fixedDelay(5000)`, `maxMessagesPerPoll(1)`.
5. Trước splitter, dùng QueueChannel test để kiểm tra payload là `List<InboxEvent>`.
6. Sau splitter, kiểm tra mỗi message là một `InboxEvent` và có header collection phù hợp.
7. Thử `expectSingleResult(true)` trong **flow khác**, bỏ splitter, so sánh payload và không tìm thấy dữ liệu.

### Phần B — Batch, query và lịch

1. Seed 200 document NEW trong database test.
2. Chạy source với maxMessagesPerPoll=1 nhưng query chưa có limit: quan sát vì sao một Message vẫn có thể chứa rất nhiều document.
3. Thêm query `limit(50)`, sort theo `createdAt/_id`, kiểm tra mỗi batch.
4. So sánh fixedDelay và fixedRate khi downstream xử lý mất vài giây.
5. Thử maxMessagesPerPoll=-1 trong **lab cô lập với query có điểm dừng**, giải thích nguy cơ vòng lặp vô hạn của nguồn read-only luôn có kết quả.
6. Thiết kế index phù hợp với tenant/status/sort và quan sát query plan.

### Phần C — Dynamic query và update

1. Dùng `InboxReadPolicy.currentQuery()` và SpEL trong `MongoDbMessageSource`.
2. Chuyển status từ NEW sang RETRY theo cách quản trị được kiểm soát, xem query ở lượt poll sau.
3. Dùng `update(new Update().set("status","CLAIMED"))` trong một test riêng.
4. Giả lập app crash giữa CLAIMED và business completion; đề xuất recovery/lease.
5. Chạy hai instance cùng poll, mô phỏng read/update race; trình bày atomic findAndModify claim.
6. Thiết kế idempotency key giữ nguyên qua redelivery.

### Phần D — Testing và vận hành

1. Unit test validator; unit test `source.receive()` bằng Mockito với list và list rỗng.
2. Integration test MongoDB thật + QueueChannel sink, seed/dọn dữ liệu riêng.
3. Thử MongoDB down, auth error, invalid mapping và error channel.
4. Kiểm tra stop/start endpoint và liệu dữ liệu chưa DONE có được đọc lại.
5. Đưa messages sang Kafka/JMS/HTTP; định nghĩa lúc nào được đánh dấu DONE hoặc ACK source.
6. Đề xuất metrics về document count, message count, lag, empty polls, claim conflict, retry và queue depth.

**Câu hỏi tự đánh giá:**

- Ai thực sự gọi `MongoDbMessageSource.receive()`?
- Vì sao `MongoDbMessageSource` không phải change stream subscriber?
- Khi `expectSingleResult(false)` và query tìm 20 document, source tạo bao nhiêu Message?
- Vì sao `maxMessagesPerPoll(1)` không giới hạn 1 document?
- Điều gì xảy ra nếu đặt maxMessagesPerPoll=-1 nhưng query luôn trả một list không rỗng?
- Sự khác biệt giữa fixedDelay và fixedRate là gì?
- Query `limit(50)` giúp gì nếu source trả List?
- Vì sao cần sort theo cả createdAt và _id trong một số workflow?
- Vì sao query source được đánh giá mỗi poll nhưng không có request payload?
- `updateExpression` có nghĩa downstream đã commit không?
- Hai instance cùng query NEW có thể xử lý trùng cùng document không?
- Khi nào cần findAndModify, lease và owner?
- `MongoHeaders.COLLECTION_NAME` giúp chẩn đoán điều gì?
- Vì sao test một lần poll thành công chưa chứng minh không có duplicates?
- Khi nào nên dùng change stream, outbound gateway hoặc broker thay cho polling?

## 20. Tài liệu tham khảo

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): inbound channel adapter, query-expression, updateExpression, change stream và transaction synchronization.
- [Spring Integration API — MongoDbMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/inbound/MongoDbMessageSource.html): source, find/findOne, List payload, empty result và header collection.
- [Spring Integration API — AbstractMongoDbMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/inbound/AbstractMongoDbMessageSource.html): entityClass, expectSingleResult, collection expression và update expression.
- [Spring Integration API — MongoDb DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): factory `inboundChannelAdapter` và các overload.
- [Spring Integration API — AbstractMongoDbMessageSourceSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/AbstractMongoDbMessageSourceSpec.html): `collectionName`, `collectionNameSupplier`, `entityClass`, `update`.
- [Spring Integration Reference — Configuring Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/channel-adapter.html): `SourcePollingChannelAdapter`, maxMessagesPerPoll và điều khiển polling.
- [Spring Integration Reference — Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html): trigger, fixed-delay, fixed-rate, error channel, transaction.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): MongoOperations, Query, Criteria, mapping, index và MongoTransactionManager.
- [MongoDB Manual — findAndModify](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/): thao tác claim có điều kiện trên document.

## Kết luận

**`MongoDbMessageSource` là nguồn dữ liệu MongoDB theo cơ chế polling**. Nó được `SourcePollingChannelAdapter` gọi `receive()` theo lịch, thực hiện `find()` hoặc `findOne()` và trả một Spring Message cho downstream khi có dữ liệu. **Mặc định source phát một Message chứa List document**, nên cần splitter nếu mỗi document phải thành một message riêng.

Trong **SPRING_INTEGRATION_ADAPTERS**, một pipeline chỉ bền vững khi phân biệt **poll frequency với batch size**, **query thành công với business commit**, **read với atomic claim** và **Spring Message với event ID nghiệp vụ**. Hãy giới hạn query, dùng sort/index và batch hợp lý, thiết kế trạng thái xử lý/lease/idempotency/retry, kiểm tra error channel và shutdown, đồng thời test qua MongoDB thực khi cần. **Polling là cách lấy dữ liệu theo lịch, không phải bảo đảm giao hàng exactly-once.**
