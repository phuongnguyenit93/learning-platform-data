# MongoDbOutboundGateway trong Spring Integration

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của **`MongoDbOutboundGateway`** trong mô hình **request/reply**, khác với MongoDB inbound/outbound channel adapter.
- Cấu hình MongoDB outbound gateway bằng **Java DSL**, Java bean hoặc **XML**, nhận request từ `MessageChannel` và phát response sang reply channel.
- Chọn `MongoOperations`, collection, `entityClass`, query tĩnh hoặc query động bằng `queryFunction`/`queryExpression`.
- Phân biệt kết quả **`List<T>` theo mặc định** với **một `T`** khi bật `expectSingleResult(true)`, kể cả cách xử lý không tìm thấy dữ liệu.
- Xây dựng API truy vấn theo từng request bằng `@MessagingGateway`, đồng thời hiểu vì sao **reply channel tĩnh** và **temporary reply channel** của caller không nên dùng lẫn lộn.
- Sử dụng `MessageCollectionCallback` cho phép toán chuyên biệt như `countDocuments()`, không kết hợp callback với thuộc tính query trên cùng endpoint.
- Giới hạn batch, sort, projection, timeout và phân quyền để tránh truy vấn không an toàn hoặc trả quá nhiều dữ liệu.
- Kiểm thử payload, reply headers, kết quả rỗng, lỗi DB, request timeout, lifecycle và các tình huống đi qua HTTP, JMS, AMQP, Kafka hoặc các adapter khác.

Bài thuộc chương **Adapter MongoDB** của module **SPRING_INTEGRATION_ADAPTERS**. Module hướng dẫn kết nối các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành luồng qua file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, đồng thời chú trọng hợp đồng message, lỗi và vòng đời kết nối. Trong bài này, **MongoDB là đích truy vấn**, còn ứng dụng yêu cầu câu trả lời cho **một request cụ thể**.

## 1. Bài toán: hỏi MongoDB ngay khi có yêu cầu

Một HTTP endpoint nhận yêu cầu “Tìm những bản ghi telemetry mới của thiết bị `node-7`”. Dữ liệu được lưu trong collection `telemetry_events`:

~~~json
{
  "_id": "evt-101",
  "deviceId": "node-7",
  "sequence": 101,
  "status": "NEW",
  "temperatureC": 26.5,
  "createdAt": "2026-11-23T02:00:00Z"
}
~~~

Ứng dụng cần:

1. Nhận `FindEventsRequest("node-7", 20)`.
2. Tạo MongoDB `Query` có điều kiện device ID, trạng thái và giới hạn 20 document.
3. Chuyển query thành MongoDB operation tại outbound gateway.
4. Nhận reply là `List<TelemetryEvent>`.
5. Dùng danh sách để tạo HTTP response, tổng hợp hoặc chuyển tới một hệ thống khác.

~~~mermaid
sequenceDiagram
    participant A as HTTP / Messaging caller
    participant C as Request MessageChannel
    participant G as MongoDbOutboundGateway
    participant D as MongoDB
    A->>C: Message<FindEventsRequest>
    C->>G: Request + replyChannel header
    G->>D: find(query, TelemetryEvent.class)
    D-->>G: List<TelemetryEvent>
    G-->>A: Reply Message<List<TelemetryEvent>>
    Note over A: Caller kiểm tra kết quả, không tự poll
~~~

Điểm khác biệt với MongoDB **inbound channel adapter**: **không có poller để tự đọc collection theo chu kỳ**. Outbound gateway chỉ truy vấn khi có **request message**, rồi tạo reply theo hợp đồng endpoint.

## 2. Phân biệt MongoDbOutboundGateway với các thành phần gần giống

| Thành phần | Ai kích hoạt? | Hướng dữ liệu | Kết quả chính |
|---|---|---|---|
| **MongoDB inbound channel adapter** | Poller gọi source định kỳ | MongoDB → MessageChannel | Phát message từ query theo lịch |
| **MongoDB outbound channel adapter** | Có message ở input channel | MessageChannel → MongoDB | **Ghi** payload; một chiều |
| **`MongoDbOutboundGateway`** | Có **request message** | MessageChannel → MongoDB → reply channel | **Truy vấn và trả reply** |
| **MongoDB change stream inbound adapter** | MongoDB phát change event | MongoDB → MessageChannel | Thông báo insert/update/delete theo subscription |
| **`MongoTemplate` trực tiếp** | Java code gọi method | Java service ↔ MongoDB | Trả giá trị trực tiếp, không cần Integration endpoint |
| **MongoDB message store** | Queue/aggregator/claim-check | Spring Integration ↔ MongoDB | Lưu trạng thái message/group, không phải gateway truy vấn nghiệp vụ |

**Tên “outbound” chỉ hướng mà request được gửi từ ứng dụng đến MongoDB**, không có nghĩa mọi outbound endpoint là một chiều. `MongoDbOutboundGateway` kế thừa `AbstractReplyProducingMessageHandler` nên có hành vi request/reply; `MongoDbStoringMessageHandler` là writer một chiều.

### 2.1. Khi nào nên dùng gateway?

Dùng outbound gateway khi:

- Cần tra cứu theo **tham số riêng của mỗi request**.
- Cần kết quả trả về cho HTTP handler, command handler, validator hoặc workflow.
- Muốn giữ các bước transform/filter/enrich/routing trong một IntegrationFlow.
- Muốn truy vấn một collection đã biết và giới hạn dữ liệu trả về.
- Cần một phép toán đặc biệt dựa trên `MessageCollectionCallback`.

Không nên dùng gateway như một “poller ẩn”. Nếu nghiệp vụ là định kỳ đọc toàn bộ document `NEW` mà không có caller, hãy dùng **inbound adapter + poller**, change stream hoặc background job thích hợp.

## 3. Bản chất request, reply và headers

Một message đến gateway chứa:

~~~text
Request Message<FindEventsRequest>
  payload = FindEventsRequest("node-7", 20)
  headers:
    id = <Spring Message ID>
    replyChannel = <reply target>
    errorChannel = <error target>  (nếu có)
    correlationId = "lookup-101"
~~~

Gateway tạo MongoDB query, thực thi và tạo một **reply message** chứa kết quả. Các header thích hợp thường được mang theo theo cơ chế reply của Spring Integration; những header hệ thống hoặc đã bị filter có thể không được copy nguyên vẹn. Cần **kiểm thử header thực tế** nếu downstream phụ thuộc `correlationId`, trace ID hay tenant context.

| Thành phần | Vai trò | Ghi chú |
|---|---|---|
| `requestChannel` | Kênh gateway đọc request | Thường là `DirectChannel` |
| `replyChannel` | Kênh nhận reply | Có thể là kênh cấu hình tĩnh hoặc kênh tạm do caller tạo |
| `MessageHeaders.REPLY_CHANNEL` | Header chỉ nơi gửi reply | Không phải field nằm trong MongoDB document |
| `MessageHeaders.ERROR_CHANNEL` | Gợi ý đường xử lý lỗi trong một số flow | Lỗi đồng bộ có thể ném về caller |
| `correlationId` | Liên kết request và reply ở tầng message | Cần giữ nếu flow bất đồng bộ/nhiều nhánh |
| `query / queryFunction` | Quy định bộ lọc MongoDB | Không được mặc định tin payload/header từ client |
| `entityClass` | Kiểu ánh xạ của kết quả | Mặc định là `org.bson.Document` nếu không chỉ định |

Không lấy `MessageHeaders.ID` (UUID của message nội bộ) thay cho ID nghiệp vụ `_id` của MongoDB. Một request mới có thể có message ID mới dù tìm cùng một document.

## 4. Chuẩn bị Spring Boot và MongoDB

### 4.1. Dependencies

Với dự án Spring Boot **3.x** được BOM quản lý các version tương thích:

~~~xml
<!-- Các dependency này nằm trong <dependencies> của pom.xml -->
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

Tùy major version Spring Boot, tên starter MongoDB hoặc version tương thích có thể thay đổi. Dùng dependency management của phiên bản dự án và **blocking MongoDB driver**, không trộn với reactive driver khi đang học cách gọi `MongoOperations` đồng bộ.

### 4.2. MongoDB URI trong lab

Ví dụ `application.yml` dành cho Spring Boot 3.x:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/mongo_gateway_lab
~~~

Ứng dụng sẽ thường có bean `MongoTemplate`/`MongoOperations` khi MongoDB starter và connection config hợp lệ. Trong production, URI/credentials phải đến từ secret/config được quản trị, không để mật khẩu trực tiếp trong tài liệu hoặc source code.

### 4.3. Seed dữ liệu bằng mongosh

Chỉ thực hiện trên database lab:

~~~javascript
use mongo_gateway_lab

db.telemetry_events.insertMany([
  {
    _id: "evt-101",
    deviceId: "node-7",
    sequence: 101,
    status: "NEW",
    temperatureC: 26.5,
    createdAt: ISODate("2026-11-23T02:00:00Z")
  },
  {
    _id: "evt-102",
    deviceId: "node-7",
    sequence: 102,
    status: "NEW",
    temperatureC: 26.8,
    createdAt: ISODate("2026-11-23T02:00:01Z")
  },
  {
    _id: "evt-103",
    deviceId: "node-8",
    sequence: 103,
    status: "DONE",
    temperatureC: 25.9,
    createdAt: ISODate("2026-11-23T02:00:02Z")
  }
])

db.telemetry_events.find(
  { deviceId: "node-7", status: "NEW" }
).sort({ createdAt: 1, _id: 1 })
~~~

Gọi `insertMany` lần thứ hai với cùng `_id` có thể gây duplicate-key error. Khi lặp bài thực hành, dùng các ID mới hoặc seed bằng upsert trong **database test**, không xóa collection production.

## 5. Entity và hợp đồng kết quả

Định nghĩa một entity Java 17+:

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "telemetry_events")
public record TelemetryEvent(
        @Id String id,
        String deviceId,
        long sequence,
        String status,
        BigDecimal temperatureC,
        Instant createdAt) {
}
~~~

Spring Data MongoDB chuyển document từ MongoDB thành `TelemetryEvent` dựa trên mapping và converter. Những tình huống cần quan tâm:

- `@Id` ánh xạ thuộc tính Java `id` với trường MongoDB `_id`.
- Khi `entityClass(TelemetryEvent.class)` được cấu hình, gateway trả các đối tượng kiểu này; không phải JSON string.
- Khi không cấu hình `entityClass`, kiểu mặc định của kết quả thường là `org.bson.Document`.
- Không tự suy luận một record hợp lệ chỉ vì MongoDB mapping thành công: có thể còn thiếu field, status sai, timestamp thiếu hoặc giá trị ngoài miền.
- Nếu collection có nhiều schema/version, nên chuyển sang DTO response riêng thay vì cho HTTP trả thẳng mọi field của entity.

Một request cũng nên là dữ liệu **có kiểu rõ ràng**, không phải JSON query tùy ý:

~~~java
package example.mongodb;

public record FindEventsRequest(String deviceId, int limit) {

    public FindEventsRequest {
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,64}")
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                    "Invalid deviceId or limit (must be 1..100)");
        }
    }
}
~~~

**Đây là kiểm tra đầu vào ở tầng ứng dụng.** Trong hệ thống đa tenant, cần thêm xác thực và **tenant filter từ identity được tin cậy**, không chỉ validate chuỗi `deviceId`.

## 6. Java DSL: truy vấn tĩnh và trả reply qua test channel

Bắt đầu bằng query cố định `status=NEW` để minh họa cơ chế query/reply.

~~~mermaid
flowchart LR
    A["Request producer"] --> R["mongoListRequests: DirectChannel"]
    R --> G["MongoDbOutboundGateway"]
    G -->|"find: status=NEW"| DB["MongoDB"]
    DB -->|"List<TelemetryEvent>"| G
    G --> Q["mongoListReplies: QueueChannel"]
    Q --> T["Consumer/JUnit<br/>receive(timeout)"]
~~~

Cấu hình Spring Integration:

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class MongoStaticQueryFlow {

    @Bean("mongoListRequests")
    public MessageChannel mongoListRequests() {
        return new DirectChannel();
    }

    @Bean("mongoListReplies")
    public QueueChannel mongoListReplies() {
        return new QueueChannel(16);
    }

    @Bean
    public IntegrationFlow mongoFindNewFlow(
            MongoOperations mongoOperations) {

        return IntegrationFlow.from("mongoListRequests")
                .handle(MongoDb.outboundGateway(mongoOperations)
                        .collectionName("telemetry_events")
                        .query("{ 'status': 'NEW' }")
                        .entityClass(TelemetryEvent.class)
                        .expectSingleResult(false))
                .channel("mongoListReplies")
                .get();
    }
}
~~~

**Đây là flow dùng reply channel tĩnh**, phù hợp minh họa và test. Không có `Pollers.fixedDelay(...)`: query chỉ chạy khi một message được gửi vào `mongoListRequests`.

Giải thích:

1. `MongoDb.outboundGateway(mongoOperations)` tạo builder cho gateway sử dụng Spring Data MongoDB blocking API.
2. `collectionName("telemetry_events")` chọn collection xác định.
3. `query("{ 'status': 'NEW' }")` là MongoDB query tĩnh, **không đọc payload của request**.
4. `entityClass(TelemetryEvent.class)` chỉ định kiểu kết quả.
5. `expectSingleResult(false)` là chế độ mặc định, dùng `find(...)` và trả **một list các entity**.
6. `.channel("mongoListReplies")` chuyển reply sang một `QueueChannel` để test/consumer chủ động nhận.
7. `QueueChannel(16)` giới hạn 16 **reply messages**, không giới hạn số document nằm trong một reply list.

### 6.1. Gửi request và đọc reply từ QueueChannel

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public final class ListRequestExample {

    private final MessageChannel requests;
    private final QueueChannel replies;

    public ListRequestExample(
            @Qualifier("mongoListRequests") MessageChannel requests,
            @Qualifier("mongoListReplies") QueueChannel replies) {
        this.requests = requests;
        this.replies = replies;
    }

    public void runOnce() {
        Message<String> request = MessageBuilder
                .withPayload("LIST_NEW")
                .setHeader("correlationId", "lookup-101")
                .build();

        if (!requests.send(request)) {
            throw new IllegalStateException(
                    "MongoDB request not dispatched");
        }

        Message<?> reply = replies.receive(3000);
        if (reply == null) {
            throw new IllegalStateException(
                    "No MongoDB reply in 3 seconds");
        }

        System.out.println(reply.getPayload());
    }
}
~~~

Ở ví dụ này, request payload chỉ là **tín hiệu kích hoạt**, vì query tĩnh không sử dụng payload. Sau đó reply thường là một `List<TelemetryEvent>` (dù chỉ có một document).

**Không áp dụng kiểu dùng chung một `QueueChannel` cho nhiều HTTP request đồng thời.** Những request cạnh tranh có thể nhận nhầm kết quả của nhau nếu không có cơ chế correlation/routing rõ ràng. Đối với API request/reply thực, nên dùng một `@MessagingGateway` với temporary reply channel như mục 8.

## 7. expectSingleResult: một entity hay cả danh sách?

API xác định:

| Cấu hình | MongoOperations tương ứng | Payload có kết quả | Cách dùng |
|---|---|---|---|
| `expectSingleResult(false)` (mặc định) | `find(Query, Class, collection)` | `List<TelemetryEvent>` | API search/list, batch có giới hạn |
| `expectSingleResult(true)` | `findOne(Query, Class, collection)` | `TelemetryEvent` | API tìm một document |

Ví dụ query duy nhất:

~~~java
MongoDb.outboundGateway(mongoOperations)
        .collectionName("telemetry_events")
        .query("{ '_id': 'evt-101' }")
        .entityClass(TelemetryEvent.class)
        .expectSingleResult(true)
~~~

Khi có document `evt-101`, reply payload là một `TelemetryEvent`. Nếu không tìm thấy, `findOne(...)` trả `null`; **Spring Message không hỗ trợ payload null** nên không được mặc định có `Message<TelemetryEvent>` chứa giá trị `null`. Tùy cách ghép endpoint, flow có thể không phát reply và caller phải xử lý timeout/no-reply theo hợp đồng.

Với `expectSingleResult(false)`, `find(...)` có thể trả **danh sách rỗng** khi không có document; hãy kiểm tra cụ thể result trong integration test và quyết định ứng dụng sẽ trả `[]` hay một lỗi nghiệp vụ. **Kết quả rỗng không phải mặc định là lỗi MongoDB.**

### 7.1. Không coi query “một dòng” là chỉ một document

Ngay cả khi query thường tìm được đúng một document trong dữ liệu test, nếu `expectSingleResult(false)`, payload vẫn thuộc contract **List**, không tự động chuyển sang entity. Viết handler bằng kiểu đúng để tránh `ClassCastException`.

### 7.2. Thứ tự khi dùng findOne

Nếu query có thể khớp nhiều document, `findOne` chỉ trả một document. **Không mặc định “first” là bản ghi cũ nhất**. Khi cần lấy bản ghi mới nhất/cũ nhất, tạo `Query` với `Sort` rõ ràng hoặc dùng một collection/query phù hợp.

## 8. Truy vấn theo tham số mỗi request bằng queryFunction

Đây là ứng dụng quan trọng nhất của gateway: một request được biểu diễn bằng DTO, gateway xây `Query` từ payload và trả danh sách đã được **giới hạn**.

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.dsl.MongoDb;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.messaging.Message;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class MongoDynamicQueryFlow {

    @Bean
    public IntegrationFlow searchTelemetryFlow(
            MongoOperations mongoOperations) {

        return IntegrationFlow.from("mongoSearchRequests")
                .handle(MongoDb.outboundGateway(mongoOperations)
                        .collectionName("telemetry_events")
                        .entityClass(TelemetryEvent.class)
                        .expectSingleResult(false)
                        .queryFunction(
                            (Message<FindEventsRequest> message) -> {
                                FindEventsRequest request =
                                        message.getPayload();

                                return Query.query(
                                    Criteria.where("deviceId")
                                            .is(request.deviceId())
                                            .and("status").is("NEW"))
                                    .with(Sort.by(
                                        Sort.Order.asc("createdAt"),
                                        Sort.Order.asc("_id")))
                                    .limit(request.limit());
                            }))
                .get();
    }
}
~~~

`mongoSearchRequests` là tên **input channel** để một Messaging Gateway hoặc producer phát request. Flow trên **cố ý không gắn `.channel("mongoListReplies")` ở cuối**. Reply-producing handler có thể gửi kết quả về **reply channel do caller cung cấp** trong header, phù hợp với `@MessagingGateway` ở phần sau.

Các điểm cần kiểm soát:

- `FindEventsRequest` tự validate `deviceId` và `limit ∈ [1, 100]`.
- `queryFunction` tạo `Query` qua Spring Data `Criteria`, không ghép chuỗi MongoDB query từ input thô.
- Query buộc `status=NEW` và một `deviceId` cụ thể, sắp xếp theo `createdAt` rồi `_id` và giới hạn số document.
- `.limit(...)` giới hạn document trả về **trong DB**, không phải giới hạn số message ở channel.
- Đây vẫn là **blocking query**. Nếu MongoDB chậm, thread dispatch của request có thể bị block cho tới khi DB trả lời hoặc timeout.

**Đừng cho client tự gửi một đối tượng `Query` tùy ý** nếu request đi từ HTTP/Kafka không tin cậy. Nếu multi-tenant, cần đưa tenant scope **bắt buộc** vào Criteria dựa trên context đã xác thực, đồng thời kiểm soát phân quyền DB.

### 8.1. Khai báo @MessagingGateway cho caller

~~~java
package example.mongodb;

import java.util.List;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface TelemetryLookupApi {

    @Gateway(
        requestChannel = "mongoSearchRequests",
        replyTimeout = 5000)
    List<TelemetryEvent> findEvents(FindEventsRequest request);
}
~~~

Khi `findEvents(...)` được gọi, proxy tạo request message, đặt reply channel tạm theo contract của `@MessagingGateway`, gửi vào `mongoSearchRequests`, đợi reply và chuyển payload sang kiểu trả về.

Nếu dùng Spring Integration Java DSL và interface gateway trong dự án, cần để Spring phát hiện/đăng ký interface (qua component scan hoặc `@IntegrationComponentScan` theo cấu hình). Không thể chỉ viết interface mà kỳ vọng một proxy được tạo nếu chưa bật cơ chế đăng ký phù hợp.

Ví dụ caller:

~~~java
import java.util.List;

public final class TelemetryService {

    private final TelemetryLookupApi lookup;

    public TelemetryService(TelemetryLookupApi lookup) {
        this.lookup = lookup;
    }

    public List<TelemetryEvent> find(String deviceId) {
        return lookup.findEvents(new FindEventsRequest(deviceId, 20));
    }
}
~~~

**Đây là phương án request/reply cho nhiều caller.** Khác ví dụ mục 6, không để các HTTP request dùng chung một QueueChannel reply rồi tự gọi `receive`; temporary reply channel giúp từng lời gọi nhận response tương ứng.

### 8.2. Tránh ghép thêm reply channel tĩnh vào flow này

Nếu một flow luôn chuyển kết quả vào `mongoListReplies`, trong khi proxy `@MessagingGateway` đang đợi trên reply channel tạm, **proxy có thể không nhận được phản hồi** và timeout. Cách cấu hình phải nhất quán:

- **Kiểu A:** request channel → outbound gateway → **QueueChannel tĩnh**. Một consumer/test cụ thể đọc queue và chịu trách nhiệm correlation.
- **Kiểu B:** `@MessagingGateway` → request channel → outbound gateway → **trả về replyChannel header**. Không ép reply sang một queue tĩnh không có cơ chế trả về caller.

Khi cần publish kết quả đồng thời cho một hệ thống khác, hãy định nghĩa router/wire tap/pub-sub phù hợp thay vì thay đổi reply destination tùy tiện.

## 9. Query tĩnh, queryExpression và queryFunction

Spring Integration cung cấp các cách thiết lập query khác nhau:

| Cách | Ví dụ | Tính chất |
|---|---|---|
| **`query(String)`** | `query("{ 'status': 'NEW' }")` | Chuỗi query tĩnh |
| **`queryExpression(String)`** | SpEL dùng payload/header | Tạo query động từ expression; cần kiểm soát nguồn |
| **`queryFunction(...)`** | Java Function sinh Spring Data `Query` | Phù hợp với DTO typed, validation, limit và sort |
| **`collectionCallback(...)`** | Callback dùng MongoCollection raw driver | Thay thế thao tác query/find thông thường |

**Không cấu hình `query`, `queryExpression` và `queryFunction` đồng thời** để định nghĩa một request operation; chọn một chiến lược rõ ràng. `collectionCallback` là nhánh thay thế khác, không trộn với các thuộc tính query.

### 9.1. queryExpression trên payload

Ví dụ ý tưởng:

~~~java
MongoDb.outboundGateway(mongoOperations)
        .collectionName("telemetry_events")
        .entityClass(TelemetryEvent.class)
        .queryExpression("payload")
~~~

Trong cấu hình này, expression `payload` chỉ hợp lý khi **payload thực sự là một `Query` hoặc chuỗi query MongoDB hợp lệ**. Nó không tự biến `FindEventsRequest` thành bộ lọc. Với input bên ngoài, đây thường **không phải lựa chọn an toàn nhất** vì có thể mở rộng phạm vi query không mong muốn.

Ưu tiên `queryFunction(...)` để xây query typed và áp các điều kiện không thể bỏ qua, như tenant, status, limit.

### 9.2. Chọn collection động theo header

Có thể dùng:

~~~java
MongoDb.outboundGateway(mongoOperations)
        .collectionNameExpression("headers['trustedCollection']")
        .query("{ 'status': 'NEW' }")
        .entityClass(TelemetryEvent.class)
~~~

**Đây là đoạn minh họa độc lập**, không thay đổi flow đã cấu hình ở mục 8. Chỉ dùng khi `trustedCollection` được đặt từ **mã ứng dụng đã kiểm tra allowlist**, tuyệt đối không để một client HTTP hoặc Kafka chỉ định tùy ý collection.

Ví dụ allowlist:

~~~java
String collection = switch (validatedKind) {
    case "telemetry" -> "telemetry_events";
    case "audit" -> "audit_events";
    default -> throw new IllegalArgumentException(
            "Unsupported collection category");
};
~~~

Trong hệ thống đa tenant, allowlist vẫn chưa đủ: phải kiểm tra **quyền của tenant đối với collection và từng document**.

## 10. MessageCollectionCallback: phép toán không phải find/findOne

Đôi khi request cần đếm document, chạy aggregation pipeline hoặc một thao tác không được biểu diễn thuận tiện bằng `find`/`findOne`. Spring Integration hỗ trợ `MessageCollectionCallback` với quyền truy cập MongoDB collection và request message.

Ví dụ **đếm toàn bộ document** trong collection lab:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.MongoOperations;

@Bean
public IntegrationFlow countTelemetryFlow(
        MongoOperations mongoOperations) {

    return IntegrationFlow.from("mongoCountRequests")
            .handle(MongoDb.outboundGateway(mongoOperations)
                    .collectionName("telemetry_events")
                    .collectionCallback(
                        (collection, requestMessage) ->
                            collection.countDocuments()))
            .get();
}
~~~

Callback dùng API raw MongoDB driver; `collection.countDocuments()` trả số lượng document và gateway tạo reply chứa kết quả số đếm khi không có lỗi. Trong ví dụ này, callback không cần dùng requestMessage. Với phép toán theo request, có thể đọc input đã kiểm tra để xây một `Bson` filter an toàn.

**Nguyên tắc quan trọng:**

- `collectionCallback(...)` **loại trừ** `query(...)` / `queryExpression(...)` / `queryFunction(...)` trên cùng spec.
- Nếu muốn query có phân trang, projection và typed mapping, dùng DSL query thông thường.
- Nếu callback tự chạy aggregate, count, update hoặc raw commands, **bạn chịu trách nhiệm** về kiểu return, phân quyền, timeout, transaction, input validation và tính an toàn của thao tác.
- Không giả định mọi `CollectionCallback` là read-only. Cần chặn thao tác ghi từ người dùng không có quyền.
- Kết quả từ callback có thể không phải `TelemetryEvent`; downstream phải dùng đúng payload type.

Đây là lý do gateway **có thể dùng cho các operation tùy biến**, nhưng đường query/find là mặc định rõ ràng nhất để học request/reply.

## 11. Cấu hình trực tiếp bằng class MongoDbOutboundGateway

Java DSL giúp viết ngắn, nhưng có thể khai báo gateway bean với API Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.mongodb.outbound.MongoDbOutboundGateway;
import org.springframework.messaging.MessageHandler;

@Bean
@ServiceActivator(inputChannel = "mongoDirectRequests")
public MessageHandler mongoDirectGateway(
        MongoOperations mongoOperations) {

    MongoDbOutboundGateway gateway =
            new MongoDbOutboundGateway(mongoOperations);

    gateway.setCollectionNameExpressionString(
            "'telemetry_events'");
    gateway.setQueryExpressionString(
            "'{''status'' : ''NEW''}'");
    gateway.setEntityClass(TelemetryEvent.class);
    gateway.setExpectSingleResult(false);
    gateway.setOutputChannelName("mongoDirectReplies");

    return gateway;
}
~~~

Ở đây `setCollectionNameExpressionString` và `setQueryExpressionString` nhận **SpEL expression string**, vì vậy các dấu nháy đơn bên ngoài và cách escape trong string query có ý nghĩa. Nếu không muốn nhầm hai lớp quoting, Java DSL với `.collectionName(...)` và `.query(...)` thường dễ đọc hơn.

Khai báo `mongoDirectRequests`/`mongoDirectReplies` trong context khi thực hành. Không tạo thêm một endpoint cùng consume `mongoDirectRequests` mà không có chủ đích routing rõ ràng.

## 12. Cấu hình XML outbound-gateway

Dự án dùng Spring Integration XML có thể mô tả request/reply:

~~~xml
<!-- Trong Spring XML đã khai báo namespace int và int-mongodb -->
<int:channel id="mongoQueryRequests"/>

<int:channel id="mongoQueryReplies">
    <int:queue capacity="16"/>
</int:channel>

<int-mongodb:outbound-gateway
        id="mongoQueryGateway"
        request-channel="mongoQueryRequests"
        reply-channel="mongoQueryReplies"
        mongo-template="mongoTemplate"
        collection-name="telemetry_events"
        query="{ 'status': 'NEW' }"
        entity-class="example.mongodb.TelemetryEvent"/>
~~~

Các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `request-channel` | Channel gateway nhận message |
| `reply-channel` | Channel nhận message kết quả |
| `mongo-template` | Bean Spring Data MongoTemplate |
| `mongodb-factory` | Phương án dùng MongoDatabaseFactory thay cho mongo-template |
| `mongo-converter` | Converter khi cấu hình bằng factory |
| `collection-name` | Collection tĩnh |
| `collection-name-expression` | SpEL xác định collection theo request |
| `query` | Chuỗi MongoDB query tĩnh |
| `query-expression` | SpEL tạo chuỗi query hoặc `Query` |
| `entity-class` | Kiểu kết quả |
| `collection-callback` | Phương án thay thế cho query/find |

**Không cấu hình đồng thời `mongo-template` và `mongodb-factory`**, cũng không vừa đặt `collection-callback` vừa dùng query attributes. XML ví dụ giống **flow test với reply channel tĩnh** ở mục 6, không phải cấu hình cho `@MessagingGateway` nhiều request đồng thời.

Với code dùng `@MessagingGateway` trong mục 8, hãy bỏ reply-channel tĩnh hoặc cung cấp reply routing đúng tới caller.

## 13. Trường hợp không tìm thấy, lỗi và reply timeout

### 13.1. Không tìm thấy không nhất thiết là exception

Với danh sách:

~~~text
find(...): []
    |
    v
Reply payload = List rỗng (nếu handler phát list)
    |
    v
Caller trả []
~~~

Với single-result:

~~~text
findOne(...): null
    |
    v
Không có entity payload hợp lệ
    |
    v
Flow có thể không phát reply
    |
    v
Caller xử lý no-reply / timeout
~~~

**Đây là hợp đồng cần test theo phiên bản và kiểu gateway của ứng dụng.** Không nên viết business logic mặc định giả định “không có dữ liệu” sẽ luôn sinh một `Optional.empty()` từ MongoDB outbound gateway. Nếu HTTP API cần `404 Not Found` hoặc trả `[]` ổn định, hãy xác định rõ trong service/facade thay vì để timeout bị hiểu nhầm thành “không có document”.

### 13.2. Các loại timeout khác nhau

| Timeout | Tầng | Khi hết hạn |
|---|---|---|
| `replyTimeout` của `@Gateway` | Caller chờ reply | Có thể không nhận phản hồi dù query chưa kết thúc hoặc không có result |
| MongoDB `serverSelectionTimeout` | Driver chọn server | Lỗi kết nối/không chọn được server |
| MongoDB socket/read timeout | Driver chờ IO | Lỗi timeout IO |
| Query `maxTimeMS` / deadline phù hợp | Server/query | Query có thể bị dừng do vượt budget |
| `QueueChannel.receive(3000)` | Test/consumer chờ một reply message | Trả `null` nếu queue trống quá hạn |
| HTTP timeout | Client HTTP hoặc gateway khác | Có thể hết hạn trước khi query MongoDB kết thúc |

**Reply timeout không phải DB query timeout.** Đặt reply timeout 5 giây không đảm bảo driver sẽ hủy operation MongoDB ngay khi người gọi hết chờ. Cần giới hạn timeout ở driver/query và đảm bảo kích thước kết quả để không giữ thread quá lâu.

### 13.3. Error handling

| Lỗi | Nơi có thể phát sinh | Nên xử lý |
|---|---|---|
| MongoDB không kết nối | Driver/query call | Retry có backoff, cảnh báo, timeout rõ |
| Thiếu quyền DB/collection | MongoDB authorization | Sửa role/config, không retry vô hạn |
| Query sai định dạng | Parse expression / query | Validate sớm, test expression |
| Mapping không hợp lệ | MongoConverter/entity class | Sửa schema/DTO, quarantine khi cần |
| Query quá rộng | Không limit/index | Limit/sort/projection, kiểm tra query plan |
| Empty result | Tìm không có document | Trả `[]` hoặc not-found theo API contract |
| Single result không có reply | `findOne` trả null | Xử lý no-reply/timeout, xác định hợp đồng |
| Reply đi sai channel | Flow ép output cố định | Cấu hình temporary/static reply nhất quán |
| Downstream xử lý reply lỗi | Transformer/HTTP/Kafka sau gateway | Error channel hoặc exception theo flow |
| Retry query sau lỗi | DB/network tạm thời | Read-only retry có giới hạn; xem consistency |

Trong flow đồng bộ dùng `DirectChannel`, lỗi truy vấn có thể quay về caller dưới dạng `MessagingException` hoặc exception được wrap. Với `ExecutorChannel`/asynchronous flow, lỗi có thể đi sang `errorChannel` nếu được cấu hình. **Không giả định mọi lỗi đều vào một kênh lỗi duy nhất.**

## 14. Query performance, batch, sort và projection

Một search API không nên gọi `find({})` rồi tải toàn bộ collection về memory. Với `expectSingleResult(false)`, gateway có thể tạo **một `Message<List<T>>` chứa rất nhiều document**.

| Biện pháp | Tác dụng |
|---|---|
| `Query.limit(n)` | Giới hạn số document trả về |
| `Query.with(Sort)` | Thứ tự xác định |
| `query.fields().include(...)` | Projection những field cần |
| `Query.skip(n)` / cursor keyset | Phân trang theo contract |
| MongoDB index phù hợp | Tránh collection scan không cần thiết |
| Driver/server query timeout | Ngăn query chạy quá thời gian |
| Tenant scope bắt buộc | Ngăn query vượt phạm vi dữ liệu |
| Rate limit và cache | Tránh gọi MongoDB lặp vô hạn |

Ví dụ query hạn chế dữ liệu:

~~~java
Query query = Query.query(
        Criteria.where("deviceId").is("node-7")
                .and("status").is("NEW"))
        .with(Sort.by(
            Sort.Order.asc("createdAt"),
            Sort.Order.asc("_id")))
        .limit(50);

query.fields()
        .include("_id")
        .include("deviceId")
        .include("sequence")
        .include("status")
        .include("createdAt");
~~~

**Projection sang entity:** nếu DTO `TelemetryEvent` có nhiều field nhưng query không lấy chúng, field thiếu có thể nhận giá trị null/default theo mapping. Với API production, nên tạo DTO projection riêng hoặc tránh dùng entity có primitive field bắt buộc khi không truy vấn đủ dữ liệu.

MongoDB index gợi ý cho điều kiện filter + sort ở ví dụ:

~~~javascript
db.telemetry_events.createIndex(
  { deviceId: 1, status: 1, createdAt: 1, _id: 1 }
)
~~~

Index này cần được đánh giá bằng query plan, kích thước collection, dữ liệu thật và chi phí ghi. Không tạo index trên production mà chưa có kế hoạch vận hành.

### 14.1. Vì sao maxMessagesPerPoll không áp dụng?

`MongoDbOutboundGateway` xử lý **một request một lần**, không phải `MessageSource` dùng polling. `maxMessagesPerPoll` chỉ liên quan khi một **poller upstream** đọc QueueChannel/DB/file hoặc kích hoạt message source. Đặt poller vào gateway này không giới hạn kết quả `find()`; phải dùng **query limit**.

### 14.2. Thận trọng với phân trang offset

`skip` lớn có thể tốn tài nguyên và làm kết quả không ổn định khi dữ liệu thay đổi giữa các trang. Với dữ liệu telemetry lớn, cân nhắc keyset pagination theo `(createdAt, _id)` hoặc cursor semantics phù hợp và xác định consistency/read concern.

## 15. Consistency và request/reply không đồng nghĩa snapshot toàn hệ thống

Gateway truy vấn dữ liệu **ở thời điểm DB xử lý request**. Nếu nhiều client đồng thời ghi và đọc, kết quả có thể khác nhau giữa các lần query.

- Một HTTP request có thể nhận danh sách trong khi dữ liệu mới được insert sau khi query bắt đầu.
- Nhiều lần đọc liên tiếp không chắc giống nhau khi có writer cập nhật document.
- Read concern, read preference và transaction/session của MongoDB ảnh hưởng consistency/freshness; cần cấu hình tại Spring Data/driver phù hợp.
- Query một collection không tự tạo transaction xuyên Kafka/JMS/HTTP và MongoDB.
- Gateway request/reply không tự tạo event replay, durable queue hay caching.

Nếu mục tiêu là tra cứu trạng thái mạnh hoặc nhiều document cần snapshot nhất quán, hãy đánh giá MongoDB transaction/read concern thực tế. Nếu cần stream tất cả các thay đổi, **change stream** phù hợp hơn việc gửi query lặp liên tục.

## 16. Kiểm thử MongoDbOutboundGateway

### 16.1. Unit test hợp đồng request

Ví dụ JUnit 5:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FindEventsRequestTest {

    @Test
    void validRequestAccepted() {
        FindEventsRequest request =
                new FindEventsRequest("node-7", 20);

        assertEquals("node-7", request.deviceId());
        assertEquals(20, request.limit());
    }

    @Test
    void rejectsInvalidLimit() {
        assertThrows(IllegalArgumentException.class,
                () -> new FindEventsRequest("node-7", 0));

        assertThrows(IllegalArgumentException.class,
                () -> new FindEventsRequest("node-7", 101));
    }

    @Test
    void rejectsInvalidDeviceId() {
        assertThrows(IllegalArgumentException.class,
                () -> new FindEventsRequest("", 10));
    }
}
~~~

Unit test chỉ kiểm tra contract của request, **không chứng minh queryFunction đã chạy hoặc MongoDB đã trả dữ liệu**.

### 16.2. Integration test với MongoDB test instance

Có thể dùng **Testcontainers** hoặc một MongoDB riêng cho test khi runner hỗ trợ. Tạo database/collection lab, seed dữ liệu với ID duy nhất, sau đó dùng một flow đơn giản kết thúc bằng `QueueChannel` để thu reply.

Minh họa test theo **cấu hình tĩnh** ở mục 6:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoGatewayIntegrationTest {

    @Autowired
    @Qualifier("mongoListRequests")
    MessageChannel requests;

    @Autowired
    @Qualifier("mongoListReplies")
    QueueChannel replies;

    @Test
    void returnsListOfDocuments() {
        assertTrue(requests.send(
                MessageBuilder.withPayload("LIST_NEW").build()));

        Message<?> reply = replies.receive(5000);
        assertNotNull(reply, "No MongoDB reply");
        assertInstanceOf(List.class, reply.getPayload());

        List<?> result = (List<?>) reply.getPayload();
        assertFalse(result.isEmpty(), "No seeded NEW documents");
        assertInstanceOf(TelemetryEvent.class, result.get(0));
    }
}
~~~

**Điều kiện test:** một MongoDB test instance thực sự được cấu hình và seed `status=NEW`. Test nên dùng collection riêng/cleanup riêng; tránh để một suite khác tạo/đổi dữ liệu làm assertion không ổn định. Không chạy bài test có thao tác xóa seed trên production.

### 16.3. Test dynamic @MessagingGateway

Với flow mục 8, inject `TelemetryLookupApi` và assert kết quả trả về:

~~~java
@Autowired
TelemetryLookupApi lookupApi;

@Test
void findsOnlyRequestedDevice() {
    List<TelemetryEvent> result =
            lookupApi.findEvents(
                new FindEventsRequest("node-7", 20));

    assertTrue(result.size() <= 20);
    assertTrue(result.stream().allMatch(
        e -> "node-7".equals(e.deviceId())
                && "NEW".equals(e.status())));
}
~~~

Đây là phần method của một JUnit class đã có context, MongoDB test data và import tương ứng; **không phải file test độc lập**. Nếu response mapping hoặc proxy chưa được đăng ký, test sẽ fail trước assertion — đúng vì mục tiêu là xác minh wiring request/reply.

### 16.4. Test trường hợp không có data

Tách hai trường hợp:

1. Với `expectSingleResult(false)`, tìm theo ID không tồn tại: kỳ vọng logic tìm kiếm trả list rỗng theo contract đang test.
2. Với `expectSingleResult(true)`, tìm ID không tồn tại: xác minh response/no-reply timeout theo cách endpoint được ghép. Nếu API muốn null/not-found nhất quán, thêm adapter/facade xử lý rõ.

Không gộp **DB connection timeout** với **not found** thành một response giống nhau — đó là lỗi nghiệp vụ khác hẳn.

### 16.5. Test lỗi và tải

| Case | Assertion quan trọng |
|---|---|
| MongoDB down | Nhận exception/error response đúng, không treo vô hạn |
| Thiếu quyền read | Authorization error, không retry mù |
| Query không có index | Đo latency/explain trong lab, đưa ra giới hạn |
| User nhập limit 1.000.000 | DTO validate từ chối sớm |
| Payload từ user là query string thô | Không cho đi thẳng vào DB |
| Hai caller đồng thời | Mỗi caller nhận reply đúng, không tranh reply queue |
| Reply timeout nhỏ hơn query time | Phân biệt timeout ở proxy và DB |
| Kết quả nhiều document | Assert giới hạn và sort; không coi đây là nhiều reply messages |
| Callback count | Payload là Long/count, không phải TelemetryEvent |
| Đổi collection theo tenant | Tenant không thể query ngoài quyền được cấp |

## 17. Quan sát, lỗi và lifecycle trong production

Những metric gợi ý (cần thiết kế instrumentation, không mặc định framework xuất đủ tên này):

| Metric | Mục tiêu |
|---|---|
| `mongo_gateway_requests_total` | Tổng request vào gateway |
| `mongo_gateway_replies_total` | Tổng reply thực tế phát |
| `mongo_gateway_empty_results_total` | Kết quả list rỗng hoặc not-found theo contract |
| `mongo_gateway_errors_total` | Query/mapping/auth errors |
| `mongo_gateway_query_duration_seconds` | Thời gian DB query |
| `mongo_gateway_reply_latency_seconds` | Thời gian end-to-end request/reply |
| `mongo_gateway_reply_timeout_total` | Caller chờ quá hạn |
| `mongo_gateway_results_size` | Số document trong một reply |
| `mongo_gateway_inflight_requests` | Số request đang chạy |
| `mongo_gateway_rejected_queries_total` | Request sai limit/tenant/scope |

Không tạo metric label theo `_id`, `deviceId`, request ID hoặc URI với cardinality vô hạn. Có thể dùng trace ID/correlation ID trong log có giới hạn, không ghi toàn bộ query chứa dữ liệu nhạy cảm.

### 17.1. Vòng đời endpoint

- Spring context tạo bean `MongoDbOutboundGateway` và đăng ký consumer tại input channel.
- Khi upstream gửi request, handler thực thi MongoDB query theo cấu hình.
- Gateway **không tự poll**; vì vậy `fixedDelay` không phải thuộc tính riêng của endpoint này.
- Nếu MongoDB chưa sẵn sàng, ứng dụng có thể vẫn start nhưng truy vấn sẽ lỗi khi xử lý.
- Khi endpoint dừng, caller mới có thể không được xử lý hoặc timeout tùy channel/lifecycle.
- Khi shutdown, cần dừng nhận request mới, kiểm soát request in-flight, timeout và đóng resources an toàn.
- Việc dùng ExecutorChannel có thể tách thread, nhưng phải xử lý đúng temporary reply channel/correlation nếu caller đã hết thời gian chờ.

**Không dùng một QueueChannel không giới hạn làm nơi gom reply vĩnh viễn**. Với hệ thống nhiều request, dùng gateway proxy có correlation phù hợp hoặc một pipeline event-driven có bounded queue, TTL và error policy rõ.

## 18. Bảo mật truy vấn MongoDB qua gateway

Một outbound gateway có thể bị lạm dụng vì nó chạy query theo request:

- **Không cho request ngoài gửi MongoDB JSON query tùy ý**: có thể làm lộ collection, tenant khác hoặc query toàn bộ dữ liệu.
- **Đưa query qua Java Criteria** với DTO hợp lệ; ép điều kiện tenant/authorization từ identity đáng tin.
- **Giới hạn limit/sort/projection** và query timeout; chống resource exhaustion bởi tìm kiếm không index.
- **Collection dynamic cần allowlist**, không chỉ regex; kiểm tra người gọi được phép truy cập phạm vi dữ liệu.
- **Least privilege**: cấp tài khoản MongoDB quyền đọc những collection cần thiết. Nếu dùng `collectionCallback` có thể ghi, phải kiểm soát quyền riêng.
- **Không phản hồi nguyên entity chứa field nhạy cảm**: map sang response DTO chỉ có field được phép.
- **Secrets và TLS**: quản lý URI/password an toàn; bật TLS và network policy khi yêu cầu.
- **Rate limit** ở HTTP/gateway/queue trước khi nhiều request cùng vào MongoDB.
- **Không log toàn query** nếu chứa dữ liệu cá nhân; dùng request type, query template ID và correlation ID được kiểm soát.

Ngoài bảo mật ứng dụng, có thể yêu cầu auditing, retention và index theo quy định vận hành. Hợp đồng truy vấn nên được version hóa như mọi contract message trong Spring Integration.

## 19. Bài thực hành tổng hợp

Thiết kế một dịch vụ **HTTP → Spring Integration MongoDbOutboundGateway → MongoDB → HTTP response**.

### Phần A — Truy vấn tĩnh

1. Khởi tạo MongoDB lab và seed ba document của mục 4.
2. Tạo `TelemetryEvent` với `@Document`, `@Id` và các field thích hợp.
3. Tạo `mongoListRequests` dạng DirectChannel và `mongoListReplies` dạng QueueChannel hữu hạn.
4. Viết flow Java DSL dùng `MongoDb.outboundGateway(mongoOperations)`, `query("{ 'status':'NEW' }")`, `entityClass(TelemetryEvent.class)` và `expectSingleResult(false)`.
5. Gửi một request và nhận reply bằng `receive(3000)`; xác nhận payload là `List<TelemetryEvent>` chứ không phải một entity.
6. Đổi thành `expectSingleResult(true)` trong **flow thử nghiệm khác**, query theo `_id` và đối chiếu trường hợp tìm thấy/không tìm thấy.

### Phần B — Dynamic query và @MessagingGateway

1. Viết `FindEventsRequest` với validate deviceId/limit.
2. Dùng `queryFunction` tạo Criteria lọc `deviceId`, `status=NEW`, sort theo `createdAt, _id`, limit tối đa 100.
3. Tạo interface `TelemetryLookupApi` với `@MessagingGateway` và `@Gateway(requestChannel=...)`.
4. Tạo service/controller gọi proxy và chuyển entity sang DTO response; không phơi bày field ngoài quyền.
5. Thử hai request song song; chứng minh reply không bị trả nhầm giữa các caller.
6. Thử query theo thiết bị không có data; xác định response rỗng và no-reply contract rõ ràng.

### Phần C — Callback, XML và vận hành

1. Tạo flow **khác** dùng `collectionCallback((collection, request) -> collection.countDocuments())`, assert reply kiểu số.
2. Viết cấu hình XML `int-mongodb:outbound-gateway` với request/reply channel, entity class và query tĩnh.
3. Đo DB query latency, reply latency, inflight count, empty results, error và timeout.
4. Giả lập MongoDB down, quyền truy cập sai, reply timeout ngắn và kết quả lớn.
5. Thêm tenant scope, allowlist collection và rate limit. Chứng minh một client không thể tìm dữ liệu tenant khác.
6. So sánh gateway với MongoDB inbound polling và change stream, xác định khi nào cần mỗi loại.

**Câu hỏi tự đánh giá:**

- Vì sao tên `MongoDbOutboundGateway` có chữ “outbound” nhưng vẫn tạo reply?
- Gateway khác `MongoDbStoringMessageHandler` ở điểm nào?
- `expectSingleResult(false)` trả bao nhiêu reply message khi DB có 20 document?
- Vì sao `findOne` không tìm được dữ liệu không đồng nghĩa luôn có payload `null`?
- `queryFunction` có lợi gì so với ghép một JSON query string từ HTTP input?
- Tại sao reply QueueChannel tĩnh có thể gây trả nhầm kết quả khi nhiều request đồng thời?
- Khi nào cần `MessageCollectionCallback` thay cho `query`?
- Vì sao không đặt `query` và `collectionCallback` trên cùng gateway?
- `maxMessagesPerPoll` có giới hạn số document trong reply của outbound gateway không?
- Reply timeout có làm MongoDB driver tự hủy query không?
- Vì sao cần giới hạn projection và tenant scope khi trả kết quả?
- Làm thế nào kiểm thử correlation, no-result, lỗi DB và concurrency?

## 20. Tài liệu tham khảo

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): outbound gateway, Java DSL, Java/XML, collection callback, inbound và reactive adapter.
- [Spring Integration API — MongoDbOutboundGateway](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/outbound/MongoDbOutboundGateway.html): class request/reply, constructors, query/collection expressions, callback.
- [Spring Integration API — MongoDbOutboundGatewaySpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDbOutboundGatewaySpec.html): `query`, `queryExpression`, `queryFunction`, `expectSingleResult`, `collectionCallback`.
- [Spring Integration API — MongoDb Java DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): factory `outboundGateway(MongoOperations)` và các adapter khác.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): `@MessagingGateway`, reply channel, timeout, request/reply.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): `MongoOperations`, `Query`, `Criteria`, mapping, transactions, indexes.
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/): consistency/freshness của truy vấn MongoDB.
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/): index và tối ưu truy vấn.

## Kết luận

**`MongoDbOutboundGateway` là một request/reply endpoint**: nhận message truy vấn từ input channel, gọi MongoDB thông qua Spring Data rồi phát kết quả ra reply channel. Gateway phù hợp với tra cứu theo từng yêu cầu của HTTP, JMS, AMQP, Kafka hoặc một flow tích hợp khác, trong khi inbound channel adapter phù hợp với polling và outbound channel adapter phù hợp với thao tác ghi.

Thiết kế bền vững cần **typed query, giới hạn số document, sort rõ ràng, collection và tenant scope an toàn, cùng timeout và error policy được kiểm soát**. Cần hiểu reply payload là **List hay entity**, xử lý riêng not-found và lỗi DB, không nhầm temporary reply channel với queue kết quả dùng chung. Gateway cung cấp cấu trúc tích hợp; **độ tin cậy, tính nhất quán và quyền truy cập dữ liệu** vẫn do hợp đồng ứng dụng, MongoDB configuration và quy trình vận hành quyết định.
