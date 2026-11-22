# Nested test để nhóm các tình huống

JUnit Jupiter cung cấp annotation **@Nested** để tổ chức các test method thành những nhóm có quan hệ theo ngữ cảnh. Thay vì đặt tất cả test của một lớp vào cùng một danh sách dài, ta có thể mô tả trạng thái hoặc điều kiện chung ở một lớp lồng bên trong, rồi đặt các hành vi tương ứng vào nhóm đó.

Ví dụ, khi kiểm thử giỏ hàng, có thể chia tình huống thành:

- Khi giỏ hàng trống: tổng tiền bằng không, không thể thanh toán.
- Khi giỏ hàng có sản phẩm: tổng tiền được tính đúng, có thể thanh toán.
- Khi giỏ hàng đã hết hiệu lực: không thể tiếp tục thanh toán.

Các nhóm này vẫn thuộc cùng một test class và cùng kiểm tra một thành phần, nhưng cấu trúc lồng nhau giúp người đọc hiểu điều kiện của từng nhóm trước khi đọc các test method bên trong.

## 1. @Nested giải quyết vấn đề gì?

Một test class có thể tăng nhanh số lượng method khi một thành phần có nhiều trạng thái và mỗi trạng thái lại có nhiều hành vi cần xác nhận. Nếu đặt tất cả method ngang hàng, tên test phải lặp lại điều kiện:

~~~java
class ShoppingCartTest {

    @Test
    void emptyCartHasZeroTotal() {
        // ...
    }

    @Test
    void emptyCartCannotBeCheckedOut() {
        // ...
    }

    @Test
    void cartWithItemsCalculatesTotal() {
        // ...
    }

    @Test
    void cartWithItemsCanBeCheckedOut() {
        // ...
    }
}
~~~

Các test vẫn chạy được, nhưng điều kiện chung nằm rải rác trong tên method. Khi dùng **@Nested**, điều kiện được đưa lên cấp nhóm:

~~~java
class ShoppingCartTest {

    @Nested
    class WhenCartIsEmpty {
        @Test
        void hasZeroTotal() {
            // ...
        }

        @Test
        void cannotBeCheckedOut() {
            // ...
        }
    }

    @Nested
    class WhenCartContainsItems {
        @Test
        void calculatesTotal() {
            // ...
        }

        @Test
        void canBeCheckedOut() {
            // ...
        }
    }
}
~~~

Khi đọc cấu trúc này, người đọc thấy ngay hai ngữ cảnh chính. Tên method bên trong chỉ cần mô tả hành vi cụ thể vì điều kiện đã được biểu đạt bởi tên nhóm.

**@Nested** có ba lợi ích chính:

1. **Nhóm theo ngữ cảnh:** những test có cùng trạng thái ban đầu hoặc cùng điều kiện nghiệp vụ nằm cạnh nhau.
2. **Tái sử dụng phần chuẩn bị chung:** lớp ngoài có thể thiết lập fixture nền; lớp lồng có thể bổ sung dữ liệu riêng cho tình huống.
3. **Hiển thị cấu trúc phân cấp:** IDE và báo cáo test có thể trình bày nhóm và test method theo quan hệ cha – con.

**@Nested** chỉ tổ chức cấu trúc kiểm thử. Nó không tự tạo database, không tự mở transaction riêng và cũng không biến các test thành một workflow phải chạy theo thứ tự.

## 2. Quy tắc cơ bản của lớp lồng trong JUnit Jupiter

Một lớp dùng với **@Nested** phải là **non-static inner class** của test class bao quanh. Lớp đó có thể truy cập các field và method của instance lớp ngoài theo quy tắc truy cập của Java.

~~~java
class AccountServiceTest {

    private AccountService accountService;

    @BeforeEach
    void setUp() {
        accountService = new AccountService();
    }

    @Nested
    class WhenAccountIsActive {

        @Test
        void allowsTransfer() {
            // Có thể truy cập accountService của lớp ngoài.
            assertDoesNotThrow(() -> accountService.transfer(/* dữ liệu */));
        }
    }
}
~~~

Ví dụ trên minh họa quan hệ truy cập; lời gọi transfer và kiểu dữ liệu thực tế phụ thuộc vào API của ứng dụng. Các lớp lồng dùng cho test thường để package-private, giống cách JUnit Jupiter cho phép test class và test method không cần khai báo public.

Một số quy tắc cần nhớ:

- Lớp lồng phải có annotation **@Nested** để JUnit Jupiter nhận diện nó là nested test class.
- Lớp lồng không được khai báo static.
- Lớp lồng có thể chứa các test method, các callback lifecycle và những lớp **@Nested** khác.
- Có thể tạo nhiều cấp lồng nhau, nhưng mỗi cấp nên thể hiện một điều kiện có ý nghĩa.
- Các test method trong lớp lồng vẫn là test độc lập; chúng không phụ thuộc vào việc method khác đã chạy trước hay chưa.

Không cần thêm **@Test** lên lớp lồng. Annotation **@Nested** xác định vai trò nhóm của lớp đó; từng method bên trong dùng **@Test**, **@ParameterizedTest** hoặc loại test phù hợp.

## 3. Ví dụ đầy đủ: nhóm theo trạng thái của giỏ hàng

Giả sử ứng dụng có một ShoppingCart với các hành vi: tính tổng tiền, thêm sản phẩm và thanh toán. Ta muốn kiểm tra hai trạng thái chính là giỏ hàng trống và giỏ hàng có sản phẩm.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class ShoppingCartTest {

    private ShoppingCart cart;

    @BeforeEach
    void createEmptyCart() {
        cart = new ShoppingCart();
    }

    @Nested
    @DisplayName("Khi giỏ hàng trống")
    class WhenCartIsEmpty {

        @Test
        @DisplayName("Tổng tiền bằng không")
        void hasZeroTotal() {
            assertEquals(BigDecimal.ZERO, cart.total());
        }

        @Test
        @DisplayName("Không cho phép thanh toán")
        void rejectsCheckout() {
            assertThrows(
                EmptyCartException.class,
                () -> cart.checkout()
            );
        }
    }

    @Nested
    @DisplayName("Khi giỏ hàng có sản phẩm")
    class WhenCartContainsItems {

        @BeforeEach
        void addProducts() {
            cart.addItem("book", new BigDecimal("50.00"), 2);
            cart.addItem("pen", new BigDecimal("10.00"), 1);
        }

        @Test
        @DisplayName("Tính tổng tiền của các sản phẩm")
        void calculatesTotal() {
            assertEquals(new BigDecimal("110.00"), cart.total());
        }

        @Test
        @DisplayName("Cho phép thanh toán")
        void allowsCheckout() {
            assertDoesNotThrow(() -> cart.checkout());
        }
    }
}
~~~

Các lớp ShoppingCart, EmptyCartException và các method nghiệp vụ trong ví dụ là mô hình minh họa. Điểm cần chú ý là cấu trúc chuẩn bị:

- createEmptyCart() ở lớp ngoài chạy trước mỗi test, tạo một giỏ hàng mới.
- Với nhóm WhenCartIsEmpty, không cần chuẩn bị thêm vì giỏ hàng đã ở trạng thái trống.
- Với nhóm WhenCartContainsItems, addProducts() bổ sung sản phẩm trước mỗi test thuộc nhóm đó.
- Mỗi test chỉ kiểm tra một hành vi của trạng thái tương ứng.

Nhờ vậy, phần chuẩn bị chung không bị lặp lại trong từng method, còn dữ liệu đặc thù của nhóm vẫn nằm ngay tại nơi định nghĩa nhóm.

## 4. Vòng đời của lớp ngoài và lớp lồng

Một điểm quan trọng khi dùng **@Nested** là hiểu thứ tự các callback lifecycle. JUnit Jupiter áp dụng callback của lớp bao quanh và lớp lồng theo thứ tự phân cấp.

Với một test method trong lớp lồng:

1. Callback **@BeforeEach** của lớp ngoài được thực hiện.
2. Callback **@BeforeEach** của lớp lồng được thực hiện.
3. Test method được chạy.
4. Callback **@AfterEach** của lớp lồng được thực hiện.
5. Callback **@AfterEach** của lớp ngoài được thực hiện.

Điều đó cho phép lớp ngoài thiết lập fixture nền và lớp lồng bổ sung điều kiện riêng:

~~~java
class PaymentServiceTest {

    private PaymentService paymentService;
    private FakePaymentGateway gateway;

    @BeforeEach
    void setUpBaseEnvironment() {
        gateway = new FakePaymentGateway();
        paymentService = new PaymentService(gateway);
    }

    @Nested
    class WhenGatewayAcceptsPayment {

        @BeforeEach
        void configureAcceptedPayment() {
            gateway.acceptNextPayment();
        }

        @Test
        void returnsSuccessfulResult() {
            // paymentService và gateway đã được chuẩn bị.
        }
    }

    @Nested
    class WhenGatewayDeclinesPayment {

        @BeforeEach
        void configureDeclinedPayment() {
            gateway.declineNextPayment();
        }

        @Test
        void returnsDeclinedResult() {
            // Mỗi test thuộc nhóm này nhận trạng thái decline.
        }
    }
}
~~~

Ví dụ giả định có fake gateway cho phép điều khiển kết quả. Callback ở lớp ngoài tạo môi trường mới; callback trong từng nhóm chọn kết quả phù hợp. Vì test method được chạy độc lập, mỗi test không cần dựa vào việc nhóm khác đã cấu hình gateway.

### 4.1. Phân chia việc chuẩn bị

Một cách phân chia dễ hiểu là:

| Vị trí | Nên chuẩn bị |
|---|---|
| Constructor hoặc field initializer | Giá trị bất biến, đơn giản, không phụ thuộc lifecycle của test |
| **@BeforeEach** lớp ngoài | SUT, mock/fake và trạng thái nền dùng cho mọi nhóm |
| **@BeforeEach** lớp lồng | Trạng thái đặc thù của nhóm |
| Test method | Dữ liệu chỉ dùng trong một kịch bản và hành động cần kiểm tra |
| **@AfterEach** lớp lồng | Dọn tài nguyên chỉ do nhóm đó tạo ra |
| **@AfterEach** lớp ngoài | Dọn tài nguyên nền do lớp ngoài tạo ra |

Không nên đưa mọi thao tác vào **@BeforeEach** của lớp ngoài. Nếu nhóm có điều kiện khác nhau, việc chuẩn bị ở lớp lồng giúp người đọc thấy điều kiện đó ngay trong ngữ cảnh liên quan.

### 4.2. @BeforeAll và @AfterAll

Theo lifecycle mặc định **PER_METHOD**, các method **@BeforeAll** và **@AfterAll** phải là static. Với nested test class, muốn dùng **@BeforeAll** hoặc **@AfterAll** không static trong lớp lồng, test instance lifecycle liên quan phải là **PER_CLASS**.

Có thể cấu hình lifecycle bằng **@TestInstance(TestInstance.Lifecycle.PER_CLASS)**. Khi đó, một instance được dùng cho các test method trong class tương ứng và callback cấp lớp có thể dùng instance method:

~~~java
@Nested
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class WhenUsingSharedResource {

    @BeforeAll
    void openSharedResource() {
        // Chuẩn bị tài nguyên dùng chung cho nhóm.
    }

    @AfterAll
    void closeSharedResource() {
        // Giải phóng tài nguyên sau khi nhóm hoàn tất.
    }
}
~~~

Chỉ dùng **PER_CLASS** khi có lý do rõ ràng, chẳng hạn cần quản lý một tài nguyên tốn kém cho cả nhóm. Vì nhiều test method dùng cùng một instance, field mutable có thể giữ lại trạng thái giữa các test. Nếu dùng lifecycle này, cần tự bảo đảm mỗi test không để lại trạng thái ảnh hưởng đến test tiếp theo.

Thông thường, **@BeforeEach** là lựa chọn phù hợp hơn cho dữ liệu kịch bản. Nó giúp mỗi test nhận một trạng thái khởi đầu rõ ràng và giảm nguy cơ phụ thuộc thứ tự.

## 5. Nhóm theo điều kiện, rồi nhóm tiếp theo theo trạng thái con

JUnit Jupiter cho phép lồng nhiều cấp. Điều này hữu ích khi một hành vi phụ thuộc vào nhiều tầng điều kiện.

Ví dụ với tài khoản:

- Tình huống chung: tài khoản đang hoạt động.
  - Khi số dư đủ: chuyển tiền thành công.
  - Khi số dư không đủ: chuyển tiền bị từ chối.
- Tình huống chung: tài khoản bị khóa.
  - Không cho phép chuyển tiền.
  - Không cho phép rút tiền.

~~~java
class TransferServiceTest {

    private TransferService transferService;
    private Account source;
    private Account destination;

    @BeforeEach
    void setUpAccounts() {
        source = Account.activeWithBalance(new BigDecimal("500.00"));
        destination = Account.activeWithBalance(new BigDecimal("100.00"));
        transferService = new TransferService();
    }

    @Nested
    @DisplayName("Khi tài khoản nguồn đang hoạt động")
    class WhenSourceAccountIsActive {

        @Nested
        @DisplayName("Khi số dư đủ")
        class WhenBalanceIsSufficient {

            @Test
            void transfersAmount() {
                // Arrange
                BigDecimal amount = new BigDecimal("200.00");

                // Act
                transferService.transfer(source, destination, amount);

                // Assert
                assertEquals(new BigDecimal("300.00"), source.balance());
                assertEquals(new BigDecimal("300.00"), destination.balance());
            }
        }

        @Nested
        @DisplayName("Khi số dư không đủ")
        class WhenBalanceIsInsufficient {

            @Test
            void rejectsTransfer() {
                // Arrange
                BigDecimal amount = new BigDecimal("900.00");

                // Act + Assert
                assertThrows(
                    InsufficientBalanceException.class,
                    () -> transferService.transfer(source, destination, amount)
                );
            }
        }
    }
}
~~~

Ví dụ tập trung vào cách biểu diễn quan hệ giữa các điều kiện; các factory method và API của Account là minh họa. Cấp ngoài nhất chuẩn bị tài khoản nền, cấp giữa xác định trạng thái tài khoản, cấp trong cùng mô tả trường hợp cụ thể.

Không nên lồng lớp chỉ để tạo nhiều tầng tiêu đề. Nếu nhóm con không có điều kiện hoặc ý nghĩa riêng, một cấp **@Nested** là đủ. Cấu trúc quá sâu khiến người đọc phải mở nhiều lớp mới hiểu được một test method.

## 6. Dùng @DisplayName để tên nhóm dễ đọc

Tên class Java nên mô tả điều kiện bằng từ ngữ nhất quán, ví dụ **WhenAccountIsLocked**. Annotation **@DisplayName** cho phép cung cấp nhãn thân thiện hơn trong IDE và báo cáo:

~~~java
@Nested
@DisplayName("Khi tài khoản bị khóa")
class WhenAccountIsLocked {

    @Test
    @DisplayName("Từ chối yêu cầu chuyển tiền")
    void rejectsTransfer() {
        // ...
    }
}
~~~

Có thể đặt **@DisplayName** cho cả test class ngoài, lớp lồng và từng method. Nên dùng tên nhóm để mô tả điều kiện, còn tên method mô tả hành vi hoặc kết quả. Tránh lặp lại nguyên văn cùng một câu ở cả tên nhóm và tên method.

Ví dụ cấu trúc hiển thị có thể được hiểu như sau:

~~~text
TransferServiceTest
└── Khi tài khoản nguồn đang hoạt động
    ├── Khi số dư đủ
    │   └── Chuyển tiền thành công
    └── Khi số dư không đủ
        └── Từ chối giao dịch
~~~

Tên hiển thị là nhãn phục vụ người đọc. Chúng không thay đổi cách JUnit chọn test hay điều kiện thực thi.

## 7. Kết hợp @Nested với các loại test khác của JUnit Jupiter

Lớp lồng là một test class bình thường về nhiều mặt, vì vậy có thể chứa các loại test method được JUnit Jupiter hỗ trợ.

### 7.1. Parameterized test trong một nhóm

Khi một nhóm có nhiều giá trị đầu vào cùng kiểm tra một quy tắc, có thể đặt **@ParameterizedTest** bên trong lớp lồng:

~~~java
@Nested
@DisplayName("Khi số lượng không hợp lệ")
class WhenQuantityIsInvalid {

    @ParameterizedTest
    @ValueSource(ints = {0, -1, -5})
    void rejectsQuantity(int quantity) {
        assertThrows(
            InvalidQuantityException.class,
            () -> orderService.create(commandWithQuantity(quantity))
        );
    }
}
~~~

Nhóm cung cấp ngữ cảnh “số lượng không hợp lệ”; parameterized test cung cấp nhiều dữ liệu đại diện cho cùng quy tắc. Nếu các giá trị có kết quả hoặc ý nghĩa khác nhau, nên dùng test riêng hoặc nguồn tham số có tên để báo cáo dễ hiểu hơn.

### 7.2. Tag cho việc lọc test

**@Tag** có thể được dùng trên test class, nested class hoặc method để đánh dấu nhóm test theo mục đích chạy, ví dụ **slow**, **database** hoặc **integration**:

~~~java
@Nested
@Tag("database")
class WhenPersistingOrder {

    @Test
    void storesOrder() {
        // ...
    }
}
~~~

**@Nested** và **@Tag** có mục đích khác nhau:

- **@Nested** mô tả quan hệ cấu trúc và ngữ cảnh giữa các test.
- **@Tag** gắn nhãn để cấu hình lựa chọn hoặc loại trừ test khi chạy.

Một nhóm có thể vừa được tổ chức bằng **@Nested**, vừa được gắn tag nếu các test trong nhóm có cùng yêu cầu chạy.

### 7.3. Các annotation khác

Các annotation như **@Disabled**, **@Timeout**, **@RepeatedTest** và **@DisplayName** vẫn có thể được dùng tùy theo mục đích của test. Hãy đặt annotation ở cấp class khi chính sách áp dụng cho toàn nhóm, hoặc ở cấp method khi chỉ một test cần hành vi đó. Không nên dùng annotation để che giấu một nhóm test đang thất bại hoặc để biến test không ổn định thành test bị bỏ qua lâu dài.

## 8. Dùng @Nested trong Spring Framework Test

JUnit Jupiter chịu trách nhiệm phát hiện và thực thi lớp lồng. Spring TestContext có thể cung cấp context, dependency injection và các chức năng kiểm thử Spring cho test class đó.

Ví dụ:

~~~java
@SpringBootTest
class CustomerServiceIntegrationTest {

    @Autowired
    private CustomerService customerService;

    @Nested
    @DisplayName("Khi khách hàng đang hoạt động")
    class WhenCustomerIsActive {

        @Test
        void allowsProfileUpdate() {
            // Dùng customerService đã được inject từ Spring context.
        }
    }

    @Nested
    @DisplayName("Khi khách hàng bị khóa")
    class WhenCustomerIsLocked {

        @Test
        void rejectsProfileUpdate() {
            // Kiểm tra hành vi trong cùng ngữ cảnh Spring.
        }
    }
}
~~~

Trong ví dụ này, lớp ngoài khai báo cấu hình Spring và dependency. Các nested test class tổ chức kịch bản theo trạng thái khách hàng. Theo mặc định, cấu hình kiểm thử Spring từ lớp bao quanh được kế thừa cho nested test class.

### 8.1. Điều khiển kế thừa cấu hình với @NestedTestConfiguration

Spring Framework cung cấp **@NestedTestConfiguration** để điều khiển việc nested test class kế thừa cấu hình kiểm thử từ enclosing class. Mặc định là **INHERIT**, nghĩa là cấu hình Spring của lớp bao quanh được kế thừa. Khi cần nested class có cấu hình riêng, có thể chọn **OVERRIDE**:

~~~java
@SpringBootTest
class ApplicationIntegrationTest {

    @Nested
    class UsesApplicationContext {
        @Test
        void verifiesApplicationBean() {
            // ...
        }
    }

    @Nested
    @NestedTestConfiguration(
        NestedTestConfiguration.EnclosingConfiguration.OVERRIDE
    )
    @ContextConfiguration(classes = IsolatedTestConfiguration.class)
    class UsesIsolatedContext {

        @Test
        void verifiesIsolatedBean() {
            // ...
        }
    }
}
~~~

Ví dụ minh họa cách chọn chính sách kế thừa; cấu hình cụ thể cần phù hợp với test context của ứng dụng. **@NestedTestConfiguration** thuộc Spring TestContext và có từ Spring Framework 5.3. Khi dùng phiên bản Spring cũ hơn, cần kiểm tra khả năng hỗ trợ trước khi áp dụng.

Một số nguyên tắc khi kết hợp nested test với Spring:

- Đặt cấu hình chung như **@SpringBootTest** hoặc **@ContextConfiguration** ở lớp ngoài nếu mọi nhóm dùng cùng môi trường.
- Đặt dữ liệu kịch bản và thao tác mock theo nhóm hoặc test method, không biến lớp lồng thành nơi khởi tạo lại toàn bộ context không cần thiết.
- Nếu một nhóm cần context khác, xác định rõ chính sách kế thừa và cấu hình override.
- Nhớ rằng context cache của Spring phụ thuộc cấu hình context. Những cấu hình khác nhau có thể tạo context khác nhau và làm tăng thời gian chạy.
- Không giả định **@Nested** tự tạo transaction riêng. Transaction test được quyết định bởi cấu hình Spring Test và annotation giao dịch có hiệu lực.

## 9. @Nested khác gì với tách test class hoặc dùng @Tag?

Không phải mọi nhóm test đều cần lớp lồng. Chọn cách tổ chức dựa trên quan hệ giữa các tình huống và phạm vi cấu hình.

| Cách tổ chức | Phù hợp khi | Điểm cần cân nhắc |
|---|---|---|
| Test method ngang hàng | Số lượng test ít, điều kiện đơn giản | Tên method có thể phải lặp điều kiện |
| **@Nested** | Nhiều test cùng một thành phần nhưng khác ngữ cảnh hoặc trạng thái | Có thêm cấp lớp và quy tắc lifecycle |
| Tách thành nhiều test class | Nhóm có cấu hình, fixture hoặc trách nhiệm kiểm thử độc lập | Có thể phải chia sẻ helper hoặc cấu hình |
| **@Tag** | Cần lọc test theo loại hoặc chi phí chạy | Tag không tự tạo cấu trúc cha – con |

Ví dụ, các test cho service có thể nằm trong một class với các nested group theo trạng thái nghiệp vụ. Nhưng nếu test repository cần database riêng, test API cần server thật và test service chỉ cần mock, việc tách thành các test class có cấu hình riêng có thể rõ ràng hơn.

Một cách phân biệt hữu ích:

- Dùng **@Nested** khi câu hỏi là **“các test này thuộc những tình huống nào của cùng một đối tượng?”**
- Dùng nhiều test class khi câu hỏi là **“đây có phải các phạm vi kiểm thử hoặc môi trường khác nhau không?”**
- Dùng **@Tag** khi câu hỏi là **“cần chạy hoặc loại trừ những test nào?”**

Các cách này có thể phối hợp. Một test class có thể chứa nhiều nested group và mỗi group có tag riêng.

## 10. Những lỗi tổ chức thường gặp

### 10.1. Lớp lồng chỉ đổi tên nhưng không thêm ngữ cảnh

Một lớp như **NestedTests** hoặc **MoreTests** không giúp người đọc hiểu điều kiện của test. Hãy đặt tên theo trạng thái hoặc điều kiện, chẳng hạn **WhenAccountIsLocked** hay **WhenRequestIsInvalid**.

### 10.2. Lồng quá nhiều cấp

Nếu một test method nằm sâu trong nhiều lớp nhưng các lớp trung gian không bổ sung điều kiện có ý nghĩa, cấu trúc trở nên khó điều hướng. Chỉ tạo thêm cấp khi nó làm rõ một chiều phân loại thực sự.

### 10.3. Đưa quá nhiều dữ liệu đặc thù vào lớp ngoài

Nếu lớp ngoài luôn tạo một tài khoản bị khóa, nhóm “tài khoản đang hoạt động” phải sửa lại trạng thái hoặc tạo một tài khoản khác. Hãy để lớp ngoài tạo fixture nền trung tính; mỗi nhóm chịu trách nhiệm chuyển fixture sang trạng thái của mình.

### 10.4. Dùng trạng thái thay đổi giữa các test

Không để một test method thay đổi field dùng chung rồi kỳ vọng test kế tiếp nhận được trạng thái đó. Test có thể được chạy riêng, chạy song song hoặc theo thứ tự khác. Mỗi test cần tự chuẩn bị điều kiện của mình qua lifecycle callback hoặc helper.

### 10.5. Dùng thứ tự test để mô tả quy trình

Không nên tạo một nhóm gồm “bước 1 tạo tài khoản”, “bước 2 nạp tiền”, “bước 3 chuyển tiền” rồi yêu cầu các test chạy theo thứ tự. Nếu cần kiểm tra workflow, một test method có thể thực hiện toàn bộ chuỗi hành động cần thiết và xác nhận kết quả cuối. Các test độc lập khác vẫn nên tự tạo dữ liệu riêng.

### 10.6. Dùng @BeforeAll không đúng lifecycle

Trong nested class, callback cấp lớp có quy tắc về **PER_CLASS**. Nếu không thực sự cần tài nguyên dùng chung, dùng **@BeforeEach** sẽ đơn giản hơn và ít rủi ro chia sẻ trạng thái.

### 10.7. Lặp lại cấu hình Spring ở mọi nhóm

Nếu các nested group dùng chung một context, khai báo cấu hình ở lớp ngoài giúp giảm lặp. Nếu nhóm cần cấu hình khác, hãy thể hiện rõ việc override bằng cơ chế của Spring TestContext thay vì thêm annotation tùy tiện.

### 10.8. Nhầm nested test với nested production class

**@Nested** là cấu trúc dành cho test class. Không cần tạo lớp lồng trong mã production chỉ để phản chiếu cấu trúc test. Cấu trúc kiểm thử nên phục vụ cách diễn đạt kịch bản và không buộc thiết kế production phải có cùng hình dạng.

## 11. Đọc kết quả và xử lý lỗi trong nested test

Khi test thất bại, cấu trúc phân cấp giúp xác định ngữ cảnh trước khi đọc assertion. Một báo cáo có thể hiển thị đường dẫn dạng:

~~~text
ShoppingCartTest
└── Khi giỏ hàng có sản phẩm
    └── Tính tổng tiền của các sản phẩm
        FAILED
~~~

Từ tên nhóm, có thể suy ra test được chạy sau khi fixture nền của lớp ngoài và fixture của nhóm đã được chuẩn bị. Khi điều tra, kiểm tra theo thứ tự:

1. Lớp ngoài có tạo đúng trạng thái nền cho mọi nhóm không?
2. Callback **@BeforeEach** của nhóm có ghi đè hoặc làm sai trạng thái đó không?
3. Test method có tự tạo dữ liệu riêng cần thiết không?
4. Assertion có kiểm tra đúng hành vi của nhóm không?
5. Có trạng thái mutable, mock hoặc tài nguyên nào bị chia sẻ giữa các test không?

Nếu chỉ test trong một nested group thất bại, bắt đầu từ callback của nhóm đó. Nếu mọi nhóm cùng thất bại, xem lại fixture hoặc cấu hình ở lớp ngoài. Nếu lỗi chỉ xảy ra khi chạy toàn suite, kiểm tra tài nguyên dùng chung, lifecycle **PER_CLASS**, transaction và sự phụ thuộc thứ tự.

Khi chạy từ IDE, có thể chọn riêng test method, nested class hoặc toàn bộ test class. Chạy riêng một nested group là cách hữu ích để khoanh vùng, nhưng kết quả cuối cùng vẫn cần được xác nhận trong phạm vi suite mà dự án sử dụng.

## 12. Mẫu tổ chức có thể áp dụng

Với một thành phần có nhiều trạng thái, có thể bắt đầu bằng cấu trúc:

~~~java
class ComponentTest {

    private Component component;

    @BeforeEach
    void setUp() {
        component = new Component();
    }

    @Nested
    @DisplayName("Khi điều kiện A")
    class WhenConditionA {

        @BeforeEach
        void prepareConditionA() {
            // Thiết lập trạng thái A.
        }

        @Test
        void performsExpectedBehavior() {
            // Arrange bổ sung nếu cần.
            // Act.
            // Assert.
        }
    }

    @Nested
    @DisplayName("Khi điều kiện B")
    class WhenConditionB {

        @BeforeEach
        void prepareConditionB() {
            // Thiết lập trạng thái B.
        }

        @Test
        void performsAlternativeBehavior() {
            // Arrange bổ sung nếu cần.
            // Act.
            // Assert.
        }
    }
}
~~~

Khi thiết kế nhóm nested, hãy cân nhắc:

- Tên nhóm có mô tả một điều kiện hoặc trạng thái cụ thể không?
- Các test bên trong có thực sự chia sẻ ngữ cảnh đó không?
- Fixture nền ở lớp ngoài có trung tính và hữu ích cho các nhóm không?
- Fixture riêng có được đặt trong callback hoặc test method của đúng nhóm không?
- Lifecycle có vô tình chia sẻ trạng thái giữa các test không?
- Có thể hiểu cấu trúc chỉ bằng tên class, tên nhóm và tên method không?
- Cấp lồng có mang thêm thông tin, hay chỉ làm cấu trúc sâu hơn?
- Cấu hình Spring có được kế thừa hoặc override một cách có chủ đích không?

## Kết luận

**@Nested** giúp JUnit Jupiter diễn đạt các tình huống kiểm thử theo cấu trúc cha – con. Lớp ngoài giữ phần chuẩn bị nền, lớp lồng xác định trạng thái hoặc điều kiện, còn test method kiểm tra từng hành vi cụ thể. Khi nhóm theo ngữ cảnh có ý nghĩa, dùng lifecycle đúng cách và giữ mỗi test độc lập, cấu trúc nested làm test suite dễ đọc, dễ điều tra và dễ mở rộng hơn.
