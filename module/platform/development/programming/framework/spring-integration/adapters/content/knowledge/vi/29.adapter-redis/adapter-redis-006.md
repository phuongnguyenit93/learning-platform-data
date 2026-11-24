# Redis queue outbound adapter

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **Redis queue outbound channel adapter** lấy Spring Integration Message từ MessageChannel và **đẩy một giá trị vào Redis List** bằng LPUSH hoặc RPUSH.
- Phân biệt chính xác Redis queue outbound với Redis **Pub/Sub outbound (PUBLISH)**, **store outbound (ghi collection)**, **Stream outbound (XADD)** và **queue outbound gateway (request–reply)**.
- Chọn chiều **LPUSH/BRPOP** hoặc **RPUSH/BLPOP** để bảo toàn FIFO; nhận biết các cặp push/pop cùng đầu tạo hành vi kiểu stack.
- Cấu hình **RedisQueueOutboundChannelAdapter** và **Redis.queueOutboundChannelAdapter(...)** với RedisConnectionFactory, serializer, extractPayload, leftPush và queue/queue-expression.
- Ghi **JSON UTF-8** theo hợp đồng eventId, schemaVersion, attempt và business IDs; ghép đúng serializer với Redis queue inbound.
- Hiểu ranh giới **đã enqueue** khác **đã dequeue**, **đã commit nghiệp vụ** và **đã ACK**; nhận biết nguy cơ mất item sau destructive POP.
- Thiết kế **idempotency**, retry có giới hạn, outbox/reconciliation, xử lý poison item, ACL, monitoring, lifecycle và khôi phục khi Redis/client lỗi.
- Kiểm thử queue direction, payload bytes, dynamic queue routing, competing consumers, duplicate, Redis failover và các khoảng crash bằng Redis thật.

## 1. Bài toán: chuyển một công việc từ Spring Integration sang Redis List

Giả sử **CatalogService** nhận ảnh mới qua HTTP hoặc SFTP. Dịch vụ không muốn tạo thumbnail đồng bộ trong request thread. Sau khi lưu ảnh gốc và metadata, nó tạo một **thumbnail job** để **ImageWorker** xử lý:

~~~text
Redis key: catalog:{thumbnail}:pending
Payload:
{
  "eventId": "evt-thumb-1001",
  "eventType": "THUMBNAIL_REQUESTED",
  "schemaVersion": 1,
  "productId": "P-1001",
  "imageVersion": 5,
  "objectKey": "tenant-a/products/P-1001/v5/original.jpg"
}
~~~

Luồng:

~~~mermaid
flowchart LR
    SRC["HTTP / SFTP / File inbound"] --> VALID["Validate + persist metadata"]
    VALID --> OUT["Spring Integration<br/>MessageChannel"]
    OUT --> AD["Redis queue outbound<br/>RedisQueueOutboundChannelAdapter"]
    AD -->|"LPUSH"| REDIS[("Redis List<br/>catalog:thumbnail:pending")]
    REDIS -->|"BRPOP"| IN["Redis queue inbound"]
    IN --> HAND["ImageWorker<br/>thumbnail handler"]
    HAND --> DB[("Product DB + object storage")]
~~~

**Redis queue outbound adapter** là endpoint ở phía **producer**: nó nhận một Spring Message, chọn Redis List key, serialize đối tượng được gửi và gọi thao tác push. Nó **không chờ ImageWorker hoàn tất**, không trả thumbnail, cũng không tự tạo acknowledgment. Khi dữ liệu được ghi vào List, producer có thể kết thúc trách nhiệm **enqueue** theo hợp đồng đang dùng.

Đây là bài của chương **Adapter Redis**, module **SPRING_INTEGRATION_ADAPTERS**. Module tập trung kết nối các hệ thống ngoài qua inbound/outbound adapter, gateway, poller, MessageChannel, cũng như tích hợp File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Trong bài này, trọng tâm là **đẩy work item vào Redis List**, không biến Redis List thành một message broker có ACK chỉ bằng cách thêm một adapter.

## 2. Bản chất Redis List: LPUSH, RPUSH, BLPOP, BRPOP

Redis List giữ dãy giá trị theo thứ tự từ **left/head** sang **right/tail**. Các lệnh cơ bản:

| Lệnh | Tác dụng | Có xóa item khỏi List? |
| --- | --- | --- |
| LPUSH key value | Thêm item vào **trái** | Không |
| RPUSH key value | Thêm item vào **phải** | Không |
| LPOP key | Lấy item bên **trái** | **Có** |
| RPOP key | Lấy item bên **phải** | **Có** |
| BLPOP key timeout | Chờ và lấy bên **trái** | **Có** khi nhận item |
| BRPOP key timeout | Chờ và lấy bên **phải** | **Có** khi nhận item |
| LLEN key | Đếm items còn trong List | Không |
| LRANGE key start stop | Xem một range (diagnostics) | Không |

### 2.1. LPUSH kết hợp BRPOP tạo FIFO

Giả sử producer gửi A, B, C:

~~~text
LPUSH A        [ A ]
LPUSH B        [ B, A ]
LPUSH C        [ C, B, A ]
BRPOP          [ C, B ]  -> A
BRPOP          [ C ]     -> B
BRPOP          [ ]       -> C
~~~

Item nào **vào trước** được pop ra trước, với điều kiện **không có thêm producer/consumer tương tác ngoài hợp đồng** và chúng ta đang nói đến **thứ tự pop của List**, không phải thứ tự xử lý xong.

### 2.2. RPUSH kết hợp BLPOP cũng tạo FIFO

~~~text
RPUSH A        [ A ]
RPUSH B        [ A, B ]
RPUSH C        [ A, B, C ]
BLPOP          [ B, C ]  -> A
BLPOP          [ C ]     -> B
BLPOP          [ ]       -> C
~~~

Đây là lựa chọn phù hợp khi tích hợp với một worker bên ngoài có contract **BLPOP**.

### 2.3. Cùng đầu push/pop dẫn đến LIFO

~~~text
LPUSH A, LPUSH B, LPUSH C -> [ C, B, A ]
BLPOP -> C, rồi B, rồi A
~~~

**Không thể chỉ đặt leftPush(true) và kết luận FIFO**. Phải kiểm tra cả phía nhận là **rightPop(true)** hay **rightPop(false)**.

### 2.4. Mặc định của hai adapter Spring Integration

Theo tài liệu Spring Integration Redis:

- Redis **queue outbound** mặc định **leftPush=true**.
- Redis **queue inbound** mặc định **rightPop=true**.
- Ghép hai mặc định đó tạo một hàng đợi **FIFO theo thứ tự pop**.
- Tùy chọn leftPush/rightPop được thêm từ Spring Integration **4.3**.

| Producer outbound | Consumer inbound | Thứ tự item được lấy |
| --- | --- | --- |
| leftPush(true) → LPUSH | rightPop(true) → BRPOP | **FIFO** |
| leftPush(false) → RPUSH | rightPop(false) → BLPOP | **FIFO** |
| leftPush(true) → LPUSH | rightPop(false) → BLPOP | **LIFO** |
| leftPush(false) → RPUSH | rightPop(true) → BRPOP | **LIFO** |

Với hai consumers hoạt động song song, Redis pop một item nguyên tử cho **một** consumer, nhưng A có thể xử lý job 10 giây, B xử lý 1 giây: **completion order không còn là FIFO**.

## 3. Redis List queue không phải Redis Pub/Sub, Stream hay gateway

| Mô hình | Hành động phía outbound | Khi worker offline | Hợp đồng xử lý |
| --- | --- | --- | --- |
| **Redis queue outbound** | LPUSH/RPUSH vào **List** | Item chưa pop có thể còn trong List | Competing consumers, không có ACK native của List POP |
| Redis Pub/Sub outbound | PUBLISH tới topic | Notification bị bỏ qua đối với subscriber offline | Best-effort broadcast |
| Redis Stream outbound | XADD record vào Stream | Record còn nếu retention cho phép | Record ID, consumer groups/PEL/XACK nếu dùng đúng |
| Redis store outbound | Ghi vào List/Set/ZSet/Map/Properties | State còn theo Redis persistence/TTL | State mutation, không tự là work claim |
| Redis queue outbound gateway | Gửi request và chờ reply theo Redis queue protocol | Phụ thuộc timeout/recovery | Request–reply có correlation riêng |

### 3.1. Queue outbound là one-way adapter

~~~mermaid
sequenceDiagram
    participant C as CatalogService
    participant O as Redis queue outbound
    participant R as Redis List
    participant W as ImageWorker
    C->>O: send(Message<Job JSON>)
    O->>R: LPUSH catalog:thumbnail:pending JSON
    R-->>O: Redis command result
    O-->>C: Handler returns
    W->>R: BRPOP catalog:thumbnail:pending
    R-->>W: Job JSON (removed from List)
    W->>W: Business processing
    Note over C,W: Không có response ImageWorker trả về producer
~~~

Nếu cần producer gửi yêu cầu rồi đợi đáp án thumbnail URL, chọn một **gateway request–reply** hoặc API/async callback có correlation, không chờ QueueOutboundChannelAdapter tự tạo reply.

### 3.2. Redis List không có pending/ACK native

Một khi **BRPOP** trả item cho worker, item **đã rời khỏi List**. Nếu worker chết ngay sau đó, Redis không tự đưa item về pending. Bản thân việc LPUSH thành công **không giải quyết cửa sổ mất ở phía tiêu thụ**.

### 3.3. Queue inbound là message-driven

Spring Integration Redis queue inbound dùng một **listener task/blocking pop**; nó **không cần Spring Integration poller** riêng. Vì vậy:

~~~text
Redis queue outbound: MessageChannel -> Redis List PUSH
Redis queue inbound:  Redis List blocking POP -> MessageChannel
~~~

Khác với **Redis store inbound**: source nhận một **RedisStore view** qua poller, không pop một item.

## 4. Các thành phần và option của queue outbound adapter

Thành phần triển khai:

~~~java
org.springframework.integration.redis.outbound.RedisQueueOutboundChannelAdapter
~~~

Trong Java DSL:

~~~java
org.springframework.integration.redis.dsl.Redis
~~~

Các tùy chọn chính:

| Option | Mặc định | Vai trò |
| --- | --- | --- |
| queue | Bắt buộc chọn | Tên Redis **List key** cố định |
| queue-expression | Thay thế queue | SpEL xác định Redis key khi message tới |
| connection-factory | RedisConnectionFactory | Kết nối Redis |
| serializer | Phụ thuộc payload và cấu hình | Serialize object thành bytes để LPUSH/RPUSH |
| extract-payload | **true** | Đẩy payload hay toàn bộ Spring Message |
| left-push | **true** | LPUSH nếu true; RPUSH nếu false |
| input channel | Tên channel được chọn | Spring MessageChannel gửi đến handler |

**queue và queue-expression loại trừ nhau**. Khi dùng queue-expression, incoming Message là **root** để đánh giá biểu thức. Không lấy raw Redis key do client ngoài truyền trực tiếp mà bỏ qua validation.

### 4.1. Serializer mặc định cần được hiểu đúng

Tài liệu Spring Integration ghi rõ: mặc định thường dùng **JdkSerializationRedisSerializer**, nhưng khi payload là **String** và chưa chỉ định serializer, framework có thể chọn **StringRedisSerializer**. Vì vậy hai loại message đi qua cùng adapter **không nên được coi là cùng wire format** nếu không có cấu hình rõ.

**Khuyến nghị:** Với JSON String liên dịch vụ, chỉ định **StringRedisSerializer** tường minh ở outbound và deserializer tương ứng ở inbound. Tránh để mặc định serializer là chi tiết ngầm định của việc nâng Spring Boot/Spring Integration.

### 4.2. extractPayload=true là mặc định

Khi true, Redis List chỉ chứa giá trị của **message.getPayload()** sau serialization. Các Spring MessageHeaders như replyChannel, errorChannel, ID, trace context **không tự được đưa vào List**.

Khi false, endpoint serialize **toàn bộ Spring Message**; phải thống nhất format/deserializer phía nhận và kiểm tra loại Message/headers có serializable/trusted hay không. Không dùng cách này như phương án mặc định để truyền event liên dịch vụ.

## 5. Dependencies và RedisConnectionFactory

Trong một dự án Spring Boot dùng Maven và dependency management tương thích:

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

Cấu hình Redis **chỉ cho local/test**:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 3s
      timeout: 3s
~~~

Production phải cân nhắc TLS, Redis ACL, credentials từ secret manager, network isolation, Sentinel/Cluster, retry/timeout và memory policy. Tên properties phụ thuộc phiên bản Spring Boot; dùng BOM và configuration metadata thực tế khi triển khai.

### 5.1. RedisConnectionFactory chỉ là transport

**RedisConnectionFactory** cung cấp Redis connections. Nó không tự tạo Redis List, không poll queue, không serialize một POJO thành JSON và không bảo đảm một thumbnail đã được tạo. RedisQueueOutboundChannelAdapter dùng factory để thực hiện push khi có Spring Message.

### 5.2. Redis List key được tạo khi push

Thông thường, khi LPUSH/RPUSH vào key **chưa tồn tại**, Redis tạo List có phần tử được thêm. Không cần provision một queue resource như JMS destination hoặc RabbitMQ exchange/binding. Tuy nhiên:

- Nếu key đang tồn tại với **Redis type khác**, lệnh có thể lỗi **WRONGTYPE**.
- Redis ACL có thể từ chối ghi key.
- Redis memory/maxmemory policy có thể làm command lỗi hoặc eviction theo cấu hình.
- TTL có thể đã được thiết lập bởi service khác và làm key/list biến mất theo thời gian.

### 5.3. Redis List key khác Redis channel name

Một Redis key tên **catalog:{thumbnail}:pending** là một giá trị Redis List, không phải Pub/Sub channel cùng tên. Gọi **LPUSH** không tạo message cho SUBSCRIBE; để worker nhận, dùng **BRPOP/BLPOP** hoặc Redis queue inbound adapter.

## 6. Thiết kế payload thumbnail job

Để giao tiếp giữa CatalogService và ImageWorker, nên dùng một **job envelope** có ID nghiệp vụ ổn định và schema rõ.

~~~json
{
  "eventId": "evt-thumb-1001",
  "eventType": "THUMBNAIL_REQUESTED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "tenantRef": "tenant-a",
  "productId": "P-1001",
  "imageVersion": 5,
  "objectKey": "tenant-a/products/P-1001/v5/original.jpg"
}
~~~

### 6.1. eventId và Spring MessageHeaders.ID là khác nhau

| Trường | Dùng vào việc gì? |
| --- | --- |
| **eventId** | Idempotency, retry, audit xuyên services |
| **eventType** | Chọn handler đúng nghiệp vụ |
| **schemaVersion** | Validate/upgrade payload contract |
| **productId + imageVersion** | Tránh task cũ ghi đè output của ảnh mới |
| **objectKey** | Tham chiếu object storage đã được cấp quyền |
| **Spring MessageHeaders.ID** | ID của message runtime bên trong integration flow |

Spring Message ID có thể thay đổi khi tạo lại Spring Message/retry. **Không dùng nó như business eventId** nếu cần deduplicate xuyên process restarts.

### 6.2. Tại sao không chứa toàn bộ ảnh trong Redis List?

Redis List nằm trong bộ nhớ Redis (và chịu chính sách persistence/memory). Đẩy ảnh nhiều MB vào mỗi item có thể tạo:

- Memory pressure và replication/AOF overhead.
- Latency/network spikes khi serialize, push hoặc pop.
- Cản trở công cụ quan sát và dead-letter.
- Chi phí giải mã lớn ở worker.

Thay vào đó lưu ảnh trong **object storage có phân quyền**, gửi **objectKey/ID/version** trong job. Consumer vẫn phải kiểm tra tenant ownership, content type, size và path namespace trước khi đọc file.

### 6.3. Hợp đồng phiên bản

Worker đang chạy schemaVersion=1 có thể nhận job đã được enqueue từ trước khi deploy mới. Vì queue giữ backlog cho workers offline, rolling deployment phải tính đến **payload cũ còn lại trong Redis**. Không xóa field bắt buộc hoặc đổi ý nghĩa imageVersion mà thiếu migration/compatibility policy.

### 6.4. Job identity và retry

Nếu producer timeout ở ranh giới LPUSH rồi retry, cùng eventId có thể nằm **hai lần trong Redis List**. Consumer phải có idempotency ledger hoặc unique business key; riêng Redis List không có unique constraint cho items.

## 7. Java DSL: Redis.queueOutboundChannelAdapter(...)

Ví dụ cấu hình một flow nhận JSON String qua **thumbnailJobsOutbound** và ghi bằng **LPUSH** vào **catalog:{thumbnail}:pending**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.redis.dsl.Redis;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class ThumbnailRedisQueueOutboundConfig {

    public static final String QUEUE = "catalog:{thumbnail}:pending";

    @Bean
    public MessageChannel thumbnailJobsOutbound() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow thumbnailRedisQueueOutboundFlow(
            RedisConnectionFactory factory) {
        return IntegrationFlow.from("thumbnailJobsOutbound")
            .handle(Redis.queueOutboundChannelAdapter(QUEUE, factory)
                .serializer(new StringRedisSerializer())
                .extractPayload(true)
                .leftPush(true))
            .get();
    }
}
~~~

**Tác dụng:** message có payload kiểu String được serialize thành UTF-8 bytes rồi **LPUSH** vào Redis List key. Không có consumer reply, và dữ liệu không được tự tạo thành một Redis Stream record.

**Đối chiếu phiên bản:** Các phương thức factory/spec được mô tả trong tài liệu Spring Integration Redis và Javadocs. Với versions có thay đổi DSL, kiểm tra dependency BOM, API spec và biên dịch trước production; **RedisQueueOutboundChannelAdapter(String, RedisConnectionFactory)** với setSerializer/setExtractPayload/setLeftPush là lựa chọn bean API tương ứng được tài liệu hóa.

### 7.1. Vì sao khai báo DirectChannel?

DirectChannel truyền Spring Message trực tiếp cho subscriber handler trong cùng đường gọi. Nếu Redis ghi thất bại, exception có thể được propagate về caller, giúp upstream chọn cách xử lý. Nhưng **send trả về không đồng nghĩa business worker hoàn tất**, vì worker có thể chưa nhận item.

### 7.2. Queue name cố định

**QUEUE** là một **Redis List key**. Giá trị có dấu **{thumbnail}** minh họa Redis Cluster hash tag (hữu ích nếu sau này dùng multi-key atomic commands cùng slot). Hash tag **không làm LPUSH bền vững hơn** và không phải Redis Pub/Sub channel pattern.

### 7.3. extractPayload=true

Nếu Spring Message có các headers **tenantId, traceId, correlationId, replyChannel**, outbound adapter ở chế độ này **không gửi headers như một envelope**. Muốn worker nhận những trường cần thiết, hãy đưa chúng vào JSON schema có kiểm tra, không serialize toàn bộ runtime Message headers tùy tiện.

### 7.4. leftPush=true phải ghép với rightPop=true

Đặt **leftPush(true)** là phía producer. Còn **rightPop(true)** thuộc cấu hình Redis queue inbound consumer. Một bên mặc định không đảm bảo phía kia đang sử dụng hướng nhận mặc định, nhất là khi worker là Node.js/Python code bên ngoài.

## 8. Producer service: tạo JSON rồi gửi Spring Message

Nên có một DTO typed cho business dữ liệu, serialize ở ranh giới outbound một cách rõ ràng:

~~~java
import java.time.Instant;

public record ThumbnailRequested(
        String eventId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String tenantRef,
        String productId,
        long imageVersion,
        String objectKey) {
}
~~~

Service producer dùng Jackson ObjectMapper:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class ThumbnailJobPublisher {

    private final ObjectMapper objectMapper;
    private final MessageChannel thumbnailJobsOutbound;

    public ThumbnailJobPublisher(
            ObjectMapper objectMapper,
            @Qualifier("thumbnailJobsOutbound")
            MessageChannel thumbnailJobsOutbound) {
        this.objectMapper = objectMapper;
        this.thumbnailJobsOutbound = thumbnailJobsOutbound;
    }

    public void enqueueNewImage(
            String tenantRef,
            String productId,
            long imageVersion,
            String objectKey) {

        if (tenantRef == null || tenantRef.isBlank()
                || productId == null || productId.isBlank()
                || imageVersion <= 0
                || objectKey == null || objectKey.isBlank()) {
            throw new IllegalArgumentException("Invalid thumbnail job");
        }

        ThumbnailRequested job = new ThumbnailRequested(
            "evt-thumb-" + UUID.randomUUID(),
            "THUMBNAIL_REQUESTED",
            1,
            Instant.now(),
            tenantRef,
            productId,
            imageVersion,
            objectKey);

        try {
            String json = objectMapper.writeValueAsString(job);
            boolean accepted = thumbnailJobsOutbound.send(
                MessageBuilder.withPayload(json).build());
            if (!accepted) {
                throw new IllegalStateException(
                    "Outbound channel rejected thumbnail job");
            }
        }
        catch (JsonProcessingException e) {
            throw new IllegalArgumentException(
                "Cannot serialize thumbnail job", e);
        }
    }
}
~~~

**Quan trọng về eventId:** Ví dụ tạo UUID cho **mỗi yêu cầu nghiệp vụ mới**. Nếu retry cùng một yêu cầu vì kết quả LPUSH không rõ, **phải giữ nguyên eventId của job cũ**. Một bản production nên tạo/lưu jobId/eventId trong cùng transaction nghiệp vụ hoặc outbox rồi retry từ bản đó; không gọi lại phương thức tạo UUID để biến một retry thành sự kiện mới.

### 8.1. Serialize rõ thay vì đưa POJO trực tiếp

Với **StringRedisSerializer**, gửi ThumbnailRequested POJO trực tiếp có thể gây serializer type mismatch. Chuyển thành JSON String trước khi gọi channel giúp producer–consumer có contract độc lập ngôn ngữ. Có thể dùng transformer trong IntegrationFlow thay vì service, miễn là việc chuyển đổi không bị mập mờ.

### 8.2. ObjectMapper phải hỗ trợ java.time

Spring Boot thường tự cấu hình Jackson JavaTimeModule khi có dependency liên quan, nhưng phải kiểm tra version và serialization contract cho Instant. Nếu object mapper không hỗ trợ kiểu thời gian được dùng, **fail trước khi enqueue** và không giả định Redis có lỗi.

### 8.3. Không log full objectKey/PII vô hạn

Log eventId, eventType, productId đã được phép quan sát và outcome; không tự log credentials, signed URLs, email hay tenant secrets trong job payload.

## 9. Bean Java: RedisQueueOutboundChannelAdapter và @ServiceActivator

Nếu không dùng DSL, có thể khai báo trực tiếp **RedisQueueOutboundChannelAdapter** làm MessageHandler:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.redis.outbound.RedisQueueOutboundChannelAdapter;

@Configuration
public class ThumbnailRedisQueueHandlerConfig {

    @Bean
    @ServiceActivator(inputChannel = "thumbnailJobsOutbound")
    public RedisQueueOutboundChannelAdapter thumbnailQueueHandler(
            RedisConnectionFactory factory) {

        RedisQueueOutboundChannelAdapter handler =
            new RedisQueueOutboundChannelAdapter(
                "catalog:{thumbnail}:pending", factory);

        handler.setSerializer(new StringRedisSerializer());
        handler.setExtractPayload(true);
        handler.setLeftPush(true);
        return handler;
    }
}
~~~

**Đây là phương án thay thế mục 7.** Chạy đồng thời cả flow DSL và @ServiceActivator trên cùng DirectChannel có thể tạo **cạnh tranh giữa subscribers** hoặc **duplicate enqueue** tùy topology. Với một bài lab, chỉ giữ **một** publisher endpoint trên input channel.

### 9.1. Constructor cố định hay expression?

Javadocs cho hai constructor:

~~~java
RedisQueueOutboundChannelAdapter(
    String queueName,
    RedisConnectionFactory connectionFactory);

RedisQueueOutboundChannelAdapter(
    org.springframework.expression.Expression queueNameExpression,
    RedisConnectionFactory connectionFactory);
~~~

Đây là **hai lựa chọn thay thế**, không đặt đồng thời queue name cố định và expression trên cùng endpoint rồi kỳ vọng tự ưu tiên một cái.

### 9.2. XML namespace

Với hệ thống dùng Spring Integration XML:

~~~xml
<int-redis:queue-outbound-channel-adapter
    id="thumbnailRedisQueueOutbound"
    channel="thumbnailJobsOutbound"
    connection-factory="redisConnectionFactory"
    queue="catalog:{thumbnail}:pending"
    serializer="stringRedisSerializer"
    extract-payload="true"
    left-push="true"/>
~~~

Bean **stringRedisSerializer** phải được khai báo riêng, tương ứng RedisSerializer. XML snippet chỉ minh họa cấu hình endpoint, chưa bao gồm namespace declarations/context và RedisConnectionFactory bean đầy đủ.

### 9.3. Handler không có replyChannel

RedisQueueOutboundChannelAdapter là một **outbound channel adapter**, không phải **RedisQueueOutboundGateway**. Nó không tự tạo UUID conversation và không đợi một Redis List reply. Nếu caller cần trạng thái thumbnail, nên dùng một API truy vấn trạng thái hoặc event completion được thiết kế riêng.

## 10. Redis queue inbound: ghép đúng phía nhận

Để chứng minh payload đã được enqueue có thể tới ImageWorker, cấu hình **RedisQueueMessageDrivenEndpoint** ở **ứng dụng worker khác**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.redis.inbound.RedisQueueMessageDrivenEndpoint;
import org.springframework.messaging.MessageChannel;

@Configuration
public class ThumbnailRedisQueueInboundConfig {

    @Bean
    public MessageChannel thumbnailJobsInput() {
        return new DirectChannel();
    }

    @Bean
    public RedisQueueMessageDrivenEndpoint thumbnailQueueInbound(
            RedisConnectionFactory factory,
            MessageChannel thumbnailJobsInput) {

        RedisQueueMessageDrivenEndpoint endpoint =
            new RedisQueueMessageDrivenEndpoint(
                "catalog:{thumbnail}:pending", factory);

        endpoint.setSerializer(new StringRedisSerializer());
        endpoint.setRightPop(true);
        endpoint.setOutputChannel(thumbnailJobsInput);
        endpoint.setAutoStartup(true);
        return endpoint;
    }
}
~~~

### 10.1. Phân biệt producer và consumer configuration

| Bên | Bean | Cấu hình direction | Vai trò |
| --- | --- | --- | --- |
| CatalogService | RedisQueueOutboundChannelAdapter | setLeftPush(true) | **LPUSH** item vào Redis List |
| ImageWorker | RedisQueueMessageDrivenEndpoint | setRightPop(true) | **BRPOP** item từ Redis List |

Mỗi bên phải dùng **đúng cùng Redis instance/database/queue key và wire format**, không chỉ có class names tương tự.

### 10.2. ServiceActivator của worker

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Service;

@Service
public class ThumbnailJobConsumer {

    private final ObjectMapper objectMapper;
    private final ThumbnailBusinessService businessService;

    public ThumbnailJobConsumer(
            ObjectMapper objectMapper,
            ThumbnailBusinessService businessService) {
        this.objectMapper = objectMapper;
        this.businessService = businessService;
    }

    @ServiceActivator(inputChannel = "thumbnailJobsInput")
    public void handle(String json) throws JsonProcessingException {
        ThumbnailRequested job =
            objectMapper.readValue(json, ThumbnailRequested.class);

        if (!"THUMBNAIL_REQUESTED".equals(job.eventType())
                || job.schemaVersion() != 1
                || job.eventId() == null
                || job.eventId().isBlank()) {
            throw new IllegalArgumentException(
                "Unsupported or invalid thumbnail job");
        }

        // Implementation must be idempotent and validate tenant/objectKey.
        businessService.process(job);
    }
}
~~~

~~~java
public interface ThumbnailBusinessService {
    void process(ThumbnailRequested job);
}
~~~

**Chú ý:** Exception từ business handler **không tự làm BRPOP rollback**. Khi Redis queue inbound đã pop item mà process chết hoặc handler lỗi, worker không có Redis List native ACK để yêu cầu server requeue. Muốn xử lý retry bền vững, phải thiết kế thêm processing state hoặc nguồn job có thể rebuild.

### 10.3. Vì sao code worker không tự khẳng định at-least-once?

Trong ví dụ đơn giản, việc pop/xử lý/commit không nằm trong một transaction Redis–database nguyên tử:

~~~text
Redis List BRPOP -> Spring Message -> JSON parse -> DB/object storage commit
                    |
                    +-- crash tại đây: item có thể đã mất
~~~

Vì vậy mẫu code ghép producer–consumer chứng minh **transport interop**, không chứng minh **durable delivery** sau mọi sự cố.

## 11. Serializer và extractPayload phải tương thích hai bên

Đây là lỗi phổ biến khi worker là ứng dụng Node.js/Python hoặc Java service thuộc team khác.

### 11.1. Ma trận wire format

| Outbound payload | Serializer | Redis List bytes | Inbound mong đợi |
| --- | --- | --- | --- |
| String JSON | **StringRedisSerializer** | UTF-8 JSON | StringRedisSerializer hoặc UTF-8 bytes → JSON |
| Java POJO | JdkSerializationRedisSerializer | Java native serialization | Compatible JDK deserializer, không khuyến nghị cross-language |
| DTO được Jackson serialize thành String | StringRedisSerializer | UTF-8 JSON | String/JSON DTO |
| byte[] | Byte-array serializer phù hợp | Raw bytes | byte[] cùng contract |
| Toàn bộ Spring Message | Serializer hỗ trợ Message object | Container object (có thể là JDK bytes) | Deserializer tin cậy + expect-message phù hợp |

Với queue dùng chung giữa services, **JSON/String UTF-8** thường dễ duy trì hơn native Java serialization. Đặt schemaVersion/eventType trong JSON envelope để nâng cấp độc lập.

### 11.2. Cấu hình cả hai phía

~~~text
Producer:
  extractPayload=true
  serializer=StringRedisSerializer
  Spring payload=String JSON
  leftPush=true

Consumer:
  serializer=StringRedisSerializer
  expectMessage=false
  rightPop=true
  service activator nhận String
~~~

**expectMessage** là cấu hình của **inbound**, khác extractPayload ở outbound. Nếu producer gửi **entire Spring Message** nhưng consumer kỳ vọng String payload, có thể lỗi deserialization/shape. Không dùng expectMessage=true để “bắt thêm headers” khi producer chỉ serialize JSON String.

### 11.3. Headers không tồn tại độc lập trong Redis List

Redis List value là một chuỗi bytes/item, không có protocol headers như AMQP basic properties hay Kafka record headers. Nếu messageId, traceparent, causationId hoặc tenantRef cần qua ranh giới, **đưa chúng vào JSON envelope** theo schema và kiểm tra trusted fields.

### 11.4. JSON double-encoding

Nếu một String vốn chứa JSON được đưa qua JSON serializer dành cho String, bytes có thể trở thành một **JSON string literal** với escape/quotes. Worker parse thành String thay vì object. Kiểm tra raw Redis payload bằng Redis CLI hoặc test assertion bytes; đừng chỉ test ObjectMapper ở producer.

### 11.5. Default serializer không thay thế integration contract

Lựa chọn serializer mặc định có thể thay theo type của payload hoặc adapter/framework version. Việc publisher chạy được trên một máy không chứng minh Python worker nhận đúng UTF-8. Cần **contract test producer–consumer** với cùng schema và raw bytes.

### 11.6. Dữ liệu không tin cậy

Không bật unsafe polymorphic deserialization hay JDK native deserialization cho values mà nhiều producers được quyền ghi. JSON parse cũng cần giới hạn **payload bytes, nesting depth, field types, string lengths** và tenant authorization ở worker.

## 12. Dynamic queue routing: queue-expression

Một hệ thống có thể dùng nhiều Redis Lists cho các loại công việc:

~~~text
catalog:{thumbnail}:high
catalog:{thumbnail}:normal
catalog:{thumbnail}:low
~~~

**RedisQueueOutboundChannelAdapter** nhận queueName cố định hoặc **Expression**. Queue-expression được đánh giá theo **incoming Spring Message** (root). Điều này giúp định tuyến theo header đã kiểm soát:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.redis.outbound.RedisQueueOutboundChannelAdapter;

@Configuration
public class ThumbnailPriorityRoutingConfig {

    @Bean
    @ServiceActivator(inputChannel = "thumbnailPriorityOutbound")
    public RedisQueueOutboundChannelAdapter thumbnailPriorityQueueHandler(
            RedisConnectionFactory factory) {

        var expression = new SpelExpressionParser()
            .parseExpression("headers['redisQueue']");

        var adapter = new RedisQueueOutboundChannelAdapter(
            expression, factory);
        adapter.setSerializer(new StringRedisSerializer());
        adapter.setExtractPayload(true);
        adapter.setLeftPush(true);
        return adapter;
    }
}
~~~

**Không dùng đồng thời cấu hình cố định và dynamic queue cho một adapter.** Một queue cố định nên dùng constructor String; SpEL trong ví dụ được tạo từ **hằng biểu thức do developer kiểm soát**, không phải từ raw user input.

### 12.1. Chọn queue từ enum/allowlist

~~~java
public enum ThumbnailQueueTier {
    HIGH("catalog:{thumbnail}:high"),
    NORMAL("catalog:{thumbnail}:normal"),
    LOW("catalog:{thumbnail}:low");

    private final String redisKey;

    ThumbnailQueueTier(String redisKey) {
        this.redisKey = redisKey;
    }

    public String redisKey() {
        return redisKey;
    }
}
~~~

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class PriorityThumbnailPublisher {

    private final MessageChannel thumbnailPriorityOutbound;

    public PriorityThumbnailPublisher(
            @Qualifier("thumbnailPriorityOutbound")
            MessageChannel thumbnailPriorityOutbound) {
        this.thumbnailPriorityOutbound = thumbnailPriorityOutbound;
    }

    public void publish(ThumbnailQueueTier tier, String validatedJson) {
        if (tier == null || validatedJson == null
                || validatedJson.isBlank()) {
            throw new IllegalArgumentException("Invalid queue job");
        }

        boolean sent = thumbnailPriorityOutbound.send(
            MessageBuilder.withPayload(validatedJson)
                .setHeader("redisQueue", tier.redisKey())
                .build());
        if (!sent) {
            throw new IllegalStateException(
                "Cannot dispatch to outbound queue channel");
        }
    }
}
~~~

**Ràng buộc:** Với dynamic queue, tên key phải được set từ **allowlist**. Không nhận raw Redis key từ HTTP header/form/tenant input rồi cho expression tạo hoặc ghi vào một namespace tùy ý. Redis ACL cũng phải giới hạn key patterns.

### 12.2. Nhiều queues chưa phải priority queue toàn cục

Ba Redis Lists theo tier không tự tạo một **global priority queue**. Worker phải thiết kế cách chọn queue, fairness, starvation prevention, concurrency và backlog metrics; Redis BRPOP với nhiều keys có thứ tự ưu tiên phụ thuộc thứ tự keys trong command, không tự giải quyết QoS cho mọi workload.

### 12.3. Dynamic queue vs Spring Integration router

Với số lượng queues nhỏ, có thể dùng **Spring Integration router** để gửi tới nhiều outbound flows có queue cố định. Cách này dễ quan sát và ACL hơn một SpEL expression quá rộng. Dynamic queue phù hợp khi producer thật sự cần chọn key theo contract đã kiểm soát.

## 13. Enqueue thành công khác business completion

Redis List phù hợp làm backlog khi worker offline, nhưng cần phân biệt **những mốc trạng thái**:

~~~mermaid
flowchart LR
    A["DB metadata committed"] --> B["LPUSH command success"]
    B --> C["Job ở Redis List"]
    C --> D["Worker BRPOP item"]
    D --> E["Validate + process"]
    E --> F["Business DB/object storage commit"]
~~~

| Mốc | Đã bảo đảm điều gì? | Chưa bảo đảm điều gì? |
| --- | --- | --- |
| Spring MessageChannel.send accepted | Message đi vào đường gửi theo channel contract | Redis đã ghi hay chưa nếu async |
| LPUSH trả thành công | Redis xử lý thao tác push | Redis đã fsync/replicate đủ policy, worker đã nhận |
| LLEN tăng | List đang có item | Hành động thumbnail sẽ thành công |
| BRPOP trả item | Worker đã lấy item khỏi List | Business transaction đã commit |
| Business commit success | Side effect durable theo hệ thống đích | Item không bao giờ bị retry/duplicate |

**Không dùng Redis List length làm thước đo số thumbnail đã hoàn tất.** Nó chỉ đo items còn trong List tại thời điểm query.

### 13.1. Producer gửi nhưng worker offline

Một ưu điểm của List so với Pub/Sub: item **chưa bị pop** có thể vẫn nằm trong Redis List và được nhận sau khi ImageWorker khởi động lại, **miễn là Redis key/dữ liệu còn và có cấu hình persistence/TTL/eviction phù hợp**.

### 13.2. Worker pop rồi crash

~~~text
T0: CatalogService LPUSH job-1001
T1: ImageWorker BRPOP job-1001   -> item rời pending List
T2: ImageWorker crash trước DB commit
T3: Redis pending List không còn job-1001
~~~

**Redis List direct POP không tự redeliver**. Outbound adapter đã làm đúng chức năng ghi, nhưng hệ thống end-to-end vẫn mất một job nếu không có reconciliation/processing store.

### 13.3. Outbound adapter không quyết định ACK

RedisQueueOutboundChannelAdapter không quản lý consumer ACK/requeue. Đổi leftPush=true thành false chỉ đổi chiều ghi; **không làm Redis ghi pending state hoặc lưu delivery-count**.

## 14. Các khoảng lỗi ở phía producer

### 14.1. Lỗi trước khi LPUSH

Có thể do:

- DTO invalid hoặc ObjectMapper serialization failure.
- Spring Integration filter/router bỏ message.
- MessageChannel không có subscriber.
- Redis queueExpression trả tên key sai/null.
- RedisSerializer không xử lý kiểu payload.

Khi đó Redis chưa nhận request push theo đường lỗi rõ. Cần phân loại trước network retry; JSON/schema lỗi thường là **non-retryable** cho tới khi sửa.

### 14.2. Redis command trả lỗi

| Lỗi | Dấu hiệu | Hướng điều tra |
| --- | --- | --- |
| Connection failure | Không kết nối Redis | Redis address, TLS, DNS, network, failover |
| ACL NOPERM | Không có quyền LPUSH/RPUSH key | Redis user, command/key patterns |
| WRONGTYPE | Key tồn tại nhưng không phải List | Namespace ownership, migration |
| OOM/maxmemory | Redis từ chối ghi hoặc eviction policy tác động | Capacity, memory settings, persistence |
| Timeout | Chờ response quá lâu | Redis latency/network, unknown outcome |
| Serializer exception | Không encode payload | Schema/serializer config |
| Queue expression failure | Dynamic key sai | Header/SpEL/routing validation |

### 14.3. Unknown outcome sau LPUSH

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant R as Redis
    P->>R: LPUSH jobId=evt-thumb-1001
    R->>R: Push thành công
    R--xP: Connection drop before reply
    Note over P,R: Publisher không biết command đã chạy
    P->>R: Retry LPUSH same eventId
    R->>R: List có thể chứa 2 items
~~~

Redis List không deduplicate theo eventId. **Giữ cùng eventId cho retry**, có unique business job state/idempotent handler, và theo dõi duplicate metrics; không tự tạo một UUID mới rồi kết luận là công việc độc lập.

### 14.4. RetryTemplate không bền vững qua restart

Một RetryTemplate/RequestHandlerRetryAdvice có thể retry các lỗi transient **trong JVM đang chạy**, nhưng nếu process chết giữa attempts, job chưa được phát lại trừ khi nguồn event được lưu bền.

Nếu cần retry sau restart, dùng **database outbox, persistent task table hoặc broker/stream durable**. Retry không được áp dụng vô hạn cho WRONGTYPE, serializer mismatch, invalid routing key.

### 14.5. ErrorChannel không phải Redis dead-letter queue

ErrorChannel của Spring Integration nhận ErrorMessage theo flow/concurrency configuration; nó **không tự ghi một dead List**, không tự khôi phục event bị mất sau process crash, và không biết worker downstream đã commit hay chưa. Thiết kế error handler bền vững nếu job không được phép mất.

### 14.6. Đừng tự LPUSH lại trong mọi catch

Một vòng:

~~~java
try {
    publisher.enqueueNewImage(tenant, product, version, key);
}
catch (RuntimeException e) {
    // Không làm thế này vô điều kiện với eventId mới:
    publisher.enqueueNewImage(tenant, product, version, key);
}
~~~

có thể tạo duplicate, biến transient timeout thành nhiều jobs và bỏ mất thông tin attempt. **Đặt retry ở một lớp giữ nguyên eventId**, với max attempts, backoff và durable state khi cần.

## 15. Database commit và LPUSH: transactional outbox

Giả sử CatalogService lưu metadata ảnh trong database và thêm thumbnail job vào Redis:

### 15.1. LPUSH trước DB commit

~~~text
BEGIN DB TRANSACTION
  INSERT image_metadata(productId=P-1001, version=5)
  LPUSH thumbnail job
ROLLBACK DB
~~~

Worker có thể BRPOP trước khi metadata commit, tra không thấy dữ liệu hoặc xử lý job mà DB đã rollback. Redis push không tự rollback theo JDBC transaction.

### 15.2. LPUSH sau DB commit

~~~text
BEGIN DB TRANSACTION
  INSERT image_metadata(...)
COMMIT DB
  -> LPUSH job
~~~

Trình tự này tránh phần lớn trường hợp worker nhìn thấy dữ liệu chưa commit. Nhưng còn cửa sổ:

~~~text
DB commit success
JVM crash before LPUSH
Job metadata ở DB, không có item Redis
~~~

Nếu muốn bảo đảm thumbnail cuối cùng sẽ được tạo, cần nguồn job có thể **rebuild/reconcile**.

### 15.3. Transactional outbox

Một mô hình:

~~~mermaid
flowchart LR
    API["HTTP/SFTP upload"] --> DB[("DB transaction:<br/>image metadata + outbox")]
    DB --> PUB["Outbox publisher<br/>durable retry"]
    PUB --> AD["Redis queue outbound"]
    AD --> LIST[("Redis List pending")]
    LIST --> WORK["ImageWorker"]
    WORK --> DB
    DB --> REC["Periodic reconcile"]
    REC --> PUB
~~~

**Trong cùng transaction DB**, ghi image metadata và outbox record:

~~~sql
BEGIN;

INSERT INTO image_metadata (
    product_id, image_version, object_key, status
)
VALUES ('P-1001', 5, 'tenant-a/products/P-1001/v5/original.jpg',
        'NEEDS_THUMBNAIL');

INSERT INTO outbox_events (
    event_id, event_type, payload_json, status
)
VALUES ('evt-thumb-1001', 'THUMBNAIL_REQUESTED',
        '{"eventId":"evt-thumb-1001","schemaVersion":1}',
        'PENDING');

COMMIT;
~~~

**Đây là SQL minh họa**, không phải schema hoàn chỉnh (cần PK, unique indexes, timestamps, tenant, transactional isolation). Worker outbox đọc các sự kiện PENDING rồi gửi qua Redis outbound adapter; chỉ đánh dấu DISPATCHED sau mốc Redis command success phù hợp.

### 15.4. Outbox không loại bỏ duplicate

Nếu Redis LPUSH thành công nhưng outbox publisher crash trước khi mark DISPATCHED, publisher sẽ gửi lại sau restart. **Outbox thường chọn không làm mất ý định gửi, chấp nhận duplicate delivery**, nên ImageWorker phải idempotent theo eventId/productVersion.

### 15.5. Outbox chưa giải quyết mất job sau BRPOP

Một outbox đã được đánh dấu DISPATCHED không tự biết worker đã BRPOP rồi crash. Muốn bảo đảm thumbnail được tạo cuối cùng, cần:

- Business status **NEEDS_THUMBNAIL / PROCESSING / DONE** ở DB.
- **Periodic reconciliation** enqueue lại jobs chưa DONE sau timeout.
- Idempotent worker để tránh lặp side effect.
- Hoặc thay direct POP bằng **reliable claim/ACK protocol**, Redis Streams/AMQP/JMS phù hợp.

### 15.6. Không gọi @Transactional là distributed transaction

JDBC transaction, Redis LPUSH, object storage write và HTTP provider call không mặc nhiên thuộc một transaction nguyên tử chỉ vì cùng chạy trong method có annotation @Transactional.

## 16. End-to-end idempotency ở ImageWorker

Một job có thể xuất hiện nhiều lần khi:

- Producer retry LPUSH do timeout/UNKNOWN outcome.
- Outbox replay sau crash.
- Operator manual replay.
- Scheduler đối soát DB NEEDS_THUMBNAIL.
- Reliable queue reclaimer requeue sau lease timeout.

**eventId chỉ hữu ích khi handler có logic thật.** Không chỉ thêm trường eventId vào JSON rồi tin rằng Redis deduplicate.

### 16.1. Unique business identity

Ví dụ bảng durable:

~~~sql
CREATE TABLE thumbnail_jobs (
    event_id       VARCHAR(80) PRIMARY KEY,
    product_id     VARCHAR(80) NOT NULL,
    image_version  BIGINT NOT NULL,
    status         VARCHAR(20) NOT NULL,
    attempt_count  INTEGER NOT NULL,
    updated_at     TIMESTAMP NOT NULL,
    UNIQUE (product_id, image_version)
);
~~~

Ứng dụng nên tạo business job record bằng **unique constraint** hoặc update có điều kiện:

- Nếu cùng eventId đã DONE → skip side effect.
- Nếu cùng productId/imageVersion đang PROCESSING → kiểm tra lease/owner.
- Nếu job version cũ đã bị thay bởi version mới → bỏ job cũ theo policy.
- Nếu client retry cùng business request → giữ identity.

### 16.2. Output deterministic

Thumbnail output key có thể đặt theo **productId/imageVersion**. Nếu worker thực hiện lại cùng job, nó ghi cùng một artifact, tránh tạo ra nhiều thumbnail không thể theo dõi. Tuy nhiên ghi đè trong object storage cũng cần **version/conditional writes**, vì worker cũ có thể kết thúc sau worker mới.

### 16.3. Side effect external có trạng thái UNKNOWN

Nếu upload thumbnail đến object storage thành công nhưng connection timeout, retry có thể lặp write. Hãy chọn deterministic key, kiểm tra ETag/version/object existence và lưu trạng thái DONE có cơ chế đối soát. Không dùng “timeout = chắc chắn chưa ghi”.

### 16.4. Cần giới hạn retention của idempotency state

Nếu Redis backlog/outbox/reconciliation có thể replay sau bảy ngày mà bảng processed eventId bị xóa sau 24 giờ, một replay cũ có thể bị coi là job mới. Retention của business dedup phải xét **khoảng thời gian duplicate có thể xuất hiện**.

## 17. Reliable List queue: BLMOVE và processing List

Nếu mục tiêu không chỉ là best-effort thumbnail mà cần khả năng phục hồi khi worker crash, Redis List direct POP cần thêm một giao thức riêng.

~~~mermaid
flowchart LR
    OUT["Redis queue outbound<br/>LPUSH"] --> READY[("ready List")]
    READY -->|"BLMOVE RIGHT LEFT"| PROCESS[("processing List")]
    PROCESS --> H["Business worker"]
    H --> DB[("Durable commit")]
    DB -->|"LREM exact item"| PROCESS
    PROCESS -. "Reclaimer on expiry" .-> READY
~~~

### 17.1. BLMOVE claim

Thay vì BRPOP xóa item khỏi Redis, consumer dùng một thao tác **move nguyên tử**:

~~~text
BLMOVE catalog:{thumbnail}:ready
        catalog:{thumbnail}:processing
        RIGHT LEFT 0
~~~

Lệnh này lấy một phần tử từ bên RIGHT của ready List và đặt vào bên LEFT processing List trong Redis. Nếu worker chết trước khi ACK, **item có thể còn ở processing** cho reclaimer theo policy.

**Cần lưu ý:** Đây là một **protocol tự xây ở tầng ứng dụng**, không phải hành vi mặc định của RedisQueueMessageDrivenEndpoint. Outbound adapter vẫn chỉ **LPUSH** vào ready key; bạn phải tự triển khai consumer claim, lease, ACK và recovery.

### 17.2. ACK bằng LREM đúng item

Sau khi business commit, consumer có thể gọi **LREM processing 1 value** để xóa đúng item đã claim. Nhưng nếu processing List có **hai serialized values giống hệt nhau**, LREM theo value không phân biệt owner. Dùng jobId duy nhất/representation đủ phân biệt, kiểm soát ownership hoặc một cấu trúc trạng thái có khóa để không ACK nhầm.

### 17.3. Cửa sổ duplicate sau business commit

~~~text
BLMOVE ready -> processing
Business DB commit success
Worker crash before LREM processing
Reclaimer moves item back -> delivered again
~~~

Idempotency là bắt buộc. Một reliable queue thường chọn **at-least-once delivery** với duplicate có kiểm soát thay vì nguy cơ mất job khi direct POP.

### 17.4. Lease, reclaimer và fencing

Processing List một mình **không biết job nào đã timeout**. Cần state về:

- eventId, owner/workerId.
- claim timestamp, leaseUntil, attempts.
- status PROCESSING/DONE/FAILED.
- nextRetryAt và lastErrorCategory.
- fencing token/version nếu worker cũ có thể hoàn tất sau lease expiry.

Reclaimer phải xác định những jobs thực sự đủ điều kiện claim lại, không requeue tất cả processing items vô điều kiện.

### 17.5. Redis Cluster hash slots

Với BLMOVE gồm **source + destination**, Redis Cluster yêu cầu các keys trong lệnh đa key thuộc **cùng hash slot**. Hash tag:

~~~text
catalog:{thumbnail}:ready
catalog:{thumbnail}:processing
catalog:{thumbnail}:dead
~~~

giúp keys thuộc cùng slot. Nếu dùng hai keys khác slots, có thể gặp **CROSSSLOT**; không tự tắt kiểm tra hay giả định Spring Data Redis client giải quyết transaction liên shard.

### 17.6. Khi nào nên chọn Redis Streams hoặc broker khác?

Nếu hệ thống đã cần **ready + processing + ACK + lease + retry count + dead list + reclaimer + metrics + audit**, đánh giá Redis Streams (consumer group/PEL/XACK) hoặc RabbitMQ/JMS/Kafka theo semantics workload. Đừng tự xây một message broker đầy đủ chỉ vì Redis List đã có sẵn.

## 18. Concurrency và MessageChannel phía outbound

### 18.1. DirectChannel

~~~text
Caller thread
  -> thumbnailJobsOutbound.send()
  -> RedisQueueOutboundChannelAdapter
  -> Redis LPUSH
  -> Return hoặc exception
~~~

**DirectChannel** phù hợp khi muốn biết kết quả gọi handler đồng bộ và có lượng thông điệp vừa phải. Nếu Redis mất kết nối, HTTP request thread hoặc outbox worker thread có thể bị giữ bởi timeout. **Thành công của send chỉ xác nhận ranh giới hiện tại**, không chứng minh ImageWorker đã tạo thumbnail.

### 18.2. ExecutorChannel

~~~text
Caller -> ExecutorChannel -> executor memory queue
                          -> worker thread -> Redis LPUSH
~~~

Khi dùng ExecutorChannel:

- Caller có thể return **trước khi Redis LPUSH thực sự chạy**.
- Exception push xảy ra trong executor thread, cần error handling/observability riêng.
- Khi application crash, tasks trong executor memory queue có thể bị mất.
- Executor queue không bounded có thể gây OutOfMemoryError khi Redis chậm.
- Giới hạn executor threads, capacity, backpressure và rejection policy.

Không dùng ExecutorChannel như cách biến một Redis push thành durable enqueue; muốn độ bền, dùng **outbox/persistent task store**.

### 18.3. QueueChannel nội bộ

Một flow khác có thể:

~~~text
HTTP inbound -> QueueChannel -> Spring Integration Poller
                            -> Redis queue outbound -> Redis List
~~~

Đây là **Spring Integration QueueChannel**, khác **Redis List**. Nếu QueueChannel mặc định giữ items trong memory, nó có thể mất items khi JVM crash dù Redis chưa thấy LPUSH. Một persistent MessageStore chỉ bảo vệ các mốc được thiết kế, không tạo consumer ACK tự động ở Redis.

### 18.4. PublishSubscribeChannel và duplicate

Nếu một PublishSubscribeChannel nội bộ phát cùng job tới **hai Redis queue outbound handlers trỏ cùng Redis key**, queue có thể nhận **hai LPUSH** cho một business event. Kiểm tra số handlers/subscribers và topic/queue names trước khi quy mọi duplicate cho Redis failover.

### 18.5. Hai producer cùng ghi một queue

Redis xử lý mỗi LPUSH atomically; nếu hai CatalogService replicas gửi đồng thời, thứ tự giữa hai requests được xác định bởi thứ tự Redis xử lý, **không bảo đảm thứ tự tạo event ở hai databases/threads**. Khi cần business ordering theo productId, dùng sequence/version và consumer contract thay vì dựa hoàn toàn vào List FIFO.

### 18.6. Nhiều workers cạnh tranh nhận item

Với Redis List direct POP:

~~~text
Redis List -> Worker A BRPOP
           -> Worker B BRPOP
           -> Worker C BRPOP
~~~

Mỗi List item được pop bởi một consumer tại thời điểm thao tác, **không broadcast tới tất cả workers**. Nhưng Redis có thể chứa duplicate payloads từ producer retry; mỗi item vẫn được worker khác nhau xử lý, nên cần idempotency.

### 18.7. FIFO là thứ tự nhận, không phải completion

~~~text
Job A popped 10:00:00; processing 10 s
Job B popped 10:00:01; processing 1 s

Job B DONE trước Job A.
~~~

Nếu nghiệp vụ bắt buộc A hoàn tất trước B, giới hạn concurrency theo khóa domain, dùng business sequence hoặc một mô hình actor/partition phù hợp. Không chỉ chỉnh leftPush/rightPop.

## 19. Redis memory, TTL và backlog capacity

Redis List thường được lưu trong Redis memory (và có persistence/replication theo cấu hình), nên producer không được enqueue vô hạn khi consumer chậm.

### 19.1. Backlog tăng

~~~text
Producer enqueue rate = 500 jobs/second
Consumer success rate = 100 jobs/second

Backlog growth ≈ 400 jobs/second
                = 24,000 jobs/minute
~~~

Đây chỉ là ví dụ số học ở steady state; thực tế còn requeue, burst traffic, failure, producer downtime và jobs processing. Hệ thống phải monitor growth rate, queue age, Redis memory và downstream throughput.

### 19.2. List không tự có max queue depth

Redis List không áp giới hạn số item theo từng key giống một số message brokers có queue policy. Nếu muốn giới hạn hoặc rate-control:

- Throttling/reject/slow producers trước LPUSH.
- Capacity-based admission control dùng Redis/DB state, nhưng tránh race check-then-push.
- Batch/coalesce jobs cùng productId/version nếu business cho phép.
- Dùng bounded outbox workers và downstream concurrency.
- Chọn Redis Streams/broker có chính sách retention/backpressure phù hợp nếu cần.

Một check **LLEN trước rồi LPUSH** không tạo hard capacity guarantee khi nhiều publishers chạy song song. Muốn ngưỡng nguyên tử, phải dùng script/command strategy thích hợp và test theo Redis topology.

### 19.3. Không cắt queue bằng LTRIM tùy tiện

~~~text
LPUSH newJob
LTRIM key 0 999
~~~

Lệnh LTRIM có thể loại các jobs cũ mà chưa worker nào xử lý. Đây là **data loss**, không phải retry policy. Chỉ dùng loại bỏ theo capacity nếu business thực sự chấp nhận mất những công việc đó và đã ghi trong SLA.

### 19.4. TTL và key eviction

Nếu một thành phần đặt **EXPIRE** cho Redis List key, key có thể biến mất khi hết TTL cùng với các items chưa pop. Redis **maxmemory eviction** cũng có thể xóa key theo eviction policy hoặc từ chối ghi; cần hiểu production Redis configuration.

**Đừng mặc định LPUSH khôi phục một TTL đã bị đặt**. Việc LPUSH thêm vào List thường không biến nó thành persistent key vô hạn nếu TTL đang còn theo semantics Redis. Test TTL ownership và cân nhắc key namespace riêng.

### 19.5. Persistence không tạo consumer ACK

Redis RDB/AOF/replication có thể giúp phục hồi Redis state sau một số lỗi, nhưng **không khôi phục item đã BRPOP thành công và worker chưa commit**. Độ bền của Redis state và độ tin cậy **end-to-end delivery** là hai tầng khác nhau.

### 19.6. Capacity planning

Nếu mỗi JSON job khoảng 600 bytes, một triệu jobs là khoảng 600 MB **chỉ tính raw payload**, chưa tính List/allocator metadata, Redis replication/AOF, TTL/index, client buffers và overhead khác. Không dùng công thức raw bytes làm dự báo memory production duy nhất; benchmark với Redis thực, payload thật và peak backlog.

## 20. Bảo mật: Redis ACL, tenant và dữ liệu công việc

### 20.1. Redis ACL và key namespace

Phân tách tối thiểu:

| Actor | Quyền cần thiết theo chức năng |
| --- | --- |
| Producer CatalogService | LPUSH/RPUSH tới **ready List** được phép |
| Consumer ImageWorker | BRPOP/BLPOP từ ready key, theo recovery policy |
| Reliable-queue worker | BLMOVE, LREM và quyền trên processing key |
| Reclaimer | Đọc/quản lý processing/lease/attempt state |
| Operator | Xem backlog, replay failed jobs có audit |

ACL cụ thể phụ thuộc Redis version/commands/key patterns. Không cấp quyền **FLUSHALL, FLUSHDB hoặc DEL tùy ý** cho worker chỉ để tránh lỗi NOPERM. Hệ production cần TLS, secret rotation, network policies và least privilege.

### 20.2. Tenant boundary

Một JSON job có **tenantRef** không làm nó trở thành request đã được xác thực. ImageWorker phải xác minh productId thuộc tenant được phép, objectKey nằm trong allowlisted prefix/bucket, và nghiệp vụ có quyền thực hiện side effect. Không tin tưởng job chỉ vì Redis List key có tên chuẩn.

### 20.3. Dynamic queue expression phải có allowlist

QueueExpression nhận Redis key theo Spring Message runtime. Nếu header redisQueue lấy trực tiếp từ HTTP request, attacker có thể khiến ứng dụng có Redis credentials ghi tới keys ngoài phạm vi. Chọn queue từ enum/config được kiểm soát và áp ACL.

### 20.4. Payload poisoning và deserialization

Không deserialize Java native objects từ một shared Redis List khi producer khác hoặc nhiều tenants có thể ghi vào đó. Với JSON cần giới hạn:

- Byte size, JSON nesting depth và field count.
- Allowlisted eventType/schemaVersion.
- Strings/product IDs/object paths đúng format.
- Không tùy tiện bật Jackson polymorphic default typing.
- Có policy với malformed/unsupported payload.

### 20.5. Object storage references

ImageWorker không được chuyển objectKey thành filesystem path hoặc shell command không được validate. Cần allowlisted bucket/prefix, file size/media type limits, decode image limits và chống path traversal/tenant cross-access. Không đặt signed URLs còn hiệu lực hoặc access tokens trong dead lists/logs nếu có thể tránh.

### 20.6. Retry/dead storage chứa dữ liệu nhạy cảm

Một dead List có thể lưu raw payload và lastError lâu hơn ready List. Vì vậy cần retention, ACL, encryption, PII handling, audit replay và quyền truy cập tối thiểu cho operators.

## 21. Monitoring: phân biệt enqueued, popped và completed

| Tín hiệu | Ý nghĩa | Không được suy ra |
| --- | --- | --- |
| Queue outbound attempts | Messages đi vào handler | Redis LPUSH đã thành công |
| Redis push success count | Redis trả thành công cho LPUSH/RPUSH | Worker đã xử lý |
| Redis command errors/timeouts | Publisher gặp lỗi transport/serializer | Mọi timeout chắc chắn chưa push |
| **LLEN ready** | Items còn đang chờ pop | Business backlog tổng = ready |
| **LLEN processing** | Items đã claim chưa ACK (nếu tự xây reliable queue) | Tất cả đang chạy bình thường |
| **LLEN dead** | Jobs cách ly (nếu tự xây dead List) | Jobs tự được replay |
| Consumer pop/claim rate | Tốc độ nhận công việc | Business success |
| Business completed rate | Tốc độ commit side effect | Queue cleanup luôn thành công |
| Oldest job age | Độ trễ jobs chưa xử lý | Chỉ tính bằng LLEN |
| Duplicate skipped | Idempotency chặn lặp | Producer không enqueue trùng |
| Reclaimer count | Jobs được nhận lại | Worker cũ chắc chắn không làm side effect |

### 21.1. Metric names minh họa

~~~text
thumbnail_redis_queue_push_attempt_total
thumbnail_redis_queue_push_success_total
thumbnail_redis_queue_push_error_total{reason="CONNECTION_TIMEOUT"}
thumbnail_redis_queue_ready_length
thumbnail_redis_queue_processing_length
thumbnail_redis_queue_dead_length
thumbnail_redis_queue_oldest_age_seconds
thumbnail_worker_pop_total
thumbnail_worker_completed_total
thumbnail_worker_retry_total{reason="OBJECT_STORAGE_TIMEOUT"}
thumbnail_worker_duplicate_skipped_total
thumbnail_worker_reclaimed_total
thumbnail_worker_processing_duration_seconds
~~~

Đây là **tên metric do ứng dụng tự instrument**, không phải Spring Integration mặc định xuất toàn bộ. Labels phải bounded: không gắn eventId, productId, raw objectKey hoặc dynamic queue key chưa kiểm soát thành metrics labels có cardinality vô hạn.

### 21.2. LLEN=0 chưa phải DONE=100%

~~~text
Ready LLEN = 0
Executor queued tasks = 100
Business DONE = 0
~~~

Với queue inbound direct POP, Redis List có thể rỗng vì worker đã pop rồi giữ items trong memory, không có durable ACK. Khi JVM crash, tasks có thể mất. Dashboard cần business status, processing/reconciliation và end-to-end success, không chỉ queue length.

### 21.3. Monitoring Redis errors

Theo dõi Redis command latency, connection pool exhaustion, ACL/WRONGTYPE, failover/reconnect, memory/eviction, AOF/RDB health, publish/enqueue retry và application-level error categories.

### 21.4. Cảnh báo theo SLA

Cảnh báo nếu:

- LLEN ready tăng liên tục quá ngưỡng nhiều phút.
- Oldest unprocessed job vượt SLA.
- Queue outbound error rate hoặc Redis response latency tăng.
- Dead jobs/retry exhausted tăng bất thường.
- Có nhiều processing jobs quá hạn lease.
- Business success gần 0 dù pop/claim rate cao.
- Redis memory gần maxmemory hoặc eviction đang ảnh hưởng queues.

### 21.5. Structured logging

~~~text
flow=thumbnailQueueOutbound
queueAlias=catalog-thumbnail-pending
eventId=evt-thumb-1001
eventType=THUMBNAIL_REQUESTED
schemaVersion=1
enqueueAttempt=2
enqueueStatus=REDIS_COMMAND_SUCCESS
durationMs=6
~~~

Không log **BUSINESS_DONE** ở producer sau LPUSH; trạng thái đó do business worker/reconciliation xác nhận.

## 22. Lifecycle: startup, shutdown, reconnect và failover

### 22.1. Outbound handler khởi tạo lúc nào?

**RedisQueueOutboundChannelAdapter** là MessageHandler do Spring quản lý. Khi ApplicationContext khởi động, flow/consumer endpoint được đăng ký với input channel. Handler không tự poll Redis List trong nền; nó chỉ push khi nhận Spring Message.

~~~mermaid
flowchart TD
    START["Spring context start"] --> CONN["RedisConnectionFactory initialized"]
    CONN --> FLOW["Outbound flow active"]
    FLOW --> INPUT{"Message received?"}
    INPUT -->|"Có"| PUSH["Serialize + LPUSH/RPUSH"]
    PUSH --> FLOW
    INPUT -->|"Không"| FLOW
    FLOW -->|"Stop"| END["Stop new dispatch, drain/reconcile"]
~~~

### 22.2. Startup order

Nếu HTTP/SFTP source bắt đầu gửi trước khi Redis sẵn sàng, outbound có thể lỗi hoặc làm upstream task thất bại tùy channel. Đừng coi **Bean đã tạo xong** là Redis health/readiness đạt. Test Redis connectivity + key permissions theo SLA.

Với nguồn có thể tạo lại job từ DB, publisher có thể retry sau. Với nguồn **không thể phát lại**, cần durable handoff/outbox **trước** thời điểm adapter push.

### 22.3. Graceful shutdown

Khi dừng producer:

1. Dừng nhận các lệnh nghiệp vụ mới theo policy.
2. Để các in-flight direct sends hoàn tất hoặc ghi intent bền vững.
3. Nếu dùng ExecutorChannel, không báo completed khi job còn trong executor memory queue.
4. Flush metrics/logs quan trọng theo thời hạn hữu hạn.
5. Để RedisConnectionFactory client được đóng theo lifecycle Spring.
6. Sau restart, reconciliation những outbox/jobs chưa đánh dấu DISPATCHED.

### 22.4. Redis failover

Redis Sentinel/Cluster failover có thể khiến:

- Connection broken trước push → retry.
- Push thành công nhưng response lost → result UNKNOWN, duplicate khi retry.
- Redis state bị rollback theo replication/persistence policy.
- Client phải reconnect/refresh topology.

Một Redis endpoint đã reconnect **không tự biết** các business jobs ở khoảng trước failover còn hay mất. Dựa vào durable event ledger và reconciliation để phát lại có kiểm soát.

### 22.5. Redis Cluster và queue expression

Mỗi Redis List key thuộc một hash slot. Một LPUSH đơn key không cần cùng slot với key khác, nhưng khi xây **BLMOVE processing/ready**, keys liên quan phải cùng slot. Dynamic queue expression cần namespace/hash-tag policy nếu cùng bộ queue sẽ tham gia multi-key atomic commands.

### 22.6. Không xóa queue để sửa lỗi consumer

RedisQueueMessageDrivenEndpoint có thể có các API quản trị List như getQueueSize/clearQueue theo phiên bản. **Không gọi clearQueue hoặc DEL trên production queue** khi worker bị lỗi nếu chưa có recovery/audit: có thể làm mất toàn bộ jobs chưa xử lý.

## 23. Kiểm thử end-to-end với Redis thật

Unit test ThumbnailJobPublisher chỉ chứng minh tạo JSON và gửi Spring Message; nó **không chứng minh** RedisQueueOutboundChannelAdapter đã dùng LPUSH đúng key, serializer đúng bytes và worker inbound đọc được. Cần integration test với Redis server riêng, chẳng hạn Testcontainers.

### 23.1. Ma trận kiểm thử

| Kịch bản | Thiết lập | Assertion |
| --- | --- | --- |
| **Happy path** | Producer gửi JSON String | Redis List chứa item tương ứng |
| **LPUSH direction** | Gửi A, B, C | LRANGE thấy [C,B,A] |
| **RPUSH direction** | leftPush=false | LRANGE thấy [A,B,C] |
| **FIFO with BRPOP** | LPUSH A/B/C, inbound rightPop=true | Pop A, B, C |
| **FIFO with BLPOP** | RPUSH A/B/C, inbound rightPop=false | Pop A, B, C |
| **LIFO mismatch** | LPUSH với BLPOP | Pop C, B, A; phát hiện sai contract |
| **Queue key đúng** | Producer/worker cùng key | Worker nhận được |
| **Sai key** | Producer ghi key khác worker | Không nhận, backlog key gốc còn |
| **String wire format** | Outbound StringRedisSerializer | Redis raw value là UTF-8 JSON |
| **Serializer mismatch** | Outbound JDK, inbound String | Phát hiện lỗi giải mã |
| **extractPayload=true** | Spring Message có headers | List chứa payload, không tự chứa headers |
| **extractPayload=false** | Custom compatible serializer | Whole Message roundtrip nếu contract hỗ trợ |
| **Dynamic queue** | queueExpression từ enum/header | Chỉ đẩy vào allowlisted key |
| **Dynamic queue missing** | Thiếu header redisQueue | Fail/route policy, không ghi nhầm |
| **Unauthorized queue** | External tries other namespace | Reject trước Redis; Redis ACL bổ sung |
| **WRONGTYPE** | Key chứa String | Redis báo lỗi; không tự xóa key |
| **Redis unavailable** | Stop test Redis | Outbound error/retry được quan sát |
| **Connection UNKNOWN** | Cắt mạng gần LPUSH | EventId dedup; không tuyên bố chắc chưa push |
| **Worker offline** | Producer LPUSH, worker chưa start | List giữ item nếu key/data còn |
| **Two competing workers** | Hai inbound BRPOP cùng List | Một Redis item bị pop bởi một worker |
| **Duplicate producer retry** | LPUSH hai JSON cùng eventId | Worker side effect không lặp |
| **Crash before outbound send** | Kill publisher trước LPUSH | Outbox/reconciliation phát lại job |
| **Crash after LPUSH before outbox update** | Kill publisher | Replay có thể duplicate, handler idempotent |
| **Crash after BRPOP before commit** | Kill worker | Item bị mất khỏi ready List nếu không recovery |
| **BLMOVE claim** | Move ready → processing | Item còn processing tới ACK |
| **Crash after BLMOVE before commit** | Kill worker | Reclaimer có thể phục hồi |
| **Crash after commit before LREM** | Kill worker | Duplicate delivery, idempotency bảo vệ |
| **Lease expiry race** | Worker A chạy chậm, B reclaim | Test fencing/ownership |
| **Redis Cluster cross-slot** | Ready/processing khác hash slot | Cross-slot error được phát hiện |
| **Poison JSON** | Malformed payload | Lỗi phân loại, không hot-loop retry vô hạn |
| **Large payload** | Item vượt size policy | Reject/rate limit, không OOM |
| **Backlog burst** | Producer nhanh hơn worker | LLEN tăng, có alert/capacity handling |
| **TTL expiry** | Key queue có TTL trong test | Job có thể mất; phát hiện cấu hình sai |
| **Redis ACL** | User thiếu quyền push | Error rõ, không bypass security |
| **Metrics** | Push + pop + business commit | Enqueued/popped/DONE là metrics khác nhau |

### 23.2. Test Redis CLI về chiều List

Chỉ trên Redis test riêng:

~~~bash
redis-cli LPUSH test:thumbnail:ready A
redis-cli LPUSH test:thumbnail:ready B
redis-cli LPUSH test:thumbnail:ready C
redis-cli LRANGE test:thumbnail:ready 0 -1
# Mong đợi: C B A
redis-cli RPOP test:thumbnail:ready
# Mong đợi: A
redis-cli RPOP test:thumbnail:ready
# Mong đợi: B
redis-cli RPOP test:thumbnail:ready
# Mong đợi: C
~~~

**Đừng dùng DEL/FLUSHDB cho queue production** để tạo trạng thái trống trước test. Một queue test nên nằm trong Redis instance/namespace được cô lập.

### 23.3. Test nhận payload bằng CountDownLatch

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class ThumbnailQueueCapture {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<String> payload =
        new AtomicReference<>();

    public void accept(String json) {
        payload.set(json);
        latch.countDown();
    }

    public String awaitJson() throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Redis queue item not received");
        }
        return payload.get();
    }
}
~~~

**Helper này chưa phải integration test hoàn chỉnh.** Test phải start Spring context với outbound adapter, inbound endpoint, Redis test server, StringRedisSerializer hai đầu và subscriber handler được nối vào thumbnailJobsInput. Dùng timeout có giới hạn; không chỉ sleep cố định rồi assume worker nhận.

### 23.4. Test two windows quan trọng nhất

Hai lỗi thường quyết định kiến trúc:

~~~text
Window A: DB commit -> publisher crash -> LPUSH chưa chạy
  -> Cần outbox/reconciliation.

Window B: BRPOP -> worker crash -> DB commit chưa chạy
  -> Cần processing/lease/reclaimer hoặc có nguồn job rebuild.
~~~

Một integration test happy path không chứng minh hai cửa sổ này an toàn. Khi đề xuất at-least-once, cần chứng minh qua **fault injection** và idempotency assertions.

### 23.5. Không kiểm chứng bằng LLEN duy nhất

Nếu consumer BRPOP quá nhanh, khi test đo LLEN có thể là 0 dù adapter đã LPUSH. Dùng latch/captured JSON, eventId DB state hoặc test riêng producer-only không start consumer để kiểm tra List. Cần xác định cụ thể đang test **enqueue** hay **end-to-end processing**.

### 23.6. Test đa phiên bản serializer/schema

Trong rolling deployment, job từ producer v1 còn trong List khi worker v2 start. Test phải bảo đảm worker v2 đọc được payload v1 hoặc đưa record sang durable failure state; không để toàn bộ queue bị chặn bởi một poison message.

## 24. Troubleshooting

### 24.1. LLEN không tăng sau khi send

Kiểm tra:

1. Spring Message đã vào đúng input channel chưa?
2. Có filter/router discard message không?
3. Handler có được đăng ký/start không?
4. Queue expression có chọn đúng key không?
5. Redis connection/ACL có hoạt động không?
6. Serializer có ném exception trước LPUSH không?
7. Có worker khác đang BRPOP ngay làm LLEN giảm không?
8. Redis instance/database index có đúng không?

**LLEN=0** không tự chứng minh LPUSH chưa từng chạy nếu consumer hoạt động đồng thời.

### 24.2. LLEN tăng nhưng worker không nhận

Có thể vì:

- Worker đang nghe **sai Redis key/instance/database**.
- Inbound endpoint chưa start hoặc Redis connection lỗi.
- Serializer mismatch khiến payload không tới business handler.
- Redis queue inbound đang lỗi trong listener task/recovery loop.
- Key là Redis List nhưng worker lại subscribe Pub/Sub channel hoặc dùng XREAD trên Stream.
- ACL người tiêu thụ thiếu quyền BRPOP/BLPOP.

Theo dõi inbound errors và thử một test worker có đúng queue key/payload serializer.

### 24.3. Worker nhận sai thứ tự

Kiểm tra cả **leftPush** và **rightPop**. LPUSH + BLPOP tạo LIFO, không FIFO. Với nhiều workers, thứ tự **business completion** vẫn có thể khác thứ tự pop ngay cả khi producer/consumer chọn đúng hai đầu List.

### 24.4. Worker parse JSON lỗi

Nếu Redis raw bytes bắt đầu như binary Java serialization hoặc JSON string literal với escaped quotes, producer có thể đang dùng serializer không tương thích. Dùng raw Redis inspection ở test namespace, so sánh bytes, và cấu hình StringRedisSerializer tường minh.

### 24.5. Một job bị chạy hai lần

Có thể do:

- Producer retry LPUSH sau timeout.
- Outbox publisher replay.
- Reconciliation enqueue job chưa DONE.
- Operator replay dead jobs.
- Reliable queue reclaimer nhận lại job sau lease expiry.

Xác định cùng **eventId** hay chỉ cùng productId. Nếu cùng eventId mà output bị lặp, kiểm tra idempotency ledger/unique constraint. Nếu khác eventId nhưng cùng business imageVersion, cần business dedup key.

### 24.6. Job biến mất sau worker lỗi

Nếu worker dùng BRPOP direct, item có thể đã bị xóa khỏi List trước khi business commit. Redis persistence không tự restore. Tìm business state NEEDS_THUMBNAIL, outbox/reconciliation hoặc processing store; không mong adapter tự có dead-letter/requeue.

### 24.7. Queue key báo WRONGTYPE

Một service khác có thể đã ghi key dưới dạng String/Hash/Set. Dùng **TYPE key** trên Redis test/monitor được phép để xác minh. Không tự xóa production key; sửa namespace hoặc migration có kiểm soát.

### 24.8. Redis timeout nhưng job vẫn xuất hiện

Đây là **unknown result**: Redis có thể xử lý LPUSH thành công nhưng reply mất. Retry có thể tạo hai items. Giữ stable eventId, dùng outbox state và idempotent worker. Không chuyển unknown outcome thành chắc chắn failed.

### 24.9. Redis queue memory tăng vô hạn

Kiểm tra enqueue rate, worker success rate, processing time, error/retry hot loop, payload size và unexpected producer duplicate. Cân nhắc throttling/capacity policy, scale workers theo downstream capacity, TTL/reconcile nếu phù hợp. Không LTRIM production queue để xóa backlog khi business không cho phép mất items.

### 24.10. Producer send thành công nhưng thumbnail chưa tạo

Đây có thể là **expected async behavior**. Enqueue và business processing là hai mốc. Truy vấn job status/thumbnail state từ database và kiểm tra worker metrics/queue length; không dùng boolean send hoặc List length thay business completion.

## 25. Tình huống kiến trúc thực tế

### 25.1. Case A – Thumbnail job có thể rebuild từ database

**Bối cảnh:** Catalog DB có record ảnh gốc và status NEEDS_THUMBNAIL, Redis chỉ giúp điều phối ImageWorker nhanh hơn.

~~~mermaid
flowchart LR
    API["HTTP/SFTP upload"] --> DB[("Catalog DB<br/>NEEDS_THUMBNAIL")]
    DB --> OUT["Redis queue outbound"]
    OUT --> Q[("Redis List pending")]
    Q --> W["ImageWorker"]
    W --> STORE[("Object storage thumbnail")]
    W --> DONE["Catalog DB status DONE"]
    DB --> REC["Periodic reconciliation"]
    REC --> OUT
~~~

**Đây là lựa chọn có thể chấp nhận direct POP** nếu:

- DB là source of truth về những ảnh chưa hoàn tất.
- Khi item mất sau BRPOP, scheduler tìm lại record NEEDS_THUMBNAIL và enqueue lại.
- ImageWorker idempotent theo productId/imageVersion.
- Có SLA cho reconciliation latency.
- Có monitoring số sản phẩm stale và retries.

**Lưu ý:** Thiết kế an toàn nhờ **database + reconciliation**, không phải bản thân BRPOP có ACK.

### 25.2. Case B – Import CSV từ SFTP

**Bối cảnh:** Một SFTP inbound adapter đồng bộ CSV, parser ghi import rows vào DB, sau đó push work items vào Redis List cho workers.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound<br/>poller"] --> CSV["CSV parser"]
    CSV --> DB[("Import DB rows + outbox")]
    DB --> PUB["Redis queue outbound<br/>LPUSH"]
    PUB --> Q[("import:{rows}:ready")]
    Q --> WORK["Row worker<br/>BRPOP"]
    WORK --> DB
~~~

Phân biệt:

- **SFTP inbound poller** tìm file theo lịch.
- **Redis queue outbound** đẩy từng row-job vào Redis List.
- **Redis queue inbound** lấy work items cho worker.
- **DB import state** xác định row đã xử lý/failed, không phải LLEN.

Không xóa file nguồn hoặc đánh dấu import DONE chỉ vì LPUSH tất cả rows thành công, nếu hợp đồng DONE nghĩa là từng row đã commit.

### 25.3. Case C – Redis queue outbound → HTTP outbound

Một ImageWorker có thể lấy item từ Redis List và gọi HTTP API để xử lý:

~~~text
Redis queue outbound (producer)
  -> Redis List
  -> Redis queue inbound (worker)
  -> HTTP outbound gateway/adapter
  -> External image processor
~~~

HTTP timeout có thể là **UNKNOWN**: provider đã xử lý nhưng response mất. Nếu job được retry, cần **idempotency key** hoặc khả năng lookup result; Redis List không tự giải quyết duplicate HTTP calls.

### 25.4. Case D – Thanh toán không được mất

**Không dùng Redis List direct POP làm nguồn duy nhất** cho nghiệp vụ trừ tiền hoặc điều chỉnh sổ cái. Cần durable producer handoff, consumer ACK/recovery, unique eventId và side effect idempotency.

~~~mermaid
flowchart LR
    PAY["Payment DB + transactional outbox"] --> LOG["Durable broker/Stream"]
    LOG --> CON["Consumer group + ACK"]
    CON --> LEDGER[("Ledger DB + inbox")]
    LEDGER -. "ACK after durable commit" .-> LOG
~~~

Nếu bắt buộc dùng Redis Lists, phải thiết kế và chứng minh qua fault injection **ready→processing claim, durable ACK, lease/reclaimer, dedup và reconciliation**; chi phí vận hành có thể lớn hơn dùng Redis Streams/AMQP/JMS.

### 25.5. Case E – Nhiều priority queues

~~~text
catalog:{thumbnail}:high
catalog:{thumbnail}:normal
catalog:{thumbnail}:low
~~~

Producer chọn queue theo allowlisted enum. Consumers có thể ưu tiên HIGH nhưng phải có **fairness** để LOW không starve vĩnh viễn. Mỗi queue cần LLEN/oldest-age metrics; Redis List không tự biết business priority chỉ vì tên key chứa high/low.

### 25.6. Case F – Redis List → Kafka bridge

~~~text
Redis LPUSH
  -> Redis BRPOP
  -> Kafka outbound producer
  -> Kafka broker ACK
~~~

**Cửa sổ mất:** Redis BRPOP đã xóa item nhưng Kafka producer chưa nhận ACK/commit; process crash có thể làm mất event. **Cửa sổ trùng:** Kafka đã lưu record nhưng client nhận outcome UNKNOWN, worker retry sẽ gửi lại.

Với bridge cần không mất dữ liệu, dùng durable source/processing protocol hoặc transactional outbox/inbox và Kafka eventId dedup. Đừng nghĩ Kafka idempotent producer tự tạo transaction nguyên tử với Redis BRPOP.

### 25.7. Case G – Redis List cho best-effort background email

Redis List queue có thể được chọn cho notifications có nguồn campaign/job table và cho phép reconcile. Nhưng email provider timeout không chứng minh đã gửi hay chưa. Cần campaignRecipientKey/idempotency nếu hỗ trợ, rate-limit, retry bounded, dead job policy và tránh gửi cùng thông báo nhiều lần.

### 25.8. Case H – Broadcast tới ba replicas

**Không dùng Redis List queue outbound nếu mục tiêu mỗi replica đều nhận cùng notification.** Redis POP là **competing consumers**: một Redis List item thường được lấy bởi một worker. Khi muốn invalidate local cache trên mọi replica, dùng **Redis Pub/Sub outbound** (với TTL/reconciliation) hoặc một mô hình fan-out durable có queue riêng cho từng subscriber.

## 26. Những hiểu lầm thường gặp

**“Redis queue outbound là Redis Pub/Sub outbound.”** Sai. Queue outbound **LPUSH/RPUSH** vào List; Pub/Sub outbound **PUBLISH** tới channel.

**“Redis List là Redis Stream không có consumer group.”** Chúng là các Redis data types khác nhau. List không có record ID/PEL/XACK native.

**“LPUSH mặc định nghĩa là FIFO với mọi consumer.”** FIFO chỉ đúng khi phía nhận pop ở **đầu đối diện**, thường BRPOP.

**“LPUSH + BLPOP là FIFO.”** Cùng phía trái dẫn đến LIFO/stack behavior.

**“FIFO theo Redis nghĩa là jobs hoàn thành theo đúng thứ tự.”** Nhiều workers có processing time khác nhau; completion order có thể lệch.

**“Redis queue outbound sẽ tự tạo một JMS/AMQP queue entity.”** Redis List là một key; push có thể tạo List khi key chưa tồn tại.

**“List key là một Redis topic có thể SUBSCRIBE.”** LPUSH không phát Pub/Sub notification.

**“Queue outbound có replyChannel giống gateway.”** Đây là one-way adapter, không chờ business reply.

**“MessageChannel.send accepted nghĩa là worker đã làm xong.”** Spring dispatch/enqueue và business commit là hai mốc khác nhau.

**“Redis LPUSH trả thành công nghĩa là Redis đã fsync/replicate tuyệt đối và worker đã ACK.”** Phải xem Redis durability policy; List POP không có native ACK.

**“Redis AOF tự phục hồi item đã BRPOP nhưng chưa commit.”** Persistence không rollback destructive POP theo transaction của application.

**“Queue inbound dùng Spring Integration Poller giống store inbound.”** Redis queue inbound là message-driven blocking listener; store inbound là polling source/view.

**“extractPayload=true tự chuyển Spring headers thành JSON.”** Nó chỉ gửi payload; muốn headers cần envelope/mapping rõ.

**“extractPayload=false là cách an toàn nhất khi giao tiếp nhiều ngôn ngữ.”** Whole Spring Message có type/serializer/runtime headers phức tạp; thường nên gửi DTO JSON.

**“Serializer mặc định luôn JSON UTF-8.”** Có thể là JDK serializer cho non-String payload; cấu hình explicit và test bytes.

**“StringRedisSerializer có thể tự serialize mọi Java POJO.”** Chỉ chuyển payload thành String JSON trước hoặc dùng serializer typed phù hợp.

**“Spring MessageHeaders.ID là business eventId.”** Runtime Message ID có thể khác qua retries/restarts; eventId phải ổn định theo nghiệp vụ.

**“Redis List tự deduplicate items cùng eventId.”** List cho phép duplicate values; cần business unique constraint.

**“Tăng max retries luôn ngăn mất job.”** Retry trong JVM không bền qua crash và có thể tạo duplicate ở outcome UNKNOWN.

**“Outbox bảo đảm consumer không thể mất job sau BRPOP.”** Outbox bảo vệ ý định enqueue ở producer; consumer vẫn cần reliable processing hoặc reconciliation.

**“@Transactional trên JDBC làm Redis LPUSH rollback.”** Không có distributed transaction mặc định giữa Redis và database.

**“LLEN=0 nghĩa là business jobs DONE.”** Worker có thể đã pop rồi crash; internal executor có thể giữ tasks chưa commit.

**“QueueChannel hay ExecutorChannel mặc định durable qua restart.”** Thường là memory queues, cần persistent contract nếu muốn bền vững.

**“Một List item được broadcast tới mọi ImageWorker.”** Competing consumers pop mỗi item cho một worker; broadcast là use case khác.

**“BLMOVE tự quản lý retry count, lease và ACK.”** BLMOVE chỉ chuyển item nguyên tử; application tự quản lý processing state.

**“Xóa cả processing List khi gặp lỗi sẽ retry an toàn.”** Có thể làm mất jobs của nhiều workers; cần jobId/ownership/reclaimer.

**“LREM sau commit bảo đảm exactly-once.”** Crash sau commit trước LREM có thể làm duplicate replay; idempotency cần thiết.

**“Dùng dynamic queue name lấy từ raw HTTP header là an toàn.”** Có nguy cơ ghi nhầm tenant/key; phải allowlist và ACL.

**“Redis key có prefix prod là security boundary.”** Prefix là quy ước, không thay quyền Redis ACL, TLS và network isolation.

**“Redis Cluster BLMOVE có thể dùng keys từ bất kỳ slots.”** Multi-key command phải đáp ứng cùng hash slot.

**“LTRIM để giữ Redis queue nhỏ là không ảnh hưởng nghiệp vụ.”** Có thể xóa jobs chưa xử lý; chỉ chấp nhận khi loss policy rõ.

**“TTL của Redis List chỉ làm worker nhận muộn hơn.”** TTL expiry có thể xóa toàn bộ pending jobs.

**“Một test happy path chứng minh at-least-once end-to-end.”** Cần test crash ở hai phía LPUSH và BRPOP, idempotency, recovery, unknown outcomes và failover.

**“Tăng số workers sẽ luôn giảm latency.”** Nếu database/object storage đã bão hòa, tăng workers có thể tăng retries và lỗi.

## 27. Checklist thiết kế Redis queue outbound

| Nhóm | Câu hỏi cần xác minh |
| --- | --- |
| **Use case** | Job có chấp nhận mất sau destructive POP không? Có nguồn rebuild không? |
| **Đúng adapter** | Redis queue outbound (List PUSH) hay Pub/Sub/store/Stream/gateway? |
| **Redis key** | Queue cố định hay queue-expression; namespace và type LIST đúng? |
| **Direction** | leftPush=true/false và consumer rightPop=true/false có cùng hợp đồng FIFO không? |
| **Connection** | RedisConnectionFactory đúng Redis instance/database/Cluster, TLS/credentials? |
| **Payload type** | JSON String, byte[] hay whole Spring Message? |
| **Serializer** | Outbound/inbound đều dùng StringRedisSerializer hoặc contract khác khớp nhau? |
| **Headers** | eventId, traceparent, tenantRef có trong envelope nếu cần qua Redis? |
| **Schema** | eventType/schemaVersion và validation của worker hỗ trợ rolling upgrade? |
| **MessageChannel** | Direct/Executor/QueueChannel có durable/async semantics nào? |
| **Queue routing** | queue-expression được tạo từ enum/allowlist, không từ raw input? |
| **Enqueue status** | Phân biệt channel accepted, Redis command success và business DONE? |
| **Producer retry** | Max attempts/backoff, unknown outcome và stable eventId? |
| **Producer durability** | DB transaction/outbox/reconciliation giải quyết crash-before-LPUSH? |
| **Consumer durability** | BRPOP loss window có được chấp nhận/bù bằng DB không? |
| **Reliable queue** | Nếu cần: BLMOVE, processing list, owner, lease, ACK, reclaimer? |
| **Idempotency** | Unique eventId, productId/imageVersion, deterministic output/conditional commit? |
| **Dead jobs** | Poison JSON/invalid schema được lưu bền, có owner, audit và replay? |
| **Redis persistence** | AOF/RDB, replicas/failover RPO/RTO có phù hợp? |
| **Redis Cluster** | Multi-key processing/ready keys có cùng hash slot? |
| **Capacity** | LLEN, oldest age, peak enqueue rate, worker throughput và Redis memory? |
| **Rate limiting** | Backpressure và bounded internal executor, không LTRIM mất dữ liệu? |
| **Security** | Redis ACL, key namespace, tenant/objectKey validation và secrets? |
| **Lifecycle** | Startup/readiness, shutdown, reconnect và outbox recovery? |
| **Metrics** | Push/claim/processing/DONE/reclaim/dead và queue age được tách riêng? |
| **Testing** | Redis thật, direction, serializer, worker offline, duplicate, crash/failover? |
| **Documentation** | Chủ sở hữu queue, schema, TTL/retention, loss policy và runbook? |

### 27.1. Quy tắc lựa chọn nhanh

**Redis queue outbound** phù hợp khi:

- Cần **đưa work item** cho một trong nhiều consumers.
- Chấp nhận Redis List đơn giản và có thể rebuild/đối soát công việc nếu mất sau POP, hoặc đã thiết kế reliable claim/recovery riêng.
- Có yêu cầu FIFO theo **thứ tự pop**, không nhầm với completion order.
- Có serializer, eventId/idempotency và monitoring rõ.

**Redis Pub/Sub outbound** phù hợp cho notification broadcast best-effort. **Redis Stream outbound** phù hợp hơn khi cần record IDs/consumer groups/ACK/replay. **AMQP/JMS/Kafka** phù hợp tùy các yêu cầu broker, ordering, capacity, durability và vận hành.

### 27.2. Mẫu hợp đồng producer–consumer tối thiểu

~~~text
Redis key:
  catalog:{thumbnail}:pending

Producer:
  LPUSH (leftPush=true)
  StringRedisSerializer, extractPayload=true
  JSON schemaVersion=1
  stable eventId

Consumer:
  BRPOP (rightPop=true)
  StringRedisSerializer, expectMessage=false
  JSON schemaVersion=1
  idempotent handler + durable job state

Operations:
  monitor LLEN + business DONE + oldest job age
  retry/reconciliation for job loss
  alert on Redis errors, duplicates and poison jobs
~~~

### 27.3. Không gắn “exactly-once” lên adapter

Một nhãn **exactly-once processing** chỉ có ý nghĩa khi định nghĩa rõ **business side effect**, idempotency, durable commits và cách xử lý crash windows. RedisQueueOutboundChannelAdapter **không có API ACK consumer hay distributed transaction**; nó chỉ giúp Spring Integration ghi vào Redis List.

## 28. Câu hỏi tự kiểm tra

1. Redis queue outbound channel adapter dùng lệnh Redis nào để enqueue item?
2. RedisQueueOutboundChannelAdapter khác RedisPublishingMessageHandler ở đâu?
3. Redis List queue khác Redis Stream ở record ID, consumer group và ACK như thế nào?
4. Vì sao Redis queue outbound là **one-way** chứ không phải Redis queue outbound gateway?
5. Redis List key phải được tạo thủ công trước khi LPUSH hay Redis có thể tạo khi push?
6. Khi key đã chứa Redis String, lệnh LPUSH sẽ xảy ra điều gì?
7. LPUSH kết hợp với BRPOP có đặc tính FIFO như thế nào?
8. RPUSH kết hợp BLPOP có giữ FIFO không? Vì sao?
9. LPUSH kết hợp BLPOP tạo LIFO hay FIFO?
10. Vì sao FIFO theo Redis pop không chứng minh business completion order?
11. Các tùy chọn leftPush(true) và rightPop(true) thuộc hai endpoint nào?
12. Redis queue inbound có cần Spring Integration Pollers.fixedDelay không?
13. extractPayload(true) mặc định gửi dữ liệu gì vào Redis List?
14. Khi dùng extractPayload(false), worker cần thống nhất điều gì về serializer và expectMessage?
15. Vì sao Spring MessageHeaders.ID không thay business eventId?
16. Nếu String payload không chỉ định serializer, Spring Integration có thể dùng serializer nào?
17. Nếu payload là POJO còn serializer là StringRedisSerializer, rủi ro gì?
18. Vì sao gửi JSON String bằng JSON serializer một lần nữa có thể gây double-encoding?
19. Redis List có metadata headers giống AMQP/Kafka không?
20. Redis.queueOutboundChannelAdapter(...) cần RedisConnectionFactory để làm gì?
21. Java DSL và @ServiceActivator trực tiếp là hai cách cấu hình tương đương ở tầng nào?
22. Nếu chạy hai publisher flows trỏ cùng Redis key, có thể xảy ra duplicate thế nào?
23. queue khác queue-expression như thế nào, và có được cấu hình cả hai không?
24. Queue-expression đọc header từ incoming Spring Message cần trust boundary nào?
25. Vì sao allowlisted enum an toàn hơn raw HTTP header redisQueue?
26. Khi producer dùng ba priority Lists, worker nên xử lý fairness/starvation ra sao?
27. Nếu producer LPUSH nhưng worker offline, Redis có thể giữ item với điều kiện nào?
28. Vì sao Redis List direct BRPOP không có consumer ACK native?
29. Nếu worker crash sau BRPOP trước DB commit, item có trở lại List không?
30. Khi LPUSH thành công nhưng client không nhận reply, retry có thể tạo duplicate như thế nào?
31. Vì sao phải giữ nguyên eventId khi retry cùng một business job?
32. RetryTemplate trong JVM giải quyết được điều gì và không giải quyết sau crash điều gì?
33. Outbox ngăn mất job ở khoảng crash nào giữa DB commit và LPUSH?
34. Vì sao outbox không tự bảo vệ khoảng crash sau BRPOP?
35. Một periodic reconciliation dựa trên trạng thái NEEDS_THUMBNAIL có thể bù item mất như thế nào?
36. Làm sao dùng unique eventId hoặc productId/imageVersion để xử lý idempotent?
37. Khi output thumbnail đã được tạo nhưng worker timeout, vì sao cần deterministic object key/lookup?
38. BLMOVE ready→processing cải thiện điều gì so với destructive BRPOP?
39. Processing List có tự quản lý lease/attempt count và reclaimer không?
40. Vì sao cần LREM đúng item, ownership và stable job identity?
41. Nếu business commit nhưng worker crash trước LREM, nguy cơ gì phát sinh?
42. Redis Cluster yêu cầu gì với source/destination keys trong BLMOVE?
43. Vì sao TTL/eviction trên queue List có thể làm mất pending jobs?
44. LLEN=0 có đồng nghĩa mọi jobs DONE không?
45. Với hai consumers đang chạy, một List item được broadcast hay competing pop?
46. DirectChannel và ExecutorChannel khác nhau như thế nào về lỗi và khả năng mất job trong memory?
47. ErrorChannel của Spring Integration có tự tạo Redis DLQ/replay không?
48. Redis ACL cần giới hạn những commands/keys nào cho producer và worker?
49. Một test Redis CLI nào chứng minh LPUSH A/B/C rồi RPOP ra A/B/C?
50. Một integration test nào phát hiện producer/worker dùng serializer khác nhau?
51. Một integration test nào chứng minh worker offline rồi restart vẫn nhận pending List item?
52. Một integration test nào chứng minh job có thể mất sau BRPOP-before-commit?
53. Một integration test nào chứng minh outbox replay có thể tạo duplicate nhưng idempotency ngăn side effect lặp?
54. Nếu Redis LPUSH liên tục nhanh hơn worker, cần theo dõi metrics nào?
55. Tại sao không nên dùng LTRIM làm giải pháp capacity mặc định cho queue chứa job bắt buộc?
56. Nếu Redis failover trả outcome UNKNOWN, vận hành cần đối soát như thế nào?
57. Nếu QueueChannel nội bộ đã accepted message, Redis queue outbound chắc chắn đã LPUSH chưa?
58. Khi nào nên chuyển từ Redis List tự xây ACK/reclaimer sang Redis Streams hoặc RabbitMQ?
59. Trong flow SFTP→Redis List→worker, mốc nào mới là “import completed”?
60. Hãy thiết kế một thumbnail pipeline có payload versioned, Redis List FIFO, idempotent worker, producer outbox và reconciliation.

## 29. Nguồn tham khảo và phạm vi phiên bản

Các nguồn chính thức nên đối chiếu trước khi áp dụng code:

- [Spring Integration – Redis Support](https://docs.spring.io/spring-integration/reference/redis.html): phần Redis Queue Outbound Channel Adapter, Java DSL/bean/XML, queue-expression, leftPush, serializer và extractPayload.
- [Spring Integration – RedisQueueOutboundChannelAdapter Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/redis/outbound/RedisQueueOutboundChannelAdapter.html): constructors String/Expression + RedisConnectionFactory; setExtractPayload, setSerializer, setLeftPush.
- [Spring Integration – RedisQueueMessageDrivenEndpoint Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/redis/inbound/RedisQueueMessageDrivenEndpoint.html): Redis List consumer endpoint, rightPop, serializer và lifecycle.
- [Spring Integration – Changes 4.2 to 4.3](https://docs.spring.io/spring-integration/reference/changes-4.2-4.3.html): bổ sung leftPush/rightPop cho Redis List queue adapters.
- [Redis – Lists data type](https://redis.io/docs/latest/develop/data-types/lists/): Redis List, LPUSH/RPUSH/POP và thứ tự.
- [Redis – BLMOVE](https://redis.io/docs/latest/commands/blmove/): atomic move giữa Lists, lựa chọn RIGHT/LEFT và blocking read.
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): RedisConnectionFactory, serializers và RedisTemplate operations.

**Giới hạn phiên bản:** Spring Integration 3.0 cung cấp Redis queue outbound adapter; tùy chọn leftPush/rightPop xuất hiện từ 4.3. Các API Java DSL, Redis serializer, Spring Boot configuration và Redis Cluster behavior phải được **biên dịch và kiểm thử với BOM/client/server version thực tế** trước production. Bài này là nội dung **STEP 4**, không đồng nghĩa đã chạy Gradle/build hay QA học thuật chuyên sâu ở STEP 6.

## Tổng kết

**Redis queue outbound adapter** nhận Spring Integration Message và ghi vào **Redis List** bằng **LPUSH mặc định** hoặc RPUSH. Trong Java có thể dùng **Redis.queueOutboundChannelAdapter(...)** hoặc **RedisQueueOutboundChannelAdapter** trực tiếp. Phải thống nhất **queue name/queue-expression, RedisConnectionFactory, StringRedisSerializer, extractPayload và leftPush** với consumer. Cặp **LPUSH + BRPOP** giúp FIFO theo **thứ tự pop**, không cam kết thứ tự business side effects hoàn tất khi có nhiều workers.

Điều cần nhớ là **enqueue thành công khác business completion**. Redis List giữ backlog khi worker offline nếu dữ liệu còn, nhưng **BRPOP phá hủy item trước khi handler commit** và không có ACK native. Worker crash sau pop có thể làm mất job; producer retry ở trạng thái Redis command UNKNOWN có thể tạo duplicate. **Transactional outbox, durable business status, reconciliation, idempotent worker** hoặc một reliable processing protocol/Redis Streams là những công cụ cần thiết nếu nghiệp vụ phải hoàn thành qua mọi sự cố.

Khi nối Redis List với HTTP, SFTP, File, JMS, AMQP, Kafka và cơ sở dữ liệu trong **SPRING_INTEGRATION_ADAPTERS**, hãy tách biệt các mốc **DB commit → Spring MessageChannel dispatch → Redis LPUSH/RPUSH → worker claim/pop → durable business commit**. Một flow chất lượng không chỉ enqueue được JSON, mà còn có **hợp đồng dữ liệu, ranh giới lỗi, bảo mật, capacity, monitoring và thử nghiệm crash** đủ rõ để vận hành và khôi phục.
