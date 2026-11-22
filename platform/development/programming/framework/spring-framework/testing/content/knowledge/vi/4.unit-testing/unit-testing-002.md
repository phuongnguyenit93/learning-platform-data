# Tiêm thành phần cộng tác mà không khởi động ApplicationContext

Trong kiểm thử đơn vị một service Spring, ta thường cần thay các thành phần mà service gọi đến bằng những đối tượng kiểm soát được: repository, gateway HTTP, publisher, clock hoặc một service khác. Việc đó không bắt buộc phải khởi động Spring `ApplicationContext`.

Một unit test có thể tạo trực tiếp đối tượng cần kiểm thử bằng `new`, rồi truyền các thành phần cộng tác qua constructor. Nếu cần mô phỏng hành vi hoặc kiểm tra lời gọi, ta dùng stub, fake hoặc mock. JUnit Jupiter chạy test; Mockito có thể tạo mock và quản lý vòng đời mock. Spring container không tham gia vào lần chạy này.

Đây là cách kiểm thử phù hợp khi mục tiêu là xác nhận logic của một lớp trong điều kiện đầu vào và phản hồi của các collaborator đã được kiểm soát. Nó giúp test nhanh, tập trung và ít phụ thuộc vào cấu hình ứng dụng.

## 1. Hiểu đúng việc tiêm dependency trong unit test

Trong ứng dụng đang chạy, Spring container thường tạo bean, tìm các dependency và truyền chúng vào constructor hoặc field được cấu hình. Trong unit test không có container, test tự chịu trách nhiệm tạo object graph nhỏ nhất cần thiết.

```text
Ứng dụng khi chạy

Spring ApplicationContext
        │ tạo và liên kết bean
        ▼
OrderService ───────► OrderRepository
      │
      └─────────────► NotificationGateway


Unit test không có ApplicationContext

JUnit test
   │ tạo trực tiếp
   ▼
OrderService ───────► mock OrderRepository
      │
      └─────────────► mock NotificationGateway
```

Hai cách tạo object graph phục vụ hai mục tiêu khác nhau:

- Spring container kiểm tra và thực hiện việc tạo bean theo cấu hình ứng dụng.
- Unit test tạo trực tiếp một lớp và cung cấp những collaborator cần thiết để kiểm tra hành vi của lớp đó.

Constructor injection làm cho ranh giới này rõ ràng. Một lớp khai báo dependency bắt buộc trong constructor; khi chạy ứng dụng, Spring truyền bean thật hoặc bean thay thế theo cấu hình; khi chạy unit test, test truyền fake hoặc mock.

## 2. Thiết kế lớp cần kiểm thử bằng constructor injection

Giả sử `OrderService` xử lý việc tạo đơn hàng. Nó cần lưu đơn hàng qua repository và gửi thông báo qua một gateway.

```java
public interface OrderRepository {
    Order save(Order order);
}

public interface NotificationGateway {
    void orderCreated(Order order);
}

public record CreateOrderCommand(String customerId, String sku, int quantity) {}

public record Order(String customerId, String sku, int quantity) {
    public static Order from(CreateOrderCommand command) {
        return new Order(command.customerId(), command.sku(), command.quantity());
    }
}
```

Service nhận hai collaborator qua constructor:

```java
import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final NotificationGateway notificationGateway;

    public OrderService(
            OrderRepository orderRepository,
            NotificationGateway notificationGateway) {
        this.orderRepository = Objects.requireNonNull(orderRepository);
        this.notificationGateway = Objects.requireNonNull(notificationGateway);
    }

    public Order create(CreateOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        Order saved = orderRepository.save(Order.from(command));
        notificationGateway.orderCreated(saved);
        return saved;
    }
}
```

`@Service` đánh dấu lớp để Spring có thể phát hiện và đăng ký bean khi có component scanning. Annotation này không làm cho constructor chỉ có thể được gọi bởi Spring. Unit test vẫn có thể tạo `new OrderService(...)` bình thường; khi không khởi động `ApplicationContext`, Spring không quét classpath, không tạo bean và không thực hiện dependency injection.

Constructor injection có một số lợi ích rõ ràng đối với kiểm thử:

- Nhìn vào constructor là biết đầy đủ dependency bắt buộc của lớp.
- Test tạo object với đúng các collaborator mà trường hợp kiểm thử cần.
- Các dependency có thể khai báo `final`, giúp object giữ được cấu trúc ổn định sau khi tạo.
- Không cần khởi tạo context chỉ để gán một vài field hoặc gọi setter.
- Nếu thiếu dependency, lỗi xuất hiện ngay tại điểm tạo object thay vì muộn hơn khi gọi phương thức.

## 3. Tiêm mock thủ công bằng Mockito

Mockito có thể tạo đối tượng giả để test điều khiển phản hồi và quan sát tương tác. Với constructor injection, cách trực tiếp nhất là tạo mock rồi truyền chúng vào constructor của lớp cần kiểm thử.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private NotificationGateway notificationGateway;

    private OrderService orderService;

    @BeforeEach
    void setUp() {
        orderService = new OrderService(orderRepository, notificationGateway);
    }

    @Test
    void savesOrderAndSendsNotification() {
        CreateOrderCommand command = new CreateOrderCommand("customer-1", "SKU-1", 2);
        Order savedOrder = new Order("customer-1", "SKU-1", 2);
        when(orderRepository.save(any(Order.class))).thenReturn(savedOrder);

        Order result = orderService.create(command);

        assertThat(result).isSameAs(savedOrder);
        verify(orderRepository).save(new Order("customer-1", "SKU-1", 2));
        verify(notificationGateway).orderCreated(savedOrder);
    }
}
```

Trong test trên:

1. `@ExtendWith(MockitoExtension.class)` yêu cầu JUnit Jupiter dùng Mockito extension để khởi tạo và quản lý các annotation Mockito trong test.
2. `@Mock` tạo mock cho từng interface cộng tác.
3. `setUp()` tạo `OrderService` bằng constructor thông thường và truyền hai mock vào.
4. `when(...).thenReturn(...)` quy định phản hồi của repository.
5. `verify(...)` xác nhận service đã gọi collaborator với dữ liệu mong đợi.

`MockitoExtension` là extension của Mockito dành cho JUnit Jupiter. Nó không phải `SpringExtension`, không tạo Spring bean và không nạp `ApplicationContext`. Test có thể chạy độc lập bằng JUnit Platform.

Nếu không cần annotation, ta cũng có thể tạo mock trực tiếp:

```java
import static org.mockito.Mockito.mock;

@Test
void createsOrderWithExplicitMocks() {
    OrderRepository repository = mock(OrderRepository.class);
    NotificationGateway notifications = mock(NotificationGateway.class);
    OrderService service = new OrderService(repository, notifications);

    // Thiết lập hành vi mock, gọi service và kiểm tra kết quả.
}
```

Cách này làm rõ mọi bước khởi tạo ngay trong test. Nó hữu ích khi mỗi test cần cấu hình object graph khác nhau hoặc chỉ cần một vài mock.

## 4. Dùng `@InjectMocks` khi muốn Mockito tạo đối tượng cần kiểm thử

Mockito có annotation `@InjectMocks` để yêu cầu Mockito tạo instance của lớp cần kiểm thử và thử đưa các mock hoặc spy phù hợp vào instance đó.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceWithInjectMocksTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private NotificationGateway notificationGateway;

    @InjectMocks
    private OrderService orderService;

    @Test
    void savesAndNotifies() {
        CreateOrderCommand command = new CreateOrderCommand("customer-1", "SKU-1", 2);
        Order savedOrder = new Order("customer-1", "SKU-1", 2);
        when(orderRepository.save(any(Order.class))).thenReturn(savedOrder);

        assertThat(orderService.create(command)).isEqualTo(savedOrder);
        verify(notificationGateway).orderCreated(savedOrder);
    }
}
```

Mockito ưu tiên thử constructor injection, sau đó có thể thử setter/property injection và field injection theo các quy tắc của nó. Đây là cơ chế tiện lợi của Mockito, không phải thuật toán dependency injection của Spring. Mockito không đọc `@Autowired`, không xử lý component scanning, không chạy auto-configuration và không tạo proxy Spring cho object được đánh dấu `@InjectMocks`.

Một vài điểm cần nhớ khi dùng `@InjectMocks`:

- Các collaborator phù hợp phải có mock hoặc spy tương ứng trong test.
- Nếu Mockito không tìm được mock cho một tham số constructor, nó có thể truyền `null` trong quá trình thử constructor injection. Vì vậy, test vẫn có thể lỗi khi gọi phương thức nếu dependency bị thiếu.
- Khi có nhiều constructor hoặc dependency cùng kiểu, việc chọn và ghép dependency có thể kém rõ ràng hơn cách tạo thủ công.
- `@InjectMocks` không tự tạo mock cho mọi dependency lồng sâu trong object graph.
- Annotation không thay thế việc thiết kế constructor rõ ràng và không bảo đảm rằng cấu hình bean của ứng dụng hoạt động đúng.

Vì vậy, hãy dùng `@InjectMocks` khi object graph đơn giản và việc tự động ghép dependency làm test dễ đọc hơn. Nếu cần thấy rõ chính xác object nào được truyền vào đâu, `new OrderService(mockA, mockB)` thường minh bạch hơn.

## 5. Chọn test double phù hợp: stub, mock, fake và dummy

Không phải collaborator nào cũng cần Mockito mock. Một test double là đối tượng thay thế collaborator thật trong một test. Các loại thường gặp có mục đích khác nhau:

| Loại | Mục đích | Ví dụ |
|---|---|---|
| Dummy | Được truyền vào để đáp ứng chữ ký phương thức nhưng không được sử dụng. | Một object placeholder cho tham số bắt buộc của test. |
| Stub | Trả về dữ liệu đã định trước để kiểm soát đường chạy. | Repository stub luôn trả về một order cụ thể. |
| Fake | Cài đặt đơn giản nhưng có hành vi thực sự, thường lưu trạng thái trong bộ nhớ. | Repository dùng `Map` thay database. |
| Mock | Ghi nhận tương tác để test xác minh lời gọi hoặc đối số. | Xác nhận gateway nhận đúng thông báo. |
| Spy | Bọc một object thật và cho phép theo dõi hoặc thay thế một phần hành vi. | Theo dõi lời gọi của một collaborator thật. |

### 5.1. Stub: kiểm soát kết quả trả về

Nếu mục tiêu là kiểm tra logic của service khi repository trả về một kết quả cụ thể, stub là đủ. Với Mockito, stub thường được thiết lập bằng `when(...).thenReturn(...)`:

```java
when(orderRepository.save(any(Order.class))).thenReturn(savedOrder);
```

Service nhận phản hồi đã định trước và test kiểm tra kết quả đầu ra. Không cần xác minh mọi lời gọi phụ nếu hành vi đó không phải điều test cần chứng minh.

### 5.2. Fake: dùng một triển khai nhỏ trong bộ nhớ

Một fake hữu ích khi collaborator có trạng thái và test cần kiểm tra kết quả qua nhiều lần gọi. Ví dụ một repository giả đơn giản:

```java
import java.util.ArrayList;
import java.util.List;

class InMemoryOrderRepository implements OrderRepository {

    private final List<Order> orders = new ArrayList<>();

    @Override
    public Order save(Order order) {
        orders.add(order);
        return order;
    }

    List<Order> findAll() {
        return List.copyOf(orders);
    }
}
```

Test có thể truyền fake vào service:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

@Test
void storesCreatedOrderInMemory() {
    InMemoryOrderRepository repository = new InMemoryOrderRepository();
    NotificationGateway notifications = mock(NotificationGateway.class);
    OrderService service = new OrderService(repository, notifications);

    service.create(new CreateOrderCommand("customer-1", "SKU-1", 2));

    assertThat(repository.findAll())
            .containsExactly(new Order("customer-1", "SKU-1", 2));
}
```

Fake có thể làm test gần với hành vi của một repository hơn mock thuần, nhưng không chứng minh câu lệnh SQL, mapping JPA, transaction hoặc cấu hình database thật hoạt động. Những nội dung đó cần một bài kiểm thử persistence phù hợp.

### 5.3. Mock: xác minh tương tác có ý nghĩa

Mock phù hợp khi hợp đồng của lớp cần kiểm thử bao gồm việc gọi một collaborator. Ví dụ service phải gửi thông báo sau khi lưu thành công. Test có thể dùng `verify(notificationGateway).orderCreated(savedOrder)` để xác nhận tương tác.

Không nên xác minh mọi lời gọi nội bộ một cách máy móc. Nếu test kiểm tra số lần gọi, thứ tự gọi hoặc chi tiết đối số không liên quan đến hành vi bên ngoài, test dễ bị gắn chặt vào cách triển khai và phải sửa khi refactor dù hành vi vẫn đúng.

### 5.4. Spy: dùng thận trọng

Spy bọc một object thật, nên lời gọi chưa được stub thường chạy logic thật của object đó. Spy hữu ích trong một số trường hợp đặc biệt, nhưng có thể khiến test vô tình chạm vào file, mạng hoặc trạng thái thật. Với collaborator có side effect, mock hoặc fake thường dễ kiểm soát hơn.

## 6. Kiểm tra nhiều nhánh logic mà không cần Spring

Khi đã kiểm soát được collaborator, test có thể tập trung vào nhánh thành công, nhánh lỗi và quy tắc tương tác.

Ví dụ service từ chối số lượng không hợp lệ trước khi gọi repository:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void rejectsNonPositiveQuantityBeforeCallingCollaborators() {
    CreateOrderCommand command = new CreateOrderCommand("customer-1", "SKU-1", 0);

    assertThatThrownBy(() -> orderService.create(command))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage("Quantity must be positive");

    verifyNoInteractions(orderRepository, notificationGateway);
}
```

Ví dụ này kiểm tra hợp đồng của service: đầu vào không hợp lệ bị từ chối và không tạo side effect. Không cần database, HTTP server hoặc application context.

Với trường hợp repository thất bại, có thể thiết lập exception để xác nhận service truyền lỗi phù hợp và không gửi thông báo:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@Test
void doesNotNotifyWhenSavingFails() {
    CreateOrderCommand command = new CreateOrderCommand("customer-1", "SKU-1", 2);
    when(orderRepository.save(any(Order.class)))
            .thenThrow(new IllegalStateException("Storage unavailable"));

    assertThatThrownBy(() -> orderService.create(command))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("Storage unavailable");

    verifyNoInteractions(notificationGateway);
}
```

Các ví dụ dùng Mockito để cô lập collaborator. Khi test một quy tắc thuần Java, có thể không cần Mockito; chỉ dùng object thật hoặc fake nhỏ là đủ.

## 7. Dependency injection không đồng nghĩa với khởi động Spring

Một nhầm lẫn phổ biến là thấy lớp có `@Service`, `@Repository` hoặc `@Component` thì cho rằng muốn test lớp đó phải có Spring container. Thực tế, các annotation này là metadata mà Spring sử dụng khi xây dựng ứng dụng. Bản thân class Java vẫn là một class bình thường có thể được tạo trực tiếp.

| Thành phần | Unit test không có context | Kiểm thử tích hợp Spring |
|---|---|---|
| Tạo service | `new OrderService(...)` | Spring tạo bean theo cấu hình. |
| Cung cấp collaborator | Truyền mock, stub hoặc fake vào constructor. | Spring resolve bean từ context. |
| `@Service` / `@Component` | Không cần annotation có hiệu lực để tạo object trực tiếp. | Được component scanning hoặc cấu hình bean sử dụng. |
| `@Autowired` | Không được xử lý nếu không có Spring container. | Spring thực hiện injection theo context. |
| `@Mock` | Mockito tạo mock độc lập. | Có thể dùng cùng test framework nếu test có tích hợp Mockito. |
| `@MockBean` / `@MockitoBean` | Không cần và không thay thế mock thủ công. | Thay thế hoặc đăng ký mock bean trong Spring test context theo API/phiên bản tương ứng. |

Nếu một lớp chỉ có field `@Autowired` và không có constructor để truyền dependency, gọi `new` sẽ không làm Spring tự gán field. Field đó vẫn là `null` nếu test không tự gán. Đây là lý do constructor injection thường giúp lớp dễ unit test hơn.

Không nên khởi động `@SpringBootTest` chỉ để Mockito tạo mock. `@SpringBootTest` có nhiệm vụ dựng môi trường ứng dụng Boot; `MockitoExtension` có nhiệm vụ khởi tạo mock cho unit test. Hai công cụ phục vụ hai phạm vi kiểm thử khác nhau.

## 8. Các dependency cần thiết cho test độc lập

Một unit test dùng JUnit Jupiter và Mockito cần test engine/API của JUnit cùng Mockito core và integration module dành cho JUnit Jupiter. Với Gradle, ví dụ khai báo trực tiếp:

```groovy
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.mockito:mockito-junit-jupiter")
    testImplementation("org.assertj:assertj-core")
}

tasks.test {
    useJUnitPlatform()
}
```

Trong ứng dụng Spring Boot, `spring-boot-starter-test` thường cung cấp các thư viện test thông dụng, trong đó có JUnit Jupiter, Mockito và AssertJ theo dependency management của Boot. Tuy nhiên, Spring Boot starter không phải điều kiện bắt buộc để tạo unit test độc lập. Một dự án Spring Framework không dùng Boot vẫn có thể khai báo trực tiếp JUnit và Mockito.

Nếu test không dùng bất kỳ API Spring Test nào, nó cũng không cần `spring-test` chỉ vì lớp đang kiểm thử được đánh dấu `@Service`. Chỉ thêm dependency khi test thực sự dùng API thuộc module đó.

## 9. Khi nào unit test không có context là đủ?

Hãy chọn unit test không có `ApplicationContext` khi câu hỏi cần trả lời tập trung vào logic của một lớp:

- Với cùng một input, service có tính ra kết quả đúng không?
- Khi collaborator trả về một kết quả hoặc ném exception, service xử lý ra sao?
- Service có gọi collaborator cần thiết với đúng dữ liệu không?
- Các điều kiện đầu vào có chặn side effect không?
- Một nhánh lỗi có ngăn các bước tiếp theo được thực hiện không?

Các test này thường chạy nhanh vì không cần tạo context, khởi tạo connection pool, quét component hay cấu hình web environment. Chúng cũng giúp xác định lỗi ở logic của lớp mà không bị ảnh hưởng bởi cấu hình của các bean khác.

Tuy nhiên, unit test độc lập không chứng minh Spring đã lắp ráp ứng dụng đúng. Nó không xác nhận component scanning, điều kiện auto-configuration, qualifier, profile, property binding, proxy transaction, security filter chain hoặc endpoint được đăng ký. Khi cần xác nhận các hợp đồng đó, hãy bổ sung bài kiểm thử tích hợp Spring có phạm vi phù hợp.

Một chiến lược cân bằng thường gồm:

1. Unit test không context để kiểm tra nhiều trường hợp logic của service và các nhánh lỗi.
2. Một số test Spring context để xác nhận cấu hình bean và các tích hợp quan trọng.
3. Test chuyên biệt cho persistence, MVC, security hoặc HTTP khi hành vi cần kiểm tra thuộc các tầng đó.

Không cần biến mọi unit test thành test tích hợp. Ngược lại, cũng không thể dùng unit test với mock để kết luận rằng toàn bộ wiring và cấu hình Spring đang đúng.

## 10. Những trường hợp cần chú ý

### Dependency được cung cấp qua `@Value`

Nếu service đọc cấu hình bằng field `@Value`, tạo trực tiếp bằng `new` sẽ không tự gán giá trị. Nên cân nhắc chuyển giá trị cấu hình thành tham số constructor hoặc một object cấu hình được truyền vào constructor. Khi đó unit test có thể cung cấp giá trị cụ thể mà không cần property resolution của Spring.

```java
public class RetryPolicy {
    private final int maxAttempts;

    public RetryPolicy(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public boolean canRetry(int attempt) {
        return attempt < maxAttempts;
    }
}
```

Test chỉ cần `new RetryPolicy(3)` để kiểm tra các ngưỡng. Một bài context test riêng có thể xác nhận giá trị property được bind vào bean đúng như cấu hình ứng dụng.

### Dependency là proxy hoặc phụ thuộc vào AOP

Khi chạy trong Spring, bean có thể được bọc bởi proxy để thực hiện transaction, caching, security hoặc advice khác. `new` tạo object Java trực tiếp và không tự tạo proxy. Unit test trực tiếp kiểm tra logic phương thức; nó không kiểm chứng hành vi do proxy bổ sung. Nếu cần xác nhận `@Transactional` hoặc advice được áp dụng thật, hãy kiểm tra bằng Spring context test và transaction manager phù hợp.

### Lớp phụ thuộc vào request scope hoặc context của web

Một số bean cần request, session hoặc security context. Nếu logic nghiệp vụ có thể tách khỏi trạng thái web, hãy truyền dữ liệu cần thiết vào phương thức hoặc collaborator rõ ràng để unit test dễ kiểm soát. Nếu mục tiêu là kiểm tra cách Spring gắn scope và request context, cần bài test web/context tương ứng.

### Không thể tạo object vì constructor quá phức tạp

Nếu một lớp cần rất nhiều collaborator hoặc constructor có nhiều nhánh cấu hình, hãy xem lại trách nhiệm và object graph của lớp. Không nên dùng reflection để ghi tùy tiện vào các field private chỉ nhằm vượt qua constructor trong test. Có thể tạo factory/builder rõ ràng cho dữ liệu test, tách trách nhiệm hoặc cung cấp dependency qua constructor có ý nghĩa.

## 11. Thói quen giúp unit test bền vững

- Tạo object cần kiểm thử bằng constructor rõ ràng; giữ các dependency bắt buộc là `final` khi phù hợp.
- Mock những collaborator có side effect hoặc cần kiểm soát phản hồi; dùng fake khi một triển khai nhỏ trong bộ nhớ giúp test tự nhiên hơn.
- Stub các phản hồi cần thiết cho nhánh đang kiểm tra; tránh thiết lập quá nhiều hành vi không liên quan.
- Xác minh tương tác khi lời gọi là một phần của hợp đồng, chẳng hạn gửi thông báo sau khi lưu thành công.
- Tránh xác minh chi tiết nội bộ không tạo ra giá trị cho người đọc test.
- Không dùng `@InjectMocks` như bằng chứng rằng Spring wiring đúng; nó chỉ là tiện ích khởi tạo object của Mockito.
- Không khởi động Spring context nếu test chỉ cần logic Java và các collaborator có thể được cung cấp trực tiếp.
- Bổ sung context test khi cần chứng minh cấu hình Spring, proxy, property binding hoặc tích hợp framework.

Tiêm collaborator mà không khởi động `ApplicationContext` là cách kiểm thử đơn vị trực tiếp và hiệu quả: test tạo lớp cần kiểm thử, truyền vào những dependency có hành vi được kiểm soát, rồi kiểm tra kết quả và tương tác. Spring vẫn có thể quản lý cùng lớp đó khi ứng dụng chạy; unit test chỉ chọn kiểm tra phần trách nhiệm của lớp mà không cần dựng toàn bộ container.
