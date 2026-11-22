# Mockito: giới hạn over-mocking và kiểm thử chỉ lặp lại mã hiện thực

## Mục tiêu

Trong Spring Boot, Mockito giúp kiểm thử một thành phần mà không cần gọi cơ sở dữ liệu, HTTP service hay hệ thống gửi thông báo thật. Nhưng mock quá nhiều có thể làm bài test chỉ chứng minh rằng **một mock trả đúng giá trị ta vừa lập trình cho nó trả**, hoặc chỉ khẳng định rằng implementation đã gọi những phương thức nội bộ nhất định. Khi thay đổi thiết kế mà hành vi vẫn đúng, test như vậy dễ vỡ; khi có lỗi nghiệp vụ, nó lại có thể tiếp tục pass.

Sau bài này, bạn có thể:

- Phân biệt **test hành vi quan sát được** với **test cấu trúc lời gọi nội bộ**.
- Nhận diện over-mocking và tình huống test chỉ lặp lại cách cài đặt hoặc công thức sai của sản phẩm.
- Xác định khi nào mock là đúng: ở ranh giới I/O, collaborator khó kiểm soát, tác động bên ngoài hoặc tương tác thật sự là một phần hợp đồng.
- Dùng Mockito cùng JUnit Jupiter để kiểm giá trị trả về và tác động lưu dữ liệu một cách có ý nghĩa.
- Thiết kế bộ test gồm unit test với **logic thật** và test tích hợp cho những hành vi mà mock không thể chứng minh.
- Sử dụng câu hỏi “test nào sẽ fail khi có lỗi nghiệp vụ nhưng vẫn pass khi refactor?” để xem lại chất lượng assertion.

**Ý chính:** Mock là một công cụ kiểm soát dependency. Chất lượng test phụ thuộc vào **hợp đồng được kiểm và bằng chứng assertion cung cấp**, không phụ thuộc việc tạo được bao nhiêu `@Mock`, `when` hay `verify`.

## 1. Mock, stub, fake, spy và system under test

**SUT (System Under Test)** là thành phần đang được kiểm. **Collaborator** là đối tượng mà SUT sử dụng. Ta có thể kiểm một service với collaborator thật, fake hoặc mock tùy mục tiêu. “Mock” trong Mockito có thể vừa được **stub** để trả dữ liệu, vừa được **verify** để kiểm tương tác.

| Khái niệm | Vai trò chính | Ví dụ |
| --- | --- | --- |
| **SUT thật** | Chạy logic cần được xác minh | `PriceCalculator`, `OrderService` |
| **Stub** | Cung cấp response có kiểm soát | Repository được cấu hình trả một `Customer` cụ thể |
| **Mock** | Đối tượng giả được tạo bởi Mockito, có thể stub và verify | `@Mock OrderRepository repository` |
| **Fake** | Cài đặt giản lược nhưng có hành vi thực | `InMemoryOrderRepository` giữ đơn hàng trong danh sách |
| **Spy** | Bọc đối tượng thật, cho phép theo dõi hoặc thay đổi một phần lời gọi | `spy(realService)` trong trường hợp đặc biệt |

Trong Mockito, `when(repository.findById(42L)).thenReturn(Optional.of(customer))` là **stubbing** một mock. `verify(repository).save(order)` là **kiểm tương tác**. Cả hai đều có thể hữu ích, nhưng không tự thay thế assertion về dữ liệu, trạng thái và quy tắc nghiệp vụ.

Một nguyên tắc thực dụng:

> **Chạy logic thật khi mục tiêu là kiểm logic đó; thay thế ranh giới không cần chạy thật khi mục tiêu là kiểm cách SUT sử dụng ranh giới.**

Ví dụ, unit test tính giá không cần mock phép nhân, điều kiện giảm giá hay một `record` chỉ giữ dữ liệu. Nhưng test thao tác gửi email có thể cần mock `MailGateway` để không gửi email thật, rồi verify đúng thông điệp được gửi. Test service lưu đơn hàng có thể mock repository để kiểm lời gọi lưu; muốn khẳng định SQL, mapping JPA hoặc transaction thật hoạt động thì cần integration test thích hợp.

## 2. “Over-mocking” là gì?

**Over-mocking** xảy ra khi test dùng mock tới mức thay thế logic cốt lõi cần kiểm hoặc ràng buộc quá nhiều chi tiết nội bộ. Không thể định nghĩa bằng một ngưỡng “trên ba mock là sai”; điều quyết định là **mock thay thế phần nào và assertion chứng minh được gì**.

Một vài dấu hiệu:

1. **Mock đối tượng chỉ có logic thuần túy** như calculator, validator, mapper không I/O, value object; stub kết quả của chính phép tính lẽ ra cần chạy thật.
2. **Stub từng bước trung gian** và `verify` đúng thứ tự các lời gọi private/implementation-level; test fail khi refactor dù kết quả công khai không đổi.
3. **Lặp lại giả định của implementation trong expected** (cùng điều kiện nhầm lẫn, cùng công thức sai), khiến test và mã sản phẩm cùng trả một kết quả sai.
4. Có nhiều dòng `when(...).thenReturn(...)` nhưng rất ít assertion về output, trạng thái hoặc tác động có ý nghĩa; test chủ yếu xác nhận các mock hoạt động như cấu hình.
5. Dùng `verifyNoMoreInteractions(...)` hoặc `InOrder` cho mọi collaborator chỉ để bắt implementation không đổi, dù **thứ tự và số lượng lời gọi không được mô tả trong hợp đồng**.
6. Mọi test cấp controller/service đều mock các tầng bên dưới; không có test nào chạy logic thật kết hợp với persistence/serialization quan trọng.

Những dấu hiệu này là **câu hỏi để xem xét**, không phải lệnh cấm tuyệt đối. Nếu hợp đồng nói “một giao dịch chỉ được gửi yêu cầu thanh toán đúng một lần”, `times(1)` là assertion nghiệp vụ quan trọng. Nếu thứ tự “ghi audit trước khi phát sự kiện” là yêu cầu, `InOrder` có thể hợp lý. Nếu không có yêu cầu đó, việc kiểm số lần gọi mọi helper chỉ tăng chi phí refactor.

## 3. Hai kiểu bài test dễ tạo cảm giác an toàn giả

### 3.1. Stub luôn kết quả của logic đang cần kiểm

Giả sử quy tắc là “mua 2 sản phẩm, mỗi sản phẩm 120 đơn vị, thành tiền 240”. Một test có thể viết:

~~~java
// MẪU CẦN XEM LẠI: snippet minh họa, chưa phải class chạy độc lập.
PriceCalculator calculator = mock(PriceCalculator.class);
OrderRepository repository = mock(OrderRepository.class);

when(calculator.total(2, 120)).thenReturn(240);

OrderService service = new OrderService(calculator, repository);
Order result = service.place("BOOK", 2, 120);

assertEquals(240, result.amount());
verify(calculator).total(2, 120);
~~~

Bài test trên chạy **`OrderService` thật**, nhưng **`PriceCalculator.total` hoàn toàn không chạy**. Nếu phép tính thật vô tình đổi từ `quantity * unitPrice` thành `quantity + unitPrice`, bài test vẫn có thể pass, vì `calculator` bị mock trả 240. `verify(calculator).total(2, 120)` chỉ khẳng định lời gọi xảy ra, **không khẳng định phép tính cho kết quả đúng**.

Nó vẫn có một mục đích hợp lệ nếu mục tiêu giới hạn là “`OrderService` truyền đúng dữ liệu cho `PriceCalculator`”; nhưng đừng ghi nó là bằng chứng đã kiểm **quy tắc tính tiền**. Để kiểm quy tắc đó, dùng `new PriceCalculator()` thật và assert với con số kỳ vọng có nguồn gốc từ yêu cầu.

### 3.2. Tính expected bằng cùng công thức sai với production

Giả sử nghiệp vụ quy định **đơn hàng từ 500 trở lên được miễn phí vận chuyển**, các đơn nhỏ hơn chịu phí 30. Nếu cả production lẫn test dùng nhầm `> 500` thay vì `>= 500`, test sau sẽ không phát hiện lỗi ở ranh giới 500:

~~~java
// MẪU SAI về thiết kế oracle; giả sử service.shippingFee tồn tại.
int subtotal = 500;
int expected = subtotal > 500 ? 0 : 30; // sao chép điều kiện sai
assertEquals(expected, service.shippingFee(subtotal));
~~~

Nếu SUT cũng dùng sai toán tử `>`, expected bằng 30 và actual bằng 30, test pass dù **yêu cầu đúng phải là 0**. Đây là hiện tượng **kiểm thử chỉ lặp lại mã hiện thực**: test không có nguồn chân lý độc lập.

Cách sửa là chọn giá trị và expected từ đặc tả:

~~~java
// Minh họa: expected đến từ quy tắc “từ 500 trở lên”.
assertEquals(0, service.shippingFee(500));
assertEquals(30, service.shippingFee(499));
assertEquals(0, service.shippingFee(501));
~~~

Các snippet `shippingFee` minh họa quy tắc biên; chương trình runnable của bài nằm ở mục 5–6 và sử dụng bài toán tính tiền đơn giản hơn. Việc tự tính expected bằng code không **luôn sai**, nhưng cần chứng minh expected được suy ra từ đặc tả **độc lập** với đường đi của SUT. Với phép toán có logic nhiều bước, nên dùng bảng ví dụ đã được kiểm duyệt hoặc một reference implementation độc lập thay vì copy thuật toán hiện tại vào test.

### 3.3. Verify chi tiết triển khai thay vì kết quả bên ngoài

Ví dụ một service chia việc thành `normalize()`, `calculate()`, `map()` rồi trả `Order`. Nếu test buộc gọi ba helper theo thứ tự chỉ vì code hiện tại làm như vậy, việc gộp hai helper hoặc cache kết quả có thể làm test fail mặc dù API vẫn đúng. Hợp đồng tốt hơn thường là “đúng amount, đúng đơn hàng được lưu, dữ liệu lỗi không được lưu”.

**Tác động nào là hợp đồng?** Đối với repository trong một use case “đặt đơn hàng”, **phải lưu đơn** có thể là hợp đồng của service. Khi đó `verify(repository).save(...)` là assertion đúng đắn. Ngược lại, “service phải gọi `calculator.total` đúng một lần” thường chỉ là chi tiết triển khai, trừ khi bài toán có yêu cầu về cost, idempotency, side effect hoặc sự nhất quán mà số lần gọi ảnh hưởng tới bên ngoài.

## 4. Chọn ranh giới mock có chủ đích

Đặt câu hỏi về mỗi dependency trước khi mock:

| Dependency | Thường chọn | Vì sao |
| --- | --- | --- |
| `PriceCalculator`/`DiscountPolicy` thuần Java | **Chạy thật** | Đây là logic cần bảo vệ; chạy nhanh và xác định |
| `Order` record, value object | **Chạy thật** | Dữ liệu đơn giản, không có I/O |
| `OrderRepository` dùng DB thật | **Mock trong unit test service** hoặc fake phù hợp | Cô lập I/O và kiểm ý định lưu; cần integration test để chứng minh lưu thật |
| HTTP client gọi nhà cung cấp ngoài | **Stub/mock ở adapter boundary** | Tránh mạng thật, phí dịch vụ và test thiếu ổn định |
| `Clock` | **`Clock.fixed(...)` thật** | Điều khiển thời gian không cần Mockito |
| `Random`/ID generator có thể tiêm vào | **Fake hoặc stub có seed/ID xác định** | Tránh dữ liệu ngẫu nhiên làm test chập chờn |
| Spring MVC serialization và HTTP mapping | **MockMvc với controller/serializer thật** | Kiểm status, JSON body, validation và mapping |
| JPA mapping/SQL/transaction | **DB test phù hợp** | Mock repository không chạy SQL hoặc transaction |

Không cần mock mọi collaborator chỉ vì nó nằm ngoài class SUT. Các đối tượng thuần Java và dependency chạy nhanh có thể dùng thật để giảm setup, giúp test đi qua nhiều nhánh nghiệp vụ quan trọng hơn.

**Fakes và mocks giải đáp câu hỏi khác nhau.** Một fake repository in-memory có thể kiểm lưu rồi đọc lại ở mức service nhưng không chứng minh JPA mapping, SQL constraint hay transaction của database thật. Một mock có thể kiểm “repository.save được gọi với order nào” nhưng không chứng minh dữ liệu tồn tại sau commit. Để xác minh tính đúng của persistence adapter, dùng integration test gắn với hạ tầng gần môi trường thật.

## 5. Ví dụ Java 17 + JUnit Jupiter + Mockito: chỉ mock ranh giới lưu trữ

Thiết kế một bài toán nhỏ:

- Sản phẩm có `sku`, `quantity` (số lượng nguyên dương) và `unitPrice` (đơn giá không âm).
- Thành tiền **`quantity × unitPrice`**; nếu phép nhân tràn phạm vi `int` phải từ chối kết quả, không im lặng tràn số.
- `OrderService.place(...)` trả về đơn hàng đúng và yêu cầu repository lưu đơn đó.
- `sku` trống, số lượng không hợp lệ hoặc đơn giá âm phải bị từ chối; dữ liệu không hợp lệ **không được lưu**.

Ở đây, **`PriceCalculator` là logic thật cần kiểm**; `OrderRepository` là ranh giới I/O được thay bằng mock ở unit test. Ta không cần khởi động Spring ApplicationContext để kiểm một service Java thuần.

### 5.1. Cấu trúc project

~~~text
mock-boundary-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/com/example/testing/
    │   ├── PriceCalculator.java
    │   ├── Order.java
    │   ├── OrderRepository.java
    │   └── OrderService.java
    └── test/java/com/example/testing/
        ├── PriceCalculatorTest.java
        └── OrderServiceTest.java
~~~

Ví dụ không cần module Spring Boot thực thi, nên dùng Java plugin cho dễ thấy giới hạn mock; **cùng pattern áp dụng trong project Spring Boot**. Nếu đã có Wrapper, sử dụng Wrapper của repo. Nếu tạo project mới, cần tạo Wrapper bằng Gradle phiên bản phù hợp, sau đó commit các tệp Wrapper.

**`settings.gradle`**

~~~groovy
rootProject.name = 'mock-boundary-demo'
~~~

**`build.gradle`** dùng Gradle Groovy DSL và JUnit 5.10.2/Mockito 5.12.0 để ví dụ có phiên bản minh họa cụ thể, không ràng buộc dự án Spring Boot khác phải dùng những số phiên bản này:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'org.mockito:mockito-junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`mockito-junit-jupiter` mang Mockito integration cho Jupiter và phụ thuộc Mockito core. `@ExtendWith(MockitoExtension.class)` cho phép JUnit tạo mock riêng theo từng test, đồng thời hỗ trợ kiểm những stubbing không cần thiết. `useJUnitPlatform()` cho Gradle chạy test qua JUnit Platform. Nếu project **đã có** `spring-boot-starter-test`, kiểm dependency sẵn có trước khi thêm trực tiếp JUnit/Mockito; thường starter đã mang theo các thư viện test phù hợp theo bộ phiên bản Spring Boot quản lý.

### 5.2. Mã sản phẩm: logic thật và một output port

**`src/main/java/com/example/testing/PriceCalculator.java`**

~~~java
package com.example.testing;

public final class PriceCalculator {

    public int total(int quantity, int unitPrice) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        if (unitPrice < 0) {
            throw new IllegalArgumentException(
                    "unitPrice must not be negative");
        }

        return Math.multiplyExact(quantity, unitPrice);
    }
}
~~~

`Math.multiplyExact(int, int)` ném `ArithmeticException` khi tràn `int`. Đây là hành vi được chọn rõ ràng trong yêu cầu minh họa: test sẽ bảo vệ việc không lặng lẽ trả số sai do overflow. Với hệ thống tiền tệ thực, cần quy định đơn vị và kiểu số phù hợp, có thể là `BigDecimal` hoặc số nguyên theo đơn vị nhỏ nhất thay vì dùng `int` đơn giản.

**`src/main/java/com/example/testing/Order.java`**

~~~java
package com.example.testing;

public record Order(String sku, int quantity, int amount) {
}
~~~

**`src/main/java/com/example/testing/OrderRepository.java`**

~~~java
package com.example.testing;

public interface OrderRepository {
    void save(Order order);
}
~~~

`OrderRepository` là một interface minh họa đại diện cho cổng lưu trữ. Nó không tự là Spring Data JPA repository và chưa có implementation thật; đây là thiết kế có chủ đích để test service độc lập với hạ tầng. Trong Spring Boot, adapter thực có thể bọc `JpaRepository`, còn unit test chỉ quan tâm hợp đồng của output port.

**`src/main/java/com/example/testing/OrderService.java`**

~~~java
package com.example.testing;

import java.util.Objects;

public final class OrderService {

    private final PriceCalculator calculator;
    private final OrderRepository repository;

    public OrderService(
            PriceCalculator calculator,
            OrderRepository repository) {
        this.calculator = Objects.requireNonNull(calculator);
        this.repository = Objects.requireNonNull(repository);
    }

    public Order place(String sku, int quantity, int unitPrice) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank");
        }

        int amount = calculator.total(quantity, unitPrice);
        Order order = new Order(sku, quantity, amount);
        repository.save(order);
        return order;
    }
}
~~~

Flow quan sát được: kiểm SKU; tính amount bằng calculator thật; tạo `Order`; gọi port `save`; trả lại đơn hàng. Nếu input không hợp lệ, method ném exception trước khi gọi `save`. Vì implementation này không tự truy cập database, test chưa cần Spring context hay transaction.

### 5.3. Test logic giá với object thật

**`src/test/java/com/example/testing/PriceCalculatorTest.java`**

~~~java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorTest {

    private final PriceCalculator calculator = new PriceCalculator();

    @Test
    void multipliesQuantityByUnitPrice() {
        // Arrange: ví dụ nghiệp vụ đã xác định
        int quantity = 2;
        int unitPrice = 120;

        // Act
        int amount = calculator.total(quantity, unitPrice);

        // Assert: expected độc lập từ đặc tả
        assertEquals(240, amount);
    }

    @Test
    void zeroUnitPriceProducesZeroAmount() {
        assertEquals(0, calculator.total(3, 0));
    }

    @ParameterizedTest
    @ValueSource(ints = {0, -1})
    void rejectsNonPositiveQuantity(int quantity) {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.total(quantity, 120));
    }

    @Test
    void rejectsNegativeUnitPrice() {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.total(2, -1));
    }

    @Test
    void rejectsIntegerOverflow() {
        assertThrows(ArithmeticException.class,
                () -> calculator.total(Integer.MAX_VALUE, 2));
    }
}
~~~

Test không có `@Mock`, vì đang kiểm trực tiếp **logic tính toán**. Hai ca ở `@ValueSource` tạo hai invocation riêng; các method `@Test` còn lại tạo bốn invocation. Tổng class này có **6 lượt test**. Nếu đổi phép nhân thành phép cộng, ca `multipliesQuantityByUnitPrice` sẽ fail. Nếu bỏ check `quantity<=0`, test sẽ fail. Nếu phép nhân tràn và code dùng toán tử `*` thuần, test overflow sẽ fail. Đây là các **bằng chứng về quy tắc**, không phải bằng chứng về số lần gọi helper.

Lưu ý: `assertEquals(240, amount)` là một **giá trị mong đợi đã định trước**, không gọi lại `calculator.total` để tính expected và cũng không dùng một mock trả 240. Các giá trị biên xuất phát từ yêu cầu đã nêu ở đầu bài.

### 5.4. Test service với mock duy nhất ở output port

**`src/test/java/com/example/testing/OrderServiceTest.java`**

~~~java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository repository;

    private final PriceCalculator calculator = new PriceCalculator();

    @Test
    void placeReturnsCorrectOrderAndRequestsPersistence() {
        // Arrange: service thật, calculator thật, repository mock
        OrderService service = new OrderService(calculator, repository);

        // Act
        Order result = service.place("BOOK", 2, 120);

        // Assert: kết quả nghiệp vụ quan sát được
        assertEquals(new Order("BOOK", 2, 240), result);

        // Assert: lưu chính đơn hàng vừa tạo là hợp đồng của use case
        ArgumentCaptor<Order> captured =
                ArgumentCaptor.forClass(Order.class);
        verify(repository).save(captured.capture());
        assertEquals(result, captured.getValue());
    }

    @Test
    void invalidQuantityDoesNotSaveAnOrder() {
        OrderService service = new OrderService(calculator, repository);

        assertThrows(IllegalArgumentException.class,
                () -> service.place("BOOK", 0, 120));

        verifyNoInteractions(repository);
    }

    @Test
    void blankSkuDoesNotSaveAnOrder() {
        OrderService service = new OrderService(calculator, repository);

        assertThrows(IllegalArgumentException.class,
                () -> service.place("   ", 1, 120));

        verifyNoInteractions(repository);
    }
}
~~~

Bài test đầu có hai bằng chứng **khác nhau**:

1. `assertEquals(new Order("BOOK", 2, 240), result)` kiểm giá trị trả về của use case khi calculator thật chạy.
2. `verify(repository).save(captured.capture())` và `assertEquals(result, captured.getValue())` kiểm yêu cầu lưu **đúng order đã trả về**, chứ không kiểm các helper hoặc thứ tự các bước tính toán.

`ArgumentCaptor` hữu ích khi contract yêu cầu **payload được gửi ra ranh giới** phải chứa đúng dữ liệu. Vì `Order` là record có `equals` theo các thành phần, trong tình huống đơn giản còn có thể dùng `verify(repository).save(new Order("BOOK", 2, 240))`; captor được dùng ở đây để minh họa cách kiểm payload mà không dựa vào implementation của repo.

Hai test dữ liệu lỗi dùng `verifyNoInteractions(repository)` bởi yêu cầu nói rõ **đầu vào không hợp lệ không được lưu**. Nếu code sai gọi `save` trước rồi mới kiểm validation, assertion này phát hiện lỗi có ý nghĩa. Không nên thêm `verifyNoMoreInteractions` lên mọi mock chỉ để cấm mọi lời gọi ngoài dự kiến; việc đó có thể ràng buộc test vào cấu trúc không nằm trong hợp đồng.

**Tổng test runnable:** `PriceCalculatorTest` có 6 invocation; `OrderServiceTest` có 3 invocation; toàn bộ ví dụ có **9 invocation**, dự kiến pass khi các file đúng như trên. Không có `System.out.println` nên **không có stdout nghiệp vụ**. Nếu kiểm thử báo fail, kiểm tra stack trace và HTML/XML report thay vì giả định sẽ in ra chín dòng “PASS”.

### 5.5. Thực thi bằng Gradle Wrapper

Khi project có `gradlew`, `gradlew.bat` và `gradle/wrapper/...`, từ thư mục gốc:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy một class:

~~~bash
./gradlew test --tests 'com.example.testing.OrderServiceTest'
~~~

Báo cáo Gradle Java test thường ở `build/reports/tests/test/index.html` và `build/test-results/test/`. Trong multi-project build, đó là `build` của đúng module đang chạy task. Nếu task `UP-TO-DATE` hoặc `FROM-CACHE`, test có thể sử dụng kết quả trước; để điều tra một vấn đề cụ thể có thể dùng `./gradlew test --rerun-tasks`.

Trong một module **Spring Boot đã có dependency testing**, thường không cần khai báo từng library JUnit/Mockito theo phiên bản độc lập nếu `spring-boot-starter-test` cung cấp chúng. Giữ `useJUnitPlatform()` cho Gradle task và để Spring Boot BOM/dependency management quản lý các phiên bản tương thích. Đoạn cấu hình tương ứng thường là:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Đây là **đoạn để tích hợp vào `build.gradle` đã có Spring Boot plugin và quản lý dependency**, không phải một project Spring Boot hoàn chỉnh độc lập. Với ví dụ chạy được phía trên, hãy dùng **file `build.gradle` đầy đủ ở mục 5.1**.

## 6. Refactor nên giữ test xanh, lỗi hành vi phải làm test đỏ

Một test hữu ích cần cân bằng **độ nhạy với lỗi nghiệp vụ** và **độ bền trước refactor hợp lệ**. Có thể đánh giá bằng cách thay đổi có chủ đích trong suy nghĩ hoặc trên một nhánh thử nghiệm:

| Thay đổi giả định | Kết quả mong muốn | Test nào nên phát hiện? |
| --- | --- | --- |
| Sửa `Math.multiplyExact` thành phép cộng | **Fail**: thành tiền 2×120 không còn là 240 | `PriceCalculatorTest` và `OrderServiceTest` |
| Bỏ `repository.save(order)` | **Fail**: mất yêu cầu lưu đơn | `OrderServiceTest` với `verify(save)` |
| Lưu một order có amount khác returned result | **Fail**: lưu sai payload | Captor và so sánh order |
| Bỏ kiểm tra quantity không hợp lệ | **Fail**: input lỗi có thể được lưu | Test validation và `verifyNoInteractions` |
| Đổi tên helper hoặc tách/gộp bước tính mà vẫn đúng kết quả | **Pass** | Test không nên buộc số lần gọi helper |
| Chuyển implementation repository từ JPA sang adapter tương đương | **Pass ở unit test service** | Contract của service không phụ thuộc SQL |
| JPA mapping hoặc unique constraint bị hỏng | **Fail ở integration test persistence** | Mock repo không thể phát hiện trực tiếp |

Bảng nêu **mục tiêu của bộ test**, không tuyên bố chúng ta đã chạy các mutation trên dự án. Khi thực hành, có thể tạo một thay đổi nhỏ cho SUT, xác nhận test liên quan fail, rồi hoàn nguyên. Đó là kiểm tra thủ công giá trị phát hiện lỗi của assertion.

### Mutation test là công cụ bổ trợ, không phải thước đo duy nhất

Mutation testing cố thay đổi toán tử, điều kiện hoặc câu lệnh của production code để xem test có “giết” được mutation hay không. Nếu đổi `<=` thành `<` ở ranh giới mà test vẫn xanh, có thể thiếu ca giá trị biên. Tuy nhiên, không phải mọi mutation sống sót đều là lỗi nghiệp vụ: code có thể tương đương ngữ nghĩa hoặc mutation nằm ở vùng không thuộc hợp đồng của test đang xét. Tập trung vào những mutation phản ánh quy tắc đáng bảo vệ.

## 7. Khi verify tương tác là đúng và khi không cần

**Verify có ý nghĩa** khi tác động ra bên ngoài là một phần hành vi được công bố:

- Chỉ gửi một lệnh thu tiền cho một giao dịch để tránh thanh toán lặp.
- Không gửi email khi địa chỉ không hợp lệ hoặc khách hàng chưa đồng ý.
- Không ghi dữ liệu khi validation thất bại.
- Phát sự kiện nghiệp vụ có đúng ID/payload khi đơn hàng được tạo.
- Dùng đúng đối tác/vùng dữ liệu có quyền truy cập theo hợp đồng an toàn.

**Verify dễ giòn** khi chỉ bám implementation:

- `verify(mapper).toDto(entity)` dù người dùng chỉ cần response JSON đúng.
- `verify(service, times(1)).privateLikeHelper(...)` chỉ vì code đang chia hàm theo cách đó.
- `verifyNoMoreInteractions` cho mọi mock trong một test mà không có ràng buộc “không thêm tác động” thực sự.
- `InOrder` cho nhiều collaborator thuần tính toán dù thứ tự không ảnh hưởng kết quả.

Đừng kết luận **mọi verify là over-mocking**. Quan trọng là trả lời: “Nếu lời gọi này bị bỏ hoặc thay đổi trong khi output khác vẫn đúng, hợp đồng có bị vi phạm không?” Nếu có, verify hợp lý. Nếu không, một assertion dựa trên kết quả quan sát được thường đủ.

### `times(1)`, `never`, `verifyNoInteractions` và `verifyNoMoreInteractions`

`verify(repository).save(order)` mặc định kiểm **đúng một lần** lời gọi tương ứng; `verify(repository, times(1)).save(order)` diễn đạt cùng ý rõ hơn khi số lần là yêu cầu. `verify(repository, never()).save(any())` kiểm không gọi `save` với bất kỳ đối số phù hợp; `verifyNoInteractions(repository)` chặt hơn, kiểm **không có tương tác nào** với mock đó. Nếu repository có thao tác đọc hợp lệ trước khi validation, `verifyNoInteractions` có thể quá mạnh; hãy chọn `never().save(any())` khi hợp đồng chỉ cấm thao tác lưu.

`verifyNoMoreInteractions(repository)` kiểm không có **tương tác nào khác chưa được verify**. Chỉ dùng khi chính sách side-effect yêu cầu như vậy; nó thường không nên là assertion mặc định của mọi unit test. Tránh biến việc “test sạch về mock” thành mục tiêu thay cho độ chính xác nghiệp vụ.

## 8. MockMvc và Spring Boot: mock đến tầng nào?

Một dự án Spring Boot có nhiều mức test:

| Mức | Nên chạy thật | Có thể thay bằng mock/fake | Câu hỏi được trả lời |
| --- | --- | --- | --- |
| **Domain unit** | Policy, calculator, validator thuần Java | Thường không cần mock | Quy tắc nghiệp vụ có đúng? |
| **Service unit** | Service + các collaborator thuần cần kiểm | Repository, client HTTP, email gateway | Use case trả đúng gì và yêu cầu tác động gì? |
| **MVC slice (`@WebMvcTest`)** | Controller, binding, validation, serialization, HTTP mapping | Dependency bên dưới controller tùy mục tiêu | API map request/response đúng không? |
| **Integration (`@SpringBootTest`, `@DataJpaTest` khi phù hợp)** | Những bean/hạ tầng thật cần kiểm chứng | Chỉ những external boundary ngoài phạm vi | Các tầng hợp tác, lưu/đọc và transaction thực sự đúng không? |

Ví dụ một `@WebMvcTest` mock service trả sẵn JSON DTO có thể chứng minh **controller serialize và map HTTP đúng**, nhưng không chứng minh service tính amount đúng. Nó không sai nếu phạm vi bài test là HTTP contract. Hãy có unit test/service test riêng cho business rules; với nghiệp vụ có rủi ro cao hoặc bug do integration, thêm bài test tích hợp qua đủ luồng cần thiết.

Ngược lại, dùng `@SpringBootTest` cho mọi phép cộng đơn giản sẽ mở Spring context tốn thời gian và gây phụ thuộc hạ tầng không cần thiết. Chọn mức test để **mỗi loại lỗi quan trọng có nơi phát hiện**, và tránh lặp lại hàng trăm kịch bản tương tự ở mọi mức khi không có giá trị bổ sung.

### Mock repository khác kiểm chứng persistence

Trong ví dụ, `verify(repository).save(order)` kiểm **ý định gọi cổng lưu**. Nó **không chứng minh**:

- Entity được ánh xạ đúng sang bảng/cột JPA.
- Constraint và transaction được áp dụng đúng.
- Dữ liệu thực sự commit và tìm lại được bằng query.
- Tầng adapter chuyển lỗi DB sang exception nghiệp vụ chính xác.

Những điều đó thuộc integration test adapter hoặc luồng use case qua database phù hợp, thường dùng database test có trạng thái độc lập. In-memory fake có thể giúp kiểm use case nhanh hơn nhưng không thay được test DB thật khi SQL/JPA là một phần yêu cầu.

## 9. Thiết kế expected độc lập với implementation

**Test oracle** là cơ sở xác định “kết quả nào là đúng”. Oracle tốt thường đến từ một hoặc nhiều nguồn:

1. **Yêu cầu nghiệp vụ có ví dụ cụ thể:** “2 sản phẩm x 120 = 240”, “bắt đầu từ 500 được miễn phí”.
2. **Hợp đồng API:** HTTP status, JSON schema, field bắt buộc, lỗi validation.
3. **Invariant:** giá trị không âm, tổng bằng tổng các thành phần, idempotency, không phát giao dịch trùng.
4. **Tính chất độc lập:** với quy tắc phù hợp, tăng quantity không được làm amount giảm; hoặc đơn không hợp lệ không được lưu.
5. **Reference data đã được kiểm duyệt:** bảng tình huống biên do nhóm xác nhận, phiên bản hóa cùng test.

Một expected chỉ sao chép một đoạn code sản phẩm **không phải oracle độc lập**. Ví dụ test lấy expected từ cùng `PriceCalculator` rồi đối chiếu với `OrderService` đang sử dụng chính calculator đó có thể chỉ chứng minh phép nối hai thành phần nhất quán, không chứng minh amount đúng. Nó vẫn có thể hữu ích để kiểm orchestration, nhưng muốn khẳng định quy tắc “amount đúng” cần ví dụ hoặc invariant riêng.

### Ranh giới và giá trị phản ví dụ

Với quy tắc “từ 500 trở lên”, cần test `499`, `500`, `501`. Các trường hợp cực trị thường phát hiện lỗi mà ca “đơn bình thường 1000” bỏ sót. Với phép nhân `int`, kiểm `Integer.MAX_VALUE × 2` giúp phát hiện overflow mà hai số nhỏ không phát hiện. Với tác động “không lưu khi invalid”, test âm/zero và verify không lưu giúp phát hiện thứ tự validation sai.

Dữ liệu lớn không đồng nghĩa bao phủ tốt. Một bộ test nhỏ bao phủ **quy tắc, biên và lỗi** thường hữu ích hơn hàng trăm dòng có expected tính từ cùng implementation.

## 10. Các lỗi thường gặp trong Mockito và cách xử lý

| Dấu hiệu | Nguyên nhân | Cách cải thiện |
| --- | --- | --- |
| Test pass dù logic domain sai | Calculator/validator đang bị mock | Chạy logic domain thật trong ít nhất một mức test |
| Test fail mỗi khi đổi tên helper hoặc chia/tách method | Verify lời gọi nội bộ quá chặt | Assert output/tác động thuộc hợp đồng |
| Test rất dài với hàng chục `when` | Setup mock cho cả chuỗi mà test chưa cần | Giảm fixture, dùng object thật hoặc fake đúng phạm vi |
| `UnnecessaryStubbingException` | Mockito strict stubbing phát hiện stub không dùng | Xóa stub thừa; chỉ dùng `lenient` có chủ đích, không tắt kiểm tra toàn cục để che vấn đề |
| Stub bất thường gây `PotentialStubbingProblem` | Tham số stub không khớp lời gọi, thường ở strict stubbing | Kiểm dữ liệu/đường đi thật, xem lại stub hoặc dùng argument matcher đúng |
| `Wanted but not invoked` | Lời gọi không xảy ra hoặc mock không được SUT dùng | Kiểm SUT có nhận đúng mock qua constructor và hợp đồng có yêu cầu lời gọi không |
| `verifyNoMoreInteractions` fail sau refactor hợp lệ | Test cấm chi tiết không thuộc contract | Gỡ assertion thừa hoặc thu hẹp vào side effect cần cấm |
| `@Mock`/`@InjectMocks` không khởi tạo | Thiếu Mockito Jupiter extension hoặc setup tương ứng | Dùng `@ExtendWith(MockitoExtension.class)` và dependency đúng |
| `NullPointerException` do collaborator | SUT nhận dependency null hoặc setup chưa được tiêm | Ưu tiên constructor injection, tạo SUT tường minh |
| Dùng `when(spy.method())` gây chạy method thật lúc stub | Spy mặc định gọi phương thức thật trong stubbing dạng này | Dùng `doReturn(...).when(spy).method()` khi thực sự cần spy; hạn chế partial mock |
| Test dùng mock repo nhưng nghĩ đã kiểm SQL | Mock không chạy persistence thật | Thêm integration test repository/adapter với DB phù hợp |
| Test flaky do thời gian/random/network | Dependency không được kiểm soát | `Clock.fixed`, seed xác định, fake/mock external gateway, fixture độc lập |
| Test expected do chính SUT sinh ra | Oracle trùng với implementation | Dùng đặc tả, bảng case, invariant hoặc oracle độc lập |
| Test khẳng định chỉ có exception mà không kiểm side effect | Lỗi vẫn có thể lưu dữ liệu trước khi throw | Kết hợp assertThrows với kiểm “không lưu” nếu hợp đồng yêu cầu |

### `@InjectMocks` có phải là xấu?

Không. `@InjectMocks` có thể tạo SUT và đưa các mock đã khai báo vào, rất tiện cho class nhiều dependency. Nhưng khi cần hiểu rõ bài test đang chạy dependency nào thật, **constructor injection tường minh** như ví dụ giúp dễ đọc hơn. Nếu có bốn mock nhưng hai mock không liên quan ca kiểm thử, đặt câu hỏi liệu service đã ôm quá nhiều trách nhiệm hoặc test đang dựng fixture quá rộng.

### Có nên dùng spy?

Spy chạy hành vi thật trừ khi phương thức được stub. Nó có ích trong một số trường hợp cần thay đổi một phần collaborator mà không thể tách ngay dependency, nhưng làm test dễ gắn chặt vào implementation. Đừng spy service chỉ để chứng minh “method A gọi method B” nếu hành vi mà người dùng cần là kết quả cuối cùng. Ưu tiên tách dependency thật thành abstraction có hợp đồng rõ rồi kiểm đầu ra/tác động.

### Có nên mock static hoặc constructor?

Mockito có cơ chế mock static/construction trong một phạm vi nhất định, nhưng dùng tràn lan có thể che dependency ẩn trong thiết kế. Với đồng hồ, UUID, API ngoại vi hoặc factory, cân nhắc **tiêm dependency** hoặc dùng đối tượng chuẩn có thể kiểm soát như `Clock.fixed(...)`. Chỉ dùng mock static khi mã legacy không thể cô lập hợp lý và test có giới hạn rõ ràng.

## 11. Checklist review một bài test dùng Mockito

Trước khi merge test mới, hãy tự hỏi:

1. **SUT thực là gì?** Test có đang chạy logic mà tên test tuyên bố kiểm không, hay logic ấy bị mock hết?
2. **Hợp đồng nào được bảo vệ?** Nêu rõ giá trị trả về, exception, trạng thái, payload/sự kiện hoặc side effect cần/không được xảy ra.
3. **Expected đến từ đâu?** Có ví dụ nghiệp vụ hoặc invariant độc lập không, hay vừa copy công thức từ implementation?
4. **Những mock nào cần thiết?** Repo, network, email, clock, random, hay chỉ là helper thuần Java?
5. **Tại sao verify này có giá trị?** Nếu đổi một lời gọi nội bộ mà kết quả bên ngoài vẫn đúng, test có nên pass không?
6. **Nếu thay đổi hành vi để tạo lỗi, test có fail không?** Thử bỏ `save`, đổi phép nhân, bỏ validation, đổi payload gửi đi.
7. **Nếu refactor hợp lệ, test có thể giữ xanh không?** Đổi tên helper, chuyển mapper, cấu trúc lại code mà contract không đổi.
8. **Điều gì mock không kiểm được?** Có cần test tích hợp cho persistence, HTTP mapping, transaction hoặc external protocol?
9. **Test có độc lập và rõ ràng không?** Không lệ thuộc thứ tự chạy, shared mock state, random không kiểm soát, mạng thật.
10. **Báo cáo thất bại có chỉ ra quy tắc nào sai không?** Tên test và assertion nên nói được ví dụ input/expected có ý nghĩa.

### Bài tập thực hành

**Bài A — đọc một mock-heavy test:** Chọn một test có nhiều `@Mock`. Phân loại từng mock: thuần domain, I/O port hay helper nội bộ. Thử thay một dependency thuần bằng object thật, rút gọn stub và giữ nguyên assertion có ý nghĩa.

**Bài B — kiểm ranh giới:** Với ví dụ ở mục 5, tạm bỏ `repository.save(order)`. Kỳ vọng test `placeReturnsCorrectOrderAndRequestsPersistence` fail tại `verify`, trong khi `PriceCalculatorTest` vẫn pass. Hoàn nguyên sau khi quan sát. Điều này chứng minh mỗi test bảo vệ một hợp đồng riêng.

**Bài C — phát hiện lỗi logic:** Tạm đổi `Math.multiplyExact(quantity, unitPrice)` thành `quantity + unitPrice`. Kỳ vọng test tính tiền fail; nếu bộ test chỉ stub calculator trả 240 thì nó **không phát hiện** được thay đổi. Hoàn nguyên.

**Bài D — test biên:** Thay `quantity <= 0` bằng `quantity < 0`. Kỳ vọng ca quantity=0 fail. Nếu test chỉ có dữ liệu quantity=2, lỗi biên này sẽ lọt qua.

**Bài E — xác định khoảng trống integration:** Giả sử output port được nối tới một `JpaRepository` thật. Đề xuất ít nhất một integration test lưu rồi đọc lại để phát hiện sai mapping/constraint mà Mockito không quan sát được; phân biệt kết quả của unit test với bằng chứng từ DB thật.

**Ghi nhớ:** Giới hạn mock ở những collaborator mà test cần điều khiển hoặc cần quan sát tương tác theo hợp đồng. Cho logic nghiệp vụ chạy thật; chọn expected độc lập với implementation; và đánh giá test bằng khả năng **thất bại khi hành vi sai, tồn tại khi refactor hợp lệ**. Bộ test đáng tin là tập hợp các bằng chứng bổ sung ở đúng ranh giới, không phải tập hợp những lời gọi `verify` giống nguyên văn mã hiện thực.
