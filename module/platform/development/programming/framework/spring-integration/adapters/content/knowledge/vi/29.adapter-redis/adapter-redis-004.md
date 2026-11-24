# Redis stream inbound adapter

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cách **Redis Stream inbound channel adapter** sử dụng **Reactive StreamReceiver** để chuyển bản ghi Redis Streams thành Spring Integration **Message** trên **MessageChannel**.
- Phân biệt **XREAD** độc lập, **XREADGROUP** theo consumer group, **Redis Pub/Sub inbound**, **Redis List queue inbound** và **Redis store inbound**.
- Xác định ý nghĩa của **stream key**, **Record ID**, **field/value map**, **consumer group**, **consumer name**, **ReadOffset**, **Pending Entries List (PEL)** và **XACK**.
- Cấu hình **ReactiveRedisStreamMessageProducer** với **ReactiveRedisConnectionFactory**, nhóm consumer, manual acknowledgment, offset, timeout, batch size và output channel.
- Sử dụng **Redis.streamInboundChannelAdapter(...)** trong Java DSL; phân biệt **extractPayload(true/false)** và các header metadata về stream.
- Thiết kế handler **validate → idempotent business commit → acknowledgment** và hiểu tác động nếu ACK quá sớm hoặc quá muộn.
- Phân loại lỗi parsing, network, business transient/permanent; xử lý poison records, pending entries, reclaim và dead-letter theo chính sách ứng dụng.
- Thiết kế retention, trimming, replay, backpressure, consumer concurrency, scaling, security và observability.
- Kiểm thử happy path, consumer offline, crash trước/sau commit, redelivery, pending recovery, serializer mismatch và nâng cấp schema.

## 1. Bài toán: sự kiện phải còn khi consumer offline

Giả sử **OrderService** phát sự kiện **ORDER_CREATED**. Dịch vụ **FulfillmentService** cần nhận để tạo shipping request, nhưng có thể tạm ngừng trong lúc triển khai hoặc mất kết nối.

~~~text
Redis Stream key: orders:events
Stream record ID: 1795410000123-0
Fields:
  eventId       = evt-order-1001
  eventType     = ORDER_CREATED
  schemaVersion = 1
  orderId       = O-1001
  tenantRef     = T-1
~~~

Với **Redis Pub/Sub** thông thường, notification được phát lúc consumer offline **không được giữ lại để phát lại cho subscriber**. Với **Redis Streams**, publisher ghi một **record có ID vào cấu trúc dữ liệu lưu trên Redis**; một consumer có thể đọc lại những records chưa bị retention/trimming loại bỏ.

Spring Integration hỗ trợ **Redis Stream Inbound Channel Adapter** để biến các stream records đó thành Spring Messages:

~~~mermaid
flowchart LR
    P["OrderService<br/>XADD"] --> R[("Redis Stream<br/>orders:events")]
    R --> RX["Reactive StreamReceiver<br/>XREADGROUP"]
    RX --> A["Redis stream<br/>inbound adapter"]
    A --> C["Spring Integration<br/>MessageChannel"]
    C --> V["Validate + idempotency"]
    V --> H["Fulfillment handler"]
    H --> DB[("Business DB")]
    H -. "ACK after commit" .-> R
~~~

**Mục tiêu không phải chỉ nhận được một message**, mà là xác định ba mốc riêng:

1. Redis đã lưu record bằng **XADD**.
2. Consumer đã nhận record qua **XREADGROUP**, record có thể nằm trong **PEL** nếu chưa ACK.
3. Business handler đã hoàn tất và consumer gọi **XACK** phù hợp.

Một sự kiện có thể nằm ở trạng thái 1 hoặc 2 mà **chưa từng hoàn thành nghiệp vụ**. Không dùng “adapter nhận được message” thay cho business success.

Bài thuộc chương **Adapter Redis** của module **SPRING_INTEGRATION_ADAPTERS**. Trong bối cảnh kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và MessageChannel, Redis Streams là một nguồn **message-driven dựa trên reactive stream polling**, với mô hình lưu record, consumer group và acknowledgement khác File/SFTP, HTTP, JMS, AMQP, Kafka, Redis Pub/Sub hoặc Redis List.

## 2. Redis Streams là gì?

Redis Stream là một cấu trúc dữ liệu **append-oriented** với các records có **ID được sắp thứ tự**. Mỗi record chứa các cặp field/value. Lệnh phổ biến:

~~~redis
XADD orders:events * eventId evt-order-1001 eventType ORDER_CREATED schemaVersion 1 orderId O-1001
~~~

Redis trả về ID record, ví dụ:

~~~text
1795410000123-0
~~~

Đó là **Redis Stream ID**, không phải eventId nghiệp vụ. Nó thường có hai phần được biểu diễn như **millisecondsTime-sequence**, được Redis gán khi dùng dấu sao; record IDs vẫn cần xử lý như định danh vận chuyển, không đồng nghĩa timestamp domain hay ID thanh toán.

### 2.1. Một stream record có những gì?

~~~text
Redis Stream record
  stream key: orders:events
  record ID: 1795410000123-0
  fields:
    eventId: evt-order-1001
    eventType: ORDER_CREATED
    schemaVersion: "1"
    orderId: O-1001
~~~

Redis Streams không mặc nhiên có AMQP-style **contentType/correlationId/replyTo** standard properties. Nếu các giá trị này cần cho hợp đồng, định nghĩa chúng trong **record fields** hoặc cơ chế encode/metadata rõ ràng.

### 2.2. Redis Stream ID khác eventId

| Định danh | Nguồn tạo | Phạm vi | Dùng cho |
| --- | --- | --- | --- |
| **Redis Stream record ID** | Redis XADD / client chọn theo quy tắc stream | Một record trong một stream | Offset, XACK, PEL, tracing delivery |
| **eventId** | Producer/business service | Một sự kiện nghiệp vụ qua retry | Idempotency, audit, đối soát |
| **Spring MessageHeaders.ID** | Spring Messaging runtime | Một Spring Message nội bộ | Quan sát/integration routing nội bộ |
| **correlationId** | Theo business contract | Một request/workflow nếu cần | Ghép nghiệp vụ hoặc tracing |
| **traceId/spanId** | Observability instrumentation | Trace/span | Theo dõi phân tán |

Nếu producer **XADD cùng business event hai lần**, Redis có thể cấp **hai record IDs khác nhau**, dù cả hai chứa một eventId. Vì thế consumer vẫn cần **idempotent processing**.

### 2.3. XADD không có nghĩa business handler đã hoàn tất

XADD thành công xác nhận thao tác ghi vào Redis theo điều kiện server/client. Nó không bảo đảm:

- Record sẽ được giữ mãi, vì stream có thể bị trim/xóa.
- Consumer đang online.
- Consumer đã ACK.
- Database/object storage hoặc payment provider đã commit.
- Redis đã nhân bản/lưu bền theo mức durability mong muốn trong mọi tình huống failover.

Khi cần RPO/RTO chặt, xem chính sách Redis persistence, replication và failover cùng với producer acknowledgement.

## 3. So sánh bốn loại Redis inbound

| Endpoint/mô hình | Dữ liệu nguồn | Cách nhận | Khi consumer offline | ACK/recovery |
| --- | --- | --- | --- | --- |
| **Redis Pub/Sub inbound** | Channel notification | SUBSCRIBE/PSUBSCRIBE | Message mới không được giữ cho subscriber offline | Không có consumer ACK/replay Pub/Sub |
| **Redis queue inbound** | Redis List | Blocking POP (thường BRPOP) | Items chưa pop còn trong List | POP phá hủy; phải tự tạo processing/ACK |
| **Redis store inbound** | List/Set/ZSet/Map/Properties | Spring Integration Poller nhận **RedisStore view** | Store hiện tại có thể còn | Poll/view không tự claim một item |
| **Redis Stream inbound** | Redis Stream | Reactive StreamReceiver, XREAD/XREADGROUP | Records có thể đọc lại trong retention | Consumer group PEL/XACK, recovery cần thiết kế |

### 3.1. Không thêm Spring Poller vào stream inbound một cách máy móc

Redis Stream inbound adapter dùng **reactive StreamReceiver** với vòng **XREAD/XREADGROUP**, thường có cấu hình **pollTimeout** cho Redis blocking read. Nó **không phải** một RedisStoreMessageSource cần Pollers.fixedDelay(...) như Redis store inbound.

Một adapter message-driven có thể **chủ động đọc** Redis; “message-driven” không có nghĩa Redis gửi PUBLISH đến listener. Quan trọng là **ai quản lý vòng receive**: ở đây là StreamReceiver, không phải một Spring Integration SourcePollingChannelAdapter.

### 3.2. Streams không tự biến side effect thành exactly-once

Nếu worker xử lý DB thành công rồi crash trước XACK, record vẫn ở PEL và có thể được claim lại. Nếu consumer XACK trước DB commit, crash có thể khiến record được đánh dấu đã ACK dù nghiệp vụ thất bại.

Vì thế Redis Streams thường dùng theo tư duy **at-least-once với manual ACK/recovery**, kết hợp **eventId và idempotent business handler**, chứ không tuyên bố exactly-once end-to-end.

## 4. XREAD độc lập và XREADGROUP có consumer group

Redis Streams có hai đường nhận chính.

### 4.1. Standalone XREAD

~~~redis
XREAD COUNT 10 BLOCK 1000 STREAMS orders:events 0-0
~~~

Lệnh này có thể đọc records sau ID được chỉ định. Client tự quản lý offset; Redis **không tự lưu PEL theo consumer group** cho một standalone XREAD.

Nếu hai ứng dụng độc lập cùng XREAD một stream từ những offsets tương ứng, cả hai có thể nhận cùng records; đây không phải competing consumers.

### 4.2. Consumer-group XREADGROUP

~~~redis
XGROUP CREATE orders:events fulfillment-v1 0-0 MKSTREAM
XREADGROUP GROUP fulfillment-v1 worker-a COUNT 10 BLOCK 1000 STREAMS orders:events >
~~~

Giải thích:

- **fulfillment-v1**: consumer group, có trạng thái tiến độ/pending riêng.
- **worker-a**: consumer name trong nhóm.
- **COUNT 10**: số lượng records tối đa Redis trả cho một lệnh đọc, không phải số business commits.
- **BLOCK 1000**: timeout chờ dữ liệu ở Redis, không phải retry business.
- **>**: với consumer group, yêu cầu records **chưa được giao tới consumer khác trong nhóm** theo tiến độ group.

Nếu worker crash sau XREADGROUP nhưng trước XACK, record có thể **nằm trong PEL**. Một lời gọi XREADGROUP với **>** ở worker khác **không tự đọc lại mọi pending record**; cần cơ chế đọc/claim pending phù hợp.

### 4.3. Nhóm khác nhau nhận các bản logic khác nhau

~~~mermaid
flowchart LR
    R["Redis Stream<br/>orders:events"] --> G1["Group fulfillment-v1"]
    R --> G2["Group analytics-v1"]
    G1 --> A["Worker fulfillment A"]
    G1 --> B["Worker fulfillment B"]
    G2 --> C["Analytics worker C"]
~~~

Trong **cùng group**, workers có thể chia records; **giữa các groups**, mỗi group có tiến độ nhận riêng. Một record có thể được xử lý một lần theo mục đích của mỗi group, nhưng vẫn có duplicate deliveries khi retry/recovery.

Không tạo **group mới mỗi lần ứng dụng restart** nếu muốn tiếp tục xử lý trạng thái pending của group cũ.

## 5. Consumer group, PEL và XACK

**Pending Entries List (PEL)** là trạng thái do Redis giữ cho các records đã được group giao đến consumer nhưng **chưa được ACK**.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as Redis Stream + group PEL
    participant A as Consumer A
    participant B as Business DB
    P->>R: XADD eventId=evt-1001
    A->>R: XREADGROUP GROUP fulfillment-v1 worker-a >
    R-->>A: Record ID 1795410000123-0
    Note over R,A: Record đã delivered, ở PEL
    A->>B: Validate + commit business
    B-->>A: Commit OK
    A->>R: XACK orders:events fulfillment-v1 1795410000123-0
    Note over R,A: XACK xóa pending entry cho group
~~~

### 5.1. XACK không xóa record khỏi stream

XACK **loại record ID khỏi PEL của một consumer group**, không tương đương XDEL và không tự cắt giảm stream length. Record có thể vẫn còn trong stream để một group khác đọc hoặc cho phép replay theo retention.

### 5.2. Trạng thái sau crash

| Điểm crash | Redis record | Group PEL | Business outcome |
| --- | --- | --- | --- |
| Trước XADD | Chưa có nếu chưa ghi | Không | Producer phải quyết định retry/outbox |
| Sau XADD, trước group delivery | Còn nếu chưa trim | Chưa pending | Có thể nhận về sau |
| Sau XREADGROUP, trước business commit | Còn nếu chưa trim | **Pending** | Chưa biết/xử lý chưa xong |
| Sau business commit, trước XACK | Còn nếu chưa trim | **Pending** | Đã hoàn tất nhưng có thể duplicate |
| Sau XACK | Có thể còn | Không còn pending cho group | Chỉ biết ack, không tự chứng minh business state |

**Chính sách ACK an toàn thường là sau mốc commit bền vững**; khi kết quả provider không rõ sau timeout, phải đối soát trước khi ACK hoặc retry theo contract.

### 5.3. Không lấy pending count làm completed count

Redis PEL thấp có thể do **autoAck quá sớm**, stream đã bị trim hoặc handler ACK ngay sau nhận. Nó không chứng minh mọi order đã được fulfill.

Metrics cần tách **XADD**, **delivered**, **business committed**, **XACK**, **pending idle** và **reclaimed**.

## 6. ReadOffset: chọn điểm bắt đầu nhận

**ReadOffset** ảnh hưởng trực tiếp tới việc consumer có đọc được backlog mong muốn hay không. Spring Data Redis cung cấp các chiến lược như **latest()**, **from(recordId)** và **lastConsumed()**.

| Chế độ | Ý nghĩa trong thiết kế | Điều cần lưu ý |
| --- | --- | --- |
| **ReadOffset.latest()** | Đọc records mới từ thời điểm hiện tại theo cách Redis định nghĩa offset cuối | Có thể bỏ lỡ records trước khi bắt đầu/giữa các lần poll |
| **ReadOffset.from(id)** | Đọc records sau ID được chỉ định | Cần lưu/checkpoint ID và chọn vị trí có chủ đích |
| **ReadOffset.lastConsumed()** | Trong consumer group: tiếp tục theo tiến độ group, thường dùng cho records chưa giao | Không tự quét PEL của records đã giao nhưng chưa ACK |

### 6.1. Default của adapter

Theo Spring Integration API, **ReactiveRedisStreamMessageProducer** mặc định có **ReadOffset.latest()** cho standalone XREAD. Khi chuyển sang **consumer group** bằng consumer name và offset vẫn là mặc định latest, adapter có cơ chế chuyển phù hợp sang **lastConsumed()**.

Điều này rất quan trọng: đừng chỉ nhìn Java source thiếu setReadOffset rồi đoán rằng consumer group sẽ đọc lịch sử từ ID 0-0. **Group creation offset** và **read offset của worker** là hai quyết định riêng.

### 6.2. Group được tạo từ đầu hay từ cuối stream?

Redis CLI minh họa hai lựa chọn:

~~~bash
# Bắt đầu group từ đầu stream còn được giữ:
redis-cli XGROUP CREATE orders:events fulfillment-v1 0-0 MKSTREAM

# Ví dụ trên một tên group khác, chỉ nhận records được append sau thời điểm tạo:
redis-cli XGROUP CREATE orders:events analytics-new '$' MKSTREAM
~~~

Ở đây **0-0** định nghĩa vị trí khởi đầu cho group khi được tạo, còn **$** chỉ vị trí cuối tại thời điểm tạo. Không dùng hai lệnh trên với cùng group name rồi kỳ vọng Redis cho phép tạo lại nhóm đã tồn tại.

Khi Spring Integration **setCreateConsumerGroup(true)**, endpoint có thể tự tạo group/stream nếu chưa tồn tại; cần test chính xác **offset khởi tạo** và behavior với dữ liệu có trước trong version đang dùng. Nếu yêu cầu đọc backlog lịch sử, hãy **provision group với offset rõ ràng trước khi adapter chạy** rồi để adapter dùng group đã tạo.

### 6.3. Consumer group offset không phải PEL recovery

Một lỗi thiết kế thường gặp:

~~~text
Worker A đọc msg-1 -> PEL pending
Worker A crash
Worker B khởi động và XREADGROUP ... >
Worker B nhận msg-2, msg-3

msg-1 có thể vẫn pending ở A.
~~~

Consumer group lưu trạng thái delivered/unacknowledged, nhưng **new deliveries** không tự dọn PEL của workers chết. Phải có **XPENDING + XCLAIM/XAUTOCLAIM** hoặc quy trình recovery phù hợp.

### 6.4. Standalone latest có khoảng trống giữa polls

Spring Data Redis cảnh báo ReadOffset.latest() có thể bỏ qua records được thêm trong khoảng “dead time” giữa những lần XREAD. Reactive StreamReceiver còn có cơ chế backpressure làm ngừng/pause polling khi không có demand.

Nếu cần tránh mất records khi dùng standalone consumption, chọn offset dựa trên **last seen ID/checkpoint**, hoặc dùng consumer group với retention/PEL recovery. Không mặc định một reactive Flux + latest sẽ cho durable replay hoàn chỉnh.

### 6.5. Không đánh đồng OFFSET với business checkpoint

Ngay khi Redis group đã giao một record, **last-delivered ID** có thể tiến lên, trong khi handler chưa commit. Business checkpoint nằm ở **eventId, trạng thái database, idempotency** và **XACK thành công** theo chính sách.

## 7. Stream inbound là reactive: kiến trúc StreamReceiver

Spring Integration Redis Stream inbound được giới thiệu từ **Spring Integration 5.4** dưới dạng **ReactiveRedisStreamMessageProducer**. Thành phần sử dụng **Spring Data Redis StreamReceiver** để tạo một dòng records và gửi Spring Messages vào output channel.

~~~mermaid
flowchart LR
    REDIS[("Redis Stream")] -->|"XREAD/XREADGROUP"| REC["StreamReceiver"]
    REC --> FL["Reactive Flux of Records"]
    FL --> ADP["ReactiveRedisStreamMessageProducer"]
    ADP --> MSG["Spring Message<br/>payload + headers"]
    MSG --> MC["MessageChannel"]
    MC --> HAND["Business / Validation"]
    HAND -. "ACK callback" .-> REDIS
~~~

### 7.1. Reactive ở transport không làm mọi handler non-blocking

**StreamReceiver** có thể đọc bất đồng bộ và sử dụng backpressure của Reactor, nhưng nếu bạn nối vào **DirectChannel** và gọi JDBC/HTTP blocking trong handler, đường xử lý vẫn có những đoạn **blocking**.

Cần xác định:

- Có dùng reactive output channel/FluxMessageChannel không?
- Handler có gọi blocking API không?
- Reactor threads và boundedElastic/thread pool nào thực hiện việc nặng?
- Khi downstream chậm, records có bị delivered vào PEL nhiều hơn khả năng xử lý không?
- Khi flow async, lúc nào mới gọi acknowledgment callback?

Không coi tên **ReactiveRedisStreamMessageProducer** là cam kết toàn pipeline non-blocking hoặc tự backpressure business service.

### 7.2. Standalone XREAD so với XREADGROUP

Theo API adapter, mặc định nó có thể đọc như standalone client **XREAD**; để chuyển sang consumer group **XREADGROUP**, đặt **consumerName** và **consumerGroup** phù hợp. Consumer name nên **duy nhất trong cùng group đối với các instances đang hoạt động**.

Không tạo cùng consumerName cho mọi replica trừ khi bạn đã chủ động thiết kế recovery/ownership và kiểm chứng Redis behavior. Ví dụ dùng **worker-a**, **worker-b** thay vì mọi container đều là **worker-1**.

### 7.3. StreamReceiverOptions

**StreamReceiverOptions** của Spring Data Redis cấu hình transport behavior như:

- **pollTimeout**: thời gian BLOCK chờ records.
- **batchSize**: COUNT trong một lần đọc.
- **serialization context**: mã hóa key/fields/values.
- **target type / object mapper**: ánh xạ record tới DTO khi thích hợp.
- **onErrorResume**: chiến lược ứng xử khi nhận/deserialize lỗi trong phiên bản hỗ trợ.

Trong các phiên bản Spring Integration **5.5+**, adapter cũng hỗ trợ một số setters trực tiếp tương ứng. **Không cấu hình cả StreamReceiverOptions được truyền sẵn và các setters trực tiếp cùng nhóm** nếu API quy định chúng mutually exclusive.

### 7.4. Poll timeout không phải retry interval nghiệp vụ

Nếu đặt pollTimeout=200ms, Redis XREADGROUP có thể block chờ records tới timeout. Điều đó không có nghĩa:

- Consumer retry business sau 200ms.
- PEL entries sẽ được claim sau 200ms.
- Redis Stream tự trim sau 200ms.
- Task processing có SLA dưới 200ms.

Retry/backoff/reclaim cần cơ chế riêng.

### 7.5. BatchSize không phải commit batch

batchSize=10 có thể yêu cầu Redis trả tối đa 10 records mỗi lần đọc; handler có thể xử lý từng record và ACK riêng, hoặc tự batch theo business contract. **Không ACK toàn bộ 10 records nếu mới 9 records thực sự committed**.

## 8. Dependencies và Redis ConnectionFactory

Với Spring Boot và dependency management tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-redis</artifactId>
    </dependency>
</dependencies>
~~~

Các artifact Spring Boot starter phụ thuộc vào thế hệ Boot; nếu môi trường không có một starter reactive riêng, sử dụng starter Redis/Lettuce/Reactor phù hợp với BOM. **Điều kiện chính là có ReactiveRedisConnectionFactory thực sự**, không chỉ RedisConnectionFactory đồng bộ.

### 8.1. Local/test Redis config

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 3s
      timeout: 3s
~~~

Đây là cấu hình minh họa cho môi trường test. Production cần TLS, secret management, Redis ACL, Sentinel/Cluster và timeouts phù hợp. Namespace property có thể thay đổi theo phiên bản Spring Boot; xác minh BOM/config metadata thực tế.

### 8.2. ReactiveRedisConnectionFactory khác RedisTemplate

| Thành phần | Vai trò |
| --- | --- |
| ReactiveRedisConnectionFactory | Kết nối Redis cho reactive operations/StreamReceiver |
| ReactiveRedisTemplate / ReactiveStreamOperations | Producer/consumer Redis Streams reactive |
| StringRedisTemplate | Công cụ Spring Data Redis đồng bộ, thuận tiện ghi/đọc field String trong lab |
| ReactiveRedisStreamMessageProducer | Endpoint Spring Integration phát Spring Messages từ stream records |
| MessageChannel | Nơi IntegrationFlow xử lý records đã nhận |

Một **LettuceConnectionFactory** có thể đáp ứng cả API sync và reactive tùy cấu hình/phiên bản. Không suy ra mọi RedisConnectionFactory đều hỗ trợ reactive. Khi tạo adapter, inject đúng **ReactiveRedisConnectionFactory**.

### 8.3. Không tự áp dụng thư viện JDK serialization

Với record fields liên dịch vụ, ưu tiên **UTF-8 String fields/typed JSON/Avro/Protobuf** theo contract. Không đẩy các object Java native serialized từ producer này rồi dùng trusted-all deserialization ở consumer khác.

### 8.4. Địa chỉ stream và group

Trong ví dụ:

~~~text
Stream key:     orders:events
Consumer group: fulfillment-v1
Consumer name:  fulfillment-pod-a
EventId:        evt-order-1001
Record ID:      1795410000123-0
~~~

**Stream key** định danh Redis data structure, **group** là trạng thái delivery độc lập, **consumer name** là owner của pending entries, còn **eventId** là business identity. Đừng copy consumerName thành eventId hay đặt group theo tên pod mỗi lần deploy.

## 9. Producer test: XADD record có hợp đồng rõ

Ví dụ Spring Data Redis đồng bộ với StringRedisTemplate:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStreamPublisher {

    public static final String STREAM = "orders:events";
    private final StringRedisTemplate redisTemplate;

    public OrderStreamPublisher(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public RecordId publishCreated(String eventId, String orderId) {
        if (eventId == null || eventId.isBlank()
                || orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Missing event identity");
        }

        Map<String, String> fields = new LinkedHashMap<>();
        fields.put("eventId", eventId);
        fields.put("eventType", "ORDER_CREATED");
        fields.put("schemaVersion", "1");
        fields.put("orderId", orderId);

        MapRecord<String, String, String> record =
            StreamRecords.newRecord()
                .in(STREAM)
                .ofMap(fields);

        return redisTemplate.opsForStream().add(record);
    }
}
~~~

**Cần kiểm chứng:** Trong các thế hệ Spring Data Redis, generic signature của StreamRecords builder và type inference có thể thay đổi. Khi compile thực tế, điều chỉnh theo version thư viện và serializer; giữ contract **stream key + field map + RecordId** không đổi.

### 9.1. Dùng Redis CLI để quan sát

~~~bash
redis-cli XADD orders:events '*' eventId evt-order-1001 eventType ORDER_CREATED schemaVersion 1 orderId O-1001
redis-cli XRANGE orders:events - +
redis-cli XLEN orders:events
~~~

Các commands đọc không làm XACK. **XLEN** đếm records được giữ, không phải số records pending/ACK hay business DONE.

### 9.2. Không dùng Record ID làm eventId mặc định

Nếu producer timeout và không biết XADD đã thành công hay chưa, retry có thể tạo record khác với **Record ID khác**. Consumer cần biết cả hai records là **cùng một eventId** nếu business contract yêu cầu deduplicate.

### 9.3. Database transaction và XADD

~~~text
DB commit -> crash -> XADD chưa gửi
~~~

Với order event bắt buộc không mất, dùng **transactional outbox** hoặc một nguồn event durable phù hợp để phát sau commit. XADD thành công **không tự nguyên tử với JDBC transaction**.

### 9.4. Stream retention

Không để stream tăng vô hạn. Có thể dùng chính sách XADD MAXLEN hoặc XTRIM nhưng phải tính thời gian downtime, tốc độ consumer và nhu cầu audit/replay. **Trim quá sớm có thể làm records biến mất khỏi stream dù còn pending metadata**, khiến recovery không còn payload.

## 10. Java configuration: ReactiveRedisStreamMessageProducer

Ví dụ dưới đây dùng **manual ACK** và **consumer group đã được provision trước** trong Redis test. Nhờ vậy, bài học không phụ thuộc vào lựa chọn offset khi tạo group tự động.

Trước khi chạy ứng dụng:

~~~bash
redis-cli XGROUP CREATE orders:events fulfillment-v1 0-0 MKSTREAM
~~~

Nếu group đã tồn tại, Redis báo **BUSYGROUP**; không xóa/tạo lại group production chỉ để chạy lại lệnh cấu hình.

### 10.1. MessageChannel nhận stream records

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class OrderStreamChannelConfig {

    @Bean
    public MessageChannel ordersStreamInput() {
        return new DirectChannel();
    }
}
~~~

### 10.2. Bean adapter chuyên dụng

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.integration.redis.inbound.ReactiveRedisStreamMessageProducer;
import org.springframework.messaging.MessageChannel;

@Configuration
public class OrderStreamInboundConfig {

    @Bean
    public ReactiveRedisStreamMessageProducer ordersStreamInbound(
            ReactiveRedisConnectionFactory redisFactory,
            @Qualifier("ordersStreamInput")
            MessageChannel ordersStreamInput) {

        ReactiveRedisStreamMessageProducer adapter =
            new ReactiveRedisStreamMessageProducer(
                redisFactory, OrderStreamPublisher.STREAM);

        adapter.setConsumerGroup("fulfillment-v1");
        adapter.setConsumerName("fulfillment-local-a");
        adapter.setCreateConsumerGroup(false);
        adapter.setAutoAck(false);
        adapter.setReadOffset(ReadOffset.lastConsumed());
        adapter.setPollTimeout(Duration.ofMillis(300));
        adapter.setBatchSize(10);
        adapter.setExtractPayload(false);
        adapter.setOutputChannel(ordersStreamInput);
        adapter.setAutoStartup(true);

        return adapter;
    }
}
~~~

**Ý nghĩa từng lựa chọn:**

| Setting | Giá trị trong lab | Ý nghĩa |
| --- | --- | --- |
| streamKey | orders:events | Stream đang đọc |
| consumerGroup | fulfillment-v1 | Dùng nhóm được provision |
| consumerName | fulfillment-local-a | Định danh consumer; phải duy nhất cho replicas đồng thời |
| createConsumerGroup | false | Không tự tạo group từ một offset ngầm |
| autoAck | false | Business flow tự quyết định ACK |
| readOffset | lastConsumed | Nhận records mới theo group progress |
| pollTimeout | 300 ms | Timeout BLOCK đọc stream |
| batchSize | 10 | COUNT tối đa cho lần read |
| extractPayload | false | Spring Message payload giữ **Record** để handler thấy ID/fields |
| outputChannel | ordersStreamInput | Đưa Spring Message vào flow |

**Ràng buộc phiên bản:** Các setters **setPollTimeout** và **setBatchSize** có trong Spring Integration 5.5+; bản 5.4 có thể cần **setStreamReceiverOptions(...)** thay thế. Không vừa setStreamReceiverOptions vừa dùng setters riêng trong cùng bean nếu phiên bản quy định chúng loại trừ nhau.

**Lưu ý chạy nhiều replicas:** Trong ví dụ hardcode consumerName để code dễ đọc. Khi triển khai nhiều pods, tạo tên consumer **khác nhau và ổn định đủ lâu** theo chiến lược vận hành; không copy cùng chuỗi fulfillment-local-a cho mọi instance.

### 10.3. Vòng đời của adapter

ReactiveRedisStreamMessageProducer là endpoint hỗ trợ **SmartLifecycle**. Khi Spring context start, nó có thể tự subscribe/receive theo thiết lập autoStartup. Khi stop/restart, subscriber có thể kết nối lại, nhưng **PEL của consumer group vẫn phải được phục hồi riêng** nếu records đã giao chưa được XACK.

### 10.4. Không thêm Spring Integration Poller

Đây **không phải** cách cấu hình đúng cho source này:

~~~text
Redis Stream inbound -> Pollers.fixedDelay(2000) để giả lập XREADGROUP
~~~

Reactive StreamReceiver đã quản lý vòng nhận/blocking read. Thời gian pollTimeout của Redis khác tần suất Pollers.fixedDelay của RedisStoreMessageSource.

## 11. Java DSL: Redis.streamInboundChannelAdapter(...)

Nếu muốn mô tả hoàn toàn bằng Spring Integration Java DSL, factory **Redis.streamInboundChannelAdapter** cung cấp các options tương ứng:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.redis.dsl.Redis;

@Configuration
@EnableIntegration
public class OrderStreamDslConfig {

    @Bean
    public IntegrationFlow orderStreamInboundDsl(
            ReactiveRedisConnectionFactory factory,
            FulfillmentStreamHandler handler) {

        return IntegrationFlow.from(
            Redis.streamInboundChannelAdapter(
                    factory, OrderStreamPublisher.STREAM)
                .consumerGroup("fulfillment-v1")
                .consumerName("fulfillment-local-a")
                .createConsumerGroup(false)
                .autoAck(false)
                .readOffset(ReadOffset.lastConsumed())
                .pollTimeout(Duration.ofMillis(300))
                .batchSize(10)
                .extractPayload(false))
            .handle(handler, "handle")
            .get();
    }
}
~~~

**Quan trọng:** Bean **OrderStreamInboundConfig** ở mục 10 và **OrderStreamDslConfig** ở đây là **hai phương án thay thế cho một subscriber**. Không chạy cả hai trong cùng context rồi xem duplicate callbacks là broker retry; đó có thể là hai consumers độc lập cùng group.

Java DSL có thể dùng **.channel(c -> c.flux())** để dùng reactive channel khi thiết kế end-to-end nonblocking. Ví dụ trên nối trực tiếp handler đồng bộ để dạy rõ **acknowledgment sau business commit**; muốn thay bằng flow reactive cần kiểm tra thời điểm hoàn thành downstream và ownership callback.

### 11.1. Khi nào chọn bean API thay DSL?

| Bean ReactiveRedisStreamMessageProducer | Java DSL |
| --- | --- |
| Dễ kiểm soát từng setter với IDE/Javadocs | Flow gọn, kết nối handler/router dễ nhìn |
| Dễ gắn output channel và lifecycle bằng bean | Endpoint specs đặt cạnh topology |
| Dễ tách test transport khỏi test business | Dễ diễn đạt EIP flow cùng transformer/filter |
| Cần tự bảo đảm không duplicate bean flow | Cần kiểm tra API spec cho phiên bản |

Cả hai dùng cùng cơ chế Redis StreamReceiver; **không có một phương án tạo thêm broker delivery guarantee tự động**.

## 12. Payload: extractPayload(true/false)

Redis stream record có thể được giữ nguyên hoặc chỉ lấy phần value/fields làm Spring Message payload.

| Config | Spring Message payload | Khi nào phù hợp |
| --- | --- | --- |
| **extractPayload(true)** (mặc định) | Value của Record, có thể là Map/DTO tùy serializer | Handler chỉ cần business fields |
| **extractPayload(false)** | Toàn bộ Redis Stream Record | Handler cần stream key, Record ID và value cùng một object |

Ngay cả khi **extractPayload(true)**, adapter có thể phát **metadata stream/record** trong Spring MessageHeaders. Không cố tìm message ID bằng cách đoán key "id" trong business field map.

### 12.1. RedisHeaders được adapter gắn

Theo Spring Integration Redis Stream inbound, các header đáng chú ý:

| Header | Ý nghĩa |
| --- | --- |
| **RedisHeaders.STREAM_KEY** | Redis stream key |
| **RedisHeaders.STREAM_MESSAGE_ID** | Redis Stream record ID |
| **RedisHeaders.CONSUMER_GROUP** | Consumer group (nếu đang dùng) |
| **RedisHeaders.CONSUMER** | Consumer name |
| **IntegrationMessageHeaderAccessor.ACKNOWLEDGMENT_CALLBACK** | Callback ACK khi autoAck=false |

Header của framework phục vụ routing/observability/ACK; **không coi chúng là business eventId, authentication hay tenant authorization**.

### 12.2. Bản ghi không nhất thiết chứa JSON body

Với XADD các fields eventId/eventType/orderId, payload mặc định có thể là **Map** đã deserialize, không phải JSON String. Đừng viết handler bắt buộc ObjectMapper.readValue(String) trong khi producer chưa serialize JSON.

Một cách chọn contract khác là:

~~~text
Stream fields:
  eventId = evt-order-1001
  eventType = ORDER_CREATED
  schemaVersion = 1
  payloadJson = {"orderId":"O-1001", ...}
~~~

Khi đó handler parse payloadJson có kiểm soát và validate schema. Không vừa đặt JSON object vào field rồi lại dùng Jackson serialize toàn bộ String lần hai mà không test raw bytes.

### 12.3. Kiểu dữ liệu qua serializer

Redis field values về giao thức là bytes; Spring Data Redis serializers quyết định Java type nhận được. Nếu producer dùng StringRedisTemplate, nên cấu hình receiver tương thích với String serialization hoặc xác minh default behavior của phiên bản. Nếu dùng **ObjectRecord + HashMapper**, cần kiểm soát trusted target types, field names và schema migration.

Không cast cứng mọi value là String khi chưa có contract test producer–consumer.

## 13. Handler: commit nghiệp vụ rồi ACK

Ta dùng handler nhận **Message<?>** chứa MapRecord, validate business event, gọi service commit, cuối cùng mới ACK.

### 13.1. Service interface cho nghiệp vụ

~~~java
public interface FulfillmentBusinessService {

    // Implementation phải đảm bảo idempotency theo eventId,
    // commit durable state trước khi method trả về bình thường.
    void applyOrderCreated(String eventId, String orderId);
}
~~~

Nếu implementation dùng JDBC/JPA, đặt transaction tại **Spring-managed service method** thích hợp, unique constraint cho eventId và kiểm tra idempotency. Không giả định một interface tự bảo đảm transaction.

### 13.2. FulfillmentStreamHandler

~~~java
import java.util.Map;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.acks.SimpleAcknowledgment;
import org.springframework.integration.redis.RedisHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Service;

@Service
public class FulfillmentStreamHandler {

    private final FulfillmentBusinessService businessService;

    public FulfillmentStreamHandler(
            FulfillmentBusinessService businessService) {
        this.businessService = businessService;
    }

    public void handle(Message<?> springMessage) {
        if (!(springMessage.getPayload()
                instanceof MapRecord<?, ?, ?> record)) {
            throw new IllegalArgumentException(
                "Expected a Redis MapRecord payload");
        }

        Map<?, ?> fields = record.getValue();
        Object eventId = fields.get("eventId");
        Object eventType = fields.get("eventType");
        Object version = fields.get("schemaVersion");
        Object orderId = fields.get("orderId");

        if (!(eventId instanceof String)
                || ((String) eventId).isBlank()
                || !"ORDER_CREATED".equals(eventType)
                || !"1".equals(version)
                || !(orderId instanceof String)
                || ((String) orderId).isBlank()) {
            throw new IllegalArgumentException(
                "Invalid or unsupported order event");
        }

        Object rawAck = springMessage.getHeaders().get(
            IntegrationMessageHeaderAccessor.ACKNOWLEDGMENT_CALLBACK);
        if (!(rawAck instanceof SimpleAcknowledgment acknowledgment)) {
            throw new IllegalStateException(
                "Expected manual acknowledgment callback");
        }

        // Business service commits idempotent durable state.
        businessService.applyOrderCreated(
            (String) eventId, (String) orderId);

        // Only after business transaction returns successfully:
        acknowledgment.acknowledge();

        Object recordId = springMessage.getHeaders().get(
            RedisHeaders.STREAM_MESSAGE_ID);
        System.out.println("Fulfilled stream record: " + recordId);
    }
}
~~~

**Luồng trên giả định** các field values được deserialize thành String, do producer và receiver cùng dùng String serialization. Nếu dùng serializer khác, cần transformer/contract validation phù hợp. Đây là một **mẫu minh họa**, không là production-ready fulfillment service.

### 13.3. Vì sao lấy callback từ header?

Với **autoAck(false)** trong consumer group, adapter đưa **SimpleAcknowledgment** vào header có hằng **IntegrationMessageHeaderAccessor.ACKNOWLEDGMENT_CALLBACK**. Business handler phải quyết định khi nào ACK. Không tự tạo một String custom header "ack=true" rồi kỳ vọng Redis XACK.

### 13.4. ACK phải đến sau mốc commit

Thứ tự an toàn thường là:

~~~text
Validate record
  -> check idempotency/eventId
  -> commit database side effect
  -> call acknowledgment.acknowledge()
~~~

Nếu handler throw exception trước ACK, record có thể **tiếp tục pending trong PEL**. Nó **không tự requeue ngay** chỉ vì Java ném lỗi; cần recovery policy.

### 13.5. Callback ACK không phải transaction JDBC

ACK thuộc Redis group, business commit thuộc database/external service. Nếu Redis ACK thất bại sau DB commit:

- Record có thể còn pending.
- Reclaimer có thể giao lại.
- Idempotent service phải nhận diện eventId đã DONE và không tạo side effect trùng.
- Handler vẫn có thể ACK record đã xử lý thành công ở lượt recovery.

Nếu ACK outcome không rõ do network timeout, kiểm tra PEL/state thay vì mặc định retry side effect.

### 13.6. Không ACK trước khi xử lý async hoàn tất

Nếu handler chỉ đặt công việc vào executor rồi gọi acknowledgment.acknowledge(), Redis có thể coi record đã được xử lý trong khi task còn ở memory queue. Process crash làm mất việc ở tầng business.

Nếu muốn xử lý async:

- Giữ callback/record ID tới lúc worker thực sự commit và ACK sau đó, **hoặc**
- Trước tiên ghi một durable inbox/job table, ACK Redis chỉ sau khi handoff lưu bền thành công, rồi worker xử lý inbox.

Không truyền object callback qua JSON/outbound adapters như business data; nó là một đối tượng runtime gắn với delivery.

## 14. Thiết kế business contract và versioning

Để một stream được dùng bởi nhiều services và nhiều phiên bản ứng dụng, cần xác định **record schema** độc lập với Java class name.

### 14.1. Contract mẫu ORDER_CREATED

| Field | Kiểu trên wire | Bắt buộc | Quy tắc |
| --- | --- | --- | --- |
| eventId | UTF-8 String | Có | ID nghiệp vụ ổn định qua retries |
| eventType | UTF-8 String | Có | Allowlist: ORDER_CREATED |
| schemaVersion | String số nguyên hoặc kiểu được công bố | Có | Consumer chỉ nhận versions hỗ trợ |
| orderId | UTF-8 String | Có | Validate format/length, tenant ownership |
| occurredAt | ISO-8601 UTC String | Nên có | Thời điểm domain, không dựa vào stream ID làm nguồn duy nhất |
| traceparent | W3C Trace Context String | Optional | Observability, không có quyền authorization |
| tenantRef | String tham chiếu đã validate | Tùy use case | Không tự tin vào header/field do producer gửi |

Ví dụ:

~~~bash
redis-cli XADD orders:events '*' eventId evt-order-1001 eventType ORDER_CREATED schemaVersion 1 orderId O-1001 occurredAt 2026-11-23T02:00:00Z
~~~

### 14.2. Typed event envelope

Một kiến trúc khác để tương thích với HTTP/Kafka/AMQP:

~~~json
{
  "eventId": "evt-order-1001",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "data": {
    "orderId": "O-1001",
    "tenantRef": "T-1"
  }
}
~~~

Producer có thể ghi envelope này trong **field payloadJson**, rồi thêm eventId/eventType/schemaVersion để Redis workers có thể lọc. Nếu duplicate các trường, phải có **quy tắc nguồn sự thật** khi fields ngoài và envelope không khớp; fail fast hoặc cách ly, không chọn ngẫu nhiên.

### 14.3. Không dựa vào Redis Record ID để phân quyền

Record ID do Redis cấp không chứng minh một order thuộc tenant nào. Stream key, group và consumer metadata cũng không thay authentication/authorization. Consumer phải validate input và tra nguồn nghiệp vụ đáng tin cậy.

### 14.4. Schema compatibility trong rolling deployment

| Producer | Consumer | Kết quả cần kiểm thử |
| --- | --- | --- |
| v1 | v1 | Đọc được bản ghi cũ |
| v1 | v2 | Consumer mới vẫn đọc v1 khi còn hỗ trợ |
| v2 | v1 | Producer mới phát dữ liệu tương thích hoặc consumer cũ reject có kiểm soát |
| v2 | v2 | Hợp đồng mới hoạt động |
| Field version v2, payloadJson v1 | Bất kỳ | Phát hiện conflict |
| Unknown eventType | Bất kỳ | Không route nhầm vào handler có quyền nhạy cảm |

Đặc biệt, records cũ có thể vẫn nằm trong stream hoặc PEL **sau khi deploy version mới**; không chỉ test producer/consumer cùng version.

### 14.5. Kích thước và giới hạn

Redis Stream record có thể chứa nhiều fields/bytes; đặt giới hạn payload, số fields, JSON nesting depth, string length và batch size. Không đưa file ảnh, binary blob cực lớn hoặc Throwable/Java class serialization vào stream nếu có thể đặt object storage reference.

## 15. ErrorChannel và lỗi ở những tầng khác nhau

Đường nhận có nhiều ranh giới lỗi:

~~~mermaid
flowchart TD
    R["Redis XREADGROUP"] --> RX["StreamReceiver"]
    RX --> DE["Deserialize Record"]
    DE --> AD["Inbound adapter"]
    AD --> C["MessageChannel"]
    C --> V["Validate contract"]
    V --> H["Business handler"]
    RX -. "Network, ACL, timeout" .-> E1["Receiver error recovery"]
    DE -. "Serializer / hash mapper" .-> E2["ErrorMessage / errorChannel"]
    V -. "Invalid version/schema" .-> E3["Business error policy"]
    H -. "DB / provider transient" .-> E3
    E1 --> OPS["Observe / alert / recover"]
    E2 --> OPS
    E3 --> OPS
~~~

### 15.1. Lỗi trước khi Spring Message được tạo

Một record có thể bị lỗi **deserialization** ngay trong StreamReceiver/adapter. Khi đó service activator ở giữa IntegrationFlow **chưa nhận được Spring Message**, nên try/catch của handler không đủ.

Spring Integration Redis Stream inbound có đường **errorChannel/onErrorResume** theo phiên bản. Với manual ACK, một **ErrorMessage** cho record lỗi có thể mang **ACKNOWLEDGMENT_CALLBACK**. Error handler phải quyết định:

- Có thể sửa/đọc lại record?
- Có thể gửi raw record sang **durable dead-letter stream/table** không?
- Có nên giữ record pending để operator/recovery xử lý?
- Chỉ được ACK sau khi **chứng minh đã lưu bền quyết định loại bỏ/cách ly**?

Không tự ACK tất cả deserialization errors chỉ để PEL giảm.

### 15.2. onErrorResume của StreamReceiver

Từ Spring Integration **5.5**, API cho phép cấu hình receiver options/onErrorResume; mặc định theo tài liệu có thể chuyển lỗi đã trích xuất thành ErrorMessage tới error channel.

**Không cấu hình một onErrorResume luôn trả empty publisher rồi nuốt tất cả exceptions** nếu hệ thống cần biết lỗi serializer/network; như vậy sẽ mất quan sát và có thể làm record stuck trong PEL.

### 15.3. ErrorChannel không phải DLQ

ErrorChannel là một cơ chế **Spring Messaging** để xử lý exception/error messages. Nó không tự:

- Ghi raw record vào durable storage.
- Giảm retry count hay quyết định max attempts.
- Chuyển stream record sang một Redis DLQ.
- XACK pending sau khi business commit.
- Claim lại pending entries từ consumer đã chết.

Nếu một error flow chỉ log exception rồi return, record có thể **vẫn pending**. Ngược lại, nếu error flow ACK không phù hợp, record có thể **không còn trong PEL** dù dữ liệu chưa được lưu để điều tra.

### 15.4. Không áp NACK như RabbitMQ

Redis Streams có **XACK** và các lệnh claim/re-read, nhưng không có một NACK broker-native đồng nghĩa **basic.nack(requeue=true)** của RabbitMQ. Với manual ACK:

- **Business success:** XACK qua callback.
- **Transient failure:** có thể để pending và lên lịch recover/retry có giới hạn.
- **Permanent failure:** lưu bền raw record/error metadata ở một nơi cách ly, ACK original theo policy.
- **Unknown outcome:** kiểm tra business state/idempotency trước khi retry.

Đừng nhìn tên interface ACK callback rồi suy rằng mọi giá trị REJECT/REQUEUE có semantics Redis giống AMQP; xác minh implementation của Redis adapter, và sử dụng Redis PEL/XCLAIM/XAUTOCLAIM cho recovery.

### 15.5. Exception lan truyền và DirectChannel

Với DirectChannel, handler có thể chạy đồng bộ trong đường dispatch; exception được propagate/được framework chuyển thành ErrorMessage theo configuration. Nhưng **exception Java không tự reset group last-delivered ID** và không khiến record tự xuất hiện ở lượt XREADGROUP > tiếp theo.

### 15.6. Async handler và ack timing

Nếu flow dùng ExecutorChannel/FluxMessageChannel, callback có thể trả về trước khi business work hoàn tất. Phải giữ **ACK callback đúng record** và chỉ gọi nó sau durable handoff/commit; không chỉ dựa trên hành vi upstream send trả về.

Đừng biến header ACK callback thành một Kafka/HTTP outgoing header; nó là runtime object không có contract cross-protocol.

## 16. Pending Entries List: quan sát và phục hồi

Redis cung cấp các lệnh để xem và xử lý pending entries.

### 16.1. XPENDING

~~~bash
redis-cli XPENDING orders:events fulfillment-v1
redis-cli XPENDING orders:events fulfillment-v1 - + 10
~~~

Kết quả có thể chứa số pending, ID range, owners, idle time và delivery count theo dạng lệnh. **Không dùng XPENDING output như business transaction log**; đó là metadata của Redis group.

### 16.2. XINFO GROUPS và XINFO CONSUMERS

~~~bash
redis-cli XINFO GROUPS orders:events
redis-cli XINFO CONSUMERS orders:events fulfillment-v1
~~~

Các lệnh này giúp điều tra group progress, consumers, pending ownership/idle, nhưng group lag hoặc pending count **không bao quát** các dữ liệu đã bị trim, các side effects ngoài Redis hoặc trùng business eventId.

### 16.3. XCLAIM / XAUTOCLAIM

Khi consumer A crash, một consumer/reclaimer khác có thể **claim pending records đã idle đủ lâu**:

~~~bash
# Minh họa XAUTOCLAIM:
redis-cli XAUTOCLAIM orders:events fulfillment-v1 worker-reclaimer 60000 0-0 COUNT 20
~~~

Trong ví dụ, **60000** là min-idle-time tính bằng milliseconds; **0-0** là cursor bắt đầu và **COUNT 20** giới hạn công việc mỗi lượt. Output gồm cursor tiếp theo và claimed entries theo Redis version; cần xử lý cursor, batch, lỗi và records đã bị trim.

**Không chạy reclaim trên group production để thử cho vui**: thao tác có thể chuyển ownership các jobs đang xử lý, khiến business duplicate/concurrent side effects.

### 16.4. Reclaim không đồng nghĩa người xử lý cũ chắc chắn chết

Một record idle 60 giây có thể do:

- Worker crash.
- Worker đang xử lý tác vụ lâu hơn dự kiến.
- Network partition hoặc heartbeat không có.
- Một handler đã commit business nhưng XACK lỗi.

Sau claim, record **có thể xử lý lại**. Nên có idempotency key, business state check và fencing/lease policy khi task có side effect nhạy cảm.

### 16.5. New records và pending recovery là hai vòng khác nhau

~~~mermaid
flowchart TD
    START["FulfillmentService"] --> NEW["Inbound adapter<br/>XREADGROUP >"]
    START --> REC["Recovery worker<br/>XPENDING/XAUTOCLAIM"]
    NEW --> PROC["Idempotent processing"]
    REC --> PROC
    PROC --> ACK["XACK after success"]
    PROC --> ERR["Retry / durable dead-letter"]
~~~

Một **ReactiveRedisStreamMessageProducer** nhận new group deliveries không được mặc định coi là **reclaimer cho mọi pending cũ**. Hãy triển khai/test recovery worker hoặc công cụ vận hành riêng nếu SLA yêu cầu.

### 16.6. Pending record đã bị trim

PEL có thể còn thông tin về ID đã giao, nhưng raw record có thể không còn do XTRIM/XDEL/retention. XAUTOCLAIM có behavior xử lý tham chiếu tới records đã bị xóa theo Redis version. Khi payload mất, recovery không thể “tạo lại nguyên văn” chỉ từ pending metadata.

Do đó **retention và pending idle/lag phải được giám sát cùng nhau**. Không trim theo size quá ngắn khi consumer có thể dừng nhiều ngày.

## 17. Retry, poison records và dead-letter

### 17.1. Phân loại lỗi

| Lỗi | Có nên retry? | Hướng xử lý |
| --- | --- | --- |
| Malformed field map / JSON | Thường không nóng | Cách ly raw record, alert schema |
| Unsupported schemaVersion | Không ngay | Compatibility policy, replay sau khi nâng consumer |
| Unknown tenant/eventType | Không | Reject/forensics, kiểm tra nguồn |
| DB connection tạm lỗi | Có giới hạn | Exponential backoff, record pending/recovery |
| Provider 429/503 | Có giới hạn | Retry/backoff/circuit breaker |
| Provider timeout, outcome UNKNOWN | Cần đối soát | Tránh gửi side effect trùng |
| Redis connectivity lỗi | Recovery transport | Không ngụ ý business đã rollback |
| Record trimmed trước recovery | Không thể replay nguyên payload từ stream | Phải đối soát/source of truth |

### 17.2. Một error stream do ứng dụng định nghĩa

Redis Streams không tự có **RabbitMQ DLX routing**. Ứng dụng có thể tạo một Redis Stream:

~~~text
orders:events:dead
~~~

Mỗi dead-letter record chứa:

~~~json
{
  "originalStream": "orders:events",
  "originalRecordId": "1795410000123-0",
  "eventId": "evt-order-1001",
  "reason": "UNSUPPORTED_SCHEMA_VERSION",
  "failedAt": "2026-11-23T03:30:00Z",
  "attempts": 4
}
~~~

**Trình tự khuyến nghị:** ghi **durable dead-letter payload/error state** thành công và có thể xác minh, rồi XACK original. Nếu XADD dead thành công nhưng ACK original thất bại, recovery có thể dead-letter lần hai; nên dùng eventId/originalStream/recordId để deduplicate DLQ entries.

### 17.3. Retry không phải chỉ đọc lại ngay lập tức

Nếu record malformed luôn gây lỗi, một recovery worker liên tục XAUTOCLAIM rồi xử lý lại sẽ tạo hot loop. Cần:

- Retry budget và attempt count bền vững.
- Delay/backoff, nextAttemptAt hoặc retry scheduler.
- Error classifier transient/permanent.
- Final dead state khi hết attempts.
- Cơ chế operator replay sau khi sửa lỗi.

Redis PEL có delivery count nhưng không thay thế toàn bộ business retry ledger, đặc biệt khi republish tạo record ID mới hoặc nhiều nguyên nhân cần tính riêng.

### 17.4. Khi ACK thất bại sau dead-letter thành công

Nếu record được XADD vào dead stream nhưng connection mất trước ACK original:

- Original vẫn có thể pending.
- Lần reclaim tiếp theo thấy eventId đã được dead-letter.
- Recovery worker có thể **XACK original mà không tạo bản dead trùng** theo policy đã được lưu bền.

Đây là tình huống cần **idempotent dead-letter handling**, không thể xử lý đúng chỉ bằng một try/catch đặt quanh XACK.

### 17.5. ErrorChannel phải có trách nhiệm rõ

Nên xác định owner:

| Thành phần | Trách nhiệm |
| --- | --- |
| Inbound adapter | Đọc/deserialize và phát Spring Messages |
| Business handler | Validate, idempotent commit, ACK thành công |
| Error handler | Phân loại raw record lỗi, durable dead-letter hoặc để pending |
| Recovery worker | Nhận/reclaim pending hợp lệ, apply retry policy |
| Operator | Điều tra/replay dead jobs, giữ audit |

Nếu cùng một failure bị handler retry, errorChannel re-publish và reclaimer claim đồng thời mà không có state chung, một event có thể gây nhiều side effects.

## 18. Retention, XTRIM, XDEL và khả năng replay

Redis Stream **không được giữ mãi vô hạn** trừ khi bạn cố ý chấp nhận chi phí memory/storage tăng liên tục. Retention phải dựa trên **SLA xử lý, downtime dài nhất, nhu cầu replay/audit và độ bền Redis**.

### 18.1. XTRIM theo độ dài

~~~bash
# Giữ gần đúng tối đa 100000 records, cú pháp theo Redis version:
redis-cli XTRIM orders:events MAXLEN '~' 100000

# Quan sát:
redis-cli XLEN orders:events
redis-cli XINFO STREAM orders:events
~~~

Lựa chọn **MAXLEN ~** là approximate trimming, tối ưu hiệu suất theo cơ chế Redis. Nó **không bảo đảm stream còn mọi records mà nhóm consumer chưa xử lý**.

### 18.2. XADD MAXLEN

Publisher cũng có thể dùng policy giới hạn khi append:

~~~bash
redis-cli XADD orders:events MAXLEN '~' 100000 '*' eventId evt-1002 eventType ORDER_CREATED schemaVersion 1 orderId O-1002
~~~

**Không copy giá trị 100000 làm ngưỡng production.** Cần ước tính:

~~~text
Required retained records ≈ peak append rate (records/second)
                          x recovery window (seconds)
                          x safety factor
~~~

Ví dụ peak 100 records/s, downtime/recovery target 3 giờ → khoảng 1.080.000 records **chưa tính hệ số an toàn, replay, log audit và memory**. Nếu workload có burst, nên lấy số liệu đo thay vì chỉ average.

### 18.3. Trimming có thể ảnh hưởng PEL

XTRIM hoặc XDEL có thể loại **payload record** khỏi stream trong khi metadata PEL còn tồn tại, tùy Redis version/command options. Khi đó:

- XPENDING có thể còn nhắc tới ID.
- Recovery không còn raw fields để replay business record.
- XAUTOCLAIM có thể xử lý references tới missing records theo version.
- Một group khác chưa đọc record sẽ không còn dữ liệu đó.

Với Redis versions mới có options về cách quản lý references khi xóa/trim, phải **kiểm tra chính xác semantics của Redis server đang chạy**. Không dựa vào một mặc định để cam kết retained history trong mọi version.

### 18.4. XACK không xóa record, XDEL không ACK business

| Command | Tác động điển hình |
| --- | --- |
| XADD | Ghi record mới |
| XREAD/XREADGROUP | Đọc; với group giao record và có thể vào PEL |
| XACK | Xác nhận ID của group, bỏ pending |
| XDEL | Xóa record khỏi stream theo chính sách |
| XTRIM | Giới hạn retention bằng loại records |
| XGROUP DESTROY | Xóa trạng thái cả group |

**Không dùng XDEL thay XACK** để “dọn PEL” và không XGROUP DESTROY một group production nhằm xóa pending mà chưa xử lý recovery.

### 18.5. Retention và số lượng groups

Nếu một stream có nhóm fulfillment xử lý nhanh và nhóm analytics xử lý chậm, trimming dựa trên tốc độ fulfillment có thể làm analytics mất records. Retention phải xét **slowest required group**, thời gian offline và dữ liệu dự phòng.

### 18.6. Replay không đồng nghĩa chạy lại side effect

Một operator có thể replay records cũ vào group mới hoặc stream mới, nhưng business service phải:

- Giữ **eventId gốc** nếu đó là cùng sự kiện.
- Kiểm tra đã xử lý trước đó chưa.
- Phân biệt sửa dữ liệu và phát lại nguyên văn.
- Giữ audit/replay reason.
- Không gửi lại email/charge thẻ đơn giản vì Redis record chưa ACK.

## 19. Redis persistence, replication và failover

Redis Streams là dữ liệu được lưu trong Redis; khả năng khôi phục phụ thuộc cấu hình **RDB/AOF, fsync, replication, Sentinel/Cluster và chính sách hạ tầng**.

### 19.1. Redis đã trả XADD không chứng minh bền vững tuyệt đối

Nếu primary trả thành công rồi mất điện trước khi dữ liệu được flush/replicate theo mức yêu cầu, một số records có thể mất trong failover/RPO. Không được suy:

~~~text
XADD returned ID == mọi replicas đã lưu bền vĩnh viễn
~~~

Nếu event mang giá trị nghiệp vụ cao, chọn Redis persistence/durability policy phù hợp, kiểm tra failover tests và cân nhắc durable outbox ở producer.

### 19.2. Group state cũng cần được bảo vệ

Consumer group metadata/PEL được lưu trên Redis. Nếu mất group state do rollback/failover hoặc operator reset, consumer có thể đọc lại/miss records tùy offset. Business **idempotency ledger** độc lập với Redis giúp nhận diện duplicate ngay cả khi Redis group history thay đổi.

### 19.3. Redis Cluster

Một Redis Stream thường nằm ở shard theo key hash slot. Nếu dùng scripts/transactions liên quan nhiều keys (stream chính, dead stream, state hash), Redis Cluster yêu cầu những keys trong thao tác atomic nhiều key phải ở **cùng hash slot**, khi command/script áp dụng quy tắc đó.

Ví dụ namespace:

~~~text
orders:{fulfillment}:events
orders:{fulfillment}:dead
orders:{fulfillment}:state
~~~

Hash tag **fulfillment** giúp keys thuộc cùng slot, nhưng **không tự tạo distributed transaction** với DB hoặc Kafka. Không cần ép mọi stream của toàn công ty cùng slot vì có thể gây hotspot.

### 19.4. Sentinel/failover và unknown outcomes

Một XACK/XADD có thể thành công trên server nhưng client timeout trước response. Khi kết quả là **UNKNOWN**, đừng mặc định thao tác chưa được áp dụng. Kiểm tra:

- XACK đã loại ID khỏi PEL chưa?
- EventId đã được ghi trong business DB chưa?
- Producer outbox record đã được mark dispatched chưa?
- Một duplicate XADD đã được tạo chưa?

Thực hiện retry theo **idempotency và reconcile**, không chỉ bằng sleep rồi gửi lại vô điều kiện.

### 19.5. Consumer name và failover

Redis consumer names không phải health registry tự động của Kubernetes. Nếu pod bị thay tên sau deploy, PEL entries của consumer name cũ không tự được chuyển; **reclaimer** cần tìm stale owners và claim.

## 20. Backpressure, batchSize và concurrency

Reactive StreamReceiver hỗ trợ demand-driven consumption, nhưng **backpressure trên Flux** không thay thế mọi queueing/reliability problem.

### 20.1. Sơ đồ tải

~~~mermaid
flowchart LR
    P["XADD 500 rec/s"] --> R["Redis Stream"]
    R --> AD["StreamReceiver COUNT 20"]
    AD --> C["MessageChannel"]
    C --> EX["Executor / reactive pipeline"]
    EX --> DB["Business DB<br/>100 rec/s"]
    DB -. "ACK" .-> R
~~~

Khi producer ghi 500 records/s và business chỉ xử lý 100 records/s, backlog có thể tăng. Phải đo **group lag, pending count, in-flight work và age**; tăng batchSize/consumer concurrency không giúp nếu DB đã ở giới hạn.

### 20.2. batchSize là hint của Redis read

batchSize=20 giới hạn số records Redis có thể trả theo COUNT, không giới hạn số task đang bay trong mọi executor/thread hoặc số records được ACK cùng lúc. Nếu thiết kế xử lý 20 records song song, mỗi record cần **tự quản lý ACK/error outcome**.

### 20.3. Consumer concurrency trong cùng group

Nhiều **consumer names** trong một group có thể cạnh tranh nhận records mới:

~~~text
Group fulfillment-v1:
  worker-a
  worker-b
  worker-c
~~~

Redis có thể phân phối new records cho những consumers đang XREADGROUP. Không cam kết round-robin tuyệt đối hoặc business completion order. Nếu orderId O-1001 có events A rồi B, concurrent workers có thể hoàn tất B trước A.

### 20.4. Ordering và version

Nếu business cần ordering theo orderId:

- Tạo **business sequence/version** trong payload.
- Validate current version khi cập nhật database.
- Phân vùng công việc theo key hoặc serialize processing per entity khi cần.
- Chấp nhận retry có thể làm event cũ về muộn.
- Không dùng Redis Stream ID như thứ tự commit business toàn cục giữa nhiều producers.

Một stream có ordered IDs nhưng **không bảo đảm thứ tự hoàn tất các side effects** khi group có nhiều consumers.

### 20.5. Blocking code trong reactive path

Không chạy một JDBC query blocking lâu trên Redis reactive I/O thread nếu có thể tránh. Dùng một worker execution model/bounded scheduler phù hợp, nhưng **nơi ACK** phải gắn với completion signal của business operation, không phải lúc task được submit.

### 20.6. Output channel ảnh hưởng ACK timing

| Channel | Đặc tính | Rủi ro nếu ACK không đúng chỗ |
| --- | --- | --- |
| DirectChannel | Dispatch đồng bộ | Handler blocking có thể giữ transport thread |
| ExecutorChannel | Submit task lên executor | ACK ngay sau submit có thể mất work khi crash |
| QueueChannel | Đệm Spring Messages; có thể poll downstream | Không mặc định durable; ACK trước durable handoff dễ mất work |
| FluxMessageChannel | Reactive handoff/demand | Completion và ack phải bám đúng record/reactive signal |

Một QueueChannel dùng persistent MessageStore có thể tạo durable handoff, nhưng cần bảo đảm **message và metadata cần thiết có thể serialize an toàn**, cùng trình tự ACK sau khi lưu thành công. Không serialize native ACK callback như payload lâu dài; dùng stream key/recordId và cơ chế recovery rõ ràng.

### 20.7. Prefetch Redis Streams không giống RabbitMQ

Không tìm RabbitMQ **prefetchCount** để cấu hình Redis Stream inbound. Redis Streams dùng XREADGROUP COUNT/BLOCK và StreamReceiver demand/backpressure; PEL và consumer group là khái niệm riêng. Áp nhầm tham số từ AMQP/JMS/Kafka sẽ tạo cảm giác đã kiểm soát in-flight trong khi chưa có chính sách tương ứng.

## 21. Lifecycle: start, stop, restart và rolling deployment

### 21.1. Khi khởi động

~~~mermaid
sequenceDiagram
    participant APP as Spring Application
    participant E as Stream inbound endpoint
    participant R as Redis
    participant H as Business handler
    APP->>E: Initialize / start
    E->>R: Connect / verify consumer group
    E->>R: XREADGROUP BLOCK/COUNT
    R-->>E: New record
    E->>H: Spring Message + metadata
    H->>R: XACK after business commit
~~~

**AutoStartup=true** chỉ có nghĩa endpoint được yêu cầu start cùng context; không chứng minh Redis group thực sự kết nối đúng, records được parse đúng hay pending recovery đã chạy xong. Cần readiness/health checks theo policy.

### 21.2. Khi stop graceful

Quy trình đề xuất:

1. Ngừng nhận new records hoặc drain subscription theo lifecycle.
2. Cho in-flight handlers hoàn tất trong timeout hữu hạn.
3. Ghi durable business state và ACK khi hoàn tất.
4. Những records chưa ACK để lại trong PEL cho recovery worker.
5. Không xóa consumer group hoặc stream key khi deploy.
6. Sau restart, kiểm tra XPENDING và stale consumers.

Nếu ứng dụng chạy lâu hơn shutdown grace period, một số records có thể dừng ở trạng thái pending; đó là lý do cần **recovery/idempotency**.

### 21.3. Khi scale up/down

Đặt consumer group **ổn định theo workload** và consumer name **unique per active instance**. Khi scale down, kiểm tra pending entries thuộc consumers ngừng hoạt động. Không nhầm số active pods với số pending owners được Redis giữ lại.

### 21.4. Tạo group và migration

Khi nâng phiên bản/schema:

- Giữ group cũ nếu muốn tiếp tục group progress.
- Tạo group mới với **offset có chủ đích** nếu cần replay.
- Không delete group cũ trước khi đối soát pending và retention.
- Xác định consumer cũ/cũ record schema sẽ được xử lý thế nào.
- Nếu group tạo tại '$', những records hiện có trước đó sẽ không được giao như new group records theo offset khởi tạo.

### 21.5. Lỗi nối mạng khi đọc

StreamReceiver có thể khôi phục connection/đường đọc tùy client và onErrorResume policy. Nhưng **một connection đã hồi phục** không đồng nghĩa:

- Pending của worker cũ được tự claim.
- Business records bị trim được tự phát lại.
- Consumer đã đổi group offset về đúng điểm.
- Callback ACK cho các records đã xử lý trước crash sẽ tự chạy lại.

Phải kiểm tra từng điều kiện trong test và monitoring.

## 22. Security: ACL, tenant boundary và serializer

Redis Streams là nguồn dữ liệu ngoài ứng dụng Spring Integration, vì thế fields và metadata được nhận **không tự là input đáng tin cậy**.

### 22.1. Redis ACL và network

Nên phân quyền theo vai trò:

| Actor | Quyền cần thiết về mặt chức năng |
| --- | --- |
| Producer | XADD vào stream được phép |
| Consumer group worker | XREADGROUP, XACK và truy cập stream/group đúng phạm vi |
| Recovery worker | XPENDING/XCLAIM/XAUTOCLAIM cho group được phép |
| Admin/bootstrap | XGROUP CREATE, cấu hình retention khi được ủy quyền |
| Operator | XINFO, xem lỗi, replay có audit; không mặc định FLUSHDB/XGROUP DESTROY |

Redis ACL hỗ trợ quy định key/commands theo Redis version; cấu hình tối thiểu còn phụ thuộc các lệnh mà client/framework phát hành. Đừng cấp quyền admin cho mọi worker chỉ để **setCreateConsumerGroup(true)** chạy được.

Trong production, dùng TLS, credential rotation, secret manager, giới hạn mạng/port và audit những thao tác xóa/trim/group reset.

### 22.2. Tenant và eventType không xác thực quyền

Giả sử producer đưa record:

~~~text
eventType=ORDER_CREATED
tenantRef=another-tenant
orderId=O-999
~~~

Consumer không được tự coi tenantRef là bằng chứng rằng caller có quyền tạo fulfillment cho tenant đó. Hãy tra **order ownership** và policy ở nguồn tin cậy hoặc dựa vào một producer identity/channel authorization được kiểm soát. Stream group và Redis key naming không thay business authorization.

### 22.3. Serializer trusted types

Nếu người viết stream không phải cùng một trust boundary, tránh native Java deserialization và polymorphic type mapping không giới hạn. Dùng:

- String field values hoặc JSON/schema format.
- HashMapper target DTO đã cho phép.
- Độ dài key/value tối đa.
- JSON nesting/array depth limits.
- Validation field enum, IDs, numeric ranges.
- Schema migration rõ ràng.

Không bật Jackson default typing tùy ý cho một trường do producer bên ngoài tạo.

### 22.4. Redis stream field names không phải Spring headers

Một Redis record field **"acknowledgmentCallback"** không tự trở thành đối tượng SimpleAcknowledgment tin cậy. Header ACK callback do **adapter** đưa vào Spring Message trong runtime. Tránh chuyển raw record fields thành những header nội bộ quan trọng bằng mapping vô điều kiện.

### 22.5. PII, logging và dead-letter retention

Đừng log toàn bộ record nếu chứa email, địa chỉ giao hàng hoặc token. Với dead-letter stream, cần giới hạn retention, quyền đọc, mã hóa theo hạ tầng, chính sách xóa dữ liệu và audit replay. **DLQ thường chứa dữ liệu lỗi nhạy cảm hơn stream thông thường**.

### 22.6. Rate limiting và resource abuse

Một producer có thể XADD quá nhanh hoặc tạo records lớn, khiến Redis memory, consumer PEL và service downstream quá tải. Kiểm soát upstream rate, validation/kích thước, stream retention, batch/concurrency, quotas và alerting.

## 23. Monitoring: lag, pending, ACK và business outcome

Không xây dashboard chỉ dựa vào **XLEN** hoặc số records đã được StreamReceiver giao. Một consumer group có nhiều mốc cần đo.

| Tín hiệu | Mục đích | Giới hạn |
| --- | --- | --- |
| **XADD rate** | Producer ghi bao nhiêu records | Không phải số business events duy nhất |
| **XLEN** | Records còn trong stream | Không phải PEL count hay group lag |
| **Group last-delivered ID** | Tiến độ đọc của group | Có thể ahead so với completed business |
| **Consumer group lag** | Ước tính records chưa được giao | Có thể không đầy đủ khi trim/delete, version-dependent |
| **XPENDING total** | Records đã delivered chưa ACK | Không chỉ rõ business đã commit hay chưa |
| **Oldest pending idle** | Phát hiện stale consumers | Có thể là job hợp lệ xử lý lâu |
| **XACK rate** | Tốc độ xác nhận | Không chứng minh business commit nếu autoAck quá sớm |
| **Business completed rate** | Số records đã hoàn thành side effect | Quan trọng nhất cho SLA |
| **Duplicate skipped rate** | Idempotency bảo vệ khi retry | Có thể tăng sau crash/reclaim |
| **DLQ ingress** | Dữ liệu poison/exhausted | Cần owner và replay policy |
| **Error rates** | Serializer, schema, Redis I/O, DB, external APIs | Phải phân nhóm |
| **Processing latency** | Thời gian receive → durable commit → ACK | Dùng p95/p99, timeout |

### 23.1. Metrics minh họa

~~~text
redis_stream_inbound_received_total{stream="orders-events",group="fulfillment-v1"}
redis_stream_inbound_decode_failed_total{reason="INVALID_UTF8"}
redis_stream_inbound_ack_total{result="success"}
redis_stream_inbound_ack_failed_total
redis_stream_inbound_pending_oldest_seconds
redis_stream_inbound_reclaimed_total
redis_stream_inbound_group_lag
fulfillment_event_committed_total
fulfillment_event_duplicate_skipped_total
fulfillment_event_failed_total{reason="INVALID_SCHEMA"}
fulfillment_event_processing_duration_seconds
~~~

Đây là **tên metric do ứng dụng có thể tự instrument**, không phải Spring Integration tự xuất đầy đủ. Dùng labels cardinality thấp như stream alias, group và bounded reason enum; không gắn eventId/recordId/tenantId tùy ý thành metric label.

### 23.2. Redis CLI vận hành

~~~bash
redis-cli XINFO STREAM orders:events
redis-cli XINFO GROUPS orders:events
redis-cli XINFO CONSUMERS orders:events fulfillment-v1
redis-cli XPENDING orders:events fulfillment-v1
redis-cli XLEN orders:events
~~~

Các commands trên quan sát metadata; thực thi trên production vẫn phải tuân thủ ACL, audit và chi phí query. Với streams/groups lớn, dùng dạng command có giới hạn thay vì quét không hạn chế.

### 23.3. Pending không giảm

Nếu business success tăng mà XPENDING vẫn tăng:

1. autoAck có thực sự false không?
2. Handler có nhận ACKNOWLEDGMENT_CALLBACK không?
3. Handler có gọi acknowledge() sau commit?
4. Redis XACK có lỗi/unknown outcome không?
5. Stream/group/recordId đúng không?
6. Records cũ của consumer name đã chết đang chờ reclaim?

Không chỉ tăng số workers để làm pending count giảm; nếu mọi workers đều không ACK, backlog pending sẽ tiếp tục tăng.

### 23.4. Lag thấp nhưng business chậm

Khi XREADGROUP giao nhanh, group last-delivered ID có thể gần cuối stream nhưng hàng nghìn records **đang pending**. Monitor cả **group lag** và **PEL/in-flight/business completion**. Một dashboard chỉ hiển thị group lag gần 0 có thể báo sai “không backlog”.

### 23.5. ACK thấp nhưng PEL cũng thấp

Kiểm tra liệu adapter đang **autoAck(true)** và ACK rất sớm hay group đang đọc XREAD standalone chứ không phải XREADGROUP. Nếu không dùng consumer group, **XPENDING của một group không mô tả các standalone reads**.

### 23.6. Trace correlation

Giữ eventId và traceparent trong record fields hoặc propagation contract, ghi chúng vào structured logs theo quy định. Có thể gắn stream ID/group/consumer như metadata log, nhưng không dùng trace context để cấp quyền hoặc deduplicate nghiệp vụ.

## 24. Kiểm thử: Unit, contract và Redis integration

Một bài học về stream inbound phải xác minh **Redis thực có group/PEL/ACK**, không chỉ test method xử lý Map ở service.

### 24.1. Ma trận kiểm thử

| Test | Thiết lập | Assertion |
| --- | --- | --- |
| **XADD happy path** | Producer thêm record hợp lệ | Redis trả RecordId, XRANGE có fields |
| **Consumer group creation** | Tạo group từ 0-0 trước record | XREADGROUP nhận backlog theo contract |
| **Group starts at $** | Có backlog, tạo group từ cuối | Không nhận backlog như new records |
| **Standalone XREAD** | Không đặt consumerName | Không tạo pending của group |
| **Manual ACK** | autoAck=false, handler commit | PEL giảm sau callback/ACK |
| **No ACK** | Handler ném exception trước callback | Record ở PEL, không tự redeliver với > |
| **Auto ACK** | autoAck=true, handler lỗi sau receive | Test cửa sổ đã ACK nhưng side effect fail |
| **Payload extraction** | extractPayload=true | Handler nhận value/fields, stream headers vẫn phù hợp |
| **Full Record** | extractPayload=false | Handler nhận Record có ID/value |
| **Header contract** | Group XREADGROUP | RedisHeaders.STREAM_KEY/STREAM_MESSAGE_ID/CONSUMER_GROUP/CONSUMER đúng |
| **Serializer mismatch** | Producer/receiver khác format | Conversion error được quan sát |
| **Malformed field** | schemaVersion sai | Error path + record không ACK vô tình |
| **Bad deserialization** | Payload khiến mapper lỗi | ErrorChannel có policy ACK/DLQ phù hợp |
| **Business idempotency** | Hai records cùng eventId | Side effect chỉ commit theo business key một lần |
| **Crash before commit** | Kill worker sau XREADGROUP | PEL giữ record, reclaim phục hồi |
| **Crash after commit** | Kill trước XACK | Reclaim có duplicate, handler skip và ACK |
| **Crash after XACK** | Verify record còn trong stream | XACK không XDEL |
| **Two consumers same group** | worker-a/worker-b cùng XREADGROUP | New records phân phối, không broadcast toàn bộ |
| **Two separate groups** | fulfillment và analytics | Mỗi group có tiến độ độc lập |
| **Pending reclaim** | Worker-a chết, idle > threshold | XAUTOCLAIM chuyển ownership đúng |
| **Long-running job** | Worker vẫn chạy nhưng idle tăng | Policy không tạo side effect trùng |
| **Poison record** | Sai schema nhiều attempts | Final dead-letter bền vững, ACK original theo policy |
| **DLQ and ACK failure** | Dead XADD success, XACK timeout | Deduplicate dead-letter khi retry |
| **Trim while pending** | XTRIM record chưa ACK | Phát hiện nguy cơ mất raw payload |
| **Retention/backlog** | Consumer offline lâu | Records còn nếu retention đủ, có khả năng nhận về sau |
| **Redis failover** | Restart Redis test | Group/PEL/records tồn tại theo RPO đã cấu hình |
| **ReadOffset.latest** | Standalone polling có khoảng dừng | Không tự cam kết đọc mọi record |
| **ReadOffset.lastConsumed** | Group + manual ACK | New reads theo group, pending cần reclaim riêng |
| **Async Channel** | ACK trước worker finish | Test rủi ro mất work nếu crash |
| **Backpressure** | Producer nhanh hơn handler | PEL/lag/backlog có thể tăng, không OOM |
| **Wrong consumerName** | Hai replicas cùng name | Quan sát ownership/operational confusion |
| **Wrong stream/group** | Config sai Redis key | Không nhận message hoặc Redis error rõ |
| **ACL denied** | Redis user thiếu XREADGROUP/XACK | Adapter/error metrics rõ, không ACK giả |
| **Cross-slot Lua** | Redis Cluster với các keys khác slot | Không âm thầm thực hiện một phần |
| **Rolling schema change** | v1/v2 producers & consumers | Compatibility, poison policy và replay đúng |

### 24.2. Test Redis CLI manual ACK

Trên Redis test:

~~~bash
redis-cli XGROUP CREATE test:orders:events test-fulfillment 0-0 MKSTREAM
redis-cli XADD test:orders:events '*' eventId evt-test-1 eventType ORDER_CREATED schemaVersion 1 orderId O-1
redis-cli XREADGROUP GROUP test-fulfillment worker-a COUNT 1 STREAMS test:orders:events '>'
redis-cli XPENDING test:orders:events test-fulfillment
~~~

Ghi nhận Redis ID trả từ XREADGROUP, ví dụ **1795410000123-0**, rồi ACK đúng record:

~~~bash
redis-cli XACK test:orders:events test-fulfillment 1795410000123-0
redis-cli XPENDING test:orders:events test-fulfillment
redis-cli XRANGE test:orders:events - +
~~~

Sau XACK, pending ID không còn thuộc group PEL; nhưng record **vẫn có thể còn trong XRANGE**. Đây là test quan trọng để phân biệt ACK với XDEL.

### 24.3. Test start timing

Với consumer group đã được tạo từ 0-0 và retention đủ, XADD **trước khi Java adapter start** vẫn có thể được XREADGROUP đọc. Đây là khác Redis Pub/Sub.

Tuy nhiên nếu group tạo tại '$' sau khi events đã có, backlog có thể bị bỏ qua theo group position. Test phải kiểm soát **thứ tự: tạo stream, tạo group, XADD, start adapter** và không dựa vào Thread.sleep ngẫu nhiên.

### 24.4. CountDownLatch capture helper

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.messaging.Message;

public final class StreamMessageCapture {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<Message<?>> captured =
        new AtomicReference<>();

    public void accept(Message<?> message) {
        captured.set(message);
        latch.countDown();
    }

    public Message<?> awaitMessage() throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError(
                "Redis stream message not received");
        }
        return captured.get();
    }
}
~~~

**Đây chỉ là helper**, không phải integration test hoàn chỉnh. Test phải nối helper vào một IntegrationFlow riêng, khởi chạy Redis server/container test, tạo group với offset rõ, cấu hình serializer đúng và xác minh ACK/PEL bằng Redis commands hoặc Spring Data Redis API.

Không dùng cùng queue/stream/group test với consumer production hoặc một worker khác đang đọc cạnh tranh.

## 25. Business idempotency: hiệu quả tương đương một lần xử lý

Redis Stream + manual ACK bảo vệ trạng thái **delivered nhưng chưa acknowledged**, nhưng không quyết định transaction của một database hoặc hệ thống thứ ba. Cần một **business idempotency boundary**.

### 25.1. Durable inbox ở FulfillmentService

Ví dụ bảng:

~~~sql
CREATE TABLE fulfillment_inbox (
    event_id       VARCHAR(80) PRIMARY KEY,
    event_type     VARCHAR(80) NOT NULL,
    order_id       VARCHAR(80) NOT NULL,
    status         VARCHAR(20) NOT NULL,
    processed_at   TIMESTAMP NULL
);
~~~

Trong một JDBC transaction:

1. Validate eventId/orderId và authorization.
2. Dùng unique constraint trên **event_id** để xử lý race giữa các workers.
3. Nếu event đã DONE, bỏ qua business side effect mới và báo xử lý idempotent thành công.
4. Nếu chưa xử lý, tạo shipment hoặc ghi durable work intent.
5. Commit inbox + business state phù hợp.
6. **Sau khi transaction thực sự hoàn tất thành công**, ACK Redis record.

Đây là thiết kế, không phải toàn bộ DDL/index/locking của một production database. Với PostgreSQL có thể dùng **INSERT ... ON CONFLICT**; với hệ CSDL khác chọn cú pháp tương thích và test transaction isolation/concurrent workers.

### 25.2. Một DB transaction không bao gồm external API

Giả sử handler gọi ShippingProvider API:

~~~text
Send HTTP createShipment(idempotencyKey=evt-order-1001)
  -> timeout
~~~

Không biết provider đã tạo shipment hay chưa. Nếu retry không có idempotency/lookup, có thể tạo hai shipments. Giải pháp:

- Truyền **business idempotency key** được provider hỗ trợ.
- Lưu request/response state bền vững.
- Nếu response UNKNOWN, tra trạng thái trước khi gửi lại.
- Không ACK Redis khi chỉ mới submit một async request mà chưa có mốc durable handoff.

### 25.3. ACK duplicate có thể vẫn là hành vi đúng

Một record XADD được deliver lại sau crash. Fulfillment DB cho thấy eventId đã DONE. Handler:

~~~text
Validate eventId
  -> find DONE in durable inbox
  -> skip external side effect
  -> ACK Redis record
~~~

Đây là **idempotent consumer**: Redis có thể at-least-once delivery, nhưng business side effect không bị lặp theo eventId.

### 25.4. Same eventId, different content

Nếu hai stream records chứa cùng eventId nhưng orderId/tenant khác nhau, không được lặng lẽ bỏ qua như duplicate hợp lệ. Nên lưu **payload hash/version** hoặc kiểm tra business identity; khi cùng ID nhưng nội dung khác, tạo security/contract alert hoặc cách ly để điều tra.

### 25.5. Đừng xóa inbox quá sớm

Nếu inbox chỉ giữ eventId 24 giờ nhưng stream có thể replay sau bảy ngày, consumer có thể quên sự kiện đã DONE và tạo side effect lần nữa. **Retention của idempotency ledger phải lớn hơn hoặc bằng khoảng thời gian duplicate/replay có thể xuất hiện**, hoặc có một business uniqueness rule mạnh hơn.

## 26. Tình huống kiến trúc thực tế

### 26.1. Case A – Orders → Fulfillment, mỗi record cần được xử lý

~~~mermaid
flowchart LR
    O["OrderService DB"] --> OB[("Transactional outbox")]
    OB --> PUB["Outbox publisher"]
    PUB --> STR[("Redis Stream<br/>orders:events")]
    STR --> G["Group fulfillment-v1"]
    G --> SI["Stream inbound adapter"]
    SI --> INBOX[("Fulfillment inbox + DB")]
    INBOX --> ACK["XACK after commit"]
    ACK -.-> STR
    G --> REC["Pending reclaimer"]
    REC --> INBOX
~~~

**Thiết kế hợp lý:** Group ổn định, manual ACK, durable inbox, PEL recovery và retention đủ dài. Nếu XADD thành công nhưng outbox publisher nhận timeout, producer có thể gửi trùng eventId; FulfillmentService vẫn deduplicate.

**Không nên:** autoAck mặc định true và coi XPENDING=0 là đã tạo shipment.

### 26.2. Case B – Một stream, hai nhóm độc lập

**Yêu cầu:** Fulfillment và Analytics đều phải nhận OrderCreated.

~~~text
Redis Stream orders:events
    |
    +-- Group fulfillment-v1 --> Fulfillment workers A/B
    |
    +-- Group analytics-v1   --> Analytics workers X/Y
~~~

Mỗi group có **tiến độ đọc, PEL và ACK riêng**. Analytics chậm không nhất thiết làm fulfillment chậm, nhưng **retention của stream cần đủ cho cả hai groups**. Tránh xóa raw record vì fulfillment đã ACK trong khi analytics còn cần nó.

### 26.3. Case C – SFTP import → Redis Streams

**Yêu cầu:** File CSV qua SFTP chứa 10.000 đơn hàng; parser tạo events đưa vào stream.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound adapter<br/>poller"] --> PAR["CSV parser/validation"]
    PAR --> DB[("Import DB + outbox")]
    DB --> XADD["Redis Stream outbound<br/>XADD"]
    XADD --> STR[("orders:events")]
    STR --> RIN["Redis Stream inbound"]
    RIN --> H["Idempotent processor"]
    H --> DB
~~~

**SFTP poller** quét file nguồn, còn **StreamReceiver** đọc stream records. Không dùng Redis store polling adapter hoặc Redis Pub/Sub subscriber như thể chúng đều có PEL/ACK.

Không đánh dấu toàn bộ file import DONE chỉ vì đã XADD 10.000 records; cần theo dõi **business completion** của từng event, hoặc định nghĩa rõ mốc import chỉ là “successfully queued”.

### 26.4. Case D – Redis Stream inbound → Kafka outbound

Một bridge có thể:

~~~text
Redis XREADGROUP
  -> Spring Message
  -> Kafka producer
  -> Kafka broker ACK
  -> Redis XACK
~~~

**Hai khoảng lỗi:**

- Redis XACK trước Kafka ACK → Redis cho rằng xong, Kafka có thể chưa lưu: **mất event**.
- Kafka ACK thành công nhưng Redis XACK thất bại → record pending, bridge gửi lại: **duplicate Kafka event**.

Chọn thứ tự **Kafka publish confirmed trước Redis ACK**, đồng thời Kafka consumers deduplicate theo eventId hoặc dùng một durable bridge/outbox/inbox. **Kafka idempotent producer** có phạm vi bảo vệ riêng, không tạo một transaction nguyên tử giữa Redis consumer group và Kafka broker.

### 26.5. Case E – Redis Stream inbound → AMQP outbound

Nguyên tắc tương tự:

~~~text
XREADGROUP -> transform -> RabbitTemplate/outbound adapter
           -> publisher confirm/return policy
           -> XACK after durable handoff
~~~

Publisher confirm, mandatory returns, unroutable messages và business ACK của consumer RabbitMQ là **những mốc khác nhau**. Khi cần handoff chính xác, xác minh routing tới queue/broker và dùng eventId/idempotency; không ACK Redis chỉ vì outbound MessageChannel.send() trả thành công trong mọi cấu hình.

### 26.6. Case F – Cache invalidation best-effort

Nếu chỉ phát một tín hiệu “cache thay đổi” không cần backlog hoặc PEL, Redis Pub/Sub inbound có thể đơn giản hơn Streams. Nếu phải replay sau downtime hoặc cần audit event IDs, Streams hợp lý hơn nhưng kéo theo **retention, consumer group, ACK, recovery**. Chọn theo SLA, không chỉ theo throughput.

### 26.7. Case G – Nhiều tenants dùng một stream

Một stream chung cho nhiều tenants giúp vận hành ít keys hơn nhưng mở rộng trust boundary:

- Consumer phải validate tenantRef theo policy.
- Không lấy tenantRef làm chứng cứ authorization.
- Rate limit per tenant/producer.
- Không để một tenant quá tải ngăn các tenants khác được xử lý.
- Cân nhắc stream/group isolation khi cần SLA hoặc compliance riêng.

Không tự tạo consumer group per tenant một cách vô hạn nếu group metadata/PEL và retention không được quản lý.

## 27. Troubleshooting: stream consumer không nhận hoặc không ACK

### 27.1. Không nhận records dù Redis có XLEN > 0

Kiểm tra theo thứ tự:

1. Redis **host/port/database/cluster** của publisher và consumer có cùng dữ liệu không?
2. **Stream key** có chính xác không (case-sensitive)?
3. Group đã tồn tại chưa? Tạo từ **0-0 hay '$'**?
4. Adapter đang **XREAD standalone hay XREADGROUP**? ConsumerName có được đặt?
5. **ReadOffset** là latest hay lastConsumed?
6. Records có nằm trong **PEL** cũ thay vì new deliveries không?
7. Redis ACL cho XREADGROUP/XACK có đúng không?
8. Serializer có decode được fields không?
9. MessageChannel có subscriber/handler đang hoạt động không?
10. Handler có lỗi hoặc errorChannel nuốt exception không?
11. Redis retention có trim records trước khi consumer nhận không?

**XLEN > 0 không tự có nghĩa group sẽ được giao tất cả records đó**; group offset có thể đã ở cuối hoặc records đang pending ở một consumer khác.

### 27.2. Nhận được nhưng pending tăng

Khả năng thường gặp:

- autoAck(false) nhưng handler không gọi callback.
- Handler lỗi trước business commit.
- ACK gọi nhưng Redis I/O thất bại/timeout.
- Business work async chưa hoàn tất.
- Consumer name cũ chết, pending thuộc owner không hoạt động.
- Schema lỗi khiến nhiều records bị giữ để điều tra.

Kiểm tra **XPENDING, XINFO CONSUMERS, eventId business state và error metrics**; không chỉ tăng consumer concurrency.

### 27.3. Handler chạy hai lần cho cùng event

Có thể do:

- Producer XADD lại cùng eventId với ID khác.
- Recovery claim record sau crash/ACK failure.
- Hai integration paths/handlers đang nhận một event.
- Một replay operator phát lại bản cũ.
- Group bị reset/đổi offset.

Giải pháp: **idempotent business key**, trace recordId và producer attempts. Không tuyên bố Redis Streams bảo đảm exactly-once khi application chưa có hợp đồng side effect idempotent.

### 27.4. Không thấy lỗi serializer trong business handler

Lỗi xảy ra **trước khi adapter tạo Spring Message**. Kiểm tra StreamReceiver onErrorResume/errorChannel, trusted serializers, format producer và ACK policy đối với ErrorMessage. Đừng chỉ thêm try/catch trong service activator.

### 27.5. Consumer mới bỏ qua records cũ

Group có thể được tạo từ **'$'** hoặc standalone receiver dùng **latest()**. Tạo group mới từ **0-0** chỉ khi muốn replay có chủ đích, có kế hoạch idempotency. Không tùy tiện reset offset group production khi có pending chưa xử lý.

### 27.6. XAUTOCLAIM không cứu được record

Kiểm tra:

- Min idle time đã đủ chưa?
- Đúng group/stream key không?
- Cursor đã được xử lý hết chưa?
- Record đã bị trimmed/deleted chưa?
- Có consumer khác đang reclaim không?
- Reclaimer có thực sự commit/ACK sau claim không?

### 27.7. Redis group lag gần 0 nhưng CPU/DB quá tải

Group đã deliver gần hết stream nhưng PEL/in-flight có thể rất lớn. Đo business latency/ACK/oldest pending. Nếu worker xử lý chậm, tăng batchSize có thể làm việc tồi hơn vì tạo thêm pending và memory pressure.

### 27.8. XACK trả 0

XACK có thể trả 0 khi ID không còn pending trong group (đã ACK, sai group/ID hoặc tình huống khác). Không retry business side effect chỉ vì XACK trả 0; xác minh metadata và trạng thái business.

### 27.9. Redis consumer group BUSYGROUP

Khi group đã tồn tại, một XGROUP CREATE với cùng tên có thể trả BUSYGROUP. Điều này thường là tín hiệu provision đã diễn ra; không tự xóa group rồi tạo lại. Adapter setCreateConsumerGroup(true) cần được kiểm thử behavior idempotent theo version.

### 27.10. Handler nhận Map nhưng không nhận Redis Record ID

Với extractPayload(true), payload là value; Stream ID thuộc **RedisHeaders.STREAM_MESSAGE_ID** trong Spring MessageHeaders. Nếu cần cả raw record, chuyển sang **extractPayload(false)** và test type/serializer. Không tự cast payload Map thành MapRecord.

### 27.11. Test chạy trên local nhưng fail khi scale

Một consumer name hardcode có thể trùng giữa các replicas. Một group mới có thể tạo từ offset không như mong đợi. Serializer/ACL có thể khác Redis test và production. Phải test với **hai consumers trong cùng group**, pending ownership, shutdown và reclaim; không chỉ một application instance.

## 28. Những hiểu lầm phổ biến

**“Redis Stream inbound cũng giống Redis Pub/Sub inbound.”** Không: Streams giữ records theo retention, hỗ trợ group/PEL/ACK; Pub/Sub notification không có subscriber backlog.

**“Redis Stream inbound đọc một Redis List bằng BRPOP.”** Không: nó dùng **XREAD/XREADGROUP** từ Redis Stream key.

**“Redis store inbound và stream inbound dùng chung Pollers.fixedDelay.”** Store inbound là polling MessageSource/view; stream inbound có **Reactive StreamReceiver** quản lý vòng đọc.

**“XADD thành công nghĩa là FulfillmentService xử lý xong.”** XADD chỉ ghi record vào Redis; xử lý business có mốc riêng.

**“Redis record ID chính là eventId của OrderCreated.”** Record ID và business eventId có phạm vi khác nhau; retry XADD có thể tạo record ID mới.

**“ReadOffset.latest() luôn an toàn để đọc lịch sử.”** Nó hướng tới records mới và có thể bỏ lỡ dữ liệu trong các trường hợp standalone/dead time; cần offset/checkpoint có chủ đích.

**“ReadOffset.lastConsumed() tự nhận lại mọi records trong PEL.”** Nó không tự claim pending của consumer khác; cần recovery.

**“ConsumerName không quan trọng khi dùng group.”** ConsumerName ảnh hưởng ownership PEL và cần được quản lý khi scale/restart.

**“Mỗi replica nên tạo một consumer group mới.”** Như vậy mỗi group có thể nhận riêng records, thay vì chia việc trong cùng group; còn làm phình group metadata.

**“Hai consumer groups chia đều một stream.”** Các groups có tiến độ độc lập; **trong cùng group** mới có competing consumers.

**“Consumer group mặc định có exactly-once business delivery.”** Có thể redelivery sau crash/ACK loss; cần idempotency.

**“AutoAck=true an toàn nếu handler có @Transactional.”** ACK có thể xảy ra trước business commit theo đường auto-ack, không tự gắn vào DB transaction.

**“Manual ACK là gọi XACK ngay khi MessageChannel.send trả về.”** Chỉ ACK sau durable business commit/handoff, không phải sau submit async.

**“Không ACK sẽ tự nhận lại bằng XREADGROUP > ở lượt sau.”** Pending không tự thành new record; cần read pending/reclaim.

**“XACK xóa dữ liệu khỏi Redis Stream.”** XACK chỉ xử lý PEL của group, không đồng nghĩa XDEL/XTRIM.

**“XDEL là ACK cho mọi groups.”** XDEL xóa raw record; group-specific ACK/state khác biệt và còn rủi ro mất dữ liệu cho groups khác.

**“Stream giữ records mãi dù XTRIM/MAXLEN.”** Retention có thể loại records, kể cả payload cần cho pending recovery.

**“Pending count = số records chưa được xử lý đúng.”** Pending bao gồm delivered chưa ACK, có thể business đã commit nhưng ACK thất bại.

**“Group lag = 0 nghĩa là không còn công việc.”** Có thể PEL/in-flight rất lớn; phải đo cả business completion.

**“Kafka prefetchCount hoặc RabbitMQ basic.nack có thể dùng nguyên trong Redis Streams.”** Redis dùng COUNT/BLOCK/PEL/XACK/CLAIM, không có AMQP NACK semantics.

**“ACK callback là một custom Redis field.”** Nó là Spring Integration runtime header, không phải field do producer XADD tùy ý.

**“Sửa String header ack=true làm Redis ACK.”** Chỉ callback/API Redis hợp lệ mới thực hiện ACK thực.

**“ErrorChannel log exception thì record đã được cách ly.”** Log không tạo durable DLQ; phải lưu raw error state và quyết định ACK rõ.

**“Redis Streams có DLX giống RabbitMQ.”** Redis có thể xây dead stream theo ứng dụng, không có DLX auto-route mặc định.

**“XAUTOCLAIM chỉ nhận lại records chắc chắn chưa xử lý.”** Có thể reclaim record đã commit business nhưng ACK thất bại; cần eventId/idempotency.

**“Min idle > 60 giây nghĩa là worker cũ đã chết.”** Worker cũ có thể đang xử lý lâu; cần owner, lease, fencing và side effect idempotent.

**“Khi Redis failover, mọi XADD/XACK đều chắc chắn thành công hoặc thất bại rõ.”** Connection timeout có thể dẫn tới UNKNOWN outcome.

**“Đặt batchSize=100 bảo đảm 100 business commits.”** COUNT là giới hạn read, không phải batch transaction/ACK.

**“Reactive adapter bảo đảm mọi downstream handler non-blocking.”** Nếu handler dùng JDBC/HTTP blocking thì toàn flow vẫn có blocking work.

**“Đưa ACK callback vào QueueChannel memory là bền vững.”** Callback là runtime object, QueueChannel mặc định không phải durable handoff.

**“Consumer group được tạo từ '$' sẽ đọc backlog trước đó.”** Group tạo ở cuối nhằm nhận các records mới; cần offset 0-0 khi muốn từ đầu còn giữ.

**“Records có trong XRANGE chắc chắn mọi group đều sẽ đọc được.”** Group offset/read strategy khác nhau; có thể không giao records đó như new messages.

**“Hai records khác stream ID chắc chắn là hai business events.”** Có thể là cùng eventId do producer retry/replay.

**“Một service chung stream tenantRef là đủ để xác thực quyền.”** TenantRef là input, phải xác minh authorization theo nguồn đáng tin.

**“Chạy XGROUP DESTROY giúp sửa pending lỗi mà không ảnh hưởng dữ liệu.”** Xóa group làm mất group progress/PEL; cần kế hoạch migration/recovery.

**“Chỉ test happy path đủ chứng minh at-least-once.”** Phải test crash, group offsets, PEL recovery, trim, duplicate, ACK unknown và rolling schema.

## 29. Checklist thiết kế Redis Stream inbound trước production

| Nhóm | Câu hỏi cần trả lời |
| --- | --- |
| **Use case** | Cần replay/PEL/ACK hay chỉ cần Pub/Sub notification best-effort? |
| **Stream key** | Đúng Redis instance/database/namespace, key type STREAM chưa? |
| **Producer contract** | XADD record fields, eventId, eventType, schemaVersion, serializer rõ chưa? |
| **Reactive source** | ReactiveRedisConnectionFactory/StreamReceiver đúng version và lifecycle chưa? |
| **Adapter wiring** | Redis.streamInboundChannelAdapter hoặc ReactiveRedisStreamMessageProducer chỉ chạy một instance/flow đúng chủ đích? |
| **Mode** | XREAD standalone hay XREADGROUP? Có consumerName không? |
| **Group** | Group ổn định, group creation offset là 0-0 hay '$', đã provision trước chưa? |
| **Offset** | ReadOffset.latest/lastConsumed/from(id) phù hợp backlog policy? |
| **Manual ACK** | autoAck=false có được cấu hình và handler nhận ACKNOWLEDGMENT_CALLBACK? |
| **Business boundary** | XACK sau durable commit hoặc durable handoff, không sau submit async? |
| **Payload** | extractPayload(true/false) và MapRecord/ObjectRecord đã được test? |
| **Headers** | RedisHeaders.STREAM_KEY/STREAM_MESSAGE_ID/CONSUMER_GROUP/CONSUMER có đúng kiểu? |
| **Serialization** | Producer/receiver thống nhất key/field/value serializers và schema? |
| **Schema validation** | Malformed/unsupported data có error policy rõ? |
| **PEL recovery** | Ai chạy XPENDING/XAUTOCLAIM? Min idle, cursor, batch, owner và metrics? |
| **Idempotency** | Unique eventId và business transaction/durable inbox? |
| **Unknown outcomes** | ACK/XADD/provider timeout có kiểm tra state trước retry không? |
| **Retry** | Attempts, backoff và final failed state được lưu bền ở đâu? |
| **Dead-letter** | DLQ là durable stream/table, ACK original chỉ sau khi lưu thành công? |
| **Retention** | XTRIM/MAXLEN có giữ đủ backlog/pending cho slowest group? |
| **Concurrency** | Nhiều consumers có thể hoàn tất lệch thứ tự, xử lý version thế nào? |
| **Backpressure** | batchSize, reactive demand, handler capacity, executor bounds đã đo? |
| **Lifecycle** | Start/stop, drain, stale consumer names và restart recovery? |
| **Redis HA** | Persistence, replication, Cluster/Sentinel và failover/RPO/RTO? |
| **Security** | TLS, Redis ACL, stream/group permissions, tenant authorization? |
| **Monitoring** | Group lag, XPENDING, oldest idle, XACK rate, business DONE và DLQ? |
| **Testing** | Test Redis thật, crash-before-commit, crash-after-commit, claim, trim và duplicate? |
| **Compatibility** | Producer cũ/consumer mới, pending records v1, API version/serializer đã test? |

### 29.1. Nếu chỉ nhớ ba quy tắc

1. **Consumer group tiến độ không phải business completion**: một record delivered có thể nằm trong PEL, chưa commit.
2. **Manual ACK sau durable commit**, nhưng vẫn phải có idempotency vì crash-after-commit-before-XACK gây duplicate.
3. **PEL recovery và retention là hai cơ chế riêng**: pending phải được claim có kiểm soát, record raw phải còn để recover.

### 29.2. Khi nào không nên dùng Redis Streams?

Nếu chỉ là cache invalidation có TTL/reconciliation và không cần backlog, Pub/Sub có thể ít chi phí vận hành hơn. Nếu cần event sourcing/audit retention hàng năm, throughput rất cao hoặc cross-datacenter durability/transactions phức tạp, cần đánh giá Kafka/JMS/AMQP/database logs theo đặc thù hạ tầng.

**Không có transport nào loại bỏ hoàn toàn yêu cầu thiết kế idempotency và business transaction** trong môi trường phân tán.

### 29.3. Mức tối thiểu để có một demo đáng tin

~~~text
1. Redis test, stream key và group tạo từ offset 0-0.
2. Producer XADD eventId/eventType/schemaVersion/orderId.
3. Stream inbound autoAck=false + consumerName unique.
4. Handler validate schema + durable inbox/unique eventId.
5. ACK callback sau commit.
6. Recovery worker XPENDING/XAUTOCLAIM records stale.
7. Retention đủ dài và monitoring pending/business completion.
8. Integration test crash ở hai phía của commit/XACK.
~~~

Nếu thiếu bước recovery, demo vẫn có thể chạy happy path nhưng records pending sau crash **có nguy cơ bị bỏ quên**.

## 30. Câu hỏi tự kiểm tra

1. Redis Stream inbound adapter có trách nhiệm gì ở ranh giới Redis và Spring Integration?
2. Redis Streams khác Pub/Sub ở khả năng lưu giữ record và replay thế nào?
3. Redis List blocking POP khác XREADGROUP ở cơ chế pending/ACK ra sao?
4. Redis store inbound trả RedisStore view hay một Stream Record?
5. StreamReceiver của Spring Data Redis được dùng bởi Spring Integration Redis Stream inbound thế nào?
6. Một Redis Stream record có các thành phần gì ngoài field/value map?
7. Vì sao Redis Record ID không thể dùng làm eventId nghiệp vụ duy nhất trong mọi trường hợp?
8. XADD thành công chứng minh điều gì và không chứng minh điều gì?
9. XREAD standalone khác XREADGROUP như thế nào?
10. Khi nào nhiều consumers cùng group chia việc, khi nào nhiều groups độc lập cùng đọc một stream?
11. PEL là gì? Khi nào một record xuất hiện trong PEL?
12. XACK ảnh hưởng PEL và raw Redis Stream record khác nhau thế nào?
13. Nếu handler commit DB rồi crash trước XACK, lần recovery có thể dẫn tới điều gì?
14. Nếu autoAck xảy ra trước DB commit và JVM chết, rủi ro là gì?
15. Tại sao manual ACK + idempotency quan trọng hơn chỉ bật manual ACK?
16. ReadOffset.latest() và ReadOffset.lastConsumed() khác nhau ở hoàn cảnh nào?
17. Vì sao standalone latest có thể bỏ lỡ records giữa polls khi có dead time/backpressure?
18. XGROUP CREATE với 0-0 khác với '$' khi đã có backlog như thế nào?
19. Group last-delivered ID có tương đương số events đã commit nghiệp vụ không?
20. Khi worker-a chết, tại sao worker-b XREADGROUP với '>' không tự nhận mọi pending của worker-a?
21. XPENDING dùng để kiểm tra những thông tin nào?
22. XAUTOCLAIM cần min-idle-time và cursor để làm gì?
23. Tại sao một record idle lâu không chứng minh worker cũ đã chết?
24. Khi reclaim record đã được business commit nhưng chưa ACK, handler nên xử lý ra sao?
25. Spring Integration tự thêm những RedisHeaders nào vào Spring Message?
26. IntegrationMessageHeaderAccessor.ACKNOWLEDGMENT_CALLBACK là gì? Nó có nằm trong Redis record fields không?
27. extractPayload(true) khác extractPayload(false) thế nào?
28. Một producer ghi field values bằng StringRedisTemplate nhưng consumer dùng serializer khác có thể lỗi ở đâu?
29. Tại sao lỗi deserialization có thể xảy ra trước khi handler nhận Spring Message?
30. ErrorChannel có tự tạo Redis DLQ, retry budget và XACK không?
31. Với lỗi schema vĩnh viễn, nên chuyển record sang nơi cách ly theo thứ tự nào trước XACK?
32. Tại sao dead XADD thành công nhưng original XACK thất bại có thể tạo duplicate dead-letter?
33. BatchSize=20 có nghĩa mọi records cùng một business transaction không?
34. Khi producer nhanh hơn consumer, những metric nào giúp biết backlog đang nằm ở new messages hay PEL?
35. Khi group lag gần 0, tại sao vẫn có thể có hàng nghìn công việc chưa hoàn tất?
36. Redis Stream có cung cấp RabbitMQ basic.nack(requeue=true) cùng semantics không?
37. Redis XTRIM có thể ảnh hưởng tới payload của pending record thế nào?
38. XACK, XDEL và XTRIM khác nhau ra sao?
39. Vì sao retention cần dựa vào slowest required consumer group thay vì nhóm nhanh nhất?
40. Khi Redis failover, một XADD/XACK timeout có thể có outcome UNKNOWN như thế nào?
41. Redis Cluster yêu cầu điều gì khi dùng Lua/multi-key commands trên các keys khác nhau?
42. Khi scale từ một lên ba pods, phải quản lý group name và consumer names ra sao?
43. Một Redis Stream inbound handler dùng ExecutorChannel cần đặt ACK tại điểm nào?
44. Khi nào cần durable inbox trước khi ACK?
45. Unique constraint trên eventId bảo vệ khỏi loại race/duplicate nào?
46. Nếu cùng eventId xuất hiện với hai payload khác nhau, nên xử lý thế nào?
47. Nếu Kafka ACK thành công nhưng Redis XACK thất bại ở bridge, hậu quả là gì?
48. Nếu Redis XACK trước Kafka ACK, điều gì có thể mất?
49. Vì sao tracing metadata không phải authentication/authorization?
50. Một integration test nào chứng minh manual ACK làm PEL giảm đúng lúc?
51. Một integration test nào chứng minh XACK không tự xóa raw stream record?
52. Một integration test nào chứng minh pending record của worker chết có thể được claim?
53. Một integration test nào chứng minh giữ eventId ổn định bảo vệ business khỏi duplicate?
54. Những rủi ro gì khi create group tại '$' trong lúc stream đã chứa dữ liệu?
55. Cần kiểm tra những gì khi XPENDING tăng nhưng business DONE vẫn tăng?
56. Một stream có hai groups Fulfillment và Analytics cần retention/ACL khác nhau thế nào?
57. Khi nào phải coi Redis Stream là transport trung gian chứ không phải source of truth?
58. Nếu một record bị trim trước khi PEL recovery, lấy payload gốc từ đâu?
59. Vì sao không thể chỉ dựa vào Redis group offset để khẳng định exactly-once side effects?
60. Thiết kế một flow Redis Stream inbound tối thiểu có manual ACK, durable business state và pending recovery.

## 31. Tài liệu tham khảo và phạm vi phiên bản

Các nguồn chính thức nên đối chiếu trước khi đưa code vào dự án:

- [Spring Integration – Redis Support, Redis Stream Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/redis.html): Java DSL, ReactiveRedisStreamMessageProducer, autoAck, consumer group, stream headers, error channel.
- [Spring Integration – ReactiveRedisStreamMessageProducer Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/redis/inbound/ReactiveRedisStreamMessageProducer.html): Constructor, ReadOffset, ACK configuration, StreamReceiverOptions và setters theo phiên bản.
- [Spring Integration – RedisStreamInboundChannelAdapterSpec Javadoc](https://www.springframework.org/spring-integration/docs/7.1.x-SNAPSHOT/api/org/springframework/integration/redis/dsl/RedisStreamInboundChannelAdapterSpec.html): Java DSL methods như consumerGroup, consumerName, autoAck và createConsumerGroup.
- [Spring Data Redis – Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): XREAD/XREADGROUP, StreamReceiver, ReadOffset, XACK, PEL và backpressure considerations.
- [Redis – Streams data type](https://redis.io/docs/latest/develop/data-types/streams/): XADD, consumer groups, delivery semantics và retention.
- [Redis – XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/): Reclaim pending entries, min idle, cursor và version-dependent results.

**Giới hạn version cần lưu ý:** Spring Integration giới thiệu Reactive Redis Stream inbound từ **5.4**; từ **5.5** có thêm các cấu hình receiver options/direct setters như pollTimeout, batchSize và error resume. Redis server/client cũng có khác biệt theo version về các lệnh như XAUTOCLAIM và trimming/reference options. Khi implement thực tế, chọn **BOM đồng bộ**, đối chiếu API theo phiên bản đang dùng và **chạy integration tests với Redis thật**. Bài học không thay thế build/test/QA học thuật chuyên sâu tại bước tiếp theo.

## Tổng kết

**Redis stream inbound adapter** đưa các **Redis Stream records** qua **Spring Data Redis Reactive StreamReceiver** vào **Spring Integration MessageChannel**. Adapter đọc bằng **XREAD** hoặc **XREADGROUP** tùy cấu hình; với consumer group, Redis quản lý **Pending Entries List (PEL)** và cho phép **XACK** theo từng record. Đây là khác biệt cốt lõi với Redis Pub/Sub notifications, Redis List destructive POP và RedisStoreMessageSource collection views.

**Manual ACK** là lựa chọn quan trọng khi xử lý nghiệp vụ cần độ tin cậy cao. Trong Spring Integration, **autoAck(false)** đưa **ACKNOWLEDGMENT_CALLBACK** vào Spring MessageHeaders; handler phải **validate → commit business state bền vững → ACK**. Nếu crash trước commit, record có thể còn pending; nếu crash sau commit trước XACK, record có thể được xử lý lại. Vì thế cần **eventId ổn định, unique constraint/idempotency, pending reclaimer và error/dead-letter policy** — không chỉ bật consumer group.

Tốc độ nhận và độ bền không chỉ được quyết định bởi batchSize hoặc số consumers. Cần thiết kế **group creation offset, ReadOffset, retention/XTRIM, StreamReceiver backpressure, graceful shutdown, Redis persistence/failover, ACL, schema compatibility, tracing và monitoring PEL/lag/business outcomes**. XACK không tương đương XDEL, group last-delivered ID không tương đương business commit, và Stream ID không thay eventId.

Khi tích hợp Redis Streams với File/SFTP, HTTP, JMS, AMQP, Kafka hoặc database trong module **SPRING_INTEGRATION_ADAPTERS**, luôn phân biệt rõ **đã ghi vào stream**, **đã được group giao**, **đã commit nghiệp vụ** và **đã ACK/cleanup**. Một hệ thống tin cậy cần chính sách phục hồi cho mọi khoảng crash, một nguồn trạng thái bền vững và kiểm thử cả happy path lẫn duplicate/replay/trim/failover. Chọn Redis Stream inbound khi cần **record history, consumer-group delivery và recovery có kiểm soát**, chứ không chỉ vì tên adapter chứa từ “stream”.
