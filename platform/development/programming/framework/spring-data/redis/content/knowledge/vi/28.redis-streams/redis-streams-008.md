# Cấu hình StreamMessageListenerContainer trong Spring Data Redis

**Redis Streams** cho phép ứng dụng ghi các sự kiện vào một stream và để một hoặc nhiều consumer xử lý theo thứ tự ID của bản ghi. Nếu ứng dụng Java phải tự viết vòng lặp `XREAD` hoặc `XREADGROUP`, tự quản lý thread, kết nối, offset và thời điểm dừng, mã xử lý rất dễ bị trộn lẫn với nghiệp vụ. **Spring Data Redis** cung cấp `StreamMessageListenerContainer` để tổ chức việc **poll Redis Streams trên các tác vụ nền** và chuyển message đến một `StreamListener`.

Cấu hình container cần trả lời nhiều câu hỏi hơn việc kết nối được Redis: stream có tồn tại chưa, đọc trực tiếp hay qua consumer group, bắt đầu ở offset nào, dùng bao nhiêu thread, mỗi lần poll lấy bao nhiêu bản ghi, khi nào `XACK`, khi listener lỗi thì message ở đâu và làm sao khôi phục pending sau khi instance chết.

Bài học này trình bày một cấu hình hoàn chỉnh với `StreamMessageListenerContainer`, cách đăng ký consumer group, điều chỉnh các tùy chọn vận hành và cách triển khai xử lý message có khả năng retry thực tế.

## 1. Vị trí của StreamMessageListenerContainer trong hệ thống

Một producer dùng Redis Streams có thể ghi sự kiện tạo đơn hàng:

```text
Producer (Order Service)
        |
        | XADD orders:events * eventType OrderCreated orderId 42
        v
Redis Stream: orders:events
        |
        | XREAD / XREADGROUP, có thể BLOCK trong mỗi vòng poll
        v
StreamMessageListenerContainer
        |
        | chuyển Record tới StreamListener
        v
OrderEventHandler
        |
        +--> xử lý nghiệp vụ
        +--> xác nhận XACK (nếu dùng consumer group, manual ACK)
```

**Container không phải chính stream hay một broker riêng.** Nó chạy bên trong tiến trình Spring, sử dụng kết nối Redis và executor để đọc stream, rồi gọi callback khi nhận được record.

Các thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| `RedisConnectionFactory` | Cung cấp kết nối Redis qua client được cấu hình |
| `StreamMessageListenerContainer<K,V>` | Điều phối polling bất đồng bộ và đưa record tới listener |
| `StreamMessageListenerContainerOptions<K,V>` | Cấu hình batch size, poll timeout, executor, serializer và xử lý lỗi |
| `StreamOffset<K>` / `ReadOffset` | Xác định stream và vị trí bắt đầu đọc |
| `Consumer.from(group, name)` | Xác định consumer group và consumer identity |
| `StreamListener<K,V>` | Nhận và xử lý từng record |
| `Subscription` | Đại diện một đăng ký đọc stream, có thể quản lý/hủy đăng ký |
| `StringRedisTemplate.opsForStream()` | Gửi `XADD`, `XACK` hoặc thao tác stream khác khi cần |

`StreamMessageListenerContainer` là API theo kiểu imperative, **không phải** `StreamReceiver` của Reactive Redis. Cả hai đều hỗ trợ nhận message nhưng mô hình sử dụng thread, backpressure và callback khác nhau.

## 2. “Bất đồng bộ” ở container không có nghĩa Redis không blocking

Một nhầm lẫn phổ biến là thấy tên listener container rồi nghĩ việc đọc Redis không bao giờ dùng lệnh chờ.

Trên thực tế, container thường thực hiện các vòng poll bằng `XREAD` hoặc `XREADGROUP` với tham số `BLOCK`. Redis có thể giữ request trong một khoảng thời gian để chờ message mới. Điểm khác biệt là **lệnh chờ chạy trong công việc nền của container**, không chặn thread đang xử lý HTTP request của ứng dụng.

```text
HTTP thread:
  gọi service/đăng ký listener -> tiếp tục xử lý HTTP

Container polling task:
  XREADGROUP BLOCK 2000 COUNT 20
           |
           +--> Có message: đọc và gọi listener
           |
           +--> Hết 2 giây: quay lại vòng poll
```

Vì vậy:

- `pollTimeout` điều khiển **thời gian chờ tối đa của một lần poll blocking** (tùy API và cách Redis client truyền lệnh).
- `batchSize` điều khiển số record tối đa được yêu cầu trong một vòng poll.
- Executor quyết định tài nguyên thread thực hiện việc đọc và callback.
- Một callback xử lý chậm có thể làm vòng poll/subscription tương ứng xử lý ít message hơn.
- Container cần được khởi động và dừng đúng cách để giải phóng công việc nền và kết nối.

Không nên đặt `pollTimeout` rất lớn rồi mong việc shutdown/đổi cấu hình sẽ luôn được phản hồi tức thì. Ngược lại, timeout quá ngắn có thể gây nhiều vòng poll không có dữ liệu và tăng overhead.

## 3. Chuẩn bị stream và consumer group trước khi khởi động

Bài học sử dụng:

```text
Stream key:      orders:events
Consumer group:  orders-workers
Consumer name:   orders-api-1
```

Có hai lựa chọn: đọc stream **không qua group**, hoặc đọc **trong consumer group**. Với hệ thống nhiều instance cần chia nhau xử lý message, consumer group thường là lựa chọn phù hợp.

### 3.1. Tạo group bằng redis-cli

Trên Redis thử nghiệm:

```bash
redis-cli XGROUP CREATE orders:events orders-workers 0-0 MKSTREAM
```

Ý nghĩa:

- `orders:events`: key của Redis Stream.
- `orders-workers`: tên group.
- `0-0`: group bắt đầu từ đầu lịch sử stream, để các message hiện có có thể được phân phối khi consumer đọc message mới cho group.
- `MKSTREAM`: nếu stream chưa có, Redis tạo một stream rỗng.

Nếu thay `0-0` bằng `$`, group khởi tạo tại **ID cuối hiện tại**, tức các message đã tồn tại trước khi tạo group thường không được phát như message mới cho group. Đây là quyết định quan trọng khi triển khai lần đầu.

Nếu group đã tồn tại, Redis có thể trả `BUSYGROUP`. Việc chuẩn bị group trong application/deployment cần có hành vi **idempotent**, phân biệt “group đã có” với lỗi Redis thật, không vô điều kiện xóa và tạo lại group mỗi lần khởi động.

Kiểm tra:

```bash
redis-cli XINFO GROUPS orders:events
```

### 3.2. Ghi message thử

```bash
redis-cli XADD orders:events '*' eventType OrderCreated orderId 42 version 1
redis-cli XADD orders:events '*' eventType OrderPaid orderId 42 version 2
```

Mỗi message có một **record ID** do Redis cấp, ví dụ `1730000000000-0`. ID này không phải `orderId`; nó biểu thị vị trí của entry trong stream, còn `orderId` là dữ liệu nghiệp vụ nằm trong map của message.

Có thể quan sát:

```bash
redis-cli XRANGE orders:events - +
redis-cli XLEN orders:events
```

`XLEN` là số entry còn tồn tại trong stream, **không phải** số message đang chờ ACK của một group. Xác nhận bằng `XACK` cũng **không tự xóa entry khỏi stream**.

## 4. Khai báo các dependency và bean nền

Giả sử ứng dụng Spring Boot đã có Redis connection và sử dụng `spring-boot-starter-data-redis`. Các class chính thuộc các package Spring Data Redis:

```java
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;
import org.springframework.data.redis.stream.StreamMessageListenerContainerOptions;
import org.springframework.data.redis.stream.Subscription;
```

Với một môi trường thực tế, `RedisConnectionFactory` do Spring Boot cấu hình từ URI/host/port, TLS, credentials và pool nếu có. Container sẽ dùng connection factory này; **đừng tạo Redis client riêng cho từng message**.

### 4.1. Tạo executor có tên thread rõ ràng

```java
package example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class StreamExecutorConfiguration {

    @Bean("redisStreamExecutor")
    public ThreadPoolTaskExecutor redisStreamExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("redis-stream-poll-");

        return executor;
    }
}
```

Con số 4/8/64 là giá trị **minh họa**, không phải khuyến nghị cố định. Mỗi subscription có thể cần một tác vụ polling tồn tại lâu, đặc biệt khi dùng blocking read. Nếu số thread ít hơn số subscription đang chờ, có subscription không có thread để bắt đầu poll.

Với listener xử lý nghiệp vụ nặng, nên tách polling và công việc xử lý theo kiến trúc phù hợp; tuy nhiên, nếu chuyển việc xử lý sang executor khác, **không ACK trước khi công việc đó hoàn tất bền vững**.

## 5. Cấu hình StreamMessageListenerContainerOptions

Một cấu hình options điển hình:

```java
StreamMessageListenerContainerOptions
        <String, MapRecord<String, String, String>> options =
        StreamMessageListenerContainerOptions
                .<String, MapRecord<String, String, String>>builder()
                .pollTimeout(Duration.ofSeconds(2))
                .batchSize(20)
                .executor(redisStreamExecutor)
                .build();
```

Ý nghĩa:

| Option | Vai trò | Điều cần cân nhắc |
|---|---|---|
| `pollTimeout(Duration)` | Thời gian chờ trong mỗi lần polling Redis | Thời gian phát hiện message và khả năng dừng/thoát vòng poll |
| `batchSize(int)` | Yêu cầu tối đa bao nhiêu record mỗi lần đọc | Throughput, thời gian xử lý một batch, số message đang chờ ACK |
| `executor(TaskExecutor)` | Nơi chạy các tác vụ polling/callback | Số subscription, thời gian blocking, saturation |
| Serializers | Cách giải mã key, field, value | Phải thống nhất với producer để không nhận chuỗi/byte sai |
| Error handling | Cách ghi nhận và phản ứng với lỗi đọc/deserialize/callback | Không được coi lỗi listener là đã xử lý thành công |
| Object mapping/target type | Chuyển record thành kiểu Java khi dùng object records | Tương thích schema và converter |

Các API chi tiết của builder có thể khác theo version Spring Data Redis, nhưng những lựa chọn trên là các khía cạnh cần thiết khi triển khai. Với ví dụ `MapRecord<String, String, String>`, producer và listener cùng quy ước field/value dạng chuỗi.

### 5.1. Đừng nhầm batchSize với giới hạn số message chưa ACK

`batchSize(20)` ảnh hưởng **số entry yêu cầu mỗi lần đọc**, không có nghĩa Redis tự hạn chế toàn group tối đa 20 entry chưa được ACK.

Một handler lỗi lặp lại hoặc một consumer bị dừng giữa chừng có thể khiến **Pending Entries List (PEL)** tăng theo thời gian. Cần đo và quản lý PEL độc lập với batch size.

### 5.2. Serializer là một phần của giao thức message

Redis Stream entry chứa các byte. Nếu producer dùng `StringRedisTemplate` ghi field `eventType` và value `OrderCreated` dưới dạng chuỗi, consumer cần giải mã tương thích.

Ngược lại, khi producer sử dụng serializer nhị phân hoặc JSON theo quy ước riêng, listener không thể tự suy ra kiểu chỉ từ tên Java generic. Trong dự án dùng `ObjectRecord`, còn phải xác định converter, type information, schema evolution và target type.

Cần thống nhất hợp đồng:

```text
Stream: orders:events
Field:  eventType  -> UTF-8 string
Field:  orderId    -> UTF-8 decimal string
Field:  version    -> UTF-8 decimal string

RecordId do Redis cấp
Consumer group: orders-workers
ACK sau khi xử lý và ghi trạng thái thành công
```

## 6. Bean container với consumer group và vòng đời start/stop

Ví dụ sau dùng một listener có tên rõ ràng, một executor riêng và lifecycle được Spring quản lý.

```java
package example.orders;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;
import org.springframework.data.redis.stream.StreamMessageListenerContainerOptions;

@Configuration
public class OrderStreamContainerConfiguration {

    private static final String STREAM = "orders:events";
    private static final String GROUP = "orders-workers";

    @Bean(initMethod = "start", destroyMethod = "stop")
    public StreamMessageListenerContainer
            <String, MapRecord<String, String, String>>
    orderStreamContainer(
            RedisConnectionFactory connectionFactory,
            @Qualifier("redisStreamExecutor") TaskExecutor executor,
            OrderStreamListener listener) {

        var options = StreamMessageListenerContainerOptions
                .<String, MapRecord<String, String, String>>builder()
                .pollTimeout(Duration.ofSeconds(2))
                .batchSize(20)
                .executor(executor)
                .build();

        var container = StreamMessageListenerContainer.create(
                connectionFactory, options);

        container.receive(
                Consumer.from(GROUP, "orders-api-1"),
                StreamOffset.create(STREAM, ReadOffset.lastConsumed()),
                listener
        );

        return container;
    }
}
```

Trong ví dụ:

1. Spring tạo `RedisConnectionFactory` và executor.
2. Bean method dựng container với options.
3. `container.receive(...)` đăng ký subscription cho stream, group và listener.
4. `initMethod = "start"` yêu cầu Spring khởi động container khi bean sẵn sàng; tùy lifecycle support của phiên bản, cũng có thể tổ chức startup bằng cơ chế lifecycle riêng, nhưng **không gọi start hai lần vô tình**.
5. `destroyMethod = "stop"` yêu cầu dừng các tác vụ polling khi context đóng.

**Điều kiện tiên quyết:** group `orders-workers` phải được tạo trước khi consumer thực sự bắt đầu `XREADGROUP`. Bean container không mặc nhiên chịu trách nhiệm tự tạo group. Nếu group chưa có, quá trình đọc có thể thất bại với lỗi `NOGROUP`.

### 6.1. Tên consumer phải được quản lý

`Consumer.from(GROUP, "orders-api-1")` định danh một member trong group. Trong môi trường có nhiều instance, **không dùng cùng một tên consumer cho mọi instance** nếu cần quan sát và phân quyền pending rõ ràng.

Ví dụ:

```text
orders-workers:
    orders-api-1
    orders-api-2
    orders-worker-batch-1
```

Tên consumer nên được cấu hình theo instance/pod ID hoặc một định danh vận hành ổn định theo chính sách triển khai. Redis không ngăn hai process sử dụng cùng tên, nhưng chúng bị xem là cùng consumer identity, làm việc phân tích PEL và việc thu hồi message khó hiểu hơn.

### 6.2. Thêm nhiều subscription

Một container có thể đăng ký nhiều subscription nếu cần. Nhưng **mỗi polling subscription sử dụng tài nguyên**: thêm subscription không miễn phí và không có nghĩa một executor nhỏ có thể phục vụ vô hạn stream/consumer.

Nếu cần xử lý 20 stream hoặc 20 subscription, cần thiết kế số thread, connection và mức độ blocking phù hợp. Nếu dùng nhiều consumer cùng group để chia tải, phân biệt mỗi subscription là một consumer riêng và tránh vô ý cho một event được xử lý nhiều lần bởi các nhóm khác nhau.

## 7. Viết StreamListener với manual acknowledgement

Với consumer group, một message được giao cho consumer nhưng **chưa ACK** sẽ nằm trong Pending Entries List cho tới khi được xác nhận hoặc xử lý bằng cơ chế phục hồi phù hợp.

Một listener có thể triển khai:

```java
package example.orders;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Component;

@Component
public class OrderStreamListener
        implements StreamListener
                <String, MapRecord<String, String, String>> {

    private static final String STREAM = "orders:events";
    private static final String GROUP = "orders-workers";

    private final OrderEventService orderEventService;
    private final StringRedisTemplate redisTemplate;

    public OrderStreamListener(
            OrderEventService orderEventService,
            StringRedisTemplate redisTemplate) {
        this.orderEventService = orderEventService;
        this.redisTemplate = redisTemplate;
    }

    @Override
    public void onMessage(MapRecord<String, String, String> message) {
        String eventType = message.getValue().get("eventType");
        String orderId = message.getValue().get("orderId");

        // Hàm này phải có idempotency nếu message có thể được giao lại.
        orderEventService.process(
                message.getId().getValue(),
                eventType,
                orderId
        );

        // ACK chỉ sau khi tác động nghiệp vụ cần thiết đã hoàn tất.
        redisTemplate.opsForStream().acknowledge(
                STREAM,
                GROUP,
                message.getId()
        );
    }
}
```

Ý nghĩa:

- `message.getId()` lấy **Redis stream record ID**, không phải `orderId` của payload.
- `message.getValue()` cho biết các field/value đã được deserialize.
- `orderEventService.process(...)` thực hiện nghiệp vụ, ví dụ ghi vào database hoặc gọi một xử lý có thể kiểm chứng.
- `XACK` được gửi **sau khi** `process` thành công.
- Nếu `process` ném exception, dòng ACK phía sau sẽ không chạy; message có thể còn pending để xử lý lại.

Để đơn giản, ví dụ không đưa logic retry vào listener. Trong production phải ghi log gồm stream, group, consumer, record ID, loại lỗi và có phương án xử lý message độc hại. Không ghi thông tin nhạy cảm từ payload vào log.

### 7.1. Manual ACK không có nghĩa exactly-once

Có một khoảng lỗi:

```text
T1  Consumer nhận message ID 100-0
T2  Ghi kết quả nghiệp vụ vào database thành công
T3  Process chết trước XACK
T4  Message vẫn nằm pending
T5  Consumer khác reclaim và xử lý lại 100-0
```

Nếu xử lý nghiệp vụ không idempotent, một sự kiện có thể tạo tác động lặp. Vì vậy Redis Streams + consumer group + manual ACK thường được thiết kế theo ngữ nghĩa **at-least-once ở tầng ứng dụng** khi có retry/reclaim. Cần dùng event ID hoặc business idempotency key để phát hiện đã xử lý.

Ví dụ với database, có thể tạo bảng `processed_events(consumer_group, stream_record_id, processed_at)` có unique constraint. Trong cùng transaction SQL với thay đổi nghiệp vụ, ghi nhận event ID đã xử lý. Nếu record bị giao lại, service kiểm tra/insert có điều kiện và bỏ qua tác động trùng, sau đó vẫn có thể ACK.

Việc ghi nhận idempotency và thay đổi nghiệp vụ trong cùng database transaction mang lại bảo đảm tốt hơn việc lưu một biến boolean trong bộ nhớ JVM.

## 8. receive() và receiveAutoAck(): khác nhau ở đâu?

Khi đăng ký consumer group, Spring Data Redis cung cấp đường nhận message với **ACK thủ công** và đường **auto acknowledgment** (tùy API/phiên bản).

Ví dụ manual ACK:

```java
container.receive(
        Consumer.from("orders-workers", "orders-api-1"),
        StreamOffset.create("orders:events", ReadOffset.lastConsumed()),
        listener
);
```

Ví dụ auto ACK:

```java
container.receiveAutoAck(
        Consumer.from("orders-workers", "orders-api-1"),
        StreamOffset.create("orders:events", ReadOffset.lastConsumed()),
        listener
);
```

Khác biệt về thiết kế:

| Tiêu chí | Manual ACK qua `receive` | Auto ACK qua `receiveAutoAck` |
|---|---|---|
| Ai quyết định gửi ACK? | Code xử lý nghiệp vụ | Container/framework theo cơ chế auto-ack |
| Có thể chỉ ACK sau DB commit? | Có, khi code sắp xếp đúng | Không nên giả định ACK phản ánh transaction nghiệp vụ đã commit |
| Phù hợp | Message quan trọng, có thể cần retry/reclaim | Xử lý nhẹ có thể chấp nhận giới hạn delivery |
| Khi handler lỗi | Có thể để pending nếu chưa ACK | Hành vi đã ACK/không còn pending phụ thuộc semantics auto-ack, cần xem xét cẩn thận |
| Cần xử lý idempotency? | Có | Vẫn cần nếu có khả năng lặp ở nhiều tầng |

Không nên dùng auto-ACK chỉ để “giảm vài dòng code” khi business operation bắt buộc không được mất. Với luồng quan trọng, ưu tiên **manual ACK sau xử lý thành công** và có chính sách reclaim/retry rõ ràng.

## 9. Chọn ReadOffset đúng với chế độ đọc

`ReadOffset` không chỉ là chi tiết cú pháp. Nó quyết định **message nào được Redis trả về**, và dùng sai offset có thể gây bỏ sót hoặc đọc lại ngoài ý muốn.

### 9.1. Consumer group: ReadOffset.lastConsumed()

```java
container.receive(
        Consumer.from("orders-workers", "orders-api-1"),
        StreamOffset.create(
                "orders:events",
                ReadOffset.lastConsumed()),
        listener
);
```

Trong consumer group, cách dùng `lastConsumed()` được áp dụng phổ biến để đọc **những entry mới chưa được giao cho group**, tương ứng ý tưởng `XREADGROUP ... STREAMS orders:events >`.

Khi worker restart, nhóm đã có vị trí đọc và Pending Entries List riêng. Việc chỉ đăng ký lại bằng `lastConsumed()` **không có nghĩa mọi entry pending của consumer chết trước đó sẽ được xử lý lại tự động**.

### 9.2. Đọc không qua group

```java
container.receive(
        StreamOffset.create(
                "orders:events",
                ReadOffset.from("0-0")),
        listener
);
```

Đây là ví dụ nhận từ offset xác định mà không gắn consumer group. Trong mô hình không group, mỗi subscription có thể đọc các entry theo offset của nó; không có `XACK` hoặc PEL của consumer group cho đường đọc này.

`ReadOffset.latest()` phù hợp khi chỉ quan tâm entry xuất hiện sau điểm bắt đầu đọc và chấp nhận bỏ qua lịch sử. Cần cẩn trọng khi polling bằng latest offset, vì nếu ứng dụng dùng sai semantics qua các lần poll hoặc có khoảng không đọc, một số message đến trong khoảng đó có thể bị bỏ sót theo cách đặt offset.

### 9.3. Không tự thay offset khi chưa xác định yêu cầu

| Mục tiêu | Cách tiếp cận |
|---|---|
| Chia message giữa nhiều worker | Consumer group, `ReadOffset.lastConsumed()` |
| Đọc lịch sử từ đầu trong môi trường thử nghiệm | Offset bắt đầu như `0-0`, tùy group/non-group |
| Chỉ xem message mới khi monitor | Offset latest, chấp nhận không replay lịch sử |
| Khôi phục message đã giao nhưng chưa ACK | Kiểm tra PEL và dùng cơ chế claim/retry, không chỉ đổi offset |
| Chạy lại toàn bộ stream như một batch | Thiết kế riêng replay cursor/group, tránh làm hỏng offset production |

Đổi group offset bằng `XGROUP SETID` có thể thay đổi phạm vi message mới được giao cho cả group. Đây là thao tác quản trị ảnh hưởng dữ liệu, không dùng tùy tiện để sửa một consumer bị lỗi.

## 10. Pending Entries List và cách khôi phục message chưa ACK

Redis consumer group lưu thông tin các message đã được giao nhưng **chưa ACK** trong PEL. Khi listener lỗi hoặc ứng dụng chết sau nhận, các message này không biến mất chỉ vì container dừng.

Quan sát:

```bash
redis-cli XINFO GROUPS orders:events
redis-cli XINFO CONSUMERS orders:events orders-workers
redis-cli XPENDING orders:events orders-workers
```

Nếu cần xem các pending entry cụ thể:

```bash
redis-cli XPENDING orders:events orders-workers - + 10
```

Kết quả có thể cung cấp record ID, consumer đang sở hữu, thời gian idle và số lần delivery theo dạng lệnh sử dụng.

### 10.1. Vì sao pending không tự được đọc lại bằng dấu >

Khi consumer group đọc entry mới bằng `>`, Redis chọn các entry **chưa từng được giao cho group**. Một entry đã nằm trong PEL không tự quay lại như entry mới. Việc restart container với cùng `ReadOffset.lastConsumed()` không tự giải quyết các message tồn đọng trong PEL.

Cần một **recovery flow**:

1. Quan sát PEL theo group và idle time.
2. Xác định entry nào đã idle đủ lâu để có thể reclaim.
3. Chuyển quyền sở hữu pending entry đến consumer hiện tại.
4. Chạy lại xử lý nghiệp vụ một cách idempotent.
5. ACK khi hoàn tất.

### 10.2. XAUTOCLAIM

Ví dụ dùng Redis CLI trong môi trường thử nghiệm:

```bash
redis-cli XAUTOCLAIM orders:events orders-workers orders-recovery-1 60000 0-0 COUNT 100
```

Ý nghĩa:

- `orders:events`: stream.
- `orders-workers`: group.
- `orders-recovery-1`: consumer nhận quyền sở hữu.
- `60000`: yêu cầu message idle ít nhất 60.000 ms.
- `0-0`: cursor bắt đầu quét pending.
- `COUNT 100`: mức độ xử lý mong muốn trong lô.

Phải tiếp tục bằng cursor được Redis trả về khi cần quét thêm; `XAUTOCLAIM` không đảm bảo một lần gọi xử lý hết tất cả message tồn đọng.

**Idle threshold không nên quá ngắn.** Nếu một handler hợp lệ đang xử lý một message lâu hơn 60 giây, recovery worker có thể reclaim nó khi handler đầu tiên vẫn làm việc, tạo xử lý song song trùng. Cần chọn threshold từ thời gian xử lý thực tế, có ownership/idempotency và chính sách retry phù hợp.

### 10.3. Poison message và dead-letter

Một message có schema sai hoặc nghiệp vụ không thể hoàn thành có thể thất bại lặp lại. Nếu cứ reclaim vô hạn, PEL không giảm và service lãng phí tài nguyên.

Cần thiết kế:

- Số lần thử tối đa hoặc tiêu chí lỗi không thể phục hồi.
- Log ID, loại lỗi, thời gian và lịch sử thử.
- Dead-letter stream hoặc bảng lỗi riêng để điều tra.
- Khi đã lưu được bản sao sự kiện lỗi bền vững vào dead-letter, quyết định ACK message gốc theo chính sách rõ ràng.
- Khả năng replay sau khi sửa code hoặc dữ liệu nguồn.
- Không tự ACK/drop message chỉ vì lỗi khó xử lý mà không có cơ chế kiểm toán.

Container nhận message là một phần của hệ thống; **retry/reclaim/DLQ không tự xuất hiện đầy đủ chỉ nhờ tạo container**.

## 11. Vòng đời subscription: đăng ký, chạy, hủy, dừng

Một subscription được tạo bằng:

```java
Subscription subscription = container.receive(
        Consumer.from("orders-workers", "orders-api-1"),
        StreamOffset.create("orders:events", ReadOffset.lastConsumed()),
        listener
);
```

Để nhận message, container phải ở trạng thái đang chạy. Khi cấu hình bằng bean có `initMethod="start"`, vòng đời thông thường do Spring quản lý. Có thể dùng:

```java
container.start();
container.stop();
```

trong một chiến lược quản lý lifecycle khác khi không dùng init/destroy method. Tránh vừa khai báo tự start vừa gọi start tùy tiện tại nhiều vị trí.

`Subscription` cung cấp cơ chế quản lý đăng ký, gồm hủy subscription khi không còn cần poll stream; các API cụ thể có thể khác theo phiên bản, nên dùng theo hợp đồng của dependency đang chạy.

### 11.1. Shutdown an toàn

Trong deployment rolling restart:

1. Ngừng nhận HTTP/command mới hoặc đưa instance ra khỏi cân bằng tải nếu cần.
2. Dừng/hủy subscription để không nhận thêm message.
3. Cho phép handler đang chạy hoàn tất trong thời hạn graceful shutdown.
4. ACK các message đã hoàn tất; những message chưa hoàn tất giữ trạng thái pending để recovery xử lý.
5. Dừng executor và giải phóng kết nối.

Không nên cho rằng `container.stop()` tự làm hoàn tất mọi nghiệp vụ đang chạy. Nếu tiến trình bị kill giữa chừng, message đã nhận nhưng chưa ACK có thể cần reclaim sau restart. Chính sách graceful shutdown cần phù hợp timeout của Kubernetes/systemd và thời gian xử lý dài nhất.

### 11.2. Không tạo container mới cho mỗi request

Container là thành phần chạy nền lâu dài, phù hợp làm **singleton bean**. Tạo container, executor và subscription trong từng HTTP request có thể làm rò rỉ thread, connection và tạo nhiều consumer không kiểm soát.

Nếu có nhiều stream cùng quy cách, một container có thể quản lý nhiều subscription, hoặc nhóm container theo cấu hình vận hành; quyết định dựa vào tài nguyên, tần suất poll và yêu cầu cô lập lỗi.

## 12. Quản lý lỗi container và listener

Cần phân biệt ít nhất ba nhóm lỗi:

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| **Lỗi đọc Redis** | Mạng đứt, timeout, lỗi permission, Redis failover | Retry/reconnect theo policy, giám sát subscription đang chạy |
| **Lỗi deserialize** | Producer thay schema/serializer, payload sai định dạng | Ghi nhận record có vấn đề, DLQ hoặc sửa schema |
| **Lỗi nghiệp vụ** | Database timeout, message trùng, dữ liệu không hợp lệ | Không ACK trước thành công; idempotency, retry, DLQ |

Options của container hỗ trợ cơ chế xử lý lỗi; ở các phiên bản tương ứng có thể cấu hình error handler để ghi nhận exception ở tác vụ polling/processing. **Không nên dựa duy nhất vào log exception để kết luận subscription vẫn sẽ tiếp tục chạy**: một số lỗi có thể khiến subscription dừng/hủy tùy cấu hình. Cần giám sát trạng thái thực tế.

Ví dụ log hữu ích:

```text
stream      = orders:events
group       = orders-workers
consumer    = orders-api-1
recordId    = 1730000000000-0
operation   = process
errorType   = DatabaseTimeout
attempt     = 3
durationMs  = 1200
action      = leave-pending
```

Không nên log toàn bộ payload có dữ liệu nhạy cảm; thường chỉ ID và metadata lỗi đã đủ để điều tra.

### 12.1. Catch exception rồi nuốt có nguy hiểm không?

```java
@Override
public void onMessage(MapRecord<String, String, String> record) {
    try {
        orderEventService.process(...);
    } catch (Exception e) {
        log.error("Processing failed", e);
        // Không ACK trong nhánh lỗi.
    }
}
```

Khi dùng manual ACK, message vẫn pending nếu không ACK; nhưng nếu listener chỉ nuốt lỗi mà không có recovery worker, message có thể bị bỏ quên vô hạn. Vì vậy phải có đường xử lý pending rõ ràng, không chỉ “đã log lỗi là xong”.

## 13. Throughput, batchSize và kích thước executor

Giả sử message đến ở tốc độ 500 message/s, mỗi message cần trung bình 20 ms để xử lý. Một subscription xử lý tuần tự trên một thread có công suất lý thuyết khoảng:

```text
1 / 0,020 giây ≈ 50 message/giây
```

Đây chỉ là phép ước lượng đơn giản, bỏ qua độ trễ Redis, I/O, retry, network, database và xử lý batch. Nếu thực sự chỉ có một luồng xử lý tuần tự như vậy, việc tăng `batchSize` từ 20 lên 200 không tự tạo ra công suất 500 message/s.

Các đòn bẩy cần cân nhắc:

- Tăng số **consumer identity** trong cùng group để chia message.
- Đảm bảo executor đủ thread cho các subscription đang blocking read.
- Giảm thời gian xử lý mỗi message hoặc offload sang worker pool có giới hạn.
- Điều chỉnh `batchSize` để cân bằng round-trip và thời gian giữ các message.
- Đo CPU Redis, database, network, pending count và consumer lag.
- Có backpressure/chặn nhận khi downstream quá tải thay vì nạp vô hạn message vào bộ nhớ.

**Không ACK trước khi công việc offload kết thúc.** Nếu listener chỉ submit vào thread pool rồi ACK lập tức, process crash có thể làm mất tác vụ vẫn còn chờ trong bộ nhớ mà Redis đã xem là xác nhận.

### 13.1. Consumer group không giống pub/sub broadcast

Trong một group, các consumer **chia nhau** những message mới được giao; mỗi entry thường được giao cho một consumer trong group tại một thời điểm. Nếu hai hệ thống độc lập cần cùng nhận một sự kiện, chúng thường cần **hai consumer group** khác nhau.

```text
Stream orders:events
    |
    +--> Group orders-payment-workers
    |         payment-worker-1
    |         payment-worker-2
    |
    +--> Group orders-analytics-workers
              analytics-worker-1
              analytics-worker-2
```

Mỗi group có offset và PEL riêng. ACK ở group analytics không thay thế ACK ở group payment.

## 14. Quản lý retention: XACK không xóa stream entry

Redis Streams phân biệt:

1. **Stream storage:** các entry vật lý còn tồn tại trong stream.
2. **Consumer group delivery state:** entry nào đã được giao và đang pending.
3. **ACK state:** xác nhận một group đã xử lý message theo giao thức của ứng dụng.

Ví dụ:

```bash
redis-cli XLEN orders:events
redis-cli XPENDING orders:events orders-workers
```

Sau khi `XACK`, pending count có thể giảm nhưng `XLEN` vẫn giữ nguyên. Nếu không có retention policy, stream có thể tiếp tục tăng theo thời gian.

Một số lệnh quản trị:

```bash
redis-cli XTRIM orders:events MAXLEN '~' 100000
redis-cli XINFO STREAM orders:events
```

`XTRIM` có thể loại bỏ entry khỏi stream; nếu xóa khi một group còn cần message, dữ liệu để replay/reclaim có thể không còn đầy đủ. Cần chọn retention dựa trên nhóm consumer chậm nhất, thời gian sự cố, nhu cầu replay và dung lượng Redis.

Không mặc định “message ACK rồi” có nghĩa có thể xóa ngay cho mọi group. Một stream có thể phục vụ nhiều group độc lập với tốc độ và PEL khác nhau.

## 15. Phương án tạo group ngay trong application

Có thể triển khai bước khởi tạo stream/group khi application bắt đầu. Tuy nhiên, phải xử lý đồng thời khi **nhiều instance khởi động cùng lúc**.

Một quy trình hợp lý:

```text
Application startup
   |
   +--> Kiểm tra kết nối Redis
   |
   +--> Ensure stream/group exists
   |       |
   |       +--> Chưa có: tạo group với offset đã chọn
   |       |
   |       +--> Đã có: giữ nguyên offset và PEL
   |       |
   |       +--> Lỗi quyền/mạng: báo lỗi, retry hoặc fail startup
   |
   +--> Đăng ký subscription
   |
   +--> Start container
```

Nếu dùng `StringRedisTemplate.opsForStream().createGroup(...)`, cần kiểm tra overload/method theo phiên bản Spring Data Redis và yêu cầu stream đã tồn tại hay chưa; `MKSTREAM` qua redis-cli cho phép tạo stream rỗng cùng group trong một lệnh.

Điều đặc biệt quan trọng: **không xóa và tạo lại group mỗi lần ứng dụng restart**. Làm vậy có thể mất PEL hoặc thay đổi vị trí phát message và phá hỏng khả năng recovery.

Trong hệ thống production, việc tạo group như một migration/deployment step được quản lý tập trung thường giúp kiểm soát offset khởi đầu và tránh race tạo group giữa các pod.

## 16. Khi nào nên dùng StreamMessageListenerContainer thay vì đọc thủ công?

| Bài toán | Phương án |
|---|---|
| Service liên tục xử lý sự kiện trên background thread | `StreamMessageListenerContainer` |
| Một tiến trình batch chạy vài phút rồi kết thúc | Có thể dùng `StreamOperations.read(...)` trực tiếp, tự quản lý cursor |
| Ứng dụng reactive end-to-end | Cân nhắc `StreamReceiver` và reactive Redis APIs |
| Cần manual ACK và consumer group | Container `receive(...)` + ACK + recovery |
| Cần xử lý message pending từ instance đã chết | Cần bổ sung `XPENDING`/`XAUTOCLAIM`/recovery flow |
| Cần replay stream theo ID lịch sử | Thiết kế riêng offset/group và retention |
| Cần broadcast tới nhiều hệ thống độc lập | Mỗi hệ thống một consumer group |
| Chỉ cần thông báo ephemeral không lưu lịch sử | Redis Pub/Sub có thể phù hợp hơn, nhưng không có PEL/replay |

Container giải quyết **cách lắng nghe**, không giải quyết đầy đủ mọi yêu cầu về lưu trữ, idempotency, retry và nghiệp vụ.

## 17. Quan sát và giám sát hệ thống stream

Một container “đang chạy” chưa chắc đang xử lý tốt. Có thể subscription còn active nhưng handler liên tục fail, hoặc executor bị thiếu thread.

Những metric nên có:

| Metric | Ý nghĩa |
|---|---|
| Consumer lag | Số message mới chưa được giao/được xử lý theo cách đo tương ứng |
| PEL size | Số message đã giao nhưng chưa ACK của group |
| Oldest pending idle | Pending lâu nhất, dấu hiệu consumer chết hoặc stuck |
| Processing latency | Thời gian từ nhận record đến khi nghiệp vụ hoàn tất |
| ACK latency | Thời gian đến khi xác nhận message thành công |
| Retry/reclaim count | Số lần message được xử lý lại |
| Poison/DLQ count | Message không thể xử lý theo hợp đồng |
| Polling errors | Lỗi Redis connectivity, permission hoặc deserialize |
| Executor active/queue | Mức sử dụng tài nguyên thread |
| Stream length | Số entry còn được giữ trong stream |
| Consumer last activity | Phân biệt consumer còn tồn tại và consumer đang thực sự nhận message |

Lưu ý, `XINFO GROUPS` có chỉ số `lag` trong những phiên bản Redis phù hợp, nhưng cách hiểu có thể bị ảnh hưởng bởi trimming, offset nhóm và cấu trúc stream. PEL size cũng không phải tổng số sự kiện chưa xử lý nghiệp vụ ở mọi điều kiện. Không quy toàn bộ sức khỏe hệ thống về một chỉ số.

Các lệnh thực hành:

```bash
redis-cli XINFO STREAM orders:events
redis-cli XINFO GROUPS orders:events
redis-cli XINFO CONSUMERS orders:events orders-workers
redis-cli XPENDING orders:events orders-workers
redis-cli XLEN orders:events
```

## 18. Những sự cố hay gặp

### 18.1. NOGROUP ngay khi container bắt đầu

**Hiện tượng:** listener không nhận message, Redis trả lỗi liên quan consumer group chưa tồn tại.

**Nguyên nhân:** container được start trước khi tạo group hoặc ứng dụng kết nối nhầm database/Redis instance.

**Hướng xử lý:** xác minh `XINFO GROUPS` và tạo group idempotent theo quy trình startup. Không tự ý reset group đang có message pending.

### 18.2. Container đăng ký đúng nhưng không có message

Kiểm tra:

- Container đã `start()` chưa?
- Subscription có được tạo trước khi khởi động chưa?
- Executor có thread rảnh cho polling task không?
- Stream key có đúng không?
- Group được tạo bằng `$` và chỉ có message cũ trước lúc tạo group?
- Message đã được group phân phối cho consumer khác?
- Message đang pending chứ không còn nằm ở nhóm entry mới?

Lệnh `XRANGE` chứng minh stream có entry; **không chứng minh group còn entry mới để nhận bằng `>`**.

### 18.3. Chỉ xử lý message mới, bỏ sót message trước đó

Nếu group được tạo với `$`, message đã tồn tại trước đó không được nhóm tự nhận như entry mới. Nếu consumer không dùng group và đặt `ReadOffset.latest()`, nó cũng có thể cố ý bỏ qua lịch sử.

Giải pháp phải dựa vào yêu cầu replay thực tế; đừng sửa offset production mà chưa kiểm tra retention và PEL.

### 18.4. Message pending tăng liên tục

Có thể handler lỗi nhưng không ACK; hoặc ACK bị lỗi, consumer chết, nghiệp vụ quá chậm, message poison. Kiểm tra `XPENDING`, event ID, delivery count và status của ứng dụng; triển khai reclaim/retry chứ không chỉ tăng batch size.

### 18.5. Message bị xử lý hai lần

Redis Streams consumer group không tự cam kết exactly-once nghiệp vụ. Process có thể hoàn tất DB rồi chết trước ACK; recovery giao lại message.

Thiết kế idempotency theo stream record ID hoặc business event ID, với unique constraint ở nguồn có thẩm quyền. Không dùng “đã thấy ID trong HashMap memory” làm bảo đảm sau restart.

### 18.6. Một subscription chiếm thread rất lâu

Blocking poll và callback được thực thi trên tài nguyên executor. Nếu executor quá nhỏ, một subscription bị chậm hoặc handler block có thể làm subscription khác không có thread.

Cần đo thời gian xử lý, kích thước pool, queue depth và số subscription. Thêm thread không giải quyết được downstream database bottleneck nếu mỗi message vẫn tạo transaction chậm.

### 18.7. Serializer không khớp giữa producer và consumer

Producer ghi Hash fields theo serializer nhị phân, nhưng listener mong `MapRecord<String,String,String>`. Có thể thấy key/value khác mong đợi hoặc lỗi decode.

Cần xác định contract field/value và cấu hình serializer ở cả hai phía. Không tự dùng `toString()` trên byte array rồi coi đó là JSON hợp lệ.

### 18.8. Không dừng container khi ứng dụng shutdown

Một task blocking còn giữ kết nối hoặc đang chạy handler có thể làm shutdown kéo dài, hoặc bị kill trước khi ACK. Cần gắn lifecycle và graceful shutdown với deployment.

### 18.9. Dùng cùng consumer name ở mọi pod

Redis xem các lời gọi có cùng tên là cùng consumer identity; pending ownership và metric khó tách theo instance. Cấu hình tên consumer duy nhất hoặc có chính sách cấp tên rõ ràng.

### 18.10. Tưởng rằng XACK đã xóa message

`XACK` xóa trạng thái pending đối với một group, nhưng entry có thể còn trong stream và các group khác vẫn cần nó. Dùng chính sách trim/retention riêng, không gắn xóa vật lý vào logic ACK tùy tiện.

## 19. Thực hành end-to-end trong môi trường thử nghiệm

### Bước 1 — Tạo stream/group

```bash
redis-cli XGROUP CREATE orders:events orders-workers 0-0 MKSTREAM
```

Nếu group đã có từ lần thực hành trước, không reset bừa; dùng tên stream/group mới hoặc kiểm soát dữ liệu thử nghiệm riêng.

### Bước 2 — Chạy ứng dụng

Đảm bảo container đã đăng ký subscription và start. Kiểm tra log ứng dụng có listener và không có `NOGROUP`/lỗi deserialize.

### Bước 3 — Gửi hai event

```bash
redis-cli XADD orders:events '*' eventType OrderCreated orderId 42 version 1
redis-cli XADD orders:events '*' eventType OrderPaid orderId 42 version 2
```

Ghi lại record ID Redis trả về ở mỗi lần `XADD`.

### Bước 4 — Quan sát listener và ACK

Khi handler xử lý thành công, kiểm tra:

```bash
redis-cli XPENDING orders:events orders-workers
redis-cli XINFO GROUPS orders:events
```

Nếu handler ACK đúng, các record đã xử lý không còn nằm trong PEL của group. Nhưng:

```bash
redis-cli XRANGE orders:events - +
```

vẫn có thể trả các entry đã ACK do chưa trim.

### Bước 5 — Gây lỗi xử lý có kiểm soát

Trong môi trường lab, cho handler ném exception trước ACK đối với một event cụ thể. Quan sát message pending, delivery count, lỗi listener và hoạt động subscription.

Tạo một recovery consumer riêng dùng `XAUTOCLAIM` khi idle threshold đủ lâu. Cho xử lý thành công và ACK. Kiểm tra tác động nghiệp vụ có bị lặp hay không khi event đã được xử lý một phần trước lúc lỗi.

### Bước 6 — Thử nhiều instance

Chạy hai instance với tên consumer khác nhau nhưng cùng group. Gửi nhiều event và quan sát thông qua `XINFO CONSUMERS` xem message được phân phối thế nào. Nếu muốn cả hai instance xử lý cùng mỗi event, hãy dùng **hai group riêng**, không phải hai consumer cùng group.

### Bước 7 — Kiểm tra shutdown

Dừng một instance khi đang có message xử lý chậm; quan sát pending còn lại, sau đó reclaim trên instance khác theo chính sách. Mục tiêu là xác nhận hệ thống có thể phục hồi sau sự cố thay vì chỉ chạy tốt khi không có lỗi.

## 20. Tự kiểm tra kiến thức

**1. Container có đọc Redis theo kiểu không blocking tuyệt đối không?**

Không. Container chạy vòng poll trong tác vụ nền của ứng dụng; các lệnh `XREAD`/`XREADGROUP` vẫn có thể dùng `BLOCK` trong khoảng `pollTimeout`.

**2. Cần gọi `start()` không?**

Cần đảm bảo container thực sự được khởi động, thông qua Spring lifecycle hoặc gọi tường minh, và được dừng khi shutdown. Chỉ `receive(...)` để đăng ký chưa đủ bảo đảm polling đang chạy.

**3. Vì sao group cần tồn tại trước khi đọc?**

`XREADGROUP` yêu cầu group đã được tạo; nếu không Redis có thể trả `NOGROUP`. Container không mặc nhiên thay thế bước tạo group.

**4. Khác biệt giữa group khởi tạo với `0-0` và `$` là gì?**

`0-0` cho phép group bắt đầu từ lịch sử stream; `$` đặt vị trí tại cuối hiện tại, thường bỏ qua các entry đã tồn tại trước khi group được tạo trong luồng đọc message mới.

**5. Tại sao `ReadOffset.lastConsumed()` không tự xử lý hết message pending sau crash?**

Vì đọc entry mới cho group khác với đọc những entry đã được giao và đang nằm trong PEL. Pending cần được theo dõi và reclaim/retry riêng.

**6. Khi nào nên gọi `XACK`?**

Với manual ACK và yêu cầu xử lý đáng tin cậy, ACK sau khi phần xử lý nghiệp vụ cần thiết đã hoàn tất. Nếu thất bại trước ACK, message còn cơ hội được xử lý lại qua recovery flow.

**7. ACK có xóa record khỏi stream không?**

Không. ACK xác nhận trạng thái của consumer group; muốn xóa/trim entry vật lý cần chính sách riêng.

**8. Consumer group có bảo đảm exactly-once business processing không?**

Không. Message có thể được giao lại khi process chết giữa lúc ghi nghiệp vụ và ACK; cần idempotency.

**9. Tăng batchSize có tự tăng khả năng xử lý của một callback chậm lên gấp nhiều lần không?**

Không. Batch size chủ yếu ảnh hưởng số entry yêu cầu một lần; throughput còn phụ thuộc handler, executor, Redis, database và số consumer.

**10. Nhiều ứng dụng cùng cần nhận mọi event thì dùng một group hay nhiều group?**

Thường là nhiều group độc lập; consumer trong cùng group chia nhau entry mới, không broadcast đầy đủ đến từng consumer.

## 21. Ghi nhớ khi triển khai production

- `StreamMessageListenerContainer` là thành phần polling nền, phù hợp làm bean có lifecycle rõ ràng, không tạo mới cho mỗi HTTP request.
- Khởi tạo stream/group idempotent trước khi `XREADGROUP`; chọn `0-0` hay `$` theo yêu cầu đọc lịch sử.
- Với consumer group, dùng `Consumer.from(group, consumerName)` và `ReadOffset.lastConsumed()` để nhận entry mới, nhưng **không quên PEL**.
- Cấu hình `pollTimeout`, `batchSize`, executor và serializers theo tải thực tế; đo throughput thay vì chỉ tăng thông số.
- Dùng manual `XACK` sau khi xử lý thành công khi cần retry đáng tin cậy; thiết kế idempotency cho message được giao lại.
- Có recovery flow cho pending bằng `XPENDING`/`XAUTOCLAIM`, idle threshold phù hợp và dead-letter cho poison message.
- Theo dõi subscription health, executor saturation, consumer lag, pending size, processing latency và Redis errors.
- Nhớ `XACK` không xóa entry vật lý; cấu hình retention/`XTRIM` theo mọi consumer group cùng dùng stream.
- Với nhiều instance, đặt consumer identity rõ ràng và lập kế hoạch graceful shutdown, crash recovery.
- Phân biệt container imperative với `StreamReceiver` reactive; chọn mô hình phù hợp kiến trúc ứng dụng.

**Cấu hình thành công không chỉ là listener nhận được một message.** Một hệ thống Redis Streams đáng tin cậy còn phải chứng minh nó khởi động đúng offset, không tự đánh mất pending, xử lý an toàn khi nhận trùng, quan sát được backlog và có khả năng phục hồi sau lỗi Redis hoặc restart.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): stream records, consumer group, StreamMessageListenerContainer và offset semantics.
- [Spring Data Redis — StreamMessageListenerContainer API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/stream/StreamMessageListenerContainer.html): đăng ký listener và lifecycle.
- [Spring Data Redis — StreamMessageListenerContainerOptions API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/stream/StreamMessageListenerContainer.StreamMessageListenerContainerOptions.html): các tùy chọn polling và deserialization.
- [Redis — Streams Introduction](https://redis.io/docs/latest/develop/data-types/streams/): mô hình Redis Stream và consumer group.
- [Redis — XGROUP CREATE](https://redis.io/docs/latest/commands/xgroup-create/): tạo group và lựa chọn ID khởi đầu.
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/): đọc trong consumer group, BLOCK, COUNT và pending.
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/): xác nhận record của consumer group.
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/): quan sát Pending Entries List.
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/): thu hồi pending message đủ idle.
- [Redis — XTRIM](https://redis.io/docs/latest/commands/xtrim/): giới hạn độ dài stream theo retention policy.
