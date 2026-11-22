# Vòng đời test instance và trạng thái chia sẻ

JUnit Jupiter tạo và quản lý đối tượng test theo một vòng đời xác định. Cách tạo đối tượng này ảnh hưởng trực tiếp đến constructor, field của test class, các callback `@BeforeAll` / `@AfterAll`, khả năng chạy song song và cách dữ liệu được chia sẻ giữa các test. Khi hiểu rõ vòng đời, ta có thể chọn cách tổ chức fixture phù hợp mà không để một test vô tình làm thay đổi kết quả của test khác.

Mặc định, JUnit Jupiter dùng **một test instance cho mỗi test method** (`PER_METHOD`). Ngoài ra, ta có thể cấu hình **một test instance cho cả test class** (`PER_CLASS`) bằng `@TestInstance`. Hai chế độ này không thay đổi ý nghĩa của assertion hay cách JUnit phát hiện `@Test`; chúng thay đổi thời điểm tạo instance và thời gian tồn tại của trạng thái nằm trong instance đó.

## 1. Test instance là gì?

Một test instance là đối tượng Java được JUnit tạo từ lớp chứa các phương thức kiểm thử. Ví dụ:

```java
class AccountServiceTest {
    private AccountService service;

    @BeforeEach
    void setUp() {
        service = new AccountService();
    }

    @Test
    void createsAccount() {
        // Kiểm tra hành vi tạo tài khoản.
    }
}
```

`AccountServiceTest` là test class; mỗi đối tượng `AccountServiceTest` được tạo khi JUnit thực thi test là một test instance. Các field không phải `static`, chẳng hạn `service`, thuộc về một instance cụ thể. Vì vậy, thời gian sống của field phụ thuộc vào việc JUnit tạo một hay nhiều instance.

Vòng đời của test instance độc lập với vòng đời của đối tượng ứng dụng mà test đang kiểm tra. Chẳng hạn, một test dùng `@SpringBootTest` có thể nhận cùng một Spring `ApplicationContext` đã được TestContext Framework cache, trong khi test class vẫn được tạo instance mới cho từng test method. Ngược lại, chọn `PER_CLASS` chỉ làm test instance tồn tại lâu hơn; nó không tự làm Spring singleton bean hoặc database được khởi tạo lại.

## 2. Chế độ mặc định `PER_METHOD`

Nếu không khai báo `@TestInstance`, JUnit Jupiter mặc định sử dụng `TestInstance.Lifecycle.PER_METHOD`. JUnit tạo một instance mới cho mỗi test method. Các field instance của test class vì vậy được khởi tạo lại khi chuyển sang method khác.

```java
class MessageServiceTest {
    private final List<String> sentMessages = new ArrayList<>();

    @Test
    void recordsFirstMessage() {
        sentMessages.add("hello");

        assertThat(sentMessages).containsExactly("hello");
    }

    @Test
    void startsWithAnEmptyMessageList() {
        assertThat(sentMessages).isEmpty();
    }
}
```

Hai test trên không phụ thuộc thứ tự chạy. Khi chạy `recordsFirstMessage`, list thuộc instance của method đó. Khi chạy `startsWithAnEmptyMessageList`, JUnit tạo instance khác nên field `sentMessages` được khởi tạo lại.

`PER_METHOD` là lựa chọn an toàn để bắt đầu vì nó giảm khả năng trạng thái instance bị rò rỉ giữa các test method. Tuy vậy, chế độ này không tự cô lập mọi thứ. `static` field, singleton, cache, file, system property, database, message broker và các tài nguyên bên ngoài vẫn có thể được chia sẻ giữa nhiều test.

### 2.1. Ảnh hưởng đến constructor

Với `PER_METHOD`, constructor test class được gọi cho từng test method. Nếu constructor nhận tham số qua `ParameterResolver` của JUnit hoặc extension, việc tạo instance và phân giải tham số cũng diễn ra theo từng instance.

Constructor nên dùng để khởi tạo các dependency hoặc giá trị bất biến mà test instance cần. Tránh đặt hành động tốn kém hoặc tác dụng phụ toàn cục trong constructor, vì hành động đó sẽ lặp lại theo số test method.

### 2.2. Quy tắc của `@BeforeAll` và `@AfterAll`

Trong chế độ `PER_METHOD`, `@BeforeAll` và `@AfterAll` phải là phương thức `static`, vì JUnit gọi chúng ở phạm vi class trước khi có một instance cụ thể dành cho từng test method và sau khi các method đã kết thúc.

```java
class AccountServiceTest {
    @BeforeAll
    static void startSuite() {
        // Khởi tạo tài nguyên dùng chung ở phạm vi class.
    }

    @BeforeEach
    void setUp() {
        // Chuẩn bị dữ liệu riêng cho từng test method.
    }

    @AfterEach
    void tearDown() {
        // Dọn dữ liệu riêng của test method.
    }

    @AfterAll
    static void stopSuite() {
        // Giải phóng tài nguyên ở phạm vi class.
    }
}
```

Các callback `@BeforeEach` và `@AfterEach` vẫn chạy trên instance tương ứng với test method. Chúng là nơi thích hợp để chuẩn bị và dọn fixture riêng của từng test.

## 3. Chế độ `PER_CLASS`

Khi một test class được đánh dấu `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, JUnit tạo một instance duy nhất cho class đó và dùng instance này cho các test method trong class.

```java
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import static org.junit.jupiter.api.TestInstance.Lifecycle.PER_CLASS;

@TestInstance(PER_CLASS)
class ReportServiceTest {
    private ReportService service;

    @BeforeAll
    void initializeClassFixture() {
        // Đây là instance method vì test instance đã tồn tại.
        service = new ReportService();
    }

    @BeforeEach
    void resetStateForCurrentTest() {
        service.clearReports();
    }

    @Test
    void createsMonthlyReport() {
        service.createMonthlyReport(2026, 11);

        assertThat(service.findAll()).hasSize(1);
    }

    @Test
    void startsWithoutReportsForAnotherTest() {
        assertThat(service.findAll()).isEmpty();
    }

    @AfterAll
    void releaseClassFixture() {
        service.close();
    }
}
```

Với `PER_CLASS`, `@BeforeAll` và `@AfterAll` có thể là instance method. Chúng được gọi một lần cho vòng đời của class, nên có thể truy cập field của test instance. Đây là khác biệt thường được dùng khi cần khởi tạo một fixture tốn kém một lần hoặc khi muốn dùng non-static `@MethodSource`.

Điểm cần chú ý là `service` cũng tồn tại xuyên suốt các test method. Ví dụ trên chủ động gọi `clearReports()` trong `@BeforeEach` để mỗi test bắt đầu từ trạng thái sạch. Nếu bỏ bước reset này, test tạo báo cáo có thể khiến test kế tiếp nhìn thấy báo cáo cũ.

### 3.1. Khi nào nên dùng `PER_CLASS`?

Chế độ này có thể phù hợp khi:

- Cần khởi tạo một tài nguyên đắt đỏ một lần cho cả class, chẳng hạn một server hoặc fixture dùng chung có cơ chế reset rõ ràng.
- Cần dùng `@BeforeAll` / `@AfterAll` không phải `static` để truy cập dependency được quản lý trên test instance.
- Cần khai báo factory phương thức không `static`, ví dụ một `@MethodSource` lấy dữ liệu từ field của test instance.
- Các test trong class được thiết kế để quản lý trạng thái chia sẻ có chủ đích và có thể reset độc lập.

Không nên chọn `PER_CLASS` chỉ để tránh viết `static` hoặc để chia sẻ kết quả của một test cho test khác. Nếu test B cần dữ liệu do test A tạo ra, hai test đã bị phụ thuộc thứ tự. Hãy để mỗi test tự thiết lập điều kiện đầu vào hoặc trích phần tạo dữ liệu thành một fixture dùng chung có thể gọi độc lập.

### 3.2. Rủi ro trạng thái bị rò rỉ

Với `PER_CLASS`, mọi field instance có thể được nhiều test method cùng truy cập. Một test thay đổi list, map, counter, mock hoặc object domain có thể ảnh hưởng tới test khác nếu không khôi phục trạng thái.

Ví dụ sau thể hiện một thiết kế dễ gây lỗi:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ShoppingCartTest {
    private final List<String> items = new ArrayList<>();

    @Test
    void addsAnItem() {
        items.add("book");
        assertThat(items).containsExactly("book");
    }

    @Test
    void startsWithAnEmptyCart() {
        assertThat(items).isEmpty();
    }
}
```

Test `startsWithAnEmptyCart` sẽ phụ thuộc vào việc test `addsAnItem` đã chạy hay chưa. JUnit không đảm bảo thứ tự test method theo thứ tự khai báo trong source. Khi chạy riêng từng test, test có thể qua; khi chạy cả class hoặc chạy song song, kết quả có thể khác.

Cách sửa phù hợp là khởi tạo hoặc reset dữ liệu trước mỗi test:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ShoppingCartTest {
    private List<String> items;

    @BeforeEach
    void createFreshCart() {
        items = new ArrayList<>();
    }

    @Test
    void addsAnItem() {
        items.add("book");

        assertThat(items).containsExactly("book");
    }

    @Test
    void startsWithAnEmptyCart() {
        assertThat(items).isEmpty();
    }
}
```

Một cách khác là giữ fixture bất biến sau `@BeforeAll` và tạo object mutable mới cho từng test. Ví dụ, có thể chia sẻ một cấu hình đọc-only nhưng tạo mới `ShoppingCart` trong `@BeforeEach`. Cách này giảm số vị trí phải reset và giúp ownership của trạng thái rõ ràng.

## 4. Trình tự callback trong một test class

JUnit Jupiter cung cấp các callback theo phạm vi class và phạm vi từng test. Với một test class đơn giản, có thể hình dung trình tự như sau:

```text
Tạo test instance
        |
        v
   @BeforeAll                 một lần cho class
        |
        +-----------------------------------+
        |                                   |
        v                                   v
   @BeforeEach                         @BeforeEach
        |                                   |
        v                                   v
     @Test                               @Test
        |                                   |
        v                                   v
   @AfterEach                          @AfterEach
        |                                   |
        +-----------------------------------+
        |
        v
    @AfterAll                  một lần sau class
```

Sơ đồ tập trung vào callback của JUnit. Các extension có thể bổ sung callback ở những điểm tương ứng trong vòng đời; thứ tự chi tiết giữa extension và callback được quy định bởi extension API và thứ tự đăng ký extension.

| Callback | Tần suất | Mục đích thường gặp |
|---|---|---|
| Constructor | Mỗi test instance | Khởi tạo field và dependency của instance |
| `@BeforeAll` | Một lần trước các test trong class | Tạo tài nguyên cấp class |
| `@BeforeEach` | Trước mỗi test method | Chuẩn bị dữ liệu riêng của test |
| `@Test` | Theo từng test method | Thực thi kịch bản và assertion |
| `@AfterEach` | Sau mỗi test method | Dọn tài nguyên riêng của test |
| `@AfterAll` | Một lần sau các test trong class | Đóng tài nguyên cấp class |

### 4.1. Thứ tự giữa các phương thức callback

Không nên dựa vào thứ tự khai báo các phương thức `@BeforeEach` hoặc `@AfterEach` trong cùng một class. JUnit sử dụng thứ tự xác định nhưng không được thiết kế để phản ánh thứ tự trong source; thứ tự đó có thể khó đọc và không nên được dùng để tạo phụ thuộc giữa các callback.

Nếu một test cần hai bước chuẩn bị theo trình tự, hãy gọi chúng từ một phương thức setup duy nhất hoặc đóng gói thành helper có tên thể hiện thứ tự. Điều này giúp luồng chuẩn bị được nhìn thấy trực tiếp.

Với kế thừa, callback `@BeforeAll` và `@BeforeEach` được thực thi từ superclass xuống subclass. Các callback `@AfterEach` và `@AfterAll` chạy theo chiều ngược lại: subclass trước superclass. Điều này cho phép lớp cha chuẩn bị tài nguyên chung và lớp con mở rộng phần chuẩn bị; khi dọn dẹp, lớp con giải phóng phần riêng trước khi lớp cha giải phóng tài nguyên nền.

Ví dụ:

```java
abstract class BaseRepositoryTest {
    @BeforeEach
    void initializeBaseFixture() {
        // Chuẩn bị fixture chung.
    }

    @AfterEach
    void cleanBaseFixture() {
        // Dọn fixture chung.
    }
}

class CustomerRepositoryTest extends BaseRepositoryTest {
    @BeforeEach
    void initializeCustomerFixture() {
        // Chạy sau initializeBaseFixture().
    }

    @AfterEach
    void cleanCustomerFixture() {
        // Chạy trước cleanBaseFixture().
    }
}
```

Không dùng kế thừa chỉ để chia sẻ một vài dòng setup ngắn. Nếu fixture có nhiều biến thể, factory hoặc helper tường minh thường dễ hiểu hơn một cây lớp test có nhiều callback ẩn.

## 5. Vòng đời của `@Nested` và dynamic test

`@Nested` cho phép nhóm các test liên quan trong những lớp lồng nhau không `static`. Cấu trúc này hữu ích khi một đối tượng có nhiều trạng thái hoặc hành vi theo bối cảnh:

```java
class OrderServiceTest {
    private OrderService service;

    @BeforeEach
    void setUp() {
        service = new OrderService();
    }

    @Nested
    class WhenOrderIsPending {
        @Test
        void allowsConfirmation() {
            // Kiểm tra xác nhận đơn hàng.
        }
    }

    @Nested
    class WhenOrderIsCancelled {
        @Test
        void rejectsConfirmation() {
            // Kiểm tra từ chối xác nhận.
        }
    }
}
```

Lớp nested có thể truy cập thành viên của instance bên ngoài theo quy tắc của Java. Vì vậy, field mutable ở lớp ngoài có thể trở thành trạng thái dùng chung trong cấu trúc nested. Hãy tổ chức setup sao cho mỗi kịch bản nhận fixture đúng trạng thái của nó; không dùng một test nested để chuẩn bị dữ liệu cho test nested khác.

Các lớp nested cũng có thể khai báo callback riêng để bổ sung setup hoặc cleanup cho ngữ cảnh của chúng. Khi có nhiều cấp nested, hãy giữ callback ngắn và đặt fixture gần nhóm test sử dụng nó để người đọc nhận biết được trạng thái nào được tạo ở mỗi cấp.

### 5.1. Dynamic test và callback

`@TestFactory` tạo các dynamic test bằng `DynamicTest`. Có một khác biệt quan trọng: `@BeforeEach` và `@AfterEach` chạy quanh phương thức factory, không chạy riêng cho từng dynamic test được factory trả về. Vì vậy, không nên giả định mỗi dynamic test có một chu kỳ setup/teardown độc lập như một phương thức `@Test` thông thường.

```java
class PriceRulesTest {
    @TestFactory
    Stream<DynamicTest> validatesSeveralPrices() {
        List<BigDecimal> prices = List.of(
                new BigDecimal("0.00"),
                new BigDecimal("10.00"),
                new BigDecimal("99.00"));

        return prices.stream().map(price -> DynamicTest.dynamicTest(
                "accepts price " + price,
                () -> assertThat(price).isGreaterThanOrEqualTo(BigDecimal.ZERO)
        ));
    }
}
```

Trong ví dụ, dynamic test chỉ dùng dữ liệu cục bộ và assertion thuần. Nếu mỗi dynamic test cần một service hoặc database state riêng, hãy tạo fixture ngay trong executable của từng `DynamicTest`, hoặc cân nhắc `@ParameterizedTest` nếu kịch bản là một test method chạy với nhiều bộ tham số. Không dựa vào `@BeforeEach` để reset giữa các dynamic node.

## 6. Trạng thái instance, trạng thái static và tài nguyên bên ngoài

Chế độ `PER_METHOD` chỉ cô lập field instance của test class. Các loại trạng thái sau vẫn có thể tồn tại lâu hơn một test instance:

| Loại trạng thái | Phạm vi thường gặp | Rủi ro giữa các test |
|---|---|---|
| Field instance | Một test instance | Có thể chia sẻ với nhiều test method trong `PER_CLASS` |
| `static` field | Class được nạp trong classloader | Các instance của cùng class cùng nhìn thấy giá trị |
| Singleton Spring bean | Spring `ApplicationContext` | Nhiều test có thể dùng chung bean và mutable state |
| Cache hoặc system property | JVM hoặc application context | Test khác có thể đọc dữ liệu cũ hoặc cấu hình đã đổi |
| Database, file, broker | Hạ tầng bên ngoài | Dữ liệu có thể tồn tại qua nhiều class và lần chạy |
| Static mock hoặc global registry | JVM/classloader | Có thể ảnh hưởng các test chạy cùng tiến trình |

Ví dụ, `static List<String> events` vẫn là một list dùng chung ngay cả khi test class đang dùng `PER_METHOD`. Tạo test instance mới không tạo một classloader mới và cũng không xóa giá trị static.

Để quản lý trạng thái chia sẻ, hãy chọn biện pháp theo phạm vi:

- Field instance: tạo fixture mới trong constructor hoặc `@BeforeEach`.
- Static field: tránh mutable static nếu không cần thiết; nếu bắt buộc, reset rõ ràng trong setup và bảo đảm không chạy đồng thời khi đang thay đổi.
- Spring singleton: thiết kế bean stateless; nếu bean giữ trạng thái, cung cấp API reset dành cho test hoặc dùng context riêng khi thật sự cần.
- Database: dùng dữ liệu có định danh riêng, transaction rollback khi phù hợp, hoặc xóa dữ liệu theo fixture.
- File và tài nguyên hệ điều hành: tạo thư mục/file tạm riêng cho test và luôn đóng hoặc xóa bằng cleanup.
- System property: lưu giá trị cũ, thiết lập giá trị mới trong test và khôi phục trong `finally` hoặc callback cleanup.

Không coi `@AfterEach` là biện pháp duy nhất để khôi phục trạng thái. Nếu test thất bại giữa chừng, cleanup vẫn cần được viết sao cho an toàn và không phụ thuộc vào việc mọi bước setup đã hoàn tất. Với tài nguyên có thể tự đóng, ưu tiên `try-with-resources` hoặc extension quản lý tài nguyên.

## 7. Test instance lifecycle trong Spring Test

Spring TestContext Framework và JUnit Jupiter phối hợp qua `SpringExtension`. Hai hệ thống này quản lý những đối tượng khác nhau:

- JUnit quản lý test instance và các callback của Jupiter.
- Spring quản lý `ApplicationContext`, dependency injection, transaction test và các listener của TestContext Framework.

Ví dụ:

```java
@SpringBootTest
class CustomerServiceIntegrationTest {
    @Autowired
    private CustomerService customerService;

    @Test
    void createsCustomer() {
        // Kiểm tra service trong Spring context.
    }
}
```

Với mặc định `PER_METHOD`, JUnit tạo một `CustomerServiceIntegrationTest` mới cho mỗi test method. Spring có thể tái sử dụng `ApplicationContext` đã được cache giữa các test tương thích. Vì vậy, field `customerService` được inject vào test instance mới nhưng bean mà field tham chiếu có thể vẫn là cùng một singleton trong context được chia sẻ.

Điều này dẫn đến hai hệ quả:

1. Reset field của test class không reset trạng thái bên trong singleton bean.
2. Tạo test instance mới không đồng nghĩa tạo Spring context mới hoặc database mới.

Bean Spring thông thường nên stateless hoặc quản lý state theo request/session phù hợp. Nếu một singleton bean giữ mutable state, các test có thể tác động lẫn nhau dù đang dùng `PER_METHOD`. Hãy kiểm tra thiết kế bean và ranh giới dữ liệu trước khi dùng `@DirtiesContext`.

`@DirtiesContext` đánh dấu một `ApplicationContext` là không còn sử dụng được để Spring loại nó khỏi cache và tạo context mới khi cần. Annotation này hữu ích khi test thực sự làm thay đổi cấu hình hoặc trạng thái context theo cách không thể khôi phục. Nó tốn thời gian khởi tạo và không thay thế việc dọn dữ liệu database, file hoặc tài nguyên ngoài context.

### 7.1. Transaction test không phụ thuộc vào `PER_CLASS`

Khi dùng `@Transactional` trong Spring Test, transaction kiểm thử thường được quản lý theo từng test method và được rollback sau test theo cấu hình mặc định của TestContext Framework. Chọn `PER_CLASS` không biến các test method thành một transaction dùng chung.

Tương tự, một field giữ entity hoặc repository reference trên test instance không quyết định transaction boundary. Nếu test cần xác nhận dữ liệu đã commit, hãy thiết kế transaction rõ ràng và đọc dữ liệu từ transaction khác sau commit. Đừng suy luận commit/rollback từ việc JUnit dùng một hay nhiều test instance.

## 8. Chạy song song và trạng thái chia sẻ

JUnit Jupiter hỗ trợ thực thi test song song khi được bật trong cấu hình nền tảng. Mặc định, parallel execution không được bật chỉ vì test class dùng `PER_CLASS`; tuy nhiên, khi dự án bật chạy song song, nhiều test method có thể truy cập cùng một instance và cùng field mutable.

Ví dụ, với `PER_CLASS`:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class SequenceServiceTest {
    private final List<Long> generatedIds = new ArrayList<>();

    @Test
    void generatesFirstId() {
        generatedIds.add(1L);
    }

    @Test
    void generatesSecondId() {
        generatedIds.add(2L);
    }
}
```

Nếu hai test được chạy đồng thời, chúng cùng truy cập `generatedIds`. `ArrayList` không được thiết kế để nhiều luồng cùng sửa mà không đồng bộ. Ngay cả khi đổi sang collection thread-safe, test vẫn có thể phụ thuộc vào thứ tự hoặc số phần tử nếu không reset state.

Các lựa chọn xử lý gồm:

- Giữ test độc lập và tạo dữ liệu riêng cho mỗi test; đây thường là lựa chọn tốt nhất.
- Không dùng `PER_CLASS` nếu không cần chia sẻ instance.
- Dùng `@Execution(ExecutionMode.SAME_THREAD)` khi một class cần thực thi tuần tự vì lý do có thể giải thích được.
- Dùng `@ResourceLock` khi nhiều test phải truy cập cùng một tài nguyên có tên và cần phối hợp quyền truy cập.
- Tách tài nguyên bên ngoài theo test, chẳng hạn schema, key, thư mục hoặc queue riêng.

Ví dụ dùng resource lock cho system property dùng chung:

```java
@ResourceLock(value = "user.timezone", mode = ResourceAccessMode.READ_WRITE)
class TimeZoneConfigurationTest {
    @Test
    void changesAndRestoresDefaultTimeZone() {
        // Thay đổi cấu hình trong phạm vi được khóa và khôi phục sau test.
    }
}
```

Resource lock giúp JUnit phối hợp những test có khai báo cùng resource key. Nó không khóa code bên ngoài JUnit hoặc tiến trình khác, và không tự khôi phục giá trị đã thay đổi. Test vẫn phải cleanup đúng cách.

## 9. Cấu hình lifecycle mặc định cho cả dự án

Ngoài annotation trên từng class, JUnit Jupiter cho phép thay đổi lifecycle mặc định bằng cấu hình nền tảng trong file `junit-platform.properties` trên test classpath:

```properties
junit.jupiter.testinstance.lifecycle.default = per_class
```

File này thường được đặt tại `src/test/resources/junit-platform.properties`. Khi có cấu hình trên, các test class không khai báo `@TestInstance` sẽ dùng `PER_CLASS` thay cho mặc định `PER_METHOD`. Một class có `@TestInstance` tường minh vẫn thể hiện lựa chọn lifecycle của chính nó.

Thay đổi mặc định toàn dự án có thể ảnh hưởng nhiều test class cùng lúc. Nếu cấu hình chỉ tồn tại trong IDE hoặc chỉ có trên một module, test có thể chạy với lifecycle khác nhau giữa môi trường phát triển và CI. Vì vậy:

- Chỉ thay đổi mặc định toàn dự án khi nhóm thống nhất chính sách và hiểu ảnh hưởng đến toàn bộ test suite.
- Đưa file cấu hình vào source control để IDE, Gradle/Maven và CI dùng cùng một giá trị.
- Với class thực sự cần `PER_CLASS`, cân nhắc khai báo `@TestInstance(PER_CLASS)` trực tiếp để ý định dễ đọc tại nơi sử dụng.
- Khi nâng cấp hoặc di chuyển test, kiểm tra cả cấu hình engine và cấu hình classpath; không giả định lifecycle chỉ đến từ annotation.

Nếu dự án không có nhu cầu rõ ràng về một chính sách khác, giữ mặc định `PER_METHOD` giúp hành vi dễ dự đoán hơn cho người viết test mới.

## 10. Lựa chọn giữa `PER_METHOD` và `PER_CLASS`

| Tiêu chí | `PER_METHOD` | `PER_CLASS` |
|---|---|---|
| Số instance | Một instance cho mỗi test method | Một instance cho cả class |
| Field instance | Được khởi tạo lại giữa các method | Có thể giữ giá trị giữa các method |
| `@BeforeAll` / `@AfterAll` | Phải là `static` | Có thể là instance method |
| Constructor | Được gọi cho từng test method | Được gọi một lần cho class |
| Cách ly trạng thái instance | Tốt hơn theo mặc định | Cần reset hoặc thiết kế state có chủ đích |
| Chạy song song | Mỗi method có instance riêng, nhưng tài nguyên khác vẫn có thể chia sẻ | Các method có thể cùng truy cập một instance nếu chạy đồng thời |
| Trường hợp phù hợp | Hầu hết unit test và integration test thông thường | Fixture cấp class, tài nguyên dùng chung có reset rõ ràng, non-static factory |

Hãy chọn theo loại trạng thái thực sự cần chia sẻ. Nếu chỉ muốn tránh khởi tạo một object nhỏ vài lần, lợi ích thường không đáng để đưa thêm mutable state vào test class. Nếu cần khởi động một server hoặc tài nguyên cấp class, `PER_CLASS` có thể làm setup/cleanup rõ ràng hơn, miễn là từng test vẫn độc lập.

## 11. Các lỗi thường gặp và cách xử lý

### Cho rằng `PER_METHOD` làm mọi trạng thái được reset

Field instance được tách, nhưng static field, Spring singleton, database và file vẫn có thể tồn tại. Xác định phạm vi của dữ liệu trước khi quyết định cách reset.

### Dùng `PER_CLASS` rồi dựa vào thứ tự test

Test tạo dữ liệu trước và test đọc dữ liệu sau tạo ra phụ thuộc thứ tự. Mỗi test nên tự tạo fixture hoặc gọi factory chung để tạo trạng thái ban đầu.

### Dùng `@AfterEach` để che một setup không xác định

Nếu cleanup giả định một field đã được khởi tạo hoặc một bước đã hoàn tất, nó có thể gây lỗi thứ cấp và che lỗi gốc. Cleanup nên kiểm tra tài nguyên có tồn tại, an toàn khi gọi nhiều lần và luôn giải phóng phần đã tạo.

### Cho rằng `@BeforeAll` chạy trước khi có test instance ở mọi chế độ

Trong `PER_CLASS`, instance được tạo để các callback instance có thể chạy. `@BeforeAll` không `static` có thể truy cập field của instance. Trong `PER_METHOD`, `@BeforeAll` là `static` và không truy cập field instance.

### Nhầm test instance với Spring context

JUnit có thể tạo instance mới trong khi Spring tái sử dụng context. Reset field test class không reset singleton bean. Chỉ dùng `@DirtiesContext` khi context thực sự bị làm bẩn và không thể phục hồi bằng cleanup thông thường.

### Dùng dynamic test nhưng mong setup chạy cho từng dynamic node

Callback `@BeforeEach` / `@AfterEach` bao quanh factory method, không chạy riêng cho từng dynamic test. Tạo fixture trong từng executable hoặc chọn parameterized test cho kịch bản phù hợp.

### Chạy song song với mutable state dùng chung

`PER_CLASS` kết hợp với parallel execution có thể tạo race condition. Ưu tiên fixture riêng cho mỗi test; dùng resource lock hoặc thực thi tuần tự chỉ khi tài nguyên dùng chung là bắt buộc.

## 12. Quy trình thiết kế fixture theo vòng đời

Khi thiết kế một test class, hãy xác định rõ những câu hỏi sau:

1. Test có cần field instance để lưu fixture giữa các callback hay không?
2. Mỗi test method có thể tự tạo fixture mới với chi phí hợp lý không?
3. Có tài nguyên nào cần tạo một lần cho cả class không, và ai chịu trách nhiệm đóng tài nguyên đó?
4. Nếu dùng `PER_CLASS`, field mutable nào phải reset trước mỗi test?
5. Có trạng thái `static`, Spring singleton hoặc tài nguyên bên ngoài nào vẫn được chia sẻ dù dùng `PER_METHOD` không?
6. Dự án có bật parallel execution không, và những test nào cùng truy cập tài nguyên chung?
7. Callback cleanup có an toàn khi test thất bại giữa chừng không?

Một cấu trúc thường dễ duy trì là: `@BeforeAll` khởi tạo tài nguyên cấp class, `@BeforeEach` tạo fixture riêng, test method thực hiện đúng một kịch bản, `@AfterEach` dọn tài nguyên riêng và `@AfterAll` đóng tài nguyên cấp class. Với `PER_METHOD`, hai callback cấp class cần `static`; với `PER_CLASS`, chúng có thể là instance method.

Không phải class nào cũng cần đủ mọi callback. Hãy bỏ callback nếu không có công việc tương ứng. Setup quá tổng quát có thể khiến mỗi test nhận nhiều dữ liệu và dependency không dùng đến; fixture càng gần kịch bản càng dễ hiểu.

## 13. Ví dụ tổng hợp: tài nguyên cấp class và fixture từng test

Giả sử một test class cần dùng một HTTP stub server trong suốt class, nhưng mỗi test gửi request với dữ liệu riêng. Ta có thể dùng `PER_CLASS` để khởi động server một lần, sau đó reset mapping và request log trước từng test:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CatalogClientTest {
    private StubServer stubServer;
    private CatalogClient catalogClient;

    @BeforeAll
    void startStubServer() {
        stubServer = new StubServer();
        stubServer.start();
        catalogClient = new CatalogClient(stubServer.baseUrl());
    }

    @BeforeEach
    void resetStubState() {
        stubServer.resetMappings();
        stubServer.resetRequests();
    }

    @Test
    void readsCatalogItem() {
        stubServer.stubGet("/catalog/42", 200, """
                {"id": 42, "name": "Keyboard"}
                """);

        CatalogItem item = catalogClient.findById(42L);

        assertThat(item.name()).isEqualTo("Keyboard");
        assertThat(stubServer.receivedRequests()).hasSize(1);
    }

    @Test
    void mapsNotFoundResponse() {
        stubServer.stubGet("/catalog/404", 404, "{}");

        assertThatThrownBy(() -> catalogClient.findById(404L))
                .isInstanceOf(CatalogItemNotFoundException.class);
    }

    @AfterAll
    void stopStubServer() {
        if (stubServer != null) {
            stubServer.stop();
        }
    }
}
```

`StubServer` ở đây là kiểu minh họa cho một HTTP mock server mà dự án chọn sử dụng. Test dùng chung tiến trình server nhưng reset mapping và request log trước mỗi method. Khi chạy song song, cần bảo đảm server hỗ trợ phân vùng state theo test hoặc khóa quyền truy cập; nếu không, hãy chạy các method này tuần tự.

Ví dụ này cho thấy `PER_CLASS` không có nghĩa là mọi dữ liệu đều được giữ lại. Ta chủ động phân loại tài nguyên theo vòng đời: server tồn tại theo class, còn mapping và request log được reset theo từng test.

## 14. Nguyên tắc cần nhớ

- `PER_METHOD` là mặc định: mỗi test method có một test instance mới.
- `PER_CLASS` tạo một instance dùng chung cho class; field mutable có thể rò rỉ giữa các test.
- `@BeforeAll` và `@AfterAll` là `static` trong `PER_METHOD`, nhưng có thể là instance method trong `PER_CLASS`.
- `@BeforeEach` và `@AfterEach` quản lý fixture theo test method; dynamic test không có chu kỳ callback riêng cho từng dynamic node.
- Test instance không phải Spring `ApplicationContext`; tạo instance mới không reset singleton bean hoặc dữ liệu bên ngoài.
- Static state và tài nguyên ngoài JVM vẫn cần được quản lý độc lập với lifecycle của JUnit.
- Khi bật chạy song song, hãy kiểm soát mọi tài nguyên mutable dùng chung; fixture độc lập thường là cách đơn giản và đáng tin cậy nhất.

Vòng đời test instance là nền tảng để tổ chức trạng thái trong JUnit Jupiter. Chọn `PER_METHOD` cho tính độc lập mặc định, hoặc `PER_CLASS` khi có nhu cầu chia sẻ tài nguyên rõ ràng và có kế hoạch reset cụ thể. Khi mỗi test tự thiết lập điều kiện ban đầu và dọn đúng phần trạng thái mình sở hữu, test suite sẽ ổn định hơn khi chạy riêng, chạy toàn bộ hoặc chạy song song trong CI.
