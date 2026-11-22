# Xử lý công việc bằng Streams và consumer group trong Spring Data Redis

Redis Streams là một cấu trúc dữ liệu cho phép lưu các sự kiện theo thứ tự ID, đọc theo vị trí và theo dõi các bản ghi đã được giao nhưng chưa xử lý xong. Kết hợp **consumer group**, Streams phù hợp cho các công việc bất đồng bộ như gửi email xác nhận đơn hàng, cập nhật chỉ mục, đồng bộ tồn kho, gửi webhook hoặc chạy tác vụ hậu xử lý.

Trong Spring Data Redis, chúng ta thường dùng **`StringRedisTemplate` / `RedisTemplate`**, `StreamOperations`, `StreamRecords`, `Consumer`, `StreamReadOptions` và `StreamOffset` để xây dựng producer và consumer. Nhưng một chương trình chỉ biết gọi `XADD` rồi `XREADGROUP` **chưa phải hàng đợi công việc tin cậy**. Cần thiết kế cả xác nhận hoàn thành (`XACK`), Pending Entries List (PEL), xử lý lại sau lỗi, idempotency, retention, concurrency và quan sát.

Bài thực hành tập trung vào workflow:

~~~text
POST /orders
      |
      v
OrderService -> lưu đơn hàng -> phát OrderCreated
                                    |
                                    v
                             Redis Stream
                             orders.events
                                    |
                             Group order-workers
                                    |
                     +--------------+--------------+
                     |              |              |
                  worker-A       worker-B       worker-C
                     |              |              |
                  handler        handler        handler
                     |              |              |
                  commit         commit         commit
                     |              |              |
                    XACK           XACK           XACK
~~~

**Điểm mấu chốt:** Consumer group giúp phân phối và theo dõi message, nhưng **không tự đảm bảo exactly-once business processing**. Một message có thể được giao lại; handler phải an toàn trước duplicate.

## 1. Mục tiêu và kiến thức cần có

Sau bài thực hành, bạn có thể:

1. Khởi tạo stream và consumer group đúng offset.
2. Ghi message bằng Redis CLI và Spring Data Redis.
3. Nhận message mới bằng `XREADGROUP` và `ReadOffset.lastConsumed()`.
4. Chỉ `XACK` sau khi side effect nghiệp vụ đã thành công.
5. Dùng `XPENDING` để biết message nào đang được giao nhưng chưa xác nhận.
6. Dùng `XAUTOCLAIM` hoặc `XCLAIM` để khôi phục công việc của consumer chết.
7. Thiết kế idempotent handler dựa trên business event ID.
8. Phân loại retryable error, poison message và dead-letter queue (DLQ).
9. Định nghĩa retention để tránh mất message chưa xử lý.
10. Kiểm thử worker crash, xử lý trùng, restart, timeout và load.
11. Biết giới hạn của Streams khi kết hợp database transaction, Redis persistence và Cluster.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Data Redis, Redis Server thật và Redis CLI. Redis 6.2 trở lên được dùng cho `XAUTOCLAIM`; các command Streams/consumer group cơ bản có từ Redis 5. Nếu stack của dự án dùng phiên bản khác, cần đối chiếu API và khả năng command tương ứng.

## 2. Vì sao không dùng HTTP đồng bộ cho mọi tác vụ?

Giả sử một request đặt hàng cần:

~~~text
1. Lưu đơn hàng
2. Gửi email
3. Gửi webhook
4. Cập nhật dashboard
5. Trả HTTP response
~~~

Nếu email hoặc webhook chậm 10 giây, user có thể tưởng thao tác đặt hàng bị lỗi dù database đã lưu đơn.

Tách thành công việc bất đồng bộ:

~~~text
HTTP
   -> DB commit
   -> publish event
   -> trả orderId và trạng thái tiếp nhận

Worker
   -> đọc event
   -> thực hiện side effect
   -> ACK
~~~

Lợi ích:

- Giảm thời gian request phải chờ các bước không cần đồng bộ.
- Tách scaling của API và worker.
- Có backlog khi worker chậm, miễn stream/Redis còn giữ dữ liệu.
- Quan sát pending và khôi phục sau crash.
- Có thể tổ chức nhiều consumer groups phục vụ mục đích khác nhau.

Rủi ro mới:

- Công việc không hoàn tất ngay khi HTTP thành công.
- Event có thể được xử lý lại.
- Producer có thể ghi DB thành công nhưng publish thất bại.
- Worker có thể commit DB nhưng crash trước ACK.
- Streams có thể tăng RAM nếu không có retention.
- Redis persistence/failover vẫn có rủi ro mất dữ liệu đã nhận.
- Nhiều consumers không đảm bảo side effect hoàn tất theo thứ tự append.

Do đó cần một workflow chứ không chỉ một queue API.

## 3. Stream, entry, Record ID và consumer group

Một Stream lưu các entry dưới một Redis key:

~~~text
Redis key: orders.events

1700000000100-0
  eventId=evt-101
  orderId=order-101
  eventType=ORDER_CREATED
  schemaVersion=1

1700000000101-0
  eventId=evt-102
  orderId=order-102
  eventType=ORDER_CREATED
  schemaVersion=1
~~~

Một entry có ID dạng `milliseconds-sequence`. Với `XADD ... *`, Redis tự sinh ID. ID biểu diễn vị trí entry trong stream; nó **không thay thế** business event ID được producer sử dụng để dedupe.

Consumer group quản lý vị trí đọc và những message chưa được ACK:

~~~text
                         orders.events
                              |
            +-----------------+-----------------+
            |                                   |
        group A:                           group B:
       order-workers                    analytics-workers
            |                                   |
      +-----+-----+                             |
      |           |                         analytics-1
   worker-A    worker-B
~~~

Hai consumer trong **cùng group** chia các entries mới. Hai **groups khác nhau** có vị trí đọc riêng và có thể cùng xử lý một entry theo mục đích khác nhau.

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Stream key | `orders.events` | Chứa entries |
| Group | `order-workers` | Nhóm cùng chia công việc và quản lý PEL |
| Consumer | `worker-A` | Worker identity trong group |
| Record ID | `1700000000100-0` | Định danh entry trong stream |
| Business event ID | `evt-101` | Nhận diện thao tác nghiệp vụ khi retry/dedupe |
| PEL | Pending Entries List | Trạng thái entries đã giao, chưa ACK |

**XACK không xóa entry khỏi Stream**. Nó chỉ xóa trạng thái pending của entry đối với group được chỉ định.

## 4. Chuẩn bị Redis và ứng dụng

Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Để chạy một Redis test server riêng, có thể dùng Docker:

~~~bash
docker run --rm --name redis-streams-lab -p 6379:6379 redis:7.2.5-alpine
~~~

Tag Redis trong ví dụ chỉ để minh họa phiên bản cụ thể. Trên dự án thật, chọn Redis version/distribution tương ứng production và kiểm tra image đang sử dụng. Không dùng cổng công khai/Redis production cho các thao tác thử nghiệm xóa dữ liệu.

Kiểm tra:

~~~bash
redis-cli PING
~~~

Kết quả mong đợi:

~~~text
PONG
~~~

Cấu hình Spring Boot 3.x:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 5s

app:
  orders:
    stream-key: orders.events
    group: order-workers
    poll-delay-ms: 250
~~~

Lệnh `XREADGROUP BLOCK` có thể đợi vài giây khi stream rỗng; command timeout phải đủ phù hợp với thời gian BLOCK và network. Nếu production dùng Sentinel/Cluster/TLS/ACL, không chỉ sao chép ví dụ standalone.

## 5. Thực hành bằng Redis CLI trước khi code Java

### 5.1. Tạo consumer group

~~~bash
redis-cli XGROUP CREATE orders.events order-workers 0-0 MKSTREAM
~~~

Các thành phần:

- `orders.events`: tên Stream.
- `order-workers`: tên consumer group.
- `0-0`: group có thể đọc các entries đã tồn tại từ đầu stream, theo cách đọc message mới.
- `MKSTREAM`: tạo stream rỗng nếu chưa tồn tại.

Lệnh thành công trả `OK`. Nếu group đã có, Redis có thể trả lỗi `BUSYGROUP`. Trong quá trình bootstrap tự động, chỉ xử lý `BUSYGROUP` như trường hợp “group đã tồn tại”, không bỏ qua tất cả exceptions.

### 5.2. Phân biệt group offset `0-0` và `$`

~~~bash
redis-cli XGROUP CREATE other.events other-group '$' MKSTREAM
~~~

Khi tạo group từ `$`, group bắt đầu tại vị trí cuối hiện tại, nên các entries cũ không được giao như message mới bằng `>`. Dùng `0-0` khi nhóm phải xử lý lịch sử đã có.

Nếu group đã tồn tại, gọi lại `XGROUP CREATE` không tự cập nhật offset. Không destroy group đang chứa pending chỉ để đổi vị trí đọc.

### 5.3. Publish message

~~~bash
redis-cli XADD orders.events '*' eventId evt-001 orderId order-101 eventType ORDER_CREATED schemaVersion 1
redis-cli XADD orders.events '*' eventId evt-002 orderId order-102 eventType ORDER_CREATED schemaVersion 1
redis-cli XADD orders.events '*' eventId evt-003 orderId order-103 eventType ORDER_CREATED schemaVersion 1
~~~

`*` để Redis tự tạo Record ID. Có thể xem entries:

~~~bash
redis-cli XRANGE orders.events - + COUNT 10
redis-cli XLEN orders.events
~~~

`XRANGE` dùng để xem dữ liệu. Nó không cập nhật vị trí consumer group, không tạo pending và không thay thế `XREADGROUP` cho worker.

### 5.4. Worker đầu tiên đọc message

~~~bash
redis-cli XREADGROUP GROUP order-workers worker-A COUNT 2 STREAMS orders.events '>'
~~~

Redis giao tối đa hai entries mới cho consumer `worker-A`. Dấu `>` yêu cầu entries chưa từng được giao mới cho group.

Kiểm tra pending:

~~~bash
redis-cli XPENDING orders.events order-workers
redis-cli XPENDING orders.events order-workers - + 10
~~~

### 5.5. ACK một entry

Dùng Record ID thật từ output đọc ở trên, ví dụ minh họa:

~~~bash
redis-cli XACK orders.events order-workers 1700000000100-0
~~~

Kết quả thường là `1` nếu entry đang pending trong group và được ACK, hoặc `0` nếu không có pending entry tương ứng.

Kiểm tra:

~~~bash
redis-cli XPENDING orders.events order-workers
redis-cli XRANGE orders.events - +
~~~

Sau ACK, entry vẫn có thể xuất hiện trong `XRANGE`; nó không còn nằm trong PEL của group nữa.

## 6. Phân phối message giữa các consumers

Thử mở hai terminal:

~~~bash
redis-cli XREADGROUP GROUP order-workers worker-A COUNT 1 BLOCK 2000 STREAMS orders.events '>'
~~~

~~~bash
redis-cli XREADGROUP GROUP order-workers worker-B COUNT 1 BLOCK 2000 STREAMS orders.events '>'
~~~

Redis sẽ cấp entries mới cho những consumer đang thực hiện lệnh đọc. **Không có bảo đảm chia đều 50/50 hoặc round-robin theo từng entry**. Worker đọc liên tục/nhanh hơn có thể nhận nhiều entries hơn.

Khi tạo một group `analytics-workers` riêng cho cùng stream, nhóm đó có thể đọc event với trạng thái độc lập. Vì vậy:

- Cùng group: work sharing.
- Khác group: independent processing.
- Pub/Sub: broadcast cho subscribers online, nhưng không có PEL/ACK.
- Streams: entries được giữ cho tới khi trim/xóa hoặc dữ liệu Redis mất.

## 7. Thiết kế payload phục vụ xử lý thực tế

Event payload mẫu:

~~~text
eventId       = evt-001
eventType     = ORDER_CREATED
schemaVersion = 1
orderId       = order-101
createdAt     = 2026-11-13T10:15:30Z
~~~

Nên có:

- **eventId** do producer tạo ổn định trong tất cả lần retry của cùng sự kiện.
- **eventType** để dispatch handler.
- **schemaVersion** để hỗ trợ rolling upgrade.
- **aggregateId** như `orderId` khi cần phân biệt nghiệp vụ.
- **createdAt** để tính business processing latency.
- **trace/correlation ID** nếu cần, nhưng không dùng IDs có cardinality cao làm metric labels.

Không nhất thiết nhồi toàn bộ order JSON vào Stream. Với payload rất lớn hoặc dữ liệu nhạy cảm, có thể chỉ lưu ID và worker đọc dữ liệu từ source of truth.

Cần xác định handling cho eventType/schemaVersion không hỗ trợ: phân loại lỗi, giữ lại để điều tra hoặc DLQ, không ACK rồi bỏ qua im lặng.

## 8. Producer Spring Data Redis: ghi message bằng `XADD`

Ví dụ một producer:

~~~java
package com.example.orders.stream;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {

    public static final String STREAM = "orders.events";

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public RecordId publish(
            String eventId,
            String orderId
    ) {
        Map<String, String> payload = new LinkedHashMap<>();
        payload.put("eventId", eventId);
        payload.put("eventType", "ORDER_CREATED");
        payload.put("schemaVersion", "1");
        payload.put("orderId", orderId);
        payload.put("createdAt", Instant.now().toString());

        var record = StreamRecords.mapBacked(payload)
            .withStreamKey(STREAM);

        RecordId id = redis.opsForStream().add(record);

        if (id == null) {
            throw new IllegalStateException(
                "Redis did not return RecordId"
            );
        }
        return id;
    }
}
~~~

`StringRedisTemplate` cho phép làm việc với String values/fields. Nếu dùng template có serializer khác, hãy xác nhận raw key/hash field/value bytes bằng integration test trên Redis thật.

### 8.1. Record ID khác business event ID

Một producer gọi:

~~~text
XADD eventId=evt-001 -> Redis appended, response lost
Retry XADD eventId=evt-001 -> Redis appended again
~~~

Redis có thể tạo **hai Record IDs khác nhau** cho cùng `eventId`. Do đó producer không nên tạo business event ID mới mỗi khi retry, và consumer cần dedupe theo stable ID này.

### 8.2. Publish thành công chưa phải xử lý thành công

`XADD` trả Record ID chỉ xác nhận Redis đã nhận/append entry theo trạng thái command. Nó không chứng minh:

- Worker đã đọc.
- Handler hoàn tất.
- Email/webhook đã gửi.
- Business DB đã commit.
- Message đã được `XACK`.
- Dữ liệu được fsync/replicate bền vững qua mọi crash.

Nếu API cần báo kết quả công việc, nên có trạng thái riêng như `QUEUED`, `PROCESSING`, `SUCCEEDED`, `FAILED` thay vì trả “đã hoàn tất” ngay sau `XADD`.

## 9. Lỗ hổng dual-write: DB commit rồi publish

Nếu code làm:

~~~text
BEGIN DATABASE TRANSACTION
  INSERT order
COMMIT
XADD orders.events
~~~

thì service có thể crash sau `COMMIT` nhưng trước `XADD`. Đơn hàng tồn tại mà event không được publish.

Đảo thứ tự cũng không đảm bảo đúng:

~~~text
XADD
BEGIN DATABASE TRANSACTION
  INSERT order
ROLLBACK
~~~

Event tồn tại nhưng order chưa có.

`@Transactional` của Spring JPA **không tự bao gồm Redis Stream trong cùng distributed transaction**.

### 9.1. Transactional outbox

Với công việc quan trọng, cân nhắc:

~~~text
BEGIN DB TRANSACTION
  INSERT orders
  INSERT outbox_events(eventId, payload, status)
COMMIT
     |
     v
Outbox publisher
  -> đọc event chưa phát
  -> XADD với stable eventId
  -> đánh dấu đã phát
     |
     v
Redis Stream consumer group
~~~

Outbox publisher có thể crash sau `XADD` nhưng trước khi cập nhật outbox status, làm message được publish lại. Vì vậy **outbox và consumer idempotency phải đi cùng nhau**.

Redis Streams dùng để vận chuyển work, còn database/outbox giúp bảo vệ sự kiện được phát sinh cùng thay đổi nghiệp vụ khi cần.

## 10. Consumer group đọc entries mới bằng `XREADGROUP`

CLI:

~~~bash
redis-cli XREADGROUP GROUP order-workers worker-A COUNT 10 BLOCK 2000 STREAMS orders.events '>'
~~~

Các tham số:

| Tham số | Ý nghĩa |
|---|---|
| `GROUP order-workers worker-A` | Group và consumer identity |
| `COUNT 10` | Giới hạn số entries mong muốn trả mỗi lượt |
| `BLOCK 2000` | Có thể chờ khoảng 2 giây khi chưa có entries mới |
| `STREAMS orders.events` | Stream key cần đọc |
| `>` | Giao entries chưa từng được group giao mới |

Với Spring Data Redis:

~~~java
List<MapRecord<String, Object, Object>> records =
    redis.opsForStream().read(
        Consumer.from("order-workers", consumerName),
        StreamReadOptions.empty()
            .count(10)
            .block(Duration.ofSeconds(2)),
        StreamOffset.create(
            "orders.events",
            ReadOffset.lastConsumed()
        )
    );
~~~

`ReadOffset.lastConsumed()` dùng trong group read biểu diễn việc đọc entries mới theo group position. Không dùng nó để tự lấy pending của consumer đã chết.

Khi không có message, API có thể trả `null` hoặc collection rỗng tùy đường gọi; hãy xử lý cả hai.

## 11. Consumer Java với xử lý rồi mới ACK

Trước tiên tách business handler:

~~~java
package com.example.orders.stream;

public interface OrderEventHandler {
    // Bắt buộc idempotent theo stable eventId.
    void applyOnce(
        String eventId,
        String eventType,
        String orderId
    );
}
~~~

Một worker polling đơn giản:

~~~java
package com.example.orders.stream;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OrderStreamWorker {

    private static final Logger log =
        LoggerFactory.getLogger(OrderStreamWorker.class);

    private static final String STREAM = "orders.events";
    private static final String GROUP = "order-workers";

    private final StringRedisTemplate redis;
    private final OrderEventHandler handler;

    private final String consumerName =
        "worker-" + UUID.randomUUID();

    public OrderStreamWorker(
            StringRedisTemplate redis,
            OrderEventHandler handler
    ) {
        this.redis = redis;
        this.handler = handler;
    }

    @Scheduled(fixedDelay = 250)
    public void readOnce() {
        List<MapRecord<String, Object, Object>> records;

        try {
            records = redis.opsForStream().read(
                Consumer.from(GROUP, consumerName),
                StreamReadOptions.empty()
                    .count(10)
                    .block(Duration.ofSeconds(2)),
                StreamOffset.create(
                    STREAM,
                    ReadOffset.lastConsumed()
                )
            );
        } catch (RuntimeException ex) {
            log.error("Cannot read Redis Stream", ex);
            return;
        }

        if (records == null || records.isEmpty()) {
            return;
        }

        for (var record : records) {
            handleAndAck(record);
        }
    }

    private void handleAndAck(
            MapRecord<String, Object, Object> record
    ) {
        try {
            Map<Object, Object> fields = record.getValue();
            String eventId = required(fields, "eventId");
            String eventType = required(fields, "eventType");
            String orderId = required(fields, "orderId");

            // Thành công khi side effect đã commit.
            handler.applyOnce(eventId, eventType, orderId);

            Long acked = redis.opsForStream()
                .acknowledge(STREAM, GROUP, record.getId());

            log.debug(
                "record={} eventId={} acked={}",
                record.getId(), eventId, acked
            );
        } catch (RuntimeException ex) {
            // Không ACK khi handler thất bại.
            log.error(
                "Processing failed for record={}",
                record.getId(), ex
            );
        }
    }

    private static String required(
            Map<Object, Object> fields,
            String name
    ) {
        Object value = fields.get(name);
        if (!(value instanceof String text)
                || text.isBlank()) {
            throw new IllegalArgumentException(
                "Invalid field: " + name
            );
        }
        return text;
    }
}
~~~

Bật scheduling:

~~~java
@SpringBootApplication
@EnableScheduling
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Những điểm quan trọng của ví dụ:

- Consumer identity riêng cho một process.
- `ReadOffset.lastConsumed()` đọc entries mới.
- Mỗi record được xử lý rồi ACK riêng.
- Handler lỗi thì record giữ pending.
- ACK timeout không có nghĩa side effect chưa chạy.
- Đây là **bản tối thiểu**, chưa có reclaim, DLQ và shutdown hoàn chỉnh.
- Một task `@Scheduled` gọi `BLOCK 2s` có thể chiếm scheduler thread; cần executor/scheduler tách riêng nếu còn nhiều scheduled jobs.

## 12. Tạo group trước khi worker chạy

Worker ví dụ yêu cầu group tồn tại. Trên lab:

~~~bash
redis-cli XGROUP CREATE orders.events order-workers 0-0 MKSTREAM
~~~

Một phương án dùng Spring API khi stream đã tồn tại:

~~~java
redis.opsForStream().createGroup(
    "orders.events",
    ReadOffset.from("0-0"),
    "order-workers"
);
~~~

Với API không tự `MKSTREAM`, việc tạo group trên stream chưa tồn tại sẽ lỗi. Có thể bootstrap group trong migration/deployment, hoặc dùng lệnh `XGROUP CREATE ... MKSTREAM` qua Redis command interface.

Nếu nhiều pods khởi động cùng lúc, một pod có thể tạo group thành công, pod khác nhận `BUSYGROUP`. Hãy chỉ xử lý **đúng lỗi group đã tồn tại**; không bắt mọi exception rồi bỏ qua vì có thể che `NOAUTH`, sai endpoint hoặc network outage.

Đừng dùng `XGROUP DESTROY` như bước khởi tạo thông thường; nó xóa trạng thái group/PEL đang quan trọng.

## 13. Tại sao phải ACK sau khi business commit?

Hai trình tự:

**Trình tự nguy hiểm**

~~~text
XREADGROUP
   |
   v
XACK
   |
   v
Call external API
   |
   X worker dies
~~~

Message không còn pending; việc gửi công việc có thể bị mất.

**Trình tự phù hợp cho khả năng xử lý lại**

~~~text
XREADGROUP
   |
   v
Validate payload
   |
   v
Run idempotent handler
   |
   v
Commit durable business outcome
   |
   v
XACK
~~~

Nếu worker chết **sau commit nhưng trước ACK**, message vẫn pending và có thể xử lý lại. Đó là lý do handler phải idempotent.

`XACK` chỉ tác động PEL của group; entry đã ACK vẫn còn trong stream cho tới khi được trim/xóa.

## 14. Pending Entries List (PEL)

Khi `XREADGROUP` giao message cho consumer, Redis ghi metadata của entry vào PEL cho group.

~~~text
stream entry
     |
     v
XREADGROUP -> consumer-A
     |
     v
Pending Entries List:
   record ID
   consumer owner
   idle time
   delivery count
     |
     +-- XACK -> remove pending entry
     |
     +-- error / crash -> remains pending
~~~

Quan sát:

~~~bash
redis-cli XPENDING orders.events order-workers
redis-cli XPENDING orders.events order-workers - + 10
redis-cli XINFO GROUPS orders.events
redis-cli XINFO CONSUMERS orders.events order-workers
~~~

`XPENDING` có summary và dạng mở rộng, thường hiển thị ID, owner, idle duration, delivery count.

**PEL lưu metadata giao nhận, không phải một bản sao payload độc lập.** Nếu stream entry bị trim/xóa, metadata pending có thể còn nhưng dữ liệu để xử lý lại không còn.

### 14.1. Những gì pending count không nói

- Không bao gồm entries chưa từng được group giao.
- Không chứng minh handler đã bắt đầu xử lý.
- Không chứng minh business effect chưa hoàn tất nếu worker đã commit nhưng mất ACK.
- Không phản ánh trực tiếp mức độ vi phạm SLA nếu thiếu tuổi công việc.
- Không thay thế end-to-end business completion metric.

Một message pending 30 phút có thể nghiêm trọng hơn 100 pending mới được giao 1 giây trước đó.

## 15. Message pending không tự trở thành entry mới

Một lỗi hiểu thường gặp:

~~~text
worker-A receives evt-001
worker-A crashes without ACK
worker-B polls with '>'
~~~

Worker-B sẽ **không tự nhận evt-001** qua dấu `>`, vì message đã được group giao. Nó vẫn pending dưới owner worker-A.

Muốn khôi phục:

- Consumer cũ đọc lại **pending của chính consumer name**.
- Hoặc một consumer khác **claim** những entries idle đủ lâu bằng `XCLAIM` hoặc `XAUTOCLAIM`.

Do vậy, nếu chỉ chạy luồng đọc entries mới và ACK, hệ thống **có thể để pending tồn tại mãi** khi một worker chết.

## 16. Đọc lại pending của chính consumer

CLI:

~~~bash
redis-cli XREADGROUP GROUP order-workers worker-A COUNT 10 STREAMS orders.events 0
~~~

Khi ID không phải `>`, group read dùng lịch sử pending của **consumer được chỉ định**, không tự lấy pending của mọi consumer khác.

Spring API:

~~~java
var pending = redis.opsForStream().read(
    Consumer.from("order-workers", "worker-A"),
    StreamReadOptions.empty().count(10),
    StreamOffset.create(
        "orders.events",
        ReadOffset.from("0-0")
    )
);
~~~

Lưu ý:

- Dùng đúng consumer name mà pending đang thuộc về.
- Đọc lại có thể làm thay đổi idle/delivery metadata.
- Nếu cứ đọc từ `0-0` và không ACK, có thể nhận đi nhận lại cùng entries.
- Cần retry delay và giới hạn attempts.
- Không dùng cách này để kỳ vọng tự cứu pending của một worker name đã biến mất.

Khi scale hoặc mỗi restart đổi tên worker, nên có một recovery task dùng claim.

## 17. Khôi phục bằng `XAUTOCLAIM`

Redis 6.2+ hỗ trợ:

~~~bash
redis-cli XAUTOCLAIM orders.events order-workers worker-B 60000 0-0 COUNT 10
~~~

Ý nghĩa:

| Thành phần | Mục đích |
|---|---|
| `orders.events` | Stream |
| `order-workers` | Group |
| `worker-B` | Consumer nhận ownership |
| `60000` | Chỉ claim entries có idle ít nhất 60.000 ms |
| `0-0` | Cursor bắt đầu quét PEL |
| `COUNT 10` | Giới hạn số entries muốn trả trong một lần |

Kết quả có cursor mới và những entries claim được. Tùy Redis version, phản hồi còn có thông tin các IDs không còn payload nhưng còn metadata pending. Recovery loop phải dùng cursor và xử lý kết quả đúng phiên bản.

### 17.1. Không claim quá sớm

Giả sử một handler đang gọi API chậm mất 90 giây. Nếu recovery claim sau 5 giây:

~~~text
worker-A still processing
     |
     +-- after 5 seconds
              |
              v
worker-B claims same message
              |
              v
both may run business side effect
~~~

Thay đổi owner trong PEL không ép worker-A dừng công việc đang thực thi. Do đó:

- Chọn idle threshold dựa trên handler duration và SLA.
- Duy trì idempotency ngay cả khi threshold hợp lý.
- Với tác vụ rất dài, cần cơ chế ownership/heartbeat hoặc thiết kế work lease ngoài PEL khi phù hợp.
- Không coi `XAUTOCLAIM` là distributed lock chống chạy song song.

### 17.2. Recovery loop nên hoạt động độc lập

Một lịch xử lý có thể là:

~~~text
Every 30 seconds:
  scan pending with XAUTOCLAIM
  claim entries idle beyond threshold
  process with same idempotent handler
  XACK after successful commit
  advance scan cursor
  record metrics
~~~

Giới hạn số entries mỗi vòng, concurrency, tốc độ retry và logging. Không quét toàn bộ PEL liên tục ở peak traffic.

### 17.3. `XCLAIM` dùng khi đã biết ID

`XCLAIM` nhận danh sách cụ thể IDs và điều kiện idle; phù hợp khi có công cụ vận hành chọn một số pending. `XAUTOCLAIM` thuận tiện hơn cho background recovery tự tìm entries.

Cả hai đều có thể làm một entry được giao lại; không thay thế durable dedupe.

## 18. Tránh xử lý trùng bằng idempotent handler

Hai kịch bản phổ biến:

**Producer retry**

~~~text
XADD eventId=evt-001 -> appended
response lost
retry XADD eventId=evt-001 -> another RecordId
~~~

**Consumer crash**

~~~text
XREADGROUP evt-001
business transaction COMMIT
worker crashes before XACK
another worker reclaims evt-001
~~~

Cả hai khiến cùng business event được nhìn thấy nhiều lần.

Giải pháp là **stable business event ID và durable idempotency record**.

### 18.1. Ví dụ schema database

~~~sql
CREATE TABLE processed_stream_events (
    consumer_group VARCHAR(128) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_group, event_id)
);
~~~

Trong **cùng một DB transaction**:

~~~text
BEGIN
  INSERT processed_stream_events(group, eventId)
  if insert says "already exists":
      return no-op
  else:
      perform business DB side effect
COMMIT
~~~

Unique constraint ngăn hai transaction đánh dấu xử lý lần đầu cho cùng group+eventId.

### 18.2. Pseudocode Spring service

~~~java
@Service
public class OrderHandler implements OrderEventHandler {

    private final ProcessedEventRepository processed;
    private final OrderRepository orders;

    @Transactional
    @Override
    public void applyOnce(
        String eventId,
        String eventType,
        String orderId
    ) {
        if (!processed.tryInsert(
                "order-workers", eventId)) {
            return;
        }

        if (!"ORDER_CREATED".equals(eventType)) {
            throw new IllegalArgumentException(
                "Unsupported eventType"
            );
        }

        orders.markConfirmationPending(orderId);
    }
}
~~~

`ProcessedEventRepository.tryInsert` là abstraction cần triển khai bằng thao tác database atomic, ví dụ `INSERT ... ON CONFLICT DO NOTHING` và kiểm tra row count.

**Quan trọng:** insert idempotency marker và business update phải cùng transaction. Nếu marker commit trước rồi business operation thất bại, message có thể bị coi đã xử lý trong khi side effect chưa xảy ra.

### 18.3. External API không rollback cùng DB

Nếu handler gửi email rồi crash trước khi ghi marker, email có thể gửi hai lần khi retry.

Cân nhắc:

- API downstream hỗ trợ idempotency key.
- Outbox/command table cho yêu cầu gửi email.
- Trạng thái gửi và reconciliation với provider.
- Business-specific dedupe/replay logic.
- Không khẳng định exactly-once nếu không có cơ chế tương ứng ở external side effect.

## 19. Xử lý lỗi và chính sách retry

Không phải mọi lỗi đều cần retry:

| Loại | Ví dụ | Hướng xử lý |
|---|---|---|
| Transient | DB timeout, HTTP 503 | Backoff + jitter + giới hạn |
| Permanent payload | Thiếu `eventId`, unsupported version | DLQ/quarantine |
| Duplicate hợp lệ | Event ID đã commit | No-op và ACK |
| Redis unavailable | Command read/ACK timeout | Reconnect, unknown outcome |
| Wrong configuration | `NOGROUP`, ACL denial | Khắc phục cấu hình, alert |
| Unknown external result | Email API timeout sau khi gửi | Reconcile/dedupe, không lặp mù |
| Business validation | Order not found | Tùy contract: retry có giới hạn hoặc quarantine |

Nếu handler throw và không ACK, entry sẽ còn pending. Nhưng **chỉ để pending mà không có recovery job không phải một retry policy hoàn chỉnh**.

### 19.1. Tránh poison-message hot loop

Một entry thiếu required field luôn làm handler lỗi. Nếu worker đọc lại ngay lập tức, nó có thể tạo:

~~~text
read -> fail -> read -> fail -> read -> fail -> ...
~~~

Hậu quả là CPU/log/DB load tăng. Cần:

- Exponential backoff với jitter.
- Retry count và độ trễ tối đa.
- Phân loại lỗi fatal vs transient.
- Dead-letter queue sau số lần thử phù hợp.
- Metrics về age/retry và alert.
- Không chặn mãi các entries tốt vì một poison message.

## 20. Thiết kế dead-letter queue

Stream dành cho những message không thể xử lý tự động:

~~~text
orders.events.dlq
~~~

Payload có thể gồm:

~~~text
originalStream     orders.events
originalRecordId   1700000000100-0
eventId            evt-001
eventType          ORDER_CREATED
failureCategory    INVALID_SCHEMA
attemptCount       5
failedAt           2026-11-13T10:30:00Z
~~~

Không đưa password/token hoặc raw stack trace nhạy cảm vào Redis message. DLQ phải có owner và retention rõ.

### 20.1. Thứ tự chuyển DLQ và ACK

Trình tự nguy hiểm:

~~~text
XACK original
XADD DLQ
crash between steps -> message disappears from pending
~~~

Một trình tự có thể khôi phục hơn:

~~~text
XADD DLQ
XACK original
~~~

Nếu crash sau `XADD DLQ` trước `XACK`, message có thể được chuyển DLQ lần nữa khi retry. Vì vậy DLQ và recovery cần dedupe theo `eventId`/`originalRecordId`.

Với Redis Cluster, không thể mặc định dùng multi-key Lua/transaction nguyên tử giữa original stream và DLQ nếu hai keys khác hash slot. Nếu cần Redis-side atomicity, phải kiểm tra same-slot, Redis version và client behavior; đồng thời nhớ Redis atomicity không bao trùm external DB.

### 20.2. Vận hành DLQ

- Theo dõi DLQ length và oldest age.
- Định nghĩa ai điều tra.
- Có công cụ replay giữ stable event ID.
- Có audit log cho manual retry.
- Không replay quá nhanh gây overload.
- Không xóa DLQ chỉ vì đã tạo alert.
- Đặt retention đủ dài cho thời gian xử lý sự cố.

## 21. Retention: tránh stream tăng vô hạn và tránh mất công việc

`XACK` không xóa entries. Nếu producer ghi liên tục, stream tăng không giới hạn nếu không có retention.

Một ví dụ:

~~~bash
redis-cli XADD orders.events MAXLEN '~' 100000 '*' eventId evt-500 orderId order-500 eventType ORDER_CREATED
~~~

Trong Redis CLI thông thường, cú pháp nguyên thủy:

~~~text
XADD key MAXLEN ~ count * field value ...
~~~

`~` là approximate trimming; có thể để nhiều hơn mức đếm yêu cầu. Lệnh trim riêng:

~~~bash
redis-cli XTRIM orders.events MAXLEN '~' 100000
~~~

### 21.1. Trim sai có thể làm mất payload pending

Giả sử worker-A đã nhận entry nhưng chưa ACK, producer tiếp tục ghi nhanh và trim entries cũ. Lúc recovery, PEL có thể còn metadata trong khi entry gốc đã biến mất, tùy phiên bản/cơ chế trim.

Do đó retention phải xét:

- Tốc độ producer peak.
- Consumer downtime tối đa.
- Tốc độ xử lý thấp nhất khi degraded.
- Retry/backoff/recovery window.
- Nhóm consumer chậm nhất.
- Yêu cầu audit/replay.
- Khả năng storage/memory.
- RPO/RTO của dữ liệu.

Không chọn `MAXLEN 100000` chỉ vì trông gọn. Với producer 10.000 entries/s, 100.000 entries chỉ tương đương khoảng 10 giây dữ liệu ở tốc độ đó, **trước khi xét batch/trim behavior**.

### 21.2. Nhiều groups phải cùng được tính

Nếu `order-workers` ACK nhanh nhưng `analytics-workers` chậm một giờ, việc xóa entries đã ACK của `order-workers` có thể phá luồng analytics. Retention phải bảo vệ tất cả consumer groups cần dữ liệu.

Nếu một group không còn được dùng, hãy có quy trình decommission group có đánh giá pending/lag trước khi xóa group metadata, không tự động xóa group im lặng.

## 22. Thứ tự công việc và nhiều worker

Redis Stream giữ thứ tự entries theo ID nhưng **không bảo đảm thứ tự hoàn tất side effects** khi nhiều workers.

~~~text
entry 100 -> worker-A -> handler mất 5 giây
entry 101 -> worker-B -> handler mất 100 ms

entry 101 có thể commit trước entry 100.
~~~

Nếu các events độc lập, điều đó có thể chấp nhận. Nếu hai events của cùng order phải được áp dụng theo thứ tự, cần thêm:

- Aggregate `orderId` và version/sequence trong payload.
- Version guard trong DB.
- Partition key và phân tuyến công việc.
- Một consumer tuần tự trong phạm vi cần ordering.
- Reconciliation khi phát hiện gap.
- Không tăng concurrency trái với invariant.

Consumer group **không mặc định partition cố định theo orderId**. Cùng một order có thể được các consumers khác nhau đọc trong những lần giao kế tiếp.

### 22.1. Version guard

~~~text
DB order version = 4

Event version 5 -> apply -> DB version 5
Event version 5 -> duplicate -> no-op
Event version 7 -> missing version 6 -> defer/reconcile
~~~

Đây chỉ là mô hình, business logic phải định nghĩa version/consistency theo aggregate thực tế.

## 23. `StreamMessageListenerContainer` thay cho polling thủ công

Spring Data Redis hỗ trợ `StreamMessageListenerContainer` để quản lý polling và callback.

Khung cấu hình minh họa:

~~~java
@Bean
StreamMessageListenerContainer<String,
        MapRecord<String, String, String>> orderStreamContainer(
        RedisConnectionFactory connectionFactory
) {
    var options = StreamMessageListenerContainer
        .StreamMessageListenerContainerOptions
        .<String, MapRecord<String, String, String>>builder()
        .pollTimeout(Duration.ofSeconds(2))
        .build();

    return StreamMessageListenerContainer.create(
        connectionFactory, options
    );
}
~~~

Đăng ký nhận message:

~~~java
container.receive(
    Consumer.from("order-workers", consumerName),
    StreamOffset.create(
        "orders.events",
        ReadOffset.lastConsumed()
    ),
    message -> {
        // Validate -> handle idempotently -> XACK.
    }
);
~~~

Đoạn trên là **khung API**; ứng dụng thực cần import types, quản lý lifecycle/container subscription và kiểm tra generic signatures theo Spring Data Redis version sử dụng.

Listener container giúp polling/dispatch, **không tự bảo đảm**:

- Group đã tồn tại.
- Handler transactional/idempotent.
- ACK sau commit.
- Pending recovery/claim.
- Retry có backoff.
- DLQ.
- Ordering và consumer scaling.
- Durable publish từ DB.

Một số API có cơ chế auto-ack. Không bật auto-ack cho công việc quan trọng nếu nó làm entry được ACK trước khi business side effect thật sự commit.

## 24. Reactive reader và giới hạn concurrency

Với WebFlux, có thể dùng `StreamReceiver` và các reactive operations phù hợp version. Cần vẫn giữ quy tắc:

~~~text
Reactive receive
   -> validate
   -> business side effect
   -> commit
   -> XACK
~~~

Đặc biệt:

- Tránh `.block()` trên Netty event-loop.
- Bounded `flatMap(concurrency)` cho handler độc lập.
- Nếu cần thứ tự, cân nhắc `concatMap` hoặc partition.
- Cancellation có thể xảy ra sau khi Redis đã giao entry.
- Pending recovery vẫn phải có.
- Không tạo vô hạn publishers/commands.
- Client timeout sau ACK có unknown outcome như mô hình sync.

Reactive backpressure không làm mọi thao tác Redis hay side effect trở nên exactly-once.

## 25. Tính số consumer, connection và throughput

Có ba tham số khác nhau:

1. Số consumer processes hoặc subscriptions trong cùng group.
2. Số entries mỗi lượt đọc (`COUNT`).
3. Số handlers chạy đồng thời.

Ví dụ giả định:

~~~text
4 application pods
2 consumers mỗi pod
COUNT 10
mỗi pod tối đa 8 handler tasks đồng thời
~~~

Số consumers và handlers không nhất thiết bằng số Redis TCP connections, đặc biệt với Lettuce shared/dedicated connection semantics.

Nếu handler mất trung bình 200 ms, một worker tuần tự có throughput lý tưởng xấp xỉ:

\[
1 / 0.2 = 5 \text{ events/s}
\]

Với 10 workers độc lập và downstream đủ capacity, mô hình lý tưởng khoảng 50 events/s. Thực tế cần đo Redis read/ACK RTT, DB, API, payload, retry, latency percentile và contention.

### 25.1. Backlog tăng khi producer nhanh hơn consumer

Giả sử:

~~~text
Arrivals = 500 events/s
Completions = 350 events/s
Net growth = 150 events/s
~~~

Sau 10 phút, mức công việc chưa hoàn tất có thể tăng khoảng:

\[
150 \times 600 = 90{,}000
\]

nếu tốc độ giữ nguyên. Đây là cơ sở cảnh báo sớm trước khi vượt business deadline.

### 25.2. Blocking connection budget

`XREADGROUP BLOCK` giữ connection trong lúc chờ. Khi dùng Lettuce, blocking command thường cần dedicated connection theo factory/client implementation; với Jedis, pool demand càng cần được đo.

Cần tính:

~~~text
blocking readers
+ transaction/session connections
+ Pub/Sub subscriptions
+ regular Redis connections
+ Redis Cluster node connections
+ rolling deployment surge
~~~

Tăng số workers không chắc tăng throughput nếu DB/email provider là bottleneck.

## 26. Cần quan sát gì?

Redis CLI:

~~~bash
redis-cli XLEN orders.events
redis-cli XINFO STREAM orders.events
redis-cli XINFO GROUPS orders.events
redis-cli XINFO CONSUMERS orders.events order-workers
redis-cli XPENDING orders.events order-workers
redis-cli XPENDING orders.events order-workers - + 20
redis-cli INFO memory
redis-cli INFO clients
redis-cli INFO commandstats
~~~

| Metric | Ý nghĩa | Giới hạn |
|---|---|---|
| `XLEN` | Tổng entries còn trong stream | Không phải backlog chưa xử lý |
| Group `pending` | Entries đã giao, chưa ACK | Không gồm entries chưa giao |
| Group `lag` | Ước lượng entries chưa giao khi Redis tính được | Không phải số side effects chưa hoàn tất |
| `last-delivered-id` | Vị trí giao mới | Không chứng minh ACK |
| Consumer pending | Pending thuộc consumer | Không khẳng định worker còn sống |
| Pending idle | Thời gian từ lần giao gần đây | Không phải business event age |
| Delivery count | Lịch sử giao nhận theo Redis | Không bằng số external API calls |
| Stream memory | RAM của key theo Redis | Chưa bao hết RSS/COW/cgroup |

### 26.1. Business completion metrics

Nên instrument:

- Event publish success/failure.
- Event receive count.
- Handler success/error/retry.
- Processing duration.
- Độ trễ từ `createdAt` đến **commit side effect**.
- Oldest uncompleted business event.
- Pending recovery/claim count.
- DLQ count và oldest age.
- ACK success/timeout.
- Duplicate event no-op count.
- Consumer reconnects.

Tên metrics có thể như `app_stream_handler_total` và `app_stream_processing_delay_seconds`, nhưng đây là **metric do application tự định nghĩa**, không mặc định Spring Data Redis có sẵn.

Không dùng raw `eventId`, `orderId` hoặc Redis key làm Prometheus label: cardinality và rủi ro dữ liệu sẽ rất lớn.

## 27. Graceful shutdown và rolling deploy

Khi Kubernetes dừng worker:

~~~text
SIGTERM
  -> stop polling new messages
  -> let in-flight handlers finish within grace period
  -> ACK only successfully committed work
  -> exit
~~~

Nếu hết thời gian trước ACK, message vẫn pending để recovery. Cần:

- `BLOCK` timeout hữu hạn.
- Subscription/scheduler shutdown đúng lifecycle.
- Consumer identity policy rõ.
- `terminationGracePeriodSeconds` phù hợp.
- Recovery worker claim pending sau idle threshold an toàn.
- Không ACK tất cả in-flight entries khi nhận SIGTERM.

### 27.1. Consumer names sau restart

- **Stable name theo worker identity:** dễ đọc lại pending của cùng name nhưng phải tránh hai process trùng tên.
- **Unique name mỗi process:** tránh trùng trong rolling deploy, nhưng pending của process cũ cần claim.

Chọn theo kiến trúc, không xem UUID trong ví dụ là đáp án chuẩn cho mọi service.

## 28. Những tình huống lỗi cần test

### 28.1. Worker chết trước business commit

~~~text
XREADGROUP -> pending
worker crashes
recovery claims
handler executes once
XACK
~~~

Test yêu cầu event không bị bỏ quên.

### 28.2. Worker chết sau commit trước ACK

~~~text
XREADGROUP -> handler COMMIT
worker crashes before ACK
recovery claims
handler sees processed eventId -> no-op
XACK
~~~

Test yêu cầu side effect không bị thực thi hai lần.

### 28.3. Producer timeout sau XADD

~~~text
XADD actually appended
response lost
producer retries same eventId
second Redis entry appears
~~~

Test yêu cầu dedupe theo business event ID, không chỉ theo Record ID.

### 28.4. Handler sai schema

~~~text
missing eventId
-> validation error
-> retry policy decides permanent error
-> safely publish DLQ
-> ACK original after durable quarantine
~~~

Không được retry nóng vô hạn.

### 28.5. Lỗi `XACK` hoặc Redis connection

Handler có thể đã commit, ACK có thể thành công hoặc không, client timeout. Test phải phân biệt unknown outcome và không gọi lại external side effect thiếu idempotency.

### 28.6. Stream bị trim quá sớm

Test cảnh báo/retention khi consumer group offline lâu hoặc backlog tăng. Không đặt MAXLEN nhỏ đến mức xóa entries chưa xử lý.

### 28.7. Hai workers cạnh tranh reclaim

Test trường hợp worker-A chậm nhưng chưa chết, worker-B claim sau idle threshold; chỉ idempotency ở business layer mới bảo vệ side effect.

### 28.8. Restart và failover

Test Redis persistence/replication phù hợp, startup group state, reconnect và processing replay; không mặc định Redis ACK dữ liệu là zero-loss nếu primary chết trước replica/persistence.

## 29. Testcontainers với Redis Server thật

Một integration test cần Redis thực, không chỉ mock `RedisTemplate`. Có thể dùng:

~~~java
@SpringBootTest
@Testcontainers
class StreamIntegrationTest {

    @Container
    static final GenericContainer<?> redis =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.2.5-alpine")
        ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> redis.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate template;

    @Test
    void shouldReadAndAckMessage() {
        // 1. Tạo stream/group có namespace riêng.
        // 2. XADD với stable eventId.
        // 3. XREADGROUP bằng consumer test.
        // 4. Assert payload, RecordId và pending.
        // 5. Handler commit, XACK.
        // 6. Assert pending không còn.
    }
}
~~~

Đây là **khung minh họa**, không phải full test runnable do các thao tác setup/assert cần bổ sung cho contract thực. Phần quan trọng là JVM test phải kết nối đúng Redis container qua host/port động.

Suite nên có:

| Test | Mục tiêu |
|---|---|
| Publish/read/ACK | Happy path |
| Two consumers, one group | Work sharing |
| Two groups | Independent processing |
| Exception before ACK | PEL remains |
| Crash before commit | Reclaim and retry |
| Crash after commit | Idempotent no-op |
| Duplicate eventId | Dedupe |
| Poison message | DLQ |
| Claim after idle | Recovery threshold |
| Early claim while worker alive | No duplicate business effect |
| Redis timeout | Unknown outcome |
| Trimming | Retention safety |
| Stream missing/group missing | Error classification |
| Consumer restart | Pending recovery |
| Failover | Reconnect/retry semantics |
| Cluster topology | Slot routing/command support |

Nếu scheduler worker tự chạy trong test context, nó có thể giành mất message trước test method. Hãy tách profile, stream/group namespace hoặc tự điều khiển lifecycle để tránh test race.

## 30. Redis Cluster: ràng buộc theo hash slot

Trong Redis Cluster, mỗi stream key thuộc một hash slot. `XADD`/`XREADGROUP` một stream thường được client cluster-aware route tới node sở hữu slot.

Nhưng một `XREAD`/`XREADGROUP` chứa nhiều stream keys có thể chịu ràng buộc **same-slot**. Không tự giả định một command có thể đọc nhiều stream ở các primary khác nhau.

Nếu cần co-location:

~~~text
events:{tenant-42}:orders
events:{tenant-42}:payments
~~~

Hai keys cùng hash tag có cùng slot. Tuy nhiên tag quá rộng có thể tạo hot slot.

Khi thiết kế DLQ:

~~~text
orders:{partition-1}:events
orders:{partition-1}:dlq
~~~

có thể hữu ích nếu cần Redis-side multi-key transaction/script, nhưng vẫn phải tuân thủ API, Redis version và giới hạn durability. Không gom mọi events toàn hệ thống vào một hash tag chỉ để dễ thao tác.

### 30.1. Failover và MOVED/ASK

Redis Cluster/Sentinel failover có thể gây reconnect, timeout, hoặc redirect như `MOVED`/`ASK`. Các lệnh đã gửi có thể có outcome không chắc chắn.

- Producer vẫn cần stable eventId.
- Consumer vẫn cần idempotency.
- Blocking reads cần reconnect/re-subscribe phù hợp.
- Pending cần recovery.
- Không coi một Redis standalone integration test là bằng chứng Cluster-ready.

## 31. Redis durability, eviction và nguy cơ mất công việc

Redis Streams chạy trong Redis in-memory. Nếu sử dụng làm hàng đợi công việc quan trọng, phải xét:

- RDB snapshot có thể không chứa các write mới nhất.
- AOF `appendfsync everysec` không cam kết tuyệt đối mất tối đa đúng một giây trong mọi failure.
- Replica replication thường bất đồng bộ.
- Failover có thể làm mất một số acknowledged writes.
- Redis memory pressure có thể khiến write bị từ chối.
- Nếu policy cho phép eviction stream key, công việc có thể mất.
- Nếu stream bị xóa hoặc trim quá sớm, PEL không thể tạo lại payload đã mất.

Với workload quan trọng, cân nhắc **outbox bền vững + reconciliation + retention**. Redis persistence/replication được tính theo RPO/RTO, không thể thay thế bằng một câu “Stream không mất message”.

### 31.1. Không dùng chung cache eviction với queue không được mất

Nếu một Redis instance chứa cả cache có thể xóa và công việc quan trọng, `allkeys-lru` có thể làm stream key bị eviction khi thiếu RAM. Cân nhắc tách workloads hoặc chọn policy theo contract dữ liệu.

`noeviction` không tự giải quyết capacity; khi memory đầy, producer có thể nhận lỗi ghi. Cần backpressure, capacity alerts và outbox/retry thích hợp.

## 32. Checklist vận hành worker

**Producer**

- [ ] Stable event ID, event type, schema version.
- [ ] Dùng Stream key/serializer thống nhất.
- [ ] Có outbox nếu DB commit rồi publish phải đáng tin cậy.
- [ ] Publish timeout được xử lý với dedupe.
- [ ] Có metrics và alert publish failure.
- [ ] Payload không chứa dữ liệu nhạy cảm dư thừa.

**Consumer**

- [ ] Group được tạo một lần ở offset phù hợp.
- [ ] Consumer identity rõ theo process/pod.
- [ ] `ReadOffset.lastConsumed()` chỉ dùng cho entry mới.
- [ ] Chỉ ACK sau side effect commit.
- [ ] Handler idempotent theo business event ID.
- [ ] Có pending recovery/`XAUTOCLAIM`.
- [ ] Claim idle threshold không quá thấp.
- [ ] Có retry/backoff/max attempts và DLQ.
- [ ] Graceful shutdown không ACK nhầm.
- [ ] Có concurrency limit theo downstream capacity.
- [ ] Khi cần ordering có version/partition strategy.

**Redis và vận hành**

- [ ] Theo dõi `XINFO GROUPS`, `XPENDING`, consumer health.
- [ ] Theo dõi oldest uncompleted business event, không chỉ `XLEN`.
- [ ] Có retention bảo vệ backlog và pending.
- [ ] Có memory/disk headroom theo payload và growth.
- [ ] Có cảnh báo DLQ tăng và quy trình redrive.
- [ ] Có kế hoạch failover/persistence/RPO.
- [ ] Không dùng `XTRIM`/`XGROUP DESTROY` để “xóa lỗi” mà không hiểu dữ liệu.
- [ ] Đã test crash, duplicate, ACK timeout và recovery.
- [ ] Nếu dùng Cluster, đã test same-slot/multi-stream behavior.

## 33. Những hiểu lầm cần tránh

**“Consumer group hoạt động như Pub/Sub, mọi consumer nhận mọi entry.”** Sai. Consumers trong cùng group chia entries mới.

**“`XREADGROUP >` sẽ tự phát lại message của worker đã chết.”** Sai. Message đang pending cần đọc theo consumer cũ hoặc claim.

**“`XACK` xóa entry khỏi Stream.”** Sai. Nó chỉ xóa trạng thái pending trong group.

**“`XLEN` là số job chưa xử lý.”** Sai. Stream còn chứa entries đã ACK và chưa trim.

**“`lag=0` nghĩa là mọi event đã hoàn tất.”** Sai. Có thể còn pending chưa ACK.

**“`XAUTOCLAIM` ngăn mọi duplicate.”** Sai. Worker cũ vẫn có thể chạy, producer còn có thể publish duplicate.

**“`COUNT 100` tạo một transaction 100 messages.”** Sai. ACK/side effects không tự atomic theo batch.

**“Càng nhiều consumer càng giữ đúng thứ tự.”** Sai. Thứ tự hoàn tất có thể khác thứ tự Stream ID.

**“`@Transactional` của JPA làm DB và Redis XADD nguyên tử.”** Sai. Cần outbox hoặc kiến trúc nhất quán khác.

**“`XADD` trả ID nghĩa là event đã được fsync trên mọi replica.”** Sai. Durability phụ thuộc cấu hình và topology.

**“Auto-ACK phù hợp mọi xử lý.”** Sai. ACK trước business commit có thể gây mất công việc.

**“Không cần dọn Stream vì message sẽ biến mất sau ACK.”** Sai. Phải thiết kế retention.

**“DLQ chỉ là nơi bỏ message lỗi.”** Sai. Cần owner, replay, dedupe và retention.

**“Reactive không cần giới hạn concurrency.”** Sai. Redis, network, buffers và downstream đều hữu hạn.

## 34. Kết luận và quy trình triển khai đề xuất

Một workflow Spring Data Redis Streams có thể tổ chức như sau:

~~~text
Business DB transaction
       |
       +-- outbox nếu cần bảo đảm publish
       |
       v
XADD (stable eventId)
       |
       v
Redis Stream
       |
       v
XREADGROUP ... >
       |
       v
Validate + idempotent handler
       |
       v
Commit side effect
       |
       v
XACK
       |
       +-- error/crash: PEL
                            |
                            v
                         XAUTOCLAIM
                            |
                      retry / DLQ
~~~

Các nguyên tắc cốt lõi:

1. **Streams lưu entries, consumer group quản lý phân phối và PEL**.
2. **`XREADGROUP ... >` lấy entry mới**; pending cũ cần cơ chế recovery rõ ràng.
3. **`XACK` chỉ sau khi side effect hoàn tất**, không ACK để che error.
4. **Redelivery là tình huống bình thường**; cần stable `eventId` và durable idempotency.
5. **Outbox giải quyết khoảng trống DB commit → publish** ở những workflow cần tin cậy.
6. **Retry và DLQ** giúp xử lý poison message nhưng không được làm duplicate external side effects.
7. **Retention phải bảo vệ cả messages chưa giao lẫn pending của mọi group**.
8. **Ordering, concurrency và connection sizing** phải dựa trên nghiệp vụ và downstream capacity.
9. **Quan sát business completion delay**, không chỉ stream length hoặc số pending.
10. **Kiểm thử crash, reconnect, duplicate và failover** trên Redis Server/topology thật trước khi dựa vào hàng đợi cho công việc quan trọng.

Redis Streams là một công cụ mạnh để xây dựng workers bất đồng bộ trong Spring Boot. Độ tin cậy của hệ thống không đến từ một lệnh Redis riêng lẻ, mà đến từ **hợp đồng đầy đủ giữa producer, stream, consumer group, database, side effect, ACK, recovery và vận hành**.
