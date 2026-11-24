# CassandraMessageHandler

## 1. Vai trò của CassandraMessageHandler trong Spring Integration

Giả sử hệ thống bán hàng nhận sự kiện `OrderPaid` qua JMS. Sau khi validate, ứng dụng cần lưu sự kiện vào Apache Cassandra để tra cứu theo `eventId`. Một lựa chọn là viết CQL trực tiếp trong từng service activator, nhưng cách đó khiến logic lưu trữ, kết nối và xử lý kết quả bị trộn với nghiệp vụ.

`CassandraMessageHandler` là thành phần của **Spring Integration Cassandra** chịu trách nhiệm nhận **Spring Message** và thực hiện thao tác trên Cassandra thông qua **Spring Data `ReactiveCassandraOperations`**. Lớp nằm trong package:

~~~java
org.springframework.integration.cassandra.outbound.CassandraMessageHandler
~~~

Từ Spring Integration **6.0**, lớp này hỗ trợ hai cách dùng:

- **Outbound channel adapter:** nhận message và thực hiện thao tác Cassandra một chiều; mặc định **không tạo reply**.
- **Outbound gateway:** cũng dùng handler đó nhưng bật chế độ tạo reply, cho phép flow nhận kết quả truy vấn/ghi.

Về kế thừa, `CassandraMessageHandler extends AbstractReplyProducingMessageHandler`. Vì thế nó có các khả năng của một handler tạo reply, nhưng **kế thừa lớp có tên ReplyProducing không có nghĩa mọi cấu hình đều gửi reply**. `setProducesReply(boolean)` mới là công tắc phân biệt hai vai trò.

Trong module **SPRING_INTEGRATION_ADAPTERS**, các inbound/outbound adapter, gateway, poller và `MessageChannel` kết nối các hệ thống file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; đồng thời kiểm soát hợp đồng message, lỗi và vòng đời kết nối. Chủ đề **CassandraMessageHandler** của chương **Adapter Cassandra** đào sâu chính điểm giao giữa Spring Integration và Cassandra: kiểu payload, chế độ CQL, thực thi reactive, kết quả, lỗi và tính đúng đắn của việc ghi.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích handler nhận `Message<?>` và giao tiếp với `ReactiveCassandraOperations` thế nào.
2. Tạo handler trực tiếp bằng Java và bằng Java DSL.
3. Chọn đúng `Type.INSERT`, `UPDATE`, `DELETE`, `STATEMENT`.
4. Sử dụng entity, danh sách entity, ingest matrix, CQL query có tham số và driver `Statement<?>`.
5. Phân biệt `setAsync(false)` với chế độ async mặc định, cũng như `setProducesReply(true)`.
6. Cấu hình `WriteOptions`, truyền lỗi về đúng ranh giới và chống xử lý trùng.
7. Kiểm thử handler bằng broker Cassandra thật hoặc test container thay vì chỉ kiểm tra mock.

## 2. Handler nằm ở đâu trong integration flow?

~~~mermaid
flowchart LR
    I["HTTP / JMS / Kafka / File inbound"] --> T["Transformer + Validator"]
    T --> M["Spring Message<OrderEvent>"]
    M --> C["MessageChannel"]
    C --> H["CassandraMessageHandler"]
    H --> R["ReactiveCassandraOperations"]
    R --> D["Cassandra driver / CqlSession"]
    D --> K[("Apache Cassandra cluster")]
    H -. "Chỉ khi producesReply=true" .-> O["Spring reply channel"]
~~~

| Thành phần | Chịu trách nhiệm | Không nên gán nhầm |
|---|---|---|
| `Spring Message<?>` | Payload và headers trong JVM | Không phải một hàng Cassandra |
| `MessageChannel` | Bàn giao message trong IntegrationFlow | Không mặc định là queue bền vững |
| `CassandraMessageHandler` | Chọn operation, lấy payload, thực thi reactive Cassandra, có thể tạo reply | Không tự là Cassandra cluster/driver |
| `ReactiveCassandraOperations` | Mapping entity và thực hiện thao tác Cassandra | Không tự thiết kế partition key đúng nghiệp vụ |
| `CqlSession`/driver | Connection, routing, request timeout, consistency và codecs | Không tự bảo đảm idempotency ứng dụng |
| `CassandraMessageHandlerSpec` | API Java DSL cấu hình handler | Không phải instance handler để gọi thủ công trên runtime |

### Một message đi qua handler như thế nào?

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as Spring MessageChannel
    participant H as CassandraMessageHandler
    participant O as ReactiveCassandraOperations
    participant DB as Cassandra

    P->>C: Message<OrderEvent>
    C->>H: handleMessage(request)
    H->>H: Chọn Type + kiểm tra payload
    H->>O: insert/update/delete/execute
    O->>DB: Cassandra request
    DB-->>O: Completion / result / error
    O-->>H: Reactive signal
    alt producesReply = true
        H-->>C: Reply theo chế độ async/sync và channel
    else producesReply = false
        H-->>H: Không phát reply nghiệp vụ
    end
~~~

**Chốt ý:** nếu handler chạy **async**, thời điểm `MessageChannel.send(...)` kết thúc có thể khác thời điểm Cassandra xác nhận write. Đối với nguồn JMS/Kafka, khác biệt này ảnh hưởng trực tiếp đến lúc message nguồn được acknowledge hoặc offset được commit.

## 3. API quan trọng: constructor, setter và kiểu operation

Trong Spring Integration 6.x/7.x, các constructor công khai:

~~~java
new CassandraMessageHandler(ReactiveCassandraOperations operations);

new CassandraMessageHandler(
        ReactiveCassandraOperations operations,
        CassandraMessageHandler.Type queryType);
~~~

`Type` là enum gồm:

~~~java
CassandraMessageHandler.Type.INSERT
CassandraMessageHandler.Type.UPDATE
CassandraMessageHandler.Type.DELETE
CassandraMessageHandler.Type.STATEMENT
~~~

Các phương thức cần nhớ:

| API | Mục đích | Dùng khi |
|---|---|---|
| `setProducesReply(boolean)` | Bật/tắt reply của handler | Adapter một chiều hoặc gateway |
| `setAsync(boolean)` | Chọn xử lý bất đồng bộ hay chờ kết quả | Quyết định completion và error boundary |
| `setWriteOptions(WriteOptions)` | Gắn tùy chọn cho thao tác ghi entity | INSERT/UPDATE/DELETE |
| `setIngestQuery(String)` | Cấu hình ingest CQL; chuyển sang chế độ INSERT | Payload là ma trận hàng giá trị |
| `setQuery(String)` | CQL có tham số, chuyển sang chế độ STATEMENT | Ví dụ SELECT theo khóa |
| `setParameterExpressions(Map<String, Expression>)` | Bind các named parameters vào query | Chỉ có ý nghĩa cùng `setQuery(...)` |
| `setStatementExpression(Expression)` | SpEL tạo driver `Statement<?>` | CQL động theo message |
| `setStatementExpressionString(String)` | Biến thể nhận biểu thức dạng chuỗi | Cấu hình SpEL trực tiếp |
| `setStatementProcessor(MessageProcessor<Statement<?>>)` | Tạo driver statement từ message | Logic Java tùy biến, dễ unit test |
| `setOutputChannel(MessageChannel)` | Địa chỉ nhận reply | Chỉ dùng khi tạo reply |

`setAsync(...)` và `setOutputChannel(...)` được **kế thừa** từ các lớp handler của Spring Integration; chúng không phải API riêng của Cassandra driver. Ngoài những getter/setter công khai, `handleRequestMessage(Message<?>)` là **protected hook** của lớp cơ sở, **không phải phương thức business code nên gọi trực tiếp**.

### 3.1. Quy tắc cấu hình trước khi handler bắt đầu xử lý

Handler thường là Spring bean singleton. Nên đặt `Type`, query, parameter expressions, `WriteOptions`, `async` và `producesReply` **trước khi endpoint nhận message**. Đừng thay đổi các field cấu hình của một handler dùng chung từ thread xử lý từng sự kiện; điều đó có thể tạo race condition và kết quả khó kiểm chứng.

Nếu một ứng dụng cần nhiều thao tác khác nhau (INSERT, DELETE, SELECT), cách dễ bảo trì là **nhiều handler/endpoints được cấu hình tĩnh** và một router/flow chọn endpoint phù hợp. Không dùng `operationType` header từ client để thay enum hoặc CQL một cách tự do.

## 4. Chuẩn bị môi trường và mô hình dữ liệu test

Ví dụ tập trung vào **Spring Integration 6+**, Java 17+, Spring Data Cassandra reactive và Apache Cassandra. Dùng Spring Boot BOM để quản lý các phiên bản tương thích:

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

`spring-integration-cassandra` cung cấp handler; Spring Data reactive cung cấp `ReactiveCassandraOperations`/`ReactiveCassandraTemplate`. Không dùng `JdbcTemplate` hoặc imperative `CassandraTemplate` làm đối số constructor này.

Ví dụ cấu hình Spring Boot cho một node Cassandra development:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
~~~

Tên datacenter và địa chỉ phải đúng với cluster đang dùng; tên `datacenter1` chỉ là ví dụ. Với production phải cấu hình authentication, TLS, topology, replication và secrets đúng môi trường.

Tạo keyspace và bảng bằng `cqlsh` trên broker Cassandra test:

~~~sql
-- SimpleStrategy/replication_factor=1 chỉ dành cho lab một DC/nút.
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    payload_json text
);
~~~

Chọn `event_id` làm partition key vì truy vấn lab **theo eventId**. Cassandra không phải RDBMS tùy ý lọc theo `order_id` trên bảng này; nếu phải truy vấn theo order, cần thiết kế table theo query pattern riêng. Với production nhiều replica/DC, không dùng cấu hình replication mẫu một node.

Entity Java:

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_event")
public record OrderEvent(
        @PrimaryKey("event_id") String eventId,
        @Column("order_id") String orderId,
        @Column("event_type") String eventType,
        @Column("payload_json") String payloadJson) {
}
~~~

`@Table` và `@PrimaryKey` cho Spring Data biết cách map entity sang CQL; `record` biểu diễn một sự kiện bất biến. Producer nên gửi cùng `eventId` cho các lần retry cùng sự kiện. **Cùng khóa không chứng minh dữ liệu không thay đổi**: Cassandra INSERT bình thường có thể upsert/ghi đè nếu payload khác.

## 5. Cách 1: tạo trực tiếp CassandraMessageHandler làm service activator

Đây là cách thuận tiện để hiểu **handler thật** mà Java DSL sẽ tạo phía dưới. Trong một class `@Configuration` đã bật Spring Integration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.messaging.MessageHandler;

@Bean
@ServiceActivator(inputChannel = "cassandraWriteInput")
public MessageHandler cassandraMessageHandler(
        ReactiveCassandraOperations operations) {

    CassandraMessageHandler handler = new CassandraMessageHandler(
            operations, CassandraMessageHandler.Type.INSERT);
    handler.setProducesReply(false);
    handler.setAsync(false);
    return handler;
}
~~~

Giải thích từng dòng quan trọng:

- Constructor nhận `ReactiveCassandraOperations` đã kết nối tới Cassandra, rồi chọn `Type.INSERT` tường minh.
- `setProducesReply(false)` yêu cầu **một chiều**: không gửi response tới `replyChannel` hay `outputChannel`. Đây cũng là mode mặc định của Cassandra handler.
- `setAsync(false)` yêu cầu handler **chờ kết quả reactive operation** theo cơ chế đồng bộ của Spring Integration, giúp lỗi I/O dễ đi về caller trong một flow đồng bộ.
- `@ServiceActivator(inputChannel=...)` gắn handler vào channel `cassandraWriteInput`. Nếu chỉ tạo `@Bean` mà không đăng ký consumer/channel, Spring Message sẽ không tự tìm đến handler.

### 5.1. Gửi một entity tới handler

Với channel `cassandraWriteInput` được tạo/đăng ký bởi Spring Integration:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final MessageChannel input;

    public OrderEventPublisher(
            @Qualifier("cassandraWriteInput") MessageChannel input) {
        this.input = input;
    }

    public void publish(String eventId, String orderId, String payloadJson) {
        OrderEvent event = new OrderEvent(
                eventId, orderId, "OrderPaid", payloadJson);

        boolean accepted = input.send(
                MessageBuilder.withPayload(event)
                        .setHeader("eventId", eventId)
                        .build());
        if (!accepted) {
            throw new IllegalStateException("Không bàn giao được Spring Message");
        }
    }
}
~~~

Handler nhận **payload `OrderEvent`**, không đọc JSON rồi tự tạo entity. Giá trị header `eventId` có thể dùng để log/tracing, nhưng **không tự map thành một Cassandra column**. Các cột lấy từ entity mapping.

Đặt validator trước khi gửi (`eventId` không rỗng, `payloadJson` hợp lệ, `eventType` thuộc allowlist). Đừng ghi payload chứa token, password hoặc thông tin cá nhân không được phép lưu.

### 5.2. Vì sao vẫn không thể coi mỗi `send()` là business commit?

Trên `DirectChannel` và handler `async(false)`, đường gọi có thể chờ tới khi Cassandra operation hoàn thành hoặc ném exception. Nhưng:

- Cassandra có thể trả **timeout** dù write đã được cluster thực hiện: kết quả là **không chắc chắn**, cần idempotency khi retry.
- Cấu hình consistency chỉ nói mức xác nhận theo replicas, không tạo transaction với JMS/HTTP/Kafka.
- Nếu channel đổi thành `ExecutorChannel` hoặc handler chuyển về mặc định async, caller có thể thấy `send()` thành công trước khi Cassandra hoàn tất.

### 5.3. Khi nào dùng direct handler thay cho DSL?

Nên dùng direct `CassandraMessageHandler` khi cần:

- Đặt trực tiếp nhiều setter đặc thù của handler.
- Tạo một bean handler dùng lại trong cấu hình `@ServiceActivator` hiện có.
- Kiểm thử các tham số handler ở cấp component hoặc tích hợp XML/annotation.

Nếu mục tiêu chính là mô tả luồng đọc–biến đổi–ghi dữ liệu bằng các endpoint, **Java DSL thường dễ theo dõi hơn**.

## 6. Cách 2: tạo handler thông qua Java DSL

Factory `Cassandra.outboundChannelAdapter(operations, type)` tạo `CassandraMessageHandlerSpec`, giúp cấu hình handler mà không phải tự gọi constructor và `setProducesReply(false)`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class CassandraIntegrationConfiguration {

    @Bean
    public IntegrationFlow orderEventWriteFlow(
            ReactiveCassandraOperations operations) {

        return IntegrationFlow.from("cassandraWriteInput")
                .handle(Cassandra.outboundChannelAdapter(
                                operations,
                                CassandraMessageHandler.Type.INSERT),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

Trong `.handle(spec, endpoint -> ...)`:

1. `spec` quyết định logic của `CassandraMessageHandler`.
2. `endpoint.async(false)` tác động đến cơ chế async của handler endpoint.
3. `IntegrationFlow.from("cassandraWriteInput")` định nghĩa input channel; một ứng dụng nên chỉ có **một** consumer logic cho channel nếu không cố ý phân phối nhiều bước.

**Không đăng ký đồng thời** `@ServiceActivator` ở mục 5 và flow ở mục 6 với **cùng input channel** rồi chờ mỗi event chỉ ghi một lần. Hai ví dụ là các phương án thay thế.

### 6.1. XML namespace cũng tạo cùng handler

~~~xml
<int:channel id="cassandraWriteInput"/>

<int-cassandra:outbound-channel-adapter
        id="cassandraWriter"
        channel="cassandraWriteInput"
        cassandra-template="reactiveCassandraTemplate"
        mode="INSERT"
        async="false"/>
~~~

Đây là **fragment**: cần namespace `int`, `int-cassandra` và bean `reactiveCassandraTemplate` thực sự triển khai `ReactiveCassandraOperations`. Thuộc tính `cassandra-template` trong namespace là tên lịch sử, **không có nghĩa** handler nhận `org.springframework.data.cassandra.core.CassandraTemplate` imperative.

Tạo Java DSL **hoặc** XML cho cùng endpoint, không đăng ký trùng khi chỉ có một writer.

## 7. Mode của handler và hợp đồng payload

### 7.1. Bốn mode hoạt động

| `Type` | Input dự kiến | Kết quả Cassandra điển hình | Ghi chú quan trọng |
|---|---|---|---|
| `INSERT` | Entity có `@Table` hoặc `List<entity>` | Insert/upsert theo mapping | Không phải unique-insert mặc định |
| `UPDATE` | Entity hoặc danh sách entity | Update theo mapping | Có thể có upsert semantics; xem CQL thực tế |
| `DELETE` | Entity hoặc danh sách entity | Delete/tombstone theo key | Cẩn trọng xóa lớn và tombstone accumulation |
| `STATEMENT` | Driver `Statement<?>`, query hoặc statement processor/expression | Thực thi CQL tự tạo | Phải bind parameters và giới hạn câu lệnh |

Đối với mode entity (`INSERT`/`UPDATE`/`DELETE`), Spring Integration Reference ghi rõ handler kỳ vọng **entity được annotate `@Table`** trong payload. Khi payload là **list entity**, handler gọi thao tác batch tương ứng. Không tự động convert một `String` JSON thành entity chỉ vì nội dung có field trùng tên bảng.

~~~text
Đúng:   Message<OrderEvent>        -> Type.INSERT
Đúng:   Message<List<OrderEvent>>  -> Type.INSERT
Sai:    Message<String JSON>       -> Type.INSERT (chưa transform)
Đúng:   Message<Statement<?>>      -> Type.STATEMENT
~~~

### 7.2. Trường hợp dữ liệu nguồn là JSON

Một inbound JMS adapter thường đưa body `TextMessage` thành Spring payload `String`. Hãy parse và validate trước khi gửi tới Cassandra:

~~~java
// Fragment Java DSL; objectMapper là bean Jackson được inject.
.transform(String.class, json -> {
    try {
        return objectMapper.readValue(json, OrderEvent.class);
    } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
        throw new IllegalArgumentException("JSON OrderEvent không hợp lệ", ex);
    }
})
.channel("cassandraWriteInput")
~~~

Một bước parse thành công không đồng nghĩa event nghiệp vụ hợp lệ. Cần kiểm tra `eventId`, `eventType`, schema version, authorization/tenant và quy tắc null. Khi cần mapping từ DTO API sang entity Cassandra, nên thực hiện rõ ràng trong transformer thay vì ép repository/database hiểu payload API nguyên trạng.

### 7.3. Cassandra upsert và retry

CQL `INSERT` thông thường ghi theo primary key và có **upsert semantics**. Gửi hai lần cùng `event_id` không tự phát sinh lỗi unique constraint như `INSERT` của RDBMS.

Nếu cùng ID nhưng nội dung khác nhau, timestamp/write rules có thể làm giá trị row thay đổi. Với **event log**, nên bảo đảm sự kiện là **immutable**: cùng `eventId` phải có cùng nội dung; dữ liệu không khớp là lỗi contract, không phải retry hợp lệ.

Nếu yêu cầu chỉ ghi khi khóa chưa tồn tại, dùng CQL conditional `IF NOT EXISTS` (lightweight transaction – LWT) hoặc một chiến lược kiểm soát idempotency được thiết kế riêng; khi đó cần quan sát kết quả `[applied]`, thường qua gateway/driver thay vì adapter một chiều.

## 8. `setQuery(...)` và `setParameterExpressions(...)`

`setQuery(String)` cho phép handler thực thi một CQL query có **named parameters**. Theo tài liệu Spring Integration, gọi setter này đưa handler vào **mode `STATEMENT`**. Các parameter expressions được đánh giá trên **Spring Message**, không phải thực thi trực tiếp trên broker.

### 8.1. Gateway SELECT qua Java DSL

Ví dụ tìm bản ghi `order_event` theo `eventId`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow findOrderEventById(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("cassandraFindRequests")
            .handle(Cassandra.outboundGateway(operations)
                    .query("SELECT * FROM order_event WHERE event_id = :eventId")
                    .parameter("eventId", "payload"))
            .channel(c -> c.flux("cassandraFindResults"))
            .get();
}
~~~

Input của flow là Spring Message mang payload `String eventId`. `parameter("eventId", "payload")` đánh giá SpEL trên message để bind giá trị vào tham số CQL `:eventId`. Handler **không** phải tự xây câu SQL/CQL bằng phép cộng chuỗi chứa `eventId`.

**Tại sao dùng `outboundGateway`?** SELECT cần trả kết quả cho caller/flow tiếp theo. `outboundChannelAdapter` dùng handler không reply, nên sẽ thực hiện operation nhưng không có Spring reply chứa hàng được tìm thấy.

`FluxMessageChannel` giúp làm việc với kết quả reactive mà không buộc handler chờ theo kiểu imperative. Tùy API Spring Data và loại query, kết quả có thể là publisher/collection hoặc một đối tượng kết quả theo operation; hãy viết consumer theo **payload type đã kiểm tra ở integration test**, không ép mọi SELECT reply thành `OrderEvent` đơn lẻ.

### 8.2. Cấu hình trực tiếp tương đương

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.expression.Expression;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.messaging.MessageHandler;

@Bean
@ServiceActivator(inputChannel = "cassandraFindRequests")
public MessageHandler cassandraFindHandler(
        ReactiveCassandraOperations operations) {

    CassandraMessageHandler handler = new CassandraMessageHandler(operations);
    handler.setQuery(
            "SELECT * FROM order_event WHERE event_id = :eventId");

    SpelExpressionParser parser = new SpelExpressionParser();
    Map<String, Expression> params = Map.of(
            "eventId", parser.parseExpression("payload"));

    handler.setParameterExpressions(params);
    handler.setProducesReply(true);
    handler.setOutputChannelName("cassandraFindResults");
    return handler;
}
~~~

Ví dụ này là **cách thay thế** Java DSL ở mục 8.1. Nếu dùng cả hai cùng nhận `cassandraFindRequests`, sẽ có hai service activators và việc phân phối message khác với một gateway đơn lẻ.

Lưu ý:

- `setParameterExpressions(...)` chỉ có ý nghĩa khi đã dùng `setQuery(...)`. Không lắp các parameter expressions này vào entity `INSERT` rồi mong handler dùng chúng.
- Expression được đánh giá theo dữ liệu message. Nếu đầu vào thiếu field, kiểu không tương thích hoặc expression lỗi, exception có thể xảy ra **trước khi** một CQL operation được gửi.
- Chỉ dùng CQL query được **allowlist**. Bind values không thay thế validation và authorization.

### 8.3. Tham số lấy từ headers

Spring Integration hỗ trợ named parameter từ payload hoặc headers:

~~~java
// Fragment cho outbound gateway có query parameter hóa.
.query("SELECT * FROM order_event WHERE event_id = :eventId LIMIT :limit")
.parameter("eventId", "payload")
.parameter("limit", message -> message.getHeaders().get("limit"))
~~~

Ứng dụng cần validate `limit` là số nguyên dương, có trần an toàn, và truy vấn phù hợp khóa bảng. Đừng chấp nhận giá trị `LIMIT` cực lớn từ request bên ngoài rồi đổ toàn bộ result vào bộ nhớ. Với CQL cụ thể, khả năng bind từng loại tham số còn phụ thuộc driver/parser; nên xác minh trên Cassandra thật.

## 9. `setStatementProcessor(...)` và `statementFunction(...)`

Khi CQL không thuận tiện biểu diễn bằng named query string hoặc cần build statement từ nhiều trường, handler hỗ trợ:

- `setStatementExpression(Expression)` hoặc `setStatementExpressionString(String)`.
- `setStatementProcessor(MessageProcessor<Statement<?>>)`.
- Java DSL `statementExpression(...)` hoặc `statementFunction(...)`.

Các cấu hình này đưa handler vào **mode `STATEMENT`**. Spring Integration có thể đánh giá expression hoặc gọi function để xây `com.datastax.oss.driver.api.core.cql.Statement<?>` từ Spring Message.

### 9.1. Xây một CQL statement bằng bind values

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow saveEventByStatement(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("cassandraStatementWrite")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .statementFunction(message -> {
                        OrderEvent event = (OrderEvent) message.getPayload();
                        return SimpleStatement.newInstance(
                                "INSERT INTO order_event "
                                + "(event_id, order_id, event_type, payload_json) "
                                + "VALUES (?, ?, ?, ?)",
                                event.eventId(),
                                event.orderId(),
                                event.eventType(),
                                event.payloadJson());
                    }),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

`SimpleStatement.newInstance(query, values...)` truyền **giá trị bind** thay vì nối chuỗi CQL với data từ JSON. Đây là biện pháp cần thiết để tránh CQL injection qua **giá trị**. Tên keyspace, table và column thường không được bind như một value; chỉ cho phép các identifier được cấu hình sẵn, không nhận từ dữ liệu người dùng tùy ý.

**Điểm khác với mode `INSERT`:** ở đây message vẫn mang `OrderEvent` nhưng **statement function** quyết định câu lệnh sẽ được gửi. Spring Data entity mapping không còn là cơ chế duy nhất chọn tên bảng/cột; người viết handler chịu trách nhiệm về CQL và driver codecs.

### 9.2. Truyền sẵn driver `Statement<?>` làm payload

Trong mode `STATEMENT`, một message cũng có thể mang `Statement<?>` đã được dựng từ trước:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.messaging.support.MessageBuilder;

SimpleStatement statement = SimpleStatement.newInstance(
        "INSERT INTO order_event "
        + "(event_id, order_id, event_type, payload_json) "
        + "VALUES (?, ?, ?, ?)",
        "evt-2001", "ORD-2001", "OrderPaid",
        "{\"eventId\":\"evt-2001\"}");

cassandraStatementInput.send(
        MessageBuilder.withPayload(statement).build());
~~~

`cassandraStatementInput` phải là channel được inject và nối đến handler mode `STATEMENT`. Đừng dùng cùng channel với handler mode `INSERT` đang mong entity, nếu không payload contract bị vi phạm.

### 9.3. SpEL và QueryBuilder

Tài liệu Spring Integration còn cho phép `statementExpression(...)` dùng DataStax QueryBuilder; Spring đăng ký `QueryBuilder` dưới dạng import trong bối cảnh SpEL. Một ví dụ tạo SELECT statement khi không dùng query parameterization:

~~~java
// Fragment Java DSL: minh họa expression trả về driver Statement.
.statementExpression("T(QueryBuilder).selectFrom('order_event').all().build()")
~~~

Đây là SELECT không có giới hạn dòng nên **chỉ minh họa cơ chế SpEL trong môi trường test**, không dùng cho production. Với một bảng lớn, hãy chọn partition key rõ ràng và `LIMIT`/page size đúng hợp đồng. Các câu lệnh dữ liệu phá hủy như `TRUNCATE`/`DROP` không nên được xây trực tiếp từ metadata do client gửi.

### 9.4. Không trộn ba nguồn chọn statement trên một handler

| Cấu hình đã chọn | Handler kỳ vọng | Không nên đồng thời dùng |
|---|---|---|
| `setQuery(...)` + parameter expressions | Một query string đã xác định, bind tham số | Statement processor không cùng contract |
| `setStatementProcessor(...)` | Processor tạo `Statement<?>` theo message | `setQuery(...)` khác mục tiêu |
| `setStatementExpression(...)` | SpEL tạo `Statement<?>` | Một processor khác cạnh tranh |
| Mode `STATEMENT`, không có generator | Payload đã là `Statement<?>` | Entity thuần nếu không được build thành statement |

Chọn **một** cơ chế tạo CQL cho mỗi handler endpoint. Dù API cho phép setter được gọi nối tiếp, không nên dựa vào thứ tự thay thế lẫn nhau hoặc fallback khó hiểu; hãy thiết kế endpoint riêng và kiểm tra query thực tế trong test.

## 10. `setIngestQuery(...)`: nhận ma trận nhiều hàng

`setIngestQuery(String)` phục vụ cách ghi nhiều hàng theo một CQL ingest query có placeholders, đưa handler về mode **INSERT**. Khác với entity batch, **payload phải là `List<List<?>>`**: mỗi inner list là một dòng giá trị đúng thứ tự placeholders.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageHandler;

@Bean
@ServiceActivator(inputChannel = "cassandraIngestInput")
public MessageHandler cassandraIngestHandler(
        ReactiveCassandraOperations operations) {

    CassandraMessageHandler handler = new CassandraMessageHandler(operations);
    handler.setIngestQuery(
            "INSERT INTO order_event "
            + "(event_id, order_id, event_type, payload_json) "
            + "VALUES (?, ?, ?, ?)");
    handler.setAsync(false);
    return handler;
}
~~~

Producer tạo payload:

~~~java
import java.util.List;
import org.springframework.messaging.support.MessageBuilder;

List<List<Object>> rows = List.of(
        List.<Object>of(
                "evt-2001", "ORD-2001", "OrderPaid",
                "{\"eventId\":\"evt-2001\"}"),
        List.<Object>of(
                "evt-2002", "ORD-2002", "OrderPaid",
                "{\"eventId\":\"evt-2002\"}")
);

cassandraIngestInput.send(
        MessageBuilder.withPayload(rows).build());
~~~

**Kiểm tra đầu vào:**

- Mỗi hàng có đúng bốn giá trị ứng với bốn dấu `?`.
- Kiểu Java có codec tương thích với kiểu cột CQL.
- `List.of(...)` của Java **không cho phép null**; nếu nghiệp vụ có cột nullable, chọn cấu trúc dữ liệu phù hợp và kiểm thử binding.
- Không dùng ingest matrix unbounded cho hàng triệu rows: phải chunk, đo latency và giới hạn tải.

**Đừng nhầm ingest với ACID transaction nhiều row.** Cassandra batch có các đặc tính theo partition/cluster, không biến toàn bộ nguồn message thành một database transaction kiểu RDBMS.

## 11. `setWriteOptions(...)` cho các phép ghi entity

`WriteOptions` thuộc **Spring Data Cassandra**, cho phép cấu hình một số đặc tính của thao tác ghi. Spring Integration chỉ chuyển đối tượng này tới handler; nó không tự làm cho Cassandra write an toàn với mọi workload.

Ví dụ đặt TTL 7 ngày cho dữ liệu **demo**:

~~~java
import java.time.Duration;
import org.springframework.data.cassandra.core.cql.WriteOptions;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;

WriteOptions options = WriteOptions.builder()
        .ttl(Duration.ofDays(7))
        .build();

CassandraMessageHandler handler = new CassandraMessageHandler(
        operations, CassandraMessageHandler.Type.INSERT);
handler.setWriteOptions(options);
handler.setAsync(false);
~~~

`operations` trong fragment là bean `ReactiveCassandraOperations` đã được inject. Đoạn này minh họa setter, không thay thế đăng ký bean/endpoint vào `MessageChannel`.

Tùy version Spring Data, `WriteOptions` còn có thể mang consistency, timeout, TTL và các write-level settings khác. **Không cấu hình theo tên method chưa được version thực tế hỗ trợ**; đối chiếu Javadoc của Spring Data trong dependency tree.

### 11.1. TTL Cassandra khác TTL của JMS/Kafka

| Giá trị | Nằm ở đâu? | Nghĩa |
|---|---|---|
| Cassandra `WriteOptions.ttl(...)` | Cassandra storage layer | Thời gian sống của dữ liệu/cell được ghi |
| JMS `timeToLive` | JMS producer/broker | Thời điểm một JMS message hết hạn |
| Kafka retention | Kafka topic/broker | Chính sách giữ records trong log |
| Driver request timeout | Cassandra client driver | Thời gian chờ kết quả một request |
| Spring `sendTimeout` | Messaging endpoint/channel | Giới hạn chờ gửi message theo channel |

Đặt TTL trên Cassandra **không** làm JMS message nguồn tự hết hạn hoặc được acknowledge. Khi Cassandra cell hết TTL, dữ liệu có thể liên quan tombstones và compaction; không xem TTL là một job xóa đồng bộ chính xác theo giây.

### 11.2. Không áp dụng `WriteOptions` cho mọi mode một cách máy móc

Spring Integration DSL mô tả `writeOptions(...)` dành cho `INSERT`, `UPDATE` và `DELETE`. Với `STATEMENT` được build sẵn, muốn consistency/timeout phù hợp phải cấu hình **trên driver statement hoặc execution profile** theo contract tương ứng; đừng giả định `setWriteOptions(...)` sẽ rewrite mọi CQL statement tùy ý.

### 11.3. Consistency và giá trị xác nhận

Cassandra dùng consistency level như `ONE`, `LOCAL_QUORUM`, `ALL`... phù hợp replication topology. Ví dụ `LOCAL_QUORUM` trong một datacenter với RF=3 thường yêu cầu tối thiểu hai replica đáp ứng; nếu RF/topology khác phải tính lại.

**Write completion** nghĩa là operation được driver/cluster xác nhận theo cấu hình consistency và timeout, không tự bảo đảm transaction nguyên tử cùng PostgreSQL, HTTP request, JMS acknowledgment hoặc Kafka offset. Một timeout vẫn có thể xảy ra **sau khi Cassandra thực sự ghi**, nên retry cần idempotency.

## 12. Async mặc định và cách handler tạo reply

Theo Spring Integration Reference, `CassandraMessageHandler` **mặc định `async=true`**. Gọi `setAsync(false)` để chuyển sang đồng bộ, trong đó Spring Integration có thể `block()` reactive `Mono` để chờ kết quả của operation.

### 12.1. Ma trận thực thi

| Vai trò handler | Async | Điều caller/flow nhận |
|---|---|---|
| Adapter `producesReply=false` | `true` (mặc định) | Không phát reply; Cassandra completion có thể đến sau `send()` |
| Adapter `producesReply=false` | `false` | Không phát reply, nhưng handler chờ operation theo cơ chế sync |
| Gateway `producesReply=true` | `true` | Có reactive publisher/result tùy operation và channel |
| Gateway `producesReply=true` | `false` | Đợi kết quả và tạo reply theo operation |

Spring Integration Reference nêu rõ với **gateway async**, kết quả ghi có thể ở dạng `Mono<WriteResult>`; cách tiêu thụ còn tùy output channel. Để xử lý reactive đúng nghĩa, tài liệu khuyến nghị `FluxMessageChannel`. Với **sync**, handler gọi `Mono.block()` để lấy giá trị cho reply.

Đừng khẳng định mọi `SELECT`, `INSERT` và `DELETE` đều cho đúng một Java class reply giống nhau. Query nhiều hàng có thể có semantics stream/publisher khác write; cần test **payload type** trên output channel và chọn transformer/consumer phù hợp.

### 12.2. Gateway Java DSL để lấy kết quả ghi

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow writeEventWithResult(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("cassandraWriteRequests")
            .handle(Cassandra.outboundGateway(
                            operations,
                            CassandraMessageHandler.Type.INSERT),
                    endpoint -> endpoint.async(false))
            .channel("cassandraWriteResults")
            .get();
}
~~~

Input `cassandraWriteRequests` chứa entity `OrderEvent`. Gateway tạo reply theo kết quả của operation. Output `cassandraWriteResults` cần có **consumer phù hợp** để nhận kết quả; chỉ đặt tên channel mà không có consumer thì flow có thể không đáp ứng như mong đợi.

### 12.3. Direct handler bật reply tường minh

~~~java
@Bean
@ServiceActivator(inputChannel = "cassandraWriteRequests")
public MessageHandler cassandraReplyingWriteHandler(
        ReactiveCassandraOperations operations) {

    CassandraMessageHandler handler = new CassandraMessageHandler(
            operations, CassandraMessageHandler.Type.INSERT);
    handler.setProducesReply(true);
    handler.setAsync(false);
    handler.setOutputChannelName("cassandraWriteResults");
    return handler;
}
~~~

Đây là **cấu hình thay thế** gateway ở mục 12.2. Bật `producesReply` nhưng không có đường reply hợp lệ (output channel hoặc `replyChannel` của request) sẽ làm flow khó dự đoán và có thể dẫn đến lỗi gửi reply. Trong code production, nên định nghĩa rõ request/reply contract.

### 12.4. Đừng gọi blocking handler trên event-loop không cho phép block

`setAsync(false)` thuận lợi cho một `DirectChannel` nằm trong luồng imperative, nhưng có thể block thread đang gọi. Khi một WebFlux/Reactor event-loop gọi handler và endpoint dùng `Mono.block()`, ứng dụng có thể gặp lỗi hoặc suy giảm throughput. Đối với reactive pipeline, hãy thiết kế toàn flow theo reactive, có subscriber, backpressure, retry/error strategy rõ ràng và `FluxMessageChannel` phù hợp.

**Reactive không có nghĩa vô hạn concurrency.** Nếu input sinh nhanh hơn Cassandra xử lý, số request in-flight có thể tăng và làm driver/cluster quá tải; cần giới hạn concurrency, đo p95/p99 và tránh unbounded buffering.

## 13. Exception, error channel và transaction boundary

Một Cassandra operation có thể thất bại ở các giai đoạn khác nhau:

1. **Trước I/O:** payload sai kiểu, SpEL parameter không đánh giá được, CQL bind thiếu giá trị, query được cấu hình sai.
2. **Trong I/O:** auth/permission bị từ chối, table không tồn tại, cluster unavailable, overloaded, read/write timeout.
3. **Sau khi cluster đã có thể ghi:** client timeout/mất connection nên không biết chắc write đã áp dụng hay chưa.

### 13.1. Sync handler và DirectChannel

~~~mermaid
flowchart LR
    A["JMS listener, transacted"] --> B["DirectChannel"]
    B --> C["CassandraMessageHandler async=false"]
    C --> D[("Cassandra cluster")]
    D -->|"Exception đồng bộ"| E["Exception truyền ngược về listener"]
    E --> F["JMS rollback / redelivery theo broker policy"]
~~~

Trong flow đồng bộ, exception có thể truyền về JMS listener và ảnh hưởng việc rollback/ack khi container được cấu hình tương ứng. **Điều đó không tạo transaction nguyên tử giữa JMS và Cassandra**: Cassandra có thể đã ghi nhưng JMS commit thất bại, làm event đến lại.

### 13.2. Async handler hoặc async channel

~~~mermaid
flowchart LR
    A["JMS listener"] --> B["MessageChannel"]
    B --> C["CassandraMessageHandler async=true"]
    C -. "operation chạy sau" .-> D[("Cassandra cluster")]
    B --> E["JMS callback có thể kết thúc"]
    E --> F["JMS commit"]
    D -. "lỗi sau commit" .-> G["Reactive error handling / monitoring"]
~~~

Nếu `ExecutorChannel`/`QueueChannel` tách thread hoặc handler chạy async, một số lỗi Cassandra xảy ra **sau khi listener nguồn đã ack/commit**. Không thể đợi rollback JMS message gốc chỉ bằng cách khai báo `errorChannel` ở downstream.

### 13.3. `errorChannel` không tự động là retry queue

Spring Integration có `ErrorMessage`/`errorChannel` để quan sát và phân loại lỗi. Nhưng:

- `errorChannel` là một **Spring MessageChannel**, không phải DLQ broker.
- Không tự tạo retry/backoff hoặc atomic handoff sang nguồn message.
- Với async completion, phải xác minh lỗi được đưa tới error path mà ứng dụng thật đang quan sát; không giả định một `try/catch` quanh `send()` thấy mọi lỗi.
- Nếu error handler **hấp thụ exception** trong một flow JMS transacted, callback có thể được coi thành công và JMS commit dù database chưa lưu.

### 13.4. Retry theo loại lỗi

| Lỗi | Thử lại nguyên message? | Cách xử lý |
|---|---|---|
| Cluster unavailable tạm thời | Có thể | Backoff có giới hạn, giảm concurrency, alert |
| Write timeout với kết quả không chắc | Có thể nhưng cần idempotency | Giữ `eventId`, tránh tác động lặp |
| CQL syntax/table không tồn tại | Không giúp nếu cấu hình chưa sửa | Fail fast, sửa schema/config |
| Entity mapping/codec sai | Thường không | Sửa contract/transformer |
| Permissions/auth sai | Không giúp trước khi khắc phục | Alert, sửa ACL/secrets |
| Duplicate event với cùng dữ liệu | Không cần làm nghiệp vụ lại | Kiểm tra và kết thúc có chủ đích |
| Cùng `eventId` nhưng payload khác | Không tự động | Cách ly, điều tra data corruption |

Nếu nguồn JMS có redelivery 5 lần còn ứng dụng retry Cassandra 3 lần trong mỗi callback, một sự kiện có thể dẫn đến **tới 15 lần ghi/thử ghi**. Phải quản lý retry budget ở **cấp end-to-end**, tránh nhân tải trong lúc cluster đang lỗi.

## 14. Connection, lifecycle và giới hạn tài nguyên

`CassandraMessageHandler` là một Spring Integration endpoint dùng bean `ReactiveCassandraOperations` và driver/session được cấu hình bên ngoài. Nó **không** tạo một Cassandra cluster mới cho từng message và cũng không nên tạo `CqlSession` mới trong mỗi lời gọi `handleMessage`.

### 14.1. Vòng đời của handler

1. **Startup:** Spring tạo `ReactiveCassandraOperations` và handler; endpoint đăng ký consumer trên input channel.
2. **Receive:** handler dùng cấu hình mode/query/statement đã được chuẩn bị để xử lý message.
3. **Execute:** Spring Data tạo reactive operation; handler/endpoint quyết định subscribe/block và đường reply/error.
4. **Stop:** endpoint có thể dừng nhận message mới, nhưng cần xác định cách drain những reactive writes đang in-flight.
5. **Restart/reconnect:** driver/session có thể khôi phục kết nối; nguồn message phải tự có chiến lược replay/idempotency phù hợp nếu write bị ngắt.

Không dựa vào việc gọi `stop()` trên endpoint để khẳng định **mọi pending write đã được Cassandra commit**. Cần kiểm chứng shutdown behavior với driver/handler version và deployment orchestration thực tế.

### 14.2. Dùng chung ReactiveCassandraOperations đúng cách

`ReactiveCassandraOperations` thường là bean singleton được cấu hình và tái sử dụng. Không tạo một template mới theo `eventId` hoặc header từ client. Các thiết lập như contact points, local DC, auth, TLS, timeouts và execution profiles thuộc phạm vi kết nối/driver, cần được quản lý tập trung và không lộ thông tin mật trong log.

### 14.3. Query pattern, partition key và hot partitions

Cassandra tối ưu theo **partition key**. Table `order_event(event_id PRIMARY KEY, ...)` hợp lý khi truy vấn chính là `eventId`. Nếu workload yêu cầu xem mọi sự kiện của một order theo thời gian, cần thiết kế table riêng, ví dụ partition theo `orderId` và clustering theo timestamp/sequence, có giới hạn kích thước partition.

Một handler đúng API nhưng dùng sai partition key vẫn có thể làm cluster nghẽn. Đừng xem `ALLOW FILTERING` như giải pháp mặc định cho thiếu index/mô hình query; nó có thể khiến truy vấn trở nên đắt đỏ.

## 15. Bảo mật, kiểm soát CQL và tính đúng đắn

### 15.1. CQL bind values không thay được authorization

`setQuery(...)` và `statementFunction(...)` giúp dùng bind parameters để truyền **giá trị** an toàn. Tuy nhiên:

- Không cho phép client truyền tên bảng, cột hoặc CQL fragment tùy ý.
- Không dùng header `operation=DELETE` từ nguồn không đáng tin để gọi một handler delete nếu chưa có quyền và hợp đồng nghiệp vụ.
- Không tự đưa SQL/CQL string trực tiếp từ HTTP/JMS payload vào `SimpleStatement`.
- Dùng Cassandra role có quyền tối thiểu trên keyspace/table tương ứng, không dùng admin role cho ứng dụng.

### 15.2. Không coi headers là dữ liệu nghiệp vụ đã xác thực

`MessageHeaders` có thể chứa `tenantId`, `eventType`, `traceId`... do nguồn ngoài đặt. Những giá trị này **không tự chứng minh quyền truy cập** hoặc tính nhất quán với payload. Nếu hệ thống multi-tenant, service phải validate sender/tenant rồi mới định tuyến tới Cassandra table/partition được cho phép.

### 15.3. Idempotency theo eventId, không theo một write success flag

Ví dụ hai message mang cùng `eventId` nhưng payload khác:

~~~json
{"eventId":"evt-2001","orderId":"ORD-2001","eventType":"OrderPaid"}
~~~

~~~json
{"eventId":"evt-2001","orderId":"ORD-2001","eventType":"OrderCancelled"}
~~~

Không nên coi cả hai là cùng một retry bình thường. Cassandra upsert theo `event_id` có thể làm bản ghi cuối phụ thuộc write timestamp/conflict resolution, không phản ánh thứ tự nghiệp vụ. Cần **so sánh nội dung immutable**, version hoặc conditional write, tùy thiết kế.

Nếu đang lưu state theo `orderId` chứ không phải event log, cần quy tắc `aggregateVersion` để tránh các event đến lệch thứ tự (đặc biệt khi JMS/Kafka redelivery). Chỉ dựa vào timestamp của JVM nhận message không đủ.

## 16. Troubleshooting theo dấu hiệu

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Không tìm thấy bean `ReactiveCassandraOperations` | Thiếu reactive starter/bean hoặc auto-config không chạy | Dependency, cấu hình Spring Data, bean types |
| Handler không được gọi | Chưa gắn `@ServiceActivator` hoặc flow/channel sai tên | Spring Integration graph, channel subscribers |
| `MessageDeliveryException` do không có subscriber | Chỉ tạo handler bean mà không đăng ký endpoint | Kiểm tra input channel và consumer |
| Gửi `String` JSON mà `INSERT` lỗi | Handler chờ `@Table` entity | Thêm JSON-to-entity transformer |
| `query(...)` không bind được | Thiếu `parameterExpressions`, SpEL sai, type không phù hợp | So sánh tên `:param` với map và message |
| `Statement<?>` bị class cast lỗi | Mode/payload không tương thích | Kiểm tra `Type.STATEMENT` và source của statement |
| Lỗi table/keyspace | Schema chưa tồn tại hoặc session vào keyspace khác | Kiểm tra keyspace, migrations, `DESCRIBE TABLE` |
| Lỗi CodecNotFound | CQL column và Java value không có codec phù hợp | Đối chiếu Cassandra schema và driver codecs |
| `send()` trả true nhưng không thấy row | Handler async, lỗi xảy ra sau, tra sai key | Đo completion, error channel, query theo partition key |
| Data bị thay đổi sau retry | INSERT upsert cùng key với payload khác | So sánh event contract, kiểm tra immutable payload |
| Query timeout/overloaded | Partition nóng, batch lớn, in-flight cao | Driver/node metrics, p95/p99, số task |
| TTL làm dữ liệu biến mất | WriteOptions/CQL TTL quá ngắn | Đối chiếu retention policy, table TTL |
| Gateway không có reply | Vẫn dùng adapter một chiều hoặc reply channel không có consumer | Kiểm tra `producesReply` và output channel |
| JMS source không redeliver khi Cassandra lỗi | Async boundary hoặc exception bị error flow hấp thụ | Kiểm tra acknowledgment/transaction đường nguồn |
| Stop ứng dụng mất pending work | Operation async chưa được drain; in-memory buffer | Shutdown test, durable source, idempotent replay |

### Những metric nên đo

| Metric | Ý nghĩa vận hành |
|---|---|
| Spring Message input rate | Tốc độ message đi vào handler |
| Cassandra writes/queries completed | Operation thực sự hoàn thành |
| Cassandra errors theo loại | Timeout, unavailable, auth, syntax, mapping |
| Operation latency p50/p95/p99 | Độ trễ client/cluster, không chỉ tốc độ `send()` |
| In-flight requests | Phát hiện không giới hạn concurrency |
| Retry count/elapsed time | Nguy cơ retry storm khi cluster degraded |
| JMS queue depth / Kafka lag | Backpressure và backlog nguồn |
| Hot partition/compaction/tombstone | Vấn đề data model, TTL và delete |
| Duplicate/conflicting event IDs | Chất lượng dữ liệu và idempotency |
| Gateway reply/error rate | Kiểm tra reply và error path có hoạt động |

Hãy log `eventId`, `operationType`, keyspace/table, trace/correlation ID và loại exception; tránh log nguyên payload có PII hoặc credentials. Không đưa statement CQL chứa giá trị nhạy cảm vào log ở mức debug trên production.

## 17. Thực hành: kiểm chứng CassandraMessageHandler từ đầu đến cuối

**Môi trường:** Java 17+, Spring Integration Cassandra, Spring Data Cassandra reactive, một Cassandra test node/container, keyspace/table `shop_integration.order_event` từ mục 4. Mỗi bài thử chỉ bật **một endpoint nhận cùng input channel** để tránh ghi trùng ngoài chủ ý.

### Bài A — Handler bean trực tiếp

1. Khởi tạo `ReactiveCassandraOperations` kết nối tới cluster test.
2. Tạo `CassandraMessageHandler(operations, Type.INSERT)`, bật `setAsync(false)` và gắn `@ServiceActivator(inputChannel="cassandraWriteInput")`.
3. Gửi `OrderEvent("evt-2001", "ORD-2001", "OrderPaid", json)` qua `MessageChannel`.
4. Dùng `cqlsh` kiểm tra:

~~~sql
SELECT event_id, order_id, event_type
FROM shop_integration.order_event
WHERE event_id = 'evt-2001';
~~~

5. Gửi lại cùng `eventId`, quan sát upsert; thay payload thành event khác cùng ID và giải thích nguy cơ phá contract immutable.

### Bài B — Java DSL so với @ServiceActivator

1. Thay handler bean trực tiếp bằng flow `Cassandra.outboundChannelAdapter(...)`.
2. Xác nhận dữ liệu được lưu giống mục A khi dùng cùng entity.
3. Chuyển mode sang `UPDATE` trên một handler riêng; quan sát CQL semantics theo entity.
4. Dùng `DELETE` trên **dữ liệu test** và giải thích tombstones.
5. Đảm bảo endpoint một chiều không gửi Spring reply.

### Bài C — Named query và statement processor

1. Tạo gateway `SELECT ... WHERE event_id = :eventId`, bind `eventId` từ payload.
2. Gửi một ID có dữ liệu và một ID không tồn tại; quan sát loại payload/result thực tế ở reply channel.
3. Gửi ID không hợp lệ để kiểm tra validation và error path.
4. Chạy `statementFunction(...)` dùng `SimpleStatement.newInstance` với bind values.
5. Thử đưa một giá trị có dấu nháy vào payload và xác nhận **nó là value**, không được nối thành CQL syntax.

### Bài D — Ingest matrix và batch

1. Cấu hình `setIngestQuery("INSERT ... VALUES (?, ?, ?, ?)")`.
2. Gửi một `List<List<Object>>` gồm hai hàng đúng kiểu, truy vấn lại từng `event_id`.
3. Gửi hàng thiếu một value, kiểm tra lỗi được đưa ra rõ ràng.
4. Chạy với số hàng 2, 20, 100 và so sánh latency/heap; không giả định batch lớn nhanh hơn.
5. Test payload `null` với cấu trúc dữ liệu hỗ trợ null thay vì `List.of(...)`.

### Bài E — Async, reply và lỗi

1. Với Cassandra hoạt động, so sánh thời điểm `send()` trả về ở `async(true)` và `async(false)`.
2. Ngắt kết nối Cassandra trong lúc ghi; kiểm tra sync exception và async error path.
3. Chạy `Cassandra.outboundGateway(...)`, xác nhận có reply trong flow.
4. Chạy gateway async với `FluxMessageChannel` phù hợp; ghi nhận publisher/result và loại payload.
5. Test một handler bật `producesReply(true)` nhưng không có output/reply channel, rồi sửa cấu hình đúng.

### Bài F — Nguồn JMS, duplicate và shutdown

1. Nối JMS inbound transacted qua `DirectChannel` tới Cassandra sync handler.
2. Cho Cassandra thất bại, quan sát JMS rollback/redelivery khi exception được propagate.
3. Bật Cassandra async hoặc chèn `ExecutorChannel`; quan sát source callback có thể kết thúc trước DB completion.
4. Cho Cassandra ghi thành công rồi mô phỏng crash trước source ack, gửi lại `eventId`; xác minh dữ liệu event bất biến.
5. Dừng ứng dụng khi có nhiều requests in-flight và kiểm tra chính sách drain/recovery.

### Tiêu chí hoàn thành

| Kiểm tra | Kết quả PASS |
|---|---|
| Handler được đăng ký | Spring Message đến đúng `CassandraMessageHandler` |
| Entity INSERT | CQL row có key và values đúng |
| JSON contract | Payload JSON được transform/validate trước handler entity |
| Mode selection | INSERT/UPDATE/DELETE/STATEMENT có endpoint phù hợp |
| Named parameters | `:eventId` được bind từ Spring Message, không nối chuỗi |
| Ingest | Matrix đúng kích thước/kiểu, không batch vô hạn |
| Async vs sync | Đo completion/error boundary khác nhau |
| Gateway reply | Chỉ sinh reply khi `producesReply=true` và có reply path |
| Failure handling | Lỗi được ghi nhận, có retry/backoff phù hợp |
| Idempotency | Retry cùng event không tạo business side effect sai |
| Shutdown/recovery | Không giả định operations in-flight tự được giữ bền vững |

Với Cassandra consistency, timeout, batch và gateway output, **phải chạy integration test với Cassandra thật hoặc test container**. Unit test với mock `ReactiveCassandraOperations` chỉ kiểm tra tương tác API; không chứng minh Cassandra đã persist hay delivery semantics của hệ thống nguồn.

## 18. Câu hỏi tự đánh giá

1. `CassandraMessageHandler` nhận kiểu Spring input nào và dùng API nào để làm việc với Cassandra?
2. Vì sao lớp này kế thừa `AbstractReplyProducingMessageHandler` nhưng vẫn mặc định một chiều?
3. Hai constructor khác nhau ở tham số nào?
4. `setProducesReply(true)` có tự tạo một output channel nếu chưa cấu hình không?
5. Mặc định `async=true` ảnh hưởng thế nào đến `MessageChannel.send()`?
6. Khi nào nên dùng `setAsync(false)` và rủi ro của nó với WebFlux event-loop?
7. Mode `INSERT` cần payload gì, và vì sao JSON `String` không luôn phù hợp?
8. Lý do gì để dùng `Type.STATEMENT` thay vì entity mapping?
9. `setQuery(...)` làm thay đổi mode ra sao? `setParameterExpressions(...)` dùng khi nào?
10. `setStatementProcessor(...)` và `setStatementExpressionString(...)` khác nhau ở việc tạo statement như thế nào?
11. `setIngestQuery(...)` yêu cầu cấu trúc payload nào?
12. Vì sao không nên dùng batch unbounded trên nhiều partitions?
13. `WriteOptions.ttl(...)` khác JMS message TTL ở đâu?
14. Cassandra `INSERT` có tự chặn bản ghi trùng khóa không?
15. Khi source JMS đã ack rồi Cassandra async write lỗi, điều gì xảy ra?
16. Một Cassandra timeout có chứng minh server chưa ghi dữ liệu không?
17. Vì sao idempotent event log cần `eventId` ổn định và payload bất biến?
18. Nếu muốn SELECT ra nhiều hàng, tại sao nên kiểm tra kiểu reply và dùng reactive output channel phù hợp?

## 19. Tài liệu tham khảo

- [Spring Integration Reference — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): giới thiệu `CassandraMessageHandler`, hai chế độ adapter/gateway, async, các mode, ingest và statement.
- [Spring Integration API — CassandraMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/outbound/CassandraMessageHandler.html): constructors, `setIngestQuery`, `setQuery`, `setStatementProcessor`, `setWriteOptions` và `setProducesReply`.
- [Spring Integration API — CassandraMessageHandler.Type](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/outbound/CassandraMessageHandler.Type.html): enum INSERT/UPDATE/DELETE/STATEMENT.
- [Spring Integration API — CassandraMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/CassandraMessageHandlerSpec.html): Java DSL `ingestQuery`, `parameter`, `statementFunction`, `query` và `writeOptions`.
- [Spring Integration API — Cassandra DSL Factory](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/Cassandra.html): `outboundChannelAdapter(...)` và `outboundGateway(...)`.
- [Spring Data Cassandra Reference — Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): reactive operations, subscription và error handling.
- [Spring Data Cassandra API — WriteOptions](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/WriteOptions.html): TTL và cấu hình write options.
- [Apache Cassandra Documentation](https://cassandra.apache.org/doc/latest/): CQL, data modeling, consistency, replication, TTL và lightweight transaction.

**Ghi nhớ:** `CassandraMessageHandler` là **cầu nối Spring Message → ReactiveCassandraOperations**. Handler hỗ trợ **INSERT/UPDATE/DELETE/STATEMENT**, mặc định **async** và **không trả reply**; chỉ bật `producesReply`/gateway khi cần kết quả. Đặt đúng payload contract, query parameters và write options; kiểm soát lỗi async, idempotency và source acknowledgement. Một thông báo đã đi qua `MessageChannel` không tự chứng minh Cassandra đã ghi thành công, đặc biệt khi xử lý reactive hoặc có lỗi mạng.




