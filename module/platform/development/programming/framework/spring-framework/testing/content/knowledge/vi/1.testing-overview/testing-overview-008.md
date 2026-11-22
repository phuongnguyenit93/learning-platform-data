# Quan hệ giữa khả năng kiểm thử và thiết kế Dependency Injection

Khả năng kiểm thử (testability) là mức độ dễ dàng để tạo một đối tượng trong điều kiện kiểm soát, cung cấp dữ liệu đầu vào, thay thế các dịch vụ bên ngoài và quan sát kết quả. Trong ứng dụng Spring, thiết kế Dependency Injection (DI) ảnh hưởng trực tiếp đến khả năng đó: một lớp nhận các phụ thuộc từ bên ngoài thường dễ khởi tạo, cô lập và kiểm tra hơn một lớp tự tìm hoặc tự tạo các dịch vụ mà nó cần.

DI không phải kỹ thuật chỉ dành cho bài kiểm thử. Đây là cách tổ chức việc tạo và kết nối đối tượng trong ứng dụng. Khi các phụ thuộc được khai báo rõ ràng, Spring có thể lắp ráp chúng ở lúc chạy ứng dụng, còn bài kiểm thử có thể tự lắp ráp đối tượng với các phụ thuộc giả phù hợp. Một thiết kế tốt vì vậy hỗ trợ cả mã chạy thật lẫn mã kiểm thử.

## 1. Khả năng kiểm thử phản ánh chất lượng thiết kế

Một lớp có khả năng kiểm thử tốt thường có bốn đặc điểm:

1. **Có thể khởi tạo dễ dàng:** người viết test có thể tạo đối tượng cần kiểm tra mà không phải khởi động toàn bộ ứng dụng.
2. **Có thể kiểm soát phụ thuộc:** test có thể cung cấp dữ liệu giả, bộ nhớ giả, đồng hồ cố định hoặc cổng giao tiếp giả thay cho cơ sở dữ liệu, mạng và hệ thống bên ngoài.
3. **Có thể tạo kết quả lặp lại:** cùng một đầu vào và cùng trạng thái ban đầu tạo ra kết quả ổn định; test không phụ thuộc ngẫu nhiên vào thời gian, mạng hoặc dữ liệu môi trường.
4. **Có thể quan sát hành vi:** kết quả trả về, trạng thái được lưu hoặc tương tác với một ranh giới bên ngoài có thể được kiểm tra qua hợp đồng rõ ràng.

Ví dụ, một dịch vụ tính hạn sử dụng gọi trực tiếp Instant.now() sẽ phụ thuộc vào thời điểm máy chạy test. Bài kiểm thử phải đoán thời gian hoặc chờ đến một mốc cụ thể. Nếu dịch vụ nhận Clock từ bên ngoài, test có thể dùng đồng hồ cố định:

~~~java
import java.time.Clock;
import java.time.Instant;

public class ExpirationPolicy {
    private final Clock clock;

    public ExpirationPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !expiresAt.isAfter(clock.instant());
    }
}
~~~

Test có thể kiểm soát chính xác thời điểm hiện tại:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class ExpirationPolicyTest {
    @Test
    void considersAnInstantBeforeTheFixedTimeExpired() {
        Instant fixedNow = Instant.parse("2026-11-12T10:00:00Z");
        Clock clock = Clock.fixed(fixedNow, ZoneOffset.UTC);
        ExpirationPolicy policy = new ExpirationPolicy(clock);

        boolean expired = policy.isExpired(
                Instant.parse("2026-11-12T09:59:59Z"));

        assertTrue(expired);
    }
}
~~~

Không phải mọi đối tượng đều cần được đưa vào Spring hoặc biến thành interface. Clock là một phụ thuộc có ý nghĩa vì thời gian hiện tại là yếu tố bên ngoài có thể làm test mất tính xác định. Một đối tượng giá trị nhỏ, thuần túy và không có trạng thái bên ngoài vẫn có thể được tạo trực tiếp trong phương thức hoặc trong test.

Khả năng kiểm thử thường bộc lộ cùng các vấn đề thiết kế khác. Nếu một lớp chỉ có thể kiểm tra sau khi dựng cả ứng dụng, kết nối cơ sở dữ liệu và gọi dịch vụ thật, lớp đó có thể đang gắn quá chặt với hạ tầng. Nếu test phải dùng reflection để gán một trường riêng tư, hoặc phải sửa trạng thái static trước và sau mỗi test, các phụ thuộc của lớp đang bị che giấu. Test khó viết là tín hiệu để xem lại ranh giới trách nhiệm và cách quản lý phụ thuộc.

## 2. Dependency Injection làm phụ thuộc trở nên tường minh

Dependency Injection là cách một đối tượng nhận những đối tượng hoặc giá trị mà nó cần từ bên ngoài, thay vì tự tìm chúng. Trong Spring, container tạo bean, giải quyết các phụ thuộc và kết nối chúng theo cấu hình, component scan hoặc khai báo bean.

Hãy xét một dịch vụ đặt hàng cần cổng thanh toán và nơi lưu đơn hàng:

~~~java
public record Order(String id, java.math.BigDecimal amount) {
}

public interface PaymentGateway {
    void charge(String orderId, java.math.BigDecimal amount);
}

public interface OrderRepository {
    void save(Order order);
}
~~~

Dịch vụ nhận hai phụ thuộc qua constructor:

~~~java
import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final PaymentGateway paymentGateway;
    private final OrderRepository orderRepository;

    public OrderService(
            PaymentGateway paymentGateway,
            OrderRepository orderRepository) {
        this.paymentGateway = paymentGateway;
        this.orderRepository = orderRepository;
    }

    public Order place(String orderId, BigDecimal amount) {
        Order order = new Order(orderId, amount);
        paymentGateway.charge(orderId, amount);
        orderRepository.save(order);
        return order;
    }
}
~~~

Constructor thể hiện đầy đủ điều kiện để OrderService hoạt động. Khi Spring tạo bean, container phải tìm được một bean PaymentGateway và một bean OrderRepository. Nếu thiếu một phụ thuộc bắt buộc hoặc có nhiều bean không phân giải được, lỗi xuất hiện lúc tạo context thay vì đợi đến khi một nhánh nghiệp vụ hiếm gặp được gọi.

Trong bài kiểm thử đơn vị, ta có thể tạo dịch vụ trực tiếp và đưa vào các đối tượng thay thế. Không cần chạy component scan, tạo ApplicationContext hay khởi động Spring Boot chỉ để kiểm tra logic của place.

### Constructor injection và khả năng kiểm thử

Constructor injection thường là lựa chọn phù hợp nhất cho các phụ thuộc bắt buộc:

- **Phụ thuộc được khai báo rõ:** nhìn vào constructor có thể biết lớp cần những gì.
- **Đối tượng hoàn chỉnh sau khi tạo:** không có khoảng thời gian đối tượng tồn tại nhưng một trường bắt buộc vẫn chưa được gán.
- **Dễ khởi tạo trong unit test:** test gọi constructor trực tiếp và truyền mock hoặc fake.
- **Hỗ trợ tính bất biến:** các trường phụ thuộc có thể khai báo final, tránh thay đổi kết nối sau khi khởi tạo.
- **Lỗi cấu hình được phát hiện sớm:** Spring không thể tạo bean nếu không giải quyết được các tham số constructor bắt buộc.

Với một constructor duy nhất, Spring tự động sử dụng constructor đó để inject; thông thường không cần đặt @Autowired trên constructor. Việc gọi constructor trực tiếp trong test cũng không cần annotation Spring.

### Field injection che giấu điều kiện khởi tạo

Một cách viết kém thuận lợi cho kiểm thử là:

~~~java
@Service
public class ReportService {
    @Autowired
    private ReportRepository repository;

    public Report find(String id) {
        return repository.findById(id);
    }
}
~~~

Khi gọi new ReportService() trong test, trường repository chưa được Spring gán. Test không thể cung cấp phụ thuộc qua constructor và thường phải khởi động Spring context hoặc dùng reflection để sửa trạng thái nội bộ. Cách này làm test phụ thuộc vào cơ chế khởi tạo của framework thay vì kiểm tra hành vi của lớp.

Có thể viết lại bằng constructor injection:

~~~java
@Service
public class ReportService {
    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    public Report find(String id) {
        return repository.findById(id);
    }
}
~~~

Setter injection vẫn có chỗ dùng cho phụ thuộc thực sự tùy chọn hoặc có thể thay đổi sau khi tạo đối tượng. Tuy nhiên, không nên dùng setter để né một constructor có nhiều phụ thuộc bắt buộc. Nếu một lớp có quá nhiều tham số constructor, đó thường là dấu hiệu lớp đang đảm nhiệm nhiều trách nhiệm và cần xem xét tách nhỏ.

## 3. Thay thế phụ thuộc để kiểm tra hành vi

Với OrderService, bài test có thể dùng Mockito để mô phỏng hai ranh giới bên ngoài:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import java.math.BigDecimal;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {
    @Mock
    PaymentGateway paymentGateway;

    @Mock
    OrderRepository orderRepository;

    private OrderService service;

    @BeforeEach
    void setUp() {
        service = new OrderService(paymentGateway, orderRepository);
    }

    @Test
    void chargesAndSavesTheOrder() {
        BigDecimal amount = new BigDecimal("125.00");

        Order result = service.place("O-100", amount);

        assertEquals(new Order("O-100", amount), result);
        verify(paymentGateway).charge("O-100", amount);
        verify(orderRepository).save(new Order("O-100", amount));
    }

    @Test
    void doesNotSaveWhenPaymentFails() {
        BigDecimal amount = new BigDecimal("125.00");
        doThrow(new IllegalStateException("Payment declined"))
                .when(paymentGateway)
                .charge("O-100", amount);

        assertThrows(
                IllegalStateException.class,
                () -> service.place("O-100", amount));

        verify(paymentGateway).charge("O-100", amount);
        verifyNoInteractions(orderRepository);
    }
}
~~~

Test tự tạo OrderService bằng constructor và chủ động điều khiển kết quả của cổng thanh toán. Test thứ nhất kiểm tra đơn hàng trả về và các tương tác cần thiết. Test thứ hai mô phỏng lỗi thanh toán và xác nhận kho lưu trữ chưa được gọi. Đây là unit test: nó kiểm tra hành vi của một lớp trong điều kiện cô lập, không kiểm tra việc Spring đăng ký bean.

Các đối tượng thay thế có thể có nhiều dạng:

| Loại test double | Mục đích | Ví dụ sử dụng |
|---|---|---|
| Stub | Trả về dữ liệu đã định trước | Một repository trả về một đơn hàng mẫu |
| Fake | Có triển khai đơn giản nhưng hoạt động được | Repository lưu dữ liệu trong Map thay cho cơ sở dữ liệu |
| Mock | Ghi nhận hoặc yêu cầu một tương tác cụ thể | Xác nhận PaymentGateway.charge() được gọi |
| Spy | Theo dõi một đối tượng thật hoặc một phần hành vi thật | Chỉ dùng khi cần quan sát tương tác mà vẫn giữ triển khai thật |

Mock hữu ích khi hợp đồng của lớp bao gồm việc gọi một ranh giới bên ngoài. Tuy nhiên, nếu mọi test đều xác minh từng lời gọi nội bộ, test sẽ dễ hỏng khi refactor dù hành vi bên ngoài không đổi. Hãy ưu tiên kiểm tra kết quả và trạng thái có ý nghĩa; chỉ xác minh tương tác khi tương tác đó thực sự là một phần của yêu cầu, chẳng hạn không gửi thanh toán hai lần hoặc không lưu đơn hàng sau khi thanh toán thất bại.

## 4. Kiểm tra Spring wiring riêng với unit test

Unit test ở trên chứng minh logic của OrderService với các phụ thuộc do test cung cấp. Nó không chứng minh Spring có thể tạo bean và kết nối các bean trong ứng dụng. Đó là một câu hỏi kiểm thử khác, cần một Spring context phù hợp.

Spring TestContext Framework cung cấp @SpringJUnitConfig để tạo context cho JUnit Jupiter. Ta có thể chỉ đăng ký dịch vụ cần kiểm tra và các bean thay thế:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderServiceContextTest.TestConfig.class)
class OrderServiceContextTest {
    @Autowired
    OrderService service;

    @Autowired
    InMemoryOrderRepository repository;

    @Test
    void springCreatesTheServiceWithTheConfiguredDependencies() {
        BigDecimal amount = new BigDecimal("80.00");

        service.place("O-200", amount);

        assertEquals(
                new Order("O-200", amount),
                repository.findById("O-200"));
    }

    @Configuration
    @Import(OrderService.class)
    static class TestConfig {
        @Bean
        PaymentGateway paymentGateway() {
            return (orderId, amount) -> {
                // Không gọi hệ thống thanh toán thật trong test.
            };
        }

        @Bean
        InMemoryOrderRepository orderRepository() {
            return new InMemoryOrderRepository();
        }
    }
}

class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new ConcurrentHashMap<>();

    @Override
    public void save(Order order) {
        orders.put(order.id(), order);
    }

    public Order findById(String id) {
        return orders.get(id);
    }
}
~~~

Trong ví dụ này, @Import(OrderService.class) đăng ký dịch vụ vào context; các phương thức @Bean cung cấp cổng thanh toán và repository dùng trong test. Spring thực hiện constructor injection giống như khi chạy ứng dụng. Repository giả vẫn lưu dữ liệu để test kiểm tra trạng thái sau khi gọi dịch vụ.

Kiểu test này có thể phát hiện lỗi wiring như thiếu bean, constructor không phân giải được hoặc cấu hình tạo ra bean sai. Nó có chi phí cao hơn unit test vì phải tạo context, nên chỉ dùng khi câu hỏi cần kiểm tra thực sự liên quan đến Spring container. @SpringJUnitConfig không khởi động toàn bộ Spring Boot application; cấu hình test chỉ bao gồm những thành phần đã khai báo hoặc import.

### Chọn đúng phạm vi kiểm thử trong hệ sinh thái Spring

| Phạm vi | Công cụ thường dùng | Điều cần xác nhận |
|---|---|---|
| Unit test | JUnit Jupiter, Mockito, fake tự viết | Logic của một lớp với phụ thuộc được kiểm soát |
| Spring context test | @SpringJUnitConfig, @ContextConfiguration | Bean được tạo và inject đúng trong một context giới hạn |
| Boot integration test | @SpringBootTest | Cấu hình ứng dụng và nhiều thành phần phối hợp trong context gần với runtime |
| Boot slice test | @WebMvcTest, @DataJpaTest | Một lát cắt như MVC hoặc JPA hoạt động với cấu hình liên quan |

Các annotation slice như @WebMvcTest và @DataJpaTest thuộc hệ sinh thái Spring Boot Test. Chúng giúp kiểm tra một lớp hạ tầng mà không phải dựng toàn bộ ứng dụng. Không nên chọn @SpringBootTest mặc định cho mọi test chỉ vì dự án sử dụng Spring Boot.

Một cách chia phạm vi hợp lý là:

- Dùng unit test cho quy tắc nghiệp vụ, phép tính và nhánh xử lý có thể kiểm tra bằng đối tượng Java thông thường.
- Dùng Spring context test khi cần xác nhận cách bean được khai báo, inject hoặc cấu hình.
- Dùng slice test khi cần xác nhận một lớp tích hợp cụ thể như controller, JSON mapping hoặc repository.
- Dùng integration test rộng hơn khi cần xác nhận nhiều thành phần phối hợp, transaction, cấu hình bảo mật hoặc giao tiếp với hạ tầng.

Các cấp test bổ sung cho nhau. Unit test nhanh không thể xác nhận cấu hình Spring; một integration test thành công cũng không thay thế được nhiều unit test tập trung vào các nhánh nghiệp vụ.

## 5. Những thiết kế DI làm giảm khả năng kiểm thử

DI chỉ giúp khi nó làm rõ ranh giới phụ thuộc. Một số cách sử dụng vẫn khiến test khó viết hoặc khó bảo trì.

### Tự tạo phụ thuộc hạ tầng bên trong lớp nghiệp vụ

Ví dụ, một service tự tạo HTTP client, repository hoặc adapter cụ thể:

~~~java
public class CustomerService {
    private final CustomerRepository repository =
            new JdbcCustomerRepository();

    public Customer find(String id) {
        return repository.findById(id);
    }
}
~~~

Test không thể thay repository mà không sửa mã hoặc can thiệp trạng thái nội bộ. Lớp nghiệp vụ đang quyết định cả hành vi lẫn cách tạo hạ tầng. Hãy chuyển việc tạo repository về composition root (nơi lắp ráp đối tượng), thường là Spring container, rồi truyền repository qua constructor.

Việc dùng new không phải lúc nào cũng sai. Tạo một DTO, value object, collection hoặc đối tượng thuần túy rẻ và xác định ngay trong phương thức là bình thường. Vấn đề nằm ở việc tự tạo một phụ thuộc mà test cần thay thế, đặc biệt khi phụ thuộc đó truy cập mạng, cơ sở dữ liệu, thời gian hệ thống hoặc trạng thái dùng chung.

### Dùng ApplicationContext như service locator

Một lớp có thể nhận ApplicationContext rồi gọi getBean() khi cần:

~~~java
public class CustomerService {
    private final ApplicationContext context;

    public CustomerService(ApplicationContext context) {
        this.context = context;
    }

    public Customer find(String id) {
        CustomerRepository repository =
                context.getBean(CustomerRepository.class);
        return repository.findById(id);
    }
}
~~~

Constructor chỉ cho thấy lớp phụ thuộc vào ApplicationContext; các dịch vụ thực sự cần thiết bị ẩn bên trong thân phương thức. Test phải dựng context hoặc mô phỏng cả service locator. Hãy inject trực tiếp CustomerRepository để đồ thị phụ thuộc có thể đọc được và test có thể thay thế đúng ranh giới.

### Tạo quá nhiều interface chỉ để mock

Không cần tạo một interface cho mọi lớp. Nếu một lớp nhỏ, ổn định, không chứa I/O và không có nhu cầu thay thế triển khai, inject trực tiếp kiểu cụ thể có thể đơn giản hơn. Interface có giá trị khi nó thể hiện một hợp đồng, tách nghiệp vụ khỏi hạ tầng, có nhiều triển khai hợp lệ hoặc tạo ranh giới thay thế có ý nghĩa.

Một interface được tạo chỉ để test mock có thể làm tăng số lượng kiểu và khiến luồng chương trình khó theo dõi. Khả năng kiểm thử tốt đến từ phụ thuộc được quản lý đúng, không đến từ số lượng interface.

### Dồn quá nhiều trách nhiệm vào một service

Constructor có quá nhiều tham số thường báo hiệu lớp đang phối hợp nhiều nhóm công việc. Thêm mock cho từng tham số có thể giúp test chạy, nhưng không giải quyết vấn đề trách nhiệm. Hãy xem xét liệu lớp có thể tách thành các thành phần có mục đích rõ hơn hay không. Mỗi thành phần nên có một tập phụ thuộc vừa đủ để thực hiện trách nhiệm của nó.

Không nên gom mọi phụ thuộc vào một Map, một đối tượng ApplicationContext hoặc một lớp provider chung chỉ để làm constructor ngắn lại. Cách đó làm mất thông tin về những dịch vụ thực sự cần thiết.

### Dùng trạng thái static hoặc singleton có thể thay đổi

Trạng thái static dùng chung giữa các test khiến thứ tự chạy test có thể ảnh hưởng kết quả. Một test thay đổi cấu hình hoặc dữ liệu toàn cục có thể làm test khác thất bại. Hãy ưu tiên trạng thái nằm trong phạm vi đối tượng hoặc context, truyền các phụ thuộc cần thiết từ bên ngoài và khởi tạo dữ liệu test độc lập. Nếu có trạng thái dùng chung bắt buộc, cần có cơ chế reset rõ ràng và kiểm tra khả năng chạy song song.

## 6. Thiết kế ranh giới phụ thuộc phù hợp

Một thiết kế dễ kiểm thử không có nghĩa là mọi lớp đều phải được mock. Điều quan trọng là phân biệt logic thuần túy với những khả năng cần giao tiếp ra bên ngoài.

| Nhóm phụ thuộc | Ví dụ | Cách tổ chức phù hợp |
|---|---|---|
| Giá trị và logic thuần túy | Money, bộ chuyển đổi, quy tắc tính phí | Tạo trực tiếp; kiểm tra bằng input/output |
| Thời gian và nguồn tạo dữ liệu biến đổi | Clock, ID generator, random source | Inject để test kiểm soát được kết quả |
| Lưu trữ | Repository, cache | Inject qua hợp đồng phù hợp; dùng fake hoặc database test tùy phạm vi |
| Giao tiếp bên ngoài | HTTP client, email sender, payment gateway | Inject adapter hoặc port; mock/fake trong test cô lập |
| Cấu hình | URL, timeout, giới hạn nghiệp vụ | Bind thành cấu hình có kiểu; test với giá trị rõ ràng |

Trong kiến trúc có phân lớp hoặc ports-and-adapters, lớp nghiệp vụ phụ thuộc vào hợp đồng mà nó cần. Adapter cụ thể thực hiện hợp đồng đó bằng JDBC, HTTP hoặc một công nghệ khác. Spring kết nối implementation trong ứng dụng thật; test có thể cung cấp fake hoặc mock. Đây là cách dùng DI có mục đích: hướng phụ thuộc về các hợp đồng ổn định và cho phép thay đổi hạ tầng mà không phải sửa logic nghiệp vụ.

Không nhất thiết phải tạo interface cho mọi phụ thuộc ngay từ đầu. Hãy bắt đầu từ nhu cầu thực tế: phụ thuộc nào gây I/O, có trạng thái biến đổi, khó tạo trong test hoặc có khả năng có nhiều implementation? Tách hợp đồng ở các ranh giới đó. Với logic thuần túy, giữ mã đơn giản và kiểm tra trực tiếp thường hiệu quả hơn.

## 7. Quản lý Spring context trong test

Spring TestContext Framework có thể lưu cache các ApplicationContext để những test có cấu hình tương đương dùng lại context. Điều này giảm thời gian khởi tạo, nhưng cũng khiến cấu hình test và trạng thái dùng chung cần được tổ chức cẩn thận.

Một số nguyên tắc thực tế:

- Giữ cấu hình context tập trung và ổn định khi nhiều test có thể dùng chung.
- Không để dữ liệu mutable trong singleton bean làm test phụ thuộc thứ tự chạy.
- Dọn dữ liệu trong repository hoặc database theo cơ chế rõ ràng ở mỗi test.
- Chỉ dùng @DirtiesContext khi test thực sự làm thay đổi context đến mức không thể dùng lại; annotation này yêu cầu Spring loại context khỏi cache và tạo lại khi cần.
- Hạn chế tạo quá nhiều cấu hình context khác nhau nếu chúng không kiểm tra các hành vi khác nhau, vì mỗi cấu hình có thể cần một context riêng.

Nếu một test chỉ kiểm tra phép tính hoặc nhánh xử lý của service, hãy tạo service trực tiếp. Nếu test cần xác nhận bean wiring, dùng context nhỏ. Nếu cần kiểm tra cấu hình ứng dụng rộng, dùng @SpringBootTest có chủ đích. Phạm vi càng rộng thì chi phí khởi tạo và khả năng phụ thuộc hạ tầng càng lớn.

## 8. Đọc tín hiệu từ một test khó viết

Khi test khó khởi tạo hoặc thường xuyên thất bại, hãy xác định nguyên nhân trước khi thêm annotation hoặc mock. Các câu hỏi sau giúp tìm đúng vấn đề:

1. **Test có phải khởi động Spring chỉ để tạo một đối tượng không?** Nếu có, xem lớp có thể dùng constructor injection và được khởi tạo như Java object thông thường hay không.
2. **Có phụ thuộc nào tự tạo hoặc tự tìm bên trong lớp không?** Chuyển việc tạo phụ thuộc ra ngoài và inject qua constructor.
3. **Kết quả có phụ thuộc thời gian, random, mạng hoặc dữ liệu môi trường không?** Đưa nguồn biến đổi vào một phụ thuộc có thể kiểm soát.
4. **Test có cần reflection để thay đổi trường private không?** Xem lại cách khai báo phụ thuộc và API công khai của lớp.
5. **Một test phải mock quá nhiều collaborator không?** Kiểm tra trách nhiệm của lớp và ranh giới giữa nghiệp vụ với hạ tầng.
6. **Test chỉ kiểm tra tương tác nội bộ?** Chuyển trọng tâm sang kết quả, trạng thái hoặc hợp đồng có ý nghĩa với bên gọi.
7. **Lỗi chỉ xuất hiện khi chạy cùng các test khác?** Tìm static state, singleton mutable, dữ liệu dùng chung hoặc cấu hình context bị thay đổi.

Không phải mọi test khó đều chứng minh thiết kế sai. Có những hành vi vốn cần môi trường tích hợp, chẳng hạn transaction thật hoặc tương tác với database engine. Mục tiêu là đặt hành vi vào đúng cấp kiểm thử và làm rõ phần nào được kiểm soát bởi test, phần nào cần xác nhận bằng hạ tầng thật.

## 9. Quy trình áp dụng khi thiết kế một service mới

Khi xây dựng một service Spring có khả năng kiểm thử tốt, có thể đi theo trình tự sau:

1. Viết rõ trách nhiệm và hành vi công khai của service.
2. Liệt kê dữ liệu đầu vào, đầu ra và các khả năng bên ngoài mà hành vi cần dùng.
3. Giữ các quy tắc thuần túy trong Java khi có thể; không đưa chúng vào Spring chỉ để tiện test.
4. Khai báo các phụ thuộc bắt buộc qua constructor. Tạo hợp đồng tại ranh giới lưu trữ, mạng, thời gian hoặc hệ thống bên ngoài khi cần thay thế implementation.
5. Viết unit test bằng cách tự tạo service và cung cấp mock/fake. Kiểm tra cả kết quả bình thường lẫn lỗi quan trọng.
6. Bổ sung Spring context test để xác nhận bean wiring khi việc wiring có rủi ro hoặc là một phần của thay đổi.
7. Bổ sung integration hoặc slice test khi hành vi phụ thuộc vào Spring MVC, JPA, transaction, security hoặc cấu hình hạ tầng.
8. Nếu test cần quá nhiều mock hoặc phải dựng nhiều thành phần không liên quan, xem lại ranh giới trách nhiệm trước khi mở rộng test setup.

Trình tự này giúp phân biệt hai câu hỏi: “logic của lớp có đúng không?” và “ứng dụng có lắp ráp, cấu hình các lớp đúng không?”. Unit test trả lời câu hỏi đầu; Spring context và integration test trả lời câu hỏi thứ hai ở phạm vi tương ứng.

## 10. Nguyên tắc cần ghi nhớ

- DI làm đồ thị phụ thuộc tường minh và cho phép thay thế collaborator trong test.
- Constructor injection thường phù hợp với phụ thuộc bắt buộc vì đối tượng hoàn chỉnh ngay khi được tạo.
- Test đơn vị không cần Spring context nếu lớp có thể được khởi tạo trực tiếp và các phụ thuộc đã được kiểm soát.
- Spring context test kiểm tra việc tạo bean và wiring; nó bổ sung cho unit test.
- @SpringBootTest phù hợp với kiểm tra tích hợp rộng, không phải lựa chọn mặc định cho mọi bài test.
- Chỉ tạo abstraction tại ranh giới có ý nghĩa; không tạo interface cho mọi lớp chỉ để mock.
- Thời gian, random, mạng, cơ sở dữ liệu và trạng thái toàn cục là các nguồn làm test mất tính xác định; hãy quản lý chúng qua phụ thuộc rõ ràng.
- Một constructor quá lớn, service locator hoặc quá nhiều mock có thể là tín hiệu cần xem lại thiết kế.

Thiết kế Dependency Injection tốt giúp Spring lắp ráp ứng dụng rõ ràng và giúp test chủ động kiểm soát môi trường thực thi. Khả năng kiểm thử vì vậy là một hệ quả quan trọng của việc quản lý phụ thuộc đúng cách, đồng thời là công cụ phản hồi để cải thiện ranh giới và trách nhiệm của các thành phần trong ứng dụng.
