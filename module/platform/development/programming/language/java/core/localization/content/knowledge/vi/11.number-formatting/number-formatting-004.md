# Dấu thập phân, phân nhóm và hệ chữ số theo locale

## 1. Vì sao cùng một số có nhiều cách viết?

Giá trị số học `1234567.89` không thay đổi khi người dùng đổi ngôn ngữ hay khu vực, nhưng **cách biểu diễn thành văn bản** có thể thay đổi hoàn toàn. Trong Java Core Localization, `java.text.NumberFormat` và `java.text.DecimalFormat` chịu trách nhiệm dùng dữ liệu locale để quyết định dấu thập phân, dấu phân nhóm, số chữ số, quy tắc nhóm, chữ số được dùng và nhiều đặc điểm định dạng khác.

Một vài cách viết tương ứng (với dữ liệu CLDR điển hình):

| Locale | Ví dụ biểu diễn số `1234567.89` | Dấu thập phân | Dấu nhóm |
| --- | --- | --- | --- |
| `en-US` | `1,234,567.89` | `.` | `,` |
| `vi-VN` | `1.234.567,89` | `,` | `.` |
| `de-DE` | `1.234.567,89` | `,` | `.` |
| `fr-FR` | `1 234 567,89` | `,` | khoảng trắng hẹp không ngắt U+202F |
| `ar-EG` | `١٬٢٣٤٬٥٦٧٫٨٩` | U+066B (`٫`) | U+066C (`٬`) |

Dòng `fr-FR` trong bảng **không dùng dấu cách ASCII thông thường** giữa các nhóm mà dùng ký tự U+202F, dù mắt thường có thể khó phân biệt. Dòng `ar-EG` sử dụng **chữ số Ả Rập-Indic** và dấu phân tách riêng. Ký tự và quy tắc cụ thể có thể khác theo phiên bản Java, nhà cung cấp locale data và tùy chọn numbering system; các ví dụ trên đã được đối chiếu trên một runtime JDK dùng dữ liệu CLDR.

**Quy tắc quan trọng nhất:** không có "dấu chấm luôn là dấu thập phân" hay "dấu phẩy luôn là dấu phân nhóm" cho mọi locale. Cũng không thể mặc định chữ số hiển thị luôn là `0`–`9` (U+0030–U+0039).

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **decimal separator**, **grouping separator** và **grouping pattern**.
2. Dùng `NumberFormat`/`DecimalFormatSymbols` để định dạng số cho locale cụ thể.
3. Hiểu Unicode numbering system và thẻ BCP 47 có extension `u-nu-*`.
4. Tránh nhầm biểu diễn số cho người dùng với biểu diễn số dùng lưu trữ/giao tiếp máy.
5. Parse số có dấu ngăn cách một cách có kiểm soát, phát hiện nội dung thừa và tránh mất chính xác.
6. Hiểu sự khác biệt giữa định dạng số thông thường, tiền tệ, phần trăm và những giới hạn giữa các runtime.

## 2. Ba thành phần phải tách biệt

### 2.1. Dấu thập phân (decimal separator)

Dấu thập phân phân chia phần nguyên và phần lẻ.

```text
en-US:  12.5
vi-VN:  12,5
ar-EG:  ١٢٫٥
```

Vì vậy `12,5` có thể là mười hai phẩy năm ở một locale, trong khi parser của locale khác không hiểu cùng một ý nghĩa. Trong API Java, dấu thập phân cho kiểu định dạng số thông thường có thể xem qua `DecimalFormatSymbols.getDecimalSeparator()`.

**Không** dùng `String.replace(",", ".")` để chuyển mọi chuỗi số quốc tế thành dạng chuẩn: dấu phẩy có thể là dấu nhóm, dấu thập phân hoặc một phần dữ liệu sai.

### 2.2. Dấu phân nhóm (grouping separator)

Dấu nhóm phân tách các nhóm chữ số để dễ đọc những số lớn.

```text
en-US: 1,234,567
vi-VN: 1.234.567
fr-FR: 1 234 567
ar-EG: ١٬٢٣٤٬٥٦٧
```

Dấu nhóm không phải một phần của **giá trị số học**. Nó là ký tự trình bày được chèn thêm theo locale, và một số kiểu format có thể không sử dụng dấu nhóm. Java cho phép yêu cầu tắt nhóm bằng `formatter.setGroupingUsed(false)`; điều đó **không** thay đổi dấu thập phân hay biến số thành chuỗi chuẩn để lưu trữ.

Dấu nhóm có thể là **khoảng trắng Unicode không ngắt** như U+00A0 hoặc U+202F. Vì vậy:

- `"1 234"` chứa U+0020 (space ASCII) chưa chắc được parser của locale chấp nhận giống `"1 234"` chứa U+202F.
- `trim()`, `split(" ")` và các thao tác thay "dấu cách" thủ công không phải cách xử lý đáng tin cậy cho dữ liệu số đã địa phương hóa.
- Khi kết quả trông đúng nhưng parse không được, hãy kiểm tra **code point** chứ không chỉ nhìn font trên màn hình.

### 2.3. Quy tắc phân nhóm (grouping pattern)

Không phải mọi hệ thống ngôn ngữ đều chia số thành nhóm ba từ phải sang trái. Ví dụ cách nhóm theo quy ước Ấn Độ:

```text
12,34,567.89
```

Phần ba chữ số ở bên phải (`567`) đi cùng các nhóm hai chữ số (`34`, `12`). Đây là **quy tắc nhóm**, khác hoàn toàn với ký tự dấu nhóm. Có cùng dấu phẩy nhưng pattern khác thì kết quả vẫn khác.

**Cần biết giới hạn của JDK:** `java.text.DecimalFormat` truyền thống không cung cấp cơ chế tổng quát biểu diễn *hai kích thước nhóm khác nhau* chỉ bằng pattern `#,##,##0`. Nhiều dấu nhóm trong pattern được chuẩn hóa theo nhóm cuối; thí nghiệm `#,##,##0.00` trên JDK cho ra `#,##0.00` và định dạng `1,234,567.89`. Ngoài ra, `NumberFormat.getNumberInstance(Locale.forLanguageTag("hi-IN"))` trên một runtime JDK có thể vẫn xuất dạng ba chữ số `1,234,567.89`. **Đừng khẳng định chỉ đặt `hi-IN` là chắc chắn có dạng lakh/crore trên mọi JDK**; nếu nghiệp vụ đòi hỏi cách phân nhóm Ấn Độ, kiểm thử provider/phiên bản đang chạy và cân nhắc thư viện ICU có hỗ trợ dữ liệu pattern phù hợp.

## 3. Hệ chữ số (numbering system) không chỉ là dấu phân cách

Chữ số Latin quen thuộc:

```text
0 1 2 3 4 5 6 7 8 9
```

chỉ là **một tập ký tự chữ số**. Một số locale dùng hệ chữ số khác để biểu diễn cùng giá trị:

| Hệ / mã `nu` | Ví dụ chữ số 0–4 | Mục đích |
| --- | --- | --- |
| `latn` | `0 1 2 3 4` | Latin digits |
| `arab` | `٠ ١ ٢ ٣ ٤` | Arabic-Indic digits |
| `arabext` | `۰ ۱ ۲ ۳ ۴` | Extended Arabic-Indic digits |
| `deva` | `० १ २ ३ ४` | Devanagari digits |
| `thai` | `๐ ๑ ๒ ๓ ๔` | Thai digits |

Đây là **ký tự hiển thị**, không phải những giá trị số học khác nhau. Trong Java, `Character.digit(...)` có thể nhận biết nhiều chữ số Unicode, nhưng điều đó **không bảo đảm** mọi API parse sẽ hỗ trợ mọi hệ chữ số hay mọi cách ghép dấu phân cách. Hãy dùng API locale-aware phù hợp và kiểm tra chính sách input.

### Unicode locale extension `nu` trong BCP 47

`Locale` có thể mang Unicode locale extension chọn numbering system:

```text
en-US-u-nu-arab
ar-EG-u-nu-latn
th-TH-u-nu-thai
```

- `en-US-u-nu-arab`: tiếng Anh/Mỹ với yêu cầu biểu diễn số bằng hệ `arab`.
- `ar-EG-u-nu-latn`: tiếng Ả Rập/Ai Cập với yêu cầu dùng chữ số Latin.
- `th-TH-u-nu-thai`: tiếng Thái/Thái Lan với yêu cầu dùng hệ chữ số Thái.

Các đối tượng trên tạo bằng `Locale.forLanguageTag(tag)`; có thể truy xuất giá trị bằng `locale.getUnicodeLocaleType("nu")`. Ví dụ:

```java
Locale locale = Locale.forLanguageTag("en-US-u-nu-arab");
System.out.println(locale.getUnicodeLocaleType("nu")); // arab
```

Đây là **đoạn minh họa trong phương thức** với `import java.util.Locale;`, không phải chương trình độc lập.

**Giới hạn:** có `nu` trong thẻ **không phải lời bảo đảm** rằng mọi `NumberFormat`, phiên bản JDK và locale provider đều hỗ trợ hệ chữ số được yêu cầu. Một vài numbering system có cách ghi không phải mười chữ số thập phân liền nhau; một số API sẽ dùng mặc định hoặc không thể định dạng theo cách người dùng mong muốn. Cần kiểm thử trên runtime thực, nhất là khi `nu` lấy từ input của người dùng.

## 4. API Java Core: dùng lớp nào?

| Lớp / phương thức | Vai trò | Lưu ý |
| --- | --- | --- |
| `NumberFormat.getNumberInstance(locale)` | Định dạng/parse số thông thường theo locale | Factory nhận `Locale` tường minh |
| `NumberFormat.getIntegerInstance(locale)` | Định dạng/parse dạng số nguyên | Có thể làm tròn khi format; không dùng thay cho validation đầu vào |
| `NumberFormat.getCurrencyInstance(locale)` | Định dạng tiền tệ theo locale | Có thêm ký hiệu tiền, quy tắc phân số và dấu riêng |
| `NumberFormat.getPercentInstance(locale)` | Định dạng phần trăm | Thường nhân giá trị với 100 khi format |
| `DecimalFormat` | Tùy biến pattern, rounding, parsing `BigDecimal` | Dạng hiện thực phổ biến cho decimal numbers |
| `DecimalFormatSymbols.getInstance(locale)` | Lấy dấu/chữ số/ký hiệu theo locale | Có thể quan sát `getZeroDigit()`, `getDecimalSeparator()`, `getGroupingSeparator()` |
| `NumberFormat.setGroupingUsed(...)` | Bật/tắt hiển thị dấu nhóm | Không đổi giá trị số |
| `NumberFormat.setMinimumFractionDigits(...)` | Số chữ số phần lẻ tối thiểu | Có thể thêm chữ số 0 |
| `NumberFormat.setMaximumFractionDigits(...)` | Số chữ số phần lẻ tối đa | Có thể làm tròn để giảm độ dài |
| `DecimalFormat.setParseBigDecimal(true)` | Parse phần số thực sang `BigDecimal` | Kiểm tra chuỗi đã được tiêu thụ hết nếu cần input chặt chẽ |

Các formatter như `DecimalFormat`/`NumberFormat` **không được bảo đảm thread-safe**. Với server đa người dùng, tránh dùng một instance formatter mutable trong static singleton cho mọi request; tạo theo request/lần xử lý, hoặc quản lý vòng đời riêng và không chia sẻ đồng thời. `Locale` bản thân nó bất biến, có thể truyền qua luồng xử lý một cách an toàn.

**Không dùng `Locale.setDefault(userLocale)` theo request.** Default locale là trạng thái dùng chung trong JVM, có thể gây lẫn ngôn ngữ giữa các request. Hãy truyền đúng `Locale` vào factory.

## 5. Ví dụ Java 17+: so sánh separator theo locale

Tạo file `NumberLocaleDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberLocaleDemo {
    private static String code(char symbol) {
        return String.format("U+%04X", (int) symbol);
    }

    private static void show(String languageTag) {
        Locale locale = Locale.forLanguageTag(languageTag);
        NumberFormat formatter = NumberFormat.getNumberInstance(locale);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        String result = formatter.format(new BigDecimal("1234567.89"));
        // Biểu diễn U+202F rõ ràng trong output để tránh khó quan sát.
        String visible = result.replace("\u202F", "<NNBSP>");
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);

        System.out.println(languageTag + ": " + visible);
        System.out.println("  digits-zero=" + code(symbols.getZeroDigit())
                + ", decimal=" + code(symbols.getDecimalSeparator())
                + ", grouping=" + code(symbols.getGroupingSeparator()));
    }

    public static void main(String[] args) {
        show("en-US");
        show("vi-VN");
        show("fr-FR");
        show("ar-EG-u-nu-latn");
        show("ar-EG");
    }
}
```

Lệnh biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 NumberLocaleDemo.java
java NumberLocaleDemo
```

Kết quả tham chiếu trên JDK dùng CLDR với các ký hiệu đã xác minh:

```text
en-US: 1,234,567.89
  digits-zero=U+0030, decimal=U+002E, grouping=U+002C
vi-VN: 1.234.567,89
  digits-zero=U+0030, decimal=U+002C, grouping=U+002E
fr-FR: 1<NNBSP>234<NNBSP>567,89
  digits-zero=U+0030, decimal=U+002C, grouping=U+202F
ar-EG-u-nu-latn: 1,234,567.89
  digits-zero=U+0030, decimal=U+002E, grouping=U+002C
ar-EG: ١٬٢٣٤٬٥٦٧٫٨٩
  digits-zero=U+0660, decimal=U+066B, grouping=U+066C
```

`<NNBSP>` chỉ là **ký hiệu minh họa do chương trình thay U+202F để in rõ ràng**, không phải một phần của số được định dạng gốc. Ký tự thực sự nằm trong chuỗi là U+202F. Sự khác biệt ký tự có thể khiến hai chuỗi nhìn gần giống nhau nhưng `String.equals` trả `false`.

Giải thích:

- Với `en-US`, dấu thập phân là U+002E (`.`), dấu nhóm U+002C (`,`).
- Với `vi-VN`, hai dấu đảo vai trò; cách hiển thị tương tự `de-DE` cho dữ liệu ví dụ.
- Với `fr-FR`, dấu nhóm là U+202F (*narrow no-break space*); cần giữ nguyên Unicode khi trình bày và kiểm tra dữ liệu.
- Với `ar-EG-u-nu-latn`, extension `nu=latn` yêu cầu chữ số và bộ separator Latin theo môi trường đã kiểm thử.
- Với `ar-EG`, hệ chữ số `arab` dùng U+0660 trở đi, U+066B cho thập phân và U+066C cho phân nhóm.

Kết quả chính xác của dữ liệu locale phụ thuộc runtime/provider; khi xây test snapshot, hãy cố định phiên bản Java và provider hoặc so sánh theo thuộc tính nghiệp vụ phù hợp thay vì giả định mọi JDK đều giống nhau.

## 6. Phân nhóm có thể bật/tắt độc lập

Trong một vài màn hình UI, việc thêm dấu nhóm làm số dễ đọc; trong một số định dạng mã hoặc trường input kỹ thuật, có thể muốn bỏ phân nhóm:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public class GroupingToggleDemo {
    public static void main(String[] args) {
        Locale locale = Locale.US;
        NumberFormat formatter = NumberFormat.getNumberInstance(locale);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        BigDecimal value = new BigDecimal("1234567.89");
        System.out.println(formatter.format(value));

        formatter.setGroupingUsed(false);
        System.out.println(formatter.format(value));
    }
}
```

```bash
javac GroupingToggleDemo.java
java GroupingToggleDemo
```

```text
1,234,567.89
1234567.89
```

Tắt dấu nhóm không có nghĩa đang sử dụng dạng serialization chuẩn cho mọi tình huống: locale vẫn có thể dùng dấu thập phân `,` hoặc chữ số không phải Latin. Một giá trị dùng cho JSON number, config kỹ thuật hoặc giao thức API cần hợp đồng lưu trữ **độc lập locale**.

### Cẩn thận với `DecimalFormat` pattern

Một pattern tiêu chuẩn:

```java
DecimalFormat formatter = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
```

Mẫu `#,##0.00` có:

- `#`: chữ số tùy chọn.
- `0`: chữ số bắt buộc.
- `,`: vị trí phân nhóm trong **pattern không địa phương hóa**.
- `.`: vị trí dấu thập phân trong **pattern không địa phương hóa**.

Những dấu `.`/`,` trong pattern chuẩn **không nhất thiết là ký tự xuất ra**. Ký tự output lấy từ `DecimalFormatSymbols` của locale. `applyPattern(...)` dùng cú pháp pattern chuẩn; `applyLocalizedPattern(...)` mới dùng ký hiệu pattern địa phương hóa. Đừng thay mọi dấu chấm/phẩy trong pattern bằng tay rồi kỳ vọng chính xác.

Trong ví dụ này đoạn code là **minh họa** với `import java.text.DecimalFormat;`, `import java.text.DecimalFormatSymbols;` và `import java.util.Locale;`. Muốn có locale-specific formatter đơn giản, ưu tiên factory `NumberFormat.getNumberInstance(locale)` thay vì viết pattern nếu không cần thiết.

## 7. Parse: cùng chuỗi, ý nghĩa khác nhau theo locale

Hai chuỗi sau không thể hiểu đúng nếu không biết chính sách ngôn ngữ của nguồn:

```text
1,234
1.234
```

Ví dụ với `NumberFormat`:

- `en-US` thường hiểu `1,234` là một nghìn hai trăm ba mươi tư.
- `de-DE` thường hiểu `1,234` là một phẩy hai ba bốn.

Chỉ đổi dấu bằng `replace` có thể tạo lỗi nghiêm trọng khi xử lý lượng tiền, số đo, thống kê hoặc dữ liệu giao dịch. Điều quan trọng là **parse từ locale mà dữ liệu được nhập theo**, không nhất thiết locale của máy chủ. Nếu dữ liệu được lưu dưới dạng JSON number thì không cần parse bằng luật locale.

### Ví dụ Java 17+: parse hai cách và kiểm tra toàn bộ chuỗi

Tạo file `LocaleParsingDemo.java`:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleParsingDemo {
    public static void main(String[] args) throws Exception {
        NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
        NumberFormat germany =
                NumberFormat.getNumberInstance(Locale.GERMANY);

        System.out.println("en-US: " + us.parse("1,234"));
        System.out.println("de-DE: " + germany.parse("1,234"));

        String input = "1,234.56xyz";
        DecimalFormat decimal = new DecimalFormat(
                "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));
        decimal.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = decimal.parse(input, position);

        boolean fullyConsumed = parsed != null
                && position.getIndex() == input.length();

        System.out.println("value: " + parsed);
        System.out.println("type: " + parsed.getClass().getSimpleName());
        System.out.println("consumed: " + position.getIndex());
        System.out.println("fully valid: " + fullyConsumed);
    }
}
```

```bash
javac LocaleParsingDemo.java
java LocaleParsingDemo
```

Kết quả:

```text
en-US: 1234
de-DE: 1.234
value: 1234.56
type: BigDecimal
consumed: 8
fully valid: false
```

Ở đây:

1. Cùng một input `1,234` sinh giá trị khác nhau khi parse theo locale khác.
2. `setParseBigDecimal(true)` giúp nhận `BigDecimal` thay vì chỉ lấy một số nhị phân dấu phẩy động có thể mất chính xác.
3. `parse(input, position)` **có thể parse thành công tiền tố** và bỏ qua đuôi không hợp lệ. Chuỗi `"1,234.56xyz"` có chín ký tự đầu phần số? Trong ví dụ parser tiêu thụ đúng **8 ký tự** (`"1,234.56"`), còn lại `"xyz"`; kiểm tra `position.getIndex() == input.length()` bắt được dữ liệu thừa.

**Bổ sung quan trọng về validation:** parse hết chuỗi cũng **không mặc định xác nhận cách đặt dấu nhóm là hợp lệ theo mọi quy tắc nghiệp vụ**. Một parser số có thể chấp nhận tổ hợp dấu nhóm không đúng pattern dự kiến. Đối với đầu vào cần bảo mật/chính xác cao, xác định rõ chính sách locale, ký tự được phép, phạm vi giá trị, độ chính xác, và kiểm tra đầy đủ định dạng hoặc normalize theo tiêu chuẩn nguồn trước khi dùng dữ liệu. Tránh tin rằng chỉ gọi `NumberFormat.parse(...)` là đủ để xác thực trường tài chính.

## 8. Độ chính xác và rounding: ký tự đúng chưa chắc giá trị đúng

`NumberFormat` làm hai việc có ảnh hưởng dữ liệu: quyết định **cách hiển thị ký tự**, đồng thời có thể **làm tròn** khi đặt số chữ số phần lẻ tối đa.

Ví dụ:

```java
formatter.setMinimumFractionDigits(2);
formatter.setMaximumFractionDigits(2);
```

Hai chữ số sau dấu thập phân luôn được hiển thị nếu có thể, nhưng giá trị nhiều hơn hai chữ số lẻ sẽ được làm tròn theo `RoundingMode` hiện có. Không được hiểu kết quả đã định dạng là con số gốc chính xác hơn dữ liệu ban đầu.

Với tiền tệ, đặc biệt nên dùng `BigDecimal` tạo từ chuỗi hoặc phép toán chính xác (`new BigDecimal("0.1")`), không dùng `new BigDecimal(0.1)` nếu muốn biểu diễn đúng số thập phân 0.1 như người dùng nhập. Thiết lập rounding theo quy tắc nghiệp vụ thay vì ngầm dựa vào default của formatter.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class RoundingLocaleDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));
        formatter.setRoundingMode(RoundingMode.HALF_UP);

        System.out.println(formatter.format(new BigDecimal("1234.565")));
    }
}
```

```bash
javac RoundingLocaleDemo.java
java RoundingLocaleDemo
```

```text
1,234.57
```

Ví dụ này minh họa **quy tắc làm tròn đã chỉ định**, không có nghĩa locale `en-US` bắt buộc luôn dùng `HALF_UP`. Locale mô tả quy ước hiển thị; rounding được chọn theo domain và API.

## 9. Dữ liệu hiển thị khác định dạng lưu trữ

Có hai hướng xử lý phải phân biệt rõ:

### 9.1. Dữ liệu cho người dùng đọc

```text
BigDecimal("1234567.89") + Locale vi-VN
                ↓ NumberFormat
            1.234.567,89
```

Chuỗi này dùng trong giao diện, báo cáo theo ngôn ngữ, hóa đơn hoặc nội dung bản địa hóa. Nó có thể chứa ký tự Unicode không dễ nhận biết hoặc các hệ chữ số không phải Latin. Đây là **đầu ra hiển thị**, không phải chuẩn truyền số giữa các dịch vụ.

### 9.2. Dữ liệu cho máy/giao thức

```text
BigDecimal("1234567.89").toPlainString()
                ↓
            1234567.89
```

Trong JSON, số được biểu diễn theo cú pháp định dạng số của JSON, **không** theo default `Locale`. Với dữ liệu cần giữ chính xác, cân nhắc schema kiểu number, decimal string hoặc integer minor units tùy domain; không gửi `"1.234.567,89"` rồi bắt server đoán.

Tránh:

```java
// Không khuyến nghị cho lưu trữ số độc lập locale:
String stored = NumberFormat.getNumberInstance(
        Locale.getDefault()).format(amount);
```

Lý do: nếu default locale đổi theo máy, theo JVM hoặc theo người dùng, cùng giá trị số học sẽ được serialise thành các chuỗi khác nhau. Đến khi parse lại mà thiếu locale gốc thì thông tin bị mơ hồ.

Nên tách hai lớp:

- **Domain layer:** dùng `int`/`long`/`BigDecimal` với loại dữ liệu và phép tính chuẩn.
- **Presentation layer:** lấy `Locale` của người dùng và format để hiển thị; nếu nhận input dạng chuỗi địa phương hóa, parse với locale đã xác minh.

## 10. Tiền tệ, phần trăm và các trường hợp cần thận trọng

`NumberFormat.getNumberInstance(locale)` không đồng nghĩa với mọi số trong mọi ngữ cảnh. Các factory sau phục vụ quy ước khác nhau:

```java
NumberFormat amount = NumberFormat.getNumberInstance(locale);
NumberFormat money = NumberFormat.getCurrencyInstance(locale);
NumberFormat percent = NumberFormat.getPercentInstance(locale);
```

Đây là **đoạn mã minh họa** với biến `locale` và `import java.text.NumberFormat;` đã khai báo.

- **Tiền tệ:** ký hiệu tiền, vị trí ký hiệu, số phần lẻ và dấu phân cách có thể phụ thuộc locale và currency. Trong nghiệp vụ đa tiền tệ, còn phải chỉ định **`Currency` cụ thể**; locale không phải mã tiền tệ của giao dịch.
- **Phần trăm:** nhiều formatter biến giá trị `0.12` thành biểu diễn 12%; không đưa trực tiếp `12` nếu domain đang dùng 12 phần trăm như 0.12 mà không kiểm tra hợp đồng. Dấu phần trăm và spacing cũng có thể thay đổi.
- **Số âm:** dấu trừ, thứ tự dấu và pattern có thể thay đổi theo locale/kiểu định dạng.
- **Chế độ compact/scientific:** `NumberFormat.getCompactNumberInstance(...)` và scientific format có ngữ nghĩa riêng. Không dùng thuật toán dấu nhóm của số thông thường để dựng tất cả định dạng này.
- **Văn bản hai chiều (RTL):** khi hiển thị số Arab trong giao diện kết hợp Latin/Arabic, cần cân nhắc hướng văn bản và Unicode bidi control; không loại ký tự Unicode bằng cách tự replace vì nhìn thấy thứ tự chưa như ý.

Từ góc nhìn i18n, **chữ số, dấu và cách nhóm thuộc dữ liệu của locale và tùy chọn định dạng**, còn **đơn vị đo, tiền tệ và độ chính xác** thuộc ngữ nghĩa miền ứng dụng.

## 11. Checklist xử lý số theo locale trong ứng dụng

1. **Resolve locale cho từng người dùng/request:** dùng preference đáng tin cậy, validate và giới hạn tập locale hỗ trợ. Không thay `Locale.setDefault` trên server.
2. **Biết đúng kiểu dữ liệu:** số nguyên, decimal chính xác, tiền tệ, phần trăm hay giá trị đo. Chọn `BigDecimal` khi tính chính xác thập phân có ý nghĩa.
3. **Chọn đúng formatter factory:** số thường, tiền tệ, phần trăm hoặc pattern riêng có kiểm thử.
4. **Truyền locale tường minh:** `getNumberInstance(locale)`, không phụ thuộc cấu hình máy.
5. **Thiết lập grouping và fraction digits theo mục đích UI**, không ép mặc định của toàn bộ ứng dụng.
6. **Chọn rounding mode khi làm tròn có tác động nghiệp vụ**; phân biệt làm tròn để hiển thị với giá trị dùng trong phép tính.
7. **Xác minh separator bằng code point** khi gặp khoảng trắng Unicode hoặc digits khác Latin.
8. **Tôn trọng `u-nu`** nếu provider hỗ trợ, nhưng đừng coi mọi numbering system đều được hỗ trợ tuyệt đối.
9. **Parse với locale của nguồn input**, dùng `ParsePosition` nếu cần kiểm tra hết chuỗi, và thêm validation domain.
10. **Tách định dạng lưu trữ độc lập locale** khỏi chuỗi hiển thị.
11. **Kiểm thử locale thực tế trên JDK/provider mục tiêu**, đặc biệt grouping kiểu Ấn Độ, Arabic digits, RTL và các dấu không ngắt.
12. **Không chia sẻ `DecimalFormat` mutable giữa nhiều thread** mà thiếu cơ chế cách ly thích hợp.

## 12. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `Double.parseDouble("1,5")` và cho rằng locale vi-VN đã được áp dụng | `Double.parseDouble` yêu cầu cú pháp số độc lập locale, không dùng dấu `,` thập phân | Dùng `NumberFormat` theo locale cho input người dùng |
| Dùng `replace(",", ".")` với mọi chuỗi | `,` có thể là dấu nhóm; `1,234` mơ hồ | Parse theo locale nguồn |
| Xem whitespace phân nhóm Pháp là ASCII space | Dữ liệu có thể dùng U+202F/U+00A0 | Kiểm tra code point, dùng formatter/parser locale |
| Dùng `#,##,##0` và giả định JDK luôn tạo nhóm Ấn Độ | `DecimalFormat` truyền thống có giới hạn nhóm đa kích thước | Kiểm thử runtime; dùng thư viện hỗ trợ nếu bắt buộc |
| Luôn hiển thị chữ số U+0030–U+0039 | Một số numbering system dùng chữ số khác | Dùng API tôn trọng locale/`u-nu` |
| Xem `u-nu-arab` là bảo đảm mọi API đổi sang chữ số Ả Rập | Hỗ trợ phụ thuộc provider/API | Kiểm tra hỗ trợ và output thực |
| Dùng `NumberFormat.format` để lưu số trong DB/API | Kết quả phụ thuộc locale | Lưu số hoặc decimal string có schema chuẩn |
| Parse một chuỗi có đuôi thừa mà không kiểm tra | `parse` có thể dừng trước cuối chuỗi | Kiểm tra `ParsePosition.getIndex()` và validate bổ sung |
| Dùng `double` cho tất cả phép tính tiền | Có sai số nhị phân dấu phẩy động | Dùng `BigDecimal`/integer minor units theo domain |
| Dùng một `DecimalFormat` static cho mọi thread | Formatter mutable không được bảo đảm thread-safe | Tạo instance riêng theo request/lần xử lý |
| Coi `Locale` là mã currency hoặc múi giờ | Đây là các khái niệm khác nhau | Dùng `Currency` và `ZoneId` thích hợp |
| Quên test số âm, số nhỏ, 0, số thập phân và số lớn | Format có thể khác ở các mép | Viết ma trận kiểm thử theo locale và domain |

## 13. Câu hỏi tự kiểm tra

1. Cùng `1,234`, locale `en-US` và `de-DE` có thể hiểu giống nhau không? **Không.** Đây có thể là `1234` ở en-US nhưng `1.234` ở de-DE.
2. `vi-VN` thường dùng dấu nào cho phần thập phân và dấu nào cho phân nhóm? **Dấu phẩy `,` cho thập phân, dấu chấm `.` cho phân nhóm** trong dữ liệu ví dụ.
3. Vì sao không nên viết `replace(" ", "")` khi xử lý dấu nhóm của `fr-FR`? **Vì dấu nhóm có thể là U+202F, không phải U+0020; thao tác còn có nguy cơ sửa dữ liệu khác.**
4. `u-nu-latn` trong `ar-EG-u-nu-latn` nói lên điều gì? **Yêu cầu hệ chữ số Latin; formatter có thể tôn trọng khi provider hỗ trợ.**
5. `DecimalFormatSymbols.getGroupingSeparator()` nói lên grouping size không? **Không.** Nó chỉ nói ký tự phân nhóm; grouping pattern là quy tắc khác.
6. Vì sao `#,##,##0` trên `DecimalFormat` không nhất thiết cho `12,34,567`? **Vì `DecimalFormat` truyền thống không hỗ trợ tùy ý hai kích thước grouping trong cùng pattern; chỉ lưu khoảng nhóm cuối.**
7. `NumberFormat.setGroupingUsed(false)` có bảo đảm chuỗi luôn có dấu thập phân `.` không? **Không.** Locale vẫn quyết định ký tự thập phân.
8. Lỗi của `parse("1,234.56xyz")` nếu không dùng `ParsePosition` là gì? **Có thể parse số đầu và bỏ `xyz` mà không báo lỗi.**
9. Tại sao `BigDecimal("1234.56")` thích hợp cho giá trị tiền hơn `new BigDecimal(1234.56)`? **String constructor tránh giữ sai số do biểu diễn nhị phân của literal double.**
10. Đâu là khác biệt giữa format ra `1.234,56` cho người dùng và lưu `1234.56` trong API? **Một bên là presentation theo locale; một bên là serialization có hợp đồng độc lập locale.**

## 14. Tài liệu tham khảo

- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): factory format/parse theo locale, grouping, số chữ số phần lẻ.
- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): pattern, parse `BigDecimal`, rounding, thread safety và grouping.
- [Java SE 21 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormatSymbols.html): mã ký tự cho zero digit, decimal separator và grouping separator.
- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): language tag BCP 47, Unicode extension `nu`.
- [Unicode CLDR — Numbers](https://cldr.unicode.org/translation/number-currency-formats): dữ liệu mẫu số/tiền tệ và quy ước định dạng.
- [Unicode TR35 — Numbers](https://unicode.org/reports/tr35/tr35-numbers.html): numbering systems, number patterns và ký hiệu địa phương hóa.
