# Kiểm thử số thập phân, phần trăm, tiền tệ và phân tích toàn chuỗi trong Java

## 1. Vì sao ba loại định dạng số cần bộ kiểm thử riêng?

Trong Java Core Localization, cùng một đại lượng số có thể đi qua ba cách trình bày khác nhau:

- **Số thập phân thường:** `1234.50` có thể được hiển thị `1,234.50` ở `en-US`, `1.234,50` ở `de-DE`.
- **Phần trăm:** tỷ lệ domain `0.125` có thể được hiển thị `12.5%`; dấu `%` và cách đặt khoảng trắng tùy locale.
- **Tiền tệ:** amount `1234.50` cộng currency code `USD` có thể hiển thị `$1,234.50`, `1.234,50 $` hoặc một cách biểu đạt khác theo locale.

Một bộ test chỉ kiểm tra `format(value)` tạo chuỗi "trông đúng" sẽ bỏ sót nhiều lỗi: parser nhận **một phần đầu chuỗi** rồi lờ phần sau, hai locale hiểu cùng dấu khác nhau, phần trăm bị nhân/chia 100 sai, amount bị làm tròn, currency bị suy từ ký hiệu mơ hồ, hoặc parser chấp nhận `NaN` trong field chỉ cho phép số hữu hạn.

Bài này thuộc nhóm **Kiểm thử và lỗi**. Trọng tâm là thiết kế kiểm thử có chủ đích cho **decimal / percentage / currency**, đặc biệt yêu cầu **phân tích toàn chuỗi (full-input consumption)**: chỉ chấp nhận input khi parser đọc hết chuỗi, không còn ký tự dư, giá trị có đúng kiểu và thỏa mãn quy tắc domain.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Tạo formatter/parser `NumberFormat` theo một `Locale` tường minh, chọn đúng loại decimal, percent hay currency.
2. Dùng `ParsePosition` để phân biệt **parse thành công một tiền tố** với **parse thành công toàn bộ chuỗi**.
3. Dùng `DecimalFormat.setParseBigDecimal(true)` để xử lý số decimal chính xác, đồng thời từ chối `NaN` và infinity cho trường nghiệp vụ không chấp nhận.
4. Hiểu phần trăm biểu diễn một **tỷ lệ**: `12.5%` là `0.125` trong mô hình thường gặp, không phải `12.5`.
5. Tách amount và ISO currency code khỏi ký hiệu tiền và tên tiền theo locale.
6. Viết ma trận test đủ positive, negative, boundary, Unicode whitespace, rounding, locale mismatch và input rác.
7. Phân biệt **đọc hết input** với **xác thực cú pháp/đúng nhóm dấu**: một chuỗi có thể được parser tiêu thụ hết nhưng vẫn không hợp chính sách nhập liệu.
8. Thiết kế test không nhầm sự khác biệt hợp lệ của dữ liệu CLDR/JDK với lỗi nghiệp vụ.

## 2. Tách bốn điều kiện chất lượng: format, parse, consumed và domain

Một input số không nên được coi là hợp lệ chỉ vì `NumberFormat.parse(...)` trả về `Number`.

Có **bốn lớp kiểm tra riêng**:

| Lớp | Câu hỏi | Ví dụ lỗi |
| --- | --- | --- |
| **Formatting** | Giá trị domain hiển thị đúng theo locale, currency, precision và rounding không? | `0.125` bị in `0.125%` thay vì `12.5%` |
| **Parsing** | Formatter đọc được chuỗi đầu vào thành một giá trị không? | Parser `en-US` không hiểu comma decimal của `de-DE` |
| **Full consumption** | Parser có tiêu thụ **tất cả** input không? | `"1,234.50oops"` chỉ đọc `"1,234.50"` |
| **Validation** | Input hợp chính sách cú pháp và domain không? | `"12,34.50"` có grouping sai nhưng có thể vẫn được parser chấp nhận |

Sau cùng mới đến **bảo toàn dữ liệu**: `format → parse` có giữ được giá trị số học, scale và kiểu ban đầu không? Nếu format làm tròn, câu trả lời có thể là **không**, dù cả bốn điều kiện trên đều thỏa.

### Một quy trình nhập liệu an toàn

```text
Raw input + locale nguồn + loại field
                |
        Giới hạn size/ký tự
                |
        Parser đúng loại field
                |
        ParsePosition: consumed hết?
                |
        Kiểu giá trị có hợp lệ?
                |
        Validation dấu nhóm, scale,
        range, đơn vị/currency?
                |
        Domain value có kiểu
                |
        Lưu theo schema canonical
```

Locale lấy từ **ngữ cảnh nguồn input**, không đoán từ `Locale.getDefault()` của JVM và không dựa vào ký tự trông giống dấu phẩy/dấu chấm. Nếu dữ liệu đến từ API machine-to-machine, nên dùng schema decimal canonical thay vì đi qua localized parser của UI.

## 3. Những factory Java cần chọn đúng

Java SE 17 cung cấp các phương thức:

| Loại field | Factory | Ví dụ domain | Ví dụ hiển thị en-US |
| --- | --- | --- | --- |
| Decimal | `NumberFormat.getNumberInstance(locale)` | `BigDecimal("1234.50")` | `1,234.50` |
| Percent | `NumberFormat.getPercentInstance(locale)` | Tỷ lệ `BigDecimal("0.125")` | `12.5%` nếu cho 1 chữ số phần lẻ |
| Currency | `NumberFormat.getCurrencyInstance(locale)` | `1234.50` + `USD` | `$1,234.50` |
| Integer | `NumberFormat.getIntegerInstance(locale)` | `1234` | `1,234` |

**Khác biệt quan trọng:** `getIntegerInstance` được cấu hình để parse phần nguyên, có thể dừng tại dấu thập phân. Không dùng nó để parse một trường decimal rồi mong đọc hết `"12.5"`.

Đối tượng trả về thường là `DecimalFormat` trên các locale/provider phổ biến nhưng `NumberFormat` là lớp trừu tượng và API factory không hứa mọi implementation luôn là `DecimalFormat`. Khi bài cần `setParseBigDecimal(true)`, kiểm tra kiểu trước khi ép:

```java
NumberFormat base = NumberFormat.getNumberInstance(locale);
if (!(base instanceof DecimalFormat decimal)) {
    throw new IllegalStateException("DecimalFormat required");
}
decimal.setParseBigDecimal(true);
```

Đây là đoạn code **minh họa trong phương thức**, cần import `java.text.*`. Không ép kiểu vô điều kiện trong một thư viện phải hỗ trợ mọi locale provider tùy chỉnh.

**Không dùng chung một `DecimalFormat` mutable** đang đổi currency, fraction digits hoặc pattern qua nhiều luồng. Test nên tạo instance mới; code sản xuất cũng cần lifecycle/đồng bộ phù hợp.

## 4. Ma trận kiểm thử tối thiểu

Không dồn tất cả loại số vào một test "format tốt". Mỗi cột là một giả định riêng cần được kiểm tra.

| Nhóm | Input/giá trị | Kết quả mong đợi |
| --- | --- | --- |
| Decimal `en-US` | `"1,234.50"` | Giá trị `1234.50`, consumed 100% |
| Decimal `de-DE` | `"1.234,50"` | Giá trị `1234.50`, consumed 100% |
| Locale mismatch | `"1.234,50"` parse `en-US` | Không được xác nhận là input hoàn chỉnh hợp lệ |
| Suffix rác | `"1,234.50oops"` | Không chấp nhận vì chỉ parse tiền tố |
| Grouping sai | `"12,34.50"` `en-US` | Từ chối nếu chính sách bắt buộc grouping chuẩn |
| Empty / khoảng trắng | `""`, `" "` | Xử lý theo chính sách input; không âm thầm coi là 0 |
| Percent | `"12.5%"` `en-US` | Ratio `0.125`, consumed 100% |
| Percent thiếu ký hiệu | `"12.5"` với percent parser | Không thành công theo pattern áp dụng |
| Percent suffix | `"12.5%extra"` | Không chấp nhận |
| Currency | `"$1,234.50"` `en-US` | Amount `1234.50` và currency `USD` theo **context** |
| Currency suffix | `"$1,234.50oops"` | Không chấp nhận |
| Currency khác ký hiệu | `"€1,234.50"` với USD formatter | Không coi là USD hợp lệ |
| Fraction precision | `1.239` hiển thị hai chữ số | Format làm tròn; không đòi parse trả `1.239` |
| Special numbers | `NaN`, infinity | Từ chối nếu domain chỉ chấp nhận decimal hữu hạn |
| Signed zero | `-0` | Định nghĩa rõ có cần bảo tồn dấu âm của zero không |
| Unicode whitespace | U+0020, U+00A0, U+202F | Test từng ký tự, không coi chúng giống nhau |
| CLDR upgrade | Cùng locale, JDK trước/sau | Tách thay đổi presentation với lỗi domain |

Dùng các locale thực của sản phẩm. `en-US` và `de-DE` là điểm khởi đầu tốt vì dấu nhóm/thập phân đổi vai trò; thêm `fr-FR` để phát hiện khoảng trắng Unicode và locale khác với hệ số chữ số không Latin khi có yêu cầu.

## 5. `ParsePosition`: yếu tố bắt buộc để xác nhận toàn chuỗi

`NumberFormat.parse(String, ParsePosition)` cố parse bắt đầu tại vị trí `ParsePosition.getIndex()`, sau đó cập nhật index đến nơi đã đọc. Phương thức có thể:

- Trả một `Number` và index **bằng chiều dài** input: parser đã đọc hết.
- Trả `Number` nhưng index **nhỏ hơn chiều dài**: chỉ đọc tiền tố.
- Trả `null` hoặc không tiến khi input không parse được; `errorIndex` giúp xác định vị trí lỗi.
- Trả một kiểu `Number` không phù hợp domain, ví dụ `Double.NaN` khi bật `setParseBigDecimal(true)`.

Ví dụ:

```text
input:          1,234.50oops
parsed number:  1234.50
end index:      8
input length:   12

Result: REJECT — còn ký tự chưa được tiêu thụ
```

**Hàm kiểm tra đơn giản:**

```java
ParsePosition position = new ParsePosition(0);
Number number = decimalFormat.parse(input, position);

boolean consumedAll = number != null
        && position.getIndex() == input.length();
```

Nhưng ngay cả `consumedAll == true` cũng chỉ xác nhận về **độ dài**, chưa kiểm chứng grouping/currency đúng theo domain. Vì thế nên đặt tên `parseFully` hoặc `consumedAll`, đừng đặt tên `validateEntireFinancialInput` nếu hàm chưa có validation riêng.

### Tránh lẫn `ParseException` với `ParsePosition`

Overload `parse(String)` có thể ném `ParseException` khi không thể bắt đầu parse, nhưng cũng có thể chấp nhận **tiền tố** rồi bỏ phần sau. Overload `parse(String, ParsePosition)` cho phép kiểm tra offset, thường trả `null` khi không parse được và không dùng ngoại lệ làm đường thành công/thất bại thông thường.

Với form giao diện, nên phân biệt lỗi "không bắt đầu được", "có đuôi chưa parse", "sai nhóm dấu", "số ngoài miền" và "currency không đúng" để thông báo có ích cho người dùng.

## 6. Java 17+: parser kiểm tra toàn chuỗi cho cả ba loại

Tạo file `FullInputNumberDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Currency;
import java.util.Locale;

public class FullInputNumberDemo {
    enum Kind { DECIMAL, PERCENT, CURRENCY }

    static DecimalFormat formatter(
            Locale locale, Kind kind, Currency currency) {
        NumberFormat base = switch (kind) {
            case DECIMAL -> NumberFormat.getNumberInstance(locale);
            case PERCENT -> NumberFormat.getPercentInstance(locale);
            case CURRENCY -> NumberFormat.getCurrencyInstance(locale);
        };
        if (!(base instanceof DecimalFormat decimal)) {
            throw new IllegalStateException("DecimalFormat required");
        }
        if (kind == Kind.CURRENCY) {
            decimal.setCurrency(currency);
        }
        decimal.setParseBigDecimal(true);
        return decimal;
    }

    static BigDecimal parseFully(
            String input, Locale locale, Kind kind,
            Currency currency) {
        if (input == null || input.isEmpty()) {
            throw new IllegalArgumentException("Empty input");
        }
        DecimalFormat format = formatter(locale, kind, currency);
        ParsePosition at = new ParsePosition(0);
        Number parsed = format.parse(input, at);

        if (!(parsed instanceof BigDecimal decimal)
                || at.getIndex() != input.length()) {
            throw new IllegalArgumentException(
                    "Incomplete or invalid input");
        }
        return decimal;
    }

    static void test(String label, String raw,
            Locale locale, Kind kind, Currency currency) {
        try {
            BigDecimal result =
                    parseFully(raw, locale, kind, currency);
            System.out.println(label + ": " + result.toPlainString());
        } catch (IllegalArgumentException ex) {
            System.out.println(label + ": REJECT");
        }
    }

    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        test("decimal US", "1,234.50",
                Locale.US, Kind.DECIMAL, usd);
        test("decimal DE", "1.234,50",
                Locale.GERMANY, Kind.DECIMAL, usd);
        test("decimal suffix", "1,234.50oops",
                Locale.US, Kind.DECIMAL, usd);
        test("wrong locale", "1.234,50",
                Locale.US, Kind.DECIMAL, usd);

        test("percent", "12.5%",
                Locale.US, Kind.PERCENT, usd);
        test("percent suffix", "12.5%extra",
                Locale.US, Kind.PERCENT, usd);
        test("percent missing symbol", "12.5",
                Locale.US, Kind.PERCENT, usd);

        test("currency", "$1,234.50",
                Locale.US, Kind.CURRENCY, usd);
        test("currency suffix", "$1,234.50oops",
                Locale.US, Kind.CURRENCY, usd);
        test("currency wrong symbol", "€1,234.50",
                Locale.US, Kind.CURRENCY, usd);
        test("NaN", "NaN",
                Locale.US, Kind.DECIMAL, usd);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FullInputNumberDemo.java
java FullInputNumberDemo
```

Stdout với JDK sử dụng định dạng `en-US`/`de-DE` phổ biến, đã đối chiếu logic trên runtime Java:

```text
decimal US: 1234.50
decimal DE: 1234.50
decimal suffix: REJECT
wrong locale: REJECT
percent: 0.125
percent suffix: REJECT
percent missing symbol: REJECT
currency: 1234.50
currency suffix: REJECT
currency wrong symbol: REJECT
NaN: REJECT
```

**Giải thích quan trọng:**

1. `12.5%` thành `0.125` vì `DecimalFormat` dạng phần trăm dùng multiplier 100. Giá trị domain đang biểu diễn **ratio**, không phải số điểm phần trăm.
2. `"1.234,50"` ở parser `Locale.US` có thể chỉ đọc tới `"1.234"`, nên phải từ chối vì chưa tiêu thụ hết.
3. `"1,234.50oops"` có thể tạo `BigDecimal("1234.50")` **nhưng còn đuôi**; không được chấp nhận.
4. `NaN` có thể được trả dưới dạng `Double` kể cả khi `setParseBigDecimal(true)`; điều kiện `instanceof BigDecimal` ngăn nó vào domain decimal hữu hạn.
5. `CURRENCY` ở đây nhận **currency expected từ context**. Khi `NumberFormat.parse` trả số thành công, nó **không tự cấp một Currency có thể tin cậy** từ ký hiệu. Kết quả parse là amount; đồng tiền là thuộc tính domain riêng phải được kiểm tra ở tầng thích hợp.
6. Hàm tên `parseFully` chỉ áp dụng điều kiện **toàn chuỗi và BigDecimal**, chưa xác thực grammar grouping nghiêm ngặt hay scale/range; bài sau sẽ bổ sung.

Với locale provider khác (SPI/HOST), mẫu ký hiệu tiền có thể thay đổi; nếu test phụ thuộc output nguyên văn, cố định provider/build hoặc tạo fixture theo hợp đồng đã kiểm chứng.

## 7. Percent: tách tỷ lệ, số phần trăm và số điểm phần trăm

Đây là một trong những lỗi kiểm thử nghiêm trọng nhất. Có ba khái niệm:

| Giá trị | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `0.125` | Ratio (12,5 phần trăm trên thang 0–1) | Tỷ lệ sử dụng trong phép nhân |
| `12.5%` | Cách **hiển thị** ratio `0.125` | `NumberFormat.getPercentInstance` |
| `12.5` | Số phần trăm tính theo đơn vị phần trăm, không phải ratio | Nếu lưu kiểu percent points, phải định nghĩa conversion |

Với `getPercentInstance(Locale.US)`:

```java
NumberFormat percent =
        NumberFormat.getPercentInstance(Locale.US);
percent.setMaximumFractionDigits(1);

String text = percent.format(new BigDecimal("0.125"));
// "12.5%"
```

Đây là **đoạn minh họa trong một phương thức**. Khi parse `"12.5%"` bằng percent formatter có `setParseBigDecimal(true)`, kết quả thường là `BigDecimal("0.125")`, không phải `12.5`. **Không nhân 100 thêm lần nữa khi dựng domain value**, và không chia 100 lần nữa nếu parser đã làm.

### Test percent nên có

- 0 → `0%` ở mẫu mặc định en-US.
- `0.125` → `12.5%` khi cấu hình 1 chữ số thập phân.
- `1` → `100%`; nếu domain chỉ cho ratio 0–1 thì phải kiểm tra miền.
- Giá trị âm nếu domain cho phép, ví dụ mức thay đổi `-0.025` → `-2.5%`.
- Giá trị lớn hơn 1 nếu nghiệp vụ cho phép tăng trưởng >100%.
- Dấu phần trăm ở trước/sau tùy locale và các khoảng trắng Unicode.
- Input thiếu `%`, input có phần đuôi, input chỉ gồm ký hiệu.
- Rounding khi từ `12.34%` hiển thị một chữ số thành `12.3%`; parse lại chỉ giữ giá trị đã hiển thị.

**Chọn semantic rõ:** đối với "tỷ lệ chiết khấu" có thể lưu ratio `0.125`; đối với "thay đổi 12,5 điểm phần trăm" là một đại lượng khác. Domain type hoặc tên field nên nêu rõ, ví dụ `discountRate` chứ không dùng `percent` mơ hồ.

## 8. Java 17+: formatting test cho decimal, percent và currency

Tạo file `NumberFormattingMatrixDemo.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.List;
import java.util.Locale;

public class NumberFormattingMatrixDemo {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");
        BigDecimal ratio = new BigDecimal("0.125");
        Currency usd = Currency.getInstance("USD");

        for (String tag : List.of("en-US", "de-DE")) {
            Locale locale = Locale.forLanguageTag(tag);

            NumberFormat decimal =
                    NumberFormat.getNumberInstance(locale);
            decimal.setMinimumFractionDigits(2);
            decimal.setMaximumFractionDigits(2);

            NumberFormat percent =
                    NumberFormat.getPercentInstance(locale);
            percent.setMaximumFractionDigits(1);

            NumberFormat money =
                    NumberFormat.getCurrencyInstance(locale);
            money.setCurrency(usd);

            System.out.println(tag + " | decimal="
                    + decimal.format(amount) + " | percent="
                    + percent.format(ratio) + " | money="
                    + money.format(amount));
        }

        System.out.println("amount unchanged="
                + amount.equals(new BigDecimal("1234.50")));
        System.out.println("ratio unchanged="
                + ratio.equals(new BigDecimal("0.125")));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 NumberFormattingMatrixDemo.java
java NumberFormattingMatrixDemo
```

Ví dụ stdout trên JDK dùng locale data CLDR đã kiểm thử:

```text
en-US | decimal=1,234.50 | percent=12.5% | money=$1,234.50
de-DE | decimal=1.234,50 | percent=12,5 % | money=1.234,50 $
amount unchanged=true
ratio unchanged=true
```

Dòng `de-DE` chứa **U+00A0 NO-BREAK SPACE** giữa giá trị và `%`/`$` trên runtime tham chiếu. Đừng thay nó bằng ASCII space rồi lưu thành golden string nếu đang kiểm thử chính xác Unicode. Nếu chạy JDK/provider khác, output presentation có thể đổi; hai dòng `amount unchanged` và `ratio unchanged` mới là kiểm tra domain invariants.

**Tại sao phải test cả output?** Vì dù domain đúng, hiển thị vẫn có thể sai do thiếu `setCurrency`, nhầm factory percent với number, nhầm minimum/maximum fraction digits, hoặc format theo locale mặc định của máy. Test domain và test presentation bổ sung cho nhau, không thay thế nhau.

## 9. Currency: amount, ISO code và ký hiệu phải được kiểm thử tách biệt

Đối tượng `Currency` biểu diễn một đồng tiền được nhận diện bằng **mã**, ví dụ `USD`, `EUR` hoặc `VND`. Ký hiệu `$`, `€` hoặc chữ viết tắt theo locale chỉ phục vụ trình bày và **không phải khóa duy nhất** cho currency.

Ví dụ:

```java
Currency currency = Currency.getInstance("USD");
NumberFormat format =
        NumberFormat.getCurrencyInstance(Locale.GERMANY);
format.setCurrency(currency);
String output = format.format(new BigDecimal("1234.50"));
```

Đây là **đoạn code trong phương thức**. Locale Đức mô tả quy ước ký hiệu/dấu ngăn cách, nhưng đồng tiền domain vẫn là USD. Người dùng sống tại Đức có thể thanh toán USD; không được suy mọi giao dịch của họ là EUR từ `Locale.GERMANY`.

### Currency test cần phân biệt

1. **Amount parse:** `"$1,234.50"` có tạo đúng decimal amount không?
2. **Currency identity:** mã currency do nghiệp vụ cung cấp có đúng `USD` không?
3. **Display symbol:** ký hiệu, vị trí, khoảng trắng theo locale có hợp chính sách presentation không?
4. **Mismatch:** nếu yêu cầu USD, input biểu diễn EUR được xử lý thế nào? Không lấy một giá trị `BigDecimal` rồi âm thầm gán USD.
5. **Fraction digits:** JPY, USD, KWD có quy ước chữ số phần lẻ khác nhau; chính sách scale/rounding nghiệp vụ phải rõ.
6. **Ambiguity:** ký hiệu `$` có thể là nhiều đồng tiền; đừng đoán mã từ ký hiệu text đơn lẻ.
7. **Negative amounts:** refund/chargeback có thể mang dấu âm; cách hiển thị/accounting format và policy nghiệp vụ có thể khác.
8. **Locale upgrade:** vị trí symbol và no-break space có thể đổi theo CLDR/JDK, nên test snapshot có thông tin runtime.

### Chọn schema cho tiền

```json
{
  "amount": "1234.50",
  "currency": "USD"
}
```

Đây là ví dụ JSON máy-máy với decimal string có schema, **không** phải giá tiền đã địa phương hóa. Nếu dùng cột DB, chọn DECIMAL/NUMERIC với precision/scale rõ và trường currency code riêng. Dùng `BigDecimal` trong Java; đừng tính tiền bằng `double` hoặc dùng `NumberFormat.format(amount)` làm nguồn dữ liệu.

**Giới hạn của parser:** `NumberFormat.parse` đọc giá trị số theo pattern currency, nhưng không phải bộ xác minh currency code từ một chuỗi text tự do. Nếu UI có field currency riêng, xem đó là một input có kiểm soát; nếu cần đọc đa currency từ văn bản, phải dùng parser có khả năng nhận diện đơn vị và quy tắc domain, rồi validate mã thu được.

## 10. Full-input consumption không đồng nghĩa strict grouping

Đây là điểm phải có test riêng. Trên các JDK có `DecimalFormat` phổ biến, input:

```text
12,34.50
```

có thể được parser số `en-US` đọc **hết** và trả `1234.50`, dù dấu nhóm không được đặt theo quy ước `1,234.50`.

Điều kiện:

```java
position.getIndex() == input.length()
```

là **cần** để từ chối suffix còn dư, nhưng **không đủ** để xác nhận input tuân đúng grammar grouping. Parser i18n thường linh hoạt để đọc nhiều dạng đầu vào; nghiệp vụ tiền tệ có thể cần quy tắc nghiêm hơn.

### Kiến trúc kiểm tra nhiều lớp

```text
Input "12,34.50"
          |
      full parse
          |
    parsed = 1234.50
    consumed = true
          |
      lexical policy
          |
  Grouping không hợp lệ
          |
        REJECT
```

Cách thực hiện lexical validation phải theo loại input và locale. **Không áp dụng một regex dùng dấu phẩy/chấm ASCII cho mọi locale**: `fr-FR` có thể dùng U+202F, `ar-EG` có chữ số và dấu phân cách khác, còn định dạng Ấn Độ có nhóm số khác kiểu 3-3-3. Nếu nghiệp vụ chỉ nhận một cấu trúc máy cố định, tốt hơn dùng canonical grammar không có grouping thay vì localized grammar quá phức tạp.

## 11. Java 17+: strict policy đơn giản cho decimal en-US

Ví dụ sau chỉ được thiết kế cho một **form số dương en-US, không có exponent**, cho phép nhóm bằng dấu phẩy theo đúng cụm ba chữ số hoặc viết không nhóm, phần thập phân 1–2 chữ số, không dấu `+/-`.

Tạo file `StrictGroupingDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;
import java.util.regex.Pattern;

public class StrictGroupingDemo {
    private static final Pattern US_DECIMAL = Pattern.compile(
            "(?:0|[1-9][0-9]*|"
            + "[1-9][0-9]{0,2}(?:,[0-9]{3})+)"
            + "(?:\\.[0-9]{1,2})?");

    static BigDecimal parse(String input) {
        if (input == null || !US_DECIMAL.matcher(input).matches()) {
            throw new IllegalArgumentException("Invalid syntax");
        }

        NumberFormat base = NumberFormat.getNumberInstance(Locale.US);
        if (!(base instanceof DecimalFormat formatter)) {
            throw new IllegalStateException("DecimalFormat required");
        }
        formatter.setParseBigDecimal(true);
        ParsePosition pos = new ParsePosition(0);
        Number value = formatter.parse(input, pos);

        if (!(value instanceof BigDecimal result)
                || pos.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid value");
        }
        return result;
    }

    static void test(String input) {
        try {
            System.out.println(input + " => " + parse(input));
        } catch (IllegalArgumentException ex) {
            System.out.println(input + " => REJECT");
        }
    }

    public static void main(String[] args) {
        test("1234.50");
        test("1,234.50");
        test("12,34.50");
        test("1,234.50xyz");
        test("0012.50");
        test("1,234.567");
        test("0.50");
    }
}
```

```bash
javac StrictGroupingDemo.java
java StrictGroupingDemo
```

```text
1234.50 => 1234.50
1,234.50 => 1234.50
12,34.50 => REJECT
1,234.50xyz => REJECT
0012.50 => REJECT
1,234.567 => REJECT
0.50 => 0.50
```

**Phạm vi có chủ đích:**

- Regex này **không** dành cho `de-DE`, `fr-FR`, Arabic numbers hay âm số.
- Số `1234.50` không dùng grouping vẫn hợp lệ theo policy minh họa; `1,234.50` dùng grouping đúng cũng hợp lệ.
- `0012.50` bị từ chối vì policy không cho leading zero; một domain khác có thể cho phép.
- Phần lẻ nhiều nhất 2 chữ số, không phải mặc định mà Java ép buộc.
- `regex.matches()` kiểm tra **toàn bộ chuỗi**; sau đó parser vẫn được kiểm tra full consumption và kiểu giá trị.
- Với số tiền thực, còn phải kiểm tra domain scale/precision, currency, rounding, min/max và giới hạn input size.

Nếu cần grammmar localized nghiêm ngặt cho nhiều ngôn ngữ, phải dựa trên dữ liệu locale và quy tắc của parser/ICU thích hợp, không tự nhân bản regex US sang toàn bộ ứng dụng.

## 12. Rounding: `format → parse` có thể không giữ nguyên số

Một test sai phổ biến là:

```java
BigDecimal original = new BigDecimal("1.239");
String text = currencyFormatter.format(original);
BigDecimal restored = parse(text);
assertEquals(original, restored); // Không phải bất biến mặc định
```

Nếu formatter chỉ hiển thị hai chữ số thập phân, `1.239` có thể thành `1.24`. Parser không có cách khôi phục chữ số thứ ba đã bị bỏ. Test sai sẽ cho rằng localization hỏng, trong khi **bộ formatter đang thực hiện đúng chính sách presentation**.

### Java 17+: minh họa round-trip mất precision

Tạo file `RoundingRoundTripDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class RoundingRoundTripDemo {
    public static void main(String[] args) throws Exception {
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        formatter.setParseBigDecimal(true);

        BigDecimal original = new BigDecimal("1.239");
        String shown = formatter.format(original);
        BigDecimal parsed = (BigDecimal) formatter.parse(shown);

        System.out.println("original=" + original);
        System.out.println("shown=" + shown);
        System.out.println("parsed=" + parsed);
        System.out.println("same numeric value="
                + (original.compareTo(parsed) == 0));
    }
}
```

```bash
javac RoundingRoundTripDemo.java
java RoundingRoundTripDemo
```

```text
original=1.239
shown=1.24
parsed=1.24
same numeric value=false
```

**Test đúng theo hợp đồng:** nếu domain phải bảo toàn `1.239`, giữ `BigDecimal` nguyên trong domain/persistence, chỉ format `1.24` cho UI. Nếu nghiệp vụ bắt buộc làm tròn đến 2 chữ số **trước khi ghi sổ**, đó phải là phép tính với `setScale(2, roundingMode)` hoặc logic tiền tệ được định nghĩa rõ **trong domain**, không phải hậu quả tùy tiện của formatter.

### `BigDecimal.equals` khác `compareTo`

`new BigDecimal("1.20").equals(new BigDecimal("1.2"))` là `false` do scale khác, còn `compareTo(...) == 0`. Khi test parse/round-trip, quyết định **giữ scale** có phải requirement không. Không mặc định dùng `equals` cho mọi phép kiểm tra giá trị số, và cũng không bỏ qua scale nếu domain thật sự đòi đúng số chữ số.

## 13. NaN, Infinity và âm zero: test trường hợp đặc biệt

Khi `DecimalFormat.setParseBigDecimal(true)` được bật, parser thông thường trả `BigDecimal` cho các số decimal hữu hạn; tuy nhiên các ký hiệu đặc biệt như **NaN** hoặc **infinity** có thể trả **`Double`**. `BigDecimal` không có biểu diễn NaN/infinity.

Vì thế:

```java
Number result = decimal.parse(input, position);
if (!(result instanceof BigDecimal)) {
    // Từ chối NaN, Infinity và kiểu không phù hợp domain.
}
```

Đây là đoạn minh họa. Nếu hệ thống cho phép NaN trong một miền như thống kê, cần một kiểu/domain policy riêng, không cố ép thành số tiền.

### Âm zero

`double` phân biệt `+0.0` và `-0.0` ở mức biểu diễn/bit; `BigDecimal` thì không bảo toàn dấu âm của zero như một giá trị riêng. Khi parse `"-0"` với `setParseBigDecimal(true)`, kết quả có thể là `BigDecimal.ZERO`; nếu domain cần phân biệt âm zero, phải lưu thêm metadata hoặc chọn kiểu số phù hợp.

Đừng xem `-0` là "số âm tiền hợp lệ" chỉ vì có dấu trừ trong raw string. Domain tài chính thường chỉ cần giá trị zero, nhưng việc cho phép cú pháp `-0` là quyết định của validator.

### Số quá lớn/nhỏ

Test `Long.MAX_VALUE`, `BigDecimal` lớn, số có nhiều chữ số phần lẻ, số gần zero, và input bất thường dài. Kiểm tra giới hạn tài nguyên để tránh parser xử lý chuỗi khổng lồ từ người dùng hoặc làm giảm hiệu năng. `setParseBigDecimal(true)` không thay thế giới hạn magnitude/precision.

## 14. Unicode whitespace: test code point, không đoán bằng mắt

Một số locale dùng khoảng trắng Unicode làm group separator hoặc đặt giữa số và ký hiệu tiền/percent:

| Ký tự | Mã | Vai trò thường gặp |
| --- | --- | --- |
| ASCII SPACE | U+0020 | Khoảng trắng thông thường |
| NO-BREAK SPACE | U+00A0 | Khoảng trắng không ngắt |
| NARROW NO-BREAK SPACE | U+202F | Khoảng trắng hẹp không ngắt |

Ví dụ `fr-FR` có thể hiển thị số `1 234,5` với **U+202F**, trong khi tiếng Nga và một số pattern currency dùng U+00A0. JDK/CLDR có thể cập nhật các dấu này.

Nếu test:

```java
assertEquals("1 234,5", actual);
```

nó có thể thất bại dù hai chuỗi nhìn giống nhau; ngược lại, tự chuyển tất cả space thành ASCII để test pass có thể bỏ qua lỗi phân tích dữ liệu và line breaking. Khi điều tra, in code point của chuỗi:

```java
static String codePoints(String s) {
    return s.codePoints()
            .mapToObj(cp -> String.format(
                    Locale.ROOT, "U+%04X", cp))
            .toList().toString();
}
```

Đây là **phương thức minh họa** cần import `java.util.Locale`. Hãy ghi cả locale, JDK version, provider, currency và output Unicode code points vào báo cáo regression.

### Java 17+: probe dấu phân nhóm `fr-FR`

Tạo file `UnicodeGroupingProbe.java`:

```java
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.util.Locale;

public class UnicodeGroupingProbe {
    static String cps(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .toList().toString();
    }

    public static void main(String[] args) {
        Locale france = Locale.FRANCE;
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(france);
        NumberFormat formatter =
                NumberFormat.getNumberInstance(france);

        String output = formatter.format(1234.5);
        System.out.printf(Locale.ROOT, "group=U+%04X%n",
                (int) symbols.getGroupingSeparator());
        System.out.println("number=" + cps(output));
    }
}
```

```bash
javac UnicodeGroupingProbe.java
java UnicodeGroupingProbe
```

Ví dụ kết quả trên JDK đã kiểm thử:

```text
group=U+202F
number=[U+0031, U+202F, U+0032, U+0033, U+0034, U+002C, U+0035]
```

**Không hardcode** rằng mọi phiên bản JDK đều dùng U+202F cho `fr-FR`. Bản test này dùng `DecimalFormatSymbols` để quan sát thực tế; nếu sản phẩm yêu cầu cố định một dạng vào/ra, hãy định nghĩa contract riêng và test chính contract đó.

## 15. Bài test tự động phải tách domain test và presentation snapshot

### 15.1. Test domain invariant

Giá trị nghiệp vụ phải giữ nguyên:

- `BigDecimal("1234.50")` vẫn là số thập phân `1234.50` khi đổi locale.
- Tỷ lệ `BigDecimal("0.125")` vẫn là ratio `0.125`.
- Mã currency vẫn `"USD"` dù ký hiệu/vị trí đổi.
- Giá trị sau parse thỏa min/max/scale/precision.
- Đổi JVM default locale không được làm kết quả thay đổi **nếu** API luôn truyền locale tường minh.

Đối với `BigDecimal`, so theo `compareTo` nếu policy chỉ đòi giá trị số học; so `equals` nếu phải giữ scale chính xác. Mọi test phải nói rõ chọn tiêu chí nào.

### 15.2. Test presentation

Chuỗi theo `Locale.US`, `Locale.GERMANY`, `Locale.FRANCE` có thể khác ở dấu nhóm, thập phân, percent/currency sign và spacing. Khi test literal output, cần xác định:

- JDK major/minor và locale data;
- `java.locale.providers` (nếu cấu hình);
- locale tag và Unicode extension numbering system nếu có;
- currency code, rounding mode, min/max fraction digits;
- ký tự Unicode chính xác.

Nếu nâng JDK dẫn đến CLDR đổi kiểu space hay tên ký hiệu, hãy đánh giá **đây là thay đổi hợp lệ trong presentation hay là vi phạm hợp đồng API**. Đừng mặc nhiên cập nhật snapshot hoặc tự sửa raw data để "khớp kết quả cũ".

### 15.3. Property-based / data-driven testing

Có thể sinh các giá trị hợp lệ trong domain và kiểm tra:

1. Formatter không ném lỗi cho dải amount hợp lệ.
2. Sau format, parser cùng locale nhận được **giá trị đã hiển thị**, không đòi tự động phục hồi precision trước rounding.
3. Khi không có rounding/precision loss theo policy, test numeric round-trip bằng `BigDecimal.compareTo==0`.
4. Input được nối thêm một suffix không hợp lệ phải bị từ chối nếu API hứa parse toàn chuỗi.
5. Input khác locale không được âm thầm chấp nhận thành giá trị sai mà chưa có validation.
6. Sau parser, miền giá trị, currency và scale phải đúng schema.

**Đừng biến các properties thành khẳng định sai:** `parse(format(x)) == x` không đúng phổ quát do rounding, grouping/provider/signed zero và scale. Phải ràng buộc giả thiết đầu vào và cấu hình formatter.

## 16. Java 17+: một chương trình tự kiểm thử không cần JUnit

Dùng `AssertionError` để tạo bộ smoke tests có thể chạy bằng JDK 17+, không cần `-ea`. Tạo file `NumericParsingSmokeTest.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Currency;
import java.util.Locale;

public class NumericParsingSmokeTest {
    static BigDecimal parseAll(NumberFormat input, String raw) {
        if (!(input instanceof DecimalFormat format)) {
            throw new IllegalStateException("DecimalFormat required");
        }
        format.setParseBigDecimal(true);
        ParsePosition pos = new ParsePosition(0);
        Number value = format.parse(raw, pos);
        if (!(value instanceof BigDecimal decimal)
                || pos.getIndex() != raw.length()) {
            throw new IllegalArgumentException("Not fully parsed");
        }
        return decimal;
    }

    static void equal(BigDecimal expected, BigDecimal actual) {
        if (expected.compareTo(actual) != 0) {
            throw new AssertionError("Expected " + expected
                    + ", received " + actual);
        }
    }

    static void reject(NumberFormat format, String raw) {
        try {
            parseAll(format, raw);
            throw new AssertionError("Unexpected acceptance: " + raw);
        } catch (IllegalArgumentException expected) {
            // Rejection was expected.
        }
    }

    public static void main(String[] args) {
        equal(new BigDecimal("1234.50"),
                parseAll(NumberFormat.getNumberInstance(Locale.US),
                        "1,234.50"));
        equal(new BigDecimal("1234.50"),
                parseAll(NumberFormat.getNumberInstance(Locale.GERMANY),
                        "1.234,50"));

        reject(NumberFormat.getNumberInstance(Locale.US),
                "1,234.50tail");
        reject(NumberFormat.getNumberInstance(Locale.US),
                "1.234,50");

        equal(new BigDecimal("0.125"),
                parseAll(NumberFormat.getPercentInstance(Locale.US),
                        "12.5%"));
        reject(NumberFormat.getPercentInstance(Locale.US),
                "12.5%tail");

        NumberFormat currency =
                NumberFormat.getCurrencyInstance(Locale.US);
        currency.setCurrency(Currency.getInstance("USD"));
        equal(new BigDecimal("1234.50"),
                parseAll(currency, "$1,234.50"));
        reject(currency, "$1,234.50tail");

        reject(NumberFormat.getNumberInstance(Locale.US), "NaN");

        System.out.println("decimal: PASS");
        System.out.println("percent: PASS");
        System.out.println("currency: PASS");
        System.out.println("full-input: PASS");
        System.out.println("special-values: PASS");
    }
}
```

```bash
javac -encoding UTF-8 NumericParsingSmokeTest.java
java NumericParsingSmokeTest
```

Stdout khi mọi điều kiện pass:

```text
decimal: PASS
percent: PASS
currency: PASS
full-input: PASS
special-values: PASS
```

Hàm `reject` chỉ công nhận ngoại lệ `IllegalArgumentException` do parser validation tạo ra, không dùng giá trị trả về để nhận diện lỗi. Test này **cố ý không bao gồm** strict grouping; xem `StrictGroupingDemo` ở trên để kiểm tra grammar đầu vào theo chính sách.

**Cảnh báo:** trong dự án lớn, test helper nên tách immutable test fixtures, không dùng chung formatter giữa case song song. Với JUnit 5, viết các test có tên rõ, parametrized tests theo locale/kind/input và báo cáo input/code points khi thất bại.

## 17. Thiết kế test suite đầy đủ hơn cho sản phẩm thực

Một bộ kiểm thử có cấu trúc:

```text
tests/
  DecimalFormattingTest
  DecimalFullInputParsingTest
  PercentRatioSemanticsTest
  CurrencyCodeAndSymbolTest
  NegativeZeroAndSpecialValuesTest
  StrictGroupingPolicyTest
  UnicodeSeparatorTest
  RoundingAndScaleTest
  LocaleMismatchTest
  JdkLocaleUpgradeRegressionTest
```

Đây là **cấu trúc khái niệm** cho test suite, không phải các file phải tạo trong bài học.

Mỗi test case nên lưu:

```text
field-kind: DECIMAL / PERCENT / CURRENCY
locale-tag: en-US / de-DE / fr-FR / ...
currency-code: USD / EUR / VND / ...
input-text: Unicode string
expected-amount: decimal canonical value
expected-consumed: true/false
expected-valid: true/false
expected-error: parse/type/syntax/domain/currency
rounding-mode: HALF_EVEN / ...
fraction-digits: min/max
runtime/provider metadata: nếu snapshot thật sự phụ thuộc
```

**Cần đo và log những điều sau khi test fail:** input escaped, code points, locale tag, loại format, index đã tiêu thụ, error index, kiểu `Number`, BigDecimal scale, min/max fraction digits, currency code và provider/JDK version. Không ghi dữ liệu cá nhân nhạy cảm nguyên văn vào log; test fixtures nên dùng giá trị giả lập.

### Tình huống cần ưu tiên theo rủi ro

- **Đơn hàng/thuế/thanh toán:** precision, scale, currency code và decimal parse phải được ưu tiên hơn snapshot dấu chấm/phẩy.
- **Dashboard phần trăm:** ratio vs percent points, rounding và không mất dấu âm.
- **Input theo locale nhiều ngôn ngữ:** full-input và grouping validation, Unicode spaces.
- **CSV/import legacy:** biết locale/format gốc của từng file; tránh parse cùng một chuỗi bằng locale đang dùng để xem UI.
- **API machine-to-machine:** canonical schema, không dựa vào `Locale.getDefault()`.
- **Nâng cấp JDK/CLDR:** kiểm tra riêng các thay đổi ký hiệu/space/numbering systems so với domain invariants.

## 18. Tách chuỗi hiển thị khỏi giá trị lưu trữ

Dữ liệu domain nên có dạng:

```json
{
  "amount": "1234.50",
  "currency": "USD",
  "ratio": "0.125"
}
```

Trong đó:

- `amount` là decimal canonical string theo hợp đồng (hoặc kiểu DECIMAL trong DB).
- `currency` là mã ISO currency, không phải symbol.
- `ratio` là tỷ lệ decimal 0–1 theo nghĩa được mô tả trong schema.

Với dữ liệu này, UI có thể format theo `en-US`/`de-DE` và không ảnh hưởng giá trị gốc. Khi cần hiển thị phần trăm, chuyển ratio bằng `getPercentInstance`. Khi tính số tiền, dùng `BigDecimal` với rounding/domain policy; không parse lại kết quả hiển thị để thực hiện phép toán.

### Vấn đề khi lưu `format(amount)`

Nếu bạn lưu `"1.234,50"` vào DB mà không có locale, một ngày sau code có thể đọc bằng parser `en-US` và hiểu thành `1.234` rồi bỏ phần đuôi. Nếu lưu `"12.5%"` mà không thống nhất ratio, phía nhận có thể coi `12.5` là tỷ lệ thay vì 12,5 phần trăm. Nếu lưu `"$1,234.50"` mà không lưu currency code, dấu `$` vẫn không xác định duy nhất đồng tiền.

**Giải pháp:** ở boundary đầu vào, parse thành đối tượng có kiểu + validation, ở boundary đầu ra format theo locale. Domain và persistence không phụ thuộc cách đặt dấu nhóm, ký hiệu hoặc khoảng trắng của runtime.

## 19. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ dùng `parse(String)` và kiểm tra không exception | Parser có thể chấp nhận tiền tố | `ParsePosition` + so index với length |
| Coi `getIndex()==length` là strict grammar | `12,34.50` có thể parse hết | Lexical validation theo policy locale |
| Dùng number formatter cho percent | `12.5%` không theo semantic ratio | `getPercentInstance` với multiplier đúng |
| Chia/nhân 100 hai lần | Sai tỷ lệ gấp 100 lần | Domain lưu ratio hoặc percent points rõ |
| Coi `"$"` là currency code | Dollar nhiều đồng tiền | Lưu `Currency`/ISO code |
| Quên `setCurrency` khi giao dịch khác currency default | In ký hiệu/đơn vị sai | Lấy currency từ domain |
| Chuyển `BigDecimal` qua `double` không cần thiết | Mất precision nhị phân | Dùng decimal exactness |
| So `BigDecimal.equals` cho numeric-only test | Scale khác tạo false negative | `compareTo==0` nếu chỉ so giá trị |
| Giả định `parse(format(x))==x` luôn đúng | Formatting rounding mất số | Tách domain invariant vs display precision |
| Chấp nhận `NaN` cho amount | Special Number không hợp tiền | Check type hữu hạn/`BigDecimal` |
| Không test `-0` | Signed-zero semantic bị mất | Định nghĩa policy |
| Normalize mọi Unicode space thành ASCII | Phá format/no-break semantics | Kiểm tra theo locale và field |
| Parse input de-DE bằng en-US | Sai giá trị hoặc bỏ suffix | Locale nguồn rõ ràng |
| Sử dụng default locale JVM cho mọi user | Kết quả lệch theo server | Truyền locale tường minh |
| Một formatter mutable dùng chung đa luồng | Race giữa currency/fraction settings | Instance riêng, hoặc đồng bộ rõ |
| Snapshot cố định cho mọi JDK | Test hỏng khi CLDR cập nhật | Runtime metadata + review đúng phạm vi |
| Chỉ test happy path một con số | Bỏ suffix, lỗi grouping, âm, overflow | Ma trận positive/negative/boundary |
| Dùng parse locale cho API canonical | Dữ liệu machine-to-machine mơ hồ | Schema decimal nhất quán |

## 20. Câu hỏi tự kiểm tra

1. **`NumberFormat.getNumberInstance` có phải cũng là percent formatter không?** Không; dùng `getPercentInstance` cho tỷ lệ.
2. **`"12.5%"` parse theo percent formatter US thành bao nhiêu nếu domain lưu ratio?** `0.125`.
3. **Tại sao `"1,234.50extra"` có thể trả số?** Parser có thể đọc một tiền tố; chỉ kiểm tra exception là không đủ.
4. **Điều kiện full input là gì?** Giá trị parse hợp lệ, đúng kiểu và `ParsePosition.getIndex()==input.length()`.
5. **Điều kiện full input có bảo đảm dấu nhóm đúng chuẩn không?** Không; `DecimalFormat` có thể khoan dung với grouping.
6. **`"12,34.50"` ở `en-US` có thể bị parser nhận thành `1234.50` không?** Có thể, nên phải thêm grammar validation nếu bắt buộc strict.
7. **Vì sao `BigDecimal("1.20").equals(BigDecimal("1.2"))` là false?** Scale khác dù số học bằng nhau.
8. **`setParseBigDecimal(true)` có làm NaN trở thành BigDecimal không?** Không; NaN có thể là `Double` và phải được xử lý theo domain.
9. **Vì sao `-0` cần test?** Kiểu số khác nhau có thể giữ/mất dấu âm zero; domain phải định nghĩa nghĩa của nó.
10. **`$` có đủ để xác định currency code không?** Không, vì nhiều đồng tiền cùng ký hiệu.
11. **`NumberFormat.getCurrencyInstance(Locale.GERMANY)` có tự biết đơn hàng USD không?** Không; set currency từ domain.
12. **`fr-FR` có thể dùng U+202F ở đâu?** Là group separator trong nhiều phiên bản CLDR/JDK.
13. **Có nên đổi U+202F sang U+0020 trong mọi số trước parse không?** Không; cần input contract riêng, không thay đổi văn bản tùy tiện.
14. **Nếu formatter chỉ hiển thị hai chữ số, parse có khôi phục `1.239` từ `1.24` không?** Không.
15. **Phần trăm 0% và 100% có cần test boundary không?** Có, cùng miền của ratio và chính sách giá trị âm hoặc >100%.
16. **Vì sao currency tests phải kiểm tra currency code riêng?** Parser text chỉ đọc amount theo pattern; symbol có thể mơ hồ.
17. **Có nên dựa vào `Locale.getDefault()` khi test nhiều locale?** Không; truyền locale tường minh.
18. **Khi nào so sánh literal formatted output?** Khi test thuộc tính presentation có contract và runtime/provider đã được xác định.
19. **Một API JSON gửi `"1.234,50"` mà không truyền locale có an toàn không?** Không; nên dùng decimal canonical.
20. **Tại sao cần test parse suffix lạ?** Để bảo đảm không chấp nhận đầu vào chỉ được tiêu thụ một phần.
21. **Khác biệt giữa full parse và validation domain?** Full parse kiểm tra ký tự đã đọc, domain validation kiểm tra quy tắc business/miền giá trị.
22. **Nếu test với `"NaN"` nhận về `Double.NaN`, nên làm gì khi domain là Money?** Từ chối.

## 21. Checklist triển khai

- [ ] Formatter/parser nhận `Locale` rõ ràng, không lấy implicit JVM default từ request người dùng.
- [ ] Test decimal, percent và currency thành **ba loại riêng**.
- [ ] Domain tiền dùng `BigDecimal` cùng currency code; domain ratio có nghĩa rõ.
- [ ] Test cả format, parse, full-input và business/lexical validation.
- [ ] `ParsePosition` bắt đầu từ 0; so index kết thúc với toàn bộ chiều dài input.
- [ ] Kiểm tra kiểu số; không cho `NaN`/infinity vào domain khi không được phép.
- [ ] Có test negative zero, sign, min/max, precision, scale và rounding.
- [ ] Có test sai locale và dấu `,`/`.` đổi vai trò.
- [ ] Có test suffix rác, empty string, grouping sai, ký hiệu tiền sai và phần trăm thiếu `%`.
- [ ] Có test Unicode whitespace U+0020/U+00A0/U+202F và hệ chữ số được hỗ trợ.
- [ ] Không giả định full-consumption đồng nghĩa grouping đúng.
- [ ] Không đòi `parse(format(x)) == x` khi formatter có rounding/lossy precision.
- [ ] Không lưu localized display strings làm source of truth.
- [ ] Test output presentation gắn JDK/CLDR/provider nếu so nguyên văn.
- [ ] Formatter mutable không được dùng chung không bảo vệ giữa threads.
- [ ] QA chạy trên runtime/locale provider của production, với ít nhất một tập legacy input thực tế.

## Tài liệu tham khảo

- [Oracle Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): decimal, integer, currency, percent factories; parse theo locale và `ParsePosition`.
- [Oracle Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): pattern, rounding, `setParseBigDecimal`, parse prefix, special numbers.
- [Oracle Java SE 17 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html): các dấu thập phân/phân nhóm, currency và numbering symbols.
- [Oracle Java SE 17 — ParsePosition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html): vị trí parse thành công/không thành công.
- [Oracle Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal scale/precision và `equals` vs `compareTo`.
- [Oracle Java SE 17 — Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html): currency code và symbol theo locale.
- [Oracle Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): locale tags và `Category.FORMAT`.
- [Unicode CLDR](https://cldr.unicode.org/): dữ liệu về dấu, number patterns, currency symbols và các thay đổi theo phiên bản.
