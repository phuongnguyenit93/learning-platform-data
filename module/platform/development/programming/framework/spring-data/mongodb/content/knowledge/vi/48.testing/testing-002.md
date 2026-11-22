# Kiểm thử quy tắc nghiệp vụ không cần MongoDB

## 1. Vì sao cần tách kiểm thử nghiệp vụ khỏi cơ sở dữ liệu?

Ứng dụng **Spring Data MongoDB** thường có hai nhóm trách nhiệm khác nhau:

- **Quy tắc nghiệp vụ:** khi nào đơn hàng được hủy, cách tính giảm giá, khi nào một yêu cầu bị từ chối, trạng thái nào được chuyển tiếp, dữ liệu đầu vào phải thỏa điều kiện gì.
- **Truy cập dữ liệu:** dùng **MongoTemplate** hoặc **MongoRepository** để tìm, lưu, cập nhật document; ánh xạ Java sang BSON; thực hiện query, aggregation, transaction hoặc các thao tác reactive.

Nhóm thứ nhất có thể được kiểm tra bằng **unit test chạy hoàn toàn trong JVM**, không cần MongoDB, Docker, kết nối mạng hoặc Spring ApplicationContext. Những bài test này chạy nhanh, ổn định và báo rõ quy tắc nào đã bị phá vỡ. Nhóm thứ hai cần những kiểm thử riêng vì mock không thể chứng minh rằng truy vấn, index, mapping và transaction thực sự chạy đúng trên MongoDB.

Ví dụ, yêu cầu nghiệp vụ:

> Đơn hàng chỉ được hủy khi đang ở trạng thái PENDING; đơn hàng đã gửi đi phải bị từ chối. Nếu hủy hợp lệ thì lưu trạng thái CANCELLED.

Chúng ta có thể kiểm tra điều kiện chuyển trạng thái và việc service yêu cầu lưu đơn hàng bằng Java thuần + Mockito. Để biết một thao tác repository thực sự cập nhật đúng document trong MongoDB, vẫn cần integration test.

### Mục tiêu bài học

Sau bài học, bạn có thể:

1. Nhận biết phần nào của ứng dụng Spring Data MongoDB nên kiểm thử **không cần database**.
2. Viết unit test cho hàm nghiệp vụ thuần với JUnit 5, gồm các giá trị biên và trường hợp không hợp lệ.
3. Tách service khỏi hạ tầng bằng interface (port), dùng Mockito hoặc fake để giả lập truy cập dữ liệu.
4. Kiểm thử luồng nghiệp vụ đồng bộ và reactive mà không khởi động MongoDB.
5. Xác định rõ khi nào phải bổ sung kiểm thử tích hợp cho MongoTemplate/repository.

## 2. Xác định ranh giới kiểm thử

Một cách tổ chức đơn giản:

~~~mermaid
flowchart TB
    UI["REST API / Message handler"]
    S["Application service<br/>Điều phối nghiệp vụ"]
    P["Domain policy / Entity<br/>Quy tắc nghiệp vụ thuần Java"]
    Port["OrderGateway<br/>Interface truy cập dữ liệu"]
    Adapter["MongoOrderGateway<br/>MongoTemplate / MongoRepository"]
    DB[("MongoDB")]

    UI --> S
    S --> P
    S --> Port
    Adapter -.->|"implements"| Port
    Adapter --> DB

    UT["Unit test: JUnit + Mockito/Fake"] -.-> S
    UT -.-> P
    IT["Integration test"] -.-> Adapter
    IT -.-> DB
~~~

**Hướng phụ thuộc** là điểm quan trọng: quy tắc nghiệp vụ không cần biết MongoDB dùng collection nào, shard key gì hoặc driver hoạt động ra sao. Service có thể phụ thuộc vào một interface nói bằng ngôn ngữ nghiệp vụ như **OrderGateway**, còn adapter MongoDB triển khai interface đó.

| Điều cần xác minh | Test không cần MongoDB? | Công cụ phù hợp |
| --- | --- | --- |
| Tổng tiền, điều kiện giảm giá, phí vận chuyển | Có | JUnit 5, Java thuần |
| Chuyển trạng thái đơn hàng, validation, phát hiện lỗi nghiệp vụ | Có | JUnit 5 |
| Service gọi lưu đúng dữ liệu khi điều kiện thỏa | Có | Mockito hoặc fake repository |
| Service không ghi khi nghiệp vụ từ chối | Có | JUnit + Mockito |
| Bộ lọc MongoDB tạo ra kết quả đúng với BSON thật | Không đủ nếu chỉ dùng mock | Integration test với MongoDB |
| Ánh xạ @Document, @Id, converters, indexes | Không đủ nếu chỉ dùng mock | @DataMongoTest / integration test |
| Transaction, aggregation, TTL index, unique index, sharding | Không | Integration test trong môi trường tương ứng |
| Reactor pipeline ra đúng giá trị hoặc lỗi theo quy tắc nghiệp vụ | Có | StepVerifier + stub/mock reactive gateway |
| Backpressure, tương tác driver, transaction reactive với MongoDB thực | Không đủ nếu chỉ dùng mock | Integration test reactive |

**Unit test độc lập database không có nghĩa được phép bỏ integration test.** Hai loại test chứng minh hai thứ khác nhau.

## 3. Ví dụ 1: kiểm thử tính giá đơn hàng bằng Java thuần

Giả sử hệ thống bán hàng có quy tắc:

- Giỏ hàng phải có ít nhất một dòng; **số lượng của từng dòng lớn hơn 0** và **đơn giá không âm**.
- Nếu tổng tiền hàng trước giảm giá **từ 1.000.000 VND**, giảm **5%**; số tiền giảm làm tròn tới đồng bằng **HALF_UP**.
- Phí giao hàng **30.000 VND** nếu tiền hàng **sau giảm giá** nhỏ hơn **500.000 VND**; từ ngưỡng đó được miễn phí.
- Tổng thanh toán = tiền hàng trước giảm giá − giảm giá + phí giao hàng.

Quy tắc này không cần bất kỳ repository nào. Hãy hiện thực bằng một đối tượng không phụ thuộc Spring hay MongoDB.

### 3.1. Mã nghiệp vụ

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;

record CartLine(BigDecimal unitPrice, int quantity) {
    CartLine {
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Price must not be negative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}

record PriceBreakdown(
    BigDecimal subtotal,
    BigDecimal discount,
    BigDecimal shippingFee,
    BigDecimal total
) {}

final class PricingPolicy {
    private static final BigDecimal DISCOUNT_THRESHOLD =
        new BigDecimal("1000000");
    private static final BigDecimal DISCOUNT_RATE =
        new BigDecimal("0.05");
    private static final BigDecimal FREE_SHIPPING_THRESHOLD =
        new BigDecimal("500000");
    private static final BigDecimal SHIPPING_FEE =
        new BigDecimal("30000");

    PriceBreakdown quote(List<CartLine> lines) {
        Objects.requireNonNull(lines, "lines");
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Cart must not be empty");
        }

        BigDecimal subtotal = lines.stream()
            .map(line -> line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal discount = subtotal.compareTo(DISCOUNT_THRESHOLD) >= 0
            ? subtotal.multiply(DISCOUNT_RATE)
                .setScale(0, RoundingMode.HALF_UP)
            : BigDecimal.ZERO;

        BigDecimal afterDiscount = subtotal.subtract(discount);
        BigDecimal shippingFee =
            afterDiscount.compareTo(FREE_SHIPPING_THRESHOLD) >= 0
                ? BigDecimal.ZERO
                : SHIPPING_FEE;

        return new PriceBreakdown(
            subtotal,
            discount,
            shippingFee,
            afterDiscount.add(shippingFee)
        );
    }
}
~~~

**Vì sao dùng BigDecimal?** Tiền tệ không nên tính bằng **double** vì phép biểu diễn số thực nhị phân có thể tạo sai số. Ví dụ đặt ngưỡng và quy tắc làm tròn rõ ràng giúp test kiểm tra đúng kết quả nghiệp vụ. Trong ví dụ này, giá được hiểu là số đồng VND; ứng dụng thực có thể kiểm tra thêm scale, loại tiền, thuế và các quy tắc làm tròn khác.

### 3.2. Unit test với JUnit 5

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class PricingPolicyTest {
    private final PricingPolicy policy = new PricingPolicy();

    private PriceBreakdown quote(String unitPrice) {
        return policy.quote(
            List.of(new CartLine(new BigDecimal(unitPrice), 1))
        );
    }

    @Test
    void belowDiscountThresholdDoesNotApplyDiscount() {
        PriceBreakdown result = quote("999999");

        assertEquals(new BigDecimal("999999"), result.subtotal());
        assertEquals(BigDecimal.ZERO, result.discount());
        assertEquals(BigDecimal.ZERO, result.shippingFee());
        assertEquals(new BigDecimal("999999"), result.total());
    }

    @Test
    void atDiscountThresholdAppliesFivePercent() {
        PriceBreakdown result = quote("1000000");

        assertEquals(new BigDecimal("50000"), result.discount());
        assertEquals(new BigDecimal("950000"), result.total());
    }

    @ParameterizedTest
    @CsvSource({
        "499999, 30000, 529999",
        "500000, 0, 500000"
    })
    void shippingFeeChangesAtThreshold(
        String subtotal, String expectedFee, String expectedTotal
    ) {
        PriceBreakdown result = quote(subtotal);

        assertEquals(new BigDecimal(expectedFee), result.shippingFee());
        assertEquals(new BigDecimal(expectedTotal), result.total());
    }

    @Test
    void discountUsesHalfUpRounding() {
        PriceBreakdown result = quote("1000011");

        // 1.000.011 * 5% = 50.000,55 => làm tròn thành 50.001 VND
        assertEquals(new BigDecimal("50001"), result.discount());
        assertEquals(new BigDecimal("950010"), result.total());
    }

    @Test
    void emptyCartIsRejected() {
        assertThrows(
            IllegalArgumentException.class,
            () -> policy.quote(List.of())
        );
    }

    @Test
    void invalidCartLineIsRejected() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new CartLine(new BigDecimal("-1"), 1)
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> new CartLine(new BigDecimal("1000"), 0)
        );
    }
}
~~~

Các test trên chỉ khởi tạo **PricingPolicy** rồi gọi phương thức; không có annotation **@SpringBootTest**, **@DataMongoTest** hoặc kết nối MongoDB.

Một bài test nghiệp vụ tốt nên chứng minh **kết quả quan sát được**. Không nên viết test chỉ lặp lại câu lệnh bên trong hàm hoặc xác nhận các phương thức private đã được gọi. Những test đó dễ vẫn xanh khi điều kiện biên bị sai.

### 3.3. Tìm các điểm biên dễ bỏ sót

Với chính sách trên, nên đánh giá các trường hợp:

| Nhóm kiểm tra | Ví dụ | Vì sao cần test? |
| --- | --- | --- |
| Dưới, bằng, trên ngưỡng giảm giá | 999.999 / 1.000.000 / 1.000.001 | Bắt lỗi dùng **>** thay **>=**. |
| Dưới, bằng, trên ngưỡng miễn phí giao hàng | 499.999 / 500.000 / 500.001 | Xác minh ranh giới và đơn vị tiền. |
| Làm tròn tiền giảm | 1.000.011 × 5% | Bắt lỗi làm tròn hoặc chuyển sang double. |
| Nhiều dòng hàng | 2 sản phẩm × 3 cái | Bắt lỗi cộng nhầm số lượng/đơn giá. |
| Dữ liệu sai | Giỏ rỗng, giá âm, số lượng 0 | Xác minh quy tắc từ chối. |
| Thứ tự áp dụng quy tắc | Phí giao hàng tính sau giảm giá | Tránh thay đổi không chủ đích khi sửa thuật toán. |

Trường hợp giá gần ngưỡng miễn phí **sau khi trừ giảm giá** rất dễ bị bỏ quên khi nghiệp vụ phát triển thêm các chương trình khuyến mãi. Khi có điều kiện mới, cần bổ sung case theo hành vi mới, không chỉ bổ sung test cho dòng code mới.

## 4. Ví dụ 2: kiểm thử service có thao tác lưu dữ liệu

Không phải quy tắc nào cũng là hàm tính toán. Một service thường cần đọc dữ liệu hiện có, quyết định nghiệp vụ rồi lưu kết quả. Vẫn có thể unit test không cần MongoDB bằng cách cho service phụ thuộc vào **port**.

Giả sử quy tắc: đơn hàng chỉ được hủy khi trạng thái **PENDING**; nếu đơn hàng không tồn tại thì trả lỗi; khi hủy thành công phải lưu trạng thái **CANCELLED**.

### 4.1. Domain và cổng truy cập dữ liệu

~~~java
import java.util.NoSuchElementException;
import java.util.Optional;

enum OrderStatus {
    PENDING, PAID, SHIPPED, CANCELLED
}

record Order(String id, OrderStatus status) {
    Order cancel() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                "Only PENDING orders can be cancelled"
            );
        }
        return new Order(id, OrderStatus.CANCELLED);
    }
}

interface OrderGateway {
    Optional<Order> findById(String id);
    void save(Order order);
}

final class CancelOrderService {
    private final OrderGateway gateway;

    CancelOrderService(OrderGateway gateway) {
        this.gateway = gateway;
    }

    Order cancel(String id) {
        Order current = gateway.findById(id)
            .orElseThrow(
                () -> new NoSuchElementException("Order not found: " + id)
            );

        Order cancelled = current.cancel();
        gateway.save(cancelled);
        return cancelled;
    }
}
~~~

Lớp **Order** chứa quy tắc chuyển trạng thái. **CancelOrderService** điều phối việc đọc/lưu nhưng không import bất kỳ lớp nào của MongoDB. Interface **OrderGateway** được thiết kế theo nghiệp vụ; implementation dùng MongoDB sẽ được cung cấp khi chạy ứng dụng thật.

### 4.2. Test service bằng Mockito

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import java.util.NoSuchElementException;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CancelOrderServiceTest {
    private OrderGateway gateway;
    private CancelOrderService service;

    @BeforeEach
    void setUp() {
        gateway = mock(OrderGateway.class);
        service = new CancelOrderService(gateway);
    }

    @Test
    void pendingOrderCanBeCancelledAndSaved() {
        when(gateway.findById("o-100"))
            .thenReturn(Optional.of(
                new Order("o-100", OrderStatus.PENDING)
            ));

        Order actual = service.cancel("o-100");

        Order expected = new Order("o-100", OrderStatus.CANCELLED);
        assertEquals(expected, actual);
        verify(gateway).save(expected);
    }

    @Test
    void shippedOrderIsRejectedWithoutSaving() {
        when(gateway.findById("o-200"))
            .thenReturn(Optional.of(
                new Order("o-200", OrderStatus.SHIPPED)
            ));

        assertThrows(
            IllegalStateException.class,
            () -> service.cancel("o-200")
        );
        verify(gateway, never()).save(any(Order.class));
    }

    @Test
    void missingOrderIsRejectedWithoutSaving() {
        when(gateway.findById("missing"))
            .thenReturn(Optional.empty());

        assertThrows(
            NoSuchElementException.class,
            () -> service.cancel("missing")
        );
        verify(gateway, never()).save(any(Order.class));
    }
}
~~~

Không hề tạo một MongoDB server trong các test này:

1. **Arrange:** Mockito tạo phản hồi giả cho **findById**.
2. **Act:** service chạy quy tắc hủy đơn thực tế.
3. **Assert:** kiểm tra giá trị trả về hoặc exception, đồng thời kiểm tra side effect **save**.

Kiểm tra **save không được gọi** trong trường hợp từ chối đặc biệt quan trọng: có những lỗi cho ra thông báo đúng nhưng vẫn ghi dữ liệu sai trước khi ném exception.

**Cần phân biệt hai việc:** Mockito chứng minh service **gửi đúng lệnh** tới gateway; nó chưa chứng minh một bản ghi thật đã được MongoDB cập nhật. Trách nhiệm đó thuộc kiểm thử adapter.

### 4.3. Adapter dùng Spring Data MongoDB

Ví dụ sau minh họa cách nối port với repository; đây là **code chạy trong ứng dụng**, không cần được gọi trong unit test phía trên.

~~~java
import java.util.Optional;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.stereotype.Repository;

@Document(collection = "orders")
record OrderDocument(@Id String id, String status) {}

interface SpringOrderRepository
        extends MongoRepository<OrderDocument, String> {}

@Repository
class MongoOrderGateway implements OrderGateway {
    private final SpringOrderRepository repository;

    MongoOrderGateway(SpringOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public Optional<Order> findById(String id) {
        return repository.findById(id)
            .map(doc -> new Order(
                doc.id(), OrderStatus.valueOf(doc.status())
            ));
    }

    @Override
    public void save(Order order) {
        repository.save(new OrderDocument(
            order.id(), order.status().name()
        ));
    }
}
~~~

Code tách thành các file Java và package thích hợp khi đưa vào dự án. Adapter chịu trách nhiệm ánh xạ document sang domain và ngược lại. Khi thay **MongoRepository** bằng **MongoTemplate**, service nghiệp vụ vẫn chỉ làm việc qua **OrderGateway**.

Đoạn minh họa đơn giản hóa yêu cầu đồng thời. Trong production, quy tắc “chỉ hủy PENDING” có thể cần **điều kiện cập nhật nguyên tử** hoặc **optimistic locking** để tránh trường hợp đơn hàng chuyển sang SHIPPED sau lúc đọc nhưng trước lúc lưu. Unit test không thể chứng minh an toàn trước race condition ở MongoDB; phải thiết kế và kiểm thử điều đó ở adapter/database.

## 5. Dùng fake repository thay vì mock khi nào?

Một **fake** là implementation đơn giản chạy trong bộ nhớ. Fake hữu ích nếu nhiều test cần các thao tác CRUD cơ bản hoặc cần quan sát state sau một chuỗi hành động.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

final class InMemoryOrderGateway implements OrderGateway {
    private final Map<String, Order> orders = new HashMap<>();

    void seed(Order order) {
        orders.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }

    @Override
    public void save(Order order) {
        orders.put(order.id(), order);
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CancelOrderWithFakeTest {

    @Test
    void cancellationChangesStoredOrder() {
        InMemoryOrderGateway gateway = new InMemoryOrderGateway();
        gateway.seed(new Order("o-300", OrderStatus.PENDING));
        CancelOrderService service = new CancelOrderService(gateway);

        service.cancel("o-300");

        assertEquals(
            OrderStatus.CANCELLED,
            gateway.findById("o-300").orElseThrow().status()
        );
    }
}
~~~

| Công cụ | Ưu điểm | Giới hạn |
| --- | --- | --- |
| **Mockito mock** | Chỉ rõ tương tác, tham số, và trường hợp không được ghi. | Dễ làm test phụ thuộc quá mức vào chi tiết cách service gọi hàm. |
| **Fake trong bộ nhớ** | Thuận tiện để kiểm tra state sau nhiều bước, ít cấu hình stub. | Có nguy cơ mô phỏng sai hành vi MongoDB thật. |
| **MongoDB thực qua integration test** | Kiểm chứng mapping, query và đặc tính persistence thật. | Khởi tạo chậm hơn, cần môi trường và dữ liệu test được quản lý. |

Fake **không tự thực hiện** unique index, transaction, collations, aggregation, query semantics hoặc atomic update giống MongoDB. Không dùng kết quả test fake để tuyên bố các cơ chế đó hoạt động đúng.

## 6. Không khởi động Spring khi chưa cần

Với test nghiệp vụ thuần, thường chỉ cần:

~~~java
PricingPolicy policy = new PricingPolicy();
OrderGateway gateway = mock(OrderGateway.class);
CancelOrderService service = new CancelOrderService(gateway);
~~~

Các lệnh này không dựng **Spring ApplicationContext** và không mở kết nối MongoDB. Hạn chế dùng **@SpringBootTest** cho những phép tính đơn giản chỉ vì service được đánh dấu **@Service** trong ứng dụng. Tương tự, **@DataMongoTest** là lựa chọn kiểm thử tầng MongoDB, không phải điều kiện bắt buộc cho unit test.

Một cấu hình dependency thường gặp trong dự án Spring Boot dùng Gradle là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

**spring-boot-starter-test** thường cung cấp JUnit Jupiter, AssertJ và Mockito theo hệ phiên bản do Spring Boot quản lý. Tùy phiên bản Gradle/Spring Boot và cấu hình dự án, hãy bảo đảm chạy test trên nền JUnit Platform (ví dụ **useJUnitPlatform()** nếu chưa được cấu hình):

~~~groovy
tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đặt các file test vào **src/test/java** với package tương ứng, rồi chạy bộ test cụ thể:

~~~bash
./gradlew test --tests "*PricingPolicyTest"
./gradlew test --tests "*CancelOrderServiceTest"
~~~

Trong dự án dùng Maven hoặc Windows, lệnh tương đương thay đổi theo công cụ và wrapper đang có. Những lệnh trên là ví dụ cho cách tổ chức kiểm thử, không phải báo cáo rằng repository hiện tại đã được chạy test.

### Khi không dễ tách Spring

Một class nghiệp vụ có thể đang đọc **@Value**, gọi **MongoTemplate** trong constructor hoặc phụ thuộc trực tiếp vào **MongoRepository**. Có thể chuyển dần theo hướng:

1. Đưa cấu hình thay đổi theo môi trường thành tham số/đối tượng cấu hình, truyền qua constructor.
2. Tách tính toán và validation thành một class Java không có phụ thuộc framework.
3. Đặt các lời gọi persistence vào gateway hoặc repository được inject.
4. Với các quy tắc cần thời gian hiện tại, inject **Clock**; với random ID, cung cấp nguồn sinh ID có thể kiểm soát trong test.

**Không nhất thiết phải viết lại toàn bộ kiến trúc** mới có unit test: có thể mock trực tiếp interface **MongoRepository** trong service hiện có, miễn là không nhầm kết quả đó với kiểm thử MongoDB.

## 7. Kiểm thử nghiệp vụ reactive mà không cần MongoDB

Spring Data MongoDB hỗ trợ truy cập reactive thông qua **ReactiveMongoRepository** hoặc **ReactiveMongoTemplate**. Trong test nghiệp vụ, có thể định nghĩa một gateway trả **Mono/Flux**, rồi dùng **StepVerifier** để xác minh kết quả, lỗi và quá trình hoàn thành của stream.

Ví dụ quy tắc hủy đơn giống phần trên:

~~~java
import java.util.NoSuchElementException;
import reactor.core.publisher.Mono;

interface ReactiveOrderGateway {
    Mono<Order> findById(String id);
    Mono<Order> save(Order order);
}

final class ReactiveCancelOrderService {
    private final ReactiveOrderGateway gateway;

    ReactiveCancelOrderService(ReactiveOrderGateway gateway) {
        this.gateway = gateway;
    }

    Mono<Order> cancel(String id) {
        return gateway.findById(id)
            .switchIfEmpty(Mono.error(
                new NoSuchElementException("Order not found: " + id)
            ))
            .map(Order::cancel)
            .flatMap(gateway::save);
    }
}
~~~

~~~java
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveCancelOrderServiceTest {

    @Test
    void pendingOrderIsSavedAndEmitted() {
        ReactiveOrderGateway gateway = mock(ReactiveOrderGateway.class);
        Order existing = new Order("o-400", OrderStatus.PENDING);
        Order cancelled = new Order("o-400", OrderStatus.CANCELLED);

        when(gateway.findById("o-400")).thenReturn(Mono.just(existing));
        when(gateway.save(cancelled)).thenReturn(Mono.just(cancelled));

        Mono<Order> result = new ReactiveCancelOrderService(gateway)
            .cancel("o-400");

        StepVerifier.create(result)
            .expectNext(cancelled)
            .verifyComplete();

        verify(gateway).save(cancelled);
    }

    @Test
    void invalidTransitionEmitsErrorWithoutSaving() {
        ReactiveOrderGateway gateway = mock(ReactiveOrderGateway.class);
        when(gateway.findById("o-401"))
            .thenReturn(Mono.just(
                new Order("o-401", OrderStatus.SHIPPED)
            ));

        StepVerifier.create(
                new ReactiveCancelOrderService(gateway).cancel("o-401")
            )
            .expectError(IllegalStateException.class)
            .verify();

        verify(gateway, never()).save(any(Order.class));
    }
}
~~~

Các test trên cần **reactor-test** để sử dụng StepVerifier. Nếu dự án chưa có dependency này, cấu hình phiên bản tương thích với Reactor đang dùng, thường thông qua dependency management của Spring Boot:

~~~groovy
testImplementation 'io.projectreactor:reactor-test'
~~~

**Đặc điểm đáng chú ý của reactive:** pipeline có thể được lắp ráp trước nhưng logic chỉ thực sự chạy khi được subscribe; **StepVerifier** giúp kích hoạt và quan sát cả kết quả lẫn error signal. Không cần chờ bằng **Thread.sleep()**. Với luồng có delay/timeouts trong code nghiệp vụ, có thể dùng **StepVerifier.withVirtualTime** nếu code được thiết kế phù hợp.

## 8. Chiến lược xây dựng bộ unit test có giá trị

### 8.1. Kiểm tra hành vi từ yêu cầu

Hãy diễn đạt test bằng ngôn ngữ nghiệp vụ: **pendingOrderCanBeCancelledAndSaved**, **shippedOrderIsRejectedWithoutSaving**, **atDiscountThresholdAppliesFivePercent**. Một test tốt trả lời được:

- Điều kiện đầu vào là gì?
- Quy tắc yêu cầu kết quả hoặc lỗi gì?
- Khi xảy ra lỗi, có side effect nào cần chắc chắn không xuất hiện?

Không nên dùng mock để thay thế chính **PricingPolicy** hoặc **Order.cancel()** khi mục đích là kiểm thử logic của chúng; làm vậy loại bỏ phần code cần xác minh.

### 8.2. Kiểm tra trạng thái và tương tác vừa đủ

Ưu tiên assert đầu ra và trạng thái có ý nghĩa. Với hành vi có side effect cần thiết, thêm **verify** hoặc kiểm tra fake state. Tránh kiểm tra thứ tự của mọi lời gọi nội bộ nếu thứ tự ấy không phải yêu cầu nghiệp vụ, vì refactor vô hại có thể khiến test thất bại.

### 8.3. Có negative test và boundary test

Các nhánh thất bại thường quan trọng hơn “happy path”: đơn hàng không tồn tại, trạng thái không hợp lệ, giá âm, số lượng bằng 0, ngưỡng giảm giá, trường hợp làm tròn. Một bài test chỉ xác nhận điều kiện bình thường thường không bắt được lỗi khi yêu cầu thay đổi.

### 8.4. Kiểm soát dữ liệu không quyết định

Nếu service dùng **Instant.now()**, **UUID.randomUUID()**, API bên ngoài hoặc bộ phát sự kiện, hãy truyền **Clock**, hàm cấp ID hay interface thích hợp để tạo test lặp lại được. Tránh kiểm tra thời gian bằng cách đợi thật hoặc so sánh đồng hồ hệ thống với độ chính xác quá chặt.

### 8.5. Tách unit test và integration test trong CI

Unit test nghiệp vụ nên chạy rất thường xuyên, chẳng hạn mỗi lần thay code hoặc mỗi pull request. Integration test với MongoDB nên chạy ở pipeline thích hợp để kiểm tra sự tương tác với database thực. Phân loại test theo mục đích giúp phát hiện nhanh lỗi nghiệp vụ mà vẫn có độ tin cậy về phần lưu trữ.

## 9. Khi nào bắt buộc phải dùng MongoDB để kiểm chứng?

Một số hành vi **không thể xác minh đầy đủ** bằng mock hoặc fake:

| Hành vi | Vì sao unit test chưa đủ? |
| --- | --- |
| Derived query như **findByTenantIdAndStatus** | Mockito không chạy query parser hay truy vấn BSON trên MongoDB. |
| **MongoTemplate Query/Criteria**, collation, regex | Cần biết filter thực sự được server đánh giá như thế nào. |
| **Aggregation pipeline** | Các giai đoạn group, lookup, unwind và xử lý kiểu BSON có ngữ nghĩa ở MongoDB. |
| **@Document**, **@Id**, custom converter | Mapping Java ↔ BSON có thể khác giả định trong domain test. |
| **Unique index**, TTL index, compound index | Enforcement và hành vi index đến từ MongoDB server. |
| **Transaction** và cơ chế rollback | Phụ thuộc session, topology và triển khai MongoDB thực. |
| **Optimistic locking** qua **@Version** | Cần kiểm tra xung đột ghi khi dùng persistence thật. |
| **Reactive MongoDB** | Driver, timeout, backpressure và kết nối thật cần môi trường tích hợp. |

Trong dự án Spring Boot, **@DataMongoTest** phù hợp để khởi tạo phần cấu hình liên quan MongoDB và kiểm thử repository, converter hoặc MongoTemplate với một môi trường MongoDB phù hợp. **Testcontainers** là một lựa chọn phổ biến để cung cấp MongoDB dùng trong integration test; khi kiểm thử transaction cần bảo đảm topology MongoDB hỗ trợ transaction (chẳng hạn replica set).

Đừng giả định có thể chỉ bật **@DataMongoTest** mà tự động có MongoDB chạy sẵn. Cấu hình test cần chỉ rõ database test thực tế, vòng đời container hoặc hạ tầng test và cách làm sạch dữ liệu.

### Bài toán race condition

Ví dụ **cancel()** ở trên gồm bước đọc trạng thái rồi lưu. Hai luồng đồng thời có thể cùng đọc **PENDING**; một luồng chuyển đơn sang **SHIPPED**, luồng còn lại lại lưu **CANCELLED**. Unit test dùng mock thường bỏ qua rủi ro này.

Một cách giải quyết tại tầng MongoDB là **conditional atomic update**: chỉ cập nhật nếu **_id** trùng và trạng thái hiện tại vẫn là **PENDING**; kiểm tra số document bị thay đổi để quyết định thành công hay xung đột. Có thể dùng MongoTemplate với **Query** và **Update** cho thao tác như vậy. Unit test có thể kiểm tra cách service xử lý kết quả “không cập nhật được”, còn integration test phải xác minh tính nguyên tử trên MongoDB thật.

## 10. Các lỗi thiết kế test phổ biến

| Cách làm dễ sai | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Mỗi unit test gọi **@SpringBootTest** | Startup chậm, phụ thuộc cấu hình và hạ tầng. | Khởi tạo class cần test bằng constructor khi kiểm tra nghiệp vụ. |
| Mock cả logic nghiệp vụ cần kiểm tra | Test luôn xanh dù quy tắc sai. | Giữ domain/policy là đối tượng thật, mock tại ranh giới I/O. |
| Kiểm tra một giá trị bình thường | Không phát hiện lỗi điều kiện biên. | Thêm dưới/bằng/trên ngưỡng, invalid input, nhánh lỗi. |
| Dùng **Thread.sleep()** chờ reactive | Test chậm và thiếu ổn định. | Dùng StepVerifier, virtual time khi thích hợp. |
| Fake repository mô phỏng toàn bộ MongoDB | Fake phức tạp, ngữ nghĩa khác server thật. | Chỉ giả lập hành vi mà service cần; phần DB kiểm tra tích hợp. |
| Chỉ assert exception mà bỏ qua side effect | Có thể vẫn ghi dữ liệu sai trước khi ném lỗi. | Kiểm tra **never().save(...)** hoặc trạng thái fake. |
| So sánh **BigDecimal** tùy tiện | **equals()** phân biệt scale, chẳng hạn 1.0 và 1.00. | Quy định scale rõ ràng hoặc dùng **compareTo()** khi chỉ quan tâm giá trị số. |
| Giấu phụ thuộc bên trong static/global singleton | Khó tạo test độc lập và dễ ảnh hưởng giữa các test. | Inject dependency qua constructor; tránh shared mutable state. |
| Xem mock test là chứng cứ query/index chạy đúng | Lỗi persistence lọt qua CI. | Bổ sung integration test theo rủi ro thực tế. |

## 11. Quy trình áp dụng vào dự án

1. **Liệt kê quy tắc nghiệp vụ** từ use case: đầu vào, điều kiện chấp nhận/từ chối, kết quả, side effect.
2. **Khoanh vùng code thuần:** tách chính sách tính toán, trạng thái và validation ra khỏi lời gọi MongoTemplate/repository.
3. **Định nghĩa ranh giới I/O:** chọn interface nhỏ phù hợp khi cần đọc/lưu dữ liệu, gửi sự kiện hoặc gọi dịch vụ ngoài.
4. **Viết unit test trước cho giá trị biên:** ưu tiên yêu cầu khó, dễ sai và nhánh lỗi; dùng JUnit 5.
5. **Giả lập dependency tối thiểu:** Mockito khi cần verify tương tác; fake khi cần theo dõi trạng thái qua nhiều bước.
6. **Chạy test trong JVM:** không cần MongoDB, Docker hoặc khởi động cả Spring context cho các phần nghiệp vụ này.
7. **Viết integration test cho adapter MongoDB:** mapping, filter, save/update, index, transaction và tình huống cạnh tranh dữ liệu.
8. **Đo hiệu quả bộ test:** lỗi nghiệp vụ phải được chỉ ra bởi unit test dễ hiểu; lỗi hạ tầng/truy vấn phải được chỉ ra bởi integration test.

### Câu hỏi tự kiểm tra

**1. Service có dùng MongoRepository thì có bắt buộc phải chạy MongoDB mới test được không?** Không. Có thể inject mock repository hoặc tách một gateway để kiểm tra nghiệp vụ và tương tác service. Cần integration test riêng để biết repository thực sự làm việc đúng với MongoDB.

**2. @DataMongoTest có phải là cách nhanh nhất để test phép tính giảm giá không?** Không. Một **PricingPolicyTest** dùng Java/JUnit trực tiếp là đủ và tập trung hơn.

**3. Mock repository trả đơn hàng PENDING có chứng minh MongoDB đang lưu đúng đơn hàng đó không?** Không. Mock chỉ là dữ liệu đầu vào do test tự thiết lập.

**4. Làm sao kiểm tra service không ghi dữ liệu khi nghiệp vụ từ chối?** Với Mockito, dùng **verify(gateway, never()).save(...)**. Với fake, kiểm tra trạng thái vẫn giữ nguyên.

**5. Dùng StepVerifier kiểm tra Mono có yêu cầu MongoDB không?** Không, nếu dữ liệu được cung cấp bởi stub/mock reactive gateway. StepVerifier subscribe pipeline và xác minh tín hiệu.

**6. Race condition giữa đọc trạng thái và ghi cập nhật có được chứng minh bởi unit test thông thường không?** Không. Cần thiết kế thao tác ghi phù hợp, như conditional update hoặc optimistic locking, rồi kiểm thử trên MongoDB thực.

## Kết luận

Với **Spring Data MongoDB**, phần lớn **quy tắc nghiệp vụ** có thể được kiểm thử trong JVM bằng **JUnit 5**, kết hợp **Mockito** hoặc một fake đơn giản khi service phụ thuộc vào lưu trữ. Tách domain/policy khỏi MongoTemplate và repository giúp kiểm thử nhanh, rõ và ít phụ thuộc môi trường; các service vẫn có thể tích hợp với MongoDB qua adapter. Khi cần xác minh **BSON mapping, truy vấn, aggregation, index, transaction, reactive driver hoặc tính nguyên tử của cập nhật**, phải bổ sung kiểm thử tích hợp với MongoDB. Bộ kiểm thử tốt giữ rõ ranh giới: **unit test chứng minh quyết định nghiệp vụ; integration test chứng minh thao tác dữ liệu thật**.
