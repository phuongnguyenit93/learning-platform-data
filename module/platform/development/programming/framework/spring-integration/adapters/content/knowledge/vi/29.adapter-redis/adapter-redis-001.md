# Redis inbound channel adapter

## Mục tiêu học tập

Sau khi hoàn thành bài này, bạn có thể:

- Giải thích **Redis inbound channel adapter** là gì, vai trò của nó tại ranh giới Redis Pub/Sub và **Spring Integration MessageChannel**.
- Phân biệt **message-driven inbound** với **polling inbound**, **channel adapter một chiều** với **gateway request–reply**, đồng thời phân biệt Redis Pub/Sub với **Redis Streams** và các queue dựa trên Redis List.
- Thiết kế kênh Redis, subscription theo **channel** hoặc **pattern**, xác định hợp đồng payload/metadata và vòng đời subscriber.
- Kết nối Redis listener với **DirectChannel**, transformer, filter, router, service activator và error flow; hiểu hệ quả khi thay bằng ExecutorChannel hoặc QueueChannel.
- Thực hành publish bằng **StringRedisTemplate**, tiếp nhận qua Redis Pub/Sub rồi chuyển thành Spring Message và xử lý một sự kiện mẫu.
- Phân tích giới hạn **at-most-once của Redis Pub/Sub**, subscriber offline, đứt kết nối, retry, idempotency và tình huống cần lưu bền bằng Redis Streams, database/outbox hoặc broker khác.
- Áp dụng kiểm thử hợp đồng, thử reconnect, an toàn dữ liệu, giám sát và graceful shutdown.

## 1. Bức tranh tổng thể: Redis → Spring Integration

**Redis inbound channel adapter** là một endpoint đầu vào của Spring Integration giúp ứng dụng **nhận thông điệp do Redis Pub/Sub phát ra** và đưa chúng vào **MessageChannel** để các thành phần trong integration flow tiếp tục xử lý.

Giả sử CatalogService thay đổi giá sản phẩm và thông báo một sự kiện:

~~~text
Redis channel: catalog.price.changed
Payload JSON : {"eventId":"evt-1001","productId":"P-1001","priceVnd":150000}
~~~

Ứng dụng SearchService muốn cập nhật hoặc vô hiệu hóa cache tìm kiếm khi có thay đổi này. Thay vì tự viết code nhận Redis rồi gọi handler từ nhiều nơi, ta tạo một **điểm tích hợp rõ ràng**:

~~~mermaid
flowchart LR
    P["CatalogService"] -->|"PUBLISH"| R["Redis Pub/Sub<br/>channel"]
    R --> S["Redis subscriber<br/>listener container"]
    S --> IA["Redis inbound<br/>channel adapter"]
    IA --> MC["MessageChannel"]
    MC --> T["Transformer / Validator"]
    T --> H["Service activator"]
    H --> C["Invalidate / refresh cache"]
~~~

Trong kiến trúc **SPRING_INTEGRATION_ADAPTERS**, đây là cách nối một hệ thống ngoài vào luồng messaging của ứng dụng. Các adapter khác của module có thể kết nối File, SFTP, HTTP, JMS, AMQP, Kafka hoặc database; tuy nhiên **ngữ nghĩa phát và nhận của từng giao thức không giống nhau**. Không được suy ra bảo đảm giao nhận của Kafka/JMS/AMQP từ việc Redis cũng có cơ chế publish/subscribe.

**Câu hỏi then chốt:** Nếu SearchService ngắt kết nối đúng lúc CatalogService publish, sự kiện có còn được giữ lại không? Với **Redis Pub/Sub thông thường, không**: Redis không tạo hàng đợi bền vững cho mỗi subscriber để phát lại những thông điệp đã bỏ lỡ.

### 1.1. Vị trí của inbound channel adapter

Một flow Spring Integration thường có hai miền:

| Miền | Thành phần | Trách nhiệm |
| --- | --- | --- |
| Redis/ngoài ứng dụng | Publisher, Redis server, Pub/Sub channel | Phát thông điệp tới subscriber đang kết nối |
| Ranh giới tiếp nhận | Redis inbound channel adapter / Redis listener | Nhận dữ liệu từ Redis và tạo Spring Message |
| Trong Spring Integration | MessageChannel, transformer, filter, router | Định tuyến, kiểm tra, chuyển đổi dữ liệu |
| Nghiệp vụ | Service activator | Thực hiện thao tác cache, database, logging... |
| Ranh giới gửi tiếp | Outbound adapter khác | Publish kết quả sang Redis/Kafka/HTTP... nếu thiết kế yêu cầu |

Redis inbound channel adapter là một **message producer từ góc nhìn Spring Integration**: nó *produce* Spring Messages vào channel nội bộ sau khi nhận một Redis Pub/Sub notification; không phải một **Redis publisher**.

### 1.2. Adapter một chiều không tự tạo request–reply

Một inbound adapter điển hình là **one-way**:

~~~text
Redis PUBLISH -> inbound adapter -> Spring MessageChannel
~~~

Nó không giữ một HTTP-style request để chờ Spring service trả kết quả cho publisher. Nếu ứng dụng cần nhận yêu cầu và phản hồi chính xác cho caller, phải thiết kế giao thức request–reply riêng (ví dụ HTTP gateway, AMQP gateway hoặc kênh reply Redis và cơ chế correlation/timeout tự xây dựng). **Redis Pub/Sub PUBLISH không phải lời gọi RPC**.

## 2. Redis Pub/Sub thực sự hoạt động như thế nào?

Redis hỗ trợ lệnh **PUBLISH** để gửi bytes tới một **channel name**; các client đang SUBSCRIBE/PSUBSCRIBE theo kênh/pattern tương ứng có thể nhận được thông điệp.

~~~mermaid
sequenceDiagram
    participant A as Subscriber A
    participant R as Redis
    participant B as Subscriber B
    participant P as Publisher
    A->>R: SUBSCRIBE catalog.price.changed
    B->>R: PSUBSCRIBE catalog.*
    P->>R: PUBLISH catalog.price.changed body
    R-->>A: message
    R-->>B: pmessage
    R-->>P: number of matching subscriptions (not ACK)
~~~

### 2.1. Tên channel là định tuyến, không phải queue

Tên channel như **catalog.price.changed** là một **địa chỉ Pub/Sub**, không phải Redis key chứa một danh sách bản tin. Không có cấu trúc:

~~~text
catalog.price.changed -> [msg-1, msg-2, msg-3]
~~~

được Redis Pub/Sub mặc định lưu bền cho subscriber tới muộn. Khi không có subscriber phù hợp, Redis không lưu sẵn một backlog để khi subscriber mới kết nối sẽ nhận lại.

### 2.2. Redis Pub/Sub có đặc tính at-most-once

Theo mô hình Pub/Sub thường dùng, thông điệp được phát tới những subscriber đang kết nối phù hợp tại thời điểm publish, **không có một ACK xử lý nghiệp vụ hoặc lệnh replay** từ phía subscriber như Redis Streams consumer group. Nếu client bị mất kết nối, xử lý chậm đến mức có sự cố hoặc tiến trình bị kill, bản tin có thể bị mất với subscriber đó.

Đừng gọi đây là **exactly-once** hay **at-least-once** chỉ vì Spring Integration có MessageChannel và handler. Spring Integration chỉ tổ chức luồng **sau khi ứng dụng đã nhận được sự kiện**.

### 2.3. PUBLISH trả số lượng subscriber, không phải kết quả nghiệp vụ

Nếu chạy:

~~~redis
PUBLISH catalog.price.changed "{\"eventId\":\"evt-1001\",\"productId\":\"P-1001\"}"
~~~

Redis trả về số lượng subscription/client phù hợp theo ngữ nghĩa của lệnh và chế độ Pub/Sub đang sử dụng. **Giá trị lớn hơn 0 không chứng minh** SearchService đã parse JSON, cập nhật cache thành công, hay event đã được ghi bền vững.

### 2.4. Một publisher, nhiều subscriber

~~~mermaid
flowchart LR
    P["CatalogService"] --> R["Redis channel"]
    R --> A["SearchService instance 1"]
    R --> B["SearchService instance 2"]
    R --> C["AnalyticsService"]
~~~

Với Pub/Sub, **mỗi subscriber được đăng ký phù hợp có thể nhận cùng một message**. Đây là broadcast, không phải **competing consumers** theo một queue như RabbitMQ.

Nếu cả hai instance của SearchService cùng nghe một channel, **cả hai có thể cùng xử lý cùng event**. Điều này tốt cho việc vô hiệu hóa cache cục bộ trên mỗi node nhưng có thể nguy hiểm nếu mỗi node cùng thực hiện **một giao dịch database không idempotent**.

## 3. Redis inbound adapter là message-driven, không phải polling

Trong Spring Integration có hai kiểu kích hoạt endpoint phổ biến:

| Kiểu | Ví dụ | Cơ chế khởi phát | Điểm cần cân nhắc |
| --- | --- | --- | --- |
| **Message-driven inbound** | Redis Pub/Sub, AMQP/JMS listener | Bên ngoài gửi notification đến listener | Không cần poller lấy message định kỳ |
| **Polled inbound** | File, SFTP file synchronizer, JDBC polling | Poller gọi nguồn theo lịch | Cần lịch poll, lock/filter, idempotency |
| **Request-driven inbound** | HTTP inbound gateway | Request đến server endpoint | Request/reply/timeout của caller |

Redis Pub/Sub subscriber thường do **RedisMessageListenerContainer** (Spring Data Redis) quản lý cùng với **RedisConnectionFactory**. Spring Integration Redis inbound endpoint tích hợp callback nhận thông điệp với MessageChannel.

**Không thêm một Pollers.fixedDelay(...) chỉ để chờ Redis Pub/Sub message.** Poller không khiến Redis lưu lại những thông điệp đã mất. Muốn poll một danh sách/stream hoặc database, phải chọn endpoint và chiến lược riêng phù hợp với mô hình dữ liệu đó.

### 3.1. Data flow logic

~~~text
Redis publisher
    |
    |  PUBLISH topic bytes
    v
Redis server
    |
    |  Pub/Sub delivery to connected clients
    v
RedisMessageListenerContainer
    |
    |  Spring Data Redis MessageListener callback
    v
Redis inbound channel adapter
    |
    |  create Spring Message (payload + headers)
    v
MessageChannel
    |
    v
Transformer -> Filter -> Service activator
~~~

### 3.2. Chọn đúng lớp với đúng phiên bản

Trong Spring Integration Redis, component chính thường được biết đến dưới tên **RedisInboundChannelAdapter** hoặc cấu hình inbound Redis adapter tương ứng trong DSL/XML. API tạo đối tượng, setter topics và cách truyền listener container có thể khác giữa các thế hệ Spring Integration/Spring Data Redis.

Ở bài này, chúng ta đưa ra **cấu trúc Java/Spring Data Redis có thể kiểm chứng** và một ví dụ cấu hình adapter theo ý nghĩa. Khi dùng phiên bản cụ thể, hãy đối chiếu tên method/constructor của thư viện được dependency management quản lý và chạy integration test. **Không coi một ví dụ từ phiên bản khác là bảo đảm source tương thích 100%.**

## 4. Subscription theo channel và pattern

Redis có hai cách đăng ký Pub/Sub phổ biến:

~~~redis
SUBSCRIBE catalog.price.changed
PSUBSCRIBE catalog.*
~~~

**Channel subscription** nhận các message trên một channel được chọn; **pattern subscription** nhận các channel phù hợp pattern theo cú pháp Redis, ví dụ catalog.*.

Spring Data Redis biểu diễn hai khái niệm bằng **ChannelTopic** và **PatternTopic**.

~~~java
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.PatternTopic;
import org.springframework.data.redis.listener.Topic;

Topic exact = new ChannelTopic("catalog.price.changed");
Topic group = new PatternTopic("catalog.*");
~~~

### 4.1. Chọn subscription nào?

| Yêu cầu | Lựa chọn | Lý do |
| --- | --- | --- |
| Consumer chỉ nhận cập nhật giá | ChannelTopic("catalog.price.changed") | Hợp đồng hẹp, dễ phân quyền/kiểm thử |
| Consumer cần nhiều loại sự kiện catalog | PatternTopic("catalog.*") | Giảm số subscription, cần router/validator |
| Consumer được phép nhận mọi sự kiện | Pattern rộng theo chính sách | Dễ mở rộng nhưng nguy cơ tải/metadata ngoài dự kiến |
| Nhiều nhóm nghiệp vụ cách ly | Nhiều channel naming conventions | Giúp giảm va chạm và định rõ ownership |

**Không dùng pattern quá rộng** như * khi hệ thống có lưu lượng lớn hoặc nhiều tenant mà chưa đánh giá access control và bảo mật. Một publisher bất kỳ có thể chọn tên channel gây trùng namespace nếu không có quyền và quy ước rõ.

### 4.2. Naming convention

Gợi ý:

~~~text
<environment>.<service>.<domain>.<event>
prod.catalog.product.price-changed
staging.catalog.product.price-changed
~~~

Tên chỉ là **quy ước ứng dụng**, Redis không tự suy tên eventType hay schemaVersion từ chuỗi này. Nếu code dùng pattern prod.catalog.* thì event payload vẫn cần validation trước khi thực hiện side effect.

### 4.3. Đăng ký trùng

Nếu client vừa SUBSCRIBE chính xác một channel vừa PSUBSCRIBE pattern khớp channel đó, cần hiểu cơ chế delivery theo từng subscription của Redis. Một thông điệp có thể được quan sát dưới nhiều subscription tương ứng; đừng mặc định rằng tầng ứng dụng chỉ có đúng một callback khi cấu hình overlapping subscriptions. Khi một nghiệp vụ không được lặp, dùng **eventId/idempotency** và test topology subscription cụ thể.

## 5. Các thành phần Spring và trách nhiệm

| Thành phần | Thuộc thư viện | Vai trò |
| --- | --- | --- |
| **RedisConnectionFactory** | Spring Data Redis | Tạo kết nối Redis với cấu hình client, authentication/TLS |
| **RedisMessageListenerContainer** | Spring Data Redis | Quản lý đăng ký channel/pattern, listener callbacks và kết nối lại |
| **RedisInboundChannelAdapter** | Spring Integration Redis | Chuyển Redis Pub/Sub notifications thành Spring Messages ở đầu vào |
| **MessageChannel** | Spring Messaging/Integration | Chuyển message tới các subscriber trong một flow |
| **DirectChannel** | Spring Integration | Gọi handler đồng bộ theo caller thread |
| **ExecutorChannel** | Spring Integration | Dispatch bất đồng bộ qua executor, thay đổi ranh giới lỗi |
| **QueueChannel** | Spring Integration | Đệm messages nội bộ; mặc định không là durable event log |
| **Transformer** | Spring Integration | Chuyển byte[]/String/JSON sang domain DTO |
| **Service activator** | Spring Integration | Thực hiện nghiệp vụ như invalidate cache |
| **ErrorChannel / ErrorMessage** | Spring Integration | Chuyển lỗi của flow theo cấu hình, không làm Redis replay |

Một số endpoint Redis khác có thể dùng **list/queue operations** hoặc **Redis Streams**, với mô hình khác. Không gọi mọi endpoint có tên Redis là một Pub/Sub inbound channel adapter.

### 5.1. RedisConnectionFactory không phải adapter

RedisConnectionFactory chỉ tạo và quản lý kết nối cần thiết. Nó không tự đăng ký channels và không tự tạo Spring Messages. Listener container quản lý subscription, còn adapter đưa message đã nhận vào flow.

### 5.2. RedisMessageListenerContainer có vai trò quan trọng

Listener container giúp:

- Sử dụng connection Redis để SUBSCRIBE/PSUBSCRIBE.
- Đăng ký và bỏ đăng ký Topic/MessageListener.
- Quản lý callback và task executor phù hợp.
- Xử lý vòng đời start/stop và phục hồi subscription sau reconnect theo khả năng thư viện/client.

**Phục hồi subscription sau reconnect không đồng nghĩa tự phát lại message đã bỏ lỡ** trong khoảng thời gian mất kết nối.

### 5.3. Dữ liệu đi qua adapter

Redis Pub/Sub payload về mặt giao thức là **bytes**. Ứng dụng có thể đưa bytes đó vào Spring Message dạng byte[] hoặc chuyển thành String/DTO tùy component/serializer/transformer đang cấu hình.

**Không mặc định mọi Redis inbound adapter luôn phát String UTF-8.** Khi cần một hợp đồng chính xác, hãy test kiểu payload đầu vào và áp dụng converter/transformer một lần, rõ ràng.

## 6. Redis Pub/Sub khác Redis Streams, Redis Lists và Redis keyspace notifications

Từ **Redis inbound** có thể dẫn đến hiểu lầm rằng tất cả dữ liệu nằm trong Redis đều được nhận theo cùng một cách. Thực tế, Redis có nhiều mô hình với ngữ nghĩa khác nhau.

| Mô hình Redis | Cách ghi/đọc điển hình | Khi consumer offline | Dùng khi nào? |
| --- | --- | --- | --- |
| **Pub/Sub** | PUBLISH; SUBSCRIBE/PSUBSCRIBE | Message phát trong lúc offline không có backlog để replay | Tín hiệu cache invalidation, refresh, thông báo best-effort |
| **Streams** | XADD; XREAD/XREADGROUP; XACK | Bản ghi còn trong stream theo retention, có thể xử lý tiếp | Event quan trọng cần lịch sử, nhóm consumer, retry/recovery |
| **Lists** | LPUSH/RPUSH; BLPOP/BRPOP hoặc pattern reliability riêng | Danh sách vẫn chứa item chưa pop, tùy persistence/retention | Job queue đơn giản; cần thiết kế cách xử lý crash sau pop |
| **Keys/Hash/Set** | GET/HGET/SMEMBERS... | Dữ liệu hiện tại còn nếu được lưu bền/TTL cho phép | Tra cứu trạng thái hoặc cache, không phải một event log |
| **Keyspace notifications** | Redis phát notification về thay đổi key khi bật tính năng | Không replay khi subscriber mất kết nối | Quan sát thay đổi cache/key với chấp nhận best-effort |

### 6.1. “Dùng Redis” không có nghĩa “có queue”

Redis Pub/Sub **không quản lý danh sách pending cho từng consumer**. Nếu handler cần xác nhận mỗi đơn hàng đã được xử lý, Pub/Sub không có bộ cơ chế **consumer group + acknowledgment** như Streams.

Spring Integration MessageChannel được tạo **sau khi Redis phát và ứng dụng nhận được notification**. QueueChannel trong Spring Integration cũng không tự biến Pub/Sub thành một hệ thống delivery bền vững khi Redis subscriber bị offline.

### 6.2. Khi nào nên chọn Redis Streams?

Ví dụ:

~~~text
Tạo đơn hàng:
  Bắt buộc xử lý mỗi event dù consumer khởi động lại?
  Cần biết event nào chưa ACK?
  Cần consumer group với công việc được phân phối giữa workers?

  -> Cân nhắc Redis Streams hoặc broker bền vững.
~~~

Streams có các thao tác đọc và ACK record riêng, retention và pending-entry behavior cần thiết kế. Không thể thay một lệnh PUBLISH bằng XADD rồi giữ nguyên Redis Pub/Sub inbound channel adapter và mong endpoint tự chuyển thành stream consumer.

### 6.3. Lists cũng không mặc nhiên exactly-once

Một consumer dùng BLPOP có thể lấy item khỏi list rồi chết trước khi cập nhật DB. Nếu không có cơ chế chuyển item sang processing list, reclaim hoặc durable inbox, item có thể mất khỏi hàng đợi. Các mẫu reliable queue cho Lists phải thiết kế riêng.

**Đánh giá độ tin cậy theo ngữ nghĩa cụ thể của Redis primitive và endpoint, không theo tên sản phẩm Redis.**

### 6.4. Keyspace notifications là một trường hợp Pub/Sub đặc biệt

Redis có thể phát thông báo khi key hết hạn hoặc bị thay đổi, nếu được cấu hình **notify-keyspace-events** phù hợp. Ví dụ một channel logic cho sự kiện hết hạn:

~~~text
__keyevent@0__:expired
~~~

Điểm cần phân biệt:

- Không được bật mặc định trong mọi cấu hình Redis; cần quyền và đánh giá tải khi bật.
- Đây vẫn là notification **best-effort**, không là event store bền vững.
- Khi nhận sự kiện expired, key có thể **đã hết tồn tại**, nên không đọc lại được giá trị cũ.
- Thời điểm nhận expired notification không phải timer chính xác cho một nghiệp vụ phải chạy đúng hạn.
- Trong Redis Cluster, topology subscription và nguồn notification cần kiểm thử ở các node/shard thích hợp.

Không dùng keyspace expiration notification làm nguồn duy nhất để thực hiện nghiệp vụ tài chính hoặc xóa dữ liệu bắt buộc theo deadline. Hãy sử dụng job scheduler/event log bền vững khi yêu cầu bắt buộc.

## 7. Chọn payload contract trước khi chọn code

Redis Pub/Sub chỉ truyền **channel** và **body bytes**, không có một bảng message headers chuẩn tương đương AMQP basic properties. Vì vậy ứng dụng cần định nghĩa **envelope** hoặc một hợp đồng chuyển đổi tự quản lý.

### 7.1. Envelope đề xuất

~~~json
{
  "eventId": "evt-price-1001",
  "eventType": "PRODUCT_PRICE_CHANGED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "data": {
    "productId": "P-1001",
    "priceVnd": 150000
  }
}
~~~

| Trường | Vai trò | Cần chú ý |
| --- | --- | --- |
| eventId | Định danh sự kiện nghiệp vụ | Ổn định qua retry/republish |
| eventType | Loại nghiệp vụ | Validate allowlist, không chỉ suy từ channel |
| schemaVersion | Phiên bản dữ liệu | Cần chính sách tương thích |
| occurredAt | Thời điểm nghiệp vụ | Không đồng nghĩa thời điểm subscriber nhận |
| data | Payload miền nghiệp vụ | Giới hạn kích thước, kiểu và miền giá trị |

### 7.2. Redis channel không thay thế eventType

Channel **catalog.price.changed** giúp fan-out đúng nhóm subscriber, nhưng:

- Tên channel có thể thay đổi theo environment hoặc migration.
- PatternTopic có thể nhận nhiều loại event.
- Redis subscriber không tự xác minh payload đúng schema chỉ vì channel tên “price.changed”.

Do đó handler cần validate **eventType**, **schemaVersion**, và những field data cần thiết.

### 7.3. Không dùng message ID của Spring làm eventId

Spring Integration có thể tạo MessageHeaders.ID khi tạo Spring Message. Khi cùng event được Redis publisher gửi lại hoặc cùng body được nhận bởi instance khác, ID nội bộ đó có thể khác. Nếu cần chống xử lý trùng, phải dùng **eventId trong envelope**, hoặc một business key có contract rõ.

### 7.4. Charset, serialization và kích thước

Một publisher dùng **StringRedisTemplate** thường serialize String bằng UTF-8 theo cấu hình mặc định; một publisher khác có thể gửi bytes bằng serializer khác. Consumer cần thống nhất:

- Encoding: UTF-8 hay binary.
- Format: JSON object, text command, Protobuf...
- Kích thước tối đa, độ sâu JSON và số lượng trường.
- JSON schema/version compatibility.
- Xử lý malformed UTF-8, null field, số âm, overflow.

Nếu producer gửi JSON String đã serialize mà tầng khác serialize thêm lần nữa, consumer có thể nhận **JSON string literal** thay vì JSON object. Hãy test raw bytes và chỉ định một nơi chịu trách nhiệm serialize.

## 8. Dependencies và cấu hình môi trường

Ví dụ dùng Spring Boot, Spring Data Redis và Spring Integration Redis.

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

Sử dụng **BOM/dependency management** của Spring Boot tương ứng để chọn versions Spring Data Redis và Spring Integration phù hợp. Đừng chọn ngẫu nhiên các phiên bản không tương thích, đặc biệt khi ứng dụng dùng Java DSL hoặc Redis client thay đổi API theo thời gian.

### 8.1. Spring Boot connection properties mẫu

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 3s
      timeout: 3s
~~~

Đây là ví dụ local/test. Trong production có thể cần TLS, credentials hoặc Redis Sentinel/Cluster, timeouts và client resources theo mô hình hạ tầng. **Không ghi password thật trong tài liệu hoặc source code.**

Lưu ý: key cấu hình Boot có thể thay đổi giữa các thế hệ (ví dụ namespace của Redis properties); phải kiểm tra phiên bản Boot đang sử dụng. Mặc định một application đã có RedisConnectionFactory từ Spring Boot nếu auto-configuration phù hợp.

### 8.2. Publisher sử dụng StringRedisTemplate

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CatalogRedisPublisher {

    public static final String CHANNEL = "catalog.price.changed";
    private final StringRedisTemplate redisTemplate;

    public CatalogRedisPublisher(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public void publishRawJson(String json) {
        if (json == null || json.isBlank()) {
            throw new IllegalArgumentException("JSON body is required");
        }
        redisTemplate.convertAndSend(CHANNEL, json);
    }
}
~~~

Điều hàm này thực hiện: **publish một thông điệp vào Redis channel**, với serializer của template. Số lượng subscribers mà PUBLISH có thể báo lại **không phải** business success; không thể dựa vào nó để kết luận SearchService đã cập nhật cache.

### 8.3. Publish test bằng Redis CLI

Trong môi trường Redis test:

~~~bash
redis-cli SUBSCRIBE catalog.price.changed
~~~

Ở một terminal thứ hai:

~~~bash
redis-cli PUBLISH catalog.price.changed '{"eventId":"evt-price-1001","eventType":"PRODUCT_PRICE_CHANGED","schemaVersion":1,"data":{"productId":"P-1001","priceVnd":150000}}'
~~~

Redis CLI chỉ minh họa Pub/Sub và giúp kiểm tra topic/payload. Để test thực sự Spring Integration adapter, phải khởi động application subscriber và kiểm tra message đi qua MessageChannel/handler.

### 8.4. Không dùng cùng một connection theo cách tùy tiện

Redis Pub/Sub subscription đặt connection vào chế độ nhận messages theo cơ chế giao thức/client. Spring Data Redis listener container quản lý connection/subscription của nó. Đừng tự lấy một low-level connection đang SUBSCRIBE rồi đồng thời dùng nó để chạy những lệnh dữ liệu không phù hợp. Hãy để RedisConnectionFactory, RedisTemplate và listener container quản lý vòng đời theo library.

## 9. Cấu hình Redis inbound channel adapter theo mô hình Spring Integration

Mục tiêu cuối của adapter:

~~~text
RedisChannelTopic("catalog.price.changed")
    -> RedisInboundChannelAdapter
    -> redisInput : MessageChannel
    -> transformer
    -> handler
~~~

### 9.1. Spring MessageChannel nội bộ

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class RedisInputChannelConfiguration {

    @Bean
    public MessageChannel redisInput() {
        return new DirectChannel();
    }
}
~~~

**DirectChannel** gửi message đồng bộ tới subscriber xử lý. Nếu handler parse JSON và invalidates cache nhanh, có thể phù hợp. Nếu handler cần gọi nhiều hệ thống chậm, cần cân nhắc executor/durable handoff, không mặc định block callback Redis lâu.

### 9.2. Vai trò của RedisInboundChannelAdapter

Một Redis inbound channel adapter cấu hình đúng thường cần ít nhất:

| Cấu hình | Ý nghĩa |
| --- | --- |
| RedisConnectionFactory | Kết nối tới đúng Redis instance hoặc cluster/Sentinel; Redis không có virtual host kiểu RabbitMQ |
| Topics/Patterns | ChannelTopic hoặc PatternTopic được subscribe |
| Output MessageChannel | Nơi phát Spring Message vào flow |
| Serializer/conversion policy | Cách biểu diễn Redis bytes thành payload |
| Error channel/handler | Cách xử lý exception từ listener và downstream |
| Lifecycle | Tự subscribe khi start, unsubscribe khi stop |

**Chính sách API:** Spring Integration Redis có những thay đổi giữa phiên bản ở constructor, cấu hình topics và Java DSL factory. Khi dùng class **RedisInboundChannelAdapter** trong project, phải dựa vào API của phiên bản thực tế thay vì sao chép phương thức chỉ tồn tại ở một phiên bản. Bài cung cấp ngay sau đây một **bridge dùng public APIs của Spring Data Redis** làm minh họa chạy được logic tương đương, đồng thời làm rõ ranh giới mà adapter chuyên dụng quản lý.

### 9.3. Vì sao có ví dụ bridge thủ công?

Một bridge thủ công giúp người học thấy chính xác:

1. Redis callback nhận **byte[]** và channel bytes từ Redis server.
2. Code tạo **Spring Message<byte[]>**.
3. Gắn custom header **redisChannel** phục vụ routing/log.
4. Gửi Message đến **redisInput**.
5. IntegrationFlow áp transformer/validator/handler.

Trong production, nếu dùng RedisInboundChannelAdapter chuyên dụng, **không đăng ký đồng thời bridge thủ công trên cùng subscription chỉ để “tăng reliability”**: đó là hai subscribers độc lập và có thể làm business handler xử lý trùng. Chọn một con đường tiếp nhận rõ ràng.

## 10. Ví dụ Java: RedisMessageListenerContainer đưa dữ liệu vào MessageChannel

Ví dụ sau mô tả trực tiếp cơ chế mà một Redis inbound integration endpoint cần thực hiện. Chúng ta dùng **RedisMessageListenerContainer** và **MessageListener** từ Spring Data Redis để tạo một bridge đến **redisInput**.

**Lưu ý:** Đây là **bridge thủ công tương đương luồng nhận Pub/Sub**, không phải tuyên bố bean dưới đây có kiểu **RedisInboundChannelAdapter** của Spring Integration. Nó hữu ích để kiểm soát body bytes/channel và hiểu rõ callback. Khi project đã có adapter chuyên dụng hoạt động, dùng adapter đó thay bridge này, không duy trì cả hai subscriptions.

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
public class RedisSubscriberBridgeConfiguration {

    @Bean
    public RedisMessageListenerContainer redisListenerContainer(
            RedisConnectionFactory connectionFactory,
            @Qualifier("redisInput") MessageChannel redisInput) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);

        MessageListener listener = (message, pattern) -> {
            byte[] body = message.getBody();
            String redisChannel = new String(
                message.getChannel(), StandardCharsets.UTF_8);

            boolean accepted = redisInput.send(
                MessageBuilder.withPayload(body)
                    .setHeader("redisChannel", redisChannel)
                    .build());

            if (!accepted) {
                throw new IllegalStateException(
                    "redisInput did not accept the message");
            }
        };

        container.addMessageListener(
            listener, new ChannelTopic("catalog.price.changed"));

        return container;
    }
}
~~~

### 10.1. Nhận biết đúng điểm vào và điểm ra

- **message.getBody():** bytes thông điệp Redis subscriber nhận, chưa chắc là String/JSON hợp lệ.
- **message.getChannel():** bytes tên channel gắn với message.
- **pattern:** đối số callback về subscription pattern; có thể không cần với ChannelTopic chính xác trong ví dụ.
- **MessageBuilder:** tạo Spring Message<byte[]> để phát vào Spring Integration.
- **redisInput.send(...):** đưa thông điệp vào MessageChannel nội bộ.

Header tên **redisChannel** trong ví dụ là **custom header do chúng ta tự định nghĩa**, không phải hằng được bảo đảm bởi mọi Redis inbound adapter. Khi đổi sang adapter chuyên dụng, phải test tên và kiểu metadata channel mà adapter phát ra; không copy code kỳ vọng header redisChannel tự xuất hiện nếu không có bước mapping rõ.

### 10.2. Chỉ có một owner cho subscription

Nếu đồng thời chạy:

~~~text
RedisInboundChannelAdapter SUBSCRIBE catalog.price.changed
RedisSubscriberBridgeConfiguration SUBSCRIBE catalog.price.changed
~~~

Redis có thể phát thông điệp tới cả hai subscriptions. Nếu cả hai cùng nối vào redisInput, business handler có thể được gọi **hai lần cho một publish**. Đừng dùng hai endpoint để “backup delivery” theo suy đoán.

### 10.3. PatternTopic thay ChannelTopic

Nếu cần một nhóm kênh:

~~~java
import org.springframework.data.redis.listener.PatternTopic;

container.addMessageListener(
    listener, new PatternTopic("catalog.*"));
~~~

Đây là **phương án thay thế dòng addMessageListener** trong ví dụ, không phải yêu cầu subscribe thêm nếu một thông điệp phù hợp cả exact channel và pattern. Khi dùng pattern, handler nên kiểm tra **redisChannel** để route từng eventType phù hợp.

### 10.4. Vì sao không thêm Poller?

RedisMessageListenerContainer đã nhận callback khi Redis đẩy Pub/Sub message. Thêm poller vào flow này không làm Pub/Sub có backlog hoặc replay. Nếu cần nhận theo lịch từ Redis list/stream, dùng endpoint và dữ liệu model tương ứng.

### 10.5. Callback và xử lý lỗi

Nếu redisInput là DirectChannel, handler downstream có thể chạy **đồng bộ trong chuỗi callback listener**. Nếu handler ném exception, RedisMessageListenerContainer có thể ghi nhận lỗi theo error handler nhưng **Redis Pub/Sub không tự redeliver message chỉ vì callback Java lỗi**.

Do đó nên xác định:

1. Handler có thể xử lý nhanh không?
2. Lỗi parse/sai schema là lỗi vĩnh viễn hay tạm thời?
3. Có thể bỏ qua message này theo SLA không?
4. Nếu không thể mất message, có nguồn bền vững nào để phục hồi không?

Không retry vô hạn trong callback, vì có thể chặn listener và làm các notifications tiếp theo bị ảnh hưởng.

## 11. Spring Integration flow: decode, validate, xử lý cache

Vì bridge ở mục 10 tạo Spring Message<byte[]>, ta dùng một **transformer** để giải mã UTF-8 trước khi tới service activator.

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class CatalogRedisIntegrationFlow {

    @Bean
    public IntegrationFlow catalogRedisFlow(
            CatalogPriceHandler catalogPriceHandler) {

        return IntegrationFlow.from("redisInput")
            .transform(byte[].class,
                body -> new String(body, StandardCharsets.UTF_8))
            .handle(String.class, (json, headers) -> {
                catalogPriceHandler.accept(
                    json, headers.get("redisChannel"));
                return null;
            })
            .get();
    }
}
~~~

Trong ví dụ này, **redisInput** là DirectChannel được khai báo ở mục 9; nếu thay bridge thủ công bằng RedisInboundChannelAdapter chuyên dụng, cũng dùng kênh đầu ra cùng tên hoặc gắn output channel tương đương.

### 11.1. Decoder UTF-8 và dữ liệu lỗi

Lệnh **new String(body, UTF_8)** diễn giải bytes theo UTF-8. Trong một số cấu hình decoder, bytes sai encoding có thể được thay thế bằng ký tự replacement. Với hợp đồng yêu cầu **reject dữ liệu UTF-8 sai**, cần bộ decoder có **CodingErrorAction.REPORT** hoặc cơ chế validation tương đương, không chỉ dựa vào việc tạo được một String.

Việc convert body thành String cũng **không tự validate JSON**. Hãy parse JSON theo schema/version ở handler hoặc transformer tiếp theo.

### 11.2. Domain record và validation

~~~java
public record ProductPriceChanged(
        String eventId,
        String eventType,
        int schemaVersion,
        Data data) {

    public record Data(
            String productId,
            long priceVnd) {}
}
~~~

### 11.3. Handler dùng Jackson ObjectMapper

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

@Service
public class CatalogPriceHandler {

    private final ObjectMapper objectMapper;
    private final ProductCacheInvalidator invalidator;

    public CatalogPriceHandler(
            ObjectMapper objectMapper,
            ProductCacheInvalidator invalidator) {
        this.objectMapper = objectMapper;
        this.invalidator = invalidator;
    }

    public void accept(String json, Object channelHeader) {
        final ProductPriceChanged event;
        try {
            event = objectMapper.readValue(
                json, ProductPriceChanged.class);
        } catch (JsonProcessingException ex) {
            throw new InvalidCatalogEventException(
                "Malformed product price event", ex);
        }

        if (!"catalog.price.changed".equals(channelHeader)) {
            throw new InvalidCatalogEventException(
                "Unexpected Redis channel");
        }
        if (event == null
                || event.eventId() == null
                || event.eventId().isBlank()
                || !"PRODUCT_PRICE_CHANGED".equals(event.eventType())
                || event.schemaVersion() != 1
                || event.data() == null
                || event.data().productId() == null
                || event.data().productId().isBlank()
                || event.data().priceVnd() < 0) {
            throw new InvalidCatalogEventException(
                "Unsupported event contract");
        }

        // Cache invalidation can safely be repeated.
        invalidator.invalidate(event.data().productId());
    }
}
~~~

~~~java
public class InvalidCatalogEventException extends RuntimeException {

    public InvalidCatalogEventException(String message) {
        super(message);
    }

    public InvalidCatalogEventException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
public interface ProductCacheInvalidator {

    void invalidate(String productId);
}
~~~

**Giới hạn của ví dụ:** ProductCacheInvalidator là interface phải được triển khai (ví dụ dùng Spring Cache hoặc RedisTemplate). Nếu cache nằm trên nhiều nodes, mỗi node đang subscribe nên nhận notification khi online, nhưng có thể bỏ lỡ khi offline. Cần **TTL, refresh theo phiên bản, periodic reconciliation hoặc nguồn dữ liệu chuẩn** để tránh cache stale kéo dài.

### 11.4. Jackson không tự xuất hiện từ mọi starter

Để inject **ObjectMapper**, ứng dụng phải có Jackson và auto-configuration/bean thích hợp. Nếu starter đang dùng không cung cấp Jackson, thêm dependency JSON tương ứng (ví dụ **spring-boot-starter-json** trong môi trường Spring Boot hỗ trợ) hoặc tự cấu hình mapper, rồi kiểm tra compatibility với phiên bản Boot.

### 11.5. Body event khác header của Redis

Trong flow trên:

- eventId, eventType, schemaVersion, productId, priceVnd nằm trong **JSON payload**.
- redisChannel là một **Spring MessageHeader nội bộ** do bridge gắn.
- Redis Pub/Sub không gửi metadata messageId, contentType, deliveryTag hay correlationId theo một cơ chế wire chuẩn tương đương AMQP.

Nếu cần traceId, tenantRef hoặc schemaVersion dưới dạng header chung cho nhiều adapters, ta có thể tách chúng từ JSON envelope sang Spring MessageHeaders trong transformer; nhưng giá trị ấy vẫn phải được validate và không tự trở thành bằng chứng authorization.

## 12. RedisInboundChannelAdapter chuyên dụng và bridge thủ công: chọn thế nào?

**Tốt nhất dùng endpoint Redis inbound channel adapter có sẵn** khi Spring Integration Redis ở phiên bản dự án hỗ trợ đúng use case Pub/Sub và topic mapping. Điều đó giúp giữ cấu hình endpoint, lifecycle và integration error handling trong cùng mô hình Spring Integration.

Bridge thủ công phù hợp khi:

- Cần hiểu hoặc kiểm soát byte[]/channel mapping rất cụ thể.
- Chưa sử dụng được adapter chuyên dụng trong phiên bản/framework hiện tại.
- Phải gắn thêm metadata/validation trước khi xây Spring Message.
- Đang viết một bài test đối chiếu behavior.

| Khía cạnh | RedisInboundChannelAdapter chuyên dụng | Spring Data Redis listener bridge thủ công |
| --- | --- | --- |
| Vai trò trong Integration | Endpoint inbound tự tạo Spring Message | Tự gọi MessageBuilder và MessageChannel.send |
| Subscription | Qua API adapter/topic config | RedisMessageListenerContainer.addMessageListener |
| Lifecycle | Spring Integration endpoint + listener | Spring-managed listener container |
| Payload/header mapping | Theo contract/serializer/mapper của adapter/version | Ứng dụng tự chọn byte[] và custom header |
| Error handling | Theo endpoint/framework version | Listener error handler + exception trong callback |
| Công sức tự duy trì | Thường ít hơn | Nhiều logic mapping cần tự kiểm thử |
| Redis Pub/Sub replay | **Không** | **Không** |

**Điểm quan trọng:** Không có phương án nào trong hai cột tự tạo **durable subscriber backlog** cho Redis Pub/Sub. Lựa chọn component không thể thay đổi guarantee vốn có của Redis PUBLISH/SUBSCRIBE.

### 12.1. Đừng nhầm Spring Integration Redis inbound với Redis Stream inbound

Nếu yêu cầu cần consumer group, pending records, ACK và replay, hãy tìm đúng **Redis Streams integration** hỗ trợ bởi phiên bản Spring Data Redis/Spring Integration đang dùng, hoặc dùng một worker đọc Streams chủ động với semantics được thiết kế riêng. Không chỉ đổi kiểu Topic thành stream key trong cấu hình Pub/Sub adapter.

### 12.2. Xử lý pattern mà vẫn giữ contract

Một PatternTopic("catalog.*") có thể nhận:

~~~text
catalog.price.changed
catalog.stock.changed
catalog.product.deleted
~~~

Flow nên có router/validator dựa trên **channel + eventType** để chuyển đúng handler. Nếu chưa hỗ trợ eventType mới, chọn một đường từ chối/điều tra có kiểm soát; đừng đẩy tất cả JSON qua PriceHandler rồi coi exception của Pub/Sub là một retry queue.

### 12.3. Một application có nhiều flow Redis

Có thể đăng ký nhiều Topics trên cùng listener container hoặc nhiều adapter được tổ chức rõ ràng, tùy library và thiết kế:

~~~text
catalog.*  -> catalogInput  -> catalogRouter
search.*   -> searchInput   -> searchHandler
cache.*    -> cacheInput    -> cacheInvalidator
~~~

Giữ tách biệt ownership và error metrics. Nếu subscriptions chồng nhau, một sự kiện có thể đến nhiều nhánh; muốn mỗi event chỉ ảnh hưởng một lần tới một business side effect thì cần idempotency hoặc tránh overlap.

## 13. Delivery semantics: có những điểm mất message nào?

Mỗi bước của một flow đều có thể có lỗi:

~~~mermaid
sequenceDiagram
    participant P as CatalogService
    participant R as Redis
    participant L as Pub/Sub subscriber
    participant F as Spring Integration flow
    participant S as Cache service
    P->>R: PUBLISH price changed
    R-->>L: Notification (nếu đang subscribe)
    L->>F: MessageChannel.send
    F->>S: Invalidate cache
    Note over R,S: Không có consumer ACK/replay mặc định ở Pub/Sub
~~~

### 13.1. Mất trước khi nhận notification

Subscriber có thể offline do deploy, crash, mất mạng, Redis failover hoặc permission/configuration lỗi. Những message Pub/Sub được publish trong khoảng đó có thể **không đến subscriber**.

Khi RedisMessageListenerContainer reconnect và subscribe lại, nó có thể nhận các **message tương lai**, nhưng không có cơ chế yêu cầu Redis Pub/Sub phát lại mọi message trong khoảng downtime.

### 13.2. Mất sau khi đã nhận notification

Redis client có thể đã nhận body bytes, nhưng application:

- Chưa kịp tạo Spring Message.
- Đang xử lý qua DirectChannel thì lỗi parse.
- Đưa công việc vào ExecutorChannel rồi process crash.
- Ghi cache/database thất bại.

Ngay cả khi framework ghi exception, Redis Pub/Sub cũng **không tự tạo lại delivery có ACK/NACK** như consumer queue. Vì vậy exception handling phải bám sát **SLA mất message có được chấp nhận hay không**.

### 13.3. Subscriber nhận cùng event nhiều lần có thể không?

Mặc dù Pub/Sub thường được mô tả là at-most-once tại tầng phân phối cho một thông điệp publish, **một business event vẫn có thể đến nhiều lần** nếu:

- Producer chủ động PUBLISH lại cùng event.
- Hai nguồn tạo cùng eventId.
- Application đăng ký nhiều subscription trùng nhau.
- Một event được republish qua một bridge/retry workflow khác.

At-most-once **không đồng nghĩa exactly-once ở tầng business**. Nếu handler có side effect không idempotent, cần eventId, version hoặc một cơ chế bảo vệ phù hợp.

### 13.4. Không tồn tại “queue depth của Pub/Sub channel”

Với một Redis channel Pub/Sub thông thường:

- Không có danh sách records được lưu bền cho mỗi subscriber.
- Không có pending messages cần ACK theo nhóm consumer.
- Không có offset để subscriber mới đọc lại từ một vị trí cũ.
- Không có DLQ tự động cho một handler thất bại.

Một metric **PUBLISH count** hoặc **current subscribers** không phải bằng chứng toàn bộ events đã được các business handlers xử lý.

### 13.5. Chọn hướng xử lý theo mức quan trọng của event

| Event | Khi mất một notification | Thiết kế thường phù hợp |
| --- | --- | --- |
| Vô hiệu hóa cache | Cache có thể stale tạm thời | Pub/Sub + TTL/version refresh/reconciliation |
| Trigger refresh dashboard | Dashboard có thể hiển thị cũ đến lần refresh tiếp | Pub/Sub có thể chấp nhận |
| Cập nhật một database projection có thể rebuild | Có thể tái tạo từ nguồn sự thật | Pub/Sub chỉ là hint, có periodic rebuild |
| Đơn hàng phải được xử lý một lần | Không thể bỏ lỡ | Redis Streams/AMQP/Kafka/JMS hoặc durable outbox phù hợp |
| Giao dịch thanh toán | Mất thông điệp gây sai nghiệp vụ nghiêm trọng | Durable event/workflow + idempotency/đối soát |

**Tiêu chí lựa chọn không phải throughput Redis nhanh hay chậm**, mà là ranh giới độ tin cậy, khả năng phục hồi và yêu cầu đã hoàn tất nghiệp vụ.

## 14. Chống mất cache invalidation: TTL và nguồn dữ liệu chuẩn

Redis inbound Pub/Sub rất phù hợp để gửi **cache invalidation hints** nếu hệ thống chấp nhận được một khoảng stale có giới hạn.

Giả sử SearchService có cache sản phẩm cục bộ. CatalogService cập nhật giá trong database rồi PUBLISH price changed. Nếu SearchService offline vài giây, nó có thể bỏ lỡ notification và giữ cache cũ.

### 14.1. Kết hợp nhiều lớp bảo vệ

~~~mermaid
flowchart TD
    DB["Catalog DB<br/>source of truth"] --> U["Write price"]
    U --> P["Publish invalidation hint"]
    P --> R["Redis Pub/Sub"]
    R --> S["SearchService invalidate cache"]
    DB --> V["Periodic / on-demand revalidation"]
    V --> S
    S --> C["Local cache with TTL"]
~~~

Các lớp có thể phối hợp:

1. **TTL:** cache tự hết hạn, dù một event bị bỏ lỡ.
2. **Version/ETag:** khi đọc lại, xác minh dữ liệu so với version mới nhất.
3. **Periodic reconciliation:** quét các records thay đổi từ nguồn dữ liệu chuẩn và refresh.
4. **Invalidate idempotent:** xóa một cache key nhiều lần vẫn không gây side effect nguy hiểm.
5. **Nguồn sự thật:** database/catalog service được coi là nơi xác định giá cuối cùng.

### 14.2. Không chỉ PUBLISH trước DB commit

Nếu CatalogService PUBLISH trước khi transaction DB commit rồi transaction rollback, subscribers đã nhận tín hiệu về một thay đổi không thành công. Với invalidation, việc xóa cache dư có thể không nguy hiểm, nhưng vẫn tạo tải và khó chẩn đoán.

Nếu sự kiện bắt buộc phải tương ứng với transaction commit, hãy cân nhắc **after-commit publish** hoặc **transactional outbox**; tuy nhiên:

- **After-commit publish** vẫn có khoảng mất event nếu process crash sau commit trước publish.
- **Outbox** ghi intent cùng transaction, hỗ trợ phát lại sau restart.
- Publish qua Redis Pub/Sub **vẫn không bảo đảm subscriber offline nhận được**; muốn downstream replay, phải thay hoặc bổ sung một durable event stream/queue.

### 14.3. Tránh cập nhật trạng thái theo thứ tự notification

Ví dụ event A thông báo giá 100.000, event B thông báo giá 120.000. Nếu các notifications/handlers có thứ tự xử lý không mong muốn, code trực tiếp ghi giá từ message cũ có thể ghi đè giá mới.

Với cache invalidation, **xóa key rồi đọc lại source of truth** thường an toàn hơn việc tin vào thứ tự notification để áp một state mới. Nếu phải apply event, cần **productVersion/sequence monotonic**, kiểm tra out-of-order và concurrency.

## 15. Thread model, backpressure và các loại MessageChannel

Redis subscriber callback cần trả lời câu hỏi: **khi downstream chậm thì phải làm gì?**

### 15.1. DirectChannel

~~~text
Redis callback thread
  -> DirectChannel.send()
  -> Transformer
  -> Service activator
  -> return callback
~~~

DirectChannel có ưu điểm:

- Lỗi của handler có thể lan đồng bộ về chuỗi gọi, dễ quan sát.
- Không tạo một queue task nội bộ lớn nếu handler nhanh.
- Phù hợp các thao tác idempotent ngắn như invalidate cache.

Nhược điểm: handler chậm có thể **giữ thread xử lý notification**, gây backlog trong client hoặc tăng rủi ro mất nhận dưới tải, tùy listener container và Redis client. Không gọi HTTP timeout nhiều phút ngay trong callback mà không có thiết kế capacity.

### 15.2. ExecutorChannel

~~~text
Redis callback -> ExecutorChannel -> executor queue -> worker
                  send() có thể return trước khi worker xong
~~~

ExecutorChannel tách thời gian thực thi business khỏi callback nếu executor đủ capacity. Nhưng:

- Khi process crash, task trong memory queue có thể mất.
- Redis Pub/Sub không tự redeliver.
- Executor có thể reject khi queue đầy.
- Một số lỗi business xảy ra ở thread khác; không thể dựa vào try/catch của publisher/subscriber callback để bắt đủ.

Nếu chọn ExecutorChannel, cần bounded queue, RejectedExecutionHandler policy, metrics và quyết định rõ khi quá tải. **Không gọi đây là durable backpressure**.

### 15.3. QueueChannel

QueueChannel có thể đệm nội bộ rồi một poller/consumer tiếp tục xử lý:

~~~mermaid
flowchart LR
    R["Redis Pub/Sub"] --> IA["Inbound adapter"]
    IA --> Q["QueueChannel<br/>bounded memory"]
    Q --> P["Internal poller/consumer"]
    P --> H["Business handler"]
~~~

**Redis inbound adapter vẫn là message-driven**; nếu sau đó dùng QueueChannel, poller chỉ tiêu thụ **queue nội bộ**, không phải poll Redis Pub/Sub. QueueChannel mặc định không phải hàng đợi bền vững qua process restart.

Spring Integration hỗ trợ những cơ chế persistent MessageStore trong một số kiểu queue channel, nhưng cấu hình đó không thay đổi việc Redis Pub/Sub có thể mất message **trước khi adapter nhận và lưu vào store**.

### 15.4. Khi downstream bắt buộc phải lưu bền

Một phương án:

~~~text
Redis Pub/Sub subscriber
  -> validate
  -> insert durable inbox/job
  -> background worker processes job
~~~

Phương án này bảo vệ **những notification đã tới và được ghi vào inbox**, nhưng không khôi phục được events phát khi subscriber offline. Nếu yêu cầu không bỏ lỡ, cần bổ sung/đổi nguồn phát thành durable event stream hoặc một cơ chế đối soát từ database nguồn.

### 15.5. Fan-out nội bộ và fan-out Redis là hai tầng khác nhau

Redis Pub/Sub broadcast cho mọi **Redis subscribers**. Trong Spring Integration, **PublishSubscribeChannel** có thể fan-out một Spring Message cho nhiều subscribers **trong cùng application**. Không nhầm hai tầng này:

~~~text
Redis PUBLISH 1 lần
  -> App A subscriber
       -> PublishSubscribeChannel -> handler 1 + handler 2
  -> App B subscriber
       -> PublishSubscribeChannel -> handler 1 + handler 2
~~~

Một event có thể gây nhiều business side effects nếu không định nghĩa ownership. Với tác vụ chỉ nên xảy ra một lần trên toàn cluster, Pub/Sub broadcast tới mọi instance có thể không phù hợp.

## 16. Error handling trong Redis inbound flow

Redis Pub/Sub không có consumer NACK/ACK để broker quyết định requeue. Vì vậy, lỗi ứng dụng phải được xử lý ở tầng Spring Integration và nguồn dữ liệu nghiệp vụ.

### 16.1. Phân loại lỗi

| Lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Malformed message** | JSON không parse được, UTF-8 lỗi | Log metadata an toàn, cách ly nếu có nơi lưu bền |
| **Unsupported schema** | schemaVersion=3 nhưng handler chỉ hiểu 1 | Fail fast, cảnh báo compatibility, không retry nóng |
| **Unauthorized/invalid source** | EventType/channel không nằm trong allowlist | Reject tại business boundary, đánh dấu security signal |
| **Transient downstream** | Cache server/HTTP tạm lỗi | Retry ngắn có giới hạn; sau đó ghi durable job hoặc reconcile |
| **Slow handler** | HTTP call bị treo, DB lock | Timeout, circuit breaker, bounded workers, backpressure |
| **Redis reconnect** | Redis failover/network partition | Giám sát outage và đối soát missed period |
| **Unexpected exception** | NullPointerException, lỗi mapping | Error flow/alert; không giả định Redis tự gửi lại |

### 16.2. ErrorChannel khác hệ thống retry bền vững

Spring Integration có cơ chế **ErrorMessage/errorChannel** cho lỗi trong flow, tùy cách endpoint/channel/handler được cấu hình. Nó giúp xử lý, ghi nhận và định tuyến exception, nhưng:

- Không làm Redis Pub/Sub có pending log.
- Không sinh ACK/NACK Pub/Sub để broker phát lại message.
- Không mặc nhiên lưu body lỗi vào database.
- Có thể không bắt được mọi exception xảy ra **trước khi Spring Message được tạo**.

Nếu error flow chỉ log exception rồi kết thúc, notification thất bại vẫn có thể biến mất khỏi góc nhìn subscriber. Nếu yêu cầu phục hồi, hãy **ghi payload hoặc business key vào durable error store** và có cơ chế retry/reconcile riêng.

### 16.3. Retry giới hạn cho lỗi tạm thời

Không đặt một retry vô hạn trong Redis listener callback. Ví dụ chiến lược:

~~~text
Attempt 1: invalidate cache -> timeout
Backoff 200 ms
Attempt 2: invalidate cache -> timeout
Backoff 400 ms
Attempt 3: invalidate cache -> success
~~~

Nếu ba attempts đều lỗi, thay vì giữ listener bận vô hạn có thể ghi một durable refresh request hoặc dựa vào TTL/reconciliation theo SLA. Retry ở đây là **application retry**, không phải Redis Pub/Sub redelivery.

### 16.4. Khi nhận dữ liệu lỗi, có DLQ không?

Redis Pub/Sub không có **DLX/DLQ** broker-native như RabbitMQ AMQP. Muốn có “error queue”, bạn phải tự thiết kế một **Redis Stream/List, database error table, Kafka topic, RabbitMQ queue** hoặc nguồn lưu bền khác.

**Đừng đặt tên một Redis channel là dlq rồi nghĩ rằng messages sẽ được giữ để replay.** PUBLISH tới channel đó vẫn là Pub/Sub, subscriber offline có thể mất message.

### 16.5. Biên lỗi quan trọng nhất

~~~mermaid
flowchart TD
    R["Redis message"] --> C["Transport / listener callback"]
    C --> M["Create Spring Message"]
    M --> T["Decode + validate"]
    T --> H["Business handler"]
    C -. "Connection / callback error" .-> E["Listener error handling"]
    M -. "Bridge/channel error" .-> E
    T -. "Payload/schema error" .-> F["Integration error flow"]
    H -. "Business error" .-> F
    E --> O["Observe / alert / recover externally"]
    F --> O
~~~

Thiết kế tốt phải xác định **lỗi được phát hiện ở đâu**, **có giữ được body không**, **có tài nguyên lưu bền không** và **làm sao khôi phục được**. Một exception stack trace trong log không thay thế được cơ chế retry đáng tin cậy.

## 17. Vòng đời subscription, reconnect và graceful shutdown

Redis Pub/Sub có một subscription gắn với **kết nối đang hoạt động**. Vì thế cần phân biệt việc component Spring còn RUNNING và việc Redis subscriber thật sự đang kết nối/nhận messages.

### 17.1. Khi ứng dụng khởi động

~~~mermaid
sequenceDiagram
    participant APP as Spring Application
    participant LC as RedisMessageListenerContainer
    participant R as Redis
    participant F as IntegrationFlow
    APP->>LC: Initialize / start
    LC->>R: Connect + SUBSCRIBE topics
    APP->>F: Start integration endpoints
    R-->>LC: New messages after subscription
    LC->>F: Spring Messages
~~~

Một Spring ApplicationContext có thể đã khởi động nhưng Redis chưa kết nối được hoặc đang trong giai đoạn resubscribe. Nếu readiness của service phụ thuộc việc nhận Redis events, cần liveness/readiness/metrics theo trạng thái subscriber thực tế, không chỉ kiểm tra process còn sống.

### 17.2. Khi mất connection

Các tình huống:

- Redis server restart/failover.
- Mất mạng tạm thời.
- Client Redis reconnect do socket timeout.
- ACL/credential thay đổi.
- Application quá tải và không xử lý callback kịp.

RedisMessageListenerContainer có thể có cơ chế recovery/resubscription theo client và phiên bản; nhưng **những messages phát trong thời gian offline không thể được Redis Pub/Sub replay**.

Vì vậy recovery phải có **hai tầng riêng**:

1. **Khôi phục kết nối/subscription** để nhận những message tương lai.
2. **Khôi phục tính đúng nghiệp vụ** cho khoảng mất kết nối bằng TTL, reconciliation hoặc nguồn dữ liệu/event log bền vững.

Một log “Redis connected” chỉ phản ánh tầng thứ nhất.

### 17.3. Graceful shutdown

Một quy trình hợp lý:

1. Ngừng nhận công việc mới theo lifecycle của ứng dụng khi chuẩn bị shutdown.
2. Cho những callbacks/handlers đang thực thi hoàn tất trong một khoảng giới hạn.
3. Dừng listener container/adapter theo cơ chế Spring lifecycle.
4. Đóng connection theo quản lý của RedisConnectionFactory/client, không đóng nguồn dùng chung tùy tiện.
5. Khi restart, resubscribe và thực hiện reconciliation nếu yêu cầu cache/state cần cập nhật.

**Graceful shutdown không khiến Redis lưu lại events được publish sau khi subscriber ngừng nhận.** Dù shutdown không có exception, Pub/Sub vẫn là một kết nối nhận best-effort.

### 17.4. Khi scale từ một lên nhiều replicas

Nếu triển khai ba SearchService replicas đều subscribe **catalog.price.changed**, mỗi replica có thể nhận một event:

~~~text
Redis channel
  -> SearchService-1 invalidates local cache
  -> SearchService-2 invalidates local cache
  -> SearchService-3 invalidates local cache
~~~

Đây thường là behavior mong muốn cho cache cục bộ. Nhưng nếu cả ba replicas ghi một row audit hoặc kích hoạt thanh toán, side effect có thể bị lặp theo số replicas.

Khi cần **một worker trong nhóm** xử lý mỗi event, Pub/Sub không cung cấp consumer group semantics. Dùng Redis Streams consumer groups hoặc broker/queue được thiết kế cho competing consumers.

### 17.5. Khi Redis chạy Cluster/Sentinel

Không tự giả định một client Pub/Sub subscribe tới một node ngẫu nhiên sẽ có đúng behavior tương đương mọi topology Redis, đặc biệt khi dùng sharded Pub/Sub/keyspace notifications hoặc khi hạ tầng failover.

- Kiểm tra hỗ trợ client Redis và version server.
- Xác định kênh thông thường hay sharded Pub/Sub.
- Kiểm thử phát từ node/đường kết nối publisher thực tế và subscriber thực tế.
- Kiểm tra reconnect, resubscribe và khoảng mất messages.
- Không dùng Redis database index làm biên cô lập Pub/Sub channel theo cách áp dụng cho keys; dùng namespace/prefix, ACL và hạ tầng phù hợp.

## 18. Security và trust boundary của Redis Pub/Sub

Redis Pub/Sub là một kênh trao đổi dữ liệu giữa các ứng dụng. Một message từ channel quen thuộc **không tự xác thực nội dung nghiệp vụ** hoặc đảm bảo producer có quyền thay đổi dữ liệu.

### 18.1. Redis ACL, TLS và network

Thiết kế production nên kiểm tra:

- Quyền **PUBLISH** chỉ cho những channel/namespace cần thiết.
- Quyền **SUBSCRIBE/PSUBSCRIBE** chỉ cho những channel/namespace cần thiết.
- Redis ACL phù hợp với phiên bản server, bao gồm hạn chế kênh Pub/Sub nếu hỗ trợ.
- Kết nối dùng TLS và credential management theo policy của tổ chức.
- Không lộ Redis password/connection string trong log, image hoặc mã nguồn.
- Không subscribe pattern quá rộng khi ứng dụng chỉ cần một nhóm sự kiện.

Redis ACL cho Pub/Sub có cú pháp/chính sách riêng theo phiên bản; không suy ra chỉ có quyền key GET/SET thì cũng có quyền tương ứng cho mọi channel.

### 18.2. Không tin eventType/tenantId từ message ngoài

Ví dụ một publisher gửi:

~~~json
{
  "eventId": "evt-123",
  "eventType": "PRODUCT_PRICE_CHANGED",
  "tenantId": "other-tenant",
  "data": {
    "productId": "P-1",
    "priceVnd": 1
  }
}
~~~

Nếu SearchService xử lý đa tenant, không thể chỉ nhìn **tenantId** trong JSON rồi cập nhật dữ liệu của tenant đó. Phải có một **nguồn xác thực/trust policy** giữa producer và consumer và validation quyền tenant tương ứng.

**Tên Redis channel không phải authentication token**. Một message nhận qua prod.catalog.* chỉ chứng minh nó được gửi theo đường Redis đó, không chứng minh payload được phép thao tác một tenant nhất định.

### 18.3. Không dùng native Java serialization với input không tin cậy

Trong Spring Data Redis/Spring Integration, serializer có thể khác nhau. Tránh deserialize native Java objects từ payload không tin cậy hoặc bật trusted types quá rộng. Với event liên dịch vụ, ưu tiên **JSON schema/Protobuf/Avro** với target type được kiểm soát, validation, size limit và versioning.

### 18.4. Chống payload lớn và injection

Đặt giới hạn:

- Số bytes tối đa mỗi Pub/Sub message.
- JSON nesting depth và số lượng fields.
- Độ dài eventId/productId/tenantRef.
- Giá trị số có miền hợp lệ và chống integer overflow.
- Số topics/patterns subscribe.
- Rate limits/backpressure ở producer nếu workload có burst.

Không đưa raw event vào câu SQL/Redis key động hoặc expression language với quyền cao mà không validate. Nếu business logic dùng tên channel để chọn downstream routing, phải có whitelist các đích hợp lệ.

### 18.5. Logging và PII

Log metadata hữu ích:

~~~text
integrationEndpoint=catalogRedisInbound
redisChannel=catalog.price.changed
eventId=evt-price-1001
eventType=PRODUCT_PRICE_CHANGED
schemaVersion=1
processingStatus=VALIDATION_FAILED
errorCode=INVALID_PRODUCT_ID
~~~

Không log toàn bộ payload chứa dữ liệu cá nhân hoặc thông tin thanh toán chỉ để debug, không in Redis credentials hoặc token, và không dùng eventId làm metric label có cardinality cao.

## 19. Observability: đo gì khi Pub/Sub không có backlog?

Với Redis Pub/Sub, không thể dùng duy nhất **queue depth** hay **consumer lag offset** như một durable event stream để kết luận subscriber có đang theo kịp hay đã bỏ lỡ message.

| Tín hiệu | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| Subscription active / connection state | Subscriber có kết nối/đăng ký không | Không cho biết messages đã bỏ lỡ lúc offline |
| PUBLISH attempts/success | Producer đã gọi Redis publish ra sao | Không chứng minh handler nghiệp vụ thành công |
| Subscriber receive count | Số messages đã tới callback | Không có đối chứng durable nếu không ghi event/source count |
| Handler success/error | Số events parse/xử lý thành công hoặc lỗi | Không phản ánh events mất trước callback |
| Last received event timestamp | Phát hiện subscription im lặng bất thường | Có thể không có publisher activity hợp lệ |
| Processing latency p50/p95/p99 | Downstream handler có chậm không | Không là Redis broker delivery guarantee |
| Redis reconnect/resubscribe count | Tần suất gián đoạn | Không cho biết chính xác số notifications bị mất |
| Cache stale age / reconciliation gap | Mức độ đúng của dữ liệu ứng dụng | Cần đo từ source of truth |

### 19.1. Redis PUBSUB NUMSUB có ích nhưng không đủ

Redis có lệnh dùng để xem số subscribers trên channel, ví dụ:

~~~bash
redis-cli PUBSUB NUMSUB catalog.price.changed
~~~

Đây là một **ảnh chụp trạng thái subscriber hiện tại** (và còn tùy ngữ nghĩa khi dùng pattern/cluster). Nó không phải kết quả business processing, không thay log ở consumer và không chứng minh sự kiện phát trong khoảng downtime đã được replay.

### 19.2. Metric gợi ý

~~~text
redis_pubsub_received_total{channel="catalog.price.changed"}
redis_pubsub_validation_failed_total{eventType="PRODUCT_PRICE_CHANGED"}
redis_pubsub_handler_failed_total{errorClass="TransientCacheError"}
redis_pubsub_reconnect_total
redis_pubsub_processing_duration_seconds
catalog_cache_reconciliation_lag_seconds
~~~

Đây là **tên metric thiết kế minh họa**, không phải cam kết Spring Integration tự xuất các metric đó. Nếu dùng Micrometer/Observation, hãy chọn labels có cardinality thấp; **không đưa eventId, productId hoặc payload tùy ý làm label**.

### 19.3. Đo mất event bằng sequence/version từ nguồn

Redis Pub/Sub không tự cấp consumer offset, nhưng producer có thể định nghĩa **productVersion/sequence** trong sự kiện hoặc nguồn trạng thái bền vững. Nếu consumer thấy version nhảy:

~~~text
product P-1001:
  lastAppliedVersion = 7
  receivedVersion    = 10
~~~

thì có cơ sở nghi ngờ thiếu update trung gian và **refetch từ source of truth**. Cách này hiệu quả hơn chỉ nhìn PUBLISH subscriber count để kết luận không mất dữ liệu.

### 19.4. Cảnh báo theo SLA

Cần cảnh báo những trường hợp:

- Redis listener liên tục reconnect hoặc offline quá ngưỡng.
- Parser/handler errors tăng sau deploy.
- Một nhóm cache không được refresh lâu hơn TTL/SLA.
- Downstream queue/executor saturation.
- Latency nhận → handler tăng bất thường.
- Data reconciliation phát hiện phiên bản stale kéo dài.

Không dùng cùng một ngưỡng heartbeat cho mọi channel nếu publisher hợp lệ chỉ phát event khi có thay đổi.

## 20. Kiểm thử Redis inbound channel adapter

Unit test logic parse/cache không chứng minh đã SUBSCRIBE đúng channel. Muốn xác thực endpoint Redis, cần **integration test với Redis server thật trong môi trường test** và các messages có eventId xác định.

### 20.1. Ma trận kiểm thử

| Trường hợp | Thiết lập | Điều phải xác minh |
| --- | --- | --- |
| **Happy path** | Subscriber đã start, PUBLISH JSON hợp lệ | Message tới redisInput và handler được gọi |
| **Sai channel** | PUBLISH channel khác | Handler không nhận nếu subscription chỉ exact channel |
| **Pattern match** | Dùng PatternTopic("catalog.*") | Chỉ những channels hợp lệ được chuyển vào flow |
| **Overlap topics** | Exact topic và pattern cùng khớp | Phát hiện nếu handler được gọi nhiều lần |
| **Malformed JSON** | Body không parse được | Validation error được quan sát; không giả định Redis requeue |
| **UTF-8 lỗi** | Publish bytes invalid | Strict decoder hoặc validation phát hiện |
| **SchemaVersion không hỗ trợ** | Event version mới hơn | Reject/alert có kiểm soát |
| **Payload lớn** | Body vượt limit | Bảo vệ memory/parser; không crash listener |
| **Consumer offline** | Stop subscriber trước khi PUBLISH | Không nhận message cũ sau restart; chứng minh giới hạn Pub/Sub |
| **Redis restart/reconnect** | Restart Redis giữa messages | Resubscribe nhận messages mới, test reconciliation gap |
| **Callback lỗi** | Service activator ném exception | Error handler/metrics, không có broker ACK/replay |
| **Handler chậm** | Sleep/test delayed downstream | Đo callback throughput và client pressure |
| **ExecutorChannel** | Giao task async rồi kill app | Phát hiện rủi ro mất task trong memory |
| **Nhiều app replicas** | Hai subscribers cùng channel | Cả hai có thể nhận một publish |
| **Cache idempotency** | PUBLISH cùng eventId hai lần | Không tạo side effect nguy hiểm |
| **Out-of-order** | Gửi version 10 rồi version 9 | Consumer không ghi đè state mới bằng state cũ |
| **ACL** | User subscribe sai channel | Thấy lỗi quyền, không im lặng giả vờ subscribe |
| **Shutdown** | Stop app khi đang xử lý | Lifecycle đúng và phương án khôi phục cache |
| **Redis cluster/sentinel** | Test topology thực tế | Subscription/reconnect hợp lệ sau failover |
| **Keyspace notifications** | Bật event type trong broker test | Nhận notification nhưng không suy ra history |

### 20.2. Test nên publish sau khi subscription đã được đăng ký

Với Redis Pub/Sub, nếu test gọi PUBLISH **trước khi Redis subscriber thật sự active**, message có thể bị mất và assertion sẽ timeout, dù code routing/handler hoàn toàn đúng. Test cần có bước **readiness xác minh subscription active**, không chỉ đợi Spring ApplicationContext dựng xong rồi gửi ngay.

Tránh dùng **Thread.sleep(1000)** làm bảo đảm tuyệt đối. Dùng health/readiness từ listener, latch/subscriber status hoặc các điều kiện đồng bộ phù hợp trong test broker/Redis server thực tế.

### 20.3. Test callback dùng CountDownLatch

Ví dụ một handler test quan sát message nhận được:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CapturingRedisHandler {

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

Trong Spring test, có thể thay business handler bằng spy/test handler hoặc một integration test flow riêng để gọi **CapturingRedisHandler.accept(...)**, sau đó:

1. Khởi động Redis và subscription, xác minh đã subscribe.
2. PUBLISH JSON trên channel test.
3. Đợi latch, assert payload hoặc eventId.
4. Kiểm tra header redisChannel/metadata theo hợp đồng của endpoint.
5. Dừng subscriber, publish thêm event, restart và xác minh event cũ **không tự phát lại**.

**Mã latch là một helper**, không phải integration test hoàn chỉnh có application context và Redis server; tránh nhầm việc compile helper với kết luận endpoint thực hoạt động.

### 20.4. Unit test domain handler tách khỏi Redis

Test riêng **CatalogPriceHandler** với một ObjectMapper và ProductCacheInvalidator giả lập:

~~~text
Input: eventId=evt-price-1001,
       eventType=PRODUCT_PRICE_CHANGED,
       schemaVersion=1,
       productId=P-1001,
       priceVnd=150000
Expected: invalidate("P-1001") exactly once for this invocation.
~~~

Thêm test malformed JSON, wrong event type, unsupported schema, productId rỗng, priceVnd âm. Những test này chứng minh business logic, không chứng minh Redis subscription.

### 20.5. Không chạy test mất kết nối trên Redis production

Restart Redis, đổi ACL, cố tình kill subscriber hoặc publish payload độc hại phải được thực hiện ở **môi trường cô lập**. Có thể dùng một Redis test container/process do test sở hữu, không làm gián đoạn Redis đang phục vụ các ứng dụng khác.

## 21. Ba tình huống thiết kế thực tế

### 21.1. Tình huống A: invalidation cache của ba application replicas

**Yêu cầu:** CatalogService cập nhật giá; SearchService chạy ba replicas với cache cục bộ. Mỗi replica cần bỏ cache sản phẩm khi nhận event.

~~~mermaid
flowchart LR
    CAT["Catalog DB + CatalogService"] --> P["Redis PUBLISH"]
    P --> CH["catalog.price.changed"]
    CH --> A["Search replica A<br/>Redis inbound"]
    CH --> B["Search replica B<br/>Redis inbound"]
    CH --> C["Search replica C<br/>Redis inbound"]
    A --> CA["Local cache A"]
    B --> CB["Local cache B"]
    C --> CC["Local cache C"]
~~~

**Lựa chọn hợp lý:** Redis Pub/Sub broadcast phù hợp cho invalidation **best-effort**; mỗi replica cần xử lý một notification. Cache eviction nên idempotent, có TTL và lấy lại dữ liệu từ nguồn chuẩn.

**Failure mode quan trọng:** Replica B restart trong lúc PUBLISH và không nhận event. Khi quay lại, cache cũ có thể còn trong bộ nhớ nếu state được khôi phục hoặc Redis/local cache không được xóa; cần TTL, version refresh hoặc xóa cache khi startup.

**Không nên dùng:** Pub/Sub như nguồn duy nhất để cập nhật số dư hay dữ liệu không thể rebuild sau khi bỏ lỡ.

### 21.2. Tình huống B: cập nhật projection cần không mất event

**Yêu cầu:** ProductPriceChanged phải cập nhật một bảng báo cáo giá. Nếu consumer offline, khi trở lại phải nhận các thay đổi chưa xử lý.

~~~mermaid
flowchart LR
    CAT["Catalog transaction"] --> OUT[("Durable outbox")]
    OUT --> WORK["Publisher worker"]
    WORK --> STREAM["Redis Stream / durable broker"]
    STREAM --> GROUP["Consumer group"]
    GROUP --> DB[("Analytics projection")]
    GROUP -. "ACK sau xử lý" .-> STREAM
~~~

**Lựa chọn:** Không dùng Redis Pub/Sub inbound channel adapter như transport duy nhất. Cân nhắc **Redis Streams consumer group** hoặc Kafka/AMQP/JMS có cơ chế delivery phù hợp, phối hợp outbox và idempotent consumer.

**Tại sao:** Mô hình này cần offset/record history/pending/retry, khác bản chất với SUBSCRIBE/PUBLISH. Thay đổi adapter không thể bù lại guarantee không tồn tại trong Pub/Sub.

### 21.3. Tình huống C: SFTP import → Redis notification

**Yêu cầu:** Hệ thống nhập CSV sản phẩm từ SFTP mỗi tối, cập nhật database rồi thông báo các dịch vụ cache refresh.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound adapter<br/>poller"] --> PAR["CSV parse + validate"]
    PAR --> DB[("Catalog DB")]
    DB --> OUT["Commit / durable outbox"]
    OUT --> REDIS["Redis Pub/Sub publisher"]
    REDIS --> IN["Redis inbound adapter"]
    IN --> C["Cache refresh handler"]
~~~

Điểm cần chốt:

1. **SFTP poller** chọn file nguồn; các file chưa xử lý có thể được quét lại theo filter/metadata phù hợp.
2. **Database transaction** quyết định sản phẩm đã được cập nhật.
3. **Redis publish** là notification cho cache, không tự chứng minh các subscribers đang online.
4. **Redis inbound adapter** chỉ nhận thông báo trong lúc subscriber kết nối.
5. **Cache TTL/reconciliation** đảm bảo eventual consistency sau missed notification.

Không xóa file SFTP gốc hoặc đánh dấu toàn pipeline hoàn tất chỉ vì Redis PUBLISH trả về số subscriber >0 nếu yêu cầu nghiệp vụ còn cần đối soát database/import.

### 21.4. Tình huống D: Redis Pub/Sub → Kafka

Một integration flow có thể nhận Pub/Sub message rồi publish sang Kafka. Tuy nhiên:

~~~text
Redis PUBLISH
  -> Redis inbound adapter
  -> transformer
  -> Kafka outbound adapter
~~~

Nếu adapter/transformer nhận Redis message nhưng Kafka broker chưa xác nhận publish thì application crash, nguồn Redis Pub/Sub **không có backlog để replay**. Nếu Kafka thực sự đã lưu nhưng ứng dụng không biết kết quả, có thể publish trùng khi ứng dụng tự retry.

Đối với bridge cần không mất event, nên đặt **durable boundary** trước hoặc tại điểm nguồn, ví dụ outbox/stream do producer ghi và consumer có thể đọc lại. Một Kafka producer được cấu hình đúng không tự sửa được việc **Redis Pub/Sub source đã mất message** trước khi bridge nhận.

## 22. Troubleshooting: không nhận được message thì kiểm tra gì?

Một vấn đề hay gặp: Redis CLI thấy PUBLISH thành công, nhưng Spring Integration handler không chạy. Không nên đoán ngay mapper hoặc Redis client lỗi; kiểm tra tuần tự:

1. **Redis instance/endpoint:** publisher và subscriber có cùng Redis server/topology không?
2. **Channel name:** subscription là catalog.price.changed hay prod.catalog.price.changed? Có typo/case mismatch không?
3. **Pattern syntax:** PatternTopic có khớp channel thực không?
4. **Lifecycle:** listener container/adapter đã start, subscribe xong chưa?
5. **ACL/network:** client được phép SUBSCRIBE/PUBLISH channel đó không?
6. **Pub/Sub timing:** publish có xảy ra trước khi subscriber online không?
7. **Body serialization:** payload bytes mà converter/transformer mong đợi có giống producer tạo không?
8. **MessageChannel:** outbound header/payload từ adapter có được channel chấp nhận, có subscriber phù hợp không?
9. **Handler error:** transformer/filter/service activator có ném exception hoặc loại message không?
10. **Async flow:** ExecutorChannel có đang đầy, reject task hoặc worker bị treo không?
11. **Scaling:** cùng event có đến nhiều replicas, gây nhiều callbacks không?
12. **Cluster/Sentinel:** client có subscribe đúng topology và reconnect sau failover không?

### 22.1. Phân biệt Redis CLI nhận được và ứng dụng nhận được

Một terminal dùng:

~~~bash
redis-cli SUBSCRIBE catalog.price.changed
~~~

chỉ chứng minh **terminal đó** đã subscribe, không chứng minh Java listener cũng subscribe đúng instance/channel. Một PUBLISH trả về số subscribers >0 có thể chỉ phản ánh CLI hoặc ứng dụng khác, không phải business consumer đang hoạt động.

### 22.2. Handler được gọi nhưng cache không đổi

Khi handler log eventId thành công nhưng cache vẫn stale:

- Cache key của SearchService có đúng productId/tenant không?
- Mỗi replica có cache local riêng không?
- Có TTL/refresh policy không?
- EventType/schemaVersion có được validate không?
- Invalidation xảy ra sau commit của source DB chưa?
- Một background worker có repopulate cache từ bản ghi cũ không?
- Có event out-of-order so với productVersion không?

**Không tự kết luận Redis mất message nếu callback đã chạy.** Vấn đề có thể ở business semantics và cơ chế cache riêng.

### 22.3. Error log tăng nhưng Redis Pub/Sub vẫn hoạt động

Redis connection có thể tốt trong khi mọi messages đều malformed JSON hoặc schemaVersion không hỗ trợ. Một subscriber vẫn RUNNING không có nghĩa dữ liệu đang được xử lý thành công. Theo dõi **validation errors và handler success** tách riêng metrics connection.

### 22.4. Một topic nhận quá nhiều sự kiện

Nếu PatternTopic quá rộng và traffic tăng:

- Chọn exact channels khi có thể.
- Đặt giới hạn payload/schema.
- Tách luồng theo event type/ownership.
- Đánh giá callback thread pool và downstream latency.
- Giảm coupling: chỉ gửi notification tối thiểu, consumer refetch source state.
- Nếu cần retention/throttling/replay, chuyển sang transport có queue/stream phù hợp.

## 23. Những hiểu lầm phổ biến

**“Redis inbound channel adapter đọc từ Redis List.”** Bài này nói về Redis **Pub/Sub**. Redis Lists/Streams có cơ chế và endpoint khác, cần thiết kế riêng.

**“Có MessageChannel thì Redis Pub/Sub tự giữ backlog.”** MessageChannel là trừu tượng nội bộ sau khi message đã tới application; Redis Pub/Sub vẫn không lưu message chờ subscriber offline.

**“PUBLISH trả về 1 nghĩa là consumer đã cập nhật DB.”** Con số phản ánh subscriber matching theo lệnh, không phải business acknowledgment.

**“Subscribe lại sau reconnect sẽ nhận mọi message bỏ lỡ.”** Redis Pub/Sub không hỗ trợ replay lịch sử cho subscriber.

**“PUBSUB NUMSUB bằng 1 nghĩa là đúng service cần nhận đang chạy.”** Có thể là CLI/instance khác; con số không phải business success.

**“Hai SearchService replicas trên một Redis channel sẽ chia việc mỗi người một nửa.”** Pub/Sub broadcast tới subscribers, không phải consumer group competing consumers.

**“Dùng PatternTopic(*) luôn tiện hơn.”** Pattern rộng làm tăng tải, giảm isolation và mở rộng nguồn dữ liệu không tin cậy.

**“Một message nhận từ exact topic chắc chắn có đúng eventType.”** Tên topic không thay schema validation.

**“Spring MessageHeaders.ID là khóa idempotency ổn định.”** ID này có thể thay đổi khi event được tạo/nhận lại, hãy dùng eventId nghiệp vụ.

**“Cứ nhận Redis message là payload String UTF-8.”** Redis vận chuyển bytes; serializer/transformer quyết định kiểu payload Java.

**“Đã decode UTF-8 thành String thì JSON chắc chắn hợp lệ.”** Cần parse JSON và validate field/schemaVersion.

**“RedisMessageListenerContainer là Kafka consumer group.”** Listener container quản lý Pub/Sub subscription; không có offset/pending/ACK như Streams/Kafka.

**“Thêm poller giúp Redis Pub/Sub nhận lại message cũ.”** Poller không tạo dữ liệu lịch sử chưa từng được lưu trong Pub/Sub.

**“Dùng ExecutorChannel là có durable queue.”** Executor tasks thường ở memory; process crash có thể làm mất task.

**“QueueChannel mặc định giữ message qua restart.”** QueueChannel mặc định không phải event log bền vững; cần MessageStore phù hợp và vẫn không sửa gap ở Redis source.

**“ErrorChannel có thể NACK một Redis Pub/Sub message.”** Pub/Sub không có consumer ACK/NACK broker-native; error flow phải dùng nguồn retry/reconcile riêng.

**“Redis có DLQ như RabbitMQ.”** Redis Pub/Sub không có DLX/DLQ; đặt tên channel là dlq không tạo message persistence.

**“Nếu cache invalidation có thể mất thì hệ thống sai ngay.”** Có thể chấp nhận nếu contract có TTL/revalidation/nguồn sự thật và SLA stale rõ; với giao dịch quan trọng thì không phù hợp.

**“Pub/Sub at-most-once nghĩa là business event không bao giờ trùng.”** Producer retry hoặc overlapping subscriptions có thể tạo xử lý trùng ở business level.

**“Keyspace expired notification là durable event log.”** Keyspace notifications vẫn là Pub/Sub best-effort; key có thể đã bị xóa khi event đến.

**“Redis database index tách Pub/Sub channels như vhost.”** Channel namespace và ACL phải được thiết kế riêng; không sử dụng Redis key database index như ranh giới Pub/Sub authorization/broadcast tuyệt đối.

**“StringRedisTemplate luôn dùng cùng serializer với mọi app.”** Producer và consumer có thể cấu hình khác; phải test raw payload bytes.

**“PUBLISH trước database commit tương đương after-commit.”** Event có thể phát dù transaction nguồn rollback.

**“Transactional outbox + Redis Pub/Sub bảo đảm subscriber offline nhận lại.”** Outbox phục hồi lần publish từ producer; Pub/Sub vẫn không có subscriber replay.

**“Thêm nhiều subscribers cùng channel làm message đáng tin hơn.”** Nhiều recipients không giúp một subscriber offline nhận lại message cũ; nó có thể nhân số side effects.

**“Một listener RUNNING chứng minh app đã xử lý mọi event.”** Cần metrics handler, reconciliation và xác nhận nguồn dữ liệu.

**“Tăng concurrency tự sửa lỗi schema.”** Không; tăng concurrency có thể chỉ làm số callbacks lỗi tăng nhanh hơn.

**“Header redisChannel trong ví dụ là Redis wire header tiêu chuẩn.”** Redis Pub/Sub chỉ có channel/body; header redisChannel được bridge tự tạo trong Spring Message.

**“Spring Integration Redis inbound adapter và bridge thủ công cần chạy song song cho an toàn.”** Hai subscribers có thể nhận hai bản message logic và gây duplicate.

## 24. Checklist trước khi đưa Redis inbound flow vào production

| Nhóm | Câu hỏi cần xác nhận |
| --- | --- |
| **Use case** | Event có thể mất khi subscriber offline không? Nếu không thì vì sao chọn Pub/Sub? |
| **Topic contract** | Channel/pattern tên gì, ai sở hữu, có namespace environment/tenant không? |
| **Fan-out** | Mỗi app instance đều cần nhận event hay chỉ một worker trong consumer group? |
| **Payload** | Body text/JSON/binary? Serializer, charset và max payload size? |
| **Schema** | eventId/eventType/schemaVersion có không? Kiểm tra compatibility thế nào? |
| **Inbound adapter** | Component nào subscribe, ai quản lý listener container và output channel? |
| **Subscription overlap** | Có exact ChannelTopic và PatternTopic cùng match gây double callback không? |
| **Channel type** | DirectChannel, ExecutorChannel hay QueueChannel? Khi process crash, task có mất không? |
| **Business handling** | Handler có side effect idempotent không? Có source-of-truth refresh? |
| **Lost event** | Có TTL/reconciliation hoặc durable event log để phục hồi không? |
| **Connection** | RedisConnectionFactory, TLS, ACL, timeouts, Sentinel/Cluster được test chưa? |
| **Lifecycle** | Listener auto-start, reconnect/resubscribe và graceful shutdown ra sao? |
| **Errors** | Malformed JSON, unsupported schema và downstream failures đi đâu? |
| **Backpressure** | Callback chậm, executor queue đầy, rate burst được xử lý thế nào? |
| **Security** | Ai có quyền PUBLISH/SUBSCRIBE? Có tin tenantId trong payload một cách sai lầm không? |
| **Monitoring** | Receive/handler success/error/reconnect/reconciliation gap có metric/alert không? |
| **Testing** | Test publisher khi subscriber offline và không có replay chưa? |
| **Version upgrade** | API RedisInboundChannelAdapter và serializer/header behavior đã được kiểm tra với phiên bản thực? |

### 24.1. Quy tắc lựa chọn nhanh

Nếu yêu cầu chỉ là **“có thay đổi, hãy cập nhật lại cache khi đang online”**, Redis Pub/Sub inbound adapter là một lựa chọn gọn nhẹ. Nếu yêu cầu là **“không một event nghiệp vụ nào được bỏ sót; có thể replay sau downtime”**, cần một durable event stream/queue hoặc một nguồn sự thật và cơ chế đối soát đủ mạnh. **Không lấy tên inbound adapter làm lời bảo đảm delivery.**

### 24.2. Kiểm tra ranh giới trước khi optimize

Trước khi tăng số callbacks, thread pool hoặc thay DirectChannel:

1. Kiểm tra Redis subscription đã đúng và không overlap.
2. Kiểm tra payload/charset/schema.
3. Xác định bao nhiêu handler errors là lỗi dữ liệu cố định.
4. Đo handler latency và executor saturation.
5. Kiểm tra TTL/reconciliation gap và SLA của dữ liệu.
6. Sau đó mới điều chỉnh concurrency/connection pool theo workload thực.

### 24.3. Checklist khi thay Redis Pub/Sub bằng Redis Streams

Không chỉ đổi tên channel; cần quyết định:

- Stream key và cách XADD dữ liệu.
- Consumer group và danh tính consumer.
- Cách ACK record sau mốc xử lý/lưu bền.
- Pending messages, reclaim và max delivery attempts.
- Retention/trimming của stream.
- Idempotent consumer và dữ liệu out-of-order.
- Error stream/DLQ có thể replay.
- Monitoring lag/pending/consumer health.

Những yếu tố này không thuộc guarantee mặc định của Redis Pub/Sub inbound adapter.

## 25. Câu hỏi tự kiểm tra

1. Redis inbound channel adapter giải quyết ranh giới nào giữa Redis và Spring Integration?
2. Vì sao Redis Pub/Sub inbound adapter là **message-driven** thay vì polling?
3. Redis PUBLISH truyền gì và subscriber nhận những loại thông tin nào?
4. ChannelTopic và PatternTopic khác nhau như thế nào? Khi nào nên dùng từng loại?
5. Nếu subscriber không online lúc publisher gửi, Redis Pub/Sub có giữ backlog cho subscriber đó không?
6. Vì sao Redis Pub/Sub không tương đương Redis Streams consumer group?
7. PUBLISH trả về số subscribers >0 có chứng minh handler nghiệp vụ thành công không?
8. Khi chạy ba replicas cùng subscribe một channel, mỗi replica có thể nhận điều gì?
9. Đâu là sự khác biệt giữa Redis Pub/Sub broadcast và competing consumers trên một queue?
10. RedisMessageListenerContainer có trách nhiệm gì? RedisConnectionFactory có trách nhiệm gì?
11. Trong bridge Java minh họa, Redis bytes được lấy từ đâu và chuyển thành Spring Message thế nào?
12. Header **redisChannel** trong ví dụ do Redis broker tự phát hay ứng dụng tự gắn?
13. Vì sao cần biết payload thực tế là byte[] hay String trước khi viết transformer?
14. Thông điệp text/plain và JSON cần xử lý schema, charset khác nhau thế nào?
15. Tại sao eventId trong payload cần ổn định qua các lần publish lại?
16. Nếu vừa ChannelTopic("catalog.price.changed") vừa PatternTopic("catalog.*"), có rủi ro gì?
17. DirectChannel có lợi thế và rủi ro gì khi handler chạy lâu?
18. ExecutorChannel có bảo đảm những task đã giao vào queue nội bộ không bị mất khi process crash không?
19. QueueChannel cần poller nội bộ trong một số flow có làm Redis Pub/Sub trở thành polling source không?
20. Vì sao Redis connection reconnect thành công chưa giải quyết được những notifications bị bỏ lỡ?
21. Cache TTL và source-of-truth reconciliation giúp xử lý giới hạn Pub/Sub thế nào?
22. Nếu business event buộc phải xử lý không mất một record, nên cân nhắc cấu trúc dữ liệu hoặc broker nào?
23. Transactional outbox khôi phục vấn đề gì, và vì sao không tự tạo subscriber replay cho Redis Pub/Sub?
24. Nếu CatalogService PUBLISH trước DB commit rồi rollback, SearchService có thể nhận trạng thái không nhất quán thế nào?
25. Khi key hết hạn, keyspace notification có đảm bảo đọc lại được giá trị key đã hết hạn không?
26. Vì sao keyspace notifications không nên là nguồn duy nhất cho tác vụ cần chạy đúng deadline?
27. Một event được publish lại dù Pub/Sub at-most-once có thể gây duplicate nghiệp vụ như thế nào?
28. Redis Pub/Sub có consumer ACK, offset, pending và DLQ mặc định như Redis Streams/Kafka/AMQP không?
29. Khi JSON decode lỗi trong listener, Redis có tự redeliver sau một exception Java không?
30. Nếu muốn bảo vệ message đã nhận trước khi chạy worker bất đồng bộ dài, có thể lưu vào đâu?
31. Nếu vẫn muốn recover messages đã phát trong lúc subscriber offline, durable inbox sau subscriber có đủ không? Vì sao?
32. Những Redis ACL và network constraints nào cần kiểm tra khi subscribe pattern rộng?
33. Vì sao eventType hoặc tenantId trong JSON không được tự động coi là thông tin authorization?
34. Metric nào theo dõi receive/handler errors, metric nào giúp đo missed notifications gián tiếp?
35. Tại sao PUBSUB NUMSUB không thể thay consumer health/business metrics?
36. Trong case ba replicas cache, có nên chỉ cho một replica nhận notification không? Vì sao?
37. Trong case cập nhật database projection bắt buộc, Redis Streams khác Pub/Sub ở những khả năng nào?
38. Nếu Redis inbound đưa message sang Kafka outbound, có thể mất event tại những ranh giới nào?
39. Test nào chứng minh một Redis Pub/Sub subscriber không nhận lại message được phát khi đang offline?
40. Khi nâng Spring Boot/Spring Data Redis/Spring Integration, cần xác minh API, serializers và subscription behavior nào?

## Tổng kết

**Redis inbound channel adapter** đưa các thông điệp **Redis Pub/Sub** từ subscriber/listener container vào **Spring Integration MessageChannel**, rồi cho phép các thành phần transformer, filter, router và service activator xử lý theo hợp đồng ứng dụng. Đây là một **message-driven inbound adapter một chiều**: Redis PUBLISH phát notification, adapter nhận rồi tạo Spring Message; không có request–reply nghiệp vụ hay polling định kỳ mặc định.

Tính năng quan trọng nhất cần ghi nhớ là **Redis Pub/Sub không lưu backlog để subscriber offline replay và không có cơ chế consumer ACK/NACK** tương đương Redis Streams hoặc broker queue bền vững. Reconnect giúp nhận **thông điệp tương lai**, không phục hồi lịch sử bị bỏ lỡ. Với notification như cache invalidation, hãy kết hợp **idempotent handler, TTL, version check và periodic reconciliation**. Với event bắt buộc không được mất, cân nhắc **Redis Streams, outbox và durable broker/queue** thay vì kỳ vọng MessageChannel hay errorChannel tự bổ sung delivery guarantee.

Về triển khai, cần quản lý **RedisConnectionFactory, topics/patterns, listener lifecycle, serializer/charset, schemaVersion, Redis inbound adapter output channel, thread model và error handling**. Các ví dụ với StringRedisTemplate, RedisMessageListenerContainer, MessageBuilder và IntegrationFlow chỉ rõ ranh giới dữ liệu Redis bytes → Spring Message → handler; production nên ưu tiên endpoint Redis inbound channel adapter chuyên dụng khi API/version đáp ứng yêu cầu và test hành vi thực tế.

Khi tích hợp Redis với File, SFTP, HTTP, JMS, AMQP, Kafka hoặc database trong **SPRING_INTEGRATION_ADAPTERS**, hãy tách biệt rõ **đã publish**, **đã được subscriber nhận**, **đã lưu bền** và **đã hoàn tất nghiệp vụ**. Thiết kế tốt dựa trên mức bảo đảm của hệ thống nguồn, hợp đồng message ổn định, giới hạn lỗi và khả năng khôi phục có thể kiểm chứng — không dựa vào tên của một adapter.
