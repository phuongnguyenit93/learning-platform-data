# Unit test cho logic không phụ thuộc Spring

> **Chương:** Test types  
> **Phạm vi:** Spring Modulith — verification & testing  
> **Trọng tâm:** Kiểm thử nhanh, độc lập cho quy tắc nghiệp vụ thuần Java nằm bên trong một application module.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện phần logic của một module có thể kiểm thử bằng cách khởi tạo đối tượng Java trực tiếp, không cần Spring ApplicationContext.
- Viết unit test bằng JUnit Jupiter (JUnit 5) cho kết quả, các trường hợp biên, ngoại lệ và bất biến nghiệp vụ.
- Dùng fake hoặc stub để cô lập một dependency thông qua interface khi đối tượng được kiểm thử cần cộng tác với thành phần khác.
- Phân biệt điều unit test chứng minh được với kiểm tra ranh giới module bằng `ApplicationModules.verify()` và kiểm thử tích hợp bằng `@ApplicationModuleTest`.
- Đặt unit test vào quality gate của CI để phát hiện hồi quy sớm.

Trong kiến trúc Spring Modulith, mỗi application module sở hữu một phần chức năng nghiệp vụ. Dù module được lắp ráp bằng Spring, các phép tính, quyết định và quy tắc miền nghiệp vụ bên trong module thường có thể là Java thuần. **Unit test nên bắt đầu từ phần logic này.** Việc bỏ qua Spring ở cấp test giúp vòng phản hồi ngắn, lỗi dễ khoanh vùng và bộ test ít phụ thuộc cấu hình môi trường.

## 2. Unit test thuần Java kiểm tra điều gì?

Một unit test cô lập **đơn vị hành vi nhỏ nhất có ý nghĩa**, chẳng hạn phương thức tính phí, chính sách chiết khấu, điều kiện đủ tư cách xử lý đơn, hoặc việc chuyển trạng thái của một aggregate.

| Thuộc tính | Unit test không phụ thuộc Spring |
| --- | --- |
| Đối tượng được kiểm thử (SUT) | Class, record, hàm hoặc domain service Java thuần |
| Khởi tạo | Dùng `new`, constructor, factory; không cần bean container |
| Đầu vào | Tham số, value object, fake/stub của interface |
| Quan sát | Giá trị trả về, ngoại lệ, trạng thái, lời gọi cộng tác khi cần |
| Không cần | `@SpringBootTest`, `@ApplicationModuleTest`, database, HTTP server, message broker |
| Thế mạnh | Nhanh, tất định, thông báo lỗi sát quy tắc nghiệp vụ |
| Giới hạn | Chưa xác nhận cấu hình bean, transaction, persistence, event delivery hoặc quy tắc phụ thuộc giữa các module |

Ví dụ trong module `order`: phép tính tổng tiền và giảm giá có thể được kiểm thử độc lập. Nhưng test đó **không tự phát hiện** module `order` có lỡ import một class `internal` của module `inventory` hay không. Đó là trách nhiệm của bài kiểm tra kiến trúc.

### Dấu hiệu nên tách logic ra khỏi Spring

- Một phương thức dùng nhiều nhánh `if`, `switch`, phép tính hoặc quy tắc miền nghiệp vụ nhưng lại nằm trực tiếp trong `@RestController` hoặc một class phụ thuộc quá nhiều bean.
- Logic có thể được mô tả bằng quan hệ **đầu vào → kết quả** mà không cần gọi database hoặc gửi sự kiện thật.
- Cùng một quy tắc cần chạy trong nhiều luồng xử lý, nhưng muốn kiểm thử nó mà không khởi tạo cả module.

Có thể tách quy tắc đó thành class thuần Java và để tầng ứng dụng Spring gọi class này. **Không cần gắn `@Component` hay `@Service` vào mọi class nghiệp vụ**; Spring chỉ cần biết cách tạo và nối các đối tượng thực sự cần quản lý.

## 3. Ví dụ xuyên suốt: tính tiền đơn hàng

Giả sử module `order` có quy tắc minh họa:

1. Mỗi dòng hàng có đơn giá không âm và số lượng nguyên dương.
2. Đơn hàng phải chứa ít nhất một dòng.
3. `STANDARD` không được giảm giá; `GOLD` được giảm 10% trên tổng tiền trước giảm.
4. Tổng phải trả bằng tổng trước giảm trừ mức giảm.

Đây là **quy tắc ví dụ**, không phải giả định về chính sách thật của bất kỳ hệ thống nào. Ta cài đặt nó bằng Java 17+ và `BigDecimal` để tránh sai số nhị phân của `double` khi làm việc với tiền.

**`src/main/java/com/example/order/domain/OrderLine.java`**

~~~java
package com.example.order.domain;

import java.math.BigDecimal;
import java.util.Objects;

public record OrderLine(BigDecimal unitPrice, int quantity) {

    public OrderLine {
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must be >= 0");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be > 0");
        }
    }

    public BigDecimal amount() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

Validation đặt ở constructor của `OrderLine` giúp ngăn một dòng hàng không hợp lệ ngay khi được tạo. Các test nghiệp vụ khác nhờ đó có thể giả định đối tượng đầu vào thỏa bất biến cơ bản.

**`src/main/java/com/example/order/domain/OrderPriceCalculator.java`**

~~~java
package com.example.order.domain;

import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public final class OrderPriceCalculator {

    private static final BigDecimal GOLD_RATE = new BigDecimal("0.10");

    public enum CustomerTier {
        STANDARD, GOLD
    }

    public record Quote(
            BigDecimal subtotal,
            BigDecimal discount,
            BigDecimal total
    ) {}

    public Quote calculate(List<OrderLine> lines, CustomerTier tier) {
        Objects.requireNonNull(lines, "lines");
        Objects.requireNonNull(tier, "tier");

        if (lines.isEmpty()) {
            throw new IllegalArgumentException(
                    "Order must contain at least one line");
        }

        BigDecimal subtotal = lines.stream()
                .map(line -> Objects.requireNonNull(line, "line").amount())
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal discount = tier == CustomerTier.GOLD
                ? subtotal.multiply(GOLD_RATE)
                : BigDecimal.ZERO;

        return new Quote(
                subtotal,
                discount,
                subtotal.subtract(discount));
    }
}
~~~

`OrderPriceCalculator` chỉ phụ thuộc JDK và các kiểu trong cùng module. Không có `@Autowired`, `ApplicationContext`, `Repository` hay kết nối hạ tầng. Do đó có thể tạo SUT bằng `new OrderPriceCalculator()` ngay trong bài test.

### Thiết kế ca kiểm thử trước khi viết mã test

| Kịch bản | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Cộng nhiều dòng | 2 × 10.000 và 1 × 5.000, `STANDARD` | Tạm tính 25.000, giảm 0, tổng 25.000 |
| Áp dụng hạng khách hàng | 1 × 10.000, `GOLD` | Giảm 1.000, tổng 9.000 |
| Hạng không giảm | 1 × 10.000, `STANDARD` | Giảm 0, tổng 10.000 |
| Đơn hàng rỗng | Danh sách rỗng | `IllegalArgumentException` |
| Số lượng không hợp lệ | 0 hoặc số âm | `IllegalArgumentException` khi tạo `OrderLine` |
| Đơn giá âm | `-1` | `IllegalArgumentException` khi tạo `OrderLine` |

## 4. Unit test với JUnit 5

**`src/test/java/com/example/order/domain/OrderPriceCalculatorTest.java`**

~~~java
package com.example.order.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

import com.example.order.domain.OrderPriceCalculator.CustomerTier;

class OrderPriceCalculatorTest {

    private final OrderPriceCalculator calculator =
            new OrderPriceCalculator();

    @Test
    void sums_all_order_lines() {
        var lines = List.of(
                new OrderLine(new BigDecimal("10000.00"), 2),
                new OrderLine(new BigDecimal("5000.00"), 1));

        var quote = calculator.calculate(lines, CustomerTier.STANDARD);

        assertMoney("25000", quote.subtotal());
        assertMoney("0", quote.discount());
        assertMoney("25000", quote.total());
    }

    @ParameterizedTest
    @CsvSource({
            "STANDARD, 0, 10000",
            "GOLD, 1000, 9000"
    })
    void applies_discount_by_customer_tier(
            CustomerTier tier,
            String expectedDiscount,
            String expectedTotal) {

        var quote = calculator.calculate(
                List.of(new OrderLine(new BigDecimal("10000"), 1)),
                tier);

        assertMoney("10000", quote.subtotal());
        assertMoney(expectedDiscount, quote.discount());
        assertMoney(expectedTotal, quote.total());
    }

    @Test
    void rejects_empty_order() {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.calculate(
                        List.of(), CustomerTier.STANDARD));
    }

    @ParameterizedTest
    @ValueSource(ints = {0, -2})
    void rejects_non_positive_quantity(int quantity) {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine(new BigDecimal("10"), quantity));
    }

    @Test
    void rejects_negative_unit_price() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine(new BigDecimal("-1"), 1));
    }

    @Test
    void rejects_missing_tier() {
        assertThrows(NullPointerException.class,
                () -> calculator.calculate(
                        List.of(new OrderLine(BigDecimal.TEN, 1)),
                        null));
    }

    private static void assertMoney(String expected, BigDecimal actual) {
        assertEquals(0, new BigDecimal(expected).compareTo(actual));
    }
}
~~~

Trong test này:

- **Arrange:** tạo `OrderLine`, `CustomerTier` và đối tượng `OrderPriceCalculator`.
- **Act:** gọi `calculate(...)` hoặc constructor có bất biến cần kiểm tra.
- **Assert:** đối chiếu tổng tiền, mức giảm, tổng phải trả hoặc kiểu ngoại lệ.

`@ParameterizedTest` giúp cùng một quy tắc được kiểm tra với nhiều bộ dữ liệu mà không lặp toàn bộ thân test. Hai phép so sánh `BigDecimal("10.0").equals(BigDecimal("10.00"))` và `compareTo(...) == 0` có ý nghĩa khác nhau: `equals` còn xét `scale`, còn `compareTo` so sánh giá trị số. Ví dụ sử dụng `compareTo` vì hợp đồng nghiệp vụ ở đây quy định **số tiền**, chưa quy định độ dài phần thập phân khi hiển thị.

Lưu ý: nếu ứng dụng có yêu cầu làm tròn theo đơn vị tiền tệ, hãy viết rõ chính sách `RoundingMode` và thêm test cho các mốc làm tròn. Không tự thêm làm tròn vào ví dụ này vì đầu bài chưa có yêu cầu đó.

### Dependency tối thiểu để chạy test

Một dự án Spring Boot có thể đã có `spring-boot-starter-test`, trong đó bao gồm các công cụ kiểm thử cần thiết theo phiên bản do Boot quản lý. Test thuần Java ở trên **không sử dụng** Spring Test Context dù bộ thư viện test có mặt trên classpath.

Nếu dự án dùng JUnit Jupiter độc lập, cần JUnit Jupiter API/engine và phần `junit-jupiter-params` cho `@ParameterizedTest`; cấu hình runner để thực thi bằng JUnit Platform (ví dụ `useJUnitPlatform()` với Gradle). Không cần `@SpringBootTest` chỉ để được chạy qua test runner.

## 5. Khi logic có dependency: dùng port và fake

Trong thực tế, tầng ứng dụng của module `order` có thể cần tra hạng khách hàng từ một nguồn bên ngoài. Nếu quy tắc tính tiền vẫn nằm trong `OrderPriceCalculator`, ta có thể đặt một **port** cho việc tra cứu và thay bằng fake/stub khi unit test.

**`src/main/java/com/example/order/application/CustomerTierLookup.java`**

~~~java
package com.example.order.application;

import com.example.order.domain.OrderPriceCalculator.CustomerTier;

@FunctionalInterface
public interface CustomerTierLookup {
    CustomerTier findTier(String customerId);
}
~~~

**`src/main/java/com/example/order/application/QuoteUseCase.java`**

~~~java
package com.example.order.application;

import java.util.List;
import java.util.Objects;

import com.example.order.domain.OrderLine;
import com.example.order.domain.OrderPriceCalculator;
import com.example.order.domain.OrderPriceCalculator.Quote;

public final class QuoteUseCase {

    private final CustomerTierLookup tierLookup;
    private final OrderPriceCalculator calculator;

    public QuoteUseCase(
            CustomerTierLookup tierLookup,
            OrderPriceCalculator calculator) {
        this.tierLookup = Objects.requireNonNull(tierLookup);
        this.calculator = Objects.requireNonNull(calculator);
    }

    public Quote quote(String customerId, List<OrderLine> lines) {
        var tier = tierLookup.findTier(customerId);
        return calculator.calculate(lines, tier);
    }
}
~~~

**`src/test/java/com/example/order/application/QuoteUseCaseTest.java`**

~~~java
package com.example.order.application;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

import com.example.order.domain.OrderLine;
import com.example.order.domain.OrderPriceCalculator;
import com.example.order.domain.OrderPriceCalculator.CustomerTier;

class QuoteUseCaseTest {

    @Test
    void quotes_gold_customer_without_database_or_spring() {
        CustomerTierLookup fakeLookup = customerId -> {
            assertEquals("customer-42", customerId);
            return CustomerTier.GOLD;
        };
        var useCase = new QuoteUseCase(
                fakeLookup,
                new OrderPriceCalculator());

        var quote = useCase.quote(
                "customer-42",
                List.of(new OrderLine(new BigDecimal("10000"), 1)));

        assertEquals(0,
                new BigDecimal("9000").compareTo(quote.total()));
    }
}
~~~

Ở đây, lambda là stub cho `CustomerTierLookup`: nó cung cấp kết quả cố định, đồng thời kiểm tra ID được chuyển tới port. Ta không cần database thật hoặc một Spring bean của adapter.

Có thể dùng Mockito với `mock(...)`, `when(...)` và `verify(...)` khi lời gọi hoặc tương tác là một phần quan trọng của hợp đồng. Tuy nhiên, đừng mock `OrderPriceCalculator` trong bài test `QuoteUseCase` nếu mục tiêu là chứng minh cả việc kết nối các quy tắc thuần Java. Cần xác định rõ **SUT** và chỉ thay những dependency làm test mất tính độc lập hoặc khó kiểm soát.

> **Ranh giới quan trọng:** Đặt interface và domain class đúng phạm vi công khai cho phép của từng application module. Dùng fake để unit test **không cho phép** module khác phụ thuộc vào package `internal` của module này. Quy tắc đó cần được xác minh riêng ở cấp kiến trúc.

## 6. Cách chọn test phù hợp trong Spring Modulith

| Câu hỏi cần trả lời | Kiểu kiểm thử phù hợp | Spring context? |
| --- | --- | --- |
| Với đơn giá, số lượng và hạng khách, tổng tiền có đúng không? | Unit test JUnit thuần Java | Không |
| Port nhận đúng ID khách và kết quả được dùng để tính giá? | Unit test với fake/mock | Không |
| Một module có phụ thuộc sai module khác, tạo vòng phụ thuộc hoặc truy cập package bị che giấu không? | Kiểm tra kiến trúc bằng `ApplicationModules.of(Application.class).verify()` | Không cần chạy toàn bộ ứng dụng theo kiểu integration test |
| Bean của module có được cấu hình, inject đúng và thực thi trong Spring không? | `@ApplicationModuleTest` | Có |
| Repository, transaction, sự kiện xuất bản/tiếp nhận có vận hành đúng với hạ tầng không? | Integration test/module test phù hợp, đôi khi cần database hoặc broker | Thường có |

`@ApplicationModuleTest` có mục đích khởi tạo ngữ cảnh ứng dụng cho module cần kiểm thử, theo các tùy chọn phạm vi của Spring Modulith. Nó rất hữu ích cho kiểm thử tích hợp, nhưng việc dùng nó cho mọi phép tính thuần Java khiến test chậm hơn và làm lỗi cấu hình môi trường che khuất lỗi quy tắc nghiệp vụ.

`ApplicationModules.verify()` kiểm tra mô hình module và quy tắc kiến trúc; nó không chứng minh công thức chiết khấu đúng. Ngược lại, toàn bộ các unit test ở phần 4 có thể xanh trong khi cấu trúc module vi phạm quy tắc phụ thuộc. **Quality gate nên có cả unit test và architecture verification**, sau đó thêm module/integration test cho đường đi thực qua Spring và hạ tầng.

### Các lỗi thường gặp

1. **Gắn `@SpringBootTest` lên mọi test:** biến một phép tính nhỏ thành việc kiểm tra khởi tạo context; thời gian chạy và nguyên nhân lỗi khó dự đoán hơn.
2. **Mock cả đối tượng chứa quy tắc đang cần kiểm chứng:** test chỉ xác nhận mock trả dữ liệu đã cấu hình, không bảo vệ quy tắc nghiệp vụ.
3. **Chỉ thử ca thành công:** bỏ sót input rỗng, giá trị biên, null và chính sách xử lý dữ liệu bất hợp lệ.
4. **Đồng nhất unit test với ranh giới module:** test thuần Java không tự cấm truy cập cross-module sai.
5. **Dùng ngày giờ, random, network hoặc database thật trong unit test:** kết quả dễ thay đổi; nên truyền `Clock`, nguồn số ngẫu nhiên hoặc port qua constructor khi thực sự cần.
6. **Dùng `BigDecimal.equals` không chủ đích:** test có thể thất bại do khác `scale` dù hai giá trị tiền bằng nhau; hoặc ngược lại bỏ qua yêu cầu định dạng nếu `scale` là một phần hợp đồng.

## 7. Đưa test vào CI và tổ chức bộ test

Theo cấu trúc Maven/Gradle thông dụng, đặt test dưới `src/test/java`, giữ package tương ứng với class cần kiểm thử và đặt tên dễ nhận biết như `OrderPriceCalculatorTest`. Bước `test` trong pipeline chạy unit test mỗi khi có commit hoặc pull request. Nếu dự án có thêm bài kiểm tra `ApplicationModules.verify()` và `@ApplicationModuleTest`, bảo đảm chúng cũng nằm trong các job kiểm tra phù hợp; chia nhóm theo tốc độ khi số lượng test tăng.

Một quality gate có thể vận hành theo thứ tự:

1. **Unit tests:** chạy nhanh và thường xuyên cho domain logic; không cần dịch vụ ngoài.
2. **Architecture verification:** chặn phụ thuộc module sai, vòng phụ thuộc và vi phạm phạm vi truy cập.
3. **Module/integration tests:** kiểm tra wiring, database, sự kiện và giao tiếp giữa các phần đã tích hợp.
4. **Chấp nhận thay đổi** khi các bước bắt buộc đều xanh; lỗi phải hiển thị rõ test và điều kiện thất bại.

Đừng diễn giải việc unit test xanh là bằng chứng hoàn tất kiểm thử hệ thống. Nó chỉ xác nhận các hành vi được mô tả bởi test trong phạm vi các dependency đã cô lập.

## 8. Bài thực hành

Mở rộng ví dụ mà không khởi tạo Spring:

- Thêm hạng khách `SILVER` được giảm 5%; viết test cho cả `STANDARD`, `SILVER` và `GOLD` trước khi sửa logic.
- Xác định hành vi của đơn giá bằng 0 và một dòng có `null`; bổ sung test theo hợp đồng bạn chọn.
- Thêm quy tắc mức giảm tối đa nếu bài toán yêu cầu, rồi kiểm thử trường hợp tổng tiền bằng, nhỏ hơn và lớn hơn ngưỡng.
- Tạo một implementation khác của `CustomerTierLookup` dùng dữ liệu trong bộ nhớ để kiểm thử `QuoteUseCase` với nhiều khách hàng; giải thích khi nào fake hữu ích hơn mock.

**Tiêu chí tự kiểm tra:** Mỗi test tự chuẩn bị dữ liệu, không phụ thuộc thứ tự chạy, không đọc môi trường ngoài, có tên mô tả hành vi và thất bại khi cố ý làm sai chính sách chiết khấu. Khi chạy riêng class test, bạn không cần khởi động Spring hay cấp database.

## Ghi nhớ

Trong Spring Modulith, unit test thuần Java là tầng bảo vệ đầu tiên cho **logic nghiệp vụ bên trong module**. Hãy giữ quy tắc dễ gọi và dễ kiểm tra bằng dữ liệu đầu vào trực tiếp; dùng port và fake khi cần cô lập collaborator. Sau đó bổ sung **kiểm tra kiến trúc** để giữ ranh giới module và **kiểm thử tích hợp** để xác nhận Spring, persistence, transaction và sự kiện hoạt động đúng khi ghép hệ thống.
