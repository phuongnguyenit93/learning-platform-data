# Redis queue inbound adapter

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **Redis queue inbound adapter** đưa dữ liệu từ Redis **List** vào **Spring Integration MessageChannel** như thế nào; phân biệt nó với Redis Pub/Sub inbound adapter.
- Hiểu cơ chế **blocking pop**, cách phối hợp **LPUSH/BRPOP** hoặc **RPUSH/BLPOP**, thứ tự FIFO và ảnh hưởng khi nhiều consumers cùng đọc một queue key.
- Cấu hình **RedisQueueMessageDrivenEndpoint**, **RedisConnectionFactory**, output channel, transformer và service activator; phân biệt endpoint message-driven dựa trên blocking read với poller thực sự của Spring Integration.
- Xây dựng hợp đồng payload, serializer/charset, eventId, schemaVersion và quy tắc xử lý message thiếu hoặc sai cấu trúc.
- Phân tích cửa sổ mất dữ liệu khi **pop khỏi List trước khi business transaction commit**, kể cả khi Redis đã bật persistence; hiểu giới hạn của retry và errorChannel.
- Thiết kế phương án đáng tin cậy hơn bằng **BLMOVE/LMOVE sang processing list**, ACK ở mức ứng dụng, reclaimer, idempotent consumer hoặc **Redis Streams consumer groups**.
- Tổ chức concurrency, retry/backoff, xử lý poison message, monitoring ready/processing/dead messages, bảo mật và graceful shutdown.
- Kiểm thử bằng Redis thật các tình huống FIFO, cạnh tranh consumer, crash-after-pop, duplicate, payload lỗi, reconnect và năng lực phục hồi.

## 1. Tình huống: Redis List làm hàng đợi công việc

Giả sử dịch vụ **CatalogService** cần yêu cầu **ImageWorker** tạo thumbnail sau khi nhận ảnh sản phẩm. Thay vì gửi HTTP request đồng bộ và chờ image processing, CatalogService đưa một task vào **Redis List** có tên:

~~~text
Key: catalog:thumbnail:pending
Value: {"eventId":"evt-thumb-1001","schemaVersion":1,
        "productId":"P-1001","imageKey":"images/P-1001/original.jpg"}
~~~

ImageWorker muốn nhận task đó rồi chạy xử lý:

~~~mermaid
flowchart LR
    P["CatalogService"] -->|"LPUSH task"| L["Redis List<br/>catalog:thumbnail:pending"]
    L -->|"Blocking POP"| A["Redis queue<br/>inbound adapter"]
    A --> C["Spring Integration<br/>MessageChannel"]
    C --> V["Validate / transform"]
    V --> H["Thumbnail service activator"]
    H --> OBJ[("Object storage")]
    H --> DB[("Catalog DB")]
~~~

**Redis queue inbound adapter** là ranh giới tiếp nhận message từ queue dạng Redis List. Từ góc nhìn Spring Integration, endpoint này là **message producer**: nó lấy item từ Redis và phát **Spring Message** vào output channel, để downstream transformer/router/service activator xử lý.

Điểm thiết kế phải kiểm tra ngay: **Nếu adapter pop task khỏi Redis rồi JVM chết trước khi ghi thumbnail, task có còn trong queue không?** Với thao tác pop phá hủy trực tiếp, câu trả lời thường là **không**. Đây là khác biệt quan trọng giữa một List queue đơn giản và hệ thống message broker có consumer ACK, pending state và redelivery.

Bài này thuộc chương **Adapter Redis** của module **SPRING_INTEGRATION_ADAPTERS**. Module nghiên cứu inbound/outbound adapter, gateway, poller, MessageChannel và tích hợp với File, SFTP, HTTP, JMS, AMQP, Kafka, database. Cùng mang tên “adapter” nhưng **hợp đồng giao nhận phụ thuộc hệ thống nguồn**, không thể suy bảo đảm của AMQP/Kafka chỉ từ việc Spring Integration đã nhận được một message.

## 2. Redis List và queue: hiểu dữ liệu trước khi dùng adapter

Redis **List** là một chuỗi các phần tử có thứ tự. Có các lệnh thêm và lấy phần tử ở hai đầu:

| Lệnh | Hành vi cơ bản | Ứng dụng trong queue |
| --- | --- | --- |
| **LPUSH key value** | Thêm value vào đầu bên trái | Producer thêm task theo mẫu LPUSH/BRPOP |
| **RPUSH key value** | Thêm value vào đầu bên phải | Producer thêm task theo mẫu RPUSH/BLPOP |
| **LPOP key** | Lấy và xóa phần tử trái | Consumer nonblocking theo mẫu RPUSH/LPOP |
| **RPOP key** | Lấy và xóa phần tử phải | Consumer nonblocking theo mẫu LPUSH/RPOP |
| **BLPOP key timeout** | Đợi phần tử rồi lấy/xóa từ bên trái | Blocking consumer của mẫu RPUSH/BLPOP |
| **BRPOP key timeout** | Đợi phần tử rồi lấy/xóa từ bên phải | Blocking consumer của mẫu LPUSH/BRPOP |
| **LLEN key** | Đếm item còn trong List | Đo backlog ready, không đo task đang xử lý |
| **LMOVE/BLMOVE** | Chuyển item giữa hai Lists một cách nguyên tử | Mẫu ready → processing để có cơ sở recovery |
| **LREM key count value** | Xóa phần tử khớp value trong List | Có thể làm ACK ứng dụng sau xử lý, cần ID/đồng bộ hợp lý |

### 2.1. Hai mẫu FIFO tương đương khi dùng đúng chiều

**Mẫu A – producer LPUSH, consumer BRPOP:**

~~~text
LPUSH task-A
LPUSH task-B
LPUSH task-C

List trái -> phải:
  [task-C, task-B, task-A]

BRPOP lấy: task-A, rồi task-B, rồi task-C
~~~

**Mẫu B – producer RPUSH, consumer BLPOP:**

~~~text
RPUSH task-A
RPUSH task-B
RPUSH task-C

List trái -> phải:
  [task-A, task-B, task-C]

BLPOP lấy: task-A, rồi task-B, rồi task-C
~~~

Hai mẫu đều có thể đạt thứ tự FIFO theo thứ tự Redis thực hiện các lệnh push. **Không trộn LPUSH với BLPOP** rồi kỳ vọng FIFO: cùng đầu có thể tạo LIFO.

### 2.2. Redis List không tự gắn trạng thái pending/ack

Khi **BRPOP** trả item, phần tử đó đã bị xóa khỏi List. Redis không tự nhớ rằng **consumer X đang xử lý task A** để đợi ACK từ business handler.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as Redis List
    participant I as Inbound adapter
    participant H as Thumbnail handler
    P->>R: LPUSH task-A
    I->>R: BRPOP pending timeout
    R-->>I: task-A (đã xóa khỏi List)
    I->>H: Spring Message(task-A)
    H--xH: Process crash
    Note over R,H: task-A không còn trong pending List
~~~

**Cần phân biệt** Redis persistence với acknowledgment: Redis có thể ghi bền trạng thái List, nhưng nếu lệnh POP đã được áp dụng, trạng thái được lưu bền sau đó vẫn là **List không còn item vừa pop**. AOF/RDB không tự biến POP thành một delivery chưa ACK.

### 2.3. FIFO của queue không bằng thứ tự hoàn tất công việc

Ngay cả khi Redis trả item A trước item B, hai workers có thể có thời gian xử lý khác nhau:

~~~text
Worker 1 nhận A -> xử lý 10 giây
Worker 2 nhận B -> xử lý 1 giây

Kết thúc: B trước A
~~~

Nếu nghiệp vụ cần thao tác theo thứ tự cho cùng productId, cần version/sequence hoặc khóa xử lý theo business key. **Redis List FIFO không bảo đảm completion order toàn cục khi có concurrency**.

### 2.4. Queue key không phải Pub/Sub channel

Tên **catalog:thumbnail:pending** trong Redis List là **key lưu dữ liệu**. Lệnh LPUSH thay đổi List, **không PUBLISH** một Redis Pub/Sub notification trên channel cùng tên.

Một subscriber SUBSCRIBE catalog:thumbnail:pending sẽ **không tự nhận** items vừa LPUSH. Và một Redis queue inbound adapter sử dụng List không nhận PUBLISH như Pub/Sub inbound adapter.

## 3. Redis queue inbound, Redis Pub/Sub và Redis Streams khác nhau

| Tiêu chí | Redis List queue inbound | Redis Pub/Sub inbound | Redis Streams consumer |
| --- | --- | --- | --- |
| Nguồn dữ liệu | Redis List key | Redis Pub/Sub channel/pattern | Redis Stream key |
| Ghi dữ liệu | LPUSH/RPUSH | PUBLISH | XADD |
| Đọc | BLPOP/BRPOP hoặc cơ chế List phù hợp | SUBSCRIBE/PSUBSCRIBE callback | XREAD/XREADGROUP |
| Item còn khi consumer offline? | **Có**, nếu chưa bị pop và Redis giữ dữ liệu | **Không**, message Pub/Sub không có subscriber backlog | **Có**, trong phạm vi retention |
| Nhiều consumers cùng nguồn | Tranh nhau pop từng item | Mỗi subscriber phù hợp có thể nhận | Consumer groups phân phối records |
| Broker-managed ACK | Không có trên List POP đơn giản | Không có | XACK cho consumer group |
| Pending/redelivery | Phải tự thiết kế processing list/reclaimer | Không có | PEL/pending + claim/recovery |
| Dễ mất sau khi ứng dụng nhận? | **Có**, khi POP rồi crash | **Có**, sau callback hoặc khi offline | Tùy ACK/retention/thiết kế xử lý |
| Phù hợp | Task queue đơn giản có thể phục hồi/rebuild | Cache invalidation best-effort | Event/job cần history và khả năng phục hồi rõ |

### 3.1. Không gọi mọi Redis inbound adapter là Pub/Sub

Redis Pub/Sub inbound dùng listener và topic pattern; **Redis queue inbound adapter** xử lý item trong **List**. Hai adapter có thể đều gửi Spring Message vào DirectChannel, nhưng **phần trước MessageChannel hoàn toàn khác nhau**.

### 3.2. Streams không chỉ là “List có thêm field”

Redis Streams có record IDs, consumer groups, pending entry tracking và các thao tác như XACK/XCLAIM/XAUTOCLAIM. Các cơ chế đó không tự xuất hiện khi chuyển một List qua Redis queue inbound adapter. Nếu yêu cầu cần pending/ack, phải chọn **Stream** hoặc tự triển khai reliable queue có trách nhiệm vận hành.

### 3.3. Một List có dữ liệu khi consumer offline, nhưng vẫn có cửa sổ mất

~~~text
Tình huống 1:
  Worker offline trước khi POP.
  Producer LPUSH task.
  -> Task còn trong List để worker nhận sau.

Tình huống 2:
  Worker vừa BRPOP task.
  Worker crash trước business commit.
  -> Task đã rời List; không tự quay lại.
~~~

Redis List queue cơ bản **khác Pub/Sub ở khả năng tích lũy backlog khi worker offline**, nhưng **chưa đạt at-least-once end-to-end** nếu vẫn pop phá hủy trực tiếp trước xử lý.

## 4. Message-driven dựa trên blocking POP, không phải Pub/Sub callback

Tên **message-driven endpoint** đôi khi khiến người học nghĩ rằng Redis chủ động gửi message tới client bằng PUBLISH. Với List queue, consumer có thể **block chờ Redis trả item** qua lệnh đọc List.

~~~text
RedisQueueMessageDrivenEndpoint
   -> Redis connection
   -> blocking List pop, ví dụ BRPOP
   -> item được lấy từ Redis
   -> tạo Spring Message
   -> output MessageChannel
~~~

Nó được xem là **message-driven trong mô hình Integration endpoint** vì có một loop lắng nghe/blocking read và phát message khi có item, **không yêu cầu một Spring Integration Poller chạy định kỳ** như File inbound.

### 4.1. Blocking read không phải poller.fixedDelay

| Khái niệm | Công việc |
| --- | --- |
| Blocking Redis pop | Lệnh Redis chờ item cho tới khi có item/timeout |
| Redis queue message-driven endpoint | Quản lý vòng nhận của queue, phát Spring Message |
| Spring Integration poller | Scheduler gọi receive() định kỳ từ PollableMessageSource |
| QueueChannel poller nội bộ | Poller lấy Spring Message từ QueueChannel, không nhất thiết đọc Redis |

Nếu một phiên bản framework có lựa chọn **polled Redis store source**, đó là mô hình endpoint khác; không tự thêm poller vào RedisQueueMessageDrivenEndpoint chỉ vì nó đọc dữ liệu từ List.

### 4.2. Blocking timeout dùng để làm gì?

Với blocking Redis pop, timeout có thể giúp loop nhận kiểm tra trạng thái dừng/reconnect theo implementation. Timeout **không có nghĩa retry backoff nghiệp vụ**, cũng **không tạo delivery ACK**. Không áp một giá trị receive-timeout chưa kiểm thử vào môi trường có SLA và client version cụ thể.

### 4.3. Nên dùng component nào?

Spring Integration Redis có endpoint chuyên dụng thường được biết đến với tên **RedisQueueMessageDrivenEndpoint** cho Redis List queue inbound. Các phiên bản có thể khác nhau ở constructor/DSL setters, serializer và task executor. Phần ví dụ dưới đây dùng cấu trúc endpoint đã xuất hiện trong các thế hệ Spring Integration; khi đưa vào project phải xác minh API của **phiên bản thực tế** thay vì suy từ code của một phiên bản khác.

Mặc dù có thể tự viết loop RedisTemplate.opsForList().rightPop(...), adapter chuyên dụng giúp quản lý **lifecycle**, **output channel** và integration wiring nhất quán hơn. Tuy nhiên adapter **không thể tạo bảo đảm giao nhận mà Redis List POP không cung cấp**.

## 5. Hợp đồng message: Redis List item là bytes, không phải Spring Message

Redis List lưu giá trị dưới dạng dữ liệu đã được serialize. Spring Message chỉ xuất hiện **khi inbound endpoint tạo nó**.

~~~mermaid
flowchart LR
    DTO["Task DTO"] --> SER["Serializer"]
    SER --> B["Redis List bytes"]
    B --> POP["Queue inbound endpoint"]
    POP --> MC["Spring Message<br/>payload + headers"]
    MC --> TR["Transformer / parser"]
    TR --> H["Thumbnail handler"]
~~~

### 5.1. Chọn schema tường minh

Ví dụ task JSON:

~~~json
{
  "eventId": "evt-thumb-1001",
  "eventType": "THUMBNAIL_REQUESTED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "data": {
    "productId": "P-1001",
    "imageKey": "images/P-1001/original.jpg"
  }
}
~~~

| Trường | Vai trò | Quy tắc |
| --- | --- | --- |
| eventId | Idempotency key | Ổn định qua retries/requeues |
| eventType | Loại công việc | Allowlist; không chỉ suy theo queue key |
| schemaVersion | Phiên bản hợp đồng | Consumer từ chối version không hỗ trợ |
| occurredAt | Thời điểm yêu cầu trong domain | Không đồng nghĩa thời điểm Redis POP |
| productId | Business identity | Kiểm tra format/quyền tenant |
| imageKey | Tham chiếu object storage | Chỉ cho phép namespace/đường dẫn hợp lệ |

### 5.2. Redis List không có AMQP headers

Redis List value không tự có basic properties như messageId/correlationId/replyTo/contentType của AMQP. Nếu cần metadata xuyên hệ thống, đưa vào **payload envelope** hoặc thiết kế cơ chế serialize phù hợp.

Spring Integration có thể tạo MessageHeaders.ID và timestamp cho Spring Message **mới**, nhưng các trường đó **không thay thế eventId nghiệp vụ bền vững** khi task phải retry hoặc được worker khác nhận.

### 5.3. Thống nhất hướng push/pop và serializer

Nếu producer dùng StringRedisTemplate:

~~~java
stringRedisTemplate.opsForList()
    .leftPush("catalog:thumbnail:pending", json);
~~~

thì consumer phải đọc đúng Redis key và **byte encoding tương thích**. Với consumer BRPOP, mẫu LPUSH/BRPOP giữ FIFO. Với consumer BLPOP, dùng RPUSH/BLPOP nếu muốn FIFO.

**Không đoán phía pop chỉ từ tên class**: hãy kiểm tra implementation/API phiên bản Spring Integration Redis đang dùng và viết integration test thứ tự với ít nhất ba items trước khi chọn phía push.

### 5.4. JSON serializer so với Java object serialization

Tránh dùng native Java serialization làm hợp đồng trao đổi giữa các service hay với dữ liệu không tin cậy. Ưu tiên **JSON UTF-8/Avro/Protobuf** với schemaVersion, giới hạn kích thước và target type allowlist.

Nếu producer serialize JSON String bằng JSON serializer lần nữa, Redis List có thể chứa **JSON string literal** thay vì JSON object. Nếu converter/handler decode hai lần hoặc không thống nhất charset, event có thể lỗi mặc dù thao tác LPUSH thành công.

## 6. Dependencies và cấu hình Redis ConnectionFactory

Với Spring Boot và Spring Integration Redis, ví dụ dependencies:

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

Sử dụng **Spring Boot dependency management/BOM** để quản lý phiên bản Spring Data Redis, Spring Integration và Redis client tương thích. API ở các phiên bản có thể khác nhau; cần biên dịch với chính phiên bản đang dùng.

### 6.1. Spring Boot properties local/test

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 3s
      timeout: 3s
~~~

Đây là ví dụ môi trường local. Khi production cần xét TLS, ACL, Sentinel/Cluster, client pool/resources và timeouts theo hệ thống thực. Redis **không có vhost theo cách RabbitMQ tổ chức**; xác định đúng namespace/key prefix và quyền trên Redis instance.

Các thế hệ Spring Boot khác nhau có thể dùng tên property Redis khác nhau; kiểm tra tài liệu của version thực tế thay vì sao chép nguyên cấu hình khi upgrade.

### 6.2. RedisConnectionFactory không tự tiêu thụ queue

**RedisConnectionFactory** tạo kết nối Redis; nó chưa biết queue key nào cần nhận và chưa gọi service activator. Endpoint **RedisQueueMessageDrivenEndpoint** hoặc thành phần tự đọc List mới có trách nhiệm đọc queue rồi tạo Spring Message.

### 6.3. Phạm vi cấu hình transport

Khi Redis endpoint dùng một List key chung:

~~~text
Redis URL/host
  -> Authentication/ACL
  -> Key: catalog:thumbnail:pending
  -> List push/pop contract
  -> Payload bytes + serializer
  -> Spring Integration output MessageChannel
~~~

Chỉ đặt queue name đúng không đủ nếu publisher sử dụng Redis instance khác, database index khác, ACL khác hoặc serializer không tương thích.

## 7. Ví dụ publisher: LPUSH một thumbnail job

Producer gửi JSON vào một Redis List bằng **StringRedisTemplate**. Chọn producer **LPUSH** để minh họa consumer đọc theo hướng BRPOP.

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ThumbnailJobPublisher {

    public static final String PENDING_QUEUE =
        "catalog:thumbnail:pending";

    private final StringRedisTemplate redisTemplate;

    public ThumbnailJobPublisher(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public long enqueueJson(String json) {
        if (json == null || json.isBlank()) {
            throw new IllegalArgumentException(
                "Thumbnail job JSON must not be blank");
        }

        Long size = redisTemplate.opsForList()
            .leftPush(PENDING_QUEUE, json);

        if (size == null) {
            throw new IllegalStateException(
                "Redis did not return a queue length");
        }
        return size;
    }
}
~~~

**enqueueJson trả về chiều dài List sau LPUSH**, không phải số workers đã xử lý thành công. Thao tác Redis thành công cũng chưa chứng minh thumbnail tồn tại trong object storage.

### 7.1. Đẩy job bằng Redis CLI

Trên Redis **test**:

~~~bash
redis-cli LPUSH catalog:thumbnail:pending '{"eventId":"evt-thumb-1001","eventType":"THUMBNAIL_REQUESTED","schemaVersion":1,"data":{"productId":"P-1001","imageKey":"images/P-1001/original.jpg"}}'
redis-cli LLEN catalog:thumbnail:pending
~~~

Nếu một worker đang chạy, LLEN có thể trở lại **0 rất nhanh** vì item đã bị pop. **LLEN=0 không chứng minh job đã hoàn tất nghiệp vụ**.

### 7.2. Lỗi publisher và kết quả không rõ

Nếu network bị mất gần thời điểm LPUSH, producer có thể không biết Redis đã nhận giá trị hay chưa. Retry một LPUSH cùng JSON **có thể tạo hai List items cùng nội dung**.

Vì vậy producer phải cấp **eventId ổn định**, và consumer cần idempotency nếu side effect không được lặp. Không tạo eventId mới cho mỗi lần retry cùng một business task khi muốn deduplicate.

### 7.3. LPUSH không nguyên tử với DB commit

Nếu CatalogService lưu task metadata vào database rồi LPUSH:

~~~text
DB commit -> process crash -> LPUSH chưa diễn ra
~~~

job có thể không được enqueue. Nếu LPUSH trước commit rồi DB rollback, worker lại có thể chạy cho một record chưa có. Với yêu cầu giao nhận quan trọng, cân nhắc **transactional outbox** hoặc thiết kế một nguồn trạng thái bền vững có worker phát job sau commit, kết hợp idempotency.

## 8. Spring Integration Redis queue inbound endpoint

Trong những phiên bản Spring Integration Redis hỗ trợ API tương ứng, endpoint chuyên dụng thường là **RedisQueueMessageDrivenEndpoint**. Nó được cấu hình với **Redis queue key**, **RedisConnectionFactory** và **output channel**.

### 8.1. Tạo DirectChannel

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class ThumbnailQueueChannelConfig {

    @Bean
    public MessageChannel thumbnailInput() {
        return new DirectChannel();
    }
}
~~~

### 8.2. Đăng ký RedisQueueMessageDrivenEndpoint

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.integration.redis.inbound.RedisQueueMessageDrivenEndpoint;
import org.springframework.messaging.MessageChannel;

@Configuration
public class ThumbnailRedisQueueInboundConfig {

    @Bean
    public RedisQueueMessageDrivenEndpoint thumbnailRedisQueueInbound(
            RedisConnectionFactory connectionFactory,
            @Qualifier("thumbnailInput")
            MessageChannel thumbnailInput) {

        RedisQueueMessageDrivenEndpoint endpoint =
            new RedisQueueMessageDrivenEndpoint(
                ThumbnailJobPublisher.PENDING_QUEUE,
                connectionFactory);

        endpoint.setOutputChannel(thumbnailInput);
        return endpoint;
    }
}
~~~

**Lưu ý tính tương thích:** Đây là **mẫu cấu hình Java cho dòng API có RedisQueueMessageDrivenEndpoint và constructor tương ứng**. Tùy phiên bản, package/constructor/serializer/receive timeout hoặc tùy chọn DSL có thể thay đổi. Hãy xác minh bằng dependency thực tế trong project và biên dịch; nếu API khác, điều chỉnh theo version chứ không dùng reflection hay gọi setter tự đoán.

**Điểm quan trọng:** Cấu hình endpoint không tự cung cấp ACK/DLQ và không tự quản lý một processing list. Nếu implementation đọc bằng pop phá hủy thì business side effect có **cửa sổ mất việc sau pop** như mục 2; phải kiểm tra đường xử lý và nhu cầu reliability trước production.

### 8.3. Kiểm tra chiều đọc

Trong lab dùng LPUSH/BRPOP để FIFO. Không được khẳng định chỉ từ bean trên rằng mọi version của endpoint đều dùng đúng BRPOP, không có serializer mặc định khác nhau hoặc có cùng cấu hình blocking timeout. Hãy thử đẩy A, B, C vào queue test và quan sát thứ tự nhận; nếu endpoint dùng đầu ngược lại, **điều chỉnh phía producer** hoặc cấu hình endpoint theo API chính thức.

### 8.4. Không thêm poller vào endpoint message-driven

RedisQueueMessageDrivenEndpoint nhận dữ liệu bằng vòng đọc/đợi của nó. **Pollers.fixedDelay(...)** chỉ hợp lý khi dùng một **polled message source** hoặc một QueueChannel downstream cần consumer riêng; không thêm poller vào endpoint này với kỳ vọng tạo retry hoặc message persistence.

### 8.5. Một endpoint, một nhiệm vụ rõ ràng

Nếu nhiều Spring beans cùng đăng ký endpoint đọc **cùng một Redis List**, chúng trở thành **các competing consumers**. Điều đó có thể đúng khi cần chia công việc, nhưng không đúng khi bạn nghĩ mỗi bean sẽ nhận đầy đủ mọi item như Pub/Sub broadcast.

Đừng đồng thời dùng **RedisQueueMessageDrivenEndpoint** và một consumer thủ công BLPOP từ cùng queue trong integration test khi muốn kiểm tra riêng adapter chuyên dụng: hai consumer sẽ tranh nhau lấy dữ liệu, khiến kết quả không xác định.

## 9. Spring Integration flow: nhận payload, validate và gọi service

Endpoint queue inbound phát Spring Message vào **thumbnailInput**. Ta nối channel đó với một handler:

~~~mermaid
flowchart LR
    POP["Redis queue inbound"] --> CH["thumbnailInput<br/>DirectChannel"]
    CH --> V["PayloadDecoder"]
    V --> J["JSON parser + schema validation"]
    J --> H["ThumbnailJobHandler"]
    H --> B["Idempotent processing"]
~~~

### 9.1. Java DSL không ép kiểu trước khi biết serializer

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class ThumbnailQueueFlowConfiguration {

    @Bean
    public IntegrationFlow thumbnailQueueFlow(
            ThumbnailJobHandler thumbnailJobHandler) {

        return IntegrationFlow.from("thumbnailInput")
            .handle((payload, headers) -> {
                final String json;

                if (payload instanceof String) {
                    json = (String) payload;
                } else if (payload instanceof byte[]) {
                    json = new String(
                        (byte[]) payload, StandardCharsets.UTF_8);
                } else {
                    throw new IllegalArgumentException(
                        "Unsupported Redis queue payload type: "
                            + payload.getClass().getName());
                }

                thumbnailJobHandler.handle(json);
                return null;
            })
            .get();
    }
}
~~~

**Tại sao không mặc định payload String?** Redis List lưu bytes; adapter có thể dùng serializer riêng và phát String, byte[] hoặc dạng Message khác theo phiên bản/cấu hình. Mã này **chỉ chấp nhận hai kiểu đã nêu**; nếu adapter chuyên dụng phát một payload dạng object khác hoặc cố deserialize bằng một serializer không tương thích, cần chỉnh converter/serializer của endpoint và kiểm thử. Không lặng lẽ gọi toString() trên object không rõ loại.

Đoạn xử lý String/byte[] giúp nhận diện kiểu trong handler nhưng **không bảo đảm decoder UTF-8 strict**. Nếu hợp đồng cần phát hiện mọi chuỗi bytes UTF-8 sai, dùng CharsetDecoder với CodingErrorAction.REPORT hoặc validator tương đương.

### 9.2. Nếu default serializer không tương thích StringRedisTemplate

Không có quy luật rằng RedisQueueMessageDrivenEndpoint và StringRedisTemplate đang dùng **cùng serializer mặc định**. Có phiên bản/endpoint thiết kế nhận thông điệp do outbound adapter tương ứng serialize; có phiên bản cấu hình serializer riêng.

Nếu consumer test báo lỗi deserialize dù raw Redis List item là JSON đúng, phải kiểm tra:

1. **Giá trị bytes** thực tế mà producer LPUSH.
2. **RedisSerializer** mà inbound endpoint đang sử dụng.
3. Endpoint có chờ một **Spring Message** serialized hay chỉ chờ payload text/binary?
4. Đầu pop **LEFT hay RIGHT** của implementation?
5. Có đặt serializer cùng hợp đồng ở cả inbound/outbound hay chưa?

Chỉ tiếp tục khi producer–consumer **đã qua contract test**. Đừng “sửa” bằng cách cố parse Java serialized bytes như UTF-8.

### 9.3. Có thể chia thành transformer và service activator

Trong flow production, nên tách:

~~~text
thumbnailInput
  -> PayloadDecoder (bytes/String -> JSON text)
  -> JsonToThumbnailJob transformer (JSON -> DTO)
  -> BeanValidation/SchemaValidator
  -> ThumbnailJobHandler
~~~

Ưu điểm: mỗi bước có lỗi cụ thể để log/cách ly, dễ unit test và không khiến business handler phụ thuộc vào kiểu payload low-level.

### 9.4. Handler return không phải ACK Redis List

Một khi item đã bị pop khỏi Redis List, việc service activator return thành công **không gửi một Redis ACK đặc biệt** cho item đó. Với List pop trực tiếp, Redis đã thay đổi trạng thái queue **trước** khi handler chạy. Nếu handler ném exception, cũng không có tự động NACK/requeue từ Redis theo mẫu này.

## 10. Model, validation và business handler

Một thumbnail job nên có eventId ổn định và schemaVersion, không để Redis queue key quyết định mọi ý nghĩa nghiệp vụ.

### 10.1. DTO và parser

~~~java
public record ThumbnailJob(
        String eventId,
        String eventType,
        int schemaVersion,
        Data data) {

    public record Data(
            String productId,
            String imageKey) {
    }
}
~~~

~~~java
public class InvalidThumbnailJobException
        extends RuntimeException {

    public InvalidThumbnailJobException(String message) {
        super(message);
    }

    public InvalidThumbnailJobException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

### 10.2. ThumbnailJobHandler

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

@Service
public class ThumbnailJobHandler {

    private final ObjectMapper objectMapper;
    private final ThumbnailProcessingService processingService;

    public ThumbnailJobHandler(
            ObjectMapper objectMapper,
            ThumbnailProcessingService processingService) {
        this.objectMapper = objectMapper;
        this.processingService = processingService;
    }

    public void handle(String json) {
        if (json == null || json.length() > 16_384) {
            throw new InvalidThumbnailJobException(
                "Thumbnail task is missing or too large");
        }

        final ThumbnailJob job;
        try {
            job = objectMapper.readValue(json, ThumbnailJob.class);
        } catch (JsonProcessingException ex) {
            throw new InvalidThumbnailJobException(
                "Malformed task JSON", ex);
        }

        if (job == null
                || job.eventId() == null
                || !job.eventId().matches("[A-Za-z0-9_-]{1,80}")
                || !"THUMBNAIL_REQUESTED".equals(job.eventType())
                || job.schemaVersion() != 1
                || job.data() == null
                || job.data().productId() == null
                || !job.data().productId()
                    .matches("[A-Za-z0-9_-]{1,80}")
                || job.data().imageKey() == null
                || !job.data().imageKey().startsWith("images/")) {

            throw new InvalidThumbnailJobException(
                "Unsupported thumbnail task contract");
        }

        processingService.process(job);
    }
}
~~~

~~~java
public interface ThumbnailProcessingService {
    void process(ThumbnailJob job);
}
~~~

**ThumbnailProcessingService là interface** cần tự triển khai (ImageMagick, Java image library, object storage, database hoặc worker API). Ví dụ chưa khởi tạo object storage/client và không giả định toàn bộ các side effects thuộc một transaction.

### 10.3. Validation của imageKey là chưa đủ cho production

Kiểm tra startsWith("images/") chỉ là ví dụ nhỏ. Nếu imageKey trở thành đường dẫn filesystem hoặc object storage:

- Không dùng raw key để mở file local mà không kiểm tra path traversal.
- Kiểm tra tenant/owner của sản phẩm.
- Whitelist bucket/prefix/content type.
- Giới hạn kích thước ảnh, pixel dimensions và thời gian xử lý.
- Không thực thi shell command bằng string concatenation từ input.

Một Redis List key nội bộ vẫn có thể nhận dữ liệu sai hoặc độc hại nếu producer khác có quyền ghi.

### 10.4. Jackson, Spring bean và transaction

ObjectMapper phải được cung cấp qua Spring configuration (ví dụ Spring Boot JSON auto-configuration hoặc bean tự khai báo). Khi cập nhật DB trong ThumbnailProcessingService, hãy dùng **@Transactional tại service bean được Spring proxy** nếu database transaction cần thiết.

**Transaction database không bao phủ thao tác Redis pop đã xảy ra trước đó.** Nếu service ném exception/rollback, item đã pop không tự xuất hiện lại trong pending queue.

### 10.5. Idempotency trước side effect

Nếu producer LPUSH cùng eventId hai lần hoặc reclaimer đưa task về queue sau một sự cố, processingService có thể gặp duplicate. Một mô hình có thể dùng:

~~~text
thumbnail_jobs
  event_id VARCHAR PRIMARY KEY
  product_id VARCHAR
  state VARCHAR  -- NEW / PROCESSING / DONE / FAILED
  output_key VARCHAR
  updated_at TIMESTAMP
~~~

Kết hợp:

- Unique constraint trên eventId.
- Idempotent output object key, ví dụ derived từ productId + image version.
- Trạng thái xử lý và khả năng reconcile.
- Nếu task đã DONE, không tạo side effect mới; trả kết quả idempotent.

Tránh phương pháp “SELECT xem eventId chưa tồn tại rồi INSERT” thiếu unique constraint vì nhiều workers có thể race.

## 11. Test nhanh bằng Redis CLI: FIFO và destructive POP

Trong Redis **test**:

~~~bash
redis-cli DEL test:thumbnail:pending
redis-cli LPUSH test:thumbnail:pending task-A
redis-cli LPUSH test:thumbnail:pending task-B
redis-cli LPUSH test:thumbnail:pending task-C
redis-cli LLEN test:thumbnail:pending
redis-cli BRPOP test:thumbnail:pending 1
redis-cli BRPOP test:thumbnail:pending 1
redis-cli BRPOP test:thumbnail:pending 1
redis-cli LLEN test:thumbnail:pending
~~~

Kỳ vọng logic:

~~~text
Trước pop: LLEN = 3
Lần 1: task-A
Lần 2: task-B
Lần 3: task-C
Sau pop: LLEN = 0
~~~

**Chỉ dùng lệnh DEL ở queue test được phép xóa.** Không chạy trên key production chứa công việc thật.

Nếu bỏ Redis queue inbound adapter vào cùng queue test và nó đang chạy, adapter có thể pop cạnh tranh với Redis CLI, khiến kết quả không xác định. Khi test chiều pop của endpoint, dùng một queue test riêng và chỉ có một consumer theo đúng kịch bản.

### 11.1. Test Redis với một worker offline

1. Dừng endpoint nhận queue trước khi producer LPUSH.
2. Đẩy hai tasks vào Redis List.
3. Kiểm tra LLEN=2 khi không có consumer khác.
4. Khởi động endpoint nhận.
5. Quan sát tasks tới MessageChannel/handler.

Nếu Redis lưu dữ liệu List theo cấu hình hạ tầng và chưa bị ai pop, các items vẫn nằm trong List khi worker chưa chạy. Đây là ưu điểm của List queue so với Redis Pub/Sub notification.

### 11.2. Test crash sau POP

1. Cho consumer pop một task.
2. Chủ động dừng tiến trình trước khi handler hoàn tất.
3. Quan sát **pending List có thể không còn task**.
4. Khởi động lại consumer và xác minh **không tự nhận lại** task đó từ pending List.

Đây là phép thử thiết yếu để hiểu độ tin cậy. Nếu cần tránh mất job sau pop, hãy dùng mẫu **processing list** hoặc Redis Streams ở các mục sau, không chỉ thêm Redis AOF/RDB.

## 12. Cửa sổ mất dữ liệu của destructive POP

Một flow Redis List queue trực tiếp thường có chuỗi:

~~~text
Producer LPUSH job
  -> Redis List giữ job
  -> Consumer BRPOP xóa job khỏi List
  -> Adapter tạo Spring Message
  -> DirectChannel gọi handler
  -> Handler thực hiện side effect
  -> Business commit
~~~

**Redis đã loại job khỏi pending List trước khi mốc business commit**. Dù DirectChannel đồng bộ, lệnh POP vẫn là một sự kiện riêng, không nằm cùng transaction với database hoặc object storage.

### 12.1. Ma trận thời điểm lỗi

| Điểm xảy ra lỗi | Trạng thái Redis pending List | Trạng thái nghiệp vụ | Rủi ro |
| --- | --- | --- | --- |
| Trước LPUSH | Chưa có job | Chưa xử lý | Producer phải retry/outbox |
| LPUSH đã thành công, chưa POP | Có job nếu Redis giữ state | Chưa xử lý | Worker có thể nhận sau |
| POP đã xong, chưa tạo Spring Message | Không còn job | Chưa xử lý | **Mất task** |
| Đã gửi vào DirectChannel, handler chưa xong | Không còn job | Không chắc | **Mất task nếu crash** |
| Database rollback sau POP | Không còn job | Chưa commit | **Không có broker redelivery** |
| Database commit, trước khi log success | Không còn job | Đã commit | Khó quan sát kết quả; producer retry có thể tạo duplicate |
| Producer LPUSH lại cùng eventId | Có thể thêm item thứ hai | Có thể đã xử lý | Cần idempotent consumer |

**Redis persistence không giải quyết trường hợp POP rồi business rollback**: Redis không có thông tin về business transaction khác. Spring @Transactional ở service activator cũng không tự rollback Redis POP.

### 12.2. “Bật AOF” có đủ không?

RDB/AOF và replication giúp Redis phục hồi **trạng thái dữ liệu Redis** trong những điều kiện cấu hình nhất định. Chúng không tự giữ lại phần tử sau khi **BRPOP đã xóa thành công**.

Ngoài ra, Redis persistence/replication có các mức bảo đảm khác nhau khi crash hoặc failover. Không khẳng định LPUSH chắc chắn đã bền trên mọi node chỉ vì Redis trả thành công; cần đánh giá cấu hình AOF/fsync, replication/failover và yêu cầu RPO/RTO của hệ thống thực.

### 12.3. Có thể retry handler ngay trong listener không?

Có. Một RetryTemplate hoặc retry advice có thể thử lại thao tác database/API vài lần **sau khi POP**, nếu process vẫn sống. Điều này giảm lỗi transient ngắn, nhưng:

- Không phục hồi được task sau process crash.
- Không ngăn producer publish duplicate.
- Có thể giữ thread nhận lâu, khiến throughput giảm.
- Nếu payload sai cố định, retry nóng không có tác dụng.

**Retry trong process khác với Redis redelivery bền vững.** Dù retry đủ 3 attempts và cuối cùng fail, item vẫn không tự trở lại pending List.

### 12.4. ErrorChannel có lưu lại item không?

Spring Integration errorChannel có thể định tuyến **ErrorMessage** khi một endpoint/flow có hỗ trợ và được cấu hình. Nhưng nó **không tự tạo một Redis ACK/NACK** cho item đã POP, cũng không tự đưa item trở lại List.

Nếu muốn sau lỗi có thể replay, phải thiết kế nơi lưu payload/job metadata bền vững và một chính sách chuyển trách nhiệm rõ. Khi dùng error flow để republish vào Redis List, phải xét **duplicate, mất kết quả publish và recursion/retry vô hạn**.

## 13. Reliable queue với processing List: nguyên lý

Muốn tránh cửa sổ “POP xong thì không còn bản sao chờ phục hồi”, một mẫu phổ biến dùng **hai Redis Lists**:

~~~text
catalog:{thumbnail}:ready
catalog:{thumbnail}:processing
~~~

Ta chuyển job từ ready sang processing **trong một thao tác Redis nguyên tử**, thay vì xóa hẳn khỏi Redis:

~~~mermaid
flowchart LR
    PUB["Producer"] -->|"LPUSH"| Q["ready List"]
    Q -->|"BLMOVE RIGHT LEFT"| W["processing List"]
    W --> H["Worker process"]
    H -->|"Commit + ACK via LREM"| DONE["Done"]
    W -->|"Worker crash / timeout"| RC["Reclaimer"]
    RC -->|"Requeue có kiểm soát"| Q
~~~

### 13.1. Redis BLMOVE

Trên phiên bản Redis hỗ trợ **BLMOVE**:

~~~redis
BLMOVE catalog:{thumbnail}:ready catalog:{thumbnail}:processing RIGHT LEFT 2
~~~

Lệnh này **chờ** một phần tử từ bên phải của ready List, rồi **chuyển** sang bên trái của processing List trong cùng thao tác Redis. Giá trị được trả về cho worker để xử lý.

Nếu timeout mà không có item, client có thể nhận kết quả rỗng; điều đó không phải một business failure. Nếu kết nối bị lỗi, cần xác định job đã được chuyển sang processing hay chưa trước khi suy đoán an toàn.

### 13.2. ACK nghiệp vụ bằng cách xóa khỏi processing

Sau khi xử lý và commit xong:

~~~redis
LREM catalog:{thumbnail}:processing 1 job-payload
~~~

Đây là **ACK do ứng dụng tự thiết kế**, không phải ACK/consumer group native của Redis List. Phải chắc phần tử bị xóa là **đúng job**. Với payload trùng từng byte, LREM có thể xóa một phần tử khớp chứ không biết “job của worker nào”; nên dùng task ID duy nhất/khung payload và ownership phù hợp.

**LREM là thao tác sau commit**, không được đặt trước side effect quan trọng. Nếu xóa trước rồi crash, lại mất khả năng recovery như POP trực tiếp.

### 13.3. Sau commit mà crash trước LREM thì sao?

~~~text
BLMOVE ready -> processing
  -> DB commit / thumbnail created
  -> process crash trước LREM
  -> processing List còn job
  -> reclaimer đưa job trở lại ready
  -> worker xử lý lại
~~~

Đây là **at-least-once ở mức ứng dụng nếu hệ thống reclaimer hoạt động đúng và dữ liệu Redis được giữ**, không phải exactly-once. Cần idempotency, ví dụ eventId unique, output key deterministic, business state machine.

### 13.4. Đừng giả định RedisQueueMessageDrivenEndpoint mặc định dùng BLMOVE

**Endpoint queue inbound chuyên dụng ở mục 8 không được tự động coi là reliable queue hai Lists.** Nếu bạn chuyển sang thiết kế BLMOVE/processing List, phải xây một nguồn nhận/endpoint phù hợp với **BLMOVE** hoặc dùng một thành phần/framework thực sự hỗ trợ giao thức hai giai đoạn đó.

Đừng dùng cả RedisQueueMessageDrivenEndpoint pop từ ready **và** BLMOVE worker từ ready trên cùng queue rồi cho rằng mọi job sẽ có processing tracking. Endpoint pop trực tiếp sẽ lấy một số jobs mà không qua processing List, phá vỡ reliability contract.

### 13.5. Redis Cluster và hash slot

BLMOVE/LMOVE là thao tác **đa key**. Trong Redis Cluster, các key liên quan phải đáp ứng yêu cầu **cùng hash slot**. Cách đặt tên:

~~~text
catalog:{thumbnail}:ready
catalog:{thumbnail}:processing
catalog:{thumbnail}:dead
~~~

Phần trong cặp ngoặc nhọn là **hash tag** để những key này cùng slot theo cơ chế Redis Cluster. Không chọn hai keys đặt ở slots khác nhau rồi kỳ vọng một lệnh BLMOVE cross-slot vẫn chạy.

### 13.6. BRPOPLPUSH và các phiên bản Redis

Các tài liệu cũ có thể dùng **BRPOPLPUSH** (move từ right của source sang left của destination trong một lệnh blocking). Các phiên bản Redis mới cung cấp **BLMOVE** với lựa chọn đầu nguồn/đích rõ hơn; khi bảo trì một hệ thống hiện có, cần xác minh phiên bản Redis server/client và trạng thái deprecated của lệnh cũ trước khi quyết định migration.

## 14. Reliable processing cần reclaimer và lease, không chỉ BLMOVE

Processing List giữ lại job sau worker crash, nhưng Redis không tự quyết định **khi nào job “mắc kẹt” cần được nhận lại**.

### 14.1. Reclaimer có trách nhiệm gì?

- Theo dõi job nào đã được claim từ ready.
- Lưu/tra cứu thời điểm claim hoặc last heartbeat.
- Xác định owner/worker còn sống hay không.
- Khi lease hết hạn, đưa job trở lại ready hoặc final dead queue **có kiểm soát**.
- Không requeue job đang chạy hợp lệ nhưng lâu hơn ước lượng bình thường.
- Giới hạn số lần attempt; phân loại lỗi cố định và lỗi có thể hồi phục.

Một List các JSON payload **không tự chứa thời điểm claim và owner** nếu ứng dụng không thêm metadata. Có thể cần hash/job table/sorted set để theo dõi leases và deadlines; thiết kế cập nhật metadata phải nhất quán với thao tác claim.

### 14.2. Một lỗi phổ biến khi reclaimer hoạt động quá sớm

~~~mermaid
sequenceDiagram
    participant W1 as Worker 1
    participant R as Redis
    participant RC as Reclaimer
    participant W2 as Worker 2
    W1->>R: Claim task-10 (processing)
    W1->>W1: Image processing lâu hơn lease
    RC->>R: Lease expired -> requeue
    W2->>R: Claim task-10
    W2->>W2: Process task-10
    W1->>W1: Finish task-10
    Note over W1,W2: Hai worker có thể cùng xử lý side effect
~~~

Giải pháp cần phối hợp:

1. **Heartbeat/lease extension** khi xử lý lâu.
2. **Fencing token/version** nếu side effect dễ bị xử lý bởi owner cũ.
3. **Idempotent output** theo eventId/productId/imageVersion.
4. **Kiểm tra owner** khi ACK hoặc đổi trạng thái.
5. Deadline/timeout hợp lý, không đơn giản requeue mọi item sau một khoảng cố định.

### 14.3. Hai thao tác Redis rời nhau có cửa sổ race

Ví dụ worker:

~~~text
BLMOVE ready -> processing
HSET task:{id} owner=worker-1 claimedAt=...
~~~

Nếu process crash **giữa hai thao tác**, processing List có job nhưng hash metadata chưa được ghi. Nếu reclaimer chỉ quét hash, job có thể bị bỏ quên.

Để làm reliable queue nghiêm ngặt, cần cân nhắc **Lua scripting/transactions phù hợp, dữ liệu job registry có thể reconcile**, hoặc chọn Redis Streams consumer group để không tự xây toàn bộ cơ chế claim/ACK/reclaim. **BLMOVE nguyên tử chỉ bảo đảm bước move; không làm toàn bộ workflow nguyên tử**.

### 14.4. Requeue và dead-letter không thể dựa vào tên key

Redis Lists không có native DLX như RabbitMQ. Muốn giữ job lỗi trong **catalog:{thumbnail}:dead**, ứng dụng cần tự thực hiện việc chuyển và ghi lý do lỗi.

Nếu xử lý theo processing List, phải **chuyển đúng job** từ processing sang dead/ready, không dùng một lệnh LMOVE mù quáng có thể lấy nhầm phần tử của worker khác.

### 14.5. Mẫu Lua chuyển item lỗi sang dead List

Ví dụ ý tưởng: chỉ di chuyển một payload cụ thể, khi payload đã có định danh duy nhất trong processing List.

~~~lua
-- KEYS[1]: processing list
-- KEYS[2]: dead list
-- ARGV[1]: serialized job payload, unique for the claimed job

local removed = redis.call('LREM', KEYS[1], 1, ARGV[1])
if removed == 1 then
    redis.call('LPUSH', KEYS[2], ARGV[1])
end
return removed
~~~

Script chạy nguyên tử đối với các Redis operations khác trên server/shard liên quan, giúp tránh khoảng trống riêng giữa LREM và LPUSH. Tuy nhiên nó **chưa** thực hiện kiểm tra lease owner/attempt count, không xử lý payload trùng hoàn toàn một cách phân biệt worker và không tự bảo đảm lưu bền qua mọi chế độ Redis crash/failover. Production cần policy ownership và đối soát toàn bộ state.

Trong Redis Cluster, các keys của một script nhiều key cũng cần nằm trong cùng hash slot.

### 14.6. Kết luận về reliable List queue

Để từ List queue đơn giản lên reliable work queue, bạn phải tự quản lý **claim, processing, ACK, timeout, reclaimer, duplicate, poison message, dead-letter và monitoring**. Đây có thể là lựa chọn hợp lý với hệ thống nhỏ có tiêu chuẩn rõ, nhưng độ phức tạp tăng đáng kể.

Nếu đã cần đủ những tính năng trên, hãy đánh giá **Redis Streams, RabbitMQ/AMQP, Kafka hoặc JMS** trước khi tự duy trì một giao thức queue tùy biến.

## 15. Retry, poison job và final error state

Một task có thể không được xử lý vì **lỗi dữ liệu cố định** hoặc **lỗi hạ tầng tạm thời**. Retry policy cần phân biệt hai nhóm đó trước khi dùng Redis queue làm nơi chứa công việc.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Malformed payload** | JSON hỏng, thiếu eventId, sai schemaVersion | Không retry nóng; cách ly payload/metadata để điều tra |
| **Business validation** | productId không tồn tại, imageKey sai quyền | Ghi trạng thái từ chối theo contract; có thể cần sửa dữ liệu |
| **Transient dependency** | Object storage trả 503, DB connection timeout | Retry có giới hạn và backoff, sau đó durable retry |
| **Quota/rate limit** | Dịch vụ resize chạm concurrency hoặc bandwidth limit | Backpressure, delay, hạn mức worker |
| **Unknown outcome** | Đứt mạng gần lúc object storage hoàn tất ghi | Đối soát bằng deterministic output key, không mặc định thất bại |
| **Poison task** | Payload luôn gây exception | Final dead list/error table sau khi phân loại |
| **Permanent configuration** | Sai credentials/bucket, thiếu quyền | Cảnh báo và sửa cấu hình, không loop retry vô hạn |

### 15.1. Retry trong service activator có giới hạn

Với lỗi transient ngắn, có thể dùng Spring Retry tại ranh giới xử lý:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.retry.support.RetryTemplateBuilder;

@Configuration
public class ThumbnailRetryConfig {

    @Bean
    public RetryTemplate thumbnailRetryTemplate() {
        return new RetryTemplateBuilder()
            .maxAttempts(3)
            .exponentialBackoff(250L, 2.0, 2000L)
            .retryOn(TransientThumbnailException.class)
            .build();
    }
}
~~~

~~~java
public class TransientThumbnailException extends RuntimeException {
    public TransientThumbnailException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Trong handler/flow có thể gọi:

~~~java
thumbnailRetryTemplate.execute(context -> {
    thumbnailJobHandler.handle(json);
    return null;
});
~~~

**maxAttempts(3)** thường gồm lần chạy đầu và tối đa hai lần retry. Chỉ retry những exception được phân loại là transient; **không dùng retryOn(RuntimeException.class)** nếu nó có thể lặp lại dữ liệu invalid hàng nghìn lần.

### 15.2. Vì sao retry này chưa bảo đảm phục hồi?

RetryTemplate chạy trong JVM, sau khi queue inbound endpoint đã pop job. Nếu JVM chết ở attempt 2, trạng thái retry cục bộ mất. Redis List pending cũng đã mất job ở chế độ direct POP.

Muốn retry sau restart, cần **một bản job còn ở nguồn lưu bền** (processing List, Stream, database task table...) và một component có trách nhiệm nhận lại theo policy.

### 15.3. Không tự requeue vô hạn vào chính List

Một cách xử lý sai thường gặp:

~~~text
catch (Exception ex) {
    redisTemplate.opsForList().leftPush(pendingKey, sameJson);
}
~~~

Nếu task sai schema, queue nhận lại chính task đó ngay lập tức; consumer có thể tạo **hot loop** tốn CPU, memory, Redis traffic và log. Ngoài ra, **LPUSH lại** là một publish mới vào List, không phải transaction đảo ngược POP nguyên tử với business transaction.

Nếu retry có giới hạn, cần attempt counter bền vững, backoff/nextAttemptAt, và nơi giữ task lỗi cuối cùng.

### 15.4. Thiết kế dead list/error table

Redis List không có một **dead-letter exchange** native như RabbitMQ. Có thể thiết kế:

~~~text
catalog:{thumbnail}:ready
catalog:{thumbnail}:processing
catalog:{thumbnail}:dead
~~~

Một dead job nên kèm metadata:

~~~json
{
  "eventId": "evt-thumb-1001",
  "attempts": 4,
  "errorCategory": "IMAGE_UNSUPPORTED_FORMAT",
  "lastErrorAt": "2026-11-23T03:00:00Z",
  "originalPayload": {
    "eventType": "THUMBNAIL_REQUESTED",
    "schemaVersion": 1
  }
}
~~~

Các trường attempts/errorCategory trong ví dụ là **hợp đồng ứng dụng tự lưu**, không do Redis List tự tạo. Nếu cần sửa payload trước replay, phải lưu audit và xác định eventId có giữ nguyên hay không theo hợp đồng idempotency.

### 15.5. Delayed retry không tự có ở List

Redis List không có timeout **cho từng phần tử để tự chuyển sang ready**. Có thể dùng một Redis Sorted Set chứa score nextRetryAt, scheduler quét due jobs rồi chuyển vào ready, hoặc dùng một durable job table/Redis Streams phù hợp.

Khi scheduler đọc và move từ delayed sang ready, cần đảm bảo **không mất job giữa hai thao tác** và **không publish trùng ngoài chính sách**. Có thể phải dùng Lua script/transaction, unique job IDs, trạng thái bền vững và idempotency.

### 15.6. Khi xử lý lỗi phải chọn một chủ sở hữu

Một item đã pop trực tiếp sẽ không còn trong ready List. Đừng để **Spring Integration error flow**, **handler catch**, **task retry scheduler** và **operator replay** cùng tự LPUSH lại mà không có cơ chế trạng thái chung, vì một lỗi duy nhất có thể tạo nhiều bản task.

Nên xác định:

- Ai ghi trạng thái thất bại?
- Ai được phép tạo lượt retry mới?
- Khi nào retry budget hết?
- Ai xác nhận task đã DONE?
- Ai có quyền replay dead jobs?
- Khi kết quả không rõ, đối soát ở đâu trước khi thử lại?

## 16. Concurrency, competing consumers và thứ tự FIFO

Một Redis List key có thể được nhiều consumers đọc. Mỗi thao tác Redis POP là nguyên tử ở mức Redis command, nên **cùng một List element không bị hai consumers pop thành công đồng thời**. Nhưng điều đó không bảo đảm business side effect được thực thi chính xác một lần.

~~~mermaid
flowchart TD
    P["LPUSH tasks A/B/C/D"] --> Q["Redis List ready"]
    Q -->|"POP"| W1["Worker 1"]
    Q -->|"POP"| W2["Worker 2"]
    Q -->|"POP"| W3["Worker 3"]
    W1 --> H1["Process A"]
    W2 --> H2["Process B"]
    W3 --> H3["Process C"]
~~~

### 16.1. Một key, nhiều worker

Các workers chia nhau các List items theo thời điểm Redis thực hiện POP. Không có khái niệm mỗi worker đều nhận toàn bộ nội dung một List như Pub/Sub.

Nếu Warehouse và Analytics **đều** cần một event, không dùng hai consumers cùng List với kỳ vọng broadcast. Tạo hai queue/list riêng, một event log có nhiều consumer groups, hoặc một exchange/broker hỗ trợ fan-out theo yêu cầu.

### 16.2. Thứ tự xử lý trong cluster

Ngay cả khi queue FIFO ở mức pop:

- Worker 1 có thể xử lý task A lâu hơn Worker 2 xử lý B.
- Một worker crash khiến task A phải recovery, trong lúc B đã DONE.
- Retry và reclaimer có thể đưa item cũ về cuối/đầu queue khác nhau.
- Object storage/DB có thể hoàn tất request lệch thứ tự.

Nếu một productId có nhiều phiên bản ảnh, cần **version/token monotonic** để output cũ không ghi đè output mới. Một Redis List đơn giản không bảo đảm causal ordering ở business state.

### 16.3. Năng lực xử lý không chỉ do Redis throughput

Ví dụ ba workers, mỗi task resize mất hai giây:

~~~text
3 workers / 2 giây mỗi task ≈ 1,5 task/giây
~~~

Đây là ước lượng lý tưởng nếu workers chạy song song và không có giới hạn tài nguyên. Redis có thể pop rất nhanh nhưng object storage, CPU ảnh, memory hoặc DB có thể mới là bottleneck. Tăng số consumers không giúp nếu hệ thống đích đã bão hòa.

### 16.4. Không có prefetch giống RabbitMQ

Redis List blocking pop **không tự có prefetchCount/consumer ACK** như Spring AMQP listener container. Số task **in-flight** phụ thuộc số loops/threads nhận, nơi đặt queue nội bộ, executor và worker concurrency.

Nếu dùng ExecutorChannel và worker queue không giới hạn, endpoint có thể pop task rất nhanh và chất đống tác vụ chưa hoàn tất trong memory. Redis ready LLEN giảm nhưng nguy cơ mất jobs khi crash tăng. **LLEN thấp không tự chứng minh hệ thống theo kịp hoặc đã xử lý xong**.

### 16.5. DirectChannel, ExecutorChannel, QueueChannel

| Channel | Thời điểm xử lý | Rủi ro với Redis POP |
| --- | --- | --- |
| **DirectChannel** | Handler đồng bộ trong flow | Ít đệm trong memory nhưng vẫn mất item nếu crash sau POP |
| **ExecutorChannel** | Gửi sang executor thread/queue | POP có thể hoàn tất khi task còn trong memory; crash làm mất |
| **QueueChannel** | Đệm Spring Messages để poller nội bộ đọc | Không tự bền vững nếu không dùng MessageStore và vẫn có gap trước khi lưu |
| **PublishSubscribeChannel** | Fan-out nội bộ tới nhiều subscribers | Một Redis job có thể tạo nhiều side effects; không thay consumer group |

**Spring Integration poller trên QueueChannel** chỉ tiêu thụ những Spring Messages đã được đệm; nó không biến Redis List inbound adapter thành durable queue có ACK.

## 17. ErrorChannel và transaction boundaries

Một exception có thể xuất hiện ở những bước khác nhau:

~~~mermaid
flowchart TD
    R["Redis List POP"] --> A["Redis queue inbound adapter"]
    A --> M["Spring Message"]
    M --> C["MessageChannel"]
    C --> T["Transformer / parse"]
    T --> H["Business handler"]
    R -. "Network / Redis WRONGTYPE" .-> E1["Transport / endpoint errors"]
    A -. "Serializer failure" .-> E1
    T -. "Malformed payload" .-> E2["Spring Integration error handling"]
    H -. "DB / object store error" .-> E2
    E1 --> REC["Observe / reconcile"]
    E2 --> REC
~~~

### 17.1. Lỗi trước khi tạo Spring Message

Nếu Redis connection lỗi hoặc serializer không giải mã được item trước khi adapter tạo Spring Message, **service activator có thể chưa được gọi**. Handler try/catch không thể bắt được mọi lỗi của transport.

Cần cấu hình/giám sát error handling của endpoint theo phiên bản Spring Integration, đồng thời ghi log key name, serializer, error category và Redis connectivity theo chính sách bảo mật.

### 17.2. Lỗi trong handler không tự PUT BACK

Nếu DirectChannel gọi handler, handler ném RuntimeException và errorChannel ghi log, item đã được pop **không tự quay về ready**. Ngay cả khi exception được propagate tới endpoint, List không có lệnh NACK theo eventId.

Đừng hiểu việc thấy Spring ErrorMessage là bằng chứng Redis đã giữ lại bản sao của task.

### 17.3. Ranh giới database transaction

~~~text
Redis List POP  (transaction Redis riêng)
   -> Spring Message
   -> @Transactional business method
   -> DB commit/rollback
~~~

Spring @Transactional của DB không tự rollback lệnh POP của Redis, và Redis MULTI/EXEC không biến việc resize ảnh/object storage/JDBC thành transaction nguyên tử toàn hệ thống.

Nếu side effect qua nhiều hệ thống, cần outbox/inbox, state machine, idempotency key, reconciliation hoặc bù trừ phù hợp.

### 17.4. Exactly-once có thể đạt trong phạm vi nào?

Có thể cố gắng tạo **effectively-once side effect** cho một record database bằng unique constraint trên eventId trong một transaction. Tuy nhiên:

- Điều đó không tự khôi phục task đã mất sau direct POP.
- Object storage/API ngoài DB có thể có kết quả UNKNOWN sau timeout.
- Reclaimer/producer retry có thể tạo duplicate deliveries.
- Redis List không cấp exactly-once end-to-end guarantee.

**Chính xác hơn:** Redis List direct POP cho phép một consumer lấy item một lần theo thao tác Redis, còn business correctness cần cơ chế riêng.

### 17.5. Durable inbox sau POP có giải quyết mọi vấn đề không?

Một consumer có thể POP rồi ghi job vào database inbox trước khi làm business:

~~~text
POP Redis List
   -> DB insert inbox
   -> ACK ở tầng DB / worker đọc inbox
~~~

Mô hình này bảo vệ jobs **sau khi đã insert thành công vào inbox**, nhưng vẫn có khoảng **POP → DB insert** nơi process crash có thể làm mất item. Nếu SLA không cho phép mất job, phải thay điểm claim bằng cơ chế giữ bản sao ở Redis (processing List/Streams), hoặc khiến producer ghi trực tiếp vào nguồn bền vững được worker đọc.

## 18. Vòng đời endpoint, Redis downtime và graceful shutdown

Redis queue inbound adapter hoạt động theo lifecycle của Spring Integration và Redis client. Cần xác định:

1. Khi application start, endpoint có auto-start cùng context không?
2. Redis chưa sẵn sàng thì endpoint retry kết nối ra sao?
3. Khi lệnh blocking POP đang chờ, stop có hủy/thoát được trong thời gian hợp lý không?
4. Khi Redis failover, connection được tái lập và loop nhận chạy tiếp không?
5. Nếu một item đã POP trước shutdown, handler đang ở trạng thái nào?

### 18.1. Worker offline và Redis List backlog

Nếu worker offline **trước khi POP**, producer vẫn có thể LPUSH items vào Redis List (miễn Redis đang sẵn và chính sách lưu trữ/eviction cho phép). Khi worker online lại, nó có thể tiếp tục lấy items chưa pop.

Khác Redis Pub/Sub, queue List có **backlog**. Nhưng backlog có giới hạn bởi memory, maxmemory/eviction policy, persistence/replication và vận hành. Đừng coi Redis List là nơi lưu vô hạn theo mặc định.

### 18.2. Redis reconnect không đồng nghĩa job được xử lý an toàn

Sau reconnect, endpoint có thể đọc những items **còn trong ready List**. Những items đã pop trước khi JVM chết sẽ không tự xuất hiện lại nếu bạn chưa có processing List/reclaimer hoặc nguồn khác để recover.

### 18.3. Graceful shutdown

Một kế hoạch phù hợp:

- Ngừng nhận/claim job mới theo lifecycle endpoint.
- Cho handlers đang chạy hoàn tất trong timeout có kiểm soát.
- Với reliable processing, ghi nhận trạng thái DONE và ACK/delete processing item sau business commit.
- Nếu timeout, để lease/reclaimer có thể xử lý lại theo eventId và ownership.
- Đóng resources theo lifecycle Spring, không tự phá RedisConnectionFactory dùng chung.
- Sau restart, kiểm tra ready backlog, processing stuck jobs và retry scheduler.

**Không tuyên bố stop() thành công đồng nghĩa không có task thất lạc.** Phải đo trạng thái in-flight và đường recovery.

### 18.4. WRONGTYPE khi queue key bị ghi nhầm

Redis key đang dùng làm List có thể bị một client khác SET thành String hoặc ghi cấu trúc dữ liệu không tương thích. Khi đó các lệnh List có thể báo **WRONGTYPE**. Redis queue inbound endpoint không thể tự sửa schema key.

Đặt namespace rõ, hạn chế ACL/write permissions, không reuse key name cho cache text hoặc set. Trong môi trường test có thể kiểm tra **TYPE key** trước khi chạy, nhưng production không nên tự DEL key để “sửa nhanh” vì có thể làm mất jobs.

### 18.5. Redis Cluster/Sentinel

Khi dùng Redis Sentinel hoặc Cluster:

- Kiểm tra tính tương thích của blocking List commands với client/node routing.
- Multi-key operation như BLMOVE cần keys cùng hash slot trong Redis Cluster.
- Test reconnect/failover và Redis persistence/replication RPO.
- Không suy ra một Redis connection timeout nghĩa là task chưa được pop; kết quả lệnh có thể **UNKNOWN** nếu đứt kết nối sau khi broker áp dụng lệnh nhưng trước khi client nhận response.
- Khi kết quả claim không rõ, processing list/reconciliation có thể cần giúp phân biệt job đã được chuyển hay chưa.

## 19. Bảo mật và giới hạn dữ liệu

Một Redis List queue có thể được nhiều services ghi/đọc tùy ACL. Không được coi queue nội bộ là nơi dữ liệu đầu vào mặc nhiên an toàn.

### 19.1. Redis ACL và key namespace

Trong production, xác định:

- Producer được phép **LPUSH/RPUSH** vào queue key nào.
- Consumer được phép **BLPOP/BRPOP** hoặc BLMOVE từ/đến keys nào.
- Reclaimer được phép sửa processing/dead lists, cập nhật lease state ở đâu.
- Operator nào được quyền xem/sửa/replay dead jobs.
- Những Redis commands nguy hiểm như FLUSHDB/DEL tùy ý có bị hạn chế theo policy không.
- Kết nối dùng TLS, credentials lấy từ secret manager/environment và mạng được giới hạn truy cập.

**Redis ACL không thay validation nghiệp vụ.** Một service có quyền LPUSH chưa có nghĩa mọi imageKey hoặc tenantId nó gửi đều hợp lệ.

### 19.2. Object storage paths và tenant boundary

Trong ví dụ thumbnail, **imageKey** là dữ liệu do producer gửi. Nếu consumer có quyền ghi object storage:

1. Kiểm tra productId thuộc tenant được phép.
2. Validate namespace/prefix và object key.
3. Chỉ dùng allowlisted bucket/container.
4. Giới hạn file type/size, pixel count và decoding resources.
5. Không chuyển imageKey vào shell command không escape/validate.
6. Tránh ghi đè thumbnail thuộc productVersion mới bằng task cũ.

**Không dùng Redis queue key hoặc eventType làm chứng cứ xác thực người dùng.** Ownership/authorization phải dựa vào nguồn tin cậy và policy dịch vụ.

### 19.3. Tránh deserialize object tùy ý

Không dùng native Java serialization để deserialize dữ liệu từ Redis khi producer khác hoặc nhiều team có thể ghi queue. Ưu tiên schema JSON/Protobuf/Avro và trusted target DTO, validation, byte-size limit.

Nếu dùng ObjectMapper, giới hạn polymorphic type handling, không bật default typing tùy tiện cho dữ liệu chưa tin cậy.

### 19.4. Payload nhạy cảm và dead list

Dead jobs thường được giữ lâu hơn pending jobs. Khi lưu lỗi:

- Không copy credentials, access token hoặc signed object URLs còn hiệu lực vào dead List.
- Giới hạn retention và truy cập theo vai trò.
- Tránh log full raw payload có PII.
- Có quy trình export/xóa dữ liệu theo chính sách.
- Khi replay, ghi audit ai thực hiện, lúc nào và task nào.

### 19.5. Rate limits và resource exhaustion

Redis List có thể chứa nhiều items nếu producer nhanh hơn consumer. Đặt ngưỡng queue length, giới hạn kích thước payload, producer-side throttling và capacity alerts.

Nếu tăng worker concurrency vô hạn, object storage, CPU, memory hoặc database có thể bị quá tải. Đảm bảo executor queues bounded và có chính sách khi đầy, không chỉ để Redis pending LLEN giảm.

## 20. Monitoring: ready, processing, dead và business outcome

Với Redis List queue, **LLEN của ready List** chỉ phản ánh những items còn trong danh sách đó. Để hiểu pipeline, cần nhiều thước đo:

| Tín hiệu | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| **LLEN ready** | Items chưa được claim/pop | Backlog lớn có thể do worker chậm/offline |
| **LLEN processing** | Items đã move nhưng chưa ACK trong reliable queue | Có thể có jobs đang chạy hoặc bị stuck |
| **LLEN dead** | Jobs đã cách ly theo policy ứng dụng | Cần owner và quy trình replay |
| Enqueue rate | Tốc độ producer thêm jobs | Không phải tốc độ hoàn tất |
| Pop/claim rate | Tốc độ adapter/worker lấy jobs | Có thể cao dù business fail |
| Handler success rate | Tốc độ xử lý nghiệp vụ thành công | So sánh với enqueue và retries |
| Handler error/retry | Lỗi theo loại, số attempts | Phân biệt poison vs transient |
| Job processing latency | Thời gian từ claim đến kết quả | Đo p95/p99 và timeouts |
| Oldest job age | Job chờ hoặc xử lý lâu nhất | Cần timestamp trong payload/metadata |
| Redis command errors | WRONGTYPE, timeout, ACL, cross-slot | Vấn đề cấu hình/Redis |
| Reclaim count/lease expiry | Số jobs bị nhận lại | Phát hiện worker crash/hung hoặc lease quá ngắn |
| Duplicate skipped | Idempotency bảo vệ side effects | Tăng sau crash/retry có thể bình thường |

### 20.1. Không dùng LLEN=0 như completed count

Giả sử Redis List có 100 tasks, inbound adapter có một ExecutorChannel nhận nhanh và executor queue 100 items trong memory:

~~~text
Redis pending LLEN = 0
Executor pending tasks = 100
Thumbnail success = 0
~~~

Nếu application crash, các tasks có thể mất vì Redis đã pop xong. Một dashboard chỉ hiển thị LLEN pending sẽ báo “không backlog”, gây hiểu sai. Đo **in-flight/processing** cùng business success.

### 20.2. Metric gợi ý

~~~text
thumbnail_queue_enqueued_total
thumbnail_queue_popped_total
thumbnail_queue_processing_total
thumbnail_queue_completed_total
thumbnail_queue_failed_total{reason="INVALID_SCHEMA"}
thumbnail_queue_retry_total{reason="DEPENDENCY_TIMEOUT"}
thumbnail_queue_reclaimed_total
thumbnail_queue_duplicate_skipped_total
thumbnail_queue_processing_duration_seconds
~~~

Đây là **tên metric minh họa**, không phải Spring Integration tự xuất tất cả. Tránh gắn **eventId, productId, imageKey** thành metric labels có cardinality quá cao; những trường đó phù hợp hơn ở logs/traces có kiểm soát.

### 20.3. Giám sát thời gian chờ lâu

Với reliable queue có lease, một job ở processing List nhưng không có heartbeat trong thời gian dài cần điều tra:

- Worker crash?
- Side effect treo?
- Redis mất kết nối?
- Job đang hợp lệ nhưng xử lý ảnh quá lớn?
- Lease quá ngắn và reclaimer đã xử lý trùng?

Không tự requeue tất cả jobs processing chỉ vì chúng xuất hiện ở đó hơn vài giây; cần SLA, worker state và idempotency/fencing.

### 20.4. Log đủ hữu ích nhưng không rò rỉ

~~~text
queue=catalog:thumbnail:pending
eventId=evt-thumb-1001
eventType=THUMBNAIL_REQUESTED
schemaVersion=1
attempt=2
workerId=image-worker-03
state=FAILED_RETRYABLE
durationMs=1800
errorCategory=OBJECT_STORAGE_TIMEOUT
~~~

**attempt** ở đây là trạng thái do ứng dụng quản lý; Redis List POP không tự tạo delivery count. Khi dùng endpoint direct POP và không có durable attempt state, đừng tự log một số attempts tổng thể như thể nó luôn chính xác qua restart.

### 20.5. Alerting theo SLA

Cần cảnh báo khi:

- Ready backlog tăng liên tục trong một thời gian dài.
- Có nhiều jobs processing quá hạn lease.
- Redis command timeout/connection retry tăng.
- Retry exhausted/dead jobs tăng đột biến.
- Thumbnail processing success giảm dù dequeue rate vẫn cao.
- Redis memory/maxmemory sắp chạm giới hạn.
- Product projection/cache stale vượt SLA và reconciliation không đạt.

Ngưỡng phải dựa trên workload và benchmark thực tế, không copy một giá trị tuỳ ý vào production.

## 21. Kiểm thử end-to-end với Redis thật

Unit test ThumbnailJobHandler chứng minh logic parse và validate. Nhưng không chứng minh RedisQueueMessageDrivenEndpoint **đọc đúng Redis key, đúng phía List, đúng serializer và đúng lifecycle**. Cần một integration test cô lập với Redis server thật, chẳng hạn test Redis instance/Redis Testcontainers phù hợp với project.

### 21.1. Ma trận kiểm thử

| Kịch bản | Thiết lập | Kết quả cần xác minh |
| --- | --- | --- |
| **Happy path** | LPUSH job hợp lệ, endpoint chạy | Spring Message đến handler, thumbnail được xử lý |
| **FIFO 3 items** | Đẩy A, B, C theo publisher contract | Thứ tự pop phù hợp chiều LPUSH/BRPOP hoặc RPUSH/BLPOP |
| **Sai serializer** | Gửi JSON bytes khác với endpoint mong đợi | Phát hiện lỗi conversion trước business handler |
| **Sai key** | Producer LPUSH key khác queue endpoint đọc | Không nhận task từ key khác |
| **Wrong Redis instance/database** | Publisher/consumer khác connection target | Không nhận; phát hiện cấu hình |
| **WRONGTYPE** | Key queue bị ghi thành String | Adapter phát lỗi rõ, không xóa dữ liệu |
| **Consumer offline** | LPUSH khi endpoint chưa start | Task còn trong List đến khi worker nhận, nếu không có consumer khác |
| **Crash sau direct POP** | Kill worker sau POP trước commit | Task có thể mất khỏi ready List; không tự redeliver |
| **Crash trước POP** | Kill worker trước khi đọc | Job có thể còn pending |
| **Duplicate LPUSH** | Producer retry cùng eventId | Business side effect không lặp |
| **Invalid JSON/schema** | Gửi malformed payload | Error policy không retry vô hạn; không tin có native DLQ |
| **Downstream transient error** | Mock object storage 503 rồi success | RetryTemplate hữu hạn, side effect đúng |
| **Downstream permanent error** | imageKey sai/không có quyền | Cách ly hoặc trạng thái thất bại rõ |
| **Multi-worker competing** | Hai consumers đọc cùng List | Mỗi Redis item bị pop bởi một worker, không broadcast |
| **Long-running jobs** | A mất 10 giây, B mất 1 giây | Không ngộ nhận completion order là FIFO |
| **Executor queue full** | Tạo burst vượt năng lực worker | Không âm thầm mất task mà không có alert/recovery |
| **BLMOVE claim** | Dùng ready/processing Lists | Job chuyển nguyên tử, processing theo dõi unacked ứng dụng |
| **Crash sau BLMOVE** | Kill worker trước business commit | Processing giữ job cho reclaimer theo policy |
| **Crash sau commit trước LREM** | Kill sau DB commit | Reclaim có thể redeliver, idempotency ngăn lặp |
| **Lease timeout** | Worker xử lý lâu hơn lease | Test fencing/idempotency chống hai workers cùng side effect |
| **Dead job transition** | Invalid task hết retry | Đúng job chuyển processing → dead, audit đủ |
| **Redis Cluster** | Keys BLMOVE khác hash slot | Cross-slot failure được phát hiện |
| **Reconnect/failover** | Restart Redis test | Loop nhận phục hồi theo khả năng client, kiểm tra unknown outcome |
| **Graceful shutdown** | Stop khi handler đang chạy | Xử lý in-flight theo policy; không báo hoàn tất giả |
| **ACL** | Consumer không có quyền đọc queue key | Error và alert có ý nghĩa |
| **Monitoring** | Đo enqueued, popped, completed, dead | Không coi LLEN=0 là success |

### 21.2. Test callback bằng CountDownLatch

Khi cần test Spring Integration flow trong một test context, có thể thay business handler bằng test sink để quan sát payload:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ThumbnailCapturingSink {

    private final AtomicReference<String> payload =
        new AtomicReference<>();
    private final CountDownLatch latch = new CountDownLatch(1);

    public void accept(String value) {
        payload.set(value);
        latch.countDown();
    }

    public String awaitPayload() throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Redis queue item not received");
        }
        return payload.get();
    }
}
~~~

**Đây chỉ là helper**, chưa phải integration test hoàn chỉnh. Test cần Spring context có endpoint, Redis thật, Redis serializers phù hợp, queue test riêng và phương thức inject sink vào IntegrationFlow test. Không dùng kết quả compile helper để tuyên bố adapter đã subscribe/consume đúng.

### 21.3. Test không nên dựa vào Thread.sleep cố định

Một Redis queue endpoint có lifecycle start/connect/blocking receive. Trong integration test:

1. Đảm bảo Redis test sẵn sàng.
2. Tạo endpoint và output channel/handler.
3. Xác nhận endpoint đã start/đủ điều kiện nhận.
4. LPUSH task vào key test.
5. Đợi latch/condition có timeout hợp lý.
6. Assert eventId/payload và side effect.
7. Kiểm tra List/processing state theo mô hình đang test.

Với List queue, một task LPUSH trước khi consumer online **có thể được nhận sau** nếu Redis giữ List; không nên áp nguyên quy tắc timing của Redis Pub/Sub.

### 21.4. Test nào có giá trị nhất?

**Crash sau direct POP trước DB commit** cho thấy mất item ở queue đơn giản. **Crash sau BLMOVE trước commit** cho thấy bản sao trong processing List còn để recovery. **Crash sau commit trước LREM** cho thấy duplicate delivery có thể xảy ra và idempotency là cần thiết.

Ba test này thường có giá trị thiết kế hơn việc chỉ gửi 100 JSON messages trong happy path.

### 21.5. Không thử lỗi trên queue production

Không DEL key production, cố tình WRONGTYPE trên queue thật hoặc restart Redis dùng chung để test. Dùng key namespace riêng hoặc Redis server/vhost tương ứng theo hạ tầng (Redis không có vhost như RabbitMQ), credential test tối thiểu và xóa dữ liệu thử nghiệm có kiểm soát.

## 22. Tình huống kiến trúc: chọn queue inbound cho đúng bài toán

### 22.1. Case A – Thumbnail có thể tạo lại từ database

**Bối cảnh:** CatalogService đã lưu ảnh gốc, metadata và trạng thái NEEDS_THUMBNAIL trong database. Redis List chỉ giúp ImageWorker biết có việc cần xử lý sớm.

~~~mermaid
flowchart TD
    U["Upload image"] --> DB[("Catalog DB<br/>NEEDS_THUMBNAIL")]
    DB --> P["LPUSH thumbnail task"]
    P --> Q["Redis List pending"]
    Q --> A["Redis queue inbound adapter"]
    A --> H["ImageWorker"]
    H --> OBJ[("Object storage thumbnail")]
    H --> D["Mark DONE in DB"]
    DB --> R["Periodic reconciliation"]
    R -->|"NEEDS_THUMBNAIL còn tồn"| P
~~~

Trong case này, Redis List direct POP **có thể chấp nhận được** nếu:

- Database là nguồn sự thật về jobs chưa hoàn tất.
- Worker tạo thumbnail idempotent theo productId/imageVersion.
- Scheduler định kỳ quét jobs còn NEEDS_THUMBNAIL để enqueue lại.
- Duplicate được kiểm soát khi retry/đối soát.
- SLA cho phép có độ trễ do reconciliation.

**Nếu mất task sau POP**, database vẫn chứa trạng thái chưa DONE, nên scheduler có thể phục hồi. Điều này **không làm POP tự reliable**; hệ thống đạt khả năng phục hồi nhờ **nguồn trạng thái bền vững bên ngoài**.

### 22.2. Case B – Gửi email marketing best-effort

**Bối cảnh:** Một hệ thống nội bộ cần gửi thông báo quảng bá, chấp nhận retry theo chiến dịch và có nguồn dữ liệu gốc. Redis List queue có thể giúp phân phối các jobs nhẹ.

Tuy nhiên, khi gửi email:

- Một request timeout không chứng minh SMTP/provider chưa gửi.
- Retry có thể tạo email trùng nếu không có idempotency/campaign-recipient key.
- Queue List POP không có native dead-letter.
- Hạn mức provider cần backoff, rate limit và monitoring.

Ngay cả với best-effort, cần mô tả **những message nào có thể mất** và có nguồn campaign/job table để chạy lại không.

### 22.3. Case C – Xử lý thanh toán bắt buộc không mất

**Bối cảnh:** PaymentService nhận tác vụ trừ tiền. Nếu worker chết sau POP trước transaction, không thể mất task; nếu worker chết sau commit, không được trừ hai lần.

**Không nên dùng Redis List direct POP làm nguồn duy nhất**. Cân nhắc:

~~~mermaid
flowchart LR
    REQ["Payment request"] --> DB[("Payment DB transaction<br/>+ outbox")]
    DB --> PUB["Outbox publisher"]
    PUB --> MQ["Durable broker / Redis Stream"]
    MQ --> C["Idempotent consumer"]
    C --> PAY["Payment provider with idempotency key"]
    C --> DB
~~~

Nếu vẫn tự xây reliable Lists, phải có processing claim, lease/fencing, durable attempt state, ACK chỉ sau commit, recovery và reconciliation được chứng minh qua failure tests. Chi phí xây/dẫn vận hành có thể vượt lợi ích Redis List đơn giản.

### 22.4. Case D – SFTP import → Redis work queue

**Bối cảnh:** SFTP inbound adapter đồng bộ file CSV vào thư mục local, parser tạo nhiều jobs, rồi producer LPUSH vào Redis List; workers xử lý từng row.

~~~mermaid
flowchart LR
    SF["SFTP inbound adapter<br/>poller"] --> CSV["CSV parser/validator"]
    CSV --> DB[("Import DB<br/>row states")]
    DB --> Q["Redis List pending"]
    Q --> RI["Redis queue inbound"]
    RI --> H["Row processor"]
    H --> DB
~~~

Không xóa file nguồn hoặc đánh dấu import hoàn tất chỉ vì **LPUSH trả về chiều dài queue**. Cần trạng thái từng row/eventId; scheduler có thể retry rows chưa DONE nếu task bị mất sau POP.

### 22.5. Case E – Redis queue inbound → HTTP outbound adapter

**Bối cảnh:** Worker pop job và gọi HTTP API ngoài:

~~~text
Redis List -> queue inbound adapter -> DirectChannel
           -> HTTP outbound gateway/adapter -> External API
~~~

Vì HTTP có thể trả timeout khi hệ thống đích **đã xử lý xong**, cần idempotency key và cách tra trạng thái kết quả ở provider. Với direct POP, một lỗi sau pop có thể mất job; với recovery/retry, có thể gọi HTTP lần nữa. Điều quan trọng là **thiết kế side effect idempotent**, không phải chỉ chỉnh Redis retry.

### 22.6. Case F – Redis queue inbound → AMQP/Kafka outbound

Nếu endpoint nhận Redis List rồi gửi sang RabbitMQ/Kafka:

~~~text
Redis POP
  -> Spring Message
  -> AMQP/Kafka outbound adapter
  -> broker destination
~~~

Nếu Redis POP đã hoàn tất nhưng AMQP publisher confirm/Kafka producer result chưa đạt mốc lưu bền cần thiết, process crash có thể làm mất event ở khoảng giữa. Ngược lại, broker đích có thể đã nhận nhưng kết quả producer UNKNOWN, ứng dụng retry sẽ tạo duplicate.

**Không coi MessageChannel.send thành công là publisher confirm/kafka ACK**. Đối với bridge không thể mất message, nên có durable source/handoff, transactional outbox hoặc mô hình hỗ trợ ACK/retry cả hai phía.

## 23. Sai lầm phổ biến khi dùng Redis queue inbound

**“Redis queue inbound chính là Redis Pub/Sub inbound.”** Sai. List queue đọc items bằng List operations; Pub/Sub nhận notifications từ PUBLISH/SUBSCRIBE.

**“LPUSH phát thông báo cho subscriber SUBSCRIBE cùng tên.”** LPUSH ghi Redis List key, không phải PUBLISH trên channel đó.

**“Redis List luôn FIFO dù push/pop đầu nào.”** FIFO cần một phía thêm và phía đối diện lấy; LPUSH/BLPOP cùng đầu có thể tạo LIFO.

**“Blocking POP nghĩa là Redis giữ delivery tới khi handler ACK.”** Với BRPOP/BLPOP, item bị xóa khi lệnh trả kết quả; không có native ACK.

**“Redis persistence tự phục hồi job đã BRPOP nhưng handler chưa commit.”** Persistence giữ trạng thái Redis, không tạo cơ chế rollback POP theo DB transaction.

**“Redis List queue có DLX/DLQ giống RabbitMQ.”** Redis Lists không có dead-letter exchange native; dead list là một contract do ứng dụng thiết kế.

**“Redis queue inbound phải có Spring Pollers.fixedDelay.”** Message-driven endpoint có vòng blocking read; poller riêng không tạo thêm độ bền.

**“Dùng QueueChannel sau inbound là không thể mất task.”** QueueChannel mặc định không durable; POP đã diễn ra trước khi task được đưa vào queue nội bộ.

**“ExecutorChannel luôn tăng reliability.”** Executor có thể giữ tasks trong memory rồi mất khi process crash.

**“LLEN pending = 0 nghĩa là hoàn tất toàn bộ tasks.”** Tasks có thể đang xử lý, bị mất sau POP hoặc đang nằm trong executor queue.

**“RetryTemplate có thể replay job sau restart.”** RetryTemplate trong JVM không phải durable attempt log; POP trực tiếp đã xóa item khỏi Redis List.

**“Cứ LPUSH lại trong catch là tạo retry an toàn.”** Có thể hot loop, duplicate và mất trạng thái retry giữa crash.

**“BLMOVE tự có consumer ACK và reclaimer.”** BLMOVE chỉ nguyên tử chuyển item giữa Lists; application phải quản lý processing, lease/ACK/reclaim.

**“LREM processing sau commit bảo đảm exactly-once.”** Crash sau commit trước LREM có thể khiến job bị requeue; cần idempotent consumer.

**“LMOVE bất kỳ phần tử processing sang dead là đúng job vừa lỗi.”** Có thể lấy nhầm phần tử thuộc worker khác; cần nhận diện job và ownership chính xác.

**“Gắn attemptCount trong Java object là đủ để giới hạn retry sau restart.”** Cần durable attempt state hoặc nguồn bền vững để khôi phục.

**“Một worker đã lease job thì không có worker nào xử lý trùng.”** Lease có thể hết trước khi worker cũ thực sự dừng; cần fencing/idempotency.

**“Redis Streams chỉ khác Redis List ở cú pháp.”** Streams có record IDs, pending/ACK và consumer-group semantics, khác bản chất direct List POP.

**“Một List với hai consumers sẽ broadcast mỗi item cho cả hai.”** Redis pop atomically phân phối item cho một consumer, không phải fan-out.

**“Queue FIFO có nghĩa completion order FIFO khi ba workers chạy song song.”** Jobs có thể hoàn thành lệch thứ tự; cần domain sequence nếu quan trọng.

**“Đã thêm eventId trong JSON thì tự chống trùng.”** EventId chỉ hữu ích khi handler có unique constraint/idempotency logic thật.

**“MessageHeaders.ID của Spring ổn định qua Redis retry.”** Spring Message có thể được tạo lại với ID mới; dùng business eventId ổn định.

**“Redis queue inbound nhận String UTF-8 ở mọi phiên bản.”** Serializer của producer và inbound endpoint phải được đối chiếu; có thể là bytes/serialized messages.

**“Cứ đặt JSON contentType header kiểu AMQP trong Redis List.”** List value không có bảng AMQP basic properties; schema nên ở envelope hoặc mapping do ứng dụng tự thiết kế.

**“Một đoạn @Transactional bọc business xử lý là rollback được BRPOP.”** DB transaction không tự đưa item trở lại Redis List.

**“Redis Cluster BLMOVE keys đặt đâu cũng được.”** Multi-key command phải đáp ứng cùng hash slot.

**“Đặt dead list là nơi lưu vĩnh viễn không cần người quản lý.”** Cần retention, ACL, capacity, alert, replay và audit.

**“Tăng worker concurrency sẽ luôn giảm tổng thời gian.”** Downstream CPU, storage, DB hoặc provider rate limit có thể bão hòa và tăng lỗi.

**“Kết nối Redis đã phục hồi nghĩa là công việc sau POP trước crash đã phục hồi.”** Reconnect chỉ cho phép đọc dữ liệu còn trong Redis, không phục hồi item đã pop mất.

**“Test happy path chứng minh at-least-once.”** Phải test crash giữa claim/commit/ACK, reclaimer, duplicates, Redis failover và unknown outcomes.

## 24. Checklist thiết kế Redis queue inbound

| Nhóm | Câu hỏi cần xác minh trước production |
| --- | --- |
| **Use case** | Job bị mất sau POP có thể phục hồi/rebuild từ nguồn khác không? |
| **Redis primitive** | Dùng List, Stream hay Pub/Sub? Có nhầm inbound adapter không? |
| **Queue key** | Namespace, environment, key type và Redis connection đúng không? |
| **Push/pop** | LPUSH/BRPOP hoặc RPUSH/BLPOP đã thống nhất và test FIFO chưa? |
| **Serializer** | Producer và Redis inbound endpoint dùng cùng wire format chưa? |
| **Payload** | eventId/eventType/schemaVersion, max size, validation/charset có rõ không? |
| **Endpoint** | RedisQueueMessageDrivenEndpoint có API/constructor phù hợp phiên bản không? |
| **MessageChannel** | DirectChannel, ExecutorChannel hay QueueChannel? Nơi nào có thể mất task? |
| **Reliability** | Có chấp nhận cửa sổ crash-after-POP không? Nếu không, cơ chế nào thay thế? |
| **Processing List** | BLMOVE có dùng cùng hash slot, có owner/lease/ACK/reclaim không? |
| **Idempotency** | Unique eventId, deterministic output và trạng thái DONE được lưu ở đâu? |
| **Retry** | Có classifier, max attempts, backoff và nextRetryAt bền vững không? |
| **Poison jobs** | Có dead list/error table, retention, replay và owner không? |
| **Concurrency** | Bao nhiêu workers, mỗi worker giữ bao nhiêu jobs, downstream capacity thế nào? |
| **Transaction** | Redis claim, DB commit và object storage side effect có những khoảng lỗi nào? |
| **Lifecycle** | Start/stop/reconnect/failover và in-flight handling ra sao? |
| **Security** | Redis ACL key patterns, TLS, credentials, authorization payload? |
| **Cluster** | BLMOVE/source/dest có hash slot hợp lệ không? |
| **Monitoring** | Ready/processing/dead, success/retry/reclaim, oldest age và alerts? |
| **Testing** | Integration test với Redis thực và fault injection sau claim/commit/ACK? |

### 24.1. Quyết định nhanh

**Chọn Redis List queue inbound** khi công việc có thể xử lý bởi competing consumers, backlog được giữ khi workers offline, và bạn đã **chấp nhận hoặc có cách bù** cho cửa sổ mất giữa POP và business commit.

**Chọn Redis Streams hoặc broker hỗ trợ acknowledgment** khi cần pending state, replay sau crash và khả năng quan sát attempts/recovery có cấu trúc.

**Chọn Redis Pub/Sub inbound** khi cần broadcast notification tới subscribers online, không cần backlog cho từng consumer.

### 24.2. Khi nào chỉ cần DirectChannel?

DirectChannel phù hợp cho handler nhanh, đồng bộ và đơn giản. Tuy nhiên DirectChannel **không thể biến destructive POP thành transactional delivery**. Khi công việc có thể mất lâu hoặc phải retry sau restart, hãy chọn nguồn durable/processing protocol trước rồi mới quyết định channel nội bộ.

### 24.3. Khi nào nên bỏ tự xây reliable List queue?

Nếu thiết kế đã cần:

~~~text
processing list + ACK + leases + heartbeat
  + reclaimer + pending dashboard + retry budget
  + dead queue + delivery-count monitoring
  + duplicates + consumer ownership
~~~

thì nên đánh giá Redis Streams, RabbitMQ, JMS hoặc Kafka theo workload và vận hành. **Thời gian xây/duy trì một reliable queue** có thể lớn hơn nhiều so với việc dùng một primitive có các khái niệm tương ứng sẵn.

## 25. Câu hỏi tự kiểm tra

1. Redis queue inbound adapter đọc dữ liệu từ loại Redis primitive nào? Nó khác Redis Pub/Sub inbound như thế nào?
2. Vì sao RedisQueueMessageDrivenEndpoint có thể được xem là message-driven mặc dù nó dùng Redis blocking POP?
3. Hai cặp lệnh push/pop nào thường bảo toàn FIFO? Chuyện gì xảy ra nếu chọn cùng đầu List?
4. BRPOP khác RPOP ở điều gì? Tham số timeout của BRPOP có phải retry backoff nghiệp vụ không?
5. Vì sao LPUSH vào Redis List không làm một subscriber SUBSCRIBE cùng tên channel nhận được thông báo?
6. Khi worker offline trước POP, Redis List có giữ tasks cho worker tương lai không? Điều kiện nào phải đúng?
7. Khi worker đã BRPOP nhưng JVM crash trước DB commit, điều gì xảy ra với item ở pending List?
8. Vì sao bật Redis AOF/RDB không làm một lệnh POP tự có consumer acknowledgment?
9. Redis List direct POP khác Redis Streams consumer group ở pending/ACK/recovery như thế nào?
10. RedisQueueMessageDrivenEndpoint đưa item vào thành phần nào của Spring Integration? Vì sao nó là message producer theo góc nhìn integration?
11. Khi nào cần cấu hình Spring Integration poller và khi nào không?
12. Nếu producer dùng StringRedisTemplate nhưng inbound endpoint có serializer khác, những lỗi nào có thể xuất hiện?
13. Tại sao không giả định payload sau adapter luôn là String UTF-8?
14. Payload eventId/schemaVersion giúp bảo vệ những khía cạnh nào? Vì sao Spring MessageHeaders.ID không thay eventId?
15. LPUSH trả về chiều dài List có chứng minh thumbnail đã được tạo không?
16. Nếu Redis connection mất gần một lệnh LPUSH, producer retry có thể tạo duplicate thế nào?
17. Vì sao direct POP + @Transactional service không tạo một transaction nguyên tử giữa Redis và DB?
18. Đối với một task sai schema, retry trực tiếp vào cùng List trong catch có rủi ro gì?
19. RetryTemplate.maxAttempts(3) bảo đảm điều gì trong JVM? Nó không bảo đảm điều gì sau restart?
20. ErrorChannel ghi nhận exception có tự đưa item đã POP trở lại Redis List không?
21. ExecutorChannel có thể làm tăng cửa sổ mất dữ liệu sau POP như thế nào?
22. QueueChannel mặc định khác Redis List backlog/Redis Streams như thế nào về độ bền?
23. Nhiều workers cùng đọc một Redis List có phải mỗi worker đều nhận toàn bộ items không?
24. Vì sao FIFO ở mức Redis POP không đồng nghĩa thứ tự hoàn tất nghiệp vụ?
25. Redis List có native prefetch/ACK tương đương RabbitMQ consumer không?
26. BLMOVE source destination RIGHT LEFT khác BRPOP ở điểm quan trọng nào về giữ dữ liệu?
27. Processing List có giúp phục hồi job nếu worker chết ngay sau claim không? Vì sao vẫn cần reclaimer?
28. Nếu DB đã commit nhưng worker chết trước LREM processing, nguy cơ duplicate xảy ra thế nào?
29. Vì sao job cần eventId ổn định, unique constraint hoặc deterministic output key?
30. Nếu processing List chứa hai phần tử cùng serialized payload, LREM có vấn đề gì về ownership?
31. Reclaimer cần những metadata nào để nhận biết một job stuck?
32. Vì sao một lease quá ngắn có thể khiến hai workers xử lý cùng job?
33. Fencing token/idempotency khác nhau như thế nào khi một worker cũ vẫn đang chạy?
34. Vì sao BLMOVE và ghi owner metadata trong hai Redis commands riêng chưa tạo được claim workflow nguyên tử?
35. Redis Cluster yêu cầu gì đối với keys nguồn/đích của BLMOVE? Hash tag có tác dụng gì?
36. Dead List do ứng dụng thiết kế khác RabbitMQ DLX/DLQ native như thế nào?
37. Nếu một Redis List queue có LLEN=0 nhưng executor đang giữ 100 tasks, hệ thống đã hoàn tất 100 tasks chưa?
38. Cần theo dõi những metrics nào ngoài LLEN ready để biết hệ thống có đang theo kịp và không mất job?
39. Những trường hợp Redis WRONGTYPE/ACL/timeout cần được xử lý ở transport boundary thế nào?
40. Trong flow SFTP → Redis queue → handler, vì sao không thể đánh dấu import thành công chỉ nhờ LPUSH?
41. Với bridge Redis queue → Kafka, có khoảng mất dữ liệu nào giữa POP và Kafka producer acknowledgment?
42. Nếu thumbnail job có thể rebuild từ database, một periodic reconciliation có thể bù cho mất item sau POP như thế nào?
43. Nếu tác vụ thanh toán không được phép mất, nên chọn mô hình durable handoff/ACK/idempotency nào?
44. Kiểm thử crash sau POP, crash sau BLMOVE và crash sau DB commit trước LREM giúp chứng minh những điều khác nhau nào?
45. Khi nào nên chuyển từ tự xây reliable Redis List queue sang Redis Streams hoặc broker chuyên dụng?

## Tổng kết

**Redis queue inbound adapter** đưa các item từ **Redis List key** vào **Spring Integration MessageChannel**, rồi để transformer, filter, router và service activator xử lý theo hợp đồng ứng dụng. Khác Redis Pub/Sub inbound nhận notification theo SUBSCRIBE, queue inbound nhận công việc qua **List POP**, thường có cơ chế **blocking read** và các workers cạnh tranh lấy từng phần tử. Phải thống nhất **push/pop direction**, serializer/charset, payload schema và vòng đời endpoint để tránh nhận sai thứ tự hoặc lỗi conversion.

**Cảnh báo quan trọng nhất:** Với List queue **pop phá hủy trực tiếp**, item bị xóa khỏi Redis **trước khi business handler commit**. Redis có thể giữ pending backlog khi worker offline, nhưng không tự tạo ACK, pending entry, DLQ hay rollback theo JDBC transaction. RetryTemplate, DirectChannel, QueueChannel và errorChannel đều **không tự giải quyết** cửa sổ mất job sau POP. Nếu nghiệp vụ không thể bỏ sót task, cần một nguồn bền vững và cơ chế claim/recovery phù hợp.

Mẫu **BLMOVE ready → processing**, **ACK ứng dụng sau commit**, **reclaimer/lease**, retry có giới hạn, final dead state và idempotent consumer có thể cải thiện reliability, nhưng làm tăng đáng kể trách nhiệm tự xây và vận hành. Với yêu cầu pending/replay/consumer group rõ ràng, nên đánh giá **Redis Streams**, AMQP, JMS, Kafka hoặc durable database jobs theo nhu cầu.

Trong module **SPRING_INTEGRATION_ADAPTERS**, khi nối Redis với File, SFTP, HTTP, AMQP, Kafka hoặc database, luôn phân biệt bốn mốc: **đã enqueue vào Redis**, **đã pop/claim**, **đã lưu bền ở bước kế tiếp** và **đã hoàn tất side effect nghiệp vụ**. Chỉ khi hợp đồng lỗi, transaction, idempotency, monitoring và thử nghiệm crash được xác định đầy đủ, một Redis queue inbound flow mới có khả năng vận hành và khôi phục đáng tin cậy.
