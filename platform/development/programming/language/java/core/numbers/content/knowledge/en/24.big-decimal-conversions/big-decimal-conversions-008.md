# Parse và format BigDecimal theo locale trong Java

## 1. Vấn đề: cùng một số, nhiều cách viết

Một BigDecimal có giá trị `1234567.50` có thể được hiển thị theo những quy ước khác nhau:

| Locale | Cách hiển thị thường gặp | Dấu thập phân | Dấu nhóm nghìn |
| --- | --- | --- | --- |
| `Locale.US` | `1,234,567.50` | Dấu chấm `.` | Dấu phẩy `,` |
| `Locale.GERMANY` | `1.234.567,50` | Dấu phẩy `,` | Dấu chấm `.` |
| Các locale khác | Có thể dùng chữ số hoặc ký tự Unicode khác | Phụ thuộc locale | Có thể là khoảng trắng/Unicode |

**BigDecimal lưu giá trị số thập phân cùng precision và scale, không lưu locale.** Locale là ngữ cảnh văn hóa/ngôn ngữ dùng để chuyển giá trị thành văn bản hoặc hiểu văn bản do người dùng nhập.

Bài học tập trung vào hai hướng:

- **Format:** `BigDecimal → String` cho giao diện, báo cáo, biểu mẫu.
- **Parse:** `String` theo locale → `BigDecimal` để kiểm tra và tính toán.

Để tránh mất chính xác, xử lý thập phân trực tiếp bằng BigDecimal và lớp `java.text`, không chuyển qua `double` chỉ để format hay parse.

## 2. Các API liên quan và vai trò

| API | Chức năng |
| --- | --- |
| `java.math.BigDecimal` | Biểu diễn thập phân chính xác, độc lập locale |
| `java.util.Locale` | Mô tả ngôn ngữ/vùng; ví dụ `Locale.US`, `Locale.GERMANY`, `Locale.forLanguageTag("vi-VN")` |
| `java.text.NumberFormat` | Lớp nền để format/parse số theo locale |
| `java.text.DecimalFormat` | Cung cấp pattern định dạng và `setParseBigDecimal(true)` |
| `java.text.DecimalFormatSymbols` | Dấu thập phân, dấu nhóm và các ký hiệu số theo locale |
| `java.text.ParsePosition` | Biết parser đã tiêu thụ bao nhiêu ký tự; phát hiện phần thừa |
| `java.math.RoundingMode` | Quy tắc làm tròn khi số chữ số hiển thị bị giới hạn |
| `java.util.Currency` | Định danh đồng tiền, tách biệt với locale |

**Hai loại chuỗi không nên trộn lẫn:**

- Chuỗi số **cho máy**: `1234567.50`, cú pháp thập phân được hợp đồng dữ liệu quy định; `BigDecimal.toPlainString()` tạo chuỗi thập phân không dùng dấu nhóm theo locale.
- Chuỗi số **cho con người**: `1,234,567.50` hay `1.234.567,50`; cách viết phụ thuộc locale.

Đặc biệt `1,234` có thể có nghĩa là 1234 trong US nhưng 1.234 trong Germany. Parser không thể đoán locale một cách đáng tin chỉ từ dấu phẩy/chấm: locale phải được lấy từ cấu hình phiên, lựa chọn người dùng hoặc hợp đồng dữ liệu.

## 3. Format BigDecimal với NumberFormat

Lấy formatter bằng `NumberFormat.getNumberInstance(locale)` hoặc `NumberFormat.getInstance(locale)`. Tùy mục đích hiển thị, cấu hình:

- `setGroupingUsed(true)`: hiển thị dấu phân nhóm phần nguyên.
- `setMinimumFractionDigits(2)`: luôn hiển thị tối thiểu hai chữ số thập phân.
- `setMaximumFractionDigits(2)`: hiển thị tối đa hai chữ số thập phân.
- `setRoundingMode(RoundingMode.HALF_EVEN)`: quy tắc làm tròn nếu phần thập phân dài hơn giới hạn.

`format(value)` nhận trực tiếp BigDecimal thông qua overload `format(Object)`. Không cần gọi `doubleValue()`, vì chuyển đổi này có thể mất precision.

### Ví dụ Java 17: US và Germany

Tạo tệp `LocaleFormatDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Locale;

public class LocaleFormatDemo {
    static String display(BigDecimal value, Locale locale) {
        NumberFormat format = NumberFormat.getNumberInstance(locale);
        format.setGroupingUsed(true);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        format.setRoundingMode(RoundingMode.HALF_EVEN);
        return format.format(value);
    }

    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234567.50");

        System.out.println("US = " + display(amount, Locale.US));
        System.out.println("DE = " + display(amount, Locale.GERMANY));
        System.out.println("plain = " + amount.toPlainString());
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac LocaleFormatDemo.java
java LocaleFormatDemo
~~~

Đầu ra với dữ liệu locale tiêu chuẩn:

~~~text
US = 1,234,567.50
DE = 1.234.567,50
plain = 1234567.50
~~~

Đối tượng `amount` không bị sửa. Chuỗi đã format có mục đích **trình bày**, không phải tự động là cú pháp số hợp lệ cho cơ sở dữ liệu, JSON hoặc constructor BigDecimal.

Nếu dùng `Locale.getDefault()`, kết quả phụ thuộc môi trường chạy. Với API, bài kiểm thử và xử lý server cần tái lập được, nên truyền locale tường minh. Với giao diện, lấy locale từ lựa chọn/ngữ cảnh của người dùng.

## 4. BigDecimal(String) không hiểu ký hiệu theo locale

Constructor `new BigDecimal(String)` đọc cú pháp số thập phân của Java. Nó không biết dấu chấm và dấu phẩy nào là dấu nhóm hay dấu thập phân theo vùng:

| Chuỗi đầu vào | `new BigDecimal(...)` |
| --- | --- |
| `"1234.50"` | Hợp lệ |
| `"-0.125"` | Hợp lệ |
| `"1,234.50"` | `NumberFormatException` |
| `"1.234,50"` | `NumberFormatException` |

Để parse số do người dùng gõ theo locale, cần dùng `NumberFormat`/`DecimalFormat` tương ứng. Không thay toàn bộ dấu phẩy bằng dấu chấm vì trong một số locale dấu phẩy là **dấu thập phân**, nhưng locale khác dùng nó làm **dấu nhóm**. Một số locale sử dụng ký tự phân nhóm Unicode, chẳng hạn khoảng trắng không ngắt dòng.

## 5. Parse trực tiếp ra BigDecimal

`NumberFormat.parse(...)` trả về kiểu `Number`, không bảo đảm luôn là BigDecimal: với cấu hình mặc định, đối tượng kết quả có thể là `Long` hoặc `Double`. Vì thế, đừng cast thẳng về BigDecimal nếu chưa kiểm tra cấu hình.

`DecimalFormat` có phương thức `setParseBigDecimal(true)` để parser tạo BigDecimal cho giá trị số thập phân thông thường. Lấy đối tượng từ `NumberFormat.getNumberInstance(locale)`; trong JDK 17 với các locale phổ biến như US/Germany, formatter này là DecimalFormat. Khi xây dựng thư viện cho provider đặc biệt, nên kiểm tra `instanceof DecimalFormat`.

Điểm quan trọng khác: `parse` có thể chấp nhận **tiền tố hợp lệ** của chuỗi mà bỏ qua ký tự ở phía sau. Với biểu mẫu người dùng, hãy dùng `ParsePosition` và yêu cầu vị trí kết thúc bằng độ dài chuỗi. Bên cạnh đó, kiểm tra kiểu trả về vì `BigDecimal` không biểu diễn được NaN hoặc Infinity.

### Ví dụ Java 17: parse toàn bộ chuỗi

Tạo tệp `LocaleParseDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleParseDemo {
    static BigDecimal parseFull(String text, Locale locale)
            throws ParseException {
        NumberFormat generic = NumberFormat.getNumberInstance(locale);
        if (!(generic instanceof DecimalFormat format)) {
            throw new IllegalStateException("DecimalFormat unavailable");
        }

        format.setParseBigDecimal(true);
        format.setParseIntegerOnly(false);

        ParsePosition position = new ParsePosition(0);
        Number number = format.parse(text, position);
        if (!(number instanceof BigDecimal decimal)
                || position.getIndex() != text.length()) {
            throw new ParseException("Invalid localized number",
                    Math.max(0, position.getIndex()));
        }
        return decimal;
    }

    public static void main(String[] args) throws ParseException {
        BigDecimal us = parseFull("1,234,567.50", Locale.US);
        BigDecimal de = parseFull("1.234.567,50", Locale.GERMANY);

        System.out.println("US = " + us.toPlainString());
        System.out.println("DE = " + de.toPlainString());
        System.out.println("same = " + (us.compareTo(de) == 0));

        try {
            parseFull("1,234.50oops", Locale.US);
            System.out.println("Unexpected acceptance");
        } catch (ParseException ex) {
            System.out.println("Suffix rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac LocaleParseDemo.java
java LocaleParseDemo
~~~

Đầu ra:

~~~text
US = 1234567.50
DE = 1234567.50
same = true
Suffix rejected
~~~

Ở đây `setParseBigDecimal(true)` giữ giá trị decimal mà không đi qua double, còn `ParsePosition` chặn chuỗi có phần đuôi `oops`.

**Giới hạn:** kiểm tra tiêu thụ hết chuỗi **không đồng nghĩa** cú pháp dấu nhóm đã đúng theo quy tắc nghiêm ngặt của biểu mẫu. DecimalFormat có thể parse tương đối dễ dãi với một số vị trí grouping; nếu hợp đồng yêu cầu nhóm ba chữ số chặt chẽ, phải bổ sung validation tương ứng với locale/pattern. Đừng mặc định rằng `setGroupingUsed(true)` tự động kiểm tra cấu trúc nhập hoàn toàn nghiêm ngặt. Trong **Java 17**, API `DecimalFormat.setStrict` chưa có; tránh dùng ví dụ dựa vào API của phiên bản JDK mới hơn.

## 6. DecimalFormatSymbols và mẫu hiển thị

Khi cần pattern xác định, tạo `DecimalFormat` với `DecimalFormatSymbols.getInstance(locale)`. Trong pattern không bản địa hóa:

- `,` là ký hiệu **grouping** của pattern;
- `.` là ký hiệu **decimal** của pattern;
- `0` là chữ số bắt buộc; `#` là chữ số tùy chọn.

Chẳng hạn pattern `#,##0.00` yêu cầu nhóm nghìn và đúng hai chữ số phần lẻ. Với locale Germany, formatter **hiển thị** dấu chấm cho grouping và dấu phẩy cho decimal dù trong pattern viết ngược.

Tạo tệp `LocalePatternDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class LocalePatternDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.GERMANY);
        DecimalFormat formatter =
                new DecimalFormat("#,##0.00", symbols);
        formatter.setRoundingMode(RoundingMode.HALF_EVEN);

        BigDecimal value = new BigDecimal("1234.555");
        System.out.println("formatted = " + formatter.format(value));
        System.out.println("original = " + value.toPlainString());
    }
}
~~~

~~~bash
javac LocalePatternDemo.java
java LocalePatternDemo
~~~

Đầu ra:

~~~text
formatted = 1.234,56
original = 1234.555
~~~

`DecimalFormat.applyPattern(...)` nhận pattern theo ký hiệu chuẩn, trong khi `applyLocalizedPattern(...)` nhận pattern đã bản địa hóa. Không nhầm pattern với chuỗi số nhập vào. Nếu muốn đổi dấu thập phân/dấu nhóm, cấu hình locale/symbols phù hợp; tránh dùng `String.replace` lên chuỗi vì dễ phá số âm, số có nhiều dấu nhóm và tiền tố/hậu tố.

## 7. Format có thể làm tròn: không đảm bảo round-trip

Đối tượng BigDecimal gốc vẫn giữ nguyên khi format, nhưng **chuỗi hiển thị có thể mất chữ số** vì `maximumFractionDigits` và `RoundingMode`. Khi parse lại, những chữ số đã bị mất không thể khôi phục.

Ví dụ `1234.567` format theo US với tối đa hai chữ số lẻ, HALF_UP → `1,234.57`. Parse lại → `1234.57`, khác giá trị gốc.

Tạo tệp `LocaleRoundTripDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleRoundTripDemo {
    public static void main(String[] args) {
        DecimalFormat format =
                (DecimalFormat) NumberFormat.getNumberInstance(Locale.US);
        format.setGroupingUsed(true);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        format.setRoundingMode(RoundingMode.HALF_UP);
        format.setParseBigDecimal(true);

        BigDecimal original = new BigDecimal("1234.567");
        String displayed = format.format(original);
        BigDecimal parsed = (BigDecimal)
                format.parse(displayed, new ParsePosition(0));

        System.out.println("original = " + original);
        System.out.println("displayed = " + displayed);
        System.out.println("parsed = " + parsed);
        System.out.println("same value = "
                + (original.compareTo(parsed) == 0));
    }
}
~~~

~~~bash
javac LocaleRoundTripDemo.java
java LocaleRoundTripDemo
~~~

Đầu ra:

~~~text
original = 1234.567
displayed = 1,234.57
parsed = 1234.57
same value = false
~~~

Ngay cả khi giá trị số học không đổi, **scale có thể khác**: `new BigDecimal("2.0").compareTo(new BigDecimal("2.00")) == 0`, nhưng `equals(...)` trả false vì BigDecimal xét cả scale. Formatter có thể thay đổi số chữ số 0 cuối theo `minimumFractionDigits`/`maximumFractionDigits`; do đó không dùng format→parse như phương thức lưu trữ một giá trị và scale chính xác.

Quy tắc thực hành: giữ BigDecimal gốc trong mô hình dữ liệu; chỉ format khi cần trình bày. Nếu người dùng thực sự chỉnh sửa giá trị, parse bằng locale đã được xác định rồi kiểm tra lại chính sách nghiệp vụ.

## 8. Tiền tệ: Locale và Currency là hai thông tin khác nhau

`NumberFormat.getCurrencyInstance(locale)` tạo cách **trình bày tiền tệ** theo locale; `Currency` xác định **đồng tiền** (USD, EUR, VND...). BigDecimal chỉ lưu con số, không kèm mã đồng tiền. Một số locale có thể sử dụng ký hiệu tương tự nhau cho các đồng tiền khác nhau, nên không suy ra mã ISO 4217 đáng tin chỉ từ ký hiệu hiển thị.

Tạo tệp `LocaleCurrencyDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class LocaleCurrencyDemo {
    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1234.50");
        NumberFormat usd = NumberFormat.getCurrencyInstance(Locale.US);

        usd.setCurrency(Currency.getInstance("USD"));
        usd.setMinimumFractionDigits(2);
        usd.setMaximumFractionDigits(2);
        usd.setRoundingMode(RoundingMode.HALF_EVEN);

        System.out.println(usd.format(value));
        System.out.println(value.toPlainString());
    }
}
~~~

~~~bash
javac LocaleCurrencyDemo.java
java LocaleCurrencyDemo
~~~

Đầu ra với locale US tiêu chuẩn:

~~~text
$1,234.50
1234.50
~~~

**Currency formatter không nhất thiết chấp nhận cùng chuỗi như number formatter.** Cần định nghĩa liệu người dùng nhập cả ký hiệu tiền hoặc chỉ phần số; dùng parser tương ứng và lưu mã currency riêng trong miền nghiệp vụ. Không giả định mọi loại tiền đều dùng hai chữ số thập phân: cấu hình theo chính sách đồng tiền/giao dịch.

Với Việt Nam, có thể truyền `Locale.forLanguageTag("vi-VN")`. Đầu ra chính xác về dấu cách, dấu nhóm và vị trí ký hiệu có thể tùy dữ liệu locale và provider của JDK; không hard-code chúng trong phép tính hoặc kiểm thử chạy đa môi trường.

## 9. Luồng xử lý input từ UI và API

Một luồng nhập số từ người dùng nên được xác định rõ trước khi code:

1. **Xác định locale đáng tin cậy** từ lựa chọn/ngữ cảnh người dùng hoặc hợp đồng API. Đừng đoán locale từ chuỗi số.
2. **Quy định những gì được phép nhập:** dấu nhóm, số âm, khoảng trắng đầu/cuối, số mũ, ký hiệu tiền hoặc số chữ số phần lẻ tối đa.
3. **Parse bằng DecimalFormat theo locale** và bật `setParseBigDecimal(true)`, kiểm tra tiêu thụ hết chuỗi bằng `ParsePosition`.
4. **Bổ sung kiểm tra cú pháp nếu cần nhập nghiêm ngặt.** Vị trí dấu nhóm, Unicode whitespace và dấu phân cách phải được xét theo locale thật; việc parse thành công chưa chắc là input hợp lệ theo chính sách sản phẩm.
5. **Kiểm tra nghiệp vụ:** giá trị min/max, loại tiền, số chữ số lẻ, rounding mode. Không làm tròn dữ liệu vừa nhập một cách âm thầm nếu quy định yêu cầu từ chối.
6. **Lưu và trao đổi định dạng máy được quy định:** ví dụ decimal string không dấu nhóm; JSON number chỉ khi các bên giữ độ chính xác cần thiết. Chỉ format có locale ở bước xuất giao diện.

Một yêu cầu thường gặp là chỉ chấp nhận số tiền có **không quá hai chữ số lẻ mang giá trị**. Có thể dùng `setScale(2, RoundingMode.UNNECESSARY)` để từ chối khi phải mất giá trị do cắt chữ số. Cách này không kiểm tra số chữ số 0 mà người dùng gõ, vì `12.5000` có thể chuyển chính xác thành `12.50`.

### Ví dụ Java 17: kiểm tra scale không tự làm tròn

Tạo tệp `LocaleScalePolicyDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class LocaleScalePolicyDemo {
    static BigDecimal requireCents(BigDecimal input) {
        return input.setScale(2, RoundingMode.UNNECESSARY);
    }

    public static void main(String[] args) {
        System.out.println(requireCents(new BigDecimal("12.5")));
        System.out.println(requireCents(new BigDecimal("12.5000")));

        try {
            System.out.println(requireCents(new BigDecimal("12.345")));
        } catch (ArithmeticException ex) {
            System.out.println("Rejected: fractional value would be lost");
        }
    }
}
~~~

~~~bash
javac LocaleScalePolicyDemo.java
java LocaleScalePolicyDemo
~~~

Đầu ra:

~~~text
12.50
12.50
Rejected: fractional value would be lost
~~~

Nếu nghiệp vụ đòi từ chối cả `12.5000` vì chuỗi **đã nhập bốn chữ số lẻ**, phải có kiểm tra cú pháp/độ dài đầu vào riêng trước hoặc trong khi parse. Đừng nhầm kiểm tra tính chính xác số học với kiểm tra hình thức văn bản.

## 10. An toàn luồng và formatter có trạng thái

`BigDecimal` là bất biến. `NumberFormat` và `DecimalFormat` lại **có trạng thái mutable**: gọi `setRoundingMode`, `setCurrency`, `setParseBigDecimal` hay `setMaximumFractionDigits` thay đổi hành vi của instance.

Các formatter này **không mặc định thread-safe**. Không chia sẻ một `static DecimalFormat` có thể bị chỉnh sửa giữa nhiều request đồng thời mà thiếu đồng bộ hóa. Cách dễ hiểu là tạo formatter theo từng request/luồng; nếu dùng cache hoặc clone để tối ưu, phải kiểm soát đồng thời và việc thay đổi cấu hình.

Tránh phụ thuộc `Locale.getDefault()` cho kết quả phải tái lập. Trong kiểm thử, luôn chọn locale tường minh. Trong UI, dùng locale thực của người dùng; trong API, hợp đồng nhận dữ liệu phải nói rõ dạng số được chấp nhận.

## 11. Các lỗi phổ biến

1. **Dùng `new BigDecimal("1.234,50")`:** constructor không parse theo locale; dùng DecimalFormat với Locale.GERMANY.
2. **Cast `NumberFormat.parse(...)` về BigDecimal không bật `setParseBigDecimal(true)`:** dễ gặp ClassCastException hoặc đi qua kiểu không mong muốn.
3. **Chỉ bắt ParseException:** `parse` có thể nhận tiền tố và bỏ phần dư, nên cần kiểm tra ParsePosition.
4. **Nghĩ ParsePosition đảm bảo dấu nhóm hoàn toàn đúng:** parser có thể dễ dãi; kiểm tra input chuẩn theo locale nếu cần.
5. **Tự thay `,` thành `.`:** không hỗ trợ dấu nhóm Unicode, vị trí dấu hoặc locale khác.
6. **Chuyển BigDecimal sang double trước format:** có thể mất độ chính xác.
7. **Không cấu hình giới hạn chữ số và rounding mode:** chuỗi hiển thị có thể bị làm tròn ngoài mong đợi.
8. **Dùng round-trip format→parse để lưu giá trị:** chữ số bị cắt và scale gốc có thể mất.
9. **Trộn locale và loại tiền:** tiền tệ là metadata nghiệp vụ riêng, không chỉ là ký hiệu hiển thị.
10. **Tạo một DecimalFormat static dùng chung đa luồng:** có nguy cơ hành vi không an toàn trong truy cập đồng thời.
11. **Bỏ qua input đặc biệt như NaN/Infinity:** BigDecimal không biểu diễn được các giá trị ấy; kiểm tra kiểu sau parse.
12. **Dùng locale mặc định trong API/test:** có thể thay đổi giữa máy và gây kết quả khó lặp lại.

## 12. Tự kiểm tra

**Câu 1.** Chuỗi `"1.234,50"` nên được parse theo locale nào để có số `1234.50`?

**Đáp án:** `Locale.GERMANY`. BigDecimal(String) không parse trực tiếp chuỗi này.

**Câu 2.** Tại sao `"1,234"` không đủ để xác định giá trị số khi chưa biết locale?

**Đáp án:** Trong US dấu phẩy thường phân nhóm hàng nghìn (1234), trong Germany dấu phẩy thường là dấu thập phân (1.234).

**Câu 3.** Với formatter US, maxFractionDigits=2, HALF_UP, BigDecimal `1234.567` hiển thị gì? Parse lại có bằng số gốc không?

**Đáp án:** `1,234.57`, parse lại thành `1234.57` nên khác số gốc.

**Câu 4.** `ParsePosition.getIndex() == text.length()` có đảm bảo mọi dấu nhóm đặt đúng quy cách không?

**Đáp án:** Không. Nó chỉ kiểm tra đã parse hết ký tự; cú pháp grouping có thể cần được kiểm tra bổ sung.

**Câu 5.** `setScale(2, UNNECESSARY)` có từ chối `12.5000` không?

**Đáp án:** Không; giá trị chuyển chính xác thành `12.50`. Nếu cần từ chối chuỗi có quá hai chữ số sau dấu, phải kiểm tra input dưới dạng văn bản.

**Câu 6.** Tại sao không nên dùng một instance DecimalFormat mutable chung cho mọi request?

**Đáp án:** NumberFormat/DecimalFormat không tự đồng bộ; nhiều luồng có thể truy cập/tráo đổi trạng thái và cho kết quả không đáng tin.

## 13. Tổng kết

- **BigDecimal giữ số thập phân; Locale chỉ cách ghi/đọc văn bản**, vì vậy phân biệt dữ liệu máy và giao diện.
- **Format:** lấy NumberFormat theo locale, cấu hình grouping, số chữ số lẻ và RoundingMode; truyền BigDecimal trực tiếp.
- **Parse:** lấy DecimalFormat theo locale, bật `setParseBigDecimal(true)`, kiểm tra `ParsePosition`, kiểu trả về và ràng buộc nghiệp vụ.
- **Không giả định round-trip bảo toàn thông tin** nếu định dạng có làm tròn hoặc thay scale; không dùng double làm trung gian.
- Formatter mutable cần quản lý theo luồng, locale phải được lựa chọn rõ ràng, và đồng tiền phải được lưu độc lập với số.

Tài liệu API Java SE 17: [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), [NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html), [DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html), [DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html) và [ParsePosition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html).