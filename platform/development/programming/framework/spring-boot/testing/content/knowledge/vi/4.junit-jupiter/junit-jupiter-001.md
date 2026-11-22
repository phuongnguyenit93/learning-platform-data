# JUnit Jupiter: @Test, @DisplayName và cấu trúc lớp kiểm thử

## 1. Vì sao cần hiểu cấu trúc lớp kiểm thử?

JUnit Jupiter là mô hình lập trình và extension API để viết bài kiểm thử trên nền **JUnit Platform**. Trong một dự án Spring Boot, Jupiter thường được cung cấp qua `spring-boot-starter-test`. Để test có giá trị, cần biết **JUnit nhận diện phương thức kiểm thử như thế nào, tên kiểm thử hiển thị ra sao, trạng thái được khởi tạo khi nào và kết quả được đánh giá bằng assertion nào**.

Bài này tập trung vào ba nội dung:

1. `@Test` đánh dấu một phương thức là test; nội dung test tổ chức theo *Arrange – Act – Assert*.
2. `@DisplayName` đặt tên dễ đọc cho lớp và phương thức trong cây kết quả kiểm thử.
3. Lớp kiểm thử chứa test methods, lifecycle methods, trạng thái/fixture và có thể tổ chức theo nhóm bằng `@Nested`.

Đây là kiến thức **JUnit Jupiter**, áp dụng cho cả Java thuần lẫn code Spring Boot. Một test thuần Java không cần `@SpringBootTest` hoặc khởi động ApplicationContext.

## 2. @Test: phương thức nào được thực thi như bài kiểm thử?

Khai báo với đúng import:

~~~java
import org.junit.jupiter.api.Test;
~~~

Ví dụ tối giản:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        int actual = 2 + 3;
        assertEquals(5, actual);
    }
}
~~~

JUnit Jupiter phát hiện `addsTwoNumbers()` vì nó có `@Test`, gọi phương thức thông qua test engine và ghi nhận **PASS** khi không có assertion thất bại hoặc ngoại lệ ngoài dự kiến. Nếu `assertEquals(5, actual)` nhận giá trị khác 5, Jupiter đánh dấu **FAILED** và cung cấp expected/actual trong báo cáo.

**Quy tắc đối với phương thức `@Test` của Jupiter:**

- Không cần `public`; mức truy cập *package-private* như ví dụ thường được khuyến khích. Lớp/phương thức test **không được `private`**.
- Phương thức `@Test` **không được `static`**, phải có kiểu trả về `void`.
- Test có thể nhận tham số **nếu** Jupiter hoặc một extension đã đăng ký có `ParameterResolver` tương ứng (ví dụ tham số `TestInfo`). Không tự ý thêm tham số tùy ý như phương thức Java thông thường.
- `@Test` không nhận thuộc tính `expected` hoặc `timeout` kiểu JUnit 4; hãy dùng `assertThrows(...)` hoặc API timeout thích hợp của Jupiter.
- Chỉ gắn `@Test` là **chưa đủ bảo đảm test kiểm tra điều gì**: một phương thức rỗng vẫn có thể PASS. Cần assertion có ý nghĩa hoặc xác minh một hành vi quan sát được.

**Phân biệt import rất quan trọng:**

| Jupiter | JUnit 4 cũ |
| --- | --- |
| `org.junit.jupiter.api.Test` | `org.junit.Test` |
| `org.junit.jupiter.api.Assertions` | `org.junit.Assert` |
| `org.junit.jupiter.api.BeforeEach` | `org.junit.Before` |
| `org.junit.jupiter.api.BeforeAll` | `org.junit.BeforeClass` |

Không trộn tùy tiện các annotation giữa hai thế hệ. `@RunWith` là cơ chế runner của JUnit 4; JUnit Jupiter có test engine trên Platform và extension API riêng. Một dự án hỗn hợp có thể chạy JUnit 4 qua Vintage Engine nhưng điều đó không làm hai bộ annotation trở thành tương đương.

## 3. @DisplayName: mô tả hành vi cho người đọc kết quả test

`@DisplayName("...")` chỉ định tên hiển thị trên IDE, báo cáo test và các test runner hỗ trợ. Có thể đặt ở **lớp** hoặc **phương thức**:

~~~java
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("Kiểm tra điều kiện tuổi")
class AgeRuleTest {

    @Test
    @DisplayName("Người đủ 18 tuổi được chấp nhận")
    void acceptsAdult() {
        int age = 18;
        assertTrue(age >= 18);
    }

    @Test
    @DisplayName("Người chưa đủ 18 tuổi bị từ chối")
    void rejectsMinor() {
        int age = 17;
        assertTrue(age < 18);
    }
}
~~~

Trong cây kết quả, thay vì phải hiểu tên kỹ thuật `acceptsAdult()`, người đọc có thể thấy:

~~~text
Kiểm tra điều kiện tuổi
  ✓ Người đủ 18 tuổi được chấp nhận
  ✓ Người chưa đủ 18 tuổi bị từ chối
~~~

Dấu ✓ trong ví dụ là **minh họa một giao diện báo cáo khi test PASS**, không phải stdout cố định của JUnit hay Gradle.

**Nguyên tắc đặt tên:**

- Đặt **tên phương thức Java ổn định**, có ý nghĩa để tìm bằng IDE hoặc bộ lọc build: `rejectsMinor`, `calculatesShippingFee`.
- Đặt **display name diễn giải nghiệp vụ và kỳ vọng**: “Khi không đủ tồn kho, không tạo giao dịch thanh toán”.
- Tên có thể là tiếng Việt Unicode, dấu cách hoặc ký tự đặc biệt; vẫn cần đọc dễ hiểu trong báo cáo CI.
- Không dùng `@DisplayName` để che một test mơ hồ. Tên phải phù hợp assertion; test mang tên “từ chối giá âm” phải thật sự assert hành vi từ chối.

**`@DisplayName` không đổi tên class/method trong Java, không thêm assertion và không tác động logic chạy test.** Nó chỉ cung cấp metadata trình bày. Không có `@DisplayName`, Jupiter dùng tên mặc định do display-name generator tạo ra; có thể tùy biến bằng `@DisplayNameGeneration`, nhưng tên gán trực tiếp bằng `@DisplayName` được ưu tiên.

Ví dụ với generator (chỉ áp dụng khi cần chuẩn hóa tên hàng loạt):

~~~java
import org.junit.jupiter.api.DisplayNameGeneration;
import org.junit.jupiter.api.DisplayNameGenerator;
import org.junit.jupiter.api.Test;

@DisplayNameGeneration(DisplayNameGenerator.ReplaceUnderscores.class)
class NamingTest {

    @Test
    void invalid_input_is_rejected() {
        // Minh họa cơ chế đặt tên; test thực tế phải có assertion.
    }
}
~~~

Tên hiển thị của phương thức trên sẽ được tạo theo kiểu “invalid input is rejected”; đây **chỉ là ví dụ cú pháp generator, không phải một bài test đầy đủ về nghiệp vụ**.

## 4. Cấu trúc chuẩn của một lớp test

Một lớp test có thể gồm:

| Thành phần | Chức năng | Thời điểm |
| --- | --- | --- |
| `@BeforeAll` | Chuẩn bị tài nguyên dùng chung cho lớp khi cần | Trước các test thuộc lớp |
| `@BeforeEach` | Tạo/reset fixture cho từng test | Trước mỗi lần chạy test |
| `@Test` | Chạy một kịch bản độc lập và assertion | Mỗi lần thực thi kịch bản |
| `@AfterEach` | Dọn tài nguyên/thao tác sau từng test | Sau mỗi lần chạy test |
| `@AfterAll` | Dọn tài nguyên chung của lớp | Sau các test thuộc lớp |
| `@Nested` | Gom các test trong inner class theo trạng thái/hành vi | Như một nhánh con trong cây test |

Ví dụ **khung cấu trúc** để nhận diện vị trí các thành phần (không phải bài kiểm thử nghiệp vụ độc lập):

~~~java
import org.junit.jupiter.api.*;

@DisplayName("Một chức năng")
class FeatureTest {

    @BeforeAll
    static void beforeAll() {
        // Thiết lập dùng chung; tránh kết nối thật nếu không cần.
    }

    @BeforeEach
    void setUp() {
        // Chuẩn bị dữ liệu mới cho từng test.
    }

    @Test
    @DisplayName("Hoàn thành hành vi A")
    void behaviorA() {
        // Arrange -> Act -> Assert.
    }

    @AfterEach
    void tearDown() {
        // Dọn tài nguyên của từng test nếu có.
    }

    @AfterAll
    static void afterAll() {
        // Giải phóng tài nguyên chung nếu có.
    }
}
~~~

Theo lifecycle mặc định **`PER_METHOD`**, JUnit Jupiter tạo một instance lớp test mới cho mỗi phương thức test. Vì thế state ở field của instance thường không bị chia sẻ giữa các test. `@BeforeEach` vẫn hữu ích để việc khởi tạo fixture rõ ràng và tái sử dụng được.

Mặc định, `@BeforeAll` và `@AfterAll` ở lớp test thông thường phải là `static`; `@BeforeEach` và `@AfterEach` là instance methods. Nếu chủ động dùng `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, Jupiter có thể gọi `@BeforeAll` và `@AfterAll` không static, nhưng lúc đó state instance có thể dùng chung giữa các test: cần quản lý/reset cẩn thận. Không đổi sang `PER_CLASS` chỉ để tránh viết một hàm `static`.

**Không dựa vào thứ tự các phương thức `@Test`.** Thứ tự chạy không nên trở thành điều kiện đúng của suite. Nếu thật sự có yêu cầu sắp xếp, Jupiter cung cấp `@TestMethodOrder` và `@Order`, nhưng test độc lập vẫn là lựa chọn tốt cho các ví dụ và nghiệp vụ thông thường.

## 5. Ví dụ đầy đủ, chạy được: cấu trúc test cho Giỏ hàng

Giả sử một giỏ hàng cộng tiền theo đơn vị **cent** và từ chối đơn giá không dương. Mục tiêu bài test: giỏ hàng mới rỗng, thêm hai sản phẩm làm tổng tăng đúng, giá không hợp lệ ném lỗi và không thay đổi trạng thái.

Đặt file `src/test/java/example/CartTest.java`, dùng **Java 17+** và JUnit Jupiter:

~~~java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@DisplayName("Giỏ hàng")
class CartTest {

    private Cart cart;

    @BeforeEach
    void setUp() {
        cart = new Cart();
    }

    @Test
    @DisplayName("Giỏ hàng mới có 0 sản phẩm và tổng tiền bằng 0")
    void startsEmpty() {
        assertAll("Giỏ hàng mới",
                () -> assertEquals(0, cart.itemCount()),
                () -> assertEquals(0, cart.totalCents()));
    }

    @Nested
    @DisplayName("Khi thêm sản phẩm")
    class AddingItems {

        @Test
        @DisplayName("Cộng dồn đúng tiền và số lượng")
        void addsValidPrices() {
            cart.add(1_000);
            cart.add(2_500);

            assertAll("Sau khi thêm",
                    () -> assertEquals(2, cart.itemCount()),
                    () -> assertEquals(3_500, cart.totalCents()));
        }

        @Test
        @DisplayName("Giá bằng 0 bị từ chối và giỏ không đổi")
        void rejectsZeroPrice() {
            IllegalArgumentException error = assertThrows(
                    IllegalArgumentException.class,
                    () -> cart.add(0));

            assertEquals("Giá phải dương", error.getMessage());
            assertEquals(0, cart.itemCount());
            assertEquals(0, cart.totalCents());
        }

        @Test
        @DisplayName("Giá âm bị từ chối")
        void rejectsNegativePrice() {
            assertThrows(IllegalArgumentException.class,
                    () -> cart.add(-100));
            assertEquals(0, cart.itemCount());
        }
    }

    // Mô hình tối thiểu để ví dụ tự chạy, không cần Spring hoặc DB.
    static final class Cart {
        private int count;
        private int total;

        void add(int priceCents) {
            if (priceCents <= 0) {
                throw new IllegalArgumentException("Giá phải dương");
            }
            int newTotal = Math.addExact(total, priceCents);
            total = newTotal;
            count++;
        }

        int itemCount() {
            return count;
        }

        int totalCents() {
            return total;
        }
    }
}
~~~

**Giải thích chi tiết từng phần:**

1. `@DisplayName("Giỏ hàng")` trên lớp đặt tên cho nhánh gốc trong báo cáo.
2. `private Cart cart` là fixture của lớp test. `@BeforeEach` tạo giỏ hàng mới mỗi lần để các bài test không phụ thuộc việc bài nào chạy trước.
3. `startsEmpty()` dùng `@Test` và `assertAll(...)` kiểm đồng thời số lượng và tổng tiền; có hai assertions độc lập nên khi một giá trị sai vẫn nhận được thông tin của cả nhóm assertion.
4. `@Nested` tạo một **inner class không static** mang tên `AddingItems`, gom ba kịch bản cùng ngữ cảnh. Inner class vẫn có thể sử dụng field `cart` của outer class; `@BeforeEach` ở outer class được gọi cho cả các test bên trong `@Nested`.
5. `addsValidPrices()` tạo trạng thái qua *Act* rồi assert đúng kết quả: 2 sản phẩm và 3.500 cent.
6. `rejectsZeroPrice()` dùng `assertThrows(...)` để xác nhận lỗi đã được ném; đồng thời assert state không thay đổi.
7. `Cart` là một class sản phẩm đơn giản đặt trong file test **chỉ để ví dụ tự chứa**. Trong dự án thực tế, hãy import và kiểm chính implementation `Cart` hoặc service tương ứng từ `src/main/java`; không nên sao chép lại production logic vào test rồi xem đó là bằng chứng của implementation thật.

Cây kết quả có dạng:

~~~text
Giỏ hàng
  Giỏ hàng mới có 0 sản phẩm và tổng tiền bằng 0     PASS
  Khi thêm sản phẩm
    Cộng dồn đúng tiền và số lượng                  PASS
    Giá bằng 0 bị từ chối và giỏ không đổi          PASS
    Giá âm bị từ chối                               PASS
~~~

Thứ tự hiển thị ở đây là minh họa, **không phải cam kết thứ tự chạy**. Test không cần in ra stdout; bằng chứng chính nằm ở các assertion và báo cáo của JUnit Platform.

### Vì sao không cần Spring Boot context?

Ví dụ chỉ kiểm Java object thuần. `@SpringBootTest` sẽ khởi tạo context nhiều hơn nhu cầu và thường chậm hơn. Khi mục tiêu là kiểm Spring dependency injection, MVC, transaction, repository hoặc security integration, chọn annotation test tương ứng cho phạm vi đó; `@Test` và `@DisplayName` vẫn dùng để đánh dấu và mô tả phương thức test.

## 6. Chạy test trong dự án Gradle/Spring Boot

Trong module Spring Boot sử dụng Gradle và đã có plugin/BOM của Spring Boot, cấu hình test thường có dạng:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **đoạn cấu hình bổ sung vào `build.gradle` đang tồn tại**, không phải file build hoàn chỉnh. `spring-boot-starter-test` cung cấp JUnit Jupiter và các thư viện hỗ trợ test theo phiên bản mà Spring Boot quản lý. `useJUnitPlatform()` cho Gradle biết cần chạy test qua JUnit Platform, bao gồm Jupiter engine.

Chạy từ root Gradle phù hợp với module được cấu hình:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

**Kỳ vọng:** JUnit Platform phát hiện **4 phương thức `@Test`** (một ở outer class, ba ở `@Nested`). Cả bốn **PASS** nếu mã và cấu hình đúng. Với Gradle, tác vụ thành công kết thúc bằng `BUILD SUCCESSFUL` khi các điều kiện build khác cũng đúng. Số dòng, dấu check, thứ tự và mức chi tiết của console phụ thuộc công cụ/bản cấu hình; không giả định một chuỗi stdout chính xác.

Báo cáo HTML do Gradle sinh thường ở `build/reports/tests/test/index.html` của module đã chạy. IDE như IntelliJ cũng hiển thị test tree theo `@DisplayName`. Nếu muốn chạy một lớp riêng, bộ lọc Gradle có thể chọn bằng `--tests`; với nested classes, chú ý tên binary có dấu `$` và cách IDE/Gradle lọc test để không vô tình bỏ sót nhóm con.

### Những điểm cần kiểm khi test không được phát hiện

1. Có đúng file trong nguồn test (thường `src/test/java`), đúng tên package/thư mục và dependency không?
2. Có import **`org.junit.jupiter.api.Test`** thay vì vô tình dùng `org.junit.Test` không?
3. Tác vụ Gradle có `useJUnitPlatform()` và Jupiter engine đúng phiên bản không?
4. Lớp/phương thức có bị khai báo `private` hoặc phương thức `@Test` sai chữ ký (ví dụ `static` hoặc trả về `boolean`) không?
5. Có bị `@Disabled`, bộ lọc `--tests`, tag filter hoặc cấu hình IDE loại ra không?
6. Có lỗi compile trong Java trước khi JUnit kịp discover test không?

Đừng sửa lỗi discovery bằng cách thêm `@SpringBootTest`; annotation đó dành cho mục tiêu kiểm tích hợp với Spring, không thay cho cấu hình JUnit Platform.

## 7. Cách viết nội dung một bài test có chất lượng

Tổ chức theo **Arrange – Act – Assert**:

~~~java
@Test
@DisplayName("Sau khi thêm hai sản phẩm, tổng tiền là 3.500 cent")
void sumsTwoPrices() {
    // Arrange
    Cart cart = new Cart();

    // Act
    cart.add(1_000);
    cart.add(2_500);

    // Assert
    assertEquals(3_500, cart.totalCents());
}
~~~

Đoạn này dùng `Cart` từ ví dụ ở mục 5: **mã minh họa phương thức, không phải file độc lập**. Trong test thực tế, hạn chế lẫn nhiều kịch bản không liên quan vào một method. Chọn assertions mô tả *hợp đồng quan sát được*, thay vì kiểm quá nhiều chi tiết implementation.

- Với kết quả: `assertEquals(expected, actual)`, `assertTrue(condition)`, `assertFalse(condition)`.
- Với lỗi: `assertThrows(ExceptionType.class, executable)`; kiểu con của exception dự kiến cũng được chấp nhận. Cần đúng chính xác loại exception thì dùng `assertThrowsExactly` nếu phiên bản Jupiter hỗ trợ.
- Với nhiều khẳng định độc lập: `assertAll(...)` nhóm assertion cho cùng hành vi.
- Với thao tác quan trọng nhưng không có kết quả trực tiếp: cân nhắc mock/verify ở test khác; đừng lạm dụng test tương tác cho thứ có thể assert bằng trạng thái.

`@DisplayName` nên chỉ rõ hành vi, không lặp lại đơn thuần “test1”, “happy path” hoặc tên lớp. Tên phương thức Java cũng nên rõ nghĩa vì giúp grep, refactor và nhận diện khi log báo lỗi.

## 8. Cách tổ chức lớp test dễ bảo trì

**Một lớp test thường gắn với một đối tượng hoặc một nhóm hành vi nhất quán**, ví dụ `CartTest` kiểm `Cart`, `CheckoutServiceTest` kiểm `CheckoutService`. Nếu khối lượng lớn, `@Nested` giúp gom theo bối cảnh:

~~~text
CheckoutServiceTest
  Khi tồn kho còn đủ
    Tạo yêu cầu thanh toán đúng số tiền
    Giảm tồn sau khi thanh toán thành công
  Khi tồn kho không đủ
    Từ chối đơn hàng
    Không gửi yêu cầu thanh toán
~~~

Nhưng `@Nested` không bắt buộc. Với ba test đơn giản không có ngữ cảnh chung, một lớp phẳng với `@Test` + `@DisplayName` thường dễ đọc hơn. Tránh lồng nhiều tầng làm fixture và lifecycle khó theo dõi.

Với một nhóm `@Nested` cần thiết lập thêm trạng thái, có thể đặt `@BeforeEach` riêng bên trong: Jupiter gọi setup của outer class trước rồi setup của inner class. Bảo đảm thiết lập không phụ thuộc bài test khác. Với Java 17+ và phiên bản Jupiter phù hợp, một số quy tắc lifecycle `@BeforeAll` bên trong nested class khác các phiên bản Java rất cũ; ở bài cơ bản, ưu tiên `@BeforeEach` và fixture đơn giản.

Đừng dùng `@TestInstance(PER_CLASS)` hay `@TestMethodOrder` như giải pháp mặc định để chia sẻ trạng thái giữa các test. Việc đó có thể khiến test phụ thuộc thứ tự và chạy riêng từng method thất bại. Nếu có tài nguyên thật đắt đỏ cần dùng chung, thiết kế fixture theo lifecycle rõ ràng và bảo đảm cleanup.

## 9. Sai lầm phổ biến và cách tránh

**Gắn `@DisplayName` mà quên `@Test`.** Một phương thức chỉ có tên hiển thị không trở thành test. Phải có annotation test thích hợp như `@Test` hoặc `@ParameterizedTest`; không gắn đồng thời hai loại tùy tiện cho cùng kịch bản.

**Dùng sai import.** `org.junit.Test` là JUnit 4. Trong dự án dùng Jupiter, dùng `org.junit.jupiter.api.Test` và `org.junit.jupiter.api.DisplayName`.

**Test không có assertion.** Method chỉ gọi một hàm nhưng không kiểm kết quả có thể PASS dù nghiệp vụ sai. Cần ít nhất một tiêu chí quan sát rõ: giá trị trả về, trạng thái, ngoại lệ hoặc tương tác cần thiết.

**Một test phụ thuộc test khác.** Field static mutable, dữ liệu DB dùng chung, dựa vào thứ tự chạy làm kết quả chập chờn. Tạo fixture độc lập, reset state bằng `@BeforeEach` và không dựa vào thứ tự phương thức.

**Chữ ký test không hợp lệ.** Phương thức `@Test` static, private hoặc trả về giá trị sẽ không phù hợp contract của Jupiter. Dùng instance method, non-private và `void`.

**Dùng tên khó hiểu.** `test1`, `caseA` hoặc `shouldWork` khiến báo cáo ít giá trị. Kết hợp tên Java ngắn gọn và display name mô tả “điều kiện → kết quả”.

**Lồng `@Nested` quá sâu.** Nhiều tầng làm khó xác định fixture nào được tạo, state nào đang dùng. Chỉ nhóm khi thật sự giúp đọc ngữ cảnh.

**Tạo Spring context cho phép tính đơn giản.** Không cần `@SpringBootTest` chỉ để chạy `@Test`. Chọn unit test cho object thuần; chọn Spring slice/integration khi muốn chứng minh framework wiring và behavior.

**Bỏ qua khác biệt JUnit 4/Jupiter.** Sao chép `@Test(expected = ...)` hoặc `@Before` của JUnit 4 vào Jupiter sẽ sai. Dùng `assertThrows`, `@BeforeEach`, `@BeforeAll` và các extension API của Jupiter.

## 10. Checklist trước khi hoàn tất lớp kiểm thử

- [ ] Test class và test method nằm đúng `src/test/java` với package và import Jupiter.
- [ ] Mỗi test có `@Test` (hoặc annotation kiểm thử Jupiter thích hợp), không `private`/`static`, trả về `void`.
- [ ] `@DisplayName` mô tả hành vi và kỳ vọng, nhất quán với assertions.
- [ ] Mỗi method độc lập, có fixture rõ ràng và Arrange – Act – Assert.
- [ ] `@BeforeEach` chỉ chuẩn bị trạng thái; `@AfterEach` chỉ dọn khi cần.
- [ ] Nếu dùng `@Nested`, inner class không static và hiểu lifecycle từ outer.
- [ ] Không dùng thứ tự test hoặc mutable state dùng chung làm điều kiện kết quả.
- [ ] Gradle cấu hình JUnit Platform; test được phát hiện và báo cáo PASS/FAIL đúng mong đợi.
- [ ] Test kiểm implementation thật của chức năng đang học; không thay thế nó bằng bản copy trong test thực tế.

**Điểm cần nhớ:** `@Test` cho test engine biết **chạy phương thức nào**; `@DisplayName` giúp con người hiểu **test chứng minh điều gì**; cấu trúc lớp với fixture, lifecycle và `@Nested` giúp mỗi kịch bản **độc lập, dễ đọc và dễ bảo trì**.

### Tài liệu tham khảo

- [JUnit 5 User Guide – Writing Tests](https://docs.junit.org/5.10.0/user-guide/index.html#writing-tests): quy tắc test methods, lifecycle, display names và nested tests.
- [JUnit 5 User Guide – Display Names](https://docs.junit.org/5.10.0/user-guide/index.html#writing-tests-display-names): `@DisplayName` và cách hiển thị.
- [JUnit 5 User Guide – Test Instance Lifecycle](https://docs.junit.org/5.10.0/user-guide/index.html#writing-tests-test-instance-lifecycle): `PER_METHOD` và `PER_CLASS`.
- [Gradle User Manual – Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html): cấu hình `useJUnitPlatform()` và báo cáo test.
