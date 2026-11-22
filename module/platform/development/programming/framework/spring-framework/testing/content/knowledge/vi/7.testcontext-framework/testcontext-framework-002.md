# Vai trò TestContext, TestContextManager và TestExecutionListener

Khi kiểm thử một ứng dụng Spring, nhiều hành vi cần được chuẩn bị trước khi phương thức test chạy: tạo `ApplicationContext`, inject dependency vào test instance, mở transaction kiểm thử, nạp dữ liệu SQL, quản lý event và dọn dẹp context sau khi test kết thúc. Nếu mỗi test tự thực hiện các bước này, mã kiểm thử sẽ lặp lại nhiều cấu hình và dễ bỏ sót một phần vòng đời.

**Spring TestContext Framework** cung cấp một mô hình chung để quản lý vòng đời đó. Ba thành phần cốt lõi cần hiểu là:

- `TestContext`: giữ thông tin về test hiện tại và cung cấp quyền truy cập tới `ApplicationContext` cùng các thuộc tính gắn với lần kiểm thử.
- `TestContextManager`: điều phối vòng đời kiểm thử, tạo và cập nhật `TestContext`, đồng thời gọi các listener theo từng giai đoạn.
- `TestExecutionListener`: nhận callback tại các mốc của vòng đời để thực hiện công việc như inject dependency, quản lý transaction, chạy SQL hoặc xử lý logic kiểm thử dùng chung.

Khi dùng JUnit Jupiter, `SpringExtension` kết nối JUnit với `TestContextManager`. Hiểu mối quan hệ này giúp ta biết vì sao `@Autowired`, `@Transactional`, `@Sql`, `@DirtiesContext` và các tính năng Spring Test hoạt động đúng thời điểm, đồng thời cho phép mở rộng framework bằng listener riêng khi cần.

## 1. TestContext Framework giải quyết vấn đề gì?

Một bài kiểm thử Spring thường cần nhiều hơn việc gọi một phương thức Java. Ví dụ, một test controller có thể cần:

1. Khởi tạo context chứa controller, service, security filter và cấu hình MVC.
2. Inject `MockMvc` hoặc các dependency vào test instance.
3. Chuẩn bị dữ liệu trước khi gọi endpoint.
4. Chạy request qua pipeline Spring MVC.
5. Ghi nhận exception hoặc kết quả của test.
6. Xóa dữ liệu hoặc đóng context nếu test làm thay đổi trạng thái ứng dụng.

TestContext Framework chuẩn hóa các bước đó thành một vòng đời có callback. Nhờ vậy, các thành phần mở rộng có thể tham gia đúng giai đoạn mà không cần biết chi tiết runner hoặc test framework đang điều khiển việc thực thi.

Framework được thiết kế để tích hợp với nhiều nền tảng kiểm thử. JUnit Jupiter sử dụng `SpringExtension`; JUnit 4 có `SpringRunner` (tên lớp là `SpringJUnit4ClassRunner`); các tích hợp khác có thể dùng cơ chế riêng. Phần lớn ví dụ trong bài dùng JUnit Jupiter vì đây là lựa chọn phổ biến trong các dự án Spring hiện nay.

TestContext Framework thuộc Spring Test. Nó có thể được dùng trong ứng dụng Spring Framework thuần và trong Spring Boot. Spring Boot cung cấp các annotation tiện dụng như `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, nhưng vòng đời TestContext bên dưới vẫn do Spring Test quản lý.

## 2. Ba thành phần cốt lõi và mối quan hệ

### `TestContext`

`TestContext` đại diện cho ngữ cảnh thực thi test. Nó cung cấp thông tin như:

- Class đang chứa test.
- Test instance hiện tại.
- Method test hiện tại.
- Exception phát sinh trong lần chạy, nếu có.
- `ApplicationContext` liên quan đến test.
- Một vùng thuộc tính để listener lưu và chia sẻ dữ liệu trong vòng đời test.

Listener nhận một đối tượng `TestContext` trong callback. Từ đó, listener có thể biết test nào đang chạy, truy cập bean hoặc lưu thông tin cần dùng ở callback tiếp theo.

`TestContext` là abstraction; implementation mặc định của Spring là `DefaultTestContext`. Việc dùng interface giúp listener ít phụ thuộc vào cách Spring lưu trữ thông tin bên trong.

### `TestContextManager`

`TestContextManager` điều phối vòng đời cho một test class. Nó tạo hoặc nhận `TestContext`, quản lý danh sách `TestExecutionListener`, rồi gọi callback tương ứng khi test framework thông báo các mốc bắt đầu và kết thúc.

Manager cũng phối hợp với cơ chế bootstrap để xác định cách tạo context, context loader và listener. Thông thường ta không cần tự tạo manager trong test; extension hoặc runner của Spring sẽ đảm nhận việc này.

### `TestExecutionListener`

`TestExecutionListener` là extension point để tham gia vòng đời test. Listener có thể chạy trước hoặc sau các mốc như chuẩn bị test instance, trước method, sau method và sau toàn bộ class.

Spring có các listener mặc định để thực hiện nhiều chức năng quen thuộc. Ví dụ, dependency injection listener inject các dependency vào test instance; transaction listener quản lý transaction kiểm thử; SQL scripts listener thực thi script được khai báo bằng `@Sql`; dirties context listener xử lý context được đánh dấu cần loại khỏi cache.

Sơ đồ khái quát:

```text
JUnit Jupiter
    |
    v
SpringExtension
    |
    v
TestContextManager
    |              \
    |               +--> TestExecutionListener A
    |               +--> TestExecutionListener B
    |               +--> TestExecutionListener C
    |
    v
TestContext
    |-- test class / instance / method / exception
    |-- ApplicationContext
    +-- attributes dùng trong vòng đời test
```

`SpringExtension` là cầu nối với JUnit; `TestContextManager` điều phối; `TestContext` mang thông tin; các listener thực hiện công việc ở từng giai đoạn.

## 3. Vòng đời callback của TestContext

TestContext Framework chia quá trình thực thi thành các mốc. Các callback phổ biến của `TestExecutionListener` gồm:

| Callback | Thời điểm | Công việc phù hợp |
| --- | --- | --- |
| `beforeTestClass` | Trước khi bắt đầu test class | Chuẩn bị tài nguyên cấp class hoặc ghi nhận bắt đầu suite nhỏ |
| `prepareTestInstance` | Sau khi test instance được tạo, trước khi chạy setup method | Inject dependency hoặc chuẩn bị test instance |
| `beforeTestMethod` | Trước method test và trước các setup method theo vòng đời JUnit tương ứng | Chuẩn bị dữ liệu theo method, mở transaction test |
| `beforeTestExecution` | Ngay trước khi thực thi thân method test | Bắt đầu đo thời gian hoặc ghi nhận thời điểm thực thi |
| `afterTestExecution` | Ngay sau thân method test, trước teardown method | Thu thập kết quả, thời gian hoặc exception của phần test |
| `afterTestMethod` | Sau khi hoàn tất method test và teardown tương ứng | Rollback transaction, dọn dữ liệu theo chính sách |
| `afterTestClass` | Sau khi hoàn tất các test method của class | Dọn tài nguyên cấp class hoặc ghi nhận kết thúc |

Tên callback mô tả mốc của TestContext. Thứ tự thực tế khi tích hợp với JUnit còn liên quan đến callback mà extension triển khai và thứ tự lifecycle của JUnit.

### Thứ tự khi dùng JUnit Jupiter

`SpringExtension` triển khai các callback của JUnit Jupiter và chuyển tiếp chúng tới `TestContextManager`. Có thể hình dung trình tự như sau:

```text
BeforeAllCallback
    -> TestContextManager.beforeTestClass()

TestInstancePostProcessor
    -> TestContextManager.prepareTestInstance()

BeforeEachCallback
    -> TestContextManager.beforeTestMethod()

@BeforeEach của người viết test

BeforeTestExecutionCallback
    -> TestContextManager.beforeTestExecution()

Thân @Test

AfterTestExecutionCallback
    -> TestContextManager.afterTestExecution()

@AfterEach của người viết test

AfterEachCallback
    -> TestContextManager.afterTestMethod()

AfterAllCallback
    -> TestContextManager.afterTestClass()
```

Sơ đồ này giúp xác định đúng nơi đặt logic. Chẳng hạn, dependency injection cho test instance cần diễn ra trước `@BeforeEach`, còn việc đo riêng thời gian chạy thân test nên bắt đầu ở `beforeTestExecution` và kết thúc ở `afterTestExecution`.

Trong JUnit Jupiter, callback `beforeTestMethod` của Spring được gọi ở `BeforeEachCallback`, trước phương thức `@BeforeEach` do người viết test khai báo. Callback `beforeTestExecution` được gọi sau setup method và ngay trước thân test. Ở chiều ngược lại, `afterTestExecution` xảy ra sau thân test và trước `@AfterEach`; `afterTestMethod` được gọi sau teardown method tương ứng.

Các mốc này có ý nghĩa khi dùng `@Transactional`, `@Sql` hoặc listener tùy chỉnh. Ví dụ, nếu muốn đo riêng thời gian thực thi method, đo từ `beforeTestExecution` đến `afterTestExecution`; nếu đo cả chuẩn bị fixture và teardown, cần chọn mốc rộng hơn.

## 4. TestContext chứa thông tin gì?

Listener không cần giữ một biến toàn cục để biết test nào đang chạy. Nó nhận `TestContext` và truy cập thông tin qua các phương thức của interface.

Ví dụ:

```java
public class TestInformationListener extends AbstractTestExecutionListener {

    @Override
    public void beforeTestMethod(TestContext testContext) {
        Class<?> testClass = testContext.getTestClass();
        Method testMethod = testContext.getTestMethod();
        Object testInstance = testContext.getTestInstance();

        System.out.printf(
            "Starting %s#%s on %s%n",
            testClass.getSimpleName(),
            testMethod.getName(),
            testInstance.getClass().getSimpleName()
        );
    }
}
```

Ví dụ này minh họa cách đọc thông tin test. Trong ứng dụng thực tế, nên dùng logger của dự án thay cho `System.out` để log có cấu trúc và có thể lọc theo cấp độ.

`TestContext` còn cung cấp `getApplicationContext()` để lấy context đang được dùng cho test. Listener có thể lấy bean từ context nếu thật sự cần tương tác với thành phần Spring:

```java
@Override
public void beforeTestMethod(TestContext testContext) {
    ApplicationContext applicationContext = testContext.getApplicationContext();
    TestAuditRecorder recorder = applicationContext.getBean(TestAuditRecorder.class);

    recorder.recordStarted(
        testContext.getTestClass(),
        testContext.getTestMethod()
    );
}
```

Chỉ nên truy cập context khi listener cần một bean. Việc gọi `getApplicationContext()` có thể kích hoạt quá trình tải context nếu nó chưa được tạo. Một listener dùng cho mọi test không nên vô tình buộc các test nhẹ phải khởi động toàn bộ ứng dụng.

## 5. TestContext và ApplicationContext khác nhau ra sao?

Hai tên này dễ gây nhầm lẫn nhưng đại diện cho hai loại ngữ cảnh khác nhau:

| Đối tượng | Đại diện cho | Nội dung tiêu biểu |
| --- | --- | --- |
| `ApplicationContext` | Container của ứng dụng Spring | Bean, environment, event, resource và cấu hình |
| `TestContext` | Ngữ cảnh của lần kiểm thử | Test class, instance, method, exception, ApplicationContext và attributes |

Một `ApplicationContext` có thể được nhiều test class sử dụng lại thông qua context cache. Mỗi test class có vòng đời TestContext được điều phối bởi manager tương ứng. TestContext tham chiếu tới ApplicationContext cần thiết cho test.

Ví dụ, `OrderService` là bean trong `ApplicationContext`; `OrderServiceTest` là test class; method `createsOrderWhenPaymentIsApproved()` là method test hiện tại. Listener có thể đọc method từ `TestContext` rồi lấy `OrderService` từ `ApplicationContext`.

Không dùng `TestContext` như một nơi thay thế cho dữ liệu nghiệp vụ của ứng dụng. Nó là hạ tầng hỗ trợ kiểm thử, còn trạng thái đơn hàng, khách hàng hoặc transaction thuộc các thành phần ứng dụng và database tương ứng.

## 6. TestContextManager điều phối như thế nào?

`TestContextManager` được tạo cho test class thông qua tích hợp của Spring với test framework. Manager phối hợp các thành phần sau:

- Bootstrapper xác định cấu hình TestContext, context loader và listener.
- TestContext chứa thông tin test hiện tại.
- Danh sách `TestExecutionListener` nhận callback.
- Cơ chế tải và cache `ApplicationContext` cung cấp context cho test.

Trong JUnit Jupiter, `SpringExtension` thường tạo hoặc lấy `TestContextManager` từ extension context store để các callback của cùng test class dùng chung manager theo vòng đời phù hợp.

Ta có thể xem manager như bộ điều phối sự kiện vòng đời. Nó không phải service nghiệp vụ, không thay thế JUnit và cũng không phải ApplicationContext. Hầu hết dự án chỉ cần dùng extension/runner do Spring cung cấp, không cần gọi trực tiếp các phương thức của manager.

### Bootstrapper

`TestContextBootstrapper` chịu trách nhiệm khởi tạo cấu hình TestContext. Bootstrapper mặc định là `DefaultTestContextBootstrapper`; với ứng dụng web có thể có bootstrapper chuyên biệt. Annotation `@BootstrapWith` cho phép chọn bootstrapper tùy chỉnh khi dự án cần thay đổi cách xây dựng TestContext.

Thông thường, các annotation kiểm thử của Spring Boot đã khai báo cơ chế bootstrap phù hợp. Chỉ nên tùy chỉnh bootstrapper khi cần thay đổi cách framework tạo context hoặc xây dựng bộ listener ở cấp nền tảng kiểm thử.

### Context loader và context cache

Context loader chịu trách nhiệm tải `ApplicationContext` từ cấu hình test. Spring Test dùng cơ chế cache để tái sử dụng context có cấu hình tương đương giữa các test class, giảm chi phí khởi tạo.

Các yếu tố như cấu hình context, profile, property, initializer, context customizer và một số annotation có thể ảnh hưởng khóa cache. Khi một test làm bẩn context và dùng `@DirtiesContext`, listener tương ứng sẽ yêu cầu framework loại context khỏi cache theo chính sách của annotation.

Điều này giải thích vì sao một test có thể chạy nhanh khi context đã được tạo bởi test trước, nhưng chậm hơn đáng kể khi chạy độc lập. Nó cũng giải thích vì sao listener không nên tự ý đóng context hoặc giữ tham chiếu tới bean sau khi context đã bị loại khỏi cache.

## 7. TestExecutionListener là gì?

`TestExecutionListener` là một interface của Spring Test, nằm trong package `org.springframework.test.context`. Nó định nghĩa callback cho các giai đoạn trong vòng đời test.

Các callback chính:

```java
public interface TestExecutionListener {

    default void beforeTestClass(TestContext testContext) throws Exception { }

    default void prepareTestInstance(TestContext testContext) throws Exception { }

    default void beforeTestMethod(TestContext testContext) throws Exception { }

    default void beforeTestExecution(TestContext testContext) throws Exception { }

    default void afterTestExecution(TestContext testContext) throws Exception { }

    default void afterTestMethod(TestContext testContext) throws Exception { }

    default void afterTestClass(TestContext testContext) throws Exception { }
}
```

Đây là hình dạng rút gọn để minh họa các callback; hãy tham chiếu API của phiên bản Spring đang dùng khi viết listener thực tế. Các phiên bản Spring hiện đại cung cấp `AbstractTestExecutionListener` để không phải tự triển khai mọi method.

Listener nên thực hiện một trách nhiệm hẹp, chẳng hạn ghi nhận thời gian, chuẩn bị dữ liệu dùng chung hoặc tích hợp một cơ chế kiểm thử nội bộ. Nếu listener vừa khởi tạo database, vừa tạo user, vừa kiểm tra quyền, vừa ghi log, nó sẽ khó tái sử dụng và khó xác định lỗi.

## 8. Các listener mặc định của Spring

Spring đăng ký một tập listener mặc định để cung cấp những tính năng kiểm thử phổ biến. Danh sách cụ thể có thể thay đổi theo phiên bản Spring và loại ứng dụng, nhưng các trách nhiệm thường gặp gồm:

| Listener | Vai trò |
| --- | --- |
| `ServletTestExecutionListener` | Chuẩn bị hạ tầng request/response cho một số kiểm thử web |
| `DirtiesContextBeforeModesTestExecutionListener` | Xử lý các chế độ `@DirtiesContext` trước test method |
| `ApplicationEventsTestExecutionListener` | Chuẩn bị và quản lý việc ghi nhận application event trong test |
| `DependencyInjectionTestExecutionListener` | Inject dependency vào test instance |
| `DirtiesContextTestExecutionListener` | Đánh dấu hoặc loại context khi test làm bẩn context |
| `TransactionalTestExecutionListener` | Quản lý transaction kiểm thử cho test được đánh dấu `@Transactional` |
| `SqlScriptsTestExecutionListener` | Thực thi SQL script được khai báo bằng `@Sql` |
| `EventPublishingTestExecutionListener` | Phát các event vòng đời test trong cơ chế event của Spring Test |
| `MockitoResetTestExecutionListener` | Reset Mockito mock/spy theo cấu hình hỗ trợ của phiên bản Spring tương ứng |

Không nên dựa vào thứ tự hoặc sự hiện diện của một listener cụ thể mà không xem phiên bản framework. Spring có thể bổ sung listener mới hoặc thay đổi cách tích hợp theo thời gian. Nếu cần chẩn đoán, hãy xem danh sách listener thực tế mà `TestContextManager` đang sử dụng trong phiên bản dự án.

### Dependency injection cho test instance

Ví dụ:

```java
@SpringBootTest
class OrderServiceIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void createsOrder() {
        // Các dependency đã được inject trước khi test chạy
    }
}
```

`DependencyInjectionTestExecutionListener` tham gia chuẩn bị test instance. Nhờ đó, test class có thể dùng `@Autowired` tương tự bean trong ứng dụng.

### Transactional listener

```java
@SpringBootTest
@Transactional
class OrderTransactionTest {

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrderInsideTestTransaction() {
        // Thao tác trong transaction kiểm thử
    }
}
```

`TransactionalTestExecutionListener` phối hợp với `@Transactional` để quản lý transaction test theo cấu hình Spring Test. Mặc định, transaction kiểm thử thường được rollback sau method. Có thể điều khiển commit/rollback bằng các annotation hỗ trợ như `@Commit`, `@Rollback` hoặc `TestTransaction` trong trường hợp phù hợp.

Không suy luận rằng transaction của test luôn đại diện cho transaction production. Test có thể chạy trong transaction bao ngoài và rollback ở cuối, trong khi service production có thể mở transaction qua proxy hoặc chạy ở thread khác. Hãy thiết kế integration test riêng nếu cần chứng minh commit, propagation hoặc xử lý sau commit.

### SQL scripts listener

`SqlScriptsTestExecutionListener` hỗ trợ `@Sql` để chạy script trước hoặc sau test:

```java
@SpringBootTest
@Sql(scripts = "/sql/orders-test-data.sql", executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class OrderQueryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void findsOrdersForCustomer() {
        // Dữ liệu được chuẩn bị bằng SQL script
    }
}
```

Listener phối hợp thời điểm chạy script với vòng đời test. Hãy đảm bảo script tương thích schema và transaction của test. Nếu script có side effect không thể rollback, cần có chiến lược cleanup riêng.

## 9. SpringExtension kết nối JUnit Jupiter với TestContextManager

Với JUnit Jupiter, tích hợp phổ biến là `SpringExtension`:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class CustomerServiceTest {

    @Autowired
    CustomerService customerService;

    @Test
    void findsCustomerById() {
        // ...
    }
}
```

`SpringExtension` triển khai các extension callback của JUnit Jupiter và chuyển tiếp chúng tới `TestContextManager`. Nó cũng hỗ trợ giải quyết tham số method test và lifecycle method từ Spring context khi phù hợp.

Trong Spring Boot, nhiều annotation kiểm thử đã bao gồm `SpringExtension` thông qua meta-annotation. Ví dụ:

```java
@SpringBootTest
class ApplicationIntegrationTest {
    // SpringExtension đã được đăng ký bởi annotation kiểm thử
}
```

Vì vậy, với `@SpringBootTest`, `@WebMvcTest` hoặc `@DataJpaTest` thông thường, không cần thêm `@ExtendWith(SpringExtension.class)` lần nữa. Với test dùng `@ContextConfiguration` thuần và JUnit Jupiter, đăng ký extension là cần thiết để kích hoạt tích hợp Spring Test.

### SpringExtension hỗ trợ những gì?

Ngoài việc chuyển tiếp callback, extension còn hỗ trợ:

- Chuẩn bị test instance để Spring inject dependency.
- Giải quyết tham số có thể lấy từ Spring context hoặc TestContext.
- Tích hợp các annotation kiểm thử của Spring với JUnit Jupiter.
- Quản lý các callback trước và sau test method theo vòng đời đã mô tả.

Điều này giúp người viết test dùng các annotation quen thuộc mà không cần gọi trực tiếp manager hoặc listener.

## 10. Đăng ký listener tùy chỉnh

Khi dự án cần hành vi dùng chung ở một mốc của vòng đời test, có thể tạo listener riêng bằng cách kế thừa `AbstractTestExecutionListener`.

Ví dụ ghi nhận thời điểm bắt đầu và kết thúc test method:

```java
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public class TestTimingListener extends AbstractTestExecutionListener {

    private static final String START_TIME =
        TestTimingListener.class.getName() + ".startTime";

    @Override
    public void beforeTestExecution(TestContext testContext) {
        testContext.setAttribute(START_TIME, System.nanoTime());
    }

    @Override
    public void afterTestExecution(TestContext testContext) {
        Object value = testContext.getAttribute(START_TIME);
        if (value instanceof Long startTime) {
            long elapsedNanos = System.nanoTime() - startTime;
            System.out.printf(
                "%s#%s took %d ms%n",
                testContext.getTestClass().getSimpleName(),
                testContext.getTestMethod().getName(),
                elapsedNanos / 1_000_000
            );
            testContext.removeAttribute(START_TIME);
        }
    }
}
```

Listener dùng attribute của `TestContext` để lưu thời điểm bắt đầu rồi đọc lại ở callback kết thúc. Cách này tránh dùng một biến static mutable để chia sẻ thời gian giữa các test. Ví dụ dùng `System.out` để ngắn gọn; trong dự án thực tế nên dùng logger.

Đăng ký listener bằng `@TestExecutionListeners`:

```java
@SpringBootTest
@TestExecutionListeners(
    listeners = TestTimingListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class OrderIntegrationTest {

    @Test
    void createsOrder() {
        // ...
    }
}
```

`MERGE_WITH_DEFAULTS` yêu cầu Spring kết hợp listener tùy chỉnh với listener mặc định. Đây thường là lựa chọn phù hợp khi chỉ bổ sung một listener và vẫn cần dependency injection, transaction, SQL script cùng các tính năng mặc định.

## 11. Vì sao phải chú ý `mergeMode` và listener mặc định?

Khi khai báo `@TestExecutionListeners`, cách kết hợp listener tùy chỉnh với danh sách mặc định rất quan trọng.

Hai chế độ thường cần phân biệt:

- `MERGE_WITH_DEFAULTS`: thêm listener được khai báo vào danh sách mặc định. Các listener mặc định vẫn được giữ và Spring sắp xếp danh sách theo quy tắc order.
- `REPLACE_DEFAULTS`: thay danh sách mặc định bằng listener được khai báo. Chỉ dùng khi chủ động muốn tự quản lý toàn bộ listener.

Ví dụ nếu thay toàn bộ listener mặc định mà quên `DependencyInjectionTestExecutionListener`, các field `@Autowired` trong test instance có thể không được inject. Nếu bỏ `TransactionalTestExecutionListener`, transaction test có thể không được quản lý như mong đợi. Nếu bỏ listener xử lý `@Sql`, script không được chạy theo cấu hình đã khai báo.

Trong các phiên bản Spring hiện đại, `@TestExecutionListeners` còn có thuộc tính `inheritListeners` để điều khiển listener được kế thừa từ class cha hoặc cấu hình meta-annotation. Hãy xem xét cả `inheritListeners` và `mergeMode` khi test class nằm trong hệ thống kế thừa nhiều tầng.

Thông thường, thêm một listener riêng nên dùng `MERGE_WITH_DEFAULTS`. Dùng `REPLACE_DEFAULTS` khi có lý do cụ thể, hiểu rõ chức năng mặc định nào bị loại và đã tự cung cấp các chức năng cần thiết.

## 12. Thứ tự thực thi listener

Khi có nhiều listener, thứ tự có thể ảnh hưởng đến kết quả. Ví dụ, listener chuẩn bị dữ liệu phải chạy trước listener đọc dữ liệu; listener ghi nhận kết quả có thể cần chạy sau listener thực hiện assertion hoặc thu thập exception.

Spring sắp xếp listener theo cơ chế ordering, dựa trên `Ordered` hoặc annotation `@Order` khi được hỗ trợ. Các callback trước thường được gọi theo thứ tự listener; các callback sau được gọi theo thứ tự ngược lại để tạo cấu trúc vào-ra tương ứng.

Có thể chỉ định order bằng `Ordered`:

```java
public class PrepareFixtureListener extends AbstractTestExecutionListener
        implements Ordered {

    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void beforeTestMethod(TestContext testContext) {
        // Chuẩn bị fixture trước listener có order lớn hơn
    }
}
```

Với các listener có thứ tự khác nhau, hãy chọn giá trị order theo hợp đồng và ghi lại lý do. Tránh phụ thuộc vào thứ tự mặc định không được tài liệu hóa hoặc vào thứ tự khai báo class trong một mảng annotation nếu framework có cơ chế sắp xếp riêng.

Không nên tạo nhiều listener có phụ thuộc vòng tròn. Nếu listener A cần dữ liệu do B tạo nhưng B lại cần kết quả do A tạo, hãy gộp trách nhiệm vào một thành phần có thứ tự rõ hoặc thiết kế lại dữ liệu chia sẻ.

## 13. Lưu dữ liệu giữa callback bằng TestContext attributes

`TestContext` cung cấp các thao tác `getAttribute`, `setAttribute`, `removeAttribute` và truy cập tập thuộc tính. Listener có thể dùng vùng này để truyền thông tin từ callback trước sang callback sau.

Ví dụ, listener lưu một ID được tạo trước test method:

```java
public class FixtureListener extends AbstractTestExecutionListener {

    private static final String CUSTOMER_ID =
        FixtureListener.class.getName() + ".customerId";

    @Override
    public void beforeTestMethod(TestContext testContext) {
        testContext.setAttribute(CUSTOMER_ID, "customer-test-42");
    }

    @Override
    public void afterTestMethod(TestContext testContext) {
        String customerId = (String) testContext.getAttribute(CUSTOMER_ID);
        // Dùng ID để cleanup nếu listener thực sự sở hữu fixture này
        testContext.removeAttribute(CUSTOMER_ID);
    }
}
```

Đặt tên attribute có namespace dựa trên tên class listener để tránh xung đột với listener khác. Kiểm tra null hoặc kiểu dữ liệu trước khi ép kiểu nếu attribute có thể không được tạo ở mọi nhánh.

Attributes phù hợp cho dữ liệu nhỏ, gắn với vòng đời test. Không nên dùng chúng như cache toàn cục, nơi lưu entity lớn hoặc phương tiện truyền trạng thái giữa các test method không liên quan. Dữ liệu cần chia sẻ giữa các test nên được quản lý bằng fixture, database hoặc cơ chế chuyên biệt có vòng đời rõ ràng.

## 14. Đăng ký listener toàn cục bằng cơ chế phát hiện mặc định

Ngoài việc khai báo listener trong `@TestExecutionListeners`, Spring Test hỗ trợ phát hiện listener mặc định thông qua cơ chế `SpringFactoriesLoader`. Trong nhiều phiên bản Spring, các listener mặc định được khai báo trong file `META-INF/spring.factories` theo key tương ứng với `TestExecutionListener`.

Cơ chế này phù hợp khi thư viện kiểm thử muốn cung cấp listener cho nhiều test class mà không phải thêm annotation ở từng class. Tuy nhiên, việc thêm listener vào danh sách mặc định có phạm vi rộng và có thể ảnh hưởng mọi test sử dụng TestContext trong classpath.

Khi tạo thư viện dùng chung:

- Chỉ đăng ký listener nếu nó có ích rộng rãi và không gây side effect ngoài ý muốn.
- Giữ callback nhanh, có thể chạy nhiều lần và an toàn khi test bị lỗi.
- Tài liệu hóa cách tắt hoặc thay thế listener nếu cần.
- Kiểm tra tương thích với phiên bản Spring mà thư viện hỗ trợ.
- Tránh tự động khởi tạo hệ thống ngoài chỉ vì một test dùng Spring Test.

Nếu listener chỉ phục vụ một module hoặc một nhóm test, đăng ký bằng `@TestExecutionListeners` thường dễ hiểu và giới hạn phạm vi hơn.

## 15. Listener và `@DirtiesContext`

Spring cache `ApplicationContext` để giảm thời gian chạy test. Nếu test làm thay đổi trạng thái singleton bean hoặc cấu hình context theo cách khiến các test sau không còn đáng tin cậy, có thể dùng `@DirtiesContext` để đánh dấu context cần loại khỏi cache.

Ví dụ:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LegacyConfigurationMutationTest {

    @Test
    void changesSharedConfigurationForThisTestClass() {
        // ...
    }
}
```

`DirtiesContextTestExecutionListener` phối hợp với annotation để xử lý context ở đúng thời điểm. Các chế độ như trước/sau method hoặc trước/sau class có thể tạo khác biệt lớn về thời gian chạy vì context phải được tải lại.

Không dùng `@DirtiesContext` như cách dọn mọi loại dữ liệu. Nó loại context khỏi cache và đóng tài nguyên liên quan theo cơ chế Spring, nhưng không thay thế cleanup cho database dùng chung, file ngoài context, message đã gửi hoặc dữ liệu trên dịch vụ bên ngoài.

Nếu một test chỉ thay đổi dữ liệu database, thường nên dùng transaction rollback hoặc fixture cleanup. Chỉ đánh dấu context dirty khi trạng thái của chính context hoặc bean singleton đã bị thay đổi đến mức không thể khôi phục đáng tin cậy.

## 16. Listener và transaction kiểm thử

`TransactionalTestExecutionListener` là ví dụ rõ về giá trị của callback. Khi test được đánh dấu `@Transactional`, listener phối hợp với `PlatformTransactionManager` để bắt đầu transaction trước method test và kết thúc theo chính sách rollback/commit.

```java
@SpringBootTest
@Transactional
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void savesCustomer() {
        repository.save(new Customer("customer-42"));

        assertTrue(repository.existsById("customer-42"));
    }
}
```

Thông thường, thay đổi được rollback sau test để dữ liệu không ảnh hưởng method tiếp theo. Nếu cần commit có chủ đích, có thể dùng `@Commit` hoặc `@Rollback(false)` trong tình huống phù hợp.

Có một số trường hợp transaction test không bao phủ được:

- Code chạy ở thread khác, chẳng hạn tác vụ `@Async`, không tham gia transaction gắn với thread test theo mặc định.
- Một transaction có propagation `REQUIRES_NEW` có thể commit độc lập với transaction bao ngoài của test.
- Dữ liệu được ghi bởi hệ thống ngoài hoặc message broker không tự rollback cùng database transaction.
- Test kiểm tra `afterCommit` nhưng transaction bị rollback ở cuối test nên callback commit không xảy ra.

Khi cần xác nhận commit thật hoặc event sau commit, hãy thiết kế test với ranh giới transaction rõ ràng, có thể dùng `TestTransaction` để kết thúc transaction kiểm thử theo cách có chủ đích và đọc lại dữ liệu từ transaction mới.

## 17. Listener và `@Sql`

`@Sql` khai báo script SQL chạy trước hoặc sau test method, class hoặc nhóm test tùy cấu hình. Listener xử lý annotation này và thực thi script bằng datasource phù hợp.

```java
@SpringBootTest
@Sql(
    scripts = "/sql/insert-customers.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
    scripts = "/sql/cleanup-customers.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
class CustomerSearchIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void findsCustomerByEmail() {
        assertTrue(repository.findByEmail("customer@example.test").isPresent());
    }
}
```

Script trước test tạo dữ liệu; script sau test dọn dữ liệu. Nếu test chạy trong transaction được rollback, cần hiểu script chạy trong hay ngoài transaction theo cấu hình `@SqlConfig` và transaction manager. Không giả định cleanup script luôn cần thiết nếu rollback đã bao phủ thay đổi; ngược lại, rollback cũng không hoàn tác side effect nằm ngoài transaction.

## 18. Viết listener tùy chỉnh để kiểm tra metadata hoặc quy tắc chung

Một listener có thể thực thi quy tắc chung cho nhiều test class. Ví dụ, listener có thể yêu cầu test có tên hoặc metadata nhất định, ghi nhận thông tin vào log hoặc chuẩn bị một fixture dùng chung.

```java
public class TestMetadataListener extends AbstractTestExecutionListener {

    @Override
    public void beforeTestMethod(TestContext testContext) {
        Method method = testContext.getTestMethod();

        if (method.isAnnotationPresent(RequiresExternalService.class)) {
            String endpoint = System.getenv("EXTERNAL_SERVICE_URL");
            if (endpoint == null || endpoint.isBlank()) {
                throw new IllegalStateException(
                    "EXTERNAL_SERVICE_URL is required for this test"
                );
            }
        }
    }
}
```

Ví dụ giả định dự án có annotation `@RequiresExternalService`. Listener kiểm tra cấu hình trước khi test chạy và thất bại rõ ràng nếu một dependency bắt buộc không được cấp. Nếu dependency chỉ tùy chọn, có thể cân nhắc condition hoặc assumption thay vì làm mọi test thất bại.

Trong thực tế, nên tránh để listener trở thành nơi chứa toàn bộ quy tắc test. Quy tắc đặc thù của một test thường nên nằm trong chính test hoặc extension chuyên biệt. Listener dùng chung chỉ nên chứa hành vi có cùng ý nghĩa cho nhiều test class.

## 19. Kiểm thử listener tùy chỉnh

Listener cũng là code và cần được kiểm tra. Có thể kiểm tra đơn vị hành vi nhỏ bằng cách mock `TestContext` hoặc tạo một test context phù hợp, sau đó xác nhận listener đọc/ghi attribute và gọi collaborator đúng.

Ví dụ kiểm tra listener ghi attribute:

```java
@ExtendWith(MockitoExtension.class)
class FixtureListenerTest {

    @Mock
    TestContext testContext;

    @Test
    void storesCustomerIdBeforeTestMethod() {
        FixtureListener listener = new FixtureListener();

        listener.beforeTestMethod(testContext);

        verify(testContext).setAttribute(
            contains("customerId"),
            eq("customer-test-42")
        );
    }
}
```

Đây là ví dụ minh họa; nếu attribute key là private constant, test có thể xác nhận theo cách tương tác hoặc hành vi công khai mà nhóm chọn. Không nên mở rộng visibility chỉ để test một hằng số nội bộ.

Ngoài unit test listener, nên có ít nhất một test tích hợp nhỏ đăng ký listener qua `@TestExecutionListeners` để chứng minh framework thực sự gọi callback ở đúng thời điểm. Unit test chỉ chứng minh logic của listener; nó không chứng minh listener được phát hiện hoặc được đăng ký đúng.

## 20. Các lỗi thường gặp khi dùng TestContext Framework

- **Quên đăng ký `SpringExtension`:** test dùng `@ContextConfiguration` nhưng JUnit Jupiter không có extension, nên Spring không inject dependency và callback không chạy.
- **Đăng ký listener nhưng thay thế danh sách mặc định ngoài ý muốn:** mất dependency injection, transaction hoặc SQL listener.
- **Dùng sai callback:** chuẩn bị fixture sau khi thân test đã bắt đầu hoặc cleanup trước khi assertion hoàn tất.
- **Truy cập ApplicationContext quá sớm:** listener làm test vốn nhẹ phải tải toàn bộ context.
- **Giữ state trong biến static:** các test chạy song song hoặc theo thứ tự khác nhau có thể làm state rò rỉ.
- **Dùng `@DirtiesContext` để dọn mọi dữ liệu:** context cache và database là hai loại trạng thái khác nhau.
- **Giả định transaction test rollback mọi side effect:** message, email, HTTP request và transaction ở thread khác không tự rollback.
- **Không xét thứ tự listener:** listener đọc dữ liệu trước khi listener khác chuẩn bị xong.
- **Tạo listener quá nhiều trách nhiệm:** callback khó dự đoán, khó kiểm thử và làm mọi test phụ thuộc vào hạ tầng chung.
- **Không kiểm tra test bị bỏ qua hoặc context không được tạo:** pipeline có thể không cung cấp bằng chứng mà nhóm nghĩ rằng đã có.

## 21. Khi nào nên dùng listener và khi nào nên dùng JUnit extension?

JUnit Jupiter extension là cơ chế mở rộng của JUnit. `TestExecutionListener` là cơ chế mở rộng của Spring TestContext. Hai loại có thể cùng xuất hiện trong một test nhưng tham gia ở các lớp khác nhau.

| Nhu cầu | Cơ chế thường phù hợp |
| --- | --- |
| Tích hợp callback của Spring, quản lý context, transaction hoặc dependency injection | TestContext Framework và `TestExecutionListener` |
| Thêm hành vi gắn với JUnit Jupiter nhưng không cần Spring context | JUnit Jupiter extension |
| Tham số hóa, điều kiện bật/tắt hoặc lifecycle đặc thù của JUnit | Các annotation và extension của JUnit Jupiter |
| Inject bean hoặc phối hợp với `ApplicationContext` trong test | SpringExtension và TestContext Framework |
| Dùng chung logic cho nhiều test framework thông qua Spring Test | `TestExecutionListener` khi logic thật sự thuộc vòng đời TestContext |

Nếu logic không cần `ApplicationContext` hoặc TestContext, một JUnit extension thường gọn hơn. Nếu logic cần biết test class, test method, context Spring và phải chạy cùng các listener mặc định, `TestExecutionListener` là điểm mở rộng phù hợp.

Không nên đăng ký cùng một hành vi ở cả JUnit extension và TestExecutionListener nếu không có lý do rõ ràng, vì callback có thể chạy hai lần và tạo side effect lặp.

## 22. Quy trình chẩn đoán khi callback không chạy như mong đợi

Khi `@Autowired`, `@Sql`, transaction hoặc listener tùy chỉnh không hoạt động, hãy lần lượt xác định:

1. **Test framework:** test đang chạy bằng JUnit Jupiter, JUnit 4 hay nền tảng khác?
2. **Integration adapter:** `SpringExtension` hoặc runner phù hợp đã được đăng ký chưa? Annotation Spring Boot có tự đăng ký extension không?
3. **Bootstrap:** context có được cấu hình bằng `@ContextConfiguration`, `@SpringBootTest` hoặc annotation tương ứng không?
4. **Listener list:** listener mặc định có còn không? `@TestExecutionListeners` đang merge hay replace?
5. **Lifecycle point:** logic đang đặt ở callback nào và callback đó xảy ra trước hay sau setup/teardown method?
6. **Ordering:** listener có chạy trước listener cung cấp dữ liệu hoặc dependency mà nó cần không?
7. **Context state:** context có được cache, đánh dấu dirty hoặc tải lại không?
8. **Transaction:** test đang chạy trong transaction nào, thread nào và side effect nằm trong hay ngoài transaction?

Có thể bật log phù hợp cho package Spring Test để quan sát quá trình bootstrap, tải context và callback. Hãy dùng mức log vừa đủ trong lúc chẩn đoán và tránh để log quá chi tiết trong toàn bộ pipeline nếu nó làm báo cáo khó đọc.

## 23. Tổng kết vai trò trong một test Spring

Khi một test Spring bắt đầu, test framework gọi adapter tương ứng như `SpringExtension`. Extension chuyển các mốc lifecycle tới `TestContextManager`. Manager cập nhật `TestContext` và gọi `TestExecutionListener` theo thứ tự phù hợp. Listener mặc định inject dependency, quản lý transaction, chạy SQL hoặc xử lý context; listener tùy chỉnh có thể bổ sung hành vi dùng chung. `ApplicationContext` cung cấp bean của ứng dụng và có thể được cache để tái sử dụng giữa các test.

Khi hiểu rõ ba vai trò này, ta có thể chọn đúng điểm để chuẩn bị dữ liệu, đo thời gian, quản lý transaction hoặc cleanup. TestContext mang thông tin của lần kiểm thử; TestContextManager điều phối vòng đời; TestExecutionListener thực hiện công việc ở từng callback. SpringExtension kết nối mô hình đó với JUnit Jupiter, giúp các annotation kiểm thử Spring hoạt động nhất quán trong suốt vòng đời test.
