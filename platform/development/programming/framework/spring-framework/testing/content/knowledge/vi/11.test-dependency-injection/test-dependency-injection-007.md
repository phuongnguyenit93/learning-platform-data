# PER_CLASS, test instance và context được khởi tạo lại

JUnit Jupiter và Spring TestContext Framework đều có khái niệm vòng đời, nhưng chúng quản lý hai loại đối tượng khác nhau. JUnit quyết định một test class được tạo thành bao nhiêu test instance; Spring quản lý vòng đời của `ApplicationContext`, nơi chứa các bean được inject vào test.

`@TestInstance(PER_CLASS)` yêu cầu JUnit dùng một instance duy nhất cho tất cả test method trong một class. Trong khi đó, Spring có thể tái sử dụng hoặc khởi tạo lại `ApplicationContext` độc lập với lựa chọn này. Hiểu rõ hai vòng đời giúp tránh nhầm lẫn về trạng thái dùng chung, dependency injection, `@BeforeAll` và tác động của `@DirtiesContext`.

## 1. Test instance là gì?

Test instance là object được JUnit tạo từ test class để chứa các trường, constructor và lifecycle method của bài kiểm thử.

Ví dụ:

```java
class AccountServiceTest {

    private String accountId;

    @BeforeEach
    void setUp() {
        accountId = "ACC-01";
    }

    @Test
    void loadsAccount() {
        // Sử dụng accountId
    }
}
```

JUnit tạo một object `AccountServiceTest`, sau đó gọi các lifecycle method và test method theo vòng đời đã cấu hình. Trường `accountId` thuộc về object test này, không phải thuộc về Spring `ApplicationContext`.

JUnit Jupiter hỗ trợ hai lifecycle chính:

- `PER_METHOD`: tạo một test instance mới cho mỗi test method. Đây là mặc định.
- `PER_CLASS`: tạo một test instance cho cả test class và dùng lại nó cho các test method trong class.

Có thể hình dung:

```text
PER_METHOD
Test class
   |
   +--> Instance A --> testOne()
   |
   +--> Instance B --> testTwo()
   |
   +--> Instance C --> testThree()


PER_CLASS
Test class
   |
   +--> Instance A
           |
           +--> testOne()
           +--> testTwo()
           +--> testThree()
```

Sự khác biệt quan trọng là các trường instance của test class được giữ lại giữa các method khi dùng `PER_CLASS`. Vì vậy, trạng thái do một test method thay đổi có thể được test method tiếp theo nhìn thấy.

## 2. Lifecycle mặc định PER_METHOD

Nếu không khai báo `@TestInstance`, JUnit Jupiter sử dụng `PER_METHOD`.

```java
class CounterTest {

    private int counter;

    @BeforeEach
    void setUp() {
        counter = 0;
    }

    @Test
    void incrementsCounter() {
        counter++;
        assertEquals(1, counter);
    }

    @Test
    void startsAtZero() {
        assertEquals(0, counter);
    }
}
```

Mỗi test method chạy trên một test instance mới. Vì vậy, trường `counter` của method thứ nhất không được chia sẻ với instance của method thứ hai. `@BeforeEach` vẫn chạy trước từng method và chuẩn bị trạng thái cho instance tương ứng.

`PER_METHOD` giúp test ít phụ thuộc vào thứ tự thực thi hơn vì mỗi method có object test riêng. Đây là lựa chọn phù hợp khi test cần giữ fixture mutable trong các trường instance.

## 3. Khai báo PER_CLASS

Để dùng một instance cho cả class, đặt `@TestInstance(TestInstance.Lifecycle.PER_CLASS)` trên test class:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CounterTest {

    private int counter;

    @BeforeEach
    void setUp() {
        counter = 0;
    }

    @Test
    void incrementsCounter() {
        counter++;
        assertEquals(1, counter);
    }

    @Test
    void alsoStartsAtZero() {
        assertEquals(0, counter);
    }
}
```

Cả hai test method sử dụng cùng một object `CounterTest`. Tuy nhiên, `@BeforeEach` đặt `counter` về 0 trước từng method, nên test không phụ thuộc giá trị mà method trước để lại.

Nếu bỏ `setUp()`, giá trị `counter` sẽ tiếp tục tồn tại sau khi một test method thay đổi nó. Test sau có thể nhìn thấy giá trị đã thay đổi.

### Lợi ích của PER_CLASS

Một lợi ích dễ nhận thấy là `@BeforeAll` và `@AfterAll` có thể là instance method thay vì bắt buộc phải là `static`:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class DatabaseScenarioTest {

    private TestDataset dataset;

    @BeforeAll
    void createSharedDataset() {
        dataset = new TestDataset();
        dataset.prepare();
    }

    @AfterAll
    void removeSharedDataset() {
        dataset.close();
    }

    @Test
    void readsFirstRecord() {
        // Sử dụng dataset
    }

    @Test
    void readsSecondRecord() {
        // Tiếp tục sử dụng dataset
    }
}
```

Vì JUnit giữ lại một instance cho class, lifecycle method không static có thể truy cập các trường instance. Điều này hữu ích khi một class có tài nguyên hoặc fixture chung được chuẩn bị một lần và được các test method sử dụng.

Tuy nhiên, tài nguyên dùng chung cần có chiến lược cleanup rõ ràng. Nếu mỗi test method làm thay đổi dataset, hãy khôi phục trạng thái trước method tiếp theo hoặc thiết kế các tình huống độc lập.

## 4. PER_CLASS không có nghĩa là Spring context chỉ có một vòng đời

Đây là điểm cần phân biệt rõ:

| Khái niệm | Đối tượng được quản lý | Thành phần quyết định |
|---|---|---|
| Test instance lifecycle | Object của test class | JUnit Jupiter |
| ApplicationContext lifecycle | Spring context và các bean trong context | Spring TestContext Framework |
| Test method lifecycle | Các bước trước/sau từng method | JUnit và các extension |
| Transaction lifecycle của test | Transaction gắn với test method | Spring TestContext transaction support |

Một test class dùng `PER_CLASS` chỉ có nghĩa JUnit tái sử dụng object test. Nó không yêu cầu Spring tạo context mới một lần cho class, cũng không ngăn Spring tái sử dụng context giữa các test class.

Ngược lại, hai test class khác nhau có thể có hai test instance riêng nhưng dùng chung một Spring `ApplicationContext` nếu cấu hình kiểm thử tương đương và context còn trong cache.

```text
JUnit test class A                 JUnit test class B
      |                                   |
      v                                   v
  Test instance A                     Test instance B
      |                                   |
      +----------------+------------------+
                       |
                       v
             Spring TestContext cache
                       |
                       v
             ApplicationContext C1
                       |
             +---------+---------+
             |                   |
          Bean X               Bean Y
```

Sơ đồ cho thấy test instance và Spring context là hai lớp quản lý riêng. Việc một test instance được tạo mới không đồng nghĩa các bean trong context cũng được tạo mới.

## 5. SpringExtension chuẩn bị test instance như thế nào?

Khi SpringExtension được đăng ký, JUnit gọi các callback của extension tại những mốc trong vòng đời test. Một callback quan trọng là `TestInstancePostProcessor`.

Sau khi JUnit tạo test instance, SpringExtension chuyển sự kiện chuẩn bị instance đến Spring TestContext Framework. Spring có thể inject các dependency được khai báo trên test class:

```java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        Order order = orderService.createOrder(
                new CreateOrderCommand("CUSTOMER-42")
        );

        assertNotNull(order.getId());
    }
}
```

Với `PER_CLASS`, instance của `OrderServiceTest` được tạo một lần. Spring chuẩn bị instance đó và inject `OrderService`. Các test method trong class sử dụng cùng trường `orderService`.

Với `PER_METHOD`, JUnit tạo instance mới cho từng method và Spring chuẩn bị từng instance mới theo vòng đời tương ứng.

Điều này không có nghĩa Spring tạo mới `OrderService` mỗi lần inject. Nếu context được tái sử dụng, bean singleton `OrderService` có thể vẫn là cùng một object trong nhiều lần chuẩn bị test instance.

## 6. Hai vòng đời hoạt động độc lập

Có thể xét hai trường hợp:

**Trường hợp A: test instance mới, context được tái sử dụng.**

Với `PER_METHOD`, JUnit tạo object test mới cho từng method. Nếu các test dùng cùng cấu hình và Spring context vẫn nằm trong cache, Spring có thể inject cùng bean singleton từ context đang được tái sử dụng.

**Trường hợp B: test instance được tái sử dụng, context được khởi tạo lại.**

Với `PER_CLASS`, JUnit giữ một object test cho cả class. Nếu context bị đánh dấu dirty, Spring có thể đóng context cũ và tạo context mới khi test tiếp theo cần sử dụng. Object test của JUnit vẫn là object cũ.

Bảng sau tóm tắt:

| Test instance | Spring context | Kết quả |
|---|---|---|
| Mới theo từng method | Tái sử dụng | Test object mới, bean có thể được dùng chung |
| Một instance cho cả class | Tái sử dụng | Test object và context tiếp tục tồn tại |
| Mới theo từng method | Được tạo lại | Test object mới nhận dependency từ context hiện hành |
| Một instance cho cả class | Được tạo lại | Test object giữ nguyên; dependency Spring cần được cập nhật theo context mới |

Vì vậy, khi điều tra một test thất bại do trạng thái dùng chung, cần xác định trạng thái nằm trong test instance hay trong Spring bean. Hai nơi có cơ chế reset khác nhau.

## 7. Spring context được khởi tạo lại khi nào?

Spring TestContext Framework cache `ApplicationContext` theo cấu hình kiểm thử. Khi một context còn hợp lệ và cấu hình phù hợp, Spring có thể tái sử dụng context đó.

Context có thể bị loại khỏi cache và cần tạo lại trong các trường hợp như:

- Test dùng `@DirtiesContext` để đánh dấu context dirty.
- Context không còn hợp lệ sau một thay đổi cấu hình hoặc trạng thái được Spring quản lý.
- Cache loại context theo chính sách giới hạn dung lượng.
- Một test class yêu cầu cấu hình context khác với context đã có.

Trong thực tế kiểm thử, `@DirtiesContext` là cách tường minh thường gặp để báo cho Spring rằng context đã bị thay đổi và không nên tiếp tục tái sử dụng.

Ví dụ:

```java
@SpringBootTest
class FeatureRegistryTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void registersTemporaryFeature() {
        featureRegistry.enable("temporary");

        assertTrue(featureRegistry.isEnabled("temporary"));
    }
}
```

Sau test method, Spring đánh dấu context dirty, loại nó khỏi cache và đóng context. Khi một test khác cần context có cùng cấu hình, Spring tạo context mới.

## 8. PER_CLASS kết hợp với @DirtiesContext

Khi dùng `PER_CLASS`, test instance được tái sử dụng dù Spring context có thể bị khởi tạo lại giữa các method. Vì vậy, cần quan tâm đến dependency được inject vào test instance.

Ví dụ:

```java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class FeatureRegistryTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void enablesTemporaryFeature() {
        featureRegistry.enable("temporary");

        assertTrue(featureRegistry.isEnabled("temporary"));
    }

    @Test
    void startsWithoutTemporaryFeature() {
        assertFalse(featureRegistry.isEnabled("temporary"));
    }
}
```

Sau method đầu tiên, context bị đánh dấu dirty. Test instance vẫn là cùng object vì lifecycle là `PER_CLASS`.

Spring TestContext Framework có cơ chế phối hợp giữa listener đánh dấu context dirty và `DependencyInjectionTestExecutionListener`. Khi context bị dirty, Spring yêu cầu dependency injection listener inject lại các dependency được quản lý theo field hoặc setter vào test instance trước test method tiếp theo. Nhờ đó, trường `featureRegistry` có thể được cập nhật để tham chiếu bean từ context mới.

Điểm này rất quan trọng: JUnit không tạo lại test instance trong tình huống trên. Spring chủ động chuẩn bị lại dependency cho instance đang được dùng.

Cơ chế reinjection áp dụng cho dependency injection mà Spring TestContext quản lý. Nó không reset mọi trường của test class. Ví dụ, một trường `int counter` do test tự thay đổi vẫn giữ giá trị cũ nếu không được reset trong `@BeforeEach`.

### Phân biệt dependency Spring và trạng thái riêng của test

| Thành phần | Khi context dirty | Cách xử lý |
|---|---|---|
| Trường `@Autowired` được Spring inject | Spring TestContext có thể inject lại theo cơ chế reinjection | Sử dụng dependency từ context mới |
| Trường dữ liệu test như `counter`, `input` | Không tự reset | Khởi tạo lại trong `@BeforeEach` |
| Trường static | Không thuộc test instance hoặc context | Tự khôi phục trạng thái |
| Dependency được truyền qua constructor | Constructor của PER_CLASS instance không chạy lại | Tránh giữ dependency constructor từ context bị đóng nếu context có thể reload trong class |
| Bean singleton trong context cũ | Context cũ bị đóng | Dùng bean từ context mới sau khi Spring chuẩn bị lại dependency |

## 9. Lưu ý với constructor injection và PER_CLASS

Constructor injection tạo dependency tại thời điểm JUnit tạo test instance. Với `PER_CLASS`, constructor chỉ được gọi một lần cho class.

Ví dụ:

```java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class OrderServiceTest {

    private final OrderService orderService;

    OrderServiceTest(OrderService orderService) {
        this.orderService = orderService;
    }

    @Test
    void createsOrder() {
        // Sử dụng orderService
    }
}
```

Nếu Spring context bị đóng và tạo lại trong khi test instance vẫn được tái sử dụng, trường final `orderService` vẫn tham chiếu đối tượng đã được truyền vào constructor ban đầu. Spring không thể gọi lại constructor trên cùng object để thay thế trường final đó.

Vì vậy, khi class dùng constructor injection và có khả năng làm dirty context giữa các method, cần thiết kế vòng đời sao cho dependency không bị giữ lại sau khi context cũ đóng. Một số lựa chọn:

- Dùng `PER_METHOD` để mỗi method có test instance mới khi context đã được làm mới sau method trước.
- Tránh làm dirty context giữa các method; nếu chỉ cần loại context sau cả class, cân nhắc chế độ class-level phù hợp.
- Dùng field hoặc setter injection do Spring TestContext quản lý nếu cần Spring reinject dependency vào một test instance `PER_CLASS`.
- Dùng method parameter injection khi dependency chỉ cần ở một method và muốn nhận bean từ context tại thời điểm method chạy.

Không nên kết hợp constructor injection, `PER_CLASS` và context reload giữa các method mà không xem xét rõ dependency có còn tham chiếu bean thuộc context cũ hay không.

## 10. @BeforeAll và dependency injection trong PER_CLASS

Với `PER_CLASS`, `@BeforeAll` có thể là instance method. Điều này cho phép dùng các trường đã được chuẩn bị trên test instance:

```java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CatalogServiceTest {

    @Autowired
    private CatalogService catalogService;

    private List<String> productIds;

    @BeforeAll
    void loadSharedProductIds() {
        productIds = catalogService.findFeaturedProductIds();
    }

    @Test
    void hasFeaturedProducts() {
        assertFalse(productIds.isEmpty());
    }

    @Test
    void firstProductIdIsAvailable() {
        assertNotNull(productIds.get(0));
    }
}
```

Ở đây `catalogService` được Spring inject vào test instance, còn `productIds` là dữ liệu test được chuẩn bị một lần. Các method dùng chung danh sách này.

Cần cân nhắc liệu dữ liệu đó có bất biến hay không. Nếu một test sửa `productIds`, test khác có thể nhìn thấy thay đổi. Nếu mỗi test cần một danh sách độc lập, hãy tạo bản sao hoặc chuẩn bị lại dữ liệu trong `@BeforeEach`.

Với `PER_METHOD`, `@BeforeAll` thông thường phải là static vì test instance chưa được giữ lại như một instance dùng chung cho class. Nếu cần truy cập dependency Spring trong phần chuẩn bị trước tất cả test method, có thể cân nhắc `PER_CLASS`, nhưng phải quản lý trạng thái instance và dependency theo các nguyên tắc ở trên.

## 11. PER_CLASS không làm transaction kéo dài qua cả class

Một nhầm lẫn khác là cho rằng dùng một test instance cho cả class thì transaction cũng được dùng chung.

Spring TestContext transaction support thường quản lý transaction theo test method. Nếu class hoặc method được đánh dấu `@Transactional`, mỗi test method có thể chạy trong một transaction riêng và được rollback sau method theo cấu hình mặc định.

```java
@SpringBootTest
@Transactional
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void createsAccount() {
        accountRepository.save(new Account("ACC-01"));
        assertTrue(accountRepository.findById("ACC-01").isPresent());
    }

    @Test
    void doesNotSeePreviousUncommittedAccount() {
        assertFalse(accountRepository.findById("ACC-01").isPresent());
    }
}
```

Test instance được chia sẻ, nhưng transaction không vì thế mà trở thành một transaction duy nhất cho cả class. Trạng thái database được quản lý theo transaction của test method. Ví dụ giả định không có dữ liệu `ACC-01` được tạo sẵn và mỗi method chạy với transaction test tiêu chuẩn.

Cần phân biệt:

- Trường instance của test class tồn tại theo `PER_CLASS`.
- Transaction test được quản lý theo vòng đời test method.
- Bean singleton tồn tại theo vòng đời của context.
- Context có thể được cache hoặc làm mới độc lập.

Nếu test commit transaction, thực hiện thao tác bất đồng bộ hoặc ghi vào tài nguyên ngoài transaction, cần cleanup riêng. `PER_CLASS` không tự động dọn dữ liệu và cũng không kéo dài transaction.

## 12. Trạng thái mutable và thứ tự chạy test

Với `PER_CLASS`, mọi test method cùng truy cập các trường instance. Nếu test method thay đổi trạng thái mà không reset, kết quả có thể phụ thuộc thứ tự chạy.

Ví dụ dễ gây phụ thuộc:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ShoppingCartTest {

    private final List<String> items = new ArrayList<>();

    @Test
    void addsBook() {
        items.add("BOOK-01");
        assertEquals(1, items.size());
    }

    @Test
    void startsWithEmptyCart() {
        assertTrue(items.isEmpty());
    }
}
```

Nếu `addsBook()` chạy trước, test `startsWithEmptyCart()` thất bại vì danh sách vẫn chứa dữ liệu. Nếu thứ tự ngược lại, cả hai có thể PASS.

Cách cải thiện là chuẩn bị trạng thái trước mỗi method:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ShoppingCartTest {

    private List<String> items;

    @BeforeEach
    void setUp() {
        items = new ArrayList<>();
    }

    @Test
    void addsBook() {
        items.add("BOOK-01");
        assertEquals(1, items.size());
    }

    @Test
    void startsWithEmptyCart() {
        assertTrue(items.isEmpty());
    }
}
```

Nếu trạng thái dùng chung thực sự là mục tiêu của test, hãy đặt tên và tổ chức test để người đọc hiểu sự phụ thuộc đó. Tuy nhiên, phần lớn test nên độc lập để có thể chạy riêng, chạy lại hoặc sắp xếp lại mà không thay đổi kết quả.

## 13. Chạy song song với PER_CLASS

Một test instance `PER_CLASS` được nhiều method dùng chung. Nếu JUnit được cấu hình chạy test song song, nhiều method có thể truy cập cùng trường hoặc cùng fixture tại một thời điểm.

Điều này tạo ra nguy cơ race condition khi trạng thái mutable không được bảo vệ:

```text
Một test instance PER_CLASS
          |
          +------ testA() ----+
          |                   |
          +------ testB() ----+--> Cùng sửa một field
          |                   |
          +------ testC() ----+
```

Nếu class cần chạy tuần tự vì có trạng thái dùng chung, có thể cấu hình execution mode phù hợp, ví dụ `@Execution(ExecutionMode.SAME_THREAD)`. Tuy nhiên, cách tốt hơn thường là thiết kế fixture độc lập hoặc bất biến để không cần đồng bộ hóa trạng thái giữa các method.

Không nên dùng `PER_CLASS` chỉ để tiết kiệm việc tạo vài object test. Lợi ích đó thường nhỏ so với chi phí điều tra lỗi do chia sẻ trạng thái hoặc chạy song song.

## 14. Cấu hình lifecycle mặc định cho toàn bộ test suite

Ngoài annotation trên từng test class, JUnit Jupiter cho phép cấu hình lifecycle mặc định bằng file `junit-platform.properties` trên test classpath:

```properties
junit.jupiter.testinstance.lifecycle.default = per_class
```

Khi cấu hình này có hiệu lực, test class không khai báo `@TestInstance` sẽ dùng `PER_CLASS` làm mặc định.

Có thể đặt file ở vị trí test resources phù hợp, thường là:

```text
src/test/resources/junit-platform.properties
```

Thay đổi mặc định toàn cục có thể ảnh hưởng các test class đang dựa vào `PER_METHOD`, đặc biệt các class có mutable field và không reset trong `@BeforeEach`. Cần xem xét toàn bộ test suite trước khi đổi chính sách. Với một nhóm test riêng cần `PER_CLASS`, annotation trên class giúp ý định hiển thị ngay tại nơi sử dụng.

## 15. Các tình huống thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Test method nhìn thấy dữ liệu do method trước tạo | Dùng `PER_CLASS` và field mutable không được reset | Khởi tạo lại trong `@BeforeEach` |
| `@BeforeAll` báo lỗi vì method không static | Test đang dùng lifecycle mặc định `PER_METHOD` | Dùng static method hoặc khai báo `PER_CLASS` |
| Dependency field tham chiếu bean từ context cũ | Context bị dirty nhưng dependency chưa được cập nhật theo cơ chế Spring TestContext | Kiểm tra DI listener, cách injection và thời điểm context reload |
| Constructor-injected bean không đổi sau context reload | Test instance `PER_CLASS` không chạy lại constructor | Tránh reload context giữa các method hoặc đổi cách quản lý dependency |
| Hai test class dùng cùng bean state | Spring context được tái sử dụng từ cache | Reset bean, dùng fixture độc lập hoặc đánh dấu context dirty khi thật sự cần |
| Test transaction bị nhầm là dùng chung cả class | Nhầm test instance lifecycle với transaction lifecycle | Kiểm tra transaction theo từng test method |
| Test thất bại khi chạy song song | Nhiều method cùng truy cập một test instance | Loại bỏ mutable shared state hoặc điều chỉnh execution mode |
| Context khởi động lại nhiều lần | Context thường xuyên bị đánh dấu dirty hoặc cấu hình khác nhau | Kiểm tra `@DirtiesContext` và cấu hình context |

Khi điều tra một lỗi, hãy trả lời lần lượt: test instance có được tạo mới không; Spring context có được tái sử dụng không; dependency được inject bằng field, setter, constructor hay method parameter; và trạng thái bị thay đổi thuộc test object, bean, transaction hay tài nguyên bên ngoài.

## 16. Cách chọn lifecycle phù hợp

| Nhu cầu | Lựa chọn |
|---|---|
| Mỗi test cần trạng thái instance riêng | `PER_METHOD` |
| Cần dùng instance method cho `@BeforeAll`/`@AfterAll` | `PER_CLASS` |
| Muốn chia sẻ fixture bất biến giữa các method | Có thể dùng `PER_CLASS` |
| Test có nhiều mutable field độc lập | Ưu tiên `PER_METHOD` hoặc reset rõ ràng trong `@BeforeEach` |
| Context có thể bị làm mới giữa các method | Hiểu cơ chế reinjection và tránh giữ dependency constructor cũ trong `PER_CLASS` |
| Chỉ muốn chia sẻ Spring bean | Để Spring context cache quản lý; không cần dùng `PER_CLASS` chỉ vì lý do này |
| Test method có thể chạy song song | Tránh mutable state trên test instance dùng chung hoặc cấu hình chạy tuần tự phù hợp |

`PER_CLASS` phù hợp khi việc dùng một test instance chung là chủ đích và trạng thái được quản lý rõ ràng. `PER_METHOD` thường dễ cô lập hơn vì mỗi method có object test mới. Dù chọn cách nào, vòng đời của Spring context vẫn được quản lý độc lập thông qua TestContext Framework và cache.

Điều quan trọng là không đồng nhất test instance với `ApplicationContext`. JUnit quyết định object test được tạo và tái sử dụng thế nào; Spring quyết định context được cache, đóng và khởi tạo lại thế nào. Khi hiểu hai vòng đời này, ta có thể dự đoán chính xác hơn dependency nào được giữ lại, trạng thái nào cần reset và cách tổ chức test an toàn khi context thay đổi.

