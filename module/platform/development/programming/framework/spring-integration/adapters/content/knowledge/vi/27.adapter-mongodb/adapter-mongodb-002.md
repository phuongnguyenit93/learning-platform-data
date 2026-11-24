# MongoDB outbound channel adapter trong Spring Integration

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả cách **MongoDB outbound channel adapter** nhận `Message<?>` từ `MessageChannel` và ghi payload vào một collection.
- Phân biệt outbound **adapter một chiều**, outbound **gateway request/reply**, inbound adapter có poller và reactive outbound adapter.
- Tạo `MongoDbStoringMessageHandler` bằng `MongoOperations`, gắn vào IntegrationFlow với Java DSL `.handle(...)` và cấu hình XML tương đương.
- Chọn collection cố định hoặc qua expression trên header **được kiểm soát**, hiểu vai trò của `MongoTemplate` và `MongoConverter`.
- Phân biệt `save`, `insert`, `updateFirst` và `upsert`; hiểu `_id` ổn định giúp chống bản ghi trùng nhưng không tự tạo exactly-once end-to-end.
- Tiền xử lý `byte[]`, JSON, DTO và `List<T>`; kiểm tra mapping, lỗi ghi, transaction, write concern, retry và idempotency.
- Kiểm thử đường message-to-document bằng MongoDB test instance, theo dõi độ trễ, trạng thái queue và vòng đời consumer.

Bài thuộc chương **Adapter MongoDB**, module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`, thực hành các luồng qua file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, cùng hợp đồng message, lỗi và vòng đời kết nối. Ở bài này, **MongoDB là đích ghi**, còn Spring Integration giúp dữ liệu đã chuẩn hóa đến đúng handler lưu trữ.

## 1. Bài toán: ghi telemetry từ hệ thống ngoài vào MongoDB

Một dịch vụ Spring Boot nhận sự kiện từ UDP, HTTP hoặc Kafka rồi muốn lưu bản ghi sau khi validate:

~~~json
{
  "_id": "evt-1001",
  "deviceId": "node-7",
  "sequence": 42,
  "temperatureC": 26.5,
  "measuredAt": "2026-11-23T02:00:00Z",
  "source": "udp"
}
~~~

~~~mermaid
flowchart LR
    A["UDP / HTTP / Kafka / SFTP"] --> B["Inbound adapter hoặc gateway"]
    B --> C["Deserialize + validate"]
    C --> D["MessageChannel: toMongo"]
    D --> E["MongoDbStoringMessageHandler"]
    E --> F["MongoOperations.save"]
    F --> G["MongoDB collection<br/>telemetry_events"]
~~~

Producer gửi `Message<TelemetryRecord>` vào input channel; MongoDB writer nhận **payload** rồi thực hiện ghi. Đối tượng đã lưu thường được truy vấn lại bằng `MongoTemplate` hoặc repository nếu nghiệp vụ muốn kiểm tra kết quả.

**Chú ý:** Outbound adapter **không tự gửi reply message** chứa document ID hay kết quả ghi. Nếu nghiệp vụ cần phản hồi kết quả qua channel, phải thiết kế một gateway/service có response contract thích hợp. Đồng thời, một lần `send()` thành công không chứng minh chuỗi nghiệp vụ ở mọi hệ thống đã hoàn tất.

## 2. Vị trí MongoDB outbound trong Spring Integration

| Thành phần | Vai trò | Cơ chế kích hoạt |
|---|---|---|
| **MongoDB inbound channel adapter** | Query MongoDB, đưa kết quả ra output channel | **Poller** |
| **MongoDB outbound channel adapter** | Ghi payload vào một MongoDB collection | Message đến **input channel** |
| **MongoDB outbound gateway** | Query MongoDB và trả response message | Request message và reply channel |
| **MongoDB change stream inbound** | Phát message khi có sự kiện thay đổi | Subscription/change stream |
| **Reactive MongoDB outbound adapter** | Ghi bằng ReactiveMongoOperations | Reactive/asynchronous pipeline |
| **MongoOperations trong service** | Thực hiện CRUD/transaction tùy biến | Code ứng dụng gọi |

**MongoDB outbound adapter không cần poller riêng.** Nó là message consumer: khi upstream phát một message, handler xử lý theo semantics của channel. Ví dụ SFTP inbound dùng poller để lấy file rồi chuyển sang MongoDB outbound; poller nằm ở **SFTP inbound**, không ở writer.

### 2.1. Class và DSL cần dùng đúng

Trong Spring Integration, writer blocking có class:

~~~java
org.springframework.integration.mongodb.outbound.MongoDbStoringMessageHandler
~~~

Java DSL có thể nhận bean đó bằng `.handle(handler)`. Đừng nhầm với `MongoDb.outboundGateway(...)` — đó là gateway query có reply. API `MongoDb.reactiveOutboundChannelAdapter(...)` phục vụ **reactive**; không suy luận có factory blocking tên `MongoDb.outboundChannelAdapter(...)` trên mọi phiên bản.

## 3. Payload và MessageHeaders không phải cùng dữ liệu

Một Spring message đi vào MongoDB writer:

~~~text
Message<TelemetryRecord>
  payload:
    id = "evt-1001"
    deviceId = "node-7"
    sequence = 42
    measuredAt = 2026-11-23T02:00:00Z
  headers:
    id = Spring Message UUID
    timestamp = Spring Message creation time
    correlationId = ...
    mongoTargetCollection = ...
~~~

`MongoDbStoringMessageHandler` lấy **message payload** để lưu. Message headers là metadata của Spring Integration; chúng **không tự biến thành field trong BSON document**.

| Thành phần | Dùng cho việc gì? | Mặc định lưu vào MongoDB? |
|---|---|---|
| Entity `id` / `@Id` | Ánh xạ thành document `_id` | Có, nếu converter cấu hình phù hợp |
| `deviceId`, `sequence` | Field nghiệp vụ | Có |
| `MessageHeaders.ID` | Định danh message nội bộ | Không tự động |
| `MessageHeaders.TIMESTAMP` | Thời điểm message được tạo | Không tự động |
| `headers['mongoTargetCollection']` | Chọn collection nếu cấu hình expression | Không tự động |
| `correlationId` | Trace một luồng message | Chỉ khi chủ động ánh xạ vào payload |

Một event bị retry có thể được đóng gói vào **message mới** với UUID khác. Để nhận diện bản ghi nghiệp vụ và hỗ trợ idempotency, dùng **event ID ổn định** trong payload, không dựa vào MessageHeaders.ID.

## 4. Chuẩn bị dependency và kết nối

Với một dự án **Spring Boot 3.x** dùng dependency management đồng bộ:

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
~~~

Khi dùng Spring Boot major version khác, cần đối chiếu tên artifact starter, BOM và tương thích của Spring Integration/Spring Data. Bài này dùng **blocking MongoOperations**, không dùng ReactiveMongoOperations.

Trong `application.yml` của lab:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/adapter_lab
~~~

URI trên chỉ là **MongoDB local để học**. Production cần secrets/TLS, connection timeout, write concern, quyền truy cập ít nhất cần thiết và đúng database/collection. Spring Boot thường tạo bean `MongoTemplate` có thể inject qua `MongoOperations` khi MongoDB starter đã cấu hình đúng.

## 5. Thiết kế entity có định danh bền vững

Java 17+:

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "telemetry_events")
public record TelemetryRecord(
        @Id String id,
        String deviceId,
        long sequence,
        BigDecimal temperatureC,
        Instant measuredAt,
        String source) {
}
~~~

Ý nghĩa:

- `id` (ví dụ `evt-1001`): ID sự kiện **ổn định qua retry**; ánh xạ sang `_id`.
- `deviceId` và `sequence`: định danh nguồn và sequence nghiệp vụ, có thể dùng để chống trùng theo contract.
- `temperatureC`: giá trị `BigDecimal`, phụ thuộc mapping của Spring Data/MongoConverter.
- `measuredAt`: thời điểm tạo dữ liệu ở nguồn, không nhất thiết là lúc MongoDB ghi.
- `source`: nguồn được ứng dụng chuẩn hóa như `udp`, `http`, `kafka`.

**Không tạo ID ngẫu nhiên mới mỗi khi retry cùng event** nếu mục tiêu tránh document trùng. Bất kỳ field nào từ nguồn bên ngoài cũng cần được validate, kể cả `id`, `deviceId`, số đo và timestamp.

## 6. Cấu hình Java DSL: một Message được ghi vào MongoDB

Tạo `DirectChannel` làm input channel, bean `MongoDbStoringMessageHandler` và IntegrationFlow nối hai thành phần:

~~~java
package example.mongodb;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.outbound.MongoDbStoringMessageHandler;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class MongoOutboundConfig {

    @Bean("toMongo")
    public MessageChannel toMongo() {
        return new DirectChannel();
    }

    @Bean("mongoWriter")
    public MongoDbStoringMessageHandler mongoWriter(
            MongoOperations mongoOperations) {

        MongoDbStoringMessageHandler handler =
                new MongoDbStoringMessageHandler(mongoOperations);

        handler.setCollectionNameExpression(
                new LiteralExpression("telemetry_events"));

        return handler;
    }

    @Bean
    public IntegrationFlow mongoOutboundFlow(
            @Qualifier("mongoWriter")
            MongoDbStoringMessageHandler writer) {

        return IntegrationFlow.from("toMongo")
                .handle(writer)
                .get();
    }
}
~~~

Giải thích:

1. `toMongo` là input channel cho MongoDB writer.
2. `MongoDbStoringMessageHandler(mongoOperations)` nhận đối tượng Spring Data đã kết nối database.
3. `LiteralExpression("telemetry_events")` đặt collection tĩnh; không để request bên ngoài quyết định tùy ý.
4. `.handle(writer)` đăng ký một **service-activating outbound endpoint**, không mở poller.
5. Với `DirectChannel`, dispatch đến handler là **đồng bộ** trong thread caller theo semantics của channel. Ghi MongoDB chậm có thể khiến producer bị chờ.
6. Không có reply channel mặc định để trả kết quả `save`. Nếu cần result/error response theo message, phải định nghĩa riêng.

### 6.1. Producer gửi một record

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class TelemetryPublisher {

    private final MessageChannel toMongo;

    public TelemetryPublisher(
            @Qualifier("toMongo") MessageChannel toMongo) {
        this.toMongo = toMongo;
    }

    public void publish(TelemetryRecord record) {
        if (record == null || record.id() == null
                || record.id().isBlank()
                || record.deviceId() == null
                || !record.deviceId().matches("[A-Za-z0-9_-]{1,64}")
                || record.sequence() < 0
                || record.temperatureC() == null
                || record.measuredAt() == null
                || record.source() == null
                || record.source().isBlank()) {
            throw new IllegalArgumentException("Invalid telemetry");
        }

        boolean accepted = toMongo.send(
                MessageBuilder.withPayload(record).build());
        if (!accepted) {
            throw new IllegalStateException(
                    "MongoDB outbound message was not accepted");
        }
    }

    public void publishExample() {
        publish(new TelemetryRecord(
                "evt-1001",
                "node-7",
                42L,
                new BigDecimal("26.5"),
                Instant.parse("2026-11-23T02:00:00Z"),
                "udp"));
    }
}
~~~

Với cấu hình này, `publishExample()` gửi đúng một `Message<TelemetryRecord>` vào MongoDB writer. Nếu không có lỗi, handler thực hiện lưu payload vào collection theo cấu hình.

**Đừng hiểu `send()==true` thành MongoDB commit ACK theo nghĩa nghiệp vụ ở mọi kiến trúc.** Trong flow đồng bộ với DirectChannel, exception MongoDB thường về caller; nếu thay bằng ExecutorChannel/QueueChannel, producer có thể nhận kết quả send trước khi database lưu xong.

### 6.2. Kiểm tra bằng mongosh

Sau khi publish một lần trong môi trường lab:

~~~javascript
use adapter_lab

db.telemetry_events.findOne({ _id: "evt-1001" })
~~~

Kết quả mong đợi chứa `_id`, `deviceId`, `sequence`, `temperatureC`, `measuredAt` và `source`. Kiểu BSON thực tế của thời gian/số có thể phụ thuộc converter; khi test nên đọc lại bằng entity class và assert **giá trị nghiệp vụ**, không so sánh cứng một chuỗi JSON hiển thị.

## 7. Phân biệt save, insert, partial update và upsert

Trong implementation blocking, `MongoDbStoringMessageHandler` dùng cơ chế lưu payload qua **`MongoOperations.save(payload, collectionName)`**. Vì vậy hành vi **save** là trọng tâm của outbound adapter.

| Thao tác | API ví dụ | Khi document đã tồn tại | Dùng khi |
|---|---|---|---|
| **save** | `mongoOperations.save(record, collection)` | Có thể thay thế/ghi đè document theo `_id`, chịu quy tắc mapping/version | Lưu trạng thái tài liệu đầy đủ |
| **insert** | `mongoOperations.insert(record, collection)` | Trùng `_id` thường báo duplicate key | Event bất biến, chỉ chấp nhận tạo mới |
| **partial update** | `updateFirst(Query, Update, ...)` | Đổi các field được chỉ định | Vá status, counters hoặc metadata |
| **upsert theo query** | `upsert(Query, Update, ...)` | Update nếu khớp; insert nếu chưa có | Update theo điều kiện/nghiệp vụ |
| **findAndModify** | `findAndModify(...)` | Thay đổi có điều kiện, trả document theo option | Claim job/lease |
| **outbound gateway** | MongoDb gateway query | Có reply message | Cần query result thay vì chỉ ghi |

### 7.1. Save với cùng _id không phải “bỏ qua duplicate”

Giả sử document `evt-1001` đã có field `status=DONE` do một service khác cập nhật. Nếu bạn `save` lại payload cũ không có field status, thao tác save có thể **thay thế document** và làm mất field mới, tùy schema/version.

Những nguyên tắc cần nhớ:

- **Save không phải patch.** Không dùng outbound writer mặc định khi chỉ muốn cập nhật một field của bản ghi hiện hữu.
- **Cùng _id có thể tránh tạo thêm document, không có nghĩa tránh được ghi đè dữ liệu mới**.
- Nếu cần optimistic locking, hãy nghiên cứu `@Version` và hành vi `MongoTemplate.save` tương ứng, sau đó kiểm thử version conflict.
- Nếu một sự kiện phải ghi đúng một lần và không cho phép update, dùng custom handler gọi `insert`, kết hợp unique key và phân loại duplicate theo nghiệp vụ.
- Nếu cập nhật theo điều kiện như `status=PROCESSING`, dùng `updateFirst`/`findAndModify` với điều kiện owner/version thích hợp.

### 7.2. Ví dụ cập nhật status: handler khác, không phải tùy chọn của writer

Đoạn sau **không phải chế độ patch của MongoDbStoringMessageHandler**. Đây là một Service Activator riêng khi ứng dụng cần cập nhật từng trường:

~~~java
package example.mongodb;

import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class StatusPatchHandler {

    private final MongoOperations mongoOperations;

    public StatusPatchHandler(MongoOperations mongoOperations) {
        this.mongoOperations = mongoOperations;
    }

    @ServiceActivator(inputChannel = "statusPatches")
    public void handle(StatusPatch request) {
        Query query = Query.query(
                Criteria.where("_id").is(request.eventId())
                        .and("status").is("PROCESSING"));
        Update update = new Update().set("status", "DONE");

        var result = mongoOperations.updateFirst(
                query, update, "telemetry_events");

        if (result.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "No PROCESSING event: " + request.eventId());
        }
    }

    public record StatusPatch(String eventId) {}
}
~~~

Cần khai báo channel `statusPatches` và producer gửi `StatusPatch` riêng. Trong hệ thống có nhiều worker, nên thêm điều kiện claim owner/version/lease để tránh worker này kết thúc nhầm việc của worker khác.

## 8. Chọn collection bằng LiteralExpression hoặc SpEL

### 8.1. Collection cố định

Cấu hình của mục 6:

~~~java
handler.setCollectionNameExpression(
        new LiteralExpression("telemetry_events"));
~~~

Đây là lựa chọn an toàn cho một luồng sự kiện cố định: dễ phân quyền, cấu hình index và giám sát.

### 8.2. Collection theo header đã được kiểm soát

Giả sử upstream tin cậy đã gắn header:

~~~text
headers["mongoTargetCollection"] = "telemetry_events"
~~~

Có thể cấu hình:

~~~java
import org.springframework.expression.spel.standard.SpelExpressionParser;

handler.setCollectionNameExpression(
        new SpelExpressionParser().parseExpression(
            "headers['mongoTargetCollection']"));
~~~

Cách này **thay thế** LiteralExpression, không dùng cả hai cùng lúc. Spring Integration đánh giá expression theo message để chọn collection.

**Rủi ro:** nếu request HTTP/Kafka/UDP từ bên ngoài được phép gắn header chứa bất kỳ tên collection nào, client có thể khiến writer ghi sai collection hoặc vượt phạm vi tenant. Trước handler, chuyển mã logic đã được xác thực sang một allowlist:

~~~java
String allowedCollection = switch (trustedCategory) {
    case "telemetry" -> "telemetry_events";
    case "audit" -> "audit_events";
    default -> throw new IllegalArgumentException(
            "Unsupported MongoDB target");
};
~~~

`trustedCategory` ở đây phải là một giá trị ứng dụng đã xác thực quyền, không phải header chưa tin cậy. Với multi-tenant, phải kiểm tra **tenant ownership/authorization**, không chỉ regex trên tên collection.

### 8.3. Hai cách khởi tạo handler

~~~java
// Cách A: Spring Data MongoOperations/MongoTemplate đã cấu hình:
MongoDbStoringMessageHandler a =
        new MongoDbStoringMessageHandler(mongoOperations);

// Cách B: dùng MongoDatabaseFactory và MongoConverter riêng:
MongoDbStoringMessageHandler b =
        new MongoDbStoringMessageHandler(mongoDatabaseFactory);
b.setMongoConverter(mongoConverter);
~~~

Chỉ dùng `setMongoConverter` theo contract API dành cho handler tạo bằng factory; **không gọi thêm trên handler đã nhận MongoOperations** nếu API không cho phép. Trong XML, `mongo-template` và `mongodb-factory` là hai cách thay thế, không khai báo đồng thời cho cùng adapter.

## 9. Kiểu payload: DTO, JSON, byte[] và List

| Payload nhận từ upstream | Khuyến nghị |
|---|---|
| `TelemetryRecord` có `@Id` | Đưa vào writer sau validation |
| `org.bson.Document` | Có thể lưu theo MongoDB mapping; kiểm tra schema và loại BSON |
| `Map<String,Object>` | Xác định rõ mapping, ID và field hợp lệ |
| JSON `String` | Parse/validate thành DTO hoặc Document trước ghi |
| `byte[]` từ UDP/SFTP/file | Decode theo charset/protocol rồi tạo DTO |
| `List<TelemetryRecord>` | Dùng **splitter** để biến thành từng message |

Ví dụ một MongoDB inbound adapter có thể phát `Message<List<InboxEvent>>`. Không mặc định rằng outbound writer sẽ lưu từng phần tử list thành một document riêng. Hãy thêm splitter:

~~~mermaid
flowchart LR
    A["Message<List<TelemetryRecord>>"] --> B["Splitter"]
    B --> C["Message<TelemetryRecord>"]
    C --> D["toMongo"]
    D --> E["MongoDB writer"]
~~~

Flow phụ:

~~~java
@Bean
public IntegrationFlow batchToMongoFlow() {
    return IntegrationFlow.from("batchInput")
            .split()
            .channel("toMongo")
            .get();
}
~~~

Trong context thật phải khai báo `batchInput` và `toMongo`. Đoạn này **không tự thêm batch insert/bulk write**; một message được tách thường dẫn đến một lần handler ghi. Nếu cần bulk operations, hãy thiết kế một handler riêng với batch size, transaction/retry và idempotency thích hợp.

**Nguyên tắc chuyển đổi:** không đưa bytes chưa kiểm tra từ UDP hoặc JSON chưa validate thẳng vào database writer rồi trông chờ MongoConverter tự đảm nhiệm tất cả ràng buộc schema nghiệp vụ.

## 10. Cấu hình XML tương đương

Khi dự án dùng Spring Integration XML:

~~~xml
<!-- File XML có namespace int và int-mongodb thích hợp -->
<int:channel id="toMongoXml"/>

<int-mongodb:outbound-channel-adapter
        id="mongoOutboundWriter"
        channel="toMongoXml"
        mongo-template="mongoTemplate"
        collection-name="telemetry_events"/>
~~~

Ở đây `mongoTemplate` là bean đã được khai báo; `channel` là **input channel** của outbound adapter.

Nếu cần dùng factory/converter:

~~~xml
<int-mongodb:outbound-channel-adapter
        id="mongoOutboundWithFactory"
        channel="toMongoXml"
        mongodb-factory="mongoDbFactory"
        mongo-converter="mongoConverter"
        collection-name="telemetry_events"/>
~~~

Hai đoạn là **hai phương án**, không đăng ký cùng lúc rồi mong mọi message tự được phát đến cả hai. Với `DirectChannel` nhiều subscriber, message không được bảo đảm broadcast cho tất cả; nếu chủ đích fan-out, dùng `PublishSubscribeChannel` hoặc wire tap theo kiến trúc.

Một số thuộc tính của outbound writer:

- `collection-name`: collection tĩnh.
- `collection-name-expression`: expression SpEL trả tên collection.
- `mongo-template`: bean Spring Data MongoTemplate.
- `mongodb-factory` và `mongo-converter`: cấu hình thay thế.
- `channel`: channel mà endpoint consume.

**Không dùng các thuộc tính query/poller của MongoDB inbound adapter** để giả định outbound writer sẽ “quét collection theo lịch”. Hướng dữ liệu ngược nhau.

## 11. Lỗi ghi, timeout và error channel

Các lỗi thường gặp:

| Tình huống | Nguyên nhân có thể | Cách phản ứng |
|---|---|---|
| Connection timeout | MongoDB down, DNS/route, pool cạn | Retry có giới hạn, backoff, cảnh báo |
| Permission denied | Credentials/role thiếu quyền ghi | Sửa cấu hình/quyền; không retry vô hạn |
| Mapping/validation error | Dữ liệu thiếu field, sai type | Reject/quarantine; không retry dữ liệu xác định sai |
| Duplicate key | Unique index/_id bị vi phạm trong insert | Phân loại duplicate theo event ID |
| Optimistic locking conflict | `@Version` cũ hơn DB | Re-read/reconcile theo nghiệp vụ |
| Write result không rõ | Timeout sau khi server có thể đã ghi | Retry với ID ổn định; kiểm tra trạng thái trước khi quyết định |
| MongoDB chậm | I/O, index, connection pool, quá tải | Queue có giới hạn, đo latency, scaling |
| Business flow lỗi sau save | Bước kế tiếp thất bại | Thiết kế transaction/outbox và idempotency |
| Collection đích sai | Header routing chưa validate | Allowlist, kiểm tra quyền và trace |

### 11.1. DirectChannel và lỗi đồng bộ

~~~text
producer.send(message)
    |
    v
DirectChannel
    |
    v
MongoDbStoringMessageHandler
    |
    v
MongoOperations.save(...)
    |
    +-- Bình thường: call quay về
    +-- Exception: có thể trả về caller (MessagingException)
~~~

Với cấu hình đồng bộ như mục 6, luồng producer có thể chờ MongoDB I/O. Đây là lựa chọn đơn giản nhưng cần cân nhắc timeout ở HTTP/UDP producer hoặc service xử lý.

### 11.2. ExecutorChannel, QueueChannel và lỗi bất đồng bộ

Nếu đặt executor hoặc queue giữa producer và writer, việc chấp nhận message có thể xảy ra **trước** khi MongoDB hoàn tất lưu. Exception có thể đi tới error channel hoặc được xử lý trong worker/poller, không nhất thiết tới caller.

Cần thiết kế:

1. Queue **có capacity giới hạn**.
2. Retry/backoff/jitter theo loại lỗi; không retry vô hạn.
3. Dead-letter/quarantine cho payload lỗi schema.
4. Cùng **event ID** qua mọi attempt.
5. Metric phân biệt `accepted`, `save succeeded` và `business committed`.
6. Durable outbox/broker nếu process crash không được làm mất message pending.

**QueueChannel in-memory không tự biến thành durable queue**, và `MessageChannel.send()==true` không đồng nghĩa MongoDB đã ACK write.

## 12. Idempotency, write concern và transaction

### 12.1. Khi write timeout, kết quả có thể chưa xác định

Một kịch bản:

~~~mermaid
sequenceDiagram
    participant S as Producer
    participant I as Integration flow
    participant M as MongoDB
    S->>I: Event evt-1001
    I->>M: save(_id=evt-1001)
    M-->>I: Response bị thất lạc
    Note over I: Timeout, chưa rõ đã ghi hay chưa
    S->>I: Retry cùng event ID
    I->>M: save(_id=evt-1001) lần nữa
~~~

Nếu retry tạo ID mới, có thể sinh duplicate document. Nếu dùng **cùng `_id`**, lần ghi lại có thể không tạo thêm document, nhưng vẫn có thể **ghi đè** thay đổi khác. Trường hợp sự kiện là immutable, nên đánh giá thiết kế **insert-only + unique key** thay cho replace.

### 12.2. Unique key nghiệp vụ

Một cách tăng bảo vệ khi thiết bị phát sự kiện có sequence:

~~~javascript
db.telemetry_events.createIndex(
  { deviceId: 1, sequence: 1 },
  { unique: true }
)
~~~

**Chỉ là ví dụ lab.** Nếu thiết bị reset sequence khi reboot, cần `epoch` hoặc event ID toàn cục trong unique key. Trước khi tạo unique index trên collection thật, phải kiểm tra dữ liệu trùng, chi phí index, retention và tương thích schema.

### 12.3. ACK MongoDB và business ACK không giống nhau

MongoDB có **write concern** để quy định xác nhận ghi trong triển khai cụ thể (ví dụ mức ghi từ primary hoặc majority). Nhưng một ACK ghi MongoDB **không chứng minh Kafka offset đã commit, HTTP client đã nhận response hoặc file đã được đánh dấu hoàn thành**.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant K as Kafka consumer
    participant F as Integration flow
    participant M as MongoDB
    K->>F: Event evt-1001
    F->>M: save(evt-1001)
    M-->>F: Write acknowledged
    Note over F: Crash trước khi commit offset
    K->>F: Redelivery cùng event
    F->>M: Save lại, cần idempotency
~~~

Đối với file/SFTP, chỉ xóa/di chuyển file nguồn theo hợp đồng sau khi dữ liệu được ghi thành công. Với JMS/AMQP cần thiết kế broker ACK/transaction. UDP thuần không tự bảo đảm giao hàng; khi cần chắc chắn phải có application-level ACK hoặc đổi transport.

### 12.4. MongoDB transaction không tự bao trùm hệ thống khác

Nếu nghiệp vụ cần thay đổi **nhiều document atomically**, cần MongoDB transaction với deployment hỗ trợ, `MongoTransactionManager` và transaction boundary đúng. Không mặc định `MongoDbStoringMessageHandler` tự mở multi-document transaction.

Ngay cả khi một transaction MongoDB commit, nó không tự bao trùm HTTP, Kafka, JMS hoặc file system. Muốn đồng bộ trạng thái giữa các hệ thống, thường cần **outbox, saga, retry và reconciliation**.

## 13. Vòng đời và graceful shutdown

Outbound handler là consumer endpoint do Spring Integration quản lý:

- Bean, input channel và subscription được thiết lập khi Spring context khởi tạo.
- Khi endpoint đang hoạt động, message tới channel sẽ được xử lý theo cách dispatch.
- Writer không có poller riêng; lỗi kết nối có thể xuất hiện **khi xử lý một message**, dù ứng dụng trước đó đã start thành công.
- Khi shutdown, cần điều phối dừng producer, ngừng nhận message mới và hoàn tất những thao tác đang chạy.
- Nếu dùng ExecutorChannel/QueueChannel, còn có message pending. Stop endpoint không tự bảo đảm các message ấy đã được ghi bền.
- Nếu business không cho phép mất event, cần durable source/outbox và quy trình resume sau restart.

Tách rõ các mốc:

~~~text
A. Producer tạo message
B. Channel nhận message
C. MongoDB handler bắt đầu save
D. MongoDB xác nhận write theo write concern
E. Business xác nhận đã hoàn tất / ACK upstream
~~~

Không phát ACK nghiệp vụ tại **B** nếu hợp đồng yêu cầu chờ **D hoặc E**. Khi write timeout không rõ kết quả, phải đối chiếu bằng event ID và tiếp tục retry/reconciliation phù hợp.

## 14. Kiểm thử MongoDB outbound adapter

### 14.1. Unit test validator

Tách logic validate khỏi IO:

~~~java
package example.mongodb;

public final class TelemetryValidator {

    public void validate(TelemetryRecord value) {
        if (value == null
                || value.id() == null || value.id().isBlank()
                || value.deviceId() == null
                || value.deviceId().isBlank()
                || value.temperatureC() == null
                || value.measuredAt() == null
                || value.sequence() < 0) {
            throw new IllegalArgumentException("Invalid telemetry");
        }
    }
}
~~~

JUnit:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class TelemetryValidatorTest {

    @Test
    void validEventIsAccepted() {
        TelemetryRecord event = new TelemetryRecord(
                "evt-1001", "node-7", 42L,
                new BigDecimal("26.5"),
                Instant.parse("2026-11-23T02:00:00Z"),
                "udp");

        assertDoesNotThrow(
                () -> new TelemetryValidator().validate(event));
    }

    @Test
    void missingIdIsRejected() {
        TelemetryRecord event = new TelemetryRecord(
                null, "node-7", 42L,
                new BigDecimal("26.5"),
                Instant.parse("2026-11-23T02:00:00Z"),
                "udp");

        assertThrows(IllegalArgumentException.class,
                () -> new TelemetryValidator().validate(event));
    }
}
~~~

Unit test **chưa kiểm tra MongoDB connection, mapping hoặc writer**.

### 14.2. Integration test với MongoDB test instance

Dùng MongoDB riêng cho test (hoặc Testcontainers khi runner có Docker). Test gửi message qua `toMongo` rồi đọc document:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoOutboundIntegrationTest {

    @Autowired
    @Qualifier("toMongo")
    MessageChannel toMongo;

    @Autowired
    MongoOperations mongoOperations;

    @Test
    void writesPayloadIntoExpectedCollection() {
        String id = "test-" + UUID.randomUUID();
        TelemetryRecord event = new TelemetryRecord(
                id, "node-test", 43L,
                new BigDecimal("24.5"),
                Instant.parse("2026-11-23T02:00:00Z"),
                "test");

        try {
            assertTrue(toMongo.send(
                    MessageBuilder.withPayload(event).build()));

            TelemetryRecord stored = mongoOperations.findById(
                    id, TelemetryRecord.class, "telemetry_events");

            assertNotNull(stored);
            assertEquals("node-test", stored.deviceId());
            assertEquals(43L, stored.sequence());
            assertEquals(0, stored.temperatureC()
                    .compareTo(new BigDecimal("24.5")));
        } finally {
            mongoOperations.remove(
                Query.query(Criteria.where("_id").is(id)),
                "telemetry_events");
        }
    }
}
~~~

**Điều kiện chạy:** phải cấu hình context trỏ vào MongoDB **test** có thật. Đoạn code không tự mở server hoặc container và tuyệt đối không được trỏ vào production database khi test có cleanup. Khi đưa các class vào project, nhớ dùng cùng package hoặc import đúng tên.

### 14.3. Ma trận test nên có

| Test case | Điều cần khẳng định |
|---|---|
| Gửi một DTO hợp lệ | Document có trong đúng collection |
| Gửi lại cùng ID và payload | Không tự tạo nhiều document nếu save theo ID đúng hợp đồng |
| Gửi cùng ID nhưng payload khác | Phát hiện nguy cơ replace/overwrite |
| ID null | Validator từ chối trước khi DB tự cấp ID |
| Upstream gửi JSON string | Có bước parse/validate trước writer |
| Message chứa List | Split thành từng message hoặc dùng bulk handler riêng |
| MongoDB tạm down | Error handling, retry và metric đúng |
| Collection dynamic | Allowlist và authorization chính xác |
| Producer qua ExecutorChannel | Không coi send true là DB commit |
| Crash sau DB write trước ACK source | Redelivery cần idempotency |

Đừng tuyên bố “exactly once” chỉ vì test thấy một document còn lại sau hai lần save cùng ID; có thể đã có **hai thao tác ghi**.

## 15. Quan sát, hiệu năng và bảo mật

Những metric gợi ý, cần tự triển khai hoặc map từ instrumentation thực tế:

| Metric | Nội dung |
|---|---|
| `mongo_outbound_received_total` | Message tới writer |
| `mongo_outbound_validation_rejected_total` | Payload bị từ chối trước save |
| `mongo_outbound_save_attempt_total` | Số lần thử lưu |
| `mongo_outbound_save_success_total` | Ghi thành công theo contract |
| `mongo_outbound_save_error_total` | Lỗi ghi |
| `mongo_outbound_write_duration_seconds` | Thời gian write |
| `mongo_outbound_retry_total` | Retry count |
| `mongo_outbound_pending_depth` | Message trong queue/outbox |
| `mongo_outbound_dead_letter_total` | Message đưa vào quarantine |
| `mongo_outbound_business_committed_total` | Sự kiện hoàn tất theo business |

Cẩn trọng với label metric theo `eventId`/`deviceId` vì dễ tăng cardinality không kiểm soát.

**Hiệu năng:** đừng gửi List rất lớn mà không biết semantics handler; cân nhắc bulk write riêng có batch size, chỉ mục hợp lý và queue có giới hạn. MongoDB áp dụng giới hạn **BSON document tối đa 16 MiB** trong cấu hình thông thường; hãy đo dữ liệu sau mapping, không chỉ kích thước JSON string. Blocking MongoOperations không phù hợp để chạy trực tiếp trên event-loop reactive không cho phép chặn.

**Bảo mật:** dùng tài khoản MongoDB có least privilege, TLS khi cần và secret manager. Không cho header chưa xác thực chọn collection tùy ý. Validate schema/version/ID, giới hạn độ dài và tránh ghi log nguyên document nhạy cảm. Giới hạn retry để không khuếch đại tải khi DB down; kiểm tra audit và retention theo dữ liệu nghiệp vụ.

## 16. Bài thực hành tổng hợp

Xây pipeline **HTTP/UDP/Kafka → Spring Integration → MongoDB**:

1. Tạo MongoDB `adapter_lab`, collection `telemetry_events` và kết nối bằng `MongoOperations`.
2. Định nghĩa entity `TelemetryRecord` có `@Id` và các trường đã validate.
3. Tạo `toMongo`, `MongoDbStoringMessageHandler`, `LiteralExpression("telemetry_events")` và `IntegrationFlow.from("toMongo").handle(writer)`.
4. Gửi `Message<TelemetryRecord>` rồi kiểm tra document qua mongosh và integration test.
5. Gửi lại cùng ID/same payload, sau đó cùng ID/changed payload: giải thích sự khác biệt giữa idempotency và overwrite.
6. Thử custom `insert` để yêu cầu insert-only và `updateFirst` để patch; không giả định writer mặc định đổi operation tùy message.
7. Kết nối một upstream tạo `Message<List<T>>` rồi thêm splitter.
8. Chuyển collection từ static sang dynamic **chỉ sau bước allowlist**.
9. Tắt MongoDB lab, quan sát lỗi ở DirectChannel; thử ExecutorChannel và phân biệt gửi thành công với commit.
10. Đề xuất outbox, retry/backoff, unique key và một test crash sau DB write nhưng trước source ACK.
11. Đặt metric cho received, save attempts/success/error, latency, queue depth và retries.
12. Nếu muốn reply có dữ liệu truy vấn, so sánh adapter với `MongoDb.outboundGateway(...)`.

**Câu hỏi tự đánh giá:**

- Vì sao MongoDB outbound channel adapter không tự có poller?
- `MongoDbStoringMessageHandler` và `MongoDb.outboundGateway(...)` khác nhau thế nào?
- Handler lưu message payload hay toàn bộ message headers?
- `MessageHeaders.ID` có nên dùng làm idempotency key của document không?
- `save` khác `insert` và `updateFirst` ra sao?
- Khi nào `save` có thể ghi đè thay đổi của một writer khác?
- Nếu cần chỉ cập nhật `status`, nên dùng cách nào?
- Vì sao `List<T>` nên qua splitter khi muốn ghi từng document?
- Tại sao `send()==true` với ExecutorChannel không chứng minh DB đã ghi?
- Sau timeout, vì sao cùng event ID quan trọng?
- MongoDB write concern có bao trùm Kafka offset hay HTTP response không?
- Làm thế nào bảo vệ collection selection qua header?

## 17. Tài liệu tham khảo

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): MongoDB outbound adapter, XML, outbound gateway và reactive variant.
- [Spring Integration API — MongoDbStoringMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/outbound/MongoDbStoringMessageHandler.html): constructor, collection name expression và converter.
- [Spring Integration API — MongoDb Java DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): các factory inbound, gateway và reactive.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): semantics DirectChannel, ExecutorChannel và queue.
- [Spring Data MongoDB — CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): save, insert, update, upsert, optimistic locking và transaction.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): MongoTemplate, entity mapping, converter, indexes và transaction.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): định nghĩa và mức xác nhận write.

## Kết luận

**MongoDB outbound channel adapter** là một endpoint **ghi payload** của Spring Integration. Trong blocking API, `MongoDbStoringMessageHandler` nhận `Message` ở input channel rồi lưu payload vào MongoDB collection qua `MongoOperations`; có thể cấu hình bằng Java DSL hoặc XML.

Thiết kế đúng cần **entity có kiểu và ID ổn định**, collection rõ ràng, hiểu chính xác **save không phải insert-only hoặc partial update**, kiểm soát lỗi/timeout, transaction và idempotency. Một ACK ghi từ MongoDB không chứng minh các hệ thống HTTP, SFTP, Kafka, JMS, AMQP, file hay UDP liên quan đã hoàn tất toàn bộ nghiệp vụ; điều đó phụ thuộc hợp đồng ACK, outbox, retry, transaction và quy trình vận hành end-to-end.
