# Strategy Pattern trong Java: thay thế thuật toán bằng composition

> **Chủ đề:** OOP → Mẫu thiết kế → Strategy và thay thế thuật toán.  
> **Mục tiêu:** Hiểu lý do dùng Strategy, nhận biết ba vai trò Context–Strategy–Concrete Strategy, tự triển khai trong Java, chuyển thuật toán ở thời điểm chạy, kiểm thử hợp đồng chung và biết khi nào không nên dùng thêm abstraction.

## 1. Strategy là gì?

**Strategy** là mẫu thiết kế hành vi (*behavioral design pattern*) trong bộ mẫu GoF. Ý tưởng là **đóng gói các thuật toán có thể thay thế cho nhau thành những đối tượng cùng một hợp đồng**, rồi cho đối tượng sử dụng thuật toán (Context) làm việc thông qua hợp đồng đó.

Khi cần đổi cách xử lý, Context nhận một implementation khác thay vì tự chứa tất cả các nhánh `if/else` hoặc `switch` chi tiết. Thuật toán được thay thế có thể là cách tính phí, chọn tuyến vận chuyển, sắp xếp, áp khuyến mãi, xác thực, nén dữ liệu hoặc tính điểm.

Ba vai trò cốt lõi:

| Vai trò | Trách nhiệm | Trong ví dụ sẽ dùng |
|---|---|---|
| **Strategy** | Định nghĩa hoạt động chung và hợp đồng đầu vào/đầu ra | `DiscountStrategy` |
| **Concrete Strategy** | Thực hiện một biến thể thuật toán | `NoDiscount`, `PercentageDiscount`, `FixedDiscount` |
| **Context** | Điều phối nghiệp vụ và sử dụng Strategy qua interface | `Checkout` |
| **Client / composition root** | Chọn Strategy thích hợp cho ngữ cảnh, truyền vào Context | `StrategyDemo.main` |

**Điểm cốt lõi:** Context không cần biết thuật toán cụ thể đã triển khai như thế nào. Context chỉ dựa vào hành vi đã được Strategy cam kết.

## 2. Vấn đề trước khi áp dụng Strategy

Một website bán hàng có thể hỗ trợ ba chính sách giảm giá: không giảm, giảm theo tỷ lệ, giảm số tiền cố định. Nếu nhúng thuật toán ngay trong Checkout:

~~~java
// Minh họa mã khó mở rộng — không phải chương trình hoàn chỉnh.
BigDecimal calculateDiscount(String type, BigDecimal subtotal) {
    if ("NONE".equals(type)) {
        return BigDecimal.ZERO;
    }
    if ("PERCENT".equals(type)) {
        return subtotal.multiply(new BigDecimal("0.10"));
    }
    if ("FIXED".equals(type)) {
        return new BigDecimal("30.00").min(subtotal);
    }
    throw new IllegalArgumentException("Unknown discount type");
}
~~~

Ví dụ trên cố ý rút gọn và **chưa xử lý làm tròn tiền**. Vấn đề thiết kế xuất hiện khi số thuật toán, thông số và quy tắc ngày càng nhiều:

- Mỗi chính sách mới buộc sửa phương thức đang phục vụ nghiệp vụ chính.
- Các biến thể trộn chung điều kiện lựa chọn với công thức tính; dễ sửa nhầm nhánh đang hoạt động.
- Khó kiểm thử từng thuật toán một cách độc lập khi mọi thứ ở cùng một phương thức lớn.
- Nếu nhiều màn hình hoặc use case cùng tính chiết khấu, các nhánh có thể bị lặp.

Không có nghĩa `if/else` luôn sai. Với **hai điều kiện ngắn, ổn định và không có nhu cầu thay đổi riêng**, một hàm đơn giản có thể rõ ràng hơn nhiều lớp. Strategy hữu ích khi **thuật toán thực sự là một trục biến thiên độc lập**.

## 3. Cấu trúc Strategy

~~~mermaid
classDiagram
    class DiscountStrategy {
        <<interface>>
        +discountFor(subtotal) BigDecimal
    }
    class NoDiscount {
        +discountFor(subtotal) BigDecimal
    }
    class PercentageDiscount {
        -rate : BigDecimal
        +discountFor(subtotal) BigDecimal
    }
    class FixedDiscount {
        -amount : BigDecimal
        +discountFor(subtotal) BigDecimal
    }
    class Checkout {
        -strategy : DiscountStrategy
        +Checkout(strategy)
        +quote(subtotal) PriceQuote
    }
    class StrategyDemo {
        +main(args) void
    }

    DiscountStrategy <|.. NoDiscount
    DiscountStrategy <|.. PercentageDiscount
    DiscountStrategy <|.. FixedDiscount
    Checkout --> DiscountStrategy : sử dụng
    StrategyDemo ..> Checkout : khởi tạo
    StrategyDemo ..> DiscountStrategy : lựa chọn
~~~

Mũi tên quan trọng là **`Checkout → DiscountStrategy`**: Context phụ thuộc vào abstraction. Các Concrete Strategy có thể được thêm vào mà không phải viết lại công thức điều phối của Context.

Strategy thường dùng **composition**: Context **có một** đối tượng Strategy. Đây là một cách ưu tiên composition trước việc tạo nhiều subclass của chính Context, chứ không phải cấm inheritance trong mọi tình huống.

## 4. Ví dụ Java 17 có thể chạy độc lập: chiến lược giảm giá

Ta định nghĩa hợp đồng rõ ràng trước khi viết implementation:

- `subtotal` là số tiền không âm, có độ chính xác **đến đơn vị xu** (tối đa hai chữ số thập phân có ý nghĩa; có thể thêm các số 0).
- `discountFor(subtotal)` trả giá trị không null, **không âm và không vượt subtotal**, với độ chính xác đến hai chữ số thập phân.
- Strategy **không sửa subtotal**, không tự thực hiện thanh toán và không tạo các tác dụng phụ ngoài tính toán. `BigDecimal` vốn bất biến.
- Context kiểm tra tổng tiền đầu vào và chặn kết quả vi phạm hợp đồng, giúp lỗi thuật toán được phát hiện gần nguồn hơn.

> Đây là mô hình tiền tệ để học Strategy với đơn vị có hai chữ số thập phân. Sản phẩm thực tế cần quy định tiền tệ, đơn vị nhỏ nhất, thuế, làm tròn và phạm vi áp dụng khuyến mãi theo nghiệp vụ; không phải mọi đồng tiền đều có hai chữ số thập phân.

Lưu toàn bộ ví dụ sau vào **`StrategyDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Map;
import java.util.Objects;

// Strategy: một thuật toán giảm giá, không thực hiện thanh toán.
@FunctionalInterface
interface DiscountStrategy {
    /**
     * Tiền điều kiện: subtotal không null, >= 0, chính xác tới 2 số lẻ.
     * Hậu điều kiện: 0 <= kết quả <= subtotal; tối đa 2 số lẻ.
     */
    BigDecimal discountFor(BigDecimal subtotal);
}

// Concrete Strategy A: không giảm.
final class NoDiscount implements DiscountStrategy {
    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return new BigDecimal("0.00");
    }
}

// Concrete Strategy B: giảm theo tỷ lệ.
// Ví dụ: rate = 0.10 tương ứng 10%.
final class PercentageDiscount implements DiscountStrategy {
    private final BigDecimal rate;

    PercentageDiscount(BigDecimal rate) {
        Objects.requireNonNull(rate, "rate");
        if (rate.compareTo(BigDecimal.ZERO) < 0
                || rate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException("rate must be in [0, 1]");
        }
        this.rate = rate;
    }

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return subtotal.multiply(rate)
                .setScale(2, RoundingMode.HALF_UP);
    }
}

// Concrete Strategy C: giảm số tiền cố định, không vượt subtotal.
final class FixedDiscount implements DiscountStrategy {
    private final BigDecimal amount;

    FixedDiscount(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be >= 0");
        }
        try {
            this.amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException("amount has fractions of cent", ex);
        }
    }

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return amount.min(subtotal);
    }
}

// Giá trước giảm, mức giảm và giá cuối cùng là một kết quả bất biến.
record PriceQuote(
        BigDecimal subtotal,
        BigDecimal discount,
        BigDecimal total
) {}

// Context: giữ quy trình báo giá, ủy quyền công thức cho Strategy.
final class Checkout {
    private final DiscountStrategy strategy;

    Checkout(DiscountStrategy strategy) {
        this.strategy = Objects.requireNonNull(strategy, "strategy");
    }

    PriceQuote quote(BigDecimal subtotal) {
        Objects.requireNonNull(subtotal, "subtotal");
        if (subtotal.signum() < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }

        final BigDecimal normalized;
        try {
            normalized = subtotal.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "subtotal has fractions of cent", ex);
        }

        BigDecimal rawDiscount = Objects.requireNonNull(
                strategy.discountFor(normalized),
                "Strategy must return a discount");

        final BigDecimal discount;
        try {
            discount = rawDiscount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalStateException(
                    "Strategy returned fractions of cent", ex);
        }

        if (discount.signum() < 0
                || discount.compareTo(normalized) > 0) {
            throw new IllegalStateException(
                    "Strategy must return discount in [0, subtotal]");
        }

        return new PriceQuote(
                normalized,
                discount,
                normalized.subtract(discount));
    }
}

public class StrategyDemo {
    public static void main(String[] args) {
        // Đây là nơi cấu hình/chọn chiến lược theo tên.
        Map<String, DiscountStrategy> strategies = Map.of(
                "NONE", new NoDiscount(),
                "TEN_PERCENT",
                    new PercentageDiscount(new BigDecimal("0.10")),
                "FIXED_30",
                    new FixedDiscount(new BigDecimal("30.00"))
        );

        BigDecimal subtotal = new BigDecimal("120.00");

        for (String key : List.of("NONE", "TEN_PERCENT", "FIXED_30")) {
            DiscountStrategy selected = strategies.get(key);
            Checkout checkout = new Checkout(selected);
            PriceQuote quote = checkout.quote(subtotal);

            System.out.println(
                    key + " -> discount=" + quote.discount()
                    + ", total=" + quote.total());
        }
    }
}
~~~

Chạy trên JDK 17 trở lên:

~~~bash
javac StrategyDemo.java
java StrategyDemo
~~~

Kết quả dự kiến:

~~~text
NONE -> discount=0.00, total=120.00
TEN_PERCENT -> discount=12.00, total=108.00
FIXED_30 -> discount=30.00, total=90.00
~~~

**Đọc từng thành phần của ví dụ:**

1. `DiscountStrategy` là một **hợp đồng thống nhất**, chỉ nói “tính mức giảm”; không áp đặt thuật toán.
2. `NoDiscount`, `PercentageDiscount` và `FixedDiscount` cài đặt các thuật toán độc lập.
3. `Checkout` nhận Strategy qua **constructor injection**. Nó kiểm tra quy tắc chung và gọi `strategy.discountFor(...)`. Không hề dùng `instanceof` hay biết tên class cụ thể.
4. `StrategyDemo.main` lấy chiến lược phù hợp từ `Map`, khởi tạo Context và chạy cùng một quy trình. Đây là **lựa chọn thuật toán ở thời điểm chạy**, trước khi tạo Context.
5. Nếu cần chính sách mới, ví dụ `LoyaltyDiscount`, ta viết thêm class thực thi `DiscountStrategy` rồi đăng ký ở nơi lựa chọn; phần lớn code `Checkout` không cần sửa.

Lưu ý: `Map` chỉ là **cơ chế chọn** Strategy. Bản thân Map/Registry không phải điều định nghĩa mẫu Strategy. Điều định nghĩa mẫu là việc **đưa một thuật toán có cùng contract vào Context**, thông qua một interface chung.

## 5. Strategy thay đổi vào lúc nào?

Trong tài liệu GoF, Strategy có thể được chọn khi dựng Context hoặc thay bằng một implementation khác tùy nhu cầu. Hai cách phổ biến:

| Cách | Minh họa | Phù hợp |
|---|---|---|
| **Chọn khi tạo Context (immutable)** | `new Checkout(new PercentageDiscount(rate))` | Mỗi request/phiên có chính sách riêng, dễ kiểm soát concurrency |
| **Đổi Strategy trong Context** | `context.setStrategy(other)` | Một đối tượng dài hạn cần đổi thuật toán chủ động, có cơ chế quản lý trạng thái rõ ràng |
| **Truyền Strategy cho mỗi phương thức** | `quote(subtotal, strategy)` | Cùng Context xử lý nhiều request độc lập, thuật toán là tham số của mỗi lần gọi |

Ví dụ đổi Strategy trực tiếp (không phải class `Checkout` ở phần trước):

~~~java
// Chỉ minh họa cơ chế thay đổi động trên một Context.
final class MutableQuoteService {
    private DiscountStrategy strategy;

    MutableQuoteService(DiscountStrategy initial) {
        setStrategy(initial);
    }

    void setStrategy(DiscountStrategy next) {
        strategy = Objects.requireNonNull(next);
    }

    BigDecimal calculateDiscount(BigDecimal validSubtotal) {
        return strategy.discountFor(validSubtotal);
    }
}
~~~

Khi cùng một `MutableQuoteService` được chia sẻ giữa nhiều HTTP request, `setStrategy` trên một request có thể ảnh hưởng request khác. Không nên dùng một singleton mutable cho chiến lược mang dữ liệu riêng của từng người dùng nếu chưa thiết kế đồng bộ/tránh race condition. Thực tế thường **chọn Strategy theo từng request rồi truyền rõ ràng**, hoặc dùng Context bất biến như `Checkout`.

Chú ý `MutableQuoteService` cố ý chưa kiểm tra quy tắc tiền tệ. Ví dụ đầy đủ đã giao việc kiểm tra hợp đồng cho `Checkout`; khi áp dụng thực tế, cần giữ đúng các kiểm tra đó.

## 6. Cách viết Strategy bằng lambda trong Java

Vì `DiscountStrategy` có **một phương thức trừu tượng** (`@FunctionalInterface`), Java cho phép dùng lambda thay cho một class cụ thể khi thuật toán đủ ngắn và không cần state phức tạp.

~~~java
DiscountStrategy weekendDiscount = subtotal ->
        subtotal.multiply(new BigDecimal("0.05"))
                .setScale(2, RoundingMode.HALF_UP);

Checkout checkout = new Checkout(weekendDiscount);
PriceQuote result = checkout.quote(new BigDecimal("200.00"));
// Giảm 10.00, tổng còn 190.00
~~~

Các dòng này dùng những type/import đã có trong `StrategyDemo.java`; có thể đặt bên trong `main` hoặc phương thức Java tương thích.

**Chọn class riêng** nếu Strategy có nhiều bước, tham số cấu hình, dependency (dịch vụ, repository), logging riêng hoặc cần kiểm thử phức tạp. **Chọn lambda** nếu hành vi ngắn, tự giải thích được tên biến và không làm mờ quy tắc nghiệp vụ. Việc dùng lambda không làm mất bản chất của Strategy: vẫn là một implementation của hợp đồng `DiscountStrategy`.

## 7. Strategy và nguyên lý OOP/SOLID

Strategy thể hiện rất rõ ba ý tưởng OOP:

- **Đóng gói:** Mỗi biến thể thuật toán tự quản lý chi tiết tính toán.
- **Đa hình:** Lời gọi `discountFor` được dispatch tới implementation được truyền vào.
- **Composition:** Context giữ tham chiếu tới một đối tượng Strategy, không bắt buộc kế thừa Context.

Liên hệ SOLID:

| Nguyên lý | Strategy hỗ trợ ra sao | Lưu ý |
|---|---|---|
| **SRP** | Tách trách nhiệm điều phối checkout và tính từng loại giảm giá | Đừng tách class vô ích cho các biểu thức quá nhỏ |
| **OCP** | Có thể thêm `LoyaltyDiscount` mà không sửa thuật toán chung của `Checkout` | Vẫn cần đăng ký/chọn biến thể ở composition root |
| **LSP** | Các Strategy phải thực sự thay thế được theo contract `0 ≤ discount ≤ subtotal` | Có interface **không đồng nghĩa** mọi implementation hợp lệ |
| **ISP** | Interface một thao tác, đủ cho nhu cầu của Context | Tránh interface lớn ép Strategy làm những việc không liên quan |
| **DIP** | `Checkout` phụ thuộc `DiscountStrategy` thay vì class cụ thể | Cần chú ý hướng phụ thuộc giữa các module nếu chia package/module |

DI và Strategy cũng khác nhau: **DI** là cách cung cấp dependency từ ngoài vào; **Strategy** mô tả một **họ thuật toán có thể thay thế**. Trong ví dụ có cả hai: ta dùng constructor DI để đưa một Strategy vào Context.

## 8. Kiểm thử Strategy một cách có hệ thống

Việc tách thuật toán giúp kiểm thử hai lớp vấn đề: (a) công thức của từng Strategy; (b) hợp đồng chung và cách Context gọi Strategy. Các đoạn dưới đây dùng JUnit Jupiter (JUnit 5), đặt ở test source set, cùng package với `StrategyDemo.java`; cần dependency `junit-jupiter` và test runner của dự án.

### 8.1. Kiểm thử đơn vị từng thuật toán và tình huống biên

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class DiscountStrategyTest {
    @Test
    void percentageDiscountRoundsToCents() {
        Checkout checkout = new Checkout(
                new PercentageDiscount(new BigDecimal("0.10")));

        PriceQuote quote = checkout.quote(new BigDecimal("12.34"));

        assertEquals(new BigDecimal("1.23"), quote.discount());
        assertEquals(new BigDecimal("11.11"), quote.total());
    }

    @Test
    void fixedDiscountNeverExceedsSubtotal() {
        Checkout checkout = new Checkout(
                new FixedDiscount(new BigDecimal("30.00")));

        PriceQuote quote = checkout.quote(new BigDecimal("12.00"));

        assertEquals(new BigDecimal("12.00"), quote.discount());
        assertEquals(new BigDecimal("0.00"), quote.total());
    }

    @Test
    void invalidAmountAndBadStrategyAreRejected() {
        Checkout checkout = new Checkout(new NoDiscount());

        assertThrows(IllegalArgumentException.class,
                () -> checkout.quote(new BigDecimal("-1.00")));
        assertThrows(IllegalArgumentException.class,
                () -> checkout.quote(new BigDecimal("1.001")));

        // Một Strategy phá hợp đồng trả mức giảm lớn hơn subtotal.
        DiscountStrategy broken = amount -> amount.add(BigDecimal.ONE);
        Checkout guarded = new Checkout(broken);

        assertThrows(IllegalStateException.class,
                () -> guarded.quote(new BigDecimal("10.00")));
    }
}
~~~

Trong test trên, `BigDecimal.equals` so sánh cả **scale**; `1.23` và `1.230` khác nhau theo `equals`. Ví dụ đã chuẩn hóa giá trị xuống hai chữ số thập phân để việc so sánh chính xác. Khi chỉ muốn kiểm tra giá trị số, có thể dùng `compareTo`.

### 8.2. Một contract test dùng lại cho mọi Strategy

Mỗi Strategy mới cần tuân thủ cùng hợp đồng: đầu vào hợp lệ, đầu ra khác null, không âm, không vượt giá gốc. Dùng `@ParameterizedTest` để tránh viết lại cùng test khi thêm biến thể:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class DiscountStrategyContractTest {
    static Stream<Arguments> strategies() {
        return Stream.of(
                Arguments.of("none", new NoDiscount()),
                Arguments.of("percent",
                        new PercentageDiscount(new BigDecimal("0.10"))),
                Arguments.of("fixed",
                        new FixedDiscount(new BigDecimal("30.00")))
        );
    }

    @ParameterizedTest(name = "{0} preserves discount bounds")
    @MethodSource("strategies")
    void allStrategiesSatisfyContract(
            String name, DiscountStrategy strategy) {
        for (String value : new String[]{"0.00", "0.01", "12.34", "120.00"}) {
            BigDecimal subtotal = new BigDecimal(value);
            BigDecimal discount = assertDoesNotThrow(
                    () -> strategy.discountFor(subtotal));
            assertNotNull(discount);
            assertTrue(discount.compareTo(BigDecimal.ZERO) >= 0);
            assertTrue(discount.compareTo(subtotal) <= 0);
            assertEquals(0, discount.setScale(2,
                    java.math.RoundingMode.UNNECESSARY)
                    .compareTo(discount));
        }
    }
}
~~~

Đoạn cuối kiểm tra rằng mức giảm biểu diễn được chính xác đến hai chữ số thập phân; nếu một Strategy trả giá trị ba chữ số thập phân có ý nghĩa, `setScale(2, UNNECESSARY)` sẽ ném `ArithmeticException` và test thất bại. Đoạn test cần dependency bổ sung `junit-jupiter-params`. Đây là bộ **kiểm thử mẫu**, chưa bao phủ mọi giá trị; nên bổ sung kiểm thử thuộc tính, dữ liệu cực trị và các boundary đặc thù (đúng ngưỡng, ngay dưới/trên ngưỡng, đơn hàng lớn).

Ở dự án thật, phép tính giá cần được kiểm thử cùng các quy tắc **làm tròn, giới hạn khuyến mãi, thuế và tiền tệ**. Hợp đồng Strategy là chính nơi các quy tắc chung nên được diễn đạt rõ.

## 9. So sánh Strategy với những mẫu/hình thức dễ nhầm

| Cách tiếp cận | Ý tưởng chủ đạo | Khác Strategy ở đâu? |
|---|---|---|
| **Strategy** | Chọn một thuật toán từ nhiều implementation cùng contract | Context ủy quyền hành vi cho đối tượng Strategy |
| **State** | Hành vi phụ thuộc trạng thái nội tại của Context; chuyển trạng thái là một phần mô hình | Các đối tượng State thường quản lý/chỉ đạo **chuyển trạng thái**, còn Strategy thường do client hoặc cấu hình chọn |
| **Template Method** | Class cha cố định khung thuật toán; subclass override từng bước | Dùng **kế thừa**; Strategy chủ yếu dùng **composition/delegation** |
| **Command** | Đóng gói một yêu cầu/hành động thành object | Thường hướng đến thực thi, queue, log, undo; Strategy hướng đến biến thể thuật toán |
| **Factory Method / Factory** | Tạo đối tượng | Factory có thể **tạo hoặc chọn** Strategy, nhưng bản thân Strategy tập trung vào hành vi của object được chọn |
| **Một `switch` đơn giản** | Chọn thuật toán bằng điều kiện trực tiếp | Ít class hơn; phù hợp khi ít nhánh, logic ngắn và hiếm thay đổi |

Một điểm cần thận trọng: Strategy và State có thể có **sơ đồ UML tương tự** (Context giữ interface, nhiều implementation). Phân biệt bằng **ý nghĩa mô hình**: chọn cách giải cùng một việc hay thể hiện một trạng thái cùng các chuyển tiếp của đối tượng.

### Khi Strategy chưa chắc là đáp án tốt

Không nên tự động tạo interface và năm class chỉ để thay một phép cộng ngắn. Cân nhắc:
- Số biến thể có thật hay chỉ là giả định tương lai?
- Logic của mỗi biến thể có đủ phức tạp hoặc thay đổi riêng để hưởng lợi từ tách class?
- Contract có ổn định và dễ diễn đạt không?
- Code dùng một lần hay được nhiều Context chia sẻ?
- Thay đổi biến thể có cần runtime hay chỉ được cố định tại lúc build?
- Chi phí tạo class, đăng ký, cấu hình và test có tương xứng không?

Một hàm thuần hoặc `switch` vẫn có thể là thiết kế tốt. Có thể refactor sang Strategy khi sự biến thiên đã rõ.

## 10. Nâng cao: chọn Strategy từ dữ liệu người dùng một cách an toàn

Trong ví dụ main, `Map` lưu sẵn các instance được tin cậy. Khi loại chiến lược đến từ HTTP request, file cấu hình hoặc database, **không được** nạp class tùy ý bằng tên từ input rồi phản chiếu tạo instance. Hãy ánh xạ khóa hợp lệ tới những Strategy đã đăng ký/cấu hình.

Ví dụ mở rộng của `StrategyDemo.java`:

~~~java
// strategies là Map<String, DiscountStrategy> trong main.
String requested = "TEN_PERCENT"; // Ví dụ giá trị đã đọc từ request.
DiscountStrategy strategy = strategies.get(requested);

if (strategy == null) {
    throw new IllegalArgumentException(
            "Unsupported discount policy: " + requested);
}

PriceQuote quote = new Checkout(strategy)
        .quote(new BigDecimal("200.00"));
System.out.println(quote.total()); // 180.00
~~~

Với chính sách cần gọi database hoặc API bên ngoài, có thể viết Strategy là một class riêng và đưa dependency vào constructor. Khi nhiều Strategy dùng chung, chúng nên được thiết kế thread-safe hoặc tạo theo đúng scope sử dụng. Không lưu đơn hàng của user A trong field của một Strategy singleton nếu request user B cũng có thể dùng nó.

Nếu chính sách được chọn từ cơ sở dữ liệu, nên lưu **mã nghiệp vụ và tham số** (ví dụ `DISCOUNT_RATE` và giá trị `0.10`) theo mô hình có kiểm soát; việc ánh xạ mã sang implementation thuộc tầng cấu hình/chọn Strategy. Luồng thực hiện một đơn hàng có thể cần ghi nhận **phiên bản chính sách** để tái hiện kết quả khi kiểm toán.

## 11. Bài tập thực hành: chiến lược tính phí giao hàng

Bạn đang viết `ShippingService`. Cùng một đơn hàng có ba cách tính phí:

| Chiến lược | Luật ví dụ | Đầu ra với trọng lượng 3 kg |
|---|---|---:|
| `StandardShipping` | 15.000 VND + 5.000 VND/kg | 30.000 VND |
| `ExpressShipping` | 30.000 VND + 10.000 VND/kg | 60.000 VND |
| `FreeShipping` | 0 VND | 0 VND |

Giả định khối lượng kg nguyên dương cho đơn giản. Hãy:
1. Định nghĩa `ShippingStrategy` có `long feeFor(int weightKg)`.
2. Cài đặt ba Concrete Strategy theo bảng. Trong production, phải quy định cách xử lý khối lượng thập phân, giới hạn, vùng địa lý và overflow khi nhân/cộng.
3. Viết `ShippingService` nhận `ShippingStrategy` qua constructor, xác thực `weightKg > 0`, trả phí không âm.
4. Chọn Strategy theo lựa chọn của người mua từ một `Map` hoặc `enum` tại composition root; không dùng chuỗi `if/else` bên trong `ShippingService`.
5. Viết JUnit test cho cả ba phương thức và một contract test chung; thử bổ sung `SameDayShipping` mà không sửa core của `ShippingService`.

### Câu hỏi tự kiểm tra

1. `Checkout` có cần biết class `PercentageDiscount` không? Nếu có, đang phụ thuộc sai chỗ nào?
2. Strategy quyết định **thuật toán tính tiền** hay chịu trách nhiệm **khởi tạo đối tượng**? Factory có thể tham gia vào đâu?
3. Đổi Strategy cho một singleton bằng setter trong hệ thống nhiều request có thể gây lỗi gì?
4. Vì sao Strategy mới phải giữ hợp đồng `0 ≤ discount ≤ subtotal` dù interface Java chỉ có chữ ký trả `BigDecimal`?
5. Khi chỉ có hai biểu thức đơn giản, không có nhu cầu thay đổi, vì sao `switch` có thể là lựa chọn tốt?

**Kết luận thực hành:** **Strategy = một hợp đồng hành vi + nhiều implementation thuật toán + Context dùng composition để ủy quyền.** Chọn Strategy ở ranh giới cấu hình hoặc theo request; giữ Context tập trung vào nghiệp vụ chung và bảo vệ hợp đồng đầu vào/đầu ra. Pattern có giá trị khi các thuật toán thực sự cần biến thiên độc lập, không phải khi chỉ muốn loại bỏ mọi câu lệnh `if`.