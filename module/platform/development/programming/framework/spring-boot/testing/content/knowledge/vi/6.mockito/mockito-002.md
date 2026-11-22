# @Mock, @InjectMocks và khởi tạo qua MockitoExtension

## 1. Ba thành phần giải quyết ba nhiệm vụ khác nhau

Trong kiểm thử Java 17+/Spring Boot với JUnit Jupiter, ta thường muốn kiểm tra **logic thật của một service** nhưng không gọi database, mạng hoặc hệ thống gửi thông báo thật. Mockito giúp thay thế những **phụ thuộc bên ngoài service** bằng đối tượng giả (mock) có hành vi kiểm soát được.

Ba công cụ trọng tâm:

- **`@Mock`** (Mockito): tạo một mock cho dependency, ví dụ repository, client hoặc interface gửi thông báo. Ta quy định mock trả gì bằng stubbing và có thể kiểm tra nó đã nhận lời gọi nào.
- **`@InjectMocks`** (Mockito): tạo hoặc dùng **đối tượng thật đang được kiểm thử** (system under test, SUT) rồi cố gắng truyền những mock/spy đã khai báo vào dependency của nó. Annotation này **không biến SUT thành mock**.
- **`@ExtendWith(MockitoExtension.class)`** (JUnit Jupiter + Mockito): tích hợp Mockito vào vòng đời JUnit 5 để tự khởi tạo/tiêm các trường annotation của Mockito, quản lý phiên làm việc và kiểm tra stubbing theo strictness thích hợp.

Một cách đọc dễ nhớ:

~~~text
JUnit Jupiter chạy test
        |
        v
MockitoExtension khởi tạo các @Mock
        |
        v
@InjectMocks dựng/chuẩn bị service THẬT
        |                          |
        +---- StockPort mock ------+
        +---- ReceiptPort mock ----+
        |
        v
@Test gọi service thật
        |
        +--> mock trả kết quả đã stub
        +--> assertion kiểm tra output
        +--> verify kiểm tra tương tác cần thiết
~~~

Nếu thiếu `MockitoExtension` hoặc cơ chế khởi tạo Mockito tương đương, trường `@Mock` có thể chưa được gán, dẫn đến `null`. Nếu chỉ khai báo `@Mock` mà không cấu hình hành vi, đối tượng giả **không tự mô phỏng nghiệp vụ thật**.

## 2. @Mock: tạo dependency giả và điều khiển hành vi

Giả sử service gọi một interface truy cập kho:

~~~java
public interface StockPort {
    boolean reserve(String sku, int quantity);
}
~~~

Trong một lớp test có MockitoExtension:

~~~java
@Mock
StockPort stockPort;
~~~

Mockito tạo một đối tượng triển khai giả của `StockPort`. Khi test gọi `stockPort.reserve(...)`, mặc định **không có nghiệp vụ kho thật được chạy**. Với phương thức trả về `boolean`, mock chưa được stub trả `false` theo default answer thông thường. Với nhiều kiểu dữ liệu khác, giá trị mặc định có thể là `0`, `null`, collection rỗng hoặc giá trị thích hợp theo phiên bản/API.

Để mô tả một tình huống cụ thể, khai báo **stubbing**:

~~~java
when(stockPort.reserve("SKU-1", 2)).thenReturn(true);
~~~

Ý nghĩa: khi mock nhận đúng lời gọi `reserve("SKU-1", 2)`, nó trả `true`. Đây là **quy tắc của test**, không phải trạng thái tồn kho thật. Sau khi gọi SUT, có thể xác minh tương tác:

~~~java
verify(stockPort).reserve("SKU-1", 2);
~~~

`verify(...)` mặc định kiểm tra **một lần** đối với lời gọi khớp tham số; nếu hợp đồng yêu cầu số lần khác, sử dụng `times(n)` hoặc `never()`.

Bảng so sánh:

| Việc cần làm | Công cụ | Ví dụ |
| --- | --- | --- |
| Tạo dependency giả | `@Mock` | `@Mock StockPort stockPort;` |
| Quy định kết quả của mock | `when(...).thenReturn(...)` | Khi đủ hàng trả `true` |
| Gọi logic nghiệp vụ thật | Phương thức của SUT | `service.reserve(...)` |
| Kiểm tra kết quả trả về | JUnit assertion | `assertTrue(accepted)` |
| Kiểm tra dependency được gọi | Mockito `verify` | Gọi đúng SKU và số lượng |
| Kiểm tra dependency không được gọi | `verifyNoInteractions` hoặc `verify(..., never())` | Không gửi thông báo khi thiếu hàng |

**Không đồng nhất stubbing với assertion.** `when(...).thenReturn(...)` chỉ tạo điều kiện ban đầu. Test PASS hay FAIL phải do assertion, verification và các kiểm tra của runner quyết định.

## 3. @InjectMocks: SUT thật nhận các mock đã được tạo

Ví dụ một service nhận hai dependency qua constructor:

~~~java
public ReservationService(StockPort stockPort, ReceiptPort receiptPort) {
    this.stockPort = stockPort;
    this.receiptPort = receiptPort;
}
~~~

Trong test:

~~~java
@Mock
StockPort stockPort;

@Mock
ReceiptPort receiptPort;

@InjectMocks
ReservationService service;
~~~

Sau khi Mockito khởi tạo annotation, `service` là **instance của `ReservationService`**, còn `stockPort` và `receiptPort` trong service tham chiếu đến các mock tương ứng. Khi ta gọi `service.reserve(...)`, logic Java thật của service chạy; các cuộc gọi ra dependency được kiểm soát bởi Mockito.

### Mockito chọn cách injection như thế nào?

Theo mô tả của `@InjectMocks`, Mockito cố gắng sử dụng các chiến lược theo thứ tự:

1. **Constructor injection**: chọn constructor phù hợp theo quy tắc của Mockito (ưu tiên constructor lớn nhất) và tìm mock/spy tương ứng cho các tham số.
2. **Setter/property injection**: khi cần và áp dụng được, tìm setter/property theo kiểu; một số tình huống nhiều dependency cùng kiểu cần phân biệt thêm bằng tên.
3. **Field injection**: có thể tiêm vào field theo kiểu/tên nếu chiến lược trước không hoàn tất và trường hợp được hỗ trợ.

Nếu constructor injection tạo đối tượng thành công, Mockito không tiếp tục thử các chiến lược còn lại chỉ để tiêm thêm mọi field. **Mockito không cam kết phát hiện tất cả dependency bị thiếu.** Với một số constructor, dependency không tìm thấy có thể được truyền `null`; với dependency không mock được hoặc kiểu không hợp lệ, việc injection có thể không thực hiện được. Vì vậy:

- Ưu tiên **constructor injection** rõ ràng cho mã ứng dụng và đánh dấu dependency bắt buộc bằng `final`.
- Có thể dùng `Objects.requireNonNull(...)` trong constructor để lỗi thiếu dependency xuất hiện sớm.
- Đừng coi `@InjectMocks` là dependency injection framework đầy đủ hoặc bằng chứng mọi field đã được gán.
- Không kỳ vọng Mockito tự tạo một cây dependency lồng nhau: mỗi dependency cần mock/spy hoặc instance thật được cung cấp rõ ràng.

`@InjectMocks` **không phải `@Autowired`**. Nó không tìm Spring bean, không mở ApplicationContext, không đọc `application.yml` và không tự khởi động server hay kết nối database.

## 4. MockitoExtension: ai khởi tạo các annotation?

Với JUnit Jupiter, tích hợp được đăng ký bằng annotation:

~~~java
@ExtendWith(MockitoExtension.class)
class ReservationServiceTest {
    @Mock
    StockPort stockPort;

    @Mock
    ReceiptPort receiptPort;

    @InjectMocks
    ReservationService service;
}
~~~

JUnit gọi extension qua vòng đời kiểm thử. MockitoExtension thiết lập mock và injection cần thiết trước khi thân `@Test` chạy, phối hợp với `@BeforeEach` và kết thúc phiên Mockito sau mỗi lượt test. Khi đã đăng ký extension, **không cần** tự gọi `MockitoAnnotations.openMocks(this)` cho cùng lớp.

Các import đúng là:

~~~java
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
~~~

Ba annotation nằm ở các package khác nhau: `@ExtendWith` thuộc JUnit Jupiter; `@Mock` và `@InjectMocks` thuộc Mockito; `MockitoExtension` là cầu nối từ artifact `mockito-junit-jupiter`.

### Khác với JUnit 4

`@RunWith(MockitoJUnitRunner.class)` là cách dùng trong JUnit 4. Trong lớp `@Test` của JUnit Jupiter, dùng `@ExtendWith(MockitoExtension.class)`, không trộn `@RunWith`/`@Before`/`org.junit.Test` với `org.junit.jupiter.api.Test` nếu không có mục đích tương thích riêng.

## 5. Ví dụ hoàn chỉnh: test service nhận hai dependency

Giả sử chức năng **đặt trước hàng** có quy tắc:

- SKU phải có nội dung và số lượng phải dương.
- Service hỏi cổng kho có giữ được số lượng yêu cầu hay không.
- Nếu thiếu hàng, trả `false` và **không gửi** xác nhận.
- Nếu đủ hàng, gửi xác nhận cho đơn đặt và trả `true`.

Ta muốn kiểm thử đúng quy tắc đó **không truy cập kho hay gửi thông báo thật**.

### 5.1. Interface của dependency

**Tệp `src/main/java/com/example/testing/StockPort.java`:**

~~~java
package com.example.testing;

public interface StockPort {
    boolean reserve(String sku, int quantity);
}
~~~

**Tệp `src/main/java/com/example/testing/ReceiptPort.java`:**

~~~java
package com.example.testing;

public interface ReceiptPort {
    void send(String sku, int quantity);
}
~~~

Hai interface là ranh giới giữa nghiệp vụ và hệ thống bên ngoài. Trong sản phẩm thực tế, ta có thể dùng adapter Spring bean gọi database/HTTP/email; trong unit test này Mockito thay adapter bằng mock.

### 5.2. Lớp thật cần kiểm thử

**Tệp `src/main/java/com/example/testing/ReservationService.java`:**

~~~java
package com.example.testing;

import java.util.Objects;

public final class ReservationService {
    private final StockPort stockPort;
    private final ReceiptPort receiptPort;

    public ReservationService(StockPort stockPort, ReceiptPort receiptPort) {
        this.stockPort = Objects.requireNonNull(stockPort, "stockPort");
        this.receiptPort = Objects.requireNonNull(receiptPort, "receiptPort");
    }

    public boolean reserve(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        if (!stockPort.reserve(sku, quantity)) {
            return false;
        }

        receiptPort.send(sku, quantity);
        return true;
    }
}
~~~

Không cần annotation `@Service` để JUnit chạy ví dụ; đây là Java thuần. Trong Spring Boot thật có thể thêm `@Service` và để Spring quản lý instance khi ứng dụng chạy. Unit test chỉ quan tâm hành vi của lớp thật, nên không bắt buộc Spring context.

### 5.3. Lớp JUnit Jupiter dùng @Mock, @InjectMocks và MockitoExtension

**Tệp `src/test/java/com/example/testing/ReservationServiceTest.java`:**

~~~java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ReservationServiceTest {
    @Mock
    StockPort stockPort;

    @Mock
    ReceiptPort receiptPort;

    @InjectMocks
    ReservationService service;

    @Test
    void reserve_whenStockIsAvailable_returnsTrueAndSendsReceipt() {
        // Arrange: giả lập dependency chấp nhận giữ 2 sản phẩm.
        when(stockPort.reserve("SKU-1", 2)).thenReturn(true);

        // Act: gọi LOGIC THẬT của service.
        boolean accepted = service.reserve("SKU-1", 2);

        // Assert: kết quả và tương tác quan trọng.
        assertTrue(accepted);
        verify(stockPort).reserve("SKU-1", 2);
        verify(receiptPort).send("SKU-1", 2);
    }

    @Test
    void reserve_whenStockIsInsufficient_returnsFalseWithoutReceipt() {
        // Arrange: kho từ chối.
        when(stockPort.reserve("SKU-1", 2)).thenReturn(false);

        // Act
        boolean accepted = service.reserve("SKU-1", 2);

        // Assert: không gửi xác nhận khi không đủ hàng.
        assertFalse(accepted);
        verify(stockPort).reserve("SKU-1", 2);
        verifyNoInteractions(receiptPort);
    }

    @Test
    void reserve_whenQuantityIsZero_throwsBeforeCallingDependencies() {
        // Không stub: tham số được kiểm tra trước khi dùng dependency.
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve("SKU-1", 0)
        );

        assertEquals("Quantity must be positive", error.getMessage());
        verifyNoInteractions(stockPort, receiptPort);
    }

    @Test
    void reserve_whenSkuIsBlank_throwsBeforeCallingDependencies() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve("  ", 2)
        );

        assertEquals("SKU must not be blank", error.getMessage());
        verifyNoInteractions(stockPort, receiptPort);
    }
}
~~~

Mỗi test có tình huống riêng, mock mới theo phiên MockitoExtension, và chỉ stub lời gọi sẽ thực sự diễn ra. Trong kiểm thử đủ hàng, ta xác nhận **cả kết quả trả về và thông báo đã được yêu cầu gửi**. Trong kiểm thử thiếu hàng, `verifyNoInteractions(receiptPort)` bảo đảm service không yêu cầu gửi nhầm.

Bài test số lượng bằng 0 **không được** stub `stockPort.reserve(...)` vì service phải ném lỗi trước lời gọi đó. Nếu thêm stubbing không dùng đến, MockitoExtension với strict stubs có thể báo vấn đề.

### 5.4. Cấu hình Gradle và chạy

Trong dự án **Spring Boot 3.x sử dụng Gradle Groovy DSL** đã có plugin Spring Boot, repositories và Java 17+, phần dependency/test task liên quan là:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` trong Spring Boot 3.x thông dụng cung cấp JUnit Jupiter, Mockito core và tích hợp Mockito JUnit Jupiter. Nếu dự án Java **không dùng Spring Boot starter**, cần khai báo riêng JUnit Jupiter và `org.mockito:mockito-junit-jupiter` với các version tương thích, cùng dependency Mockito core nếu chưa được kéo vào.

Chạy từ thư mục có Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.testing.ReservationServiceTest"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.testing.ReservationServiceTest"
~~~

Với bốn tệp Java đúng như trên và dependency hợp lệ, bốn test sẽ đạt khi các assertion/verification đúng. Vì ví dụ không có `System.out.println`, **không có stdout cố định do code tự in**. Gradle hiển thị trạng thái task và kết quả tùy cấu hình log/IDE.

Trong test này, `@InjectMocks` tự tạo `ReservationService` thông qua constructor có hai tham số. Hai tham số nhận đúng mock của `StockPort` và `ReceiptPort` đã khai báo tại test class.

## 6. Khi nào dùng @InjectMocks, khi nào tự new đối tượng?

`@InjectMocks` giúp lớp test gọn khi dependency đơn giản. Tuy nhiên, cùng ví dụ có thể khởi tạo service bằng **constructor tường minh**:

~~~java
@ExtendWith(MockitoExtension.class)
class ReservationServiceExplicitTest {
    @Mock
    StockPort stockPort;

    @Mock
    ReceiptPort receiptPort;

    private ReservationService service;

    @BeforeEach
    void setUp() {
        service = new ReservationService(stockPort, receiptPort);
    }

    @Test
    void reserve_whenStockIsAvailable_returnsTrue() {
        when(stockPort.reserve("SKU-1", 1)).thenReturn(true);

        assertTrue(service.reserve("SKU-1", 1));
        verify(receiptPort).send("SKU-1", 1);
    }
}
~~~

Đây là **một lớp minh họa đặt trong cùng package `com.example.testing`**, cần import JUnit `@BeforeEach`, `@Test`, `@ExtendWith`, Mockito `@Mock`, `MockitoExtension`, và static imports `when`, `verify`, `assertTrue`. Khi thêm import đúng và lưu thành `ReservationServiceExplicitTest.java`, ví dụ có thể chạy trong cùng dự án.

Lúc JUnit gọi `@BeforeEach`, MockitoExtension đã khởi tạo các mock. Lệnh `new ReservationService(stockPort, receiptPort)` cho người đọc nhìn rõ tất cả dependency bắt buộc và tránh injection ngầm khi constructor phức tạp.

| Hoàn cảnh | Chọn cách nào? | Lý do |
| --- | --- | --- |
| Service nhỏ, dependency toàn là mock/spy rõ ràng | `@InjectMocks` | Giảm code setup mà vẫn chạy SUT thật |
| Constructor có nhiều dependency cùng kiểu, có config/value object thật | `new SUT(...)` trong `@BeforeEach` | Thấy rõ mock được gắn vào tham số nào |
| Cần tự kết hợp mock với object thật | Constructor tường minh | Tránh giả định Mockito tự tạo mọi object |
| Muốn Spring inject bean thật trong ApplicationContext | Spring TestContext, không dùng `@InjectMocks` như thay thế | Mockito không phải Spring DI |
| Test không có dependency | `new SUT()` trực tiếp | Không cần Mockito |

Không có yêu cầu phải dùng `@InjectMocks` cho mọi unit test. Chọn cách tạo SUT làm **ý định và dependency rõ nhất** cho người đọc.

## 7. MockitoExtension còn làm gì ngoài khởi tạo @Mock?

### 7.1. Vòng đời và kiểm tra strict stubbing

MockitoExtension mở phiên Mockito quanh một lượt test và hoàn tất phiên sau khi test kết thúc. Cấu hình mặc định ở các phiên bản Mockito phổ biến sử dụng `STRICT_STUBS` để phát hiện các stubbing không cần thiết hoặc không khớp.

Ví dụ sai thường gặp:

~~~java
@Test
void reserve_whenQuantityIsZero_throws() {
    when(stockPort.reserve("SKU-1", 2)).thenReturn(true); // Không dùng.

    assertThrows(
            IllegalArgumentException.class,
            () -> service.reserve("SKU-1", 0)
    );
}
~~~

Service ném lỗi trước khi gọi mock, vì vậy stub cho `reserve("SKU-1", 2)` **không dùng đến**. Trong strict mode, Mockito có thể báo `UnnecessaryStubbingException` tại bước kết thúc test. Cách sửa là **bỏ dòng stub thừa**, không tắt strictness theo phản xạ.

Nếu một stub thật sự có lý do hợp lệ để chỉ được dùng trong một số nhánh, Mockito có `lenient()` hoặc `@MockitoSettings(strictness = ...)`. Hãy giới hạn nới lỏng ở phạm vi cần thiết và hiểu lý do; trong unit test nhỏ, stub ngay tại từng test thường đơn giản hơn.

### 7.2. Mock ở tham số phương thức

Ngoài field, MockitoExtension có thể cung cấp một mock cho tham số của `@Test` hoặc một số lifecycle method:

~~~java
@Test
void canCreateLocalMock(@Mock StockPort localPort) {
    when(localPort.reserve("SKU-X", 1)).thenReturn(true);
    assertTrue(localPort.reserve("SKU-X", 1));
}
~~~

Đây là **đoạn phương thức trong test class đã có `@ExtendWith(MockitoExtension.class)`**; cần import `@Test`, `@Mock`, `when` và `assertTrue`. Mock `localPort` được cấp cho invocation đó, không tự động đồng nhất với field `@Mock StockPort stockPort` và cũng không có nghĩa `@InjectMocks` sẽ tiêm mock tham số này vào service đã tạo.

Dùng mock tham số cho các dependency chỉ một test cần. Với mock phải được tiêm vào `@InjectMocks`, field `@Mock` ở cấp lớp như ví dụ chính giúp quan hệ injection rõ ràng hơn.

## 8. Vì sao @Mock không phải @MockitoBean của Spring?

Trong một **unit test**, ta dùng Mockito tạo service thật bằng constructor và truyền mock vào. Không có Spring context:

~~~text
JUnit + MockitoExtension
   -> @Mock StockPort
   -> @InjectMocks ReservationService
   -> gọi business method trực tiếp
~~~

Trong một **Spring integration/slice test**, Spring tạo ApplicationContext và quyết định bean nào được inject. Nếu cần thay một dependency bean trong context, dùng cơ chế override bean dành cho Spring Test (ví dụ `@MockitoBean` trên các phiên bản Spring Framework/Spring Boot hỗ trợ; dự án cũ có thể dùng `@MockBean` của Spring Boot). Đó là **phạm vi khác** với `@Mock` thuần Mockito.

| `@Mock` + `@InjectMocks` | Bean mock trong Spring TestContext |
| --- | --- |
| Tạo mock thuộc đối tượng test; SUT do Mockito/test tạo | Thay hoặc đăng ký mock tại mức ApplicationContext |
| Không cần chạy Spring Boot | Cần cơ chế kiểm thử Spring để tạo context |
| Hợp với unit test của business logic | Hợp với web slice hoặc integration test cần bean wiring |
| Không tự hoạt động với `@Autowired` | Spring quản lý injection vào các bean/test liên quan |

**Bẫy phổ biến:** viết `@SpringBootTest`, dùng field `@Mock SomeRepository` và tưởng rằng bean `SomeRepository` do Spring inject vào một service thật cũng bị thay thế. Annotation `@Mock` thuần **không tự thay Spring bean**. Tùy mục tiêu, hãy chọn unit test với constructor injection tường minh hoặc dùng bean override của Spring Test.

Cũng không cần thêm `@SpringBootTest` chỉ vì class ứng dụng có `@Service`. Nếu logic chỉ dựa trên mock dependency, JUnit + MockitoExtension thường đủ; test nhanh hơn vì không dựng Spring context.

## 9. Những giới hạn quan trọng của @InjectMocks

### Thiếu dependency không nhất thiết gây lỗi injection rõ ràng

Ví dụ:

~~~java
@Mock
StockPort stockPort;

@InjectMocks
ReservationService service; // Thiếu ReceiptPort mock.
~~~

Trong một số trường hợp, Mockito có thể cố truyền `null` cho dependency không tìm thấy và constructor của `ReservationService` ở ví dụ chính sẽ phát hiện bằng `Objects.requireNonNull`. Với lớp khác không kiểm tra `null`, lỗi có thể chỉ xuất hiện khi chạy nghiệp vụ. Vì vậy, đừng cho rằng thấy `service != null` là đã wiring đầy đủ.

### Không inject như Spring

Mockito không đọc bean qualifier, cấu hình Spring, transaction proxy, security context hay các dependency mà container Spring quản lý. `@InjectMocks` làm việc trên đối tượng và mock/spy đã khai báo, theo chiến lược injection của Mockito; nó **không phải bản sao `@Autowired`**.

### Không tự tạo mọi dependency hoặc cấu trúc lồng nhau

Nếu service A phụ thuộc service B, còn B phụ thuộc C, không thể mong một `@InjectMocks A` tự khám phá và tạo đủ B/C một cách giống Spring. Hãy khai báo mock cần thiết, tạo đối tượng thật tường minh hoặc chuyển sang Spring context test nếu đang kiểm thử wiring thực tế.

### Dependency trùng kiểu dễ mơ hồ

Nếu constructor có hai đối số cùng một interface, việc suy luận mock đúng vị trí có thể khó đọc và dễ sai. Constructor tường minh trong `@BeforeEach` cho biết chính xác mock nào được truyền cho tham số nào. Với property/field injection, Mockito có quy tắc so khớp theo kiểu và tên trong một số trường hợp, nhưng không nên dựa vào quy tắc ngầm nếu mã test trở nên mơ hồ.

### Mock đối tượng cần kiểm thử là sai mục tiêu thường gặp

~~~java
@Mock
ReservationService service;
~~~

Cách này tạo **service giả**; `service.reserve(...)` không chạy logic thật, trừ khi dùng kỹ thuật spy/partial mock có chủ đích. Nếu mục tiêu là unit test logic của `ReservationService`, dùng đối tượng thật (`@InjectMocks` hoặc `new`) và **mock các dependency của nó**.

## 10. Gỡ lỗi khi test Mockito không hoạt động như mong đợi

| Biểu hiện | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| `NullPointerException` ở field `@Mock` trong test | Chưa khởi tạo Mockito annotations, thiếu `MockitoExtension` | Thêm `@ExtendWith(MockitoExtension.class)` và đúng import |
| SUT `null` hoặc constructor báo thiếu dependency | `@InjectMocks` không tạo/inject được đủ mock, thiếu mock hoặc constructor không tương thích | Kiểm tra constructor và khai báo mock; cân nhắc `new` tường minh |
| Unit test trả `false` dù kỳ vọng `true` | Mock `boolean` chưa được stub nên trả default `false` | Thêm `when(...).thenReturn(true)` đúng tham số |
| `UnnecessaryStubbingException` | Stub không được dùng trong lượt test với strict stubs | Bỏ stub thừa, đặt stubbing sát ca thực sự cần |
| `Wanted but not invoked` | `verify` không tìm thấy lời gọi phù hợp | Kiểm tra đường đi nghiệp vụ và argument thực tế |
| `MissingMethodInvocationException` khi stubbing | Dùng `when(...)` trên object không phải mock hoặc expression không hợp lệ | Chỉ stub dependency mock được Mockito quản lý |
| Dùng `@Mock` mà bean Spring thật vẫn được gọi | Mock Mockito chưa thay Spring bean trong context | Dùng bean override phù hợp hoặc unit test ngoài context |
| Test chạy riêng PASS nhưng chạy suite FAIL | State dùng chung, dữ liệu ngoài test hoặc phụ thuộc thứ tự | Tách fixture, tránh static mutable state và tác động ngoài |
| Test chỉ `verify` nhiều lời gọi nội bộ, dễ gãy khi refactor | Kiểm tra implementation thay vì hợp đồng | Assert đầu ra và chỉ verify interaction quan trọng |

### Nếu không dùng MockitoExtension

Mockito hỗ trợ `MockitoAnnotations.openMocks(this)` để khởi tạo annotation thủ công, ví dụ đặt ở `@BeforeEach` và đóng handle trả về ở `@AfterEach`. Cách đó có thể phù hợp khi tích hợp đặc biệt, nhưng cần quản lý resource đóng đúng vòng đời. **Không đồng thời bật MockitoExtension và khởi tạo bằng `openMocks` cho cùng annotation** vì sẽ tạo phiên/mocks chồng lấn, gây khó xác định trạng thái.

Dùng `Mockito.mock(StockPort.class)` rồi `new ReservationService(...)` cũng hợp lệ khi không muốn annotation; quan trọng là mock được tạo trước khi truyền cho SUT.

## 11. Quy trình thực hành và checklist

Khi thiết kế một ca unit test có dependency:

1. **Xác định SUT thật:** service/class nào chứa quyết định nghiệp vụ đang được kiểm tra?
2. **Liệt kê dependency ra ngoài:** repository, HTTP client, notifier... Chỉ mock những gì test không cần chạy thật.
3. **Khởi tạo:** `@ExtendWith(MockitoExtension.class)`, `@Mock` cho dependency, `@InjectMocks` cho SUT hoặc `new` tường minh.
4. **Arrange:** đặt dữ liệu và stub đúng lời gọi sẽ diễn ra với `when(...).thenReturn(...)`.
5. **Act:** gọi phương thức **trên SUT thật**.
6. **Assert:** kiểm tra kết quả/exception, rồi chỉ verify những tương tác quan trọng với hợp đồng.
7. **Chạy độc lập:** test không phụ thuộc thứ tự hoặc state từ test trước; loại bỏ stubbing không dùng đến.

Checklist trước khi chốt:

- [ ] Dùng đúng `org.junit.jupiter.api.Test`, `org.mockito.Mock`, `org.mockito.InjectMocks` và `org.mockito.junit.jupiter.MockitoExtension`.
- [ ] `@ExtendWith(MockitoExtension.class)` thực sự có hiệu lực hoặc đã có cơ chế khởi tạo Mockito tương đương.
- [ ] Đối tượng `@InjectMocks` là SUT **thật**, không phải mock của chính SUT.
- [ ] Mọi dependency bắt buộc đều có mock/instance phù hợp.
- [ ] Stub đúng tham số và chỉ những lần gọi cần thiết cho tình huống.
- [ ] Kiểm tra kết quả bằng assertion, không chỉ nhìn thấy code chạy hết.
- [ ] Dùng `verify` cho hệ quả/tương tác quan trọng, không khóa chặt chi tiết cài đặt vụn vặt.
- [ ] Không nhầm mock Mockito với bean mock trong Spring ApplicationContext.
- [ ] Test chạy độc lập, không gọi DB/email/API thật trừ khi đó là mục tiêu của loại test đã chọn.

**Ghi nhớ:** `@Mock` tạo **dependency giả**; `@InjectMocks` dựng hoặc chuẩn bị **đối tượng nghiệp vụ thật** và đưa mock vào; `MockitoExtension` nối quá trình đó với vòng đời **JUnit Jupiter**. Stubbing đặt điều kiện, lời gọi SUT thực thi nghiệp vụ, còn assertion/verification chứng minh kết quả.

### Tài liệu tham khảo

- [Mockito — @InjectMocks Javadoc](https://www.javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/InjectMocks.html)
- [Mockito — MockitoExtension Javadoc](https://www.javadoc.io/doc/org.mockito/mockito-junit-jupiter/latest/org.mockito.junit.jupiter/org/mockito/junit/jupiter/MockitoExtension.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/)