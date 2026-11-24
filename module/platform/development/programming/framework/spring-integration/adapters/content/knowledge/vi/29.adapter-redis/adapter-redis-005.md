# Redis outbound channel adapter

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **Redis outbound channel adapter** chuyển một **Spring Integration Message** thành bản tin Redis **Pub/Sub** bằng lệnh **PUBLISH**, và vì sao nó là một endpoint **một chiều**.
- Sử dụng đúng **RedisPublishingMessageHandler** và **Redis.outboundChannelAdapter(...)**, phân biệt với Redis **queue**, **store**, **stream** outbound và các Redis outbound **gateway**.
- Cấu hình **RedisConnectionFactory**, **MessageChannel**, **MessageConverter**, **RedisSerializer**, topic cố định hoặc **topic-expression** để chọn kênh đích.
- Thiết kế hợp đồng payload có **eventId, eventType, schemaVersion**, UTF-8/JSON, namespace của topic và quy tắc bảo mật.
- Nắm giới hạn delivery của Redis Pub/Sub: **không có subscriber backlog, ACK, retry bền vững hay replay cho consumer offline**.
- Đọc đúng ý nghĩa lệnh PUBLISH trả về số subscribers mà **không coi đó là xác nhận xử lý nghiệp vụ**.
- Xử lý lỗi conversion, Redis connection, dynamic routing, downstream failures; theo dõi metrics, lifecycle và bảo mật.
- Xây dựng integration test với Redis thật, chủ động kiểm tra subscriber readiness, nhiều replicas, lost notification, topic routing và malformed payload.
- Lựa chọn Redis List/Streams, AMQP, Kafka, JMS hoặc transactional outbox khi sự kiện phải được bảo đảm đến nơi.

## 1. Bối cảnh: phát notification từ một Spring Integration flow

Giả sử **CatalogService** cập nhật giá sản phẩm trong database. Sau khi thay đổi được commit, các instance của **SearchService** cần biết sản phẩm nào nên xóa cache cục bộ.

~~~mermaid
flowchart LR
    DB[("Catalog database")] --> EVT["PriceChanged event"]
    EVT --> CH["Spring Integration<br/>priceChangedOutbound"]
    CH --> A["Redis outbound<br/>channel adapter"]
    A -->|"PUBLISH"| R["Redis Pub/Sub<br/>catalog.price.changed"]
    R --> B["Search replica A"]
    R --> C["Search replica B"]
    R --> D["Search replica C"]
~~~

Spring Integration cung cấp **Redis outbound channel adapter** để chuyển thông điệp gửi từ **MessageChannel** thành một bản tin Redis Pub/Sub. Thành phần triển khai chính là **RedisPublishingMessageHandler**; với Java DSL, cấu hình bằng **Redis.outboundChannelAdapter(redisConnectionFactory)**.

Tại ranh giới này, adapter nhận một Spring Message, xác định Redis topic, chuyển nội dung bằng **MessageConverter/RedisSerializer**, rồi yêu cầu Redis **PUBLISH**. Nó **không** chờ SearchService gửi reply, không yêu cầu mỗi subscriber ACK, không tự giữ thông điệp cho subscriber đang offline.

**Điều quan trọng nhất:** Nếu SearchService B đang restart khi notification được PUBLISH, Redis Pub/Sub không giữ một bản riêng cho B để phát sau. Vì vậy case **cache invalidation** cần kết hợp TTL/version/reconciliation; còn đơn hàng hoặc thanh toán bắt buộc không được mất cần một cơ chế giao nhận bền vững hơn.

Bài học nằm trong chương **Adapter Redis** của module **SPRING_INTEGRATION_ADAPTERS**: kết nối hệ thống ngoài vào Spring Integration bằng inbound/outbound adapter, gateway, poller và MessageChannel; kết hợp với File, SFTP, HTTP, JMS, AMQP, Kafka, cơ sở dữ liệu. Chủ đề trực tiếp của bài là **Redis Pub/Sub outbound channel adapter**; các Redis queue/store/stream chỉ được dùng để so sánh và chọn công cụ thích hợp, không thay thế nội dung chính.

## 2. Redis Pub/Sub: lệnh PUBLISH làm và không làm gì?

Redis Pub/Sub định tuyến thông báo theo **topic/channel name** là chuỗi:

~~~text
Producer:
  PUBLISH catalog.price.changed <payload bytes>

Redis:
  gửi đến các clients đang SUBSCRIBE channel đó
  hoặc PSUBSCRIBE pattern khớp channel

Subscriber:
  nhận notification khi đang subscribe/kết nối hợp lệ
~~~

Ví dụ trên Redis CLI ở **môi trường test**:

~~~bash
# Terminal 1: subscribe trước
redis-cli SUBSCRIBE catalog.price.changed

# Terminal 2: publish sau
redis-cli PUBLISH catalog.price.changed '{"eventId":"evt-price-1001","productId":"P-1001"}'
~~~

Nếu Terminal 1 đang subscribe đúng Redis server/channel, nó nhận thông điệp. Nếu chạy PUBLISH trước khi Terminal 1 subscribe, không có lịch sử để subscriber mới đọc lại.

### 2.1. PUBLISH không ghi một Redis key/List/Stream

| Redis operation | Nguồn đích | Độ bền/replay |
| --- | --- | --- |
| **PUBLISH** | Channel Pub/Sub | Không giữ backlog cho subscriber offline |
| **LPUSH/RPUSH** | Redis List key | Item chưa POP có thể còn trong List |
| **XADD** | Redis Stream key | Record có ID, retention, consumer-group recovery nếu thiết kế đúng |
| **SET/HSET/ZADD** | Redis key/value, Hash, ZSET | Ghi trạng thái/collection, không tự là Pub/Sub notification |

Một channel tên **catalog.price.changed** không phải một Redis List hay Stream. Lệnh **LLEN catalog.price.changed** không đo “số notification chưa gửi”; với một channel Pub/Sub bình thường **không tồn tại queue depth của subscriber**.

### 2.2. Một chiều là gì?

~~~mermaid
sequenceDiagram
    participant C as CatalogService
    participant O as Redis outbound adapter
    participant R as Redis
    participant S as SearchService
    C->>O: Message(payload, headers)
    O->>R: PUBLISH topic body
    R-->>S: Pub/Sub notification (nếu online)
    Note over C,S: Không có application reply/consumer ACK
~~~

Vì adapter là **one-way outbound endpoint**, nó không có **replyChannel** như request–reply gateway. Nếu nghiệp vụ cần gọi và nhận kết quả tức thời, cân nhắc HTTP/JMS/AMQP gateway hoặc cơ chế request–reply được thiết kế riêng.

### 2.3. PUBLISH trả về gì?

Redis PUBLISH thường trả **số clients được gửi bản tin theo ngữ nghĩa server/lệnh**, không phải số business handlers đã commit hoặc số replicas đã áp dụng cache invalidation thành công.

~~~text
PUBLISH result = 2
  != 2 services đã update cache
  != 2 database transactions đã commit
  != event đã được lưu bền để retry
~~~

Trong Redis Cluster/sharded Pub/Sub, ý nghĩa chi tiết của số subscribers và phạm vi node có thể phụ thuộc topology/lệnh; không dùng giá trị này làm bằng chứng end-to-end.

### 2.4. At-most-once transport không bảo đảm exactly-once business

Redis Pub/Sub không có broker-native ACK/replay: một message có thể **bị mất** khi subscriber offline hoặc lỗi sau callback. Nhưng business event vẫn có thể **xử lý trùng** nếu producer publish lại, bridge retry, topic pattern chồng nhau hoặc subscriber logic chạy nhiều lần.

**At-most-once ở một lần publish không đồng nghĩa eventId chỉ có một lần side effect.**

## 3. Redis outbound channel adapter nằm ở đâu trong hệ Spring Integration?

~~~mermaid
flowchart LR
    SRC["File/SFTP/HTTP/JDBC<br/>source"] --> F["IntegrationFlow"]
    F --> V["Validate / transform"]
    V --> ROUTE["Route/topic decision"]
    ROUTE --> M["MessageChannel"]
    M --> HAND["RedisPublishingMessageHandler"]
    HAND --> SER["MessageConverter<br/>RedisSerializer"]
    SER --> REDIS["Redis PUBLISH"]
~~~

### 3.1. Các thành phần và trách nhiệm

| Thành phần | Vai trò |
| --- | --- |
| **IntegrationFlow** | Xác định luồng message từ nguồn tới đích |
| **MessageChannel** | Ranh giới chuyển Spring Message giữa các endpoint |
| **RedisPublishingMessageHandler** | Outbound handler chọn topic và thực hiện Redis publish |
| **RedisConnectionFactory** | Cung cấp connection Redis cho handler |
| **MessageConverter** | Chuyển đổi biểu diễn Spring Message ↔ dữ liệu cần gửi theo chiến lược |
| **RedisSerializer** | Encode giá trị trước khi gửi bytes tới Redis |
| **RedisInboundChannelAdapter** | Ở app subscriber khác, nhận Redis Pub/Sub vào Spring flow |
| **Service activator/transformer** | Validate, xây event, quyết định business semantics |

### 3.2. Không cần poller ở outbound adapter

Outbound endpoint nhận messages từ input channel. Nó **không định kỳ poll Redis**. Poller chỉ xuất hiện nếu **nguồn trước đó** cần polling (File/SFTP/JDBC inbound) hoặc downstream là một pollable channel cần consumer.

~~~text
SFTP poller -> CSV parser -> MessageChannel
                               -> Redis outbound adapter -> PUBLISH
~~~

Trong ví dụ này **SFTP inbound** được poll, không phải Redis PUBLISH.

### 3.3. Khi nào cần inbound adapter tương ứng?

Phía SearchService cần Redis Pub/Sub inbound adapter subscribe đúng topic. Có thể viết bằng Spring Integration **Redis.inboundChannelAdapter(...)** hoặc **RedisInboundChannelAdapter**. Nó không đọc Redis List và không chờ XREADGROUP.

### 3.4. Redis publish-subscribe channel là phương án khác

Spring Integration còn cung cấp **Redis-backed PublishSubscribeChannel** giúp kết nối subscribers/producers qua cùng Redis topic. Đó là một channel abstraction riêng; không cần vừa đăng ký Redis-backed channel vừa thêm outbound adapter phát cùng một message vào chính topic đó nếu không muốn duplicate.

## 4. So sánh outbound adapter và gateway/adapter Redis khác

| Endpoint | Hành động Redis | Dùng khi |
| --- | --- | --- |
| **Redis outbound channel adapter** | **PUBLISH** một Pub/Sub notification | Broadcast best-effort, ví dụ invalidate cache |
| **Redis queue outbound channel adapter** | Push vào Redis **List** | Đưa work item cho competing consumers |
| **RedisStore outbound channel adapter** | Ghi vào LIST/SET/ZSET/MAP/PROPERTIES | Cập nhật collection/state |
| **Redis Stream outbound channel adapter** | Ghi bản ghi vào Redis **Stream** | Cần record IDs và consumption có backlog/replay |
| **Redis outbound command gateway** | Thực thi lệnh Redis, nhận kết quả | Query/increment/command request–reply |
| **Redis queue outbound gateway** | Tạo request/reply theo queue protocol | Cần kết quả RPC-like, có timeout/correlation |

Tên gọi của các endpoint không thay **delivery guarantee**: kể cả Spring Message đã tới outbound adapter, PUBLISH vẫn không lưu backlog cho subscriber offline.

### 4.1. Đừng chọn PUBLISH cho một công việc cần worker duy nhất

Nếu ba replicas SearchService đều subscribe, một PUBLISH có thể đến **cả ba**, phù hợp khi mỗi replica có local cache cần invalidate. Nhưng nếu ba workers đều gọi thanh toán thì side effect có thể bị lặp theo số replicas. Với work distribution, chọn queue/stream consumer group có semantics phù hợp.

### 4.2. Đừng nhầm thành Redis Streams vì message là event

Một event JSON gửi qua PUBLISH vẫn chỉ là **Pub/Sub notification**. Nó không tự có **record ID, PEL, XACK, replay** như Redis Streams.

## 5. Dependencies và RedisConnectionFactory

Với Spring Boot, Maven dependencies minh họa:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-redis</artifactId>
    </dependency>
</dependencies>
~~~

Sử dụng **Spring Boot BOM/dependency management** để tránh trộn phiên bản Spring Integration, Spring Data Redis và Redis client. Cấu hình Spring Boot local/test:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 3s
      timeout: 3s
~~~

Đây không phải cấu hình production: cần bổ sung TLS, ACL, credentials từ secret manager, failover/Sentinel/Cluster và timeouts phù hợp. Tên properties có thể khác theo thế hệ Spring Boot.

### 5.1. RedisConnectionFactory khác Spring MessageChannel

**RedisConnectionFactory** cung cấp kết nối để thực hiện Redis PUBLISH. **MessageChannel** là ranh giới nội bộ truyền thông điệp đến handler. Bạn có thể gửi một Spring Message vào DirectChannel dù Redis đang offline; thao tác gửi sau đó có thể **ném exception** nếu handler không publish được.

### 5.2. Không cần khai báo Redis topic trước

Khác Redis Stream hoặc List key, topic Pub/Sub thông thường là một địa chỉ string. Bạn không cần XGROUP CREATE, LPUSH, XADD hoặc tạo key trước khi PUBLISH. Nhưng **subscriber cần đăng ký đang hoạt động** nếu muốn nhận message.

### 5.3. Cùng Redis host chưa đủ

Producer và subscriber cần thống nhất:

- Redis **deployment/topology** thật sự đang kết nối.
- **Topic name** chính xác, có phân biệt chữ hoa/thường.
- Quyền PUBLISH/SUBSCRIBE của Redis users.
- Redis classic Pub/Sub hay sharded Pub/Sub ở môi trường Cluster.
- **Payload serialization/charset** và event schema.
- Thời điểm subscriber active, network và lifecycle.

**Không dùng Redis database index như một biên cô lập Pub/Sub giống RabbitMQ virtual host.** Thiết kế namespace/ACL/instance isolation rõ ràng.

## 6. Java DSL: publish notification lên topic cố định

Ví dụ sử dụng **Redis.outboundChannelAdapter(redisConnectionFactory)** từ Spring Integration Redis DSL. Cho topic **catalog.price.changed** cố định và payload là một String JSON đã được validate/encode bằng UTF-8.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.redis.dsl.Redis;
import org.springframework.integration.support.converter.SimpleMessageConverter;

@Configuration
@EnableIntegration
public class CatalogRedisPublishFlow {

    @Bean
    public IntegrationFlow catalogPricePublishFlow(
            RedisConnectionFactory connectionFactory) {

        return IntegrationFlow.from("priceChangedOutbound")
            .handle(Redis.outboundChannelAdapter(connectionFactory)
                .topic("catalog.price.changed")
                .serializer(new StringRedisSerializer())
                .messageConverter(new SimpleMessageConverter()))
            .get();
    }
}
~~~

**Lưu ý API và converter:** Các phương thức **topic**, **serializer**, **messageConverter** thuộc RedisOutboundChannelAdapterSpec ở những phiên bản Spring Integration tương ứng. **SimpleMessageConverter** của Spring Integration được dùng trong ví dụ như cách chuyển message/payload; serializer tường minh là **StringRedisSerializer**. Khi dùng phiên bản khác, kiểm tra package/class import và biên dịch bằng BOM thực. Nếu producer gửi object khác String/byte[] thì phải xác nhận converter + serializer thật sự hỗ trợ; không cho rằng một POJO bất kỳ tự thành JSON.

### 6.1. MessageChannel được tạo ra sao?

Trong Java DSL, **IntegrationFlow.from("priceChangedOutbound")** tham chiếu một input channel tên priceChangedOutbound. Nếu ứng dụng có flow khác gửi tới đây, hai flow được kết nối qua channel đó.

Ví dụ muốn khai báo channel rõ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class CatalogOutboundChannels {

    @Bean
    public MessageChannel priceChangedOutbound() {
        return new DirectChannel();
    }
}
~~~

**DirectChannel** dispatch handler đồng bộ trong đường gửi message, phù hợp khi publish nhanh và muốn exception phản ánh ngay tới caller. Nhưng thành công của DirectChannel.send **không phải consumer ACK**.

### 6.2. Gửi Spring Message từ service

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class CatalogPriceEventEmitter {

    private final MessageChannel priceChangedOutbound;

    public CatalogPriceEventEmitter(
            @Qualifier("priceChangedOutbound")
            MessageChannel priceChangedOutbound) {
        this.priceChangedOutbound = priceChangedOutbound;
    }

    public void emitJson(String validatedJson) {
        if (validatedJson == null || validatedJson.isBlank()) {
            throw new IllegalArgumentException("JSON must not be blank");
        }

        boolean accepted = priceChangedOutbound.send(
            MessageBuilder.withPayload(validatedJson).build());

        if (!accepted) {
            throw new IllegalStateException(
                "Spring MessageChannel did not accept event");
        }
    }
}
~~~

**accepted=true** nghĩa là Spring MessageChannel chấp nhận message theo contract của channel; nó **không xác minh SearchService đã nhận hoặc đã xóa cache**. Nếu Redis PUBLISH thất bại ở handler đồng bộ, exception có thể lan tới caller.

### 6.3. Hợp đồng String JSON

Một message mẫu:

~~~json
{
  "eventId": "evt-price-1001",
  "eventType": "PRODUCT_PRICE_CHANGED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "data": {
    "productId": "P-1001",
    "productVersion": 42
  }
}
~~~

Đối với notification cache, **không nhất thiết nhúng giá mới**: consumer nhận productId/version, invalidate rồi đọc lại **database/catalog API** để tránh áp state cũ nếu events đến/được xử lý lệch thứ tự.

### 6.4. Dòng dữ liệu qua adapter

~~~mermaid
sequenceDiagram
    participant S as CatalogPriceEventEmitter
    participant MC as priceChangedOutbound
    participant RA as RedisPublishingMessageHandler
    participant RED as Redis
    S->>MC: send(Message<String JSON>)
    MC->>RA: handleMessage
    RA->>RA: topic + convert + serialize
    RA->>RED: PUBLISH catalog.price.changed bytes
    RED-->>RA: publish command result
    RA-->>S: handler returns
    Note over S,RED: Không có consumer-level reply
~~~

### 6.5. Tránh tự gửi trong constructor

Không emit event khi Spring context chưa start và adapter/subscriber/test chưa sẵn sàng. Đối với sự kiện nghiệp vụ, gửi sau khi **nguồn dữ liệu đã commit** theo transaction boundary phù hợp. Lifecycle của Spring Integration endpoints và Redis connection phải được kiểm thử trong startup/shutdown.

## 7. Cấu hình Java bean: RedisPublishingMessageHandler

Nếu không dùng DSL, có thể tạo MessageHandler trực tiếp. Đây là một cách cấu hình **thay thế**, không nên chạy đồng thời với flow DSL trên cùng input channel và topic khi muốn mỗi event chỉ publish một lần.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.redis.outbound.RedisPublishingMessageHandler;
import org.springframework.integration.support.converter.SimpleMessageConverter;

@Configuration
public class CatalogRedisPublishingHandlerConfig {

    @Bean
    @ServiceActivator(inputChannel = "priceChangedOutbound")
    public RedisPublishingMessageHandler catalogRedisPublisher(
            RedisConnectionFactory connectionFactory) {

        RedisPublishingMessageHandler handler =
            new RedisPublishingMessageHandler(connectionFactory);

        handler.setTopic("catalog.price.changed");
        handler.setSerializer(new StringRedisSerializer());
        handler.setMessageConverter(new SimpleMessageConverter());
        return handler;
    }
}
~~~

**So sánh:** DSL và direct bean dùng cùng **RedisPublishingMessageHandler**, chỉ khác cách wiring endpoint. Với @ServiceActivator, Spring Integration tạo consumer endpoint nối input channel đến handler. Không cần poller khi input là DirectChannel; chỉ thêm poller nếu có QueueChannel nội bộ cần poll.

### 7.1. XML namespace

Với project dùng Spring Integration XML:

~~~xml
<int-redis:outbound-channel-adapter
    id="redisPricePublisher"
    channel="priceChangedOutbound"
    topic="catalog.price.changed"
    message-converter="priceMessageConverter"/>
~~~

Bean **priceMessageConverter** cần được khai báo theo policy serialization cụ thể; XML snippet chỉ minh họa cú pháp endpoint, không phải ApplicationContext đầy đủ. XML hỗ trợ **topic** hoặc **topic-expression**, nhưng hai cách xác định topic đó **mutually exclusive**.

### 7.2. Vì sao không dùng một outbound gateway?

RedisPublishingMessageHandler là **MessageHandler một chiều**. Nó không tạo reply Spring Message chứa số subscribers hoặc response của downstream. Nếu cần kết quả command Redis, **Redis outbound command gateway** là thành phần khác; tuy nhiên ngay cả trả về số subscribers cũng không phải consumer business ACK.

## 8. Dynamic topic: topicExpression và chọn đúng kênh

Không phải mọi thông báo đều phát trên một topic. Ví dụ CatalogService có thể gửi:

~~~text
catalog.price.changed
catalog.product.deleted
catalog.inventory.changed
~~~

**RedisPublishingMessageHandler** hỗ trợ **setTopic(String)** cho topic cố định và **setTopicExpression(Expression)** cho topic động. DSL tương ứng có **topic(String)**, **topicExpression(String/Expression)**, và một số phiên bản có **topicFunction(...)**.

### 8.1. Expression đọc một header đáng tin cậy

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.redis.dsl.Redis;
import org.springframework.integration.support.converter.SimpleMessageConverter;

@Configuration
public class CatalogDynamicTopicFlow {

    @Bean
    public IntegrationFlow catalogDynamicPublishFlow(
            RedisConnectionFactory factory) {

        return IntegrationFlow.from("catalogDynamicOutbound")
            .handle(Redis.outboundChannelAdapter(factory)
                .topicExpression("headers['redisTopic']")
                .serializer(new StringRedisSerializer())
                .messageConverter(new SimpleMessageConverter()))
            .get();
    }
}
~~~

Ở đây **headers['redisTopic']** được đánh giá cho từng Spring Message. Nó **không phải cú pháp tên topic Redis**; đó là **SpEL** tại endpoint Java. Kết quả expression phải là một topic hợp lệ theo API, và phải chịu kiểm tra policy namespace trước khi publish.

### 8.2. Producer nên dùng enum/allowlist

~~~java
public enum CatalogEventTopic {
    PRICE_CHANGED("catalog.price.changed"),
    PRODUCT_DELETED("catalog.product.deleted"),
    INVENTORY_CHANGED("catalog.inventory.changed");

    private final String channel;

    CatalogEventTopic(String channel) {
        this.channel = channel;
    }

    public String channel() {
        return channel;
    }
}
~~~

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class CatalogDynamicPublisher {

    private final MessageChannel outbound;

    public CatalogDynamicPublisher(
            @Qualifier("catalogDynamicOutbound") MessageChannel outbound) {
        this.outbound = outbound;
    }

    public void publish(CatalogEventTopic eventTopic, String json) {
        if (eventTopic == null || json == null || json.isBlank()) {
            throw new IllegalArgumentException("Invalid event");
        }

        boolean sent = outbound.send(
            MessageBuilder.withPayload(json)
                .setHeader("redisTopic", eventTopic.channel())
                .build());
        if (!sent) {
            throw new IllegalStateException("Outbound channel rejected event");
        }
    }
}
~~~

**Điểm an toàn:** Chỉ những giá trị trong enum được đặt vào header routing. **Không** nhận raw channel name từ URL/JSON của người dùng rồi dùng trực tiếp làm Redis topic: điều đó có thể phát dữ liệu lên topic của tenant khác hoặc lộ thông tin cho subscribers không được phép.

### 8.3. topic và topic-expression mutually exclusive

| Cấu hình | Khi nào dùng |
| --- | --- |
| **topic("catalog.price.changed")** | Mọi message cùng một kênh, dễ review và giới hạn quyền |
| **topicExpression("headers['redisTopic']")** | Một endpoint chọn kênh theo metadata đã validate |
| **topicFunction(...)** | Trong version hỗ trợ, logic Java typed để chọn topic |

**Không cấu hình đồng thời topic cố định và topic-expression** trên cùng handler với kỳ vọng expression override có kiểm soát. Hãy chọn một cách định tuyến cho một endpoint.

### 8.4. Topic prefix cho môi trường

~~~text
dev.catalog.price.changed
staging.catalog.price.changed
prod.catalog.price.changed
~~~

Prefix hỗ trợ quan sát và giảm nhầm lẫn, nhưng **prefix không tự là authentication/authorization**. Redis ACL, network isolation và chính sách phân quyền producer/subscriber vẫn quan trọng.

### 8.5. Nếu không muốn dynamic topic

Với số topic cố định nhỏ, có thể dùng **Spring Integration router** gửi message vào nhiều outbound channels, mỗi channel có một handler/topic cố định. Cách này dễ audit/ACL hơn một SpEL expression quá linh hoạt. Chỉ thêm complexity khi nhu cầu thật sự cần.

## 9. MessageConverter và RedisSerializer khác nhau thế nào?

Redis Pub/Sub truyền **channel string và body bytes**. Spring Message lại có **payload và headers**. Hai bước chuyển đổi thường cần kiểm soát:

~~~mermaid
flowchart LR
    SM["Spring Message<br/>payload+headers"] --> CV["MessageConverter"]
    CV --> OB["Object / payload representation"]
    OB --> SE["RedisSerializer"]
    SE --> BY["Redis Pub/Sub body bytes"]
    BY --> RED["PUBLISH topic bytes"]
~~~

### 9.1. MessageConverter

MessageConverter của Spring Messaging giúp xác định cách chuyển từ Spring Message sang biểu diễn phù hợp. Spring Integration có **SimpleMessageConverter** nhưng không mặc định biến mọi POJO thành JSON theo schema bạn muốn.

Nếu cần chuyển DTO thành JSON, nên thực hiện qua **transformer minh bạch** trước outbound adapter hoặc một converter được cấu hình/test rõ; không dựa vào **toString()** của DTO để tạo payload trao đổi liên dịch vụ.

### 9.2. RedisSerializer

RedisSerializer quyết định cách Java value được biến thành **byte[]** để gửi tới Redis. Với message JSON String, dùng **StringRedisSerializer UTF-8**:

~~~java
handler.setSerializer(new StringRedisSerializer());
~~~

Nếu payload là byte[] thô hoặc một object phức tạp, phải chọn serializer tương thích và test byte-for-byte với subscriber. Không ngộ nhận **JsonRedisSerializer cho một String đã chứa JSON** luôn cho cùng wire bytes như StringRedisSerializer: nó có thể thêm lớp JSON-escaping/quotes.

### 9.3. Những biến thể wire format

| Producer payload | Serializer/strategy | Redis body có thể là |
| --- | --- | --- |
| String JSON | StringRedisSerializer | Bytes UTF-8 của JSON object |
| String JSON | JSON serializer serialize String | JSON string literal có escape và quotes |
| Java POJO | JDK serialization | Binary Java serialized bytes, không phù hợp cross-language |
| Java POJO | DTO → JSON transformer → String serializer | JSON UTF-8 theo schema |
| byte[] | Pass-through bytes strategy | Raw bytes theo binary contract |

**Không đoán định dạng payload từ class Redis outbound channel adapter.** Hãy kiểm tra converter, serializer của producer, raw Redis payload và deserializer của subscriber.

### 9.4. Redis không tự truyền mọi Spring MessageHeaders

Redis Pub/Sub thường chỉ mang **channel** và **body**. Các header như:

~~~text
MessageHeaders.ID
MessageHeaders.TIMESTAMP
contentType
correlationId
tenantId
replyChannel
errorChannel
~~~

không tự biến thành metadata độc lập của Redis Pub/Sub. Nếu cần eventId, traceparent, schemaVersion, originService hoặc tenantRef ở phía nhận, đặt chúng trong **event envelope** đã định nghĩa, hoặc dùng một converter/mapper có cùng hợp đồng cả hai đầu.

**Không đưa các runtime headers nhạy cảm** như replyChannel/errorChannel/callback object vào serialized body một cách vô điều kiện.

### 9.5. Envelope liên dịch vụ khuyến nghị

~~~json
{
  "eventId": "evt-price-1001",
  "eventType": "PRODUCT_PRICE_CHANGED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "originService": "catalog-service",
  "traceparent": "00-00000000000000000000000000000001-0000000000000001-01",
  "data": {
    "productId": "P-1001",
    "productVersion": 42
  }
}
~~~

Đây là **hợp đồng payload minh họa**, không phải schema mặc định của Spring Integration. Consumer cần kiểm tra eventType, schemaVersion, required fields, size, tenant/business authorization và các giới hạn bảo mật.

### 9.6. Kiểm soát charset

Nếu thỏa thuận UTF-8, producer và subscriber phải dùng cùng charset. Không phụ thuộc default charset của JVM hoặc dùng new String(bytes) không chỉ rõ charset. Đối với input nhị phân không tin cậy, có thể dùng **CharsetDecoder** strict để phát hiện UTF-8 invalid.

### 9.7. Versioning và rolling deployment

Pub/Sub không có replay, nhưng trong rolling deployment, **một lúc có thể tồn tại consumers v1 và v2**. Producer không được phát một schema mới phá compatibility mà không có chiến lược hỗ trợ versions, topic versioning hoặc migration.

| Producer | Consumer | Kỳ vọng |
| --- | --- | --- |
| v1 | v1 | Đọc được |
| v1 | v2 | v2 vẫn hiểu v1 trong thời gian hỗ trợ |
| v2 | v1 | Dữ liệu tương thích hoặc v1 reject/alert có kiểm soát |
| v2 | v2 | Schema mới hoạt động |
| Unknown eventType | Mọi consumer | Không route nhầm và không làm side effect |

## 10. Ghép outbound với Redis inbound channel adapter

Trong ứng dụng SearchService, subscriber nhận notification rồi invalidate cache:

~~~mermaid
flowchart LR
    A["CatalogRedisPublishFlow"] -->|"PUBLISH"| R["Redis Pub/Sub<br/>catalog.price.changed"]
    R --> I["Redis inbound channel adapter"]
    I --> T["Transformer<br/>JSON → DTO"]
    T --> V["Validate productVersion"]
    V --> C["Local cache invalidation"]
~~~

### 10.1. Ví dụ inbound cùng topic

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.redis.dsl.Redis;

@Configuration
public class SearchRedisSubscriptionFlow {

    @Bean
    public IntegrationFlow priceInvalidationSubscriber(
            RedisConnectionFactory factory,
            SearchCacheInvalidator invalidator) {

        return IntegrationFlow.from(
                Redis.inboundChannelAdapter(factory)
                    .topics("catalog.price.changed"))
            .handle((payload, headers) -> {
                invalidator.handleNotification(payload);
                return null;
            })
            .get();
    }
}
~~~

~~~java
public interface SearchCacheInvalidator {
    void handleNotification(Object rawPayload);
}
~~~

**Lưu ý:** Đây là mẫu wiring subscriber; handler phải **đổi rawPayload theo serializer/converter đã thống nhất**, parse JSON, validate schema/version, kiểm tra source authorization rồi mới invalidate. Không cho rằng payload luôn là String trong mọi phiên bản/cấu hình inbound.

### 10.2. Topic pattern và overlap

Subscriber có thể subscribe exact topic **catalog.price.changed** hoặc pattern như **catalog.***. Nếu cùng một application đăng ký subscriptions chồng nhau, một publish có thể dẫn tới nhiều callbacks tùy implementation/đăng ký; kiểm tra duplicate side effects và topic ownership.

### 10.3. Inbound RedisHeaders.MESSAGE_SOURCE

Redis inbound adapter có thể cung cấp **RedisHeaders.MESSAGE_SOURCE** để chỉ topic hoặc pattern mà nó nhận thông điệp từ đó, theo phiên bản. Header này hữu ích cho routing/observability tại subscriber, nhưng **không biến topic thành một token xác thực**.

### 10.4. Không dùng Pub/Sub để đồng bộ state không thể rebuild

Nếu cache eviction bị lỡ, TTL và nguồn sự thật cho phép sửa. Nếu notification mang một delta duy nhất mà mất sẽ làm database projection sai mãi mãi, nên dùng **Redis Streams, Kafka, AMQP hoặc nguồn sự kiện bền vững**.

## 11. Delivery semantics: những khoảng mất message

Đường publish gồm nhiều điểm failure:

~~~mermaid
sequenceDiagram
    participant B as Business service
    participant F as Spring Integration flow
    participant R as Redis
    participant S as Subscriber
    participant DB as Consumer business state
    B->>F: send(eventId)
    F->>R: PUBLISH
    R-->>S: Notification, only if connected
    S->>DB: Parse / validate / handle
    Note over F,DB: Redis Pub/Sub không có consumer ACK và replay
~~~

### 11.1. Ma trận lỗi

| Vị trí lỗi | Tình huống | Kết quả có thể xảy ra |
| --- | --- | --- |
| Trước khi Spring Message đến adapter | Filter discard, router sai, channel không có consumer | Không publish |
| Trong converter/serializer | Unsupported payload, byte encoding lỗi | Không gửi được hoặc gửi body sai contract |
| Redis connection unavailable | Redis timeout/ACL/mạng lỗi | PUBLISH thất bại; có thể có exception |
| Kết nối đứt ở ranh giới response | Redis có thể đã xử lý PUBLISH | **Unknown outcome**, retry có thể tạo duplicate |
| Subscriber offline | Deploy, crash, network partition | **Không có backlog để subscriber nhận lại** |
| Subscriber nhận bytes nhưng parse lỗi | Malformed JSON, unsupported schema | Redis không tự redeliver |
| Subscriber xử lý xong nhưng log/metric lỗi | Business đã hoàn tất, producer không biết | Có thể hiểu nhầm chưa xử lý |
| Producer publish hai lần cùng eventId | Retry/application logic | Consumer có thể xử lý cùng business event hai lần |

### 11.2. Không có ACK/NACK tương đương AMQP

Redis Pub/Sub không có:

- Consumer acknowledgment theo message ID.
- Pending Entries List cho từng subscriber.
- Offset để replay khi reconnect.
- Dead-letter exchange/queue native.
- Redelivery sau subscriber ném exception.

**Spring Integration errorChannel** không tạo ra các khả năng Redis protocol không có.

### 11.3. Redis publish result bằng 0

PUBLISH có thể trả số subscribers bằng 0 khi không có kết nối subscribe phù hợp. Điều này không tự là lỗi command Redis. Trong nhiều ứng dụng best-effort, không có subscribers lúc publish là hợp lệ; trong ứng dụng khác đó là tín hiệu vận hành cần cảnh báo.

**RedisPublishingMessageHandler là one-way handler** và không cung cấp một business result channel cho caller. Nếu cần đọc số subscribers, phải dùng API Redis command phù hợp ở nơi khác; nhưng không dùng nó như chứng cứ delivery.

### 11.4. Redis reconnect không sửa mất notification

Subscriber có thể reconnect và subscribe lại sau failover. Nó sẽ nhận **những notification mới** khi đang online, không nhận các messages được publish trong lúc không có kết nối.

Một chiến lược tốt cho cache invalidation là **on-start refresh / TTL / periodic reconciliation**, không chỉ retry kết nối.

### 11.5. At-most-once không ngăn publisher retry trùng

Nếu producer PUBLISH rồi connection mất trước khi nhận reply, application không thể biết chắc Redis đã gửi notification hay chưa. Retry cùng eventId có thể giúp tăng xác suất subscriber nhận, nhưng **có thể gây duplicate**. Consumer nên xử lý idempotent, chẳng hạn xóa cùng cache key nhiều lần là an toàn.

## 12. Database commit và Redis PUBLISH: ranh giới giao dịch

Giả sử thay đổi giá phải commit trước khi phát notification. Có ba cách phổ biến:

### 12.1. PUBLISH trước khi commit: sai lệch nếu rollback

~~~text
BEGIN DB TRANSACTION
  UPDATE product price = 120000
  PUBLISH productId=P-1001
ROLLBACK DB
~~~

SearchService có thể đã invalidate hoặc refetch dữ liệu trong lúc transaction chưa commit hoặc cuối cùng rollback. Với cache invalidation, xóa cache dư thường không nghiêm trọng, nhưng có thể gây thundering herd hoặc race repopulation.

### 12.2. Publish afterCommit

~~~text
BEGIN DB TRANSACTION
  UPDATE product price = 120000
COMMIT DB
  -> afterCommit callback
     -> Redis outbound adapter PUBLISH
~~~

After-commit tránh gửi notification cho thay đổi chắc chắn rollback, nhưng vẫn có một **khoảng crash**:

~~~text
DB commit thành công
  -> JVM crash trước Redis PUBLISH
  -> database đã đổi, notification chưa bao giờ phát
~~~

Vì vậy **afterCommit không đồng nghĩa atomic publish**. Nó là một sự phối hợp thời điểm, không phải distributed transaction.

### 12.3. Transactional outbox

Khi cần phát bền vững từ database:

~~~mermaid
flowchart LR
    APP["CatalogService"] --> DB[("DB transaction:<br/>product + outbox row")]
    DB --> W["Outbox worker<br/>retry until dispatched"]
    W --> PUB["Redis outbound adapter<br/>PUBLISH"]
    PUB --> R["Redis Pub/Sub"]
    R --> S["Search subscriber"]
~~~

Outbox giúp khôi phục **ý định publish** khi producer chết sau DB commit. Tuy nhiên, **outbox + Pub/Sub vẫn không bảo đảm subscriber offline nhận được message**. Khi business event thật sự cần replay ở **phía consumer**, phải thay/bổ sung Pub/Sub bằng Redis Streams hoặc durable broker/inbox.

### 12.4. Nguồn sự thật và reconciliation

Với case cache:

1. Catalog DB là nguồn giá chính xác.
2. Redis PUBLISH báo **“product P-1001 changed”**, không buộc consumer tin vào giá cũ/mới trong payload.
3. SearchService invalidate cache idempotently.
4. TTL/version check/periodic refresh giúp sửa khi bỏ lỡ notification.
5. Thống kê staleness age để phát hiện mất đồng bộ kéo dài.

Đây là **eventual consistency có điều kiện phục hồi**, không phải cam kết message không bao giờ mất.

### 12.5. Thứ tự sự kiện và cache

Giả sử producer cập nhật version 41 rồi 42. Nếu consumers nhận/xử lý events không đúng thứ tự hoặc refetch trong lúc DB thay đổi, cache có thể bị cập nhật sai nếu handler tin vào payload state. Tốt hơn:

- Chỉ invalidate theo productId.
- Hoặc apply update khi **productVersion lớn hơn** phiên bản đã xử lý.
- Khi nghi ngờ gap, **refetch nguồn sự thật**.

## 13. Topic topology và fan-out trong hệ nhiều services

### 13.1. Một channel → nhiều subscribers

~~~text
Redis PUBLISH catalog.price.changed
    +-- SearchService replica A -> local cache invalidate
    +-- SearchService replica B -> local cache invalidate
    +-- SearchService replica C -> local cache invalidate
~~~

Với local cache, mọi replica nhận thông báo là hợp lý. Với một hành động chỉ nên chạy đúng một lần trên cluster, Redis Pub/Sub broadcast không phù hợp nếu không có phối hợp ownership.

### 13.2. Pattern subscription mở rộng phạm vi nhận

~~~text
SUBSCRIBE catalog.price.changed
PSUBSCRIBE catalog.*
~~~

Đăng ký pattern rộng có thể nhận nhiều event types hơn mục đích handler; cần parse eventType + allowlist, tránh routing nhầm. Nếu có cả exact và pattern overlap, một logical event có thể tạo nhiều callbacks tùy client subscriptions.

### 13.3. Topic Redis không giống Kafka topic

| Redis Pub/Sub channel | Kafka topic |
| --- | --- |
| Không có partition offset/replay | Có durable log/offset theo retention |
| Không lưu subscriber backlog | Consumer group có thể đọc lịch sử đã giữ |
| PUBLISH gửi cho online subscribers | Produce lưu vào broker theo ack/durability |
| Không native consumer ACK | Commit offset/consumer processing contract riêng |

Chỉ đặt tên một Redis channel là **orders.events** không biến nó thành một event log.

### 13.4. Domain event hay transport hint?

**Transport hint:** Product X changed → hãy refetch/invalidate. Mất một hint có thể được TTL/reconciliation sửa.

**Domain fact:** Payment Y settled → phải cập nhật ledger. Nếu mất một fact không thể rebuild, Pub/Sub đơn lẻ là lựa chọn rủi ro.

Chọn giao thức theo hậu quả khi mất message, không chỉ theo tốc độ PUBLISH.

### 13.5. Kết hợp Pub/Sub và Streams có chủ đích

Một hệ thống có thể dùng:

~~~text
Durable event log/Redis Stream -> projection worker
                              -> Redis PUBLISH cache hint
~~~

Nguồn event bền vững bảo đảm có thể xử lý/replay domain facts; Pub/Sub là lớp notification nhanh để invalidate cache. **Không đảo ngược vai trò** bằng cách dùng PUBLISH là nguồn duy nhất rồi hy vọng một bridge downstream ghi đủ mọi event.

## 14. Lỗi Redis outbound và xử lý trong Spring Integration

Lỗi có thể xuất hiện trước, trong hoặc sau lệnh PUBLISH:

~~~mermaid
flowchart TD
    M["Spring Message"] --> V["Validate payload"]
    V --> T["Select topic"]
    T --> C["MessageConverter"]
    C --> S["RedisSerializer"]
    S --> R["Redis PUBLISH"]
    V -. "Schema error" .-> ERR["Exception / error flow"]
    T -. "Invalid/untrusted topic" .-> ERR
    C -. "Type conversion" .-> ERR
    S -. "Serialization" .-> ERR
    R -. "ACL/network/timeout" .-> ERR
    R --> SUB["Online subscribers"]
    SUB -. "Handler failure" .-> LOCAL["Subscriber-side error"]
~~~

### 14.1. Lỗi conversion/serialization

Nếu payload là DTO Java mà serializer chỉ chấp nhận String, lệnh PUBLISH có thể không được thực hiện. Giải pháp:

- Validate DTO trước khi gọi outbound.
- Dùng **DTO → JSON String transformer** rõ ràng.
- Dùng StringRedisSerializer hoặc serializer khớp contract.
- Log **eventId và error category**, không log toàn bộ payload nhạy cảm.

### 14.2. Lỗi topic expression

TopicExpression có thể trả null, một kiểu không phải String hoặc một tên topic ngoài allowlist. Không coi lỗi publish là lỗi Redis network khi nguyên nhân là **routing input sai**. Dùng enum/router và kiểm tra topic trước outbound handler.

### 14.3. Redis connection/ACL

Lỗi thường gặp:

| Lỗi | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| RedisConnectionFailureException | Không kết nối được Redis | Kiểm tra host/network, timeouts, failover |
| RedisSystemException/command error | Redis command lỗi | Phân loại theo cause, command, client version |
| NOPERM/ACL | Redis user không được PUBLISH topic | Kiểm tra Redis ACL channel permission |
| Timeout | Không nhận kết quả trong hạn | Có thể **unknown publish outcome**, không retry vô hạn |
| Serializer exception | Không chuyển được payload | Fix schema/serializer, không retry nóng |
| Untrusted topic | Topic ngoài namespace hợp lệ | Reject và cảnh báo security |

### 14.4. DirectChannel exception propagation

Với **DirectChannel** và handler đồng bộ, exception của outbound adapter có thể propagate về caller đang gửi message. Nếu caller là một HTTP inbound gateway hoặc service được gọi bởi request thread, điều đó có thể tạo lỗi HTTP/transaction rollback tùy cách bạn tổ chức.

**Rủi ro:** Database đã commit nhưng PUBLISH timeout → API trả lỗi → client retry request → business write/notification có thể trùng. Thiết kế idempotency/outbox/response semantics theo business contract, không mặc định publisher failure nghĩa DB transaction chưa xảy ra.

### 14.5. ErrorChannel khác nơi lưu bền

Spring Integration hỗ trợ **ErrorMessage/errorChannel** theo cách endpoint, executor và flow được cấu hình. Nhưng:

- ErrorChannel không lưu Pub/Sub message cho subscriber offline.
- Error handler chỉ log không tương đương durable retry.
- Redis không phát lại notification khi downstream consumer ném exception.
- Lỗi ở phía subscriber cần **subscriber-side monitoring/error flow** riêng.
- Lỗi trong thread async có thể xuất hiện ở error flow thay vì propagate tới thread caller.

Nếu cần retry durable, ghi event intent vào DB/outbox/stream trước khi publish và quản lý attempts/status.

### 14.6. Retry có giới hạn, không hot loop

Với lỗi Redis connection transient, có thể áp **RetryTemplate/RequestHandlerRetryAdvice** hoặc logic retry ở publisher worker nếu phù hợp. Nhưng:

- Retry kết nối trong cùng JVM mất tác dụng nếu process crash.
- Timeout có outcome không rõ → có thể PUBLISH trùng.
- Dữ liệu sai cố định không nên retry vô hạn.
- PUBLISH thành công lần 2 vẫn không bảo đảm subscriber offline đã nhận lần 1 hay 2.

Retry policy phải rõ **max attempts, backoff, classifier, alerting và fallback**.

### 14.7. Subscriber business error không trở về publisher

Nếu SearchService nhận message nhưng JSON parser/handler lỗi, Redis không có một request–reply path cho publisher biết. Một monitoring service tại Catalog không được tự tuyên bố SearchService đã update cache chỉ vì Redis outbound handler không ném exception.

## 15. Lifecycle, Redis failover và trạng thái publisher

### 15.1. Start và stop

Redis outbound adapter là một **message handler endpoint**, không có vòng Redis subscription của riêng nó. Khi application start, Spring Integration đăng ký consumer cho input channel. RedisConnectionFactory quản lý kết nối/client theo Spring context lifecycle.

Trong lúc app đang shutdown:

- Ngừng producer/source phát event mới.
- Cho những outbound sends đang xử lý hoàn tất hoặc đưa intent vào durable outbox.
- Không tự close RedisConnectionFactory dùng chung trước khi các handlers kết thúc.
- Nếu business event cần không mất, đánh dấu trạng thái khi publish/handoff thực sự hoàn tất theo contract.

**Graceful shutdown không giúp Pub/Sub giữ message cho SearchService offline.**

### 15.2. Redis reconnect/failover

Publisher có thể reconnect sau Redis restart hoặc Sentinel failover. Nhưng:

- Lệnh PUBLISH khi Redis unavailable có thể lỗi.
- Lệnh gửi gần thời điểm mất kết nối có kết quả UNKNOWN.
- Redis Pub/Sub không tự replay các publishes tới subscriber bị disconnect.
- Failover thành công của Redis không bảo đảm business cache consistency đã được khôi phục.

### 15.3. Redis Cluster và sharded Pub/Sub

Phải phân biệt **classic PUBLISH/SUBSCRIBE** với **sharded SPUBLISH/SSUBSCRIBE** trên Redis Cluster (khi hạ tầng hỗ trợ). Không tự giả định adapter vốn sử dụng Redis PUBLISH sẽ chuyển sang SPUBLISH chỉ vì Redis triển khai ở Cluster.

Các topology/client versions có thể ảnh hưởng routing và subscriber counts. Hãy kiểm thử **publisher từ node/connection thực tế, subscriber pattern thực tế, failover và nhận message** trên cùng hạ tầng.

### 15.4. Không dùng Redis DB index làm topic isolation

Pub/Sub channel namespace không được tách giống key database index của Redis theo cách một ứng dụng có thể tưởng tượng. Khi cùng Redis server phục vụ nhiều môi trường/tenants, dùng:

- Key/channel prefix nhất quán.
- Redis ACL channel patterns phù hợp.
- Network/TLS/credential separation.
- Redis instance/deployment isolation nếu cần mức bảo vệ mạnh.

### 15.5. Khác với Redis Streams retention

PUBLISH không tạo record được lưu trong stream chỉ vì Redis bật AOF/RDB. Persistence của Redis keys/Streams không bổ sung một **subscriber backlog** cho Pub/Sub.

## 16. Bảo mật và trust boundary

Redis Pub/Sub outbound gửi dữ liệu cho **mọi subscriptions phù hợp** trong phạm vi server/cluster và ACL. Vì vậy:

1. Chỉ cho publisher quyền **PUBLISH** những channels cần thiết.
2. Chỉ cho subscribers quyền **SUBSCRIBE/PSUBSCRIBE** những channels họ được phép đọc.
3. Không dùng topic do external client nhập trực tiếp trong SpEL expression.
4. Không nhúng PII/credentials/payment details vào payload nếu chỉ cần cache hint.
5. Validate eventType/schemaVersion/tenant/business ownership trước publish và ở consumer.
6. Bảo vệ Redis network, TLS, credentials, rate limits và message size.

### 16.1. Payload giả mạo tenant

~~~json
{
  "eventId": "evt-1001",
  "eventType": "PRODUCT_PRICE_CHANGED",
  "tenantRef": "other-tenant",
  "data": {
    "productId": "P-999"
  }
}
~~~

Việc record đi qua topic **prod.catalog.price.changed** không chứng minh publisher có quyền thay dữ liệu tenant khác. Consumer phải dựa vào nguồn xác thực/ủy quyền phù hợp, không tin raw payload.

### 16.2. Topic expression injection

Nếu application dùng:

~~~text
topicExpression = headers['redisTopic']
~~~

thì header đó phải được set từ **allowlisted enum/config**, không lấy raw topic name từ form/HTTP header không xác thực. Tương tự, không parse một raw SpEL expression do client cung cấp rồi chạy với application evaluation context.

### 16.3. Serializer an toàn

Tránh native Java serialization cho payload không tin cậy và đặc biệt cho giao tiếp giữa services khác ngôn ngữ. JSON/Avro/Protobuf với schema validation và strict type restrictions thường dễ quản lý hơn. Đừng bật Jackson default typing cho mọi class từ raw Redis input.

### 16.4. Subscriber pattern quá rộng

Pattern rộng như **PSUBSCRIBE với wildcard (*)** có thể nhận dữ liệu thuộc nhiều domains/environments không liên quan. Giới hạn topic patterns, event types và ACL; không để handler with privileged side effect chạy dựa trên một channel name khớp wildcard nhưng thiếu validation.

## 17. Concurrency, backpressure và giới hạn throughput

### 17.1. DirectChannel

~~~text
Caller thread
  -> DirectChannel.send()
  -> RedisPublishingMessageHandler.handleMessage()
  -> Redis PUBLISH command
  -> return / exception
~~~

DirectChannel không tạo queue nội bộ và thường phù hợp với tác vụ publish nhỏ. Nhưng Redis network latency/timeout có thể **giữ thread của caller**, chẳng hạn một HTTP request thread hoặc DB event processor.

### 17.2. ExecutorChannel

~~~text
Caller -> ExecutorChannel -> executor queue -> Redis publish worker
            send may return before PUBLISH finishes
~~~

ExecutorChannel giảm độ trễ của caller nếu executor còn capacity, nhưng:

- Task chưa chạy có thể chỉ nằm trong memory queue.
- Process crash có thể làm mất những notification chưa publish.
- Exception publish xảy ra ở thread khác, cần errorChannel/metrics.
- Queue đầy có thể reject task; phải có bounded capacity/policy.
- Caller thấy send accepted **không tương đương Redis đã xử lý lệnh**.

Nếu cần durable publish, dùng outbox/DB task source hoặc message store được thiết kế phù hợp; **ExecutorChannel không tự là durable broker**.

### 17.3. QueueChannel

QueueChannel cho phép đệm Spring Messages rồi poller nội bộ tiêu thụ:

~~~text
Application -> QueueChannel -> internal poller -> Redis outbound adapter
~~~

Poller này **đọc QueueChannel nội bộ**, không poll Redis Pub/Sub. QueueChannel mặc định ở memory, không giữ tasks qua restart. Có thể dùng persistent MessageStore trong thiết kế riêng, nhưng khi đó vẫn phải xác minh các ranh giới send/store/commit và Pub/Sub không replay ở phía subscriber.

### 17.4. PublishSubscribeChannel nội bộ khác Redis Pub/Sub

**PublishSubscribeChannel** của Spring Integration phát cùng Spring Message tới nhiều handlers trong ứng dụng. **Redis Pub/Sub** phát notification tới Redis subscribers trên mạng. Nếu bạn dùng cả hai:

~~~text
Local PublishSubscribeChannel
  -> Redis outbound adapter 1 (topic A)
  -> Redis outbound adapter 2 (topic B)
~~~

một event có thể tạo **hai Redis PUBLISH**, đây là fan-out do cấu hình. Nếu cả hai topics match cùng subscriber pattern, handler có thể nhận duplicate logic.

### 17.5. Không dùng publish rate làm success rate

Ví dụ CatalogService publish 10.000 events/s; Redis command latency thấp, nhưng SearchService chỉ xử lý 2.000 events/s. Redis Pub/Sub không có per-subscriber backpressure/ACK như queue bền vững. Under load, subscriber hoặc client buffers có thể gặp lỗi/ngắt kết nối, làm mất notifications.

Giải pháp phù hợp có thể là:

- **Coalesce** nhiều updates của cùng productId thành một invalidation hint.
- Rate limit/batch ở producer theo business SLA.
- Subscriber xử lý nhanh, tránh blocking long tasks trong callback.
- TTL/reconciliation để sửa dữ liệu stale.
- Chuyển sang durable queue/stream khi không chấp nhận mất event.

### 17.6. Topic granularity và cardinality

Không tạo một Redis Pub/Sub channel cho **mỗi productId/userId** nếu điều đó dẫn tới hàng triệu dynamic channels/patterns khó quản lý và ACL phức tạp. Thường chọn một channel theo **event type/domain** và đặt productId trong payload:

~~~text
Topic: catalog.price.changed
Payload: {"productId":"P-1001", ...}
~~~

Nếu multi-tenant cần isolation chặt, có thể chia namespace/topic/deployment theo tenant group, nhưng phải có số liệu capacity và policy cụ thể.

## 18. Observability: theo dõi publish và subscriber outcomes

Redis outbound channel adapter có thể được instrument với Micrometer/Observation tùy Spring Integration version, cùng custom business metrics.

| Metric/tín hiệu | Ý nghĩa | Không chứng minh |
| --- | --- | --- |
| Spring outbound handler invocation | Số messages đã tới endpoint | Redis đã nhận |
| Redis PUBLISH command success | Redis đã xử lý command theo client outcome | Subscriber xử lý nghiệp vụ thành công |
| Redis PUBLISH exception | Redis/network/conversion lỗi | Mọi notification đều chắc chắn chưa gửi |
| Redis PUBLISH subscriber count | Số recipients theo ngữ nghĩa Redis | Các recipients đã commit |
| Publisher retry count | Số lần thử lại | Không có duplicate |
| Subscriber receive count | Số callbacks ở từng app | Mọi events đã tới |
| Subscriber handler success/error | Kết quả xử lý phía nhận | Events đã mất trước callback |
| Redis reconnect/disconnect | Mức độ gián đoạn | Số messages bị mất chính xác |
| Cache stale-age/reconciliation gap | Tính đúng dữ liệu ứng dụng | Redis transport delivery trực tiếp |

### 18.1. Metric names gợi ý

~~~text
redis_pubsub_outbound_attempted_total{topic="catalog.price.changed"}
redis_pubsub_outbound_succeeded_total{topic="catalog.price.changed"}
redis_pubsub_outbound_failed_total{reason="CONNECTION_TIMEOUT"}
redis_pubsub_outbound_retry_total
redis_pubsub_outbound_duration_seconds
redis_pubsub_subscriber_received_total{topic="catalog.price.changed"}
redis_pubsub_subscriber_validation_failed_total{eventType="PRODUCT_PRICE_CHANGED"}
catalog_cache_reconciliation_stale_seconds
~~~

Đây là **tên metric do ứng dụng có thể thiết kế**, không phải các metric framework cam kết tự xuất. Dùng labels cardinality thấp; không đặt eventId, productId, tenantRef hoặc raw dynamic topic tự do thành labels không giới hạn.

### 18.2. Structured logging

~~~text
component=redisPriceOutbound
topic=catalog.price.changed
eventId=evt-price-1001
eventType=PRODUCT_PRICE_CHANGED
schemaVersion=1
publishStatus=SUCCESS
payloadBytes=162
durationMs=4
~~~

Nếu Redis command trả thành công, đặt status **PUBLISHED** hoặc **COMMAND_SUCCESS**, không ghi **DELIVERED_TO_ALL_CONSUMERS** hay **BUSINESS_DONE**.

### 18.3. Correlation giữa producer và subscriber

Giữ eventId/traceparent trong JSON envelope để SearchService log cùng eventId khi nhận. Redis Pub/Sub không có một trace context header chuẩn tự vận chuyển như HTTP; muốn distributed tracing cần propagation contract, instrumentation và chính sách an toàn.

### 18.4. Monitor subscriber readiness

Ở phía SearchService:

- Redis listener container/subscription active chưa?
- Reconnect/resubscribe count thế nào?
- Received/handled/failed counts?
- Last-received timestamp có phù hợp publisher activity không?
- Cache version/staleness age có nằm trong SLA?

Một publisher monitor đủ không thể biết toàn bộ subscriber outcomes nếu không có **subscriber-side metrics hoặc reconciliation**.

### 18.5. Redis PUBSUB NUMSUB

~~~bash
redis-cli PUBSUB NUMSUB catalog.price.changed
~~~

Đây là một snapshot số subscriptions của channel theo ngữ nghĩa Redis. Nó **không phải health check cho một business consumer cụ thể**, không tính đủ mọi trường hợp pattern subscriptions/cluster theo cách người mới nghĩ, và không thể thay business success metrics.

## 19. Kiểm thử với Redis thật: từ contract đến mất message

Unit test converter hoặc service emitter không chứng minh Redis adapter đã publish đúng channel/wire bytes. Cần một integration test với Redis test instance hoặc Testcontainers, cùng subscriber thực sự subscribe.

### 19.1. Ma trận kiểm thử

| Test | Thiết lập | Điều cần xác minh |
| --- | --- | --- |
| Happy path | Subscriber active, gửi JSON hợp lệ | Subscriber nhận đúng topic và payload |
| Topic constant | Cấu hình topic cố định | Không publish sang topic khác |
| Topic expression | Header redisTopic từ enum | Định tuyến tới topic đã chọn |
| Unknown topic | Header ngoài allowlist | Reject trước PUBLISH |
| No subscriber | PUBLISH khi không có subscriber | Publish command vẫn có thể thành công, không có consumer replay |
| Subscriber starts late | Publish rồi mới subscribe | Không nhận thông điệp cũ |
| Subscriber reconnect | Mất Redis connection, publish trong outage | Chỉ messages mới sau resubscribe được nhận |
| Two subscribers | Hai Redis clients subscribe một topic | Cả hai có thể nhận cùng PUBLISH |
| Overlapping patterns | Exact topic + pattern match | Phát hiện duplicate callbacks nếu có |
| String serializer | Producer JSON String | Bytes và JSON đúng contract |
| JSON double-encoding | Producer JSON serializer cho String | Test phát hiện quotes/escapes không mong đợi |
| POJO unsupported | Gửi DTO không có transformer | Lỗi có ý nghĩa; không âm thầm toString |
| Invalid UTF-8 | Raw bytes không hợp lệ | Consumer strict decoder/validation reject |
| Missing schemaVersion | Event không có version | Consumer reject/alert |
| Unsupported eventType | Event type lạ | Không route tới handler có quyền cao |
| Redis offline | Stop Redis test | Sender ném lỗi/metrics; retry policy |
| Redis ACL denied | User thiếu quyền PUBLISH | Command fails/alert |
| Network outcome UNKNOWN | Drop connection gần command | Logic dedup khi retry, không kết luận chắc chưa gửi |
| DirectChannel failure | Redis handler ném exception | Caller/error boundary đúng |
| ExecutorChannel failure | Publish lỗi async | Error flow nhận, metrics đúng |
| QueueChannel crash | Task còn trong memory | Không coi memory buffer là durable |
| Transaction rollback | UPDATE rollback | Không gửi after-commit event sai |
| Crash after DB commit | Trước PUBLISH | Outbox/reconciliation nhận biết gap |
| Idempotency | PUBLISH hai lần cùng eventId | Consumer xử lý idempotent |
| Local cache replicas | Hai/ba SearchService instances | Mỗi replica invalidate khi online |
| Topic namespace | dev/prod topics | Không cross-publish |
| Redis Cluster/failover | Hạ tầng test tương đương production | PUBLISH/subscribe đúng topology |
| Payload size burst | Rate tăng đột ngột | Không OOM hoặc unbounded executor queue |
| Graceful shutdown | Dừng publisher khi flow đang chạy | Durable intent hoặc xử lý được in-flight theo SLA |

### 19.2. Test subscriber phải active trước khi publish

Với Pub/Sub, **thời điểm subscribe rất quan trọng**. Đừng start ApplicationContext rồi PUBLISH lập tức mà không đợi listener thật sự subscribe; một test có thể timeout dù logic Java đúng, vì notification được gửi trước thời điểm SUBSCRIBE hoàn tất.

Nên dùng health/readiness hoặc test synchronization phù hợp để xác minh subscriber đã đăng ký với Redis; **Thread.sleep(1000)** không là bảo đảm tuyệt đối.

### 19.3. Capturing handler cho integration test

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class RedisPubSubCapture {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<String> received =
        new AtomicReference<>();

    public void accept(String json) {
        received.set(json);
        latch.countDown();
    }

    public String awaitMessage() throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Redis Pub/Sub message not received");
        }
        return received.get();
    }
}
~~~

**Đây là test helper**, không phải Spring Boot integration test hoàn chỉnh. Test cần Redis test server, outbound flow, inbound adapter với serializer cùng contract, capture wiring, subscriber readiness và assertions. Không chạy destructive failover/ACL experiments trên Redis production.

### 19.4. Test wire-format bằng Redis CLI

Một cách đơn giản:

1. Start redis-cli SUBSCRIBE test.catalog.price.changed.
2. Gửi Spring Message JSON String qua Redis outbound adapter cấu hình **test topic**.
3. Quan sát bytes/text được subscriber nhận.
4. Parse thành JSON và xác minh eventId/schemaVersion/productVersion.
5. So sánh với JSON serializer khác để phát hiện double-encoding.

### 19.5. Test no-subscriber khác Redis List

Đừng áp bài test của Redis List queue vào Pub/Sub. Với List, item LPUSH khi worker offline có thể nằm lại trong List. Với Pub/Sub, PUBLISH khi subscriber offline **không có backlog** cho subscriber mới.

### 19.6. Cần kiểm thử hai phía transaction

Nếu dùng afterCommit:

- DB rollback → không PUBLISH.
- DB commit → afterCommit PUBLISH nếu process sống.
- Crash sau DB commit trước publish → outbox/reconciliation có thể phục hồi.
- Redis publish success nhưng subscriber offline → vẫn không replay.
- Pub/Sub duplicate do publisher retry → consumer xử lý idempotent.

## 20. Các tình huống thiết kế thực tế

### 20.1. Case A – Cache invalidation cho nhiều replicas

**Yêu cầu:** Tất cả SearchService replicas có local cache cần xóa key sản phẩm sau cập nhật.

~~~mermaid
flowchart LR
    C["Catalog DB commit"] --> O["Redis outbound adapter"]
    O --> R["catalog.price.changed"]
    R --> A["Search A cache"]
    R --> B["Search B cache"]
    R --> D["Search C cache"]
    C --> RECON["Periodic source reconciliation"]
    RECON --> A
    RECON --> B
    RECON --> D
~~~

Đây là **use case phù hợp** cho Redis Pub/Sub outbound nếu:

- Cache eviction idempotent.
- Cache có TTL/version check.
- Dữ liệu đúng nằm ở Catalog DB/service.
- Phía subscriber có monitoring reconnect và staleness.
- Mất một notification gây stale **có giới hạn và có cách sửa**.

### 20.2. Case B – Cập nhật payment ledger bắt buộc

**Yêu cầu:** Mỗi PaymentSettled phải cập nhật ledger, không được bỏ qua khi consumer offline.

**Không dùng Pub/Sub PUBLISH làm nguồn duy nhất**. Cân nhắc:

~~~mermaid
flowchart LR
    PAY["Payment DB + outbox"] --> W["Outbox worker"]
    W --> D["Durable broker / Redis Stream"]
    D --> IN["Consumer group + durable inbox"]
    IN --> LEDGER["Ledger DB"]
    IN -. "ACK after commit" .-> D
~~~

Sự kiện bắt buộc không được mất cần **durable producer handoff, consumer ACK/recovery, idempotency và reconciliation**. Pub/Sub có thể chỉ là tín hiệu phụ báo UI refresh.

### 20.3. Case C – SFTP import → Redis PUBLISH

**Yêu cầu:** Mỗi lần import CSV từ SFTP hoàn thành, thông báo dashboard refresh.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound adapter + poller"] --> CSV["Parse/validate CSV"]
    CSV --> DB[("Import DB commit")]
    DB --> OUT["Redis outbound adapter"]
    OUT --> R["imports.completed"]
    R --> UI["Dashboard subscribers"]
~~~

Phân biệt:

1. **SFTP poller** tìm file mới.
2. **CSV parser** xác minh dữ liệu.
3. **DB commit** là mốc import hoàn tất.
4. **Redis PUBLISH** chỉ báo dashboard biết refresh.

Không đánh dấu import DONE chỉ nhờ Redis PUBLISH; cũng không cần một Redis consumer ACK nếu notification chỉ giúp refresh view có TTL.

### 20.4. Case D – HTTP inbound → Redis Pub/Sub notification

~~~text
HTTP POST /catalog/products/P-1001
  -> validate request + authorization
  -> update Catalog DB
  -> afterCommit/event outbox
  -> Redis outbound adapter PUBLISH
~~~

**Vấn đề:** Nếu PUBLISH timeout sau DB commit, HTTP API có thể trả lỗi tùy cách tổ chức callback; client retry có thể tạo thay đổi/notifications trùng. Chọn response semantics rõ: HTTP thành công khi DB commit hay khi notification được publish, và dùng idempotency nếu retry.

### 20.5. Case E – Một message phát nhiều topics

Một thay đổi inventory có thể cần:

~~~text
inventory.changed -> Redis PUBLISH inventory.changed
                  -> Redis PUBLISH dashboard.refresh
~~~

Dùng router hoặc PublishSubscribeChannel nội bộ để dispatch tới **hai outbound handlers** có topic cố định. Đừng dùng một topic-expression chứa danh sách topics rồi kỳ vọng Redis tự fan-out theo dấu phẩy; **PUBLISH nhận một channel name** cho mỗi lệnh.

Nếu subscriber đăng ký wildcard match cả hai topics, nó có thể thấy hai notifications liên quan cùng eventId. Quy tắc deduplicate/ownership phải rõ.

### 20.6. Case F – Redis outbound → bridge sang Kafka

Nếu một bridge subscribe Redis Pub/Sub rồi produce tới Kafka:

~~~text
Catalog -> Redis PUBLISH -> Bridge subscriber -> Kafka producer
~~~

Khi bridge offline, những Redis Pub/Sub notifications được publish trong khoảng đó có thể mất **trước khi Kafka nhìn thấy**. Kafka producer ACK chỉ xác nhận records đã đến được Kafka; nó **không bù được khoảng trống source Redis Pub/Sub**.

Nếu business yêu cầu không bỏ sót, hãy đặt durable event log/outbox **ở trước bridge**, không chỉ chỉnh Kafka settings.

### 20.7. Case G – Redis Pub/Sub giữa nhiều tenants

Topic như **tenant123.catalog.price.changed** có thể thuận tiện để phân vùng traffic, nhưng topic name **không là authorization token**. Cần:

- Tenant identity và quyền từ nguồn đáng tin.
- Producer/subscriber ACL theo namespace nếu hạ tầng cho phép.
- Retention/log policy với dữ liệu nhạy cảm.
- Rate limits để một tenant không làm Redis Pub/Sub quá tải.
- Không cho external caller tùy ý đặt header redisTopic.

## 21. Troubleshooting: PUBLISH thành công nhưng subscriber không nhận

Khi business team báo SearchService không invalidate cache, hãy kiểm tra từng biên thay vì tăng retry ngay:

~~~mermaid
flowchart TD
    SRC["Spring Message"] --> CH{"Outbound channel có handler?"}
    CH -->|"Không"| E1["Flow wiring / filter / route"]
    CH -->|"Có"| TOP{"Topic đúng?"}
    TOP -->|"Không"| E2["Topic expression / allowlist"]
    TOP -->|"Có"| SE{"Wire payload đúng?"}
    SE -->|"Không"| E3["Converter / serializer"]
    SE -->|"Có"| PUB{"Redis PUBLISH thành công?"}
    PUB -->|"Không"| E4["ACL / network / timeout"]
    PUB -->|"Có"| SUB{"Subscriber active?"}
    SUB -->|"Không"| E5["Pub/Sub không có backlog"]
    SUB -->|"Có"| HAND{"Consumer xử lý?"}
    HAND -->|"Không"| E6["JSON/schema/cache handler"]
    HAND -->|"Có"| DONE["Kiểm tra TTL/version/DB state"]
~~~

### 21.1. Spring Message không tới handler

Kiểm tra:

- Input channel đúng tên **priceChangedOutbound**?
- Có khai báo cả DSL và @ServiceActivator dẫn tới nhiều consumers hoặc cấu hình cạnh tranh?
- Upstream filter/router có discard?
- DirectChannel có subscriber hợp lệ khi send?
- Có error flow đang xử lý exception nhưng không alert?

### 21.2. Redis connection tốt nhưng sai topic

Producer có thể PUBLISH **prod.catalog.price.changed** trong khi subscriber SUBSCRIBE **catalog.price.changed**. Redis không cảnh báo rằng một channel name không có subscribers; PUBLISH vẫn hợp lệ.

Tạm test với một topic cụ thể và observer Redis CLI ở môi trường được phép, rồi bật topicExpression trở lại sau khi xác minh header.

### 21.3. Topic expression cho ra String sai

Một header có thể không tồn tại, bị đổi kiểu hoặc chứa prefix khác. **Expression evaluation failure** khác Redis connection failure; log topic alias/route decision đã validate và từ chối input không đúng.

### 21.4. Payload bị mã hóa hai lần

Triệu chứng: Subscriber tưởng sẽ nhận JSON object:

~~~json
{"eventId":"evt-1001","eventType":"PRODUCT_PRICE_CHANGED"}
~~~

nhưng bytes thực lại biểu diễn một JSON String literal có escaped quotes. Consumer Jackson đọc thành String chứ không phải object, hoặc fail validation. Chốt **StringRedisSerializer khi payload đã là JSON String**, hoặc thống nhất sử dụng DTO/JSON converter hai đầu.

### 21.5. Subscriber offline trong khoảng publish

Nếu Redis CLI SUBSCRIBE chạy **sau khi PUBLISH**, nó sẽ không nhận message trước đó. Đó là **đúng ngữ nghĩa Pub/Sub**, không phải Kafka lag, Redis List mất item hoặc bug của Spring MessageChannel.

### 21.6. PUBSUB NUMSUB khác kỳ vọng

Có thể đang quan sát sai Redis node/topology, subscriber đăng ký pattern chứ không exact topic, hoặc application chưa hoàn tất subscribe. NUMSUB không xác nhận một business service cụ thể đã xử lý. Kiểm tra subscriber-side logs/metrics và business state.

### 21.7. Subscriber nhận nhưng cache vẫn stale

Kiểm tra:

- Consumer đã parse đúng eventType/schemaVersion?
- productId/tenantRef có đúng authorization không?
- Cache key/prefix có nhất quán giữa các replicas không?
- Có TTL/version/refresh policy?
- Handler đã invalidate nhưng một task khác repopulate cache từ bản cũ?
- Có lần cập nhật productVersion mới hơn?
- Có replica offline và chưa reconcile?

Khi **subscriber callback đã chạy**, đừng vội quy lỗi cho Redis PUBLISH. Có thể lỗi là **cache/business semantics**.

### 21.8. Redis connection timeout gần publish

Trường hợp result UNKNOWN: Redis có thể đã nhận lệnh nhưng client không nhận reply. Nếu retry, có thể có duplicate. Cần eventId ổn định và consumer idempotency; không lặng lẽ tạo eventId mới mỗi lần thử lại cùng một thay đổi.

### 21.9. Một publish tạo nhiều callbacks

Nguyên nhân có thể là:

- Nhiều subscribers/replicas thật sự cần nhận.
- Exact topic và pattern subscriptions chồng nhau.
- Hai Redis outbound handlers cùng publish.
- Producer retry.
- Subscriber handler được đăng ký nhiều lần.

Phân biệt **fan-out chủ đích** với **duplicate business side effect** trước khi sửa topology.

## 22. Những hiểu lầm phổ biến

**“Redis outbound channel adapter là Redis Stream producer.”** Không: endpoint này dùng PUBLISH Pub/Sub. Redis Stream outbound là adapter khác dùng record append.

**“Redis PUBLISH lưu message để subscriber offline nhận lại.”** Không có subscriber backlog/replay mặc định.

**“PUBLISH trả về 3 là ba services đã commit.”** Kết quả lệnh không phải business acknowledgment.

**“Không có subscriber nghĩa là PUBLISH lỗi.”** Có thể là command thành công nhưng không recipient phù hợp; ứng dụng phải tự quyết định SLA.

**“Outbound adapter có replyChannel như gateway.”** Adapter một chiều không trả business reply.

**“Thêm Pollers.fixedDelay khiến Redis PUBLISH retry tin cậy.”** Poller chỉ áp dụng cho polling source/channel khác, không tạo Redis Pub/Sub persistence.

**“MessageChannel.send true nghĩa là mọi subscribers đã xử lý.”** Nó phản ánh ranh giới channel/handler, không consumer-level ACK.

**“RedisConnectionFactory tự publish khi bean được tạo.”** Kết nối không tự phát notification; phải có Message tới handler.

**“Topic PUBLISH phải được XGROUP CREATE trước.”** XGROUP thuộc Redis Streams, không phải Pub/Sub.

**“Redis List key và Pub/Sub channel cùng tên là cùng một queue.”** Là hai cơ chế độc lập.

**“Serializer mặc định sẽ tự chuyển POJO thành JSON như Jackson.”** Phải kiểm tra converter/serializer; dùng transformer hoặc serializer có contract rõ.

**“Spring MessageHeaders tự truyền sang Redis Pub/Sub.”** Redis Pub/Sub chỉ có channel/body; cần envelope hoặc mapper rõ ràng.

**“eventId có trong payload thì tự ngăn duplicate.”** Consumer phải triển khai idempotent processing/unique state.

**“MessageHeaders.ID là eventId ổn định qua publisher retry.”** Spring Message ID có thể thay đổi; tạo business eventId trước khi retry.

**“Chỉ có Redis RedisSerializer mới quan trọng.”** MessageConverter và serializer phối hợp; sai ở một bước sẽ lỗi wire format.

**“JSON String dùng JSON serializer sẽ luôn ra raw JSON object bytes.”** Có thể bị serialize như một JSON string literal; test raw bytes.

**“TopicExpression nhận URL query string nào cũng an toàn.”** Phải có allowlist, ACL và tenant policy.

**“Topic prefix prod là cơ chế bảo mật.”** Prefix chỉ là convention; không thay Redis ACL/network isolation.

**“Redis Pub/Sub tách hoàn toàn theo Redis database index.”** Không coi index như vhost/tenant boundary của topic.

**“PublishSubscribeChannel nội bộ bằng Redis Pub/Sub.”** Một cái fan-out Spring Messages trong app; cái kia Pub/Sub qua Redis.

**“Hai replicas subscribe thì messages được chia một nửa.”** Pub/Sub broadcast tới subscribers; chia việc là queue/consumer group use case.

**“Redis errorChannel tự tạo DLQ bền vững cho Pub/Sub.”** Error handling nội bộ không tạo replay/durable queue bên Redis.

**“Subscriber ném exception làm Redis redeliver notification.”** Pub/Sub không có consumer NACK/requeue.

**“AfterCommit PUBLISH là atomic với DB transaction.”** JVM có thể crash sau DB commit trước Redis command.

**“Transactional outbox + Pub/Sub bảo đảm subscriber offline nhận được.”** Outbox bảo vệ ý định ở producer; consumer vẫn có thể bỏ lỡ Pub/Sub.

**“Chỉ tăng retry vô hạn là đạt at-least-once end-to-end.”** Retry command có UNKNOWN outcome/duplicate và không tạo subscriber backlog.

**“ExecutorChannel làm publish bền vững.”** Task trong executor queue thường là memory, crash có thể mất.

**“QueueChannel mặc định giữ events qua restart.”** QueueChannel cần persistent MessageStore nếu muốn bền vững, và vẫn không tự sửa delivery Pub/Sub phía nhận.

**“Redis bật AOF/RDB nghĩa là Pub/Sub có replay.”** Persistence Redis state không biến Pub/Sub notifications thành stream records.

**“Redis Classic PUBLISH và Sharded SPUBLISH luôn tương đương trong mọi client/Cluster.”** Hãy kiểm tra API/client/topology; không giả định adapter tự đổi lệnh.

**“NUMSUB bằng 1 chứng minh đúng SearchService đang nhận.”** Có thể chỉ là Redis CLI/instance khác; phải giám sát service.

**“Một test happy path đã chứng minh không mất message.”** Cần test subscriber offline, reconnect, Redis outage, publish outcome UNKNOWN, serializer và schema.

**“Subscriber nhận JSON hợp lệ nghĩa là được phép xử lý tenantRef đó.”** Schema validation không thay authorization.

**“Outbound adapter publish thành công nên cache chắc chắn không stale.”** Subscriber có thể offline hoặc handler lỗi; TTL/reconciliation mới bảo vệ tính đúng có giới hạn.

## 23. Checklist thiết kế trước production

| Nhóm | Câu hỏi cần xác minh |
| --- | --- |
| **Use case** | Redis Pub/Sub best-effort có phù hợp nếu subscriber offline không? |
| **Đúng endpoint** | Dùng RedisPublishingMessageHandler/Redis.outboundChannelAdapter, không nhầm queue/store/stream? |
| **MessageChannel** | Input channel tên gì, ai gửi, có duplicate handler/flow không? |
| **Transaction** | Notification được phát trước/sau DB commit? Crash gap được khôi phục bằng gì? |
| **Producer eventId** | eventId có ổn định giữa retries không? Có domain/business idempotency? |
| **Topic contract** | Topic cố định hay expression? Namespace/version/environment? |
| **Topic security** | Có allowlist và Redis PUBLISH ACL theo kênh không? |
| **Connection** | RedisConnectionFactory đúng host/topology, TLS, credentials/timeouts? |
| **Converter** | MessageConverter có tạo đúng kiểu payload cần serialize không? |
| **Serializer** | StringRedisSerializer/JSON/custom bytes có khớp inbound không? |
| **Payload** | schemaVersion, eventType, occurredAt, productId/version, size limit? |
| **Headers** | Metadata cần qua Redis đã đưa vào envelope thay vì tin có wire headers? |
| **Subscriber** | Redis inbound subscribe đúng topic/pattern, có readiness trước PUBLISH? |
| **Fan-out** | Bao nhiêu replicas nhận? Event có an toàn khi xử lý trên tất cả replicas? |
| **Delivery** | Không có Pub/Sub ACK/backlog/replay đã được ghi trong SLA? |
| **Error handling** | Conversion/topic/Redis command errors đi đâu? Thread sync/async? |
| **Retry** | Retry budget/backoff và handling UNKNOWN publish outcome? |
| **Fallback** | Cache TTL, refetch, reconciliation hay durable Stream/broker? |
| **Lifecycle** | Startup, shutdown, reconnect và failover được test chưa? |
| **Capacity** | Publish bursts, subscriber throughput, client buffers và rate limits? |
| **Monitoring** | Publisher attempt/success/fail, subscriber receive/handle, cache stale age? |
| **Cluster** | Classic Pub/Sub vs sharded Pub/Sub, correct Redis topology/client support? |
| **Testing** | Redis thật, no-subscriber case, serializer bytes, duplicate, Redis outage? |
| **Versioning** | Rolling deployments có consumers cũ/mới và schema compatibility? |
| **Privacy** | Payload/log/retention có chứa PII/token không cần thiết? |

### 23.1. Quy tắc lựa chọn nhanh

**Chọn Redis outbound channel adapter PUBLISH** khi muốn gửi notification đến nhiều subscribers đang online, ví dụ cache invalidation, dashboard refresh, ephemeral state update, với điều kiện có thể chấp nhận và sửa **missed notifications**.

**Chọn Redis queue outbound** khi muốn đưa job vào Redis List để competing workers nhận, sau khi đã hiểu destructive POP window.

**Chọn Redis Stream outbound hoặc AMQP/Kafka/JMS durable producer** nếu business events cần record IDs, backlog/replay, consumer progress, retry và audit.

**Chọn Redis command gateway** khi workflow cần trả kết quả của Redis command, không phải một broadcast notification.

### 23.2. Lộ trình triển khai an toàn

~~~text
1. Xác định business source of truth và mức stale chấp nhận.
2. Thiết kế topic namespace + JSON envelope + eventId/schemaVersion.
3. Dùng transformer tạo JSON UTF-8 minh bạch.
4. Redis outbound adapter với topic cố định trước.
5. Subscriber inbound cùng topic, assert raw wire format.
6. Test subscriber offline và no-replay behavior.
7. Bổ sung TTL/version/reconciliation, monitoring hai phía.
8. Nếu cần durable delivery, thay source/handoff bằng Stream/broker/outbox.
9. Chỉ bổ sung dynamic topic/async queue khi có use case và test riêng.
~~~

### 23.3. Bốn mốc không được trộn

~~~text
Mốc 1: Business DB commit thành công.
Mốc 2: Spring Integration outbound handler nhận message.
Mốc 3: Redis PUBLISH command thành công.
Mốc 4: Mỗi subscriber xử lý và commit business outcome.
~~~

Trong Redis Pub/Sub **không có protocol trả về mốc 4 về mốc 3**. Muốn biết mốc 4, cần subscriber metrics, reconciliation, một kênh xác nhận ứng dụng khác hoặc chuyển sang hạ tầng durable message processing.

## 24. Câu hỏi tự kiểm tra

1. Redis outbound channel adapter trong Spring Integration phát thông điệp bằng Redis command nào?
2. RedisPublishingMessageHandler khác RedisQueueOutboundChannelAdapter ở điểm nào?
3. Spring Integration MessageChannel đóng vai trò gì trước Redis outbound handler?
4. Vì sao Redis Pub/Sub outbound là **one-way adapter**, không phải gateway?
5. Một Redis topic có cần tạo bằng lệnh XGROUP CREATE trước khi PUBLISH không?
6. Khi subscriber không online, PUBLISH có lưu message cho subscriber đó nhận sau không?
7. Lệnh PUBLISH trả về số subscribers > 0 có chứng minh business handler thành công không?
8. Redis PUBLISH khác LPUSH và XADD ở dữ liệu giữ lại thế nào?
9. Redis store outbound adapter dùng cho những collection types nào?
10. Vì sao không dùng PUBLISH làm nguồn duy nhất của PaymentSettled event?
11. Khi nào Pub/Sub phù hợp cho invalidation cache của ba replicas?
12. RedisConnectionFactory có phải thành phần tự tạo Spring Message không?
13. Trong Java DSL, phương thức nào cấu hình outbound adapter cho Redis?
14. RedisPublishingMessageHandler có thể được khai báo trực tiếp bằng @ServiceActivator không?
15. setTopic và setTopicExpression có nên đặt đồng thời không?
16. topicExpression đọc headers['redisTopic'] có rủi ro nào nếu header đến từ HTTP input không xác thực?
17. Làm sao dùng enum/allowlist để giới hạn dynamic topic?
18. Vì sao prefix dev/prod không thể thay Redis ACL?
19. MessageConverter và RedisSerializer phục vụ hai giai đoạn khác nhau nào?
20. Nếu payload đã là JSON String, dùng JSON serializer serialize String thêm lần nữa có thể gây lỗi gì?
21. Redis Pub/Sub có tự truyền Spring MessageHeaders.ID, correlationId, replyChannel và contentType không?
22. Vì sao cần eventId ổn định qua producer retries?
23. Khi subscriber nhận raw byte[], phải giải mã charset và kiểm tra JSON như thế nào?
24. Vì sao cùng schemaVersion/eventType có thể được dùng để hỗ trợ rolling deployment?
25. RedisInboundChannelAdapter ở SearchService phải subscribe thế nào để nhận topic outbound đang publish?
26. Exact topic và pattern subscriptions chồng nhau có thể gây vấn đề gì?
27. DirectChannel khác ExecutorChannel thế nào về exception propagation và durability?
28. QueueChannel ở trước Redis outbound có tự tạo Pub/Sub backlog bền vững không?
29. Nếu Redis command bị timeout ở ranh giới response, vì sao retry có thể gây duplicate?
30. Redis reconnect thành công có phục hồi notifications phát trong outage không?
31. Nếu Database rollback sau khi đã PUBLISH, subscriber có thể thấy một event sai thế nào?
32. Publish afterCommit giải quyết vấn đề gì và còn cửa sổ mất event nào?
33. Transactional outbox ở producer giúp khôi phục điều gì, và không thể bảo đảm điều gì ở Pub/Sub subscriber?
34. Với cache invalidation, TTL/version/refetch giúp xử lý missed notification thế nào?
35. Vì sao producer publish result=2 không chứng minh hai cache replicas đã invalidate?
36. Trong Redis Cluster, Classic Pub/Sub và Sharded Pub/Sub cần kiểm tra gì khi cấu hình adapter?
37. Vì sao Redis database index không phải tenant isolation boundary cho Pub/Sub?
38. Nếu Redis PUBLISH thành công nhưng SearchService cache stale, bạn debug những ranh giới nào?
39. ErrorChannel có tự làm Redis redeliver message tới subscriber đã throw exception không?
40. Những lỗi nào nên retry có giới hạn và lỗi nào nên fail fast?
41. Một integration test nào chứng minh subscriber offline không có replay?
42. Vì sao integration test phải chờ subscriber readiness trước khi PUBLISH?
43. Một integration test nào kiểm tra producer/consumer dùng cùng serializer UTF-8?
44. Khi publisher dùng topicExpression, cần test unauthorized topic như thế nào?
45. Nếu hai handlers cùng publish một logical event, cách điều tra duplicate là gì?
46. Với SFTP → Redis outbound, poller nào đang thực sự chạy theo lịch?
47. Redis outbound → Kafka bridge có thể mất event ở đâu trước khi Kafka nhận?
48. Nếu có một Kafka ACK nhưng Redis source Pub/Sub đã bỏ lỡ message lúc bridge offline, Kafka có phục hồi được không?
49. Metric nào là publisher success, metric nào là subscriber business success, metric nào đo cache staleness?
50. Khi nào nên thay Redis Pub/Sub bằng Redis Streams, AMQP, Kafka hoặc JMS?

## 25. Tài liệu tham khảo và giới hạn phiên bản

Đối chiếu các nguồn chính thức trước khi triển khai:

- [Spring Integration – Redis Support](https://docs.spring.io/spring-integration/reference/redis.html): Redis outbound channel adapter, Java DSL, Java bean/XML, message converter và topic-expression.
- [Spring Integration – RedisPublishingMessageHandler Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/redis/outbound/RedisPublishingMessageHandler.html): setTopic, setTopicExpression, setSerializer và setMessageConverter.
- [Spring Integration – RedisOutboundChannelAdapterSpec Javadoc](https://www.springframework.org/spring-integration/docs/7.1.0-SNAPSHOT/api/org/springframework/integration/redis/dsl/RedisOutboundChannelAdapterSpec.html): Redis.outboundChannelAdapter DSL options, topicExpression và topicFunction trong các phiên bản hỗ trợ.
- [Spring Data Redis – Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html): RedisMessageListenerContainer, topics/patterns và Redis client semantics.
- [Redis – Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): PUBLISH/SUBSCRIBE, at-most-once message delivery, sharded Pub/Sub.
- [Redis – PUBLISH](https://redis.io/docs/latest/commands/publish/): lệnh PUBLISH và ý nghĩa kết quả command.

**Lưu ý:** Ví dụ Java DSL và direct bean được viết theo Spring Integration API chính thức có các thành phần RedisPublishingMessageHandler, RedisOutboundChannelAdapterSpec, SimpleMessageConverter và StringRedisSerializer. Một số overloads/packages/configuration có thể thay đổi theo phiên bản Spring Boot–Spring Integration–Spring Data Redis. Khi đưa code vào project, phải **biên dịch, kiểm thử Redis thật, kiểm tra serializer và error semantics của dependency cụ thể**. Bài học này hoàn thành bước soạn nội dung STEP 4; không thay thế vòng Content QA chuyên sâu ở STEP 6.

## Tổng kết

**Redis outbound channel adapter** là endpoint **một chiều** chuyển Spring Integration Message sang **Redis Pub/Sub PUBLISH**. Trong Java, có thể dùng **RedisPublishingMessageHandler** hoặc **Redis.outboundChannelAdapter(...)**; lựa chọn topic cố định hay dynamic **topicExpression** phụ thuộc chính sách định tuyến, nhưng phải có **allowlist và Redis ACL** phù hợp. **MessageConverter và RedisSerializer** phải thống nhất với Redis inbound consumer về wire format, charset và schema.

Giới hạn cốt lõi là **PUBLISH không tạo backlog/ACK/replay cho subscriber offline**. Redis command success, MessageChannel.send success hoặc subscriber count không phải bằng chứng các downstream business handlers đã hoàn tất. Khi notification chỉ giúp **cache invalidation**, sử dụng TTL, productVersion, idempotent handler và reconciliation giúp xử lý tình huống mất thông điệp. Khi cần delivery bền vững, dùng Redis Streams, List queue có recovery, AMQP, Kafka, JMS hoặc durable database job/outbox theo SLA.

Khi nối Redis outbound với File/SFTP, HTTP, JMS, AMQP, Kafka và database trong **SPRING_INTEGRATION_ADAPTERS**, hãy tách biệt rõ các mốc **business commit → integration handoff → Redis PUBLISH → subscriber business outcome**, rồi thiết kế timeout, lỗi, retry, monitoring và khả năng phục hồi cho từng ranh giới. Một Redis outbound flow chất lượng không chỉ publish được thông điệp, mà còn **nói rõ notification có thể mất ở đâu, trùng ở đâu và hệ thống sửa sai như thế nào**.
