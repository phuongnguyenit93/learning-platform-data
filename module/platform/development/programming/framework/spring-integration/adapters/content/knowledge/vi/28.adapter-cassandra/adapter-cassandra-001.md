# Cassandra outbound channel adapter

## 1. Bài toán: ghi dữ liệu từ IntegrationFlow vào Cassandra

Một ứng dụng thương mại điện tử nhận sự kiện `OrderPaid` qua HTTP hoặc JMS. Hệ thống cần lưu một bản sao sự kiện để phục vụ tra cứu và đối soát theo `eventId` trong **Apache Cassandra**, rồi tiếp tục xử lý các luồng khác. Nếu viết trực tiếp lệnh CQL ở mọi handler, logic kết nối cơ sở dữ liệu sẽ bị rải rác khắp integration flow, khó thống nhất timeout, xử lý lỗi và khả năng quan sát.

**Cassandra outbound channel adapter** của Spring Integration giải quyết điểm nối này: một `MessageChannel` đưa **Spring Message** tới adapter, và adapter dùng **Spring Data for Apache Cassandra** để thực hiện thao tác lên cluster Cassandra. Đây là một **outbound endpoint một chiều**: nhiệm vụ chính là ghi/thực thi thao tác, **không phát reply nghiệp vụ** trở lại flow.

Trong module **SPRING_INTEGRATION_ADAPTERS**, người học kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`, thực hành hợp đồng message, lỗi và vòng đời kết nối với file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Chương **Adapter Cassandra** mở rộng kiến thức đó sang mô hình dữ liệu phân tán, reactive persistence và những giới hạn giao dịch đặc thù của Cassandra.

**Sau bài này bạn có thể:**

1. Giải thích vai trò của `CassandraMessageHandler`, `ReactiveCassandraOperations` và `Cassandra.outboundChannelAdapter(...)`.
2. Cấu hình một luồng **Spring Message → Cassandra** cho entity đã được map bằng `@Table` và `@PrimaryKey`.
3. Chọn đúng mode `INSERT`, `UPDATE`, `DELETE` hoặc `STATEMENT` và đúng loại payload.
4. Phân biệt **adapter một chiều** với **Cassandra outbound gateway** có reply.
5. Hiểu mặc định **asynchronous**, hậu quả đối với exception, acknowledgment, retry và kết quả ghi.
6. Thiết kế Cassandra keyspace/table, timeout, consistency, idempotency, backpressure và integration test.

## 2. Kiến trúc tổng quan và ranh giới trách nhiệm

~~~mermaid
flowchart LR
    A["HTTP/JMS/File inbound endpoint"] --> B["Transformer + Validator"]
    B --> C["Spring Message<OrderEvent>"]
    C --> D["MessageChannel"]
    D --> E["Cassandra outbound channel adapter"]
    E --> F["CassandraMessageHandler"]
    F --> G["ReactiveCassandraOperations"]
    G --> H["Cassandra driver + CqlSession"]
    H --> I[("Apache Cassandra cluster")]
~~~

| Thành phần | Trách nhiệm | Không tự bảo đảm |
|---|---|---|
| `MessageChannel` | Bàn giao Spring Message giữa các endpoint | Không phải hàng đợi bền vững nếu channel là in-memory |
| `Cassandra.outboundChannelAdapter(...)` | Tạo spec cho outbound handler | Không tạo Cassandra cluster hoặc keyspace |
| `CassandraMessageHandler` | Đọc payload, chọn loại thao tác, gọi API reactive | Không tự là transaction manager cho cả HTTP/JMS/Cassandra |
| `ReactiveCassandraOperations` | Các thao tác Cassandra và mapping entity | Không tự chọn data model tối ưu cho mọi truy vấn |
| `CqlSession`/driver | Kết nối, routing, timeout/consistency ở driver | Không tự thực hiện deduplication nghiệp vụ |
| Cassandra cluster | Lưu dữ liệu theo partition/replica | Không có ACID transaction nhiều bảng theo cách RDBMS |

Spring Integration hỗ trợ **Cassandra outbound channel adapter và outbound gateway từ phiên bản 6.0**. Theo bảng tổng quan endpoint của Spring Integration, module Cassandra **không cung cấp một Cassandra inbound channel adapter riêng** như JDBC polling inbound. Nếu cần phát hiện thay đổi Cassandra để khởi phát flow, phải chọn một kiến trúc khác, chẳng hạn một nguồn sự kiện, CDC phù hợp hoặc poller được triển khai có chủ đích; không bịa ra `Cassandra.inboundAdapter(...)`.

### 2.1. Hành trình của một sự kiện

~~~mermaid
sequenceDiagram
    participant P as Event producer
    participant Flow as Spring Integration flow
    participant Handler as CassandraMessageHandler
    participant Ops as ReactiveCassandraOperations
    participant DB as Cassandra
    P->>Flow: Spring Message<OrderEvent>
    Flow->>Handler: handle()
    Handler->>Ops: INSERT entity (reactive)
    Ops->>DB: CQL write
    DB-->>Ops: Write completion hoặc error
    Ops-->>Handler: Signal thành công/lỗi
    Note over Flow,Handler: Chế độ async quyết định thời điểm caller có thể biết kết quả
~~~

Chú ý: **`MessageChannel.send(...)` trả về thành công không nhất thiết chứng minh Cassandra đã ghi xong.** Đặc biệt khi outbound handler chạy bất đồng bộ, cuộc gọi có thể hoàn tất trước khi CQL operation hoàn thành. Điều này khác với một service dùng `CassandraTemplate` đồng bộ và trực tiếp chờ kết quả.

## 3. Chuẩn bị dependency và môi trường

Ví dụ hướng tới **Spring Integration 6+**, Spring Data for Apache Cassandra tương thích, Java 17+ và Cassandra cluster thử nghiệm. Spring Integration 7+ vẫn có những API cốt lõi đang được trình bày; **không trộn version thủ công** giữa Spring Integration, Spring Data, driver và Spring Boot BOM.

Nếu dùng Spring Boot với BOM, dependency cơ bản:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-cassandra</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
</dependency>
~~~

`spring-integration-cassandra` chứa endpoint integration. Spring Data Cassandra reactive cung cấp `ReactiveCassandraOperations`; driver kết nối cluster qua `CqlSession`. Starter của Spring Boot là một lựa chọn cấu hình tự động; nếu không dùng Boot, phải tạo các bean tương thích cho reactive Cassandra operations và driver.

Một cấu hình Spring Boot minh họa cho **môi trường development local**:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
~~~

Đây là cấu hình **ví dụ ứng dụng Spring Boot**, không phải file YAML metadata của bài học. `datacenter1` phải đúng tên datacenter mà broker Cassandra/test container công bố; không mặc định cluster thật cũng có tên như vậy. Địa chỉ/port, xác thực và TLS cần được quản lý bằng cơ chế cấu hình/secrets thích hợp. Startup của ứng dụng không có nghĩa keyspace/table đã tồn tại.

### 3.1. CQL schema phục vụ đúng kiểu tra cứu

Chọn mục tiêu đơn giản: **ghi và đọc theo `eventId`**. Trên một cluster test, tạo keyspace và table:

~~~sql
-- Chỉ dùng SimpleStrategy cho môi trường thử nghiệm một datacenter/nút.
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    occurred_at timestamp,
    payload_json text
);
~~~

**Tại sao chọn `event_id` làm partition key?** Vì lab chủ yếu kiểm tra một bản ghi bằng `WHERE event_id = ?` và muốn retry cùng event ID được ghi lại ở cùng khóa. Nếu yêu cầu mới là `SELECT ... WHERE order_id = ? ORDER BY occurred_at`, table hiện tại **không tối ưu**. Cassandra được thiết kế theo **query pattern**; cần xây bảng/partition/clustering key khác, không kỳ vọng `ALLOW FILTERING` hoặc index tùy ý giải quyết mọi truy vấn.

Không sao chép `SimpleStrategy` vào production nhiều datacenter; phải chọn replication strategy, replication factor, consistency và topology theo thiết kế vận hành Cassandra thực tế.

### 3.2. Mô hình entity dùng Spring Data Cassandra

~~~java
import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_event")
public record OrderEvent(
        @PrimaryKey("event_id") String eventId,
        @Column("order_id") String orderId,
        @Column("event_type") String eventType,
        @Column("occurred_at") Instant occurredAt,
        @Column("payload_json") String payloadJson) {
}
~~~

`@Table` chỉ bảng Cassandra; `@PrimaryKey` và `@Column` giúp mapping field Java sang tên cột CQL rõ ràng. `Instant` ánh xạ phù hợp với Cassandra `timestamp` theo bộ codec/mapping đang dùng. Record trên là immutable, nên mỗi event có một `eventId` ổn định và payload JSON đã được serialize/validate **trước khi** gửi vào outbound adapter.

Nếu yêu cầu một sự kiện có khóa nghiệp vụ phức hợp, Spring Data Cassandra hỗ trợ `@PrimaryKeyClass`/`@PrimaryKeyColumn` với partition/clustering columns, nhưng cần thiết kế dựa trên truy vấn và kích thước partition; không đặt khóa ngẫu nhiên chỉ để “có composite key”.

## 4. Java DSL: Cassandra outbound channel adapter ghi entity

Spring Integration sử dụng factory:

~~~java
Cassandra.outboundChannelAdapter(reactiveCassandraOperations)
~~~

hoặc overload chỉ định `CassandraMessageHandler.Type`. Trong bài thực hành, **chọn mode `INSERT` tường minh** và đặt `async(false)` để lỗi ghi dễ được quan sát trong cùng lời gọi khi chạy qua channel đồng bộ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;

@Configuration
@EnableIntegration
public class OrderEventCassandraConfig {

    @Bean
    public IntegrationFlow saveOrderEventToCassandra(
            ReactiveCassandraOperations operations) {

        return IntegrationFlow.from("cassandraOrderWrite")
                .handle(Cassandra.outboundChannelAdapter(
                                operations, CassandraMessageHandler.Type.INSERT),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

Ở đây:

- `ReactiveCassandraOperations` là **bean Spring Data Cassandra**, thường có implementation `ReactiveCassandraTemplate`. Adapter **không** nhận trực tiếp `JdbcTemplate`, `CassandraTemplate` imperative hoặc `DataSource`.
- `Cassandra.outboundChannelAdapter(...)` tạo một `CassandraMessageHandler` làm consumer của channel.
- `Type.INSERT` yêu cầu payload là một **entity được map bằng `@Table`**, hoặc một danh sách entity được hỗ trợ; trong ví dụ là `OrderEvent`.
- `endpoint.async(false)` đặt chế độ thực thi handler đồng bộ hơn: Spring Integration gọi `Mono.block()` để chờ thao tác kết thúc. Đây là tùy chọn phù hợp cho **lab và luồng bắt buộc quan sát lỗi đồng bộ**, không phải mặc định hiệu năng tốt nhất.
- Adapter **không phát reply** về Spring `replyChannel`. Nếu cần kết quả `WriteResult`, dùng outbound **gateway** được trình bày ở mục 7.

Không phải cứ có `async(false)` là operation đã trở thành một transaction ACID với HTTP/JMS/DB khác; nó chỉ thay đổi thời điểm caller chờ và nhận tín hiệu hoàn thành của operation Cassandra.

### 4.1. Gửi Spring Message vào input channel

~~~java
import java.time.Instant;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final MessageChannel cassandraOrderWrite;

    public OrderEventPublisher(
            @Qualifier("cassandraOrderWrite") MessageChannel cassandraOrderWrite) {
        this.cassandraOrderWrite = cassandraOrderWrite;
    }

    public void publish(String eventId, String orderId, String json) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        if (json == null || json.isBlank()) {
            throw new IllegalArgumentException("Missing JSON");
        }

        OrderEvent event = new OrderEvent(
                eventId, orderId, "OrderPaid", Instant.now(), json);

        boolean sent = cassandraOrderWrite.send(
                MessageBuilder.withPayload(event)
                        .setHeader("eventType", event.eventType())
                        .setHeader("eventId", event.eventId())
                        .build());
        if (!sent) {
            throw new IllegalStateException(
                    "Spring Message không được bàn giao tới Cassandra endpoint");
        }
    }
}
~~~

Đoạn trên là một service thực tế trong ứng dụng Spring có flow ở mục 4, bean channel tương ứng và Cassandra connection hoạt động. `MessageBuilder` đóng gói `OrderEvent` làm payload; headers phục vụ routing/tracing nhưng **không tự được ghi thành cột Cassandra**. Entity mapping mới xác định các cột được INSERT.

**Không nhầm `send(true)` với “đã ghi bền vững”:** trên một `DirectChannel` và handler `async(false)`, phương thức có thể chỉ kết thúc sau khi operation Cassandra báo hoàn thành, nhưng kết quả vẫn phụ thuộc timeout/consistency và trạng thái cluster. Nếu đổi sang `ExecutorChannel` hoặc bật async, việc gửi trên channel có thể hoàn tất **trước CQL write**.

### 4.2. Payload đúng và payload sai

| Payload Spring Message | Mode adapter | Hệ quả |
|---|---|---|
| `OrderEvent` có `@Table` | `INSERT` | Spring Data map entity sang CQL INSERT |
| `List<OrderEvent>` | `INSERT` | Có thể thực hiện operation batch theo Spring Data |
| `String` JSON chứa event | `INSERT` | **Không mặc định** parse JSON thành entity; cần transformer |
| `Map<String,Object>` | `INSERT` | Không phải entity đã map trong ví dụ; không giả định tự thành bảng |
| `Statement<?>` của driver | `STATEMENT` | Thực thi statement tùy chỉnh, không dùng entity mapping của INSERT |
| `List<List<?>>` | `ingestQuery(...)` | Được diễn giải là ma trận các dòng tham số cho ingest CQL |

Nếu inbound đến từ HTTP/JMS với payload JSON `String`, hãy **deserialize/validate** ở transformer trước khi đưa tới Cassandra endpoint:

~~~java
// Fragment trong IntegrationFlow; objectMapper đã được inject.
.transform(String.class, json -> {
    try {
        return objectMapper.readValue(json, OrderEvent.class);
    } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
        throw new IllegalArgumentException("OrderEvent JSON không hợp lệ", ex);
    }
})
.channel("cassandraOrderWrite")
~~~

Đây là fragment, không phải một flow Java hoàn chỉnh. Sử dụng `OrderEvent` trực tiếp trong `MessageChannel` sẽ tránh serialize/deserialize lại không cần thiết khi hệ thống bên trong JVM đã có DTO.

## 5. INSERT, UPDATE, DELETE và STATEMENT: chọn đúng mode

`CassandraMessageHandler.Type` có **bốn giá trị**: `INSERT`, `UPDATE`, `DELETE` và `STATEMENT`.

| Mode | Payload dự kiến | Mục đích | Cảnh báo |
|---|---|---|---|
| `INSERT` | Một entity `@Table` hoặc danh sách entity | Ghi dữ liệu theo mapping | Cassandra INSERT thông thường có **upsert semantics** |
| `UPDATE` | Một entity `@Table` hoặc danh sách entity | Cập nhật dữ liệu từ entity | Không mặc định có optimistic locking/compare-and-set |
| `DELETE` | Một entity `@Table` hoặc danh sách entity | Xóa dữ liệu dựa trên mapping/key | Cassandra tạo tombstones; cần kiểm soát quy mô delete |
| `STATEMENT` | `Statement<?>` hoặc kết quả của query/expression/processor | Thực thi CQL statement tùy biến | CQL phải có bind values và được giới hạn theo nghiệp vụ |

Ví dụ đổi mode của một adapter:

~~~java
// Fragment: một flow khác dành riêng cho DELETE.
.handle(Cassandra.outboundChannelAdapter(
        operations, CassandraMessageHandler.Type.DELETE),
        endpoint -> endpoint.async(false))
~~~

Không đổi mode của cùng một handler singleton theo header tùy ý trong lúc nhiều message đang được xử lý. Nếu cần một flow cho insert và một flow cho delete, dùng **router** đưa Spring Message tới các channels/handlers riêng với contract rõ.

### 5.1. Cassandra INSERT là upsert, không phải “insert if absent”

Với câu lệnh thường:

~~~sql
INSERT INTO shop_integration.order_event (
    event_id, order_id, event_type, occurred_at, payload_json
) VALUES (
    'evt-1501', 'ORD-1501', 'OrderPaid',
    '2026-11-23T03:00:00Z', '{"eventId":"evt-1501"}'
);
~~~

Gửi lại cùng `event_id` có thể **ghi đè/hoà nhập giá trị cột** theo timestamp write và Cassandra last-write-wins rules. **Không mặc định** Cassandra từ chối bản ghi trùng như một database quan hệ với unique constraint và `INSERT` lỗi khi khóa đã tồn tại.

Nếu nghiệp vụ bắt buộc **chỉ ghi khi chưa tồn tại**, cần dùng **lightweight transaction**/conditional CQL `IF NOT EXISTS` hoặc một chiến lược idempotency có phân tích consistency/race phù hợp, và theo dõi `[applied]`. Đổi adapter sang `INSERT` thông thường **không tự bật LWT**.

### 5.2. UPDATE và DELETE cũng cần khóa

Cassandra `UPDATE` có thể tạo row mới khi key chưa tồn tại, tùy câu lệnh và dữ liệu; không suy ra một operation UPDATE đơn giản có nghĩa “chỉ sửa row đang có”. DELETE tạo tombstones và có đặc tính lưu/compaction; xóa hàng loạt theo partition key là một quyết định thiết kế, không chỉ là “xóa khỏi RAM”.

Với việc thay trạng thái đơn, cần xem **mô hình last-write-wins và trình tự event**; nếu `OrderCancelled` đến trước `OrderPaid` do bất đồng bộ, upsert theo event có thể làm trạng thái bị lùi. Dùng version/guard hoặc LWT khi yêu cầu so sánh–ghi nguyên tử đối với một partition.

## 6. Ingest query: gửi nhiều dòng qua ma trận giá trị

`CassandraMessageHandler.setIngestQuery(...)` và Java DSL `ingestQuery(...)` kích hoạt cách nhập bằng một CQL INSERT có placeholders. Theo tài liệu Spring Integration, payload khi đó phải là **`List<List<?>>`**, mỗi inner list biểu diễn một hàng giá trị tương ứng với thứ tự các dấu hỏi trong CQL.

Ví dụ:

~~~java
@Bean
public IntegrationFlow bulkOrderEventIngest(
        ReactiveCassandraOperations operations) {

    String cql = """
            INSERT INTO order_event
              (event_id, order_id, event_type, occurred_at, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """;

    return IntegrationFlow.from("cassandraBulkWrite")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .ingestQuery(cql),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Giả sử đã có keyspace mặc định `shop_integration` trên Cassandra session. Payload gửi tới `cassandraBulkWrite`:

~~~java
import java.time.Instant;
import java.util.List;

List<List<?>> rows = List.of(
    List.of("evt-1501", "ORD-1501", "OrderPaid",
            Instant.parse("2026-11-23T03:00:00Z"), "{\"eventId\":\"evt-1501\"}"),
    List.of("evt-1502", "ORD-1502", "OrderPaid",
            Instant.parse("2026-11-23T03:01:00Z"), "{\"eventId\":\"evt-1502\"}")
);

cassandraBulkWrite.send(MessageBuilder.withPayload(rows).build());
~~~

`cassandraBulkWrite` là một `MessageChannel` đã được inject, và `MessageBuilder` có import từ Spring Messaging như phần trước. **Số phần tử mỗi inner list phải khớp số placeholders**; tất cả giá trị phải có codec/type Cassandra hỗ trợ. Nếu cần nullable field, không dùng `List.of(...)` cho danh sách có `null` (Java không chấp nhận).

**Cảnh báo về batch:** Cassandra batch không phải công cụ nén toàn bộ một file CSV hàng triệu row thành một transaction nhanh hơn. Batch qua nhiều partition có thể tốn nhiều tài nguyên coordinator và ảnh hưởng throughput. Cần chunk nhỏ, kiểm soát memory, concurrency và quan sát p95 latency; batch chỉ nên dùng khi nghiệp vụ/driver hỗ trợ rõ ràng. `ingestQuery` không biến Cassandra thành một cơ sở dữ liệu có ACID transaction đa partition.

## 7. STATEMENT: tự tạo CQL an toàn và phân biệt outbound gateway

Mode `STATEMENT` cho phép kiểm soát CQL cụ thể mà Spring Data entity mapping không biểu đạt đủ. Có ba hướng được `CassandraMessageHandler` hỗ trợ:

1. **`query(String)`** kèm `parameter(...)` để bind các tham số có tên.
2. **`statementExpression(...)`** dùng SpEL trả về đối tượng driver `Statement<?>`.
3. **`statementFunction(...)`** tạo `Statement<?>` từ Spring Message bằng Java function.

### 7.1. Statement function dùng bind values, không nối chuỗi đầu vào

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow writeOrderEventStatement(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("cassandraStatementWrite")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .statementFunction(message -> {
                        OrderEvent event = (OrderEvent) message.getPayload();
                        return SimpleStatement.newInstance(
                                "INSERT INTO order_event "
                                + "(event_id, order_id, event_type, occurred_at, payload_json) "
                                + "VALUES (?, ?, ?, ?, ?)",
                                event.eventId(),
                                event.orderId(),
                                event.eventType(),
                                event.occurredAt(),
                                event.payloadJson());
                    }),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

`SimpleStatement.newInstance(String, Object...)` dùng **bind values** thay cho việc nối dữ liệu từ HTTP/JMS vào chuỗi CQL. Điều này giảm nguy cơ injection đối với **giá trị**, đồng thời giúp driver quản lý type/codec. **Tên keyspace/table/cột không nên được ghép từ user input**; chỉ cho phép identifiers đã định nghĩa trước.

Nếu cần sử dụng DataStax Java Driver `QueryBuilder`, có thể tạo statement bằng builder và truyền thẳng làm payload hoặc trả về từ `statementFunction(...)`. Với nghiệp vụ thông thường, Spring Data entity mapping đơn giản và dễ kiểm soát hơn việc tự sinh mọi câu CQL.

### 7.2. CQL query có named parameters

~~~java
// Fragment trong IntegrationFlow; chỉ dùng khi cần mode STATEMENT.
.handle(Cassandra.outboundChannelAdapter(operations)
        .query("INSERT INTO order_event "
             + "(event_id, order_id, event_type) "
             + "VALUES (:eventId, :orderId, :eventType)")
        .parameter("eventId", "payload.eventId")
        .parameter("orderId", "payload.orderId")
        .parameter("eventType", "payload.eventType"),
        endpoint -> endpoint.async(false))
~~~

Theo Spring Integration, **`.query(...)` tự chọn mode `STATEMENT`**, và `.parameter(...)` cung cấp biểu thức đánh giá giá trị từ Spring Message. Đây là **bind value** theo tên; tránh nối chuỗi CQL với giá trị chưa được validate.

**Đừng dùng các tham số ở chế độ khác rồi mong chúng có tác dụng:** `parameterExpressions` được dùng cùng `query(String)`, không phải với entity `INSERT` mặc định hay một driver `Statement` đã tự build.

### 7.3. Outbound adapter khác outbound gateway ở điều gì?

Một handler `CassandraMessageHandler` có thể chạy hai vai trò:

| Yêu cầu | Endpoint nên chọn | Kết quả trên Spring MessageChannel |
|---|---|---|
| Chỉ cần gửi entity để ghi, không cần reply | `Cassandra.outboundChannelAdapter(...)` | Không chủ động tạo Spring reply |
| Muốn đọc kết quả ghi hoặc SELECT | `Cassandra.outboundGateway(...)` | Tạo reply theo operation |
| Muốn kết quả synchronous để điều khiển nghiệp vụ | Gateway `async(false)` | Kết quả operation được đợi và trả về cho flow |
| Muốn duy trì xử lý reactive end-to-end | Gateway async và `FluxMessageChannel` phù hợp | Publisher/reply được xử lý theo reactive flow |

Gateway ví dụ trả kết quả INSERT:

~~~java
@Bean
public IntegrationFlow writeOrderEventWithReply(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("cassandraWriteRequests")
            .handle(Cassandra.outboundGateway(operations,
                            CassandraMessageHandler.Type.INSERT),
                    endpoint -> endpoint.async(false))
            .channel("cassandraWriteResults")
            .get();
}
~~~

Theo tài liệu Spring Integration, ở chế độ **gateway async**, Cassandra handler tạo `Mono<WriteResult>` và cách xử lý tiếp phụ thuộc loại `MessageChannel`; với `async(false)`, handler có thể gọi `Mono.block()` để lấy kết quả. Với reactive pipeline thực sự, `FluxMessageChannel` thường phù hợp hơn channel blocking. Đây là **luồng gateway thay thế** cho adapter mục 4, không nên gắn hai endpoint vào cùng một input channel khi chỉ muốn một lần ghi.

**Lưu ý:** gateway không biến kết quả thành một giao dịch phân tán hay bảo đảm “exactly once”; `WriteResult` phản ánh completion của operation Cassandra theo driver/session/consistency, cần đọc theo API và operation cụ thể.

## 8. XML namespace và cấu hình Java thuần

Spring Integration còn có XML namespace `int-cassandra`. Để dùng XML, phải khai báo đúng namespace/XSD cho version đang sử dụng và tạo bean `ReactiveCassandraOperations`.

~~~xml
<int:channel id="cassandraOrderWrite"/>

<int-cassandra:outbound-channel-adapter
        id="orderEventCassandraWriter"
        channel="cassandraOrderWrite"
        cassandra-template="reactiveCassandraTemplate"
        mode="INSERT"
        async="false"
        auto-startup="true"/>
~~~

Đây là fragment: cần namespace `int` và `int-cassandra`, bean tên `reactiveCassandraTemplate` thực sự triển khai `ReactiveCassandraOperations` và một Cassandra session đã cấu hình. Trong XML, thuộc tính `cassandra-template` tham chiếu template/operations **reactive**; đừng truyền `CassandraTemplate` đồng bộ chỉ vì tên thuộc tính nghe giống nhau.

Nếu ứng dụng dùng Spring Boot auto-configuration, tên bean có thể khác ví dụ; cần đặt tham chiếu theo tên bean thực tế. Chỉ đăng ký Java DSL **hoặc** XML cho cùng writer, tránh hai consumer vô tình thực hiện cùng operation.

### Java cấu hình trực tiếp không dùng DSL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.messaging.MessageHandler;

@Bean
@ServiceActivator(inputChannel = "cassandraOrderWrite")
public MessageHandler cassandraOrderWriter(
        ReactiveCassandraOperations operations) {

    CassandraMessageHandler handler = new CassandraMessageHandler(
            operations, CassandraMessageHandler.Type.INSERT);
    handler.setAsync(false);
    return handler;
}
~~~

Ở đây `@ServiceActivator` đưa message của channel `cassandraOrderWrite` tới handler. Đây là **phương án thay thế** cho `Cassandra.outboundChannelAdapter(...)` trong Java DSL; cả hai đều sử dụng `CassandraMessageHandler`. Không tự tạo một bean `MessageHandler` mà quên đăng ký consumer trên channel, nếu không Spring Message có thể không có nơi xử lý.

## 9. Bất đồng bộ, reactive execution và đường báo lỗi

`CassandraMessageHandler` dùng `ReactiveCassandraOperations` và theo tài liệu Spring Integration **mặc định `async=true`**. Điều này ảnh hưởng lớn tới cách ứng dụng biết operation đã ghi thành công hay gặp lỗi.

### 9.1. So sánh hai chế độ

| Tình huống | `async=true` (mặc định) | `async=false` |
|---|---|---|
| Luồng thực thi | Hướng bất đồng bộ/reactive | Handler chờ kết quả reactive operation |
| Caller trên `DirectChannel` | Có thể kết thúc trước Cassandra completion | Có thể thấy lỗi operation trong cùng đường gọi |
| Throughput | Giảm thời gian chặn thread nhưng cần giới hạn in-flight | Dễ reasoning hơn, thread có thể chờ DB lâu |
| Error handling | Kết quả/lỗi đến sau cần một đường quan sát lỗi phù hợp | Exception có thể đi ngược lên channel caller đồng bộ |
| Tương tác với transaction nguồn | Không tự giữ transaction nguồn đang mở tới lúc Cassandra ghi xong | Vẫn không có distributed transaction với Cassandra |
| Use case | Reactive pipeline và tải cao được quản lý tốt | Lab, migration đơn giản, cần completion đồng bộ |

Tài liệu Spring Data Cassandra nhấn mạnh **publisher reactive là lazy**: tạo `Mono`/`Flux` chưa thực hiện I/O cho đến khi có subscription. Spring Integration handler đảm trách việc tích hợp publisher với endpoint. Nếu tự dùng `ReactiveCassandraTemplate.insert(entity)` trong code riêng, **phải có một subscriber thực sự**; gọi API rồi bỏ quên `Mono` sẽ không lưu dữ liệu.

### 9.2. Timeout không chứng minh ghi thất bại

Giả sử cluster đã xử lý một INSERT nhưng client mất kết nối trước khi nhận thành công. Caller có thể thấy timeout, retry, rồi gửi cùng event lần hai. Vì vậy:

- Với Cassandra upsert bình thường, dùng **primary key ổn định** và dữ liệu immutable cho sự kiện để giảm tác hại khi gửi trùng.
- Nếu cần chỉ-ghi-một-lần, dùng conditional write/LWT đúng phạm vi partition và kiểm tra trạng thái `[applied]`.
- Nếu lỗi xảy ra sau khi nguồn JMS/Kafka đã acknowledge/commit, không thể giả định tăng retry ở Cassandra endpoint sẽ tạo giao hàng đúng-một-lần.
- Không chỉ log `MessageChannel.send()==true` rồi báo nghiệp vụ “đã lưu” khi endpoint đang async.

### 9.3. `errorChannel`, exception và nguồn message

Lỗi mapping entity, CQL syntax, timeout, authentication hoặc unavailable có thể xảy ra:

1. **Trước khi reactive operation được lập lịch**, ví dụ payload sai kiểu hoặc cấu hình query thiếu.
2. **Khi operation được thực thi**, ví dụ Cassandra unavailable hoặc write timeout.
3. **Sau khi Cassandra đã áp dụng operation nhưng client không nhận confirmation**, tạo trạng thái không chắc chắn.

Với handler sync và đường `DirectChannel`, exception có thể truyền về inbound endpoint. Với handler async hoặc `ExecutorChannel`, lỗi có thể xuất hiện sau khi upstream đã trả thành công; cần cấu hình **error channel, monitoring hoặc reactive error handling** phù hợp, và integration test để xác nhận lỗi thực sự được ghi nhận trong phiên bản đang dùng.

**Không kết luận `errorChannel` tự retry hay tự tạo DLQ.** Nó là Spring Integration channel vận chuyển `ErrorMessage`, không phải transaction, queue broker hoặc recovery strategy. Không xử lý exception rồi bỏ qua nó nếu đó là lỗi phải khắc phục.

## 10. `WriteOptions`: TTL, consistency, timeout và idempotency

`CassandraMessageHandler` cho phép chỉ định `WriteOptions` của Spring Data Cassandra, thường dùng với `INSERT`, `UPDATE` hoặc `DELETE`. Đây là cấu hình **cho database write**, không giống JMS `timeToLive`, HTTP timeout hoặc Spring `MessageChannel.sendTimeout`.

### 10.1. Ví dụ đặt TTL cho bản ghi thử nghiệm

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.cql.WriteOptions;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;

@Bean
public WriteOptions demoEventWriteOptions() {
    return WriteOptions.builder()
            .ttl(Duration.ofDays(7))
            .build();
}

@Bean
public IntegrationFlow eventWriteWithTtl(
        ReactiveCassandraOperations operations,
        WriteOptions demoEventWriteOptions) {

    return IntegrationFlow.from("cassandraTtlWrite")
            .handle(Cassandra.outboundChannelAdapter(
                            operations, CassandraMessageHandler.Type.INSERT)
                    .writeOptions(demoEventWriteOptions),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Đây là **một flow thay thế** ví dụ cơ bản, không phải yêu cầu ghi cùng event hai lần. Cassandra TTL quy định thời gian sống của các cell được ghi (tùy thao tác và schema), không phải “tự xóa row đúng tức khắc sau bảy ngày” như một lịch xóa tác vụ. Expired data có tombstones và compaction behavior; rất nhiều TTL khác nhau cũng có thể tăng chi phí vận hành.

**Đừng đặt TTL tùy ý cho sự kiện thanh toán, audit hoặc dữ liệu cần đối soát dài hạn.** Retention phải được duyệt theo hợp đồng dữ liệu và chính sách lưu trữ.

### 10.2. Consistency level và timeout

Cassandra dùng **consistency level** như `ONE`, `LOCAL_QUORUM` hoặc các lựa chọn khác để xác định yêu cầu phản hồi từ replicas trong phạm vi replication topology. `WriteOptions` hoặc execution profile của DataStax driver có thể mang consistency/timeout; lựa chọn hợp lý phụ thuộc keyspace replication, local datacenter và SLA.

| Thiết lập | Hỏi gì trước khi chọn? | Điều không được suy ra |
|---|---|---|
| `ConsistencyLevel.ONE` | Ứng dụng chấp nhận mức bảo đảm đọc/ghi nào? | Không có nghĩa dữ liệu đã đồng bộ đến mọi replica |
| `LOCAL_QUORUM` | Mỗi DC có bao nhiêu replica? Đọc và ghi theo consistency nào? | Không tự tạo giao dịch ACID giữa các partition |
| Request timeout | Mạng/cluster có p99 bao nhiêu? Có retry không? | Timeout **không chứng minh** server chưa ghi dữ liệu |
| Cassandra TTL | Dữ liệu cần lưu bao lâu? | TTL không phải độ trễ của operation |
| Idempotent execution flag | Câu lệnh có an toàn để driver retry không? | Gắn flag không biến mọi INSERT/UPDATE thành business idempotent |

Sơ đồ khái niệm (không phải đặc tả mọi consistency):

~~~mermaid
flowchart LR
    C["Client gửi write CL=LOCAL_QUORUM"] --> K["Coordinator"]
    K --> R1[("Replica 1")]
    K --> R2[("Replica 2")]
    K --> R3[("Replica 3")]
    R1 --> K
    R2 --> K
    K --> A["Trả thành công khi đủ replica xác nhận"]
~~~

Trong trường hợp mô hình ba replica trong một local DC, `LOCAL_QUORUM` thường cần đủ hai replica phản hồi. Nếu kiến trúc multi-DC, phân phối và replication khác thì phải tính lại theo topology thực tế. `CL=QUORUM/LOCAL_QUORUM` không thay cho việc xem xét conflict resolution, timestamp hay event ordering.

### 10.3. Thao tác có tính điều kiện: `IF NOT EXISTS`

Khi cần **chỉ tạo bản ghi một lần** theo primary key, có thể dùng CQL:

~~~sql
INSERT INTO order_event (
    event_id, order_id, event_type, occurred_at, payload_json
) VALUES (?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

Đây là **lightweight transaction (LWT)** của Cassandra, không giống SQL `BEGIN/COMMIT` tổng quát. Operation có thể trả về thông tin `[applied]`; cần đọc kết quả qua gateway/driver để biết câu lệnh đã thực sự áp dụng hay đã có row trước đó.

LWT có chi phí điều phối/độ trễ cao hơn so với write thông thường. Không bật cho mọi event chỉ vì tên gọi “transaction”; nếu use case chỉ cần cùng `eventId` ghi lại **cùng nội dung bất biến**, upsert có primary key ổn định đôi khi là thiết kế hợp lý hơn, sau khi đánh giá đúng ngữ nghĩa nghiệp vụ.

## 11. Khi nguồn là JMS/Kafka: vì sao cần idempotent write?

Một integration flow có thể là:

~~~mermaid
flowchart LR
    A[("JMS hoặc Kafka")] --> B["Inbound adapter"]
    B --> C["Validate và transform"]
    C --> D["Cassandra outbound adapter"]
    D --> E[("Cassandra order_event")]
    B -. "Ack/offset commit thuộc source" .-> A
~~~

**Nguồn message và Cassandra là hai hệ thống có transaction/acknowledgment riêng.** Bật JMS session transacted, Kafka manual acknowledgment hoặc handler `async(false)` không tự hình thành một transaction phân tán nguyên tử giữa nguồn và Cassandra.

### 11.1. Hai cửa sổ lỗi

| Trình tự | Nguy cơ | Thiết kế đối phó |
|---|---|---|
| **Cassandra write xong → ứng dụng crash → JMS ack/Kafka offset chưa commit** | Source có thể phát lại cùng event | Dùng primary key `eventId` ổn định và thao tác idempotent |
| **Source ack/commit → Cassandra async write lỗi** | Source có thể không tự phát lại; sự kiện chưa lưu | Chọn acknowledgment boundary đúng hoặc durable handoff |
| **Cassandra timeout nhưng thực tế đã ghi** | Retry gửi thêm operation | Upsert dữ liệu bất biến hoặc LWT/guard tùy contract |
| **Event v2 xử lý trước v1** | Bản ghi state có thể bị ghi lùi | Version, ordering theo partition key hoặc conditional write |

Nếu dùng `JMS message-driven inbound adapter` với `DirectChannel` và Cassandra handler `async(false)`, một số exception đồng bộ có thể truyền về JMS listener để rollback message. Điều này **giúp** nhưng không tạo atomic commit hai tài nguyên; Cassandra write đã xảy ra vẫn có thể bị lặp khi JMS commit thất bại.

Nếu chuyển sang `ExecutorChannel` hoặc handler Cassandra mặc định async, JMS listener có thể kết thúc/commit trước khi Cassandra write thật hoàn thành. Khi đó lỗi ở DB về sau **không tự động rollback được source JMS message**. Cần thiết kế retry và durable handoff riêng, hoặc thay đổi ranh giới để source chỉ ack sau completion khi hạ tầng hỗ trợ.

### 11.2. Chống trùng hợp đồng event

Contract JSON có thể gồm:

~~~json
{
  "eventId": "evt-1501",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "orderId": "ORD-1501",
  "occurredAt": "2026-11-23T03:00:00Z"
}
~~~

Thực hiện:

1. Xác thực schema, trường bắt buộc và quyền producer.
2. Giữ `eventId` **không đổi** qua retry/redelivery/replay.
3. Dùng `eventId` làm partition key trong bảng **lưu sự kiện bất biến** như ví dụ.
4. Đảm bảo cùng `eventId` không đi kèm nội dung thay đổi ngoài ý muốn; nếu conflict, đánh dấu lỗi contract.
5. Với bảng **state theo orderId**, cân nhắc `aggregateVersion` hoặc conditional update để không ghi lùi state.

Một write “idempotent về dữ liệu” và một operation “idempotent ở tầng driver” là hai tiêu chí khác nhau. Ví dụ tăng counter `value = value + 1` thường **không an toàn khi retry mù quáng**, dù cùng event ID có trong payload. Phải xét tác động thực tế của CQL.

## 12. Backpressure, concurrency và batch trong hệ thống tải cao

### 12.1. Reactive không đồng nghĩa vô hạn tải

Vì dùng `ReactiveCassandraOperations`, Cassandra handler có thể thực hiện I/O theo reactive execution. Nhưng nếu producer đổ vào một `DirectChannel` nhanh hơn Cassandra đáp ứng và handler async, số operations in-flight có thể tăng quá giới hạn driver/cluster.

Các câu hỏi cần trả lời trước khi tăng concurrency:

- Cassandra hiện đáp ứng bao nhiêu writes/s ở p95/p99?
- Cluster có bao nhiêu coordinator/replica? Một partition key có đang nóng không?
- Mỗi event/payload JSON lớn bao nhiêu? Có TTL/tombstone pressure không?
- Buffer và `maxConcurrency` ở reactive pipeline được giới hạn chưa?
- Retry sẽ nhân thêm bao nhiêu tải trong lúc cluster degraded?
- Khi shutdown, các operations chưa hoàn tất được drain hay chấp nhận replay từ nguồn?

### 12.2. Batch không phải công cụ tăng tốc mặc định

Cassandra batch có vai trò trong atomicity/ordering của các mutation liên quan (đặc biệt trong cùng partition), nhưng **logged batch nhiều partition** có thể nặng. Đừng cho 100.000 event vào một `List<OrderEvent>` rồi kỳ vọng một handler ghi nhanh hơn 100.000 writes được phân phối và kiểm soát.

Hướng thực hành an toàn:

1. Chọn chunk nhỏ có giới hạn theo số bản ghi và kích thước bytes.
2. Ưu tiên nhóm operations theo partition khi yêu cầu nghiệp vụ phù hợp.
3. Kiểm tra GC/heap của JVM, thread waiting khi `async(false)` và số in-flight khi `async(true)`.
4. Đo p95/timeout và phân phối load trên nodes trước và sau khi chỉnh batch.
5. Giảm concurrency và tăng backoff khi Cassandra báo overload/unavailable, không tạo retry storm.

### 12.3. Khi nào dùng channel đồng bộ?

| Channel trong flow | Lợi ích | Rủi ro |
|---|---|---|
| `DirectChannel` + sync Cassandra handler | Lỗi operation dễ truyền về caller đồng bộ | Thread caller có thể bị block bởi DB |
| `ExecutorChannel` + sync handler | Tách thread upstream | Lỗi downstream có thể xuất hiện sau source ack |
| `FluxMessageChannel` + reactive handler/gateway | Thích hợp pipeline theo Reactive Streams | Cần kiểm soát subscription, backpressure và lỗi async |
| `QueueChannel` in-memory | Giảm coupling thời điểm trong JVM | Queue không durable qua crash nếu không có message store bền vững |

Nếu ứng dụng yêu cầu **đã nhận JMS event thì chắc chắn lưu Cassandra hoặc broker sẽ redeliver**, nên chọn một chiến lược có acknowledgment boundary rõ và test crash; không chọn channel chỉ dựa vào throughput benchmark trong điều kiện bình thường.

## 13. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân khả dĩ | Cách chẩn đoán và sửa |
|---|---|---|
| Không tìm thấy bean `ReactiveCassandraOperations` | Thiếu dependency reactive, auto-configuration chưa chạy, connection cấu hình sai | Kiểm tra starter/bean và driver configuration |
| Application startup lỗi keyspace | `keyspace-name` chưa được tạo hoặc user thiếu quyền | Provision keyspace/schema trước, cấp ACL phù hợp |
| Cassandra không kết nối được | Sai `local-datacenter`, contact-points, port, TLS hoặc credentials | Kiểm tra logs driver và metadata cluster |
| CQL table không tồn tại | Schema chưa chạy hoặc session trỏ sai keyspace | Kiểm tra keyspace, `DESCRIBE TABLE` và migration |
| `String` JSON không được ghi theo mode `INSERT` | Handler mong entity được map bằng `@Table` | Thêm transformer JSON → entity hoặc dùng mode statement phù hợp |
| Lỗi mapping `Instant`/codec | Java type/CQL column type không tương ứng | Kiểm tra mapping, annotations và driver codecs |
| `send()` trả thành công nhưng không có row | Handler async, lỗi completion không được quan sát, sai keyspace | Kiểm tra async mode, error handling, trace operation và CQL SELECT theo key |
| Một event có nội dung bị thay sau retry | Cassandra INSERT upsert, key trùng nhưng payload khác | Giữ event immutable, kiểm tra conflict hoặc dùng conditional write |
| `SELECT` theo `order_id` lỗi hoặc rất chậm | Table chỉ có partition key `event_id` | Thiết kế table theo query pattern, không mặc định dùng `ALLOW FILTERING` |
| Ghi hàng loạt chậm hơn ghi lẻ | Batch quá lớn, nhiều partition, coordinator bottleneck | Chia chunk, giảm concurrency, thử unlogged/partition-aware khi phù hợp |
| Timeout/retry tạo tải đột biến | Driver/app/source retry chồng nhau | Đặt retry budget, exponential backoff, quan sát in-flight requests |
| Dữ liệu có TTL biến mất | `WriteOptions.ttl` hoặc CQL TTL được đặt quá ngắn | Đối chiếu retention policy, expired cells và compaction |
| `IF NOT EXISTS` không báo applied | Không đọc kết quả LWT ở adapter một chiều | Dùng gateway/driver để kiểm tra `[applied]` |
| Cassandra cluster có hot partition | Partition key không phân bố đều | Tái thiết kế key/distribution dựa trên workload |
| Lỗi DB không làm source JMS redeliver | Channel async hoặc lỗi được error flow hấp thụ | Kiểm tra thread/ack boundary; durable handoff hoặc sync handling |

### Phân loại exception trước khi retry

**Có thể tạm thời:** connection bị gián đoạn, cluster unavailable trong thời gian ngắn, overload có backoff, request timeout chưa rõ kết quả.

**Thường không cải thiện khi retry nguyên trạng:** CQL syntax sai, keyspace/table không tồn tại, quyền truy cập bị từ chối, entity mapping/codec không hợp lệ, dữ liệu vi phạm contract.

Không retry vô hạn lỗi vĩnh viễn. Với dữ liệu không hợp lệ, nên cách ly/quarantine kèm `eventId` và lý do lỗi; với hạ tầng tạm thời, thử lại có giới hạn và monitoring. Với sự kiện từ JMS/Kafka, hệ thống nguồn có thể redeliver riêng, nên tránh nhân **số lần retry ứng dụng × số lần retry broker** thành một vòng bão lỗi.

### Observability tối thiểu

| Metric | Lý do |
|---|---|
| Inbound messages/s | Nắm lượng công việc vào flow |
| Cassandra writes/s thành công/thất bại | Nhận biết adapter có thực sự ghi không |
| Write latency p50/p95/p99 | Phát hiện tải cao và replica chậm |
| In-flight reactive operations | Nhận biết thiếu giới hạn concurrency |
| Timeout/Unavailable/Overloaded errors | Phân loại lỗi cluster và network |
| Retry count & elapsed time | Chặn retry storm, đo tổng độ trễ |
| Cassandra coordinator/node metrics | Phát hiện hot partition/GC/compaction/timeout |
| Source JMS queue depth/Kafka lag | Kiểm tra backpressure từ đầu nguồn |
| Duplicate eventId/conflicting payload count | Phát hiện redelivery và producer gửi trùng |
| TTL/expired data/tombstone warnings | Xác minh retention và dữ liệu xóa |

Log nên chứa `eventId`, `operationType`, tên keyspace/table, correlation/tracing ID và loại exception; không log nguyên JSON có PII, credentials, token hoặc nội dung bí mật. Với multi-tenant, Cassandra user/role cần cấp quyền tối thiểu trên những keyspace/table cần thiết.

## 14. Bài thực hành: luồng lưu sự kiện đơn hàng vào Cassandra

**Môi trường:** Cassandra local/test container (ví dụ một node), Spring Integration 6+, Spring Data Cassandra reactive, Java 17+, bảng `shop_integration.order_event`. Chỉ dùng dữ liệu giả; không thao tác trên keyspace production. Cần một consumer/producer test đưa entity vào `cassandraOrderWrite` và một công cụ đọc CQL như `cqlsh`.

### Phần A — Khởi tạo kết nối và bảng

1. Tạo keyspace/table ở mục 3; xác minh schema bằng `cqlsh`.
2. Đặt `spring.cassandra.contact-points`, `local-datacenter`, `keyspace-name` phù hợp cluster đang chạy.
3. Khởi động ứng dụng, xác nhận bean `ReactiveCassandraOperations` được tạo và driver có thể kết nối.
4. Nếu lỗi `NoHostAvailable`/connection, kiểm tra port 9042, auth/TLS và datacenter trước khi sửa flow.

### Phần B — INSERT entity qua outbound adapter

1. Tạo flow mục 4 với `Type.INSERT` và `endpoint.async(false)`.
2. Gọi `OrderEventPublisher.publish("evt-1501", "ORD-1501", json)`.
3. Trong `cqlsh`, truy vấn:

~~~sql
SELECT event_id, order_id, event_type, occurred_at
FROM shop_integration.order_event
WHERE event_id = 'evt-1501';
~~~

4. Kiểm tra row khớp entity, `occurred_at` được lưu dưới dạng timestamp.
5. Gửi cùng `eventId` lần hai, quan sát semantics upsert; không nhầm đây là exception unique key.

### Phần C — Payload/statement/batch

1. Thay entity payload bằng JSON `String` và quan sát lỗi kiểu/mapping khi cố dùng `INSERT`; không để lỗi bị bỏ qua.
2. Thêm transformer `String → OrderEvent` với validation và chạy lại.
3. Chạy flow `statementFunction(...)` ở mục 7 với hai event mới; xác minh bind values không phụ thuộc nối chuỗi user input.
4. Chạy `ingestQuery(...)` với payload `List<List<?>>` hai hàng, kiểm tra row đã được ghi.
5. Tăng batch size có kiểm soát (2 → 20 → 100 records) và đo latency/throughput, không suy luận rằng batch càng lớn càng tốt.

### Phần D — So sánh sync và async

1. Với `async(false)`, ngắt kết nối Cassandra rồi gọi publisher; xem exception/timeout và thời gian chờ trên caller thread.
2. Chuyển sang mặc định `async(true)`, thử lại. Kiểm tra lúc nào `MessageChannel.send(...)` trả về và lỗi xuất hiện ở đâu.
3. Cấu hình đúng đường báo lỗi/metric cho async completion, chứng minh lỗi không bị mất trong logging.
4. Dùng `Cassandra.outboundGateway(...)` để quan sát kết quả operation thay vì chỉ một chiều; phân biệt gateway result với adapter không reply.
5. Nếu có pipeline Reactor, dùng `FluxMessageChannel` thích hợp và đo số operation in-flight.

### Phần E — Consistency, TTL và sự cố không rõ kết quả

1. Dùng `WriteOptions.ttl(Duration.ofDays(7))` trên dữ liệu demo; truy vấn kiểm tra TTL bằng công cụ/CQL phù hợp.
2. So sánh cấu hình consistency phù hợp cluster test. Nếu một node, không suy ra phép thử phản ánh môi trường nhiều replicas/production.
3. Mô phỏng timeout sau khi write có thể đã được nhận; gửi lại cùng `eventId`.
4. Xác minh event payload immutable qua retry; nếu muốn “chỉ insert khi chưa tồn tại”, thử CQL `IF NOT EXISTS` qua gateway/driver và đọc `[applied]`.
5. Dùng event có `aggregateVersion` nhỏ hơn trạng thái đã ghi, kiểm chứng chiến lược không ghi lùi nếu nghiệp vụ yêu cầu.

### Phần F — Nguồn JMS/Kafka và idempotency

1. Tạo nguồn test JMS hoặc Kafka gửi `eventId=evt-1501` với payload giống nhau hai lần.
2. Với Cassandra outbound sync và `DirectChannel`, thử lỗi Cassandra và xem nguồn JMS/Kafka xử lý ack/offset theo cấu hình.
3. Chèn `ExecutorChannel` hoặc bật async, quan sát lúc nào source ack/commit có thể xảy ra.
4. Làm cho Cassandra write hoàn thành rồi mô phỏng crash trước source ack; xác nhận replay không tạo dữ liệu nghiệp vụ sai.
5. Gửi cùng event ID nhưng JSON khác nội dung; quyết định đó là duplicate hợp lệ hay **conflicting event** cần cách ly, không âm thầm chọn bản sau.

### Ma trận kết quả cần đạt

| Kiểm tra | PASS khi |
|---|---|
| Entity mapping | `@Table`/`@PrimaryKey` ghi đúng bảng/cột |
| Outbound adapter | Nhận Spring Message và chạy Cassandra write một chiều |
| No-reply | Không mong Spring reply từ adapter |
| Gateway alternative | Có result khi cần, hiểu khác biệt `Mono<WriteResult>` và sync completion |
| Payload contract | JSON String phải qua transformer hoặc CQL statement thích hợp |
| Cassandra upsert | Retry cùng khóa không bị nhầm là unique insert exception |
| LWT | `IF NOT EXISTS` được kiểm chứng bằng kết quả `[applied]` |
| Async failure | Có đường quan sát/ xử lý lỗi sau completion |
| Source acknowledgment | Không ack quá sớm khi yêu cầu Cassandra write hoàn tất |
| Batch/capacity | Không dùng unbounded batch, có đo p95 và in-flight |
| Retention | TTL và keyspace replication được chọn theo môi trường |

Các phần về timeout, consistency, batch performance và source ack **phải được thử với Cassandra cluster thực hoặc test container**, và với JMS/Kafka thật nếu muốn chứng minh redelivery/offset behavior. Unit test mock `ReactiveCassandraOperations` chỉ kiểm tra việc flow gọi đúng API; nó không chứng minh Cassandra đã ghi hoặc các giới hạn consistency/transaction.

## 15. Câu hỏi tự đánh giá

1. Cassandra outbound channel adapter khác outbound gateway ở chuyện trả reply như thế nào?
2. Tại sao `ReactiveCassandraOperations` là dependency quan trọng hơn `JdbcTemplate` đối với adapter này?
3. `@Table` và `@PrimaryKey` được Spring Data Cassandra dùng làm gì?
4. Vì sao payload JSON `String` không mặc định trở thành Cassandra entity?
5. Mặc định `CassandraMessageHandler` bất đồng bộ có ý nghĩa gì với `MessageChannel.send()`?
6. Khi nào bạn nên chủ động cấu hình `endpoint.async(false)`?
7. `Type.INSERT`, `UPDATE`, `DELETE`, `STATEMENT` khác nhau về payload/operation ra sao?
8. Vì sao Cassandra `INSERT` không tương đương unique insert của PostgreSQL?
9. `ingestQuery(...)` yêu cầu payload có hình dạng gì? Vì sao batch quá lớn là nguy hiểm?
10. Tại sao dùng bind values trong `SimpleStatement` an toàn hơn nối chuỗi CQL từ user input?
11. `WriteOptions.ttl(...)` khác JMS TTL và request timeout ở đâu?
12. Cassandra `IF NOT EXISTS` có thể giúp chống trùng theo khóa như thế nào, và có đánh đổi gì?
13. Vì sao thiết kế bảng Cassandra phải xuất phát từ query pattern?
14. Tại sao tăng số consumer cùng một key partition có thể làm Cassandra quá tải?
15. Khi Cassandra write hoàn tất nhưng JMS commit lỗi, chuyện gì có thể xảy ra?
16. Đổi `DirectChannel` sang `ExecutorChannel` có tác động gì tới ranh giới lỗi/ack?
17. Tại sao Cassandra driver retry và broker source redelivery phải được cân đối cùng nhau?
18. Metric nào giúp phân biệt cluster unavailable với thiếu backpressure ở ứng dụng?

## 16. Tài liệu tham khảo

- [Spring Integration Reference — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): adapter, gateway, `CassandraMessageHandler`, reactive modes, ingest, query/statement và XML.
- [Spring Integration API — Cassandra DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/Cassandra.html): `outboundChannelAdapter(...)` và `outboundGateway(...)`.
- [Spring Integration API — CassandraMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/CassandraMessageHandlerSpec.html): `ingestQuery`, `writeOptions`, `statementFunction`, `query`, `parameter`.
- [Spring Integration API — CassandraMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/outbound/CassandraMessageHandler.html): type/mode, handler và các tùy chọn operation.
- [Spring Integration Reference — Integration Endpoints](https://docs.spring.io/spring-integration/reference/endpoint-summary.html): đối chiếu endpoint Cassandra outbound adapter/gateway, không có Cassandra inbound adapter sẵn.
- [Spring Data Cassandra Reference — Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): `ReactiveCassandraTemplate`, subscription, exception translation và reactive execution.
- [Spring Data Cassandra Reference — Persisting Entities](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): entity mapping, insert/update/delete và CQL operations.
- [Spring Data Cassandra API — WriteOptions](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/WriteOptions.html): TTL và write-level options.
- [Apache Cassandra Documentation](https://cassandra.apache.org/doc/latest/): CQL, data modeling, replication, consistency, batch và lightweight transactions.

**Ghi nhớ:** Cassandra outbound channel adapter đưa **Spring Message** từ `MessageChannel` ra Apache Cassandra thông qua `CassandraMessageHandler` và `ReactiveCassandraOperations`. Chọn đúng entity/mode (`INSERT`, `UPDATE`, `DELETE`, `STATEMENT`), hiểu **async mặc định**, và chỉ dùng outbound gateway khi cần reply. Cassandra là hệ dữ liệu phân tán với upsert, partitioning, consistency và timeout riêng; để tích hợp an toàn với JMS/Kafka/HTTP, cần khóa sự kiện ổn định, retry có giới hạn, quan sát completion và kiểm thử ranh giới acknowledgment thay vì giả định một lần gửi message đồng nghĩa ghi dữ liệu thành công.




