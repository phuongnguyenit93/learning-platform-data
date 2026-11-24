# Kiểm chứng số lần tăng và tránh ghi nhận trùng một sự kiện

Một `Counter` trong Micrometer chỉ hữu ích khi mỗi lần tăng tương ứng với một sự kiện được định nghĩa rõ ràng. Nếu cùng một đơn hàng bị đếm ở controller, service và consumer, hoặc một message được giao lại sau timeout, số đo có thể lớn hơn số sự kiện nghiệp vụ thực tế. Ngược lại, nếu tăng counter trước khi giao dịch được commit rồi giao dịch rollback, số đo có thể ghi nhận một kết quả chưa từng được lưu thành công.

Để kiểm chứng số lần tăng, cần xác định chính xác sự kiện nào được đếm, chọn một điểm ghi nhận có ngữ nghĩa ổn định, xử lý retry và redelivery bằng cơ chế idempotency của nghiệp vụ, rồi kiểm tra `count()` bằng test. Counter là dữ liệu quan sát tích lũy; nó không phải cơ chế chống trùng và cũng không thay thế sổ cái hay dữ liệu giao dịch có tính bền vững.

## Xác định một lần tăng đại diện cho điều gì

Trước khi viết `increment()`, hãy diễn đạt tên metric thành một câu có thể kiểm chứng. Ví dụ:

- `orders.created`: số đơn hàng được tạo thành công và được chấp nhận vào hệ thống.
- `payments.attempted`: số lần hệ thống bắt đầu thử thanh toán, kể cả lần thử lại.
- `payments.succeeded`: số lần thanh toán hoàn tất thành công theo định nghĩa nghiệp vụ.
- `messages.processed`: số message được xử lý thành công lần đầu.
- `messages.duplicate`: số lần consumer nhận message đã được xử lý trước đó.

Các tên này mô tả những sự kiện khác nhau. Một lần checkout có thể tạo ra ba lần thử thanh toán nhưng chỉ tạo một đơn hàng. Nếu tất cả cùng tăng một counter tên `orders.completed`, dashboard sẽ không thể phân biệt retry với kết quả nghiệp vụ.

| Câu hỏi cần trả lời | Sự kiện nên đếm | Vị trí ghi nhận phù hợp |
|---|---|---|
| Có bao nhiêu yêu cầu được gửi đến hệ thống? | Request được tiếp nhận | Điểm vào ứng dụng hoặc bộ lọc HTTP |
| Có bao nhiêu lần thử gọi dịch vụ thanh toán? | Mỗi lần gọi thực tế | Bên trong thao tác được retry |
| Có bao nhiêu đơn hàng được tạo thành công? | Một đơn hàng mới được commit | Sau khi giao dịch tạo đơn hàng thành công |
| Có bao nhiêu message bị giao lại? | Một lần nhận trùng đã được nhận diện | Nhánh phát hiện duplicate ở consumer |

Một counter nên có một định nghĩa sự kiện và một chủ sở hữu instrumentation rõ ràng. Nếu nhiều lớp đều cần quan sát cùng một quy trình, mỗi lớp có thể có metric riêng với ngữ nghĩa riêng; đừng để nhiều lớp cùng tăng một counter đại diện cho một kết quả duy nhất.

## Cách Counter tích lũy số lần tăng

`Counter` biểu diễn một giá trị tích lũy chỉ tăng. Gọi `increment()` để tăng một đơn vị hoặc `increment(amount)` để tăng một lượng dương. `count()` trả về tổng số đã ghi nhận trong vòng đời của meter ở registry hiện tại.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public class OrderMetrics {
    private final Counter ordersCreated;

    public OrderMetrics(MeterRegistry registry) {
        this.ordersCreated = Counter.builder("orders.created")
                .description("Số đơn hàng được tạo thành công")
                .tag("channel", "web")
                .register(registry);
    }

    public void recordCreated() {
        ordersCreated.increment();
    }

    public double count() {
        return ordersCreated.count();
    }
}
```

Trong ứng dụng thực tế, tag `channel` thường được truyền từ ngữ cảnh nghiệp vụ nhưng phải được chuẩn hóa về tập giá trị hữu hạn như `web`, `mobile` hoặc `partner`. Ví dụ trên cố định `web` để tập trung vào cách đăng ký và đọc counter.

Không dùng counter để biểu diễn số lượng hiện tại có thể tăng và giảm, chẳng hạn số kết nối đang mở hoặc số message còn trong hàng đợi. Những đại lượng đó phù hợp với `Gauge`. Counter cũng không phải đồng hồ đo thời gian; hãy dùng `Timer` cho thời lượng thao tác.

## Ghi nhận đúng một lần ở ranh giới nghiệp vụ

Giả sử một đơn hàng được tạo qua các lớp HTTP controller, application service và repository. Nếu cả ba lớp cùng gọi `ordersCreated.increment()`, một đơn hàng có thể bị đếm ba lần. Chọn một ranh giới đại diện cho sự kiện, thường là nơi ứng dụng xác nhận kết quả nghiệp vụ thành công, rồi đặt thao tác tăng counter ở đó.

```java
@Service
public class CreateOrderService {
    private final OrderRepository orders;
    private final OrderMetrics metrics;

    public CreateOrderService(
            OrderRepository orders,
            OrderMetrics metrics) {
        this.orders = orders;
        this.metrics = metrics;
    }

    public Order create(CreateOrderCommand command) {
        Order saved = orders.save(Order.from(command));
        metrics.recordCreated();
        return saved;
    }
}
```

Đoạn mã minh họa vị trí instrumentation sau khi repository trả về kết quả lưu. Nếu `save(...)` thất bại trước khi trả về, counter không tăng. Tuy nhiên, nếu phương thức đang chạy trong một transaction lớn hơn, việc `save(...)` trả về chưa có nghĩa transaction đã commit. Khi transaction có thể rollback sau đó, cần đặt phép tăng sau commit như phần tiếp theo.

Một nguyên tắc hữu ích là phân biệt rõ các giai đoạn: *được tiếp nhận*, *được thử xử lý*, *được lưu thành công* và *được commit*. Đặt tên counter và vị trí tăng theo đúng giai đoạn cần đo. Nhờ vậy, một lỗi sau khi tiếp nhận không bị hiểu nhầm thành một đơn hàng đã tạo thành công.

## Tránh đếm một kết quả chưa commit

Micrometer cập nhật counter ngay khi gọi `increment()`. Việc tăng counter không tham gia transaction cơ sở dữ liệu. Nếu code tăng counter rồi transaction rollback, số đo không tự giảm lại.

Trong Spring, có thể phát một application event bên trong transaction và dùng `@TransactionalEventListener` ở pha `AFTER_COMMIT` để tăng counter sau khi giao dịch commit:

```java
public record OrderCreatedEvent(String channel) {}

@Service
public class CreateOrderService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public CreateOrderService(
            OrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public Order create(CreateOrderCommand command) {
        Order saved = orders.save(Order.from(command));
        events.publishEvent(new OrderCreatedEvent(command.channel()));
        return saved;
    }
}

@Component
public class OrderMetricsListener {
    private final MeterRegistry registry;

    public OrderMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        registry.counter("orders.created", "channel", event.channel())
                .increment();
    }
}
```

Listener chỉ chạy sau khi transaction thành công commit, nên rollback thông thường không làm counter tăng. Event cần được phát trong một transaction đang hoạt động để listener `AFTER_COMMIT` nhận được nó; nếu không có transaction, listener mặc định không chạy trừ khi bật `fallbackExecution` một cách có chủ đích.

Có một giới hạn cần hiểu: cập nhật metric sau commit vẫn là thao tác trong bộ nhớ của tiến trình. Nếu JVM dừng ngay sau khi database commit nhưng trước khi listener tăng counter, metric có thể bị thiếu. Nếu yêu cầu đếm chính xác và có thể phục hồi sau sự cố, hãy dùng dữ liệu giao dịch hoặc transactional outbox làm nguồn sự thật, rồi xuất metric từ quy trình đọc dữ liệu bền vững. Không thể biến một lần `increment()` trong JVM thành một phần nguyên tử của transaction database.

## Retry và redelivery có thể tạo lần tăng lặp

Retry là việc thực hiện lại một thao tác sau lỗi tạm thời hoặc timeout. Redelivery là việc broker gửi lại message mà consumer chưa xác nhận hoặc chưa hoàn tất ack. Cả hai đều có thể khiến cùng một yêu cầu nghiệp vụ đi qua code nhiều lần.

Ví dụ, dịch vụ thanh toán đã xử lý yêu cầu nhưng phản hồi bị timeout. Client gửi lại yêu cầu. Nếu mỗi lần vào service đều tăng `payments.succeeded`, cùng một khoản thanh toán có thể bị đếm nhiều lần dù chỉ có một giao dịch thành công.

Hãy quyết định metric cần đếm:

- Nếu cần biết tải và số lần gọi thực tế, tăng `payments.attempted` cho mỗi lần thử. Retry phải làm counter này tăng thêm.
- Nếu cần biết số thanh toán thành công theo nghiệp vụ, chỉ tăng `payments.succeeded` khi kết quả mới được xác nhận và đã qua kiểm tra idempotency.
- Nếu cần biết số lần phát hiện yêu cầu lặp, tăng riêng `payments.duplicate` hoặc `messages.duplicate` trong nhánh phát hiện trùng.

Không loại bỏ retry khỏi metric attempts: retry là một phần của tải thực tế và có thể làm tăng chi phí hoặc khuếch đại sự cố. Điều cần tránh là cộng một kết quả nghiệp vụ nhiều lần vào counter kết quả thành công.

## Idempotency là cơ chế chống xử lý trùng

Idempotency bảo đảm nhiều lần nhận cùng một yêu cầu logic không tạo ra nhiều kết quả nghiệp vụ. Một hệ thống thường dùng idempotency key hoặc event ID để nhận diện yêu cầu đã xử lý. Việc lưu dấu đã xử lý phải có tính bền vững và được phối hợp với transaction nghiệp vụ.

Ví dụ về luồng consumer:

```java
@Transactional
public void handle(OrderCreatedMessage message) {
    if (processedMessages.existsById(message.eventId())) {
        metrics.recordDuplicateMessage();
        return;
    }

    processedMessages.save(new ProcessedMessage(message.eventId()));
    orderProjection.apply(message);
    events.publishEvent(new OrderProcessedEvent(message.channel()));
}
```

Trong ví dụ, `processedMessages` cần có ràng buộc duy nhất trên `eventId`, và thao tác ghi dấu cùng cập nhật projection phải thuộc transaction phù hợp. Chỉ kiểm tra `existsById` rồi ghi riêng rẽ mà không có ràng buộc duy nhất hoặc kiểm soát cạnh tranh có thể để hai consumer đồng thời cùng xử lý một event. Cách xử lý lỗi unique constraint cần được chuyển thành nhánh duplicate phù hợp.

Counter `messages.duplicate` nên được tăng khi consumer nhận diện một event đã xử lý. Counter `orders.processed` nên tăng sau khi lần xử lý mới commit, chẳng hạn thông qua listener `AFTER_COMMIT`. Đừng lưu event ID vào tag hoặc tạo một counter riêng cho từng event: việc đó làm cardinality tăng không giới hạn và metric không phải kho dedup.

Với message broker có giao nhận at-least-once, idempotency thường là trách nhiệm của consumer. Cơ chế exactly-once của một thành phần hoặc broker không tự động bảo đảm toàn bộ side effect ngoài broker, như cập nhật database và tăng metric, cũng exactly-once.

## Tránh ghi nhận trùng khi dùng nhiều lớp instrumentation

Một số nguồn trùng phổ biến:

1. **Instrumentation lặp ở nhiều tầng:** controller, service và repository cùng tăng một counter kết quả.
2. **Retry interceptor:** method được gọi lại nhiều lần nhưng counter kết quả đặt bên trong method retry.
3. **Message redelivery:** consumer nhận lại event sau khi xử lý thành công nhưng ack bị mất hoặc timeout.
4. **Callback lặp:** listener hoặc handler có thể được gọi lại bởi framework, scheduler hoặc logic thử lại.
5. **Transaction rollback:** counter tăng trước khi transaction hoàn tất và không thể rollback theo database.
6. **Đếm cả ở producer và consumer:** producer ghi nhận message đã publish, consumer ghi nhận message đã xử lý; hai metric này hợp lệ nếu tên và ngữ nghĩa khác nhau, nhưng không nên cùng tăng một counter tên `events.completed`.

Hãy rà soát toàn bộ đường đi của một sự kiện và xác định đúng một điểm sở hữu counter cho từng kết quả. Nếu cần đo nhiều giai đoạn, đặt tên riêng theo giai đoạn để người đọc dashboard không nhầm chúng là cùng một loại sự kiện.

## Kiểm chứng số lần tăng bằng SimpleMeterRegistry

`SimpleMeterRegistry` cho phép kiểm tra giá trị counter ngay trong unit test mà không cần backend bên ngoài:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

class OrderMetricsTest {
    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();

    @AfterEach
    void closeRegistry() {
        registry.close();
    }

    @Test
    void incrementsOnceForEachCreatedOrder() {
        Counter counter = registry.counter(
                "orders.created", "channel", "web");

        counter.increment();
        counter.increment();

        assertThat(counter.count()).isEqualTo(2.0);
    }
}
```

Test trên kiểm tra trực tiếp ngữ nghĩa tăng counter. Với service nghiệp vụ, nên kiểm tra cả hành vi khi xử lý thành công, thất bại và nhận lại cùng một event:

| Tình huống | Kết quả mong đợi cho counter thành công | Counter khác có thể tăng |
|---|---:|---|
| Một đơn hàng mới commit | +1 | `orders.attempted` +1 nếu có đo lần thử |
| Transaction rollback | +0 | `orders.failed` hoặc `orders.attempted` tùy định nghĩa |
| Cùng event được giao lại sau khi đã xử lý | +0 | `messages.duplicate` +1 |
| Một yêu cầu retry ba lần rồi thành công | +1 | `payments.attempted` +3 |
| Hai event ID khác nhau tạo hai đơn hàng mới | +2 | — |

Để test idempotency, gọi consumer hai lần với cùng event ID và xác nhận side effect nghiệp vụ chỉ được áp dụng một lần. Sau đó kiểm tra counter kết quả thành công tăng một lần và counter duplicate tăng một lần. Bài test này phải kiểm tra cơ chế dedup của service/repository; chỉ kiểm tra `Counter.count()` không chứng minh được nghiệp vụ đã chống trùng.

## Kiểm tra đồng thời và phạm vi của count()

Micrometer meter được thiết kế để cập nhật từ nhiều luồng trong cùng registry. Tuy nhiên, test đồng thời nên kiểm tra số lần tăng dự kiến sau khi các worker hoàn tất, thay vì đọc count giữa lúc các luồng vẫn đang chạy.

Ví dụ đơn giản để xác nhận tổng số lần tăng:

```java
int workers = 4;
int incrementsPerWorker = 1_000;
ExecutorService pool = Executors.newFixedThreadPool(workers);
Counter counter = registry.counter("test.concurrent.events");

List<Future<?>> tasks = new ArrayList<>();
for (int worker = 0; worker < workers; worker++) {
    tasks.add(pool.submit(() -> {
        for (int i = 0; i < incrementsPerWorker; i++) {
            counter.increment();
        }
    }));
}

for (Future<?> task : tasks) {
    task.get();
}
pool.shutdown();

assertThat(counter.count()).isEqualTo(4_000.0);
```

Đoạn mã cần các import `java.util.ArrayList`, `java.util.List`, `java.util.concurrent.ExecutorService`, `java.util.concurrent.Executors` và `java.util.concurrent.Future`; trong test thực tế hãy đóng executor trong `finally` hoặc dùng fixture quản lý vòng đời phù hợp. Mục đích của ví dụ là đợi tất cả tác vụ kết thúc trước khi so sánh tổng.

`count()` là tổng tích lũy trong meter hiện tại, không phải tốc độ theo giây và cũng không nhất thiết là tổng lịch sử của toàn hệ thống. Counter trong registry của một JVM có thể bắt đầu lại khi tiến trình khởi động lại. Với backend time-series, hãy dùng phép tính như `rate()` hoặc `increase()` để xử lý counter theo thời gian và theo từng instance.

## Giữ tag có cardinality thấp

Counter thường được phân nhóm bằng tag như `channel`, `result`, `payment_method` hoặc `region`. Mỗi tổ hợp tag tạo ra một meter ID riêng. Không thêm `orderId`, `eventId`, `requestId`, email hoặc exception message làm tag để phân biệt từng lần tăng.

Ví dụ tốt:

```java
registry.counter("payments.succeeded", "provider", "bank-a").increment();
registry.counter("payments.succeeded", "provider", "bank-b").increment();
```

Ví dụ không phù hợp:

```java
registry.counter("payments.succeeded", "orderId", order.id()).increment();
```

Nếu cần tìm một giao dịch cụ thể, dùng log hoặc trace với ID tương quan phù hợp. Metric trả lời câu hỏi tổng hợp như có bao nhiêu giao dịch thành công theo provider, không lưu danh sách định danh của từng giao dịch.

## Quy trình điều tra khi count không khớp

Khi dashboard hiển thị số lượng khác với kỳ vọng, kiểm tra theo trình tự:

1. **Chốt định nghĩa:** counter đang đếm request, attempt, event được nhận hay kết quả đã commit?
2. **Tìm tất cả điểm tăng:** tìm mọi lời gọi `increment()` cho tên meter và kiểm tra instrumentation ở các tầng, interceptor và listener.
3. **Kiểm tra retry/redelivery:** cùng một thao tác có thể đi qua code bao nhiêu lần? Metric nào cần đếm từng lần thử và metric nào chỉ đếm kết quả mới?
4. **Kiểm tra transaction:** counter có tăng trước commit hoặc trong nhánh có thể rollback không?
5. **Kiểm tra idempotency:** event ID hoặc idempotency key có được lưu bền vững và bảo vệ khỏi xử lý đồng thời không?
6. **Kiểm tra tag:** dashboard có đang lọc đúng `channel`, `result`, `instance` và các chiều khác không?
7. **Kiểm tra phạm vi thời gian:** `count()` trong JVM là tổng từ lúc meter được tạo; truy vấn backend có thể dùng `rate`, `increase` hoặc cửa sổ thời gian khác.

Không sửa sai lệch bằng cách giảm counter hoặc phát một giá trị âm. Counter có ngữ nghĩa chỉ tăng; nếu cần hiệu chỉnh số liệu nghiệp vụ, hãy sửa nguồn dữ liệu chuẩn và xây dựng metric hiệu chỉnh riêng với tên, ý nghĩa rõ ràng.

## Checklist hoàn thành

- [ ] Mỗi counter có định nghĩa sự kiện rõ ràng, ví dụ attempt, accepted, succeeded hoặc duplicate.
- [ ] Mỗi kết quả nghiệp vụ chỉ có một điểm instrumentation sở hữu việc tăng counter.
- [ ] Retry và redelivery được đo riêng với kết quả nghiệp vụ đã deduplicate.
- [ ] Counter thành công chỉ tăng sau thời điểm thành công được định nghĩa; transaction cần commit được xử lý sau commit.
- [ ] Cơ chế idempotency dùng ID bền vững và có bảo vệ khi xử lý đồng thời.
- [ ] Unit test xác nhận số lần tăng với `SimpleMeterRegistry`.
- [ ] Integration test xác nhận cùng event gửi lại không tạo side effect nghiệp vụ hoặc counter thành công trùng.
- [ ] Tag chỉ dùng tập giá trị hữu hạn và không chứa định danh từng giao dịch.
- [ ] Dashboard và truy vấn phân biệt tổng tích lũy, tốc độ và khoảng thời gian.

Kiểm chứng một counter không chỉ là xác nhận `count()` tăng đúng trong một unit test. Cần chứng minh điểm ghi nhận khớp với định nghĩa sự kiện, transaction và idempotency bảo vệ kết quả nghiệp vụ, còn retry hoặc redelivery được phản ánh bằng metric riêng. Khi các quy tắc này rõ ràng, số đo mới giúp diễn giải vận hành mà không nhầm số lần thử với số kết quả thực tế.
