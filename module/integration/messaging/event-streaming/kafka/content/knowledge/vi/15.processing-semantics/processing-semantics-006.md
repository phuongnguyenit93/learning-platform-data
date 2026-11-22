# Giữ thứ tự theo thực thể khi có nhiều bước xử lý

Trong hệ thống event-driven, một thực thể nghiệp vụ thường trải qua nhiều bước: đơn hàng được tạo, thanh toán được xác nhận, tồn kho được giữ chỗ rồi vận chuyển được khởi tạo. Các bước này phải được xử lý theo đúng thứ tự của thực thể. Nếu sự kiện bước sau đến trước, service có thể chuyển trạng thái sai, ghi đè dữ liệu mới bằng dữ liệu cũ hoặc phát sinh side effect không hợp lệ.

Kafka bảo đảm thứ tự record trong từng partition. Để tận dụng bảo đảm đó, producer cần dùng một key ổn định đại diện cho thực thể, chẳng hạn orderId, để các sự kiện của cùng đơn hàng đi vào cùng partition. Consumer cũng phải xử lý tuần tự theo partition hoặc thiết kế cơ chế tuần tự theo key nếu chuyển công việc sang worker pool.

Tuy vậy, partition ordering chỉ giải quyết thứ tự trong log. Nó không tự sắp xếp các sự kiện được nhiều thread hoặc nhiều service phát ra sai thứ tự, không bảo đảm thứ tự hoàn thành khi consumer xử lý bất đồng bộ và không tạo thứ tự tổng thể giữa nhiều topic. Với quy trình nhiều bước, nên kết hợp key ổn định, sequence/version của aggregate, idempotency, retry có kiểm soát và transactional outbox.

## 1. Thứ tự trong Kafka được bảo đảm ở phạm vi nào?

Kafka lưu record trong một partition theo thứ tự append. Mỗi record được gán offset trong partition đó. Consumer đọc record theo thứ tự offset khi đọc tuần tự partition.

Ví dụ topic order-events có ba partition:

~~~text
order-events
  partition 0: offset 0, 1, 2, 3, ...
  partition 1: offset 0, 1, 2, 3, ...
  partition 2: offset 0, 1, 2, 3, ...
~~~

Kafka có thể bảo đảm thứ tự trong partition 0, trong partition 1 và trong partition 2. Kafka không tạo thứ tự tổng thể giữa ba partition.

Nếu hai sự kiện nằm ở hai partition khác nhau:

~~~text
partition 0: OrderCreated(order-42)
partition 2: PaymentAuthorized(order-42)
~~~

Consumer có thể nhận hoặc xử lý chúng theo lịch trình khác nhau. Không thể suy ra sự kiện nào xảy ra trước chỉ bằng cách so sánh offset vì offset chỉ có ý nghĩa trong partition của nó.

### 1.1. Thứ tự log và thứ tự nghiệp vụ là hai khái niệm khác nhau

- **Thứ tự log:** thứ tự record được append vào cùng một partition và biểu diễn bằng offset.
- **Thứ tự phát sự kiện:** thứ tự mà producer hoặc service quyết định gửi event.
- **Thứ tự xử lý:** thứ tự consumer bắt đầu xử lý record.
- **Thứ tự hoàn thành:** thứ tự các tác vụ xử lý kết thúc.
- **Thứ tự nghiệp vụ:** thứ tự chuyển trạng thái hợp lệ của một thực thể.

Kafka trực tiếp duy trì thứ tự log trong partition. Ứng dụng phải thiết kế để thứ tự phát, xử lý và hoàn thành phù hợp với quy tắc nghiệp vụ.

Ví dụ, một consumer có thể đọc OrderCreated trước PaymentAuthorized, nhưng nếu đẩy hai record sang hai worker độc lập thì worker xử lý PaymentAuthorized có thể hoàn tất trước. Khi đó log vẫn đúng thứ tự nhưng trạng thái downstream có thể sai.

## 2. Xác định thực thể cần giữ thứ tự

Trước khi cấu hình Kafka, cần xác định đơn vị nghiệp vụ nào cần có thứ tự.

| Quy trình | Entity key | Các bước cần giữ thứ tự |
|---|---|---|
| Đơn hàng | orderId | Created → Paid → Packed → Shipped |
| Tài khoản | accountId | Opened → Deposited → Withdrawn → Closed |
| Đặt chỗ | bookingId | Requested → Confirmed → CheckedIn → Completed |
| Hàng tồn kho | sku hoặc warehouseId + sku | Received → Reserved → Released → Shipped |
| Hồ sơ khách hàng | customerId | Created → Updated → Suspended |

Entity key phải phản ánh đúng phạm vi trạng thái được tuần tự hóa. Nếu tồn kho được quản lý độc lập theo kho và SKU, chỉ dùng SKU có thể gom nhiều kho vào cùng một luồng; dùng warehouseId + sku có thể phù hợp hơn.

Một topic có thể chứa nhiều loại event, nhưng các event cùng aggregate nên dùng cùng key và cùng quy tắc partitioning. Nếu mỗi loại event dùng một key khác nhau, chúng có thể đi vào các partition khác nhau và mất bảo đảm thứ tự theo thực thể.

## 3. Dùng key ổn định để đưa event cùng thực thể vào một partition

Với producer Java, record có key khác null thường được partitioner mặc định định tuyến dựa trên key đã serialize. Các record có cùng key bytes và cùng partitioning configuration sẽ đi về cùng partition.

Ví dụ:

~~~java
ProducerRecord<String, OrderEvent> record =
    new ProducerRecord<>(
        "order-events",
        event.orderId(),
        event
    );

producer.send(record);
~~~

Với orderId = "order-42", các event của cùng đơn hàng dùng cùng key:

~~~text
key=order-42  OrderCreated
key=order-42  PaymentAuthorized
key=order-42  InventoryReserved
key=order-42  ShipmentCreated
~~~

Nếu partition count và partitioner không thay đổi, các record đó được định tuyến về cùng partition. Kafka sẽ lưu chúng theo thứ tự producer append vào partition.

### 3.1. Key phải ổn định và không null

Không dùng các giá trị ngẫu nhiên như UUID mới cho mỗi event làm key nếu mục tiêu là gom sự kiện theo thực thể. Những key khác nhau có thể đưa các bước của cùng đơn hàng vào các partition khác nhau.

Không nên bỏ key khi cần ordering theo entity. Với key null, partitioner có thể phân phối record theo chiến lược sticky hoặc round-robin tùy client và cấu hình; không có bảo đảm các event của cùng thực thể sẽ cùng partition.

Key nên có các đặc điểm:

- Đại diện cho đúng aggregate hoặc entity cần tuần tự hóa.
- Có giá trị ổn định trong suốt vòng đời entity.
- Được serialize nhất quán ở mọi producer.
- Không thay đổi định dạng giữa các service nếu không có kế hoạch migration.
- Không chứa dữ liệu nhạy cảm nếu key xuất hiện trong log, metric hoặc công cụ quản trị.

### 3.2. Không nhầm key với event ID

orderId xác định thực thể và giúp định tuyến partition. eventId xác định duy nhất một sự kiện để deduplicate.

Ví dụ envelope:

~~~java
public record OrderEvent(
    String eventId,
    String orderId,
    long aggregateVersion,
    String eventType,
    String payload
) {}
~~~

Khi publish:

~~~java
OrderEvent event = new OrderEvent(
    "evt-1002",
    "order-42",
    2L,
    "PaymentAuthorized",
    "{\"amount\":125000}"
);

ProducerRecord<String, OrderEvent> record =
    new ProducerRecord<>(
        "order-events",
        event.orderId(),
        event
    );

record.headers().add(
    "event-type",
    event.eventType().getBytes(StandardCharsets.UTF_8)
);

producer.send(record);
~~~

orderId là key định tuyến; eventId là khóa nhận diện lần phát; aggregateVersion thể hiện thứ tự logic của trạng thái aggregate. Ba trường phục vụ ba mục đích khác nhau.

## 4. Partition count và thay đổi mapping của key

Key-based partitioning chỉ có tác dụng khi các producer dùng cùng quy tắc partitioning và partition count phù hợp.

Với partitioner mặc định, key được hash rồi ánh xạ vào số partition hiện tại. Nếu tăng partition count, cùng một key có thể được ánh xạ sang partition khác. Những event cũ của entity vẫn nằm ở partition cũ, còn event mới có thể đi vào partition mới.

Ví dụ:

~~~text
Trước khi tăng partition:
  order-42 -> partition 1
  OrderCreated        -> P1
  PaymentAuthorized   -> P1

Sau khi tăng partition count:
  order-42 -> partition 4
  ShipmentCreated     -> P4
~~~

Consumer có thể xử lý partition 4 trước khi hoàn tất các event còn lại ở partition 1. Vì vậy, thay đổi partition count có thể phá vỡ giả định thứ tự theo entity qua thời điểm thay đổi.

Khi topic đã chứa dữ liệu nghiệp vụ cần thứ tự lâu dài:

- Lập kế hoạch partition count ngay từ đầu theo tải dự kiến.
- Không tăng partition tùy tiện trong lúc workflow đang chạy.
- Nếu cần mở rộng, dùng aggregate version để phát hiện event đến sai thứ tự.
- Có thể tạo topic version mới và migration có kiểm soát.
- Không giả định Kafka tự di chuyển record cũ sang partition mới.

Custom partitioner cũng phải nhất quán giữa các producer. Một service dùng orderId, service khác dùng customerId hoặc cách serialize key khác sẽ không giữ cùng partition mapping.

## 5. Thứ tự ở producer: đừng để nhiều thread quyết định sai trình tự

KafkaProducer thread-safe, nên nhiều thread có thể gọi send() trên cùng instance. Tuy nhiên, thread safety không có nghĩa Kafka biết thứ tự nghiệp vụ mong muốn giữa các thread.

Giả sử hai thread cùng phát sự kiện cho một đơn hàng:

~~~text
Thread A: phát OrderCreated (version 1)
Thread B: phát PaymentAuthorized (version 2)

Do scheduling:
  Thread B gọi send trước
  Thread A gọi send sau
~~~

Nếu producer append theo thứ tự lời gọi thực tế, partition có thể lưu version 2 trước version 1. Key giống nhau chỉ đưa hai record về cùng partition; nó không tự sắp xếp lại theo aggregateVersion.

Cách xử lý:

- Tuần tự hóa việc phát event theo aggregate ID.
- Chỉ phát bước tiếp theo sau khi bước trước đã được commit vào nguồn dữ liệu và sẵn sàng publish.
- Gán version tăng đơn điệu trong transaction cập nhật aggregate.
- Dùng outbox để lưu event cùng transaction với thay đổi trạng thái.
- Tránh để nhiều service cùng phát event cho một aggregate mà không có cơ chế phân quyền hoặc sequence rõ ràng.

### 5.1. Idempotent producer không sắp xếp nghiệp vụ

enable.idempotence=true giúp Kafka producer tránh duplicate do retry trong phạm vi producer session theo cơ chế sequence number của Kafka. Nó cũng duy trì thứ tự batch khi retry theo các giới hạn của client hiện đại.

Idempotence không giải quyết các trường hợp:

- Hai thread tạo lệnh gửi theo thứ tự sai.
- Hai producer instance độc lập phát event cùng entity.
- Hai service phát event mà không có coordination.
- Outbox relay lấy event version mới trước version cũ.
- Consumer xử lý song song và hoàn thành sai thứ tự.

Idempotence là bảo vệ ở tầng ghi Kafka; sequence/version và quy trình phát event vẫn phải được thiết kế ở tầng nghiệp vụ.

### 5.2. Không dùng timestamp để thay thế sequence

Timestamp có thể bị lệch do đồng hồ máy, event bị gửi trễ hoặc retry. Hai event có timestamp giống nhau cũng không cho biết thứ tự nghiệp vụ.

Với một aggregate, dùng số version hoặc sequence tăng dần:

~~~text
orderId=order-42
version=1  OrderCreated
version=2  PaymentAuthorized
version=3  InventoryReserved
version=4  ShipmentCreated
~~~

Consumer có thể kiểm tra version để phát hiện duplicate, stale event hoặc gap.

## 6. Xử lý tuần tự ở consumer

Nếu consumer xử lý đồng bộ trong poll loop, các record của cùng partition được xử lý theo thứ tự mà client trả về. Đây là cách đơn giản nhất để giữ ordering.

Ví dụ KafkaConsumer thuần:

~~~java
while (running) {
    ConsumerRecords<String, OrderEvent> records =
        consumer.poll(Duration.ofMillis(500));

    for (ConsumerRecord<String, OrderEvent> record : records) {
        orderHandler.handle(record.key(), record.value());
    }

    consumer.commitSync();
}
~~~

Với cách xử lý này:

- Một poll thread duyệt record tuần tự.
- Các record trong cùng partition được xử lý theo thứ tự offset.
- Các partition khác nhau có thể xen kẽ trong cùng batch.
- Nếu handler chậm, poll loop có thể bị chậm và cần tính đến max.poll.interval.ms.
- Nếu một record lỗi và không được xử lý, cần chính sách retry/commit phù hợp.

Đoạn mã chỉ minh họa trình tự cơ bản. Trong production, cần tắt auto commit nếu tự quản lý commit, xử lý exception theo từng record và chỉ commit offset liên tục đã xử lý thành công.

### 6.1. Một partition được gán cho tối đa một member trong group

Trong cùng consumer group, một partition tại một thời điểm chỉ được gán cho tối đa một consumer member. Điều này cho phép consumer xử lý tuần tự partition mà không có hai member cùng đọc và commit tiến độ của partition đó.

Nếu group có nhiều consumer hơn số partition, consumer dư không nhận partition. Nếu một consumer nhận nhiều partition, nó vẫn phải quản lý tiến độ riêng của từng partition.

### 6.2. Spring Kafka với listener đồng bộ

Ví dụ:

~~~java
@Component
public class OrderEventListener {

    private final OrderWorkflow workflow;

    public OrderEventListener(OrderWorkflow workflow) {
        this.workflow = workflow;
    }

    @KafkaListener(
        topics = "order-events",
        groupId = "order-workflow"
    )
    public void consume(
            ConsumerRecord<String, OrderEvent> record) {

        workflow.apply(
            record.key(),
            record.value()
        );
    }
}
~~~

Với listener đồng bộ tiêu chuẩn, container gọi listener trên consumer thread. Các record của một partition được giao cho cùng consumer member và callback được xử lý tuần tự trên thread đó.

Nếu tăng concurrency, Spring Kafka tạo nhiều consumer instance để xử lý các partition khác nhau. Một partition vẫn không được chia cho hai consumer member trong cùng group tại cùng thời điểm.

## 7. Concurrency trong ứng dụng có thể phá vỡ thứ tự

Một lỗi thường gặp là đọc record theo thứ tự rồi chuyển mỗi record sang thread pool:

~~~java
for (ConsumerRecord<String, OrderEvent> record : records) {
    executor.submit(() -> workflow.apply(record.value()));
}
~~~

Đoạn mã trên không bảo đảm thứ tự hoàn thành. Worker có thể xử lý version 2 nhanh hơn version 1 dù poll trả version 1 trước.

Ví dụ:

~~~text
Poll trả:
  version 1 -> task A
  version 2 -> task B

Worker:
  task B hoàn tất trước
  task A hoàn tất sau

Trạng thái có thể bị ghi:
  version 2
  rồi bị ghi đè bởi version 1
~~~

Nếu công việc có side effect như trừ tiền, giữ tồn kho hoặc cập nhật trạng thái đơn hàng, việc hoàn thành sai thứ tự có thể gây lỗi nghiệp vụ nghiêm trọng.

Có ba lựa chọn thường dùng:

1. Xử lý đồng bộ tuần tự theo partition.
2. Dùng worker lane tuần tự theo key hoặc partition.
3. Cho phép xử lý song song nhưng dùng version check và state transition có điều kiện để ngăn event cũ ghi đè event mới.

Lựa chọn phù hợp tùy yêu cầu throughput và mức độ phức tạp có thể chấp nhận.

## 8. Tuần tự hóa theo key khi cần worker pool

Nếu một consumer nhận nhiều partition và cần tận dụng worker pool, có thể gửi các event của cùng key vào cùng một lane tuần tự. Các key khác nhau vẫn có thể xử lý đồng thời.

Một mô hình đơn giản là chia worker thành các stripe:

~~~text
order-42 -> stripe 2 -> task 1 -> task 2 -> task 3
order-57 -> stripe 1 -> task 1 -> task 2
order-91 -> stripe 2 -> task 1
~~~

Mỗi stripe có một worker tuần tự. Các key hash vào cùng stripe được xử lý theo thứ tự enqueue. Va chạm giữa hai key khác nhau chỉ làm giảm concurrency, không làm sai thứ tự của cùng key nếu việc enqueue cũng tuần tự.

Pseudo-code:

~~~java
int stripeCount = 8;

ExecutorService[] stripes = new ExecutorService[stripeCount];

for (int i = 0; i < stripeCount; i++) {
    stripes[i] = new ThreadPoolExecutor(
        1,
        1,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(500),
        new ThreadPoolExecutor.AbortPolicy()
    );
}

void dispatch(ConsumerRecord<String, OrderEvent> record) {
    String entityKey = record.key();

    if (entityKey == null) {
        throw new IllegalArgumentException(
            "Entity key is required for ordered processing"
        );
    }

    int stripe = Math.floorMod(entityKey.hashCode(), stripeCount);

    stripes[stripe].execute(() ->
        workflow.apply(entityKey, record.value())
    );
}
~~~

Đây là khung minh họa, không phải consumer hoàn chỉnh. Cần bổ sung shutdown, xử lý rejection, bounded queue backpressure, exception reporting và completion tracking theo partition.

### 8.1. Thứ tự enqueue phải được giữ

Stripe chỉ giữ thứ tự mà task được enqueue. Nếu nhiều poll thread hoặc nhiều process cùng dispatch event của một entity, thứ tự enqueue vẫn có thể sai. Vì vậy, cần bảo đảm một entity được đọc theo một nguồn thứ tự duy nhất hoặc kiểm tra version trong tầng xử lý.

### 8.2. Không commit ngay sau khi enqueue

Việc task được đưa vào queue không có nghĩa nghiệp vụ đã xử lý xong. Nếu consumer commit offset ngay sau enqueue rồi process chết, Kafka sẽ không giao lại các record đó theo tiến độ đã commit.

Cần theo dõi completion theo từng partition và chỉ commit offset tiếp theo sau record cuối cùng đã hoàn tất liên tục. Nếu offset 10 chưa xong nhưng offset 11 đã xong, không commit qua 10.

Nếu worker queue đầy, áp dụng pause/resume hoặc backpressure. Không được bỏ task và tiếp tục commit.

### 8.3. Version check vẫn cần thiết

Stripe bảo vệ thứ tự trong một process và một luồng dispatch. Nó không bảo vệ trước:

- Producer khác phát event cũ muộn.
- Retry topic làm event đến trễ.
- Rebalance khi worker cũ chưa dừng.
- Partition mapping thay đổi sau khi tăng partition count.
- Hai service cùng cập nhật một aggregate.

Dùng aggregate version và optimistic locking để bảo vệ state ở nơi lưu trữ cuối cùng.

## 9. Aggregate version và state transition có điều kiện

Mỗi aggregate nên có version tăng dần sau mỗi thay đổi trạng thái thành công.

Ví dụ:

| Version | Event | Trạng thái sau bước |
|---:|---|---|
| 1 | OrderCreated | CREATED |
| 2 | PaymentAuthorized | PAID |
| 3 | InventoryReserved | RESERVED |
| 4 | ShipmentCreated | SHIPPED |

Consumer lưu version đã áp dụng. Khi nhận event:

- Nếu event.version == currentVersion + 1, có thể áp dụng bước tiếp theo.
- Nếu event.version <= currentVersion, event có thể là duplicate hoặc stale; kiểm tra event ID và chính sách deduplication.
- Nếu event.version > currentVersion + 1, có gap; cần chờ, replay hoặc điều tra event bị thiếu.

Ví dụ:

~~~java
public void apply(OrderEvent event) {
    OrderState current = repository.findById(event.orderId());

    if (event.aggregateVersion() <= current.version()) {
        // Duplicate hoặc event cũ; kiểm tra eventId nếu cần.
        return;
    }

    if (event.aggregateVersion() != current.version() + 1) {
        throw new OutOfOrderEventException(
            event.orderId(),
            current.version(),
            event.aggregateVersion()
        );
    }

    OrderState next = stateMachine.apply(current, event);

    repository.saveWithExpectedVersion(
        next,
        current.version()
    );
}
~~~

saveWithExpectedVersion cần được thực hiện bằng optimistic locking hoặc câu lệnh update có điều kiện trong transaction database. Không chỉ đọc version rồi ghi lại bằng hai thao tác tách rời, vì hai consumer hoặc hai process có thể cùng đọc một version và ghi đè lẫn nhau.

### 9.1. Phân biệt duplicate với gap

Giả sử current version là 3:

- Nhận version 3 lần nữa: có thể là duplicate.
- Nhận version 2: event cũ hoặc replay.
- Nhận version 4: đúng bước tiếp theo.
- Nhận version 6: thiếu version 4 hoặc 5, không nên áp dụng ngay.

Version giúp phát hiện sai thứ tự, nhưng ứng dụng vẫn phải quyết định cách khôi phục gap. Có thể retry có giới hạn, truy vấn event store, yêu cầu replay hoặc đưa entity vào trạng thái chờ xử lý.

### 9.2. Inbox và idempotency

Consumer có thể lưu eventId vào bảng inbox với unique constraint:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong cùng transaction database:

1. Insert event ID vào inbox.
2. Nếu unique constraint báo đã tồn tại, xem là duplicate và bỏ qua side effect.
3. Kiểm tra aggregate version.
4. Cập nhật trạng thái nghiệp vụ.
5. Commit transaction.

Cách này giúp xử lý lặp an toàn khi Kafka giao lại record sau crash hoặc consumer restart. Inbox không tự tạo exactly-once giữa Kafka và database; nó giúp làm side effect database idempotent.

## 10. Retry có thể làm sai thứ tự như thế nào?

Retry là một trong những nguyên nhân khiến event bước sau vượt qua event bước trước.

Giả sử cùng partition có:

~~~text
offset 100: OrderCreated(version 1)
offset 101: PaymentAuthorized(version 2)
offset 102: InventoryReserved(version 3)
~~~

Nếu version 1 lỗi tạm thời:

- **Blocking retry:** consumer chưa xử lý tiếp record sau cho đến khi version 1 được xử lý hoặc được đưa vào chính sách recovery. Thứ tự partition được giữ, nhưng partition có thể bị chặn.
- **Non-blocking retry topic:** version 1 được chuyển sang retry topic; main topic tiếp tục với version 2 và 3. Event bước sau có thể được xử lý trước version 1.
- **DLT:** record lỗi được chuyển sang dead-letter topic để điều tra hoặc replay sau; những record sau có thể đã được xử lý.

### 10.1. Blocking retry

Blocking retry giữ record lỗi trong luồng xử lý hiện tại và retry trước khi tiến đến record tiếp theo theo cách triển khai. Nó phù hợp khi thứ tự theo partition/entity quan trọng hơn khả năng bỏ qua record lỗi.

Nhược điểm:

- Một record lỗi có thể chặn toàn partition.
- Downstream lỗi kéo dài có thể làm poll chậm và gây rebalance.
- Retry/backoff phải nằm trong giới hạn vận hành.
- Cần DLT hoặc quy trình dừng sau số lần retry nhất định.

Không nên retry vô hạn trong poll thread.

### 10.2. Non-blocking retry và retry topic

Spring Kafka hỗ trợ retry topic, ví dụ bằng @RetryableTopic. Record lỗi được publish sang topic retry có delay; listener trên main topic có thể tiếp tục các record sau.

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1000,
        multiplier = 2.0
    )
)
@KafkaListener(
    topics = "order-events",
    groupId = "order-workflow"
)
public void consume(OrderEvent event) {
    workflow.apply(event);
}
~~~

Đây là ví dụ khái quát; cần cấu hình retry topic, DLT, serializer và error handler phù hợp phiên bản Spring Kafka.

Non-blocking retry có thể làm sai thứ tự theo entity. Nếu OrderCreated(version 1) đang ở retry topic nhưng PaymentAuthorized(version 2) tiếp tục trên main topic, version 2 có thể đến database trước version 1.

Chỉ dùng retry topic khi:
- Nghiệp vụ chấp nhận event đến trễ.
- Consumer kiểm tra aggregate version và xử lý gap.
- Hoặc có cơ chế khóa/hold các event sau của cùng entity cho đến khi event lỗi hoàn tất.

### 10.3. Cô lập lỗi theo entity

Nếu muốn các entity khác tiếp tục nhưng một entity phải giữ đúng thứ tự, có thể thiết kế tầng xử lý:

- Đánh dấu entity đang bị blocked tại version lỗi.
- Các event sau của cùng entity được giữ lại hoặc retry, không áp dụng vượt version.
- Event của entity khác tiếp tục xử lý.
- Khi event lỗi được phục hồi, tiếp tục version tiếp theo.

Cách này phức tạp hơn retry theo partition nhưng giảm ảnh hưởng của một entity lỗi lên toàn bộ partition. Trạng thái blocked phải được lưu bền vững để không mất khi consumer restart.

## 11. Transactional outbox để phát event đúng thứ tự từ database

Một service thường vừa cập nhật database vừa publish Kafka. Nếu cập nhật database thành công nhưng publish thất bại, trạng thái database và event stream không đồng bộ. Nếu publish trước rồi database rollback, consumer có thể nhận event của một thay đổi chưa được commit.

Transactional outbox giải quyết ranh giới này bằng cách ghi thay đổi nghiệp vụ và outbox event trong cùng một transaction database.

~~~mermaid
flowchart TD
    A["Service nhận lệnh"] --> B["Database transaction"]
    B --> C["Update aggregate + tăng version"]
    B --> D["Insert outbox event cùng version"]
    C --> E["Commit database"]
    D --> E
    E --> F["Outbox relay đọc event chưa publish"]
    F --> G["Kafka Producer: key = aggregateId"]
    G --> H["Topic partition theo aggregate"]
    H --> I["Consumer kiểm tra eventId và version"]
~~~

Ví dụ bảng outbox:

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL,
    UNIQUE (aggregate_id, aggregate_version)
);
~~~

Trong transaction nghiệp vụ:

1. Lock hoặc cập nhật aggregate với optimistic version.
2. Tăng aggregate version.
3. Ghi outbox event cùng version.
4. Commit cả hai thay đổi trong một transaction.

Relay đọc outbox và publish với key là aggregate ID. Khi publish thành công, relay đánh dấu event đã gửi theo cơ chế phù hợp.

### 11.1. Relay cũng phải giữ thứ tự

Transactional outbox bảo đảm event không bị tách khỏi transaction database, nhưng không tự bảo đảm relay publish đúng thứ tự nếu nhiều worker đọc cùng aggregate song song.

Cần:

- Đọc event theo aggregate_id, aggregate_version.
- Chỉ publish version tiếp theo khi version trước đã được xử lý gửi theo chính sách.
- Phân công một aggregate cho một relay lane hoặc shard tại một thời điểm.
- Dùng key aggregate ID khi publish Kafka.
- Có cơ chế lease/claim để tránh hai relay cùng xử lý một aggregate.
- Chịu được trường hợp publish thành công nhưng relay chưa kịp đánh dấu published_at.

Trường hợp publish thành công nhưng cập nhật trạng thái outbox thất bại có thể khiến relay gửi lại. Vì vậy, consumer vẫn cần deduplicate theo eventId và kiểm tra version. Outbox cung cấp reliable publication, còn idempotent consumer bảo vệ side effect.

## 12. Nhiều topic không có thứ tự tổng thể

Một workflow có thể phát các event vào nhiều topic:

~~~text
order-events:
  OrderCreated(order-42)

payment-events:
  PaymentAuthorized(order-42)

inventory-events:
  InventoryReserved(order-42)
~~~

Dù các record cùng dùng key order-42, chúng nằm trong các topic khác nhau. Mỗi topic có partition log riêng và offset riêng. Kafka không bảo đảm thứ tự tổng thể giữa các topic.

Nếu cần một thứ tự event stream theo aggregate, có thể:

- Dùng một topic aggregate events chứa nhiều event type.
- Dùng aggregate version để consumer xác minh thứ tự.
- Gắn correlationId, causationId và version để theo dõi workflow.
- Dùng state machine ở service điều phối để chỉ cho phép bước tiếp theo sau khi bước trước hoàn tất.

Kafka transaction có thể commit nguyên tử nhiều record trên nhiều partition/topic khi consumer đọc read_committed, nhưng tính nguyên tử không tạo ra thứ tự tổng thể giữa các partition. Consumer vẫn cần hiểu quan hệ nghiệp vụ giữa các event.

## 13. Dùng Kafka Streams để xử lý theo key

Kafka Streams tổ chức xử lý theo task gắn với partition. Khi dữ liệu được partition theo key, các record cùng key có thể được xử lý trong cùng task theo thứ tự partition.

Ví dụ:

~~~java
StreamsBuilder builder = new StreamsBuilder();

KStream<String, OrderEvent> events =
    builder.stream("order-events");

KStream<String, OrderEvent> keyed =
    events.selectKey((oldKey, event) -> event.orderId());

KStream<String, OrderEvent> ordered =
    keyed.repartition(
        Repartitioned.<String, OrderEvent>as("orders-by-id")
            .withKeySerde(Serdes.String())
            .withValueSerde(orderEventSerde)
    );

ordered.processValues(
    () -> new OrderStateProcessor()
);

builder.build();
~~~

Ví dụ minh họa việc đổi key sang orderId rồi repartition để các event cùng đơn hàng đi cùng partition trước khi xử lý stateful. Cần định nghĩa serde và processor thực tế theo ứng dụng.

### 13.1. Khi nào cần repartition?

Nếu key ban đầu không phải entity ID hoặc đã thay đổi key trong topology, các record cùng entity có thể đang ở các partition khác nhau. selectKey() chỉ thay key trong record stream; khi thao tác sau cần grouping/stateful processing theo key, Kafka Streams có thể yêu cầu repartition. Có thể khai báo repartition() tường minh để dễ quan sát topology.

Repartition topic tạo một luồng mới được partition theo key mới. Sau đó các thao tác theo key được thực hiện dựa trên partition mapping mới.

### 13.2. State store và thứ tự theo key

Kafka Streams state store thường được partition theo cùng key với input. Một task xử lý dữ liệu của các partition được giao cho task đó. Record cùng key đi cùng partition nên state của entity được cập nhật theo thứ tự record trong partition.

Nếu topology có nhiều nhánh, join hoặc nhiều topic đầu vào, cần hiểu semantics của join window, timestamp và repartition. Kafka Streams không tự tạo thứ tự nghiệp vụ giữa các input topic độc lập.

### 13.3. Exactly-once không đồng nghĩa thứ tự toàn cục

Kafka Streams có thể dùng exactly-once processing để phối hợp output, state store changelog và offset trong transaction Kafka. Điều đó bảo vệ tính nhất quán của processing trong phạm vi Kafka Streams, nhưng không tạo thứ tự toàn cục giữa nhiều partition hoặc tự bảo vệ database/HTTP side effect bên ngoài.

## 14. Xử lý event đến sai thứ tự bằng state machine

Với quy trình nhiều bước, nên định nghĩa các trạng thái và chuyển trạng thái hợp lệ.

Ví dụ order workflow:

~~~text
CREATED
   |
   v
PAID
   |
   v
INVENTORY_RESERVED
   |
   v
SHIPPED
   |
   v
COMPLETED
~~~

Nếu nhận ShipmentCreated khi order chưa ở INVENTORY_RESERVED, consumer không nên tự động chuyển sang SHIPPED nếu nghiệp vụ yêu cầu giữ đúng quy trình.

State machine có thể kiểm tra:

| Event | Trạng thái hiện tại hợp lệ | Trạng thái mới |
|---|---|---|
| OrderCreated | Không tồn tại | CREATED |
| PaymentAuthorized | CREATED | PAID |
| InventoryReserved | PAID | INVENTORY_RESERVED |
| ShipmentCreated | INVENTORY_RESERVED | SHIPPED |
| OrderCompleted | SHIPPED | COMPLETED |

Khi event không hợp lệ:
- Nếu version bị thiếu, chờ event trước hoặc replay.
- Nếu event duplicate, deduplicate.
- Nếu chuyển trạng thái không hợp lệ, cách ly và điều tra.
- Nếu event stale, không ghi đè trạng thái mới hơn.
- Nếu workflow bị hủy, phát event hủy theo state transition được định nghĩa.

State machine và aggregate version là lớp bảo vệ cuối cùng khi partition ordering không đủ hoặc dữ liệu đến từ nhiều nguồn.

## 15. Quan sát và chẩn đoán vấn đề ordering

Khi trạng thái entity sai thứ tự, cần truy vết theo entity key và version, không chỉ nhìn consumer lag tổng thể.

Nên ghi log các trường:

~~~text
topic=order-events
partition=2
offset=105
key=order-42
eventId=evt-1002
aggregateVersion=2
eventType=PaymentAuthorized
consumerGroup=order-workflow
traceId=trace-abc
~~~

Các chỉ số và dấu hiệu cần theo dõi:

| Dấu hiệu | Nguyên nhân có thể |
|---|---|
| Version gap tăng | Event bị thiếu, retry topic làm đảo thứ tự hoặc producer publish sai trình tự |
| Stale event tăng | Duplicate, replay hoặc producer cũ gửi event muộn |
| Cùng entity xuất hiện ở nhiều partition | Key/partitioner không thống nhất hoặc partition count đã thay đổi |
| Consumer lag cao ở một partition | Hot key hoặc một entity có lưu lượng lớn |
| Retry topic lag tăng | Downstream lỗi hoặc retry delay quá dài |
| Outbox version gap | Relay publish không tuần tự hoặc transaction tạo event có lỗi |
| Duplicate event ID | Retry publish, relay crash sau publish hoặc consumer replay |
| State transition bị từ chối | Event đến sai thứ tự hoặc workflow state không hợp lệ |

Có thể truy vấn log theo aggregateId để dựng lại lịch sử event và đối chiếu version. Không dùng timestamp đơn lẻ để kết luận thứ tự nếu hệ thống có nhiều producer hoặc đồng hồ không đồng bộ.

## 16. Quy trình thiết kế giữ thứ tự cho một workflow

Khi xây dựng workflow mới, có thể đi theo trình tự:

1. Xác định aggregate/entity cần giữ thứ tự.
2. Chọn key ổn định đại diện cho aggregate.
3. Định nghĩa aggregate version tăng đơn điệu.
4. Bảo đảm mọi producer dùng cùng key và partitioning rule.
5. Tránh nhiều thread phát event cùng aggregate mà không serialize.
6. Dùng transactional outbox nếu database và Kafka phải nhất quán.
7. Consumer xử lý tuần tự theo partition hoặc tuần tự theo key.
8. Lưu event ID để deduplicate side effect.
9. Kiểm tra version và state transition trước khi cập nhật.
10. Quyết định blocking retry hay retry topic theo yêu cầu ordering.
11. Chỉ commit offset sau khi xử lý hoàn tất liên tục.
12. Giám sát version gap, stale event, duplicate và partition distribution.

### Ví dụ cấu hình cơ bản

~~~properties
# Producer
acks=all
enable.idempotence=true

# Consumer
enable.auto.commit=false
max.poll.records=100
isolation.level=read_committed
~~~

Các cấu hình trên hỗ trợ độ tin cậy và quản lý commit, nhưng không tự thiết lập ordering theo entity. Key, version, producer serialization và consumer processing model vẫn là phần quyết định.

## 17. Những lỗi thiết kế thường gặp

- **Dùng eventId làm Kafka key:** mỗi event có key khác nhau nên các bước của cùng entity có thể đi vào nhiều partition.
- **Dùng key null:** partitioner có thể phân phối record mà không giữ entity affinity.
- **Cho rằng cùng key luôn đủ:** producer vẫn có thể phát event theo thứ tự sai do nhiều thread hoặc nhiều instance.
- **Tăng partition mà không đánh giá mapping:** key có thể chuyển partition và event mới vượt event cũ.
- **Dispatch từng record sang worker pool không giới hạn:** record cùng key có thể hoàn thành sai thứ tự và queue gây áp lực memory.
- **Commit ngay sau enqueue:** crash có thể làm mất công việc chưa hoàn thành khỏi tiến độ consumer.
- **Dùng retry topic mà không xét thứ tự:** event bước sau có thể được xử lý trước event lỗi.
- **Chỉ dựa vào timestamp:** đồng hồ và độ trễ publish không phản ánh chắc chắn sequence nghiệp vụ.
- **Cho rằng idempotence giải quyết mọi duplicate và ordering:** nó không điều phối nhiều producer hoặc side effect database.
- **Cho rằng Kafka transaction tạo thứ tự giữa topic:** transaction bảo đảm tính nguyên tử theo phạm vi hỗ trợ, không tạo total order.
- **Không kiểm tra aggregate version:** event stale hoặc gap có thể ghi đè trạng thái sai.
- **Không có inbox/outbox:** crash giữa database commit và Kafka publish có thể làm mất hoặc phát lặp sự kiện.

## 18. Checklist giữ thứ tự theo thực thể

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| Entity boundary | Thực thể nào cần có thứ tự: order, account, booking hay inventory item? |
| Kafka key | Mọi event của entity có dùng cùng key ổn định không? |
| Partitioner | Các producer có cùng serializer và partitioning rule không? |
| Partition count | Có kế hoạch trước khi tăng partition count không? |
| Producer concurrency | Có nhiều thread/instance phát cùng aggregate không? |
| Aggregate version | Event có version hoặc sequence tăng đơn điệu không? |
| Consumer | Listener có xử lý tuần tự theo partition/key không? |
| Worker pool | Queue có giới hạn, lane có giữ thứ tự và completion có được theo dõi không? |
| Retry | Retry topic có thể khiến event sau vượt event lỗi không? |
| Idempotency | Event ID đã được deduplicate ở nơi side effect được commit chưa? |
| Database | Có optimistic locking hoặc conditional update theo version không? |
| Outbox | Database state và outbox event có cùng transaction không? |
| Cross-topic | Có giả định sai về thứ tự giữa các topic không? |
| Monitoring | Có cảnh báo version gap, stale event, duplicate và hot partition không? |

## 19. Kết luận

Muốn giữ thứ tự theo thực thể qua nhiều bước xử lý, hãy đưa mọi event của cùng aggregate vào một partition bằng key ổn định, phát event theo sequence tăng dần và xử lý tuần tự theo partition hoặc theo key. Kafka bảo đảm thứ tự trong một partition; các lớp producer, consumer, retry, database và workflow vẫn phải phối hợp để bảo vệ thứ tự nghiệp vụ.

Aggregate version giúp phát hiện duplicate, stale event và gap. Transactional outbox giúp thay đổi database và event được ghi cùng transaction; inbox và optimistic locking giúp consumer xử lý lặp an toàn. Retry topic, worker pool, tăng partition và nhiều topic đều có thể làm thay đổi thứ tự quan sát được, nên phải được thiết kế có chủ đích.

Không có một cấu hình Kafka đơn lẻ tạo ra thứ tự xuyên suốt toàn hệ thống. Bảo đảm đáng tin cậy đến từ entity key nhất quán, sequence rõ ràng, state transition có điều kiện, xử lý bất đồng bộ có kiểm soát và khả năng phục hồi khi event đến trễ hoặc được giao lại.
