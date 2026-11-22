# Tiêm phụ thuộc trong lớp kiểm thử lồng

JUnit Jupiter cho phép nhóm các test có liên quan bằng annotation `@Nested`. Khi một test class được lồng bên trong class khác, lớp nested vẫn có thể khai báo dependency riêng và cần được chuẩn bị trước khi chạy test. Với Spring Framework Test, `SpringExtension` phối hợp cùng TestContext Framework để tiêm bean vào từng test instance, bao gồm cả instance của lớp kiểm thử lồng.

Hai cơ chế cùng tham gia nhưng có trách nhiệm riêng:

- JUnit Jupiter quản lý cấu trúc lớp lồng, tạo test instance và thực thi các callback vòng đời.
- Spring Test quản lý `ApplicationContext`, chuẩn bị test instance và tiêm dependency theo cấu hình Spring.

Trong trường hợp thông thường, lớp nested kế thừa cấu hình Spring từ lớp bao quanh. Nhờ vậy, các nhóm test có thể dùng cùng context và khai báo dependency ngay tại lớp cần sử dụng. Spring Framework từ phiên bản 5.3 bổ sung `@NestedTestConfiguration` để điều khiển việc kế thừa cấu hình này.

## 1. Lớp kiểm thử lồng trong JUnit Jupiter

Một lớp được đánh dấu `@Nested` là test class lồng bên trong test class khác. Lớp nested phải là lớp thành viên không có `static`, vì nó gắn với một instance của lớp bao quanh.

```java
class OrderServiceTests {

    @Nested
    class CreateOrder {

        @Test
        void createsAnOrder() {
            // Kiểm tra hành vi tạo đơn hàng.
        }
    }

    @Nested
    class CancelOrder {

        @Test
        void cancelsAnExistingOrder() {
            // Kiểm tra hành vi hủy đơn hàng.
        }
    }
}
```

Các nhóm nested test giúp tổ chức test theo hành vi hoặc bối cảnh. Tên hiển thị trong IDE và báo cáo có thể thể hiện đường dẫn từ lớp bao quanh đến lớp lồng, giúp người đọc hiểu test đang kiểm tra nhánh nào.

JUnit Jupiter vẫn coi mỗi phương thức `@Test` là một lần thực thi riêng. Với lifecycle mặc định `PER_METHOD`, JUnit tạo test instance mới cho mỗi test method. Đối với nested test, instance của lớp bao quanh cũng được tạo để làm enclosing instance cho lớp nested.

## 2. SpringExtension tiêm dependency vào test instance

Để Spring tham gia vòng đời JUnit Jupiter, đăng ký `SpringExtension`. Cách ngắn gọn là dùng annotation tổng hợp `@SpringJUnitConfig`:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceTests {

    @Autowired
    private OrderService orderService;

    @Nested
    class CreateOrder {

        @Autowired
        private OrderRepository orderRepository;

        @Test
        void createsAnOrder() {
            // Dùng orderService và orderRepository.
        }
    }
}
```

Ở ví dụ này, `@SpringJUnitConfig` đăng ký SpringExtension và chỉ định cấu hình context. Spring tiêm `OrderService` vào instance của lớp ngoài và `OrderRepository` vào instance của lớp nested. Nếu lớp nested kế thừa cấu hình từ lớp ngoài, cả hai dependency được resolve từ cùng `ApplicationContext`.

`SpringExtension` triển khai callback `TestInstancePostProcessor` của JUnit Jupiter. Trong giai đoạn post-process test instance, extension gọi Spring TestContext để chuẩn bị instance. `DependencyInjectionTestExecutionListener` thực hiện việc inject các field và setter được đánh dấu phù hợp. Quá trình này áp dụng cho test instance của lớp nested khi SpringExtension được đăng ký cho test đó.

Vì vậy, field `@Autowired` đặt trong lớp nested được tiêm trước khi các callback `@BeforeEach` và phương thức test của instance đó chạy.

## 3. Cấu hình Spring được kế thừa từ lớp bao quanh

Khi test class dùng `@Nested`, Spring cần xác định annotation cấu hình nào trên lớp bao quanh được áp dụng cho lớp nested. Từ Spring Framework 5.3, TestContext Framework hỗ trợ cơ chế kế thừa này thông qua `@NestedTestConfiguration`.

Chế độ mặc định là `EnclosingConfiguration.INHERIT`. Lớp nested kế thừa cấu hình Spring từ enclosing test class:

```java
@SpringJUnitConfig(classes = SharedOrderTestConfiguration.class)
class OrderServiceTests {

    @Nested
    class CreateOrder {
        // Dùng context từ SharedOrderTestConfiguration.
    }

    @Nested
    class CancelOrder {
        // Cũng dùng cấu hình Spring được kế thừa.
    }
}
```

Nếu không khai báo cấu hình Spring khác trong lớp nested, các lớp con có thể dùng cùng metadata context. Khi cache còn entry tương ứng, Spring Test có thể tái sử dụng cùng `ApplicationContext`.

Các annotation Spring Test có thể được kế thừa theo cơ chế này gồm các annotation cấu hình context như `@ContextConfiguration`, `@ContextHierarchy`, `@WebAppConfiguration`, `@TestPropertySource`, `@ActiveProfiles` và một số annotation điều khiển quá trình test như `@Transactional` hoặc `@Sql`. Phạm vi cụ thể phụ thuộc annotation và phiên bản Spring đang dùng.

### 3.1. Bổ sung cấu hình riêng cho lớp nested

Mặc định, lớp nested có thể bổ sung cấu hình Spring của riêng nó. Với `@ContextConfiguration`, các class hoặc resource khai báo ở lớp nested được kết hợp với cấu hình kế thừa theo quy tắc kế thừa của annotation đó:

```java
@SpringJUnitConfig(classes = SharedOrderTestConfiguration.class)
class OrderServiceTests {

    @Nested
    @ContextConfiguration(classes = AuditTestConfiguration.class)
    class AuditedOrderTests {
        // Context có cấu hình dùng chung và cấu hình audit bổ sung.
    }
}
```

Các bean từ hai cấu hình phải tương thích với nhau. Nếu cả hai khai báo bean cùng kiểu hoặc cùng tên, cần xử lý bằng qualifier, primary hoặc cách tổ chức bean phù hợp.

### 3.2. Tắt kế thừa bằng OVERRIDE

Khi một nested test cần cấu hình độc lập với lớp bao quanh, có thể dùng:

```java
@Nested
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
class IsolatedNestedTests {
    // Khai báo cấu hình Spring riêng cho nhóm test này.
}
```

Ở chế độ `OVERRIDE`, Spring Test không kế thừa các annotation test context từ enclosing class. Lớp nested cần khai báo các annotation cấu hình mà nó cần sử dụng. Quy tắc kế thừa từ superclass của test class vẫn là một cơ chế riêng.

Có thể đặt `@NestedTestConfiguration` trên test class hoặc dùng meta-annotation để tạo quy ước chung. Dự án cũng có thể đặt annotation này trong `package-info.java` để thay đổi mặc định cho các test trong package.

### 3.3. Thay đổi mặc định bằng system property

Spring Test cho phép thay đổi chế độ kế thừa mặc định bằng system property:

```text
spring.test.enclosing.configuration=override
```

Giá trị `inherit` giữ hành vi kế thừa mặc định. Cấu hình package hoặc class cụ thể có thể làm rõ quy tắc tại phạm vi nhỏ hơn. Khi dùng thiết lập toàn cục, hãy bảo đảm nhóm test nested đã khai báo đầy đủ context cần thiết.

## 4. Ví dụ hoàn chỉnh: dùng chung bean ở lớp ngoài và lớp nested

Giả sử một service phụ thuộc vào repository:

```java
public interface OrderRepository {
    Optional<Order> findById(long id);
}

public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Order find(long id) {
        return repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Order not found"));
    }
}
```

Cấu hình Java dành cho test:

```java
@Configuration
class OrderTestConfiguration {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    OrderService orderService(OrderRepository orderRepository) {
        return new OrderService(orderRepository);
    }
}
```

Test class có thể inject service ở ngoài và repository ở lớp nested:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceNestedTests {

    @Autowired
    private OrderService orderService;

    @Nested
    class FindOrder {

        @Autowired
        private OrderRepository orderRepository;

        @Test
        void serviceIsInjectedIntoEnclosingTestInstance() {
            assertThat(orderService).isNotNull();
        }

        @Test
        void repositoryIsInjectedIntoNestedTestInstance() {
            assertThat(orderRepository).isNotNull();
        }

        @Test
        void nestedTestCanUseTheSharedServiceBean() {
            assertThat(orderService.find(42L)).isNotNull();
        }
    }
}
```

`OrderService` và `OrderRepository` được tạo như bean trong context. Mỗi test instance nhận tham chiếu đến bean theo cơ chế injection của Spring. Nếu bean dùng scope mặc định là singleton, các instance test có thể cùng tham chiếu đến một bean; việc tạo test instance mới không đồng nghĩa tạo context hoặc bean singleton mới.

Ví dụ giả định `InMemoryOrderRepository` có dữ liệu test cho mã đơn hàng 42. Trong dự án thực tế, có thể dùng repository fake, cấu hình persistence test hoặc mock bean tùy mục tiêu kiểm thử.

## 5. Tiêm dependency bằng field và setter

Field injection là cách thường thấy trong Spring test:

```java
@Nested
class UpdateOrder {

    @Autowired
    private OrderService orderService;

    @Test
    void updatesOrder() {
        assertThat(orderService).isNotNull();
    }
}
```

Setter injection cũng được hỗ trợ:

```java
@Nested
class DeleteOrder {

    private OrderService orderService;

    @Autowired
    void setOrderService(OrderService orderService) {
        this.orderService = orderService;
    }

    @Test
    void deletesOrder() {
        assertThat(orderService).isNotNull();
    }
}
```

Field injection phù hợp với test fixture nhỏ vì ít mã thiết lập. Setter injection có thể hữu ích khi muốn thực hiện thêm thao tác chuẩn bị sau khi dependency được cung cấp. Cả hai đều được Spring xử lý trong bước chuẩn bị test instance.

Không nên tự gọi setter hoặc tự tạo bean trong `@BeforeEach` chỉ để thay thế việc inject đã được Spring quản lý. Hãy để một cơ chế rõ ràng chịu trách nhiệm cung cấp dependency cho test.

## 6. Tiêm dependency qua tham số phương thức test

`SpringExtension` còn hỗ trợ resolve tham số cho test method và các lifecycle method phù hợp. Có thể dùng `@Autowired` trên tham số:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceNestedTests {

    @Nested
    class FindOrder {

        @Test
        void findsOrder(@Autowired OrderService orderService) {
            assertThat(orderService).isNotNull();
        }
    }
}
```

Cách này hữu ích khi dependency chỉ cần trong một phương thức. Nó cũng có thể dùng trong `@BeforeEach`:

```java
@Nested
class FindOrder {

    private OrderService orderService;

    @BeforeEach
    void setUp(@Autowired OrderService service) {
        this.orderService = service;
    }

    @Test
    void findsOrder() {
        assertThat(orderService).isNotNull();
    }
}
```

Tham số được resolve bởi SpringExtension phải được phân biệt với tham số do JUnit hoặc extension khác quản lý. Nếu một test class đăng ký nhiều extension có thể xử lý cùng tham số, hãy dùng annotation qualifier phù hợp hoặc cấu hình resolver rõ ràng để tránh xung đột.

## 7. Constructor injection trong nested test class

Spring Test hỗ trợ constructor injection cho test class thông qua `@TestConstructor` hoặc constructor được đánh dấu `@Autowired`. Có thể chọn chế độ tự động inject tất cả tham số constructor:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class OrderServiceConstructorTests {

    private final OrderService orderService;

    OrderServiceConstructorTests(OrderService orderService) {
        this.orderService = orderService;
    }
}
```

Với nested test class, JUnit còn phải cung cấp enclosing instance theo quy tắc của lớp thành viên không static. Vì vậy, field injection hoặc method parameter injection thường dễ đọc và ít gây nhầm lẫn hơn khi lớp nested chỉ cần một vài bean. Nếu dùng constructor injection, cần bảo đảm constructor parameter được SpringExtension hỗ trợ và không xung đột với cách JUnit tạo nested instance.

Chế độ constructor autowire mặc định có thể được điều khiển bằng annotation `@TestConstructor` hoặc thuộc tính `spring.test.constructor.autowire.mode` theo phiên bản Spring. Không nên bật chế độ toàn cục nếu chỉ một nhóm test cần constructor injection.

## 8. Vòng đời của lớp ngoài và lớp nested

Với JUnit Jupiter, các lifecycle callback của lớp bao quanh tham gia vào việc chạy nested test. Ví dụ, `@BeforeEach` ở lớp ngoài được thực thi trước `@BeforeEach` của lớp nested cho mỗi nested test invocation. Callback `@AfterEach` chạy theo thứ tự ngược lại.

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceNestedTests {

    @Autowired
    OrderService orderService;

    @BeforeEach
    void prepareOuterTest() {
        // Dependency của lớp ngoài đã được inject.
    }

    @Nested
    class FindOrder {

        @Autowired
        OrderRepository orderRepository;

        @BeforeEach
        void prepareNestedTest() {
            // Dependency của lớp nested đã được inject.
        }

        @Test
        void findsOrder() {
            assertThat(orderService).isNotNull();
            assertThat(orderRepository).isNotNull();
        }
    }
}
```

Việc tiêm dependency diễn ra trong giai đoạn post-process test instance, trước các callback setup của test instance đó. Vì vậy, các phương thức `@BeforeEach` có thể sử dụng field đã được inject.

Mặc định, JUnit dùng `PER_METHOD`. Nếu chuyển sang `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, instance test được tái sử dụng trong phạm vi class tương ứng. Việc này ảnh hưởng trạng thái field của test class và cách dùng `@BeforeAll`, nhưng không thay đổi nguyên tắc Spring tiêm dependency vào test instance. Hãy tránh để mutable state của một nested test ảnh hưởng đến test khác.

Một nested class có thể dùng `@BeforeAll` không static khi lifecycle của nó là `PER_CLASS`. Nếu không thay đổi lifecycle, `@BeforeAll` vẫn phải tuân theo quy tắc static của JUnit Jupiter.

## 9. Context được chia sẻ, test instance thì riêng biệt

Có hai vòng đời cần hiểu:

| Thành phần | Vòng đời thường gặp |
|---|---|
| Test instance | JUnit tạo theo lifecycle `PER_METHOD` hoặc `PER_CLASS`. |
| Nested test instance | Được tạo theo từng nested test và gắn với enclosing instance. |
| Spring ApplicationContext | Được TestContext Framework cache theo cấu hình đã hợp nhất. |
| Singleton bean | Thường tồn tại trong suốt vòng đời context và được nhiều test instance cùng tham chiếu. |

Ví dụ, hai nested class có thể cùng nhận một bean `OrderService` từ cùng context. Mỗi nested class có field riêng chứa tham chiếu đến bean đó, nhưng bean singleton mà hai field trỏ tới có thể là cùng một object.

Điều này có ý nghĩa khi bean chứa mutable state. Nếu một test thay đổi trạng thái dùng chung của singleton, test sau có thể nhìn thấy thay đổi đó. Nên dọn dữ liệu hoặc reset trạng thái bằng fixture phù hợp; chỉ dùng `@DirtiesContext` khi context thực sự không thể tái sử dụng an toàn.

## 10. Tổ chức nested tests theo bối cảnh nghiệp vụ

Một cách tổ chức thường gặp là đặt các dependency chung ở lớp ngoài, còn các lớp nested tập trung vào từng nhóm hành vi:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceTests {

    @Autowired
    OrderService orderService;

    @Nested
    class Create {

        @Test
        void createsOrder() {
            // Kiểm tra tạo đơn hàng hợp lệ.
        }

        @Test
        void rejectsInvalidQuantity() {
            // Kiểm tra dữ liệu đầu vào không hợp lệ.
        }
    }

    @Nested
    class Find {

        @Test
        void returnsExistingOrder() {
            // Kiểm tra tìm thấy đơn hàng.
        }

        @Test
        void reportsMissingOrder() {
            // Kiểm tra trường hợp không tồn tại.
        }
    }

    @Nested
    class Cancel {

        @Test
        void cancelsPendingOrder() {
            // Kiểm tra hủy đơn hàng đang chờ.
        }
    }
}
```

Nếu dependency chỉ cần cho một nhóm hành vi, có thể inject trực tiếp trong lớp nested đó. Cách này giúp thể hiện phạm vi sử dụng của dependency và tránh làm lớp ngoài chứa quá nhiều field chỉ phục vụ một nhánh test.

Nếu mọi nested class đều cần cùng một service, inject ở lớp ngoài có thể giảm lặp lại. Cả hai cách đều hợp lệ; hãy chọn theo mức độ dùng chung thực tế và khả năng đọc của test.

## 11. Kết hợp nested tests với cấu hình riêng

Một số nhóm test có thể cần profile hoặc property riêng. Vì các annotation cấu hình được kế thừa theo mặc định, hãy khai báo phần khác biệt tại lớp nested:

```java
@SpringJUnitConfig(classes = PaymentTestConfiguration.class)
@ActiveProfiles("test")
class PaymentServiceTests {

    @Nested
    @TestPropertySource(properties = "payment.mode=offline")
    class OfflinePayment {
        // Bổ sung property cho nhóm test offline.
    }

    @Nested
    @TestPropertySource(properties = "payment.mode=online")
    class OnlinePayment {
        // Bổ sung property cho nhóm test online.
    }
}
```

Các property khác nhau làm metadata context khác nhau, do đó hai nhóm nested có thể cần hai context riêng. Không nên kỳ vọng chúng dùng chung context chỉ vì cùng nằm trong một outer test class.

Nếu muốn một nhóm nested không kế thừa cấu hình ngoài, dùng `@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)` và khai báo đầy đủ cấu hình cần thiết. Việc thay đổi policy kế thừa cần được thực hiện có chủ đích vì nó ảnh hưởng đến cả annotation context và các annotation Spring Test liên quan.

## 12. Tương tác với @TestExecutionListeners

Spring Test sử dụng các `TestExecutionListener` để thực hiện công việc trong vòng đời test, trong đó có inject dependency. Listener mặc định `DependencyInjectionTestExecutionListener` đảm nhiệm việc tiêm các dependency được khai báo trong test class.

Nếu tùy chỉnh danh sách listener bằng `@TestExecutionListeners`, cần chú ý chế độ kế thừa và listener mặc định. Việc thay thế danh sách listener không đúng có thể làm mất listener dependency injection, khiến field `@Autowired` trong lớp ngoài hoặc nested không được gán.

Khi chỉ muốn bổ sung listener riêng, hãy dùng thuộc tính hợp nhất phù hợp của phiên bản Spring thay vì vô tình thay toàn bộ listener mặc định. Nếu gặp lỗi dependency trong nested class, kiểm tra cả việc SpringExtension có được đăng ký và listener inject có còn trong cấu hình TestContext hay không.

## 13. Những lỗi thường gặp

### Thiếu SpringExtension

`@Nested` chỉ tổ chức test theo JUnit Jupiter. Nó không tự kích hoạt Spring dependency injection. Nếu test cần `@Autowired`, phải đăng ký `SpringExtension` thông qua `@ExtendWith(SpringExtension.class)` hoặc `@SpringJUnitConfig`.

### Mong Spring tiêm field khi nested class không thuộc Spring test

Nếu lớp nested nằm trong một test class không đăng ký SpringExtension hoặc không có context metadata phù hợp, field `@Autowired` không được xử lý. Kiểm tra extension và cấu hình context trước khi kiểm tra bean.

### Dùng phiên bản Spring trước 5.3 nhưng trông chờ kế thừa cấu hình nested

`@NestedTestConfiguration` được giới thiệu trong Spring Framework 5.3. Với phiên bản cũ, cần khai báo cấu hình Spring tường minh cho nested test theo cách mà phiên bản đó hỗ trợ; không giả định cấu hình từ lớp bao quanh tự được kế thừa.

### Kế thừa cấu hình ngoài ý muốn

Nếu nested class cần một context độc lập nhưng vẫn ở chế độ `INHERIT`, các annotation cấu hình của lớp ngoài có thể được gộp vào. Dùng `OVERRIDE` khi muốn ngừng kế thừa cấu hình Spring từ enclosing class.

### Nhầm test instance với bean instance

Một test instance mới không có nghĩa Spring tạo một bean singleton mới. Nhiều test instance có thể cùng tham chiếu đến bean trong context cache. Hãy quản lý trạng thái dùng chung cẩn thận.

### Lớp nested cần dependency nhưng field đặt sai phạm vi

Field private của lớp ngoài không tự trở thành field của lớp nested. Nested class có thể truy cập thành viên của enclosing instance theo quy tắc Java, nhưng nếu cần dependency trực tiếp trong nested test, khai báo field injection ngay tại nested class sẽ làm ý định rõ ràng hơn.

### Constructor injection xung đột với việc tạo nested instance

Nested class có enclosing instance được JUnit cung cấp theo quy tắc của JUnit Jupiter. Khi constructor injection không được resolve như mong muốn, hãy kiểm tra `@TestConstructor` và các parameter resolver. Với test nested đơn giản, field hoặc method parameter injection thường dễ cấu hình hơn.

### @TestExecutionListeners làm mất listener inject

Nếu danh sách listener bị thay thế mà không giữ listener mặc định cần thiết, dependency injection có thể ngừng hoạt động. Kiểm tra cấu hình listener và chế độ merge khi tùy chỉnh.

### Dùng @DirtiesContext để sửa mọi lỗi trạng thái

`@DirtiesContext` loại context khỏi cache và làm test khởi tạo lại context. Nếu chỉ cần reset dữ liệu hoặc trạng thái của một collaborator, hãy dọn trạng thái ở phạm vi đó để tránh tạo lại toàn bộ context không cần thiết.

## 14. Chọn cách tiêm dependency phù hợp

| Nhu cầu | Cách làm |
|---|---|
| Nhiều nested class cùng dùng một service | Inject service ở lớp ngoài nếu mọi nhóm test đều cần nó. |
| Chỉ một nested class cần một repository | Đặt `@Autowired` field ngay trong nested class đó. |
| Dependency chỉ cần trong một test method | Dùng tham số method có `@Autowired`. |
| Muốn constructor injection cho test | Dùng `@TestConstructor` hoặc constructor `@Autowired`, chú ý enclosing instance của nested class. |
| Nested class cần bổ sung bean/config | Dùng `@ContextConfiguration` bổ sung theo quy tắc merge. |
| Nested class cần context riêng | Dùng `@NestedTestConfiguration(OVERRIDE)` và khai báo cấu hình độc lập. |
| Cần cùng context cho nhiều nhóm nested | Giữ metadata cấu hình tương đương để TestContext cache có thể tái sử dụng. |

Khi viết nested tests với Spring, hãy để JUnit quản lý cấu trúc và vòng đời của các lớp lồng, đồng thời để SpringExtension chuẩn bị từng test instance. Dùng cấu hình được kế thừa khi các nhóm test thực sự chia sẻ cùng môi trường; inject dependency tại đúng phạm vi sử dụng để test dễ đọc và dễ bảo trì.
