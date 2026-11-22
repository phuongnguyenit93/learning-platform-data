# Unit test nghiệp vụ Java độc lập với cloud runtime

Java function trong môi trường serverless thường được gọi qua HTTP, queue hoặc event trigger. Nếu phần nghiệp vụ được viết trực tiếp bên trong handler và phụ thuộc vào AWS SDK, Google Cloud client, environment variables hoặc network, mỗi lần kiểm thử đều phải dựng thêm nhiều thành phần bên ngoài. Test khi đó chậm, dễ lỗi do môi trường và khó xác định một thất bại đến từ quy tắc nghiệp vụ hay từ hạ tầng.

Cách thiết kế hiệu quả là giữ **domain và use case Java độc lập với cloud runtime**. Handler chỉ chuyển đổi request/event thành lệnh nội bộ; adapter giao tiếp với database, queue hoặc secret store thông qua interface; phần nghiệp vụ nhận các dependency đó qua constructor. Unit test có thể chạy trong JVM thông thường với dữ liệu giả lập, không cần credential cloud, network hoặc function emulator.

Bài học này hướng dẫn cách tách nghiệp vụ khỏi AWS Lambda, Cloud Run và event SDK; viết unit test bằng JUnit 5; dùng fake hoặc mock tại ranh giới; kiểm soát thời gian và ID để test có tính xác định; và nhận biết những bảo đảm cần integration test ở database hoặc cloud thật.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao unit test nghiệp vụ không nên khởi động cloud runtime.
- Tách domain, application/use case và infrastructure adapter.
- Thiết kế port/interface để nghiệp vụ không phụ thuộc AWS/GCP SDK.
- Viết unit test cho business rule, boundary condition và error path bằng JUnit 5.
- Dùng fake repository, fake inventory và mock đúng ranh giới.
- Inject Clock, ID generator và configuration để kiểm thử xác định.
- Kiểm tra idempotency ở cấp use case và hiểu giới hạn của test trong bộ nhớ.
- Tách unit test, adapter test, contract test và integration test.
- Tránh test phụ thuộc thời gian, mạng, thứ tự thực thi hoặc chi tiết nội bộ.
- Tổ chức test suite phù hợp cho pipeline CI của Java serverless.

## 1. Mục tiêu của unit test trong serverless

Unit test kiểm tra một đơn vị nhỏ của code trong môi trường được kiểm soát. Với nghiệp vụ Java, đơn vị có thể là:

- Một domain policy tính giá, thuế, giới hạn hoặc trạng thái.
- Một aggregate kiểm tra transition hợp lệ.
- Một use case điều phối các bước tạo đơn, giữ hàng hoặc xác nhận thanh toán.
- Một validator kiểm tra event schema hoặc dữ liệu đầu vào.
- Một mapper chuyển dữ liệu từ adapter sang command nội bộ.

Unit test không cần chứng minh AWS Lambda có thể nhận event thật, IAM role có quyền đọc SQS hay Cloud Run có thể bind cổng HTTP. Những việc đó thuộc integration/deployment test. Unit test cần trả lời câu hỏi: **với đầu vào và trạng thái đã biết, quy tắc nghiệp vụ có tạo ra kết quả đúng không?**

| Loại test | Phạm vi | Có cần cloud runtime? |
|---|---|---|
| Domain unit test | Quy tắc và model thuần Java | Không |
| Use case unit test | Luồng nghiệp vụ với port giả lập | Không |
| Adapter test | Mapping HTTP/event, response và exception | Thường không; dùng event DTO hoặc fixture |
| Contract test | Định dạng request/response giữa service | Không nhất thiết; có thể chạy độc lập |
| Repository/client integration test | SQL, transaction, serialization hoặc SDK adapter | Có thể cần database/emulator hoặc dịch vụ test |
| Cloud integration test | IAM, trigger, event source mapping, network và deployment | Có môi trường cloud test |

Các tầng test bổ sung cho nhau. Một unit test chạy nhanh không chứng minh quyền IAM đúng; một integration test qua cloud không thay thế hàng trăm trường hợp boundary của business rule.

## 2. Tách domain khỏi cloud runtime

Một kiến trúc thường dùng có ba vùng:

1. **Domain:** entity, value object, policy và quy tắc nghiệp vụ. Không import AWS/GCP SDK, Spring hoặc framework HTTP.
2. **Application:** use case điều phối nghiệp vụ và định nghĩa các port cần thiết như repository, inventory, payment hoặc event publisher.
3. **Adapters/infrastructure:** Lambda handler, HTTP controller, queue listener, database repository và cloud client triển khai các port.

~~~mermaid
flowchart TD
    T["Unit tests"] --> D["Domain rules"]
    T --> U["Application use cases"]
    H["HTTP / Lambda / Pub/Sub adapter"] --> U
    Q["Queue / Event adapter"] --> U
    U --> P["Ports / interfaces"]
    R["Repository adapter"] -. "implements" .-> P
    I["Inventory / payment adapter"] -. "implements" .-> P
    E["Event publisher adapter"] -. "implements" .-> P
    R --> DB["Database"]
    I --> EXT["External services"]
    E --> BUS["Queue / Event bus"]
~~~

Dependency hướng vào trong: adapter phụ thuộc application; application phụ thuộc abstraction/port; domain không biết cloud tồn tại. Nhờ đó, unit test có thể tạo use case bằng fake object mà không khởi tạo Lambda context, Spring container hoặc SDK client.

### Ví dụ cấu trúc package

~~~text
com.example.orders
  domain/
    Order.java
    OrderLine.java
    OrderPricingPolicy.java
    PriceBreakdown.java
  application/
    PlaceOrderCommand.java
    PlaceOrderUseCase.java
    PlaceOrderResult.java
    port/
      OrderRepository.java
      InventoryPort.java
      OrderIdGenerator.java
  adapter/
    inbound/
      lambda/
      http/
      messaging/
    outbound/
      dynamodb/
      jdbc/
      sqs/
      payment/
~~~

Đây là cách tổ chức gợi ý; package có thể khác theo dự án. Điều quan trọng là code domain/application không import class như `APIGatewayProxyRequestEvent`, `SQSEvent`, `Context`, `DynamoDbClient` hoặc `PubSubMessage`.

## 3. Viết business rule thành Java thuần

Xét quy tắc tính giá đơn hàng: cộng thành tiền các dòng, áp dụng giảm giá 10% khi subtotal đạt ít nhất 1.000.000 đồng, sau đó tính thuế 8% trên số tiền sau giảm giá. Thuế và giảm giá được làm tròn đến đồng gần nhất theo HALF_UP.

Quy tắc này không cần database, HTTP hay cloud. Có thể biểu diễn bằng value object và policy.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice) {

    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        Objects.requireNonNull(unitPrice, "unitPrice is required");
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice cannot be negative");
        }
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

Policy tính giá:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

public final class OrderPricingPolicy {
    private static final BigDecimal DISCOUNT_THRESHOLD =
            new BigDecimal("1000000");
    private static final BigDecimal DISCOUNT_RATE =
            new BigDecimal("0.10");
    private static final BigDecimal TAX_RATE =
            new BigDecimal("0.08");

    public PriceBreakdown calculate(List<OrderLine> lines) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("order must contain at least one line");
        }

        BigDecimal subtotal = lines.stream()
                .map(OrderLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal discount = subtotal.compareTo(DISCOUNT_THRESHOLD) >= 0
                ? subtotal.multiply(DISCOUNT_RATE)
                        .setScale(0, RoundingMode.HALF_UP)
                : BigDecimal.ZERO;

        BigDecimal taxableAmount = subtotal.subtract(discount);
        BigDecimal tax = taxableAmount.multiply(TAX_RATE)
                .setScale(0, RoundingMode.HALF_UP);
        BigDecimal total = taxableAmount.add(tax);

        return new PriceBreakdown(subtotal, discount, tax, total);
    }
}
~~~

Kết quả được trả trong object bất biến:

~~~java
import java.math.BigDecimal;

public record PriceBreakdown(
        BigDecimal subtotal,
        BigDecimal discount,
        BigDecimal tax,
        BigDecimal total) {
}
~~~

Ví dụ này cố định một chính sách thuế/giảm giá để minh họa test. Hệ thống thật có thể phải tính theo currency, thời điểm hiệu lực, loại khách hàng, vùng thuế hoặc promotion. Các quyết định đó nên nằm trong domain policy có test riêng, không được ẩn trong Lambda handler.

### Test boundary của business rule

Dùng JUnit 5 để kiểm tra trường hợp dưới ngưỡng, đúng ngưỡng, trên ngưỡng và dữ liệu không hợp lệ.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderPricingPolicyTest {
    private final OrderPricingPolicy policy = new OrderPricingPolicy();

    @Test
    void doesNotApplyDiscountBelowThreshold() {
        var result = policy.calculate(List.of(
                new OrderLine("SKU-1", 1, new BigDecimal("999999"))));

        assertMoney("999999", result.subtotal());
        assertMoney("0", result.discount());
        assertMoney("80000", result.tax());
        assertMoney("1079999", result.total());
    }

    @Test
    void appliesDiscountAtThreshold() {
        var result = policy.calculate(List.of(
                new OrderLine("SKU-1", 2, new BigDecimal("500000"))));

        assertMoney("1000000", result.subtotal());
        assertMoney("100000", result.discount());
        assertMoney("72000", result.tax());
        assertMoney("972000", result.total());
    }

    @Test
    void rejectsEmptyOrder() {
        assertThrows(
                IllegalArgumentException.class,
                () -> policy.calculate(List.of()));
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderLine(
                        "SKU-1", 0, new BigDecimal("10000")));
    }

    private static void assertMoney(String expected, BigDecimal actual) {
        assertEquals(0, new BigDecimal(expected).compareTo(actual));
    }
}
~~~

Dùng `BigDecimal.compareTo` để so sánh giá trị tiền vì `equals` còn xét scale. Ví dụ `1.0` và `1.00` có cùng giá trị số nhưng không bằng nhau theo `equals`.

Các test này chạy trong JVM bình thường. Không cần AWS credentials, LocalStack, Google Cloud emulator hoặc Docker.

## 4. Tách use case bằng port/interface

Domain policy đã độc lập, nhưng use case thường cần repository, inventory hoặc ID generator. Application nên định nghĩa interface cho các nhu cầu đó.

Ví dụ các port:

~~~java
import java.util.Optional;

public interface OrderRepository {
    Optional<Order> findByIdempotencyKey(String idempotencyKey);
    void save(Order order);
}

public interface InventoryPort {
    boolean reserve(java.util.List<OrderLine> lines);
}

public interface OrderIdGenerator {
    String nextId();
}
~~~

Model nội bộ:

~~~java
import java.time.Instant;
import java.util.List;

public record Order(
        String id,
        String customerId,
        List<OrderLine> lines,
        PriceBreakdown price,
        String idempotencyKey,
        Instant createdAt) {

    public Order {
        lines = List.copyOf(lines);
    }
}

public record PlaceOrderCommand(
        String customerId,
        List<OrderLine> lines,
        String idempotencyKey) {

    public PlaceOrderCommand {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("order must contain lines");
        }
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new IllegalArgumentException("idempotencyKey is required");
        }
        lines = List.copyOf(lines);
    }
}

public record PlaceOrderResult(String orderId, java.math.BigDecimal total) {
}
~~~

Application định nghĩa exception nghiệp vụ:

~~~java
public final class OutOfStockException extends RuntimeException {
    public OutOfStockException() {
        super("One or more order lines cannot be reserved");
    }
}
~~~

Use case phụ thuộc abstraction và nhận thời gian qua `Clock`:

~~~java
import java.time.Clock;
import java.util.Optional;

public final class PlaceOrderUseCase {
    private final OrderRepository orders;
    private final InventoryPort inventory;
    private final OrderIdGenerator ids;
    private final OrderPricingPolicy pricing;
    private final Clock clock;

    public PlaceOrderUseCase(
            OrderRepository orders,
            InventoryPort inventory,
            OrderIdGenerator ids,
            OrderPricingPolicy pricing,
            Clock clock) {
        this.orders = orders;
        this.inventory = inventory;
        this.ids = ids;
        this.pricing = pricing;
        this.clock = clock;
    }

    public PlaceOrderResult execute(PlaceOrderCommand command) {
        Optional<Order> existing =
                orders.findByIdempotencyKey(command.idempotencyKey());

        if (existing.isPresent()) {
            return toResult(existing.get());
        }

        PriceBreakdown price = pricing.calculate(command.lines());

        if (!inventory.reserve(command.lines())) {
            throw new OutOfStockException();
        }

        Order order = new Order(
                ids.nextId(),
                command.customerId(),
                command.lines(),
                price,
                command.idempotencyKey(),
                clock.instant());

        orders.save(order);
        return toResult(order);
    }

    private static PlaceOrderResult toResult(Order order) {
        return new PlaceOrderResult(order.id(), order.price().total());
    }
}
~~~

Use case không biết nó đang chạy trong Lambda, Cloud Run hay một JVM thông thường. Nó chỉ biết các port cần thiết.

Thứ tự reserve rồi save trong ví dụ đơn giản hóa. Hệ thống thực tế phải xử lý trường hợp inventory đã giữ thành công nhưng lưu order thất bại, hoặc request đồng thời cùng idempotency key. Có thể cần transaction, reservation expiry, compensation/saga và transactional outbox. Unit test có thể kiểm tra các nhánh điều phối, nhưng không chứng minh transaction phân tán hoặc unique constraint ở database hoạt động đúng.

## 5. Dùng fake để kiểm thử use case

Một **fake** là implementation đơn giản của port, thường giữ dữ liệu trong bộ nhớ hoặc trả kết quả được cấu hình. Fake giúp test luồng nghiệp vụ mà không cần mock từng method hoặc dựng cloud SDK.

Ví dụ test repository trong bộ nhớ:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> byIdempotencyKey = new HashMap<>();

    @Override
    public Optional<Order> findByIdempotencyKey(String key) {
        return Optional.ofNullable(byIdempotencyKey.get(key));
    }

    @Override
    public void save(Order order) {
        byIdempotencyKey.put(order.idempotencyKey(), order);
    }

    int size() {
        return byIdempotencyKey.size();
    }
}
~~~

Fake inventory cho phép test thành công và hết hàng:

~~~java
import java.util.List;

final class FakeInventory implements InventoryPort {
    private final boolean canReserve;
    private int reserveCalls;

    FakeInventory(boolean canReserve) {
        this.canReserve = canReserve;
    }

    @Override
    public boolean reserve(List<OrderLine> lines) {
        reserveCalls++;
        return canReserve;
    }

    int reserveCalls() {
        return reserveCalls;
    }
}
~~~

Các fake này chỉ phục vụ unit test. Chúng không mô phỏng lock, transaction, consistency hoặc retry semantics của database thật.

### Test use case với Clock cố định

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class PlaceOrderUseCaseTest {
    private static final Instant NOW =
            Instant.parse("2026-11-17T10:15:30Z");

    private InMemoryOrderRepository orders;
    private FakeInventory inventory;
    private AtomicInteger idSequence;
    private Clock clock;

    @BeforeEach
    void setUp() {
        orders = new InMemoryOrderRepository();
        inventory = new FakeInventory(true);
        idSequence = new AtomicInteger();
        clock = Clock.fixed(NOW, ZoneOffset.UTC);
    }

    private PlaceOrderCommand command() {
        return new PlaceOrderCommand(
                "customer-7",
                List.of(new OrderLine(
                        "SKU-1", 2, new BigDecimal("300000"))),
                "idem-order-7");
    }

    private PlaceOrderUseCase useCase() {
        return new PlaceOrderUseCase(
                orders,
                inventory,
                () -> "order-" + idSequence.incrementAndGet(),
                new OrderPricingPolicy(),
                clock);
    }

    @Test
    void createsOrderAndReturnsCalculatedTotal() {
        PlaceOrderResult result = useCase().execute(command());

        assertEquals("order-1", result.orderId());
        assertEquals(
                0,
                new BigDecimal("648000").compareTo(result.total()));

        Order saved = orders
                .findByIdempotencyKey("idem-order-7")
                .orElseThrow();

        assertEquals("customer-7", saved.customerId());
        assertEquals(NOW, saved.createdAt());
        assertEquals(1, inventory.reserveCalls());
        assertEquals(1, orders.size());
    }

    @Test
    void rejectsOrderWhenInventoryCannotBeReserved() {
        inventory = new FakeInventory(false);

        assertThrows(
                OutOfStockException.class,
                () -> useCase().execute(command()));

        assertEquals(1, inventory.reserveCalls());
        assertEquals(0, orders.size());
        assertEquals(0, idSequence.get());
    }

    @Test
    void returnsExistingOrderForRepeatedIdempotencyKey() {
        Order existing = new Order(
                "order-existing",
                "customer-7",
                command().lines(),
                new PriceBreakdown(
                        new BigDecimal("600000"),
                        BigDecimal.ZERO,
                        new BigDecimal("48000"),
                        new BigDecimal("648000")),
                "idem-order-7",
                NOW);
        orders.save(existing);

        PlaceOrderResult result = useCase().execute(command());

        assertEquals("order-existing", result.orderId());
        assertEquals(0, inventory.reserveCalls());
        assertEquals(0, idSequence.get());
        assertEquals(1, orders.size());
    }
}
~~~

Test chứng minh các nhánh nghiệp vụ ở cấp use case: tạo đơn, hết hàng và nhận lại cùng idempotency key theo tuần tự. Nó không chứng minh hai request đồng thời không thể cùng vượt qua bước kiểm tra key. Bảo đảm đó phải được thực hiện ở adapter/database bằng unique constraint hoặc atomic claim và được kiểm tra bằng integration/concurrency test.

## 6. Fake, mock và stub: chọn công cụ đúng chỗ

Các khái niệm thường dùng:

- **Stub:** trả dữ liệu định trước để test một nhánh.
- **Fake:** implementation đơn giản nhưng hoạt động được, ví dụ repository trong bộ nhớ.
- **Mock:** object ghi nhận lời gọi để test tương tác hoặc mô phỏng lỗi.
- **Spy:** object thật được bọc để quan sát hoặc thay thế một phần hành vi.

Ưu tiên fake khi có thể mô tả trạng thái nghiệp vụ rõ ràng. Dùng mock khi cần kiểm tra một tương tác quan trọng hoặc mô phỏng một lỗi khó tạo bằng fake.

Ví dụ với Mockito:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Optional;
import org.junit.jupiter.api.Test;

class PlaceOrderUseCaseMockitoTest {
    @Test
    void doesNotSaveOrderWhenInventoryCannotBeReserved() {
        OrderRepository repository = mock(OrderRepository.class);
        InventoryPort inventory = mock(InventoryPort.class);
        PlaceOrderCommand command = new PlaceOrderCommand(
                "customer-7",
                java.util.List.of(new OrderLine(
                        "SKU-1", 1, new java.math.BigDecimal("100000"))),
                "idem-1");

        when(repository.findByIdempotencyKey("idem-1"))
                .thenReturn(Optional.empty());
        when(inventory.reserve(command.lines())).thenReturn(false);

        PlaceOrderUseCase useCase = new PlaceOrderUseCase(
                repository,
                inventory,
                () -> "unused",
                new OrderPricingPolicy(),
                java.time.Clock.fixed(
                        java.time.Instant.parse("2026-11-17T10:00:00Z"),
                        java.time.ZoneOffset.UTC));

        assertThrows(
                OutOfStockException.class,
                () -> useCase.execute(command));

        verify(repository).findByIdempotencyKey("idem-1");
        verify(inventory).reserve(command.lines());
        verify(repository, never()).save(any(Order.class));
    }
}
~~~

Ví dụ này dùng mock để mô phỏng inventory từ chối giữ hàng và xác minh use case không lưu order. Nó kiểm tra một tương tác có ý nghĩa nghiệp vụ. Tránh viết test chỉ xác nhận mock trả lại đúng giá trị mà chính test vừa cấu hình.

Không verify mọi lời gọi nội bộ. Nếu test yêu cầu một method private hoặc một chuỗi lời gọi không quan trọng phải xảy ra đúng thứ tự, test có thể gãy khi refactor dù hành vi bên ngoài vẫn đúng. Hãy kiểm tra kết quả, state quan sát được và các side effect có ý nghĩa nghiệp vụ.

## 7. Kiểm soát thời gian, ID và randomness

Serverless function có thể được gọi lại sau retry, chạy trên instance khác hoặc xử lý event đến trễ. Nếu business logic trực tiếp gọi `Instant.now()`, `UUID.randomUUID()` hoặc `new Random()`, test khó tái tạo chính xác kết quả.

Hãy inject nguồn không xác định:

| Nguồn | Cách inject | Lợi ích |
|---|---|---|
| Thời gian hiện tại | `Clock` | Dùng Clock.fixed trong test |
| ID | `OrderIdGenerator` hoặc Supplier | Dùng ID cố định, dễ assert |
| Randomness | Interface/RandomGenerator | Dùng seed cố định hoặc fake |
| Feature decision | Policy/config snapshot | Kiểm tra cả hai nhánh rõ ràng |
| Retry/backoff | Scheduler/Delay abstraction | Test số lần thử mà không sleep |

Ví dụ test thời gian hết hạn:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class ReservationExpiryTest {
    @Test
    void expiresAtConfiguredDeadline() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-17T10:00:00Z"),
                ZoneOffset.UTC);

        Instant expiresAt = clock.instant().plus(Duration.ofMinutes(15));

        assertEquals(
                Instant.parse("2026-11-17T10:15:00Z"),
                expiresAt);
    }
}
~~~

Đây là test cho phép tính thời gian. Nếu logic cần kiểm tra thời điểm trước/sau deadline, hãy truyền Clock vào domain service và test cả hai phía của ranh giới.

Không dùng `Thread.sleep()` để đợi timer trong unit test. Sleep làm test chậm và phụ thuộc scheduler của máy CI. Hãy điều khiển Clock hoặc scheduler giả lập.

## 8. Kiểm thử validation và error mapping ở adapter

Handler serverless là adapter inbound. Nó chuyển event/platform request thành command, gọi use case và chuyển kết quả thành response hoặc acknowledgement.

Ví dụ:

~~~text
API Gateway event
    -> Lambda handler / HTTP adapter
        -> parse path, body, headers, authenticated principal
        -> PlaceOrderCommand
            -> PlaceOrderUseCase
                -> domain rules and ports
        -> HTTP response / error response
~~~

Handler không nên chứa logic tính giá, kiểm tra tồn kho hoặc quyết định giảm giá. Những quy tắc đó thuộc domain/application để có thể test độc lập.

Adapter test nên kiểm tra:

- Thiếu header idempotency key được map thành lỗi 400.
- JSON body không hợp lệ được map thành lỗi 400.
- Principal không tồn tại hoặc thiếu claim bắt buộc bị từ chối.
- Use case thành công được map thành HTTP 201/response schema đúng.
- OutOfStockException được map thành mã lỗi nghiệp vụ phù hợp, ví dụ 409.
- Lỗi hạ tầng không bị trả ra stack trace hoặc secret cho client.
- Event message có schema version không hỗ trợ được xử lý theo chính sách đã định.

Dùng DTO/fixture tương tự platform event để test mapping. Không cần dựng Lambda runtime chỉ để xác minh handler đọc đúng một field trong event. Tuy nhiên, test mapping phải dùng cấu trúc event đúng với loại trigger thực tế; adapter cho API Gateway REST API và HTTP API có schema khác nhau.

### Phân biệt lỗi nghiệp vụ và lỗi hạ tầng

| Loại lỗi | Ví dụ | Cách adapter thường phản hồi |
|---|---|---|
| Input invalid | Thiếu customerId, quantity âm | HTTP 400 hoặc reject message theo hợp đồng |
| Business conflict | Hết hàng, trạng thái đơn không cho phép | HTTP 409 hoặc event result nghiệp vụ |
| Not found | Order không tồn tại hoặc không hiển thị cho caller | HTTP 404 theo chính sách |
| Unauthorized/forbidden | Thiếu danh tính hoặc không có quyền | HTTP 401/403 |
| Transient infrastructure | Database timeout, service unavailable | HTTP 5xx hoặc retry theo trigger |
| Permanent infrastructure/config | IAM AccessDenied, schema không tương thích | Cảnh báo, fail có kiểm soát; không retry vô hạn |

Không biến mọi exception thành HTTP 200 hoặc acknowledgement thành công. Với queue, acknowledgement thành công có thể khiến message không được giao lại. Cần phân loại lỗi retryable và non-retryable theo semantics của trigger.

## 9. Idempotency: test logic và giới hạn của in-memory fake

Một unit test có thể chứng minh use case nhận cùng idempotency key lần thứ hai và trả lại order đã lưu. Nhưng serverless thường có nhiều invocation chạy song song, có thể trên nhiều instance hoặc JVM.

In-memory repository chỉ tuần tự hóa trong một test object. Nó không mô phỏng:

- Unique constraint của database.
- Transaction isolation.
- Hai invocation cùng claim một key.
- Lock timeout hoặc deadlock.
- Retry sau khi side effect đã commit nhưng response bị mất.
- Message redelivery từ queue hoặc event source mapping.

Vì vậy, cần test theo tầng:

1. **Unit test:** key đã tồn tại thì use case không lặp lại nghiệp vụ theo luồng tuần tự.
2. **Repository integration test:** unique constraint/conditional insert chỉ cho một transaction claim key.
3. **Concurrency test:** gửi đồng thời nhiều request cùng key và xác minh chỉ một kết quả nghiệp vụ.
4. **Failure/recovery test:** giả lập crash sau side effect hoặc sau commit nhưng trước acknowledgement, rồi kiểm tra retry.

Nếu nghiệp vụ gọi payment provider, dùng idempotency key ổn định ở provider và lưu trạng thái thao tác. Không chỉ test số lần gọi mock; cần kiểm tra adapter thật gửi cùng key theo hợp đồng của provider.

## 10. Kiểm thử transaction, outbox và side effect

Một use case có thể cập nhật database rồi publish event. Nếu database commit thành công nhưng publish thất bại, hệ thống có thể mất event. Nếu publish thành công nhưng database rollback, consumer có thể nhận event cho dữ liệu không tồn tại.

Unit test có thể kiểm tra orchestration gọi port phù hợp và phản ứng với lỗi. Nhưng tính nguyên tử của transaction cần integration test với database và outbox adapter.

Mẫu transactional outbox:

- Trong cùng database transaction, lưu business record và outbox event.
- Worker riêng đọc outbox và publish message.
- Sau khi publish thành công, đánh dấu event đã gửi.
- Consumer xử lý idempotent vì publish có thể lặp.

Test nên bao phủ:
- Business record và outbox entry được lưu cùng transaction.
- Transaction rollback thì cả hai cùng không tồn tại.
- Publisher thất bại thì outbox entry còn để retry.
- Publish thành công nhưng worker crash trước khi đánh dấu sent thì event có thể gửi lại.
- Consumer nhận duplicate event nhưng không lặp side effect.

Đây là những test vượt ra ngoài unit test thuần và cần database/broker hoặc test adapter tương ứng.

## 11. Test theo trigger nhưng giữ business logic chung

Một use case có thể được gọi từ nhiều adapter:

| Trigger | Adapter chịu trách nhiệm | Phần nghiệp vụ dùng chung |
|---|---|---|
| HTTP | Parse path/body/header, auth context, response | PlaceOrderUseCase |
| SQS/Pub/Sub | Parse message, schema version, ack/retry | ProcessOrderEventUseCase |
| Scheduler | Parse schedule input, kiểm tra thời điểm | ExpireReservationsUseCase |
| Workflow task | Map task input/output, task token | ApproveOrderUseCase |

Không nhân đôi business rule trong từng handler. Hãy test một lần ở use case, rồi test adapter riêng để chứng minh mỗi trigger map dữ liệu đúng.

Ví dụ HTTP và queue có thể cùng gọi `PlaceOrderUseCase`, nhưng chính sách lỗi khác nhau: HTTP trả 409 cho conflict; consumer có thể retry hoặc đưa message vào DLQ. Sự khác nhau này thuộc adapter và trigger policy, không nên làm thay đổi phép tính giá hoặc quy tắc domain.

## 12. Cấu hình test và dependency trong Maven

Với Maven, có thể dùng JUnit Jupiter và Mockito. Ví dụ dependency test:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-junit-jupiter</artifactId>
        <version>5.14.2</version>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>
    </plugins>
</build>
~~~

Đây là phiên bản ví dụ; dự án nên dùng version đã được quản lý tập trung trong dependency management/BOM và tương thích với JDK đang dùng. Với Spring Boot, ưu tiên dependency management của Spring Boot thay vì khai báo version JUnit/Mockito độc lập nếu starter test đã cung cấp.

Chạy unit test:

~~~bash
mvn test
~~~

Chạy một test class:

~~~bash
mvn -Dtest=OrderPricingPolicyTest test
~~~

Không cần khởi chạy function emulator trong bước unit test. CI có thể chạy unit test trước, sau đó mới chạy integration test có database/container hoặc môi trường cloud test.

## 13. Tổ chức test suite trong pipeline

Một pipeline thực tế có thể chia theo tốc độ và mức phụ thuộc:

~~~mermaid
flowchart TD
    A["Compile"] --> B["Domain unit tests"]
    B --> C["Use case unit tests"]
    C --> D["Adapter / mapping tests"]
    D --> E["Repository and contract tests"]
    E --> F["Cloud integration tests"]
    F --> G["Deploy / smoke tests"]
~~~

- **Domain unit tests:** chạy thường xuyên nhất, không cần framework hoặc network.
- **Use case tests:** dùng fake/mock ports, kiểm tra luồng nghiệp vụ và lỗi.
- **Adapter tests:** xác minh mapping, schema và response.
- **Repository/contract tests:** kiểm tra SQL, serialization, message contract hoặc API client.
- **Cloud integration tests:** xác minh IAM, trigger, VPC, retry, DLQ và permission thật trong account/project test.
- **Smoke test:** xác minh revision/function đã deploy nhận được request hoặc event theo cấu hình.

Khi một unit test thất bại, cần biết test nào và business rule nào bị vi phạm. Khi cloud integration test thất bại, cần biết resource/permission/region nào liên quan. Phân tầng rõ giúp giảm thời gian điều tra.

## 14. Những anti-pattern cần tránh

| Anti-pattern | Vì sao có vấn đề | Cách thay thế |
|---|---|---|
| Test phải có AWS/GCP credentials | Khó chạy local và phụ thuộc account | Test domain/use case qua port |
| Khởi động toàn bộ Spring context cho mọi rule | Chậm và test quá rộng | Unit test class thuần Java |
| Business logic nằm trong Lambda handler | Khó tái sử dụng và test | Chuyển vào use case/domain |
| Mock mọi object kể cả value object | Test phụ thuộc implementation | Dùng object thật và fake đơn giản |
| Assert thứ tự mọi lời gọi nội bộ | Refactor dễ làm test gãy | Assert kết quả và side effect quan trọng |
| Dùng sleep để test timeout | Flaky và chậm | Inject Clock/scheduler |
| Dùng static mutable state giữa test | Test ảnh hưởng lẫn nhau | Dependency riêng và reset rõ ràng |
| Test idempotency chỉ bằng Map | Không chứng minh atomicity phân tán | Database constraint + concurrency test |
| Test chỉ happy path | Bỏ sót boundary và failure | Thêm invalid, conflict, timeout, duplicate |
| Chạy integration test cho mọi thay đổi nhỏ | Pipeline chậm và tốn tài nguyên | Phân tầng test theo rủi ro |

Không chạy test phụ thuộc thứ tự hoặc chia sẻ state mutable giữa test. JUnit có thể chạy test theo thứ tự không được bảo đảm; mỗi test nên tự dựng dữ liệu và dependency cần thiết.

## 15. Checklist unit test cho Java serverless

- [ ] Domain model và business policy không import AWS/GCP SDK.
- [ ] Use case chỉ phụ thuộc interface/port và dependency được inject.
- [ ] Handler chỉ parse event/request, gọi use case và map kết quả.
- [ ] Test chạy được bằng JVM thông thường, không cần cloud credential hoặc network.
- [ ] Có test cho happy path, boundary, invalid input và business conflict.
- [ ] Fake được dùng cho repository/port đơn giản; mock chỉ ở ranh giới cần kiểm tra tương tác.
- [ ] Clock, ID generator và randomness được inject khi ảnh hưởng kết quả.
- [ ] Test không dùng sleep hoặc thời gian thực không kiểm soát.
- [ ] Idempotency được test tuần tự ở use case và đồng thời ở integration layer.
- [ ] Transaction, unique constraint và outbox được test với adapter/database thật.
- [ ] HTTP/event adapter có test cho mapping và error response/acknowledgement.
- [ ] Test fixture không chứa secret hoặc dữ liệu production.
- [ ] CI phân biệt unit, adapter, contract, integration và smoke test.
- [ ] Assertion kiểm tra hành vi nghiệp vụ, không khóa chặt chi tiết triển khai.
- [ ] Test có tên mô tả hành vi và thất bại chỉ ra điều kiện bị vi phạm.

## Tự kiểm tra

1. Vì sao unit test nghiệp vụ không nên cần Lambda runtime hoặc Cloud Run container?
2. Domain, application/use case và adapter có trách nhiệm khác nhau như thế nào?
3. Port/interface giúp kiểm thử use case ra sao?
4. Khi nào nên dùng fake thay cho Mockito mock?
5. Vì sao cần inject Clock và ID generator vào business logic?
6. Unit test idempotency bằng in-memory repository chứng minh được điều gì và không chứng minh được điều gì?
7. Vì sao IAM permission và event source mapping cần cloud integration test?
8. HTTP adapter và SQS adapter có thể dùng chung use case nhưng xử lý lỗi khác nhau ra sao?
9. Transactional outbox cần những test nào ngoài unit test?
10. Vì sao một bộ test có coverage cao vẫn có thể bỏ sót lỗi nghiệp vụ?

Unit test nghiệp vụ Java đạt hiệu quả khi code không phụ thuộc runtime cụ thể. Domain giữ quy tắc thuần Java; use case điều phối qua port; adapter chịu trách nhiệm chuyển đổi HTTP/event và gọi dịch vụ cloud. Với JUnit 5, fake dependencies và các nguồn thời gian/ID được inject, phần lớn quy tắc có thể được kiểm tra nhanh, lặp lại và xác định. Những bảo đảm về IAM, network, transaction và concurrency phân tán tiếp tục được xác minh ở tầng integration phù hợp.

