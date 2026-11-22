# Phân biệt đối tượng kiểm thử với bean do context quản lý

Trong một bài kiểm thử Spring, có hai nhóm đối tượng thường xuất hiện cùng lúc: đối tượng kiểm thử (test instance) do framework kiểm thử tạo ra và các bean do Spring ApplicationContext quản lý. Test instance là nơi chứa test method, fixture, mock và các trường hỗ trợ kiểm tra. Bean là những đối tượng thuộc đồ thị ứng dụng mà Spring tạo, cấu hình, inject và quản lý vòng đời theo scope.

Spring có thể inject bean vào test instance, nhưng việc được inject không biến test instance thành một bean của ApplicationContext. Đây là điểm quan trọng để hiểu đúng phạm vi của @Autowired, @Mock, @Bean, @Configuration và các annotation thay thế bean. Nếu nhầm hai loại đối tượng, test có thể tạo mock nhưng service vẫn dùng bean thật, hoặc vô tình chia sẻ trạng thái giữa nhiều test.

## 1. Hai cơ chế tạo và quản lý đối tượng

Một test class thường do JUnit Jupiter tạo theo vòng đời test đã cấu hình. JUnit gọi các test method và các callback như @BeforeEach, @AfterEach. Spring tham gia thông qua SpringExtension và TestContext Framework để chuẩn bị ApplicationContext, inject phụ thuộc vào test instance và cung cấp các tính năng như transaction test-managed.

Trong khi đó, ApplicationContext là container của Spring. Nó tạo các bean từ component scan, các phương thức @Bean, cấu hình XML hoặc những cơ chế đăng ký bean khác. Container giải quyết phụ thuộc giữa bean và quản lý vòng đời của chúng theo scope.

| Đặc điểm | Test instance | Bean do ApplicationContext quản lý |
|---|---|---|
| Ai tạo? | JUnit hoặc test framework tương ứng | Spring container |
| Mục đích | Chứa test method, fixture và assertion | Thực hiện chức năng của ứng dụng hoặc hạ tầng |
| Cách nhận phụ thuộc | Spring có thể inject vào test instance; JUnit/Spring có thể cung cấp tham số cho constructor hoặc method | Spring giải quyết phụ thuộc khi tạo bean |
| Vòng đời | Theo test lifecycle của JUnit và cấu hình @TestInstance | Theo bean scope và vòng đời ApplicationContext |
| Có nằm trong bean registry? | Không chỉ vì test instance dùng Spring Extension hoặc có @Autowired | Có, sau khi được đăng ký trong context |
| Có thể được chia sẻ? | Phụ thuộc lifecycle của JUnit, thường là một instance cho mỗi method | Có thể được chia sẻ giữa nhiều test khi context được cache và bean là singleton |

Ví dụ, một test class có thể được Spring inject InventoryService:

~~~java
@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryServiceTest {
    @Autowired
    private InventoryService inventoryService;

    @Test
    void findsAnInventoryItem() {
        // inventoryService là bean do Spring quản lý.
    }
}
~~~

JUnit tạo đối tượng InventoryServiceTest để gọi test method. Spring tìm bean InventoryService trong context rồi gán vào trường inventoryService của đối tượng test. Test class vẫn là test instance của JUnit; InventoryService mới là bean trong context.

## 2. Test instance được Spring inject nhưng không trở thành bean

TestContext Framework có listener tên DependencyInjectionTestExecutionListener. Listener này chuẩn bị test instance bằng cách yêu cầu Spring autowire các phụ thuộc đã khai báo trên test class. Vì thế, các trường hoặc phương thức có @Autowired trong test class có thể nhận bean từ ApplicationContext.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryServiceTest {
    @Autowired
    private InventoryService inventoryService;

    @Autowired
    private InventoryRepository inventoryRepository;

    @Test
    void loadsAnItem() {
        InventoryItem item = inventoryService.find("SKU-01");

        assertEquals("SKU-01", item.sku());
    }
}
~~~

Spring inject hai bean vào test instance. Điều đó không có nghĩa Spring đã đăng ký InventoryServiceTest thành bean, cũng không có nghĩa test class sẽ được component scan như một service thông thường.

Spring TestContext dùng ApplicationContext để giải quyết các bean cần inject, nhưng đối tượng test vẫn được framework kiểm thử tạo. Spring chỉ thực hiện công việc autowire trên đối tượng đã có. Đây là lý do một test class có thể dùng @Autowired mà không cần đặt @Component hoặc @Service lên chính test class.

### Constructor injection cho test class

Với JUnit Jupiter, SpringExtension còn hỗ trợ cung cấp tham số constructor hoặc test method từ context. Có thể dùng @TestConstructor để yêu cầu autowire tất cả tham số constructor:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.TestConstructor;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(InventoryTestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class InventoryServiceConstructorTest {
    private final InventoryService inventoryService;

    InventoryServiceConstructorTest(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @Test
    void findsAnItem() {
        InventoryItem item = inventoryService.find("SKU-01");

        assertEquals("SKU-01", item.sku());
    }
}
~~~

Constructor injection giúp fixture bắt buộc được khai báo ngay khi tạo test instance. Tuy nhiên, test class vẫn không trở thành bean. Spring tham gia phân giải tham số constructor thông qua tích hợp với JUnit; JUnit vẫn quản lý việc tạo và gọi test instance.

Spring cũng có thể phân giải tham số của test method:

~~~java
@Test
void receivesAServiceAsParameter(InventoryService inventoryService) {
    assertNotNull(inventoryService);
}
~~~

Khả năng này đến từ parameter resolver của SpringExtension. Không nên nhầm việc một tham số được lấy từ context với việc method hoặc test class là một bean.

## 3. Bean được tạo và quản lý trong ApplicationContext

Bean là một đối tượng mà Spring container biết đến và quản lý. Bean có thể được đăng ký bằng component scan, bằng phương thức @Bean trong lớp @Configuration, hoặc bằng các cơ chế cấu hình khác.

Ví dụ, lớp nghiệp vụ và repository có thể được định nghĩa như sau:

~~~java
public record InventoryItem(String sku, int available) {
}

public interface InventoryRepository {
    InventoryItem findBySku(String sku);
}

public class InventoryService {
    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    public InventoryItem find(String sku) {
        return repository.findBySku(sku);
    }
}
~~~

Một cấu hình Spring đăng ký các bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InventoryConfiguration {
    @Bean
    InventoryRepository inventoryRepository() {
        return new JdbcInventoryRepository();
    }

    @Bean
    InventoryService inventoryService(
            InventoryRepository inventoryRepository) {
        return new InventoryService(inventoryRepository);
    }
}
~~~

Khi ApplicationContext được tạo, Spring gọi các phương thức @Bean theo nhu cầu để đăng ký và tạo bean. Phương thức inventoryService nhận tham số inventoryRepository; Spring tự phân giải bean phù hợp rồi truyền vào constructor. Cả InventoryRepository implementation và InventoryService đều thuộc context.

Trong test, ta có thể dùng cấu hình test riêng thay cho cấu hình production:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InventoryTestConfig {
    @Bean
    InMemoryInventoryRepository inventoryRepository() {
        return new InMemoryInventoryRepository();
    }

    @Bean
    InventoryService inventoryService(
            InventoryRepository inventoryRepository) {
        return new InventoryService(inventoryRepository);
    }
}

class InMemoryInventoryRepository implements InventoryRepository {
    private final Map<String, InventoryItem> items =
            new ConcurrentHashMap<>();

    InMemoryInventoryRepository() {
        items.put("SKU-01", new InventoryItem("SKU-01", 8));
    }

    @Override
    public InventoryItem findBySku(String sku) {
        return items.get(sku);
    }
}
~~~

InventoryTestConfig là cấu hình dùng cho test. Phương thức @Bean tạo InMemoryInventoryRepository và InventoryService. Các đối tượng được trả về từ phương thức @Bean được Spring đăng ký trong context; bản thân lớp test sử dụng context vẫn là test instance riêng.

Trong dự án Spring Boot, @TestConfiguration thường được dùng để bổ sung bean chỉ phục vụ test. Lớp cấu hình này có thể là static nested class trong test hoặc được import rõ ràng. Với Spring Framework thuần, @Configuration kết hợp @ContextConfiguration hoặc @SpringJUnitConfig cũng đủ để khai báo context kiểm thử.

## 4. Phân biệt @Autowired trên test với @Autowired trên bean

Annotation @Autowired có thể xuất hiện trên cả test class và bean ứng dụng, nhưng đối tượng nhận injection khác nhau.

~~~java
@Service
public class CheckoutService {
    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
~~~

Trong trường hợp này, Spring inject PaymentGateway khi tạo bean CheckoutService. Đây là một phần của quá trình xây dựng đồ thị bean.

~~~java
@SpringJUnitConfig(CheckoutTestConfig.class)
class CheckoutServiceTest {
    @Autowired
    private CheckoutService checkoutService;
}
~~~

Trong trường hợp này, Spring inject bean CheckoutService vào trường của test instance. Test class không được thêm vào bean registry chỉ bởi annotation @Autowired.

Có thể nhìn vào mục tiêu của injection:

- Trên constructor của bean: xác định các phụ thuộc bắt buộc để Spring tạo bean.
- Trên trường hoặc phương thức của bean: yêu cầu Spring inject sau hoặc trong quá trình tạo bean.
- Trên test instance: yêu cầu TestContext chuẩn bị fixture bằng các bean từ context.
- Trên tham số test method hoặc constructor test: yêu cầu SpringExtension phân giải tham số từ context.

Constructor injection thường là cách tốt để khai báo phụ thuộc bắt buộc của bean. Trên test class, field injection vẫn phổ biến vì test framework tạo test instance trước rồi Spring có thể chuẩn bị nó; constructor injection cũng khả dụng khi được cấu hình đúng.

## 5. @Mock không tự thay thế bean trong context

Một nhầm lẫn phổ biến là khai báo @Mock trong test class rồi mong bean ứng dụng tự động sử dụng mock đó. Annotation @Mock của Mockito chỉ tạo một đối tượng mock trong fixture của test. Nó không đăng ký mock thành bean và không thay thế phụ thuộc đã được inject vào một bean khác.

Xét ví dụ sau:

~~~java
@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryServiceTest {
    @Mock
    private InventoryRepository inventoryRepository;

    @Autowired
    private InventoryService inventoryService;

    @Test
    void findsAnItem() {
        // inventoryService vẫn giữ repository mà Spring đã inject.
    }
}
~~~

Ở đây, @Mock tạo InventoryRepository mock trong test instance. Nhưng InventoryService được tạo trong ApplicationContext từ cấu hình test và đã nhận repository bean do Spring giải quyết. Mock trong trường inventoryRepository không tự thay đổi tham chiếu bên trong InventoryService. Nếu test stub trường mock rồi gọi inventoryService, service có thể vẫn đi tới repository bean khác.

Nếu muốn unit test cô lập service, hãy tự tạo service bằng constructor:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class InventoryServiceUnitTest {
    @Mock
    private InventoryRepository repository;

    private InventoryService service;

    @BeforeEach
    void setUp() {
        service = new InventoryService(repository);
    }

    @Test
    void returnsTheItemFromTheRepository() {
        InventoryItem expected = new InventoryItem("SKU-01", 8);
        when(repository.findBySku("SKU-01")).thenReturn(expected);

        InventoryItem actual = service.find("SKU-01");

        assertEquals(expected, actual);
    }
}
~~~

Test này không cần ApplicationContext. MockitoExtension tạo mock, còn test tự tạo InventoryService và truyền mock vào constructor. Service chắc chắn sử dụng đúng đối tượng đã được stub.

## 6. Thay thế bean trong context bằng @MockitoBean

Nếu mục tiêu là kiểm tra service trong một Spring context nhưng thay repository bean bằng mock, cần dùng cơ chế bean override. Từ Spring Framework 6.2, @MockitoBean có thể đăng ký mock thay cho bean phù hợp trong ApplicationContext.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryServiceContextTest {
    @MockitoBean
    private InventoryRepository inventoryRepository;

    @Autowired
    private InventoryService inventoryService;

    @Test
    void usesTheMockBeanInjectedIntoTheService() {
        InventoryItem expected = new InventoryItem("SKU-01", 8);
        when(inventoryRepository.findBySku("SKU-01"))
                .thenReturn(expected);

        InventoryItem actual = inventoryService.find("SKU-01");

        assertEquals(expected, actual);
    }
}
~~~

Trong ví dụ này, @MockitoBean yêu cầu Spring TestContext thay bean InventoryRepository trong context bằng Mockito mock. InventoryService được Spring tạo và nhận chính mock bean đó. Vì thế, khi test stub trường inventoryRepository rồi gọi inventoryService, service dùng kết quả đã cấu hình.

@MockitoBean thuộc package org.springframework.test.context.bean.override.mockito và cần Spring Framework 6.2 trở lên. Với phiên bản cũ hơn, dự án có thể dùng cơ chế mock bean do phiên bản Spring Boot cung cấp hoặc cấu hình một test bean thay thế. Cần đối chiếu phiên bản dependency thực tế trước khi chọn annotation.

Các annotation bean override khác có thể gồm:

- @MockitoSpyBean: tạo spy từ bean hiện có trong context để giữ phần lớn hành vi thật và cho phép theo dõi hoặc stub có chọn lọc.
- @TestBean: thay thế hoặc cung cấp bean bằng một factory method trong test, phù hợp khi cần fake hoặc implementation test cụ thể.
- @MockitoBean: tạo mock và đưa nó vào context theo kiểu bean override.

Những annotation này tác động đến bean graph của context. Chúng khác với @Mock và @Spy của Mockito, vốn chỉ tạo đối tượng trong fixture của test.

## 7. Phân biệt các annotation thường gặp

| Annotation | Thuộc cơ chế nào? | Tạo hoặc tác động đến đâu? |
|---|---|---|
| @Autowired | Spring Core / TestContext | Inject bean vào bean ứng dụng hoặc test instance |
| @Component, @Service, @Repository | Spring component scanning | Đăng ký lớp ứng dụng thành bean |
| @Configuration | Spring configuration | Khai báo cấu hình tạo bean |
| @Bean | Spring configuration | Đăng ký đối tượng trả về từ phương thức thành bean |
| @TestConfiguration | Spring Boot Test | Bổ sung cấu hình và bean chỉ dùng cho test |
| @Mock | Mockito | Tạo mock trong test fixture |
| @Spy | Mockito | Tạo spy trong test fixture từ đối tượng thật |
| @MockitoBean | Spring TestContext 6.2+ | Override hoặc cung cấp mock bean trong ApplicationContext |
| @MockitoSpyBean | Spring TestContext 6.2+ | Override bean bằng spy trong ApplicationContext |
| @TestBean | Spring TestContext 6.2+ | Override hoặc cung cấp bean bằng factory method của test |

Tên annotation gần nhau không có nghĩa chúng có cùng phạm vi. Hãy xác định câu hỏi trước khi chọn:

- Cần một mock để truyền vào service được tạo thủ công? Dùng @Mock hoặc Mockito.mock().
- Cần một bean mock thay cho repository trong context? Dùng @MockitoBean nếu phiên bản hỗ trợ.
- Cần giữ bean thật nhưng theo dõi hoặc stub một phần hành vi? Cân nhắc @Spy hoặc @MockitoSpyBean theo phạm vi fixture hay context.
- Cần một implementation giả hoạt động được như repository trong bộ nhớ? Tạo fake và đăng ký bằng @Bean trong cấu hình test.

## 8. Vòng đời test instance khác vòng đời ApplicationContext

Một khác biệt quan trọng khác nằm ở thời gian sống của đối tượng. Với JUnit Jupiter, lifecycle mặc định là PER_METHOD: JUnit tạo một test instance mới cho mỗi test method. Có thể thay đổi thành PER_CLASS bằng @TestInstance(TestInstance.Lifecycle.PER_CLASS), khi đó một test instance được dùng chung cho các method của class.

ApplicationContext thường được Spring TestContext cache và tái sử dụng giữa các test có cấu hình tương đương. Vì thế, một test class mới có thể nhận lại cùng singleton bean từ context cache, trong khi test instance của nó là đối tượng mới.

Sơ đồ khái quát:

~~~text
JUnit tạo TestInstance A
        |
        v
Spring inject bean từ ApplicationContext X
        |
        v
Chạy test method 1
        |
        v
Kết thúc test method 1
        |
        v
JUnit tạo TestInstance B (PER_METHOD)
        |
        v
Spring inject lại bean từ ApplicationContext X
        |
        v
Chạy test method 2
~~~

Trong sơ đồ, TestInstance A và B khác nhau nhưng ApplicationContext X có thể được dùng lại. Bean singleton trong context X cũng có thể là cùng một đối tượng giữa hai test. Vì vậy, không nên để trạng thái mutable của singleton bean làm test phụ thuộc vào thứ tự chạy.

### Test fixture và bean singleton

Test fixture thường gồm dữ liệu đầu vào, mock, expected result và biến hỗ trợ cho một test. Fixture nên có phạm vi phù hợp với test method và được khởi tạo hoặc reset rõ ràng.

Bean singleton mặc định có một instance cho mỗi bean definition trong một ApplicationContext. Khi context được cache, singleton bean có thể tồn tại qua nhiều test class. Nếu bean giữ danh sách, bộ đếm hoặc trạng thái thay đổi, test cần đảm bảo trạng thái đó được reset hoặc cô lập.

Không nên nhầm việc @Autowired một singleton bean vào trường test với việc trường đó trở thành singleton. Trường trong test instance thuộc vòng đời test; đối tượng mà trường tham chiếu có thể là singleton bean do context quản lý.

### Khi nào cần @DirtiesContext?

@DirtiesContext đánh dấu ApplicationContext không còn phù hợp để tái sử dụng, khiến Spring loại context khỏi cache và tạo lại khi cần. Nó hữu ích khi test làm thay đổi cấu trúc hoặc trạng thái nội bộ của context theo cách không thể dọn bằng fixture thông thường.

Không nên dùng @DirtiesContext như cơ chế mặc định để reset mọi dữ liệu. Nếu chỉ cần xóa bản ghi database, transaction rollback, SQL cleanup hoặc phương thức reset của fake thường phù hợp hơn. Tạo lại toàn bộ context có thể làm test suite chậm đáng kể.

## 9. TestConfiguration, @Import và component scan

Test có thể dựng context từ nhiều nguồn cấu hình. @ContextConfiguration cho phép chỉ định lớp cấu hình hoặc resource cần tải. @SpringJUnitConfig là annotation kết hợp SpringExtension và @ContextConfiguration cho JUnit Jupiter.

Ví dụ dùng cấu hình tường minh:

~~~java
@SpringJUnitConfig({
        InventoryConfiguration.class,
        InventoryAdditionalTestConfig.class
})
class InventoryIntegrationTest {
    @Autowired
    private InventoryService inventoryService;
}
~~~

Các lớp cấu hình được chỉ định sẽ đóng góp bean vào cùng context. Nếu dùng @Import, một cấu hình có thể import cấu hình khác hoặc lớp bean cụ thể.

Trong Spring Boot, @SpringBootTest thường tải cấu hình ứng dụng chính và khởi tạo context rộng hơn. Test instance vẫn do JUnit tạo và được Spring inject. @TestConfiguration có thể bổ sung bean chỉ dùng cho test mà không biến test class thành bean.

Không nên đưa test class vào component scan chỉ để nhận @Autowired. Hãy khai báo cấu hình test và để TestContext quản lý việc inject fixture. Component scan dành cho các lớp ứng dụng muốn đăng ký thành bean.

## 10. Các lỗi dễ gặp khi nhầm hai loại đối tượng

### Tạo @Mock nhưng service vẫn gọi database thật

Nguyên nhân thường là mock chỉ nằm trên trường test instance, còn service đã được tạo trong context với repository bean khác. Nếu muốn unit test, tự tạo service bằng constructor. Nếu muốn giữ context, dùng cơ chế bean override như @MockitoBean hoặc một fake bean trong cấu hình test.

### Đặt @Component lên test class để mong Spring quản lý nó

Test framework đã tạo test instance và Spring TestContext có cơ chế inject riêng. Đăng ký test class thành component thường không cần thiết và có thể làm rối component scan hoặc cấu hình context. Hãy giữ test class là fixture và chỉ đăng ký các lớp ứng dụng cần kiểm tra.

### Thay đổi trạng thái singleton bean trong test

Test có thể làm thay đổi trạng thái của bean và khiến test sau thất bại. Hãy thiết kế bean không giữ trạng thái mutable không cần thiết, reset dữ liệu giữa các test hoặc dùng context mới khi thật sự cần.

### Dùng @DirtiesContext để sửa mọi lỗi dữ liệu

Context mới không phải cách dọn dữ liệu database tối ưu. Hãy xác định dữ liệu nằm trong bean, transaction hay database rồi dùng cơ chế cleanup đúng phạm vi.

### Giả định @Autowired test field đồng nghĩa với test object là bean

@Autowired chỉ mô tả yêu cầu inject. Nó không quyết định ai tạo test instance và không đăng ký test class vào ApplicationContext.

### Nhầm @TestConfiguration với test instance

@TestConfiguration là lớp cấu hình đóng góp bean vào context. Test class sử dụng cấu hình vẫn là đối tượng riêng do JUnit quản lý. Một phương thức @Bean trong cấu hình có thể trả về bean dùng trong test, nhưng chính test instance không được tạo ra bởi phương thức đó.

## 11. Quy trình chọn cách tạo đối tượng trong test

Khi viết test Spring, hãy xác định phạm vi cần kiểm tra trước:

1. Nếu cần kiểm tra logic của một lớp Java, tạo đối tượng bằng constructor và truyền dependency thật đơn giản, fake hoặc Mockito mock. Không cần tạo ApplicationContext.
2. Nếu cần kiểm tra Spring wiring hoặc bean lifecycle, dùng @SpringJUnitConfig hoặc @ContextConfiguration để tạo context giới hạn.
3. Nếu cần kiểm tra cấu hình toàn ứng dụng Spring Boot, dùng @SpringBootTest khi lợi ích của context đầy đủ là cần thiết.
4. Nếu muốn service trong context dùng mock của một dependency, dùng @MockitoBean ở phiên bản Spring Framework hỗ trợ hoặc cấu hình fake bean thay thế.
5. Nếu muốn test fixture nhận bean từ context, dùng @Autowired hoặc constructor/method parameter injection qua SpringExtension.
6. Nếu test thay đổi trạng thái singleton bean hoặc context, xác định cách reset phù hợp; chỉ dùng @DirtiesContext khi cần loại bỏ context.
7. Giữ dữ liệu fixture của từng test tách biệt và tránh để trạng thái dùng chung làm kết quả phụ thuộc thứ tự chạy.

Việc phân biệt rõ test instance và bean giúp chọn đúng cơ chế cho từng nhu cầu. Test instance là nơi JUnit chạy kiểm tra và Spring có thể inject fixture; bean là thành phần Spring quản lý trong ApplicationContext. @Mock tác động đến fixture, còn @MockitoBean và @Bean tác động đến bean graph. Khi hiểu đúng ranh giới đó, test sẽ kiểm soát được phụ thuộc, vòng đời và trạng thái của các đối tượng mà nó đang kiểm tra.
