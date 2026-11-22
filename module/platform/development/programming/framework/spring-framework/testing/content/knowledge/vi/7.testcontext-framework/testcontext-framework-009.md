# Phân biệt vòng đời kiểm thử với vòng đời ApplicationContext

Khi viết test Spring, có hai vòng đời diễn ra đồng thời nhưng phục vụ hai mục đích khác nhau. Vòng đời kiểm thử quản lý một test class, một test method và các callback như setup, execution, teardown. Vòng đời `ApplicationContext` quản lý vùng chứa Spring: nạp cấu hình, tạo bean, duy trì singleton, tái sử dụng context và đóng context khi cần.

Hai vòng đời này có liên hệ nhưng không đồng nhất. JUnit có thể tạo một test instance mới cho mỗi method trong khi Spring vẫn dùng lại cùng một `ApplicationContext` đã được cache. Vì thế, field của test class có thể được làm mới, còn trạng thái trong một singleton bean vẫn tồn tại giữa nhiều test. Hiểu sự khác biệt này giúp tránh lỗi phụ thuộc thứ tự, rò rỉ trạng thái và khởi động context không cần thiết.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả vòng đời của test class và test method trong JUnit Jupiter.
- Giải thích Spring TestContext tham gia vào các giai đoạn kiểm thử như thế nào.
- Phân biệt test instance, test execution và `ApplicationContext`.
- Giải thích vì sao nhiều test method có thể dùng chung một context.
- Hiểu cache của Spring TestContext và các yếu tố ảnh hưởng tới việc tái sử dụng context.
- Sử dụng `@DirtiesContext` đúng mục đích và đúng phạm vi.
- Nhận biết trạng thái nào được reset sau mỗi test và trạng thái nào có thể còn lại.
- Phân biệt vòng đời context với transaction và vòng đời của tài nguyên bên ngoài.

## 1. Hai vòng đời cùng xuất hiện trong một bài kiểm thử

JUnit quản lý việc chạy test. Spring TestContext bổ sung khả năng chuẩn bị test instance, cung cấp dependency và quản lý context. Bản thân `ApplicationContext` lại có vòng đời riêng, bắt đầu từ lúc được tải và refresh, tiếp tục trong thời gian được tái sử dụng, rồi kết thúc khi bị đóng.

Có thể hình dung quan hệ tổng quát:

~~~mermaid
flowchart TD
    A["JUnit bắt đầu test class"] --> B["Spring chuẩn bị TestContext"]
    B --> C["Tải hoặc lấy ApplicationContext từ cache"]
    C --> D["Tạo và inject test instance"]
    D --> E["Chạy callback trước test"]
    E --> F["Chạy test method"]
    F --> G["Chạy callback sau test"]
    G --> H["JUnit tiếp tục method kế tiếp"]
    H -->|Cùng cấu hình context| C
    H -->|Cấu hình khác| I["Tải ApplicationContext khác"]
    C --> J["Context được tái sử dụng"]
    J --> K["Đóng khi bị loại khỏi cache hoặc JVM kết thúc"]
~~~

Vòng đời test thường lặp lại nhiều lần trên một context đã tồn tại. Spring không mặc định tạo mới toàn bộ container cho mỗi method. Cơ chế cache giúp giảm thời gian chạy suite, đặc biệt khi context chứa nhiều bean, auto-configuration, datasource hoặc embedded server.

Điều quan trọng là phân biệt ba khái niệm:

| Khái niệm | Được quản lý bởi | Ý nghĩa |
|---|---|---|
| Test class | JUnit Jupiter | Nhóm các test method và callback cấp class |
| Test instance | JUnit, được Spring chuẩn bị | Đối tượng Java chứa field và method của test |
| ApplicationContext | Spring Framework | Container chứa bean, environment và tài nguyên Spring |

Một test instance là một Java object. `ApplicationContext` là một container có thể chứa hàng trăm bean. Chúng có thể có thời điểm tạo và thời điểm hủy rất khác nhau.

## 2. Vòng đời test trong JUnit Jupiter

JUnit Jupiter cung cấp các annotation và callback để kiểm soát việc chạy test. Với test class thông thường, vòng đời mặc định của test instance là `PER_METHOD`: JUnit tạo một instance mới cho mỗi test method.

Ví dụ:

~~~java
class LifecycleTest {

    private int counter;

    @BeforeAll
    static void beforeAll() {
        System.out.println("Before all tests");
    }

    @BeforeEach
    void beforeEach() {
        counter = 0;
        System.out.println("Before each test");
    }

    @Test
    void firstTest() {
        counter++;
        assertEquals(1, counter);
    }

    @Test
    void secondTest() {
        counter++;
        assertEquals(1, counter);
    }

    @AfterEach
    void afterEach() {
        System.out.println("After each test");
    }

    @AfterAll
    static void afterAll() {
        System.out.println("After all tests");
    }
}
~~~

Với vòng đời mặc định, mỗi method chạy trên một instance riêng. Vì vậy, field `counter` không mang giá trị từ test thứ nhất sang test thứ hai. `@BeforeEach` vẫn có thể dùng để chuẩn bị dữ liệu cho từng method, còn `@AfterEach` thực hiện dọn dẹp tương ứng.

Các giai đoạn thường gặp:

| Callback hoặc annotation | Phạm vi | Thời điểm |
|---|---|---|
| `@BeforeAll` | Một lần cho test class | Trước các test method |
| `@BeforeEach` | Mỗi test method | Trước phần thân test |
| `@Test` | Một method | Thực hiện hành vi đang kiểm tra |
| `@AfterEach` | Mỗi test method | Sau phần thân test |
| `@AfterAll` | Một lần cho test class | Sau các test method |

Theo mặc định, `@BeforeAll` và `@AfterAll` thường là static. Nếu dùng `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, JUnit sử dụng một test instance cho cả class và cho phép các callback này là instance method.

Ví dụ:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class SharedTestInstanceTest {

    private int counter;

    @BeforeAll
    void initializeOnce() {
        counter = 10;
    }

    @Test
    void firstTest() {
        counter++;
        assertEquals(11, counter);
    }

    @Test
    void anotherTest() {
        // Giá trị counter phụ thuộc vào thứ tự nếu test cùng sửa field.
    }
}
~~~

Với `PER_CLASS`, các test method dùng chung field của test instance. Nếu nhiều test cùng sửa một field mutable, kết quả có thể phụ thuộc thứ tự chạy. Chỉ dùng vòng đời này khi việc chia sẻ test instance là có chủ đích và test được thiết kế an toàn với trạng thái dùng chung.

JUnit có thể chạy test theo thứ tự hoặc song song tùy cấu hình. Không nên dựa vào thứ tự ngầm định để chuẩn bị dữ liệu cho test khác. Mỗi test nên tự thiết lập điều kiện cần thiết và có thể chạy độc lập.

## 3. Spring TestContext tham gia vào vòng đời test như thế nào?

Spring TestContext Framework tích hợp Spring với các framework kiểm thử như JUnit Jupiter. Nó cung cấp một mô hình chung để nạp context, inject dependency vào test instance, quản lý transaction kiểm thử và gọi các listener ở những thời điểm thích hợp.

Với JUnit Jupiter, `SpringExtension` là cầu nối giữa JUnit và Spring TestContext. Có thể đăng ký extension trực tiếp:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfiguration.class)
class SpringContextTest {
    // Test methods
}
~~~

Hoặc dùng annotation kết hợp:

~~~java
@SpringJUnitConfig(TestConfiguration.class)
class SpringContextTest {
    // Test methods
}
~~~

Các annotation Spring Boot như `@SpringBootTest` cũng tích hợp cơ chế Spring TestContext và extension tương ứng.

Ở mức khái niệm, quá trình diễn ra như sau:

1. JUnit bắt đầu xử lý test class và các extension đã đăng ký.
2. Spring TestContext tạo hoặc lấy metadata cần thiết cho test class.
3. Khi cần context, Spring tải cấu hình và lấy `ApplicationContext` từ cache nếu có context phù hợp.
4. Spring chuẩn bị test instance và thực hiện dependency injection theo cấu hình kiểm thử.
5. Các callback của Spring TestContext được gọi quanh từng method và quanh test class.
6. JUnit thực thi phần thân test cùng các callback JUnit.
7. Spring thực hiện callback sau test, bao gồm các listener liên quan đến transaction và SQL nếu được kích hoạt.

`SpringExtension` kết nối các callback của JUnit Jupiter với `TestContextManager`. TestContextManager điều phối các giai đoạn như chuẩn bị test instance, trước và sau test method, trước và sau phần thực thi test, cũng như trước và sau test class.

Spring TestContext không thay thế JUnit. JUnit vẫn quyết định cách phát hiện và thực thi test; Spring bổ sung context và các dịch vụ kiểm thử cần thiết.

## 4. ApplicationContext có vòng đời riêng

`ApplicationContext` là container cấp cao của Spring. Khi một context được tải, Spring đọc cấu hình, đăng ký bean definition, thực hiện refresh và tạo các singleton eager cần thiết. Trong quá trình đó, bean factory và các post-processor tham gia vào việc tạo, inject và khởi tạo bean.

Một vòng đời khái quát của context:

~~~mermaid
flowchart TD
    A["Đọc cấu hình và resource"] --> B["Đăng ký BeanDefinition"]
    B --> C["Refresh ApplicationContext"]
    C --> D["Tạo và inject bean"]
    D --> E["Khởi tạo bean và callback"]
    E --> F["Context sẵn sàng"]
    F --> G["Nhiều test có thể sử dụng context"]
    G --> H{"Context bị loại khỏi cache?"}
    H -->|Có| I["Đóng context"]
    H -->|Không| G
    I --> J["Hủy bean và giải phóng resource"]
~~~

Các bước quan trọng:

- **Đọc cấu hình:** Spring nhận cấu hình từ class, XML, component scan, auto-configuration và các nguồn được chỉ định.
- **Đăng ký bean definition:** container biết loại bean, scope, dependency và cách tạo chúng.
- **Refresh:** context hoàn tất quá trình thiết lập container và chuyển sang trạng thái sẵn sàng.
- **Tạo bean:** Spring tạo các singleton cần khởi tạo sớm, giải quyết dependency và áp dụng các post-processor.
- **Khởi tạo:** các callback như `@PostConstruct`, `InitializingBean` hoặc custom init method có thể được gọi.
- **Sử dụng:** test và các thành phần trong context có thể truy cập bean.
- **Đóng:** khi context thực sự được đóng, Spring gọi các callback hủy bean và giải phóng tài nguyên mà container quản lý.

Một context không tự đóng sau mỗi test method. Trong Spring TestContext, context thường được giữ trong cache để các test tương thích có thể dùng lại.

## 5. Một context có thể phục vụ nhiều test instance

Đây là điểm quan trọng nhất khi phân biệt hai vòng đời.

Ví dụ hai test class cùng dùng một cấu hình:

~~~java
@SpringBootTest
class OrderServiceTest {

    @Autowired
    OrderService orderService;

    @Test
    void createsOrder() {
        // Kiểm tra nghiệp vụ
    }
}
~~~

~~~java
@SpringBootTest
class OrderControllerTest {

    @Autowired
    OrderService orderService;

    @Test
    void handlesOrderRequest() {
        // Kiểm tra HTTP hoặc controller
    }
}
~~~

Nếu cấu hình context của hai class tương thích và tạo cùng cache key, Spring có thể dùng lại một `ApplicationContext`. JUnit vẫn tạo test instance theo lifecycle của từng class. Mỗi test method mặc định có instance riêng, nhưng field `orderService` được inject từ cùng một singleton bean trong context được tái sử dụng.

Có thể hình dung:

~~~mermaid
flowchart TB
    C["Một ApplicationContext được cache"]
    B["Singleton OrderService"]
    C --> B
    T1["Test instance: method A"] -->|Autowired| B
    T2["Test instance: method B"] -->|Autowired| B
    T3["Test instance ở class khác"] -->|Autowired| B
~~~

Điều đó có nghĩa:

- Field thông thường trong test class có thể được khởi tạo lại cho mỗi method.
- Singleton bean trong context có thể vẫn là cùng một instance.
- Trạng thái mutable nằm trong singleton bean có thể tồn tại qua nhiều test.
- Cache context giúp tránh chi phí nạp và khởi tạo lại toàn bộ ứng dụng.
- Việc tạo test instance mới không đồng nghĩa tạo một container Spring mới.

Một test có thể xanh khi chạy riêng nhưng thất bại trong suite nếu nó dựa vào trạng thái bean đã bị test khác thay đổi. Ngược lại, test chạy sau có thể vô tình dựa vào dữ liệu hoặc trạng thái do test trước để lại.

Vì vậy, không nên lưu trạng thái nghiệp vụ của từng test vào singleton bean dùng chung. Hãy reset dữ liệu qua API hoặc fixture phù hợp, dùng bean scope phù hợp với mục đích, hoặc tạo context mới khi test thật sự làm thay đổi cấu hình hay trạng thái container không thể khôi phục.

## 6. Spring TestContext cache context như thế nào?

Spring TestContext duy trì một cache cho các `ApplicationContext` đã tải. Khi một test cần context, framework tính toán cấu hình kiểm thử và tìm context phù hợp trong cache. Nếu có, nó tái sử dụng context; nếu không, nó tải context mới rồi đưa vào cache.

Việc cache dựa trên cấu hình context, không đơn giản dựa trên tên test class. Một số yếu tố quan trọng tham gia xác định cache key gồm:

- Các vị trí cấu hình hoặc class cấu hình.
- Các context initializer.
- Context loader và context hierarchy.
- Active profiles.
- Property source được khai báo cho test.
- Các context customizer, chẳng hạn cấu hình mock bean hoặc dynamic property.
- Resource base path đối với web context.

Do đó, hai test class có cùng annotation bề ngoài chưa chắc dùng chung context nếu các property, profile, customizer hoặc cấu hình khác nhau.

Ví dụ, hai class cùng dùng `@SpringBootTest` nhưng có active profile khác nhau:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class TestProfileContextTest {
}
~~~

~~~java
@SpringBootTest
@ActiveProfiles("integration")
class IntegrationProfileContextTest {
}
~~~

Hai cấu hình profile khác nhau tạo ra context khác nhau vì bean, property và điều kiện cấu hình có thể khác.

Tương tự, `@TestPropertySource` hoặc cấu hình dynamic property khác nhau có thể làm cache key thay đổi. Việc dùng nhiều tổ hợp cấu hình riêng biệt khiến suite phải tải nhiều context và có thể làm thời gian chạy tăng đáng kể.

### Cache có giới hạn

Context cache có giới hạn kích thước và sử dụng chính sách loại bỏ các context ít được dùng gần đây khi cần chỗ. Khi một context bị loại khỏi cache, Spring đóng context đó để giải phóng bean và tài nguyên được quản lý.

Cache tồn tại trong phạm vi JVM của tiến trình test. Nếu build tool chia test thành nhiều fork JVM, mỗi fork có cache riêng. Một context được tải ở fork này không tự động được tái sử dụng ở fork khác.

Điều này giải thích vì sao cùng một suite có thể thấy context khởi động lại khi test được chia qua nhiều tiến trình hoặc khi cache bị loại bỏ.

### Quan sát cache

Có thể bật log DEBUG cho package cache của Spring TestContext để xem context được lấy từ cache, tải mới hoặc bị loại bỏ. Ví dụ cấu hình logging trong test:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Log cache giúp phân biệt hai tình huống:

- Test method chạy lại trên context đã có.
- Một cấu hình mới khiến Spring phải tải context khác.


## 7. @DirtiesContext tác động tới vòng đời context

`@DirtiesContext` báo cho Spring TestContext biết rằng context đã bị thay đổi theo cách cần loại khỏi cache. Khi context bị đánh dấu dirty, framework loại context tương ứng khỏi cache và đóng nó. Test sau cần cùng cấu hình sẽ phải tải context mới.

Ví dụ:

~~~java
@SpringBootTest
@DirtiesContext
class ChangesApplicationContextTest {

    @Test
    void changesContextManagedState() {
        // Thực hiện thay đổi khiến context không thể tái sử dụng.
    }
}
~~~

Có thể đặt annotation ở cấp class hoặc method, tùy phạm vi thay đổi. Các mode thường dùng cho phép đánh dấu trước hoặc sau class/method, hoặc trước/sau từng test method. Hãy chọn mode theo thời điểm context không còn an toàn để tái sử dụng.

Ví dụ dùng ở cấp method:

~~~java
@Test
@DirtiesContext
void invalidatesContextAfterThisMethod() {
    // Thay đổi trạng thái bean hoặc cấu hình cần loại context.
}
~~~

Dùng ở cấp class:

~~~java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationTest {
    // Các test trong class dùng context này.
}
~~~

`@DirtiesContext` phù hợp khi test thay đổi trạng thái của context hoặc bean theo cách không thể khôi phục an toàn. Nó có chi phí vì context phải được tạo lại cho những test tiếp theo.

Không dùng annotation này như một lệnh dọn database tổng quát. Nó không tự động rollback transaction bên ngoài, xóa file, xóa message trong broker, reset static field hoặc hoàn tác request đã gửi tới dịch vụ khác. Hãy dọn đúng loại tài nguyên đã thay đổi.

## 8. Phân biệt trạng thái test instance, bean và tài nguyên ngoài context

Khi một test kết thúc, không phải mọi trạng thái đều được reset. Cần xác định trạng thái thuộc lớp nào.

| Trạng thái | Vòng đời chính | Điều gì xảy ra sau mỗi test? |
|---|---|---|
| Local variable trong test method | Method | Biến không còn được sử dụng sau method |
| Field của test instance với `PER_METHOD` | Test instance | Instance được tạo riêng cho method; instance cũ không dùng cho method kế tiếp |
| Field test instance với `PER_CLASS` | Test class | Giá trị có thể còn lại giữa các method |
| Singleton bean trong context cache | ApplicationContext | Có thể còn nguyên giữa nhiều method và class |
| Request-scoped/session-scoped bean | Request hoặc session | Phụ thuộc vòng đời scope tương ứng |
| Test-managed transaction | Test method | Thường kết thúc và rollback sau test nếu được cấu hình mặc định |
| Database ngoài context | Database hoặc container | Không tự xóa chỉ vì test instance kết thúc |
| File, message hoặc dữ liệu dịch vụ ngoài | Tài nguyên bên ngoài | Cần cơ chế dọn dẹp riêng |

Một ví dụ thường gây nhầm lẫn:

~~~java
@SpringBootTest
class CounterIntegrationTest {

    @Autowired
    CounterService counterService;

    @Test
    void firstTest() {
        counterService.increment();
        assertEquals(1, counterService.value());
    }

    @Test
    void secondTest() {
        // Nếu CounterService là singleton và không reset,
        // giá trị có thể đã thay đổi từ test trước.
    }
}
~~~

Với context được tái sử dụng, `CounterService` có thể vẫn là cùng singleton bean. JUnit tạo test instance mới không reset field bên trong bean đó.

Một cách xử lý là cung cấp phương thức reset có chủ đích cho fixture kiểm thử, hoặc thiết kế service không giữ trạng thái mutable theo từng request. Nếu trạng thái là dữ liệu persistence, hãy chuẩn bị và dọn database bằng cơ chế phù hợp.

## 9. Vòng đời transaction kiểm thử không phải vòng đời context

Spring TestContext có thể quản lý transaction cho test thông qua `TransactionalTestExecutionListener` khi test được đánh dấu `@Transactional` và có transaction manager phù hợp.

Ví dụ:

~~~java
@SpringBootTest
@Transactional
class OrderTransactionTest {

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrderInsideTestTransaction() {
        repository.save(new Order("ORD-1001", "CUS-42", 2));

        assertEquals(1, repository.count());
    }
}
~~~

Trong cấu hình test-managed transaction thông thường, transaction được bắt đầu cho test và rollback sau test. Điều này giúp dữ liệu database không rò rỉ giữa các method nếu mọi thao tác nằm trong transaction đó.

Tuy nhiên, context vẫn có thể được cache và dùng lại. Rollback transaction không đóng context, không tạo lại singleton bean và không reset mọi trạng thái trong bộ nhớ.

Cũng cần phân biệt test chạy trong cùng thread với request qua server thật. Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, HTTP request được xử lý trên thread của server và transaction riêng. Transaction gắn với test method không tự động bao trùm transaction của request đó. Nếu request ghi dữ liệu, test cần chiến lược dọn dữ liệu riêng.

Một số callback transaction có thứ tự riêng:

- `@BeforeTransaction` chạy trước khi transaction kiểm thử bắt đầu.
- `@AfterTransaction` chạy sau khi transaction kiểm thử kết thúc.
- `@BeforeEach` và `@AfterEach` thuộc lifecycle callback của JUnit và được điều phối cùng Spring TestContext.

Khi cần kiểm tra dữ liệu trước hoặc sau transaction, hãy dùng callback transaction tương ứng thay vì giả định mọi callback đều nằm trong cùng một transaction.

## 10. Bean lifecycle và context lifecycle

`ApplicationContext` quản lý lifecycle của bean. Khi singleton bean được tạo, Spring có thể thực hiện dependency injection, gọi aware callback, áp dụng bean post-processor, gọi init method và đưa bean vào sử dụng. Khi context đóng, Spring gọi các callback hủy đối với bean được quản lý phù hợp.

Ví dụ bean có callback:

~~~java
@Component
public class ResourceRegistry {

    @PostConstruct
    void initialize() {
        // Chuẩn bị tài nguyên khi bean được tạo.
    }

    @PreDestroy
    void close() {
        // Giải phóng tài nguyên khi bean bị hủy.
    }
}
~~~

Nếu context được cache qua nhiều test, `@PostConstruct` không chạy lại sau mỗi test method. Nó chạy khi bean được tạo trong context. Tương tự, `@PreDestroy` không chạy sau mỗi method; nó chạy khi bean bị hủy cùng context hoặc theo cơ chế lifecycle tương ứng.

Điều này quan trọng với bean giữ connection, thread pool, scheduler hoặc tài nguyên dài hạn. Nếu test muốn xác nhận init/destroy callback, hãy kiểm tra lifecycle của context hoặc bean trong một test có phạm vi phù hợp.

Không nên đóng thủ công context được Spring TestContext quản lý chỉ để làm sạch sau mỗi test. Việc đóng context thủ công có thể khiến cache giữ một context đã bị đóng và làm các test tiếp theo lỗi. Hãy để TestContext quản lý cache và dùng `@DirtiesContext` khi thực sự cần loại context.

## 11. Khi nào context mới được tạo và khi nào được tái sử dụng?

Có thể dùng các câu hỏi sau để xác định hành vi:

| Tình huống | Hành vi thường gặp |
|---|---|
| Hai test method trong cùng class, cùng cấu hình | Dùng chung context đã tải |
| Hai test class có cùng cache key | Có thể dùng chung context |
| Active profile khác nhau | Tải context riêng |
| Property source hoặc context customizer khác | Có thể tạo cache key khác và tải context riêng |
| Test đánh dấu `@DirtiesContext` | Context bị loại khỏi cache và đóng theo mode |
| Cache đầy và context cũ bị loại | Context bị loại được đóng |
| Test chạy ở JVM fork khác | Dùng cache riêng của JVM đó |
| JUnit tạo test instance mới | Không có nghĩa context mới được tạo |

Cụm từ “có thể dùng chung” là quan trọng: Spring tái sử dụng context khi cấu hình tạo cùng cache key và context vẫn còn trong cache. Nếu context đã bị loại hoặc bị đánh dấu dirty, framework sẽ tải lại.

Đừng suy luận context được tái sử dụng chỉ vì hai class cùng có `@SpringBootTest`. Hãy xem profile, property, configuration classes, context customizers và log cache khi cần xác định chính xác.

## 12. Kiểm thử an toàn khi context được chia sẻ

Vì context và singleton bean có thể được chia sẻ, test cần kiểm soát trạng thái.

**Không để test phụ thuộc vào thứ tự.** Mỗi method tự chuẩn bị dữ liệu và xác nhận kết quả của chính nó. Test không nên yêu cầu method khác chạy trước để tạo bản ghi hoặc thay đổi bean.

**Hạn chế mutable state trong singleton.** Service thường nên xử lý dữ liệu request qua tham số và kết quả trả về. Nếu cần cache hoặc stateful component, cung cấp cách làm sạch hoặc cô lập phù hợp.

**Dọn tài nguyên theo đúng vòng đời.** Transaction rollback xử lý thay đổi trong transaction; container có lifecycle riêng; file, message và dịch vụ bên ngoài cần cleanup riêng.

**Cẩn thận với chạy song song.** Hai test dùng chung context có thể đồng thời truy cập singleton bean. Nếu test thay đổi trạng thái chung, chúng có thể tranh chấp hoặc ảnh hưởng kết quả của nhau. Test dùng `@DirtiesContext` cũng cần được tổ chức cẩn thận khi chạy song song vì context có thể bị loại trong lúc test khác đang sử dụng.

**Dùng `@DirtiesContext` có mục tiêu.** Chỉ đánh dấu dirty khi trạng thái context không thể khôi phục. Nếu vấn đề chỉ là dữ liệu database, hãy dọn database thay vì tải lại toàn bộ context.

**Theo dõi số context được tải.** Log cache giúp nhận ra nhiều cấu hình khác nhau không cần thiết hoặc context liên tục bị loại. Việc này hữu ích khi suite chậm vì khởi động ứng dụng nhiều lần.

## 13. Quy trình phân tích một test Spring

Khi một test có hành vi khó hiểu, hãy lần lượt xác định:

1. JUnit đang dùng lifecycle `PER_METHOD` hay `PER_CLASS`?
2. Test method đang chạy trên test instance nào?
3. Test được tích hợp Spring qua extension hoặc annotation nào?
4. Context được tải từ cấu hình nào và có thể dùng cache key nào?
5. Bean đang được inject là prototype, request-scoped hay singleton?
6. Trạng thái gây lỗi nằm trong test instance, bean, transaction hay tài nguyên bên ngoài?
7. Test kết thúc thì callback nào chạy và loại trạng thái nào được reset?
8. Có `@DirtiesContext`, profile hoặc property nào khiến context bị tạo lại?
9. Nếu dữ liệu persistence bị rò rỉ, transaction test có thực sự bao trùm thao tác đó không?
10. Nếu chạy song song hoặc qua nhiều JVM fork, test có còn độc lập không?

Ví dụ, khi một singleton bean giữ bộ đếm và test thứ hai nhận giá trị khác không, hãy kiểm tra xem context có được cache hay không và bean có được reset không. Khi `@PostConstruct` chỉ chạy một lần dù nhiều test method được thực thi, đó thường là dấu hiệu context đang được tái sử dụng đúng cách. Khi log cho thấy context liên tục tải lại, hãy xem cache key và các annotation làm thay đổi cấu hình.

## Kết luận

Vòng đời kiểm thử và vòng đời `ApplicationContext` là hai cơ chế riêng. JUnit quản lý test class, test instance và các callback quanh method. Spring TestContext kết nối JUnit với context, dependency injection, transaction và listener. `ApplicationContext` quản lý bean, singleton, init/destroy callback và có thể được cache để dùng lại giữa nhiều test tương thích.

Vì vậy, một test instance mới không đồng nghĩa một Spring context mới. Field của test class và trạng thái trong singleton bean có thể có vòng đời khác nhau. Khi thiết kế test, hãy xác định rõ trạng thái thuộc test instance, context, transaction hay tài nguyên bên ngoài; từ đó chọn cách chuẩn bị và dọn dẹp tương ứng.


