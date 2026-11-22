# Kiểm thử chính sách và dịch vụ miền bằng các trường hợp biên

Trong Domain-Driven Design (DDD), chính sách (Policy) và dịch vụ miền (Domain Service) thường diễn đạt những quyết định nghiệp vụ không thuộc tự nhiên về một Entity hoặc Value Object riêng lẻ. Chúng có thể tính giá, xác định điều kiện đủ tư cách, lựa chọn phương án áp dụng hoặc phối hợp dữ liệu thuộc nhiều khái niệm miền. Vì những quyết định này ảnh hưởng trực tiếp đến kết quả nghiệp vụ, kiểm thử cần chứng minh chúng hoạt động đúng ở cả trường hợp thông thường lẫn ranh giới khó.

Một bài test tốt không chỉ xác nhận rằng phương thức trả về một con số. Nó làm rõ điều kiện nào được chấp nhận, điều kiện nào bị từ chối, cách xử lý khi giá trị nằm đúng tại ngưỡng, và kết quả khi nhiều quy tắc cùng áp dụng. Với chính sách chiết khấu, các trường hợp đáng chú ý có thể là tổng tiền thấp hơn ngưỡng một đơn vị nhỏ, bằng đúng ngưỡng, cao hơn ngưỡng, khách hàng không đủ hạng, hai ưu đãi xung đột, mức giảm vượt trần hoặc hai khoản tiền khác tiền tệ.

Bài học này trình bày cách kiểm thử Policy và Domain Service theo ngôn ngữ nghiệp vụ; cách tìm trường hợp biên bằng bảng quyết định và phân tích giá trị biên; cách kiểm thử Value Object, Aggregate và Domain Event; cùng cách chọn unit test, integration test và contract test phù hợp.

## 1. Kiểm thử miền phải trả lời câu hỏi nghiệp vụ

Kiểm thử miền (domain test) xác nhận mô hình có thực hiện đúng quy tắc và hành vi mà chuyên gia nghiệp vụ mong đợi hay không. Test nên mô tả được:

- Ai hoặc đối tượng nào đang thực hiện hành động?
- Điều kiện ban đầu là gì?
- Quy tắc nào quyết định kết quả?
- Kết quả nghiệp vụ được chấp nhận hoặc từ chối ra sao?
- Trạng thái nào và sự kiện nào được tạo ra?

Ví dụ, câu hỏi “khách hạng Gold có được giảm 10% không?” chưa đủ rõ. Cần làm rõ thêm:

- Tổng tiền được tính trước hay sau thuế và phí vận chuyển?
- Ngưỡng tối thiểu có được tính là đủ điều kiện không?
- Mức giảm có giới hạn tối đa không?
- Có được cộng dồn với coupon khác không?
- Hạng khách hàng được xác định ở thời điểm tạo giỏ hay lúc đặt đơn?
- Nếu đơn bị hủy, ưu đãi có được khôi phục không?

Các câu trả lời xác định chính sách và các trường hợp test. Nếu quy tắc còn mơ hồ, hãy hỏi chuyên gia nghiệp vụ trước khi khẳng định một kết quả mong đợi. Test không nên biến giả định của lập trình viên thành quy tắc chính thức.

### 1.1. Test hành vi, không kiểm tra cấu trúc nội bộ

Giả sử Policy trả về khoản giảm giá. Test nên xác nhận số tiền giảm và lý do đủ điều kiện. Nó không cần xác nhận Policy gọi một private helper bao nhiêu lần, sử dụng vòng lặp nào hoặc tạo bao nhiêu object tạm.

| Nên kiểm tra | Tránh kiểm tra nếu không phải hợp đồng |
|---|---|
| Đơn đạt ngưỡng thì được giảm theo chính sách | Tên private method tính phần trăm |
| Không được cộng hai ưu đãi loại trừ nhau | Số lần gọi một helper nội bộ |
| Tổng tiền không âm | Thứ tự các phép gán biến cục bộ |
| Đơn đã giao không thể hủy theo quy tắc hiện hành | Số lần gọi getter của Entity |
| Event nghiệp vụ đúng được ghi nhận sau hành động hợp lệ | Cách lưu event trong collection nội bộ |

Kiểm thử theo hành vi giúp mô hình có thể được refactor mà không phải viết lại toàn bộ test mỗi khi đổi cấu trúc.

### 1.2. Tách test miền khỏi test hạ tầng

Policy thuần hoặc Domain Service thuần thường có thể kiểm thử bằng unit test nhanh, không cần khởi động Spring, ORM, database hoặc message broker. Repository, mapping và transaction cần integration test riêng. Tích hợp với nhà cung cấp cần contract test hoặc adapter test.

Không cần đưa mọi test vào cùng một loại. Chọn phạm vi nhỏ nhất đủ để kiểm chứng hợp đồng đang xét.

## 2. Phân biệt Policy, Domain Service và Application Service

Trước khi viết test, cần xác định đúng trách nhiệm của đối tượng.

| Thành phần | Trách nhiệm | Câu hỏi kiểm thử |
|---|---|---|
| Policy | Biểu diễn một quy tắc hoặc chiến lược quyết định | Với điều kiện đầu vào này, chính sách chọn kết quả nào? |
| Domain Service | Thực hiện phép tính hoặc hành vi miền không thuộc tự nhiên một Entity/Value Object cụ thể | Kết quả miền có đúng với dữ liệu và quy tắc được cung cấp không? |
| Aggregate Root | Bảo vệ invariant và kiểm soát thay đổi trạng thái của Aggregate | Hành động hợp lệ được chấp nhận, hành động sai bị từ chối thế nào? |
| Value Object | Bảo vệ ý nghĩa, equality và quy tắc của một giá trị | Giá trị biên hoặc không hợp lệ được xử lý ra sao? |
| Application Service | Điều phối use case, transaction, repository và cổng tích hợp | Các bước của use case được phối hợp đúng không? |

Policy có thể là interface với nhiều implementation, hoặc chỉ là một class cụ thể nếu chưa có nhu cầu thay thế. Domain Service không phải nơi gom mọi logic còn sót lại. Nếu hành vi tự nhiên thuộc Order, Money hoặc một Aggregate Root, hãy đặt nó ở đó.

Application Service thường không nên chứa toàn bộ điều kiện chiết khấu, tính thuế hoặc invariant của đơn. Nó có thể tải dữ liệu cần thiết, gọi Policy hoặc Domain Service, yêu cầu Aggregate thực hiện hành vi và lưu kết quả.

## 3. Bắt đầu bằng bảng quyết định

Bảng quyết định (decision table) liệt kê các điều kiện ảnh hưởng đến một quyết định và kết quả tương ứng. Nó giúp tìm trường hợp bị bỏ sót khi có nhiều điều kiện kết hợp.

Giả sử chính sách minh họa:

- Chỉ khách hạng Gold được hưởng ưu đãi.
- Subtotal phải lớn hơn hoặc bằng 1.000.000 VND.
- Mức giảm là 10%.
- Khoản giảm tối đa là 300.000 VND.
- Coupon loại trừ nhau không được cộng dồn với ưu đãi Loyalty.

| Khách Gold? | Subtotal đạt ngưỡng? | Có coupon xung đột? | Kết quả |
|---|---|---|---|
| Không | Không | Không | Không giảm Loyalty |
| Không | Có | Không | Không giảm Loyalty |
| Có | Không | Không | Không giảm Loyalty |
| Có | Có | Có | Áp dụng quy tắc ưu tiên đã được xác nhận; không tự cộng dồn |
| Có | Có | Không | Giảm 10%, không vượt 300.000 VND |

Bảng này còn một điểm cần xác nhận: khi coupon xung đột, ưu đãi nào được ưu tiên? Có thể ưu tiên coupon, ưu đãi Loyalty hoặc chọn mức có lợi nhất cho khách. Không nên tự chọn một cách rồi coi đó là sự thật nghiệp vụ.

### 3.1. Từ bảng quyết định thành bộ test

Mỗi hàng đại diện cho một nhóm điều kiện cần có ít nhất một test. Nếu nhiều hàng có cùng kết quả, vẫn cần xác nhận rằng những điều kiện dẫn đến kết quả đó không bị bỏ qua.

Một bộ test cơ bản có thể gồm:

1. Khách không phải Gold, subtotal cao hơn ngưỡng.
2. Khách Gold, subtotal thấp hơn ngưỡng.
3. Khách Gold, subtotal bằng ngưỡng.
4. Khách Gold, subtotal cao hơn ngưỡng.
5. Khoản giảm tính ra nhỏ hơn mức trần.
6. Khoản giảm tính ra đúng mức trần.
7. Khoản giảm tính ra lớn hơn mức trần.
8. Có coupon loại trừ nhau.
9. Hai đầu vào khác tiền tệ.
10. Dữ liệu đầu vào không hợp lệ.

### 3.2. Đừng kiểm thử mọi tổ hợp một cách máy móc

Nếu có 10 điều kiện boolean, toàn bộ tổ hợp có thể lên tới 1.024 trường hợp. Không phải mọi tổ hợp đều hợp lệ hoặc có ý nghĩa. Hãy dùng bảng quyết định, phân tích rủi ro và hiểu biết nghiệp vụ để chọn trường hợp đại diện, trường hợp biên và các tương tác quan trọng.

Khi rủi ro cao hoặc nhiều điều kiện tương tác phức tạp, có thể dùng pairwise testing, combinatorial testing hoặc property-based testing để mở rộng độ bao phủ.

## 4. Phân tích giá trị biên

Lỗi thường xuất hiện tại ranh giới: bằng ngưỡng hay chưa, ngày kết thúc có được tính không, số lượng tối đa có bao gồm giá trị cuối, hoặc số tiền được làm tròn trước hay sau khi áp dụng tỷ lệ.

Với một ngưỡng T, hãy xem xét tối thiểu:

- T - ε: ngay dưới ngưỡng.
- T: đúng bằng ngưỡng.
- T + ε: ngay trên ngưỡng.

ε là đơn vị nhỏ nhất có ý nghĩa theo miền. Với số tiền có scale hai chữ số, ε có thể là 0,01 đơn vị tiền. Với số lượng nguyên, ε thường là 1. Với thời gian, ε phụ thuộc độ chính xác mà nghiệp vụ và hệ thống sử dụng.

| Quy tắc | Dưới biên | Đúng biên | Trên biên |
|---|---|---|---|
| Subtotal tối thiểu 1.000.000 VND | 999.999,99: không đạt | 1.000.000,00: đạt nếu dùng điều kiện >= | 1.000.000,01: đạt |
| Số lượng tối đa 10 | 9: hợp lệ | 10: hợp lệ | 11: từ chối |
| Điểm tối thiểu 500 | 499: không đạt | 500: đạt nếu ngưỡng bao gồm | 501: đạt |
| Thời điểm hết hạn | Trước hạn: còn hiệu lực | Đúng thời điểm hết hạn: theo quy tắc biên đã định | Sau hạn: hết hiệu lực |

### 4.1. Phân biệt >= với >

Một lỗi phổ biến là code dùng dấu lớn hơn trong khi chính sách yêu cầu “từ ... trở lên”. Test đúng tại ngưỡng sẽ phát hiện khác biệt này.

Ví dụ:

~~~java
@Test
void goldCustomerQualifiesAtExactMinimumSpend() {
    Money subtotal = money("1000000.00", "VND");

    DiscountDecision decision = policy.evaluate(CustomerTier.GOLD, subtotal);

    assertEquals(money("100000.00", "VND"), decision.discount());
}
~~~

Test này diễn đạt rõ quy tắc ngưỡng bao gồm. Nếu nghiệp vụ định nghĩa “lớn hơn 1.000.000”, expected result phải khác.

### 4.2. Kiểm thử biên kép

Một số quy tắc có cả giới hạn dưới và giới hạn trên. Ví dụ mức giảm phải từ 0 đến 300.000 VND. Cần kiểm tra:

- Giá trị âm nhỏ nhất có thể nhận.
- 0.
- Giá trị dương nhỏ.
- Mức trần trừ một đơn vị nhỏ.
- Đúng mức trần.
- Mức trần cộng một đơn vị nhỏ.

Nếu đầu vào có thể vượt giới hạn do dữ liệu ngoài hoặc lỗi tích hợp, test cần xác định hệ thống từ chối, giới hạn (clamp) hay chuyển sang lỗi miền. Không tự chọn cách xử lý nếu nghiệp vụ chưa quy định.

## 5. Kiểm thử Value Object trước khi kiểm thử Policy

Policy và Domain Service thường dựa trên Value Object. Nếu Money, Quantity, DateRange hoặc Percentage có hành vi sai, test Policy có thể thất bại vì nguyên nhân ở lớp giá trị.

Ví dụ các điều cần kiểm thử cho Money:

- Không chấp nhận amount hoặc currency null.
- Phép cộng/trừ yêu cầu cùng tiền tệ.
- Equality phản ánh quy tắc số học mà miền mong muốn.
- Quy tắc scale và rounding được áp dụng đúng.
- Giá trị âm được phép hay bị từ chối tùy khái niệm.
- Không có phép so sánh giữa hai loại tiền mà không có quy tắc chuyển đổi.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

record Money(BigDecimal amount, Currency currency) {
    Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
        amount = amount.stripTrailingZeros();
    }

    static Money zero(Currency currency) {
        return new Money(BigDecimal.ZERO, currency);
    }

    Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    Money multiply(BigDecimal factor) {
        int scale = Math.max(currency.getDefaultFractionDigits(), 0);
        BigDecimal result = amount.multiply(factor)
            .setScale(scale, RoundingMode.HALF_UP);
        return new Money(result, currency);
    }

    int compareTo(Money other) {
        requireSameCurrency(other);
        return amount.compareTo(other.amount);
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch");
        }
    }
}
~~~

Test:

~~~java
@Test
void moneyCannotBeComparedAcrossCurrencies() {
    Money vnd = money("100000", "VND");
    Money usd = money("10", "USD");

    assertThrows(IllegalArgumentException.class, () -> vnd.compareTo(usd));
}

@Test
void moneyEqualityUsesNormalizedNumericValue() {
    Money first = money("10.0", "VND");
    Money second = money("10.00", "VND");

    assertEquals(first, second);
    assertEquals(first.hashCode(), second.hashCode());
}
~~~

Ví dụ giả định Money chuẩn hóa scale khi tạo. Một hệ thống có thể chọn quy tắc khác, nhưng equality và hash code phải nhất quán với định nghĩa miền. Với tiền tệ, đừng mặc định số chữ số thập phân luôn giống nhau cho mọi currency; cần xác định độ chính xác và quy tắc làm tròn theo nghiệp vụ.

## 6. Kiểm thử Policy bằng các trường hợp biên

Policy nên có đầu vào và kết quả đủ rõ để test trực tiếp. Ví dụ, LoyaltyDiscountPolicy nhận hạng khách hàng và subtotal, rồi trả về quyết định chiết khấu.

~~~java
import java.math.BigDecimal;

record DiscountDecision(Money discount, String reason) {}

enum CustomerTier {
    REGULAR,
    SILVER,
    GOLD
}

final class LoyaltyDiscountPolicy {
    private final Money minimumSpend;
    private final Money maximumDiscount;
    private final BigDecimal rate;

    LoyaltyDiscountPolicy(
            Money minimumSpend,
            Money maximumDiscount,
            BigDecimal rate) {
        this.minimumSpend = minimumSpend;
        this.maximumDiscount = maximumDiscount;
        this.rate = rate;
    }

    DiscountDecision evaluate(CustomerTier tier, Money subtotal) {
        if (tier != CustomerTier.GOLD) {
            return new DiscountDecision(
                Money.zero(subtotal.currency()), "CUSTOMER_NOT_ELIGIBLE"
            );
        }
        if (subtotal.compareTo(minimumSpend) < 0) {
            return new DiscountDecision(
                Money.zero(subtotal.currency()), "MINIMUM_SPEND_NOT_MET"
            );
        }

        Money calculated = subtotal.multiply(rate);
        Money discount = calculated.compareTo(maximumDiscount) > 0
            ? maximumDiscount
            : calculated;

        if (discount.compareTo(subtotal) > 0) {
            discount = subtotal;
        }
        return new DiscountDecision(discount, "LOYALTY_DISCOUNT_APPLIED");
    }
}
~~~

Đây là ví dụ rút gọn; implementation Money cần định nghĩa rõ phép nhân, scale và rounding. Constructor thực tế cũng nên xác thực minimumSpend, maximumDiscount và rate cùng currency/miền giá trị phù hợp.

### 6.1. Kiểm thử khách không đủ điều kiện

~~~java
@Test
void regularCustomerReceivesNoGoldDiscount() {
    DiscountDecision decision = policy.evaluate(
        CustomerTier.REGULAR,
        money("2000000.00", "VND")
    );

    assertEquals(money("0", "VND"), decision.discount());
    assertEquals("CUSTOMER_NOT_ELIGIBLE", decision.reason());
}
~~~

### 6.2. Kiểm thử ngay dưới và đúng ngưỡng

~~~java
@Test
void goldCustomerBelowMinimumSpendReceivesNoDiscount() {
    DiscountDecision decision = policy.evaluate(
        CustomerTier.GOLD,
        money("999999.99", "VND")
    );

    assertEquals(money("0", "VND"), decision.discount());
}

@Test
void goldCustomerAtMinimumSpendReceivesDiscount() {
    DiscountDecision decision = policy.evaluate(
        CustomerTier.GOLD,
        money("1000000.00", "VND")
    );

    assertEquals(money("100000.00", "VND"), decision.discount());
}
~~~

### 6.3. Kiểm thử mức giảm tối đa

~~~java
@Test
void discountDoesNotExceedConfiguredCap() {
    DiscountDecision decision = policy.evaluate(
        CustomerTier.GOLD,
        money("5000000.00", "VND")
    );

    assertEquals(money("300000.00", "VND"), decision.discount());
}
~~~

Test này xác nhận mức trần nghiệp vụ, không kiểm tra cách Policy triển khai phép min. Nếu mức giảm tối đa thay đổi, expected value và cấu hình test phải phản ánh quy tắc đã được xác nhận.

### 6.4. Kiểm thử thứ tự ưu tiên và cộng dồn

Nếu có nhiều chính sách, hãy kiểm tra cả trường hợp một chính sách đủ điều kiện và trường hợp nhiều chính sách cùng đủ điều kiện. Ví dụ:

| Loyalty | Coupon | Quy tắc đã thống nhất | Kết quả cần kiểm tra |
|---|---|---|---|
| Không đủ điều kiện | Hợp lệ | Coupon áp dụng độc lập | Coupon được dùng |
| Hợp lệ | Không có | Loyalty áp dụng | Giảm Loyalty |
| Hợp lệ | Hợp lệ, loại trừ nhau | Coupon ưu tiên | Chỉ Coupon được dùng |
| Hợp lệ | Hợp lệ, được cộng dồn | Cộng theo thứ tự đã định | Tổng giảm đúng, không vượt trần |
| Hợp lệ | Hợp lệ, không rõ ưu tiên | Chưa có chính sách | Cần làm rõ trước khi chốt test |

Không nên chỉ test từng policy riêng lẻ nếu nghiệp vụ có quy tắc tương tác giữa chúng. Có thể test từng policy độc lập, sau đó test bộ chọn/chính sách phối hợp ở một phạm vi riêng.

## 7. Kiểm thử Domain Service với dữ liệu biên

Domain Service phù hợp khi một hành vi miền cần nhiều dữ liệu hoặc không thuộc tự nhiên về một Entity/Value Object cụ thể. Nó có thể là phép tính giá, xác định tuyến vận chuyển, phân bổ phí hoặc đánh giá điều kiện bảo hiểm.

Ví dụ, dịch vụ tính phí giao hàng dựa trên vùng và khối lượng:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

record WeightKg(BigDecimal value) {
    WeightKg {
        Objects.requireNonNull(value);
        if (value.signum() < 0) {
            throw new IllegalArgumentException("Weight cannot be negative");
        }
    }
}

record ShippingZone(String code) {}

record ShippingRequest(ShippingZone zone, WeightKg weight) {}

interface ShippingRateTable {
    Money baseRateFor(ShippingZone zone);
    Money surchargePerKgFor(ShippingZone zone);
}

final class ShippingCostCalculator {
    Money calculate(ShippingRequest request, ShippingRateTable rates) {
        Money base = rates.baseRateFor(request.zone());
        BigDecimal billableKg = request.weight().value()
            .setScale(0, RoundingMode.CEILING);
        Money surcharge = rates.surchargePerKgFor(request.zone())
            .multiply(billableKg);
        return base.add(surcharge);
    }
}
~~~

Test có thể dùng một rate table giả (fake) với dữ liệu xác định. Mục tiêu là xác nhận công thức nghiệp vụ và các biên của khối lượng/vùng, không cần gọi dịch vụ vận chuyển thật trong unit test.

Các trường hợp cần xem xét:

- Khối lượng bằng 0 có hợp lệ không?
- Khối lượng tối đa của một kiện là bao nhiêu?
- Ngưỡng chuyển bậc tính theo lớn hơn hay lớn hơn/bằng?
- Vùng không được hỗ trợ được từ chối hay dùng tuyến thay thế?
- Phụ phí được tính theo kg nguyên hay làm tròn lên mỗi phần kg?
- Phí cơ bản và phụ phí có cùng tiền tệ không?
- Tổng phí có mức tối thiểu hoặc tối đa không?

Một test về làm tròn có thể phân biệt 1,01 kg với 2 kg nếu chính sách tính mỗi kg lẻ thành một kg phí:

~~~java
@Test
void partialKilogramRoundsUpWhenPolicyChargesPerStartedKilogram() {
    ShippingRequest request = request("ZONE_A", "1.01");

    Money fee = calculator.calculate(request, rateTableWithPerStartedKg());

    assertEquals(money("30000", "VND"), fee);
}
~~~

Expected value ở đây phụ thuộc chính sách minh họa: phí cơ bản 10.000 VND và phụ phí 10.000 VND cho mỗi kg bắt đầu, nên 1,01 kg tính thành hai kg phụ phí. Nếu nghiệp vụ tính theo trọng lượng thực, kết quả phải khác. Test phải phản ánh quy tắc đã thống nhất, không phải một cách làm tròn tùy ý.

## 8. Kiểm thử thời gian, ngày hiệu lực và múi giờ

Chính sách thường phụ thuộc ngày bắt đầu, ngày kết thúc hoặc thời điểm hết hạn. Các lỗi biên có thể xuất hiện khi:

- Ngày bắt đầu có được tính hay không.
- Ngày kết thúc có được tính trọn ngày hay không.
- Thời điểm bắt đầu/kết thúc dùng timezone nào.
- Giờ chuyển mùa (DST) làm một thời điểm địa phương bị lặp hoặc không tồn tại.
- Hệ thống dùng clock thực khiến test lúc chạy được, lúc thất bại.

### 8.1. Dùng khoảng thời gian nửa mở

Một quy ước dễ kết hợp là khoảng nửa mở [start, end): bao gồm thời điểm bắt đầu và không bao gồm thời điểm kết thúc. Hai khoảng liên tiếp có thể nối nhau mà không chồng lấn:

- Ưu đãi A: từ 1/6 00:00 đến 1/7 00:00.
- Ưu đãi B: từ 1/7 00:00 đến 1/8 00:00.

Tại đúng 1/7 00:00, A đã hết hiệu lực và B bắt đầu có hiệu lực.

~~~java
import java.time.Instant;

record TimeWindow(Instant startsAt, Instant endsAt) {
    TimeWindow {
        if (!startsAt.isBefore(endsAt)) {
            throw new IllegalArgumentException("Invalid time window");
        }
    }

    boolean contains(Instant instant) {
        return !instant.isBefore(startsAt) && instant.isBefore(endsAt);
    }
}
~~~

Test:

~~~java
@Test
void timeWindowIncludesStartAndExcludesEnd() {
    Instant start = Instant.parse("2026-06-01T00:00:00Z");
    Instant end = Instant.parse("2026-07-01T00:00:00Z");
    TimeWindow window = new TimeWindow(start, end);

    assertTrue(window.contains(start));
    assertTrue(window.contains(end.minusNanos(1)));
    assertFalse(window.contains(end));
    assertFalse(window.contains(start.minusNanos(1)));
}
~~~

Nếu nghiệp vụ nói “đến hết ngày 30/6 theo giờ Việt Nam”, cần chuyển ngày địa phương sang khoảng Instant theo ZoneId được xác định, không gắn cứng UTC mà không giải thích.

### 8.2. Inject Clock thay vì đọc giờ hệ thống trực tiếp

Nếu Policy gọi Instant.now() trực tiếp, test khó kiểm soát thời điểm. Hãy truyền Clock hoặc thời điểm hiện tại vào:

~~~java
import java.time.Clock;
import java.time.Instant;

final class PromotionPolicy {
    private final TimeWindow validity;
    private final Clock clock;

    PromotionPolicy(TimeWindow validity, Clock clock) {
        this.validity = validity;
        this.clock = clock;
    }

    boolean isActive() {
        return validity.contains(clock.instant());
    }
}
~~~

Test dùng Clock cố định:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;

@Test
void promotionIsInactiveAtExclusiveEndInstant() {
    Instant end = Instant.parse("2026-07-01T00:00:00Z");
    Clock fixedClock = Clock.fixed(end, ZoneOffset.UTC);
    PromotionPolicy policy = new PromotionPolicy(
        new TimeWindow(
            Instant.parse("2026-06-01T00:00:00Z"),
            end
        ),
        fixedClock
    );

    assertFalse(policy.isActive());
}
~~~

Clock cố định giúp test xác định và có thể chạy lại. Test thêm các trường hợp trước thời điểm bắt đầu, đúng thời điểm bắt đầu, ngay trước thời điểm kết thúc và đúng thời điểm kết thúc.

## 9. Kiểm thử Aggregate và chuyển trạng thái

Policy có thể đúng riêng lẻ nhưng Aggregate vẫn có thể dùng sai kết quả hoặc cho phép một chuyển trạng thái không hợp lệ. Vì vậy cần test hành vi tại Aggregate Root.

Ví dụ quy tắc:

- Chỉ đơn nháp mới được thêm dòng.
- Không thể đặt đơn rỗng.
- Đơn đã đặt không được sửa dòng.
- Chỉ đơn đã đặt mới được xác nhận.
- Đơn đã giao không thể hủy theo chính sách hiện hành.

Test nên bao gồm cả hành vi hợp lệ và hành vi bị từ chối:

Các tên như newDraftOrder(), customerTier(), discountPolicy(), EmptyOrderCannotBePlaced và OrderIsNotEditable là fixture/kiểu lỗi minh họa. Trong ứng dụng thật, chúng cần khớp với API và ngôn ngữ của Aggregate đang được kiểm thử.

~~~java
@Test
void cannotPlaceAnOrderWithoutLines() {
    Order order = newDraftOrder();

    assertThrows(
        EmptyOrderCannotBePlaced.class,
        () -> order.place(customerTier(), discountPolicy())
    );
    assertEquals(OrderStatus.DRAFT, order.status());
}

@Test
void cannotAddLineAfterOrderHasBeenPlaced() {
    Order order = orderWithOneLine();
    order.place(customerTier(), discountPolicy());

    assertThrows(
        OrderIsNotEditable.class,
        () -> order.addLine(anotherLine())
    );
}
~~~

Điểm cần kiểm tra là khi hành vi thất bại, trạng thái Aggregate vẫn hợp lệ. Không chỉ assert rằng có exception; hãy xác nhận không có thay đổi một phần nếu quy tắc yêu cầu thao tác nguyên tử.

### 9.1. Kiểm thử invariant bằng nhiều đường gọi

Nếu một invariant chỉ được kiểm tra ở Application Service, một đường gọi khác có thể bỏ qua. Test Aggregate trực tiếp giúp chứng minh Aggregate Root tự bảo vệ quy tắc.

Ví dụ, không thể chỉ kiểm tra dòng hàng trong controller. Hãy gọi trực tiếp Order.place() với Aggregate rỗng và xác nhận nó từ chối.

### 9.2. Không kiểm tra setter thay cho hành vi

Test gọi setStatus("PLACED") rồi xác nhận giá trị mới chỉ kiểm tra cấu trúc dữ liệu. Test nên gọi place() và xác nhận các điều kiện để đơn được đặt, trạng thái kết quả và event tương ứng.

## 10. Kiểm thử Domain Event

Domain Event diễn đạt sự thật nghiệp vụ đã xảy ra. Khi một hành vi thành công, test có thể xác nhận event đúng được tạo; khi hành vi bị từ chối, event thành công không được phát ra.

Ví dụ:

| Hành vi | Event mong đợi |
|---|---|
| Đặt đơn hợp lệ | OrderPlaced |
| Đặt đơn rỗng | Không có OrderPlaced |
| Hủy đơn hợp lệ | OrderCancelled |
| Hủy đơn đã giao và bị cấm | Không có OrderCancelled |
| Áp dụng ưu đãi thành công | DiscountApplied nếu domain cần ghi nhận sự thật đó |

Test event nên xác nhận nội dung có ý nghĩa, như orderId, giá đã chốt, discount và thời điểm nghiệp vụ. Không nên phụ thuộc vào class serializer hoặc message broker trong unit test Aggregate.

### 10.1. Phân biệt Domain Event với Integration Event

Domain Event nội bộ mô tả sự thật trong một bounded context. Integration Event là hợp đồng được công bố qua ranh giới tích hợp. Unit test domain kiểm tra event nội bộ. Contract test kiểm tra payload, version và tương thích của integration event.

Không nên dùng một test unit để cố kiểm tra toàn bộ broker, serialization và consumer. Những mối quan tâm đó cần test ở phạm vi tích hợp phù hợp.

## 11. Kiểm thử Domain Service với dependency bên ngoài

Domain Service đôi khi cần dữ liệu từ một cổng (port) như bảng giá, lịch làm việc hoặc tỷ giá đã được xác định. Unit test nên thay dependency đó bằng fake có dữ liệu xác định.

Ví dụ:

~~~java
final class FixedShippingRateTable implements ShippingRateTable {
    @Override
    public Money baseRateFor(ShippingZone zone) {
        return money("10000", "VND");
    }

    @Override
    public Money surchargePerKgFor(ShippingZone zone) {
        return money("10000", "VND");
    }
}
~~~

Fake là một implementation nhỏ, có hành vi xác định và phục vụ test. Nó thường dễ hiểu hơn một mock phức tạp phải cấu hình nhiều lời gọi.

Nếu dịch vụ miền cần tỷ giá ngoại tệ, hãy quyết định tỷ giá thuộc dữ liệu đầu vào hay được lấy qua port. Test cần dùng một tỷ giá cố định và xác nhận kết quả. Không gọi dịch vụ tỷ giá thật trong unit test vì kết quả thay đổi theo thời gian và mạng.

### 11.1. Khi nào dùng mock?

Mock có ích khi cần xác nhận một tương tác là hợp đồng quan trọng, ví dụ application handler yêu cầu một port lưu Aggregate hoặc gửi command sau commit. Nhưng không nên mock mọi collaborator nội bộ của Policy rồi xác nhận chuỗi lời gọi; cách đó khiến test gắn chặt implementation.

### 11.2. Không dùng mock để giả lập chính quy tắc cần kiểm thử

Nếu mục tiêu là kiểm tra DiscountPolicy, hãy dùng implementation thật của DiscountPolicy. Mock chính Policy rồi assert nó trả về một số tiền đã định sẽ không kiểm tra quy tắc nào.

## 12. Các nhóm trường hợp biên cần rà soát

Khi kiểm thử chính sách và dịch vụ miền, hãy xem xét các nhóm sau. Không phải nhóm nào cũng áp dụng cho mọi domain; hãy chọn theo quy tắc thực tế.

| Nhóm | Câu hỏi biên | Ví dụ |
|---|---|---|
| Ngưỡng số | Ngay dưới, đúng bằng, ngay trên? | Subtotal tối thiểu |
| Giới hạn | Giá trị tối đa có được bao gồm? | Số lượng tối đa mỗi đơn |
| Giá trị rỗng | Không có phần tử thì sao? | Đơn không có dòng hàng |
| Giá trị null | Có được phép vắng mặt? | Địa chỉ giao hàng chưa nhập |
| Số âm | Có ý nghĩa hay phải từ chối? | Quantity, discount, weight |
| Độ chính xác | Làm tròn ở bước nào? | Thuế, phí, chiết khấu |
| Đơn vị | Có thể so sánh trực tiếp? | kg và lb |
| Tiền tệ | Có cùng currency không? | VND và USD |
| Thời gian | Biên bắt đầu/kết thúc? | Promotion validity |
| Múi giờ | Thời gian địa phương được hiểu theo vùng nào? | Hạn thanh toán |
| Trạng thái | Chuyển đổi nào bị cấm? | Cancelled sang Confirmed |
| Trùng lặp | Cùng ID hoặc SKU xuất hiện hai lần? | Dòng hàng, coupon |
| Ưu tiên | Nhiều policy cùng đủ điều kiện? | Loyalty và coupon |
| Dữ liệu ngoài | Mã chưa biết hoặc dữ liệu thiếu? | Supplier status |
| Đồng thời | Hai command cùng tranh một giới hạn? | Giữ tồn kho |

### 12.1. Giá trị rỗng và null

Phân biệt collection rỗng với null. Collection rỗng có thể là một giá trị hợp lệ nhưng không chứa phần tử; null có thể biểu thị chưa biết hoặc chưa cung cấp. Domain model nên định nghĩa rõ.

Ví dụ, đơn nháp có thể chưa có dòng hàng, nhưng hành vi place() phải từ chối đơn rỗng. Một Policy tính phí giao hàng có thể từ chối địa chỉ null hoặc trả kết quả yêu cầu bổ sung địa chỉ, tùy use case.

### 12.2. Giá trị âm và zero

Zero không luôn giống âm. Số lượng bằng 0 có thể không hợp lệ; phí vận chuyển bằng 0 có thể hợp lệ trong chiến dịch miễn phí; discount bằng 0 có thể là kết quả hợp lệ khi không đủ điều kiện. Test cần phân biệt các trường hợp đó.

### 12.3. Độ chính xác và làm tròn

Với số tiền, cần xác định:

- Precision/scale của dữ liệu.
- Rounding mode.
- Làm tròn từng dòng hay tổng đơn.
- Làm tròn trước hay sau khi cộng thuế/chiết khấu.
- Sự khác biệt giữa phần trăm hiển thị và tỷ lệ tính toán.

Một test tổng tiền có thể kiểm tra trường hợp nhiều dòng có phần thập phân để phát hiện sai lệch do làm tròn từng dòng so với làm tròn tổng.

## 13. Test Domain Service theo tính chất (Property-Based Testing)

Example-based testing xác nhận một số ví dụ cụ thể. Property-based testing kiểm tra các tính chất phải luôn đúng trên nhiều bộ dữ liệu được sinh tự động.

Ví dụ với một chính sách giảm giá:

- Discount không âm.
- Discount không vượt subtotal.
- Total bằng subtotal trừ discount.
- Khách không đủ điều kiện không được giảm.
- Cùng đầu vào và cùng policy cho cùng kết quả.

Pseudo-test:

~~~java
@Property
void discountNeverExceedsSubtotal(
        @ForAll("positiveSubtotals") BigDecimal subtotalValue) {
    Money subtotal = money(subtotalValue, "VND");

    DiscountDecision decision =
        policy.evaluate(CustomerTier.GOLD, subtotal);

    assertTrue(decision.discount().compareTo(Money.zero(VND)) >= 0);
    assertTrue(decision.discount().compareTo(subtotal) <= 0);
}
~~~

Đoạn code minh họa phong cách property-based testing; annotation và provider phụ thuộc thư viện được chọn, chẳng hạn jqwik. Generator phải tạo dữ liệu hợp lệ theo miền, đồng thời có generator riêng cho dữ liệu biên và không hợp lệ.

Property-based testing không thay thế ví dụ nghiệp vụ. Nó bổ sung khả năng khám phá tổ hợp và giá trị mà người viết test có thể bỏ sót.

### 13.1. Invariant có thể biểu diễn thành property

Ví dụ:

- Tổng tiền không âm nếu mọi dòng và chính sách đều không âm.
- Tổng số lượng bằng tổng số lượng các dòng sau khi chuẩn hóa SKU.
- Một khoảng thời gian hợp lệ luôn có start trước end.
- Sau khi hủy, Aggregate không thể quay lại trạng thái đã đặt nếu không có hành vi khôi phục được nghiệp vụ cho phép.

Property cần được viết dựa trên quy tắc đã xác nhận. Không nên áp đặt property toán học sai với nghiệp vụ, chẳng hạn giả định cộng tiền luôn giao hoán khi hai loại tiền khác nhau.

## 14. Kiểm thử bảng quyết định và tổ hợp điều kiện

Với Policy có nhiều điều kiện, có thể lưu test case dưới dạng bảng dữ liệu để tránh bỏ sót và giảm code lặp.

Ví dụ JUnit parameterized test:

~~~java
@ParameterizedTest
@MethodSource("discountCases")
void evaluatesLoyaltyDiscount(
        CustomerTier tier,
        String subtotal,
        String expectedDiscount) {
    DiscountDecision decision = policy.evaluate(
        tier,
        money(subtotal, "VND")
    );

    assertEquals(
        money(expectedDiscount, "VND"),
        decision.discount()
    );
}

static Stream<Arguments> discountCases() {
    return Stream.of(
        arguments(CustomerTier.REGULAR, "2000000.00", "0"),
        arguments(CustomerTier.GOLD, "999999.99", "0"),
        arguments(CustomerTier.GOLD, "1000000.00", "100000.00"),
        arguments(CustomerTier.GOLD, "5000000.00", "300000.00")
    );
}
~~~

Các case được đặt tên hoặc ghi chú theo quy tắc để người đọc biết vì sao mỗi hàng tồn tại. Tránh biến bảng test thành một danh sách số khó hiểu không có liên kết với nghiệp vụ.

## 15. Kiểm thử tính xác định và phụ thuộc thời gian

Policy và Domain Service nên cho kết quả xác định với cùng đầu vào và cùng phiên bản chính sách. Nếu phụ thuộc thời gian, timezone, tỷ giá hoặc cấu hình, các phụ thuộc đó cần được truyền vào hoặc được kiểm soát trong test.

Nên:

- Truyền Clock thay vì gọi thời gian hệ thống rải rác.
- Dùng tỷ giá hoặc bảng giá cố định trong unit test.
- Đưa rounding mode và scale thành quy tắc rõ ràng.
- Cố định locale nếu chuẩn hóa chữ hoặc định dạng có liên quan.
- Không phụ thuộc thứ tự iteration của collection không có thứ tự.
- Không đọc dữ liệu môi trường hoặc remote service trong test miền.

Nếu một chính sách thay đổi theo ngày, test cần kiểm tra đúng thời điểm hiệu lực và đúng phiên bản policy. Không nên dùng ngày hiện tại của máy chạy test làm đầu vào ngầm.

## 16. Kiểm thử các mức tích hợp liên quan

Unit test không đủ để chứng minh Repository, transaction hoặc integration adapter hoạt động đúng. Hãy phân chia theo ranh giới:

| Loại test | Phạm vi | Ví dụ |
|---|---|---|
| Unit test miền | Value Object, Aggregate, Policy, Domain Service | Ngưỡng chiết khấu, điều kiện hủy đơn |
| Application test | Điều phối use case và transaction boundary | Handler tải Aggregate, gọi policy, lưu kết quả |
| Repository integration test | ORM, mapping, query và transaction với database | Lưu và tải lại Money/Order, optimistic locking |
| Contract test | Hợp đồng API/event với bên ngoài | Mã trạng thái, payload, schema version |
| Component/integration test | Nhiều thành phần chạy cùng nhau | Outbox, event handler, projection |
| End-to-end test | Một hành trình người dùng xuyên hệ thống | Đặt đơn, thanh toán và xem trạng thái |

### 16.1. Repository integration test

Repository test nên dùng database thật hoặc môi trường gần production khi mapping, locking, constraint hoặc SQL có ảnh hưởng. Một fake repository trong unit test không thể chứng minh ORM mapping hoặc transaction isolation đúng.

Các trường hợp đáng kiểm tra:

- Aggregate được lưu và tải lại giữ nguyên giá trị miền.
- Unique constraint ngăn dữ liệu trùng theo quy tắc.
- Optimistic locking phát hiện hai lần cập nhật cạnh tranh.
- Transaction rollback khi invariant hoặc persistence constraint thất bại.
- Query trả đúng dữ liệu và không làm mất precision.

### 16.2. Application Service test

Application test kiểm tra điều phối, ví dụ:

- Không tìm thấy Aggregate thì use case trả lỗi phù hợp.
- Policy được gọi với snapshot/đầu vào đã xác định.
- Aggregate được lưu khi hành vi hợp lệ.
- Event được ghi nhận theo transaction boundary.
- Khi hành vi miền từ chối, không lưu trạng thái thành công.

Không nên kiểm tra lại mọi quy tắc chiết khấu ở Application Service test nếu đã có unit test chuyên biệt cho Policy.

### 16.3. Contract test cho ACL và dịch vụ ngoài

Nếu Domain Service phụ thuộc một port được adapter triển khai, contract test có thể xác nhận dữ liệu từ nhà cung cấp được dịch thành kiểu miền đúng. Ví dụ:

- Mã trạng thái hợp lệ được ánh xạ đúng.
- Mã chưa biết được xử lý theo chính sách.
- Lỗi timeout không bị biến thành “không tìm thấy”.
- Tiền tệ và đơn vị được giữ nguyên hoặc quy đổi theo quy tắc.

Unit test miền nên dùng fake port. Contract test mới kiểm tra adapter và hợp đồng ngoài.

## 17. Kiểm thử Domain Event Handler và tính lặp an toàn

Event handler có thể được gọi nhiều lần do cơ chế giao nhận message. Nếu handler thực hiện một hành động nghiệp vụ như cộng điểm hoặc tạo reservation, cần kiểm thử tính idempotent.

Ví dụ:

- Cùng một event ID chỉ được cộng điểm một lần.
- Event cũ không ghi đè trạng thái mới hơn.
- Handler retry sau lỗi tạm thời không tạo giao dịch trùng.
- Event sai schema hoặc thiếu dữ liệu được cách ly và quan sát được.

Đây là test ở ranh giới handler/integration, không phải unit test của Policy thuần. Hãy tách rõ test logic quyết định khỏi test delivery, persistence và deduplication.

## 18. Kiểm thử đồng thời khi chính sách phụ thuộc giới hạn dùng chung

Một Policy có thể kiểm tra “còn tối đa 100 voucher” hoặc “mỗi khách chỉ dùng một lần”. Unit test Policy có thể xác nhận logic điều kiện, nhưng không thể chứng minh hai request đồng thời không cùng vượt giới hạn nếu dữ liệu được cập nhật trong database.

Phân biệt:

- **Quy tắc quyết định:** voucher còn hiệu lực và khách đủ điều kiện không? Kiểm thử Policy.
- **Tính nhất quán khi ghi:** hai request cùng dùng voucher có được ghi nhận trùng không? Kiểm thử integration/concurrency với transaction và constraint.

Nếu giới hạn thuộc một Aggregate hoặc context, thao tác kiểm tra và tiêu thụ quyền sử dụng cần được bảo vệ trong transaction của nơi sở hữu dữ liệu. Không dựa vào một query read model có thể trễ.

## 19. Test fixture, builder và dữ liệu dễ đọc

Test miền thường cần tạo nhiều object hợp lệ. Fixture tốt giúp người đọc tập trung vào quy tắc thay vì boilerplate.

Ví dụ:

~~~java
Order order = anOrder()
    .forCustomer(CustomerTier.GOLD)
    .withLine("SKU-1", 2, money("500000", "VND"))
    .build();
~~~

Builder nên có giá trị mặc định hợp lệ và cho phép thay đổi những thuộc tính liên quan tới scenario. Tránh builder có hàng chục field tùy chọn không rõ ý nghĩa.

Một số nguyên tắc:

- Tên fixture phản ánh vai trò nghiệp vụ.
- Giá trị mặc định không che giấu điều kiện của test.
- Dữ liệu trong test nên ngắn và dễ tính nhẩm.
- Không dùng factory ngẫu nhiên không seed khi kết quả ảnh hưởng assertion.
- Dùng object mother khi có một vài mẫu miền phổ biến; dùng builder khi test cần tùy chỉnh.
- Tránh chia sẻ object mutable giữa nhiều test.

## 20. Đặt tên test theo Given–When–Then

Tên test tốt mô tả điều kiện và kết quả:

- goldCustomerAtMinimumSpendReceivesDiscount
- regularCustomerDoesNotReceiveLoyaltyDiscount
- discountIsCappedAtMaximumAllowedAmount
- promotionIsInactiveAtExclusiveEndInstant
- orderCannotBePlacedWithoutLines
- shippedOrderCannotBeCancelled

Có thể tổ chức test theo Given–When–Then:

1. **Given:** khách Gold có subtotal đúng ngưỡng.
2. **When:** chính sách chiết khấu được đánh giá.
3. **Then:** khoản giảm 10% được trả về.

Không nhất thiết phải dùng framework BDD riêng. Điều quan trọng là test có cấu trúc và ngôn ngữ dễ đọc.

## 21. Mutation Testing giúp đánh giá chất lượng test

Mutation testing tạo ra những thay đổi nhỏ có chủ đích trong code, ví dụ:

- Đổi điều kiện subtotal >= threshold thành subtotal > threshold.
- Bỏ giới hạn discount tối đa.
- Đổi rounding mode.
- Bỏ kiểm tra currency mismatch.
- Cho phép hủy đơn sau khi giao.

Nếu test vẫn pass sau mutation, có thể test chưa kiểm tra đúng quy tắc hoặc scenario biên còn thiếu.

Mutation testing không thay thế review nghiệp vụ và không phải lúc nào cũng cần chạy cho mọi module. Nó hữu ích với Policy quan trọng, nhiều nhánh và có hậu quả tài chính hoặc vận hành lớn.

## 22. Những anti-pattern khi kiểm thử chính sách và dịch vụ miền

- **Chỉ test happy path:** bỏ qua ngưỡng, giới hạn, dữ liệu thiếu và xung đột chính sách.
- **Test một giá trị ở xa biên:** không phát hiện lỗi dùng > thay vì >=.
- **Assert chi tiết implementation:** refactor nhỏ làm test hỏng dù hành vi không đổi.
- **Mock chính đối tượng cần kiểm thử:** test chỉ xác nhận mock trả về dữ liệu đã cấu hình.
- **Khởi động toàn bộ Spring cho mọi unit test:** test chậm và lỗi hạ tầng che lấp lỗi miền.
- **Dùng thời gian thực:** test phụ thuộc giờ chạy và timezone của máy.
- **So sánh tiền tệ bằng BigDecimal không nhất quán:** test có thể sai do scale hoặc thiếu currency.
- **Không xác định rounding:** các test tiền có kết quả khác nhau giữa các implementation.
- **Test quy tắc ở nhiều tầng giống hệt nhau:** suite dài nhưng không tăng độ tin cậy.
- **Dùng fixture quá thông minh:** người đọc không biết dữ liệu thực tế của scenario.
- **Bỏ qua tương tác giữa các Policy:** từng policy đúng nhưng khi phối hợp lại sai.
- **Không test lỗi:** lỗi kỹ thuật bị ánh xạ thành kết quả nghiệp vụ sai.
- **Chỉ kiểm tra exception:** không xác nhận trạng thái Aggregate không bị thay đổi một phần.
- **Dùng fake để chứng minh database behavior:** fake không mô phỏng transaction, constraint hoặc locking thật.
- **Test theo code thay vì quy tắc:** test lặp lại logic implementation và không bắt được hiểu sai nghiệp vụ.

## 23. Quy trình xây bộ test cho một Policy hoặc Domain Service

Có thể thực hiện theo trình tự:

1. **Xác nhận quy tắc với chuyên gia:** làm rõ điều kiện, ngoại lệ, thứ tự ưu tiên và thời điểm áp dụng.
2. **Định nghĩa đầu vào/đầu ra:** dùng kiểu miền có ý nghĩa, xác định nullability và đơn vị.
3. **Lập decision table:** liệt kê tổ hợp điều kiện và kết quả.
4. **Tìm giá trị biên:** dưới, đúng và trên từng ngưỡng; ngày bắt đầu/kết thúc; min/max.
5. **Kiểm thử Value Object:** bảo đảm dữ liệu nền hợp lệ và phép toán đúng.
6. **Viết unit test Policy/Domain Service:** test quyết định, kết quả và lý do.
7. **Kiểm thử Aggregate:** xác nhận invariant, chuyển trạng thái và event.
8. **Kiểm thử tích hợp ở ranh giới:** repository, transaction, adapter và event handler.
9. **Kiểm thử tính chất hoặc mutation khi phù hợp:** tìm trường hợp mà ví dụ cụ thể chưa bao phủ.
10. **Đọc lại test cùng ngôn ngữ miền:** chuyên gia có thể hiểu scenario và expected result không?

~~~mermaid
flowchart TD
    A[Quy tắc nghiệp vụ] --> B[Trao đổi và làm rõ]
    B --> C[Decision table]
    C --> D[Boundary cases]
    D --> E[Unit tests cho VO / Policy / Domain Service]
    E --> F[Aggregate behavior tests]
    F --> G[Integration / Contract tests]
    G --> H{Quy tắc và ranh giới đã được kiểm chứng?}
    H -->|Chưa| B
    H -->|Rồi| I[Review và duy trì bộ test]
~~~

## 24. Checklist kiểm thử chính sách và dịch vụ miền

Trước khi hoàn thiện bộ test, hãy kiểm tra:

- [ ] Quy tắc đã được xác nhận bằng ngôn ngữ nghiệp vụ.
- [ ] Đầu vào, đầu ra, đơn vị và nullability được xác định rõ.
- [ ] Có test cho trường hợp bình thường và trường hợp không đủ điều kiện.
- [ ] Mỗi ngưỡng quan trọng có test dưới, đúng và trên biên.
- [ ] Giới hạn tối đa/tối thiểu được kiểm tra.
- [ ] Đã xem xét zero, negative, null, empty và duplicate khi có ý nghĩa.
- [ ] Currency, precision, scale và rounding được kiểm thử.
- [ ] Ngày hiệu lực, timezone và thời điểm kết thúc được kiểm thử bằng Clock cố định.
- [ ] Tương tác giữa nhiều Policy có test riêng.
- [ ] Domain Service dùng fake hoặc dữ liệu xác định cho dependency.
- [ ] Aggregate tự bảo vệ invariant và không đổi trạng thái khi hành vi bị từ chối.
- [ ] Domain Event đúng chỉ xuất hiện sau hành vi hợp lệ.
- [ ] Repository và concurrency được kiểm thử bằng integration test phù hợp.
- [ ] Contract và adapter xử lý dữ liệu/lỗi ngoài đúng ý nghĩa.
- [ ] Test không phụ thuộc implementation detail không phải hợp đồng.
- [ ] Fixture rõ ràng, có giá trị dễ đọc và không chia sẻ mutable state.
- [ ] Có property-based hoặc mutation testing khi rủi ro và độ phức tạp phù hợp.

## 25. Câu hỏi tự kiểm tra

1. Policy và Domain Service khác nhau như thế nào về trách nhiệm?
2. Vì sao test chính sách phải dựa trên quyết định nghiệp vụ thay vì chi tiết implementation?
3. Decision table giúp tìm trường hợp thiếu như thế nào?
4. Với ngưỡng tối thiểu T, vì sao cần kiểm tra T - ε, T và T + ε?
5. Làm thế nào phân biệt zero, null và collection rỗng trong một quy tắc?
6. Vì sao Money cần kiểm tra currency, precision và rounding?
7. Khoảng thời gian nửa mở [start, end) giúp tránh lỗi biên nào?
8. Vì sao nên truyền Clock vào Policy phụ thuộc thời gian?
9. Aggregate test cần kiểm tra điều gì khi hành vi bị từ chối?
10. Khi nào dùng fake, khi nào dùng mock và khi nào cần integration test?
11. Property-based testing bổ sung gì cho example-based testing?
12. Mutation testing giúp phát hiện bộ test yếu như thế nào?
13. Vì sao một unit test không thể chứng minh optimistic locking hoặc transaction của database?
14. Làm thế nào kiểm thử tương tác giữa nhiều Policy có thể cùng đủ điều kiện?

## Kết luận

Kiểm thử chính sách và dịch vụ miền cần bắt đầu từ ngôn ngữ, điều kiện và quyết định nghiệp vụ. Bảng quyết định giúp nhìn thấy tổ hợp điều kiện; phân tích giá trị biên phát hiện lỗi tại ngưỡng; test Value Object, Policy, Domain Service và Aggregate xác nhận quy tắc được bảo vệ đúng nơi. Integration và contract test kiểm tra các bảo đảm phụ thuộc database hoặc hệ thống bên ngoài.

Hãy chọn test case theo rủi ro và ý nghĩa miền, kiểm tra dưới/đúng/trên biên, kiểm soát thời gian và tiền tệ, đồng thời xác nhận trạng thái không thay đổi khi hành vi bị từ chối. Một bộ test tốt giúp chuyên gia và đội phát triển cùng nhìn thấy chính sách đang được thực thi, hỗ trợ thay đổi mô hình mà vẫn giữ được các cam kết nghiệp vụ.
