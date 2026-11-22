# Thay thế Liskov (LSP): Bảo toàn hợp đồng của kiểu cha

> Chủ đề: OOP → SOLID → Liskov Substitution Principle. Trọng tâm là **khả năng thay thế về hành vi**: một đối tượng thuộc kiểu con phải dùng được tại mọi vị trí mà chương trình mong đợi kiểu cha, đồng thời giữ nguyên những cam kết mà mã sử dụng kiểu cha đang dựa vào.

## 1. Nguyên lý nói gì?

Giả sử một hàm nhận đối tượng kiểu `T`. Nếu `S` là kiểu con của `T`, việc truyền một đối tượng `S` thay cho `T` phải giữ đúng các tính chất mà hàm đó được phép kỳ vọng từ hợp đồng của `T`. Viết ngắn gọn:

~~~java
void process(T value) { /* chỉ dựa vào hợp đồng công khai của T */ }

// Nếu S <: T, process(new S(...)) vẫn phải đáp ứng hợp đồng của T.
~~~

LSP không yêu cầu kiểu con tạo ra **cùng một kết quả cụ thể** với mọi kiểu con khác; kiểu con được phép có thuật toán hoặc chính sách riêng. Điều bắt buộc là mọi kết quả và cách ứng xử của nó nằm trong phạm vi đã cam kết bởi kiểu cha.

Đừng đánh đồng “`extends` / `implements` hợp lệ và biên dịch được” với “thay thế được”. Trình biên dịch Java kiểm tra nhiều quy tắc về kiểu và ghi đè phương thức, nhưng không tự chứng minh được hợp đồng nghiệp vụ (ví dụ: “chiết khấu không được vượt tổng tiền hàng”).

### Hợp đồng của kiểu cha gồm những gì?

| Thành phần | Điều kiểu cha cam kết | Kiểu con phải làm gì? |
|---|---|---|
| **Tiền điều kiện (precondition)** | Điều kiện người gọi phải đáp ứng trước khi gọi, ví dụ: tổng tiền ≥ 0 | **Không được siết chặt**: không tự dưng đòi thêm điều kiện đầu vào hợp lệ |
| **Hậu điều kiện (postcondition)** | Điều kiện đúng sau khi phương thức hoàn tất, ví dụ: chiết khấu thuộc [0, tổng tiền] | **Không được làm yếu**: có thể bảo đảm nhiều hơn, nhưng phải giữ mọi bảo đảm cũ |
| **Bất biến (invariant)** | Trạng thái luôn hợp lệ trong vòng đời đối tượng | Không tạo trạng thái phá vỡ các bất biến mà người dùng kiểu cha tin cậy |
| **Lỗi và ngoại lệ** | Cách báo lỗi cho những trường hợp thuộc hợp đồng | Không phát sinh ngoại lệ không được hợp đồng cho phép trên đầu vào hợp lệ; quy tắc Java về `checked exception` chỉ là một phần của vấn đề |
| **Tác dụng phụ/quan sát được** | Các quy ước về dữ liệu bị thay đổi, số lần thực hiện, thứ tự, tính ổn định nếu có ghi rõ | Không thay đổi tùy tiện những cam kết mà client có quyền dựa vào |

Một phương thức có thể khai báo **đầu vào không hợp lệ** và ném lỗi tương ứng. LSP không đòi kiểu con chấp nhận mọi dữ liệu trong thế giới; nó đòi kiểu con chấp nhận ít nhất tất cả dữ liệu **hợp lệ theo kiểu cha**.

## 2. Tình huống thực tế: tính chiết khấu tại checkout

Giả sử ứng dụng bán hàng có nhiều chính sách chiết khấu: giảm cố định và giảm cho đơn đạt ngưỡng. Checkout không muốn biết từng loại chính sách; nó chỉ biết hợp đồng của `DiscountPolicy`.

**Hợp đồng công khai**:

- Đầu vào `subtotal` phải khác `null` và ≥ 0. Với `null` hoặc số âm, báo `IllegalArgumentException`.
- Với mọi `subtotal` hợp lệ, `discountFor(subtotal)` phải trả về `BigDecimal` khác `null`, thỏa mãn `0 ≤ discount ≤ subtotal`.
- Không sửa đầu vào hay tạo tác dụng phụ bất ngờ; ở đây `BigDecimal` vốn bất biến.
- Chính sách được tự chọn giá trị giảm cụ thể; không bắt buộc luôn giảm hoặc luôn giảm cùng số tiền.

### 2.1. Thiết kế đáp ứng LSP (Java 17+)

Lưu ví dụ dưới đây thành `LspDemo.java`; có thể biên dịch và chạy bằng JDK mà không cần thư viện ngoài.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

interface DiscountPolicy {
    /**
     * @param subtotal khác null và >= 0
     * @return giá trị khác null, nằm trong [0, subtotal]
     * @throws IllegalArgumentException nếu subtotal null hoặc âm
     */
    BigDecimal discountFor(BigDecimal subtotal);
}

final class Discounts {
    private Discounts() {}

    static void requireValid(BigDecimal subtotal) {
        if (subtotal == null || subtotal.signum() < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }
    }
}

/** Giảm một số tiền cố định, nhưng không bao giờ vượt tiền hàng. */
final class FixedDiscount implements DiscountPolicy {
    private final BigDecimal amount;

    FixedDiscount(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be >= 0");
        }
        this.amount = amount;
    }

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        Discounts.requireValid(subtotal);
        return amount.min(subtotal);
    }
}

/** Đơn dưới ngưỡng được giảm 0, không phát sinh ngoại lệ. */
final class ThresholdDiscount implements DiscountPolicy {
    private static final BigDecimal THRESHOLD =
            new BigDecimal("100.00");
    private static final BigDecimal REWARD =
            new BigDecimal("10.00");

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        Discounts.requireValid(subtotal);
        if (subtotal.compareTo(THRESHOLD) < 0) {
            return BigDecimal.ZERO;
        }
        return REWARD.min(subtotal);
    }
}

final class CheckoutService {
    BigDecimal total(BigDecimal subtotal, DiscountPolicy policy) {
        Discounts.requireValid(subtotal);
        BigDecimal discount =
                Objects.requireNonNull(policy, "policy")
                       .discountFor(subtotal);
        // Client được phép tin vào hợp đồng của DiscountPolicy.
        return subtotal.subtract(discount);
    }
}

public class LspDemo {
    public static void main(String[] args) {
        CheckoutService checkout = new CheckoutService();
        BigDecimal subtotal = new BigDecimal("25.00");

        List<DiscountPolicy> policies = List.of(
                new FixedDiscount(new BigDecimal("10.00")),
                new ThresholdDiscount()
        );
        for (DiscountPolicy policy : policies) {
            System.out.println(checkout.total(subtotal, policy));
        }
        // 15.00: chính sách giảm cố định
        // 25.00: chưa đạt ngưỡng nên giảm 0
    }
}
~~~

~~~bash
javac LspDemo.java
java LspDemo
~~~

**Vì sao thay thế an toàn?** `CheckoutService.total` chỉ sử dụng `DiscountPolicy` và dựa trên việc chiết khấu không âm, không vượt tổng tiền. Cả hai implementation đều nhận được *mọi subtotal hợp lệ*, kể cả 0 hoặc đơn rất nhỏ. Vì vậy, có thể thêm chính sách mới mà không phải viết nhánh phân biệt kiểu trong `CheckoutService`.

Một cách nhìn theo luồng gọi:

~~~mermaid
flowchart TD
    C["CheckoutService.total(subtotal, policy)"]
    P["DiscountPolicy.discountFor(subtotal)"]
    F["FixedDiscount"]
    T["ThresholdDiscount"]
    R["Kiểm tra: 0 <= discount <= subtotal"]
    O["total = subtotal - discount"]
    C --> P
    P --> F
    P --> T
    F --> R
    T --> R
    R --> O
~~~

## 3. Hai cách vi phạm LSP thường gặp

### 3.1. Siết chặt tiền điều kiện của kiểu cha

~~~java
// Ví dụ SAI: chèn thêm class này vào cùng package với ví dụ trên.
final class BadVipDiscount implements DiscountPolicy {
    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        Discounts.requireValid(subtotal);
        if (subtotal.compareTo(new BigDecimal("100")) < 0) {
            throw new UnsupportedOperationException(
                    "VIP discount only for orders >= 100");
        }
        return new BigDecimal("10.00");
    }
}
~~~

Tổng tiền `25.00` là đầu vào **hợp lệ** theo `DiscountPolicy`. Tuy vậy, `BadVipDiscount` lại ném `UnsupportedOperationException`. Đối tượng này không thể thay thế một `DiscountPolicy` bất kỳ trong `CheckoutService`, dù code biên dịch bình thường.

**Sửa:** Với đơn dưới 100, trả chiết khấu `BigDecimal.ZERO` như `ThresholdDiscount`. Nếu nghiệp vụ yêu cầu từ chối xử lý một đơn hàng, hãy định nghĩa điều đó **ngay trong hợp đồng của kiểu cha** hoặc tách một abstraction chuyên biệt; không tự thêm điều kiện bí mật trong subclass.

### 3.2. Làm yếu hậu điều kiện

~~~java
// Ví dụ SAI: trả số tiền giảm cố định mà không chặn theo subtotal.
final class BadFixedDiscount implements DiscountPolicy {
    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        Discounts.requireValid(subtotal);
        return new BigDecimal("50.00");
    }
}
~~~

Với đơn `25.00`, chiết khấu trả về `50.00`, vi phạm ràng buộc `discount ≤ subtotal`. `CheckoutService.total` khi đó cho ra `-25.00`; lỗi nghiệp vụ xuất hiện ở client mặc dù nó dùng đúng API.

**Sửa:** Trả `new BigDecimal("50.00").min(subtotal)` như `FixedDiscount`. Khi tính toán tiền tệ, nên dùng `BigDecimal(String)` thay vì `new BigDecimal(double)` để tránh mang sai số nhị phân vào phép tính.

| Trường hợp | `subtotal = 25.00` | Hợp đồng | Kết luận |
|---|---:|---|---|
| `FixedDiscount(10)` | Giảm 10, tổng còn 15 | Đúng | Thay thế được |
| `ThresholdDiscount` | Giảm 0, tổng còn 25 | Đúng | Thay thế được |
| `BadVipDiscount` | Ném `UnsupportedOperationException` | Sai: thêm điều kiện | Vi phạm LSP |
| `BadFixedDiscount` | Giảm 50, tổng âm | Sai: phá hậu điều kiện | Vi phạm LSP |

Hai lỗi trên có tính chất khác nhau: **thêm lý do từ chối đầu vào hợp lệ** là siết tiền điều kiện; **trả kết quả ngoài miền hợp lệ** là làm yếu hậu điều kiện. Một implementation cũng có thể vi phạm nhiều phần hợp đồng cùng lúc.

## 4. Kiểm thử hợp đồng chung cho mọi implementation

Unit test riêng từng lớp dễ bỏ sót khả năng thay thế. Thay vào đó, hãy chạy **cùng một bộ test** cho mọi `DiscountPolicy` mới. Ví dụ dưới đây dùng JUnit Jupiter và JUnit 5 parameterized tests; tệp `DiscountPolicyContractTest.java` nên được đặt cùng package với các lớp ví dụ, trong source set kiểm thử.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.function.Supplier;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class DiscountPolicyContractTest {

    static Stream<Arguments> policies() {
        return Stream.of(
            Arguments.of("fixed",
                (Supplier<DiscountPolicy>) () ->
                    new FixedDiscount(new BigDecimal("10.00"))),
            Arguments.of("threshold",
                (Supplier<DiscountPolicy>) ThresholdDiscount::new)
        );
        // Thử bổ sung BadVipDiscount hoặc BadFixedDiscount vào đây:
        // bộ kiểm thử sẽ phát hiện hành vi phá hợp đồng.
    }

    @ParameterizedTest(name = "{0} respects valid inputs")
    @MethodSource("policies")
    void validSubtotalsReturnValidDiscount(
            String name, Supplier<DiscountPolicy> factory) {
        DiscountPolicy policy = factory.get();

        for (String input : new String[]{"0", "25.00", "100.00", "250.00"}) {
            BigDecimal subtotal = new BigDecimal(input);
            BigDecimal discount = assertDoesNotThrow(
                () -> policy.discountFor(subtotal),
                "A valid subtotal must not be rejected");

            assertNotNull(discount);
            assertTrue(discount.compareTo(BigDecimal.ZERO) >= 0);
            assertTrue(discount.compareTo(subtotal) <= 0);
        }
    }

    @ParameterizedTest(name = "{0} rejects invalid inputs as specified")
    @MethodSource("policies")
    void invalidSubtotalsFollowContract(
            String name, Supplier<DiscountPolicy> factory) {
        DiscountPolicy policy = factory.get();
        assertThrows(IllegalArgumentException.class,
            () -> policy.discountFor(null));
        assertThrows(IllegalArgumentException.class,
            () -> policy.discountFor(new BigDecimal("-1")));
    }
}
~~~

Lưu ý: để chạy đoạn test này cần các dependency JUnit Jupiter, JUnit Params và cấu hình test runner trong Maven/Gradle. Mục tiêu là **test hành vi quan sát được ở cấp interface**, không ép tất cả lớp có cùng công thức tính. Trong ví dụ, `BadVipDiscount` trượt ca `subtotal = 25`; `BadFixedDiscount` trượt ca `0` và `25`.

Kiểm thử trên vài giá trị là **bằng chứng có giới hạn**, không phải chứng minh toán học cho mọi đầu vào. Với phép tính tiền quan trọng, hãy bổ sung kiểm thử giá trị biên (0, đúng ngưỡng, ngay dưới/trên ngưỡng), dữ liệu rất lớn, số có nhiều chữ số thập phân và kiểm thử thuộc tính để tăng độ tin cậy.

## 5. Ví dụ OOP kinh điển: Rectangle và Square

Giả sử `Rectangle` công khai hai setter độc lập `setWidth(w)` và `setHeight(h)`, đồng thời cam kết gọi setter nào thì **chỉ kích thước tương ứng** thay đổi. Một `Square extends Rectangle` ghi đè `setWidth` để tự đổi cả chiều cao nhằm giữ hai cạnh bằng nhau. Điều này bảo toàn “hình vuông” nhưng phá hợp đồng “đổi chiều rộng không ảnh hưởng chiều cao” của `Rectangle`.

Ví dụ client hợp lệ với kiểu cha:

~~~java
void resize(Rectangle r) {
    r.setWidth(5);
    r.setHeight(4);
    // Theo hợp đồng setter độc lập: diện tích = 20.
    assert r.area() == 20;
}
~~~

Nếu `Square` âm thầm ép hai cạnh bằng nhau, client không còn nhận được hành vi đã được kiểu cha hứa. Đây là vấn đề của **hợp đồng setter đã thiết kế**, không phải tuyên bố rằng hình vuông không phải hình chữ nhật về toán học.

Thiết kế tốt hơn tùy yêu cầu có thể là hai kiểu bất biến triển khai chung `Shape.area()`, trong đó interface chung **không hứa setter độc lập**; hoặc dùng composition thay cho quan hệ kế thừa để tái sử dụng logic. Đừng ép quan hệ `is-a` trong miền toán học thành `extends` khi hợp đồng phần mềm không tương thích.

## 6. LSP liên quan gì đến những chữ còn lại trong SOLID?

- **SRP:** Một lớp có trách nhiệm rõ ràng sẽ dễ mô tả hợp đồng, nhưng SRP đúng chưa bảo đảm LSP đúng.
- **OCP:** Khi mọi implementation giữ hợp đồng, ta có thể thêm loại `DiscountPolicy` mới mà ít phải sửa `CheckoutService`; LSP là điều kiện quan trọng để mở rộng an toàn.
- **ISP:** Interface quá rộng khiến nhiều implementation buộc phải `throw new UnsupportedOperationException()` trên tác vụ hợp lệ; chia interface theo năng lực thường giúp mỗi hợp đồng trung thực hơn.
- **DIP:** Client phụ thuộc abstraction, nhưng abstraction chỉ hữu ích nếu các implementation tuân thủ cùng hợp đồng hành vi.

Không nhất thiết dùng inheritance mới có LSP: `implements` một interface cũng tạo nghĩa vụ thay thế. Ngược lại, một chương trình không có kế thừa không tự động “đạt SOLID”.

## 7. Cách áp dụng khi review hoặc refactor

Trước khi thêm lớp con hoặc implementation mới, trả lời lần lượt:

1. **Xác định client:** Nơi nào nhận kiểu cha? Client đang dựa vào những giả định nào về tham số, kết quả, lỗi và tác dụng phụ?
2. **Viết hợp đồng:** Diễn tả rõ dữ liệu đầu vào hợp lệ, ngoại lệ cho dữ liệu sai, giá trị đầu ra hợp lệ, bất biến và hành vi quan trọng. Dùng JavaDoc, API docs và test.
3. **Đối chiếu kiểu con:** Có điều kiện đầu vào nào vừa phát sinh? Có `null`, exception, giá trị âm, trạng thái bất hợp lệ, thay đổi dữ liệu, hoặc side effect mới trên đầu vào hợp lệ không?
4. **Chạy contract tests:** Áp dụng cùng bộ test ở cấp interface cho mọi implementation. Thêm ca biên và kiểm thử tích hợp theo rủi ro.
5. **Thiết kế lại khi hợp đồng không phù hợp:** Tách interface theo khả năng, chuyển “không hỗ trợ” thành một kết quả được hợp đồng quy định, hoặc dùng composition. Không che lỗi bằng `instanceof` để phân biệt subtype ngay trong client.

### Sai lầm dễ gặp

- Chỉ kiểm tra `@Override`, chữ ký phương thức hoặc giới hạn checked exception rồi kết luận “đúng LSP”.
- Viết phương thức trong subtype ném `UnsupportedOperationException` dù phương thức đó hợp lệ theo abstraction.
- Cho phép subtype trả `null` khi kiểu cha đã hứa kết quả khác `null`, hoặc trả giá trị ngoài miền hợp lệ.
- Dùng `instanceof BadVipDiscount` trong `CheckoutService` để cứu một contract đã bị phá: cách này chuyển hiểu biết về subtype vào client, tăng rẽ nhánh khi mở rộng.
- Hiểu nhầm rằng mọi kiểu con phải có cùng kết quả, hiệu năng hoặc chi tiết thuật toán: chỉ những thuộc tính đã hứa trong hợp đồng mới bắt buộc. Nếu latency, thứ tự xử lý, tính idempotent hoặc thread safety là cam kết công khai, chúng cũng phải được bảo toàn.

**Ghi nhớ:** Kế thừa đúng về cú pháp chưa đủ. Hãy hỏi: “Nếu caller chỉ biết kiểu cha, caller có còn an toàn khi nhận kiểu con này không?” Nếu câu trả lời là không, cần sửa implementation hoặc thiết kế lại hợp đồng và quan hệ giữa các kiểu.