# Mapping payload sang row với Spring Integration và Apache Cassandra

## 1. Bài toán: một Spring Message không tự trở thành Cassandra row

Một dịch vụ nhận JSON `OrderPaid` từ HTTP, JMS hoặc Kafka. Spring Integration chuyển dữ liệu đó thành `Message<?>`, rồi đẩy qua `MessageChannel` đến Cassandra outbound adapter. Nếu payload vẫn là `String` hoặc `Map<String, Object>`, adapter Cassandra ở mode `INSERT` **không tự hiểu** field `orderId` phải ghi vào cột `order_id` hay một JSON object bất kỳ phải biến thành row ở table nào.

Ta cần xác định rõ các ranh giới:

~~~mermaid
flowchart LR
    A["HTTP/JMS/Kafka body: JSON"] --> B["Deserialize / validate"]
    B --> C["Business DTO: OrderPaidEvent"]
    C --> D["Spring Integration Transformer"]
    D --> E["@Table entity: OrderEventRow"]
    E --> F["CassandraMessageHandler: INSERT"]
    F --> G["ReactiveCassandraOperations"]
    G --> H["MappingCassandraConverter"]
    H --> I["CQL INSERT với bound values"]
    I --> J[("Cassandra row")]
~~~

**Mapping payload sang row** không chỉ là đổi tên trường. Nó bao gồm: định danh nghiệp vụ, partition key, kiểu Java↔CQL, timestamp/timezone, null/UNSET, serialization, entity metadata và cách lỗi chuyển đổi ảnh hưởng đến acknowledgment của nguồn.

Đây là bài thuộc chương **Adapter Cassandra**, module **SPRING_INTEGRATION_ADAPTERS**. Module hướng dẫn kết nối các hệ thống ngoài vào Spring Integration qua inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành luồng trao đổi qua file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, xử lý hợp đồng message, lỗi và vòng đời kết nối. Nội dung bài tập trung vào Cassandra, nhưng mô hình validate → transform → map → persist cũng áp dụng khi nguồn là các adapter khác.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt payload transport, business DTO, Spring Message, Cassandra entity và CQL row.
2. Khai báo `@Table`, `@PrimaryKey`, `@Column` và composite key bằng `@PrimaryKeyClass`/`@PrimaryKeyColumn`.
3. Sử dụng `MappingCassandraConverter`/`ReactiveCassandraOperations` để mapping entity sang CQL columns và ngược lại.
4. Viết `Transformer` trong Java DSL để chuyển `Message<OrderPaidEvent>` thành `Message<OrderEventRow>`.
5. Xử lý các kiểu `text`, `int`, `bigint`, `decimal`, `timestamp`, `uuid`, collection và JSON text.
6. Phân biệt Spring Integration `Type.INSERT`, `ingestQuery` và `statementFunction`; biết thời điểm chọn direct CQL/`RowMapper`.
7. Thiết kế error handling, idempotency, replay, schema versioning và kiểm thử mapping trên Cassandra thật.

## 2. Năm kiểu dữ liệu nằm trên cùng một luồng

| Lớp dữ liệu | Ví dụ | Có annotation Cassandra? | Ai chịu trách nhiệm? |
|---|---|---|---|
| **Transport payload** | JSON bytes/string trong JMS/HTTP/Kafka | Không | Inbound adapter + message converter |
| **Domain event DTO** | `OrderPaidEvent(eventId, orderId, ...)` | Thường không | Contract validation, normalization |
| **Spring Message** | `Message<OrderPaidEvent>` + headers | Không | Channel, transformer, routing, error path |
| **Persistence entity** | `@Table("order_event") OrderEventRow` | Có | MappingCassandraConverter, repository/template |
| **Cassandra row** | `event_id text`, `occurred_at timestamp` | CQL schema | Cassandra driver/coordinator/replicas |

Không có phép biến đổi mặc định toàn diện từ **một JSON String bất kỳ** sang entity tương thích với một CQL table. Spring Data có convention-based mapping, nhưng một integration system có nhiều contract/schema versions nên **khai báo rõ tên table, tên cột, key, kiểu dữ liệu và validation**.

### 2.1. Inbound và outbound sử dụng hai cách hiểu chữ “converter”

Ở đầu vào, **Spring Messaging/Jackson/message converter** biến JSON/XML/bytes thành một Java object phù hợp business contract. Ở đầu ra, **Spring Data `CassandraConverter`**, thường là `MappingCassandraConverter`, biến **entity** và property metadata thành các giá trị CQL. Đây là **hai tầng khác nhau**.

~~~text
JSON "amountMinor": 150000
   |
   | Jackson / source deserialization
   v
OrderPaidEvent.amountMinor() : long
   |
   | Domain mapper
   v
OrderEventRow.amountMinor() : long
   |
   | MappingCassandraConverter + Java Driver codec
   v
Cassandra amount_minor : bigint
~~~

Một `RowMapper` từ Spring Data CQL hoạt động theo chiều ngược lại: **Cassandra Row → Java object**, khi truy vấn thủ công bằng `CqlTemplate`/`ReactiveCqlTemplate`. Nó không phải thành phần tự chuyển JSON inbound thành row.

## 3. Thiết kế một CQL schema gắn với contract nghiệp vụ

Ví dụ dùng Java 17+, Spring Data Cassandra 4.x/5.x, Spring Integration 6.x/7.x tương thích và một Cassandra cluster test. Môi trường có keyspace `shop_integration` đã được provision.

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    schema_version int,
    occurred_at timestamp,
    amount_minor bigint,
    currency text,
    payload_json text
);
~~~

**Vì sao `event_id` làm primary key?** Bài này minh họa nghiệp vụ tìm một event theo `eventId` và tránh tạo row mới khi broker redeliver đúng cùng sự kiện. Nếu cần query lịch sử theo `orderId`, nên thiết kế **bảng khác** với partition/clustering key phù hợp; không quét toàn bộ `order_event` rồi lọc `order_id`.

Một input JSON hợp lệ:

~~~json
{
  "eventId": "evt-8001",
  "orderId": "ORD-8001",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T03:00:00Z",
  "amountMinor": 150000,
  "currency": "VND"
}
~~~

Đối chiếu field:

| JSON/domain field | Java type | Cassandra column/type | Quy tắc |
|---|---|---|---|
| `eventId` | `String` | `event_id text PRIMARY KEY` | Không rỗng, ổn định qua retries |
| `orderId` | `String` | `order_id text` | Không rỗng, thuộc tenant/authorization context |
| `eventType` | `String` | `event_type text` | Allowlist event types được hỗ trợ |
| `schemaVersion` | `int` | `schema_version int` | Version serializer; chỉ nhận phiên bản được hỗ trợ |
| `occurredAt` | `Instant` | `occurred_at timestamp` | UTC semantics, chính xác đến milliseconds |
| `amountMinor` | `long` | `amount_minor bigint` | Đơn vị tiền nhỏ nhất, không phải floating point |
| `currency` | `String` | `currency text` | Mã tiền tệ được kiểm tra |
| Toàn bộ raw/canonical payload | `String` | `payload_json text` | Audit/troubleshooting có kiểm soát, không lưu secrets |

**Cassandra không tự tạo ID như auto-increment SQL.** Entity đã mapping phải có primary key khi gọi `insert`. Dùng `eventId` của business event thay vì sinh một UUID mới khi consumer nhận lại message.

### 3.1. Tách API contract khỏi table layout

Producer không cần biết table Cassandra tên gì. Ví dụ một HTTP request có trường `amountMinor`, còn Cassandra dùng `amount_minor`. Mapping thuộc **ứng dụng consumer/adapter**, không phải yêu cầu producer đổi JSON property theo cách lưu trữ.

Ngược lại nếu thay schema Cassandra từ `amount_minor bigint` thành `amount_decimal decimal`, không thể mong `MappingCassandraConverter` tự suy luận quy tắc chuyển đổi tiền tệ. Cần migration và mapper versioned.

## 4. Khai báo DTO và entity riêng biệt

### 4.1. DTO cho business event

~~~java
import java.time.Instant;

public record OrderPaidEvent(
        String eventId,
        String orderId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        long amountMinor,
        String currency) {
}
~~~

DTO này **không có `@Table`** vì nó mô tả hợp đồng sự kiện, không phải database schema. Với JSON deserialization, framework cần được cấu hình cho Java records/`Instant` đúng phiên bản Jackson/Spring Boot và timezone.

### 4.2. Entity mapping sang bảng CQL

~~~java
import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_event")
public record OrderEventRow(
        @PrimaryKey("event_id") String eventId,
        @Column("order_id") String orderId,
        @Column("event_type") String eventType,
        @Column("schema_version") int schemaVersion,
        @Column("occurred_at") Instant occurredAt,
        @Column("amount_minor") long amountMinor,
        @Column("currency") String currency,
        @Column("payload_json") String payloadJson) {
}
~~~

Chúng ta dùng `@Column` **cho tất cả regular fields** để loại bỏ phụ thuộc vào convention hoặc `NamingStrategy` khác nhau giữa project versions. Spring Data Cassandra hỗ trợ immutable domain objects/records ở phiên bản hiện đại, nhưng cần kiểm tra khả năng constructor binding nếu dự án đang dùng phiên bản rất cũ.

**Không lấy `@Id` hoặc `@PrimaryKey` từ JPA rồi áp dụng không kiểm chứng.** Import đúng package của Spring Data Cassandra. `@Table` của Cassandra cũng không phải `jakarta.persistence.Table`.

### 4.3. Sơ đồ hai mô hình có thay đổi độc lập

~~~mermaid
flowchart TD
    C["OrderPaidEvent - business contract"] --> M["OrderPaidToRowMapper"]
    M --> E["OrderEventRow - persistence model"]
    E --> MC["MappingCassandraConverter"]
    MC --> R[("Cassandra order_event row")]
    SC["CQL schema migration"] --> R
    V["Event schema version"] --> C
    N["Table/column naming rules"] --> E
~~~

Việc tách domain DTO và entity giúp:

- Không buộc Kafka/JMS schema thay đổi theo mỗi migration Cassandra.
- Chọn **chính xác** dữ liệu cần persist, tránh vô tình lưu auth token, headers hoặc temporary fields.
- Dễ test mapping đơn vị và integration test round-trip.
- Có chỗ đặt normalization như timestamp precision, currency allowlist, JSON canonicalization.
- Thay đổi table layout/bucketing mà không bắt mọi producer cập nhật đồng loạt.

## 5. Viết mapper: validate → normalize → serialize → tạo row

Đây là lớp dễ bị bỏ qua nhất. Entity annotation chỉ biết **cột nào nhận field nào**; annotation không tự hiểu phiên bản payload, quyền truy cập tenant, hoặc liệu một sự kiện `OrderPaid` với `amountMinor=-100` có hợp lệ hay không.

### 5.1. Mapper hoàn chỉnh với Jackson

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public final class OrderPaidToRowMapper {

    private static final Set<String> CURRENCIES =
            Set.of("VND", "USD");

    private final ObjectMapper objectMapper;

    public OrderPaidToRowMapper(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public OrderEventRow map(OrderPaidEvent event) {
        validate(event);

        // CQL timestamp dùng millisecond precision.
        Instant canonicalTime =
                event.occurredAt().truncatedTo(ChronoUnit.MILLIS);

        OrderPaidEvent canonical = new OrderPaidEvent(
                event.eventId(),
                event.orderId(),
                event.eventType(),
                event.schemaVersion(),
                canonicalTime,
                event.amountMinor(),
                event.currency());

        final String json;
        try {
            json = objectMapper.writeValueAsString(canonical);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Không serialize được OrderPaidEvent", ex);
        }

        if (json.getBytes(StandardCharsets.UTF_8).length > 64 * 1024) {
            throw new IllegalArgumentException("Payload vượt giới hạn lab");
        }

        return new OrderEventRow(
                canonical.eventId(),
                canonical.orderId(),
                canonical.eventType(),
                canonical.schemaVersion(),
                canonical.occurredAt(),
                canonical.amountMinor(),
                canonical.currency(),
                json);
    }

    private static void validate(OrderPaidEvent event) {
        if (event == null
                || event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()
                || event.occurredAt() == null) {
            throw new IllegalArgumentException(
                    "Thiếu eventId, orderId hoặc occurredAt");
        }
        if (!"OrderPaid".equals(event.eventType())
                || event.schemaVersion() != 1
                || event.amountMinor() <= 0
                || event.currency() == null
                || !CURRENCIES.contains(event.currency())) {
            throw new IllegalArgumentException(
                    "OrderPaidEvent không đúng hợp đồng phiên bản 1");
        }
    }
}
~~~

Ví dụ dùng **Jackson 2 API** (`com.fasterxml.jackson.databind.ObjectMapper`) của các ứng dụng Spring Boot 3.x. Khi dùng Spring Framework 7/Spring Boot 4 cùng Jackson 3, import/API serialization khác; cần dùng mapper được framework cấu hình tương thích với version dự án thay vì copy namespace cũ. Với `Instant`, cấu hình Java Time support, serialization timezone và format thống nhất.

**Giới hạn 64 KiB chỉ dùng minh họa**, không phải Cassandra hard limit. Production cần giới hạn payload theo cấu hình và kích thước row/partition thực, không lưu toàn bộ object nhạy cảm chỉ để debug.

### 5.2. Vì sao chuẩn hóa độ chính xác timestamp?

CQL `timestamp` biểu diễn mốc thời gian ở **độ chính xác millisecond**. `java.time.Instant` có thể chứa nanoseconds; nếu ứng dụng dùng timestamp như một thành phần clustering key và so sánh Java object với row đọc lại, khác biệt precision sẽ gây khó khăn. Hãy chọn canonical precision trước khi tạo key/row.

~~~text
Input Instant:    2026-11-23T03:00:00.123456789Z
Canonical value:  2026-11-23T03:00:00.123Z
CQL timestamp:    2026-11-23T03:00:00.123Z
~~~

Không dùng `LocalDateTime.now()` hoặc timezone mặc định của JVM để “điền” timestamp còn thiếu trong event. Một retry vài phút sau sẽ tạo khác dữ liệu; nếu timestamp thuộc primary key, điều này có thể tạo row nghiệp vụ mới.

### 5.3. Một business event, nhiều cách lưu

Ví dụ `OrderPaidEvent` có thể được:

- Lưu thành một row trong `order_event` theo `event_id` để tra cứu nhanh.
- Lưu vào một bảng timeline theo `(tenant_id, order_id, month)` để truy vấn lịch sử.
- Dùng làm input cho một projection current-state có version guard.

Ba kiểu lưu có thể dùng ba entity/mapping classes. **Không cố ép một entity chứa tất cả cách phân vùng** rồi dựa vào một primary key không thể phục vụ mọi query.

### 5.4. Điều gì xảy ra khi deserialization đã thất bại?

Nếu input JSON bị lỗi cú pháp, thiếu field không nullable hoặc `Instant` không parse được, mapper **chưa được gọi**. Lỗi xảy ra tại tầng **deserialize/contract**; retry cùng raw bytes thường không thể sửa. Phân loại “poison message” để quarantine hoặc DLQ có kiểm soát, thay vì retry nóng làm tắc nguồn.

## 6. Java DSL Spring Integration: biến DTO thành Cassandra entity

Spring Integration có `Transformer` để chuyển Spring Message payload từ một Java type sang type khác, thường giữ lại headers theo cơ chế messaging của framework. Chúng ta dùng transform **trước** `CassandraMessageHandler`.

### 6.1. Dependency minh họa

Nếu dùng Spring Boot có BOM quản lý dependency versions:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-cassandra</artifactId>
</dependency>
~~~

Tùy nguồn cụ thể còn cần `spring-integration-jms`, `spring-integration-kafka`, `spring-integration-http` hoặc dependencies phù hợp; bài học giả định **message đã được đưa vào channel**. Không thêm ngẫu nhiên tất cả adapter dependencies chỉ để chạy một flow Cassandra.

Ví dụ `application.yml` của **ứng dụng lab**, không phải YAML metadata của bài học:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
~~~

Tên local DC phải khớp metadata Cassandra thật; table/keyspace cần được provision bằng migration hoặc lab setup.

### 6.2. Flow cho payload đã deserialized thành OrderPaidEvent

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class OrderPaidCassandraFlowConfig {

    @Bean
    public IntegrationFlow orderPaidToCassandra(
            OrderPaidToRowMapper mapper,
            ReactiveCassandraOperations operations) {

        return IntegrationFlow.from("validatedOrderPaidEvents")
                .transform(OrderPaidEvent.class, mapper::map)
                .handle(Cassandra.outboundChannelAdapter(
                                operations,
                                CassandraMessageHandler.Type.INSERT),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

Hợp đồng:

- `validatedOrderPaidEvents` nhận **`Message<OrderPaidEvent>`**, không nhận JSON text.
- Transformer chuyển **`OrderPaidEvent` thành `OrderEventRow` có `@Table`**.
- Cassandra outbound adapter với `Type.INSERT` gọi `ReactiveCassandraOperations`, dùng `MappingCassandraConverter` để map entity fields thành CQL row.
- `endpoint.async(false)` yêu cầu endpoint chờ operation trước khi hoàn tất đường xử lý đồng bộ; hữu ích cho test/JMS error propagation nhưng có thể **block thread**.
- Adapter là **một chiều**; không sinh business reply cho caller.

Với `async(true)` mặc định, Cassandra write có thể kết thúc **sau** khi upstream `send()` hoàn tất. Điều đó ảnh hưởng đến nguồn JMS/Kafka acknowledgment, không chỉ hiệu năng.

### 6.3. Nếu input vẫn là JSON String

Tạo một lớp decoder riêng. Với Spring Boot 3/Jackson 2:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

@Component
public class OrderPaidJsonDecoder {

    private final ObjectMapper objectMapper;

    public OrderPaidJsonDecoder(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public OrderPaidEvent decode(String json) {
        if (json == null || json.isBlank()) {
            throw new IllegalArgumentException("JSON input rỗng");
        }
        try {
            return objectMapper.readValue(json, OrderPaidEvent.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Invalid OrderPaid JSON", ex);
        }
    }
}
~~~

Luồng hai lần transform:

~~~java
@Bean
public IntegrationFlow rawJsonOrderPaidToCassandra(
        OrderPaidJsonDecoder decoder,
        OrderPaidToRowMapper mapper,
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("rawOrderPaidJson")
            .transform(String.class, decoder::decode)
            .transform(OrderPaidEvent.class, mapper::map)
            .handle(Cassandra.outboundChannelAdapter(
                            operations, CassandraMessageHandler.Type.INSERT),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Đây là một **flow thay thế** cho mục 6.2 nếu source gửi JSON String. Không đăng ký hai endpoints cùng input channel trong một bài lab rồi kỳ vọng mỗi message chỉ được persist một lần. Nếu inbound HTTP/JMS/Kafka adapter đã chuyển JSON sang DTO, **bỏ qua decoder** và dùng flow mục 6.2.

### 6.4. Gửi message vào flow đúng contract

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderPaidPublisher {

    private final MessageChannel channel;

    public OrderPaidPublisher(
            @Qualifier("validatedOrderPaidEvents") MessageChannel channel) {
        this.channel = channel;
    }

    public void publish(OrderPaidEvent event) {
        boolean accepted = channel.send(
                MessageBuilder.withPayload(event)
                        .setHeader("eventId", event.eventId())
                        .setHeader("sourceSystem", "payment-service")
                        .build());
        if (!accepted) {
            throw new IllegalStateException("Message was not accepted");
        }
    }
}
~~~

Header `eventId` hữu ích cho tracing/routing, nhưng **entity primary key** vẫn do mapper lấy từ `event.eventId()`. Nếu source gửi header mâu thuẫn với payload, cần có chính sách validate; không cho header không đáng tin ghi đè một ID nghiệp vụ.

**Không hiểu `send(true)` là Cassandra write đã commit theo mọi cấu hình.** Với channel/handler bất đồng bộ, boolean chỉ phản ánh bàn giao message theo semantics của channel.

## 7. Mapping chiều đọc: Cassandra row → entity → response DTO

Mapping hai chiều không nhất thiết đối xứng hoàn toàn. Một row có thể thiếu regular column do schema migration hoặc historical data; response DTO có thể che bớt fields nhạy cảm; một event schema version cũ có thể cần upcast trước khi trả về API.

### 7.1. ReactiveCassandraOperations.selectOneById

~~~java
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public final class OrderEventReader {

    private final ReactiveCassandraOperations operations;

    public OrderEventReader(ReactiveCassandraOperations operations) {
        this.operations = operations;
    }

    public Mono<OrderEventRow> findRow(String eventId) {
        if (eventId == null || eventId.isBlank()) {
            return Mono.error(new IllegalArgumentException(
                    "eventId bắt buộc"));
        }
        return operations.selectOneById(eventId, OrderEventRow.class);
    }
}
~~~

`selectOneById` trả **`Mono<OrderEventRow>` hoặc `Mono.empty()`** nếu không có row. `MappingCassandraConverter` map CQL columns thành record constructor properties. **Không tự coi `Mono.empty()` là Cassandra connection failure**; nó có thể là “not found” hợp lệ.

### 7.2. Tạo DTO đọc riêng, tránh lộ payload lưu trữ

~~~java
import java.time.Instant;

public record OrderEventView(
        String eventId,
        String orderId,
        String eventType,
        Instant occurredAt,
        long amountMinor,
        String currency) {
}
~~~

~~~java
public Mono<OrderEventView> findView(String eventId) {
    return operations.selectOneById(eventId, OrderEventRow.class)
            .map(row -> new OrderEventView(
                    row.eventId(),
                    row.orderId(),
                    row.eventType(),
                    row.occurredAt(),
                    row.amountMinor(),
                    row.currency()));
}
~~~

Đây là method fragment trong service có `operations` đã inject. `OrderEventView` **không chứa `payloadJson`**, nên HTTP/API client không tự nhận toàn bộ dữ liệu được lưu trong Cassandra.

### 7.3. Khi cần “not found” có ý nghĩa

~~~java
return operations.selectOneById(eventId, OrderEventRow.class)
        .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Event không tồn tại")));
~~~

Đây là fragment, không phải API error mapping tối ưu cho production. HTTP layer nên chuyển “not found” sang response 404 bằng exception/handler của ứng dụng; còn Cassandra connection timeout phải được phân loại khác và không bị đổi thành 404. Đừng nuốt `DataAccessException` rồi trả `Mono.empty()` cho mọi lỗi.

### 7.4. Projection và cột truy vấn

Nếu client chỉ cần `eventId`, `eventType`, `occurredAt`, tránh luôn `SELECT *` hoặc nạp JSON payload có kích thước lớn. Spring Data Cassandra hỗ trợ projections/`as(...)` trên fluent template API với mapping/limitations theo phiên bản; hoặc chọn CQL columns rõ ràng và map DTO qua `RowMapper`.

Trong Cassandra, `SELECT` còn phải phù hợp **partition key/query pattern**; projection ít cột không biến một truy vấn thiếu partition key thành truy vấn hiệu quả.

## 8. Composite primary key: mapping payload cho bảng timeline

Một schema `event_id PRIMARY KEY` phù hợp lookup theo ID. Nếu use case cần xem lịch sử của một order, có thể thêm bảng:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.events_by_order_month (
    tenant_id text,
    order_id text,
    bucket_month text,
    occurred_at timestamp,
    event_id text,
    event_type text,
    payload_json text,
    PRIMARY KEY (
        (tenant_id, order_id, bucket_month),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Ở đây `tenant_id + order_id + bucket_month` cùng tạo **Cassandra partition key**; `occurred_at` và `event_id` là clustering columns. Vì vậy `@PrimaryKey("event_id")` đơn lẻ **không còn đủ**.

### 8.1. Key class

~~~java
import java.io.Serializable;
import java.time.Instant;
import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public record OrderTimelineKey(
        @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
                type = PrimaryKeyType.PARTITIONED)
        String tenantId,

        @PrimaryKeyColumn(name = "order_id", ordinal = 1,
                type = PrimaryKeyType.PARTITIONED)
        String orderId,

        @PrimaryKeyColumn(name = "bucket_month", ordinal = 2,
                type = PrimaryKeyType.PARTITIONED)
        String bucketMonth,

        @PrimaryKeyColumn(name = "occurred_at", ordinal = 3,
                type = PrimaryKeyType.CLUSTERED,
                ordering = Ordering.DESCENDING)
        Instant occurredAt,

        @PrimaryKeyColumn(name = "event_id", ordinal = 4,
                type = PrimaryKeyType.CLUSTERED,
                ordering = Ordering.ASCENDING)
        String eventId
) implements Serializable {
    private static final long serialVersionUID = 1L;
}
~~~

Record cung cấp `equals/hashCode` theo giá trị và constructor đầy đủ. Spring Data Cassandra documentation yêu cầu composite key mang **value-equality semantics** phù hợp database key equality. Nếu dự án Spring Data cũ không hỗ trợ record key theo cách mong đợi, dùng class `@PrimaryKeyClass` với getters/setters, no-args constructor và `equals/hashCode`, rồi kiểm thử mapping thực tế.

### 8.2. Entity timeline

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_order_month")
public record OrderTimelineRow(
        @PrimaryKey OrderTimelineKey key,
        @Column("event_type") String eventType,
        @Column("payload_json") String payloadJson) {
}
~~~

### 8.3. Mapper phải tính bucket từ event timestamp

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

public final class TimelineRowMapper {

    private static final DateTimeFormatter MONTH =
            DateTimeFormatter.ofPattern("uuuu-MM");

    private TimelineRowMapper() {}

    public static OrderTimelineRow map(
            String authenticatedTenantId,
            OrderEventRow event) {

        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || event == null
                || event.occurredAt() == null) {
            throw new IllegalArgumentException(
                    "Thiếu tenant hoặc event timestamp");
        }

        Instant time = event.occurredAt()
                .truncatedTo(ChronoUnit.MILLIS);
        String month = MONTH.format(time.atOffset(ZoneOffset.UTC));

        OrderTimelineKey key = new OrderTimelineKey(
                authenticatedTenantId, event.orderId(), month,
                time, event.eventId());
        return new OrderTimelineRow(
                key, event.eventType(), event.payloadJson());
    }
}
~~~

Mapper này dùng `authenticatedTenantId` do ứng dụng xác minh từ **source identity/context**, không dùng một header do HTTP client tự điền mà chưa qua authorization. Với hệ multi-tenant, mapping partition key là một phần của **security boundary**.

### 8.4. Vì sao không dùng ngày xử lý làm bucket?

~~~text
Event xảy ra:             2026-11-30T23:59:59Z
Consumer xử lý:           2026-12-01T00:00:05Z
Consumer replay:          2027-01-15T10:00:00Z

Bucket từ occurredAt UTC: 2026-11 trong cả ba lần.
Bucket từ LocalDate.now:  2026-12 hoặc 2027-01 (SAI).
~~~

Nếu một event được redeliver với cùng `eventId` nhưng **bucket khác**, nó sẽ ghi row vào **partition khác**. Điều đó tạo duplicate business event dù input không đổi. Cần dùng **cùng timezone, precision, key schema và hash rules** trên mọi producer/consumer/backfill.

### 8.5. Truy vấn phải đủ partition key

~~~sql
SELECT event_id, occurred_at, event_type
FROM shop_integration.events_by_order_month
WHERE tenant_id = 'tenant-42'
  AND order_id = 'ORD-8001'
  AND bucket_month = '2026-11'
LIMIT 50;
~~~

Chỉ lọc `WHERE tenant_id = ?` trên composite partition key này không xác định một Cassandra partition. Không chữa bằng `ALLOW FILTERING` như đường truy vấn mặc định; thiết kế bảng khác nếu cần query theo tenant mà không biết order/month.

## 9. Mapping Java types thành CQL types

Spring Data Cassandra dùng **driver CodecRegistry** kết hợp Spring converters để map property values. Khi cấu trúc phức tạp, phải kiểm tra Java type và CQL type đúng cặp; chỉ trùng tên field **không đủ**.

| Cassandra type | Java type nên dùng | Lưu ý |
|---|---|---|
| `text`/`varchar` | `String` | Độ dài/payload được validate ở application |
| `int` | `int`, `Integer` | Check range và overflow khi parse JSON |
| `bigint` | `long`, `Long` | Phù hợp minor units khi miền giá trị cho phép |
| `decimal` | `BigDecimal` | Quy tắc scale/rounding phải thuộc contract |
| `boolean` | `boolean`, `Boolean` | Null/missing khác false trong partial update |
| `uuid` | `java.util.UUID` | Không tạo UUID mới khi retry một event đã có ID |
| `timestamp` | `java.time.Instant` | UTC semantics; CQL lưu milliseconds |
| `date` | `java.time.LocalDate` | Không có timezone trong kiểu date |
| `blob` | `java.nio.ByteBuffer` | Không mặc định serialize Java Object |
| `list<text>` | `List<String>` | Cần giới hạn length/size |
| `set<text>` | `Set<String>` | Không có thứ tự logic như List |
| `map<text,int>` | `Map<String,Integer>` | Codec generic types/metadata cần phù hợp |
| `frozen<UDT>` | `@UserDefinedType` hoặc driver `UdtValue` | Chỉ dùng nếu schema/model phù hợp |

### 9.1. Tránh dùng double cho số tiền

~~~java
public record PaymentAmount(long amountMinor, String currency) {}
~~~

Với `VND`, `amountMinor=150000` trong ví dụ có thể biểu diễn 150.000 đơn vị nhỏ nhất theo contract. Nếu business dùng loại tiền có fraction, phải định nghĩa hệ đơn vị và rounding rõ; **không dùng `double` làm phép tính tiền chính xác** chỉ vì CQL hỗ trợ `double`.

### 9.2. Nullable regular fields

Với Java record:

~~~java
@Column("payload_json") String payloadJson
~~~

Nếu `payloadJson` null, Spring Data `INSERT` thường **không đưa null field vào mutation** (xem tài liệu Spring Data template). **UPDATE** và partial update có thể có semantics khác; CQL `NULL` thường tạo tombstone/xóa giá trị cũ, còn driver `UNSET` có thể bỏ qua field trong mutation. Không suy “JSON không gửi field” đồng nghĩa “xóa cột” hoặc ngược lại nếu chưa xác định API/mapper strategy.

Với một incoming PATCH event, tốt hơn dùng DTO **phân biệt missing vs explicit null** và update operation có chủ đích, thay vì map nguyên object đầy null rồi gọi `update(entity)` với kỳ vọng nó tự hiểu partial update.

### 9.3. Collections, UDT, nested JSON

Hai lựa chọn thường gặp:

- **Các cột CQL typed:** dùng `list`/`set`/`map`/`@UserDefinedType` cho dữ liệu cần query/đọc có cấu trúc ổn định.
- **Một `payload_json text` column:** lưu JSON canonical cho audit/khả năng tương thích schema; phải serialize/deserialize ở tầng app và chấp nhận không query tùy ý nội bộ JSON như quan hệ.

Đừng tạo một `Map<String,Object>` gồm mọi kiểu Java rồi mong driver tự chọn codec cho nested object tùy ý. Đặc biệt, **Cassandra JSON syntax** và **JSON String trong một text column** là hai khái niệm khác nhau: `INSERT ... JSON '...'` là CQL feature riêng, không phải mặc định của `CassandraMessageHandler.Type.INSERT`.

## 10. Mapping annotations: khai báo đúng, không đoán từ tên field

| Annotation | Dùng ở đâu? | Tác dụng |
|---|---|---|
| `@Table("order_event")` | Entity class/record | Chọn CQL table |
| `@PrimaryKey("event_id")` | Entity field/record component | Chọn primary key đơn, hoặc field chứa composite key class |
| `@PrimaryKeyClass` | Composite key class | Mô tả nhiều PK columns |
| `@PrimaryKeyColumn` | Key component / flat entity key field | Partitioned/clustered, ordinal, ordering |
| `@Column("amount_minor")` | Entity regular property | Map Java property sang đúng CQL column |
| `@Transient` | Entity field | Loại field khỏi persistence |
| `@CassandraType` | Field/property | Chỉ định CQL type khi auto mapping chưa đủ |
| `@UserDefinedType` | UDT value class | Mapping Cassandra UDT |
| `@Embedded` | Embedded value class | Flatten các property theo rules của mapping |
| `@Version` | Entity field | Optimistic locking theo rules Spring Data Cassandra |

### 10.1. `@Transient` tránh lưu dữ liệu không dành cho Cassandra

~~~java
import org.springframework.data.annotation.Transient;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("demo_event")
public class DemoEvent {

    @PrimaryKey("event_id")
    private String eventId;

    private String eventType;

    @Transient
    private String processingTraceId; // Chỉ dùng trong ứng dụng

    public DemoEvent() {}

    // Getter/setter cho các fields, lược bớt.
}
~~~

Vì các fields thông thường có thể được Spring Data mapping theo convention, chỉ thêm field `processingTraceId` vào entity rồi nghĩ nó không được lưu là rủi ro. `@Transient` biểu thị ý định rõ ràng. Với immutable object/constructor binding, không dùng một transient constructor parameter bắt buộc mà mapper không thể materialize từ row.

### 10.2. `@Version` không thay cho eventId idempotency

Spring Data Cassandra hỗ trợ `@Version` để giúp optimistic locking khi lưu entity có version. Tuy nhiên:

- Đây là version của **persistence entity** theo Spring Data rules, không tự trùng với `schemaVersion` của JSON.
- Không tự gắn với broker offset hoặc JMS sequence.
- Không giải quyết cross-table/partition transaction.
- Khi có concurrent writers, phải kiểm tra thực tế mapping/version handling/LWT trong version Spring Data đang dùng.

**Không dùng cùng một field `schemaVersion` vừa để chọn serializer vừa làm optimistic lock mà không có contract rõ ràng.**

### 10.3. NamingStrategy và migration

Nếu không chỉ rõ `@Column`, Spring Data có thể dựa vào Java property name và `NamingStrategy`. Một quy ước như snake_case rất tiện, nhưng nếu một service dùng `orderId` → `order_id` còn service khác giữ nguyên `orderId`, sẽ có mismatch khó phát hiện.

Đối với integration events và bảng phục vụ nhiều services, **explicit column names** cùng integration test schema là lựa chọn dễ bảo trì. Khi đổi cột, dùng migration/backfill có compatibility window; không sửa annotation trên một deploy rồi kỳ vọng dữ liệu cũ biến đổi tự động.

## 11. Custom conversions: khi Java value object không là native CQL type

`MappingCassandraConverter` có thể dùng các Spring `Converter<S,T>` được **đăng ký tường minh** qua `CassandraCustomConversions`. Nó không tự tìm toàn bộ converters trong classpath để tránh tác động ngoài mong muốn lên cách map các type khác.

### 11.1. Ví dụ value object

~~~java
public record EmailAddress(String value) {
    public EmailAddress {
        if (value == null || !value.contains("@")) {
            throw new IllegalArgumentException("EmailAddress không hợp lệ");
        }
    }
}
~~~

Giả sử một schema dùng CQL `text` để lưu email, nhưng domain model dùng `EmailAddress`. Có thể khai báo converters:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class EmailToString
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}

@ReadingConverter
public final class StringToEmail
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

`@WritingConverter` giúp xác định chiều Java domain type → CQL-compatible value; `@ReadingConverter` giúp xác định chiều DB value → domain type. Với các type primitives có thể tạo converter mơ hồ (`String`→`Long` chẳng hạn), annotation direction đặc biệt quan trọng.

### 11.2. Đăng ký converter đúng cách

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.config.AbstractCassandraConfiguration;
import org.springframework.data.cassandra.core.convert.CassandraCustomConversions;

@Configuration
public class CassandraMappingConfig
        extends AbstractCassandraConfiguration {

    @Override
    protected String getKeyspaceName() {
        return "shop_integration";
    }

    @Override
    public CassandraCustomConversions customConversions() {
        return CassandraCustomConversions.create(config -> {
            config.registerConverter(new EmailToString());
            config.registerConverter(new StringToEmail());
        });
    }
}
~~~

Đây là **một hướng cấu hình thay thế** khi ứng dụng chủ động sở hữu Spring Data Cassandra Java configuration. Nếu Spring Boot đang auto-configure templates/sessions, không tạo thêm `AbstractCassandraConfiguration` vô ý làm phát sinh **duplicate beans/session factories**; tích hợp custom conversions vào cấu hình thực tế của project.

### 11.3. Converter ở mức property

Global converter `String → EmailAddress` có thể ảnh hưởng đến mọi property tương ứng nếu mapping nhận diện type đó. Khi chỉ một field cần định dạng đặc biệt, Spring Data Cassandra có **property-based converters** được đăng ký qua `CassandraCustomConversions.create(...)` và `configurePropertyConversions(...)`.

Chọn một trong hai:

- **Global type converter:** ý nghĩa type ổn định trên nhiều entities.
- **Property-specific converter:** chỉ một cột/field cần encoding/encryption/normalization riêng.

Với encryption, không tự ghi crypto code vào mapper rồi serialize secrets sang text; dùng phương án mã hóa/quản lý keys chuyên biệt và kiểm thử khả năng đọc dữ liệu cũ sau key rotation.

### 11.4. Khi nào nên dùng custom converter?

| Nhu cầu | Cách phù hợp |
|---|---|
 JSON body → OrderPaidEvent | Inbound JSON decoder/message converter |
 OrderPaidEvent → OrderEventRow | Domain Transformer/mapper |
 EmailAddress → Cassandra text | Spring Data custom conversion nếu entity dùng value object |
 CQL Row → read DTO | `CqlTemplate RowMapper` hoặc entity mapping + DTO mapper |
 Type UUID/Instant đã được driver hỗ trợ | Native codec, không tự viết converter không cần thiết |
 Property được mã hóa riêng | Property converter + security design |

**Không nhầm tên giống nhau:** Spring Integration `Transformer` nằm trong integration flow, còn Spring Data `Converter` nằm ở persistence mapping metadata. Chúng hoạt động ở hai tầng và có cách test khác nhau.

## 12. Mapping thủ công bằng CqlTemplate và RowMapper

Đôi khi ứng dụng chỉ đọc vài cột, hoặc dùng query/DTO không phù hợp với một `@Table` entity. `CqlTemplate`/`ReactiveCqlTemplate` hỗ trợ **RowMapper** để chuyển CQL `Row` thành Java result.

### 12.1. Imperative RowMapper

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.data.cassandra.core.cql.CqlOperations;
import org.springframework.stereotype.Repository;

@Repository
public final class EventSummaryDao {

    private final CqlOperations cql;

    public EventSummaryDao(CqlOperations cql) {
        this.cql = cql;
    }

    public List<EventSummary> findById(String eventId) {
        return cql.query(
                "SELECT event_id, event_type, occurred_at "
                + "FROM order_event WHERE event_id = ?",
                (row, rowNum) -> new EventSummary(
                        row.getString("event_id"),
                        row.getString("event_type"),
                        row.getInstant("occurred_at")),
                eventId);
    }
}

record EventSummary(
        String eventId, String eventType, Instant occurredAt) {}
~~~

`CqlOperations.query(String, RowMapper<T>, Object... args)` chuẩn bị/bind `eventId` và map từng Cassandra driver `Row` sang `EventSummary`. Query sử dụng primary key `event_id`, tránh `ALLOW FILTERING`. Với query chỉ mong một row, có thể dùng `queryForObject(...)` với `RowMapper` phù hợp, lưu ý exception/empty cases của overload.

### 12.2. Reactive RowMapper

~~~java
import org.springframework.data.cassandra.core.cql.ReactiveCqlOperations;
import reactor.core.publisher.Flux;

// Fragment trong repository đã inject ReactiveCqlOperations reactiveCql.
Flux<EventSummary> summaries = reactiveCql.query(
        "SELECT event_id, event_type, occurred_at "
        + "FROM order_event WHERE event_id = ?",
        (row, rowNum) -> new EventSummary(
                row.getString("event_id"),
                row.getString("event_type"),
                row.getInstant("occurred_at")),
        eventId);
~~~

`ReactiveCqlOperations` trả `Flux<T>`/`Mono<T>`; **không có subscription thì I/O có thể chưa chạy**. Đừng gọi `collectList()` trên một query không có giới hạn/partition predicate rồi mặc định memory sẽ an toàn.

### 12.3. Entity mapping so với RowMapper

| Tiêu chí | MappingCassandraConverter + entity | RowMapper thủ công |
|---|---|---|
| Table/column metadata | `@Table`, `@Column`, `@PrimaryKey` | Code getter trên driver `Row` |
| Dùng được với template insert | Có | Không tự động |
| Mapping records/domain objects | Tự động theo metadata | Tự xây object |
| Đọc một vài cột không thuộc full entity | Có projection API | Rõ và đơn giản |
| Custom type conversion | `CassandraCustomConversions` | Tự convert hoặc dùng codec |
| Schema migration | Annotation/constructor compatibility | Getter names/types phải cập nhật |
| Spring Integration Type.INSERT | Payload phải là entity | Không dùng RowMapper |

Đừng truyền một `RowMapper` vào `CassandraMessageHandler.Type.INSERT` với kỳ vọng nó map JSON ra database row; endpoint không hoạt động theo contract đó. RowMapper phục vụ **read mapping**, còn write mapping thường dùng entity/statement.

## 13. Ba cách đưa payload vào CassandraMessageHandler

Spring Integration Cassandra (từ **6.0**) hỗ trợ `CassandraMessageHandler` với **`ReactiveCassandraOperations`**. Handler có các mode như `INSERT`, `UPDATE`, `DELETE`, `STATEMENT`, mặc định **asynchronous**; có thể dùng làm outbound adapter một chiều hoặc outbound gateway khi cần reply.

### 13.1. Bảng chọn đúng input contract

| Mode/thiết lập | Input Spring Message payload | Ai làm mapping? | Khi nào nên dùng? |
|---|---|---|---|
| `Type.INSERT` / `Type.UPDATE` / `Type.DELETE` | Một entity có `@Table` | Spring Data Cassandra converter | Domain-driven persistence |
| Entity mode với `List<entity>` | Danh sách entity có mapping | Spring Data batch operations | Nhóm mutations được thiết kế có chủ đích |
| `ingestQuery(...)` | `List<List<?>>`, từng inner list đúng vị trí `?` | App tạo ma trận, handler bind CQL values | Ingest các hàng có query shape cố định |
| `query(...).parameter(...)` | Payload/headers dùng lấy bind values | Parameter expressions + driver | SELECT/STATEMENT với named markers |
| `statementFunction(...)` | DTO hoặc message bất kỳ | App tạo `Statement<?>` từ message | Cần chủ động kiểm soát CQL/values/options |

Không chọn `Type.INSERT` rồi đẩy một JSON `String` vào với kỳ vọng Spring Data biết table/field names. Đầu vào phải được chuyển sang **entity được map** hoặc chọn đúng mode CQL.

### 13.2. Đường 1 — Entity

~~~text
Message<OrderPaidEvent>
    -> .transform(mapper::map)
Message<OrderEventRow @Table>
    -> Cassandra.outboundChannelAdapter(Type.INSERT)
    -> ReactiveCassandraOperations
    -> MappingCassandraConverter
    -> CQL INSERT
~~~

Đây là đường **mặc định dễ bảo trì nhất** khi domain DTO và entity mappings ổn định. `WriteOptions`/`InsertOptions` có thể bổ sung consistency, TTL, timeout và behavior phù hợp operation, nhưng cần được set ở đúng layer/version.

### 13.3. Đường 2 — Ingest query với List<List<?>>

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow ingestOrderEventRows(
        ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("orderEventMatrixInput")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .ingestQuery(
                            "INSERT INTO order_event "
                            + "(event_id, order_id, event_type, "
                            + "schema_version, occurred_at, amount_minor, "
                            + "currency, payload_json) "
                            + "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Tạo một ma trận giá trị:

~~~java
import java.util.List;

// row là OrderEventRow đã validate và normalize.
List<List<Object>> matrix = List.of(
        List.<Object>of(
                row.eventId(),
                row.orderId(),
                row.eventType(),
                row.schemaVersion(),
                row.occurredAt(),
                row.amountMinor(),
                row.currency(),
                row.payloadJson())
);
~~~

Sau đó gửi `Message<List<List<Object>>>` vào `orderEventMatrixInput`. Mỗi inner list chứa **đúng tám giá trị theo thứ tự tám dấu `?`**. `List.of(...)` không chấp nhận null; nếu nguồn có nullable column phải xác định contract/collection và cách bind null/UNSET.

**Không nhầm `List<OrderEventRow>` với `List<List<?>>`.** Hai kiểu payload khác nhau vì handler chạy **entity batch** hay **ingest query**. Cả hai đều có thể tạo nhiều Cassandra mutations, nhưng batch type/retry/partition semantics phải được xem xét riêng.

### 13.4. Đường 3 — statementFunction tạo CQL statement

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow explicitOrderEventStatementFlow(
        ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("orderEventStatementInput")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .statementFunction(message -> {
                        OrderEventRow row =
                                (OrderEventRow) message.getPayload();
                        return SimpleStatement.newInstance(
                                "INSERT INTO order_event "
                                + "(event_id, order_id, event_type, "
                                + "schema_version, occurred_at, amount_minor, "
                                + "currency, payload_json) "
                                + "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                row.eventId(),
                                row.orderId(),
                                row.eventType(),
                                row.schemaVersion(),
                                row.occurredAt(),
                                row.amountMinor(),
                                row.currency(),
                                row.payloadJson());
                    }),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

`SimpleStatement.newInstance(query, values...)` giữ values **tách khỏi CQL syntax**. Với yêu cầu reuse prepared query, có thể gọi `CqlSession.prepare(...)` rồi bind ra `BoundStatement` trong DAO/helper được quản lý; không tự ghép JSON values vào CQL text.

**Mode STATEMENT bypasses entity-to-column mapping cho câu lệnh được tạo thủ công:** bạn phải giữ đúng thứ tự columns, type, null semantics và key fields. Đừng dùng nó chỉ để tránh học `@Table` nếu domain mapping đã đủ.

### 13.5. Nếu chỉ muốn SELECT và cần reply

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow readEventGateway(
        ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("readEventRequests")
            .handle(Cassandra.outboundGateway(operations)
                    .query("SELECT event_id, order_id, event_type "
                           + "FROM order_event WHERE event_id = :eventId")
                    .parameter("eventId", "payload"))
            .channel(c -> c.flux("readEventResults"))
            .get();
}
~~~

`:eventId` là **CQL named marker**; `"payload"` là **Spring Expression Language** truy cập input Spring Message. Gateway có reply; kết quả `STATEMENT` phải được xử lý theo kiểu reply/publisher thực tế của phiên bản Spring Integration/Spring Data, **không giả định luôn nhận `OrderEventRow`** như khi gọi `ReactiveCassandraOperations.selectOneById(...)`.

Nếu cần response DTO được mapping rõ ràng, có thể đặt **service activator** gọi `ReactiveCassandraOperations` rồi `.map(row -> dto)` (mục 7) để kiểm soát contract.

### 13.6. Adapter và gateway không thay thế nhau

| Ý định | Phương án |
|---|---|
 Ghi một chiều, kết thúc bằng Cassandra | Outbound channel adapter + error/ack policy |
 SELECT trả kết quả tới requestor | Outbound gateway hoặc service activator có reply |
 LWT cần xem `[applied]` | Driver/gateway/operations có access tới kết quả condition |
 Chuyển JSON → entity | Transformer trước handler, không phải CQL RowMapper |
 Dùng DTO không có `@Table` | CQL statement/inbound transformer, không đẩy trực tiếp vào entity mode |

Một **one-way adapter** không tạo Spring reply chứa row chỉ vì message input có header `replyChannel`. Với request-reply, phải chọn endpoint và channel có **reply semantics** phù hợp.

## 14. Xử lý payload đa phần tử, batch và partial failures

Nếu input chứa `List<OrderPaidEvent>`, một cách thiết kế rõ ràng là:

~~~text
Message<List<OrderPaidEvent>>
 -> validate từng event + batch-size/bytes + partition boundaries
 -> map từng OrderPaidEvent thành OrderEventRow
 -> Message<List<OrderEventRow>>
 -> Cassandra Type.INSERT (batch operation)
~~~

### 14.1. Ví dụ mapping list

~~~java
import java.util.List;

public List<OrderEventRow> mapBatch(List<OrderPaidEvent> events) {
    if (events == null || events.isEmpty() || events.size() > 10) {
        throw new IllegalArgumentException("Batch lab cần 1..10 events");
    }
    return events.stream()
            .map(mapper::map)
            .toList();
}
~~~

Đây là method fragment trong một component có field `OrderPaidToRowMapper mapper`. Có thể gọi nó từ `.transform(List.class, ...)` với type validation. **Đừng cast bừa một list chứa JSON Strings thành List<OrderPaidEvent>**: Java generics bị type erasure; cần deserialize/validate từng phần tử.

### 14.2. Một Spring list không phải một atomic SQL transaction

Khi handler Cassandra chạy entity batch, Cassandra có **LOGGED/UNLOGGED/COUNTER semantics** riêng và giới hạn theo partition. Một batch multi-partition không tạo SQL-style snapshot isolation; nếu một event invalid, có thể cả batch không xử lý được; nếu lỗi giữa network/coordinator, kết quả có thể chưa rõ.

Chọn batch có chủ đích, giới hạn:

- **Số items, serialized bytes** và số distinct Cassandra partition keys.
- Idempotency của từng mutation.
- Khi nào phải fail cả batch so với tách/quarantine từng item.
- Kiểu batch phù hợp (logged nhỏ cho nhu cầu liên quan; unlogged/independent async writes cho use case khác).
- Retry budget khi broker redeliver cùng list.

**Không dùng một CQL batch lớn để tăng throughput của hàng nghìn events độc lập**. Các writes riêng bất đồng bộ có giới hạn có thể phân bố coordinator load tốt hơn.

## 15. Schema evolution và contract versioning

Khi nguồn bắt đầu gửi event phiên bản 2 có trường `paymentMethod`, đừng chỉ thêm property vào record rồi kỳ vọng Cassandra tự ALTER TABLE. Phải lựa chọn rõ:

1. **Bỏ qua field mới:** nếu persistence không cần lưu.
2. **Lưu vào `payload_json`:** nếu audit/compatibility cần nhưng không query.
3. **Thêm cột CQL và entity field:** migration tạo column trước, code đọc/ghi tương thích, backfill nếu cần.
4. **Tạo bảng/projection mới:** khi query pattern/partition key khác.

### 15.1. Chuỗi triển khai tương thích

~~~mermaid
flowchart TD
    A["Producer v1 đang chạy"] --> B["Migration thêm nullable column"]
    B --> C["Consumer hiểu v1 + v2, mapper versioned"]
    C --> D["Producer gửi v2 có kiểm soát"]
    D --> E["Backfill / reconcile dữ liệu cũ"]
    E --> F["Dọn contract cũ sau retention window"]
~~~

Cassandra không tự thay giá trị null ở mọi row cũ khi thêm cột. `@Column` mới có thể đọc null trên historical data; Java primitive `int`/`long` không biểu diễn null, nên **dùng boxed type** khi cột vắng mặt là trạng thái hợp lệ.

### 15.2. Schema version khác aggregation version

| Trường | Ý nghĩa |
|---|---|
| `schemaVersion` | Phiên bản định dạng JSON/event |
| `aggregateVersion` | Thứ tự thay đổi business state của một order |
| `@Version` của Spring Data | Optimistic locking trên persistence entity |
| Cassandra write timestamp | Conflict resolution của mutation |
| Kafka offset | Vị trí record trong broker partition |

**Không đồng nhất** các phiên bản này. Một order ở aggregate version 17 có thể được gửi dưới JSON schema version 2; write timestamp và Kafka offset vẫn là các tọa độ riêng.

### 15.3. Dữ liệu historical sai kiểu

Nếu `amountMinor` đã từng được lưu dưới dạng `text` trong bảng cũ nhưng ứng dụng mới dùng `bigint`, Spring Data không tự convert mọi row tùy ý. Cần migrate data/table hoặc custom conversion rõ ràng, có integration test đọc dữ liệu cũ và xử lý failures. Tránh “fix” bằng cách bắt tất cả codec exceptions rồi trả zero amount, vì sẽ làm sai dữ liệu tài chính.

## 16. Error handling: lỗi ở lớp nào cần đi đâu?

Một integration flow có thể thất bại ở **deserialize**, **validation**, **domain mapping**, **Spring Data conversion**, **driver codec/CQL** hoặc **Cassandra network/storage**. Phân loại đúng giúp tránh retry các lỗi **không thể tự phục hồi** và giảm nguy cơ acknowledge message nguồn quá sớm.

| Tầng | Ví dụ lỗi | Hướng xử lý |
|---|---|---|
| JSON deserialization | JSON thiếu dấu ngoặc, `Instant` sai format | Quarantine/DLQ, sửa producer contract |
| Domain validation | `eventId` rỗng, `amountMinor <= 0` | Fail fast; không gọi Cassandra |
| Domain mapper | Không serialize được canonical JSON, bucket/tenant bất hợp lệ | Phân loại permanent error; sửa mapping |
| Spring Data converter | Không tìm thấy metadata `@Table`/`@PrimaryKey`, record constructor mismatch | Sửa entity/schema/config |
| Driver codec | Java type không khớp CQL type, unsupported UDT | Sửa schema/type/codec |
| Invalid CQL/schema | Table/column không tồn tại, keyspace sai | Migration/config; retry nguyên dạng vô ích |
| Auth/permission | Cassandra role không có quyền | Sửa ACL/secrets; không retry nóng |
| Timeout/unavailable | Cluster overload, network, replica chậm | Retry có giới hạn nếu idempotent, backoff/reconcile |
| Conditional result | `IF NOT EXISTS` trả applied=false | Phân biệt duplicate hợp lệ và conflict nghiệp vụ |

**Lỗi chuyển đổi dữ liệu khác lỗi Cassandra cluster.** Nếu một poisoned event gửi lặp lại với cùng JSON sai, tăng Kafka consumers/JMS redeliveries không giúp sửa nó. Nên có quota/retry policy riêng cho permanent contract failures.

### 16.1. Spring Integration error channel

Trong Spring Integration, `errorChannel` có thể nhận `ErrorMessage` từ một số endpoint/asynchronous paths. Nhưng đó là **một Spring MessageChannel**, không phải tự động:

- JMS broker DLQ;
- Kafka dead-letter topic;
- Cassandra transaction rollback;
- durable inbox/outbox;
- cơ chế gửi lại event sau process crash.

Nếu source listener transacted dùng `DirectChannel`, transformer/handler đồng bộ ném exception trở về listener, broker **có thể rollback/redeliver theo cấu hình**. Nếu lỗi bị nuốt trong error handler và listener thấy success, broker có thể commit dù Cassandra chưa ghi.

### 16.2. Sync vs async ảnh hưởng tới nguồn

~~~mermaid
sequenceDiagram
    participant JMS as JMS broker
    participant L as Inbound listener
    participant T as Mapper/Transformer
    participant C as Cassandra handler
    participant DB as Cassandra

    JMS->>L: Deliver evt-8001
    L->>T: Spring Message qua DirectChannel
    T->>C: OrderEventRow entity
    C->>DB: INSERT, async=false
    alt Write completed
        DB-->>C: Success
        C-->>L: Handler returns
        L-->>JMS: Commit
    else Conversion/DB error
        C-->>L: Exception propagated
        L-->>JMS: Rollback theo policy
    end
    Note over JMS,DB: Commit Cassandra và JMS không atomic
~~~

Khi dùng `ExecutorChannel`, `QueueChannel` in-memory hoặc Cassandra handler `async=true` mặc định, **source callback có thể kết thúc trước Cassandra completion**. Lỗi Cassandra sau đó **không tự rollback được JMS message đã commit**.

### 16.3. Timeout không chứng minh Cassandra chưa ghi

~~~text
INSERT event_id='evt-8001' được replicas áp dụng.
    -> Response bị mất trên mạng.
    -> Driver báo timeout.
    -> JMS listener rollback, broker giao lại evt-8001.
    -> Mapper phải tạo lại row cùng primary key và values.
~~~

Cassandra regular `INSERT` có **upsert semantics**, không phải SQL unique insert tự từ chối duplicate. Khi cùng `eventId` được retry với cùng payload immutable, idempotency dễ kiểm soát hơn. Nhưng nếu retry thay `occurredAt`, `amountMinor`, `payloadJson` hoặc TTL, kết quả có thể thay đổi; cần một invariant rõ ràng.

### 16.4. Phát hiện duplicate vs conflicting duplicate

Ví dụ:

~~~text
Event đầu: eventId=evt-8001, amountMinor=150000
Retry:     eventId=evt-8001, amountMinor=150000
    -> Có thể là redelivery hợp lệ.

Xung đột:  eventId=evt-8001, amountMinor=250000
    -> Không nên ghi đè âm thầm rồi tuyên bố idempotent.
~~~

Nếu nghiệp vụ yêu cầu “chỉ chấp nhận eventId một lần”, cân nhắc `INSERT ... IF NOT EXISTS`/LWT hoặc inbox/claim strategy thích hợp. Khi `applied=false`, phải kiểm tra row đã tồn tại có cùng nội dung hay không. **LWT không tạo distributed transaction với JMS/Kafka**, và claim ở bảng A rồi ghi timeline ở bảng B vẫn cần reconciliation nếu crash giữa hai thao tác.

### 16.5. Retry budget nhiều tầng

Một event có thể bị retry bởi:

1. Cassandra Java Driver retry policy;
2. application Spring Retry/Resilience4j;
3. JMS broker redelivery hoặc Kafka replay;
4. DLQ replay thủ công;
5. reconciliation job.

Nếu mỗi tầng tự retry vô hạn, tổng writes có thể tăng mạnh khi Cassandra đang quá tải. Hãy giới hạn **attempts, concurrency, backoff, deadline và error classification**. Một error do JSON sai schema nên đi quarantine, không dùng toàn bộ retry budget của database.

## 17. Kiểm soát dữ liệu và security trong mapping

### 17.1. Đừng lưu mọi header/payload không kiểm soát

Headers của một Spring Message có thể chứa:

- JMS/Kafka metadata, correlation ID, reply channel;
- credentials/tokens do gateway hoặc producer đính kèm;
- tracing baggage và thông tin nội bộ;
- user-provided tenant headers không đáng tin.

Không serialize `MessageHeaders` vào `payload_json` hoặc dùng `message.toString()` làm audit record. Chỉ lưu **allowlist fields** đã được phê duyệt và áp chính sách PII/data retention. Logs/traces cũng cần tránh raw JSON chứa dữ liệu nhạy cảm.

### 17.2. Partition key là một security boundary

Nếu hệ multi-tenant dùng `tenantId` trong Cassandra partition key, **phải xác minh tenant từ authenticated identity**, không tin một `tenantId` nằm trong JSON do client gửi. Mapper nên nhận `verifiedTenantId` từ tầng authorization và kiểm tra nó khớp payload/context khi thích hợp.

Không lấy tên keyspace, table hoặc column trực tiếp từ user message rồi nối CQL string:

~~~java
// KHÔNG LÀM: tên bảng do client tự chọn.
String unsafe = "INSERT INTO " + message.getHeaders().get("table") + "...";
~~~

Prepared statements chỉ bind **giá trị** ở các vị trí CQL hỗ trợ; chúng **không** thay thế allowlist và authorization cho database identifiers.

### 17.3. Payload limits và decompression

Một Kafka/JMS event có thể mang JSON lớn hoặc nested arrays sâu. Trước khi deserialize và ghi Cassandra:

- Giới hạn raw message bytes và JSON depth theo công cụ/codec.
- Giới hạn string lengths, số collections/items và serialized row size.
- Kiểm tra charset/encoding nếu nguồn gửi raw bytes.
- Có quota theo tenant/source, tránh một producer chiếm hết memory.
- Tránh đọc toàn bộ bảng Cassandra vào `List` hoặc `collectList()` không giới hạn.

Giới hạn `64 KiB` trong mapper lab chỉ là **một ví dụ**; production thresholds phải được benchmark với Cassandra column/partition size và broker limits.

### 17.4. Transaction và data retention

Giữ `payload_json` như audit record cần xác định TTL, encryption at rest, data minimization và retention policy. **Cassandra TTL không phải thời gian sống của JMS/Kafka message**, cũng không bảo đảm dữ liệu đã biến mất khỏi tất cả backup/snapshot ngay tại thời điểm TTL hết hạn.

## 18. Observability: từ eventId tới Cassandra row

| Tầng | Thông tin nên đo | Vì sao |
|---|---|---|
| Inbound adapter | Received count, source type, bytes | Biết lưu lượng đầu vào |
| Deserialize | Parse error rate, schemaVersion | Phát hiện producer contract drift |
| Domain mapper | Validation failures, normalization latency | Biết event bị loại trước DB |
| Spring transformer | Handler latency, transform error rate | Xác định bottleneck ứng dụng |
| Entity/driver | Codec/mapper exceptions, query type | Phát hiện schema/type mismatch |
| Cassandra driver | In-flight requests, timeouts, retries, p95/p99 | Theo dõi DB pressure |
| Cassandra cluster | Per-node read/write latency, hot partitions, compaction | Đánh giá data model |
| Source broker | JMS queue depth/Kafka lag | Biết downstream chậm tạo backlog |
| Business | Duplicate/conflicting eventId counts | Kiểm soát idempotency |
| DLQ/quarantine | Reasons, oldest event age, replay count | Khôi phục lỗi data contract |

### 18.1. Log thông tin hữu ích nhưng không lộ dữ liệu

Tối thiểu có thể log: `eventId`, `traceId`, logical operation, CQL table alias (không nhất thiết full CQL), schema version, result/exception class, elapsed time. Không log toàn bộ `payloadJson` theo mặc định, đặc biệt khi event chứa thông tin thanh toán hay PII.

Không dùng `eventId` làm metric label cho từng event vì cardinality có thể bùng nổ. Dùng logs/traces cho per-event debugging; metrics aggregate theo source, eventType, error category, environment/region.

### 18.2. Mapping health check

Một health check Cassandra connection thành công **không chứng minh mapper vẫn đúng schema**. Có thể connect nhưng table thiếu cột, record constructor sai, codec mismatch hoặc producer gửi schemaVersion mới chưa hỗ trợ.

Nên có **canary integration test** hoặc smoke test ghi/đọc một row test trên môi trường phù hợp, kiểm tra fields/precision/JSON contract và cleanup theo policy; không ghi row giả vào production table mà không có kế hoạch retention/quyền truy cập.

## 19. Bảng xử lý sự cố mapping

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Adapter báo không tìm thấy mapped entity | Payload là JSON String/Map thay vì `@Table` entity | Decode/transform trước `Type.INSERT` |
| `@Table` import không đúng | Dùng annotation JPA thay Cassandra | Import `org.springframework.data.cassandra.core.mapping.Table` |
| Row thiếu `event_id` hoặc key null | Mapper bỏ eventId/producer thiếu ID | Validate và giữ business eventId |
| Field `orderId` không vào `order_id` | NamingStrategy hoặc thiếu `@Column` | Map tên cột tường minh |
| Timestamp lệch timezone | Đổi `Instant` thành `LocalDateTime` bằng timezone JVM | Dùng UTC Instant và chuẩn hóa precision |
| Row đọc lại khác nanoseconds đầu vào | Cassandra timestamp ở milliseconds | Canonicalize ở mapper trước khi ghi |
| `amountMinor` sai số | Dùng `double`/floating-point, scale không rõ | Dùng `long` minor units hoặc BigDecimal có contract |
| `CodecNotFoundException` | Java type không khớp CQL type | Kiểm tra schema, setter/codec/converter |
| `MappingException`/constructor error | Record fields không khớp row metadata | Sửa annotations/constructor/field names |
| Custom converter không chạy | Chỉ tạo `@Component` nhưng không register | Đăng ký bằng `CassandraCustomConversions` |
| Converter áp sai chiều | Ambiguous String ↔ native types | `@WritingConverter`/`@ReadingConverter` |
| Converter tạo duplicate beans | Thêm config Cassandra thủ công trên Boot auto-config | Dùng một chiến lược cấu hình rõ |
| `@Transient` bị lưu thành field | Import sai/không đánh dấu field | Dùng `org.springframework.data.annotation.Transient` |
| JSON v2 không parse vào DTO v1 | Schema version thay đổi, consumer chưa upcast | Versioned decoder/mapper và compatibility tests |
| Partial update xóa dữ liệu | Missing field bị xử lý như CQL NULL | Phân biệt missing/null/UNSET/update semantics |
| `ReactiveCassandraOperations.insert(...)` không ghi | Không có subscriber | Trả `Mono` cho framework hoặc subscriber phù hợp |
| `send()` true nhưng chưa có row | Handler/channel async | Chờ completion theo ack policy, quan sát error |
| Gateway SELECT không trả `OrderEventRow` | STATEMENT reply không phải entity mapping tự động | Dùng `selectOneById` hoặc mapper trên reply |
| `ingestQuery` thất bại | Matrix thiếu/thừa values, sai thứ tự/codec | Kiểm tra số `?`, row width và types |
| Query theo `orderId` không hợp lệ | Bảng chỉ partition theo `event_id` | Bảng riêng theo query pattern |
| Same event tạo hai timeline rows | Replay dùng bucket/current time khác | Deterministic key từ original `occurredAt` |
| Có dữ liệu conflict sau retry | Cùng eventId nhưng amount/payload khác | Idempotency validation hoặc LWT/inbox |
| JMS không redeliver khi Cassandra error | Source đã ack trước async completion | Durable handoff hoặc chờ completion |
| Kafka lag tăng đột ngột | Cassandra chậm/poison messages | Phân loại lỗi, backpressure, retry budget |
| Logs chứa dữ liệu nhạy cảm | Serialize toàn bộ Spring headers/payload | Field allowlist, masking, retention |

### 19.1. Checklist review trước production

1. **Input contract:** xác định payload đã là DTO, JSON text hay raw bytes.
2. **Schema:** table/keyspace/cột/PK đúng migration hiện tại.
3. **Domain mapper:** validation, schemaVersion, timezone/precision, money types.
4. **Entity:** `@Table`, `@PrimaryKey`, `@Column` và composite key đúng.
5. **Converter:** chỉ đăng ký custom conversion khi cần, không mơ hồ chiều đọc/ghi.
6. **Cassandra handler:** đúng mode `INSERT`/`STATEMENT`/`ingestQuery`.
7. **Reactive:** publisher/subscription, async completion và reply channel được thiết kế.
8. **Error:** poison messages khác DB outages; có DLQ/quarantine và alert.
9. **Idempotency:** eventId/full Cassandra key bất biến qua redelivery/replay.
10. **Security:** verified tenant context, allowlist fields, không lưu secrets/PII dư thừa.
11. **Performance:** kích thước row, partition layout, in-flight concurrency và timeouts.
12. **Tests:** unit mapper + Cassandra integration round-trip + broker failure path.

## 20. Bài thực hành: xây pipeline mapping payload sang Cassandra row

**Môi trường:** Java 17+, Spring Integration Cassandra 6+ và Spring Data Cassandra tương thích; ứng dụng Spring Boot, Cassandra test cluster/Testcontainers. Nếu cần kiểm chứng JMS/Kafka redelivery thì dùng broker test tương ứng. Không thực hiện `TRUNCATE/DROP` hoặc chaos test trên production.

### Bài A — Thiết kế hợp đồng DTO/entity

1. Tạo keyspace `shop_integration` và bảng `order_event` ở mục 3.
2. Tạo `OrderPaidEvent` record với các field từ JSON.
3. Tạo `OrderEventRow` record có `@Table("order_event")`, `@PrimaryKey("event_id")` và `@Column` rõ ràng.
4. Viết bảng mapping JSON field → Java type → CQL column/type.
5. Kiểm tra import đúng annotation Cassandra; không dùng JPA.
6. Thêm một field tracing vào entity lab và thử `@Transient` để tránh persist.

**PASS:** entity metadata khớp schema, key field không null và không lưu field không thuộc persistence contract.

### Bài B — Unit test domain mapper

Tạo event hợp lệ và chạy mapper trực tiếp, **chưa kết nối Cassandra**. Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

class OrderPaidToRowMapperTest {

    private final ObjectMapper objectMapper =
            new ObjectMapper()
                    .registerModule(new JavaTimeModule())
                    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    private final OrderPaidToRowMapper mapper =
            new OrderPaidToRowMapper(objectMapper);

    @Test
    void mapsValidEventAndNormalizesTimestamp() {
        OrderPaidEvent input = new OrderPaidEvent(
                "evt-8001", "ORD-8001", "OrderPaid", 1,
                Instant.parse("2026-11-23T03:00:00.123456789Z"),
                150000, "VND");

        OrderEventRow row = mapper.map(input);
        assertEquals("evt-8001", row.eventId());
        assertEquals("ORD-8001", row.orderId());
        assertEquals(150000, row.amountMinor());
        assertEquals(
                Instant.parse("2026-11-23T03:00:00.123Z"),
                row.occurredAt());
    }

    @Test
    void rejectsInvalidAmount() {
        OrderPaidEvent invalid = new OrderPaidEvent(
                "evt-8002", "ORD-8002", "OrderPaid", 1,
                Instant.parse("2026-11-23T03:00:00Z"),
                -1, "VND");
        assertThrows(
                IllegalArgumentException.class,
                () -> mapper.map(invalid));
    }
}
~~~

Đây là ví dụ với **Jackson 2**/Spring Boot 3.x; Spring Boot 4 dùng Jackson 3 thì cập nhật import/config theo version. Unit test chứng minh **validation và object mapping**, không chứng minh Cassandra driver codecs, primary key/cluster behavior hay schema compatibility.

### Bài C — Cassandra integration round-trip

1. Khởi động Cassandra test container/cluster, provision table `order_event`.
2. Inject `ReactiveCassandraOperations`.
3. Tạo `OrderEventRow` bằng mapper và gọi `operations.insert(row)`.
4. Đảm bảo `Mono` được subscribe bằng `StepVerifier`/test subscriber.
5. Gọi `operations.selectOneById("evt-8001", OrderEventRow.class)`.
6. So sánh tất cả fields sau khi đọc, nhất là `Instant` millisecond và `payloadJson`.
7. Gửi lại cùng event ID, kiểm tra không xuất hiện **row thứ hai** do key khác.

~~~java
// Fragment test đã có "operations" và "row":
reactor.test.StepVerifier.create(
        operations.insert(row)
                .then(operations.selectOneById(
                        row.eventId(), OrderEventRow.class)))
        .assertNext(found -> {
            org.junit.jupiter.api.Assertions.assertEquals(
                    row.eventId(), found.eventId());
            org.junit.jupiter.api.Assertions.assertEquals(
                    row.occurredAt(), found.occurredAt());
        })
        .verifyComplete();
~~~

**PASS:** CQL rows đọc lại đúng entity metadata/type. Không cố chứng minh từ unit mock rằng driver sẽ map đúng mọi field trong Cassandra thật.

### Bài D — Java DSL Transformer và outbound adapter

1. Cấu hình `orderPaidToCassandra` ở mục 6.2.
2. Gửi `Message<OrderPaidEvent>` vào `validatedOrderPaidEvents`.
3. Truy vấn Cassandra bằng `eventId` và xác minh row.
4. Gửi DTO sai `currency`/`amountMinor`, kiểm tra validation fail trước khi gọi Cassandra.
5. Gửi payload sai type `String` vào channel chỉ nhận DTO, ghi nhận transformer conversion error.
6. Chuyển `async(false)` sang async default và so sánh thời điểm `send()` trả về với write completion.

**PASS:** không có JSON String được đưa thẳng vào `Type.INSERT`; hiểu response/error boundary.

### Bài E — JSON decoder và versioned schema

1. Cấu hình flow `rawJsonOrderPaidToCassandra` ở mục 6.3 thay vì flow DTO input.
2. Gửi JSON hợp lệ, xác nhận được deserialize, validate, map, persist.
3. Gửi JSON malformed, timestamp không parse được và `schemaVersion=99`; phân loại lỗi.
4. Viết decoder v2 hiểu thêm `paymentMethod` và tương thích v1.
5. Thử thêm nullable column trong Cassandra trước rồi mới triển khai mapper mới.
6. Đọc row cũ sau migration, kiểm tra không crash khi field mới chưa có.

**PASS:** invalid/unsupported schema events được quarantine theo policy, không biến mọi lỗi thành Cassandra timeout.

### Bài F — Composite key và timeline

1. Tạo bảng `events_by_order_month` ở mục 8.
2. Tạo `OrderTimelineKey` với ba partition columns, hai clustering columns.
3. Chuyển event vào cuối tháng 11 và đầu tháng 12 thành hai `OrderTimelineRow`.
4. Query theo đủ `tenant_id`, `order_id`, `bucket_month`.
5. Replay cùng một event vào tháng 1 năm sau, xác minh bucket vẫn từ original `occurredAt`.
6. Thử header `tenantId` không được xác thực, xác minh mapper không lấy thẳng từ client.

**PASS:** deterministic composite key, không tạo row khác khi redelivery.

### Bài G — RowMapper so với entity mapping

1. Sử dụng `OrderEventReader.findRow(...)` để đọc entity.
2. Sử dụng `EventSummaryDao.findById(...)` để đọc 3 cột bằng CQL RowMapper.
3. Thử `ReactiveCqlOperations.query(...)` và subscribe `Flux<EventSummary>`.
4. Đo thời gian/bytes khi chỉ chọn 3 cột so với lấy cả `payload_json` lớn.
5. Thử một query thiếu partition-key predicate, ghi nhận lỗi/hiệu năng và sửa schema/query.

**PASS:** hiểu trường hợp dùng entity converter, RowMapper và projection; không nhầm RowMapper là outbound Transformer.

### Bài H — Ba mode CassandraMessageHandler

1. Với cùng một `OrderEventRow`, chạy `Type.INSERT` entity mode.
2. Chuyển row thành `List<List<Object>>` và chạy `ingestQuery`.
3. Chạy `statementFunction` trả driver `SimpleStatement` với positional values.
4. Gửi matrix thiếu một value: xác nhận schema/codec/binding error được phát hiện.
5. Gửi JSON String vào entity mode: xác nhận không được tự mapping vào row.
6. Tạo gateway SELECT và quan sát reply type; nếu muốn `OrderEventRow`, dùng `selectOneById` hoặc mapping rõ ràng.

**PASS:** lựa chọn mode dựa vào input contract và chịu trách nhiệm mapping đúng tầng.

### Bài I — Error handling, retry và idempotency

1. Dùng JMS listener transacted hoặc Kafka test consumer có offset policy xác định.
2. Gửi event hợp lệ qua `DirectChannel` + Cassandra handler sync.
3. Mô phỏng Cassandra unavailable, cho exception truyền tới source boundary theo cấu hình.
4. Cho Cassandra ghi thành công nhưng crash trước source commit; broker redeliver cùng `eventId`.
5. Đảm bảo mapper tạo **cùng row** khi replay; kiểm tra event ID không bị thay.
6. Thử cùng `eventId` với amount khác, chuyển thành conflicting duplicate cần điều tra.
7. Dùng async channel/handler để quan sát lỗi Cassandra xảy ra sau khi callback source kết thúc.
8. Thêm DLQ/quarantine/durable handoff phù hợp cho hai loại lỗi khác nhau.

**PASS:** không tuyên bố Cassandra và broker có giao dịch xuyên hệ thống; có cơ chế replay và không nuốt lỗi.

### Ma trận kiểm chứng

| Chủ đề | Kết quả PASS |
|---|---|
| JSON decoder | Đúng type, timestamp, schemaVersion |
| Domain validation | Không ghi event thiếu ID/amount sai |
| Entity mapping | `@Table`/`@PrimaryKey`/`@Column` đúng CQL |
| Nullable & precision | Không làm mất data vì null hoặc timestamp precision |
| Round-trip | Row đọc lại đúng key/value |
| Composite key | Partition/clustering fields đúng thứ tự |
| Spring DSL | Transformer chạy trước Cassandra INSERT |
| Custom conversions | Có đăng ký, đúng chiều reading/writing |
| RowMapper | CQL Row → DTO đúng số cột/type |
| Entity vs ingest | `List<entity>` không nhầm `List<List<?>>` |
| Statement | Values bind, không ghép CQL từ client |
| Async/ack | Completion và error đi đúng ranh giới |
| Idempotency | Giữ eventId và deterministic primary key |
| Security | Không persist untrusted tenant/headers/secrets |
| Migration | Đọc được historical rows sau schema evolution |

## 21. Câu hỏi tự đánh giá

1. Vì sao Cassandra outbound adapter `Type.INSERT` không tự map một JSON String thành CQL row?
2. Spring Message payload khác message headers và Cassandra entity ở đâu?
3. Spring Integration `Transformer` và Spring Data `MappingCassandraConverter` làm việc ở hai tầng nào?
4. `@Table("order_event")` có tác dụng gì? Có thể dùng annotation JPA thay thế không?
5. Vì sao nên khai báo `@Column("amount_minor")` thay vì phụ thuộc hoàn toàn vào naming convention?
6. CQL `event_id text PRIMARY KEY` khác `order_id` regular column ở điểm nào?
7. Cassandra có tự cấp `eventId` như SQL auto-increment khi gọi `insert` không?
8. Vì sao một event redeliver cần giữ nguyên business `eventId`?
9. Lợi ích của việc tách `OrderPaidEvent` khỏi `OrderEventRow` là gì?
10. Có nên lưu toàn bộ Spring Message headers vào `payload_json` không? Vì sao?
11. Tại sao `Instant` cần được chuẩn hóa đến millisecond khi persist CQL timestamp?
12. Cách tính bucket từ `occurredAt` khác gì so với ngày giờ consumer xử lý?
13. Vì sao Java `double` có thể không phù hợp để biểu diễn amount tiền?
14. Một property Java `String` có thể map sang Cassandra `uuid` tự động trong mọi trường hợp không?
15. Khi nào nên dùng `BigDecimal` so với `long amountMinor`?
16. CQL `NULL` và `UNSET` khác nhau thế nào trong partial UPDATE?
17. Vì sao JSON field missing không nên tự suy là “xóa Cassandra column”?
18. Những giới hạn nào cần áp dụng cho raw JSON và row size trước khi ghi?
19. `@PrimaryKeyClass` và `@PrimaryKeyColumn` dùng khi nào?
20. Cassandra partition key và clustering columns ảnh hưởng truy vấn theo order history thế nào?
21. Vì sao composite key cần có `equals/hashCode` phù hợp value equality?
22. Nếu nguồn mang tenantId chưa được xác thực, mapper nên xử lý thế nào?
23. Spring Data `CassandraCustomConversions` có tự tìm converters qua component scan không?
24. `@WritingConverter` khác `@ReadingConverter` ở chiều chuyển đổi nào?
25. Khi nào nên dùng custom type converter, khi nào chỉ cần domain Transformer?
26. `RowMapper` được dùng cho INSERT hay SELECT? Nó map object theo chiều nào?
27. `ReactiveCassandraOperations.selectOneById(...)` trả gì nếu không có row?
28. Vì sao không được nuốt Cassandra timeout rồi trả `Mono.empty()`?
29. Khi nào dùng projection/RowMapper thay vì đọc toàn bộ `payload_json`?
30. `CassandraMessageHandler.Type.INSERT` cần payload có loại metadata nào?
31. `ingestQuery` yêu cầu payload kiểu gì và vì sao thứ tự positional values quan trọng?
32. `statementFunction` nhận Spring Message và trả kiểu gì?
33. Vì sao bind parameters không bảo vệ tên table/column do client cung cấp?
34. Một `List<OrderEventRow>` khác `List<List<?>>` tại handler như thế nào?
35. `Cassandra.outboundChannelAdapter(...)` và `outboundGateway(...)` khác nhau về reply contract ra sao?
36. Vì sao `MessageChannel.send(true)` không luôn chứng minh Cassandra đã ghi xong?
37. `DirectChannel` + handler sync khác `ExecutorChannel` + async về lỗi JMS như thế nào?
38. Lỗi JSON contract và Cassandra `UnavailableException` có nên cùng một retry policy không?
39. Khi cùng `eventId` có payload khác, vì sao không nên coi là duplicate hợp lệ?
40. `@Version` của persistence entity có giống `schemaVersion` JSON không?
41. Đổi CQL column trong migration có đòi hỏi thay entity annotation/transformer không?
42. Vì sao unit test mapper không thể thay thế integration test Cassandra codec/schema?
43. Một Kafka event đã được commit offset trước Cassandra write thất bại cần cơ chế recovery gì?
44. Hãy nêu ba metrics/traces giúp xác định lỗi mapper so với cluster timeout.
45. Những quy tắc nào bảo đảm một event sẽ tạo **cùng Cassandra row key** qua replay?

## 22. Tài liệu tham khảo chính thức

- [Spring Integration — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): `CassandraMessageHandler`, entity payload, `List<entity>`, `ingestQuery`, `statementFunction`, adapter/gateway và async.
- [Spring Data Cassandra — Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `MappingCassandraConverter`, `@Table`, `@PrimaryKey`, `@Column`, `@Transient`, `@PrimaryKeyClass` và composite keys.
- [Spring Data Cassandra — Persisting Entities](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `CassandraTemplate`/`ReactiveCassandraTemplate`, `insert`/`selectOneById`, type conversion, exception translation.
- [Spring Data Cassandra — Custom Conversions](https://docs.spring.io/spring-data/cassandra/reference/cassandra/converters.html): `CassandraCustomConversions`, `@ReadingConverter`/`@WritingConverter` và đăng ký explicit converters.
- [Spring Data Cassandra — Property-based Converters](https://docs.spring.io/spring-data/cassandra/reference/cassandra/property-converters.html): chuyển đổi ở cấp property thay vì toàn type.
- [Spring Data Cassandra API — ReactiveCassandraOperations](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/ReactiveCassandraOperations.html): `insert`, `selectOneById`, `selectOne`, reactive results.
- [Spring Data Cassandra API — CqlTemplate](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/CqlTemplate.html): `query`/`queryForObject`, prepared bind và `RowMapper`.
- [Spring Data Cassandra API — ReactiveCqlOperations](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/ReactiveCqlOperations.html): `Flux`/`Mono` RowMapper và reactive CQL operations.
- [Spring Data Cassandra API — MappingCassandraConverter](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/convert/MappingCassandraConverter.html): object mapping, CQL row → entity và conversion.
- [Spring Integration — Message Transformation](https://docs.spring.io/spring-integration/reference/transformer.html): `Transformer` trong IntegrationFlow.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage` và `errorChannel` theo messaging semantics.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html): lựa chọn partition key/table theo query patterns.
- [Apache Cassandra — CQL Data Types](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html): CQL `timestamp`, `bigint`, `decimal`, `uuid` và collections.
- [Apache Cassandra Java Driver — Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): CQL parameters, codecs, bind và routing metadata.

**Ghi nhớ:** Mapping payload sang Cassandra row có **ít nhất hai bước độc lập**: chuyển dữ liệu transport thành **DTO được validate** và chuyển **DTO thành entity/CQL values có schema rõ ràng**. Với Spring Integration, hãy dùng `Transformer` trước `Cassandra.outboundChannelAdapter(..., Type.INSERT)` để đảm bảo handler nhận **entity `@Table`**; đừng nhầm entity mode với `ingestQuery(List<List<?>>)` hoặc `statementFunction(Statement<?>)`. Spring Data `MappingCassandraConverter` xử lý mapping tên cột, primary key và Java↔CQL types, nhưng **không thay** domain validation, tenant authorization, versioning, idempotency hoặc acknowledgment design với JMS/Kafka. Kiểm thử cả mapping đơn vị lẫn round-trip trên Cassandra thật trước production.







