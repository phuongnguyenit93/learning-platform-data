# setParseBigDecimal và bảo toàn độ chính xác khi phân tích số

## 1. Mục tiêu và tình huống sử dụng

Khi người dùng nhập một con số trong giao diện theo ngôn ngữ của họ, chương trình Java phải thực hiện hai việc **khác nhau**:

1. **Hiểu cú pháp số theo locale**: dấu thập phân, dấu phân nhóm và hệ chữ số.
2. **Giữ nguyên giá trị thập phân cần thiết cho nghiệp vụ**: không biến dữ liệu tài chính hay dữ liệu yêu cầu độ chính xác cao thành một phép xấp xỉ nhị phân không mong muốn.

Ví dụ, hai chuỗi sau có thể mô tả cùng số học:

```text
en-US: 1,234.50
de-DE: 1.234,50
```

Khi parse đúng locale, kết quả mong muốn có thể là đối tượng `BigDecimal` biểu diễn chính xác `1234.50`, bao gồm **scale bằng 2**. Nhưng `NumberFormat.parse(String)` thông thường trả về kiểu `Number` như `Long` hoặc `Double` tùy đầu vào, cách triển khai và thiết lập. Với số thập phân dài, `Double` không bảo toàn mọi chữ số mà người dùng đã nhập.

`DecimalFormat.setParseBigDecimal(true)` giải quyết phần quan trọng đó: yêu cầu `DecimalFormat` trả về `BigDecimal` cho **giá trị số hữu hạn** được parse, thay vì làm tròn thông tin qua `double` hoặc chuyển thành kiểu số nguyên thông thường. Đây là tính năng cho **đọc số**, khác với các cấu hình làm tròn lúc **định dạng số ra chuỗi**.

Sau bài học, bạn có thể:

- Dùng `DecimalFormat` với `Locale` và bật `setParseBigDecimal(true)` đúng cách.
- Hiểu sự khác nhau giữa **giá trị**, **precision**, **scale** và biểu diễn nhị phân `double`.
- Phát hiện parser chỉ đọc **một phần** input bằng `ParsePosition`.
- Nhận diện các ngoại lệ `NaN`, vô cực và âm zero, cũng như lỗi dữ liệu đầu vào.
- Phân biệt số được hiển thị với số chính xác được dùng trong phép toán và dữ liệu lưu trữ.
- Thiết kế một đường xử lý đầu vào số có kiểm tra locale, chữ số được phép, miền giá trị và độ chính xác.

## 2. Tại sao không dùng ngay `Double.parseDouble`?

`Double.parseDouble("1234.50")` yêu cầu cú pháp số dạng Java, **không** tự áp dụng ký hiệu dấu phân cách địa phương hóa. Chẳng hạn, chuỗi `1.234,50` theo `de-DE` không được hiểu tự động thành `1234.50` bởi `Double.parseDouble`.

Ngay cả khi input không có phân nhóm và dấu thập phân là `.`, kiểu `double` sử dụng biểu diễn **IEEE 754 nhị phân**, nên không lưu chính xác được nhiều số thập phân như `0.1` hoặc `0.2`. Điều này khác với lỗi parse dấu phẩy: đây là lỗi **biểu diễn số** sau khi parse.

```java
System.out.println(0.1 + 0.2); // 0.30000000000000004
```

Đoạn trên là minh họa trong một phương thức Java. Để tính số tiền hoặc các dữ liệu cần độ chính xác decimal, ta thường sử dụng `BigDecimal` thay vì phụ thuộc vào `double`.

**Lưu ý:** `BigDecimal` không tự quyết định input là en-US hay de-DE. Nó giải quyết biểu diễn/thuật toán thập phân; `DecimalFormat` mới là thành phần đọc chuỗi theo locale.

## 3. `NumberFormat` và `DecimalFormat`: cấu hình parse

### 3.1. API liên quan

| API | Vai trò |
| --- | --- |
| `NumberFormat.getNumberInstance(locale)` | Lấy formatter/parser số thường cho locale |
| `NumberFormat.parse(String)` | Trả `Number`; kết quả có thể là `Long` hoặc `Double` |
| `DecimalFormat.setParseBigDecimal(true)` | Bật chế độ parse số hữu hạn thành `BigDecimal` |
| `DecimalFormat.isParseBigDecimal()` | Kiểm tra cờ đang bật |
| `DecimalFormat.parse(String, ParsePosition)` | Parse từ vị trí chỉ định, trả vị trí sau ký tự cuối được đọc |
| `DecimalFormatSymbols.getInstance(locale)` | Lấy dấu và ký hiệu theo locale |
| `DecimalFormat.setParseIntegerOnly(true)` | Yêu cầu parse phần nguyên; **không** thích hợp khi cần giữ phần thập phân |
| `DecimalFormat.setGroupingUsed(boolean)` | Quy định sử dụng dấu nhóm trong định dạng; không phải bộ kiểm tra nghiêm ngặt mọi vị trí nhóm |

Ví dụ cấu hình `DecimalFormat` tường minh:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

Locale locale = Locale.forLanguageTag("en-US");
DecimalFormat parser = new DecimalFormat(
        "#,##0.################",
        DecimalFormatSymbols.getInstance(locale));
parser.setParseBigDecimal(true);
```

Đây là **một đoạn code trong phương thức**, không phải file Java độc lập. Pattern trên mô tả một số có phân nhóm và tối đa 16 vị trí phần lẻ để **định dạng**; nó không tự giới hạn số chữ số được phép khi **parse**. Nếu muốn quy tắc precision/scale của form nhập, cần **validation riêng** sau bước parse.

Trong nhiều môi trường JDK thông dụng, `NumberFormat.getNumberInstance(locale)` trả về `DecimalFormat` và có thể ép kiểu:

```java
NumberFormat nf = NumberFormat.getNumberInstance(locale);
if (nf instanceof DecimalFormat decimal) {
    decimal.setParseBigDecimal(true);
} else {
    throw new IllegalStateException("DecimalFormat not available");
}
```

Nhưng **không mặc định mọi locale provider đều trả về `DecimalFormat`**. `NumberFormat` là lớp cha; nếu nghiệp vụ phụ thuộc chắc chắn vào `setParseBigDecimal`, hãy dùng đường khởi tạo parser có kiểu và provider phù hợp, hoặc kiểm tra kiểu trước khi cast. Không viết `(DecimalFormat) nf` mà không hiểu ràng buộc triển khai của ứng dụng.

### 3.2. Cờ `parseBigDecimal` thay đổi *kiểu kết quả*

Mặc định, `DecimalFormat` có thể trả:

- `Long` cho số nguyên vừa miền dữ liệu.
- `Double` cho số có phần lẻ hoặc số không vừa kiểu nguyên.
- `Double` biểu diễn `NaN` hoặc vô cực khi parser nhận được các ký hiệu tương ứng.

Khi bật `setParseBigDecimal(true)`, với số **hữu hạn** parser trả một `BigDecimal` có giá trị thập phân chính xác theo chữ số đã đọc. Nó **không** có nghĩa `parse(...)` được đổi kiểu trả về ở mức khai báo: phương thức vẫn khai báo kiểu `Number`, vì vậy phải kiểm tra kết quả trước khi dùng phương thức riêng của `BigDecimal`.

## 4. Giá trị, precision và scale khác nhau

`BigDecimal` lưu một giá trị decimal bằng một số nguyên không giới hạn độ dài (`unscaledValue`) và một số mũ thập phân (`scale`). Về nguyên lý:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Ví dụ:

| Chuỗi decimal | Giá trị số học | `scale()` | `precision()` |
| --- | --- | --- | --- |
| `0.1` | một phần mười | 1 | 1 |
| `0.10` | một phần mười | 2 | 2 |
| `1234.50` | một nghìn hai trăm ba mươi tư phẩy năm | 2 | 6 |
| `1234.500` | cùng giá trị số học | 3 | 7 |

**Scale** là số chữ số sau dấu thập phân trong biểu diễn thông thường, nhưng có thể âm với số dạng lũy thừa mười; **precision** là số chữ số có nghĩa của unscaled value. Scale không đơn thuần là "độ chính xác tính toán" và precision không phải độ dài của chuỗi đã nhập (không tính dấu, dấu phân nhóm, các chữ số 0 đầu vô nghĩa).

Hai số:

```java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("1.2");
```

có giá trị số học bằng nhau nhưng khác scale. `a.equals(b)` trả `false` vì `BigDecimal.equals` xét cả scale, trong khi `a.compareTo(b) == 0` là `true` vì so sánh giá trị số học.

**Vì sao cần giữ scale?** Trong nghiệp vụ, `1.20` có thể mang ý nghĩa người dùng nhập đến hai chữ số thập phân, khác `1.2` chỉ nhập một chữ số. Nhưng điều đó không đồng nghĩa scale của chuỗi được parse luôn là thuộc tính nghiệp vụ bắt buộc: một số hệ thống tiền tệ quy định scale cố định bằng 2 và cần chủ động kiểm tra `setScale(...)` theo quy tắc được chấp nhận.

## 5. Ví dụ chạy được: bật/tắt `setParseBigDecimal`

Tạo file `ParseBigDecimalDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class ParseBigDecimalDemo {
    public static void main(String[] args) throws Exception {
        DecimalFormat parser = new DecimalFormat(
                "#,##0.################",
                DecimalFormatSymbols.getInstance(Locale.US));

        Number ordinary = parser.parse("1,234.50");
        System.out.println("ordinary type: "
                + ordinary.getClass().getSimpleName());
        System.out.println("ordinary value: " + ordinary);

        parser.setParseBigDecimal(true);
        BigDecimal exact = (BigDecimal) parser.parse("1,234.50");
        System.out.println("exact type: "
                + exact.getClass().getSimpleName());
        System.out.println("exact value: " + exact.toPlainString());
        System.out.println("scale: " + exact.scale());
        System.out.println("precision: " + exact.precision());

        BigDecimal zeroTen = (BigDecimal) parser.parse("0.10");
        System.out.println("0.10 value: " + zeroTen.toPlainString());
        System.out.println("0.10 scale: " + zeroTen.scale());

        String large = "12345678901234567890.123456789";
        BigDecimal veryLarge = (BigDecimal) parser.parse(large);
        System.out.println("large: " + veryLarge.toPlainString());
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac -encoding UTF-8 ParseBigDecimalDemo.java
java ParseBigDecimalDemo
```

Kết quả:

```text
ordinary type: Double
ordinary value: 1234.5
exact type: BigDecimal
exact value: 1234.50
scale: 2
precision: 6
0.10 value: 0.10
0.10 scale: 2
large: 12345678901234567890.123456789
```

**Giải thích quan trọng:**

- Parser mặc định trả `Double` và in `1234.5`; biểu diễn `1,234.50` đã mất dấu phân nhóm và số 0 sau dấu thập phân trong giá trị được in.
- Chế độ `BigDecimal` giữ `1234.50` với `scale=2` và `precision=6`.
- Số decimal rất dài được giữ chính xác theo các chữ số hợp lệ đã parse, không bị cắt xuống khoảng 15–17 chữ số có nghĩa của `double`.
- Việc cast thành `BigDecimal` trong ví dụ là phù hợp vì đầu vào đều là **số hữu hạn hợp lệ**. Với input tùy ý từ người dùng, **không cast vô điều kiện**; cần xử lý trường hợp `NaN`/vô cực và kiểm tra kết quả.

## 6. Không nhầm `new BigDecimal(double)` với parser chính xác

Một lỗi có thể xảy ra dù đã bật `setParseBigDecimal(true)` là sau đó chuyển giá trị thành `double`:

```java
BigDecimal exact = (BigDecimal) parser.parse("0.1");
double approximate = exact.doubleValue();
```

`doubleValue()` chuyển sang biểu diễn nhị phân và có thể mất các chữ số chính xác; nếu lại tạo `BigDecimal` từ `double`, dữ liệu có thể thay đổi ngoài ý muốn.

Ba cách khởi tạo `BigDecimal` cần phân biệt:

| Cách khởi tạo | Đặc điểm |
| --- | --- |
| `new BigDecimal("0.1")` | Biểu diễn decimal đúng bằng `0.1` |
| `BigDecimal.valueOf(0.1)` | Dùng chuỗi chuẩn từ `Double.toString(0.1)`, thường cho giá trị decimal dự kiến `0.1` |
| `new BigDecimal(0.1)` | Biểu diễn **chính xác giá trị nhị phân double** gần `0.1`, không nhất thiết bằng decimal `0.1` |

Với input có dấu phân cách locale, hãy parse trực tiếp thành `BigDecimal` bằng `DecimalFormat`, thay vì `Double.parseDouble` rồi `new BigDecimal(double)`. Với chuỗi lưu trữ ở dạng decimal **độc lập locale** (ví dụ `"1234.50"` trong schema của ứng dụng), `new BigDecimal(string)` là lựa chọn rõ ràng vì không cần parser dấu nhóm.

## 7. Parse theo locale: dấu phân cách thay đổi ý nghĩa

Một parser dành cho `en-US` có thể đọc `1,234.50` thành `1234.50`; parser cho `de-DE` đọc `1.234,50` thành cùng giá trị. Nhưng parser Mỹ áp dụng vào chuỗi Đức có thể **đọc sai hoặc chỉ đọc một tiền tố**:

```text
en-US: 1,234.50
de-DE: 1.234,50
```

Các dấu chấm/phẩy có ý nghĩa ngược nhau. Không được chuyển locale bằng cách thay mọi dấu phẩy thành dấu chấm: dấu phẩy là **dấu phân nhóm** trong en-US nhưng là **dấu thập phân** trong de-DE.

### Ví dụ Java 17+: so sánh hai locale

Tạo `LocaleDecimalParseDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class LocaleDecimalParseDemo {
    static DecimalFormat parserFor(Locale locale) {
        DecimalFormat parser = new DecimalFormat(
                "#,##0.################",
                DecimalFormatSymbols.getInstance(locale));
        parser.setParseBigDecimal(true);
        return parser;
    }

    public static void main(String[] args) throws Exception {
        DecimalFormat us = parserFor(Locale.US);
        DecimalFormat de = parserFor(Locale.GERMANY);

        BigDecimal fromUs =
                (BigDecimal) us.parse("1,234.50");
        BigDecimal fromDe =
                (BigDecimal) de.parse("1.234,50");

        System.out.println("US: " + fromUs.toPlainString());
        System.out.println("DE: " + fromDe.toPlainString());

        // Sai locale: parse(String) có thể chấp nhận một tiền tố.
        Number wrong = us.parse("1.234,50");
        System.out.println("wrong locale: " + wrong);
    }
}
```

```bash
javac LocaleDecimalParseDemo.java
java LocaleDecimalParseDemo
```

Kết quả:

```text
US: 1234.50
DE: 1234.50
wrong locale: 1.234
```

Kết quả dòng cuối **không phải thành công**: `us.parse("1.234,50")` chấp nhận `1.234` rồi dừng trước phần `,50`. Không nên xem một giá trị số khác `null` là bằng chứng input hoàn toàn hợp lệ.

Lưu ý: `Locale` mà bạn chọn phải là **locale của định dạng người dùng thực sự nhập**, không phải locale mặc định của server hay locale của người khác. Nếu ứng dụng cho phép thay đổi ngôn ngữ trong form, phải liên kết dữ liệu đầu vào với ngôn ngữ định dạng thực tế.

## 8. `ParsePosition`: phân tích hết chuỗi hay chỉ một phần?

`NumberFormat.parse(String)` / `DecimalFormat.parse(String)` có thể trả về một `Number` sau khi chỉ đọc **một phần** input. Đối với một form nhập số, rủi ro này đặc biệt nghiêm trọng:

```text
Input:  1,234.50oops
Parsed: 1234.50
Suffix: oops
```

Nếu bạn không phát hiện đuôi `oops`, hệ thống có thể âm thầm chấp nhận dữ liệu sai.

Dùng `ParsePosition` để kiểm tra parser đi qua **toàn bộ chuỗi**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class FullInputParseDemo {
    static BigDecimal parseAll(String raw, Locale locale) {
        if (raw == null || raw.isEmpty()) {
            throw new IllegalArgumentException("Empty input");
        }

        DecimalFormat format = new DecimalFormat(
                "#,##0.################",
                DecimalFormatSymbols.getInstance(locale));
        format.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number number = format.parse(raw, position);

        if (!(number instanceof BigDecimal decimal)
                || position.getIndex() != raw.length()) {
            throw new IllegalArgumentException(
                    "Invalid decimal input");
        }
        return decimal;
    }

    public static void main(String[] args) {
        System.out.println(parseAll("1,234.50", Locale.US));
        try {
            parseAll("1,234.50oops", Locale.US);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
        try {
            parseAll("oops", Locale.US);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

```bash
javac FullInputParseDemo.java
java FullInputParseDemo
```

```text
1234.50
Invalid decimal input
Invalid decimal input
```

`ParsePosition.getIndex()` là vị trí ngay sau phần đã parse; `getErrorIndex()` giúp chẩn đoán lỗi khi không thể bắt đầu đọc. Đối với input form, tiêu chuẩn "thành công" cần bao gồm **(1) có kết quả đúng kiểu; (2) toàn bộ ký tự đầu vào đã được tiêu thụ; (3) giá trị thỏa domain constraints**.

**Điểm rất quan trọng:** ngay cả việc đọc hết chuỗi **vẫn chưa phải bộ kiểm tra cú pháp nhóm thật nghiêm ngặt**. Nhiều hiện thực `DecimalFormat` có thể chấp nhận nhóm đặt không đúng quy ước, ví dụ `12,34.5` với parser kiểu Mỹ và trả giá trị `1234.5`. Nếu hệ thống quy định chính xác cú pháp dấu nhóm, cần validation format riêng hoặc cơ chế parser stricter được hỗ trợ bởi thư viện/version mục tiêu; không tự giả định `DecimalFormat` đã kiểm tra mọi quy tắc hiển thị.

**Chính sách khoảng trắng:** ví dụ `parseAll` không tự `trim()`, nên khoảng trắng đầu/cuối có thể bị từ chối. Trong sản phẩm, có thể chủ động cho phép một số khoảng trắng quanh input, nhưng phải quy định rõ cả U+0020 và Unicode spacing; không silently sửa dấu phân nhóm nằm bên trong số.

## 9. Các trường hợp đặc biệt: `NaN`, vô cực và âm zero

`setParseBigDecimal(true)` **không bảo đảm mọi kết quả từ `parse(...)` đều là `BigDecimal`**.

- `NaN`: nếu input khớp biểu diễn `NaN` của locale/provider, parser trả một `Double` có giá trị `Double.NaN`, **không** phải `BigDecimal`.
- **Vô cực:** nếu input khớp ký hiệu vô cực của `DecimalFormatSymbols`, parser vẫn có thể trả `Double.POSITIVE_INFINITY` hoặc `Double.NEGATIVE_INFINITY`.
- **Âm zero:** khi `parseBigDecimal` **tắt**, chuỗi như `"-0"` có thể được phân tích thành `Double(-0.0)`. Khi cờ **bật**, kết quả `BigDecimal.ZERO` không có trạng thái âm zero riêng; dấu âm của zero không thể được bảo tồn bằng `BigDecimal`.
- `parseIntegerOnly`: khi bật, parser không giữ phần sau dấu thập phân; không sử dụng nếu mục đích là giữ decimal chính xác.

### Ví dụ Java 17+: xử lý đúng `Number` khi gặp giá trị đặc biệt

File `SpecialNumberDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class SpecialNumberDemo {
    public static void main(String[] args) throws Exception {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);
        DecimalFormat parser = new DecimalFormat(
                "#,##0.################", symbols);
        parser.setParseBigDecimal(true);

        Number finite = parser.parse("0.10");
        Number notANumber = parser.parse(symbols.getNaN());
        Number infinity = parser.parse(symbols.getInfinity());
        Number negativeZero = parser.parse("-0");

        System.out.println("finiteBigDecimal="
                + (finite instanceof BigDecimal));
        System.out.println("nanIsDouble="
                + (notANumber instanceof Double));
        System.out.println("nan="
                + Double.isNaN(notANumber.doubleValue()));
        System.out.println("infinity="
                + Double.isInfinite(infinity.doubleValue()));
        System.out.println("negativeZero=" + negativeZero);
    }
}
```

```bash
javac SpecialNumberDemo.java
java SpecialNumberDemo
```

Kết quả trên JDK thông dụng:

```text
finiteBigDecimal=true
nanIsDouble=true
nan=true
infinity=true
negativeZero=0
```

Chương trình lấy `symbols.getNaN()` và `symbols.getInfinity()` thay vì tự đoán chuỗi hiển thị: ký hiệu có thể khác theo locale. Khi ứng dụng chỉ chấp nhận giá trị decimal hữu hạn, **kiểm tra `instanceof BigDecimal`** như `FullInputParseDemo` trước khi dùng giá trị.

## 10. `setMaximumFractionDigits` không giới hạn precision của parser

Một nhầm lẫn phổ biến:

```java
DecimalFormat format = new DecimalFormat(
        "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));
format.setParseBigDecimal(true);

BigDecimal parsed =
        (BigDecimal) format.parse("1,234.56789");
System.out.println(parsed);        // 1234.56789
System.out.println(format.format(parsed)); // 1,234.57
```

Đây là đoạn minh họa trong phương thức có các import cần thiết. `"#,##0.00"` hoặc `setMaximumFractionDigits(2)` ảnh hưởng **chuỗi output khi format**, **không** tự khiến `parse` cắt hoặc từ chối một số có năm chữ số thập phân.

Sự khác nhau này quan trọng với hệ thống tiền tệ: bạn có thể vô tình chấp nhận `1.23456` ở bước nhập, sau đó chỉ hiển thị `1.23` và nghĩ giá trị đã được giới hạn về hai chữ số. Để quy định số thập phân tối đa, hãy kiểm tra `parsed.scale()` / dữ liệu raw hoặc thiết lập `setScale(allowedScale, RoundingMode.UNNECESSARY)` nếu muốn **từ chối** mọi giá trị buộc phải làm tròn.

```java
// Minh họa một chính sách tiền tệ yêu cầu tối đa hai chữ số decimal.
BigDecimal amount = parsed.setScale(
        2, java.math.RoundingMode.UNNECESSARY);
```

`RoundingMode.UNNECESSARY` ném `ArithmeticException` nếu cần làm tròn để hạ scale; nhưng nó cho phép giảm các chữ số 0 không làm đổi giá trị, ví dụ `1.230` thành `1.23`. Vì vậy, nếu điều kiện nghiệp vụ là **"không được nhập hơn hai chữ số phần lẻ kể cả số 0"**, cần kiểm tra `scale()` hoặc biểu diễn input trước khi chuẩn hóa; hai điều kiện này khác nhau.

## 11. Xử lý decimal chính xác sau khi parse

`BigDecimal` giúp tính số học thập phân nhưng không tự đưa ra quy tắc tài chính. Ví dụ:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalMathDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("0.1");
        BigDecimal b = new BigDecimal("0.2");

        System.out.println(a.add(b).toPlainString());
        System.out.println(
                new BigDecimal("1.20").equals(new BigDecimal("1.2")));
        System.out.println(
                new BigDecimal("1.20")
                        .compareTo(new BigDecimal("1.2")) == 0);

        BigDecimal divided = BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_UP);
        System.out.println(divided.toPlainString());
    }
}
```

```bash
javac DecimalMathDemo.java
java DecimalMathDemo
```

```text
0.3
false
true
0.33
```

- Cộng `BigDecimal("0.1")` với `BigDecimal("0.2")` ra giá trị đúng `0.3`.
- `equals` xem xét scale, còn `compareTo` so sánh giá trị toán học.
- Phép chia có thể tạo số thập phân vô hạn như `1/3`, nên cần quy tắc scale/rounding; `BigDecimal` không làm cho mọi phép toán luôn có kết quả thập phân hữu hạn.

Trong ứng dụng tài chính, còn phải quyết định **Currency**, số đơn vị tiền nhỏ nhất, quy tắc làm tròn tại từng bước, giới hạn giá trị và yêu cầu audit. `setParseBigDecimal(true)` chỉ là một khâu của luồng xử lý chính xác.

## 12. Đường xử lý input trong sản phẩm

Một quy trình an toàn cho form nhập số:

1. **Xác định nguồn input và locale**. Nếu người dùng chọn `de-DE`, dùng đúng locale khi đọc dấu decimal/grouping. Không lấy `Locale.getDefault()` của máy chủ để đoán.
2. **Kiểm tra ký tự và kích thước đầu vào**. Giới hạn độ dài phù hợp tránh input có hàng triệu chữ số gây tốn bộ nhớ/CPU. Quyết định cho phép số âm, dấu `+`, số mũ, ký hiệu tiền tệ và Unicode digits hay không.
3. **Parse thành `BigDecimal`** bằng `DecimalFormat` có `setParseBigDecimal(true)`; truyền `Locale` tường minh, không thay default JVM theo request.
4. **Kiểm tra toàn bộ input** bằng `ParsePosition`; xử lý các ký tự còn thừa, trường hợp `NaN`/vô cực và input thiếu.
5. **Kiểm tra format strict nếu cần**. Nếu dấu phân nhóm phải đúng vị trí, áp dụng validator cú pháp theo locale hoặc parse nghiêm ngặt phù hợp; không coi parse hết chuỗi là đủ.
6. **Kiểm tra giá trị**: số âm có hợp lệ không, min/max, scale/precision, đơn vị tiền, số lượng tối đa.
7. **Tính toán bằng `BigDecimal` và rounding policy rõ ràng**, không đổi sang `double` trong giữa pipeline.
8. **Lưu trữ theo hợp đồng độc lập locale**: column decimal/numeric có scale được kiểm soát hoặc chuỗi canonical `value.toPlainString()` nếu schema yêu cầu. Không lưu dấu nhóm theo locale để máy khác parse lại.
9. **Định dạng ra giao diện** bằng `NumberFormat.getNumberInstance(viewLocale)`/`DecimalFormat` và các thiết lập display phù hợp; không để việc format thay đổi giá trị domain.

### Hai dạng chuỗi cùng ý nghĩa nhưng khác hợp đồng

```text
Nguồn nhập của người dùng (de-DE):   "1.234,50"
                  | DecimalFormat parseBigDecimal
                  v
Domain BigDecimal:                  1234.50
                  |
           +------+------+
           |             |
           v             v
Lưu trữ canonical     Hiển thị en-US
"1234.50"             "1,234.50"
```

**Điểm mấu chốt:** dấu ngăn cách theo locale chỉ là **cú pháp đầu vào/đầu ra**. Sau khi parse đúng, hãy giữ kiểu decimal có ý nghĩa nghiệp vụ, không mang theo dấu ngăn cách vào các phép tính.

## 13. Những lỗi phổ biến

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Parse locale bằng `Double.parseDouble` | Không hiểu dấu nhóm/thập phân theo locale | Dùng `DecimalFormat` cấu hình theo locale |
| Parse bằng `NumberFormat` rồi gọi `doubleValue()` | Có thể mất chữ số decimal dài | Bật `setParseBigDecimal(true)` và giữ `BigDecimal` |
| `new BigDecimal(double)` để giữ số nhập decimal | Lưu đúng giá trị nhị phân gần đúng, không phải chuỗi decimal đã nhập | Dùng parse trực tiếp thành `BigDecimal` hoặc `new BigDecimal(String)` cho canonical string |
| Cast mọi kết quả `parse` thành `BigDecimal` | `NaN`/vô cực có thể trả `Double` | Kiểm tra `instanceof BigDecimal` |
| Nghĩ `0.10` và `0.1` có cùng scale | Numeric value có thể bằng nhau nhưng scale khác | Phân biệt `compareTo` và `equals` |
| Chỉ kiểm tra `parse` có trả kết quả | Parser có thể chỉ đọc phần đầu | Kiểm tra `ParsePosition.getIndex() == input.length()` |
| Chỉ kiểm tra toàn chuỗi đã parse | Dấu nhóm sai vị trí có thể vẫn được chấp nhận | Thêm validation lexical/strict theo hợp đồng |
| Chọn sai locale | `1,234` có nghĩa khác nhau giữa en-US và de-DE | Dùng locale thực tế của input |
| `setMaximumFractionDigits(2)` rồi tưởng input bị giới hạn | Thiết lập định dạng output, không phải validation parser | Kiểm tra `scale`/precision theo domain |
| Tự `replace(",", ".")` để chuẩn hóa | Có thể biến dấu nhóm thành dấu decimal hoặc ngược lại | Dùng parser locale và validation |
| Coi `BigDecimal` tự xử lý mọi rounding | Chia số có thể cần quy tắc làm tròn | Chọn `RoundingMode` rõ ràng |
| Dùng chung `DecimalFormat` static giữa thread | `DecimalFormat` mutable, không bảo đảm thread-safe | Tạo instance riêng cho luồng xử lý |
| Lưu chuỗi có dấu nhóm từ UI vào DB/API | Dữ liệu phụ thuộc locale và khó round-trip | Lưu giá trị decimal theo schema độc lập locale |

## 14. Tự kiểm tra

1. **`setParseBigDecimal(true)` thay đổi điều gì?** Nó yêu cầu `DecimalFormat` trả `BigDecimal` cho kết quả số hữu hạn, thay vì dựa trên `Long`/`Double` thông thường.
2. **Vì sao `NumberFormat.parse("0.10")` rồi lấy `double` không giữ được scale=2?** `double` không biểu diễn khái niệm scale decimal; nó chỉ mang giá trị nhị phân gần đúng.
3. **`BigDecimal("1.20").equals(BigDecimal("1.2"))` có đúng không?** Không: hai biểu diễn có scale khác. `compareTo(...) == 0` đúng về giá trị số học.
4. **Dùng parser en-US để đọc `1.234,50` có an toàn không?** Không: nó có thể đọc một phần thành `1.234`; phải dùng đúng locale của nguồn input.
5. **Vì sao `parse(String)` trả về `Number` dù đã bật `parseBigDecimal`?** Đó là chữ ký API của `NumberFormat`/`DecimalFormat`, và các giá trị đặc biệt vẫn có thể trả kiểu khác.
6. **`NaN` có được trả dưới dạng `BigDecimal` không?** Không. Những giá trị như NaN hoặc infinity không được biểu diễn bởi `BigDecimal` và có thể trả `Double`.
7. **`parseBigDecimal` bật có giữ được `"-0"` là âm zero không?** Không: `BigDecimal` không có trạng thái negative zero riêng.
8. **`setMaximumFractionDigits(2)` có từ chối chuỗi `1.23456` khi parse không?** Không mặc định; cần kiểm tra scale/precision và validator.
9. **Tại sao kiểm tra `ParsePosition` hết chuỗi vẫn chưa đủ?** Vì một số parser chấp nhận grouping sai quy ước; validation cú pháp có thể cần nghiêm ngặt hơn.
10. **Có nên lưu kết quả đã format theo locale `de-DE` như `"1.234,50"` vào API decimal canonical không?** Không nếu schema yêu cầu số độc lập locale. Hãy lưu numeric/decimal canonical và chỉ format khi hiển thị.
11. **`BigDecimal` có tự chọn làm tròn phép chia `1/3` không?** Không theo chính sách nghiệp vụ; phải chỉ định scale và `RoundingMode` khi cần.
12. **Với khoản tiền `1234.50`, điều gì cần kiểm tra ngoài việc parse chính xác?** Currency, scale/quy tắc phân số, miền giá trị, rounding, parser strict và chính sách lưu trữ.

## 15. Tài liệu tham khảo

- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): `setParseBigDecimal`, `isParseBigDecimal`, kiểu trả về và các trường hợp đặc biệt.
- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): `parse`, định dạng/đọc số theo locale.
- [Java SE 21 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormatSymbols.html): các dấu thập phân, phân nhóm và ký hiệu `NaN`/vô cực.
- [Java SE 21 — ParsePosition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ParsePosition.html): theo dõi vị trí đã parse và vị trí lỗi.
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): scale, precision, rounding và so sánh giá trị.
- [Java SE 21 — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): kiểm soát quy tắc làm tròn.
