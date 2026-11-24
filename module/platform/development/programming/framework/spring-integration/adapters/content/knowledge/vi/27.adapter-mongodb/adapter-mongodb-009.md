# Reactive MongoDB adapter trong Spring Integration

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **MongoDB blocking** với **MongoDB reactive** ở driver, factory, `MongoOperations`/`ReactiveMongoOperations`, endpoint và cách thực thi.
- Hiểu `Publisher`, `Mono`, `Flux`, **subscription**, backpressure, cancellation và sự khác nhau giữa việc tạo publisher với việc thực sự gửi query/ghi MongoDB.
- Cấu hình `ReactiveMongoDbMessageSource` qua Java DSL `MongoDb.reactiveInboundChannelAdapter(...)`, poller, splitter và `FluxMessageChannel`.
- Giải thích tại sao **reactive inbound source trả `Message<Flux<T>>` hoặc `Message<Mono<T>>`**, không phải `Message<List<T>>` như blocking source.
- Cấu hình `ReactiveMongoDbStoringMessageHandler` qua `MongoDb.reactiveOutboundChannelAdapter(...)`; theo dõi kết quả `Mono<Void>` thay vì chỉ kiểm tra `send()==true`.
- Chọn `ReactiveMongoDatabaseFactory` hoặc `ReactiveMongoOperations`, cấu hình mapping, query, collection, filter tenant và limits.
- Phân biệt **reactive MongoDB polling** với **MongoDB change stream** và outbound request/reply gateway.
- Điều tiết số lượng document, concurrency, retry, timeout và xử lý lỗi trên reactive pipeline, không phá non-blocking bằng `block()`.
- Xây dựng kiểm thử với Reactor `StepVerifier` và MongoDB test instance, xử lý trường hợp publisher rỗng, lỗi kết nối và flow không subscribe.
- Thiết kế idempotency, ACK/commit, shutdown/restart và recovery khi MongoDB là một mắt xích giữa Kafka, JMS, AMQP, HTTP, UDP, file hoặc SFTP.

Bài thuộc chương **Adapter MongoDB** của module **SPRING_INTEGRATION_ADAPTERS**. Phạm vi module là kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`, thực hành trao đổi qua file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, đồng thời quan tâm hợp đồng message, lỗi và vòng đời kết nối. Trong bài này, trọng tâm là **reactive MongoDB I/O** trong các Spring Integration flows; non-blocking không tự tạo transaction hoặc exactly-once.

> Các API reactive MongoDB của Spring Integration xuất hiện từ phiên bản **5.3**. Ví dụ dùng Java 17+, Spring Boot 3.x và phiên bản Spring Integration/Spring Data tương thích. Riêng terminal operator `handleReactive(...)` có từ Spring Integration **6.1**. Khi áp dụng, hãy kiểm tra BOM/API đúng với phiên bản dự án.

## 1. Bài toán: nhận telemetry và lưu MongoDB không chặn I/O

Một service nhận event từ HTTP hoặc Kafka rồi cần lưu MongoDB:

~~~json
{
  "_id": "evt-1001",
  "tenantId": "tenant-a",
  "deviceId": "node-7",
  "sequence": 1001,
  "status": "NEW",
  "temperatureC": 26.5,
  "observedAt": "2026-11-23T02:00:00Z"
}
~~~

Đồng thời một worker định kỳ đọc các document `NEW` để chuyển sang hệ thống phân tích. Nếu mỗi request giữ một thread chờ MongoDB trả lời, tài nguyên có thể bị cạn khi tải tăng; reactive driver cho phép biểu diễn I/O bằng các publishers và tiêu thụ theo subscription.

~~~mermaid
flowchart LR
    A["HTTP / Kafka / AMQP"] --> M["MessageChannel"]
    M --> F["FluxMessageChannel"]
    F --> W["ReactiveMongoDbStoringMessageHandler"]
    W -->|"subscribe write Mono"| DB[("MongoDB")]
    P["Poller"] --> S["ReactiveMongoDbMessageSource"]
    S -->|"Message<Flux<T>>"| SP["Splitter"]
    SP --> C["FluxMessageChannel"]
    C --> H["Reactive handler"]
    DB -.->|"reactive query"| S
~~~

Cần phân biệt ba cột mốc:

1. **Spring Message được chấp nhận** ở channel.
2. **MongoDB publisher được subscribe và hoàn tất** theo kết quả driver.
3. **Nghiệp vụ được commit** và upstream được ACK theo hợp đồng riêng.

Điểm 1 không chứng minh điểm 2; điểm 2 cũng không chứng minh Kafka offset, JMS ACK, HTTP response hoặc trạng thái file/SFTP đã hoàn tất.

## 2. Mono, Flux, Publisher và Subscription

| Khái niệm | Ý nghĩa | Chú ý |
|---|---|---|
| `Publisher<T>` | Nguồn dữ liệu theo Reactive Streams | Không nhất thiết làm I/O trước khi subscribe |
| `Mono<T>` | Không hoặc một giá trị | `Mono.empty()` khác Message có payload null |
| `Flux<T>` | Không, một hoặc nhiều giá trị | Flux không phải List đã materialize |
| `Subscription` | Đăng ký, demand và cancellation | Subscriber quyết định khi nào stream bắt đầu |
| `onNext` | Một element được phát | Chưa chứng minh downstream commit |
| `onComplete` | Stream kết thúc bình thường | Với write Mono, là tín hiệu operation hoàn tất theo contract |
| `onError` | Stream thất bại | Có thể chỉ xuất hiện sau subscription |
| Backpressure | Demand của downstream | Không thay thế giới hạn query, pool hoặc concurrency |

### 2.1. Một MongoDB publisher thường là cold

~~~java
Flux<TelemetryEvent> pending =
    reactiveMongoOperations.find(
        Query.query(Criteria.where("status").is("NEW")),
        TelemetryEvent.class,
        "telemetry_events");
~~~

Tạo `pending` **không đủ để khẳng định database đã được query**. Một subscriber hoặc một reactive IntegrationFlow đã subscribe mới kích hoạt MongoDB operation.

~~~java
// Minh họa cách subscriber nhận tín hiệu;
// production nên để framework quản lý subscription.
pending.subscribe(
    record -> System.out.println(record.id()),
    error -> System.err.println(error.getMessage()));
~~~

**Không dùng `subscribe()` tùy tiện trong một business handler** nếu caller cần biết chính xác write succeeded/failed hoặc cần kiểm soát shutdown. Nên **trả publisher** để framework ghép vào pipeline và quản lý terminal signals.

### 2.2. Tạo Mono rồi bỏ đi không ghi dữ liệu

~~~java
// Sai: MongoDB save có thể chưa chạy vì Mono bị bỏ đi.
reactiveMongoOperations.save(event, "telemetry_events");

// Đúng trong một method trả Mono<Void>:
return reactiveMongoOperations
        .save(event, "telemetry_events")
        .then();
~~~

Không thêm `block()` chỉ để “chắc chắn chạy” trên WebFlux/event-loop. Hãy nối pipeline vào một subscriber thực và dùng `StepVerifier` trong test.

### 2.3. Non-blocking không phải tự động song song vô hạn

Reactive MongoDB giúp không chặn thread khi chờ socket, nhưng MongoDB server, client pool, network, throughput, data size và CPU vẫn hữu hạn. Nếu dùng `flatMap` tạo quá nhiều writes hoặc `onBackpressureBuffer` không giới hạn, ứng dụng vẫn có thể OOM hoặc quá tải database.

## 3. Các lớp và API: blocking vs reactive

| Vai trò | Blocking | Reactive |
|---|---|---|
| Java driver | `mongodb-driver-sync` | `mongodb-driver-reactivestreams` |
| Database factory | `MongoDatabaseFactory` | **`ReactiveMongoDatabaseFactory`** |
| Spring Data template | `MongoTemplate` | **`ReactiveMongoTemplate`** |
| Operations interface | `MongoOperations` | **`ReactiveMongoOperations`** |
| Query nhiều document | `List<T> find(...)` | **`Flux<T> find(...)`** |
| Query một document | `T findOne(...)` | **`Mono<T> findOne(...)`** |
| Save | Kết quả/exception từ synchronous call | **`Mono<T> save(...)`** |
| Spring Integration source | `MongoDbMessageSource` | **`ReactiveMongoDbMessageSource`** |
| Spring Integration writer | `MongoDbStoringMessageHandler` | **`ReactiveMongoDbStoringMessageHandler`** |
| Default inbound Message payload | `List<T>` | **`Flux<T>`** |
| Single-result inbound Message payload | `T` | **`Mono<T>`** |
| Reactive-aware MessageChannel | — | **`FluxMessageChannel`** |

Import cơ bản:

~~~java
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.integration.mongodb.inbound.ReactiveMongoDbMessageSource;
import org.springframework.integration.mongodb.outbound.ReactiveMongoDbStoringMessageHandler;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
~~~

`ReactiveMongoDatabaseFactory` có package `org.springframework.data.mongodb`; đừng nhầm với tên package của `ReactiveMongoTemplate`. **Reactive adapter không nhận blocking `MongoOperations`**.

## 4. Cài dependency và cấu hình kết nối

### 4.1. Maven — Spring Boot 3.x

~~~xml
<!-- Đặt trong <dependencies> của pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
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
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Trong ứng dụng **không dùng starter** cần có reactive MongoDB driver `org.mongodb:mongodb-driver-reactivestreams` và Spring Data MongoDB đã quản lý version tương thích. Không tự phối các major version driver/Integration/Data mà chưa kiểm tra BOM.

### 4.2. MongoDB lab

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/reactive_adapter_lab
~~~

URI local không có credentials **chỉ dành cho lab**. Production phải dùng secrets/TLS, role ít quyền nhất, pool/timeout phù hợp. Nếu đã dùng Boot auto-configuration tạo `ReactiveMongoOperations`, **inject bean có sẵn**; không tạo thêm mỗi request một MongoClient riêng.

### 4.3. Cấu hình thủ công — thay thế Spring Boot auto-config

~~~java
package example.reactivemongo;

import com.mongodb.reactivestreams.client.MongoClient;
import com.mongodb.reactivestreams.client.MongoClients;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.SimpleReactiveMongoDatabaseFactory;

@Configuration
public class ManualReactiveMongoConfiguration {

    @Bean(destroyMethod = "close")
    public MongoClient reactiveMongoClient() {
        return MongoClients.create(
                "mongodb://127.0.0.1:27017");
    }

    @Bean
    public ReactiveMongoDatabaseFactory reactiveMongoFactory(
            MongoClient reactiveMongoClient) {
        return new SimpleReactiveMongoDatabaseFactory(
                reactiveMongoClient, "reactive_adapter_lab");
    }

    @Bean
    public ReactiveMongoTemplate reactiveMongoTemplate(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTemplate(factory);
    }
}
~~~

Cách thủ công này **thay thế** Boot auto-config trong một lab/profile riêng. Không chạy cả hai cấu hình gây bean ambiguity; MongoClient là singleton được Spring quản lý/đóng trong shutdown. Collection nằm trong database đã được factory chọn; `collectionName("...")` **không đổi database**.

## 5. Hợp đồng entity và dữ liệu mẫu

~~~java
package example.reactivemongo;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "telemetry_events")
public record TelemetryEvent(
        @Id String id,
        String tenantId,
        String deviceId,
        long sequence,
        @Field(targetType = FieldType.DECIMAL128)
        BigDecimal temperatureC,
        String status,
        Instant observedAt) {
}
~~~

Trong mongosh trên database lab:

~~~javascript
use reactive_adapter_lab

db.telemetry_events.insertMany([
  {
    _id: "evt-1001",
    tenantId: "tenant-a",
    deviceId: "node-7",
    sequence: 1001,
    temperatureC: NumberDecimal("26.5"),
    status: "NEW",
    observedAt: ISODate("2026-11-23T02:00:00Z")
  },
  {
    _id: "evt-1002",
    tenantId: "tenant-a",
    deviceId: "node-8",
    sequence: 1002,
    temperatureC: NumberDecimal("25.8"),
    status: "NEW",
    observedAt: ISODate("2026-11-23T02:00:01Z")
  },
  {
    _id: "evt-1003",
    tenantId: "tenant-b",
    deviceId: "node-7",
    sequence: 1003,
    temperatureC: NumberDecimal("29.1"),
    status: "DONE",
    observedAt: ISODate("2026-11-23T02:00:02Z")
  }
])
~~~

Lần seed thứ hai với các `_id` cũ có thể tạo duplicate-key error. Không chạy trên production. Kiểm tra entity mapping của Decimal128, `Instant`, `@Id` và trường bắt buộc trên **MongoDB test thật**.

### 5.1. Validate trước khi ghi

~~~java
package example.reactivemongo;

public final class TelemetryValidator {

    public void validate(TelemetryEvent event) {
        if (event == null
                || event.id() == null || event.id().isBlank()
                || event.tenantId() == null
                || event.tenantId().isBlank()
                || event.deviceId() == null
                || event.deviceId().isBlank()
                || event.sequence() < 0
                || event.temperatureC() == null
                || event.observedAt() == null) {
            throw new IllegalArgumentException("Invalid telemetry");
        }
    }
}
~~~

Validation ở đây là synchronous và nhẹ, có thể dùng trước khi tạo `Mono`. Trong production còn cần contract schema/version, tenant authorization, giới hạn dữ liệu và event ID ổn định qua retry.

## 6. Reactive inbound source: Message chứa Publisher

Class chính:

~~~java
org.springframework.integration.mongodb.inbound.ReactiveMongoDbMessageSource
~~~

Nó là `MessageSource<Publisher<?>>`: **poller gọi `receive()`, nhưng query MongoDB được thực hiện khi publisher trong payload được subscribe**.

| Chế độ | API Spring Data | Message payload sau `receive()` |
|---|---|---|
| `expectSingleResult(false)` — mặc định | `ReactiveMongoOperations.find(...)` | **`Flux<TelemetryEvent>`** |
| `expectSingleResult(true)` | `ReactiveMongoOperations.findOne(...)` | **`Mono<TelemetryEvent>`** |

### 6.1. Một poll có thể tạo publisher trước khi có kết quả

~~~text
Poll #1
  -> source.receive()
  -> Message<Flux<TelemetryEvent>>
  -> split / FluxMessageChannel / subscriber
  -> ReactiveMongoOperations.find(query)
  -> onNext(evt-1001), onNext(evt-1002)
  -> onComplete
~~~

**Không ép `message.getPayload()` sang `List` hoặc `TelemetryEvent` ngay khi source trả message.** Khi query không có data, `Flux` có thể được tạo và **hoàn tất rỗng** sau subscription; khác với blocking source thường trả `null` khi find trả list rỗng.

Một `Mono<T>` không tìm thấy document cũng có thể `onComplete` không có `onNext`. Nó không biến thành Spring Message có payload `null`.

### 6.2. Header nguồn

Inbound source có thể gắn `MongoHeaders.COLLECTION_NAME` để thể hiện collection đã query. Đây là metadata của Spring Integration, không phải BSON field của mỗi document. Khi splitter tạo message con, hãy **kiểm thử header thực tế** nếu cần dùng cho routing/tracing.

## 7. Java DSL reactive inbound: poller + splitter + FluxMessageChannel

~~~java
package example.reactivemongo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;

@Configuration
@EnableIntegration
public class ReactiveMongoInboundConfig {

    @Bean
    public IntegrationFlow reactiveMongoInboundFlow(
            ReactiveMongoOperations mongo) {

        return IntegrationFlow.from(
                MongoDb.reactiveInboundChannelAdapter(
                        mongo,
                        "{ 'tenantId':'tenant-a', 'status':'NEW' }")
                    .collectionName("telemetry_events")
                    .entityClass(TelemetryEvent.class)
                    .expectSingleResult(false),
                e -> e.poller(
                    Pollers.fixedDelay(5000)
                           .maxMessagesPerPoll(1)))
            .split()
            .channel(c -> c.flux("reactiveMongoEvents"))
            .get();
    }
}
~~~

Giải thích:

1. `reactiveInboundChannelAdapter(...)` tạo reactive MongoDB message source.
2. Poller **vẫn cần thiết** để kích hoạt `receive()`: source này không tự là change stream.
3. `expectSingleResult(false)` tạo `Message<Flux<TelemetryEvent>>`.
4. `split()` xử lý Publisher và tạo các messages chứa từng `TelemetryEvent`.
5. `FluxMessageChannel` tham gia reactive composition và cho phép demand từ downstream.
6. **Cần consumer/subscriber** của `reactiveMongoEvents`; chỉ tạo channel không chứng minh DB query đã được subscribe.
7. `status=NEW` không bị đổi chỉ bằng find; các poll sau có thể **phát lại cùng document**.

### 7.1. Single result

~~~java
MongoDb.reactiveInboundChannelAdapter(
        mongo,
        "{ 'status':'NEW' }")
    .collectionName("telemetry_events")
    .entityClass(TelemetryEvent.class)
    .expectSingleResult(true);
~~~

Đây là một **builder thay thế**. Payload của source sẽ là `Mono<TelemetryEvent>`; có thể dùng splitter để unwrap tối đa một phần tử. `findOne` không tự chọn “cũ nhất” khi thiếu sort và không tạo atomic claim.

### 7.2. maxMessagesPerPoll khác query limit

~~~text
Pollers.fixedDelay(5000)
    -> khi nào poll task được kích hoạt

maxMessagesPerPoll(1)
    -> tối đa một lần gọi receive() trong một poll

Query.limit(50)
    -> tối đa 50 MongoDB documents trong query

FluxMessageChannel demand
    -> điều phối yêu cầu phát dữ liệu qua subscriber
~~~

Một `Message<Flux<T>>` có thể chứa publisher phát 50, 500 hoặc rất nhiều document sau subscription. Do đó phải kết hợp `Query.limit`, projection, index và bounded downstream capacity.

## 8. Downstream phải subscribe: terminal reactive handler

Từ Spring Integration **6.1**, có thể đặt `handleReactive(...)` ở cuối một flow:

~~~java
package example.reactivemongo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;

@Configuration
public class ReactiveMongoProcessConfig {

    @Bean
    public IntegrationFlow readAndProcess(
            ReactiveMongoOperations mongo,
            TelemetryReactiveProcessor processor) {

        return IntegrationFlow.from(
                MongoDb.reactiveInboundChannelAdapter(
                        mongo, "{ 'status':'NEW' }")
                    .collectionName("telemetry_events")
                    .entityClass(TelemetryEvent.class),
                e -> e.poller(
                    Pollers.fixedDelay(5000)
                           .maxMessagesPerPoll(1)))
            .split()
            .channel(c -> c.flux("reactiveProcessEvents"))
            .handleReactive(message ->
                processor.process(
                    (TelemetryEvent) message.getPayload()))
            .get();
    }
}
~~~

Processor ví dụ trả về `Mono<Void>`:

~~~java
package example.reactivemongo;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class TelemetryReactiveProcessor {

    public Mono<Void> process(TelemetryEvent event) {
        return Mono.fromRunnable(() ->
            System.out.println("Observed " + event.id()));
    }
}
~~~

**Đây là flow thay thế mục 7**, không bật cả hai poller cùng query NEW trong một lab nếu không chủ động nghiên cứu đọc trùng. `Mono.fromRunnable` chỉ cho biết đã in log khi publisher hoàn tất, **không phải** Kafka/DB/HTTP downstream commit. Thay bằng publisher của reactive client thực sự và quy định ACK theo contract.

Nếu phiên bản Spring Integration cũ hơn 6.1, sử dụng `ReactiveMessageHandler`/spec trong flow có `FluxMessageChannel` theo API tương ứng; đừng chuyển sang một `@ServiceActivator` blocking rồi mặc định rằng pipeline vẫn hoàn toàn backpressure-aware.

## 9. Lỗi fire-and-forget khi viết reactive handler

**Không nên:**

~~~java
public void handle(TelemetryEvent event) {
    reactiveMongoOperations.save(event).subscribe();
    // Method trả về trước khi biết save succeeded/failed.
}
~~~

Nó làm mất liên hệ giữa business ACK và MongoDB completion, khó hủy subscription lúc shutdown và có thể khiến mọi lỗi chỉ được log ở một nơi không mong muốn.

**Nên trả publisher:**

~~~java
public Mono<Void> handle(TelemetryEvent event) {
    return reactiveMongoOperations
            .save(event, "telemetry_events")
            .then();
}
~~~

Caller/framework phải compose hoặc subscribe `Mono` này. **Không dùng `block()` trên Reactor event-loop** để cố làm đồng bộ. Chỉ isolate một đoạn blocking legacy qua scheduler được kiểm soát nếu thực sự không có reactive API thay thế.
## 10. Reactive outbound channel adapter: MongoDB writer một chiều

Class chính:

~~~java
org.springframework.integration.mongodb.outbound.ReactiveMongoDbStoringMessageHandler
~~~

Nó là một `ReactiveMessageHandler`: khi được gọi với `Message<?>`, handler xây thao tác ghi và trả một **`Mono<Void>`**. Với `FluxMessageChannel`, Spring Integration có thể compose hoạt động đó vào `ReactiveStreamsConsumer` để subscriber chờ hoàn tất và xử lý `onError`.

DSL có hai lựa chọn:

~~~java
MongoDb.reactiveOutboundChannelAdapter(reactiveMongoOperations);

MongoDb.reactiveOutboundChannelAdapter(reactiveMongoDatabaseFactory);
~~~

Không sử dụng `MongoDb.outboundGateway(mongoOperations)` để thay writer reactive: đó là **blocking request/reply query gateway** khác contract.

### 10.1. Java DSL với FluxMessageChannel

~~~java
package example.reactivemongo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.MessageChannels;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;

@Configuration
@EnableIntegration
public class ReactiveMongoOutboundConfig {

    @Bean
    public IntegrationFlow reactiveMongoOutbound(
            ReactiveMongoOperations mongo) {

        return IntegrationFlow.from("toReactiveMongo")
                .channel(MessageChannels.flux())
                .handle(
                    MongoDb.reactiveOutboundChannelAdapter(mongo)
                        .collectionName("telemetry_events"))
                .get();
    }
}
~~~

- `toReactiveMongo` là input channel của flow (được DSL tạo nếu chưa có bean cùng tên).
- Channel reactive ở trước writer giúp framework compose `Mono<Void>`.
- Writer lưu **message payload**, không tự lưu tất cả Spring headers vào BSON.
- `collectionName("telemetry_events")` chọn collection tĩnh trong database của MongoOperations.
- Adapter **không phát reply saved document** như một outbound gateway.
- Phải có upstream producer phát `Message<TelemetryEvent>` đã validate tới `toReactiveMongo`.
- `MessageChannel.send()==true` có thể chỉ phản ánh message được chấp nhận ở tầng channel, **không chứng minh MongoDB write đã hoàn tất**.

### 10.2. Reactive handler trên DirectChannel sẽ khác gì?

Khi không có reactive stream composition (ví dụ đặt reactive handler vào flow imperative với DirectChannel), Spring Integration có thể dùng `ReactiveMessageHandlerAdapter` để **subscribe ngay** vào `Mono<Void>`.

Điều này giúp operation được thực hiện nhưng **không đem lại backpressure end-to-end** như một flow có `FluxMessageChannel`. Đồng thời caller của send vẫn không nên tự đồng nhất thành công khi dispatch với MongoDB commit; phải kiểm tra endpoint/caller contract của kiến trúc cụ thể.

### 10.3. Khởi tạo handler class trực tiếp

~~~java
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.mongodb.outbound.ReactiveMongoDbStoringMessageHandler;

ReactiveMongoDbStoringMessageHandler writer =
        new ReactiveMongoDbStoringMessageHandler(
                reactiveMongoOperations);

writer.setCollectionNameExpression(
        new LiteralExpression("telemetry_events"));
~~~

Đây là **fragment** để tạo handler, không phải IntegrationFlow đầy đủ. Phương án tạo bằng factory:

~~~java
ReactiveMongoDbStoringMessageHandler writer =
        new ReactiveMongoDbStoringMessageHandler(
                reactiveMongoDatabaseFactory);

writer.setMongoConverter(mongoConverter);
writer.setCollectionNameExpression(
        new LiteralExpression("telemetry_events"));
~~~

`setMongoConverter(...)` chỉ phù hợp theo API khi handler được tạo bằng **`ReactiveMongoDatabaseFactory`**; không dùng setter này để mong thay converter bên trong một `ReactiveMongoOperations` đã được dựng hoàn chỉnh.

## 11. MongoDB save không phải insert-only hoặc partial update

Reactive storing handler thực hiện ghi payload với semantics `save` của Spring Data MongoDB. Các lựa chọn nghiệp vụ khác cần handler/service khác.

| Phép toán | Ví dụ ReactiveMongoOperations | Đặc điểm |
|---|---|---|
| **save** | `save(entity, collection)` | Insert nếu chưa có hoặc ghi theo ID, có thể thay thế document |
| **insert** | `insert(entity, collection)` | Chỉ tạo mới; duplicate ID báo lỗi |
| **updateFirst** | `updateFirst(query, update, ...)` | Patch một số field khi query khớp |
| **upsert** | `upsert(query, update, ...)` | Update hoặc insert theo điều kiện |
| **findAndModify** | `findAndModify(query, update, ...)` | Atomic conditional update trên một document |
| **Outbound adapter** | `ReactiveMongoDbStoringMessageHandler` | Writer một chiều dùng save semantics |

### 11.1. Save cùng ID không đủ để tuyên bố exactly-once

Nếu event `evt-1001` được ghi rồi Kafka redelivery cùng ID:

- `save` có thể không tạo document thứ hai.
- Nhưng nó vẫn có thể ghi đè field thay đổi mới ở MongoDB.
- Nếu event phải bất biến, cân nhắc `insert` và unique key.
- Nếu cập nhật trạng thái PROCESSING → DONE, dùng update có điều kiện owner/version.
- Với `@Version`, tìm hiểu optimistic locking và mapping/version conflict của ReactiveMongoTemplate.

Lỗi timeout sau write có thể để lại **kết quả chưa biết**: server có thể đã nhận dù client nhận `onError`. Khi retry, giữ cùng business ID và reconcile trạng thái, không tự tạo event ID ngẫu nhiên mới.

### 11.2. Partial update reactive

Ví dụ service muốn cập nhật status chỉ khi document hiện tại thuộc `PROCESSING`:

~~~java
package example.reactivemongo;

import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public final class CompletionRepository {

    private final ReactiveMongoOperations mongo;

    public CompletionRepository(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }

    public Mono<Boolean> markDone(String id) {
        Query query = Query.query(
            Criteria.where("_id").is(id)
                .and("status").is("PROCESSING"));

        Update update = new Update().set("status", "DONE");

        return mongo.updateFirst(
                query, update, "telemetry_events")
            .map(result -> result.getMatchedCount() == 1);
    }
}
~~~

Cần bổ sung owner/version/lease trong hệ thống nhiều worker. `matchedCount==1` không chứng minh Kafka/HTTP business side effect đã thành công; đó chỉ là kết quả MongoDB operation.

## 12. Chọn collection động an toàn

Reactive writer cho phép `collectionNameFunction` đọc request Message:

~~~java
MongoDb.reactiveOutboundChannelAdapter(mongo)
    .collectionNameFunction(
        (org.springframework.messaging.Message<TelemetryEvent> message) ->
            collectionPolicy.allowedCollection(
                message.getHeaders()
                    .get("approvedDataset", String.class)));
~~~

`collectionPolicy` là bean được inject:

~~~java
package example.reactivemongo;

import org.springframework.stereotype.Component;

@Component
public class ReactiveMongoCollectionPolicy {

    public String allowedCollection(String approvedDataset) {
        if (approvedDataset == null) {
            throw new IllegalArgumentException(
                    "Missing collection category");
        }

        return switch (approvedDataset) {
            case "LIVE" -> "telemetry_events";
            case "ARCHIVE" -> "telemetry_archive";
            default -> throw new IllegalArgumentException(
                    "Unapproved MongoDB collection");
        };
    }
}
~~~

**Không để người dùng tự gửi tên collection thô hoặc SpEL expression.** `approvedDataset` phải do ứng dụng server-side gắn **sau khi xác thực quyền và loại message**, không chỉ copy header HTTP/Kafka/UDP chưa tin cậy.

Collection policy không tự thay đổi **MongoDB database**. Nếu cần database/cluster khác, dùng ReactiveMongoOperations/factory khác với credential và role được cấu hình riêng.

## 13. Query có giới hạn: Criteria, Sort, fields và limit

Reactive Streams giúp yêu cầu dữ liệu theo demand, nhưng một query không giới hạn vẫn có thể gây áp lực memory/network/server. Hãy giới hạn ở MongoDB.

~~~java
package example.reactivemongo;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class ReactiveTelemetryQueries {

    private ReactiveTelemetryQueries() {}

    public static Query newBatch(
            String authorizedTenant, int batchSize) {

        if (authorizedTenant == null
                || authorizedTenant.isBlank()
                || batchSize < 1 || batchSize > 100) {
            throw new IllegalArgumentException(
                    "Unauthorized tenant or invalid batch size");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(authorizedTenant)
                        .and("status").is("NEW"))
                .with(Sort.by(
                    Sort.Order.asc("observedAt"),
                    Sort.Order.asc("_id")))
                .limit(batchSize);

        query.fields()
            .include("_id")
            .include("tenantId")
            .include("deviceId")
            .include("sequence")
            .include("temperatureC")
            .include("status")
            .include("observedAt");

        return query;
    }
}
~~~

Trong ví dụ lab:

~~~java
MongoDb.reactiveInboundChannelAdapter(
        reactiveMongoOperations,
        ReactiveTelemetryQueries.newBatch("tenant-a", 50))
    .collectionName("telemetry_events")
    .entityClass(TelemetryEvent.class)
    .expectSingleResult(false);
~~~

Đây là **builder**, không phải flow được đăng ký nếu chưa nối vào `IntegrationFlow.from(...)` và poller. Cả overload `ReactiveMongoOperations, Query` và `ReactiveMongoDatabaseFactory, Query` đều được Spring Integration DSL cung cấp trong các phiên bản phù hợp.

### 13.1. Limit khác demand và maxMessagesPerPoll

| Giới hạn | Tầng | Ý nghĩa |
|---|---|---|
| `maxMessagesPerPoll(1)` | Poller | Số lần `receive()` trong một poll task |
| `Query.limit(50)` | MongoDB | Số document trong một query |
| `request(n)` | Reactive Streams | Nhu cầu downstream với publisher |
| `flatMap(..., 8)` | Reactor operator | Tối đa 8 inner subscriptions in-flight ở operator này |
| `QueueChannel(64)` | Message channel | Capacity số messages trong queue |
| `maxFetchSize` | Remote file adapter | Số file remote fetch, không phải số MongoDB documents |

Một `Message<Flux<T>>` có thể phát nhiều document; `maxMessagesPerPoll(1)` **không đồng nghĩa một document**.

### 13.2. Projection và partial entity

Nếu chỉ query vài field, một `TelemetryEvent` được map có thể bị thiếu `temperatureC`, `status` hoặc `observedAt`, tạo null/default. Không dùng entity projection thiếu field để `save` lại nguyên document: có thể gây mất dữ liệu.

Chọn DTO projection có đúng fields hoặc giữ đủ field khi cần business update. `_id` mặc định được trả về ở MongoDB projection trừ khi loại trừ tường minh; giữ ID khi cần dedup/ACK.

### 13.3. Index theo filter và sort

Trong mongosh trên database test:

~~~javascript
db.telemetry_events.createIndex({
  tenantId: 1,
  status: 1,
  observedAt: 1,
  _id: 1
})
~~~

Index có thể hỗ trợ filter + sort. Đo bằng `explain("executionStats")` trên dữ liệu đủ lớn, so sánh examined keys/docs và latency, không tự khẳng định mọi query dùng index tốt chỉ vì đã tạo.

## 14. Query/collection expression ở reactive inbound

Có thể khởi tạo source bằng một `Expression`:

~~~java
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.mongodb.inbound.ReactiveMongoDbMessageSource;

ReactiveMongoDbMessageSource source =
    new ReactiveMongoDbMessageSource(
        reactiveMongoOperations,
        new SpelExpressionParser().parseExpression(
            "@mongoReadPolicy.nextQuery()"));
~~~

`mongoReadPolicy` là Spring bean trả một `Query` mới hợp lệ trong mỗi lần receive. Source phải được Spring quản lý để SpEL có thể phân giải bean reference. **Inbound polling không có request Message đầu vào**, nên không dùng `payload.deviceId` như với outbound gateway.

Source spec cũng hỗ trợ collection supplier:

~~~java
MongoDb.reactiveInboundChannelAdapter(
        reactiveMongoOperations,
        "{ 'status':'NEW' }")
    .collectionNameSupplier(
        () -> trustedPolicy.currentCollection())
    .entityClass(TelemetryEvent.class);
~~~

`trustedPolicy` là bean được inject, lựa chọn collection có allowlist. Nếu query và collection thay đổi độc lập giữa hai threads, có nguy cơ dùng **query của policy mới** với **collection của policy cũ**; nên quản lý một immutable policy snapshot hoặc serialize thay đổi tại lifecycle boundary.

**Expression được đánh giá khi source receive**, nhưng MongoDB reactive operation chạy sau subscription. Đừng mặc định kết quả phản ánh chính xác trạng thái query/collection tại lúc subscriber nhận data nếu policy được phép đổi trong khi operation đang pending; hãy test theo đúng API và contract bạn sử dụng.

## 15. updateExpression và việc poll lại tài liệu

Từ Spring Integration **5.5**, reactive source hỗ trợ `updateExpression`:

~~~java
import org.springframework.data.mongodb.core.query.Update;

MongoDb.reactiveInboundChannelAdapter(
        reactiveMongoOperations,
        "{ 'status':'NEW' }")
    .collectionName("telemetry_events")
    .entityClass(TelemetryEvent.class)
    .update(new Update().set("status", "CLAIMED"));
~~~

Đoạn này **chỉ là builder minh họa**. Source có thể cập nhật document đã lấy để không còn khớp query NEW ở lượt poll sau. Nhưng:

- **CLAIMED không chứng minh downstream đã xử lý xong.**
- Nếu app crash sau update, trước Kafka/HTTP/JMS completion, document có thể kẹt.
- Nhiều instance cùng query NEW trước update có thể xử lý trùng.
- Query/find và update không tự tạo atomic claim giữa các instance.
- Nếu update không làm thay đổi field lọc, poll sau có thể phát lại như cũ.
- Cần business event ID bền, lease/owner, recovery, retry và idempotent downstream.

Với work queue quan trọng, cân nhắc một **custom reactive MessageSource** dùng `ReactiveMongoOperations.findAndModify(...)` có điều kiện trên document để claim nguyên tử. Cần thiết kế cách release/extend lease, fencing owner/version và chỉ chuyển DONE sau business commit.

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant DB as MongoDB
    A->>DB: find(status=NEW)
    B->>DB: find(status=NEW)
    DB-->>A: evt-1001
    DB-->>B: evt-1001
    Note over A,B: Hai bên đều có thể xử lý cùng event
~~~

Một reactive publisher không tự cung cấp exactly-once. Đây là vấn đề **giao hàng và trạng thái nghiệp vụ**, không phải vấn đề blocking/non-blocking.

## 16. Backpressure, concurrency và thứ tự

### 16.1. Bounded concurrency với flatMap

Trong một Reactor service được caller subscribe:

~~~java
public Flux<TelemetryEvent> saveBatch(
        Flux<TelemetryEvent> events,
        ReactiveMongoOperations mongo) {

    return events.flatMap(
        e -> mongo.save(e, "telemetry_events"),
        8);
}
~~~

Operator này có tối đa 8 inner publishers in-flight, nhưng **không bảo đảm thứ tự kết quả bằng thứ tự input**. Nếu ứng dụng đòi hỏi thứ tự tuyệt đối:

~~~java
return events.concatMap(
    e -> mongo.save(e, "telemetry_events"));
~~~

`concatMap` tuần tự, có thể giảm throughput. Nếu chỉ yêu cầu thứ tự theo `deviceId`, thiết kế partition/key routing phù hợp thay vì xếp toàn bộ sự kiện vào một hàng.

### 16.2. Backpressure không thay thế giới hạn query

- `FluxMessageChannel` giúp phối hợp demand với subscriber.
- `Query.limit` kiểm soát bao nhiêu document được yêu cầu từ MongoDB.
- `flatMap(concurrency)` giới hạn I/O đồng thời ở **stage đó**, không phải toàn hệ thống.
- Kích thước queues, prefetch, buffers và thread schedulers còn ảnh hưởng memory.
- Khi có một handler blocking/eager `subscribe()` trong flow, backpressure end-to-end có thể bị phá.

Không dùng `onBackpressureDrop`/`onErrorContinue` tùy tiện với dữ liệu đơn hàng hoặc thanh toán; mất message có thể là hành vi không chấp nhận được.

### 16.3. Không gọi block() trên event-loop

Nếu bước tiếp theo dùng JDBC/SDK blocking, hãy chuyển riêng bước đó sang một scheduler có capacity phù hợp (ví dụ boundedElastic). Nhưng ưu tiên reactive client thật; không bọc blocking API trong Reactor rồi cho rằng tự động đạt lợi ích non-blocking.

## 17. Xử lý lỗi trong Reactor: onError xảy ra sau subscription

Code tạo Mono thường không bắt được lỗi network của MongoDB bằng một `try/catch` bao ngoài:

~~~java
try {
    Mono<TelemetryEvent> pending =
        reactiveMongoOperations.save(
            event, "telemetry_events");
    // Không có subscriber nên DB chưa phát onError ở đây.
} catch (Exception ex) {
    // Không phải nơi phù hợp để bắt lỗi I/O bất đồng bộ.
}
~~~

Chính sách tốt hơn là compose publisher:

~~~java
public Mono<Void> saveWithLogging(
        TelemetryEvent event,
        ReactiveMongoOperations mongo) {

    return mongo.save(event, "telemetry_events")
        .doOnSuccess(saved ->
            System.out.println("Saved id=" + saved.id()))
        .doOnError(ex ->
            System.err.println(
                "MongoDB error: "
                + ex.getClass().getSimpleName()))
        .then();
}
~~~

Đây chỉ là logging; `onError` vẫn được propagate. Không tự coi logging thành retry hay dead-letter.

### 17.1. Retry có giới hạn và phân loại lỗi

~~~java
import java.time.Duration;
import org.springframework.dao.TransientDataAccessException;
import reactor.util.retry.Retry;

public Mono<Void> saveWithRetry(
        TelemetryEvent event,
        ReactiveMongoOperations mongo) {

    return mongo.save(event, "telemetry_events")
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .filter(ex ->
                    ex instanceof TransientDataAccessException))
        .then();
}
~~~

**Đây là predicate minh họa**, không bao quát tất cả lỗi driver/write concern. Không retry mapping error, validation error hoặc auth failure vô hạn. Với timeout không chắc MongoDB đã ghi, retry cần ID ổn định, duplicate handling và reconciliation.

### 17.2. Không che onError bằng Mono.empty()

~~~java
// Nguy hiểm nếu upstream ACK dựa trên onComplete:
return mongo.save(event)
    .onErrorResume(e -> Mono.empty())
    .then();
~~~

Nếu MongoDB down, đoạn này có thể biến lỗi thành success signal làm upstream commit sớm và mất event. Nếu muốn fallback, trước hết phải ghi bền vào retry queue/dead-letter/outbox hoặc có hợp đồng chấp nhận mất dữ liệu minh bạch.

### 17.3. errorChannel và Reactive Streams onError

- Trong flow imperative, exception thường đi qua caller hoặc error channel theo endpoint.
- Trong flow reactive, lỗi có thể phát ở **onError của subscriber** sau khi Message đã được dispatch.
- Cần biết nơi nào sở hữu subscription, advice và error policy; **không tự mặc định mọi onError thành một ErrorMessage**.
- MongoDB `Flux.empty()` là **không có document**, còn `Flux.error(...)` là **lỗi**, cần metric/response khác nhau.
- Một source query thành công nhưng downstream Kafka lỗi vẫn là lỗi sau query; không được ghi là MongoDB read failure.
## 18. Timeout, cancellation và lifecycle

### 18.1. Các loại timeout không giống nhau

| Tầng | Ví dụ | Nó kiểm soát gì? |
|---|---|---|
| Poller | `Pollers.fixedDelay(5000)` | Khi nào `receive()` được gọi |
| MongoDB driver | Server selection/socket timeout | Khi client chờ MongoDB server/I/O |
| MongoDB query | Query max time/read preference | Thời gian truy vấn và server selection policy |
| Reactor | `Mono.timeout(Duration)` | Timeout tại publisher |
| HTTP/request caller | API/gateway response timeout | Khi client ngừng chờ response |
| Graceful shutdown | Application stop deadline | Thời gian hoàn tất in-flight work |

**Reactor timeout/cancellation không chứng minh MongoDB chưa ghi.** Server có thể đã commit trước khi response bị thất lạc, hoặc còn đang xử lý operation. Khi chưa biết kết quả write, dùng event ID ổn định và reconciliation thay vì tự sinh ID mới.

### 18.2. Vòng đời reactive inbound

~~~text
ApplicationContext start
  -> SourcePollingChannelAdapter start
  -> Poller phát trigger
  -> ReactiveMongoDbMessageSource.receive()
  -> Message<Publisher<?>> được tạo
  -> Splitter / FluxMessageChannel / downstream subscribe
  -> MongoDB query thực thi
  -> onNext / onComplete hoặc onError
  -> Poll lần tiếp theo
~~~

Điểm quan trọng:

- Source là **polling source**, không tự nhận MongoDB push events.
- Nếu không có subscriber downstream, publisher có thể không được consume.
- Khi stop, cần hủy/dừng poller và các subscriptions theo lifecycle.
- Khi restart, query vẫn có thể gặp lại cùng các `NEW` documents vì **không có checkpoint tự động**.
- `FluxMessageChannel` không phải durable queue; nếu process chết, message pending trong RAM có thể mất.
- Với source query status NEW nhiều instances, cần claim/lease hoặc idempotent downstream.

### 18.3. Shutdown cho reactive outbound

Để tránh gửi ACK upstream quá sớm:

1. Ngừng nhận message mới từ HTTP/Kafka/JMS/AMQP.
2. Chờ các reactive write `Mono<Void>` đang in-flight đến terminal signal theo deadline.
3. Ghi bền message chưa hoàn thành vào broker/outbox hoặc giữ state cho retry sau restart.
4. Không tạo `subscribe()` riêng trong handler khiến framework khó theo dõi.
5. Đóng MongoDB client do Spring quản lý.
6. Sau restart, dùng ID/lease/checkpoint đúng hợp đồng để tiếp tục xử lý.

Đừng coi `cancel()` là rollback business transaction; đó là cancellation signal của subscription.

## 19. Reactive MongoDB transaction

Spring Data cung cấp `ReactiveMongoTransactionManager` cho MongoDB transactions khi deployment hỗ trợ (thường cần replica set hoặc sharded cluster thích hợp).

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Bean
public ReactiveMongoTransactionManager reactiveMongoTransactionManager(
        ReactiveMongoDatabaseFactory factory) {
    return new ReactiveMongoTransactionManager(factory);
}

@Bean
public TransactionalOperator reactiveMongoTxOperator(
        ReactiveMongoTransactionManager txManager) {
    return TransactionalOperator.create(txManager);
}
~~~

Đây là **fragment của class `@Configuration`**. Factory/transaction manager và operations phải nằm trong cùng cấu hình transaction; một manager cho cluster A không tự quản lý operation ở cluster B.

### 19.1. TransactionalOperator trong pipeline

Ví dụ hai thao tác MongoDB trong cùng database/transaction:

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public Mono<Void> saveAndAcknowledgeInbox(
        TelemetryEvent event,
        ReactiveMongoOperations mongo,
        TransactionalOperator tx) {

    Mono<Void> work = mongo
        .save(event, "telemetry_events")
        .then(mongo.updateFirst(
            Query.query(
                Criteria.where("_id").is(event.id())
                    .and("status").is("PROCESSING")),
            new Update().set("status", "DONE"),
            "inbox_events"))
        .flatMap(update -> {
            if (update.getMatchedCount() != 1) {
                return Mono.error(new IllegalStateException(
                    "Inbox state no longer PROCESSING"));
            }
            return Mono.empty();
        });

    return work.as(tx::transactional);
}
~~~

**Giới hạn ví dụ:** chưa có claim owner/version/lease. Nó minh họa reactive transaction composition, không phải implementation work queue đầy đủ. Phải dùng MongoDB topology thực sự hỗ trợ transaction và kiểm thử failure. Lệnh MongoDB trong transaction không tự bao trùm Kafka consumer offset, HTTP response, JMS ACK hoặc file rename.

### 19.2. Vì sao outbox/idempotency vẫn cần?

Nếu MongoDB transaction commit thành công, nhưng process crash trước khi ACK Kafka, Kafka có thể redeliver cùng event. Nếu downstream đã nhận HTTP/Kafka publish nhưng response thất lạc, retry cũng có thể tạo duplicate. Giải pháp thường gồm **durable inbox/outbox, unique business key, retry có giới hạn, state reconciliation và idempotent consumer**.

Reactive và blocking API không làm biến mất bài toán distributed transaction.

## 20. Reactive inbound polling, change stream và request/reply

| Tiêu chí | Reactive MongoDB polling | MongoDB change stream | MongoDB outbound gateway |
|---|---|---|---|
| Endpoint | `ReactiveMongoDbMessageSource` | `MongoDbChangeStreamMessageProducer` | `MongoDbOutboundGateway` |
| Kích hoạt | **Poller** | MongoDB change stream subscription | Request Message |
| Dữ liệu | Flux/Mono của query kết quả | ChangeStreamEvent/body theo config | Reply query |
| Java DSL | `reactiveInboundChannelAdapter` | `changeStreamInboundChannelAdapter` | `outboundGateway` |
| Có poller? | **Có** | Không giống query polling | Không |
| Khi nào dùng? | Quét backlog/NEW theo lịch | CDC/near-real-time changes | Tra cứu theo từng request |
| Phục hồi | Status/claim/lease/idempotency | Resume token/resubscribe | Timeout/retry của caller |
| Driver | Reactive | Reactive | API hiện có thường blocking |

### 20.1. Change stream là endpoint riêng

Ví dụ Java DSL:

~~~java
@Bean
public IntegrationFlow reactiveChangeStreamFlow(
        ReactiveMongoOperations mongo) {

    return IntegrationFlow.from(
            MongoDb.changeStreamInboundChannelAdapter(mongo)
                .collection("telemetry_events")
                .domainType(TelemetryEvent.class))
        .channel(c -> c.flux("mongoChanges"))
        .get();
}
~~~

Đây là flow **khác** reactive polling, không phải chỉ đổi query của `ReactiveMongoDbMessageSource`. MongoDB change stream yêu cầu deployment, role và khả năng hỗ trợ tương ứng; payload mặc định có thể chứa `ChangeStreamEvent<T>` thay vì `T`. Cần thiết kế resume token, reconnect và checkpoint theo API thực tế, không tự suy ra channel là durable.

### 20.2. Có reactiveOutboundGateway hay không?

Spring Integration có `MongoDbOutboundGateway` cho MongoDB **request/reply query** theo API blocking `MongoOperations`. Các factory MongoDB reactive trong Java DSL gồm `reactiveInboundChannelAdapter` và `reactiveOutboundChannelAdapter`; **không mặc định có factory `MongoDb.reactiveOutboundGateway(...)`** nếu API của version bạn dùng không công bố.

Nếu WebFlux cần trả `Mono<T>`/`Flux<T>` theo request, có thể tạo **reactive Spring Data service** và compose publisher vào response. Không nên bịa một method DSL không tồn tại.

~~~java
package example.reactivemongo;

import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class ReactiveTelemetryLookup {

    private final ReactiveMongoOperations mongo;

    public ReactiveTelemetryLookup(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }

    public Flux<TelemetryEvent> findNew(
            String authorizedTenant, String deviceId) {

        Query query = Query.query(
                Criteria.where("tenantId").is(authorizedTenant)
                    .and("deviceId").is(deviceId)
                    .and("status").is("NEW"))
                .limit(50);

        return mongo.find(
                query, TelemetryEvent.class, "telemetry_events");
    }
}
~~~

Đây là reactive service Spring Data **không phải** Spring Integration outbound gateway. Nếu ứng dụng cần EIP routing, correlation và request/reply thực sự, phải thiết kế message gateway/custom endpoint có reactive completion được theo dõi đúng cách.

## 21. Kiểm thử với StepVerifier và MongoDB test instance

**`StepVerifier` xác minh tín hiệu của publisher**: `onNext`, `onComplete`, `onError`, cancel, data/order. Nó giúp phân biệt “có một publisher” với “publisher đã chạy và phát dữ liệu đúng”.

### 21.1. Integration test cho ReactiveMongoOperations

Dùng Testcontainers khi runner có Docker hoặc MongoDB test riêng. Ví dụ Spring Boot Test trong class dùng một database test, không bao giờ dùng production:

~~~java
package example.reactivemongo;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest
class ReactiveMongoOperationsIT {

    @Autowired
    ReactiveMongoOperations mongo;

    @Test
    void savesThenReadsAndCleansUp() {
        String id = "it-" + UUID.randomUUID();

        TelemetryEvent event = new TelemetryEvent(
                id, "tenant-test", "node-test", 1L,
                new BigDecimal("26.5"), "NEW",
                Instant.parse("2026-11-23T02:00:00Z"));

        Query byId = Query.query(Criteria.where("_id").is(id));

        Mono<TelemetryEvent> exercise =
            mongo.save(event, "telemetry_events")
                .then(mongo.findById(
                    id, TelemetryEvent.class, "telemetry_events"))
                .flatMap(readBack ->
                    mongo.remove(byId, "telemetry_events")
                        .thenReturn(readBack));

        StepVerifier.create(exercise)
            .expectNextMatches(readBack ->
                id.equals(readBack.id())
                    && "tenant-test".equals(readBack.tenantId())
                    && readBack.sequence() == 1L)
            .verifyComplete();
    }
}
~~~

Bài test đảm bảo save/đọc/delete trong một **reactive chain đã được subscribe**. Nếu `save` hoặc `findById` lỗi trước bước cleanup, `flatMap` không thực hiện remove; test nâng cao nên dùng `Mono.usingWhen` hoặc test teardown độc lập để cleanup cả đường lỗi. Nó **chưa kiểm tra Spring Integration flow**.

### 21.2. Test reactive source trả Message có Publisher

Trong một test có MongoDB data đã seed, tạo source độc lập **không có background poller**:

~~~java
import org.reactivestreams.Publisher;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.mongodb.inbound.ReactiveMongoDbMessageSource;
import org.springframework.messaging.Message;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

ReactiveMongoDbMessageSource source =
    new ReactiveMongoDbMessageSource(
        mongo,
        new LiteralExpression("{ '_id': 'evt-1001' }"));

source.setCollectionNameExpression(
    new LiteralExpression("telemetry_events"));
source.setEntityClass(TelemetryEvent.class);
source.setExpectSingleResult(false);
source.afterPropertiesSet();

Message<Publisher<?>> msg = source.receive();
assertNotNull(msg);
assertInstanceOf(Publisher.class, msg.getPayload());

StepVerifier.create(Flux.from(msg.getPayload()))
    .expectNextMatches(value ->
        value instanceof TelemetryEvent event
            && "evt-1001".equals(event.id()))
    .verifyComplete();
~~~

Đây là **fragment** trong một JUnit class có `@Autowired ReactiveMongoOperations mongo` và test data; không phải file test Java độc lập. Nó xác minh **kết quả sau subscribe**, không chỉ `receive()!=null`.

### 21.3. Test single-result, empty và error

Tạo source riêng `setExpectSingleResult(true)`:

- Khi document tồn tại, `Message<Mono<TelemetryEvent>>` và subscriber nhận một event.
- Khi không tồn tại, `Mono.empty()` hoàn tất không có `onNext`.
- Khi MongoDB down hoặc thiếu quyền, publisher phát `onError`; không đánh đồng với empty publisher.
- Khi query dạng Flux có ba document, `StepVerifier` nên assert đủ ba IDs/tenant, không chỉ kiểm tra `thenConsumeWhile` vì một Flux rỗng cũng có thể PASS.

Nếu test với `@beanName` trong SpEL, cần Spring BeanFactory/EvaluationContext hợp lệ; dùng `LiteralExpression` khi chỉ muốn test source behavior.

### 21.4. Test trực tiếp reactive storing handler

Có thể thử handler bên ngoài IntegrationFlow để chứng minh `Mono<Void>` được subscribe:

~~~java
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.mongodb.outbound.ReactiveMongoDbStoringMessageHandler;
import org.springframework.messaging.support.MessageBuilder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

ReactiveMongoDbStoringMessageHandler handler =
    new ReactiveMongoDbStoringMessageHandler(mongo);

handler.setCollectionNameExpression(
    new LiteralExpression("telemetry_events"));
handler.afterPropertiesSet();

Mono<Void> write = handler.handleMessage(
    MessageBuilder.withPayload(event).build());

StepVerifier.create(write).verifyComplete();

StepVerifier.create(
        mongo.findById(
            event.id(), TelemetryEvent.class, "telemetry_events"))
    .expectNextMatches(saved ->
        event.id().equals(saved.id()))
    .verifyComplete();
~~~

Đây là test fragment với `mongo` và `event` được tạo từ test fixture và có cơ chế cleanup. Dùng đúng API của `ReactiveMessageHandler` trong version dự án. **Một test trực tiếp handler không thay thế test wiring FluxMessageChannel và consumer lifecycle**.

### 21.5. Ma trận test end-to-end

| Test case | Điều cần khẳng định |
|---|---|
| Mono được tạo nhưng chưa subscribe | Không tuyên bố DB đã ghi |
| Flux source có hai matches | Sau subscribe phát đúng hai events |
| Flux source rỗng | `onComplete` không có `onNext` |
| Mono single không có data | `Mono.empty()` |
| MongoDB tạm down | `onError` rõ ràng, retry/error policy đúng |
| Header collection không hợp lệ | Policy từ chối trước khi ghi |
| Query.limit(20) | Không quá 20 document |
| Projection thiếu field | Không vô tình save partial entity |
| FluxMessageChannel | Consumer thực sự subscribe |
| Chậm/đầy pool | Bounded concurrency và timeout |
| Hai poller cùng NEW | Phát hiện duplicate/claim race |
| Retry cùng event ID | Không tự tạo ID mới cho mỗi attempt |
| Save thay đổi field | Hiểu replacement vs patch |
| Stop/restart | Có cách phục hồi in-flight/pending |
| Business ACK | Chỉ phát khi điều kiện commit được đáp ứng |

**Không chỉ assert `MessageChannel.send()==true`** rồi kết luận MongoDB đã commit. Cần kiểm tra terminal signal của write hoặc readback MongoDB có bounded waiting, và tách ACK nghiệp vụ khỏi DB ACK.

## 22. Quan sát, bảo mật và vận hành

### 22.1. Metrics gợi ý

| Metric | Phân biệt điều gì? |
|---|---|
| `reactive_mongo_polls_total` | Lượt gọi source receive |
| `reactive_mongo_publisher_created_total` | Số publishers được tạo |
| `reactive_mongo_publisher_subscribed_total` | Publisher thực sự được subscribe |
| `reactive_mongo_documents_emitted_total` | Số document phát sau query |
| `reactive_mongo_query_empty_total` | Query không có kết quả |
| `reactive_mongo_write_attempt_total` | Write operation bắt đầu |
| `reactive_mongo_write_success_total` | Write `onComplete` |
| `reactive_mongo_write_error_total` | Write `onError` |
| `reactive_mongo_inflight_operations` | Operation đang chờ terminal signal |
| `reactive_mongo_operation_latency_seconds` | Latency end-to-end |
| `reactive_mongo_retry_total` | Retry count |
| `reactive_mongo_cancel_total` | Cancellation |
| `reactive_mongo_pending_depth` | Backlog nếu có |
| `reactive_mongo_business_committed_total` | Event nghiệp vụ đã hoàn tất |

Đây là **tên metric minh họa**, không mặc định framework xuất cùng tên. Đừng đưa `eventId`, deviceId, MongoDB URI, tên collection động vô hạn hay token vào metric labels.

### 22.2. Phân biệt log theo giai đoạn

~~~text
event_received
publisher_created
publisher_subscribed
mongo_write_started
mongo_write_completed
mongo_write_failed
business_committed
~~~

Nếu chuyển scheduler/thread, logging MDC/ThreadLocal không mặc nhiên được truyền nguyên vẹn. Cần dùng Reactor context hoặc context propagation đã được cấu hình và test, với correlation/business ID bền qua retry.

### 22.3. Bảo mật

- Dùng tài khoản MongoDB có **least privilege**, không cấp admin cho adapter.
- Bảo vệ secrets/TLS và network access; không log credentials.
- Giới hạn query bằng tenant filter server-side, `limit`, sort và index phù hợp.
- Dùng collection allowlist, không cho header/raw SpEL do client quyết định.
- Validate bytes/JSON, schema/version/ID và kích thước payload trước MongoDB writer.
- Không log toàn bộ document nhạy cảm; dùng error class, operation type và correlation.
- Cấu hình backpressure, queue capacity, concurrency và retry budget để ngăn resource exhaustion.
- Thiết kế retention/index/backup và recovery tương ứng business SLA.
- Nếu reactive flow có blocking SDK khác, tránh chạy trực tiếp trên event-loop.

## 23. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
|---|---|---|
| Source tạo Message nhưng không thấy data | Không có subscriber đến Flux payload | Splitter, FluxMessageChannel và downstream consumer |
| Ép message payload sang List | Nhầm blocking/reactive source | Dùng Publisher/Flux/Mono |
| Write không chạy | Mono được tạo rồi bỏ đi | Compose/subscribe do framework quản lý |
| `send()==true` nhưng DB chưa có doc | Send chỉ xác nhận channel dispatch | Theo dõi write terminal signal/readback |
| MongoTemplate bị inject vào reactive builder | Nhầm API blocking | Dùng ReactiveMongoOperations/factory |
| `block()` gây nghẽn | Chặn Reactor event-loop | Reactive API hoặc isolate blocking |
| Flux đọc rất nhiều documents | Thiếu Query.limit/projection | Giới hạn query, batch và demand |
| FlatMap viết không theo thứ tự | Concurrent inner publishers | concatMap hoặc keyed sequencing |
| onError bị che | onErrorResume trả empty | Retry/DLQ đúng contract |
| Poll liên tục đọc lại NEW | Không có trạng thái/claim | Lease/idempotency và update |
| PROCESSING bị kẹt sau crash | Update trước business commit | Lease expiry, recovery job |
| Hai worker làm trùng một document | find/update không phải atomic claim | findAndModify/owner/version |
| Query trả rỗng nhưng source.receive()!=null | Message mang Flux rỗng | Test sau subscription |
| MongoDB timeout nhưng write có thể đã commit | Response lost | Retry cùng ID và reconciliation |
| Reactivity không làm giảm latency | Query/index/pool/server nghẽn | Explain, pool metrics, limit |
| Change stream không chạy | MongoDB topology/role không phù hợp | Deployment và resume token |
| Reactor cancel được hiểu là rollback | Không có bảo đảm đó | Đối chiếu trạng thái DB |
| Shutdown mất pending | Queue in-memory, fire-and-forget | Durable upstream/outbox và drain |

Đường khoanh vùng:

~~~text
Producer/Poller
  -> Spring Message
  -> Reactive source/handler
  -> Publisher created
  -> Subscribe/demand
  -> ReactiveMongoOperations
  -> MongoDB driver/database/collection
  -> onNext/onComplete/onError
  -> Business ACK/commit
~~~

## 24. Bài thực hành tổng hợp

Xây hệ thống **HTTP/Kafka → Spring Integration reactive MongoDB outbound → MongoDB → reactive inbound polling → xử lý sự kiện**.

### Phần A — API và subscription

1. Khởi tạo MongoDB test và Spring Boot reactive MongoDB starter.
2. Inject `ReactiveMongoOperations`, dựng entity `TelemetryEvent` với `@Id`.
3. Tạo `Mono` từ `save` nhưng chưa subscribe; giải thích vì sao chưa có DB ACK.
4. Dùng `StepVerifier` để subscribe, đọc lại dữ liệu và cleanup.
5. So sánh `Message<Flux<T>>`, `Message<Mono<T>>`, `Message<List<T>>` và `Message<T>`.

### Phần B — Inbound polling

1. Tạo `MongoDb.reactiveInboundChannelAdapter(...)` query status NEW.
2. Gắn fixedDelay poller, splitter, FluxMessageChannel và consumer thực sự.
3. Seed N document NEW, assert N events được phát **sau subscription**.
4. Chuyển sang `expectSingleResult(true)` trong flow khác; test empty publisher.
5. Thêm Query.limit, tenant filter, sort và projection.
6. Thử `updateExpression`, sau đó giả lập crash ở CLAIMED để thiết kế recovery.

### Phần C — Outbound writer

1. Tạo `MongoDb.reactiveOutboundChannelAdapter(reactiveMongoOperations)`.
2. Đặt `FluxMessageChannel` trước handler.
3. Gửi event từ upstream và đợi DB write/readback có giới hạn.
4. Dùng `collectionNameFunction` với allowlist LIVE/ARCHIVE.
5. Thử header thiếu, sai quyền, MongoDB down và lỗi mapping.
6. Gửi cùng event ID nhiều lần; phân biệt save/insert/partial update.

### Phần D — Reliability và hiệu năng

1. Thử `flatMap(..., 8)` và `concatMap`, so sánh throughput/order.
2. Thử timeout/cancellation và giải thích vì sao phải reconcile DB.
3. Dùng unique key và idempotency để xử lý redelivery Kafka/JMS.
4. Giả lập hai pollers cùng query NEW để thảo luận atomic claim.
5. Thiết kế `ReactiveMongoTransactionManager` cho các MongoDB operations liên quan.
6. Đặt metric publisher created/subscribed, documents emitted, write success/error, inflight.
7. Thử shutdown khi còn pending writes, kiểm tra durable retry/outbox.
8. So sánh reactive polling với change stream và blocking adapters để chọn kiến trúc.

**Câu hỏi tự đánh giá:**

- `Mono` và `Flux` khác nhau thế nào?
- Vì sao tạo `Mono` chưa đủ để MongoDB write thực sự chạy?
- `ReactiveMongoDbMessageSource.receive()` trả dữ liệu dạng nào?
- `expectSingleResult(false)` có nghĩa Source trả `List<T>` không?
- Khi source không có dữ liệu, `Flux.empty()` khác `receive()==null` thế nào?
- Vì sao reactive inbound vẫn cần poller?
- `FluxMessageChannel` giúp gì và giới hạn gì?
- `maxMessagesPerPoll(1)` có giới hạn một MongoDB document không?
- Vì sao `Query.limit(50)` khác backpressure demand?
- Tại sao `send()==true` không phải write ACK?
- Vì sao save có thể ghi đè một document cùng ID?
- Khi nào nên dùng partial update hoặc insert-only?
- `flatMap` và `concatMap` khác nhau về thứ tự?
- Vì sao `onErrorResume(Mono.empty())` có thể làm mất event?
- Cancellation có chứng minh DB chưa commit không?
- `ReactiveMongoTransactionManager` có tự commit Kafka offset hay JMS ACK không?
- Reactive source và MongoDB change stream khác nhau thế nào?
- Vì sao không nên giả định có `reactiveOutboundGateway` nếu Java DSL API không công bố?
- Test StepVerifier phải xác minh gì để tránh false positive?
- Khi nhiều instance cùng poll NEW, cần loại claim nào?

## 25. Tài liệu tham khảo

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): MongoDB reactive channel adapters, inbound/outbound và change stream.
- [Spring Integration API — MongoDb DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): các factory reactiveInboundChannelAdapter, reactiveOutboundChannelAdapter.
- [Spring Integration API — ReactiveMongoDbMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/inbound/ReactiveMongoDbMessageSource.html): Message có Flux/Mono payload và subscription.
- [Spring Integration API — ReactiveMongoDbMessageSourceSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/ReactiveMongoDbMessageSourceSpec.html): collection, entityClass, expectSingleResult và update.
- [Spring Integration API — ReactiveMongoDbStoringMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/outbound/ReactiveMongoDbStoringMessageHandler.html): Mono<Void>, collectionNameExpression và converter.
- [Spring Integration API — ReactiveMongoDbMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/ReactiveMongoDbMessageHandlerSpec.html): collectionName, collectionNameFunction.
- [Spring Integration Reference — Reactive Streams Support](https://docs.spring.io/spring-integration/reference/reactive-streams.html): FluxMessageChannel, ReactiveMessageHandler, splitter và polling.
- [Spring Data MongoDB — Configuration](https://docs.spring.io/spring-data/mongodb/reference/mongodb/configuration.html): ReactiveMongoDatabaseFactory và ReactiveMongoTemplate.
- [Spring Data MongoDB — CRUD](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): save, insert, update, MongoOperations.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): ReactiveMongoTransactionManager và transactions.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): subscribe, onError, flatMap, concatMap, cancellation.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): kiểm thử publishers.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): độ bền ghi và write acknowledgment.

## Kết luận

**Reactive MongoDB adapter** trong Spring Integration gồm **`ReactiveMongoDbMessageSource`** để đọc MongoDB theo poller, phát `Message<Flux<T>>` hoặc `Message<Mono<T>>`, và **`ReactiveMongoDbStoringMessageHandler`** để ghi payload qua reactive driver. Điểm quan trọng nhất là **publisher phải được subscribe** mới kích hoạt I/O theo reactive contract; `FluxMessageChannel` cùng `ReactiveMessageHandler` giúp compose luồng theo demand.

Trong **SPRING_INTEGRATION_ADAPTERS**, một thiết kế production còn cần kiểm soát **query/collection/tenant, batch/concurrency/backpressure, lỗi/timeout/cancellation, transaction đúng phạm vi, event ID ổn định, retry/idempotency và ACK nghiệp vụ**. **Reactive cải thiện hiệu quả I/O, không tự tạo exactly-once hoặc loại bỏ nhu cầu recovery sau crash.**




