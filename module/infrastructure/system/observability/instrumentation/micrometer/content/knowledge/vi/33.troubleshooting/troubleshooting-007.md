# Số đếm tăng hai lần do nhiều tầng cùng đo một thao tác

Một dashboard hiển thị 200 đơn hàng đã thanh toán trong khi hệ thống nghiệp vụ chỉ có 100 đơn thường là dấu hiệu cần kiểm tra ngữ nghĩa và vị trí ghi nhận metric. Nguyên nhân có thể là controller và service cùng tăng một Counter, một domain event bị xử lý lặp, retry tạo thêm lần ghi, hoặc một truy vấn backend cộng hai luồng dữ liệu vốn đang mô tả cùng một thao tác.

Không phải mọi số liệu xuất hiện ở nhiều tầng đều là đếm trùng. Một HTTP request, một lần gọi use case, một lần truy vấn database và một domain event là những đơn vị khác nhau. Chúng có thể cùng xảy ra trong một luồng xử lý và đều đáng đo. Vấn đề xuất hiện khi nhiều tầng cùng cập nhật một meter với cùng ý nghĩa, hoặc dashboard cộng các series có cùng ý nghĩa như thể chúng là các sự kiện độc lập.

Cách xử lý bền vững là định nghĩa rõ đơn vị được đếm, chọn một điểm ghi nhận có thẩm quyền cho từng metric, giữ metric name phản ánh đúng ranh giới thao tác và xác minh toàn bộ đường đi từ code đến backend.

## 1. Nhận diện dấu hiệu đếm trùng

Một số biểu hiện thường gặp:

- Counter tăng gần gấp đôi sau khi thêm instrumentation ở service layer.
- Số đơn thanh toán trong dashboard cao hơn số bản ghi PAID trong database.
- Một request tạo hai lần tăng cho cùng metric name và tag set.
- Timer count cao gấp đôi số lần gọi nghiệp vụ dự kiến.
- Sau khi thêm Observation tùy chỉnh, metrics HTTP hoặc business metrics tăng bất thường.
- Chạy một request duy nhất nhưng metric tăng hai lần.
- Dashboard tổng hợp hai job hoặc hai instance cùng scrape một endpoint.

Không nên kết luận ngay rằng Micrometer tự tăng Counter hai lần. Micrometer ghi nhận những lần ứng dụng gọi `increment()`, `record()` hoặc những lần handler hoàn tất Observation. Cần lần theo tất cả nơi có thể tạo ra các lần ghi đó.

## 2. Trước hết phải định nghĩa “một lần” là gì

Cùng một luồng xử lý có thể có nhiều loại đơn vị đo:

| Đơn vị | Ý nghĩa | Ví dụ |
|---|---|---|
| HTTP request | Một request đi vào server | Một lần gọi `POST /orders` |
| Use case invocation | Một lần application service được gọi | Một lần chạy `PlaceOrder` |
| Dependency call | Một lần gọi database hoặc payment provider | Một lần gọi `authorize()` |
| Domain event | Một sự kiện nghiệp vụ đã phát sinh | `OrderPaid` |
| Business entity | Một đối tượng duy nhất đạt trạng thái nào đó | Một order chuyển sang PAID một lần |
| Delivery attempt | Một lần broker giao message cho consumer | Một lần nhận message, kể cả retry |

Các đơn vị này không thể thay thế cho nhau. Một HTTP request có thể gọi service nhiều lần; một use case có thể gọi payment provider hai lần do retry; một domain event có thể được broker giao lại nhiều lần; một order chỉ nên được tính là đã thanh toán một lần nếu metric định nghĩa theo entity chuyển trạng thái.

Trước khi sửa code, viết định nghĩa metric thành một câu hoàn chỉnh. Ví dụ:

> `business.orders.paid` tăng đúng một lần cho mỗi order khi chuyển trạng thái sang PAID đã được commit thành công.

Định nghĩa này xác định entity, trạng thái và thời điểm ghi nhận. Nó cũng loại trừ việc tăng Counter ở mỗi lần HTTP request hoặc mỗi lần message delivery.

## 3. Nhiều tầng cùng đo một thao tác có thể hợp lệ hoặc sai

Xét luồng:

```text
HTTP Controller
    -> OrderApplicationService
        -> PaymentService
            -> PaymentGateway
        -> OrderRepository
        -> DomainEventPublisher
            -> OrderPaidListener
```

Mỗi tầng có thể có một phép đo hợp lệ:

| Tầng | Metric phù hợp | Đơn vị |
|---|---|---|
| HTTP controller/server instrumentation | `http.server.requests` | HTTP request |
| Application service | `business.order.process` | Lần chạy use case |
| Payment service | `business.payment.authorize` | Lần thử authorize |
| Repository | `repository.calls` hoặc Timer riêng | Lần gọi repository |
| Domain event listener | `business.orders.paid` | Sự kiện/order được xác nhận theo định nghĩa |

Các metric này không trùng nếu chúng có tên và ngữ nghĩa riêng. Đếm trùng xảy ra khi controller và service cùng tăng `business.orders.created` cho một lần tạo đơn, hoặc listener và service cùng tăng `business.orders.paid` cho cùng một lần chuyển trạng thái.

Đừng xóa instrumentation ở các tầng khác chỉ vì dashboard có nhiều con số. Hãy phân biệt ranh giới đo và chỉ loại bỏ những lần ghi lặp cùng một ngữ nghĩa.

## 4. Anti-pattern: controller và service cùng tăng một Counter

Ví dụ lỗi:

```java
@RestController
class OrderController {

    private final OrderService orderService;
    private final Counter createdOrders;

    OrderController(OrderService orderService, MeterRegistry registry) {
        this.orderService = orderService;
        this.createdOrders = registry.counter("business.orders.created");
    }

    @PostMapping("/orders")
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        createdOrders.increment();
        return orderService.create(request);
    }
}

@Service
class OrderService {

    private final Counter createdOrders;

    OrderService(MeterRegistry registry) {
        this.createdOrders = registry.counter("business.orders.created");
    }

    Order create(CreateOrderRequest request) {
        Order order = persist(request);
        createdOrders.increment();
        return order;
    }
}
```

Một request gọi controller rồi gọi service. Cả hai Counter có cùng tên và tag set, vì vậy cùng đại diện cho một meter identity trong registry. Mỗi nơi gọi `increment()` làm giá trị tăng một lần; tổng cộng tăng hai.

Sửa bằng cách chọn một nơi chịu trách nhiệm cho metric. Nếu định nghĩa là số order được tạo thành công, service nên tăng sau khi thao tác lưu thành công:

```java
@Service
class OrderService {

    private final MeterRegistry registry;

    OrderService(MeterRegistry registry) {
        this.registry = registry;
    }

    Order create(CreateOrderRequest request) {
        Order order = persist(request);

        registry.counter("business.orders.created").increment();

        return order;
    }
}
```

Controller chỉ điều phối HTTP và không tăng lại business Counter. Nếu cần đếm request, dùng HTTP server metric vốn được framework instrument hoặc một metric riêng như `api.order.create.requests` với định nghĩa request rõ ràng.

## 5. Cùng meter identity không có nghĩa Micrometer tự khử lần ghi

Micrometer xác định meter dựa trên tên và các thuộc tính nhận dạng như tag set. Khi gọi `registry.counter(name, tags...)` nhiều lần với cùng identity, registry thường trả về meter đã đăng ký tương ứng thay vì tạo một Counter độc lập cho mỗi lời gọi.

Điều này tránh tạo meter duplicate cùng identity, nhưng không tự phát hiện hai tầng đang đo cùng một sự kiện.

Ví dụ:

```java
Counter first = registry.counter(
    "business.orders.created",
    "channel", "web"
);

Counter second = registry.counter(
    "business.orders.created",
    "channel", "web"
);

first.increment();
second.increment();
```

Hai biến tham chiếu đến cùng meter identity trong registry; hai lần gọi `increment()` vẫn tạo tổng tăng là 2. Registry không biết rằng ứng dụng chỉ có một order.

Ngược lại, nếu tag khác nhau, đó là hai meter identity riêng:

```java
registry.counter("business.orders.created", "channel", "web");
registry.counter("business.orders.created", "channel", "mobile");
```

Hai meter này có thể hợp lệ nếu channel là chiều phân tích mong muốn. Trước khi tìm lỗi, hãy so sánh cả tên và toàn bộ tag set, không chỉ tên metric.

## 6. Timer cũng có thể bị đếm hai lần

Timer không chỉ đo thời gian. Mỗi lần record một duration, Timer cũng tăng count. Nếu cùng một thao tác được record hai lần vào cùng Timer identity, cả count và total time đều tăng hai lần.

Ví dụ lỗi:

```java
Timer orderTimer = registry.timer("business.order.process");

Order process(Order order) {
    return orderTimer.record(() -> {
        return applicationService.process(order);
    });
}

class OrderApplicationService {
    private final Timer orderTimer;

    OrderApplicationService(MeterRegistry registry) {
        this.orderTimer = registry.timer("business.order.process");
    }

    Order process(Order order) {
        return orderTimer.record(() -> performWorkflow(order));
    }
}
```

Một lần gọi controller đo toàn bộ service; service lại đo cùng workflow bằng cùng tên và tag. Timer count tăng hai, total time là tổng duration của cả hai lần đo. Vì hai khoảng đo có thể lồng nhau, không thể diễn giải tổng time như thời gian thực tế của hai thao tác độc lập.

Nếu cần đo cả hai ranh giới, đặt tên riêng:

- `http.server.requests` cho request.
- `business.order.process` cho workflow.
- `business.payment.authorize` cho lời gọi payment.

Nếu cả hai tầng chỉ nhằm đo cùng một workflow, giữ một Timer tại ranh giới được chọn.

## 7. Observation lồng nhau không mặc nhiên là double count

Observation cha và con thường đại diện cho các thao tác khác nhau. Ví dụ `business.order.process` bao quanh `business.payment.authorize`. Khi meter handler tạo Timer cho mỗi Observation, hai Timer có tên khác nhau sẽ đo hai ranh giới khác nhau và đây là điều mong muốn.

Cần kiểm tra các trường hợp sau:

- Parent và child vô tình dùng cùng Observation name và cùng low-cardinality tags.
- Cùng một thao tác được instrument tự động bởi framework và lại được bọc bằng Observation tùy chỉnh có cùng semantics.
- Một meter handler bị đăng ký nhiều lần vào cùng ObservationRegistry.
- Custom handler tự ghi Timer trong khi handler metrics mặc định cũng ghi Timer cùng tên/tag.

Ví dụ parent và child cùng dùng tên:

```java
Observation.createNotStarted("business.operation", registry)
    .observe(() ->
        Observation.createNotStarted("business.operation", registry)
            .observe(this::doWork)
    );
```

Nếu cả hai Observation cùng được meter handler chuyển thành cùng Timer identity, một lần workflow có thể ghi hai mẫu vào Timer đó: một mẫu cho parent và một mẫu cho child. Điều này không phải lỗi của Observation API; instrumentation đã chọn cùng một metric identity cho hai ranh giới.

Đặt tên rõ ràng cho từng cấp:

```java
Observation.createNotStarted("business.order.process", registry)
    .observe(() ->
        Observation.createNotStarted("business.payment.authorize", registry)
            .observe(this::authorizePayment)
    );
```

Trace vẫn thể hiện quan hệ cha con, còn metrics được tổng hợp riêng theo từng loại thao tác.

## 8. Phân biệt Observation metrics handler và tracing handler

Một ObservationRegistry có thể có nhiều handler. Một handler metrics tạo Timer hoặc meter; tracing handler tạo span. Chúng cùng nhận lifecycle nhưng tạo ra loại tín hiệu khác nhau.

Không nhầm việc có cả hai handler với double count. Một Observation có thể tạo một Timer và một span mà không phải ghi hai Counter.

Nguy cơ xuất hiện khi:

- Đăng ký hai meter handlers có cùng chức năng.
- Tự tạo một Timer thủ công quanh thao tác đã được Observation metrics handler đo bằng cùng tên/tag.
- Framework đã instrument HTTP server/client nhưng ứng dụng lại instrument thêm cùng boundary bằng cùng meter name.
- Handler tùy chỉnh gọi `record()` hoặc `increment()` cùng meter identity với handler khác.

Trong Spring Boot, kiểm tra các handler đã được auto-configure trước khi tự đăng ký thêm. Không thêm `DefaultMeterObservationHandler` thủ công nếu registry đã có handler metrics tương ứng. Khi custom handler cần metric riêng, dùng tên và semantics riêng, hoặc thay thế cấu hình có chủ đích theo phiên bản framework.

## 9. Đăng ký nhiều MeterRegistry và CompositeMeterRegistry

Composite registry chuyển phép ghi đến các registry con đã được gắn. Nếu một Counter được ghi qua CompositeMeterRegistry, các registry con có thể nhận cùng phép đo để export đến các backend khác nhau.

Điều đó thường là fan-out có chủ đích, không có nghĩa một lần increment trở thành nhiều sự kiện nghiệp vụ trong cùng một backend.

Tuy nhiên, dashboard có thể cộng trùng nếu:

- Cùng service được scrape bởi hai Prometheus jobs.
- Cùng metrics được gửi đến hai tenant/project rồi dashboard hợp nhất dữ liệu.
- Query bỏ qua label phân biệt `job`, `cluster`, `replica` hoặc nguồn export.
- Cả registry trực tiếp và collector cùng gửi một bộ metrics vào cùng nơi nhận.

Kiểm tra đường đi dữ liệu và label nguồn trước khi thay đổi instrumentation. Không gỡ child registry chỉ vì thấy cùng metric xuất hiện ở hai backend nếu đó là cấu hình fan-out mong muốn.

## 10. Event listener và message redelivery

Một nguồn đếm trùng phổ biến là event được xử lý nhiều lần. Broker có thể giao message theo cơ chế at-least-once; consumer có thể xử lý xong nghiệp vụ nhưng chết trước khi acknowledge. Message được giao lại và listener chạy lần nữa.

Nếu listener tăng Counter mỗi lần nhận message:

```java
@KafkaListener(topics = "order-paid")
void onOrderPaid(OrderPaidEvent event) {
    registry.counter("business.orders.paid").increment();
    updateProjection(event);
}
```

Cùng một event có thể làm Counter tăng nhiều lần. Nếu định nghĩa metric là số delivery attempt, cách đếm này có thể đúng nhưng cần đổi tên thành `messaging.order_paid.deliveries`. Nếu định nghĩa là số order duy nhất đã thanh toán, listener phải idempotent trước khi tăng Counter.

Một mẫu xử lý:

```java
@KafkaListener(topics = "order-paid")
void onOrderPaid(OrderPaidEvent event) {
    boolean firstProcessing = processedEvents.insertIfAbsent(event.eventId());

    if (!firstProcessing) {
        return;
    }

    updateProjection(event);
    registry.counter("business.orders.paid").increment();
}
```

Đây chỉ là phác thảo. Trong hệ thống thật, việc ghi nhận event ID và cập nhật trạng thái cần được bảo vệ bằng transaction hoặc cơ chế idempotency bền vững phù hợp. Một cấu trúc in-memory như Set không đủ cho nhiều instance hoặc restart.

## 11. Retry không nhất thiết là một entity mới

Một lần thanh toán có thể thử gọi provider nhiều lần:

```text
Payment intent P-42
    Attempt 1 -> timeout
    Attempt 2 -> connection reset
    Attempt 3 -> approved
```

Các metric sau trả lời câu hỏi khác nhau:

| Metric | Giá trị dự kiến | Ý nghĩa |
|---|---:|---|
| `business.payment.intents` | 1 | Một ý định thanh toán |
| `business.payment.attempts` | 3 | Ba lần thử gọi provider |
| `business.payment.approved` | 1 | Một kết quả được chấp thuận |
| `business.orders.paid` | 1 | Một order chuyển sang PAID |

Nếu cùng một Counter `business.orders.paid` được tăng ở mỗi attempt, retry làm số order đã thanh toán tăng sai. Hãy đếm attempt tại vòng retry và đếm business outcome tại điểm trạng thái được xác nhận.

Không dùng payment reference hoặc order ID làm tag để khử trùng. Deduplication phải dựa trên khóa nghiệp vụ/event ID trong kho trạng thái phù hợp; metric tag chỉ phục vụ nhóm dữ liệu.

## 12. Transaction rollback và thời điểm ghi nhận

Nếu Counter tăng trước khi transaction commit, transaction có thể rollback nhưng Counter không tự giảm. Đây không nhất thiết là double count, nhưng tạo số liệu vượt số entity đã commit và dễ bị hiểu là lỗi đếm.

Ví dụ:

```java
@Transactional
public Order createOrder(CreateOrderRequest request) {
    Order order = repository.save(new Order(request));

    registry.counter("business.orders.created").increment();

    validateSomethingThatMayFail(order);

    return order;
}
```

Nếu `validateSomethingThatMayFail` ném exception và transaction rollback, Counter vẫn đã tăng.

Với business event gắn với commit, có thể phát event trong transaction và xử lý metric sau commit:

```java
@Transactional
public Order createOrder(CreateOrderRequest request) {
    Order order = repository.save(new Order(request));
    events.publishEvent(new OrderCreated(order.id()));
    return order;
}

@Component
class OrderMetricsListener {

    private final MeterRegistry registry;

    OrderMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void onCreated(OrderCreated event) {
        registry.counter("business.orders.created").increment();
    }
}
```

Cách này tránh tăng metric khi transaction rollback. Nhưng listener sau commit trong cùng process vẫn có thể không chạy nếu process dừng đúng thời điểm sau commit; nếu cần độ tin cậy cao cho business event, dùng transactional outbox hoặc event pipeline bền vững. Metrics vẫn là số liệu vận hành tổng hợp, không phải sổ cái.

## 13. Đừng cộng Timer count với Counter count cho cùng một khái niệm

Timer đã có count biểu thị số lần record duration. Nếu đồng thời có Counter `business.order.processed` được tăng đúng một lần cho mỗi lần Timer record, cộng hai giá trị sẽ đếm cùng sự kiện hai lần.

Ví dụ:

- `business.order.process` Timer count = 100.
- `business.orders.processed` Counter = 100.

Không tính `100 + 100 = 200` order processed. Hai meter biểu diễn hai phép đo cho cùng 100 lần xử lý. Nếu chỉ cần số lần xử lý, chọn một nguồn count rõ ràng. Nếu cần cả duration và business event, giữ cả hai nhưng dashboard không cộng chúng.

Với Prometheus Timer, series `_count` thường biểu diễn số lần record; `_sum` biểu diễn tổng thời lượng. Tên export thực tế phụ thuộc registry và naming convention. Kiểm tra exposition trước khi viết query.

## 14. Kiểm tra toàn bộ điểm ghi trong code

Khi phát hiện tăng gấp đôi, tìm mọi điểm cập nhật cùng meter:

- `registry.counter(...).increment()`
- `Counter.builder(...).register(...).increment()`
- `Timer.record(...)`
- `Timer.Sample.stop(...)`
- `DistributionSummary.record(...)`
- Observation handlers và custom handlers
- Event listeners, message consumers và retry callbacks
- AOP interceptor, servlet filter và framework auto-instrumentation

So sánh meter name, tag keys, tag values và loại meter. Cùng tên nhưng khác tag không phải cùng meter identity; cùng tên và cùng tag có thể được registry gộp vào một meter.

Có thể duyệt registry trong môi trường phát triển:

```java
registry.getMeters().stream()
    .filter(meter -> meter.getId().getName().startsWith("business.order"))
    .forEach(meter -> System.out.println(
        meter.getId().getName() + " " + meter.getId().getTags()
    ));
```

Inventory cho biết meter identities đã đăng ký. Nó không cho biết code path nào gọi increment. Để xác định nơi ghi, dùng tìm kiếm code, debugger, profiler hoặc custom test handler; không bật log từng lần increment trong production nếu volume cao.

## 15. Dùng test để tái hiện đúng một thao tác

Unit test với `SimpleMeterRegistry` có thể chứng minh một lần gọi service làm Counter tăng đúng một lần:

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderServiceMetricsTest {

    @Test
    void countsOneCreatedOrderOnce() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        OrderService service = new OrderService(registry);

        service.create(new CreateOrderRequest("web"));

        assertThat(
            registry.get("business.orders.created").counter().count()
        ).isEqualTo(1.0);

        registry.close();
    }
}
```

Đây là test cho service. Nếu controller cũng tăng cùng meter, hãy viết integration test gọi HTTP endpoint và kiểm tra kết quả cuối cùng là một. Test từng lớp riêng lẻ có thể đều pass trong khi toàn bộ call chain vẫn tăng hai lần.

Một test bổ sung có thể xác nhận retry count khác với entity count:

```java
@Test
void countsAttemptsSeparatelyFromPaidOrders() {
    PaymentWorkflow workflow = new PaymentWorkflow(registry, fakeGatewayWithTwoFailuresThenApproval());

    workflow.pay(order);

    assertThat(registry.get("business.payment.attempts").counter().count())
        .isEqualTo(3.0);

    assertThat(registry.get("business.orders.paid").counter().count())
        .isEqualTo(1.0);
}
```

Các class và fake gateway trong ví dụ là thành phần minh họa. Trong dự án thật, dùng fixture phù hợp và bảo đảm registry mới cho mỗi test để trạng thái meter không rò rỉ giữa các test.

## 16. Test duplicate event và transaction semantics

Với event consumer, test hai lần nhận cùng event ID và xác nhận business metric chỉ tăng một lần:

```java
@Test
void duplicateDeliveryDoesNotCountAnotherPaidOrder() {
    OrderPaidEvent event = new OrderPaidEvent("evt-42", "order-7");

    listener.onOrderPaid(event);
    listener.onOrderPaid(event);

    assertThat(registry.get("business.orders.paid").counter().count())
        .isEqualTo(1.0);
}
```

Test cần dùng implementation idempotency thật hoặc test double phản ánh đúng semantics của kho lưu event ID. Nếu idempotency chỉ nằm trong memory của một instance, integration test nhiều instance hoặc restart vẫn có thể phát hiện lỗi.

Với transaction, cần xác nhận rollback không làm tăng metric nếu metric định nghĩa theo sự kiện đã commit. Nếu dùng `@TransactionalEventListener(AFTER_COMMIT)`, integration test cần chạy trong transaction thực và xác nhận listener không chạy khi rollback.

## 17. Kiểm tra dashboard và PromQL

Một query có thể cộng trùng dù code chỉ tăng một lần nếu dashboard chọn nhiều series hoặc nhiều nguồn scrape.

Ví dụ đếm tốc độ đơn hàng theo service:

```promql
sum by (service) (
  rate(business_orders_created_total[5m])
)
```

Nếu cùng service được scrape bởi hai job, query có thể cộng cả hai. Kiểm tra các label nguồn:

```promql
sum by (job, instance, service) (
  rate(business_orders_created_total[5m])
)
```

Query thứ hai giúp thấy từng luồng `job` và `instance`. Nếu hai job scrape cùng một endpoint, sửa discovery/scrape config hoặc chọn một nguồn có thẩm quyền; không tùy tiện dùng `max` để che duplicate vì có thể làm mất số liệu thật khi nhiều instance xử lý traffic riêng.

Khi aggregate nhiều replica, `sum` thường đúng nếu mỗi replica chỉ ghi các sự kiện nó thực sự xử lý. Nếu cùng một event được broadcast đến nhiều consumer group hoặc xử lý lặp ở nhiều replica, cần sửa semantics/idempotency ở nguồn trước khi aggregate.

## 18. Phân biệt lỗi đếm trùng trong ứng dụng và trong backend

| Dấu hiệu | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Một request trong test làm Counter tăng 2 | Hai điểm increment trong call chain | Tìm tất cả nơi ghi cùng meter identity |
| Timer count gấp đôi sau thêm Observation | Timer thủ công và Observation handler cùng record | So sánh tên/tag và handler |
| Counter tăng lại sau redelivery | Consumer không idempotent | Gửi lại cùng event ID |
| Counter tăng dù transaction rollback | Ghi trước commit | Test rollback và kiểm tra listener timing |
| Registry có một meter nhưng backend có hai luồng | Hai scrape jobs hoặc hai exporters | Kiểm tra job, instance, remote-write path |
| Chỉ dashboard tổng bị gấp đôi | Query cộng hai label sets hoặc panel cộng hai metric | Xem raw series và expression |
| Chỉ sau deploy mới tăng gấp đôi | Hai version/pod cùng phát event hoặc rollout overlap | Kiểm tra deployment, consumer group và source labels |

Cần xác định nơi số liệu bị nhân đôi trước khi thay đổi code. Nếu raw meter trong một instance đã tăng hai lần, lỗi nằm trước hoặc tại registry. Nếu raw meter đúng nhưng backend query gấp đôi, tập trung vào export, scrape, labels và query.

## 19. Quy tắc thiết kế để tránh đếm trùng

- Mỗi business metric có một định nghĩa và một owner chịu trách nhiệm ghi.
- Đếm entity/state transition tại điểm nghiệp vụ có thẩm quyền.
- Đếm HTTP request ở HTTP instrumentation; đếm use case ở application boundary; đếm dependency call tại adapter.
- Dùng tên riêng cho các ranh giới khác nhau.
- Không tăng cùng business Counter ở cả controller và service.
- Không thêm meter handler mặc định trùng với handler Spring Boot đã cấu hình.
- Dùng idempotency bền vững cho event consumer và retry.
- Ghi business event sau commit hoặc qua outbox khi cần độ tin cậy cao.
- Không cộng Timer count và Counter count nếu chúng cùng biểu diễn một tập sự kiện.
- Kiểm tra label nguồn khi tổng hợp nhiều registry, job hoặc replica.

## 20. Checklist điều tra khi số đếm tăng hai lần

- [ ] Metric đang đếm request, invocation, attempt, delivery, event hay entity?
- [ ] Định nghĩa “một lần” đã được viết rõ chưa?
- [ ] Có nhiều tầng cùng gọi `increment()` cho cùng meter name/tag không?
- [ ] Có Timer hoặc Observation handler ghi cùng ranh giới hai lần không?
- [ ] Parent và child Observation có vô tình dùng cùng name/tag không?
- [ ] Framework auto-instrumentation có đo thao tác rồi không?
- [ ] Có custom handler bị đăng ký trùng không?
- [ ] Có retry hoặc message redelivery không?
- [ ] Consumer có idempotency theo event ID/business key không?
- [ ] Counter có tăng trước transaction commit không?
- [ ] Dashboard có cộng Counter với Timer count không?
- [ ] Prometheus có scrape cùng endpoint từ nhiều job không?
- [ ] Query có bỏ qua label `job`, `instance` hoặc cluster không?
- [ ] Integration test gọi toàn bộ call chain đã xác nhận đúng một lần chưa?

Đếm trùng thường là vấn đề về ngữ nghĩa và quyền sở hữu phép đo. Micrometer gộp các lần đăng ký cùng meter identity nhưng vẫn ghi nhận mọi lần ứng dụng gọi increment hoặc record. Hãy xác định rõ đơn vị được đếm, đặt một điểm ghi có thẩm quyền cho metric đó và đặt tên riêng cho request, use case, dependency call, attempt và business event. Sau đó kiểm thử toàn bộ call chain, event retry, transaction và query backend để tìm đúng nơi số liệu bị nhân đôi.

## Tài liệu tham khảo

- [Micrometer Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html) — semantics của Counter và cách tăng số đếm.
- [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html) — count, total time và cách record duration.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html) — Observation lifecycle và handlers.
- [Micrometer Meter Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html) — meter identity và registry behavior.
- [Spring Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — xử lý event theo transaction phase.
- [Prometheus Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/) — label sets và cách truy vấn series.

