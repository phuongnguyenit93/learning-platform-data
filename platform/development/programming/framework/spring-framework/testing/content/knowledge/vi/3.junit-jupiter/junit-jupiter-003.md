# Vòng đời @Test, @BeforeEach, @AfterEach, @BeforeAll và @AfterAll

JUnit Jupiter cung cấp các annotation để đánh dấu phương thức kiểm thử và xác định những bước cần chạy trước hoặc sau mỗi test. Hiểu đúng vòng đời này giúp chuẩn bị dữ liệu nhất quán, giải phóng tài nguyên đúng lúc và tránh để trạng thái của test này ảnh hưởng đến test khác.

Năm annotation có vai trò liên quan nhưng khác nhau:

- **@Test** đánh dấu một phương thức là test cần thực thi.
- **@BeforeEach** chạy trước mỗi lần thực thi test tương ứng.
- **@AfterEach** chạy sau mỗi lần thực thi test tương ứng.
- **@BeforeAll** chạy một lần trước các test trong lớp.
- **@AfterAll** chạy một lần sau khi các test trong lớp hoàn tất.

Các annotation này thuộc package org.junit.jupiter.api của JUnit Jupiter. Chúng là nền tảng để tổ chức test trong dự án Java và các dự án Spring sử dụng JUnit 5.

## 1. Vòng đời tổng quát của một test class

Với một lớp có nhiều phương thức @Test, thứ tự tổng quát là:

~~~text
@BeforeAll
    |
    +-- @BeforeEach
    |       |
    |       +-- @Test thứ nhất
    |       |
    |     @AfterEach
    |
    +-- @BeforeEach
    |       |
    |       +-- @Test thứ hai
    |       |
    |     @AfterEach
    |
    +-- ... các test còn lại ...
    |
@AfterAll
~~~

Ví dụ, một lớp có hai test sẽ trải qua các bước sau:

1. JUnit tạo test instance theo chế độ vòng đời đang cấu hình.
2. Các phương thức @BeforeAll được thực thi một lần.
3. Trước test thứ nhất, các phương thức @BeforeEach được thực thi.
4. Phương thức @Test thứ nhất chạy.
5. Các phương thức @AfterEach được thực thi.
6. Chu trình BeforeEach → Test → AfterEach lặp lại cho test thứ hai.
7. Sau khi các test trong lớp hoàn tất, các phương thức @AfterAll được thực thi.

JUnit không mặc định bảo đảm test thứ nhất hay test thứ hai trong ví dụ trên sẽ chạy trước. Điều được bảo đảm là các callback vòng đời phù hợp được đặt trước và sau lần thực thi test tương ứng.

### Quan sát thứ tự bằng một ví dụ nhỏ

~~~java
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class LifecycleExampleTest {

    @BeforeAll
    static void beforeAll() {
        System.out.println("BeforeAll");
    }

    @BeforeEach
    void beforeEach() {
        System.out.println("BeforeEach");
    }

    @Test
    void firstTest() {
        System.out.println("firstTest");
    }

    @Test
    void secondTest() {
        System.out.println("secondTest");
    }

    @AfterEach
    void afterEach() {
        System.out.println("AfterEach");
    }

    @AfterAll
    static void afterAll() {
        System.out.println("AfterAll");
    }
}
~~~

Một kết quả chạy có thể có dạng:

~~~text
BeforeAll
BeforeEach
secondTest
AfterEach
BeforeEach
firstTest
AfterEach
AfterAll
~~~

Tên test xuất hiện trước có thể thay đổi. Dù thứ tự hai test khác nhau, BeforeAll vẫn chạy một lần ở đầu lớp, mỗi test vẫn có BeforeEach và AfterEach, còn AfterAll chạy ở cuối.

## 2. @Test: đánh dấu phương thức kiểm thử

@Test cho JUnit biết phương thức nào cần được thực thi như một test. Một test thường kiểm tra một hành vi cụ thể bằng cách chuẩn bị đầu vào, gọi thành phần cần kiểm thử và xác nhận kết quả mong đợi.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class CalculatorTest {

    @Test
    void addsTwoNumbers() {
        Calculator calculator = new Calculator();

        int result = calculator.add(2, 3);

        assertEquals(5, result);
    }
}
~~~

Phương thức addsTwoNumbers được JUnit phát hiện và thực thi. Assertion xác nhận kết quả thực tế bằng 5.

Một số quy tắc quan trọng:

- Phương thức @Test không được khai báo private hoặc static.
- Phương thức thường trả về void.
- Phương thức có thể có phạm vi package-private; không bắt buộc phải public.
- Phương thức có thể nhận tham số nếu có ParameterResolver phù hợp cung cấp các giá trị đó.
- @Test không tự chuẩn bị dữ liệu, không tự dọn tài nguyên và không tự bảo đảm trạng thái bên ngoài được đặt lại giữa các test.

Trong JUnit Jupiter, nếu cần kiểm tra một exception, hãy dùng assertion như assertThrows. Không dùng thuộc tính expected của annotation @Test như cách viết quen thuộc trong JUnit 4.

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

@Test
void rejectsNegativeQuantity() {
    assertThrows(
            IllegalArgumentException.class,
            () -> orderService.createOrder(-1)
    );
}
~~~

## 3. @BeforeEach: chuẩn bị trước mỗi test

@BeforeEach đánh dấu phương thức cần chạy trước từng phương thức test tương ứng. Đây là nơi phù hợp để tạo fixture mới, khởi tạo object cần kiểm thử, chuẩn bị dữ liệu riêng hoặc đặt mock về trạng thái cần thiết.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ShoppingCartTest {

    private ShoppingCart cart;

    @BeforeEach
    void setUp() {
        cart = new ShoppingCart();
    }

    @Test
    void newCartIsEmpty() {
        assertTrue(cart.isEmpty());
    }

    @Test
    void cartCanContainAnItem() {
        cart.add(new Item("keyboard", 1));

        assertTrue(cart.contains("keyboard"));
    }
}
~~~

Mỗi test bắt đầu với một ShoppingCart mới. Test thêm sản phẩm không làm thay đổi fixture mà test còn lại sử dụng.

@BeforeEach thường được dùng để:

- Tạo object và dependency giả phục vụ test.
- Chuẩn bị dữ liệu đầu vào cho một tình huống.
- Khởi tạo mock hoặc cấu hình hành vi của mock.
- Thiết lập thư mục tạm, file tạm hoặc tài nguyên chỉ dùng trong một test.
- Đặt trạng thái của fixture về một trạng thái ban đầu dễ dự đoán.

Không nên đưa mọi thao tác chuẩn bị vào một phương thức setup quá lớn. Khi mỗi test cần điều kiện khác nhau, hãy để phần dữ liệu riêng trong test hoặc tách thành các phương thức trợ giúp có tên rõ ràng. Setup càng dễ đọc thì người bảo trì càng hiểu được vì sao test có kết quả mong đợi.

### @BeforeEach chạy bao nhiêu lần?

Với các phương thức @Test thông thường, @BeforeEach chạy một lần trước mỗi test method. Nó cũng được áp dụng cho mỗi lần thực thi của các loại test template như @RepeatedTest và @ParameterizedTest.

Ví dụ, một @ParameterizedTest có bốn bộ tham số thì phần setup được thực hiện cho từng invocation. Mỗi invocation được xử lý như một lần thực thi test riêng.

## 4. @AfterEach: dọn dẹp sau mỗi test

@AfterEach đánh dấu phương thức chạy sau mỗi lần thực thi test tương ứng. Nó thường được dùng để đóng tài nguyên, xóa file tạm, dừng server chỉ dùng trong test hoặc khôi phục trạng thái mà test đã thay đổi.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class FileWriterTest {

    private Path temporaryFile;

    @BeforeEach
    void createTemporaryFile() throws IOException {
        temporaryFile = Files.createTempFile("writer-test-", ".txt");
    }

    @Test
    void writesContentToFile() throws IOException {
        Files.writeString(temporaryFile, "JUnit Jupiter");

        String content = Files.readString(temporaryFile);

        org.junit.jupiter.api.Assertions.assertEquals(
                "JUnit Jupiter", content);
    }

    @AfterEach
    void deleteTemporaryFile() throws IOException {
        if (temporaryFile != null) {
            Files.deleteIfExists(temporaryFile);
        }
    }
}
~~~

Việc dọn dẹp trong @AfterEach giúp tài nguyên được giải phóng ngay cả khi assertion trong test thất bại. Phương thức cleanup nên chịu được trạng thái chuẩn bị chưa hoàn tất, ví dụ kiểm tra null trước khi đóng hoặc xóa tài nguyên.

Nếu một phương thức @BeforeEach thất bại, test method tương ứng và các phương thức setup tiếp theo sẽ không chạy. Các callback @AfterEach vẫn được thực thi để có cơ hội dọn dẹp phần tài nguyên đã tạo. Vì vậy, cleanup nên an toàn khi chỉ một phần setup đã hoàn thành.

### Khi nào cần @AfterEach?

Dùng @AfterEach khi test tạo ra hoặc thay đổi tài nguyên cần được thu hồi sau từng lần chạy:

- Đóng stream, socket, client hoặc kết nối do test tự mở.
- Dừng một server cục bộ được khởi chạy riêng cho test.
- Xóa file hoặc thư mục tạm.
- Hủy subscription hoặc listener đã đăng ký.
- Khôi phục system property, biến môi trường mô phỏng hoặc trạng thái dùng chung mà test đã thay đổi.

Với object Java thuần chỉ tồn tại trong test instance và không giữ tài nguyên bên ngoài, đôi khi không cần cleanup thủ công. Garbage collector sẽ quản lý vòng đời bộ nhớ. Hãy dành @AfterEach cho những tác động cần được thu hồi rõ ràng.

## 5. @BeforeAll: chuẩn bị một lần cho cả lớp

@BeforeAll đánh dấu phương thức chạy một lần trước khi các test trong test class được thực thi. Annotation này phù hợp với tài nguyên tốn chi phí khởi tạo và có thể dùng chung trong phạm vi lớp test, chẳng hạn một server thử nghiệm hoặc dữ liệu tham chiếu chỉ đọc.

Theo mặc định, phương thức @BeforeAll phải là static. Lý do là JUnit mặc định tạo một test instance riêng cho mỗi test method; do đó, ở thời điểm chạy BeforeAll, JUnit không chọn một instance cụ thể để gọi phương thức instance.

~~~java
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class SharedResourceTest {

    @BeforeAll
    static void startSharedResource() {
        System.out.println("Start shared resource once");
    }

    @Test
    void firstScenario() {
        // Sử dụng tài nguyên dùng chung.
    }

    @Test
    void secondScenario() {
        // Tiếp tục sử dụng tài nguyên dùng chung.
    }
}
~~~

@BeforeAll chỉ chạy một lần cho lớp, dù lớp có một hay nhiều test method. Nếu lớp có nhiều test, không khởi động lại tài nguyên dùng chung trước mỗi test bằng BeforeAll; đó là nhiệm vụ khác với BeforeEach.

Một số trường hợp phù hợp:

- Khởi chạy một server giả dùng chung cho cả lớp.
- Tạo một bộ dữ liệu tham chiếu bất biến.
- Khởi tạo tài nguyên đắt đỏ có thể được nhiều test sử dụng an toàn.
- Kiểm tra hoặc chuẩn bị môi trường chung trước khi bắt đầu các test.

Không nên dùng BeforeAll để tạo trạng thái có thể bị một test sửa đổi rồi để test sau phụ thuộc vào trạng thái ấy. Nếu dữ liệu cần độc lập giữa các test, hãy tạo hoặc khôi phục nó trong BeforeEach.

## 6. @AfterAll: giải phóng tài nguyên dùng chung

@AfterAll đánh dấu phương thức chạy một lần sau khi các test trong lớp đã hoàn tất. Đây là nơi phù hợp để giải phóng tài nguyên được tạo trong @BeforeAll.

Theo mặc định, phương thức @AfterAll phải là static.

~~~java
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class SharedResourceTest {

    @BeforeAll
    static void startSharedResource() {
        System.out.println("Start shared resource");
    }

    @Test
    void scenarioA() {
        // Kiểm tra hành vi A.
    }

    @Test
    void scenarioB() {
        // Kiểm tra hành vi B.
    }

    @AfterAll
    static void stopSharedResource() {
        System.out.println("Stop shared resource");
    }
}
~~~

Cặp @BeforeAll và @AfterAll nên được thiết kế cùng nhau: tài nguyên nào được tạo một lần thì cần có điểm giải phóng tương ứng. Nếu khởi tạo thất bại giữa chừng, phương thức giải phóng cũng nên kiểm tra tài nguyên đã thực sự được tạo trước khi đóng.

Không đặt việc dọn dữ liệu riêng của từng test vào @AfterAll. Nếu chỉ dọn ở cuối lớp, một test có thể nhìn thấy dữ liệu do test chạy trước để lại. Với dữ liệu riêng của từng lần chạy, dùng @AfterEach hoặc cơ chế rollback của framework phù hợp.

## 7. Quy tắc static và vòng đời instance của test class

Một điểm quan trọng của JUnit Jupiter là vòng đời của đối tượng test. Vòng đời này quyết định số lượng instance được tạo và liệu các phương thức BeforeAll/AfterAll có thể là instance method hay không.

### Mặc định: PER_METHOD

JUnit Jupiter mặc định sử dụng TestInstance.Lifecycle.PER_METHOD. JUnit tạo một instance mới của test class cho mỗi test method.

Hệ quả:

- Các field instance của test class được khởi tạo lại theo từng test method.
- Một test thay đổi field instance không làm thay đổi field của instance ở test method khác.
- Field static vẫn được dùng chung giữa các test.
- Tài nguyên bên ngoài như database, file, system property hoặc server vẫn có thể được dùng chung dù instance test mới được tạo.

Ví dụ:

~~~java
class CounterTest {

    private int count = 0;

    @Test
    void incrementsCounter() {
        count++;
        org.junit.jupiter.api.Assertions.assertEquals(1, count);
    }

    @Test
    void counterStartsAtZero() {
        org.junit.jupiter.api.Assertions.assertEquals(0, count);
    }
}
~~~

Với PER_METHOD, hai test method nhận hai instance riêng. Vì vậy, thay đổi field count trong test đầu không làm test thứ hai bắt đầu với giá trị 1.

### Chuyển sang PER_CLASS

Có thể cấu hình một instance dùng chung cho toàn bộ test class bằng @TestInstance(TestInstance.Lifecycle.PER_CLASS):

~~~java
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class PerClassLifecycleTest {

    private String sharedValue;

    @BeforeAll
    void initializeOnce() {
        sharedValue = "initialized";
    }

    @Test
    void firstTest() {
        org.junit.jupiter.api.Assertions.assertEquals(
                "initialized", sharedValue);
    }

    @Test
    void secondTest() {
        org.junit.jupiter.api.Assertions.assertEquals(
                "initialized", sharedValue);
    }
}
~~~

Khi dùng PER_CLASS:

- JUnit chỉ tạo một instance cho cả test class.
- @BeforeAll và @AfterAll có thể là phương thức instance, không cần static.
- Các field instance được chia sẻ giữa các test method.
- Trạng thái thay đổi trong một test có thể ảnh hưởng đến test khác nếu không được đặt lại.
- Nếu bật chạy song song, việc nhiều test cùng thay đổi state dùng chung có thể tạo ra race condition.

PER_CLASS hữu ích khi cần dùng instance method cho BeforeAll/AfterAll hoặc khi có lý do rõ ràng để chia sẻ fixture. Tuy nhiên, hãy chủ động khôi phục trạng thái trong BeforeEach và tránh để thứ tự chạy test quyết định kết quả.

Có thể đặt mặc định toàn cục trong file junit-platform.properties:

~~~properties
junit.jupiter.testinstance.lifecycle.default = per_class
~~~

Thay đổi mặc định toàn cục có thể ảnh hưởng đến nhiều test class. Nếu chỉ một lớp cần PER_CLASS, đặt @TestInstance trực tiếp trên lớp đó sẽ làm ý định dễ nhìn thấy hơn.

### So sánh hai chế độ

| Đặc điểm | PER_METHOD (mặc định) | PER_CLASS |
|---|---|---|
| Số instance | Một instance cho mỗi test method | Một instance cho cả lớp |
| Field instance | Được khởi tạo lại theo test method | Được chia sẻ giữa các test |
| @BeforeAll mặc định | static | Có thể là instance method |
| @AfterAll mặc định | static | Có thể là instance method |
| Nguy cơ state leak qua field instance | Thấp hơn | Cao hơn nếu không reset |
| Phù hợp khi | Cần test độc lập, fixture riêng | Cần lifecycle instance hoặc chia sẻ state có chủ đích |

Dù dùng chế độ nào, static field, database, filesystem và dịch vụ bên ngoài vẫn có thể tạo ra trạng thái dùng chung. PER_METHOD không tự động cô lập toàn bộ môi trường chạy test.

## 8. Quy tắc khai báo phương thức lifecycle

Các phương thức được đánh dấu bằng @BeforeEach, @AfterEach, @BeforeAll và @AfterAll phải tuân theo quy tắc của JUnit Jupiter:

- Phải trả về void.
- Không được khai báo private.
- Có thể khai báo package-private, protected hoặc public.
- Có thể khai báo throws nếu thao tác setup hoặc cleanup phát sinh checked exception.
- Có thể nhận tham số nếu có ParameterResolver hỗ trợ.
- @BeforeEach và @AfterEach là instance method.
- @BeforeAll và @AfterAll là static theo mặc định, trừ khi test class dùng PER_CLASS.

JUnit cũng cung cấp các tham số tích hợp sẵn như TestInfo và TestReporter. Ví dụ:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestInfo;

class UserServiceTest {

    @BeforeEach
    void prepare(TestInfo testInfo) {
        System.out.println(
                "Preparing: " + testInfo.getDisplayName());
    }
}
~~~

TestInfo có thể cung cấp display name, tên phương thức và thông tin về tag của test hiện tại. Cơ chế này hữu ích khi muốn ghi nhận thông tin test mà không cần tự quản lý biến toàn cục.

## 9. Thứ tự lifecycle khi có kế thừa và @Nested

JUnit Jupiter hỗ trợ test class kế thừa từ superclass và test class lồng nhau bằng @Nested. Lifecycle callback có quy tắc để setup và cleanup diễn ra theo thứ tự hợp lý.

### Kế thừa từ superclass

Nếu superclass và subclass cùng khai báo lifecycle method:

- @BeforeAll trong superclass chạy trước @BeforeAll trong subclass.
- @BeforeEach trong superclass chạy trước @BeforeEach trong subclass.
- @AfterEach trong subclass chạy trước @AfterEach trong superclass.
- @AfterAll trong subclass chạy trước @AfterAll trong superclass.

Quy tắc này giúp lớp cha chuẩn bị phần fixture chung trước, còn lớp con có thể bổ sung fixture riêng. Khi kết thúc, lớp con giải phóng phần riêng trước khi lớp cha giải phóng phần chung.

~~~java
abstract class BaseServiceTest {

    @BeforeEach
    void prepareBaseFixture() {
        System.out.println("Base setup");
    }

    @AfterEach
    void cleanBaseFixture() {
        System.out.println("Base cleanup");
    }
}

class PaymentServiceTest extends BaseServiceTest {

    @BeforeEach
    void preparePaymentFixture() {
        System.out.println("Payment setup");
    }

    @AfterEach
    void cleanPaymentFixture() {
        System.out.println("Payment cleanup");
    }

    @Test
    void processesPayment() {
        // Kiểm tra hành vi thanh toán.
    }
}
~~~

Với test trên, thứ tự setup là Base setup rồi Payment setup. Thứ tự cleanup là Payment cleanup rồi Base cleanup.

### Sử dụng @Nested

Một lớp @Nested gom các test liên quan vào một nhóm, thường để mô tả những trạng thái hoặc tình huống của cùng một đối tượng.

Lifecycle của lớp bên ngoài vẫn áp dụng cho test nằm trong lớp lồng nhau. Với mỗi test trong lớp nested, setup của lớp ngoài chạy trước setup của lớp nested; cleanup của lớp nested chạy trước cleanup của lớp ngoài.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class OrderServiceTest {

    @BeforeEach
    void prepareOrderService() {
        System.out.println("Outer setup");
    }

    @Nested
    class WhenOrderIsPaid {

        @BeforeEach
        void preparePaidOrder() {
            System.out.println("Nested setup");
        }

        @Test
        void cannotCancelPaidOrder() {
            // Kiểm tra quy tắc hủy đơn đã thanh toán.
        }
    }
}
~~~

Nếu cần khai báo @BeforeAll hoặc @AfterAll trong nested test class, hãy dùng vòng đời PER_CLASS cho lớp nested theo quy định của JUnit Jupiter. Điều này cho phép callback của nested class là instance method.

### Nhiều lifecycle method trong cùng một lớp

Có thể khai báo nhiều phương thức cùng mang @BeforeEach hoặc @AfterEach. JUnit có cơ chế sắp xếp xác định, nhưng thứ tự giữa các phương thức cùng loại trong một lớp được cố ý thiết kế để không tạo ra một thứ tự dễ dựa vào như thứ tự alphabet.

Không nên viết test mà setupA bắt buộc chạy trước setupB chỉ vì tên phương thức hoặc vị trí khai báo. Nếu hai bước có quan hệ phụ thuộc, hãy gọi chúng theo đúng thứ tự trong một phương thức setup duy nhất hoặc đóng gói thành một phương thức trợ giúp rõ ràng.

## 10. Không phụ thuộc vào thứ tự thực thi test

JUnit Jupiter không bảo đảm các test method sẽ chạy theo thứ tự mà lập trình viên viết trong file. Mặc định, thứ tự được xác định theo một cơ chế ổn định nhưng cố ý không dễ dự đoán.

Một thiết kế test tốt cần bảo đảm:

- Mỗi test có thể chạy độc lập.
- Test không cần một test khác chạy trước để tạo dữ liệu.
- Kết quả của test không phụ thuộc vào giá trị field mà test khác để lại.
- Test có thể chạy riêng lẻ hoặc trong toàn bộ test suite mà vẫn cho kết quả nhất quán.

JUnit có @TestMethodOrder và @Order để chỉ định thứ tự khi thực sự cần. Tuy nhiên, nếu test A phải chạy trước test B để B có dữ liệu, hãy cân nhắc chuyển hai bước thành một scenario rõ ràng hoặc tạo fixture riêng cho B. Dùng thứ tự test để che giấu sự phụ thuộc thường khiến suite khó chạy song song và khó chẩn đoán khi có lỗi.

## 11. Vòng đời với @ParameterizedTest, @RepeatedTest và @TestFactory

Ngoài @Test, JUnit Jupiter còn có các loại test khác. Hiểu cách lifecycle áp dụng giúp tránh giả định sai về số lần setup và cleanup.

### @ParameterizedTest

Một parameterized test chạy cùng một phương thức với nhiều bộ tham số. Mỗi invocation có lifecycle setup và cleanup tương ứng.

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class UsernameValidatorTest {

    private UsernameValidator validator;

    @BeforeEach
    void setUp() {
        validator = new UsernameValidator();
    }

    @ParameterizedTest
    @ValueSource(strings = {"alice", "bob", "carol"})
    void acceptsValidUsernames(String username) {
        assertTrue(validator.isValid(username));
    }
}
~~~

Với ba giá trị trong ValueSource, phương thức test được thực thi ba lần và setup được thực hiện cho từng invocation.

### @RepeatedTest

@RepeatedTest chạy một test method nhiều lần theo số lần chỉ định. BeforeEach và AfterEach được thực thi quanh mỗi repetition.

~~~java
@RepeatedTest(3)
void generatesUniqueIdentifier() {
    String id = identifierGenerator.nextId();

    assertNotNull(id);
}
~~~

Mỗi repetition có thể dùng TestInfo hoặc RepetitionInfo để lấy thông tin về lần lặp hiện tại. Không nên để repetition trước làm thay đổi trạng thái khiến repetition sau phải dựa vào kết quả đó, trừ khi mục tiêu của test thực sự là kiểm tra chuỗi thao tác có trạng thái.

### @TestFactory và dynamic tests

@TestFactory là một phương thức tạo ra các dynamic test. Một điểm khác biệt quan trọng là @BeforeEach và @AfterEach được áp dụng quanh phương thức factory, không chạy riêng quanh từng dynamic test được tạo ra từ factory đó.

~~~java
import java.util.stream.Stream;

import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;

class DynamicNumberTest {

    @TestFactory
    Stream<DynamicTest> positiveNumbersAreAccepted() {
        return Stream.of(1, 2, 3)
                .map(number -> DynamicTest.dynamicTest(
                        "accepts " + number,
                        () -> org.junit.jupiter.api.Assertions
                                .assertTrue(number > 0)
                ));
    }
}
~~~

Nếu từng dynamic test cần một fixture mới hoặc cần cleanup riêng, hãy tạo và giải phóng fixture ngay bên trong executable của dynamic test, hoặc sử dụng extension/cơ chế quản lý tài nguyên phù hợp. Không giả định rằng mỗi dynamic test sẽ tự động nhận một chu trình BeforeEach/AfterEach như một phương thức @Test độc lập.

## 12. Sử dụng lifecycle trong bài kiểm thử Spring

Spring TestContext Framework tích hợp với JUnit Jupiter thông qua SpringExtension. Các annotation kiểm thử Spring như @SpringBootTest, @WebMvcTest và @DataJpaTest đã tích hợp SpringExtension. Với test class dùng cấu hình Spring Framework trực tiếp, có thể đăng ký extension bằng @ExtendWith(SpringExtension.class) hoặc dùng annotation cấu hình phù hợp như @SpringJUnitConfig.

SpringExtension kết nối vòng đời JUnit với việc chuẩn bị test instance, dependency injection và các callback của Spring TestContext.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class GreetingServiceIntegrationTest {

    @Autowired
    private GreetingService greetingService;

    private String input;

    @BeforeEach
    void prepareInput() {
        input = "Ada";
    }

    @Test
    void returnsGreetingForUser() {
        assertEquals("Hello, Ada", greetingService.greet(input));
    }
}
~~~

Trong ví dụ này, Spring chuẩn bị test instance và inject GreetingService. Phương thức @BeforeEach có thể sử dụng dependency đã được inject để chuẩn bị dữ liệu cho test.

### Dùng @BeforeAll trong Spring test

Theo mặc định, @BeforeAll là static nên không thể truy cập field instance như một dependency được inject bằng @Autowired. Có hai cách xử lý tùy mục đích:

- Nếu callback chỉ cần thao tác tài nguyên static hoặc dữ liệu độc lập với test instance, giữ phương thức static.
- Nếu thực sự cần dùng field instance trong BeforeAll/AfterAll, cấu hình test class với @TestInstance(TestInstance.Lifecycle.PER_CLASS) để callback có thể là instance method.

Ví dụ:

~~~java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class SharedSpringFixtureTest {

    @Autowired
    private ReferenceDataService referenceDataService;

    @BeforeAll
    void prepareReferenceData() {
        referenceDataService.initializeReadOnlyData();
    }

    @Test
    void usesReferenceData() {
        // Kiểm tra hành vi sử dụng dữ liệu tham chiếu.
    }
}
~~~

Với PER_CLASS, test instance được tạo và Spring có cơ hội chuẩn bị instance trước khi các callback của lớp chạy. Dù vậy, hãy chỉ dùng dữ liệu chia sẻ khi nó ổn định và không bị các test sửa đổi ngoài dự kiến. Dữ liệu riêng cho từng test vẫn nên được chuẩn bị trong BeforeEach.

### Quan hệ với transaction của Spring Test

Khi một Spring test method được đánh dấu @Transactional và được TestContext quản lý transaction, Spring thường bắt đầu transaction cho test và rollback sau khi test hoàn tất. Điều này giúp cô lập thay đổi dữ liệu trong nhiều bài kiểm thử persistence.

Một vài điểm cần nhớ:

- @BeforeEach là nơi phù hợp để chuẩn bị dữ liệu thuộc từng test transaction.
- @AfterEach có thể thực hiện cleanup thuộc cùng phạm vi test method.
- @BeforeAll và @AfterAll là callback cấp lớp, không nằm trong transaction riêng của từng test method.
- Rollback transaction không tự hoàn tác tác động bên ngoài database, ví dụ email đã gửi, file đã ghi hoặc request đã gửi sang dịch vụ khác.
- Nếu test commit transaction hoặc sử dụng cơ chế transaction khác, cần hiểu rõ tác động đến dữ liệu dùng chung.

Đừng giả định rằng chỉ cần dùng PER_METHOD là mọi dữ liệu trong database tự được làm mới. Vòng đời instance JUnit và vòng đời transaction Spring là hai cơ chế khác nhau. Hãy chọn đúng cơ chế cô lập cho từng loại state.

## 13. Những lỗi thường gặp và cách xử lý

### Dùng @BeforeAll nhưng quên static

Với lifecycle mặc định PER_METHOD, phương thức @BeforeAll instance không hợp lệ. Hãy khai báo static hoặc chuyển lớp sang PER_CLASS khi có lý do sử dụng instance callback.

### Dùng @AfterAll để dọn dữ liệu của từng test

Nếu mỗi test tạo dữ liệu riêng, chờ đến cuối lớp mới xóa có thể khiến test sau đọc thấy dữ liệu cũ. Dùng @AfterEach hoặc transaction rollback để xử lý theo từng test.

### Chia sẻ field có thể thay đổi trong PER_CLASS

Một test thêm phần tử vào list dùng chung, test tiếp theo có thể nhận list đã thay đổi. Hãy tạo fixture mới trong BeforeEach, xóa state sau test hoặc dùng dữ liệu bất biến.

### Cho rằng test luôn chạy theo thứ tự khai báo

Test có thể chạy theo thứ tự khác. Nếu test chỉ thành công khi một test khác chạy trước, hãy loại bỏ phụ thuộc đó bằng fixture riêng hoặc một scenario được tổ chức rõ ràng.

### Khởi tạo tài nguyên ở BeforeEach nhưng không đóng ở AfterEach

Tạo server, stream hoặc file ở mỗi test mà không giải phóng sẽ khiến tài nguyên tích lũy, làm test chậm hoặc thất bại ngẫu nhiên. Ghép điểm tạo và điểm giải phóng theo cùng phạm vi lifecycle.

### Dùng BeforeAll cho dữ liệu có thể bị thay đổi

Dữ liệu tạo một lần rồi dùng chung có thể làm các test ảnh hưởng lẫn nhau. Chỉ chia sẻ dữ liệu bất biến hoặc có quy trình reset đáng tin cậy.

### Cho rằng @AfterEach chỉ chạy khi test thành công

Cleanup vẫn được gọi khi test thất bại và cũng có thể được gọi sau khi setup thất bại một phần. Hãy viết cleanup có kiểm tra trạng thái để tránh lỗi thứ cấp che khuất nguyên nhân ban đầu.

### Đặt quá nhiều logic vào lifecycle method

Một setup lớn có thể khiến người đọc không biết test thực sự kiểm tra điều gì. Chỉ giữ các bước chung cho nhiều test trong lifecycle method; dữ liệu đặc thù và hành động chính nên nằm trong test tương ứng.

## 14. Cách chọn annotation theo nhu cầu

| Nhu cầu | Annotation phù hợp | Phạm vi |
|---|---|---|
| Đánh dấu hành vi cần kiểm tra | @Test | Một phương thức test |
| Tạo fixture mới hoặc reset state trước test | @BeforeEach | Mỗi lần thực thi test |
| Đóng tài nguyên hoặc dọn dữ liệu sau test | @AfterEach | Mỗi lần thực thi test |
| Khởi tạo tài nguyên dùng chung cho cả lớp | @BeforeAll | Một lần mỗi test class |
| Giải phóng tài nguyên dùng chung của lớp | @AfterAll | Một lần mỗi test class |
| Chạy cùng test với nhiều dữ liệu | @ParameterizedTest | Một invocation cho mỗi bộ tham số |
| Lặp lại cùng test nhiều lần | @RepeatedTest | Một invocation cho mỗi repetition |
| Tạo test động từ dữ liệu lúc chạy | @TestFactory | Một lần gọi factory; dynamic nodes có lifecycle riêng |

Có thể dùng các câu hỏi sau để chọn đúng nơi đặt code:

1. Đây có phải hành vi cần xác nhận của hệ thống không? Nếu có, đặt trong phương thức @Test.
2. Bước này có cần chạy lại để mỗi test có trạng thái ban đầu độc lập không? Nếu có, dùng @BeforeEach.
3. Tài nguyên này cần được giải phóng ngay sau từng test không? Nếu có, dùng @AfterEach.
4. Tài nguyên có thể được tạo một lần và chia sẻ an toàn trong cả lớp không? Nếu có, cân nhắc @BeforeAll.
5. Tài nguyên dùng chung đó cần được đóng khi lớp hoàn tất không? Nếu có, dùng @AfterAll.
6. Callback cấp lớp có cần truy cập field instance không? Nếu có, cân nhắc PER_CLASS và đánh giá tác động của state dùng chung.

## Kết luận

@Test xác định phương thức kiểm thử; @BeforeEach và @AfterEach quản lý phần chuẩn bị và dọn dẹp theo từng lần thực thi; @BeforeAll và @AfterAll quản lý tài nguyên ở phạm vi cả lớp. Mặc định PER_METHOD giúp các test có instance riêng, còn PER_CLASS cho phép chia sẻ instance và dùng callback cấp lớp không static. Trong dự án Spring, SpringExtension kết nối vòng đời JUnit với dependency injection và TestContext, trong khi transaction và trạng thái bên ngoài vẫn cần được quản lý theo cơ chế riêng. Khi đặt mỗi thao tác vào đúng phạm vi lifecycle, test sẽ độc lập hơn, ít rò rỉ tài nguyên và dễ bảo trì hơn.
