# Biểu diễn tiền tệ, đơn vị đo và các giá trị có ngữ nghĩa

> **Chương:** Biểu diễn dữ liệu  
> **Module:** DATA_PERSISTENCE_FUNDAMENTALS  
> **Phạm vi:** Thiết kế cách biểu diễn, xác thực, tính toán và lưu bền vững các giá trị mang ngữ nghĩa nghiệp vụ trong ứng dụng Java; từ số tiền, tiền tệ, đại lượng đo đến schema, truy vấn, giao dịch, bảo mật, phục hồi và tiến hóa dữ liệu.

## 1. Vấn đề: cùng một con số nhưng ý nghĩa khác nhau

Trong cơ sở dữ liệu, hai giá trị dưới đây đều có thể được lưu bằng kiểu số:

~~~text
amount = 100
quantity = 100
~~~

Nhưng chúng **chưa đủ thông tin để diễn giải**:

- `amount = 100` là 100 VND, 100 USD hay 100 xu?
- `quantity = 100` là 100 gram, 100 kilogram, 100 mét hay 100 sản phẩm?
- Đơn giá là **50.000 VND/kg** hay **50.000 VND/món**?
- `rate = 5` nghĩa là 5%, 5 lần hay tỉ giá 5 đơn vị tiền tệ đích trên một đơn vị tiền tệ nguồn?
- `temperature = 25` là 25°C hay 25°F?

Nếu lưu một con số rồi để mỗi API, batch job hoặc báo cáo tự suy đoán đơn vị, dữ liệu có thể được **ghi thành công nhưng mang ý nghĩa sai**. Một phép cộng `10 USD + 10 VND` hoặc `2 kg + 3 m` là phép toán không hợp lệ về ngữ nghĩa, dù kiểu số cho phép thực hiện.

Mục tiêu của bài học:

1. Phân biệt **giá trị số**, **đơn vị**, **đại lượng**, **ngữ cảnh** và **quy tắc làm tròn**.
2. Thiết kế biểu diễn an toàn cho **Money**, tỷ giá, phần trăm, số lượng và đơn vị đo.
3. Dùng `BigDecimal` và value object trong Java để bảo vệ các phép toán.
4. Thiết kế hợp đồng JSON và schema database giữ đủ ngữ nghĩa, hỗ trợ ràng buộc, truy vấn và chỉ mục.
5. Nhận diện ảnh hưởng đến giao dịch, kiểm soát đồng thời, migration, audit và khôi phục dữ liệu.

## 2. Giá trị có ngữ nghĩa là gì?

Một **giá trị có ngữ nghĩa** (*semantic value*) không chỉ là dữ liệu nguyên thủy như `int`, `double` hoặc `String`. Nó mang theo các quy tắc xác định **giá trị đó đo hoặc biểu thị điều gì**, **phép toán nào hợp lệ**, **giới hạn ra sao** và **cần thông tin nào để tái diễn giải về sau**.

Có thể hình dung:

~~~text
Giá trị có ngữ nghĩa =
    trị số
    + đơn vị hoặc mã phân loại
    + bối cảnh/quy tắc diễn giải khi cần
~~~

Ví dụ:

| Dữ liệu thô | Biểu diễn có ngữ nghĩa | Điều được làm rõ |
| --- | --- | --- |
| `100` | `Money(100, "USD")` | 100 đô la Mỹ |
| `2500` | `Quantity(2500, "g")` | Khối lượng 2.500 gram |
| `25` | `Temperature(25, "°C")` | Nhiệt độ theo thang Celsius |
| `0.15` | `TaxRate(0.15)` | Tỷ lệ thuế 15% theo quy ước nội bộ |
| `1.07` | `ExchangeRate(EUR → USD, 1.07, at=...)` | Tỷ giá có hướng và mốc hiệu lực |
| `3600` | `Duration(3600, "s")` | Thời lượng 3.600 giây |

Một số giá trị còn có **ngữ nghĩa về thời điểm** (giá tại thời điểm mua), **nguồn dữ liệu** (tỷ giá do nhà cung cấp nào báo), **mức tin cậy** (giá trị đo hay ước lượng) hoặc **trạng thái** (đã xác nhận/chưa xác nhận).

Không nhất thiết tạo một lớp Java riêng cho mọi số. Nhưng khi một giá trị ảnh hưởng tới **tiền, tồn kho, quyền lợi hoặc báo cáo**, việc mô hình hóa rõ ràng thường rẻ hơn rất nhiều so với sửa dữ liệu sai đã được lưu bền vững.

## 3. Biểu diễn tiền tệ: số tiền luôn gắn với loại tiền

**Money** gồm ít nhất hai thành phần:

~~~text
Money = (amount, currency)

Ví dụ:
  amount   = 1250.75
  currency = USD
~~~

`amount` là trị số. `currency` chỉ loại tiền; mã ba chữ cái theo ISO 4217 như `USD`, `VND`, `JPY` thường phù hợp để trao đổi giữa hệ thống.

### 3.1. Mã tiền tệ không phải ký hiệu hiển thị

Ký hiệu `$` có thể được dùng cho nhiều loại tiền tệ khác nhau. Dữ liệu chỉ chứa `"$100"` không đủ để xác định 100 USD hay 100 loại đô la khác. Ngược lại, `USD` là mã phân biệt rõ hơn trong một hợp đồng dữ liệu.

| Thành phần | Dùng để làm gì? | Ví dụ |
| --- | --- | --- |
| Mã tiền tệ | Định danh ổn định trong dữ liệu và API | `USD`, `VND`, `JPY` |
| Trị số | Giá trị tiền theo đơn vị chính hoặc đơn vị nhỏ đã thống nhất | `123.45` |
| Đơn vị nhỏ (*minor unit*) | Cách biểu diễn phân số tiền theo thông lệ tiền tệ | 100 cent = 1 USD |
| Locale hiển thị | Quy tắc định dạng số, dấu phân cách, vị trí ký hiệu | `vi-VN`, `en-US` |

**Mã tiền tệ và locale độc lập nhau.** Một tài khoản ở Việt Nam vẫn có thể có số dư USD; locale `vi-VN` không tự quyết định loại tiền cần lưu.

### 3.2. Không có một số chữ số thập phân cố định cho mọi tiền tệ

Một số loại tiền có hai chữ số thập phân thông dụng (ví dụ USD), một số thường không có chữ số thập phân (ví dụ JPY, VND theo đơn vị nhỏ được chuẩn hóa trong ISO 4217). Những loại tiền khác có thể có số chữ số thập phân khác.

Vì vậy, không nên mặc định “mọi tiền đều có 2 chữ số thập phân” hoặc luôn nhân số tiền với 100. Với tiền tệ lịch sử, quy tắc minor unit còn có thể thay đổi theo thời gian hoặc nghiệp vụ có **đơn vị tính toán nội bộ** khác đơn vị thanh toán.

**Quy tắc thực hành:** Lưu rõ loại tiền, mức chính xác và cách làm tròn. Nếu chọn biểu diễn minor units bằng số nguyên, cần quy định **minor unit của từng loại tiền** và phiên bản quy tắc sử dụng.

## 4. Lựa chọn kiểu số: vì sao tiền không nên dùng double?

`float` và `double` sử dụng số thực nhị phân theo chuẩn IEEE 754. Nhiều phân số thập phân như 0,1 không thể biểu diễn chính xác bằng hữu hạn bit nhị phân.

Ví dụ:

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum); // 0.30000000000000004
~~~

Trong nhiều bài toán mô phỏng khoa học, sai số xấp xỉ đó có thể chấp nhận nếu được kiểm soát. Nhưng đối với số tiền dùng để **tính phí, đối soát, lưu sổ**, một sai khác nhỏ tích lũy hoặc kết hợp với làm tròn không đúng lúc có thể tạo kết quả sai.

### 4.1. Dùng BigDecimal với giá trị thập phân tường minh

~~~java
import java.math.BigDecimal;

BigDecimal price = new BigDecimal("12.50");
BigDecimal quantity = new BigDecimal("2.5");
BigDecimal total = price.multiply(quantity);

System.out.println(total); // 31.250
~~~

`BigDecimal` biểu diễn số thập phân với trị số và scale; phù hợp cho phép tính cần kiểm soát chính xác thập phân. Nên khởi tạo từ **chuỗi** hoặc API chuyển đổi có chủ đích:

~~~java
BigDecimal exact = new BigDecimal("0.1");
BigDecimal fromDoubleValue = BigDecimal.valueOf(0.1);

// Không nên dùng cách này khi mong muốn số thập phân chính xác 0.1:
BigDecimal notDecimalPointOne = new BigDecimal(0.1);
~~~

`new BigDecimal(0.1)` ghi nhận chính xác **giá trị double xấp xỉ 0,1**, vì vậy có nhiều chữ số thập phân ngoài dự kiến. `BigDecimal.valueOf(0.1)` dùng biểu diễn chuỗi của double để tạo một giá trị thập phân thường gần với ý định, nhưng với dữ liệu nghiệp vụ đầu vào, **chuỗi số ban đầu** vẫn là lựa chọn rõ ràng nhất.

### 4.2. BigDecimal có scale và quy tắc so sánh riêng

~~~java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

System.out.println(a.equals(b));    // false: scale khác nhau
System.out.println(a.compareTo(b)); // 0: giá trị số bằng nhau
~~~

`equals` xét cả giá trị lẫn scale; `compareTo` so sánh theo giá trị số. Nếu dùng `BigDecimal` làm key của tập hợp hoặc bản đồ, phải quyết định scale canonical. Đừng âm thầm thay `equals` bằng `compareTo` khi nghiệp vụ cần phân biệt mức chính xác dữ liệu đầu vào.

**BigDecimal không tự biết loại tiền, đơn vị hay quy tắc làm tròn.** Nó là công cụ số học; ngữ nghĩa phải đến từ domain model.

## 5. Biểu diễn Money bằng value object trong Java

Một value object là kiểu dữ liệu tập trung vào **giá trị và quy tắc** thay vì danh tính một bản ghi database. Java record phù hợp cho trường hợp đơn giản:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }

    Money add(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Khac loai tien");
        }
        return new Money(amount.add(other.amount()), currency);
    }

    Money multiply(BigDecimal factor) {
        Objects.requireNonNull(factor, "factor");
        return new Money(amount.multiply(factor), currency);
    }

    Money roundTo(int scale, RoundingMode rule) {
        return new Money(amount.setScale(scale, rule), currency);
    }
}

class Example {
    public static void main(String[] args) {
        Money price = new Money(
                new BigDecimal("12.50"), Currency.getInstance("USD"));

        Money subtotal = price.multiply(new BigDecimal("2.5"));
        Money payable = subtotal.roundTo(2, RoundingMode.HALF_EVEN);

        System.out.println(payable.amount()); // 31.25
        System.out.println(payable.currency().getCurrencyCode()); // USD

        Money inVnd = new Money(
                new BigDecimal("10000"), Currency.getInstance("VND"));
        // price.add(inVnd) sẽ báo lỗi vì khác currency.
    }
}
~~~

Ví dụ dùng record bất biến, kiểm tra null và từ chối cộng khác tiền tệ. Trong hệ thống thật còn cần:

- Quy tắc số tiền **âm**: một khoản hoàn tiền hoặc điều chỉnh có thể âm, nhưng “giá bán cơ bản” thường không được âm.
- Quy định **scale, precision và rounding** ở từng loại giao dịch.
- Giới hạn giá trị cực lớn trước khi lưu để phù hợp schema.
- Nếu yêu cầu thanh toán, quy tắc của cổng thanh toán có thể khác số chữ số thập phân dùng trong tính toán nội bộ.

Không nên chặn mọi giá trị âm ở lớp `Money` nếu hệ thống có refund hoặc bút toán điều chỉnh. Có thể tạo kiểu riêng như `NonNegativePrice` hoặc kiểm tra bất biến tại điểm nghiệp vụ.

Các thư viện theo chuẩn **JSR 354 (Java Money)** cũng cung cấp mô hình giá trị tiền tệ, nhưng lựa chọn thư viện phải dựa trên phụ thuộc và quy ước của dự án. Nền tảng thiết kế vẫn là **amount + currency + quy tắc nghiệp vụ**.

## 6. Làm tròn là quy tắc nghiệp vụ, không phải thao tác trang trí

Giả sử tiền thuế được tính bằng:

~~~text
tax = taxable_amount × tax_rate
~~~

Ta có thể tính toán ở độ chính xác cao hơn số chữ số được phép thanh toán, rồi làm tròn **tại điểm được quy định**. Làm tròn từng dòng hàng và làm tròn một lần trên tổng đơn có thể cho kết quả khác nhau.

### 6.1. Các chế độ làm tròn thường dùng

| Chế độ | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `HALF_UP` | Khi đúng điểm giữa, làm tròn xa 0 | Thường gặp trong một số quy tắc hóa đơn |
| `HALF_EVEN` | Khi đúng điểm giữa, chọn chữ số cuối chẵn | Giảm một dạng thiên lệch khi làm tròn nhiều lần |
| `DOWN` | Bỏ phần dư theo hướng về 0 | Không giống `FLOOR` với số âm |
| `FLOOR` | Làm tròn về âm vô cực | Có thể khác `DOWN` nếu giá trị âm |
| `UNNECESSARY` | Yêu cầu phép tính không phải làm tròn | Có thể phát sinh ngoại lệ nếu phần thập phân không thể biểu diễn ở scale yêu cầu |

Ví dụ:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal oneThird = BigDecimal.ONE
        .divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP);
System.out.println(oneThird); // 0.3333

BigDecimal midpoint = new BigDecimal("2.345");
System.out.println(midpoint.setScale(2, RoundingMode.HALF_UP));   // 2.35
System.out.println(midpoint.setScale(2, RoundingMode.HALF_EVEN)); // 2.34
~~~

`BigDecimal.divide` không truyền scale hoặc `MathContext` có thể ném `ArithmeticException` khi kết quả là số thập phân vô hạn tuần hoàn. Vì vậy, hãy thiết kế **độ chính xác và rounding mode** cho phép chia, không chỉ ở cuối giao dịch.

### 6.2. Tránh làm tròn tại mọi bước mà không có quy tắc

Giả sử mỗi dòng hàng phát sinh thuế 0,005 USD. Nếu làm tròn từng dòng lên 0,01 USD rồi cộng hai dòng, thuế là 0,02 USD; nếu cộng hai số chưa làm tròn rồi làm tròn tổng, thuế có thể là 0,01 USD. Hai cách thể hiện **hai chính sách khác nhau**.

Không có một thứ tự làm tròn đúng cho mọi nghiệp vụ. Quy tắc cần dựa trên luật/điều khoản và cách đối soát thực tế, được mô tả trong đặc tả nghiệp vụ và kiểm thử bằng ví dụ ranh giới.

### 6.3. Số tiền nguyên theo minor units

Một lựa chọn khác là lưu **số nguyên minor units**:

~~~java
import java.math.BigDecimal;
import java.util.Currency;

static long toMinorUnits(BigDecimal major, Currency currency) {
    int digits = currency.getDefaultFractionDigits();
    if (digits < 0) {
        throw new IllegalArgumentException("Khong co minor unit xac dinh");
    }
    // Không tự làm tròn: giá trị không biểu diễn chính xác sẽ báo lỗi.
    return major.movePointRight(digits).longValueExact();
}
~~~

Trong một lớp Java có các import tương ứng, phương thức này chuyển số tiền theo đơn vị chính sang `long` minor units; ví dụ `12.34 USD → 1234` cent và `125 VND → 125` đơn vị tiền. `longValueExact()` báo lỗi nếu có phần lẻ không biểu diễn được hoặc vượt giới hạn kiểu `long`.

Phương pháp này tốt khi **đơn vị nhỏ và quy tắc giao dịch đã xác định**, song không phù hợp nếu mặc định mọi tiền tệ đều có hai chữ số thập phân hoặc hệ thống cần số lượng thập phân trung gian tinh hơn đơn vị thanh toán. Trong dữ liệu lịch sử, cần biết **quy tắc minor unit đã áp dụng ở thời điểm ghi**.

## 7. Tỷ giá: không được cộng, so sánh hay quy đổi tiền tệ tùy tiện

Giả sử có:

~~~text
100 USD
100 VND
~~~

Chúng **không thể cộng hoặc so sánh trực tiếp** nếu mục tiêu là tổng giá trị kinh tế. Muốn quy đổi, phải có một **exchange rate** với hướng rõ ràng:

~~~text
fromCurrency = USD
toCurrency   = VND
rate         = 25000 VND / USD   (ví dụ giả định, không phải tỷ giá hiện hành)
validAt      = thời điểm hoặc khoảng hiệu lực
source       = nguồn tỷ giá đã được chấp nhận
~~~

Với tỷ giá minh họa `1 USD = 25.000 VND`, `12,34 USD × 25.000 VND/USD = 308.500 VND` trước phí hoặc quy tắc thanh toán khác.

### 7.1. Tỷ giá phải có hướng và thời điểm

Một số `25000` không đủ để biết đơn vị là `VND/USD` hay `USD/VND`. Tỷ giá nghịch đảo có thể không phải giá trị được sử dụng khi giao dịch do spread, phí hoặc cách niêm yết. Cần lưu ít nhất:

- Đồng tiền nguồn và đồng tiền đích.
- Giá trị tỷ giá, số chữ số chính xác và quy tắc làm tròn.
- Thời gian hiệu lực, thời gian lấy dữ liệu và nguồn dữ liệu.
- Loại tỷ giá khi nghiệp vụ cần (mua/bán, tỷ giá hợp đồng, tỷ giá kế toán).
- Mã giao dịch/đối soát và số tiền gốc nếu đã thực hiện quy đổi.

**Dữ liệu lịch sử không nên được âm thầm tính lại theo tỷ giá hôm nay.** Một đơn đã thanh toán phải bảo toàn số tiền và tỷ giá đã dùng, hoặc bảo toàn chứng từ/quy tắc có thể tái hiện, để hoàn tiền và đối soát sau này.

### 7.2. Value object tỷ giá

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.Currency;

record FxRate(
        Currency from,
        Currency to,
        BigDecimal targetPerSource,
        Instant validAt,
        String source) {

    FxRate {
        if (from == null || to == null || validAt == null || source == null
                || source.isBlank() || targetPerSource == null
                || targetPerSource.signum() <= 0) {
            throw new IllegalArgumentException("Ty gia khong hop le");
        }
    }

    Money convert(Money original, int scale, RoundingMode rounding) {
        if (!original.currency().equals(from)) {
            throw new IllegalArgumentException("Sai currency nguon");
        }
        return new Money(
                original.amount().multiply(targetPerSource)
                        .setScale(scale, rounding),
                to);
    }
}
~~~

Đoạn này giả định kiểu `Money` đã định nghĩa ở mục 5. Trường `source` và `validAt` chỉ là thông tin tối thiểu; nếu cần kiểm toán chính xác, phải bổ sung định danh/bản phát hành nguồn tỷ giá và chính sách làm tròn/thu phí cụ thể.

## 8. Đơn vị đo: trị số phải đi cùng đại lượng và đơn vị

Với các phép đo, cần phân biệt:

- **Quantity value:** số lượng đo được, ví dụ `2500`.
- **Unit:** đơn vị thể hiện, ví dụ `g`.
- **Dimension:** loại đại lượng, ví dụ **khối lượng**, **chiều dài**, **thời gian**.
- **Measurement context:** nguồn đo, mức chính xác, sai số, thời điểm, điều kiện nếu nghiệp vụ yêu cầu.

Một giá trị `2,5 kg` có thể quy đổi sang `2.500 g`, nhưng không thể quy đổi thành `2.500 m` vì khác dimension.

| Đại lượng | Đơn vị ví dụ | Quy đổi điển hình |
| --- | --- | --- |
| Khối lượng | kg, g | 1 kg = 1.000 g |
| Chiều dài | m, cm | 1 m = 100 cm |
| Thời gian | s, min, h | 1 h = 3.600 s |
| Dung lượng dữ liệu | B, kB, KiB | 1 kB = 1.000 B; 1 KiB = 1.024 B |
| Thể tích | L, mL | 1 L = 1.000 mL |
| Nhiệt độ | °C, °F, K | Cần xét offset; không chỉ nhân một hệ số |

**Viết hoa, viết thường và tiền tố rất quan trọng.** Theo quy ước phổ biến, `m` là mét, `mm` là milimét, `M` là tiền tố mega chứ không phải một đơn vị “mét viết hoa”. `MB` (thập phân) và `MiB` (nhị phân) có ý nghĩa khác nhau khi tính dung lượng.

### 8.1. Đơn vị hiển thị và đơn vị lưu chuẩn

Một hệ thống có thể cho người dùng nhập `2500 g` hoặc `2.5 kg`, nhưng lưu giá trị đã chuẩn hóa về **kg** để hỗ trợ truy vấn và so sánh:

~~~text
Input A: 2500 g  → canonicalMass = 2.5 kg
Input B: 2.5 kg  → canonicalMass = 2.5 kg
~~~

Nếu cần truy vết, nên lưu thêm **trị số và đơn vị gốc**. Việc chỉ giữ giá trị chuẩn có thể làm mất thông tin về độ chính xác biểu kiến của phép đo đầu vào (ví dụ `2,500 kg` có thể thể hiện độ phân giải khác `2,5 kg` theo ngữ cảnh).

Lưu chuẩn chỉ có lợi nếu **đơn vị chuẩn và quy tắc quy đổi ổn định**, được thống nhất toàn hệ thống. Nếu các service sử dụng nhiều quy ước khác nhau, cột `mass` không có đơn vị trong tên/hợp đồng vẫn rất dễ bị hiểu sai.

## 9. Value object Quantity và kiểm tra dimension trong Java

Ví dụ sau xây dựng bốn đơn vị thuộc hai dimension; hệ số chuyển về đơn vị chuẩn lần lượt là **kg** cho khối lượng và **m** cho chiều dài:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.util.Objects;

enum Dimension {
    MASS, LENGTH
}

enum Unit {
    KG(Dimension.MASS, "1"),
    G(Dimension.MASS, "0.001"),
    M(Dimension.LENGTH, "1"),
    CM(Dimension.LENGTH, "0.01");

    final Dimension dimension;
    final BigDecimal factorToBase;

    Unit(Dimension dimension, String factor) {
        this.dimension = dimension;
        this.factorToBase = new BigDecimal(factor);
    }
}

record Quantity(BigDecimal value, Unit unit) {
    public Quantity {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(unit, "unit");
    }

    Quantity to(Unit target) {
        Objects.requireNonNull(target, "target");
        if (unit.dimension != target.dimension) {
            throw new IllegalArgumentException("Khac loai dai luong");
        }
        BigDecimal base = value.multiply(unit.factorToBase);
        BigDecimal converted = base.divide(
                target.factorToBase, MathContext.DECIMAL128);
        return new Quantity(converted, target);
    }

    Quantity add(Quantity other) {
        Objects.requireNonNull(other, "other");
        Quantity converted = other.to(unit);
        return new Quantity(value.add(converted.value()), unit);
    }
}

class QuantityExample {
    public static void main(String[] args) {
        Quantity input = new Quantity(new BigDecimal("2500"), Unit.G);
        Quantity kilograms = input.to(Unit.KG);
        System.out.println(kilograms.value()); // 2.500

        Quantity total = kilograms.add(
                new Quantity(new BigDecimal("0.5"), Unit.KG));
        System.out.println(total.value()); // 3.000

        // kilograms.add(new Quantity(BigDecimal.ONE, Unit.M));
        // -> IllegalArgumentException: khác dimension.
    }
}
~~~

Ở đây, dimension giúp phát hiện lỗi “cộng kg với mét”. `MathContext.DECIMAL128` đưa ra độ chính xác số học cho các phép chia có thể sinh chữ số thập phân dài; nó **không tự quyết định độ phân giải đo đạc hợp lệ**. Nghiệp vụ vẫn phải quy định scale, rounding và giới hạn dựa trên đơn vị/thiết bị.

Đây là ví dụ đơn giản với quy đổi **tuyến tính**. Nhiệt độ Celsius/Fahrenheit cần **chuyển đổi affine có độ lệch**; các phép toán nhiệt độ tuyệt đối cũng khác phép toán chênh lệch nhiệt độ. Những đại lượng có bản chất đó cần kiểu và quy tắc riêng, không áp dụng máy móc `value × factor`.

### 9.1. Một số giá trị không phải “quantity vật lý”

Các giá trị như **tỷ lệ phần trăm**, **điểm tín dụng**, **điểm đánh giá**, **số lượng người**, **mã vùng**, **mã trạng thái** có quy tắc khác với khối lượng hoặc chiều dài.

Ví dụ, `0.15` có thể biểu thị tỷ lệ 15% dưới dạng **ratio**, còn `15` có thể là 15 điểm phần trăm hoặc 15%. Hợp đồng cần quy định rõ:

~~~text
taxRate = 0.15         # ratio, tương đương 15%
discountPercent = 15  # số phần trăm, không phải ratio
ratingScore = 4.5      # điểm theo thang đã định nghĩa
~~~

Nếu trộn hai quy ước ratio và percent, phép nhân có thể lệch 100 lần. Hãy đặt tên trường và kiểu domain phản ánh quy ước, chẳng hạn `taxRateRatio` và `discountPercentPoints`.

## 10. Đơn giá là tiền trên một đơn vị đại lượng

Giả sử một cửa hàng bán cà phê theo khối lượng:

~~~text
quantity       = 2500 g
unitPrice      = 12.50 USD/kg

quantity chuẩn = 2.5 kg
subtotal       = 2.5 kg × 12.50 USD/kg
               = 31.25 USD
~~~

Đơn giá ở đây không chỉ là `12.50 USD`. Nó mang đơn vị ghép **USD/kg**. Nếu bỏ mất `/kg`, một dịch vụ khác có thể hiểu đó là giá mỗi gói, tạo sai lệch lớn.

Trong domain model, có thể biểu diễn:

~~~text
UnitPrice {
  amount:   12.50
  currency: USD
  perUnit:  kg
}

Quantity {
  value: 2500
  unit:  g
}
~~~

Trước khi nhân, phải đổi quantity sang đúng đơn vị mẫu số của đơn giá. Không được nhân `2500 × 12.50` rồi gắn nhãn USD nếu đơn giá quy định theo kg.

### 10.1. Tính toán cần đi qua một ranh giới nghiệp vụ

1. Xác thực quantity dương, unit nằm trong tập hợp được hỗ trợ.
2. Kiểm tra dimension của quantity phù hợp với đơn vị tính giá.
3. Quy đổi quantity về đơn vị mà `UnitPrice` sử dụng.
4. Nhân bằng `BigDecimal` và lưu kết quả trung gian với độ chính xác đủ.
5. Áp dụng quy tắc thuế/chiết khấu đã định nghĩa.
6. Làm tròn theo quy tắc thanh toán, lưu kết quả cuối cùng cùng currency.

Một hàng hóa bán theo **chiếc** lại cần số đếm nguyên. Với thuốc hoặc hàng hóa có quy định định lượng, có thể cần độ phân giải, bước nhảy và giới hạn nhỏ nhất/lớn nhất riêng.

## 11. Thiết kế schema database giữ đủ ngữ nghĩa

Một schema có các cột `amount NUMERIC` và `weight NUMERIC` nhưng không có currency/unit hoặc hợp đồng thống nhất sẽ rất khó bảo trì.

Ví dụ PostgreSQL dùng hai bảng độc lập để minh họa:

~~~sql
CREATE TABLE payments (
    id UUID PRIMARY KEY,
    amount NUMERIC(20, 4) NOT NULL CHECK (amount >= 0),
    currency_code VARCHAR(3) NOT NULL CHECK (
        currency_code ~ '^[A-Z]{3}$'
    ),
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE parcel_measurements (
    id UUID PRIMARY KEY,
    mass_value NUMERIC(20, 6) NOT NULL CHECK (mass_value >= 0),
    mass_unit VARCHAR(8) NOT NULL CHECK (mass_unit IN ('g', 'kg')),
    measured_at TIMESTAMPTZ NOT NULL
);
~~~

Các đặc điểm:

- `NUMERIC(20, 4)` và `NUMERIC(20, 6)` là **lựa chọn minh họa**. Precision/scale phải được tính theo giới hạn nghiệp vụ, cách quy đổi và các giá trị lớn nhất có thể xuất hiện.
- `CHECK (amount >= 0)` phù hợp với bảng **khoản thu** ví dụ. Một bảng refund hoặc ledger có thể cho phép amount âm hoặc lưu dấu biến động riêng.
- Biểu thức `'^[A-Z]{3}$'` chỉ kiểm tra **hình thức** mã tiền tệ, không chứng minh mã đó được công nhận hoặc được ứng dụng hỗ trợ. Có thể dùng bảng tham chiếu currency hoặc kiểm tra tại domain.
- `mass_unit` giới hạn hai đơn vị đo mà ví dụ hỗ trợ; hệ thống thực tế có thể dùng bảng mã đơn vị, bảng tham chiếu hoặc một chuẩn như UCUM tùy lĩnh vực.
- Các cột thời gian giúp ghi nhận bối cảnh; với tỷ giá hoặc dữ liệu đo phải cân nhắc thêm nguồn, phương pháp và mức chính xác.

### 11.1. Dùng cột có đơn vị cố định khi nghiệp vụ thống nhất

Nếu toàn bộ hệ thống quy định khối lượng lưu theo gram, cột `mass_grams` có thể rõ hơn cặp `mass_value, mass_unit`. Tuy nhiên, nếu còn cần phân biệt **2 kg** với **2000 g** đã được nhập từ một thiết bị nào đó, hãy lưu thêm thông tin nguồn.

Hai hướng có thể cân nhắc:

| Hướng | Ưu điểm | Hạn chế |
| --- | --- | --- |
| **Giá trị + mã đơn vị** | Giữ nguyên cách người dùng/nguồn nhập | Query so sánh giữa nhiều đơn vị phải quy đổi, dễ dùng sai |
| **Đơn vị chuẩn cố định** | So sánh, sắp xếp, làm index đơn giản | Có thể mất ngữ cảnh gốc nếu không lưu thêm |
| **Đồng thời giá trị gốc và chuẩn** | Truy vấn hiệu quả và phục vụ audit | Phải bảo đảm quy tắc quy đổi và tính nhất quán hai phiên bản |

Với dữ liệu cần tra cứu “khối lượng lớn hơn 10 kg”, một cột canonical như `mass_kg` giúp lập index rõ hơn so với truy vấn trộn `g` và `kg`. Nếu lưu cả hai dạng, nên để việc ghi và chuẩn hóa diễn ra **nguyên tử** trong cùng transaction hoặc theo cơ chế bất biến được kiểm soát.

### 11.2. Lưu tiền bằng NUMERIC hay BIGINT minor units?

| Mô hình | Ví dụ | Thích hợp khi | Lưu ý |
| --- | --- | --- | --- |
| `NUMERIC + currency_code` | `amount=12.34, USD` | Cần số thập phân và scale rõ | Phải quyết định rounding, precision và chặn mixed-currency |
| `BIGINT minor_units + currency_code` | `minor=1234, USD` | Số tiền có đơn vị nhỏ cố định theo giao dịch | Tránh overflow; cần quy tắc minor unit theo currency |
| Value object Money trong Java + mapping rõ | `Money(BigDecimal, Currency)` | Muốn giữ bất biến ở domain | ORM/JDBC phải ánh xạ hai trường cùng nhau |

Đừng chọn `DOUBLE PRECISION` cho cột tiền chỉ vì tính toán nhanh hoặc đơn giản. Với dữ liệu kế toán, việc chứng minh phép tính và đối soát thường quan trọng hơn tối ưu vi mô đó.

### 11.3. Ràng buộc không thay được mọi guard nghiệp vụ

Database có thể kiểm tra kiểu, `CHECK`, `NOT NULL`, `UNIQUE` và khóa ngoại. Nhưng nó không tự biết quy tắc “giá bán tối đa cho loại khách hàng này”, “tỷ giá phải được duyệt” hoặc “đơn phải được thanh toán trước khi xuất kho” nếu quy tắc đó chưa được mô hình hóa.

Hãy đặt **guard** tại domain/service và bảo vệ lại bất biến quan trọng tại thời điểm ghi. Đặc biệt khi nhiều request cạnh tranh, cần transaction, khóa hoặc cập nhật có điều kiện để tránh lưu dữ liệu hợp lệ riêng lẻ nhưng mâu thuẫn với tổng thể.

## 12. Thiết kế hợp đồng JSON và API không làm mất ý nghĩa

Một API nên truyền amount/unit/currency bằng những trường được đặt tên rõ:

~~~json
{
  "lineId": "L-1001",
  "quantity": {
    "value": "2500",
    "unit": "g"
  },
  "unitPrice": {
    "amount": "12.50",
    "currency": "USD",
    "perUnit": "kg"
  }
}
~~~

Vì JSON không quy định một kiểu thập phân có scale giống `BigDecimal`, việc truyền **decimal dưới dạng chuỗi** là một hợp đồng thường được chọn để client JavaScript không vô tình chuyển qua floating point binary và làm đổi giá trị. Nếu API chọn JSON number, phải quy định precision, giới hạn và hành vi parser ở từng nền tảng.

Khi dữ liệu tới Java:

- Parse chuỗi số bằng `new BigDecimal(value)` và từ chối đầu vào không hợp lệ.
- Kiểm tra mã currency/unit trong danh sách được hỗ trợ; phân biệt chữ hoa/thường theo hợp đồng.
- Không tin một `total` do client tính sẵn khi server chịu trách nhiệm tính tiền.
- Phân biệt rõ `0`, `null`, “không đo được”, “không áp dụng” và “chưa có dữ liệu”.
- Giới hạn độ dài, precision, scale và số lượng phần tử để tránh tốn tài nguyên bất thường.

**Không để client quyết định tỷ giá được sử dụng để thanh toán.** Các giá trị có tác động tài chính cần được server kiểm tra/tra cứu từ nguồn tin cậy và gắn với transaction tương ứng.

### 12.1. Phân biệt giá trị chưa biết và giá trị bằng không

Ví dụ một kiện hàng chưa cân:

~~~json
{
  "mass": null,
  "measurementStatus": "NOT_MEASURED"
}
~~~

Nó **không tương đương** với:

~~~json
{
  "mass": {"value": "0", "unit": "kg"},
  "measurementStatus": "MEASURED"
}
~~~

Trong SQL, `NULL` có ngữ nghĩa khác 0; cần quy định khi nào được phép null, cách kiểm tra và báo cáo. Một cột `NOT NULL DEFAULT 0` cho trọng lượng chưa đo có thể gây ra nhầm lẫn nghiêm trọng trong tính phí vận chuyển.

## 13. Giá trị có ngữ nghĩa trong truy vấn và chỉ mục

### 13.1. Không so sánh tiền khác loại như thể cùng đơn vị

Truy vấn sau thường **không trả lời được** câu hỏi “khoản thanh toán có giá trị lớn hơn 100 USD”:

~~~sql
SELECT id, amount, currency_code
FROM payments
WHERE amount > 100;
~~~

Nếu bảng chứa cả USD, VND và JPY, `100` mang các ý nghĩa khác nhau. Đúng hơn, cần nêu rõ loại tiền:

~~~sql
SELECT id, amount, currency_code
FROM payments
WHERE currency_code = 'USD'
  AND amount > 100;
~~~

Nếu cần xếp hạng giá trị quy đổi về một đồng tiền báo cáo, hệ thống phải có quy tắc tỷ giá và mốc thời gian xác định. Kết quả quy đổi có thể được lưu như dữ liệu dẫn xuất với nguồn gốc, hoặc tính có kiểm soát; không tự cộng mọi cột `amount` khác currency.

### 13.2. Chỉ mục phục vụ truy vấn có ngữ nghĩa

Nếu workload thường tìm các giao dịch USD vượt ngưỡng, có thể cân nhắc chỉ mục:

~~~sql
CREATE INDEX idx_payments_currency_amount
    ON payments (currency_code, amount);
~~~

Một index như vậy có thể phù hợp với điều kiện equality theo currency và range theo amount, nhưng chi phí ghi tăng và lợi ích thực tế phụ thuộc dữ liệu, query planner và tần suất truy cập. Hãy đo với `EXPLAIN` và số liệu đại diện.

Đối với đại lượng đo, nếu dữ liệu được chuẩn hóa về cột `mass_kg`, truy vấn khoảng và index dễ thống nhất hơn. Nếu dữ liệu vẫn ở các unit khác nhau, không được lọc `mass_value > 10` mà quên unit.

### 13.3. Tránh ghi đè ngữ nghĩa trong báo cáo tổng hợp

Các biểu đồ “doanh thu theo tháng” hoặc “khối lượng vận chuyển theo ngày” cần quy định:

- Nhóm nào có thể cộng với nhau (cùng currency, cùng dimension).
- Đơn vị báo cáo và quy tắc quy đổi.
- Thời điểm chọn tỷ giá và chính sách làm tròn.
- Dữ liệu nào bị hoàn tiền, hủy, sửa lỗi hoặc đến trễ.

Một dashboard hiển thị giá trị chính xác đến bốn chữ số thập phân vẫn có thể **sai ngữ nghĩa** nếu cộng nhầm tiền tệ hoặc lẫn gram với kilogram.

## 14. Giao dịch và kiểm soát đồng thời với số tiền, số lượng

Khi nhiều request cùng cập nhật một khoản tiền hay lượng tồn, điều kiện đúng ở RAM có thể không còn đúng khi ghi.

Ví dụ trừ tồn kho lưu theo **đơn vị cố định là gram**:

~~~sql
UPDATE inventory
SET available_grams = available_grams - :requestedGrams,
    version = version + 1
WHERE product_id = :productId
  AND available_grams >= :requestedGrams
  AND version = :expectedVersion;
~~~

Ở đây:

1. Server phải **chuẩn hóa quantity về gram** và xác thực `requestedGrams > 0` trước khi bind tham số.
2. Nếu bản ghi được cập nhật đúng một hàng, điều kiện về tồn kho/version đã thỏa tại thời điểm ghi.
3. Nếu không cập nhật hàng nào, cần xử lý xung đột, không có sản phẩm hoặc không đủ tồn kho.
4. Nếu tạo đơn và trừ kho là một thao tác nghiệp vụ, tất cả thay đổi liên quan phải nằm trong transaction phù hợp và chỉ báo thành công sau khi commit theo hợp đồng.

Lưu ý: kiểu của `available_grams` phải hỗ trợ **độ phân giải nhỏ nhất có thể có trong hàng hóa thực tế**. Nếu kho đo đến 0,1 g nhưng schema dùng integer gram, việc làm tròn mỗi yêu cầu sẽ làm mất dữ liệu. Có thể chọn decimal gram hoặc một đơn vị chuẩn nhỏ hơn dựa trên nghiệp vụ.

Với các thao tác như chuyển khoản, không chỉ cần kiểu Money chính xác: còn phải bảo đảm **số dư không âm theo quy tắc**, các bút toán được ghi nguyên tử, xử lý yêu cầu lặp và có khả năng đối soát khi kết quả commit không rõ.

### 14.1. Tránh nhân đôi tác động khi retry

Giả sử client gửi yêu cầu thanh toán 100 USD, nhưng mất kết nối đúng lúc commit. Nếu thử lại bằng một transaction mới mà không có idempotency key, có thể tạo khoản thu thứ hai.

Một thiết kế có thể lưu `request_id`/`payment_id` duy nhất, trạng thái xử lý, Money và kết quả nghiệp vụ trong cùng transaction; khi retry, tra cứu theo khóa ổn định trước khi thực hiện lại. Độ chính xác của `BigDecimal` không tự giải quyết bài toán **exactly-once effect**.

## 15. Dữ liệu gốc, dữ liệu chuẩn và khả năng kiểm toán

Với phép đo có nguồn gốc bên ngoài, có thể cần lưu cả **giá trị gốc** và **giá trị dùng để tính toán**:

~~~text
sourceValue:       2500
sourceUnit:        g
canonicalValue:    2.500
canonicalUnit:     kg
measuredAt:        2026-11-01T08:00:00Z
sourceSystem:      scale-device-17
conversionRule:    mass-v1
~~~

Nếu chỉ giữ `canonicalValue`, ta có thể không biết giá trị gốc đến từ đơn vị nào và thiết bị nào. Nếu chỉ giữ giá trị gốc, các truy vấn so sánh có thể phải quy đổi trên từng hàng và có nguy cơ mỗi dịch vụ áp dụng quy tắc khác nhau.

Tương tự với tiền:

~~~text
originalAmount:    12.34
originalCurrency:  USD
convertedAmount:   308500
targetCurrency:    VND
fxRate:            25000 VND/USD  (ví dụ giả định)
rateValidAt:       2026-11-01T08:00:00Z
roundingRule:      HALF_EVEN, scale=0
~~~

Việc lưu cả đầu vào, chính sách và kết quả chỉ cần thiết đến mức **phù hợp với khả năng truy vết và yêu cầu lưu giữ**. Những trường bổ sung làm tăng chi phí lưu trữ nhưng có thể giảm đáng kể chi phí xử lý tranh chấp và khôi phục sai sót.

## 16. Dữ liệu có ngữ nghĩa còn gắn với bảo mật và quyền truy cập

Không phải mọi trường số đều vô hại. Giá tiền, mức chiết khấu, hạn mức tín dụng, số lượng tồn kho hoặc tỷ giá hợp đồng đều có thể là thông tin nhạy cảm và ảnh hưởng quyền lợi.

- **Phân quyền sửa:** chỉ các thao tác nghiệp vụ được cho phép mới thay đổi giá, số tiền thanh toán hay quy tắc quy đổi.
- **Không tin client:** server tính lại số tiền cuối hoặc xác minh số tiền được ký/xác nhận bởi nguồn tin cậy.
- **Query tham số hóa:** dùng `PreparedStatement` hoặc framework bind tham số; không nối input thành SQL.
- **Giới hạn đầu vào:** chặn trị số cực lớn, scale/precision quá mức, unit không biết hoặc mã currency không hỗ trợ.
- **Audit:** ghi ai thay giá, tỉ giá nguồn nào đã dùng, khi nào hoàn tiền hoặc điều chỉnh.
- **Bảo vệ bản sao:** log, event, backup và file export cũng có thể chứa dữ liệu tiền tệ hoặc thông tin kinh doanh nhạy cảm.

Ví dụ, một kẻ tấn công có thể gửi `discountPercent = 10000` hoặc `quantity = -1`. Nếu backend chỉ kiểm tra “đây là một số hợp lệ”, hệ thống vẫn có nguy cơ tạo đơn sai. Kiểm tra miền giá trị và quyền thao tác phải được thực hiện **ở phía server**.

## 17. Tiến hóa schema và quy tắc biểu diễn theo thời gian

Giả sử phiên bản đầu chỉ bán hàng theo **chiếc**, lưu `quantity INTEGER`. Phiên bản sau bổ sung hàng bán theo **kg**. Nếu chỉ đổi `quantity` sang `NUMERIC` mà không bổ sung ngữ nghĩa, các bản ghi cũ sẽ trở nên mơ hồ.

Một quy trình migration hợp lý:

1. **Xác định ý nghĩa lịch sử:** tất cả quantity cũ đều là số chiếc hay có ngoại lệ?
2. **Bổ sung trường mới tương thích:** ví dụ `quantity_value` và `quantity_unit`, trong giai đoạn chuyển tiếp vẫn đọc được dữ liệu cũ.
3. **Backfill có kiểm soát:** chuyển bản ghi cũ sang unit `piece` chỉ khi chắc chắn quy tắc cũ là số chiếc.
4. **Cập nhật reader/writer:** hỗ trợ mô hình mới, áp dụng validation và không ghi giá trị thiếu unit.
5. **Kiểm tra dữ liệu/chỉ mục:** quan sát collision, lỗi quy đổi, kết quả báo cáo và thời gian truy vấn.
6. **Siết ràng buộc, loại đường cũ:** chỉ sau khi mọi ứng dụng đang chạy tương thích và migration đã được xác nhận.

Đối với tiền tệ, thay đổi minor units, cách hiển thị, rounding policy hoặc tỷ giá có thể tác động dữ liệu lịch sử. Đừng tự viết lại toàn bộ khoản thu cũ theo chính sách mới nếu chưa có quyết định nghiệp vụ. Có thể cần lưu **policy version** và phân biệt số tiền đã giao dịch với số tiền báo cáo tính lại.

### 17.1. Sao lưu và phục hồi cần giữ cả ngữ nghĩa

Backup số liệu mà thiếu bảng tham chiếu currency/unit, lịch sử tỷ giá hoặc thông tin phiên bản quy tắc có thể **khôi phục được byte nhưng không khôi phục được cách diễn giải**.

Khi lập kế hoạch restore, cần kiểm tra:

- Dữ liệu chính và bảng tham chiếu được phục hồi tới những thời điểm phù hợp.
- Schema và phiên bản ứng dụng có thể đọc các kiểu/đơn vị đã tồn tại.
- Các bút toán và trạng thái giao dịch không bị áp dụng trùng khi replay.
- Kết quả tính lại từ bản khôi phục trùng với các tổng đã được đối soát trong giới hạn làm tròn quy định.

**Durability, backup và semantic integrity là các yêu cầu bổ sung cho nhau.** Lưu rất bền một giá trị sai đơn vị không làm ứng dụng đúng hơn.

## 18. Hiệu năng: chọn biểu diễn có thể đo và truy vấn hiệu quả

`BigDecimal` thường tốn nhiều CPU và bộ nhớ hơn phép toán trên `long`, trong khi `NUMERIC` có chi phí khác `BIGINT` ở database. Nhưng đổi sang `double` chỉ vì nhanh hơn có thể đưa sai số không phù hợp vào nghiệp vụ.

Những tiêu chí cần xem:

| Câu hỏi | Hệ quả thiết kế |
| --- | --- |
| Lượng phép tính tiền/giây lớn đến mức nào? | Xem xét chi phí BigDecimal, batch, caching của kết quả dẫn xuất |
| Có sử dụng một đơn vị nhỏ cố định không? | Có thể dùng `long` nếu bảo đảm không overflow và đúng minor units |
| Truy vấn có lọc theo giá trị tiền không? | Phải lọc cùng currency hoặc có giá trị quy đổi được xác minh |
| Truy vấn khoảng theo đại lượng đo có phổ biến không? | Cột canonical cố định và index có thể phù hợp |
| Các trường đơn vị/tỷ giá có thay đổi thường xuyên không? | Tác động tới index, cache invalidation, audit |
| Thường cần báo cáo tổng hợp không? | Xem xét tổng hợp theo currency/dimension, batch và thời điểm tỷ giá |

Đừng chỉ so sánh tốc độ phép nhân: hãy đo **end-to-end latency**, p95/p99, số query, contention, lỗi rounding và quy mô dữ liệu. Những phép tính sai ngữ nghĩa đôi khi rất nhanh nhưng không có giá trị đối với hệ thống.

## 19. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Dùng `double` cho tiền | Sai số nhị phân, khó đối soát | `BigDecimal` hoặc minor units nguyên có hợp đồng |
| Lưu `100` nhưng không lưu currency | Không biết 100 đơn vị tiền nào | Money = amount + currency |
| Mặc định mọi currency có 2 chữ số lẻ | Sai với JPY, VND và những loại tiền khác | Kiểm tra quy tắc minor units theo currency |
| Lưu `quantity=2500` nhưng không có unit | Không biết là 2500 g hay kg | Unit đi cùng value hoặc cột canonical nêu rõ đơn vị |
| Cộng hai lượng khác dimension | Kết quả vô nghĩa | Kiểm tra dimension và quy đổi trước khi cộng |
| Nhân giá/kg trực tiếp với số gram | Sai lệch 1.000 lần | Chuyển quantity về đúng đơn vị giá |
| Trộn `15` và `0.15` cho tỷ lệ 15% | Sai lệch 100 lần | Kiểu tên trường/tỷ lệ nhất quán |
| Làm tròn ở mọi bước | Phát sinh sai khác hóa đơn | Quy định rõ rounding mode và điểm làm tròn |
| Quy đổi tiền theo tỷ giá mới khi đối soát đơn cũ | Sai lịch sử giao dịch | Lưu rate, thời điểm, nguồn, kết quả đã chốt |
| Dùng `NULL` và `0` như nhau | Biến “chưa đo” thành “đo được 0” | Mô hình trạng thái chưa biết/chưa áp dụng |
| Sắp xếp mọi amount khác currency cùng nhau | Báo cáo tổng hợp sai | Lọc theo currency hoặc quy đổi có kiểm soát |
| Dùng metadata unit chưa rõ phiên bản khi restore | Không tái diễn giải đúng dữ liệu cũ | Quản lý tham chiếu và policy version |

## 20. Bài tập vận dụng

### Bài tập 1: Chọn biểu diễn đúng

Xét các trường dữ liệu `productPrice = 19.99`, `stock = 500`, `temperature = 25` và `discount = 10`. Hãy bổ sung type, currency/unit, ngữ nghĩa miền giá trị, scale và quy tắc làm tròn hoặc cập nhật thích hợp.

**Gợi ý:** Một giá bán cần Money (currency rõ); stock có thể là số chiếc nguyên hoặc Quantity khối lượng; nhiệt độ cần thang; discount phải nêu `10%` hay `0.10 ratio`.

### Bài tập 2: Tính đơn giá theo khối lượng

Khách mua `2.500 g` hàng, đơn giá `12.50 USD/kg`. Hãy tính subtotal trước thuế và giải thích vì sao phải quy đổi đơn vị trước khi nhân.

**Gợi ý đáp án:** `2.500 g = 2,5 kg`; subtotal `2,5 × 12,50 = 31,25 USD`. Nếu nhân trực tiếp 2.500 × 12,50 thì đã coi g như kg, tạo kết quả sai 1.000 lần.

### Bài tập 3: So sánh BigDecimal

Giải thích vì sao `new BigDecimal("10.0").equals(new BigDecimal("10.00"))` trả `false`, còn `compareTo` trả 0. Bạn sẽ định nghĩa uniqueness của giá bán trong database ra sao khi không quan tâm scale đầu vào?

**Gợi ý:** Numeric value bằng nhau nhưng scale khác. Định nghĩa scale canonical cho giá và dùng ràng buộc/kiểu NUMERIC phù hợp tại database khi cần.

### Bài tập 4: Dữ liệu thiếu ngữ nghĩa

Một bảng chứa `amount DECIMAL(18,2)` và `currency_code` nhưng ứng dụng thực hiện `SUM(amount)` trên mọi bản ghi. Hãy đề xuất cách sửa truy vấn/báo cáo khi có cả USD và VND, đồng thời cho biết thông tin cần lưu nếu muốn tổng quy đổi.

**Gợi ý:** Nhóm theo `currency_code`, hoặc quy đổi từng khoản theo quy tắc tỷ giá và mốc thời gian được thống nhất. Lưu nguồn, rate, thời điểm và chính sách làm tròn để kiểm toán.

### Bài tập 5: Thay đổi mô hình dữ liệu

Ứng dụng cũ lưu tồn kho theo số chiếc nguyên, ứng dụng mới hỗ trợ kg và g. Hãy lập kế hoạch migration không làm mất ý nghĩa của các bản ghi cũ; nêu tình huống nào cần giữ cả giá trị nhập gốc và giá trị chuẩn.

**Gợi ý:** Xác minh ngữ nghĩa cũ, thêm unit và decimal, backfill theo quy tắc rõ ràng, cập nhật reader/writer, kiểm tra index/truy vấn và giữ nguồn đo khi phải audit độ chính xác.

## 21. Checklist trước khi lưu giá trị có ngữ nghĩa

- [ ] Trị số đi kèm loại tiền, đơn vị đo hoặc mã phân loại thích hợp.
- [ ] Đã xác định dùng `BigDecimal`/`NUMERIC` hay minor units nguyên và kiểm soát giới hạn kiểu.
- [ ] Không dùng số thực nhị phân cho các phép tính tiền cần chính xác thập phân.
- [ ] Scale, precision, rounding mode và thời điểm làm tròn được quy định theo nghiệp vụ.
- [ ] Các phép cộng/trừ/so sánh kiểm tra cùng currency hoặc dimension.
- [ ] Đơn giá nêu rõ **tiền trên đơn vị nào**; quantity được quy đổi trước khi nhân.
- [ ] Tỷ giá có hướng, mốc hiệu lực, nguồn và chính sách làm tròn.
- [ ] Schema có ràng buộc không âm, mã unit/currency hợp lệ và giới hạn theo từng trường.
- [ ] API định nghĩa rõ biểu diễn decimal và phân biệt zero với unknown/null.
- [ ] Query, index và báo cáo không trộn giá trị khác tiền tệ/đơn vị một cách vô nghĩa.
- [ ] Transaction và kiểm soát đồng thời bảo vệ việc ghi quan trọng.
- [ ] Dữ liệu lịch sử có thể truy vết về đơn vị gốc, tỷ giá và phiên bản quy tắc khi cần.
- [ ] Migration, backup và restore phục hồi được cả **giá trị lẫn cách diễn giải**.

## 22. Ghi nhớ

**Một con số không tự mang ý nghĩa của nó.** Đối với tiền, phải biết cả amount và currency. Đối với số đo, phải biết quantity, unit và dimension. Đối với tỷ lệ, tỷ giá hoặc giá trị có ngữ cảnh, phải quy định thêm hướng, thời điểm, nguồn và quy tắc diễn giải khi cần.

Trong Java, `BigDecimal` cùng các value object giúp bảo vệ phép toán ngay ở domain. Ở tầng persistence, schema, ràng buộc, transaction, query, index và kế hoạch khôi phục phải duy trì những ý nghĩa đó qua nhiều lần ghi, đọc và nâng cấp. **Lưu bền vững một giá trị chỉ có ích khi hệ thống tiếp tục hiểu đúng nó trong suốt vòng đời dữ liệu.**
