# Vì sao đổi ký hiệu hoặc mã tiền không thực hiện quy đổi giá trị trong Java

## 1. Bài toán: cùng một con số nhưng hai loại tiền

Giả sử ứng dụng có một hóa đơn **100,00 USD**. Khi chuyển ngôn ngữ hoặc khu vực hiển thị, giao diện có thể dùng cách viết khác, chẳng hạn đổi vị trí ký hiệu, cách phân nhóm chữ số hay dấu thập phân. Nhưng **đổi cách viết không biến 100 USD thành 100 EUR**.

Một lỗi nguy hiểm là lấy formatter tiền tệ đang hiển thị USD, gọi `setCurrency(EUR)`, thấy chữ “€” xuất hiện rồi kết luận rằng hệ thống đã quy đổi. Giá trị số gốc vẫn là 100; không có tỷ giá nào được truy xuất hay phép nhân/chia nào được thực hiện.

Ba khái niệm phải giữ độc lập:

1. **Amount (số tiền):** giá trị có thể tính toán, thường biểu diễn bằng `BigDecimal`, ví dụ `100.00`.
2. **Currency (đơn vị tiền):** loại tiền mà giá trị đang biểu thị, ví dụ `USD` hoặc `EUR`, thường biểu diễn bằng `java.util.Currency` và mã ISO 4217.
3. **Presentation (cách trình bày):** người dùng muốn nhìn số tiền như thế nào, ví dụ dạng ký hiệu `$`, `US$`, `€` hoặc mã `USD` tùy locale và formatter.

**Quy đổi tiền (foreign-exchange conversion)** là một hành động nghiệp vụ riêng: nó cần biết loại tiền nguồn, loại tiền đích, tỷ giá đúng chiều, thời điểm báo giá, chính sách làm tròn và có thể cả phí. `Currency`, `Locale` và `NumberFormat` **không cung cấp tỷ giá hối đoái**.

### Mục tiêu

Sau bài này, bạn có thể giải thích vì sao `NumberFormat.setCurrency` và `Currency.getSymbol` chỉ ảnh hưởng thông tin biểu diễn; viết mô hình số tiền có đủ amount + currency; thực hiện phép quy đổi rõ điều kiện bằng `BigDecimal`; xử lý fraction digits, rounding, locale và API contract; và tránh nhầm chuỗi đã format với số tiền thực.

## 2. Đổi nhãn không làm đổi đại lượng

Hãy tưởng tượng một nhãn chai ghi **1 lít**. Nếu thay chữ “lít” bằng “gallon” nhưng **không đổi con số 1**, ta tạo ra một nhãn sai, chứ không chuyển đơn vị. Với tiền cũng vậy:

```text
GIÁ TRỊ GỐC                     THAO TÁC                    KẾT QUẢ
100.00 USD
    |
    +-- Đổi Locale hiển thị ------------------------> "100,00 ..." 
    |                                                (cách viết đổi)
    |
    +-- Đổi symbol / Currency trong formatter ------> "€100.00" 
    |                                                (số vẫn 100.00)
    |
    +-- Quy đổi bằng tỷ giá 0.9150 EUR / USD -------> 91.50 EUR
                                                     (giá trị đã tính lại)
```

Các chuỗi trong sơ đồ chỉ minh họa **ý nghĩa**, không định nghĩa chính xác dấu cách/ký hiệu của mọi locale và bản JDK.

Một đối tượng `Currency` mô tả **một loại tiền**, không mô tả một “khoản tiền có giá trị”. Ví dụ `Currency.getInstance("USD")` biết mã `USD`, tên/biểu tượng theo locale và số chữ số thập phân mặc định của tiền tệ; nó không biết “100 USD bằng bao nhiêu EUR hôm nay”.

Tương tự, `Locale.FRANCE` có thể khiến một currency formatter mặc định chọn EUR và cách viết của Pháp; nhưng từ đó không suy ra một số tiền USD trong hệ thống đã được đổi thành EUR. **Locale của người xem không phải đồng tiền của giao dịch.**

## 3. Phân biệt các API Java thường gây hiểu nhầm

| API / thao tác | Nó làm gì? | Có quy đổi số tiền không? |
| --- | --- | --- |
| `Currency.getInstance("USD")` | Lấy đối tượng mô tả đơn vị tiền USD | **Không** |
| `currency.getCurrencyCode()` | Lấy mã ISO 4217, ví dụ `USD` | **Không** |
| `currency.getSymbol(locale)` | Lấy ký hiệu tiền tệ phù hợp locale | **Không** |
| `currency.getDisplayName(locale)` | Lấy tên đơn vị tiền theo ngôn ngữ của locale | **Không** |
| `Currency.getInstance(locale)` | Suy loại tiền mặc định gắn với lãnh thổ (khi có) | **Không** |
| `NumberFormat.getCurrencyInstance(locale)` | Tạo formatter tiền với quy ước locale | **Không** |
| `numberFormat.setCurrency(otherCurrency)` | Thay Currency được formatter sử dụng | **Không** |
| `numberFormat.format(amount)` | Biến số thành **chuỗi** hiển thị | **Không** |
| `amount.multiply(rate)` | Thực hiện phép nhân số học | **Có thể là bước quy đổi**, nếu rate đúng chiều và có policy nghiệp vụ |

### 3.1. `Currency` là metadata về đơn vị

`java.util.Currency` là lớp mô tả tiền tệ. Những phương thức đáng nhớ:

```java
import java.util.Currency;
import java.util.Locale;

Currency usd = Currency.getInstance("USD");
Currency eur = Currency.getInstance("EUR");

System.out.println(usd.getCurrencyCode());       // USD
System.out.println(eur.getCurrencyCode());       // EUR
System.out.println(usd.getDefaultFractionDigits()); // 2
System.out.println(usd.getSymbol(Locale.US));    // Ký hiệu theo Locale.US
```

Đây là **đoạn mã minh họa** nằm trong method; các comment chỉ diễn giải giá trị. `getDefaultFractionDigits()` cho biết số chữ số thập phân thông thường theo đơn vị tiền (ví dụ USD và EUR thường là 2, JPY là 0). Nó không nói tỷ giá hoặc bao nhiêu đơn vị tiền nguồn cần để mua một đơn vị tiền đích. Với một số mã đặc biệt, kết quả có thể là `-1`, nên cần kiểm tra trước khi dùng để đặt scale.

Ký hiệu không phải định danh duy nhất: dấu `$` được nhiều loại tiền sử dụng. Locale có thể trả ký hiệu khác như `US$` để phân biệt. Mã `USD` hoặc `CAD` thường thích hợp hơn cho **lưu trữ/API**, còn ký hiệu phù hợp hơn cho **hiển thị**.

### 3.2. `Locale` không phải tỷ giá

`Locale.forLanguageTag("vi-VN")` mô tả ngôn ngữ/vùng để định dạng và dịch thông điệp. Một người dùng ở Việt Nam vẫn có thể xem giao dịch USD hoặc JPY; một người dùng tiếng Anh có thể trả bằng VND. Múi giờ, địa chỉ, quốc gia cư trú và loại tiền thanh toán cũng không được tự suy duy nhất từ locale.

Có thể dùng `Currency.getInstance(Locale.US)` để lấy đơn vị tiền mặc định gắn với lãnh thổ Hoa Kỳ; điều đó **không biến tất cả giao dịch xem bằng `Locale.US` thành USD**. Với locale không có quốc gia hoặc lãnh thổ không có đơn vị tiền phù hợp, việc lấy currency theo locale cần xử lý ngoại lệ/kết quả không có tiền tệ tương ứng, không được mặc định luôn thành công.

### 3.3. `NumberFormat.setCurrency` không làm phép toán

Với `NumberFormat.getCurrencyInstance(locale)`, `setCurrency(currency)` cấu hình currency của formatter để tạo chuỗi. Nó **không nhận tỷ giá**, **không biết tiền nguồn của số**, và **không sửa biến `BigDecimal`** đang được format.

Một điểm tinh vi trong Java: `NumberFormat.setCurrency` **không tự điều chỉnh** `minimumFractionDigits` và `maximumFractionDigits` của formatter. Khi đổi từ tiền thường có 2 chữ số thập phân sang tiền thường không có phần lẻ như JPY, phải chủ động cấu hình precision phù hợp hoặc tạo formatter với chính sách đúng, không dựa vào `setCurrency` để “sửa hết”.

## 4. Ví dụ Java 17: thay ký hiệu nhưng số gốc giữ nguyên

Tệp `CurrencyLabelDemo.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyLabelDemo {
    record Money(BigDecimal amount, Currency currency) {}

    public static void main(String[] args) {
        Money original = new Money(
                new BigDecimal("100.00"),
                Currency.getInstance("USD"));

        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(Locale.US);

        formatter.setCurrency(original.currency());
        String asUsd = formatter.format(original.amount());

        // Chỉ đổi Currency của formatter; KHÔNG đổi Money.
        formatter.setCurrency(Currency.getInstance("EUR"));
        String asEurLabel = formatter.format(original.amount());

        System.out.println("amount=" +
                original.amount().toPlainString());
        System.out.println("moneyCurrency=" +
                original.currency().getCurrencyCode());
        System.out.println("formatterCurrency=" +
                formatter.getCurrency().getCurrencyCode());
        System.out.println("sameAmount=" +
                original.amount().equals(new BigDecimal("100.00")));

        System.out.println("before=" + asUsd);
        System.out.println("after=" + asEurLabel);
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 CurrencyLabelDemo.java
java CurrencyLabelDemo
```

**Bốn dòng đầu có kết quả chính xác:**

```text
amount=100.00
moneyCurrency=USD
formatterCurrency=EUR
sameAmount=true
```

Với dữ liệu locale thông dụng của `Locale.US`, hai dòng tiếp theo thường hiển thị kiểu:

```text
before=$100.00
after=€100.00
```

Dấu/khoảng trắng/ký hiệu hiển thị là dữ liệu locale có thể khác giữa các provider, vendor và phiên bản JDK; hai dòng này là ví dụ điển hình, **không phải contract chuỗi cho mọi môi trường**.

Đây chính là một tình huống **nguy hiểm**: dòng `after` hiển thị ký hiệu EUR đi với số `100.00`, nhưng object `original` vẫn có đơn vị **USD**. Nếu đưa chuỗi này tới người dùng như “100 EUR” mà không quy đổi, ứng dụng đã gắn **nhãn sai lên một giá trị**. `setCurrency` không biến `100 USD` thành `100 EUR`, cũng không tạo một object `Money` mới với loại tiền hợp lệ.

Nguyên tắc thực hành: **Đừng thay currency trong formatter để mô phỏng chức năng “Chuyển sang EUR”.** Formatter phải nhận đúng currency của *số tiền sau khi tính toán nghiệp vụ*.

## 5. Quy đổi thật cần những thành phần nào?

Quy đổi từ USD sang EUR có thể được mô tả bằng phép toán:

\[
\text{amount}_{EUR} = \text{amount}_{USD} \times
    \left(\frac{\text{EUR}}{\text{USD}}\right)
\]

Trong đó tỷ giá phải được định nghĩa **theo đúng chiều**. Ví dụ tỷ giá `0.9150 EUR per 1 USD` có nghĩa là mỗi 1 USD được quy đổi thành 0,9150 EUR (trước phí và làm tròn). Số tiền 100,00 USD sẽ thành:

\[
100.00 \times 0.9150 = 91.500000
\]

Nếu chính sách làm tròn cho EUR là 2 chữ số thập phân, kết quả lưu/chi trả trong ví dụ là **91.50 EUR**.

**Tỷ giá 0.9150 chỉ là dữ liệu giả định phục vụ học tập**, không phải tỷ giá thị trường được kiểm chứng, tỷ giá hiện hành hay lời khuyên giao dịch. Trong sản phẩm thực tế phải lấy báo giá từ nguồn đã được phê duyệt, gắn thời điểm và xác định tính hợp lệ của báo giá.

Một phép quy đổi hoàn chỉnh thường cần:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Số tiền nguồn | `100.00` | Giá trị cần đổi |
| Loại tiền nguồn (base) | `USD` | Đơn vị của amount nguồn |
| Loại tiền đích (quote/counter) | `EUR` | Đơn vị của kết quả |
| Tỷ giá có hướng | `0.9150 EUR/USD` | Số EUR trên mỗi USD |
| Thời điểm báo giá | `2026-10-28T00:00:00Z` | Báo giá có hiệu lực lúc nào |
| Precision và rounding | `scale=2, HALF_EVEN` | Quy tắc làm tròn tiền đích trong ví dụ |
| Phí, spread, thuế (nếu có) | Theo hợp đồng | Phải có quy tắc riêng, không do formatter tính |

Nếu tỷ giá được định nghĩa theo chiều ngược, ví dụ `USD per EUR`, không được nhân một cách máy móc: cần đảo chiều bằng phép chia thích hợp và quy định precision/rounding cho phép toán đó. Ngay cả tỷ giá nghịch đảo toán học cũng có thể **không phải tỷ giá giao dịch thực tế** vì mua/bán có spread và phí.

## 6. Ví dụ Java 17: tính số tiền mới bằng BigDecimal

Tệp `FxConversionDemo.java` sau tạo **một kết quả mới** thay vì chỉ đổi label. Nó sử dụng tỷ giá giả định, xác minh cặp tiền tệ, thực hiện phép nhân với `BigDecimal` và quy định rounding cho số tiền đích.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.Currency;

public class FxConversionDemo {
    record Money(BigDecimal amount, Currency currency) {}

    record Quote(
            Currency baseCurrency,
            Currency counterCurrency,
            BigDecimal counterPerBase,
            Instant asOf
    ) {}

    static Money convert(
            Money source, Quote quote, Currency target) {

        if (!source.currency().equals(quote.baseCurrency())
                || !target.equals(quote.counterCurrency())) {
            throw new IllegalArgumentException("Wrong FX pair");
        }

        BigDecimal rawTarget =
                source.amount().multiply(quote.counterPerBase());

        int digits = target.getDefaultFractionDigits();
        if (digits < 0) {
            throw new IllegalArgumentException(
                    "Currency minor-unit policy required");
        }

        BigDecimal rounded =
                rawTarget.setScale(digits, RoundingMode.HALF_EVEN);

        return new Money(rounded, target);
    }

    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        Currency eur = Currency.getInstance("EUR");

        Money source = new Money(new BigDecimal("100.00"), usd);

        // Chỉ là TỶ GIÁ GIẢ ĐỊNH cho bài học.
        Quote quote = new Quote(
                usd,
                eur,
                new BigDecimal("0.9150"),
                Instant.parse("2026-10-28T00:00:00Z"));

        Money target = convert(source, quote, eur);

        System.out.println("source=" +
                source.amount().toPlainString() + " " +
                source.currency().getCurrencyCode());
        System.out.println("rate=" +
                quote.counterPerBase().toPlainString() +
                " EUR per USD");
        System.out.println("asOf=" + quote.asOf());
        System.out.println("target=" +
                target.amount().toPlainString() + " " +
                target.currency().getCurrencyCode());
        System.out.println("sourceUnchanged=" +
                source.amount().toPlainString() + " " +
                source.currency().getCurrencyCode());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 FxConversionDemo.java
java FxConversionDemo
```

**Stdout chính xác với JDK 17, currency USD/EUR và dữ liệu giả định trên:**

```text
source=100.00 USD
rate=0.9150 EUR per USD
asOf=2026-10-28T00:00:00Z
target=91.50 EUR
sourceUnchanged=100.00 USD
```

Điểm quan trọng:

1. `Money` luôn có **cả `BigDecimal` lẫn `Currency`**, không có trạng thái “100 nhưng chưa biết là USD hay EUR”.
2. `Quote` ghi rõ base, counter, chiều tỷ giá và thời điểm. Nhân với 0.9150 có nghĩa vì tỷ giá được định nghĩa là **EUR trên một USD**.
3. `convert` kiểm tra cặp tiền nhằm ngăn dùng nhầm tỷ giá `EUR→USD` cho giao dịch `USD→EUR`.
4. Kết quả là `new Money(91.50, EUR)`, khác `Money(100.00, USD)`. Đó mới là **quy đổi giá trị**.
5. `BigDecimal` tính số thập phân chính xác từ chuỗi; `setScale(2, HALF_EVEN)` là ví dụ **chính sách làm tròn nghiệp vụ**, không phải thứ gì `NumberFormat.format` tự quyết định thay doanh nghiệp.
6. Chương trình không truy cập internet, không dùng tỷ giá thật và **chưa bao gồm spread, phí, thuế hoặc báo giá hết hạn**.

Trong sản phẩm, chính sách scale có thể phụ thuộc phương thức thanh toán, quy định pháp lý, đơn vị tiền, ngân hàng và nghiệp vụ; `Currency.getDefaultFractionDigits()` là điểm tham khảo về số chữ số thông thường, không phải quy tắc thanh toán bao quát mọi trường hợp.

## 7. Vì sao BigDecimal quan trọng hơn double cho tiền?

Phép tính trong hệ nhị phân bằng `double` không biểu diễn chính xác nhiều số thập phân như 0.1 hoặc 0.2. Với phép quy đổi, tích lũy phí, cộng tổng giao dịch và làm tròn theo chính sách, sai số có thể ảnh hưởng kết quả.

**Ưu tiên:**

```java
BigDecimal amount = new BigDecimal("100.00");
BigDecimal rate = new BigDecimal("0.9150");
BigDecimal result = amount.multiply(rate);
```

Tránh khởi tạo `new BigDecimal(0.1)` khi mong muốn chính xác giá trị thập phân 0.1 vì constructor này nhận đúng xấp xỉ nhị phân của `double`. Nếu nguồn giá trị là chuỗi decimal có quy ước rõ hoặc cột DECIMAL trong DB, hãy bảo toàn dạng thập phân từ đầu.

`BigDecimal` còn có vấn đề scale:

- `new BigDecimal("1.0")` và `new BigDecimal("1.00")` có cùng giá trị số học, nhưng khác scale.
- `equals` xét cả giá trị và scale, trong khi `compareTo` so sánh giá trị số học.
- Khi chia `BigDecimal` để đảo tỷ giá, có thể gặp phép chia không có biểu diễn thập phân hữu hạn. Hãy truyền `MathContext` hoặc scale/`RoundingMode` phù hợp.
- Quy tắc làm tròn **sau phép quy đổi** khác quy tắc **làm tròn sau mỗi bước tính phí**; phải được quy định tường minh để tránh sai lệch.

`NumberFormat` có thể làm tròn **chuỗi hiển thị** mà không thay `BigDecimal` ban đầu. Không dùng chuỗi đã format hoặc parse lại text để làm nguồn chân lý cho số dư hay giao dịch.

## 8. Fraction digits: đổi currency không tự sửa toàn bộ formatter

Mỗi currency có số chữ số thập phân thông thường khác nhau. Ví dụ:

| Currency | `getDefaultFractionDigits()` điển hình | Ví dụ hiển thị |
| --- | ---: | --- |
| `USD` | 2 | `100.00` |
| `EUR` | 2 | `100.00` |
| `JPY` | 0 | `100` |
| `KWD` | 3 | `100.000` |

Bảng nói về **chữ số thập phân mặc định của currency**, không phải tỷ giá hoặc số tiền sau quy đổi. Ví dụ số thuần trong cột phải, chưa tính ký hiệu và quy tắc dấu của locale.

Một lỗi thường gặp:

```java
NumberFormat f = NumberFormat.getCurrencyInstance(Locale.US);
f.setCurrency(Currency.getInstance("JPY"));
// Không giả định f đã tự đặt fraction digits = 0.
```

Để chủ động định dạng theo đơn vị tiền đích:

```java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyDisplay {
    public static String show(
            java.math.BigDecimal amount,
            Currency currency,
            Locale displayLocale) {

        NumberFormat f =
                NumberFormat.getCurrencyInstance(displayLocale);

        f.setCurrency(currency);

        int digits = currency.getDefaultFractionDigits();
        if (digits >= 0) {
            f.setMinimumFractionDigits(digits);
            f.setMaximumFractionDigits(digits);
        }

        return f.format(amount);
    }
}
```

Đây là **lớp tiện ích có thể biên dịch trên Java 17**, không có `main`; cần gọi từ chương trình khác. Quy tắc `digits >= 0` tránh dùng giá trị đặc biệt `-1` như một scale không hợp lệ. Với hệ thống tài chính, chính sách fraction digits và rounding nên xác định cùng nghiệp vụ, không chỉ sao chép mặc định.

Hàm `show` định dạng **amount và currency được truyền vào**, chứ không tính số tiền đích. Muốn hiển thị kết quả quy đổi, trước tiên gọi phép tính `convert` ở tầng nghiệp vụ rồi mới gọi `show(target.amount(), target.currency(), locale)`. Ngược lại, hiển thị số nguồn với currency đích **mà chưa convert** tạo ra thông tin sai.

### Tại sao không đoán currency chỉ từ locale?

Một người dùng có `displayLocale=vi-VN` có thể có hóa đơn `100 USD`, `100 EUR` hoặc `100 VND`. Hàm `show` vẫn nhận cả `Currency` để không đánh đồng lựa chọn ngôn ngữ với đơn vị tiền. Formatter của `Locale.US` có thể hiển thị ký hiệu khác cho EUR, nhưng đó vẫn là **đơn vị do đối số `currency` quyết định**.

## 9. Cách trình bày sau khi quy đổi

Giả sử backend đã tạo hai thực thể:

```text
sourceMoney  = 100.00 USD
targetMoney  = 91.50 EUR
displayLocale = vi-VN
```

Một màn hình đúng có thể thể hiện:

```text
Số tiền gốc:        100,00 USD
Tỷ giá minh họa:    1 USD = 0,9150 EUR
Số tiền sau đổi:    91,50 EUR
Báo giá tại:        2026-10-28T00:00:00Z
```

Các cách viết trên là **minh họa nội dung người dùng**, không phải chuỗi output chắc chắn của `NumberFormat`/`DateTimeFormatter` ở mọi JDK. Locale có thể thay đổi ký hiệu, dấu cách và trật tự mã tiền. Ứng dụng nên dùng định dạng theo `Locale` và ghi rõ mã ISO 4217 khi ký hiệu dễ gây nhầm.

Nếu màn hình chỉ thay thành “€100.00” mà không hiển thị tỷ giá hoặc kết quả số học, đó là **không thực hiện quy đổi**. Không nên báo “Converted successfully” chỉ vì UI xuất hiện ký hiệu khác.

Một số thông tin khác nên có theo yêu cầu sản phẩm: tỷ giá mua/bán, phí, tổng khấu trừ, số tiền thực nhận, hạn hiệu lực báo giá, mã giao dịch và ghi chú rằng giá trị hiển thị là ước tính hay đã chốt.

## 10. Lưu trữ và API: số tiền là amount + currency

Để frontend và backend không phụ thuộc ngôn ngữ hay dấu phân nhóm, cần hợp đồng dữ liệu tường minh.

Ví dụ JSON dưới đây dùng **chuỗi decimal chuẩn** để giữ độ chính xác khi đi qua hệ thống không bảo toàn decimal một cách tự nhiên:

```json
{
  "source": {
    "amount": "100.00",
    "currency": "USD"
  },
  "quote": {
    "baseCurrency": "USD",
    "counterCurrency": "EUR",
    "counterPerBase": "0.9150",
    "asOf": "2026-10-28T00:00:00Z",
    "roundingMode": "HALF_EVEN"
  },
  "result": {
    "amount": "91.50",
    "currency": "EUR"
  }
}
```

Đây là **ví dụ contract**, không phải định dạng JSON do Java/Jackson tự sinh mặc định. Một API có thể dùng JSON number nếu đã quy định chính xác precision/scale và giới hạn của client; cách dùng chuỗi decimal thường có lợi khi cần tương tác với JavaScript hoặc hệ thống kế toán.

Không gửi giá trị máy cần tính toán ở dạng `"€91,50"` hoặc `"$100.00"` rồi yêu cầu backend đoán currency, dấu decimal hoặc số tiền thật từ văn bản. **Chuỗi hiển thị được tạo tại giao diện, không thay thế dữ liệu canonical.**

Với cơ sở dữ liệu, một bản ghi tiền thường gồm `DECIMAL/NUMERIC` có precision và scale được chọn đúng cùng currency code. Khi có quy đổi, tùy yêu cầu kiểm toán cần giữ cả tiền nguồn, tiền đích, quote/rate đã áp dụng, thời điểm và các khoản phí. **Không tự ghi đè số tiền nguồn thành số tiền đích** nếu nghiệp vụ cần truy vết.

## 11. Currency symbol và mã tiền không thay thế tỷ giá

### 11.1. Đổi ký hiệu

`currency.getSymbol(locale)` hoặc một formatter có thể cho ký hiệu `$`, `US$`, `€`, v.v. Đây chỉ là text đại diện cho đơn vị tiền. Nó có thể khác theo ngôn ngữ, thậm chí có trường hợp mã ISO được hiển thị thay ký hiệu.

**Không parse ký hiệu để tìm “mã tiền chuẩn”**: cùng ký hiệu `$` có thể dùng cho USD, CAD, AUD và những đồng tiền khác; người dùng có thể gõ ký hiệu không nhất quán với locale.

### 11.2. Đổi mã ISO 4217

Ngay cả khi chỉ đổi chuỗi `"USD"` thành `"EUR"` trong một DTO, hệ thống mới thay **đơn vị ghi nhãn**, chưa thay `amount`. Một đối tượng kiểu:

```json
{"amount":"100.00","currency":"EUR"}
```

có nghĩa là **100 EUR**, không phải “100 USD sẽ được quy đổi sang EUR sau”. Nếu ban đầu là 100 USD, sửa code mà giữ amount 100.00 khiến dữ liệu bị gán sai nghĩa.

Cần tạo **bản ghi kết quả mới** sau phép tính và chính sách làm tròn, đồng thời ghi được nguồn gốc của kết quả nếu cần.

### 11.3. Chọn locale khác cũng không phải đổi mã tiền

Chuyển `Locale.US` sang `Locale.FRANCE` có thể làm `NumberFormat.getCurrencyInstance(...)` chọn currency mặc định khác, nhưng không có phép nhân tỷ giá nào. Vì vậy, trong giao diện hiển thị nhiều loại tiền, hãy truyền **đúng Currency của amount** vào formatter và cấu hình fraction digits phù hợp.

## 12. Tỷ giá: chiều, thời điểm và sự thay đổi liên tục

Một tỷ giá chỉ có ý nghĩa khi được gắn với **cặp tiền** và **chiều**. Ví dụ:

```text
quote:
  base = USD
  counter = EUR
  rate = 0.9150 EUR / 1 USD
```

Nếu nguồn là 100 USD, phép toán là `100 × 0.9150 = 91.50 EUR`. Nếu nguồn là EUR và cần USD, không được dùng phép nhân giống hệt: phải lấy một quote cho chiều EUR→USD hoặc dùng phép đảo tỷ giá **theo quy tắc nghiệp vụ**, có precision và rounding phù hợp. Tỷ giá mua/bán không nhất thiết là nghịch đảo chính xác.

Tỷ giá còn có tính thời điểm. Một giá trị `0.9150` không thể được coi là “mãi mãi đúng”. Phải nêu đó là giá tại lúc nào, nguồn nào, còn hiệu lực hay không, và loại tỷ giá nào (tham chiếu, mua, bán, giao dịch đã khóa).

**Không tự biến formatter thành dịch vụ tỷ giá.** `Currency` trong JDK không lấy giá thị trường, `NumberFormat` không kết nối nguồn báo giá và `Locale` không cung cấp ngày/giờ hiệu lực FX.

## 13. Các vấn đề làm tròn trong nghiệp vụ

Việc làm tròn một giá trị trong UI khác với việc xác định khoản tiền hợp lệ để thanh toán:

- `NumberFormat.setMaximumFractionDigits(2)` giới hạn **chuỗi hiển thị**, không cập nhật `BigDecimal` gốc.
- `BigDecimal.setScale(2, RoundingMode.HALF_EVEN)` tạo **giá trị thập phân đã làm tròn** theo một chính sách rõ.
- `Currency.getDefaultFractionDigits()` cho thông tin chữ số thập phân thông thường; một số giao dịch tiền mặt có quy tắc làm tròn bội số riêng, ví dụ 0,05 đơn vị, không thể suy chỉ từ scale.
- Phí giao dịch và spread có thể được áp dụng trước hoặc sau conversion; thứ tự và thời điểm làm tròn phải được cố định bằng contract.
- Tùy sản phẩm, số tiền hiển thị “ước tính” có thể khác số tiền được chốt khi báo giá hết hạn; phải phân biệt hai loại.
- Hạn chế việc nhân/chia nhiều bước rồi làm tròn tùy tiện ở từng bước, vì các kết quả khác nhau có thể xuất hiện dù cùng một tỷ giá đầu vào.

`RoundingMode.UNNECESSARY` có thể dùng để phát hiện phép làm tròn không được phép khi giá trị có phần dư, nhưng thường sẽ ném `ArithmeticException` nếu dữ liệu yêu cầu làm tròn; chọn nó chỉ khi contract thực sự yêu cầu tính chính xác tuyệt đối ở scale đó.

## 14. Thiết kế Java để hạn chế gắn nhãn sai

Nếu chỉ lưu `BigDecimal amount` mà không lưu `Currency`, code dễ gắn nhầm formatter của quốc gia khác cho khoản tiền. Nên biểu diễn rõ:

```java
record Money(BigDecimal amount, Currency currency) {}
```

Đây là khai báo record có thể đặt ở cấp package hoặc trong một class, không phải chương trình độc lập. Khi tạo object, cần bảo đảm `amount` và `currency` được kiểm tra không `null` nếu nghiệp vụ yêu cầu. Java record chỉ là cấu trúc lưu dữ liệu; nó **không tự thực hiện** bất kỳ phép conversion nào.

Một dịch vụ nên có API nghiệp vụ rõ nghĩa:

```text
convert(sourceMoney, quote, targetCurrency)
    → Money(amountAfterRateAndRounding, targetCurrency)

format(money, displayLocale)
    → String localizedLabel
```

Không nên có API mơ hồ:

```text
changeCurrency(sourceMoney, "EUR")
    → ???
```

Tên `changeCurrency` có thể bị hiểu là sửa nhãn hoặc thực hiện quy đổi. Nếu sản phẩm có một nghiệp vụ đổi tiền, nên đặt tên rõ như `convertCurrency`, kiểm soát dữ liệu quote và trả một object kết quả khác.

### NumberFormat trong ứng dụng đa người dùng

`NumberFormat` mutable và không mặc nhiên an toàn khi nhiều luồng sử dụng đồng thời. Trên Java server, nên tạo instance riêng theo request/locale hoặc quản lý cache an toàn; không để hai request cùng gọi `setCurrency` trên một formatter global rồi hiển thị nhầm USD/EUR cho người khác.

Không gọi `Locale.setDefault` để lựa chọn vùng cho từng request. Locale mặc định là trạng thái JVM, có thể làm thay đổi cách định dạng của request khác.

## 15. Những sai lầm dễ xảy ra

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Gọi `setCurrency(EUR)` trên formatter USD và xem đó là quy đổi | 100 USD có thể bị hiển thị thành 100 EUR | Tính `amount × rate` rồi tạo `Money` mới |
| Đổi trường `currency` trong DTO mà giữ nguyên amount | Dữ liệu bị gắn sai đơn vị | Chỉ đổi currency cùng phép tính nghiệp vụ |
| Suy tiền thanh toán từ `Locale.getDefault()` | Cùng giao dịch có thể thành loại tiền khác khi deploy | Lưu currency trong dữ liệu giao dịch |
| Dùng ký hiệu `$` làm mã tiền | Mơ hồ giữa nhiều currency | Dùng mã ISO 4217 |
| Dùng `double` cho giá trị tiền cần chính xác thập phân | Sai số nhị phân và làm tròn khó kiểm soát | Dùng `BigDecimal` từ chuỗi decimal |
| Nhân rate sai chiều | Sai số tiền đích | Quote ghi base/counter và đơn vị của tỷ giá |
| Dùng tỷ giá không có thời điểm | Khó truy vết và có thể đã hết hạn | Ghi nguồn và thời điểm báo giá |
| Chỉ dùng `setCurrency(JPY)` và tin formatter tự đổi fraction digits | Hiển thị sai precision | Đặt min/max fraction digits theo policy |
| Parse lại chuỗi `"€91,50"` để lưu tiền | Phụ thuộc locale và có thể mất chính xác | Truyền số và currency theo contract canonical |
| So sánh hai chuỗi format để so giá trị | Hậu tố, dấu và rounding có thể khác | So sánh giá trị Money cùng đơn vị hoặc quy đổi có kiểm soát |
| Dùng rate giả định làm tỷ giá hiện hành | Gây hiểu nhầm tính hợp lệ của giao dịch | Ghi rõ quote và xác minh nguồn thực tế |
| Chia sẻ một formatter mutable cho nhiều request | Rủi ro đổi nhãn tiền giữa các request | Formatter riêng hoặc cơ chế an toàn luồng |

## 16. Kiểm thử cần kiểm tra cả số học lẫn hiển thị

Nên có **hai nhóm test độc lập**.

### Nhóm A — xác minh conversion là phép toán có contract

1. Khi source là `Money(100.00, USD)` và quote `0.9150 EUR per USD`, result phải là `Money(91.50, EUR)` với `HALF_EVEN`/scale 2.
2. Source không bị thay đổi; quote không bị thay đổi.
3. Nếu source là EUR nhưng quote base là USD, phải từ chối thay vì âm thầm nhân tỷ giá sai chiều.
4. Phải kiểm tra các ranh giới như amount bằng 0, âm (nếu hỗ trợ refund), số rất lớn, rate bằng 0/âm hoặc quote hết hạn theo policy.
5. Với tiền không có hai chữ số thập phân mặc định, phải dùng đúng scale/rounding của nghiệp vụ.
6. Phải kiểm tra phép quy đổi hai chiều, phí và spread theo công thức thực tế; đừng giả định đổi đi đổi về chắc chắn giữ nguyên lượng tiền do làm tròn và chênh lệch tỷ giá.

### Nhóm B — xác minh formatter chỉ trình bày

1. `NumberFormat.getCurrencyInstance(Locale.US)` và `getCurrencyInstance(Locale.FRANCE)` có thể biểu diễn khác nhau, nhưng object `Money` ban đầu không đổi.
2. `setCurrency(EUR)` thay Currency của formatter, **không** đổi `Money.amount()` hoặc `Money.currency()`.
3. Format cùng `Money` ở hai locale không được làm thay đổi tỷ giá hoặc currency code trong domain.
4. Không chốt toàn bộ chuỗi Unicode của nhiều locale mà không pin JDK/CLDR/provider; có thể có khoảng trắng không ngắt dòng, ký hiệu và dấu khác.
5. Với formatter dùng chung trong service nhiều luồng, có test concurrency hoặc thiết kế tách instance để tránh trộn cấu hình.
6. UI nên hiển thị đúng tên/mã tiền nếu ký hiệu có thể mơ hồ.

### Bài tập tự kiểm tra

**Câu 1.** Có `amount=100.00`, `currency=USD`. Sau khi gọi `formatter.setCurrency(EUR)`, amount bằng bao nhiêu?

**Đáp án:** Vẫn 100.00, nếu không có phép toán nào khác. Chuỗi có thể chứa ký hiệu EUR nhưng **đây không phải 100 EUR đã được quy đổi**.

**Câu 2.** Cho tỷ giá giả định `0.9150 EUR per USD`, đổi 100.00 USD trước phí ra EUR là bao nhiêu?

**Đáp án:** 91.500000 EUR trước làm tròn theo scale, thường thể hiện 91.50 EUR với scale 2 và policy đã định.

**Câu 3.** Một người dùng `vi-VN` mua sản phẩm giá 50 USD. Đổi locale hiển thị thành `en-US` có nghĩa đổi đồng tiền thanh toán thành USD không?

**Đáp án:** Không; giao dịch vốn đã là USD. Chỉ quy ước trình bày có thể đổi. Nếu ban đầu bằng VND, đổi locale cũng không tự tạo USD.

**Câu 4.** `Currency.getSymbol(Locale.US)` có thể dùng để xác định duy nhất mã ISO 4217 cho bất kỳ ký hiệu `$` nào không?

**Đáp án:** Không; nhiều currency có thể chia sẻ ký hiệu. Lưu và truyền currency code riêng.

**Câu 5.** Vì sao cặp tiền và chiều tỷ giá phải được lưu cùng con số `0.9150`?

**Đáp án:** Vì `0.9150 EUR/USD` có nghĩa khác `0.9150 USD/EUR`; phép nhân/chia và kết quả khác nhau. Cần cả thời điểm hiệu lực và chính sách xử lý phí/làm tròn.

**Câu 6.** `NumberFormat.setCurrency(JPY)` có bảo đảm formatter hiển thị đúng 0 chữ số thập phân khi trước đó được tạo cho USD không?

**Đáp án:** Không; `setCurrency` không tự thay đổi minimum/maximum fraction digits. Cần cấu hình theo loại tiền đích hoặc policy ứng dụng.

## 17. Ghi nhớ

- **`Currency` là metadata đơn vị; `Locale` là bối cảnh trình bày; `NumberFormat` tạo chuỗi. Không thành phần nào trong ba thành phần này tự cung cấp hoặc áp dụng tỷ giá.**
- Thay `$` thành `€` hoặc mã `USD` thành `EUR` mà giữ nguyên amount là **đổi nhãn**, không phải quy đổi.
- Quy đổi đúng cần **amount nguồn + currency nguồn + currency đích + tỷ giá có hướng + thời điểm + rounding/fees policy**.
- **`BigDecimal`** phù hợp tính toán tiền theo thập phân; **`NumberFormat`** phù hợp định dạng cho người dùng. Không dùng chuỗi đã format thay số tiền canonical.
- Kết quả quy đổi phải là **giá trị mới đi cùng đơn vị mới**; object nguồn và lịch sử báo giá nên được giữ nếu nghiệp vụ cần.
- Gửi API/DB bằng amount và mã currency rõ ràng; format theo locale khi hiển thị.
- Với giao dịch thật, tỷ giá trong tài liệu là ví dụ, không phải giá thị trường. Hãy dùng quote được phê duyệt và lưu khả năng truy vết.

**Tài liệu Java SE 17 chính thức:**

- [`Currency` — java.util.Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html)
- [`NumberFormat` — java.text.NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [`BigDecimal` — java.math.BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
