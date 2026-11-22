# Tránh dùng state mutable dùng chung

## Mục tiêu của bài học

Trong chương **Concurrency và scale**, bài này giải thích vì sao listener Kafka chạy đồng thời cần tránh chia sẻ trạng thái có thể thay đổi giữa nhiều luồng xử lý. Với Spring Kafka, một listener endpoint có thể tạo nhiều consumer container con; các consumer này có thể gọi cùng một listener bean gần như cùng lúc. Nếu listener hoặc service giữ dữ liệu mutable trong field dùng chung, ứng dụng có thể gặp race condition, mất cập nhật, dữ liệu sai và lỗi khó tái hiện.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Khi tăng concurrency hoặc chạy nhiều instance, thiết kế state an toàn là điều kiện quan trọng để scale consumer mà không làm sai kết quả nghiệp vụ.

Sau bài học, người học có thể:

- Hiểu vì sao listener bean mặc định thường được chia sẻ giữa nhiều consumer thread.
- Nhận diện state mutable dùng chung và các race condition phổ biến.
- Thiết kế listener stateless và ưu tiên object immutable.
- Phân biệt biến local, field của bean, static field và state bên ngoài.
- Chọn `AtomicLong`, `LongAdder`, `ConcurrentHashMap` hoặc lock đúng mục đích.
- Bảo vệ invariant nghiệp vụ bằng transaction và cơ chế lưu trữ phù hợp.
- Tránh lỗi khi xử lý batch, callback bất đồng bộ và retry.
- Kiểm thử tính thread-safe và theo dõi lỗi concurrency trong production.

## 1. Vì sao consumer Kafka có thể xử lý đồng thời?

Trong Spring Kafka, `ConcurrentKafkaListenerContainerFactory` có thể tạo một `ConcurrentMessageListenerContainer` quản lý nhiều child container. Mỗi child container sở hữu một Kafka consumer riêng và chạy vòng lặp poll/listener của nó.

Ví dụ:

~~~java
factory.setConcurrency(3);
~~~

Một endpoint có concurrency bằng 3 có thể có ba consumer thread gọi cùng một phương thức listener. Trong Spring, listener thường là singleton bean, nên các thread này gọi trên cùng một object listener.

~~~mermaid
flowchart TD
    A["@KafkaListener singleton bean"] --> B["Listener method"]
    C["Consumer thread 1"] --> B
    D["Consumer thread 2"] --> B
    E["Consumer thread 3"] --> B
    B --> F["Shared service dependencies"]
~~~

Nếu ứng dụng có hai replica, mỗi replica có thể tạo thêm ba consumer. Khi đó có sáu consumer trong cùng group, có thể cùng gọi các bean singleton trong từng process.

Concurrency đến từ nhiều nơi:

- `concurrency` của listener container.
- Nhiều instance/replica của ứng dụng.
- Nhiều listener endpoint dùng chung một service bean.
- Executor hoặc callback bất đồng bộ do ứng dụng tạo.
- Scheduled job, HTTP request hoặc luồng xử lý khác cùng truy cập bean.

Không nên giả định một listener method chỉ được gọi bởi một thread. Thiết kế cần xem mọi dependency dùng chung có an toàn khi được gọi đồng thời hay không.

## 2. Mutable state dùng chung là gì?

State là dữ liệu mà một object giữ để dùng trong nhiều lần xử lý. Mutable state là dữ liệu có thể thay đổi sau khi object được tạo.

Ví dụ listener có field:

~~~java
@Service
public class OrderListener {

    private int processedCount;

    @KafkaListener(
        topics = "commerce.order.created",
        groupId = "billing-service"
    )
    public void listen(OrderCreated event) {
        processedCount++;
        // Xử lý event.
    }
}
~~~

`processedCount` là mutable state trong singleton bean. Khi nhiều consumer thread gọi `listen()` cùng lúc, các thread cùng đọc và ghi field này.

Một số nguồn state mutable dùng chung thường gặp:

- Field của `@Component`, `@Service`, `@Repository` singleton.
- `static` field.
- `ArrayList`, `HashMap`, `HashSet` được nhiều thread truy cập.
- DTO hoặc domain object được cache rồi sửa trực tiếp.
- Buffer, formatter hoặc builder không thread-safe.
- Biến trong object service được inject vào nhiều listener.
- Cache hoặc registry tùy chỉnh có giá trị mutable bên trong.
- Dữ liệu giữ trong singleton để theo dõi tiến độ xử lý.

Không phải mọi field đều nguy hiểm. Field `final` trỏ tới object immutable thường an toàn để chia sẻ. Nhưng `final` chỉ ngăn gán lại tham chiếu; nó không làm object bên trong trở thành immutable.

~~~java
private final List<String> topics = new ArrayList<>();
~~~

Tham chiếu `topics` không thể gán sang list khác, nhưng nội dung list vẫn có thể bị sửa và `ArrayList` không an toàn khi nhiều thread cùng đọc/ghi.

## 3. Race condition và lost update

Race condition xảy ra khi kết quả phụ thuộc vào thứ tự hoặc thời điểm các thread truy cập state dùng chung.

Ví dụ `processedCount++` không phải một thao tác nguyên tử. Về logic, nó gồm:

1. Đọc giá trị hiện tại.
2. Cộng thêm một.
3. Ghi giá trị mới.

Giả sử giá trị ban đầu là 10:

~~~text
Thread A đọc 10
Thread B đọc 10
Thread A ghi 11
Thread B ghi 11

Kết quả: 11
Kỳ vọng: 12
~~~

Một lần tăng bị mất. Đây là lost update.

Các lỗi tương tự có thể xảy ra khi:

- Hai thread cùng kiểm tra một đơn hàng chưa tồn tại rồi cùng tạo hóa đơn.
- Hai thread cùng cập nhật số dư dựa trên một giá trị cũ.
- Một thread thêm phần tử trong khi thread khác duyệt `ArrayList`.
- Một thread sửa object cache trong lúc thread khác đọc.
- Hai thread cùng cập nhật trạng thái theo chuỗi bước không nguyên tử.

Các lỗi concurrency thường khó tái hiện vì phụ thuộc lịch chạy của thread, tải hệ thống và thời điểm I/O. Một test chạy đơn lẻ có thể pass nhiều lần dù code vẫn có race condition.

## 4. Vấn đề visibility và memory consistency

Ngay cả khi không có lost update rõ ràng, một thread có thể không quan sát ngay thay đổi của thread khác nếu chương trình không thiết lập quan hệ đồng bộ phù hợp.

Ví dụ:

~~~java
public class ListenerState {

    private boolean stopped;

    public void stop() {
        stopped = true;
    }

    public void work() {
        while (!stopped) {
            // Tiếp tục làm việc.
        }
    }
}
~~~

Nếu `stop()` và `work()` chạy trên hai thread khác nhau, trường `stopped` không có cơ chế visibility. Thread chạy vòng lặp không được bảo đảm quan sát thay đổi theo cách ứng dụng mong muốn.

Dùng `volatile` có thể bảo đảm visibility cho cờ độc lập:

~~~java
private volatile boolean stopped;
~~~

Tuy nhiên, `volatile` không làm các thao tác compound như `count++` trở thành nguyên tử. Nó cũng không bảo vệ invariant liên quan đến nhiều field.

Cần chọn đúng công cụ:

- `volatile`: visibility cho một giá trị được đọc/ghi độc lập.
- `AtomicInteger`/`AtomicLong`: thao tác nguyên tử trên một biến.
- `synchronized`/`Lock`: bảo vệ vùng thao tác cần tính nguyên tử và invariant.
- Collection concurrent: bảo vệ cấu trúc collection theo contract của nó.
- Database transaction/constraint: bảo vệ dữ liệu nghiệp vụ được chia sẻ giữa nhiều process.

## 5. Ưu tiên listener stateless

Một listener stateless không giữ trạng thái nghiệp vụ thay đổi giữa các lần gọi. Nó nhận event, gọi service xử lý và kết thúc.

Ví dụ:

~~~java
@Service
public class OrderCreatedListener {

    private final BillingService billingService;

    public OrderCreatedListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
        topics = "commerce.order.created",
        groupId = "billing-service"
    )
    public void listen(OrderCreated event) {
        billingService.createInvoice(event);
    }
}
~~~

Phương thức không thay đổi field của listener. Dữ liệu phục vụ một lần xử lý nằm trong tham số và biến local.

Biến local thông thường thuộc stack frame của lần gọi phương thức. Mỗi thread có lần gọi riêng, nên các biến local không bị thread khác sửa trực tiếp.

~~~java
public void listen(OrderCreated event) {
    String orderId = event.orderId();
    BigDecimal total = calculateTotal(event);

    billingService.createInvoice(orderId, total);
}
~~~

Stateless không có nghĩa toàn bộ ứng dụng không được có state. Nó có nghĩa listener không dựa vào mutable state trong bộ nhớ của bean để phối hợp giữa các lần xử lý. State nghiệp vụ nên được lưu ở nơi có cơ chế đồng thời phù hợp như database, cache thread-safe hoặc state store được thiết kế riêng.

## 6. Ưu tiên object immutable

Object immutable không cho phép thay đổi trạng thái sau khi được tạo. Chúng dễ chia sẻ giữa các thread vì không có thao tác ghi sau khi khởi tạo.

Java record là lựa chọn tốt cho event DTO:

~~~java
public record OrderCreated(
    String orderId,
    String customerId,
    BigDecimal total
) {
}
~~~

Các field của record là final và record không cung cấp setter. Nhiều listener thread có thể đọc cùng một instance mà không cần lock nếu các thành phần bên trong cũng immutable hoặc không bị sửa.

Cần lưu ý immutable chỉ thực sự an toàn nếu toàn bộ object graph không chứa mutable object bị chia sẻ. Ví dụ:

~~~java
public record OrderSnapshot(List<String> itemIds) {
}
~~~

Record này không tự biến list thành immutable. Nếu caller giữ list gốc rồi sửa, snapshot vẫn quan sát được thay đổi đó.

Có thể tạo defensive copy:

~~~java
public record OrderSnapshot(List<String> itemIds) {

    public OrderSnapshot {
        itemIds = List.copyOf(itemIds);
    }
}
~~~

`List.copyOf` tạo list không sửa được qua tham chiếu mới và ngăn thay đổi cấu trúc từ list gốc ảnh hưởng tới snapshot. Các phần tử bên trong cũng cần immutable nếu chúng được chia sẻ.

## 7. Dùng biến local thay cho field tạm

Không lưu dữ liệu của lần xử lý hiện tại vào field singleton.

Không an toàn:

~~~java
@Service
public class OrderListener {

    private OrderCreated currentEvent;

    @KafkaListener(topics = "commerce.order.created")
    public void listen(OrderCreated event) {
        currentEvent = event;
        billingService.process(currentEvent);
    }
}
~~~

Hai thread có thể ghi đè `currentEvent` của nhau. Thread A có thể gọi service với event của thread B.

An toàn hơn:

~~~java
@Service
public class OrderListener {

    @KafkaListener(topics = "commerce.order.created")
    public void listen(OrderCreated event) {
        billingService.process(event);
    }
}
~~~

Nếu cần biến tạm, khai báo trong phương thức. Không cần field chỉ để truyền dữ liệu giữa các dòng trong cùng một lần xử lý.

Trường hợp phải giữ state qua nhiều record, hãy xác định rõ scope và cơ chế đồng bộ. Đừng dùng field singleton làm nơi chứa “record hiện tại” hoặc “batch hiện tại”.

## 8. Collection thread-safe và giới hạn của chúng

Nếu thật sự cần một collection dùng chung giữa nhiều thread, hãy chọn cấu trúc có contract hỗ trợ concurrency.

Ví dụ:

~~~java
private final Map<String, OrderSnapshot> cache =
    new ConcurrentHashMap<>();
~~~

`ConcurrentHashMap` cho phép nhiều thread truy cập và cập nhật cấu trúc map an toàn theo các operation được hỗ trợ.

Nhưng điều đó không tự làm object value bên trong thread-safe:

~~~java
private final Map<String, MutableOrderState> states =
    new ConcurrentHashMap<>();
~~~

Nếu hai thread cùng lấy một `MutableOrderState` rồi sửa các field của object đó, race condition vẫn xảy ra. ConcurrentHashMap chỉ bảo vệ thao tác trên map, không bảo vệ mọi thao tác trên value.

Với danh sách chỉ thêm và đọc, có thể cân nhắc `CopyOnWriteArrayList` nếu số lần ghi thấp và số lần đọc cao. Collection này tạo bản sao mảng khi ghi, nên không phù hợp với workload ghi nhiều hoặc list lớn.

Không dùng `Collections.synchronizedList` như giải pháp tự động cho mọi trường hợp. Khi duyệt collection, vẫn cần đồng bộ theo contract của wrapper để tránh thay đổi đồng thời.

Ví dụ duyệt list đồng bộ:

~~~java
List<String> synchronizedTopics =
    Collections.synchronizedList(new ArrayList<>());

synchronized (synchronizedTopics) {
    for (String topic : synchronizedTopics) {
        log.info("Topic: {}", topic);
    }
}
~~~

Mọi đoạn code khác thêm, xóa hoặc duyệt list cũng cần tuân theo cùng quy tắc đồng bộ. Nếu có thể, ưu tiên không chia sẻ list mutable hoặc dùng snapshot immutable.

## 9. AtomicLong, LongAdder và thao tác nguyên tử

Với bộ đếm độc lập, có thể dùng `AtomicLong`:

~~~java
@Service
public class ListenerMetrics {

    private final AtomicLong processedCount = new AtomicLong();

    public void markProcessed() {
        processedCount.incrementAndGet();
    }

    public long processedCount() {
        return processedCount.get();
    }
}
~~~

`incrementAndGet()` là thao tác nguyên tử. Nhiều thread tăng counter sẽ không bị lost update.

Nếu chỉ cần metric đếm dưới tải ghi cao, `LongAdder` có thể giảm contention:

~~~java
private final LongAdder processedCount = new LongAdder();

public void markProcessed() {
    processedCount.increment();
}

public long processedCount() {
    return processedCount.sum();
}
~~~

`LongAdder` phù hợp với thống kê tổng hợp. Giá trị `sum()` trong lúc có cập nhật đồng thời không phải snapshot nguyên tử tuyệt đối. Không dùng nó để cấp số thứ tự duy nhất hoặc bảo vệ quyết định nghiệp vụ.

### 9.1. Atomic không bảo vệ nhiều bước nghiệp vụ

Ví dụ dùng `AtomicInteger` cho số lượng hàng:

~~~java
if (stock.get() > 0) {
    stock.decrementAndGet();
}
~~~

Đoạn code vẫn có race condition logic. Hai thread có thể cùng đọc `stock` bằng 1 rồi cả hai cùng giảm, dẫn tới giá trị -1.

Có thể dùng compare-and-set loop:

~~~java
boolean reserveOne(AtomicInteger stock) {
    while (true) {
        int current = stock.get();

        if (current <= 0) {
            return false;
        }

        if (stock.compareAndSet(current, current - 1)) {
            return true;
        }
    }
}
~~~

Cách này bảo vệ phép kiểm tra và giảm trên một biến atomic trong một process. Nhưng nếu tồn kho nằm trong database và nhiều application instance cùng cập nhật, AtomicInteger trong mỗi process không đủ. Cần atomic update hoặc locking ở database.

## 10. ConcurrentHashMap và thao tác compound

Không nên tách thao tác “kiểm tra rồi thêm” thành hai bước nếu nhiều thread cùng thực hiện:

~~~java
if (!states.containsKey(orderId)) {
    states.put(orderId, new OrderState());
}
~~~

Hai thread có thể cùng thấy key chưa tồn tại rồi cùng tạo state. Dùng operation nguyên tử như `computeIfAbsent`:

~~~java
OrderState state = states.computeIfAbsent(
    orderId,
    ignored -> new OrderState()
);
~~~

Hàm mapping nên ngắn, không thực hiện I/O lâu và không cập nhật ngược vào chính map theo cách gây re-entrancy.

Nếu object `OrderState` mutable và nhiều thread cùng thay đổi, cần đồng bộ riêng cho state hoặc chuyển state sang immutable update:

~~~java
private final ConcurrentHashMap<String, OrderSnapshot> states =
    new ConcurrentHashMap<>();

public void update(String orderId, OrderEvent event) {
    states.compute(orderId, (key, current) ->
        apply(current, event)
    );
}
~~~

Trong ví dụ, `apply` nên trả về snapshot mới và không sửa object `current`. `compute` giúp thao tác thay thế value của key diễn ra nguyên tử theo contract của map. Không dùng cách này để thay thế transaction cho dữ liệu cần phối hợp giữa nhiều key hoặc nhiều hệ thống.

## 11. Khi nào dùng synchronized hoặc Lock?

Khi một invariant cần nhiều thao tác cùng được thực hiện như một đơn vị, có thể dùng `synchronized` hoặc `Lock`.

Ví dụ:

~~~java
public class InMemoryInventory {

    private int available;

    public synchronized boolean reserve(int quantity) {
        if (quantity <= 0 || available < quantity) {
            return false;
        }

        available -= quantity;
        return true;
    }
}
~~~

Khối synchronized bảo vệ việc kiểm tra và giảm số lượng trong một object trên một JVM.

Nhược điểm:

- Các thread phải chờ nhau khi cùng vào critical section.
- Lock rộng làm giảm concurrency và throughput.
- Lock chỉ có hiệu lực trong process/JVM đó.
- Không bảo vệ state nếu process khác truy cập cùng dữ liệu ở nơi khác.

Nếu dùng `ReentrantLock`, cần luôn unlock trong `finally`:

~~~java
private final Lock lock = new ReentrantLock();

public void update() {
    lock.lock();
    try {
        // Critical section.
    } finally {
        lock.unlock();
    }
}
~~~

Không giữ lock trong khi gọi HTTP, database hoặc thao tác chậm nếu có thể tránh. Critical section nên ngắn và có phạm vi rõ ràng.

## 12. State nghiệp vụ nên được bảo vệ ở nơi lưu trữ có thẩm quyền

Spring Kafka consumer thường chạy trên nhiều thread và nhiều instance. Một `synchronized` hoặc `AtomicLong` trong JVM không đồng bộ được state giữa các replica.

Ví dụ hai instance cùng xử lý sự kiện đặt hàng và cập nhật tồn kho. Cả hai đều có biến `AtomicInteger` riêng. Mỗi instance có thể tin rằng còn hàng dù tổng số lượng đã bị instance khác đặt trước.

Với state nghiệp vụ quan trọng, nên dùng cơ chế lưu trữ có khả năng điều phối đồng thời:

- Database transaction.
- Unique constraint hoặc optimistic locking.
- Câu lệnh update nguyên tử.
- Redis atomic operation hoặc distributed lock khi phù hợp.
- Inbox/idempotency table để chống xử lý lặp.
- Kafka Streams state store khi bài toán cần stateful stream processing theo key.

Ví dụ optimistic locking với JPA:

~~~java
@Entity
public class Inventory {

    @Id
    private String productId;

    private int available;

    @Version
    private long version;

    public void reserve(int quantity) {
        if (quantity <= 0 || available < quantity) {
            throw new IllegalStateException("Insufficient stock");
        }

        available -= quantity;
    }
}
~~~

`@Version` cho phép persistence provider phát hiện cập nhật cạnh tranh. Khi hai transaction cùng sửa một version, một transaction có thể thất bại do optimistic lock conflict và cần retry theo chính sách nghiệp vụ.

Một câu lệnh update có điều kiện cũng có thể bảo vệ phép trừ tồn kho:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :productId
  AND available >= :quantity;
~~~

Kiểm tra số dòng được cập nhật. Nếu bằng 0, không đủ hàng hoặc bản ghi không tồn tại. Database thực hiện phép kiểm tra và cập nhật như một statement nguyên tử theo semantics của hệ quản trị.

## 13. Idempotency và duplicate delivery

Kafka consumer có thể nhận lại một record nếu xử lý xong nhưng chưa commit offset, hoặc nếu retry/rebalance làm record được giao lại. Do đó, không dùng một `Set` trong bộ nhớ của listener singleton làm cơ chế chống duplicate lâu dài.

Ví dụ cách làm không đủ an toàn:

~~~java
private final Set<String> processedEventIds =
    ConcurrentHashMap.newKeySet();

public void process(OrderCreated event) {
    if (processedEventIds.add(event.eventId())) {
        billingService.createInvoice(event);
    }
}
~~~

Set này chỉ tồn tại trong một JVM. Khi restart, dữ liệu mất; khi có nhiều replica, mỗi replica có set riêng. Hai instance có thể cùng xử lý một event.

Một cách chắc chắn hơn là lưu event ID trong database với unique constraint trong cùng transaction với thay đổi nghiệp vụ:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong transaction:

1. Thử insert event ID.
2. Nếu insert thành công, thực hiện thay đổi nghiệp vụ.
3. Nếu vi phạm unique constraint, event đã được xử lý trước đó; bỏ qua theo chính sách.
4. Commit database transaction.
5. Listener hoàn tất để container commit Kafka offset.

Cần thiết kế xử lý unique violation phù hợp với transaction manager và database driver. Mục tiêu là việc đánh dấu đã xử lý và thay đổi nghiệp vụ cùng commit hoặc cùng rollback.

## 14. Không chia sẻ mutable state qua callback bất đồng bộ

Một listener có thể gọi `KafkaTemplate.send()` hoặc executor. Callback thường chạy trên thread khác. Không giả định callback chạy trên consumer thread.

Ví dụ nguy hiểm:

~~~java
private OrderCreated currentEvent;

public void listen(OrderCreated event) {
    currentEvent = event;

    kafkaTemplate.send("billing.audit", event)
        .whenComplete((result, error) -> {
            auditService.record(currentEvent, error);
        });
}
~~~

Một lần gọi listener khác có thể ghi đè `currentEvent` trước khi callback đầu tiên chạy. Callback sẽ ghi audit cho sai event.

Hãy capture biến local immutable trong callback:

~~~java
public void listen(OrderCreated event) {
    OrderCreated current = event;

    kafkaTemplate.send("billing.audit", current)
        .whenComplete((result, error) -> {
            auditService.record(current, error);
        });
}
~~~

`current` thuộc lần gọi hiện tại và được callback giữ qua closure. Điều này an toàn nếu `OrderCreated` immutable và các dependency được gọi từ callback cũng thread-safe.

Nếu listener cần chờ send hoàn tất trước khi commit offset, cần chờ future hoặc dùng cơ chế async listener phù hợp với phiên bản Spring Kafka. Nếu trả về khỏi listener trước khi công việc quan trọng hoàn tất, container có thể commit offset quá sớm.

## 15. ThreadLocal không phải kho state cho event

`ThreadLocal` giữ giá trị riêng theo thread, nên có thể hữu ích cho context ngắn hạn như correlation ID trong một luồng đồng bộ. Nhưng không nên dùng nó làm nơi lưu state nghiệp vụ của consumer.

Các vấn đề:

- Callback bất đồng bộ có thể chạy trên thread khác và không thấy giá trị.
- Thread của container được tái sử dụng cho nhiều record.
- Giá trị cũ có thể rò sang lần xử lý tiếp theo nếu không cleanup.
- ThreadLocal không chia sẻ state giữa các replica.
- Không bảo đảm context được truyền qua executor.

Nếu buộc phải dùng ThreadLocal, luôn cleanup trong `finally`:

~~~java
try {
    RequestContext.set(traceId);
    billingService.process(event);
} finally {
    RequestContext.clear();
}
~~~

Ưu tiên truyền context qua tham số hoặc dùng cơ chế context propagation có chủ đích thay vì dựa vào ThreadLocal ngầm.

## 16. Batch listener và state mutable

Batch listener nhận `List<ConsumerRecord<K,V>>`. List thuộc lần gọi listener, nhưng không nên chia sẻ nó sang thread khác rồi tiếp tục sửa sau khi listener trả về.

Không làm:

~~~java
private List<ConsumerRecord<String, OrderCreated>> currentBatch;

public void listen(List<ConsumerRecord<String, OrderCreated>> records) {
    currentBatch = records;
    executor.submit(() -> process(currentBatch));
}
~~~

Lần gọi batch tiếp theo có thể thay thế `currentBatch`. Task cũ có thể xử lý nhầm batch mới.

Hãy tạo snapshot local và truyền trực tiếp:

~~~java
public void listen(List<ConsumerRecord<String, OrderCreated>> records) {
    List<OrderCreated> events = records.stream()
        .map(ConsumerRecord::value)
        .filter(Objects::nonNull)
        .toList();

    processBatchAndWait(events);
}
~~~

Nếu chuyển sang executor, cần đợi task hoàn tất trước khi listener kết thúc hoặc quản lý acknowledgment/offset theo cơ chế bất đồng bộ có hỗ trợ. `List.copyOf(records)` chỉ tạo bản sao cấu trúc list; nó không biến `ConsumerRecord` hoặc payload mutable bên trong thành immutable.

## 17. Không dùng static mutable state để chia sẻ giữa consumer

`static` field tồn tại ở cấp classloader/JVM, không phải một kho state phân tán.

Ví dụ:

~~~java
public class ConsumerState {
    public static final Map<String, Integer> COUNTS =
        new HashMap<>();
}
~~~

Nếu nhiều listener thread cập nhật `COUNTS`, HashMap có thể bị race condition. Đổi sang ConcurrentHashMap chỉ giải quyết cấu trúc map, còn logic cập nhật value vẫn phải an toàn.

Ngoài ra, mỗi application replica có một static map riêng. Static field không giúp đồng bộ giữa các pod hoặc server.

Chỉ dùng static immutable constants cho dữ liệu cấu hình bất biến. Tránh static cache mutable nếu chưa có thiết kế concurrency, eviction, giới hạn bộ nhớ và đồng bộ giữa instance.

## 18. State theo partition và thứ tự xử lý

Một số bài toán muốn giữ state trong bộ nhớ theo partition hoặc key. Có thể thực hiện nếu kiểm soát assignment, thread ownership, rebalance, restart và phục hồi state. Đây là bài toán phức tạp hơn việc lưu một map trong listener.

Các điểm cần xem xét:

- Partition có thể được chuyển sang consumer khác khi rebalance.
- Consumer có thể restart và mất state trong RAM.
- Một key có thể được định tuyến khác partition sau khi tăng partition hoặc đổi partitioner.
- Nhiều application instance không chia sẻ local map.
- State cần được khôi phục hoặc tái tạo từ changelog/database.

Nếu logic cần stateful processing theo key, window, join hoặc state store có phục hồi, cân nhắc Kafka Streams. Kafka Streams cung cấp task/partition ownership và state store/changelog theo mô hình stream processing thay vì tự quản lý map mutable trong listener.

Trong Spring Kafka listener thông thường, chỉ dựa vào “cùng partition được một consumer xử lý” là chưa đủ để bảo đảm state local luôn tồn tại hoặc luôn thuộc cùng thread qua mọi lần rebalance.

## 19. Transaction annotation và thread boundary

`@Transactional` của Spring thường gắn transaction context với thread đang thực thi. Nếu listener chuyển công việc sang executor, transaction của thread listener không tự động đi theo task mới.

Ví dụ:

~~~java
@Transactional
public void listen(OrderCreated event) {
    executor.submit(() -> billingService.createInvoice(event));
}
~~~

Transaction bao quanh phương thức `listen()` có thể kết thúc trước khi task chạy xong. Task có thể chạy ngoài transaction mong muốn.

Nếu cần transaction cho công việc bất đồng bộ, hãy gọi một service method mở transaction riêng bên trong task, hoặc dùng cơ chế quản lý transaction được hỗ trợ rõ ràng. Không chia sẻ EntityManager/session không thread-safe giữa các thread.

Tương tự, không giả định security context, MDC hoặc tracing context tự động truyền sang executor. Dùng context propagation có chủ đích và dọn context sau khi task hoàn tất.

## 20. Cẩn trọng với dependency được inject

Listener stateless vẫn có thể không an toàn nếu dependency mà nó gọi giữ mutable state không thread-safe.

Ví dụ:

~~~java
@Service
public class BillingService {

    private final SimpleDateFormat formatter =
        new SimpleDateFormat("yyyy-MM-dd");

    public String format(Date date) {
        return formatter.format(date);
    }
}
~~~

`SimpleDateFormat` không thread-safe. Nhiều listener thread gọi cùng service có thể nhận kết quả sai hoặc lỗi.

Dùng `DateTimeFormatter` immutable/thread-safe:

~~~java
private static final DateTimeFormatter FORMATTER =
    DateTimeFormatter.ISO_LOCAL_DATE;

public String format(LocalDate date) {
    return FORMATTER.format(date);
}
~~~

Khi review listener, kiểm tra cả dependency graph:

- Formatter, parser và builder có mutable không?
- Có field collection được cập nhật không?
- Có client hoặc session được thiết kế cho một thread không?
- Có buffer dùng chung không?
- Có cache tự viết không?
- Có method trả object mutable rồi caller sửa không?

Nhiều thư viện như `KafkaTemplate` được thiết kế để chia sẻ trong ứng dụng Spring, nhưng không nên suy rộng rằng mọi object dependency đều thread-safe. Kiểm tra contract của từng lớp.

## 21. Kiểm thử thread safety

Kiểm thử đơn vị thông thường với một lần gọi tuần tự không phát hiện được nhiều race condition. Cần tạo tải đồng thời có kiểm soát.

Ví dụ kiểm tra counter:

~~~java
@Test
void shouldCountConcurrentUpdates() throws Exception {
    int workers = 8;
    int incrementsPerWorker = 10_000;

    AtomicLong count = new AtomicLong();
    ExecutorService executor =
        Executors.newFixedThreadPool(workers);

    CountDownLatch ready = new CountDownLatch(workers);
    CountDownLatch start = new CountDownLatch(1);

    List<Future<?>> tasks = new ArrayList<>();

    for (int worker = 0; worker < workers; worker++) {
        tasks.add(executor.submit(() -> {
            ready.countDown();
            start.await();

            for (int i = 0; i < incrementsPerWorker; i++) {
                count.incrementAndGet();
            }

            return null;
        }));
    }

    try {
        assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
        start.countDown();

        for (Future<?> task : tasks) {
            task.get(10, TimeUnit.SECONDS);
        }

        assertThat(count.get())
            .isEqualTo((long) workers * incrementsPerWorker);
    } finally {
        executor.shutdownNow();
    }
}
~~~

Test này minh họa cách đồng bộ thời điểm bắt đầu để tạo contention. Khối `finally` đóng executor kể cả khi assertion hoặc future thất bại, tránh rò thread trong test.

### 21.1. Kiểm thử listener đồng thời

Với Kafka integration test:

1. Tạo topic có nhiều partition.
2. Cấu hình listener concurrency lớn hơn 1.
3. Gửi nhiều event với key phân bố khác nhau.
4. Tạo tải đồng thời đủ để nhiều consumer nhận partition.
5. Xác nhận số event được xử lý đúng và không có lost update.
6. Kiểm tra database constraints và idempotency khi gửi duplicate.
7. Restart hoặc rebalance consumer trong lúc tải nếu cần kiểm tra recovery.

Dùng `CountDownLatch`, `CyclicBarrier`, Awaitility hoặc test probe để đồng bộ. Tránh `Thread.sleep()` cố định vì nó không bảo đảm các thread đã đi vào vùng tranh chấp.

### 21.2. Kiểm thử race condition không chỉ dựa vào một lần pass

Race condition phụ thuộc lịch thread. Chạy stress test nhiều vòng có thể tăng khả năng phát hiện, nhưng không chứng minh tuyệt đối code thread-safe.

Kết hợp:

- Review ownership của state.
- Kiểm tra contract thread-safe của dependency.
- Unit test concurrent operations.
- Integration test với listener concurrency.
- Test duplicate/rebalance/restart.
- Metrics và log trong môi trường staging.

## 22. Theo dõi concurrency trong production

Một số tín hiệu giúp phát hiện lỗi hoặc nghẽn do state dùng chung:

| Tín hiệu | Điều cần quan sát |
|---|---|
| Consumer concurrency | Số child consumer và số replica thực tế |
| Listener processing time | Thời gian xử lý và độ lệch giữa các lần gọi |
| Consumer lag | Lag theo group và partition |
| Error/retry rate | Lỗi tăng khi concurrency tăng |
| Database conflict | Optimistic lock conflict, deadlock hoặc unique violation |
| Lock wait time | Thread chờ lock và critical section quá dài |
| Thread pool queue | Task bất đồng bộ bị dồn hàng |
| Heap/cache size | Cache mutable tăng không giới hạn |
| Duplicate event count | Event bị giao lại hoặc xử lý lặp |
| Rebalance frequency | Consumer membership không ổn định |

Khi tăng concurrency, hãy theo dõi throughput và error rate cùng lúc. Throughput tăng nhưng duplicate, database conflict hoặc latency tăng mạnh có thể là dấu hiệu state dùng chung đang gây contention hoặc sai dữ liệu.

## 23. Các lỗi thiết kế thường gặp

| Thiết kế | Rủi ro | Hướng xử lý |
|---|---|---|
| `count++` trong field singleton | Lost update | AtomicLong/LongAdder nếu chỉ là metric |
| `ArrayList` dùng chung giữa listener thread | Race condition và lỗi cấu trúc | Local list hoặc collection phù hợp |
| `HashMap` dùng chung | Concurrent modification/corruption | ConcurrentHashMap hoặc state store |
| ConcurrentHashMap chứa mutable value | Race condition bên trong value | Immutable value, atomic compute hoặc lock |
| Field `currentEvent` | Thread ghi đè event của nhau | Dùng tham số/biến local |
| Static mutable cache | Không thread-safe và không chia sẻ giữa replica | Cache có concurrency/eviction hoặc external store |
| ThreadLocal không cleanup | Context rò sang lần xử lý khác | `try/finally` và clear |
| Callback dùng field mutable | Callback đọc nhầm dữ liệu | Capture biến local immutable |
| Submit task rồi listener return | Commit offset trước khi task hoàn tất | Chờ task hoặc async acknowledgment có kiểm soát |
| Synchronized toàn bộ listener | Throughput giảm, lock contention | Giảm critical section hoặc thiết kế stateless |
| Dùng Atomic để bảo vệ nhiều field | Invariant vẫn có thể bị phá vỡ | Lock, transaction hoặc atomic update |
| Dùng RAM chống duplicate | Mất state khi restart và mỗi replica khác nhau | Inbox/unique constraint trong database |

## 24. Checklist trước khi tăng concurrency

- [ ] Listener bean không giữ event hoặc batch hiện tại trong mutable field?
- [ ] Các biến tạm được giữ local trong từng invocation?
- [ ] DTO/event được chia sẻ có immutable hoặc defensive copy?
- [ ] Service dependency được kiểm tra thread-safety?
- [ ] Collection dùng chung có concurrency contract phù hợp?
- [ ] Atomic chỉ được dùng cho thao tác trên biến độc lập?
- [ ] Invariant nhiều bước được bảo vệ bằng lock/transaction phù hợp?
- [ ] State nghiệp vụ quan trọng nằm ở storage có thẩm quyền?
- [ ] Idempotency không phụ thuộc một Set/Map trong RAM?
- [ ] Callback không đọc field mutable có thể bị ghi đè?
- [ ] Task bất đồng bộ hoàn tất trước khi commit offset hoặc có cơ chế ack rõ ràng?
- [ ] ThreadLocal được cleanup?
- [ ] Transaction và context propagation được xử lý đúng khi đổi thread?
- [ ] Có test concurrent load, duplicate, rebalance và restart?
- [ ] Theo dõi consumer lag, lock wait, database conflict và retry rate?

## Kết luận

Khi Spring Kafka tăng concurrency, nhiều consumer thread có thể gọi cùng một listener bean singleton và cùng các service dependency. Mutable state trong field, static collection hoặc object cache dùng chung có thể gây race condition, lost update và dữ liệu không nhất quán. Ưu tiên listener stateless, biến local và object immutable; chỉ dùng atomic, concurrent collection hoặc lock khi thực sự cần chia sẻ state và hiểu rõ giới hạn của từng cơ chế.

State nghiệp vụ cần nhất quán giữa nhiều thread hoặc nhiều application instance nên được bảo vệ bằng transaction, constraint, optimistic locking hoặc state store phù hợp. Đặc biệt, không dùng state trong RAM để thay thế idempotency bền vững, không trả về khỏi listener trước khi công việc bất đồng bộ hoàn tất và luôn kiểm thử dưới concurrency thực tế. Thiết kế ownership của state rõ ràng giúp tăng consumer concurrency mà vẫn giữ kết quả xử lý đáng tin cậy.
