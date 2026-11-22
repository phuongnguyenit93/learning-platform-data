# Tiền tệ, số lượng, địa chỉ và khoảng giá trị trong mô hình nghiệp vụ

## Vì sao cần mô hình hóa giá trị có ý nghĩa?

Trong một hệ thống nghiệp vụ, nhiều thông tin trông giống các kiểu dữ liệu đơn giản nhưng thực chất mang theo quy tắc quan trọng. Một số tiền luôn gắn với đơn vị tiền tệ; một số lượng phải có đơn vị đo; một địa chỉ tuân theo cách biểu diễn của quốc gia và mục đích sử dụng; một khoảng giá trị phải xác định rõ giới hạn có được tính vào hay không. Nếu chỉ dùng `double`, `int` hoặc `String`, các quy tắc này dễ bị bỏ quên và mỗi nơi có thể xử lý một kiểu khác nhau.

Domain-Driven Design (DDD) sử dụng **Value Object (đối tượng giá trị)** để biểu diễn những khái niệm được xác định bằng các giá trị cấu thành và quy tắc của chúng. Value Object giúp đưa ý nghĩa nghiệp vụ vào mô hình: tiền tệ nào được phép cộng với nhau, số lượng nào hợp lệ, địa chỉ nào đủ thông tin cho một dịch vụ, hay một mức giá có nằm trong khoảng áp dụng hay không.

Bài học tập trung vào bốn nhóm giá trị thường gặp: **tiền tệ (Money), số lượng (Quantity), địa chỉ (Address) và khoảng giá trị (Range)**. Đây là những ví dụ cụ thể để luyện cách thiết kế value object có ý nghĩa, tính hợp lệ và hành vi rõ ràng trước khi quyết định cách lưu trữ.

Sau bài học, người học có thể:

- Giải thích vì sao một giá trị nghiệp vụ nên được biểu diễn bằng Value Object thay vì kiểu nguyên thủy.
- Thiết kế `Money` có tiền tệ, phép toán an toàn và chính sách làm tròn rõ ràng.
- Thiết kế `Quantity` gắn với đơn vị đo và ngăn phép toán giữa các đại lượng không tương thích.
- Mô hình hóa `Address` phù hợp với quốc gia, mục đích sử dụng và ngữ cảnh nghiệp vụ.
- Mô hình hóa khoảng số hoặc ngày với quy tắc biên bao gồm và không bao gồm.
- Kiểm tra tính bất biến, equality, validation và cách ánh xạ value object sang nơi lưu trữ.

## Đặc điểm chung của Value Object

Value Object không có danh tính độc lập trong mô hình. Hai giá trị được xem là tương đương khi những thành phần có ý nghĩa đối với nghiệp vụ của chúng tương đương. Chẳng hạn, `Money(100, VND)` khác `Money(100, USD)` vì tiền tệ là một phần bản chất của giá trị. Hai địa chỉ có cùng các thành phần theo quy tắc so sánh của miền có thể được xem là cùng giá trị, dù chúng được tạo ở hai thời điểm khác nhau.

Một value object được thiết kế tốt thường có các đặc điểm sau:

1. **Ý nghĩa rõ ràng:** tên kiểu cho biết giá trị đại diện cho điều gì, chẳng hạn `Money`, `Weight`, `PostalAddress` hoặc `DateRange`.
2. **Tính hợp lệ được bảo vệ:** constructor hoặc factory từ chối giá trị vi phạm quy tắc miền.
3. **Bất biến (immutable):** sau khi tạo, giá trị không bị thay đổi tại chỗ; thay đổi tạo ra một value object mới.
4. **So sánh theo giá trị:** `equals` và `hashCode` phản ánh những thành phần quyết định ý nghĩa của giá trị.
5. **Hành vi gần dữ liệu:** các phép tính và kiểm tra có ý nghĩa với giá trị được đặt trong chính value object khi phù hợp.
6. **Không phụ thuộc cách lưu trữ:** value object có thể được nhúng, lưu thành nhiều cột, serialize hoặc tính toán; hình thức lưu không quyết định bản chất miền.

Không phải cứ gom vài trường vào một class là đã có value object. Nhóm cần xác định ý nghĩa, điều kiện hợp lệ và quy tắc so sánh. Một `String` có thể đủ cho ghi chú tự do; nhưng nếu một mã bưu chính, địa chỉ email hoặc số tài khoản có quy tắc định dạng và hành vi riêng, một kiểu miền chuyên biệt có thể phù hợp hơn.

## Money: Tiền luôn đi cùng tiền tệ

### Vì sao không dùng số thực cho tiền?

Tiền là một đại lượng có đơn vị. `100` không đủ ý nghĩa nếu chưa biết đó là 100 đồng, 100 đô la Mỹ hay 100 euro. Vì vậy, `Money` cần ít nhất hai thành phần: số tiền và tiền tệ.

Không nên dùng `float` hoặc `double` để biểu diễn số tiền cần tính toán chính xác. Đây là các kiểu dấu phẩy động nhị phân; nhiều số thập phân không thể biểu diễn chính xác bằng dạng nhị phân. Sai số nhỏ có thể tích lũy qua phép cộng, nhân, chia hoặc làm tròn. Trong Java, `BigDecimal` thường phù hợp hơn cho phép tính tiền tệ, đi cùng một chính sách scale và rounding được xác định rõ.

### Các quy tắc nghiệp vụ của Money

Trước khi viết class `Money`, hãy xác nhận:

- Tiền tệ được xác định bằng mã nào và có nằm trong danh sách được hỗ trợ không?
- Có cho phép số tiền âm không? Khoản điều chỉnh, bút toán hoặc hoàn tiền có thể cần số âm; số tiền thanh toán đầu vào có thể phải dương.
- Phép cộng và so sánh có yêu cầu cùng tiền tệ không?
- Khi nhân với tỷ lệ hoặc chia, làm tròn ở bước nào và theo quy tắc nào?
- Có lưu số chữ số thập phân theo tiền tệ, theo sản phẩm hay theo quy định nghiệp vụ không?
- Khi đổi tiền, tỷ giá nào được dùng, có hiệu lực tại thời điểm nào và nguồn tỷ giá là ai?

Không có một quy tắc làm tròn đúng cho mọi nghiệp vụ. Một hệ thống có thể làm tròn từng dòng hàng, hệ thống khác chỉ làm tròn tổng hóa đơn; một nghiệp vụ tài chính có thể cần quy tắc riêng cho từng loại giao dịch. Chính sách phải được xác nhận với chuyên gia nghiệp vụ và quy định áp dụng.

### Ví dụ Money trong Java

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency)
        implements Comparable<Money> {

    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        // Chuẩn hóa scale để 10.0 và 10.00 có cùng biểu diễn giá trị.
        amount = amount.stripTrailingZeros();
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money subtract(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    public Money multiply(
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

    public boolean isNegative() {
        return amount.signum() < 0;
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
                    "Money values must use the same currency");
        }
    }
}
```

Đây là ví dụ value object tối giản. `record` tạo `equals` và `hashCode` dựa trên các thành phần; việc chuẩn hóa `BigDecimal` trong constructor giúp tránh khác biệt scale không mong muốn khi so sánh bằng `equals`. Phép `compareTo` kiểm tra tiền tệ trước, vì so sánh 100 USD với 100 VND không có ý nghĩa nếu chưa quy đổi.

Phương thức `multiply` yêu cầu bên gọi truyền scale và `RoundingMode` để chính sách làm tròn không bị ẩn. Trong hệ thống thực tế, nhóm thường đóng gói chính sách này vào một service hoặc value object chuyên biệt như `TaxAmount`, `UnitPrice` hay `SettlementAmount`, tùy quy tắc miền. Không nên tùy tiện dùng `Currency.getDefaultFractionDigits()` làm chính sách duy nhất nếu nghiệp vụ có quy tắc làm tròn riêng.

### Đổi tiền là một hành vi khác với cộng tiền

Không thể cộng trực tiếp `Money(100, USD)` với `Money(100, EUR)`. Muốn quy đổi, cần một tỷ giá có nguồn, thời điểm hiệu lực và chiều quy đổi rõ ràng. Có thể mô hình hóa tỷ giá như một value object:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record ExchangeRate(
        Currency baseCurrency,
        Currency counterCurrency,
        BigDecimal rate
) {
    public ExchangeRate {
        Objects.requireNonNull(baseCurrency, "baseCurrency");
        Objects.requireNonNull(counterCurrency, "counterCurrency");
        Objects.requireNonNull(rate, "rate");
        if (baseCurrency.equals(counterCurrency)) {
            throw new IllegalArgumentException("Currencies must differ");
        }
        if (rate.signum() <= 0) {
            throw new IllegalArgumentException("Rate must be positive");
        }
    }
}
```

Ví dụ chỉ thể hiện cặp tiền và tỷ giá. Một mô hình giao dịch thực tế thường cần thêm thời điểm áp dụng, nguồn tỷ giá, loại tỷ giá và chính sách làm tròn. Không nên tự lấy tỷ giá mới nhất khi đọc lại giao dịch cũ nếu nghiệp vụ yêu cầu giữ tỷ giá tại thời điểm phát sinh.

### Những lỗi thường gặp với Money

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ lưu số tiền dạng `double` | Sai số thập phân và thiếu đơn vị tiền | Dùng `BigDecimal` cùng tiền tệ |
| Cộng hai số tiền khác tiền tệ | Kết quả không có ý nghĩa | Kiểm tra cùng tiền tệ hoặc thực hiện quy đổi có tỷ giá rõ ràng |
| Làm tròn ở mọi bước mà không có chính sách | Sai lệch tổng tiền và khó đối soát | Xác định điểm và phương thức làm tròn theo nghiệp vụ |
| Coi mọi số tiền đều không âm | Không biểu diễn được điều chỉnh hoặc bút toán âm | Đặt quy tắc ở kiểu miền cụ thể như `PaymentAmount` hoặc `RefundAmount` |
| Dùng số tiền hiện tại để dựng lại giao dịch cũ | Mất giá trị đã cam kết tại thời điểm giao dịch | Lưu snapshot giá và tiền tệ theo chính sách |

## Quantity: Số lượng phải có đơn vị đo

### Con số không đủ để mô tả số lượng

`5` có thể là 5 chiếc, 5 kilogram, 5 lít hoặc 5 giờ. Nếu chỉ lưu một con số, hệ thống có thể cộng hoặc so sánh những đại lượng không cùng bản chất. Một `Quantity` cần gắn số lượng với đơn vị đo và quy tắc chuyển đổi phù hợp.

Đơn vị thường thuộc một **chiều đo (dimension)** như số đếm, khối lượng, thể tích, chiều dài hoặc thời gian. Chỉ các đơn vị cùng chiều đo mới có thể quy đổi hoặc cộng với nhau. 500 gram có thể đổi thành 0,5 kilogram; 500 gram không thể cộng với 0,5 lít.

### Các câu hỏi nghiệp vụ cần xác nhận

- Số lượng có được bằng 0 hoặc âm không? Số lượng đặt hàng thường phải lớn hơn 0, trong khi tồn kho hoặc chênh lệch kiểm kê có thể bằng 0 hay âm tùy cách mô hình.
- Có cho phép phần lẻ không? Sản phẩm bán theo chiếc có thể yêu cầu số nguyên; hàng cân có thể cho phép phần thập phân.
- Đơn vị nào được chấp nhận cho từng sản phẩm hoặc dịch vụ?
- Quy đổi đơn vị có chính xác tuyệt đối hay cần độ chính xác và làm tròn?
- Đơn vị cơ sở được chọn theo nghiệp vụ, theo kho hay theo nhà cung cấp?
- Một đơn vị đóng gói như thùng có chứa số chiếc cố định hay phụ thuộc lô hàng?

Không nên xây một kiểu `Quantity` dùng chung với mọi quy tắc nếu các khái niệm có chính sách khác nhau. `OrderQuantity`, `StockQuantity`, `Duration` hoặc `Weight` có thể là các value object riêng, dù cùng chứa một số và một đơn vị.

### Ví dụ Quantity với chiều đo và quy đổi

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.util.Objects;

enum Unit {
    PIECE("COUNT", "1"),
    GRAM("MASS", "0.001"),
    KILOGRAM("MASS", "1"),
    MILLILITER("VOLUME", "0.001"),
    LITER("VOLUME", "1");

    private final String dimension;
    private final BigDecimal factorToBase;

    Unit(String dimension, String factorToBase) {
        this.dimension = dimension;
        this.factorToBase = new BigDecimal(factorToBase);
    }

    String dimension() {
        return dimension;
    }

    BigDecimal factorToBase() {
        return factorToBase;
    }
}

public record Quantity(BigDecimal amount, Unit unit) {
    public Quantity {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(unit, "unit");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Quantity cannot be negative");
        }
    }

    public Quantity convertTo(Unit target) {
        Objects.requireNonNull(target, "target");
        if (!unit.dimension().equals(target.dimension())) {
            throw new IllegalArgumentException("Incompatible dimensions");
        }

        BigDecimal baseAmount = amount.multiply(unit.factorToBase());
        BigDecimal converted = baseAmount.divide(
                target.factorToBase(), MathContext.DECIMAL128);
        return new Quantity(converted, target);
    }

    public Quantity add(Quantity other) {
        Quantity converted = other.convertTo(unit);
        return new Quantity(amount.add(converted.amount), unit);
    }
}
```

Trong ví dụ, `GRAM` và `KILOGRAM` cùng chiều khối lượng; `MILLILITER` và `LITER` cùng chiều thể tích. `convertTo` chuyển qua đơn vị cơ sở của chiều đo, sau đó chuyển sang đơn vị đích. `MathContext.DECIMAL128` là lựa chọn độ chính xác minh họa; ứng dụng cần xác định độ chính xác, scale và cách làm tròn tại điểm nghiệp vụ phù hợp.

Constructor cho phép số lượng bằng 0 và từ chối số âm. Nếu số lượng đặt hàng bắt buộc lớn hơn 0, có thể tạo kiểu `OrderQuantity` riêng để áp dụng quy tắc đó. Nếu hệ thống cần biểu diễn điều chỉnh tồn kho âm, hãy dùng một khái niệm như `StockDelta` thay vì nới lỏng quy tắc của mọi loại quantity.

Ví dụ enum chỉ là tập đơn vị nhỏ. Hệ thống thực tế có thể cần đơn vị đóng gói, hệ đo khác nhau, hệ số chuyển đổi theo sản phẩm hoặc quy đổi không cố định. Chẳng hạn, một thùng có thể chứa 12 hoặc 24 sản phẩm tùy quy cách; hệ số đó thuộc thông tin quy cách đóng gói, không nên nhét vào hệ số chuyển đổi toàn cục của `Unit`.

### Những lỗi thường gặp với Quantity

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ lưu số lượng mà không lưu đơn vị | Không biết đại lượng đang đo gì | Gắn quantity với unit và dimension |
| Cộng khối lượng với thể tích | Kết quả vô nghĩa | Chỉ cho phép phép toán giữa các chiều đo tương thích |
| Mặc định mọi quantity phải là số nguyên | Không biểu diễn được cân nặng hoặc thể tích lẻ | Xác định độ chính xác theo loại hàng và quy trình |
| Dùng một kiểu quantity cho mọi nghiệp vụ | Quy tắc âm, zero và làm tròn bị trộn lẫn | Tạo kiểu miền cụ thể khi chính sách khác nhau |
| Quy đổi đơn vị đóng gói bằng hệ số cố định toàn cục | Sai khi quy cách phụ thuộc sản phẩm hoặc lô | Đưa quy cách vào mô hình sở hữu nó |

## Address: Địa chỉ phụ thuộc quốc gia và mục đích sử dụng

### Không có một cấu trúc địa chỉ đúng cho mọi nơi

Địa chỉ thường được biểu diễn bằng nhiều thành phần như dòng địa chỉ, phường/xã, quận/huyện, tỉnh/thành, mã bưu chính và quốc gia. Nhưng thứ tự, tên gọi và trường bắt buộc khác nhau giữa các quốc gia. Một số nơi dùng mã bưu chính làm thông tin định tuyến chính; nơi khác có thể không dùng mã bưu chính. Có địa chỉ cần tên tòa nhà, tầng, căn hộ hoặc chỉ dẫn giao hàng.

Vì vậy, `Address` nên phản ánh mục đích của bounded context. Địa chỉ giao hàng trong đơn hàng có thể là snapshot tại thời điểm đặt. Địa chỉ liên hệ của khách hàng có thể được cập nhật và xác minh trong CRM. Địa điểm giao nhận có thể có danh tính, tọa độ, lịch hoạt động và vòng đời riêng; khi đó nó có thể là entity thay vì value object.

### Các quyết định cần làm rõ

- Địa chỉ được dùng để giao hàng, xuất hóa đơn, liên hệ, xác minh hay định tuyến?
- Quốc gia nào được hỗ trợ và trường nào bắt buộc ở từng quốc gia?
- Có cho phép nhiều dòng địa chỉ không?
- Có cần lưu nguyên văn nội dung người dùng nhập để đối soát không?
- Có chuẩn hóa khoảng trắng, chữ hoa/thường, dấu câu hoặc viết tắt không?
- Việc chuẩn hóa có làm thay đổi cách viết chính thức hoặc khả năng giao hàng không?
- Địa chỉ có cần được xác minh bởi dịch vụ bên ngoài không? Kết quả xác minh có phải là một giá trị riêng?

Không nên tự động loại bỏ dấu, thay viết tắt hoặc chuẩn hóa tên địa danh nếu điều đó có thể làm sai địa chỉ thực tế. Chuẩn hóa nên được thực hiện theo quy tắc rõ ràng và giữ lại dữ liệu gốc khi cần.

### Ví dụ PostalAddress

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public record PostalAddress(
        List<String> lines,
        String locality,
        String region,
        String postalCode,
        String countryCode
) {
    public PostalAddress {
        Objects.requireNonNull(lines, "lines");
        lines = lines.stream()
                .map(PostalAddress::requireText)
                .toList();
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("At least one address line is required");
        }
        locality = optionalText(locality);
        region = optionalText(region);
        postalCode = optionalText(postalCode);
        countryCode = requireCountryCode(countryCode);
    }

    private static String requireText(String value) {
        Objects.requireNonNull(value, "address line");
        String normalized = value.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Address line cannot be blank");
        }
        return normalized;
    }

    private static String optionalText(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }

    private static String requireCountryCode(String value) {
        Objects.requireNonNull(value, "countryCode");
        String code = value.trim().toUpperCase(Locale.ROOT);
        if (!code.matches("[A-Z]{2}")) {
            throw new IllegalArgumentException("Expected a two-letter country code");
        }
        return code;
    }
}
```

Đây là ví dụ đơn giản dùng mã quốc gia hai chữ cái. Nó không cố áp đặt `locality`, `region` hoặc `postalCode` là bắt buộc, vì các trường này có thể tùy chọn theo quốc gia. Trong sản phẩm thực tế, nên có chính sách xác thực theo quốc gia và mục đích sử dụng thay vì xem constructor trên là bộ quy tắc toàn cầu.

`List.copyOf` hoặc `Stream.toList()` giúp danh sách dòng địa chỉ không bị sửa qua tham chiếu bên ngoài; trong ví dụ này `toList()` trả về danh sách không thể sửa. Việc cắt khoảng trắng đầu cuối là chuẩn hóa nhẹ. Equality của record vẫn dựa trên các trường đã chuẩn hóa đó; nếu nghiệp vụ muốn xem hai cách viết khác nhau là cùng địa chỉ, cần định nghĩa rõ thuật toán canonicalization hoặc một quy trình xác minh, không nên tự suy ra chỉ từ chuỗi gần giống nhau.

### Address có luôn là Value Object không?

Không. Trong đơn hàng, địa chỉ giao hàng thường là giá trị được chụp lại để giữ bằng chứng khách đã yêu cầu giao đến đâu tại thời điểm đặt. Thay địa chỉ tạo một giá trị mới trong đơn theo chính sách. Trong một hệ thống quản lý địa điểm, một địa điểm có thể có `LocationId`, trạng thái xác minh, lịch sử thay đổi và được nhiều quy trình tham chiếu; khái niệm đó có thể là entity. Hãy xác định theo ngữ cảnh và vòng đời.

## Range: Khoảng giá trị phải có quy tắc biên

### Khoảng không chỉ có hai con số

Một khoảng giá trị cần xác định ít nhất giới hạn dưới, giới hạn trên và việc mỗi giới hạn có được tính vào hay không. Khoảng từ 10 đến 20 có thể mang nghĩa `[10, 20]`, `[10, 20)`, `(10, 20]` hoặc `(10, 20)`. Các ký hiệu này lần lượt cho biết biên dưới và biên trên là bao gồm (`[`, `]`) hay không bao gồm (`(`, `)`).

Quy tắc biên có thể thay đổi kết quả nghiệp vụ. Nếu hai mức giá được chia thành `0 đến dưới 100` và `100 đến dưới 500`, giá trị đúng 100 chỉ thuộc khoảng thứ hai. Nếu cả hai khoảng đều bao gồm 100, một giá trị có thể khớp hai mức cùng lúc.

### Ví dụ Range tổng quát

```java
import java.util.Objects;

public record Range<T extends Comparable<? super T>>(
        T lower,
        boolean lowerInclusive,
        T upper,
        boolean upperInclusive
) {
    public Range {
        Objects.requireNonNull(lower, "lower");
        Objects.requireNonNull(upper, "upper");

        int order = lower.compareTo(upper);
        if (order > 0 || (order == 0 && !(lowerInclusive && upperInclusive))) {
            throw new IllegalArgumentException("Invalid range boundaries");
        }
    }

    public boolean contains(T value) {
        Objects.requireNonNull(value, "value");
        int lowerComparison = value.compareTo(lower);
        int upperComparison = value.compareTo(upper);

        boolean aboveLower = lowerInclusive
                ? lowerComparison >= 0
                : lowerComparison > 0;
        boolean belowUpper = upperInclusive
                ? upperComparison <= 0
                : upperComparison < 0;

        return aboveLower && belowUpper;
    }
}
```

`Range` yêu cầu kiểu `T` có thể so sánh và không cho phép biên null. Khoảng có hai biên bằng nhau chỉ hợp lệ khi cả hai biên đều bao gồm; khi đó khoảng chứa đúng một giá trị. Nếu nghiệp vụ cần khoảng mở không giới hạn hoặc khoảng rỗng, hãy mở rộng mô hình với quy tắc rõ ràng thay vì dùng `null` với ý nghĩa ngầm định.

Ví dụ sử dụng:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

Range<BigDecimal> discountBand = new Range<>(
        new BigDecimal("100"), true,
        new BigDecimal("500"), false
);

boolean appliesAt100 = discountBand.contains(new BigDecimal("100")); // true
boolean appliesAt500 = discountBand.contains(new BigDecimal("500")); // false

Range<LocalDate> bookingWindow = new Range<>(
        LocalDate.of(2026, 1, 1), true,
        LocalDate.of(2026, 2, 1), false
);
```

Với giá trị tiền, có thể dùng `Range<Money>` vì `Money` triển khai `Comparable` và kiểm tra tiền tệ khi so sánh. Hai biên và giá trị truy vấn phải cùng tiền tệ; nếu khác, phép so sánh sẽ bị từ chối. Nếu miền cần khoảng giá luôn cùng một loại tiền, một `MoneyRange` chuyên biệt có thể kiểm tra điều kiện đó ngay khi tạo.

### Khoảng ngày và thời gian

Với lịch đặt chỗ, khoảng nửa mở `[start, end)` thường hữu ích: ngày bắt đầu được tính, ngày kết thúc không được tính. Hai lượt đặt `09:00–10:00` và `10:00–11:00` có thể liền nhau mà không chồng lấn. Tuy nhiên, một chính sách thuê thiết bị có thể tính cả ngày trả; một hợp đồng có thể có ngày kết thúc bao gồm. Phải xác nhận quy tắc với nghiệp vụ.

Phân biệt `LocalDate`, `LocalDateTime` và `Instant` theo ý nghĩa:

- `LocalDate` biểu diễn ngày lịch, không có giờ hoặc múi giờ.
- `LocalDateTime` biểu diễn ngày giờ địa phương, chưa xác định một thời điểm duy nhất trên toàn cầu.
- `Instant` biểu diễn một thời điểm trên dòng thời gian toàn cầu.

Nếu khoảng thời gian liên quan đến đặt lịch tại một địa điểm, múi giờ và quy tắc giờ mùa hè có thể ảnh hưởng đến cách diễn giải. Không nên chọn kiểu thời gian chỉ dựa trên định dạng hiển thị.

### Khoảng giá trị trong chính sách

Range có thể được dùng để mô hình hóa:

- Ngưỡng chiết khấu theo tổng giá trị đơn hàng.
- Khoảng tuổi đủ điều kiện tham gia chương trình.
- Khoảng ngày hiệu lực của hợp đồng hoặc chính sách.
- Giới hạn trọng lượng hoặc kích thước kiện hàng.
- Ngưỡng cảnh báo tồn kho.

Một tập các range trong chính sách thường cần thêm quy tắc không chồng lấn, không bỏ sót giá trị, thứ tự ưu tiên hoặc khoảng vô hạn. `Range.contains()` chỉ trả lời một giá trị có nằm trong một khoảng hay không; nó chưa bảo đảm toàn bộ tập khoảng là nhất quán. Việc kiểm tra các khoảng trong một tập nên thuộc về value object hoặc aggregate quản lý chính sách đó.

## Kết hợp các Value Object trong một mô hình nghiệp vụ

Các value object thường phối hợp để biểu diễn một quy tắc hoàn chỉnh. Ví dụ, một dòng hàng có số lượng, đơn giá và tổng tiền. Nếu số lượng có đơn vị đo và đơn giá là tiền cho một đơn vị, phép nhân cần bảo đảm đơn vị tương thích và chính sách làm tròn được áp dụng đúng.

```java
public record OrderLineValue(
        Quantity quantity,
        Money unitPrice,
        Money lineTotal
) {
    public OrderLineValue(Quantity quantity, Money unitPrice, int scale) {
        this(
                quantity,
                unitPrice,
                unitPrice.multiply(quantity.amount(), scale,
                        java.math.RoundingMode.HALF_UP)
        );
    }

    public OrderLineValue(Quantity quantity, Money unitPrice, Money lineTotal) {
        this.quantity = java.util.Objects.requireNonNull(quantity);
        this.unitPrice = java.util.Objects.requireNonNull(unitPrice);
        this.lineTotal = java.util.Objects.requireNonNull(lineTotal);
        if (lineTotal.isNegative()) {
            throw new IllegalArgumentException("Line total cannot be negative");
        }
    }
}
```

Đoạn mã trên chỉ minh họa việc kết hợp các value object; nó giả định `quantity.amount()` là số lượng có thể nhân trực tiếp với đơn giá và không xét chuyển đổi đơn vị. Một mô hình thực tế cần xác định đơn giá là tiền trên đơn vị nào, ví dụ VND/kg hoặc USD/chiếc, và xác định chính sách làm tròn cho dòng hàng. Không phải mọi `Quantity` đều có thể nhân với mọi `Money` một cách hợp lệ.

Một cách diễn đạt rõ hơn trong miền có thể là `UnitPrice` chứa tiền trên một đơn vị đo cụ thể, hoặc một hành vi trên `OrderLine` biết cách tính tổng tiền theo chính sách. Tên kiểu miền nên làm rõ đơn vị và ý nghĩa thay vì để người đọc suy đoán từ phép nhân hai con số.

## Chọn nơi đặt quy tắc và nơi lưu trữ

### Quy tắc thuộc về Value Object

Đưa vào value object những quy tắc trực tiếp xác định tính hợp lệ hoặc phép toán của chính giá trị đó:

- `Money` kiểm tra tiền tệ, phép cộng cùng tiền tệ và phép so sánh.
- `Quantity` kiểm tra đơn vị tương thích và quy đổi trong cùng chiều đo.
- `PostalAddress` kiểm tra cấu trúc tối thiểu và chuẩn hóa an toàn theo chính sách.
- `Range` kiểm tra thứ tự biên và xác định một giá trị có thuộc khoảng hay không.

### Quy tắc thuộc về Entity hoặc Aggregate

Những quy tắc phụ thuộc trạng thái và quan hệ của nhiều khái niệm nên nằm ở entity hoặc aggregate có trách nhiệm:

- Đơn hàng có được xác nhận hay không phụ thuộc trạng thái đơn và các dòng hàng.
- Mức chiết khấu nào được áp dụng có thể phụ thuộc hạng khách hàng, thời điểm, sản phẩm và chính sách khuyến mãi.
- Một địa chỉ có được dùng cho giao hàng hay không có thể phụ thuộc vùng phục vụ và dịch vụ vận chuyển.
- Một khoảng giá có được thêm vào bảng giá hay không có thể phụ thuộc các khoảng hiện có và quy tắc không chồng lấn.

Không đưa mọi chính sách vào constructor của value object. Value object nên tự bảo vệ tính hợp lệ nội tại; quyết định phụ thuộc dữ liệu hoặc trạng thái bên ngoài cần được thực hiện bởi thành phần sở hữu quy tắc đó.

### Ánh xạ Value Object sang lưu trữ

Value Object không bắt buộc tương ứng một bảng riêng. Tùy cơ sở dữ liệu và nhu cầu truy vấn, có thể:

- Lưu `Money` bằng hai cột số tiền và mã tiền tệ trong bảng của entity sở hữu.
- Lưu `Address` bằng các cột nhúng hoặc một cấu trúc JSON nếu phù hợp với nhu cầu truy vấn và kiểm soát schema.
- Lưu `Quantity` bằng số lượng và mã đơn vị; bảo đảm mã đơn vị và quy tắc quy đổi được quản lý nhất quán.
- Lưu `Range` bằng các cột biên và cờ inclusive/exclusive, hoặc biểu diễn bằng cấu trúc phù hợp với kho dữ liệu.

Khi lưu snapshot, hãy xác định dữ liệu nào cần giữ để tái hiện quyết định tại thời điểm giao dịch. Ví dụ, đơn hàng có thể cần giữ địa chỉ giao hàng và đơn giá đã chốt ngay cả khi hồ sơ khách hàng hoặc catalog thay đổi sau đó.

Không nên để annotation ORM, cấu trúc bảng hoặc JSON quyết định ngược lại ý nghĩa của value object. Domain model nên thể hiện quy tắc; lớp persistence mapper chịu trách nhiệm chuyển đổi sang cấu trúc lưu trữ.

## Những sai lầm thường gặp khi thiết kế Value Object

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Dùng kiểu nguyên thủy cho mọi giá trị | Mất đơn vị, ngữ nghĩa và quy tắc | Tạo value object có tên miền rõ ràng |
| Dùng `double` cho tiền | Sai số biểu diễn và làm tròn khó kiểm soát | Dùng `BigDecimal` với chính sách rõ ràng |
| Cho phép cộng tiền khác tiền tệ | Kết quả không có ý nghĩa | Yêu cầu cùng tiền tệ hoặc quy đổi bằng tỷ giá xác định |
| Dùng một `Quantity` không có dimension | Có thể cộng những đại lượng khác nhau | Gắn đơn vị và chiều đo |
| Coi địa chỉ có cùng cấu trúc ở mọi quốc gia | Từ chối địa chỉ hợp lệ hoặc làm mất thông tin | Xác thực theo quốc gia và mục đích sử dụng |
| Chuẩn hóa địa chỉ quá mạnh | Có thể đổi tên chính thức hoặc làm sai chỉ dẫn giao hàng | Chỉ chuẩn hóa theo chính sách được xác nhận và giữ dữ liệu gốc khi cần |
| Không quy định biên của Range | Giá trị biên bị áp dụng hai lần hoặc không được áp dụng | Chọn inclusive/exclusive và kiểm tra toàn bộ tập khoảng |
| Cho value object phụ thuộc vào cơ sở dữ liệu | Khó tái sử dụng và kiểm thử quy tắc miền | Giữ domain model độc lập với persistence |
| Đưa chính sách toàn hệ thống vào một value object | Giá trị trở nên phụ thuộc vào nhiều trạng thái bên ngoài | Đặt quy tắc ở aggregate hoặc domain service phù hợp |

## Checklist rà soát Value Object

Trước khi dùng một value object trong mô hình, hãy kiểm tra:

- [ ] Tên kiểu diễn đạt rõ ý nghĩa nghiệp vụ.
- [ ] Các thành phần cấu thành giá trị đã được xác định đầy đủ.
- [ ] Constructor hoặc factory từ chối trạng thái không hợp lệ.
- [ ] Equality và hash code dựa trên những giá trị có ý nghĩa.
- [ ] Đối tượng bất biến hoặc có cơ chế bảo vệ thay đổi rõ ràng.
- [ ] Các phép toán kiểm tra đơn vị, tiền tệ và điều kiện tương thích.
- [ ] Chính sách làm tròn và độ chính xác được xác định tại đúng ranh giới.
- [ ] Các biên của khoảng được mô tả rõ là bao gồm hay không bao gồm.
- [ ] Quy tắc phụ thuộc vào trạng thái bên ngoài nằm ở entity, aggregate hoặc domain service thích hợp.
- [ ] Mô hình không bị chi phối bởi cách ORM hoặc cơ sở dữ liệu lưu dữ liệu.
- [ ] Có ví dụ và trường hợp biên để kiểm chứng với chuyên gia nghiệp vụ.

## Kết luận

Money, Quantity, Address và Range cho thấy Value Object có thể bảo vệ những quy tắc rất cụ thể của miền nghiệp vụ. Tiền cần tiền tệ và chính sách tính toán; số lượng cần đơn vị và chiều đo; địa chỉ cần cấu trúc phù hợp với quốc gia và mục đích; khoảng giá trị cần quy tắc biên rõ ràng. Khi các quy tắc này được đặt trong những kiểu miền bất biến, có equality và hành vi phù hợp, mô hình trở nên dễ hiểu và đáng tin cậy hơn. Sau đó, nhóm có thể ánh xạ các giá trị sang cơ sở dữ liệu theo nhu cầu mà không làm mất ý nghĩa nghiệp vụ.
