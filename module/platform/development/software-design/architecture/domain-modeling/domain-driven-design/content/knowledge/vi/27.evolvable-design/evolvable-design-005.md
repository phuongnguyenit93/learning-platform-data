# Phép toán khép kín trên Value Object khi phù hợp

Trong Domain-Driven Design (DDD), Value Object biểu diễn một khái niệm được xác định bằng giá trị và các quy tắc của nó, chẳng hạn Money, Quantity, Percentage hoặc DateRange. Một Value Object tốt không chỉ gom các field có liên quan; nó còn có thể cung cấp những phép toán mang ý nghĩa nghiệp vụ và bảo vệ bất biến của chính giá trị đó.

Một ý tưởng hữu ích khi thiết kế API cho Value Object là **closure (tính khép kín)**: một phép toán nhận các giá trị thuộc một kiểu và trả về một giá trị cùng kiểu, miễn là phép toán đó hợp lệ trong miền. Ví dụ, cộng hai khoản tiền cùng loại tiền trả về một Money mới; cộng hai khoảng số lượng cùng đơn vị trả về một Quantity mới.

Tính khép kín giúp người gọi tiếp tục làm việc với mô hình miền thay vì phải lấy primitive ra, tự tính rồi dựng lại object. Tuy nhiên, không phải phép toán nào cũng nên trả về cùng kiểu. Giao của hai DateRange có thể không tồn tại; hợp của hai khoảng rời nhau có thể là hai khoảng; chia Money cho Money có thể tạo ra một tỷ lệ. Ép những kết quả này thành cùng Value Object sẽ làm sai ngữ nghĩa.

Bài học tập trung vào việc chọn phép toán khép kín khi nó phản ánh đúng khái niệm, giữ bất biến, thiết kế API dễ tiến hóa và kiểm thử các quy tắc giá trị.

Sau bài học, người học có thể:

- Giải thích closure trong thiết kế phép toán trên Value Object.
- Thiết kế phương thức trả về một Value Object mới thay vì sửa object hiện tại.
- Bảo vệ invariant khi cộng, trừ, nhân hoặc so sánh giá trị.
- Nhận biết khi phép toán chỉ hợp lệ trên một miền con, chẳng hạn cùng currency hoặc cùng unit.
- Phân biệt phép toán khép kín với phép toán có kết quả là kiểu khác hoặc có thể không có kết quả.
- Quyết định khi nào logic thuộc Value Object và khi nào cần Domain Service hoặc policy.
- Kiểm thử tính bất biến, closure, equality và các tính chất đại số có ý nghĩa.
- Tiến hóa API Value Object mà không làm lộ primitive hoặc phá vỡ consumer.

## 1. Closure là gì?

Trong đại số, một phép toán hai ngôi trên tập S được gọi là khép kín nếu với mọi a và b thuộc S, kết quả a ⊙ b cũng thuộc S.

\[
a, b \in S \Rightarrow a \odot b \in S
\]

Trong thiết kế phần mềm, có thể diễn đạt thực tế hơn:

- Phương thức nhận một hoặc nhiều giá trị miền.
- Khi điều kiện nghiệp vụ hợp lệ, phương thức trả về một instance thuộc cùng kiểu Value Object.
- Instance kết quả thỏa mãn invariant của kiểu đó.
- Object đầu vào không bị thay đổi ngoài ý muốn.

Ví dụ:

~~~java
Money total = unitPrice.plus(shippingFee);
~~~

Nếu phương thức plus nhận hai Money cùng currency và trả về Money mới, phép cộng này khép kín trên nhóm Money có cùng currency.

Ngược lại:

~~~java
BigDecimal total = unitPrice.amount().add(shippingFee.amount());
~~~

Cách tính trên đưa người gọi ra khỏi ngôn ngữ miền. Caller phải tự nhớ kiểm tra currency, scale, rounding và cách dựng lại Money. Nếu nhiều nơi tự làm, quy tắc có thể bị lặp hoặc không nhất quán.

### Closure trong code không chỉ là chữ ký trả về

Một phương thức có chữ ký Money plus(Money other) chưa chắc được thiết kế đúng. Nếu nó âm thầm cộng hai currency khác nhau, bỏ qua invariant hoặc mutate object hiện tại, nó chỉ có vẻ khép kín về kiểu dữ liệu.

Closure có ý nghĩa khi kết quả cùng kiểu đồng thời vẫn đúng ngữ nghĩa và hợp lệ theo quy tắc của Value Object.

## 2. Vì sao phép toán khép kín hữu ích với Value Object?

### Giữ ngôn ngữ nghiệp vụ trong API

Thay vì thao tác trên primitive:

~~~java
BigDecimal newAmount = oldAmount.add(adjustment);
Money newBalance = new Money(newAmount, currency);
~~~

có thể diễn đạt trực tiếp:

~~~java
Money newBalance = balance.plus(adjustment);
~~~

Tên phương thức phản ánh ý định. Caller không cần biết cách lưu trữ nội bộ là BigDecimal, integer minor units hay một biểu diễn khác.

### Giữ invariant tại nơi sở hữu giá trị

Money có thể yêu cầu currency hợp lệ. Quantity có thể yêu cầu số lượng không âm và đơn vị đo phù hợp. DateRange có thể yêu cầu ngày bắt đầu trước ngày kết thúc.

Nếu phép toán nằm trong Value Object, object có thể kiểm tra điều kiện và chỉ tạo kết quả hợp lệ. Caller không phải tự nhớ mọi quy tắc trước khi dựng object.

### Hỗ trợ tính bất biến

Value Object thường được thiết kế immutable. Phép toán trả về object mới:

~~~java
Money original = Money.of("100.00", usd);
Money increased = original.plus(Money.of("15.00", usd));
~~~

original vẫn giữ nguyên 100.00; increased là 115.00. Hai object có thể được truyền qua nhiều tầng mà không lo một caller khác âm thầm sửa giá trị.

### Giảm phụ thuộc vào cách biểu diễn

Nếu Money đổi từ BigDecimal sang số nguyên minor units, caller vẫn có thể gọi plus, minus và compareTo. Đây là một lợi ích của việc đóng gói hành vi cùng dữ liệu: implementation có thể thay đổi trong khi hợp đồng miền ổn định.

## 3. Điều kiện để một phép toán khép kín đúng nghĩa

Một phép toán khép kín trên Value Object nên đáp ứng các điều kiện sau:

1. **Đúng miền:** các toán hạng thuộc cùng khái niệm và tương thích theo quy tắc.
2. **Giữ invariant:** kết quả thỏa mọi điều kiện tạo lập của Value Object.
3. **Bất biến đầu vào:** không thay đổi các object đã nhận.
4. **Kết quả rõ ràng:** trả cùng kiểu nếu kết quả thực sự vẫn là cùng khái niệm.
5. **Lỗi có ý nghĩa:** trường hợp không hợp lệ được từ chối hoặc biểu diễn rõ, không tự sửa dữ liệu âm thầm.
6. **Không phụ thuộc hạ tầng:** phép toán thuần giá trị không gọi database, HTTP hoặc đọc đồng hồ toàn cục.

Không phải mọi phép toán đều được định nghĩa cho mọi cặp giá trị cùng kiểu. Money có currency khác nhau không thể cộng trực tiếp; Quantity ở đơn vị kg và m không thể cộng. Đây là phép toán khép kín trên miền đầu vào hợp lệ, chứ không phải trên mọi instance bất kể trạng thái.

## 4. Ví dụ Money: cộng và trừ cùng currency

Money không chỉ là một số thập phân. Nó bao gồm số tiền và currency. Hai giá trị 100 USD và 100 EUR không thể coi là cùng một giá trị chỉ vì phần số bằng nhau.

Ví dụ sau dùng Java record. BigDecimal và Currency đều bất biến nên phù hợp để tạo một Value Object bất biến.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency)
        implements Comparable<Money> {

    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        amount = amount.stripTrailingZeros();
    }

    public static Money of(String amount, Currency currency) {
        return new Money(new BigDecimal(amount), currency);
    }

    public static Money zero(Currency currency) {
        return new Money(BigDecimal.ZERO, currency);
    }

    public Money plus(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money minus(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    public Money negate() {
        return new Money(amount.negate(), currency);
    }

    public Money times(
            BigDecimal factor,
            int scale,
            RoundingMode roundingMode
    ) {
        Objects.requireNonNull(factor, "factor");
        Objects.requireNonNull(roundingMode, "roundingMode");

        BigDecimal result = amount.multiply(factor)
                .setScale(scale, roundingMode);

        return new Money(result, currency);
    }

    public boolean isZero() {
        return amount.signum() == 0;
    }

    public boolean isPositive() {
        return amount.signum() > 0;
    }

    @Override
    public int compareTo(Money other) {
        requireSameCurrency(other);
        return amount.compareTo(other.amount);
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                    "Cannot operate on different currencies: "
                            + currency + " and " + other.currency
            );
        }
    }
}
~~~

Các phương thức plus, minus, negate và times đều trả về Money mới. Currency được giữ nguyên. Constructor kiểm tra null và chuẩn hóa scale bằng stripTrailingZeros, vì vậy 10.0 và 10.00 có biểu diễn giá trị tương đương trong record này.

Ví dụ cho phép Money âm để biểu diễn khoản điều chỉnh, bút toán đảo hoặc chênh lệch. Nếu một khái niệm nghiệp vụ như UnitPrice hoặc ChargeAmount không được âm, hãy tạo Value Object riêng với invariant không âm thay vì áp một quy tắc cho mọi Money.

### Cộng hai khoản tiền

~~~java
Currency usd = Currency.getInstance("USD");

Money itemTotal = Money.of("120.00", usd);
Money shipping = Money.of("8.50", usd);

Money payable = itemTotal.plus(shipping);
// Money(128.5, USD)

Money beforeDiscount = payable;
Money discount = Money.of("10.00", usd);
Money afterDiscount = payable.minus(discount);
// Money(118.5, USD)
~~~

Caller không cần lấy amount ra để cộng. Money.plus kiểm tra currency và bảo đảm kết quả tiếp tục là Money.

### Currency mismatch phải được xử lý rõ

~~~java
Money dollars = Money.of("100", Currency.getInstance("USD"));
Money euros = Money.of("100", Currency.getInstance("EUR"));

dollars.plus(euros); // Từ chối: không thể cộng trực tiếp.
~~~

Không được tự chọn currency của toán hạng bên trái hoặc coi hai con số có thể cộng vì cùng kiểu BigDecimal. Nếu cần chuyển đổi, phải có tỷ giá và chính sách làm tròn rõ ràng.

Một phép đổi tiền có thể có chữ ký:

~~~java
Money convertTo(
        Currency target,
        ExchangeRate rate,
        MoneyRoundingPolicy roundingPolicy
);
~~~

Phép đổi có thể vẫn trả về Money, nhưng nó phụ thuộc vào một tỷ giá có ngữ cảnh: cặp currency, chiều tỷ giá, thời điểm hiệu lực, nguồn và rounding policy. Nếu những dữ kiện này cần được truy vấn hoặc lựa chọn theo nghiệp vụ, việc phối hợp nên nằm ở domain service hoặc application layer; Value Object vẫn có thể thực hiện phép tính thuần khi đã nhận đủ dữ kiện.

### Rounding là một phần của ngữ nghĩa

Cộng và trừ BigDecimal có thể thực hiện chính xác theo giá trị thập phân đã lưu. Nhân hoặc chia thường cần quy tắc scale và rounding.

Không nên để phương thức times tự chọn HALF_UP hoặc số chữ số thập phân mà không có hợp đồng. Chính sách làm tròn có thể phụ thuộc currency, loại giao dịch, quy định kế toán hoặc hợp đồng. Ví dụ trên yêu cầu caller truyền scale và RoundingMode để quyết định được thể hiện rõ.

Trong hệ thống lớn, có thể thay cặp tham số bằng một Value Object như MoneyRoundingPolicy để giữ tên và chính sách nghiệp vụ ổn định.

## 5. Quantity: phép toán chỉ hợp lệ khi cùng đơn vị

Quantity biểu diễn số lượng cùng đơn vị đo. 5 kg và 5 lít không phải cùng một loại đại lượng. Ngay cả 1 kg và 1000 g cũng chỉ cộng được sau khi quy đổi về một đơn vị chung.

Ví dụ mô hình đơn giản:

~~~java
import java.util.Objects;

public record UnitOfMeasure(String code, String dimension) {
    public UnitOfMeasure {
        Objects.requireNonNull(code, "code");
        Objects.requireNonNull(dimension, "dimension");
        code = code.trim();
        dimension = dimension.trim();

        if (code.isEmpty() || dimension.isEmpty()) {
            throw new IllegalArgumentException("Unit metadata is required");
        }
    }
}
~~~

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record Quantity(BigDecimal value, UnitOfMeasure unit) {

    public Quantity {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(unit, "unit");
        value = value.stripTrailingZeros();

        if (value.signum() < 0) {
            throw new IllegalArgumentException("Quantity cannot be negative");
        }
    }

    public Quantity plus(Quantity other) {
        requireSameUnit(other);
        return new Quantity(value.add(other.value), unit);
    }

    public Quantity minus(Quantity other) {
        requireSameUnit(other);
        BigDecimal result = value.subtract(other.value);

        if (result.signum() < 0) {
            throw new IllegalArgumentException("Quantity cannot be negative");
        }

        return new Quantity(result, unit);
    }

    public Quantity times(BigDecimal factor) {
        Objects.requireNonNull(factor, "factor");

        if (factor.signum() < 0) {
            throw new IllegalArgumentException("Factor cannot be negative");
        }

        return new Quantity(value.multiply(factor), unit);
    }

    private void requireSameUnit(Quantity other) {
        Objects.requireNonNull(other, "other");
        if (!unit.equals(other.unit)) {
            throw new IllegalArgumentException(
                    "Quantities must use the same unit"
            );
        }
    }
}
~~~

Quantity ở đây cho phép giá trị bằng 0 nhưng không cho phép âm. Vì vậy, minus chỉ hợp lệ khi kết quả không âm. Phép trừ không phải là một phép toán toàn phần trên mọi cặp Quantity; nó được định nghĩa trên những cặp mà số lượng còn lại hợp lệ.

Nếu nghiệp vụ cần biểu diễn lượng tăng/giảm có dấu, có thể tạo QuantityDelta riêng. Đừng làm yếu invariant của Quantity chỉ để một phép toán luôn trả về cùng kiểu.

### Quy đổi đơn vị không phải cộng trực tiếp

Có thể quy đổi 1000 g thành 1 kg, nhưng quy đổi cần biết dimension và hệ số. Với đơn vị đo có thể thay đổi theo sản phẩm hoặc quy tắc, nên dùng UnitConversionPolicy hoặc domain service sở hữu danh mục quy đổi.

Sau khi quy đổi về cùng UnitOfMeasure, plus mới được thực hiện. Không nên tự động chuyển đổi bên trong plus nếu điều đó che giấu quyết định đơn vị hoặc rounding.

## 6. Không phải mọi phép toán trên Value Object đều khép kín

Tính khép kín là công cụ thiết kế, không phải luật buộc mọi phương thức phải trả về cùng kiểu.

### DateRange intersection có thể không có kết quả

Hai khoảng ngày có thể giao nhau hoặc rời nhau. Nếu không giao nhau, không tồn tại DateRange hợp lệ để trả về.

~~~java
import java.time.LocalDate;
import java.util.Optional;

public record DateRange(
        LocalDate startInclusive,
        LocalDate endExclusive
) {
    public DateRange {
        if (startInclusive == null || endExclusive == null
                || !startInclusive.isBefore(endExclusive)) {
            throw new IllegalArgumentException("Invalid date range");
        }
    }

    public Optional<DateRange> intersection(DateRange other) {
        LocalDate start = startInclusive.isAfter(other.startInclusive)
                ? startInclusive : other.startInclusive;

        LocalDate end = endExclusive.isBefore(other.endExclusive)
                ? endExclusive : other.endExclusive;

        if (!start.isBefore(end)) {
            return Optional.empty();
        }

        return Optional.of(new DateRange(start, end));
    }
}
~~~

Khi hai khoảng không giao nhau, Optional.empty() là kết quả đúng. Không nên trả một DateRange rỗng nếu invariant của DateRange yêu cầu start trước end.

### Union có thể trả về nhiều khoảng

Hợp của hai khoảng rời nhau không phải một DateRange duy nhất. Chữ ký phù hợp có thể là:

~~~java
List<DateRange> union(DateRange other);
~~~

Nếu hai khoảng chồng lấn hoặc liền kề, kết quả có thể gộp thành một khoảng. Nếu rời nhau, kết quả gồm hai khoảng. Kiểu trả về thể hiện đúng khả năng của nghiệp vụ.

### Phép toán có thể trả về Value Object khác

Phép chia hai khoản tiền cùng currency có thể tạo ra một tỷ lệ không có đơn vị tiền. Nếu kết quả biểu diễn chi phí trên mỗi đơn vị, nó có thể là UnitPrice; nếu là tỷ lệ giữa hai tổng tiền, nó có thể là Ratio. Hãy chọn kiểu kết quả theo ngữ nghĩa, thay vì trả Money chỉ vì đầu vào đều là Money.

## 7. Phân biệt closure với các tính chất đại số khác

Closure thường đi cùng các khái niệm đại số, nhưng chúng không đồng nghĩa.

| Tính chất | Ý nghĩa | Ví dụ có thể áp dụng |
|---|---|---|
| Closure | Kết quả vẫn thuộc cùng kiểu/tập giá trị hợp lệ | Money + Money → Money cùng currency |
| Commutativity | Đổi thứ tự toán hạng không đổi kết quả | a + b = b + a |
| Associativity | Cách nhóm toán hạng không đổi kết quả | (a + b) + c = a + (b + c) |
| Identity | Có phần tử trung tính | Money.zero(USD) |
| Inverse | Có phần tử đảo | Money.negate() nếu Money cho phép âm |

Không nên mặc định một phép toán có mọi tính chất chỉ vì nó trả về cùng kiểu.

Ví dụ Money cộng BigDecimal chính xác và cùng currency có thể có tính giao hoán, kết hợp và phần tử không. Nhưng nếu mỗi lần cộng đều làm tròn về hai chữ số, kết quả có thể phụ thuộc thứ tự nhóm. Nếu Money không cho phép âm, phép đối negate có thể không hợp lệ. Những tính chất cần được xác định theo domain và precision policy.

## 8. Giữ Value Object immutable khi thực hiện phép toán

Một phép toán khép kín nên trả về object mới. Không thay đổi field của object hiện tại:

~~~java
// Tránh: object có thể bị thay đổi từ nhiều nơi.
money.setAmount(money.amount().add(other.amount()));

// Nên: tạo giá trị mới.
Money updated = money.plus(other);
~~~

Lợi ích:

- Giá trị đã được kiểm tra không bị thay đổi âm thầm.
- Equality và hash code ổn định khi dùng trong Set hoặc Map.
- Dễ chia sẻ object giữa các thread.
- Test có thể kiểm tra input không đổi sau operation.
- Caller có thể giữ lại giá trị trước đó để so sánh hoặc ghi nhận lịch sử.

Record giúp tạo object immutable ở mức field, nhưng cần nhớ tính bất biến là nông (shallow). Nếu một record chứa List mutable, phải sao chép phòng vệ bằng List.copyOf. Với Money, BigDecimal và Currency là các kiểu bất biến nên không có vấn đề đó.

## 9. Đặt phép toán ở đúng nơi trong mô hình miền

### Phép toán thuần giá trị thuộc Value Object

Nếu operation chỉ cần dữ liệu nằm trong Value Object và quy tắc luôn đúng cho khái niệm đó, đặt nó trong Value Object.

Ví dụ:

- Money.plus, Money.minus.
- Quantity.plus khi cùng unit.
- DateRange.contains(date).
- Percentage.applyTo(amount) nếu rounding policy đã được xác định.

### Phép toán cần chính sách hoặc dữ liệu bên ngoài có thể cần Domain Service

Ví dụ chuyển đổi tiền cần tỷ giá được chọn theo ngày, nguồn tỷ giá, loại khách hàng và chính sách làm tròn. Nếu Value Object phải tự gọi repository hoặc API để tìm tỷ giá, nó sẽ phụ thuộc hạ tầng.

Có thể tách:

~~~text
Application Service
       |
       v
ExchangeMoneyService
       |
       +----> ExchangeRateRepository
       |
       +----> Money.convert(rate, policy)
~~~

Domain Service lấy đúng ExchangeRate và policy. Phép tính thuần trên Money vẫn nằm trong Money hoặc một calculator thuần nếu cần.

### Phép toán liên quan vòng đời Aggregate thuộc hành vi Aggregate

Một phép tính có thể ảnh hưởng đến invariant của Order, chẳng hạn giảm số lượng dòng hàng không được làm đơn đã đặt trở thành rỗng. Dù Quantity có phép trừ khép kín, quyết định cập nhật dòng hàng vẫn thuộc Order Root.

~~~java
public void reduceLineQuantity(
        OrderLineId lineId,
        Quantity reduction
) {
    requireDraft();

    OrderLine line = findLine(lineId);
    Quantity remaining = line.quantity().minus(reduction);

    if (remaining.isZero()) {
        lines.remove(line);
    } else {
        line.changeQuantity(remaining);
    }
}
~~~

Đoạn code minh họa trách nhiệm: Quantity kiểm tra phép trừ; Order kiểm tra trạng thái và quyết định xóa dòng hay cập nhật dòng. Value Object không thay thế Aggregate Root.

## 10. API Value Object dễ tiến hóa

Một Value Object thường trở thành API được nhiều phần của domain sử dụng. Vì vậy, tên phương thức, kiểu trả về và invariant cần được thiết kế có chủ đích.

### Dùng tên theo ngôn ngữ nghiệp vụ

Các tên plus, minus, increaseBy, reduceBy, contains, overlaps hoặc convertTo thường dễ hiểu hơn một hàm generic calculate.

Nếu hai phép toán có chính sách khác nhau, tên nên làm rõ:

- applyDiscount có thể khác subtract.
- roundForInvoice có thể khác roundForDisplay.
- extendByBusinessDays khác plusDays.
- convertAt khác changeCurrency.

### Không trả primitive nếu kết quả vẫn là một khái niệm miền

Nếu phép toán tạo ra một Money, trả Money. Nếu tạo ra một Percentage hoặc Ratio, trả kiểu tương ứng. Trả BigDecimal khiến caller phải tự diễn giải lại ý nghĩa.

Tuy nhiên, primitive có thể phù hợp ở ranh giới persistence, serialization hoặc thư viện tính toán. Hãy chuyển đổi tại adapter và giữ domain API có ngữ nghĩa.

### Thay đổi invariant là thay đổi hợp đồng

Giả sử Quantity trước đây cho phép 0, sau đó constructor đổi sang yêu cầu lớn hơn 0. Các caller đang dùng minus để đưa số lượng về 0 có thể bị lỗi. Đây là breaking change về hành vi dù chữ ký Java không đổi.

Khi thay đổi invariant:

1. Tìm các use case đang phụ thuộc vào giá trị cũ.
2. Xác định kiểu mới hoặc operation mới nếu semantics khác.
3. Có thể giữ API cũ trong giai đoạn chuyển tiếp nếu an toàn.
4. Thêm test cho quy tắc mới và các biên.
5. Cập nhật mapper, persistence và contract ở các ranh giới liên quan.

Nếu hai khái niệm có invariant khác nhau, tách thành hai Value Object thường tốt hơn việc thêm nhiều cờ tùy chọn vào một class.

## 11. Kiểm thử closure và invariant

Kiểm thử nên xác nhận cả kiểu kết quả, giá trị, điều kiện đầu vào và tính bất biến.

### Unit test cho Money

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Currency;
import org.junit.jupiter.api.Test;

class MoneyTest {
    private final Currency usd = Currency.getInstance("USD");

    @Test
    void plusReturnsMoneyWithSameCurrency() {
        Money first = Money.of("10.00", usd);
        Money second = Money.of("2.50", usd);

        Money result = first.plus(second);

        assertEquals(Money.of("12.5", usd), result);
        assertEquals(Money.of("10", usd), first);
        assertEquals(Money.of("2.5", usd), second);
    }

    @Test
    void minusRejectsDifferentCurrency() {
        Money dollars = Money.of("10", usd);
        Money euros = Money.of(
                "5", Currency.getInstance("EUR"));

        assertThrows(
                IllegalArgumentException.class,
                () -> dollars.minus(euros)
        );
    }

    @Test
    void zeroIsIdentityForAddition() {
        Money amount = Money.of("19.99", usd);

        assertEquals(amount, amount.plus(Money.zero(usd)));
    }

    @Test
    void negationProducesAdditiveInverse() {
        Money amount = Money.of("19.99", usd);

        assertTrue(amount.plus(amount.negate()).isZero());
    }
}
~~~

Các test xác nhận:

- Kết quả vẫn là Money.
- Currency không thay đổi.
- Input không bị mutate.
- Currency mismatch bị từ chối.
- Zero là phần tử trung tính.
- Negation tạo phần tử đối trong mô hình cho phép số âm.

### Kiểm thử theo tính chất

Ngoài các ví dụ cố định, có thể tạo nhiều đầu vào để kiểm tra các tính chất:

- a.plus(b) luôn có currency bằng currency của a khi currency hai bên giống nhau.
- a.plus(b) có cùng giá trị với b.plus(a) nếu phép cộng không làm tròn.
- a.plus(Money.zero(currency)) bằng a.
- a.minus(a) bằng zero cùng currency.
- Phép toán không làm thay đổi a hoặc b.
- Mọi kết quả đều qua constructor và giữ invariant.

Property-based testing với thư viện như jqwik có thể tạo nhiều BigDecimal và currency để tìm các trường hợp biên. Nếu không có thư viện, có thể viết vòng lặp test với tập dữ liệu được sinh có kiểm soát.

### Kiểm thử các trường hợp không khép kín

Với DateRange, test cả:

- Hai khoảng giao nhau tạo Optional chứa DateRange hợp lệ.
- Hai khoảng rời nhau tạo Optional.empty.
- Hai khoảng chỉ chạm biên theo quy ước nửa mở không có phần giao.
- Constructor từ chối start bằng hoặc sau end.

Đừng chỉ kiểm thử trường hợp thành công. Trường hợp không tồn tại kết quả là một phần của semantics.

## 12. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Đưa mọi phép tính ra ngoài Value Object | Quy tắc bị lặp ở nhiều caller | Đặt phép toán thuần giá trị vào VO sở hữu dữ liệu |
| Chỉ nhìn kiểu trả về để kết luận closure | Có thể bỏ qua invariant hoặc semantics | Kiểm tra cả miền đầu vào và kết quả |
| Mutate Value Object hiện tại | Caller khác có thể quan sát thay đổi ngoài ý muốn | Trả về instance mới |
| Cộng Money khác currency | Kết quả không có ý nghĩa | Yêu cầu cùng currency hoặc chuyển đổi rõ ràng |
| Tự chọn rounding trong phép nhân/chia | Kết quả phụ thuộc implementation, khó giải thích | Truyền policy hoặc rounding context |
| Ép mọi phép toán trả cùng kiểu | Mất thông tin khi kết quả có thể rỗng hoặc nhiều phần | Dùng Optional, collection hoặc kiểu kết quả miền |
| Cho Quantity âm chỉ để phép trừ luôn thành công | Làm yếu invariant của số lượng | Tách Quantity và QuantityDelta nếu semantics khác |
| Dùng primitive cho kết quả miền | Caller phải tự gắn lại ý nghĩa và kiểm tra | Trả Value Object phù hợp |
| Đưa repository hoặc HTTP vào Value Object | VO phụ thuộc hạ tầng và khó kiểm thử | Dùng Domain Service/Application Service |
| Nhầm phép toán VO với hành vi Aggregate | Bỏ qua trạng thái và invariant của root | Root điều phối thay đổi thuộc aggregate |
| Giả định closure đồng nghĩa associative/commutative | Có thể sai khi có rounding hoặc quy tắc nghiệp vụ | Xác định và test từng tính chất |
| Tạo quá nhiều wrapper không có ngữ nghĩa | Mô hình rườm rà, khó dùng | Chỉ tạo VO khi có identity-by-value, invariant hoặc hành vi rõ |

## 13. Quy trình thiết kế một phép toán trên Value Object

Khi cần thêm operation, hãy thực hiện:

1. **Đặt tên khái niệm:** Value Object biểu diễn điều gì và được chuyên gia gọi như thế nào?
2. **Viết invariant:** giá trị nào hợp lệ, đơn vị/currency/dimension nào phải khớp?
3. **Mô tả toán hạng:** operation nhận một hay nhiều giá trị; có cần policy hoặc context không?
4. **Xác định kiểu kết quả:** cùng VO, VO khác, Optional, collection hay kết quả đánh giá?
5. **Xác định failure mode:** từ chối, trả empty, trả lỗi miền hay cần kết quả có lý do?
6. **Giữ immutable:** tạo instance mới và không để lộ cấu trúc mutable.
7. **Kiểm tra tính chất:** closure, identity, inverse, associativity hoặc commutativity chỉ khi nghiệp vụ cần.
8. **Kiểm thử biên:** currency mismatch, unit mismatch, zero, âm, rounding, range rỗng và overflow.
9. **Đánh giá khả năng tiến hóa:** thay đổi invariant hoặc return type ảnh hưởng caller nào?
10. **Đặt đúng ranh giới:** phép tính thuần trong VO; chính sách bên ngoài trong domain service; trạng thái aggregate trong root.

## 14. Checklist rà soát

- [ ] Value Object biểu diễn một khái niệm có ý nghĩa và equality theo giá trị.
- [ ] Invariant được kiểm tra khi tạo object và sau mỗi operation.
- [ ] Operation trả cùng VO khi kết quả thực sự cùng khái niệm.
- [ ] Input không bị thay đổi; object kết quả là instance mới.
- [ ] Currency, unit, dimension hoặc precision được kiểm tra rõ.
- [ ] Rounding policy được thể hiện tường minh khi cần.
- [ ] Trường hợp không có kết quả dùng Optional hoặc kiểu kết quả phù hợp.
- [ ] Kết quả nhiều phần dùng collection/kiểu miền phù hợp, không ép vào một VO.
- [ ] Primitive không bị lộ khi kết quả vẫn mang ngữ nghĩa miền.
- [ ] Không gọi repository, HTTP hoặc clock toàn cục trong phép toán thuần.
- [ ] Aggregate Root vẫn bảo vệ invariant thuộc vòng đời của aggregate.
- [ ] Các tính chất đại số được xác định theo semantics, không giả định.
- [ ] Test bao gồm closure, invariant, immutability và trường hợp lỗi.
- [ ] Thay đổi invariant/return type được xem là thay đổi hợp đồng API.

## Kết luận

Phép toán khép kín giúp Value Object giữ dữ liệu và hành vi cùng một chỗ: nhận giá trị miền, kiểm tra điều kiện và trả về một giá trị mới cùng kiểu khi ngữ nghĩa cho phép. Money cộng cùng currency có thể trả Money; Quantity cộng cùng đơn vị có thể trả Quantity; nhưng DateRange intersection có thể không có kết quả và union có thể tạo nhiều khoảng. Thiết kế tốt không ép mọi phép toán thành khép kín. Nó chọn closure ở nơi invariant và semantics hỗ trợ, dùng kiểu kết quả khác khi cần, giữ object immutable và đặt chính sách có phụ thuộc bên ngoài vào đúng service. Nhờ vậy, Value Object trở thành một API miền ổn định, dễ kiểm thử và dễ tiến hóa.

