# Tạo đối tượng nghiệp vụ trực tiếp bằng constructor

Trong kiểm thử đơn vị, ta thường chỉ cần một đối tượng nghiệp vụ thật để gọi phương thức và quan sát kết quả. Hãy tạo đối tượng đó trực tiếp bằng constructor Java với từ khóa `new`. Cách này giúp test tập trung vào hành vi của class, không cần khởi động Spring container, quét component hay nạp toàn bộ cấu hình ứng dụng.

Ví dụ, khi kiểm tra `OrderService`, ta có thể viết `new OrderService(repository)` và truyền vào một repository giả lập. Khi kiểm tra `Money` hoặc `Order`, ta tạo chính các đối tượng nghiệp vụ đó bằng constructor với dữ liệu cụ thể. Spring vẫn có vai trò lắp ghép các bean khi ứng dụng chạy, nhưng việc lắp ghép đó thuộc một loại kiểm thử khác.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao unit test thường tạo đối tượng đang kiểm tra bằng `new`.
- Phân biệt constructor của Java với cơ chế tạo bean của Spring.
- Tạo đối tượng nghiệp vụ với dữ liệu kiểm soát được và kiểm tra các bất biến trong constructor.
- Truyền dependency qua constructor khi kiểm tra service hoặc class cần collaborator.
- Kết hợp đối tượng thật với mock, stub hoặc fake ở đúng ranh giới.
- Tổ chức dữ liệu kiểm thử bằng helper hoặc fixture mà vẫn giữ mỗi test độc lập.
- Nhận biết khi nào cần một Spring context test thay vì unit test thuần Java.

## 1. Constructor là điểm tạo trạng thái ban đầu của đối tượng

Trong Java, toán tử `new` cấp phát một đối tượng và gọi constructor tương ứng. Constructor nhận các giá trị cần thiết để thiết lập trạng thái ban đầu. Khi constructor hoàn tất, đối tượng có thể được sử dụng theo hợp đồng mà class công bố.

Ví dụ một value object biểu diễn số lượng:

~~~java
public final class Quantity {

    private final int value;

    public Quantity(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
        this.value = value;
    }

    public int value() {
        return value;
    }
}
~~~

Unit test tạo trực tiếp đối tượng:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class QuantityTest {

    @Test
    void keepsTheProvidedPositiveValue() {
        Quantity quantity = new Quantity(3);

        assertEquals(3, quantity.value());
    }

    @Test
    void rejectsZeroAtConstructionTime() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new Quantity(0)
        );
    }
}
~~~

Test không cần annotation Spring. Nó gọi đúng constructor công khai của class và xác nhận hai phần của hợp đồng: giá trị hợp lệ được giữ lại, còn giá trị không hợp lệ bị từ chối ngay khi tạo đối tượng.

Đây là lợi ích quan trọng của việc tạo trực tiếp: test nhìn thấy rõ đối tượng nào được tạo, constructor nào được gọi và dữ liệu ban đầu là gì.

## 2. Đối tượng nghiệp vụ không cần Spring để tồn tại

Một class mô hình hóa nghiệp vụ có thể là Java object thông thường. Ví dụ:

~~~java
public final class Money {

    private final long amountInCents;
    private final String currency;

    public Money(long amountInCents, String currency) {
        if (amountInCents < 0) {
            throw new IllegalArgumentException(
                "Amount cannot be negative"
            );
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException(
                "Currency is required"
            );
        }

        this.amountInCents = amountInCents;
        this.currency = currency;
    }

    public long amountInCents() {
        return amountInCents;
    }

    public String currency() {
        return currency;
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Currencies must match"
            );
        }

        return new Money(
            amountInCents + other.amountInCents,
            currency
        );
    }
}
~~~

Test có thể tạo hai giá trị tiền trực tiếp và kiểm tra phép cộng:

~~~java
class MoneyTest {

    @Test
    void addsAmountsWithTheSameCurrency() {
        Money first = new Money(1250, "VND");
        Money second = new Money(750, "VND");

        Money total = first.add(second);

        assertEquals(2000, total.amountInCents());
        assertEquals("VND", total.currency());
    }

    @Test
    void rejectsDifferentCurrencies() {
        Money first = new Money(1250, "VND");
        Money second = new Money(500, "USD");

        assertThrows(
            IllegalArgumentException.class,
            () -> first.add(second)
        );
    }
}
~~~

`Money` không cần biết Spring là gì. Nó không cần `@Component`, `@Service` hoặc `@Autowired` để kiểm tra quy tắc cộng tiền. Constructor và phương thức công khai đã đủ để tạo trạng thái rồi thực hiện hành vi.

Các đối tượng thường được tạo trực tiếp trong unit test gồm:

- Entity và aggregate của domain.
- Value object như tiền, địa chỉ, mã định danh và khoảng thời gian.
- DTO hoặc command thuần Java.
- Validator, mapper và calculator không phụ thuộc container.
- Service hoặc policy nhận các collaborator qua constructor.

Đừng thêm phụ thuộc Spring vào một class chỉ để test có thể tạo nó. Nếu một đối tượng chỉ cần dữ liệu đầu vào và quy tắc Java, hãy giữ việc tạo đối tượng đơn giản.

## 3. Tạo đối tượng đang kiểm tra và truyền dữ liệu tường minh

Một unit test nên cho người đọc thấy trạng thái đầu vào của đối tượng. Hãy truyền dữ liệu qua constructor thay vì tạo một đối tượng rỗng rồi sửa nhiều field sau đó.

Ví dụ một đơn hàng:

~~~java
public final class Order {

    private final String orderNumber;
    private final String customerId;
    private final Quantity quantity;

    public Order(
            String orderNumber,
            String customerId,
            Quantity quantity) {

        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException(
                "Order number is required"
            );
        }
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                "Customer id is required"
            );
        }

        this.orderNumber = orderNumber;
        this.customerId = customerId;
        this.quantity = Objects.requireNonNull(
            quantity,
            "quantity"
        );
    }

    public String orderNumber() {
        return orderNumber;
    }

    public String customerId() {
        return customerId;
    }

    public Quantity quantity() {
        return quantity;
    }
}
~~~

Một test có thể chuẩn bị toàn bộ trạng thái ngay tại vị trí tạo:

~~~java
class OrderTest {

    @Test
    void exposesTheValuesUsedToCreateTheOrder() {
        Order order = new Order(
            "ORD-1001",
            "CUS-42",
            new Quantity(2)
        );

        assertEquals("ORD-1001", order.orderNumber());
        assertEquals("CUS-42", order.customerId());
        assertEquals(2, order.quantity().value());
    }

    @Test
    void requiresAQuantity() {
        assertThrows(
            NullPointerException.class,
            () -> new Order("ORD-1001", "CUS-42", null)
        );
    }
}
~~~

Cách viết này làm rõ dữ liệu nào thuộc về đối tượng. Nếu constructor bảo vệ bất biến, test cũng đi qua chính con đường tạo trạng thái hợp lệ mà code production sử dụng.

Trong ví dụ thực tế, class có thể dùng `record`, constructor nhiều tham số hoặc constructor nhận một command object. Dù hình thức nào, hãy ưu tiên API tạo đối tượng mà code production thực sự gọi. Không dùng reflection để gán field private hoặc bỏ qua validation chỉ để dựng một trạng thái mà ứng dụng bình thường không thể tạo ra.

## 4. Tạo service trực tiếp và truyền dependency qua constructor

Service thường cần repository, gateway hoặc một collaborator khác. Unit test vẫn có thể tạo service bằng constructor; dependency được truyền vào có thể là đối tượng thật đơn giản, fake hoặc mock tùy mục tiêu.

Ví dụ service:

~~~java
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public Order place(
            String orderNumber,
            String customerId,
            int quantityValue) {

        Quantity quantity = new Quantity(quantityValue);

        Order order = new Order(
            orderNumber,
            customerId,
            quantity
        );

        return repository.save(order);
    }
}
~~~

Interface mà service phụ thuộc:

~~~java
public interface OrderRepository {
    Order save(Order order);
}
~~~

Test tạo service trực tiếp và đưa mock vào constructor:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderRepository repository;

    @Test
    void createsAnOrderAndSendsItToTheRepository() {
        when(repository.save(any(Order.class)))
            .thenAnswer(invocation -> invocation.getArgument(0));

        OrderService service = new OrderService(repository);

        Order result = service.place(
            "ORD-1001",
            "CUS-42",
            2
        );

        assertEquals("ORD-1001", result.orderNumber());
        assertEquals("CUS-42", result.customerId());
        assertEquals(2, result.quantity().value());

        verify(repository).save(any(Order.class));
    }

    @Test
    void doesNotSaveAnOrderWithInvalidQuantity() {
        OrderService service = new OrderService(repository);

        assertThrows(
            IllegalArgumentException.class,
            () -> service.place("ORD-1001", "CUS-42", 0)
        );

        verifyNoInteractions(repository);
    }
}
~~~

Điểm cần chú ý là dòng `new OrderService(repository)`. Test tự quyết định dependency nào được truyền vào. Không cần Spring quét component, không cần tạo application context và không cần khởi động database.

`@Mock` ở đây chỉ giúp Mockito tạo một repository giả. Nó không tạo service. Chính test gọi constructor để tạo service đang được kiểm tra.

## 5. Chọn đối tượng thật, mock, stub hay fake cho dependency

Khi tạo đối tượng bằng constructor, các tham số constructor phải được cung cấp đầy đủ. Không phải dependency nào cũng nên mock. Hãy chọn cách tạo theo hành vi mà test cần xác nhận.

| Loại dependency | Cách thường dùng | Khi phù hợp |
|---|---|---|
| Value object hoặc entity đơn giản | Tạo thật bằng `new` | Hành vi và trạng thái của nó là một phần test cần dùng |
| Calculator hoặc policy thuần Java | Tạo thật bằng `new` | Logic đơn giản, ổn định và không cần hạ tầng |
| Repository hoặc gateway | Mock hoặc fake | Muốn cô lập service khỏi database hoặc hệ thống ngoài |
| Clock hoặc nguồn thời gian | Truyền `Clock.fixed(...)` | Cần kiểm tra ngày giờ có kết quả xác định |
| Bộ sinh mã hoặc UUID | Stub/fake có kết quả cố định | Cần kiểm tra kết quả mà không phụ thuộc ngẫu nhiên |
| Client mạng hoặc hệ thống bên ngoài | Mock hoặc fake | Không muốn gửi request thật trong unit test |

### Mock: kiểm tra tương tác với collaborator

Mock phù hợp khi cần xác nhận service gọi dependency với dữ liệu đúng, hoặc không gọi dependency khi đầu vào sai. Trong ví dụ trên, `verify(repository).save(...)` xác nhận hành vi lưu.

Không nên mock các đối tượng giá trị chỉ để tránh dùng constructor. Một `Money` hoặc `Quantity` thật thường đơn giản và đáng tin cậy hơn mock, vì test có thể kiểm tra đúng logic của value object.

### Stub: cung cấp câu trả lời cố định

Stub cung cấp kết quả đã định trước để test đi qua một nhánh cụ thể. Mockito có thể cấu hình stub bằng `when(...).thenReturn(...)` hoặc `thenAnswer(...)`.

### Fake: dependency thay thế có hành vi thực

Fake là một triển khai đơn giản có thể chạy trong bộ nhớ. Ví dụ, một repository fake lưu order trong `Map` giúp test service kiểm tra luồng lưu và đọc mà không cần database:

~~~java
class InMemoryOrderRepository implements OrderRepository {

    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public Order save(Order order) {
        orders.put(order.orderNumber(), order);
        return order;
    }

    public Optional<Order> findByOrderNumber(String orderNumber) {
        return Optional.ofNullable(orders.get(orderNumber));
    }
}
~~~

Test có thể tạo cả fake và service trực tiếp:

~~~java
@Test
void savesAnOrderInTheInMemoryRepository() {
    InMemoryOrderRepository repository =
        new InMemoryOrderRepository();

    OrderService service = new OrderService(repository);

    Order saved = service.place(
        "ORD-1001",
        "CUS-42",
        2
    );

    assertTrue(
        repository.findByOrderNumber("ORD-1001").isPresent()
    );
    assertEquals("ORD-1001", saved.orderNumber());
}
~~~

Fake hữu ích khi nhiều test cần hành vi cộng tác có ý nghĩa. Tuy nhiên, fake chỉ mô phỏng hợp đồng cần thiết; nó không chứng minh truy vấn SQL, transaction hoặc mapping của database thật hoạt động. Những điều đó cần test persistence riêng.

## 6. Constructor giúp test kiểm soát thời gian và dữ liệu biến đổi

Nếu một service gọi trực tiếp `LocalDate.now()`, `Instant.now()` hoặc `UUID.randomUUID()`, test có thể nhận kết quả khác nhau theo thời điểm hoặc lần chạy. Có thể giữ logic xác định bằng cách đưa nguồn thời gian hoặc nguồn định danh qua constructor.

Ví dụ service dùng `Clock`:

~~~java
public class SubscriptionService {

    private final Clock clock;

    public SubscriptionService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public LocalDate renewalDate(int trialDays) {
        if (trialDays < 0) {
            throw new IllegalArgumentException(
                "Trial days cannot be negative"
            );
        }

        return LocalDate.now(clock).plusDays(trialDays);
    }
}
~~~

Test truyền clock cố định:

~~~java
@Test
void calculatesRenewalDateFromTheInjectedClock() {
    Clock clock = Clock.fixed(
        Instant.parse("2026-01-10T00:00:00Z"),
        ZoneOffset.UTC
    );

    SubscriptionService service =
        new SubscriptionService(clock);

    assertEquals(
        LocalDate.of(2026, 1, 17),
        service.renewalDate(7)
    );
}
~~~

Constructor làm cho nguồn thời gian trở thành một dependency rõ ràng. Test có thể tạo một service mới với clock cố định cho từng trường hợp.

Cùng nguyên tắc có thể áp dụng cho:

- `Supplier<UUID>` hoặc một interface `IdGenerator`.
- Nguồn tỷ giá hoặc dữ liệu tham chiếu.
- Bộ random có seed cố định.
- Bộ đọc cấu hình hoặc chiến lược tính toán.

Không cần tạo abstraction cho mọi lời gọi Java. Chỉ đưa dependency vào constructor khi việc kiểm soát nó thực sự giúp logic dễ kiểm thử, dễ thay thế hoặc dễ cấu hình hơn.

## 7. Tổ chức constructor arguments và dữ liệu test

Khi constructor có nhiều tham số, phần chuẩn bị dữ liệu có thể làm test dài. Ta có thể dùng helper hoặc factory dành riêng cho test, nhưng helper phải giữ cho trạng thái quan trọng dễ nhìn thấy.

Ví dụ helper tạo order hợp lệ:

~~~java
class OrderTest {

    private Order anOrder() {
        return new Order(
            "ORD-1001",
            "CUS-42",
            new Quantity(2)
        );
    }

    @Test
    void exposesTheOrderNumber() {
        Order order = anOrder();

        assertEquals("ORD-1001", order.orderNumber());
    }
}
~~~

Helper phù hợp khi nhiều test dùng cùng một cấu hình mặc định và khác nhau ở hành vi đang kiểm tra. Nếu một test cần dữ liệu đặc biệt, hãy tạo trực tiếp trong test hoặc truyền tham số vào helper để sự khác biệt được thể hiện rõ.

Ví dụ helper có tham số:

~~~java
private Order anOrder(
        String orderNumber,
        String customerId,
        int quantity) {

    return new Order(
        orderNumber,
        customerId,
        new Quantity(quantity)
    );
}
~~~

Một test có thể gọi:

~~~java
Order order = anOrder("ORD-2002", "CUS-77", 5);
~~~

Với object có nhiều field, test data builder có thể giúp đọc dễ hơn:

~~~java
class OrderBuilder {

    private String orderNumber = "ORD-1001";
    private String customerId = "CUS-42";
    private int quantity = 2;

    OrderBuilder withOrderNumber(String value) {
        this.orderNumber = value;
        return this;
    }

    OrderBuilder withCustomerId(String value) {
        this.customerId = value;
        return this;
    }

    OrderBuilder withQuantity(int value) {
        this.quantity = value;
        return this;
    }

    Order build() {
        return new Order(
            orderNumber,
            customerId,
            new Quantity(quantity)
        );
    }
}
~~~

Sử dụng:

~~~java
Order order = new OrderBuilder()
    .withOrderNumber("ORD-2002")
    .withCustomerId("CUS-77")
    .withQuantity(5)
    .build();
~~~

Builder chỉ là công cụ chuẩn bị dữ liệu. Nó không nên che khuất hành vi mà test muốn kiểm tra. Nếu một test chỉ cần ba tham số, constructor trực tiếp thường rõ ràng hơn một builder dài.

Tránh dùng một đối tượng mutable dùng chung cho nhiều test. Một test thay đổi field có thể làm test khác phụ thuộc thứ tự chạy. Hãy tạo instance mới trong từng test hoặc trong `@BeforeEach`, và tránh giữ trạng thái có thể thay đổi ở field `static`.

## 8. Constructor công khai, factory method và bất biến nghiệp vụ

Không phải class nào cũng cần public constructor. Một số domain object có thể yêu cầu tạo qua factory method để diễn đạt rõ điều kiện hoặc bảo vệ quy tắc tạo trạng thái.

Ví dụ:

~~~java
public final class EmailAddress {

    private final String value;

    private EmailAddress(String value) {
        this.value = value;
    }

    public static EmailAddress of(String value) {
        if (value == null || !value.contains("@")) {
            throw new IllegalArgumentException(
                "Invalid email address"
            );
        }

        return new EmailAddress(value);
    }

    public String value() {
        return value;
    }
}
~~~

Test nên gọi API tạo đối tượng mà người dùng class được phép sử dụng:

~~~java
@Test
void createsAnEmailAddressFromAValidValue() {
    EmailAddress email = EmailAddress.of("ada@example.com");

    assertEquals("ada@example.com", email.value());
}
~~~

Ở đây test không gọi constructor private. Factory method là cổng tạo đối tượng được class công bố. Tinh thần vẫn giống tạo trực tiếp: test tạo object thật bằng API Java, không nhờ Spring container.

Khi constructor có validation, hãy kiểm tra cả đầu vào hợp lệ và không hợp lệ. Khi object có nhiều trạng thái nghiệp vụ, hãy kiểm tra từng đường tạo hợp lệ thay vì cố gán field để đạt tới trạng thái đó.

Với entity có lifecycle, constructor có thể tạo trạng thái ban đầu; các phương thức domain tiếp theo mới làm thay đổi trạng thái. Hãy tạo entity bằng constructor hoặc factory rồi gọi hành vi công khai theo đúng trình tự nghiệp vụ. Không sửa trực tiếp field private bằng reflection.

## 9. So sánh cách tạo đối tượng trong unit test và Spring test

Có ba cơ chế thường bị nhầm lẫn:

| Cách tạo | Ai tạo đối tượng? | Phạm vi phù hợp |
|---|---|---|
| `new MyService(dependency)` | Test gọi constructor Java | Unit test cho logic của class |
| `@InjectMocks` | Mockito tạo đối tượng và inject mock theo quy tắc của nó | Unit test khi muốn Mockito hỗ trợ khởi tạo |
| `@Autowired` trong Spring test | Spring container cung cấp bean | Kiểm tra cấu hình, wiring và hành vi phụ thuộc context |

### Tạo trực tiếp bằng `new`

Test chủ động tạo instance và truyền chính xác dependency:

~~~java
OrderService service = new OrderService(repository);
~~~

Cách này dễ đọc, không có bước khởi tạo ẩn và giúp compiler kiểm tra tham số constructor.

### Dùng `@InjectMocks`

Mockito có thể tạo đối tượng đang kiểm tra và thử inject các mock hoặc spy tương ứng. Cách này tiện khi class có nhiều dependency, nhưng việc khởi tạo không còn hiển thị trực tiếp tại dòng tạo object. Nếu cần thấy rõ dependency nào được truyền vào, hãy tự gọi constructor.

Hai cách có thể dùng trong unit test; chúng không yêu cầu Spring context.

### Dùng `@Autowired`

`@Autowired` yêu cầu Spring cung cấp bean từ context. Đây là lựa chọn phù hợp khi câu hỏi kiểm thử là Spring có chọn đúng bean, tạo đúng scope, áp dụng đúng profile hoặc lắp ghép dependency đúng không.

Một unit test thuần Java không cần dùng `@Autowired`. Nếu test dùng `@SpringBootTest`, nó đã chuyển sang phạm vi context hoặc integration test.

## 10. Khi nào việc tạo trực tiếp không đủ?

Tạo đối tượng bằng constructor xác nhận được logic Java của đối tượng và cách test cung cấp dependency. Nó không xác nhận Spring có cấu hình bean đúng.

Hãy dùng Spring TestContext hoặc Spring Boot test khi cần kiểm tra:

- Component scan có tìm thấy class cần thiết không.
- Spring có chọn đúng implementation cho interface không.
- `@Qualifier`, `@Primary`, profile hoặc conditional configuration có hoạt động không.
- Bean có được tạo với scope và lifecycle mong muốn không.
- Configuration properties có được bind đúng không.
- Proxy, transaction, AOP hoặc các tính năng phụ thuộc container có được áp dụng không.

Ví dụ, nếu cần xác nhận hai implementation của `PaymentGateway` được chọn theo qualifier, tạo service bằng `new` không trả lời được câu hỏi đó. Hãy khởi tạo một context test nhỏ và inject bean theo cấu hình thực tế.

Ngược lại, nếu test chỉ muốn kiểm tra `OrderService` từ chối số lượng bằng không trước khi lưu, khởi động toàn bộ ứng dụng là phạm vi quá rộng. Tạo service trực tiếp với repository mock là đủ.

## 11. Những lỗi thường gặp

- **Khởi động Spring cho mọi unit test:** việc tạo context làm test chậm và che khuất logic đang kiểm tra. Hãy tạo object thuần Java khi class không phụ thuộc container.
- **Dùng constructor rỗng rồi sửa field bằng setter:** trạng thái tạm thời có thể không hợp lệ và test không còn phản ánh cách production tạo object.
- **Mock mọi đối tượng:** value object và domain object đơn giản nên là instance thật để test dùng đúng hành vi của chúng.
- **Dùng constructor khác với production:** test có thể bỏ qua validation hoặc dependency bắt buộc. Hãy gọi API tạo object mà code ứng dụng thực sự dùng.
- **Tạo dữ liệu ngẫu nhiên hoặc phụ thuộc thời gian hệ thống:** kết quả khó lặp lại. Truyền clock, generator hoặc dữ liệu cố định khi cần.
- **Dùng fixture mutable dùng chung:** test có thể ảnh hưởng lẫn nhau. Tạo instance mới cho mỗi test.
- **Mock implementation cụ thể thay vì boundary:** mock repository hoặc gateway qua interface thường làm ranh giới rõ hơn và giảm phụ thuộc vào chi tiết nội bộ.
- **Cho rằng `new` kiểm tra được Spring wiring:** constructor trực tiếp không chạy component scan, không xử lý qualifier và không áp dụng bean lifecycle.
- **Dùng reflection để bỏ qua constructor:** test tạo ra trạng thái mà code production không thể tạo, khiến kết quả ít đáng tin.
- **Đưa quá nhiều dependency vào constructor mà không xem xét thiết kế:** điều đó có thể cho thấy class đang đảm nhận quá nhiều trách nhiệm. Hãy xem lại cấu trúc khi vấn đề xuất hiện trong thiết kế thật, thay vì thêm một constructor phụ chỉ để làm test dễ viết.

## 12. Quy trình viết unit test với constructor trực tiếp

Khi kiểm tra một class, có thể đi theo trình tự sau:

1. Xác định class đang được kiểm tra và hành vi công khai cần xác nhận.
2. Đọc constructor để biết dữ liệu bắt buộc và dependency cần truyền vào.
3. Tạo các value object hoặc domain object thật bằng constructor hoặc factory method công khai.
4. Tạo collaborator thật nếu đơn giản; dùng mock, stub hoặc fake cho boundary cần cô lập.
5. Gọi constructor của class đang kiểm tra ngay trong test hoặc trong helper dễ đọc.
6. Thực hiện một hành vi cần kiểm tra.
7. Xác nhận kết quả và tương tác có ý nghĩa với collaborator.
8. Tạo instance mới cho test khác để tránh trạng thái bị chia sẻ.
9. Nếu câu hỏi chuyển sang Spring wiring hoặc lifecycle, chuyển sang một context test riêng.

Ví dụ, với `OrderService`, mỗi test có thể tạo service mới từ repository mock, truyền cùng một bộ dữ liệu rõ ràng và xác nhận một hành vi. Các test về `Order` hoặc `Quantity` có thể tạo những object đó trực tiếp mà không cần dựng service hay Spring.

## Kết luận

Tạo đối tượng nghiệp vụ trực tiếp bằng constructor là cách tự nhiên để viết unit test cho Java object. Test chủ động chọn dữ liệu, tạo instance thật và truyền dependency cần thiết. Điều này giữ phạm vi kiểm thử nhỏ, kết quả dễ lặp lại và nguyên nhân lỗi dễ khoanh vùng.

Khi cần kiểm tra logic của class, hãy dùng constructor hoặc factory method công khai để tạo object. Khi cần kiểm tra việc Spring lắp ghép bean, profile, proxy hoặc lifecycle, hãy dùng Spring TestContext. Phân biệt đúng hai mục tiêu giúp mỗi test trả lời một câu hỏi rõ ràng.

