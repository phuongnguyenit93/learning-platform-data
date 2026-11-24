# Query expression và collection trong Spring Integration MongoDB

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **`query` tĩnh**, **`query-expression` (SpEL)** và **`queryFunction`** khi dùng MongoDB inbound adapter và outbound gateway.
- Hiểu chính xác **khi nào expression được đánh giá**: mỗi lượt poll ở inbound hay mỗi request message ở outbound gateway.
- Phân biệt **`collection-name`**, **`collection-name-expression`**, `collectionNameFunction` và `collectionNameSupplier`, đồng thời tránh nhầm **collection** với **database**.
- Dùng **`MongoOperations`/`MongoTemplate`**, `Query`, `Criteria`, `Sort` và projection để giới hạn phạm vi dữ liệu.
- Cấu hình **MongoDB inbound channel adapter** với query/collection động mà không giả định poller có `payload` hay `headers`.
- Cấu hình **MongoDbOutboundGateway** nhận request có kiểu, lấy query theo `payload`, đặt collection dựa trên allowlist và gửi reply theo đúng request.
- Dùng **MongoDB outbound storing handler** chọn collection đích; nhận biết writer không có `query-expression` vì nhiệm vụ của nó là lưu payload.
- Thiết kế validation, tenant isolation, chống query injection, batch limit, idempotency và quan sát lỗi tại đúng tầng.
- Kiểm thử routing theo collection, giới hạn query, kết quả rỗng, update/retry khi poll, request/reply và concurrency.

Bài thuộc chương **Adapter MongoDB** của module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối hệ thống ngoài với Spring Integration bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; đồng thời thực hành file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, chú trọng **hợp đồng message, lỗi và vòng đời kết nối**. Trong bài này, ta tập trung vào hai quyết định tại mỗi thao tác MongoDB: **truy vấn nội dung gì** và **truy cập collection nào**.

## 1. Bài toán: một ứng dụng, nhiều cách đọc và ghi MongoDB

Giả sử hệ thống thu thập telemetry có hai collection:

~~~text
Database: telemetry_lab

telemetry_live
  _id, deviceId, tenantId, status, temperatureC, observedAt

telemetry_archive
  _id, deviceId, tenantId, status, temperatureC, observedAt
~~~

Có ba luồng tích hợp:

1. **Inbound polling:** mỗi 5 giây tìm tối đa 50 document trong `telemetry_live` có `status=NEW` rồi đưa vào `MessageChannel`.
2. **Outbound gateway:** khi API nhận `SearchRequest(deviceId, dataset, limit)`, truy vấn `telemetry_live` hoặc `telemetry_archive` và trả lại danh sách document.
3. **Outbound channel adapter:** khi một message đã chuẩn hóa cần được lưu, chọn collection đích đã được cho phép rồi gọi MongoDB save.

~~~mermaid
flowchart LR
    DB["MongoDB: live/archive"] -->|"query + collection mỗi poll"| I["MongoDB inbound"]
    P["Poller"] -.-> I
    I --> C1["MessageChannel: newTelemetry"]

    API["HTTP / JMS request"] --> C2["mongoSearchRequests"]
    C2 --> G["MongoDbOutboundGateway"]
    G <-->|"query + collection mỗi request"| DB
    G --> R["Reply channel của caller"]

    B["Processed event"] --> C3["toMongo"]
    C3 --> W["MongoDB storing handler"]
    W -->|"collection expression + save"| DB
~~~

**Cả ba endpoint đều truy cập MongoDB, nhưng expression không được đánh giá trong cùng ngữ cảnh.** Đặc biệt, polling inbound không có request `Message` từ bên ngoài để đọc `payload.deviceId`.

## 2. Thuật ngữ cốt lõi: query, expression, collection

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Query** | Điều kiện chọn document và tùy chọn tìm kiếm | `{ status: "NEW" }`; `Query.limit(50)` |
| **`query`** | Một query được khai báo tĩnh trong cấu hình endpoint | `query("{ 'status': 'NEW' }")` |
| **`query-expression`** | Chuỗi SpEL sẽ được đánh giá để tạo **MongoDB query string** hoặc Spring Data `Query` | `@readPlan.currentQuery()`, `@queryFactory.forRequest(payload)` |
| **`queryFunction`** | Java Function nhận `Message<P>` và tạo `Query`, dành cho DSL outbound gateway | `message -> Query.query(...)` |
| **Collection** | Tập document bên trong **một database** | `telemetry_live` |
| **`collection-name`** | Collection cố định | `collectionName("telemetry_live")` |
| **`collection-name-expression`** | SpEL trả về tên collection, thường kiểu String | `@collectionPolicy.resolve(payload.dataset)` |
| **`collectionNameFunction`** | Java Function nhận request Message và trả tên collection | `message -> allowedName(...)` |
| **`collectionNameSupplier`** | Supplier tên collection ở MongoDB inbound source, đánh giá mỗi lần receive | `() -> readPlan.currentCollection()` |
| **Entity class** | Kiểu Java dùng để map document | `TelemetryEvent.class` |

**Query khác collection:** query chọn **document nào** trong collection, collection xác định **tập dữ liệu nào** được hỏi/ghi. Đổi collection **không đổi database** mà `MongoOperations` hoặc `MongoDatabaseFactory` đã kết nối.

### 2.1. query là JSON MongoDB, query-expression là SpEL

Hai cấu hình này không tương đương về cú pháp:

~~~java
// MongoDB query tĩnh (DSL gateway).
.query("{ 'status': 'NEW' }")

// SpEL expression trả ra một Query object (DSL gateway).
.queryExpression("@queryFactory.forRequest(payload)")
~~~

Dòng thứ nhất là **query data**, còn dòng thứ hai là **expression cần được framework đánh giá**. Không mặc định chuỗi `"{ 'status': 'NEW' }"` đặt vào `queryExpression(...)` sẽ có ý nghĩa như `query(...)`; khi cần expression literal phải tuân thủ cú pháp string literal của SpEL hoặc trả `Query` từ một bean.

### 2.2. queryExpression khác expression của update

Ở MongoDB inbound message source có cả:

- **Query expression:** xác định document nào được đọc.
- **Collection expression:** xác định collection được đọc.
- **Update expression (tùy chọn):** mô tả cập nhật document sau khi source lấy được nó.

Một update để document không khớp query ở chu kỳ sau **không đồng nghĩa downstream đã xử lý thành công**, cũng không tự tạo transaction/claim đúng một lần khi nhiều worker hoạt động đồng thời.

## 3. Bảng so sánh endpoint và ngữ cảnh đánh giá expression

| Endpoint | Query dùng lúc nào? | Collection dùng lúc nào? | Root context đáng chú ý |
|---|---|---|---|
| **MongoDB inbound polling** | **Mỗi lần `MessageSource.receive()`** | **Mỗi lần receive()** | Không có request Message đầu vào; thường gọi bean/provider hoặc supplier |
| **MongoDB outbound gateway** | **Mỗi request message** | **Mỗi request message** | Có thể đọc `payload`, `headers` của request |
| **MongoDB outbound storing adapter** | Không có query tìm document | **Mỗi message cần lưu** | Có `payload`/`headers` của message được ghi |
| **MongoDB change stream inbound** | Pipeline/subscription riêng | Subscription trên collection/database tương ứng | Không đánh đồng với polling query |
| **MongoOperations gọi từ service** | Theo lời gọi Java | Theo method và template/factory | Không phải expression của Integration endpoint |

**Bẫy hay gặp:** sao chép expression `payload.deviceId` của outbound gateway vào `query-expression` của polling inbound. Inbound source không nhận một request Message có payload như vậy; expression thường lỗi hoặc không có dữ liệu để đánh giá.

### 3.1. Query động không đồng nghĩa query tùy ý từ client

Tính động nên phục vụ **hợp đồng ứng dụng đã giới hạn**, ví dụ:

- Inbound chuyển từ đọc `status=NEW` sang các document `RETRY` đủ điều kiện.
- Gateway tìm một thiết bị cụ thể trong collection live/archive theo **enum dataset**.
- Writer định tuyến một loại event đã xác thực đến collection tương ứng.

Không dùng biểu thức động để cho HTTP request có thể đọc mọi collection, bỏ điều kiện tenant hoặc cung cấp toàn bộ JSON MongoDB query từ input không tin cậy.

## 4. Chuẩn bị MongoDB lab, dependency và entity

### 4.1. Dependency dự án

Với Spring Boot **3.x** và dependency management của cùng bộ phiên bản:

~~~xml
<!-- Trong phần <dependencies> của pom.xml -->
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

Khi dùng major version khác của Spring Boot, kiểm tra tên starter và BOM tương thích. Bài dùng **MongoOperations blocking** với MongoDB Java driver đồng bộ, không phối trộn với ReactiveMongoOperations.

Ví dụ `application.yml` cho lab:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/telemetry_lab
~~~

URI local không có credentials chỉ dành cho bài tập. Trong môi trường thật, phải dùng secret manager/biến môi trường, TLS và quyền theo collection. Không đưa credential vào source code hoặc log.

### 4.2. Dữ liệu thử trong mongosh

~~~javascript
use telemetry_lab

db.telemetry_live.insertMany([
  {
    _id: "live-101",
    deviceId: "node-7",
    tenantId: "tenant-a",
    status: "NEW",
    temperatureC: 26.5,
    observedAt: ISODate("2026-11-20T10:00:00Z")
  },
  {
    _id: "live-102",
    deviceId: "node-8",
    tenantId: "tenant-a",
    status: "DONE",
    temperatureC: 25.8,
    observedAt: ISODate("2026-11-20T10:01:00Z")
  }
])

db.telemetry_archive.insertOne({
  _id: "arc-201",
  deviceId: "node-7",
  tenantId: "tenant-a",
  status: "DONE",
  temperatureC: 24.9,
  observedAt: ISODate("2026-10-01T10:00:00Z")
})
~~~

Truy vấn thử:

~~~javascript
db.telemetry_live.find(
  { deviceId: "node-7", tenantId: "tenant-a", status: "NEW" }
).sort({ observedAt: -1, _id: -1 }).limit(20)

db.telemetry_archive.find({ deviceId: "node-7" })
~~~

Khi chạy lại nhiều lần, seed cùng `_id` có thể gây duplicate-key. Chỉ dùng collection/database test riêng; có thể dùng `updateOne(..., { upsert: true })` cho test seed có tính lặp lại. Không xóa dữ liệu production.

### 4.3. Entity có kiểu

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "telemetry_live")
public record TelemetryEvent(
        @Id String id,
        String deviceId,
        String tenantId,
        String status,
        BigDecimal temperatureC,
        Instant observedAt) {
}
~~~

`@Document(collection = "telemetry_live")` xác định collection mặc định **khi một thao tác không chỉ định collection khác**. Khi Integration endpoint cung cấp `collectionName("telemetry_archive")`, collection của endpoint có thể **ghi đè mặc định của mapping**; vì vậy không dựa vào annotation để đoán collection thực tế.

Trong hai collection có cùng schema, có thể dùng một `TelemetryEvent.class` để đọc. Với schema khác nhau, nên dùng các entity/DTO riêng hoặc chuyển đổi có kiểm soát.

## 5. Inbound adapter: query tĩnh + collection tĩnh

Bắt đầu bằng flow định kỳ đọc collection `telemetry_live`:

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
public class StaticMongoInboundConfig {

    @Bean("newTelemetry")
    public MessageChannel newTelemetry() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow staticMongoInbound(MongoOperations mongo) {
        return IntegrationFlow
                .from(
                    MongoDb.inboundChannelAdapter(
                            mongo, "{ 'status': 'NEW' }")
                        .collectionName("telemetry_live")
                        .entityClass(TelemetryEvent.class)
                        .expectSingleResult(false),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(1)))
                .split()
                .channel("newTelemetry")
                .get();
    }
}
~~~

**Giải thích:**

1. `MongoDb.inboundChannelAdapter(mongo, queryString)` cấu hình nguồn query MongoDB.
2. `.collectionName("telemetry_live")` chọn collection tĩnh.
3. `.expectSingleResult(false)` là mặc định: mỗi lần nhận có thể tạo **`Message<List<TelemetryEvent>>`**.
4. `.split()` tách danh sách thành từng `Message<TelemetryEvent>`.
5. `Pollers.fixedDelay(5000)` kích hoạt polling; `maxMessagesPerPoll(1)` giới hạn số lần lấy message, **không phải một document**.
6. Không có document khớp thì message source không phát output.
7. Query `status=NEW` **sẽ đọc lại cùng document** ở chu kỳ sau nếu không có bước claim/update trạng thái.

Để `DirectChannel` có subscriber trong bài lab, có thể thêm một handler đơn giản (đặt trong file Java riêng):

~~~java
package example.mongodb;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class NewTelemetryObserver {

    @ServiceActivator(inputChannel = "newTelemetry")
    public void handle(TelemetryEvent event) {
        System.out.printf("Received event id=%s, device=%s%n",
                event.id(), event.deviceId());
    }
}
~~~

Handler này chỉ quan sát; log thành công **không phải** bằng chứng document đã được claim, đã commit vào hệ thống khác hay sẽ không bị poll lại. Trong test, có thể thay handler bằng `QueueChannel` làm test sink để assert từng message.

Vì query string ở đây được cố định lúc cấu hình, nó **không đọc header/payload từ các message khác**. Muốn đổi điều kiện ở mỗi poll, dùng source với expression/supplier phù hợp.

## 6. Inbound: query-expression được đánh giá ở mỗi lần poll

Trong inbound source, `queryExpression` là một Spring `Expression` được đánh giá **mỗi lần `receive()`**. Không có input request message để dùng `payload.deviceId` hoặc `headers.tenantId` như outbound gateway.

### 6.1. Một bean giữ chính sách poll được phép

Ví dụ provider tự tạo query có giới hạn; trong ứng dụng thật, giá trị tenant/status đến từ **cấu hình đã quản trị hoặc trạng thái điều phối tin cậy**, không phải người dùng cung cấp trực tiếp một JSON query.

~~~java
package example.mongodb;

import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component("mongoReadPlan")
public class MongoReadPlan {

    private final AtomicReference<String> activeStatus =
            new AtomicReference<>("NEW");

    public Query currentQuery() {
        String status = activeStatus.get();

        return Query.query(
                Criteria.where("tenantId").is("tenant-a")
                        .and("status").is(status))
                .with(Sort.by(
                    Sort.Order.asc("observedAt"),
                    Sort.Order.asc("_id")))
                .limit(50);
    }

    public String collection() {
        return "telemetry_live";
    }

    public void changeStatusByAdmin(String nextStatus) {
        if (!Set.of("NEW", "RETRY").contains(nextStatus)) {
            throw new IllegalArgumentException(
                    "Polling status not allowed");
        }
        activeStatus.set(nextStatus);
    }
}
~~~

`AtomicReference` giúp việc đọc/ghi status trong demo là thread-safe. Tuy nhiên, **đây chỉ là trạng thái trong RAM**, không được đồng bộ qua nhiều instance, không là checkpoint và sẽ reset khi app restart. Khi muốn điều phối nhiều worker, dùng nguồn trạng thái/lịch được quản lý có quyền truy cập và semantics rõ ràng.

### 6.2. Java DSL với MongoDbMessageSource và SpEL

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.inbound.MongoDbMessageSource;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.data.mongodb.core.MongoOperations;

@Configuration
@EnableIntegration
public class DynamicMongoInboundConfig {

    @Bean
    public MongoDbMessageSource dynamicMongoSource(
            MongoOperations mongo) {

        SpelExpressionParser parser = new SpelExpressionParser();

        MongoDbMessageSource source = new MongoDbMessageSource(
                mongo,
                parser.parseExpression("@mongoReadPlan.currentQuery()"));

        source.setCollectionNameExpression(
                parser.parseExpression("@mongoReadPlan.collection()"));
        source.setEntityClass(TelemetryEvent.class);
        source.setExpectSingleResult(false);

        return source;
    }

    @Bean
    public IntegrationFlow dynamicMongoInbound(
            MongoDbMessageSource dynamicMongoSource) {
        return IntegrationFlow
                .from(dynamicMongoSource,
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(1)))
                .split()
                .channel("newTelemetry")
                .get();
    }
}
~~~

**Cấu hình trên thay thế flow tĩnh của mục 5** trong một lab; không bật cả hai poller trên cùng tập dữ liệu nếu bạn không chủ động muốn kiểm tra việc đọc trùng. Bean `newTelemetry` được khai báo ở cấu hình chung hoặc ví dụ mục 5.

- `@mongoReadPlan.currentQuery()` là SpEL gọi bean trong Spring context; kết quả trả một **Spring Data `Query`**.
- `@mongoReadPlan.collection()` là SpEL trả **String** tên collection.
- Source sẽ đánh giá expression mỗi lượt receive, vì vậy lệnh đổi status **được cấp quyền** có thể ảnh hưởng các lượt poll sau.
- Cần có BeanFactory/ApplicationContext do Spring quản lý để SpEL tham chiếu `@mongoReadPlan`.
- Cấu hình động không đồng nghĩa query update đến ngay lập tức khi thay status; nó chỉ có hiệu lực **khi poll tiếp theo chạy**.

**Lưu ý quan trọng:** Spring Data `Query` được tạo trong phương thức `currentQuery()` mỗi lần, không dùng lại một Query mutable rồi sửa qua nhiều thread. Nếu yêu cầu đổi nhiều giá trị cùng lúc (tenant, status, limit), nên thay **một immutable policy object** atomically, tránh đọc status thuộc cấu hình mới nhưng collection thuộc cấu hình cũ.

### 6.3. XML equivalent

~~~xml
<!-- Trong Spring XML có namespace int và int-mongodb -->
<int-mongodb:inbound-channel-adapter
    id="mongoDynamicInbound"
    channel="mongoLists"
    mongo-template="mongoTemplate"
    query-expression="@mongoReadPlan.currentQuery()"
    collection-name-expression="@mongoReadPlan.collection()"
    entity-class="example.mongodb.TelemetryEvent">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-mongodb:inbound-channel-adapter>
~~~

XML này minh họa **một cách cấu hình khác**: bean `mongoReadPlan` phải tồn tại, channel `mongoLists` phải được khai báo và downstream nhận List hoặc đi qua splitter. Không khai báo thêm `query` khi đã dùng `query-expression`, cũng không dùng cả `collection-name` và `collection-name-expression` trên cùng endpoint.

### 6.4. Khi nên chọn collectionNameSupplier

MongoDB inbound DSL cho phép:

~~~java
MongoDb.inboundChannelAdapter(
        mongo, "{ 'status': 'NEW' }")
    .collectionNameSupplier(
        () -> mongoReadPlan.collection())
    .entityClass(TelemetryEvent.class);
~~~

Trong đó `mongoReadPlan` là bean được inject vào class cấu hình. Đây là **đoạn builder thay thế**, chưa là một IntegrationFlow hoàn chỉnh. `collectionNameSupplier` có thể giảm nhu cầu dùng SpEL nếu chỉ cần Java function để chọn collection mỗi lượt receive; vẫn phải kiểm soát allowlist và nhất quán với query.

## 7. Outbound gateway: query theo request message

Khác inbound polling, **`MongoDbOutboundGateway`** nhận một request Message. SpEL và Java Function có thể đọc trực tiếp `payload` hoặc `headers` của request để chọn query và collection.

### 7.1. Định nghĩa request có kiểu và danh mục collection

~~~java
package example.mongodb;

public enum Dataset {
    LIVE,
    ARCHIVE
}

public record SearchRequest(
        String deviceId,
        Dataset dataset,
        int limit) {

    public SearchRequest {
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,64}")
                || dataset == null
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                    "Invalid MongoDB search request");
        }
    }
}
~~~

Dùng enum thay vì tên collection thô giúp giới hạn những lựa chọn từ client. Tuy nhiên, với ứng dụng multi-tenant, việc người dùng chọn `ARCHIVE` hợp lệ về mặt enum **chưa đủ** để cho phép đọc archive: kiểm tra **role/tenant authorization** trước khi gọi MongoDB.

### 7.2. Query builder và collection policy dùng chung

~~~java
package example.mongodb;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component("mongoQueryPolicy")
public class MongoQueryPolicy {

    public Query forRequest(SearchRequest request) {
        // Request constructor đã validate deviceId/dataset/limit.
        // tenantId phải lấy từ một context được xác thực.
        String authorizedTenant = "tenant-a"; // Chỉ dành cho lab.

        return Query.query(
                Criteria.where("tenantId").is(authorizedTenant)
                        .and("deviceId").is(request.deviceId()))
                .with(Sort.by(
                    Sort.Order.desc("observedAt"),
                    Sort.Order.desc("_id")))
                .limit(request.limit());
    }

    public String collectionFor(Dataset dataset) {
        return switch (dataset) {
            case LIVE -> "telemetry_live";
            case ARCHIVE -> "telemetry_archive";
        };
    }
}
~~~

**Trong production không hard-code tenant `tenant-a`**. Thay bằng tenant ID được xác thực, bảo đảm giá trị đó được đưa vào Criteria trong server-side query. Không lấy tenantId từ `payload` mà người gọi có thể tự sửa, trừ khi có bước kiểm tra quyền tương ứng.

### 7.3. Java DSL với queryFunction và collectionNameFunction

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.messaging.Message;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class MongoSearchFlowConfig {

    @Bean
    public IntegrationFlow mongoSearchFlow(
            MongoOperations mongo,
            MongoQueryPolicy policy) {

        return IntegrationFlow.from("mongoSearchRequests")
                .handle(MongoDb.outboundGateway(mongo)
                    .entityClass(TelemetryEvent.class)
                    .expectSingleResult(false)
                    .queryFunction(
                        (Message<SearchRequest> message) ->
                            policy.forRequest(message.getPayload()))
                    .collectionNameFunction(
                        (Message<SearchRequest> message) ->
                            policy.collectionFor(
                                message.getPayload().dataset())))
                .get();
    }
}
~~~

Điểm cần hiểu:

1. `queryFunction` nhận **request message**, không phải một `MessageSource.receive()` không có đầu vào.
2. `collectionNameFunction` cũng nhận request; cùng một `SearchRequest` quyết định query và collection.
3. `queryFunction` trả **Spring Data `Query`** có filter, sort và limit; không nối string query từ client.
4. `collectionNameFunction` chọn một trong **hai collection có allowlist**.
5. `expectSingleResult(false)` tạo reply với danh sách `TelemetryEvent`.
6. Flow không ép reply vào QueueChannel tĩnh, để `@MessagingGateway` sử dụng **temporary reply channel** theo từng caller.
7. Đây là **blocking gateway**; cần điều chỉnh MongoDB socket/query timeout và pool nếu nhiều request đồng thời.

### 7.4. Proxy request/reply theo từng caller

~~~java
package example.mongodb;

import java.util.List;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface MongoSearchApi {

    @Gateway(
        requestChannel = "mongoSearchRequests",
        replyTimeout = 5000)
    List<TelemetryEvent> search(SearchRequest request);
}
~~~

Gọi:

~~~java
List<TelemetryEvent> found = searchApi.search(
        new SearchRequest("node-7", Dataset.LIVE, 20));
~~~

Đoạn gọi `searchApi` nằm trong một service đã inject interface đó. `@IntegrationComponentScan` trong cấu hình ở trên giúp tìm và đăng ký proxy gateway nếu package scan bao gồm interface.

**Không dùng một QueueChannel reply chung rồi để nhiều HTTP request gọi `receive()` cạnh tranh**. Một message thuộc request A có thể bị consumer của request B lấy nhầm. Temporary reply channel do `@MessagingGateway` cấp sẽ ghép response với đúng lời gọi.

## 8. queryExpression và collectionNameExpression với SpEL

Java Function thường dễ kiểm thử hơn, nhưng SpEL hữu ích trong cấu hình XML hoặc khi muốn tham chiếu bean chính sách.

### 8.1. Gateway: expression đọc payload của request

Thay thế hai function ở flow trước bằng:

~~~java
MongoDb.outboundGateway(mongo)
    .entityClass(TelemetryEvent.class)
    .expectSingleResult(false)
    .queryExpression(
        "@mongoQueryPolicy.forRequest(payload)")
    .collectionNameExpression(
        "@mongoQueryPolicy.collectionFor(payload.dataset)")
~~~

Trong outbound gateway:

- `payload` là một `SearchRequest` do caller gửi.
- `@mongoQueryPolicy` là bean Spring do framework tìm trong expression context.
- `forRequest(payload)` phải trả `Query`, còn `collectionFor(...)` trả tên collection `String`.
- Nếu tên method hoặc field sai, lỗi xuất hiện **khi expression được đánh giá cho request**.

**Không khai báo đồng thời `query(...)`, `queryExpression(...)` và `queryFunction(...)`** cho một gateway: đó là những phương án thay thế. Tương tự, chọn một trong `collectionName(...)`, `collectionNameExpression(...)` hoặc `collectionNameFunction(...)`.

### 8.2. Query expression trên headers

Nếu header được **ứng dụng đáng tin** đặt sau bước xác thực, SpEL có thể đọc:

~~~java
.queryExpression(
    "@mongoQueryPolicy.forRequest(payload)")
.collectionNameExpression(
    "@mongoCollectionPolicy.fromApprovedHeader(headers['datasetKind'])")
~~~

`mongoCollectionPolicy` phải là bean được khai báo và method `fromApprovedHeader` cần **allowlist**. Không đặt trực tiếp:

~~~java
.collectionNameExpression(
    "headers['collection']")
~~~

trong một luồng tiếp nhận header từ người dùng không tin cậy nếu không có bước kiểm tra quyền và giới hạn collection. Đây là ví dụ **mẫu không an toàn** khi dữ liệu nguồn chưa được kiểm soát.

### 8.3. Ví dụ query tĩnh không dùng payload

~~~java
MongoDb.outboundGateway(mongo)
    .collectionName("telemetry_live")
    .query("{ 'status': 'NEW' }")
    .entityClass(TelemetryEvent.class)
    .expectSingleResult(false)
~~~

Query này chạy khi có request message nhưng **nội dung filter không phụ thuộc request**. Đừng mong gửi payload `"node-7"` sẽ tự thay điều kiện MongoDB nếu chưa cấu hình expression/function sử dụng payload đó.

## 9. Outbound storing adapter: collection expression, không có query tìm kiếm

MongoDB outbound channel adapter thường sử dụng `MongoDbStoringMessageHandler` để **lưu payload**. Nó **không có query-expression để tìm document** như inbound source/gateway. Phần dynamic phù hợp ở writer là **chọn collection để save payload**.

~~~mermaid
flowchart LR
    P["Producer Message<TelemetryEvent>"] --> V["Validate + routing policy"]
    V --> C["toMongo: MessageChannel"]
    C --> H["MongoDbStoringMessageHandler"]
    H -->|"collectionNameExpression"| DB["MongoDB live / archive"]
~~~

### 9.1. Ví dụ Java DSL với SpEL và allowlist

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.outbound.MongoDbStoringMessageHandler;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class MongoDynamicWriteConfig {

    @Bean("toMongo")
    public MessageChannel toMongo() {
        return new DirectChannel();
    }

    @Bean
    public MongoDbStoringMessageHandler mongoWriter(
            MongoOperations mongo) {

        MongoDbStoringMessageHandler writer =
                new MongoDbStoringMessageHandler(mongo);

        SpelExpressionParser parser = new SpelExpressionParser();
        writer.setCollectionNameExpression(
            parser.parseExpression(
                "@mongoCollectionPolicy.fromApprovedHeader("
                    + "headers['approvedDataset'])"));

        return writer;
    }

    @Bean
    public IntegrationFlow mongoWriteFlow(
            MongoDbStoringMessageHandler mongoWriter) {
        return IntegrationFlow.from("toMongo")
                .handle(mongoWriter)
                .get();
    }
}
~~~

Bean policy cho writer:

~~~java
package example.mongodb;

import org.springframework.stereotype.Component;

@Component("mongoCollectionPolicy")
public class MongoCollectionPolicy {

    public String fromApprovedHeader(String category) {
        if (category == null) {
            throw new IllegalArgumentException(
                    "approvedDataset is missing");
        }

        return switch (category) {
            case "LIVE" -> "telemetry_live";
            case "ARCHIVE" -> "telemetry_archive";
            default -> throw new IllegalArgumentException(
                    "Unknown or unauthorized dataset");
        };
    }
}
~~~

Producer **tin cậy** gửi một message đã validate với header do server đặt:

~~~java
Message<TelemetryEvent> message =
        MessageBuilder.withPayload(event)
            .setHeader("approvedDataset", "LIVE")
            .build();

toMongo.send(message);
~~~

Đoạn này giả định biến `event` và `toMongo` đã được khai báo/inject, cùng import `Message` và `MessageBuilder`. Header `approvedDataset` phải được **thiết lập sau khi kiểm tra quyền và loại sự kiện**, không chuyển thẳng header cùng tên từ HTTP/UDP/Kafka chưa xác thực.

### 9.2. Writer save không phải partial update

`MongoDbStoringMessageHandler` thông thường dùng `MongoOperations.save(payload, collectionName)`. Nếu payload có `@Id` thì save có thể ghi đè/thay thế document theo ID. Không coi đây là thao tác patch field hoặc insert-only.

Nếu cần update `status` theo điều kiện/optimistic locking, dùng service gọi `MongoOperations.updateFirst` hoặc `findAndModify` riêng. **Chọn collection đúng là điều kiện cần nhưng chưa bảo đảm idempotency.**

### 9.3. Collection expression không thay đổi MongoDB database

Nếu bean `MongoOperations` kết nối tới database `telemetry_lab`, các expression trả `telemetry_live` hay `telemetry_archive` đều chọn **collection bên trong telemetry_lab**.

Muốn truy cập một database khác, phải dùng **MongoOperations/MongoDatabaseFactory** kết nối đến database đó hoặc routing tầng service đã thiết kế. Không cố nhét tên database từ client vào `collectionNameExpression` để thay đổi connection.

## 10. XML: query-expression và collection-name-expression

Spring Integration hỗ trợ namespace XML khi ứng dụng chưa dùng Java DSL.

### 10.1. Inbound polling: expression trên policy bean

~~~xml
<!-- Trong Spring XML có khai báo int và int-mongodb namespace -->
<int-mongodb:inbound-channel-adapter
        id="mongoDynamicPoller"
        channel="mongoInboundResults"
        mongo-template="mongoTemplate"
        query-expression="@mongoReadPlan.currentQuery()"
        collection-name-expression="@mongoReadPlan.collection()"
        entity-class="example.mongodb.TelemetryEvent">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-mongodb:inbound-channel-adapter>
~~~

`mongoReadPlan` là bean do Spring quản lý; `mongoInboundResults` là channel nhận `Message<List<TelemetryEvent>>` khi có dữ liệu, nếu chưa có splitter.

### 10.2. Outbound gateway: expression trên request

~~~xml
<int:channel id="mongoQueryRequests"/>
<int:channel id="mongoQueryReplies">
    <int:queue capacity="16"/>
</int:channel>

<int-mongodb:outbound-gateway
        id="mongoDynamicLookup"
        request-channel="mongoQueryRequests"
        reply-channel="mongoQueryReplies"
        mongo-template="mongoTemplate"
        query-expression="@mongoQueryPolicy.forRequest(payload)"
        collection-name-expression="@mongoQueryPolicy.collectionFor(payload.dataset)"
        entity-class="example.mongodb.TelemetryEvent"/>
~~~

**Ví dụ XML này dùng reply channel tĩnh**, thích hợp khi có một test consumer hoặc một dispatcher chịu trách nhiệm correlation. Với nhiều request HTTP đồng thời, hãy dùng gateway proxy với temporary reply channel và không đưa tất cả kết quả vào một queue cạnh tranh.

### 10.3. Outbound storing adapter: chỉ chọn collection

~~~xml
<int:channel id="toMongoXml"/>

<int-mongodb:outbound-channel-adapter
        id="mongoStoreByCategory"
        channel="toMongoXml"
        mongo-template="mongoTemplate"
        collection-name-expression=
          "@mongoCollectionPolicy.fromApprovedHeader(headers['approvedDataset'])"/>
~~~

Tùy parser XML/formatter, nên đặt toàn bộ attribute expression trên một dòng khi sao chép. Không thêm thuộc tính `query-expression` vào outbound writer vì endpoint không phải polling/query gateway.

### 10.4. Những cặp tùy chọn không khai báo đồng thời

| Endpoint | Phải chọn một |
|---|---|
| Inbound | `query` **hoặc** `query-expression` |
| Inbound | `collection-name` **hoặc** `collection-name-expression` |
| Gateway | `query`, `query-expression` **hoặc** Java DSL `queryFunction` |
| Gateway | `collection-name`, `collection-name-expression` **hoặc** Java DSL `collectionNameFunction` |
| Gateway | Query attributes **hoặc** `collection-callback` |
| Writer | `collection-name` **hoặc** `collection-name-expression` |
| Bất kỳ endpoint MongoDB tương thích | `mongo-template` **hoặc** `mongodb-factory` (kèm converter nếu API yêu cầu) |

Các cặp này là **phương án cấu hình thay thế**, không phải hệ thống ưu tiên tự chọn khi cả hai cùng được đặt. Khi cần một bean converter tùy chỉnh, đảm bảo constructor/factory overload hỗ trợ và mapping nhất quán.

## 11. Query performance và giới hạn dữ liệu

Với inbound `expectSingleResult(false)` hoặc outbound gateway list query, một query rộng có thể tạo **một Message chứa List rất lớn**.

Ví dụ `Query` có điều kiện và giới hạn:

~~~java
Query query = Query.query(
        Criteria.where("tenantId").is(authorizedTenant)
                .and("deviceId").is(request.deviceId()))
        .with(Sort.by(
            Sort.Order.desc("observedAt"),
            Sort.Order.desc("_id")))
        .limit(Math.min(request.limit(), 100));

query.fields()
        .include("_id")
        .include("deviceId")
        .include("tenantId")
        .include("observedAt");
~~~

**Lưu ý projection:** nếu vẫn map vào `TelemetryEvent` có những field không được trả về, các field đó có thể là `null`/default. Hãy dùng DTO projection thích hợp hoặc lấy đủ field cần thiết.

| Cách kiểm soát | Tác dụng |
|---|---|
| Filter bắt buộc `tenantId` | Ngăn đọc dữ liệu tenant khác |
| `Query.limit(n)` | Giới hạn số document DB trả |
| `Sort` ổn định với `_id` | Dễ tái lập và phân trang |
| Projection | Giảm bytes/network và tránh lộ field không cần |
| Index theo filter + sort | Tránh scan collection quá rộng |
| Query time limit và driver timeout | Giới hạn tài nguyên khi query chậm |
| Request rate limit | Giảm nguy cơ DoS tới MongoDB |
| Cursor/keyset pagination | Có thể tốt hơn `skip` lớn ở dataset lớn |
| Monitoring latency/count | Phát hiện query plan hoặc collection routing lỗi |

Ví dụ index cho query có tenant + device + thời gian:

~~~javascript
db.telemetry_live.createIndex({
  tenantId: 1,
  deviceId: 1,
  observedAt: -1,
  _id: -1
})
~~~

Index nên được đánh giá theo **workload thật và query plan**, không tạo tràn lan trên production. Khi query thêm `status` làm filter thường xuyên, cân nhắc vị trí status trong compound index theo pattern truy vấn.

### 11.1. maxMessagesPerPoll không giới hạn số document

Trong inbound, `maxMessagesPerPoll(1)` nghĩa là tối đa một lần nhận message từ source theo chu kỳ, **không có nghĩa query trả một document**. Muốn lấy tối đa 50 document thì phải thêm `Query.limit(50)` hoặc cấu hình tương ứng ở truy vấn.

Outbound gateway không cần poller riêng: không có `maxMessagesPerPoll` trên gateway để giới hạn kết quả. Giới hạn nằm trong **Query**.

### 11.2. Sorting và pagination

Nếu yêu cầu “mới nhất”, phải sort rõ trên thời gian (thường kèm ID). Không giả định MongoDB `findOne` luôn lấy document mới nhất khi không có sort.

Với phân trang theo offset, `skip` lớn có thể gây tải và làm các trang thiếu ổn định khi collection thay đổi. Có thể dùng **keyset** theo `(observedAt, _id)` và giữ contract đồng nhất giữa query, index và cursor.

## 12. Đọc lặp, updateExpression và tính đúng đắn nghiệp vụ

Với MongoDB inbound query:

~~~text
Query: status=NEW
Poll #1 -> live-101
Poll #2 -> live-101
Poll #3 -> live-101
~~~

Nếu không có thay đổi trạng thái, **cùng document có thể được đọc nhiều lần**. Việc đổi collection expression mỗi poll không tự tạo checkpoint hoặc state của consumer.

Một phương án đơn giản là update document sau khi source đọc:

~~~java
import org.springframework.data.mongodb.core.query.Update;

MongoDb.inboundChannelAdapter(
        mongo, "{ 'status': 'NEW' }")
    .collectionName("telemetry_live")
    .entityClass(TelemetryEvent.class)
    .update(new Update().set("status", "CLAIMED"));
~~~

Đây là **đoạn builder thay thế** chỉ để minh họa `update`. Nó không bảo đảm downstream đã commit khi trạng thái chuyển CLAIMED.

**Các rủi ro cần xử lý:**

- App crash sau claim, trước khi xử lý xong → document bị kẹt.
- Hai instance có thể tranh cùng document nếu không dùng claim nguyên tử có điều kiện.
- Payload đọc trước update có thể còn `status=NEW` dù DB đã đổi trạng thái.
- Nếu query thay đổi từ NEW sang RETRY giữa các poll, chính sách retry phải rõ ràng.
- Nếu collection expression đổi trong lúc query/update đang chạy, cần bảo đảm mỗi thao tác có **cặp query–collection nhất quán** theo thiết kế.
- Khi downstream gửi HTTP/Kafka/JMS/AMQP, cần idempotency và ACK/transaction theo hệ thống đích.

Với workflow cần tin cậy, cân nhắc **atomic `findAndModify` claim**, owner/lease, retry/backoff, unique event ID và dead-letter/quarantine. `PseudoTransactionManager` dùng cho transaction synchronization không tự biến mọi thao tác MongoDB thành transaction thật.

## 13. Trường hợp trống, lỗi expression và reply timeout

| Tình huống | Tác động | Cách xử lý |
|---|---|---|
| Inbound query không có document | Source không phát Message | Tính empty poll bình thường, không tự tạo lỗi |
| Gateway `find(...)` trả list rỗng | Có thể trả `List` rỗng | Caller xử lý empty result theo API contract |
| Gateway `findOne(...)` không tìm thấy | Kết quả null, flow có thể không phát reply | Xử lý no-reply/not-found và timeout |
| Expression trả sai kiểu | Không tạo được MongoDB Query hoặc collection name | Kiểm tra expression bằng unit/integration test |
| Expression truy cập `payload` trong inbound | Không có request payload | Chuyển sang provider bean/supplier cho poller |
| Collection expression trả null/rỗng | Không có tên collection hợp lệ | Fail fast, kiểm soát default rõ |
| Collection không tồn tại | Có thể query trả rỗng hoặc writer tạo collection tùy quyền/hành vi | Validate allowlist và cấu hình, không tự suy ra lỗi |
| Query sai schema/field | Trả rỗng hoặc mapping lỗi | Kiểm tra tên field, converter, projection |
| MongoDB không kết nối được | Lỗi driver/timeouts | Retry có giới hạn, health/metrics |
| Reply channel bị ép sai | Caller không nhận kết quả | Dùng temporary reply channel hoặc correlation rõ |
| Query quá rộng | CPU, RAM, network và pool quá tải | Limit, index, projection, rate limit |

**Không nhầm “không có dữ liệu” với “MongoDB lỗi”.** Với `findOne` trả null, Spring Messaging không có payload null thông thường; request/reply caller có thể phải áp chính sách not-found riêng.

### 13.1. Timeout cần phân tầng

- `replyTimeout` của `@Gateway`: caller chờ bao lâu để nhận reply.
- MongoDB server selection/socket timeout: driver chờ server hoặc I/O.
- Query max time: giới hạn thời gian thực thi query nếu được cấu hình.
- `QueueChannel.receive(3000)`: test consumer chờ Spring Message.
- Poller fixed delay: khoảng cách giữa những lượt receive của inbound.

**Reply timeout không phải query cancellation:** caller hết thời gian đợi không có nghĩa MongoDB operation lập tức bị hủy. Đặt timeout ở tầng driver/query và giới hạn số kết quả để tránh giữ tài nguyên không cần thiết.

## 14. Bảo mật: SpEL không phải ngôn ngữ query được trao cho người dùng

Để bảo vệ một ứng dụng có biểu thức động:

1. **Không cho người dùng tự gửi SpEL expression string** để hệ thống biên dịch/chạy; SpEL có khả năng truy cập bean/method trong context và phải được coi là cấu hình **tin cậy**.
2. **Không nối JSON MongoDB query từ input** mà không validate, vì một client có thể chèn MongoDB operators không mong muốn hoặc yêu cầu toàn bộ collection.
3. **Dùng typed DTO và Criteria** để ghép các điều kiện bắt buộc như tenant, status, deviceId, limit.
4. **Không để header chọn collection tự do**; chuyển từ một enum/mã đã xác thực sang allowlist cụ thể.
5. **Phân quyền theo tenant** trước khi cho phép chọn LIVE/ARCHIVE; chỉ có allowlist tên collection chưa đủ.
6. **Least privilege** ở MongoDB: tài khoản chỉ có các quyền read/write cần cho endpoint.
7. **Giới hạn collection cardinality**: không tạo collection mới cho mỗi request hoặc event ID.
8. **Không log query chứa dữ liệu nhạy cảm**; ghi operation name, query template ID, collection logical name và correlation ID.
9. **Rate limit, timeout, index** và monitoring để phòng trường hợp truy vấn nặng gây DoS.
10. Nếu có nhiều database, phân tách MongoOperations/factory và xác minh routing, không suy từ collection name rằng đã chuyển database.

Ví dụ **không an toàn** nếu gọi từ header chưa tin cậy:

~~~text
query-expression = "payload"
collection-name-expression = "headers['collection']"
~~~

Khi `payload` là query tùy ý và header `collection` không được kiểm tra, một client có thể vượt phạm vi dữ liệu. **Hợp đồng đúng** là `SearchRequest` có giới hạn và policy bean server-side đưa ra Query + collection.

## 15. Unit test query policy và collection routing

### 15.1. Không cần MongoDB để kiểm tra Query/collection

Dùng JUnit 5:

~~~java
package example.mongodb;

import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.query.Query;
import static org.junit.jupiter.api.Assertions.*;

class MongoQueryPolicyTest {

    private final MongoQueryPolicy policy =
            new MongoQueryPolicy();

    @Test
    void buildsBoundedTenantQuery() {
        Query query = policy.forRequest(
            new SearchRequest("node-7", Dataset.LIVE, 20));

        assertEquals(20, query.getLimit());
        assertEquals("node-7",
            query.getQueryObject().getString("deviceId"));
        assertEquals("tenant-a",
            query.getQueryObject().getString("tenantId"));
    }

    @Test
    void routesOnlyAllowedCollections() {
        assertEquals("telemetry_live",
            policy.collectionFor(Dataset.LIVE));
        assertEquals("telemetry_archive",
            policy.collectionFor(Dataset.ARCHIVE));
    }

    @Test
    void rejectsBadRequest() {
        assertThrows(IllegalArgumentException.class,
            () -> new SearchRequest("", Dataset.LIVE, 20));
        assertThrows(IllegalArgumentException.class,
            () -> new SearchRequest("node-7", Dataset.LIVE, 5000));
        assertThrows(IllegalArgumentException.class,
            () -> new SearchRequest("node-7", null, 20));
    }
}
~~~

Các test này kiểm tra builder và allowlist, **chưa chứng minh MongoDB adapter đã bind đúng collection** hoặc DB trả đúng dữ liệu. Dùng integration test để xác minh end-to-end.

### 15.2. Test expression SpEL với context đúng

Mục tiêu:

- Outbound gateway: expression `@mongoQueryPolicy.forRequest(payload)` phải xử lý `Message<SearchRequest>`.
- Inbound source: expression `@mongoReadPlan.currentQuery()` phải hoạt động khi **không có request payload**.
- Collection policy: nếu header `approvedDataset` thiếu/không hợp lệ, writer phải fail trước khi gọi MongoDB.

Khi unit-test SpEL độc lập, cần **BeanResolver** và EvaluationContext tương ứng với Spring Integration. Dùng `StandardEvaluationContext` không đăng ký BeanResolver rồi kết luận expression `@beanName` sai là một test không hợp lệ. Đơn giản hơn, thử expression qua một Spring Test context có bean policy thật.

## 16. Integration test với MongoDB test instance

Sử dụng **MongoDB riêng cho test** hoặc Testcontainers khi runner hỗ trợ Docker. Seed tài liệu với ID duy nhất và dọn đúng collection sau test.

~~~mermaid
flowchart LR
    T["JUnit gửi SearchRequest"] --> G["MongoDbOutboundGateway"]
    G -->|"Query + collection theo policy"| DB["MongoDB test"]
    DB --> G
    G --> R["Reply Message<List<TelemetryEvent>>"]
    R --> A["JUnit assert IDs và collection"]
~~~

### 16.1. Test gateway routing qua hai collection

Trong class JUnit đã có Spring Boot test context và `MongoSearchApi` proxy:

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoCollectionRoutingIT {

    @Autowired
    MongoSearchApi searchApi;

    @Test
    void searchesLiveCollection() {
        List<TelemetryEvent> result = searchApi.search(
            new SearchRequest("node-7", Dataset.LIVE, 20));

        assertTrue(result.size() <= 20);
        assertTrue(result.stream().allMatch(
            e -> "node-7".equals(e.deviceId())
                && "tenant-a".equals(e.tenantId())));
    }

    @Test
    void searchesArchiveCollection() {
        List<TelemetryEvent> result = searchApi.search(
            new SearchRequest("node-7", Dataset.ARCHIVE, 20));

        assertTrue(result.size() <= 20);
        assertTrue(result.stream().allMatch(
            e -> "node-7".equals(e.deviceId())));
    }
}
~~~

**Điều kiện tiên quyết:** Spring context phải có `MongoSearchFlowConfig`, `MongoSearchApi`, policy và MongoDB test đã seed dữ liệu. Test ở trên minh họa phương pháp; nó không tự tạo Testcontainers và chưa chứng minh routing nếu cả hai danh sách đều rỗng.

**Cần tăng độ mạnh assertion** trong bài thực hành: seed `live-101` và `arc-201` trong đúng collection, assert tập ID ở hai kết quả **khác nhau**, tránh test pass giả khi query trả list rỗng hoặc khi cấu hình nhầm collection.

### 16.2. Test inbound polling theo trạng thái

1. Seed một document NEW và một document DONE trong `telemetry_live`.
2. Khởi động inbound source với `MongoReadPlan.currentQuery()` trả NEW.
3. Lấy message ở test sink sau splitter, assert chỉ có NEW và header `MongoHeaders.COLLECTION_NAME`.
4. Chuyển trạng thái read plan qua API quản trị có kiểm soát sang RETRY, seed document RETRY.
5. Đợi poll tiếp theo và assert có document RETRY, không tự đổi collection hoặc tenant sai.
6. Dừng endpoint trước cleanup; dùng test DB để tránh ảnh hưởng dữ liệu khác.
7. Giải thích vì sao đọc lặp khi không claim/update là hành vi cần thiết kế idempotency.

### 16.3. Test writer collection expression

- Gửi event với header `approvedDataset=LIVE` được server cấp → kiểm tra document trong `telemetry_live`.
- Gửi event với `approvedDataset=ARCHIVE` → kiểm tra `telemetry_archive`.
- Thiếu header, hoặc giá trị `INTERNAL` → writer phải từ chối theo policy.
- Kiểm tra event chỉ xuất hiện ở collection được phép và không ở collection kia.
- Gửi cùng event ID hai lần, xác định `save` có thể overwrite; nếu cần insert-only, dùng handler/operation khác.

**Không dùng test với database production** và không “cleanup toàn collection” nếu đó là collection được chia sẻ.

## 17. Lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Expression không tìm thấy bean `@mongoReadPlan` | Không đăng ký bean hoặc context sai | Component scan/bean name/SpEL evaluation context |
| Inbound expression báo không có `payload` | Polling source không có input Message | Dùng provider bean/supplier |
| Query expression trả sai kiểu | String không phải Mongo query hoặc SpEL lỗi | Đánh giá type/value bằng unit test |
| Query trả dữ liệu không mong muốn | Thiếu tenant filter, status hoặc query không có limit | Inspect Query object, role và dữ liệu test |
| Không tìm thấy collection | Tên collection sai, database/template sai | Kiểm tra MongoOperations DB và collection |
| Chọn LIVE nhưng đọc ARCHIVE | Function/policy hoặc bean context lỗi | Seed ID khác nhau, assert per collection |
| Writer ghi nhầm collection | Header chưa được chuẩn hóa, policy thiếu | Validate header và audit routing |
| Không có message sau inbound poll | Query không khớp hoặc source chưa start | Probe DB, poller lifecycle, header |
| Dữ liệu NEW xuất hiện lặp lại | Poller chưa claim/update trạng thái | Idempotency/claim/lease/retry |
| Gateway timeout dù DB truy vấn thành công | Reply channel sai/caller hết thời hạn | Temporary reply channel, driver/query timeout |
| Nhiều request nhận nhầm reply | Chia sẻ QueueChannel không correlation | @MessagingGateway hoặc correlation router |
| Khi tăng tải, heap tăng | Query trả List lớn, thiếu limit | Limit/projection/page, DB index |
| XML không khởi động | Cùng khai báo query và query-expression | Chọn một option tương ứng |
| SpEL expression từ user bị lợi dụng | Cho phép raw expression động | Cấm expression không tin cậy, policy server-side |
| Tenant A nhìn thấy dữ liệu B | Query thiếu tenant scope hoặc role DB rộng | Kiểm thử authorization/criteria ở server |

Để chẩn đoán, đi theo chuỗi:

~~~text
Message / Poller
    -> Expression evaluation
    -> Query + collection selection
    -> MongoOperations/MongoTemplate
    -> MongoDatabaseFactory/connection
    -> MongoDB execution
    -> Message payload and headers
    -> Downstream business processing
~~~

Một lỗi query không khớp dữ liệu không tự sinh `ErrorMessage`; một exception khi poll/gateway/handler cũng có đường lỗi khác nhau tùy channel đồng bộ, bất đồng bộ và error handling.

## 18. Vòng đời và observability

- Inbound adapter bắt đầu polling theo lifecycle và lịch poller; đổi read plan được áp ở lần receive tiếp theo.
- Gateway chỉ chạy khi có request, không có poller riêng.
- Writer chỉ được gọi khi có message vào input channel, không quét collection.
- Nếu MongoDB tạm down, lỗi có thể xuất hiện khi operation chạy, không nhất thiết tại thời điểm tạo MongoTemplate.
- Khi shutdown, dừng producer/poller, drain các message đang xử lý theo contract; một queue trong RAM không tự bền.
- Khi rollout nhiều instance, một read plan trong memory không được đồng bộ giữa các process; tránh hai worker đọc/claim trùng nếu không có cơ chế phối hợp DB.

Metric gợi ý (cần tự instrument hoặc map theo framework):

| Metric | Ý nghĩa |
|---|---|
| `mongo_inbound_poll_total` | Số lượt poll |
| `mongo_inbound_empty_total` | Poll không có document |
| `mongo_query_expression_errors_total` | Lỗi build/evaluate query |
| `mongo_collection_route_errors_total` | Lỗi collection policy |
| `mongo_query_duration_seconds` | Thời gian DB query |
| `mongo_query_result_documents` | Số document trả về mỗi query |
| `mongo_gateway_requests_total` | Số request vào gateway |
| `mongo_gateway_reply_timeout_total` | Số request không có reply trong deadline |
| `mongo_writer_save_success_total` | Số thao tác writer thành công |
| `mongo_writer_save_error_total` | Lỗi ghi |
| `mongo_pending_work_depth` | Backlog/queue pending nếu có |

Không dùng label metric theo từng `eventId`, tên collection do người dùng tự cấp hoặc `tenantId` có cardinality vô hạn. Log nên ghi **collection đã nằm trong allowlist**, loại query, trạng thái, exception type và correlation ID được kiểm soát.

## 19. Bài thực hành tổng hợp

Thiết kế một ứng dụng **MongoDB → Spring Integration → MongoDB/HTTP** sử dụng query và collection động có kiểm soát.

### Phần A — Cơ sở expression

1. Seed dữ liệu cho `telemetry_live` và `telemetry_archive` trong MongoDB lab.
2. Dùng `query("{ 'status': 'NEW' }")` và `collectionName("telemetry_live")` ở outbound gateway; giải thích vì sao request payload không làm query thay đổi.
3. Dùng `queryExpression("@mongoQueryPolicy.forRequest(payload)")` trong một flow khác; xác định type trả về.
4. Trả lời vì sao `queryExpression("payload")` chỉ phù hợp khi payload đã là một Query hoặc query string hợp lệ.
5. Phân biệt `query`/`query-expression` với `collection-name`/`collection-name-expression`.

### Phần B — Inbound polling

1. Tạo `MongoReadPlan` trả Query với status và tenant cố định/được quản trị, limit 50.
2. Cấu hình `MongoDbMessageSource` với query expression gọi bean; gắn poller fixed delay 5 giây.
3. Dùng collection expression hoặc `collectionNameSupplier` chọn `telemetry_live`.
4. Sau lần poll, kiểm tra payload List trước splitter và `Message<TelemetryEvent>` sau splitter.
5. Cho status chuyển NEW → RETRY bằng API quản trị, quan sát query ở lần poll sau.
6. Thảo luận rủi ro đọc lại và claim/lease nếu chạy nhiều instance.

### Phần C — Gateway theo từng request

1. Định nghĩa `SearchRequest`, `Dataset` enum và `MongoQueryPolicy`.
2. Viết flow dùng `queryFunction` + `collectionNameFunction`, không có reply channel tĩnh.
3. Viết `MongoSearchApi` với `@MessagingGateway` và kiểm tra request/reply.
4. Seed IDs khác nhau cho LIVE/ARCHIVE; assert đúng collection và tenant.
5. Thử hai request đồng thời, giới hạn 20 kết quả và query thiếu dữ liệu.
6. Thử queryExpression và collectionNameExpression trên policy bean, so sánh mức dễ test.

### Phần D — Writer, lỗi và bảo mật

1. Viết `MongoDbStoringMessageHandler` với expression lựa chọn collection từ header đã kiểm tra.
2. Thử LIVE/ARCHIVE/giá trị lạ; xác nhận chỉ ghi vào collection hợp lệ.
3. Kiểm tra writer sử dụng `save`, không phải patch hoặc query theo request.
4. Thử MongoDB test instance down, quá timeout và query quá rộng; thiết kế retry/backoff.
5. Thiết kế test ngăn tenant A truy cập dữ liệu tenant B và ngăn client chèn raw SpEL/JSON query.
6. Đề xuất index, projection, paging và metric phục vụ production.

**Câu hỏi tự đánh giá:**

- Vì sao inbound `query-expression` không được đọc `payload` của request HTTP?
- `queryFunction` và `queryExpression` khác nhau thế nào về kiểu API và khả năng kiểm thử?
- `collection-name-expression` phải trả kiểu gì?
- Thay collection có đồng nghĩa đổi database không?
- Vì sao `maxMessagesPerPoll(1)` không giới hạn số document query trả?
- Vì sao một `Query` có limit và sort tốt hơn JSON query raw không kiểm soát?
- Vì sao cần tenant filter ở server ngay cả khi input DTO đã validate?
- Tại sao `collectionNameFunction` nên dùng enum/allowlist?
- Điều gì xảy ra nếu `MongoDbMessageSource` đọc cùng document NEW mỗi 5 giây?
- Với `findOne` không thấy document, vì sao không luôn có reply với payload null?
- Khi nào nên dùng `MongoDbStoringMessageHandler` và khi nào nên dùng `MongoDbOutboundGateway`?
- Làm sao test routing mà không bị false positive do hai danh sách đều rỗng?

## 20. Tài liệu tham khảo

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): query-expression, collection-name-expression, inbound polling, outbound gateway và storing adapter.
- [Spring Integration API — MongoDbMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/inbound/MongoDbMessageSource.html): đánh giá query expression mỗi `receive()`, kết quả List hoặc single.
- [Spring Integration API — MongoDbMessageSourceSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDbMessageSourceSpec.html): Java DSL source builder.
- [Spring Integration API — AbstractMongoDbMessageSourceSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/AbstractMongoDbMessageSourceSpec.html): collectionNameExpression, collectionNameSupplier, entityClass, update.
- [Spring Integration API — MongoDbOutboundGatewaySpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDbOutboundGatewaySpec.html): queryFunction, queryExpression, collectionNameFunction, collection callback.
- [Spring Integration API — MongoDbStoringMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/outbound/MongoDbStoringMessageHandler.html): collectionNameExpression và ghi payload.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): MongoOperations, Query, Criteria, Sort, mapping, index và transaction.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): request/reply, temporary reply channel, timeout.
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/): index, query performance và chọn dữ liệu.

## Kết luận

**Query expression** quyết định **đọc document nào**, còn **collection expression** quyết định **đọc/ghi vào collection nào**. Ở MongoDB inbound, expression được đánh giá khi **poller gọi `receive()`**, không có request payload; ở `MongoDbOutboundGateway`, expression/function có thể dùng `payload` và `headers` của **từng request**; ở outbound storing handler, expression chọn collection để **save payload**.

Trong **SPRING_INTEGRATION_ADAPTERS**, hãy ưu tiên **typed DTO, Spring Data Criteria, query limit, sort, index, collection allowlist và tenant scope được xác thực**. Không truyền biểu thức SpEL hoặc JSON query tự do từ nguồn ngoài, không đánh đồng collection với database, và không coi một query/save thành công là toàn bộ nghiệp vụ đã hoàn tất. **Kết nối đúng cần đi cùng hợp đồng message, idempotency, retry, bảo mật và quan sát được vận hành.**
