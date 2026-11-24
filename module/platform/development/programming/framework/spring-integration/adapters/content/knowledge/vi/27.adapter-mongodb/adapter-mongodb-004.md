# MongoTemplate và MongoDbFactory trong Spring Integration

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích rành mạch **MongoDB Java driver**, `MongoClient`, **`MongoDatabaseFactory`**, **`MongoTemplate`**, `MongoOperations` và `MongoConverter`.
- Hiểu vì sao tài liệu cũ nhắc **MongoDbFactory**, trong khi API Spring Data MongoDB hiện hành sử dụng **MongoDatabaseFactory**, và biết cập nhật import/cấu hình đúng theo phiên bản.
- Cấu hình MongoDB cho ứng dụng Spring Boot bằng auto-configuration hoặc cấu hình thủ công Java/XML, không khởi tạo trùng client/template.
- Chọn phụ thuộc `MongoOperations` hay `MongoDatabaseFactory` khi xây **MongoDB inbound channel adapter**, **outbound channel adapter** và **outbound gateway**.
- Thiết kế entity mapping với `@Document`, `@Id`, `@Field`, kiểu thời gian và số thập phân; biết khi nào cần custom converter.
- Tách database, collection, tenant, credentials và transaction; sử dụng `@Qualifier` an toàn khi ứng dụng có nhiều MongoDB.
- Phân tích connection pool, blocking/reactive, lỗi driver, transaction, timeout, retry và lifecycle liên quan đến integration flow.
- Viết unit/integration test kiểm tra MongoTemplate, wiring của factory và đường `MessageChannel` tới MongoDB.

Bài thuộc chương **Adapter MongoDB** của module **SPRING_INTEGRATION_ADAPTERS**. Module hướng dẫn kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành tích hợp file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, đồng thời quan tâm hợp đồng message, lỗi và vòng đời kết nối. **MongoTemplate và MongoDatabaseFactory là lớp kết nối và truy cập dữ liệu mà MongoDB adapters sử dụng**, chứ bản thân chúng không phải message channel hoặc poller.

## 1. Bài toán: adapter cần thành phần gì để kết nối MongoDB?

Giả sử ứng dụng có ba nhu cầu:

1. Định kỳ lấy document `status=NEW` từ collection `inbox_events` đưa vào một `MessageChannel`.
2. Nhận một `Message<Reading>` đã được chuẩn hóa từ HTTP/UDP/Kafka rồi lưu vào collection `readings`.
3. Khi HTTP request hỏi dữ liệu mới nhất của một thiết bị, truy vấn MongoDB và trả `Message<List<Reading>>`.

Cả ba đều sử dụng kết nối MongoDB và ánh xạ Java ↔ BSON. Thay vì mỗi endpoint tự mở socket, Spring Data cung cấp các tầng:

~~~mermaid
flowchart TB
    A["Spring Integration inbound / outbound / gateway"] --> O["MongoOperations / MongoTemplate"]
    O --> V["MongoConverter / MappingMongoConverter"]
    O --> F["MongoDatabaseFactory"]
    V -.-> O
    F --> C["MongoClient<br/>MongoDB Java Driver"]
    C --> DB["MongoDB server / replica set"]
    P["Poller"] -.->|"Chỉ cho inbound polling"| A
    A --> M["MessageChannel"]
~~~

**Phân biệt trách nhiệm:**

- `MongoClient` quản lý việc giao tiếp với MongoDB theo driver, bao gồm connection pool và server discovery.
- `MongoDatabaseFactory` cung cấp cách lấy `MongoDatabase` theo database name và tích hợp thông tin session với Spring Data.
- `MongoTemplate` triển khai `MongoOperations`, cung cấp API Java cấp cao như `find`, `save`, `updateFirst`, `remove`.
- `MongoConverter` ánh xạ dữ liệu Java với BSON document, phục vụ query mapping, đọc/ghi entity và custom conversions.
- **Spring Integration adapter/gateway** lấy những bean đó làm phụ thuộc để nhận/gửi Spring Message.
- **Poller** quyết định lúc gọi message source inbound; nó không phải chức năng của MongoTemplate.

## 2. Tên MongoDbFactory và MongoDatabaseFactory qua các phiên bản

Chủ đề bài học dùng từ **MongoDbFactory** vì thuật ngữ này xuất hiện trong tài liệu cấu hình MongoDB đời cũ.

| Tên | Vai trò | Khi viết code hiện hành |
|---|---|---|
| `MongoDbFactory` | Interface factory trong các phiên bản Spring Data MongoDB cũ | Kiểm tra phiên bản dự án; không tự dùng import lịch sử |
| **`MongoDatabaseFactory`** | Interface factory thay thế trong Spring Data MongoDB hiện đại | **Sử dụng** trong ví dụ bài này |
| **`SimpleMongoClientDatabaseFactory`** | Implementation dựa trên synchronous `MongoClient` | Dùng khi tự cấu hình database factory |
| `MongoTemplate` | Implementation của `MongoOperations` | Dùng cho CRUD/query và inject vào Integration endpoint |
| `MongoConverter` / `MappingMongoConverter` | Java object ↔ MongoDB document | Cần khi chọn factory path có converter riêng |
| `ReactiveMongoDatabaseFactory` | Factory cho reactive driver | Không thay trực tiếp cho blocking `MongoDatabaseFactory` |

**Import chính xác cho API hiện hành**:

~~~java
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.convert.MongoConverter;
~~~

**Không viết** `org.springframework.data.mongodb.core.MongoDatabaseFactory` — interface này nằm trong package `org.springframework.data.mongodb`. Nếu một ví dụ cũ dùng `MongoDbFactory` hoặc class/constructor của MongoDB driver đời cũ, cần tra phiên bản Spring Data/Spring Integration tương ứng trước khi chuyển sang code hiện đại.

Lưu ý tên attribute XML **`mongodb-factory`** và tên biến bean **`mongoDbFactory`** vẫn có thể xuất hiện trong cấu hình hiện nay. Đó là **tên cấu hình/bean**, không có nghĩa Java interface trong dự án mới vẫn là `MongoDbFactory`.

## 3. Những lớp dữ liệu không nên đồng nhất

| Lớp | Ví dụ | Trách nhiệm |
|---|---|---|
| Network driver | `com.mongodb.client.MongoClient` | Kết nối, pool, chọn server, chạy MongoDB commands |
| Factory | `MongoDatabaseFactory` | Lấy database và phối hợp session trong Spring Data |
| Operations | `MongoOperations` | Contract cấp cao của thao tác truy vấn/ghi |
| Template | `MongoTemplate` | Implementation phổ biến của MongoOperations |
| Converter | `MongoConverter` | Mapping ID, field, type, custom conversions |
| Integration endpoint | `MongoDbMessageSource`, `MongoDbStoringMessageHandler`, `MongoDbOutboundGateway` | Chuyển Spring Message và DB operation qua lại |
| Integration channel | `DirectChannel`, `QueueChannel`, ... | Định tuyến message giữa các endpoint |

**Không lấy `MongoClient.getDatabase(...)` làm thay thế mặc định cho `MongoTemplate`** khi bạn cần mapping kiểu domain, `@Id`, `@Field` hoặc cơ chế exception/transaction của Spring Data. Truy cập driver thô vẫn có ích cho các lệnh đặc biệt, nhưng người viết code phải tự xử lý BSON, timeout, session và schema tương ứng.

## 4. Thêm dependency và chọn blocking hay reactive

Với **Spring Boot 3.x** sử dụng BOM quản lý các version tương thích, một ứng dụng MongoDB adapters blocking có thể khai báo:

~~~xml
<!-- Bên trong phần dependencies của pom.xml -->
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

- Spring Data MongoDB cung cấp `MongoTemplate`, `MongoDatabaseFactory` và entity mapping.
- Spring Integration MongoDB cung cấp adapter/gateway, DSL, message source/handler.
- MongoDB **synchronous driver** cần hiện diện; MongoDB starter blocking thường cung cấp qua transitive dependency.
- Spring Boot major version khác có thể dùng tên starter/properties khác. Hãy dùng dependency BOM tương thích với **phiên bản thật của dự án**, không trộn tùy ý các major version.

**Reactive** là một nhánh riêng: `ReactiveMongoOperations`, `ReactiveMongoTemplate`, `ReactiveMongoDatabaseFactory` và reactive streams driver. Không truyền reactive factory vào constructor của blocking `MongoDbStoringMessageHandler` rồi mong compiler tự chuyển. Ngược lại, gọi blocking MongoTemplate trên event-loop có thể chặn thread và gây nghẽn.

## 5. Cách A: để Spring Boot tự cấu hình MongoTemplate

Với **Spring Boot 3.x**, cấu hình lab trong `application.yml`:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/adapter_lab
~~~

Khi các điều kiện auto-configuration phù hợp, Spring Boot có thể tự tạo `MongoClient`, `MongoDatabaseFactory`, `MongoTemplate` và converter. Khi đó **chỉ inject bean sẵn có**:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@Service
public class ReadingsQueryService {

    private final MongoOperations mongo;

    public ReadingsQueryService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public Reading findById(String id) {
        Query query = Query.query(Criteria.where("_id").is(id));
        return mongo.findOne(query, Reading.class, "readings");
    }
}
~~~

**Cách A không cần tự tạo thêm MongoTemplate bean.** Việc vừa để Boot tạo template vừa khai báo bean thủ công cùng kiểu/tên có thể gây auto-configuration back off không như dự định, bean ambiguity hoặc một endpoint dùng nhầm database. Nếu đã có một `MongoOperations` do Boot quản lý thì nên tái sử dụng xuyên các IntegrationFlow cùng database.

### 5.1. Đưa credentials ra khỏi source code

Trong lab URI không có mật khẩu. Production nên dùng environment variable hoặc secret manager được hệ thống triển khai cung cấp, chẳng hạn thay giá trị `spring.data.mongodb.uri` bằng cấu hình ở môi trường. Không ghi user/password, access token hay certificate private key trong repository hoặc log.

Khi chạy trong Docker, `127.0.0.1` trỏ vào **container hiện tại**, không tự trỏ vào MongoDB trên host hoặc container khác. Cần dùng hostname/port của network được triển khai và kiểm tra DNS, firewall, TLS.

## 6. Cách B: tự cấu hình MongoClient → Factory → Template

Nếu ứng dụng không dùng Spring Boot auto-config, có nhiều database hoặc cần kiểm soát đặc biệt, có thể tự khai báo các bean.

~~~java
package example.mongodb;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;

@Configuration
public class ManualMongoConfiguration {

    @Bean(destroyMethod = "close")
    public MongoClient mongoClient(
            @Value("${app.mongo.uri}") String uri) {
        return MongoClients.create(uri);
    }

    @Bean
    public MongoDatabaseFactory mongoDatabaseFactory(
            MongoClient mongoClient) {
        return new SimpleMongoClientDatabaseFactory(
                mongoClient, "adapter_lab");
    }

    @Bean
    public MongoTemplate mongoTemplate(
            MongoDatabaseFactory mongoDatabaseFactory) {
        return new MongoTemplate(mongoDatabaseFactory);
    }
}
~~~

Cấu hình property dành cho ví dụ này:

~~~yaml
app:
  mongo:
    uri: mongodb://127.0.0.1:27017
~~~

**Cách B là phương án thay thế cách A**, không cần đăng ký cả hai trong cùng một Spring context. Nếu có nhiều client/template, dùng bean name và `@Qualifier` cụ thể như mục 12.

Giải thích vòng đời:

1. `MongoClients.create(uri)` tạo synchronous MongoClient.
2. `SimpleMongoClientDatabaseFactory(client, "adapter_lab")` chọn database và cung cấp API factory.
3. `new MongoTemplate(factory)` tạo lớp thao tác CRUD/query; mặc định Spring Data tạo/cấu hình converter phù hợp.
4. `@Bean(destroyMethod="close")` gắn việc đóng **MongoClient** với lifecycle Spring context.
5. `MongoTemplate` và factory được dùng lại giữa các message; **không tạo MongoClient mới trong mỗi handler call**.
6. Khi MongoDB tạm down, khởi tạo object client/template chưa chắc phát hiện ngay; lỗi thật có thể xảy ra tại lần I/O đầu tiên.

Nếu nhiều database trên **cùng MongoDB deployment**, các factory có thể chia sẻ một MongoClient pool nhưng chọn tên database khác. Nếu database thuộc **cluster khác**, cần các MongoClient với URI, pool và credentials riêng.

### 6.1. Khi nào muốn truyền factory cho MongoTemplate kèm MongoConverter?

Spring Data có constructor nhận factory và converter:

~~~java
MongoTemplate template =
        new MongoTemplate(mongoDatabaseFactory, mongoConverter);
~~~

`mongoConverter` phải được **cấu hình/khởi tạo đúng** cho Spring Data, chẳng hạn `MappingMongoConverter` có mapping context và custom conversions phù hợp. Không nên tạo một converter sơ sài chỉ để gọi constructor; điều đó có thể làm khác hành vi `@Id`, `@Field`, enum, time hay custom type giữa inbound/outbound.

Một quy tắc hữu ích: nếu ứng dụng không có yêu cầu mapping đặc biệt, **ưu tiên dùng template đã được Boot cấu hình**. Nếu cần converter riêng, cấu hình và test ở tầng Spring Data trước khi đưa nó vào Spring Integration.

## 7. MongoTemplate/MongoOperations dùng làm gì?

`MongoOperations` là interface mô tả các thao tác với document theo mô hình Spring Data. `MongoTemplate` là implementation phổ biến.

| API | Ý nghĩa | Khi sử dụng trong Integration |
|---|---|---|
| `find(Query, T.class, collection)` | Lấy danh sách document thành entity | MongoDB inbound polling / outbound gateway |
| `findOne(Query, T.class, collection)` | Tìm một entity hoặc null | Gateway tìm document đơn |
| `findById(id, T.class, collection)` | Tìm theo ID | Service tra cứu |
| `save(object, collection)` | Insert mới hoặc ghi theo ID, có thể thay thế document | MongoDB outbound storing handler |
| `insert(object, collection)` | Insert mới, không thay thế theo ID | Custom handler cần insert-only |
| `updateFirst(Query, Update, ...)` | Sửa field có điều kiện | Đánh dấu status, claim, patch |
| `upsert(Query, Update, ...)` | Update nếu khớp, insert nếu không | Đồng bộ trạng thái theo key |
| `remove(Query, ...)` | Xóa document theo query | Cleanup test hoặc nghiệp vụ có quyền |
| `findAndModify(...)` | Query + update có điều kiện ở một operation | Claim job, lease |
| `execute(...)` | Truy cập API raw collection khi cần | Các thao tác không biểu diễn gọn qua template |

Ví dụ truy vấn và ghi một document:

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public final class ReadingRepositoryLikeService {

    private final MongoOperations mongo;

    public ReadingRepositoryLikeService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public List<Reading> recentNewReadings(String deviceId) {
        Query query = Query.query(
                Criteria.where("deviceId").is(deviceId)
                        .and("status").is("NEW"))
                .with(Sort.by(
                    Sort.Order.desc("observedAt"),
                    Sort.Order.desc("_id")))
                .limit(50);

        return mongo.find(query, Reading.class, "readings");
    }

    public void store(Reading reading) {
        mongo.save(reading, "readings");
    }

    public long markDone(String eventId) {
        Query query = Query.query(
                Criteria.where("_id").is(eventId)
                        .and("status").is("PROCESSING"));
        Update update = new Update().set("status", "DONE");

        return mongo.updateFirst(
                query, update, "readings")
                .getModifiedCount();
    }
}
~~~

`markDone` dùng **partial update**, không gọi `save` để thay một field khi có nguy cơ overwrite thay đổi đồng thời. Kết quả `getModifiedCount()==0` có thể nghĩa là document không khớp query, trạng thái đã là DONE hoặc một writer khác đã thay đổi — phải xác minh theo contract.

**Phân biệt read/write API và message integration:** gọi `MongoOperations.find(...)` không tự phát Spring Message. Chỉ khi bạn kết nối nó với một `MessageSource`/`MessageHandler`/gateway hoặc gửi kết quả vào channel thì nó mới trở thành một bước IntegrationFlow.

## 8. MongoConverter và entity mapping

Để MongoDB document có kiểu rõ ràng, dùng Spring Data mapping annotations:

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "readings")
public record Reading(
        @Id String id,
        @Field("device_id") String deviceId,
        long sequence,
        @Field(targetType = FieldType.DECIMAL128)
        BigDecimal temperatureC,
        String status,
        Instant observedAt) {
}
~~~

Document tương ứng có thể có:

~~~json
{
  "_id": "evt-101",
  "device_id": "node-7",
  "sequence": 101,
  "temperatureC": { "$numberDecimal": "26.5" },
  "status": "NEW",
  "observedAt": { "$date": "2026-11-23T02:00:00Z" }
}
~~~

**Đoạn JSON là Extended JSON minh họa**, không phải cách MongoDB driver luôn in ra document. Trong code Spring Data, `@Field("device_id")` tác động lên tên field được ghi vào BSON; truy vấn qua `Query` dựa trên domain property có thể được converter/query mapper xử lý. Kiểm thử dữ liệu thực khi kết hợp query raw, aggregation raw hoặc callback trực tiếp driver.

### 8.1. Vai trò của converter

- `@Id` ánh xạ ID của Java entity tới `_id` của document.
- `@Field` đổi tên field Java/BSON hoặc chỉ định kiểu BSON.
- `MongoConverter` ánh xạ Java object ↔ MongoDB document; `MappingMongoConverter` là implementation thông dụng.
- Converter có thể xử lý type information, custom conversions và các loại dữ liệu phức tạp.
- `BigDecimal` cần quy định cách lưu phù hợp, chẳng hạn Decimal128 để xử lý số thập phân; không mặc định mọi cấu hình đều lưu giống ví dụ.
- `Instant` và time zone cần một hợp đồng rõ; MongoDB date là thời điểm UTC, còn cách hiển thị phụ thuộc client.

Khi bạn cung cấp một `MongoTemplate` có converter riêng, **cả adapter dùng template đó** sẽ chịu kết quả mapping theo cấu hình. Nếu thay bằng đường factory + converter ở Integration endpoint, hãy đảm bảo converter đúng kiểu và đồng nhất với luồng còn lại.

### 8.2. Custom conversions

Nếu cần lưu một value object đặc biệt, Spring Data hỗ trợ `MongoCustomConversions` với converters đọc/ghi. Các converters cần được đăng ký vào `MappingMongoConverter` và được thử nghiệm hai chiều.

**Không tự viết `toString()` rồi lưu mọi DTO thành String JSON** khi mục tiêu là query theo `deviceId`, `status`, timestamp hoặc index. Dữ liệu không đúng BSON schema sẽ khó truy vấn, khó index và dễ lỗi chuyển đổi về sau.

## 9. Chọn Template hay Factory cho MongoDB inbound adapter

Với Spring Integration Java DSL, cách trực tiếp dùng **MongoOperations**:

~~~java
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
public class ReadingInboundConfig {

    @Bean("mongoReadings")
    public MessageChannel mongoReadings() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow pollNewReadings(MongoOperations mongo) {
        return IntegrationFlow
                .from(
                    MongoDb.inboundChannelAdapter(
                            mongo, "{ 'status': 'NEW' }")
                        .collectionName("readings")
                        .entityClass(Reading.class)
                        .expectSingleResult(false),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(1)))
                .split()
                .channel("mongoReadings")
                .get();
    }
}
~~~

**Flow này chỉ minh họa đọc**. Nó không đánh dấu `status=DONE`; vì thế cùng document `NEW` có thể bị phát lại ở những chu kỳ sau. Khi triển khai thật, cần update/claim có điều kiện, retry, idempotency và quản lý backlog.

Một phương án **thay thế** dùng factory trực tiếp:

~~~java
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(Criteria.where("status").is("NEW"))
        .limit(50);

MongoDb.inboundChannelAdapter(mongoDatabaseFactory, query)
        .collectionName("readings")
        .entityClass(Reading.class)
        .expectSingleResult(false);
~~~

Đoạn factory là phần cấu hình spec để gắn vào `IntegrationFlow.from(sourceSpec, pollerConfig)`, **không phải một flow thứ hai cần chạy đồng thời**. Nếu dùng cả hai flow quét cùng collection, nguy cơ đọc trùng tăng.

### 9.1. Một poll không có nghĩa một document

Mặc định một lần `MongoDbMessageSource.receive()` với `expectSingleResult(false)` có thể trả một `Message<List<Reading>>`. `maxMessagesPerPoll(1)` giới hạn số lần gọi source trong một chu kỳ, **không giới hạn số document** của một query. Cần `Query.limit(...)`, sort, index và splitter để điều tiết tải.

## 10. Cấu hình MongoDB outbound storing handler

Khi upstream gửi `Message<Reading>` vào channel, writer blocking có thể sử dụng template đã cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.outbound.MongoDbStoringMessageHandler;
import org.springframework.data.mongodb.core.MongoOperations;

@Bean
public MongoDbStoringMessageHandler readingWriter(MongoOperations mongo) {
    MongoDbStoringMessageHandler handler =
            new MongoDbStoringMessageHandler(mongo);
    handler.setCollectionNameExpression(
            new LiteralExpression("readings"));
    return handler;
}

@Bean
public IntegrationFlow writeReadings(
        MongoDbStoringMessageHandler readingWriter) {
    return IntegrationFlow.from("toMongoReadings")
            .handle(readingWriter)
            .get();
}
~~~

Đây là fragment của một `@Configuration` có khai báo input channel `toMongoReadings`. `MongoDbStoringMessageHandler` lưu **payload**, không tự lưu toàn bộ Spring Message headers. Nó thường dùng đường `MongoOperations.save(...)`, nghĩa là có thể **thay thế document theo ID**, không phải partial update.

Cách khác dùng factory:

~~~java
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.convert.MongoConverter;

MongoDbStoringMessageHandler writer =
        new MongoDbStoringMessageHandler(mongoDatabaseFactory);
writer.setMongoConverter(mongoConverter);
writer.setCollectionNameExpression(
        new LiteralExpression("readings"));
~~~

**Đây là phương án thay thế**, không tạo hai writer tranh nhau cùng một `DirectChannel`. `setMongoConverter(...)` chỉ phù hợp với instance handler được khởi tạo bằng **MongoDatabaseFactory**, theo contract API. Nếu handler đã nhận `MongoOperations` hoàn chỉnh, converter là cấu hình bên trong template; không dùng setter để giả định đổi được converter của template đã dựng.

## 11. Cấu hình MongoDB outbound gateway (request/reply)

Nếu flow cần đọc MongoDB **theo từng request** và nhận kết quả:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.MongoOperations;

@Bean
public IntegrationFlow searchNewReadings(MongoOperations mongo) {
    return IntegrationFlow.from("readingQueryRequests")
            .handle(MongoDb.outboundGateway(mongo)
                    .collectionName("readings")
                    .query("{ 'status': 'NEW' }")
                    .entityClass(Reading.class)
                    .expectSingleResult(false))
            .get();
}
~~~

Khi caller có `replyChannel` hợp lệ (ví dụ `@MessagingGateway` proxy), outbound gateway phát response, thường chứa một `List<Reading>` nếu `expectSingleResult(false)`. Gateway **không cần poller** và khác outbound storing handler một chiều.

API Java DSL còn hỗ trợ dùng factory + converter:

~~~java
MongoDb.outboundGateway(
        mongoDatabaseFactory, mongoConverter)
    .collectionName("readings")
    .query("{ 'status': 'NEW' }")
    .entityClass(Reading.class)
    .expectSingleResult(false);
~~~

**Quan trọng:** với gateway, factory path cần **MongoConverter** khi dùng factory overload này. Không suy luận mọi endpoint MongoDB chỉ cần một factory và đều tự có converter giống nhau.

### 11.1. Cấu hình callback hoặc query

Gateway có thể dùng `query(...)` / `queryFunction(...)` hoặc `collectionCallback(...)` để chạy một phép toán trên collection. Các đường này có API/semantics riêng; **không trộn collection callback với query options** trong cùng gateway.

Khi query phụ thuộc input HTTP/Kafka, ưu tiên DTO typed, `Criteria` và limit, không cho người dùng tùy ý cung cấp MongoDB JSON query hoặc collection name chưa xác thực.

## 12. Dùng nhiều MongoDB/database an toàn

Giả sử ứng dụng có hai database trên **cùng cluster**: `business_db` và `audit_db`. Có thể tạo hai factory dùng chung một MongoClient:

~~~java
import com.mongodb.client.MongoClient;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;

@Configuration
public class MultiDatabaseMongoConfig {

    @Bean("businessFactory")
    public MongoDatabaseFactory businessFactory(MongoClient client) {
        return new SimpleMongoClientDatabaseFactory(
                client, "business_db");
    }

    @Bean("auditFactory")
    public MongoDatabaseFactory auditFactory(MongoClient client) {
        return new SimpleMongoClientDatabaseFactory(
                client, "audit_db");
    }

    @Bean("businessMongo")
    public MongoOperations businessMongo(
            @Qualifier("businessFactory")
            MongoDatabaseFactory factory) {
        return new MongoTemplate(factory);
    }

    @Bean("auditMongo")
    public MongoOperations auditMongo(
            @Qualifier("auditFactory")
            MongoDatabaseFactory factory) {
        return new MongoTemplate(factory);
    }
}
~~~

Đây là **phương án cấu hình riêng**: nó giả định ứng dụng đã có đúng một `MongoClient` bean, không được chạy đồng thời với cấu hình tự tạo template trùng bean trong mục 6 mà không điều phối. Khi inject vào endpoint, phải chọn đúng template:

~~~java
@Bean
public MongoDbStoringMessageHandler auditWriter(
        @Qualifier("auditMongo") MongoOperations mongo) {
    MongoDbStoringMessageHandler handler =
            new MongoDbStoringMessageHandler(mongo);
    handler.setCollectionNameExpression(
            new LiteralExpression("audit_events"));
    return handler;
}
~~~

**Một MongoClient dùng chung nghĩa là dùng chung kết nối/credential theo client**, nhưng database names khác nhau. Việc tách database **không tự tạo quyền truy cập riêng**: cần MongoDB roles, tenant policy và auditing phù hợp.

### 12.1. Đừng nhầm database với collection

- **Database** được factory/template chọn, ví dụ `business_db`.
- **Collection** được MongoOperations hoặc Integration endpoint chọn, ví dụ `readings`.
- Đổi `collectionNameExpression` từ `readings` sang `audit_events` **không chuyển sang database `audit_db`**.
- Muốn đổi database đích an toàn, dùng bean/template tương ứng và routing/authorization rõ; không dùng header chưa tin cậy làm tên database tùy ý.

### 12.2. Hai cluster khác nhau

Nếu `audit_db` ở cluster khác, dùng MongoClient riêng với URI/credentials/pool riêng. Đặt tên bean rõ như `auditClient`/`auditFactory`/`auditMongo` và inject bằng `@Qualifier`. Nếu có nhiều candidates, autowiring chỉ theo kiểu `MongoOperations` thường không đủ; đừng dựa vào bean được chọn tình cờ.

Khi thiết kế multi-tenant, đừng để client có khả năng đọc/ghi mọi tenant nếu không cần. Factory không thay thế authorization.

## 13. Java XML configuration: mongo-template và mongodb-factory

Spring Integration MongoDB XML namespace dùng những attribute như:

| Attribute | Ý nghĩa |
|---|---|
| `mongo-template` | Ref đến `MongoTemplate` / MongoOperations đã cấu hình |
| `mongodb-factory` | Ref đến bean triển khai `MongoDatabaseFactory` |
| `mongo-converter` | Ref đến `MongoConverter` khi cấu hình factory path phù hợp |
| `collection-name` | Tên collection cố định |
| `collection-name-expression` | Expression để chọn collection theo message |
| `query / query-expression` | Bộ lọc đọc trên inbound/gateway, không phải thuộc tính writer thông thường |

Hai cấu hình **thay thế** cho một MongoDB outbound writer:

~~~xml
<!-- Ví dụ A: dùng template đã tạo -->
<int-mongodb:outbound-channel-adapter
    id="mongoWriterWithTemplate"
    channel="toMongo"
    mongo-template="mongoTemplate"
    collection-name="readings"/>
~~~

~~~xml
<!-- Ví dụ B: dùng factory + converter -->
<int-mongodb:outbound-channel-adapter
    id="mongoWriterWithFactory"
    channel="toMongo"
    mongodb-factory="mongoDbFactory"
    mongo-converter="mongoConverter"
    collection-name="readings"/>
~~~

**Không đăng ký cả hai endpoint trên cùng input `DirectChannel`** nếu ý định là một message chỉ được ghi một lần. Hai subscriber trên `DirectChannel` không tự nhận cùng một bản sao message; một số trường hợp chúng cạnh tranh để nhận message.

**Không được đặt đồng thời `mongo-template` và `mongodb-factory` trên cùng một adapter/gateway** theo contract XML. Nếu cần converter đặc biệt, hãy đảm bảo cả đường template và factory đã sử dụng cấu hình chuyển đổi tương thích.

Nếu bạn khai báo bean factory trong Spring XML, class implementation hiện hành là `org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory`, còn Java interface là `org.springframework.data.mongodb.MongoDatabaseFactory`. XML bean ID `mongoDbFactory` chỉ là tên gọi, không phải import Java cũ.

## 14. Connection pool, threading và performance

MongoTemplate thường được đăng ký làm **singleton bean dùng lại**. Mỗi lần gửi message qua MongoDB adapter không nên khởi tạo một `MongoClient` mới.

| Tình huống | Rủi ro | Hướng xử lý |
|---|---|---|
| Tạo client trong mỗi message handler | Tăng pool/socket, chậm và có thể rò resource | Dùng singleton MongoClient bean |
| Inbound poll quá nhanh | DB query liên tục và đọc trùng | Điều chỉnh poller, query limit/index, trạng thái xử lý |
| Writer dùng DirectChannel | MongoDB I/O làm block thread caller | Chọn timeout/nhánh async có kiểm soát |
| Writer dùng ExecutorChannel | Queue/worker quá tải | Capacity hữu hạn, retry policy, error channel |
| Gateway trả List rất lớn | Tốn memory, latency và thread | Query.limit, projection, pagination |
| Client pool cạn | Request xếp hàng chờ connection | Giám sát pool, điều chỉnh throughput và pool config |
| Database down | Server selection/write timeout | Circuit breaker, backoff, health/readiness |
| Nhiều template với nhiều client | Pool tổng tăng | Chỉ tách client khi cần cluster/credentials riêng |

**Blocking và reactive không trộn tùy tiện:** nếu dùng reactive flow để xử lý nhiều request không chặn thread, hãy chọn `ReactiveMongoOperations` và MongoDB reactive adapters thực sự. Gọi blocking MongoTemplate trên Reactor event-loop làm mất lợi ích non-blocking.

### 14.1. Kết quả một lần gửi message nói được điều gì?

- `MessageChannel.send(...)` thành công cho biết message được chấp nhận/dispatch theo channel semantics.
- Với `DirectChannel`, handler DB blocking có thể đã được gọi trong cùng thread trước khi send trả về; lỗi MongoDB thường xuất hiện dưới dạng exception.
- Với queue/executor, send thành công **không chứng minh** dữ liệu đã ghi xong.
- Với MongoDB write concern, ACK xác định mức độ server xác nhận ghi; nó **không bảo đảm** event nguồn Kafka/JMS/SFTP/HTTP đã hoàn tất transaction ở hệ thống khác.

Cần tách metric **message accepted**, **query/write attempted**, **DB acknowledged** và **business completed**.

## 15. Lỗi, retry và transaction

### 15.1. Phân loại lỗi

| Lỗi | Địa điểm phát sinh | Hành động phù hợp |
|---|---|---|
| DNS/TLS/auth lỗi | MongoClient chọn/kết nối server | Sửa cấu hình, quyền, TLS; cảnh báo |
| Server selection timeout | Driver không chọn được MongoDB server | Retry/backoff có giới hạn, kiểm tra topology |
| Pool exhausted | Chờ connection lâu | Điều chỉnh pool, throttle workload |
| Mapping error | Converter/đọc document | Validate schema, sửa converter, quarantine |
| Duplicate key | Insert hoặc unique index | Đối chiếu idempotency key, không retry vô hạn |
| Write concern timeout | DB chưa xác nhận ở mức yêu cầu | Kết quả có thể chưa rõ; retry cùng ID và đối chiếu |
| Optimistic locking | `@Version` conflict | Re-read/reconcile, không overwrite |
| Query quá rộng | Quét nhiều document | Index, limit, projection, auth |
| Transaction aborted | MongoDB transaction lỗi | Retry transaction theo contract, tránh lặp side effect |
| Downstream thất bại sau DB save | Hệ thống khác không hoàn tất | Outbox/reconciliation/idempotency |

Spring Data thường chuyển lỗi driver sang các loại `DataAccessException`; exception có thể được Spring Integration wrap thành `MessagingException` tùy flow. **Không khẳng định mọi lỗi đều tự đến errorChannel**; với DirectChannel đồng bộ, lỗi có thể đi thẳng về caller, còn ở executor/poller sẽ cần xử lý lỗi phù hợp.

### 15.2. Transaction manager

Nếu MongoDB deployment hỗ trợ transaction, có thể khai báo `MongoTransactionManager` cho **đúng factory**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Bean
public MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory mongoDatabaseFactory) {
    return new MongoTransactionManager(mongoDatabaseFactory);
}
~~~

**MongoDB multi-document transactions** yêu cầu topology MongoDB phù hợp, thường replica set hoặc sharded cluster hỗ trợ. Code ở trên là một **fragment** trong class cấu hình, không khiến một standalone MongoDB bất kỳ tự hỗ trợ transaction.

Nếu có hai MongoDatabaseFactory/transaction manager, phải inject đúng manager cùng database mà operation sử dụng; không thể ngầm dùng một transaction bao trùm hai cluster độc lập hoặc Kafka và MongoDB.

### 15.3. Không nhầm PseudoTransactionManager

Spring Integration có cơ chế **transaction synchronization** cho poller, và đôi khi ví dụ dùng `PseudoTransactionManager` để kích hoạt callback trước/sau luồng. Pseudo manager **không biến thao tác MongoDB thành transaction thật**; cần dùng transaction manager/session thực tế để đảm bảo atomicity theo MongoDB.

Để xử lý event không được mất khi qua nhiều hệ thống, hãy cân nhắc **durable outbox/inbox, ACK sau commit, idempotency và retry** thay vì suy ra exactly-once chỉ từ việc có MongoTemplate.

## 16. Kiểm thử factory, template và Integration flow

### 16.1. Unit test phần mapping và business rule

Unit test chỉ kiểm tra DTO/validator, không cần MongoDB:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ReadingValidationTest {

    @Test
    void hasStableIdentityAndValues() {
        Reading event = new Reading(
                "evt-101", "node-7", 101,
                new BigDecimal("26.5"),
                "NEW", Instant.parse("2026-11-23T02:00:00Z"));

        assertEquals("evt-101", event.id());
        assertEquals("node-7", event.deviceId());
        assertEquals(101L, event.sequence());
    }

    @Test
    void decimalIsNotAFloatApproximation() {
        BigDecimal decimal = new BigDecimal("26.5");
        assertEquals(0,
                decimal.compareTo(new BigDecimal("26.50")));
    }
}
~~~

Unit test này **không chứng minh MongoConverter thực sự ghi Decimal128**, cũng không kiểm tra URI, database name hoặc connector Spring Integration.

### 16.2. Integration test MongoTemplate trên database test

Dùng MongoDB test instance hoặc Testcontainers khi runner có Docker. Mục tiêu: save rồi findById, đối chiếu dữ liệu được mapping:

~~~java
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
class MongoTemplateIntegrationTest {

    @Autowired
    MongoOperations mongo;

    @Test
    void roundTripsMappedReading() {
        String id = "it-" + UUID.randomUUID();
        Reading original = new Reading(
                id, "node-test", 7,
                new BigDecimal("26.5"),
                "NEW", Instant.parse("2026-11-23T02:00:00Z"));

        try {
            mongo.save(original, "readings");

            Reading stored = mongo.findById(
                    id, Reading.class, "readings");

            assertNotNull(stored);
            assertEquals("node-test", stored.deviceId());
            assertEquals(7L, stored.sequence());
            assertEquals(0, stored.temperatureC()
                    .compareTo(new BigDecimal("26.5")));
        } finally {
            mongo.remove(
                Query.query(Criteria.where("_id").is(id)),
                "readings");
        }
    }
}
~~~

**Chỉ chạy với MongoDB test được cấu hình rõ**, không trỏ vào database production vì đoạn test sẽ ghi rồi xóa bản ghi. Nếu ứng dụng có nhiều MongoOperations beans, dùng `@Qualifier` và kiểm tra database đã chọn.

### 16.3. Test IntegrationFlow dùng MongoTemplate

Có thể gắn một `QueueChannel` làm output sink sau inbound adapter:

~~~text
MongoDB test collection
      |
      v
MongoDb.inboundChannelAdapter(...)
      |
      v
Splitter
      |
      v
QueueChannel test sink
      |
      v
JUnit receive(timeout) và assert
~~~

Hoặc test outbound writer bằng cách gửi `Message<Reading>` vào `toMongoReadings`, sau đó dùng MongoOperations đọc lại document. Với gateway, gửi request và kiểm tra reply payload trong queue hoặc qua `@MessagingGateway` proxy.

**Test quan trọng cần có:**

1. Factory chọn đúng database, template dùng đúng converter.
2. `@Id`, `@Field("device_id")` và Decimal128 mapping đúng.
3. Inbound `expectSingleResult(false)` tạo List và splitter tách đúng loại.
4. Query rỗng không tạo message ở inbound polling; gateway list có hợp đồng response riêng.
5. Writer với cùng ID: kiểm tra save/overwrite semantics, không coi như insert-only.
6. Hai MongoOperations beans: `@Qualifier` đưa message tới đúng database, không ghi chéo.
7. MongoDB down: timeout, errorChannel và retry theo flow.
8. Không có dữ liệu: poller không lặp message sai hoặc tự sinh payload null.
9. Shutdown/restart: connection pool được quản lý và backlog/claim theo nghiệp vụ.
10. Multi-document transaction: chỉ test khi MongoDB topology thực sự hỗ trợ.

### 16.4. Phát hiện sai database bằng assertion

Khi dùng multi-database, một test nên ghi ID duy nhất vào `business_db.readings` và xác nhận **không có** cùng ID trong `audit_db.readings`. Ngoài assert số lượng document, kiểm tra database/collection được chọn, credentials và trường mapping. Việc cùng tên collection ở hai DB là hoàn toàn có thể nên log chỉ có `collectionName` chưa đủ để chẩn đoán routing lỗi.

## 17. Bảo mật, cấu hình và observability

- **Secrets/TLS:** URI/credentials từ secret manager hoặc environment, bật TLS và kiểm soát certificate trust khi cần.
- **Least privilege:** tài khoản đọc inbound không nhất thiết cần write; tài khoản outbound writer chỉ được ghi collection đúng quyền.
- **Tenant isolation:** collection-name expression không tự đổi database; dùng template riêng theo tenant/DB và kiểm tra quyền từ identity đáng tin.
- **No raw query injection:** không cho client HTTP/Kafka điều khiển query/collection tự do; dùng `Criteria`, limit và allowlist.
- **Payload contract:** validate schema, ID, field bắt buộc, kiểu số/thời gian trước MongoOperations.
- **Không log secrets/document nhạy cảm:** log error class, endpoint ID, database logical ID, collection allowlisted, event ID cần thiết.
- **Index và retention:** query/unique indexes phục vụ workload; không tạo index lớn vô kế hoạch.
- **Pool limits:** dùng lại client và đo connection pool utilization, server selection latency.
- **Error and retry budgets:** phân biệt lỗi auth vĩnh viễn với lỗi mạng tạm thời; không retry vô hạn gây thác lũ.
- **Session/transaction:** không chia sẻ session thủ công giữa thread nếu API/driver không hỗ trợ; dùng Spring transaction scope.
- **Metrics:** phân biệt `mongo_connect_errors_total`, `mongo_query_latency_seconds`, `mongo_save_attempt_total`, `mongo_save_success_total`, `mongo_poll_empty_total`, `mongo_integration_errors_total`, `mongo_pending_work_depth`.

Đây là **tên metric minh họa**, không phải mặc định mọi phiên bản Spring Integration xuất cùng tên. Hạn chế label có giá trị động vô hạn như `deviceId`, `_id`, IP/port hoặc MongoDB URI chứa credentials.

## 18. Các lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| Không có bean MongoTemplate | Thiếu starter/auto-config bị loại hoặc cấu hình sai | Dependency, bean graph, profile |
| Có nhiều bean MongoOperations | Multi-database nhưng inject không qualifier | Bean names, `@Qualifier`, `@Primary` có chủ đích |
| Compile lỗi `MongoDbFactory` | Dùng import API lịch sử | Chuyển sang `MongoDatabaseFactory` đúng phiên bản |
| Compile lỗi package factory | Nhầm `org.springframework.data.mongodb.core` | Import `org.springframework.data.mongodb.MongoDatabaseFactory` |
| XML báo factory/template conflict | Đặt cả `mongo-template` và `mongodb-factory` | Chọn một đường cấu hình |
| Mapping field không đúng | Custom converter thiếu config hoặc dùng raw driver | Kiểm tra @Id/@Field, converter, DB document |
| Writer ghi sai DB | Tiêm nhầm template/factory | @Qualifier, DB name của factory, target URI |
| Query trả rỗng nhưng DB có data | Sai database/collection, field mapping hoặc filter | find trực tiếp trong DB test, logs |
| Adapter poll liên tục ra trùng | Chưa đánh dấu document xử lý | Claim/lease, status và idempotency |
| MongoDB down nhưng app vẫn start | Client kết nối lazy/first I/O | Readiness, server selection timeout |
| Ghi trùng khi retry | ID không ổn định hoặc insert mới mỗi lần | Stable event ID, unique index |
| Nút thắt throughput | Pool nhỏ, query rộng, DirectChannel block | Pool metrics, query plan, channel timing |
| Transaction không khởi tạo | Standalone MongoDB/topology không hỗ trợ | Replica set, transaction manager, session |
| Reactive flow bị chặn | Dùng MongoTemplate blocking trên event loop | ReactiveMongoOperations hoặc executor thích hợp |

**Hãy khoanh vùng theo chuỗi:** request → `MessageChannel` → Integration endpoint → `MongoOperations`/converter → `MongoDatabaseFactory` → `MongoClient` → MongoDB server. Lỗi xảy ra ở một tầng không nên tự động quy kết cho toàn bộ hệ thống.

## 19. Bài thực hành tổng hợp

Tạo một ứng dụng Spring Boot và MongoDB lab, triển khai hai kiểu wiring **thay thế nhau**:

### Phần A — Hiểu các lớp

1. Vẽ sơ đồ từ `MessageChannel` tới `MongoClient`, ghi nhiệm vụ của mỗi bean.
2. Tìm import đúng của `MongoDatabaseFactory` và `SimpleMongoClientDatabaseFactory`.
3. Giải thích vì sao tên bean `mongoDbFactory` trong XML không phải tên Java interface hiện hành.
4. So sánh `MongoOperations.find`, `MongoDatabaseFactory.getDatabase()` và `MongoClient.getDatabase()`.

### Phần B — Boot và manual configuration

1. Dùng Boot 3.x với `spring.data.mongodb.uri`; inject `MongoOperations` sẵn có và lưu một `Reading`.
2. Ở profile lab **khác**, tự cấu hình MongoClient, factory và MongoTemplate như mục 6.
3. Thử cấu hình cả hai trong cùng context để quan sát lỗi bean ambiguity/backoff, rồi **sửa** bằng chọn một phương án.
4. Tạo một Reading có `@Id`, `@Field`, Decimal128 và timestamp, đọc lại bằng MongoTemplate để assert mapping.

### Phần C — Adapter integration

1. Dùng `MongoDb.inboundChannelAdapter(mongoOperations, query)` + poller + splitter để lấy `status=NEW`.
2. Thử thay bằng overload `MongoDatabaseFactory` trong một flow lab khác, không chạy hai poller cạnh tranh.
3. Cấu hình `MongoDbStoringMessageHandler(mongoOperations)` để ghi `Message<Reading>`.
4. Chuyển sang constructor factory + `setMongoConverter` phù hợp; kiểm tra kết quả map cùng schema.
5. Dùng `MongoDb.outboundGateway(mongoOperations)`, sau đó thử overload factory+converter trong flow riêng.
6. Phân biệt một `Message<List<Reading>>` với nhiều `Message<Reading>`; kiểm tra `maxMessagesPerPoll` khác `Query.limit`.

### Phần D — Concurrency và vận hành

1. Tạo hai database trong lab, hai factory/template có qualifier; xác minh writer không ghi chéo DB.
2. Thử tắt MongoDB và quan sát lỗi server selection, error handling, retry có giới hạn.
3. Thử một event ID gửi hai lần để quan sát save vs insert semantics; đề xuất unique index và idempotency.
4. Chạy test sau restart để đảm bảo MongoClient do Spring sở hữu được đóng đúng.
5. Nếu MongoDB có replica set, thêm transaction manager và kiểm tra một transaction thật; giải thích vì sao nó không bao trùm Kafka/HTTP.
6. Thiết kế metric cho query/write latency, pool usage, poll count, queue depth và business commit.

**Câu hỏi tự đánh giá:**

- Sự khác biệt giữa MongoClient, MongoDatabaseFactory và MongoTemplate là gì?
- Vì sao tên MongoDbFactory trong tài liệu cũ có thể gây lỗi import ở dự án mới?
- `MongoDatabaseFactory` thuộc package Java nào?
- Vì sao nên inject MongoOperations thay vì tạo MongoClient mỗi lần có message?
- Khi nào nên chọn MongoOperations, khi nào nên chọn factory + converter cho Integration endpoint?
- Vì sao `MongoDbStoringMessageHandler` chỉ được gọi `setMongoConverter` theo điều kiện constructor?
- `@Field("device_id")` và `@Id` ảnh hưởng cách MongoDB lưu dữ liệu như thế nào?
- `maxMessagesPerPoll(1)` có nghĩa query trả đúng một document không?
- Tên collection động có chuyển sang database khác không?
- Vì sao dùng một factory/transaction manager cho hai cluster không có nghĩa một transaction xuyên cluster?
- Khi nào nên dùng ReactiveMongoOperations thay cho MongoTemplate?
- Một lần `send()==true` qua QueueChannel có nghĩa MongoDB đã ghi xong chưa?

## 20. Tài liệu tham khảo

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): MongoDatabaseFactory, blocking/reactive, inbound/outbound adapters, gateway và XML.
- [Spring Integration API — MongoDb Java DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): overload nhận MongoOperations/MongoDatabaseFactory/MongoConverter.
- [Spring Integration API — MongoDbStoringMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/outbound/MongoDbStoringMessageHandler.html): constructors và điều kiện setMongoConverter.
- [Spring Data MongoDB — Connecting to MongoDB](https://docs.spring.io/spring-data/mongodb/reference/mongodb/configuration.html): factory, template và reactive counterparts.
- [Spring Data MongoDB — MongoTemplate](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html): API CRUD/query và converter.
- [Spring Data MongoDB — Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): @Document, @Id, @Field và custom conversions.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): MongoTransactionManager, client session và giới hạn transaction.
- [MongoDB Manual — Connection Pooling](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/): MongoClient pool và các tùy chọn driver.

## Kết luận

**MongoTemplate** cung cấp API cấp cao để thao tác MongoDB thông qua `MongoOperations`; **MongoDatabaseFactory** chọn database và phối hợp kết nối/session ở tầng Spring Data; **MongoClient** là driver thực sự giao tiếp với server; **MongoConverter** quyết định cách Java object được ánh xạ sang BSON và ngược lại. Tên **MongoDbFactory** thường gặp trong tài liệu lịch sử, còn code Spring Data MongoDB hiện hành dùng `MongoDatabaseFactory`.

Trong **SPRING_INTEGRATION_ADAPTERS**, hãy để Spring Boot cấu hình template khi phù hợp hoặc tự dựng **một** đường client → factory → template có lifecycle rõ ràng. Các inbound adapter, outbound storing handler và outbound gateway có thể nhận template hoặc factory/converter tùy API; lựa chọn phải nhất quán với mapping, database, quyền truy cập, transaction và mục tiêu giao hàng. **Cấu hình kết nối đúng mới là điều kiện cần; xử lý message đáng tin cậy còn cần query giới hạn, idempotency, retry, monitoring và thiết kế nghiệp vụ phù hợp.**
